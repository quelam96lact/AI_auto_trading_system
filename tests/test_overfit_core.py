"""Tests for scripts/overfit_core.py."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from scripts.overfit_core import (
    PBOResult,
    deflated_sharpe,
    neighbor_pass_fraction,
    pbo_cscv,
    pick_plateau,
    purged_cpcv_splits,
    sharpe_cols,
)
from scripts.research188_core import deflated_sharpe as ref_deflated_sharpe


def test_sharpe_cols_basic_and_edge_cases() -> None:
    m = np.array(
        [
            [1.0, 2.0, 0.0],
            [3.0, 2.0, 0.0],
            [5.0, 2.0, 0.0],
        ]
    )
    res = sharpe_cols(m)
    expected_col0 = np.mean([1.0, 3.0, 5.0]) / np.std([1.0, 3.0, 5.0], ddof=1)
    assert res.shape == (3,)
    assert res[0] == pytest.approx(expected_col0)
    assert res[1] == 0.0
    assert res[2] == 0.0

    # T < 2 -> all zeros
    assert np.array_equal(sharpe_cols(np.array([[1.0, 2.0]])), np.array([0.0, 0.0]))
    assert np.array_equal(sharpe_cols(np.empty((0, 2))), np.array([0.0, 0.0]))


def test_sharpe_cols_value_errors() -> None:
    with pytest.raises(ValueError):
        sharpe_cols(np.array([1.0, 2.0]))
    with pytest.raises(ValueError):
        sharpe_cols(np.zeros((2, 2, 2)))
    with pytest.raises(ValueError):
        sharpe_cols(np.array([[1.0, np.nan], [2.0, 3.0]]))
    with pytest.raises(ValueError):
        sharpe_cols(np.array([[1.0, np.inf], [2.0, 3.0]]))


def test_pbo_cscv_zero_and_one() -> None:
    # T=8, N=2, S=4: col 0 strictly positive Sharpe in every block, col 1 strictly negative -> PBO = 0.0
    perf_zero = np.array(
        [
            [2.0, -4.0],
            [4.0, -2.0],
            [2.0, -4.0],
            [4.0, -2.0],
            [2.0, -4.0],
            [4.0, -2.0],
            [2.0, -4.0],
            [4.0, -2.0],
        ]
    )
    res_zero = pbo_cscv(perf_zero, n_splits=4)
    assert isinstance(res_zero, PBOResult)
    assert res_zero.pbo == 0.0
    assert res_zero.n_combos == 6
    assert res_zero.n_rows_used == 8
    assert len(res_zero.logits) == 6
    assert all(x > 0.0 for x in res_zero.logits)

    with pytest.raises(FrozenInstanceError):
        res_zero.pbo = 0.5  # type: ignore[misc]

    # T=8, N=2, S=4: symmetric sign-flipping blocks -> IS winner loses (or ties) OOS -> PBO = 1.0
    perf_one = np.array(
        [
            [9.5, -9.5],
            [10.5, -10.5],
            [0.5, -0.5],
            [1.5, -1.5],
            [-1.5, 1.5],
            [-0.5, 0.5],
            [-10.5, 10.5],
            [-9.5, 9.5],
        ]
    )
    res_one = pbo_cscv(perf_one, n_splits=4)
    assert res_one.pbo == 1.0
    assert res_one.n_combos == 6
    assert all(x <= 0.0 for x in res_one.logits)


def test_pbo_cscv_n_combos_70_and_drop_remainder() -> None:
    rng = np.random.default_rng(42)
    perf_s8 = rng.normal(0.0, 1.0, size=(16, 4))
    res_s8 = pbo_cscv(perf_s8, n_splits=8)
    assert res_s8.n_combos == 70
    assert len(res_s8.logits) == 70
    assert res_s8.n_rows_used == 16

    # Drop last T % n_splits rows
    base = rng.normal(0.0, 1.0, size=(8, 3))
    extra1 = np.vstack([base, np.array([[100.0, -100.0, 0.0], [100.0, -100.0, 0.0]])])
    extra2 = np.vstack([base, np.array([[-50.0, 50.0, 10.0], [-50.0, 50.0, 10.0]])])
    r1 = pbo_cscv(extra1, n_splits=4)
    r2 = pbo_cscv(extra2, n_splits=4)
    assert r1.n_rows_used == 8
    assert r1.logits == r2.logits
    assert r1.pbo == r2.pbo


def test_pbo_cscv_tie_picks_smallest_col() -> None:
    # Col 0 and Col 1 are identical in blocks 0,1 (IS for combo (0,1))
    # but in blocks 2,3 (OOS for combo (0,1)), Col 0 is worse than Col 1.
    # Tie-breaker must pick Col 0 (smallest index), giving rank=1 in OOS for combo (0,1).
    perf = np.array(
        [
            [1.0, 1.0],
            [3.0, 3.0],
            [1.0, 1.0],
            [3.0, 3.0],
            [-3.0, 1.0],
            [-1.0, 3.0],
            [-3.0, 1.0],
            [-1.0, 3.0],
        ]
    )
    res = pbo_cscv(perf, n_splits=4)
    # First combo in itertools.combinations(range(4), 2) is (0, 1)
    # n_star = 0, OOS rank of col 0 is 1.0, w = 1/3, logit = ln(0.5)
    assert res.logits[0] == pytest.approx(np.log(0.5))


def test_pbo_cscv_value_errors() -> None:
    valid = np.ones((8, 2))
    with pytest.raises(ValueError, match="2-dimensional"):
        pbo_cscv(np.ones(8), n_splits=4)
    with pytest.raises(ValueError, match="N >= 2"):
        pbo_cscv(np.ones((8, 1)), n_splits=4)
    bad_nan = valid.copy()
    bad_nan[0, 0] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        pbo_cscv(bad_nan, n_splits=4)
    bad_inf = valid.copy()
    bad_inf[0, 0] = np.inf
    with pytest.raises(ValueError, match="NaN"):
        pbo_cscv(bad_inf, n_splits=4)
    with pytest.raises(ValueError, match="n_splits"):
        pbo_cscv(valid, n_splits=3)
    with pytest.raises(ValueError, match="n_splits"):
        pbo_cscv(valid, n_splits=0)
    with pytest.raises(ValueError, match="n_splits"):
        pbo_cscv(valid, n_splits=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="T // n_splits"):
        pbo_cscv(np.ones((6, 2)), n_splits=4)


def test_purged_cpcv_splits_hand_calculated_and_properties() -> None:
    splits = purged_cpcv_splits(
        n_obs=10,
        n_groups=5,
        n_test_groups=2,
        horizon=1,
        embargo=1,
    )
    expected = [
        ([5, 6, 7, 8, 9], [0, 1, 2, 3]),
        ([7, 8, 9], [0, 1, 4, 5]),
        ([3, 4, 9], [0, 1, 6, 7]),
        ([3, 4, 5, 6], [0, 1, 8, 9]),
        ([0, 7, 8, 9], [2, 3, 4, 5]),
        ([0, 9], [2, 3, 6, 7]),
        ([0, 5, 6], [2, 3, 8, 9]),
        ([0, 1, 2, 9], [4, 5, 6, 7]),
        ([0, 1, 2], [4, 5, 8, 9]),
        ([0, 1, 2, 3, 4], [6, 7, 8, 9]),
    ]
    assert len(splits) == 10
    for (train, test), (exp_train, exp_test) in zip(splits, expected, strict=True):
        assert np.issubdtype(train.dtype, np.integer)
        assert np.issubdtype(test.dtype, np.integer)
        assert train.tolist() == exp_train
        assert test.tolist() == exp_test

    # horizon=0, embargo=0 -> partition of 0..n_obs-1
    no_purge = purged_cpcv_splits(n_obs=11, n_groups=4, n_test_groups=2, horizon=0, embargo=0)
    assert len(no_purge) == 6
    all_idx = set(range(11))
    for train, test in no_purge:
        t_set = set(train.tolist())
        v_set = set(test.tolist())
        assert t_set.isdisjoint(v_set)
        assert t_set | v_set == all_idx

    # Empty train allowed without error
    empty_train_splits = purged_cpcv_splits(n_obs=6, n_groups=3, n_test_groups=1, horizon=5, embargo=5)
    assert any(len(tr) == 0 for tr, _ in empty_train_splits)


def test_purged_cpcv_splits_value_errors() -> None:
    with pytest.raises(ValueError, match="n_groups"):
        purged_cpcv_splits(10, 1, 1, 0, 0)
    with pytest.raises(ValueError, match="n_obs"):
        purged_cpcv_splits(3, 4, 1, 0, 0)
    with pytest.raises(ValueError, match="n_test_groups"):
        purged_cpcv_splits(10, 5, 0, 0, 0)
    with pytest.raises(ValueError, match="n_test_groups"):
        purged_cpcv_splits(10, 5, 5, 0, 0)
    with pytest.raises(ValueError, match="horizon"):
        purged_cpcv_splits(10, 5, 2, -1, 0)
    with pytest.raises(ValueError, match="embargo"):
        purged_cpcv_splits(10, 5, 2, 0, -1)
    with pytest.raises(ValueError, match="n_obs"):
        purged_cpcv_splits(True, 5, 2, 0, 0)  # type: ignore[arg-type]


def test_deflated_sharpe_matches_research188() -> None:
    cases = [
        # (sr, n_obs, skew, kurt, n_trials, sr_trials_var)
        (0.5, 100, 0.0, 3.0, 1, 0.0),
        (0.5, 100, 0.0, 3.0, 1, 0.25),
        (1.0, 252, -0.5, 4.5, 10, 0.1),
        (1.5, 50, 0.3, 2.5, 50, 0.2),
        (-0.2, 120, -1.0, 6.0, 20, 0.05),
        (0.0, 60, 0.0, 3.0, 5, 0.1),
        (2.0, 30, 0.1, 3.2, 100, 0.3),
        (0.8, 500, -0.2, 3.8, 2, 0.01),
        (0.3, 1000, 0.5, 5.0, 200, 0.04),
        # Edge cases: n_obs <= 1
        (1.0, 1, 0.0, 3.0, 10, 0.1),
        (1.0, 0, 0.0, 3.0, 10, 0.1),
        (1.0, -5, 0.0, 3.0, 1, 0.0),
        # Edge cases: var_sr <= 0
        (3.0, 50, 4.0, 1.0, 5, 0.05),
        (2.0, 20, 5.0, 1.0, 1, 0.0),
        (1.5, 10, 2.0, 1.0, 25, 0.1),
        # Edge cases: sr_trials_var <= 0
        (1.2, 80, 0.0, 3.0, 15, 0.0),
        (1.2, 80, 0.0, 3.0, 15, -0.1),
        # Additional grid points
        (0.1, 40, -0.8, 7.0, 3, 0.02),
        (0.75, 150, 0.2, 2.8, 30, 0.15),
        (1.1, 200, -0.1, 3.5, 75, 0.08),
        (0.4, 25, 0.0, 3.0, 4, 0.03),
        (1.8, 300, 0.6, 4.2, 150, 0.25),
    ]
    assert len(cases) >= 20
    for params in cases:
        got = deflated_sharpe(*params)
        ref = ref_deflated_sharpe(*params)
        assert abs(got - ref) <= 1e-12, f"Mismatch for {params}: {got} vs {ref}"


def test_neighbor_pass_fraction_1d_and_2d() -> None:
    # 1D with NaN and boundary
    scores_1d = np.array([1.0, 0.5, np.nan, 2.0, 1.5])
    frac_1d = neighbor_pass_fraction(scores_1d, threshold=1.0)
    # idx 0: [1.0, 0.5] -> 1/2
    # idx 1: [1.0, 0.5, nan] -> 1/3
    # idx 2: [0.5, nan, 2.0] -> 1/3
    # idx 3: [nan, 2.0, 1.5] -> 2/3
    # idx 4: [2.0, 1.5] -> 2/2
    np.testing.assert_allclose(frac_1d, [0.5, 1.0 / 3.0, 1.0 / 3.0, 2.0 / 3.0, 1.0])

    # 2D corner (4 cells) and center (9 cells)
    scores_2d = np.array(
        [
            [1.0, 1.0, 0.0],
            [1.0, 0.0, np.nan],
            [0.0, 1.0, 1.0],
        ]
    )
    frac_2d = neighbor_pass_fraction(scores_2d, threshold=1.0)
    assert frac_2d[0, 0] == pytest.approx(3.0 / 4.0)  # (0,0),(0,1),(1,0),(1,1) -> 3 pass / 4
    assert frac_2d[1, 1] == pytest.approx(5.0 / 9.0)  # 5 pass / 9


def test_pick_plateau_tie_breaking_and_none() -> None:
    # None when no cell passes
    assert pick_plateau(np.array([[0.5, np.nan], [0.9, 0.0]]), threshold=1.0) is None

    # Level 1: highest neighbor_pass_fraction wins over isolated high peak
    # (0,0) has score 10.0, neighbors (0,1)=0.0, (1,0)=0.0, (1,1)=0.0 -> frac 1/4
    # (2,2) has score 1.0, all 4 corner neighbors >= 1.0 -> frac 4/4
    scores_l1 = np.array(
        [
            [10.0, 0.0, 0.0],
            [0.0, 1.0, 1.0],
            [0.0, 1.0, 1.0],
        ]
    )
    pick_l1 = pick_plateau(scores_l1, threshold=1.0)
    assert pick_l1 == (2, 2)
    assert all(type(x) is int for x in pick_l1)

    # Level 2: tie in neighbor_pass_fraction (both 1.0), higher median wins
    # 1D: [1.0, 1.0, 1.0, 0.0, 3.0, 4.0, 1.5]
    # idx 1 has nbrs [1,1,1] -> frac=1.0, median=1.0
    # idx 5 has nbrs [3,4,1.5] -> frac=1.0, median=3.0
    # idx 6 has nbrs [4,1.5] -> frac=1.0, median=2.75
    scores_l2 = np.array([1.0, 1.0, 1.0, 0.0, 3.0, 4.0, 1.5])
    assert pick_plateau(scores_l2, threshold=1.0) == (5,)

    # Level 3: tie in both fraction and median -> lexicographically smallest index
    scores_l3 = np.array(
        [
            [1.0, 1.0],
            [1.0, 1.0],
        ]
    )
    assert pick_plateau(scores_l3, threshold=1.0) == (0, 0)


def test_plateau_value_errors() -> None:
    with pytest.raises(ValueError, match="dimension"):
        neighbor_pass_fraction(np.array(1.0), threshold=0.5)
    with pytest.raises(ValueError, match="zero-length"):
        neighbor_pass_fraction(np.empty((2, 0)), threshold=0.5)
    with pytest.raises(ValueError, match="threshold"):
        pick_plateau(np.array([1.0, 2.0]), threshold=float("nan"))
