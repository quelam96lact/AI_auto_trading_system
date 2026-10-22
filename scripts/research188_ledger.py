"""Trial ledger for Brief 188 (multi-timeframe anti-overfitting research).

Enforces:
- Append-only recording of every evaluated configuration.
- Fixed schema: utc_ts, idea_id, idea_sha, market, period, params_json, n, mean_net, sharpe, p, cagr, mdd, calmar.
- Hard budget: raises if rows with period == 'EA' exceed 400.
- Immutability: raises if an existing idea_id is evaluated with a different idea_sha.
- Ceiling of at most 6 ideas.
"""

from __future__ import annotations

import csv
import hashlib
import inspect
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LEDGER_COLUMNS = [
    "utc_ts",
    "idea_id",
    "idea_sha",
    "market",
    "period",
    "params_json",
    "n",
    "mean_net",
    "sharpe",
    "p",
    "cagr",
    "mdd",
    "calmar",
]


def compute_idea_sha(idea_fn_or_src: Callable | str) -> str:
    """Compute sha256 hex digest of idea rule function source code."""
    if isinstance(idea_fn_or_src, str):
        src = idea_fn_or_src
    else:
        src = inspect.getsource(idea_fn_or_src)
    return hashlib.sha256(src.encode("utf-8")).hexdigest()


def evaluate_and_log(
    idea_id: str,
    idea_fn_or_sha: Callable | str,
    params: dict[str, Any],
    market: str,
    period: str,
    metrics: dict[str, Any],
    ledger_path: str = "docs/research/dot188/trial_ledger.csv",
) -> None:
    """Evaluate and log configuration to trial ledger with budget and sha validation.

    Raises:
        ValueError: if period == 'EA' and EA count exceeds 400.
        ValueError: if idea_id has a different idea_sha in existing ledger.
        ValueError: if number of distinct ideas exceeds 6.
    """
    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Compute idea_sha
    if isinstance(idea_fn_or_sha, str) and len(idea_fn_or_sha) == 64 and all(c in "0123456789abcdefABCDEF" for c in idea_fn_or_sha):
        idea_sha = idea_fn_or_sha.lower()
    else:
        idea_sha = compute_idea_sha(idea_fn_or_sha)

    # Read existing entries to verify invariants
    ea_count = 0
    existing_sha_by_idea: dict[str, str] = {}
    distinct_ideas: set[str] = set()

    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                i_id = row.get("idea_id", "")
                i_sha = row.get("idea_sha", "")
                p_period = row.get("period", "")

                distinct_ideas.add(i_id)
                if i_id not in existing_sha_by_idea:
                    existing_sha_by_idea[i_id] = i_sha
                elif existing_sha_by_idea[i_id] != i_sha:
                    # Inconsistent existing data
                    pass

                if p_period == "EA":
                    ea_count += 1

    # Check invariants
    # 1. Budget of EA evaluations <= 400
    if period == "EA" and ea_count >= 400:
        raise ValueError(
            f"Hard budget exceeded: ledger already has {ea_count} 'EA' rows (maximum 400 allowed)."
        )

    # 2. Idea sha immutability
    if idea_id in existing_sha_by_idea and existing_sha_by_idea[idea_id] != idea_sha:
        raise ValueError(
            f"idea_id '{idea_id}' was previously logged with sha {existing_sha_by_idea[idea_id][:8]}..., "
            f"cannot reuse id with new sha {idea_sha[:8]}... Must create a new idea_id."
        )

    # 3. Maximum 6 distinct ideas
    if idea_id not in distinct_ideas and len(distinct_ideas) >= 6:
        raise ValueError(
            f"Idea budget exceeded: already reached 6 distinct ideas ({distinct_ideas})."
        )

    # Prepare row
    utc_ts = datetime.now(UTC).isoformat()
    params_json = json.dumps(params, sort_keys=True)

    row_data = {
        "utc_ts": utc_ts,
        "idea_id": idea_id,
        "idea_sha": idea_sha,
        "market": market,
        "period": period,
        "params_json": params_json,
        "n": metrics.get("n", 0),
        "mean_net": f"{metrics.get('mean_net', 0.0):.6f}",
        "sharpe": f"{metrics.get('sharpe', 0.0):.4f}",
        "p": f"{metrics.get('p', 1.0):.4f}",
        "cagr": f"{metrics.get('cagr', 0.0):.4f}",
        "mdd": f"{metrics.get('mdd', 0.0):.4f}",
        "calmar": f"{metrics.get('calmar', 0.0):.4f}",
    }

    file_is_new = not path.exists() or path.stat().st_size == 0
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_COLUMNS)
        if file_is_new:
            writer.writeheader()
        writer.writerow(row_data)
