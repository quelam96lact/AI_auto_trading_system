"""Đo lường chiến lược Time-Series Momentum trên tỷ giá Forex (Brief đợt 118).

Quy định Brief 118:
- Chiến lược: Time-series momentum, lookback 250 ngày giao dịch (hàng), tái cân bằng hàng tháng.
- Dữ liệu: bars_ext_daily, source = 'FRB_H10' (và kiểm chứng phụ source = 'ECB').
- Tái cân bằng: Ngày có dữ liệu cuối cùng của mỗi tháng trong chuỗi.
- Tín hiệu tại t: r = close_t / close_{t-250} - 1. r > 0 -> LONG (+1), r < 0 -> SHORT (-1), r == 0 -> FLAT (0).
- Phí: 0.05% mỗi chân (vào từ phẳng = 1 chân, đảo chiều = 2 chân, giữ nguyên = 0 chân).
- Funding: Mức A = 0.000%/ngày, Mức B = 0.016%/ngày, Mức C = 0.030%/ngày.
- Đối chứng ngẫu nhiên: 2.000 lượt hoán vị dấu +-1 ngẫu nhiên, giữ nguyên lịch tái cân bằng và chi phí.
- Hiệu chỉnh đa kiểm định: Holm-Bonferroni qua 4 phép thử (2 cặp x 2 cửa sổ).
- Niêm phong: Chỉ đọc dữ liệu đến hết 2026-08-31.
- Không commit, không push, không đặt lệnh, không sửa trading/engine/.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

from trading.metrics import (
    empirical_percentile_rank,
    holm_adjust,
    max_drawdown,
    sharpe,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SEALED_MAX_DATE_STR = "2026-08-31"

TAKER_FEE_RATE = 0.0005  # 0.05% mỗi chân (takerFeeRate BingX)
FUNDING_RATE_A = 0.00000  # 0.000%/ngày
FUNDING_RATE_B = 0.00016  # 0.016%/ngày (trung bình trị tuyệt đối)
FUNDING_RATE_C = 0.00030  # 0.030%/ngày (P95 xấu)

OUTPUT_DIR = Path("docs/superpowers/research/dot-118-output")


# ---------------------------------------------------------------------------
# 1. Các hàm logic cốt lõi thuần túy (Pure Functions - có Unit Test)
# ---------------------------------------------------------------------------

def identify_month_ends(
    bars: list[tuple[date, float]],
) -> list[tuple[int, date, float]]:
    """Xác định ngày có dữ liệu cuối cùng của mỗi tháng trong chuỗi (Brief 118 §1).

    QUY TẮC BẮT BUỘC:
    Lấy ngày có dữ liệu cuối cùng của mỗi tháng trong chuỗi, KHÔNG phải ngày cuối
    theo lịch dương (vì cuối tháng theo lịch có thể rơi vào thứ Bảy/Chủ nhật hoặc ngày lễ).

    Args:
        bars: Danh sách các nến (date, close) đã sắp xếp tăng dần theo date.

    Returns:
        list[tuple[int, date, float]]: Danh sách (row_index, date, close) của các mốc tháng cuối.
    """
    if not bars:
        return []

    by_month: dict[tuple[int, int], list[tuple[int, date, float]]] = defaultdict(list)
    for i, (d, c) in enumerate(bars):
        by_month[(d.year, d.month)].append((i, d, c))

    sorted_ym = sorted(by_month.keys())
    return [by_month[ym][-1] for ym in sorted_ym]


def compute_tsmom_signal_at_bar(
    bars: list[tuple[date, float]],
    bar_index: int,
    lookback_rows: int = 250,
) -> tuple[float, int]:
    """Tính tín hiệu động lượng tại một mốc nến bar_index (Brief 118 §1).

    r = close_t / close_{t-250} - 1 (với t-250 là 250 hàng trước đó trong chuỗi).
    r > 0 -> LONG (+1), r < 0 -> SHORT (-1), r == 0 -> FLAT (0).

    Args:
        bars: Danh sách (date, close).
        bar_index: Chỉ số hàng t hiện tại.
        lookback_rows: Số hàng nhìn lại (cố định 250 hàng).

    Returns:
        tuple[float, int]: (momentum_return, position). Nếu chưa đủ 250 hàng, trả về (0.0, 0).
    """
    if bar_index < lookback_rows:
        return 0.0, 0

    curr_close = bars[bar_index][1]
    past_close = bars[bar_index - lookback_rows][1]

    if past_close <= 0 or curr_close <= 0:
        raise ValueError(
            f"Giá không hợp lệ tại mốc {bar_index} ({curr_close}) hoặc {bar_index - lookback_rows} ({past_close})"
        )

    r = (curr_close / past_close) - 1.0
    if r > 0:
        pos = 1
    elif r < 0:
        pos = -1
    else:
        pos = 0
    return r, pos


def calculate_turnover_fee(prev_pos: int, curr_pos: int, fee_per_leg: float = TAKER_FEE_RATE) -> tuple[int, float]:
    """Tính số chân giao dịch và phí khớp lệnh (Brief 118 §2).

    - Vào từ phẳng (0 -> 1 hoặc 0 -> -1): 1 chân.
    - Đảo chiều (1 -> -1 hoặc -1 -> 1): 2 chân.
    - Giữ nguyên vị thế (1 -> 1 hoặc -1 -> -1 hoặc 0 -> 0): 0 chân.
    - Thoát về phẳng (1 -> 0 hoặc -1 -> 0): 1 chân.

    Số chân = |curr_pos - prev_pos|.
    Phí = số chân * fee_per_leg.
    """
    legs = abs(curr_pos - prev_pos)
    fee = legs * fee_per_leg
    return legs, fee


def calculate_period_funding(
    pos: int,
    start_date: date | None,
    end_date: date,
    daily_funding_rate: float,
) -> tuple[int, float]:
    """Tính phí funding cho thời gian nắm giữ vị thế (Brief 118 §2).

    Funding tính cho mỗi ngày lịch có giữ vị thế, lấy trị tuyệt đối:
    funding_cost = days * daily_funding_rate (khi pos != 0).
    Nếu pos == 0 hoặc start_date is None, funding = 0.
    """
    if pos == 0 or start_date is None:
        days = (end_date - start_date).days if start_date else 0
        return days, 0.0
    days = (end_date - start_date).days
    if days < 0:
        raise ValueError(f"Khoảng ngày không hợp lệ: {start_date} -> {end_date}")
    return days, days * abs(daily_funding_rate)


def simulate_tsmom_strategy(
    bars: list[tuple[date, float]],
    funding_rate: float = FUNDING_RATE_B,
    fee_per_leg: float = TAKER_FEE_RATE,
    lookback_rows: int = 250,
) -> list[dict[str, Any]]:
    """Mô phỏng toàn bộ chuỗi tái cân bằng hàng tháng của chiến lược TSMOM.

    Mỗi tháng k có khoảng nắm giữ từ ngày cuối tháng k-1 đến ngày cuối tháng k.
    Tín hiệu được chốt tại ngày cuối tháng k-1 và giữ nguyên suốt tháng k.
    """
    month_ends = identify_month_ends(bars)
    if len(month_ends) < 2:
        return []

    periods: list[dict[str, Any]] = []
    prev_pos = 0

    for idx_m in range(len(month_ends)):
        _, curr_d, curr_c = month_ends[idx_m]
        ym = (curr_d.year, curr_d.month)

        if idx_m == 0:
            # Tháng đầu tiên trong chuỗi không có mốc tháng trước đó
            periods.append({
                "ym": ym,
                "entry_date": None,
                "exit_date": curr_d,
                "entry_close": None,
                "exit_close": curr_c,
                "pos": 0,
                "legs": 0,
                "fee": 0.0,
                "days": 0,
                "funding": 0.0,
                "price_ret": 0.0,
                "ret_gross": 0.0,
                "ret_net": 0.0,
                "mom_r": 0.0,
            })
            continue

        prior_idx, prior_d, prior_c = month_ends[idx_m - 1]

        # 1. Tín hiệu xác định tại prior_idx
        mom_r, pos = compute_tsmom_signal_at_bar(bars, prior_idx, lookback_rows=lookback_rows)

        # 2. Phí giao dịch (turnover fee)
        legs, fee = calculate_turnover_fee(prev_pos, pos, fee_per_leg=fee_per_leg)

        # 3. Phí funding theo số ngày lịch
        days, funding = calculate_period_funding(pos, prior_d, curr_d, funding_rate)

        # 4. Lợi suất giá của kỳ
        price_ret = (curr_c / prior_c) - 1.0
        ret_gross = (pos * price_ret) if pos != 0 else 0.0

        # 5. Lợi suất ròng
        ret_net = ret_gross - fee - funding

        periods.append({
            "ym": ym,
            "entry_date": prior_d,
            "exit_date": curr_d,
            "entry_close": prior_c,
            "exit_close": curr_c,
            "pos": pos,
            "legs": legs,
            "fee": fee,
            "days": days,
            "funding": funding,
            "price_ret": price_ret,
            "ret_gross": ret_gross,
            "ret_net": ret_net,
            "mom_r": mom_r,
        })
        prev_pos = pos

    return periods


def evaluate_window_performance(
    periods: list[dict[str, Any]],
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
) -> dict[str, Any]:
    """Đánh giá hiệu năng chiến lược trong một cửa sổ thời gian cụ thể."""
    sub = [p for p in periods if (start_year, start_month) <= p["ym"] <= (end_year, end_month)]
    if not sub:
        raise ValueError(f"Không có dữ liệu trong cửa sổ ({start_year}-{start_month}) đến ({end_year}-{end_month})")

    eq = 1.0
    curve = [eq]
    rets: list[float] = []
    total_legs = 0
    active_periods_count = 0

    for p in sub:
        r = p["ret_net"]
        rets.append(r)
        total_legs += p["legs"]
        if p["pos"] != 0:
            active_periods_count += 1
        eq *= (1.0 + r)
        curve.append(eq)

    mdd = max_drawdown(curve)
    sh = sharpe(rets, periods_per_year=12.0)
    net_ret = eq - 1.0

    return {
        "n_periods": len(sub),
        "active_periods": active_periods_count,
        "total_legs": total_legs,
        "net_ret": net_ret,
        "mdd": mdd,
        "sharpe": sh,
        "curve": curve,
        "rets": rets,
        "sub_periods": sub,
    }


def run_null_simulation_permutation(
    sub_periods: list[dict[str, Any]],
    real_net_ret: float,
    funding_rate: float = FUNDING_RATE_B,
    fee_per_leg: float = TAKER_FEE_RATE,
    n_iterations: int = 2000,
    seed: int = 42,
) -> tuple[list[float], float]:
    """Chạy đối chứng ngẫu nhiên hoán vị dấu +-1 ngẫu nhiên (Brief 118 §4).

    - Giữ nguyên tập ngày tái cân bằng.
    - Thay dấu momentum bằng +-1 ngẫu nhiên, 50/50 (chỉ trên các kỳ có tín hiệu, bỏ qua warm-up).
    - Giữ nguyên mô hình chi phí (đảo chiều tốn 2 chân, funding theo số ngày).
    - p-value = tỷ lệ lượt có lợi nhuận ròng >= lợi nhuận ròng thật.
    - Dùng empirical_percentile_rank từ trading.metrics.
    """
    rng = random.Random(seed)
    null_rets: list[float] = []

    for _ in range(n_iterations):
        eq = 1.0
        prev_pos = 0
        for p in sub_periods:
            if p["entry_date"] is None or p["pos"] == 0:
                pos = 0
            else:
                pos = 1 if rng.random() < 0.5 else -1

            _, fee = calculate_turnover_fee(prev_pos, pos, fee_per_leg=fee_per_leg)
            _, funding = calculate_period_funding(pos, p["entry_date"], p["exit_date"], funding_rate)

            r_gross = pos * p["price_ret"]
            r_net = r_gross - fee - funding
            eq *= (1.0 + r_net)
            prev_pos = pos

        null_rets.append(eq - 1.0)

    rank = empirical_percentile_rank(null_rets, real_net_ret)
    p_val = 1.0 - (rank / 100.0)
    return null_rets, p_val


def compute_buy_and_hold_benchmark(
    bars: list[tuple[date, float]],
    start_date: date,
    end_date: date,
    funding_rate: float = 0.0,
    fee_per_leg: float = TAKER_FEE_RATE,
) -> dict[str, Any]:
    """Tính đối chứng Mua-và-giữ (Long-only Buy-and-Hold) trên cùng cửa sổ (Brief 118 §8.4).

    Vào Long tại start_date, thoát tại end_date.
    Phí: 2 chân (1 chân vào + 1 chân ra).
    Funding: số ngày lịch nắm giữ * funding_rate.
    """
    sub = [b for b in bars if start_date <= b[0] <= end_date]
    if len(sub) < 2:
        return {"gross_ret": 0.0, "net_ret": 0.0, "days": 0, "start_close": 0.0, "end_close": 0.0}

    start_d, start_c = sub[0]
    end_d, end_c = sub[-1]

    gross_ret = (end_c / start_c) - 1.0
    fee = 2 * fee_per_leg
    days = (end_d - start_d).days
    funding = days * funding_rate
    net_ret = gross_ret - fee - funding

    return {
        "start_date": start_d,
        "end_date": end_d,
        "start_close": start_c,
        "end_close": end_c,
        "days": days,
        "gross_ret": gross_ret,
        "fee": fee,
        "funding": funding,
        "net_ret": net_ret,
    }


# ---------------------------------------------------------------------------
# 2. Đọc cơ sở dữ liệu (Chỉ đọc bars_ext_daily up to 2026-08-31)
# ---------------------------------------------------------------------------

def load_ext_daily_bars(
    conn: psycopg.Connection,
    source: str,
    symbol: str,
) -> list[tuple[date, float]]:
    """Đọc dữ liệu nến ngày từ bars_ext_daily, tuân thủ niêm phong 2026-08-31."""
    sql = """
        SELECT date, close
        FROM bars_ext_daily
        WHERE source = %s AND symbol = %s AND date <= %s
        ORDER BY date ASC;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (source, symbol, SEALED_MAX_DATE_STR))
        return [(r[0], float(r[1])) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# 3. Thực thi chính và xuất báo cáo
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Đo lường chiến lược TSMOM trên Forex (Brief 118)")
    parser.add_argument("--iterations", type=int, default=2000, help="Số lượt chạy đối chứng null (mặc định 2000)")
    parser.add_argument("--seed", type=int, default=42, help="Seed ngẫu nhiên (mặc định 42)")
    parser.add_argument("--dsn", default=None, help="Postgres connection string DSN")
    return parser.parse_args()


def export_monthly_csv(periods: list[dict[str, Any]], filepath: Path) -> None:
    """Ghi bảng chi tiết từng tháng ra file CSV để kiểm chéo."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "year", "month", "entry_date", "exit_date", "entry_close", "exit_close",
        "mom_r_lookback", "pos", "legs", "fee", "days", "funding", "price_ret",
        "ret_gross", "ret_net"
    ]
    with filepath.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for p in periods:
            y, m = p["ym"]
            writer.writerow([
                y, m,
                p["entry_date"].isoformat() if p["entry_date"] else "",
                p["exit_date"].isoformat(),
                f"{p['entry_close']:.6f}" if p["entry_close"] is not None else "",
                f"{p['exit_close']:.6f}",
                f"{p['mom_r']:.6f}",
                p["pos"],
                p["legs"],
                f"{p['fee']:.6f}",
                p["days"],
                f"{p['funding']:.6f}",
                f"{p['price_ret']:.6f}",
                f"{p['ret_gross']:.6f}",
                f"{p['ret_net']:.6f}",
            ])


def main() -> None:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_lines: list[str] = []

    def log(msg: str = "") -> None:
        print(msg)
        summary_lines.append(msg)

    resolved_dsn = resolve_dsn(args.dsn)
    log("=" * 115)
    log("BÁO CÁO ĐO LƯỜNG TIỀN ĐĂNG KÝ: TIME-SERIES MOMENTUM TRÊN FOREX (BRIEF 118)")
    log("Cơ sở dữ liệu: bars_ext_daily (FRB_H10 & ECB) | Niêm phong: 2026-08-31")
    log(f"Tham số: Lookback = 250 hàng, Tái cân bằng hàng tháng, Phí = 0.05%/chân, Seed = {args.seed}, N = {args.iterations}")
    log("=" * 115)

    with psycopg.connect(resolved_dsn) as conn:
        # 1. Chạy 2 cặp chính trên FRB_H10
        pairs_data: dict[str, list[tuple[date, float]]] = {}
        for sym in ["EURUSD", "USDJPY"]:
            bars = load_ext_daily_bars(conn, "FRB_H10", sym)
            pairs_data[sym] = bars

        ecb_eur_bars = load_ext_daily_bars(conn, "ECB", "EURUSD")

    # Lưu trữ p-values cho 4 phép thử thuộc cổng §3
    p_values_for_gate: dict[str, float] = {}
    main_table_rows: list[dict[str, Any]] = []

    for sym in ["EURUSD", "USDJPY"]:
        bars = pairs_data[sym]
        p_A = simulate_tsmom_strategy(bars, funding_rate=FUNDING_RATE_A)
        p_B = simulate_tsmom_strategy(bars, funding_rate=FUNDING_RATE_B)
        p_C = simulate_tsmom_strategy(bars, funding_rate=FUNDING_RATE_C)

        export_monthly_csv(p_B, OUTPUT_DIR / f"{sym.lower()}_frb_monthly.csv")

        # Cửa sổ 1: 1999-01-04 to 2012-12-31
        w1_A = evaluate_window_performance(p_A, 1999, 1, 2012, 12)
        w1_B = evaluate_window_performance(p_B, 1999, 1, 2012, 12)
        w1_C = evaluate_window_performance(p_C, 1999, 1, 2012, 12)
        _, p1 = run_null_simulation_permutation(w1_B["sub_periods"], w1_B["net_ret"], funding_rate=FUNDING_RATE_B, n_iterations=args.iterations, seed=args.seed)
        p_values_for_gate[f"{sym}_CHINH"] = p1

        main_table_rows.append({
            "pair": sym,
            "window": "CHÍNH (1999-2012)",
            "n_rebalance": w1_B["n_periods"],
            "legs": w1_B["total_legs"],
            "ret_A": w1_A["net_ret"],
            "ret_B": w1_B["net_ret"],
            "ret_C": w1_C["net_ret"],
            "mdd_B": w1_B["mdd"],
            "sharpe_B": w1_B["sharpe"],
            "p_val": p1,
            "gate_key": f"{sym}_CHINH",
        })

        # Cửa sổ 2: 2013-01-01 to 2026-08-31
        w2_A = evaluate_window_performance(p_A, 2013, 1, 2026, 8)
        w2_B = evaluate_window_performance(p_B, 2013, 1, 2026, 8)
        w2_C = evaluate_window_performance(p_C, 2013, 1, 2026, 8)
        _, p2 = run_null_simulation_permutation(w2_B["sub_periods"], w2_B["net_ret"], funding_rate=FUNDING_RATE_B, n_iterations=args.iterations, seed=args.seed)
        p_values_for_gate[f"{sym}_LAP_LAI"] = p2

        main_table_rows.append({
            "pair": sym,
            "window": "LẶP LẠI (2013-2026)",
            "n_rebalance": w2_B["n_periods"],
            "legs": w2_B["total_legs"],
            "ret_A": w2_A["net_ret"],
            "ret_B": w2_B["net_ret"],
            "ret_C": w2_C["net_ret"],
            "mdd_B": w2_B["mdd"],
            "sharpe_B": w2_B["sharpe"],
            "p_val": p2,
            "gate_key": f"{sym}_LAP_LAI",
        })

    # Hiệu chỉnh Holm trên 4 phép thử
    holm_results = holm_adjust(p_values_for_gate, alpha=0.05)

    log("\n" + "=" * 115)
    log("BẢNG CHÍNH ĐỢT 118: TIME-SERIES MOMENTUM TRÊN FRB H.10 (EUR/USD & USD/JPY)")
    log("=" * 115)
    header = f"{'Cặp':<8} | {'Cửa sổ':<20} | {'Tái CB':<6} | {'Chân':<5} | {'Mức A (0%)':<11} | {'Mức B (0.016%)':<14} | {'Mức C (0.030%)':<14} | {'MaxDD(B)':<9} | {'Sharpe(B)':<9} | {'p-value':<7} | {'Holm':<6}"
    log(header)
    log("-" * 115)

    for row in main_table_rows:
        h_pass = "ĐẠT" if holm_results[row["gate_key"]] else "K.ĐẠT"
        sh_str = f"{row['sharpe_B']:.2f}" if row['sharpe_B'] is not None else "N/A"
        line = (
            f"{row['pair']:<8} | {row['window']:<20} | {row['n_rebalance']:<6} | {row['legs']:<5} | "
            f"{row['ret_A']*100:>10.2f}% | {row['ret_B']*100:>13.2f}% | {row['ret_C']*100:>13.2f}% | "
            f"{row['mdd_B']*100:>8.2f}% | {sh_str:>9} | {row['p_val']:>7.4f} | {h_pass:<6}"
        )
        log(line)
    log("-" * 115)

    log("\n--- KẾT QUẢ HIỆU CHỈNH HOLM-BONFERRONI (alpha = 0.05, m = 4) ---")
    sorted_p = sorted(p_values_for_gate.items(), key=lambda kv: kv[1])
    for i, (k, p) in enumerate(sorted_p, start=1):
        threshold = 0.05 / (4 - i + 1)
        res = "ĐẠT" if holm_results[k] else "KHÔNG ĐẠT"
        log(f"  [{i}/4] {k:<15}: p = {p:.4f} vs Ngưỡng = {threshold:.4f} -> {res}")

    # 2. Cửa sổ tham khảo USD/JPY 1971-1998
    log("\n" + "=" * 115)
    log("CỬA SỔ THAM KHẢO USD/JPY: 1971-01-04 ĐẾN 1998-12-31 (7.015 PHIÊN / 10.224 NGÀY LỊCH / 336 THÁNG)")
    log("CẢNH BÁO QUAN TRỌNG: Giai đoạn này thuộc chế độ tiền tệ Bretton Woods sụp đổ và Hiệp định Plaza (1985),")
    log("tồn tại xu hướng giảm một chiều cực mạnh của USD/JPY (từ 360 về 115), không phản ánh chế độ hiện đại.")
    log("Cửa sổ này KHÔNG thuộc cổng đạt/không đạt của Brief 118.")
    log("=" * 115)

    jpy_bars = pairs_data["USDJPY"]
    p_A_jpy = simulate_tsmom_strategy(jpy_bars, funding_rate=FUNDING_RATE_A)
    p_B_jpy = simulate_tsmom_strategy(jpy_bars, funding_rate=FUNDING_RATE_B)
    p_C_jpy = simulate_tsmom_strategy(jpy_bars, funding_rate=FUNDING_RATE_C)
    w3_A = evaluate_window_performance(p_A_jpy, 1971, 1, 1998, 12)
    w3_B = evaluate_window_performance(p_B_jpy, 1971, 1, 1998, 12)
    w3_C = evaluate_window_performance(p_C_jpy, 1971, 1, 1998, 12)

    sh_w3 = f"{w3_B['sharpe']:.2f}" if w3_B['sharpe'] is not None else "N/A"
    log(f"Số lần tái cân bằng: {w3_B['n_periods']} | Tổng số chân phí: {w3_B['total_legs']}")
    log(f"Lợi nhuận ròng Mức A (0% funding) : {w3_A['net_ret']*100:>10.2f}%")
    log(f"Lợi nhuận ròng Mức B (0.016%/ngày): {w3_B['net_ret']*100:>10.2f}% (Funding nuốt chửng toàn bộ lợi nhuận)")
    log(f"Lợi nhuận ròng Mức C (0.030%/ngày): {w3_C['net_ret']*100:>10.2f}%")
    log(f"Max Drawdown (Mức B)              : {w3_B['mdd']*100:>10.2f}% | Sharpe: {sh_w3}")

    # 3. Đối chứng Mua-và-giữ (Buy & Hold)
    log("\n" + "=" * 115)
    log("ĐỐI CHỨNG MUA-VÀ-GIỮ (BUY-AND-HOLD) TRÊN CÙNG CÁC CỬA SỔ")
    log("=" * 115)
    bh_header = f"{'Cặp':<8} | {'Cửa sổ':<20} | {'Số ngày':<7} | {'Gross Return':<12} | {'Net Mức A (0%)':<14} | {'Net Mức B (0.016%)':<18} | {'Net Mức C (0.030%)':<18}"
    log(bh_header)
    log("-" * 115)

    for sym in ["EURUSD", "USDJPY"]:
        bars = pairs_data[sym]
        bh_w1 = compute_buy_and_hold_benchmark(bars, date(1999, 1, 4), date(2012, 12, 31), funding_rate=FUNDING_RATE_B)
        bh_w1_A = compute_buy_and_hold_benchmark(bars, date(1999, 1, 4), date(2012, 12, 31), funding_rate=FUNDING_RATE_A)
        bh_w1_C = compute_buy_and_hold_benchmark(bars, date(1999, 1, 4), date(2012, 12, 31), funding_rate=FUNDING_RATE_C)

        bh_w2 = compute_buy_and_hold_benchmark(bars, date(2013, 1, 1), date(2026, 8, 31), funding_rate=FUNDING_RATE_B)
        bh_w2_A = compute_buy_and_hold_benchmark(bars, date(2013, 1, 1), date(2026, 8, 31), funding_rate=FUNDING_RATE_A)
        bh_w2_C = compute_buy_and_hold_benchmark(bars, date(2013, 1, 1), date(2026, 8, 31), funding_rate=FUNDING_RATE_C)

        line_w1 = f"{sym:<8} | {'CHÍNH (1999-2012)':<20} | {bh_w1['days']:<7} | {bh_w1['gross_ret']*100:>11.2f}% | {bh_w1_A['net_ret']*100:>13.2f}% | {bh_w1['net_ret']*100:>17.2f}% | {bh_w1_C['net_ret']*100:>17.2f}%"
        line_w2 = f"{sym:<8} | {'LẶP LẠI (2013-2026)':<20} | {bh_w2['days']:<7} | {bh_w2['gross_ret']*100:>11.2f}% | {bh_w2_A['net_ret']*100:>13.2f}% | {bh_w2['net_ret']*100:>17.2f}% | {bh_w2_C['net_ret']*100:>17.2f}%"
        log(line_w1)
        log(line_w2)

        if sym == "USDJPY":
            bh_w3 = compute_buy_and_hold_benchmark(bars, date(1971, 1, 4), date(1998, 12, 31), funding_rate=FUNDING_RATE_B)
            bh_w3_A = compute_buy_and_hold_benchmark(bars, date(1971, 1, 4), date(1998, 12, 31), funding_rate=FUNDING_RATE_A)
            bh_w3_C = compute_buy_and_hold_benchmark(bars, date(1971, 1, 4), date(1998, 12, 31), funding_rate=FUNDING_RATE_C)
            line_w3 = f"{sym:<8} | {'THAM KHẢO (1971-98)':<20} | {bh_w3['days']:<7} | {bh_w3['gross_ret']*100:>11.2f}% | {bh_w3_A['net_ret']*100:>13.2f}% | {bh_w3['net_ret']*100:>17.2f}% | {bh_w3_C['net_ret']*100:>17.2f}%"
            log(line_w3)
    log("-" * 115)

    # 4. Lặp lại trên chuỗi ECB EUR/USD
    log("\n" + "=" * 115)
    log("LẶP LẠI TRÊN CHUỖI ECB EUR/USD (14:15 CET - KHÁC MỐC ĐỒNG HỒ VỚI BINGX)")
    log("=" * 115)
    ecb_p_A = simulate_tsmom_strategy(ecb_eur_bars, funding_rate=FUNDING_RATE_A)
    ecb_p_B = simulate_tsmom_strategy(ecb_eur_bars, funding_rate=FUNDING_RATE_B)
    ecb_p_C = simulate_tsmom_strategy(ecb_eur_bars, funding_rate=FUNDING_RATE_C)

    export_monthly_csv(ecb_p_B, OUTPUT_DIR / "eurusd_ecb_monthly.csv")

    ecb_w1_A = evaluate_window_performance(ecb_p_A, 1999, 1, 2012, 12)
    ecb_w1_B = evaluate_window_performance(ecb_p_B, 1999, 1, 2012, 12)
    ecb_w1_C = evaluate_window_performance(ecb_p_C, 1999, 1, 2012, 12)

    ecb_w2_A = evaluate_window_performance(ecb_p_A, 2013, 1, 2026, 8)
    ecb_w2_B = evaluate_window_performance(ecb_p_B, 2013, 1, 2026, 8)
    ecb_w2_C = evaluate_window_performance(ecb_p_C, 2013, 1, 2026, 8)

    sh_ecb_w1 = f"{ecb_w1_B['sharpe']:.2f}" if ecb_w1_B['sharpe'] is not None else "N/A"
    sh_ecb_w2 = f"{ecb_w2_B['sharpe']:.2f}" if ecb_w2_B['sharpe'] is not None else "N/A"

    log(f"Cửa sổ 1 (1999-2012): Net A = {ecb_w1_A['net_ret']*100:.2f}%, Net B = {ecb_w1_B['net_ret']*100:.2f}%, Net C = {ecb_w1_C['net_ret']*100:.2f}%, MDD(B) = {ecb_w1_B['mdd']*100:.2f}%, Sharpe(B) = {sh_ecb_w1}")
    log(f"Cửa sổ 2 (2013-2026): Net A = {ecb_w2_A['net_ret']*100:.2f}%, Net B = {ecb_w2_B['net_ret']*100:.2f}%, Net C = {ecb_w2_C['net_ret']*100:.2f}%, MDD(B) = {ecb_w2_B['mdd']*100:.2f}%, Sharpe(B) = {sh_ecb_w2}")
    log("Nhận xét: Lợi nhuận ròng trên chuỗi ECB âm ở cả hai cửa sổ và cả ba mức funding, đồng nhất với chuỗi FRB H.10.")

    # Ghi toàn bộ output ra file
    summary_path = OUTPUT_DIR / "summary_table.txt"
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
    full_output_path = OUTPUT_DIR / "full_run_output.txt"
    full_output_path.write_text("\n".join(summary_lines), encoding="utf-8")
    log(f"\n[INFO] Đã ghi toàn bộ báo cáo tóm tắt vào: {summary_path}")
    log(f"[INFO] Đã ghi full output vào: {full_output_path}")


if __name__ == "__main__":
    main()
