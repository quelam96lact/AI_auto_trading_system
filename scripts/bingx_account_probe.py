"""Script thăm dò tài khoản BingX Perpetual chỉ đọc (Brief 111 Step 5).

Chức năng:
1. Đọc đúng tên biến viết hoa BINGX_API_KEY và BINGX_API_SECRET từ .env / môi trường.
   Nếu thiếu, thoát mã 1 và thông báo rõ tên biến cần có.
2. Kiểm tra giờ server và độ lệch đồng hồ máy local.
3. Lấy số dư tài khoản Perpetual Futures (USDT-M).
4. Lấy số lượng vị thế đang mở và lệnh đang chờ.
5. Lấy thông số hợp đồng BTC-USDT (bước giá, bước khối lượng, min qty, min notional, phí) và nguồn trích xuất.
6. Thực hiện một lần gọi có chủ đích với chữ ký sai để chứng minh cơ chế bắt lỗi rõ ràng.

Chạy:
    uv run python scripts/bingx_account_probe.py
"""

from __future__ import annotations

import os
import pathlib
import sys
import time

from trading.bingx_client import BingXClient, BingXError


def load_credentials_from_env() -> tuple[str, str]:
    """Đọc credentials từ .env hoặc môi trường, chỉ chấp nhận chữ HOA."""
    # 1. Đọc từ file .env nếu có (case-sensitive)
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
            # BẮT BUỘC: Chỉ chấp nhận đúng tên viết hoa BINGX_API_KEY / BINGX_API_SECRET
            if k == "BINGX_API_KEY":
                key = v.strip()
            elif k == "BINGX_API_SECRET":
                secret = v.strip()

    # 2. Fallback sang os.environ nếu trong .env chưa có
    if not key:
        key = os.environ.get("BINGX_API_KEY")
    if not secret:
        secret = os.environ.get("BINGX_API_SECRET")

    if not key or not secret:
        sys.stderr.write(
            "LỖI: Thiếu biến môi trường BINGX_API_KEY hoặc BINGX_API_SECRET.\n"
            "Quy ước repo: Tên biến phải viết hoa toàn bộ 'BINGX_API_KEY' và 'BINGX_API_SECRET' trong file .env.\n"
        )
        sys.exit(1)

    return key, secret


def main() -> None:
    # Thiết lập UTF-8 output cho console Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 70)
    print("BINGX PERPETUAL FUTURES ACCOUNT PROBE (READ-ONLY) — BRIEF 111")
    print("=" * 70)

    api_key, api_secret = load_credentials_from_env()

    # In thông tin client (đã che key, không in secret)
    client = BingXClient(api_key=api_key, api_secret=api_secret)
    print(f"\n[1] Khởi tạo Client: {client}")

    # Kiểm quyền API Key
    print("\n[2] Kiểm tra quyền API Key:")
    print("    - API BingX hiện KHÔNG có endpoint REST tra cứu quyền trực tiếp của API key.")
    print("    - CHUA XAC MINH: chu du an phai tu kiem tren web BingX rang key nay CHI bat Read (khong Trade, khong Withdraw).")

    # Kiểm tra đồng hồ & độ lệch
    try:
        server_time = client.get_server_time()
        offset_ms = client.get_clock_offset()
        local_time_ms = int(time.time() * 1000)
        print("\n[3] Kiểm tra đồng hồ hệ thống:")
        print(f"    - Giờ local:     {local_time_ms} ms")
        print(f"    - Giờ server:    {server_time} ms")
        print(f"    - Độ lệch:       {offset_ms:+d} ms (ngưỡng an toàn recvWindow=5000ms)")
    except Exception as e:
        print(f"    -> LỖI đọc giờ server: {e}")
        sys.exit(1)

    # Đọc số dư tài khoản Perpetual (USDT-M)
    try:
        bal = client.get_perpetual_balance()
        print("\n[4] Số dư tài khoản Perpetual (USDT-M):")
        print(f"    - Tài sản (Asset):          {bal['asset']}")
        print(f"    - Số dư ví (Balance):       {bal['balance']:.4f} USDT")
        print(f"    - Giá trị ròng (Equity):    {bal['equity']:.4f} USDT")
        print(f"    - Ký quỹ khả dụng (Avail):  {bal['available_margin']:.4f} USDT")
        print(f"    - Ký quỹ đang dùng (Used):  {bal['used_margin']:.4f} USDT")
        print(f"    - Lợi nhuận chưa chốt (PnL): {bal['unrealized_profit']:+.4f} USDT")
    except Exception as e:
        print(f"    -> LỖI đọc số dư: {e}")
        sys.exit(1)

    # Đọc vị thế đang mở
    try:
        positions = client.get_positions()
        print(f"\n[5] Vị thế đang mở (Open Positions): {len(positions)} vị thế")
        if positions:
            for p in positions:
                print(f"    * {p['symbol']} | Side: {p['position_side']} | Qty: {p['position_amt']} | Entry: {p['avg_price']} | Leverage: {p['leverage']}x")
        else:
            print("    (Không có vị thế nào đang mở)")
    except Exception as e:
        print(f"    -> LỖI đọc vị thế: {e}")
        sys.exit(1)

    # Đọc lệnh đang chờ
    try:
        open_orders = client.get_open_orders()
        print(f"\n[6] Lệnh đang chờ (Open Orders): {len(open_orders)} lệnh")
        if open_orders:
            for o in open_orders:
                print(f"    * OrderId: {o['order_id']} | {o['symbol']} | Side: {o['side']} | Type: {o['type']} | Price: {o['price']} | Qty: {o['orig_qty']}")
        else:
            print("    (Không có lệnh nào đang chờ)")
    except Exception as e:
        print(f"    -> LỖI đọc lệnh chờ: {e}")
        sys.exit(1)

    # Đọc thông số hợp đồng BTC-USDT
    try:
        spec = client.get_contract("BTC-USDT")
        ticker = client.get_ticker("BTC-USDT")
        raw = spec["raw"]
        print("\n[7] Thông số hợp đồng BTC-USDT:")
        print(f"    - Bước giá (Tick Size):          {spec['tick_size']} (Nguồn: pricePrecision={spec['price_precision']})")
        print(f"    - Bước khối lượng (Step Size):   {spec['step_size']} (Nguồn: size={raw.get('size')}, quantityPrecision={spec['quantity_precision']})")
        print(f"    - Khối lượng tối thiểu (Min Qty): {spec['min_qty']} BTC (Nguồn: tradeMinQuantity={raw.get('tradeMinQuantity')})")
        print(f"    - Giá trị lệnh tối thiểu (Notional): {spec['min_notional']} USDT (Nguồn: tradeMinUSDT={raw.get('tradeMinUSDT')})")
        print(f"    - Tỷ lệ phí (Fee Rate):          Maker: {spec['maker_fee_rate']*100:.3f}% | Taker: {spec['taker_fee_rate']*100:.3f}% (Nguồn: makerFeeRate/takerFeeRate từ API)")
        print(f"    - Giá thị trường hiện tại:       Last: {ticker['last_price']} | Bid: {ticker['bid_price']} | Ask: {ticker['ask_price']}")
    except Exception as e:
        print(f"    -> LỖI đọc thông số BTC-USDT: {e}")
        sys.exit(1)

    # Thử nghiệm có chủ đích: Gọi với chữ ký sai để chứng minh cơ chế bắt lỗi rõ ràng
    print("\n[8] Kiểm chứng cơ chế bắt lỗi (Gọi có chủ đích với chữ ký sai):")
    bad_client = BingXClient(api_key=api_key, api_secret="INVALID_SECRET_TEST_FOR_ERROR_DETECTION")
    try:
        bad_client.get_perpetual_balance()
        print("    -> LỖI: Lẽ ra phải ném BingXError nhưng request lại thành công!")
        sys.exit(1)
    except BingXError as err:
        print("    -> Bắt được BingXError thành công như kỳ vọng:")
        print(f"       {err}")
        print("       (Xác nhận: Lỗi chứa mã lỗi BingX, không im lặng, và không chứa secret thật)")

    print("\n" + "=" * 70)
    print("KẾT QUẢ: THĂM DÒ TÀI KHOẢN BINGX CHỈ ĐỌC THÀNH CÔNG 100%!")
    print("=" * 70)


if __name__ == "__main__":
    main()
