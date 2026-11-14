"""Validation runner for Brief 227: Volume Spike Events + LightGBM Event Filter.

Provides `run_validation(data_dir, model_train_dir, h, start, end)` (§5):
trains LightGBM strictly on purged events from `model_train_dir` and evaluates
the ML and B0 portfolios on `data_dir` between `start` and `end`.

Note: Builder writes and tests this only on synthetic tmp_path data;
never runs it on real held-out validation data.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from lightgbm import LGBMRegressor

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.research191_data import load_exchanges, load_stocks
from scripts.research192_core import load_sessions
from scripts.research193_core import (
    calculate_rotation_metrics,
    ew_benchmark,
    get_rebalance_dates,
)
from scripts.research227_core import (
    COST_RT,
    FEATURE_NAMES,
    LGBM_PARAMS,
    MIN_TURNOVER_227,
    EventRecord,
    find_events,
    precompute_market_context,
    prepare_events_with_outcomes,
    simulate_event_portfolio,
)


def _to_date(val: date | str) -> date:
    if isinstance(val, date):
        return val
    return date.fromisoformat(val)


def run_validation(
    data_dir: Path | str,
    model_train_dir: Path | str,
    h: int,
    start: date | str,
    end: date | str,
) -> dict[str, Any]:
    """Run ML & B0 pipeline on `data_dir`, training models ONLY on `model_train_dir` (§5).

    For each calendar year Y covered by [start, end]:
    - Trains LGBMRegressor strictly on events from `model_train_dir` whose
      `sell_date < first_session_of_year_Y` (within validation period) and `y is not None`.
    - Scores validation events in year Y within [start, end].
    - Simulates both ML (score > COST_RT) and B0 portfolios on `data_dir`.
    """
    start_d = _to_date(start)
    end_d = _to_date(end)
    if end_d < start_d:
        raise ValueError(f"end ({end_d}) must be >= start ({start_d})")

    train_dir = Path(model_train_dir)
    val_dir = Path(data_dir)

    train_sessions = load_sessions(train_dir)
    train_stocks = load_stocks(train_dir)
    train_exchanges = load_exchanges(train_dir)

    val_sessions = load_sessions(val_dir, end=end_d)
    val_stocks = load_stocks(val_dir, end=end_d)
    val_exchanges = load_exchanges(val_dir)

    # 1. Prepare events in model_train_dir strictly
    train_ctx = precompute_market_context(train_stocks, min_turnover=MIN_TURNOVER_227)
    raw_train_events = find_events(
        bars_by_symbol=train_stocks,
        sessions=train_sessions,
        exchanges=train_exchanges,
        min_turnover=MIN_TURNOVER_227,
    )
    train_events_all = prepare_events_with_outcomes(
        events=raw_train_events,
        bars_by_symbol=train_stocks,
        sessions=train_sessions,
        exchanges=train_exchanges,
        h=h,
        min_turnover=MIN_TURNOVER_227,
        ctx=train_ctx,
    )

    # 2. Prepare events in validation data_dir
    val_ctx = precompute_market_context(val_stocks, min_turnover=MIN_TURNOVER_227)
    raw_val_events = find_events(
        bars_by_symbol=val_stocks,
        sessions=val_sessions,
        exchanges=val_exchanges,
        min_turnover=MIN_TURNOVER_227,
    )
    val_events_all = prepare_events_with_outcomes(
        events=raw_val_events,
        bars_by_symbol=val_stocks,
        sessions=val_sessions,
        exchanges=val_exchanges,
        h=h,
        min_turnover=MIN_TURNOVER_227,
        ctx=val_ctx,
    )
    val_events = [
        ev for ev in val_events_all if start_d <= ev.buy_date <= end_d
    ]

    # 3. Train per validation year Y strictly on purged events from model_train_dir
    active_sessions = [s for s in val_sessions if start_d <= s <= end_d]
    if not active_sessions:
        raise ValueError(f"No sessions found in {val_dir} between {start_d} and {end_d}")

    first_sess_by_year: dict[int, date] = {}
    for s in active_sessions:
        if s.year not in first_sess_by_year or s < first_sess_by_year[s.year]:
            first_sess_by_year[s.year] = s

    scores_by_key: dict[tuple[str, date], float] = {}
    train_counts_by_year: dict[int, int] = {}
    models_by_year: dict[int, LGBMRegressor] = {}

    for yr in sorted(first_sess_by_year.keys()):
        cutoff_date = first_sess_by_year[yr]
        eligible_train: list[EventRecord] = [
            ev
            for ev in train_events_all
            if ev.y is not None and ev.sell_date is not None and ev.sell_date < cutoff_date
        ]
        train_counts_by_year[yr] = len(eligible_train)
        yr_val_events = [ev for ev in val_events if ev.buy_date.year == yr]

        if not eligible_train:
            for ev in yr_val_events:
                scores_by_key[ev.key] = 0.0
            continue

        x_train = np.array(
            [[ev.features[f] for f in FEATURE_NAMES] for ev in eligible_train],
            dtype=np.float64,
        )
        y_train = np.array([float(ev.y) for ev in eligible_train], dtype=np.float64)

        model = LGBMRegressor(**LGBM_PARAMS)
        model.fit(x_train, y_train)
        models_by_year[yr] = model

        if yr_val_events:
            x_val = np.array(
                [[ev.features[f] for f in FEATURE_NAMES] for ev in yr_val_events],
                dtype=np.float64,
            )
            preds = model.predict(x_val)
            for ev, pred in zip(yr_val_events, preds):
                scores_by_key[ev.key] = float(pred)

    # 4. Simulate ML and B0 portfolios over [start_d, end_d]
    all_rebal = get_rebalance_dates(val_sessions)
    pre_rebal = [r for r in all_rebal if r < start_d]
    in_rebal = [r for r in all_rebal if start_d <= r <= end_d]
    rebal_dates = [pre_rebal[-1], *in_rebal] if pre_rebal else in_rebal
    if len(rebal_dates) < 2:
        rebal_dates = [start_d, end_d]

    ew_rets = ew_benchmark(
        rebalance_dates=rebal_dates,
        bars_by_symbol=val_stocks,
        sessions=val_sessions,
        min_turnover=MIN_TURNOVER_227,
    )

    sim_ml = simulate_event_portfolio(
        events=val_events,
        sessions=val_sessions,
        bars_by_symbol=val_stocks,
        exchanges=val_exchanges,
        h=h,
        variant="ML",
        scores=scores_by_key,
        rebalance_dates=rebal_dates,
        start_date=start_d,
        end_date=end_d,
        cost_threshold=COST_RT,
    )
    sim_b0 = simulate_event_portfolio(
        events=val_events,
        sessions=val_sessions,
        bars_by_symbol=val_stocks,
        exchanges=val_exchanges,
        h=h,
        variant="B0",
        scores=None,
        rebalance_dates=rebal_dates,
        start_date=start_d,
        end_date=end_d,
        cost_threshold=COST_RT,
    )

    ml_metrics = calculate_rotation_metrics(
        monthly_r=sim_ml["monthly_returns"],
        monthly_ew=ew_rets,
        rebalance_dates=rebal_dates,
        portfolio_metrics={
            "cagr": sim_ml["cagr"],
            "mdd": sim_ml["mdd"],
            "calmar": sim_ml["calmar"],
        },
        seed=227,
    )
    b0_metrics = calculate_rotation_metrics(
        monthly_r=sim_b0["monthly_returns"],
        monthly_ew=ew_rets,
        rebalance_dates=rebal_dates,
        portfolio_metrics={
            "cagr": sim_b0["cagr"],
            "mdd": sim_b0["mdd"],
            "calmar": sim_b0["calmar"],
        },
        seed=227,
    )
    ml_vs_b0 = calculate_rotation_metrics(
        monthly_r=sim_ml["monthly_returns"],
        monthly_ew=sim_b0["monthly_returns"],
        rebalance_dates=rebal_dates,
        portfolio_metrics={
            "cagr": sim_ml["cagr"],
            "mdd": sim_ml["mdd"],
            "calmar": sim_ml["calmar"],
        },
        seed=227,
    )

    return {
        "h": h,
        "start": start_d.isoformat(),
        "end": end_d.isoformat(),
        "n_val_events": len(val_events),
        "train_counts_by_year": train_counts_by_year,
        "scores_by_event_key": scores_by_key,
        "ml_sim": sim_ml,
        "b0_sim": sim_b0,
        "ml_metrics": ml_metrics,
        "b0_metrics": b0_metrics,
        "ml_vs_b0": ml_vs_b0,
        "models_by_year": models_by_year,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Brief 227 Validation Runner")
    parser.add_argument("--data-dir", required=True, help="Validation data directory")
    parser.add_argument("--model-train-dir", required=True, help="Exploration training data directory")
    parser.add_argument("--h", type=int, required=True, choices=[5, 10], help="Holding sessions H")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    res = run_validation(
        data_dir=args.data_dir,
        model_train_dir=args.model_train_dir,
        h=args.h,
        start=args.start,
        end=args.end,
    )
    summary = {
        "h": res["h"],
        "start": res["start"],
        "end": res["end"],
        "n_val_events": res["n_val_events"],
        "train_counts_by_year": res["train_counts_by_year"],
        "ml_metrics": {k: v for k, v in res["ml_metrics"].items() if k != "x_series"},
        "b0_metrics": {k: v for k, v in res["b0_metrics"].items() if k != "x_series"},
        "ml_vs_b0": {k: v for k, v in res["ml_vs_b0"].items() if k != "x_series"},
        "ml_closed_trades": len(res["ml_sim"]["closed_trades"]),
        "b0_closed_trades": len(res["b0_sim"]["closed_trades"]),
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())
