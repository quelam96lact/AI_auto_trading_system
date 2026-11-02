"""Exploration runner for Brief 195 (Daily Trend MA + 1-Hour RSI Entry + Daily ATR Trailing Stop).

Workflow (§5):
- Step 1: Grid search 8 configs (n in {50, 100}, theta in {30, 40}, k in {2, 3}).
  Ordered by n, then theta, then k (each ascending).
  Logs each trial to docs/research/dot195/trial_ledger.csv with period='EA'.
  Selects config with highest sharpe_X.
- Step 2 (Plateau): Checks all 3 parameter neighbors (+/- 1 step) for mean_X > 0 and sharpe_X >= 0.5 * best_sharpe_X.
  If failed: rejected, does NOT shift to another peak.
- Step 3 (Criteria):
  - mean_X > 0 and one-sided p (weekly bootstrap) < 0.05
  - mean_r > 0 (net return after fees > 0)
  - n >= 100 (number of trades >= 100)
- Step 4 (DSR): compute_step4_dsr on weekly series X_w.
  Calls deflated_sharpe with n_trials = len(week_sharpes) + 27.
  Gate: DSR >= 0.95.
- Output: candidates.json, trial_ledger.csv, exploration_report.md.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from scripts.research188_ledger import evaluate_and_log
from scripts.research191_data import load_exchanges, load_stocks
from scripts.research191_exits import assert_ledger_safety
from scripts.research192_core import load_sessions
from scripts.research193_explore import get_parameter_neighbors
from scripts.research195_core import (
    IDEA_ID,
    compute_configuration_metrics,
    compute_step4_dsr,
    load_bars_5m,
    resample_1h,
    simulate_trades,
)

IDEA_SHA = "I1_DMA_RSI1H_ATR"

GRID = {
    "n": [50, 100],
    "theta": [30.0, 40.0],
    "k": [2.0, 3.0],
}

DEFAULT_DATA_DIR = Path("data/research195/explore")
DEFAULT_LEDGER_PATH = Path("docs/research/dot195/trial_ledger.csv")
DEFAULT_CANDIDATES_PATH = Path("docs/research/dot195/candidates.json")
DEFAULT_REPORT_PATH = Path("docs/research/dot195/exploration_report.md")


def run_exploration(
    data_dir: Path | str = DEFAULT_DATA_DIR,
    ledger_path: Path | str = DEFAULT_LEDGER_PATH,
    candidates_path: Path | str = DEFAULT_CANDIDATES_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
) -> dict[str, Any]:
    """Execute Brief 195 exploration workflow (§5).

    Line 1 enforces assert_ledger_safety(ledger_path).
    """
    assert_ledger_safety(ledger_path)

    d_dir = Path(data_dir)
    print(f"Loading data from {d_dir}...")
    sessions = load_sessions(d_dir, end=date(2026, 8, 7))
    daily_stocks = load_stocks(d_dir, end=date(2026, 8, 7))
    exchanges = load_exchanges(d_dir)
    bars_5m = load_bars_5m(d_dir)

    print("Resampling 5m bars to 1h bars...")
    bars_1h: dict[str, list[Any]] = {}
    for sym, b_list in bars_5m.items():
        bars_1h[sym] = resample_1h(b_list)

    explore_symbols = sorted(bars_5m.keys())

    Path(ledger_path).parent.mkdir(parents=True, exist_ok=True)
    Path(candidates_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)

    # Step 1: Run 8 configurations in exact order: n, theta, k
    all_results: list[dict[str, Any]] = []
    results_by_params: dict[tuple[int, float, float], dict[str, Any]] = {}

    print("\n--- Running 8 Grid Configurations ---")
    for n_val in GRID["n"]:
        for theta_val in GRID["theta"]:
            for k_val in GRID["k"]:
                params = {"n": n_val, "theta": theta_val, "k": k_val}
                print(f"Testing config: n={n_val}, theta={theta_val}, k={k_val}...")
                trades = simulate_trades(
                    bars_1h_by_symbol=bars_1h,
                    daily_bars_by_symbol=daily_stocks,
                    sessions=sessions,
                    exchanges=exchanges,
                    n=n_val,
                    theta=theta_val,
                    k=k_val,
                    explore_symbols=explore_symbols,
                )
                metrics = compute_configuration_metrics(trades)

                # Log to trial_ledger.csv
                evaluate_and_log(
                    idea_id=IDEA_ID,
                    idea_fn_or_sha=IDEA_SHA,
                    params=params,
                    metrics={
                        "n": metrics["n"],
                        "mean_net": metrics["mean_X"],
                        "sharpe": metrics["sharpe_X"],
                        "p": metrics["p"],
                    },
                    market="stock",
                    period="EA",
                    ledger_path=str(ledger_path),
                )

                res_item = {
                    "params": params,
                    "metrics": metrics,
                    "trades": trades,
                }
                all_results.append(res_item)
                results_by_params[(n_val, theta_val, k_val)] = res_item

    # Find configuration with highest sharpe_X
    best_item = max(all_results, key=lambda x: x["metrics"]["sharpe_X"])
    best_params = best_item["params"]
    best_metrics = best_item["metrics"]
    best_sharpe = best_metrics["sharpe_X"]

    print(
        f"\nSelected configuration: n={best_params['n']}, theta={best_params['theta']}, k={best_params['k']} "
        f"with sharpe_X={best_sharpe:.4f}, mean_X={best_metrics['mean_X']:.4f}"
    )

    # Step 2: Plateau check (all 3 parameter neighbors)
    neighbors = get_parameter_neighbors(GRID, best_params)
    plateau_passed = True
    plateau_details: list[dict[str, Any]] = []

    for nb_params in neighbors:
        key = (nb_params["n"], nb_params["theta"], nb_params["k"])
        nb_res = results_by_params[key]
        nb_metrics = nb_res["metrics"]
        nb_sharpe = nb_metrics["sharpe_X"]
        nb_mean = nb_metrics["mean_X"]

        nb_pass = (nb_mean > 0.0) and (nb_sharpe >= 0.50 * best_sharpe)
        if not nb_pass:
            plateau_passed = False

        plateau_details.append(
            {
                "params": nb_params,
                "mean_X": nb_mean,
                "sharpe_X": nb_sharpe,
                "passed": nb_pass,
            }
        )

    print(f"Plateau check: {'PASSED' if plateau_passed else 'FAILED'}")

    # Step 3: Criteria check
    cond_mean_x_p = (best_metrics["mean_X"] > 0.0) and (best_metrics["p"] < 0.05)
    cond_mean_r = best_metrics["mean_r"] > 0.0
    cond_n_trades = best_metrics["n"] >= 100
    criteria_passed = cond_mean_x_p and cond_mean_r and cond_n_trades

    print(
        f"Criteria check: mean_X>0 & p<0.05={cond_mean_x_p} (p={best_metrics['p']:.4f}), "
        f"mean_r>0={cond_mean_r} ({best_metrics['mean_r']:.4f}), "
        f"n>=100={cond_n_trades} ({best_metrics['n']}) -> {'PASSED' if criteria_passed else 'FAILED'}"
    )

    # Step 4: DSR (only calculated if plateau and criteria pass)
    week_sharpes = [r["metrics"]["sharpe_w"] for r in all_results]
    dsr_value: float | None = None
    dsr_passed = False

    if plateau_passed and criteria_passed:
        dsr_value = compute_step4_dsr(
            sharpe_w=best_metrics["sharpe_w"],
            n_weeks=best_metrics["n_weeks"],
            skew=best_metrics["skew_w"],
            kurt=best_metrics["kurt_w"],
            week_sharpes=week_sharpes,
        )
        dsr_passed = dsr_value >= 0.95
        print(f"Step 4 DSR: {dsr_value:.4f} -> {'PASSED' if dsr_passed else 'FAILED'}")
    else:
        print("Step 4 DSR: khong tinh (dung truoc Buoc 4)")

    # Candidate selection
    candidates_list: list[dict[str, Any]] = []
    if plateau_passed and criteria_passed and dsr_passed:
        candidates_list.append(
            {
                "idea_id": IDEA_ID,
                "n": best_params["n"],
                "theta": best_params["theta"],
                "k": best_params["k"],
                "metrics": {
                    "n": best_metrics["n"],
                    "n_weeks": best_metrics["n_weeks"],
                    "mean_X": best_metrics["mean_X"],
                    "sharpe_X": best_metrics["sharpe_X"],
                    "p": best_metrics["p"],
                    "mean_r": best_metrics["mean_r"],
                    "mean_EW": best_metrics["mean_EW"],
                    "win_rate": best_metrics["win_rate"],
                    "median_holding_bars": best_metrics["median_holding_bars"],
                    "median_holding_sessions": best_metrics["median_holding_sessions"],
                    "stop_count": best_metrics["stop_count"],
                    "trend_count": best_metrics["trend_count"],
                    "end_count": best_metrics["end_count"],
                    "sharpe_w": best_metrics["sharpe_w"],
                    "dsr": dsr_value,
                },
            }
        )

    # Export candidates.json
    cand_obj = {"candidates": candidates_list}
    cand_json_str = json.dumps(cand_obj, indent=2, ensure_ascii=False)
    with open(candidates_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(cand_json_str)

    candidates_sha = hashlib.sha256(Path(candidates_path).read_bytes()).hexdigest()

    # Generate exploration_report.md
    report_md = _generate_report(
        best_item=best_item,
        all_results=all_results,
        plateau_details=plateau_details,
        plateau_passed=plateau_passed,
        criteria_passed=criteria_passed,
        dsr_value=dsr_value,
        candidates_count=len(candidates_list),
        candidates_sha=candidates_sha,
    )
    with open(report_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(report_md)

    return {
        "all_results": all_results,
        "best_item": best_item,
        "plateau_passed": plateau_passed,
        "criteria_passed": criteria_passed,
        "dsr_value": dsr_value,
        "candidates": candidates_list,
        "candidates_sha": candidates_sha,
    }


def _generate_report(
    best_item: dict[str, Any],
    all_results: list[dict[str, Any]],
    plateau_details: list[dict[str, Any]],
    plateau_passed: bool,
    criteria_passed: bool,
    dsr_value: float | None,
    candidates_count: int,
    candidates_sha: str,
) -> str:
    """Generate exploration report in markdown (§5)."""
    p = best_item["params"]
    m = best_item["metrics"]

    dsr_str = f"{dsr_value:.4f}" if dsr_value is not None else "không tính"

    lines = [
        "# Báo cáo khám phá Đợt 195: Xu hướng ngày (MA) + Vào lệnh 1 giờ (RSI) + Thoát ATR ngày",
        "",
        "> [!WARNING]",
        "> **Cảnh báo thiên lệch (§0):** Danh sách khoảng 300 mã có nến 5 phút là universe collector chọn theo thanh khoản ở thời điểm gần đây, nên có thiên lệch nhìn trước nhẹ; dữ liệu không có mã huỷ niêm yết. Phép so với EW trên cùng universe vẫn đứng vững.",
        "",
        "## 1. Cấu hình được chọn (Sharpe_X cao nhất)",
        "",
        f"- **Tham số:** `n={p['n']}`, `theta={p['theta']}`, `k={p['k']}`",
        f"- **Số lệnh:** {m['n']}",
        f"- **Số tuần:** {m['n_weeks']}",
        f"- **mean_X:** {m['mean_X']:.6f}",
        f"- **sharpe_X:** {m['sharpe_X']:.4f}",
        f"- **p (bootstrap tuần):** {m['p']:.4f}",
        f"- **mean_r (lãi ròng sau phí):** {m['mean_r']:.6f}",
        f"- **mean_EW:** {m['mean_EW']:.6f}",
        f"- **Tỷ lệ thắng (r > 0):** {m['win_rate']:.2%}",
        f"- **Trung vị số nến 1h giữ:** {m['median_holding_bars']:.1f}",
        f"- **Trung vị số phiên giữ:** {m['median_holding_sessions']:.1f}",
        f"- **Thoát lệnh theo lý do:** STOP={m['stop_count']}, TREND={m['trend_count']}, END={m['end_count']}",
        f"- **sharpe_w (tuần):** {m['sharpe_w']:.4f}",
        f"- **DSR Bước 4:** {dsr_str}",
        "",
        "## 2. Kiểm tra cao nguyên (Bước 2)",
        "",
        f"- **Kết quả:** {'ĐẠT' if plateau_passed else 'TRƯỢT'}",
        "",
        "| Láng giềng | mean_X | sharpe_X | Ngưỡng sharpe (>= 50%) | Kết quả |",
        "|---|---|---|---|---|",
    ]

    for nb in plateau_details:
        nb_p = nb["params"]
        p_str = f"n={nb_p['n']}, theta={nb_p['theta']}, k={nb_p['k']}"
        res_str = "ĐẠT" if nb["passed"] else "TRƯỢT"
        thresh = 0.50 * m["sharpe_X"]
        lines.append(
            f"| `{p_str}` | {nb['mean_X']:.6f} | {nb['sharpe_X']:.4f} | {thresh:.4f} | {res_str} |"
        )

    lines.extend(
        [
            "",
            "## 3. Tiêu chí lựa chọn (Bước 3 & 4)",
            "",
            f"- `mean_X > 0` và `p < 0.05`: {'ĐẠT' if (m['mean_X'] > 0 and m['p'] < 0.05) else 'TRƯỢT'} (mean_X={m['mean_X']:.6f}, p={m['p']:.4f})",
            f"- `mean_r > 0`: {'ĐẠT' if m['mean_r'] > 0 else 'TRƯỢT'} (mean_r={m['mean_r']:.6f})",
            f"- `n >= 100`: {'ĐẠT' if m['n'] >= 100 else 'TRƯỢT'} (n={m['n']})",
            f"- `DSR >= 0.95`: {dsr_str}",
            "",
            "## 4. Bảng tổng hợp 8 cấu hình (Grid)",
            "",
            "| n | theta | k | Số lệnh | mean_X | sharpe_X | p | mean_r | Trung vị phiên giữ |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )

    for r in all_results:
        rp = r["params"]
        rm = r["metrics"]
        lines.append(
            f"| {rp['n']} | {rp['theta']} | {rp['k']} | {rm['n']} | {rm['mean_X']:.6f} | {rm['sharpe_X']:.4f} | {rm['p']:.4f} | {rm['mean_r']:.6f} | {rm['median_holding_sessions']:.1f} |"
        )

    lines.extend(
        [
            "",
            "## 5. Kết luận",
            "",
            f"- **Số ứng viên vào cổng kiểm chứng:** {candidates_count}",
            f"- **SHA256 candidates.json:** `{candidates_sha}`",
        ]
    )

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    run_exploration()
