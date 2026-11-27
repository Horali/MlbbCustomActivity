"""Match watcher: reads the FixLag chat viewer SSE stream (`/events`)."""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MatchInfo:
    match_id: str
    phase: str  # "IDLE" | "DRAFT" | "LOADING" | "BATTLE"
    mode: str = ""
    is_custom: bool = False
    party_size: int | None = None
    hero: str = ""
    ign: str = ""


def match_from_summary(d: dict[str, Any]) -> MatchInfo:
    """FixLag `summary_dict` payload -> MatchInfo for the local player."""
    local_uid = d.get("local_uid")
    me: dict[str, Any] = {}
    for p in d.get("players") or []:
        if local_uid is not None and p.get("uid") == local_uid:
            me = p
            break
    party = d.get("local_party_size")
    return MatchInfo(
        match_id=str(d.get("match_id", "")),
        phase=str(d.get("phase") or "IDLE").upper(),
        mode=str(d.get("mode_label") or ""),
        is_custom=d.get("pvp_type") == 6,
        party_size=party if isinstance(party, int) and party > 0 else None,
        hero=str(me.get("hero_name") or ""),
        ign=str(me.get("name") or ""),
    )


class MatchFeed:
    """Keeps the latest match summaries and viewer status. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._matches: dict[str, dict[str, Any]] = {}
        self._status: dict[str, Any] = {}
        self._status_at: float | None = None

    def handle(self, event: str, data: dict[str, Any], now: float) -> None:
        with self._lock:
            if event == "snapshot":
                for m in data.get("matches") or []:
                    self._matches[str(m.get("match_id"))] = m
                self._set_status(data.get("status"), now)
            elif event in ("match_new", "match_update") and "match_id" in data:
                self._matches[str(data["match_id"])] = data
            elif event == "status":
                self._set_status(data, now)
            elif event == "source_reset":
                self._matches.clear()
                self._set_status(data.get("status"), now)

    def _set_status(self, status: Any, now: float) -> None:
        if isinstance(status, dict):
            self._status = status
            self._status_at = now

    def current(self, now: float, stale_after: float = 10.0) -> tuple[MatchInfo | None, float | None]:
        """Active match and seconds since the last match packet. (None, None) if the viewer is gone."""
        with self._lock:
            if self._status_at is None or now - self._status_at > stale_after:
                return None, None
            age = self._status.get("last_pkt_age_s")
            mid = self._status.get("active_match_id")
            m = self._matches.get(str(mid)) if mid else None
            if m is None:
                return None, age
            info = match_from_summary(m)
            # The status line carries the freshest phase.
            phase = str(self._status.get("phase") or info.phase).upper()
            if phase != info.phase:
                info = MatchInfo(**{**info.__dict__, "phase": phase})
            return info, age


def iter_sse(lines):
    """Yield (event, data_dict) from an iterable of SSE text lines."""
    event, data = "message", []
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line:
            if data:
                try:
                    yield event, json.loads("\n".join(data))
                except json.JSONDecodeError:
                    pass
            event, data = "message", []
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())


def run_feed(url: str, feed: MatchFeed, stop: threading.Event) -> None:
    """Read the SSE stream until `stop`, reconnecting with a back-off."""
    delay = 2.0
    while not stop.is_set():
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                ctype = resp.headers.get("Content-Type", "")
                if "text/event-stream" not in ctype:
                    raise ValueError(f"not the chat viewer ({ctype or 'no content type'}) at {url}")
                delay = 2.0
                log.info("chat viewer connected: %s", url)
                lines = (b.decode("utf-8", "replace") for b in resp)
                for event, data in iter_sse(lines):
                    feed.handle(event, data, time.time())
                    if stop.is_set():
                        return
        except Exception as exc:  # network errors, viewer not started
            log.debug("chat viewer not reachable: %s", exc)
        stop.wait(delay)
        delay = min(delay * 2, 30.0)
