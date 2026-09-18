"""Báo cáo vệ sinh bảng orders (Brief 49 Task 3.2).

Mục tiêu:
Script CHỈ ĐỌC (SELECT thuần túy), kiểm tra các mã hiện diện trong bảng orders,
phân loại:
1. trong config.symbols — bình thường
2. không trong config nhưng có trong bars_daily — lịch sử hợp lệ (ví dụ HII)
3. không phải mã thật — nghi là dấu vết test (ví dụ TEST)

Cuối cùng in câu lệnh DELETE soạn sẵn cho nhóm thứ 3 (nếu có) để chủ dự án
tự quyết định. Script TUYỆT ĐỐI KHÔNG chạy lệnh DELETE.

Chạy:
  uv run python scripts/check_orders_hygiene.py [--dsn DSN] [--config CONFIG_PATH]
"""

import argparse
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from _db_common import load_dotenv, resolve_dsn
except ImportError:
    from scripts._db_common import load_dotenv, resolve_dsn

from trading.config import load_config

TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Báo cáo vệ sinh bảng orders (CHỈ ĐỌC, KHÔNG XOÁ)"
    )
    parser.add_argument("--dsn", default=None, help="Postgres connection DSN")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Đường dẫn file cấu hình config.yaml",
    )
    return parser.parse_args()


def format_ts(ts) -> str:
    if ts is None:
        return "N/A"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=ZoneInfo("UTC"))
    return ts.astimezone(TZ_VN).strftime("%Y-%m-%d %H:%M:%S")


def check_orders_hygiene(dsn: str, config_path: str = "config/config.yaml") -> int:
    load_dotenv()
    cfg = load_config(config_path)
    configured_symbols = set(cfg.symbols)

    print("=" * 80)
    print("BÁO CÁO VỆ SINH BẢNG ORDERS (CHỈ ĐỌC — KHÔNG XOÁ DỮ LIỆU)")
    print(f"Cấu hình symbols: {sorted(configured_symbols)}")
    print("=" * 80)

    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SET TimeZone='Asia/Ho_Chi_Minh';")

            # 1. Truy vấn nhóm theo symbol
            cur.execute("""
                SELECT symbol, count(*), min(ts), max(ts)
                FROM orders
                GROUP BY 1
                ORDER BY symbol;
            """)
            order_rows = cur.fetchall()

            if not order_rows:
                print("\nBảng orders hiện tại không có dòng nào.")
                return 0

            # 2. Phân loại từng symbol
            classified_results = []
            test_symbols = []
            total_orders = 0

            for sym, cnt, min_ts, max_ts in order_rows:
                total_orders += cnt
                if sym in configured_symbols:
                    category = "trong config.symbols (bình thường)"
                else:
                    # Kiểm tra xem có trong bars_daily không
                    cur.execute(
                        "SELECT 1 FROM bars_daily WHERE symbol = %s LIMIT 1;",
                        (sym,),
                    )
                    has_daily = cur.fetchone() is not None
                    if has_daily:
                        category = "không trong config nhưng có trong bars_daily (lịch sử hợp lệ)"
                    else:
                        category = "không phải mã thật (nghi là dấu vết test)"
                        test_symbols.append((sym, cnt))

                classified_results.append({
                    "symbol": sym,
                    "count": cnt,
                    "first_ts": format_ts(min_ts),
                    "last_ts": format_ts(max_ts),
                    "category": category,
                })

            # 3. In bảng kết quả
            print(f"\n{'Mã':<6} | {'Số dòng':<8} | {'Mốc đầu (VN)':<20} | {'Mốc cuối (VN)':<20} | {'Phân loại'}")
            print("-" * 110)
            for row in classified_results:
                print(
                    f"{row['symbol']:<6} | "
                    f"{row['count']:<8} | "
                    f"{row['first_ts']:<20} | "
                    f"{row['last_ts']:<20} | "
                    f"{row['category']}"
                )
            print("-" * 110)
            print(f"Tổng số dòng trong bảng orders: {total_orders}")

            # 4. In câu lệnh DELETE soạn sẵn cho nhóm thứ ba (nếu có)
            print("\n" + "=" * 80)
            if test_symbols:
                print("PHÁT HIỆN MÃ NGHI LÀ DẤU VẾT TEST:")
                for s, c in test_symbols:
                    print(f"  - Mã '{s}': {c} dòng")

                sym_list_sql = ", ".join(f"'{s}'" for s, _ in test_symbols)
                print("\n[CẢNH BÁO] Script này CHỈ ĐỌC, KHÔNG tự ý xóa bất kỳ dữ liệu nào trên DB.")
                print("Chủ dự án có thể cân nhắc chạy câu lệnh SQL soạn sẵn dưới đây trên psql / DB GUI:")
                print("-" * 80)
                if len(test_symbols) == 1:
                    print(f"DELETE FROM orders WHERE symbol = '{test_symbols[0][0]}';")
                else:
                    print(f"DELETE FROM orders WHERE symbol IN ({sym_list_sql});")
                print("-" * 80)
            else:
                print("Không phát hiện mã test / mã lạ nào trong bảng orders.")
            print("=" * 80)

            return 0
    finally:
        conn.close()


def main() -> None:
    args = parse_args()
    dsn = resolve_dsn(args.dsn)
    exit_code = check_orders_hygiene(dsn, args.config)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
