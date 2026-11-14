"""Core logic for Brief 237 (Low Attention / Abnormal Turnover Monthly Rotation Portfolio).

Defines:
- LONG_WINDOW = 250
- MIN_TURNOVER_237 = MIN_TURNOVER_193 (1 billion VND)
- is_fund_symbol / filter_out_funds: excludes fund certificates (E1VFVN30, FU*)
- get_universe_at_r: §3.2 universe filter at r^- (>= 250 bars, is_liquid, non-fund)
- select_lowattn_symbols: §3.3 AT_S = mean(v[-S:]) / mean(v[-250:]) ending at r^-
"""

from __future__ import annotations

from bisect import bisect_left
from datetime import date

from scripts.research191_data import StockDailyBar
from scripts.research191_exits import is_liquid
from scripts.research193_core import MIN_TURNOVER_193

LONG_WINDOW = 250
MIN_TURNOVER_237 = MIN_TURNOVER_193


def is_fund_symbol(symbol: str) -> bool:
    """Return True if symbol is a fund certificate excluded by §1 (E1VFVN30 or FU*)."""
    return symbol == "E1VFVN30" or symbol.startswith("FU")


def filter_out_funds(
    bars_by_symbol: dict[str, list[StockDailyBar]],
) -> dict[str, list[StockDailyBar]]:
    """Exclude fund certificates from bars_by_symbol before selection or EW calculation."""
    return {
        sym: b_list
        for sym, b_list in bars_by_symbol.items()
        if not is_fund_symbol(sym)
    }


def _find_bar_index(b_list: list[StockDailyBar], target_date: date) -> int | None:
    """Find index of target_date in date-sorted bar list via binary search."""
    idx = bisect_left(b_list, target_date, key=lambda b: b.date)
    if idx < len(b_list) and b_list[idx].date == target_date:
        return idx
    return None


def _get_r_minus(r: date, sessions: list[date]) -> date | None:
    """Return the trading session immediately before r in S, or None if unavailable."""
    idx = bisect_left(sessions, r)
    if idx >= len(sessions) or sessions[idx] != r:
        # Fallback in case caller passes an unsorted session list in unit tests
        for i, d in enumerate(sessions):
            if d == r:
                return sessions[i - 1] if i >= 1 else None
        return None
    if idx < 1:
        return None
    return sessions[idx - 1]


def get_universe_at_r(
    r: date,
    sessions: list[date],
    bars_by_symbol: dict[str, list[StockDailyBar]],
    min_turnover: float = MIN_TURNOVER_237,
    long_window: int = LONG_WINDOW,
) -> list[str]:
    """Return A->Z sorted symbols in the §3.2 universe evaluated at r^-.

    Eligibility criteria at r^- (session immediately prior to r in S):
    - Not a fund certificate (E1VFVN30 or starting with FU).
    - Has a bar at r^-.
    - Has at least long_window bars (250) up to and including r^- (bar index t >= 249).
    - Passes is_liquid(bars, t, min_turnover=1e9) at r^-.
    """
    r_minus = _get_r_minus(r, sessions)
    if r_minus is None:
        return []

    universe: list[str] = []
    min_last_idx = long_window - 1
    for sym, b_list in bars_by_symbol.items():
        if is_fund_symbol(sym):
            continue
        t = _find_bar_index(b_list, r_minus)
        if t is None or t < min_last_idx:
            continue
        if not is_liquid(b_list, t, min_turnover=min_turnover):
            continue
        universe.append(sym)

    universe.sort()
    return universe


def select_lowattn_symbols(
    r: date,
    sessions: list[date],
    bars_by_symbol: dict[str, list[StockDailyBar]],
    s_window: int,
    n_stocks: int,
    min_turnover: float = MIN_TURNOVER_237,
    long_window: int = LONG_WINDOW,
    out_scores: dict[str, float] | None = None,
) -> list[str]:
    """Select top N lowest-AT_S symbols from §3.2 universe at r^- (§3.3).

    AT_S = mean(v over last s_window bars up to r^-) / mean(v over last 250 bars up to r^-),
    where v_i = close_i * volume_i. Symbols with denominator <= 0 are excluded.
    Ties break A->Z. Returns fewer than N if universe is smaller.
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
        if t is None or t < s_window - 1:
            continue

        short_bars = b_list[t - s_window + 1 : t + 1]
        long_start = max(0, t - long_window + 1)
        long_bars = b_list[long_start : t + 1]

        short_mean = sum(b.close * b.volume for b in short_bars) / s_window
        long_mean = sum(b.close * b.volume for b in long_bars) / len(long_bars)
        if long_mean <= 0.0:
            continue

        at_score = float(short_mean / long_mean)
        if out_scores is not None:
            out_scores[sym] = at_score
        eligible.append((at_score, sym))

    eligible.sort(key=lambda item: (item[0], item[1]))
    return [sym for _score, sym in eligible[:n_stocks]]
