"""Bộ kiểm thử đơn vị cho trading/ssi_orders.py (Brief đợt 176).

Kiểm chứng việc đọc số lượng khớp (filledQty) và số lượng huỷ (cancelQty)
từ lịch sử lệnh SSI API, phân trang, không monkey-patch SDK, và đầu-cuối đối soát.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from ssi_sdk.enums.trading import OrderStatus
from ssi_sdk.models.portfolio import Order

from trading.calendar_vn import TZ
from trading.real_order_reconcile import decide_update
from trading.ssi_orders import fetch_order_history, order_from_raw
from trading.storage.db import PlacedRealFill

# --- Fixtures dữ liệu JSON thô theo đúng các khóa của SSI API /api/v3/trading/orderBook ---

def _make_raw_ff() -> dict[str, Any]:
    return {
        "avgPrice": 58500.0,
        "cancelQty": 0,
        "clientRequestId": "req_ff",
        "filledQty": 500,
        "inputTime": "2026/10/05 13:54:20",
        "message": "",
        "modifiedTime": "",
        "orderId": "order_ff_1",
        "orderStatus": "FF",
        "orderType": "LO",
        "price": 58500.0,
        "quantity": 500,
        "side": "B",
        "symbol": "CTD",
    }


def _make_raw_ffpc() -> dict[str, Any]:
    return {
        "avgPrice": 27150.0,
        "cancelQty": 308,
        "clientRequestId": "req_ffpc",
        "filledQty": 92,
        "inputTime": "2026/10/06 13:29:35",
        "message": "",
        "modifiedTime": "",
        "orderId": "order_ffpc_1",
        "orderStatus": "FFPC",
        "orderType": "LO",
        "price": 27150.0,
        "quantity": 400,
        "side": "S",
        "symbol": "TCX",
    }


def _make_raw_cl() -> dict[str, Any]:
    return {
        "avgPrice": 0.0,
        "cancelQty": 100,
        "clientRequestId": "req_cl",
        "filledQty": 0,
        "inputTime": "2026/10/06 09:15:00",
        "message": "",
        "modifiedTime": "",
        "orderId": "order_cl_1",
        "orderStatus": "CL",
        "orderType": "LO",
        "price": 25000.0,
        "quantity": 100,
        "side": "B",
        "symbol": "HPG",
    }


class FakeRestClient:
    def __init__(self, pages_responses: list[dict[str, Any]]):
        self.pages_responses = pages_responses
        self.calls: list[dict[str, Any]] = []

    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params_dict = dict(params or {})
        self.calls.append({"endpoint": endpoint, "params": params_dict})
        page = params_dict.get("pageIndex", 1)
        if 1 <= page <= len(self.pages_responses):
            return self.pages_responses[page - 1]
        return {"orderList": [], "totalRecord": 0}


class FakePortfolio:
    def __init__(self, rest_client: FakeRestClient):
        self._rest = rest_client


# --- 1. Test order_from_raw đọc đúng số lượng và trạng thái ---

def test_1_order_from_raw() -> None:
    account_no = "0000000"

    # Lệnh FF
    o_ff = order_from_raw(_make_raw_ff(), account_no)
    assert o_ff.filled_quantity == 500
    assert o_ff.cancel_quantity == 0
    assert o_ff.status == OrderStatus.FILLED
    assert o_ff.avg_price == 58500.0

    # Lệnh FFPC
    o_ffpc = order_from_raw(_make_raw_ffpc(), account_no)
    assert o_ffpc.filled_quantity == 92
    assert o_ffpc.cancel_quantity == 308
    assert o_ffpc.status == OrderStatus.PARTIAL_CANCELLED
    assert o_ffpc.avg_price == 27150.0

    # Lệnh CL
    o_cl = order_from_raw(_make_raw_cl(), account_no)
    assert o_cl.filled_quantity == 0
    assert o_cl.cancel_quantity == 100
    assert o_cl.status == OrderStatus.CANCELLED


# --- 2. Test Khóa kiểu cũ và không ghi đè khi có cả hai khóa ---

def test_2_khoa_kieu_cu_va_khong_ghi_de_khi_co_ca_hai() -> None:
    account_no = "0000000"

    # Có cả hai khóa: filledQuantity phải được ưu tiên giữ nguyên, không ghi đè từ filledQty
    raw_both = {
        "filledQuantity": 150,
        "filledQty": 500,
        "cancelQuantity": 20,
        "cancelQty": 80,
        "orderId": "1",
        "symbol": "AAA",
        "side": "B",
        "orderStatus": "FF",
    }
    o_both = order_from_raw(raw_both, account_no)
    assert o_both.filled_quantity == 150
    assert o_both.cancel_quantity == 20

    # Chỉ có khóa kiểu cũ
    raw_old_only = {
        "filledQuantity": 250,
        "cancelQuantity": 30,
        "orderId": "2",
        "symbol": "AAA",
        "side": "B",
        "orderStatus": "FF",
    }
    o_old = order_from_raw(raw_old_only, account_no)
    assert o_old.filled_quantity == 250
    assert o_old.cancel_quantity == 30


# --- 3. Test Phân trang lấy đủ tất cả các trang và kiểm tra totalRecord ---

@pytest.mark.asyncio
async def test_3_phan_trang() -> None:
    # 3 trang (2 + 2 + 1, totalRecord = 5)
    raw1 = _make_raw_ff()
    raw1["orderId"] = "o1"
    raw2 = _make_raw_ff()
    raw2["orderId"] = "o2"
    raw3 = _make_raw_ff()
    raw3["orderId"] = "o3"
    raw4 = _make_raw_ff()
    raw4["orderId"] = "o4"
    raw5 = _make_raw_ff()
    raw5["orderId"] = "o5"

    page1 = {"orderList": [raw1, raw2], "totalRecord": 5, "accountNo": "0000000"}
    page2 = {"orderList": [raw3, raw4], "totalRecord": 5, "accountNo": "0000000"}
    page3 = {"orderList": [raw5], "totalRecord": 5, "accountNo": "0000000"}

    rest = FakeRestClient([page1, page2, page3])
    portfolio = FakePortfolio(rest)

    orders = await fetch_order_history(
        portfolio, "0000000", "2026/08/01", "2026/10/10", page_size=2
    )

    assert len(orders) == 5
    assert len(rest.calls) == 3
    assert [c["params"]["pageIndex"] for c in rest.calls] == [1, 2, 3]
    assert [o.order_id for o in orders] == ["o1", "o2", "o3", "o4", "o5"]

    # Kiểm tra mismatch: totalRecord 6 mà chỉ có 5 -> ValueError
    p1_mis = {"orderList": [raw1, raw2], "totalRecord": 6, "accountNo": "0000000"}
    p2_mis = {"orderList": [raw3, raw4], "totalRecord": 6, "accountNo": "0000000"}
    p3_mis = {"orderList": [raw5], "totalRecord": 6, "accountNo": "0000000"}
    rest_mismatch = FakeRestClient([p1_mis, p2_mis, p3_mis])
    portfolio_mismatch = FakePortfolio(rest_mismatch)

    with pytest.raises(ValueError, match="totalRecord"):
        await fetch_order_history(
            portfolio_mismatch, "0000000", "2026/08/01", "2026/10/10", page_size=2
        )


# --- 4. Test Không monkey-patch SDK ---

def test_4_khong_monkey_patch_sdk() -> None:
    import trading.ssi_orders  # noqa: F401

    # Order.from_dict của SDK nguyên bản vẫn đọc filledQuantity (thiếu filledQty -> 0)
    o = Order.from_dict({"filledQty": 7, "orderId": "x"}, "x")
    assert o.filled_quantity == 0


# --- 5. Test Đầu-cuối đối soát với decide_update ---

@pytest.mark.asyncio
async def test_5_dau_cuoi_doi_soat() -> None:
    raw_ff = _make_raw_ff()
    raw_ffpc = _make_raw_ffpc()

    rest = FakeRestClient([
        {"orderList": [raw_ff, raw_ffpc], "totalRecord": 2, "accountNo": "0000000"}
    ])
    portfolio = FakePortfolio(rest)

    orders = await fetch_order_history(
        portfolio, "0000000", "2026/10/01", "2026/10/10"
    )
    assert len(orders) == 2
    orders_by_id = {o.order_id: o for o in orders}

    # Đối soát lệnh FF
    row_ff = PlacedRealFill(
        id=1,
        ts=datetime(2026, 10, 5, 13, 50, tzinfo=TZ),
        account_no="0000000",
        symbol="CTD",
        side="BUY",
        qty=500,
        price=58500.0,
        fee=100.0,
        pnl=None,
        ssi_order_id="order_ff_1",
        status="placed",
    )
    up_ff = decide_update(row_ff, orders_by_id["order_ff_1"])
    assert up_ff is not None
    assert up_ff.status == "filled"
    assert up_ff.qty == 500
    assert up_ff.price == 58500.0

    # Đối soát lệnh FFPC (khớp một phần)
    row_ffpc = PlacedRealFill(
        id=2,
        ts=datetime(2026, 10, 6, 13, 20, tzinfo=TZ),
        account_no="0000000",
        symbol="TCX",
        side="SELL",
        qty=400,
        price=27150.0,
        fee=100.0,
        pnl=0.0,
        ssi_order_id="order_ffpc_1",
        status="placed",
    )
    up_ffpc = decide_update(row_ffpc, orders_by_id["order_ffpc_1"])
    assert up_ffpc is not None
    assert up_ffpc.status == "filled"
    assert up_ffpc.qty == 92
    assert up_ffpc.price == 27150.0
    assert up_ffpc.qty < row_ffpc.qty  # Nhánh khớp một phần
