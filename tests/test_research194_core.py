"""Unit tests and mutation tests for Brief 194 core infrastructure (§4).

Includes:
- Hand-calculated test for simulate_swing_portfolio with all 4 fee branches (buy, STOP, TREND, END).
- Test for weekly_trend_series with mid-week price flip.
- 17 mutation tests (a)–(n) calling the exact product functions in Brief 194 §4.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from scripts.research188_core import deflated_sharpe
from scripts.research191_data import StockDailyBar
from scripts.research194_core import (
    MIN_TURNOVER_194,
    chandelier_stop,
    entry_signals,
    simulate_swing_portfolio,
    weekly_trend_series,
)
from scripts.research194_explore import compute_step4_dsr, run_exploration


def _make_dummy_bars(
    sym: str,
    dates: list[date],
    base_price: float = 100.0,
    volume: float = 20_000_000.0,
    price_map: dict[date, float] | None = None,
) -> list[StockDailyBar]:
    bars = []
    for d in dates:
        p = price_map.get(d, base_price) if price_map else base_price
        bars.append(
            StockDailyBar(
                symbol=sym,
                date=d,
                open=p,
                high=p,
                low=p,
                close=p,
                volume=volume,
            )
        )
    return bars


def _make_swing_test_setup():
    """Create a calibrated multi-stock environment for swing testing.

    Sessions 0..99 (weekday calendar).
    r0 = sessions[62] (Wednesday).
    r1 = sessions[67] (Wednesday next week).
    At r0 close:
      Stocks A, B, C trigger buy signal.
    At session 63 open (Thursday):
      Stocks A, B, C are bought (10M each @ 100.0).
    At session 64 close (Friday):
      Stock A plunges to 50.0 -> triggers STOP exit signal.
    At session 65 open (Monday, T+2):
      Stock A is sold at 110.0 (STOP exit).
    At session 65 close (Monday):
      Stock B weekly trend turns False -> triggers TREND exit signal.
    At session 66 open (Tuesday):
      Stock B is sold at 95.0 (TREND exit).
    At session 67 close (Wednesday, final r1):
      Stock C is liquidated at 105.0 (END exit).
    """
    start_d = date(2020, 1, 6)  # Monday
    sessions = [
        start_d + timedelta(days=i)
        for i in range(100)
        if (start_d + timedelta(days=i)).weekday() < 5
    ]

    r0 = sessions[62]
    r1 = sessions[67]

    def make_bars(sym: str):
        prices = [50.0 + (i // 5) * 5.0 for i in range(100)]
        prices[60] = 70.0
        prices[61] = 70.0
        prices[62] = 115.0
        prices[63] = 100.0
        prices[64] = 100.0
        prices[65] = 100.0
        prices[66] = 100.0
        prices[67] = 100.0
        return [
            StockDailyBar(sym, s, p, p, p, p, 20_000_000.0)
            for s, p in zip(sessions, prices)
        ]

    bars_a = make_bars("A")
    bars_b = make_bars("B")
    bars_c = make_bars("C")

    # A triggers STOP at 64 close
    bars_a[64].close = 50.0
    bars_a[65].open = 110.0

    # B: In week 13 (sessions 55..59), closes are 120.0 so week 14 drops to 100.0
    for i in range(55, 60):
        bars_b[i].close = 120.0
    bars_b[66].open = 95.0

    # C: week 14 close (session 64) is 115.0 so weekly trend stays UP
    bars_c[64].close = 115.0
    bars_c[67].close = 105.0

    bars_by_sym = {"A": bars_a, "B": bars_b, "C": bars_c}
    exchanges = {"A": "HOSE", "B": "HOSE", "C": "HOSE"}
    return sessions, r0, r1, bars_by_sym, exchanges


# ==============================================================================
# 1. Hand-Calculated Tests for simulate_swing_portfolio and weekly_trend_series
# ==============================================================================


def test_simulate_swing_portfolio_hand_calculated():
    """Verify simulate_swing_portfolio with all 4 fee branches (§4):
    1. Buy fee: 3 positions * 33,000 = 99,000 VND
    2. Sell fee (STOP): 11M * 0.0043 = 47,300 VND
    3. Sell fee (TREND): 9.5M * 0.0043 = 40,850 VND
    4. Sell fee (END): 10.5M * 0.0043 = 45,150 VND

    Total fees = 99,000 + 47,300 + 40,850 + 45,150 = 232,300.0 VND.
    Final NAV = 100,767,700.0 VND.
    """
    sessions, r0, r1, bars_by_sym, exchanges = _make_swing_test_setup()

    res = simulate_swing_portfolio(
        sessions=sessions,
        bars_by_symbol=bars_by_sym,
        exchanges=exchanges,
        rebalance_dates=[r0, r1],
        n=2,
        theta=40.0,
        k=2.0,
        initial_capital=100_000_000.0,
        k_slots=10,
        min_turnover=MIN_TURNOVER_194,
    )

    expected_final_nav = 100_767_700.0
    expected_total_fees = 232_300.0

    assert np.isclose(res["final_nav"], expected_final_nav, atol=1e-2), (
        f"Final NAV mismatch: expected {expected_final_nav}, got {res['final_nav']}"
    )
    assert np.isclose(res["total_fees"], expected_total_fees, atol=1e-2), (
        f"Total fees mismatch: expected {expected_total_fees}, got {res['total_fees']}"
    )

    reasons = [t.exit_reason for t in res["closed_trades"]]
    assert "STOP" in reasons
    assert "TREND" in reasons
    assert "END" in reasons


def test_weekly_trend_series():
    """Verify weekly_trend_series does NOT flip mid-week (§4).

    Setup:
    - Multiple weeks of data.
    - Inside week W (Monday to Friday), a massive price move happens on Wednesday.
    - weekly_trend_series only uses completed weeks strictly prior to week W.
    - Therefore, TREND(Monday) == TREND(Tuesday) == TREND(Wednesday) == TREND(Friday).
    """
    start_d = date(2020, 1, 6)
    sessions = [
        start_d + timedelta(days=i)
        for i in range(150)
        if (start_d + timedelta(days=i)).weekday() < 5
    ]

    bars = _make_dummy_bars("SYM", sessions, base_price=100.0)
    bars[47].close = 200.0
    bars[47].high = 200.0

    trend = weekly_trend_series(bars, sessions, n=5)
    assert trend[sessions[45]] == trend[sessions[46]] == trend[sessions[47]] == trend[sessions[49]], (
        "Weekly trend must not change mid-week"
    )


# ==============================================================================
# 2. Seventeen Mutation Tests (a)–(n) from Brief 194 §4
# ==============================================================================


def test_mutation_a_weekly_trend_uses_running_week():
    """Mutation (a): Xu hướng tuần dùng tuần đang chạy (chứa t).

    Product function called: weekly_trend_series.
    """
    start_d = date(2020, 1, 6)
    sessions = [
        start_d + timedelta(days=i)
        for i in range(150)
        if (start_d + timedelta(days=i)).weekday() < 5
    ]

    price_map = {}
    for i, s in enumerate(sessions):
        week_num = i // 5
        price_map[s] = 100.0 - week_num * 1.0

    for s in sessions[45:50]:
        price_map[s] = 200.0

    bars = _make_dummy_bars("SYM", sessions, price_map=price_map)
    trend = weekly_trend_series(bars, sessions, n=5)
    assert not trend[sessions[47]], "Running week jump must NOT make trend True on Wednesday"


def test_mutation_b_weekly_trend_drops_sma_slope():
    """Mutation (b): Bỏ điều kiện SMA_n(w) > SMA_n(w−1).

    Product function called: weekly_trend_series.
    """
    start_d = date(2020, 1, 6)
    sessions = [
        start_d + timedelta(days=i)
        for i in range(35)
        if (start_d + timedelta(days=i)).weekday() < 5
    ]

    # Weeks 0, 1, 2, 3:
    # w0=100, w1=100, w2=40, w3=60.
    # At w3: w_close=60 > SMA_2=(40+60)/2=50.
    # But SMA_prev=(100+40)/2=70 > SMA_2=50 (falling SMA slope).
    # In week 4 (session 20), visible week is w3.
    weekly_closes = [100.0, 100.0, 40.0, 60.0, 60.0]
    price_map = {}
    for i, s in enumerate(sessions[:25]):
        w_idx = i // 5
        price_map[s] = weekly_closes[w_idx]

    bars = _make_dummy_bars("SYM", sessions[:25], price_map=price_map)
    trend = weekly_trend_series(bars, sessions[:25], n=2)
    assert not trend[sessions[20]], "Declining SMA slope must yield TREND = False"


def test_mutation_c_entry_signals_drops_crossover_requirement():
    """Mutation (c): RSI không cần cắt lên (chỉ RSI(t) >= theta), hoặc dùng RSI(t+1).

    Product function called: entry_signals.
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(80)]
    r = sessions[65]

    bars = _make_dummy_bars("SYM", sessions, base_price=100.0)
    for i in range(60, 67):
        bars[i].close = 100.0 + (i - 60) * 2.0

    weekly_trend = {"SYM": {s: True for s in sessions}}
    rsi_dict = {s: 50.0 for s in sessions}
    rsi_by_sym = {"SYM": rsi_dict}

    sigs = entry_signals(
        r=r,
        bars_by_symbol={"SYM": bars},
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        weekly_trend_by_symbol=weekly_trend,
        rsi_by_symbol=rsi_by_sym,
        theta=40.0,
        min_turnover=MIN_TURNOVER_194,
    )
    assert sigs == [], "RSI must cross over theta from below; steady high RSI must NOT trigger"


def test_mutation_d_entry_signals_drops_is_liquid():
    """Mutation (d): Bỏ is_liquid.

    Product function called: entry_signals.
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(80)]
    r = sessions[65]

    bars = _make_dummy_bars("SYM", sessions, base_price=100.0, volume=100.0)
    weekly_trend = {"SYM": {s: True for s in sessions}}
    rsi_dict = {s: 50.0 for s in sessions}
    rsi_dict[sessions[64]] = 35.0
    rsi_by_sym = {"SYM": rsi_dict}

    sigs = entry_signals(
        r=r,
        bars_by_symbol={"SYM": bars},
        sessions=sessions,
        exchanges={"SYM": "HOSE"},
        weekly_trend_by_symbol=weekly_trend,
        rsi_by_symbol=rsi_by_sym,
        theta=40.0,
        min_turnover=MIN_TURNOVER_194,
    )
    assert sigs == [], "Illiquid symbol must be rejected by entry_signals"


def test_mutation_e_chandelier_stop_uses_high_or_drops_entry_price():
    """Mutation (e): H_t dùng high thay vì close, hoặc bỏ E khỏi max.

    Product function called: chandelier_stop.
    """
    stop_val = chandelier_stop(entry_price=100.0, highest_close=90.0, atr=5.0, k=2.0)
    assert np.isclose(stop_val, 90.0, atol=1e-6), "H_t must be max(E, highest_close)"


def test_mutation_f_simulate_sells_at_close_not_next_open():
    """Mutation (f): Bán ở close t thay vì open phiên sau.

    Product function called: simulate_swing_portfolio.
    """
    sessions, r0, r1, bars_by_sym, exchanges = _make_swing_test_setup()
    res = simulate_swing_portfolio(
        sessions=sessions,
        bars_by_symbol=bars_by_sym,
        exchanges=exchanges,
        rebalance_dates=[r0, r1],
        n=2,
        theta=40.0,
        k=2.0,
        min_turnover=MIN_TURNOVER_194,
    )
    stop_trade = next(t for t in res["closed_trades"] if t.symbol == "A")
    assert np.isclose(stop_trade.exit_price, 110.0, atol=1e-2), (
        "Exit must match at next session open (110.0)"
    )


def test_mutation_g_simulate_sells_before_t_plus_2():
    """Mutation (g): Bán trước T+2.

    Product function called: simulate_swing_portfolio.
    """
    sessions, r0, r1, bars_by_sym, exchanges = _make_swing_test_setup()
    # Trigger stop immediately at entry day close (session 63)
    bars_by_sym["A"][63].close = 50.0
    res = simulate_swing_portfolio(
        sessions=sessions,
        bars_by_symbol=bars_by_sym,
        exchanges=exchanges,
        rebalance_dates=[r0, r1],
        n=2,
        theta=40.0,
        k=2.0,
        min_turnover=MIN_TURNOVER_194,
    )
    stop_trade = next(t for t in res["closed_trades"] if t.symbol == "A")
    assert stop_trade.exit_date >= sessions[65], "Cannot sell before T+2"


def test_mutation_h_simulate_sells_when_floor_locked():
    """Mutation (h): Bán được khi khoá sàn.

    Product function called: simulate_swing_portfolio.
    """
    sessions, r0, r1, bars_by_sym, exchanges = _make_swing_test_setup()
    # Lock floor at session 65 (-7% from prev close 50.0 -> 50 * 0.93 = 46.5)
    bars_by_sym["A"][65].open = 46.0
    bars_by_sym["A"][65].high = 46.0
    bars_by_sym["A"][65].low = 46.0
    bars_by_sym["A"][65].close = 46.0

    res = simulate_swing_portfolio(
        sessions=sessions,
        bars_by_symbol=bars_by_sym,
        exchanges=exchanges,
        rebalance_dates=[r0, r1],
        n=2,
        theta=40.0,
        k=2.0,
        min_turnover=MIN_TURNOVER_194,
    )
    trade_a = next(t for t in res["closed_trades"] if t.symbol == "A")
    assert trade_a.exit_date > sessions[65], "Floor locked session must defer sell"


def test_mutation_i_simulate_buys_when_entry_status_not_ok():
    """Mutation (i): Mua được khi entry_status != 'ok' (mở cửa giá trần).

    Product function called: simulate_swing_portfolio.
    """
    sessions, r0, r1, bars_by_sym, exchanges = _make_swing_test_setup()
    # At session 63 open, stock A opens at ceiling (+7% from 115.0 -> 115 * 1.07 = 123.05)
    bars_by_sym["A"][63].open = 125.0
    bars_by_sym["A"][63].high = 125.0
    bars_by_sym["A"][63].low = 125.0
    bars_by_sym["A"][63].close = 125.0

    res = simulate_swing_portfolio(
        sessions=sessions,
        bars_by_symbol=bars_by_sym,
        exchanges=exchanges,
        rebalance_dates=[r0, r1],
        n=2,
        theta=40.0,
        k=2.0,
        min_turnover=MIN_TURNOVER_194,
    )
    syms_bought = {t.symbol for t in res["closed_trades"]}
    assert "A" not in syms_bought, "Ceiling open must NOT be bought"


def test_mutation_j_simulate_exceeds_k_slots():
    """Mutation (j): Giữ quá K mã, hoặc mua lại mã đang giữ.

    Product function called: simulate_swing_portfolio.
    """
    sessions, r0, r1, bars_by_sym, exchanges = _make_swing_test_setup()
    # Add 2 more symbols that also trigger buy
    bars_by_sym["D"] = [
        StockDailyBar("D", b.date, b.open, b.high, b.low, b.close, b.volume)
        for b in bars_by_sym["A"]
    ]
    bars_by_sym["E"] = [
        StockDailyBar("E", b.date, b.open, b.high, b.low, b.close, b.volume)
        for b in bars_by_sym["A"]
    ]
    exchanges["D"] = "HOSE"
    exchanges["E"] = "HOSE"

    res = simulate_swing_portfolio(
        sessions=sessions,
        bars_by_symbol=bars_by_sym,
        exchanges=exchanges,
        rebalance_dates=[r0, r1],
        n=2,
        theta=40.0,
        k=2.0,
        k_slots=2,
        min_turnover=MIN_TURNOVER_194,
    )
    syms_bought = {t.symbol for t in res["closed_trades"]}
    assert len(syms_bought) <= 2, "Cannot exceed K=2 slots"


def test_mutation_k1_omit_buy_fee():
    """Mutation (k1): Bỏ phí ở nhánh mua.

    Product function called: simulate_swing_portfolio.
    """
    sessions, r0, r1, bars_by_sym, exchanges = _make_swing_test_setup()
    res = simulate_swing_portfolio(
        sessions=sessions,
        bars_by_symbol=bars_by_sym,
        exchanges=exchanges,
        rebalance_dates=[r0, r1],
        n=2,
        theta=40.0,
        k=2.0,
        min_turnover=MIN_TURNOVER_194,
    )
    assert np.isclose(res["total_fees"], 232_300.0, atol=1e-2), (
        "Total fees must include buy fees"
    )


def test_mutation_k2_omit_stop_fee():
    """Mutation (k2): Bỏ phí ở nhánh bán STOP.

    Product function called: simulate_swing_portfolio.
    """
    sessions, r0, r1, bars_by_sym, exchanges = _make_swing_test_setup()
    res = simulate_swing_portfolio(
        sessions=sessions,
        bars_by_symbol=bars_by_sym,
        exchanges=exchanges,
        rebalance_dates=[r0, r1],
        n=2,
        theta=40.0,
        k=2.0,
        min_turnover=MIN_TURNOVER_194,
    )
    assert np.isclose(res["total_fees"], 232_300.0, atol=1e-2), (
        "Total fees must include STOP sell fees"
    )


def test_mutation_k3_omit_trend_fee():
    """Mutation (k3): Bỏ phí ở nhánh bán TREND.

    Product function called: simulate_swing_portfolio.
    """
    sessions, r0, r1, bars_by_sym, exchanges = _make_swing_test_setup()
    res = simulate_swing_portfolio(
        sessions=sessions,
        bars_by_symbol=bars_by_sym,
        exchanges=exchanges,
        rebalance_dates=[r0, r1],
        n=2,
        theta=40.0,
        k=2.0,
        min_turnover=MIN_TURNOVER_194,
    )
    assert np.isclose(res["total_fees"], 232_300.0, atol=1e-2), (
        "Total fees must include TREND sell fees"
    )


def test_mutation_k4_omit_end_fee():
    """Mutation (k4): Bỏ phí ở nhánh bán END.

    Product function called: simulate_swing_portfolio.
    """
    sessions, r0, r1, bars_by_sym, exchanges = _make_swing_test_setup()
    res = simulate_swing_portfolio(
        sessions=sessions,
        bars_by_symbol=bars_by_sym,
        exchanges=exchanges,
        rebalance_dates=[r0, r1],
        n=2,
        theta=40.0,
        k=2.0,
        min_turnover=MIN_TURNOVER_194,
    )
    assert np.isclose(res["total_fees"], 232_300.0, atol=1e-2), (
        "Total fees must include END sell fees"
    )


def test_mutation_l_mdd_calculated_on_daily_nav_not_monthly():
    """Mutation (l): MDD tính trên NAV tháng thay vì NAV ngày.

    Product function called: simulate_swing_portfolio.
    """
    sessions, r0, r1, bars_by_sym, exchanges = _make_swing_test_setup()
    # At session 64, make all 3 positions plunge by 50%
    bars_by_sym["A"][64].close = 50.0
    bars_by_sym["B"][64].close = 50.0
    bars_by_sym["C"][64].close = 50.0

    res = simulate_swing_portfolio(
        sessions=sessions,
        bars_by_symbol=bars_by_sym,
        exchanges=exchanges,
        rebalance_dates=[r0, r1],
        n=2,
        theta=40.0,
        k=20.0,  # Wide stop so positions are held through session 64
        min_turnover=MIN_TURNOVER_194,
    )
    # 50% plunge on held positions causes > 5% drawdown on daily NAV
    assert res["mdd"] >= 0.045, "MDD must capture daily intra-month plunge"


def test_mutation_m_exploration_asserts_ledger_safety(tmp_path: Path):
    """Mutation (m): run_exploration xoá sổ cũ hoặc bỏ assert_ledger_safety.

    Product function called: run_exploration with ledger_path in tmp_path.
    If ledger exists, run_exploration must raise SystemExit at line 1.
    """
    existing_ledger = tmp_path / "trial_ledger.csv"
    existing_ledger.write_text("existing ledger\n")

    with pytest.raises(SystemExit, match="đã tồn tại; sổ thử không được xoá để chạy lại"):
        run_exploration(
            data_dir=tmp_path,
            ledger_path=existing_ledger,
            candidates_path=tmp_path / "candidates.json",
            report_path=tmp_path / "exploration_report.md",
        )


def test_mutation_n_step4_dsr_includes_plus_26_trials():
    """Mutation (n): Bước 4 dùng n_trials thiếu + 26, hoặc gọi deflated_sharpe sai tham số.

    Product function called: compute_step4_dsr from research194_explore.py.
    Compares compute_step4_dsr against direct call to deflated_sharpe with n_trials = 18 + 26 = 44.
    """
    ea_sharpes = [0.1 * i for i in range(18)]
    sharpe_x = 0.5
    n_months = 36
    skew = -0.2
    kurt = 3.5

    # Direct reference call
    ref_n_trials = 18 + 26  # 44
    ref_var = float(np.var(ea_sharpes, ddof=1))
    ref_dsr = deflated_sharpe(
        sr=sharpe_x,
        n_obs=n_months,
        skew=skew,
        kurt=kurt,
        n_trials=ref_n_trials,
        sr_trials_var=ref_var,
    )

    # Product function call
    dsr_prod = compute_step4_dsr(
        sharpe_x=sharpe_x,
        n_months=n_months,
        skew=skew,
        kurt=kurt,
        ea_sharpes=ea_sharpes,
    )

    assert np.isclose(dsr_prod, ref_dsr, atol=1e-6), (
        "Step 4 DSR must use n_trials = len(ea_sharpes) + 26"
    )


# ==============================================================================
# 3. Claude audit additions: branches no test above exercised
# ==============================================================================


def test_weekly_trend_first_flip_is_monday_after_nth_plus_one_week():
    """§3.1: needs n + 1 completed weeks; TREND first turns True on the Monday after them.

    Weekly closes 10, 20, 30, 40, ... (constant within each week), n = 3.
    - Week 3 (sessions 15..19): only weeks 0..2 visible = 3 < n + 1 -> False all week,
      even though the running week already closes at 40.
    - Week 4 Monday (session 20): weeks 0..3 visible, SMA3 = 30 > SMA3(prev) = 20,
      close 40 > 30 -> True. This is the first True session.
    """
    start_d = date(2020, 1, 6)  # Monday
    sessions = [
        start_d + timedelta(days=i)
        for i in range(42)
        if (start_d + timedelta(days=i)).weekday() < 5
    ]
    price_map = {s: 10.0 * (i // 5 + 1) for i, s in enumerate(sessions)}
    bars = _make_dummy_bars("SYM", sessions, price_map=price_map)

    trend = weekly_trend_series(bars, sessions, n=3)
    first_true = next(i for i, s in enumerate(sessions) if trend[s])
    assert first_true == 20
    assert not any(trend[s] for s in sessions[15:20])


def test_mutation_e_highest_close_tracks_close_not_high():
    """Mutation (e), simulator side: H_t must use close, not high.

    A is bought at session 63 open (100). Bar 63 has high 200 but close 100.
    - With close: H = 100, stop = 100 - 2*ATR < 100, no STOP. Week ending 64 closes
      at 100 < SMA2, so TREND fails at close 65 -> sold at open 66, reason TREND.
    - With high: H = 200, stop > 100 -> STOP at close 63 -> sold at open 65.
    """
    sessions, r0, r1, bars_by_sym, exchanges = _make_swing_test_setup()
    bars_by_sym["A"][63].high = 200.0
    bars_by_sym["A"][64].close = 100.0

    res = simulate_swing_portfolio(
        sessions=sessions,
        bars_by_symbol=bars_by_sym,
        exchanges=exchanges,
        rebalance_dates=[r0, r1],
        n=2,
        theta=40.0,
        k=2.0,
        min_turnover=MIN_TURNOVER_194,
    )
    trade_a = next(t for t in res["closed_trades"] if t.symbol == "A")
    assert trade_a.exit_reason == "TREND"
    assert trade_a.exit_date == sessions[66]


def test_mutation_j_simulate_does_not_rebuy_held_symbol():
    """Mutation (j), second half: a held symbol must not be bought again.

    C dips to 60 at close 63 (RSI 37.9) and recovers to 115 at close 64 (RSI 57.0),
    a fresh cross of theta = 40 while C is held. k = 20 keeps every stop far away.
    C must close exactly one trade, the one entered at session 63.
    """
    sessions, r0, r1, bars_by_sym, exchanges = _make_swing_test_setup()
    bars_by_sym["C"][63].close = 60.0

    res = simulate_swing_portfolio(
        sessions=sessions,
        bars_by_symbol=bars_by_sym,
        exchanges=exchanges,
        rebalance_dates=[r0, r1],
        n=2,
        theta=40.0,
        k=20.0,
        min_turnover=MIN_TURNOVER_194,
    )
    trades_c = [t for t in res["closed_trades"] if t.symbol == "C"]
    assert len(trades_c) == 1
    assert trades_c[0].entry_date == sessions[63]


def test_simulate_no_entry_signal_at_penultimate_close():
    """§3.4: no buy signal is taken at the close of the session before the last.

    Period sessions[60] -> sessions[63]; the A/B/C signal fires at close 62, which is
    the penultimate session. Nothing may be bought, so NAV stays at 100M with no fees.
    """
    sessions, _, _, bars_by_sym, exchanges = _make_swing_test_setup()
    res = simulate_swing_portfolio(
        sessions=sessions,
        bars_by_symbol=bars_by_sym,
        exchanges=exchanges,
        rebalance_dates=[sessions[60], sessions[63]],
        n=2,
        theta=40.0,
        k=2.0,
        min_turnover=MIN_TURNOVER_194,
    )
    assert res["closed_trades"] == []
    assert res["total_fees"] == 0.0
    assert res["final_nav"] == 100_000_000.0


def test_simulate_tenth_buy_capped_by_cash():
    """§3.4: v = min(NAV/K, cash / 1.0033); cash never goes negative.

    Ten copies of C signal at close 62. Nine buys take 10M each and cost 10.033M,
    leaving 9.703M, so the tenth buy is 9.703M / 1.0033. All ten end at 105 (END).
    """
    sessions, r0, r1, bars_by_sym, exchanges = _make_swing_test_setup()
    for i in range(10):
        sym = f"C{i}"
        bars_by_sym[sym] = [
            StockDailyBar(sym, b.date, b.open, b.high, b.low, b.close, b.volume)
            for b in bars_by_sym["C"]
        ]
        exchanges[sym] = "HOSE"
    for sym in ("A", "B", "C"):
        del bars_by_sym[sym]
        del exchanges[sym]

    res = simulate_swing_portfolio(
        sessions=sessions,
        bars_by_symbol=bars_by_sym,
        exchanges=exchanges,
        rebalance_dates=[r0, r1],
        n=2,
        theta=40.0,
        k=2.0,
        min_turnover=MIN_TURNOVER_194,
    )
    tenth_v = (100_000_000.0 - 9 * 10_000_000.0 * 1.0033) / 1.0033
    invested = 9 * 10_000_000.0 + tenth_v
    expected_final_nav = invested / 100.0 * 105.0 * 0.9957
    assert len(res["closed_trades"]) == 10
    assert all(t.exit_reason == "END" for t in res["closed_trades"])
    assert np.isclose(res["final_nav"], expected_final_nav, atol=1e-2)


def test_simulate_stop_wins_when_stop_and_trend_fire_together():
    """§3.3: if STOP and TREND are both true at the same close, the reason is STOP.

    B already loses its weekly trend at close 65; also crash its close 65 to 50.
    """
    sessions, r0, r1, bars_by_sym, exchanges = _make_swing_test_setup()
    bars_by_sym["B"][65].close = 50.0

    res = simulate_swing_portfolio(
        sessions=sessions,
        bars_by_symbol=bars_by_sym,
        exchanges=exchanges,
        rebalance_dates=[r0, r1],
        n=2,
        theta=40.0,
        k=2.0,
        min_turnover=MIN_TURNOVER_194,
    )
    trade_b = next(t for t in res["closed_trades"] if t.symbol == "B")
    assert trade_b.exit_reason == "STOP"
    assert trade_b.exit_date == sessions[66]
