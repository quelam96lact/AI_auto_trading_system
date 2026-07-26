"""Phase 0 spike: xác nhận lấy được OHLC thật từ HNX + UPCOM (không chỉ HOSE).
Chạy: uv run python scripts/spike_ssi_sdk_hnx_upcom_ohlc.py [--seconds N] [--stream-only] [--ohlc-only]

YÊU CẦU TRƯỚC: chạy scripts/spike_ssi_sdk_auth.py để xác thực OTP và lưu token
vào scripts/.ssi_sdk_token.json. Script này đọc lại token đó (KHÔNG xin OTP lại);
nếu access_token hết hạn nó sẽ thử refresh() bằng refresh_token đã lưu.

Mục đích:
- Kiến trúc collector hiện tại xử lý theo symbol string, không ràng buộc board.
- Tuy nhiên mọi dữ liệu thật từng dùng đều chỉ là HOSE. Spike này verify thật với
  1 mã HNX và 1 mã UPCOM để xác nhận giả định symbol-agnostic hoạt động đúng.

Cần env SSI_API_KEY, SSI_API_SECRET. Phần stream cần phiên giao dịch đang mở
(ngoài giờ có thể không nhận message nào — file .jsonl rỗng là bình thường).
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

SYMBOLS_OUT = Path(__file__).parent / ".spike_hnx_upcom_symbols.json"
OHLC_HNX_OUT = Path(__file__).parent / ".spike_ohlc_hnx_sample.json"
OHLC_UPCOM_OUT = Path(__file__).parent / ".spike_ohlc_upcom_sample.json"
STREAM_OUT = Path(__file__).parent / ".spike_stream_hnx_upcom_sample.jsonl"


async def discover_symbols(data) -> dict[str, str | None]:
    from ssi_sdk.enums import Board

    result: dict[str, str | None] = {"hnx": None, "upcom": None}

    for label, board in [("hnx", Board.HNX), ("upcom", Board.UPCOM)]:
        print(f"\nKhám phá mã {label.upper()} qua get_securities_info_by_board({board})...")
        securities = await data.market_data.get_securities_info_by_board(board)
        if not securities:
            print(f"  -> Board {label.upper()} trả về danh sách rỗng (bỏ qua).")
            continue
        top = [s.symbol for s in securities[:10]]
        print(f"  -> {len(securities)} mã; 10 mã đầu: {top}")
        chosen = securities[0].symbol
        result[label] = chosen
        print(f"  -> Chọn mã đầu tiên: {chosen}")

    SYMBOLS_OUT.write_text(
        json.dumps(
            {
                "hnx": result["hnx"],
                "upcom": result["upcom"],
                "timestamp": datetime.now(VN_TZ).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nĐã ghi mã đã chọn → {SYMBOLS_OUT}")
    return result


async def fetch_ohlc_sample(symbol: str, out_path: Path) -> None:
    from ssi_sdk import AsyncData

    async with await make_auth() as auth:
        data = AsyncData(auth)
        to_date = datetime.now(VN_TZ).date()
        from_date = to_date - timedelta(days=7)
        from_str = f"{from_date:%Y/%m/%d} 00:00:00"
        to_str = f"{to_date:%Y/%m/%d} 23:59:59"
        print(f"Gọi get_ohlc_5minute_historical({symbol}, {from_str} -> {to_str})...")
        rows = await data.market_data.get_ohlc_5minute_historical(symbol, from_str, to_str)
        payload = [dataclasses.asdict(r) for r in rows]
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Nhận {len(rows)} OHLCData → {out_path}")
        if rows:
            print("Mẫu dòng đầu:", payload[0])


async def fetch_all_ohlc(symbols: dict[str, str | None]) -> None:
    if symbols["hnx"]:
        await fetch_ohlc_sample(symbols["hnx"], OHLC_HNX_OUT)
    else:
        print("Không có mã HNX — bỏ qua OHLC HNX.")

    if symbols["upcom"]:
        await fetch_ohlc_sample(symbols["upcom"], OHLC_UPCOM_OUT)
    else:
        print("Không có mã UPCOM — bỏ qua OHLC UPCOM.")


async def record_stream(symbols: dict[str, str | None], seconds: int) -> None:
    from ssi_sdk import AsyncStream
    from ssi_sdk.enums import Timeframe

    active = [s for s in [symbols.get("hnx"), symbols.get("upcom")] if s]
    if not active:
        print("Không có mã HNX/UPPCOM nào để stream — bỏ qua.")
        return

    count = 0
    out = STREAM_OUT.open("a", encoding="utf-8")

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
        await stream.streaming.subscribe_symbol_ohlcv(active, Timeframe.MINUTE_5)
        print(f"Đang lắng nghe {active} MINUTE_5 trong {seconds}s → {STREAM_OUT}")
        await asyncio.sleep(seconds)
        await stream.streaming.disconnect()
    out.close()
    print(f"Xong: {count} message. Rỗng ngoài giờ giao dịch là bình thường.")


async def main(seconds: int, stream_only: bool, ohlc_only: bool) -> None:
    from ssi_sdk import AsyncData

    symbols: dict[str, str | None]

    if stream_only:
        # Nếu chỉ chạy stream, đọc lại symbols đã khám phá trước đó.
        if not SYMBOLS_OUT.exists():
            print(f"Chưa có {SYMBOLS_OUT} — chạy script không có --stream-only trước.")
            sys.exit(1)
        symbols = json.loads(SYMBOLS_OUT.read_text(encoding="utf-8"))
    else:
        async with await make_auth() as auth:
            data = AsyncData(auth)
            symbols = await discover_symbols(data)

    if not ohlc_only:
        await record_stream(symbols, seconds)
    if not stream_only:
        await fetch_all_ohlc(symbols)


if __name__ == "__main__":
    seconds = 120
    if "--seconds" in sys.argv:
        seconds = int(sys.argv[sys.argv.index("--seconds") + 1])
    stream_only = "--stream-only" in sys.argv
    ohlc_only = "--ohlc-only" in sys.argv
    asyncio.run(main(seconds, stream_only, ohlc_only))
