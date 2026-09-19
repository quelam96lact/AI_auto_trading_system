"""Unit tests cho chiến lược Buy-and-Hold theo nhịp thị trường (Brief 61).

Bốn test bắt buộc:
1. test_khong_doi_khi_regime_khong_doi: Chuỗi regime toàn RISK_ON -> giống hệt B&H thuần.
2. test_mua_ban_dung_gia_va_phi: Dựng tay 1 mã, 1 lần đổi trạng thái -> khớp chính xác công thức B&H.
3. test_khong_nhin_trom_tuong_lai: Thêm regime ngày d+1 không làm đổi quyết định của ngày d.
4. test_max_drawdown_dung: Dựng tay chuỗi vốn 100 -> 150 -> 80 -> 120 -> đúng -46.67%.
"""

from datetime import UTC, date, datetime

import pytest

from scripts.measure_regime_hold import (
    compute_max_drawdown,
    simulate_symbol_regime_hold,
)
from trading.models import Bar
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS


def _make_bar(d: date, open_p: float, close_p: float, symbol: str = "TEST") -> Bar:
    dt = datetime(d.year, d.month, d.day, 15, 0, tzinfo=UTC)
    return Bar(
        symbol=symbol,
        ts=dt,
        open=open_p,
        high=max(open_p, close_p),
        low=min(open_p, close_p),
        close=close_p,
        volume=100_000.0,
    )


def test_khong_doi_khi_regime_khong_doi():
    """Test 1: Chuỗi regime toàn RISK_ON -> Không có giao dịch nào ngoài lần mua đầu và đóng cuối kỳ."""
    dates = [date(2023, 1, i) for i in range(1, 6)]
    bars = [
        _make_bar(dates[0], 10.0, 10.5),
        _make_bar(dates[1], 10.5, 11.0),
        _make_bar(dates[2], 11.0, 11.5),
        _make_bar(dates[3], 11.5, 12.0),
        _make_bar(dates[4], 12.0, 12.5),
    ]
    prior_regime = {d: "RISK_ON" for d in dates}

    res = simulate_symbol_regime_hold(bars, prior_regime, capital=1_000_000_000.0)

    # 1 lần mua ở bar 0, 1 lần đóng ở bar cuối
    assert res["buy_trades"] == 1
    assert res["sell_trades"] == 1
    assert pytest.approx(res["pnl"], rel=1e-6) == res["bh_pnl"]


def test_mua_ban_dung_gia_va_phi():
    """Test 2: Dựng tay 1 mã, đổi trạng thái -> Kiểm giá mua/bán và phí khớp chính xác công thức."""
    dates = [date(2023, 1, i) for i in range(1, 5)]
    bars = [
        _make_bar(dates[0], 10.0, 10.0),  # Ngày 1: HOLD -> Mua ở Open=10.0
        _make_bar(dates[1], 12.0, 12.0),  # Ngày 2: CASH -> Bán ở Open=12.0
        _make_bar(dates[2], 11.0, 11.0),  # Ngày 3: HOLD -> Mua ở Open=11.0
        _make_bar(dates[3], 15.0, 16.0),  # Ngày 4: Cuối kỳ -> Đóng ở Close=16.0
    ]

    prior_regime = {
        dates[0]: "RISK_ON",
        dates[1]: "RISK_OFF",
        dates[2]: "RISK_ON",
        dates[3]: "RISK_ON",
    }

    capital = 1_000_000_000.0
    slip = SLIPPAGE_BPS / 10_000
    fee = FEE_RATE
    tax = SELL_TAX_RATE
    lot_size = 100

    # Nhịp 1: mua 10.0, bán 12.0
    buy_p1 = 10.0 * (1 + slip)
    qty1 = int(capital // (buy_p1 * (1 + fee)))
    qty1 = (qty1 // lot_size) * lot_size
    cost1 = qty1 * buy_p1 * (1 + fee)
    cash1 = capital - cost1

    sell_p1 = 12.0 * (1 - slip)
    proceeds1 = qty1 * sell_p1 * (1 - fee - tax)
    cash2 = cash1 + proceeds1

    # Nhịp 2: mua lại từ cash2 ở 11.0, đóng ở Close=16.0 ngày cuối kỳ
    buy_p2 = 11.0 * (1 + slip)
    qty2 = int(cash2 // (buy_p2 * (1 + fee)))
    qty2 = (qty2 // lot_size) * lot_size
    cost2 = qty2 * buy_p2 * (1 + fee)
    cash3 = cash2 - cost2

    sell_p2 = 16.0 * (1 - slip)
    proceeds2 = qty2 * sell_p2 * (1 - fee - tax)
    cash4 = cash3 + proceeds2

    expected_pnl = cash4 - capital

    res = simulate_symbol_regime_hold(bars, prior_regime, capital=capital, lot_size=lot_size)

    assert res["min_cash_seen"] >= 0.0
    assert res["buy_trades"] == 2
    assert res["sell_trades"] == 2
    assert pytest.approx(res["pnl"], rel=1e-6) == expected_pnl


def test_khong_nhin_trom_tuong_lai():
    """Test 3: Thêm regime của ngày d+1 không làm đổi quyết định giao dịch của ngày d."""
    dates = [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3)]
    bars = [
        _make_bar(dates[0], 10.0, 10.0),
        _make_bar(dates[1], 11.0, 11.0),
        _make_bar(dates[2], 12.0, 15.0),
    ]

    # Bộ 1: Chỉ có dữ liệu đến ngày 3
    prior_regime_1 = {
        dates[0]: "RISK_ON",
        dates[1]: "RISK_ON",
        dates[2]: "NEUTRAL",
    }
    res1 = simulate_symbol_regime_hold(bars, prior_regime_1)

    # Bộ 2: Thêm ngày tương lai d+1 = ngày 4 (RISK_OFF)
    future_date = date(2023, 1, 4)
    prior_regime_2 = dict(prior_regime_1)
    prior_regime_2[future_date] = "RISK_OFF"
    res2 = simulate_symbol_regime_hold(bars, prior_regime_2)

    # Quyết định và kết quả trong 3 ngày đầu phải giống nhau tuyệt đối
    assert res1["pnl"] == res2["pnl"]
    assert res1["buy_trades"] == res2["buy_trades"]
    assert res1["sell_trades"] == res2["sell_trades"]
    for d in dates:
        assert res1["daily_equity"][d] == res2["daily_equity"][d]


def test_max_drawdown_dung():
    """Test 4: Chuỗi vốn [100, 150, 80, 120] -> Max drawdown đúng -46.67%."""
    series = [100.0, 150.0, 80.0, 120.0]
    mdd = compute_max_drawdown(series)
    expected = (80.0 - 150.0) / 150.0  # -70 / 150 = -0.466666...
    assert pytest.approx(mdd, rel=1e-4) == expected
    assert f"{mdd:.2%}" == "-46.67%"


def test_cash_khong_bao_gio_am():
    """Test 5 (bắt buộc, Brief 62): Dựng kịch bản audit (bán thấp, mua lại cao gấp 3 lần),
    khẳng định cash không âm ở bất kỳ thời điểm nào trong suốt mô phỏng.
    """
    capital = 1_000_000.0
    dates = [
        date(2026, 1, 1),
        date(2026, 1, 4),
        date(2026, 1, 7),
        date(2026, 1, 10),
    ]
    bars = [
        _make_bar(dates[0], 10.0, 10.0),  # Mua ở 10.0
        _make_bar(dates[1], 10.0, 10.0),  # Bán ở 10.0
        _make_bar(dates[2], 30.0, 30.0),  # Mua lại ở 30.0 (giá cao gấp 3 lần)
        _make_bar(dates[3], 35.0, 35.0),  # Cuối kỳ đóng ở 35.0
    ]
    prior_regime = {
        dates[0]: "RISK_ON",
        dates[1]: "RISK_OFF",
        dates[2]: "RISK_ON",
        dates[3]: "RISK_ON",
    }
    res = simulate_symbol_regime_hold(bars, prior_regime, capital=capital)
    assert res["min_cash_seen"] >= 0.0
    assert res["buy_trades"] == 2
    assert res["sell_trades"] == 2

