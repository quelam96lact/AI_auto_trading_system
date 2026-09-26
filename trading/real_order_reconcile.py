"""Mô-đun đối soát lệnh thật giữa sổ lệnh SSI và cơ sở dữ liệu hệ thống (Brief 103).

Quyết định cập nhật trạng thái dòng `real_order_fills` (từ 'placed' sang 'filled' hoặc 'cancelled')
dựa trên dữ liệu sổ lệnh thật từ SSI SDK.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ssi_sdk.enums.trading import OrderStatus

from trading.paper_broker import FEE_RATE as FEE_RATE_ESTIMATE

if TYPE_CHECKING:
    from trading.storage.db import PlacedRealFill

# Tập các trạng thái kết thúc (terminal statuses) của SSI SDK:
# - OrderStatus.FILLED ("FF"): ssi_sdk/enums/trading.py:35
# - OrderStatus.PARTIAL_CANCELLED ("FFPC"): ssi_sdk/enums/trading.py:37
# - OrderStatus.CANCELLED ("CL"): ssi_sdk/enums/trading.py:40
# - OrderStatus.REJECTED ("RJ"): ssi_sdk/enums/trading.py:41
# - OrderStatus.EXPIRED ("EX"): ssi_sdk/enums/trading.py:42
# SDK luon parse status thanh enum (ssi_sdk/models/portfolio.py:725: OrderStatus(...)), nen chi
# can enum - ban chep chuoi "FF"/"CL"... truoc day khong bao gio khop va co the lech (audit dot 103).
DEFAULT_TERMINAL_STATUSES: frozenset[OrderStatus] = frozenset({
    OrderStatus.FILLED,
    OrderStatus.PARTIAL_CANCELLED,
    OrderStatus.CANCELLED,
    OrderStatus.REJECTED,
    OrderStatus.EXPIRED,
})


@dataclass(frozen=True)
class Update:
    """Kết quả cập nhật dòng lệnh thật."""

    status: str
    qty: int
    price: float
    fee: float
    pnl: float | None


def decide_update(
    row: "PlacedRealFill",
    order: Any,
    terminal_statuses: frozenset[Any] | set[Any] = DEFAULT_TERMINAL_STATUSES,
) -> Update | None:
    """Hàm thuần quyết định cập nhật dòng real_order_fills có status='placed'.

    Args:
        row: Một dòng real_order_fills có status='placed' (gồm qty, price, side, fee, pnl).
        order: Đối tượng Order tương ứng của SSI SDK.
        terminal_statuses: Tập trạng thái kết thúc của Order.

    Returns:
        Update(...) nếu lệnh đã kết thúc và cần cập nhật; None nếu lệnh chưa kết thúc.
    """
    row_qty = row.qty
    row_price = float(row.price)
    row_side = row.side
    row_pnl = row.pnl

    f = int(getattr(order, "filled_quantity", 0) or 0)
    c = int(getattr(order, "cancel_quantity", 0) or 0)
    q = int(row_qty)

    order_status = getattr(order, "status", None)
    is_terminal_status = order_status in terminal_statuses

    is_finished = (f + c >= q) or is_terminal_status
    if not is_finished:
        return None

    # Giá khớp: dùng giá khớp trung bình của SDK nếu có và > 0; nếu không thì dùng giá đặt gốc (row.price)
    avg_price = getattr(order, "avg_price", 0)
    if avg_price is not None and float(avg_price) > 0:
        match_price = float(avg_price)
    else:
        match_price = row_price

    if f == 0:
        return Update(
            status="cancelled",
            qty=0,
            price=row_price,
            fee=0.0,
            pnl=0.0,
        )

    match_qty = min(f, q)
    fee = match_price * match_qty * FEE_RATE_ESTIMATE

    if row_side == "BUY":
        pnl = None
    else:
        # Lệnh BÁN: Tính lại pnl theo giá vốn gốc
        # Giá vốn = row.price - row.pnl / row.qty (từ confirm_real_order.py:178: pnl = (giá đặt - giá vốn) * qty)
        if row_pnl is None:
            pnl = None
        else:
            cost_price = row_price - (float(row_pnl) / q)
            pnl = (match_price - cost_price) * match_qty

    return Update(
        status="filled",
        qty=match_qty,
        price=match_price,
        fee=fee,
        pnl=pnl,
    )
