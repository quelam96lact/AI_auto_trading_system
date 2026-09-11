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


# ============ Brief 31 Task 1 & 2: persist_bars publish-first & lag_ms ============


async def test_persist_bars_calls_publish_before_write_bars(monkeypatch):
    """1. Test: pub.publish được gọi TRƯỚC storage.write_bars."""
    from unittest.mock import AsyncMock

    import trading.collector.main as collector_main
    from trading.models import Bar

    call_order = []
    storage = MagicMock()
    storage.write_bars.side_effect = lambda bars: call_order.append("write_bars")
    pub = MagicMock()
    pub.publish = AsyncMock(side_effect=lambda b: call_order.append("publish"))

    bar = Bar("VCB", datetime(2026, 7, 15, 9, 5, tzinfo=TZ), 1.0, 1.0, 1.0, 1.0, 10)
    await collector_main.persist_bars(storage, pub, [bar])

    assert call_order == ["publish", "write_bars"]


async def test_persist_bars_alerts_critical_when_publish_fails(monkeypatch):
    """2. Test: publish ném lỗi -> alert CRITICAL, nội dung nói bar chưa tới engine."""
    from unittest.mock import AsyncMock

    import trading.collector.main as collector_main
    from trading.models import Bar

    alerts_seen = []
    monkeypatch.setattr(
        collector_main,
        "alert",
        lambda level, msg, **f: alerts_seen.append((level, msg, f)),
    )

    storage = MagicMock()
    pub = MagicMock()
    pub.publish = AsyncMock(side_effect=RuntimeError("nats disconnected"))
    bar = Bar("VCB", datetime(2026, 7, 15, 9, 5, tzinfo=TZ), 1.0, 1.0, 1.0, 1.0, 10)

    await collector_main.persist_bars(storage, pub, [bar])

    storage.write_bars.assert_not_called()
    assert any(
        lvl == "CRITICAL" and "bar publish failed" in m and "not delivered to engine" in m
        for lvl, m, _ in alerts_seen
    )


async def test_persist_bars_alerts_critical_when_db_write_fails_after_publish(monkeypatch):
    """3. Test: publish thành công nhưng write_bars ném lỗi -> alert CRITICAL,
    nói bar đã tới engine, DB thiếu; và KHÔNG dùng chữ 'dropped'."""
    from unittest.mock import AsyncMock

    import trading.collector.main as collector_main
    from trading.models import Bar

    alerts_seen = []
    monkeypatch.setattr(
        collector_main,
        "alert",
        lambda level, msg, **f: alerts_seen.append((level, msg, f)),
    )

    storage = MagicMock()
    storage.write_bars.side_effect = OSError("connection refused")
    pub = MagicMock()
    pub.publish = AsyncMock()
    bar = Bar("VCB", datetime(2026, 7, 15, 9, 5, tzinfo=TZ), 1.0, 1.0, 1.0, 1.0, 10)

    await collector_main.persist_bars(storage, pub, [bar])

    pub.publish.assert_called_once_with(bar)
    critical_alerts = [
        (lvl, m, f) for lvl, m, f in alerts_seen if lvl == "CRITICAL"
    ]
    assert len(critical_alerts) == 1
    _lvl, msg, _ = critical_alerts[0]
    assert "bar db persist failed" in msg
    assert "already published to engine" in msg
    assert "dropped" not in msg


async def test_persist_bars_lag_ms_in_alert(monkeypatch):
    """Task 2: lag_ms xuất hiện trong payload alert và có giá trị đúng."""
    from unittest.mock import AsyncMock

    import trading.collector.main as collector_main
    from trading.models import Bar

    alerts_seen = []
    monkeypatch.setattr(
        collector_main,
        "alert",
        lambda level, msg, **f: alerts_seen.append((level, msg, f)),
    )

    # Bar lúc 09:00 (đóng khung lúc 09:05). Giả lập now là 09:05:00.150 (+150ms)
    frozen_now = datetime(2026, 7, 15, 9, 5, 0, 150000, tzinfo=TZ)
    monkeypatch.setattr(
        collector_main,
        "datetime",
        _FrozenDatetime(frozen_now),
    )

    storage = MagicMock()
    pub = MagicMock()
    pub.publish = AsyncMock()
    bar = Bar("VCB", datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 1.0, 1.0, 1.0, 1.0, 10)

    await collector_main.persist_bars(storage, pub, [bar])

    info_alerts = [
        (lvl, m, f) for lvl, m, f in alerts_seen if lvl == "INFO" and m == "bars closed"
    ]
    assert len(info_alerts) == 1
    assert "lag_ms" in info_alerts[0][2]
    assert info_alerts[0][2]["lag_ms"] == 150.0


async def test_persist_bars_negative_lag_ms_not_clamped(monkeypatch):
    """Task 2: đồng hồ lệch cho giá trị âm -> vẫn ghi ra, không bị kẹp về 0."""
    from unittest.mock import AsyncMock

    import trading.collector.main as collector_main
    from trading.models import Bar

    alerts_seen = []
    monkeypatch.setattr(
        collector_main,
        "alert",
        lambda level, msg, **f: alerts_seen.append((level, msg, f)),
    )

    # Bar lúc 09:00 (đóng khung lúc 09:05). Giả lập now là 09:04:59.500 (-500ms)
    frozen_now = datetime(2026, 7, 15, 9, 4, 59, 500000, tzinfo=TZ)
    monkeypatch.setattr(
        collector_main,
        "datetime",
        _FrozenDatetime(frozen_now),
    )

    storage = MagicMock()
    pub = MagicMock()
    pub.publish = AsyncMock()
    bar = Bar("VCB", datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 1.0, 1.0, 1.0, 1.0, 10)

    await collector_main.persist_bars(storage, pub, [bar])

    info_alerts = [
        (lvl, m, f) for lvl, m, f in alerts_seen if lvl == "INFO" and m == "bars closed"
    ]
    assert len(info_alerts) == 1
    assert info_alerts[0][2]["lag_ms"] == -500.0


async def test_persist_bars_custom_interval_lag_ms(monkeypatch):
    """Brief 32 Task 1: latch dựng với khoảng 1 phút -> lag_ms tính theo 1 phút, KHÔNG theo 5."""
    from unittest.mock import AsyncMock

    import trading.collector.main as collector_main
    from trading.models import Bar

    alerts_seen = []
    monkeypatch.setattr(
        collector_main,
        "alert",
        lambda level, msg, **f: alerts_seen.append((level, msg, f)),
    )

    # Bar lúc 09:00 (nếu interval 1 phút thì đóng khung lúc 09:01). Giả lập now là 09:01:00.200 (+200ms)
    frozen_now = datetime(2026, 7, 15, 9, 1, 0, 200000, tzinfo=TZ)
    monkeypatch.setattr(
        collector_main,
        "datetime",
        _FrozenDatetime(frozen_now),
    )

    storage = MagicMock()
    pub = MagicMock()
    pub.publish = AsyncMock()
    bar = Bar("VCB", datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 1.0, 1.0, 1.0, 1.0, 10)

    # Truyền interval=timedelta(minutes=1)
    await collector_main.persist_bars(storage, pub, [bar], interval=timedelta(minutes=1))

    info_alerts = [
        (lvl, m, f) for lvl, m, f in alerts_seen if lvl == "INFO" and m == "bars closed"
    ]
    assert len(info_alerts) == 1
    assert "lag_ms" in info_alerts[0][2]
    assert info_alerts[0][2]["lag_ms"] == 200.0


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


# ============ Brief đợt 26 Task 1.6: BarLatch wiring test ============


async def test_stream_handler_with_latch_publishes_only_closed_bar(monkeypatch):
    """Brief đợt 26 Tiêu chí 6:
    Bơm 3 snapshot khung A rồi 1 snapshot khung B qua on_stream_message:
    → pub.publish được gọi ĐÚNG 1 LẦN, với bar khung A mang giá trị của snapshot thứ 3.
    → storage.write_bars nhận đầy đủ snapshot từng lần.
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    import trading.collector.main as collector_main
    from trading.collector.latch import BarLatch
    from trading.models import Bar

    t0 = datetime(2026, 9, 10, 9, 30, tzinfo=TZ)
    t1 = datetime(2026, 9, 10, 9, 35, tzinfo=TZ)

    bars_sequence = [
        Bar("VCB", t0, 90.0, 90.5, 89.8, 90.2, 1000),
        Bar("VCB", t0, 90.0, 90.8, 89.8, 90.4, 5000),
        Bar("VCB", t0, 90.0, 91.0, 89.7, 90.9, 12000),  # snapshot 3 của khung A
        Bar("VCB", t1, 91.0, 91.5, 90.8, 91.2, 2000),   # snapshot 1 của khung B
    ]

    seq_idx = 0

    def fake_parse(msg):
        nonlocal seq_idx
        b = bars_sequence[seq_idx]
        seq_idx += 1
        return b

    monkeypatch.setattr(collector_main, "parse_interval_message", fake_parse)
    monkeypatch.setattr(collector_main, "alert", lambda *a, **k: None)

    wd = MagicMock()
    storage = MagicMock()
    pub = MagicMock()
    pub.publish = AsyncMock()

    persist_tasks = set()
    latch = BarLatch(interval_seconds=300, grace_seconds=60)
    handler = collector_main.make_stream_message_handler(
        wd, storage, pub, persist_tasks=persist_tasks, latch=latch
    )

    # Gửi 3 message khung A
    handler({"dummy": 1})
    handler({"dummy": 2})
    handler({"dummy": 3})

    # Gửi 1 message khung B
    handler({"dummy": 4})

    # Chờ các task async hoàn thành
    if persist_tasks:
        await asyncio.gather(*list(persist_tasks))

    # pub.publish ĐÚNG 1 LẦN
    assert pub.publish.call_count == 1, f"pub.publish phai duoc goi dung 1 lan, thuc te={pub.publish.call_count}"
    published_bar = pub.publish.call_args[0][0]
    assert published_bar.symbol == "VCB"
    assert published_bar.ts == t0
    assert published_bar.close == 90.9
    assert published_bar.volume == 12000

    # storage.write_bars được gọi cho cả 4 snapshot + 1 closed bar
    assert storage.write_bars.call_count >= 4


# ============ Brief đợt 35 Task 1: Sleep / clock drift detection ============


async def test_housekeeping_tick_first_tick_no_alert(cfg):
    """Tiêu chí 4: Tick đầu tiên (chưa có mốc trước) -> không cảnh báo, không nổ."""
    import trading.collector.main as collector_main

    storage = MagicMock()
    wd = MagicMock()
    state = HousekeepingState()

    alerts = []
    collector_main.alert = lambda level, msg, **kw: alerts.append((level, msg, kw))

    await housekeeping_tick(cfg, storage, wd, state)

    critical_alerts = [a for a in alerts if a[0] == "CRITICAL"]
    assert len(critical_alerts) == 0
    assert state.last_monotonic is not None
    assert state.last_wall is not None


async def test_housekeeping_tick_normal_drift_no_alert(cfg, monkeypatch):
    """Tiêu chí 1: Hai tick liên tiếp bình thường (drift ~0) -> không cảnh báo."""
    import trading.collector.main as collector_main

    storage = MagicMock()
    wd = MagicMock()

    t0_wall = datetime(2026, 9, 11, 10, 0, 0, tzinfo=TZ)
    t1_wall = datetime(2026, 9, 11, 10, 0, 30, tzinfo=TZ)

    state = HousekeepingState(
        last_monotonic=100.0,
        last_wall=t0_wall,
    )

    monkeypatch.setattr(collector_main.time, "monotonic", lambda: 130.0)
    monkeypatch.setattr(collector_main, "datetime", _FrozenDatetime(t1_wall))

    alerts = []
    monkeypatch.setattr(collector_main, "alert", lambda level, msg, **kw: alerts.append((level, msg, kw)))

    await housekeeping_tick(cfg, storage, wd, state)

    critical_alerts = [a for a in alerts if a[0] == "CRITICAL"]
    assert len(critical_alerts) == 0


async def test_housekeeping_tick_large_drift_in_trading_hours_alerts_critical(cfg, monkeypatch):
    """Tiêu chí 2: Δwall = 5400s còn Δmonotonic = 30s, trong giờ giao dịch -> có CRITICAL, ghi rõ số giây và 'trong giờ giao dịch'."""
    import trading.collector.main as collector_main

    storage = MagicMock()
    wd = MagicMock()

    t0_wall = datetime(2026, 9, 11, 10, 0, 0, tzinfo=TZ)
    t1_wall = datetime(2026, 9, 11, 11, 30, 0, tzinfo=TZ)

    state = HousekeepingState(
        last_monotonic=100.0,
        last_wall=t0_wall,
    )

    monkeypatch.setattr(collector_main.time, "monotonic", lambda: 130.0)
    monkeypatch.setattr(collector_main, "datetime", _FrozenDatetime(t1_wall))

    alerts = []
    monkeypatch.setattr(collector_main, "alert", lambda level, msg, **kw: alerts.append((level, msg, kw)))

    await housekeeping_tick(cfg, storage, wd, state)

    critical_alerts = [a for a in alerts if a[0] == "CRITICAL"]
    assert len(critical_alerts) == 1
    _level, msg, kw = critical_alerts[0]
    assert _level == "CRITICAL"
    assert "5370" in msg or kw.get("dead_seconds") == 5370.0
    assert "trong giờ giao dịch" in msg
    assert kw.get("in_trading_hours") is True


async def test_housekeeping_tick_large_drift_outside_trading_hours_alerts_outside(cfg, monkeypatch):
    """Tiêu chí 3: Cùng drift lớn nhưng ngoài giờ giao dịch -> vẫn cảnh báo nhưng ghi rõ 'ngoài giờ giao dịch'."""
    import trading.collector.main as collector_main

    storage = MagicMock()
    wd = MagicMock()

    t0_wall = datetime(2026, 9, 11, 20, 0, 0, tzinfo=TZ)
    t1_wall = datetime(2026, 9, 11, 21, 30, 0, tzinfo=TZ)

    state = HousekeepingState(
        last_monotonic=100.0,
        last_wall=t0_wall,
    )

    monkeypatch.setattr(collector_main.time, "monotonic", lambda: 130.0)
    monkeypatch.setattr(collector_main, "datetime", _FrozenDatetime(t1_wall))

    alerts = []
    monkeypatch.setattr(collector_main, "alert", lambda level, msg, **kw: alerts.append((level, msg, kw)))

    await housekeeping_tick(cfg, storage, wd, state)

    critical_alerts = [a for a in alerts if a[0] == "CRITICAL"]
    assert len(critical_alerts) == 1
    _level, msg, kw = critical_alerts[0]
    assert _level == "CRITICAL"
    assert "5370" in msg or kw.get("dead_seconds") == 5370.0
    assert "ngoài giờ giao dịch" in msg
    assert kw.get("in_trading_hours") is False


# ============ Brief đợt 36 Task 2: Late snapshot observation ============


async def test_stream_handler_snapshot_during_open_frame_no_late_log(monkeypatch):
    """Tiêu chí 1: Snapshot tới khi khung còn mở (late_ms <= 0) -> không ghi log late snapshot."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    import trading.collector.main as collector_main
    from trading.collector.latch import BarLatch
    from trading.models import Bar

    # Khung 09:30, đóng lúc 09:35
    t0 = datetime(2026, 9, 14, 9, 30, tzinfo=TZ)
    # Thời điểm nhận: 09:32 (còn mở, late_ms = -180,000 ms)
    t_now = datetime(2026, 9, 14, 9, 32, tzinfo=TZ)
    monkeypatch.setattr(collector_main, "datetime", _FrozenDatetime(t_now))

    bar = Bar("VCB", t0, 90.0, 90.5, 89.8, 90.2, 1000)
    monkeypatch.setattr(collector_main, "parse_interval_message", lambda msg: bar)

    alerts = []
    monkeypatch.setattr(collector_main, "alert", lambda level, msg, **kw: alerts.append((level, msg, kw)))

    wd = MagicMock()
    storage = MagicMock()
    pub = MagicMock()
    pub.publish = AsyncMock()
    persist_tasks = set()
    latch = BarLatch(interval_seconds=300, grace_seconds=60)

    handler = collector_main.make_stream_message_handler(
        wd, storage, pub, persist_tasks=persist_tasks, latch=latch
    )
    handler({"dummy": 1})

    if persist_tasks:
        await asyncio.gather(*list(persist_tasks))

    late_logs = [a for a in alerts if a[1] == "late snapshot"]
    assert len(late_logs) == 0


async def test_stream_handler_snapshot_after_frame_close_logs_late_snapshot(monkeypatch):
    """Tiêu chí 2: Snapshot tới sau mốc đóng khung (late_ms > 0) -> có log late snapshot với late_ms đúng."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    import trading.collector.main as collector_main
    from trading.collector.latch import BarLatch
    from trading.models import Bar

    # Khung 09:30, đóng lúc 09:35 (300s interval)
    t0 = datetime(2026, 9, 14, 9, 30, tzinfo=TZ)
    # Thời điểm nhận: 09:35:03.500 (+3.5s = +3500ms sau mốc đóng khung)
    t_now = datetime(2026, 9, 14, 9, 35, 3, 500000, tzinfo=TZ)
    monkeypatch.setattr(collector_main, "datetime", _FrozenDatetime(t_now))

    bar = Bar("VCB", t0, 90.0, 90.5, 89.8, 90.2, 1000)
    monkeypatch.setattr(collector_main, "parse_interval_message", lambda msg: bar)

    alerts = []
    monkeypatch.setattr(collector_main, "alert", lambda level, msg, **kw: alerts.append((level, msg, kw)))

    wd = MagicMock()
    storage = MagicMock()
    pub = MagicMock()
    pub.publish = AsyncMock()
    persist_tasks = set()
    latch = BarLatch(interval_seconds=300, grace_seconds=60)

    handler = collector_main.make_stream_message_handler(
        wd, storage, pub, persist_tasks=persist_tasks, latch=latch
    )
    handler({"dummy": 1})

    if persist_tasks:
        await asyncio.gather(*list(persist_tasks))

    late_logs = [a for a in alerts if a[1] == "late snapshot"]
    assert len(late_logs) == 1
    level, msg, kw = late_logs[0]
    assert level == "INFO"
    assert msg == "late snapshot"
    assert kw.get("symbol") == "VCB"
    assert kw.get("bar_ts") == t0.isoformat()
    assert kw.get("late_ms") == 3500.0



