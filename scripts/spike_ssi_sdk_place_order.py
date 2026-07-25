"""Phase 0 spike: xác nhận đặt lệnh THẬT (đặt 1 lệnh LO an toàn + huỷ ngay).

⚠️ CẢNH BÁO: Script này ĐẶT 1 LỆNH THẬT lên sàn (không phải dry-run), rồi
huỷ ngay lập tức. Đọc kỹ PLAN_REAL_ORDER_PLACEMENT.md trước khi chạy.

Chạy: uv run --with ssi-sdk python scripts/spike_ssi_sdk_place_order.py [--symbol VCB] [--account 0434221]

YÊU CẦU TRƯỚC: scripts/spike_ssi_sdk_auth.py đã chạy (có token đã lưu).
Cần thêm env SSI_PRIVATE_KEY (đã có sẵn trong .env — dùng để ký lệnh,
xác nhận từ source code services/trading.py::_sign_and_encode).

An toàn (theo đúng thứ tự, không đảo):
1. Gọi get_max_buy_sell_at_market_price() TRƯỚC — CHỈ ĐỌC, không đặt
   lệnh gì. Nếu sức mua tính ra (ở giá thị trường HIỆN TẠI, cao hơn giá
   sẽ dùng ở bước 3) < 100 cổ phiếu (1 lô tối thiểu HOSE/HNX) → DỪNG
   NGAY, in rõ cần nạp thêm bao nhiêu tiền, KHÔNG cố đặt lệnh biết
   trước sẽ thất bại (account Cash 0434221 hiện chỉ ~21,459đ — xem
   PLAN_REAL_ORDER_PLACEMENT.md mục "Rủi ro mới phát hiện").
2. Lấy giá đóng cửa thật gần nhất qua AsyncData (CHỈ ĐỌC, cùng cơ chế
   đã audit ở backfill.py Phase 2 migration) — KHÔNG tự đoán giá.
3. Đặt 1 lệnh LIMIT mua giá = 93% giá đóng cửa (dưới biên độ ±7% HOSE,
   được sàn chấp nhận nhưng gần như chắc chắn không khớp trong vài giây
   trước khi huỷ). Giá thấp hơn giá dùng ở bước 1 → sức mua chắc chắn
   đủ nếu bước 1 đã pass (giá thấp hơn = mua được nhiều cổ phiếu hơn
   với cùng số tiền).
4. Huỷ NGAY lệnh vừa đặt qua cancel_order(), xác nhận huỷ thành công.
5. KHÔNG import/gọi bất kỳ API sửa/xác nhận khớp lệnh nào khác ngoài
   place_limit_order + cancel_order.
"""

import dataclasses
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from _ssi_spike_common import make_auth

MAX_BUY_SELL_OUT = Path(__file__).parent / ".spike_max_buy_sell.json"
PLACE_OUT = Path(__file__).parent / ".spike_place_order.json"
CANCEL_OUT = Path(__file__).parent / ".spike_cancel_order.json"

MIN_LOT = 100  # 1 lô tối thiểu HOSE/HNX (quy ước thị trường, không phải SDK)
SAFETY_MARGIN = 0.93  # đặt mua ở 93% giá đóng cửa gần nhất — trong biên ±7% HOSE


async def main() -> None:
    from ssi_sdk import AsyncData, AsyncTrading
    from ssi_sdk.enums import OrderSide

    symbol = "VCB"
    account_no = "0434221"
    if "--symbol" in sys.argv:
        symbol = sys.argv[sys.argv.index("--symbol") + 1]
    if "--account" in sys.argv:
        account_no = sys.argv[sys.argv.index("--account") + 1]

    auth = await make_auth()
    auth.config.private_key = os.environ["SSI_PRIVATE_KEY"]
    trading = AsyncTrading(auth)

    print(
        f"Bước 1 — get_max_buy_sell_at_market_price({account_no}, {symbol}) (chỉ đọc)..."
    )
    mbs = await trading.trading.get_max_buy_sell_at_market_price(account_no, symbol)
    payload = dataclasses.asdict(mbs)
    MAX_BUY_SELL_OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(" ", payload)

    if mbs.max_buy_quantity < MIN_LOT:
        print(
            f"\n!! DỪNG — sức mua thật ({mbs.max_buy_quantity} cổ phiếu) "
            f"< 1 lô tối thiểu ({MIN_LOT}). KHÔNG đặt lệnh.\n"
            "Account Cash hiện không đủ tiền để test đặt lệnh thật với mã này — "
            "cần nạp thêm tiền hoặc chọn mã rẻ hơn (--symbol) rồi chạy lại."
        )
        await auth.close()
        return

    print(
        f"\nBước 2 — lấy giá đóng cửa gần nhất của {symbol} (chỉ đọc, qua AsyncData)..."
    )
    data = AsyncData(auth)
    today = datetime.now().date()
    rows = await data.market_data.get_ohlc_1day_historical(
        symbol,
        (today - timedelta(days=10)).strftime("%Y/%m/%d"),
        today.strftime("%Y/%m/%d"),
    )
    if not rows:
        print("!! DỪNG — không lấy được giá đóng cửa gần nhất, không đặt lệnh.")
        await auth.close()
        return
    last_close = float(rows[-1].close_price)
    test_price = round(last_close * SAFETY_MARGIN / 100) * 100  # làm tròn bước giá 100đ
    print(f"  Giá đóng cửa gần nhất: {last_close} → giá đặt test: {test_price}")

    print(f"\nBước 3 — đặt lệnh LIMIT mua {MIN_LOT} {symbol} @ {test_price}...")
    placed = await trading.trading.place_limit_order(
        account_no, symbol, OrderSide.BUY, MIN_LOT, test_price
    )
    place_payload = dataclasses.asdict(placed)
    PLACE_OUT.write_text(
        json.dumps(place_payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(" ", place_payload)

    print(
        f"\nBước 4 — huỷ ngay lệnh vừa đặt (client_request_id={placed.client_request_id})..."
    )
    cancelled = await trading.trading.cancel_order(account_no, placed.client_request_id)
    cancel_payload = dataclasses.asdict(cancelled)
    CANCEL_OUT.write_text(
        json.dumps(cancel_payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(" ", cancel_payload)

    print(
        "\nXong. Kiểm tra lại account_balance_snapshot/Grafana để xác nhận không mất tiền ngoài dự kiến."
    )
    await auth.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
