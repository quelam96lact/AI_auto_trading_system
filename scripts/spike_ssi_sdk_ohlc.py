"""Phase 0 spike: lấy sample OHLC historical + streaming thật từ ssi-sdk mới.
Chạy: uv run python scripts/spike_ssi_sdk_ohlc.py [--seconds N]

YÊU CẦU TRƯỚC: chạy scripts/spike_ssi_sdk_auth.py để xác thực OTP và lưu token
vào scripts/.ssi_sdk_token.json. Script này đọc lại token đó (KHÔNG xin OTP lại);
nếu access_token hết hạn nó sẽ thử refresh() bằng refresh_token đã lưu.

Mục đích (theo PLAN_SSI_SDK_MIGRATION.md Phase 0):
1. Gọi get_ohlc_5minute_historical("VCB", ...) → lưu raw OHLCData ra
   scripts/.spike_ohlc_sample.json để XÁC NHẬN format thật của field
   trading_date (input cho Phase 2 viết lại backfill.py).
2. Subscribe subscribe_symbol_ohlcv(["VCB"], Timeframe.MINUTE_5), lắng nghe
   --seconds giây (mặc định 120), lưu mỗi IntervalMessage ra
   scripts/.spike_stream_sample.jsonl (mỗi dòng 1 JSON) — input cho Phase 3
   viết lại feed.py/parser.py + quyết định giữ/bỏ BarAggregator.

Cần env SSI_API_KEY, SSI_API_SECRET. Phần stream cần phiên giao dịch đang mở
(ngoài giờ có thể không nhận message nào — file .jsonl rỗng là bình thường).

Ghi chú API đã xác minh từ ssi-sdk 3.1.0 cài thật (inspect.signature):
- AsyncData(auth)/AsyncStream(auth) nhận instance AsyncAuth, KHÔNG nhận Config.
- market_data.get_ohlc_5minute_historical(symbol, from_date, to_date, page=1,
  size=1000) -> list[OHLCData]; OHLCData là dataclass (dùng dataclasses.asdict).
- streaming.on_data là PROPERTY (gán callback), connect()/wait(timeout)/
  disconnect() đều async; message push về là dataclass IntervalMessage.
- from_date/to_date: daily dùng "YYYY/MM/DD", intraday (5m ở đây) PHẢI có giờ
  "YYYY/MM/DD HH:mm:ss" — xác nhận từ docs/api-reference/data-ohlc + thực tế
  (thiếu giờ → 400213 "Invalid Date/Timestamp", đã gặp 2026-07-25).
"""

import asyncio
import dataclasses
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from _ssi_spike_common import make_auth

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")  # khớp trading/calendar_vn.py

OHLC_OUT = Path(__file__).parent / ".spike_ohlc_sample.json"
STREAM_OUT = Path(__file__).parent / ".spike_stream_sample.jsonl"

SYMBOL = "VCB"  # khớp config/config.yaml


async def fetch_ohlc_sample() -> None:
    from ssi_sdk import AsyncData

    async with await make_auth() as auth:
        data = AsyncData(auth)
        to_date = datetime.now(VN_TZ).date()
        from_date = to_date - timedelta(days=7)
        # Docs SSI (data-ohlc): intraday can "YYYY/MM/DD HH:mm:ss" (co gio),
        # khac daily chi can "YYYY/MM/DD" — thieu gio gay loi 400213
        # "Invalid Date/Timestamp" (da xac nhan thuc te 2026-07-25).
        from_str = f"{from_date:%Y/%m/%d} 00:00:00"
        to_str = f"{to_date:%Y/%m/%d} 23:59:59"
        print(f"Gọi get_ohlc_5minute_historical({SYMBOL}, {from_str} -> {to_str})...")
        rows = await data.market_data.get_ohlc_5minute_historical(
            SYMBOL, from_str, to_str
        )
        payload = [dataclasses.asdict(r) for r in rows]
        OHLC_OUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Nhận {len(rows)} OHLCData → {OHLC_OUT}")
        if rows:
            print("Mẫu dòng đầu:", payload[0])
            print("!! Kiểm tra field 'trading_date' trong file — input cho Phase 2.")


async def record_stream(seconds: int) -> None:
    from ssi_sdk import AsyncStream
    from ssi_sdk.enums import Timeframe

    count = 0
    out = STREAM_OUT.open("a", encoding="utf-8")

    def on_message(msg):  # SDK push dataclass IntervalMessage đã parse sẵn
        nonlocal count
        line = json.dumps(
            dataclasses.asdict(msg) if dataclasses.is_dataclass(msg) else msg,
            ensure_ascii=False,
            default=str,
        )
        out.write(line + "\n")
        out.flush()
        count += 1
        print(f"[{count}] {line}")

    async with await make_auth() as auth:
        stream = AsyncStream(auth)
        stream.streaming.on_data = on_message  # property setter (đã xác minh)
        await stream.streaming.connect()
        await stream.streaming.subscribe_symbol_ohlcv([SYMBOL], Timeframe.MINUTE_5)
        print(f"Đang lắng nghe {SYMBOL} MINUTE_5 trong {seconds}s → {STREAM_OUT}")
        await asyncio.sleep(seconds)
        await stream.streaming.disconnect()
    out.close()
    print(f"Xong: {count} message. Rỗng ngoài giờ giao dịch là bình thường.")


if __name__ == "__main__":
    seconds = 120
    if "--seconds" in sys.argv:
        seconds = int(sys.argv[sys.argv.index("--seconds") + 1])
    if "--stream-only" not in sys.argv:
        asyncio.run(fetch_ohlc_sample())
    if "--ohlc-only" not in sys.argv:
        asyncio.run(record_stream(seconds))
