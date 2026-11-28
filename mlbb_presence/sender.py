"""Sender: pushes presence to Discord desktop over IPC. Send only on change, max once per 15 s."""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

MIN_INTERVAL = 15.0
REFRESH = 60.0
_UNSET = object()


class Debouncer:
    """Decides when a new payload may go out. Pure: the caller gives the clock."""

    def __init__(self, min_interval: float = MIN_INTERVAL, refresh: float = REFRESH) -> None:
        self.min_interval = min_interval
        self.refresh = refresh
        self.sent: Any = _UNSET
        self.sent_at: float | None = None

    def due(self, payload: Any, now: float) -> bool:
        if payload == self.sent:
            # Re-send the same card now and then: a Discord reload drops it silently.
            return payload is not None and now - self.sent_at >= self.refresh
        if self.sent_at is None or self.sent is _UNSET:
            return True
        return now - self.sent_at >= self.min_interval

    def mark(self, payload: Any, now: float) -> None:
        self.sent, self.sent_at = payload, now

    def reset(self) -> None:
        self.sent, self.sent_at = _UNSET, None


class Sender:
    """controller: an optional ControllerClient (Activity Controller traffic light).
    green or none (no controller) = show the card; red or wait = clear it."""

    def __init__(self, app_id: str, controller: Any = None) -> None:
        self.app_id = app_id
        self.rpc = None
        self.debounce = Debouncer()
        self.controller = controller
        self._light: str | None = None

    def _showing(self) -> bool:
        return self.rpc is not None and self.debounce.sent not in (None, _UNSET)

    def _report(self, payload: dict[str, Any] | None) -> None:
        if self.controller is None:
            return
        preview = None
        if payload is not None:
            preview = {"headline": "Playing Mobile Legends",
                       "details": str(payload.get("details") or ""),
                       "state": str(payload.get("state") or "")}
        self.controller.update(online=payload is not None, showing=self._showing(), preview=preview)

    def _connect(self) -> bool:
        if self.rpc is not None:
            return True
        try:
            from pypresence import Presence
            rpc = Presence(self.app_id)
            rpc.connect()
        except Exception as exc:  # Discord not running
            log.debug("discord not reachable: %s", exc)
            return False
        self.rpc = rpc
        self.debounce.reset()
        log.info("connected to Discord")
        return True

    def push(self, payload: dict[str, Any] | None, now: float) -> None:
        light = self.controller.light if self.controller is not None else "none"
        wanted = payload
        if light in ("red", "wait"):
            payload = None
        # A light change goes out at once: a red must not wait for the 15 s debounce.
        light_changed = light != self._light and self._light is not None
        self._light = light
        try:
            if not light_changed and not self.debounce.due(payload, now):
                return
            if not self._connect():
                return
            self._send(payload, now)
        finally:
            self._report(wanted)

    def _send(self, payload: dict[str, Any] | None, now: float) -> None:
        try:
            if payload is None:
                self.rpc.clear()
                log.info("presence cleared")
            else:
                self.rpc.update(**payload)
                log.info("presence: %s | %s", payload.get("details"), payload.get("state"))
            self.debounce.mark(payload, now)
            if self.controller is not None:
                self.controller.poke()
        except Exception as exc:  # Discord closed: reconnect next time
            log.warning("discord update failed, will reconnect: %s", exc)
            self.close()

    def close(self) -> None:
        if self.rpc is not None:
            try:
                self.rpc.close()
            except Exception:
                pass
        self.rpc = None
