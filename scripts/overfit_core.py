"""Anti-overfitting toolkit for strategy parameter evaluation.

Implements:
- sharpe_cols: per-column non-annualized Sharpe ratio.
- pbo_cscv: Probability of Backtest Overfitting via CSCV (Bailey et al., 2015).
- purged_cpcv_splits: Combinatorial Purged Cross-Validation splits with purge & embargo.
- deflated_sharpe: Deflated Sharpe Ratio (Bailey & López de Prado, 2014).
- neighbor_pass_fraction: Chebyshev radius-1 neighborhood pass rate on d-D grids.
- pick_plateau: Plateau-based parameter selection with deterministic tie-breaking.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm, rankdata


def _require_int(value: object, name: str) -> int:
    """Validate that value is an integer (excluding bool) and return Python int."""
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer, got {type(value).__name__}")  # noqa: TRY004
    return int(value)


def _require_finite_float(value: object, name: str) -> float:
    """Validate that value is a finite real number and return Python float."""
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(f"{name} must be a real number, got {type(value).__name__}")  # noqa: TRY004
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return out


def sharpe_cols(m: np.ndarray) -> np.ndarray:
    """Compute non-annualized Sharpe ratio (mean / std with ddof=1) per column.

    Columns with std == 0 or fewer than 2 rows return 0.0.
    """
    try:
        arr = np.asarray(m, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"m must be a numeric 2D array: {exc}") from exc

    if arr.ndim != 2:
        raise ValueError(f"m must be 2-dimensional, got {arr.ndim}D")
    if not np.all(np.isfinite(arr)):
        raise ValueError("m must not contain NaN or inf")

    n_rows, n_cols = arr.shape
    if n_rows < 2 or n_cols == 0:
        return np.zeros(n_cols, dtype=float)

    means = np.mean(arr, axis=0)
    stds = np.std(arr, axis=0, ddof=1)
    out = np.zeros(n_cols, dtype=float)
    nonzero = stds > 0.0
    out[nonzero] = means[nonzero] / stds[nonzero]
    return out


@dataclass(frozen=True)
class PBOResult:
    """Result of Combinatorially Symmetric Cross-Validation (CSCV) PBO analysis."""

    pbo: float
    logits: tuple[float, ...]
    n_combos: int
    n_rows_used: int


def pbo_cscv(perf: np.ndarray, n_splits: int = 16) -> PBOResult:
    """Compute Probability of Backtest Overfitting (PBO) via CSCV.

    Follows Bailey, Borwein, López de Prado, Zhu (2015).
    """
    try:
        arr = np.asarray(perf, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"perf must be a numeric 2D array: {exc}") from exc

    if arr.ndim != 2:
        raise ValueError(f"perf must be 2-dimensional, got {arr.ndim}D")

    n_rows, n_cols = arr.shape
    if n_cols < 2:
        raise ValueError(f"perf must have at least 2 columns (N >= 2), got {n_cols}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("perf must not contain NaN or inf")

    s = _require_int(n_splits, "n_splits")
    if s < 2 or s % 2 != 0:
        raise ValueError(f"n_splits must be an even integer >= 2, got {s}")

    block_size = n_rows // s
    if block_size < 2:
        raise ValueError(
            f"perf must have T // n_splits >= 2, got T={n_rows}, n_splits={s} (T // n_splits={block_size})"
        )

    n_rows_used = block_size * s
    trimmed = arr[:n_rows_used, :]
    blocks = [trimmed[i * block_size : (i + 1) * block_size] for i in range(s)]

    half = s // 2
    logits_list: list[float] = []
    for combo in itertools.combinations(range(s), half):
        in_sample_set = set(combo)
        is_mat = np.vstack([blocks[i] for i in combo])
        oos_mat = np.vstack([blocks[i] for i in range(s) if i not in in_sample_set])

        is_sharpe = sharpe_cols(is_mat)
        oos_sharpe = sharpe_cols(oos_mat)

        n_star = int(np.argmax(is_sharpe))
        rank = float(rankdata(oos_sharpe, method="average")[n_star])
        w = rank / (n_cols + 1.0)
        logit = float(math.log(w / (1.0 - w)))
        logits_list.append(logit)

    n_combos = len(logits_list)
    pbo = sum(1 for x in logits_list if x <= 0.0) / n_combos
    return PBOResult(
        pbo=float(pbo),
        logits=tuple(logits_list),
        n_combos=n_combos,
        n_rows_used=n_rows_used,
    )


def purged_cpcv_splits(
    n_obs: int,
    n_groups: int,
    n_test_groups: int,
    horizon: int,
    embargo: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Generate Combinatorial Purged Cross-Validation (CPCV) (train, test) index splits."""
    n_obs_i = _require_int(n_obs, "n_obs")
    n_groups_i = _require_int(n_groups, "n_groups")
    n_test_i = _require_int(n_test_groups, "n_test_groups")
    horizon_i = _require_int(horizon, "horizon")
    embargo_i = _require_int(embargo, "embargo")

    if n_groups_i < 2:
        raise ValueError(f"n_groups must be >= 2, got {n_groups_i}")
    if n_obs_i < n_groups_i:
        raise ValueError(f"n_obs must be >= n_groups ({n_groups_i}), got {n_obs_i}")
    if n_test_i < 1 or n_test_i >= n_groups_i:
        raise ValueError(f"n_test_groups must satisfy 1 <= n_test_groups < n_groups ({n_groups_i}), got {n_test_i}")
    if horizon_i < 0:
        raise ValueError(f"horizon must be >= 0, got {horizon_i}")
    if embargo_i < 0:
        raise ValueError(f"embargo must be >= 0, got {embargo_i}")

    groups = np.array_split(np.arange(n_obs_i, dtype=int), n_groups_i)
    splits: list[tuple[np.ndarray, np.ndarray]] = []

    for combo in itertools.combinations(range(n_groups_i), n_test_i):
        test = np.concatenate([groups[g] for g in combo]).astype(int)

        # Merge adjacent test groups into contiguous blocks [a, b]
        blocks: list[tuple[int, int]] = []
        for g in combo:
            g_start = int(groups[g][0])
            g_end = int(groups[g][-1])
            if blocks and blocks[-1][1] + 1 == g_start:
                blocks[-1] = (blocks[-1][0], g_end)
            else:
                blocks.append((g_start, g_end))

        keep = np.ones(n_obs_i, dtype=bool)
        keep[test] = False
        for a, b in blocks:
            # Purge: i <= b and i + horizon >= a  =>  a - horizon <= i <= b
            # Embargo: b < i <= b + embargo
            lo = max(0, a - horizon_i)
            hi = min(n_obs_i - 1, b + embargo_i)
            if lo <= hi:
                keep[lo : hi + 1] = False

        train = np.flatnonzero(keep).astype(int)
        splits.append((train, test))

    return splits


def deflated_sharpe(
    sr: float,
    n_obs: int,
    skew: float,
    kurt: float,
    n_trials: int,
    sr_trials_var: float,
) -> float:
    """Compute Deflated Sharpe Ratio (DSR) following Bailey & López de Prado (2014).

    Matches scripts/research188_core.py::deflated_sharpe numerically.
    """
    if n_obs <= 1:
        return 0.0

    # Mertens (2002) standard error of Sharpe ratio (Pearson kurtosis, normal = 3)
    var_sr = (1.0 - skew * sr + ((kurt - 1.0) / 4.0) * (sr**2)) / (n_obs - 1)
    if var_sr <= 0:
        se_sr = 1e-6
    else:
        se_sr = math.sqrt(var_sr)

    if n_trials <= 1:
        sr_star = 0.0
    else:
        gamma = 0.5772156649015329
        e_const = math.e
        p1 = 1.0 - 1.0 / n_trials
        p2 = 1.0 - 1.0 / (n_trials * e_const)

        z1 = float(norm.ppf(p1))
        z2 = float(norm.ppf(p2))

        sr_sd = math.sqrt(max(0.0, sr_trials_var))
        sr_star = sr_sd * ((1.0 - gamma) * z1 + gamma * z2)

    z = (sr - sr_star) / se_sr
    return float(norm.cdf(z))


def neighbor_pass_fraction(scores: np.ndarray, threshold: float) -> np.ndarray:
    """Compute pass fraction in Chebyshev radius-1 neighborhood (including self)."""
    try:
        arr = np.asarray(scores, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"scores must be a numeric array: {exc}") from exc

    if arr.ndim < 1:
        raise ValueError(f"scores must have at least 1 dimension, got {arr.ndim}D")
    if any(dim == 0 for dim in arr.shape):
        raise ValueError(f"scores must not have zero-length dimensions, got shape {arr.shape}")

    thresh_f = _require_finite_float(threshold, "threshold")
    passed = (~np.isnan(arr)) & (arr >= thresh_f)

    out = np.empty(arr.shape, dtype=float)
    for idx in np.ndindex(arr.shape):
        slices = tuple(slice(max(0, i - 1), min(s, i + 2)) for i, s in zip(idx, arr.shape))
        out[idx] = float(np.mean(passed[slices]))
    return out


def pick_plateau(scores: np.ndarray, threshold: float) -> tuple[int, ...] | None:
    """Pick the best passing cell on a parameter grid by plateau robustness.

    Maximizes neighbor_pass_fraction, then median of non-NaN neighbors (including self),
    then smallest index in lexicographical order. Returns None if no cell passes.
    """
    frac = neighbor_pass_fraction(scores, threshold)
    arr = np.asarray(scores, dtype=float)
    thresh_f = float(threshold)
    passed = (~np.isnan(arr)) & (arr >= thresh_f)

    candidates = np.argwhere(passed)
    if len(candidates) == 0:
        return None

    best_idx: tuple[int, ...] | None = None
    best_key: tuple[float, float] | None = None

    for raw_idx in candidates:
        idx = tuple(int(i) for i in raw_idx)
        slices = tuple(slice(max(0, i - 1), min(s, i + 2)) for i, s in zip(idx, arr.shape))
        nbrs = arr[slices]
        valid = nbrs[~np.isnan(nbrs)]
        med = float(np.median(valid))
        key = (float(frac[idx]), med)
        if best_key is None or key > best_key:
            best_key = key
            best_idx = idx

    return best_idx
