# Phase 0 findings

Write yes / no and one line of notes for each test. See PLAN.md §8 Phase 0.

## You do these steps
1. Open https://discord.com/developers/applications. Make a new app named "Mobile Legends: Bang Bang".
2. Copy the Application ID. Copy `.env.example` to `.env`. Paste the ID.
3. Upload two test images in Rich Presence → Art Assets: key `mlbb` and key `party_3`.
4. Open Discord desktop. Run `pip install pypresence`, then `python tools/phase0_presence.py`.
5. Look at your profile from a second account (PC and phone).
6. Stop the script. Run `python tools/phase0_presence.py --scheme`.
7. In MLBB, start a Live. Tap Share, copy the link, and paste it below.

## Results
| Test | Result | Notes |
|---|---|---|
| Card shows "Playing Mobile Legends: Bang Bang" | | |
| Details, state, "(3 of 5)" and timer show | | |
| Badge shows with hover text | | |
| Buttons show on PC (second account) | | |
| Buttons show on Discord mobile | | |
| `https://applink.mobilelegends.com/` button opens MLBB on Android | | |
| `mobilelegends://` button is accepted | | expect no |
| Live share link | | paste here |
| Live link opens the live room (`adb shell am start -a android.intent.action.VIEW -d "<link>"`) | | |
| Chat viewer shows mode + party (Ranked, Classic, Brawl) | | |
