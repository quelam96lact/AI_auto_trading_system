"""Spike xác nhận dữ liệu stream index thật từ ssi-sdk.

Chạy: uv run --with ssi-sdk python scripts/spike_ssi_sdk_index_stream.py [--seconds 120]
      uv run --with ssi-sdk python scripts/spike_ssi_sdk_index_stream.py --ohlcv [--seconds 120]

YÊU CẦU TRƯỚC: chạy scripts/spike_ssi_sdk_auth.py để xác thực OTP và lưu token
vào scripts/.ssi_sdk_token.json. Script này đọc lại token đó (KHÔNG xin OTP lại);
nếu access_token hết hạn nó sẽ thử refresh() bằng refresh_token đã lưu.

Mục đích: xác nhận hình dạng thật của message nhận được qua
AsyncStreamingService.subscribe_index(["VNINDEX", "VN30"]) để làm input cho
prompt implement IndexValue mapping sau này. KHÔNG viết code production ở đây.

Mặc định dùng subscribe_index() — đã xác nhận thật (2 lần test trong giờ giao
dịch) KHÔNG nhận được tick nào, dù mã "VNINDEX"/"VN30" đúng thật (xác nhận qua
get_indexes(), xem scripts/spike_ssi_sdk_index_lookup.py). Lý do nghi ngờ:
subscribe_index() chỉ là wrapper gọi subscribe_symbol_trade/quote/room — 3
kênh này thiết kế cho chứng khoán CÓ THỂ GIAO DỊCH (có lệnh khớp, sổ lệnh bid/
ask); index không phải công cụ giao dịch được nên các kênh này không có gì để
publish. --ohlcv thử subscribe_symbol_ohlcv() thay thế (đã dùng thành công cho
bar cổ phiếu trong trading/collector/feed.py) — kênh OHLCV hợp lý hơn cho khái
niệm "nến index" (open/high/low/close mức index).

Cần env SSI_API_KEY, SSI_API_SECRET. Cần phiên giao dịch đang mở để có message
thật (ngoài giờ file .jsonl rỗng là bình thường, không phải lỗi).
"""

import asyncio
import dataclasses
import json
import sys
from pathlib import Path

from _ssi_spike_common import make_auth

OUT = Path(__file__).parent / ".spike_index_stream_sample.jsonl"
INDICES = ["VNINDEX", "VN30"]


async def record_index_stream(seconds: int, use_ohlcv: bool) -> None:
    from ssi_sdk import AsyncStream

    count = 0
    out = OUT.open("w", encoding="utf-8")

    def on_message(msg):
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
        stream.streaming.on_data = on_message
        await stream.streaming.connect()
        if use_ohlcv:
            from ssi_sdk.enums import Timeframe

            await stream.streaming.subscribe_symbol_ohlcv(INDICES, Timeframe.MINUTE_1)
            print(
                f"[--ohlcv] Đang lắng nghe {INDICES} (1m candles) trong {seconds}s → {OUT}"
            )
        else:
            await stream.streaming.subscribe_index(INDICES)
            print(f"Đang lắng nghe {INDICES} trong {seconds}s → {OUT}")
        await asyncio.sleep(seconds)
        await stream.streaming.disconnect()
    out.close()

    print(f"Xong: {count} message.")
    if count == 0:
        print(
            "Không nhận được message nào — có thể ngoài giờ giao dịch "
            "hoặc cách subscribe này không hoạt động như kỳ vọng."
        )
    else:
        print("Mẫu message cuối cùng đã in ở trên — dùng file .jsonl để phân tích.")


if __name__ == "__main__":
    seconds = 120
    if "--seconds" in sys.argv:
        seconds = int(sys.argv[sys.argv.index("--seconds") + 1])
    asyncio.run(record_index_stream(seconds, use_ohlcv="--ohlcv" in sys.argv))
