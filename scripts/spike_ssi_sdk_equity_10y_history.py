"""Phase 0 spike: xác nhận lấy được dữ liệu ngày 10 năm cho cổ phiếu 3 sàn.
Chạy: uv run --with ssi-sdk python scripts/spike_ssi_sdk_equity_10y_history.py

YÊU CẦU TRƯỚC: chạy scripts/spike_ssi_sdk_auth.py để xác thực OTP và lưu token
vào scripts/.ssi_sdk_token.json. Script này đọc lại token đó (KHÔNG xin OTP lại);
nếu access_token hết hạn nó sẽ thử refresh() bằng refresh_token đã lưu.

Mục đích:
- Verify SSI API trả dữ liệu ngày (daily OHLC) trong khoảng 10 năm cho vài mã
  mỗi sàn HOSE/HNX/UPCOM.
- Xác nhận cần tự phân trang thủ công vì API giới hạn size=1000/trang.

Cần env SSI_API_KEY, SSI_API_SECRET.
"""

import asyncio
import dataclasses
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from _ssi_spike_common import make_auth

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

SYMBOLS_OUT = Path(__file__).parent / ".spike_equity_10y_symbols.json"


def _symbols_output_path(symbol: str) -> Path:
    return Path(__file__).parent / f".spike_equity_10y_{symbol}.json"


async def discover_symbols(data) -> dict[str, list[str]]:
    from ssi_sdk.enums import Board

    result: dict[str, list[str]] = {"hose": [], "hnx": [], "upcom": []}

    for label, board in [
        ("hose", Board.HOSE),
        ("hnx", Board.HNX),
        ("upcom", Board.UPCOM),
    ]:
        print(f"\nKhám phá mã {label.upper()}...")
        securities = await data.market_data.get_securities_info_by_board(board)
        if not securities:
            print(f"  -> Board {label.upper()} trả về danh sách rỗng.")
            continue
        chosen = [s.symbol for s in securities[:3]]
        result[label] = chosen
        print(f"  -> {len(securities)} mã; chọn 3 mã đầu: {chosen}")

    SYMBOLS_OUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nĐã ghi mã đã chọn → {SYMBOLS_OUT}")
    return result


async def fetch_daily_10y(data, symbol: str) -> list:
    to_date = datetime.now(VN_TZ).date()
    from_date = to_date.replace(year=to_date.year - 10)
    from_str = f"{from_date:%Y/%m/%d}"
    to_str = f"{to_date:%Y/%m/%d}"
    all_rows = []
    page = 1
    while True:
        rows = await data.market_data.get_ohlc_1day_historical(
            symbol, from_str, to_str, page=page, size=1000
        )
        all_rows.extend(rows)
        print(f"  page {page}: {len(rows)} bar")
        if len(rows) < 1000:
            break
        page += 1
        if page > 20:
            print(f"  !! dừng ở page {page} — vượt guard 20 trang, kiểm tra lại")
            break
    return all_rows


async def fetch_all(data, symbols_by_board: dict[str, list[str]]) -> None:
    for label, symbols in symbols_by_board.items():
        for symbol in symbols:
            print(f"\nLấy dữ liệu ngày 10 năm cho {symbol} ({label.upper()})...")
            rows = await fetch_daily_10y(data, symbol)
            payload = [dataclasses.asdict(r) for r in rows]
            out_path = _symbols_output_path(symbol)
            out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            print(f"Tổng {len(rows)} bar ngày → {out_path}")
            if rows:
                print("Bar đầu:", payload[0])
                print("Bar cuối:", payload[-1])


async def main() -> None:
    from ssi_sdk import AsyncData

    async with await make_auth() as auth:
        data = AsyncData(auth)
        symbols_by_board = await discover_symbols(data)
        await fetch_all(data, symbols_by_board)


if __name__ == "__main__":
    asyncio.run(main())
