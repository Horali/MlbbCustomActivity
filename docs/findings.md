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

## Live link research (2026-11-28, from the game files)
- Source: `files/dragon2017/assets/android/lua/logic.unity3d` (Lua 5.1 bytecode, strings readable).
- App link hosts: `https://applink.mobilelegends.com/`, `applink.legend5v5.com`, `applink.moba5v5.com`, `https://play.mobilelegends.com/landing`. Routes seen: `/whatsapp`, `/TwitchOAuth/`. No `/live` or room route.
- An in-app live room is joined by `roomUserId` (streamer uid) + `serverId`: `CmdId_Live_JoinLiveRoom_CS m_RoomUserId=%s m_ServerId=%s`.
- Share links come from a server short-link service (`{"code":0,"data":{"short_url":...}}`, `GetShareDeepLink`, `ConvertLongShareUrlToShortShareUrl`). The live share template is not in the scripts.
- Team match room links do have a format: `?role_id=…&server_id=…&room_id=…&pvp_type=…` (`TouchTouchShare`). Not for Live.
- Result: we cannot build the live link ourselves. Tap Share in a Live once and copy the short link, then test it (PLAN.md §6.2).

## Profile from the phone
- `shared_prefs/com.mobile.legends.v2.playerprefs.xml`: `OfflineRoleName` = IGN, `OfflineRoleLevel` = level (113 on 2026-11-28). Role id 30028189, zone 2041. The bridge reads these over root adb.
- 2026-11-28 screenshot: the in-game Live is "My Channel" (Live Stream On/Off, Fans, Popularity, chat). It has no Share button. Viewers find the channel inside MLBB (Live list, profile, friends). So a Discord button can open MLBB, but not this exact channel.
- 2026-11-28 second script search: no app link opens a live room or a profile. Live join and profile open use internal server commands only (`Cmd_Live_JoinLiveRoom_CS` ulUid+uiZoneId, `Cmd_Role_GetBaseInfo_CS`). Team invites (`mobilelegends://appinvites/hago/TeamMatch/<payload>`) use an encrypted payload made in C#. Discord "Ask to Join" also cannot work, because MLBB on the viewer's phone does not talk to Discord. Decision left: Watch button = open MLBB + show the game ID, or no button.
