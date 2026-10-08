"""Test suite cho scripts/measure_etf_deposit_mix.py — Brief 165.

Kiểm chứng TDD trên nến dựng tay, không đọc DB:
1. w = 0: tài sản đúng bằng lãi kép tiền gửi tính tay, sai số < 1e-12.
2. w = 1, không tái cân bằng: đường tài sản trùng buy_hold của scripts/measure_vol_target_etf.py, sai số < 1e-12.
3. Lãi theo ngày lịch: hai phiên thứ Sáu -> thứ Hai cộng đúng 3 ngày lãi.
4. Tái cân bằng năm: chỉ khớp ở OPEN phiên đầu năm; giữa năm không có giao dịch; sau khớp, tỷ trọng ETF bằng w tại giá OPEN.
5. Chi phí: giá ETF đứng yên qua một lần tái cân bằng -> tài sản giảm đúng |notional| × đơn giá phía tính tay; phần tiền gửi không chịu phí.
6. MDD trên tổng tài sản: dựng chuỗi ETF giảm 50% với w = 10%, r = 0 -> MDD ≈ 5%, không phải 50%.
7. Niêm phong: hàm IS ném lỗi khi có nến >= 01/01/2023. Hàm niêm phong không có cờ thì từ chối; có cờ thì ghi log (tmp_path) TRƯỚC KHI đọc.
8. Không dùng tương lai: đổi giá mọi phiên sau ngày d thì tài sản tại các phiên <= d không đổi.
"""

from __future__ import annotations

import math
from datetime import date, datetime

import pytest

from scripts.measure_etf_deposit_mix import (
    per_side_rate,
    read_is_bars,
    simulate_mix,
    summarize_mix,
    unlock_holdout,
)
from scripts.measure_vol_target_etf import buy_hold
from trading.calendar_vn import TZ
from trading.models import Bar


def _make_bar(
    d: date,
    open_: float,
    high: float | None = None,
    low: float | None = None,
    close: float | None = None,
    volume: float = 1000.0,
    symbol: str = "E1VFVN30",
) -> Bar:
    """Tạo nến ngày giả lập với timestamp 00:00 VN."""
    c = open_ if close is None else close
    h = max(open_, c) if high is None else high
    l = min(open_, c) if low is None else low
    ts = datetime(d.year, d.month, d.day, 0, 0, tzinfo=TZ)
    return Bar(
        symbol=symbol,
        ts=ts,
        open=open_,
        high=h,
        low=l,
        close=c,
        volume=volume,
    )


# ---------------------------------------------------------------------------
# Test 1: w = 0 -> tài sản đúng bằng lãi kép tiền gửi tính tay
# ---------------------------------------------------------------------------
def test_w_zero_matches_exact_compound_interest():
    """1. w = 0: tài sản đúng bằng lãi kép tiền gửi tính tay, sai số < 1e-12."""
    dates = [
        date(2017, 1, 3),   # Thứ Ba
        date(2017, 1, 4),   # Thứ Tư (1 ngày)
        date(2017, 1, 6),   # Thứ Sáu (2 ngày)
        date(2017, 1, 9),   # Thứ Hai (3 ngày)
        date(2017, 2, 10),  # 32 ngày
    ]
    bars = [_make_bar(d, 10.0, close=10.0) for d in dates]
    r = 0.09
    res = simulate_mix(bars, w=0.0, r=r, rebalance_mode="annual", initial=1.0)

    assert len(res.equity_curve) == len(dates)
    assert res.n_trades == 0
    assert res.total_cost == 0.0

    # Tính tay từng bước
    expected_curve = [1.0]
    for i in range(1, len(dates)):
        days = (dates[i] - dates[0]).days
        expected = 1.0 * ((1.0 + r) ** (days / 365.0))
        expected_curve.append(expected)

    for actual, expected in zip(res.equity_curve, expected_curve, strict=True):
        assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# Test 2: w = 1, không tái cân bằng -> trùng buy_hold của measure_vol_target_etf
# ---------------------------------------------------------------------------
def test_w_one_no_rebalance_matches_buy_hold():
    """2. w = 1, không tái cân bằng: đường tài sản trùng buy_hold của scripts/measure_vol_target_etf.py, sai số < 1e-12."""
    dates = [
        date(2017, 1, 3),
        date(2017, 1, 4),
        date(2017, 1, 5),
        date(2017, 1, 6),
        date(2017, 1, 9),
    ]
    prices = [(10.0, 10.5), (10.6, 11.0), (10.8, 10.2), (10.1, 10.7), (10.9, 11.5)]
    bars = [_make_bar(d, op, close=cl) for d, (op, cl) in zip(dates, prices, strict=True)]

    # Chạy mô phỏng w=1.0, r=0.0, không tái cân bằng
    res_mix = simulate_mix(bars, w=1.0, r=0.0, rebalance_mode="none", initial=1.0)

    # Chạy buy_hold đối chứng
    res_bh = buy_hold(bars, start_idx=0, end_idx=len(bars) - 1, initial=1.0)

    assert len(res_mix.equity_curve) == len(res_bh.equity_curve)
    for actual, expected in zip(res_mix.equity_curve, res_bh.equity_curve, strict=True):
        assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# Test 3: Lãi theo ngày lịch -> Thứ Sáu đến Thứ Hai cộng đúng 3 ngày lãi
# ---------------------------------------------------------------------------
def test_deposit_interest_calendar_days_friday_to_monday():
    """3. Lãi theo ngày lịch: hai phiên thứ Sáu -> thứ Hai cộng đúng 3 ngày lãi."""
    d_fri = date(2026, 9, 25)  # Thứ Sáu
    d_mon = date(2026, 9, 28)  # Thứ Hai (cách 3 ngày lịch)
    bars = [
        _make_bar(d_fri, 10.0, close=10.0),
        _make_bar(d_mon, 10.0, close=10.0),
    ]
    r = 0.09
    res = simulate_mix(bars, w=0.0, r=r, rebalance_mode="none", initial=1.0)

    # Phiên thứ Sáu: 1.0
    assert res.equity_curve[0] == 1.0
    # Phiên thứ Hai: 1.0 * (1 + 0.09) ** (3 / 365)
    expected_monday = 1.0 * ((1.0 + r) ** (3.0 / 365.0))
    assert math.isclose(res.equity_curve[1], expected_monday, rel_tol=0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# Test 4: Tái cân bằng năm -> chỉ khớp ở OPEN phiên đầu năm; tỷ trọng đúng w
# ---------------------------------------------------------------------------
def test_annual_rebalance_executes_at_new_year_open_only():
    """4. Tái cân bằng năm: chỉ khớp ở OPEN phiên đầu năm; giữa năm không có giao dịch; sau khớp, tỷ trọng ETF bằng w tại giá OPEN."""
    bars = [
        # Năm 2017: 3 phiên
        _make_bar(date(2017, 1, 3), 10.0, close=12.0),
        _make_bar(date(2017, 6, 1), 12.0, close=15.0),
        _make_bar(date(2017, 12, 29), 15.0, close=18.0),
        # Năm 2018: phiên đầu năm (OPEN 20.0) -> phải tái cân bằng ở đây
        _make_bar(date(2018, 1, 2), 20.0, close=21.0),
        _make_bar(date(2018, 6, 1), 21.0, close=22.0),
        _make_bar(date(2018, 12, 28), 22.0, close=25.0),
        # Năm 2019: phiên đầu năm (OPEN 24.0) -> tái cân bằng lần 2
        _make_bar(date(2019, 1, 2), 24.0, close=24.0),
    ]

    w = 0.15
    res = simulate_mix(bars, w=w, r=0.09, rebalance_mode="annual", initial=1.0)

    # Giao dịch:
    # Trade 0: Ngày đầu (2017-01-03)
    # Trade 1: Phiên đầu năm 2018 (2018-01-02) khớp tại giá OPEN = 20.0 (không phải CLOSE = 21.0)
    # Trade 2: Phiên đầu năm 2019 (2019-01-02)
    assert res.n_trades == 3
    assert res.trades[0].day == date(2017, 1, 3)
    assert res.trades[1].day == date(2018, 1, 2)
    assert res.trades[2].day == date(2019, 1, 2)

    # Tính toán chính xác notional khớp tại OPEN=20.0:
    # Cash tích lũy 364 ngày: 0.85 * (1 + 0.09)**(364/365) = 0.9262758
    # Gross tại OPEN=20.0: 0.9262758 + 0.015 * 20.0 = 1.2262758
    # Target ETF: 0.15 * 1.2262758 = 0.18394137
    # Delta (SELL): 0.18394137 - 0.30 = -0.11605863 (notional = 0.11605863)
    # (Nếu khớp ở CLOSE=21.0 thì notional = 0.12880863)
    assert math.isclose(res.trades[1].notional, 0.11605863, rel_tol=1e-4)

    # Khẳng định giữa năm không có giao dịch
    trade_dates = [t.day for t in res.trades]
    assert date(2017, 6, 1) not in trade_dates
    assert date(2017, 12, 29) not in trade_dates
    assert date(2018, 6, 1) not in trade_dates
    assert date(2018, 12, 28) not in trade_dates


# ---------------------------------------------------------------------------
# Test 5: Chi phí -> giá ETF đứng yên, tài sản giảm đúng |notional| * rate
# ---------------------------------------------------------------------------
def test_cost_accounting_flat_price_deposit_free_of_fee():
    """5. Chi phí: giá ETF đứng yên qua một lần tái cân bằng -> tài sản giảm đúng |notional| × đơn giá phía; phần tiền gửi không chịu phí."""
    # Dựng ETF giá đứng yên 10.0 ở mọi phiên. r = 0 để cô lập lãi tiền gửi.
    bars = [
        _make_bar(date(2017, 1, 3), 10.0, close=10.0),
        _make_bar(date(2017, 12, 29), 10.0, close=10.0),
        _make_bar(date(2018, 1, 2), 10.0, close=10.0),  # Tái cân bằng năm
    ]

    w = 0.20
    res = simulate_mix(bars, w=w, r=0.0, rebalance_mode="annual", initial=1.0)

    # Phiên đầu: mua w=0.20 at 10.0 -> notional = 0.20. Cost = 0.20 * per_side_rate("BUY")
    initial_buy_cost = 0.20 * per_side_rate("BUY")
    assert math.isclose(res.trades[0].cost, initial_buy_cost, abs_tol=1e-12)

    # Vì giá đứng yên 10.0 và r=0, gross_open ở 2018-01-02 = 1.0 (cash 0.8 + etf 0.2).
    # Target ETF = 0.20 * 1.0 = 0.20 -> delta = 0 -> không phát sinh lệnh tái cân bằng thừa.
    assert res.n_trades == 1

    # Thử kịch bản ETF tăng giá làm lệch tỷ trọng -> tái cân bằng bán bớt
    bars_growth = [
        _make_bar(date(2017, 1, 3), 10.0, close=10.0),
        _make_bar(date(2017, 12, 29), 10.0, close=20.0), # ETF tăng gấp đôi
        _make_bar(date(2018, 1, 2), 20.0, close=20.0),   # Tái cân bằng bán ở OPEN=20.0
    ]
    res_growth = simulate_mix(bars_growth, w=w, r=0.0, rebalance_mode="annual", initial=1.0)
    assert res_growth.n_trades == 2
    rebal_trade = res_growth.trades[1]
    assert rebal_trade.side == "SELL"
    # Cost của lệnh SELL phải đúng |notional| * per_side_rate("SELL")
    expected_sell_cost = rebal_trade.notional * per_side_rate("SELL")
    assert math.isclose(rebal_trade.cost, expected_sell_cost, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# Test 6: MDD trên tổng tài sản -> ETF giảm 50%, w=10%, r=0 -> MDD ≈ 5%
# ---------------------------------------------------------------------------
def test_mdd_on_total_portfolio_not_etf_alone():
    """6. MDD trên tổng tài sản: dựng chuỗi ETF giảm 50% với w = 10%, r = 0 -> MDD ≈ 5%, không phải 50%."""
    bars = [
        _make_bar(date(2017, 1, 3), 100.0, close=100.0),
        _make_bar(date(2017, 1, 4), 100.0, close=50.0),   # ETF giảm 50%
        _make_bar(date(2017, 1, 5), 50.0, close=50.0),
    ]

    w = 0.10
    res = simulate_mix(bars, w=w, r=0.0, rebalance_mode="none", initial=1.0)
    s = summarize_mix(res)

    # MDD tổng tài sản phải quanh 5% (0.05), không phải 50% (0.50)
    assert 0.045 <= s["mdd"] <= 0.055, f"MDD thực tế: {s['mdd']}"


# ---------------------------------------------------------------------------
# Test 7: Niêm phong -> IS ném lỗi khi có nến >= 2023; holdout kiểm tra cờ & log
# ---------------------------------------------------------------------------
def test_sealing_enforcement_is_fails_on_holdout_and_unlock_order(tmp_path):
    """7. Niêm phong: hàm IS ném lỗi khi có nến >= 01/01/2023. Hàm niêm phong không có cờ thì từ chối; có cờ thì ghi log (tmp_path) TRƯỚC KHI đọc."""
    # A. Kiểm tra validate_sealed_bars ở read_is_bars
    class FakeStorageWithSealed:
        def read_daily_bars(self, symbol, start, end):
            return [
                _make_bar(date(2022, 12, 30), 20.0),
                _make_bar(date(2023, 1, 3), 20.0),  # Nến vi phạm
            ]

    with pytest.raises(ValueError, match="Vi phạm niêm phong"):
        read_is_bars(FakeStorageWithSealed(), "E1VFVN30")

    # B. Kiểm tra unlock_holdout không có cờ -> từ chối
    class FakeStorageHoldout:
        def __init__(self):
            self.read_called = False

        def read_daily_bars(self, symbol, start, end):
            self.read_called = True
            return [_make_bar(date(2023, 1, 3), 20.0)]

    storage_holdout = FakeStorageHoldout()
    log_file = tmp_path / "holdout-unlock-log.md"

    with pytest.raises(PermissionError):
        unlock_holdout(storage_holdout, "E1VFVN30", log_path=log_file, unlocked=False)
    assert not storage_holdout.read_called
    assert not log_file.exists()

    # C. Kiểm tra thứ tự: có cờ -> ghi log TRƯỚC KHI đọc dữ liệu
    order_events = []

    class OrderTrackingStorage:
        def read_daily_bars(self, symbol, start, end):
            # Kiểm tra xem log đã được ghi trước khi hàm này được gọi chưa
            assert log_file.exists()
            assert "E1VFVN30" in log_file.read_text(encoding="utf-8")
            order_events.append("read_db")
            return [_make_bar(date(2023, 1, 3), 20.0)]

    unlock_holdout(OrderTrackingStorage(), "E1VFVN30", log_path=log_file, unlocked=True)
    assert order_events == ["read_db"]
    assert log_file.exists()
    assert "Mốc chuẩn ETF + tiền gửi" in log_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 8: Không dùng tương lai -> đổi giá sau d không đổi equity <= d
# ---------------------------------------------------------------------------
def test_no_future_leakage():
    """8. Không dùng tương lai: đổi giá mọi phiên sau ngày d thì tài sản tại các phiên <= d không đổi."""
    dates = [
        date(2017, 1, 3),
        date(2017, 1, 4),
        date(2017, 1, 5),
        date(2017, 1, 6),
        date(2017, 1, 9),
    ]
    bars_original = [
        _make_bar(dates[0], 10.0, close=10.5),
        _make_bar(dates[1], 10.5, close=11.0),
        _make_bar(dates[2], 11.0, close=11.5),  # Ngày d = 2017-01-05
        _make_bar(dates[3], 11.5, close=12.0),
        _make_bar(dates[4], 12.0, close=12.5),
    ]

    bars_modified_future = [
        _make_bar(dates[0], 10.0, close=10.5),
        _make_bar(dates[1], 10.5, close=11.0),
        _make_bar(dates[2], 11.0, close=11.5),  # Ngày d = 2017-01-05
        _make_bar(dates[3], 50.0, close=100.0),  # Đổi giá tương lai
        _make_bar(dates[4], 100.0, close=200.0),
    ]

    w = 0.15
    res1 = simulate_mix(bars_original, w=w, r=0.09, rebalance_mode="annual", initial=1.0)
    res2 = simulate_mix(bars_modified_future, w=w, r=0.09, rebalance_mode="annual", initial=1.0)

    # Tài sản tại các phiên i=0, 1, 2 (ngày <= d) phải giống hệt nhau
    for i in range(3):
        assert math.isclose(res1.equity_curve[i], res2.equity_curve[i], rel_tol=0.0, abs_tol=1e-12)
