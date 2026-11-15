"""Core logic for Brief 238 (High Attention / Abnormal Turnover Monthly Rotation).

Reuses universe filtering, fund exclusion, and AT_S computation from
scripts/research237_core.py, flipping selection order to keep the N highest
AT_S symbols (A->Z tie-break).
"""

from __future__ import annotations

from datetime import date

from scripts.research191_data import StockDailyBar
from scripts.research237_core import (
    LONG_WINDOW,
    MIN_TURNOVER_237,
    filter_out_funds,
    get_universe_at_r,
    is_fund_symbol,
    select_lowattn_symbols,
)

MIN_TURNOVER_238 = MIN_TURNOVER_237

__all__ = [
    "LONG_WINDOW",
    "MIN_TURNOVER_238",
    "filter_out_funds",
    "get_universe_at_r",
    "is_fund_symbol",
    "select_highattn_symbols",
]


def select_highattn_symbols(
    r: date,
    sessions: list[date],
    bars_by_symbol: dict[str, list[StockDailyBar]],
    s_window: int,
    n_stocks: int,
    min_turnover: float = MIN_TURNOVER_238,
    long_window: int = LONG_WINDOW,
    out_scores: dict[str, float] | None = None,
) -> list[str]:
    """Select top N highest-AT_S symbols from §3.2 universe at r^- (§1 Brief 238).

    Ties break A->Z. Returns fewer than N if universe is smaller.
    """
    return select_lowattn_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol=bars_by_symbol,
        s_window=s_window,
        n_stocks=n_stocks,
        min_turnover=min_turnover,
        long_window=long_window,
        out_scores=out_scores,
        descending=True,
    )
