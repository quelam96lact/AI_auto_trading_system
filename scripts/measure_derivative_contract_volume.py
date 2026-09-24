"""Đo khối lượng giao dịch các hợp đồng phái sinh VN đang lưu hành (Brief 82).

Xác định hợp đồng phái sinh VN có khối lượng lớn nhất bằng số đo thật từ SSI Data API.
Tách bạch hàm tính toán thuần để kiểm thử đơn vị độc lập với SSI SDK.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import statistics
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta

# Force UTF-8 stdout/stderr on Windows to avoid UnicodeEncodeError with Vietnamese characters
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from trading.calendar_vn import TZ
from trading.config import load_config
from trading.models import Bar
from trading.storage.db import Storage

# Tiền tố mã phái sinh HNX:
# 41I1 = VN30 Index Futures
# 41I2 = VN100 Index Futures
PREFIX_VN30 = "41I1"
PREFIX_VN100 = "41I2"

# Bảng OI chép tay từ UI SSI ngày 26/07/2026 (scripts/spike_ssi_sdk_derivative_account.py:38-47)
JULY_26_OI_TABLE: dict[str, int] = {
    "41I1G8000": 39_352,
    "41I1G9000": 1_140,
    "41I1GC000": 843,
    "41I1H3000": 36,
    "41I2G8000": 68,
    "41I2G9000": 19,
    "41I2GC000": 42,
    "41I2H3000": 6,
}


@dataclass(frozen=True)
class ContractInfo:
    symbol: str
    name: str
    board: str
    first_trading_date: str
    last_trading_date: str


@dataclass(frozen=True)
class ContractVolumeStats:
    symbol: str
    name: str
    sessions_count: int
    total_volume: int
    median_volume: float
    volume_share_pct: float


def compute_volume_stats(
    contracts_data: dict[str, tuple[str, list[int]]],
) -> list[ContractVolumeStats]:
    """Hàm thuần (không I/O): Tính thống kê khối lượng các hợp đồng.

    Args:
        contracts_data: dict {symbol: (name, [vol_1, vol_2, ...])}

    Returns:
        Danh sách ContractVolumeStats sắp xếp giảm dần theo total_volume.
    """
    total_market_volume = sum(sum(vols) for _, vols in contracts_data.values())
    results: list[ContractVolumeStats] = []

    for sym, (name, vols) in contracts_data.items():
        n_sessions = len(vols)
        tot_vol = sum(vols)
        med_vol = float(statistics.median(vols)) if vols else 0.0
        share_pct = (
            (tot_vol / total_market_volume * 100.0) if total_market_volume > 0 else 0.0
        )
        results.append(
            ContractVolumeStats(
                symbol=sym,
                name=name,
                sessions_count=n_sessions,
                total_volume=tot_vol,
                median_volume=med_vol,
                volume_share_pct=round(share_pct, 2),
            )
        )

    results.sort(key=lambda s: s.total_volume, reverse=True)
    return results


def find_winning_contract(
    stats: list[ContractVolumeStats],
) -> ContractVolumeStats | None:
    """Trả về hợp đồng có tổng khối lượng lớn nhất."""
    return stats[0] if stats else None


def filter_living_contracts(
    contracts: list[ContractInfo], as_of: date
) -> list[ContractInfo]:
    """Hàm thuần: Lọc các hợp đồng còn sống tại ngày as_of (last_trading_date >= as_of)."""
    living = []
    for c in contracts:
        if not c.last_trading_date:
            continue
        d_str = c.last_trading_date.replace("-", "/")
        parts = d_str.split("/")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            l_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
            if l_date >= as_of:
                living.append(c)
    return living


def identify_front_month(
    living_contracts: list[ContractInfo], as_of: date
) -> ContractInfo | None:
    """Hàm thuần: Tìm hợp đồng front-month (last_trading_date gần nhất trong tương lai)."""
    if not living_contracts:
        return None

    def _dist(c: ContractInfo) -> int:
        d_str = c.last_trading_date.replace("-", "/")
        parts = [int(p) for p in d_str.split("/")]
        return (date(parts[0], parts[1], parts[2]) - as_of).days

    future_contracts = [c for c in living_contracts if _dist(c) >= 0]
    if not future_contracts:
        return None
    return min(future_contracts, key=_dist)


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


async def discover_derivative_contracts(data) -> list[ContractInfo]:
    """Khảo sát và lấy danh sách các hợp đồng phái sinh từ SSI API."""
    months = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "A", "B", "C"]
    years = ["G", "H"]  # G=2026, H=2027
    prefixes = [PREFIX_VN30, PREFIX_VN100]

    found: list[ContractInfo] = []
    for prefix in prefixes:
        for y in years:
            for m in months:
                sym = f"{prefix}{y}{m}000"
                try:
                    res = await data.market_data._rest.get(
                        "/api/v3/data/securitiesByBoard", params={"symbol": sym}
                    )
                    if res:
                        item = res[0]
                        found.append(
                            ContractInfo(
                                symbol=item.get("symbol", sym),
                                name=item.get("symbolNameVi") or "",
                                board=item.get("board") or "DERIVATIVES",
                                first_trading_date=item.get("firstTradingDate") or "",
                                last_trading_date=item.get("lastTradingDate") or "",
                            )
                        )
                except Exception:
                    pass
    return found


async def fetch_recent_session_volumes(
    data, symbol: str, lookback_sessions: int = 20
) -> list[int]:
    """Lấy dữ liệu nến ngày và trích xuất khối lượng của tối đa lookback_sessions phiên gần nhất."""
    # 20 phiên giao dịch tương đương khoảng 35 ngày lịch
    today = datetime.now(TZ).date()
    from_date = today - timedelta(days=50)

    from_str = f"{from_date:%Y/%m/%d} 00:00:00"
    to_str = f"{today:%Y/%m/%d} 23:59:59"

    rows = await data.market_data.get_ohlc_1day_historical(
        symbol, from_str, to_str, page=1, size=100
    )
    if not rows:
        return []

    # API trả về theo thứ tự giảm dần thời gian (mới nhất đầu tiên)
    recent = rows[:lookback_sessions]
    return [int(r.volume) for r in recent]


async def ingest_5m_bars_for_contract(
    data, storage: Storage, symbol: str, start_date_str: str, end_date: date
) -> int:
    """Nạp nến 5m cho toàn bộ thời gian của hợp đồng vào bảng bars_derivative."""
    d_parts = [int(p) for p in start_date_str.replace("-", "/").split("/")]
    frm = date(d_parts[0], d_parts[1], d_parts[2])

    size = 1000
    by_ts: dict[str, object] = {}
    chunk_start = frm

    while chunk_start <= end_date:
        chunk_end = min(chunk_start + timedelta(days=6), end_date)
        from_str = f"{chunk_start:%Y/%m/%d} 00:00:00"
        to_str = f"{chunk_end:%Y/%m/%d} 23:59:59"
        rows = await data.market_data.get_ohlc_5minute_historical(
            symbol, from_str, to_str, page=1, size=size
        )
        for r in rows:
            by_ts[r.trading_date] = r
        chunk_start = chunk_end + timedelta(days=1)

    bars = _ohlc_rows_to_bars(list(by_ts.values()))
    if bars:
        # Dot 84: nen phai sinh thuoc bang rieng bars_derivative. Ghi vao `bars` se lam
        # nhiem lai universe co phieu (measure_octopus_5m_universe.py doc DISTINCT symbol).
        storage.write_derivative_bars(bars)
    return len(bars)


async def main_async(args) -> None:
    from ssi_sdk import AsyncAuth, AsyncData
    from ssi_sdk import Config as SsiConfig

    api_key = os.environ.get("SSI_API_KEY")
    api_secret = os.environ.get("SSI_API_SECRET")
    if not api_key or not api_secret:
        print("Lỗi: Thiếu SSI_API_KEY hoặc SSI_API_SECRET trong môi trường!")
        sys.exit(1)

    cfg = SsiConfig(api_key=api_key, api_secret=api_secret)
    auth = AsyncAuth(cfg)
    await auth.authenticate(otp=None)
    data = AsyncData(auth)

    today = datetime.now(TZ).date()

    try:
        print(f"=== BƯỚC 1: KHẢO SÁT HỢP ĐỒNG PHÁI SINH TẠI NGÀY {today.isoformat()} ===")
        all_contracts = await discover_derivative_contracts(data)

        print("\nBảng tổng hợp tất cả các hợp đồng tìm thấy:")
        print(
            f"{'Mã':<12} | {'Tên hợp đồng':<30} | {'Ngày GD đầu':<12} | {'Ngày GD cuối':<12} | {'Trạng thái'}"
        )
        print("-" * 85)
        for c in all_contracts:
            l_parts = [int(p) for p in c.last_trading_date.replace("-", "/").split("/")]
            l_date = date(l_parts[0], l_parts[1], l_parts[2])
            status = "CÒN SỐNG" if l_date >= today else "HẾT HẠN"
            print(
                f"{c.symbol:<12} | {c.name:<30} | {c.first_trading_date:<12} | {c.last_trading_date:<12} | {status}"
            )

        living = filter_living_contracts(all_contracts, today)
        print(f"\n=> Tổng số mã tìm thấy: {len(all_contracts)}, số mã còn sống: {len(living)}")

        front_vn30 = identify_front_month(
            [c for c in living if c.symbol.startswith(PREFIX_VN30)], today
        )
        front_vn100 = identify_front_month(
            [c for c in living if c.symbol.startswith(PREFIX_VN100)], today
        )
        print(f"=> Front-month VN30 (41I1): {front_vn30.symbol if front_vn30 else 'None'} ({front_vn30.name if front_vn30 else ''})")
        print(f"=> Front-month VN100 (41I2): {front_vn100.symbol if front_vn100 else 'None'} ({front_vn100.name if front_vn100 else ''})")

        print("\n=== BƯỚC 2: ĐO KHỐI LƯỢNG THẬT 20 PHIÊN GẦN NHẤT & XẾP HẠNG ===")
        print("Đang tải dữ liệu daily OHLC từ SSI API (endpoint: get_ohlc_1day_historical)...")

        contracts_data: dict[str, tuple[str, list[int]]] = {}
        for c in living:
            vols = await fetch_recent_session_volumes(data, c.symbol, lookback_sessions=20)
            contracts_data[c.symbol] = (c.name, vols)

        stats = compute_volume_stats(contracts_data)

        print("\nBẢNG XẾP HẠNG KHỐI LƯỢNG GIAO DỊCH 20 PHIÊN GẦN NHẤT:")
        print(
            f"{'Hạng':<5} | {'Mã':<12} | {'Tên hợp đồng':<30} | {'Số phiên':<8} | {'Tổng khối lượng':<16} | {'Trung vị/phiên':<14} | {'Tỷ trọng (%)':<12}"
        )
        print("-" * 110)
        for idx, s in enumerate(stats, 1):
            print(
                f"{idx:<5} | {s.symbol:<12} | {s.name:<30} | {s.sessions_count:<8} | {s.total_volume:<16,} | {s.median_volume:<14,.1f} | {s.volume_share_pct:<12.2f}"
            )

        winner = find_winning_contract(stats)
        if winner:
            print(f"\n=> KẾT LUẬN: Hợp đồng có khối lượng lớn nhất là {winner.symbol} ({winner.name}), chiếm {winner.volume_share_pct:.2f}% tổng khối lượng toàn thị trường phái sinh.")

        print("\nĐối chiếu với bảng OI ngày 26/07/2026 (UI SSI):")
        print(f"{'Mã 26/07':<12} | {'OI 26/07':<10} | {'Mã tương ứng 24/09':<20} | {'Tổng Vol 20 phiên'}")
        print("-" * 65)
        for sym_july, oi_july in JULY_26_OI_TABLE.items():
            matching_stat = next((s for s in stats if s.symbol == sym_july), None)
            vol_str = f"{matching_stat.total_volume:,}" if matching_stat else "Đã đáo hạn"
            print(f"{sym_july:<12} | {oi_july:<10,} | {sym_july:<20} | {vol_str}")

        if args.ingest and winner:
            print(f"\n=== BƯỚC 3: NẠP NẾN 5 PHÚT CHO HỢP ĐỒNG THẮNG ({winner.symbol}) ===")
            app_cfg = load_config(args.config)
            db_dsn = app_cfg.db_dsn.replace("@localhost:", "@127.0.0.1:")
            storage = Storage(db_dsn)
            storage.init_schema()

            winner_info = next((c for c in living if c.symbol == winner.symbol), None)
            start_date_str = winner_info.first_trading_date if winner_info else "2026/08/21"

            print(f"Bắt đầu nạp nến 5m từ {start_date_str} đến {today.isoformat()} vào bảng bars_derivative...")
            n_ingested = await ingest_5m_bars_for_contract(
                data, storage, winner.symbol, start_date_str, today
            )
            print(f"Đã nạp xong {n_ingested} nến vào bảng bars_derivative.")

            # Truy vấn kiểm tra lại từ DB
            with storage.conn() as c:
                row = c.execute(
                    "SELECT count(*), min(ts), max(ts) FROM bars_derivative WHERE symbol = %s",
                    (winner.symbol,),
                ).fetchone()
                total_in_db, min_ts, max_ts = row

                # Thống kê phân bố số nến theo ngày
                daily_counts = c.execute(
                    "SELECT (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date, count(*) FROM bars_derivative "
                    "WHERE symbol = %s GROUP BY 1 ORDER BY 1",
                    (winner.symbol,),
                ).fetchall()

            print("\nKết quả truy vấn bảng bars_derivative:")
            print(f"  Symbol: {winner.symbol}")
            print(f"  Số nến: {total_in_db}")
            print(f"  Ngày đầu (min_ts): {min_ts}")
            print(f"  Ngày cuối (max_ts): {max_ts}")

            print("\nPhân bố số nến 5m theo phiên:")
            for d, cnt in daily_counts:
                print(f"  {d}: {cnt} nến")

    finally:
        await auth.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Đo khối lượng hợp đồng phái sinh VN (Brief 82).")
    parser.add_argument("--config", default="config/config.yaml", help="Đường dẫn file config")
    parser.add_argument("--ingest", action="store_true", help="Nạp nến 5m cho hợp đồng thắng vào DB")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
