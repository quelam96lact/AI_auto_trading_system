"""Xây dựng chuỗi dữ liệu phái sinh liên tục (continuous series) VN30F1M_CONT (Brief 83).

Quy trình:
1. Thu thập dữ liệu nến 5m lịch sử từ SSI API cho các hợp đồng VN30 (41I1*)
   vào bảng bars theo từng symbol độc lập.
2. Xây dựng lịch roll hợp đồng từ metadata (lastTradingDate).
3. Tính toán gap hiệu số tại các mốc roll và lượng cộng dồn luỹ kế (Panama method).
4. Ghép chuỗi và lưu trữ vào bảng bars dưới symbol riêng: VN30F1M_CONT.
5. In báo cáo chi tiết và truy vấn kiểm tra trực tiếp từ DB.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any

# Force UTF-8 stdout/stderr on Windows to avoid UnicodeEncodeError
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from trading.calendar_vn import TZ
from trading.config import load_config
from trading.derivative_series import (
    DEFAULT_CONTINUOUS_SYMBOL,
    ContractMetadata,
    build_roll_schedule,
    compute_roll_gaps,
    stitch_continuous,
)
from trading.models import Bar
from trading.storage.db import Storage

# Danh sách chuỗi hợp đồng front-month theo thứ tự thời gian từ 04/2026 đến 10/2026
FRONT_MONTH_CONTRACTS = [
    ContractMetadata(
        symbol="41I1G4000",
        name="VN30 Index Futures 042026",
        first_trading_date=date(2026, 2, 23),
        last_trading_date=date(2026, 4, 16),
    ),
    ContractMetadata(
        symbol="41I1G5000",
        name="VN30 Index Futures 052026",
        first_trading_date=date(2026, 3, 20),
        last_trading_date=date(2026, 5, 21),
    ),
    ContractMetadata(
        symbol="41I1G6000",
        name="VN30 Index Futures 062026",
        first_trading_date=date(2025, 10, 17),
        last_trading_date=date(2026, 6, 18),
    ),
    ContractMetadata(
        symbol="41I1G7000",
        name="VN30 Index Futures 072026",
        first_trading_date=date(2026, 5, 22),
        last_trading_date=date(2026, 7, 16),
    ),
    ContractMetadata(
        symbol="41I1G8000",
        name="VN30 Index Futures 082026",
        first_trading_date=date(2026, 6, 19),
        last_trading_date=date(2026, 8, 20),
    ),
    ContractMetadata(
        symbol="41I1G9000",
        name="VN30 Index Futures 092026",
        first_trading_date=date(2026, 1, 16),
        last_trading_date=date(2026, 9, 17),
    ),
    ContractMetadata(
        symbol="41I1GA000",
        name="VN30 Index Futures 102026",
        first_trading_date=date(2026, 8, 21),
        last_trading_date=date(2026, 10, 15),
    ),
]

# Các hợp đồng VN30 khác cũng có dữ liệu
OTHER_VN30_CONTRACTS = [
    ContractMetadata(
        symbol="41I1GB000",
        name="VN30 Index Futures 112026",
        first_trading_date=date(2026, 9, 18),
        last_trading_date=date(2026, 11, 19),
    ),
    ContractMetadata(
        symbol="41I1GC000",
        name="VN30 Index Futures 122026",
        first_trading_date=date(2026, 4, 17),
        last_trading_date=date(2026, 12, 17),
    ),
    ContractMetadata(
        symbol="41I1H3000",
        name="VN30 Index Futures 032027",
        first_trading_date=date(2026, 7, 17),
        last_trading_date=date(2027, 3, 18),
    ),
]


def _parse_trading_date(s: str) -> datetime:
    try:
        dt = datetime.strptime(s, "%Y/%m/%d %H:%M:%S")
    except ValueError:
        dt = datetime.strptime(s, "%Y/%m/%d")
    return dt.replace(tzinfo=TZ)


def _ohlc_rows_to_bars(rows) -> list[Bar]:
    out = [
        Bar(
            r.symbol,
            _parse_trading_date(r.trading_date),
            float(r.open_price),
            float(r.high_price),
            float(r.low_price),
            float(r.close_price),
            int(r.volume),
        )
        for r in rows
    ]
    out.sort(key=lambda b: b.ts)
    return out


async def fetch_and_store_contract_5m_bars(
    data,
    storage: Storage,
    symbol: str,
    from_date: date,
    to_date: date,
) -> int:
    """Tải nến 5m theo chunk 7 ngày từ SSI API và lưu vào DB (bỏ qua nến rác O=H=L=C=V=0)."""
    by_ts: dict[str, object] = {}
    chunk_start = from_date
    size = 1000

    while chunk_start <= to_date:
        chunk_end = min(chunk_start + timedelta(days=6), to_date)
        from_str = f"{chunk_start:%Y/%m/%d} 00:00:00"
        to_str = f"{chunk_end:%Y/%m/%d} 23:59:59"
        try:
            rows = await data.market_data.get_ohlc_5minute_historical(
                symbol, from_str, to_str, page=1, size=size
            )
            if rows:
                for r in rows:
                    # Bỏ qua các nến rác ngoài giờ khớp lệnh do SSI API trả về ở phiên gần
                    if float(r.open_price) == 0 and float(r.volume) == 0 and float(r.close_price) == 0:
                        continue
                    by_ts[r.trading_date] = r
        except Exception as e:
            print(f"  [Cảnh báo] Lỗi khi tải {symbol} ({from_str} -> {to_str}): {e}")
        chunk_start = chunk_end + timedelta(days=1)

    raw_bars = _ohlc_rows_to_bars(list(by_ts.values()))
    if raw_bars:
        storage.write_bars(raw_bars)
    return len(raw_bars)


def read_all_bars_for_symbol(storage: Storage, symbol: str) -> list[Bar]:
    """Đọc toàn bộ nến của một symbol từ DB."""
    with storage.conn() as c:
        rows = c.execute(
            "SELECT symbol, ts, open, high, low, close, volume, source FROM bars "
            "WHERE symbol = %s ORDER BY ts ASC",
            (symbol,),
        ).fetchall()
    return [Bar(*r) for r in rows]


def _load_dotenv(env_path: str = ".env") -> None:
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


async def main_async(args: argparse.Namespace) -> None:
    _load_dotenv()
    from ssi_sdk import AsyncAuth, AsyncData
    from ssi_sdk import Config as SsiConfig

    app_cfg = load_config(args.config)
    db_dsn = app_cfg.db_dsn.replace("@localhost:", "@127.0.0.1:")
    storage = Storage(db_dsn)
    storage.init_schema()

    today = datetime.now(TZ).date()

    all_contracts_to_ingest = FRONT_MONTH_CONTRACTS + OTHER_VN30_CONTRACTS

    if not args.stitch_only:
        print("=== BƯỚC 1: NẠP DỮ LIỆU NẾN 5 PHÚT TỪ SSI API CHO TẤT CẢ HỢP ĐỒNG VN30 ===")
        api_key = os.environ.get("SSI_API_KEY")
        api_secret = os.environ.get("SSI_API_SECRET")
        if not api_key or not api_secret:
            print("Lỗi: Thiếu SSI_API_KEY hoặc SSI_API_SECRET trong môi trường!")
            sys.exit(1)

        cfg = SsiConfig(api_key=api_key, api_secret=api_secret)
        auth = AsyncAuth(cfg)
        await auth.authenticate(otp=None)
        data = AsyncData(auth)

        try:
            for c in all_contracts_to_ingest:
                # Dữ liệu 5m trên SSI API bắt đầu khả dụng từ 2026/04/03
                earliest_possible = date(2026, 4, 3)
                start_date = max(c.first_trading_date or earliest_possible, earliest_possible)
                end_date = min(c.last_trading_date, today)

                print(f"Đang nạp nến 5m cho {c.symbol} ({c.name}) từ {start_date} đến {end_date}...")
                n_inserted = await fetch_and_store_contract_5m_bars(
                    data, storage, c.symbol, start_date, end_date
                )
                print(f"  => {c.symbol}: Đã ghi nhận {n_inserted} nến.")
        finally:
            await auth.close()

    print("\n=== BƯỚC 2: TỔNG KẾT DỮ LIỆU CÁC HỢP ĐỒNG TRONG DATABASE ===")
    print(
        f"{'Mã':<12} | {'Tên hợp đồng':<30} | {'Số nến':<8} | {'Số phiên':<8} | {'Ngày đầu':<12} | {'Ngày cuối':<12}"
    )
    print("-" * 92)

    bars_by_symbol: dict[str, list[Bar]] = {}
    contract_summary: list[dict[str, Any]] = []

    for c in FRONT_MONTH_CONTRACTS:
        bars = read_all_bars_for_symbol(storage, c.symbol)
        bars_by_symbol[c.symbol] = bars
        if bars:
            d_first = bars[0].ts.astimezone(TZ).date()
            d_last = bars[-1].ts.astimezone(TZ).date()
            sessions = len({b.ts.astimezone(TZ).date() for b in bars})
            contract_summary.append(
                {
                    "symbol": c.symbol,
                    "name": c.name,
                    "bars_count": len(bars),
                    "sessions": sessions,
                    "first_date": d_first,
                    "last_date": d_last,
                }
            )
            print(
                f"{c.symbol:<12} | {c.name:<30} | {len(bars):<8} | {sessions:<8} | {d_first.isoformat():<12} | {d_last.isoformat():<12}"
            )
        else:
            print(f"{c.symbol:<12} | {c.name:<30} | {'0':<8} | {'0':<8} | {'N/A':<12} | {'N/A':<12}")

    print("\n=== BƯỚC 3: XÂY DỰNG LỊCH ROLL & TÍNH TOÁN HIỆU SỐ (PANAMA GAP) ===")
    # Xây dựng lịch roll từ danh sách FRONT_MONTH_CONTRACTS
    roll_schedule = build_roll_schedule(FRONT_MONTH_CONTRACTS)
    print("Lịch roll dự kiến:")
    for sym, s_d, e_d in roll_schedule:
        print(f"  {sym}: hiệu lực từ {s_d} đến {e_d}")

    # Tính toán gaps tại từng mốc chuyển giao
    roll_gaps = compute_roll_gaps(bars_by_symbol, roll_schedule)
    print("\nBảng giá trị Gap tại từng mốc Roll:")
    print(
        f"{'Từ mã':<10} -> {'Sang mã':<10} | {'Ngày Roll':<10} | {'Thời điểm Overlap':<19} | {'Giá Cũ':<8} | {'Giá Mới':<8} | {'Gap (Điểm)':<10} | {'Cộng dồn (Điểm)'}"
    )
    print("-" * 105)
    for rg in roll_gaps:
        overlap_str = rg.overlap_ts.astimezone(TZ).strftime("%Y-%m-%d %H:%M")
        print(
            f"{rg.from_symbol:<10} -> {rg.to_symbol:<10} | {rg.roll_date.isoformat():<10} | {overlap_str:<19} | {rg.from_close:<8.1f} | {rg.to_close:<8.1f} | {rg.gap:<+10.2f} | {rg.cumulative_adjustment:<+15.2f}"
        )

    print("\n=== BƯỚC 4: GHÉP CHUỖI LIÊN TỤC VN30F1M_CONT VÀ GHI VÀO DATABASE ===")
    stitched_bars = stitch_continuous(
        bars_by_symbol, roll_schedule, continuous_symbol=DEFAULT_CONTINUOUS_SYMBOL
    )
    print(f"Tổng số nến chuỗi liên tục tạo ra: {len(stitched_bars)}")

    # Ghi vào bảng bars
    storage.write_bars(stitched_bars)
    print(f"Đã ghi thành công {len(stitched_bars)} nến vào bảng bars với symbol '{DEFAULT_CONTINUOUS_SYMBOL}'.")

    # Truy vấn đối soát trực tiếp từ DB
    with storage.conn() as c:
        row = c.execute(
            "SELECT symbol, count(*), min(ts), max(ts) FROM bars WHERE symbol = %s GROUP BY symbol",
            (DEFAULT_CONTINUOUS_SYMBOL,),
        ).fetchone()
        daily_rows = c.execute(
            "SELECT date(ts), count(*) FROM bars WHERE symbol = %s GROUP BY date(ts) ORDER BY date(ts) ASC",
            (DEFAULT_CONTINUOUS_SYMBOL,),
        ).fetchall()

    print("\nKết quả truy vấn nguyên văn từ database:")
    print(f"  Symbol: {row[0]}")
    print(f"  Tổng số nến: {row[1]}")
    print(f"  Thời điểm đầu (min_ts): {row[2].astimezone(TZ)}")
    print(f"  Thời điểm cuối (max_ts): {row[3].astimezone(TZ)}")
    print(f"  Tổng số phiên giao dịch liên tục: {len(daily_rows)} phiên")

    print("\nPhân bố số nến 5m trong 5 phiên đầu và 5 phiên cuối:")
    for d, cnt in daily_rows[:5]:
        print(f"  [Đầu] {d}: {cnt} nến")
    for d, cnt in daily_rows[-5:]:
        print(f"  [Cuối] {d}: {cnt} nến")


def main() -> None:
    parser = argparse.ArgumentParser(description="Xây dựng chuỗi phái sinh liên tục (Brief 83).")
    parser.add_argument("--config", default="config/config.yaml", help="Đường dẫn file config")
    parser.add_argument("--stitch-only", action="store_true", help="Chỉ ghép nến từ DB hiện tại, không gọi SSI API")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
