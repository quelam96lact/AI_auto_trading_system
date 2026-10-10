"""Test suite cho scripts/report_real_account_performance.py (Brief đợt 174 & 176).

TDD hoàn toàn trên lệnh giả, KHÔNG gọi mạng, KHÔNG ghi DB:
1. test_mot_vong_lai_rong_tinh_tay_dung_toi_dong
2. test_fifo_dung_thu_tu_lo
3. test_lenh_khong_khop_hoac_huy_bi_bo
4. test_khop_mot_phan_chi_tinh_phan_khop
5. test_ban_khong_co_gia_von_trong_ky_vao_muc_rieng
6. test_khong_co_loi_goi_ghi_nao
"""


import pytest
from ssi_sdk.models.portfolio import Order, OrderSide, OrderStatus

from scripts.report_real_account_performance import (
    build_performance_report,
    match_fifo_orders,
)


def _make_order(
    symbol: str,
    side: OrderSide,
    quantity: int,
    filled_quantity: int,
    avg_price: float,
    input_time: str,
    order_id: str = "ord1",
    status: OrderStatus = OrderStatus.FILLED,
) -> Order:
    return Order(
        account_no="0434226",
        order_id=order_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        filled_quantity=filled_quantity,
        avg_price=avg_price,
        status=status,
        input_time=input_time,
    )


# --- 1. Test Một vòng lãi ròng tính tay đúng tới đồng --------------------------------

def test_mot_vong_lai_rong_tinh_tay_dung_toi_dong() -> None:
    # Mua 1.000 @ 10.000 rồi bán 1.000 @ 11.000
    b = _make_order("AAA", OrderSide.BUY, 1000, 1000, 10_000.0, "2026/09/01 10:00:00", order_id="b1")
    s = _make_order("AAA", OrderSide.SELL, 1000, 1000, 11_000.0, "2026/09/10 14:00:00", order_id="s1")

    round_trips, open_pos, unmatch = match_fifo_orders([b, s])

    assert len(round_trips) == 1
    assert len(open_pos) == 0
    assert len(unmatch) == 0

    rt = round_trips[0]
    assert rt.symbol == "AAA"
    assert rt.qty == 1000
    assert rt.entry_price == 10_000.0
    assert rt.exit_price == 11_000.0
    assert rt.holding_days == 9

    # Tính tay đúng tới đồng:
    # Mua: 10_000_000 VND -> Phí mua = 10_000_000 * 0.0028 = 28_000 VND
    # Vốn vào (gồm phí mua) = 10_028_000 VND
    assert rt.buy_value == 10_000_000.0
    assert rt.buy_fee == 28_000.0

    # Bán: 11_000_000 VND -> Phí bán = 11_000_000 * 0.0028 = 30_800 VND
    # Thuế bán = 11_000_000 * 0.001 = 11_000 VND
    # Tiền về ròng = 11_000_000 - 30_800 - 11_000 = 10_958_200 VND
    assert rt.sell_value == 11_000_000.0
    assert rt.sell_fee == 30_800.0
    assert rt.sell_tax == 11_000.0

    # Lãi gộp = 11_000_000 - 10_000_000 = 1_000_000 VND
    assert rt.gross_pnl == 1_000_000.0

    # Lãi ròng = 10_958_200 - 10_028_000 = 930_200 VND
    assert rt.net_pnl == 930_200.0


# --- 2. Test FIFO đúng thứ tự lô ----------------------------------------------------

def test_fifo_dung_thu_tu_lo() -> None:
    # Mua 500 @ 10.000 (01/09), Mua 500 @ 12.000 (05/09), Bán 700 @ 13.000 (10/09)
    b1 = _make_order("AAA", OrderSide.BUY, 500, 500, 10_000.0, "2026/09/01 10:00:00", order_id="b1")
    b2 = _make_order("AAA", OrderSide.BUY, 500, 500, 12_000.0, "2026/09/05 10:00:00", order_id="b2")
    s1 = _make_order("AAA", OrderSide.SELL, 700, 700, 13_000.0, "2026/09/10 14:00:00", order_id="s1")

    round_trips, open_pos, _unmatch = match_fifo_orders([b1, b2, s1], mode="FIFO")

    assert len(round_trips) == 2
    # Vòng 1 dùng 500 lô đầu @ 10.000
    assert round_trips[0].qty == 500
    assert round_trips[0].entry_price == 10_000.0
    assert round_trips[0].exit_price == 13_000.0

    # Vòng 2 dùng 200 lô sau @ 12.000
    assert round_trips[1].qty == 200
    assert round_trips[1].entry_price == 12_000.0
    assert round_trips[1].exit_price == 13_000.0

    # Còn mở: 300 @ 12.000
    assert len(open_pos) == 1
    assert open_pos[0].qty == 300
    assert open_pos[0].entry_price == 12_000.0
    assert open_pos[0].symbol == "AAA"


# --- 3. Test Lệnh không khớp hoặc huỷ bị bỏ ------------------------------------------

def test_lenh_khong_khop_hoac_huy_bi_bo() -> None:
    # Lệnh filled_quantity = 0 hoặc CANCELLED không khớp
    b_cancelled = _make_order("AAA", OrderSide.BUY, 1000, 0, 10_000.0, "2026/09/01 09:15:00", status=OrderStatus.CANCELLED)
    b_pending = _make_order("AAA", OrderSide.BUY, 1000, 0, 10_000.0, "2026/09/01 09:20:00", status=OrderStatus.PENDING)

    round_trips, open_pos, unmatch = match_fifo_orders([b_cancelled, b_pending])
    assert len(round_trips) == 0
    assert len(open_pos) == 0
    assert len(unmatch) == 0

    report = build_performance_report("0434226", "2026-09-01", "2026-09-30", [b_cancelled, b_pending])
    assert report.filled_orders_count == 0
    assert report.total_buy_value == 0.0
    assert report.total_sell_value == 0.0


# --- 4. Test Khớp một phần chỉ tính phần khớp --------------------------------------

def test_khop_mot_phan_chi_tinh_phan_khop() -> None:
    # quantity = 1000, filled_quantity = 400
    b_part = _make_order(
        "AAA",
        OrderSide.BUY,
        quantity=1000,
        filled_quantity=400,
        avg_price=10_000.0,
        input_time="2026/09/01 10:00:00",
        status=OrderStatus.PARTIAL_CANCELLED,
    )
    s_part = _make_order(
        "AAA",
        OrderSide.SELL,
        quantity=1000,
        filled_quantity=400,
        avg_price=12_000.0,
        input_time="2026/09/05 14:00:00",
        status=OrderStatus.PARTIAL_FILLED,
    )

    round_trips, _open_pos, _unmatch = match_fifo_orders([b_part, s_part])
    assert len(round_trips) == 1
    assert round_trips[0].qty == 400
    assert round_trips[0].buy_value == 4_000_000.0
    assert round_trips[0].sell_value == 4_800_000.0

    report = build_performance_report("0434226", "2026-09-01", "2026-09-30", [b_part, s_part])
    assert report.total_buy_value == 4_000_000.0
    assert report.total_sell_value == 4_800_000.0


# --- 5. Test Bán không có giá vốn trong kỳ vào mục riêng ----------------------------

def test_ban_khong_co_gia_von_trong_ky_vao_muc_rieng() -> None:
    # Chỉ có lệnh bán 500 @ 15.000 (mua trước kỳ --from)
    s = _make_order("VCB", OrderSide.SELL, 500, 500, 15_000.0, "2026/09/02 11:00:00")

    round_trips, open_pos, unmatch = match_fifo_orders([s])
    assert len(round_trips) == 0
    assert len(open_pos) == 0
    assert len(unmatch) == 1
    assert unmatch[0].symbol == "VCB"
    assert unmatch[0].qty == 500
    assert unmatch[0].exit_price == 15_000.0
    assert unmatch[0].sell_value == 7_500_000.0

    report = build_performance_report("0434226", "2026-09-01", "2026-09-30", [s])
    assert len(report.round_trips) == 0
    assert len(report.unmatched_sells) == 1
    assert report.total_net_pnl == 0.0  # Không vào PnL các vòng


# --- 6. Test Không có lời gọi ghi nào (Spy trên Client và Storage) -------------------

class SpyPortfolioClient:
    def __init__(self, orders: list[Order]):
        self.orders = orders
        self.calls: list[str] = []

    async def get_historical_orders(self, account_no: str, from_date: str, to_date: str, **kwargs) -> list[Order]:
        self.calls.append("get_historical_orders")
        return list(self.orders)

    async def place_order(self, *args, **kwargs):
        self.calls.append("place_order")
        raise RuntimeError("Write method place_order called!")

    async def cancel_order(self, *args, **kwargs):
        self.calls.append("cancel_order")
        raise RuntimeError("Write method cancel_order called!")


class SpyStorage:
    def __init__(self):
        self.write_calls: list[str] = []

    def load_ssi_token(self, timeout=None):
        return {"access_token": "dummy", "refresh_token_expires_at": 9999999999}

    def write_order(self, *args, **kwargs):
        self.write_calls.append("write_order")

    def update_real_order_fill(self, *args, **kwargs):
        self.write_calls.append("update_real_order_fill")


@pytest.mark.asyncio
async def test_khong_co_loi_goi_ghi_nao() -> None:
    orders = [
        _make_order("AAA", OrderSide.BUY, 100, 100, 10_000.0, "2026/09/01 10:00:00"),
        _make_order("AAA", OrderSide.SELL, 100, 100, 11_000.0, "2026/09/02 10:00:00"),
    ]
    spy_portfolio = SpyPortfolioClient(orders)
    spy_storage = SpyStorage()

    all_orders = await spy_portfolio.get_historical_orders(
        "0434226", "2026/08/01", "2026/10/10"
    )
    rep = build_performance_report("0434226", "2026-08-01", "2026-10-10", all_orders)

    assert len(rep.round_trips) == 1
    # Kiểm tra spy portfolio: chỉ có get_historical_orders, không có place_order hay cancel_order
    assert spy_portfolio.calls == ["get_historical_orders"]
    # Kiểm tra spy storage: không có write_calls nào
    assert spy_storage.write_calls == []
