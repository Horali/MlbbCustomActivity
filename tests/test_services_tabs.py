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


def test_old_tcpdumps_are_cleaned_before_a_start(monkeypatch):
    import mlbb_presence.services as services
    monkeypatch.setattr(services, "port_in_use", lambda url: False)
    sv = Services("adb", LobbyTracker(), fixlag_dir=".", viewer_url="http://127.0.0.1:8790/events",
                  mapper_url="http://127.0.0.1:8791/")
    assert sv.stale_patterns() == ["tcp src port 30101", "udp portrange 5000-5999", "tcp port 30101"]


def test_a_hand_started_tool_keeps_its_tcpdump(monkeypatch):
    import mlbb_presence.services as services
    monkeypatch.setattr(services, "port_in_use", lambda url: "8790" in url)
    sv = Services("adb", LobbyTracker(), fixlag_dir=".", viewer_url="http://127.0.0.1:8790/events",
                  mapper_url="http://127.0.0.1:8791/")
    assert sv.stale_patterns() == ["tcp src port 30101"]


def test_pkill_sends_one_su_call(monkeypatch):
    import mlbb_presence.services as services
    calls = []
    monkeypatch.setattr(services.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    sv = Services("adb", LobbyTracker(), lobby=False)
    sv.serial = "dev:1"
    sv._pkill("a b", "c")
    assert calls == [["adb", "-s", "dev:1", "shell", "su -c 'pkill -f \"[a] b\"; pkill -f \"[c]\"'"]]


def test_cleanup_runs_once_when_the_bridge_starts_with_mlbb_closed(monkeypatch):
    sv = Services("adb", LobbyTracker(), lobby=False)
    calls = []
    monkeypatch.setattr(sv, "_pkill", lambda *p: calls.append(p))
    monkeypatch.setattr(sv, "stale_patterns", lambda: ["x"])
    sv.update(False, "dev:1", now=0.0)
    sv.update(False, "dev:1", now=5.0)
    assert calls == [("x",)] and not sv.running


def test_cleanup_runs_after_the_tools_stop(monkeypatch):
    tabs = FakeTabs()
    sv = make(tabs)
    calls = []
    monkeypatch.setattr(sv, "_pkill", lambda *p: calls.append(p))
    monkeypatch.setattr(sv, "stale_patterns", lambda: ["x"])
    sv.update(True, "dev:1", now=0.0)
    sv.update(False, "dev:1", now=1.0)
    sv.update(False, "dev:1", now=61.0)
    assert len(calls) == 2  # once at start, once after the stop


def test_new_link_switches_the_tools_without_a_restart(monkeypatch):
    import mlbb_presence.services as services
    posts = []
    monkeypatch.setattr(services, "post_source", lambda url, body: posts.append((url, body)) or True)
    sv = make(FakeTabs())
    sv._tools = {"chat viewer": object(), "lag mapper": object()}
    sv._stop = object()
    sv.serial = "USB1"
    sv.update(True, "192.168.1.6:39059", now=0.0)
    assert ("http://127.0.0.1:8790/events", {"mode": "switch_adb", "serial": "192.168.1.6:39059"}) in posts
    assert ("http://127.0.0.1:8791/", {"mode": "adb", "serial": "192.168.1.6:39059"}) in posts
    assert set(sv._tools) == {"chat viewer", "lag mapper"}  # same processes, no restart
