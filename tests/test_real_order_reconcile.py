"""Unit tests cho hàm thuần decide_update trong trading/real_order_reconcile.py (Brief 103)."""

from ssi_sdk.enums.trading import OrderStatus
from ssi_sdk.models import Order

from trading.paper_broker import FEE_RATE as FEE_RATE_ESTIMATE
from trading.real_order_reconcile import (
    Update,
    decide_update,
)


def test_1_order_incomplete_returns_none():
    """1. Lệnh chưa kết thúc (f=0, c=0, status không thuộc tập kết thúc) -> None."""
    row = {
        "qty": 100,
        "price": 10_000.0,
        "side": "BUY",
        "fee": 2500.0,
        "pnl": None,
    }
    order = Order(
        filled_quantity=0,
        cancel_quantity=0,
        status=OrderStatus.PENDING,  # "PD"
    )
    res = decide_update(row, order)
    assert res is None


def test_2_buy_full_fill():
    """2. MUA 100 @10.000, khớp 100 -> filled, qty=100, fee = 10.000 × 100 × FEE_RATE_ESTIMATE."""
    row = {
        "qty": 100,
        "price": 10_000.0,
        "side": "BUY",
        "fee": 10_000.0 * 100 * FEE_RATE_ESTIMATE,
        "pnl": None,
    }
    order = Order(
        filled_quantity=100,
        cancel_quantity=0,
        avg_price=10_000.0,
        status=OrderStatus.FILLED,  # "FF"
    )
    res = decide_update(row, order)
    assert res is not None
    assert res == Update(
        status="filled",
        qty=100,
        price=10_000.0,
        fee=10_000.0 * 100 * FEE_RATE_ESTIMATE,
        pnl=None,
    )


def test_3_sell_partial_fill_and_cancelled_remaining():
    """3. BÁN 100 @12.000, row.pnl = 200.000 (tức giá vốn 10.000), khớp 40, huỷ 60,
    giá khớp 11.900 -> filled, qty=40, pnl = (11.900 − 10.000) × 40 = 76.000.
    
    Tính tay:
    - Giá vốn = row.price - row.pnl / row.qty = 12000 - 200000 / 100 = 10000.
    - PnL mới = (avg_price - giá vốn) * qty_khớp = (11900 - 10000) * 40 = 1900 * 40 = 76000.
    - Phí mới = 11900 * 40 * FEE_RATE_ESTIMATE.
    """
    row = {
        "qty": 100,
        "price": 12_000.0,
        "side": "SELL",
        "fee": 12_000.0 * 100 * FEE_RATE_ESTIMATE,
        "pnl": 200_000.0,
    }
    order = Order(
        filled_quantity=40,
        cancel_quantity=60,
        avg_price=11_900.0,
        status=OrderStatus.PARTIAL_CANCELLED,  # "FFPC"
    )
    res = decide_update(row, order)
    assert res is not None
    assert res == Update(
        status="filled",
        qty=40,
        price=11_900.0,
        fee=11_900.0 * 40 * FEE_RATE_ESTIMATE,
        pnl=76_000.0,
    )


def test_4_cancelled_order_zero_fills():
    """4. f=0, c=100 -> cancelled, fee=0, pnl=0."""
    row = {
        "qty": 100,
        "price": 12_000.0,
        "side": "SELL",
        "fee": 12_000.0 * 100 * FEE_RATE_ESTIMATE,
        "pnl": 200_000.0,
    }
    order = Order(
        filled_quantity=0,
        cancel_quantity=100,
        status=OrderStatus.CANCELLED,  # "CL"
    )
    res = decide_update(row, order)
    assert res is not None
    assert res == Update(
        status="cancelled",
        qty=0,
        price=12_000.0,
        fee=0.0,
        pnl=0.0,
    )


def test_5_terminal_status_rejected_with_zero_fills():
    """5. f=0, c=0 nhưng status thuộc tập kết thúc (ví dụ bị từ chối) -> cancelled."""
    row = {
        "qty": 100,
        "price": 10_000.0,
        "side": "BUY",
        "fee": 2500.0,
        "pnl": None,
    }
    order = Order(
        filled_quantity=0,
        cancel_quantity=0,
        status=OrderStatus.REJECTED,  # "RJ"
    )
    res = decide_update(row, order)
    assert res is not None
    assert res == Update(
        status="cancelled",
        qty=0,
        price=10_000.0,
        fee=0.0,
        pnl=0.0,
    )


def test_6_no_avg_price_falls_back_to_row_price():
    """6. Không có trường giá khớp (avg_price=0 hoặc None) -> dùng row.price."""
    row = {
        "qty": 50,
        "price": 25_000.0,
        "side": "BUY",
        "fee": 50 * 25_000.0 * FEE_RATE_ESTIMATE,
        "pnl": None,
    }
    order = Order(
        filled_quantity=50,
        cancel_quantity=0,
        avg_price=0,  # Không có giá khớp trung bình
        status=OrderStatus.FILLED,
    )
    res = decide_update(row, order)
    assert res is not None
    assert res.price == 25_000.0
    assert res.fee == 50 * 25_000.0 * FEE_RATE_ESTIMATE


def test_7_sell_order_with_none_pnl_keeps_none():
    """7. row.pnl = None với lệnh BÁN -> pnl giữ None, không nổ."""
    row = {
        "qty": 100,
        "price": 15_000.0,
        "side": "SELL",
        "fee": 15_000.0 * 100 * FEE_RATE_ESTIMATE,
        "pnl": None,
    }
    order = Order(
        filled_quantity=100,
        cancel_quantity=0,
        avg_price=15_200.0,
        status=OrderStatus.FILLED,
    )
    res = decide_update(row, order)
    assert res is not None
    assert res.pnl is None
    assert res.status == "filled"
    assert res.qty == 100
    assert res.price == 15_200.0
