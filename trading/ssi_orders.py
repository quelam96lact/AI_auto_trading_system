"""Hàm tiện ích đọc và lấy lịch sử lệnh từ SSI API (Brief đợt 176).

Khắc phục lệch tên trường giữa SSI API (filledQty, cancelQty) và SDK (filledQuantity, cancelQuantity)
mà KHÔNG monkey-patch SDK.
"""

from __future__ import annotations

from typing import Any

from ssi_sdk.models.portfolio import Order
from ssi_sdk.services.portfolio import EP_ORDER_HISTORY


def order_from_raw(data: dict[str, Any], account_no: str) -> Order:
    """Parse dict lệnh thô từ API SSI thành Order đối tượng.

    Ánh xạ trường 'filledQty' -> 'filledQuantity' và 'cancelQty' -> 'cancelQuantity'
    nếu các trường cũ chưa có trong dict (không ghi đè nếu đã có sẵn).
    """
    d = dict(data)
    if "filledQuantity" not in d and "filledQty" in d:
        d["filledQuantity"] = d["filledQty"]
    if "cancelQuantity" not in d and "cancelQty" in d:
        d["cancelQuantity"] = d["cancelQty"]
    return Order.from_dict(d, account_no=account_no)


async def fetch_order_history(
    portfolio: Any,
    account_no: str,
    from_date: str,
    to_date: str,
    page_size: int = 100,
) -> list[Order]:
    """Lấy toàn bộ lịch sử lệnh từ SSI API qua tất cả các trang.

    Gọi endpoint EP_ORDER_HISTORY qua portfolio._rest.get, đi từ trang 1
    tới khi đủ totalRecord hoặc gặp trang rỗng.
    Parse từng lệnh bằng order_from_raw.
    Ném ValueError nếu số lệnh lấy về không khớp totalRecord.
    """
    page = 1
    orders: list[Order] = []
    total_record: int | None = None

    while True:
        params = {
            "accountNo": account_no,
            "from": from_date,
            "to": to_date,
            "pageIndex": page,
            "pageSize": page_size,
        }
        resp = await portfolio._rest.get(EP_ORDER_HISTORY, params=params)
        raw_list = resp.get("orderList") or []
        # Sua cua Claude khi audit: thieu totalRecord thi coi la 0 nhu SDK (OrderBook.from_dict),
        # de roi vao ValueError ro rang ben duoi thay vi TypeError khi so sanh voi None.
        total_record = int(resp.get("totalRecord") or 0)

        for raw_order in raw_list:
            orders.append(order_from_raw(raw_order, account_no))

        if len(orders) >= total_record or not raw_list:
            break
        page += 1

    if total_record is not None and len(orders) != total_record:
        raise ValueError(
            f"Số lệnh lấy về ({len(orders)}) không khớp totalRecord ({total_record})"
        )

    return orders
