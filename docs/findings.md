# Phase 0 findings

Write yes / no and one line of notes for each test. See PLAN.md §8 Phase 0.

## Steps
1-3. Done: the app "Mobile Legends Bang Bang" exists, the ID is in `.env`, assets are uploaded.
4. Open Discord desktop. Run `pip install pypresence`, then `python tools/phase0_presence.py`.
5. Look at your profile from a second account (PC and phone).
6. Stop the script. Run `python tools/phase0_presence.py --scheme`.
7. In MLBB, start a Live. Tap Share, copy the link, and paste it below.

## Results
| Test | Result | Notes |
|---|---|---|
| Card shows "Playing Mobile Legends Bang Bang" | yes | Discord rejects ":" in app names (2026-11-27) |
| Details, state, "(3 of 5)" and timer show | yes | "naradira · Lv. 86" / "Fanny · Ranked · Draft pick" |
| Badge shows with hover text | yes | `squadog_3` (game party icon), large `mlbb_logo` |
| Buttons show on PC (second account) | | |
| Buttons show on Discord mobile | | |
| `https://applink.mobilelegends.com/` button opens MLBB on Android | | |
| `mobilelegends://` button is accepted | | expect no |
| Live share link | | paste here |
| Live link opens the live room (`adb shell am start -a android.intent.action.VIEW -d "<link>"`) | | |
| Chat viewer shows mode + party (Ranked, Classic, Brawl) | | |
