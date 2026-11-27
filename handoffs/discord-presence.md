Status: active
Needs user: MLBB Live share link (PLAN.md §6.2) and answers to PLAN.md §11
Updated: 2026-11-28 04:40
Agent: Claude desktop app (Code tab), Opus 5.5, Phase 1 session

## Goal and why
Show a Discord Rich Presence card while the user plays MLBB on the phone (SM-S936B). Order on the card: IGN and level first, then hero, mode, phase, party badge, timer. Later a Watch button to the user's MLBB live room.

## Current state
- Phase 0 done. Discord app "Mobile Legends Bang Bang" (ID in `.env`). `tools/phase0_presence.py` sends a fixed card. The user saw it on their profile.
- Assets: large `mlbb_logo` (official Miya icon), badges `squadog_1..5` (built from the game's party icons). Game art is local only (`.gitignore`).
- Phase 1 bridge built and pushed: `mlbb_presence/` (19 tests pass). Not yet run against a live match with Discord.
- Checked on a FixLag pcap replay (`draft_LIVE6.pcap`): the feed gives IGN `naradira`, Ranked, 5-stack, hero Nolan.
- Dry run on the phone (wireless, 2 adb entries): auto serial pick works; MLBB closed -> `CLOSED`.
- FixLag `players[]` has `name`, `hero_name`, `party_size`, but no level. The IGN comes from `players[local_uid].name`, else `.env`. Level stays from `.env`.
- Watch button: off unless `LIVE=1` and `WATCH_URL` is https.

## Next steps
1. Live test evening: in FixLag run `python -m tools.chat_viewer --adb <serial>`. Here run `python -m mlbb_presence` (`--dry-run -v` prints instead of sending). Check mode, badge, hero, timer from a second account.
2. Tune `BATTLE_SILENCE` (20 s) in `state.py` if "Match ended" shows too early or late.
3. Fill the open rows in `docs/findings.md` (buttons on mobile, scheme button, Competing).
4. Ask the user for the MLBB Live share link to test the Watch button (PLAN.md §6.2).
5. Phase 2 (PLAN.md §8): "I am live" switch, tray menu.

## Open problems
- Live room share link format: unknown.
- Lobby party size before draft: needs TCP 30101 research.
- No match-end event in FixLag: the bridge uses a 20 s silence timeout after Battle.
- Level is not decoded anywhere. Placeholder 86 in `.env`.

## Decisions and lessons (keep)
- Option A (PC bridge, Python, reuse FixLag) first; Option B (Android app) later.
- Rejected: memory reads (ban risk), user-token presence (Discord ToS), OCR (fragile).
- Discord buttons: max 2, https only in practice, invisible to self. App names cannot contain ":".
- Thin 3-person art reads as "duo" at small size. Use the game's own icons.
- Badge icons: `Atlas_Clearing.unity3d` (texture `Atlas_Clearing_main` + `_mask`). Crops in the 1024 atlas: solo (770,385,800,425), duo (855,333,882,362), 4Q (725,345,770,378), 5Q (604,703,657,736). Trio = 5Q columns 8..32.
- Official icon: `base.apk` `res/mipmap-xxxhdpi-v4/ic_launcher_background.png`, alpha bbox (42,42,391,391), upscaled to 1024.
- Git Bash rewrites `/sdcard/...`: set `MSYS_NO_PATHCONV=1`.

## Where to look
- PLAN.md (§5.1 states, §6 Watch button, §8 phases), `docs/findings.md`.
- `mlbb_presence/`: `game.py` (adb ps), `match.py` (SSE), `state.py`, `mapper.py`, `sender.py`, `__main__.py`. Tests in `tests/`.
- FixLag `tools/chat_viewer/session.py` (`summary_dict`), `server.py` (`/events`, port 8765).
