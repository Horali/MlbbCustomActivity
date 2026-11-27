"""Game watcher: is MLBB running on the phone, is it on screen, and since when."""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass

PACKAGE = "com.mobile.legends"


@dataclass(frozen=True)
class GameInfo:
    running: bool
    foreground: bool = False
    started_at: float | None = None  # unix time of the game process start


def parse_etime(etime: str) -> int | None:
    """`ps` ETIME `[[dd-]hh:]mm:ss` -> seconds."""
    etime = etime.strip()
    if not etime:
        return None
    days = 0
    if "-" in etime:
        d, etime = etime.split("-", 1)
        days = int(d)
    try:
        parts = [int(p) for p in etime.split(":")]
    except ValueError:
        return None
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts[-3:]
    return ((days * 24 + h) * 60 + m) * 60 + s


def parse_ps(output: str, now: float) -> tuple[bool, float | None]:
    """Find the main MLBB process in `ps -A -o PID,ETIME,NAME` output."""
    for line in output.splitlines():
        cols = line.split()
        if len(cols) >= 3 and cols[-1] == PACKAGE:
            secs = parse_etime(cols[1])
            return True, (now - secs) if secs is not None else None
    return False, None


def parse_foreground(output: str) -> bool:
    """True when the resumed activity line in `dumpsys activity activities` is MLBB."""
    for line in output.splitlines():
        if ("ResumedActivity" in line) and PACKAGE in line:
            return True
    return False


def pick_device(devices_output: str) -> str:
    """First ready serial in `adb devices` output. USB serials win over wireless ones."""
    ready = [ln.split()[0] for ln in devices_output.splitlines()[1:]
             if len(ln.split()) >= 2 and ln.split()[1] == "device"]
    usb = [s for s in ready if ":" not in s]
    return (usb or ready or [""])[0]


class GameWatcher:
    def __init__(self, adb: str, serial: str = "") -> None:
        self.adb = adb
        self.serial = serial

        self.fixed = bool(serial)

    def _run(self, *args: str) -> str | None:
        try:
            res = subprocess.run([self.adb, *args], capture_output=True, text=True, timeout=10,
                                 encoding="utf-8", errors="replace")
        except (OSError, subprocess.TimeoutExpired):
            return None
        return res.stdout if res.returncode == 0 else None

    def _shell(self, *args: str) -> str | None:
        if not self.serial:
            self.serial = pick_device(self._run("devices") or "")
            if not self.serial:
                return None
        out = self._run("-s", self.serial, "shell", *args)
        if out is None and not self.fixed:
            self.serial = ""  # wireless port changed: pick again next time
        return out

    def poll(self) -> GameInfo | None:
        """None means the phone is not reachable."""
        ps = self._shell("ps", "-A", "-o", "PID,ETIME,NAME")
        if ps is None:
            return None
        running, started = parse_ps(ps, time.time())
        if not running:
            return GameInfo(running=False)
        acts = self._shell("dumpsys", "activity", "activities") or ""
        return GameInfo(running=True, foreground=parse_foreground(acts), started_at=started)
