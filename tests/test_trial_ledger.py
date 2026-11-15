"""Tests for scripts/trial_ledger.py and PBO wiring in scripts/research237_explore.py."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from scripts import research237_explore as ex237
from scripts import trial_ledger
from scripts.trial_ledger import PRIOR_NEGATIVE_FAMILIES, pbo_for_exploration


def _patch_fake_exploration(
    monkeypatch: pytest.MonkeyPatch,
    n_ea_months: int = 6,
) -> dict[tuple[int, int], np.ndarray]:
    """Patch data/sim functions in research237_explore for fast isolated tests in tmp_path."""
    ea_ew = [0.01 * (i + 1) for i in range(n_ea_months)]
    eb_ew = [0.005, 0.006]
    ea_rebal = [date(2017, 1 + i, 1) for i in range(n_ea_months + 1)]
    eb_rebal = [date(2019, 12, 31), date(2020, 1, 31), date(2020, 2, 28)]

    monkeypatch.setattr(ex237, "load_sessions", lambda *a, **k: [date(2017, 1, 1)])
    monkeypatch.setattr(ex237, "load_stocks", lambda *a, **k: {"AAA": []})
    monkeypatch.setattr(ex237, "load_exchanges", lambda *a, **k: {"AAA": "HOSE"})
    monkeypatch.setattr(ex237, "filter_out_funds", lambda s: s)
    monkeypatch.setattr(ex237, "get_rebalance_dates", lambda s: ea_rebal)

    def fake_filter_rebal(all_r, first_m, last_m):
        return ea_rebal if first_m == ex237.EA_FIRST_MONTH else eb_rebal

    monkeypatch.setattr(ex237, "filter_rebalance_dates", fake_filter_rebal)
    monkeypatch.setattr(
        ex237,
        "ew_benchmark",
        lambda rebal, *a, **k: ea_ew if len(rebal) == len(ea_rebal) else eb_ew,
    )
    monkeypatch.setattr(ex237, "evaluate_and_log", lambda **k: None)

    expected_cols: dict[tuple[int, int], np.ndarray] = {}

    def fake_simulate_rotation(
        rebalance_dates,
        bars_by_symbol,
        sessions,
        exchanges,
        idea_type,
        lookback,
        n_stocks,
        min_turnover,
        select_fn,
    ) -> dict[str, Any]:
        if len(rebalance_dates) == len(ea_rebal):
            r = [0.02 + 0.001 * lookback + 0.0001 * n_stocks + 0.002 * t for t in range(n_ea_months)]
            expected_cols[(lookback, n_stocks)] = np.asarray(r, dtype=float) - np.asarray(ea_ew, dtype=float)
            return {
                "monthly_returns": r,
                "mean_turnover": 0.1,
                "annual_fee_pct": 0.01,
                "avg_syms_held": float(n_stocks),
                "cagr": 0.12,
                "mdd": 0.10,
                "calmar": 1.2,
            }
        return {
            "monthly_returns": [0.02, 0.03],
            "mean_turnover": 0.1,
            "annual_fee_pct": 0.01,
            "avg_syms_held": float(n_stocks),
            "cagr": 0.10,
            "mdd": 0.10,
            "calmar": 1.0,
        }

    monkeypatch.setattr(ex237, "simulate_rotation", fake_simulate_rotation)
    return expected_cols


def _run_in_dir(base_dir: Path, **kwargs: Any) -> tuple[dict[str, Any], str]:
    res = ex237.run_exploration(
        data_dir=base_dir,
        ledger_path=base_dir / "ledger.csv",
        candidates_path=base_dir / "candidates.json",
        report_path=base_dir / "report.md",
        selections_path=base_dir / "selections.json",
        verify_step0=False,
        **kwargs,
    )
    report_text = (base_dir / "report.md").read_text(encoding="utf-8")
    return res, report_text


def test_trial_ledger_prior_negative_families_constant() -> None:
    assert PRIOR_NEGATIVE_FAMILIES == 32


def test_pbo_for_exploration_splits_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_splits: list[int] = []
    real_pbo_cscv = trial_ledger.pbo_cscv

    def spy_pbo_cscv(perf: np.ndarray, n_splits: int = 16):
        seen_splits.append(n_splits)
        return real_pbo_cscv(perf, n_splits=n_splits)

    monkeypatch.setattr(trial_ledger, "pbo_cscv", spy_pbo_cscv)

    rng = np.random.default_rng(7)
    val_36 = pbo_for_exploration(rng.normal(0.0, 1.0, size=(36, 4)))
    assert 0.0 <= val_36 <= 1.0
    assert seen_splits[-1] == 16

    val_10 = pbo_for_exploration(rng.normal(0.0, 1.0, size=(10, 4)))
    assert 0.0 <= val_10 <= 1.0
    assert seen_splits[-1] == 4

    with pytest.raises(ValueError, match="T >= 4"):
        pbo_for_exploration(np.zeros((3, 4)))


def test_run_exploration_pbo_fn_none_preserves_exact_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_fake_exploration(monkeypatch, n_ea_months=6)

    res_default, rep_default = _run_in_dir(tmp_path / "default")
    res_none, rep_none = _run_in_dir(tmp_path / "explicit_none", pbo_fn=None)

    assert "pbo_ea" not in res_default
    assert "pbo_ea" not in res_none
    assert "PBO (EA, CSCV)" not in rep_default
    assert rep_default == rep_none
    assert res_default["candidates_sha"] == res_none["candidates_sha"]
    assert res_default["selections_sha"] == res_none["selections_sha"]
    assert res_default["dsr"] == res_none["dsr"]


def test_run_exploration_pbo_fn_records_matrix_and_report_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    n_months = 8
    expected_cols = _patch_fake_exploration(monkeypatch, n_ea_months=n_months)
    captured: list[np.ndarray] = []

    def fake_pbo(matrix: np.ndarray) -> float:
        captured.append(matrix.copy())
        return 0.25

    res, report_text = _run_in_dir(tmp_path / "with_pbo", pbo_fn=fake_pbo)

    assert res["pbo_ea"] == 0.25
    pbo_lines = [line for line in report_text.splitlines() if "PBO (EA, CSCV)" in line]
    assert len(pbo_lines) == 1
    assert "PBO (EA, CSCV): 0.250" in pbo_lines[0]

    assert len(captured) == 1
    mat = captured[0]
    assert mat.shape == (n_months, 9)

    grid_pairs = [(s, n) for s in ex237.GRID["S"] for n in ex237.GRID["N"]]
    assert len(grid_pairs) == 9
    for col_idx, pair in enumerate(grid_pairs):
        np.testing.assert_allclose(mat[:, col_idx], expected_cols[pair])
