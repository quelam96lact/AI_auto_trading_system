"""Test cho scripts/screen_vcp_daily.py (Brief dot 99).

Test tren CHUOI NEN DUNG TAY, khong dung DB. Muoi hai nhom theo muc 3 cua brief.
Cac con so trong test la so TINH TAY (ghi ro phep tinh o comment), khong phai
so lay tu chinh ham dang duoc kiem.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime, timedelta

import pytest

from scripts.screen_vcp_daily import (
    COOLDOWN_BARS,
    DEPTH_MAX_S1,
    DEPTH_MAX_S3,
    IS_SIGNAL_END,
    IS_SIGNAL_START,
    MIN_CONTROL,
    MIN_TURNOVER_VND,
    TARGET_KS,
    ControlEntry,
    apply_cooldown,
    bar_date,
    base_depths,
    basket_baseline,
    bootstrap_by_month,
    breakout_ok,
    compute_targets,
    entry_status,
    excess_for_event,
    find_events,
    in_is,
    is_ceiling_open,
    liquidity_ok,
    month_key,
    net_return,
    pivot_price,
    rolling_max,
    rolling_mean,
    rolling_min,
    trend_conditions,
    trend_filter_ok,
    validate_sealed_bars,
    vcp_base_ok,
)
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS

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


def _uptrend(days: list[date], n: int = 240, start: float = 40.0, end: float = 105.0) -> list[Bar]:
    """n nen xu huong tang deu tu start toi end (moi nen cao hon nen truoc)."""
    out: list[Bar] = []
    p = start
    step = (end - start) / n
    for i in range(n):
        o, c = p, p + step
        out.append(_bar(days[i], o, c + 0.3, o - 0.3, c))
        p = c
    return out


def _seg(days: list[date], i0: int, hi: float, depth: float, vol: float, mid: float,
         n: int = 20) -> list[Bar]:
    """Mot doan nen VCP: nen dau quet het bien do (high = hi, low = hi x (1 - depth)),
    cac nen sau nam gon ben trong; close moi nen = mid."""
    lo = hi * (1.0 - depth)
    out = [_bar(days[i0], mid, hi, lo, mid, vol)]
    for k in range(1, n):
        out.append(_bar(days[i0 + k], mid, hi - 0.2, lo + 0.2, mid, vol))
    return out


# Cac test hinh dang mau truyen min_turnover=0.0: nen dung tay co gia ~100 dong nen
# khong the qua nguong 1 ty; thanh khoan duoc kiem rieng o test_1i voi nguong that.
def _base_series(
    *,
    depths: tuple[float, float, float] = (0.30, 0.15, 0.06),
    vol_scale: tuple[float, float, float] = (3.0, 2.0, 1.0),
    s1_low: float | None = None,
    uptrend_start: float = 40.0,
    breakout_close: float = 102.5,
    breakout_vol: float = 5000.0,
    n_after: int = 0,
) -> tuple[list[Bar], int]:
    """Chuoi 301 nen (+ n_after): 240 nen xu huong tu uptrend_start -> 105, 60 nen nen VCP
    (3 doan 20 nen), roi 1 nen pha vo tai t = 300. close[t-1] = 99; pivot P = 100."""
    days = _dates(T0, 301 + n_after)
    bars = _uptrend(days, start=uptrend_start)
    mids = (95.0, 97.5, 99.0)
    for seg in range(3):
        hi = 100.0
        if seg == 0 and s1_low is not None:
            depth = (hi - s1_low) / hi
        else:
            depth = depths[seg]
        bars += _seg(days, 240 + seg * 20, hi, depth, 1000.0 * vol_scale[seg], mids[seg])
    t = 300
    bars.append(_bar(days[t], 100.0, breakout_close + 0.5, 99.5, breakout_close, breakout_vol))
    for j in range(1, n_after + 1):
        prev = bars[-1].close
        bars.append(_bar(days[t + j], prev, prev + 1.2, prev - 0.2, prev + 1.0, breakout_vol))
    return bars, t


def _two_base_series() -> tuple[list[Bar], int, int]:
    """Chuoi co HAI su kien VCP that: tai t1 = 300 va t2 = 361 (cach nhau 61 nen).

    Nen VCP thu hai: 60 nen high 105 (do sau 30/15/6 phan tram), roi nen pha vo tai 361
    dong cua 106,5 > pivot 105.
    """
    days = _dates(T0, 362)
    bars = _uptrend(days)
    for seg, (d, v, mid) in enumerate(
        zip((0.30, 0.15, 0.06), (3000.0, 2000.0, 1000.0), (95.0, 97.5, 99.0), strict=True)
    ):
        bars += _seg(days, 240 + seg * 20, 100.0, d, v, mid)
    t1 = 300
    bars.append(_bar(days[t1], 100.0, 103.0, 99.5, 102.5, 5000.0))
    for seg, (d, v, mid) in enumerate(
        zip((0.30, 0.15, 0.06), (3000.0, 2000.0, 1000.0), (100.0, 102.5, 104.0), strict=True)
    ):
        bars += _seg(days, 301 + seg * 20, 105.0, d, v, mid)
    t2 = 361
    bars.append(_bar(days[t2], 105.0, 107.0, 104.5, 106.5, 5000.0))
    assert len(bars) == 362
    return bars, t1, t2


# --- 3.1 SMA, bo loc xu huong (7 dieu kien) ---------------------------------------

def test_1a_bo_loc_xu_huong_dung_ca_7_dieu_kien_tren_chuoi_dung_tay():
    bars, t = _base_series()
    cond = trend_conditions(bars, t)
    assert all(cond.values()), cond
    assert trend_filter_ok(bars, t) is True


def test_1b_lam_hong_dieu_kien_1_close_khong_con_tren_SMA150_200():
    # sup giam o 10 nen cuoi -> close[t-1] = 60 < SMA150 va SMA200
    bars, t = _base_series()
    for i in range(290, 300):
        bars[i] = _bar(bars[i].ts.astimezone(TZ).date(), 60.0, 61.0, 59.0, 60.0, 1000.0)
    cond = trend_conditions(bars, t)
    assert cond["c1_close_tren_sma150_200"] is False
    assert trend_filter_ok(bars, t) is False


def test_1c_lam_hong_dieu_kien_2_va_3_sma150_khong_con_tren_sma200():
    # 200 nen gia 200 roi 100 nen gia 100: SMA200 = 150 > SMA150 = 100, va SMA200 di xuong
    days = _dates(T0, 301)
    bars = [_bar(days[i], 200.0, 201.0, 199.0, 200.0) for i in range(200)]
    bars += [_bar(days[200 + i], 100.0, 101.0, 99.0, 100.0) for i in range(101)]
    cond = trend_conditions(bars, 300)
    assert cond["c2_sma150_tren_sma200"] is False
    assert cond["c3_sma200_di_len"] is False
    assert trend_filter_ok(bars, 300) is False


def test_1d_lam_hong_dieu_kien_4_va_5_sma50_khong_con_tren_sma150():
    # 200 nen gia 200 roi 61 nen gia 100: SMA50 = 100, SMA150 = (90x200 + 60x100)/150 = 160
    days = _dates(T0, 261)
    bars = [_bar(days[i], 200.0, 201.0, 199.0, 200.0) for i in range(200)]
    bars += [_bar(days[200 + i], 100.0, 101.0, 99.0, 100.0) for i in range(61)]
    cond = trend_conditions(bars, 260)
    assert cond["c4_sma50_tren_sma150_200"] is False
    assert cond["c5_close_tren_sma50"] is False
    assert trend_filter_ok(bars, 260) is False


def test_1e_lam_hong_dieu_kien_6_day_thap_hon_130pct_low_252_nen():
    # Ca 252 nen gan nhat deu co low cao (xu huong bat dau tu 80, nen VCP nong 15/10/6 phan tram)
    # -> min low = 84,8; can close >= 1,3 x 84,8 = 110,2 > 99 -> hong
    bars, t = _base_series(depths=(0.15, 0.10, 0.06), uptrend_start=80.0)
    cond = trend_conditions(bars, t)
    assert cond["c6_cach_day_252_nen"] is False
    assert trend_filter_ok(bars, t) is False


def test_1f_lam_hong_dieu_kien_7_dinh_cu_qua_cao():
    # mot nen trong 252 nen co high = 200 -> can close >= 0,75 x 200 = 150 > 99 -> hong
    bars, t = _base_series()
    b = bars[120]
    bars[120] = dataclasses.replace(b, high=200.0)
    cond = trend_conditions(bars, t)
    assert cond["c7_gan_dinh_252_nen"] is False
    assert trend_filter_ok(bars, t) is False


def test_1g_thieu_lich_su_252_nen_thi_khong_xet():
    bars, _t = _base_series()
    assert trend_filter_ok(bars, 100) is False      # chi co 100 nen lich su
    assert trend_filter_ok(bars, 251) is False


# --- 3.2 nen VCP ------------------------------------------------------------------

def test_2a_nen_dung_30_15_6_phan_tram_va_volume_can_dan():
    bars, t = _base_series()
    assert vcp_base_ok(bars, t) is True
    d1, d2, d3 = base_depths(bars, t)
    assert d1 == pytest.approx(0.30) and d2 == pytest.approx(0.15) and d3 == pytest.approx(0.06)


def test_2b_doi_depth2_nho_hon_depth3_thi_khong_dat():
    bars, t = _base_series(depths=(0.30, 0.05, 0.10))
    assert vcp_base_ok(bars, t) is False


def test_2c_depth3_bang_011_thi_khong_dat():
    bars, t = _base_series(depths=(0.30, 0.15, 0.11))
    assert base_depths(bars, t)[2] == pytest.approx(0.11)
    assert vcp_base_ok(bars, t) is False


def test_2d_depth1_tren_035_thi_khong_dat():
    bars, t = _base_series(depths=(0.40, 0.15, 0.06))
    assert vcp_base_ok(bars, t) is False
    assert DEPTH_MAX_S1 == 0.35 and DEPTH_MAX_S3 == 0.10


def test_2e_volume_S3_lon_hon_S1_thi_khong_dat():
    bars, t = _base_series(vol_scale=(1.0, 2.0, 3.0))
    assert vcp_base_ok(bars, t) is False


# --- 3.3 nen pha vo ---------------------------------------------------------------

def test_3a_close_bang_dung_pivot_thi_khong_phai_pha_vo():
    bars, t = _base_series(breakout_close=100.0)     # P = max high S3 = 100
    assert pivot_price(bars, t) == pytest.approx(100.0)
    assert breakout_ok(bars, t) is False


def test_3b_volume_149_lan_thi_khong_dat_150_lan_thi_dat():
    bars, t = _base_series()
    # trung binh volume 50 nen truoc t: (10x3000 + 20x2000 + 20x1000)/50 = 1800
    assert rolling_mean([b.volume for b in bars], 50)[t - 1] == pytest.approx(1800.0)
    bars_149, _ = _base_series(breakout_vol=1800.0 * 1.49)
    bars_150, _ = _base_series(breakout_vol=1800.0 * 1.5)
    assert breakout_ok(bars_149, t) is False
    assert breakout_ok(bars_150, t) is True


# --- 3.4 thoi gian nghi ------------------------------------------------------------

def test_4a_thoi_gian_nghi_10_nen_bi_bo_21_nen_duoc_giu():
    assert apply_cooldown([100, 110]) == [100]              # cach 10 < 20 -> bo
    assert apply_cooldown([100, 121]) == [100, 121]         # cach 21 >= 20 -> giu
    assert COOLDOWN_BARS == 20


def test_4b_find_events_giu_hai_su_kien_cach_xa_nhau():
    # Hai su kien VCP THAT cach nhau 61 nen (nen VCP can 60 nen, nen khong the cach 10 nen)
    bars, t1, t2 = _two_base_series()
    events = find_events(bars, min_turnover=0.0)
    assert events == [t1, t2], events
    assert t2 - t1 == 61


# --- 3.5 gia tran theo san --------------------------------------------------------

def test_5a_hose_mo_tran_thi_bo_mo_685pct_thi_giu():
    # tran HOSE: open >= 100 x (1 + 0,07 - 0,001) = 106,9
    assert is_ceiling_open(100.0, 106.95, "HOSE") is True     # +6,95%
    assert is_ceiling_open(100.0, 106.85, "HOSE") is False    # +6,85%


def test_5b_hnx_tran_10pct_va_san_la_thi_dung_7pct():
    assert is_ceiling_open(100.0, 109.95, "HNX") is True      # +9,95%
    assert is_ceiling_open(100.0, 109.5, "HNX") is False
    assert is_ceiling_open(100.0, 106.95, "SAN_LA") is True   # san khong ro -> 7%
    assert is_ceiling_open(100.0, 106.85, "SAN_LA") is False


def test_5c_entry_status_bo_vi_tran_vi_volume_0_vi_thieu_nen_sau():
    bars, t = _base_series(n_after=1)
    assert entry_status(bars, t, "HOSE") == "ok"
    b = bars[t + 1]
    # tran so voi close[t] = 102,5: 102,5 x 1,069 = 109,57
    bars[t + 1] = dataclasses.replace(b, open=110.0)
    assert entry_status(bars, t, "HOSE") == "ceiling"
    bars[t + 1] = dataclasses.replace(b, open=103.0, volume=0)
    assert entry_status(bars, t, "HOSE") == "zero_volume"
    bars2, t2 = _base_series()                                # chi 301 nen: khong co nen t+1
    assert entry_status(bars2, t2, "HOSE") == "no_bar"


# --- 3.6 cong thuc loi nhuan rong --------------------------------------------------

def test_6_loi_nhuan_rong_tinh_tay_voi_hang_so_import():
    # vao 10.000, thoat 11.000; s = 5/10.000 = 0,0005
    # tu so: 11.000 x (1 - 0,0025 - 0,001 - 0,0005) = 11.000 x 0,996 = 10.956 = 2 x 5.478
    # mau so: 10.000 x (1 + 0,0025 + 0,0005)       = 10.000 x 1,003 = 10.030 = 2 x 5.015
    # r_net = 5.478 / 5.015 - 1 = 0,092323030907... (phan so da rut gon, tinh tay)
    assert (FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS) == (0.0025, 0.001, 5)
    assert net_return(10_000.0, 11_000.0) == pytest.approx(5478 / 5015 - 1, abs=1e-15)
    # loi nhuan gop phai khac (khong duoc tra ve so gop khi hoi so rong)
    assert net_return(10_000.0, 11_000.0) < 0.10
    assert net_return(10_000.0, 10_000.0) < 0.0


# --- 3.7 chong nhin trom tuong lai (quan trong nhat) -------------------------------

def test_7_sua_moi_nen_sau_t_khong_doi_su_kien_bo_loc_va_nen():
    bars, t = _base_series()
    base_events = find_events(bars, min_turnover=0.0)
    assert base_events[0] == t

    for cut in (t - 1, t - 30, t):
        mutated = list(bars)
        for i in range(cut + 1, len(mutated)):
            b = mutated[i]
            mutated[i] = _bar(b.ts.astimezone(TZ).date(), 500.0, 999.0, 1.0, 500.0, 1.0)
        assert trend_filter_ok(mutated, cut) == trend_filter_ok(bars, cut)
        assert vcp_base_ok(mutated, cut) == vcp_base_ok(bars, cut)
        assert breakout_ok(mutated, cut) == breakout_ok(bars, cut)
        got = [e for e in find_events(mutated, min_turnover=0.0) if e <= cut]
        assert got == [e for e in base_events if e <= cut]


def test_7b_muc_tieu_duoc_phep_doi_khi_sua_nen_sau_t():
    bars, t = _base_series(n_after=25)
    r_before = compute_targets(bars, t, (5,))
    mutated = list(bars)
    for i in range(t + 1, len(mutated)):
        b = mutated[i]
        mutated[i] = _bar(b.ts.astimezone(TZ).date(), b.open, b.open * 2, b.open * 0.5, b.open * 2, 1000.0)
    r_after = compute_targets(mutated, t, (5,))
    assert r_after[5] > r_before[5]      # muc tieu DOI (duoc phep)


# --- 3.8 mui gio ------------------------------------------------------------------

def test_8_nen_1717_utc_la_ngay_hom_sau_theo_gio_VN():
    # 2022-11-30 17:00 UTC = 2022-12-01 00:00 VN -> NGOAI IS
    b = Bar(symbol="AAA", ts=datetime(2022, 11, 30, 17, 0, tzinfo=UTC),
            open=10.0, high=11.0, low=9.0, close=10.5, volume=1000)
    assert bar_date(b) == date(2022, 12, 1)
    assert in_is(bar_date(b)) is False
    assert in_is(date(2022, 11, 30)) is True
    assert IS_SIGNAL_START == date(2016, 1, 4) and IS_SIGNAL_END == date(2022, 11, 30)


# --- 3.9 niem phong --------------------------------------------------------------

def test_9_nen_tu_2023_tro_di_phai_nem_loi():
    ok = _bar(date(2022, 12, 30), 10.0, 11.0, 9.0, 10.5)
    validate_sealed_bars([ok])                     # khong nem
    xau = _bar(date(2023, 1, 2), 10.0, 11.0, 9.0, 10.5)
    with pytest.raises(ValueError):
        validate_sealed_bars([ok, xau])
    # 2023-01-01 17:00 UTC = 2023-01-02 00:00 VN -> phai nem
    xau_utc = Bar(symbol="AAA", ts=datetime(2023, 1, 1, 17, 0, tzinfo=UTC),
                  open=10.0, high=11.0, low=9.0, close=10.5, volume=1000)
    with pytest.raises(ValueError):
        validate_sealed_bars([xau_utc])


# --- 3.10 doi chung cung ngay -----------------------------------------------------

def test_10a_ro_doi_chung_khong_gom_chinh_ma_su_kien():
    # 2 ma doi chung: baseline = trung binh tinh tay, nhung ro < 5 nen excess = None (muc 1.6)
    entries = [ControlEntry("BBB", 0.01, 0.02, 0.03), ControlEntry("CCC", 0.05, 0.06, 0.07)]
    baseline, excess, n = excess_for_event(0.10, entries, 20)
    assert n == 2
    assert baseline == pytest.approx(0.05)                 # (0,03 + 0,07)/2
    assert excess is None                                  # ro < MIN_CONTROL -> bo khoi so vuot troi


def test_10b_ro_duoi_5_ma_thi_bo_khoi_phep_so_vuot_troi():
    assert MIN_CONTROL == 5
    it = [ControlEntry(f"X{i}", 0.0, 0.0, 0.01) for i in range(4)]
    _baseline, excess, n = excess_for_event(0.10, it, 20)
    assert n == 4 and excess is None
    du = [ControlEntry(f"X{i}", 0.0, 0.0, 0.01) for i in range(5)]
    _baseline, excess, n = excess_for_event(0.10, du, 20)
    assert n == 5 and excess == pytest.approx(0.09)
    assert basket_baseline(du, 20) == (pytest.approx(0.01), 5)


def test_10c_ma_doi_chung_thieu_muc_tieu_thi_khong_tinh_vao_ro():
    entries = [ControlEntry("A", None, None, 0.02), ControlEntry("B", None, None, 0.04)]
    baseline, _excess, n = excess_for_event(0.10, entries, 20)
    assert n == 2 and baseline == pytest.approx(0.03)


# --- 3.11 bootstrap theo thang ----------------------------------------------------

def test_11a_bootstrap_tat_dinh_voi_seed_co_dinh():
    by_month = {(2020, 1): [0.01, 0.02], (2020, 2): [-0.01], (2020, 3): [0.05, 0.03]}
    a = bootstrap_by_month(by_month, n=200, seed=42)
    b = bootstrap_by_month(by_month, n=200, seed=42)
    assert a == b
    assert 0.0 <= a["p"] <= 1.0
    assert a["ci_low"] <= a["mean"] <= a["ci_high"]


def test_11b_khoi_theo_thang_duong_lich_gio_VN():
    assert month_key(date(2020, 1, 31)) == (2020, 1)
    assert month_key(date(2020, 2, 3)) == (2020, 2)
    # nen cuoi thang theo gio VN: 2020-01-31 17:00 UTC = 2020-02-01 VN -> thang 2
    b = Bar(symbol="AAA", ts=datetime(2020, 1, 31, 17, 0, tzinfo=UTC),
            open=10.0, high=11.0, low=9.0, close=10.5, volume=1000)
    assert bar_date(b) == date(2020, 2, 1)
    assert month_key(bar_date(b)) == (2020, 2)


def test_11c_bootstrap_am_thi_p_lon():
    by_month = {(2020, 1): [-0.02, -0.03], (2020, 2): [-0.01]}
    r = bootstrap_by_month(by_month, n=200, seed=42)
    assert r["mean"] < 0
    assert r["p"] == pytest.approx(1.0)


# --- 3.12 thieu nen thoat --------------------------------------------------------

def test_12_chi_co_12_nen_sau_t_thi_co_r5_r10_ma_khong_co_r20():
    bars, t = _base_series(n_after=12)
    r = compute_targets(bars, t, TARGET_KS)
    assert r[5] is not None and r[10] is not None
    assert r[20] is None
    # r_5 = close[t+5]/open[t+1] - 1, r_10 = close[t+10]/open[t+1] - 1
    assert r[5] == pytest.approx(bars[t + 5].close / bars[t + 1].open - 1.0)
    assert r[10] == pytest.approx(bars[t + 10].close / bars[t + 1].open - 1.0)


# --- phu: thanh khoan, SMA truot -------------------------------------------------

def test_p1_thanh_khoan_20_nen_truoc_phai_tu_1_ty():
    days = _dates(T0, 30)
    # close x volume = 20.000 x 60.000 = 1,2 ty -> dat
    bars = [_bar(days[i], 20_000.0, 20_100.0, 19_900.0, 20_000.0, 60_000) for i in range(30)]
    assert liquidity_ok(bars, 25) is True
    # 20.000 x 40.000 = 0,8 ty -> khong dat
    bars2 = [_bar(days[i], 20_000.0, 20_100.0, 19_900.0, 20_000.0, 40_000) for i in range(30)]
    assert liquidity_ok(bars2, 25) is False
    assert MIN_TURNOVER_VND == 1_000_000_000.0


def test_p2_sma_truot_va_rolling_min_max():
    vals = [1.0, 2.0, 3.0, 4.0]
    m = rolling_mean(vals, 2)
    assert m[0] is None and m[1] == pytest.approx(1.5) and m[3] == pytest.approx(3.5)
    assert rolling_max(vals, 2)[3] == pytest.approx(4.0)
    assert rolling_min(vals, 2)[3] == pytest.approx(3.0)
    assert rolling_max(vals, 3)[1] is None
    assert rolling_mean(vals, 5)[3] is None


def test_p3_duong_nhanh_va_duong_cham_cho_cung_ket_qua_bo_loc():
    """Chot chong lech: ban chay that dung SMA tinh truoc, test dung duong cham."""
    from scripts.screen_vcp_daily import SymbolData

    bars, _t = _base_series()
    sd = SymbolData.build("AAA", "HOSE", bars)
    for tt in (250, 251, 252, 253, 275, 299, 300):
        slow = trend_conditions(bars, tt)
        fast = trend_conditions(
            bars, tt, sma50=sd.sma50, sma150=sd.sma150, sma200=sd.sma200,
            win_low=sd.win_low, win_high=sd.win_high,
        )
        assert slow == fast, f"lech tai t={tt}"
        assert sd.trend_ok(tt) == all(slow.values())


def test_1h_bo_loc_tinh_tai_nen_truoc_chu_khong_phai_tai_t():
    """Do luong quan trong: bo loc phai tinh tai DONG CUA NEN t-1.

    Nen pha vo t duoc gan high 200 (close van 102,5): neu bo loc tinh tai t thi dieu kien
    c7 (close >= 0,75 x max high 252 nen) hong -> bo loc False. Tinh dung tai t-1 thi dinh 200
    nam NGOAI cua so 252 nen (cua so ket thuc o nen t-1) -> bo loc True.
    """
    bars, t = _base_series(n_after=1)
    bars[t] = dataclasses.replace(bars[t], high=200.0)
    assert trend_filter_ok(bars, t) is True            # tai t-1 = nen 299
    assert trend_filter_ok(bars, t + 1) is False       # neu tinh tai chinh nen t thi hong
    # va su kien tai t van phai duoc nhan (khong duoc dung du lieu cua nen t)
    assert t in find_events(bars, min_turnover=0.0)


def test_1i_su_kien_phai_qua_loc_thanh_khoan_nhu_ro_doi_chung():
    """Claude audit dot 99: ban dau find_events KHONG goi liquidity_ok, trong khi ro doi
    chung (compact_control_series) co loc thanh khoan -> phe VCP va phe doi chung khac vu
    tru, trai muc 1.1. Mau VCP hop le nhung thanh khoan 20 nen truoc duoi nguong thi KHONG
    la su kien.

    Nen dung tay co gia ~100 dong, volume ~1000 -> thanh khoan ~100 nghin/nen, nen test
    dung nguong 50 nghin theo dung thang cua chuoi; nguong that (1 ty) duoc ghim rieng."""
    import inspect

    from scripts.screen_vcp_daily import MIN_TURNOVER_VND

    # Lan chay that dung mac dinh: phai dung la 1 ty
    assert inspect.signature(find_events).parameters["min_turnover"].default == MIN_TURNOVER_VND
    assert MIN_TURNOVER_VND == 1_000_000_000.0

    nguong = 50_000.0
    bars, t = _base_series()
    assert t in find_events(bars, min_turnover=nguong)          # mau goc du thanh khoan
    thin = list(bars)
    for i in range(t - 20, t):                                  # rut volume 20 nen truoc t
        thin[i] = dataclasses.replace(thin[i], volume=max(1, thin[i].volume // 1000))
    assert liquidity_ok(thin, t, min_turnover=nguong) is False
    assert t not in find_events(thin, min_turnover=nguong)
