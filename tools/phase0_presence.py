"""Phase 0: send one fixed test presence to Discord desktop.

Usage:
    pip install pypresence
    python tools/phase0_presence.py            # https buttons
    python tools/phase0_presence.py --scheme   # test a mobilelegends:// button (expect failure)
"""
import os
import sys
import time
from pathlib import Path

try:
    from pypresence import Presence
except ImportError:
    sys.exit("Install first: pip install pypresence")


def load_env() -> None:
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    load_env()
    app_id = os.environ.get("DISCORD_APP_ID")
    if not app_id:
        sys.exit("Set DISCORD_APP_ID in .env (copy .env.example)")
    watch = os.environ.get("WATCH_URL", "https://applink.mobilelegends.com/")
    if "--scheme" in sys.argv:
        watch = "mobilelegends://"

    rpc = Presence(app_id)
    rpc.connect()
    rpc.update(
        details="Ranked · Draft pick",
        state="Trio queue",
        party_size=[3, 5],
        start=int(time.time()),
        large_image=os.environ.get("LARGE_IMAGE", "mlbb"),
        large_text="Mobile Legends: Bang Bang",
        small_image=os.environ.get("SMALL_IMAGE", "squad_3"),
        small_text="Trio queue (3 of 5)",
        buttons=[
            {"label": "Watch my stream", "url": watch},
            {"label": "Join my party", "url": "https://applink.mobilelegends.com/"},
        ],
    )
    print(f"Presence sent (watch url: {watch}). Check it from a second account. Ctrl+C stops.")
    try:
        while True:
            time.sleep(15)
    except KeyboardInterrupt:
        rpc.clear()
        rpc.close()


if __name__ == "__main__":
    main()
