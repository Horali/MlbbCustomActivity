"""Run the bridge: python -m mlbb_presence [--dry-run] [-v]

Start the FixLag chat viewer first for mode, hero and party size.
Without it, the card shows the lobby/idle state and the session timer only.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
from dataclasses import replace

from .config import Config
from .game import GameWatcher
from .mapper import to_presence
from .match import MatchFeed, run_feed
from .sender import Sender
from .state import StateMachine

POLL_SECONDS = 5.0
PROFILE_SECONDS = 600.0  # re-read IGN and level from the phone every 10 min


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mlbb_presence")
    ap.add_argument("--dry-run", action="store_true", help="print the presence, do not send it")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    cfg = Config.from_env()
    if not cfg.app_id and not args.dry_run:
        print("Set DISCORD_APP_ID in .env (copy .env.example)", file=sys.stderr)
        return 2

    feed = MatchFeed()
    stop = threading.Event()
    threading.Thread(target=run_feed, args=(cfg.viewer_url, feed, stop), daemon=True).start()

    game = GameWatcher(cfg.adb, cfg.adb_serial)
    machine = StateMachine()
    sender = None if args.dry_run else Sender(cfg.app_id)
    last_printed: object = ()
    profile_at = 0.0
    try:
        while True:
            now = time.time()
            if now - profile_at >= PROFILE_SECONDS:
                ign, level = game.profile()
                if ign or level:
                    cfg = replace(cfg, ign=ign or cfg.ign, level=level or cfg.level)
                    logging.info("profile from phone: %s, level %s", cfg.ign, cfg.level)
                profile_at = now
            match, age = feed.current(now)
            state = machine.update(game.poll(), match, age, now)
            payload = to_presence(state, cfg)
            if sender is not None:
                sender.push(payload, now)
            elif payload != last_printed:
                print(state.phase, json.dumps(payload, ensure_ascii=False), flush=True)
                last_printed = payload
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if sender is not None:
            sender.push(None, float("inf"))
            sender.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
