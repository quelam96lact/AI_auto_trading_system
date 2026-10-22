"""Validator CLI for Brief 188 (multi-timeframe anti-overfitting validation).

To be executed solely by Claude on holdout validation data (V1 and V2).
CLI options:
  --data-dir: directory containing validation data files.
  --candidates: path to candidates.json (default: docs/research/dot188/candidates.json).
  --candidates-sha: expected sha256 of candidates.json. Mismatch exits with code 2.
  --part: V1 or V2.

Exit codes:
  0: Success / Completed evaluation.
  2: candidates.json sha256 mismatch.
  3: Data directory or files missing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from scripts import research188_ideas
from scripts.research188_core import (
    align_higher,
    calculate_stock_baseline_excess,
    calculate_trade_metrics,
    resample,
    simulate_portfolio,
)
from scripts.research188_data import load_crypto, load_exchanges, load_stocks


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def run_candidate_validation(
    cand: dict,
    part: str,
    data_dir: str,
    stocks_data: dict,
    crypto_data: dict,
    exchanges: dict,
    alpha: float,
) -> dict:
    """Evaluate a single candidate against Section 6 validation gates."""
    idea_id = cand["idea_id"]
    market = cand["market"]
    params = cand["params"]
    rule_fn_name = cand["rule_fn"]

    rule_fn = getattr(research188_ideas, rule_fn_name)

    # Date ranges according to part
    # Stock V1: 2016-01-01 to 2022-12-31; V2: 2023-01-01 to 2026-09-30
    # Crypto V1: 2024-04-27T10:00:00+00:00 to 2026-08-31T23:00:00+00:00; V2: 2026-09-01T00:00:00+00:00 to 2026-10-19T23:59:59+00:00
    if market == "stock":
        if part == "V1":
            p_start = datetime(2016, 1, 1, 0, 0)
            p_end = datetime(2022, 12, 31, 23, 59)
        else:
            p_start = datetime(2023, 1, 1, 0, 0)
            p_end = datetime(2026, 9, 30, 23, 59)

        all_trades = []
        for sym, daily_bars in stocks_data.items():
            exch = exchanges.get(sym, "HOSE")
            weekly_bars = resample(daily_bars, "1W")
            aligned_wk = align_higher(daily_bars, weekly_bars)

            if rule_fn_name == "rule_idea3_stk_mn_trend_wk_mom":
                monthly_bars = resample(daily_bars, "1M")
                aligned_mn = align_higher(daily_bars, monthly_bars)
                trades = rule_fn(
                    daily_bars, weekly_bars, monthly_bars, aligned_wk, aligned_mn, exch, params, p_start, p_end
                )
            else:
                trades = rule_fn(
                    daily_bars, weekly_bars, aligned_wk, exch, params, p_start, p_end
                )
            all_trades.extend(trades)

        metrics = calculate_trade_metrics(all_trades)
        port = simulate_portfolio(all_trades, "stock")
        excess = calculate_stock_baseline_excess(all_trades, stocks_data)

        # Check gates
        n = metrics["n"]
        if n < 100:
            verdict = "THIEU SUC MANH"
            reason = f"n={n} < 100"
        else:
            mean_net = metrics["mean_net"]
            p_val = metrics["p"]
            calmar = port["calmar"]
            trim_excess = excess["mean_excess_trim1pct"]

            passed = (
                mean_net > 0.0
                and p_val < alpha
                and calmar >= 0.86
                and trim_excess > 0.0
            )
            verdict = "DAT" if passed else "TRUOT"
            reason = f"mean_net={mean_net:.4f}, p={p_val:.4f} (alpha={alpha:.4f}), calmar={calmar:.2f}, trim_excess={trim_excess:.4f}"

        return {
            "idea_id": idea_id,
            "part": part,
            "n": n,
            "mean_net": metrics["mean_net"],
            "p": metrics["p"],
            "calmar": port["calmar"],
            "verdict": verdict,
            "reason": reason,
        }

    else:  # crypto
        if part == "V1":
            p_start = datetime(2024, 4, 27, 10, 0)
            p_end = datetime(2026, 8, 31, 23, 0)
        else:
            p_start = datetime(2026, 9, 1, 0, 0)
            p_end = datetime(2026, 10, 19, 23, 59)

        all_trades = []
        for sym, bars_1h in crypto_data.items():
            bars_4h = resample(bars_1h, "4h")
            bars_1d = resample(bars_1h, "1d")
            aligned_4h = align_higher(bars_1h, bars_4h)
            aligned_1d = align_higher(bars_1h, bars_1d)

            trades = rule_fn(
                bars_1h, bars_4h, bars_1d, aligned_4h, aligned_1d, params, p_start, p_end
            )
            all_trades.extend(trades)

        metrics = calculate_trade_metrics(all_trades)
        port = simulate_portfolio(all_trades, "crypto")

        n = metrics["n"]
        if n < 100:
            verdict = "THIEU SUC MANH"
            reason = f"n={n} < 100"
        else:
            mean_net = metrics["mean_net"]
            p_val = metrics["p"]
            calmar = port["calmar"]
            mean_gross = (
                sum(t.gross_return for t in all_trades) / n if n > 0 else 0.0
            )
            crypto_gross_target = 1.5 * 0.0014  # 0.21%

            passed = (
                mean_net > 0.0
                and p_val < alpha
                and calmar >= 0.86
                and mean_gross >= crypto_gross_target
            )
            verdict = "DAT" if passed else "TRUOT"
            reason = f"mean_net={mean_net:.4f}, p={p_val:.4f} (alpha={alpha:.4f}), calmar={calmar:.2f}, mean_gross={mean_gross:.4f}"

        return {
            "idea_id": idea_id,
            "part": part,
            "n": n,
            "mean_net": metrics["mean_net"],
            "p": metrics["p"],
            "calmar": port["calmar"],
            "verdict": verdict,
            "reason": reason,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Brief 188 Holdout Validator")
    parser.add_argument("--data-dir", required=True, help="Directory containing validation data")
    parser.add_argument("--candidates", default="docs/research/dot188/candidates.json", help="Candidates JSON file")
    parser.add_argument("--candidates-sha", required=True, help="Expected sha256 of candidates.json")
    parser.add_argument("--part", required=True, choices=["V1", "V2"], help="Validation part: V1 or V2")

    args = parser.parse_args()

    # 1. Verify candidates sha
    cand_path = Path(args.candidates)
    if not cand_path.exists():
        print(f"Error: {cand_path} does not exist.", file=sys.stderr)
        return 2

    actual_cand_sha = compute_sha256(cand_path)
    if actual_cand_sha.lower() != args.candidates_sha.lower():
        print(
            f"Error: candidates sha mismatch. Expected {args.candidates_sha}, got {actual_cand_sha}",
            file=sys.stderr,
        )
        return 2

    # 2. Verify data directory exists
    data_dir_path = Path(args.data_dir)
    if not data_dir_path.exists() or not (data_dir_path / "manifest.json").exists():
        print(f"Error: data directory {args.data_dir} missing or invalid.", file=sys.stderr)
        return 3

    # Load candidates
    with open(cand_path, "r", encoding="utf-8") as f:
        candidates = json.load(f)

    k = len(candidates)
    if k == 0:
        print("No candidates registered (0 candidates is a valid result).")
        return 0

    alpha = 0.05 / k

    # Load validation data
    # Cutoffs depend on part: V2 stocks up to 2026-09-30, V2 crypto up to 2026-10-19
    max_d_stk = "2026-09-30" if args.part == "V2" else "2022-12-31"
    max_ts_cry = "2026-10-19T23:59:59+00:00" if args.part == "V2" else "2026-08-31T23:00:00+00:00"

    try:
        stocks_data = load_stocks(args.data_dir, max_date=max_d_stk)
    except FileNotFoundError:
        stocks_data = {}

    try:
        crypto_data = load_crypto(args.data_dir, max_ts=max_ts_cry)
    except FileNotFoundError:
        crypto_data = {}

    exchanges = load_exchanges(args.data_dir)

    print(f"=== HOLD-OUT VALIDATION REPORT: PART {args.part} (k={k}, alpha={alpha:.4f}) ===")
    all_passed = True
    for cand in candidates:
        res = run_candidate_validation(
            cand, args.part, args.data_dir, stocks_data, crypto_data, exchanges, alpha
        )
        print(
            f"Candidate: {res['idea_id']:<26} | n={res['n']:>4} | mean_net={res['mean_net']:>7.4f} | "
            f"p={res['p']:>6.4f} | calmar={res['calmar']:>5.2f} | VERDICT: {res['verdict']}"
        )
        print(f"  Details: {res['reason']}")
        if res["verdict"] != "DAT":
            all_passed = False

    print("==========================================================================")
    print(f"OVERALL PART {args.part}: {'ALL CANDIDATES PASSED' if all_passed else 'SOME CANDIDATES FAILED/UNDERPOWERED'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
