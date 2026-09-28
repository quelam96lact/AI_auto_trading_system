"""Kiểm tra độ bám của giá perpetual BingX so với tài sản gốc ngoại sinh (Brief đợt 115).

Chỉ đọc bars_ext_daily và bars_crypto.
Không commit, không push, không đặt lệnh.
Không đọc dữ liệu từ 2026-09-01.
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
from datetime import date, datetime, timedelta
from typing import Any

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SEALED_MAX_DATE = date(2026, 8, 31)

# Danh sách tài sản đối chiếu theo Brief 115
TARGET_ASSETS = [
    {
        "asset_name": "Vàng (XAU/USD spot)",
        "bingx_symbol": "NCCOGOLD2USD-USDT",
        "ext_source": None,
        "ext_symbol": None,
        "note": "Bỏ vì không có nguồn mở đạt yêu cầu điều khoản (LBMA/IBA độc quyền thương mại)",
    },
    {
        "asset_name": "S&P 500",
        "bingx_symbol": "NCSISP5002USD-USDT",
        "ext_source": None,
        "ext_symbol": None,
        "note": "Bỏ vì không có nguồn mở đạt yêu cầu điều khoản (S&P Dow Jones Indices LLC cấm tái phân phối)",
    },
    {
        "asset_name": "NASDAQ 100",
        "bingx_symbol": "NCSINASDAQ1002USD-USDT",
        "ext_source": None,
        "ext_symbol": None,
        "note": "Bỏ vì không có nguồn mở đạt yêu cầu điều khoản (Nasdaq Inc. cấm scraping và tái phân phối)",
    },
    {
        "asset_name": "EUR/USD",
        "bingx_symbol": "NCFXEUR2USD-USDT",
        "ext_source": "FRB_H10",
        "ext_symbol": "EURUSD",
        "note": "Federal Reserve Board H.10 (Public domain)",
    },
    {
        "asset_name": "EUR/USD (ECB)",
        "bingx_symbol": "NCFXEUR2USD-USDT",
        "ext_source": "ECB",
        "ext_symbol": "EURUSD",
        "note": "European Central Bank Data Portal (Tái sử dụng tự do kèm trích dẫn nguồn)",
    },
    {
        "asset_name": "USD/JPY",
        "bingx_symbol": "NCFXUSD2JPY-USDT",
        "ext_source": "FRB_H10",
        "ext_symbol": "USDJPY",
        "note": "Federal Reserve Board H.10 (Public domain)",
    },
]


# ---------------------------------------------------------------------------
# 1. Các hàm thuần toán học & thống kê có Unit Test
# ---------------------------------------------------------------------------

def compute_basis_stats(bingx_prices: list[float], ext_prices: list[float]) -> dict[str, float]:
    """Tính các thông số phân phối của basis_t = (close_bingx / close_ext) - 1.

    Trả về:
    - median_basis: Trung vị basis
    - p5_basis: Phân vị 5% (P5)
    - p95_basis: Phân vị 95% (P95)
    - max_abs_basis: Độ lệch trị tuyệt đối cực đại
    - count_basis_gt_1pct: Số ngày có |basis| > 1% (0.01)
    - pct_basis_gt_1pct: Tỷ lệ % số ngày có |basis| > 1%
    """
    if not bingx_prices or not ext_prices:
        raise ValueError("Không đo được basis: danh sách giá rỗng")
    if len(bingx_prices) != len(ext_prices):
        raise ValueError(
            f"Không đo được basis: độ dài hai chuỗi giá không khớp ({len(bingx_prices)} != {len(ext_prices)})"
        )
    for i, (b, e) in enumerate(zip(bingx_prices, ext_prices, strict=True)):
        if b <= 0 or e <= 0:
            raise ValueError(
                f"Không đo được basis: phát hiện giá <= 0 tại mốc {i} (bingx={b}, ext={e})"
            )

    basis_list = [(b / e - 1.0) for b, e in zip(bingx_prices, ext_prices, strict=True)]
    sorted_basis = sorted(basis_list)
    n = len(sorted_basis)

    # Tính P5 và P95 theo quy ước percentile thông dụng
    def get_percentile(data: list[float], p: float) -> float:
        if len(data) == 1:
            return data[0]
        k = (len(data) - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return data[int(k)]
        return data[f] * (c - k) + data[c] * (k - f)

    p5 = get_percentile(sorted_basis, 0.05)
    p95 = get_percentile(sorted_basis, 0.95)
    median_val = statistics.median(sorted_basis)
    max_abs = max(abs(x) for x in sorted_basis)
    count_gt_1 = sum(1 for x in sorted_basis if round(abs(x), 6) > 0.01)
    pct_gt_1 = (count_gt_1 / n) * 100.0

    return {
        "median_basis": median_val,
        "p5_basis": p5,
        "p95_basis": p95,
        "max_abs_basis": max_abs,
        "count_basis_gt_1pct": count_gt_1,
        "pct_basis_gt_1pct": pct_gt_1,
    }


def compute_daily_returns(prices: list[float]) -> list[float]:
    """Tính chuỗi lợi suất ngày r_t = (P_t / P_{t-1}) - 1."""
    if len(prices) < 2:
        raise ValueError(
            f"Không đo được lợi suất ngày: chuỗi giá cần ít nhất 2 điểm, nhận được {len(prices)}"
        )
    returns: list[float] = []
    for i in range(1, len(prices)):
        prev = prices[i - 1]
        curr = prices[i]
        if prev <= 0 or curr <= 0:
            raise ValueError(
                f"Không đo được lợi suất ngày: phát hiện giá <= 0 tại mốc {i-1} ({prev}) hoặc {i} ({curr})"
            )
        returns.append((curr / prev) - 1.0)
    return returns


def compute_pearson_correlation(x: list[float], y: list[float]) -> float:
    """Tính hệ số tương quan Pearson giữa hai chuỗi số cùng độ dài."""
    n = len(x)
    if n < 2:
        raise ValueError(
            f"Không đo được tương quan: chuỗi cần ít nhất 2 điểm, nhận được {n}"
        )
    if n != len(y):
        raise ValueError(
            f"Không đo được tương quan: hai chuỗi không cùng độ dài ({n} != {len(y)})"
        )

    mean_x = statistics.mean(x)
    mean_y = statistics.mean(y)

    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y, strict=True))
    var_x = sum((a - mean_x) ** 2 for a in x)
    var_y = sum((b - mean_y) ** 2 for b in y)

    denom = math.sqrt(var_x * var_y)
    if denom == 0:
        raise ValueError("Không đo được tương quan: phương sai bằng 0 (chuỗi giá trị không biến thiên)")
    return cov / denom


def compute_tracking_error_annualized(
    r_bingx: list[float],
    r_ext: list[float],
    annual_factor: float = 252.0,
) -> float:
    """Tính sai số bám sát (Tracking Error) năm hóa.

    TE = stdev(r_bingx - r_ext) * sqrt(annual_factor).
    """
    if len(r_bingx) < 2:
        raise ValueError(
            f"Không đo được tracking error: chuỗi cần ít nhất 2 điểm, nhận được {len(r_bingx)}"
        )
    if len(r_bingx) != len(r_ext):
        raise ValueError(
            f"Không đo được tracking error: hai chuỗi không cùng độ dài ({len(r_bingx)} != {len(r_ext)})"
        )

    diffs = [b - e for b, e in zip(r_bingx, r_ext, strict=True)]
    sample_stdev = statistics.stdev(diffs)
    return sample_stdev * math.sqrt(annual_factor)


def align_series_and_evaluate(
    bingx_by_date: dict[date, float],
    ext_by_date: dict[date, float],
    shift_days: int = 0,
) -> dict[str, Any]:
    """Ghép hai chuỗi giá theo ngày với độ lệch shift_days (ext_date = bingx_date + shift_days).

    Tính các chỉ số tracking trên tập các ngày giao nhau.
    """
    matched_dates: list[date] = []
    bingx_prices: list[float] = []
    ext_prices: list[float] = []

    sorted_bingx_dates = sorted(bingx_by_date.keys())
    for b_date in sorted_bingx_dates:
        target_ext_date = b_date + timedelta(days=shift_days)
        if target_ext_date in ext_by_date:
            matched_dates.append(b_date)
            bingx_prices.append(bingx_by_date[b_date])
            ext_prices.append(ext_by_date[target_ext_date])

    if len(matched_dates) < 2:
        # KHONG tra 0.0. Con 0.0 o day doc la "khong tuong quan" va "bam hoan hao",
        # trong khi that ra la "khong do duoc". Do la dung lop loi ma B0 (do 117) da
        # bo o bon ham thuan, nhung no con sot lai o chinh lop goi nay.
        return {
            "shift_days": shift_days,
            "matched_count": len(matched_dates),
            "measurable": False,
            "basis_stats": None,
            "returns_corr": None,
            "tracking_error_annual": None,
        }

    basis_stats = compute_basis_stats(bingx_prices, ext_prices)
    r_bingx = compute_daily_returns(bingx_prices)
    r_ext = compute_daily_returns(ext_prices)
    returns_corr = compute_pearson_correlation(r_bingx, r_ext)
    te_annual = compute_tracking_error_annualized(r_bingx, r_ext)

    return {
        "shift_days": shift_days,
        "matched_count": len(matched_dates),
        "measurable": True,
        "basis_stats": basis_stats,
        "returns_corr": returns_corr,
        "tracking_error_annual": te_annual,
    }


def compare_date_alignments(
    bingx_by_date: dict[date, float],
    ext_by_date: dict[date, float],
) -> dict[str, Any]:
    """So sánh các phương án căn ngày (cùng ngày shift=0, lệch 1 ngày shift=+1 hoặc shift=-1).

    Báo cáo cách căn ngày nào cho hệ số tương quan lợi suất cao hơn.
    """
    res_0 = align_series_and_evaluate(bingx_by_date, ext_by_date, shift_days=0)
    res_p1 = align_series_and_evaluate(bingx_by_date, ext_by_date, shift_days=1)
    res_m1 = align_series_and_evaluate(bingx_by_date, ext_by_date, shift_days=-1)

    evaluations = [res_0, res_p1, res_m1]
    measurable = [e for e in evaluations if e["measurable"]]
    if not measurable:
        raise ValueError(
            "Không chọn được cách căn ngày: cả ba shift (0, +1, -1) đều dưới 2 ngày chung"
        )
    # Sắp xếp theo tương quan lợi suất giảm dần, chỉ trong số shift đo được
    measurable.sort(key=lambda x: x["returns_corr"], reverse=True)
    best = measurable[0]

    return {
        "shift_0_corr": res_0["returns_corr"],
        "shift_0_te": res_0["tracking_error_annual"],
        "shift_0_matched": res_0["matched_count"],
        "shift_0_basis": res_0["basis_stats"],
        "best_shift": best["shift_days"],
        "best_corr": best["returns_corr"],
        "best_te": best["tracking_error_annual"],
        "best_matched": best["matched_count"],
        "best_basis": best["basis_stats"],
        "eval_0": res_0,
        "eval_p1": res_p1,
        "eval_m1": res_m1,
    }


# ---------------------------------------------------------------------------
# 2. Đọc DB và Phân tích tổng thể
# ---------------------------------------------------------------------------

def load_bingx_daily_from_db(conn: psycopg.Connection, symbol: str) -> dict[date, float]:
    """Đọc nến 1d của BingX từ bảng bars_crypto, giới hạn <= 2026-08-31."""
    sql = """
        SELECT ts, close
        FROM bars_crypto
        WHERE symbol = %s AND interval = '1d' AND ts <= '2026-08-31 23:59:59+00'
        ORDER BY ts ASC;
    """
    result: dict[date, float] = {}
    with conn.cursor() as cur:
        cur.execute(sql, (symbol,))
        for row in cur.fetchall():
            ts_val = row[0]
            close_val = float(row[1])
            d = ts_val.date() if isinstance(ts_val, datetime) else ts_val
            result[d] = close_val
    return result


def load_ext_daily_from_db(
    conn: psycopg.Connection,
    source: str,
    symbol: str,
) -> dict[date, float]:
    """Đọc nến từ bảng bars_ext_daily, giới hạn <= 2026-08-31."""
    sql = """
        SELECT date, close
        FROM bars_ext_daily
        WHERE source = %s AND symbol = %s AND date <= %s
        ORDER BY date ASC;
    """
    result: dict[date, float] = {}
    with conn.cursor() as cur:
        cur.execute(sql, (source, symbol, SEALED_MAX_DATE))
        for row in cur.fetchall():
            d = row[0]
            close_val = float(row[1])
            result[d] = close_val
    return result


def run_tracking_analysis(dsn: str | None = None) -> list[dict[str, Any]]:
    """Phân tích độ bám của BingX so với tài sản gốc cho tất cả các tài sản ở §1."""
    resolved_dsn = resolve_dsn(dsn)

    reports: list[dict[str, Any]] = []

    with psycopg.connect(resolved_dsn) as conn:
        for item in TARGET_ASSETS:
            asset_name = item["asset_name"]
            bingx_sym = item["bingx_symbol"]
            ext_src = item["ext_source"]
            ext_sym = item["ext_symbol"]
            note = item["note"]

            if ext_src is None or ext_sym is None:
                # Tài sản không có nguồn đạt chuẩn (đã bị loại bỏ theo §2)
                reports.append({
                    "asset_name": asset_name,
                    "bingx_symbol": bingx_sym,
                    "source_desc": "Không có nguồn đạt chuẩn",
                    "start_year": "N/A",
                    "total_ext_days": 0,
                    "matched_days": 0,
                    "basis_median_str": "N/A",
                    "corr_str": "N/A",
                    "te_str": "N/A",
                    "best_alignment_str": "N/A",
                    "eligible": False,
                    "reason": note,
                })
                continue

            # Tải dữ liệu từ DB
            bingx_data = load_bingx_daily_from_db(conn, bingx_sym)
            ext_data = load_ext_daily_from_db(conn, ext_src, ext_sym)

            ext_years = 0
            start_year = "N/A"
            if ext_data:
                sorted_dates = sorted(ext_data.keys())
                start_year = str(sorted_dates[0].year)
                ext_span_days = (sorted_dates[-1] - sorted_dates[0]).days
                ext_years = ext_span_days / 365.25

            # Kiểm tra số nến BingX
            if not bingx_data:
                reports.append({
                    "asset_name": asset_name,
                    "bingx_symbol": bingx_sym,
                    "source_desc": f"{ext_src} ({note})",
                    "start_year": start_year,
                    "total_ext_days": len(ext_data),
                    "matched_days": 0,
                    "basis_median_str": "N/A (BingX 0 nến)",
                    "corr_str": "N/A (BingX 0 nến)",
                    "te_str": "N/A (BingX 0 nến)",
                    "best_alignment_str": "Không đo được (BingX tạm dừng)",
                    "eligible": False,
                    "reason": f"Nguồn gốc có {len(ext_data)} ngày ({ext_years:.1f} năm), nhưng BingX có 0 nến 1d do sàn tạm dừng cuối tuần (status=25, lỗi 109415)",
                })
                continue

            # So sánh độ bám nếu cả hai bên cùng có dữ liệu
            align_res = compare_date_alignments(bingx_data, ext_data)
            matched = align_res["best_matched"]
            best_shift = align_res["best_shift"]
            best_corr = align_res["best_corr"]
            best_te = align_res["best_te"]
            best_basis = align_res["best_basis"]

            basis_med = best_basis["median_basis"]
            p5 = best_basis["p5_basis"]
            p95 = best_basis["p95_basis"]

            shift_desc = f"Shift {best_shift:+d}d" if best_shift != 0 else "Cùng ngày (Shift 0)"

            # Tiêu chí: Đủ 10 năm gốc VÀ corr >= 0.95 VÀ |basis| median <= 0.5%
            has_10y = ext_years >= 10.0
            high_corr = best_corr >= 0.95
            tight_basis = abs(basis_med) <= 0.005
            is_eligible = has_10y and high_corr and tight_basis

            reports.append({
                "asset_name": asset_name,
                "bingx_symbol": bingx_sym,
                "source_desc": f"{ext_src} ({note})",
                "start_year": start_year,
                "total_ext_days": len(ext_data),
                "matched_days": matched,
                "basis_median_str": f"{basis_med*100:+.2f}% ({p5*100:+.2f}% đến {p95*100:+.2f}%)",
                "corr_str": f"{best_corr:.4f}",
                "te_str": f"{best_te*100:.2f}%",
                "best_alignment_str": shift_desc,
                "eligible": is_eligible,
                "reason": "Đạt cả 3 tiêu chí" if is_eligible else "Không thỏa mãn đủ cả 3 tiêu chí",
            })

    return reports


def print_tracking_tables(reports: list[dict[str, Any]]) -> None:
    """In bảng chính tổng kết độ bám (§5 Brief 115)."""
    print("\n" + "=" * 120)
    print("BẢNG CHÍNH: TỔNG HỢP KIỂM TRA ĐỘ BÁM CỦA BINGX SO VỚI TÀI SẢN GỐC (BRIEF ĐỢT 115)")
    print("=" * 120)
    headers = [
        "Tài sản", "Nguồn (điều khoản)", "Năm BĐ", "Số ngày", "Basis trung vị (P5–P95)", "Tương quan", "TE năm", "Căn ngày tốt hơn", "Đủ đo tiếp?"
    ]
    fmt = "{:<16} | {:<28} | {:>6} | {:>7} | {:<22} | {:>10} | {:>8} | {:<16} | {:<12}"
    print(fmt.format(*headers))
    print("-" * 120)

    for r in reports:
        elig_str = "ĐỦ ĐO TIẾP" if r["eligible"] else "KHÔNG ĐỦ"
        print(fmt.format(
            r["asset_name"][:16],
            r["source_desc"][:28],
            str(r["start_year"]),
            str(r["total_ext_days"]),
            r["basis_median_str"][:22],
            r["corr_str"],
            r["te_str"],
            r["best_alignment_str"][:16],
            elig_str,
        ))
    print("=" * 120)


def main() -> None:
    ap = argparse.ArgumentParser(description="Kiểm tra độ bám BingX so với tài sản gốc")
    ap.add_argument("--dsn", default=None, help="Postgres DSN")
    args = ap.parse_args()

    reports = run_tracking_analysis(args.dsn)
    print_tracking_tables(reports)


if __name__ == "__main__":
    main()
