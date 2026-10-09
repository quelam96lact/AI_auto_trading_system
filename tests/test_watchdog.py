import asyncio
from datetime import datetime, timedelta

from trading.calendar_vn import TZ, is_continuous_matching
from trading.collector.watchdog import Watchdog


class Clock:
    def __init__(self, t: datetime | None = None):
        self.t = t if t is not None else datetime(2026, 7, 15, 9, 30, tzinfo=TZ)

    def now(self):
        return self.t


def make(clock, trading=True):
    calls = {"stale": 0, "critical": 0}
    wd = Watchdog(
        stale_seconds=180,
        max_failures=3,
        now_fn=clock.now,
        is_trading_fn=lambda ts: trading,
        on_stale=lambda: calls.__setitem__("stale", calls["stale"] + 1),
        on_critical=lambda: calls.__setitem__("critical", calls["critical"] + 1),
    )
    return wd, calls


def make_continuous_wd(clock):
    calls = {"stale": 0, "critical": 0}
    wd = Watchdog(
        stale_seconds=180,
        max_failures=3,
        now_fn=clock.now,
        is_trading_fn=lambda ts: is_continuous_matching(ts),
        on_stale=lambda: calls.__setitem__("stale", calls["stale"] + 1),
        on_critical=lambda: calls.__setitem__("critical", calls["critical"] + 1),
    )
    return wd, calls


def test_no_alert_when_fresh():
    c = Clock()
    wd, calls = make(c)
    wd.beat()
    c.t += timedelta(seconds=60)
    wd.check()
    assert calls["stale"] == 0


def test_stale_then_critical_after_max_failures():
    c = Clock()
    wd, calls = make(c)
    wd.beat()
    for _ in range(3):
        c.t += timedelta(seconds=181)
        wd.check()
    assert calls["stale"] == 3 and calls["critical"] == 1


def test_beat_resets_failure_count():
    c = Clock()
    wd, calls = make(c)
    wd.beat()
    c.t += timedelta(seconds=181)
    wd.check()
    wd.beat()
    c.t += timedelta(seconds=181)
    wd.check()
    assert calls["stale"] == 2 and calls["critical"] == 0


def test_silent_outside_trading_hours():
    c = Clock()
    wd, calls = make(c, trading=False)
    wd.beat()
    c.t += timedelta(seconds=9999)
    wd.check()
    assert calls["stale"] == 0


# =====================================================================
# Brief 168: Watchdog feed không báo nhầm trong ATO/ATC & reset ngoài phiên
# =====================================================================


def test_ato_silence():
    """Brief 168 §3.1: ATO im lặng — tick cuối lúc 14:30 hôm trước, check mỗi 30s từ 09:00 tới 09:14:30 không có beat -> không báo."""
    # Tick cuối lúc 14:30 hôm trước (thứ Tư 07/10/2026)
    clock = Clock(datetime(2026, 10, 7, 14, 30, tzinfo=TZ))
    wd, calls = make_continuous_wd(clock)
    wd.beat()

    # check() mỗi 30s từ 09:00 tới 09:14:30 ngày 08/10/2026, không có beat()
    clock.t = datetime(2026, 10, 8, 9, 0, tzinfo=TZ)
    end_ato = datetime(2026, 10, 8, 9, 14, 30, tzinfo=TZ)
    while clock.t <= end_ato:
        wd.check()
        clock.t += timedelta(seconds=30)

    assert calls["stale"] == 0
    assert calls["critical"] == 0


def test_enter_continuous_session_no_immediate_alert():
    """Brief 168 §3.2: Vào phiên liên tục không báo ngay — 09:15:00 và 09:17:30 không báo, 09:18:30 báo 1 lần."""
    clock = Clock(datetime(2026, 10, 7, 14, 30, tzinfo=TZ))
    wd, calls = make_continuous_wd(clock)
    wd.beat()

    # Chạy qua ATO
    clock.t = datetime(2026, 10, 8, 9, 0, tzinfo=TZ)
    end_ato = datetime(2026, 10, 8, 9, 14, 30, tzinfo=TZ)
    while clock.t <= end_ato:
        wd.check()
        clock.t += timedelta(seconds=30)

    # 09:15:00 và 09:17:30 không có beat() -> không báo
    clock.t = datetime(2026, 10, 8, 9, 15, 0, tzinfo=TZ)
    wd.check()
    assert calls["stale"] == 0

    clock.t = datetime(2026, 10, 8, 9, 17, 30, tzinfo=TZ)
    wd.check()
    assert calls["stale"] == 0

    # Lúc 09:18:30 (quá 180s kể từ 09:15) -> on_stale 1 lần
    clock.t = datetime(2026, 10, 8, 9, 18, 30, tzinfo=TZ)
    wd.check()
    assert calls["stale"] == 1
    assert calls["critical"] == 0


def test_dead_in_session_stale_and_critical():
    """Brief 168 §3.3: Chết thật trong phiên vẫn bắt được — beat() 10:00, check() mỗi 30s không có tick -> stale ở >180s, critical sau 3 lần."""
    clock = Clock(datetime(2026, 10, 8, 10, 0, 0, tzinfo=TZ))
    wd, calls = make_continuous_wd(clock)
    wd.beat()

    # check() mỗi 30s không có tick: 10:00:30 -> 10:03:00 (<= 180s) -> stale = 0
    for _ in range(6):
        clock.t += timedelta(seconds=30)
        wd.check()
    assert calls["stale"] == 0

    # Lần đầu quá 180s (10:03:30) -> stale 1
    clock.t += timedelta(seconds=30)
    wd.check()
    assert calls["stale"] == 1
    assert calls["critical"] == 0

    # Lần 2 (10:06:31) -> stale 2
    clock.t += timedelta(seconds=181)
    wd.check()
    assert calls["stale"] == 2
    assert calls["critical"] == 0

    # Lần 3 (10:09:32) -> stale 3 + critical 1
    clock.t += timedelta(seconds=181)
    wd.check()
    assert calls["stale"] == 3
    assert calls["critical"] == 1


def test_atc_silence():
    """Brief 168 §3.4: ATC im lặng — beat() 14:29:50, check() từ 14:30 tới 14:45 -> không báo."""
    clock = Clock(datetime(2026, 10, 8, 14, 29, 50, tzinfo=TZ))
    wd, calls = make_continuous_wd(clock)
    wd.beat()

    clock.t = datetime(2026, 10, 8, 14, 30, 0, tzinfo=TZ)
    end_atc = datetime(2026, 10, 8, 14, 45, 0, tzinfo=TZ)
    while clock.t <= end_atc:
        wd.check()
        clock.t += timedelta(seconds=30)

    assert calls["stale"] == 0
    assert calls["critical"] == 0


def test_lunch_break_and_afternoon_entry():
    """Brief 168 §3.5: Nghỉ trưa — beat() 11:29:50, check() 11:30-12:59:30 không báo; 13:00 và 13:02:30 không báo; 13:03:30 báo 1 lần."""
    clock = Clock(datetime(2026, 10, 8, 11, 29, 50, tzinfo=TZ))
    wd, calls = make_continuous_wd(clock)
    wd.beat()

    # check() từ 11:30 tới 12:59:30 mỗi 30s -> không báo
    clock.t = datetime(2026, 10, 8, 11, 30, 0, tzinfo=TZ)
    end_lunch = datetime(2026, 10, 8, 12, 59, 30, tzinfo=TZ)
    while clock.t <= end_lunch:
        wd.check()
        clock.t += timedelta(seconds=30)
    assert calls["stale"] == 0

    # 13:00:00 và 13:02:30 không báo
    clock.t = datetime(2026, 10, 8, 13, 0, 0, tzinfo=TZ)
    wd.check()
    assert calls["stale"] == 0

    clock.t = datetime(2026, 10, 8, 13, 2, 30, tzinfo=TZ)
    wd.check()
    assert calls["stale"] == 0

    # 13:03:30 (quá 180s kể từ 13:00) không có tick -> on_stale 1 lần
    clock.t = datetime(2026, 10, 8, 13, 3, 30, tzinfo=TZ)
    wd.check()
    assert calls["stale"] == 1
    assert calls["critical"] == 0


async def test_collector_main_watchdog_wiring(monkeypatch):
    """Brief 168 §3.6: Nối dây — Watchdog trong collector/main nhận hàm cho kết quả False lúc 09:05, 14:35 và True lúc 10:00."""
    from types import SimpleNamespace

    import trading.collector.main as collector_main

    captured_kwargs = {}

    class FakeWatchdog:
        def __init__(self, *args, **kwargs):
            captured_kwargs.update(kwargs)

    async def _noop():
        pass

    async def _counts():
        return {}

    monkeypatch.setattr(collector_main, "Watchdog", FakeWatchdog)
    monkeypatch.setattr(collector_main, "Storage", lambda *a, **k: SimpleNamespace(init_schema=lambda: None))
    monkeypatch.setattr(collector_main, "BarPublisher", lambda *a, **k: SimpleNamespace(connect=_noop, close=_noop))
    monkeypatch.setattr(collector_main, "run_backfill", lambda *a, **k: _counts())
    monkeypatch.setattr(collector_main, "SSIRestClient", lambda *a, **k: SimpleNamespace(close=_noop))
    monkeypatch.setattr(collector_main, "SSIFeed", lambda *a, **k: SimpleNamespace(start=lambda: None, stop=_noop))
    monkeypatch.setattr(collector_main, "housekeeping_loop", lambda *a, **k: _noop())

    cfg = SimpleNamespace(
        db_dsn="dsn",
        nats_url="url",
        nats_stream="stream",
        bar_interval_minutes=5,
        symbols=["VCB"],
        watchdog_stale_seconds=180,
        watchdog_max_failures=3,
        holidays=frozenset(),
    )
    stop_event = asyncio.Event()
    stop_event.set()

    await collector_main.run(cfg, stop_event=stop_event)

    is_trading_fn = captured_kwargs.get("is_trading_fn")
    assert is_trading_fn is not None, "Watchdog phai nhan is_trading_fn"

    # Thứ Năm 08/10/2026: ngày giao dịch
    t_ato = datetime(2026, 10, 8, 9, 5, tzinfo=TZ)
    t_atc = datetime(2026, 10, 8, 14, 35, tzinfo=TZ)
    t_cont = datetime(2026, 10, 8, 10, 0, tzinfo=TZ)

    assert is_trading_fn(t_ato) is False, "09:05 (ATO) phai tra ve False"
    assert is_trading_fn(t_atc) is False, "14:35 (ATC) phai tra ve False"
    assert is_trading_fn(t_cont) is True, "10:00 (lien tuc) phai tra ve True"