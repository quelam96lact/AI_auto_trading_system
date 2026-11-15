"""Exploration runner for Brief 237 (Low Attention / Abnormal Turnover Monthly Rotation).

Workflow (§5):
0. Step 0: Verify universe counts at L(01/2017), L(06/2018), L(12/2019), L(06/2021), L(12/2022)
   match [56, 58, 85, 166, 136] after excluding fund certificates (E1VFVN30, FU*).
1. Step 1 (EA): Grid search I1_LOWATTN (S in {20, 40, 60} x N in {10, 15, 20} = 9 configs).
   Log every trial to docs/research/dot237/trial_ledger.csv with period='EA'.
   Select config with highest sharpe_X.
2. Step 2 (Plateau): All +/- 1 step neighbors on each parameter (S, N) must have
   mean_X > 0 and sharpe_X >= 0.5 * best_sharpe_X. Stop without changing peak on fail.
3. Step 3 (EB): Evaluate selected config once on EB (2019-12-31 -> 2022-12-30), period='EB'.
   Gates: mean_X > 0 and p < 0.05; MDD <= 2/3 * ETF_EB_MDD; CAGR >= ETF_EB_CAGR - 0.01;
   avg_syms_held >= 0.8 * N.
4. Step 4 (DSR): deflated_sharpe on EA X_m with n_trials = 9 + 29 = 38 (>= 0.95 to pass).
5. Export candidates.json, selections.json, and exploration_report.md.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from scripts.research188_core import deflated_sharpe
from scripts.research188_ledger import evaluate_and_log
from scripts.research191_data import StockDailyBar, load_exchanges, load_stocks
from scripts.research191_exits import assert_ledger_safety
from scripts.research192_core import load_sessions
from scripts.research193_core import (
    calculate_rotation_metrics,
    ew_benchmark,
    get_rebalance_dates,
    simulate_rotation,
)
from scripts.research237_core import (
    LONG_WINDOW,
    MIN_TURNOVER_237,
    filter_out_funds,
    get_universe_at_r,
    select_lowattn_symbols,
)

DATA_DIR = "data/research227/explore"
LEDGER_PATH = "docs/research/dot237/trial_ledger.csv"
CANDIDATES_PATH = "docs/research/dot237/candidates.json"
REPORT_PATH = "docs/research/dot237/exploration_report.md"
SELECTIONS_PATH = "docs/research/dot237/selections.json"

IDEA_ID = "I1_LOWATTN"
IDEA_TYPE = "LOWATTN"
SEED_237 = 237
PRIOR_NEGATIVE_FAMILIES = 29
OLD_CALMAR_GATE = 0.86

# Pre-registered ETF benchmarks (Lead computed from bars_daily prior to strategy run)
ETF_EA_CAGR = 0.1251
ETF_EA_MDD = 0.2788
ETF_EB_CAGR = 0.0550
ETF_EB_MDD = 0.4229

# EA: first rebalance L(01/2017), last rebalance L(12/2019) -> 35 months
EA_FIRST_MONTH = (2017, 1)
EA_LAST_MONTH = (2019, 12)

# EB: first rebalance L(12/2019), last rebalance L(12/2022) -> 36 months
EB_FIRST_MONTH = (2019, 12)
EB_LAST_MONTH = (2022, 12)

GRID: dict[str, list[int]] = {
    "S": [20, 40, 60],
    "N": [10, 15, 20],
}

EXPECTED_STEP0_COUNTS: dict[tuple[int, int], int] = {
    (2017, 1): 56,
    (2018, 6): 58,
    (2019, 12): 85,
    (2021, 6): 166,
    (2022, 12): 136,
}


def filter_rebalance_dates(
    all_rebal: list[date],
    first_ym: tuple[int, int],
    last_ym: tuple[int, int],
) -> list[date]:
    """Filter rebalance dates L(M) between first_ym and last_ym inclusive."""
    return [d for d in all_rebal if first_ym <= (d.year, d.month) <= last_ym]


def get_parameter_neighbors(
    grid: dict[str, list[int]],
    params: dict[str, int],
) -> list[dict[str, int]]:
    """Return all +/- 1 step neighbors independently along each grid parameter."""
    neighbors: list[dict[str, int]] = []
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


def _config_key(params: dict[str, int], prefix: str = "") -> str:
    base = f"S{int(params['S'])}_N{int(params['N'])}"
    return f"{prefix}{base}" if prefix else base


def check_step0_universe(
    all_rebal: list[date],
    sessions: list[date],
    stocks: dict[str, list[StockDailyBar]],
    expected_counts: dict[tuple[int, int], int] = EXPECTED_STEP0_COUNTS,
) -> dict[str, int]:
    """Verify §3.2 universe size at the 5 pre-counted checkpoints from §1."""
    rebal_by_ym = {(d.year, d.month): d for d in all_rebal}
    counts: dict[str, int] = {}
    mismatches: list[str] = []

    print("\n--- Step 0: Universe Count Check ---")
    for (year, month), expected in expected_counts.items():
        label = f"L({month:02d}/{year})"
        r_date = rebal_by_ym.get((year, month))
        if r_date is None:
            msg = f"{label}: rebalance date missing in sessions"
            mismatches.append(msg)
            print(f"  {msg}")
            continue

        univ = get_universe_at_r(
            r=r_date,
            sessions=sessions,
            bars_by_symbol=stocks,
            min_turnover=MIN_TURNOVER_237,
            long_window=LONG_WINDOW,
        )
        actual = len(univ)
        counts[label] = actual
        status = "MATCH" if actual == expected else "MISMATCH"
        print(f"  {label} [{r_date.isoformat()}]: actual={actual}, expected={expected} ({status})")
        if actual != expected:
            mismatches.append(f"{label} actual={actual} != expected={expected}")

    if mismatches:
        raise ValueError("Step 0 universe count mismatch: " + "; ".join(mismatches))

    return counts


def select_best_ea_config(ea_entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Select the EA configuration with the highest sharpe_X (Step 1, §5)."""
    if not ea_entries:
        raise ValueError("ea_entries must not be empty")
    return max(ea_entries, key=lambda entry: entry["metrics"]["sharpe_X"])


def check_plateau(
    best_entry: dict[str, Any],
    ea_entries: list[dict[str, Any]],
    grid: dict[str, list[int]] = GRID,
) -> tuple[bool, list[str]]:
    """Verify Step 2 plateau across +/- 1 step neighbors on every parameter (S and N)."""
    by_params = {json.dumps(r["params"], sort_keys=True): r for r in ea_entries}
    best_sharpe = float(best_entry["metrics"]["sharpe_X"])
    target_sharpe = 0.5 * best_sharpe

    neighbors = get_parameter_neighbors(grid, best_entry["params"])
    fail_reasons: list[str] = []

    if float(best_entry["metrics"]["mean_X"]) <= 0:
        fail_reasons.append(f"best {best_entry['params']}: mean_X={best_entry['metrics']['mean_X']*100:.2f}% <= 0")

    for nb in neighbors:
        nb_key = json.dumps(nb, sort_keys=True)
        nb_entry = by_params.get(nb_key)
        if nb_entry is None:
            fail_reasons.append(f"{nb}: missing EA result")
            continue
        nb_m = nb_entry["metrics"]
        if nb_m["mean_X"] <= 0 or nb_m["sharpe_X"] < target_sharpe:
            fail_reasons.append(
                f"{nb}: mean_X={nb_m['mean_X']*100:.2f}%, sharpe_X={nb_m['sharpe_X']:.3f} "
                f"(need mean_X > 0 and sharpe_X >= {target_sharpe:.3f})"
            )

    return (len(fail_reasons) == 0), fail_reasons


def check_eb_gates(
    metrics_eb: dict[str, Any],
    avg_syms_held: float,
    n_stocks: int,
    etf_cagr: float = ETF_EB_CAGR,
    etf_mdd: float = ETF_EB_MDD,
) -> tuple[bool, list[str]]:
    """Verify Step 3 EB evaluation gates (§5)."""
    fail_reasons: list[str] = []
    mean_x = float(metrics_eb["mean_X"])
    p_val = float(metrics_eb["p"])
    mdd = float(metrics_eb["mdd"])
    cagr = float(metrics_eb["cagr"])

    max_mdd = (2.0 / 3.0) * etf_mdd
    min_cagr = etf_cagr - 0.01
    min_syms = 0.8 * n_stocks

    if mean_x <= 0:
        fail_reasons.append(f"mean_X={mean_x*100:.2f}% <= 0")
    if p_val >= 0.05:
        fail_reasons.append(f"p={p_val:.4f} >= 0.05")
    if mdd > max_mdd:
        fail_reasons.append(f"MDD={mdd*100:.2f}% > {max_mdd*100:.2f}% (2/3 ETF MDD)")
    if cagr < min_cagr:
        fail_reasons.append(f"CAGR={cagr*100:.2f}% < {min_cagr*100:.2f}% (ETF CAGR - 1pp)")
    if avg_syms_held < min_syms:
        fail_reasons.append(f"avg_syms_held={avg_syms_held:.2f} < {min_syms:.2f}")

    return (len(fail_reasons) == 0), fail_reasons


def compute_step4_dsr(
    sharpe_x: float,
    n_months: int,
    skew: float,
    kurt: float,
    ea_sharpes: list[float],
    extra_trials: int = PRIOR_NEGATIVE_FAMILIES,
) -> float:
    """Compute Step 4 Deflated Sharpe Ratio (§5): n_trials = len(ea_sharpes) + extra_trials."""
    n_trials = len(ea_sharpes) + extra_trials
    sr_trials_var = float(np.var(ea_sharpes, ddof=1)) if len(ea_sharpes) > 1 else 0.0
    return deflated_sharpe(
        sr=sharpe_x,
        n_obs=n_months,
        skew=skew,
        kurt=kurt,
        n_trials=n_trials,
        sr_trials_var=sr_trials_var,
    )


def _make_selector(
    sessions: list[date],
    bars_by_symbol: dict[str, list[StockDailyBar]],
    s_window: int,
    n_stocks: int,
    selected_record: dict[str, list[str]],
    select_symbols_fn: Callable[..., list[str]] = select_lowattn_symbols,
) -> Callable[[date], list[str]]:
    """Build a select_fn closure that records selections by ISO date."""

    def _select(r: date) -> list[str]:
        syms = select_symbols_fn(
            r=r,
            sessions=sessions,
            bars_by_symbol=bars_by_symbol,
            s_window=s_window,
            n_stocks=n_stocks,
            min_turnover=MIN_TURNOVER_237,
            long_window=LONG_WINDOW,
        )
        selected_record[r.isoformat()] = list(syms)
        return syms

    return _select


def _format_report_row(label: str, metrics: dict[str, Any], sim: dict[str, Any]) -> str:
    calmar_info = f"ĐẠT ({metrics['calmar']:.2f})" if metrics["calmar"] >= OLD_CALMAR_GATE else f"TRƯỢT ({metrics['calmar']:.2f})"
    return (
        f"| {label} | {metrics['n']} | {metrics['mean_R']*100:.2f}% | {metrics['mean_EW']*100:.2f}% | "
        f"{metrics['mean_X']*100:.2f}% | {metrics['sharpe_X']:.4f} | {metrics['p']:.4f} | "
        f"{metrics['cagr']*100:.2f}% | {metrics['mdd']*100:.2f}% | {metrics['calmar']:.2f} | "
        f"{calmar_info} | {metrics['cagr_ew']*100:.2f}% | {sim['mean_turnover']*100:.2f}% | "
        f"{sim['annual_fee_pct']*100:.2f}% | {sim['avg_syms_held']:.2f} |"
    )


def _build_report_markdown(
    step0_counts: dict[str, int] | None,
    ea_results: list[dict[str, Any]],
    best_ea: dict[str, Any],
    plateau_passed: bool,
    plateau_reasons: list[str],
    eb_entry: dict[str, Any] | None,
    eb_passed: bool | None,
    eb_reasons: list[str],
    dsr_val: float | None,
    candidates: list[dict[str, Any]],
    cand_sha: str,
    sel_sha: str,
    pbo_ea: float | None = None,
) -> str:
    lines: list[str] = [
        "# Báo Cáo Khám Phá Danh Mục Ít Được Chú Ý (Brief 237)",
        "",
        "> [!IMPORTANT]",
        "> **CẢNH BÁO THIÊN LỆCH SỐNG SÓT (SURVIVORSHIP BIAS):**",
        "> Dữ liệu `stocks_daily` gần như không có mã đã huỷ niêm yết. Các mã bị huỷ niêm yết thường có thanh khoản/giá biến động xấu ở giai đoạn cuối; thiếu chúng làm kết quả hồi cứu có nguy cơ lạc quan hoặc sai lệch phân bố tương đối.",
        "",
        "> [!WARNING]",
        "> **CẢNH BÁO ĐA SO SÁNH & GẦN HỌ ĐÃ ĐÓNG (ĐỢT 193):**",
        "> Chiến lược `I1_LOWATTN` nằm cùng họ danh mục cổ phiếu xoay vòng tháng với họ biến động thấp (đợt 193 đã đóng) và đã thử tổng cộng 9 cấu hình EA cộng 29 họ âm trước đó (`N_trials = 38` khi tính DSR). Nếu trượt bất kỳ cổng nào ở EA/Cao nguyên/EB/DSR, **0 ứng viên** là kết quả hợp lệ và không được nới cổng.",
        "",
        f"- **Tổng số dòng EA đã ghi sổ:** {len(ea_results)}",
        f"- **Tổng số dòng EB đã ghi sổ:** {1 if eb_entry is not None else 0}",
        f"- **Số ứng viên chốt:** {len(candidates)}",
        f"- **SHA256 `candidates.json`:** `{cand_sha}`",
        f"- **SHA256 `selections.json`:** `{sel_sha}`",
        "",
    ]

    if step0_counts:
        lines.append("## Bước 0: Kiểm đếm Universe (§1 & §3.2)")
        lines.append("")
        lines.append("| Mốc | Số mã thực tế | Số mã Lead đếm trước |")
        lines.append("|---|---|---|")
        for (yr, mo), exp in EXPECTED_STEP0_COUNTS.items():
            lbl = f"L({mo:02d}/{yr})"
            lines.append(f"| {lbl} | {step0_counts.get(lbl, 'N/A')} | {exp} |")
        lines.append("")

    lines.extend([
        "## Bước 1: Kết quả toàn bộ 9 cấu hình EA (L(01/2017) -> L(12/2019))",
        "",
        f"- **Mốc ETF EA (`E1VFVN30`):** CAGR = `{ETF_EA_CAGR*100:.2f}%`, MDD = `{ETF_EA_MDD*100:.2f}%`.",
        f"- **Cấu hình chọn (Sharpe_X cao nhất):** `{best_ea['params']}` (Sharpe_X = `{best_ea['metrics']['sharpe_X']:.4f}`, mean_X = `{best_ea['metrics']['mean_X']*100:.2f}%`).",
        "",
        "| Cấu hình | Số tháng | Lãi tháng TB (R_m) | Lãi tháng EW (EW_m) | Vượt trội TB (mean_X) | Sharpe_X | p | CAGR | MDD | Calmar | Cổng cũ Calmar >= 0.86 (chỉ tham khảo) | CAGR EW | Turnover tháng TB | Phí / năm (% NAV) | Mã TB / tháng |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ])
    for entry in ea_results:
        cfg_label = _config_key(entry["params"])
        if entry["params"] == best_ea["params"]:
            cfg_label = f"**{cfg_label} (đỉnh)**"
        lines.append(_format_report_row(cfg_label, entry["metrics"], entry["sim"]))

    lines.extend([
        "",
        "## Bước 2: Kiểm cao nguyên (±1 bước trên cả `S` và `N`)",
        "",
        f"- **Kết quả:** **{'ĐẠT' if plateau_passed else 'TRƯỢT'}**",
    ])
    if plateau_reasons:
        for reason in plateau_reasons:
            lines.append(f"  - Lỗi láng giềng: {reason}")
    else:
        lines.append("  - Mọi láng giềng ±1 bước theo cả `S` và `N` đều có `mean_X > 0` và `sharpe_X >= 50%` đỉnh.")

    lines.extend([
        "",
        "## Bước 3: Kiểm định EB (L(12/2019) -> L(12/2022))",
        "",
        f"- **Mốc ETF EB (`E1VFVN30`):** CAGR = `{ETF_EB_CAGR*100:.2f}%` (ngưỡng >= `{(ETF_EB_CAGR-0.01)*100:.2f}%`), MDD = `{ETF_EB_MDD*100:.2f}%` (ngưỡng <= `{(2/3*ETF_EB_MDD)*100:.2f}%`).",
    ])
    if eb_entry is None:
        lines.append("- **Kết quả:** Không chạy EB (dừng tại Bước 2 - cao nguyên).")
    else:
        lines.extend([
            f"- **Kết quả:** **{'ĐẠT' if eb_passed else 'TRƯỢT'}**",
            "",
            "| Cấu hình | Số tháng | Lãi tháng TB (R_m) | Lãi tháng EW (EW_m) | Vượt trội TB (mean_X) | Sharpe_X | p | CAGR | MDD | Calmar | Cổng cũ Calmar >= 0.86 (chỉ tham khảo) | CAGR EW | Turnover tháng TB | Phí / năm (% NAV) | Mã TB / tháng |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
            _format_report_row(_config_key(eb_entry["params"], prefix="EB_"), eb_entry["metrics"], eb_entry["sim"]),
            "",
        ])
        if eb_reasons:
            for r in eb_reasons:
                lines.append(f"  - Lý do trượt: {r}")

    lines.extend([
        "",
        "## Bước 4: DSR (n_trials = 9 + 29 = 38)",
        "",
        f"- **DSR (EA):** {'không tính' if dsr_val is None else f'{dsr_val:.4f} (ngưỡng >= 0.95 -> ' + ('ĐẠT' if dsr_val >= 0.95 else 'TRƯỢT') + ')'}",
    ])
    if pbo_ea is not None:
        lines.append(f"- PBO (EA, CSCV): {pbo_ea:.3f}")
    lines.extend([
        "",
        "## Kết luận Ứng Viên",
        "",
    ])
    if candidates:
        for c in candidates:
            lines.append(f"- `{c['idea_id']}`: `{c['params']}`, DSR = `{c['dsr']:.4f}`")
    else:
        lines.append("> **0 ứng viên** vượt qua đủ các cổng. Đóng giả thuyết, không nới cổng.")

    return "\n".join(lines) + "\n"


def run_exploration(
    data_dir: Path | str = DATA_DIR,
    ledger_path: Path | str = LEDGER_PATH,
    candidates_path: Path | str = CANDIDATES_PATH,
    report_path: Path | str = REPORT_PATH,
    selections_path: Path | str = SELECTIONS_PATH,
    verify_step0: bool = True,
    idea_id: str = IDEA_ID,
    idea_type: str = IDEA_TYPE,
    seed: int = SEED_237,
    select_symbols_fn: Callable[..., list[str]] = select_lowattn_symbols,
    dsr_fn: Callable[[float, int, float, float, list[float]], float] = compute_step4_dsr,
    report_builder_fn: Callable[..., str] = _build_report_markdown,
    grid: dict[str, list[int]] = GRID,
    pbo_fn: Callable[[np.ndarray], float] | None = None,
) -> dict[str, Any]:
    """Execute exploration workflow (§5). First line calls assert_ledger_safety."""
    assert_ledger_safety(ledger_path)

    d_dir = Path(data_dir)
    print(f"Loading data from {d_dir}...")
    sessions = load_sessions(d_dir, end=date(2022, 12, 30))
    raw_stocks = load_stocks(d_dir, end=date(2022, 12, 30))
    exchanges = load_exchanges(d_dir)

    stocks = filter_out_funds(raw_stocks)
    print(f"Symbols loaded: {len(raw_stocks)} raw -> {len(stocks)} after excluding fund certificates.")

    all_rebal = get_rebalance_dates(sessions)
    step0_counts: dict[str, int] | None = None
    if verify_step0:
        step0_counts = check_step0_universe(all_rebal, sessions, stocks)

    ea_rebal = filter_rebalance_dates(all_rebal, EA_FIRST_MONTH, EA_LAST_MONTH)
    eb_rebal = filter_rebalance_dates(all_rebal, EB_FIRST_MONTH, EB_LAST_MONTH)

    print(f"\nCalculating EW benchmark for EA ({len(ea_rebal) - 1} months)...")
    ea_ew = ew_benchmark(ea_rebal, stocks, sessions, min_turnover=MIN_TURNOVER_237)

    for out_p in (ledger_path, candidates_path, report_path, selections_path):
        Path(out_p).parent.mkdir(parents=True, exist_ok=True)

    ea_results: list[dict[str, Any]] = []
    ea_sharpes: list[float] = []
    selections_dump: dict[str, Any] = {}

    print(f"\n--- Step 1: Running EA for {idea_id} (9 configs) ---")
    for s_win in grid["S"]:
        for n_stocks in grid["N"]:
            params = {"S": s_win, "N": n_stocks}
            cfg_key = _config_key(params)
            selected_record: dict[str, list[str]] = {}
            select_fn = _make_selector(
                sessions, stocks, s_win, n_stocks, selected_record, select_symbols_fn=select_symbols_fn
            )

            sim = simulate_rotation(
                rebalance_dates=ea_rebal,
                bars_by_symbol=stocks,
                sessions=sessions,
                exchanges=exchanges,
                idea_type=idea_type,
                lookback=s_win,
                n_stocks=n_stocks,
                min_turnover=MIN_TURNOVER_237,
                select_fn=select_fn,
            )

            metrics = calculate_rotation_metrics(
                monthly_r=sim["monthly_returns"],
                monthly_ew=ea_ew,
                rebalance_dates=ea_rebal,
                portfolio_metrics=sim,
                seed=seed,
            )

            ea_sharpes.append(metrics["sharpe_X"])
            ea_results.append({
                "idea_id": idea_id,
                "params": params,
                "period": "EA",
                "sim": sim,
                "metrics": metrics,
            })

            selections_dump[cfg_key] = {
                "rebalance_dates": [d.isoformat() for d in ea_rebal],
                "selected": selected_record,
                "monthly_r": [float(x) for x in sim["monthly_returns"]],
                "monthly_ew": [float(x) for x in ea_ew],
            }

            evaluate_and_log(
                idea_id=idea_id,
                idea_fn_or_sha=idea_type,
                params=params,
                market="stock",
                period="EA",
                metrics={
                    "n": metrics["n"],
                    "mean_net": metrics["mean_X"],
                    "sharpe": metrics["sharpe_X"],
                    "p": metrics["p"],
                    "cagr": metrics["cagr"],
                    "mdd": metrics["mdd"],
                    "calmar": metrics["calmar"],
                },
                ledger_path=str(ledger_path),
            )
            print(
                f"  {cfg_key}: n={metrics['n']}, mean_X={metrics['mean_X']*100:.2f}%, "
                f"sharpe_X={metrics['sharpe_X']:.4f}, p={metrics['p']:.4f}, "
                f"CAGR={metrics['cagr']*100:.2f}%, MDD={metrics['mdd']*100:.2f}%, "
                f"Calmar={metrics['calmar']:.2f}, syms={sim['avg_syms_held']:.2f}"
            )

    best_ea = select_best_ea_config(ea_results)
    print(
        f"\n[Step 1] Best EA config by sharpe_X: {best_ea['params']} "
        f"(sharpe_X={best_ea['metrics']['sharpe_X']:.4f}, mean_X={best_ea['metrics']['mean_X']*100:.2f}%)"
    )

    pbo_ea: float | None = None
    if pbo_fn is not None:
        excess_cols = [
            np.asarray(entry["sim"]["monthly_returns"], dtype=float) - np.asarray(ea_ew, dtype=float)
            for entry in ea_results
        ]
        pbo_matrix = np.column_stack(excess_cols)
        pbo_ea = float(pbo_fn(pbo_matrix))
        print(f"[Step 1] PBO (EA, CSCV): {pbo_ea:.3f}")

    # Step 2: Plateau
    plateau_passed, plateau_reasons = check_plateau(best_ea, ea_results, grid)
    if plateau_passed:
        print("[Step 2] Plateau: PASSED (all +/- 1 step neighbors pass).")
    else:
        print(f"[Step 2] Plateau: REJECTED -> {'; '.join(plateau_reasons)}")

    # Step 3: EB (only if plateau passes)
    eb_entry: dict[str, Any] | None = None
    eb_passed: bool | None = None
    eb_reasons: list[str] = []

    if plateau_passed:
        p = best_ea["params"]
        s_win = int(p["S"])
        n_stocks = int(p["N"])
        print(f"\n--- Step 3: Running EB once for {idea_id} {p} ({len(eb_rebal) - 1} months) ---")
        eb_ew = ew_benchmark(eb_rebal, stocks, sessions, min_turnover=MIN_TURNOVER_237)
        eb_selected_record: dict[str, list[str]] = {}
        eb_select_fn = _make_selector(
            sessions, stocks, s_win, n_stocks, eb_selected_record, select_symbols_fn=select_symbols_fn
        )

        sim_eb = simulate_rotation(
            rebalance_dates=eb_rebal,
            bars_by_symbol=stocks,
            sessions=sessions,
            exchanges=exchanges,
            idea_type=idea_type,
            lookback=s_win,
            n_stocks=n_stocks,
            min_turnover=MIN_TURNOVER_237,
            select_fn=eb_select_fn,
        )
        metrics_eb = calculate_rotation_metrics(
            monthly_r=sim_eb["monthly_returns"],
            monthly_ew=eb_ew,
            rebalance_dates=eb_rebal,
            portfolio_metrics=sim_eb,
            seed=seed,
        )

        eb_entry = {
            "idea_id": idea_id,
            "params": p,
            "period": "EB",
            "sim": sim_eb,
            "metrics": metrics_eb,
        }
        selections_dump[_config_key(p, prefix="EB_")] = {
            "rebalance_dates": [d.isoformat() for d in eb_rebal],
            "selected": eb_selected_record,
            "monthly_r": [float(x) for x in sim_eb["monthly_returns"]],
            "monthly_ew": [float(x) for x in eb_ew],
        }

        evaluate_and_log(
            idea_id=idea_id,
            idea_fn_or_sha=idea_type,
            params=p,
            market="stock",
            period="EB",
            metrics={
                "n": metrics_eb["n"],
                "mean_net": metrics_eb["mean_X"],
                "sharpe": metrics_eb["sharpe_X"],
                "p": metrics_eb["p"],
                "cagr": metrics_eb["cagr"],
                "mdd": metrics_eb["mdd"],
                "calmar": metrics_eb["calmar"],
            },
            ledger_path=str(ledger_path),
        )

        eb_passed, eb_reasons = check_eb_gates(
            metrics_eb=metrics_eb,
            avg_syms_held=sim_eb["avg_syms_held"],
            n_stocks=n_stocks,
            etf_cagr=ETF_EB_CAGR,
            etf_mdd=ETF_EB_MDD,
        )
        print(
            f"  EB result: n={metrics_eb['n']}, mean_X={metrics_eb['mean_X']*100:.2f}%, "
            f"sharpe_X={metrics_eb['sharpe_X']:.4f}, p={metrics_eb['p']:.4f}, "
            f"CAGR={metrics_eb['cagr']*100:.2f}%, MDD={metrics_eb['mdd']*100:.2f}%, "
            f"Calmar={metrics_eb['calmar']:.2f}, syms={sim_eb['avg_syms_held']:.2f}"
        )
        if eb_passed:
            print("[Step 3] EB Gates: PASSED.")
        else:
            print(f"[Step 3] EB Gates: REJECTED -> {'; '.join(eb_reasons)}")

    # Step 4: DSR (only if EB passes)
    dsr_val: float | None = None
    candidates: list[dict[str, Any]] = []
    if eb_passed and eb_entry is not None:
        m_ea = best_ea["metrics"]
        dsr_val = dsr_fn(
            m_ea["sharpe_X"],
            m_ea["n"],
            m_ea["skew"],
            m_ea["kurt"],
            ea_sharpes,
        )
        print(f"\n[Step 4] DSR on EA = {dsr_val:.4f} (threshold >= 0.95)")
        if dsr_val >= 0.95:
            candidates.append({
                "idea_id": idea_id,
                "params": best_ea["params"],
                "ea_sharpe_x": m_ea["sharpe_X"],
                "eb_sharpe_x": eb_entry["metrics"]["sharpe_X"],
                "dsr": dsr_val,
            })

    with open(selections_path, "w", encoding="utf-8") as f:
        json.dump(selections_dump, f, indent=2)
    sel_sha = hashlib.sha256(Path(selections_path).read_bytes()).hexdigest()

    with open(candidates_path, "w", encoding="utf-8") as f:
        json.dump(candidates, f, indent=2)
    cand_sha = hashlib.sha256(Path(candidates_path).read_bytes()).hexdigest()

    report_md = report_builder_fn(
        step0_counts=step0_counts,
        ea_results=ea_results,
        best_ea=best_ea,
        plateau_passed=plateau_passed,
        plateau_reasons=plateau_reasons,
        eb_entry=eb_entry,
        eb_passed=eb_passed,
        eb_reasons=eb_reasons,
        dsr_val=dsr_val,
        candidates=candidates,
        cand_sha=cand_sha,
        sel_sha=sel_sha,
        **({"pbo_ea": pbo_ea} if pbo_ea is not None else {}),
    )
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(f"\nDone: {len(candidates)} candidate(s). candidates.json sha256 = {cand_sha}")
    result: dict[str, Any] = {
        "step0_counts": step0_counts,
        "ea_results": ea_results,
        "best_ea": best_ea,
        "plateau_passed": plateau_passed,
        "plateau_reasons": plateau_reasons,
        "eb_entry": eb_entry,
        "eb_passed": eb_passed,
        "eb_reasons": eb_reasons,
        "dsr": dsr_val,
        "candidates": candidates,
        "candidates_sha": cand_sha,
        "selections_sha": sel_sha,
    }
    if pbo_ea is not None:
        result["pbo_ea"] = pbo_ea
    return result


def run_step0_only(data_dir: Path | str = DATA_DIR) -> dict[str, int]:
    """Run only Step 0 universe counting without computing returns or writing ledgers."""
    d_dir = Path(data_dir)
    sessions = load_sessions(d_dir, end=date(2022, 12, 30))
    raw_stocks = load_stocks(d_dir, end=date(2022, 12, 30))
    stocks = filter_out_funds(raw_stocks)
    print(f"Step 0 loaded {len(raw_stocks)} raw symbols -> {len(stocks)} non-fund symbols.")
    all_rebal = get_rebalance_dates(sessions)
    return check_step0_universe(all_rebal, sessions, stocks)


def main() -> int:
    parser = argparse.ArgumentParser(description="Explore Brief 237 (Low Attention Rotation).")
    parser.add_argument("--step0-only", action="store_true", help="Only run Step 0 universe count check.")
    args = parser.parse_args()

    if args.step0_only:
        run_step0_only()
        return 0

    run_exploration()
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())
