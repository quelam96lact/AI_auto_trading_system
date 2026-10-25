"""Exploration runner for Brief 192 (Calendar effects: TOM and PREHOL).

Workflow (§5):
1. Step 1 (EA): Grid search 2 ideas (TOM: 9 configs, PREHOL: 9 configs = 18 trials).
   Log every trial to trial_ledger.csv with period='EA'.
   Select config with highest Sharpe among configs with n >= 100.
2. Step 2 (Plateau): Verify +/- 1 step neighbors on each param have mean_net > 0
   and Sharpe >= 50% best Sharpe.
3. Step 3 (EB): Evaluate selected config on EB (2020-01-01 -> 2022-12-30).
   Check n >= 100, mean_net > 0, bootstrap p < 0.05 (seed=192), Calmar >= 0.86, mean_excess_trim1pct > 0.
4. Step 4 (DSR): Deflated Sharpe Ratio on EA trials with n_trials = 18 + 24 = 42 (DSR >= 0.95).
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

from scripts.research188_core import (
    calculate_trade_metrics,
    deflated_sharpe,
    simulate_portfolio,
)
from scripts.research188_ledger import evaluate_and_log
from scripts.research191_data import (
    load_exchanges,
    load_stocks,
)
from scripts.research191_exits import assert_ledger_safety
from scripts.research192_core import (
    generate_calendar_trades,
    get_prehol_windows,
    get_tom_windows,
    load_sessions,
    time_baseline_excess,
)
from trading.stock_study import bootstrap_by_month

LEDGER_PATH = "docs/research/dot192/trial_ledger.csv"
CANDIDATES_PATH = "docs/research/dot192/candidates.json"
REPORT_PATH = "docs/research/dot192/exploration_report.md"

EA_START = date(2016, 1, 4)
EA_END = date(2019, 12, 31)

EB_START = date(2020, 1, 1)
EB_END = date(2022, 12, 30)

IDEAS_CONFIG = {
    "I1_TOM": {
        "grid": {
            "k": [1, 2, 3],
            "m": [2, 3, 4],
        },
    },
    "I2_PREHOL": {
        "grid": {
            "n": [2, 3, 4],
            "q": [1, 2, 3],
        },
    },
}


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


def compute_bootstrap_p(trades: list[Any], seed: int = 192) -> float:
    """Bootstrap p-value by month with custom seed 192 (§5)."""
    if not trades:
        return 1.0
    by_month: dict[tuple[int, int], list[float]] = {}
    for t in trades:
        m_key = (t.entry_ts.year, t.entry_ts.month)
        by_month.setdefault(m_key, []).append(t.net_return)

    res = bootstrap_by_month(
        by_month, n=2000, seed=seed, ci_low_pct=0.05, ci_high_pct=0.95
    )
    return float(res["p"]) if res.get("p") is not None else 1.0


def calculate_window_stats(
    trades: list[Any],
    windows: list[tuple[date, date, str]],
) -> tuple[int, float]:
    """Calculate number of active windows and average number of symbols per active window."""
    if not trades:
        return 0, 0.0

    trades_by_b: dict[date, list[Any]] = {}
    for t in trades:
        trades_by_b.setdefault(t.entry_ts.date(), []).append(t)

    active_windows = 0
    counts = []
    for b, _e, _wid in windows:
        if b in trades_by_b:
            active_windows += 1
            counts.append(len(trades_by_b[b]))

    avg_syms = float(np.mean(counts)) if counts else 0.0
    return active_windows, avg_syms


def run_windows_for_idea(
    idea_id: str,
    params: dict[str, Any],
    sessions: list[date],
) -> list[tuple[date, date, str]]:
    if idea_id == "I1_TOM":
        return get_tom_windows(sessions, k=int(params["k"]), m=int(params["m"]))
    if idea_id == "I2_PREHOL":
        return get_prehol_windows(sessions, n=int(params["n"]), q=int(params["q"]))
    raise ValueError(f"Unknown idea: {idea_id}")


def run_exploration(
    data_dir: Path | str = "data/research192/explore",
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
    sessions = load_sessions(d_dir, end=EB_END)
    stocks = load_stocks(d_dir, end=EB_END)
    exchanges = load_exchanges(d_dir)

    Path(ledger_path).parent.mkdir(parents=True, exist_ok=True)
    Path(candidates_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)

    ea_results: dict[str, list[dict[str, Any]]] = {}
    selected_configs: dict[str, dict[str, Any]] = {}
    idea_status: dict[str, dict[str, Any]] = {}

    # Total EA trials: 9 + 9 = 18
    # Step 1: EA grid search
    for idea_id, cfg in IDEAS_CONFIG.items():
        grid = cfg["grid"]
        keys = list(grid.keys())
        combos = [
            dict(zip(keys, v)) for v in itertools.product(*(grid[k] for k in keys))
        ]

        ea_results[idea_id] = []
        print(f"\n--- Running EA for {idea_id} ({len(combos)} configs) ---")

        for p in combos:
            windows = run_windows_for_idea(idea_id, p, sessions)
            trades = generate_calendar_trades(
                windows=windows,
                bars_by_symbol=stocks,
                sessions=sessions,
                exchanges=exchanges,
                period_start=EA_START,
                period_end=EA_END,
            )

            metrics = calculate_trade_metrics(trades)
            baseline = time_baseline_excess(trades, stocks, sessions, EA_START, EA_END)
            p_val = compute_bootstrap_p(trades, seed=192)

            # Portfolio simulation (100M VND, 10 slots x 10%)
            port = simulate_portfolio(
                trades,
                market="stock",
                initial_capital=100_000_000.0,
                start_date=EA_START,
                end_date=EA_END,
            )
            act_windows, avg_syms = calculate_window_stats(trades, windows)

            gross_mean = (
                float(np.mean([t.gross_return for t in trades])) if trades else 0.0
            )

            log_entry = {
                "idea_id": idea_id,
                "params": p,
                "period": "EA",
                "n_trades": len(trades),
                "gross_mean": gross_mean,
                "net_mean": metrics["mean_net"],
                "sharpe": metrics["sharpe"],
                "p_value": p_val,
                "cagr": port["cagr"],
                "mdd": port["mdd"],
                "calmar": port["calmar"],
                "mean_excess": baseline["mean_excess"],
                "mean_excess_trim1pct": baseline["mean_excess_trim1pct"],
                "active_windows": act_windows,
                "avg_syms_per_window": avg_syms,
                "trades": trades,
                "windows": windows,
            }
            ea_results[idea_id].append(log_entry)

            # Log to trial ledger
            idea_fn = get_tom_windows if idea_id == "I1_TOM" else get_prehol_windows
            ledger_metrics = {
                "n": len(trades),
                "mean_net": metrics["mean_net"],
                "sharpe": metrics["sharpe"],
                "p": p_val,
                "cagr": port["cagr"],
                "mdd": port["mdd"],
                "calmar": port["calmar"],
            }
            evaluate_and_log(
                idea_id=idea_id,
                idea_fn_or_sha=idea_fn,
                params=p,
                market="stock",
                period="EA",
                metrics=ledger_metrics,
                ledger_path=ledger_path,
            )

        # Select best config: highest Sharpe among n >= 100
        valid_ea = [r for r in ea_results[idea_id] if r["n_trades"] >= 100]
        if not valid_ea:
            max_n = (
                max(r["n_trades"] for r in ea_results[idea_id])
                if ea_results[idea_id]
                else 0
            )
            print(
                f"[{idea_id}] REJECTED at Step 1: No config with n >= 100 (max n={max_n})"
            )
            idea_status[idea_id] = {
                "status": "REJECTED",
                "step": "Step 1 (EA sample size)",
                "reason": f"Thiếu mẫu (không có cấu hình nào n >= 100 trên EA, max n={max_n})",
            }
            continue

        best_cfg = max(valid_ea, key=lambda r: r["sharpe"])
        selected_configs[idea_id] = best_cfg
        print(
            f"[{idea_id}] Selected EA best config: {best_cfg['params']} (Sharpe={best_cfg['sharpe']:.3f}, n={best_cfg['n_trades']})"
        )

    # Step 2: Plateau check for ideas passing Step 1
    passed_plateau: dict[str, dict[str, Any]] = {}
    for idea_id, best_cfg in selected_configs.items():
        grid = IDEAS_CONFIG[idea_id]["grid"]
        neighbors = get_parameter_neighbors(grid, best_cfg["params"])
        ea_by_params = {
            json.dumps(r["params"], sort_keys=True): r for r in ea_results[idea_id]
        }

        target_sharpe = best_cfg["sharpe"] * 0.5
        all_passed = True
        neighbor_details = []

        for nb in neighbors:
            nb_key = json.dumps(nb, sort_keys=True)
            nb_res = ea_by_params.get(nb_key)
            if (
                nb_res is None
                or nb_res["net_mean"] <= 0
                or nb_res["sharpe"] < target_sharpe
            ):
                all_passed = False
                neighbor_details.append(
                    f"{nb}: net_mean={nb_res['net_mean'] if nb_res else 'N/A'}, sharpe={nb_res['sharpe'] if nb_res else 'N/A'}"
                )

        if all_passed:
            print(
                f"[{idea_id}] -> Đạt cao nguyên ({len(neighbors)} láng giềng đều đạt)"
            )
            passed_plateau[idea_id] = best_cfg
        else:
            print(f"[{idea_id}] REJECTED at Step 2 (Plateau): {neighbor_details}")
            idea_status[idea_id] = {
                "status": "REJECTED",
                "step": "Step 2 (Plateau)",
                "reason": f"Không đạt cao nguyên: {', '.join(neighbor_details)}",
            }

    # Step 3: EB evaluation
    eb_results: dict[str, dict[str, Any]] = {}
    passed_eb: dict[str, dict[str, Any]] = {}

    for idea_id, best_cfg in passed_plateau.items():
        print(f"\n--- Running EB for {idea_id} ({best_cfg['params']}) ---")
        p = best_cfg["params"]
        windows = run_windows_for_idea(idea_id, p, sessions)
        trades = generate_calendar_trades(
            windows=windows,
            bars_by_symbol=stocks,
            sessions=sessions,
            exchanges=exchanges,
            period_start=EB_START,
            period_end=EB_END,
        )

        metrics = calculate_trade_metrics(trades)
        baseline = time_baseline_excess(trades, stocks, sessions, EB_START, EB_END)
        p_val = compute_bootstrap_p(trades, seed=192)
        port = simulate_portfolio(
            trades,
            market="stock",
            initial_capital=100_000_000.0,
            start_date=EB_START,
            end_date=EB_END,
        )
        act_windows, avg_syms = calculate_window_stats(trades, windows)
        gross_mean = float(np.mean([t.gross_return for t in trades])) if trades else 0.0

        eb_entry = {
            "idea_id": idea_id,
            "params": p,
            "period": "EB",
            "n_trades": len(trades),
            "gross_mean": gross_mean,
            "net_mean": metrics["mean_net"],
            "sharpe": metrics["sharpe"],
            "p_value": p_val,
            "cagr": port["cagr"],
            "mdd": port["mdd"],
            "calmar": port["calmar"],
            "mean_excess": baseline["mean_excess"],
            "mean_excess_trim1pct": baseline["mean_excess_trim1pct"],
            "active_windows": act_windows,
            "avg_syms_per_window": avg_syms,
            "trades": trades,
            "windows": windows,
        }
        eb_results[idea_id] = eb_entry

        # Log to trial ledger with period='EB'
        idea_fn = get_tom_windows if idea_id == "I1_TOM" else get_prehol_windows
        ledger_metrics = {
            "n": len(trades),
            "mean_net": metrics["mean_net"],
            "sharpe": metrics["sharpe"],
            "p": p_val,
            "cagr": port["cagr"],
            "mdd": port["mdd"],
            "calmar": port["calmar"],
        }
        evaluate_and_log(
            idea_id=idea_id,
            idea_fn_or_sha=idea_fn,
            params=p,
            market="stock",
            period="EB",
            metrics=ledger_metrics,
            ledger_path=ledger_path,
        )

        # Check EB gates (§5)
        # 1. n >= 100
        # 2. net_mean > 0
        # 3. p_value < 0.05
        # 4. calmar >= 0.86
        # 5. mean_excess_trim1pct > 0
        eb_fail_reasons = []
        if len(trades) < 100:
            eb_fail_reasons.append(f"n={len(trades)} < 100")
        if metrics["mean_net"] <= 0:
            eb_fail_reasons.append(f"net_mean={metrics['mean_net']*100:.2f}% <= 0")
        if p_val >= 0.05:
            eb_fail_reasons.append(f"p={p_val:.4f} >= 0.05")
        if port["calmar"] < 0.86:
            eb_fail_reasons.append(f"calmar={port['calmar']:.2f} < 0.86")
        if baseline["mean_excess_trim1pct"] <= 0:
            eb_fail_reasons.append(
                f"mean_excess_trim1pct={baseline['mean_excess_trim1pct']*100:.2f}% <= 0"
            )

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
    # n_trials = EA rows (18) + 24 = 42
    N_TRIALS_DSR = 18 + 24
    candidates: list[dict[str, Any]] = []

    for idea_id, eb_res in passed_eb.items():
        best_ea = selected_configs[idea_id]
        ea_trades = best_ea["trades"]
        # Compute DSR on EA trades
        dsr_val = deflated_sharpe(
            trades=ea_trades,
            n_trials=N_TRIALS_DSR,
        )
        print(f"[{idea_id}] DSR on EA = {dsr_val:.4f} (threshold >= 0.95)")
        if dsr_val >= 0.95:
            cand = {
                "idea_id": idea_id,
                "params": best_ea["params"],
                "ea_sharpe": best_ea["sharpe"],
                "eb_sharpe": eb_res["sharpe"],
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
    print(
        f"\nCandidates written to {candidates_path} (count: {len(candidates)}, sha256: {cand_sha})"
    )

    # Generate exploration_report.md
    report_lines = [
        "# Báo Cáo Khám Phá Hiệu Ứng Lịch Đầu Tháng Và Trước Nghỉ Lễ (Brief 192)",
        "",
        "> [!IMPORTANT]",
        "> **CẢNH BÁO THIÊN LỆCH SỐNG SÓT (SURVIVORSHIP BIAS):**",
        "> Dữ liệu `stocks_daily` gần như không có mã đã huỷ niêm yết; theo quyết định của chủ dự án và spec H ngày 25/10, nghiên cứu không dùng mã huỷ. Mọi đánh giá hiệu quả chỉ mang tính so sánh tương đối với baseline cùng universe.",
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
            report_lines.append(f"- **Cấu hình chọn (EA):** `{best_ea['params']}`")
            report_lines.append("")
            report_lines.append(
                "| Giai đoạn | n | Lãi gộp TB | Lãi ròng TB | Sharpe | p | CAGR | MDD | Calmar | Vượt Baseline Trim1% | Số cửa sổ | Mã TB / cửa sổ |"
            )
            report_lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
            report_lines.append(
                f"| **EA** | {best_ea['n_trades']} | {best_ea['gross_mean']*100:.2f}% | {best_ea['net_mean']*100:.2f}% | "
                f"{best_ea['sharpe']:.3f} | {best_ea['p_value']:.4f} | {best_ea['cagr']*100:.2f}% | {best_ea['mdd']*100:.2f}% | "
                f"{best_ea['calmar']:.2f} | {best_ea['mean_excess_trim1pct']*100:.2f}% | {best_ea['active_windows']} | {best_ea['avg_syms_per_window']:.1f} |"
            )
            eb_res = eb_results.get(idea_id)
            if eb_res:
                report_lines.append(
                    f"| **EB** | {eb_res['n_trades']} | {eb_res['gross_mean']*100:.2f}% | {eb_res['net_mean']*100:.2f}% | "
                    f"{eb_res['sharpe']:.3f} | {eb_res['p_value']:.4f} | {eb_res['cagr']*100:.2f}% | {eb_res['mdd']*100:.2f}% | "
                    f"{eb_res['calmar']:.2f} | {eb_res['mean_excess_trim1pct']*100:.2f}% | {eb_res['active_windows']} | {eb_res['avg_syms_per_window']:.1f} |"
                )
            report_lines.append("")
            if idea_id in passed_plateau:
                report_lines.append(
                    "- **Cao nguyên:** ĐẠT (tất cả các láng giềng ±1 bước đều có lãi dương và Sharpe >= 50%)."
                )
            else:
                report_lines.append("- **Cao nguyên:** TRƯỢT.")

            if "dsr" in st:
                report_lines.append(f"- **DSR (EA):** {st['dsr']:.4f}")
            else:
                report_lines.append("- **DSR (EA):** không tính")
        report_lines.append("")

    report_lines.extend(
        [
            "---",
            "",
            "## 2. Danh Sách Ứng Viên Chốt",
            "",
        ]
    )
    if candidates:
        for cand in candidates:
            report_lines.append(
                f"- `{cand['idea_id']}`: {cand['params']} (DSR: {cand['dsr']:.4f})"
            )
    else:
        report_lines.extend(
            [
                "> [!NOTE]",
                "> **Không có ứng viên nào vượt qua toàn bộ 4 bước lọc khắt khe (0 ứng viên là kết quả hợp lệ theo §5).**",
                "> Toàn bộ các ý tưởng được ghi nhận là phép đo âm để bảo vệ vốn và không nới lỏng tiêu chuẩn.",
            ]
        )

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
