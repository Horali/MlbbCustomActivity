# MlbbCustomActivity — Project Handoff

## Summary
A Discord Rich Presence card for MLBB played on the phone: game, timer, mode, party size badge (Solo…5Q), and a "Watch my stream" button that opens MLBB on the viewer's phone.

## Current state
- Plan only, no code. Read [PLAN.md](PLAN.md) first.
- Recommended first build: Option A, a Python PC bridge that reads the FixLag chat viewer SSE stream plus `adb shell ps`, and sends presence to Discord desktop over IPC.
- Mode and party size are known from draft pick (FixLag decodes them). Lobby party size needs research (TCP 30101).
- The live room link format is unknown. Phase 0 tests it (PLAN.md §6.2).

## Active tasks
- [handoffs/discord-presence.md](handoffs/discord-presence.md) — waiting for answers to PLAN.md §11, then Phase 0.

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
