Status: active
Needs user: restart the bridge, then check the card in a Ranked room with a friend
Updated: 2026-11-28 05:05
Agent: Claude desktop app (Code tab), Opus 5.5, lobby-state side session

## Goal and why
Show the lobby mode and party size on the Discord card before draft pick, e.g. "Ranked · In lobby" with the `squadog_2` badge.

## Current state
- Done and pushed: `mlbb_presence/lobby.py` (own tcpdump on TCP 30101, Zstd, room tracker), LOBBY phase uses it in `state.py` and `mapper.py`. Tests in `tests/test_lobby.py`. New dependency `zstandard`.
- Message map in `docs/findings.md` "Lobby room messages".
- Dry run on the phone showed "Brawl · In lobby". The real bridge (`python -m mlbb_presence -v`) still ran the old code at 05:00; it needs a restart.

## Next steps
1. Restart the bridge: `python -m mlbb_presence -v` (`--no-lobby` turns the lobby capture off).
2. Open a Ranked room, invite a friend, check the card shows "Ranked · In lobby" and the duo badge.
3. Then remove this task (move lessons to HANDOFF.md) and delete this file.

## Open problems
- Bridge started while already in a room: mode known, party size unknown until someone joins or leaves.
- Joining a friend's room: the decoder learns your role id only from a room you create; it then relies on the 15 s keepalive silence to see that you left.

## Decisions and lessons (keep)
- The capture lives in this repo, not in FixLag: FixLag's chat viewer only reads UDP, and a second tcpdump is simpler than a FixLag change.
- The dump has message names but no numbers; match numbers by doing lobby actions while you capture.

## Where to look
- `mlbb_presence/lobby.py`, `docs/findings.md`, FixLag `tools/lag_mapper/tcp_lobby.py` (older lobby decoder).
