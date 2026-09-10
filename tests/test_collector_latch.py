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
