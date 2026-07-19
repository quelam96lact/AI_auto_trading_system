from datetime import date

from trading.broker import Position
from trading.risk import RiskManager
from trading.strategy import Signal

CAP = 100_000_000
D = date(2026, 7, 15)


def test_rejects_buy_order_value_over_limit():
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "BUY", 10_000)
    assert rm.approve(sig, ref_price=100_000, positions={}, daily_pnl=0, today=D) is False


def test_approves_within_limits():
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "BUY", 100)
    assert rm.approve(sig, ref_price=50_000, positions={}, daily_pnl=0, today=D) is True


def test_rejects_new_symbol_beyond_max_positions():
    rm = RiskManager(capital=CAP, max_positions=2)
    positions = {"A": Position("A", 100, 10), "B": Position("B", 100, 10)}
    sig = Signal("C", "BUY", 10)
    assert rm.approve(sig, ref_price=1_000, positions=positions, daily_pnl=0, today=D) is False


def test_allows_adding_to_already_held_symbol_beyond_max_positions():
    rm = RiskManager(capital=CAP, max_positions=2)
    positions = {"A": Position("A", 100, 10), "B": Position("B", 100, 10)}
    sig = Signal("A", "BUY", 10)
    assert rm.approve(sig, ref_price=1_000, positions=positions, daily_pnl=0, today=D) is True


def test_sell_not_blocked_by_order_value_limit():
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "SELL", 10_000)
    assert rm.approve(sig, ref_price=100_000, positions={}, daily_pnl=0, today=D) is True


def test_halts_all_trading_for_rest_of_day_after_max_loss():
    rm = RiskManager(capital=CAP, max_daily_loss_pct=0.03)
    buy = Signal("VCB", "BUY", 10)
    sell = Signal("VCB", "SELL", 10)
    assert rm.approve(buy, ref_price=1_000, positions={}, daily_pnl=-3_000_001, today=D) is False
    assert rm.approve(sell, ref_price=1_000, positions={}, daily_pnl=0, today=D) is False
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
