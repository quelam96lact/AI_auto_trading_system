"""Unit and mutation tests (a–h) for Brief 240 (scripts/research240_core.py,
scripts/research240_explore.py, and shared hooks in research237_*).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from scripts.research188_core import deflated_sharpe
from scripts.research191_data import StockDailyBar
from scripts.research240_core import get_universe_at_r, select_reversal_symbols
from scripts.research240_explore import (
    LEDGER_PATH,
    compute_step4_dsr_240,
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


def test_mutation_a_keeps_n_lowest_ret_s_not_highest():
    """Mutation (a): Giữ N mã RET_S cao nhất thay vì thấp nhất -> select_reversal_symbols."""
    sessions = _make_sessions(260)
    r = sessions[255]  # r^- = sessions[254], t = 254

    # DROP drops -20% over S=5 (close[249]=100 -> close[254]=80), GAIN rises +20%.
    bars_drop = _make_bars(
        "DROP",
        sessions,
        close_fn=lambda i, _d: 80.0 if i == 254 else 100.0,
    )
    bars_gain = _make_bars(
        "GAIN",
        sessions,
        close_fn=lambda i, _d: 120.0 if i == 254 else 100.0,
    )

    ranked = select_reversal_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol={"DROP": bars_drop, "GAIN": bars_gain},
        s_window=5,
        n_stocks=1,
    )
    assert ranked == ["DROP"]


def test_mutation_b_ret_s_evaluated_at_r_minus_not_r():
    """Mutation (b): RET_S tính tới hết r thay vì r^- -> select_reversal_symbols."""
    sessions = _make_sessions(260)
    r = sessions[255]  # r^- = sessions[254]

    # A is flat (RET_5 = 0.0) up to r^-, then crashes -80% ONLY at session r (idx 255).
    bars_a = _make_bars(
        "A",
        sessions,
        close_fn=lambda i, _d: 20.0 if i == 255 else 100.0,
    )
    # B drops -10% up to r^- (close[249]=100 -> close[254]=90), flat at r.
    bars_b = _make_bars(
        "B",
        sessions,
        close_fn=lambda i, _d: 90.0 if i == 254 else 100.0,
    )

    ranked = select_reversal_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol={"A": bars_a, "B": bars_b},
        s_window=5,
        n_stocks=1,
    )
    assert ranked == ["B"]


def test_mutation_c_ret_s_exact_window_against_hand_calculation():
    """Mutation (c): RET_S lệch 1 nến (t-S+1 hoặc t-S-1) -> select_reversal_symbols, so số tính tay."""
    sessions = _make_sessions(260)
    r = sessions[255]  # r^- = sessions[254], t = 254, S = 5 -> t-S = 249, t-S+1 = 250, t-S-1 = 248

    def _hand_close(idx: int, _d: date) -> float:
        if idx == 248:
            return 100.0  # t - S - 1
        if idx == 249:
            return 120.0  # t - S (exact)
        if idx == 250:
            return 150.0  # t - S + 1
        if idx == 254:
            return 90.0   # t (r^-)
        return 100.0

    # Hand calculation for SYM_HAND: close[254]/close[249] - 1 = 90/120 - 1 = -0.25.
    # Off-by-one t-S+1 gives 90/150 - 1 = -0.40; t-S-1 gives 90/100 - 1 = -0.10.
    bars_hand = _make_bars("SYM_HAND", sessions, close_fn=_hand_close)
    # SYM_ALT has RET_5 = 64/80 - 1 = -0.20 (under t-S-1, SYM_HAND=-0.10 would lose to SYM_ALT=-0.20).
    bars_alt = _make_bars(
        "SYM_ALT",
        sessions,
        close_fn=lambda i, _d: 64.0 if i == 254 else 80.0,
    )
    # SYM_ZERO has close[t-S] <= 0 and must be excluded cleanly.
    bars_zero = _make_bars(
        "SYM_ZERO",
        sessions,
        close_fn=lambda i, _d: 0.0 if i == 249 else (50.0 if i == 254 else 100.0),
    )

    scores: dict[str, float] = {}
    ranked = select_reversal_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol={
            "SYM_HAND": bars_hand,
            "SYM_ALT": bars_alt,
            "SYM_ZERO": bars_zero,
        },
        s_window=5,
        n_stocks=1,
        out_scores=scores,
    )
    assert ranked == ["SYM_HAND"]
    assert "SYM_ZERO" not in scores
    assert np.isclose(scores["SYM_HAND"], 90.0 / 120.0 - 1.0, atol=1e-12)
    assert np.isclose(scores["SYM_ALT"], 64.0 / 80.0 - 1.0, atol=1e-12)


def test_mutation_d_enforces_is_liquid_and_exact_250_bars():
    """Mutation (d): Bỏ is_liquid hoặc bỏ/lệch yêu cầu 250 nến -> select_reversal_symbols."""
    sessions = _make_sessions(260)
    r = sessions[255]  # r^- = sessions[254]

    # ILLIQ: steepest drop (-50%), but turnover = 100 * 500k = 50M VND < 1B VND.
    bars_illiq = _make_bars(
        "ILLIQ",
        sessions,
        close_fn=lambda i, _d: 50.0 if i == 254 else 100.0,
        vol_fn=lambda _i, _d: 500_000.0,
    )
    # SHORT_249: 249 bars up to r^- (sessions[6:], idx at r^- = 248 < 249), liquid, drop -50%.
    bars_249 = _make_bars(
        "SHORT_249",
        sessions[6:],
        close_fn=lambda i, _d: 50.0 if i == 248 else 100.0,
    )
    # EXACT_250: exactly 250 bars up to r^- (sessions[5:], idx at r^- = 249), liquid, drop -20%.
    bars_250 = _make_bars(
        "EXACT_250",
        sessions[5:],
        close_fn=lambda i, _d: 80.0 if i == 249 else 100.0,
    )
    # LONG_251: 251 bars up to r^- (sessions[4:], idx at r^- = 250), liquid, drop -10%.
    bars_251 = _make_bars(
        "LONG_251",
        sessions[4:],
        close_fn=lambda i, _d: 90.0 if i == 250 else 100.0,
    )

    ranked = select_reversal_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol={
            "ILLIQ": bars_illiq,
            "SHORT_249": bars_249,
            "EXACT_250": bars_250,
            "LONG_251": bars_251,
        },
        s_window=5,
        n_stocks=2,
    )
    assert ranked == ["EXACT_250", "LONG_251"]


def test_mutation_e_excludes_fund_certificates():
    """Mutation (e): Không loại chứng chỉ quỹ -> đường chọn mã của 240."""
    sessions = _make_sessions(260)
    r = sessions[255]  # r^- = sessions[254]

    # Funds drop -50% so they would rank first if not excluded.
    bars = {
        "E1VFVN30": _make_bars(
            "E1VFVN30",
            sessions,
            close_fn=lambda i, _d: 50.0 if i == 254 else 100.0,
        ),
        "FUESSVFL": _make_bars(
            "FUESSVFL",
            sessions,
            close_fn=lambda i, _d: 50.0 if i == 254 else 100.0,
        ),
        "AAA": _make_bars(
            "AAA",
            sessions,
            close_fn=lambda i, _d: 95.0 if i == 254 else 100.0,
        ),
    }
    assert get_universe_at_r(r=r, sessions=sessions, bars_by_symbol=bars) == ["AAA"]
    assert select_reversal_symbols(r=r, sessions=sessions, bars_by_symbol=bars, s_window=5, n_stocks=3) == ["AAA"]


def test_mutation_f_ties_break_alphabetically_a_to_z():
    """Mutation (f): Hoà điểm không theo A->Z -> select_reversal_symbols."""
    sessions = _make_sessions(260)
    r = sessions[255]

    bars = {
        sym: _make_bars(
            sym,
            sessions,
            close_fn=lambda i, _d: 90.0 if i == 254 else 100.0,
        )
        for sym in ("ZEBRA", "MIDDLE", "ALPHA")
    }
    ranked = select_reversal_symbols(
        r=r,
        sessions=sessions,
        bars_by_symbol=bars,
        s_window=5,
        n_stocks=2,
    )
    assert ranked == ["ALPHA", "MIDDLE"]


def test_mutation_g_step4_dsr_uses_9_plus_31_trials():
    """Mutation (g): DSR dùng n_trials khác 9 + 31 -> compute_step4_dsr_240 vs deflated_sharpe."""
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
        n_trials=9 + 31,
        sr_trials_var=float(np.var(ea_sharpes, ddof=1)),
    )
    prod_dsr = compute_step4_dsr_240(
        sharpe_x=sharpe_x,
        n_months=n_months,
        skew=skew,
        kurt=kurt,
        ea_sharpes=ea_sharpes,
    )
    assert np.isclose(prod_dsr, ref_dsr, atol=1e-9)


def test_mutation_h_run_exploration_ledger_target_and_safety(tmp_path: Path):
    """Mutation (h): run_exploration của 240 ghi vào sổ đợt khác hoặc bỏ assert_ledger_safety."""
    assert "dot240" in Path(LEDGER_PATH).parts
    assert "dot237" not in Path(LEDGER_PATH).parts
    assert "dot238" not in Path(LEDGER_PATH).parts

    for other_batch in ("dot237", "dot238"):
        bad_ledger = tmp_path / other_batch / "trial_ledger.csv"
        with pytest.raises(ValueError, match="dot240"):
            run_exploration(
                data_dir=tmp_path,
                ledger_path=bad_ledger,
                candidates_path=tmp_path / "candidates.json",
                report_path=tmp_path / "exploration_report.md",
                selections_path=tmp_path / "selections.json",
            )

    existing_ledger = tmp_path / "dot240" / "trial_ledger.csv"
    existing_ledger.parent.mkdir(parents=True, exist_ok=True)
    sentinel = "dot240_existing_sentinel\n"
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
