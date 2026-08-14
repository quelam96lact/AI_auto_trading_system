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
    expected_fee = expected_price * 100 * 0.0025
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


# ============ FEE-ALARM-1 Viec 1: phi MUA phai nam trong gia von ============


def test_full_roundtrip_cash_minus_capital_equals_realized_pnl():
    """FEE-ALARM-1 kiem chung 1 (RED bat buoc): mot vong BUY->SELL tron ven,
    ket thuc qty=0 -> broker.cash - broker.capital == broker.realized_pnl.
    Phai DO tren code hien tai (avg_price khong gom phi mua -> realized_pnl bo
    sot phi MUA, lech dung bang phi mua)."""
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("ENGT", "BUY", 100))
    b.on_bar(Bar("ENGT", datetime(2026, 8, 14, 9, 5, tzinfo=TZ), 10_000.0, 10_000.0, 10_000.0, 10_000.0, 1000))
    b.submit(Signal("ENGT", "SELL", 100))
    b.on_bar(Bar("ENGT", datetime(2026, 8, 14, 9, 10, tzinfo=TZ), 10_000.0, 10_000.0, 10_000.0, 10_000.0, 1000))

    assert b.position_qty("ENGT") == 0
    assert abs((b.cash - b.capital) - b.realized_pnl) < 0.01, (
        f"cash-capital ({b.cash - b.capital}) phai bang realized_pnl ({b.realized_pnl}) — "
        f"hien lech {abs((b.cash - b.capital) - b.realized_pnl)}"
    )


def test_force_exit_cash_minus_capital_equals_realized_pnl():
    """FEE-ALARM-1 kiem chung 3: BUY roi force_exit toan bo -> cash - capital
    == realized_pnl (force_exit doc avg_price, tu dung sau khi sua)."""
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("ENGT", "BUY", 100))
    b.on_bar(Bar("ENGT", datetime(2026, 8, 14, 9, 5, tzinfo=TZ), 10_000.0, 10_000.0, 10_000.0, 10_000.0, 1000))
    b.force_exit("ENGT", 10_000.0, datetime(2026, 8, 14, 9, 10, tzinfo=TZ))

    assert b.position_qty("ENGT") == 0
    assert abs((b.cash - b.capital) - b.realized_pnl) < 0.01


def test_unrealized_pnl_reflects_entry_fee():
    """FEE-ALARM-1 kiem chung 4: mua xong, mark BANG DUNG gia mua -> unrealized
    pnl phai AM dung bang phi (khong phai 0) — gia von gom phi."""
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("ENGT", "BUY", 100))
    b.on_bar(Bar("ENGT", datetime(2026, 8, 14, 9, 5, tzinfo=TZ), 10_000.0, 10_000.0, 10_000.0, 10_000.0, 1000))
    # on_bar mua voi slippage 5bps -> gia thuc = bar.open + 5
    fill_price = 10_000.0 + 10_000.0 * (5 / 10_000)
    gross = fill_price * 100
    fee = gross * 0.0025
    upnl = b.unrealized_pnl({"ENGT": 10_000.0})
    assert upnl < 0, f"unrealized phai am (phi mua), thuc te: {upnl}"
    # upnl = (mark - gia von gom phi) * qty = -(gross + fee - mark*qty)
    assert abs(upnl + (gross + fee - 10_000.0 * 100)) < 0.01, (
        f"unrealized phai = -(gia von gom phi - mark) = {- (gross + fee - 10_000.0 * 100)}, thuc te: {upnl}"
    )
