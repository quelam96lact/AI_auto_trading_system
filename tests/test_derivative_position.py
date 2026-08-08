from datetime import datetime

from trading.calendar_vn import TZ
from trading.derivative_position import (
    DERIVATIVE_CONTRACT_MULTIPLIER,
    DerivativePaperBroker,
)

CAP = 100_000_000
SYM = "41I1G8000"
TS = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
FEE = 2_700.0


def test_open_long_then_close_computes_pnl_fee_cash():
    b = DerivativePaperBroker(capital=CAP, fee_per_contract=FEE)
    open_fill = b.open_long(SYM, qty=1, price=1900.0, ts=TS)

    assert open_fill.side == "BUY" and open_fill.qty == 1
    assert open_fill.pnl is None
    assert abs(open_fill.fee - FEE) < 1e-9
    assert b.position_qty(SYM) == 1
    assert abs(b.cash - (CAP - FEE)) < 1e-9

    close_fill = b.close(SYM, price=1910.0, ts=TS)
    expected_pnl = (1910.0 - 1900.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE

    assert close_fill.side == "SELL" and close_fill.qty == 1
    assert abs(close_fill.pnl - expected_pnl) < 1e-9
    assert b.position_qty(SYM) == 0
    assert b.positions[SYM].avg_price == 0.0
    assert abs(b.realized_pnl - expected_pnl) < 1e-9
    assert abs(b.cash - (CAP - FEE + expected_pnl)) < 1e-9


def test_open_short_then_close_computes_pnl_for_price_drop():
    b = DerivativePaperBroker(capital=CAP, fee_per_contract=FEE)
    open_fill = b.open_short(SYM, qty=1, price=1900.0, ts=TS)

    assert open_fill.side == "SELL" and open_fill.qty == 1
    assert open_fill.pnl is None
    assert b.position_qty(SYM) == -1

    close_fill = b.close(SYM, price=1880.0, ts=TS)  # gia giam = lai cho short
    expected_pnl = (1900.0 - 1880.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE

    assert close_fill.side == "BUY" and close_fill.qty == 1
    assert abs(close_fill.pnl - expected_pnl) < 1e-9
    assert b.position_qty(SYM) == 0
    assert abs(b.realized_pnl - expected_pnl) < 1e-9


def test_open_short_then_close_at_higher_price_is_a_loss():
    b = DerivativePaperBroker(capital=CAP, fee_per_contract=FEE)
    b.open_short(SYM, qty=1, price=1900.0, ts=TS)

    close_fill = b.close(SYM, price=1920.0, ts=TS)  # gia tang = lo cho short
    expected_pnl = (1900.0 - 1920.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE

    assert abs(close_fill.pnl - expected_pnl) < 1e-9
    assert close_fill.pnl < 0


def test_position_qty_zero_for_unknown_symbol():
    b = DerivativePaperBroker(capital=CAP)
    assert b.position_qty("UNKNOWN") == 0


def test_close_pnl_applies_contract_multiplier():
    # VN30F1M (VN30 Index Futures, HNX) co he so nhan 100,000 VND/diem -
    # khong co he so nay, chenh 10 diem chi tinh thanh 10 VND nen phi co
    # dinh 2,700d luon lon hon bien dong gia -> moi lenh deu bao lo.
    b = DerivativePaperBroker(capital=CAP, fee_per_contract=FEE)
    b.open_long(SYM, qty=1, price=1900.0, ts=TS)

    close_fill = b.close(SYM, price=1910.0, ts=TS)  # chenh 10 diem
    expected_pnl = (1910.0 - 1900.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE

    assert abs(close_fill.pnl - expected_pnl) < 1e-9
