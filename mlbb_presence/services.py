"""Captures and tools that run only while MLBB runs on the phone.

When the game opens, start the lobby capture and (if FIXLAG_DIR is set) the FixLag chat
viewer and lag mapper, then open one Chrome window with a tab for each tool. When the
game stays closed for GRACE_SECONDS, stop all of it and close the window, so no tcpdump
runs on the phone while you do not play. A quick restart of the game keeps everything.
"""
from __future__ import annotations

import logging
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from .browser import ToolTabs
from .lobby import LobbyTracker, run_capture

log = logging.getLogger(__name__)
# Both FixLag tools capture this port range; one pkill ends the tcpdump of each.
FIXLAG_TCPDUMP = "udp portrange 5000-5999"
GRACE_SECONDS = 60.0


def port_in_use(url: str) -> bool:
    u = urlparse(url)
    try:
        with socket.create_connection((u.hostname or "127.0.0.1", u.port or 80), timeout=1):
            return True
    except OSError:
        return False


def page_url(url: str) -> str:
    """http://127.0.0.1:8790/events -> http://127.0.0.1:8790/"""
    u = urlparse(url)
    return f"{u.scheme or 'http'}://{u.netloc}/" if u.netloc else ""


class Services:
    def __init__(self, adb: str, tracker: LobbyTracker, *, lobby: bool = True,
                 fixlag_dir: str = "", viewer_url: str = "", mapper_url: str = "",
                 tabs: ToolTabs | None = None, grace_seconds: float = GRACE_SECONDS) -> None:
        self.adb = adb
        self.tracker = tracker
        self.lobby = lobby
        self.fixlag_dir = Path(fixlag_dir) if fixlag_dir else None
        self.viewer_url = viewer_url
        self.mapper_url = mapper_url
        self.tabs = tabs
        self.grace_seconds = grace_seconds
        self.serial = ""
        self._stop: threading.Event | None = None
        self._tools: dict[str, subprocess.Popen] = {}
        self._closed_since: float | None = None

    @property
    def running(self) -> bool:
        return self._stop is not None

    def update(self, game_running: bool | None, serial: str, now: float | None = None) -> None:
        """game_running None = phone not reachable: change nothing."""
        if game_running is None:
            return
        now = time.time() if now is None else now
        if self.running and serial and serial != self.serial:
            # USB unplugged or the wireless port changed: the capture thread reads
            # self.serial on each restart, so it moves to the new link.
            log.info("phone serial changed: %s -> %s", self.serial, serial)
            self.serial = serial
            if self._tools:  # our FixLag tools are bound to the old serial
                self._stop_tools()
                self._start_tools(serial)
        if game_running:
            if self._closed_since is not None:
                log.info("MLBB back within %.0f s: keeping the tools", self.grace_seconds)
            self._closed_since = None
            if not self.running and serial:
                self.start(serial)
        elif self.running:
            if self._closed_since is None:
                self._closed_since = now
                log.info("MLBB closed: stopping in %.0f s if it stays closed", self.grace_seconds)
            if now - self._closed_since >= self.grace_seconds:
                self.stop()

    def start(self, serial: str) -> None:
        self.serial = serial
        self._stop = threading.Event()
        self._closed_since = None
        log.info("MLBB opened: starting captures on %s", serial)
        if self.lobby:
            threading.Thread(target=run_capture, args=(self.adb, lambda: self.serial, self.tracker,
                                                       self._stop), daemon=True).start()
        self._start_tools(serial)
        if self.tabs is not None:
            urls = [u for u in (page_url(self.viewer_url), page_url(self.mapper_url)) if u]
            self.tabs.open(urls)

    def _tool_commands(self, serial: str) -> dict[str, tuple[str, list[str]]]:
        out: dict[str, tuple[str, list[str]]] = {}
        if self.viewer_url:
            port = urlparse(self.viewer_url).port or 8765
            out["chat viewer"] = (self.viewer_url, ["-m", "tools.chat_viewer", "--adb", serial,
                                                    "--port", str(port), "--adb-path", self.adb])
        if self.mapper_url:
            port = urlparse(self.mapper_url).port or 8766
            out["lag mapper"] = (self.mapper_url, ["-m", "tools.lag_mapper", "--serial", serial,
                                                   "--port", str(port), "--adb-path", self.adb,
                                                   "--no-browser"])
        return out

    def _start_tools(self, serial: str) -> None:
        if not self.fixlag_dir:
            return
        for name, (url, args) in self._tool_commands(serial).items():
            if port_in_use(url):  # already running (started by hand): use that one
                log.info("%s already listens on %s", name, url)
                continue
            try:
                self._tools[name] = subprocess.Popen([sys.executable, *args], cwd=self.fixlag_dir,
                                                     stdout=subprocess.DEVNULL,
                                                     stderr=subprocess.DEVNULL)
                log.info("%s started: %s", name, page_url(url))
            except OSError as exc:
                log.warning("%s failed to start: %s", name, exc)

    def stop(self) -> None:
        log.info("MLBB closed: stopping captures and tools")
        self.tracker.clear()
        self._closed_since = None
        if self._stop is not None:
            self._stop.set()
            self._stop = None
        if self.tabs is not None:
            self.tabs.close()
        self._stop_tools()

    def _stop_tools(self) -> None:
        if not self._tools:
            return
        for proc in self._tools.values():
            proc.terminate()
        for proc in self._tools.values():
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._tools.clear()
        self._pkill(FIXLAG_TCPDUMP)

    def _pkill(self, pattern: str) -> None:
        if not self.serial:
            return
        try:
            subprocess.run([self.adb, "-s", self.serial, "shell", f"su -c 'pkill -f \"{pattern}\"'"],
                           capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
