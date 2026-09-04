from datetime import date

from trading.broker import Position
from trading.risk import RiskManager
from trading.strategy import Signal

CAP = 100_000_000
D = date(2026, 7, 15)
TODAY = date(2026, 8, 13)  # SIZE-1: dung cho cac test cap qty moi


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


def test_approve_sized_caps_order_value_to_limit_instead_of_rejecting():
    """SIZE-1: thay vi tu choi khi qty_atr vuot tran, cap qty xuong vua tran
    (qty = min(qty_atr, qty_cap)). qty_atr = 500 -> order_value 50tr > tran
    20tr -> qty_cap = 20tr/100k = 200 -> qty = 200 (van duyet, khong vuot tran)."""
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "BUY", 100)
    # qty_atr = CAP*0.01/(1000*2) = 500; qty_cap = CAP*0.20/100_000 = 200
    result = rm.approve_sized(
        sig, ref_price=100_000, atr=1_000.0, positions={}, daily_pnl=0, today=D
    )
    assert result is not None
    assert result.qty == 200
    assert 100_000 * result.qty <= CAP * 0.20


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


# ============ SIZE-1: cap qty cho vua tran + moi lan tu choi noi ly do ============


def test_buy_approved_when_atr_price_below_old_threshold():
    """SIZE-1 kiem chung 1: ATR/gia = 1% (duoi ngung 2,5% cua logic cu — logic
    cu triet tieu capital hai ve, doi ATR/gia >= 2,5%) -> BUY DUOC duyet,
    qty la boi cua 100, va ref_price*qty <= capital*0,20 (khong vo tran)."""
    r = RiskManager(capital=1_000_000)
    sized = r.approve_sized(
        Signal("ENGT", "BUY", 100), ref_price=100, atr=1.0, positions={}, daily_pnl=0.0, today=TODAY
    )
    assert sized is not None and sized.side == "BUY"
    assert sized.qty % 100 == 0
    assert sized.qty > 0
    assert 100 * sized.qty <= 1_000_000 * 0.20
    assert r.last_reject_reason is None


def test_qty_capped_by_order_value_when_atr_small():
    """SIZE-1 kiem chung 2 chieu min(): ATR nho -> qty_atr lon -> qty phai
    bang qty_cap (khong bao gio vuot tran 20%)."""
    r = RiskManager(capital=1_000_000)
    sized = r.approve_sized(
        Signal("ENGT", "BUY", 100), ref_price=100, atr=0.5, positions={}, daily_pnl=0.0, today=TODAY
    )
    qty_atr = 10_000
    qty_cap = int((1_000_000 * 0.20 / 100) // 100) * 100  # 2000
    assert sized.qty == min(qty_atr, qty_cap) == qty_cap
    assert 100 * sized.qty <= 1_000_000 * 0.20


def test_qty_limited_by_atr_when_atr_large():
    """SIZE-1 kiem chung 2 chieu min(): ATR lon -> qty_atr nho -> qty phai
    bang qty_atr (khong bao gio vuot muc ATR sizing cho phep)."""
    r = RiskManager(capital=1_000_000)
    sized = r.approve_sized(
        Signal("ENGT", "BUY", 100), ref_price=100, atr=10.0, positions={}, daily_pnl=0.0, today=TODAY
    )
    qty_atr = int((1_000_000 * 0.01 / (10.0 * 2.0)) // 100) * 100  # 500
    qty_cap = 2000
    assert sized.qty == min(qty_atr, qty_cap) == qty_atr


def test_rejected_with_reason_when_lot_exceeds_cap():
    """SIZE-1 kiem chung 3: gia cao toi muc 1 lo da vuot tran -> None + reason
    neu ro ca qty_atr lan qty_cap (khong tu choi im lang)."""
    r = RiskManager(capital=1_000_000)
    sized = r.approve_sized(
        Signal("ENGT", "BUY", 100), ref_price=500_000, atr=1.0, positions={}, daily_pnl=0.0, today=TODAY
    )
    assert sized is None
    assert r.last_reject_reason is not None
    assert "qty_atr" in r.last_reject_reason and "qty_cap" in r.last_reject_reason


def test_each_reject_sets_reason_and_success_clears():
    """SIZE-1 kiem chung 4: moi nhanh tu choi dat dung ly do; duyet thanh
    cong XOA ly do cu (khong de ly do cu vuong lai gay hieu nham)."""
    r = RiskManager(capital=1_000_000)

    # halt lo ngay
    r.approve_sized(Signal("ENGT", "BUY", 100), 100, 1.0, {}, daily_pnl=-100_000, today=TODAY)
    assert r.last_reject_reason == "halt lỗ ngày"

    # ATR khong hop le
    r = RiskManager(capital=1_000_000)
    r.approve_sized(Signal("ENGT", "BUY", 100), 100, None, {}, 0.0, TODAY)
    assert r.last_reject_reason == "ATR không hợp lệ (atr=None hoặc <=0)"

    # qty sau cap < 1 lo
    r = RiskManager(capital=1_000_000)
    r.approve_sized(Signal("ENGT", "BUY", 100), 500_000, 1.0, {}, 0.0, TODAY)
    assert r.last_reject_reason.startswith("qty sau cap < 1 lô")

    # du max_positions
    r = RiskManager(capital=1_000_000, max_positions=1)
    r.approve_sized(Signal("ENGT", "BUY", 100), 100, 1.0, {"AAA": Position("AAA", 100, 10.0)}, 0.0, TODAY)
    assert r.last_reject_reason.startswith("đã đủ max_positions")

    # duyet thanh cong xoa ly do cu
    r = RiskManager(capital=1_000_000, max_positions=1)
    r.approve_sized(Signal("ENGT", "BUY", 100), 100, 1.0, {"AAA": Position("AAA", 100, 10.0)}, 0.0, TODAY)
    assert r.last_reject_reason is not None
    sized = r.approve_sized(Signal("ENGT", "BUY", 100), 100, 1.0, {}, 0.0, TODAY)
    assert sized is not None and r.last_reject_reason is None


# ==== goi C-a (04/09): RiskManager nhan don vi lo — mac dinh 100 bat bien ====


def test_lot_size_1_cho_crypto_khong_bi_tu_choi():
    """C-a tieu chi 1: lot=1 => qty tinh ra 33 (khong phai boi 100) duoc chap
    nhan. Hom nay (luon boi 100 + tu choi qty<100) 33 -> None — tai hien loi
    crypto gia cao bien mat khoi bang do.

    LUU Y so lieu: brief ghi 'von 100.000' — bat kha thi ve so hoc (qty_atr =
    100.000*1%/(1.500*2) = 0.33, lot 1 cung ra 0). Dung von 10.000.000 de co
    qty_atr = 33: < 100 nen hom nay bi tu choi, lot=1 thi chap nhan."""
    r = RiskManager(capital=10_000_000, lot_size=1, max_positions=10)
    sized = r.approve_sized(
        Signal("X", "BUY", 1), ref_price=60_000.0, atr=1_500.0,
        positions={}, daily_pnl=0.0, today=TODAY,
    )
    assert sized is not None
    assert sized.qty == 33


def test_mac_dinh_van_boi_100_va_tu_choi_qty_duoi_100():
    """C-a tieu chi 2: RiskManager(capital=...) khong truyen lot_size van lam
    tron xuong boi 100 VA tu choi qty < 100 — ranh gioi voi phien thu Hai."""
    r = RiskManager(capital=100_000_000)
    sized = r.approve_sized(
        Signal("VCB", "BUY", 100), ref_price=50_000.0, atr=2_000.0,
        positions={}, daily_pnl=0.0, today=TODAY,
    )
    assert sized is not None
    assert sized.qty % 100 == 0

    # von nho x vao mat: qty_atr < 100 => None (khong phai qty 1)
    r_small = RiskManager(capital=100_000)
    assert (
        r_small.approve_sized(
            Signal("X", "BUY", 1), ref_price=60_000.0, atr=1_500.0,
            positions={}, daily_pnl=0.0, today=TODAY,
        )
        is None
    )


def test_lot_size_10_lam_tron_xuong_boi_10():
    """lot_size la tham so duy nhat: ca phep tron lan nguong tu choi doc tu no."""
    r = RiskManager(capital=10_000_000, lot_size=10, max_positions=10)
    sized = r.approve_sized(
        Signal("X", "BUY", 1), ref_price=60_000.0, atr=2_000.0,
        positions={}, daily_pnl=0.0, today=TODAY,
    )
    assert sized is not None and sized.qty % 10 == 0
