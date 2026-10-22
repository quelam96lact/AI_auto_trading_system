"""Exploration runner for Brief 188 (multi-timeframe anti-overfitting research).

Executes:
1. Loads explore datasets (stocks_daily, crypto_1h, exchanges).
2. Evaluates each of the 6 ideas over its pre-registered parameter grid on EA.
3. Logs every configuration strictly via evaluate_and_log into trial_ledger.csv.
4. Performs Step 1 (Sharpe peak with n >= 100).
5. Performs Step 2 (Plateau check: all +/- 1 step neighbors mean_net > 0 and Sharpe >= 50% peak).
6. Performs Step 3 (Single EB evaluation: n>=100, mean_net>0, p<0.05, calmar>=0.86, excess/gross check).
7. Performs Step 4 (DSR on EA with n_trials = market EA rows + 22, target >= 0.95).
8. Generates candidates.json and exploration_report.md.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from scripts import research188_ideas
from scripts.research188_core import (
    Bar,
    Trade,
    align_higher,
    calculate_stock_baseline_excess,
    calculate_trade_metrics,
    deflated_sharpe,
    resample,
    simulate_portfolio,
)
from scripts.research188_data import TZ_VN, load_crypto, load_exchanges, load_stocks
from scripts.research188_ledger import compute_idea_sha, evaluate_and_log

# Period definitions
STK_EA_START = datetime(2016, 1, 1, 0, 0, tzinfo=TZ_VN)
STK_EA_END = datetime(2019, 12, 31, 23, 59, 59, tzinfo=TZ_VN)
STK_EB_START = datetime(2020, 1, 1, 0, 0, tzinfo=TZ_VN)
STK_EB_END = datetime(2022, 12, 31, 23, 59, 59, tzinfo=TZ_VN)

CRY_EA_START = datetime(2024, 4, 27, 10, 0, tzinfo=UTC)
CRY_EA_END = datetime(2025, 7, 31, 23, 59, 59, tzinfo=UTC)
CRY_EB_START = datetime(2025, 8, 1, 0, 0, tzinfo=UTC)
CRY_EB_END = datetime(2026, 8, 31, 23, 0, 0, tzinfo=UTC)

LEDGER_PATH = "docs/research/dot188/trial_ledger.csv"
CANDIDATES_PATH = "docs/research/dot188/candidates.json"
REPORT_PATH = "docs/research/dot188/exploration_report.md"


def get_grid_neighbors(params: dict, grid: dict) -> list[dict]:
    """Find all grid points differing by exactly +/- 1 step on ONE parameter."""
    neighbors: list[dict] = []
    keys = list(grid.keys())

    for k in keys:
        vals = grid[k]
        idx = vals.index(params[k])
        if idx > 0:
            n_down = dict(params)
            n_down[k] = vals[idx - 1]
            neighbors.append(n_down)
        if idx < len(vals) - 1:
            n_up = dict(params)
            n_up[k] = vals[idx + 1]
            neighbors.append(n_up)

    return neighbors


def run_stock_idea_simulation(
    rule_fn,
    params: dict,
    stocks_data: dict[str, list[Bar]],
    pre_weekly: dict[str, list[Bar]],
    pre_aligned_wk: dict[str, list[Bar | None]],
    pre_monthly: dict[str, list[Bar]],
    pre_aligned_mn: dict[str, list[Bar | None]],
    exchanges: dict[str, str],
    period_start: datetime,
    period_end: datetime,
) -> list[Trade]:
    all_trades: list[Trade] = []
    for sym, daily_bars in stocks_data.items():
        exch = exchanges.get(sym, "HOSE")
        wk_bars = pre_weekly[sym]
        al_wk = pre_aligned_wk[sym]

        if rule_fn.__name__ == "rule_idea3_stk_mn_trend_wk_mom":
            mn_bars = pre_monthly[sym]
            al_mn = pre_aligned_mn[sym]
            trades = rule_fn(
                daily_bars,
                wk_bars,
                mn_bars,
                al_wk,
                al_mn,
                exch,
                params,
                period_start,
                period_end,
            )
        else:
            trades = rule_fn(
                daily_bars, wk_bars, al_wk, exch, params, period_start, period_end
            )
        all_trades.extend(trades)
    return all_trades


def run_crypto_idea_simulation(
    rule_fn,
    params: dict,
    crypto_data: dict[str, list[Bar]],
    pre_4h: dict[str, list[Bar]],
    pre_aligned_4h: dict[str, list[Bar | None]],
    pre_1d: dict[str, list[Bar]],
    pre_aligned_1d: dict[str, list[Bar | None]],
    period_start: datetime,
    period_end: datetime,
) -> list[Trade]:
    all_trades: list[Trade] = []
    for sym, bars_1h in crypto_data.items():
        b_4h = pre_4h[sym]
        al_4h = pre_aligned_4h[sym]
        b_1d = pre_1d[sym]
        al_1d = pre_aligned_1d[sym]

        trades = rule_fn(
            bars_1h, b_4h, b_1d, al_4h, al_1d, params, period_start, period_end
        )
        all_trades.extend(trades)
    return all_trades


def main():
    print("[1/5] Loading explore data...")
    t0 = time.time()
    stocks_data = load_stocks("data/research188/explore")
    crypto_data = load_crypto("data/research188/explore")
    exchanges = load_exchanges("data/research188/explore")
    print(
        f"Loaded {len(stocks_data)} stocks, {len(crypto_data)} crypto symbols in {time.time()-t0:.2f}s"
    )

    print("[2/5] Pre-resampling and pre-aligning higher timeframes...")
    t0 = time.time()
    pre_weekly: dict[str, list[Bar]] = {}
    pre_aligned_wk: dict[str, list[Bar | None]] = {}
    pre_monthly: dict[str, list[Bar]] = {}
    pre_aligned_mn: dict[str, list[Bar | None]] = {}

    for sym, d_bars in stocks_data.items():
        w_bars = resample(d_bars, "1W")
        pre_weekly[sym] = w_bars
        pre_aligned_wk[sym] = align_higher(d_bars, w_bars)

        m_bars = resample(d_bars, "1M")
        pre_monthly[sym] = m_bars
        pre_aligned_mn[sym] = align_higher(d_bars, m_bars)

    pre_4h: dict[str, list[Bar]] = {}
    pre_aligned_4h: dict[str, list[Bar | None]] = {}
    pre_1d: dict[str, list[Bar]] = {}
    pre_aligned_1d: dict[str, list[Bar | None]] = {}

    for sym, c_bars in crypto_data.items():
        b_4h = resample(c_bars, "4h")
        pre_4h[sym] = b_4h
        pre_aligned_4h[sym] = align_higher(c_bars, b_4h)

        b_1d = resample(c_bars, "1d")
        pre_1d[sym] = b_1d
        pre_aligned_1d[sym] = align_higher(c_bars, b_1d)

    print(f"Pre-resampled all symbols in {time.time()-t0:.2f}s")

    # Sổ thử chỉ ghi nối thêm: không bao giờ xoá sổ cũ (audit 23/10 bỏ lệnh unlink)
    ledger_p = Path(LEDGER_PATH)
    if ledger_p.exists():
        raise SystemExit(f"{LEDGER_PATH} đã tồn tại; sổ thử không được xoá để chạy lại")

    ideas_spec = [
        {
            "id": "STK_WK_TREND_PULLBACK",
            "market": "stock",
            "fn": research188_ideas.rule_idea1_stk_wk_trend_pullback,
            "grid": {
                "w_period": [10, 20, 30],
                "rsi_len": [3, 5, 7],
                "rsi_thresh": [20, 25, 30],
            },
        },
        {
            "id": "STK_WK_VOL_BREAKOUT",
            "market": "stock",
            "fn": research188_ideas.rule_idea2_stk_wk_vol_breakout,
            "grid": {
                "vol_thresh": [0.05, 0.07, 0.09],
                "n_days": [15, 20, 25],
                "exit_days": [5, 10, 15],
            },
        },
        {
            "id": "STK_MN_TREND_WK_MOM",
            "market": "stock",
            "fn": research188_ideas.rule_idea3_stk_mn_trend_wk_mom,
            "grid": {
                "m_len": [6, 9, 12],
                "k_weeks": [2, 4, 6],
                "mom_thresh": [0.02, 0.04, 0.06],
            },
        },
        {
            "id": "CRY_1D_TREND_4H_PULLBACK",
            "market": "crypto",
            "fn": research188_ideas.rule_idea4_cry_1d_trend_4h_pullback,
            "grid": {
                "d_period": [15, 20, 30],
                "rsi_low": [25, 30, 35],
                "exit_len": [10, 15, 20],
            },
        },
        {
            "id": "CRY_4H_VOL_BREAKOUT",
            "market": "crypto",
            "fn": research188_ideas.rule_idea5_cry_4h_vol_breakout,
            "grid": {
                "trend_len": [10, 20, 30],
                "bb_len": [15, 20, 25],
                "bb_std": [1.8, 2.0, 2.2],
            },
        },
        {
            "id": "STK_WK_DONCHIAN_CHANNEL",
            "market": "stock",
            "fn": research188_ideas.rule_idea6_stk_wk_donchian_channel,
            "grid": {
                "n_weeks": [10, 15, 20, 25],
                "exit_weeks": [5, 8, 10, 12],
            },
        },
    ]

    print("\n[3/5] Running EA explorations and recording to trial ledger...")
    ea_results: dict[str, list[dict]] = {}
    total_evals = 0

    for idea in ideas_spec:
        i_id = idea["id"]
        market = idea["market"]
        fn = idea["fn"]
        grid = idea["grid"]
        ea_results[i_id] = []

        # Generate combinations
        keys = list(grid.keys())
        import itertools

        combinations = list(itertools.product(*[grid[k] for k in keys]))
        print(f"Evaluating {i_id} ({len(combinations)} configs on EA)...")

        for combo in combinations:
            params = dict(zip(keys, combo))
            if market == "stock":
                trades = run_stock_idea_simulation(
                    fn,
                    params,
                    stocks_data,
                    pre_weekly,
                    pre_aligned_wk,
                    pre_monthly,
                    pre_aligned_mn,
                    exchanges,
                    STK_EA_START,
                    STK_EA_END,
                )
                port = simulate_portfolio(trades, "stock")
            else:
                trades = run_crypto_idea_simulation(
                    fn,
                    params,
                    crypto_data,
                    pre_4h,
                    pre_aligned_4h,
                    pre_1d,
                    pre_aligned_1d,
                    CRY_EA_START,
                    CRY_EA_END,
                )
                port = simulate_portfolio(trades, "crypto")

            metrics = calculate_trade_metrics(trades)
            metrics.update(port)

            evaluate_and_log(
                idea_id=i_id,
                idea_fn_or_sha=fn,
                params=params,
                market=market,
                period="EA",
                metrics=metrics,
                ledger_path=LEDGER_PATH,
            )
            ea_results[i_id].append({"params": params, "metrics": metrics})
            total_evals += 1

    print(f"Completed {total_evals} EA evaluations. Ledger has {total_evals} rows.")

    # Calculate market-level trial counts and Sharpe variances for DSR
    market_ea_sharpes: dict[str, list[float]] = {"stock": [], "crypto": []}
    for idea in ideas_spec:
        m = idea["market"]
        for res in ea_results[idea["id"]]:
            market_ea_sharpes[m].append(res["metrics"]["sharpe"])

    market_ea_var = {
        m: float(np.var(vals, ddof=1)) if len(vals) > 1 else 0.01
        for m, vals in market_ea_sharpes.items()
    }
    market_ea_count = {m: len(vals) for m, vals in market_ea_sharpes.items()}

    print("\n[4/5] Evaluating Steps 1-4 for each idea...")
    candidates = []
    report_lines = []

    report_lines.append(
        "# Báo cáo kết quả khám phá chiến lược đa khung thời gian (Đợt 188)\n"
    )
    report_lines.append(f"- Thời điểm chạy: {datetime.now(UTC).isoformat()}")
    report_lines.append(
        f"- Tổng số cấu hình EA đã đánh giá và ghi sổ: {total_evals} / 400 ngân sách."
    )
    report_lines.append(
        f"- Phân bổ thị trường: Cổ phiếu {market_ea_count['stock']} cấu hình, Crypto {market_ea_count['crypto']} cấu hình.\n"
    )

    for idea in ideas_spec:
        i_id = idea["id"]
        market = idea["market"]
        fn = idea["fn"]
        grid = idea["grid"]
        results = ea_results[i_id]

        report_lines.append(f"## Ý tưởng: `{i_id}` ({market.upper()})\n")

        # Step 1: Select highest Sharpe config with n >= 100
        eligible_ea = [r for r in results if r["metrics"]["n"] >= 100]
        if not eligible_ea:
            max_n = max((r["metrics"]["n"] for r in results), default=0)
            report_lines.append(
                f"❌ **LOẠI TẠI BƯỚC 1 (THIẾU SỨC MẠNH EA):** Không có cấu hình nào đạt $n \\ge 100$ (max n = {max_n}).\n"
            )
            continue

        selected = max(eligible_ea, key=lambda r: r["metrics"]["sharpe"])
        sel_params = selected["params"]
        sel_m = selected["metrics"]

        report_lines.append(f"- **Cấu hình đỉnh EA được chọn:** `{sel_params}`")
        report_lines.append(
            f"  - $n = {sel_m['n']}$, Lãi ròng TB = {sel_m['mean_net']*100:.2f}%, Sharpe = {sel_m['sharpe']:.4f}, p = {sel_m['p']:.4f}, Calmar = {sel_m['calmar']:.2f}\n"
        )

        # Step 2: Plateau check (+/- 1 step on each parameter)
        neighbors = get_grid_neighbors(sel_params, grid)
        plateau_passed = True
        plateau_failures = []

        # Find results for neighbors
        for nb in neighbors:
            nb_res = next((r for r in results if r["params"] == nb), None)
            if nb_res is None:
                continue
            nb_m = nb_res["metrics"]
            # Must have mean_net > 0 and sharpe >= 0.5 * selected_sharpe
            if nb_m["mean_net"] <= 0.0 or nb_m["sharpe"] < 0.5 * sel_m["sharpe"]:
                plateau_passed = False
                plateau_failures.append(
                    f"neighbor {nb}: mean_net={nb_m['mean_net']*100:.2f}%, sharpe={nb_m['sharpe']:.4f} (cần > 0 và >= {0.5*sel_m['sharpe']:.4f})"
                )

        if not plateau_passed:
            report_lines.append(
                "❌ **LOẠI TẠI BƯỚC 2 (TRƯỢT CAO NGUYÊN):** Đỉnh bị nhọn, các cấu hình láng giềng sụp đổ hiệu quả:"
            )
            for pf in plateau_failures:
                report_lines.append(f"  - {pf}")
            report_lines.append("")
            continue
        else:
            report_lines.append(
                f"✅ **BƯỚC 2 (CAO NGUYÊN ĐẠT):** Cả {len(neighbors)} cấu hình láng giềng đều duy trì lãi ròng > 0 và Sharpe >= 50% đỉnh.\n"
            )

        # Step 3: Run ONCE on EB
        print(f"Running single EB evaluation for {i_id} with {sel_params}...")
        if market == "stock":
            eb_trades = run_stock_idea_simulation(
                fn,
                sel_params,
                stocks_data,
                pre_weekly,
                pre_aligned_wk,
                pre_monthly,
                pre_aligned_mn,
                exchanges,
                STK_EB_START,
                STK_EB_END,
            )
            eb_port = simulate_portfolio(eb_trades, "stock")
            eb_excess = calculate_stock_baseline_excess(eb_trades, stocks_data)
        else:
            eb_trades = run_crypto_idea_simulation(
                fn,
                sel_params,
                crypto_data,
                pre_4h,
                pre_aligned_4h,
                pre_1d,
                pre_aligned_1d,
                CRY_EB_START,
                CRY_EB_END,
            )
            eb_port = simulate_portfolio(eb_trades, "crypto")
            eb_excess = {"mean_excess_trim1pct": 0.0}

        eb_metrics = calculate_trade_metrics(eb_trades)
        eb_metrics.update(eb_port)

        # Log to ledger
        evaluate_and_log(
            idea_id=i_id,
            idea_fn_or_sha=fn,
            params=sel_params,
            market=market,
            period="EB",
            metrics=eb_metrics,
            ledger_path=LEDGER_PATH,
        )

        eb_n = eb_metrics["n"]
        eb_mean_net = eb_metrics["mean_net"]
        eb_p = eb_metrics["p"]
        eb_calmar = eb_metrics["calmar"]

        report_lines.append(
            "- **Kết quả kiểm chứng EB (2020-2022 cổ phiếu / 2025-2026 crypto):**"
        )
        report_lines.append(
            f"  - $n = {eb_n}$, Lãi ròng TB = {eb_mean_net*100:.2f}%, p = {eb_p:.4f}, Calmar = {eb_calmar:.2f}"
        )

        eb_passed = True
        eb_fail_reasons = []

        if eb_n < 100:
            eb_passed = False
            eb_fail_reasons.append(f"n={eb_n} < 100")
        if eb_mean_net <= 0.0:
            eb_passed = False
            eb_fail_reasons.append(f"mean_net={eb_mean_net*100:.2f}% <= 0")
        if eb_p >= 0.05:
            eb_passed = False
            eb_fail_reasons.append(f"p={eb_p:.4f} >= 0.05")
        if eb_calmar < 0.86:
            eb_passed = False
            eb_fail_reasons.append(f"calmar={eb_calmar:.2f} < 0.86")

        if market == "stock":
            trim_exc = eb_excess["mean_excess_trim1pct"]
            report_lines.append(
                f"  - Vượt baseline sau cắt 1% lãi nhất = {trim_exc*100:.2f}%"
            )
            if trim_exc <= 0.0:
                eb_passed = False
                eb_fail_reasons.append(
                    f"baseline excess trim 1% = {trim_exc*100:.2f}% <= 0"
                )
        else:
            mean_gross = (
                sum(t.gross_return for t in eb_trades) / eb_n if eb_n > 0 else 0.0
            )
            target_gross = 1.5 * 0.0014
            report_lines.append(
                f"  - Lãi gộp TB = {mean_gross*100:.2f}% (ngưỡng 1.5 x phí = {target_gross*100:.2f}%)"
            )
            if mean_gross < target_gross:
                eb_passed = False
                eb_fail_reasons.append(
                    f"mean_gross={mean_gross*100:.2f}% < {target_gross*100:.2f}%"
                )

        if not eb_passed:
            report_lines.append(
                f"❌ **LOẠI TẠI BƯỚC 3 (TRƯỢT CỔNG EB):** {', '.join(eb_fail_reasons)}\n"
            )
            continue
        else:
            report_lines.append("✅ **BƯỚC 3 (EB ĐẠT CỔNG KHẮT KHE)**\n")

        # Step 4: DSR Check on EA
        n_trials_market = market_ea_count[market] + 22
        sr_var_market = market_ea_var[market]
        dsr_val = deflated_sharpe(
            sr=sel_m["sharpe"],
            n_obs=sel_m["n"],
            skew=sel_m["skew"],
            kurt=sel_m["kurt"],
            n_trials=n_trials_market,
            sr_trials_var=sr_var_market,
        )

        report_lines.append("- **Bước 4: Deflated Sharpe Ratio (DSR):**")
        report_lines.append(
            f"  - n_trials = {n_trials_market} ({market_ea_count[market]} EA + 22 phép đo âm trước), var(SR) = {sr_var_market:.6f}"
        )
        report_lines.append(f"  - DSR = {dsr_val:.4f} (ngưỡng đạt >= 0.95)")

        if dsr_val < 0.95:
            report_lines.append(
                f"❌ **LOẠI TẠI BƯỚC 4 (TRƯỢT DSR):** DSR = {dsr_val:.4f} < 0.95 (bị phạt đa so sánh quá nặng).\n"
            )
            continue
        else:
            report_lines.append("🎉 **ĐẠT CẢ 4 BƯỚC! TRỞ THÀNH ỨNG VIÊN.**\n")
            candidates.append(
                {
                    "idea_id": i_id,
                    "idea_sha": compute_idea_sha(fn),
                    "market": market,
                    "params": sel_params,
                    "rule_fn": fn.__name__,
                    "eb_p": eb_p,
                }
            )

    # Sort candidates by EB p-value ascending, take top 3
    candidates.sort(key=lambda c: c["eb_p"])
    final_candidates = candidates[:3]

    print(
        f"\n[5/5] Finalizing candidate selection: {len(final_candidates)} candidates selected."
    )
    # Write candidates.json
    cand_path = Path(CANDIDATES_PATH)
    cand_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cand_path, "w", encoding="utf-8") as f:
        json.dump(final_candidates, f, indent=2)

    cand_sha = hashlib.sha256(cand_path.read_bytes()).hexdigest()

    report_lines.append("## Kết luận ứng viên\n")
    if final_candidates:
        report_lines.append(
            f"Tìm thấy **{len(final_candidates)} ứng viên** vượt qua toàn bộ 4 hàng rào chống overfit:"
        )
        for c in final_candidates:
            report_lines.append(
                f"- **{c['idea_id']}** ({c['market']}): params = `{c['params']}`, rule_fn = `{c['rule_fn']}`, p(EB) = {c['eb_p']:.4f}"
            )
    else:
        report_lines.append(
            "Không có ứng viên nào vượt qua toàn bộ 4 hàng rào chống overfit (**0 ứng viên**)."
        )
        report_lines.append(
            "Đây là kết quả hoàn toàn hợp lệ, phản ánh đúng tính khắc nghiệt của chi phí giao dịch thực tế và hàng rào DSR chống chọn ngẫu nhiên."
        )

    report_lines.append(f"\n**sha256 của candidates.json:** `{cand_sha}`")

    # Write report
    report_p = Path(REPORT_PATH)
    report_p.parent.mkdir(parents=True, exist_ok=True)
    report_p.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Report written to {REPORT_PATH}")
    print(f"Candidates written to {CANDIDATES_PATH} (sha256: {cand_sha})")


if __name__ == "__main__":
    main()
