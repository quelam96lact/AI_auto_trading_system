"""Kiểm tra độ bám của giá perpetual BingX theo từng mốc giờ UTC (Brief đợt 117).

Tái lập và kiểm định độ bám theo 24 mốc giờ UTC giữa nến 1h BingX và chuỗi giá gốc.
Chỉ đọc bars_crypto và bars_ext_daily.
Không commit, không push, không đặt lệnh.
Không đọc dữ liệu từ 2026-09-01.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from typing import Any

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

try:
    from check_bingx_tracking import (
        compute_basis_stats,
        compute_daily_returns,
        compute_pearson_correlation,
        compute_tracking_error_annualized,
    )
except ImportError:
    from scripts.check_bingx_tracking import (
        compute_basis_stats,
        compute_daily_returns,
        compute_pearson_correlation,
        compute_tracking_error_annualized,
    )

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SEALED_MAX_TIMESTAMP_STR = "2026-08-31 23:59:59+00"
SEALED_MAX_DATE_STR = "2026-08-31"

PAIRS_CONFIG = [
    {
        "pair_name": "EUR/USD x FRB_H10",
        "bingx_symbol": "NCFXEUR2USD-USDT",
        "ext_source": "FRB_H10",
        "ext_symbol": "EURUSD",
        "expected_best_hour": 16,
    },
    {
        "pair_name": "EUR/USD x ECB",
        "bingx_symbol": "NCFXEUR2USD-USDT",
        "ext_source": "ECB",
        "ext_symbol": "EURUSD",
        "expected_best_hour": 11,
    },
    {
        "pair_name": "USD/JPY x FRB_H10",
        "bingx_symbol": "NCFXUSD2JPY-USDT",
        "ext_source": "FRB_H10",
        "ext_symbol": "USDJPY",
        "expected_best_hour": 16,
    },
]


# ---------------------------------------------------------------------------
# 1. Các hàm thuần logic theo mốc giờ (Có Unit Test)
# ---------------------------------------------------------------------------

def extract_hourly_series(
    bars_1h: list[tuple[datetime, float]],
    target_hour: int,
) -> dict[date, float]:
    """Lấy chuỗi close của nến 1h tại đúng target_hour (0-23 UTC), mỗi ngày 1 điểm.

    Nếu có nhiều điểm trong cùng ngày (không nên xảy ra với 1h), giữ điểm cuối cùng.
    """
    if not (0 <= target_hour <= 23):
        raise ValueError(f"target_hour phải từ 0 đến 23, nhận được {target_hour}")

    result: dict[date, float] = {}
    for ts, close_val in bars_1h:
        if ts.hour == target_hour:
            d = ts.date()
            result[d] = close_val
    return result


def match_and_align_dates(
    bingx_by_date: dict[date, float],
    ext_by_date: dict[date, float],
) -> tuple[list[float], list[float], list[date]]:
    """Ghép hai chuỗi theo ngày giao nhau (intersection) theo thứ tự thời gian.

    QUAN TRỌNG: Ghép ngày trước, sau đó mới tính lợi suất trên tập ngày đã khớp.
    Trả về: (bingx_prices, ext_prices, common_dates).
    """
    common_dates = sorted(d for d in bingx_by_date if d in ext_by_date)
    bingx_prices = [bingx_by_date[d] for d in common_dates]
    ext_prices = [ext_by_date[d] for d in common_dates]
    return bingx_prices, ext_prices, common_dates


def evaluate_hourly_tracking(
    bingx_prices: list[float],
    ext_prices: list[float],
    annual_factor: float = 252.0,
) -> dict[str, Any]:
    """Tính các chỉ số độ bám trên hai chuỗi giá đã được ghép ngày.

    QUY TẮC BẮT BUỘC (Brief 117 B1):
    Ghép ngày trước, sau đó tính lợi suất trên các ngày đã khớp.
    """
    if len(bingx_prices) < 2 or len(bingx_prices) != len(ext_prices):
        raise ValueError(
            f"Không đủ dữ liệu để đánh giá: cần ít nhất 2 ngày khớp, nhận được {len(bingx_prices)}"
        )

    # 1. Tính basis trên các điểm giá
    basis_stats = compute_basis_stats(bingx_prices, ext_prices)

    # 2. Tính chuỗi lợi suất ngày trên tập ngày đã ghép
    r_bingx = compute_daily_returns(bingx_prices)
    r_ext = compute_daily_returns(ext_prices)

    # 3. Tính tương quan Pearson
    corr = compute_pearson_correlation(r_bingx, r_ext)

    # 4. Tính tracking error năm hóa
    te = compute_tracking_error_annualized(r_bingx, r_ext, annual_factor=annual_factor)

    return {
        "matched_dates_count": len(bingx_prices),
        "returns_count": len(r_bingx),
        "returns_corr": corr,
        "tracking_error_annual": te,
        "basis_stats": basis_stats,
    }


def align_and_evaluate(
    bingx_by_date: dict[date, float],
    ext_by_date: dict[date, float],
    annual_factor: float = 252.0,
) -> tuple[dict[str, Any], list[date]]:
    """Ghép hai chuỗi theo ngày trước, sau đó mới tính các chỉ số độ bám."""
    b_prices, e_prices, common_dates = match_and_align_dates(bingx_by_date, ext_by_date)
    if len(common_dates) < 2:
        raise ValueError(f"Không đủ ngày chung để đánh giá: {len(common_dates)}")
    eval_res = evaluate_hourly_tracking(b_prices, e_prices, annual_factor=annual_factor)
    return eval_res, common_dates


# ---------------------------------------------------------------------------
# 2. Đọc cơ sở dữ liệu
# ---------------------------------------------------------------------------

def load_bingx_1h_bars_from_db(
    conn: psycopg.Connection,
    symbol: str,
) -> list[tuple[datetime, float]]:
    """Đọc nến 1h BingX từ bars_crypto up to 2026-08-31 23:59:59 UTC."""
    sql = """
        SELECT ts, close
        FROM bars_crypto
        WHERE symbol = %s AND interval = '1h' AND ts <= %s
        ORDER BY ts ASC;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (symbol, SEALED_MAX_TIMESTAMP_STR))
        return [(r[0], float(r[1])) for r in cur.fetchall()]


def load_ext_daily_dict_from_db(
    conn: psycopg.Connection,
    source: str,
    symbol: str,
) -> dict[date, float]:
    """Đọc chuỗi giá đóng cửa tài sản gốc từ bars_ext_daily up to 2026-08-31."""
    sql = """
        SELECT date, close
        FROM bars_ext_daily
        WHERE source = %s AND symbol = %s AND date <= %s
        ORDER BY date ASC;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (source, symbol, SEALED_MAX_DATE_STR))
        return {r[0]: float(r[1]) for r in cur.fetchall()}


# ---------------------------------------------------------------------------
# 3. Quét 24 mốc giờ và in bảng báo cáo
# ---------------------------------------------------------------------------

def scan_hourly_tracking_for_pair(
    conn: psycopg.Connection,
    bingx_symbol: str,
    ext_source: str,
    ext_symbol: str,
) -> list[dict[str, Any]]:
    """Quét 24 giờ UTC (0 đến 23) cho một cặp tài sản, sắp xếp theo tương quan giảm dần."""
    raw_1h = load_bingx_1h_bars_from_db(conn, bingx_symbol)
    ext_daily = load_ext_daily_dict_from_db(conn, ext_source, ext_symbol)

    results: list[dict[str, Any]] = []

    for h in range(24):
        b_hour_dict = extract_hourly_series(raw_1h, h)
        try:
            eval_res, common_dates = align_and_evaluate(b_hour_dict, ext_daily)
        except ValueError:
            continue

        results.append({
            "hour": h,
            "matched_days": len(common_dates),
            "returns_count": eval_res["returns_count"],
            "corr": eval_res["returns_corr"],
            "te_annual": eval_res["tracking_error_annual"],
            "basis_stats": eval_res["basis_stats"],
        })

    # Sắp xếp theo tương quan giảm dần
    results.sort(key=lambda x: x["corr"], reverse=True)
    return results


def print_hourly_tracking_tables(dsn: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """Chạy toàn bộ 3 cặp và in bảng 24 dòng cho mỗi cặp theo yêu cầu Brief 117 B1."""
    resolved_dsn = resolve_dsn(dsn)
    all_pair_results: dict[str, list[dict[str, Any]]] = {}

    with psycopg.connect(resolved_dsn) as conn:
        for cfg in PAIRS_CONFIG:
            pair_name = cfg["pair_name"]
            bingx_sym = cfg["bingx_symbol"]
            ext_src = cfg["ext_source"]
            ext_sym = cfg["ext_symbol"]

            rows = scan_hourly_tracking_for_pair(conn, bingx_sym, ext_src, ext_sym)
            all_pair_results[pair_name] = rows

            print("\n" + "=" * 105)
            print(f"BẢNG ĐỘ BÁM 24 GIỜ UTC: {pair_name} ({bingx_sym} vs {ext_src}/{ext_sym})")
            print("=" * 105)
            headers = [
                "Giờ UTC", "Số ngày khớp", "Số điểm lợi suất", "Tương quan",
                "Tracking Error năm", "Basis trung vị", "Basis P5 - P95", "Max |Basis|",
            ]
            fmt = "{:>7} | {:>13} | {:>17} | {:>10} | {:>18} | {:>14} | {:>22} | {:>11}"
            print(fmt.format(*headers))
            print("-" * 105)

            for r in rows:
                b_stats = r["basis_stats"]
                med_str = f"{b_stats['median_basis']*100:+.4f}%"
                p5_p95_str = f"{b_stats['p5_basis']*100:+.4f}% .. {b_stats['p95_basis']*100:+.4f}%"
                max_str = f"{b_stats['max_abs_basis']*100:.4f}%"
                print(fmt.format(
                    f"{r['hour']:02d}:00",
                    str(r["matched_days"]),
                    str(r["returns_count"]),
                    f"{r['corr']:.4f}",
                    f"{r['te_annual']*100:.2f}%",
                    med_str,
                    p5_p95_str,
                    max_str,
                ))
            print("-" * 105)
            best = rows[0]
            print(
                f"-> GIỜ TỐT NHẤT: {best['hour']:02d}:00 UTC | "
                f"Tương quan = {best['corr']:.4f} | "
                f"TE = {best['te_annual']*100:.2f}% | "
                f"n = {best['returns_count']} điểm lợi suất"
            )

    return all_pair_results


def main() -> None:
    ap = argparse.ArgumentParser(description="Đo độ bám theo 24 mốc giờ UTC (Brief 117)")
    ap.add_argument("--dsn", default=None, help="Postgres DSN")
    args = ap.parse_args()

    print_hourly_tracking_tables(args.dsn)


if __name__ == "__main__":
    main()
