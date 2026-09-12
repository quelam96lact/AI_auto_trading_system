"""Kiểm toán thông tin dữ liệu phi giá Binance trên tập In-Sample (Brief đợt 41).

Phép đo:
- 27 cặp: 9 đặc trưng phi giá x 3 biến mục tiêu lợi suất tương lai (1h, 4h, 24h).
- Tương quan hạng Spearman trên các hàng hợp lệ (cả 2 giá trị != NULL).
- Tập In-Sample (IS): 2024-01-01 -> 2025-12-31 UTC. Năm 2026 niêm phong.
- Hiệu chỉnh đa phép kiểm (Family-wise Multiple Testing):
    Hoán vị theo khối (block permutation) 48 giờ trên chuỗi lợi suất.
    Lặp 1,000 lần -> Phân phối null của thống kê lớn nhất max(|rho|).
    Ngưỡng ý nghĩa: Phân vị 95 của phân phối null của max(|rho|).
- Phân tích thập phân vị cho 2 cặp mạnh nhất.
"""

import argparse
import math
import random
import sys
import time
from datetime import UTC, datetime

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

from trading.feature_panel import build_feature_panel
from trading.metrics import calculate_percentile
from trading.models import Bar

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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

TARGET_NAMES = [
    "fwd_ret_1h",
    "fwd_ret_4h",
    "fwd_ret_24h",
]


def fast_spearman_rank_correlation(x: list[float], y: list[float]) -> float:
    """Tính tương quan hạng Spearman giữa 2 chuỗi số thực cùng độ dài."""
    n = len(x)
    if n < 2:
        return 0.0

    def compute_ranks(arr: list[float]) -> list[float]:
        sorted_idx = sorted(range(n), key=lambda i: arr[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            val = arr[sorted_idx[i]]
            while j < n - 1 and arr[sorted_idx[j + 1]] == val:
                j += 1
            avg_r = (i + j + 2) / 2.0
            for k in range(i, j + 1):
                ranks[sorted_idx[k]] = avg_r
            i = j + 1
        return ranks

    rx = compute_ranks(x)
    ry = compute_ranks(y)

    mx = sum(rx) / n
    my = sum(ry) / n
    var_x = sum((r - mx) ** 2 for r in rx)
    var_y = sum((r - my) ** 2 for r in ry)

    if var_x < 1e-12 or var_y < 1e-12:
        return 0.0

    cov = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    return cov / ((var_x * var_y) ** 0.5)


def load_is_data_from_db(
    conn: psycopg.Connection,
    symbol: str = "BTCUSDT",
    is_start: datetime = datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
    is_end: datetime = datetime(2025, 12, 31, 23, 0, tzinfo=UTC),
) -> tuple[list[Bar], list[tuple[datetime, float]], list[dict], list[dict]]:
    """Tải dữ liệu từ DB phục vụ dựng panel cho tập IS (có đệm cho warm-up và fwd return)."""
    # Klines: Lấy từ IS_START đến 2026-01-02 00:00:00 UTC (để tính fwd_ret_24h cho các giờ cuối IS)
    sql_klines = """
        SELECT ts, open, high, low, close, volume
        FROM binance_klines
        WHERE symbol = %s AND interval = '1h' AND ts >= %s AND ts <= %s
        ORDER BY ts;
    """
    with conn.cursor() as cur:
        cur.execute(sql_klines, (symbol, is_start, datetime(2026, 1, 2, 0, 0, tzinfo=UTC)))
        k_rows = cur.fetchall()

    klines = [
        Bar(symbol=symbol, ts=r[0], open=float(r[1]), high=float(r[2]), low=float(r[3]), close=float(r[4]), volume=float(r[5]))
        for r in k_rows
    ]

    # Funding: Lấy toàn bộ từ 2024-01-01 đến 2026-01-02
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

    # Metrics: Lấy từ 2024-01-01 đến 2026-01-02
    sql_metrics = """
        SELECT ts, sum_open_interest, sum_open_interest_value,
               count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
               count_long_short_ratio, sum_taker_long_short_vol_ratio
        FROM binance_metrics
        WHERE symbol = %s AND ts >= %s AND ts <= %s
        ORDER BY ts;
    """
    with conn.cursor() as cur:
        cur.execute(sql_metrics, (symbol, is_start - datetime.resolution * 0, datetime(2026, 1, 2, 0, 0, tzinfo=UTC)))
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

    # Orderflow: Lấy từ 2024-01-01 đến 2026-01-02
    sql_of = """
        SELECT ts, taker_buy_volume, taker_sell_volume, delta, buy_ratio, trade_count
        FROM binance_orderflow_1h
        WHERE symbol = %s AND ts >= %s AND ts <= %s
        ORDER BY ts;
    """
    with conn.cursor() as cur:
        cur.execute(sql_of, (symbol, is_start, datetime(2026, 1, 2, 0, 0, tzinfo=UTC)))
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


def compute_all_correlations(
    panel_rows: list[dict],
    feature_names: list[str] = FEATURE_NAMES,
    target_names: list[str] = TARGET_NAMES,
) -> dict[tuple[str, str], tuple[float, int]]:
    """Tính tương quan Spearman cho tất cả các cặp (feature, target).

    Trả về: {(feat, target): (rho, valid_count)}
    """
    corrs = {}
    for f in feature_names:
        for t in target_names:
            x_vals = []
            y_vals = []
            for row in panel_rows:
                xv = row.get(f)
                yv = row.get(t)
                if xv is not None and yv is not None and not math.isnan(xv) and not math.isnan(yv):
                    x_vals.append(float(xv))
                    y_vals.append(float(yv))

            if len(x_vals) >= 2:
                rho = fast_spearman_rank_correlation(x_vals, y_vals)
                corrs[(f, t)] = (rho, len(x_vals))
            else:
                corrs[(f, t)] = (0.0, 0)

    return corrs


def run_block_permutation_test(
    panel_rows: list[dict],
    n_permutations: int = 1000,
    block_size_hours: int = 48,
    seed: int = 42,
    feature_names: list[str] = FEATURE_NAMES,
    target_names: list[str] = TARGET_NAMES,
) -> tuple[float, list[float]]:
    """Thực hiện Block Permutation Test để tìm ngưỡng phân phối null của max(|rho|).

    - Độ dài khối: 48 giờ để bảo toàn tự tương quan của lợi suất tương lai.
    - Hoán vị chuỗi biến mục tiêu (target returns), giữ nguyên đặc trưng.
    - Lấy max(|rho|) của 27 cặp trong mỗi lần hoán vị.
    - Trả về: (ngưỡng phân vị 95, danh sách 1000 giá trị max null rho).
    """
    rng = random.Random(seed)
    n_rows = len(panel_rows)

    # Chia các chỉ số hàng thành các khối 48 giờ
    blocks = []
    i = 0
    while i < n_rows:
        blocks.append(list(range(i, min(i + block_size_hours, n_rows))))
        i += block_size_hours

    n_blocks = len(blocks)
    max_null_rhos = []

    # Trích xuất sẵn các cột để hoán vị nhanh
    targets_data = {t: [row.get(t) for row in panel_rows] for t in target_names}
    features_data = {f: [row.get(f) for row in panel_rows] for f in feature_names}

    print(f"Bắt đầu chạy {n_permutations} lần hoán vị theo khối {block_size_hours}h...")
    t_start = time.perf_counter()

    for p_idx in range(n_permutations):
        # Hoán vị thứ tự các block
        shuffled_block_order = list(range(n_blocks))
        rng.shuffle(shuffled_block_order)

        # Ghép lại thứ tự hàng sau hoán vị cho target
        perm_target_indices = []
        for b_idx in shuffled_block_order:
            perm_target_indices.extend(blocks[b_idx])

        # Chuỗi target đã hoán vị
        perm_targets = {t: [targets_data[t][old_i] for old_i in perm_target_indices] for t in target_names}

        # Tính 27 tương quan trên chuỗi hoán vị
        cur_rhos = []
        for f in feature_names:
            f_col = features_data[f]
            for t in target_names:
                t_col = perm_targets[t]

                # Lọc các cặp không None
                x_v = []
                y_v = []
                for row_idx in range(n_rows):
                    xv = f_col[row_idx]
                    yv = t_col[row_idx]
                    if xv is not None and yv is not None:
                        x_v.append(xv)
                        y_v.append(yv)

                if len(x_v) >= 10:
                    r = fast_spearman_rank_correlation(x_v, y_v)
                    cur_rhos.append(abs(r))
                else:
                    cur_rhos.append(0.0)

        max_rho_perm = max(cur_rhos) if cur_rhos else 0.0
        max_null_rhos.append(max_rho_perm)

        if (p_idx + 1) % 250 == 0:
            elapsed = time.perf_counter() - t_start
            print(f"  Hoàn thành {p_idx + 1}/{n_permutations} lượt hoán vị ({elapsed:.1f}s)...")

    threshold_95 = calculate_percentile(max_null_rhos, 95.0)
    return threshold_95, max_null_rhos


def analyze_deciles(
    panel_rows: list[dict],
    feature_name: str,
    target_name: str,
) -> list[dict]:
    """Chia 10 nhóm theo giá trị đặc trưng và tính lợi suất tương lai trung bình."""
    valid_pairs = []
    for row in panel_rows:
        x = row.get(feature_name)
        y = row.get(target_name)
        if x is not None and y is not None:
            valid_pairs.append((float(x), float(y)))

    if not valid_pairs:
        return []

    # Sắp xếp theo feature x
    valid_pairs.sort(key=lambda item: item[0])
    n = len(valid_pairs)
    deciles = []

    for d in range(10):
        start_idx = int(d * n / 10.0)
        end_idx = int((d + 1) * n / 10.0) if d < 9 else n
        group = valid_pairs[start_idx:end_idx]

        count = len(group)
        if count > 0:
            mean_fwd_ret = sum(item[1] for item in group) / count
            min_feat = group[0][0]
            max_feat = group[-1][0]
        else:
            mean_fwd_ret = 0.0
            min_feat = 0.0
            max_feat = 0.0

        deciles.append({
            "decile": d + 1,
            "count": count,
            "min_feature": min_feat,
            "max_feature": max_feat,
            "mean_fwd_ret_pct": mean_fwd_ret * 100.0,
        })

    return deciles


def main() -> None:
    parser = argparse.ArgumentParser(description="Kiểm toán thông tin dữ liệu phi giá Binance IS (Brief đợt 41).")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--is-start", default="2024-01-01")
    parser.add_argument("--is-end", default="2025-12-31")
    parser.add_argument("--permutations", type=int, default=1000)
    parser.add_argument("--block-size", type=int, default=48)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--control-test", action="store_true", help="Chạy đối chứng dương và âm để kiểm tra công cụ")
    parser.add_argument("--dsn", default=None, help="Database DSN override")

    args = parser.parse_args()

    conn = psycopg.connect(resolve_dsn(args.dsn))

    is_start_dt = datetime.fromisoformat(args.is_start).replace(tzinfo=UTC)
    is_end_dt = datetime.fromisoformat(args.is_end).replace(hour=23, minute=0, second=0, tzinfo=UTC)

    print(f"=== [KIỂM TOÁN THÔNG TIN DỮ LIỆU PHI GIÁ] {args.symbol} ===")
    print(f"Khoảng In-Sample (IS): {is_start_dt} -> {is_end_dt} UTC (Năm 2026 niêm phong)")

    # 1. Tải dữ liệu từ DB
    klines, funding, metrics, orderflow = load_is_data_from_db(conn, symbol=args.symbol, is_start=is_start_dt, is_end=is_end_dt)
    conn.close()

    print(f"Dữ liệu tải: {len(klines)} nến, {len(funding)} lần funding, {len(metrics)} metrics, {len(orderflow)} orderflow.")

    # 2. Dựng bảng đặc trưng
    t_p0 = time.perf_counter()
    raw_panel = build_feature_panel(klines, funding, metrics, orderflow)
    # Lọc đúng khoảng IS
    is_panel = [r for r in raw_panel if is_start_dt <= r["ts"] <= is_end_dt]
    print(f"Bảng đặc trưng IS: {len(is_panel)} hàng ({time.perf_counter() - t_p0:.2f}s).")

    # Kiểm tra đối chứng nếu có cờ --control-test
    if args.control_test:
        print("\n=== CHẠY KIỂM TOÁN ĐỐI CHỨNG (CONTROLS) ===")
        rng_ctrl = random.Random(args.seed)
        ctrl_panel = []
        for r in is_panel:
            rc = dict(r)
            fwd_1h = r.get("fwd_ret_1h")
            # Đối chứng dương: cheat = fwd_ret_1h + nhiễu nhỏ 0.0001
            rc["ctrl_cheat"] = fwd_1h + rng_ctrl.gauss(0, 0.0001) if fwd_1h is not None else None
            # Đối chứng âm: random noise N(0, 1)
            rc["ctrl_noise"] = rng_ctrl.gauss(0, 1.0)
            ctrl_panel.append(rc)

        test_feats = ["ctrl_cheat", "ctrl_noise"]
        ctrl_corrs = compute_all_correlations(ctrl_panel, feature_names=test_feats, target_names=["fwd_ret_1h"])
        print(f"Tương quan Đối chứng Dương (cheat x fwd_ret_1h): rho = {ctrl_corrs[('ctrl_cheat', 'fwd_ret_1h')][0]:.4f}")
        print(f"Tương quan Đối chứng Âm   (noise x fwd_ret_1h): rho = {ctrl_corrs[('ctrl_noise', 'fwd_ret_1h')][0]:.4f}")

    # 3. Tính tương quan thực tế cho 27 cặp
    real_corrs = compute_all_correlations(is_panel, FEATURE_NAMES, TARGET_NAMES)

    # 4. Chạy hoán vị khối 48h (1000 lần)
    threshold_95, _null_dist = run_block_permutation_test(
        is_panel,
        n_permutations=args.permutations,
        block_size_hours=args.block_size,
        seed=args.seed,
        feature_names=FEATURE_NAMES,
        target_names=TARGET_NAMES,
    )

    print("\n================ KẾT QUẢ KIỂM TOÁN 27 CẶP (IN-SAMPLE 2024-2025) ================")
    print(f"Ngưỡng phân vị 95 của phân phối Null max(|rho|): {threshold_95:.6f}")
    print(f"{'Đặc trưng':<22} | {'Mục tiêu':<12} | {'Spearman rho':<14} | {'Số hàng':<8} | {'Vượt ngưỡng?':<12}")
    print("-" * 75)

    significant_pairs = []
    sorted_pairs = sorted(real_corrs.items(), key=lambda item: abs(item[1][0]), reverse=True)

    for (f, t), (rho, cnt) in sorted_pairs:
        is_sig = abs(rho) > threshold_95
        if is_sig:
            significant_pairs.append(((f, t), rho, cnt))
        status_str = "CÓ (VƯỢT)" if is_sig else "Không"
        print(f"{f:<22} | {t:<12} | {rho:+.6f}      | {cnt:<8} | {status_str:<12}")

    print("\n================ KẾT LUẬN KIỂM TOÁN ================")
    if significant_pairs:
        print(f"CÓ {len(significant_pairs)} cặp vượt ngưỡng ý nghĩa đa phép kiểm:")
        for (f, t), rho, cnt in significant_pairs:
            print(f"  - ({f}, {t}): rho = {rho:+.6f} (n={cnt:,})")
    else:
        print("KHÔNG có cặp nào trong 27 cặp vượt ngưỡng phân vị 95 của phân phối null!")

    # 5. Phân tích thập phân vị cho 2 cặp mạnh nhất
    top_2_pairs = [sorted_pairs[0][0], sorted_pairs[1][0]]
    print("\n================ PHÂN TÍCH THẬP PHÂN VỊ CHO 2 CẶP MẠNH NHẤT ================")
    for f_top, t_top in top_2_pairs:
        rho_val = real_corrs[(f_top, t_top)][0]
        print(f"\n--- Cặp: {f_top} x {t_top} (rho = {rho_val:+.6f}) ---")
        deciles = analyze_deciles(is_panel, f_top, t_top)
        print(f"{'Thập phân vị':<12} | {'Số nến':<8} | {'Khoảng giá trị đặc trưng':<28} | {'Lợi suất tương lai TB (%)':<24}")
        print("-" * 80)
        for d in deciles:
            val_range = f"[{d['min_feature']:.5f}, {d['max_feature']:.5f}]"
            print(f"Nhóm {d['decile']:<6} | {d['count']:<8} | {val_range:<28} | {d['mean_fwd_ret_pct']:+.4f}%")


if __name__ == "__main__":
    main()
