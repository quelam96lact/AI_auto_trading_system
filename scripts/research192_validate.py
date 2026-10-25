"""Validation script for Brief 192 (Calendar effects: TOM & PREHOL).

Used by Claude during validation gates V1 and V2 (§5 & §6).

CLI Arguments:
  --data-dir: Path to directory containing stocks_daily, sessions.csv, exchanges.csv, manifest.json.
  --candidates: Path to candidates.json.
  --candidates-sha: Expected sha256 checksum of candidates.json.
  --part: Validation part ('V1' or 'V2').
  --start: Start date (YYYY-MM-DD).
  --end: End date (YYYY-MM-DD).
  --etf-hurdle-cagr: Minimum CAGR required for V2 (default: 0.10).

Exit codes:
  0: All candidates passed (or empty candidates list).
  1: At least one candidate failed validation gates.
  2: candidates.json sha256 mismatch.
  3: Missing candidate file or required input files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from scripts.research188_core import (
    calculate_trade_metrics,
    simulate_portfolio,
)
from scripts.research191_data import (
    load_exchanges,
    load_stocks,
)
from scripts.research192_core import (
    generate_calendar_trades,
    load_sessions,
    time_baseline_excess,
)
from scripts.research192_explore import (
    compute_bootstrap_p,
    run_windows_for_idea,
)


def validate_candidates(
    data_dir: Path | str,
    candidates_path: Path | str,
    expected_sha: str,
    part: str,
    start_date: date | str,
    end_date: date | str,
    etf_hurdle_cagr: float = 0.10,
) -> int:
    cand_p = Path(candidates_path)
    if not cand_p.exists():
        print(f"ERROR: Candidates file not found: {cand_p}", file=sys.stderr)
        return 3

    # Check candidates.json checksum
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
    p_start = date.fromisoformat(str(start_date))
    p_end = date.fromisoformat(str(end_date))

    try:
        sessions = load_sessions(d_dir, end=p_end)
        stocks = load_stocks(d_dir, end=p_end)
        exchanges = load_exchanges(d_dir)
    except Exception as e:
        print(f"ERROR loading validation data: {e}", file=sys.stderr)
        return 3

    k_candidates = len(candidates)
    alpha = 0.05 / k_candidates

    all_passed = True

    for cand in candidates:
        idea_id = cand["idea_id"]
        params = cand["params"]

        print(f"\n--- Validating [{part}] {idea_id} ({params}) ---")
        windows = run_windows_for_idea(idea_id, params, sessions)
        trades = generate_calendar_trades(
            windows=windows,
            bars_by_symbol=stocks,
            sessions=sessions,
            exchanges=exchanges,
            period_start=p_start,
            period_end=p_end,
        )

        n_trades = len(trades)
        if n_trades < 100:
            print(f"[{idea_id}] THIẾU SỨC MẠNH: n={n_trades} < 100")
            all_passed = False
            continue

        metrics = calculate_trade_metrics(trades)
        p_val = compute_bootstrap_p(trades, seed=192)
        port = simulate_portfolio(
            trades,
            market="stock",
            initial_capital=100_000_000.0,
            start_date=p_start,
            end_date=p_end,
        )
        baseline = time_baseline_excess(trades, stocks, sessions, p_start, p_end)

        net_mean = metrics["mean_net"]
        calmar = port["calmar"]
        excess_trim = baseline["mean_excess_trim1pct"]
        cagr = port["cagr"]

        print(f"Trades: {n_trades}, Net Mean: {net_mean*100:.2f}%, p-value: {p_val:.4f} (alpha={alpha:.4f}), Calmar: {calmar:.2f}, Excess Trim1%: {excess_trim*100:.2f}%, CAGR: {cagr*100:.2f}%")

        reasons = []
        if net_mean <= 0:
            reasons.append("net_mean <= 0")
        if p_val >= alpha:
            reasons.append(f"p={p_val:.4f} >= alpha={alpha:.4f}")
        if calmar < 0.86:
            reasons.append(f"calmar={calmar:.2f} < 0.86")
        if excess_trim <= 0:
            reasons.append(f"excess_trim={excess_trim*100:.2f}% <= 0")

        if part.upper() == "V2" and cagr < etf_hurdle_cagr:
            reasons.append(f"CAGR={cagr*100:.2f}% < hurdle={etf_hurdle_cagr*100:.2f}%")

        if reasons:
            print(f"[{idea_id}] TRƯỢT: {', '.join(reasons)}")
            all_passed = False
        else:
            print(f"[{idea_id}] ĐẠT")

    return 0 if all_passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate candidates for Brief 192.")
    parser.add_argument("--data-dir", required=True, help="Data directory path")
    parser.add_argument("--candidates", required=True, help="Path to candidates.json")
    parser.add_argument("--candidates-sha", required=True, help="Expected SHA256 of candidates.json")
    parser.add_argument("--part", required=True, choices=["V1", "V2", "v1", "v2"], help="Validation part (V1 or V2)")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--etf-hurdle-cagr", type=float, default=0.10, help="ETF hurdle CAGR for V2")

    args = parser.parse_args()

    return validate_candidates(
        data_dir=args.data_dir,
        candidates_path=args.candidates,
        expected_sha=args.candidates_sha,
        part=args.part.upper(),
        start_date=args.start,
        end_date=args.end,
        etf_hurdle_cagr=args.etf_hurdle_cagr,
    )


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())
