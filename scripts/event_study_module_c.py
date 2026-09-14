"""Event study cho 'module C thiếu vế liquidation' trên Binance In-Sample (Brief đợt 42 Task 4).

Tên gọi bắt buộc: 'module C thiếu vế liquidation'.
Dữ liệu: Binance BTCUSDT In-Sample (2024-01-01 -> 2025-12-31 UTC). Năm 2026 niêm phong.

6 điều kiện LONG lấy nguyên văn tài liệu §6.2 (tính tại close nến 1 giờ t):
1. Xu hướng:
   - close > EMA50
   - EMA20 > EMA50
   - EMA50(t) > EMA50(t-3)
2. Funding:
   - funding_z < +1.0
3. Open Interest:
   - oi_chg_3h <= -0.015  (OI_t / OI_{t-3h} - 1 <= -0.015)
4. Nến xác nhận:
   - close > EMA20
5. Order flow:
   - delta_norm > 0
   - cvd_chg_3h(t) > cvd_chg_3h(t-3)
6. Liquidation: BỎ — dữ liệu không tồn tại.

Phép đo:
- Lợi suất tương lai ở 1h, 4h, 24h.
- So với trung bình không điều kiện của toàn bộ giờ trong IS.
- Hoán vị khối 48 giờ (1000 lần) -> phân phối null của lợi suất trung bình.
- Tiêu chí chốt trước:
  1. Số sự kiện >= 30
  2. Lợi suất tương lai TB > 0 ở ít nhất một chân trời
  3. Lợi suất đó nằm trên phân vị 95 của phân phối null
"""

import argparse
import random
import sys
from datetime import UTC, datetime
from typing import Any

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

from trading.crypto_fees import BINGX_PERP_TAKER
from trading.feature_panel import build_feature_panel
from trading.indicators import EmaCalculator
from trading.metrics import calculate_percentile, empirical_percentile_rank
from trading.models import Bar

ROUND_TRIP_FEE = 2 * BINGX_PERP_TAKER  # 0.0010 = 10 điểm cơ bản

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


MODULE_C_NAME = "module C thiếu vế liquidation"


def check_module_c_conditions(
    bar: Bar,
    feat_row: dict[str, Any],
    ema20_now: float | None,
    ema50_now: float | None,
    ema50_prev3: float | None,
    cvd_3h_prev3: float | None,
) -> dict[str, bool]:
    """Kiểm tra từng vế điều kiện riêng lẻ và điều kiện hợp của 'module C thiếu vế liquidation'."""
    close = bar.close
    funding_z = feat_row.get("funding_z")
    oi_chg_3h = feat_row.get("oi_chg_3h")
    delta_norm = feat_row.get("delta_norm")
    cvd_3h_now = feat_row.get("cvd_chg_3h")

    # 1. Xu hướng
    c_close_ema50 = bool(ema50_now is not None and close > ema50_now)
    c_ema20_ema50 = bool(ema20_now is not None and ema50_now is not None and ema20_now > ema50_now)
    c_ema50_trend = bool(ema50_now is not None and ema50_prev3 is not None and ema50_now > ema50_prev3)
    c_trend = c_close_ema50 and c_ema20_ema50 and c_ema50_trend

    # 2. Funding
    c_funding = bool(funding_z is not None and funding_z < 1.0)

    # 3. OI
    c_oi = bool(oi_chg_3h is not None and oi_chg_3h <= -0.015)

    # 4. Nến xác nhận
    c_confirm = bool(ema20_now is not None and close > ema20_now)

    # 5. Order flow
    c_delta = bool(delta_norm is not None and delta_norm > 0)
    c_cvd = bool(cvd_3h_now is not None and cvd_3h_prev3 is not None and cvd_3h_now > cvd_3h_prev3)
    c_of = c_delta and c_cvd

    # Điều kiện hợp
    c_all = c_trend and c_funding and c_oi and c_confirm and c_of

    return {
        "trend": c_trend,
        "funding": c_funding,
        "oi": c_oi,
        "confirm": c_confirm,
        "orderflow": c_of,
        "all_combined": c_all,
    }


def load_data_for_event_study(
    conn: psycopg.Connection,
    symbol: str = "BTCUSDT",
    is_start: datetime = datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
    is_end: datetime = datetime(2025, 12, 31, 23, 0, tzinfo=UTC),
) -> tuple[list[Bar], list[tuple[datetime, float]], list[dict], list[dict]]:
    """Tải dữ liệu từ DB, gồm cả dữ liệu trước 2024 để warm-up EMA và funding_z."""
    # Klines: Lấy từ 2023-01-01 để EMA50 ổn định hoàn toàn trước 2024
    sql_klines = """
        SELECT ts, open, high, low, close, volume
        FROM binance_klines
        WHERE symbol = %s AND interval = '1h' AND ts <= %s
        ORDER BY ts;
    """
    with conn.cursor() as cur:
        cur.execute(sql_klines, (symbol, datetime(2026, 1, 2, 0, 0, tzinfo=UTC)))
        k_rows = cur.fetchall()

    klines = [
        Bar(symbol=symbol, ts=r[0], open=float(r[1]), high=float(r[2]), low=float(r[3]), close=float(r[4]), volume=float(r[5]))
        for r in k_rows
    ]

    sql_funding = """
        SELECT funding_time, funding_rate
        FROM binance_funding
        WHERE symbol = %s AND funding_time <= %s
        ORDER BY funding_time;
    """
    with conn.cursor() as cur:
        cur.execute(sql_funding, (symbol, datetime(2026, 1, 2, 0, 0, tzinfo=UTC)))
        f_rows = cur.fetchall()
    funding = [(r[0], float(r[1])) for r in f_rows]

    sql_metrics = """
        SELECT ts, sum_open_interest, sum_open_interest_value,
               count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
               count_long_short_ratio, sum_taker_long_short_vol_ratio
        FROM binance_metrics
        WHERE symbol = %s AND ts <= %s
        ORDER BY ts;
    """
    with conn.cursor() as cur:
        cur.execute(sql_metrics, (symbol, datetime(2026, 1, 2, 0, 0, tzinfo=UTC)))
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

    sql_of = """
        SELECT ts, taker_buy_volume, taker_sell_volume, delta, buy_ratio, trade_count
        FROM binance_orderflow_1h
        WHERE symbol = %s AND ts <= %s
        ORDER BY ts;
    """
    with conn.cursor() as cur:
        cur.execute(sql_of, (symbol, datetime(2026, 1, 2, 0, 0, tzinfo=UTC)))
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


def run_event_study(
    klines: list[Bar],
    funding: list[tuple[datetime, float]],
    metrics: list[dict],
    orderflow: list[dict],
    is_start: datetime,
    is_end: datetime,
    n_permutations: int = 1000,
    block_size_hours: int = 48,
    seed: int = 42,
) -> dict[str, Any]:
    """Chạy event study cho 'module C thiếu vế liquidation'."""
    # 1. Tính EMA20 và EMA50 trên toàn bộ klines
    ema20_calc = EmaCalculator(20)
    ema50_calc = EmaCalculator(50)
    ema20_by_ts: dict[datetime, float | None] = {}
    ema50_by_ts: dict[datetime, float | None] = {}

    sorted_klines = sorted(klines, key=lambda b: b.ts)
    for b in sorted_klines:
        v20 = ema20_calc.update(b)
        v50 = ema50_calc.update(b)
        ema20_by_ts[b.ts] = v20
        ema50_by_ts[b.ts] = v50

    # 2. Dựng panel đặc trưng (luật căn dòng đã sửa ở Task 2)
    panel = build_feature_panel(sorted_klines, funding, metrics, orderflow, metric_lag_minutes=5)
    panel_by_ts: dict[datetime, dict] = {r["ts"]: r for r in panel}

    # 3. Lọc các thanh nến thuộc khoảng In-Sample (IS)
    is_bars = [b for b in sorted_klines if is_start <= b.ts <= is_end]
    n_is = len(is_bars)

    # Đếm số giờ thoả từng vế và tìm các vị trí sự kiện
    counts_by_condition = {
        "trend": 0,
        "funding": 0,
        "oi": 0,
        "confirm": 0,
        "orderflow": 0,
        "all_combined": 0,
    }

    event_indices = []
    events_info = []

    fwd_1h_all = []
    fwd_4h_all = []
    fwd_24h_all = []

    for i, bar in enumerate(is_bars):
        feat = panel_by_ts.get(bar.ts, {})
        ema20_val = ema20_by_ts.get(bar.ts)
        ema50_val = ema50_by_ts.get(bar.ts)

        # Lấy EMA50 t-3h và cvd_chg_3h t-3h
        ts_prev3 = bar.ts - (is_bars[1].ts - is_bars[0].ts) * 3 if len(is_bars) > 1 else None
        ema50_prev3 = ema50_by_ts.get(ts_prev3) if ts_prev3 else None
        feat_prev3 = panel_by_ts.get(ts_prev3, {}) if ts_prev3 else {}
        cvd_prev3 = feat_prev3.get("cvd_chg_3h")

        conds = check_module_c_conditions(
            bar=bar,
            feat_row=feat,
            ema20_now=ema20_val,
            ema50_now=ema50_val,
            ema50_prev3=ema50_prev3,
            cvd_3h_prev3=cvd_prev3,
        )

        for k in counts_by_condition:
            if conds[k]:
                counts_by_condition[k] += 1

        r1 = feat.get("fwd_ret_1h")
        r4 = feat.get("fwd_ret_4h")
        r24 = feat.get("fwd_ret_24h")

        fwd_1h_all.append(r1)
        fwd_4h_all.append(r4)
        fwd_24h_all.append(r24)

        if conds["all_combined"]:
            event_indices.append(i)
            events_info.append({
                "ts": bar.ts,
                "close": bar.close,
                "fwd_ret_1h": r1,
                "fwd_ret_4h": r4,
                "fwd_ret_24h": r24,
            })

    n_events = len(event_indices)

    # Tính lợi suất trung bình không điều kiện
    valid_u1 = [r for r in fwd_1h_all if r is not None]
    valid_u4 = [r for r in fwd_4h_all if r is not None]
    valid_u24 = [r for r in fwd_24h_all if r is not None]

    uncond_mean = {
        "1h": sum(valid_u1) / len(valid_u1) if valid_u1 else 0.0,
        "4h": sum(valid_u4) / len(valid_u4) if valid_u4 else 0.0,
        "24h": sum(valid_u24) / len(valid_u24) if valid_u24 else 0.0,
    }

    # Tính lợi suất trung bình sau sự kiện
    ev_r1 = [ev["fwd_ret_1h"] for ev in events_info if ev["fwd_ret_1h"] is not None]
    ev_r4 = [ev["fwd_ret_4h"] for ev in events_info if ev["fwd_ret_4h"] is not None]
    ev_r24 = [ev["fwd_ret_24h"] for ev in events_info if ev["fwd_ret_24h"] is not None]

    event_mean = {
        "1h": sum(ev_r1) / len(ev_r1) if ev_r1 else 0.0,
        "4h": sum(ev_r4) / len(ev_r4) if ev_r4 else 0.0,
        "24h": sum(ev_r24) / len(ev_r24) if ev_r24 else 0.0,
    }

    # Phép kiểm ý nghĩa: Block Permutation Test (nếu n_events >= 1)
    null_p95 = {"1h": 0.0, "4h": 0.0, "24h": 0.0}
    null_means = {"1h": [], "4h": [], "24h": []}
    max_null_ranks: list[float] = []
    max_null_p95 = 0.0

    if n_events > 0 and n_permutations > 0:
        rng = random.Random(seed)
        blocks = []
        cur_b = 0
        while cur_b < n_is:
            blocks.append(list(range(cur_b, min(cur_b + block_size_hours, n_is))))
            cur_b += block_size_hours
        n_blocks = len(blocks)

        for _ in range(n_permutations):
            shuffled_b = list(range(n_blocks))
            rng.shuffle(shuffled_b)
            perm_indices = []
            for b_idx in shuffled_b:
                perm_indices.extend(blocks[b_idx])

            # Lấy lợi suất tại các vị trí event_indices sau hoán vị
            p_r1 = [fwd_1h_all[perm_indices[e_idx]] for e_idx in event_indices if fwd_1h_all[perm_indices[e_idx]] is not None]
            p_r4 = [fwd_4h_all[perm_indices[e_idx]] for e_idx in event_indices if fwd_4h_all[perm_indices[e_idx]] is not None]
            p_r24 = [fwd_24h_all[perm_indices[e_idx]] for e_idx in event_indices if fwd_24h_all[perm_indices[e_idx]] is not None]

            null_means["1h"].append(sum(p_r1) / len(p_r1) if p_r1 else 0.0)
            null_means["4h"].append(sum(p_r4) / len(p_r4) if p_r4 else 0.0)
            null_means["24h"].append(sum(p_r24) / len(p_r24) if p_r24 else 0.0)

        for h in ("1h", "4h", "24h"):
            null_p95[h] = calculate_percentile(null_means[h], 95.0)

        # Brief 44 §3.1: Mỗi lần hoán vị, quy thành phân vị thực nghiệm trong phân phối riêng của nó,
        # rồi lấy giá trị lớn nhất trong ba -> phân phối null của thống kê lớn nhất
        for b_idx in range(n_permutations):
            r1_b = null_means["1h"][b_idx]
            r4_b = null_means["4h"][b_idx]
            r24_b = null_means["24h"][b_idx]
            rank1 = empirical_percentile_rank(null_means["1h"], r1_b)
            rank4 = empirical_percentile_rank(null_means["4h"], r4_b)
            rank24 = empirical_percentile_rank(null_means["24h"], r24_b)
            max_null_ranks.append(max(rank1, rank4, rank24))

        max_null_p95 = calculate_percentile(max_null_ranks, 95.0)

    # Tính phân vị thực nghiệm của kết quả thật
    actual_ranks = {}
    for h in ("1h", "4h", "24h"):
        actual_ranks[h] = (
            empirical_percentile_rank(null_means[h], event_mean[h])
            if (n_events > 0 and n_permutations > 0)
            else 0.0
        )

    best_horizon = max(("1h", "4h", "24h"), key=lambda h: actual_ranks[h])
    max_actual_rank = actual_ranks[best_horizon]

    # Brief 44 §3.2 & §3.3:
    # 1. Số sự kiện >= 30
    # 2. loi_the_rong = mean_event - mean_uncond - 2 * BINGX_PERP_TAKER > 0 ở ít nhất một chân trời
    # 3. Phân vị lớn nhất của kết quả thật vượt phân vị 95 của phân phối null giá trị lớn nhất
    # 4. Chân trời thoả (2) và chân trời thoả (3) là cùng một chân trời
    has_sufficient_power = n_events >= 30
    is_statistically_significant = (
        max_actual_rank > max_null_p95 if (n_events > 0 and n_permutations > 0) else False
    )

    details_horizons = {}
    has_positive_net_edge = False
    for h in ("1h", "4h", "24h"):
        m_ev = event_mean[h]
        u_m = uncond_mean[h]
        diff = m_ev - u_m
        net_edge = diff - ROUND_TRIP_FEE
        is_net_pos = net_edge > 0
        if is_net_pos:
            has_positive_net_edge = True
        is_above_max_p95 = actual_ranks[h] > max_null_p95 if (n_events > 0 and n_permutations > 0) else False
        horizon_pass = is_net_pos and is_above_max_p95
        details_horizons[h] = {
            "mean_event": m_ev,
            "mean_uncond": u_m,
            "diff": diff,
            "round_trip_fee": ROUND_TRIP_FEE,
            "loi_the_rong": net_edge,
            "empirical_percentile": actual_ranks[h],
            "single_null_p95": null_p95[h],
            "null_p95": null_p95[h],
            "is_pos": m_ev > 0,
            "is_net_pos": is_net_pos,
            "above_p95": is_above_max_p95,
            "pass": horizon_pass,
        }

    same_horizon = (details_horizons[best_horizon]["loi_the_rong"] > 0) and is_statistically_significant
    overall_pass = (
        has_sufficient_power
        and has_positive_net_edge
        and is_statistically_significant
        and same_horizon
    )

    return {
        "n_is": n_is,
        "n_events": n_events,
        "has_sufficient_power": has_sufficient_power,
        "has_positive_net_edge": has_positive_net_edge,
        "is_statistically_significant": is_statistically_significant,
        "same_horizon": same_horizon,
        "best_horizon": best_horizon,
        "max_actual_rank": max_actual_rank,
        "max_null_p95": max_null_p95,
        "counts_by_condition": counts_by_condition,
        "events": events_info,
        "uncond_mean": uncond_mean,
        "event_mean": event_mean,
        "null_p95": null_p95,
        "details_horizons": details_horizons,
        "overall_pass": overall_pass,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Event study cho '{MODULE_C_NAME}'.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--is-start", default="2024-01-01")
    parser.add_argument("--is-end", default="2025-12-31")
    parser.add_argument("--permutations", type=int, default=1000)
    parser.add_argument("--block-size", type=int, default=48)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dsn", default=None, help="Database DSN override")

    args = parser.parse_args()

    conn = psycopg.connect(resolve_dsn(args.dsn))
    is_start_dt = datetime.fromisoformat(args.is_start).replace(tzinfo=UTC)
    is_end_dt = datetime.fromisoformat(args.is_end).replace(hour=23, minute=0, second=0, tzinfo=UTC)

    print(f"=== EVENT STUDY: {MODULE_C_NAME.upper()} ===")
    print(f"Tập phân tích: {args.symbol} IS {is_start_dt.date()} -> {is_end_dt.date()} UTC (Năm 2026 niêm phong)")

    klines, funding, metrics, orderflow = load_data_for_event_study(conn, symbol=args.symbol, is_start=is_start_dt, is_end=is_end_dt)
    conn.close()

    res = run_event_study(
        klines,
        funding,
        metrics,
        orderflow,
        is_start=is_start_dt,
        is_end=is_end_dt,
        n_permutations=args.permutations,
        block_size_hours=args.block_size,
        seed=args.seed,
    )

    print(f"\nTổng số giờ trong IS: {res['n_is']} nến.")
    print(f"Số sự kiện kích hoạt ({MODULE_C_NAME}): {res['n_events']}")

    print("\n--- BẢNG SỐ GIỜ THOẢ MÃN TỪNG VẾ RIÊNG LẺ (§4.3) ---")
    c_counts = res["counts_by_condition"]
    print(f"1. Xu hướng (close>EMA50 & EMA20>EMA50 & EMA50_t>EMA50_{{t-3}}): {c_counts['trend']} giờ ({c_counts['trend']/res['n_is']*100:.2f}%)")
    print(f"2. Funding (funding_z < +1.0):                                    {c_counts['funding']} giờ ({c_counts['funding']/res['n_is']*100:.2f}%)")
    print(f"3. OI (oi_chg_3h <= -0.015):                                      {c_counts['oi']} giờ ({c_counts['oi']/res['n_is']*100:.2f}%)")
    print(f"4. Nến xác nhận (close > EMA20):                                  {c_counts['confirm']} giờ ({c_counts['confirm']/res['n_is']*100:.2f}%)")
    print(f"5. Order flow (delta_norm > 0 & cvd_3h_t > cvd_3h_{{t-3}}):         {c_counts['orderflow']} giờ ({c_counts['orderflow']/res['n_is']*100:.2f}%)")
    print(f"-> HỢP CẢ 5 VẾ ({MODULE_C_NAME}):                                  {c_counts['all_combined']} giờ ({c_counts['all_combined']/res['n_is']*100:.2f}%)")

    print("\n--- PHÉP ĐO LỢI THẾ RÒNG VÀ KIỂM ĐỊNH GIÁ TRỊ LỚN NHẤT (Brief 44 §3.1, §3.2) ---")
    print(f"Phí vòng lệnh: 2 * BINGX_PERP_TAKER = {ROUND_TRIP_FEE*100:.2f}% ({ROUND_TRIP_FEE*10000:.0f} bps)")
    print(f"Ngưỡng thống kê Max Null P95: {res['max_null_p95']:.2f}%")
    print(f"{'Chân trời':<10} | {'Lợi suất TB SK (%)':<18} | {'K.điều kiện (%)':<15} | {'Chênh lệch (%)':<15} | {'Lợi thế ròng (%)':<16} | {'Phân vị (%)':<12} | {'Vượt Max P95?':<13} | {'Lợi thế ròng > 0?'}")
    print("-" * 122)

    for h in ("1h", "4h", "24h"):
        d = res["details_horizons"][h]
        v_str = "CÓ" if d["above_p95"] else "Không"
        net_str = "CÓ" if d["is_net_pos"] else "KHÔNG"
        print(
            f"{h:<10} | {d['mean_event']*100:+.4f}%            | "
            f"{d['mean_uncond']*100:+.4f}%      | {d['diff']*100:+.4f}%        | "
            f"{d['loi_the_rong']*100:+.4f}%         | {d['empirical_percentile']:6.2f}%      | "
            f"{v_str:<13} | {net_str}"
        )

    print(f"\nChân trời đạt phân vị lớn nhất: {res['best_horizon']} ({res['max_actual_rank']:.2f}%)")

    print("\n================ KẾT LUẬN TIÊU CHÍ CHỐT TRƯỚC (Brief 44 §3.3) ================")
    print(f"1. Số sự kiện N >= 30: {res['n_events']} -> {'ĐẠT' if res['has_sufficient_power'] else 'KHÔNG ĐẠT'}")
    print(f"2. Lợi thế ròng > 0 ở ít nhất 1 chân trời: {'ĐẠT' if res['has_positive_net_edge'] else 'KHÔNG ĐẠT'}")
    print(f"3. Phân vị lớn nhất ({res['max_actual_rank']:.2f}%) vượt Max Null P95 ({res['max_null_p95']:.2f}%): {'ĐẠT' if res['is_statistically_significant'] else 'KHÔNG ĐẠT'}")
    print(f"4. Chân trời thoả (2) và (3) là cùng một chân trời ({res['best_horizon']}): {'ĐẠT' if res['same_horizon'] else 'KHÔNG ĐẠT'}")
    print("-" * 80)
    if res["overall_pass"]:
        print(">>> KẾT LUẬN TOÀN CUỘC: DƯƠNG — Thoả mãn cả 4 điều kiện chốt trước!")
    else:
        print(">>> KẾT LUẬN TOÀN CUỘC: ÂM — Không thoả mãn đủ 4 điều kiện chốt trước.")


if __name__ == "__main__":
    main()
