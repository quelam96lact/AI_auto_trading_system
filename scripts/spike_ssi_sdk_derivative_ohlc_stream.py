"""Phase 0 spike: xác nhận OHLC + stream thật cho hợp đồng VN30F1M.

Chạy: uv run --with ssi-sdk python scripts/spike_ssi_sdk_derivative_ohlc_stream.py [--seconds 120]

YÊU CẦU TRƯỚC: chạy scripts/spike_ssi_sdk_derivative_account.py trước để tạo
scripts/.spike_derivative_contract_symbol.json. Script này đọc mã hợp đồng thật
từ file đó, KHÔNG hardcode symbol.

Mục đích (PLAN_DERIVATIVE_TRADING.md Phase 0):
1. Gọi get_ohlc_1minute(<symbol thật>) → lưu sample bar.
2. Subscribe subscribe_symbol([<symbol thật>]) trong --seconds giây → ghi mỗi
   message ra .jsonl.

⚠️ TUYỆT ĐỐI KHÔNG gọi bất kừ method đặt lệnh nào trong script này.

Cần env SSI_API_KEY, SSI_API_SECRET. Phần stream cần phiên giao dịch đang mở
(ngoài giờ file .jsonl rỗng là bình thường).
"""

import asyncio
import dataclasses
import json
import sys
from pathlib import Path

from _ssi_spike_common import make_auth

CONTRACT_FILE = Path(__file__).parent / ".spike_derivative_contract_symbol.json"
OHLC_OUT = Path(__file__).parent / ".spike_derivative_ohlc_sample.json"
STREAM_OUT = Path(__file__).parent / ".spike_derivative_stream_sample.jsonl"


def _read_contract_symbol() -> str:
    if not CONTRACT_FILE.exists():
        print(
            f"Chưa có file {CONTRACT_FILE}. "
            "Chạy scripts/spike_ssi_sdk_derivative_account.py trước."
        )
        sys.exit(1)
    data = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
    symbol = data.get("symbol")
    if not symbol:
        print(f"File {CONTRACT_FILE} không chứa 'symbol' hợp lệ: {data}")
        sys.exit(1)
    print(f"Mã hợp đồng đọc từ {CONTRACT_FILE}: {symbol}")
    return symbol


async def fetch_ohlc_sample(symbol: str) -> None:
    from ssi_sdk import AsyncData

    async with await make_auth() as auth:
        data = AsyncData(auth)
        print(f"\nGọi get_ohlc_1minute({symbol})...")
        try:
            rows = await data.market_data.get_ohlc_1minute(symbol)
            payload = [dataclasses.asdict(r) for r in rows]
            OHLC_OUT.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            print(f"OK — {len(rows)} bar → {OHLC_OUT}")
            if rows:
                print("Mẫu bar đầu:", payload[0])
        except Exception as e:
            print(f"!! get_ohlc_1minute({symbol}) lỗi: {e}")


async def record_stream(symbol: str, seconds: int) -> None:
    from ssi_sdk import AsyncStream

    count = 0
    out = STREAM_OUT.open("w", encoding="utf-8")

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
        try:
            await stream.streaming.connect()
            await stream.streaming.subscribe_symbol([symbol])
            print(f"\nĐang lắng nghe {symbol} trong {seconds}s → {STREAM_OUT}")
            await asyncio.sleep(seconds)
        finally:
            try:
                await stream.streaming.disconnect()
            except Exception as e:
                print(f"disconnect warning: {e}")
    out.close()

    print(f"\nXong: {count} message.")
    if count == 0:
        print(
            "Không nhận được message nào — có thể ngoài giờ giao dịch "
            "hoặc symbol sai."
        )


if __name__ == "__main__":
    seconds = 120
    if "--seconds" in sys.argv:
        seconds = int(sys.argv[sys.argv.index("--seconds") + 1])

    symbol = _read_contract_symbol()

    if "--stream-only" not in sys.argv:
        asyncio.run(fetch_ohlc_sample(symbol))
    if "--ohlc-only" not in sys.argv:
        asyncio.run(record_stream(symbol, seconds))
