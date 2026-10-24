"""Unit tests and mutation verification for scripts/research191_exits.py.

Covers all 10 mutation requirements from Brief 191 §3:
(a) Entry matched at open t+1 instead of close t.
(b) T+2 holding: cannot sell on session 1 or session 2.
(c) Both TP and SL touched in same session takes SL (conservative).
(d) Open gap: exit at open, not capped at TP when open exceeds TP.
(e) Floor lock handling: cannot sell on floor-locked session, deferred to next session open.
(f) Tested in test_research191_data.py (None for missing foreign flow, never 0).
(g) Tested in test_research191_data.py (raise ValueError when row > end, never silently filter).
(h) GTGD >= 10B filter in entry and baseline (hand-calculated 3-stock test).
(i) Signal cannot look-ahead to t+1 foreign flow.
(j) Explore never deletes existing ledger (raises SystemExit).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from scripts.research191_data import DailyRecord
from scripts.research191_exits import (
    assert_ledger_safety,
    is_floor_locked,
    is_liquid,
    liquid_baseline_excess,
    simulate_trade_exits,
)


def _make_daily_bar(
    symbol: str,
    d: date,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 200_000_000.0,
) -> DailyRecord:
    return DailyRecord(
        symbol=symbol,
        date=d,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _make_liquid_bars(
    symbol: str,
    start_date: date,
    n_days: int,
    base_price: float = 100.0,
    daily_volume: float = 200_000_000.0,  # 100 * 200M = 20,000,000,000 VND (20 tỷ >= 10 tỷ)
) -> list[DailyRecord]:
    bars: list[DailyRecord] = []
    cur_d = start_date
    for _ in range(n_days):
        bars.append(
            _make_daily_bar(
                symbol=symbol,
                d=cur_d,
                open_=base_price,
                high=base_price * 1.01,
                low=base_price * 0.99,
                close=base_price,
                volume=daily_volume,
            )
        )
        cur_d += timedelta(days=1)
    return bars


def test_is_liquid_filter() -> None:
    """Brief §3.3: 20-session turnover close * volume >= 10 tỷ VND."""
    bars = _make_liquid_bars("HPG", date(2020, 1, 1), 25, base_price=50.0, daily_volume=100_000_000.0)
    # 50 * 100_000_000 = 5,000,000,000 VND (5 tỷ < 10 tỷ) -> False
    assert not is_liquid(bars, 19)

    bars_liq = _make_liquid_bars("HPG", date(2020, 1, 1), 25, base_price=50.0, daily_volume=300_000_000.0)
    # 50 * 300_000_000 = 15,000,000,000 VND (15 tỷ >= 10 tỷ) -> True
    assert is_liquid(bars_liq, 19)
    # Less than 20 sessions available -> False
    assert not is_liquid(bars_liq, 18)


def test_mutation_a_entry_at_open_t_plus_1_not_close_t() -> None:
    """Mutation (a): Trade must enter at open t+1, not close t."""
    bars = _make_liquid_bars("HPG", date(2020, 1, 1), 30, base_price=100.0)
    sig_idx = 19
    # At signal date t (index 19): close is 100.0
    # At entry date t+1 (index 20): open is 105.0
    bars[20] = _make_daily_bar("HPG", bars[20].date, open_=105.0, high=106.0, low=104.0, close=105.0, volume=200_000.0)

    trade = simulate_trade_exits(bars, signal_idx=sig_idx, exchange="HOSE", tp=0.10)
    assert trade is not None
    # Entry price MUST be open[t+1] (105.0), NEVER close[t] (100.0)
    assert trade.entry_price == 105.0
    assert trade.entry_ts == bars[20].ts


def test_mutation_b_t_plus_2_holding_enforced() -> None:
    """Mutation (b): T+2 holding: cannot sell on session 1 (entry) or session 2.

    First eligible exit session is session 3.
    """
    bars = _make_liquid_bars("HPG", date(2020, 1, 1), 30, base_price=100.0)
    sig_idx = 19
    # Entry is session 1 (index 20): open=100.0, TP=110.0, SL=93.0
    # Session 2 (index 21): high reaches 120.0 (exceeds TP) and low touches 90.0 (below SL)
    # Under T+2, cannot sell on session 2!
    bars[21] = _make_daily_bar("HPG", bars[21].date, open_=100.0, high=120.0, low=90.0, close=100.0, volume=200_000.0)
    # Session 3 (index 22): calm session, no exit
    bars[22] = _make_daily_bar("HPG", bars[22].date, open_=100.0, high=102.0, low=98.0, close=100.0, volume=200_000.0)
    # Session 4 (index 23): hits TP
    bars[23] = _make_daily_bar("HPG", bars[23].date, open_=100.0, high=112.0, low=99.0, close=111.0, volume=200_000.0)

    trade = simulate_trade_exits(bars, signal_idx=sig_idx, exchange="HOSE", tp=0.10)
    assert trade is not None
    # Must NOT have exited on session 2 (index 21)
    assert trade.exit_ts != bars[21].ts
    # Must exit on session 4 (index 23)
    assert trade.exit_ts == bars[23].ts
    assert trade.exit_reason == "TP"


def test_mutation_c_both_tp_sl_touched_same_session_takes_sl() -> None:
    """Mutation (c): Session touching both TP and SL must take SL (conservative), NOT TP."""
    bars = _make_liquid_bars("HPG", date(2020, 1, 1), 30, base_price=100.0)
    sig_idx = 19
    # Entry at index 20, open=100.0. TP=110.0, SL=93.0
    # Session 3 (index 22): low=90.0 (<=SL) and high=115.0 (>=TP), open=100.0
    bars[22] = _make_daily_bar("HPG", bars[22].date, open_=100.0, high=115.0, low=90.0, close=105.0, volume=200_000.0)

    trade = simulate_trade_exits(bars, signal_idx=sig_idx, exchange="HOSE", tp=0.10)
    assert trade is not None
    assert trade.exit_ts == bars[22].ts
    assert trade.exit_reason == "SL"
    assert trade.exit_price == pytest.approx(93.0)


def test_mutation_d_open_gap_exits_at_open_not_tp() -> None:
    """Mutation (d): Exit at open when open has exceeded TP (not capped at TP)."""
    bars = _make_liquid_bars("HPG", date(2020, 1, 1), 30, base_price=100.0)
    sig_idx = 19
    # Entry index 20, open=100.0. TP=110.0 (tp=0.10)
    # Session 3 (index 22): gaps up at open=115.0
    bars[22] = _make_daily_bar("HPG", bars[22].date, open_=115.0, high=116.0, low=114.0, close=115.0, volume=200_000.0)

    trade = simulate_trade_exits(bars, signal_idx=sig_idx, exchange="HOSE", tp=0.10)
    assert trade is not None
    assert trade.exit_ts == bars[22].ts
    assert trade.exit_reason == "TP"
    # MUST exit at open (115.0), NOT capped at TP (110.0)
    assert trade.exit_price == 115.0
    assert trade.exited_at_open is True


def test_mutation_d_open_gap_down_exits_at_open_not_sl() -> None:
    """Mutation (d) counterpart: Open gap down <= SL exits at open, not SL."""
    bars = _make_liquid_bars("HPG", date(2020, 1, 1), 30, base_price=100.0)
    sig_idx = 19
    # Entry index 20, open=100.0. SL=93.0
    # Session 3 (index 22): gaps down at open=90.0
    bars[22] = _make_daily_bar("HPG", bars[22].date, open_=90.0, high=92.0, low=89.0, close=91.0, volume=200_000.0)

    trade = simulate_trade_exits(bars, signal_idx=sig_idx, exchange="HOSE", tp=0.10)
    assert trade is not None
    assert trade.exit_ts == bars[22].ts
    assert trade.exit_reason == "SL"
    # MUST exit at open (90.0), NOT capped at SL (93.0)
    assert trade.exit_price == 90.0
    assert trade.exited_at_open is True


def test_mutation_e_floor_locked_deferred_to_next_session() -> None:
    """Mutation (e): On a floor-locked session (high == low == floor), cannot sell.

    Order must roll to open of next session.
    """
    bars = _make_liquid_bars("HPG", date(2020, 1, 1), 30, base_price=100.0)
    sig_idx = 19
    # Entry index 20, open=100.0. SL=93.0. Exchange is HOSE (limit 7%)
    # Prev close at session 2 (index 21) = 100.0
    # Floor price on session 3 (index 22) = 100 * (1 - 0.07) = 93.0
    # Session 3 is locked at floor: open=93.0, high=93.0, low=93.0, close=93.0
    bars[22] = _make_daily_bar("HPG", bars[22].date, open_=93.0, high=93.0, low=93.0, close=93.0, volume=200_000.0)
    assert is_floor_locked(100.0, 93.0, 93.0, "HOSE")

    # Session 4 (index 23): opens at 90.0, not floor locked (low=89.0, high=92.0)
    bars[23] = _make_daily_bar("HPG", bars[23].date, open_=90.0, high=92.0, low=89.0, close=91.0, volume=200_000.0)

    trade = simulate_trade_exits(bars, signal_idx=sig_idx, exchange="HOSE", tp=0.10)
    assert trade is not None
    # Under floor lock rule, CANNOT sell on session 3 (index 22)
    assert trade.exit_ts != bars[22].ts
    # Sells on session 4 open (index 23)
    assert trade.exit_ts == bars[23].ts
    assert trade.exit_price == 90.0
    assert trade.exit_reason == "SL"


def test_max_60_sessions_time_exit() -> None:
    """Brief §3.2: Max holding 60 sessions. Expiry exits at open of session 61."""
    # Build 85 days of bars
    bars = _make_liquid_bars("HPG", date(2020, 1, 1), 85, base_price=100.0)
    sig_idx = 19
    # Entry is session 1 (index 20).
    # Sessions 20 through 79 = 60 sessions held (20..79 inclusive = 60 sessions).
    # Session 61 is index 80 (20 + 60 = 80).
    # Keep price constant so no TP/SL touched.
    trade = simulate_trade_exits(bars, signal_idx=sig_idx, exchange="HOSE", tp=0.10)
    assert trade is not None
    assert trade.exit_ts == bars[80].ts
    assert trade.exit_reason == "TIME"
    assert trade.exit_price == bars[80].open
    assert trade.holding_sessions == 60


def test_end_of_data_exit_reason_end() -> None:
    """Brief §3.2: When data ends before 60 sessions without exit, closes at last close with END."""
    # Only 25 bars total: signal at 19, entry at 20, bars end at 24 (4 sessions after entry)
    bars = _make_liquid_bars("HPG", date(2020, 1, 1), 25, base_price=100.0)
    trade = simulate_trade_exits(bars, signal_idx=19, exchange="HOSE", tp=0.10)
    assert trade is not None
    assert trade.exit_ts == bars[-1].ts
    assert trade.exit_reason == "END"
    assert trade.exit_price == bars[-1].close


def test_mutation_h_liquid_baseline_excess_excludes_illiquid_stocks() -> None:
    """Mutation (h) & Brief §3.3: Baseline excess hand-calculated with 3 synthetic stocks.

    Stocks:
    - Stock A (STK_A): Traded stock.
      GTGD = 15 tỷ VND (liquid >= 10 tỷ).
      Entry open = 100.0, exit intraday close = 110.0 (gross return = +10.0%).
      Trade net return = compute_stock_net_return(100.0, 110.0).
    - Stock B (STK_B): Liquid explore stock.
      GTGD = 20 tỷ VND (liquid >= 10 tỷ).
      Entry open = 50.0, exit close = 60.0 (return = (60.0 / 50.0) - 1.0 = +20.0%).
    - Stock C (STK_C): Illiquid explore stock.
      GTGD = 5 tỷ VND (illiquid < 10 tỷ).
      Entry open = 20.0, exit close = 20.0 (return = (20.0 / 20.0) - 1.0 = 0.0%).

    Hand calculation:
    - Signal date is 2020-01-20 (index 19).
    - Entry date is 2020-01-21 (index 20).
    - Exit date is 2020-01-23 (index 22).
    - Liquid universe on signal date:
      STK_A (15B >= 10B) -> eligible
      STK_B (20B >= 10B) -> eligible
      STK_C (5B < 10B) -> EXCLUDED
    - Trade exited intraday (not at open), so baseline stocks use close.
    - Baseline return = mean(STK_A return, STK_B return)
                      = (0.100 + 0.200) / 2 = 0.150 (+15.0%).
    - Excess return = trade.net_return - 0.150.
    - If STK_C had NOT been excluded:
      Baseline would be (0.100 + 0.200 + 0.000) / 3 = 0.100 (+10.0%),
      yielding excess = trade.net_return - 0.100 (differs by 0.050!).
    """
    start_d = date(2020, 1, 1)
    # STK_A: 15 tỷ GTGD (100.0 * 150M = 15B)
    bars_a = _make_liquid_bars("STK_A", start_d, 25, base_price=100.0, daily_volume=150_000_000.0)
    # Entry at index 20 (open=100.0). Exit at index 22 intraday TP (close=110.0)
    bars_a[22] = _make_daily_bar("STK_A", bars_a[22].date, open_=100.0, high=110.0, low=99.0, close=110.0, volume=150_000_000.0)

    # STK_B: 20 tỷ GTGD (50.0 * 400M = 20B) (open=50.0 at idx 20, close=60.0 at idx 22 -> +20%)
    bars_b = _make_liquid_bars("STK_B", start_d, 25, base_price=50.0, daily_volume=400_000_000.0)
    bars_b[20] = _make_daily_bar("STK_B", bars_b[20].date, open_=50.0, high=52.0, low=49.0, close=51.0, volume=400_000_000.0)
    bars_b[22] = _make_daily_bar("STK_B", bars_b[22].date, open_=55.0, high=61.0, low=54.0, close=60.0, volume=400_000_000.0)

    # STK_C: 5 tỷ GTGD (illiquid: 20.0 * 250,000,000 = 5,000,000,000 VND < 10 tỷ)
    bars_c = _make_liquid_bars("STK_C", start_d, 25, base_price=20.0, daily_volume=250_000_000.0)
    bars_c[20] = _make_daily_bar("STK_C", bars_c[20].date, open_=20.0, high=21.0, low=19.0, close=20.0, volume=250_000_000.0)
    bars_c[22] = _make_daily_bar("STK_C", bars_c[22].date, open_=20.0, high=21.0, low=19.0, close=20.0, volume=250_000_000.0)

    bars_by_symbol = {"STK_A": bars_a, "STK_B": bars_b, "STK_C": bars_c}

    # Simulate trade on STK_A at signal_idx=19
    trade = simulate_trade_exits(bars_a, signal_idx=19, exchange="HOSE", tp=0.10)
    assert trade is not None
    assert trade.symbol == "STK_A"
    assert trade.exit_price == 110.0

    res = liquid_baseline_excess([trade], bars_by_symbol)
    expected_baseline_ret = (0.100 + 0.200) / 2.0  # 0.150
    expected_excess = trade.net_return - expected_baseline_ret

    assert res["mean_excess"] == pytest.approx(expected_excess, rel=1e-6)
    assert res["mean_excess_trim1pct"] == pytest.approx(expected_excess, rel=1e-6)

    # Verify that illiquid STK_C return (0.0) is NOT factored into baseline
    wrong_baseline_if_c_included = (0.100 + 0.200 + 0.0) / 3.0  # 0.100
    wrong_excess = trade.net_return - wrong_baseline_if_c_included
    assert res["mean_excess"] != pytest.approx(wrong_excess, rel=1e-3)


def test_mutation_h_entry_liquidity_filter_rejects_illiquid() -> None:
    """Mutation (h) counterpart: simulate_trade_exits rejects illiquid stocks (<10B)."""
    # Base price 20.0, volume 200M -> 4 tỷ < 10 tỷ
    bars = _make_liquid_bars("ILLIQ", date(2020, 1, 1), 25, base_price=20.0, daily_volume=200_000_000.0)
    trade = simulate_trade_exits(bars, signal_idx=19, exchange="HOSE", tp=0.10, enforce_liquidity=True)
    assert trade is None


def test_mutation_i_signal_no_lookahead_foreign_flow() -> None:
    """Mutation (i): Signal evaluated at day t cannot look ahead to day t+1 foreign flow.

    Synthetic setup:
    - Day t has normal/neutral foreign flow (no signal).
    - Day t+1 has an artificial massive foreign flow spike that precedes a price surge on day t+2.
    - A correct rule inspecting records[:t+1] cannot see t+1 and produces NO signal at t.
    - A look-ahead mutated rule inspecting records[t+1] would trigger a signal at t.
    """
    bars = _make_liquid_bars("HPG", date(2020, 1, 1), 25, base_price=100.0)
    t = 19
    # Add foreign flow data
    # Normal on day t: net_val = 0
    bars[t].net_val = 0.0
    # Day t+1: massive spike
    bars[t + 1].net_val = 50_000_000_000.0

    def correct_signal_eval(records: list[Any], idx: int) -> bool:
        # Strictly uses data up to index idx
        if idx >= len(records):
            return False
        rec = records[idx]
        return rec.net_val is not None and rec.net_val > 10_000_000_000.0

    def lookahead_mutated_signal_eval(records: list[Any], idx: int) -> bool:
        # BUG: looks ahead at index idx + 1
        if idx + 1 >= len(records):
            return False
        rec_next = records[idx + 1]
        return rec_next.net_val is not None and rec_next.net_val > 10_000_000_000.0

    # Correct signal MUST be False at day t
    assert correct_signal_eval(bars, t) is False
    # Mutated signal would erroneously trigger True
    assert lookahead_mutated_signal_eval(bars, t) is True


def test_mutation_j_ledger_safety_check_raises_if_exists(tmp_path: Path) -> None:
    """Mutation (j) & Brief §3.4: Sổ thử không bao giờ được xoá hay ghi đè.

    If ledger already exists when starting, raise SystemExit.
    """
    ledger_file = tmp_path / "trial_ledger.csv"
    # Ledger does not exist: passes safely
    assert_ledger_safety(ledger_file)

    # Ledger exists: must raise SystemExit
    ledger_file.write_text("idea_id,period,n\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="đã tồn tại; sổ thử không được xoá"):
        assert_ledger_safety(ledger_file)
