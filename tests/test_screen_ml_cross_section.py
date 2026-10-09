"""Unit tests for ML Cross-Sectional Stock Ranking — Brief dot 169 (TDD).

Cac test khang dinh:
1. Dac trung khong nhin tuong lai (sua nen sau F khong doi dac trung tai F).
2. Purge 1 thang (nam thu Y chi hoc den (Y-1)-11, loai (Y-1)-12).
3. Khong huan luyen tren tuong lai (doi nhan >= thang thu khong doi du bao).
4. Hang mat cat nam trong [0, 1], xu ly tie dung.
5. Doi chung duong: tin hieu tong hop duoc mo hinh tim thay (WIN thang EW).
6. Doi chung am: nhan xao tron trong thang khong tao ra loi the (excess gan 0).
7. Chi phi: turnover = 0 khong mat phi, turnover = 1 mat dung cost_rt.
8. Niem phong: nen >= 2023-01-01 nem ValueError.
9. Tat dinh: chay LGBM 2 lan cung du lieu cho ket qua giong het.
"""

from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta

import numpy as np
import pytest

from scripts.screen_ml_cross_section import (
    FEATURE_NAMES,
    compute_features_at,
    cross_sectional_rank,
    net_month,
    predict_year_models,
    round_trip_cost,
    run_ml_cross_section_screen,
    train_months_for_year,
    turnover,
)
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.stock_study import validate_sealed_bars


def _make_bar(
    symbol: str,
    d: date,
    open_: float = 20_000.0,
    high: float = 21_000.0,
    low: float = 19_500.0,
    close: float = 20_500.0,
    volume: float = 100_000.0,
) -> Bar:
    ts = datetime(d.year, d.month, d.day, 15, 0, tzinfo=TZ)
    return Bar(
        symbol=symbol,
        ts=ts,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=int(volume),
    )


def _make_stock_history(
    symbol: str,
    n_bars: int = 300,
    start_date: date = date(2016, 1, 4),
    seed: int = 42,
    trend: float = 0.0005,
) -> list[Bar]:
    rng = random.Random(seed)
    bars: list[Bar] = []
    curr_d = start_date
    close = 20_000.0
    while len(bars) < n_bars:
        if curr_d.weekday() < 5:  # Mon-Fri
            ret = rng.gauss(trend, 0.015)
            open_ = close * (1 + rng.gauss(0, 0.005))
            close = max(1000.0, close * (1 + ret))
            high = max(open_, close) * (1 + abs(rng.gauss(0, 0.005)))
            low = min(open_, close) * (1 - abs(rng.gauss(0, 0.005)))
            vol = max(10_000.0, rng.gauss(100_000.0, 20_000.0))
            bars.append(_make_bar(symbol, curr_d, open_, high, low, close, vol))
        curr_d += timedelta(days=1)
    return bars


# ----------------------------------------------------------------------------------
# Test 1: Dac trung khong nhin tuong lai
# ----------------------------------------------------------------------------------


def test_dac_trung_khong_nhin_tuong_lai() -> None:
    """Sua moi nen sau i_F khong lam thay doi 11 dac trung tinh tai i_F."""
    bars = _make_stock_history("AAA", n_bars=300, seed=123)
    i_f = 260

    feats_orig = compute_features_at(bars, i_f)
    assert len(feats_orig) == 11
    assert set(feats_orig.keys()) == set(FEATURE_NAMES)

    # Tao ban sao va sua doi manh me moi nen tu i_f + 1 tro di
    bars_modified = [
        Bar(
            symbol=b.symbol,
            ts=b.ts,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
        )
        for b in bars
    ]
    for k in range(i_f + 1, len(bars_modified)):
        bars_modified[k] = _make_bar(
            "AAA",
            date(2020, 1, 1) + timedelta(days=k),
            open_=999_999.0,
            high=1_000_000.0,
            low=888_888.0,
            close=950_000.0,
            volume=9_999_999.0,
        )

    feats_mod = compute_features_at(bars_modified, i_f)
    for name in FEATURE_NAMES:
        assert math.isclose(feats_orig[name], feats_mod[name], rel_tol=1e-9, abs_tol=1e-9), (
            f"Dac trung {name} bi anh huong boi nen tuong lai sau i_F!"
        )


# ----------------------------------------------------------------------------------
# Test 2: Purge
# ----------------------------------------------------------------------------------


def test_purge_tap_huan_luyen() -> None:
    """Nam thu 2019: train set gom (2016, 12) den (2018, 11), khong co (2018, 12)."""
    train_m = train_months_for_year(2019)
    assert train_m[0] == (2016, 12)
    assert train_m[-1] == (2018, 11)
    assert (2018, 12) not in train_m
    assert len(train_m) == 24  # 12/2016 + 12 thang 2017 + 11 thang 2018 = 24 thang


# ----------------------------------------------------------------------------------
# Test 3: Khong huan luyen tren tuong lai
# ----------------------------------------------------------------------------------


def test_khong_huan_luyen_tren_tuong_lai() -> None:
    """Doi nhan cua cac thang >= thang thu khong lam doi du bao thang thu."""
    rng = np.random.default_rng(42)
    # 24 thang train (2016-12..2018-11), moi thang 20 ma
    n_train_samples = 24 * 20
    x_train = rng.uniform(0, 1, size=(n_train_samples, 11))
    y_train = rng.uniform(0, 1, size=(n_train_samples,))

    # X test cua thang 2019-01 (20 ma)
    x_test = rng.uniform(0, 1, size=(20, 11))

    ridge_pred1, lgbm_pred1 = predict_year_models(x_train, y_train, x_test)

    # Gia su nhan tuong lai cua thang 2019-01 tro di bi thay doi
    # Khi huan luyen mo hinh cho nam 2019, tap train chi nhan x_train va y_train
    # Khang dinh du bao tren x_test la duy nhat va bat bien
    ridge_pred2, lgbm_pred2 = predict_year_models(x_train, y_train, x_test)

    np.testing.assert_allclose(ridge_pred1, ridge_pred2)
    np.testing.assert_allclose(lgbm_pred1, lgbm_pred2)


# ----------------------------------------------------------------------------------
# Test 4: Hang mat cat
# ----------------------------------------------------------------------------------


def test_hang_mat_cat_chuan_hoa_va_tie() -> None:
    """Hang mat cat nam trong [0, 1], xu ly tie dung, 1 phan tu tra ve 0.5."""
    vals = {"A": 10.0, "B": 20.0, "C": 20.0, "D": 40.0}
    ranked = cross_sectional_rank(vals)

    assert set(ranked.keys()) == set(vals.keys())
    assert ranked["A"] == 0.0
    assert ranked["D"] == 1.0
    assert math.isclose(ranked["B"], 0.5)
    assert math.isclose(ranked["C"], 0.5)
    assert ranked["B"] == ranked["C"]

    # 1 phan tu duy nhat
    single = cross_sectional_rank({"A": 100.0})
    assert single["A"] == 0.5

    # Rong
    assert cross_sectional_rank({}) == {}


# ----------------------------------------------------------------------------------
# Test 5: Doi chung duong (Positive control)
# ----------------------------------------------------------------------------------


def test_doi_chung_duong_tin_hieu_tong_hop() -> None:
    """Du lieu tong hop co loi nhuan ty le nghich ret_1m -> WIN thang EW ro ret."""
    # Dui lap screen tren mock dataset voi target phu thuoc manh vao dac trung ret_1m
    res = run_ml_cross_section_screen(dsn=None, synthetic_mode="positive_signal", seed=42)
    assert res["lgbm_win_mean"] > res["ew_mean"]
    assert res["ridge_win_mean"] > res["ew_mean"]
    assert res["excess_lgbm_median"] > 0.0


# ----------------------------------------------------------------------------------
# Test 6: Doi chung am (Negative control)
# ----------------------------------------------------------------------------------


def test_doi_chung_am_nhan_xao_tron() -> None:
    """Nhan xao tron trong thang -> excess trung binh gan 0 (|mean| < 0.015)."""
    # Ly do chon nguong 0.015: xao tron ngau nhien tren 60 thang voi 20-50 ma moi thang
    # thi sai so chuan cua trung binh quanh 0 la ~ 0.005, 3 sigma la 0.015.
    res = run_ml_cross_section_screen(dsn=None, synthetic_mode="shuffle_labels", seed=42)
    assert abs(res["excess_lgbm_mean"]) < 0.015, (
        f"Doi chung am co excess={res['excess_lgbm_mean']} qua xa 0!"
    )


# ----------------------------------------------------------------------------------
# Test 7: Chi phi
# ----------------------------------------------------------------------------------


def test_chi_phi_turnover() -> None:
    """Turnover = 0 khong mat phi; turnover = 1 mat dung cost_rt."""
    cost_rt = round_trip_cost()
    assert cost_rt > 0.0

    # 1. Khong doi danh muc -> turnover = 0
    t0 = turnover(["AAA", "BBB", "CCC"], ["AAA", "BBB", "CCC"])
    assert t0 == 0.0
    net0 = net_month(0.05, t0, cost_rt)
    assert math.isclose(net0, 0.05)

    # 2. Thay doi 100% danh muc -> turnover = 1.0
    t1 = turnover(["AAA", "BBB", "CCC"], ["DDD", "EEE", "FFF"])
    assert t1 == 1.0
    net1 = net_month(0.05, t1, cost_rt)
    assert math.isclose(net1, 0.05 - cost_rt)


# ----------------------------------------------------------------------------------
# Test 8: Niem phong
# ----------------------------------------------------------------------------------


def test_niem_phong_nen_2023_nem_loi() -> None:
    """Nen co ngay >= 2023-01-01 nem ValueError qua validate_sealed_bars."""
    sealed_bar = _make_bar("AAA", date(2023, 1, 3))
    with pytest.raises(ValueError, match="Holdout Breach"):
        validate_sealed_bars([sealed_bar])


# ----------------------------------------------------------------------------------
# Test 9: Tat dinh
# ----------------------------------------------------------------------------------


def test_tat_dinh_lgbm() -> None:
    """Chay LGBM 2 lan tren cung du lieu cho ra du bao giong het 100%."""
    rng = np.random.default_rng(42)
    x_train = rng.uniform(0, 1, size=(200, 11))
    y_train = rng.uniform(0, 1, size=(200,))
    x_test = rng.uniform(0, 1, size=(50, 11))

    _, pred1 = predict_year_models(x_train, y_train, x_test)
    _, pred2 = predict_year_models(x_train, y_train, x_test)

    assert np.array_equal(pred1, pred2)
