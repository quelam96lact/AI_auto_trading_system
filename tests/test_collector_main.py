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
