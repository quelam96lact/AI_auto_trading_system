"""Exploration runner for Brief 191 (Foreign flow exploration).

Workflow (§4.2):
1. Step 1 (EA): Grid search all 5 ideas over EA (2020-03-01 -> 2021-06-30).
   Log every configuration to trial_ledger.csv.
   Select config with highest Sharpe among configs with n >= 100.
2. Step 2 (Plateau): Verify +/- 1 step neighbors have mean_net > 0 and Sharpe >= 50% best Sharpe.
3. Step 3 (EB): Evaluate selected config on EB (2021-07-01 -> 2022-12-30).
   Check n >= 100, mean_net > 0, bootstrap p < 0.05 (seed=191), Calmar >= 0.86, excess_trim1pct > 0.
4. Step 4 (DSR): Deflated Sharpe Ratio on EA trials (DSR >= 0.95).
5. Candidates: Select up to 3 passing ideas, export candidates.json, and generate exploration_report.md.
"""

from __future__ import annotations

import hashlib
import io
import itertools
import json
import sys
from datetime import UTC, date, datetime
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
    join_daily,
    load_exchanges,
    load_foreign_flow,
    load_stocks,
)
from scripts.research191_exits import (
    Trade191,
    assert_ledger_safety,
    liquid_baseline_excess,
)
from scripts.research191_ideas import (
    IDEA_GRIDS,
    IDEA_IDS,
    generate_trades_for_idea,
)
from trading.stock_study import bootstrap_by_month

LEDGER_PATH = "docs/research/dot191/trial_ledger.csv"
CANDIDATES_PATH = "docs/research/dot191/candidates.json"
REPORT_PATH = "docs/research/dot191/exploration_report.md"

EA_START = date(2020, 3, 1)
EA_END = date(2021, 6, 30)

EB_START = date(2021, 7, 1)
EB_END = date(2022, 12, 30)


def compute_bootstrap_p(trades: list[Trade191], seed: int = 191) -> float:
    """Bootstrap p-value by month with custom seed (§4.2)."""
    if not trades:
        return 1.0
    by_month: dict[tuple[int, int], list[float]] = {}
    for t in trades:
        m_key = (t.entry_ts.year, t.entry_ts.month)
        if m_key not in by_month:
            by_month[m_key] = []
        by_month[m_key].append(t.net_return)

    res = bootstrap_by_month(
        by_month, n=2000, seed=seed, ci_low_pct=0.05, ci_high_pct=0.95
    )
    return float(res["p"]) if res["p"] is not None else 1.0


def calculate_exit_breakdown(trades: list[Trade191]) -> dict[str, Any]:
    """Calculate exit reason frequencies, mean returns, and median hold sessions (§4.2)."""
    n = len(trades)
    if n == 0:
        return {
            "tp_pct": 0.0,
            "sl_pct": 0.0,
            "time_pct": 0.0,
            "end_pct": 0.0,
            "mean_net_tp": 0.0,
            "mean_net_sl": 0.0,
            "median_hold": 0.0,
        }
    tp_trades = [t for t in trades if t.exit_reason == "TP"]
    sl_trades = [t for t in trades if t.exit_reason == "SL"]
    time_trades = [t for t in trades if t.exit_reason == "TIME"]
    end_trades = [t for t in trades if t.exit_reason == "END"]

    holdings = [t.holding_sessions for t in trades]
    return {
        "tp_pct": len(tp_trades) / n,
        "sl_pct": len(sl_trades) / n,
        "time_pct": len(time_trades) / n,
        "end_pct": len(end_trades) / n,
        "mean_net_tp": (
            float(np.mean([t.net_return for t in tp_trades])) if tp_trades else 0.0
        ),
        "mean_net_sl": (
            float(np.mean([t.net_return for t in sl_trades])) if sl_trades else 0.0
        ),
        "median_hold": float(np.median(holdings)) if holdings else 0.0,
    }


def get_parameter_neighbors(
    grid: dict[str, list[Any]],
    chosen_params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Get all +/- 1 step neighbor configurations across all parameters."""
    neighbors: list[dict[str, Any]] = []
    for param_name, values in grid.items():
        val = chosen_params[param_name]
        if val not in values:
            continue
        idx = values.index(val)
        # Left neighbor
        if idx > 0:
            nb = dict(chosen_params)
            nb[param_name] = values[idx - 1]
            neighbors.append(nb)
        # Right neighbor
        if idx < len(values) - 1:
            nb = dict(chosen_params)
            nb[param_name] = values[idx + 1]
            neighbors.append(nb)
    return neighbors


def run_exploration(data_dir: Path | str = "data/research191/explore") -> None:
    # Audit 25/10 (§3.4): so da ton tai thi dung ngay; ban truoc doc lai EA tu so
    # roi chay tiep cao nguyen/EB, chi dung khi so co ca EA lan EB
    assert_ledger_safety(LEDGER_PATH)

    d_dir = Path(data_dir)
    print(f"[1/5] Loading data from {d_dir}...")
    stocks = load_stocks(d_dir, end="2022-12-31")
    flows = load_foreign_flow(d_dir, end="2022-12-31")
    exchanges = load_exchanges(d_dir)
    all_joined = join_daily(stocks, flows)
    print(f"Loaded {len(all_joined)} symbols.")

    # Storage for EA results
    ea_results_by_idea: dict[str, list[dict[str, Any]]] = {i: [] for i in IDEA_IDS}
    all_ea_sharpes: list[float] = []

    print("\n[2/5] Running Step 1 (EA grid search)...")
    for idea_id in IDEA_IDS:
        print(f"\n--- Exploring {idea_id} ---")
        grid = IDEA_GRIDS[idea_id]
        keys = list(grid.keys())
        combos = [dict(zip(keys, v)) for v in itertools.product(*grid.values())]

        for params in combos:
            trades = generate_trades_for_idea(
                idea_id=idea_id,
                params=params,
                all_joined=all_joined,
                exchanges=exchanges,
                start_date=EA_START,
                end_date=EA_END,
            )

            metrics = calculate_trade_metrics(trades)
            p_val = compute_bootstrap_p(trades, seed=191)
            metrics["p"] = p_val

            sim = simulate_portfolio(
                trades,
                market="stock",
                initial_capital=100_000_000.0,
                start_date=EA_START,
                end_date=EA_END,
            )
            metrics.update(sim)

            base = liquid_baseline_excess(trades, all_joined)
            metrics.update(base)

            breakdown = calculate_exit_breakdown(trades)
            metrics.update(breakdown)

            evaluate_and_log(
                idea_id=idea_id,
                idea_fn_or_sha=idea_id,
                params=params,
                market="stock",
                period="EA",
                metrics=metrics,
                ledger_path=LEDGER_PATH,
            )

            all_ea_sharpes.append(metrics["sharpe"])
            ea_results_by_idea[idea_id].append(
                {
                    "params": params,
                    "metrics": metrics,
                }
            )

            print(
                f"  EA {params} -> n={metrics['n']}, mean_net={metrics['mean_net']*100:.2f}%, "
                f"sharpe={metrics['sharpe']:.3f}, calmar={metrics['calmar']:.2f}, "
                f"excess_trim={metrics.get('mean_excess_trim1pct', 0.0)*100:.2f}%"
            )

    sr_trials_var = (
        float(np.var(all_ea_sharpes, ddof=1)) if len(all_ea_sharpes) > 1 else 0.0
    )
    n_ea_trials = len(all_ea_sharpes)
    print(
        f"\nTotal EA trials logged: {n_ea_trials}, Sharpe variance: {sr_trials_var:.6f}"
    )

    # Process each idea through Steps 1, 2, 3, 4
    idea_summary: dict[str, dict[str, Any]] = {}
    candidates: list[dict[str, Any]] = []

    print("\n[3/5] Evaluating Plateau, EB, and DSR for each idea...")
    for idea_id in IDEA_IDS:
        summary: dict[str, Any] = {
            "idea_id": idea_id,
            "status": "REJECTED",
            "reason": "",
            "best_params": None,
            "ea_metrics": None,
            "plateau_ok": False,
            "eb_metrics": None,
            "dsr": 0.0,
            "dsr_ok": False,
        }

        # Step 1: Select config with highest Sharpe with n >= 100
        eligible = [r for r in ea_results_by_idea[idea_id] if r["metrics"]["n"] >= 100]
        if not eligible:
            max_n = max(
                (r["metrics"]["n"] for r in ea_results_by_idea[idea_id]), default=0
            )
            summary["reason"] = (
                f"Thiếu mẫu (không có cấu hình nào n >= 100 trên EA, max n={max_n})"
            )
            idea_summary[idea_id] = summary
            print(f"[{idea_id}] -> {summary['reason']}")
            continue

        best = max(eligible, key=lambda r: r["metrics"]["sharpe"])
        best_params = best["params"]

        # Run trades once on EA for the selected config to get full metrics and breakdown
        trades_ea_selected = generate_trades_for_idea(
            idea_id=idea_id,
            params=best_params,
            all_joined=all_joined,
            exchanges=exchanges,
            start_date=EA_START,
            end_date=EA_END,
        )
        best_metrics = calculate_trade_metrics(trades_ea_selected)
        best_metrics["p"] = compute_bootstrap_p(trades_ea_selected, seed=191)
        sim_ea = simulate_portfolio(
            trades_ea_selected,
            market="stock",
            initial_capital=100_000_000.0,
            start_date=EA_START,
            end_date=EA_END,
        )
        best_metrics.update(sim_ea)
        base_ea = liquid_baseline_excess(trades_ea_selected, all_joined)
        best_metrics.update(base_ea)
        breakdown_ea = calculate_exit_breakdown(trades_ea_selected)
        best_metrics.update(breakdown_ea)

        summary["best_params"] = best_params
        summary["ea_metrics"] = best_metrics
        print(
            f"[{idea_id}] Selected EA: {best_params} (Sharpe={best_metrics['sharpe']:.3f}, n={best_metrics['n']})"
        )

        # Step 2: Plateau check (+/- 1 neighbor)
        grid = IDEA_GRIDS[idea_id]
        neighbors = get_parameter_neighbors(grid, best_params)
        plateau_passed = True
        plateau_failures: list[str] = []

        for nb in neighbors:
            nb_match = next(
                (r for r in ea_results_by_idea[idea_id] if r["params"] == nb), None
            )
            if nb_match is None:
                continue
            m = nb_match["metrics"]
            if m["mean_net"] <= 0 or m["sharpe"] < 0.50 * best_metrics["sharpe"]:
                plateau_passed = False
                plateau_failures.append(
                    f"nb {nb}: mean_net={m['mean_net']*100:.2f}%, sharpe={m['sharpe']:.3f}"
                )

        summary["plateau_ok"] = plateau_passed
        if not plateau_passed:
            summary["reason"] = (
                f"Trượt cao nguyên: {len(plateau_failures)} láng giềng không đạt (cần mean_net > 0 và Sharpe >= {0.50 * best_metrics['sharpe']:.3f})"
            )
            idea_summary[idea_id] = summary
            print(f"[{idea_id}] -> {summary['reason']}")
            continue

        print(f"[{idea_id}] -> Đạt cao nguyên ({len(neighbors)} láng giềng đều đạt)")

        # Step 3: Run on EB
        print(f"[{idea_id}] Running on EB with params {best_params}...")
        trades_eb = generate_trades_for_idea(
            idea_id=idea_id,
            params=best_params,
            all_joined=all_joined,
            exchanges=exchanges,
            start_date=EB_START,
            end_date=EB_END,
        )

        metrics_eb = calculate_trade_metrics(trades_eb)
        p_val_eb = compute_bootstrap_p(trades_eb, seed=191)
        metrics_eb["p"] = p_val_eb

        sim_eb = simulate_portfolio(
            trades_eb,
            market="stock",
            initial_capital=100_000_000.0,
            start_date=EB_START,
            end_date=EB_END,
        )
        metrics_eb.update(sim_eb)

        base_eb = liquid_baseline_excess(trades_eb, all_joined)
        metrics_eb.update(base_eb)

        breakdown_eb = calculate_exit_breakdown(trades_eb)
        metrics_eb.update(breakdown_eb)

        # Log EB run to trial ledger
        evaluate_and_log(
            idea_id=idea_id,
            idea_fn_or_sha=idea_id,
            params=best_params,
            market="stock",
            period="EB",
            metrics=metrics_eb,
            ledger_path=LEDGER_PATH,
        )

        summary["eb_metrics"] = metrics_eb
        print(
            f"[{idea_id}] EB result: n={metrics_eb['n']}, mean_net={metrics_eb['mean_net']*100:.2f}%, "
            f"p={metrics_eb['p']:.4f}, calmar={metrics_eb['calmar']:.2f}, "
            f"excess_trim={metrics_eb['mean_excess_trim1pct']*100:.2f}%"
        )

        # Check EB criteria
        eb_failures: list[str] = []
        if metrics_eb["n"] < 100:
            eb_failures.append(f"n={metrics_eb['n']} < 100")
        if metrics_eb["mean_net"] <= 0:
            eb_failures.append(f"mean_net={metrics_eb['mean_net']*100:.2f}% <= 0")
        if metrics_eb["p"] >= 0.05:
            eb_failures.append(f"p={metrics_eb['p']:.4f} >= 0.05")
        if metrics_eb["calmar"] < 0.86:
            eb_failures.append(f"calmar={metrics_eb['calmar']:.2f} < 0.86")
        if metrics_eb["mean_excess_trim1pct"] <= 0:
            eb_failures.append(
                f"excess_trim1pct={metrics_eb['mean_excess_trim1pct']*100:.2f}% <= 0"
            )

        if eb_failures:
            summary["reason"] = f"Trượt EB: {', '.join(eb_failures)}"
            idea_summary[idea_id] = summary
            print(f"[{idea_id}] -> {summary['reason']}")
            continue

        print(f"[{idea_id}] -> Đạt EB!")

        # Step 4: DSR on EA
        dsr_val = deflated_sharpe(
            sr=best_metrics["sharpe"],
            n_obs=best_metrics["n"],
            skew=best_metrics["skew"],
            kurt=best_metrics["kurt"],
            n_trials=n_ea_trials + 23,
            sr_trials_var=sr_trials_var,
        )
        summary["dsr"] = dsr_val
        summary["dsr_ok"] = dsr_val >= 0.95

        if dsr_val < 0.95:
            summary["reason"] = (
                f"Trượt DSR: {dsr_val:.4f} < 0.95 (n_trials={n_ea_trials + 23})"
            )
            idea_summary[idea_id] = summary
            print(f"[{idea_id}] -> {summary['reason']}")
            continue

        print(f"[{idea_id}] -> Đạt DSR: {dsr_val:.4f} >= 0.95!")
        summary["status"] = "PASSED"
        idea_summary[idea_id] = summary
        candidates.append(summary)

    # Candidate selection: up to 3 with smallest p on EB
    if len(candidates) > 3:
        candidates.sort(key=lambda c: c["eb_metrics"]["p"])
        candidates = candidates[:3]

    print(f"\n[4/5] Selected {len(candidates)} candidates.")

    # Write candidates.json
    cand_data = {
        "generated_at": datetime.now(UTC).date().isoformat(),
        "n_ea_trials": n_ea_trials,
        "candidates": [
            {
                "idea_id": c["idea_id"],
                "params": c["best_params"],
                "ea": {
                    "n": c["ea_metrics"]["n"],
                    "sharpe": c["ea_metrics"]["sharpe"],
                    "mean_net": c["ea_metrics"]["mean_net"],
                    "calmar": c["ea_metrics"]["calmar"],
                    "tp_pct": c["ea_metrics"]["tp_pct"],
                },
                "eb": {
                    "n": c["eb_metrics"]["n"],
                    "p": c["eb_metrics"]["p"],
                    "mean_net": c["eb_metrics"]["mean_net"],
                    "calmar": c["eb_metrics"]["calmar"],
                    "excess_trim1pct": c["eb_metrics"]["mean_excess_trim1pct"],
                    "tp_pct": c["eb_metrics"]["tp_pct"],
                },
                "dsr": c["dsr"],
            }
            for c in candidates
        ],
    }

    Path(CANDIDATES_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(CANDIDATES_PATH, "w", encoding="utf-8") as f:
        json.dump(cand_data, f, indent=2)

    with open(CANDIDATES_PATH, "rb") as f:
        cand_sha = hashlib.sha256(f.read()).hexdigest()
    print(f"Wrote {CANDIDATES_PATH} (sha256={cand_sha})")

    # Generate exploration_report.md
    print("\n[5/5] Generating exploration_report.md...")
    generate_report(idea_summary, candidates, cand_sha, n_ea_trials)
    print(f"Report written to {REPORT_PATH}")


def generate_report(
    idea_summary: dict[str, dict[str, Any]],
    candidates: list[dict[str, Any]],
    cand_sha: str,
    n_ea_trials: int,
) -> None:
    lines: list[str] = [
        "# Báo Cáo Khám Phá Chiến Lược Khối Ngoại Chốt Lời +10% (Brief 191)",
        "",
        "> [!IMPORTANT]",
        "> **CẢNH BÁO THIÊN LỆCH SỐNG SÓT (SURVIVORSHIP BIAS):**",
        (
            "> Dữ liệu `bars_daily` gần như không có mã đã huỷ niêm yết; theo quyết định của chủ dự án và spec H ngày 10/10, "
            "nghiên cứu không dùng mã huỷ. Mọi đánh giá hiệu quả chỉ mang tính so sánh tương đối với baseline cùng universe."
        ),
        "",
        f"- **Tổng số thử nghiệm EA đã ghi sổ:** {n_ea_trials} cấu hình.",
        f"- **Tổng số thử nghiệm EB đã ghi sổ:** {sum(1 for s in idea_summary.values() if s['eb_metrics'] is not None)} cấu hình.",
        f"- **Số ứng viên vượt qua toàn bộ 4 bước:** {len(candidates)}.",
        f"- **SHA256 của `candidates.json`:** `{cand_sha}`",
        "",
        "---",
        "",
        "## 1. Kết Quả Từng Ý Tưởng Qua Các Bước",
        "",
    ]

    for idea_id in IDEA_IDS:
        s = idea_summary[idea_id]
        lines.append(f"### {idea_id}")
        lines.append(f"- **Trạng thái:** `{s['status']}`")
        if s["reason"]:
            lines.append(f"- **Lý do loại / Kết luận:** {s['reason']}")

        if s["best_params"] is not None:
            lines.append(f"- **Cấu hình chọn (EA):** `{s['best_params']}`")

        # Table for EA and EB
        if s["ea_metrics"] is not None:
            lines.append("")
            lines.append(
                "| Giai đoạn | n | Lãi ròng TB | Sharpe | p | Calmar | Vượt Baseline Trim1% | Tỷ lệ TP | Tỷ lệ SL | Tỷ lệ TIME | Tỷ lệ END | Lãi TB TP | Lỗ TB SL | Số phiên giữ TB |"
            )
            lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")

            ea = s["ea_metrics"]
            lines.append(
                f"| **EA** | {ea['n']} | {ea['mean_net']*100:.2f}% | {ea['sharpe']:.3f} | {ea['p']:.4f} | {ea['calmar']:.2f} | "
                f"{ea['mean_excess_trim1pct']*100:.2f}% | {ea['tp_pct']*100:.1f}% | {ea['sl_pct']*100:.1f}% | {ea['time_pct']*100:.1f}% | "
                f"{ea['end_pct']*100:.1f}% | {ea['mean_net_tp']*100:.2f}% | {ea['mean_net_sl']*100:.2f}% | {ea['median_hold']:.0f} |"
            )

            if s["eb_metrics"] is not None:
                eb = s["eb_metrics"]
                lines.append(
                    f"| **EB** | {eb['n']} | {eb['mean_net']*100:.2f}% | {eb['sharpe']:.3f} | {eb['p']:.4f} | {eb['calmar']:.2f} | "
                    f"{eb['mean_excess_trim1pct']*100:.2f}% | {eb['tp_pct']*100:.1f}% | {eb['sl_pct']*100:.1f}% | {eb['time_pct']*100:.1f}% | "
                    f"{eb['end_pct']*100:.1f}% | {eb['mean_net_tp']*100:.2f}% | {eb['mean_net_sl']*100:.2f}% | {eb['median_hold']:.0f} |"
                )
            lines.append("")

        if s["plateau_ok"]:
            lines.append(
                "- **Cao nguyên:** ĐẠT (tất cả các láng giềng ±1 bước đều có lãi dương và Sharpe >= 50%)."
            )
        if s["dsr"] > 0:
            lines.append(
                f"- **DSR:** {s['dsr']:.4f} ({'ĐẠT >= 0.95' if s['dsr_ok'] else 'TRƯỢT < 0.95'})"
            )

        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## 2. Danh Sách Ứng Viên Chốt",
            "",
        ]
    )

    if candidates:
        for idx, c in enumerate(candidates, 1):
            lines.append(f"### Ứng viên {idx}: {c['idea_id']}")
            lines.append(f"- Tham số: `{c['best_params']}`")
            lines.append(
                f"- EA: n={c['ea_metrics']['n']}, Sharpe={c['ea_metrics']['sharpe']:.3f}, TP%={c['ea_metrics']['tp_pct']*100:.1f}%"
            )
            lines.append(
                f"- EB: n={c['eb_metrics']['n']}, p={c['eb_metrics']['p']:.4f}, Calmar={c['eb_metrics']['calmar']:.2f}, Excess Trim={c['eb_metrics']['mean_excess_trim1pct']*100:.2f}%, TP%={c['eb_metrics']['tp_pct']*100:.1f}%"
            )
            lines.append(f"- DSR: {c['dsr']:.4f}")
            lines.append("")
    else:
        lines.append("> [!NOTE]")
        lines.append(
            "> **Không có ứng viên nào vượt qua toàn bộ 4 bước lọc khắt khe (0 ứng viên là kết quả hợp lệ theo §4.2).**"
        )
        lines.append(
            "> Toàn bộ các ý tưởng được ghi nhận là phép đo âm để bảo vệ vốn và không nới lỏng tiêu chuẩn."
        )
        lines.append("")

    Path(REPORT_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    if sys.stdout is not None and hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
    if sys.stderr is not None and hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )
    run_exploration()
