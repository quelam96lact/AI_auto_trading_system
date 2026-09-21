"""Lớp vỏ tương thích ngược cho phép đo hướng ngữ nghĩa timestamp (Brief đợt 72).

Đợt 72 đã gộp probe_timestamp_semantics.py vào scripts/leakage_audit.py:
- Một lõi đo thống nhất: Spearman (thay Pearson) và hoán vị khối P95 (thay ±0.03 cố định).
- Quy tắc gắn cờ thống nhất: NGHI_VAN khi rho_sau > rho_truoc và |rho_sau| > threshold; ngược lại SACH.
- File này giữ vai trò lớp vỏ (thin wrapper) gọi đường vào cột thô từ DB qua audit_raw_columns.
- Lệnh tương đương: python scripts/leakage_audit.py --mode raw
"""

import argparse
import sys
from datetime import UTC, datetime

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

try:
    from leakage_audit import (
        RAW_FEATURE_NAMES,
        audit_raw_columns,
        print_results_table,
    )
except ImportError:
    from scripts.leakage_audit import (
        RAW_FEATURE_NAMES,
        audit_raw_columns,
        print_results_table,
    )

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def pearson_correlation(x: list[float], y: list[float]) -> float:
    """Hàm Pearson cũ (giữ lại để tương thích ngược nếu có mã import).

    LƯU Ý: Phép đo chính thức từ đợt 72 đã chuyển sang Spearman (fast_spearman_rank_correlation)
    trong scripts/leakage_audit.py.
    """
    n = len(x)
    if n < 2:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    var_x = sum((val - mx) ** 2 for val in x)
    var_y = sum((val - my) ** 2 for val in y)
    if var_x < 1e-12 or var_y < 1e-12:
        return 0.0
    cov = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    return cov / ((var_x * var_y) ** 0.5)


def run_probe(
    conn: psycopg.Connection,
    symbol: str = "BTCUSDT",
    is_start: datetime = datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
    is_end: datetime = datetime(2025, 12, 31, 23, 0, tzinfo=UTC),
    raw_columns: list[str] = RAW_FEATURE_NAMES,
    n_permutations: int = 500,
    seed: int = 42,
) -> list[dict]:
    """Chạy phép đo hướng ngữ nghĩa trên các cột thô từ DB qua lõi đo thống nhất."""
    return audit_raw_columns(
        conn,
        symbol=symbol,
        is_start=is_start,
        is_end=is_end,
        raw_columns=raw_columns,
        n_permutations=n_permutations,
        seed=seed,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Đo hướng ngữ nghĩa timestamp của các cột dữ liệu phi giá (gọi lõi thống nhất leakage_audit)."
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--is-start", default="2024-01-01")
    parser.add_argument("--is-end", default="2025-12-31")
    parser.add_argument(
        "--permutations",
        type=int,
        default=500,
        help="Số lần hoán vị khối (mặc định 500; dùng 1000 cho độ chính xác cao nhất)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--raw-columns",
        nargs="+",
        default=RAW_FEATURE_NAMES,
        help="Danh sách cột thô cần đo (mặc định 6 cột chuẩn)",
    )
    parser.add_argument("--dsn", default=None, help="Database DSN override")

    args = parser.parse_args()

    is_start_dt = datetime.fromisoformat(args.is_start).replace(tzinfo=UTC)
    is_end_dt = datetime.fromisoformat(args.is_end).replace(hour=23, minute=0, second=0, tzinfo=UTC)

    conn = psycopg.connect(resolve_dsn(args.dsn))
    print(f"=== KẾT QUẢ PHÉP ĐO HƯỚNG NGỮ NGHĨA TIMESTAMP (LÕI THỐNG NHẤT) — {args.symbol} ===")
    print(f"Khoảng In-Sample (IS): {is_start_dt} -> {is_end_dt} UTC (Năm 2026 NIÊM PHONG)")
    results = run_probe(
        conn,
        symbol=args.symbol,
        is_start=is_start_dt,
        is_end=is_end_dt,
        raw_columns=args.raw_columns,
        n_permutations=args.permutations,
        seed=args.seed,
    )
    conn.close()
    print_results_table(results, label="Cot tho tu DB (mode raw)")


if __name__ == "__main__":
    main()
