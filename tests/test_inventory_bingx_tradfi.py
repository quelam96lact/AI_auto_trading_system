"""Unit tests for BingX TradFi inventory analysis pure functions (Brief 114).

Covers:
1. Hourly profile matrix (7x24 UTC table).
2. Schedule classification (24/7, 24/5, session-based).
3. 1h to 1d aggregation (open, high, low, close of last bar, volume sum).
4. Comparison of aggregated 1h vs 1d (detecting >0.1% divergence).
5. Normal vs abnormal gap detection using the schedule profile.
6. Cost to ATR ratio calculation (median ATR14%, round-trip fee, ratio).
7. Funding rate history analysis (settlement cycle, mean, mean absolute rate).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from scripts.inventory_bingx_tradfi import (
    aggregate_1h_to_daily,
    analyze_funding_history,
    build_hourly_profile_matrix,
    calculate_cost_to_atr_ratio,
    classify_trading_schedule,
    compare_1h_aggregated_with_1d,
    count_dirty_and_zero_volume_bars,
    detect_gaps,
)


def _make_bar(dt: datetime, open_p: float, high_p: float, low_p: float, close_p: float, vol: float) -> dict:
    return {
        "ts": dt,
        "open": open_p,
        "high": high_p,
        "low": low_p,
        "close": close_p,
        "volume": vol,
    }


# ---------------------------------------------------------------------------
# 1. 7x24 Matrix and Schedule Classification
# ---------------------------------------------------------------------------

def test_build_hourly_profile_matrix():
    """Verify 7x24 matrix accumulates counts correctly by UTC weekday and hour."""
    # Monday = 0, Tuesday = 1, etc.
    dt1 = datetime(2026, 8, 3, 14, 0, tzinfo=UTC)  # 2026-08-03 is Monday, hour 14
    dt2 = datetime(2026, 8, 3, 14, 0, tzinfo=UTC)  # duplicate slot
    dt3 = datetime(2026, 8, 9, 23, 0, tzinfo=UTC)  # 2026-08-09 is Sunday (6), hour 23

    bars = [
        _make_bar(dt1, 100, 101, 99, 100, 10),
        _make_bar(dt2, 100, 101, 99, 100, 10),
        _make_bar(dt3, 100, 101, 99, 100, 10),
    ]

    matrix = build_hourly_profile_matrix(bars)
    assert len(matrix) == 7
    assert all(len(row) == 24 for row in matrix)

    # Monday (0) hour 14 has 2 bars
    assert matrix[0][14] == 2
    # Sunday (6) hour 23 has 1 bar
    assert matrix[6][23] == 1
    # Tuesday (1) hour 0 has 0 bars
    assert matrix[1][0] == 0


def test_classify_trading_schedule():
    """Verify classification into 24/7, 24/5, or session-based."""
    # 1. 24/7: all 7 days and 24 hours have bars
    matrix_24_7 = [[10] * 24 for _ in range(7)]
    assert classify_trading_schedule(matrix_24_7) == "24/7 (Liên tục)"

    # 2. 24/5: Mon-Fri have 24 hours active, Sat-Sun have 0
    matrix_24_5 = [[10] * 24 for _ in range(5)] + [[0] * 24, [0] * 24]
    assert classify_trading_schedule(matrix_24_5) == "24/5 (Toàn bộ ngày thường)"

    # 3. Session-based: Mon-Fri active only 7 hours a day (e.g. US equities)
    matrix_session = [[0] * 24 for _ in range(7)]
    for d in range(5):
        for h in range(13, 20):  # 7 hours
            matrix_session[d][h] = 10
    assert "Phiên sở" in classify_trading_schedule(matrix_session)


# ---------------------------------------------------------------------------
# 2. 1h to 1d Aggregation & Comparison
# ---------------------------------------------------------------------------

def test_aggregate_1h_to_daily():
    """Verify 1h bars are aggregated into 1d OHLCV with close taken from LAST bar."""
    day1 = datetime(2026, 8, 3, 0, 0, tzinfo=UTC)
    bars = [
        # Bar 1 (00:00 UTC)
        _make_bar(day1, open_p=100.0, high_p=105.0, low_p=98.0, close_p=102.0, vol=10.0),
        # Bar 2 (01:00 UTC)
        _make_bar(day1 + timedelta(hours=1), open_p=102.0, high_p=112.0, low_p=101.0, close_p=108.0, vol=20.0),
        # Bar 3 (02:00 UTC)
        _make_bar(day1 + timedelta(hours=2), open_p=108.0, high_p=109.0, low_p=95.0, close_p=97.0, vol=15.0),
    ]

    agg = aggregate_1h_to_daily(bars)
    d = date(2026, 8, 3)
    assert d in agg

    day_res = agg[d]
    # Hand-calculated values:
    # open = first bar's open = 100.0
    assert day_res["open"] == 100.0
    # high = max(105, 112, 109) = 112.0
    assert day_res["high"] == 112.0
    # low = min(98, 101, 95) = 95.0
    assert day_res["low"] == 95.0
    # close = LAST bar's close = 97.0 (CRITICAL for mutation test: not 102.0!)
    assert day_res["close"] == 97.0
    # volume = 10 + 20 + 15 = 45.0
    assert day_res["volume"] == 45.0
    assert day_res["count_1h"] == 3


def test_compare_1h_aggregated_with_1d():
    """Verify comparison detects divergences greater than threshold (0.1%)."""
    d1 = date(2026, 8, 3)
    d2 = date(2026, 8, 4)

    agg = {
        d1: {"open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 100},
        d2: {"open": 105.0, "high": 115.0, "low": 100.0, "close": 110.0, "volume": 100},
    }

    bars_1d = [
        # d1 matches closely (close diff 0.05% < 0.1%)
        {"ts": datetime(2026, 8, 3, 0, 0, tzinfo=UTC), "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.05},
        # d2 diverges significantly (close 115 vs 110 -> 4.5% > 0.1%)
        {"ts": datetime(2026, 8, 4, 0, 0, tzinfo=UTC), "open": 105.0, "high": 115.0, "low": 100.0, "close": 115.0},
    ]

    mismatches = compare_1h_aggregated_with_1d(agg, bars_1d, threshold=0.001)
    assert len(mismatches) == 1
    assert mismatches[0]["date"] == d2
    assert "close" in mismatches[0]["diff_fields"]


# ---------------------------------------------------------------------------
# 3. Gap Detection (Normal vs Abnormal)
# ---------------------------------------------------------------------------

def test_detect_gaps_normal_vs_abnormal():
    """Verify gaps falling on normally closed slots are not flagged as abnormal."""
    # Mon-Fri active (10 bars each), Sat-Sun closed (0 bars)
    matrix_24_5 = [[10] * 24 for _ in range(5)] + [[0] * 24, [0] * 24]

    # Friday 23:00 to Monday 00:00 (weekend gap of 49h): NORMAL
    fri_night = datetime(2026, 8, 7, 23, 0, tzinfo=UTC)  # Friday 23:00
    mon_morn = datetime(2026, 8, 10, 0, 0, tzinfo=UTC)   # Monday 00:00
    mon_01 = datetime(2026, 8, 10, 1, 0, tzinfo=UTC)     # Monday 01:00 (continuous)
    # Monday 01:00 to Monday 05:00 (gap of 4h on Monday!): ABNORMAL
    mon_05 = datetime(2026, 8, 10, 5, 0, tzinfo=UTC)     # Monday 05:00

    bars = [
        _make_bar(fri_night, 100, 101, 99, 100, 10),
        _make_bar(mon_morn, 100, 101, 99, 100, 10),
        _make_bar(mon_01, 100, 101, 99, 100, 10),
        _make_bar(mon_05, 100, 101, 99, 100, 10),
    ]

    abnormal_count, top_gaps = detect_gaps(bars, interval="1h", matrix_7x24=matrix_24_5)
    # The weekend gap should NOT be in abnormal_count
    # The Monday 4-hour gap MUST be flagged as abnormal
    assert abnormal_count == 1
    assert len(top_gaps) == 1
    assert top_gaps[0]["gap_hours"] == 4.0
    assert top_gaps[0]["from_ts"] == mon_01


# ---------------------------------------------------------------------------
# 4. Cost to ATR Ratio
# ---------------------------------------------------------------------------

def test_calculate_cost_to_atr_ratio():
    """Verify median ATR14% and fee/ATR ratio calculation."""
    # Construct 20 bars with steady ATR
    base_time = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    bars = []
    # Each bar has High=101, Low=99, Close=100 -> TR = 2.0. Price = 100. TR% = 2.0%
    for i in range(25):
        bars.append(_make_bar(base_time + timedelta(hours=i), 100.0, 101.0, 99.0, 100.0, 10.0))

    taker_fee_rate = 0.0005  # 0.05% -> round trip = 0.10% (0.001)
    median_atr_pct, round_trip_fee_pct, fee_to_atr_ratio = calculate_cost_to_atr_ratio(bars, taker_fee_rate)

    # Hand calculations:
    # TR for every bar after bar 0 is max(2.0, |101 - 100|, |99 - 100|) = 2.0
    # ATR14 = 2.0
    # ATR% = 2.0 / 100.0 * 100% = 2.0%
    assert round(median_atr_pct, 4) == 2.0000
    # round_trip_fee_pct = 2 * 0.0005 * 100% = 0.10%
    assert round(round_trip_fee_pct, 4) == 0.1000
    # fee_to_atr_ratio = 0.10 / 2.0 = 0.05 (5.0%)
    assert round(fee_to_atr_ratio, 4) == 0.0500


# ---------------------------------------------------------------------------
# 5. Funding History Analysis
# ---------------------------------------------------------------------------

def test_analyze_funding_history():
    """Verify funding cycle interval and average rates calculation."""
    t0 = datetime(2026, 8, 1, 16, 0, tzinfo=UTC)
    t1 = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    t2 = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)

    records = [
        {"fundingTime": int(t0.timestamp() * 1000), "fundingRate": "0.00010"},
        {"fundingTime": int(t1.timestamp() * 1000), "fundingRate": "-0.00005"},
        {"fundingTime": int(t2.timestamp() * 1000), "fundingRate": "0.00015"},
    ]

    analysis = analyze_funding_history(records)
    assert analysis["count"] == 3
    # Consecutive intervals are 4 hours each
    assert analysis["interval_hours"] == 4.0
    # Mean rate = (0.00010 - 0.00005 + 0.00015) / 3 = 0.00020 / 3 = 0.0000667
    assert round(analysis["mean_rate"], 7) == round(0.00020 / 3, 7)
    # Mean abs rate = (0.00010 + 0.00005 + 0.00015) / 3 = 0.00030 / 3 = 0.0001000
    assert round(analysis["mean_abs_rate"], 7) == 0.0001000


def test_count_dirty_and_zero_volume_bars():
    """Verify dirty bars (<=0) and zero volume bars are properly counted."""
    t0 = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    bars = [
        # Normal bar
        _make_bar(t0, open_p=100.0, high_p=105.0, low_p=98.0, close_p=102.0, vol=10.0),
        # Dirty bar (low <= 0)
        _make_bar(t0 + timedelta(hours=1), open_p=100.0, high_p=105.0, low_p=0.0, close_p=102.0, vol=10.0),
        # Zero volume bar
        _make_bar(t0 + timedelta(hours=2), open_p=100.0, high_p=105.0, low_p=98.0, close_p=102.0, vol=0.0),
        # Dirty AND zero volume bar
        _make_bar(t0 + timedelta(hours=3), open_p=-1.0, high_p=105.0, low_p=98.0, close_p=102.0, vol=0.0),
    ]

    dirty_count, zero_vol_count = count_dirty_and_zero_volume_bars(bars)
    assert dirty_count == 2  # bar index 1 and 3
    assert zero_vol_count == 2  # bar index 2 and 3

