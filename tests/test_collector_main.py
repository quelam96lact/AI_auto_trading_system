from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from trading.calendar_vn import TZ
from trading.collector.main import (
    HousekeepingState,
    held_symbols_for_pricing,
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
        real_order_account="ACC",
    )


class _Pos:
    def __init__(self, qty):
        self.qty = qty


async def _noop_close():
    pass


class _FrozenDatetime:
    """Chỉ đóng băng datetime.now(TZ) trong module collector.main — nhánh EOD
    so sánh giờ thật, test không được phụ thuộc vào lúc nó chạy."""

    def __init__(self, frozen):
        self._frozen = frozen

    def now(self, tz=None):
        return self._frozen


def _storage_with_positions(by_account):
    st = MagicMock()
    st.read_real_positions.side_effect = lambda acc: {
        s: _Pos(q) for s, q in by_account.get(acc, {}).items()
    }
    return st


def test_held_symbols_for_pricing_unions_all_accounts(cfg):
    """MARGIN-2: lay ma dang giu cua MOI tai khoan trong ssi_equity_accounts,
    khong chi real_order_account — quyet dinh chon tai khoan CHUA chot, va NAV
    duoc tinh cho tung tai khoan."""
    from dataclasses import replace

    cfg = replace(cfg, symbols=["HII"], ssi_equity_accounts=["0434221", "0434226"])
    storage = _storage_with_positions(
        {"0434221": {"CAP": 100}, "0434226": {"HCM": 200, "TCX": 160}}
    )

    assert held_symbols_for_pricing(storage, cfg) == ["CAP", "HCM", "TCX"]


def test_held_symbols_for_pricing_excludes_configured_symbols(cfg):
    """Ma trong cfg.symbols da duoc backfill day du (ke ca intraday) o luot
    truoc — keo lai lan hai la thua."""
    from dataclasses import replace

    cfg = replace(cfg, symbols=["VCB", "HII"], ssi_equity_accounts=["0434226"])
    storage = _storage_with_positions({"0434226": {"VCB": 1500, "CAP": 100}})

    assert held_symbols_for_pricing(storage, cfg) == ["CAP"]


def test_held_symbols_for_pricing_deduplicates_across_accounts(cfg):
    """Cung mot ma giu o CA HAI tai khoan chi duoc keo MOT lan."""
    from dataclasses import replace

    cfg = replace(cfg, symbols=[], ssi_equity_accounts=["0434221", "0434226"])
    storage = _storage_with_positions(
        {"0434221": {"CAP": 100}, "0434226": {"CAP": 500}}
    )

    assert held_symbols_for_pricing(storage, cfg) == ["CAP"]


def test_held_symbols_for_pricing_skips_zero_quantity(cfg):
    """qty <= 0 khong phai vi the dang giu — compute_nav cung bo qua chung."""
    from dataclasses import replace
    cfg = replace(cfg, symbols=[], ssi_equity_accounts=["0434226"])
    storage = _storage_with_positions({"0434226": {"CAP": 0, "HCM": 200}})

    assert held_symbols_for_pricing(storage, cfg) == ["HCM"]


def test_held_symbols_for_pricing_isolates_failing_account(cfg):
    """SYNC-1: mot tai khoan doc loi khong duoc giet cac tai khoan con lai."""
    from dataclasses import replace

    cfg = replace(cfg, symbols=[], ssi_equity_accounts=["BAD", "0434226"])
    storage = MagicMock()

    def _read(acc):
        if acc == "BAD":
            raise RuntimeError("db blew up")
        return {"HCM": _Pos(200)}

    storage.read_real_positions.side_effect = _read

    assert held_symbols_for_pricing(storage, cfg) == ["HCM"]


async def test_eod_backfills_held_symbols_daily_only(cfg, monkeypatch):
    """MARGIN-2: sau luot backfill cho cfg.symbols, EOD phai keo THEM gia ngay
    cho ma dang nam giu — neu khong, NAV dinh gia chung bang bar cu dan (do
    that 14/08: CAP/HCM/SSI/TCX bar cuoi 06/08) va tut ra ngoai cua so 5 ngay."""
    from dataclasses import replace

    import trading.collector.main as collector_main

    cfg = replace(cfg, symbols=["HII"], ssi_equity_accounts=["0434226"])
    monkeypatch.setattr(collector_main, "alert", lambda *a, **k: None)
    monkeypatch.setattr(
        collector_main, "SSIRestClient", lambda *a, **k: MagicMock(close=_noop_close)
    )

    calls = []

    async def fake_run_backfill(storage, client, symbols, today, daily_only=False):
        calls.append((list(symbols), daily_only))
        return {}

    monkeypatch.setattr(collector_main, "run_backfill", fake_run_backfill)

    storage = _storage_with_positions({"0434226": {"CAP": 100, "HCM": 200}})
    state = HousekeepingState()
    state.last_account_sync = datetime.now(TZ)  # bo qua nhanh account sync
    monkeypatch.setattr(
        collector_main,
        "datetime",
        _FrozenDatetime(datetime(2026, 8, 14, 15, 10, tzinfo=TZ)),
    )

    await housekeeping_tick(cfg, storage, MagicMock(), state)

    assert calls == [
        (["HII"], False),
        (["CAP", "HCM"], True),
    ], "phai backfill cfg.symbols nhu cu, ROI keo daily_only cho ma dang giu"


async def test_eod_skips_second_backfill_when_nothing_held(cfg, monkeypatch):
    """Khong giu gi -> khong goi luot thu hai (khong ton loi goi API vo ich)."""
    from dataclasses import replace

    import trading.collector.main as collector_main

    cfg = replace(cfg, symbols=["HII"], ssi_equity_accounts=["0434226"])
    monkeypatch.setattr(collector_main, "alert", lambda *a, **k: None)
    monkeypatch.setattr(
        collector_main, "SSIRestClient", lambda *a, **k: MagicMock(close=_noop_close)
    )

    calls = []

    async def fake_run_backfill(storage, client, symbols, today, daily_only=False):
        calls.append((list(symbols), daily_only))
        return {}

    monkeypatch.setattr(collector_main, "run_backfill", fake_run_backfill)

    storage = _storage_with_positions({"0434226": {}})
    state = HousekeepingState()
    state.last_account_sync = datetime.now(TZ)
    monkeypatch.setattr(
        collector_main,
        "datetime",
        _FrozenDatetime(datetime(2026, 8, 14, 15, 10, tzinfo=TZ)),
    )

    await housekeeping_tick(cfg, storage, MagicMock(), state)

    assert calls == [(["HII"], False)]


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
        sum(
            1
            for lvl, m in alerts_seen
            if lvl == "WARN" and "housekeeping tick failed" in m
        )
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
    # WARM-1 Viec B: housekeeping truyen timeout=5 de that bai NHANH khi DB chet
    storage.beat.assert_called_once_with("collector", timeout=5)
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
        lvl == "WARN" and "failed to parse stream message" in m
        for lvl, m in alerts_seen
    )


@pytest.mark.integration  # DOC-1: test nay CHAM DB THAT (db_dsn=TEST_DSN) — can ha tang, khong phai unit; cac test con lai trong file nay la unit that
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

    assert (
        ticks == []
    ), f"khong duoc chay tick nao sau khi co lenh dung, thuc te {len(ticks)}"


# ============ Brief 2026-09-01 (dot 3) Task C: chuong khong keu suong ============


async def test_restart_feed_alerts_only_when_stream_actually_disconnected(monkeypatch):
    """Khi feed.restart() tra True (that su disconnect duoc) -> kêu WARN."""
    import trading.collector.main as collector_main

    alerts = []
    monkeypatch.setattr(collector_main, "alert", lambda level, msg, **k: alerts.append((level, msg)))

    class FakeFeed:
        async def restart(self):
            return True

    await collector_main._restart_feed_and_alert(FakeFeed())
    assert alerts == [("WARN", "feed stale, forcing reconnect")], f"thuc te: {alerts}"


async def test_restart_feed_silent_when_noop(monkeypatch):
    """Khi feed.restart() tra False (khong co stream de ngat — feed chua tung
    nối, dang trong backoff) -> KHONG kêu 'forcing reconnect' (H2: chuong mo
    ta hanh dong khong xay ra)."""
    import trading.collector.main as collector_main

    alerts = []
    monkeypatch.setattr(collector_main, "alert", lambda level, msg, **k: alerts.append((level, msg)))

    class FakeFeed:
        async def restart(self):
            return False

    await collector_main._restart_feed_and_alert(FakeFeed())
    assert alerts == [], f"restart no-op thi khong duoc kêu gi, thuc te: {alerts}"
