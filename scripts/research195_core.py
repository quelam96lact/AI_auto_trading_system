"""Core logic for Brief 195: Daily Trend (MA) + 1-Hour Entry (RSI) + Daily ATR Trailing Stop.

Pre-registered exploration library adhering to Brief 195 specifications:
- 1h resampling of 5m bars (§3.1)
- Daily trend SMA(n), ATR(14), and liquidity checking (§3.2)
- Entry signals and trade execution (§3.3)
- Trailing stop, trend loss, and data-end exits (§3.4)
- Trade-level statistics and equal-weighted benchmark comparison (§3.5)
- Step 4 Deflated Sharpe Ratio calculation with PRIOR_NEGATIVE_FAMILIES = 27 (§5)
"""

from __future__ import annotations

import bisect
import csv
import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, cast

import numpy as np
import scipy.stats

from scripts.research188_core import compute_stock_net_return, deflated_sharpe
from scripts.research191_data import StockDailyBar
from scripts.research191_exits import is_floor_locked, is_liquid
from trading.indicators import AtrCalculator
from trading.stock_study import bootstrap_by_month, is_ceiling_open
from trading.strategies.momentum_rsi import _RsiState

MIN_TURNOVER_195 = 1_000_000_000.0  # 1 tỷ VND
PRIOR_NEGATIVE_FAMILIES = 27
IDEA_ID = "I1_DMA_RSI1H_ATR"
VALID_HOURS = (9, 10, 11, 13, 14)


@dataclass(slots=True)
class Bar5m:
    symbol: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class Bar1h:
    symbol: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def date(self) -> date:
        return self.ts.date()


@dataclass(slots=True)
class Trade195:
    symbol: str
    entry_ts: datetime
    exit_ts: datetime
    entry_session: date
    exit_session: date
    entry_price: float
    exit_price: float
    net_return: float
    ew_return: float
    excess_return: float
    exit_reason: str  # "STOP", "TREND", "END"
    holding_bars: int
    holding_sessions: int


def compute_file_sha256(path: Path | str) -> str:
    """Compute sha256 hex digest of file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()


def load_bars_5m(data_dir: Path | str) -> dict[str, list[Bar5m]]:
    """Load 5m bars from bars_5m.csv.gz (or .csv), verifying sha256 against manifest.json.

    Raises:
        FileNotFoundError: If manifest.json or bars_5m file is missing.
        ValueError: If sha256 checksum does not match manifest.
    Returns:
        dict[symbol, list[Bar5m]] chronologically sorted.
    """
    d_dir = Path(data_dir)
    manifest_p = d_dir / "manifest.json"
    if not manifest_p.exists():
        raise FileNotFoundError(f"Missing manifest.json in {d_dir}")

    with open(manifest_p, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    gz_path = d_dir / "bars_5m.csv.gz"
    csv_path = d_dir / "bars_5m.csv"
    if gz_path.exists():
        filepath = gz_path
        filename = "bars_5m.csv.gz"
    elif csv_path.exists():
        filepath = csv_path
        filename = "bars_5m.csv"
    else:
        raise FileNotFoundError(f"bars_5m file not found in {d_dir}")

    # Extract expected sha
    files_entry = manifest.get("files", {})
    entry = files_entry.get(filename) or manifest.get(filename)
    if entry is None:
        alt = filename[:-3] if filename.endswith(".gz") else f"{filename}.gz"
        entry = files_entry.get(alt) or manifest.get(alt)
    if entry is None:
        raise ValueError(f"No checksum entry in manifest.json for {filename}")

    expected_sha = entry["sha256"] if isinstance(entry, dict) else str(entry)
    actual_sha = compute_file_sha256(filepath)
    if actual_sha.lower() != expected_sha.lower():
        raise ValueError(
            f"Checksum mismatch for {filename}: expected {expected_sha}, got {actual_sha}"
        )

    bars_by_symbol: dict[str, list[Bar5m]] = {}
    opener = gzip.open if filepath.name.endswith(".gz") else open
    with opener(filepath, "rt", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row["symbol"].strip()
            ts_str = row["ts"].strip()
            dt = datetime.fromisoformat(ts_str)
            bar = Bar5m(
                symbol=sym,
                ts=dt,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            bars_by_symbol.setdefault(sym, []).append(bar)

    for b_list in bars_by_symbol.values():
        b_list.sort(key=lambda b: b.ts)

    return bars_by_symbol


def resample_1h(bars_5m: list[Bar5m]) -> list[Bar1h]:
    """Resample 5m bars into 1h bars according to Brief 195 §3.1.

    Groups by (date, hour):
    - 09: 09:00 - 09:55
    - 10: 10:00 - 10:55
    - 11: 11:00 - 11:25
    - 13: 13:00 - 13:55
    - 14: 14:00 - 14:55, including ATC 14:45

    Bar values:
    - open: open of first 5m bar in group
    - close: close of last 5m bar in group
    - high: max high
    - low: min low
    - volume: sum of volume
    - ts: date at group start hour (e.g. 09:00:00)
    """
    if not bars_5m:
        return []

    # Map (date, hour) -> list[Bar5m] preserving order
    groups: dict[tuple[date, int], list[Bar5m]] = {}
    for b in bars_5m:
        h = b.ts.hour
        if h in VALID_HOURS:
            d = b.ts.date()
            groups.setdefault((d, h), []).append(b)

    bars_1h: list[Bar1h] = []
    for (d, h), g in sorted(groups.items()):
        g.sort(key=lambda x: x.ts)
        first_b = g[0]
        last_b = g[-1]
        bars_1h.append(
            Bar1h(
                symbol=first_b.symbol,
                ts=datetime.combine(d, time(h, 0)),
                open=first_b.open,
                high=max(x.high for x in g),
                low=min(x.low for x in g),
                close=last_b.close,
                volume=sum(x.volume for x in g),
            )
        )

    return bars_1h


def daily_trend_series(
    daily_bars: list[StockDailyBar],
    sessions: list[date],
    n: int,
) -> dict[date, bool]:
    """Calculate TREND_D(t) for each session in sessions (§3.2).

    Only daily bars with date < t are used.
    j: last daily bar before t.
    Requires at least n + 1 daily bars before t.
    Returns True if close[j] > SMA_n(j) AND SMA_n(j) > SMA_n(j - 1).
    """
    if len(daily_bars) < n + 1:
        return {s: False for s in sessions}

    bar_dates = [b.date for b in daily_bars]
    closes = [b.close for b in daily_bars]

    # Precalculate prefix sums for O(1) SMA
    prefix = [0.0] * (len(closes) + 1)
    for i, c in enumerate(closes):
        prefix[i + 1] = prefix[i] + c

    trend: dict[date, bool] = {}
    for s in sessions:
        j = bisect.bisect_left(bar_dates, s) - 1
        if j < n:  # need j + 1 >= n + 1, so j >= n
            trend[s] = False
            continue

        c_j = closes[j]
        # SMA_n(j): closes from j - n + 1 to j
        sma_j = (prefix[j + 1] - prefix[j + 1 - n]) / n
        # SMA_n(j - 1): closes from j - n to j - 1
        sma_j_prev = (prefix[j] - prefix[j - n]) / n

        trend[s] = (c_j > sma_j > sma_j_prev)

    return trend


def daily_atr_series(
    daily_bars: list[StockDailyBar],
    sessions: list[date],
    period: int = 14,
) -> dict[date, float | None]:
    """Calculate ATR_D(t) for each session in sessions (§3.2).

    Only daily bars with date < t are used.
    j: last daily bar before t.
    AtrCalculator(14) fed up to j. If < 14 bars, returns None.
    """
    if not daily_bars:
        return {s: None for s in sessions}

    calc = AtrCalculator(period=period)
    atr_values: list[float | None] = []
    bar_dates: list[date] = []

    for b in daily_bars:
        bar_dates.append(b.date)
        atr_values.append(calc.update(cast(Any, b)))

    atr_by_session: dict[date, float | None] = {}
    for s in sessions:
        j = bisect.bisect_left(bar_dates, s) - 1
        if j < 0 or j >= len(atr_values):
            atr_by_session[s] = None
        else:
            atr_by_session[s] = atr_values[j]

    return atr_by_session


def daily_liq_series(
    daily_bars: list[StockDailyBar],
    sessions: list[date],
    min_turnover: float = MIN_TURNOVER_195,
) -> dict[date, bool]:
    """Calculate LIQ(t) for each session in sessions (§3.2).

    Only daily bars with date < t are used.
    j: last daily bar before t.
    Requires at least 60 daily bars before t AND is_liquid(daily_bars, j, min_turnover).
    """
    if len(daily_bars) < 60:
        return {s: False for s in sessions}

    bar_dates = [b.date for b in daily_bars]
    liq: dict[date, bool] = {}

    for s in sessions:
        j = bisect.bisect_left(bar_dates, s) - 1
        if j + 1 < 60:
            liq[s] = False
        else:
            liq[s] = is_liquid(daily_bars, j, min_turnover=min_turnover)

    return liq


def simulate_trades(
    bars_1h_by_symbol: dict[str, list[Bar1h]],
    daily_bars_by_symbol: dict[str, list[StockDailyBar]],
    sessions: list[date],
    exchanges: dict[str, str],
    n: int,
    theta: float,
    k: float,
    explore_symbols: set[str] | list[str] | None = None,
) -> list[Trade195]:
    """Simulate trades for a single parameter configuration (n, theta, k) (§3.3 - §3.5).

    Every symbol is evaluated independently (no portfolio slot constraint).
    Calculates net return r_i, equal-weighted return EW_i, and excess return X_i.
    """
    symbols = sorted(bars_1h_by_symbol.keys())
    if explore_symbols is None:
        explore_set = set(symbols)
    else:
        explore_set = set(explore_symbols)

    sess_idx = {s: i for i, s in enumerate(sessions)}

    # Precalculate daily indicators and indexes for all symbols
    trend_by_sym: dict[str, dict[date, bool]] = {}
    atr_by_sym: dict[str, dict[date, float | None]] = {}
    liq_by_sym: dict[str, dict[date, bool]] = {}
    daily_close_by_sym: dict[str, dict[date, float]] = {}

    for s in symbols:
        d_bars = daily_bars_by_symbol.get(s, [])
        trend_by_sym[s] = daily_trend_series(d_bars, sessions, n=n)
        atr_by_sym[s] = daily_atr_series(d_bars, sessions, period=14)
        liq_by_sym[s] = daily_liq_series(d_bars, sessions, min_turnover=MIN_TURNOVER_195)
        daily_close_by_sym[s] = {b.date: b.close for b in d_bars}

    raw_trades: list[dict[str, Any]] = []

    for s in symbols:
        bars_1h = bars_1h_by_symbol.get(s, [])
        if len(bars_1h) < 30:
            continue

        trend_d = trend_by_sym[s]
        atr_d = atr_by_sym[s]
        liq_d = liq_by_sym[s]
        daily_closes = daily_close_by_sym[s]
        exch = exchanges.get(s)

        # Precompute RSI(14)
        rsi_state = _RsiState(14)
        rsi_vals: list[float | None] = [rsi_state.update(b.close) for b in bars_1h]

        # Map session -> last bar index of session in bars_1h
        last_bar_of_day: dict[date, int] = {}
        for idx, b in enumerate(bars_1h):
            last_bar_of_day[b.date] = idx

        in_trade = False
        pending_exit = False
        exit_reason: str | None = None
        entry_idx: int = -1
        entry_price: float = 0.0
        entry_ts: datetime = datetime(1970, 1, 1)
        entry_session: date = date(1970, 1, 1)
        H: float = 0.0

        for h in range(len(bars_1h)):
            b = bars_1h[h]
            t = b.date

            # --- Check pending exit execution at open of bar h ---
            if in_trade and pending_exit:
                idx_entry_sess = sess_idx.get(entry_session, -999)
                idx_h_sess = sess_idx.get(t, -999)

                # T+2 constraint: only sell from session entry_sess + 2 onwards,
                # and in entry_sess + 2, only from hour >= 13
                t2_ok = False
                if idx_h_sess >= idx_entry_sess + 2:
                    if idx_h_sess == idx_entry_sess + 2:
                        t2_ok = b.ts.hour >= 13
                    else:
                        t2_ok = True

                if t2_ok:
                    # Check floor locked
                    idx_prev = idx_h_sess - 1
                    ref_d = sessions[idx_prev] if 0 <= idx_prev < len(sessions) else None
                    ref_close = daily_closes.get(ref_d) if ref_d else None

                    is_locked = False
                    if ref_close is not None:
                        is_locked = is_floor_locked(ref_close, b.high, b.low, exch)

                    if not is_locked:
                        # Successfully execute exit at open of bar h
                        exit_price = b.open
                        exit_ts = b.ts
                        exit_session = t
                        holding_bars = h - entry_idx
                        idx_exit_sess = sess_idx.get(exit_session, idx_h_sess)
                        holding_sessions = idx_exit_sess - idx_entry_sess + 1

                        raw_trades.append(
                            {
                                "symbol": s,
                                "entry_ts": entry_ts,
                                "exit_ts": exit_ts,
                                "entry_session": entry_session,
                                "exit_session": exit_session,
                                "entry_price": entry_price,
                                "exit_price": exit_price,
                                "exit_reason": exit_reason or "STOP",
                                "holding_bars": holding_bars,
                                "holding_sessions": holding_sessions,
                            }
                        )

                        in_trade = False
                        pending_exit = False
                        exit_reason = None
                        # Note: symbol can re-enter from signal at close of this same bar h!

            # --- If in trade and not pending exit, evaluate exit conditions at close of bar h ---
            if in_trade and not pending_exit:
                H = max(H, b.close)

                # 1. Trailing stop check
                stop_triggered = False
                atr_val = atr_d.get(t)
                if atr_val is not None:
                    stop_level = H - k * atr_val
                    if b.close < stop_level:
                        stop_triggered = True

                # 2. Trend loss check at last bar of session
                trend_triggered = False
                if h == last_bar_of_day.get(t):
                    idx_t = sess_idx.get(t, -999)
                    if idx_t + 1 < len(sessions):
                        next_sess = sessions[idx_t + 1]
                        if not trend_d.get(next_sess, False):
                            trend_triggered = True

                if stop_triggered or trend_triggered:
                    pending_exit = True
                    # Priority: STOP takes precedence if both trigger
                    if stop_triggered:
                        exit_reason = "STOP"
                    else:
                        exit_reason = "TREND"

            # --- If not in trade (or just exited at open of bar h), evaluate entry at close of bar h ---
            if not in_trade and not pending_exit:
                # 1. TREND_D(t) is True
                cond1 = trend_d.get(t, False)

                # 2. RSI crosses above theta at bar h >= 29
                cond2 = False
                if h >= 29:
                    r_prev = rsi_vals[h - 1]
                    r_curr = rsi_vals[h]
                    if (
                        r_prev is not None
                        and r_curr is not None
                        and r_prev < theta
                        and r_curr >= theta
                    ):
                        cond2 = True

                # 3. LIQ(t) is True
                cond3 = liq_d.get(t, False)

                # 5. Has next 1h bar h + 1 and session continuity
                cond5 = False
                next_b: Bar1h | None = None
                if h + 1 < len(bars_1h):
                    next_b = bars_1h[h + 1]
                    if next_b.date == t:
                        cond5 = True
                    else:
                        # Must be strictly the next session in S
                        idx_t = sess_idx.get(t, -999)
                        if (
                            idx_t + 1 < len(sessions)
                            and next_b.date == sessions[idx_t + 1]
                        ):
                            cond5 = True

                # 6. Execution bar h + 1: not ceiling open and volume > 0
                cond6 = False
                if cond5 and next_b is not None:
                    idx_next_sess = sess_idx.get(next_b.date, -999)
                    idx_ref = idx_next_sess - 1
                    ref_sess = sessions[idx_ref] if 0 <= idx_ref < len(sessions) else None
                    ref_c = daily_closes.get(ref_sess) if ref_sess else None

                    if (
                        ref_c is not None
                        and next_b.volume > 0
                        and not is_ceiling_open(ref_c, next_b.open, exch)
                    ):
                        cond6 = True

                if cond1 and cond2 and cond3 and cond5 and cond6 and next_b is not None:
                    in_trade = True
                    pending_exit = False
                    exit_reason = None
                    entry_idx = h + 1
                    entry_price = next_b.open
                    entry_ts = next_b.ts
                    entry_session = next_b.date
                    H = entry_price

        # Close any open trade at end of data
        if in_trade:
            last_b = bars_1h[-1]
            exit_price = last_b.close
            exit_ts = last_b.ts
            exit_session = last_b.date
            holding_bars = len(bars_1h) - entry_idx
            idx_entry_sess = sess_idx.get(entry_session, 0)
            idx_exit_sess = sess_idx.get(exit_session, len(sessions) - 1)
            holding_sessions = idx_exit_sess - idx_entry_sess + 1

            raw_trades.append(
                {
                    "symbol": s,
                    "entry_ts": entry_ts,
                    "exit_ts": exit_ts,
                    "entry_session": entry_session,
                    "exit_session": exit_session,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "exit_reason": "END",
                    "holding_bars": holding_bars,
                    "holding_sessions": holding_sessions,
                }
            )

    # Pre-index 1h bars by symbol for fast EW lookup: ts_list and open_list / close_list
    sym_1h_ts: dict[str, list[datetime]] = {}
    sym_1h_bars: dict[str, list[Bar1h]] = {}
    for s in symbols:
        b_list = bars_1h_by_symbol.get(s, [])
        sym_1h_bars[s] = b_list
        sym_1h_ts[s] = [b.ts for b in b_list]

    # Pre-calculate prices P_s(tau) helper
    def get_price(s: str, tau: datetime, is_end: bool) -> float | None:
        b_list = sym_1h_bars.get(s)
        if not b_list:
            return None
        if is_end:
            return b_list[-1].close
        ts_list = sym_1h_ts[s]
        idx = bisect.bisect_left(ts_list, tau)
        if idx < len(ts_list) and ts_list[idx] == tau:
            return b_list[idx].open
        if idx > 0:
            return b_list[idx - 1].close
        return None

    # Calculate net_return, ew_return, excess_return for each trade
    trades: list[Trade195] = []
    for rt in raw_trades:
        e_price = rt["entry_price"]
        x_price = rt["exit_price"]
        tau_buy = rt["entry_ts"]
        tau_sell = rt["exit_ts"]
        e_sess = rt["entry_session"]
        is_end = rt["exit_reason"] == "END"

        r_net = compute_stock_net_return(e_price, x_price)

        # EW Universe U_i: explore symbols with LIQ(entry_session) is True
        ew_returns: list[float] = []
        for sym_cand in explore_set:
            if not liq_by_sym.get(sym_cand, {}).get(e_sess, False):
                continue
            p_buy = get_price(sym_cand, tau_buy, is_end=False)
            if p_buy is None or p_buy <= 0:
                continue
            p_sell = get_price(sym_cand, tau_sell, is_end=is_end)
            if p_sell is None or p_sell <= 0:
                continue
            ew_returns.append(p_sell / p_buy - 1.0)

        ew_ret = float(np.mean(ew_returns)) if ew_returns else 0.0
        excess = r_net - ew_ret

        trades.append(
            Trade195(
                symbol=rt["symbol"],
                entry_ts=tau_buy,
                exit_ts=tau_sell,
                entry_session=e_sess,
                exit_session=rt["exit_session"],
                entry_price=e_price,
                exit_price=x_price,
                net_return=r_net,
                ew_return=ew_ret,
                excess_return=excess,
                exit_reason=rt["exit_reason"],
                holding_bars=rt["holding_bars"],
                holding_sessions=rt["holding_sessions"],
            )
        )

    trades.sort(key=lambda tr: (tr.entry_ts, tr.symbol))
    return trades


def compute_configuration_metrics(
    trades: list[Trade195],
    seed: int = 195,
) -> dict[str, Any]:
    """Compute all evaluation metrics for a configuration (§3.5)."""
    n = len(trades)
    if n == 0:
        return {
            "n": 0,
            "mean_X": 0.0,
            "sd_X": 0.0,
            "sharpe_X": 0.0,
            "p": 1.0,
            "mean_r": 0.0,
            "win_rate": 0.0,
            "median_holding_bars": 0.0,
            "median_holding_sessions": 0.0,
            "stop_count": 0,
            "trend_count": 0,
            "end_count": 0,
            "mean_EW": 0.0,
            "by_week": {},
            "weekly_means": [],
            "sharpe_w": 0.0,
            "n_weeks": 0,
            "skew_w": 0.0,
            "kurt_w": 3.0,
        }

    x_vals = [t.excess_return for t in trades]
    r_vals = [t.net_return for t in trades]
    ew_vals = [t.ew_return for t in trades]

    mean_x = float(np.mean(x_vals))
    sd_x = float(np.std(x_vals, ddof=1)) if n > 1 else 0.0
    sharpe_x = mean_x / sd_x if sd_x > 0 else 0.0

    mean_r = float(np.mean(r_vals))
    win_rate = float(np.mean([1.0 if r > 0 else 0.0 for r in r_list])) if (r_list := r_vals) else 0.0
    med_bars = float(np.median([t.holding_bars for t in trades]))
    med_sess = float(np.median([t.holding_sessions for t in trades]))

    stop_cnt = sum(1 for t in trades if t.exit_reason == "STOP")
    trend_cnt = sum(1 for t in trades if t.exit_reason == "TREND")
    end_cnt = sum(1 for t in trades if t.exit_reason == "END")
    mean_ew = float(np.mean(ew_vals))

    # Weekly grouping for bootstrap and DSR
    by_week: dict[tuple[int, int], list[float]] = {}
    for t in trades:
        iso_cal = t.entry_session.isocalendar()
        key = (iso_cal.year, iso_cal.week)
        by_week.setdefault(key, []).append(t.excess_return)

    boot = bootstrap_by_month(
        by_week,
        n=10000,
        seed=seed,
        ci_low_pct=2.5,
        ci_high_pct=97.5,
    )
    p_val = float(boot["p"]) if boot["p"] is not None else 1.0

    # Weekly series for Step 4
    weekly_means = [float(np.mean(vals)) for _, vals in sorted(by_week.items())]
    n_weeks = len(weekly_means)
    if n_weeks > 1:
        mean_w = float(np.mean(weekly_means))
        sd_w = float(np.std(weekly_means, ddof=1))
        sharpe_w = mean_w / sd_w if sd_w > 0 else 0.0
        skew_w = float(scipy.stats.skew(weekly_means, bias=True))
        kurt_w = float(scipy.stats.kurtosis(weekly_means, fisher=False, bias=True))
    else:
        sharpe_w = 0.0
        skew_w = 0.0
        kurt_w = 3.0

    return {
        "n": n,
        "mean_X": mean_x,
        "sd_X": sd_x,
        "sharpe_X": sharpe_x,
        "p": p_val,
        "mean_r": mean_r,
        "win_rate": win_rate,
        "median_holding_bars": med_bars,
        "median_holding_sessions": med_sess,
        "stop_count": stop_cnt,
        "trend_count": trend_cnt,
        "end_count": end_cnt,
        "mean_EW": mean_ew,
        "by_week": by_week,
        "weekly_means": weekly_means,
        "sharpe_w": sharpe_w,
        "n_weeks": n_weeks,
        "skew_w": skew_w,
        "kurt_w": kurt_w,
    }


def compute_step4_dsr(
    sharpe_w: float,
    n_weeks: int,
    skew: float,
    kurt: float,
    week_sharpes: list[float],
) -> float:
    """Compute Step 4 Deflated Sharpe Ratio (§5).

    Calls deflated_sharpe(sr, n_obs, skew, kurt, n_trials=len(week_sharpes) + 27, sr_trials_var=var(week_sharpes, ddof=1)).
    PRIOR_NEGATIVE_FAMILIES = 27.
    """
    n_trials = len(week_sharpes) + PRIOR_NEGATIVE_FAMILIES
    sr_trials_var = (
        float(np.var(week_sharpes, ddof=1)) if len(week_sharpes) > 1 else 0.0
    )
    return deflated_sharpe(
        sr=sharpe_w,
        n_obs=n_weeks,
        skew=skew,
        kurt=kurt,
        n_trials=n_trials,
        sr_trials_var=sr_trials_var,
    )
