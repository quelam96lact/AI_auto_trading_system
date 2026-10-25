"""Core logic for Brief 193 (Low Volatility Monthly Rotation Portfolio).

Defines:
- MIN_TURNOVER_193 = 1_000_000_000.0 (1 billion VND)
- is_ceiling_locked: helper for ceiling lock check
- get_rebalance_dates: extracts L(M) from sessions list
- score_and_rank_symbols: evaluates §3.2 universe and §3.3 ranking (LOWVOL & LOWMAX)
- simulate_rotation: full monthly rotation portfolio simulation (§3.4)
- ew_benchmark: equal-weighted liquidity benchmark (§3.5)
- calculate_rotation_metrics: computes monthly excess X_m, Sharpe_X, p, CAGR, MDD, Calmar (§3.7)
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import numpy as np

from scripts.research191_data import StockDailyBar
from scripts.research191_exits import is_floor_locked, is_liquid
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.stock_study import bootstrap_by_month, limit_rate

MIN_TURNOVER_193 = 1_000_000_000.0  # 1 tỷ VND
CEILING_EPS = 0.001


def is_ceiling_locked(
    prev_close: float,
    high: float,
    low: float,
    exchange: str | None,
) -> bool:
    """Determine if a session is ceiling-locked (high == low == ceiling price)."""
    if high != low or prev_close <= 0:
        return False
    rate = limit_rate(exchange)
    ceil_threshold = prev_close * (1.0 + rate - CEILING_EPS)
    return high >= ceil_threshold


def get_rebalance_dates(sessions: list[date]) -> list[date]:
    """Extract L(M), the last trading session of each month in S."""
    if not sessions:
        return []
    sessions_by_ym: dict[tuple[int, int], list[date]] = {}
    for s in sessions:
        sessions_by_ym.setdefault((s.year, s.month), []).append(s)
    sorted_ym = sorted(sessions_by_ym.keys())
    return [sessions_by_ym[ym][-1] for ym in sorted_ym]


def score_and_rank_symbols(
    r: date,
    sessions: list[date],
    bars_by_symbol: dict[str, list[StockDailyBar]],
    idea_type: str,
    lookback: int,
    n_stocks: int,
    min_turnover: float = MIN_TURNOVER_193,
) -> list[str]:
    """Score and rank symbols for rebalance date r under §3.2 & §3.3.

    - r_minus: session before r in S.
    - Universe at r_minus: has bar at r_minus, is_liquid(GTGD20 >= min_turnover) at r_minus,
      and has >= lookback + 1 bars up to r_minus.
    - Score:
      - LOWVOL: sample std (ddof=1) of lookback daily returns ending at r_minus.
      - LOWMAX: mean of 3 largest daily returns in lookback window ending at r_minus.
    - Rank: lowest score first. Ties broken by symbol A->Z.
    - Returns top n_stocks symbols.
    """
    sess_idx_map = {d: i for i, d in enumerate(sessions)}
    r_idx = sess_idx_map.get(r)
    if r_idx is None or r_idx < 1:
        return []

    target_sess = sessions[r_idx - 1]

    eligible: list[tuple[float, str]] = []

    for sym, b_list in bars_by_symbol.items():
        # Find index of target_sess in b_list
        bar_idx = None
        for i, b in enumerate(b_list):
            if b.date == target_sess:
                bar_idx = i
                break
        if bar_idx is None:
            continue

        # Liquidity check at target_sess
        if not is_liquid(b_list, bar_idx, min_turnover=min_turnover):
            continue

        # Must have at least lookback + 1 bars up to target_sess
        if bar_idx < lookback:
            continue

        # Daily returns of the last lookback bars ending at bar_idx
        rets = [
            (b_list[i].close / b_list[i - 1].close) - 1.0
            for i in range(bar_idx - lookback + 1, bar_idx + 1)
        ]

        if idea_type == "LOWVOL":
            score = float(np.std(rets, ddof=1))
        elif idea_type == "LOWMAX":
            score = compute_lowmax_score(rets)
        else:
            raise ValueError(f"Unknown idea_type: {idea_type}")

        eligible.append((score, sym))

    # Lowest score first, symbol A->Z on tie
    eligible.sort(key=lambda item: (item[0], item[1]))
    return [sym for _score, sym in eligible[:n_stocks]]


def compute_lowmax_score(rets: list[float]) -> float:
    """Compute LOWMAX score: mean of 3 largest daily returns in window (§3.3)."""
    if len(rets) < 3:
        return float(np.mean(rets)) if rets else 0.0
    sorted_top = sorted(rets, reverse=True)[:3]
    return float(np.mean(sorted_top))


def simulate_rotation(
    rebalance_dates: list[date],
    bars_by_symbol: dict[str, list[StockDailyBar]],
    sessions: list[date],
    exchanges: dict[str, str],
    idea_type: str,
    lookback: int,
    n_stocks: int,
    initial_capital: float = 100_000_000.0,
    min_turnover: float = MIN_TURNOVER_193,
) -> dict[str, Any]:
    """Simulate monthly rotation portfolio (§3.4).

    - At each r in rebalance_dates:
      1. Pre-trading NAV valuation at r close.
      2. SELL first: sell dropped symbols and trim overweighted symbols.
      3. BUY second: buy new symbols and top-up underweighted symbols.
      4. Handle ceiling lock on buy and floor lock on sell.
      5. Final rebalance date: liquidate all positions.
    - Daily NAV tracking for every session in S.
    """
    if len(rebalance_dates) < 2:
        raise ValueError("At least 2 rebalance dates required (start and end)")

    sym_date_bar: dict[str, dict[date, StockDailyBar]] = {}
    sym_date_idx: dict[str, dict[date, int]] = {}
    for sym, b_list in bars_by_symbol.items():
        sym_date_bar[sym] = {b.date: b for b in b_list}
        sym_date_idx[sym] = {b.date: i for i, b in enumerate(b_list)}

    # Cost factors
    s_bps = SLIPPAGE_BPS / 10_000.0
    buy_fee_rate = FEE_RATE + s_bps
    buy_cost_factor = 1.0 + buy_fee_rate
    sell_fee_rate = FEE_RATE + SELL_TAX_RATE + s_bps
    sell_return_factor = 1.0 - sell_fee_rate

    cash = float(initial_capital)
    holdings: dict[str, float] = {}  # symbol -> shares
    last_known_close: dict[str, float] = {}

    start_date = rebalance_dates[0]
    end_date = rebalance_dates[-1]

    # Filter sessions in [start_date, end_date]
    active_sessions = [s for s in sessions if start_date <= s <= end_date]

    daily_nav: dict[date, float] = {}
    monthly_nav_pre: dict[date, float] = {}
    monthly_nav_post: dict[date, float] = {}
    turnovers: list[float] = []
    fees_paid_total = 0.0
    symbols_held_counts: list[int] = []

    # Map rebalance dates to loop
    rebal_set = set(rebalance_dates)

    for current_sess in active_sessions:
        # Update last known close for bars on this session
        for sym, date_bars in sym_date_bar.items():
            if current_sess in date_bars:
                last_known_close[sym] = date_bars[current_sess].close

        # Check if today is a rebalance date
        if current_sess in rebal_set:
            is_final_rebalance = (current_sess == end_date)

            # 1. Pre-trading NAV valuation at current_sess close
            nav_pre = cash
            for sym, shares in holdings.items():
                if shares > 0:
                    px = last_known_close.get(sym, 0.0)
                    nav_pre += shares * px

            monthly_nav_pre[current_sess] = nav_pre
            target_val = (nav_pre / n_stocks) if n_stocks > 0 else 0.0

            # Determine selected symbols
            if is_final_rebalance:
                selected_syms: list[str] = []
            else:
                selected_syms = score_and_rank_symbols(
                    r=current_sess,
                    sessions=sessions,
                    bars_by_symbol=bars_by_symbol,
                    idea_type=idea_type,
                    lookback=lookback,
                    n_stocks=n_stocks,
                    min_turnover=min_turnover,
                )

            total_val_traded_at_r = 0.0

            # 2. SELL PHASE: sell dropped symbols and trim overweighted symbols
            for sym in list(holdings.keys()):
                shares = holdings[sym]
                if shares <= 0:
                    continue

                b = sym_date_bar.get(sym, {}).get(current_sess)
                b_idx = sym_date_idx.get(sym, {}).get(current_sess)

                # Check can sell
                can_sell = True
                if b is None or b_idx is None or b_idx < 1:
                    can_sell = False
                else:
                    prev_b = bars_by_symbol[sym][b_idx - 1]
                    exch = exchanges.get(sym, "HOSE")
                    if is_floor_locked(prev_b.close, b.high, b.low, exch):
                        can_sell = False

                if not can_sell or b is None:
                    # Keep position untouched
                    continue

                px = b.close
                cur_val = shares * px
                target_sym_val = target_val if (sym in selected_syms and not is_final_rebalance) else 0.0

                if cur_val > target_sym_val:
                    excess_val = cur_val - target_sym_val
                    shares_to_sell = excess_val / px
                    holdings[sym] -= shares_to_sell
                    if holdings[sym] <= 1e-9:
                        holdings[sym] = 0.0

                    cash += excess_val * sell_return_factor
                    fee = excess_val * sell_fee_rate
                    fees_paid_total += fee
                    total_val_traded_at_r += excess_val

            # 3. BUY PHASE: buy new symbols and top-up underweighted symbols
            if not is_final_rebalance:
                for sym in selected_syms:
                    b = sym_date_bar.get(sym, {}).get(current_sess)
                    b_idx = sym_date_idx.get(sym, {}).get(current_sess)

                    # Check can buy
                    can_buy = True
                    if b is None or b_idx is None or b_idx < 1:
                        can_buy = False
                    else:
                        prev_b = bars_by_symbol[sym][b_idx - 1]
                        exch = exchanges.get(sym, "HOSE")
                        if is_ceiling_locked(prev_b.close, b.high, b.low, exch):
                            can_buy = False

                    if not can_buy or b is None:
                        continue

                    px = b.close
                    cur_shares = holdings.get(sym, 0.0)
                    cur_val = cur_shares * px

                    if cur_val < target_val:
                        needed_val = target_val - cur_val
                        max_val_by_cash = cash / buy_cost_factor
                        actual_val = min(needed_val, max_val_by_cash)
                        if actual_val > 0:
                            shares_to_buy = actual_val / px
                            holdings[sym] = cur_shares + shares_to_buy
                            cash -= actual_val * buy_cost_factor
                            fee = actual_val * buy_fee_rate
                            fees_paid_total += fee
                            total_val_traded_at_r += actual_val

            # 4. Final close-out liquidation rule for unsold assets at end_date
            if is_final_rebalance:
                for sym, shares in list(holdings.items()):
                    if shares > 0:
                        px = last_known_close.get(sym, 0.0)
                        unsold_val = shares * px
                        cash += unsold_val * sell_return_factor
                        fee = unsold_val * sell_fee_rate
                        fees_paid_total += fee
                        total_val_traded_at_r += unsold_val
                        holdings[sym] = 0.0

            # Count held symbols
            held_count = sum(1 for s, sh in holdings.items() if sh > 0)
            if not is_final_rebalance:
                symbols_held_counts.append(held_count)

            # Record turnover
            t_over = (total_val_traded_at_r / nav_pre) if nav_pre > 0 else 0.0
            turnovers.append(t_over)

            # Post-trading NAV
            nav_post = cash
            for sym, shares in holdings.items():
                if shares > 0:
                    px = last_known_close.get(sym, 0.0)
                    nav_post += shares * px
            monthly_nav_post[current_sess] = nav_post

        # Record daily NAV
        cur_day_nav = cash
        for sym, shares in holdings.items():
            if shares > 0:
                px = last_known_close.get(sym, 0.0)
                cur_day_nav += shares * px
        daily_nav[current_sess] = cur_day_nav

    # Calculate monthly returns R_m = NAV(L(m)) / NAV(L(m-1)) - 1
    monthly_returns: list[float] = []
    for m_idx in range(1, len(rebalance_dates)):
        prev_r = rebalance_dates[m_idx - 1]
        curr_r = rebalance_dates[m_idx]
        prev_nav = monthly_nav_post[prev_r]
        curr_nav = monthly_nav_post[curr_r]
        r_m = (curr_nav / prev_nav) - 1.0 if prev_nav > 0 else 0.0
        monthly_returns.append(r_m)

    # Performance metrics
    final_nav = daily_nav[end_date]
    total_days = max(1, (end_date - start_date).days)
    years = total_days / 365.25
    cagr = (final_nav / initial_capital) ** (1.0 / years) - 1.0 if final_nav > 0 else -1.0

    # Daily MDD
    peak = -math.inf
    mdd = 0.0
    for nav_val in daily_nav.values():
        peak = max(peak, nav_val)
        dd = (peak - nav_val) / peak if peak > 0 else 0.0
        mdd = max(mdd, dd)

    calmar = (cagr / mdd) if mdd > 0 else (cagr if cagr > 0 else 0.0)
    avg_syms_held = float(np.mean(symbols_held_counts)) if symbols_held_counts else 0.0
    mean_turnover = float(np.mean(turnovers)) if turnovers else 0.0
    annual_fee_pct = (fees_paid_total / years) / initial_capital if years > 0 else 0.0

    return {
        "daily_nav": daily_nav,
        "monthly_returns": monthly_returns,
        "cagr": cagr,
        "mdd": mdd,
        "calmar": calmar,
        "final_nav": final_nav,
        "total_fees": fees_paid_total,
        "annual_fee_pct": annual_fee_pct,
        "mean_turnover": mean_turnover,
        "avg_syms_held": avg_syms_held,
        "monthly_nav_post": monthly_nav_post,
    }


def ew_benchmark(
    rebalance_dates: list[date],
    bars_by_symbol: dict[str, list[StockDailyBar]],
    sessions: list[date],
    min_turnover: float = MIN_TURNOVER_193,
) -> list[float]:
    """Calculate equal-weighted liquid benchmark returns for each month (§3.5).

    For each month m between L(m-1) and L(m):
    - Universe at L(m-1): stocks meeting is_liquid at the session before L(m-1) with L=20.
    - EW return = average gross return (close(L(m)) / close(L(m-1)) - 1)
      across all universe stocks having bars on both L(m-1) and L(m).
    """
    if len(rebalance_dates) < 2:
        return []

    sess_idx_map = {d: i for i, d in enumerate(sessions)}
    sym_date_bar: dict[str, dict[date, StockDailyBar]] = {}
    sym_date_idx: dict[str, dict[date, int]] = {}
    for sym, b_list in bars_by_symbol.items():
        sym_date_bar[sym] = {b.date: b for b in b_list}
        sym_date_idx[sym] = {b.date: i for i, b in enumerate(b_list)}

    ew_returns: list[float] = []

    for m_idx in range(1, len(rebalance_dates)):
        prev_r = rebalance_dates[m_idx - 1]
        curr_r = rebalance_dates[m_idx]

        prev_r_idx = sess_idx_map.get(prev_r)
        if prev_r_idx is None or prev_r_idx < 1:
            ew_returns.append(0.0)
            continue

        r_minus = sessions[prev_r_idx - 1]

        # Universe at r_minus with lookback=20
        stock_rets: list[float] = []
        for sym, b_list in bars_by_symbol.items():
            r_minus_idx = sym_date_idx.get(sym, {}).get(r_minus)
            if r_minus_idx is None or r_minus_idx < 19:
                continue

            if not is_liquid(b_list, r_minus_idx, min_turnover=min_turnover):
                continue

            prev_b = sym_date_bar.get(sym, {}).get(prev_r)
            curr_b = sym_date_bar.get(sym, {}).get(curr_r)
            if prev_b is None or curr_b is None or prev_b.close <= 0:
                continue

            ret = (curr_b.close / prev_b.close) - 1.0
            stock_rets.append(float(ret))

        ew_m = float(np.mean(stock_rets)) if stock_rets else 0.0
        ew_returns.append(ew_m)

    return ew_returns


def calculate_rotation_metrics(
    monthly_r: list[float],
    monthly_ew: list[float],
    rebalance_dates: list[date],
    portfolio_metrics: dict[str, Any],
    seed: int = 193,
) -> dict[str, Any]:
    """Calculate core statistics on excess returns X_m = R_m - EW_m (§3.7)."""
    if len(monthly_r) != len(monthly_ew):
        raise ValueError("monthly_r and monthly_ew must have the same length")

    n = len(monthly_r)
    if n == 0:
        return {
            "n": 0,
            "mean_X": 0.0,
            "sharpe_X": 0.0,
            "p": 1.0,
            "skew": 0.0,
            "kurt": 3.0,
            "cagr_ew": 0.0,
            "mean_R": 0.0,
            "mean_EW": 0.0,
            "cagr": 0.0,
            "mdd": 0.0,
            "calmar": 0.0,
        }

    x_series = [r - ew for r, ew in zip(monthly_r, monthly_ew)]
    mean_x = float(np.mean(x_series))
    std_x = float(np.std(x_series, ddof=1)) if n > 1 else 0.0
    sharpe_x = (mean_x / std_x) if std_x > 0 else 0.0

    # Pearson skew & kurtosis
    arr = np.array(x_series)
    if n > 2 and std_x > 0:
        dev = arr - mean_x
        skew = float(np.mean(dev**3) / (std_x**3))
        kurt = float(np.mean(dev**4) / (std_x**4))
    else:
        skew = 0.0
        kurt = 3.0

    # Bootstrap p-value
    by_month: dict[tuple[int, int], list[float]] = {}
    for idx, x_val in enumerate(x_series):
        # associate each month with curr_r date
        m_date = rebalance_dates[idx + 1]
        by_month[(m_date.year, m_date.month)] = [x_val]

    res = bootstrap_by_month(by_month, n=2000, seed=seed, ci_low_pct=0.05, ci_high_pct=0.95)
    p_val = float(res["p"]) if res.get("p") is not None else 1.0

    # CAGR of EW benchmark
    total_ew_growth = float(np.prod([1.0 + ew for ew in monthly_ew]))
    start_date = rebalance_dates[0]
    end_date = rebalance_dates[-1]
    years = max(0.1, (end_date - start_date).days / 365.25)
    cagr_ew = (total_ew_growth ** (1.0 / years)) - 1.0 if total_ew_growth > 0 else -1.0

    return {
        "n": n,
        "mean_X": mean_x,
        "sharpe_X": sharpe_x,
        "p": p_val,
        "skew": skew,
        "kurt": kurt,
        "cagr_ew": cagr_ew,
        "mean_R": float(np.mean(monthly_r)),
        "mean_EW": float(np.mean(monthly_ew)),
        "cagr": portfolio_metrics.get("cagr", 0.0),
        "mdd": portfolio_metrics.get("mdd", 0.0),
        "calmar": portfolio_metrics.get("calmar", 0.0),
        "x_series": x_series,
    }
