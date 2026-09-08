from datetime import date

import pytest

from trading.risk import RiskManager
from trading.strategy import Signal

TODAY = date(2026, 9, 9)


def test_fractional_risk_btc_500_usdt_reproduction():
    """Tiêu chí 2: Vốn 500 USDT, lot_size=0.0001, giá BTC 100k, ATR 1500 sinh qty > 0."""
    rm = RiskManager(capital=500.0, lot_size=0.0001, max_positions=1)
    sig = Signal("BTC-USDT", "BUY", 0.0001)
    sized = rm.approve_sized(
        sig,
        ref_price=100_000.0,
        atr=1500.0,
        positions={},
        daily_pnl=0.0,
        today=TODAY,
    )
    assert sized is not None, f"Bị từ chối: {rm.last_reject_reason}"
    assert sized.qty > 0
    assert sized.qty == pytest.approx(0.0010, rel=1e-6)
    assert isinstance(sized.qty, float)


def test_fractional_risk_20_pct_cap():
    """Tiêu chí 3: Trần 20% vẫn hiệu lực với số thực. capital=500, giá 125.977 => giá trị lệnh <= 100 USDT."""
    rm = RiskManager(capital=500.0, lot_size=0.0001, max_positions=1)
    sig = Signal("BTC-USDT", "BUY", 0.0001)
    # capital=500, max_order_value_pct=0.20 => trần 100 USDT
    # ref_price=125_977.0, atr=500 (nhỏ để qty_atr > qty_cap)
    sized = rm.approve_sized(
        sig,
        ref_price=125_977.0,
        atr=500.0,
        positions={},
        daily_pnl=0.0,
        today=TODAY,
    )
    assert sized is not None
    order_value = sized.qty * 125_977.0
    assert order_value <= 100.0 + 1e-9
    assert sized.qty == pytest.approx(0.0007, rel=1e-6)


def test_fractional_risk_exact_step_multiplier():
    """Tiêu chí 4: Bước khối lượng chính xác.
    Với lot_size=0.0001, mọi qty phải là bội đúng của 0.0001 kiểm bằng round(qty/0.0001)*0.0001 dung sai 1e-9."""
    rm = RiskManager(capital=500.0, lot_size=0.0001, max_positions=5)
    test_cases = [
        (60_000.0, 1_200.0),
        (125_977.0, 3_500.0),
        (2_500.0, 80.0),
        (95_432.1, 2_150.0),
        (45_000.0, 500.0),
    ]
    for price, atr in test_cases:
        sig = Signal("TEST-USDT", "BUY", 0.0001)
        sized = rm.approve_sized(
            sig,
            ref_price=price,
            atr=atr,
            positions={},
            daily_pnl=0.0,
            today=TODAY,
        )
        if sized is not None:
            expected_mult = round(sized.qty / 0.0001) * 0.0001
            assert abs(sized.qty - expected_mult) < 1e-9
            assert sized.qty * price <= rm.capital * rm.max_order_value_pct + 1e-9


def test_leverage_widens_notional_cap_when_qty_cap_binds():
    """Tiêu chí 2 (Brief 23): Cùng capital, cùng giá, cùng ATR — leverage=30 phải cho qty > leverage=1 khi qty_cap là vế thắng."""
    # capital=500, risk_pct=0.01, atr_mult=2.0, ref_price=100_000, atr=500
    # raw_atr = 500 * 0.01 / (500 * 2) = 0.005 BTC (notional = 500 USDT)
    # leverage=1:  raw_cap = 500 * 0.20 * 1 / 100_000  = 0.001 BTC -> qty = 0.001 BTC
    # leverage=30: raw_cap = 500 * 0.20 * 30 / 100_000 = 0.030 BTC -> qty = 0.005 BTC (ATR binding)
    sig = Signal("BTC-USDT", "BUY", 0.0001)

    rm_1x = RiskManager(capital=500.0, lot_size=0.0001, max_positions=1, leverage=1.0)
    sized_1x = rm_1x.approve_sized(sig, ref_price=100_000.0, atr=500.0, positions={}, daily_pnl=0.0, today=TODAY)

    rm_30x = RiskManager(capital=500.0, lot_size=0.0001, max_positions=1, leverage=30.0)
    sized_30x = rm_30x.approve_sized(sig, ref_price=100_000.0, atr=500.0, positions={}, daily_pnl=0.0, today=TODAY)

    assert sized_1x is not None
    assert sized_30x is not None
    assert sized_1x.qty == pytest.approx(0.0010, rel=1e-6)
    # Chốt chặn Brief 23: leverage 30x phải nới trần giúp qty lớn hơn 1x
    assert sized_30x.qty > sized_1x.qty
    assert sized_30x.qty == pytest.approx(0.0050, rel=1e-6)


def test_leverage_1x_matches_original_behavior():
    """Tiêu chí 3 (Brief 23): leverage=1.0 cho qty y hệt không truyền leverage."""
    sig = Signal("BTC-USDT", "BUY", 0.0001)
    rm_default = RiskManager(capital=500.0, lot_size=0.0001, max_positions=1)
    rm_1x = RiskManager(capital=500.0, lot_size=0.0001, max_positions=1, leverage=1.0)

    sized_def = rm_default.approve_sized(sig, ref_price=100_000.0, atr=1500.0, positions={}, daily_pnl=0.0, today=TODAY)
    sized_1x = rm_1x.approve_sized(sig, ref_price=100_000.0, atr=1500.0, positions={}, daily_pnl=0.0, today=TODAY)

    assert sized_def is not None and sized_1x is not None
    assert sized_def.qty == sized_1x.qty


def test_risk_budget_raw_atr_independent_of_leverage():
    """Tiêu chí 4 (Brief 23): Ngân sách rủi ro (raw_atr) không đổi theo đòn bẩy."""
    sig = Signal("BTC-USDT", "BUY", 0.0001)
    # Khi ATR rất lớn (atr=5000), raw_atr = 500 * 0.01 / (5000 * 2) = 0.0005 BTC
    # Cả 1x (cap 0.001) và 30x (cap 0.030) đều bị ATR chặn ở 0.0005 BTC
    rm_1x = RiskManager(capital=500.0, lot_size=0.0001, max_positions=1, leverage=1.0)
    rm_30x = RiskManager(capital=500.0, lot_size=0.0001, max_positions=1, leverage=30.0)

    sized_1x = rm_1x.approve_sized(sig, ref_price=100_000.0, atr=5000.0, positions={}, daily_pnl=0.0, today=TODAY)
    sized_30x = rm_30x.approve_sized(sig, ref_price=100_000.0, atr=5000.0, positions={}, daily_pnl=0.0, today=TODAY)

    assert sized_1x is not None and sized_30x is not None
    assert sized_1x.qty == sized_30x.qty == pytest.approx(0.0005, rel=1e-6)

