"""Script diễn tập đặt và huỷ một lệnh thật trên BingX Perpetual Swap (Brief 112).

Mục đích:
Kiểm chứng đường truyền, xác thực API key/secret, chữ ký HMAC-SHA256, và quy trình
đặt một lệnh giới hạn nhỏ nhất có thể ở giá xa thị trường (-5%) rồi huỷ ngay lập tức.

⛔ LUẬT TỐI THƯỢNG:
- Agent TUYỆT ĐỐI KHÔNG gửi bất kỳ lệnh thật nào lên sàn.
- Script chỉ gửi lệnh thật khi có cờ --send VÀ người vận hành gõ chính xác "YES".
- Không có cờ --send: chỉ CHẠY THỬ (dry-run, chỉ đọc dữ liệu), KHÔNG gửi bất kỳ request ghi nào.

Cách chạy:
  Chạy thử (chỉ đọc):
    uv run python scripts/bingx_drill_place_cancel.py --symbol BTC-USDT

  Chạy thật (chủ tài khoản trực tiếp thực thi sau khi Claude audit):
    uv run python scripts/bingx_drill_place_cancel.py --symbol BTC-USDT --env live --send
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
import time
from typing import Any

from trading.alerts import alert
from trading.bingx_client import BingXTradeClient

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

LOGS_DIR = pathlib.Path("logs")
STATUS_POLL_ATTEMPTS = 3
STATUS_POLL_SLEEP_SEC = 2.0
MAX_NOTIONAL_USDT = 20.0
MAX_CLOCK_OFFSET_MS = 2500
DEMO_BASE_URL = "https://open-api-vst.bingx.com"
LIVE_BASE_URL = "https://open-api.bingx.com"


def load_credentials_from_env() -> tuple[str, str]:
    """Đọc credentials từ .env hoặc môi trường, chỉ chấp nhận chữ HOA."""
    env_file = pathlib.Path(".env")
    key = None
    secret = None

    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k == "BINGX_API_KEY":
                key = v.strip()
            elif k == "BINGX_API_SECRET":
                secret = v.strip()

    if not key:
        key = os.environ.get("BINGX_API_KEY")
    if not secret:
        secret = os.environ.get("BINGX_API_SECRET")

    if not key or not secret:
        sys.stderr.write(
            "LỖI: Thiếu biến môi trường BINGX_API_KEY hoặc BINGX_API_SECRET.\n"
            "Tên biến phải viết hoa toàn bộ trong file .env.\n"
        )
        sys.exit(1)

    return key, secret


def round_down_to_tick(price: float, tick_size: float, precision: int = 1) -> float:
    """Làm tròn XUỐNG theo bước giá: math.floor(price / tick_size) * tick_size."""
    steps = math.floor(round(price / tick_size, 8))
    return round(steps * tick_size, precision)


def calculate_drill_price(
    market_price: float,
    tick_size: float,
    precision: int = 1,
    discount_rate: float = 0.05,
) -> float:
    """Tính giá đặt LO BUY an toàn: thấp hơn thị trường discount_rate (5%), làm tròn XUỐNG."""
    raw_price = market_price * (1.0 - discount_rate)
    return round_down_to_tick(raw_price, tick_size, precision)


def _fail_loud(
    alert_fn: Any,
    headline: str,
    symbol: str,
    price: float,
    qty: float,
    placed: Any,
    detail: Any,
) -> None:
    """In khối CẢNH BÁO NGHIÊM TRỌNG, bắn alert CRITICAL, thoát mã 2."""
    block = (
        "\n" + "!" * 80 + "\n"
        " CẢNH BÁO NGHIÊM TRỌNG — BINGX DRILL!\n"
        f" {headline}\n"
        f"  - Mã hợp đồng:        {symbol}\n"
        f"  - Giá đặt:            {price}\n"
        f"  - Khối lượng:         {qty}\n"
        f"  - Order Info:         {placed}\n"
        f"  - Chi tiết:           {detail}\n"
        + "!" * 80 + "\n"
    )
    print(block, file=sys.stderr)
    try:
        t = alert_fn(
            "CRITICAL",
            f"BingX drill: {headline}",
            symbol=symbol,
            price=price,
            qty=qty,
            order=str(placed),
            detail=str(detail),
        )
        if t is not None and hasattr(t, "join"):
            t.join(timeout=6)
    except Exception as exc:
        print(f"Không gửi được alert: {exc}", file=sys.stderr)


def run_drill(
    client: BingXTradeClient | None = None,
    symbol: str = "BTC-USDT",
    send: bool = False,
    env: str = "demo",
    input_fn: Any = input,
    alert_fn: Any = alert,
    sleep_fn: Any = time.sleep,
) -> int:
    """Thực thi quy trình diễn tập đặt và huỷ lệnh BingX."""
    symbol = symbol.upper().strip()
    env = env.lower().strip()

    # 1. Khởi tạo client nếu chưa được tiêm
    if client is None:
        api_key, api_secret = load_credentials_from_env()
        base_url = LIVE_BASE_URL if env == "live" else DEMO_BASE_URL
        client = BingXTradeClient(api_key=api_key, api_secret=api_secret, base_url=base_url)

    # Kiểm tra an toàn môi trường Live
    client_base = getattr(client, "_base_url", "")
    is_live_target = LIVE_BASE_URL.rstrip("/") in client_base
    if send and is_live_target and env != "live":
        print(
            "!! DỪNG: Client đang trỏ tới LIVE URL nhưng thiếu cờ '--env live' tường minh.\n"
            "Để tránh nhầm lẫn, lệnh thật trên live bắt buộc phải truyền '--env live'.",
            file=sys.stderr,
        )
        return 1

    # 2. Kiểm tra đồng hồ & độ lệch
    try:
        clock_offset = client.get_clock_offset()
    except Exception as e:
        print(f"!! DỪNG: Không đọc được giờ server BingX: {e}", file=sys.stderr)
        return 1

    if abs(clock_offset) > MAX_CLOCK_OFFSET_MS:
        print(
            f"!! DỪNG: Độ lệch đồng hồ ({clock_offset:+d} ms) vượt ngưỡng an toàn {MAX_CLOCK_OFFSET_MS} ms.\n"
            "Hãy đồng bộ đồng hồ hệ thống trước khi gửi lệnh.",
            file=sys.stderr,
        )
        return 1

    # 3. Lấy thông số hợp đồng
    try:
        spec = client.get_contract(symbol)
    except Exception as e:
        print(f"!! DỪNG: Không lấy được thông số hợp đồng cho {symbol}: {e}", file=sys.stderr)
        return 1

    tick_size = spec["tick_size"]
    price_precision = spec["price_precision"]
    min_qty = spec["min_qty"]
    min_notional = spec["min_notional"]

    # 4. Lấy giá thị trường hiện tại
    try:
        ticker = client.get_ticker(symbol)
        market_price = float(ticker["last_price"])
    except Exception as e:
        print(f"!! DỪNG: Không lấy được giá thị trường cho {symbol}: {e}", file=sys.stderr)
        return 1

    # 5. Kiểm tra vị thế mở
    try:
        open_positions = client.get_positions(symbol=symbol)
    except Exception as e:
        print(f"!! DỪNG: Không đọc được danh sách vị thế: {e}", file=sys.stderr)
        return 1

    if open_positions:
        print(
            f"!! DỪNG: Đang có {len(open_positions)} vị thế mở trên {symbol}. "
            "Diễn tập yêu cầu không có vị thế mở để tránh rủi ro vị thế.",
            file=sys.stderr,
        )
        return 1

    # 6. Kiểm tra lệnh chờ
    try:
        open_orders = client.get_open_orders(symbol=symbol)
    except Exception as e:
        print(f"!! DỪNG: Không đọc được danh sách lệnh chờ: {e}", file=sys.stderr)
        return 1

    if open_orders:
        print(
            f"!! DỪNG: Đang có {len(open_orders)} lệnh chờ trên {symbol}. "
            "Diễn tập yêu cầu sổ lệnh trống trên mã này.",
            file=sys.stderr,
        )
        return 1

    # 7. Tính toán mức lệnh
    price = calculate_drill_price(market_price, tick_size, price_precision, discount_rate=0.05)
    qty = min_qty
    notional = round(price * qty, 4)

    if notional > MAX_NOTIONAL_USDT:
        print(
            f"!! DỪNG: Giá trị danh nghĩa {notional:.2f} USDT vượt trần an toàn cứng ({MAX_NOTIONAL_USDT} USDT).",
            file=sys.stderr,
        )
        return 1

    if notional < min_notional:
        print(
            f"!! DỪNG: Giá trị danh nghĩa {notional:.2f} USDT nhỏ hơn minNotional của sàn ({min_notional} USDT).",
            file=sys.stderr,
        )
        return 1

    # 8. Kiểm tra số dư ký quỹ
    try:
        bal = client.get_perpetual_balance()
        avail_margin = float(bal["available_margin"])
    except Exception as e:
        print(f"!! DỪNG: Không đọc được số dư ký quỹ: {e}", file=sys.stderr)
        return 1

    estimated_margin = notional
    if avail_margin < 2 * estimated_margin:
        if send:
            print(
                f"!! DỪNG: Ký quỹ khả dụng ({avail_margin:.2f} USDT) < 2 × ký quỹ ước tính ({estimated_margin:.2f} USDT).",
                file=sys.stderr,
            )
            return 1
        else:
            print(
                f"!! CẢNH BÁO SỐ DƯ: Ký quỹ khả dụng ({avail_margin:.2f} USDT) < 2 × ký quỹ ước tính ({estimated_margin:.2f} USDT).\n"
                "Nếu chạy thật có --send sẽ bị DỪNG. Tiếp tục chạy thử (dry-run) để in kế hoạch lệnh...",
                file=sys.stderr,
            )

    # 9. In Kế hoạch lệnh
    discount_pct = ((market_price - price) / market_price) * 100
    print("\n" + "=" * 70)
    print(" KẾ HOẠCH LỆNH DIỄN TẬP BINGX PERPETUAL (DRILL ORDER PLAN)")
    print("=" * 70)
    print(f" Môi trường:        {env.upper()} ({'LIVE REAL MONEY' if env == 'live' else 'DEMO VST'})")
    print(f" Mã hợp đồng:       {symbol}")
    print(" Chiều lệnh:        BUY (Long)")
    print(" Loại lệnh:         LIMIT (PostOnly)")
    print(f" Giá thị trường:    {market_price}")
    print(f" Giá đặt diễn tập:  {price} (thấp hơn thị trường {discount_pct:.2f}%)")
    print(f" Bước giá:          {tick_size}")
    print(f" Khối lượng đặt:    {qty} {symbol.split('-')[0]} (khối lượng tối thiểu)")
    print(f" Giá trị danh nghĩa: {notional:.4f} USDT (trần an toàn: {MAX_NOTIONAL_USDT} USDT)")
    print(f" Ký quỹ ước tính:   {estimated_margin:.4f} USDT")
    print(f" Ký quỹ khả dụng:   {avail_margin:.4f} USDT")
    print(f" Độ lệch đồng hồ:   {clock_offset:+d} ms")
    print("=" * 70)

    # 10. Chạy thử (Dry-run) nếu không có cờ --send
    if not send:
        print("\n[CHẠY THỬ / DRY-RUN] Hoàn tất lập kế hoạch. KHÔNG gửi bất kỳ lệnh nào lên sàn.")
        print("(Thu tu: chay \"--env demo --send\" TRUOC va dat exit 0, roi moi \"--env live --send\" — xem runbook dien-tap-lenh-bingx.md).")
        return 0

    # 11. Cổng xác nhận người vận hành
    confirm = input_fn("Gõ YES để GỬI LỆNH: ")
    if confirm != "YES":
        print(f"Đã huỷ diễn tập (nhận được '{confirm}', yêu cầu chính xác 'YES'). Thoát an toàn.")
        return 0

    # 12. Gửi lệnh lên sàn (Send Attempted)
    client_order_id = f"drill_{int(time.time() * 1000)}"
    print(f"\n[Bước 1] Đặt lệnh LIMIT BUY {qty} {symbol} @ {price} (PostOnly)...")
    placed = None
    try:
        placed = client.place_limit_order(
            symbol=symbol,
            side="BUY",
            price=price,
            quantity=qty,
            position_side="BOTH",
            time_in_force="PostOnly",
            client_order_id=client_order_id,
        )
    except Exception as exc:
        _fail_loud(
            alert_fn,
            "KHÔNG RÕ LỆNH ĐÃ LÊN SÀN CHƯA — KIỂM TRA app BingX",
            symbol, price, qty, None, exc,
        )
        return 2

    order_id = placed.get("order_id")
    client_order_id = placed.get("client_order_id") or client_order_id
    print(f"  -> ĐÃ GỬI LỆNH: order_id={order_id}, client_order_id={client_order_id}, status={placed.get('status')}")

    # 13. Đọc lại lệnh tối đa 3 lần
    found = None
    for attempt in range(STATUS_POLL_ATTEMPTS):
        if attempt > 0:
            sleep_fn(STATUS_POLL_SLEEP_SEC)
        try:
            ord_info = client.get_order(symbol=symbol, order_id=order_id, client_order_id=client_order_id)
            if ord_info:
                found = ord_info
                break
        except Exception:  # noqa: S112
            continue

    if found is None:
        print("!! KHÔNG xác nhận được trạng thái lệnh qua API — ĐỐI CHIẾU TAY trên app BingX.", file=sys.stderr)
        return 1

    status = str(found.get("status", "")).upper()
    executed_qty = float(found.get("executed_qty", 0.0))
    print(f"\n[Bước 2] Trạng thái lệnh sau khi đặt: status={status}, executed_qty={executed_qty}")

    # Nhánh ĐÃ KHỚP -> CRITICAL
    if status in ("FILLED", "PARTIALLY_FILLED") or executed_qty > 0:
        _fail_loud(
            alert_fn,
            f"ĐÃ KHỚP {executed_qty} — ĐÓNG VỊ THẾ TAY TRÊN APP",
            symbol, price, qty, found, f"Status: {status}, Executed: {executed_qty}",
        )
        return 2

    # Nhánh ĐANG CHỜ -> HUỶ LỆNH
    cancel_resp = None
    if status in ("NEW", "PENDING"):
        print(f"\n[Bước 3] Huỷ lệnh vừa đặt (order_id={order_id})...")
        try:
            cancel_resp = client.cancel_order(symbol=symbol, order_id=order_id, client_order_id=client_order_id)
        except Exception as exc:
            _fail_loud(
                alert_fn,
                "LỆNH CÒN TREO — HUỶ TAY",
                symbol, price, qty, found, f"Cancel exception: {exc}",
            )
            return 2

        # Xác nhận đã huỷ
        verified = None
        for attempt in range(STATUS_POLL_ATTEMPTS):
            sleep_fn(STATUS_POLL_SLEEP_SEC)
            try:
                v = client.get_order(symbol=symbol, order_id=order_id, client_order_id=client_order_id)
                if v and str(v.get("status", "")).upper() == "CANCELED":
                    verified = v
                    break
            except Exception:  # noqa: S112
                continue

        final_status = str(verified.get("status", "")).upper() if verified else ""
        if final_status == "CANCELED":
            print(f"  -> ĐÃ XÁC NHẬN HUỶ THÀNH CÔNG: Lệnh ở trạng thái {final_status}.")
        else:
            _fail_loud(
                alert_fn,
                "LỆNH CÒN TREO — HUỶ TAY",
                symbol, price, qty, verified or found, f"Status after cancel: {final_status}",
            )
            return 2

    elif status == "CANCELED":
        print("  -> Lệnh đã ở trạng thái CANCELED (ví dụ PostOnly huỷ do điều kiện khớp).")
    else:
        _fail_loud(
            alert_fn,
            f"TRẠNG THÁI KHÔNG XÁC ĐỊNH ({status}) — KIỂM TRA TAY",
            symbol, price, qty, found, f"Unexpected status: {status}",
        )
        return 2

    # 14. Ghi audit log JSON (không chứa secrets)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    now_ts = int(time.time())
    log_file = LOGS_DIR / f"bingx_drill_{now_ts}.json"
    audit_payload = {
        "timestamp": now_ts,
        "env": env,
        "symbol": symbol,
        "market_price": market_price,
        "order_price": price,
        "quantity": qty,
        "notional": notional,
        "placed_response": placed,
        "cancel_response": cancel_resp,
        "status_confirmed": "CANCELED",
    }
    log_file.write_text(json.dumps(audit_payload, indent=2, default=str), encoding="utf-8")
    print(f"\nĐã ghi audit log diễn tập vào: {log_file}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diễn tập đặt rồi huỷ một lệnh thật trên BingX — KHÔNG gửi lệnh nếu thiếu --send"
    )
    parser.add_argument(
        "--symbol",
        default="BTC-USDT",
        help="Mã hợp đồng perpetual (mặc định: BTC-USDT)",
    )
    parser.add_argument(
        "--env",
        choices=["demo", "live"],
        default="demo",
        help="Môi trường giao dịch (demo: VST, live: tài khoản thật; mặc định: demo)",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Cờ gửi lệnh thật lên sàn. Nếu không có cờ này, chỉ chạy thử (chỉ đọc).",
    )
    args = parser.parse_args()

    exit_code = run_drill(
        symbol=args.symbol,
        send=args.send,
        env=args.env,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
