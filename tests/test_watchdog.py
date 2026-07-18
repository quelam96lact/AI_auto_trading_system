from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.collector.watchdog import Watchdog


class Clock:
    def __init__(self):
        self.t = datetime(2026, 7, 15, 9, 30, tzinfo=TZ)
    def now(self):
        return self.t


def make(clock, trading=True):
    calls = {"stale": 0, "critical": 0}
    wd = Watchdog(
        stale_seconds=180, max_failures=3, now_fn=clock.now,
        is_trading_fn=lambda ts: trading,
        on_stale=lambda: calls.__setitem__("stale", calls["stale"] + 1),
        on_critical=lambda: calls.__setitem__("critical", calls["critical"] + 1),
    )
    return wd, calls


def test_no_alert_when_fresh():
    c = Clock(); wd, calls = make(c)
    wd.beat(); c.t += timedelta(seconds=60); wd.check()
    assert calls["stale"] == 0


def test_stale_then_critical_after_max_failures():
    c = Clock(); wd, calls = make(c)
    wd.beat()
    for i in range(3):
        c.t += timedelta(seconds=181); wd.check()
    assert calls["stale"] == 3 and calls["critical"] == 1


def test_beat_resets_failure_count():
    c = Clock(); wd, calls = make(c)
    wd.beat(); c.t += timedelta(seconds=181); wd.check()
    wd.beat(); c.t += timedelta(seconds=181); wd.check()
    assert calls["stale"] == 2 and calls["critical"] == 0


def test_silent_outside_trading_hours():
    c = Clock(); wd, calls = make(c, trading=False)
    wd.beat(); c.t += timedelta(seconds=9999); wd.check()
    assert calls["stale"] == 0