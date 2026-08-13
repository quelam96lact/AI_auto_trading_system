from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from trading.calendar_vn import TZ
from trading.collector.main import (
    HousekeepingState,
    housekeeping_loop,
    housekeeping_tick,
)
from trading.config import Config


@pytest.fixture
def cfg():
    return Config(
        symbols=["VCB"],
        indices=[],
        bar_interval_minutes=5,
        ssi_equity_accounts=[],
        holidays=set(),
        db_dsn="postgresql://x:***@localhost/db",
        nats_url="nats://localhost:4222",
        nats_stream="BARS",
        watchdog_stale_seconds=180,
        watchdog_max_failures=3,
        ssi_consumer_id="c",
        ssi_consumer_secret="s",
        ssi_api_key="k",
        ssi_api_secret="a",
        ssi_private_key="pk",
        real_trading_enabled=False,
        real_order_capital=1_000_000_000.0,
        real_order_account="ACC",
    )


async def test_housekeeping_loop_survives_db_failure(cfg, monkeypatch):
    """Postgres restart vài giây không được giết collector."""
    import trading.collector.main as collector_main

    alerts_seen = []
    monkeypatch.setattr(
        collector_main,
        "alert",
        lambda level, msg, **f: alerts_seen.append((level, msg)),
    )

    storage = MagicMock()
    storage.beat.side_effect = OSError("connection refused")
    wd = MagicMock()

    # Không được ném exception ra ngoài.
    await housekeeping_loop(cfg, storage, wd, sleep_seconds=0, max_ticks=2)

    assert storage.beat.call_count == 2, "loop phải chạy tiếp sau lần lỗi đầu"
    assert (
        sum(1 for lvl, m in alerts_seen if lvl == "WARN" and "housekeeping tick failed" in m)
        == 2
    )


async def test_housekeeping_tick_beats_and_checks_watchdog(cfg, monkeypatch):
    import trading.collector.main as collector_main

    async def fake_sync(*args):
        return None

    monkeypatch.setattr(collector_main, "sync_account_data", fake_sync)
    monkeypatch.setattr(collector_main, "sync_derivative_data", fake_sync)
    monkeypatch.setattr(collector_main, "alert", lambda *a, **k: None)

    storage = MagicMock()
    wd = MagicMock()
    state = HousekeepingState()

    await housekeeping_tick(cfg, storage, wd, state)

    wd.check.assert_called_once()
    storage.beat.assert_called_once_with("collector")
    assert state.last_account_sync is not None


async def test_housekeeping_tick_skips_account_sync_within_5_minutes(cfg, monkeypatch):
    import trading.collector.main as collector_main

    calls = []

    async def fake_sync(*args):
        calls.append(args)

    monkeypatch.setattr(collector_main, "sync_account_data", fake_sync)
    monkeypatch.setattr(collector_main, "sync_derivative_data", fake_sync)
    monkeypatch.setattr(collector_main, "alert", lambda *a, **k: None)

    storage = MagicMock()
    wd = MagicMock()
    state = HousekeepingState(last_account_sync=datetime.now(TZ) - timedelta(minutes=1))

    await housekeeping_tick(cfg, storage, wd, state)

    assert calls == [], "chưa đủ 5 phút thì không sync account"


async def test_persist_bars_alerts_critical_instead_of_raising(monkeypatch):
    """DB lỗi không được nuốt im lặng thành 'Task exception was never retrieved'."""
    import trading.collector.main as collector_main
    from trading.models import Bar

    alerts_seen = []
    monkeypatch.setattr(
        collector_main,
        "alert",
        lambda level, msg, **f: alerts_seen.append((level, msg)),
    )

    storage = MagicMock()
    storage.write_bars.side_effect = OSError("connection refused")
    pub = MagicMock()
    bar = Bar("VCB", datetime(2026, 7, 15, 9, 5, tzinfo=TZ), 1.0, 1.0, 1.0, 1.0, 10)

    await collector_main.persist_bars(storage, pub, [bar])

    assert any(
        lvl == "CRITICAL" and "bar persist/publish failed" in m
        for lvl, m in alerts_seen
    )


async def test_stream_handler_skips_unparsable_message_without_raising(monkeypatch):
    import trading.collector.main as collector_main

    alerts_seen = []
    monkeypatch.setattr(
        collector_main,
        "alert",
        lambda level, msg, **f: alerts_seen.append((level, msg)),
    )
    monkeypatch.setattr(
        collector_main,
        "parse_interval_message",
        MagicMock(side_effect=ValueError("bad payload")),
    )

    wd = MagicMock()
    handler = collector_main.make_stream_message_handler(wd, MagicMock(), MagicMock())

    handler({"DataType": "X", "Content": "{{{"})

    wd.beat.assert_not_called()
    assert any(
        lvl == "WARN" and "failed to parse stream message" in m for lvl, m in alerts_seen
    )


async def test_collector_stops_cleanly_when_stop_event_set(cfg, monkeypatch):
    """SIGTERM -> stop_event set -> feed.stop() + pub.close() phải được gọi,
    housekeeping_loop phải dừng. Test phần logic, không gửi signal thật."""
    import asyncio
    from dataclasses import replace

    import trading.collector.main as collector_main

    # ISO-1: DB RIÊNG (trading_test) — fixture cfg dung dsn 'localhost' ->
    # Windows resolve ::1 -> psycopg treo, nen thay bang TEST_DSN
    from tests.conftest import TEST_DSN

    cfg = replace(cfg, db_dsn=TEST_DSN)

    class FakePub:
        def __init__(self):
            self.close_called = False

        async def connect(self):
            pass

        async def close(self):
            self.close_called = True

        async def publish(self, bar):
            pass

    class FakeFeed:
        def __init__(self):
            self.stop_called = False

        def start(self):
            pass

        async def stop(self):
            self.stop_called = True

    fake_pub = FakePub()
    fake_feed = FakeFeed()

    async def fake_backfill(storage, client, symbols, today):
        return {}

    monkeypatch.setattr(collector_main, "BarPublisher", lambda *a, **k: fake_pub)
    monkeypatch.setattr(collector_main, "SSIFeed", lambda *a, **k: fake_feed)
    monkeypatch.setattr(collector_main, "run_backfill", fake_backfill)
    monkeypatch.setattr(collector_main, "alert", lambda *a, **k: None)

    stop_event = asyncio.Event()
    task = asyncio.create_task(collector_main.run(cfg, stop_event=stop_event))
    await asyncio.sleep(0.2)  # để run() khởi động xong
    stop_event.set()
    await asyncio.wait_for(task, timeout=15)

    assert fake_feed.stop_called, "feed.stop() phai duoc goi khi dung"
    assert fake_pub.close_called, "pub.close() phai duoc goi khi dung"


async def test_housekeeping_loop_runs_no_tick_after_stop_event(cfg, monkeypatch):
    """Bug đo thật: wait_for(stop_event.wait(), timeout) trả về BÌNH THƯỜNG
    (không ném TimeoutError) khi stop được set giữa lúc chờ -> rơi thẳng xuống
    housekeeping_tick — chạy thêm 1 tick (có thể là EOD backfill job SSI dài)
    ngay lúc đang tắt máy. Phải break TRƯỚC khi tick."""
    import asyncio

    import trading.collector.main as collector_main

    ticks = []

    async def fake_tick(cfg, storage, wd, state):
        ticks.append(1)

    monkeypatch.setattr(collector_main, "housekeeping_tick", fake_tick)
    monkeypatch.setattr(collector_main, "alert", lambda *a, **k: None)

    stop_event = asyncio.Event()
    # set cờ GIỮA lúc wait_for đang chờ (loop đã vào vòng) — đúng kịch bản
    # bug: wait_for trả về BÌNH THƯỜNG khi stop set, rơi thẳng xuống tick
    task = asyncio.create_task(
        collector_main.housekeeping_loop(
            cfg, object(), object(), sleep_seconds=30.0, stop_event=stop_event
        )
    )
    await asyncio.sleep(0.2)  # loop đã vào wait_for(30s)
    stop_event.set()
    await asyncio.wait_for(task, timeout=5)

    assert ticks == [], (
        f"khong duoc chay tick nao sau khi co lenh dung, thuc te {len(ticks)}"
    )
