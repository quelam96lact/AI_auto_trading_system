from datetime import datetime

from trading.broker import Position
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.strategy import Signal


def bar(o, h, l, c, sym="VCB", m=0):
    return Bar(sym, datetime(2026, 7, 15, 9, m, tzinfo=TZ), o, h, l, c, 1000)


def test_no_pending_order_no_fill():
    b = PaperBroker(capital=100_000_000)
    assert b.on_bar(bar(10.0, 10.0, 10.0, 10.0)) == []


def test_buy_fills_with_fee_and_slippage():
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("VCB", "BUY", 100))
    fills = b.on_bar(bar(10.0, 10.0, 10.0, 10.0))
    assert len(fills) == 1
    f = fills[0]
    expected_price = 10.0 * (1 + 5 / 10_000)
    assert abs(f.price - expected_price) < 1e-9
    assert f.qty == 100 and f.pnl is None
    expected_fee = expected_price * 100 * 0.0015
    assert abs(f.fee - expected_fee) < 1e-9
    assert b.position_qty("VCB") == 100


def test_sell_computes_realized_pnl_and_caps_oversell():
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("VCB", "BUY", 100))
    b.on_bar(bar(10.0, 10.0, 10.0, 10.0))
    b.submit(Signal("VCB", "SELL", 9999))
    fills = b.on_bar(bar(11.0, 11.0, 11.0, 11.0, m=5))
    assert len(fills) == 1
    assert fills[0].qty == 100
    assert fills[0].pnl is not None
    assert b.position_qty("VCB") == 0
    assert b.realized_pnl == fills[0].pnl


def test_unrealized_pnl_uses_marks():
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("VCB", "BUY", 100))
    b.on_bar(bar(10.0, 10.0, 10.0, 10.0))
    pos = b.positions["VCB"]
    expected = (12.0 - pos.avg_price) * 100
    assert abs(b.unrealized_pnl({"VCB": 12.0}) - expected) < 1e-6


def test_force_exit_closes_full_position_and_computes_pnl():
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("VCB", "BUY", 100))
    b.on_bar(bar(10.0, 10.0, 10.0, 10.0))
    entry_price = b.positions["VCB"].avg_price

    fill = b.force_exit("VCB", price=9.0, ts=datetime(2026, 7, 15, 9, 10, tzinfo=TZ))

    expected_fee = 9.0 * 100 * (b.fee_rate + b.sell_tax_rate)
    expected_pnl = (9.0 - entry_price) * 100 - expected_fee
    assert fill.symbol == "VCB" and fill.side == "SELL" and fill.qty == 100
    assert abs(fill.price - 9.0) < 1e-9
    assert abs(fill.fee - expected_fee) < 1e-9
    assert fill.pnl is not None and abs(fill.pnl - expected_pnl) < 1e-6
    assert b.position_qty("VCB") == 0
    assert b.positions["VCB"].avg_price == 0.0
    assert b.realized_pnl == fill.pnl


def test_restore_resumes_cash_positions_and_realized_pnl():
    positions = {"VCB": Position("VCB", 100, 10.0)}
    b = PaperBroker.restore(
        capital=100_000_000,
        cash=95_000_000,
        realized_pnl=200_000,
        positions=positions,
    )
    assert b.cash == 95_000_000
    assert b.realized_pnl == 200_000
    assert b.position_qty("VCB") == 100
    assert b.capital == 100_000_000
