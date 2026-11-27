Status: waiting
Needs user: run the Phase 0 steps in docs/findings.md and fill in the results
Updated: 2026-11-27 21:40
Agent: Claude desktop app (Code tab), Opus 5.5, first session

## Goal and why
Show a Discord Rich Presence card while the user plays MLBB on the phone (SM-S936B): game, timer, mode, party size badge, Watch button to the user's MLBB live room.

## Current state
- PLAN.md written. No code.
- Verified 2026-11-27: MLBB 2.2.23.12351 handles `mobilelegends://`, `mlbb://onpageresponse`, and verified app links `https://applink.mobilelegends.com/*` and `https://play.mobilelegends.com/landing/`.
- `dump.cs` has `DeeplinkManager` (OpenTeamJoin, OpenTeamMatch, HandleAppLinkLua) and Live code (`TryOpenLiveStreamView`, `SendLiveShareRewardCS`). Link paths are in Lua, not in dump.cs.

## Next steps
1. Get the user's answers to PLAN.md §11.
2. Run Phase 0 (PLAN.md §8): Discord app, test script, button tests, live link test, chat viewer check.
3. Write results to `docs/findings.md`.
4. Start Phase 1 (MVP bridge).

## Open problems
- Live room share link format: unknown until the user shares it from MLBB.
- Lobby party size before draft: needs TCP 30101 research.
- No match-end or win/loss event in FixLag yet.

## Decisions and lessons (keep)
- Option A (PC bridge, Python, reuse FixLag) first; Option B (Android app + Discord Social SDK 1.10+) later.
- Rejected: memory reads (ban risk), user-token presence (Discord ToS), OCR (fragile).
- Discord buttons: max 2, https only in practice, invisible to self.

## Where to look
- PLAN.md, FixLag `tools/chat_viewer/session.py` (`format_mode_label`, `_format_party_label`, `summary_dict`).
