"""Mapper: GameState -> Discord presence fields. Pure function (PLAN.md §5.1).

Card order (user rule): IGN and level first, then hero, mode and phase.
"""
from __future__ import annotations

from typing import Any

from .config import Config
from .state import AFTER, BATTLE, CLOSED, DRAFT, IDLE, LOADING, LOBBY, GameState

PHASE_TEXT = {
    IDLE: "Idle",
    LOBBY: "In lobby",
    DRAFT: "Draft pick",
    LOADING: "Loading",
    BATTLE: "In match",
    AFTER: "Match ended",
}

BADGE_TEXT = {
    1: "Solo queue",
    2: "Duo queue (2 of 5)",
    3: "Trio queue (3 of 5)",
    4: "4-queue (4 of 5)",
    5: "Full 5-queue (5 of 5)",
}

GAME_NAME = "Mobile Legends: Bang Bang"


def _clip(text: str) -> str | None:
    """Discord wants 2..128 characters, or the field left out."""
    text = text.strip()
    if len(text) < 2:
        return None
    return text if len(text) <= 128 else text[:127] + "…"


def to_presence(s: GameState, cfg: Config) -> dict[str, Any] | None:
    """None means: clear the presence."""
    if s.phase == CLOSED:
        return None

    ign = s.ign or cfg.ign
    level = f"Lv. {cfg.level}" if cfg.level else ""
    details = " · ".join(x for x in (ign, level) if x) or GAME_NAME

    in_match = s.phase in (DRAFT, LOADING, BATTLE, AFTER)
    with_mode = in_match or s.phase == LOBBY  # the lobby room also knows mode and party
    parts = []
    if in_match and s.hero:
        parts.append(s.hero)
    if with_mode and s.mode:
        parts.append(s.mode)
    parts.append(PHASE_TEXT.get(s.phase, ""))
    state = " · ".join(p for p in parts if p)

    out: dict[str, Any] = {
        "details": _clip(details),
        "state": _clip(state),
        "large_image": cfg.large_image,
        "large_text": f"Playing as {s.hero}" if (s.phase == BATTLE and s.hero) else GAME_NAME,
    }

    start = s.session_start
    if cfg.match_timer and s.phase == BATTLE and s.match_start:
        start = s.match_start
    if start:
        out["start"] = int(start)

    size = s.party_size
    if with_mode and not s.is_custom and size in BADGE_TEXT:
        out["party_size"] = [size, 5]
        out["small_image"] = f"{cfg.badge_prefix}{size}"
        out["small_text"] = BADGE_TEXT[size]

    if cfg.live and cfg.watch_url.startswith("https://"):
        out["buttons"] = [{"label": "Watch my stream", "url": cfg.watch_url}]

    return {k: v for k, v in out.items() if v is not None}
