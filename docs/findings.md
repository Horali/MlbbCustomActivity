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
- 2026-11-28 viewer side (another streamer's channel): the channel page has Follow and Watch, no Share. The watch screen has exit, full screen, shop, heart, gift, ranking, VIP and a chat toggle, no Share. Viewers reach a channel only inside MLBB.

## Lobby room messages (TCP 30101), 2026-11-28
- Source: a passive capture (`tcpdump "tcp port 30101"`) while the user opened Classic, Ranked and Brawl rooms and two friends joined and left. Names of the room messages come from `FixLag/data/01_dump.cs` (`CmdId_Room_*`, `MTTDProto.RoomInfo`); the numbers come from the capture.
- Frames: flag `0x00` raw or `0x10` Zstd, then a 3-byte big-endian total length. Body: struct `{v0 mid, v2 result, b6 body}` (server to client).
- `RoomInfo` tags = declaration order minus 1: `v0` room id, `v1` `uiPVPType` (1 Classic, 2 Ranked, 4 Brawl, 6 Custom), `v2` `uiRankLevelBig`, `l3` `vecPlayers`, `v6` `uiMapID`. Each player: `v0` role id, `b3` name, `b80` client IP (private: the bridge keeps only the count).
- Message ids (server to client): `11201` create reply (only you in `l3`), `11203` and `20103` a player joined, `11213` room info changed, `11205` a player left (`b6.s1` = who left, `b6.s2` = room after), `11241` keepalive every 5 s `{v0 room id, v1 pvp type}`. Client asks: `11200` create, `11204` leave, `11206` invite.
- `11733` is the public room list (other rooms): not my room. `10208` stays undecoded (account data).
- Arcade modes use big pvp types: 3030 = Card Brawl (the room's map id is 3030 too). The card shows "Arcade" for other pvp types of 1000 or more.
- Limit: a bridge started inside a room gets only keepalives (mode, no player list). It reuses the size saved in `.lobby_room.json`; if a friend joined while the bridge was off, it shows solo until the room changes. The room id stays the same when you change the mode.
- Result: `mlbb_presence/lobby.py` runs its own `tcpdump "tcp src port 30101"` and the card shows "Ranked · In lobby" with the party badge. Checked live: "Brawl · In lobby".
- Queue (2026-11-28): `19010` push `v8` 1 = in queue, 2 = off, 3 = you cancelled, 4 = ready check failed (with `v9` match id); `20423` match found (`v2` match id); `20008` battle server info; `20135` ready check failed; `20103` team back in the room. Client: `19001` start queue, `19005` cancel.
