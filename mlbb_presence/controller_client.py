"""Check-in helper for Python projects (PLAN.md section 7).

Copy this file into a project. Standard library only (Python 3.10+).

    ctl = ControllerClient("mlbb", "Mobile Legends", on_change=wake.set)
    ctl.start()
    ctl.update(online=True, showing=False, preview={"headline": "...", "details": "...", "state": "..."})
    if ctl.light in ("red", "wait"): hide the card

light: 'wait' (no answer yet), 'green', 'red', or 'none' (no controller: work alone, PLAN.md 4.4).
"""
from __future__ import annotations

import json
import threading
import urllib.request
from typing import Any, Callable


class ControllerClient:
    def __init__(self, id: str, name: str, url: str = "http://127.0.0.1:47400",
                 interval: float = 2.0, timeout: float = 1.5,
                 on_change: Callable[[], None] | None = None) -> None:
        self.id, self.name, self.url = id, name, url.rstrip("/")
        self.interval, self.timeout = interval, timeout
        self.on_change = on_change
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {"ownSwitch": "on", "online": False, "idle": False,
                                       "showing": False, "preview": None}
        self._light = "wait"
        self._switch: str | None = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def light(self) -> str:
        return self._light

    @property
    def switch(self) -> str | None:
        return self._switch

    def update(self, *, online: bool, showing: bool, idle: bool = False,
               own_switch: str = "on", preview: dict[str, str] | None = None) -> None:
        new = {"ownSwitch": own_switch, "online": bool(online), "idle": bool(idle),
               "showing": bool(showing), "preview": preview}
        with self._lock:
            changed = new != self._state
            self._state = new
        if changed:
            self.poke()

    def poke(self) -> None:
        """Check in at once (for example right after the card changed)."""
        self._wake.set()

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="controller-checkin", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _checkin_once(self) -> None:
        with self._lock:
            body = {"id": self.id, "name": self.name, **self._state}
        try:
            req = urllib.request.Request(
                f"{self.url}/v1/checkin", data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                ans = json.loads(res.read().decode("utf-8"))
            light = "green" if ans.get("light") == "green" else "red"
            switch = "off" if ans.get("switch") == "off" else "on"
        except Exception:  # no controller, or a bad answer: work alone
            light, switch = "none", None
        if (light, switch) != (self._light, self._switch):
            self._light, self._switch = light, switch
            if self.on_change is not None:
                try:
                    self.on_change()
                except Exception:
                    pass

    def _run(self) -> None:
        while not self._stop.is_set():
            self._checkin_once()
            self._wake.wait(self.interval)
            self._wake.clear()
