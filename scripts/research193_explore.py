"""Exploration runner for Brief 193 (Low Volatility Monthly Rotation Portfolio).

Workflow (§5):
1. Step 1 (EA): Grid search 2 ideas (LOWVOL: 9 configs, LOWMAX: 9 configs = 18 trials).
   Log every trial to trial_ledger.csv with period='EA'.
   Select config with highest sharpe_X.
2. Step 2 (Plateau): Verify +/- 1 step neighbors on each parameter have mean_X > 0
   and sharpe_X >= 50% best sharpe_X.
3. Step 3 (EB): Evaluate selected config on EB (2019-12-31 -> 2022-12-30, 36 months).
   Gates: mean_X > 0, p < 0.05, Calmar >= 0.86, avg_syms_held >= 0.8 * N.
4. Step 4 (DSR): compute_step4_dsr on EA X_m with n_trials = 18 + 25 = 43 (DSR >= 0.95).
5. Candidates: Export candidates.json and exploration_report.md.
"""

from __future__ import annotations

import hashlib
import io
import itertools
import json
import sys
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
    MIN_TURNOVER_193,
    calculate_rotation_metrics,
    ew_benchmark,
    get_rebalance_dates,
    simulate_rotation,
)

LEDGER_PATH = "docs/research/dot193/trial_ledger.csv"
CANDIDATES_PATH = "docs/research/dot193/candidates.json"
REPORT_PATH = "docs/research/dot193/exploration_report.md"

# EA: first rebalance L(01/2017), last rebalance L(12/2019) (35 months)
EA_FIRST_MONTH = (2017, 1)
EA_LAST_MONTH = (2019, 12)

# EB: first rebalance L(12/2019), last rebalance L(12/2022) (36 months)
EB_FIRST_MONTH = (2019, 12)
EB_LAST_MONTH = (2022, 12)

IDEAS_CONFIG = {
    "I1_LOWVOL": {
        "idea_type": "LOWVOL",
        "param_name": "L",
        "grid": {
            "L": [60, 120, 250],
            "N": [10, 15, 20],
        },
    },
    "I2_LOWMAX": {
        "idea_type": "LOWMAX",
        "param_name": "W",
        "grid": {
            "W": [20, 60, 120],
            "N": [10, 15, 20],
        },
    },
}


def filter_rebalance_dates(
    all_rebal: list[date],
    first_ym: tuple[int, int],
    last_ym: tuple[int, int],
) -> list[date]:
    """Filter rebalance dates L(M) between first_ym and last_ym inclusive."""
    out = []
    for d in all_rebal:
        ym = (d.year, d.month)
        if first_ym <= ym <= last_ym:
            out.append(d)
    return out


def get_parameter_neighbors(
    grid: dict[str, list[Any]],
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Get all +/- 1 step neighbors on each parameter independently."""
    neighbors: list[dict[str, Any]] = []
    for param_name, values in grid.items():
        curr_val = params[param_name]
        idx = values.index(curr_val)
        if idx > 0:
            nb = dict(params)
            nb[param_name] = values[idx - 1]
            neighbors.append(nb)
        if idx < len(values) - 1:
            nb = dict(params)
            nb[param_name] = values[idx + 1]
            neighbors.append(nb)
    return neighbors


def compute_step4_dsr(
    sharpe_x: float,
    n_months: int,
    skew: float,
    kurt: float,
    ea_sharpes: list[float],
) -> float:
    """Compute Step 4 Deflated Sharpe Ratio (§4, §5).

    n_trials = len(ea_sharpes) + 25 (e.g. 18 + 25 = 43).
    sr_trials_var = var(ea_sharpes, ddof=1).
    """
    n_trials = len(ea_sharpes) + 25
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
    data_dir: Path | str = "data/research193/explore",
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

    # Compute EW benchmark for EA and EB
    print(f"Calculating EW benchmarks (EA: {len(ea_rebal)-1} months, EB: {len(eb_rebal)-1} months)...")
    ea_ew = ew_benchmark(ea_rebal, stocks, sessions, min_turnover=MIN_TURNOVER_193)
    eb_ew = ew_benchmark(eb_rebal, stocks, sessions, min_turnover=MIN_TURNOVER_193)

    Path(ledger_path).parent.mkdir(parents=True, exist_ok=True)
    Path(candidates_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)

    ea_results: dict[str, list[dict[str, Any]]] = {}
    selected_configs: dict[str, dict[str, Any]] = {}
    idea_status: dict[str, dict[str, Any]] = {}
    all_ea_sharpes: list[float] = []

    # Total EA trials: 9 + 9 = 18
    # Step 1: EA grid search
    for idea_id, cfg in IDEAS_CONFIG.items():
        grid = cfg["grid"]
        idea_type = cfg["idea_type"]
        param_name = cfg["param_name"]
        keys = list(grid.keys())
        combos = [dict(zip(keys, v)) for v in itertools.product(*(grid[k] for k in keys))]

        ea_results[idea_id] = []
        print(f"\n--- Running EA for {idea_id} ({len(combos)} configs) ---")

        for p in combos:
            lookback = int(p[param_name])
            n_stocks = int(p["N"])

            sim = simulate_rotation(
                rebalance_dates=ea_rebal,
                bars_by_symbol=stocks,
                sessions=sessions,
                exchanges=exchanges,
                idea_type=idea_type,
                lookback=lookback,
                n_stocks=n_stocks,
                min_turnover=MIN_TURNOVER_193,
            )

            metrics = calculate_rotation_metrics(
                monthly_r=sim["monthly_returns"],
                monthly_ew=ea_ew,
                rebalance_dates=ea_rebal,
                portfolio_metrics=sim,
                seed=193,
            )

            all_ea_sharpes.append(metrics["sharpe_X"])

            entry = {
                "idea_id": idea_id,
                "params": p,
                "period": "EA",
                "sim": sim,
                "metrics": metrics,
            }
            ea_results[idea_id].append(entry)

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
                idea_id=idea_id,
                idea_fn_or_sha=idea_type,
                params=p,
                market="stock",
                period="EA",
                metrics=ledger_metrics,
                ledger_path=str(ledger_path),
            )

        # Select best config: highest sharpe_X
        best_cfg = max(ea_results[idea_id], key=lambda r: r["metrics"]["sharpe_X"])
        selected_configs[idea_id] = best_cfg
        print(f"[{idea_id}] Selected EA best config: {best_cfg['params']} (Sharpe_X={best_cfg['metrics']['sharpe_X']:.3f}, mean_X={best_cfg['metrics']['mean_X']*100:.2f}%)")

    # Step 2: Plateau check
    passed_plateau: dict[str, dict[str, Any]] = {}
    for idea_id, best_cfg in selected_configs.items():
        grid = IDEAS_CONFIG[idea_id]["grid"]
        neighbors = get_parameter_neighbors(grid, best_cfg["params"])
        ea_by_params = {json.dumps(r["params"], sort_keys=True): r for r in ea_results[idea_id]}

        target_sharpe = best_cfg["metrics"]["sharpe_X"] * 0.5
        all_passed = True
        neighbor_details = []

        for nb in neighbors:
            nb_key = json.dumps(nb, sort_keys=True)
            nb_res = ea_by_params.get(nb_key)
            if nb_res is None:
                all_passed = False
                neighbor_details.append(f"{nb}: N/A")
                continue

            nb_m = nb_res["metrics"]
            if nb_m["mean_X"] <= 0 or nb_m["sharpe_X"] < target_sharpe:
                all_passed = False
                neighbor_details.append(f"{nb}: mean_X={nb_m['mean_X']*100:.2f}%, sharpe_X={nb_m['sharpe_X']:.3f}")

        if all_passed:
            print(f"[{idea_id}] -> Đạt cao nguyên ({len(neighbors)} láng giềng đều đạt)")
            passed_plateau[idea_id] = best_cfg
        else:
            print(f"[{idea_id}] REJECTED at Step 2 (Plateau): {', '.join(neighbor_details)}")
            idea_status[idea_id] = {
                "status": "REJECTED",
                "step": "Step 2 (Plateau)",
                "reason": f"Không đạt cao nguyên: {', '.join(neighbor_details)}",
            }

    # Step 3: EB evaluation
    eb_results: dict[str, dict[str, Any]] = {}
    passed_eb: dict[str, dict[str, Any]] = {}

    for idea_id, best_cfg in passed_plateau.items():
        p = best_cfg["params"]
        cfg = IDEAS_CONFIG[idea_id]
        idea_type = cfg["idea_type"]
        param_name = cfg["param_name"]
        lookback = int(p[param_name])
        n_stocks = int(p["N"])

        print(f"\n--- Running EB for {idea_id} ({p}) ---")
        sim_eb = simulate_rotation(
            rebalance_dates=eb_rebal,
            bars_by_symbol=stocks,
            sessions=sessions,
            exchanges=exchanges,
            idea_type=idea_type,
            lookback=lookback,
            n_stocks=n_stocks,
            min_turnover=MIN_TURNOVER_193,
        )

        metrics_eb = calculate_rotation_metrics(
            monthly_r=sim_eb["monthly_returns"],
            monthly_ew=eb_ew,
            rebalance_dates=eb_rebal,
            portfolio_metrics=sim_eb,
            seed=193,
        )

        eb_entry = {
            "idea_id": idea_id,
            "params": p,
            "period": "EB",
            "sim": sim_eb,
            "metrics": metrics_eb,
        }
        eb_results[idea_id] = eb_entry

        # Log to trial ledger with period='EB'
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
            idea_id=idea_id,
            idea_fn_or_sha=idea_type,
            params=p,
            market="stock",
            period="EB",
            metrics=ledger_metrics_eb,
            ledger_path=str(ledger_path),
        )

        # Check EB gates (§5)
        # 1. mean_X > 0 and p < 0.05
        # 2. Calmar >= 0.86
        # 3. avg_syms_held >= 0.8 * N
        eb_fail_reasons = []
        if metrics_eb["mean_X"] <= 0:
            eb_fail_reasons.append(f"mean_X={metrics_eb['mean_X']*100:.2f}% <= 0")
        if metrics_eb["p"] >= 0.05:
            eb_fail_reasons.append(f"p={metrics_eb['p']:.4f} >= 0.05")
        if metrics_eb["calmar"] < 0.86:
            eb_fail_reasons.append(f"calmar={metrics_eb['calmar']:.2f} < 0.86")
        if sim_eb["avg_syms_held"] < 0.8 * n_stocks:
            eb_fail_reasons.append(f"avg_syms_held={sim_eb['avg_syms_held']:.1f} < {0.8*n_stocks:.1f}")

        if not eb_fail_reasons:
            print(f"[{idea_id}] -> Đạt toàn bộ cổng EB!")
            passed_eb[idea_id] = eb_entry
        else:
            print(f"[{idea_id}] REJECTED at Step 3 (EB): {', '.join(eb_fail_reasons)}")
            idea_status[idea_id] = {
                "status": "REJECTED",
                "step": "Step 3 (EB gates)",
                "reason": f"Trượt EB: {', '.join(eb_fail_reasons)}",
            }

    # Step 4: DSR for ideas passing EB
    candidates: list[dict[str, Any]] = []
    for idea_id, eb_res in passed_eb.items():
        best_ea = selected_configs[idea_id]
        m_ea = best_ea["metrics"]
        dsr_val = compute_step4_dsr(
            sharpe_x=m_ea["sharpe_X"],
            n_months=m_ea["n"],
            skew=m_ea["skew"],
            kurt=m_ea["kurt"],
            ea_sharpes=all_ea_sharpes,
        )
        print(f"[{idea_id}] DSR on EA = {dsr_val:.4f} (threshold >= 0.95)")
        if dsr_val >= 0.95:
            cand = {
                "idea_id": idea_id,
                "params": best_ea["params"],
                "ea_sharpe_x": m_ea["sharpe_X"],
                "eb_sharpe_x": eb_res["metrics"]["sharpe_X"],
                "dsr": dsr_val,
            }
            candidates.append(cand)
            idea_status[idea_id] = {
                "status": "ACCEPTED",
                "step": "Passed all gates",
                "reason": "Đạt 4 bước",
                "dsr": dsr_val,
            }
        else:
            idea_status[idea_id] = {
                "status": "REJECTED",
                "step": "Step 4 (DSR)",
                "reason": f"DSR={dsr_val:.4f} < 0.95",
                "dsr": dsr_val,
            }

    # Export candidates.json
    with open(candidates_path, "w", encoding="utf-8") as f:
        json.dump(candidates, f, indent=2)

    cand_sha = hashlib.sha256(Path(candidates_path).read_bytes()).hexdigest()
    print(f"\nCandidates written to {candidates_path} (count: {len(candidates)}, sha256: {cand_sha})")

    # Generate exploration_report.md
    report_lines = [
        "# Báo Cáo Khám Phá Danh Mục Biến Động Thấp Xoay Vòng Tháng (Brief 193)",
        "",
        "> [!IMPORTANT]",
        "> **CẢNH BÁO THIÊN LỆCH SỐNG SÓT (SURVIVORSHIP BIAS):**",
        "> Dữ liệu `stocks_daily` gần như không có mã đã huỷ niêm yết; theo quyết định của chủ dự án và spec H ngày 25/10, nghiên cứu không dùng mã huỷ. Mã huỷ thường là mã biến động cao và lỗ nặng; khi thiếu chúng, nhóm biến động cao trông tốt hơn thật, nên phép so sánh đang bất lợi tương đối cho chiến lược biến động thấp.",
        "",
        "- **Tổng số thử nghiệm EA đã ghi sổ:** 18 cấu hình.",
        f"- **Tổng số thử nghiệm EB đã ghi sổ:** {len(eb_results)} cấu hình.",
        f"- **Số ứng viên vượt qua toàn bộ 4 bước:** {len(candidates)}.",
        f"- **SHA256 của `candidates.json`:** `{cand_sha}`",
        "",
        "---",
        "",
        "## 1. Kết Quả Từng Ý Tưởng Qua Các Bước",
        "",
    ]

    for idea_id in IDEAS_CONFIG:
        st = idea_status.get(idea_id, {"status": "UNKNOWN", "reason": "Chưa xử lý"})
        report_lines.append(f"### {idea_id}")
        report_lines.append(f"- **Trạng thái:** `{st['status']}`")
        report_lines.append(f"- **Lý do loại / Kết luận:** {st.get('reason', '')}")

        best_ea = selected_configs.get(idea_id)
        if best_ea:
            p = best_ea["params"]
            m_ea = best_ea["metrics"]
            s_ea = best_ea["sim"]
            report_lines.append(f"- **Cấu hình chọn (EA):** `{p}`")
            report_lines.append("")
            report_lines.append("| Giai đoạn | Số tháng | Lãi tháng TB (R_m) | Lãi tháng EW (EW_m) | Vượt trội TB (mean_X) | Sharpe_X | p | CAGR | MDD | Calmar | CAGR EW | Turnover tháng TB | Phí / năm (% NAV) | Mã TB / tháng |")
            report_lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
            report_lines.append(
                f"| **EA** | {m_ea['n']} | {m_ea['mean_R']*100:.2f}% | {m_ea['mean_EW']*100:.2f}% | "
                f"{m_ea['mean_X']*100:.2f}% | {m_ea['sharpe_X']:.3f} | {m_ea['p']:.4f} | "
                f"{m_ea['cagr']*100:.2f}% | {m_ea['mdd']*100:.2f}% | {m_ea['calmar']:.2f} | "
                f"{m_ea['cagr_ew']*100:.2f}% | {s_ea['mean_turnover']*100:.2f}% | {s_ea['annual_fee_pct']*100:.2f}% | {s_ea['avg_syms_held']:.1f} |"
            )

            eb_res = eb_results.get(idea_id)
            if eb_res:
                m_eb = eb_res["metrics"]
                s_eb = eb_res["sim"]
                report_lines.append(
                    f"| **EB** | {m_eb['n']} | {m_eb['mean_R']*100:.2f}% | {m_eb['mean_EW']*100:.2f}% | "
                    f"{m_eb['mean_X']*100:.2f}% | {m_eb['sharpe_X']:.3f} | {m_eb['p']:.4f} | "
                    f"{m_eb['cagr']*100:.2f}% | {m_eb['mdd']*100:.2f}% | {m_eb['calmar']:.2f} | "
                    f"{m_eb['cagr_ew']*100:.2f}% | {s_eb['mean_turnover']*100:.2f}% | {s_eb['annual_fee_pct']*100:.2f}% | {s_eb['avg_syms_held']:.1f} |"
                )

            report_lines.append("")
            if idea_id in passed_plateau:
                report_lines.append("- **Cao nguyên:** ĐẠT (tất cả các láng giềng ±1 bước đều có mean_X > 0 và Sharpe_X >= 50%).")
            else:
                report_lines.append("- **Cao nguyên:** TRƯỢT.")

            if "dsr" in st:
                report_lines.append(f"- **DSR (EA):** {st['dsr']:.4f}")
            else:
                report_lines.append("- **DSR (EA):** không tính")
        report_lines.append("")

    report_lines.extend([
        "---",
        "",
        "## 2. Danh Sách Ứng Viên Chốt",
        "",
    ])
    if candidates:
        for cand in candidates:
            report_lines.append(f"- `{cand['idea_id']}`: {cand['params']} (DSR: {cand['dsr']:.4f})")
    else:
        report_lines.extend([
            "> [!NOTE]",
            "> **Không có ứng viên nào vượt qua toàn bộ 4 bước lọc khắt khe (0 ứng viên là kết quả hợp lệ theo §5).**",
            "> Toàn bộ các ý tưởng được ghi nhận là phép đo âm để bảo vệ vốn và không nới lỏng tiêu chuẩn.",
        ])

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")

    return {
        "ea_results": ea_results,
        "selected_configs": selected_configs,
        "passed_plateau": passed_plateau,
        "eb_results": eb_results,
        "candidates": candidates,
        "candidates_sha": cand_sha,
    }


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    run_exploration()
