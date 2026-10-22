"""Core multi-timeframe backtesting and anti-overfitting library for Brief 188.

Includes:
- Strict resample (1W, 1M for stocks; 4h, 1d for crypto) with explicit close_time.
- align_higher preventing look-ahead bias (only closed higher bars with close_time <= lower close_time).
- Order execution at open of t+1, minimum 3-session hold for stocks (T+2), entry_status check.
- Realistic costs: stock net_return with fee/tax/slippage; crypto 0.14% round-trip fee + 0.01% funding per 00/08/16 UTC.
- Performance metrics, portfolio simulation (10 slots stock, 5 slots crypto), baseline excess return.
- Deflated Sharpe Ratio (DSR) using Bailey & López de Prado (2014) Euler-Mascheroni approximation.
"""

from __future__ import annotations

import bisect
import calendar
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
from scipy.stats import norm

from scripts.research188_data import TZ_VN, Bar
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.stock_study import bootstrap_by_month

# Crypto fee constants (BingX VIP0 taker 0.05% + slippage 0.02% per side = 0.14% round-trip)
CRYPTO_FEE_ROUNDTRIP = 0.0014
CRYPTO_FUNDING_RATE = 0.0001  # 0.01% per funding timestamp (00/08/16 UTC) crossed


@dataclass(slots=True)
class Trade:
    symbol: str
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    net_return: float
    gross_return: float
    market: str  # "stock" or "crypto"
    side: str  # "long" or "short"
    score: float = 0.0
    holding_sessions: int = 1


def resample(bars: list[Bar], rule: str) -> list[Bar]:
    """Resample lower timeframe bars into higher timeframe bars with explicit close_time.

    Rules supported:
    - '1W', 'W', 'weekly': Stock daily -> weekly (week ends on Friday 15:00 VN time).
    - '1M', 'M', 'monthly': Stock daily -> monthly (month ends on last calendar day 15:00 VN time).
    - '4h': Crypto 1h -> 4h (boundaries 00, 04, 08, 12, 16, 20 UTC).
    - '1d', 'D': Crypto 1h -> 1d (boundary 00:00 UTC).
    """
    if not bars:
        return []

    rule_upper = rule.upper()
    if rule_upper in ("1W", "W", "WEEKLY"):
        return _resample_stocks_weekly(bars)
    elif rule_upper in ("1M", "M", "MONTHLY"):
        return _resample_stocks_monthly(bars)
    elif rule.lower() == "4h":
        return _resample_crypto_4h(bars)
    elif rule.lower() in ("1d", "d"):
        return _resample_crypto_1d(bars)
    else:
        raise ValueError(f"Unsupported resample rule: {rule}")


def _resample_stocks_weekly(bars: list[Bar]) -> list[Bar]:
    """Group stock daily bars into weekly bars. Week ends on Friday 15:00 VN time."""
    weeks: dict[tuple[int, int], list[Bar]] = {}
    for b in bars:
        iso_year, iso_week, _ = b.ts.isocalendar()
        key = (iso_year, iso_week)
        if key not in weeks:
            weeks[key] = []
        weeks[key].append(b)

    res: list[Bar] = []
    for (iso_year, iso_week), group in sorted(weeks.items()):
        # Friday of the ISO week
        mon = date.fromisocalendar(iso_year, iso_week, 1)
        fri = mon + timedelta(days=4)
        ct = datetime(fri.year, fri.month, fri.day, 15, 0, tzinfo=TZ_VN)
        res.append(
            Bar(
                symbol=group[0].symbol,
                ts=group[0].ts,
                open=group[0].open,
                high=max(g.high for g in group),
                low=min(g.low for g in group),
                close=group[-1].close,
                volume=sum(g.volume for g in group),
                close_time=ct,
            )
        )
    return res


def _resample_stocks_monthly(bars: list[Bar]) -> list[Bar]:
    """Group stock daily bars into monthly bars. Month ends on last day of month 15:00 VN time."""
    months: dict[tuple[int, int], list[Bar]] = {}
    for b in bars:
        key = (b.ts.year, b.ts.month)
        if key not in months:
            months[key] = []
        months[key].append(b)

    res: list[Bar] = []
    for (y, m), group in sorted(months.items()):
        _, last_day = calendar.monthrange(y, m)
        ct = datetime(y, m, last_day, 15, 0, tzinfo=TZ_VN)
        res.append(
            Bar(
                symbol=group[0].symbol,
                ts=group[0].ts,
                open=group[0].open,
                high=max(g.high for g in group),
                low=min(g.low for g in group),
                close=group[-1].close,
                volume=sum(g.volume for g in group),
                close_time=ct,
            )
        )
    return res


def _resample_crypto_4h(bars: list[Bar]) -> list[Bar]:
    """Group crypto 1h bars into 4h bars (00, 04, 08, 12, 16, 20 UTC)."""
    blocks: dict[datetime, list[Bar]] = {}
    for b in bars:
        bucket_hour = (b.ts.hour // 4) * 4
        bucket_ts = b.ts.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)
        if bucket_ts not in blocks:
            blocks[bucket_ts] = []
        blocks[bucket_ts].append(b)

    res: list[Bar] = []
    for bucket_ts, group in sorted(blocks.items()):
        ct = bucket_ts + timedelta(hours=4)
        res.append(
            Bar(
                symbol=group[0].symbol,
                ts=bucket_ts,
                open=group[0].open,
                high=max(g.high for g in group),
                low=min(g.low for g in group),
                close=group[-1].close,
                volume=sum(g.volume for g in group),
                close_time=ct,
            )
        )
    return res


def _resample_crypto_1d(bars: list[Bar]) -> list[Bar]:
    """Group crypto 1h bars into 1d bars (boundary 00:00 UTC)."""
    blocks: dict[datetime, list[Bar]] = {}
    for b in bars:
        bucket_ts = b.ts.replace(hour=0, minute=0, second=0, microsecond=0)
        if bucket_ts not in blocks:
            blocks[bucket_ts] = []
        blocks[bucket_ts].append(b)

    res: list[Bar] = []
    for bucket_ts, group in sorted(blocks.items()):
        ct = bucket_ts + timedelta(days=1)
        res.append(
            Bar(
                symbol=group[0].symbol,
                ts=bucket_ts,
                open=group[0].open,
                high=max(g.high for g in group),
                low=min(g.low for g in group),
                close=group[-1].close,
                volume=sum(g.volume for g in group),
                close_time=ct,
            )
        )
    return res


def align_higher(lower_bars: list[Bar], higher_bars: list[Bar]) -> list[Bar | None]:
    """Align higher timeframe bars to lower timeframe bars without look-ahead bias.

    For each lower bar t, returns the latest closed higher bar having
    higher_bar.close_time <= lower_bar.close_time.
    If no higher bar has closed yet, returns None.
    """
    if not lower_bars or not higher_bars:
        return [None] * len(lower_bars)

    higher_close_times = [b.close_time for b in higher_bars]
    aligned: list[Bar | None] = []

    for lb in lower_bars:
        # bisect_right finds index where higher_close_times <= lb.close_time
        idx = bisect.bisect_right(higher_close_times, lb.close_time)
        if idx > 0:
            aligned.append(higher_bars[idx - 1])
        else:
            aligned.append(None)

    return aligned


def compute_stock_net_return(entry_price: float, exit_price: float) -> float:
    """Calculate net return for stock trade including fees, taxes, and slippage."""
    if entry_price <= 0 or exit_price <= 0:
        return 0.0
    s = SLIPPAGE_BPS / 10_000.0
    cost_in = 1.0 + FEE_RATE + s
    cost_out = 1.0 - FEE_RATE - SELL_TAX_RATE - s
    return (exit_price * cost_out) / (entry_price * cost_in) - 1.0


def count_crypto_funding_intervals(entry_ts: datetime, exit_ts: datetime) -> int:
    """Count number of 00:00, 08:00, 16:00 UTC boundaries crossed in (entry_ts, exit_ts]."""
    # Start scanning from the first 8-hour boundary strictly after entry_ts up to exit_ts
    count = 0
    cur = entry_ts.replace(minute=0, second=0, microsecond=0)
    # Next funding boundary
    cur_hour = (cur.hour // 8 + 1) * 8
    cur = cur.replace(hour=0) + timedelta(hours=cur_hour)

    while cur <= exit_ts:
        if cur > entry_ts:
            count += 1
        cur += timedelta(hours=8)
    return count


def compute_crypto_net_return(
    entry_price: float,
    exit_price: float,
    side: str,
    entry_ts: datetime,
    exit_ts: datetime,
) -> tuple[float, float]:
    """Compute crypto net and gross returns including taker fees (0.14% round-trip) and funding.

    Returns:
        (net_return, gross_return)
    """
    if entry_price <= 0 or exit_price <= 0:
        return 0.0, 0.0

    if side == "long":
        gross = exit_price / entry_price - 1.0
    elif side == "short":
        gross = 1.0 - exit_price / entry_price
    else:
        raise ValueError(f"Invalid side: {side}")

    num_funding = count_crypto_funding_intervals(entry_ts, exit_ts)
    funding_cost = num_funding * CRYPTO_FUNDING_RATE
    net = gross - CRYPTO_FEE_ROUNDTRIP - funding_cost
    return net, gross


def deflated_sharpe(
    sr: float,
    n_obs: int,
    skew: float,
    kurt: float,
    n_trials: int,
    sr_trials_var: float,
) -> float:
    """Compute Deflated Sharpe Ratio (DSR) following Bailey & López de Prado (2014).

    Uses Euler-Mascheroni approximation (Formula 2) for expected maximum Sharpe ratio.

    When n_trials = 1, sr_star = 0 (DSR = PSR(0)).
    As n_trials increases, sr_star increases and DSR decreases monotonically.
    """
    if n_obs <= 1:
        return 0.0

    # Mertens (2002) standard error of Sharpe ratio
    var_sr = (1.0 - skew * sr + ((kurt - 1.0) / 4.0) * (sr**2)) / (n_obs - 1)
    if var_sr <= 0:
        se_sr = 1e-6
    else:
        se_sr = math.sqrt(var_sr)

    if n_trials <= 1:
        sr_star = 0.0
    else:
        # Euler-Mascheroni approximation
        gamma = 0.5772156649015329
        e_const = math.e
        p1 = 1.0 - 1.0 / n_trials
        p2 = 1.0 - 1.0 / (n_trials * e_const)

        z1 = float(norm.ppf(p1))
        z2 = float(norm.ppf(p2))

        sr_sd = math.sqrt(max(0.0, sr_trials_var))
        sr_star = sr_sd * ((1.0 - gamma) * z1 + gamma * z2)

    z = (sr - sr_star) / se_sr
    return float(norm.cdf(z))


def calculate_trade_metrics(trades: list[Trade]) -> dict[str, Any]:
    """Calculate core metrics: n, mean_net, per-trade Sharpe, and bootstrap p-value."""
    n = len(trades)
    if n == 0:
        return {
            "n": 0,
            "mean_net": 0.0,
            "sharpe": 0.0,
            "p": 1.0,
            "skew": 0.0,
            "kurt": 3.0,
        }

    net_returns = [t.net_return for t in trades]
    mean_net = float(np.mean(net_returns))
    std_net = float(np.std(net_returns, ddof=1)) if n > 1 else 0.0
    sharpe = (mean_net / std_net) if std_net > 0 else 0.0

    # Skewness and kurtosis (Pearson kurtosis, normal = 3.0)
    arr = np.array(net_returns)
    if n > 2 and std_net > 0:
        dev = arr - mean_net
        skew = float(np.mean(dev**3) / (std_net**3))
        kurt = float(np.mean(dev**4) / (std_net**4))
    else:
        skew = 0.0
        kurt = 3.0

    # Bootstrap by month
    by_month: dict[tuple[int, int], list[float]] = {}
    for t in trades:
        m_key = (t.entry_ts.year, t.entry_ts.month)
        if m_key not in by_month:
            by_month[m_key] = []
        by_month[m_key].append(t.net_return)

    bs_res = bootstrap_by_month(
        by_month, n=2000, seed=188, ci_low_pct=0.05, ci_high_pct=0.95
    )
    p_val = bs_res["p"] if bs_res["p"] is not None else 1.0

    return {
        "n": n,
        "mean_net": mean_net,
        "sharpe": sharpe,
        "p": p_val,
        "skew": skew,
        "kurt": kurt,
    }


def simulate_portfolio(
    trades: list[Trade],
    market: str,
    initial_capital: float = 100_000_000.0,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, float]:
    """Simulate slot-based portfolio equity curve.

    - Stocks: 10 slots (10% capital per slot, long-only).
    - Crypto: 5 slots (20% capital per slot, 1x leverage, long/short).
    - Excess signals rejected when slots are full; prioritized by trade.score desc, symbol asc.
    """
    if not trades:
        return {"cagr": 0.0, "mdd": 0.0, "calmar": 0.0}

    max_slots = 10 if market == "stock" else 5
    slot_alloc = 1.0 / max_slots

    # Sort trades by entry_ts, then priority score desc, symbol asc
    sorted_trades = sorted(
        trades, key=lambda t: (t.entry_ts, -t.score, t.symbol)
    )

    # Filter accepted trades based on slot availability
    accepted_trades: list[Trade] = []
    # Active positions: list of (exit_ts, trade)
    active_slots: list[Trade] = []

    for t in sorted_trades:
        # Free up positions that have exited before or at this trade's entry_ts
        active_slots = [p for p in active_slots if p.exit_ts > t.entry_ts]
        if len(active_slots) < max_slots:
            active_slots.append(t)
            accepted_trades.append(t)

    if not accepted_trades:
        return {"cagr": 0.0, "mdd": 0.0, "calmar": 0.0}

    # Build daily equity curve
    # Find overall min and max dates
    min_d = start_date or min(t.entry_ts.date() for t in accepted_trades)
    max_d = end_date or max(t.exit_ts.date() for t in accepted_trades)

    # Days count
    total_days = max(1, (max_d - min_d).days)

    # Track returns compound per trade into portfolio
    # Each accepted trade contributes slot_alloc * net_return at its exit
    # Track equity over time
    events: list[tuple[date, float]] = []
    for t in accepted_trades:
        events.append((t.exit_ts.date(), slot_alloc * t.net_return))

    events.sort(key=lambda x: x[0])

    equity = initial_capital
    peak = equity
    mdd = 0.0

    cur_idx = 0
    cur_d = min_d
    while cur_d <= max_d:
        daily_ret = 0.0
        while cur_idx < len(events) and events[cur_idx][0] == cur_d:
            daily_ret += events[cur_idx][1]
            cur_idx += 1

        equity *= 1.0 + daily_ret
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak > 0 else 0.0
        mdd = max(mdd, dd)
        cur_d += timedelta(days=1)

    total_return = equity / initial_capital
    years = max(0.1, total_days / 365.25)
    cagr = (total_return ** (1.0 / years) - 1.0) if total_return > 0 else -1.0
    calmar = (cagr / mdd) if mdd > 0 else (cagr if cagr > 0 else 0.0)

    return {"cagr": cagr, "mdd": mdd, "calmar": calmar}


def calculate_stock_baseline_excess(
    trades: list[Trade],
    all_stock_bars: dict[str, list[Bar]],
) -> dict[str, float]:
    """Calculate excess return of stock trades vs equal-weighted explore universe.

    Baseline for each trade i: mean return of all explore stocks that have bars
    on both entry date and exit date.
    Reports:
    - mean_excess: average of (trade_net_return - baseline_return)
    - mean_excess_trim1pct: average after removing top 1% highest excess return trades.
    """
    if not trades:
        return {"mean_excess": 0.0, "mean_excess_trim1pct": 0.0}

    # Pre-index bars by date for fast lookup: date -> {symbol: (open, close)}
    date_prices: dict[date, dict[str, tuple[float, float]]] = {}
    for sym, b_list in all_stock_bars.items():
        for b in b_list:
            d = b.ts.date()
            if d not in date_prices:
                date_prices[d] = {}
            date_prices[d][sym] = (b.open, b.close)

    excess_returns: list[float] = []
    for t in trades:
        entry_d = t.entry_ts.date()
        exit_d = t.exit_ts.date()

        prices_entry = date_prices.get(entry_d, {})
        prices_exit = date_prices.get(exit_d, {})

        common_symbols = set(prices_entry.keys()) & set(prices_exit.keys())
        if common_symbols:
            # Baseline: equal-weighted return of holding from entry open to exit open
            # (or exit close if exit is close)
            # In our trade execution, exit occurs at exit_ts open
            base_rets = [
                prices_exit[s][0] / prices_entry[s][0] - 1.0
                for s in common_symbols
                if prices_entry[s][0] > 0
            ]
            baseline_ret = float(np.mean(base_rets)) if base_rets else 0.0
        else:
            baseline_ret = 0.0

        excess_returns.append(t.net_return - baseline_ret)

    mean_excess = float(np.mean(excess_returns))

    # Trim top 1%
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
