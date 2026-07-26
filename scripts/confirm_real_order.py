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

from ssi_sdk import AsyncTrading
from ssi_sdk.enums import OrderSide
# 2 import trên chỉ tham chiếu class/enum, không có I/O — dry-run (real_trading_enabled=false)
# không thực sự kết nối SSI dù các symbol này được import ở module level.

from trading.alerts import alert
from trading.calendar_vn import TZ
from trading.collector.ssi_auth import ensure_authenticated
from trading.config import Config, load_config
from trading.storage.db import Storage


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

        storage.update_pending_order_status(order_id, "placed", ssi_order_id=placed.order_id)
        storage.write_real_order_fill(
            account_no=order["account_no"],
            ts=datetime.now(TZ),
            symbol=order["symbol"],
            side=order["side"],
            qty=order["quantity"],
            price=order["price"],
            fee=0.0,
            pnl=None,
            ssi_order_id=placed.order_id,
            status="placed",
        )
        print(
            f"Đã đặt lệnh THẬT: order_id={placed.order_id}, "
            f"client_request_id={placed.client_request_id}, status={placed.status}"
        )
        alert(
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
    except Exception as exc:
        storage.update_pending_order_status(order_id, "failed")
        traceback.print_exc()
        alert("CRITICAL", "real order placement FAILED", id=order_id, error=str(exc))
        sys.exit(1)
    finally:
        if auth is not None:
            await auth.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Xác nhận thủ công 1 lệnh chờ thật")
    ap.add_argument("order_id", type=int, help="id trong bảng pending_real_orders")
    ap.add_argument("--config", default="config/config.yaml", help="path tới config yaml")
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
