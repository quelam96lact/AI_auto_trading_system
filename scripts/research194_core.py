"""Core logic for Brief 194: Weekly Trend (MA) + Daily Entry (RSI) + ATR Chandelier Stop.

Defines:
- MIN_TURNOVER_194 = 1_000_000_000.0 (1 tỷ VND)
- K_SLOTS = 10
- weekly_trend_series: computes weekly trend series using previous completed ISO weeks
- chandelier_stop: calculates trailing chandelier stop level
- entry_signals: evaluates 6 entry conditions at session t close
- simulate_swing_portfolio: 10-slot swing portfolio simulation tracking daily NAV
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

import numpy as np

from scripts.research188_core import compute_stock_net_return, resample
from scripts.research191_data import StockDailyBar
from scripts.research191_exits import is_floor_locked, is_liquid
from trading.indicators import AtrCalculator
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.stock_study import entry_status
from trading.strategies.momentum_rsi import _RsiState

MIN_TURNOVER_194 = 1_000_000_000.0  # 1 tỷ VND
K_SLOTS = 10  # 10 slots cố định
BUY_FEE_RATE = FEE_RATE + SLIPPAGE_BPS / 10_000.0  # 0.0028 + 0.0005 = 0.0033
SELL_FEE_RATE = (
    FEE_RATE + SELL_TAX_RATE + SLIPPAGE_BPS / 10_000.0
)  # 0.0028 + 0.001 + 0.0005 = 0.0043
BUY_COST_FACTOR = 1.0 + BUY_FEE_RATE  # 1.0033
SELL_RETURN_FACTOR = 1.0 - SELL_FEE_RATE  # 0.9957


def weekly_trend_series(
    bars: list[StockDailyBar],
    sessions: list[date],
    n: int,
) -> dict[date, bool]:
    """Calculate weekly trend for each session in sessions (§3.1).

    - Weekly bars: resample(bars, "W") grouped by ISO week.
    - At session t, visible weeks: only ISO weeks strictly BEFORE the ISO week containing t.
      The currently running week is NOT used.
    - w: last visible week.
    - SMA_n(w): simple moving average of n weekly closes ending at w.
    - TREND(t) is True if: C_week(w) > SMA_n(w) AND SMA_n(w) > SMA_n(w - 1).
    - Requires at least n + 1 visible weeks, otherwise False.
    """
    if len(bars) < 2:
        return {s: False for s in sessions}

    weekly_bars = resample(cast(Any, bars), "W")
    if not weekly_bars:
        return {s: False for s in sessions}

    # Extract (iso_year, iso_week) and close for each weekly bar
    w_info: list[tuple[tuple[int, int], float]] = []
    for wb in weekly_bars:
        iso_y, iso_w, _ = wb.ts.isocalendar()
        w_info.append(((iso_y, iso_w), wb.close))

    # Precalculate trend for each distinct ISO week
    # Map (iso_year, iso_week) -> bool
    week_trend_cache: dict[tuple[int, int], bool] = {}
    closes_list = [c for _, c in w_info]

    # Map each session to its trend status
    trend_by_date: dict[date, bool] = {}
    for s in sessions:
        s_iso = s.isocalendar()[:2]
        if s_iso in week_trend_cache:
            trend_by_date[s] = week_trend_cache[s_iso]
            continue

        # Find count of weekly bars strictly before s_iso
        # Since w_info is chronologically sorted:
        count = 0
        for (w_y, w_w), _ in w_info:
            if (w_y, w_w) < s_iso:
                count += 1
            else:
                break

        if count < n + 1:
            week_trend_cache[s_iso] = False
            trend_by_date[s] = False
            continue

        # w is index count - 1
        last_idx = count - 1
        w_close = closes_list[last_idx]
        sma_w = sum(closes_list[last_idx - n + 1 : last_idx + 1]) / n
        sma_w_prev = sum(closes_list[last_idx - n : last_idx]) / n

        is_trend = bool(w_close > sma_w > sma_w_prev)
        week_trend_cache[s_iso] = is_trend
        trend_by_date[s] = is_trend

    return trend_by_date


def chandelier_stop(
    entry_price: float,
    highest_close: float,
    atr: float,
    k: float,
) -> float:
    """Calculate trailing Chandelier Stop level (§3.3).

    H_t = max(E, max close from entry e to t).
    Stop_t = H_t - k * ATR(t).
    """
    h_t = max(entry_price, highest_close)
    return h_t - k * atr


def entry_signals(
    r: date,
    bars_by_symbol: dict[str, list[StockDailyBar]],
    sessions: list[date],
    exchanges: dict[str, str],
    weekly_trend_by_symbol: dict[str, dict[date, bool]],
    rsi_by_symbol: Mapping[str, Mapping[date, float | None]],
    theta: float,
    min_turnover: float = MIN_TURNOVER_194,
) -> list[dict[str, Any]]:
    """Evaluate buy entry signals at close of session r (§3.2).

    6 conditions for symbol at close r:
    1. TREND(r) is True.
    2. RSI(r-1) < theta and RSI(r) >= theta (crossover).
    3. is_liquid(bars, t_idx, min_turnover).
    4. At least 60 daily bars up to r (t_idx >= 59).
    5. Not currently held (handled in portfolio simulation).
    6. entry_status(bars, t_idx, exchange) == "ok" AND next bar is on next session in S.

    Returns candidate signals with GTGD20 for priority sorting.
    """
    sess_idx_map = {d: i for i, d in enumerate(sessions)}
    r_idx = sess_idx_map.get(r)
    if r_idx is None or r_idx + 1 >= len(sessions):
        return []

    next_session = sessions[r_idx + 1]
    signals: list[dict[str, Any]] = []

    for sym, b_list in bars_by_symbol.items():
        if len(b_list) < 60:
            continue

        # Find bar index for r
        bar_idx = None
        for i, b in enumerate(b_list):
            if b.date == r:
                bar_idx = i
                break
        if bar_idx is None or bar_idx < 59 or bar_idx + 1 >= len(b_list):
            continue

        # Condition 6 part 2: next bar must fall exactly on next_session in S
        next_bar = b_list[bar_idx + 1]
        if next_bar.date != next_session:
            continue

        # Condition 1: TREND(r)
        if not weekly_trend_by_symbol.get(sym, {}).get(r, False):
            continue

        # Condition 2: RSI(r-1) < theta and RSI(r) >= theta
        prev_bar_date = b_list[bar_idx - 1].date
        rsi_prev = rsi_by_symbol.get(sym, {}).get(prev_bar_date)
        rsi_curr = rsi_by_symbol.get(sym, {}).get(r)
        if rsi_prev is None or rsi_curr is None:
            continue
        if not (rsi_prev < theta and rsi_curr >= theta):
            continue

        # Condition 3: is_liquid(bars, bar_idx, min_turnover)
        if not is_liquid(b_list, bar_idx, min_turnover=min_turnover):
            continue

        # Condition 6 part 1: entry_status == "ok"
        exch = exchanges.get(sym, "HOSE")
        if entry_status(cast(Any, b_list), bar_idx, exch) != "ok":
            continue

        # Calculate GTGD20 at r for priority ordering
        window20 = b_list[bar_idx - 19 : bar_idx + 1]
        gtgd20 = sum(b.close * b.volume for b in window20) / 20.0

        signals.append(
            {
                "symbol": sym,
                "signal_date": r,
                "next_session": next_session,
                "gtgd20": gtgd20,
            }
        )

    # Sort priority: gtgd20 descending, ties symbol A->Z
    signals.sort(key=lambda s: (-s["gtgd20"], s["symbol"]))
    return signals


@dataclass
class ActivePosition:
    symbol: str
    entry_date: date
    entry_price: float
    shares: float
    signal_date: date
    highest_close: float
    pending_exit: bool = False
    exit_reason: str = ""
    exit_signal_date: date | None = None


@dataclass
class ClosedTrade:
    symbol: str
    signal_date: date
    entry_date: date
    entry_price: float
    exit_date: date
    exit_price: float
    exit_reason: str  # "STOP" | "TREND" | "END"
    holding_sessions: int
    net_return: float


def simulate_swing_portfolio(
    sessions: list[date],
    bars_by_symbol: dict[str, list[StockDailyBar]],
    exchanges: dict[str, str],
    rebalance_dates: list[date],
    n: int,
    theta: float,
    k: float,
    initial_capital: float = 100_000_000.0,
    k_slots: int = K_SLOTS,
    min_turnover: float = MIN_TURNOVER_194,
) -> dict[str, Any]:
    """Simulate swing portfolio with K slots, daily NAV tracking, and chandelier stops (§3.4).

    Start session is rebalance_dates[0] = L(M_0).
    End session is rebalance_dates[-1] = L(M_1).
    """
    if len(rebalance_dates) < 2:
        raise ValueError("At least 2 rebalance dates required (start and end)")

    start_date = rebalance_dates[0]
    end_date = rebalance_dates[-1]

    sess_idx_map = {d: i for i, d in enumerate(sessions)}
    active_sessions = [s for s in sessions if start_date <= s <= end_date]
    if len(active_sessions) < 2:
        raise ValueError("Not enough sessions in range")

    # Fast index lookup: symbol -> date -> bar
    sym_date_bar: dict[str, dict[date, StockDailyBar]] = {}
    sym_date_idx: dict[str, dict[date, int]] = {}
    for sym, b_list in bars_by_symbol.items():
        sym_date_bar[sym] = {b.date: b for b in b_list}
        sym_date_idx[sym] = {b.date: i for i, b in enumerate(b_list)}

    # 1. Precalculate Weekly Trend, RSI(14), and ATR(14) for all symbols
    weekly_trend_by_sym: dict[str, dict[date, bool]] = {}
    rsi_by_sym: dict[str, dict[date, float | None]] = {}
    atr_by_sym: dict[str, dict[date, float | None]] = {}

    for sym, b_list in bars_by_symbol.items():
        weekly_trend_by_sym[sym] = weekly_trend_series(b_list, sessions, n=n)

        # RSI(14)
        rsi_state = _RsiState(14)
        sym_rsi: dict[date, float | None] = {}
        for b in b_list:
            sym_rsi[b.date] = rsi_state.update(b.close)
        rsi_by_sym[sym] = sym_rsi

        # ATR(14)
        atr_calc = AtrCalculator(14)
        sym_atr: dict[date, float | None] = {}
        for b in b_list:
            sym_atr[b.date] = atr_calc.update(cast(Any, b))
        atr_by_sym[sym] = sym_atr

    cash = float(initial_capital)
    holdings: dict[str, ActivePosition] = {}
    last_known_close: dict[str, float] = {}
    closed_trades: list[ClosedTrade] = []

    daily_nav: dict[date, float] = {}
    stock_exposure_ratios: list[float] = []
    fees_paid_total = 0.0

    # Signals generated at close of previous session, to execute at open of today
    pending_buy_signals: list[dict[str, Any]] = []

    # Penultimate session index
    penultimate_sess = active_sessions[-2]

    for curr_sess in active_sessions:
        # Update last known close
        for sym, d_map in sym_date_bar.items():
            if curr_sess in d_map:
                last_known_close[sym] = d_map[curr_sess].close

        curr_s_idx = sess_idx_map[curr_sess]

        if curr_sess == start_date:
            # Start date: valuation at close is exactly 100M
            daily_nav[curr_sess] = cash
            stock_exposure_ratios.append(0.0)

            # Generate buy signals at close of start_date
            pending_buy_signals = entry_signals(
                r=curr_sess,
                bars_by_symbol=bars_by_symbol,
                sessions=sessions,
                exchanges=exchanges,
                weekly_trend_by_symbol=weekly_trend_by_sym,
                rsi_by_symbol=rsi_by_sym,
                theta=theta,
                min_turnover=min_turnover,
            )
            continue

        prev_sess = sessions[curr_s_idx - 1]
        prev_close_nav = daily_nav[prev_sess]

        # -------------------------------------------------------------
        # 1. OPEN PHASE: Execute Sells first, then Buys
        # -------------------------------------------------------------
        # A. Sells
        for sym in list(holdings.keys()):
            pos = holdings[sym]
            if not pos.pending_exit:
                continue

            entry_s_idx = sess_idx_map.get(pos.entry_date, 0)
            # T+2 constraint: must be at least 2 sessions after entry session in S
            if curr_s_idx - entry_s_idx < 2:
                # Still locked by T+2, keep pending
                continue

            # Check bar on curr_sess
            b = sym_date_bar.get(sym, {}).get(curr_sess)
            b_idx = sym_date_idx.get(sym, {}).get(curr_sess)
            if b is None or b_idx is None or b_idx < 1:
                # No bar, defer to next session
                continue

            # Check floor lock
            prev_b = bars_by_symbol[sym][b_idx - 1]
            exch = exchanges.get(sym, "HOSE")
            if is_floor_locked(prev_b.close, b.high, b.low, exch):
                # Floor locked, defer to next session
                continue

            # Execute sell at open
            sell_px = b.open
            gross_val = pos.shares * sell_px
            fee = gross_val * SELL_FEE_RATE
            cash += gross_val * SELL_RETURN_FACTOR
            fees_paid_total += fee

            net_ret = compute_stock_net_return(pos.entry_price, sell_px)
            closed_trades.append(
                ClosedTrade(
                    symbol=sym,
                    signal_date=pos.signal_date,
                    entry_date=pos.entry_date,
                    entry_price=pos.entry_price,
                    exit_date=curr_sess,
                    exit_price=sell_px,
                    exit_reason=pos.exit_reason,
                    holding_sessions=curr_s_idx - entry_s_idx,
                    net_return=net_ret,
                )
            )
            del holdings[sym]

        # B. Buys from pending buy signals
        open_slots = k_slots - len(holdings)
        if open_slots > 0 and pending_buy_signals:
            # Filter out symbols currently held
            eligible_buys = [
                s for s in pending_buy_signals if s["symbol"] not in holdings
            ]
            for sig in eligible_buys[:open_slots]:
                sym = sig["symbol"]
                b = sym_date_bar.get(sym, {}).get(curr_sess)
                if b is None:
                    continue

                target_v = prev_close_nav / K_SLOTS
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

                holdings[sym] = ActivePosition(
                    symbol=sym,
                    entry_date=curr_sess,
                    entry_price=buy_px,
                    shares=shares,
                    signal_date=sig["signal_date"],
                    highest_close=max(buy_px, b.close),
                )

        # Discard untraded signals
        pending_buy_signals = []

        # -------------------------------------------------------------
        # 2. CLOSE PHASE: Daily NAV Valuation
        # -------------------------------------------------------------
        stock_val = 0.0
        for sym, pos in holdings.items():
            px = last_known_close.get(sym, pos.entry_price)
            stock_val += pos.shares * px
            # Update highest close
            b = sym_date_bar.get(sym, {}).get(curr_sess)
            if b is not None:
                pos.highest_close = max(pos.highest_close, b.close)

        cur_nav = cash + stock_val
        daily_nav[curr_sess] = cur_nav
        exposure_ratio = (stock_val / cur_nav) if cur_nav > 0 else 0.0
        stock_exposure_ratios.append(exposure_ratio)

        # -------------------------------------------------------------
        # 3. AFTER CLOSE: Exits and Entry Signals
        # -------------------------------------------------------------
        if curr_sess == end_date:
            # Final rebalance: close-out liquidation of all remaining positions
            for sym, pos in list(holdings.items()):
                px = last_known_close.get(sym, pos.entry_price)
                gross_val = pos.shares * px
                fee = gross_val * SELL_FEE_RATE
                cash += gross_val * SELL_RETURN_FACTOR
                fees_paid_total += fee

                entry_s_idx = sess_idx_map.get(pos.entry_date, 0)
                net_ret = compute_stock_net_return(pos.entry_price, px)
                closed_trades.append(
                    ClosedTrade(
                        symbol=sym,
                        signal_date=pos.signal_date,
                        entry_date=pos.entry_date,
                        entry_price=pos.entry_price,
                        exit_date=curr_sess,
                        exit_price=px,
                        exit_reason="END",
                        holding_sessions=curr_s_idx - entry_s_idx,
                        net_return=net_ret,
                    )
                )
            holdings.clear()
            daily_nav[curr_sess] = cash
        else:
            # Check exit conditions for active positions
            for sym, pos in holdings.items():
                if pos.pending_exit:
                    continue

                b = sym_date_bar.get(sym, {}).get(curr_sess)
                if b is None:
                    continue

                atr_val = atr_by_sym.get(sym, {}).get(curr_sess)
                stop_lvl = (
                    chandelier_stop(pos.entry_price, pos.highest_close, atr_val, k)
                    if atr_val is not None
                    else -math.inf
                )

                stop_triggered = b.close < stop_lvl
                trend_ok = weekly_trend_by_sym.get(sym, {}).get(curr_sess, False)

                if stop_triggered:
                    pos.pending_exit = True
                    pos.exit_reason = "STOP"
                    pos.exit_signal_date = curr_sess
                elif not trend_ok:
                    pos.pending_exit = True
                    pos.exit_reason = "TREND"
                    pos.exit_signal_date = curr_sess

            # Generate entry signals if before penultimate session
            if curr_sess < penultimate_sess:
                all_signals = entry_signals(
                    r=curr_sess,
                    bars_by_symbol=bars_by_symbol,
                    sessions=sessions,
                    exchanges=exchanges,
                    weekly_trend_by_symbol=weekly_trend_by_sym,
                    rsi_by_symbol=rsi_by_sym,
                    theta=theta,
                    min_turnover=min_turnover,
                )
                # Filter out symbols currently held
                pending_buy_signals = [
                    s for s in all_signals if s["symbol"] not in holdings
                ]

    # Calculate monthly returns R_m = NAV(L(m)) / NAV(L(m-1)) - 1
    monthly_nav: dict[date, float] = {r: daily_nav[r] for r in rebalance_dates}
    monthly_returns: list[float] = []
    for m_idx in range(1, len(rebalance_dates)):
        prev_r = rebalance_dates[m_idx - 1]
        curr_r = rebalance_dates[m_idx]
        nav_prev = monthly_nav[prev_r]
        nav_curr = monthly_nav[curr_r]
        r_m = (nav_curr / nav_prev - 1.0) if nav_prev > 0 else 0.0
        monthly_returns.append(r_m)

    # Performance metrics
    final_nav = daily_nav[end_date]
    total_days = max(1, (end_date - start_date).days)
    years = total_days / 365.25
    cagr = (
        (final_nav / initial_capital) ** (1.0 / years) - 1.0 if final_nav > 0 else -1.0
    )

    peak = -math.inf
    mdd = 0.0
    for nav_val in daily_nav.values():
        peak = max(peak, nav_val)
        dd = (peak - nav_val) / peak if peak > 0 else 0.0
        mdd = max(mdd, dd)

    calmar = (cagr / mdd) if mdd > 0 else (cagr if cagr > 0 else 0.0)
    avg_stock_exposure = (
        float(np.mean(stock_exposure_ratios)) if stock_exposure_ratios else 0.0
    )
    annual_fee_pct = (fees_paid_total / years) / initial_capital if years > 0 else 0.0

    return {
        "daily_nav": daily_nav,
        "monthly_nav": monthly_nav,
        "monthly_returns": monthly_returns,
        "closed_trades": closed_trades,
        "cagr": cagr,
        "mdd": mdd,
        "calmar": calmar,
        "final_nav": final_nav,
        "total_fees": fees_paid_total,
        "annual_fee_pct": annual_fee_pct,
        "avg_stock_exposure": avg_stock_exposure,
    }
