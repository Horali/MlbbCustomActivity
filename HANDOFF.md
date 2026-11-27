# MlbbCustomActivity — Project Handoff

## Summary
A Discord Rich Presence card for MLBB played on the phone: game, timer, mode, party size badge (Solo…5Q), and a "Watch my stream" button that opens MLBB on the viewer's phone.

## Current state
- Phase 0 done: the Discord app exists and `tools/phase0_presence.py` shows a test card (IGN, level, hero, game party badge, official icon).
- Phase 1 bridge built: `mlbb_presence/` (`python -m mlbb_presence`). It reads `adb shell ps` and the FixLag chat viewer SSE `/events`, and sends presence over Discord IPC.
- Lobby room: mode and party size come from TCP 30101 (`mlbb_presence/lobby.py`, own tcpdump; message map in `docs/findings.md`). The party size is saved in `.lobby_room.json` for restarts. Party: Discord's people icon and "(n of 5)" come from `party_size` (the timer then shares the state line; user choice 2026-11-28). The corner badge is off (`BADGE_ICON=1`). The Discord app keeps the old SOLO..5Q `party_1..5` images; the dark people icons from `tools/make_party_icons.py` were removed again.
- Mode, hero and party size are known from draft pick. Level is not decoded (fixed in `.env`).
- The live room link format is unknown (PLAN.md §6.2).

- Autostart: `tools/install_autostart.ps1` puts a hidden start script in the Windows Startup folder (log `%LOCALAPPDATA%\mlbb_presence/bridge.log`). While MLBB runs, the bridge starts the lobby capture and, with `FIXLAG_DIR` in `.env`, the FixLag chat viewer; it stops both when MLBB closes.

## Active tasks
- [handoffs/discord-presence.md](handoffs/discord-presence.md) — Phase 1 bridge built; needs a live test evening and the Live share link.

## Where to look
- Plan: [PLAN.md](PLAN.md)
- Data source project: `C:\Users\child\PROJECTS\FixLag` (read its `HANDOFF.md` and `docs/handoff.md` §3 for root and ADB).
- MLBB class map: `C:\Users\child\PROJECTS\FixLag\data\01_dump.cs` (90 MB, not in git).

## Rules and conventions
- Passive capture only. Never touch game memory (no Frida, no mods). Never use a Discord user token.
- Always pass `-s <serial>` to `adb`. Check `adb devices -l` first; the wireless port changes.
- Keep the Discord Application ID and any webhook URL in `.env`, never in git.
- Do not edit FixLag from this repo without a pointer line in the FixLag "Active tasks" list.
- Commits: small Conventional Commits to `main` under GitHub `Horali`; zero AI attribution.
