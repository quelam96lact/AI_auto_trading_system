"""Core logic for Brief 245: Ceiling-Lock Continuation Event Study (IS-only infra).

Implements:
- §1: IS data loader rejecting dates > 2022-12-30 (reusing research191_data).
- §2: E3 ceiling-lock event detection (band - 0.005 <= r_t <= band + 0.02,
      first in chain, close_t == high_t, exclude fund certificates,
      skip first bar, GTGD20 up to t-1 >= 1B VND).
- §3: Trade simulation for H in {3, 5, 10} (entry open[t+1], exit close[t+H]
      or latest bar in [t+3, t+H] per T+2, no overlapping holds per symbol,
      transaction costs from trading.paper_broker, EW benchmark).
- §4: Weekly-clustered bootstrap (10,000, seed 245), Holm correction,
      PBO (trial_ledger), plateau check, and DSR (overfit_core, n_trials = 35).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import kurtosis, skew

from scripts.overfit_core import deflated_sharpe
from scripts.research191_data import StockDailyBar, load_exchanges, load_stocks
from scripts.research191_exits import is_liquid
from scripts.research237_core import is_fund_symbol
from scripts.trial_ledger import PRIOR_NEGATIVE_FAMILIES, pbo_for_exploration
from trading.metrics import holm_adjust
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.stock_study import bootstrap_by_month, limit_rate

IS_EVENT_START_DATE = date(2017, 1, 1)
IS_END_DATE = date(2022, 12, 30)
MIN_TURNOVER_245 = 1_000_000_000.0  # 1 billion VND
BAND_LOWER_TOL = 0.005
BAND_UPPER_TOL = 0.02
HOLDING_HORIZONS: tuple[int, ...] = (3, 5, 10)
BOOT_N = 10_000
BOOT_SEED = 245
MIN_IS_TRADES = 100
DSR_THRESHOLD = 0.95
HOLM_ALPHA = 0.05
_FLOAT_EPS = 1e-12


@dataclass(slots=True)
class CeilingEvent:
    symbol: str
    event_date: date
    exchange: str
    band: float
    r_t: float
    close_t: float
    high_t: float


@dataclass(slots=True)
class Trade245:
    symbol: str
    horizon: int
    exchange: str
    event_date: date
    entry_date: date
    exit_date: date
    entry_open: float
    exit_close: float
    r_net: float
    r_ew: float
    excess_x: float


@dataclass(slots=True)
class SimulationResult245:
    horizon: int
    trades: list[Trade245]
    skipped_missing_entry: int
    skipped_missing_exit: int
    skipped_holding: int


def load_is_data(
    data_dir: Path | str,
    end: date | str = IS_END_DATE,
) -> tuple[dict[str, list[StockDailyBar]], dict[str, str]]:
    """Load IS stocks and exchanges, strictly rejecting any date > 2022-12-30."""
    end_d = end if isinstance(end, date) else date.fromisoformat(str(end))
    if end_d > IS_END_DATE:
        raise ValueError(
            f"IS end date {end_d} exceeds maximum allowed IS_END_DATE {IS_END_DATE}"
        )
    stocks = load_stocks(data_dir, end=end_d)
    exchanges = load_exchanges(data_dir)
    return stocks, exchanges


def is_ceiling_hit(r_t: float, band: float) -> bool:
    """Return True if r_t is within [band - 0.005, band + 0.02] (with 1e-12 float tol)."""
    return (band - BAND_LOWER_TOL - _FLOAT_EPS) <= r_t <= (
        band + BAND_UPPER_TOL + _FLOAT_EPS
    )


def build_sessions(bars_by_symbol: dict[str, list[StockDailyBar]]) -> list[date]:
    """Return sorted unique trading dates across all symbols."""
    return sorted({b.date for bars in bars_by_symbol.values() for b in bars})


def detect_ceiling_events(
    bars_by_symbol: dict[str, list[StockDailyBar]],
    exchanges: dict[str, str],
    sessions: list[date] | None = None,
    min_turnover: float = MIN_TURNOVER_245,
    start_date: date | None = IS_EVENT_START_DATE,
) -> list[CeilingEvent]:
    """Detect E3 ceiling-lock events (§2) across the universe.

    Criteria at bar i (date t) for symbol m:
    - Not a fund certificate (is_fund_symbol(m) is False).
    - Not the symbol's first bar in the dataset (i >= 1).
    - Event date t >= start_date (default 2017-01-01 for IS window).
    - t-1 is the symbol's immediately preceding bar (bars[i - 1]), independent of
      market-wide sessions.
    - band = limit_rate(exchange); r_t = close_t / close_{t-1} - 1.
    - band - 0.005 <= r_t <= band + 0.02.
    - First in chain: symbol's preceding bar t-1 did NOT hit ceiling (vs bars[i - 2]).
    - Locked: close_t == high_t.
    - Liquidity: 20-session avg turnover (close * volume) up to t-1 >= min_turnover.
    """
    _ = sessions  # kept in signature for caller compatibility

    events: list[CeilingEvent] = []
    for sym, bars in bars_by_symbol.items():
        if is_fund_symbol(sym):
            continue
        exch = exchanges.get(sym, "")
        band = limit_rate(exch)

        for i, bar in enumerate(bars):
            if i == 0:
                continue
            if start_date is not None and bar.date < start_date:
                continue

            prev_bar = bars[i - 1]
            if prev_bar.close <= 0.0 or bar.close <= 0.0 or bar.high <= 0.0:
                continue

            r_t = (bar.close / prev_bar.close) - 1.0
            if not is_ceiling_hit(r_t, band):
                continue

            # First in chain: symbol's immediately preceding bar (i - 1) must not have hit ceiling
            if i >= 2:
                prev2_close = bars[i - 2].close
                if prev2_close > 0.0:
                    r_prev = (prev_bar.close / prev2_close) - 1.0
                    if is_ceiling_hit(r_prev, band):
                        continue

            # Locked at ceiling: close_t == high_t
            if bar.close != bar.high:
                continue

            # Liquidity: 20-session avg turnover up to t-1 >= 1B VND
            if not is_liquid(bars, i - 1, min_turnover=min_turnover):
                continue

            events.append(
                CeilingEvent(
                    symbol=sym,
                    event_date=bar.date,
                    exchange=exch or "UNKNOWN",
                    band=band,
                    r_t=r_t,
                    close_t=bar.close,
                    high_t=bar.high,
                )
            )

    events.sort(key=lambda e: (e.event_date, e.symbol))
    return events


def compute_trade_net_return(entry_open: float, exit_close: float) -> float:
    """Compute net trade return using paper_broker cost constants."""
    if entry_open <= 0.0:
        raise ValueError(f"entry_open must be positive, got {entry_open}")
    s_bps = SLIPPAGE_BPS / 10_000.0
    buy_cost_factor = 1.0 + FEE_RATE + s_bps
    sell_return_factor = 1.0 - FEE_RATE - SELL_TAX_RATE - s_bps
    return (exit_close * sell_return_factor) / (entry_open * buy_cost_factor) - 1.0


def compute_ew_return(
    event_date: date,
    entry_date: date,
    exit_date: date,
    bars_by_symbol: dict[str, list[StockDailyBar]],
    bar_idx_by_sym: dict[str, dict[date, int]],
    min_turnover: float = MIN_TURNOVER_245,
) -> float | None:
    """Compute Equal-Weighted benchmark return from open[t+1] to close[exit_date].

    Universe: non-fund symbols with bars at entry_date and exit_date,
    and GTGD20 up to event_date (t) >= min_turnover.
    """
    rets: list[float] = []
    for sym, bars in bars_by_symbol.items():
        if is_fund_symbol(sym):
            continue
        idx_map = bar_idx_by_sym[sym]
        idx_t = idx_map.get(event_date)
        idx_entry = idx_map.get(entry_date)
        idx_exit = idx_map.get(exit_date)
        if idx_t is None or idx_entry is None or idx_exit is None:
            continue
        if not is_liquid(bars, idx_t, min_turnover=min_turnover):
            continue
        entry_px = bars[idx_entry].open
        exit_px = bars[idx_exit].close
        if entry_px <= 0.0 or exit_px <= 0.0:
            continue
        rets.append((exit_px / entry_px) - 1.0)

    if not rets:
        return None
    return sum(rets) / len(rets)


def simulate_horizon(
    events: list[CeilingEvent],
    bars_by_symbol: dict[str, list[StockDailyBar]],
    sessions: list[date],
    horizon: int,
    min_turnover: float = MIN_TURNOVER_245,
) -> SimulationResult245:
    """Simulate trades for a fixed horizon H in {3, 5, 10} (§3)."""
    if horizon < 3:
        raise ValueError(f"horizon must be >= 3 (T+2 earliest sellable at t+3), got {horizon}")

    sess_idx = {d: i for i, d in enumerate(sessions)}
    bar_idx_by_sym = {
        sym: {b.date: i for i, b in enumerate(bars)}
        for sym, bars in bars_by_symbol.items()
    }

    sorted_events = sorted(events, key=lambda e: (e.event_date, e.symbol))
    active_exit_by_sym: dict[str, date] = {}
    trades: list[Trade245] = []
    skipped_missing_entry = 0
    skipped_missing_exit = 0
    skipped_holding = 0

    for ev in sorted_events:
        s_idx = sess_idx.get(ev.event_date)
        if s_idx is None or s_idx + 1 >= len(sessions):
            skipped_missing_entry += 1
            continue

        entry_date = sessions[s_idx + 1]

        # Skip if symbol is currently held at entry_date
        prev_exit = active_exit_by_sym.get(ev.symbol)
        if prev_exit is not None and entry_date <= prev_exit:
            skipped_holding += 1
            continue

        sym_bars = bars_by_symbol.get(ev.symbol, [])
        sym_idx_map = bar_idx_by_sym.get(ev.symbol, {})
        entry_bar_idx = sym_idx_map.get(entry_date)
        if entry_bar_idx is None:
            skipped_missing_entry += 1
            continue
        entry_open = sym_bars[entry_bar_idx].open
        if entry_open <= 0.0:
            skipped_missing_entry += 1
            continue

        # Exit at t+H, or latest bar in [t+3, t+H] (T+2 settlement)
        max_exit_s_idx = min(s_idx + horizon, len(sessions) - 1)
        exit_date: date | None = None
        exit_close = 0.0
        for k in range(max_exit_s_idx, s_idx + 2, -1):
            cand_date = sessions[k]
            cand_bar_idx = sym_idx_map.get(cand_date)
            if cand_bar_idx is not None and sym_bars[cand_bar_idx].close > 0.0:
                exit_date = cand_date
                exit_close = sym_bars[cand_bar_idx].close
                break

        if exit_date is None:
            skipped_missing_exit += 1
            continue

        r_net = compute_trade_net_return(entry_open, exit_close)
        r_ew_opt = compute_ew_return(
            event_date=ev.event_date,
            entry_date=entry_date,
            exit_date=exit_date,
            bars_by_symbol=bars_by_symbol,
            bar_idx_by_sym=bar_idx_by_sym,
            min_turnover=min_turnover,
        )
        r_ew = r_ew_opt if r_ew_opt is not None else 0.0
        excess_x = r_net - r_ew

        trades.append(
            Trade245(
                symbol=ev.symbol,
                horizon=horizon,
                exchange=ev.exchange,
                event_date=ev.event_date,
                entry_date=entry_date,
                exit_date=exit_date,
                entry_open=entry_open,
                exit_close=exit_close,
                r_net=r_net,
                r_ew=r_ew,
                excess_x=excess_x,
            )
        )
        active_exit_by_sym[ev.symbol] = exit_date

    return SimulationResult245(
        horizon=horizon,
        trades=trades,
        skipped_missing_entry=skipped_missing_entry,
        skipped_missing_exit=skipped_missing_exit,
        skipped_holding=skipped_holding,
    )


def cluster_bootstrap_p_by_week(
    trades: list[Trade245],
    n_boot: int = BOOT_N,
    seed: int = BOOT_SEED,
) -> float:
    """One-sided bootstrap p-value clustered by ISO calendar week of t+1 (entry_date)."""
    if not trades:
        return 1.0
    by_week: dict[tuple[int, int], list[float]] = {}
    for tr in trades:
        iso = tr.entry_date.isocalendar()
        w_key = (iso.year, iso.week)
        by_week.setdefault(w_key, []).append(tr.excess_x)

    res = bootstrap_by_month(
        by_week,
        n=n_boot,
        seed=seed,
        ci_low_pct=0.05,
        ci_high_pct=0.95,
    )
    return float(res["p"]) if res["p"] is not None else 1.0


def holm_adjusted_pvalues(p_by_name: dict[str, float]) -> dict[str, float]:
    """Compute step-down Holm-Bonferroni adjusted p-values."""
    items = sorted(p_by_name.items(), key=lambda kv: kv[1])
    m = len(items)
    adj: dict[str, float] = {}
    running_max = 0.0
    for i, (name, p) in enumerate(items):
        scaled = min(1.0, (m - i) * p)
        running_max = max(running_max, scaled)
        adj[name] = running_max
    return adj


def _summarize_excess(vals: list[float]) -> dict[str, Any]:
    n = len(vals)
    if n == 0:
        return {
            "n": 0,
            "mean_x": 0.0,
            "median_x": 0.0,
            "win_rate_x": 0.0,
            "sharpe_x": 0.0,
        }
    arr = np.asarray(vals, dtype=float)
    mean_x = float(np.mean(arr))
    median_x = float(np.median(arr))
    win_rate_x = float(np.mean(arr > 0.0))
    std_x = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    sharpe_x = (mean_x / std_x) if (std_x > 0.0 and math.isfinite(std_x)) else 0.0
    return {
        "n": n,
        "mean_x": mean_x,
        "median_x": median_x,
        "win_rate_x": win_rate_x,
        "sharpe_x": sharpe_x,
    }


def compute_horizon_stats(
    sim: SimulationResult245,
    n_boot: int = BOOT_N,
    seed: int = BOOT_SEED,
) -> dict[str, Any]:
    """Compute §4 statistics for one horizon simulation."""
    xs = [t.excess_x for t in sim.trades]
    summary = _summarize_excess(xs)
    p_boot = cluster_bootstrap_p_by_week(sim.trades, n_boot=n_boot, seed=seed)

    by_year_vals: dict[int, list[float]] = {}
    by_exch_vals: dict[str, list[float]] = {}
    for tr in sim.trades:
        by_year_vals.setdefault(tr.entry_date.year, []).append(tr.excess_x)
        by_exch_vals.setdefault(tr.exchange, []).append(tr.excess_x)

    by_year = {y: _summarize_excess(v) for y, v in sorted(by_year_vals.items())}
    by_exchange = {e: _summarize_excess(v) for e, v in sorted(by_exch_vals.items())}

    return {
        "horizon": sim.horizon,
        **summary,
        "p_boot": p_boot,
        "skipped_missing_entry": sim.skipped_missing_entry,
        "skipped_missing_exit": sim.skipped_missing_exit,
        "skipped_holding": sim.skipped_holding,
        "by_year": by_year,
        "by_exchange": by_exchange,
    }


def check_plateau(best_h: int, stats_by_h: dict[int, dict[str, Any]]) -> bool:
    """Check plateau: neighbors along 3 <-> 5 <-> 10 must have mean_X > 0."""
    neighbors_map = {
        3: (5,),
        5: (3, 10),
        10: (5,),
    }
    neighbors = neighbors_map.get(best_h, ())
    if not neighbors:
        return False
    return all(stats_by_h[nb]["mean_x"] > 0.0 for nb in neighbors)


def build_monthly_excess_matrix(
    sims_by_h: dict[int, SimulationResult245],
    horizons: tuple[int, ...] = HOLDING_HORIZONS,
) -> tuple[list[tuple[int, int]], np.ndarray]:
    """Build (T x 3) matrix of monthly mean X by t+1 calendar month."""
    months_set: set[tuple[int, int]] = set()
    by_h_month: dict[int, dict[tuple[int, int], list[float]]] = {}
    for h in horizons:
        m_map: dict[tuple[int, int], list[float]] = {}
        for tr in sims_by_h[h].trades:
            ym = (tr.entry_date.year, tr.entry_date.month)
            months_set.add(ym)
            m_map.setdefault(ym, []).append(tr.excess_x)
        by_h_month[h] = m_map

    months = sorted(months_set)
    mat = np.zeros((len(months), len(horizons)), dtype=float)
    for r_i, ym in enumerate(months):
        for c_i, h in enumerate(horizons):
            vals = by_h_month[h].get(ym, [])
            mat[r_i, c_i] = float(np.mean(vals)) if vals else 0.0
    return months, mat


def evaluate_is_gates(
    sims_by_h: dict[int, SimulationResult245],
    n_boot: int = BOOT_N,
    seed: int = BOOT_SEED,
) -> dict[str, Any]:
    """Evaluate all §4 statistics, PBO, plateau, DSR, and IS pass/fail gates."""
    stats_by_h = {
        h: compute_horizon_stats(sims_by_h[h], n_boot=n_boot, seed=seed)
        for h in HOLDING_HORIZONS
    }

    p_raw = {f"H{h}": stats_by_h[h]["p_boot"] for h in HOLDING_HORIZONS}
    p_holm_map = holm_adjusted_pvalues(p_raw)
    holm_sig_map = holm_adjust(p_raw, alpha=HOLM_ALPHA)
    for h in HOLDING_HORIZONS:
        key = f"H{h}"
        stats_by_h[h]["p_holm"] = p_holm_map[key]
        stats_by_h[h]["holm_pass"] = holm_sig_map[key]

    months, month_mat = build_monthly_excess_matrix(sims_by_h)
    pbo_val: float | None = (
        pbo_for_exploration(month_mat) if len(months) >= 4 else None
    )

    best_h = max(HOLDING_HORIZONS, key=lambda h: stats_by_h[h]["sharpe_x"])
    best_stats = stats_by_h[best_h]
    plateau_pass = check_plateau(best_h, stats_by_h)

    best_xs = np.asarray(
        [t.excess_x for t in sims_by_h[best_h].trades], dtype=float
    )
    n_obs = len(best_xs)
    if n_obs > 2 and float(np.std(best_xs, ddof=1)) > 0.0:
        sr_skew = float(skew(best_xs, bias=False))
        sr_kurt = float(kurtosis(best_xs, fisher=False, bias=False))
    else:
        sr_skew = 0.0
        sr_kurt = 3.0

    sharpes = [stats_by_h[h]["sharpe_x"] for h in HOLDING_HORIZONS]
    sr_trials_var = float(np.var(sharpes, ddof=1)) if len(sharpes) > 1 else 0.0
    n_trials = len(HOLDING_HORIZONS) + PRIOR_NEGATIVE_FAMILIES  # 3 + 32 = 35
    dsr_val = deflated_sharpe(
        sr=best_stats["sharpe_x"],
        n_obs=n_obs,
        skew=sr_skew,
        kurt=sr_kurt,
        n_trials=n_trials,
        sr_trials_var=sr_trials_var,
    )

    is_pass = (
        best_stats["n"] >= MIN_IS_TRADES
        and best_stats["mean_x"] > 0.0
        and best_stats["p_holm"] < HOLM_ALPHA
        and plateau_pass
        and dsr_val >= DSR_THRESHOLD
    )

    return {
        "stats_by_h": stats_by_h,
        "pbo": pbo_val,
        "pbo_months": len(months),
        "best_h": best_h,
        "plateau_pass": plateau_pass,
        "n_trials": n_trials,
        "dsr": dsr_val,
        "is_pass": is_pass,
    }
