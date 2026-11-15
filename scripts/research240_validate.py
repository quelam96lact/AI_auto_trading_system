"""Validation script for Brief 240 (Short-Term Reversal Monthly Rotation Portfolio).

Reuses scripts.research237_validate.validate_candidates with Short-Term Reversal
selector, IDEA_ID = 'I1_REV', and SEED_240 = 240.
"""

from __future__ import annotations

import argparse
import io
import sys
from datetime import date
from pathlib import Path

from scripts.research237_explore import ETF_EB_CAGR, ETF_EB_MDD
from scripts.research237_validate import validate_candidates as _validate_candidates_237
from scripts.research240_core import select_reversal_symbols
from scripts.research240_explore import IDEA_ID, IDEA_TYPE, SEED_240


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
) -> int:
    """Validate Brief 240 candidates in V1 or V2 against §6 gates."""
    return _validate_candidates_237(
        data_dir=data_dir,
        candidates_path=candidates_path,
        expected_sha=expected_sha,
        part=part,
        first_rebalance=first_rebalance,
        last_rebalance=last_rebalance,
        hurdle_cagr=hurdle_cagr,
        etf_cagr=etf_cagr,
        etf_mdd=etf_mdd,
        expected_idea_id=IDEA_ID,
        idea_type=IDEA_TYPE,
        seed=SEED_240,
        select_symbols_fn=select_reversal_symbols,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate candidates for Brief 240.")
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
