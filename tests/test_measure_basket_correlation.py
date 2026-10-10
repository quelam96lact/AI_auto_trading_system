"""Test suite cho scripts/measure_basket_correlation.py (Brief dot 180).

Tat ca 9 ca test dung du lieu tong hop dung tay, co seed co dinh, khong cham DB.
Gom 9 ca kiem chung:
1. Hai chuoi giong het va ba chuoi giong het -> Pearson = 1.0, lambda = (3, 0, 0), PR = 1.0.
2. Ba chuoi doc lap (2.000 phien) -> |rho_mean| < 0.10 va PR >= 2.5.
3. Ma tran biet truoc (2 giong + 1 doc lap) -> lambda ~ (2, 1, 0), PR ~ 1.8.
4. Bay gia-vs-loi-suat: 3 chuoi 100*exp(0.002*t + noise) -> tren loi suat |rho_mean| < 0.10.
5. Lech ngay: dich 1 chuoi 1 phien -> ghep theo ngay cho rho = 1.0, ghep theo chi so cho rho ~ 0.
6. Phien thieu: du lieu co lo -> dung dung giao tap ngay, khong noi suy, khong forward-fill.
7. Cong niem phong: read_bars_window_a nem ValueError neu co nen >= 2023-01-01.
8. PR dung cong thuc (I_3 -> PR = 3.0) va bat bien khi hoan vi ma tran.
9. Dinh co ATR va lo ro theo RiskManager khop tinh tay (sai so 1e-9).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import numpy as np
import pytest

from scripts.measure_basket_correlation import (
    align_series,
    compute_correlation_matrix,
    compute_eigenvalues_and_pr,
    compute_portfolio_loss_distribution,
    read_bars_window_a,
)
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.risk import RiskManager


def _make_bar(
    symbol: str,
    d: date,
    close: float,
    high: float | None = None,
    low: float | None = None,
    open_: float | None = None,
    volume: int = 1000,
) -> Bar:
    dt = datetime(d.year, d.month, d.day, 9, 0, tzinfo=TZ)
    h = close if high is None else high
    l = close if low is None else low
    o = close if open_ is None else open_
    return Bar(
        symbol=symbol,
        ts=dt,
        open=o,
        high=h,
        low=l,
        close=close,
        volume=volume,
        source="ssi",
    )


def test_1_hai_chuoi_giong_het_va_ba_chuoi_giong_het():
    """Ca 1: Hai chuoi giong het -> rho = 1.0; Ba chuoi giong het -> lambda = (3,0,0), PR = 1.0."""
    rng = np.random.default_rng(42)
    rets_2 = rng.normal(0, 0.02, 500)
    mat_2 = np.column_stack([rets_2, rets_2])

    corr_p_2, _, mean_p_2, _ = compute_correlation_matrix(mat_2)
    assert math.isclose(corr_p_2[0, 1], 1.0, abs_tol=1e-12)
    assert math.isclose(mean_p_2, 1.0, abs_tol=1e-12)

    rets_3 = rng.normal(0, 0.02, 500)
    mat_3 = np.column_stack([rets_3, rets_3, rets_3])

    corr_p_3, _, mean_p_3, _ = compute_correlation_matrix(mat_3)
    assert math.isclose(mean_p_3, 1.0, abs_tol=1e-12)

    eigvals, pr, pr_entropy = compute_eigenvalues_and_pr(corr_p_3)
    assert math.isclose(eigvals[0], 3.0, abs_tol=1e-12)
    assert math.isclose(eigvals[1], 0.0, abs_tol=1e-12)
    assert math.isclose(eigvals[2], 0.0, abs_tol=1e-12)
    assert math.isclose(pr, 1.0, abs_tol=1e-12)
    assert math.isclose(pr_entropy, 1.0, abs_tol=1e-12)


def test_2_ba_chuoi_doc_lap():
    """Ca 2: Ba chuoi doc lap (2.000 phien) -> |rho_mean| < 0.10 va PR >= 2.5."""
    rng = np.random.default_rng(123)
    rets = rng.normal(0, 0.02, (2000, 3))

    corr_p, _, mean_p, _ = compute_correlation_matrix(rets)
    assert abs(mean_p) < 0.10

    eigvals, pr, _ = compute_eigenvalues_and_pr(corr_p)
    assert pr >= 2.5
    assert len(eigvals) == 3


def test_3_ma_tran_biet_truoc():
    """Ca 3: Hai chuoi giong nhau + mot chuoi doc lap -> lambda ~ (2, 1, 0), PR ~ 1.8."""
    rng = np.random.default_rng(99)
    n = 2000
    r1 = rng.normal(0, 0.02, n)
    r2 = r1.copy()
    r3 = rng.normal(0, 0.02, n)
    mat = np.column_stack([r1, r2, r3])

    corr_p, _, _, _ = compute_correlation_matrix(mat)
    eigvals, pr, _ = compute_eigenvalues_and_pr(corr_p)

    assert math.isclose(eigvals[0], 2.0, abs_tol=0.05)
    assert math.isclose(eigvals[1], 1.0, abs_tol=0.05)
    assert math.isclose(eigvals[2], 0.0, abs_tol=0.05)
    assert math.isclose(pr, 1.80, abs_tol=0.05)


def test_4_bay_gia_vs_loi_suat():
    """Ca 4: 3 chuoi gia 100*exp(0.002*t + noise) -> loi suat |rho_mean| < 0.10.

    Dung de phat hien phep pha (i): neu tinh tuong quan tren gia thay vi loi suat,
    tuong quan tren gia se dat ~0.99 do xu huong chung, lam test nay do.
    """
    rng = np.random.default_rng(42)
    n = 2000
    t = np.arange(n)
    noise = rng.normal(0, 0.02, (n, 3))
    prices = 100.0 * np.exp(0.002 * t[:, None] + noise)

    base_date = date(2020, 1, 1)
    bars_dict: dict[str, list[Bar]] = {"A": [], "B": [], "C": []}
    for i in range(n):
        d = base_date + timedelta(days=i)
        bars_dict["A"].append(_make_bar("A", d, float(prices[i, 0])))
        bars_dict["B"].append(_make_bar("B", d, float(prices[i, 1])))
        bars_dict["C"].append(_make_bar("C", d, float(prices[i, 2])))

    dates, mat, _symbols = align_series(bars_dict)
    assert len(dates) == n
    assert mat.shape == (n - 1, 3)

    _, _, mean_p, _ = compute_correlation_matrix(mat)
    # Tren loi suat log, tuong quan trung binh phai nho (< 0.10)
    assert abs(mean_p) < 0.10


def test_5_lech_ngay():
    """Ca 5: Dich mot chuoi 1 phien -> ghep theo ngay cho rho = 1.0.

    Dung de phat hien phep pha (ii): neu ghep theo chi so thay vi theo ngay,
    vi chuoi da bi lech 1 phien nen cac phien doc lap se cap vao nhau lam rho ~ 0 != 1.0.
    """
    rng = np.random.default_rng(2024)
    n = 300
    base_date = date(2021, 1, 1)
    # Chuoi sinh loi trang
    log_rets = rng.normal(0, 0.02, n)
    p = 100.0
    prices = [p]
    for r in log_rets:
        p = p * math.exp(r)
        prices.append(p)

    # Symbol A: co ngay d_2 -> d_200 (199 ngay)
    # Symbol B: co ngay d_1 -> d_199 (199 ngay)
    # Giao tap ngay: d_2 -> d_199 (198 ngay)
    bars_a = []
    for i in range(1, 200):
        d = base_date + timedelta(days=i)
        bars_a.append(_make_bar("A", d, prices[i]))

    bars_b = []
    # Ngay d_0 cho B co gia doc lap
    bars_b.append(_make_bar("B", base_date, 99.0))
    for i in range(1, 199):
        d = base_date + timedelta(days=i)
        bars_b.append(_make_bar("B", d, prices[i]))

    # Ghep dung theo ngay
    dates, mat, _symbols = align_series({"A": bars_a, "B": bars_b})
    assert len(dates) == 198
    corr_p, _, _, _ = compute_correlation_matrix(mat)
    # Tren cac ngay chung, A va B co gia va loi suat giong het nhau
    assert math.isclose(corr_p[0, 1], 1.0, abs_tol=1e-6)

    # Neu ghep theo chi so mang, lech 1 phien nen rho se giam manh
    _, mat_idx, _ = align_series(
        {"A": bars_a, "B": bars_b},
        match_by_index_instead_of_date=True,
    )
    corr_idx, _, _, _ = compute_correlation_matrix(mat_idx)
    assert abs(corr_idx[0, 1]) < 0.30


def test_6_phien_thieu_khong_noi_suy():
    """Ca 6: Du lieu co lo -> so phien dung duoc dung bang giao tap ngay ca ba cung co."""
    base_date = date(2021, 1, 1)
    # D1, D2, D3, D4, D5, D6, D7
    dates_all = [base_date + timedelta(days=i) for i in range(7)]

    # A co {0, 1, 2, 4, 5, 6} (thieu ngay 3)
    # B co {0, 1, 3, 4, 5, 6} (thieu ngay 2)
    # C co {0, 1, 2, 3, 4, 6} (thieu ngay 5)
    # Giao tap: {0, 1, 4, 6} -> 4 ngay -> 3 loi suat
    idx_a = {0, 1, 2, 4, 5, 6}
    idx_b = {0, 1, 3, 4, 5, 6}
    idx_c = {0, 1, 2, 3, 4, 6}

    bars_a = [_make_bar("A", dates_all[i], 100.0 + i) for i in sorted(idx_a)]
    bars_b = [_make_bar("B", dates_all[i], 50.0 + i) for i in sorted(idx_b)]
    bars_c = [_make_bar("C", dates_all[i], 20.0 + i) for i in sorted(idx_c)]

    dates, mat, _symbols = align_series({"A": bars_a, "B": bars_b, "C": bars_c})

    expected_dates = [dates_all[i] for i in [0, 1, 4, 6]]
    assert dates == expected_dates
    assert mat.shape == (3, 3)

    # Khong co ngay 2, 3, 5 trong tap ngay chung
    assert dates_all[2] not in dates
    assert dates_all[3] not in dates
    assert dates_all[5] not in dates


def test_7_cong_niem_phong(monkeypatch):
    """Ca 7: Goi read_bars_window_a voi nen >= 2023-01-01 -> phai nem ValueError."""
    mock_storage = MagicMock()

    # Gia lap read_bars tra ve 1 nen vi pham niem phong (nam 2023)
    breach_bar = _make_bar("HPG", date(2023, 5, 10), 25.0)
    monkeypatch.setattr(
        "scripts.measure_basket_correlation.read_bars",
        lambda st, sym: ([breach_bar], 0),
    )

    with pytest.raises(ValueError, match="Vi phạm niêm phong"):
        read_bars_window_a(mock_storage, "HPG")


def test_8_pr_dung_cong_thuc_va_bat_bien():
    """Ca 8: I_3 -> PR = 3.0 va PR bat bien khi hoan vi ma tran.

    Dung de phat hien phep pha (iii): cong thuc sai sum(l^2)/sum(l) cho 3/3 = 1.0 != 3.0.
    """
    eye_3 = np.eye(3)
    eigvals, pr, pr_ent = compute_eigenvalues_and_pr(eye_3)

    # Voi I_3: lambda = (1, 1, 1) -> PR = (1+1+1)^2 / (1+1+1) = 9/3 = 3.0
    assert np.allclose(eigvals, [1.0, 1.0, 1.0])
    assert math.isclose(pr, 3.0, abs_tol=1e-12)
    assert math.isclose(pr_ent, 3.0, abs_tol=1e-12)

    # Bat bien khi hoan vi thu tu hang/cot
    rng = np.random.default_rng(77)
    random_mat = rng.normal(0, 0.02, (100, 3))
    corr_orig, _, _, _ = compute_correlation_matrix(random_mat)
    _, pr_orig, _ = compute_eigenvalues_and_pr(corr_orig)

    # Hoan vi (cot 0 -> 1, cot 1 -> 2, cot 2 -> 0)
    perm_mat = random_mat[:, [1, 2, 0]]
    corr_perm, _, _, _ = compute_correlation_matrix(perm_mat)
    _, pr_perm, _ = compute_eigenvalues_and_pr(corr_perm)

    assert math.isclose(pr_orig, pr_perm, abs_tol=1e-12)


def test_9_dinh_co_atr_va_lo_ro_khop_tinh_tay():
    """Ca 9: Dinh co ATR va lo ro theo RiskManager khop tinh tay (sai so 1e-9).

    Thiet ke nen 22 phien:
    - 20 phien truoc de tinh ATR20 tai phien 20 (d_20):
      + A: close=100.0, high=102.0, low=98.0 -> TR=4.0 -> ATR20 = 4.0
           atr_pct = 4.0 / 100.0 = 0.04
           raw_w = 0.01 / (2.0 * 0.04) = 0.125 (< 0.20 max) -> w_A = 0.125
      + B: close=50.0, high=50.5, low=49.5 -> TR=1.0 -> ATR20 = 1.0
           atr_pct = 1.0 / 50.0 = 0.02
           raw_w = 0.01 / (2.0 * 0.02) = 0.25 (> 0.20 max) -> w_B = 0.20
      + C: close=20.0, high=20.5, low=19.5 -> TR=1.0 -> ATR20 = 1.0
           atr_pct = 1.0 / 20.0 = 0.05
           raw_w = 0.01 / (2.0 * 0.05) = 0.10 (< 0.20 max) -> w_C = 0.10

    - Phien 21 (d_21):
      + A: close = 98.0  -> ret = 98/100 - 1 = -0.02 -> loss = -0.125 * (-0.02) = +0.0025
      + B: close = 49.0  -> ret = 49/50 - 1 = -0.02  -> loss = -0.200 * (-0.02) = +0.0040
      + C: close = 20.2  -> ret = 20.2/20 - 1 = +0.01 -> loss = -0.100 * (+0.01) = -0.0010
      Tong lo ro = 0.0025 + 0.0040 - 0.0010 = 0.0055 (0.55%).
    """
    rm = RiskManager(capital=100_000_000.0)
    base_d = date(2020, 1, 1)

    bars_a: list[Bar] = []
    bars_b: list[Bar] = []
    bars_c: list[Bar] = []

    # 21 phien dau (i = 0 .. 20)
    for i in range(21):
        d = base_d + timedelta(days=i)
        bars_a.append(_make_bar("A", d, close=100.0, high=102.0, low=98.0))
        bars_b.append(_make_bar("B", d, close=50.0, high=50.5, low=49.5))
        bars_c.append(_make_bar("C", d, close=20.0, high=20.5, low=19.5))

    # Phien 22 (i = 21, ngay d_21)
    d_21 = base_d + timedelta(days=21)
    bars_a.append(_make_bar("A", d_21, close=98.0, high=100.0, low=98.0))
    bars_b.append(_make_bar("B", d_21, close=49.0, high=50.0, low=49.0))
    bars_c.append(_make_bar("C", d_21, close=20.2, high=20.5, low=20.0))

    bars_by_sym = {"A": bars_a, "B": bars_b, "C": bars_c}
    res = compute_portfolio_loss_distribution(bars_by_sym, rm=rm)

    # Kiem tra trong so khop so tinh tay
    assert math.isclose(res["mean_weights"]["A"], 0.125, abs_tol=1e-9)
    assert math.isclose(res["mean_weights"]["B"], 0.200, abs_tol=1e-9)
    assert math.isclose(res["mean_weights"]["C"], 0.100, abs_tol=1e-9)

    # Kiem tra lo ro phien d_21 khop dung 0.0055
    assert len(res["losses"]) == 1
    assert math.isclose(res["losses"][0], 0.0055, abs_tol=1e-9)
    assert math.isclose(res["max_loss"], 0.0055, abs_tol=1e-9)
    assert math.isclose(res["p99_loss"], 0.0055, abs_tol=1e-9)
    assert res["days_over_threshold"] == 0
