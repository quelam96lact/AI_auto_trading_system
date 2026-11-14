"""Unit and mutation tests (a–m) for Brief 237 (scripts/research237_core.py,
scripts/research237_explore.py, and scripts/research193_core.simulate_rotation).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from scripts.research188_core import deflated_sharpe
from scripts.research191_data import StockDailyBar
from scripts.research193_core import simulate_rotation
from scripts.research237_core import (
    get_universe_at_r,
    select_lowattn_symbols,
)
from scripts.research237_explore import (
    ETF_EB_CAGR,
    ETF_EB_MDD,
    GRID,
    check_eb_gates,
    check_plateau,
    compute_step4_dsr,
    run_exploration,
    select_best_ea_config,
)


def _make_sessions(n_days: int, start: date = date(2019, 1, 1)) -> list[date]:
    return [start + timedelta(days=i) for i in range(n_days)]


def _make_bars(
    sym: str,
    dates: list[date],
    close_fn: Any = None,
    vol_fn: Any = None,
    default_close: float = 100.0,
    default_vol: float = 20_000_000.0,
) -> list[StockDailyBar]:
    bars: list[StockDailyBar] = []
    for idx, d in enumerate(dates):
        p = float(close_fn(idx, d)) if close_fn else default_close
        v = float(vol_fn(idx, d)) if vol_fn else default_vol
        bars.append(
            StockDailyBar(
                symbol=sym,
                date=d,
                open=p,
                high=p,
                low=p,
                close=p,
                volume=v,
            )
        )
    return bars


def _ea_entry(s_val: int, n_val: int, mean_x: float, sharpe_x: float) -> dict[str, Any]:
    return {
        "idea_id": "I1_LOWATTN",
        "params": {"S": s_val, "N": n_val},
        "period": "EA",
        "metrics": {"mean_X": mean_x, "sharpe_X": sharpe_x},
    }


def test_mutation_a_score_evaluates_up_to_r_minus_not_r():
    """Mutation (a): Điểm AT tính tới hết r thay vì r^- -> select_lowattn_symbols."""
    sessions = _make_sessions(260)
    r = sessions[255]

    # A is constant up to r^- (AT_20 = 1.0), then spikes 100x ONLY on session r (idx 255).
    bars_a = _make_bars(
        "A",
        sessions,
        vol_fn=lambda i, _d: 2_000_000_000.0 if i == 255 else 20_000_000.0,
    )
    # B has elevated recent turnover up to r^- (idx 235..254 -> AT_20 > 1.0), normal at r.
    bars_b = _make_bars(
        "B",
        sessions,
        vol_fn=lambda i, _d: 30_000_000.0 if 235 <= i <= 254 else 20_000_000.0,
    )

    ranked = select_lowattn_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol={"A": bars_a, "B": bars_b},
        s_window=20,
        n_stocks=1,
    )
    assert ranked == ["A"]


def test_mutation_b_keeps_n_lowest_at_not_highest():
    """Mutation (b): Giữ N mã AT cao nhất thay vì thấp nhất -> select_lowattn_symbols."""
    sessions = _make_sessions(260)
    r = sessions[255]

    # LOW_ATTN: high older turnover (20B), lower recent S=20 turnover (2B -> liquid) => AT < 1.
    bars_low = _make_bars(
        "LOW_ATTN",
        sessions,
        vol_fn=lambda i, _d: 20_000_000.0 if i >= 235 else 200_000_000.0,
    )
    # HIGH_ATTN: lower older turnover (2B), high recent S=20 turnover (20B) => AT > 1.
    bars_high = _make_bars(
        "HIGH_ATTN",
        sessions,
        vol_fn=lambda i, _d: 200_000_000.0 if i >= 235 else 20_000_000.0,
    )

    ranked = select_lowattn_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol={"LOW_ATTN": bars_low, "HIGH_ATTN": bars_high},
        s_window=20,
        n_stocks=1,
    )
    assert ranked == ["LOW_ATTN"]


def test_mutation_c_enforces_is_liquid():
    """Mutation (c): Bỏ is_liquid -> select_lowattn_symbols."""
    sessions = _make_sessions(260)
    r = sessions[255]

    # ILLIQ has lower AT_20, but last 20-day avg turnover = 100 * 100 = 10,000 VND << 1B.
    bars_illiq = _make_bars(
        "ILLIQ",
        sessions,
        vol_fn=lambda i, _d: 100.0 if i >= 235 else 200_000_000.0,
    )
    # LIQ has constant 2B VND turnover (liquid, AT_20 = 1.0).
    bars_liq = _make_bars("LIQ", sessions, default_vol=20_000_000.0)

    ranked = select_lowattn_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol={"ILLIQ": bars_illiq, "LIQ": bars_liq},
        s_window=20,
        n_stocks=2,
    )
    assert ranked == ["LIQ"]


def test_mutation_d_window_lengths_match_hand_calculation():
    """Mutation (d): Sai cửa sổ tử số S hoặc mẫu số 250 -> select_lowattn_symbols + AT tính tay."""
    sessions = _make_sessions(260)
    r = sessions[255]  # r^- is index 254; 250-bar window = indices 5..254; S=20 window = 235..254

    # Symbol A: close = 10. For indices 5..234 (230 bars), vol = 500M -> v = 5B.
    # For indices 235..254 (20 bars), vol = 100M -> v = 1B.
    # short_mean(20) = 1e9; long_mean(250) = (230*5e9 + 20*1e9)/250 = 4.68e9.
    # Hand AT_20(A) = 1.0 / 4.68 = 0.21367521367521367.
    bars_a = _make_bars(
        "A",
        sessions,
        default_close=10.0,
        vol_fn=lambda i, _d: 100_000_000.0 if i >= 235 else 500_000_000.0,
    )
    # Symbol B: close = 10. For indices 5..234, vol = 200M -> v = 2B; 235..254 vol = 100M -> v = 1B.
    # short_mean(20) = 1e9; long_mean(250) = (230*2e9 + 20*1e9)/250 = 1.92e9.
    # Hand AT_20(B) = 1.0 / 1.92 = 0.5208333333333334.
    bars_b = _make_bars(
        "B",
        sessions,
        default_close=10.0,
        vol_fn=lambda i, _d: 100_000_000.0 if i >= 235 else 200_000_000.0,
    )

    scores: dict[str, float] = {}
    ranked = select_lowattn_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol={"A": bars_a, "B": bars_b},
        s_window=20,
        n_stocks=2,
        out_scores=scores,
    )

    assert ranked == ["A", "B"]
    assert np.isclose(scores["A"], 1.0 / 4.68, atol=1e-9)
    assert np.isclose(scores["B"], 1.0 / 1.92, atol=1e-9)


def test_mutation_e_at_uses_price_times_volume_not_volume_only():
    """Mutation (e): AT chỉ dùng volume, bỏ giá -> select_lowattn_symbols."""
    sessions = _make_sessions(260)
    r = sessions[255]

    # Identical constant volume across both stocks so volume-only AT = 1.0 for both.
    # If volume-only AT is used, tie-break A->Z picks AA_RISE instead of ZZ_DROP.
    bars_zz_drop = _make_bars(
        "ZZ_DROP",
        sessions,
        default_vol=200_000.0,
        close_fn=lambda i, _d: 10_000.0 if i >= 235 else 100_000.0,
    )
    bars_aa_rise = _make_bars(
        "AA_RISE",
        sessions,
        default_vol=200_000.0,
        close_fn=lambda i, _d: 100_000.0 if i >= 235 else 10_000.0,
    )

    ranked = select_lowattn_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol={"AA_RISE": bars_aa_rise, "ZZ_DROP": bars_zz_drop},
        s_window=20,
        n_stocks=1,
    )
    assert ranked == ["ZZ_DROP"]


def test_mutation_f_universe_excludes_fund_certificates():
    """Mutation (f): Không loại chứng chỉ quỹ E1VFVN30 và FU* -> get_universe_at_r."""
    sessions = _make_sessions(260)
    r = sessions[255]

    bars = {
        sym: _make_bars(sym, sessions)
        for sym in ("E1VFVN30", "FUESSVFL", "FUEVFVND", "AAA")
    }
    univ = get_universe_at_r(r=r, sessions=sessions, bars_by_symbol=bars)
    assert univ == ["AAA"]


def test_mutation_g_requires_exact_250_bars_up_to_r_minus():
    """Mutation (g): Bỏ hoặc lệch một nến yêu cầu 250 nến -> select_lowattn_symbols."""
    sessions = _make_sessions(260)
    r = sessions[255]  # r^- is sessions[254]

    # 249 bars ending at r^- (sessions[6..254]): lower AT_20, must be excluded.
    bars_249 = _make_bars(
        "SHORT_249",
        sessions[6:],
        vol_fn=lambda i, _d: 20_000_000.0 if i >= 229 else 200_000_000.0,
    )
    # Exact 250 bars ending at r^- (sessions[5..254]): constant AT_20 = 1.0, must be included.
    bars_250 = _make_bars("EXACT_250", sessions[5:])

    ranked = select_lowattn_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol={"SHORT_249": bars_249, "EXACT_250": bars_250},
        s_window=20,
        n_stocks=2,
    )
    assert ranked == ["EXACT_250"]


def test_mutation_h_simulate_rotation_uses_select_fn():
    """Mutation (h): simulate_rotation bỏ qua select_fn -> simulate_rotation."""
    sessions = _make_sessions(25)
    r0, r1, r2 = sessions[20], sessions[22], sessions[24]

    # A is completely flat (LOWVOL would pick A -> final_nav < 100M after fees).
    bars_a = _make_bars("A", sessions, default_close=100.0)
    # B has high vol in lookback then rises +30% after r0 (select_fn picks B -> final_nav > 125M).
    bars_b = _make_bars(
        "B",
        sessions,
        close_fn=lambda i, _d: 105.0 if i == 19 else (130.0 if i >= 21 else 100.0),
    )

    res = simulate_rotation(
        rebalance_dates=[r0, r1, r2],
        bars_by_symbol={"A": bars_a, "B": bars_b},
        sessions=sessions,
        exchanges={"A": "HOSE", "B": "HOSE"},
        idea_type="LOWVOL",
        lookback=2,
        n_stocks=1,
        select_fn=lambda _r: ["B"],
    )
    assert res["final_nav"] > 125_000_000.0


def test_mutation_i_select_best_ea_config_uses_sharpe_x_not_mean_x():
    """Mutation (i): Bước 1 chọn theo mean_X thay vì sharpe_X -> select_best_ea_config."""
    entries = [
        _ea_entry(20, 10, mean_x=0.05, sharpe_x=0.50),
        _ea_entry(40, 15, mean_x=0.02, sharpe_x=1.20),
    ]
    best = select_best_ea_config(entries)
    assert best["params"] == {"S": 40, "N": 15}


def test_mutation_j_plateau_checks_all_neighbors_on_both_axes():
    """Mutation (j): Bỏ kiểm cao nguyên hoặc chỉ kiểm 1 chiều -> check_plateau."""
    base_good = [
        _ea_entry(20, 10, 0.015, 0.70),
        _ea_entry(20, 15, 0.016, 0.80),
        _ea_entry(20, 20, 0.014, 0.75),
        _ea_entry(40, 10, 0.017, 0.85),
        _ea_entry(40, 15, 0.025, 1.00),  # peak
        _ea_entry(40, 20, 0.016, 0.80),
        _ea_entry(60, 10, 0.015, 0.70),
        _ea_entry(60, 15, 0.018, 0.90),
        _ea_entry(60, 20, 0.015, 0.70),
    ]
    best = next(r for r in base_good if r["params"] == {"S": 40, "N": 15})
    ok_all, _ = check_plateau(best, base_good, GRID)
    assert ok_all is True

    # Fail along N axis only ((40, 20) below 50% sharpe), while S neighbors pass.
    fail_n_axis = [
        _ea_entry(40, 20, 0.005, 0.40) if r["params"] == {"S": 40, "N": 20} else r
        for r in base_good
    ]
    ok_n, _ = check_plateau(best, fail_n_axis, GRID)
    assert ok_n is False

    # Fail along S axis only ((20, 15) mean_X <= 0), while N neighbors pass.
    fail_s_axis = [
        _ea_entry(20, 15, -0.002, -0.10) if r["params"] == {"S": 20, "N": 15} else r
        for r in base_good
    ]
    ok_s, _ = check_plateau(best, fail_s_axis, GRID)
    assert ok_s is False


def test_mutation_k_eb_gates_enforce_all_conditions():
    """Mutation (k): Bỏ cổng MDD, CAGR, hoặc p < 0.05 -> check_eb_gates."""
    passing = {
        "mean_X": 0.015,
        "p": 0.010,
        "mdd": 0.250,  # <= 2/3 * 0.4229 = 0.28193
        "cagr": 0.060,  # >= 0.0550 - 0.01 = 0.0450
    }
    ok, _ = check_eb_gates(passing, avg_syms_held=9.0, n_stocks=10, etf_cagr=ETF_EB_CAGR, etf_mdd=ETF_EB_MDD)
    assert ok is True

    bad_mdd = dict(passing, mdd=0.300)
    assert check_eb_gates(bad_mdd, 9.0, 10, ETF_EB_CAGR, ETF_EB_MDD)[0] is False

    bad_cagr = dict(passing, cagr=0.040)
    assert check_eb_gates(bad_cagr, 9.0, 10, ETF_EB_CAGR, ETF_EB_MDD)[0] is False

    bad_p = dict(passing, p=0.060)
    assert check_eb_gates(bad_p, 9.0, 10, ETF_EB_CAGR, ETF_EB_MDD)[0] is False

    bad_mean = dict(passing, mean_X=-0.005)
    assert check_eb_gates(bad_mean, 9.0, 10, ETF_EB_CAGR, ETF_EB_MDD)[0] is False

    bad_syms = dict(passing)
    assert check_eb_gates(bad_syms, 7.5, 10, ETF_EB_CAGR, ETF_EB_MDD)[0] is False


def test_mutation_l_step4_dsr_uses_plus_29_trials():
    """Mutation (l): DSR thiếu + 29 hoặc sai chữ ký -> compute_step4_dsr vs deflated_sharpe."""
    ea_sharpes = [0.05 * i for i in range(9)]
    sharpe_x = 0.60
    n_months = 35
    skew = -0.15
    kurt = 3.20

    ref_dsr = deflated_sharpe(
        sr=sharpe_x,
        n_obs=n_months,
        skew=skew,
        kurt=kurt,
        n_trials=9 + 29,
        sr_trials_var=float(np.var(ea_sharpes, ddof=1)),
    )
    prod_dsr = compute_step4_dsr(
        sharpe_x=sharpe_x,
        n_months=n_months,
        skew=skew,
        kurt=kurt,
        ea_sharpes=ea_sharpes,
    )
    assert np.isclose(prod_dsr, ref_dsr, atol=1e-9)


def test_mutation_m_exploration_asserts_ledger_safety(tmp_path: Path):
    """Mutation (m): run_exploration bỏ assert_ledger_safety hoặc xoá sổ cũ."""
    existing_ledger = tmp_path / "trial_ledger.csv"
    sentinel = "keep_me_intact\n"
    existing_ledger.write_text(sentinel, encoding="utf-8")

    with pytest.raises(SystemExit, match="đã tồn tại; sổ thử không được xoá để chạy lại"):
        run_exploration(
            data_dir=tmp_path,
            ledger_path=existing_ledger,
            candidates_path=tmp_path / "candidates.json",
            report_path=tmp_path / "exploration_report.md",
            selections_path=tmp_path / "selections.json",
        )

    assert existing_ledger.read_text(encoding="utf-8") == sentinel
