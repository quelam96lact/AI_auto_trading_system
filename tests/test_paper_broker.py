from datetime import datetime

from trading.broker import Position
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.strategy import Signal


def bar(o, h, l, c, sym="VCB", m=0, day=15):
    return Bar(sym, datetime(2026, 7, day, 9, m, tzinfo=TZ), o, h, l, c, 1000)


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
    b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=15))
    # SPEC-1a: SELL ngay D (cung ngay mua) bi tu choi — phai doi D+3
    b.submit(Signal("VCB", "SELL", 9999))
    assert b.on_bar(bar(11.0, 11.0, 11.0, 11.0, m=5)) == []
    assert b.position_qty("VCB") == 100
    # Trai qua 2 ngay giao dich nua (16, 17) — 18/07 = D+3 -> SELL khop
    b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=16))
    b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=17))
    b.submit(Signal("VCB", "SELL", 9999))
    fills = b.on_bar(bar(11.0, 11.0, 11.0, 11.0, day=18))
    assert len(fills) == 1
    assert fills[0].qty == 100  # van cap oversell ve qty dang giu
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
    b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=15))
    entry_price = b.positions["VCB"].avg_price
    # SPEC-1a: force_exit ngay D (chua settle) bi tu choi, vi the con nguyen
    rejected = b.force_exit("VCB", price=9.0, ts=datetime(2026, 7, 15, 9, 10, tzinfo=TZ))
    assert rejected.qty == 0 and b.position_qty("VCB") == 100
    # D+3 (18/07): force_exit dong duoc toan bo
    for d in (16, 17):
        b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=d))

    fill = b.force_exit("VCB", price=9.0, ts=datetime(2026, 7, 18, 9, 10, tzinfo=TZ))

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


def test_restore_position_not_sellable_until_d3():
    """SPEC1-FIX Lỗi 2: restore() khong co thong tin ngay mua -> coi nhu mua
    o NGAY RESTORE (day_index 0 = bar dau tien sau restart). SELL ngay bi tu
    choi (khong la lac quan nhu day_index -10^9), toi D+3 moi ban duoc."""
    b = PaperBroker.restore(
        capital=100_000_000,
        cash=90_000_000,
        realized_pnl=0.0,
        positions={"VCB": Position("VCB", 100, 10.0)},
    )
    # Ngay restore (bar dau tien, day 15): SELL bi tu choi — chua settle
    b.submit(Signal("VCB", "SELL", 100))
    assert b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=15)) == []
    assert b.position_qty("VCB") == 100
    # D+1, D+2 van bi tu choi
    b.submit(Signal("VCB", "SELL", 100))
    assert b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=16)) == []
    b.submit(Signal("VCB", "SELL", 100))
    assert b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=17)) == []
    assert b.position_qty("VCB") == 100
    # D+3 (day 18): ban duoc
    b.submit(Signal("VCB", "SELL", 100))
    fills = b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=18))
    assert len(fills) == 1 and fills[0].qty == 100
    assert b.position_qty("VCB") == 0


# ============ FEE-ALARM-1 Viec 1: phi MUA phai nam trong gia von ============


def test_full_roundtrip_cash_minus_capital_equals_realized_pnl():
    """FEE-ALARM-1 kiem chung 1 (RED bat buoc): mot vong BUY->SELL tron ven,
    ket thuc qty=0 -> broker.cash - broker.capital == broker.realized_pnl.
    Phai DO tren code hien tai (avg_price khong gom phi mua -> realized_pnl bo
    sot phi MUA, lech dung bang phi mua). SPEC-1a: SELL phai doi D+3 — mua
    14/08, ban 17/08."""
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("ENGT", "BUY", 100))
    b.on_bar(Bar("ENGT", datetime(2026, 8, 14, 9, 5, tzinfo=TZ), 10_000.0, 10_000.0, 10_000.0, 10_000.0, 1000))
    b.on_bar(Bar("ENGT", datetime(2026, 8, 15, 9, 5, tzinfo=TZ), 10_000.0, 10_000.0, 10_000.0, 10_000.0, 1000))
    b.on_bar(Bar("ENGT", datetime(2026, 8, 16, 9, 5, tzinfo=TZ), 10_000.0, 10_000.0, 10_000.0, 10_000.0, 1000))
    b.submit(Signal("ENGT", "SELL", 100))
    b.on_bar(Bar("ENGT", datetime(2026, 8, 17, 9, 10, tzinfo=TZ), 10_000.0, 10_000.0, 10_000.0, 10_000.0, 1000))

    assert b.position_qty("ENGT") == 0
    assert abs((b.cash - b.capital) - b.realized_pnl) < 0.01, (
        f"cash-capital ({b.cash - b.capital}) phai bang realized_pnl ({b.realized_pnl}) — "
        f"hien lech {abs((b.cash - b.capital) - b.realized_pnl)}"
    )


def test_force_exit_cash_minus_capital_equals_realized_pnl():
    """FEE-ALARM-1 kiem chung 3: BUY roi force_exit toan bo -> cash - capital
    == realized_pnl (force_exit doc avg_price, tu dung sau khi sua). SPEC-1a:
    force_exit phai doi D+3 — mua 14/08, thoat 17/08."""
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("ENGT", "BUY", 100))
    b.on_bar(Bar("ENGT", datetime(2026, 8, 14, 9, 5, tzinfo=TZ), 10_000.0, 10_000.0, 10_000.0, 10_000.0, 1000))
    b.on_bar(Bar("ENGT", datetime(2026, 8, 15, 9, 5, tzinfo=TZ), 10_000.0, 10_000.0, 10_000.0, 10_000.0, 1000))
    b.on_bar(Bar("ENGT", datetime(2026, 8, 16, 9, 5, tzinfo=TZ), 10_000.0, 10_000.0, 10_000.0, 10_000.0, 1000))
    b.force_exit("ENGT", 10_000.0, datetime(2026, 8, 17, 9, 10, tzinfo=TZ))

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


# ============ SPEC 1a: T+2,5 settlement (mua D -> ban duoc tu D+3) ============


def test_sell_rejected_on_day_plus_1_and_plus_2_fills_on_day_plus_3():
    """SPEC-1a kiem chung 1: mua ngay D (15/07), ban ngay D+1 va D+2 (16, 17/07)
    bi TU CHOI (chua settle), ban ngay D+3 (18/07) -> khop."""
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("VCB", "BUY", 100))
    assert len(b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=15))) == 1
    assert b.position_qty("VCB") == 100

    # D+1 va D+2: chua settle -> SELL bi tu choi, khong co fill, qty giu nguyen
    b.submit(Signal("VCB", "SELL", 100))
    assert b.on_bar(bar(11.0, 11.0, 11.0, 11.0, day=16)) == []
    assert b.position_qty("VCB") == 100, "D+1: vi the phai con nguyen"
    b.submit(Signal("VCB", "SELL", 100))
    assert b.on_bar(bar(11.0, 11.0, 11.0, 11.0, day=17)) == []
    assert b.position_qty("VCB") == 100, "D+2: vi the phai con nguyen"

    # D+3: da settle -> khop
    b.submit(Signal("VCB", "SELL", 100))
    fills = b.on_bar(bar(12.0, 12.0, 12.0, 12.0, day=18))
    assert len(fills) == 1 and fills[0].side == "SELL" and fills[0].qty == 100
    assert b.position_qty("VCB") == 0


def test_two_lots_older_settles_first_fifo():
    """SPEC-1a kiem chung 2: hai lo mua ngay 15 va 16/07. Ngay 18 (D+3 cua lo
    cu) chi lo cu settle -> ban duoc phan lo cu; lo moi phai doi den 19/07."""
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("VCB", "BUY", 100))
    b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=15))  # lo 1: D = 15/07
    b.submit(Signal("VCB", "BUY", 100))
    b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=16))  # lo 2: D = 16/07
    b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=17))  # ngay giao dich trung gian
    assert b.position_qty("VCB") == 200

    # 18/07 = D+3 cua lo 1 (15/07) nhung chi D+2 cua lo 2 (16/07) -> chi ban
    # duoc 100 (lo 1). SELL 200 -> khop dung 100, con 100.
    b.submit(Signal("VCB", "SELL", 200))
    fills = b.on_bar(bar(11.0, 11.0, 11.0, 11.0, day=18))
    assert len(fills) == 1 and fills[0].qty == 100, (
        f"18/07: chi lo cu settle, phai khop 100, thuc te {[f.qty for f in fills]}"
    )
    assert b.position_qty("VCB") == 100

    # 19/07 = D+3 cua lo 2 -> ban duoc not 100
    b.submit(Signal("VCB", "SELL", 100))
    fills = b.on_bar(bar(11.0, 11.0, 11.0, 11.0, day=19))
    assert len(fills) == 1 and fills[0].qty == 100
    assert b.position_qty("VCB") == 0


def test_settlement_counts_trading_days_not_calendar_days():
    """SPEC-1a: quy uoc D+3 theo NGAY GIAO DICH (so bar ngay) — mot bar 5m
    sang ngay 17/07 bat dau tinh ngay moi, khong phai 24h lich."""
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("VCB", "BUY", 100))
    b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=15))  # D = 15/07
    # 16/07 co nhieu bar 5m — chi la ngay giao dich thu 2, chua du 3 ngay
    b.submit(Signal("VCB", "SELL", 100))
    assert b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=16, m=0)) == []
    b.submit(Signal("VCB", "SELL", 100))
    assert b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=16, m=5)) == []
    # Ngay 17/07 = ngay thu 3 sau D, nhung quy uoc D+3: mua D -> ban duoc tu
    # ngay giao dich thu D+3 (18/07), tuc la sau 3 NGAY MOI — 17/07 moi la
    # ngay thu 2 sau D (16/07 la thu nhat) nen van chua duoc ban.
    b.submit(Signal("VCB", "SELL", 100))
    assert b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=17)) == []
    # 18/07 = ngay giao dich thu 4 — D+3 -> duoc ban
    b.submit(Signal("VCB", "SELL", 100))
    fills = b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=18))
    assert len(fills) == 1 and fills[0].qty == 100


def test_force_exit_only_closes_settled_portion():
    """SPEC-1a: force_exit (trailing stop) cung phai ton trong T+2,5 — ngay D
    chua settle nen khong the thoat duoc; ngay D+3 thoat duoc."""
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("VCB", "BUY", 100))
    b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=15))  # D = 15/07
    # Ngay D: force_exit khong ban duoc gi (chua settle) — vi the con nguyen
    fill = b.force_exit("VCB", price=9.0, ts=datetime(2026, 7, 15, 9, 10, tzinfo=TZ))
    assert fill.qty == 0, f"ngay mua: force_exit phai bi tu choi, thuc te qty={fill.qty}"
    assert b.position_qty("VCB") == 100
    # Broker chi biet ngay giao dich qua cac bar no thay — cho no thay cac ngay
    # 16, 17, 18 (khong co lenh treo) truoc khi force_exit ngay 18.
    for d in (16, 17, 18):
        b.on_bar(bar(10.0, 10.0, 10.0, 10.0, day=d))
    # D+3 (18/07): force_exit dong duoc toan bo
    fill = b.force_exit("VCB", price=9.0, ts=datetime(2026, 7, 18, 9, 10, tzinfo=TZ))
    assert fill.qty == 100 and b.position_qty("VCB") == 0
