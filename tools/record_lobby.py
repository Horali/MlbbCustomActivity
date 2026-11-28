"""Record lobby frame ids in both directions: time, direction, flag, mid, size.

Ids and sizes only, no message content. Research tool for the queue signal
(handoffs/discord-presence.md). Needs root adb.

Use: python tools/record_lobby.py <adb serial> <seconds> <out.txt>
"""
import shutil
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mlbb_presence import lobby as L  # noqa: E402

ADB = shutil.which("adb") or str(Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe")


def segment(l3: bytes):
    if len(l3) < 20 or l3[9] != 6:
        return None
    l4 = l3[(l3[0] & 15) * 4:]
    sport, dport, seq = struct.unpack_from("!HHI", l4, 0)
    direction = "S>C" if sport == L.LOBBY_PORT else "C>S"
    return (direction, l3[12:16], sport, dport), seq, l4[(l4[12] >> 4) * 4:]


def main() -> None:
    dev, secs, out = sys.argv[1], float(sys.argv[2]), open(sys.argv[3], "w", buffering=1)
    reader, streams, unzstd = L.PcapReader(), {}, L._zstd_decoder()

    def frame(direction: str, flag: int, body: bytes) -> None:
        raw = body
        if flag == 0x10 and body.startswith(L.ZSTD_MAGIC):
            raw = unzstd(body) or b""
        mid = L.read_varint(raw, 2)[0] if len(raw) > 3 and raw[:2] == b"\x70\x00" else "?"
        out.write(f"{time.strftime('%H:%M:%S')} {direction} f{flag:02x} {mid} {len(raw)}\n")

    cmd = [ADB, "-s", dev, "exec-out",
           f"su -c '/system/bin/tcpdump -i any -U -s 0 -w - tcp port {L.LOBBY_PORT} 2>/dev/null'"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    threading.Timer(secs, proc.terminate).start()
    out.write(f"start {time.strftime('%H:%M:%S')}\n")
    for chunk in iter(lambda: proc.stdout.read1(65536), b""):
        for pkt in reader.feed(chunk):
            l3 = L._ipv4(pkt, reader.linktype)
            seg = segment(l3) if l3 else None
            if seg is None:
                continue
            key, seq, data = seg
            for flag, body in streams.setdefault(key, L._Stream()).add(seq, data):
                frame(key[0], flag, body)
    out.write(f"end {time.strftime('%H:%M:%S')}\n")


if __name__ == "__main__":
    main()
