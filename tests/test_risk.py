from datetime import date

from trading.broker import Position
from trading.risk import RiskManager
from trading.strategy import Signal

CAP = 100_000_000
D = date(2026, 7, 15)


def test_rejects_buy_order_value_over_limit():
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "BUY", 10_000)
    assert (
        rm.approve(sig, ref_price=100_000, positions={}, daily_pnl=0, today=D) is False
    )


def test_approves_within_limits():
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "BUY", 100)
    assert rm.approve(sig, ref_price=50_000, positions={}, daily_pnl=0, today=D) is True


def test_rejects_new_symbol_beyond_max_positions():
    rm = RiskManager(capital=CAP, max_positions=2)
    positions = {"A": Position("A", 100, 10), "B": Position("B", 100, 10)}
    sig = Signal("C", "BUY", 10)
    assert (
        rm.approve(sig, ref_price=1_000, positions=positions, daily_pnl=0, today=D)
        is False
    )


def test_allows_adding_to_already_held_symbol_beyond_max_positions():
    rm = RiskManager(capital=CAP, max_positions=2)
    positions = {"A": Position("A", 100, 10), "B": Position("B", 100, 10)}
    sig = Signal("A", "BUY", 10)
    assert (
        rm.approve(sig, ref_price=1_000, positions=positions, daily_pnl=0, today=D)
        is True
    )


def test_sell_not_blocked_by_order_value_limit():
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "SELL", 10_000)
    assert (
        rm.approve(sig, ref_price=100_000, positions={}, daily_pnl=0, today=D) is True
    )


def test_halts_all_trading_for_rest_of_day_after_max_loss():
    rm = RiskManager(capital=CAP, max_daily_loss_pct=0.03)
    buy = Signal("VCB", "BUY", 10)
    sell = Signal("VCB", "SELL", 10)
    assert (
        rm.approve(buy, ref_price=1_000, positions={}, daily_pnl=-3_000_001, today=D)
        is False
    )
    assert (
        rm.approve(sell, ref_price=1_000, positions={}, daily_pnl=0, today=D) is False
    )
    assert (
        rm.approve(
            buy,
            ref_price=1_000,
            positions={},
            daily_pnl=0,
            today=date(2026, 7, 16),
        )
        is True
    )


def test_halted_date_publicly_readable_for_alerting():
    rm = RiskManager(capital=CAP, max_daily_loss_pct=0.03)
    assert rm.halted_date is None
    buy = Signal("VCB", "BUY", 10)
    rm.approve(buy, ref_price=1_000, positions={}, daily_pnl=-3_000_001, today=D)
    assert rm.halted_date == D


def test_approve_sized_computes_qty_from_atr_formula_rounded_to_lot():
    rm = RiskManager(capital=CAP)  # risk_pct=0.01, atr_multiplier=2.0 mac dinh
    sig = Signal("VCB", "BUY", 999)  # qty goc bi bo qua, sized se thay the
    result = rm.approve_sized(
        sig, ref_price=1_000, atr=333.0, positions={}, daily_pnl=0, today=D
    )
    # qty_raw = 100_000_000*0.01 / (333.0*2) = 1_000_000/666 = 1501.5015...
    # floor ve boi 100 -> 1500
    assert result == Signal("VCB", "BUY", 1500)


def test_approve_sized_rejects_when_qty_rounds_below_lot():
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "BUY", 100)
    # qty_raw = 1_000_000 / (20_000*2) = 25 -> floor ve boi 100 = 0 < 100
    result = rm.approve_sized(
        sig, ref_price=1_000, atr=20_000.0, positions={}, daily_pnl=0, today=D
    )
    assert result is None


def test_approve_sized_rejects_when_atr_is_none():
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "BUY", 100)
    result = rm.approve_sized(
        sig, ref_price=1_000, atr=None, positions={}, daily_pnl=0, today=D
    )
    assert result is None


def test_approve_sized_rejects_when_sized_order_value_over_limit():
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "BUY", 100)
    # qty_raw = 1_000_000 / (1_000*2) = 500 (boi 100 san). order_value = 100_000*500 = 50_000_000
    # > max_order_value_pct(0.20)*CAP(100_000_000) = 20_000_000 -> tu choi
    result = rm.approve_sized(
        sig, ref_price=100_000, atr=1_000.0, positions={}, daily_pnl=0, today=D
    )
    assert result is None


def test_approve_sized_sell_passes_through_unchanged_qty():
    rm = RiskManager(capital=CAP)
    sig = Signal(
        "VCB", "SELL", 350
    )  # so le, KHONG phai boi 100 - chung minh khong bi lam tron
    result = rm.approve_sized(
        sig, ref_price=1_000, atr=None, positions={}, daily_pnl=0, today=D
    )
    assert result == sig


def test_approve_sized_rejects_new_symbol_beyond_max_positions():
    rm = RiskManager(capital=CAP, max_positions=2)
    positions = {"A": Position("A", 100, 10), "B": Position("B", 100, 10)}
    sig = Signal("C", "BUY", 100)
    # atr=5_000 -> qty_raw = 1_000_000/(5_000*2) = 100 (boi 100 san, order_value nho)
    result = rm.approve_sized(
        sig, ref_price=1_000, atr=5_000.0, positions=positions, daily_pnl=0, today=D
    )
    assert result is None


def test_approve_sized_allows_adding_to_already_held_symbol_beyond_max_positions():
    rm = RiskManager(capital=CAP, max_positions=2)
    positions = {"A": Position("A", 100, 10), "B": Position("B", 100, 10)}
    sig = Signal("A", "BUY", 100)
    result = rm.approve_sized(
        sig, ref_price=1_000, atr=5_000.0, positions=positions, daily_pnl=0, today=D
    )
    assert result == Signal("A", "BUY", 100)


def test_approve_sized_shares_halt_state_with_approve():
    rm = RiskManager(capital=CAP, max_daily_loss_pct=0.03)
    buy = Signal("VCB", "BUY", 100)
    # approve() (khong sized) trigger halt truoc
    assert (
        rm.approve(buy, ref_price=1_000, positions={}, daily_pnl=-3_000_001, today=D)
        is False
    )
    assert rm.halted_date == D
    # approve_sized() cung bi chan boi CUNG mot halted_date, du atr hop le
    result = rm.approve_sized(
        buy, ref_price=1_000, atr=5_000.0, positions={}, daily_pnl=0, today=D
    )
    assert result is None
