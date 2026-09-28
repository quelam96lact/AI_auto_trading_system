"""Test cho scripts/screen_smc_stock_daily.py (Brief dot 101).

Test tren CHUOI NEN DUNG TAY, khong dung DB. Chin nhom theo muc 3 cua brief.
Cac con so trong test la so TINH TAY (ghi ro phep tinh o comment), khong phai
so lay tu chinh ham dang duoc kiem.

Gia nen dung tay khoang 100 dong nen cac test hinh dang truyen nguong thanh khoan
NHO (min_turnover=1.0) — tru mot test ghim 1 ty va mot test chung minh nguong
thanh khoan that su chan su kien (loi Claude bat o dot 99).
"""

from __future__ import annotations

import inspect
from datetime import UTC, date, datetime, timedelta

import pytest

from scripts import screen_vcp_daily as vcp
from scripts.screen_smc_stock_daily import (
    ALPHA,
    COOLDOWN_BARS,
    FRACTAL_K,
    IS_SIGNAL_END,
    IS_SIGNAL_START,
    MAIN_K,
    MIN_CONTROL,
    MIN_EVENTS,
    MIN_TURNOVER_VND,
    SWEEP_N,
    TARGET_KS,
    BasketEntry,
    baseline_for_basket,
    basket_for_day,
    bos_candidates,
    confirmed_swing_levels,
    count_drops,
    excess_k,
    find_all_events,
    find_bos_events,
    find_fvg_events,
    find_sweep_events,
    fvg_candidates,
    in_is_signal,
    make_basket_entry,
    median_of,
    missing_ks,
    sweep_candidates,
    top10_share,
    verdict_for_event,
)
from trading.calendar_vn import TZ
from trading.metrics import holm_adjust
from trading.models import Bar

T0 = date(2020, 1, 6)  # thu Hai


# --- dung chuoi nen -----------------------------------------------------------------

def _dates(start: date, n: int) -> list[date]:
    """n ngay giao dich (bo Thu Bay/Chu Nhat) ke tu start."""
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _bar(d: date, o: float, h: float, low: float, c: float, vol: float = 1000) -> Bar:
    return Bar(symbol="AAA", ts=datetime(d.year, d.month, d.day, tzinfo=TZ),
               open=o, high=h, low=low, close=c, volume=round(vol))


def _flat(n: int, price: float = 100.0, vol: float = 1000.0) -> list[Bar]:
    """n nen phang: open = close = price, high = price + 1, low = price - 1."""
    days = _dates(T0, n)
    return [_bar(d, price, price + 1.0, price - 1.0, price, vol) for d in days]


def _set(bars: list[Bar], i: int, o: float, h: float, low: float, c: float, vol: float = 1000.0) -> None:
    bars[i] = _bar(bars[i].ts.astimezone(TZ).date(), o, h, low, c, vol)


# --- 1. sweep ------------------------------------------------------------------------

def test_1a_sweep_thung_day_20_phien_va_dong_cua_tren_day():
    bars = _flat(25)
    t = 24
    # L = min(low[t-20..t-1]) = 99 (moi nen phang low = 99); low[t] = 98 < 99 va close = 100,5 > 99
    _set(bars, t, 100.0, 101.0, 98.0, 100.5)
    assert SWEEP_N == 20
    assert sweep_candidates(bars) == [t]
    assert find_sweep_events(bars, min_turnover=1.0) == [t]


def test_1b_sweep_dong_cua_BANG_day_thi_khong_phai_su_kien():
    bars = _flat(25)
    # close[t] = 99 = L -> dieu kien "close[t] > L" khong dat
    _set(bars, 24, 100.0, 101.0, 98.0, 99.0)
    assert sweep_candidates(bars) == []


def test_1c_sweep_low_BANG_day_thi_khong_phai_su_kien():
    bars = _flat(25)
    # low[t] = 99 = L -> dieu kien "low[t] < L" khong dat
    _set(bars, 24, 100.0, 101.0, 99.0, 100.5)
    assert sweep_candidates(bars) == []


def test_1d_sweep_can_du_20_phien_lich_su():
    bars = _flat(20)
    _set(bars, 19, 100.0, 101.0, 98.0, 100.5)
    assert sweep_candidates(bars) == []      # t = 19 < SWEEP_N = 20


# --- 2. bos --------------------------------------------------------------------------

def _series_with_swing() -> tuple[list[Bar], int]:
    """Chuoi 60 nen phang, nen j = 25 co high = 105 (hang xom high = 101) => swing high.

    Swing tai j chi duoc XAC NHAN tu nen j + 2 = 27 (fractal k = 2): cua so 23..27.
    j = 25 de moi su kien loc duoc (liquidity_ok doi t >= 20 moi tinh).
    """
    bars = _flat(60)
    _set(bars, 25, 100.0, 105.0, 99.0, 100.0)
    return bars, 25


def swing_high_level(bars, t, k=FRACTAL_K):
    """BAN THAM CHIEU CHI DUNG TRONG TEST (quet nguoc, cham, de doc): muc swing high da
    xac nhan gan nhat tai t. Doi chieu voi confirmed_swing_levels (ban tang dan chay that)
    o test_5d. Chuyen tu script sang day khi Claude audit dot 101."""
    from scripts.screen_vn30f_smc import _la_swing_high

    for j in range(min(t - k, len(bars) - k - 1), -1, -1):
        if _la_swing_high(bars, j, k):
            return bars[j].high
    return None


def test_2a_swing_high_chi_duoc_biet_tu_j_2():
    bars, j = _series_with_swing()
    assert FRACTAL_K == 2
    assert swing_high_level(bars, j - 1) is None      # chua co nen j
    assert swing_high_level(bars, j) is None          # tai chinh nen j: chua biet
    assert swing_high_level(bars, j + 1) is None      # j+1: van chua (thieu high[j+2])
    assert swing_high_level(bars, j + 2) == 105.0     # j+2: da xac nhan
    lv = confirmed_swing_levels(bars)                 # ham chay that, cung luat j+2
    assert lv[j] is None and lv[j + 1] is None and lv[j + 2] == 105.0


def test_2b_bos_pha_dinh_da_xac_nhan():
    bars, _j = _series_with_swing()
    # t = 28 (= j+3): close[27] = 100 <= 105 va close[28] = 106 > 105 -> pha dinh MOI
    _set(bars, 28, 100.0, 107.0, 100.0, 106.0)
    assert bos_candidates(bars) == [28]
    assert find_bos_events(bars, min_turnover=1.0) == [28]


def test_2c_khong_the_co_su_kien_bos_tai_t_bang_j_1_hoac_j_2():
    # Bang so: dat high[j+2] = 107 (chinh nen "pha dinh") thi swing tai j BI MAT,
    # vi fractal doi high[j] > high[j+2] (105 > 107 la sai).
    bars, j = _series_with_swing()
    _set(bars, j + 2, 100.0, 107.0, 100.0, 106.0)
    assert swing_high_level(bars, j + 2) is None
    assert confirmed_swing_levels(bars)[j + 2] is None
    assert bos_candidates(bars) == []


def test_2d_bos_bo_qua_neu_close_truoc_da_o_tren_swing():
    bars, _j = _series_with_swing()
    _set(bars, 30, 100.0, 107.0, 100.0, 106.0)         # t = 30: pha dinh that -> su kien
    _set(bars, 31, 106.0, 108.0, 105.0, 107.0)         # t = 31: close[30] = 106 > 105 -> khong pha MOI
    assert bos_candidates(bars) == [30]


def test_2e_bos_chua_co_swing_nao_thi_khong_co_su_kien():
    bars = _flat(60)
    _set(bars, 30, 100.0, 107.0, 100.0, 106.0)
    assert bos_candidates(bars) == []      # swing tai 30 chi duoc xac nhan tu 32 tro di


# --- 3. fvg --------------------------------------------------------------------------

def test_3a_fvg_low_bang_high_hai_nen_truoc_thi_khong_phai_su_kien():
    bars = _flat(10)
    _set(bars, 0, 100.0, 100.0, 99.0, 100.0)          # high[0] = 100
    _set(bars, 2, 100.0, 101.0, 100.0, 100.5)         # low[2] = 100 = high[0] -> khong "lon hon han"
    assert fvg_candidates(bars) == []


def test_3b_fvg_low_lon_hon_high_hai_nen_truoc_thi_la_su_kien():
    bars = _flat(10)
    _set(bars, 0, 100.0, 100.0, 99.0, 100.0)          # high[0] = 100
    _set(bars, 2, 100.0, 101.0, 100.5, 100.5)         # low[2] = 100,5 > 100
    assert fvg_candidates(bars) == [2]


def test_3c_fvg_can_it_nhat_hai_nen_truoc():
    bars = _flat(3)
    assert fvg_candidates(bars) == []                 # t = 2 la chi so dau tien duoc xet
    _set(bars, 2, 100.0, 101.0, 100.5, 100.5)
    _set(bars, 0, 100.0, 100.0, 99.0, 100.0)
    assert fvg_candidates(bars) == [2]


# --- 4. thoi gian nghi theo TUNG LOAI, TUNG MA --------------------------------------

def test_4a_hai_loai_khac_nhau_cach_5_nen_thi_ca_hai_duoc_tinh():
    bars = _flat(40)
    _set(bars, 24, 100.0, 101.0, 98.0, 100.5)         # sweep: low 98 < 99 = L, close 100,5 > 99
    _set(bars, 27, 100.0, 100.0, 99.0, 100.0)         # high[27] = 100
    _set(bars, 29, 100.0, 101.0, 100.5, 100.5)        # fvg: low[29] = 100,5 > high[27] = 100
    ev = find_all_events(bars, min_turnover=1.0)
    assert ev["sweep"] == [24]
    assert ev["fvg"] == [29]                          # chi cach 5 nen nhung KHAC loai -> van tinh
    assert ev["bos"] == []


def test_4b_hai_su_kien_cung_loai_cach_10_nen_thi_chi_giu_cai_dau():
    bars = _flat(50)
    _set(bars, 23, 100.0, 100.0, 99.0, 100.0)         # high[23] = 100
    _set(bars, 25, 100.0, 101.0, 100.5, 100.5)        # fvg tai t = 25
    _set(bars, 33, 100.0, 100.0, 99.0, 100.0)         # high[33] = 100
    _set(bars, 35, 100.0, 101.0, 100.5, 100.5)        # fvg tai t = 35 (cach 10 nen)
    assert COOLDOWN_BARS == 20
    assert fvg_candidates(bars) == [25, 35]                 # luat tho: ca hai
    assert find_fvg_events(bars, min_turnover=1.0) == [25]  # sau thoi gian nghi: chi con cai dau


def test_4c_nen_tin_hieu_volume_bang_0_thi_bo_va_dem_duoc():
    bars = _flat(25)
    _set(bars, 24, 100.0, 101.0, 98.0, 100.5, vol=0.0)
    drop: dict[str, int] = {}
    assert find_sweep_events(bars, min_turnover=1.0, drop=drop) == []
    assert drop == {"volume_0": 1}


# --- 5. khong nhin trom tuong lai ---------------------------------------------------

def _series_all_three() -> list[Bar]:
    """Chuoi 80 nen co du ba loai su kien: bos 30, sweep 45, fvg 60 (moi chi so >= 20)."""
    bars = _flat(80)
    _set(bars, 25, 100.0, 105.0, 99.0, 100.0)         # swing high tai j = 25 (xac nhan tu 27)
    _set(bars, 30, 100.0, 107.0, 100.0, 106.0)        # bos: close[29] = 100 <= 105, close[30] = 106 > 105
    _set(bars, 45, 100.0, 101.0, 98.0, 100.5)         # sweep: low 98 < 99 (min 20 nen truoc)
    _set(bars, 58, 100.0, 100.0, 99.0, 100.0)         # high[58] = 100
    _set(bars, 60, 100.0, 101.0, 100.5, 100.5)        # fvg: low[60] = 100,5 > high[58] = 100
    return bars


def test_5a_chuoi_dung_tay_co_du_ba_loai_su_kien():
    bars = _series_all_three()
    ev = find_all_events(bars, min_turnover=1.0)
    assert ev["bos"] == [30]
    assert ev["sweep"] == [45]
    assert ev["fvg"] == [60]


def test_5b_sua_moi_nen_sau_t_khong_doi_su_kien_tai_moi_nen_nho_hon_bang_t():
    bars = _series_all_three()
    base = find_all_events(bars, min_turnover=1.0)
    for cut in (0, 29, 44, 59, 79):
        mutated = list(bars)
        for i in range(cut + 1, len(mutated)):
            _set(mutated, i, 500.0, 999.0, 1.0, 500.0, vol=5000.0)
        got = find_all_events(mutated, min_turnover=1.0)
        for kind in ("sweep", "bos", "fvg"):
            assert [i for i in got[kind] if i <= cut] == [i for i in base[kind] if i <= cut], (cut, kind)


def test_5c_duong_tho_cung_bat_bien_theo_tuong_lai():
    bars = _series_all_three()
    for cut in (27, 45, 60):
        mutated = list(bars)
        for i in range(cut + 1, len(mutated)):
            _set(mutated, i, 500.0, 999.0, 1.0, 500.0, vol=5000.0)
        assert [i for i in sweep_candidates(mutated) if i <= cut] == [i for i in sweep_candidates(bars) if i <= cut]
        assert [i for i in bos_candidates(mutated) if i <= cut] == [i for i in bos_candidates(bars) if i <= cut]
        assert [i for i in fvg_candidates(mutated) if i <= cut] == [i for i in fvg_candidates(bars) if i <= cut]


def test_5d_muc_swing_tang_dan_khop_voi_ham_quet_nguoc():
    # Hai duong tinh DOC LAP: confirmed_swing_levels (tang dan, dung khi chay that) va
    # swing_high_level (quet nguoc O(n)). Lech nhau => test nay do.
    for bars in (_series_all_three(), _series_with_swing()[0], _flat(30)):
        inc = confirmed_swing_levels(bars)
        assert len(inc) == len(bars)
        for t in range(len(bars)):
            assert inc[t] == swing_high_level(bars, t), t


# --- 6. khung 40 ---------------------------------------------------------------------

def test_6_khung_40_thieu_nen_thi_co_r10_r20_ma_khong_co_r40_va_dem_duoc():
    bars = _flat(61)
    t = 30
    from scripts.screen_vcp_daily import compute_targets
    tg = compute_targets(bars, t, TARGET_KS)
    assert TARGET_KS == (10, 20, 40)
    assert tg[10] is not None and tg[20] is not None      # t+10 = 40, t+20 = 50 < 61
    assert tg[40] is None                                 # t+40 = 70 >= 61
    assert missing_ks(tg) == [40]
    drop: dict[str, int] = {}
    count_drops(tg, drop)
    assert drop == {"thieu_du_lieu_40": 1}


def test_6b_du_nen_thi_khong_thieu_khung_nao():
    bars = _flat(80)
    from scripts.screen_vcp_daily import compute_targets
    tg = compute_targets(bars, 30, TARGET_KS)
    assert missing_ks(tg) == []
    drop: dict[str, int] = {}
    count_drops(tg, drop)
    assert drop == {}


# --- 7. ro doi chung -----------------------------------------------------------------

def _liquid_bars(n: int = 80, price: float = 100.0, vol: float = 20_000_000.0) -> list[Bar]:
    """close x volume = 100 x 20.000.000 = 2 ty >= 1 ty (80 nen de du ca khung 40)."""
    return _flat(n, price=price, vol=vol)


def test_7a_ro_chi_gom_ma_dat_thanh_khoan_va_khong_co_ma_su_kien():
    entries = {}
    for sym, bars in (("AAA", _liquid_bars()), ("BBB", _liquid_bars()),
                      ("CCC", _liquid_bars()), ("DDD", _liquid_bars(vol=1000.0))):
        e = make_basket_entry(sym, bars, 25, "HOSE")
        if e is not None:
            entries[sym] = e
    assert set(entries) == {"AAA", "BBB", "CCC"}          # DDD bi loai vi duoi nguong thanh khoan
    assert entries["AAA"].r_of(40) is not None            # ma su kien van co du du lieu
    basket = basket_for_day(entries, "AAA")
    assert [e.symbol for e in basket] == ["BBB", "CCC"]   # ro KHONG gom chinh ma su kien


def test_7b_ro_duoi_5_ma_thi_bo_khoi_phep_so_vuot_troi():
    assert MIN_CONTROL == 5
    entries = {f"X{i}": BasketEntry(f"X{i}", {10: 0.01, 20: 0.02, 40: 0.03}) for i in range(2)}
    basket = basket_for_day(entries, "AAA")
    baseline, n = baseline_for_basket(basket, MAIN_K)
    assert n == 2
    assert baseline is not None
    _b, excess, n2 = excess_k(0.10, basket, MAIN_K)
    assert excess is None and n2 == 2                     # ro < 5 -> khong so vuot troi


def test_7c_ro_du_5_ma_thi_tinh_duoc_excess_bang_trung_binh_tinh_tay():
    r = {10: 0.01, 20: 0.02, 40: 0.03}
    entries = {f"X{i}": BasketEntry(f"X{i}", dict(r)) for i in range(5)}
    basket = basket_for_day(entries, "AAA")
    baseline, n = baseline_for_basket(basket, MAIN_K)
    assert n == 5 and baseline == pytest.approx(0.02)
    _b, excess, _n = excess_k(0.10, basket, MAIN_K)
    assert excess == pytest.approx(0.08)                  # 0,10 - 0,02


def test_7d_ma_thieu_muc_tieu_khong_tinh_vao_ro():
    entries = {
        "B": BasketEntry("B", {10: 0.01, 20: 0.02, 40: None}),   # B thieu r_40
        "C": BasketEntry("C", {10: 0.03, 20: 0.04, 40: 0.03}),
    }
    basket = basket_for_day(entries, "AAA")
    baseline, n = baseline_for_basket(basket, 40)
    assert n == 1 and baseline == pytest.approx(0.03)      # chi C duoc tinh o khung 40
    baseline10, n10 = baseline_for_basket(basket, 10)
    assert n10 == 2 and baseline10 == pytest.approx(0.02)  # (0,01 + 0,03)/2


# --- 8. Holm -------------------------------------------------------------------------

def test_8a_holm_p_010_020_040_thi_ca_ba_dat():
    # 0,05/3 = 0,01667 ; 0,05/2 = 0,025 ; 0,05/1 = 0,05
    # 0,010 <= 0,01667 (dat) ; 0,020 <= 0,025 (dat) ; 0,040 <= 0,05 (dat) -> ca ba DAT
    out = holm_adjust({"a": 0.010, "b": 0.020, "c": 0.040})
    assert out == {"a": True, "b": True, "c": True}


def test_8b_holm_p_020_020_040_thi_ca_ba_khong_dat():
    # 0,020 <= 0,01667 ? KHONG -> dung ngay, cac gia tri sau cung khong dat
    out = holm_adjust({"a": 0.020, "b": 0.020, "c": 0.040})
    assert out == {"a": False, "b": False, "c": False}


def test_8c_holm_p_001_030_040_thi_chi_cai_dau_dat():
    # 0,001 <= 0,01667 (dat) ; 0,030 <= 0,025 ? KHONG -> dung o day
    out = holm_adjust({"a": 0.001, "b": 0.030, "c": 0.040})
    assert out == {"a": True, "b": False, "c": False}


def test_8d_holm_giu_dung_ten_su_kien_khi_sap_xep():
    # "fvg" p nho nhat, "bos" lon nhat -> phai tra ve dung ten, khong tra ve theo thu tu sap
    out = holm_adjust({"sweep": 0.040, "bos": 0.001, "fvg": 0.020})
    assert out == {"bos": True, "fvg": True, "sweep": True}
    assert ALPHA == 0.05


# --- 9. moc IS -----------------------------------------------------------------------

def test_9a_ngay_tin_hieu_2022_11_01_nam_ngoai_IS():
    assert IS_SIGNAL_START == date(2016, 1, 4)
    assert IS_SIGNAL_END == date(2022, 10, 31)
    assert in_is_signal(date(2022, 10, 31)) is True
    assert in_is_signal(date(2022, 11, 1)) is False


def test_9b_nen_ts_2022_10_31_17h_UTC_la_ngay_01_11_gio_VN_nam_ngoai_IS():
    b = Bar(symbol="AAA", ts=datetime(2022, 10, 31, 17, 0, tzinfo=UTC),
            open=100.0, high=101.0, low=99.0, close=100.0, volume=1000)
    d = vcp.bar_date(b)
    assert d == date(2022, 11, 1)
    assert in_is_signal(d) is False
    assert in_is_signal(date(2016, 1, 3)) is False


# --- 10 + 11. nguong thanh khoan 1 ty (bat buoc cua brief) --------------------------

def test_10_ghim_lan_chay_that_dung_nguong_1_ty():
    assert MIN_TURNOVER_VND == 1_000_000_000.0
    assert MIN_TURNOVER_VND == vcp.MIN_TURNOVER_VND           # khong duoc lech voi dot 99
    for fn in (find_sweep_events, find_bos_events, find_fvg_events, find_all_events, make_basket_entry):
        assert inspect.signature(fn).parameters["min_turnover"].default == 1_000_000_000.0, fn.__name__


def test_11_su_kien_duoi_nguong_thanh_khoan_KHONG_duoc_tinh():
    # close x volume = 100 x 1000 = 100 nghin dong < 1 ty; hinh dang sweep la hop le
    bars = _flat(25, vol=1000.0)
    _set(bars, 24, 100.0, 101.0, 98.0, 100.5)
    assert find_sweep_events(bars) == []                      # dung nguong san xuat 1 ty
    assert find_sweep_events(bars, min_turnover=1.0) == [24]  # ha nguong thi moi thay
    assert find_all_events(bars)["sweep"] == []
    drop: dict[str, int] = {}
    find_sweep_events(bars, drop=drop)
    assert drop == {"duoi_thanh_khoan": 1}


# --- 12. ket luan va do lech ---------------------------------------------------------

def test_12a_khong_du_su_kien_thi_IT_SU_KIEN():
    assert MIN_EVENTS == 100
    assert verdict_for_event(99, True, 0.01, 0.01).startswith("IT_SU_KIEN")
    assert verdict_for_event(100, True, 0.01, 0.01) == "CO_LOI_THE"   # dung bang nguong van ket luan


def test_12b_can_ca_ba_dieu_kien_moi_ket_luan_CO_LOI_THE():
    assert verdict_for_event(315, True, 0.01, 0.01) == "CO_LOI_THE"
    assert verdict_for_event(315, False, 0.01, 0.01) == "KHONG_CO_LOI_THE"    # khong dat Holm
    assert verdict_for_event(315, True, -0.01, 0.01) == "KHONG_CO_LOI_THE"    # r_net trung binh <= 0
    assert verdict_for_event(315, True, 0.01, 0.0) == "KHONG_CO_LOI_THE"      # trung vi = 0, khong > 0
    assert verdict_for_event(315, True, 0.01, None) == "KHONG_CO_LOI_THE"


def test_12c_ty_trong_10_su_kien_lon_nhat():
    # 10 so 1,0 va mot so -9,0: tong = 1,0; top 10 = 10,0 -> 1000%
    assert top10_share([1.0] * 10 + [-9.0]) == pytest.approx(10.0)
    assert top10_share([]) is None
    assert top10_share([-1.0, -2.0]) == pytest.approx(1.0)   # it hon 10 -> lay het -> bang 1
    assert top10_share([1.0, -1.0]) is None                  # tong = 0 -> khong chia duoc


def test_12d_trung_vi_tinh_tay():
    assert median_of([1.0]) == pytest.approx(1.0)            # le -> chinh giua
    assert median_of([1.0, 3.0]) == pytest.approx(2.0)       # chan -> trung binh hai so giua
    assert median_of([3.0, 1.0, 2.0]) == pytest.approx(2.0)  # chua sap xep van dung
    assert median_of([]) is None
