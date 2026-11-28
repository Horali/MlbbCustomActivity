"""The tools and their Chrome tabs follow the game, with a one-minute grace period."""
from mlbb_presence.browser import chrome_command
from mlbb_presence.lobby import LobbyTracker
from mlbb_presence.services import Services, page_url


class FakeTabs:
    def __init__(self) -> None:
        self.opened: list[list[str]] = []
        self.closed = 0

    def open(self, urls) -> None:
        self.opened.append(list(urls))

    def close(self) -> None:
        self.closed += 1


def make(tabs: FakeTabs) -> Services:
    return Services("adb", LobbyTracker(), lobby=False, viewer_url="http://127.0.0.1:8790/events",
                    mapper_url="http://127.0.0.1:8791/", tabs=tabs)


def test_page_url_drops_the_path():
    assert page_url("http://127.0.0.1:8790/events") == "http://127.0.0.1:8790/"
    assert page_url("") == ""


def test_tabs_open_with_the_game():
    tabs = FakeTabs()
    sv = make(tabs)
    sv.update(True, "dev:1", now=0.0)
    assert tabs.opened == [["http://127.0.0.1:8790/", "http://127.0.0.1:8791/"]]


def test_tabs_close_only_after_a_minute_closed():
    tabs = FakeTabs()
    sv = make(tabs)
    sv.update(True, "dev:1", now=0.0)
    sv.update(False, "dev:1", now=100.0)
    sv.update(False, "dev:1", now=159.0)
    assert sv.running and tabs.closed == 0
    sv.update(False, "dev:1", now=160.0)
    assert not sv.running and tabs.closed == 1


def test_quick_restart_keeps_the_tabs():
    tabs = FakeTabs()
    sv = make(tabs)
    sv.update(True, "dev:1", now=0.0)
    sv.update(False, "dev:1", now=10.0)
    sv.update(True, "dev:1", now=40.0)    # back within the minute
    sv.update(False, "dev:1", now=50.0)   # the minute starts again here
    sv.update(False, "dev:1", now=100.0)
    assert sv.running and tabs.closed == 0 and len(tabs.opened) == 1
    sv.update(False, "dev:1", now=110.0)
    assert not sv.running and tabs.closed == 1


def test_phone_unreachable_changes_nothing():
    tabs = FakeTabs()
    sv = make(tabs)
    sv.update(True, "dev:1", now=0.0)
    sv.update(None, "dev:1", now=500.0)
    assert sv.running and tabs.closed == 0


def test_both_tools_get_the_serial_and_port():
    sv = make(FakeTabs())
    cmds = sv._tool_commands("dev:1")
    assert cmds["chat viewer"][1][:4] == ["-m", "tools.chat_viewer", "--adb", "dev:1"]
    mapper = cmds["lag mapper"][1]
    assert mapper[:4] == ["-m", "tools.lag_mapper", "--serial", "dev:1"]
    assert "8791" in mapper and "--no-browser" in mapper


def test_chrome_uses_its_own_profile():
    cmd = chrome_command("chrome.exe", ["http://a/", "http://b/"])
    assert any(a.startswith("--user-data-dir=") for a in cmd)
    assert cmd[-2:] == ["http://a/", "http://b/"]
