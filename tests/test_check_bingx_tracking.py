"""Unit tests for BingX tracking quality and basis pure functions (Brief 115).

Tests:
1. compute_basis_stats: median, P5, P95, max |basis|, count > 1%.
2. compute_pearson_correlation: exact hand-calculated correlation.
3. compute_tracking_error_annualized: sample stdev * sqrt(252).
4. align_series_and_evaluate: date matching and metrics calculation.
5. compare_date_alignments: identifying whether shift 0 or shifted alignment has higher correlation.
"""

from __future__ import annotations

import math
from datetime import date

from scripts.check_bingx_tracking import (
    align_series_and_evaluate,
    compare_date_alignments,
    compute_basis_stats,
    compute_daily_returns,
    compute_pearson_correlation,
    compute_tracking_error_annualized,
)


def test_compute_basis_stats():
    """Verify basis calculation with exact hand-calculated values."""
    ext = [100.0, 100.0, 100.0, 100.0, 100.0]
    bingx = [101.0, 99.0, 100.5, 102.0, 98.0]
    # basis: [+0.01, -0.01, +0.005, +0.02, -0.02]
    # sorted: [-0.02, -0.01, 0.005, 0.01, 0.02]
    stats = compute_basis_stats(bingx, ext)
    assert round(stats["median_basis"], 5) == 0.00500
    assert round(stats["max_abs_basis"], 5) == 0.02000
    # count where |basis| > 0.01: only 0.02 and -0.02 strictly > 0.01
    assert stats["count_basis_gt_1pct"] == 2
    assert round(stats["pct_basis_gt_1pct"], 1) == 40.0


def test_compute_daily_returns_and_correlation():
    """Verify daily return calculation and Pearson correlation."""
    prices1 = [100.0, 102.0, 101.0, 104.0]
    prices2 = [50.0, 51.0, 50.5, 52.0]
    # returns1: [2/100, -1/102, 3/101] = [0.02, -0.009804, 0.029703]
    # returns2: [1/50, -0.5/51, 1.5/50.5] = [0.02, -0.009804, 0.029703]
    r1 = compute_daily_returns(prices1)
    r2 = compute_daily_returns(prices2)
    assert len(r1) == 3
    assert len(r2) == 3
    corr = compute_pearson_correlation(r1, r2)
    assert round(corr, 5) == 1.00000

    # Inverted returns -> corr = -1.0
    r_inv = [-val for val in r1]
    corr_inv = compute_pearson_correlation(r1, r_inv)
    assert round(corr_inv, 5) == -1.00000


def test_compute_tracking_error_annualized():
    """Verify tracking error formula: sample_stdev(r_bingx - r_ext) * sqrt(252)."""
    # Suppose diffs between daily returns are: [0.01, -0.01, 0.01, -0.01]
    # r_ext = [0.0, 0.0, 0.0, 0.0]
    # r_bingx = [0.01, -0.01, 0.01, -0.01]
    r_ext = [0.0, 0.0, 0.0, 0.0]
    r_bingx = [0.01, -0.01, 0.01, -0.01]
    te = compute_tracking_error_annualized(r_bingx, r_ext, annual_factor=252.0)
    # Hand calculation:
    # diffs = [0.01, -0.01, 0.01, -0.01], mean = 0.0
    # sum of squares = 4 * 0.0001 = 0.0004
    # sample variance = 0.0004 / (4 - 1) = 0.0004 / 3 = 0.0001333333
    # sample stdev = sqrt(0.0001333333) = 0.011547005
    # annualized = 0.011547005 * sqrt(252) = 0.011547005 * 15.874507866 = 0.183303
    expected_te = math.sqrt(0.0004 / 3.0) * math.sqrt(252.0)
    assert round(te, 5) == round(expected_te, 5)


def test_align_series_and_evaluate():
    """Verify series alignment and metrics evaluation on matched dates."""
    d1 = date(2026, 8, 3)
    d2 = date(2026, 8, 4)
    d3 = date(2026, 8, 5)

    bingx = {d1: 100.0, d2: 102.0, d3: 104.0}
    ext = {d1: 100.0, d2: 102.0, d3: 104.0}

    res = align_series_and_evaluate(bingx, ext, shift_days=0)
    assert res["matched_count"] == 3
    assert round(res["returns_corr"], 4) == 1.0000
    assert round(res["tracking_error_annual"], 4) == 0.0000


def test_date_alignment_shift_comparison():
    """Verify date alignment correctly identifies when a shifted date gives higher correlation.

    CRITICAL for mutation test: If shift direction is inverted or ignored, this test will fail.
    """
    # Suppose external source records prices on date D,
    # but BingX's candle on date D actually matches the moves of external date D (shift=0).
    # Case A: Synced on same day
    d1 = date(2026, 8, 3)
    d2 = date(2026, 8, 4)
    d3 = date(2026, 8, 5)
    d4 = date(2026, 8, 6)

    # BingX prices
    bingx = {
        d1: 100.0,
        d2: 102.0,  # +2%
        d3: 100.0,  # -1.96%
        d4: 103.0,  # +3%
    }
    # External prices (same day synced)
    ext_synced = {
        d1: 100.0,
        d2: 102.0,
        d3: 100.0,
        d4: 103.0,
    }

    res_synced = compare_date_alignments(bingx, ext_synced)
    assert res_synced["best_shift"] == 0
    assert round(res_synced["best_corr"], 4) == 1.0000

    # Case B: External prices are lagged by +1 day (ext on D+1 has bingx D prices)
    dates_b = [date(2026, 8, d) for d in range(3, 9)]  # Aug 3 to Aug 8
    p_b = [100.0, 105.0, 102.0, 111.0, 108.0, 115.0]
    bingx_asym = dict(zip(dates_b, p_b, strict=False))

    dates_e = [date(2026, 8, d) for d in range(4, 10)]  # Aug 4 to Aug 9 (shifted +1 day)
    ext_lagged = dict(zip(dates_e, p_b, strict=False))

    # Calling align_series_and_evaluate with shift_days=1 MUST yield correlation 1.0 and TE 0.0
    res_direct_p1 = align_series_and_evaluate(bingx_asym, ext_lagged, shift_days=1)
    assert round(res_direct_p1["returns_corr"], 4) == 1.0000
    assert round(res_direct_p1["tracking_error_annual"], 4) == 0.0000

    # Best shift must be +1 (bingx date D matched with ext date D+1)
    res_lagged = compare_date_alignments(bingx_asym, ext_lagged)
    assert res_lagged["best_shift"] == 1
    assert round(res_lagged["best_corr"], 4) == 1.0000
    # While shift 0 correlation is negative (-0.95)
    assert res_lagged["shift_0_corr"] < 0.0
