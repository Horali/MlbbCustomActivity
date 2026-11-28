"""Sender + Activity Controller light (traffic light)."""
from mlbb_presence.sender import Sender

CARD = {"details": "Ranked", "state": "In game", "large_image": "mlbb"}


class FakeRpc:
    def __init__(self):
        self.calls = []

    def update(self, **kw):
        self.calls.append(("update", kw.get("details")))

    def clear(self):
        self.calls.append(("clear", None))

    def close(self):
        pass


class FakeController:
    def __init__(self, light):
        self.light = light
        self.reports = []
        self.pokes = 0

    def update(self, **kw):
        self.reports.append(kw)

    def poke(self):
        self.pokes += 1


def make(light):
    ctl = FakeController(light)
    s = Sender("1", controller=ctl)
    s.rpc = FakeRpc()
    return s, ctl


def test_red_clears_at_once_inside_the_debounce():
    s, ctl = make("green")
    s.push(CARD, 100.0)
    ctl.light = "red"
    s.push(CARD, 101.0)  # 1 s later: the 15 s debounce must not delay a red
    assert s.rpc.calls == [("update", "Ranked"), ("clear", None)]
    assert ctl.reports[-1]["online"] is True
    assert ctl.reports[-1]["showing"] is False


def test_green_after_red_sends_at_once():
    s, ctl = make("red")
    s.push(CARD, 100.0)
    ctl.light = "green"
    s.push(CARD, 102.0)
    assert s.rpc.calls == [("clear", None), ("update", "Ranked")]
    assert ctl.reports[-1]["showing"] is True
    assert ctl.pokes >= 1


def test_wait_shows_nothing():
    s, ctl = make("wait")
    s.push(CARD, 100.0)
    assert s.rpc.calls == [("clear", None)]


def test_none_keeps_the_old_debounce():
    s, ctl = make("none")
    s.push(CARD, 100.0)
    s.push({**CARD, "details": "Classic"}, 105.0)  # inside 15 s: waits
    assert s.rpc.calls == [("update", "Ranked")]
    s.push({**CARD, "details": "Classic"}, 116.0)
    assert s.rpc.calls[-1] == ("update", "Classic")


def test_no_card_reports_offline():
    s, ctl = make("none")
    s.push(None, 100.0)
    assert ctl.reports[-1]["online"] is False
    assert ctl.reports[-1]["preview"] is None


def test_no_controller_works_as_before():
    s = Sender("1")
    s.rpc = FakeRpc()
    s.push(CARD, 100.0)
    assert s.rpc.calls == [("update", "Ranked")]
