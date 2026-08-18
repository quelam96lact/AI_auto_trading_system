"""Kiểm tra tính đầy đủ của bars_daily — mã nào thiếu phiên nào.

Đo và báo cáo:
1. Xác định tập các phiên giao dịch thực bằng đồng thuận số mã theo ngày.
2. Thống kê theo từng mã:
   - first_date, last_date
   - total_bars, dirty_bars (OHLC <= 0)
   - expected_in_lifespan (số phiên kỳ vọng trong [first_date, last_date])
   - missing_middle (thiếu giữa đời sống)
   - missing_tail (thiếu ở đuôi tính đến as_of_date)
3. In tóm tắt ra màn hình và xuất chi tiết ra file CSV.

TUYỆT ĐỐI READ-ONLY: Không INSERT/UPDATE/DELETE.

CLI:
  uv run python scripts/check_data_completeness.py [--dsn ...] [--csv scripts/data_completeness_report.csv] [--limit N] [--symbols HPG,VIC]
"""

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

# Đảm bảo import được _db_common và trading
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _db_common import resolve_dsn

from trading.data_quality import (
    SymbolCompleteness,
    compute_daily_missing_counts,
    evaluate_symbol_completeness,
    find_missing_dates,
    infer_trading_sessions,
)
from trading.storage.db import Storage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kiểm tra tính đầy đủ của dữ liệu bars_daily và phân loại nguyên nhân"
    )
    parser.add_argument("--dsn", default=None, help="Postgres connection DSN")
    parser.add_argument(
        "--csv",
        default="scripts/data_completeness_report.csv",
        help="Đường dẫn file CSV xuất chi tiết",
    )
    parser.add_argument(
        "--min-symbols",
        type=int,
        default=100,
        help="Ngưỡng số mã tối thiểu để công nhận 1 ngày là phiên giao dịch (mặc định: 100)",
    )
    parser.add_argument(
        "--error-threshold",
        type=int,
        default=100,
        help="Ngưỡng số mã vắng trong ngày để phân định lỗi thu thập vs không giao dịch (mặc định: 100)",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Danh sách mã phân cách bởi dấu phẩy (vd: HPG,VIC,VNM)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Giới hạn số mã phân tích (để chạy thử nhanh)",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="Ngày mốc kết thúc (YYYY-MM-DD), mặc định: ngày phiên mới nhất",
    )
    parser.add_argument(
        "--detail",
        action="store_true",
        help="Truy vấn chi tiết các ngày cụ thể bị thiếu cho các mã có lỗ hổng",
    )
    return parser.parse_args()


def get_status_str(item: SymbolCompleteness) -> str:
    tags = []
    if item.missing_middle_collection_error > 0:
        tags.append("COLLECTION_ERROR")
    if item.missing_middle_no_trading > 0:
        tags.append("NO_TRADING")
    if item.missing_tail > 0:
        tags.append("MISSING_TAIL")
    if item.dirty_bars > 0:
        tags.append("DIRTY_BARS")
    if not tags:
        return "FULL"
    return "+".join(tags)



def main() -> None:
    args = parse_args()
    dsn = resolve_dsn(args.dsn)
    storage = Storage(dsn)

    print("=" * 70)
    print("BÁO CÁO KIỂM TRA TÍNH ĐẦY ĐỦ DỮ LIỆU BARS_DAILY")
    print("=" * 70)

    # 1. Đọc thống kê số mã theo ngày và suy phiên giao dịch
    print("[1/4] Đang đọc phân bố số mã theo ngày để suy tập phiên giao dịch...")
    daily_counts = storage.read_daily_symbol_counts()
    trading_sessions = infer_trading_sessions(
        daily_counts, min_symbols=args.min_symbols
    )

    if not trading_sessions:
        print("LỖI: Không tìm thấy phiên giao dịch nào thoả ngưỡng min_symbols!")
        sys.exit(1)

    as_of_date: date | None = None
    if args.as_of:
        as_of_date = datetime.strptime(args.as_of, "%Y-%m-%d").date()
    else:
        as_of_date = trading_sessions[-1]

    print(
        f"  -> Tổng số ngày có bar trong DB: {len(daily_counts):,} ngày"
    )
    print(
        f"  -> Tổng số phiên giao dịch hợp lệ (>= {args.min_symbols} mã): {len(trading_sessions):,} phiên"
    )
    print(
        f"  -> Khoảng thời gian: từ {trading_sessions[0]} đến {trading_sessions[-1]} (As of: {as_of_date})"
    )

    # 2. Đọc thống kê tổng hợp theo mã và tính phân bố thiếu theo phiên
    filter_symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None
    print("[2/4] Đang truy vấn tổng hợp theo mã từ DB và tính phân bố thiếu theo phiên...")
    raw_summaries = storage.read_symbol_completeness_summaries(symbols=filter_symbols)

    session_missing_counts = compute_daily_missing_counts(
        summaries=raw_summaries,
        trading_sessions=trading_sessions,
        daily_counts=daily_counts,
    )

    if args.limit:
        raw_summaries = raw_summaries[: args.limit]

    print(f"  -> Tổng số mã phân tích: {len(raw_summaries):,} mã")
    print(f"  -> Ngưỡng phân định lỗi thu thập: >= {args.error_threshold} mã vắng/phiên")

    # 3. Đánh giá tính đầy đủ từng mã và phân loại nguyên nhân
    print("[3/4] Đang đánh giá tính đầy đủ và phân loại nguyên nhân từng mã...")
    results: list[SymbolCompleteness] = []
    for row in raw_summaries:
        sym = row["symbol"]
        res = evaluate_symbol_completeness(
            symbol=sym,
            first_date=row["first_date"],
            last_date=row["last_date"],
            total_bars=row["total_bars"],
            dirty_bars=row["dirty_bars"],
            trading_sessions=trading_sessions,
            as_of_date=as_of_date,
        )
        if res.missing_middle > 0:
            present_dates = storage.read_symbol_present_dates(sym)
            res = evaluate_symbol_completeness(
                symbol=sym,
                first_date=row["first_date"],
                last_date=row["last_date"],
                total_bars=row["total_bars"],
                dirty_bars=row["dirty_bars"],
                trading_sessions=trading_sessions,
                as_of_date=as_of_date,
                present_dates=present_dates,
                session_missing_counts=session_missing_counts,
                collection_error_threshold=args.error_threshold,
            )
        results.append(res)

    # Thống kê tổng quan
    total_symbols = len(results)
    full_symbols = [
        r for r in results
        if r.missing_middle == 0 and r.missing_tail == 0 and r.dirty_bars == 0
    ]
    collection_error_symbols = [r for r in results if r.missing_middle_collection_error > 0]
    no_trading_symbols = [r for r in results if r.missing_middle_no_trading > 0]
    tail_missing_symbols = [r for r in results if r.missing_tail > 0]
    dirty_symbols = [r for r in results if r.dirty_bars > 0]

    total_gaps_collection = sum(r.missing_middle_collection_error for r in results)
    total_gaps_no_trading = sum(r.missing_middle_no_trading for r in results)
    total_gaps_tail = sum(r.missing_tail for r in results)

    print("\n" + "=" * 70)
    print("KẾT QUẢ TỔNG QUAN:")
    print(f"  - Tổng số mã phân tích        : {total_symbols:,}")
    print(
        f"  - Số mã ĐẦY ĐỦ 100% (không lỗi): {len(full_symbols):,} ({len(full_symbols)/total_symbols*100:.1f}%)"
    )
    print(
        f"  - Số mã dính LỖI THU THẬP     : {len(collection_error_symbols):,} ({len(collection_error_symbols)/total_symbols*100:.1f}%) [Tổng: {total_gaps_collection:,} phiên-mã]"
    )
    print(
        f"  - Số mã KHÔNG GIAO DỊCH       : {len(no_trading_symbols):,} ({len(no_trading_symbols)/total_symbols*100:.1f}%) [Tổng: {total_gaps_no_trading:,} phiên-mã]"
    )
    print(
        f"  - Số mã THIẾU Ở ĐUÔI (ngừng GD): {len(tail_missing_symbols):,} ({len(tail_missing_symbols)/total_symbols*100:.1f}%) [Tổng: {total_gaps_tail:,} phiên-mã]"
    )
    print(
        f"  - Số mã CÓ BAR RÁC (OHLC <= 0): {len(dirty_symbols):,} ({len(dirty_symbols)/total_symbols*100:.1f}%)"
    )
    print("=" * 70)

    # Top 10 lỗi thu thập
    if collection_error_symbols:
        top_err = sorted(collection_error_symbols, key=lambda x: x.missing_middle_collection_error, reverse=True)[:10]
        print("\nTOP 10 MÃ THIẾU NHIỀU PHIÊN NHẤT DO LỖI THU THẬP (vắng tương quan):")
        print(f"  {'Mã':<8} {'Từ ngày':<12} {'Đến ngày':<12} {'Kỳ vọng':<10} {'Thực có':<10} {'Lỗi thu thập':<14} {'Ko GD':<10}")
        print("  " + "-" * 78)
        for r in top_err:
            print(
                f"  {r.symbol:<8} {r.first_date!s:<12} {r.last_date!s:<12} "
                f"{r.expected_in_lifespan:<10} {r.total_bars:<10} {r.missing_middle_collection_error:<14} {r.missing_middle_no_trading:<10}"
            )

    # Top 10 không có giao dịch
    if no_trading_symbols:
        top_no_trade = sorted(no_trading_symbols, key=lambda x: x.missing_middle_no_trading, reverse=True)[:10]
        print("\nTOP 10 MÃ THIẾU NHIỀU PHIÊN NHẤT DO KHÔNG GIAO DỊCH (mã tắt thanh khoản):")
        print(f"  {'Mã':<8} {'Từ ngày':<12} {'Đến ngày':<12} {'Kỳ vọng':<10} {'Thực có':<10} {'Ko GD':<10} {'Lỗi thu thập':<14}")
        print("  " + "-" * 78)
        for r in top_no_trade:
            print(
                f"  {r.symbol:<8} {r.first_date!s:<12} {r.last_date!s:<12} "
                f"{r.expected_in_lifespan:<10} {r.total_bars:<10} {r.missing_middle_no_trading:<10} {r.missing_middle_collection_error:<14}"
            )

    # Top 10 thiếu ở đuôi
    if tail_missing_symbols:
        top_tail = sorted(tail_missing_symbols, key=lambda x: x.missing_tail, reverse=True)[:10]
        print("\nTOP 10 MÃ THIẾU NHIỀU PHIÊN NHẤT Ở ĐUÔI (hủy niêm yết / ngừng GD dài):")
        print(f"  {'Mã':<8} {'Từ ngày':<12} {'Bar cuối':<12} {'Thực có':<10} {'Thiếu đuôi':<12} {'Bar rác':<10}")
        print("  " + "-" * 66)
        for r in top_tail:
            print(
                f"  {r.symbol:<8} {r.first_date!s:<12} {r.last_date!s:<12} "
                f"{r.total_bars:<10} {r.missing_tail:<12} {r.dirty_bars:<10}"
            )

    # Top 10 mã có bar rác
    if dirty_symbols:
        top_dirty = sorted(dirty_symbols, key=lambda x: x.dirty_bars, reverse=True)[:10]
        print("\nTOP 10 MÃ CÓ NHIỀU BAR RÁC NHẤT (OHLC <= 0):")
        print(f"  {'Mã':<8} {'Từ ngày':<12} {'Đến ngày':<12} {'Tổng bar':<10} {'Bar rác':<10} {'Tỉ lệ':<10}")
        print("  " + "-" * 64)
        for r in top_dirty:
            ratio = (r.dirty_bars / r.total_bars * 100) if r.total_bars > 0 else 0
            print(
                f"  {r.symbol:<8} {r.first_date!s:<12} {r.last_date!s:<12} "
                f"{r.total_bars:<10} {r.dirty_bars:<10} {ratio:.2f}%"
            )

    # 4. Xuất CSV chi tiết
    csv_path = Path(args.csv)
    print(f"\n[4/4] Đang ghi báo cáo chi tiết vào file CSV: {csv_path}...")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "symbol",
            "first_date",
            "last_date",
            "total_bars",
            "dirty_bars",
            "expected_in_lifespan",
            "missing_middle",
            "missing_middle_no_trading",
            "missing_middle_collection_error",
            "missing_tail",
            "completeness_lifespan_pct",
            "status",
        ])
        for r in results:
            pct = (
                min(100.0, (r.total_bars / r.expected_in_lifespan * 100))
                if r.expected_in_lifespan > 0
                else 0.0
            )
            writer.writerow([
                r.symbol,
                r.first_date,
                r.last_date,
                r.total_bars,
                r.dirty_bars,
                r.expected_in_lifespan,
                r.missing_middle,
                r.missing_middle_no_trading,
                r.missing_middle_collection_error,
                r.missing_tail,
                f"{pct:.2f}",
                get_status_str(r),
            ])

    print(f"  -> Đã ghi thành công {len(results):,} dòng vào {csv_path}")

    # Nếu có cờ --detail, hiển thị mẫu chi tiết ngày thiếu cho một vài mã
    if args.detail:
        print("\n--- CHI TIẾT CÁC NGÀY THIẾU (SAMPLE) ---")
        gapped = [r for r in results if r.missing_middle > 0][:5]
        for r in gapped:
            present = storage.read_symbol_present_dates(r.symbol)
            m_dates, t_dates = find_missing_dates(
                present_dates=present,
                trading_sessions=trading_sessions,
                first_date=r.first_date,
                last_date=r.last_date,
                as_of_date=as_of_date,
            )
            print(f"Mã {r.symbol}: thiếu {len(m_dates)} ngày giữa ({r.missing_middle_collection_error} lỗi thu thập, {r.missing_middle_no_trading} ko GD), {len(t_dates)} ngày đuôi")
            if m_dates:
                print(f"  -> Ngày thiếu giữa (tối đa 10 ngày đầu): {[str(d) for d in m_dates[:10]]}")



if __name__ == "__main__":
    main()
