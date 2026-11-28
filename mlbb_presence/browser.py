"""A Chrome window with one tab per FixLag tool, opened and closed by the bridge.

Chrome runs with its own profile folder, so it is a separate Chrome process that the
bridge owns: closing it does not touch the user's normal Chrome windows.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Sequence

log = logging.getLogger(__name__)

CHROME_CANDIDATES = (
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
)
PROFILE_DIR = Path(os.environ.get("LOCALAPPDATA", ".")) / "mlbb_presence" / "chrome-tools"
READY_TIMEOUT = 45.0  # seconds to wait for the tool servers before the tabs open anyway


def find_chrome(override: str = "") -> str:
    if override:
        return override
    for path in CHROME_CANDIDATES:
        if path.is_file():
            return str(path)
    return ""


def chrome_command(chrome: str, urls: Sequence[str], profile: Path = PROFILE_DIR) -> list[str]:
    return [chrome, f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
            "--new-window", *urls]


class ToolTabs:
    """Open the tool tabs when the servers answer; close the whole window on close()."""

    def __init__(self, chrome: str, is_ready: Callable[[str], bool]) -> None:
        self.chrome = chrome
        self.is_ready = is_ready
        self._proc: subprocess.Popen | None = None
        self._cancel: threading.Event | None = None
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        return self._proc is not None or self._cancel is not None

    def open(self, urls: Sequence[str]) -> None:
        if not self.chrome or not urls or self.is_open:
            return
        cancel = threading.Event()
        self._cancel = cancel
        threading.Thread(target=self._open_when_ready, args=(list(urls), cancel), daemon=True).start()

    def _open_when_ready(self, urls: list[str], cancel: threading.Event) -> None:
        deadline = time.monotonic() + READY_TIMEOUT
        while not cancel.is_set() and time.monotonic() < deadline:
            if all(self.is_ready(u) for u in urls):
                break
            cancel.wait(1.0)
        with self._lock:
            if cancel.is_set():
                return
            try:
                self._proc = subprocess.Popen(chrome_command(self.chrome, urls),
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                log.info("tool tabs opened: %s", ", ".join(urls))
            except OSError as exc:
                log.warning("tool tabs failed to open: %s", exc)

    def close(self) -> None:
        with self._lock:
            if self._cancel is not None:
                self._cancel.set()
                self._cancel = None
            proc, self._proc = self._proc, None
        if proc is None:
            return
        # /T: also end the Chrome child processes (renderers, GPU).
        try:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
        log.info("tool tabs closed")
