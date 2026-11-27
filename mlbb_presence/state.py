"""State machine: joins the game watcher and the match watcher into one GameState."""
from __future__ import annotations

from dataclasses import dataclass, field

from .game import GameInfo
from .match import MatchInfo

# Phases
CLOSED = "CLOSED"    # game not running: clear the presence
IDLE = "IDLE"        # game running in the background
LOBBY = "LOBBY"
DRAFT = "DRAFT"
LOADING = "LOADING"
BATTLE = "BATTLE"
AFTER = "AFTER"      # match ended, shown for AFTER_SECONDS

BATTLE_SILENCE = 20.0   # no match packets for this long in Battle -> match ended
PREGAME_SILENCE = 90.0  # draft or loading with no packets -> back to lobby
AFTER_SECONDS = 60.0


@dataclass(frozen=True)
class GameState:
    phase: str
    session_start: float | None = None
    match_start: float | None = None
    mode: str = ""
    is_custom: bool = False
    party_size: int | None = None
    hero: str = ""
    ign: str = ""


@dataclass
class StateMachine:
    phase: str = CLOSED
    session_start: float | None = None
    match_start: float | None = None
    after_until: float | None = None
    last_match: MatchInfo | None = None
    ended: set[str] = field(default_factory=set)

    def update(self, game: GameInfo | None, match: MatchInfo | None,
               pkt_age: float | None, now: float) -> GameState:
        # Phone not reachable: keep what we had, but never invent a running game.
        if game is None:
            if self.phase == CLOSED:
                return self._state()
            game = GameInfo(running=True, foreground=self.phase != IDLE, started_at=self.session_start)

        if not game.running:
            self.__init__()  # reset everything
            return self._state()

        if self.session_start is None:
            self.session_start = game.started_at or now

        live = (match is not None and match.match_id not in self.ended
                and match.phase in (DRAFT, LOADING, BATTLE))
        if live:
            silent = pkt_age is not None and pkt_age >= (
                BATTLE_SILENCE if match.phase == BATTLE else PREGAME_SILENCE)
            if silent:
                if match.phase == BATTLE or self.phase == BATTLE:
                    return self._end_match(match, now)
                self.ended.add(match.match_id)  # abandoned draft
                live = False

        if live:
            if match.phase == BATTLE and self.phase != BATTLE:
                self.match_start = now
            elif match.phase != BATTLE:
                self.match_start = None
            self.phase = match.phase
            self.last_match = match
            self.after_until = None
            return self._state()

        if self.phase == BATTLE and self.last_match is not None:
            return self._end_match(self.last_match, now)

        if self.phase == AFTER and self.after_until is not None and now < self.after_until:
            return self._state()

        self.after_until = None
        self.match_start = None
        self.last_match = None
        self.phase = LOBBY if game.foreground else IDLE
        return self._state()

    def _end_match(self, match: MatchInfo, now: float) -> GameState:
        self.ended.add(match.match_id)
        self.last_match = match
        self.phase = AFTER
        self.match_start = None
        self.after_until = now + AFTER_SECONDS
        return self._state()

    def _state(self) -> GameState:
        m = self.last_match if self.phase in (DRAFT, LOADING, BATTLE, AFTER) else None
        return GameState(
            phase=self.phase,
            session_start=self.session_start,
            match_start=self.match_start,
            mode=m.mode if m else "",
            is_custom=m.is_custom if m else False,
            party_size=m.party_size if m else None,
            hero=m.hero if m else "",
            ign=m.ign if m else "",
        )
