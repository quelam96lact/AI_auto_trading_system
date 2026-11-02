"""Validation runner for Brief 195 (Daily Trend MA + 1-Hour RSI Entry + Daily ATR Trailing Stop).

Used by Claude during validation gates V1 and V2 (§5 & §6).

CLI Arguments:
  --data-dir: Path to directory containing stocks_daily, bars_5m, sessions.csv, exchanges.csv, manifest.json.
  --candidates: Path to candidates.json.
  --candidates-sha: Expected sha256 checksum of candidates.json.
  --part: Validation part ('V1' or 'V2').
  --first-session: First session date (YYYY-MM-DD).
  --last-session: Last session date (YYYY-MM-DD).

Exit codes:
  0: All candidates passed (or empty candidates list).
  1: At least one candidate failed validation gates.
  2: candidates.json sha256 mismatch.
  3: Missing candidate file or missing inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from scripts.research191_data import load_exchanges, load_stocks
from scripts.research192_core import load_sessions
from scripts.research195_core import (
    compute_configuration_metrics,
    load_bars_5m,
    resample_1h,
    simulate_trades,
)


def validate_candidates(
    data_dir: Path | str,
    candidates_path: Path | str,
    expected_sha: str,
    part: str,
    first_session: date,
    last_session: date,
    min_trades: int = 100,
) -> int:
    """Validate candidates against holdout dataset gates (§5 & §6).

    Returns exit code:
      0: All passed or empty
      1: Failed
      2: sha mismatch
      3: missing file or error
    """
    cand_p = Path(candidates_path)
    if not cand_p.exists():
        print(f"LOI: Khong tim thay file candidates: {cand_p}")
        return 3

    actual_sha = hashlib.sha256(cand_p.read_bytes()).hexdigest()
    if actual_sha.lower() != expected_sha.lower():
        print(f"LOI: Sai checksum candidates.json: mong doi {expected_sha}, thuc te {actual_sha}")
        return 2

    with open(cand_p, "r", encoding="utf-8") as f:
        data = json.load(f)

    candidates = data.get("candidates", [])
    if not candidates:
        print("Khong co ung vien nao can kiem chung (0 ung vien). Ket qua hop le.")
        return 0

    d_dir = Path(data_dir)
    if not d_dir.exists():
        print(f"LOI: Khong tim thay data_dir: {d_dir}")
        return 3

    print(f"Tai du lieu kiem chung ({part}) tu {d_dir}...")
    try:
        sessions = load_sessions(d_dir, end=last_session)
        daily_stocks = load_stocks(d_dir, end=last_session)
        exchanges = load_exchanges(d_dir)
        bars_5m = load_bars_5m(d_dir)
    except Exception as e:
        print(f"LOI khi tai du lieu: {e}")
        return 3

    print("Resampling 5m bars to 1h...")
    bars_1h: dict[str, list[Any]] = {}
    for sym, b_list in bars_5m.items():
        bars_1h[sym] = resample_1h(b_list)

    explore_symbols = sorted(bars_5m.keys())

    all_passed = True
    for idx, cand in enumerate(candidates, 1):
        n_val = int(cand["n"])
        theta_val = float(cand["theta"])
        k_val = float(cand["k"])
        print(f"\n--- Kiem chung ung vien #{idx}: n={n_val}, theta={theta_val}, k={k_val} ({part}) ---")

        all_trades = simulate_trades(
            bars_1h_by_symbol=bars_1h,
            daily_bars_by_symbol=daily_stocks,
            sessions=sessions,
            exchanges=exchanges,
            n=n_val,
            theta=theta_val,
            k=k_val,
            explore_symbols=explore_symbols,
        )

        # Filter trades within validation window [first_session, last_session]
        trades = [
            t
            for t in all_trades
            if first_session <= t.entry_session <= last_session
        ]

        metrics = compute_configuration_metrics(trades)

        n_trades = metrics["n"]
        mean_x = metrics["mean_X"]
        p_val = metrics["p"]
        mean_r = metrics["mean_r"]

        cond_n = n_trades >= min_trades
        cond_mean_x_p = (mean_x > 0.0) and (p_val < 0.05)
        cond_mean_r = mean_r > 0.0

        cand_passed = cond_n and cond_mean_x_p and cond_mean_r

        print(f"  So lenh: {n_trades} (yeu cau >= {min_trades}) -> {'DAT' if cond_n else 'TRUOT'}")
        print(f"  mean_X: {mean_x:.6f}, p: {p_val:.4f} (yeu cau >0 & p<0.05) -> {'DAT' if cond_mean_x_p else 'TRUOT'}")
        print(f"  mean_r: {mean_r:.6f} (yeu cau >0) -> {'DAT' if cond_mean_r else 'TRUOT'}")
        print(f"  Ket qua ung vien #{idx}: {'DAT' if cand_passed else 'TRUOT'}")

        if not cand_passed:
            all_passed = False

    return 0 if all_passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Validator cho Brief 195")
    parser.add_argument("--data-dir", required=True, help="Thư mục chứa dữ liệu")
    parser.add_argument("--candidates", required=True, help="Đường dẫn candidates.json")
    parser.add_argument("--candidates-sha", required=True, help="SHA256 mong đợi của candidates.json")
    parser.add_argument("--part", required=True, choices=["V1", "V2"], help="Phần kiểm chứng (V1 hoặc V2)")
    parser.add_argument("--first-session", required=True, help="Phiên đầu (YYYY-MM-DD)")
    parser.add_argument("--last-session", required=True, help="Phiên cuối (YYYY-MM-DD)")

    args = parser.parse_args()

    first_s = date.fromisoformat(args.first_session)
    last_s = date.fromisoformat(args.last_session)

    return validate_candidates(
        data_dir=args.data_dir,
        candidates_path=args.candidates,
        expected_sha=args.candidates_sha,
        part=args.part,
        first_session=first_s,
        last_session=last_s,
    )


if __name__ == "__main__":
    sys.exit(main())
