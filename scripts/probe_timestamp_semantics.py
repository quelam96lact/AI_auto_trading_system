"""Phép đo hướng ngữ nghĩa timestamp của các cột dữ liệu phi giá (Brief đợt 42 Task 1).

Mục tiêu:
Xác định một chuỗi giá trị gán nhãn thời gian T mô tả khoảng TRƯỚC hay SAU T.
- r_truoc(T) = lợi suất nến 1h KẾT THÚC tại T = (close - open) / open của nến [T-1h, T)
- r_sau(T)   = lợi suất nến 1h BẮT ĐẦU tại T  = (close - open) / open của nến [T, T+1h)

Chỉ xét các mốc T rơi đúng đầu giờ (phút = 0).
Loại bỏ các dòng có sum_open_interest = 0 trước khi tính.

Phân loại:
- bat_doi_xung = |corr_sau| - |corr_truoc|
- NHIN_VE_TUONG_LAI  khi bat_doi_xung >  0.03
- NHIN_VE_QUA_KHU    khi bat_doi_xung < -0.03
- BIEN_MUC           khi |bat_doi_xung| <= 0.03

Mốc hiệu chuẩn đối chứng: delta của ta (lấy delta của nến vừa đóng tại T [T-1h, T)).
Phải ra NHIN_VE_QUA_KHU với corr_truoc ≈ +0.75.
"""

import argparse
import sys
from datetime import datetime, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn


def pearson_correlation(x: list[float], y: list[float]) -> float:
    """Tính tương quan Pearson giữa 2 chuỗi float cùng độ dài."""
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


def run_probe(conn: psycopg.Connection, symbol: str = "BTCUSDT") -> list[dict]:
    """Chạy phép đo hướng trên 6 cột theo §1.3."""
    # 1. Lấy nến 1h: ts là thời điểm mở nến [ts, ts+1h)
    # Lợi suất của nến [ts, ts+1h) = (close - open) / open
    sql_klines = """
        SELECT ts, open, close
        FROM binance_klines
        WHERE symbol = %s AND interval = '1h'
        ORDER BY ts;
    """
    with conn.cursor() as cur:
        cur.execute(sql_klines, (symbol,))
        k_rows = cur.fetchall()

    # ret_bar[ts] là lợi suất của nến bắt đầu tại ts
    ret_by_ts: dict[datetime, float] = {}
    for r in k_rows:
        ts = r[0]
        o, c = float(r[1]), float(r[2])
        if o > 0:
            ret_by_ts[ts] = (c - o) / o

    # 2. Lấy orderflow 1h: nến [ts, ts+1h) có delta.
    # Tại mốc đầu giờ T: delta vừa kết thúc tại T là delta của nến ts = T - 1h.
    sql_of = """
        SELECT ts, delta
        FROM binance_orderflow_1h
        WHERE symbol = %s
        ORDER BY ts;
    """
    with conn.cursor() as cur:
        cur.execute(sql_of, (symbol,))
        of_rows = cur.fetchall()

    # of_delta_ended_at[T] = delta của nến [T-1h, T)
    of_delta_ended_at: dict[datetime, float] = {
        r[0] + timedelta(hours=1): float(r[1])
        for r in of_rows
    }

    # 3. Lấy metrics: chỉ lấy các mốc đúng đầu giờ (phút = 0), loại sum_open_interest = 0
    sql_metrics = """
        SELECT ts, sum_open_interest, count_long_short_ratio,
               count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
               sum_taker_long_short_vol_ratio
        FROM binance_metrics
        WHERE symbol = %s
          AND EXTRACT(MINUTE FROM ts) = 0
          AND sum_open_interest > 0
          AND sum_open_interest_value > 0
        ORDER BY ts;
    """
    with conn.cursor() as cur:
        cur.execute(sql_metrics, (symbol,))
        m_rows = cur.fetchall()

    metrics_by_ts: dict[datetime, dict] = {}
    for r in m_rows:
        metrics_by_ts[r[0]] = {
            "sum_open_interest": float(r[1]) if r[1] is not None else None,
            "count_long_short_ratio": float(r[2]) if r[2] is not None else None,
            "count_toptrader_long_short_ratio": float(r[3]) if r[3] is not None else None,
            "sum_toptrader_long_short_ratio": float(r[4]) if r[4] is not None else None,
            "sum_taker_long_short_vol_ratio": float(r[5]) if r[5] is not None else None,
        }

    # 4. Danh sách các cột cần đo
    # Cột 1: delta (đối chứng, delta đã chốt tại T)
    # Cột 2-6: các cột từ metrics tại T
    columns_to_test = [
        "delta (của ta, đối chứng)",
        "sum_open_interest",
        "count_long_short_ratio",
        "count_toptrader_long_short_ratio",
        "sum_toptrader_long_short_ratio",
        "sum_taker_long_short_vol_ratio",
    ]

    results = []

    for col in columns_to_test:
        x_vals = []
        r_truoc_vals = []
        r_sau_vals = []

        if col == "delta (của ta, đối chứng)":
            # Duyệt các mốc T trong of_delta_ended_at
            for T, val in of_delta_ended_at.items():
                r_truoc = ret_by_ts.get(T - timedelta(hours=1))  # nến [T-1h, T)
                r_sau = ret_by_ts.get(T)                         # nến [T, T+1h)
                if r_truoc is not None and r_sau is not None and val is not None:
                    x_vals.append(val)
                    r_truoc_vals.append(r_truoc)
                    r_sau_vals.append(r_sau)
        else:
            # Duyệt các mốc T trong metrics_by_ts
            for T, m_dict in metrics_by_ts.items():
                val = m_dict.get(col)
                r_truoc = ret_by_ts.get(T - timedelta(hours=1))  # nến [T-1h, T)
                r_sau = ret_by_ts.get(T)                         # nến [T, T+1h)
                if r_truoc is not None and r_sau is not None and val is not None:
                    x_vals.append(val)
                    r_truoc_vals.append(r_truoc)
                    r_sau_vals.append(r_sau)

        n = len(x_vals)
        if n < 10:
            corr_truoc = 0.0
            corr_sau = 0.0
        else:
            corr_truoc = pearson_correlation(x_vals, r_truoc_vals)
            corr_sau = pearson_correlation(x_vals, r_sau_vals)

        bat_doi_xung = abs(corr_sau) - abs(corr_truoc)

        if bat_doi_xung > 0.03:
            label = "NHIN_VE_TUONG_LAI"
        elif bat_doi_xung < -0.03:
            label = "NHIN_VE_QUA_KHU"
        else:
            label = "BIEN_MUC"

        results.append({
            "column": col,
            "n": n,
            "corr_truoc": corr_truoc,
            "corr_sau": corr_sau,
            "bat_doi_xung": bat_doi_xung,
            "label": label,
        })

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Đo hướng ngữ nghĩa timestamp của các cột dữ liệu phi giá.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--dsn", default=None, help="Database DSN override")

    args = parser.parse_args()

    conn = psycopg.connect(resolve_dsn(args.dsn))
    results = run_probe(conn, symbol=args.symbol)
    conn.close()

    print("=== KẾT QUẢ PHÉP ĐO HƯỚNG NGỮ NGHĨA TIMESTAMP (TASK 1) ===")
    print(f"{'Cột':<35} | {'N':<6} | {'corr_truoc':<12} | {'corr_sau':<12} | {'Bất đối xứng':<14} | {'Phân loại':<18}")
    print("-" * 105)

    for r in results:
        print(
            f"{r['column']:<35} | {r['n']:<6} | {r['corr_truoc']:+.4f}      | "
            f"{r['corr_sau']:+.4f}    | {r['bat_doi_xung']:+.4f}         | {r['label']:<18}"
        )


if __name__ == "__main__":
    main()
