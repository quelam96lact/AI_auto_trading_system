"""Exploration runner for Brief 194 (§5).

Workflow:
- Step 1 (EA): Grid search 18 configs (n in {20, 40}, theta in {35, 40, 45}, k in {2, 3, 4}).
  Logs each trial to docs/research/dot194/trial_ledger.csv.
  Selects best config by highest Sharpe_X.
- Step 2 (Plateau): Checks all parameter neighbors for mean_X > 0 and sharpe_X >= 0.5 * best_sharpe_X.
- Step 3 (EB): Evaluates best config on EB (2020-2022).
  Gates: mean_X > 0 and p < 0.05, Calmar >= 0.86, closed_trades >= 100.
  Logs to docs/research/dot194/trial_ledger.csv with period='EB'.
- Step 4 (DSR): Calls compute_step4_dsr with n_trials = len(ea_sharpes) + 26. Gate: DSR >= 0.95.
- Exports candidates.json and exploration_report.md.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from scripts.research188_core import deflated_sharpe
from scripts.research188_ledger import evaluate_and_log
from scripts.research191_data import load_exchanges, load_stocks
from scripts.research191_exits import assert_ledger_safety
from scripts.research192_core import load_sessions
from scripts.research193_core import (
    calculate_rotation_metrics,
    ew_benchmark,
    get_rebalance_dates,
)
from scripts.research193_explore import filter_rebalance_dates, get_parameter_neighbors
from scripts.research194_core import (
    MIN_TURNOVER_194,
    simulate_swing_portfolio,
)

IDEA_ID = "I1_WKMA_RSI_ATR"
IDEA_SHA = "I1_WKMA_RSI_ATR"

GRID = {
    "n": [20, 40],
    "theta": [35, 40, 45],
    "k": [2, 3, 4],
}

EA_FIRST_MONTH = (2016, 12)
EA_LAST_MONTH = (2019, 12)

EB_FIRST_MONTH = (2019, 12)
EB_LAST_MONTH = (2022, 12)

LEDGER_PATH = Path("docs/research/dot194/trial_ledger.csv")
CANDIDATES_PATH = Path("docs/research/dot194/candidates.json")
REPORT_PATH = Path("docs/research/dot194/exploration_report.md")


def compute_step4_dsr(
    sharpe_x: float,
    n_months: int,
    skew: float,
    kurt: float,
    ea_sharpes: list[float],
) -> float:
    """Compute Step 4 Deflated Sharpe Ratio (§4, §5).

    n_trials = len(ea_sharpes) + 26 (18 + 26 = 44).
    sr_trials_var = var(ea_sharpes, ddof=1).
    """
    n_trials = len(ea_sharpes) + 26
    sr_trials_var = float(np.var(ea_sharpes, ddof=1)) if len(ea_sharpes) > 1 else 0.0
    return deflated_sharpe(
        sr=sharpe_x,
        n_obs=n_months,
        skew=skew,
        kurt=kurt,
        n_trials=n_trials,
        sr_trials_var=sr_trials_var,
    )


def run_exploration(
    data_dir: Path | str = "data/research194/explore",
    ledger_path: Path | str = LEDGER_PATH,
    candidates_path: Path | str = CANDIDATES_PATH,
    report_path: Path | str = REPORT_PATH,
) -> dict[str, Any]:
    """Execute exploration workflow (§5).

    First line enforces assert_ledger_safety(ledger_path).
    """
    assert_ledger_safety(ledger_path)

    d_dir = Path(data_dir)
    print(f"Loading data from {d_dir}...")
    sessions = load_sessions(d_dir, end=date(2022, 12, 30))
    stocks = load_stocks(d_dir, end=date(2022, 12, 30))
    exchanges = load_exchanges(d_dir)

    all_rebal = get_rebalance_dates(sessions)
    ea_rebal = filter_rebalance_dates(all_rebal, EA_FIRST_MONTH, EA_LAST_MONTH)
    eb_rebal = filter_rebalance_dates(all_rebal, EB_FIRST_MONTH, EB_LAST_MONTH)

    print(f"Calculating EW benchmarks (EA: {len(ea_rebal)-1} months, EB: {len(eb_rebal)-1} months)...")
    ea_ew = ew_benchmark(ea_rebal, stocks, sessions, min_turnover=MIN_TURNOVER_194)
    eb_ew = ew_benchmark(eb_rebal, stocks, sessions, min_turnover=MIN_TURNOVER_194)

    Path(ledger_path).parent.mkdir(parents=True, exist_ok=True)
    Path(candidates_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)

    # Step 1: EA grid search (ordered by n, then theta, then k)
    ea_results: list[dict[str, Any]] = []
    all_ea_sharpes: list[float] = []

    print("\n--- Running EA (18 configs) ---")
    for n_val in GRID["n"]:
        for theta_val in GRID["theta"]:
            for k_val in GRID["k"]:
                params = {"n": n_val, "theta": theta_val, "k": k_val}

                sim = simulate_swing_portfolio(
                    sessions=sessions,
                    bars_by_symbol=stocks,
                    exchanges=exchanges,
                    rebalance_dates=ea_rebal,
                    n=n_val,
                    theta=float(theta_val),
                    k=float(k_val),
                    min_turnover=MIN_TURNOVER_194,
                )

                portfolio_metrics = {
                    "cagr": sim["cagr"],
                    "mdd": sim["mdd"],
                    "calmar": sim["calmar"],
                }
                metrics = calculate_rotation_metrics(
                    monthly_r=sim["monthly_returns"],
                    monthly_ew=ea_ew,
                    rebalance_dates=ea_rebal,
                    portfolio_metrics=portfolio_metrics,
                    seed=194,
                )

                all_ea_sharpes.append(metrics["sharpe_X"])

                # Trade statistics
                trades = sim["closed_trades"]
                n_trades = len(trades)
                win_rate = (
                    sum(1 for t in trades if t.net_return > 0) / n_trades
                    if n_trades > 0
                    else 0.0
                )
                mean_net_ret = (
                    float(np.mean([t.net_return for t in trades]))
                    if n_trades > 0
                    else 0.0
                )
                median_holding = (
                    float(np.median([t.holding_sessions for t in trades]))
                    if n_trades > 0
                    else 0.0
                )
                n_stop = sum(1 for t in trades if t.exit_reason == "STOP")
                n_trend = sum(1 for t in trades if t.exit_reason == "TREND")
                n_end = sum(1 for t in trades if t.exit_reason == "END")

                entry = {
                    "idea_id": IDEA_ID,
                    "params": params,
                    "period": "EA",
                    "sim": sim,
                    "metrics": metrics,
                    "n_trades": n_trades,
                    "win_rate": win_rate,
                    "mean_net_ret": mean_net_ret,
                    "median_holding": median_holding,
                    "n_stop": n_stop,
                    "n_trend": n_trend,
                    "n_end": n_end,
                }
                ea_results.append(entry)

                # Log to trial ledger
                ledger_metrics = {
                    "n": metrics["n"],
                    "mean_net": metrics["mean_X"],
                    "sharpe": metrics["sharpe_X"],
                    "p": metrics["p"],
                    "cagr": metrics["cagr"],
                    "mdd": metrics["mdd"],
                    "calmar": metrics["calmar"],
                }
                evaluate_and_log(
                    idea_id=IDEA_ID,
                    idea_fn_or_sha=IDEA_SHA,
                    params=params,
                    market="stock",
                    period="EA",
                    metrics=ledger_metrics,
                    ledger_path=str(ledger_path),
                )

    # Select best config by highest Sharpe_X
    best_ea = max(ea_results, key=lambda r: r["metrics"]["sharpe_X"])
    best_params = best_ea["params"]
    print(
        f"\nSelected EA best config: {best_params} "
        f"(Sharpe_X={best_ea['metrics']['sharpe_X']:.3f}, "
        f"mean_X={best_ea['metrics']['mean_X']*100:.2f}%)"
    )

    # Step 2: Plateau check
    neighbors = get_parameter_neighbors(GRID, best_params)
    ea_by_params = {json.dumps(r["params"], sort_keys=True): r for r in ea_results}

    target_sharpe = best_ea["metrics"]["sharpe_X"] * 0.5
    all_passed_plateau = True
    neighbor_details: list[str] = []

    for nb in neighbors:
        nb_key = json.dumps(nb, sort_keys=True)
        nb_res = ea_by_params.get(nb_key)
        if nb_res is None:
            all_passed_plateau = False
            neighbor_details.append(f"{nb}: N/A")
            continue

        nb_m = nb_res["metrics"]
        if nb_m["mean_X"] <= 0 or nb_m["sharpe_X"] < target_sharpe:
            all_passed_plateau = False
            neighbor_details.append(
                f"{nb}: mean_X={nb_m['mean_X']*100:.2f}%, sharpe_X={nb_m['sharpe_X']:.3f}"
            )

    eb_res: dict[str, Any] | None = None
    eb_fail_reasons: list[str] = []
    dsr_val: float | None = None
    candidates: list[dict[str, Any]] = []

    if not all_passed_plateau:
        print(f"REJECTED at Step 2 (Plateau): {', '.join(neighbor_details)}")
        status_conclusion = f"Trượt cao nguyên: {', '.join(neighbor_details)}"
    else:
        print(f"PASSED Step 2 (Plateau): all {len(neighbors)} neighbors passed.")

        # Step 3: EB evaluation
        print(f"\n--- Running EB for {best_params} ---")
        sim_eb = simulate_swing_portfolio(
            sessions=sessions,
            bars_by_symbol=stocks,
            exchanges=exchanges,
            rebalance_dates=eb_rebal,
            n=int(best_params["n"]),
            theta=float(best_params["theta"]),
            k=float(best_params["k"]),
            min_turnover=MIN_TURNOVER_194,
        )

        portfolio_metrics_eb = {
            "cagr": sim_eb["cagr"],
            "mdd": sim_eb["mdd"],
            "calmar": sim_eb["calmar"],
        }
        metrics_eb = calculate_rotation_metrics(
            monthly_r=sim_eb["monthly_returns"],
            monthly_ew=eb_ew,
            rebalance_dates=eb_rebal,
            portfolio_metrics=portfolio_metrics_eb,
            seed=194,
        )

        trades_eb = sim_eb["closed_trades"]
        n_trades_eb = len(trades_eb)
        win_rate_eb = (
            sum(1 for t in trades_eb if t.net_return > 0) / n_trades_eb
            if n_trades_eb > 0
            else 0.0
        )
        mean_net_ret_eb = (
            float(np.mean([t.net_return for t in trades_eb]))
            if n_trades_eb > 0
            else 0.0
        )
        median_holding_eb = (
            float(np.median([t.holding_sessions for t in trades_eb]))
            if n_trades_eb > 0
            else 0.0
        )
        n_stop_eb = sum(1 for t in trades_eb if t.exit_reason == "STOP")
        n_trend_eb = sum(1 for t in trades_eb if t.exit_reason == "TREND")
        n_end_eb = sum(1 for t in trades_eb if t.exit_reason == "END")

        eb_res = {
            "idea_id": IDEA_ID,
            "params": best_params,
            "period": "EB",
            "sim": sim_eb,
            "metrics": metrics_eb,
            "n_trades": n_trades_eb,
            "win_rate": win_rate_eb,
            "mean_net_ret": mean_net_ret_eb,
            "median_holding": median_holding_eb,
            "n_stop": n_stop_eb,
            "n_trend": n_trend_eb,
            "n_end": n_end_eb,
        }

        # Log EB to trial ledger
        ledger_metrics_eb = {
            "n": metrics_eb["n"],
            "mean_net": metrics_eb["mean_X"],
            "sharpe": metrics_eb["sharpe_X"],
            "p": metrics_eb["p"],
            "cagr": metrics_eb["cagr"],
            "mdd": metrics_eb["mdd"],
            "calmar": metrics_eb["calmar"],
        }
        evaluate_and_log(
            idea_id=IDEA_ID,
            idea_fn_or_sha=IDEA_SHA,
            params=best_params,
            market="stock",
            period="EB",
            metrics=ledger_metrics_eb,
            ledger_path=str(ledger_path),
        )

        # Check EB gates: mean_X > 0 and p < 0.05, Calmar >= 0.86, closed_trades >= 100
        if metrics_eb["mean_X"] <= 0:
            eb_fail_reasons.append(f"mean_X={metrics_eb['mean_X']*100:.2f}% <= 0")
        if metrics_eb["p"] >= 0.05:
            eb_fail_reasons.append(f"p={metrics_eb['p']:.4f} >= 0.05")
        if metrics_eb["calmar"] < 0.86:
            eb_fail_reasons.append(f"calmar={metrics_eb['calmar']:.2f} < 0.86")
        if n_trades_eb < 100:
            eb_fail_reasons.append(f"closed_trades={n_trades_eb} < 100")

        if eb_fail_reasons:
            print(f"REJECTED at Step 3 (EB): {', '.join(eb_fail_reasons)}")
            status_conclusion = f"Trượt EB: {', '.join(eb_fail_reasons)}"
        else:
            print("PASSED Step 3 (EB)!")

            # Step 4: DSR
            m_ea = best_ea["metrics"]
            dsr_val = compute_step4_dsr(
                sharpe_x=m_ea["sharpe_X"],
                n_months=m_ea["n"],
                skew=m_ea["skew"],
                kurt=m_ea["kurt"],
                ea_sharpes=all_ea_sharpes,
            )
            print(f"Step 4 DSR on EA = {dsr_val:.4f} (gate >= 0.95)")
            if dsr_val >= 0.95:
                status_conclusion = "Đạt toàn bộ 4 bước"
                candidates.append({
                    "idea_id": IDEA_ID,
                    "params": best_params,
                    "ea_sharpe_x": m_ea["sharpe_X"],
                    "eb_sharpe_x": metrics_eb["sharpe_X"],
                    "dsr": dsr_val,
                })
            else:
                status_conclusion = f"Trượt Bước 4 (DSR={dsr_val:.4f} < 0.95)"

    # Export candidates.json
    with open(candidates_path, "w", encoding="utf-8") as f:
        json.dump(candidates, f, indent=2)

    cand_sha = hashlib.sha256(Path(candidates_path).read_bytes()).hexdigest()
    print(f"\nCandidates written to {candidates_path} (count: {len(candidates)}, sha256: {cand_sha})")

    # Generate exploration_report.md
    report_lines = [
        "# Báo Cáo Khám Phá: Xu Hướng Tuần + RSI Ngày + ATR Chandelier Stop (Brief 194)",
        "",
        "> [!IMPORTANT]",
        "> **CẢNH BÁO THIÊN LỆCH SỐNG SÓT (SURVIVORSHIP BIAS):**",
        "> Dữ liệu `stocks_daily` gần như không có mã đã huỷ niêm yết. Mã huỷ thường sụt dài, tức là loại mã mà bộ lọc xu hướng tránh được. Như vậy phép so với EW thiên vị nhẹ cho EW, bất lợi tương đối cho chiến lược.",
        "",
        "- **Tổng số thử nghiệm EA đã ghi sổ:** 18 cấu hình.",
        f"- **Tổng số thử nghiệm EB đã ghi sổ:** {1 if eb_res is not None else 0} cấu hình.",
        f"- **Số ứng viên vượt qua toàn bộ 4 bước:** {len(candidates)}.",
        f"- **SHA256 của `candidates.json`:** `{cand_sha}`",
        "",
        "---",
        "",
        "## 1. Kết Quả Chiến Lược Qua Các Bước",
        "",
        f"- **Ý tưởng:** `{IDEA_ID}`",
        f"- **Cấu hình chọn (EA):** `{best_params}`",
        f"- **Kết luận / Lý do loại:** {status_conclusion}",
        "",
        "### Bảng Chỉ Số EA và EB Của Cấu Hình Được Chọn",
        "",
        "| Giai đoạn | Số tháng | Lãi tháng TB (R_m) | Lãi tháng EW (EW_m) | Vượt trội TB (mean_X) | Sharpe_X | p | CAGR | MDD | Calmar | CAGR EW | Lệnh đóng | Thắng % | Lãi ròng TB/lệnh | Median giữ | STOP / TREND / END | Vốn trong CP | Phí / năm (% NAV) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    m_ea = best_ea["metrics"]
    s_ea = best_ea["sim"]
    ea_line = (
        f"| **EA** | {m_ea['n']} | {m_ea['mean_R']*100:.2f}% | {m_ea['mean_EW']*100:.2f}% | "
        f"{m_ea['mean_X']*100:.2f}% | {m_ea['sharpe_X']:.3f} | {m_ea['p']:.4f} | "
        f"{m_ea['cagr']*100:.2f}% | {m_ea['mdd']*100:.2f}% | {m_ea['calmar']:.2f} | "
        f"{m_ea['cagr_ew']*100:.2f}% | {best_ea['n_trades']} | {best_ea['win_rate']*100:.1f}% | "
        f"{best_ea['mean_net_ret']*100:.2f}% | {best_ea['median_holding']:.1f} | "
        f"{best_ea['n_stop']} / {best_ea['n_trend']} / {best_ea['n_end']} | "
        f"{s_ea['avg_stock_exposure']*100:.1f}% | {s_ea['annual_fee_pct']*100:.2f}% |"
    )
    report_lines.append(ea_line)

    if eb_res is not None:
        m_eb = eb_res["metrics"]
        s_eb = eb_res["sim"]
        eb_line = (
            f"| **EB** | {m_eb['n']} | {m_eb['mean_R']*100:.2f}% | {m_eb['mean_EW']*100:.2f}% | "
            f"{m_eb['mean_X']*100:.2f}% | {m_eb['sharpe_X']:.3f} | {m_eb['p']:.4f} | "
            f"{m_eb['cagr']*100:.2f}% | {m_eb['mdd']*100:.2f}% | {m_eb['calmar']:.2f} | "
            f"{m_eb['cagr_ew']*100:.2f}% | {eb_res['n_trades']} | {eb_res['win_rate']*100:.1f}% | "
            f"{eb_res['mean_net_ret']*100:.2f}% | {eb_res['median_holding']:.1f} | "
            f"{eb_res['n_stop']} / {eb_res['n_trend']} / {eb_res['n_end']} | "
            f"{s_eb['avg_stock_exposure']*100:.1f}% | {s_eb['annual_fee_pct']*100:.2f}% |"
        )
        report_lines.append(eb_line)

    dsr_str = f"{dsr_val:.4f}" if dsr_val is not None else "không tính"
    report_lines.extend([
        "",
        f"- **Cao nguyên:** {'ĐẠT' if all_passed_plateau else 'TRƯỢT'}",
        f"- **DSR (EA):** {dsr_str}",
        "",
        "---",
        "",
        "## 2. Bảng Phụ Cho Cả 18 Cấu Hình EA (§5)",
        "",
        "| n | θ | k | Vượt trội TB (mean_X) | Sharpe_X (tháng) | Median số phiên giữ | Lãi ròng TB / lệnh |",
        "|---|---|---|---|---|---|---|",
    ])

    for r in ea_results:
        p = r["params"]
        m = r["metrics"]
        report_lines.append(
            f"| {p['n']} | {p['theta']} | {p['k']} | {m['mean_X']*100:.2f}% | "
            f"{m['sharpe_X']:.3f} | {r['median_holding']:.1f} | {r['mean_net_ret']*100:.2f}% |"
        )

    report_lines.extend([
        "",
        "---",
        "",
        "## 3. Danh Sách Ứng Viên Chốt",
        "",
    ])

    if candidates:
        for c in candidates:
            report_lines.append(f"- Ứng viên: `{c['idea_id']}` ({c['params']}), DSR={c['dsr']:.4f}")
    else:
        report_lines.extend([
            "> [!NOTE]",
            "> **Không có ứng viên nào vượt qua toàn bộ 4 bước lọc khắt khe (0 ứng viên là kết quả hợp lệ theo §5).**",
            "> Toàn bộ cấu hình được ghi nhận là phép đo âm để bảo vệ vốn và không nới lỏng tiêu chuẩn.",
        ])

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")

    print(f"Exploration report written to {report_path}")

    return {
        "ea_results": ea_results,
        "best_ea": best_ea,
        "all_passed_plateau": all_passed_plateau,
        "eb_res": eb_res,
        "candidates": candidates,
        "cand_sha": cand_sha,
    }


if __name__ == "__main__":
    run_exploration()
