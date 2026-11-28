"""Settings from `.env` (not in git) and the process environment."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ADB = Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools" / "adb.exe"


def load_env(path: Path = ROOT / ".env") -> None:
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    app_id: str
    ign: str = ""
    level: str = ""
    large_image: str = "mlbb_icon"
    badge_prefix: str = "party_"
    badge_icon: bool = True  # small badge on the large image; .env BADGE_ICON=1 (off by default)
    watch_url: str = ""
    live: bool = False
    match_timer: bool = False
    adb: str = str(DEFAULT_ADB)
    adb_serial: str = ""
    viewer_url: str = "http://127.0.0.1:8765/events"
    fixlag_dir: str = ""  # set: the bridge starts the FixLag chat viewer while MLBB runs
    mapper_url: str = ""  # set: the bridge also starts the FixLag lag mapper on this port
    tool_tabs: bool = True  # open a Chrome window with a tab per tool while MLBB runs
    chrome: str = ""  # path to chrome.exe; empty = the usual install folders

    @classmethod
    def from_env(cls) -> "Config":
        load_env()
        env = os.environ.get
        return cls(
            app_id=env("DISCORD_APP_ID", ""),
            ign=env("IGN", ""),
            level=env("LEVEL", ""),
            large_image=env("LARGE_IMAGE", "mlbb_icon"),
            badge_prefix=env("BADGE_PREFIX", "party_"),
            badge_icon=_flag("BADGE_ICON"),
            watch_url=env("WATCH_URL", ""),
            live=_flag("LIVE"),
            match_timer=_flag("MATCH_TIMER"),
            adb=env("ADB", str(DEFAULT_ADB)),
            adb_serial=env("ADB_SERIAL", ""),
            viewer_url=env("VIEWER_URL", "http://127.0.0.1:8765/events"),
            fixlag_dir=env("FIXLAG_DIR", ""),
            mapper_url=env("MAPPER_URL", ""),
            tool_tabs=_flag("TOOL_TABS", True),
            chrome=env("CHROME", ""),
        )
