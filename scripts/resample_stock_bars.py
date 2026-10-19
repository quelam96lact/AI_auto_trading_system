"""Tạo và lưu trữ các khung thời gian lớn (15m, 1h, 4h) cho dữ liệu cổ phiếu VN.

Đọc nến 5m từ bảng `bars`, resample theo phiên giao dịch Việt Nam
thông qua `trading.resample.resample_bars` và lưu trữ trực tiếp vào bảng `bars_tf`.
"""

from __future__ import annotations

import argparse
import io
import sys
import time

# Ép mã hoá UTF-8 trên Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from trading.models import Bar
from trading.resample import resample_bars
from trading.storage.db import Storage

try:
    from _db_common import load_dotenv, resolve_dsn
except ImportError:
    from scripts._db_common import load_dotenv, resolve_dsn

INTERVAL_MINUTES_MAP: dict[str, int] = {
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
}


def resample_stock_bars_series(
    bars_5m: list[Bar],
    target_interval: str,
) -> list[Bar]:
    """Resample danh sách nến 5m sang khung thời gian chỉ định."""
    target_minutes = INTERVAL_MINUTES_MAP.get(target_interval)
    if not target_minutes:
        raise ValueError(
            f"Khoảng thời gian không hợp lệ: {target_interval}. Hỗ trợ: {list(INTERVAL_MINUTES_MAP.keys())}"
        )
    return resample_bars(bars_5m, target_minutes)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resample dữ liệu nến cổ phiếu 5m sang 15m, 1h, 4h và lưu vào bars_tf"
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="Danh sách mã phân cách bởi dấu phẩy (mặc định: tất cả các mã trong bars)",
    )
    parser.add_argument(
        "--intervals",
        default="15m,1h,4h",
        help="Danh sách khung thời gian phân cách bởi dấu phẩy (mặc định: 15m,1h,4h)",
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="Database DSN (mặc định lấy từ .env hoặc DB_DSN)",
    )
    args = parser.parse_args()

    load_dotenv()
    db_dsn = resolve_dsn(args.dsn)
    storage = Storage(db_dsn)
    storage.init_schema()

    # Lấy danh sách symbols cần xử lý
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        with storage.conn() as c:
            rows = c.execute(
                "SELECT DISTINCT symbol FROM bars ORDER BY symbol"
            ).fetchall()
            symbols = [r[0] for r in rows]

    intervals = [i.strip() for i in args.intervals.split(",") if i.strip()]
    for itv in intervals:
        if itv not in INTERVAL_MINUTES_MAP:
            print(f"Lỗi: Khung thời gian {itv} không được hỗ trợ!", file=sys.stderr)
            sys.exit(1)

    print("=" * 88)
    print(f"Bắt đầu resample cổ phiếu VN cho {len(symbols)} mã trên các khung: {', '.join(intervals)}")
    print("=" * 88)

    t0 = time.time()
    total_bars_created = 0
    symbols_done = 0

    for i, sym in enumerate(symbols, 1):
        # Đọc toàn bộ nến 5m của symbol
        with storage.conn() as c:
            rows = c.execute(
                "SELECT symbol, ts, open, high, low, close, volume, source FROM bars "
                "WHERE symbol = %s ORDER BY ts",
                (sym,),
            ).fetchall()
        bars_5m = [Bar(*r) for r in rows]

        if not bars_5m:
            continue

        symbols_done += 1
        sym_created = 0

        for itv in intervals:
            resampled = resample_stock_bars_series(bars_5m, itv)
            storage.write_stock_tf_bars(resampled, itv)
            sym_created += len(resampled)

        total_bars_created += sym_created

        if i % 25 == 0 or i == len(symbols):
            elapsed = time.time() - t0
            print(f"[{i:3d}/{len(symbols)}] Đã xử lý {sym:<6} | Tổng nến tạo: {total_bars_created:>8,} | Thời gian: {elapsed:>5.1f}s")

    dur = time.time() - t0
    print("=" * 88)
    print(f"TỔNG KẾT RESAMPLE CỔ PHIẾU VN: Đã tạo và lưu {total_bars_created:,} nến ({symbols_done} mã) trong {dur:.1f}s")
    print("=" * 88)


if __name__ == "__main__":
    main()
