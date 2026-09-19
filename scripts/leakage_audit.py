"""Máy dò rò rỉ nhìn trước (look-ahead leakage detector) — Brief đợt 71.

Phép đo cốt lõi (đóng băng):
- rho_truoc: Spearman(feature[T], loi_suat_qua_khu[T])
    trong đó loi_suat_qua_khu[T] = close(T) / close(T - 1h) - 1
    (lợi suất của giờ VỪA KẾT THÚC tại T)
- rho_sau:  Spearman(feature[T], loi_suat_tuong_lai[T])
    trong đó loi_suat_tuong_lai[T] = close(T + 1h) / close(T) - 1
    (lợi suất của giờ SAP BAT DAU tại T = fwd_ret_1h)

Quy tắc gắn cờ (đóng băng):
- NGHI_VAN khi rho_sau > rho_truoc VÀ |rho_sau| vượt ngưỡng hoán vị khối.
    Nghĩa là: đặc trưng "biết" về tương lai nhiều hơn về quá khứ.
- SACH khi không thoả điều kiện trên.

LƯU Ý QUAN TRỌNG: SACH nghĩa là "không thấy dấu hiệu rò rỉ bằng phép này",
KHÔNG nghĩa là "chắc chắn không rò rỉ". Đây là phép sàng, không phải phép chứng minh.

Chốt an toàn (đóng băng):
- Biến đối chứng delta_norm PHẢI cho rho_truoc mạnh dương (kỳ vọng ≈ +0.75).
- Nếu delta_norm cho rho_truoc <= 0 thì phép đo đang hỏng — dừng và báo cáo.
"""

import argparse
import math
import sys
from datetime import UTC, datetime, timedelta

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

try:
    from audit_information import (
        fast_spearman_rank_correlation,
        run_block_permutation_test,
    )
except ImportError:
    from scripts.audit_information import (
        fast_spearman_rank_correlation,
        run_block_permutation_test,
    )

from trading.feature_panel import build_feature_panel
from trading.models import Bar

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ngưỡng tối thiểu cho biến đối chứng delta_norm (chốt an toàn)
CONTROL_MIN_RHO_TRUOC = 0.3

FEATURE_NAMES = [
    "funding_rate",
    "funding_z",
    "oi_chg_3h",
    "oi_chg_24h",
    "long_short_ratio",
    "toptrader_ls_ratio",
    "taker_ls_vol_ratio",
    "delta_norm",
    "cvd_chg_3h",
]

LeakageFlag = str  # "NGHI_VAN" | "SACH"


def compute_leakage_pair(
    feature_vals: list[float | None],
    past_ret_vals: list[float | None],
    future_ret_vals: list[float | None],
) -> tuple[float, float, int, int]:
    """Tính (rho_truoc, rho_sau, n_truoc, n_sau) cho một đặc trưng.

    Parameters:
    - feature_vals:   Danh sách giá trị đặc trưng theo thứ tự thời gian.
    - past_ret_vals:  Lợi suất quá khứ: close(T)/close(T-1h) - 1.
    - future_ret_vals: Lợi suất tương lai: close(T+1h)/close(T) - 1.

    Returns:
    - rho_truoc: Spearman(feature, past_ret) trên các hàng hợp lệ.
    - rho_sau:   Spearman(feature, future_ret) trên các hàng hợp lệ.
    - n_truoc:   Số hàng hợp lệ cho rho_truoc.
    - n_sau:     Số hàng hợp lệ cho rho_sau.
    """
    n = len(feature_vals)

    x_truoc, y_truoc = [], []
    x_sau, y_sau = [], []

    for i in range(n):
        fv = feature_vals[i]
        pv = past_ret_vals[i]
        fwv = future_ret_vals[i]

        if fv is None or math.isnan(fv):
            continue

        if pv is not None and not math.isnan(pv):
            x_truoc.append(fv)
            y_truoc.append(pv)

        if fwv is not None and not math.isnan(fwv):
            x_sau.append(fv)
            y_sau.append(fwv)

    rho_truoc = fast_spearman_rank_correlation(x_truoc, y_truoc) if len(x_truoc) >= 2 else 0.0
    rho_sau = fast_spearman_rank_correlation(x_sau, y_sau) if len(x_sau) >= 2 else 0.0

    return rho_truoc, rho_sau, len(x_truoc), len(x_sau)


def classify_leakage(rho_truoc: float, rho_sau: float, threshold: float) -> LeakageFlag:
    """Gắn cờ rò rỉ dựa trên hai hệ số Spearman và ngưỡng hoán vị khối.

    NGHI_VAN khi: rho_sau > rho_truoc VÀ |rho_sau| > threshold.
    SACH trong mọi trường hợp còn lại.

    LƯU Ý: SACH = "không thấy dấu hiệu rò rỉ bằng phép này",
    KHÔNG phải bảo chứng "chắc chắn sạch".
    """
    if rho_sau > rho_truoc and abs(rho_sau) > threshold:
        return "NGHI_VAN"
    return "SACH"


def add_past_return_to_panel(panel_rows: list[dict]) -> list[dict]:
    """Tính và thêm trường ret_past_1h = close(T)/close(T-1h) - 1 vào mỗi hàng panel.

    Dùng trường 'close' đã có sẵn trong panel và tra cứu theo ts.
    Các hàng không có nến giờ trước sẽ có ret_past_1h = None.
    """
    close_by_ts: dict[datetime, float] = {row["ts"]: row["close"] for row in panel_rows}

    result = []
    for row in panel_rows:
        rc = dict(row)
        ts_prev = row["ts"] - timedelta(hours=1)
        close_prev = close_by_ts.get(ts_prev)
        close_now = row.get("close")
        if close_prev is not None and close_now is not None and close_prev > 0:
            rc["ret_past_1h"] = (close_now / close_prev) - 1.0
        else:
            rc["ret_past_1h"] = None
        result.append(rc)
    return result


def check_control_variable(
    panel_rows: list[dict],
    past_ret_col: str = "ret_past_1h",
    future_ret_col: str = "fwd_ret_1h",
) -> tuple[float, bool]:
    """Kiểm tra chốt an toàn: delta_norm phải cho rho_truoc mạnh dương.

    Returns:
    - rho_truoc_control: Giá trị thực đo được.
    - ok: True nếu rho_truoc > CONTROL_MIN_RHO_TRUOC, False nếu phép đo đang hỏng.
    """
    feat_vals = [row.get("delta_norm") for row in panel_rows]
    past_vals = [row.get(past_ret_col) for row in panel_rows]
    fut_vals = [row.get(future_ret_col) for row in panel_rows]

    rho_truoc, _rho_sau, _n_truoc, _n_sau = compute_leakage_pair(feat_vals, past_vals, fut_vals)
    ok = rho_truoc > CONTROL_MIN_RHO_TRUOC
    return rho_truoc, ok


def run_leakage_audit(
    panel_rows: list[dict],
    feature_names: list[str] = FEATURE_NAMES,
    n_permutations: int = 500,
    seed: int = 42,
    past_ret_col: str = "ret_past_1h",
    future_ret_col: str = "fwd_ret_1h",
) -> list[dict]:
    """Chạy kiểm toán rò rỉ trên toàn bộ danh sách đặc trưng.

    Quy trình:
    1. Kiểm tra chốt an toàn (delta_norm).
    2. Tính ngưỡng hoán vị khối (feature_names × [future_ret_col]).
    3. Với mỗi đặc trưng: tính rho_truoc, rho_sau, gắn cờ.

    Returns:
    - Danh sách dict, mỗi dict chứa:
        {feature, rho_truoc, rho_sau, n_truoc, n_sau, threshold, flag, note}

    Raises:
    - RuntimeError nếu chốt an toàn thất bại.
    """
    # Bước 1: Chốt an toàn
    rho_ctrl, ctrl_ok = check_control_variable(panel_rows, past_ret_col, future_ret_col)
    if not ctrl_ok:
        raise RuntimeError(
            f"CHOT AN TOAN THAT BAI: delta_norm rho_truoc = {rho_ctrl:.4f} "
            f"(can > {CONTROL_MIN_RHO_TRUOC}). "
            "Phep do dang hong — kiem tra lai du lieu truoc khi doc ket qua."
        )

    # Bước 2: Ngưỡng hoán vị khối (dùng target = future_ret_col)
    # Dùng lại run_block_permutation_test từ audit_information với 1 target
    threshold_95, _ = run_block_permutation_test(
        panel_rows,
        n_permutations=n_permutations,
        block_size_hours=48,
        seed=seed,
        feature_names=feature_names,
        target_names=[future_ret_col],
    )

    # Bước 3: Tính từng đặc trưng
    results = []
    for feat in feature_names:
        feat_vals = [row.get(feat) for row in panel_rows]
        past_vals = [row.get(past_ret_col) for row in panel_rows]
        fut_vals = [row.get(future_ret_col) for row in panel_rows]

        rho_truoc, rho_sau, n_truoc, n_sau = compute_leakage_pair(feat_vals, past_vals, fut_vals)
        flag = classify_leakage(rho_truoc, rho_sau, threshold_95)

        note = ""
        if feat == "delta_norm":
            note = f"doi_chung (rho_truoc mong doi > {CONTROL_MIN_RHO_TRUOC:.2f})"

        results.append({
            "feature": feat,
            "rho_truoc": rho_truoc,
            "rho_sau": rho_sau,
            "n_truoc": n_truoc,
            "n_sau": n_sau,
            "threshold": threshold_95,
            "flag": flag,
            "note": note,
        })

    return results


def load_is_data_from_db(
    conn: psycopg.Connection,
    symbol: str = "BTCUSDT",
    is_start: datetime = datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
    is_end: datetime = datetime(2025, 12, 31, 23, 0, tzinfo=UTC),
) -> tuple[list[Bar], list[tuple[datetime, float]], list[dict], list[dict]]:
    """Tải dữ liệu IS từ DB (bao gồm đệm warm-up và fwd return).

    Tập IS: 2024-01-01 → 2025-12-31 UTC. Năm 2026 giữ NIÊM PHONG.
    """
    # Klines: cần thêm 24h sau IS_END để tính fwd_ret_24h, và 1h trước IS_START để tính ret_past_1h
    kline_start = is_start - timedelta(hours=1)
    kline_end = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)

    sql_klines = """
        SELECT ts, open, high, low, close, volume
        FROM binance_klines
        WHERE symbol = %s AND interval = '1h' AND ts >= %s AND ts <= %s
        ORDER BY ts;
    """
    with conn.cursor() as cur:
        cur.execute(sql_klines, (symbol, kline_start, kline_end))
        k_rows = cur.fetchall()

    klines = [
        Bar(
            symbol=symbol,
            ts=r[0],
            open=float(r[1]),
            high=float(r[2]),
            low=float(r[3]),
            close=float(r[4]),
            volume=float(r[5]),
        )
        for r in k_rows
    ]

    # Funding
    sql_funding = """
        SELECT funding_time, funding_rate
        FROM binance_funding
        WHERE symbol = %s AND funding_time <= %s
        ORDER BY funding_time;
    """
    with conn.cursor() as cur:
        cur.execute(sql_funding, (symbol, kline_end))
        f_rows = cur.fetchall()
    funding = [(r[0], float(r[1])) for r in f_rows]

    # Metrics
    sql_metrics = """
        SELECT ts, sum_open_interest, sum_open_interest_value,
               count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
               count_long_short_ratio, sum_taker_long_short_vol_ratio
        FROM binance_metrics
        WHERE symbol = %s AND ts >= %s AND ts <= %s
        ORDER BY ts;
    """
    with conn.cursor() as cur:
        cur.execute(sql_metrics, (symbol, is_start, kline_end))
        m_rows = cur.fetchall()
    metrics = [
        {
            "ts": r[0],
            "sum_open_interest": float(r[1]) if r[1] is not None else None,
            "sum_open_interest_value": float(r[2]) if r[2] is not None else None,
            "count_toptrader_long_short_ratio": float(r[3]) if r[3] is not None else None,
            "sum_toptrader_long_short_ratio": float(r[4]) if r[4] is not None else None,
            "count_long_short_ratio": float(r[5]) if r[5] is not None else None,
            "sum_taker_long_short_vol_ratio": float(r[6]) if r[6] is not None else None,
        }
        for r in m_rows
    ]

    # Orderflow
    sql_of = """
        SELECT ts, taker_buy_volume, taker_sell_volume, delta, buy_ratio, trade_count
        FROM binance_orderflow_1h
        WHERE symbol = %s AND ts >= %s AND ts <= %s
        ORDER BY ts;
    """
    with conn.cursor() as cur:
        cur.execute(sql_of, (symbol, is_start, kline_end))
        of_rows = cur.fetchall()
    orderflow = [
        {
            "ts": r[0],
            "taker_buy_volume": float(r[1]),
            "taker_sell_volume": float(r[2]),
            "delta": float(r[3]),
            "buy_ratio": float(r[4]),
            "trade_count": int(r[5]),
        }
        for r in of_rows
    ]

    return klines, funding, metrics, orderflow


def print_results_table(results: list[dict], label: str = "") -> None:
    """In bảng kết quả kiểm toán rò rỉ."""
    if label:
        print(f"\n{'=' * 80}")
        print(f"  {label}")
        print(f"{'=' * 80}")
    print(
        f"{'Dac trung':<22} | {'rho_truoc':>10} | {'rho_sau':>10} "
        f"| {'Nguong HV':>10} | {'Co':<10} | Ghi chu"
    )
    print("-" * 90)
    for r in results:
        flag_display = "*** NGHI_VAN ***" if r["flag"] == "NGHI_VAN" else "SACH"
        print(
            f"{r['feature']:<22} | {r['rho_truoc']:>+10.4f} | {r['rho_sau']:>+10.4f} "
            f"| {r['threshold']:>10.4f} | {flag_display:<16} | {r['note']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="May do ro ri nhin truoc — Brief dot 71."
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--is-start", default="2024-01-01")
    parser.add_argument("--is-end", default="2025-12-31")
    parser.add_argument(
        "--permutations",
        type=int,
        default=500,
        help="So lan hoan vi khoi (mac dinh 500 cho nhanh; dung 1000 cho chinh xac cao nhat)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--compare-lag",
        action="store_true",
        help="Chay ca metric_lag_minutes=5 (mac dinh) va metric_lag_minutes=0 (khong lag) de doi chieu",
    )
    parser.add_argument("--dsn", default=None, help="Database DSN override")
    args = parser.parse_args()

    conn = psycopg.connect(resolve_dsn(args.dsn))
    is_start_dt = datetime.fromisoformat(args.is_start).replace(tzinfo=UTC)
    is_end_dt = datetime.fromisoformat(args.is_end).replace(hour=23, minute=0, second=0, tzinfo=UTC)

    print(f"=== MAY DO RO RI NHIN TRUOC (Brief dot 71) — {args.symbol} ===")
    print(f"Khoang In-Sample (IS): {is_start_dt} -> {is_end_dt} UTC (Nam 2026 NIEM PHONG)")

    klines, funding, metrics, orderflow = load_is_data_from_db(
        conn, symbol=args.symbol, is_start=is_start_dt, is_end=is_end_dt
    )
    conn.close()
    print(
        f"Du lieu tai: {len(klines)} nen, {len(funding)} lan funding, "
        f"{len(metrics)} metrics, {len(orderflow)} orderflow."
    )

    def build_and_audit(metric_lag: int, label: str) -> list[dict]:
        raw_panel = build_feature_panel(
            klines, funding, metrics, orderflow, metric_lag_minutes=metric_lag
        )
        is_panel = [r for r in raw_panel if is_start_dt <= r["ts"] <= is_end_dt]
        is_panel = add_past_return_to_panel(is_panel)
        print(f"\n[{label}] Dung panel IS: {len(is_panel)} hang.")

        # Kiểm tra chốt an toàn trước
        rho_ctrl, ctrl_ok = check_control_variable(is_panel)
        print(f"[{label}] Chot an toan delta_norm: rho_truoc = {rho_ctrl:+.4f}", end="")
        if ctrl_ok:
            print(f" — DAT (> {CONTROL_MIN_RHO_TRUOC})")
        else:
            print(f" — HONG! Can > {CONTROL_MIN_RHO_TRUOC}, dung lai.")
            raise RuntimeError(
                f"Chot an toan that bai voi lag={metric_lag}m: rho_truoc delta_norm = {rho_ctrl:.4f}"
            )

        results = run_leakage_audit(
            is_panel,
            n_permutations=args.permutations,
            seed=args.seed,
        )
        print_results_table(results, label=label)
        return results

    results_lag5 = build_and_audit(metric_lag=5, label="metric_lag_minutes=5 (mac dinh)")

    if args.compare_lag:
        results_lag0 = build_and_audit(metric_lag=0, label="metric_lag_minutes=0 (khong lag — gio ro ri)")

        # In bảng đối chiếu
        print(f"\n{'=' * 80}")
        print("  BANG DOI CHIEU: metric_lag=5 vs metric_lag=0")
        print(f"{'=' * 80}")
        print(
            f"{'Dac trung':<22} | {'Co (lag=5)':>12} | {'Co (lag=0)':>12} | {'Thay doi?'}"
        )
        print("-" * 70)
        r0_by_feat = {r["feature"]: r for r in results_lag0}
        for r5 in results_lag5:
            r0 = r0_by_feat.get(r5["feature"], {})
            flag5 = r5["flag"]
            flag0 = r0.get("flag", "N/A")
            changed = "CO THAY DOI" if flag5 != flag0 else ""
            print(f"{r5['feature']:<22} | {flag5:>12} | {flag0:>12} | {changed}")


if __name__ == "__main__":
    main()
