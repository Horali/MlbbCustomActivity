"""Sender: pushes presence to Discord desktop over IPC. Send only on change, max once per 15 s."""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

MIN_INTERVAL = 15.0
_UNSET = object()


class Debouncer:
    """Decides when a new payload may go out. Pure: the caller gives the clock."""

    def __init__(self, min_interval: float = MIN_INTERVAL) -> None:
        self.min_interval = min_interval
        self.sent: Any = _UNSET
        self.sent_at: float | None = None

    def due(self, payload: Any, now: float) -> bool:
        if payload == self.sent:
            return False
        if self.sent_at is None or self.sent is _UNSET:
            return True
        return now - self.sent_at >= self.min_interval

    def mark(self, payload: Any, now: float) -> None:
        self.sent, self.sent_at = payload, now

    def reset(self) -> None:
        self.sent, self.sent_at = _UNSET, None


class Sender:
    def __init__(self, app_id: str) -> None:
        self.app_id = app_id
        self.rpc = None
        self.debounce = Debouncer()

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
        if not self.debounce.due(payload, now):
            return
        if not self._connect():
            return
        try:
            if payload is None:
                self.rpc.clear()
                log.info("presence cleared")
            else:
                self.rpc.update(**payload)
                log.info("presence: %s | %s", payload.get("details"), payload.get("state"))
            self.debounce.mark(payload, now)
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
