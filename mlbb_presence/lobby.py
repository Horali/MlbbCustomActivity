"""Lobby watcher: room mode and party size from the MLBB lobby connection (TCP 30101).

Passive only: `tcpdump` on the phone (root adb) copies the lobby packets. Nothing is
sent to the game. See docs/findings.md "Lobby room messages" for the message ids.

Wire format (server -> client):
  TCP stream of frames: flag (0x00 raw, 0x10 Zstd) + 3-byte big-endian total length.
  Frame body: 0x70 struct {v0: mid, v2: result, b6: body struct (0x70 ...)}.
  The room struct (MTTDProto.RoomInfo): v0 room id, v1 uiPVPType, v3 vecPlayers,
  v6 uiMapID. Only these numbers are kept; names and IPs in the player list are dropped.
"""
from __future__ import annotations

import json
import logging
import shutil
import struct
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

log = logging.getLogger(__name__)

LOBBY_PORT = 30101
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
PRIVATE_MIDS = frozenset({10208})       # account data: never decoded (FixLag rule)
ROOM_MIDS = frozenset({
    11201,  # create room reply (you are the only player)
    11203,  # someone entered the room
    11205,  # someone left the room (b6.s1 = the player who left)
    11209,  # room info reply
    11213,  # room info changed
    20103,  # room info push
})
LEAVE_MID = 11205
BACK_MID = 20103
QUEUE_MID = 19010   # queue state push: v8 1 = in queue; 2, 4 = not (cancel, match not accepted)
FOUND_MID = 20423   # a match was found: the ready check starts
FOUND_SECONDS = 45.0  # the ready check lasts about 30 s
KEEPALIVE_MID = 11241                   # every 5 s while in a room: {v0 room, v1 pvp type}
# No keepalive comes while you queue or play, or after a match, but the room stays
# (same id all session). So keep it until a leave message, game close, or this long.
ROOM_STALE_SECONDS = 1800.0

PVP_LABELS = {
    1: "Classic",
    2: "Ranked",
    3: "3v3",
    4: "Brawl",
    5: "VS AI",
    6: "Custom",
    7: "MCL",
    8: "Draft Pick",
    9: "1v1",
    13: "Mirror",
    21: "Ranked",
    22: "VS AI",
    23: "VS AI",
    3030: "Card Brawl",  # arcade mode, seen 2026-11-28
}
ARCADE_MIN_PVP = 1000  # arcade/event modes use big pvp types
CUSTOM_PVP = 6


def mode_label(pvp_type: int) -> str:
    if pvp_type in PVP_LABELS:
        return PVP_LABELS[pvp_type]
    return "Arcade" if pvp_type >= ARCADE_MIN_PVP else ""


@dataclass(frozen=True)
class LobbyInfo:
    room_id: int
    pvp_type: int
    party_size: int | None
    back_at: float | None = field(default=None, compare=False)  # last 20103: team in the room
    queue: str = field(default="", compare=False)  # "", "queue" or "found"

    @property
    def mode(self) -> str:
        return mode_label(self.pvp_type)

    @property
    def is_custom(self) -> bool:
        return self.pvp_type == CUSTOM_PVP


# ---------------------------------------------------------------- struct parser

def read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    val = shift = 0
    while pos < len(buf):
        b = buf[pos]
        pos += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, pos
        shift += 7
    raise ValueError("truncated varint")


def _item(buf: bytes, pos: int, tag: int, depth: int) -> tuple[Any, int]:
    wire = tag >> 4
    if wire <= 3:
        return read_varint(buf, pos)
    if wire == 4:
        ln, pos = read_varint(buf, pos)
        if pos + ln > len(buf):
            raise ValueError("truncated bytes")
        return bytes(buf[pos:pos + ln]), pos + ln
    if wire == 7:
        return parse_struct(buf, pos, depth - 1)
    raise ValueError(f"bad item tag {tag:#x}")


def parse_struct(buf: bytes, pos: int, depth: int = 16) -> tuple[dict[tuple[str, int], Any], int]:
    """Parse an MLBB TLV struct that starts right after its 0x70 tag."""
    if depth <= 0:
        raise ValueError("too deep")
    fields: dict[tuple[str, int], Any] = {}
    n = len(buf)
    while pos < n:
        tag = buf[pos]
        pos += 1
        if tag == 0x80:
            return fields, pos
        wire, fnum = tag >> 4, tag & 0x0F
        if fnum == 0x0F:
            fnum, pos = read_varint(buf, pos)
        if wire <= 3:
            fields[("v", fnum)], pos = read_varint(buf, pos)
        elif wire == 4:
            fields[("b", fnum)], pos = _item(buf, pos, tag, depth)
        elif wire == 5:
            cnt, pos = read_varint(buf, pos)
            items = []
            for _ in range(cnt):
                if pos >= n:
                    raise ValueError("truncated list")
                et = buf[pos]
                item, pos = _item(buf, pos + 1, et, depth)
                items.append(item)
            fields[("l", fnum)] = items
        elif wire == 6:
            cnt, pos = read_varint(buf, pos)
            for _ in range(cnt):
                for _kv in range(2):
                    if pos >= n:
                        raise ValueError("truncated map")
                    _, pos = _item(buf, pos + 1, buf[pos], depth)
            fields[("m", fnum)] = cnt
        elif wire == 7:
            fields[("s", fnum)], pos = parse_struct(buf, pos, depth - 1)
        else:
            raise ValueError(f"bad wire type {wire}")
    return fields, pos


def parse_message(payload: bytes) -> tuple[int, dict[tuple[str, int], Any]] | None:
    """(mid, body struct) of a decompressed lobby frame, or None. Private mids give None."""
    if len(payload) < 3 or payload[0] != 0x70 or payload[1] != 0x00:
        return None
    try:
        mid, _ = read_varint(payload, 2)
        if mid in PRIVATE_MIDS or (mid not in ROOM_MIDS and mid not in (KEEPALIVE_MID, QUEUE_MID, FOUND_MID)):
            return None
        top, _ = parse_struct(payload, 1)
        raw = top.get(("b", 6))
        if not isinstance(raw, bytes) or not raw or raw[0] != 0x70:
            return None
        body, _ = parse_struct(raw, 1)
    except ValueError:
        return None
    return mid, body


def _is_room(d: Any) -> bool:
    return (isinstance(d, dict) and isinstance(d.get(("v", 0)), int) and d[("v", 0)] > 10**10
            and isinstance(d.get(("v", 1)), int))


# ---------------------------------------------------------------- room tracker

class LobbyTracker:
    """Keeps the room you are in. Feed it decoded messages; read `current(now)`."""

    def __init__(self, memory: Path | None = None) -> None:
        self._lock = threading.Lock()
        self.room_id: int | None = None
        self.pvp_type: int | None = None
        self.party_size: int | None = None
        self.self_uid: int | None = None
        self.seen_at: float | None = None
        # 20103 comes when the team is back in the room: after a match, or when a found
        # match is cancelled (someone did not accept). It does not come at draft start.
        self.back_at: float | None = None
        self.queue_state = ""  # "", "queue", "found"
        self.found_at: float | None = None
        # Last room and its size, kept on disk: a restarted bridge inside the same room
        # gets only keepalives (no player list), so it reuses the saved size.
        self.memory = memory
        self._saved: dict[str, int] = {}
        if memory is not None:
            try:
                self._saved = {k: int(v) for k, v in json.loads(memory.read_text()).items()}
            except (OSError, ValueError, AttributeError):
                self._saved = {}
            self.self_uid = self._saved.get("self_uid")
            # Restarted bridge in the same session: keep the room until a new message.
            s = self._saved
            if {"room_id", "pvp_type", "seen_at"} <= s.keys() and (
                    time.time() - s["seen_at"] < ROOM_STALE_SECONDS):
                self.room_id, self.pvp_type = s["room_id"], s["pvp_type"]
                self.party_size, self.seen_at = s.get("party_size"), float(s["seen_at"])

    def on_message(self, mid: int, body: dict[tuple[str, int], Any], now: float) -> None:
        with self._lock:
            if mid == KEEPALIVE_MID:
                if not _is_room(body):
                    return
                if body[("v", 0)] != self.room_id:
                    self.room_id = body[("v", 0)]
                    saved = self._saved.get("party_size") if self._saved.get("room_id") == self.room_id else None
                    self.party_size = saved
                    log.info("lobby room %s, party %s (saved)", self.room_id, saved)
                self.pvp_type = body[("v", 1)]
                self.seen_at = now
                if now - self._saved.get("seen_at", 0) >= 60:  # keep the disk copy fresh
                    self._save()
                return

            if mid == QUEUE_MID:
                self.queue_state = "queue" if body.get(("v", 8)) == 1 else ""
                log.info("queue %s (v8 %s)", self.queue_state or "off", body.get(("v", 8)))
                return
            if mid == FOUND_MID:
                self.queue_state, self.found_at = "found", now
                log.info("match found")
                return

            room = next((v for k, v in body.items() if k[0] == "s" and _is_room(v)), None)
            if room is None:
                return
            uids = [p.get(("v", 0)) for p in room.get(("l", 3)) or [] if isinstance(p, dict)]
            if mid == LEAVE_MID:
                leaver = body.get(("s", 1), {}).get(("v", 0))
                if (leaver is not None and leaver == self.self_uid) or (
                        self.self_uid is not None and self.self_uid not in uids):
                    self._clear()
                    return
            if mid == BACK_MID:
                self.back_at = now
                self.queue_state = ""  # back in the room: no queue, no ready check
            if mid == 11201 and len(uids) == 1:
                self.self_uid = uids[0]
            self.room_id = room[("v", 0)]
            self.pvp_type = room[("v", 1)]
            self.party_size = len(uids) or None
            self.seen_at = now
            log.info("lobby room %s pvp %s party %s (mid %s)", self.room_id, self.pvp_type,
                     self.party_size, mid)
            self._save()

    def _save(self) -> None:
        seen = int(self.seen_at) if self.seen_at is not None else None
        self._saved = {k: v for k, v in (("room_id", self.room_id), ("pvp_type", self.pvp_type),
                                         ("party_size", self.party_size), ("self_uid", self.self_uid),
                                         ("seen_at", seen)) if v is not None}
        if self.memory is not None:
            try:
                self.memory.write_text(json.dumps(self._saved))
            except OSError:
                pass

    def clear(self) -> None:
        """The game closed: you are in no room."""
        with self._lock:
            if self.room_id is not None:
                self._clear()

    def _clear(self) -> None:
        self.room_id = self.pvp_type = self.party_size = self.seen_at = None
        self.queue_state = ""
        log.info("left the lobby room")
        self._save()

    def current(self, now: float) -> LobbyInfo | None:
        with self._lock:
            if self.seen_at is None or now - self.seen_at > ROOM_STALE_SECONDS:
                return None
            assert self.room_id is not None and self.pvp_type is not None
            # Unknown count (bridge started inside a room): show solo until the room changes.
            queue = self.queue_state
            if queue == "found" and (self.found_at is None or now - self.found_at > FOUND_SECONDS):
                queue = ""  # the draft started (or the check ended without a message)
            return LobbyInfo(self.room_id, self.pvp_type, self.party_size or 1, self.back_at, queue)


# ---------------------------------------------------------------- pcap + tcp

LINK_RAW, LINK_ETH, LINK_SLL, LINK_SLL2 = 101, 1, 113, 276


def _ipv4(pkt: bytes, linktype: int) -> bytes | None:
    if linktype == LINK_SLL2 and len(pkt) >= 20 and pkt[0:2] == b"\x08\x00":
        return pkt[20:]
    if linktype == LINK_SLL and len(pkt) >= 16 and pkt[14:16] == b"\x08\x00":
        return pkt[16:]
    if linktype == LINK_ETH and len(pkt) >= 14 and pkt[12:14] == b"\x08\x00":
        return pkt[14:]
    if linktype == LINK_RAW and pkt and pkt[0] >> 4 == 4:
        return pkt
    return None


def tcp_from_lobby(l3: bytes) -> tuple[tuple[bytes, int], int, bytes] | None:
    """(stream key, seq, payload) for IPv4 TCP sent by the lobby server, else None."""
    if len(l3) < 20 or l3[9] != 6:
        return None
    ihl = (l3[0] & 0x0F) * 4
    total = struct.unpack_from("!H", l3, 2)[0]
    l4 = l3[ihl:min(len(l3), total) if total >= ihl else len(l3)]
    if len(l4) < 20:
        return None
    sport, dport, seq = struct.unpack_from("!HHI", l4, 0)
    if sport != LOBBY_PORT:
        return None
    doff = (l4[12] >> 4) * 4
    return (l3[12:16], dport), seq, l4[doff:]


class PcapReader:
    """Incremental pcap reader: feed bytes, get (linktype, packet) records."""

    def __init__(self) -> None:
        self.buf = bytearray()
        self.endian: str | None = None
        self.linktype = 0

    def feed(self, chunk: bytes) -> list[bytes]:
        self.buf.extend(chunk)
        if self.endian is None:
            if len(self.buf) < 24:
                return []
            magic = bytes(self.buf[:4])
            if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
                self.endian = "<"
            elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
                self.endian = ">"
            else:
                raise ValueError("not a pcap stream")
            self.linktype = struct.unpack_from(self.endian + "I", self.buf, 20)[0]
            del self.buf[:24]
        out, pos = [], 0
        while len(self.buf) - pos >= 16:
            incl = struct.unpack_from(self.endian + "I", self.buf, pos + 8)[0]
            if len(self.buf) - pos < 16 + incl:
                break
            out.append(bytes(self.buf[pos + 16:pos + 16 + incl]))
            pos += 16 + incl
        del self.buf[:pos]
        return out


class _Stream:
    """In-order TCP byte stream, split into lobby frames."""

    def __init__(self) -> None:
        self.buf = bytearray()
        self.next_seq: int | None = None
        self.pending: dict[int, bytes] = {}

    def add(self, seq: int, data: bytes) -> list[tuple[int, bytes]]:
        if data:
            if self.next_seq is None:
                self.next_seq = seq
            self.pending[seq] = data
            self._drain()
        return self._frames()

    def _drain(self) -> None:
        progressed = True
        while progressed and self.pending:
            progressed = False
            for seq in list(self.pending):
                diff = (seq - self.next_seq) & 0xFFFFFFFF
                data = self.pending[seq]
                if diff == 0 or diff >= 0x80000000:  # next, or overlaps old bytes
                    del self.pending[seq]
                    skip = 0 if diff == 0 else (self.next_seq - seq) & 0xFFFFFFFF
                    if skip < len(data):
                        self.buf.extend(data[skip:])
                        self.next_seq = (self.next_seq + len(data) - skip) & 0xFFFFFFFF
                    progressed = True
        if len(self.pending) > 512:  # lost a segment: start over at the newest data
            self.pending.clear()
            self.buf.clear()
            self.next_seq = None

    def _frames(self) -> list[tuple[int, bytes]]:
        frames, pos, n = [], 0, len(self.buf)
        while pos + 4 <= n:
            flag = self.buf[pos]
            total = int.from_bytes(self.buf[pos + 1:pos + 4], "big")
            if flag not in (0x00, 0x10) or total < 4 or total > 2 * 1024 * 1024:
                pos += 1  # resync
                continue
            if pos + total > n:
                break
            frames.append((flag, bytes(self.buf[pos + 4:pos + total])))
            pos += total
        del self.buf[:pos]
        return frames


def _zstd_decoder() -> Callable[[bytes], bytes | None]:
    try:
        import zstandard  # type: ignore[import-not-found]
        dctx = zstandard.ZstdDecompressor()

        def dec(frame: bytes) -> bytes | None:
            try:
                return dctx.decompress(frame, max_output_size=8 * 1024 * 1024)
            except zstandard.ZstdError:
                return None
        return dec
    except ImportError:
        exe = shutil.which("zstd")

        def dec_cli(frame: bytes) -> bytes | None:
            if not exe:
                return None
            res = subprocess.run([exe, "-d", "--stdout"], input=frame, capture_output=True, timeout=5)
            return res.stdout if res.returncode == 0 else None
        return dec_cli


class LobbyDecoder:
    """pcap bytes -> tracker updates."""

    def __init__(self, tracker: LobbyTracker) -> None:
        self.tracker = tracker
        self.reader = PcapReader()
        self.streams: dict[tuple[bytes, int], _Stream] = {}
        self.unzstd = _zstd_decoder()

    def feed(self, chunk: bytes, now: float) -> None:
        for pkt in self.reader.feed(chunk):
            l3 = _ipv4(pkt, self.reader.linktype)
            seg = tcp_from_lobby(l3) if l3 else None
            if seg is None:
                continue
            key, seq, data = seg
            for flag, body in self.streams.setdefault(key, _Stream()).add(seq, data):
                self.on_frame(flag, body, now)

    def on_frame(self, flag: int, body: bytes, now: float) -> None:
        if flag == 0x10:
            if not body.startswith(ZSTD_MAGIC):
                return
            body = self.unzstd(body) or b""
        msg = parse_message(body)
        if msg is not None:
            self.tracker.on_message(msg[0], msg[1], now)


# ---------------------------------------------------------------- capture thread

TCPDUMP = "/system/bin/tcpdump -i any -U -s 0 -w - tcp src port 30101"


def run_capture(adb: str, serial: Callable[[], str], tracker: LobbyTracker,
                stop: threading.Event) -> None:
    """Stream lobby packets from the phone until `stop`. Restarts with a back-off."""
    delay = 5.0
    while not stop.is_set():
        dev = serial()
        if dev:
            cmd = [adb, "-s", dev, "exec-out", f"su -c '{TCPDUMP} 2>/dev/null'"]
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            except OSError as exc:
                log.debug("lobby capture failed to start: %s", exc)
            else:
                log.info("lobby capture started on %s", dev)
                _pump(proc, LobbyDecoder(tracker), stop)
                _stop_remote(adb, dev)
        stop.wait(delay)


def _pump(proc: subprocess.Popen, decoder: LobbyDecoder, stop: threading.Event) -> None:
    watchdog = threading.Thread(target=lambda: (stop.wait(), proc.terminate()), daemon=True)
    watchdog.start()
    try:
        assert proc.stdout is not None
        for chunk in iter(lambda: proc.stdout.read1(65536), b""):
            decoder.feed(chunk, time.time())
    except (OSError, ValueError) as exc:
        log.debug("lobby capture stopped: %s", exc)
    finally:
        proc.terminate()


def _stop_remote(adb: str, dev: str) -> None:
    try:
        subprocess.run([adb, "-s", dev, "shell", "su -c 'pkill -f \"tcp src port 30101\"'"],
                       capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass


def frames_for_test(messages: Iterable[bytes]) -> bytes:
    """Wrap raw message payloads as raw (flag 0x00) lobby frames. Used by the tests."""
    return b"".join(b"\x00" + (len(m) + 4).to_bytes(3, "big") + m for m in messages)
