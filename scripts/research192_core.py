"""Core logic for Brief 192 (Calendar effects: Turn of the Month and Pre-Holiday).

Defines:
- load_sessions: loads sessions.csv with sha256 check against manifest.json.
- get_tom_windows: generates (b, e) windows for Turn Of the Month (I1).
- get_prehol_windows: generates (b, e) windows for Pre-Holiday (I2).
- generate_calendar_trades: simulates trades under §3.3 rules.
- time_baseline_excess: computes excess returns vs time baseline (§3.4).
"""

from __future__ import annotations

import csv
import gzip
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np

from scripts.research188_core import (
    Trade,
    compute_stock_net_return,
)
from scripts.research191_data import (
    StockDailyBar,
    compute_file_sha256,
)
from scripts.research191_exits import (
    DEFAULT_MIN_TURNOVER,
    is_liquid,
)
from trading.stock_study import limit_rate


def load_sessions(
    data_dir: Path | str,
    end: date | str | None = None,
) -> list[date]:
    """Load market trading sessions from sessions.csv, verifying sha256 with manifest.json."""
    d_dir = Path(data_dir)
    manifest_p = d_dir / "manifest.json"
    if not manifest_p.exists():
        raise FileNotFoundError(f"Missing manifest.json in {d_dir}")

    with open(manifest_p, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    sess_file = d_dir / "sessions.csv"
    if not sess_file.exists():
        sess_file = d_dir / "sessions.csv.gz"
    if not sess_file.exists():
        raise FileNotFoundError(f"Missing sessions.csv in {d_dir}")

    files_entry = manifest.get("files", {})
    expected_sha = None
    if sess_file.name in files_entry:
        expected_sha = files_entry[sess_file.name].get("sha256")
    elif "sessions.csv" in files_entry:
        expected_sha = files_entry["sessions.csv"].get("sha256")

    if not expected_sha:
        raise ValueError(f"No sha256 checksum found in manifest.json for {sess_file.name}")

    actual_sha = compute_file_sha256(sess_file)
    if actual_sha != expected_sha:
        raise ValueError(
            f"Checksum mismatch for {sess_file.name}: expected {expected_sha}, got {actual_sha}"
        )

    end_d = end if isinstance(end, date) else (date.fromisoformat(str(end)) if end else None)

    sessions: list[date] = []
    is_gz = sess_file.name.endswith(".gz")
    open_fn = gzip.open if is_gz else open

    with open_fn(sess_file, "rt", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_d = date.fromisoformat(row["date"].strip())
            if end_d and row_d > end_d:
                raise ValueError(f"Session date {row_d} exceeds end limit {end_d}")
            sessions.append(row_d)

    sessions.sort()
    return sessions


def get_tom_windows(
    sessions: list[date],
    k: int,
    m: int,
) -> list[tuple[date, date, str]]:
    """Generate (b, e, event_id) windows for I1 TOM (Turn Of the Month) (§3.2).

    - L(M): last session in S belonging to month M.
    - Buy session b: session k counting backwards from L(M) (k=1 is L(M)).
    - Sell session e: session m of month M+1 (m=1 is 1st session of M+1).
    - Grid: k in {1, 2, 3}, m in {2, 3, 4}.
    - Enforces T+2 constraint (index of e - index of b >= 2).
    """
    if not sessions:
        return []

    sess_idx_map = {d: i for i, d in enumerate(sessions)}
    sessions_by_ym: dict[tuple[int, int], list[date]] = {}
    for s in sessions:
        sessions_by_ym.setdefault((s.year, s.month), []).append(s)

    sorted_ym = sorted(sessions_by_ym.keys())
    windows: list[tuple[date, date, str]] = []

    for idx, (year, month) in enumerate(sorted_ym):
        if idx + 1 >= len(sorted_ym):
            # No next month in sessions
            continue
        next_ym = sorted_ym[idx + 1]
        # Check consecutive calendar months
        expected_next_year = year + (month // 12)
        expected_next_month = (month % 12) + 1
        if next_ym != (expected_next_year, expected_next_month):
            continue

        month_sessions = sessions_by_ym[(year, month)]
        next_month_sessions = sessions_by_ym[next_ym]

        # L(M) is the last session in S belonging to month M
        lm_session = month_sessions[-1]
        lm_idx = sess_idx_map[lm_session]

        # Session k counting backwards from L(M)
        b_idx = lm_idx - (k - 1)
        if b_idx < 0:
            continue
        b = sessions[b_idx]

        # Session m of month M+1 (1-indexed: m=1 is index 0)
        if len(next_month_sessions) < m:
            continue
        e = next_month_sessions[m - 1]
        e_idx = sess_idx_map[e]

        assert e_idx - b_idx >= 2, f"T+2 violated for TOM: b={b} (idx {b_idx}), e={e} (idx {e_idx})"

        event_id = f"TOM_{year}_{month:02d}_k{k}_m{m}"
        windows.append((b, e, event_id))

    return windows


def get_prehol_windows(
    sessions: list[date],
    n: int,
    q: int,
) -> list[tuple[date, date, str]]:
    """Generate (b, e, event_id) windows for I2 PREHOL (Pre-Holiday) (§3.2).

    - Between consecutive sessions h and a in S, there is at least one Mon-Fri
      day that is NOT a session. Then h is session before holiday, a is first session after.
      Normal weekends (Sat-Sun only) are NOT holidays.
    - Buy session b: session n counting backwards from h (n=1 is h).
    - Sell session e: session q counting forwards from a (q=1 is a).
    - Grid: n in {2, 3, 4}, q in {1, 2, 3}.
    - Enforces T+2 constraint (index of e - index of b >= 2).
    """
    if len(sessions) < 2:
        return []

    windows: list[tuple[date, date, str]] = []

    for i in range(len(sessions) - 1):
        h = sessions[i]
        a = sessions[i + 1]

        # Check if there is at least one Monday-Friday day between h and a
        curr = h + timedelta(days=1)
        has_weekday_gap = False
        while curr < a:
            if curr.weekday() < 5:  # 0=Mon, ..., 4=Fri
                has_weekday_gap = True
                break
            curr += timedelta(days=1)

        if not has_weekday_gap:
            continue

        h_idx = i
        a_idx = i + 1

        b_idx = h_idx - (n - 1)
        if b_idx < 0:
            continue
        b = sessions[b_idx]

        e_idx = a_idx + (q - 1)
        if e_idx >= len(sessions):
            continue
        e = sessions[e_idx]

        assert e_idx - b_idx >= 2, f"T+2 violated for PREHOL: b={b} (idx {b_idx}), e={e} (idx {e_idx})"

        event_id = f"PREHOL_{h}_{a}_n{n}_q{q}"
        windows.append((b, e, event_id))

    return windows


def generate_calendar_trades(
    windows: list[tuple[date, date, str]],
    bars_by_symbol: dict[str, list[StockDailyBar]],
    sessions: list[date],
    exchanges: dict[str, str],
    period_start: date | None = None,
    period_end: date | None = None,
    max_symbols: int = 10,
    min_turnover: float = DEFAULT_MIN_TURNOVER,
) -> list[Trade]:
    """Generate calendar trades under §3.3 rules.

    - Universe at b: symbols with bar on session before b (b_prev) and 20-session
      average turnover up to b_prev >= min_turnover (is_liquid).
    - Select max 10 symbols with highest GTGD20 (ties broken by symbol A->Z).
    - Buy at close of session b (drop if missing bar or ceiling locked).
    - Sell at close of session e (roll to next available non-floor session if missing or floor-locked).
    - Overlapping check: if symbol has open trade from earlier window, skip it.
    - No stop loss or take profit.
    """
    if not windows or not sessions:
        return []

    sess_idx_map = {d: i for i, d in enumerate(sessions)}

    # Index bars by symbol and date
    sym_date_bar: dict[str, dict[date, StockDailyBar]] = {}
    sym_date_idx: dict[str, dict[date, int]] = {}
    for sym, b_list in bars_by_symbol.items():
        sym_date_bar[sym] = {}
        sym_date_idx[sym] = {}
        for idx, bar in enumerate(b_list):
            sym_date_bar[sym][bar.date] = bar
            sym_date_idx[sym][bar.date] = idx

    # Filter windows by buy date b in [period_start, period_end]
    filtered_windows = []
    for b, e, wid in windows:
        if period_start and b < period_start:
            continue
        if period_end and b > period_end:
            continue
        filtered_windows.append((b, e, wid))

    # Sort chronologically by buy date b
    filtered_windows.sort(key=lambda w: (w[0], w[1]))

    trades: list[Trade] = []
    last_exit_date: dict[str, date] = {}

    for b, e, _wid in filtered_windows:
        b_idx = sess_idx_map.get(b)
        e_idx = sess_idx_map.get(e)
        if b_idx is None or e_idx is None:
            continue
        assert e_idx - b_idx >= 2, f"T+2 violated: b={b}, e={e}"

        if b_idx < 1:
            # No session before b in S
            continue
        b_prev = sessions[b_idx - 1]

        # 1. Universe selection at b (using data strictly up to b_prev)
        candidate_scores: list[tuple[float, str]] = []
        for sym, b_list in bars_by_symbol.items():
            # Check overlap in same idea
            if sym in last_exit_date and b <= last_exit_date[sym]:
                continue

            b_prev_idx = sym_date_idx.get(sym, {}).get(b_prev)
            if b_prev_idx is None:
                continue

            # Liquidity check up to b_prev
            if not is_liquid(b_list, b_prev_idx, min_turnover=min_turnover):
                continue

            # Average 20-session turnover up to b_prev
            gtgd20 = sum(
                b_list[i].close * b_list[i].volume for i in range(b_prev_idx - 19, b_prev_idx + 1)
            ) / 20.0
            candidate_scores.append((gtgd20, sym))

        if not candidate_scores:
            continue

        # Sort: highest GTGD20 first, symbol A->Z on tie
        candidate_scores.sort(key=lambda item: (-item[0], item[1]))
        selected = candidate_scores[:max_symbols]

        # 2. Execution for selected symbols
        for gtgd20, sym in selected:
            b_bar = sym_date_bar.get(sym, {}).get(b)
            if b_bar is None:
                continue

            b_bar_idx = sym_date_idx[sym][b]
            if b_bar_idx < 1:
                continue
            prev_b_bar = bars_by_symbol[sym][b_bar_idx - 1]

            exch = exchanges.get(sym, "HOSE")
            l_rate = limit_rate(exch)

            # Check ceiling lock on session b
            is_ceiling = (b_bar.high == b_bar.low) and (
                b_bar.close >= prev_b_bar.close * (1.0 + l_rate - 0.001)
            )
            if is_ceiling:
                continue

            entry_price = float(b_bar.close)

            # 3. Sell execution starting from session e
            exit_price: float | None = None
            exit_date: date | None = None

            for j_idx in range(e_idx, len(sessions)):
                sess_j = sessions[j_idx]
                curr_bar = sym_date_bar.get(sym, {}).get(sess_j)
                if curr_bar is None:
                    continue

                curr_bar_idx = sym_date_idx[sym][sess_j]
                if curr_bar_idx < 1:
                    continue
                prev_curr_bar = bars_by_symbol[sym][curr_bar_idx - 1]
                curr_l_rate = limit_rate(exch)

                is_floor = (curr_bar.high == curr_bar.low) and (
                    curr_bar.close <= prev_curr_bar.close * (1.0 - curr_l_rate + 0.001)
                )
                if is_floor:
                    continue

                # Non-floor bar found
                exit_price = float(curr_bar.close)
                exit_date = curr_bar.date
                break

            if exit_price is None or exit_date is None:
                # End of data: close at last available bar of symbol
                last_bar = bars_by_symbol[sym][-1]
                exit_price = float(last_bar.close)
                exit_date = last_bar.date

            gross_return = (exit_price / entry_price) - 1.0
            net_return = compute_stock_net_return(entry_price, exit_price)

            exit_sess_idx = sess_idx_map.get(exit_date, len(sessions) - 1)
            holding_sessions = max(1, exit_sess_idx - b_idx)

            trade = Trade(
                symbol=sym,
                entry_ts=datetime.combine(b, datetime.min.time(), tzinfo=UTC),
                exit_ts=datetime.combine(exit_date, datetime.min.time(), tzinfo=UTC),
                entry_price=entry_price,
                exit_price=exit_price,
                net_return=net_return,
                gross_return=gross_return,
                market="stock",
                side="long",
                score=gtgd20,
                holding_sessions=holding_sessions,
            )
            trades.append(trade)
            last_exit_date[sym] = exit_date

    return trades


def time_baseline_excess(
    trades: list[Trade],
    bars_by_symbol: dict[str, list[StockDailyBar]],
    sessions: list[date],
    period_start: date,
    period_end: date,
    min_turnover: float = DEFAULT_MIN_TURNOVER,
) -> dict[str, float]:
    """Calculate excess return of trades vs time baseline for the same symbols (§3.4).

    For each trade on symbol s holding h sessions in S (from actual b to actual e):
    - Baseline is average of (close[j+h] / close[j] - 1.0)
    - j runs through all sessions in S within [period_start, period_end] such that:
      - s has a bar on both j and j+h
      - s meets is_liquid on the session before j
    - excess = net_return - baseline (trade net vs baseline gross)
    - Returns mean_excess and mean_excess_trim1pct.
    """
    if not trades or not sessions:
        return {"mean_excess": 0.0, "mean_excess_trim1pct": 0.0}

    sess_idx_map = {d: i for i, d in enumerate(sessions)}

    # Index bars by symbol and date
    sym_date_bar: dict[str, dict[date, StockDailyBar]] = {}
    sym_date_idx: dict[str, dict[date, int]] = {}
    for sym, b_list in bars_by_symbol.items():
        sym_date_bar[sym] = {}
        sym_date_idx[sym] = {}
        for idx, bar in enumerate(b_list):
            sym_date_bar[sym][bar.date] = bar
            sym_date_idx[sym][bar.date] = idx

    # Cache baseline mean returns for (symbol, h)
    baseline_cache: dict[tuple[str, int], float] = {}

    excess_returns: list[float] = []

    for t in trades:
        entry_d = t.entry_ts.date()
        exit_d = t.exit_ts.date()
        b_idx = sess_idx_map.get(entry_d)
        e_idx = sess_idx_map.get(exit_d)
        if b_idx is None or e_idx is None:
            continue
        h = max(1, e_idx - b_idx)
        sym = t.symbol

        cache_key = (sym, h)
        if cache_key not in baseline_cache:
            j_returns: list[float] = []
            b_list = bars_by_symbol.get(sym, [])

            for j_idx, j_sess in enumerate(sessions):
                if j_sess < period_start or j_sess > period_end:
                    continue
                if j_idx + h >= len(sessions):
                    continue
                if j_idx < 1:
                    continue

                j_prev_sess = sessions[j_idx - 1]
                j_prev_idx = sym_date_idx.get(sym, {}).get(j_prev_sess)
                if j_prev_idx is None:
                    continue

                # Check liquidity on session before j
                if not is_liquid(b_list, j_prev_idx, min_turnover=min_turnover):
                    continue

                j_bar = sym_date_bar.get(sym, {}).get(j_sess)
                jh_sess = sessions[j_idx + h]
                jh_bar = sym_date_bar.get(sym, {}).get(jh_sess)

                if j_bar is None or jh_bar is None or j_bar.close <= 0:
                    continue

                ret = (jh_bar.close / j_bar.close) - 1.0
                j_returns.append(float(ret))

            baseline_cache[cache_key] = float(np.mean(j_returns)) if j_returns else 0.0

        sym_baseline = baseline_cache[cache_key]
        excess_returns.append(t.net_return - sym_baseline)

    if not excess_returns:
        return {"mean_excess": 0.0, "mean_excess_trim1pct": 0.0}

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
