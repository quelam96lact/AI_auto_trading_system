"""Core infrastructure for Brief 227: Volume Spike Events + LightGBM Event Filter.

Implements the pre-registered rules in
`docs/superpowers/plans/2026-11-13-brief-dot-227-khoi-luong-dot-bien-hoc-may.md`:
- §3.1 find_events & count_precheck_events
- §3.2 event_trade
- §3.3 compute_event_features & precompute_market_context
- §3.4 compute_event_label
- §3.5 train_and_score (with strict purge sell_date < first_session_of_year_Y)
- §3.6 simulate_event_portfolio (10 slots, daily NAV & MDD, 48-month stats)
- §3.7 shuffled-label control within calendar year of buy_date
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, cast

import numpy as np
from lightgbm import LGBMRegressor
from scipy.stats import spearmanr

from scripts.research188_core import compute_stock_net_return, deflated_sharpe
from scripts.research188_ledger import evaluate_and_log
from scripts.research191_data import StockDailyBar, load_exchanges, load_stocks
from scripts.research191_exits import assert_ledger_safety, is_floor_locked
from scripts.research192_core import load_sessions
from scripts.research193_core import (
    calculate_rotation_metrics,
    ew_benchmark,
    get_rebalance_dates,
)
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.stock_study import entry_status

__all__ = [
    "BUY_COST_FACTOR",
    "BUY_FEE_RATE",
    "COST_RT",
    "FEATURE_NAMES",
    "INITIAL_CAPITAL",
    "K_SLOTS",
    "LGBM_PARAMS",
    "MIN_TURNOVER_227",
    "PRIOR_NEGATIVE_FAMILIES",
    "SELL_FEE_RATE",
    "SELL_RETURN_FACTOR",
    "VOL_MULT",
    "ClosedEventTrade",
    "EventRecord",
    "MarketContext",
    "StockDailyBar",
    "TradeOutcome",
    "assert_ledger_safety",
    "calculate_rotation_metrics",
    "compute_event_features",
    "compute_event_label",
    "count_precheck_events",
    "deflated_sharpe",
    "entry_status",
    "evaluate_and_log",
    "event_trade",
    "ew_benchmark",
    "find_events",
    "get_rebalance_dates",
    "is_floor_locked",
    "load_exchanges",
    "load_sessions",
    "load_stocks",
    "precompute_market_context",
    "prepare_events_with_outcomes",
    "simulate_event_portfolio",
    "train_and_score",
]

MIN_TURNOVER_227 = 5_000_000_000.0  # 5 tỷ VND
VOL_MULT = 2.0
PRIOR_NEGATIVE_FAMILIES = 28
K_SLOTS = 10
INITIAL_CAPITAL = 100_000_000.0

SLIPPAGE_RATE = SLIPPAGE_BPS / 10_000.0
BUY_FEE_RATE = FEE_RATE + SLIPPAGE_RATE
SELL_FEE_RATE = FEE_RATE + SELL_TAX_RATE + SLIPPAGE_RATE
BUY_COST_FACTOR = 1.0 + BUY_FEE_RATE
SELL_RETURN_FACTOR = 1.0 - SELL_FEE_RATE
COST_RT = 2.0 * FEE_RATE + SELL_TAX_RATE + 2.0 * SLIPPAGE_RATE

FEATURE_NAMES: tuple[str, ...] = (
    "vol_ratio",
    "log_gt20",
    "ret_1",
    "ret_5",
    "ret_20",
    "ret_60",
    "dist_ma20",
    "dist_ma50",
    "dist_high_60",
    "vol_20",
    "range_t",
    "close_pos",
    "gap_open",
    "events_20",
    "mkt_ret_20",
    "mkt_breadth",
)

LGBM_PARAMS: dict[str, Any] = {
    "n_estimators": 200,
    "learning_rate": 0.05,
    "num_leaves": 15,
    "min_child_samples": 50,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "random_state": 42,
    "deterministic": True,
    "force_row_wise": True,
    "n_jobs": 1,
    "verbose": -1,
}


@dataclass(slots=True)
class TradeOutcome:
    """Trade simulation result for a single event (§3.2)."""

    buy_date: date
    buy_price: float
    sell_date: date | None
    sell_price: float | None
    gross: float | None
    exit_reason: str  # "TIME" or "END"


@dataclass(slots=True)
class EventRecord:
    """Complete event record with features, trade outcome, and excess label."""

    symbol: str
    bar_idx: int
    signal_date: date
    buy_date: date
    buy_price: float
    exchange: str
    gt20: float
    vol_ratio: float
    features: dict[str, float] = field(default_factory=dict)
    sell_date: date | None = None
    sell_price: float | None = None
    gross: float | None = None
    mkt: float | None = None
    y: float | None = None
    exit_reason: str = "TIME"

    @property
    def key(self) -> tuple[str, date]:
        return (self.symbol, self.signal_date)


@dataclass(slots=True)
class ClosedEventTrade:
    """Closed trade from portfolio simulation (§3.6)."""

    symbol: str
    signal_date: date
    entry_date: date
    entry_price: float
    exit_date: date
    exit_price: float
    exit_reason: str  # "TIME" or "END"
    holding_sessions: int
    net_return: float
    score: float


@dataclass(slots=True)
class _ActivePosition:
    symbol: str
    signal_date: date
    entry_date: date
    entry_s_idx: int
    entry_price: float
    shares: float
    score: float


@dataclass(slots=True)
class MarketContext:
    """Precomputed fast lookup indices for symbols, bars, and daily liquid stats."""

    sym_date_bar: dict[str, dict[date, StockDailyBar]]
    sym_date_idx: dict[str, dict[date, int]]
    liquid_syms_prev20: dict[date, list[tuple[str, int]]]
    liquid_syms_end20: dict[date, list[tuple[str, int]]]
    mkt_features_by_date: dict[date, tuple[float, float]] = field(default_factory=dict)


def _normalize_bars_input(
    bars_by_symbol: dict[str, list[StockDailyBar]] | list[StockDailyBar],
) -> dict[str, list[StockDailyBar]]:
    if isinstance(bars_by_symbol, list):
        if not bars_by_symbol:
            return {}
        sym = bars_by_symbol[0].symbol
        return {sym: bars_by_symbol}
    return bars_by_symbol


def count_precheck_events(
    bars_by_symbol: dict[str, list[StockDailyBar]],
    min_turnover: float = MIN_TURNOVER_227,
    vol_mult: float = VOL_MULT,
) -> dict[str, Any]:
    """Count events satisfying §3.1 conditions 1-4 (excluding condition 5) by year.

    Also counts distinct symbols reaching GTGD20 >= min_turnover per year under
    the prior-20 window (t-20..t-1) for t >= 120, t >= 20, and inclusive t >= 19.
    """
    events_by_year: dict[int, int] = {}
    syms_gt20_t120: dict[int, set[str]] = {}
    syms_gt20_t20: dict[int, set[str]] = {}
    syms_gt20_incl: dict[int, set[str]] = {}

    for sym, bars in bars_by_symbol.items():
        n = len(bars)
        if n < 20:
            continue
        closes = [b.close for b in bars]
        vols = [b.volume for b in bars]
        turnovers = [c * v for c, v in zip(closes, vols)]

        # Prefix sums for O(1) window means
        pref_tv = [0.0] * (n + 1)
        pref_vol = [0.0] * (n + 1)
        for i in range(n):
            pref_tv[i + 1] = pref_tv[i] + turnovers[i]
            pref_vol[i + 1] = pref_vol[i] + vols[i]

        for t in range(19, n):
            yr = bars[t].date.year
            gt20_incl = (pref_tv[t + 1] - pref_tv[t - 19]) / 20.0
            if gt20_incl >= min_turnover:
                syms_gt20_incl.setdefault(yr, set()).add(sym)

            if t < 20:
                continue
            gt20 = (pref_tv[t] - pref_tv[t - 20]) / 20.0
            if gt20 >= min_turnover:
                syms_gt20_t20.setdefault(yr, set()).add(sym)

            if t < 120:
                continue
            if gt20 < min_turnover:
                continue
            syms_gt20_t120.setdefault(yr, set()).add(sym)

            v20 = (pref_vol[t] - pref_vol[t - 20]) / 20.0
            if v20 <= 0.0:
                continue
            if vols[t] < vol_mult * v20:
                continue
            if closes[t] <= closes[t - 1]:
                continue

            events_by_year[yr] = events_by_year.get(yr, 0) + 1

    return {
        "total_events": sum(events_by_year.values()),
        "events_by_year": dict(sorted(events_by_year.items())),
        "liquid_symbols_by_year_t120": {
            yr: len(s) for yr, s in sorted(syms_gt20_t120.items())
        },
        "liquid_symbols_by_year_t20": {
            yr: len(s) for yr, s in sorted(syms_gt20_t20.items())
        },
        "liquid_symbols_by_year_incl": {
            yr: len(s) for yr, s in sorted(syms_gt20_incl.items())
        },
    }


def _passes_cond_234(
    bars: list[StockDailyBar],
    idx: int,
    min_turnover: float,
    vol_mult: float,
) -> tuple[bool, float, float]:
    """Check §3.1 conditions 2, 3, 4 at index `idx` (requires idx >= 20)."""
    if idx < 20:
        return False, 0.0, 0.0
    window = bars[idx - 20 : idx]
    gt20 = sum(b.close * b.volume for b in window) / 20.0
    if gt20 < min_turnover:
        return False, gt20, 0.0
    v20 = sum(b.volume for b in window) / 20.0
    if v20 <= 0.0 or bars[idx].volume < vol_mult * v20:
        return False, gt20, v20
    if bars[idx].close <= bars[idx - 1].close:
        return False, gt20, v20
    return True, gt20, v20


def find_events(
    bars_by_symbol: dict[str, list[StockDailyBar]] | list[StockDailyBar],
    sessions: list[date],
    exchanges: Mapping[str, str] | None = None,
    min_turnover: float = MIN_TURNOVER_227,
    vol_mult: float = VOL_MULT,
    require_cond5: bool = True,
) -> list[EventRecord]:
    """Find volume spike events according to Brief 227 §3.1.

    Conditions at close of bar index `t` for symbol:
    1. t >= 120 (at least 120 bars before t)
    2. GT20 = mean(close * volume for t-20..t-1) >= min_turnover (5e9)
    3. V20 = mean(volume for t-20..t-1) > 0 and volume[t] >= vol_mult * V20
    4. close[t] > close[t-1]
    5. entry_status(bars, t, exchange) == 'ok' AND bar t+1 falls on sessions[i_t + 1]
    """
    bars_dict = _normalize_bars_input(bars_by_symbol)
    exch_map = exchanges or {}
    sess_idx_map = {d: i for i, d in enumerate(sessions)}
    events: list[EventRecord] = []

    for sym, bars in bars_dict.items():
        n = len(bars)
        if n <= 120:
            continue

        exch = exch_map.get(sym, "HOSE")
        closes = [b.close for b in bars]
        vols = [b.volume for b in bars]
        pref_tv = [0.0] * (n + 1)
        pref_vol = [0.0] * (n + 1)
        for i in range(n):
            pref_tv[i + 1] = pref_tv[i] + closes[i] * vols[i]
            pref_vol[i + 1] = pref_vol[i] + vols[i]

        for t in range(120, n):
            gt20 = (pref_tv[t] - pref_tv[t - 20]) / 20.0
            if gt20 < min_turnover:
                continue

            v20 = (pref_vol[t] - pref_vol[t - 20]) / 20.0
            if v20 <= 0.0:
                continue

            vol_ratio = vols[t] / v20
            if vols[t] < vol_mult * v20:
                continue

            if closes[t] <= closes[t - 1]:
                continue

            sig_date = bars[t].date
            i_t = sess_idx_map.get(sig_date)
            if i_t is None:
                continue

            if require_cond5:
                if t + 1 >= n or i_t + 1 >= len(sessions):
                    continue
                expected_buy_date = sessions[i_t + 1]
                if bars[t + 1].date != expected_buy_date:
                    continue
                if entry_status(cast(Any, bars), t, exch) != "ok":
                    continue
                buy_date = bars[t + 1].date
                buy_price = bars[t + 1].open
            else:
                if t + 1 < n and i_t + 1 < len(sessions):
                    buy_date = bars[t + 1].date
                    buy_price = bars[t + 1].open
                else:
                    buy_date = sig_date
                    buy_price = closes[t]

            events.append(
                EventRecord(
                    symbol=sym,
                    bar_idx=t,
                    signal_date=sig_date,
                    buy_date=buy_date,
                    buy_price=buy_price,
                    exchange=exch,
                    gt20=gt20,
                    vol_ratio=vol_ratio,
                )
            )

    events.sort(key=lambda e: (e.signal_date, e.symbol))
    return events


def event_trade(
    bars: list[StockDailyBar],
    t: int,
    sessions: list[date],
    h: int,
    exchange: str | None = "HOSE",
    sess_idx_map: dict[date, int] | None = None,
) -> TradeOutcome:
    """Simulate a single event trade (§3.2).

    - Buys at open of bar e = t + 1.
    - Sells at open of first bar of symbol with date >= sessions[i_e + h].
    - Retries at subsequent bar opens if sell bar is floor-locked.
    - Returns sell_date=None, sell_price=None, gross=None, exit_reason='END'
      if data ends before a valid non-floor sell bar exists.
    """
    e = t + 1
    if e >= len(bars):
        return TradeOutcome(
            buy_date=bars[t].date,
            buy_price=bars[t].close,
            sell_date=None,
            sell_price=None,
            gross=None,
            exit_reason="END",
        )

    buy_bar = bars[e]
    buy_date = buy_bar.date
    buy_price = buy_bar.open
    if sess_idx_map is None:
        sess_idx_map = {d: i for i, d in enumerate(sessions)}

    i_e = sess_idx_map.get(buy_date)
    if i_e is None or i_e + h >= len(sessions):
        return TradeOutcome(
            buy_date=buy_date,
            buy_price=buy_price,
            sell_date=None,
            sell_price=None,
            gross=None,
            exit_reason="END",
        )

    target_date = sessions[i_e + h]

    # Find first bar index > e with date >= target_date
    sell_idx: int | None = None
    for idx in range(e + 1, len(bars)):
        if bars[idx].date >= target_date:
            sell_idx = idx
            break

    if sell_idx is None:
        return TradeOutcome(
            buy_date=buy_date,
            buy_price=buy_price,
            sell_date=None,
            sell_price=None,
            gross=None,
            exit_reason="END",
        )

    # Check floor lock and defer if locked
    while sell_idx < len(bars):
        b = bars[sell_idx]
        prev_close = bars[sell_idx - 1].close
        if not is_floor_locked(prev_close, b.high, b.low, exchange):
            gross = (b.open / buy_price - 1.0) if buy_price > 0 else None
            return TradeOutcome(
                buy_date=buy_date,
                buy_price=buy_price,
                sell_date=b.date,
                sell_price=b.open,
                gross=gross,
                exit_reason="TIME",
            )
        sell_idx += 1

    return TradeOutcome(
        buy_date=buy_date,
        buy_price=buy_price,
        sell_date=None,
        sell_price=None,
        gross=None,
        exit_reason="END",
    )


def precompute_market_context(
    bars_by_symbol: dict[str, list[StockDailyBar]],
    min_turnover: float = MIN_TURNOVER_227,
) -> MarketContext:
    """Precompute fast lookup maps for market features and labels."""
    sym_date_bar: dict[str, dict[date, StockDailyBar]] = {}
    sym_date_idx: dict[str, dict[date, int]] = {}
    liquid_syms_prev20: dict[date, list[tuple[str, int]]] = {}
    liquid_syms_end20: dict[date, list[tuple[str, int]]] = {}

    for sym, bars in bars_by_symbol.items():
        d_bar: dict[date, StockDailyBar] = {}
        d_idx: dict[date, int] = {}
        n = len(bars)
        pref_tv = [0.0] * (n + 1)
        for i, b in enumerate(bars):
            d_bar[b.date] = b
            d_idx[b.date] = i
            pref_tv[i + 1] = pref_tv[i] + b.close * b.volume

        sym_date_bar[sym] = d_bar
        sym_date_idx[sym] = d_idx

        for i in range(19, n):
            dt = bars[i].date
            gt20_end = (pref_tv[i + 1] - pref_tv[i - 19]) / 20.0
            if gt20_end >= min_turnover:
                liquid_syms_end20.setdefault(dt, []).append((sym, i))
            if i >= 20:
                gt20_prev = (pref_tv[i] - pref_tv[i - 20]) / 20.0
                if gt20_prev >= min_turnover:
                    liquid_syms_prev20.setdefault(dt, []).append((sym, i))

    return MarketContext(
        sym_date_bar=sym_date_bar,
        sym_date_idx=sym_date_idx,
        liquid_syms_prev20=liquid_syms_prev20,
        liquid_syms_end20=liquid_syms_end20,
    )


def _compute_mkt_features_on_date(
    d: date,
    bars_by_symbol: dict[str, list[StockDailyBar]],
    min_turnover: float,
    ctx: MarketContext | None = None,
) -> tuple[float, float]:
    """Compute (mkt_ret_20, mkt_breadth) at date `d` using only bars up to date `d`."""
    if ctx is not None and d in ctx.mkt_features_by_date:
        return ctx.mkt_features_by_date[d]

    rets_20: list[float] = []
    up_flags: list[float] = []

    if ctx is not None:
        candidates = ctx.liquid_syms_prev20.get(d, ())
        for sym, idx_d in candidates:
            bars = bars_by_symbol[sym]
            c_now = bars[idx_d].close
            c_20 = bars[idx_d - 20].close
            c_1 = bars[idx_d - 1].close
            if c_20 > 0 and c_1 > 0:
                rets_20.append(c_now / c_20 - 1.0)
                up_flags.append(1.0 if c_now > c_1 else 0.0)
    else:
        for bars in bars_by_symbol.values():
            idx_d: int | None = None
            for idx, b in enumerate(bars):
                if b.date == d:
                    idx_d = idx
                    break
                if b.date > d:
                    break
            if idx_d is None or idx_d < 20:
                continue
            gt20 = sum(b.close * b.volume for b in bars[idx_d - 20 : idx_d]) / 20.0
            if gt20 < min_turnover:
                continue
            c_now = bars[idx_d].close
            c_20 = bars[idx_d - 20].close
            c_1 = bars[idx_d - 1].close
            if c_20 > 0 and c_1 > 0:
                rets_20.append(c_now / c_20 - 1.0)
                up_flags.append(1.0 if c_now > c_1 else 0.0)

    if not rets_20:
        res = (0.0, 0.0)
    else:
        res = (float(np.mean(rets_20)), float(np.mean(up_flags)))

    if ctx is not None:
        ctx.mkt_features_by_date[d] = res
    return res


def compute_event_features(
    bars: list[StockDailyBar],
    t: int,
    bars_by_symbol: dict[str, list[StockDailyBar]] | None = None,
    min_turnover: float = MIN_TURNOVER_227,
    vol_mult: float = VOL_MULT,
    ctx: MarketContext | None = None,
) -> dict[str, float]:
    """Compute the event feature vector at bar close `t` (§3.3).

    Strictly uses only data with date <= bars[t].date.
    """
    if t < 120:
        raise ValueError(f"Feature calculation requires t >= 120, got {t}")

    universe = _normalize_bars_input(bars_by_symbol if bars_by_symbol is not None else bars)
    b_t = bars[t]
    d_t = b_t.date
    c_t = b_t.close

    gt20 = sum(b.close * b.volume for b in bars[t - 20 : t]) / 20.0
    v20 = sum(b.volume for b in bars[t - 20 : t]) / 20.0
    vol_ratio = (b_t.volume / v20) if v20 > 0 else 0.0
    log_gt20 = math.log(gt20) if gt20 > 0 else 0.0

    ret_1 = c_t / bars[t - 1].close - 1.0
    ret_5 = c_t / bars[t - 5].close - 1.0
    ret_20 = c_t / bars[t - 20].close - 1.0
    ret_60 = c_t / bars[t - 60].close - 1.0

    ma20 = sum(b.close for b in bars[t - 19 : t + 1]) / 20.0
    ma50 = sum(b.close for b in bars[t - 49 : t + 1]) / 50.0
    high_60 = max(b.close for b in bars[t - 59 : t + 1])

    dist_ma20 = c_t / ma20 - 1.0
    dist_ma50 = c_t / ma50 - 1.0
    dist_high_60 = c_t / high_60 - 1.0

    log_rets = [math.log(bars[k].close / bars[k - 1].close) for k in range(t - 19, t + 1)]
    vol_20 = float(np.std(log_rets, ddof=1))

    range_t = (b_t.high - b_t.low) / c_t
    if b_t.high == b_t.low:
        close_pos = 0.5
    else:
        close_pos = (c_t - b_t.low) / (b_t.high - b_t.low)

    gap_open = b_t.open / bars[t - 1].close - 1.0

    events_20 = 0
    for j in range(t - 20, t):
        ok, _, _ = _passes_cond_234(bars, j, min_turnover=min_turnover, vol_mult=vol_mult)
        if ok:
            events_20 += 1

    mkt_ret_20, mkt_breadth = _compute_mkt_features_on_date(
        d=d_t,
        bars_by_symbol=universe,
        min_turnover=min_turnover,
        ctx=ctx,
    )

    return {
        "vol_ratio": float(vol_ratio),
        "log_gt20": float(log_gt20),
        "ret_1": float(ret_1),
        "ret_5": float(ret_5),
        "ret_20": float(ret_20),
        "ret_60": float(ret_60),
        "dist_ma20": float(dist_ma20),
        "dist_ma50": float(dist_ma50),
        "dist_high_60": float(dist_high_60),
        "vol_20": float(vol_20),
        "range_t": float(range_t),
        "close_pos": float(close_pos),
        "gap_open": float(gap_open),
        "events_20": float(events_20),
        "mkt_ret_20": float(mkt_ret_20),
        "mkt_breadth": float(mkt_breadth),
    }


def compute_open_mkt_return(
    buy_date: date,
    sell_date: date,
    bars_by_symbol: dict[str, list[StockDailyBar]],
    sessions: list[date],
    min_turnover: float = MIN_TURNOVER_227,
    sess_idx_map: dict[date, int] | None = None,
    ctx: MarketContext | None = None,
    mkt_cache: dict[tuple[date, date], float | None] | None = None,
) -> float | None:
    """Compute equal-weighted open[sell_date]/open[buy_date] - 1 across liquid symbols (§3.4)."""
    if mkt_cache is not None and (buy_date, sell_date) in mkt_cache:
        return mkt_cache[(buy_date, sell_date)]

    if sess_idx_map is None:
        sess_idx_map = {d: i for i, d in enumerate(sessions)}

    i_buy = sess_idx_map.get(buy_date)
    if i_buy is None or i_buy < 1:
        if mkt_cache is not None:
            mkt_cache[(buy_date, sell_date)] = None
        return None

    prev_sess = sessions[i_buy - 1]
    rets: list[float] = []

    if ctx is not None:
        for sym, _ in ctx.liquid_syms_prev20.get(prev_sess, ()):
            d_bar = ctx.sym_date_bar[sym]
            b_buy = d_bar.get(buy_date)
            b_sell = d_bar.get(sell_date)
            if b_buy is not None and b_sell is not None and b_buy.open > 0:
                rets.append(b_sell.open / b_buy.open - 1.0)
    else:
        for bars in bars_by_symbol.values():
            idx_prev: int | None = None
            b_buy: StockDailyBar | None = None
            b_sell: StockDailyBar | None = None
            for idx, b in enumerate(bars):
                if b.date == prev_sess:
                    idx_prev = idx
                elif b.date == buy_date:
                    b_buy = b
                elif b.date == sell_date:
                    b_sell = b
                    break
                elif b.date > sell_date:
                    break
            if idx_prev is None or idx_prev < 20 or b_buy is None or b_sell is None:
                continue
            gt20 = sum(b.close * b.volume for b in bars[idx_prev - 20 : idx_prev]) / 20.0
            if gt20 < min_turnover or b_buy.open <= 0:
                continue
            rets.append(b_sell.open / b_buy.open - 1.0)

    mkt = float(np.mean(rets)) if rets else None
    if mkt_cache is not None:
        mkt_cache[(buy_date, sell_date)] = mkt
    return mkt


def compute_event_label(
    trade: TradeOutcome,
    bars_by_symbol: dict[str, list[StockDailyBar]],
    sessions: list[date],
    min_turnover: float = MIN_TURNOVER_227,
    sess_idx_map: dict[date, int] | None = None,
    ctx: MarketContext | None = None,
    mkt_cache: dict[tuple[date, date], float | None] | None = None,
) -> tuple[float | None, float | None]:
    """Compute excess return label y = gross - mkt (§3.4)."""
    if trade.gross is None or trade.sell_date is None:
        return None, None

    mkt = compute_open_mkt_return(
        buy_date=trade.buy_date,
        sell_date=trade.sell_date,
        bars_by_symbol=bars_by_symbol,
        sessions=sessions,
        min_turnover=min_turnover,
        sess_idx_map=sess_idx_map,
        ctx=ctx,
        mkt_cache=mkt_cache,
    )
    if mkt is None:
        return None, None
    return float(trade.gross - mkt), mkt


def prepare_events_with_outcomes(
    events: list[EventRecord],
    bars_by_symbol: dict[str, list[StockDailyBar]],
    sessions: list[date],
    exchanges: Mapping[str, str],
    h: int,
    min_turnover: float = MIN_TURNOVER_227,
    vol_mult: float = VOL_MULT,
    ctx: MarketContext | None = None,
) -> list[EventRecord]:
    """Populate features, trade outcomes, and labels for a list of base events."""
    if ctx is None:
        ctx = precompute_market_context(bars_by_symbol, min_turnover=min_turnover)
    sess_idx_map = {d: i for i, d in enumerate(sessions)}
    mkt_cache: dict[tuple[date, date], float | None] = {}

    prepared: list[EventRecord] = []
    for ev in events:
        bars = bars_by_symbol[ev.symbol]
        exch = exchanges.get(ev.symbol, ev.exchange)
        feats = (
            dict(ev.features)
            if ev.features
            else compute_event_features(
                bars=bars,
                t=ev.bar_idx,
                bars_by_symbol=bars_by_symbol,
                min_turnover=min_turnover,
                vol_mult=vol_mult,
                ctx=ctx,
            )
        )
        outcome = event_trade(
            bars=bars,
            t=ev.bar_idx,
            sessions=sessions,
            h=h,
            exchange=exch,
            sess_idx_map=sess_idx_map,
        )
        y_val, mkt_val = compute_event_label(
            trade=outcome,
            bars_by_symbol=bars_by_symbol,
            sessions=sessions,
            min_turnover=min_turnover,
            sess_idx_map=sess_idx_map,
            ctx=ctx,
            mkt_cache=mkt_cache,
        )
        prepared.append(
            EventRecord(
                symbol=ev.symbol,
                bar_idx=ev.bar_idx,
                signal_date=ev.signal_date,
                buy_date=outcome.buy_date,
                buy_price=outcome.buy_price,
                exchange=exch,
                gt20=ev.gt20,
                vol_ratio=ev.vol_ratio,
                features=feats,
                sell_date=outcome.sell_date,
                sell_price=outcome.sell_price,
                gross=outcome.gross,
                mkt=mkt_val,
                y=y_val,
                exit_reason=outcome.exit_reason,
            )
        )
    return prepared


def _event_feature_matrix(events: Sequence[EventRecord]) -> np.ndarray:
    return np.array(
        [[ev.features[name] for name in FEATURE_NAMES] for ev in events],
        dtype=np.float64,
    )


def _shuffle_labels_by_buy_year(
    train_events: Sequence[EventRecord],
    rng: np.random.Generator,
) -> np.ndarray:
    """Shuffle training labels y strictly within each calendar year of buy_date (§3.7)."""
    y_arr = np.array([float(ev.y) for ev in train_events], dtype=np.float64)
    by_year: dict[int, list[int]] = {}
    for idx, ev in enumerate(train_events):
        by_year.setdefault(ev.buy_date.year, []).append(idx)

    for yr in sorted(by_year.keys()):
        indices = np.array(by_year[yr], dtype=np.int64)
        shuffled_vals = y_arr[indices].copy()
        rng.shuffle(shuffled_vals)
        y_arr[indices] = shuffled_vals
    return y_arr


def train_and_score(
    events: list[EventRecord],
    sessions: list[date],
    test_years: Sequence[int] = (2019, 2020, 2021, 2022),
    shuffle_labels: bool = False,
    shuffle_seed: int = 227,
    lgbm_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Walk-forward LightGBM training with strict purge sell_date < first_session_of_year_Y (§3.5).

    Returns dictionary containing:
    - scores_by_event_key: dict[(symbol, signal_date), float]
    - train_events_by_year: dict[int, list[EventRecord]]
    - models_by_year: dict[int, LGBMRegressor]
    - spearman_by_year: dict[int, float | None]
    """
    params = dict(LGBM_PARAMS)
    if lgbm_overrides:
        params.update(lgbm_overrides)

    first_sess_by_year: dict[int, date] = {}
    for s in sessions:
        yr = s.year
        if yr not in first_sess_by_year or s < first_sess_by_year[yr]:
            first_sess_by_year[yr] = s

    rng = np.random.default_rng(shuffle_seed)
    scores_by_key: dict[tuple[str, date], float] = {}
    train_events_by_year: dict[int, list[EventRecord]] = {}
    models_by_year: dict[int, LGBMRegressor] = {}
    spearman_by_year: dict[int, float | None] = {}

    for yr in test_years:
        first_sess_y = first_sess_by_year.get(yr, date(yr, 1, 1))
        train_events = [
            ev
            for ev in events
            if ev.y is not None and ev.sell_date is not None and ev.sell_date < first_sess_y
        ]
        train_events_by_year[yr] = train_events

        test_events = [ev for ev in events if ev.buy_date.year == yr]

        if len(train_events) < 2:
            for ev in test_events:
                scores_by_key[ev.key] = 0.0
            spearman_by_year[yr] = None
            continue

        x_train = _event_feature_matrix(train_events)
        if shuffle_labels:
            y_train = _shuffle_labels_by_buy_year(train_events, rng)
        else:
            y_train = np.array([float(ev.y) for ev in train_events], dtype=np.float64)

        model = LGBMRegressor(**params)
        model.fit(x_train, y_train)
        models_by_year[yr] = model

        if test_events:
            x_test = _event_feature_matrix(test_events)
            preds = model.predict(x_test)
            labeled_preds: list[float] = []
            labeled_y: list[float] = []
            for ev, pred in zip(test_events, preds):
                p_val = float(pred)
                scores_by_key[ev.key] = p_val
                if ev.y is not None:
                    labeled_preds.append(p_val)
                    labeled_y.append(float(ev.y))

            if len(labeled_preds) >= 2 and float(np.std(labeled_preds)) > 1e-12 and float(np.std(labeled_y)) > 1e-12:
                rho, _ = spearmanr(labeled_preds, labeled_y)
                spearman_by_year[yr] = float(rho) if not math.isnan(float(rho)) else None
            else:
                spearman_by_year[yr] = None
        else:
            spearman_by_year[yr] = None

    return {
        "scores_by_event_key": scores_by_key,
        "train_events_by_year": train_events_by_year,
        "models_by_year": models_by_year,
        "spearman_by_year": spearman_by_year,
    }


def simulate_event_portfolio(
    events: Sequence[EventRecord],
    sessions: list[date],
    bars_by_symbol: dict[str, list[StockDailyBar]],
    exchanges: Mapping[str, str],
    h: int,
    variant: str = "ML",
    scores: Mapping[tuple[str, date], float] | None = None,
    rebalance_dates: list[date] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    initial_capital: float = INITIAL_CAPITAL,
    k_slots: int = K_SLOTS,
    cost_threshold: float = COST_RT,
) -> dict[str, Any]:
    """Simulate 10-slot event portfolio under Brief 227 §3.6.

    - Variant 'ML' (or 'SHUFFLE'): keeps events with score > cost_threshold,
      ordered descending by score (ties symbol A -> Z).
    - Variant 'B0': keeps all events, ordered descending by vol_ratio
      (ties symbol A -> Z).
    - Each session d in [start_date, end_date]:
      1. Open sells: matured positions (curr_s_idx >= entry_s_idx + h) whose bar
         exists and is not floor-locked sell at open[d].
      2. Open buys: events whose signal_date == sessions[curr_s_idx - 1],
         excluding symbols currently held. Alloc = min(prev_close_nav / K, cash / BUY_COST_FACTOR).
      3. Close NAV valuation using close[d] (or last_known_close).
      4. If d == end_date: liquidate all remaining open positions at close (END).
    """
    if variant not in ("ML", "B0", "SHUFFLE"):
        raise ValueError(f"Unsupported variant: {variant}")

    if not sessions:
        raise ValueError("sessions cannot be empty")

    sess_idx_map = {d: i for i, d in enumerate(sessions)}

    if start_date is None:
        s2019 = [s for s in sessions if s.year >= 2019]
        start_date = s2019[0] if s2019 else sessions[0]
    if end_date is None:
        end_date = sessions[-1]

    active_sessions = [s for s in sessions if start_date <= s <= end_date]
    if not active_sessions:
        raise ValueError(f"No sessions in range [{start_date}, {end_date}]")

    if rebalance_dates is None:
        all_rebal = get_rebalance_dates(sessions)
        pre_rebal = [r for r in all_rebal if r < start_date]
        in_rebal = [r for r in all_rebal if start_date <= r <= end_date]
        if pre_rebal:
            rebalance_dates = [pre_rebal[-1], *in_rebal]
        else:
            rebalance_dates = in_rebal if len(in_rebal) >= 2 else [start_date, *in_rebal]

    # Fast bar lookup
    sym_date_bar: dict[str, dict[date, StockDailyBar]] = {}
    sym_date_idx: dict[str, dict[date, int]] = {}
    for sym, b_list in bars_by_symbol.items():
        sym_date_bar[sym] = {b.date: b for b in b_list}
        sym_date_idx[sym] = {b.date: i for i, b in enumerate(b_list)}

    # Group events by buy_date (= next session after signal_date)
    events_by_signal_date: dict[date, list[EventRecord]] = {}
    for ev in events:
        events_by_signal_date.setdefault(ev.signal_date, []).append(ev)

    score_map = scores or {}

    cash = float(initial_capital)
    holdings: dict[str, _ActivePosition] = {}
    last_known_close: dict[str, float] = {}
    closed_trades: list[ClosedEventTrade] = []

    daily_nav: dict[date, float] = {}
    stock_exposure_ratios: list[float] = []
    fees_paid_total = 0.0
    fees_by_year: dict[int, float] = {}
    navs_by_year: dict[int, list[float]] = {}

    # Seed last_known_close from bars prior to start_date so missing-bar valuations work immediately
    for sym, b_list in bars_by_symbol.items():
        for b in b_list:
            if b.date < start_date:
                last_known_close[sym] = b.close
            else:
                break

    prev_close_nav = float(initial_capital)

    for curr_sess in active_sessions:
        for sym, d_map in sym_date_bar.items():
            if curr_sess in d_map:
                last_known_close[sym] = d_map[curr_sess].close

        curr_s_idx = sess_idx_map[curr_sess]

        # ------------------------------------------------------------------
        # 1. OPEN PHASE: Sells first, then Buys
        # ------------------------------------------------------------------
        for sym in list(holdings.keys()):
            pos = holdings[sym]
            if curr_s_idx - pos.entry_s_idx < h:
                continue

            b = sym_date_bar.get(sym, {}).get(curr_sess)
            b_idx = sym_date_idx.get(sym, {}).get(curr_sess)
            if b is None or b_idx is None or b_idx < 1:
                continue

            prev_b = bars_by_symbol[sym][b_idx - 1]
            exch = exchanges.get(sym, "HOSE")
            if is_floor_locked(prev_b.close, b.high, b.low, exch):
                continue

            sell_px = b.open
            gross_val = pos.shares * sell_px
            fee = gross_val * SELL_FEE_RATE
            cash += gross_val * SELL_RETURN_FACTOR
            fees_paid_total += fee
            fees_by_year[curr_sess.year] = fees_by_year.get(curr_sess.year, 0.0) + fee

            net_ret = compute_stock_net_return(pos.entry_price, sell_px)
            closed_trades.append(
                ClosedEventTrade(
                    symbol=sym,
                    signal_date=pos.signal_date,
                    entry_date=pos.entry_date,
                    entry_price=pos.entry_price,
                    exit_date=curr_sess,
                    exit_price=sell_px,
                    exit_reason="TIME",
                    holding_sessions=curr_s_idx - pos.entry_s_idx,
                    net_return=net_ret,
                    score=pos.score,
                )
            )
            del holdings[sym]

        # 2. OPEN BUYS from previous session's signal close
        if curr_s_idx >= 1:
            prev_sess = sessions[curr_s_idx - 1]
            day_events = events_by_signal_date.get(prev_sess, [])
            open_slots = k_slots - len(holdings)

            if open_slots > 0 and day_events:
                eligible: list[tuple[float, str, EventRecord]] = []
                for ev in day_events:
                    if ev.symbol in holdings:
                        continue
                    if variant == "B0":
                        prio = ev.vol_ratio
                        eligible.append((prio, ev.symbol, ev))
                    else:
                        sc = score_map.get(ev.key)
                        if sc is None or sc <= cost_threshold:
                            continue
                        eligible.append((sc, ev.symbol, ev))

                eligible.sort(key=lambda item: (-item[0], item[1]))

                for prio, sym, ev in eligible[:open_slots]:
                    b = sym_date_bar.get(sym, {}).get(curr_sess)
                    if b is None or b.open <= 0:
                        continue

                    target_v = prev_close_nav / k_slots
                    max_v_cash = cash / BUY_COST_FACTOR
                    v = min(target_v, max_v_cash)
                    if v <= 0:
                        continue

                    buy_px = b.open
                    shares = v / buy_px
                    cost = v * BUY_COST_FACTOR
                    fee = v * BUY_FEE_RATE
                    cash -= cost
                    fees_paid_total += fee
                    fees_by_year[curr_sess.year] = (
                        fees_by_year.get(curr_sess.year, 0.0) + fee
                    )

                    holdings[sym] = _ActivePosition(
                        symbol=sym,
                        signal_date=ev.signal_date,
                        entry_date=curr_sess,
                        entry_s_idx=curr_s_idx,
                        entry_price=buy_px,
                        shares=shares,
                        score=prio,
                    )

        # ------------------------------------------------------------------
        # 2. CLOSE PHASE: Valuation
        # ------------------------------------------------------------------
        stock_val = 0.0
        for sym, pos in holdings.items():
            px = last_known_close.get(sym, pos.entry_price)
            stock_val += pos.shares * px

        cur_nav = cash + stock_val
        daily_nav[curr_sess] = cur_nav
        exposure_ratio = (stock_val / cur_nav) if cur_nav > 0 else 0.0
        stock_exposure_ratios.append(exposure_ratio)

        # ------------------------------------------------------------------
        # 3. END OF PERIOD LIQUIDATION
        # ------------------------------------------------------------------
        if curr_sess == end_date and holdings:
            for sym, pos in list(holdings.items()):
                px = last_known_close.get(sym, pos.entry_price)
                gross_val = pos.shares * px
                fee = gross_val * SELL_FEE_RATE
                cash += gross_val * SELL_RETURN_FACTOR
                fees_paid_total += fee
                fees_by_year[curr_sess.year] = (
                    fees_by_year.get(curr_sess.year, 0.0) + fee
                )

                net_ret = compute_stock_net_return(pos.entry_price, px)
                closed_trades.append(
                    ClosedEventTrade(
                        symbol=sym,
                        signal_date=pos.signal_date,
                        entry_date=pos.entry_date,
                        entry_price=pos.entry_price,
                        exit_date=curr_sess,
                        exit_price=px,
                        exit_reason="END",
                        holding_sessions=curr_s_idx - pos.entry_s_idx,
                        net_return=net_ret,
                        score=pos.score,
                    )
                )
            holdings.clear()
            cur_nav = cash
            daily_nav[curr_sess] = cur_nav

        navs_by_year.setdefault(curr_sess.year, []).append(daily_nav[curr_sess])
        prev_close_nav = daily_nav[curr_sess]

    # Monthly returns R_m = NAV(L(m)) / NAV(L(m-1)) - 1
    monthly_nav: dict[date, float] = {}
    for r in rebalance_dates:
        if r in daily_nav:
            monthly_nav[r] = daily_nav[r]
        elif r < start_date:
            monthly_nav[r] = float(initial_capital)
        else:
            # Nearest earlier session NAV if rebalance date wasn't visited
            earlier = [d for d in daily_nav if d <= r]
            monthly_nav[r] = daily_nav[earlier[-1]] if earlier else float(initial_capital)

    monthly_returns: list[float] = []
    for m_idx in range(1, len(rebalance_dates)):
        nav_prev = monthly_nav[rebalance_dates[m_idx - 1]]
        nav_curr = monthly_nav[rebalance_dates[m_idx]]
        r_m = (nav_curr / nav_prev - 1.0) if nav_prev > 0 else 0.0
        monthly_returns.append(r_m)

    # CAGR, MDD, Calmar
    nav_start_date = rebalance_dates[0] if rebalance_dates else start_date
    final_nav = daily_nav[end_date]
    total_days = max(1, (end_date - nav_start_date).days)
    years = total_days / 365.25
    cagr = (
        (final_nav / initial_capital) ** (1.0 / years) - 1.0 if final_nav > 0 else -1.0
    )

    peak = -math.inf
    mdd = 0.0
    for d in active_sessions:
        nav_val = daily_nav[d]
        peak = max(peak, nav_val)
        dd = (peak - nav_val) / peak if peak > 0 else 0.0
        mdd = max(mdd, dd)

    calmar = (cagr / mdd) if mdd > 0 else (cagr if cagr > 0 else 0.0)
    avg_stock_exposure = (
        float(np.mean(stock_exposure_ratios)) if stock_exposure_ratios else 0.0
    )

    mean_daily_nav = float(np.mean(list(daily_nav.values()))) if daily_nav else float(initial_capital)
    annual_fee_pct_avg_nav = (
        (fees_paid_total / years) / mean_daily_nav if years > 0 and mean_daily_nav > 0 else 0.0
    )
    annual_fee_pct_init = (
        (fees_paid_total / years) / initial_capital if years > 0 else 0.0
    )

    fee_pct_by_year: dict[int, float] = {}
    for yr in sorted(navs_by_year.keys()):
        avg_nav_yr = float(np.mean(navs_by_year[yr]))
        fee_yr = fees_by_year.get(yr, 0.0)
        fee_pct_by_year[yr] = (fee_yr / avg_nav_yr) if avg_nav_yr > 0 else 0.0

    return {
        "daily_nav": daily_nav,
        "monthly_nav": monthly_nav,
        "monthly_returns": monthly_returns,
        "rebalance_dates": rebalance_dates,
        "closed_trades": closed_trades,
        "cagr": cagr,
        "mdd": mdd,
        "calmar": calmar,
        "final_nav": final_nav,
        "total_fees": fees_paid_total,
        "annual_fee_pct": annual_fee_pct_avg_nav,
        "annual_fee_pct_init": annual_fee_pct_init,
        "fees_by_year": fees_by_year,
        "fee_pct_by_year": fee_pct_by_year,
        "avg_stock_exposure": avg_stock_exposure,
    }
