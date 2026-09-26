"""Test hàm thuần cho đợt 105: order flow (delta, buy_ratio, delta_z) và funding_cost.

Chỉ test hàm THUẦN, không kết nối DB: mọi đầu vào được dựng bằng số tay.
"""

from datetime import UTC, datetime, timedelta

import pytest

from scripts.measure_perp_orderflow import (
    DELTA_Z_WINDOW,
    FLOW_BUY_RATIO_LONG_MIN,
    FLOW_BUY_RATIO_SHORT_MAX,
    FLOW_DELTA_Z_MIN,
    FlowRow,
    buy_ratio,
    delta,
    delta_z_series,
    filter_module_a,
    filter_module_b,
    flow_valid,
    funding_cost,
)

BASE_TS = datetime(2020, 1, 1, 0, 0, tzinfo=UTC)


def _row(
    idx: int,
    volume: float,
    taker_buy_volume: float,
    quote_volume: float,
    taker_buy_quote_volume: float,
) -> FlowRow:
    """Dựng FlowRow tại BASE_TS + idx giờ."""
    return FlowRow(
        ts=BASE_TS + timedelta(hours=idx),
        volume=volume,
        quote_volume=quote_volume,
        taker_buy_volume=taker_buy_volume,
        taker_buy_quote_volume=taker_buy_quote_volume,
    )


def _synthetic_rows(n: int, vol: float = 100.0, tbv: float = 60.0) -> list[FlowRow]:
    """Chuỗi n nến; tbv thay đổi nhẹ theo idx để delta có phương sai."""
    rows = []
    for i in range(n):
        buy = tbv + (i % 7) - 3  # 4..10 -> delta biến thiên
        rows.append(_row(i, vol, buy, vol * 10.0, buy * 10.0))
    return rows


# ---------------------------------------------------------------------------
# 0. Hằng số phải đúng nguyên văn §2.2 / §2.4 của brief
# ---------------------------------------------------------------------------


def test_constants_match_brief():
    """Ngưỡng nằm trong code, không truyền từ ngoài (đúng §2.2/§2.4)."""
    assert DELTA_Z_WINDOW == 240
    assert FLOW_BUY_RATIO_LONG_MIN == 0.55
    assert FLOW_BUY_RATIO_SHORT_MAX == 0.45
    assert FLOW_DELTA_Z_MIN == 0.5


# ---------------------------------------------------------------------------
# 1. delta và buy_ratio khớp số tính tay (§4.4)
# ---------------------------------------------------------------------------


def test_delta_and_buy_ratio_manual_two_bars():
    """Bar 1: volume 10, taker_buy 6 -> delta = 2*6-10 = +2; quote 100, tbq 57 -> 0.57.
    Bar 2: volume 10, taker_buy 3 -> delta = 2*3-10 = -4; quote 100, tbq 45 -> 0.45.
    """
    r1 = _row(0, 10.0, 6.0, 100.0, 57.0)
    r2 = _row(1, 10.0, 3.0, 100.0, 45.0)

    assert delta(r1) == pytest.approx(2.0)
    assert buy_ratio(r1) == pytest.approx(0.57)
    assert delta(r2) == pytest.approx(-4.0)
    assert buy_ratio(r2) == pytest.approx(0.45)


def test_buy_ratio_none_when_quote_volume_zero():
    """quote_volume = 0 -> không tính được tỷ lệ -> None (không trả 0 giả)."""
    r = _row(0, 10.0, 6.0, 0.0, 0.0)
    assert buy_ratio(r) is None


def test_flow_valid_false_on_zero_volume():
    """Nến volume 0 -> flow không hợp lệ; filter A trả False (không vào lệnh)."""
    r = _row(0, 0.0, 0.0, 100.0, 0.0)
    assert flow_valid(r) is False
    assert filter_module_a(r, "LONG") is False
    assert filter_module_a(r, "SHORT") is False


# ---------------------------------------------------------------------------
# 2. delta_z: chỉ dùng quá khứ (§4.4) — chống nhìn trộm tương lai
# ---------------------------------------------------------------------------


def test_delta_z_ignores_bar_t_plus_1():
    """Sửa nến t+1 thì delta_z tại t PHẢI không đổi (chống nhìn trộm tương lai)."""
    rows = _synthetic_rows(300)
    z_before = delta_z_series(rows)
    t = 250

    modified = list(rows)
    modified[t + 1] = _row(t + 1, 100.0, 1.0, 1000.0, 10.0)  # đổi mạnh nến t+1
    z_after = delta_z_series(modified)

    assert z_after[rows[t].ts] == pytest.approx(z_before[rows[t].ts])
    assert z_after[rows[t].ts] is not None


def test_delta_z_numerator_is_bar_t_window_excludes_t():
    """z_t = (delta_t - mean(delta[t-240..t-1])) / std(delta[t-240..t-1]) — tính tay.

    Bắt cả hai lỗi: tử số lệch một nến (delta_{t-1}, lỗi bản đầu đợt 105) và cửa sổ gồm nến t.
    """
    import statistics

    rows = _synthetic_rows(300)
    t = 250
    rows[t] = _row(t, 100.0, 99.0, 1000.0, 990.0)  # delta_t = +98, khác hẳn cửa sổ
    deltas = [delta(r) for r in rows]
    window = deltas[t - DELTA_Z_WINDOW : t]
    expected = (deltas[t] - statistics.fmean(window)) / statistics.stdev(window)

    assert delta_z_series(rows)[rows[t].ts] == pytest.approx(expected)


def test_delta_z_none_before_window_and_when_std_zero():
    """Chưa đủ 240 nến -> None; std = 0 -> None (không chia cho 0, không bịa số)."""
    rows = _synthetic_rows(300)
    z = delta_z_series(rows)
    assert z[rows[0].ts] is None
    assert z[rows[DELTA_Z_WINDOW - 1].ts] is None
    assert z[rows[DELTA_Z_WINDOW].ts] is not None

    flat = _synthetic_rows(300)
    for i in range(len(flat)):
        flat[i] = _row(i, 100.0, 50.0, 1000.0, 500.0)  # delta luôn = 0 -> std = 0
    z_flat = delta_z_series(flat)
    assert z_flat[flat[DELTA_Z_WINDOW].ts] is None


# ---------------------------------------------------------------------------
# 3. Ngưỡng filter theo §2.2 (A) và §2.4 (B)
# ---------------------------------------------------------------------------


def test_filter_a_boundary_buy_ratio():
    """buy_ratio đúng 0.55 -> LONG hợp lệ; 0.5499 -> không. Đối xứng cho SHORT."""
    long_ok = _row(0, 100.0, 60.0, 100.0, 55.0)
    assert buy_ratio(long_ok) == pytest.approx(0.55)
    assert filter_module_a(long_ok, "LONG") is True

    long_fail = _row(0, 100.0, 60.0, 100.0, 54.99)
    assert filter_module_a(long_fail, "LONG") is False

    short_ok = _row(0, 100.0, 40.0, 100.0, 45.0)
    assert filter_module_a(short_ok, "SHORT") is True

    short_fail = _row(0, 100.0, 40.0, 100.0, 45.01)
    assert filter_module_a(short_fail, "SHORT") is False


def test_filter_a_requires_delta_sign():
    """A còn cần delta đúng dấu: buy_ratio 0.60 nhưng delta âm -> LONG bị chặn."""
    r = _row(0, 100.0, 40.0, 100.0, 60.0)  # delta = 2*40-100 = -20, ratio 0.60
    assert delta(r) < 0
    assert filter_module_a(r, "LONG") is False


def test_filter_b_boundary_delta_z():
    """B dùng delta_z: +0.5 / -0.5 hợp lệ, 0.4999 / -0.4999 không; None -> False."""
    assert filter_module_b(0.5, "LONG") is True
    assert filter_module_b(0.4999, "LONG") is False
    assert filter_module_b(-0.5, "SHORT") is True
    assert filter_module_b(-0.4999, "SHORT") is False
    assert filter_module_b(None, "LONG") is False
    assert filter_module_b(None, "SHORT") is False


# ---------------------------------------------------------------------------
# 4. funding_cost (§2)
# ---------------------------------------------------------------------------


def test_funding_cost_long_pays_positive_rate_short_receives():
    """LONG trả khi rate dương, SHORT nhận; notional 1000, rate 0.0001 -> 0.1 USDT."""
    entry = BASE_TS + timedelta(hours=9)
    exit_ = BASE_TS + timedelta(hours=11)
    rates = [(BASE_TS + timedelta(hours=10), 0.0001)]

    long_cost = funding_cost(entry, exit_, "LONG", 1000.0, rates)
    short_cost = funding_cost(entry, exit_, "SHORT", 1000.0, rates)

    assert long_cost == pytest.approx(0.1)
    assert short_cost == pytest.approx(-0.1)


def test_funding_cost_excludes_entry_includes_exit():
    """Mốc đúng bằng entry_ts KHÔNG tính; đúng bằng exit_ts CÓ tính."""
    entry = BASE_TS + timedelta(hours=10)
    exit_ = BASE_TS + timedelta(hours=15)
    rates = [
        (BASE_TS + timedelta(hours=10), 0.001),  # = entry -> bỏ
        (BASE_TS + timedelta(hours=15), 0.001),  # = exit  -> tính
    ]
    assert funding_cost(entry, exit_, "LONG", 1000.0, rates) == pytest.approx(1.0)


def test_funding_cost_truncates_milliseconds():
    """funding_time lệch mili-giây phải được cắt về giây trước khi so sánh."""
    entry = BASE_TS + timedelta(hours=12)
    exit_ = BASE_TS + timedelta(hours=16)
    rates = [(BASE_TS + timedelta(hours=16, milliseconds=1), 0.001)]
    # 16:00:00.001 -> cắt thành 16:00:00 = exit -> vẫn tính
    assert funding_cost(entry, exit_, "LONG", 1000.0, rates) == pytest.approx(1.0)

    rates_late = [(BASE_TS + timedelta(hours=16, seconds=1), 0.001)]
    # 16:00:01 nằm ngoài (entry, exit] -> không tính
    assert funding_cost(entry, exit_, "LONG", 1000.0, rates_late) == pytest.approx(0.0)
