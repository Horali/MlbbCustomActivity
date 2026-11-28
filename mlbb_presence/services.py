"""Captures that run only while MLBB runs on the phone.

When the game opens, start the lobby capture and (if FIXLAG_DIR is set and nothing
listens on the viewer port yet) the FixLag chat viewer. When the game closes, stop both,
so no tcpdump runs on the phone while you do not play.
"""
from __future__ import annotations

import logging
import socket
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

from .lobby import LobbyTracker, run_capture

log = logging.getLogger(__name__)
VIEWER_TCPDUMP = "udp portrange 5000-5999"  # the FixLag chat viewer filter


def port_in_use(url: str) -> bool:
    u = urlparse(url)
    try:
        with socket.create_connection((u.hostname or "127.0.0.1", u.port or 80), timeout=1):
            return True
    except OSError:
        return False


class Services:
    def __init__(self, adb: str, tracker: LobbyTracker, *, lobby: bool = True,
                 fixlag_dir: str = "", viewer_url: str = "") -> None:
        self.adb = adb
        self.tracker = tracker
        self.lobby = lobby
        self.fixlag_dir = Path(fixlag_dir) if fixlag_dir else None
        self.viewer_url = viewer_url
        self.serial = ""
        self._stop: threading.Event | None = None
        self._viewer: subprocess.Popen | None = None

    @property
    def running(self) -> bool:
        return self._stop is not None

    def update(self, game_running: bool | None, serial: str) -> None:
        """game_running None = phone not reachable: change nothing."""
        if game_running is None:
            return
        if self.running and serial and serial != self.serial:
            # USB unplugged or the wireless port changed: the capture thread reads
            # self.serial on each restart, so it moves to the new link.
            log.info("phone serial changed: %s -> %s", self.serial, serial)
            self.serial = serial
            if self._viewer is not None:  # our chat viewer is bound to the old serial
                self._stop_viewer()
                self._start_viewer(serial)
        if game_running and not self.running and serial:
            self.start(serial)
        elif not game_running and self.running:
            self.stop()

    def start(self, serial: str) -> None:
        self.serial = serial
        self._stop = threading.Event()
        log.info("MLBB opened: starting captures on %s", serial)
        if self.lobby:
            threading.Thread(target=run_capture, args=(self.adb, lambda: self.serial, self.tracker,
                                                       self._stop), daemon=True).start()
        self._start_viewer(serial)

    def _start_viewer(self, serial: str) -> None:
        if self.fixlag_dir and self.viewer_url and not port_in_use(self.viewer_url):
            port = urlparse(self.viewer_url).port or 8765
            cmd = [sys.executable, "-m", "tools.chat_viewer", "--adb", serial, "--port", str(port),
                   "--adb-path", self.adb]
            try:
                self._viewer = subprocess.Popen(cmd, cwd=self.fixlag_dir,
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                log.info("chat viewer started on port %s", port)
            except OSError as exc:
                log.warning("chat viewer failed to start: %s", exc)

    def stop(self) -> None:
        log.info("MLBB closed: stopping captures")
        if self._stop is not None:
            self._stop.set()
            self._stop = None
        self._stop_viewer()

    def _stop_viewer(self) -> None:
        if self._viewer is not None:
            self._viewer.terminate()
            try:
                self._viewer.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._viewer.kill()
            self._viewer = None
            self._pkill(VIEWER_TCPDUMP)

    def _pkill(self, pattern: str) -> None:
        if not self.serial:
            return
        try:
            subprocess.run([self.adb, "-s", self.serial, "shell", f"su -c 'pkill -f \"{pattern}\"'"],
                           capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
