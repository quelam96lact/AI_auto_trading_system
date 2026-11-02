"""Unit tests and mutation tests for Brief 195 core infrastructure (§4).

Includes:
- Hand-calculated test for simulate_trades covering STOP, TREND, END, T+2 hour 13 delay, and floor-lock postponement (§4).
- Test for resample_1h covering all 5 groups and boundaries (§3.1).
- Test for TREND_D transition and current session isolation (§3.2).
- Test for load_bars_5m checksum and ordering (§1).
- 28 mutation tests (a1 - n) calling the exact product functions in Brief 195 Table 4.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pytest

from scripts.research188_core import deflated_sharpe
from scripts.research191_data import StockDailyBar
from scripts.research195_core import (
    Bar1h,
    Bar5m,
    Trade195,
    compute_configuration_metrics,
    compute_step4_dsr,
    daily_trend_series,
    load_bars_5m,
    resample_1h,
    simulate_trades,
)
from scripts.research195_explore import run_exploration
from trading.stock_study import bootstrap_by_month

# -----------------------------------------------------------------------------
# Helpers to generate synthetic datasets for unit and mutation tests
# -----------------------------------------------------------------------------

def _make_sessions(n_sessions: int = 70, start_date: date = date(2026, 1, 5)) -> list[date]:
    """Generate n_sessions of weekday trading dates."""
    sessions: list[date] = []
    curr = start_date
    while len(sessions) < n_sessions:
        if curr.weekday() < 5:
            sessions.append(curr)
        curr += timedelta(days=1)
    return sessions


def _make_daily_bars(
    sym: str,
    sessions: list[date],
    base_price: float = 20_000.0,
    volume: float = 100_000.0,
    price_map: dict[date, float] | None = None,
    trending: bool = True,
) -> list[StockDailyBar]:
    """Generate daily bars for a symbol with turnover >= 1e9 VND (100k shares @ 20k = 2B).

    If trending is True, default price gently rises (+10 VND/day) so TREND_D is naturally satisfied.
    """
    bars = []
    for i, s in enumerate(sessions):
        default_p = base_price + (i * 10.0 if trending else 0.0)
        p = price_map.get(s, default_p) if price_map else default_p
        bars.append(
            StockDailyBar(
                symbol=sym,
                date=s,
                open=p,
                high=p + 250.0,
                low=p - 250.0,
                close=p,
                volume=volume,
            )
        )
    return bars


def _make_1h_bar(
    sym: str,
    d: date,
    hour: int,
    open_: float,
    close_: float,
    high: float | None = None,
    low: float | None = None,
    volume: float = 10_000.0,
) -> Bar1h:
    h_val = max(open_, close_) if high is None else high
    l_val = min(open_, close_) if low is None else low
    return Bar1h(
        symbol=sym,
        ts=datetime.combine(d, time(hour, 0)),
        open=open_,
        high=h_val,
        low=l_val,
        close=close_,
        volume=volume,
    )


# -----------------------------------------------------------------------------
# 1. Hand-calculated test for simulate_trades (§4)
# -----------------------------------------------------------------------------

def test_hand_calculated_simulation_with_stop_trend_end_t2_floor():
    """Hand-calculated simulation test (§4) on 3 synthetic symbols: SYM1, SYM2, SYM3.

    Setup:
    - 70 sessions: sessions[0..69].
    - Sessions 0..59 provide 60 daily bars (warm up for LIQ and TREND_D).
    - In sessions 57..62, daily closes form an ongoing uptrend (20000 + i*50).
      For n=2: SMA_2(j) > SMA_2(j-1) and close[j] > SMA_2(j).
      Therefore, TREND_D is True across sessions 60, 61, 62.
    - Bars 0..27 (28 bars): close = 20000.
    - Bar 28 (session 60, hour 09): close = 18000 -> RSI(14) drops to 0.0 (< 30).
    - Bar 29 (session 60, hour 10): close = 21000 -> RSI(14) crosses up to 61.76 (>= 30).
      Bar 29 is the 30th bar (h=29 >= 29). Condition 2 triggers!
    - At close of bar 29, buy signal fires for all 3 symbols!
    - Next bar 30 (session 60, hour 11): all 3 symbols entered at open = 20000.0 (entry session = session 60).
      Entry price E = 20000.0.

    Cost factors (trading/paper_broker.py: FEE_RATE = 0.0028, SELL_TAX_RATE = 0.001, SLIPPAGE_BPS = 5.0):
      cost_in  = 1.0 + 0.0028 + 0.0005 = 1.0033
      cost_out = 1.0 - 0.0028 - 0.0010 - 0.0005 = 0.9957
      cost_factor = cost_out / cost_in = 0.9957 / 1.0033 = 0.9924249975082228

    Trade 1 (SYM1) - STOP exit + T+2 hour 13 rule:
    - Buy session e = session 60. T+2 is session 62, permitted from hour >= 13.
    - At session 62, hour 10: close drops to 18500.0.
      Trailing stop with k=2: H = 20000.0, ATR_D = 500.0 -> Stop = 20000 - 2*500 = 19000.0.
      18500 < 19000 -> STOP exit triggers at hour 10 of session 62 (before T+2 permission!).
    - T+2 rule: signal arrives early, sell order queued until first permitted bar: session 62, hour 13!
    - At session 62, hour 13: open is 18000.0, high is 18200.0 (not floor locked). Exit executes!
    - Net return r_1:
      r_1 = (18000 * 0.9957) / (20000 * 1.0033) - 1
          = 0.9 * 0.9924249975082228 - 1
          = -0.10681750224259912
    - EW return EW_1:
      At tau_buy (session 60, 11:00): SYM1=20000, SYM2=20000, SYM3=20000.
      At tau_sell (session 62, 13:00): SYM1=18000, SYM2=20500, SYM3=21000.
      Returns: SYM1: -10%, SYM2: +2.5%, SYM3: +5.0%.
      EW_1 = (-0.10 + 0.025 + 0.05) / 3 = -0.025 / 3 = -0.00833333333333334.
    - Excess return X_1:
      X_1 = r_1 - EW_1 = -0.10681750224259912 - (-0.00833333333333334) = -0.09848416890926577.

    Trade 2 (SYM2) - TREND exit + Floor-lock postponement:
    - In session 63, daily close plunges to 15000, causing TREND_D(session 64) to be False.
      At close of session 63 hour 14 (last 1h bar of session 63), TREND exit triggers!
    - Next bar: session 64, hour 09.
      Previous daily close was 15000. HOSE floor = 15000 * 0.93 = 13950.
      At hour 09, high = low = open = 13950 -> is_floor_locked returns True!
      Exit cannot execute at hour 09 and is postponed to next bar!
    - Next bar: session 64, hour 10:
      Open = 19000, high = 19100, low = 18900 (not locked). Exit executes at open = 19000.0!
    - Net return r_2:
      r_2 = (19000 * 0.9957) / (20000 * 1.0033) - 1
          = 0.95 * 0.9924249975082228 - 1
          = -0.05719625236718817
    - EW return EW_2:
      At tau_buy: SYM1=20000, SYM2=20000, SYM3=20000.
      At tau_sell (session 64, 10:00): SYM1=18000, SYM2=19000, SYM3=21500.
      Returns: SYM1: -10%, SYM2: -5%, SYM3: +7.5%.
      EW_2 = (-0.10 + -0.05 + 0.075) / 3 = -0.075 / 3 = -0.025000000000000022.
    - Excess return X_2:
      X_2 = r_2 - EW_2 = -0.05719625236718817 - (-0.025000000000000022) = -0.03219625236718815.

    Trade 3 (SYM3) - END exit (end of data):
    - Stays open until close of final 1h bar of session 69.
    - Closes at close of final bar = 22000.0.
    - Net return r_3:
      r_3 = (22000 * 0.9957) / (20000 * 1.0033) - 1
          = 1.1 * 0.9924249975082228 - 1
          = 0.09166749725904544
    - EW return EW_3:
      At final bar close: SYM1=18000, SYM2=19000, SYM3=22000.
      Returns: SYM1: -10%, SYM2: -5%, SYM3: +10%.
      EW_3 = (-0.10 + -0.05 + 0.10) / 3 = -0.05 / 3 = -0.016666666666666646.
    - Excess return X_3:
      X_3 = r_3 - EW_3 = 0.09166749725904544 - (-0.016666666666666646) = 0.10833416392571209.
    """
    sessions = _make_sessions(70)
    exchanges = {"SYM1": "HOSE", "SYM2": "HOSE", "SYM3": "HOSE"}

    def make_daily(sym: str, crash_d63: bool = False) -> list[StockDailyBar]:
        bars = []
        for i, s in enumerate(sessions):
            p = 20000.0 + i * 50.0
            if crash_d63 and i >= 63:
                p = 15000.0
            b = _make_daily_bars(sym, [s], base_price=p, trending=False)[0]
            b.high = p + 250.0
            b.low = p - 250.0
            bars.append(b)
        return bars

    daily_bars = {
        "SYM1": make_daily("SYM1"),
        "SYM2": make_daily("SYM2", crash_d63=True),
        "SYM3": make_daily("SYM3"),
    }

    # Construct 1h bars
    extra_1 = [_make_1h_bar("SYM1", sessions[54], h, 20000.0, 20000.0) for h in (11, 13, 14)]
    bars_1h_1 = extra_1 + [_make_1h_bar("SYM1", sessions[s_idx], h, 20000.0, 20000.0) for s_idx in range(55, 60) for h in (9, 10, 11, 13, 14)]
    extra_2 = [_make_1h_bar("SYM2", sessions[54], h, 20000.0, 20000.0) for h in (11, 13, 14)]
    bars_1h_2 = extra_2 + [_make_1h_bar("SYM2", sessions[s_idx], h, 20000.0, 20000.0) for s_idx in range(55, 60) for h in (9, 10, 11, 13, 14)]
    extra_3 = [_make_1h_bar("SYM3", sessions[54], h, 20000.0, 20000.0) for h in (11, 13, 14)]
    bars_1h_3 = extra_3 + [_make_1h_bar("SYM3", sessions[s_idx], h, 20000.0, 20000.0) for s_idx in range(55, 60) for h in (9, 10, 11, 13, 14)]

    # Session 60:
    s60 = sessions[60]
    for b_list, sym in [(bars_1h_1, "SYM1"), (bars_1h_2, "SYM2"), (bars_1h_3, "SYM3")]:
        b_list.append(_make_1h_bar(sym, s60, 9, 20000.0, 18000.0))   # bar 28: dip
        b_list.append(_make_1h_bar(sym, s60, 10, 18000.0, 21000.0))  # bar 29: cross up
        b_list.append(_make_1h_bar(sym, s60, 11, 20000.0, 20000.0))  # bar 30: entry
        b_list.append(_make_1h_bar(sym, s60, 13, 20000.0, 20000.0))
        b_list.append(_make_1h_bar(sym, s60, 14, 20000.0, 20000.0))

    # Session 61: hold
    s61 = sessions[61]
    for b_list, sym in [(bars_1h_1, "SYM1"), (bars_1h_2, "SYM2"), (bars_1h_3, "SYM3")]:
        for h in (9, 10, 11, 13, 14):
            b_list.append(_make_1h_bar(sym, s61, h, 20000.0, 20000.0))

    # Session 62: SYM1 STOP triggers at hour 10, exits at hour 13
    s62 = sessions[62]
    bars_1h_1.append(_make_1h_bar("SYM1", s62, 9, 20000.0, 20000.0))
    bars_1h_1.append(_make_1h_bar("SYM1", s62, 10, 20000.0, 18500.0))  # STOP signal
    bars_1h_1.append(_make_1h_bar("SYM1", s62, 11, 18500.0, 18500.0))  # waiting for hour 13
    bars_1h_1.append(_make_1h_bar("SYM1", s62, 13, 18000.0, 18000.0, high=18200.0, low=18000.0))  # execute exit
    bars_1h_1.append(_make_1h_bar("SYM1", s62, 14, 18000.0, 18000.0))

    for h in (9, 10, 11):
        bars_1h_2.append(_make_1h_bar("SYM2", s62, h, 20000.0, 20500.0))
        bars_1h_3.append(_make_1h_bar("SYM3", s62, h, 20000.0, 21000.0))
    bars_1h_2.append(_make_1h_bar("SYM2", s62, 13, 20500.0, 20500.0))
    bars_1h_3.append(_make_1h_bar("SYM3", s62, 13, 21000.0, 21000.0))
    bars_1h_2.append(_make_1h_bar("SYM2", s62, 14, 20500.0, 20500.0))
    bars_1h_3.append(_make_1h_bar("SYM3", s62, 14, 21000.0, 21000.0))

    # Session 63: SYM2 triggers TREND at hour 14
    s63 = sessions[63]
    for h in (9, 10, 11, 13):
        bars_1h_1.append(_make_1h_bar("SYM1", s63, h, 18000.0, 18000.0))
        bars_1h_2.append(_make_1h_bar("SYM2", s63, h, 20500.0, 20500.0))
        bars_1h_3.append(_make_1h_bar("SYM3", s63, h, 21000.0, 21000.0))
    bars_1h_1.append(_make_1h_bar("SYM1", s63, 14, 18000.0, 18000.0))
    bars_1h_2.append(_make_1h_bar("SYM2", s63, 14, 20500.0, 20500.0))  # TREND signal
    bars_1h_3.append(_make_1h_bar("SYM3", s63, 14, 21000.0, 21000.0))

    # Session 64: SYM2 postponed at hour 09 by floor lock, exits at hour 10
    s64 = sessions[64]
    bars_1h_1.append(_make_1h_bar("SYM1", s64, 9, 18000.0, 18000.0))
    # Previous close was 15000 -> floor = 13950. high=low=13950 is locked!
    bars_1h_2.append(_make_1h_bar("SYM2", s64, 9, 13950.0, 13950.0, high=13950.0, low=13950.0))
    bars_1h_3.append(_make_1h_bar("SYM3", s64, 9, 21000.0, 21000.0))

    # Hour 10: unlocked, executes exit at open 19000
    bars_1h_1.append(_make_1h_bar("SYM1", s64, 10, 18000.0, 18000.0))
    bars_1h_2.append(_make_1h_bar("SYM2", s64, 10, 19000.0, 19000.0, high=19100.0, low=18900.0))
    bars_1h_3.append(_make_1h_bar("SYM3", s64, 10, 21500.0, 21500.0))

    for h in (11, 13, 14):
        bars_1h_1.append(_make_1h_bar("SYM1", s64, h, 18000.0, 18000.0))
        bars_1h_2.append(_make_1h_bar("SYM2", s64, h, 19000.0, 19000.0))
        bars_1h_3.append(_make_1h_bar("SYM3", s64, h, 21500.0, 21500.0))

    # Session 69 (final session): SYM3 exits END
    s69 = sessions[69]
    for h in (9, 10, 11, 13):
        bars_1h_1.append(_make_1h_bar("SYM1", s69, h, 18000.0, 18000.0))
        bars_1h_2.append(_make_1h_bar("SYM2", s69, h, 19000.0, 19000.0))
        bars_1h_3.append(_make_1h_bar("SYM3", s69, h, 21500.0, 21500.0))
    bars_1h_1.append(_make_1h_bar("SYM1", s69, 14, 18000.0, 18000.0))
    bars_1h_2.append(_make_1h_bar("SYM2", s69, 14, 19000.0, 19000.0))
    bars_1h_3.append(_make_1h_bar("SYM3", s69, 14, 21500.0, 22000.0))

    bars_1h_by_sym = {
        "SYM1": bars_1h_1,
        "SYM2": bars_1h_2,
        "SYM3": bars_1h_3,
    }

    trades = simulate_trades(
        bars_1h_by_symbol=bars_1h_by_sym,
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges=exchanges,
        n=2,
        theta=30.0,
        k=2.0,
    )

    assert len(trades) == 3

    # Assert Trade 1 (SYM1): STOP exit
    t1 = next(t for t in trades if t.symbol == "SYM1")
    assert t1.exit_reason == "STOP"
    assert t1.entry_price == 20000.0
    assert t1.exit_price == 18000.0
    assert np.isclose(t1.net_return, -0.10681750224259912, atol=1e-7)
    assert np.isclose(t1.ew_return, -0.00833333333333334, atol=1e-7)
    assert np.isclose(t1.excess_return, -0.09848416890926577, atol=1e-7)

    # Assert Trade 2 (SYM2): TREND exit with floor lock postponement
    t2 = next(t for t in trades if t.symbol == "SYM2")
    assert t2.exit_reason == "TREND"
    assert t2.entry_price == 20000.0
    assert t2.exit_price == 19000.0
    assert np.isclose(t2.net_return, -0.05719625236718817, atol=1e-7)
    assert np.isclose(t2.ew_return, -0.025000000000000022, atol=1e-7)
    assert np.isclose(t2.excess_return, -0.03219625236718815, atol=1e-7)

    # Assert Trade 3 (SYM3): END exit
    t3 = next(t for t in trades if t.symbol == "SYM3")
    assert t3.exit_reason == "END"
    assert t3.entry_price == 20000.0
    assert t3.exit_price == 22000.0
    assert np.isclose(t3.net_return, 0.09166749725904544, atol=1e-7)
    assert np.isclose(t3.ew_return, -0.016666666666666646, atol=1e-7)
    assert np.isclose(t3.excess_return, 0.10833416392571209, atol=1e-7)


# -----------------------------------------------------------------------------
# 2. Test resample_1h all five groups and boundaries (§3.1, §4)
# -----------------------------------------------------------------------------

def test_resample_1h_all_five_groups_and_boundaries():
    """Test resample_1h merges 5m bars into 5 groups (09, 10, 11, 13, 14) including ATC and late bars."""
    bars_5m = [
        # Group 09: 09:00 - 09:10
        Bar5m("SYM", datetime(2026, 5, 4, 9, 0), 10.0, 12.0, 9.5, 11.0, 100.0),
        Bar5m("SYM", datetime(2026, 5, 4, 9, 10), 11.0, 13.0, 10.5, 12.5, 150.0),
        # Group 10
        Bar5m("SYM", datetime(2026, 5, 4, 10, 0), 12.5, 14.0, 12.0, 13.0, 200.0),
        # Group 11: 11:25
        Bar5m("SYM", datetime(2026, 5, 4, 11, 25), 13.0, 15.0, 12.5, 14.0, 250.0),
        # Group 13
        Bar5m("SYM", datetime(2026, 5, 4, 13, 15), 14.0, 16.0, 13.5, 15.5, 300.0),
        # Group 14: 14:25, ATC 14:45, and late 14:55
        Bar5m("SYM", datetime(2026, 5, 4, 14, 25), 15.5, 17.0, 15.0, 16.0, 350.0),
        Bar5m("SYM", datetime(2026, 5, 4, 14, 45), 16.0, 18.0, 15.5, 17.5, 400.0),
        Bar5m("SYM", datetime(2026, 5, 4, 14, 55), 17.5, 19.0, 17.0, 18.5, 450.0),
    ]

    bars_1h = resample_1h(bars_5m)
    assert len(bars_1h) == 5

    # Group 09
    g9 = bars_1h[0]
    assert g9.ts == datetime(2026, 5, 4, 9, 0)
    assert g9.open == 10.0
    assert g9.high == 13.0
    assert g9.low == 9.5
    assert g9.close == 12.5
    assert g9.volume == 250.0

    # Group 11
    g11 = bars_1h[2]
    assert g11.ts == datetime(2026, 5, 4, 11, 0)
    assert g11.open == 13.0
    assert g11.close == 14.0

    # Group 14 (merges 14:25, 14:45 ATC, 14:55)
    g14 = bars_1h[4]
    assert g14.ts == datetime(2026, 5, 4, 14, 0)
    assert g14.open == 15.5
    assert g14.high == 19.0
    assert g14.low == 15.0
    assert g14.close == 18.5
    assert g14.volume == 350.0 + 400.0 + 450.0


# -----------------------------------------------------------------------------
# 3. Test TREND_D transition and current session isolation (§3.2, §4)
# -----------------------------------------------------------------------------

def test_trend_d_transition_and_current_session_isolation():
    """Verify exact first session where TREND_D turns True, and close of session t is excluded."""
    sessions = _make_sessions(10)
    # n=2 requires at least 3 daily bars before session t.
    # Sessions 0, 1 have close 10.0.
    # Session 2 has close 12.0.
    # At session 3: bars before session 3 are j=0 (10), j=1 (10), j=2 (12).
    # SMA_2(2) = (10+12)/2 = 11.0 > SMA_2(1) = 10.0. Close 12 > 11.0.
    # Therefore, exact first session where TREND_D becomes True is sessions[3]!
    price_map = {
        sessions[0]: 10.0,
        sessions[1]: 10.0,
        sessions[2]: 12.0,
        sessions[3]: 1.0,  # CRASH on session 3 itself!
    }
    daily_bars = _make_daily_bars("SYM", sessions, price_map=price_map, trending=False)
    trend = daily_trend_series(daily_bars, sessions, n=2)

    assert trend[sessions[0]] is False
    assert trend[sessions[1]] is False
    assert trend[sessions[2]] is False
    # Exact first session turning True is sessions[3]:
    assert trend[sessions[3]] is True

    # Current session isolation: even though price on session 3 crashed to 1.0,
    # TREND_D(session 3) is still True because session 3's own bar is strictly excluded!
    assert trend[sessions[3]] is True


# -----------------------------------------------------------------------------
# 4. Test load_bars_5m checksum and ordering (§1)
# -----------------------------------------------------------------------------

def test_load_bars_5m_checksum_and_ordering(tmp_path: Path):
    """Test load_bars_5m verifies sha256 checksum and sorts bars chronologically."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    csv_path = data_dir / "bars_5m.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "ts", "open", "high", "low", "close", "volume"])
        writer.writerow(["SYM", "2026-05-04T10:00", 11.0, 12.0, 10.0, 11.5, 100.0])
        writer.writerow(["SYM", "2026-05-04T09:00", 10.0, 11.0, 9.5, 10.5, 100.0])

    h = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    manifest = {"files": {"bars_5m.csv": {"sha256": h}}}
    manifest_p = data_dir / "manifest.json"
    manifest_p.write_text(json.dumps(manifest), encoding="utf-8")

    loaded = load_bars_5m(data_dir)
    assert len(loaded["SYM"]) == 2
    # Verify chronological order
    assert loaded["SYM"][0].ts < loaded["SYM"][1].ts

    # Checksum mismatch
    manifest["files"]["bars_5m.csv"]["sha256"] = "bad_checksum"
    manifest_p.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Checksum mismatch"):
        load_bars_5m(data_dir)


# -----------------------------------------------------------------------------
# 5. Table 4 Mutation Tests (mutations a1 to n)
# -----------------------------------------------------------------------------

def test_mutation_a1_resample_atc_and_late_bars():
    """Mutation a1: Nhóm 14 bỏ nến ATC 14:45, hoặc nến 14:30–14:55 thành nhóm riêng. Calls resample_1h."""
    bars_5m = [
        Bar5m("SYM", datetime(2026, 5, 4, 14, 0), 10.0, 11.0, 9.5, 10.5, 100.0),
        Bar5m("SYM", datetime(2026, 5, 4, 14, 45), 10.5, 12.0, 10.0, 11.5, 200.0),  # ATC
        Bar5m("SYM", datetime(2026, 5, 4, 14, 55), 11.5, 12.5, 11.0, 12.0, 300.0),  # late
    ]
    res = resample_1h(bars_5m)
    # Must be merged into exactly 1 bar for hour 14
    assert len(res) == 1
    assert res[0].ts.hour == 14
    assert res[0].close == 12.0
    assert res[0].volume == 600.0


def test_mutation_a2_resample_open_close_order():
    """Mutation a2: Open/close nhóm lấy sai nến (không phải nến đầu/cuối). Calls resample_1h."""
    bars_5m = [
        Bar5m("SYM", datetime(2026, 5, 4, 9, 0), 10.0, 12.0, 9.5, 11.0, 100.0),
        Bar5m("SYM", datetime(2026, 5, 4, 9, 20), 11.0, 13.0, 10.5, 12.0, 100.0),
        Bar5m("SYM", datetime(2026, 5, 4, 9, 55), 12.0, 14.0, 11.5, 13.5, 100.0),
    ]
    res = resample_1h(bars_5m)
    assert len(res) == 1
    assert res[0].open == 10.0  # must be first bar open
    assert res[0].close == 13.5  # must be last bar close


def test_mutation_b1_trend_uses_same_day():
    """Mutation b1: TREND_D(t) dùng nến ngày của chính t. Calls simulate_trades."""
    sessions = _make_sessions(70)
    exchanges = {"SYM": "HOSE"}
    price_map = {sessions[60]: 1000.0}  # Day 60 crashes
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions, price_map=price_map)}

    bars_1h = [_make_1h_bar("SYM", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    s60 = sessions[60]
    bars_1h.append(_make_1h_bar("SYM", s60, 9, 20000.0, 18000.0))   # bar 28: dip
    bars_1h.append(_make_1h_bar("SYM", s60, 10, 18000.0, 21000.0))  # bar 29: cross up
    bars_1h.append(_make_1h_bar("SYM", s60, 11, 20000.0, 20000.0))  # bar 30: entry
    bars_1h.append(_make_1h_bar("SYM", s60, 13, 20000.0, 20000.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges=exchanges,
        n=2,
        theta=30.0,
        k=2.0,
    )
    # Entry MUST succeed because session 60's crash is excluded from TREND_D(session 60)
    assert len(trades) == 1
    assert trades[0].entry_session == s60


def test_mutation_b2_trend_sma_slope_condition():
    """Mutation b2: Bỏ điều kiện SMA_n(j) > SMA_n(j-1). Calls daily_trend_series."""
    sessions = _make_sessions(10)
    # Price is above SMA, but SMA is falling
    price_map = {sessions[0]: 200.0, sessions[1]: 150.0, sessions[2]: 120.0, sessions[3]: 130.0}
    daily_bars = _make_daily_bars("SYM", sessions, price_map=price_map, trending=False)
    trend = daily_trend_series(daily_bars, sessions, n=2)
    # Must be False due to falling SMA slope!
    assert trend[sessions[4]] is False


def test_mutation_b3_trend_requires_n_plus_one_bars():
    """Mutation b3: Bỏ yêu cầu n + 1 nến. Calls daily_trend_series."""
    sessions = _make_sessions(10)
    # Exactly n bars before t (n=2, so 2 bars before sessions[2])
    daily_bars = _make_daily_bars("SYM", sessions[:2], trending=False)
    trend = daily_trend_series(daily_bars, sessions, n=2)
    # With only 2 bars (less than n+1 = 3), must be False
    assert trend[sessions[2]] is False


def test_mutation_c1_rsi_must_cross_theta():
    """Mutation c1: RSI không cần cắt lên (chỉ RSI(h) >= theta). Calls simulate_trades."""
    sessions = _make_sessions(70)
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions)}
    # If RSI was already >= 30 and stays >= 30, no crossover occurred
    bars_1h = [_make_1h_bar("SYM", sessions[50 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(35)]
    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    # Without crossover from < theta, no trade can enter
    assert len(trades) == 0


def test_mutation_c2_rsi_continuous_across_days():
    """Mutation c2: RSI reset mỗi ngày thay vì liên tục. Calls simulate_trades."""
    sessions = _make_sessions(70)
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions)}
    # Bars spread across days leading to cross from session 59 to session 60
    bars_1h = [_make_1h_bar("SYM", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h.append(_make_1h_bar("SYM", sessions[59], 14, 20000.0, 18000.0))  # dip on session 59
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 9, 18000.0, 21000.0))   # cross up at 09:00 on session 60
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 10, 20000.0, 20000.0))  # entry at 10:00

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades) == 1


def test_mutation_c3_rsi_requires_bar_30():
    """Mutation c3: Bỏ yêu cầu nến thứ 30. Calls simulate_trades."""
    sessions = _make_sessions(70)
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions)}
    # Only 28 bars total before cross: cross at bar 27 (28th bar, h=27 < 29)
    bars_1h = [_make_1h_bar("SYM", sessions[55 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(26)]
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 9, 20000.0, 18000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 10, 18000.0, 21000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 11, 20000.0, 20000.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    # Must NOT enter because h=27 is before the 30th bar
    assert len(trades) == 0


def test_mutation_d1_liquidity_is_liquid_filter():
    """Mutation d1: Bỏ is_liquid. Calls simulate_trades."""
    sessions = _make_sessions(70)
    # Volume tiny -> turnover << 1e9 VND
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions, volume=10.0)}
    bars_1h = [_make_1h_bar("SYM", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 9, 20000.0, 18000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 10, 18000.0, 21000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 11, 20000.0, 20000.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades) == 0


def test_mutation_d2_liquidity_requires_60_days():
    """Mutation d2: Bỏ yêu cầu 60 nến ngày. Calls simulate_trades."""
    sessions = _make_sessions(70)
    # Only 50 daily bars available
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions[:50])}
    bars_1h = [_make_1h_bar("SYM", sessions[40 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h.append(_make_1h_bar("SYM", sessions[49], 9, 20000.0, 18000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[49], 10, 18000.0, 21000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[49], 11, 20000.0, 20000.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades) == 0


def test_mutation_e1_cannot_rebuy_holding_or_pending():
    """Mutation e1: Mua lại mã đang giữ hoặc đang chờ bán. Calls simulate_trades."""
    sessions = _make_sessions(70)
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions)}
    bars_1h = [_make_1h_bar("SYM", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    # First buy
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 9, 20000.0, 18000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 10, 18000.0, 21000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 11, 20000.0, 20000.0))  # entered
    # Second buy attempt while holding
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 13, 20000.0, 18000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 14, 18000.0, 21000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[61], 9, 20000.0, 20000.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades) == 1


def test_mutation_e2_entry_at_open_next_bar_not_close_signal_bar():
    """Mutation e2: Khớp mua ở close h thay vì open h+1. Calls simulate_trades."""
    sessions = _make_sessions(70)
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions)}
    bars_1h = [_make_1h_bar("SYM", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 9, 20000.0, 18000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 10, 18000.0, 21000.0))  # signal close is 21000
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 11, 20500.0, 20500.0))  # open is 20500

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades) == 1
    assert trades[0].entry_price == 20500.0  # open of h+1


def test_mutation_e3_ceiling_open_and_zero_volume_block_entry():
    """Mutation e3: Mua được khi mở cửa giá trần, hoặc khi volume nến khớp bằng 0. Calls simulate_trades."""
    sessions = _make_sessions(70)
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions)}
    bars_1h_base = [_make_1h_bar("SYM", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h_base.append(_make_1h_bar("SYM", sessions[60], 9, 20000.0, 18000.0))
    bars_1h_base.append(_make_1h_bar("SYM", sessions[60], 10, 18000.0, 21000.0))

    # Case A: ceiling open on HOSE (ref ~20590 -> open at 30000 is ceiling open)
    bars_ceil = list(bars_1h_base) + [_make_1h_bar("SYM", sessions[60], 11, 30000.0, 30000.0, volume=1000.0)]
    trades_ceil = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_ceil},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades_ceil) == 0

    # Case B: zero volume on execution bar
    bars_vol0 = list(bars_1h_base) + [_make_1h_bar("SYM", sessions[60], 11, 20000.0, 20000.0, volume=0.0)]
    trades_vol0 = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_vol0},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades_vol0) == 0


def test_mutation_e4_entry_across_discontinuous_session():
    """Mutation e4: Mua qua một phiên bị ngừng (nến h+1 không thuộc phiên kế tiếp). Calls simulate_trades."""
    sessions = _make_sessions(70)
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions)}
    bars_1h = [_make_1h_bar("SYM", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 13, 20000.0, 18000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 14, 18000.0, 21000.0))  # signal at last bar of session 60
    # Next bar is at session 62 (skipped session 61 in S)
    bars_1h.append(_make_1h_bar("SYM", sessions[62], 9, 20000.0, 20000.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades) == 0


def test_mutation_f1_trailing_stop_uses_close_and_includes_entry():
    """Mutation f1: H dùng high thay close, hoặc bỏ E khỏi max. Calls simulate_trades."""
    sessions = _make_sessions(70)
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions)}
    bars_1h = [_make_1h_bar("SYM", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 9, 20000.0, 18000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 10, 18000.0, 21000.0))
    # Entry at 20000.0
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 11, 20000.0, 20000.0))
    # High spikes to 30000, but close is only 20000. ATR is 500.
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 13, 20000.0, 20000.0, high=30000.0, low=20000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 14, 20000.0, 20000.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    # Trade closes as END, not STOP
    assert len(trades) == 1
    assert trades[0].exit_reason == "END"


def test_mutation_f2_atr_excludes_current_session():
    """Mutation f2: ATR_D gồm nến ngày của phiên hiện tại. Calls simulate_trades."""
    sessions = _make_sessions(70)
    price_map = {sessions[62]: 50000.0}
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions, price_map=price_map)}
    bars_1h = [_make_1h_bar("SYM", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 9, 20000.0, 18000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 10, 18000.0, 21000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 11, 20000.0, 20000.0))
    for h in (9, 10, 11, 13, 14):
        bars_1h.append(_make_1h_bar("SYM", sessions[61], h, 20000.0, 20000.0))
    for h in (9, 10, 11, 13, 14):
        bars_1h.append(_make_1h_bar("SYM", sessions[62], h, 20000.0, 20000.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades) == 1
    assert trades[0].exit_reason == "END"


def test_mutation_f3_exit_trend_loss_at_session_end():
    """Mutation f3: Bỏ thoát TREND. Calls simulate_trades."""
    sessions = _make_sessions(70)
    # Trend turns False on session 63
    price_map = {sessions[62]: 15000.0}
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions, price_map=price_map)}
    bars_1h = [_make_1h_bar("SYM", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 9, 20000.0, 18000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 10, 18000.0, 21000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 11, 20000.0, 20000.0))  # buy session 60
    for s_idx in (61, 62):
        for h in (9, 10, 11, 13, 14):
            bars_1h.append(_make_1h_bar("SYM", sessions[s_idx], h, 20000.0, 20000.0))
    # At end of session 62, TREND_D(session 63) turns False -> TREND exit fires!
    bars_1h.append(_make_1h_bar("SYM", sessions[63], 9, 20000.0, 20000.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades) == 1
    assert trades[0].exit_reason == "TREND"


def test_mutation_f4_stop_takes_priority_over_trend():
    """Mutation f4: Ưu tiên TREND thay vì STOP khi cả hai đúng. Calls simulate_trades."""
    sessions = _make_sessions(70)
    price_map = {sessions[62]: 15000.0}
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions, price_map=price_map)}
    bars_1h = [_make_1h_bar("SYM", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 9, 20000.0, 18000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 10, 18000.0, 21000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 11, 20000.0, 20000.0))
    for s_idx in (61, 62):
        for h in (9, 10, 11, 13):
            bars_1h.append(_make_1h_bar("SYM", sessions[s_idx], h, 20000.0, 20000.0))
    # At last bar of session 62: price plunges to 10000 (STOP) AND TREND turns False (TREND)
    bars_1h.append(_make_1h_bar("SYM", sessions[62], 14, 20000.0, 10000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[63], 9, 10000.0, 10000.0, high=10100.0, low=9900.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades) == 1
    # STOP takes precedence!
    assert trades[0].exit_reason == "STOP"


def test_mutation_g1_exit_at_open_next_bar():
    """Mutation g1: Bán ở close nến tín hiệu thay vì open nến sau. Calls simulate_trades."""
    sessions = _make_sessions(70)
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions)}
    bars_1h = [_make_1h_bar("SYM", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 9, 20000.0, 18000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 10, 18000.0, 21000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 11, 20000.0, 20000.0))  # buy
    for h in (13, 14):
        bars_1h.append(_make_1h_bar("SYM", sessions[60], h, 20000.0, 20000.0))
    for s_idx in (61, 62):
        for h in (9, 10, 11, 13, 14):
            bars_1h.append(_make_1h_bar("SYM", sessions[s_idx], h, 20000.0, 20000.0))
    # At session 63, hour 10: close drops to 18000 (STOP signal)
    bars_1h.append(_make_1h_bar("SYM", sessions[63], 10, 20000.0, 18000.0))
    # Next bar session 63, hour 11: open is 17500
    bars_1h.append(_make_1h_bar("SYM", sessions[63], 11, 17500.0, 17500.0, high=17600.0, low=17400.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades) == 1
    assert trades[0].exit_price == 17500.0  # open of next bar, not 18000


def test_mutation_g2_t2_delay_requires_hour_13():
    """Mutation g2: T+2 cho bán từ open phiên e+2 (bỏ luật nến 13). Calls simulate_trades."""
    sessions = _make_sessions(70)
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions)}
    bars_1h = [_make_1h_bar("SYM", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 9, 20000.0, 18000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 10, 18000.0, 21000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 11, 20000.0, 20000.0))  # buy session 60
    # Stop triggers in session 61
    for h in (13, 14):
        bars_1h.append(_make_1h_bar("SYM", sessions[60], h, 20000.0, 20000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[61], 9, 20000.0, 15000.0))  # stop triggered
    for h in (10, 11, 13, 14):
        bars_1h.append(_make_1h_bar("SYM", sessions[61], h, 15000.0, 15000.0))

    # Session 62 (e+2): morning bars 09, 10, 11 MUST NOT execute exit
    bars_1h.append(_make_1h_bar("SYM", sessions[62], 9, 15000.0, 15000.0, high=15100.0, low=14900.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[62], 10, 15000.0, 15000.0, high=15100.0, low=14900.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[62], 11, 15000.0, 15000.0, high=15100.0, low=14900.0))
    # Hour 13: first permitted exit bar
    bars_1h.append(_make_1h_bar("SYM", sessions[62], 13, 16000.0, 16000.0, high=16100.0, low=15900.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades) == 1
    # Exit executed at hour 13
    assert trades[0].exit_ts.hour == 13
    assert trades[0].exit_price == 16000.0


def test_mutation_g3_t2_uses_session_index_not_calendar_days():
    """Mutation g3: T+2 tính theo ngày lịch thay vì chỉ số trong S. Calls simulate_trades."""
    sessions = _make_sessions(70)
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions)}
    bars_1h = [_make_1h_bar("SYM", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 9, 20000.0, 18000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 10, 18000.0, 21000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 11, 20000.0, 20000.0))  # buy session 60
    # Stop fires at session 60 close
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 13, 20000.0, 15000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 14, 15000.0, 15000.0))
    # Next session in S is session 61 (e+1): MUST NOT SELL
    for h in (9, 10, 11, 13, 14):
        bars_1h.append(_make_1h_bar("SYM", sessions[61], h, 15000.0, 15000.0, high=15100.0, low=14900.0))
    # Session 62 (e+2): sell at hour 13
    bars_1h.append(_make_1h_bar("SYM", sessions[62], 9, 15000.0, 15000.0, high=15100.0, low=14900.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[62], 13, 16000.0, 16000.0, high=16100.0, low=15900.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades) == 1
    # Must sell on session 62, not session 61!
    assert trades[0].exit_session == sessions[62]


def test_mutation_h_floor_lock_postpones_exit():
    """Mutation h: Bán được khi khoá sàn. Calls simulate_trades."""
    sessions = _make_sessions(70)
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions)}
    bars_1h = [_make_1h_bar("SYM", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 9, 20000.0, 18000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 10, 18000.0, 21000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 11, 20000.0, 20000.0))  # buy
    for h in (13, 14):
        bars_1h.append(_make_1h_bar("SYM", sessions[60], h, 20000.0, 20000.0))
    for s_idx in (61, 62):
        for h in (9, 10, 11, 13, 14):
            bars_1h.append(_make_1h_bar("SYM", sessions[s_idx], h, 20000.0, 20000.0))
    # Session 63, hour 10: STOP triggers
    bars_1h.append(_make_1h_bar("SYM", sessions[63], 10, 20000.0, 15000.0))
    # Hour 11: floor locked on HOSE (ref 20000 -> floor 18600, high=low=18600)
    bars_1h.append(_make_1h_bar("SYM", sessions[63], 11, 18600.0, 18600.0, high=18600.0, low=18600.0))
    # Hour 13: unlocked, open 19000
    bars_1h.append(_make_1h_bar("SYM", sessions[63], 13, 19000.0, 19000.0, high=19100.0, low=18900.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades) == 1
    # Exit was postponed past hour 11 and executed at hour 13
    assert trades[0].exit_ts.hour == 13
    assert trades[0].exit_price == 19000.0


def test_mutation_i_fee_both_buy_and_sell():
    """Mutation i: Bỏ phí ở chiều mua, hoặc ở chiều bán (hai phép riêng). Calls simulate_trades, compares manual r_i."""
    sessions = _make_sessions(70)
    daily_bars = {"SYM": _make_daily_bars("SYM", sessions)}
    bars_1h = [_make_1h_bar("SYM", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 9, 20000.0, 18000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 10, 18000.0, 21000.0))
    bars_1h.append(_make_1h_bar("SYM", sessions[60], 11, 20000.0, 20000.0))  # buy at 20000
    for h in (13, 14):
        bars_1h.append(_make_1h_bar("SYM", sessions[60], h, 20000.0, 20000.0))
    for s_idx in (61, 62):
        for h in (9, 10, 11, 13, 14):
            bars_1h.append(_make_1h_bar("SYM", sessions[s_idx], h, 20000.0, 20000.0))
    # Close at end: sell at 20000 (flat gross return 0.0%)
    bars_1h.append(_make_1h_bar("SYM", sessions[63], 9, 20000.0, 20000.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM": bars_1h},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades) == 1
    # Full fees: cost_factor = 0.9957 / 1.0033 = 0.992425 -> r_i = -0.007575
    expected_full_fee = 0.9957 / 1.0033 - 1.0
    assert np.isclose(trades[0].net_return, expected_full_fee)

    # If buy fee was omitted: 0.9957 / 1.0 - 1 = -0.0043
    no_buy_fee = 0.9957 - 1.0
    assert not np.isclose(trades[0].net_return, no_buy_fee)

    # If sell fee was omitted: 1.0 / 1.0033 - 1 = -0.003289
    no_sell_fee = 1.0 / 1.0033 - 1.0
    assert not np.isclose(trades[0].net_return, no_sell_fee)


def test_mutation_j1_ew_uses_exact_hourly_prices_not_daily_close():
    """Mutation j1: EW_i dùng close ngày thay vì giá 1 giờ đúng giờ mua/bán. Calls simulate_trades."""
    sessions = _make_sessions(70)
    # SYM_A is traded. SYM_B is EW benchmark with big difference between hourly price and daily close.
    # Daily close of SYM_B on session 60 is 100000, but hourly open at hour 11 is 20000.
    price_map_b = {sessions[60]: 100000.0}
    daily_bars = {
        "SYM_A": _make_daily_bars("SYM_A", sessions),
        "SYM_B": _make_daily_bars("SYM_B", sessions, price_map=price_map_b),
    }

    bars_1h_a = [_make_1h_bar("SYM_A", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h_a.append(_make_1h_bar("SYM_A", sessions[60], 9, 20000.0, 18000.0))
    bars_1h_a.append(_make_1h_bar("SYM_A", sessions[60], 10, 18000.0, 21000.0))
    bars_1h_a.append(_make_1h_bar("SYM_A", sessions[60], 11, 20000.0, 20000.0))  # buy hour 11
    bars_1h_a.append(_make_1h_bar("SYM_A", sessions[60], 13, 20000.0, 20000.0))

    bars_1h_b = [_make_1h_bar("SYM_B", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h_b.append(_make_1h_bar("SYM_B", sessions[60], 9, 20000.0, 20000.0))
    bars_1h_b.append(_make_1h_bar("SYM_B", sessions[60], 10, 20000.0, 20000.0))
    bars_1h_b.append(_make_1h_bar("SYM_B", sessions[60], 11, 20000.0, 20000.0))  # hour 11 price is 20000 (not 100000!)
    bars_1h_b.append(_make_1h_bar("SYM_B", sessions[60], 13, 22000.0, 22000.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM_A": bars_1h_a, "SYM_B": bars_1h_b},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM_A": "HOSE", "SYM_B": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades) == 1
    # EW return for SYM_B from hour 11 to end must use hourly price 20000, not daily close 100000
    assert trades[0].ew_return < 1.0


def test_mutation_j2_ew_universe_requires_liq():
    """Mutation j2: U_i bỏ điều kiện LIQ. Calls simulate_trades."""
    sessions = _make_sessions(70)
    # SYM_ILLIQ has volume=1 (turnover << 1e9 VND) -> LIQ is False
    daily_bars = {
        "SYM_A": _make_daily_bars("SYM_A", sessions),
        "SYM_ILLIQ": _make_daily_bars("SYM_ILLIQ", sessions, volume=1.0),
    }

    bars_1h_a = [_make_1h_bar("SYM_A", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h_a.append(_make_1h_bar("SYM_A", sessions[60], 9, 20000.0, 18000.0))
    bars_1h_a.append(_make_1h_bar("SYM_A", sessions[60], 10, 18000.0, 21000.0))
    bars_1h_a.append(_make_1h_bar("SYM_A", sessions[60], 11, 20000.0, 20000.0))
    bars_1h_a.append(_make_1h_bar("SYM_A", sessions[60], 13, 20000.0, 20000.0))

    # SYM_ILLIQ has crazy price surge (+1000%)
    bars_1h_illiq = [_make_1h_bar("SYM_ILLIQ", sessions[54 + (i // 5)], 9 + (i % 5), 20000.0, 20000.0) for i in range(28)]
    bars_1h_illiq.append(_make_1h_bar("SYM_ILLIQ", sessions[60], 9, 20000.0, 20000.0))
    bars_1h_illiq.append(_make_1h_bar("SYM_ILLIQ", sessions[60], 10, 20000.0, 20000.0))
    bars_1h_illiq.append(_make_1h_bar("SYM_ILLIQ", sessions[60], 11, 20000.0, 20000.0))
    bars_1h_illiq.append(_make_1h_bar("SYM_ILLIQ", sessions[60], 13, 200000.0, 200000.0))

    trades = simulate_trades(
        bars_1h_by_symbol={"SYM_A": bars_1h_a, "SYM_ILLIQ": bars_1h_illiq},
        daily_bars_by_symbol=daily_bars,
        sessions=sessions,
        exchanges={"SYM_A": "HOSE", "SYM_ILLIQ": "HOSE"},
        n=2,
        theta=30.0,
        k=2.0,
    )
    assert len(trades) == 1
    # SYM_ILLIQ must be excluded from U_i because LIQ is False!
    assert trades[0].ew_return == 0.0


def test_mutation_k_bootstrap_by_week_not_by_trade():
    """Mutation k: Bootstrap theo từng lệnh thay vì theo tuần. Calls compute_configuration_metrics."""
    trades = [
        Trade195(
            symbol="S1",
            entry_ts=datetime(2026, 5, 4, 10, 0),
            exit_ts=datetime(2026, 5, 5, 10, 0),
            entry_session=date(2026, 5, 4),  # Week 19
            exit_session=date(2026, 5, 5),
            entry_price=10.0,
            exit_price=11.0,
            net_return=0.1,
            ew_return=0.0,
            excess_return=0.1,
            exit_reason="STOP",
            holding_bars=5,
            holding_sessions=2,
        ),
        Trade195(
            symbol="S2",
            entry_ts=datetime(2026, 5, 11, 10, 0),
            exit_ts=datetime(2026, 5, 12, 10, 0),
            entry_session=date(2026, 5, 11),  # Week 20
            exit_session=date(2026, 5, 12),
            entry_price=10.0,
            exit_price=9.0,
            net_return=-0.1,
            ew_return=0.0,
            excess_return=-0.1,
            exit_reason="STOP",
            holding_bars=5,
            holding_sessions=2,
        ),
    ]
    metrics = compute_configuration_metrics(trades, seed=195)
    # compute_configuration_metrics groups by (year, week)
    assert len(metrics["by_week"]) == 2
    assert (2026, 19) in metrics["by_week"]
    assert (2026, 20) in metrics["by_week"]

    direct_boot = bootstrap_by_month(
        metrics["by_week"],
        n=10000,
        seed=195,
        ci_low_pct=2.5,
        ci_high_pct=97.5,
    )
    assert metrics["p"] == direct_boot["p"]


def test_mutation_m_ledger_safety_assert(tmp_path: Path):
    """Mutation m: run_exploration xoá sổ cũ hoặc bỏ assert_ledger_safety. Calls run_exploration with ledger in tmp_path."""
    ledger_p = tmp_path / "trial_ledger.csv"
    # Create existing invalid ledger without required header to trigger assert_ledger_safety failure
    ledger_p.write_text("corrupted,content\n1,2\n", encoding="utf-8")

    with pytest.raises(SystemExit):
        run_exploration(ledger_path=ledger_p)


def test_mutation_n_step4_dsr_prior_families_and_weekly_series():
    """Mutation n: Bước 4 dùng n_trials thiếu + 27, gọi deflated_sharpe sai tham số. Calls compute_step4_dsr."""
    week_sharpes = [0.5, 0.8, -0.2, 0.4, 0.1, -0.3, 0.6, 0.2]  # 8 trials
    sharpe_w = 0.8
    n_weeks = 18
    skew = -0.2
    kurt = 2.8

    dsr = compute_step4_dsr(
        sharpe_w=sharpe_w,
        n_weeks=n_weeks,
        skew=skew,
        kurt=kurt,
        week_sharpes=week_sharpes,
    )

    # Compute expected DSR with n_trials = 8 + 27 = 35
    expected_dsr = deflated_sharpe(
        sr=sharpe_w,
        n_obs=n_weeks,
        skew=skew,
        kurt=kurt,
        n_trials=len(week_sharpes) + 27,
        sr_trials_var=float(np.var(week_sharpes, ddof=1)),
    )
    assert np.isclose(dsr, expected_dsr)

    # If +27 was omitted (n_trials = 8), DSR would be substantially higher / different
    wrong_dsr = deflated_sharpe(
        sr=sharpe_w,
        n_obs=n_weeks,
        skew=skew,
        kurt=kurt,
        n_trials=len(week_sharpes),
        sr_trials_var=float(np.var(week_sharpes, ddof=1)),
    )
    assert not np.isclose(dsr, wrong_dsr)
