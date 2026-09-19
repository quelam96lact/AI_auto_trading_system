"""Xác nhận thủ công 1 pending_real_orders và gửi lệnh THẬT lên SSI.

Chạy: uv run --with ssi-sdk python scripts/confirm_real_order.py <id>

Đây là script thủ công — KHÔNG được gọi tự động từ engine hay cronjob.
Khi `real_trading_enabled=false` (dry-run): chỉ log + ghi DB, không gọi SSI.
Khi `real_trading_enabled=true`: gọi `place_limit_order` thật bằng tiền thật.
"""

import argparse
import sys
import traceback
from datetime import datetime

# 2 import dưới chỉ tham chiếu class/enum, không có I/O — dry-run (real_trading_enabled=false)
# không thực sự kết nối SSI dù các symbol này được import ở module level.
from ssi_sdk import AsyncTrading
from ssi_sdk.enums import OrderSide

from trading.alerts import alert
from trading.calendar_vn import TZ
from trading.collector.ssi_auth import ensure_authenticated
from trading.config import Config, load_config
from trading.paper_broker import FEE_RATE
from trading.storage.db import Storage

FEE_RATE_ESTIMATE = FEE_RATE  # 0.25% giá trị lệnh — biểu phí SSI công khai, đặt lệnh
# Online (không qua môi giới), giá trị GD dưới 100 triệu đồng/ngày/tài khoản.
# Nguồn: https://www.ssi.com.vn/khach-hang-ca-nhan/bieu-phi/bieu-gia-dich-vu-giao-dich-chung-khoan
# (hiệu lực 10/10/2025). Vẫn là ƯỚC TÍNH cho account cụ thể (bậc GD cao hơn có
# rate khác: 0.30%/0.25% — chưa hỗ trợ), KHÔNG PHẢI phí thật trả về từ SSI SDK
# per-order (PlaceOrderResponse/Order chỉ có id/status/giá/số lượng, EquityPPMMR.fees
# chỉ là tổng luỹ kế cấp tài khoản) — xem PLAN_REAL_ORDER_PLACEMENT.md.


def _print_order(order: dict) -> None:
    print(f"Pending order #{order['id']}:")
    print(f"  account_no: {order['account_no']}")
    print(f"  symbol:     {order['symbol']}")
    print(f"  side:       {order['side']}")
    print(f"  quantity:   {order['quantity']}")
    print(f"  price:      {order['price']}")
    print(f"  created_at: {order['created_at']}")
    print(f"  expires_at: {order['expires_at']}")
    print(f"  status:     {order['status']}")


async def confirm(
    cfg: Config,
    storage: Storage,
    order_id: int,
    confirm_input: str,
    place_order_fn=None,
    max_buy_sell_fn=None,
) -> None:
    """Xác nhận (hoặc từ chối) 1 pending order.

    Args:
        cfg: config đã load.
        storage: Storage instance.
        order_id: id pending order cần xử lý.
        confirm_input: chuỗi ngườ dùng nhập; "YES" để thực sự đặt, bất kỳ giá trị
            nào khác để từ chối.
        place_order_fn: optional callable để inject fake place_order trong test.
            Nếu None, dùng `AsyncTrading.trading.place_limit_order` thật.
        max_buy_sell_fn: optional callable để inject fake max buy/sell trong test.
            Nếu None, dùng `AsyncTrading.trading.get_max_buy_sell_at_market_price` thật.
    """
    order = storage.get_pending_order(order_id)
    if order is None:
        print(f"!! Lỗi: pending order id={order_id} không tồn tại.", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(TZ)
    if order["status"] != "pending" or order["expires_at"] <= now:
        print(
            f"!! Order id={order_id} không ở trạng thái chờ xác nhận hợp lệ: "
            f"status={order['status']}, expires_at={order['expires_at']}, now={now}"
        )
        sys.exit(0)

    _print_order(order)

    if order["side"] == "BUY" and order["quantity"] % 100 != 0:
        print(
            f"!! Lỗi dữ liệu: lệnh BUY số lượng {order['quantity']} không phải bội số "
            f"100 (lô tối thiểu HOSE/HNX). Không xác nhận lệnh này — kiểm tra lại "
            f"trading/real_orders.py, có thể có bug ở nơi sinh pending order."
        )
        storage.update_pending_order_status(order_id, "failed")
        sys.exit(1)

    if confirm_input != "YES":
        storage.update_pending_order_status(order_id, "rejected")
        print("Đã huỷ, không đặt lệnh.")
        sys.exit(0)

    if not cfg.real_trading_enabled:
        print(
            f"[DRY-RUN] SẼ đặt lệnh: {order['side']} {order['quantity']} {order['symbol']} "
            f"@ {order['price']} (account {order['account_no']}) — "
            f"real_trading_enabled=false nên KHÔNG gọi API thật."
        )
        storage.update_pending_order_status(order_id, "confirmed")
        alert(
            "INFO",
            "real order dry-run confirmed",
            id=order_id,
            symbol=order["symbol"],
            side=order["side"],
            qty=order["quantity"],
            price=order["price"],
        )
        sys.exit(0)

    auth = None
    try:
        auth = await ensure_authenticated(cfg, storage)
        auth.config.private_key = cfg.ssi_private_key
        trading_client = AsyncTrading(auth)

        if max_buy_sell_fn is None:
            mbs = await trading_client.trading.get_max_buy_sell_at_market_price(
                order["account_no"], order["symbol"]
            )
        else:
            mbs = await max_buy_sell_fn(order["account_no"], order["symbol"])

        available = (
            mbs.max_buy_quantity if order["side"] == "BUY" else mbs.max_sell_quantity
        )
        if available < order["quantity"]:
            print(
                f"!! DỪNG — sức {'mua' if order['side'] == 'BUY' else 'bán'} thật hiện tại "
                f"({available}) < số lượng lệnh ({order['quantity']}). KHÔNG đặt lệnh."
            )
            storage.update_pending_order_status(order_id, "failed")
            t = alert(
                "CRITICAL",
                "real order aborted - insufficient real buying/selling power at confirm time",
                id=order_id,
                symbol=order["symbol"],
                side=order["side"],
                requested_qty=order["quantity"],
                available_qty=available,
            )
            if t is not None:
                t.join(timeout=6)
            sys.exit(1)

        side = OrderSide.BUY if order["side"] == "BUY" else OrderSide.SELL
        if place_order_fn is None:
            placed = await trading_client.trading.place_limit_order(
                order["account_no"],
                order["symbol"],
                side,
                order["quantity"],
                order["price"],
            )
        else:
            placed = await place_order_fn(
                order["account_no"],
                order["symbol"],
                side,
                order["quantity"],
                order["price"],
            )

        pnl = None
        if order["side"] == "SELL":
            positions = storage.read_real_positions(order["account_no"])
            real_pos = positions.get(order["symbol"])
            if real_pos is not None:
                pnl = (order["price"] - real_pos.avg_price) * order["quantity"]

        fee = order["price"] * order["quantity"] * FEE_RATE_ESTIMATE

        storage.update_pending_order_status(
            order_id, "placed", ssi_order_id=placed.order_id
        )
        storage.write_real_order_fill(
            account_no=order["account_no"],
            ts=datetime.now(TZ),
            symbol=order["symbol"],
            side=order["side"],
            qty=order["quantity"],
            price=order["price"],
            fee=fee,
            pnl=pnl,
            ssi_order_id=placed.order_id,
            status="placed",
        )
        print(
            f"Đã đặt lệnh THẬT: order_id={placed.order_id}, "
            f"client_request_id={placed.client_request_id}, status={placed.status}"
        )
        t = alert(
            "WARN",
            "REAL order placed",
            id=order_id,
            symbol=order["symbol"],
            side=order["side"],
            qty=order["quantity"],
            price=order["price"],
            ssi_order_id=placed.order_id,
            status=placed.status,
        )
        if t is not None:
            t.join(timeout=6)
    except Exception as exc:
        storage.update_pending_order_status(order_id, "failed")
        traceback.print_exc()
        t = alert("CRITICAL", "real order placement FAILED", id=order_id, error=str(exc))
        if t is not None:
            t.join(timeout=6)
        sys.exit(1)
    finally:
        if auth is not None:
            await auth.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Xác nhận thủ công 1 lệnh chờ thật")
    ap.add_argument("order_id", type=int, help="id trong bảng pending_real_orders")
    ap.add_argument(
        "--config", default="config/config.yaml", help="path tới config yaml"
    )
    args = ap.parse_args()

    cfg = load_config(args.config)
    storage = Storage(cfg.db_dsn)

    confirm_input = input(
        "Nhập YES để xác nhận đặt lệnh THẬT (Enter/bất kỳ để huỷ): "
    ).strip()

    import asyncio

    asyncio.run(confirm(cfg, storage, args.order_id, confirm_input))


if __name__ == "__main__":
    main()
