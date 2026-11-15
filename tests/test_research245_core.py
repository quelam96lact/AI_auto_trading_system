"""Synthetic unit tests for Brief 245 (Ceiling-Lock Continuation)."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts.research191_data import StockDailyBar
from scripts.research245_core import (
    IS_END_DATE,
    MIN_TURNOVER_245,
    build_sessions,
    compute_ew_return,
    compute_trade_net_return,
    detect_ceiling_events,
    is_ceiling_hit,
    load_is_data,
    simulate_horizon,
)
from scripts.research245_explore import DEFAULT_DATA_DIR, run_exploration
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS


def _make_weekdays(start: date, count: int) -> list[date]:
    days: list[date] = []
    cur = start
    while len(days) < count:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days


def _make_liquid_bars(
    symbol: str,
    dates: list[date],
    *,
    base_price: float = 10_000.0,
    volume: float = 200_000.0,
) -> list[StockDailyBar]:
    """Create flat liquid bars (10,000 * 200,000 = 2B VND/day >= 1B)."""
    return [
        StockDailyBar(
            symbol=symbol,
            date=d,
            open=base_price,
            high=base_price,
            low=base_price,
            close=base_price,
            volume=volume,
        )
        for d in dates
    ]


def _write_synthetic_dataset(
    root: Path,
    bars: list[StockDailyBar],
    exchanges: dict[str, str],
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    stocks_p = root / "stocks_daily.csv"
    with open(stocks_p, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "date", "open", "high", "low", "close", "volume"])
        for b in bars:
            w.writerow([b.symbol, b.date.isoformat(), b.open, b.high, b.low, b.close, b.volume])

    exch_p = root / "exchanges.csv"
    with open(exch_p, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "exchange"])
        for sym, ex in exchanges.items():
            w.writerow([sym, ex])

    sha = hashlib.sha256(stocks_p.read_bytes()).hexdigest()
    (root / "manifest.json").write_text(
        json.dumps({"stocks_daily.csv": {"sha256": sha}}),
        encoding="utf-8",
    )


def test_is_loader_rejects_dates_after_2022_12_30(tmp_path: Path) -> None:
    bars = [
        StockDailyBar("AAA", date(2022, 12, 30), 10.0, 10.0, 10.0, 10.0, 1000.0),
        StockDailyBar("AAA", date(2022, 12, 31), 10.0, 10.0, 10.0, 10.0, 1000.0),
    ]
    _write_synthetic_dataset(tmp_path, bars, {"AAA": "HOSE"})

    with pytest.raises(ValueError):
        load_is_data(tmp_path)

    with pytest.raises(ValueError, match="exceeds maximum allowed"):
        load_is_data(tmp_path, end=date(2023, 1, 2))


def test_ceiling_hit_band_boundaries_all_exchanges() -> None:
    # HOSE 7%: [0.065, 0.09]
    assert is_ceiling_hit(0.065, 0.07)
    assert is_ceiling_hit(0.09, 0.07)
    assert not is_ceiling_hit(0.0649, 0.07)
    assert not is_ceiling_hit(0.0901, 0.07)

    # HNX 10%: [0.095, 0.12]
    assert is_ceiling_hit(0.095, 0.10)
    assert is_ceiling_hit(0.12, 0.10)
    assert not is_ceiling_hit(0.0949, 0.10)
    assert not is_ceiling_hit(0.1201, 0.10)

    # UPCOM 15%: [0.145, 0.17]
    assert is_ceiling_hit(0.145, 0.15)
    assert is_ceiling_hit(0.17, 0.15)
    assert not is_ceiling_hit(0.1449, 0.15)
    assert not is_ceiling_hit(0.1701, 0.15)


def test_detect_events_first_in_chain_only() -> None:
    dates = _make_weekdays(date(2022, 1, 3), 26)
    bars = _make_liquid_bars("AAA", dates, base_price=10_000.0, volume=200_000.0)
    # Day 21: +6.8% locked (first in chain -> detected)
    c1 = 10_680.0
    bars[21] = StockDailyBar("AAA", dates[21], 10_200.0, c1, 10_000.0, c1, 200_000.0)
    # Day 22: +6.8% locked again (t-1 hit ceiling -> NOT first in chain -> skipped)
    c2 = round(c1 * 1.068, 2)
    bars[22] = StockDailyBar("AAA", dates[22], c1, c2, c1, c2, 200_000.0)

    events = detect_ceiling_events({"AAA": bars}, {"AAA": "HOSE"})
    assert [e.event_date for e in events] == [dates[21]]


def test_detect_events_requires_ceiling_lock() -> None:
    dates = _make_weekdays(date(2022, 1, 3), 25)
    bars = _make_liquid_bars("AAA", dates, base_price=10_000.0, volume=200_000.0)
    # Day 21: +6.8% but close < high (not locked -> skipped)
    bars[21] = StockDailyBar("AAA", dates[21], 10_200.0, 10_700.0, 10_000.0, 10_680.0, 200_000.0)
    # Day 22: flat at 10_680
    bars[22] = StockDailyBar("AAA", dates[22], 10_680.0, 10_680.0, 10_680.0, 10_680.0, 200_000.0)
    # Day 23: +6.8% and close == high (locked -> detected)
    bars[23] = StockDailyBar("AAA", dates[23], 10_680.0, 11_406.24, 10_680.0, 11_406.24, 200_000.0)

    events = detect_ceiling_events({"AAA": bars}, {"AAA": "HOSE"})
    assert [e.event_date for e in events] == [dates[23]]


def test_detect_events_liquidity_uses_up_to_t_minus_1() -> None:
    dates = _make_weekdays(date(2022, 1, 3), 25)
    # Illiquid up to t-1: 10_000 * 50_000 = 0.5B < 1B
    bars = _make_liquid_bars("AAA", dates, base_price=10_000.0, volume=50_000.0)
    # Huge spike at t=21 pushing 20-day avg up to t > 1B, but up to t-1 is still 0.5B
    bars[21] = StockDailyBar("AAA", dates[21], 10_000.0, 10_700.0, 10_000.0, 10_700.0, 5_000_000.0)

    events = detect_ceiling_events({"AAA": bars}, {"AAA": "HOSE"})
    assert events == []

    # Make bars[1..20] liquid (1.5B) so GTGD20 up to t-1 (idx 20) >= 1B
    for i in range(1, 21):
        bars[i] = StockDailyBar("AAA", dates[i], 10_000.0, 10_000.0, 10_000.0, 10_000.0, 150_000.0)
    events_ok = detect_ceiling_events({"AAA": bars}, {"AAA": "HOSE"})
    assert [e.event_date for e in events_ok] == [dates[21]]


def test_detect_events_excludes_funds_and_first_bar() -> None:
    dates = _make_weekdays(date(2022, 1, 3), 25)
    etf_bars = _make_liquid_bars("E1VFVN30", dates, base_price=10_000.0, volume=200_000.0)
    etf_bars[21] = StockDailyBar("E1VFVN30", dates[21], 10_000.0, 10_700.0, 10_000.0, 10_700.0, 200_000.0)
    fu_bars = _make_liquid_bars("FUEVFVND", dates, base_price=10_000.0, volume=200_000.0)
    fu_bars[21] = StockDailyBar("FUEVFVND", dates[21], 10_000.0, 10_700.0, 10_000.0, 10_700.0, 200_000.0)

    events = detect_ceiling_events(
        {"E1VFVN30": etf_bars, "FUEVFVND": fu_bars},
        {"E1VFVN30": "HOSE", "FUEVFVND": "HOSE"},
    )
    assert events == []


def test_t_plus_2_horizon_3_and_fee_includes_sell_tax() -> None:
    dates = _make_weekdays(date(2022, 1, 3), 30)
    bars = _make_liquid_bars("AAA", dates, base_price=10_000.0, volume=200_000.0)
    # Event at t=20
    bars[20] = StockDailyBar("AAA", dates[20], 10_000.0, 10_700.0, 10_000.0, 10_700.0, 200_000.0)
    # Entry at t+1 (idx 21) open = 10_800, Exit at t+3 (idx 23) close = 11_880
    bars[21] = StockDailyBar("AAA", dates[21], 10_800.0, 10_900.0, 10_700.0, 10_850.0, 200_000.0)
    bars[23] = StockDailyBar("AAA", dates[23], 11_500.0, 11_900.0, 11_400.0, 11_880.0, 200_000.0)

    # Benchmark stock BBB flat at 10_000 so r_ew == 0.0
    bbb = _make_liquid_bars("BBB", dates, base_price=10_000.0, volume=200_000.0)
    universe = {"AAA": bars, "BBB": bbb}
    sessions = build_sessions(universe)
    events = detect_ceiling_events(universe, {"AAA": "HOSE", "BBB": "HOSE"}, sessions=sessions)
    assert len(events) == 1

    sim = simulate_horizon(events, universe, sessions, horizon=3)
    assert len(sim.trades) == 1
    tr = sim.trades[0]
    assert tr.entry_date == dates[21]
    assert tr.exit_date == dates[23]
    assert tr.entry_open == 10_800.0
    assert tr.exit_close == 11_880.0

    # Verify net return includes FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
    s_bps = SLIPPAGE_BPS / 10_000.0
    expected_net = (11_880.0 * (1.0 - FEE_RATE - SELL_TAX_RATE - s_bps)) / (
        10_800.0 * (1.0 + FEE_RATE + s_bps)
    ) - 1.0
    assert tr.r_net == pytest.approx(expected_net, rel=1e-12)
    assert tr.r_net == pytest.approx(compute_trade_net_return(10_800.0, 11_880.0), rel=1e-12)
    # Confirm sell tax strictly reduces net return
    no_tax_net = (11_880.0 * (1.0 - FEE_RATE - s_bps)) / (
        10_800.0 * (1.0 + FEE_RATE + s_bps)
    ) - 1.0
    assert tr.r_net < no_tax_net

    with pytest.raises(ValueError, match="horizon must be >= 3"):
        simulate_horizon(events, universe, sessions, horizon=2)


def test_skip_new_event_while_holding_same_symbol() -> None:
    dates = _make_weekdays(date(2022, 1, 3), 35)
    bars = _make_liquid_bars("AAA", dates, base_price=10_000.0, volume=200_000.0)
    bbb = _make_liquid_bars("BBB", dates, base_price=10_000.0, volume=200_000.0)

    # Event 1 at idx 20 -> entry idx 21, exit idx 25 (H=5)
    bars[20] = StockDailyBar("AAA", dates[20], 10_000.0, 10_700.0, 10_000.0, 10_700.0, 200_000.0)
    # Days 21-22 flat at 10_700 (not ceiling) so day 23 can be first-in-chain
    bars[21] = StockDailyBar("AAA", dates[21], 10_700.0, 10_700.0, 10_700.0, 10_700.0, 200_000.0)
    bars[22] = StockDailyBar("AAA", dates[22], 10_700.0, 10_700.0, 10_700.0, 10_700.0, 200_000.0)
    # Event 2 at idx 23 -> entry idx 24 <= exit_date(idx 25) -> MUST be skipped_holding
    c2 = 11_449.0
    bars[23] = StockDailyBar("AAA", dates[23], 10_700.0, c2, 10_700.0, c2, 200_000.0)
    # Days 24-25 flat at c2, Event 3 at idx 26 -> entry idx 27 > exit_date(idx 25) -> MUST execute
    bars[24] = StockDailyBar("AAA", dates[24], c2, c2, c2, c2, 200_000.0)
    bars[25] = StockDailyBar("AAA", dates[25], c2, c2, c2, c2, 200_000.0)
    c3 = round(c2 * 1.07, 2)
    bars[26] = StockDailyBar("AAA", dates[26], c2, c3, c2, c3, 200_000.0)

    universe = {"AAA": bars, "BBB": bbb}
    sessions = build_sessions(universe)
    events = detect_ceiling_events(universe, {"AAA": "HOSE", "BBB": "HOSE"}, sessions=sessions)
    assert [e.event_date for e in events] == [dates[20], dates[23], dates[26]]

    sim = simulate_horizon(events, universe, sessions, horizon=5)
    assert sim.skipped_holding == 1
    assert len(sim.trades) == 2
    assert [t.event_date for t in sim.trades] == [dates[20], dates[26]]


def test_missing_exit_candle_falls_back_or_skips() -> None:
    dates = _make_weekdays(date(2022, 1, 3), 30)
    bbb = _make_liquid_bars("BBB", dates, base_price=10_000.0, volume=200_000.0)

    # Case A: AAA missing bar at t+5 (idx 25) and t+4 (idx 24), has bar at t+3 (idx 23)
    aaa_full = _make_liquid_bars("AAA", dates, base_price=10_000.0, volume=200_000.0)
    aaa_full[20] = StockDailyBar("AAA", dates[20], 10_000.0, 10_700.0, 10_000.0, 10_700.0, 200_000.0)
    aaa_full[23] = StockDailyBar("AAA", dates[23], 10_700.0, 11_100.0, 10_700.0, 11_000.0, 200_000.0)
    aaa_a = [b for i, b in enumerate(aaa_full) if i not in (24, 25)]

    universe_a = {"AAA": aaa_a, "BBB": bbb}
    sessions_a = build_sessions(universe_a)
    events_a = detect_ceiling_events(universe_a, {"AAA": "HOSE", "BBB": "HOSE"}, sessions=sessions_a)
    sim_a = simulate_horizon(events_a, universe_a, sessions_a, horizon=5)
    assert len(sim_a.trades) == 1
    assert sim_a.trades[0].exit_date == dates[23]
    assert sim_a.trades[0].exit_close == 11_000.0

    # Case B: AAA missing all bars in (t+1, t+5] (indices 22..25) -> skipped_missing_exit
    aaa_b = [b for i, b in enumerate(aaa_full) if i not in (22, 23, 24, 25)]
    universe_b = {"AAA": aaa_b, "BBB": bbb}
    sessions_b = build_sessions(universe_b)
    events_b = detect_ceiling_events(universe_b, {"AAA": "HOSE", "BBB": "HOSE"}, sessions=sessions_b)
    sim_b = simulate_horizon(events_b, universe_b, sessions_b, horizon=5)
    assert len(sim_b.trades) == 0
    assert sim_b.skipped_missing_exit == 1

    # Case C: AAA missing entry bar at t+1 (idx 21) -> skipped_missing_entry
    aaa_c = [b for i, b in enumerate(aaa_full) if i != 21]
    universe_c = {"AAA": aaa_c, "BBB": bbb}
    sessions_c = build_sessions(universe_c)
    events_c = detect_ceiling_events(universe_c, {"AAA": "HOSE", "BBB": "HOSE"}, sessions=sessions_c)
    sim_c = simulate_horizon(events_c, universe_c, sessions_c, horizon=5)
    assert len(sim_c.trades) == 0
    assert sim_c.skipped_missing_entry == 1


def test_ew_benchmark_filters_funds_and_liquidity_up_to_t() -> None:
    dates = _make_weekdays(date(2022, 1, 3), 26)
    liq = _make_liquid_bars("AAA", dates, base_price=10_000.0, volume=200_000.0)
    liq[23] = StockDailyBar("AAA", dates[23], 10_000.0, 11_000.0, 10_000.0, 11_000.0, 200_000.0)  # +10%
    illiq = _make_liquid_bars("ILL", dates, base_price=10_000.0, volume=1_000.0)
    illiq[23] = StockDailyBar("ILL", dates[23], 10_000.0, 20_000.0, 10_000.0, 20_000.0, 1_000.0)  # +100%
    etf = _make_liquid_bars("E1VFVN30", dates, base_price=10_000.0, volume=200_000.0)
    etf[23] = StockDailyBar("E1VFVN30", dates[23], 10_000.0, 15_000.0, 10_000.0, 15_000.0, 200_000.0)  # +50%

    universe = {"AAA": liq, "ILL": illiq, "E1VFVN30": etf}
    idx_map = {sym: {b.date: i for i, b in enumerate(bl)} for sym, bl in universe.items()}
    r_ew = compute_ew_return(dates[20], dates[21], dates[23], universe, idx_map)
    assert r_ew == pytest.approx(0.10, rel=1e-12)


def test_explore_synthetic_pipeline_and_pre_dec1_guard(tmp_path: Path) -> None:
    # Guard blocks full run on real DEFAULT_DATA_DIR before 2026-12-01
    with pytest.raises(RuntimeError, match="Refusing full IS profit run"):
        run_exploration(
            DEFAULT_DATA_DIR,
            tmp_path / "blocked",
            events_only=False,
            today=date(2026, 11, 16),
        )

    # Synthetic dataset across 5 months so PBO (T >= 4) also runs
    dates = _make_weekdays(date(2022, 1, 3), 120)
    aaa = _make_liquid_bars("AAA", dates, base_price=10_000.0, volume=200_000.0)
    bbb = _make_liquid_bars("BBB", dates, base_price=10_000.0, volume=200_000.0)
    for idx in (22, 44, 66, 88, 105):
        aaa[idx] = StockDailyBar("AAA", dates[idx], 10_000.0, 10_700.0, 10_000.0, 10_700.0, 200_000.0)
        aaa[idx + 1] = StockDailyBar("AAA", dates[idx + 1], 10_800.0, 11_000.0, 10_800.0, 11_000.0, 200_000.0)
        for k in range(2, 11):
            if idx + k < len(aaa):
                aaa[idx + k] = StockDailyBar("AAA", dates[idx + k], 11_100.0, 11_200.0, 11_000.0, 11_200.0, 200_000.0)

    data_dir = tmp_path / "data"
    out_dir = tmp_path / "out"
    _write_synthetic_dataset(data_dir, aaa + bbb, {"AAA": "HOSE", "BBB": "HOSE"})

    ev_res = run_exploration(data_dir, out_dir, events_only=True, n_boot=200)
    assert ev_res["events_summary"]["total_events"] == 5
    assert (out_dir / "events_summary.json").exists()

    full_res = run_exploration(data_dir, out_dir, events_only=False, n_boot=200)
    gate = full_res["gate_result"]
    assert gate["n_trials"] == 35
    assert gate["pbo"] is not None
    assert (out_dir / "is_report.md").exists()
    assert (out_dir / "is_results.json").exists()

    # Also verify evaluate_is_gates returns expected keys
    assert set(gate["stats_by_h"].keys()) == {3, 5, 10}
    assert IS_END_DATE == date(2022, 12, 30)
    assert MIN_TURNOVER_245 == 1_000_000_000.0


def test_detect_events_exchange_holiday_gap_still_triggers() -> None:
    """(a) HOSE symbol skips an exchange-specific holiday present in market sessions."""
    dates = _make_weekdays(date(2022, 1, 3), 26)
    hnx_bars = _make_liquid_bars("HNX1", dates, base_price=10_000.0, volume=200_000.0)
    # HOSE symbol misses dates[21] (e.g. exchange-specific holiday), hits ceiling on dates[22]
    hose_full = _make_liquid_bars("AAA", dates, base_price=10_000.0, volume=200_000.0)
    hose_full[22] = StockDailyBar("AAA", dates[22], 10_000.0, 10_700.0, 10_000.0, 10_700.0, 200_000.0)
    hose_bars = [b for i, b in enumerate(hose_full) if i != 21]

    universe = {"AAA": hose_bars, "HNX1": hnx_bars}
    sessions = build_sessions(universe)
    assert dates[21] in sessions
    events = detect_ceiling_events(universe, {"AAA": "HOSE", "HNX1": "HNX"}, sessions=sessions)
    assert [e.event_date for e in events] == [dates[22]]


def test_detect_events_prev_bar_ceiling_with_market_gap_not_first_in_chain() -> None:
    """(b) t-1 of symbol hit ceiling with a market session gap in between -> NOT first in chain."""
    dates = _make_weekdays(date(2022, 1, 3), 28)
    hnx_bars = _make_liquid_bars("HNX1", dates, base_price=10_000.0, volume=200_000.0)
    hose_full = _make_liquid_bars("AAA", dates, base_price=10_000.0, volume=200_000.0)
    # Symbol has bars at idx 20 (10_000), skips idx 21, bar at idx 22 hits ceiling (10_700),
    # then bar at idx 23 hits ceiling again (11_449).
    c1 = 10_700.0
    c2 = 11_449.0
    hose_full[22] = StockDailyBar("AAA", dates[22], 10_000.0, c1, 10_000.0, c1, 200_000.0)
    hose_full[23] = StockDailyBar("AAA", dates[23], c1, c2, c1, c2, 200_000.0)
    hose_bars = [b for i, b in enumerate(hose_full) if i != 21]

    universe = {"AAA": hose_bars, "HNX1": hnx_bars}
    sessions = build_sessions(universe)
    events = detect_ceiling_events(universe, {"AAA": "HOSE", "HNX1": "HNX"}, sessions=sessions)
    # Only dates[22] is first in chain; dates[23] is blocked because symbol's t-1 (dates[22]) hit ceiling
    assert [e.event_date for e in events] == [dates[22]]


def test_detect_events_excludes_2016_from_is_window() -> None:
    """(c) Events in 2016 are excluded from the IS event window (>= 2017-01-01)."""
    dates_2016 = _make_weekdays(date(2016, 11, 1), 30)
    dates_2017 = _make_weekdays(date(2017, 1, 2), 10)
    all_dates = dates_2016 + dates_2017
    bars = _make_liquid_bars("AAA", all_dates, base_price=10_000.0, volume=200_000.0)

    # Ceiling lock in 2016 (idx 22) -> MUST be excluded
    bars[22] = StockDailyBar("AAA", all_dates[22], 10_000.0, 10_700.0, 10_000.0, 10_700.0, 200_000.0)
    # Flat through rest of 2016 and early 2017
    for idx in range(23, 35):
        bars[idx] = StockDailyBar("AAA", all_dates[idx], 10_700.0, 10_700.0, 10_700.0, 10_700.0, 200_000.0)
    # Ceiling lock in 2017 (idx 35) -> MUST be included
    c_2017 = 11_449.0
    bars[35] = StockDailyBar("AAA", all_dates[35], 10_700.0, c_2017, 10_700.0, c_2017, 200_000.0)

    events = detect_ceiling_events({"AAA": bars}, {"AAA": "HOSE"})
    assert [e.event_date for e in events] == [all_dates[35]]


def test_t_plus_2_fallback_exit_window_t3_to_th() -> None:
    """Fallback exit is strictly in [t+3, t+H]: H=3 missing t+3 skips; H=5 missing t+5 sells t+4."""
    dates = _make_weekdays(date(2022, 1, 3), 30)
    bbb = _make_liquid_bars("BBB", dates, base_price=10_000.0, volume=200_000.0)

    aaa_full = _make_liquid_bars("AAA", dates, base_price=10_000.0, volume=200_000.0)
    aaa_full[20] = StockDailyBar("AAA", dates[20], 10_000.0, 10_700.0, 10_000.0, 10_700.0, 200_000.0)
    aaa_full[24] = StockDailyBar("AAA", dates[24], 11_000.0, 11_300.0, 10_900.0, 11_250.0, 200_000.0)

    # H=3 missing t+3 (idx 23), has t+2 (idx 22) -> MUST skip (cannot sell at t+2 under T+2)
    aaa_h3 = [b for i, b in enumerate(aaa_full) if i != 23]
    univ_h3 = {"AAA": aaa_h3, "BBB": bbb}
    sess_h3 = build_sessions(univ_h3)
    ev_h3 = detect_ceiling_events(univ_h3, {"AAA": "HOSE", "BBB": "HOSE"}, sessions=sess_h3)
    sim_h3 = simulate_horizon(ev_h3, univ_h3, sess_h3, horizon=3)
    assert len(sim_h3.trades) == 0
    assert sim_h3.skipped_missing_exit == 1

    # H=5 missing t+5 (idx 25), has t+4 (idx 24) -> sells at t+4
    aaa_h5 = [b for i, b in enumerate(aaa_full) if i != 25]
    univ_h5 = {"AAA": aaa_h5, "BBB": bbb}
    sess_h5 = build_sessions(univ_h5)
    ev_h5 = detect_ceiling_events(univ_h5, {"AAA": "HOSE", "BBB": "HOSE"}, sessions=sess_h5)
    sim_h5 = simulate_horizon(ev_h5, univ_h5, sess_h5, horizon=5)
    assert len(sim_h5.trades) == 1
    assert sim_h5.trades[0].exit_date == dates[24]
    assert sim_h5.trades[0].exit_close == 11_250.0
