"""Core logic for Brief 240 (Short-Term Reversal Monthly Rotation Portfolio).

Reuses fund certificate exclusion and §3.2 universe filtering at r^- from
scripts/research237_core.py, and ranks eligible symbols by lowest S-day
return RET_S = close[t] / close[t - S] - 1 (ties broken A->Z).
"""

from __future__ import annotations

from datetime import date

from scripts.research191_data import StockDailyBar
from scripts.research237_core import (
    LONG_WINDOW,
    MIN_TURNOVER_237,
    _find_bar_index,
    _get_r_minus,
    filter_out_funds,
    get_universe_at_r,
    is_fund_symbol,
)

MIN_TURNOVER_240 = MIN_TURNOVER_237

__all__ = [
    "LONG_WINDOW",
    "MIN_TURNOVER_240",
    "filter_out_funds",
    "get_universe_at_r",
    "is_fund_symbol",
    "select_reversal_symbols",
]


def select_reversal_symbols(
    r: date,
    sessions: list[date],
    bars_by_symbol: dict[str, list[StockDailyBar]],
    s_window: int,
    n_stocks: int,
    min_turnover: float = MIN_TURNOVER_240,
    long_window: int = LONG_WINDOW,
    out_scores: dict[str, float] | None = None,
) -> list[str]:
    """Select top N lowest-RET_S symbols from §3.2 universe evaluated at r^- (§1 Brief 240).

    RET_S = close[t] / close[t - s_window] - 1 where t is the bar index of r^-.
    Symbols with close[t - s_window] <= 0 or insufficient bars are excluded.
    Ties break alphabetically A->Z. Returns fewer than N if universe is smaller.
    """
    r_minus = _get_r_minus(r, sessions)
    if r_minus is None or s_window <= 0 or long_window <= 0:
        return []

    universe = get_universe_at_r(
        r=r,
        sessions=sessions,
        bars_by_symbol=bars_by_symbol,
        min_turnover=min_turnover,
        long_window=long_window,
    )

    eligible: list[tuple[float, str]] = []
    for sym in universe:
        b_list = bars_by_symbol[sym]
        t = _find_bar_index(b_list, r_minus)
        if t is None or t < s_window:
            continue

        base_close = b_list[t - s_window].close
        if base_close <= 0.0:
            continue

        ret_s = float(b_list[t].close / base_close - 1.0)
        if out_scores is not None:
            out_scores[sym] = ret_s
        eligible.append((ret_s, sym))

    eligible.sort(key=lambda item: (item[0], item[1]))
    return [sym for _score, sym in eligible[:n_stocks]]
