"""Unit tests cho BarLatch (trading/collector/latch.py) — Brief đợt 26 Task 1.6 / Brief đợt 27 Task 2.

1. Ba snapshot cùng khung -> offer trả None cả 3 lần.
2. Snapshot thứ tư sang khung mới -> trả về bar của khung cũ, và giá trị bằng snapshot thứ 3.
3. Snapshot đến muộn (ts < khung đang mở) -> trả None, khung đang mở không đổi, alert WARN.
4. flush_due trước hạn -> rỗng; sau ts + interval + grace -> trả đúng bar đó, gọi lần 2 trả rỗng.
5. flush_all trả mọi khung đang mở của nhiều mã cùng lúc.
6. Snapshot muộn sau khi flush_due -> không bị phát lại khi khung mới tới.
7. Snapshot muộn sau khi flush_all -> bỏ qua, không bị coi là khung mới đang mở.
8. Khung mới hơn sau khi chốt -> vẫn được nhận bình thường.
"""

from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.collector.latch import BarLatch
from trading.models import Bar


def test_latch_same_frame_snapshots_return_none():
    """1. Ba snapshot cùng khung -> offer trả None cả ba lần."""
    latch = BarLatch(interval_seconds=300, grace_seconds=60)
    t0 = datetime(2026, 9, 10, 9, 30, tzinfo=TZ)

    b1 = Bar("SSI", t0, 30.0, 30.5, 29.8, 30.2, 1000)
    b2 = Bar("SSI", t0, 30.0, 30.8, 29.8, 30.6, 5000)
    b3 = Bar("SSI", t0, 30.0, 31.0, 29.7, 30.9, 12000)

    assert latch.offer(b1) is None
    assert latch.offer(b2) is None
    assert latch.offer(b3) is None


def test_latch_new_frame_closes_previous_with_latest_snapshot_values():
    """2. Snapshot thứ tư sang khung mới -> trả về bar của khung cũ mang giá trị
    của snapshot thứ ba (snapshot cuối cùng của khung đó).
    """
    latch = BarLatch(interval_seconds=300, grace_seconds=60)
    t0 = datetime(2026, 9, 10, 9, 30, tzinfo=TZ)
    t1 = datetime(2026, 9, 10, 9, 35, tzinfo=TZ)

    b1 = Bar("SSI", t0, 30.0, 30.5, 29.8, 30.2, 1000)
    b2 = Bar("SSI", t0, 30.0, 30.8, 29.8, 30.6, 5000)
    b3 = Bar("SSI", t0, 30.0, 31.0, 29.7, 30.9, 12000)
    b4 = Bar("SSI", t1, 31.0, 31.2, 30.8, 31.1, 500)

    latch.offer(b1)
    latch.offer(b2)
    latch.offer(b3)
    closed = latch.offer(b4)

    assert closed is not None
    assert closed.symbol == "SSI"
    assert closed.ts == t0
    assert closed.open == 30.0
    assert closed.high == 31.0
    assert closed.low == 29.7
    assert closed.close == 30.9
    assert closed.volume == 12000


def test_latch_late_snapshot_skips_without_corrupting_open_frame(monkeypatch):
    """3. Snapshot đến muộn (ts < khung đang mở) -> trả None, khung đang mở không đổi, alert WARN."""
    alerts = []
    import trading.collector.latch as latch_module

    monkeypatch.setattr(latch_module, "alert", lambda lvl, msg, **k: alerts.append((lvl, msg, k)))

    latch = BarLatch(interval_seconds=300, grace_seconds=60)
    t0 = datetime(2026, 9, 10, 9, 30, tzinfo=TZ)
    t1 = datetime(2026, 9, 10, 9, 35, tzinfo=TZ)
    t_past = datetime(2026, 9, 10, 9, 25, tzinfo=TZ)

    b0 = Bar("SSI", t0, 30.0, 30.5, 29.8, 30.2, 1000)
    b1 = Bar("SSI", t1, 31.0, 31.2, 30.8, 31.1, 500)
    b_late = Bar("SSI", t_past, 29.0, 29.5, 28.8, 29.2, 800)

    latch.offer(b0)
    latch.offer(b1)

    res = latch.offer(b_late)
    assert res is None
    assert len(alerts) == 1
    assert alerts[0][0] == "WARN"
    assert "out-of-order" in alerts[0][1]

    # Khung đang mở vẫn là b1 (t1)
    assert latch._current_bars["SSI"].ts == t1
    assert latch._current_bars["SSI"].close == 31.1


def test_latch_flush_due_before_and_after_deadline():
    """4. flush_due trước hạn -> rỗng; sau ts + interval + grace -> trả đúng bar đó,
    và gọi lần hai trả rỗng (không chốt 2 lần).
    """
    latch = BarLatch(interval_seconds=300, grace_seconds=60)
    t0 = datetime(2026, 9, 10, 14, 45, tzinfo=TZ)
    b = Bar("VCB", t0, 90.0, 91.0, 89.5, 90.5, 50000)
    latch.offer(b)

    # Trước hạn: 14:45 + 300s + 60s = 14:51:00
    now_before = t0 + timedelta(seconds=359)  # 14:50:59
    assert latch.flush_due(now_before) == []

    # Sau hạn: 14:51:01
    now_after = t0 + timedelta(seconds=361)
    due = latch.flush_due(now_after)
    assert len(due) == 1
    assert due[0].symbol == "VCB"
    assert due[0].ts == t0
    assert due[0].close == 90.5

    # Gọi lần hai: rỗng (đã chốt, không lặp lại)
    assert latch.flush_due(now_after) == []


def test_latch_flush_all_multiple_symbols():
    """5. flush_all trả mọi khung đang mở của nhiều mã cùng lúc."""
    latch = BarLatch(interval_seconds=300, grace_seconds=60)
    t0 = datetime(2026, 9, 10, 14, 45, tzinfo=TZ)

    b_vcb = Bar("VCB", t0, 90.0, 91.0, 89.5, 90.5, 50000)
    b_ssi = Bar("SSI", t0, 30.0, 30.5, 29.8, 30.2, 20000)
    b_hpg = Bar("HPG", t0, 25.0, 25.5, 24.8, 25.2, 80000)

    latch.offer(b_vcb)
    latch.offer(b_ssi)
    latch.offer(b_hpg)

    flushed = latch.flush_all()
    assert len(flushed) == 3
    flushed_symbols = {b.symbol for b in flushed}
    assert flushed_symbols == {"VCB", "SSI", "HPG"}

    # Sau flush_all, latch rỗng hoàn toàn
    assert latch.flush_all() == []


def test_late_snapshot_after_flush_due_not_republished_on_next_frame():
    """6. Snapshot muộn sau khi flush_due chốt -> bỏ qua, không bị phát lại lần 2 khi khung mới tới."""
    latch = BarLatch(interval_seconds=300, grace_seconds=60)
    t0 = datetime(2026, 9, 10, 9, 45, tzinfo=TZ)
    t1 = datetime(2026, 9, 10, 9, 50, tzinfo=TZ)

    b1 = Bar("AAA", t0, 100.0, 102.0, 99.0, 101.0, 1000)
    latch.offer(b1)

    # flush_due chốt khung 09:45
    due = latch.flush_due(t0 + timedelta(seconds=370))
    assert len(due) == 1
    assert due[0].ts == t0
    assert due[0].close == 101.0

    # Snapshot muộn của chính khung 09:45 tới (vd SSI gửi sót snapshot 105.0)
    b1_late = Bar("AAA", t0, 100.0, 106.0, 99.0, 105.0, 5000)
    res_late = latch.offer(b1_late)
    assert res_late is None

    # Khung 09:50 tới -> chỉ ghi nhận 09:50, KHÔNG trả về 09:45 lần thứ 2
    b2 = Bar("AAA", t1, 105.0, 106.0, 104.0, 105.5, 2000)
    res_new = latch.offer(b2)
    assert res_new is None


def test_late_snapshot_after_flush_all_ignored():
    """7. Snapshot muộn sau khi flush_all -> bỏ qua."""
    latch = BarLatch(interval_seconds=300, grace_seconds=60)
    t0 = datetime(2026, 9, 10, 14, 45, tzinfo=TZ)
    t1 = datetime(2026, 9, 10, 14, 50, tzinfo=TZ)

    b1 = Bar("AAA", t0, 100.0, 102.0, 99.0, 101.0, 1000)
    latch.offer(b1)
    flushed = latch.flush_all()
    assert len(flushed) == 1

    # Snapshot muộn của t0
    b1_late = Bar("AAA", t0, 100.0, 103.0, 99.0, 102.0, 2000)
    assert latch.offer(b1_late) is None

    # Khung mới t1
    b2 = Bar("AAA", t1, 102.0, 103.0, 101.0, 102.5, 1500)
    assert latch.offer(b2) is None


def test_newer_frame_after_closed_accepted_normally():
    """8. Khung mới hơn sau khi chốt vẫn được nhận và chốt bình thường."""
    latch = BarLatch(interval_seconds=300, grace_seconds=60)
    t0 = datetime(2026, 9, 10, 9, 45, tzinfo=TZ)
    t1 = datetime(2026, 9, 10, 9, 50, tzinfo=TZ)
    t2 = datetime(2026, 9, 10, 9, 55, tzinfo=TZ)

    b1 = Bar("AAA", t0, 100.0, 101.0, 99.0, 100.5, 1000)
    latch.offer(b1)
    due = latch.flush_due(t0 + timedelta(seconds=370))
    assert len(due) == 1

    # Khung t1 tới
    b2 = Bar("AAA", t1, 100.5, 102.0, 100.0, 101.5, 2000)
    assert latch.offer(b2) is None

    # Khung t2 tới -> chốt khung t1
    b3 = Bar("AAA", t2, 101.5, 103.0, 101.0, 102.0, 3000)
    closed = latch.offer(b3)
    assert closed is not None
    assert closed.ts == t1
    assert closed.close == 101.5


# ============ Brief đợt 44 Task 1: Snapshot Counting & Silence Alarm Tests ============


def test_latch_three_snapshots_closed_reports_count_three():
    """Brief 44 Tiêu chí 2: Ba snapshot vào cùng một bucket, bucket đóng -> snapshot_count = 3."""
    latch = BarLatch(interval_seconds=300, grace_seconds=60)
    t0 = datetime(2026, 9, 10, 9, 30, tzinfo=TZ)
    t1 = datetime(2026, 9, 10, 9, 35, tzinfo=TZ)

    b1 = Bar("SSI", t0, 30.0, 30.5, 29.8, 30.2, 1000)
    b2 = Bar("SSI", t0, 30.0, 30.8, 29.8, 30.6, 5000)
    b3 = Bar("SSI", t0, 30.0, 31.0, 29.7, 30.9, 12000)
    b4 = Bar("SSI", t1, 31.0, 31.2, 30.8, 31.1, 500)

    latch.offer(b1)
    latch.offer(b2)
    latch.offer(b3)
    closed = latch.offer(b4)

    assert closed is not None
    assert closed.symbol == "SSI"
    assert closed.ts == t0
    assert getattr(closed, "snapshot_count", None) == 3


def test_latch_flush_due_reports_correct_snapshot_count():
    """Brief 44 Tiêu chí 3: Bucket đóng bằng flush_due cũng trả đúng số đếm snapshot."""
    latch = BarLatch(interval_seconds=300, grace_seconds=60)
    t0 = datetime(2026, 9, 10, 14, 45, tzinfo=TZ)

    b1 = Bar("VCB", t0, 90.0, 90.5, 89.8, 90.2, 10000)
    b2 = Bar("VCB", t0, 90.0, 90.8, 89.8, 90.4, 30000)
    b3 = Bar("VCB", t0, 90.0, 91.0, 89.5, 90.5, 50000)

    latch.offer(b1)
    latch.offer(b2)
    latch.offer(b3)

    # Sau hạn grace: 14:45 + 300s + 60s = 14:51:00 -> 14:51:05
    now_after = t0 + timedelta(seconds=365)
    due = latch.flush_due(now_after)

    assert len(due) == 1
    assert due[0].symbol == "VCB"
    assert due[0].ts == t0
    assert due[0].close == 90.5
    assert getattr(due[0], "snapshot_count", None) == 3


def test_latch_snapshot_count_resets_on_new_bucket():
    """Brief 44 Tiêu chí 4: Số đếm reset khi sang bucket mới — bucket thứ hai không cộng dồn bucket thứ nhất."""
    latch = BarLatch(interval_seconds=300, grace_seconds=60)
    t0 = datetime(2026, 9, 10, 9, 30, tzinfo=TZ)
    t1 = datetime(2026, 9, 10, 9, 35, tzinfo=TZ)
    t2 = datetime(2026, 9, 10, 9, 40, tzinfo=TZ)

    # Khung t0: 3 snapshot
    b0_1 = Bar("SSI", t0, 30.0, 30.5, 29.8, 30.2, 1000)
    b0_2 = Bar("SSI", t0, 30.0, 30.8, 29.8, 30.6, 5000)
    b0_3 = Bar("SSI", t0, 30.0, 31.0, 29.7, 30.9, 12000)

    latch.offer(b0_1)
    latch.offer(b0_2)
    latch.offer(b0_3)

    # Khung t1: snapshot đầu tiên tới -> chốt khung t0
    b1_1 = Bar("SSI", t1, 31.0, 31.2, 30.8, 31.1, 500)
    closed_t0 = latch.offer(b1_1)
    assert closed_t0 is not None
    assert getattr(closed_t0, "snapshot_count", None) == 3

    # Khung t1: nhận thêm snapshot thứ hai
    b1_2 = Bar("SSI", t1, 31.0, 31.5, 30.8, 31.3, 1500)
    assert latch.offer(b1_2) is None

    # Khung t2: snapshot đầu tiên tới -> chốt khung t1
    b2_1 = Bar("SSI", t2, 31.5, 31.8, 31.2, 31.6, 800)
    closed_t1 = latch.offer(b2_1)
    assert closed_t1 is not None
    assert closed_t1.ts == t1
    # Số đếm của khung t1 phải là 2, KHÔNG cộng dồn 3 của khung t0 (không thành 5)
    assert getattr(closed_t1, "snapshot_count", None) == 2


async def test_latch_close_behavior_unchanged_dot36_scenario(monkeypatch):
    """Brief 44 Tiêu chí 5: Hành vi đóng nến không đổi — dựng lại đúng kịch bản test đợt 36
    (ba snapshot khung A, một snapshot khung B) và khẳng định pub.publish vẫn được gọi đúng một lần,
    với đúng giá trị cũ, và alert 'bars closed' kèm snapshots=[3].
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    import trading.collector.main as collector_main

    alerts_seen = []
    monkeypatch.setattr(
        collector_main,
        "alert",
        lambda level, msg, **kwargs: alerts_seen.append((level, msg, kwargs)),
    )

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

    # pub.publish ĐÚNG 1 LẦN với đúng giá trị cũ
    assert pub.publish.call_count == 1, f"pub.publish phai duoc goi dung 1 lan, thuc te={pub.publish.call_count}"
    published_bar = pub.publish.call_args[0][0]
    assert published_bar.symbol == "VCB"
    assert published_bar.ts == t0
    assert published_bar.close == 90.9
    assert published_bar.volume == 12000

    # Kiểm tra alert 'bars closed' có chứa snapshots=[3]
    bars_closed_alerts = [
        (lvl, msg, kw)
        for lvl, msg, kw in alerts_seen
        if lvl == "INFO" and msg == "bars closed"
    ]
    assert len(bars_closed_alerts) == 1
    closed_alert_kw = bars_closed_alerts[0][2]
    assert closed_alert_kw["symbols"] == ["VCB"]
    assert closed_alert_kw["snapshots"] == [3]


async def test_silence_alarm_in_trading_hours_and_outside(monkeypatch):
    """Brief 44 Tiêu chí 6: Test chuông im lặng:
    - Giả lập 120s không snapshot trong giờ -> phát đúng một WARN.
    - Lặp thêm tick nữa -> không phát thêm.
    - Ngoài giờ -> không phát.
    - Nhận snapshot mới -> sau 120s im lặng tiếp theo -> phát lại đúng 1 WARN cho đợt mới.
    """
    import time
    from unittest.mock import MagicMock

    import trading.collector.main as collector_main
    from trading.collector.main import HousekeepingState, housekeeping_tick
    from trading.config import Config

    cfg = Config(
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

    alerts_seen = []
    monkeypatch.setattr(
        collector_main,
        "alert",
        lambda level, msg, **kwargs: alerts_seen.append((level, msg, kwargs)),
    )

    storage = MagicMock()
    wd = MagicMock()
    latch = BarLatch(interval_seconds=300, grace_seconds=60)
    state = HousekeepingState()

    fake_mono = 1000.0
    fake_wall = datetime(2026, 9, 10, 10, 0, 0, tzinfo=TZ)  # Thứ 5, 10:00:00 (trong phiên)

    monkeypatch.setattr(time, "monotonic", lambda: fake_mono)

    class _FrozenDt:
        def __init__(self, dt_val):
            self._dt = dt_val

        def now(self, tz=None):
            return self._dt

    frozen_dt = _FrozenDt(fake_wall)
    monkeypatch.setattr(collector_main, "datetime", frozen_dt)

    # Tick 1 (t=0s trong phiên): Khởi tạo, chưa có 120s trôi qua
    await housekeeping_tick(cfg, storage, wd, state, latch=latch)
    silent_warns = [
        (lvl, msg, kw)
        for lvl, msg, kw in alerts_seen
        if lvl == "WARN" and "khong nhan snapshot nao" in msg
    ]
    assert len(silent_warns) == 0

    # Tick 2 (t=120s trong phiên, không snapshot nào tới): Phát đúng 1 WARN
    fake_mono += 120.0
    frozen_dt._dt = fake_wall + timedelta(seconds=120)
    await housekeeping_tick(cfg, storage, wd, state, latch=latch)

    silent_warns = [
        (lvl, msg, kw)
        for lvl, msg, kw in alerts_seen
        if lvl == "WARN" and "khong nhan snapshot nao" in msg
    ]
    assert len(silent_warns) == 1
    assert silent_warns[0][2]["seconds"] == 120
    assert silent_warns[0][2]["last_snapshot_ts"] is None

    # Tick 3 (t=150s trong phiên, vẫn chưa có snapshot): KHÔNG phát thêm (không spam)
    fake_mono += 30.0
    frozen_dt._dt = fake_wall + timedelta(seconds=150)
    await housekeeping_tick(cfg, storage, wd, state, latch=latch)

    silent_warns = [
        (lvl, msg, kw)
        for lvl, msg, kw in alerts_seen
        if lvl == "WARN" and "khong nhan snapshot nao" in msg
    ]
    assert len(silent_warns) == 1, "Khong duoc spam chuong im lang moi tick"

    # Nhận một snapshot mới
    b_snap = Bar("VCB", datetime(2026, 9, 10, 10, 0, tzinfo=TZ), 90.0, 90.5, 89.8, 90.2, 1000)
    latch.offer(b_snap)

    # Tick 4 (30s sau snapshot mới): Không alert vì mới 30s
    fake_mono += 30.0
    frozen_dt._dt = fake_wall + timedelta(seconds=180)
    await housekeeping_tick(cfg, storage, wd, state, latch=latch)
    silent_warns = [
        (lvl, msg, kw)
        for lvl, msg, kw in alerts_seen
        if lvl == "WARN" and "khong nhan snapshot nao" in msg
    ]
    assert len(silent_warns) == 1

    # Tick 5 (125s sau snapshot mới): Lại im lặng 125s -> phát thêm 1 WARN cho đợt mới
    fake_mono += 95.0  # tổng từ snapshot: 30 + 95 = 125s
    frozen_dt._dt = fake_wall + timedelta(seconds=275)
    await housekeeping_tick(cfg, storage, wd, state, latch=latch)
    silent_warns = [
        (lvl, msg, kw)
        for lvl, msg, kw in alerts_seen
        if lvl == "WARN" and "khong nhan snapshot nao" in msg
    ]
    assert len(silent_warns) == 2
    assert silent_warns[1][2]["seconds"] == 125
    assert silent_warns[1][2]["last_snapshot_ts"] == b_snap.ts.isoformat()

    # Ngoài giờ giao dịch: 16:00:00 (phiên đã đóng)
    outside_wall = datetime(2026, 9, 10, 16, 0, 0, tzinfo=TZ)
    frozen_dt._dt = outside_wall
    fake_mono += 500.0  # trôi qua 500s ngoài giờ
    await housekeeping_tick(cfg, storage, wd, state, latch=latch)

    silent_warns = [
        (lvl, msg, kw)
        for lvl, msg, kw in alerts_seen
        if lvl == "WARN" and "khong nhan snapshot nao" in msg
    ]
    assert len(silent_warns) == 2, "Ngoai gio giao dich KHONG duoc phat chuong im lang"
