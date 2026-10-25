"""Validation script for Brief 193 (Low Volatility Monthly Rotation Portfolio).

Used by Claude during validation gates V1 and V2 (§5 & §6).

CLI Arguments:
  --data-dir: Path to directory containing stocks_daily, sessions.csv, exchanges.csv, manifest.json.
  --candidates: Path to candidates.json.
  --candidates-sha: Expected sha256 checksum of candidates.json.
  --part: Validation part ('V1' or 'V2').
  --first-rebalance: First rebalance date (YYYY-MM-DD).
  --last-rebalance: Last rebalance date (YYYY-MM-DD).
  --hurdle-cagr: Minimum CAGR required for V2 (default: 0.10).

Exit codes:
  0: All candidates passed (or empty candidates list).
  1: At least one candidate failed validation gates.
  2: candidates.json sha256 mismatch.
  3: Missing candidate file or required input files.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from datetime import date
from pathlib import Path

from scripts.research191_data import load_exchanges, load_stocks
from scripts.research192_core import load_sessions
from scripts.research193_core import (
    MIN_TURNOVER_193,
    calculate_rotation_metrics,
    ew_benchmark,
    get_rebalance_dates,
    simulate_rotation,
)
from scripts.research193_explore import IDEAS_CONFIG, filter_rebalance_dates


def validate_candidates(
    data_dir: Path | str,
    candidates_path: Path | str,
    expected_sha: str,
    part: str,
    first_rebalance: date | str,
    last_rebalance: date | str,
    hurdle_cagr: float = 0.10,
) -> int:
    cand_p = Path(candidates_path)
    if not cand_p.exists():
        print(f"ERROR: Candidates file not found: {cand_p}", file=sys.stderr)
        return 3

    actual_sha = hashlib.sha256(cand_p.read_bytes()).hexdigest()
    if actual_sha.lower() != expected_sha.lower():
        print(
            f"ERROR: SHA256 mismatch for candidates file! Expected: {expected_sha}, Got: {actual_sha}",
            file=sys.stderr,
        )
        return 2

    with open(cand_p, "r", encoding="utf-8") as f:
        candidates = json.load(f)

    if not candidates:
        print("Candidate list is empty. Validation passed trivially.")
        return 0

    d_dir = Path(data_dir)
    first_d = date.fromisoformat(str(first_rebalance))
    last_d = date.fromisoformat(str(last_rebalance))

    try:
        sessions = load_sessions(d_dir, end=last_d)
        stocks = load_stocks(d_dir, end=last_d)
        exchanges = load_exchanges(d_dir)
    except Exception as e:
        print(f"ERROR loading validation data: {e}", file=sys.stderr)
        return 3

    all_rebal = get_rebalance_dates(sessions)
    val_rebal = filter_rebalance_dates(
        all_rebal,
        (first_d.year, first_d.month),
        (last_d.year, last_d.month),
    )

    if len(val_rebal) < 2:
        print(f"ERROR: Insufficient rebalance dates ({len(val_rebal)}) between {first_d} and {last_d}", file=sys.stderr)
        return 3

    ew_rets = ew_benchmark(val_rebal, stocks, sessions, min_turnover=MIN_TURNOVER_193)

    k_candidates = len(candidates)
    alpha = 0.05 / k_candidates

    all_passed = True

    for cand in candidates:
        idea_id = cand["idea_id"]
        params = cand["params"]

        cfg = IDEAS_CONFIG.get(idea_id)
        if not cfg:
            print(f"ERROR: Unknown idea_id {idea_id}", file=sys.stderr)
            all_passed = False
            continue

        idea_type = cfg["idea_type"]
        param_name = cfg["param_name"]
        lookback = int(params[param_name])
        n_stocks = int(params["N"])

        print(f"\n--- Validating [{part}] {idea_id} ({params}) ---")
        sim = simulate_rotation(
            rebalance_dates=val_rebal,
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
            monthly_ew=ew_rets,
            rebalance_dates=val_rebal,
            portfolio_metrics=sim,
            seed=193,
        )

        mean_x = metrics["mean_X"]
        sharpe_x = metrics["sharpe_X"]
        p_val = metrics["p"]
        calmar = sim["calmar"]
        cagr = sim["cagr"]
        avg_syms = sim["avg_syms_held"]

        print(
            f"Months: {metrics['n']}, mean_X: {mean_x*100:.2f}%, Sharpe_X: {sharpe_x:.3f}, "
            f"p: {p_val:.4f} (alpha={alpha:.4f}), Calmar: {calmar:.2f}, CAGR: {cagr*100:.2f}%, "
            f"Avg Syms: {avg_syms:.1f} (target >= {0.8*n_stocks:.1f})"
        )

        reasons = []
        if mean_x <= 0:
            reasons.append("mean_X <= 0")
        if p_val >= alpha:
            reasons.append(f"p={p_val:.4f} >= alpha={alpha:.4f}")
        if calmar < 0.86:
            reasons.append(f"calmar={calmar:.2f} < 0.86")
        if avg_syms < 0.8 * n_stocks:
            reasons.append(f"avg_syms_held={avg_syms:.1f} < {0.8*n_stocks:.1f}")

        if part.upper() == "V2" and cagr <= hurdle_cagr:
            reasons.append(f"CAGR={cagr*100:.2f}% <= hurdle={hurdle_cagr*100:.2f}%")

        if reasons:
            print(f"[{idea_id}] TRƯỢT: {', '.join(reasons)}")
            all_passed = False
        else:
            print(f"[{idea_id}] ĐẠT")

    return 0 if all_passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate candidates for Brief 193.")
    parser.add_argument("--data-dir", required=True, help="Data directory path")
    parser.add_argument("--candidates", required=True, help="Path to candidates.json")
    parser.add_argument("--candidates-sha", required=True, help="Expected SHA256 of candidates.json")
    parser.add_argument("--part", required=True, choices=["V1", "V2", "v1", "v2"], help="Validation part (V1 or V2)")
    parser.add_argument("--first-rebalance", required=True, help="First rebalance date (YYYY-MM-DD)")
    parser.add_argument("--last-rebalance", required=True, help="Last rebalance date (YYYY-MM-DD)")
    parser.add_argument("--hurdle-cagr", type=float, default=0.10, help="Hurdle CAGR for V2")

    args = parser.parse_args()

    return validate_candidates(
        data_dir=args.data_dir,
        candidates_path=args.candidates,
        expected_sha=args.candidates_sha,
        part=args.part.upper(),
        first_rebalance=args.first_rebalance,
        last_rebalance=args.last_rebalance,
        hurdle_cagr=args.hurdle_cagr,
    )


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())
