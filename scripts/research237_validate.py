"""Validation script for Brief 237 (Low Attention Monthly Rotation Portfolio).

Used by Lead during validation gates V1 and V2 (§5 & §6).

CLI Arguments:
  --data-dir: Directory containing stocks_daily, sessions.csv, exchanges.csv, manifest.json.
  --candidates: Path to candidates.json.
  --candidates-sha: Expected sha256 checksum of candidates.json.
  --part: Validation part ('V1' or 'V2').
  --first-rebalance: First rebalance date (YYYY-MM-DD).
  --last-rebalance: Last rebalance date (YYYY-MM-DD).
  --hurdle-cagr: Minimum CAGR required for V2 (ETF + deposit benchmark).
  --etf-cagr: ETF buy-and-hold CAGR over the validation period.
  --etf-mdd: ETF buy-and-hold MDD over the validation period.

Exit codes:
  0: All candidates passed (or empty candidates list).
  1: At least one candidate failed validation gates.
  2: candidates.json sha256 mismatch.
  3: Missing candidate file or invalid/missing input data.
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

from scripts.research191_data import load_exchanges, load_stocks
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
    select_lowattn_symbols,
)
from scripts.research237_explore import (
    ETF_EB_CAGR,
    ETF_EB_MDD,
    IDEA_ID,
    IDEA_TYPE,
    SEED_237,
    filter_rebalance_dates,
)


def validate_candidates(
    data_dir: Path | str,
    candidates_path: Path | str,
    expected_sha: str,
    part: str,
    first_rebalance: date | str,
    last_rebalance: date | str,
    hurdle_cagr: float = 0.10,
    etf_cagr: float = ETF_EB_CAGR,
    etf_mdd: float = ETF_EB_MDD,
    expected_idea_id: str = IDEA_ID,
    idea_type: str = IDEA_TYPE,
    seed: int = SEED_237,
    select_symbols_fn: Callable[..., list[str]] = select_lowattn_symbols,
) -> int:
    """Validate candidates in V1 or V2 against §6 gates."""
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
        raw_stocks = load_stocks(d_dir, end=last_d)
        exchanges = load_exchanges(d_dir)
    except Exception as exc:
        print(f"ERROR loading validation data: {exc}", file=sys.stderr)
        return 3

    stocks = filter_out_funds(raw_stocks)
    all_rebal = get_rebalance_dates(sessions)
    val_rebal = filter_rebalance_dates(
        all_rebal,
        (first_d.year, first_d.month),
        (last_d.year, last_d.month),
    )

    if len(val_rebal) < 2:
        print(
            f"ERROR: Insufficient rebalance dates ({len(val_rebal)}) between {first_d} and {last_d}",
            file=sys.stderr,
        )
        return 3

    ew_rets = ew_benchmark(val_rebal, stocks, sessions, min_turnover=MIN_TURNOVER_237)
    alpha = 0.05 / len(candidates)
    max_mdd = (2.0 / 3.0) * etf_mdd
    min_cagr = etf_cagr - 0.01

    all_passed = True
    for cand in candidates:
        idea_id = cand["idea_id"]
        params = cand["params"]

        if idea_id != expected_idea_id:
            print(f"ERROR: Unknown idea_id {idea_id}", file=sys.stderr)
            all_passed = False
            continue

        s_win = int(params["S"])
        n_stocks = int(params["N"])
        print(f"\n--- Validating [{part}] {idea_id} ({params}) ---")

        def _select_fn(r: date, _s: int = s_win, _n: int = n_stocks) -> list[str]:
            return select_symbols_fn(
                r=r,
                sessions=sessions,
                bars_by_symbol=stocks,
                s_window=_s,
                n_stocks=_n,
                min_turnover=MIN_TURNOVER_237,
                long_window=LONG_WINDOW,
            )

        sim = simulate_rotation(
            rebalance_dates=val_rebal,
            bars_by_symbol=stocks,
            sessions=sessions,
            exchanges=exchanges,
            idea_type=idea_type,
            lookback=s_win,
            n_stocks=n_stocks,
            min_turnover=MIN_TURNOVER_237,
            select_fn=_select_fn,
        )

        metrics = calculate_rotation_metrics(
            monthly_r=sim["monthly_returns"],
            monthly_ew=ew_rets,
            rebalance_dates=val_rebal,
            portfolio_metrics=sim,
            seed=seed,
        )

        mean_x = float(metrics["mean_X"])
        sharpe_x = float(metrics["sharpe_X"])
        p_val = float(metrics["p"])
        mdd = float(sim["mdd"])
        cagr = float(sim["cagr"])
        calmar = float(sim["calmar"])
        avg_syms = float(sim["avg_syms_held"])

        print(
            f"Months: {metrics['n']}, mean_X: {mean_x*100:.2f}%, Sharpe_X: {sharpe_x:.4f}, "
            f"p: {p_val:.4f} (alpha={alpha:.4f}), CAGR: {cagr*100:.2f}% (min {min_cagr*100:.2f}%), "
            f"MDD: {mdd*100:.2f}% (max {max_mdd*100:.2f}%), Calmar: {calmar:.2f}, "
            f"Avg Syms: {avg_syms:.2f} (target >= {0.8*n_stocks:.2f})"
        )

        reasons: list[str] = []
        if mean_x <= 0:
            reasons.append("mean_X <= 0")
        if p_val >= alpha:
            reasons.append(f"p={p_val:.4f} >= alpha={alpha:.4f}")
        if mdd > max_mdd:
            reasons.append(f"MDD={mdd*100:.2f}% > {max_mdd*100:.2f}% (2/3 ETF MDD)")
        if cagr < min_cagr:
            reasons.append(f"CAGR={cagr*100:.2f}% < {min_cagr*100:.2f}% (ETF CAGR - 1pp)")
        if avg_syms < 0.8 * n_stocks:
            reasons.append(f"avg_syms_held={avg_syms:.2f} < {0.8*n_stocks:.2f}")

        if part.upper() == "V2" and cagr <= hurdle_cagr:
            reasons.append(f"CAGR={cagr*100:.2f}% <= hurdle={hurdle_cagr*100:.2f}%")

        if reasons:
            print(f"[{idea_id}] TRƯỢT: {', '.join(reasons)}")
            all_passed = False
        else:
            print(f"[{idea_id}] ĐẠT")

    return 0 if all_passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate candidates for Brief 237.")
    parser.add_argument("--data-dir", required=True, help="Data directory path")
    parser.add_argument("--candidates", required=True, help="Path to candidates.json")
    parser.add_argument("--candidates-sha", required=True, help="Expected SHA256 of candidates.json")
    parser.add_argument("--part", required=True, choices=["V1", "V2", "v1", "v2"], help="Validation part (V1 or V2)")
    parser.add_argument("--first-rebalance", required=True, help="First rebalance date (YYYY-MM-DD)")
    parser.add_argument("--last-rebalance", required=True, help="Last rebalance date (YYYY-MM-DD)")
    parser.add_argument("--hurdle-cagr", type=float, default=0.10, help="Hurdle CAGR for V2")
    parser.add_argument("--etf-cagr", type=float, default=ETF_EB_CAGR, help="ETF CAGR over validation period")
    parser.add_argument("--etf-mdd", type=float, default=ETF_EB_MDD, help="ETF MDD over validation period")

    args = parser.parse_args()

    return validate_candidates(
        data_dir=args.data_dir,
        candidates_path=args.candidates,
        expected_sha=args.candidates_sha,
        part=args.part.upper(),
        first_rebalance=args.first_rebalance,
        last_rebalance=args.last_rebalance,
        hurdle_cagr=args.hurdle_cagr,
        etf_cagr=args.etf_cagr,
        etf_mdd=args.etf_mdd,
    )


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())
