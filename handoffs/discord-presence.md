Status: active
Needs user: one play session for the live test
Updated: 2026-11-28 13:05
Agent: Claude desktop app (Code tab), Opus 5.5, Phase 1 session

## Goal and why
Show a Discord Rich Presence card while the user plays MLBB on the phone (SM-S936B). Order on the card: IGN and level first, then hero, mode, phase, party badge, timer. The Watch button is parked (see Decisions).

## Current state
- Phase 0 done. Discord app "Mobile Legends Bang Bang" (ID in `.env`). `tools/phase0_presence.py` sends a fixed card. The user saw it on their profile.
- App icon and large image = `mlbb_icon` (2026-11-28): the launcher icon center crop (72 of 108 dp) of the game icon, so no "FUN TOGETHER" ring. Old `mlbb_logo` kept unused. Assets, badges `squadog_1..5` (built from the game's party icons). Game art is local only (`.gitignore`).
- Phase 1 bridge built and pushed: `mlbb_presence/` (20 tests pass). Not yet run against a live match with Discord.
- Checked on a FixLag pcap replay (`draft_LIVE6.pcap`): the feed gives IGN `naradira`, Ranked, 5-stack, hero Nolan.
- Dry run on the phone (wireless, 2 adb entries): auto serial pick works; MLBB closed -> `CLOSED`.
- FixLag `players[]` has `name`, `hero_name`, `party_size`, but no level. IGN and level come from the game prefs over root adb (`OfflineRoleName`, `OfflineRoleLevel` = 113); FixLag's name wins in a match; `.env` is the fallback.
- Idle: after `AFK_SECONDS` (300 s) with no touch (`dumpsys power` lastUserActivityTime) the card says Idle. The phone screen-off timeout is never, so MLBB stays on screen.
- Serial change (USB unplugged): `Services.update` moves the lobby capture and restarts the chat viewer on the new serial.
- Watch button: off unless `LIVE=1` and `WATCH_URL` is https.

## Next steps
1. Live test evening: in FixLag run `python -m tools.chat_viewer --adb <serial> --port 8790` (ClipMaker holds 8765/8766). Here run `python -m mlbb_presence` (`--dry-run -v` prints instead of sending). Check mode, badge, hero, timer from a second account.
2. Tune `BATTLE_SILENCE` (20 s) in `state.py` if "Match ended" shows too early or late.
3. Test Competing / `status_display_type` and fill that row in `docs/findings.md`.
4. Phase 2 (PLAN.md §8): "I am live" switch, tray menu.

## Open problems
- Lobby party size before draft: needs TCP 30101 research.
- No match-end event in FixLag: the bridge uses a 20 s silence timeout after Battle.
- Unrooted phones: no level from prefs and no FixLag capture (tcpdump needs root). Possible fix: PCAPdroid (untested).

## Decisions and lessons (keep)
- Option A (PC bridge, Python, reuse FixLag) first; Option B (Android app) later.
- Rejected: memory reads (ban risk), user-token presence (Discord ToS), OCR (fragile).
- Discord buttons: max 2, https only in practice, invisible to self. App names cannot contain ":".
- Thin 3-person art reads as "duo" at small size. Use the game's own icons.
- Badge icons: `Atlas_Clearing.unity3d` (texture `Atlas_Clearing_main` + `_mask`). Crops in the 1024 atlas: solo (770,385,800,425), duo (855,333,882,362), 4Q (725,345,770,378), 5Q (604,703,657,736). Trio = 5Q columns 8..32.
- Official icon: `base.apk` `res/mipmap-xxxhdpi-v4/ic_launcher_background.png`, alpha bbox (42,42,391,391), upscaled to 1024.
- Watch button PARKED by the user (2026-11-28). No link opens a Live channel or profile: My Channel and the viewer side have no Share button, and the scripts have no route (docs/findings.md). If revived: button `https://applink.mobilelegends.com/` with label "Watch in MLBB · ID 30028189" (viewer types the ID), or a small GitHub Pages helper that copies the ID and opens MLBB.
- Use Haiku subagents for adb calls and big file reads (user rule).
- Git Bash rewrites `/sdcard/...`: set `MSYS_NO_PATHCONV=1`.

## Where to look
- PLAN.md (§5.1 states, §6 Watch button, §8 phases), `docs/findings.md`.
- `mlbb_presence/`: `game.py` (adb ps), `match.py` (SSE), `state.py`, `mapper.py`, `sender.py`, `__main__.py`. Tests in `tests/`.
- FixLag `tools/chat_viewer/session.py` (`summary_dict`), `server.py` (`/events`, port 8765).
