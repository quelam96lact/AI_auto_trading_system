"""Strategy idea definitions and simulation rules for Brief 188.

Contains 6 rule functions corresponding to the registered ideas in ideas.md:
1. STK_WK_TREND_PULLBACK (Stock, Weekly + Daily)
2. STK_WK_VOL_BREAKOUT (Stock, Weekly + Daily)
3. STK_MN_TREND_WK_MOM (Stock, Monthly + Weekly + Daily)
4. CRY_1D_TREND_4H_PULLBACK (Crypto, 1D + 4h + 1h)
5. CRY_4H_VOL_BREAKOUT (Crypto, 1D + 4h + 1h)
6. STK_WK_DONCHIAN_CHANNEL (Stock, Weekly + Daily)

Strictly respects:
- No lookahead (higher timeframe bars pre-aligned with close_time <= lower close_time).
- Execution at open of t+1.
- Stocks: entry_status check, minimum 3 sessions holding constraint (T+2), stock net return.
- Crypto: taker round-trip fee (0.14%) + funding cost deduction (0.01% per 00/08/16 UTC).
- Trades recorded only if signal t is within [period_start, period_end].
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from scripts.research188_core import (
    Bar,
    Trade,
    compute_crypto_net_return,
    compute_stock_net_return,
)
from trading.stock_study import entry_status


def _compute_rsi(closes: np.ndarray, period: int) -> np.ndarray:
    """Compute RSI using Wilder's smoothing."""
    n = len(closes)
    rsi = np.full(n, 50.0)
    if n <= period:
        return rsi

    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        rsi[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period + 1, n):
        gain = gains[i - 1]
        loss = losses[i - 1]
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def _compute_sma(values: np.ndarray, window: int) -> np.ndarray:
    """Compute simple moving average."""
    n = len(values)
    sma = np.full(n, np.nan)
    if n < window:
        return sma
    cumsum = np.cumsum(np.insert(values, 0, 0))
    sma[window - 1 :] = (cumsum[window:] - cumsum[:-window]) / window
    return sma


def _compute_ema(values: np.ndarray, window: int) -> np.ndarray:
    """Compute exponential moving average."""
    n = len(values)
    ema = np.full(n, np.nan)
    if n < window:
        return ema
    alpha = 2.0 / (window + 1.0)
    ema[window - 1] = np.mean(values[:window])
    for i in range(window, n):
        ema[i] = alpha * values[i] + (1.0 - alpha) * ema[i - 1]
    return ema


# --- Idea 1: STK_WK_TREND_PULLBACK ---
def rule_idea1_stk_wk_trend_pullback(
    daily_bars: list[Bar],
    weekly_bars: list[Bar],
    aligned_wk: list[Bar | None],
    exchange: str,
    params: dict,
    period_start: datetime,
    period_end: datetime,
) -> list[Trade]:
    """Idea 1: Buy daily oversold dip when weekly trend is bullish.

    Params: w_period (int), rsi_len (int), rsi_thresh (float).
    """
    w_period = params["w_period"]
    rsi_len = params["rsi_len"]
    rsi_thresh = params["rsi_thresh"]

    n_daily = len(daily_bars)
    if n_daily < 30 or not weekly_bars:
        return []

    # Weekly SMA
    wk_closes = np.array([b.close for b in weekly_bars])
    wk_sma = _compute_sma(wk_closes, w_period)
    wk_sma_dict = {weekly_bars[i].close_time: wk_sma[i] for i in range(len(weekly_bars))}

    # Daily RSI & Daily SMA(10) for exit
    daily_closes = np.array([b.close for b in daily_bars])
    daily_rsi = _compute_rsi(daily_closes, rsi_len)
    daily_sma10 = _compute_sma(daily_closes, 10)

    trades: list[Trade] = []
    in_pos = False
    entry_idx = -1
    entry_p = 0.0
    entry_score = 0.0

    for t in range(n_daily - 1):
        if not in_pos:
            # Check entry signal at close of daily bar t
            cur_bar = daily_bars[t]
            if cur_bar.ts < period_start or cur_bar.ts > period_end:
                continue

            hb = aligned_wk[t]
            if hb is None:
                continue

            hb_sma = wk_sma_dict.get(hb.close_time)
            if hb_sma is None or np.isnan(hb_sma):
                continue

            # Bullish weekly trend and oversold daily RSI
            if hb.close > hb_sma and daily_rsi[t] < rsi_thresh:
                # Check entry status at open t+1
                status = entry_status(daily_bars, t, exchange)
                if status == "ok" and daily_bars[t + 1].open > 0:
                    in_pos = True
                    entry_idx = t + 1
                    entry_p = daily_bars[t + 1].open
                    entry_score = rsi_thresh - daily_rsi[t]
        else:
            # Holding position: minimum 3 sessions (T+2)
            held_sessions = t - entry_idx + 1
            if held_sessions >= 3:
                # Exit condition: daily close > SMA10 or max 15 sessions
                exit_signal = (daily_sma10[t] is not None and daily_bars[t].close > daily_sma10[t]) or (held_sessions >= 15)
                if exit_signal:
                    exit_idx = t + 1
                    if exit_idx < n_daily and daily_bars[exit_idx].open > 0:
                        exit_p = daily_bars[exit_idx].open
                        exit_ts = daily_bars[exit_idx].ts
                        net_ret = compute_stock_net_return(entry_p, exit_p)
                        gross_ret = (exit_p / entry_p) - 1.0
                        trades.append(
                            Trade(
                                symbol=daily_bars[0].symbol,
                                entry_ts=daily_bars[entry_idx].ts,
                                exit_ts=exit_ts,
                                entry_price=entry_p,
                                exit_price=exit_p,
                                net_return=net_ret,
                                gross_return=gross_ret,
                                market="stock",
                                side="long",
                                score=entry_score,
                                holding_sessions=held_sessions + 1,
                            )
                        )
                    in_pos = False
                    entry_idx = -1

    return trades


# --- Idea 2: STK_WK_VOL_BREAKOUT ---
def rule_idea2_stk_wk_vol_breakout(
    daily_bars: list[Bar],
    weekly_bars: list[Bar],
    aligned_wk: list[Bar | None],
    exchange: str,
    params: dict,
    period_start: datetime,
    period_end: datetime,
) -> list[Trade]:
    """Idea 2: Daily breakout with volume expansion following weekly volatility contraction.

    Params: vol_thresh (float), n_days (int), exit_days (int).
    """
    vol_thresh = params["vol_thresh"]
    n_days = params["n_days"]
    exit_days = params["exit_days"]

    n_daily = len(daily_bars)
    if n_daily < max(n_days, exit_days, 30) or not weekly_bars:
        return []

    # Weekly volatility range: (high - low) / close
    wk_vol_dict = {
        b.close_time: (b.high - b.low) / b.close if b.close > 0 else 1.0
        for b in weekly_bars
    }

    # Daily volume SMA(20)
    daily_vols = np.array([b.volume for b in daily_bars])
    daily_sma_vol = _compute_sma(daily_vols, 20)

    trades: list[Trade] = []
    in_pos = False
    entry_idx = -1
    entry_p = 0.0
    entry_score = 0.0

    for t in range(n_days, n_daily - 1):
        if not in_pos:
            cur_bar = daily_bars[t]
            if cur_bar.ts < period_start or cur_bar.ts > period_end:
                continue

            hb = aligned_wk[t]
            if hb is None:
                continue

            hb_vol = wk_vol_dict.get(hb.close_time, 1.0)
            if hb_vol < vol_thresh:
                # Daily breakout: close > max(high of previous n_days)
                prev_highs = [daily_bars[j].high for j in range(t - n_days, t)]
                max_high = max(prev_highs)
                sma_v = daily_sma_vol[t]

                if cur_bar.close > max_high and sma_v > 0 and cur_bar.volume > 1.3 * sma_v:
                    status = entry_status(daily_bars, t, exchange)
                    if status == "ok" and daily_bars[t + 1].open > 0:
                        in_pos = True
                        entry_idx = t + 1
                        entry_p = daily_bars[t + 1].open
                        entry_score = cur_bar.volume / sma_v
        else:
            held_sessions = t - entry_idx + 1
            if held_sessions >= 3:
                # Exit when daily close drops below min(low of previous exit_days)
                start_j = max(0, t - exit_days)
                min_low = min(daily_bars[j].low for j in range(start_j, t))
                if daily_bars[t].close < min_low or held_sessions >= 40:
                    exit_idx = t + 1
                    if exit_idx < n_daily and daily_bars[exit_idx].open > 0:
                        exit_p = daily_bars[exit_idx].open
                        exit_ts = daily_bars[exit_idx].ts
                        net_ret = compute_stock_net_return(entry_p, exit_p)
                        gross_ret = (exit_p / entry_p) - 1.0
                        trades.append(
                            Trade(
                                symbol=daily_bars[0].symbol,
                                entry_ts=daily_bars[entry_idx].ts,
                                exit_ts=exit_ts,
                                entry_price=entry_p,
                                exit_price=exit_p,
                                net_return=net_ret,
                                gross_return=gross_ret,
                                market="stock",
                                side="long",
                                score=entry_score,
                                holding_sessions=held_sessions + 1,
                            )
                        )
                    in_pos = False
                    entry_idx = -1

    return trades


# --- Idea 3: STK_MN_TREND_WK_MOM ---
def rule_idea3_stk_mn_trend_wk_mom(
    daily_bars: list[Bar],
    weekly_bars: list[Bar],
    monthly_bars: list[Bar],
    aligned_wk: list[Bar | None],
    aligned_mn: list[Bar | None],
    exchange: str,
    params: dict,
    period_start: datetime,
    period_end: datetime,
) -> list[Trade]:
    """Idea 3: Monthly trend regime filter combined with weekly momentum surge.

    Params: m_len (int), k_weeks (int), mom_thresh (float).
    """
    m_len = params["m_len"]
    k_weeks = params["k_weeks"]
    mom_thresh = params["mom_thresh"]

    n_daily = len(daily_bars)
    if n_daily < 60 or not weekly_bars or not monthly_bars:
        return []

    # Monthly SMA(m_len)
    mn_closes = np.array([b.close for b in monthly_bars])
    mn_sma = _compute_sma(mn_closes, m_len)
    mn_sma_dict = {monthly_bars[i].close_time: mn_sma[i] for i in range(len(monthly_bars))}

    # Weekly momentum: weekly_close / weekly_close[t-k_weeks] - 1.0
    wk_closes = [b.close for b in weekly_bars]
    wk_mom_dict: dict[datetime, float] = {}
    for i in range(k_weeks, len(weekly_bars)):
        ct = weekly_bars[i].close_time
        base_c = wk_closes[i - k_weeks]
        if base_c > 0:
            wk_mom_dict[ct] = (wk_closes[i] / base_c) - 1.0

    # Daily SMA(20) for exit
    daily_closes = np.array([b.close for b in daily_bars])
    daily_sma20 = _compute_sma(daily_closes, 20)

    trades: list[Trade] = []
    in_pos = False
    entry_idx = -1
    entry_p = 0.0
    entry_score = 0.0

    for t in range(n_daily - 1):
        if not in_pos:
            cur_bar = daily_bars[t]
            if cur_bar.ts < period_start or cur_bar.ts > period_end:
                continue

            hb_mn = aligned_mn[t]
            hb_wk = aligned_wk[t]
            if hb_mn is None or hb_wk is None:
                continue

            mn_s = mn_sma_dict.get(hb_mn.close_time)
            if mn_s is None or np.isnan(mn_s):
                continue

            if hb_mn.close > mn_s:
                mom_val = wk_mom_dict.get(hb_wk.close_time, 0.0)
                if mom_val > mom_thresh:
                    status = entry_status(daily_bars, t, exchange)
                    if status == "ok" and daily_bars[t + 1].open > 0:
                        in_pos = True
                        entry_idx = t + 1
                        entry_p = daily_bars[t + 1].open
                        entry_score = mom_val
        else:
            held_sessions = t - entry_idx + 1
            if held_sessions >= 3:
                # Exit when daily close < SMA20 or max 30 sessions
                s20 = daily_sma20[t]
                if (s20 is not None and daily_bars[t].close < s20) or held_sessions >= 30:
                    exit_idx = t + 1
                    if exit_idx < n_daily and daily_bars[exit_idx].open > 0:
                        exit_p = daily_bars[exit_idx].open
                        exit_ts = daily_bars[exit_idx].ts
                        net_ret = compute_stock_net_return(entry_p, exit_p)
                        gross_ret = (exit_p / entry_p) - 1.0
                        trades.append(
                            Trade(
                                symbol=daily_bars[0].symbol,
                                entry_ts=daily_bars[entry_idx].ts,
                                exit_ts=exit_ts,
                                entry_price=entry_p,
                                exit_price=exit_p,
                                net_return=net_ret,
                                gross_return=gross_ret,
                                market="stock",
                                side="long",
                                score=entry_score,
                                holding_sessions=held_sessions + 1,
                            )
                        )
                    in_pos = False
                    entry_idx = -1

    return trades


# --- Idea 4: CRY_1D_TREND_4H_PULLBACK ---
def rule_idea4_cry_1d_trend_4h_pullback(
    bars_1h: list[Bar],
    bars_4h: list[Bar],
    bars_1d: list[Bar],
    aligned_4h: list[Bar | None],
    aligned_1d: list[Bar | None],
    params: dict,
    period_start: datetime,
    period_end: datetime,
) -> list[Trade]:
    """Idea 4: Crypto 1D trend regime filter combined with 4h RSI oversold/overbought exhaustion.

    Params: d_period (int), rsi_low (float), exit_len (int).
    """
    d_period = params["d_period"]
    rsi_low = params["rsi_low"]
    exit_len = params["exit_len"]

    n_1h = len(bars_1h)
    if n_1h < 100 or not bars_4h or not bars_1d:
        return []

    # 1D SMA(d_period)
    closes_1d = np.array([b.close for b in bars_1d])
    sma_1d = _compute_sma(closes_1d, d_period)
    sma_1d_dict = {bars_1d[i].close_time: sma_1d[i] for i in range(len(bars_1d))}

    # 4h RSI(14) and 4h SMA(exit_len)
    closes_4h = np.array([b.close for b in bars_4h])
    rsi_4h = _compute_rsi(closes_4h, 14)
    sma_4h_exit = _compute_sma(closes_4h, exit_len)

    rsi_4h_dict = {bars_4h[i].close_time: rsi_4h[i] for i in range(len(bars_4h))}
    sma_4h_dict = {bars_4h[i].close_time: sma_4h_exit[i] for i in range(len(bars_4h))}

    trades: list[Trade] = []
    in_pos = False
    side = "long"
    entry_idx = -1
    entry_p = 0.0
    entry_score = 0.0

    for t in range(n_1h - 1):
        if not in_pos:
            cur_bar = bars_1h[t]
            if cur_bar.ts < period_start or cur_bar.ts > period_end:
                continue

            hb_1d = aligned_1d[t]
            hb_4h = aligned_4h[t]
            if hb_1d is None or hb_4h is None:
                continue

            s_1d = sma_1d_dict.get(hb_1d.close_time)
            r_4h = rsi_4h_dict.get(hb_4h.close_time)
            if s_1d is None or np.isnan(s_1d) or r_4h is None:
                continue

            # Long condition: 1D close > 1D SMA and 4h RSI < rsi_low
            if hb_1d.close > s_1d and r_4h < rsi_low and bars_1h[t + 1].open > 0:
                in_pos = True
                side = "long"
                entry_idx = t + 1
                entry_p = bars_1h[t + 1].open
                entry_score = rsi_low - r_4h
            # Short condition: 1D close < 1D SMA and 4h RSI > 100 - rsi_low
            elif hb_1d.close < s_1d and r_4h > (100.0 - rsi_low) and bars_1h[t + 1].open > 0:
                in_pos = True
                side = "short"
                entry_idx = t + 1
                entry_p = bars_1h[t + 1].open
                entry_score = r_4h - (100.0 - rsi_low)
        else:
            held_bars = t - entry_idx + 1
            hb_4h = aligned_4h[t]
            s_exit = sma_4h_dict.get(hb_4h.close_time) if hb_4h else None

            # Exit condition
            exit_signal = False
            if s_exit is not None and not np.isnan(s_exit) and (
                (side == "long" and bars_1h[t].close >= s_exit)
                or (side == "short" and bars_1h[t].close <= s_exit)
            ):
                exit_signal = True

            if exit_signal or held_bars >= 24:
                exit_idx = t + 1
                if exit_idx < n_1h and bars_1h[exit_idx].open > 0:
                    exit_p = bars_1h[exit_idx].open
                    entry_ts = bars_1h[entry_idx].ts
                    exit_ts = bars_1h[exit_idx].ts
                    net_ret, gross_ret = compute_crypto_net_return(
                        entry_p, exit_p, side, entry_ts, exit_ts
                    )
                    trades.append(
                        Trade(
                            symbol=bars_1h[0].symbol,
                            entry_ts=entry_ts,
                            exit_ts=exit_ts,
                            entry_price=entry_p,
                            exit_price=exit_p,
                            net_return=net_ret,
                            gross_return=gross_ret,
                            market="crypto",
                            side=side,
                            score=entry_score,
                            holding_sessions=held_bars + 1,
                        )
                    )
                in_pos = False
                entry_idx = -1

    return trades


# --- Idea 5: CRY_4H_VOL_BREAKOUT ---
def rule_idea5_cry_4h_vol_breakout(
    bars_1h: list[Bar],
    bars_4h: list[Bar],
    bars_1d: list[Bar],
    aligned_4h: list[Bar | None],
    aligned_1d: list[Bar | None],
    params: dict,
    period_start: datetime,
    period_end: datetime,
) -> list[Trade]:
    """Idea 5: 4h Bollinger Bands breakout aligned with 1D EMA trend.

    Params: trend_len (int), bb_len (int), bb_std (float).
    """
    trend_len = params["trend_len"]
    bb_len = params["bb_len"]
    bb_std = params["bb_std"]

    n_1h = len(bars_1h)
    if n_1h < 100 or not bars_4h or not bars_1d:
        return []

    # 1D EMA(trend_len)
    closes_1d = np.array([b.close for b in bars_1d])
    ema_1d = _compute_ema(closes_1d, trend_len)
    ema_1d_dict = {bars_1d[i].close_time: ema_1d[i] for i in range(len(bars_1d))}

    # 4h Bollinger Bands
    closes_4h = np.array([b.close for b in bars_4h])
    sma_4h = _compute_sma(closes_4h, bb_len)

    bb_upper_dict: dict[datetime, float] = {}
    bb_lower_dict: dict[datetime, float] = {}
    bb_mid_dict: dict[datetime, float] = {}

    for i in range(bb_len - 1, len(bars_4h)):
        ct = bars_4h[i].close_time
        std = np.std(closes_4h[i - bb_len + 1 : i + 1])
        mid = sma_4h[i]
        bb_upper_dict[ct] = mid + bb_std * std
        bb_lower_dict[ct] = mid - bb_std * std
        bb_mid_dict[ct] = mid

    trades: list[Trade] = []
    in_pos = False
    side = "long"
    entry_idx = -1
    entry_p = 0.0
    entry_score = 0.0

    for t in range(n_1h - 1):
        if not in_pos:
            cur_bar = bars_1h[t]
            if cur_bar.ts < period_start or cur_bar.ts > period_end:
                continue

            hb_1d = aligned_1d[t]
            hb_4h = aligned_4h[t]
            if hb_1d is None or hb_4h is None:
                continue

            e_1d = ema_1d_dict.get(hb_1d.close_time)
            up_bb = bb_upper_dict.get(hb_4h.close_time)
            lo_bb = bb_lower_dict.get(hb_4h.close_time)

            if e_1d is None or np.isnan(e_1d) or up_bb is None or lo_bb is None:
                continue

            # Long breakout
            if hb_1d.close > e_1d and up_bb > 0 and hb_4h.close > up_bb and bars_1h[t + 1].open > 0:
                in_pos = True
                side = "long"
                entry_idx = t + 1
                entry_p = bars_1h[t + 1].open
                entry_score = (hb_4h.close / up_bb) - 1.0
            # Short breakout
            elif hb_1d.close < e_1d and lo_bb > 0 and hb_4h.close < lo_bb and bars_1h[t + 1].open > 0:
                in_pos = True
                side = "short"
                entry_idx = t + 1
                entry_p = bars_1h[t + 1].open
                entry_score = 1.0 - (hb_4h.close / lo_bb)
        else:
            held_bars = t - entry_idx + 1
            hb_4h = aligned_4h[t]
            mid_bb = bb_mid_dict.get(hb_4h.close_time) if hb_4h else None

            exit_signal = False
            if mid_bb is not None and (
                (side == "long" and bars_1h[t].close <= mid_bb)
                or (side == "short" and bars_1h[t].close >= mid_bb)
            ):
                exit_signal = True

            if exit_signal or held_bars >= 36:
                exit_idx = t + 1
                if exit_idx < n_1h and bars_1h[exit_idx].open > 0:
                    exit_p = bars_1h[exit_idx].open
                    entry_ts = bars_1h[entry_idx].ts
                    exit_ts = bars_1h[exit_idx].ts
                    net_ret, gross_ret = compute_crypto_net_return(
                        entry_p, exit_p, side, entry_ts, exit_ts
                    )
                    trades.append(
                        Trade(
                            symbol=bars_1h[0].symbol,
                            entry_ts=entry_ts,
                            exit_ts=exit_ts,
                            entry_price=entry_p,
                            exit_price=exit_p,
                            net_return=net_ret,
                            gross_return=gross_ret,
                            market="crypto",
                            side=side,
                            score=entry_score,
                            holding_sessions=held_bars + 1,
                        )
                    )
                in_pos = False
                entry_idx = -1

    return trades


# --- Idea 6: STK_WK_DONCHIAN_CHANNEL ---
def rule_idea6_stk_wk_donchian_channel(
    daily_bars: list[Bar],
    weekly_bars: list[Bar],
    aligned_wk: list[Bar | None],
    exchange: str,
    params: dict,
    period_start: datetime,
    period_end: datetime,
) -> list[Trade]:
    """Idea 6: Multi-week Donchian breakout on weekly closed candles.

    Params: n_weeks (int), exit_weeks (int).
    """
    n_weeks = params["n_weeks"]
    exit_weeks = params["exit_weeks"]

    n_daily = len(daily_bars)
    if n_daily < 50 or len(weekly_bars) < max(n_weeks, exit_weeks) + 2:
        return []

    # Weekly Donchian Channels
    wk_highs = [b.high for b in weekly_bars]
    wk_lows = [b.low for b in weekly_bars]

    wk_donchian_high: dict[datetime, float] = {}
    wk_donchian_low: dict[datetime, float] = {}

    for i in range(len(weekly_bars)):
        ct = weekly_bars[i].close_time
        if i >= n_weeks:
            wk_donchian_high[ct] = max(wk_highs[i - n_weeks : i])
        if i >= exit_weeks:
            wk_donchian_low[ct] = min(wk_lows[i - exit_weeks : i])

    trades: list[Trade] = []
    in_pos = False
    entry_idx = -1
    entry_p = 0.0
    entry_score = 0.0

    for t in range(n_daily - 1):
        if not in_pos:
            cur_bar = daily_bars[t]
            if cur_bar.ts < period_start or cur_bar.ts > period_end:
                continue

            hb = aligned_wk[t]
            if hb is None:
                continue

            dh = wk_donchian_high.get(hb.close_time)
            if dh is not None and dh > 0 and hb.close > dh:
                status = entry_status(daily_bars, t, exchange)
                if status == "ok" and daily_bars[t + 1].open > 0:
                    in_pos = True
                    entry_idx = t + 1
                    entry_p = daily_bars[t + 1].open
                    entry_score = (hb.close / dh) - 1.0
        else:
            held_sessions = t - entry_idx + 1
            if held_sessions >= 3:
                hb = aligned_wk[t]
                dl = wk_donchian_low.get(hb.close_time) if hb else None
                if (dl is not None and hb.close < dl) or held_sessions >= 50:
                    exit_idx = t + 1
                    if exit_idx < n_daily and daily_bars[exit_idx].open > 0:
                        exit_p = daily_bars[exit_idx].open
                        exit_ts = daily_bars[exit_idx].ts
                        net_ret = compute_stock_net_return(entry_p, exit_p)
                        gross_ret = (exit_p / entry_p) - 1.0
                        trades.append(
                            Trade(
                                symbol=daily_bars[0].symbol,
                                entry_ts=daily_bars[entry_idx].ts,
                                exit_ts=exit_ts,
                                entry_price=entry_p,
                                exit_price=exit_p,
                                net_return=net_ret,
                                gross_return=gross_ret,
                                market="stock",
                                side="long",
                                score=entry_score,
                                holding_sessions=held_sessions + 1,
                            )
                        )
                    in_pos = False
                    entry_idx = -1

    return trades
