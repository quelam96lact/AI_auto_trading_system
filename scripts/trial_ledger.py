"""Trial ledger constants and PBO exploration helper for strategy research."""

from __future__ import annotations

import numpy as np

from scripts.overfit_core import pbo_cscv

# Cumulative negative strategy families measured prior to Dec 2026:
# - Through Dot 227: 29 negative families (per docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md, 15/11/2026).
# - Dot 237 (low-attention portfolio): #30.
# - Dot 238 (high-attention portfolio, reverse direction of 237): #31.
# - Dot 240 (short-term reversal, 0 candidates): #32 (log entry 15/11/2026 in spec above).
# Older constants in research195_core.py, research227_core.py, research237_explore.py are preserved untouched.
PRIOR_NEGATIVE_FAMILIES: int = 32


def pbo_for_exploration(matrix: np.ndarray) -> float:
    """Compute PBO (CSCV) for an exploration excess-return matrix (T x N).

    Chooses S as the largest even integer <= min(16, T // 2) and calls
    overfit_core.pbo_cscv(matrix, n_splits=S).pbo. Raises ValueError if T < 4.
    """
    arr = np.asarray(matrix, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"matrix must be 2-dimensional, got {arr.ndim}D")
    n_rows = arr.shape[0]
    if n_rows < 4:
        raise ValueError(f"matrix must have at least 4 rows (T >= 4), got T={n_rows}")

    n_splits = min(16, n_rows // 2)
    if n_splits % 2 != 0:
        n_splits -= 1

    return float(pbo_cscv(arr, n_splits=n_splits).pbo)
