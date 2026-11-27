import struct

import pytest

from mlbb_presence import state as S
from mlbb_presence.config import Config
from mlbb_presence.game import GameInfo
from mlbb_presence.lobby import LobbyDecoder, LobbyInfo, LobbyTracker, frames_for_test, parse_message
from mlbb_presence.mapper import to_presence
from mlbb_presence.state import StateMachine

ME, FRIEND, FRIEND2 = 30028189, 1142211746, 555000111
ROOM = 538147302981

# ---- tiny encoder for the MLBB TLV format ----


def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def struct_body(fields: list[tuple[int, object]]) -> bytes:
    out = bytearray()
    for fnum, val in fields:
        if isinstance(val, int):
            out += bytes([0x00 | fnum]) + varint(val)
        elif isinstance(val, bytes):
            out += bytes([0x40 | fnum]) + varint(len(val)) + val
        elif isinstance(val, list):  # list of structs
            out += bytes([0x50 | fnum]) + varint(len(val))
            for item in val:
                out += b"\x70" + struct_body(item) + b"\x80"
        elif isinstance(val, tuple):  # nested struct
            out += bytes([0x70 | fnum]) + struct_body(list(val)) + b"\x80"
    return bytes(out)


def player(uid: int) -> list[tuple[int, object]]:
    # name and client IP are in the real message; the decoder must ignore them
    return [(0, uid), (3, b"someone"), (13, 1)]


def room(pvp: int, uids: list[int], room_id: int = ROOM) -> tuple:
    return ((0, room_id), (1, pvp), (2, 7), (3, [player(u) for u in uids]), (6, 202))


def message(mid: int, body: list[tuple[int, object]]) -> bytes:
    inner = b"\x70" + struct_body(body) + b"\x80"
    return b"\x70" + struct_body([(0, mid), (2, 1), (6, inner)])


def feed(tracker: LobbyTracker, mid: int, body: list[tuple[int, object]], now: float) -> None:
    parsed = parse_message(message(mid, body))
    assert parsed is not None
    tracker.on_message(*parsed, now)


# ---- parser and tracker ----

def test_parse_message_skips_private_and_unknown_mids():
    assert parse_message(message(10208, [(0, 1)])) is None
    assert parse_message(message(10115, [(0, 1)])) is None
    mid, body = parse_message(message(11241, [(0, ROOM), (1, 2)]))
    assert mid == 11241 and body[("v", 0)] == ROOM


def test_party_grows_and_shrinks_and_leave_clears():
    t = LobbyTracker()
    feed(t, 11201, [(0, ROOM), (1, room(2, [ME]))], 0)          # create Ranked room
    assert t.current(1) == LobbyInfo(ROOM, 2, 1)
    assert t.current(1).mode == "Ranked"
    feed(t, 11203, [(2, room(2, [ME, FRIEND]))], 2)             # friend joins
    feed(t, 20103, [(0, room(2, [ME, FRIEND, FRIEND2]))], 3)    # second friend
    assert t.current(4).party_size == 3
    feed(t, 11205, [(1, ((0, FRIEND2),)), (2, room(2, [ME, FRIEND]))], 5)  # friend leaves
    assert t.current(6).party_size == 2
    feed(t, 11205, [(1, ((0, ME),)), (2, room(2, [FRIEND]))], 7)  # I leave
    assert t.current(8) is None


def test_keepalive_keeps_room_and_silence_ends_it():
    t = LobbyTracker()
    feed(t, 11201, [(1, room(4, [ME]))], 0)
    for now in (5, 10, 15, 20):
        feed(t, 11241, [(0, ROOM), (1, 4)], now)
    assert t.current(30) == LobbyInfo(ROOM, 4, 1)
    assert t.current(36) is None  # no packet for more than 15 s


def test_keepalive_of_new_room_drops_old_party_size():
    t = LobbyTracker()
    feed(t, 11203, [(2, room(2, [ME, FRIEND]))], 0)
    feed(t, 11241, [(0, ROOM + 1), (1, 1)], 1)
    assert t.current(2) == LobbyInfo(ROOM + 1, 1, 1)  # unknown count shows solo


def test_room_list_is_not_my_room():
    t = LobbyTracker()
    # mid 11733 is the public room list; it is not decoded at all
    assert parse_message(message(11733, [(0, [list(room(4, [FRIEND]))])])) is None
    assert t.current(0) is None


# ---- pcap -> tracker ----

def pcap(segments: list[tuple[int, bytes]]) -> bytes:
    out = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 276)
    for seq, data in segments:
        tcp = struct.pack("!HHIIBBHHH", 30101, 40000, seq, 0, 5 << 4, 0x18, 65535, 0, 0) + data
        ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(tcp), 0, 0, 64, 6, 0,
                         bytes([161, 202, 213, 215]), bytes([10, 0, 0, 2])) + tcp
        sll2 = struct.pack("!HHIHBB8s", 0x0800, 0, 1, 1, 0, 6, b"\0" * 8)
        rec = sll2 + ip
        out += struct.pack("<IIII", 0, 0, len(rec), len(rec)) + rec
    return out


def test_decoder_reads_pcap_with_out_of_order_segments():
    t = LobbyTracker()
    stream = frames_for_test([message(11201, [(1, room(2, [ME]))]),
                              message(11203, [(2, room(2, [ME, FRIEND]))])])
    cut = len(stream) // 2
    data = pcap([(1000, stream[:cut]), (1000 + cut, stream[cut:])])
    d = LobbyDecoder(t)
    d.feed(data, 0)
    assert t.current(1) == LobbyInfo(ROOM, 2, 2)

    t2 = LobbyTracker()
    a, b = cut // 2, cut  # three segments; the last two arrive swapped
    swapped = pcap([(1000, stream[:a]), (1000 + b, stream[b:]), (1000 + a, stream[a:b])])
    LobbyDecoder(t2).feed(swapped, 0)
    assert t2.current(1) == LobbyInfo(ROOM, 2, 2)


def test_decoder_reads_zstd_frames():
    zstandard = pytest.importorskip("zstandard")
    msg = message(11201, [(1, room(1, [ME]))])
    comp = zstandard.ZstdCompressor().compress(msg)
    frame = b"\x10" + (len(comp) + 4).to_bytes(3, "big") + comp
    t = LobbyTracker()
    LobbyDecoder(t).feed(pcap([(5, frame)]), 0)
    assert t.current(0) == LobbyInfo(ROOM, 1, 1)


# ---- state machine and card ----

CFG = Config(app_id="1", ign="naradira", level="113")
ON = GameInfo(running=True, foreground=True, started_at=1000.0)


def test_lobby_room_shows_mode_and_party_badge():
    m = StateMachine()
    s = m.update(ON, None, None, 2000.0, LobbyInfo(ROOM, 2, 2))
    p = to_presence(s, CFG)
    assert p["state"] == "Ranked · In lobby (2 of 5)"
    assert "party_size" not in p and p["state"].endswith("(2 of 5)")
    assert p["small_image"] == "squadog_2"
    assert p["small_text"] == "Duo queue (2 of 5)"


def test_lobby_without_room_is_plain():
    s = StateMachine().update(ON, None, None, 2000.0, None)
    p = to_presence(s, CFG)
    assert p["state"] == "In lobby" and "small_image" not in p


def test_custom_room_in_lobby_has_no_badge():
    s = StateMachine().update(ON, None, None, 2000.0, LobbyInfo(ROOM, 6, 3))
    p = to_presence(s, CFG)
    assert p["state"] == "Custom · In lobby" and "small_image" not in p


def test_background_hides_lobby_room():
    bg = GameInfo(running=True, foreground=False, started_at=1000.0)
    s = StateMachine().update(bg, None, None, 2000.0, LobbyInfo(ROOM, 2, 2))
    assert s.phase == S.IDLE and s.mode == "" and s.party_size is None


def test_badge_icon_switch_keeps_party_text():
    from dataclasses import replace
    s = StateMachine().update(ON, None, None, 2000.0, LobbyInfo(ROOM, 2, 1))
    p = to_presence(s, replace(CFG, badge_icon=False))
    assert "party_size" not in p and p["state"].endswith("(1 of 5)")
    assert "small_image" not in p and "small_text" not in p


def test_restart_inside_room_reuses_saved_party_size(tmp_path):
    mem = tmp_path / "room.json"
    t = LobbyTracker(memory=mem)
    feed(t, 11201, [(1, room(2, [ME]))], 0)
    feed(t, 11203, [(2, room(2, [ME, FRIEND]))], 1)
    t2 = LobbyTracker(memory=mem)  # bridge restarted; only keepalives arrive now
    feed(t2, 11241, [(0, ROOM), (1, 2)], 10)
    assert t2.current(11) == LobbyInfo(ROOM, 2, 2)
    assert t2.self_uid == ME
    feed(t2, 11241, [(0, ROOM + 5), (1, 2)], 12)  # another room: no saved size
    assert t2.current(13).party_size == 1


def test_arcade_mode_labels():
    assert LobbyInfo(ROOM, 3030, 2).mode == "Card Brawl"
    assert LobbyInfo(ROOM, 4123, 1).mode == "Arcade"
    assert LobbyInfo(ROOM, 99, 1).mode == ""


def test_draft_without_mode_uses_lobby_room():
    from mlbb_presence.match import MatchInfo
    m = StateMachine()
    m.update(ON, None, None, 2000.0, LobbyInfo(ROOM, 3030, 3))
    s = m.update(ON, MatchInfo("x", S.DRAFT), 1.0, 2010.0, None)
    assert s.phase == S.DRAFT and s.mode == "Card Brawl" and s.party_size == 3
    s = m.update(ON, MatchInfo("x", S.DRAFT, mode="Ranked", party_size=2), 1.0, 2011.0, None)
    assert s.mode == "Ranked" and s.party_size == 2  # FixLag wins when it knows the mode


def test_draft_text_only_for_draft_modes():
    from mlbb_presence.state import GameState
    p = to_presence(GameState(S.DRAFT, mode="Card Brawl", party_size=3), CFG)
    assert p["state"] == "Card Brawl · Hero selection (3 of 5)"
    p = to_presence(GameState(S.DRAFT, mode="Ranked", party_size=2), CFG)
    assert p["state"] == "Ranked · Draft pick (2 of 5)"


def test_fixlag_mode_number_gets_a_name():
    from mlbb_presence.match import MatchInfo
    s = StateMachine().update(ON, MatchInfo("y", S.BATTLE, mode="Mode 3030", hero="Layla"), 1.0, 2000.0)
    assert s.mode == "Card Brawl"
