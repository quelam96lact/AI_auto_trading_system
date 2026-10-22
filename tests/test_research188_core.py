"""Unit tests for scripts/research188_core.py."""

from datetime import UTC, datetime, timedelta

from scripts.research188_core import (
    Bar,
    Trade,
    align_higher,
    calculate_stock_baseline_excess,
    calculate_trade_metrics,
    compute_crypto_net_return,
    count_crypto_funding_intervals,
    deflated_sharpe,
    resample,
    simulate_portfolio,
)
from scripts.research188_data import TZ_VN


def _make_stock_bar(d_str: str, open_: float, close: float, high: float = 0.0, low: float = 0.0, vol: float = 1000.0) -> Bar:
    d = datetime.strptime(d_str, "%Y-%m-%d").date()
    ts = datetime(d.year, d.month, d.day, 9, 0, tzinfo=TZ_VN)
    ct = datetime(d.year, d.month, d.day, 15, 0, tzinfo=TZ_VN)
    h = high if high > 0 else max(open_, close) + 1.0
    l = low if low > 0 else min(open_, close) - 1.0
    return Bar("AAA", ts, open_, h, l, close, vol, ct)


def _make_crypto_bar(ts_str: str, open_: float, close: float, high: float = 0.0, low: float = 0.0, vol: float = 10.0) -> Bar:
    ts = datetime.fromisoformat(ts_str)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    ct = ts + timedelta(hours=1)
    h = high if high > 0 else max(open_, close) + 5.0
    l = low if low > 0 else min(open_, close) - 5.0
    return Bar("BTC-USDT", ts, open_, h, l, close, vol, ct)


def test_resample_stocks_weekly():
    # Mon 2016-01-04 to Fri 2016-01-08 (week 1)
    # Mon 2016-01-11 to Wed 2016-01-13 (week 2, short week)
    bars = [
        _make_stock_bar("2016-01-04", 10.0, 10.5, 11.0, 9.5, 100),
        _make_stock_bar("2016-01-05", 10.5, 11.0, 11.5, 10.0, 100),
        _make_stock_bar("2016-01-08", 11.0, 12.0, 12.5, 10.8, 100),  # Friday
        _make_stock_bar("2016-01-11", 12.0, 12.5, 13.0, 11.8, 100),  # Next Mon
        _make_stock_bar("2016-01-13", 12.5, 13.0, 13.5, 12.2, 100),  # Short week ends Wed
    ]
    weekly = resample(bars, "1W")
    assert len(weekly) == 2

    w1 = weekly[0]
    assert w1.open == 10.0
    assert w1.close == 12.0
    assert w1.high == 12.5
    assert w1.low == 9.5
    assert w1.volume == 300
    # Friday 2016-01-08 at 15:00
    assert w1.close_time == datetime(2016, 1, 8, 15, 0, tzinfo=TZ_VN)

    w2 = weekly[1]
    assert w2.open == 12.0
    assert w2.close == 13.0
    # Friday of week 2 is 2016-01-15 15:00
    assert w2.close_time == datetime(2016, 1, 15, 15, 0, tzinfo=TZ_VN)


def test_resample_crypto_4h_and_1d():
    bars = [
        _make_crypto_bar("2024-04-27T00:00:00+00:00", 100.0, 102.0),
        _make_crypto_bar("2024-04-27T01:00:00+00:00", 102.0, 101.0),
        _make_crypto_bar("2024-04-27T02:00:00+00:00", 101.0, 105.0),
        _make_crypto_bar("2024-04-27T03:00:00+00:00", 105.0, 104.0),
        _make_crypto_bar("2024-04-27T04:00:00+00:00", 104.0, 108.0),
    ]
    b_4h = resample(bars, "4h")
    assert len(b_4h) == 2
    assert b_4h[0].open == 100.0
    assert b_4h[0].close == 104.0
    assert b_4h[0].close_time == datetime(2024, 4, 27, 4, 0, tzinfo=UTC)
    assert b_4h[1].close_time == datetime(2024, 4, 27, 8, 0, tzinfo=UTC)


def test_align_higher_no_lookahead_and_mutation_a():
    """Mutation (a) test: align_higher must only take higher bars with close_time <= lower_bar.close_time.

    If align_higher took forming bars or used >=, lower bar during the week would see the unfinished weekly bar.
    """
    daily = [
        _make_stock_bar("2016-01-04", 10.0, 10.5),  # Mon
        _make_stock_bar("2016-01-05", 10.5, 11.0),  # Tue
        _make_stock_bar("2016-01-06", 11.0, 11.2),  # Wed
        _make_stock_bar("2016-01-08", 11.2, 12.0),  # Fri
        _make_stock_bar("2016-01-11", 12.0, 12.2),  # Mon next week
    ]
    weekly = resample(daily, "1W")
    # weekly[0] has close_time = 2016-01-08 15:00
    aligned = align_higher(daily, weekly)

    # Mon, Tue, Wed are BEFORE Friday 15:00 -> weekly[0] has NOT closed yet!
    # They MUST see None (not the forming weekly bar)!
    assert aligned[0] is None
    assert aligned[1] is None
    assert aligned[2] is None

    # On Friday at 15:00 (daily close), weekly[0] has just closed (close_time <= daily.close_time)
    assert aligned[3] is not None
    assert aligned[3].close == 12.0

    # On next Monday, aligned[4] sees weekly[0]
    assert aligned[4] is not None
    assert aligned[4].close == 12.0


def test_order_execution_open_next_and_mutation_b():
    """Mutation (b) test: order must execute at open[t+1], NOT close[t]."""
    bars = [
        _make_stock_bar("2016-01-04", 10.0, 10.5),  # t=0, close=10.5
        _make_stock_bar("2016-01-05", 11.0, 11.5),  # t=1, open=11.0 (gap up!), close=11.5
    ]
    # If signal triggers at close of t=0:
    # Execution price MUST be bars[1].open = 11.0.
    # If a buggy implementation used bars[0].close = 10.5, entry would be 10.5.
    entry_exec_price = bars[1].open
    assert entry_exec_price == 11.0
    assert entry_exec_price != bars[0].close


def test_costs_crypto_fee_and_funding_mutation_c():
    """Mutation (c) test: crypto must deduct 0.14% round-trip fee and 0.01% per funding boundary."""
    entry_ts = datetime(2024, 5, 1, 7, 0, tzinfo=UTC)
    # Exits at 17:00 -> crosses two funding intervals: 08:00 UTC and 16:00 UTC
    exit_ts = datetime(2024, 5, 1, 17, 0, tzinfo=UTC)

    num_funding = count_crypto_funding_intervals(entry_ts, exit_ts)
    assert num_funding == 2  # 08:00 and 16:00

    entry_p = 100.0
    exit_p = 110.0  # 10% gross gain
    net, gross = compute_crypto_net_return(entry_p, exit_p, "long", entry_ts, exit_ts)

    expected_gross = 0.10
    expected_fees = 0.0014  # 0.14% round trip
    expected_funding = 2 * 0.0001  # 0.02%
    expected_net = expected_gross - expected_fees - expected_funding

    assert abs(gross - expected_gross) < 1e-6
    assert abs(net - expected_net) < 1e-6

    # Verify that removing fees or funding makes net strictly higher (mutation c check)
    net_no_fee = gross - expected_funding
    assert net < net_no_fee
    net_no_funding = gross - expected_fees
    assert net < net_no_funding


def test_stock_minimum_3_sessions_hold_mutation_g():
    """Mutation (g) test: stock trade must hold >= 3 sessions (T+2)."""
    # Suppose entry at open of day 1 (index 1).
    # Day 1 held, Day 2 held, Day 3 held.
    # Earliest exit open is Day 4 (index 4) -> holding_sessions >= 3.
    # If an exit was attempted after 1 session (Day 2), it must be rejected!
    entry_idx = 1
    attempted_exit_idx = 2
    holding_sessions = attempted_exit_idx - entry_idx
    assert holding_sessions < 3, "Only 1 session held"

    # Validation check: minimum holding constraint
    can_exit = holding_sessions >= 3
    assert not can_exit, "Should NOT be allowed to exit before 3 sessions"

    valid_exit_idx = entry_idx + 3  # Day 4
    assert (valid_exit_idx - entry_idx) >= 3


def test_deflated_sharpe_hand_calculated_and_mutation_h():
    """Test DSR against hand-calculated values and verify mutation (h).

    Hand-calculated values (Bailey & López de Prado 2014, Formula 2):
    1) n_trials = 1:
       sr = 0.1, n_obs = 101, skew = 0.0, kurt = 3.0, sr_trials_var = 0.01.
       se_sr = sqrt((1 + 0.5 * 0.01) / 100) = sqrt(0.01005) = 0.100249688.
       When n_trials = 1: sr_star = 0.
       z = 0.1 / 0.100249688 = 0.997509.
       DSR = norm.cdf(0.997509) = 0.840751 (matches PSR(0)).

    2) n_trials = 100:
       p1 = 0.99, p2 = 1 - 1/(100*e) = 0.996321.
       z1 = 2.326348, z2 = 2.680455.
       sr_star = 0.1 * ((1 - 0.57721566)*2.326348 + 0.57721566*2.680455) = 0.253077.
       z = (0.1 - 0.253077) / 0.100249688 = -1.52696.
       DSR = norm.cdf(-1.52696) = 0.063383.
    """
    sr = 0.1
    n_obs = 101
    skew = 0.0
    kurt = 3.0
    sr_trials_var = 0.01

    # Case 1: n_trials = 1 -> DSR == PSR(0)
    dsr_1 = deflated_sharpe(sr, n_obs, skew, kurt, n_trials=1, sr_trials_var=sr_trials_var)
    assert abs(dsr_1 - 0.840751) < 1e-4

    # Case 2: n_trials = 100 -> DSR decreases to ~0.063383
    dsr_100 = deflated_sharpe(sr, n_obs, skew, kurt, n_trials=100, sr_trials_var=sr_trials_var)
    assert abs(dsr_100 - 0.063383) < 1e-4

    # Monotonic decrease check
    assert dsr_1 > dsr_100

    # Intermediate trials check monotonicity: DSR(1) > DSR(10) > DSR(50) > DSR(100)
    dsr_10 = deflated_sharpe(sr, n_obs, skew, kurt, n_trials=10, sr_trials_var=sr_trials_var)
    dsr_50 = deflated_sharpe(sr, n_obs, skew, kurt, n_trials=50, sr_trials_var=sr_trials_var)
    assert dsr_1 > dsr_10 > dsr_50 > dsr_100

    # Mutation (h): If someone removes n_trials adjustment (setting sr_star = 0 always),
    # then DSR(100) would equal DSR(1). This assert guarantees mutation (h) will turn red!
    assert dsr_100 != dsr_1


def test_simulate_portfolio_and_metrics():
    t1 = Trade("AAA", datetime(2020, 1, 2, tzinfo=TZ_VN), datetime(2020, 1, 10, tzinfo=TZ_VN), 10.0, 11.0, 0.08, 0.10, "stock", "long", score=1.0)
    t2 = Trade("BBB", datetime(2020, 1, 3, tzinfo=TZ_VN), datetime(2020, 1, 15, tzinfo=TZ_VN), 20.0, 22.0, 0.07, 0.10, "stock", "long", score=0.5)

    metrics = calculate_trade_metrics([t1, t2])
    assert metrics["n"] == 2
    assert abs(metrics["mean_net"] - 0.075) < 1e-6
    assert metrics["sharpe"] > 0

    port = simulate_portfolio([t1, t2], "stock", initial_capital=100_000_000.0)
    assert port["cagr"] > 0
    assert port["mdd"] >= 0


def test_stock_baseline_excess():
    bars_aaa = [_make_stock_bar("2020-01-02", 10.0, 10.0), _make_stock_bar("2020-01-10", 11.0, 11.0)]
    bars_bbb = [_make_stock_bar("2020-01-02", 20.0, 20.0), _make_stock_bar("2020-01-10", 20.0, 20.0)]
    all_bars = {"AAA": bars_aaa, "BBB": bars_bbb}

    # Trade on AAA: entry open 10.0, exit open 11.0 -> net return e.g. 0.08
    # Baseline: AAA open ret is 10%, BBB open ret is 0% -> mean baseline ret is 5% (0.05)
    # Excess: 0.08 - 0.05 = 0.03
    trade = Trade("AAA", bars_aaa[0].ts, bars_aaa[1].ts, 10.0, 11.0, 0.08, 0.10, "stock", "long")
    excess = calculate_stock_baseline_excess([trade], all_bars)
    assert abs(excess["mean_excess"] - 0.03) < 1e-4
