"""Game watcher: is MLBB running on the phone, is it on screen, and since when."""
from __future__ import annotations

import html
import re
import subprocess
import time
from dataclasses import dataclass

PACKAGE = "com.mobile.legends"


@dataclass(frozen=True)
class GameInfo:
    running: bool
    foreground: bool = False
    started_at: float | None = None  # unix time of the game process start
    idle_seconds: float | None = None  # time since the last touch on the phone


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


_IDLE_RE = re.compile(r"lastUserActivityTime=\d+ \((\d+) ms ago\)")


def parse_idle(output: str) -> float | None:
    """Seconds since the last touch, from `dumpsys power`."""
    m = _IDLE_RE.search(output)
    return int(m.group(1)) / 1000 if m else None


PREFS = f"/data/data/{PACKAGE}/shared_prefs/{PACKAGE}.v2.playerprefs.xml"
_PREF_RE = re.compile(r'name="OfflineRole(Name|Level)"(?: value="([^"]*)" />|>([^<]*)<)')


def parse_profile(text: str) -> tuple[str, str]:
    """(ign, level) from the game's player prefs. The game saves the last role here."""
    found = {}
    for key, attr, body in _PREF_RE.findall(text):
        found[key] = html.unescape(attr or body).strip()
    return found.get("Name", ""), found.get("Level", "")


def pick_device(devices_output: str, model: str = "") -> str:
    """First ready serial in `adb devices -l` output. USB serials win over wireless ones.
    With `model` (for example SM_S936B), other phones on adb are skipped."""
    ready = [ln.split()[0] for ln in devices_output.splitlines()[1:]
             if len(ln.split()) >= 2 and ln.split()[1] == "device"
             and (not model or f"model:{model}" in ln.split())]
    usb = [s for s in ready if ":" not in s]
    return (usb or ready or [""])[0]


class GameWatcher:
    def __init__(self, adb: str, serial: str = "", model: str = "") -> None:
        self.adb = adb
        self.serial = serial
        self.model = model

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
            self.serial = pick_device(self._run("devices", "-l") or "", self.model)
            if not self.serial:
                return None
        out = self._run("-s", self.serial, "shell", *args)
        if out is None and not self.fixed:
            self.serial = ""  # wireless port changed: pick again next time
        return out

    def profile(self) -> tuple[str, str]:
        """(ign, level) from the phone. Needs root; ("", "") when not available."""
        out = self._shell(f"su -c 'grep -E OfflineRole {PREFS}'") or ""
        return parse_profile(out)

    def poll(self) -> GameInfo | None:
        """None means the phone is not reachable."""
        ps = self._shell("ps", "-A", "-o", "PID,ETIME,NAME")
        if ps is None:
            return None
        running, started = parse_ps(ps, time.time())
        if not running:
            return GameInfo(running=False)
        acts = self._shell("dumpsys", "activity", "activities") or ""
        foreground = parse_foreground(acts)
        idle = parse_idle(self._shell("dumpsys", "power") or "") if foreground else None
        return GameInfo(running=True, foreground=foreground, started_at=started, idle_seconds=idle)
