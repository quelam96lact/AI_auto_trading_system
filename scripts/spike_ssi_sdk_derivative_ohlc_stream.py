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
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from _ssi_spike_common import make_auth

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

CONTRACT_FILE = Path(__file__).parent / ".spike_derivative_contract_symbol.json"
OHLC_OUT = Path(__file__).parent / ".spike_derivative_ohlc_sample.json"
OHLC_5M_2M_OUT = Path(__file__).parent / ".spike_derivative_ohlc_5m_2m_sample.json"
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


async def fetch_ohlc_5m_2months(symbol: str) -> None:
    from ssi_sdk import AsyncData

    async with await make_auth() as auth:
        data = AsyncData(auth)
        to_date = datetime.now(VN_TZ).date()
        start_date = to_date - timedelta(days=60)

        bars_by_ts: dict[str, dict] = {}  # key = trading_date string, dedupe tự nhiên
        chunk_start = start_date
        while chunk_start <= to_date:
            chunk_end = min(chunk_start + timedelta(days=6), to_date)  # chunk 7 ngày
            from_str = f"{chunk_start:%Y/%m/%d} 00:00:00"
            to_str = f"{chunk_end:%Y/%m/%d} 23:59:59"
            # Server thỉnh thoảng trả response truncated khi gọi nhiều lần liên
            # tiếp — retry nếu bar mới nhất không vượt quá ngày đầu chunk
            # (chunk 7 ngày trong phiên hợp lệ phải có bar sau ngày đầu).
            rows: list = []
            for attempt in range(4):
                await asyncio.sleep(0.25)  # throttle nhẹ giữa các call
                rows = await data.market_data.get_ohlc_5minute_historical(
                    symbol, from_str, to_str, page=1, size=1000
                )
                if not rows:
                    break  # chunk rỗng hợp lệ (hợp đồng chưa list / nghỉ lễ)
                newest_date = max(r.trading_date[:10] for r in rows)
                if newest_date > f"{chunk_start:%Y/%m/%d}" or attempt == 3:
                    break
                print(
                    f"  !! chunk trả newest={newest_date} <= chunk_start — "
                    f"server truncated, retry {attempt + 1}/3..."
                )
            print(f"Gọi chunk {from_str} -> {to_str}...")
            print(f"  nhận {len(rows)} bar (chunk 7 ngày, kỳ vọng << 1000)")
            if len(rows) >= 1000:
                print(
                    "  !! CẢNH BÁO: chunk 7 ngày trả về đúng 1000 bar — "
                    "có thể đã bị cắt/trùng do vượt 1 trang. Cần giảm chunk nhỏ hơn."
                )
            if rows:
                newest_date = max(r.trading_date[:10] for r in rows)
                if newest_date <= f"{chunk_start:%Y/%m/%d}":
                    print(
                        f"  !! CẢNH BÁO: sau 3 retry vẫn truncated (newest={newest_date}) — "
                        "dữ liệu cuối chunk có thể thiếu, báo lại để quyết định."
                    )
            for r in rows:
                bars_by_ts[r.trading_date] = r  # dedupe theo timestamp, ghi đè nếu trùng
            chunk_start = chunk_end + timedelta(days=1)

        all_rows = sorted(bars_by_ts.values(), key=lambda r: r.trading_date)
        payload = [dataclasses.asdict(r) for r in all_rows]
        OHLC_5M_2M_OUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"Tổng {len(all_rows)} bar 5 phút DUY NHẤT (2 tháng) → {OHLC_5M_2M_OUT}")
        if all_rows:
            print("Bar đầu:", payload[0])
            print("Bar cuối:", payload[-1])


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
        asyncio.run(fetch_ohlc_5m_2months(symbol))
    if "--ohlc-only" not in sys.argv:
        asyncio.run(record_stream(symbol, seconds))
