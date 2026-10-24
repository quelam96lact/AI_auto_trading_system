"""Validation CLI for Brief 191 (Holdout validation runner).

Used by Claude to validate registered candidates on holdout sets (§4.3, §5).
CLI:
  uv run python -m scripts.research191_validate \\
    --data-dir <dir> \\
    --candidates docs/research/dot191/candidates.json \\
    --candidates-sha <sha256> \\
    --part V1|V2 \\
    --end YYYY-MM-DD

Exit codes:
  0: Execution completed normally (verdicts printed per candidate).
  2: Candidates sha256 mismatch.
  3: Candidates file missing.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from scripts.research188_core import (
    calculate_trade_metrics,
    simulate_portfolio,
)
from scripts.research191_data import (
    join_daily,
    load_exchanges,
    load_foreign_flow,
    load_stocks,
)
from scripts.research191_exits import (
    Trade191,
    liquid_baseline_excess,
)
from scripts.research191_ideas import generate_trades_for_idea
from trading.stock_study import bootstrap_by_month


def compute_bootstrap_p(trades: list[Trade191], seed: int = 191) -> float:
    if not trades:
        return 1.0
    by_month: dict[tuple[int, int], list[float]] = {}
    for t in trades:
        m_key = (t.entry_ts.year, t.entry_ts.month)
        if m_key not in by_month:
            by_month[m_key] = []
        by_month[m_key].append(t.net_return)

    res = bootstrap_by_month(by_month, n=2000, seed=seed, ci_low_pct=0.05, ci_high_pct=0.95)
    return float(res["p"]) if res["p"] is not None else 1.0


def validate_candidates(
    data_dir: Path | str,
    candidates_path: Path | str,
    candidates_sha: str | None,
    part: str,
    end_date_str: str,
    etf_hurdle_cagr: float = 0.083,  # 8.30%/năm (§5)
) -> int:
    cand_p = Path(candidates_path)
    if not cand_p.exists():
        print(f"Candidates file not found: {cand_p}", file=sys.stderr)
        return 3

    # Check sha256
    with open(cand_p, "rb") as f:
        actual_sha = hashlib.sha256(f.read()).hexdigest().lower()

    if candidates_sha is not None and actual_sha != candidates_sha.lower():
        print(
            f"Candidates sha256 mismatch: expected {candidates_sha}, got {actual_sha}",
            file=sys.stderr,
        )
        return 2

    with open(cand_p, "r", encoding="utf-8") as f:
        cand_doc = json.load(f)

    candidates: list[dict[str, Any]] = cand_doc.get("candidates", [])
    if not candidates:
        print("Không có ứng viên nào để kiểm chứng (0 ứng viên đăng ký).")
        return 0

    k = len(candidates)
    alpha = 0.05 / k
    print(f"Kiểm chứng {k} ứng viên trên phần {part} (ngưỡng alpha = {alpha:.4f}):\n")

    # Determine date range
    end_d = date.fromisoformat(end_date_str)
    if part == "V1":
        start_d = date(2020, 3, 1)
        end_d = min(date(2022, 12, 30), end_d)
    elif part == "V2":
        start_d = date(2023, 1, 1)
    else:
        print(f"Unknown part {part}, must be V1 or V2", file=sys.stderr)
        return 1

    print(f"Nạp dữ liệu từ {data_dir} (ngày kết thúc {end_d})...")
    stocks = load_stocks(data_dir, end=end_d)
    flows = load_foreign_flow(data_dir, end=end_d)
    exchanges = load_exchanges(data_dir)
    all_joined = join_daily(stocks, flows)

    all_passed = True

    for idx, cand in enumerate(candidates, 1):
        idea_id = cand["idea_id"]
        params = cand["params"]
        print(f"--- Ứng viên {idx}/{k}: {idea_id} ({params}) ---")

        trades = generate_trades_for_idea(
            idea_id=idea_id,
            params=params,
            all_joined=all_joined,
            exchanges=exchanges,
            start_date=start_d,
            end_date=end_d,
        )

        n = len(trades)
        if n < 100:
            print(f"  Kết quả: THIẾU SỨC MẠNH (n = {n} < 100)")
            all_passed = False
            continue

        metrics = calculate_trade_metrics(trades)
        p_val = compute_bootstrap_p(trades, seed=191)
        metrics["p"] = p_val

        sim = simulate_portfolio(
            trades,
            market="stock",
            initial_capital=100_000_000.0,
            start_date=start_d,
            end_date=end_d,
        )
        metrics.update(sim)

        base = liquid_baseline_excess(trades, all_joined)
        metrics.update(base)

        mean_net = metrics["mean_net"]
        calmar = metrics["calmar"]
        cagr = metrics["cagr"]
        excess_trim = metrics["mean_excess_trim1pct"]

        print(
            f"  Số lệnh: n={n}, Lãi ròng TB: {mean_net*100:.2f}%, p={p_val:.4f}, "
            f"Calmar: {calmar:.2f}, CAGR: {cagr*100:.2f}%, Vượt baseline trim1%: {excess_trim*100:.2f}%"
        )

        failures: list[str] = []
        if mean_net <= 0:
            failures.append("Lãi ròng TB <= 0")
        if p_val >= alpha:
            failures.append(f"p={p_val:.4f} >= alpha={alpha:.4f}")
        if calmar < 0.86:
            failures.append(f"Calmar={calmar:.2f} < 0.86")
        if excess_trim <= 0:
            failures.append(f"Vượt baseline trim1%={excess_trim*100:.2f}% <= 0")
        if part == "V2" and cagr <= etf_hurdle_cagr:
            failures.append(f"CAGR={cagr*100:.2f}% <= mốc ETF {etf_hurdle_cagr*100:.2f}%")

        if failures:
            print(f"  Kết quả: TRƯỢT ({', '.join(failures)})")
            all_passed = False
        else:
            print("  Kết quả: ĐẠT")

    return 0 if all_passed else 1


def main() -> None:
    if sys.stdout is not None and hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if sys.stderr is not None and hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Validate candidates on holdout data.")
    parser.add_argument("--data-dir", required=True, help="Data directory.")
    parser.add_argument(
        "--candidates",
        default="docs/research/dot191/candidates.json",
        help="Path to candidates.json.",
    )
    parser.add_argument(
        "--candidates-sha",
        default=None,
        help="Expected sha256 of candidates.json.",
    )
    parser.add_argument(
        "--part",
        required=True,
        choices=["V1", "V2"],
        help="Validation part (V1: unobserved symbols, V2: later time period).",
    )
    parser.add_argument(
        "--end",
        required=True,
        help="End date YYYY-MM-DD.",
    )
    parser.add_argument(
        "--etf-hurdle-cagr",
        type=float,
        default=0.083,
        help="CAGR hurdle rate for V2 (default: 0.083).",
    )
    args = parser.parse_args()

    rc = validate_candidates(
        data_dir=args.data_dir,
        candidates_path=args.candidates,
        candidates_sha=args.candidates_sha,
        part=args.part,
        end_date_str=args.end,
        etf_hurdle_cagr=args.etf_hurdle_cagr,
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
