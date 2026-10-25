"""Unit tests for scripts/research193_core.py and scripts/research193_explore.py.

Includes:
- Hand-calculated test for simulate_rotation (3 symbols, 3 rebalance dates, 1 replacement).
- Hand-calculated test for ew_benchmark (3 symbols, 2 months).
- 10 mutation tests (a)–(j) calling the exact product functions in Brief 193 §4.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from scripts.research188_core import deflated_sharpe
from scripts.research191_data import StockDailyBar
from scripts.research193_core import (
    MIN_TURNOVER_193,
    compute_lowmax_score,
    ew_benchmark,
    score_and_rank_symbols,
    simulate_rotation,
)
from scripts.research193_explore import compute_step4_dsr, run_exploration


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


# ==============================================================================
# 1. Hand-Calculated Tests for simulate_rotation and ew_benchmark (§4)
# ==============================================================================


def test_simulate_rotation_hand_calculated():
    """Verify simulate_rotation on 3 symbols, 3 rebalance dates, 1 stock replacement (§4).

    Hand calculation breakdown:
    - Initial capital = 100,000,000 VND, N = 2.
    - Buy cost factor = 1 + 0.0028 + 0.0005 = 1.0033 (fee = 0.0033).
    - Sell return factor = 1 - 0.0028 - 0.001 - 0.0005 = 0.9957 (fee = 0.0043).

    Rebalance r0:
      NAV_pre = 100,000,000 VND. Target value per stock = 50,000,000 VND.
      Selected: A and B (scores A < B < C). Price A=100, B=100.
      Buy A: target 50M -> cash deducted = 50M * 1.0033 = 50,165,000 VND. Shares A = 500,000.
      Buy B: cash left = 49,835,000 VND -> buy val = 49,835,000 / 1.0033 = 49,671,085.418120 VND.
             Shares B = 496,710.854181202. Fee B = 163,914.581880 VND.
      Total fees r0 = 165,000 + 163,914.581880 = 328,914.581880 VND.
      NAV_post(r0) = 100M - 328,914.581880 = 99,671,085.418120 VND.
      Turnover r0 = 99,671,085.418120 / 100M = 0.996710854.

    Rebalance r1:
      Price A=100, Price B=110 (+10%), Price C=100.
      Value A = 50,000,000 VND. Value B = 496,710.854181202 * 110 = 54,638,193.959932 VND.
      NAV_pre = 104,638,193.959932 VND. Target per stock = 52,319,096.979966 VND.
      Selected: A and C (B is dropped!).
      SELL B: all shares -> cash added = 54,638,193.959932 * 0.9957 = 54,403,249.725905 VND.
              Fee sell B = 54,638,193.959932 * 0.0043 = 234,944.234028 VND.
      BUY A: top-up 2,319,096.979966 VND -> cash deducted = 2,326,750.00 VND.
             Shares A += 23,190.969800. Fee A = 7,653.020034 VND.
             Cash left = 54,403,249.725905 - 2,326,750 = 52,076,499.725905 VND.
      BUY C: cash left 52,076,499.725905 -> buy val = 52,076,499.725905 / 1.0033 = 51,905,212.524573 VND.
             Shares C = 519,052.125246. Fee C = 171,287.201331 VND.
      Total fees r1 = 234,944.234028 + 7,653.020034 + 171,287.201331 = 413,884.455393 VND.
      NAV_post(r1) = NAV_pre - fees = 104,638,193.959932 - 413,884.455393 = 104,224,309.504540 VND.
      Turnover r1 = (54,638,193.959932 + 2,319,096.979966 + 51,905,212.524573) / NAV_pre
                  = 108,862,503.464472 / 104,638,193.959932 = 1.04037063.

    Rebalance r2 (Final close-out):
      Price A=100, Price C=100.
      Liquidate A: 523,190.9697996611 * 100 * 0.9957 = 52,094,124.862952 VND.
      Liquidate C: 519,052.1252457342 * 100 * 0.9957 = 51,682,020.110718 VND.
      Final NAV (cash) = 52,094,124.862952 + 51,682,020.110718 = 103,776,144.973670 VND.
      Total fees r2 = 104,224,309.504540 * 0.0043 = 448,164.530869 VND.

    Cumulative fees = 328,914.581880 + 413,884.455393 + 448,164.530869 = 1,190,963.568142 VND.
    """
    # 25 calendar days so L >= 2 is satisfied
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(25)]
    r0 = sessions[20]
    r1 = sessions[22]
    r2 = sessions[24]
    rebalance_dates = [r0, r1, r2]

    # Prices
    price_map_a = {s: 100.0 for s in sessions}
    price_map_b = {s: 100.0 for s in sessions}
    price_map_b[r1] = 110.0
    price_map_b[sessions[23]] = 110.0
    price_map_b[r2] = 110.0

    price_map_c = {s: 100.0 for s in sessions}

    # Scores: A has lowest vol, B has low vol at r0, C has lower vol than B at r1
    # We construct bars with volume 20M @ 100 = 2B VND (>= 1B)
    bars_a = _make_dummy_bars("A", sessions, price_map=price_map_a)
    bars_b = _make_dummy_bars("B", sessions, price_map=price_map_b)
    bars_c = _make_dummy_bars("C", sessions, price_map=price_map_c)

    # Induce scores at r0: A (std=0.001) < B (std=0.002) < C (std=0.010)
    # At r1: A (std=0.001) < C (std=0.002) < B (std=0.050)
    bars_a[19].close = 100.1
    bars_b[19].close = 100.2
    bars_c[19].close = 101.0

    bars_b[21].close = 105.0  # B has high volatility at r1^-
    bars_c[21].close = 100.2

    bars_by_symbol = {"A": bars_a, "B": bars_b, "C": bars_c}
    exchanges = {"A": "HOSE", "B": "HOSE", "C": "HOSE"}

    res = simulate_rotation(
        rebalance_dates=rebalance_dates,
        bars_by_symbol=bars_by_symbol,
        sessions=sessions,
        exchanges=exchanges,
        idea_type="LOWVOL",
        lookback=2,
        n_stocks=2,
    )

    expected_final_nav = 103_776_144.973670
    expected_total_fees = 1_190_963.568142

    assert np.isclose(res["final_nav"], expected_final_nav, atol=1e-2)
    assert np.isclose(res["total_fees"], expected_total_fees, atol=1e-2)
    assert len(res["monthly_returns"]) == 2


def test_ew_benchmark_hand_calculated():
    """Verify ew_benchmark on 3 symbols, 2 months (§4).

    Month 1 (r0 -> r1):
      Ret A = 100/100 - 1 = 0.0
      Ret B = 110/100 - 1 = +0.10
      Ret C = 105/100 - 1 = +0.05
      EW1 = (0.0 + 0.10 + 0.05) / 3 = 0.05 (5.0%)

    Month 2 (r1 -> r2):
      Ret A = 100/100 - 1 = 0.0
      Ret B = 121/110 - 1 = +0.10
      Ret C = 105/105 - 1 = 0.0
      EW2 = (0.0 + 0.10 + 0.0) / 3 = 0.03333333 (3.333%)
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(25)]
    r0 = sessions[20]
    r1 = sessions[22]
    r2 = sessions[24]
    rebalance_dates = [r0, r1, r2]

    price_map_a = {s: 100.0 for s in sessions}
    price_map_b = {s: 100.0 for s in sessions}
    price_map_b[r1] = 110.0
    price_map_b[sessions[23]] = 110.0
    price_map_b[r2] = 121.0

    price_map_c = {s: 100.0 for s in sessions}
    price_map_c[r1] = 105.0
    price_map_c[sessions[23]] = 105.0
    price_map_c[r2] = 105.0

    bars_a = _make_dummy_bars("A", sessions, price_map=price_map_a)
    bars_b = _make_dummy_bars("B", sessions, price_map=price_map_b)
    bars_c = _make_dummy_bars("C", sessions, price_map=price_map_c)

    bars_by_symbol = {"A": bars_a, "B": bars_b, "C": bars_c}

    ew_rets = ew_benchmark(
        rebalance_dates=rebalance_dates,
        bars_by_symbol=bars_by_symbol,
        sessions=sessions,
        min_turnover=MIN_TURNOVER_193,
    )

    assert len(ew_rets) == 2
    assert np.isclose(ew_rets[0], 0.05, atol=1e-6)
    assert np.isclose(ew_rets[1], 0.10 / 3.0, atol=1e-6)


# ==============================================================================
# 2. Ten Mutation Tests (a)–(j) from Brief 193 §4
# ==============================================================================


def test_mutation_a_ranking_score_evaluates_up_to_r_minus_not_r():
    """Mutation (a): Điểm xếp hạng tính tới hết r thay vì r⁻.

    Product function called: score_and_rank_symbols.
    Setup:
    - Symbol A has low volatility up to r_minus (returns flat).
      On session r, symbol A has a wild swing (+30%).
    - Symbol B has slightly higher volatility up to r_minus, but flat at r.
    - If evaluated up to r_minus: A has lower volatility -> A ranked #1.
    - If mutated to evaluate up to r: A's wild swing at r makes A's vol high -> B ranked #1.
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(25)]
    r = sessions[20]

    # Symbol A: flat 100 up to r_minus (session 19), wild 130 at r (session 20)
    price_map_a = {s: 100.0 for s in sessions}
    price_map_a[r] = 130.0

    # Symbol B: slightly varied up to r_minus, flat 100 at r
    price_map_b = {s: 100.0 for s in sessions}
    price_map_b[sessions[18]] = 101.0

    bars_a = _make_dummy_bars("A", sessions, price_map=price_map_a)
    bars_b = _make_dummy_bars("B", sessions, price_map=price_map_b)

    bars_by_symbol = {"A": bars_a, "B": bars_b}

    ranked = score_and_rank_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol=bars_by_symbol,
        idea_type="LOWVOL",
        lookback=3,
        n_stocks=1,
    )
    assert ranked == ["A"], "Must evaluate up to r_minus, ignoring the swing at r"


def test_mutation_b_keeps_n_lowest_scores_not_highest():
    """Mutation (b): Giữ N mã điểm cao nhất thay vì thấp nhất.

    Product function called: score_and_rank_symbols.
    Setup:
    - Symbol A: completely flat (volatility = 0.0).
    - Symbol B: high variance (volatility >> 0.0).
    - Low-vol strategy must pick A (lowest score).
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(25)]
    r = sessions[20]

    price_map_a = {s: 100.0 for s in sessions}
    price_map_b = {sessions[i]: 100.0 + (i % 2) * 10.0 for i in range(25)}

    bars_a = _make_dummy_bars("A", sessions, price_map=price_map_a)
    bars_b = _make_dummy_bars("B", sessions, price_map=price_map_b)

    ranked = score_and_rank_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol={"A": bars_a, "B": bars_b},
        idea_type="LOWVOL",
        lookback=3,
        n_stocks=1,
    )
    assert ranked == ["A"], "Must select symbols with lowest score"


def test_mutation_c_universe_enforces_is_liquid():
    """Mutation (c): Bỏ điều kiện is_liquid của universe.

    Product function called: score_and_rank_symbols.
    Setup:
    - Symbol A has low volume (100,000 VND turnover << 1 billion VND).
    - Symbol A must be filtered out of universe and not selected.
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(25)]
    r = sessions[20]

    # Illiquid: volume = 100 shares @ 100 VND = 10,000 VND
    bars_a = _make_dummy_bars("A", sessions, volume=100.0)

    ranked = score_and_rank_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol={"A": bars_a},
        idea_type="LOWVOL",
        lookback=3,
        n_stocks=1,
    )
    assert ranked == [], "Illiquid symbol must be rejected from universe"


def test_mutation_d_cannot_buy_when_ceiling_locked():
    """Mutation (d): Mua được khi r khoá trần.

    Product function called: simulate_rotation.
    Setup:
    - Symbol A is ceiling-locked at r0 (high == low == limit_up).
    - Portfolio must NOT buy A; capital stays in cash.
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(25)]
    r0 = sessions[20]
    r1 = sessions[22]

    bars_a = _make_dummy_bars("A", sessions)
    # Lock ceiling at r0 (+7% on HOSE)
    bars_a[20].open = 107.0
    bars_a[20].high = 107.0
    bars_a[20].low = 107.0
    bars_a[20].close = 107.0

    res = simulate_rotation(
        rebalance_dates=[r0, r1],
        bars_by_symbol={"A": bars_a},
        sessions=sessions,
        exchanges={"A": "HOSE"},
        idea_type="LOWVOL",
        lookback=2,
        n_stocks=1,
    )
    assert res["avg_syms_held"] == 0.0, "Ceiling locked stock cannot be bought"


def test_mutation_e_cannot_sell_when_floor_locked():
    """Mutation (e): Bán được khi r khoá sàn.

    Product function called: simulate_rotation.
    Setup:
    - Held symbol A leaves selected list at r1, but is floor-locked at r1.
    - Portfolio must NOT sell A; retains position.
    - Subsequent session 23 has A dropping to 50.0 while B stays at 100.0.
    - If floor lock is respected: A is retained, NAV drops to ~50M.
    - If mutated (A sold despite floor lock): A sold at 93 and B bought, NAV stays ~92M.
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(25)]
    r0 = sessions[20]
    r1 = sessions[22]
    r2 = sessions[24]

    # At r0, A is bought. At r1, A is floor-locked and dropped.
    bars_a = _make_dummy_bars("A", sessions)
    # Floor lock at r1 (-7% on HOSE)
    bars_a[22].open = 93.0
    bars_a[22].high = 93.0
    bars_a[22].low = 93.0
    bars_a[22].close = 93.0

    # At session 23, A drops further to 50.0
    bars_a[23].open = 50.0
    bars_a[23].high = 50.0
    bars_a[23].low = 50.0
    bars_a[23].close = 50.0

    # Symbol B is newly selected at r1
    bars_b = _make_dummy_bars("B", sessions)
    # Make B have lower vol than A at r1
    bars_a[21].close = 105.0

    res = simulate_rotation(
        rebalance_dates=[r0, r1, r2],
        bars_by_symbol={"A": bars_a, "B": bars_b},
        sessions=sessions,
        exchanges={"A": "HOSE", "B": "HOSE"},
        idea_type="LOWVOL",
        lookback=2,
        n_stocks=1,
    )
    # At r1, A could not be sold, so position was held and suffered drop at session 23
    assert (
        res["daily_nav"][sessions[23]] < 60_000_000.0
    ), "A was held through floor lock"


def test_mutation_f_fees_charged_on_trade_value_not_nav():
    """Mutation (f): Phí tính trên NAV thay vì trên giá trị giao dịch, hoặc bỏ phí phần điều chỉnh tỷ trọng.

    Product function called: simulate_rotation.
    Verifies total fees paid against exact hand-calculated fee formula.
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(25)]
    r0 = sessions[20]
    r1 = sessions[22]
    rebalance_dates = [r0, r1]

    bars_a = _make_dummy_bars("A", sessions)
    res = simulate_rotation(
        rebalance_dates=rebalance_dates,
        bars_by_symbol={"A": bars_a},
        sessions=sessions,
        exchanges={"A": "HOSE"},
        idea_type="LOWVOL",
        lookback=2,
        n_stocks=1,
    )

    # Initial buy at r0: 100M / 1.0033 = 99,671,085.418120 VND. Fee = 328,914.581880 VND.
    # Close-out sell at r1: 99,671,085.418120 * 0.0043 = 428,585.667298 VND.
    # Total fees = 757,500.249178 VND.
    # If fees were charged on NAV (0.0033 * 100M + 0.0043 * 100M = 760,000 VND), this assertion fails.
    expected_fees = 99_671_085.418120 * 0.0033 + 99_671_085.418120 * 0.0043
    assert np.isclose(res["total_fees"], expected_fees, atol=1e-3)


def test_mutation_f_trim_sell_pays_fee_in_cash():
    """Mutation (f), nhánh bán bớt: mã vẫn trong danh sách nhưng vượt tỷ trọng thì phần bán bớt phải chịu phí.

    Product function called: simulate_rotation. N = 2, chỉ có A và B nên cả hai luôn được chọn.
    r0: mua A 50.000.000, mua B bằng tiền còn lại 49.835.000 / 1,0033 = 49.671.085,4181.
    r1: A lên 150 → giá trị A 75.000.000, B 49.671.085,4181, NAV 124.671.085,4181, mục tiêu 62.335.542,7091.
        Bán bớt A 12.664.457,2909 → tiền vào × 0,9957; mua bù B bằng toàn bộ tiền đó / 1,0033.
    r2: bán hết, × 0,9957.
    Nếu phần bán bớt không bị trừ phí trong tiền mặt, B được mua nhiều hơn và NAV cuối lệch khoảng 54 nghìn.
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(25)]
    r0, r1, r2 = sessions[20], sessions[22], sessions[24]

    price_map_a = {s: (150.0 if i >= 21 else 100.0) for i, s in enumerate(sessions)}
    bars_a = _make_dummy_bars("A", sessions, price_map=price_map_a)
    bars_a[21].high = (
        151.0  # phiên tăng giá không khoá trần, và không phải phiên xoay vòng
    )
    bars_b = _make_dummy_bars("B", sessions)

    res = simulate_rotation(
        rebalance_dates=[r0, r1, r2],
        bars_by_symbol={"A": bars_a, "B": bars_b},
        sessions=sessions,
        exchanges={"A": "HOSE", "B": "HOSE"},
        idea_type="LOWVOL",
        lookback=2,
        n_stocks=2,
    )

    val_b0 = (100_000_000.0 - 50_000_000.0 * 1.0033) / 1.0033
    nav_pre_r1 = 75_000_000.0 + val_b0
    target = nav_pre_r1 / 2
    trim = 75_000_000.0 - target
    bought_b = trim * 0.9957 / 1.0033
    expected_final = (target + val_b0 + bought_b) * 0.9957
    expected_fees = (
        50_000_000.0 * 0.0033
        + val_b0 * 0.0033
        + trim * 0.0043
        + bought_b * 0.0033
        + (target + val_b0 + bought_b) * 0.0043
    )
    assert np.isclose(res["final_nav"], expected_final, atol=1e-2)
    assert np.isclose(res["total_fees"], expected_fees, atol=1e-2)


def test_mutation_g_mdd_calculated_on_daily_nav_not_monthly():
    """Mutation (g): MDD tính trên NAV tháng thay vì NAV ngày.

    Product function called: simulate_rotation.
    Setup:
    - Between r0 and r1, price plunges by 20% on mid-month session, then recovers to 100% by r1.
    - Monthly NAV at r0 and r1 is unchanged (MDD monthly = 0%).
    - Daily NAV experiences 20% drawdown (MDD daily >= 19%).
    """
    start_d = date(2020, 1, 1)
    sessions = [start_d + timedelta(days=i) for i in range(25)]
    r0 = sessions[20]
    r1 = sessions[24]

    price_map = {s: 100.0 for s in sessions}
    # Mid-month plunge at session 22
    price_map[sessions[22]] = 80.0

    bars_a = _make_dummy_bars("A", sessions, price_map=price_map)
    res = simulate_rotation(
        rebalance_dates=[r0, r1],
        bars_by_symbol={"A": bars_a},
        sessions=sessions,
        exchanges={"A": "HOSE"},
        idea_type="LOWVOL",
        lookback=2,
        n_stocks=1,
    )
    assert res["mdd"] >= 0.19, "MDD must capture daily intra-month plunge"


def test_mutation_h_lowmax_computes_mean_of_top_3_not_top_1():
    """Mutation (h): LOWMAX lấy 1 lợi nhuận lớn nhất thay vì trung bình 3.

    Product function called: compute_lowmax_score.
    """
    rets = [0.07, 0.05, 0.03, 0.01, -0.02, -0.05]
    score = compute_lowmax_score(rets)
    # Top 3 are 0.07, 0.05, 0.03. Mean = 0.05.
    # If mutated to top 1, score = 0.07.
    assert np.isclose(
        score, 0.05, atol=1e-6
    ), "LOWMAX score must be the mean of top 3 returns"


def test_mutation_i_exploration_asserts_ledger_safety(tmp_path: Path):
    """Mutation (i): run_exploration xoá sổ cũ hoặc bỏ assert_ledger_safety.

    Product function called: run_exploration with ledger_path in tmp_path.
    If ledger exists, run_exploration must raise SystemExit at line 1.
    """
    existing_ledger = tmp_path / "trial_ledger.csv"
    existing_ledger.write_text("existing ledger\n")

    with pytest.raises(
        SystemExit, match="đã tồn tại; sổ thử không được xoá để chạy lại"
    ):
        run_exploration(
            data_dir=tmp_path,
            ledger_path=existing_ledger,
            candidates_path=tmp_path / "candidates.json",
            report_path=tmp_path / "exploration_report.md",
        )


def test_mutation_j_step4_dsr_includes_plus_25_trials():
    """Mutation (j): Bước 4 dùng n_trials thiếu + 25, hoặc gọi deflated_sharpe sai tham số.

    Product function called: compute_step4_dsr from research193_explore.py.
    Compares compute_step4_dsr against direct call to deflated_sharpe with n_trials = 18 + 25.
    """
    ea_sharpes = [0.1 * i for i in range(18)]
    sharpe_x = 0.5
    n_months = 35
    skew = -0.2
    kurt = 3.5

    # Direct reference call
    ref_n_trials = 18 + 25  # 43
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

    assert np.isclose(
        dsr_prod, ref_dsr, atol=1e-6
    ), "Step 4 DSR must use n_trials = len(ea_sharpes) + 25"
