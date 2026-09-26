from datetime import datetime

import pytest

from trading.calendar_vn import TZ
from trading.derivative_position import (
    DERIVATIVE_CONTRACT_MULTIPLIER,
    DERIVATIVE_FEE_PER_CONTRACT,
    DERIVATIVE_INITIAL_MARGIN_RATE,
    DERIVATIVE_PIT_TAX_RATE,
    DERIVATIVE_VSD_CLEARING_FEE_PER_CONTRACT,
    DerivativePaperBroker,
    derivative_trade_tax,
)

CAP = 100_000_000
SYM = "41I1G8000"
TS = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
FEE = 2_700.0


def test_open_long_then_close_computes_pnl_fee_cash():
    b = DerivativePaperBroker(
        capital=CAP, fee_per_contract=FEE, vsd_fee_per_contract=0.0, tax_rate=0.0
    )
    open_fill = b.open_long(SYM, qty=1, price=1900.0, ts=TS)

    assert open_fill.side == "BUY" and open_fill.qty == 1
    assert open_fill.pnl is None
    assert abs(open_fill.fee - FEE) < 1e-9
    assert b.position_qty(SYM) == 1
    assert abs(b.cash - (CAP - FEE)) < 1e-9

    close_fill = b.close(SYM, price=1910.0, ts=TS)
    expected_pnl = (1910.0 - 1900.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE

    assert close_fill.side == "SELL" and close_fill.qty == 1
    # LEDGER-1 Viec 2: fill.pnl gio GOM phi mo — cung nghia ben co phieu
    assert abs(close_fill.pnl - (expected_pnl - FEE)) < 1e-9
    assert b.position_qty(SYM) == 0
    assert b.positions[SYM].avg_price == 0.0
    # DERIV-FEE-1: realized gio TRU ca phi mo (expected_pnl chi tru phi dong)
    assert abs(b.realized_pnl - (expected_pnl - FEE)) < 1e-9
    assert abs(b.cash - (CAP - FEE + expected_pnl)) < 1e-9


def test_open_short_then_close_computes_pnl_for_price_drop():
    b = DerivativePaperBroker(
        capital=CAP, fee_per_contract=FEE, vsd_fee_per_contract=0.0, tax_rate=0.0
    )
    open_fill = b.open_short(SYM, qty=1, price=1900.0, ts=TS)

    assert open_fill.side == "SELL" and open_fill.qty == 1
    assert open_fill.pnl is None
    assert b.position_qty(SYM) == -1

    close_fill = b.close(SYM, price=1880.0, ts=TS)  # gia giam = lai cho short
    expected_pnl = (1900.0 - 1880.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE

    assert close_fill.side == "BUY" and close_fill.qty == 1
    # LEDGER-1 Viec 2: fill.pnl gio GOM phi mo — cung nghia ben co phieu
    assert abs(close_fill.pnl - (expected_pnl - FEE)) < 1e-9
    assert b.position_qty(SYM) == 0
    # DERIV-FEE-1: realized gio TRU ca phi mo (FEE o file nay = 2.700)
    assert abs(b.realized_pnl - (expected_pnl - FEE)) < 1e-9


def test_open_short_then_close_at_higher_price_is_a_loss():
    b = DerivativePaperBroker(
        capital=CAP, fee_per_contract=FEE, vsd_fee_per_contract=0.0, tax_rate=0.0
    )
    b.open_short(SYM, qty=1, price=1900.0, ts=TS)

    close_fill = b.close(SYM, price=1920.0, ts=TS)  # gia tang = lo cho short
    expected_pnl = (1900.0 - 1920.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE

    # LEDGER-1 Viec 2: fill.pnl gio GOM phi mo — cung nghia ben co phieu
    assert abs(close_fill.pnl - (expected_pnl - FEE)) < 1e-9
    assert close_fill.pnl < 0


def test_position_qty_zero_for_unknown_symbol():
    b = DerivativePaperBroker(capital=CAP)
    assert b.position_qty("UNKNOWN") == 0


def test_close_pnl_applies_contract_multiplier():
    # VN30F1M (VN30 Index Futures, HNX) co he so nhan 100,000 VND/diem -
    # khong co he so nay, chenh 10 diem chi tinh thanh 10 VND nen phi co
    # dinh 2,700d luon lon hon bien dong gia -> moi lenh deu bao lo.
    b = DerivativePaperBroker(
        capital=CAP, fee_per_contract=FEE, vsd_fee_per_contract=0.0, tax_rate=0.0
    )
    b.open_long(SYM, qty=1, price=1900.0, ts=TS)

    close_fill = b.close(SYM, price=1910.0, ts=TS)  # chenh 10 diem
    expected_pnl = (1910.0 - 1900.0) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE

    # LEDGER-1 Viec 2: fill.pnl gio GOM phi mo — cung nghia ben co phieu
    assert abs(close_fill.pnl - (expected_pnl - FEE)) < 1e-9


# ============ Brief 95 Task 2: TDD Tests cho biểu phí và thuế mới ============


def test_derivative_trade_tax_calculation():
    """Kiểm tra tính thuế TNCN theo công thức Task 1a (CV 11133/BTC-CST):
    Giá chuyển nhượng = (Giá x 100.000 x Qty x 17%) / 2
    Thuế TNCN = Giá chuyển nhượng x 0,1%

    Tính tay cho price = 1.900,0 điểm, qty = 1:
    Giá chuyển nhượng = (1.900,0 x 100.000 x 1 x 0,17) / 2 = 16.150.000 VNĐ
    Thuế TNCN = 16.150.000 x 0,001 = 16.150,0 VNĐ.
    """
    tax = derivative_trade_tax(1900.0, 1)
    assert tax == pytest.approx(16_150.0, abs=1e-9)


def test_derivative_trade_tax_linear_with_price():
    """Kiểm tra thuế TNCN tuyến tính theo giá:
    Giá gấp đôi (3.800,0 vs 1.900,0) thì thuế gấp đôi:
    Price 3.800: (3.800 x 100.000 x 1 x 0,17 / 2) x 0,001 = 32.300,0 VNĐ.
    32.300 == 2 x 16.150.
    """
    tax_1900 = derivative_trade_tax(1900.0, 1)
    tax_3800 = derivative_trade_tax(3800.0, 1)
    assert tax_3800 == pytest.approx(2.0 * tax_1900, abs=1e-9)
    assert tax_3800 == pytest.approx(32_300.0, abs=1e-9)


def test_long_roundtrip_pnl_and_cash_matches_hand_calc():
    """Một vòng long mở @1900.0, đóng @1910.0 (1 HĐ):
    - Biểu phí mặc định:
      * Base fee (SSI + HNX): 5.700 VNĐ / lượt
      * VSD fee: 2.550 VNĐ / lượt (thu cả mở lẫn đóng theo Task 1b)
      * Thuế mở @1900: (1900 x 100.000 x 1 x 0,17 / 2) x 0,001 = 16.150 VNĐ
      * Thuế đóng @1910: (1910 x 100.000 x 1 x 0,17 / 2) x 0,001 = 16.235 VNĐ
    - Phí mở = 5.700 + 2.550 + 16.150 = 24.400 VNĐ
    - Phí đóng = 5.700 + 2.550 + 16.235 = 24.485 VNĐ
    - Tổng phí = 24.400 + 24.485 = 48.885 VNĐ
    - Lãi gộp = (1910.0 - 1900.0) x 1 x 100.000 = 1.000.000 VNĐ
    - Realized PnL = 1.000.000 - 48.885 = 951.115 VNĐ
    - Cash ban đầu = 100.000.000 VNĐ
    - Cash sau mở = 100.000.000 - 24.400 = 99.975.600 VNĐ
    - Cash sau đóng = 99.975.600 + (1.000.000 - 24.485) = 100.951.115 VNĐ.
    """
    b = DerivativePaperBroker(capital=CAP)
    open_fill = b.open_long(SYM, qty=1, price=1900.0, ts=TS)
    assert open_fill.fee == pytest.approx(24_400.0, abs=1e-9)
    assert b.cash == pytest.approx(99_975_600.0, abs=1e-9)

    close_fill = b.close(SYM, price=1910.0, ts=TS)
    assert close_fill.fee == pytest.approx(24_485.0, abs=1e-9)
    assert close_fill.pnl == pytest.approx(951_115.0, abs=1e-9)
    assert b.realized_pnl == pytest.approx(951_115.0, abs=1e-9)
    assert b.cash == pytest.approx(100_951_115.0, abs=1e-9)


def test_short_roundtrip_pnl_and_cash_matches_hand_calc():
    """Một vòng short mở @1900.0, đóng @1880.0 (1 HĐ):
    - Biểu phí mặc định:
      * Base fee (SSI + HNX): 5.700 VNĐ / lượt
      * VSD fee: 2.550 VNĐ / lượt (thu cả mở lẫn đóng theo Task 1b)
      * Thuế mở @1900: (1900 x 100.000 x 1 x 0,17 / 2) x 0,001 = 16.150 VNĐ
      * Thuế đóng @1880: (1880 x 100.000 x 1 x 0,17 / 2) x 0,001 = 15.980 VNĐ
    - Phí mở = 5.700 + 2.550 + 16.150 = 24.400 VNĐ
    - Phí đóng = 5.700 + 2.550 + 15.980 = 24.230 VNĐ
    - Tổng phí = 24.400 + 24.230 = 48.630 VNĐ
    - Lãi gộp = (1900.0 - 1880.0) x 1 x 100.000 = 2.000.000 VNĐ
    - Realized PnL = 2.000.000 - 48.630 = 1.951.370 VNĐ
    - Cash ban đầu = 100.000.000 VNĐ
    - Cash sau mở = 100.000.000 - 24.400 = 99.975.600 VNĐ
    - Cash sau đóng = 99.975.600 + (2.000.000 - 24.230) = 101.951.370 VNĐ.
    """
    b = DerivativePaperBroker(capital=CAP)
    open_fill = b.open_short(SYM, qty=1, price=1900.0, ts=TS)
    assert open_fill.fee == pytest.approx(24_400.0, abs=1e-9)
    assert b.cash == pytest.approx(99_975_600.0, abs=1e-9)

    close_fill = b.close(SYM, price=1880.0, ts=TS)
    assert close_fill.fee == pytest.approx(24_230.0, abs=1e-9)
    assert close_fill.pnl == pytest.approx(1_951_370.0, abs=1e-9)
    assert b.realized_pnl == pytest.approx(1_951_370.0, abs=1e-9)
    assert b.cash == pytest.approx(101_951_370.0, abs=1e-9)


def test_vsd_clearing_fee_charged_on_both_open_and_close():
    """Task 1b: Phí bù trừ VSDC 2.550 đ/HĐ thu trên mỗi giao dịch khớp lệnh,
    tức thu cả lúc mở vị thế lẫn lúc đóng vị thế = 5.100 đ / vòng.
    Kiểm tra độc lập với base_fee=0 và tax_rate=0:
    - Mở: phí = 2.550 đ
    - Đóng: phí = 2.550 đ
    - Tổng phí = 5.100 đ.
    """
    b = DerivativePaperBroker(
        capital=CAP,
        fee_per_contract=0.0,
        vsd_fee_per_contract=2_550.0,
        tax_rate=0.0,
    )
    open_fill = b.open_long(SYM, qty=1, price=1900.0, ts=TS)
    assert open_fill.fee == pytest.approx(2_550.0, abs=1e-9)

    close_fill = b.close(SYM, price=1900.0, ts=TS)
    assert close_fill.fee == pytest.approx(2_550.0, abs=1e-9)
    assert b.realized_pnl == pytest.approx(-5_100.0, abs=1e-9)


def test_broker_default_arguments_use_new_constants():
    """DerivativePaperBroker(capital) không truyền gì vẫn dùng đúng các hằng số mới."""
    b = DerivativePaperBroker(capital=CAP)
    assert b.fee_per_contract == DERIVATIVE_FEE_PER_CONTRACT
    assert b.fee_per_contract == 5_700.0
    assert b.vsd_fee_per_contract == DERIVATIVE_VSD_CLEARING_FEE_PER_CONTRACT
    assert b.vsd_fee_per_contract == 2_550.0
    assert b.contract_multiplier == DERIVATIVE_CONTRACT_MULTIPLIER
    assert b.contract_multiplier == 100_000.0
    assert b.initial_margin_rate == DERIVATIVE_INITIAL_MARGIN_RATE
    assert b.initial_margin_rate == 0.17
    assert b.tax_rate == DERIVATIVE_PIT_TAX_RATE
    assert b.tax_rate == 0.001

