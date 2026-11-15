"""Unit and mutation tests (a–h) for Brief 238 (scripts/research238_core.py,
scripts/research238_explore.py, and shared hooks in research237_*).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from scripts.research188_core import deflated_sharpe
from scripts.research191_data import StockDailyBar
from scripts.research237_explore import ETF_EB_CAGR, ETF_EB_MDD
from scripts.research238_core import get_universe_at_r, select_highattn_symbols
from scripts.research238_explore import (
    LEDGER_PATH,
    check_eb_gates,
    compute_step4_dsr_238,
    run_exploration,
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


def test_mutation_a_keeps_n_highest_at_not_lowest():
    """Mutation (a): Giữ N mã AT thấp nhất thay vì cao nhất -> select_highattn_symbols."""
    sessions = _make_sessions(260)
    r = sessions[255]

    bars_low = _make_bars(
        "LOW_ATTN",
        sessions,
        vol_fn=lambda i, _d: 20_000_000.0 if i >= 235 else 200_000_000.0,
    )
    bars_high = _make_bars(
        "HIGH_ATTN",
        sessions,
        vol_fn=lambda i, _d: 200_000_000.0 if i >= 235 else 20_000_000.0,
    )

    ranked = select_highattn_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol={"LOW_ATTN": bars_low, "HIGH_ATTN": bars_high},
        s_window=20,
        n_stocks=1,
    )
    assert ranked == ["HIGH_ATTN"]


def test_mutation_b_evaluates_up_to_r_minus_not_r():
    """Mutation (b): Điểm tính tới hết r thay vì r^- -> select_highattn_symbols."""
    sessions = _make_sessions(260)
    r = sessions[255]

    # A is constant up to r^- (AT_20 = 1.0), then spikes 100x ONLY on session r (idx 255).
    bars_a = _make_bars(
        "A",
        sessions,
        vol_fn=lambda i, _d: 2_000_000_000.0 if i == 255 else 20_000_000.0,
    )
    # B has elevated recent turnover up to r^- (AT_20 > 1.0), normal at r.
    bars_b = _make_bars(
        "B",
        sessions,
        vol_fn=lambda i, _d: 30_000_000.0 if 235 <= i <= 254 else 20_000_000.0,
    )

    ranked = select_highattn_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol={"A": bars_a, "B": bars_b},
        s_window=20,
        n_stocks=1,
    )
    assert ranked == ["B"]


def test_mutation_c_enforces_is_liquid_and_250_bars():
    """Mutation (c): Bỏ is_liquid hoặc yêu cầu 250 nến -> select_highattn_symbols."""
    sessions = _make_sessions(260)
    r = sessions[255]  # r^- = sessions[254]

    # ILLIQ: AT_20 >> 1.0 (recent 500k shares @ 100 = 50M VND << 1B VND, older = 1,000 VND).
    bars_illiq = _make_bars(
        "ILLIQ",
        sessions,
        vol_fn=lambda i, _d: 500_000.0 if i >= 235 else 10.0,
    )
    # SHORT_249: 249 bars ending at r^-, high AT_20 (liquid 20B recent vs 2B older).
    bars_249 = _make_bars(
        "SHORT_249",
        sessions[6:],
        vol_fn=lambda i, _d: 200_000_000.0 if i >= 229 else 20_000_000.0,
    )
    # VALID_250: exact 250 bars ending at r^-, liquid (2B VND), AT_20 = 1.0.
    bars_250 = _make_bars("VALID_250", sessions[5:])

    ranked = select_highattn_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol={
            "ILLIQ": bars_illiq,
            "SHORT_249": bars_249,
            "VALID_250": bars_250,
        },
        s_window=20,
        n_stocks=3,
    )
    assert ranked == ["VALID_250"]


def test_mutation_d_ties_break_alphabetically_a_to_z():
    """Mutation (d): Hoà điểm không theo A->Z -> select_highattn_symbols."""
    sessions = _make_sessions(260)
    r = sessions[255]

    bars = {
        sym: _make_bars(sym, sessions)
        for sym in ("ZEBRA", "MIDDLE", "ALPHA")
    }
    ranked = select_highattn_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol=bars,
        s_window=20,
        n_stocks=2,
    )
    assert ranked == ["ALPHA", "MIDDLE"]


def test_mutation_e_excludes_fund_certificates():
    """Mutation (e): Không loại chứng chỉ quỹ -> đường chọn mã của 238."""
    sessions = _make_sessions(260)
    r = sessions[255]

    # Funds spike in recent S=20 so they would rank first if not excluded.
    bars = {
        "E1VFVN30": _make_bars(
            "E1VFVN30",
            sessions,
            vol_fn=lambda i, _d: 200_000_000.0 if i >= 235 else 20_000_000.0,
        ),
        "FUESSVFL": _make_bars(
            "FUESSVFL",
            sessions,
            vol_fn=lambda i, _d: 200_000_000.0 if i >= 235 else 20_000_000.0,
        ),
        "AAA": _make_bars("AAA", sessions),
    }
    assert get_universe_at_r(r=r, sessions=sessions, bars_by_symbol=bars) == ["AAA"]
    assert select_highattn_symbols(r=r, sessions=sessions, bars_by_symbol=bars, s_window=20, n_stocks=3) == ["AAA"]


def test_mutation_f_step4_dsr_uses_9_plus_9_plus_30_trials():
    """Mutation (f): DSR thiếu + 9 hoặc + 30 -> compute_step4_dsr_238 vs deflated_sharpe."""
    ea_sharpes = [0.1 + 0.05 * i for i in range(9)]
    sharpe_x = 0.70
    n_months = 35
    skew = -0.10
    kurt = 3.10

    ref_dsr = deflated_sharpe(
        sr=sharpe_x,
        n_obs=n_months,
        skew=skew,
        kurt=kurt,
        n_trials=9 + 9 + 30,
        sr_trials_var=float(np.var(ea_sharpes, ddof=1)),
    )
    prod_dsr = compute_step4_dsr_238(
        sharpe_x=sharpe_x,
        n_months=n_months,
        skew=skew,
        kurt=kurt,
        ea_sharpes=ea_sharpes,
    )
    assert np.isclose(prod_dsr, ref_dsr, atol=1e-9)


def test_mutation_g_ledger_target_not_dot237_and_asserts_safety(tmp_path: Path):
    """Mutation (g): run_exploration của 238 ghi vào sổ dot237 hoặc bỏ assert_ledger_safety."""
    assert "dot238" in Path(LEDGER_PATH).parts
    assert "dot237" not in Path(LEDGER_PATH).parts

    dot237_path = tmp_path / "dot237" / "trial_ledger.csv"
    with pytest.raises(ValueError, match="dot237"):
        run_exploration(
            data_dir=tmp_path,
            ledger_path=dot237_path,
            candidates_path=tmp_path / "candidates.json",
            report_path=tmp_path / "exploration_report.md",
            selections_path=tmp_path / "selections.json",
        )

    existing_ledger = tmp_path / "trial_ledger.csv"
    sentinel = "dot238_existing_sentinel\n"
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


def test_mutation_h_eb_gates_enforce_all_four_conditions():
    """Mutation (h): Cổng EB bỏ một trong bốn điều kiện -> check_eb_gates."""
    passing = {
        "mean_X": 0.015,
        "p": 0.010,
        "mdd": 0.250,
        "cagr": 0.060,
    }
    assert check_eb_gates(passing, avg_syms_held=9.0, n_stocks=10, etf_cagr=ETF_EB_CAGR, etf_mdd=ETF_EB_MDD)[0] is True

    assert check_eb_gates(dict(passing, mean_X=-0.005), 9.0, 10, ETF_EB_CAGR, ETF_EB_MDD)[0] is False
    assert check_eb_gates(dict(passing, p=0.060), 9.0, 10, ETF_EB_CAGR, ETF_EB_MDD)[0] is False
    assert check_eb_gates(dict(passing, mdd=0.300), 9.0, 10, ETF_EB_CAGR, ETF_EB_MDD)[0] is False
    assert check_eb_gates(dict(passing, cagr=0.040), 9.0, 10, ETF_EB_CAGR, ETF_EB_MDD)[0] is False
    assert check_eb_gates(passing, 7.5, 10, ETF_EB_CAGR, ETF_EB_MDD)[0] is False
