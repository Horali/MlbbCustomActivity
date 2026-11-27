from mlbb_presence.config import Config
from mlbb_presence.game import GameInfo, parse_etime, parse_foreground, parse_ps
from mlbb_presence.mapper import to_presence
from mlbb_presence.match import MatchFeed, iter_sse, match_from_summary
from mlbb_presence.sender import Debouncer
from mlbb_presence import state as S
from mlbb_presence.state import GameState, StateMachine
from mlbb_presence.match import MatchInfo

CFG = Config(app_id="1", ign="naradira", level="86")
ON = GameInfo(running=True, foreground=True, started_at=1000.0)


# ---- mapper ----

def test_closed_clears_presence():
    assert to_presence(GameState(S.CLOSED), CFG) is None


def test_lobby_puts_name_and_level_first():
    p = to_presence(GameState(S.LOBBY, session_start=1000.0), CFG)
    assert p["details"] == "naradira · Lv. 86"
    assert p["state"] == "In lobby"
    assert p["start"] == 1000
    assert p["large_image"] == "mlbb_icon"
    assert "small_image" not in p and "buttons" not in p


def test_battle_shows_hero_mode_badge():
    s = GameState(S.BATTLE, session_start=1000.0, match_start=2000.0, mode="Ranked",
                  party_size=3, hero="Fanny", ign="naradira")
    p = to_presence(s, CFG)
    assert p["state"] == "Fanny · Ranked · In match"
    assert p["party_size"] == [3, 5]
    assert p["small_image"] == "squadog_3"
    assert p["small_text"] == "Trio queue (3 of 5)"
    assert p["large_text"] == "Playing as Fanny"
    assert p["start"] == 1000  # session timer by default


def test_match_timer_option():
    cfg = Config(app_id="1", match_timer=True)
    s = GameState(S.BATTLE, session_start=1000.0, match_start=2000.0)
    assert to_presence(s, cfg)["start"] == 2000


def test_ign_from_game_wins_over_env():
    p = to_presence(GameState(S.DRAFT, ign="RealName"), CFG)
    assert p["details"] == "RealName · Lv. 86"


def test_custom_room_has_no_badge():
    s = GameState(S.DRAFT, mode="Custom Draft", is_custom=True, party_size=5)
    p = to_presence(s, CFG)
    assert "small_image" not in p and "party_size" not in p


def test_watch_button_only_when_live_and_https():
    s = GameState(S.LOBBY)
    assert "buttons" not in to_presence(s, Config(app_id="1", watch_url="https://x.test/"))
    assert "buttons" not in to_presence(s, Config(app_id="1", live=True, watch_url="mobilelegends://"))
    p = to_presence(s, Config(app_id="1", live=True, watch_url="https://x.test/"))
    assert p["buttons"] == [{"label": "Watch my stream", "url": "https://x.test/"}]


def test_no_name_falls_back_to_game_name():
    p = to_presence(GameState(S.IDLE), Config(app_id="1"))
    assert p["details"] == "Mobile Legends: Bang Bang"
    assert p["state"] == "Idle"


# ---- state machine ----

def M(phase, mid="m1"):
    return MatchInfo(match_id=mid, phase=phase, mode="Ranked", party_size=2, hero="Ling")


def test_full_match_cycle():
    sm = StateMachine()
    assert sm.update(GameInfo(running=False), None, None, 0).phase == S.CLOSED
    assert sm.update(ON, None, None, 10).phase == S.LOBBY
    assert sm.update(ON, M("DRAFT"), 0.5, 20).phase == S.DRAFT
    st = sm.update(ON, M("BATTLE"), 0.5, 30)
    assert st.phase == S.BATTLE and st.match_start == 30 and st.hero == "Ling"
    assert sm.update(ON, M("BATTLE"), 5, 600).match_start == 30
    st = sm.update(ON, M("BATTLE"), 25, 620)  # packets stopped
    assert st.phase == S.AFTER and st.mode == "Ranked"
    assert sm.update(ON, M("BATTLE"), 40, 650).phase == S.AFTER  # same match stays ended
    assert sm.update(ON, M("BATTLE"), 90, 690).phase == S.LOBBY
    assert sm.update(ON, M("DRAFT", "m2"), 0.1, 700).phase == S.DRAFT
    assert sm.session_start == 1000.0


def test_background_is_idle_and_close_resets():
    sm = StateMachine()
    assert sm.update(GameInfo(True, False, 5.0), None, None, 10).phase == S.IDLE
    assert sm.update(GameInfo(running=False), None, None, 20).phase == S.CLOSED
    assert sm.session_start is None


def test_viewer_gone_during_battle_ends_match():
    sm = StateMachine()
    sm.update(ON, M("BATTLE"), 0.1, 10)
    assert sm.update(ON, None, None, 20).phase == S.AFTER


def test_phone_unreachable_keeps_state():
    sm = StateMachine()
    sm.update(ON, M("DRAFT"), 0.1, 10)
    assert sm.update(None, M("DRAFT"), 0.1, 15).phase == S.DRAFT
    assert StateMachine().update(None, None, None, 0).phase == S.CLOSED


# ---- game watcher parsing ----

def test_parse_etime():
    assert parse_etime("05:07") == 307
    assert parse_etime("01:02:03") == 3723
    assert parse_etime("2-00:00:10") == 2 * 86400 + 10


def test_parse_ps_and_foreground():
    ps = "  PID     ELAPSED NAME\n 4242    01:00:00 com.mobile.legends\n 4243 05:00 com.mobile.legends:push\n"
    assert parse_ps(ps, 10000.0) == (True, 6400.0)
    assert parse_ps(" 1 00:01 init\n", 1.0) == (False, None)
    assert parse_foreground("  topResumedActivity=ActivityRecord{x u0 com.mobile.legends/.MainActivity t1}")
    assert not parse_foreground("  topResumedActivity=ActivityRecord{x u0 com.android.launcher/.Home t1}")


# ---- match watcher ----

SUMMARY = {
    "match_id": "m9", "phase": "DRAFT", "pvp_type": 4, "mode_label": "Ranked",
    "local_party_size": 3, "local_uid": 7,
    "players": [{"uid": 3, "name": "other", "hero_name": "Tigreal"},
                {"uid": 7, "name": "naradira", "hero_name": "Fanny"}],
}


def test_match_from_summary_picks_local_player():
    m = match_from_summary(SUMMARY)
    assert (m.phase, m.mode, m.party_size, m.hero, m.ign, m.is_custom) == (
        "DRAFT", "Ranked", 3, "Fanny", "naradira", False)


def test_feed_uses_status_phase_and_goes_stale():
    feed = MatchFeed()
    feed.handle("match_new", SUMMARY, 100)
    assert feed.current(100) == (None, None)  # no status yet
    feed.handle("status", {"active_match_id": "m9", "phase": "BATTLE", "last_pkt_age_s": 0.2}, 101)
    m, age = feed.current(102)
    assert m.phase == "BATTLE" and age == 0.2
    assert feed.current(200) == (None, None)


def test_iter_sse():
    lines = ["event: status\n", 'data: {"a": 1}\n', "\n", "id: 3\n", 'data: {"b": 2}\n', "\n"]
    assert list(iter_sse(lines)) == [("status", {"a": 1}), ("message", {"b": 2})]


# ---- debouncer ----

def test_debouncer_limits_rate_and_skips_repeats():
    d = Debouncer(15)
    assert d.due({"x": 1}, 0)
    d.mark({"x": 1}, 0)
    assert not d.due({"x": 1}, 100)
    assert not d.due({"x": 2}, 10)
    assert d.due({"x": 2}, 15)
    assert d.due(None, 15)


def test_pick_device_prefers_usb():
    from mlbb_presence.game import pick_device
    out = "List of devices attached\n192.168.1.6:5555\tdevice\nRRCY1032Y6F\tdevice\nX\toffline\n"
    assert pick_device(out) == "RRCY1032Y6F"
    assert pick_device("List of devices attached\n192.168.1.6:5555\tdevice\n") == "192.168.1.6:5555"
    assert pick_device("List of devices attached\n") == ""


def test_parse_profile_reads_name_and_level():
    from mlbb_presence.game import parse_profile
    text = ('    <string name="OfflineRoleName">nara&amp;dira</string>\n'
            '    <int name="OfflineRoleLevel" value="113" />\n')
    assert parse_profile(text) == ("nara&dira", "113")
    assert parse_profile("") == ("", "")
