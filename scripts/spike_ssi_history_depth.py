"""Spike Task 4: đo độ sâu lịch sử SSI + liệt kê mã 3 sàn.

Chạy: uv run python -m scripts.spike_ssi_history_depth

Trả lời 3 câu:
1. Mỗi sàn có bao nhiêu mã? (get_securities_info_by_board HOSE/HNX/UPCOM)
2. Daily lùi được bao xa? (VCB, cửa sổ 1 tháng tại mốc 1/2/3/5/7/10 năm)
3. 5m lùi được bao xa? (VCB, cửa sổ 1 phiên tại mốc 7/30/60/90/180/365 ngày)

Dùng lại SSIRestClient (trading/collector/backfill.py) + get_securities_info_by_board
qua ensure_authenticated — không tự viết HTTP call mới.
"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from trading.calendar_vn import TZ
from trading.collector.backfill import SSIRestClient
from trading.collector.ssi_auth import ensure_authenticated
from trading.config import load_config
from trading.storage.db import Storage

SYMBOLS_OUT = Path(__file__).parent / ".spike_all_symbols.json"

# Mốc lùi để đo độ sâu
DAILY_BACK_YEARS = [1, 2, 3, 5, 7, 10]
INTRADAY_BACK_DAYS = [125, 128, 129, 130]


async def discover_symbols(data) -> dict[str, list[str]]:
    from ssi_sdk.enums import Board

    result: dict[str, list[str]] = {}
    for label, board in [
        ("HOSE", Board.HOSE),
        ("HNX", Board.HNX),
        ("UPCOM", Board.UPCOM),
    ]:
        try:
            securities = await data.market_data.get_securities_info_by_board(board)
            syms = [s.symbol for s in securities]
            result[label] = syms
            print(f"[san] {label}: {len(syms)} ma | 5 dau: {syms[:5]}")
        except Exception as e:
            print(f"[san] {label}: LOI {type(e).__name__}: {e}")
            result[label] = []
    SYMBOLS_OUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[san] da luu danh sach day du -> {SYMBOLS_OUT}")
    return result


async def measure_daily_depth(client: SSIRestClient, symbol: str) -> None:
    today = datetime.now(TZ).date()
    for back_years in DAILY_BACK_YEARS:
        to = today - timedelta(days=365 * back_years)
        frm = to - timedelta(days=30)  # cua so 1 thang
        try:
            bars = await client.daily_ohlc(symbol, frm, to)
            print(f"[daily] lui {back_years} nam ({frm:%Y-%m}): {len(bars)} bar")
        except Exception as e:
            print(f"[daily] lui {back_years} nam: LOI {type(e).__name__}: {str(e)[:80]}")


async def measure_intraday_depth(client: SSIRestClient, symbol: str) -> None:
    today = datetime.now(TZ).date()
    for back_days in INTRADAY_BACK_DAYS:
        day = today - timedelta(days=back_days)
        try:
            bars = await client.intraday_ohlc(symbol, day, day)
            print(f"[5m]    lui {back_days} ngay ({day:%Y-%m-%d}): {len(bars)} bar")
        except Exception as e:
            print(
                f"[5m]    lui {back_days} ngay: LOI {type(e).__name__}: {str(e)[:80]}"
            )


async def main() -> int:
    cfg = load_config("config/config.yaml")
    storage = Storage(cfg.db_dsn)
    storage.init_schema()

    print("=== Auth ===")
    auth = await ensure_authenticated(cfg, storage)
    from ssi_sdk import AsyncData

    data = AsyncData(auth)

    try:
        print("\n=== 1. So ma moi san ===")
        await discover_symbols(data)

        print("\n=== 2. Do sau daily (VCB) ===")
        client = SSIRestClient(cfg, storage)
        try:
            await measure_daily_depth(client, "VCB")
        finally:
            await client.close()

        print("\n=== 3. Do sau 5m (VCB) ===")
        client = SSIRestClient(cfg, storage)
        try:
            await measure_intraday_depth(client, "VCB")
        finally:
            await client.close()
    finally:
        await auth.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
