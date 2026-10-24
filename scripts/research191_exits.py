"""Exit rules, liquidity filter, and baseline excess calculation for Brief 191.

Exit rules (§3.2):
- Entry: signal at close t, matched at open t+1. Discarded if entry_status != "ok".
- Liquidity filter (§3.3): 20-session average GTGD >= 10 tỷ VND at signal date t.
- Exit levels:
  - TP = E * (1 + tp), where tp in {0.10, 0.15, 0.20}
  - SL = E * (1 - 0.07) fixed
  - Max holding: 60 sessions. Expiry exits at open of session 61.
- T+2 holding: cannot sell before session 3 from match session (sessions 1 and 2 ignored).
- From session 3, evaluation order per session:
  1. Open <= SL: exit at open, reason "SL". Open >= TP: exit at open, reason "TP".
  2. Low <= SL and high >= TP: SL first (conservative), exit at SL, reason "SL".
  3. Low <= SL: exit at SL, reason "SL". High >= TP: exit at TP, reason "TP".
- Floor lock: (high == low == floor price). Cannot sell on floor-locked sessions;
  rolls to open of next session.
- End of data: position closes at last bar close with reason "END".
- Net return computed using compute_stock_net_return.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from scripts.research188_core import Trade, compute_stock_net_return
from trading.stock_study import entry_status, limit_rate

DEFAULT_MIN_TURNOVER = 10_000_000_000.0  # 10 tỷ VND
FLOOR_EPS = 0.001


@dataclass(slots=True)
class Trade191(Trade):
    exit_reason: str = "END"  # "TP" | "SL" | "TIME" | "END"
    signal_date: date | None = None
    exited_at_open: bool = False


def is_liquid(
    bars: list[Any],
    t: int,
    min_turnover: float = DEFAULT_MIN_TURNOVER,
) -> bool:
    """Check if 20-session average turnover (close * volume) up to and including t >= min_turnover."""
    if t < 19 or t >= len(bars):
        return False
    window = bars[t - 19 : t + 1]
    tot = sum(b.close * b.volume for b in window)
    return (tot / 20.0) >= min_turnover


def is_floor_locked(
    prev_close: float,
    high: float,
    low: float,
    exchange: str | None,
) -> bool:
    """Determine if a session is floor-locked (high == low == floor price)."""
    if high != low:
        return False
    rate = limit_rate(exchange)
    floor_threshold = prev_close * (1.0 - rate + FLOOR_EPS)
    return low <= floor_threshold


def simulate_trade_exits(
    bars: list[Any],
    signal_idx: int,
    exchange: str | None,
    tp: float = 0.10,
    score: float = 0.0,
    enforce_liquidity: bool = True,
) -> Trade191 | None:
    """Simulate trade execution and exit according to Brief 191 rules.

    - Signal at close t (signal_idx).
    - Entry at open t+1.
    - If entry_status != "ok", returns None.
    - If enforce_liquidity and not is_liquid(bars, signal_idx), returns None.
    - TP = E * (1 + tp), SL = E * (1 - 0.07).
    - T+2: first sellable session is session 3 (signal_idx + 3).
    - Floor locked session cannot sell; rolls to next session.
    - Max holding 60 sessions: exits at session 61 open with reason "TIME" (unless floor locked).
    - End of data: exits at last close with reason "END".
    """
    if signal_idx < 0 or signal_idx + 1 >= len(bars):
        return None

    if enforce_liquidity and not is_liquid(bars, signal_idx):
        return None

    status = entry_status(bars, signal_idx, exchange)
    if status != "ok":
        return None

    entry_idx = signal_idx + 1
    entry_bar = bars[entry_idx]
    entry_p = float(entry_bar.open)
    if entry_p <= 0:
        return None

    tp_price = round(entry_p * (1.0 + tp), 4)
    sl_price = round(entry_p * (1.0 - 0.07), 4)
    signal_d = bars[signal_idx].date

    # T+2: Session 1 is entry_idx, Session 2 is entry_idx + 1, Session 3 is entry_idx + 2
    first_sell_idx = entry_idx + 2
    expiry_idx = entry_idx + 60  # Session 61

    i = first_sell_idx
    n_bars = len(bars)

    while i < n_bars:
        curr_bar = bars[i]
        prev_close = bars[i - 1].close

        # Check floor lock
        floor_locked = is_floor_locked(prev_close, curr_bar.high, curr_bar.low, exchange)

        if i < expiry_idx:
            # Active holding sessions 3 through 60
            if floor_locked:
                # Cannot sell on floor-locked session; roll to next session
                i += 1
                continue

            # Not floor locked: evaluate intraday check order
            # 1. Open gap
            if curr_bar.open <= sl_price:
                exit_p = float(curr_bar.open)
                return Trade191(
                    symbol=entry_bar.symbol,
                    entry_ts=entry_bar.ts,
                    exit_ts=curr_bar.ts,
                    entry_price=entry_p,
                    exit_price=exit_p,
                    net_return=compute_stock_net_return(entry_p, exit_p),
                    gross_return=(exit_p / entry_p) - 1.0,
                    market="stock",
                    side="long",
                    score=score,
                    holding_sessions=i - entry_idx,
                    exit_reason="SL",
                    signal_date=signal_d,
                    exited_at_open=True,
                )
            if curr_bar.open >= tp_price:
                exit_p = float(curr_bar.open)
                return Trade191(
                    symbol=entry_bar.symbol,
                    entry_ts=entry_bar.ts,
                    exit_ts=curr_bar.ts,
                    entry_price=entry_p,
                    exit_price=exit_p,
                    net_return=compute_stock_net_return(entry_p, exit_p),
                    gross_return=(exit_p / entry_p) - 1.0,
                    market="stock",
                    side="long",
                    score=score,
                    holding_sessions=i - entry_idx,
                    exit_reason="TP",
                    signal_date=signal_d,
                    exited_at_open=True,
                )

            # 2. Both touched in same session -> SL first (conservative)
            if curr_bar.low <= sl_price and curr_bar.high >= tp_price:
                exit_p = sl_price
                return Trade191(
                    symbol=entry_bar.symbol,
                    entry_ts=entry_bar.ts,
                    exit_ts=curr_bar.ts,
                    entry_price=entry_p,
                    exit_price=exit_p,
                    net_return=compute_stock_net_return(entry_p, exit_p),
                    gross_return=(exit_p / entry_p) - 1.0,
                    market="stock",
                    side="long",
                    score=score,
                    holding_sessions=i - entry_idx + 1,
                    exit_reason="SL",
                    signal_date=signal_d,
                    exited_at_open=False,
                )

            # 3. Single touched
            if curr_bar.low <= sl_price:
                exit_p = sl_price
                return Trade191(
                    symbol=entry_bar.symbol,
                    entry_ts=entry_bar.ts,
                    exit_ts=curr_bar.ts,
                    entry_price=entry_p,
                    exit_price=exit_p,
                    net_return=compute_stock_net_return(entry_p, exit_p),
                    gross_return=(exit_p / entry_p) - 1.0,
                    market="stock",
                    side="long",
                    score=score,
                    holding_sessions=i - entry_idx + 1,
                    exit_reason="SL",
                    signal_date=signal_d,
                    exited_at_open=False,
                )
            if curr_bar.high >= tp_price:
                exit_p = tp_price
                return Trade191(
                    symbol=entry_bar.symbol,
                    entry_ts=entry_bar.ts,
                    exit_ts=curr_bar.ts,
                    entry_price=entry_p,
                    exit_price=exit_p,
                    net_return=compute_stock_net_return(entry_p, exit_p),
                    gross_return=(exit_p / entry_p) - 1.0,
                    market="stock",
                    side="long",
                    score=score,
                    holding_sessions=i - entry_idx + 1,
                    exit_reason="TP",
                    signal_date=signal_d,
                    exited_at_open=False,
                )

            i += 1
        else:
            # Expiry reached (session 61 or later)
            if floor_locked:
                # Cannot sell at open if session is floor-locked, roll to next session
                i += 1
                continue

            # Not floor-locked: exit at open with reason "TIME"
            exit_p = float(curr_bar.open)
            return Trade191(
                symbol=entry_bar.symbol,
                entry_ts=entry_bar.ts,
                exit_ts=curr_bar.ts,
                entry_price=entry_p,
                exit_price=exit_p,
                net_return=compute_stock_net_return(entry_p, exit_p),
                gross_return=(exit_p / entry_p) - 1.0,
                market="stock",
                side="long",
                score=score,
                holding_sessions=i - entry_idx,
                exit_reason="TIME",
                signal_date=signal_d,
                exited_at_open=True,
            )

    # End of data reached without exit
    last_bar = bars[-1]
    exit_p = float(last_bar.close)
    return Trade191(
        symbol=entry_bar.symbol,
        entry_ts=entry_bar.ts,
        exit_ts=last_bar.ts,
        entry_price=entry_p,
        exit_price=exit_p,
        net_return=compute_stock_net_return(entry_p, exit_p),
        gross_return=(exit_p / entry_p) - 1.0,
        market="stock",
        side="long",
        score=score,
        holding_sessions=len(bars) - entry_idx,
        exit_reason="END",
        signal_date=signal_d,
        exited_at_open=False,
    )


def liquid_baseline_excess(
    trades: list[Trade191],
    bars_by_symbol: dict[str, list[Any]],
    min_turnover: float = DEFAULT_MIN_TURNOVER,
) -> dict[str, float]:
    """Calculate excess return of stock trades vs equal-weighted liquid explore universe.

    For each trade:
    - Baseline stocks = all explore stocks that meet 20-session GTGD >= 10 tỷ
      at the trade's signal date AND have bars on both entry date and exit date.
    - Each baseline stock's return:
      - (exit_bar.open / entry_bar.open - 1.0) if trade exited at open (TIME or open gap)
      - (exit_bar.close / entry_bar.open - 1.0) otherwise
    - Returns mean_excess and mean_excess_trim1pct.
    """
    if not trades:
        return {"mean_excess": 0.0, "mean_excess_trim1pct": 0.0}

    # Pre-index bars by symbol and date
    date_bars: dict[date, dict[str, Any]] = {}
    sym_date_idx: dict[str, dict[date, int]] = {}

    for sym, b_list in bars_by_symbol.items():
        sym_date_idx[sym] = {}
        for idx, b in enumerate(b_list):
            d = b.date
            if d not in date_bars:
                date_bars[d] = {}
            date_bars[d][sym] = b
            sym_date_idx[sym][d] = idx

    excess_returns: list[float] = []

    for t in trades:
        entry_d = t.entry_ts.date()
        exit_d = t.exit_ts.date()

        # Determine signal date
        signal_d = t.signal_date
        if signal_d is None and t.symbol in sym_date_idx and entry_d in sym_date_idx[t.symbol]:
            entry_idx = sym_date_idx[t.symbol][entry_d]
            if entry_idx > 0:
                signal_d = bars_by_symbol[t.symbol][entry_idx - 1].date

        baseline_returns: list[float] = []

        if signal_d is not None:
            for sym, b_list in bars_by_symbol.items():
                # 1. Must have bar at signal_d and meet liquidity filter at signal_d
                sig_idx = sym_date_idx.get(sym, {}).get(signal_d)
                if sig_idx is None:
                    continue
                if not is_liquid(b_list, sig_idx, min_turnover=min_turnover):
                    continue

                # 2. Must have bar on entry_d and exit_d
                entry_b = date_bars.get(entry_d, {}).get(sym)
                exit_b = date_bars.get(exit_d, {}).get(sym)
                if entry_b is None or exit_b is None:
                    continue
                if entry_b.open <= 0:
                    continue

                # 3. Return from entry open to exit
                if t.exited_at_open:
                    stk_ret = (exit_b.open / entry_b.open) - 1.0
                else:
                    stk_ret = (exit_b.close / entry_b.open) - 1.0

                baseline_returns.append(float(stk_ret))

        if baseline_returns:
            baseline_mean = float(np.mean(baseline_returns))
        else:
            baseline_mean = 0.0

        excess_returns.append(t.net_return - baseline_mean)

    mean_excess = float(np.mean(excess_returns))

    if len(excess_returns) >= 10:
        trim_n = max(1, int(len(excess_returns) * 0.01))
        trimmed = sorted(excess_returns)[:-trim_n]
        mean_excess_trim = float(np.mean(trimmed))
    else:
        mean_excess_trim = mean_excess

    return {
        "mean_excess": mean_excess,
        "mean_excess_trim1pct": mean_excess_trim,
    }


def assert_ledger_safety(ledger_path: Path | str) -> None:
    """Enforce rule: never delete or overwrite existing trial ledger (§3.4)."""
    p = Path(ledger_path)
    if p.exists():
        raise SystemExit(f"{ledger_path} đã tồn tại; sổ thử không được xoá để chạy lại")
