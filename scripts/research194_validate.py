"""Validation runner for Brief 194 (Swing: Weekly MA + Daily RSI + ATR Chandelier Stop).

Used by Claude during validation gates V1 and V2 (§5 & §6).

CLI Arguments:
  --data-dir: Path to directory containing stocks_daily, sessions.csv, exchanges.csv, manifest.json.
  --candidates: Path to candidates.json.
  --candidates-sha: Expected sha256 checksum of candidates.json.
  --part: Validation part ('V1' or 'V2').
  --first-rebalance: First rebalance date (YYYY-MM-DD).
  --last-rebalance: Last rebalance date (YYYY-MM-DD).
  --hurdle-cagr: Minimum CAGR required for V2 (REQUIRED when --part V2, NO default value!).

Exit codes:
  0: All candidates passed (or empty candidates list).
  1: At least one candidate failed validation gates.
  2: candidates.json sha256 mismatch.
  3: Missing candidate file, missing inputs, or missing --hurdle-cagr on V2.
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
    calculate_rotation_metrics,
    ew_benchmark,
    get_rebalance_dates,
)
from scripts.research194_core import (
    MIN_TURNOVER_194,
    simulate_swing_portfolio,
)


def validate_candidates(
    data_dir: Path | str,
    candidates_path: Path | str,
    expected_sha: str,
    part: str,
    first_rebalance: date,
    last_rebalance: date,
    hurdle_cagr: float | None = None,
    min_closed_trades: int = 100,
) -> int:
    """Validate candidates against holdout dataset gates (§5 & §6)."""
    cand_p = Path(candidates_path)
    if not cand_p.exists():
        print(f"ERROR: candidates file not found: {cand_p}")
        return 3

    actual_sha = hashlib.sha256(cand_p.read_bytes()).hexdigest()
    if actual_sha.lower() != expected_sha.lower():
        print(f"ERROR: SHA256 mismatch! Expected: {expected_sha}, Actual: {actual_sha}")
        return 2

    part_upper = part.upper()
    if part_upper == "V2" and hurdle_cagr is None:
        print("ERROR: --hurdle-cagr is mandatory when --part V2!")
        return 3

    try:
        candidates = json.loads(cand_p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: Failed to parse candidates.json: {e}")
        return 3

    if not candidates:
        print("Candidate list is empty. Validation passed trivially.")
        return 0

    d_dir = Path(data_dir)
    try:
        sessions = load_sessions(d_dir)
        stocks = load_stocks(d_dir)
        exchanges = load_exchanges(d_dir)
    except Exception as e:
        print(f"ERROR: Failed to load data from {d_dir}: {e}")
        return 3

    all_rebal = get_rebalance_dates(sessions)
    rebal_dates = [r for r in all_rebal if first_rebalance <= r <= last_rebalance]
    if len(rebal_dates) < 2:
        print(
            f"ERROR: Less than 2 rebalance dates found between {first_rebalance} and {last_rebalance}"
        )
        return 3

    print(
        f"Running {part_upper} validation across {len(rebal_dates)-1} monthly periods "
        f"({rebal_dates[0]} -> {rebal_dates[-1]})..."
    )
    ew_rets = ew_benchmark(rebal_dates, stocks, sessions, min_turnover=MIN_TURNOVER_194)

    alpha = 0.05
    all_passed = True

    for cand in candidates:
        idea_id = cand["idea_id"]
        params = cand["params"]
        n_val = int(params["n"])
        theta_val = float(params["theta"])
        k_val = float(params["k"])

        print(f"\n--- Testing Candidate: {idea_id} ({params}) ---")
        sim = simulate_swing_portfolio(
            sessions=sessions,
            bars_by_symbol=stocks,
            exchanges=exchanges,
            rebalance_dates=rebal_dates,
            n=n_val,
            theta=theta_val,
            k=k_val,
            min_turnover=MIN_TURNOVER_194,
        )

        portfolio_metrics = {
            "cagr": sim["cagr"],
            "mdd": sim["mdd"],
            "calmar": sim["calmar"],
        }
        metrics = calculate_rotation_metrics(
            monthly_r=sim["monthly_returns"],
            monthly_ew=ew_rets,
            rebalance_dates=rebal_dates,
            portfolio_metrics=portfolio_metrics,
            seed=194,
        )

        n_trades = len(sim["closed_trades"])
        mean_x = metrics["mean_X"]
        p_val = metrics["p"]
        calmar = metrics["calmar"]
        cagr = metrics["cagr"]

        print(
            f"Results: mean_X={mean_x*100:.2f}%, p={p_val:.4f}, Calmar={calmar:.2f}, "
            f"CAGR={cagr*100:.2f}%, Closed Trades={n_trades}"
        )

        cand_failed = []
        if mean_x <= 0:
            cand_failed.append(f"mean_X={mean_x*100:.2f}% <= 0")
        if p_val >= alpha:
            cand_failed.append(f"p={p_val:.4f} >= {alpha}")
        if calmar < 0.86:
            cand_failed.append(f"Calmar={calmar:.2f} < 0.86")
        if n_trades < min_closed_trades:
            cand_failed.append(f"closed_trades={n_trades} < {min_closed_trades}")

        if part_upper == "V2":
            assert hurdle_cagr is not None
            if cagr <= hurdle_cagr:
                cand_failed.append(
                    f"CAGR={cagr*100:.2f}% <= hurdle={hurdle_cagr*100:.2f}%"
                )

        if cand_failed:
            print(f"TRƯỢT: {', '.join(cand_failed)}")
            all_passed = False
        else:
            print("ĐẠT")

    return 0 if all_passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Brief 194 Validation Gate Runner")
    parser.add_argument("--data-dir", required=True, help="Data directory path")
    parser.add_argument("--candidates", required=True, help="Path to candidates.json")
    parser.add_argument(
        "--candidates-sha", required=True, help="Expected SHA256 of candidates.json"
    )
    parser.add_argument(
        "--part",
        required=True,
        choices=["V1", "V2", "v1", "v2"],
        help="Validation part (V1 or V2)",
    )
    parser.add_argument(
        "--first-rebalance", required=True, help="First rebalance date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--last-rebalance", required=True, help="Last rebalance date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--hurdle-cagr",
        type=float,
        default=None,
        help="Required CAGR threshold for V2 (MANDATORY on V2, no default)",
    )

    args = parser.parse_args()

    # Enforce mandatory --hurdle-cagr on V2
    if args.part.upper() == "V2" and args.hurdle_cagr is None:
        print("ERROR: --hurdle-cagr is mandatory when --part V2!")
        return 3

    first_d = date.fromisoformat(args.first_rebalance)
    last_d = date.fromisoformat(args.last_rebalance)

    return validate_candidates(
        data_dir=args.data_dir,
        candidates_path=args.candidates,
        expected_sha=args.candidates_sha,
        part=args.part,
        first_rebalance=first_d,
        last_rebalance=last_d,
        hurdle_cagr=args.hurdle_cagr,
    )


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())
