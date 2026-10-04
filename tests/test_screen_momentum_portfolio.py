"""Test cho scripts/screen_momentum_portfolio.py (Brief dot 102).

Test tren CHUOI NEN DUNG TAY, khong dung DB. Muoi mot nhom theo muc 3 cua brief,
cong hai test GHIM bat buoc (nguong thanh khoan 1 ty; ma duoi nguong khong duoc
xep hang). Cac con so trong test la so TINH TAY (ghi ro phep tinh o comment),
khong phai so lay tu chinh ham dang duoc kiem.

Nen dung tay gia thap nen cac test HINH DANG truyen `min_turnover` nho; chi hai
test ghim moi dung nguong that 1 ty.
"""

from __future__ import annotations

import inspect
import math
import random
from datetime import UTC, date, datetime, timedelta

import pytest

from scripts import screen_vcp_daily as vcp
from scripts.screen_momentum_portfolio import (
    BLOCK_MONTHS,
    HISTORY_MAX_GAP_DAYS,
    MIN_TURNOVER_VND,
    MIN_UNIVERSE_FOR_MONTH,
    MIN_WIN_SIZE,
    MOM_LOOKBACK,
    MOM_SKIP,
    WIN_FRACTION,
    bar_date,
    block_bootstrap,
    block_samples,
    cagr,
    eligible_at,
    hold_return,
    is_stock_symbol,
    last_session_by_month,
    lose_members,
    max_drawdown,
    momentum_at,
    month_key_of,
    month_members_returns,
    month_spans,
    month_usable,
    net_month,
    next_month_key,
    portfolio_gross,
    read_symbol_bars,
    round_trip_cost,
    share_positive,
    turnover,
    win_members,
    win_size,
)
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS

START = date(2019, 1, 7)  # thu Hai


# --- dung chuoi nen -----------------------------------------------------------------

def _sessions(start: date, n: int) -> list[date]:
    """n ngay giao dich (bo Thu Bay/Chu Nhat) ke tu start."""
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _bar(d: date, o: float, c: float, sym: str = "AAA", vol: float = 5e7) -> Bar:
    return Bar(
        symbol=sym,
        ts=datetime(d.year, d.month, d.day, tzinfo=TZ),
        open=o,
        high=max(o, c),
        low=min(o, c),
        close=c,
        volume=int(vol),
    )


def _series_with_gaps(blocks: list[tuple[date, int]], sym: str = "AAA", vol: float = 5e7) -> list[Bar]:
    """Chuoi nen theo tung khoi (ngay bat dau, so phien) — khoi sau noi tiep bang
    cach NHay ngay bat dau, nen giua hai khoi la mot KHOANG TRONG."""
    bars: list[Bar] = []
    for start, n in blocks:
        for d in _sessions(start, n):
            bars.append(_bar(d, 100.0, 100.0, sym=sym, vol=vol))
    return bars


def _close_series(closes: list[float], sym: str = "AAA", vol: float = 5e7) -> list[Bar]:
    """Chuoi nen voi open = close = gia tri cho truoc, moi phien lien tiep."""
    return [_bar(d, c, c, sym=sym, vol=vol) for d, c in zip(_sessions(START, len(closes)), closes)]


def _set_close(bars: list[Bar], i: int, close: float, open_: float | None = None) -> None:
    """Sua mot nen tai cho (Bar frozen nen phai thay ca doi tuong)."""
    o = close if open_ is None else open_
    b = bars[i]
    bars[i] = Bar(
        symbol=b.symbol,
        ts=b.ts,
        open=o,
        high=max(o, close),
        low=min(o, close),
        close=close,
        volume=b.volume,
    )


# --- 1. ngay xep hang ---------------------------------------------------------------

def test_1a_F_la_phien_cuoi_cung_CO_NEN_trong_thang():
    # Thang 7/2021: 31/07 la Thu Bay => phien cuoi cung la 30/07 (Thu Sau).
    # 22 phien tinh tu 01/07 (Thu Nam) -> phien thu 22 = 30/07.
    dates = _sessions(date(2021, 7, 1), 22)
    assert dates[-1] == date(2021, 7, 30)
    cal = last_session_by_month(dates)
    assert cal[(2021, 7)] == date(2021, 7, 30)


def test_1b_thang_thieu_phien_cuoi_thi_lay_phien_co_nen_lon_nhat():
    # Du lieu dung truoc 31/12/2021 (31/12 la Thu Sau) - nen cuoi cung la 30/12.
    dates = [d for d in _sessions(date(2021, 12, 1), 24) if d <= date(2021, 12, 30)]
    cal = last_session_by_month(dates)
    assert cal[(2021, 12)] == date(2021, 12, 30)


# --- 2. diem momentum ---------------------------------------------------------------

def test_2a_mom_dung_bang_close_t_21_chia_close_t_252():
    # close[i] = 100 + i. iF = 299.
    # close[299-252] = close[47] = 147,0 ; close[299-21] = close[278] = 378,0
    # mom = 378/147 - 1 = 126/49 - 1 = 18/7 - 1 = 11/7 = 1,5714285714...
    bars = _close_series([100.0 + i for i in range(300)])
    assert MOM_LOOKBACK == 252 and MOM_SKIP == 21
    assert momentum_at(bars, 299) == pytest.approx(378.0 / 147.0 - 1)
    assert momentum_at(bars, 299) == pytest.approx(11 / 7)


def test_2b_sua_20_nen_cuoi_truoc_F_thi_mom_KHONG_doi():
    # mom chi dung close[iF-21] = close[278] nen 20 nen 279..298 (va ca 299) khong anh huong.
    bars = _close_series([100.0 + i for i in range(300)])
    truoc = momentum_at(bars, 299)
    for i in range(279, 300):
        _set_close(bars, i, 999.0)
    assert momentum_at(bars, 299) == truoc


# --- 3. chong nhin trom tuong lai ---------------------------------------------------

def test_3_sua_moi_nen_SAU_F_thi_dieu_kien_mom_va_WIN_khong_doi():
    # Ba ma, 320 phien lien tiep; F = ngay cua nen 299 (con 20 nen SAU F).
    f_date = _sessions(START, 320)[299]
    bars: dict[str, list[Bar]] = {}
    for k, sym in enumerate(("AAA", "BBB", "CCC")):
        closes = [100.0 + i + k * 50.0 for i in range(320)]
        bars[sym] = _close_series(closes, sym=sym)

    def xep_hang() -> tuple[dict[str, float], list[str]]:
        moms: dict[str, float] = {}
        for sym, b in bars.items():
            if eligible_at(b, 299, f_date, min_turnover=1.0) == "ok":
                moms[sym] = momentum_at(b, 299)
        return moms, win_members(moms)

    moms_truoc, win_truoc = xep_hang()
    assert win_truoc  # co it nhat mot ma trong WIN

    # Sua TUY Y moi nen SAU F (chi so 300..319) cua ca ba ma.
    for sym, b in bars.items():
        for i in range(300, 320):
            _set_close(b, i, 1.0 + i, open_=0.5 + i)

    moms_sau, win_sau = xep_hang()
    assert moms_sau == moms_truoc
    assert win_sau == win_truoc


# --- 4. lich su co khoang trong -----------------------------------------------------

def test_4a_ma_co_khoang_trong_dai_thi_KHONG_du_dieu_kien():
    # Khoi A: 47 phien tu 07/01/2019. Khoi B: 235 phien tu 03/08/2020, roi NHAY
    # 200 ngay, roi 18 phien cuoi. Tong 300 nen.
    # iF = 299 -> iF - 252 = 47 = nen DAU khoi B (03/08/2020).
    # F ~ giua 2021 => F - 400 ngay < 03/08/2020 nen lech > 400 ngay.
    bars = _series_with_gaps(
        [
            (date(2019, 1, 7), 47),
            (date(2020, 8, 3), 235),
            (_sessions(date(2020, 8, 3), 235)[-1] + timedelta(days=200), 18),
        ]
    )
    assert len(bars) == 300
    f_date = bar_date(bars[299])
    lech = (f_date - bar_date(bars[47])).days
    assert lech > HISTORY_MAX_GAP_DAYS
    assert eligible_at(bars, 299, f_date, min_turnover=1.0) == "lich_su_gian_doan"


def test_4b_chuoi_lien_tuc_thi_du_dieu_kien():
    bars = _close_series([100.0 + i for i in range(300)])
    f_date = bar_date(bars[299])
    lech = (f_date - bar_date(bars[47])).days
    assert lech <= HISTORY_MAX_GAP_DAYS  # 252 phien ~ 353 ngay
    assert eligible_at(bars, 299, f_date, min_turnover=1.0) == "ok"


def test_4c_thieu_lich_su_thi_khong_du_dieu_kien():
    # i_f = 251: 251 - 252 = -1 < 0 => thieu lich su (i_f = 259 thi 259-252 = 7 >= 0, VAN du).
    bars = _close_series([100.0 + i for i in range(260)])
    assert eligible_at(bars, 251, bar_date(bars[251]), min_turnover=1.0) == "thieu_du_lieu"


# --- 5. chi co phieu ----------------------------------------------------------------

def test_5a_ma_ba_ky_tu_chu_hoac_so_duoc_GIU():
    for sym in ("HPG", "VCB", "L14", "VC3", "D2D", "PV2", "C47"):
        assert is_stock_symbol(sym), sym


def test_5b_etf_chung_quyen_chu_thuong_bi_LOAI():
    for sym in ("E1VFVN30", "FUEVFVND", "CHPG2301", "hpg", "HP", "HPGG", "hp1", "A A", ""):
        assert not is_stock_symbol(sym), sym


# --- 6. co danh muc ----------------------------------------------------------------

def test_6a_co_win_lam_tron_len_va_toi_thieu_10():
    assert win_size(250) == 25          # 250 x 10% = 25
    assert win_size(101) == 11          # 101 x 10% = 10,1 -> lam tron LEN 11
    assert win_size(100) == 10          # dung bang nguong
    assert win_size(20) == MIN_WIN_SIZE  # 20 x 10% = 2 -> toi thieu 10
    assert round(WIN_FRACTION, 4) == 0.1


def test_6b_duoi_100_ma_thi_bo_thang():
    assert month_usable(101) and month_usable(MIN_UNIVERSE_FOR_MONTH)
    assert not month_usable(99)


def test_6c_win_la_nhom_mom_cao_nhat_lose_la_thap_nhat():
    moms = {f"S{i:03d}": float(i) for i in range(200)}
    w = win_members(moms)
    lo = lose_members(moms)
    assert len(w) == 20 and len(lo) == 20
    assert min(moms[s] for s in w) > max(moms[s] for s in lo)


# --- 7. mo tran --------------------------------------------------------------------

def test_7a_ma_mo_tran_bi_LOAI_va_KHONG_duoc_thay_the():
    # AAA: close truoc = 100,0 ; mo cua = 107,0 >= 100 x (1 + 0,07 - 0,001) = 106,9 -> TRAN.
    # BBB: close truoc = 100,0 ; mo cua = 101,0 -> mua duoc; ra o 105,0
    #      r = 105/101 - 1 = 0,039603960396...
    aaa = [_bar(date(2022, 6, 29), 100.0, 100.0, sym="AAA"), _bar(date(2022, 6, 30), 107.0, 110.0, sym="AAA")]
    bbb = [_bar(date(2022, 6, 29), 100.0, 100.0, sym="BBB"), _bar(date(2022, 6, 30), 101.0, 105.0, sym="BBB")]

    r_aaa, why_aaa = hold_return(aaa, 1, 1, "HOSE")
    r_bbb, why_bbb = hold_return(bbb, 1, 1, "HOSE")
    assert (r_aaa, why_aaa) == (None, "ceiling")
    assert why_bbb == "ok"
    assert r_bbb == pytest.approx(105.0 / 101.0 - 1)

    held, drop = month_members_returns(
        ["AAA", "BBB"],
        {"AAA": (r_aaa, why_aaa), "BBB": (r_bbb, why_bbb), "CCC": (0.02, "ok")},
    )
    assert set(held) == {"BBB"}, "ma mo tran phai bi loai, KHONG duoc thay bang ma khac"
    assert "CCC" not in held, "ma ngoai danh muc (du lieu co san) khong duoc chen vao"
    assert held["BBB"] == pytest.approx(105.0 / 101.0 - 1)
    assert drop == {"ceiling": 1}


def test_7b_ma_khong_co_nen_trong_thang_thi_bi_loai_va_dem():
    held, drop = month_members_returns(["AAA"], {"AAA": (None, "thieu_nen")})
    assert held == {}
    assert drop == {"thieu_nen": 1}
    assert portfolio_gross({}) is None


# --- 8. chi phi theo vong quay -----------------------------------------------------

def test_8a_turnover_bon_ma_doi_hai():
    # {A,B,C,D} -> {A,B,E,F}: 2 ma moi tren 4 = 0,5
    assert turnover(["A", "B", "C", "D"], ["A", "B", "E", "F"]) == pytest.approx(0.5)


def test_8b_thang_dau_turnover_bang_1():
    assert turnover(None, ["A", "B"]) == 1.0
    assert turnover([], ["A", "B"]) == 1.0
    assert turnover(["A", "B"], ["A", "B"]) == 0.0


def test_8c_cost_rt_tinh_tu_HANG_SO_IMPORT_khong_phai_so_go_tay():
    # 2 x 0,0028 + 0,001 + 2 x 5/10.000 = 0,0056 + 0,001 + 0,001 = 0,0076
    assert round_trip_cost() == pytest.approx(2 * FEE_RATE + SELL_TAX_RATE + 2 * SLIPPAGE_BPS / 10_000)
    assert round_trip_cost() == pytest.approx(0.0076)
    assert round_trip_cost() != pytest.approx(0.007)  # gia tri cu khi phi con 0,25% moi chieu


def test_8d_net_tru_dung_chi_phi_vong_quay():
    # gross = 0,05 ; turnover = 0,5 ; cost_rt = 0,0076 -> net = 0,05 - 0,0038 = 0,0462
    assert net_month(0.05, 0.5, round_trip_cost()) == pytest.approx(0.0462)


# --- 9. bootstrap khoi 3 thang -----------------------------------------------------

def _kiem_khoi_lien_nhau(sample: list[float], series: list[float], block: int) -> None:
    for j in range(0, len(sample) - block + 1, block):
        chunk = sample[j : j + block]
        assert all(chunk[k + 1] == chunk[k] + 1 for k in range(block - 1)), chunk
        assert any(series[i : i + block] == chunk for i in range(len(series) - block + 1)), chunk


def test_9a_moi_mau_gom_cac_KHOI_LIEN_NHAU():
    series = [float(i) for i in range(12)]
    samples = block_samples(series, BLOCK_MONTHS, random.Random(42))
    assert len(samples) == 2000
    assert all(len(s) == len(series) for s in samples)
    for s in samples[:50]:
        _kiem_khoi_lien_nhau(s, series, BLOCK_MONTHS)
    assert BLOCK_MONTHS == 3


def test_9b_do_dai_khong_chia_het_thi_lay_du_do_dai_chuoi():
    series = [float(i) for i in range(7)]
    samples = block_samples(series, BLOCK_MONTHS, random.Random(1))
    assert all(len(s) == 7 for s in samples)
    for s in samples[:50]:
        _kiem_khoi_lien_nhau(s, series, BLOCK_MONTHS)


def test_9c_bootstrap_tat_dinh_voi_seed_va_p_la_ty_le_mau_co_trung_binh_le_0():
    series = [0.01, -0.02, 0.03, 0.04, -0.01, 0.02]
    r1 = block_bootstrap(series, n_boot=300, seed=42)
    r2 = block_bootstrap(series, n_boot=300, seed=42)
    assert r1 == r2
    # Moi phan tu > 0 => moi mau deu co trung binh > 0 => p = 0
    assert block_bootstrap([0.01] * 6, n_boot=100, seed=42)["p"] == 0.0
    assert block_bootstrap([-0.01] * 6, n_boot=100, seed=42)["p"] == 1.0


def test_9d_trung_binh_va_trung_vi_cua_chuoi_duoc_bao_dung():
    series = [0.10, 0.20, 0.30]
    r = block_bootstrap(series, n_boot=200, seed=42)
    assert r["mean"] == pytest.approx(0.20)
    assert r["median"] == pytest.approx(0.20)


# --- 10. niem phong ----------------------------------------------------------------

class _FakeStorage:
    """Storage gia: tra ve dung danh sach nen da cho."""

    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars

    def read_daily_bars(self, symbol: str, start: datetime, end: datetime) -> list[Bar]:
        return self._bars


def test_10_nen_tu_2023_gio_VN_thi_NEM_LOI():
    bars = [
        _bar(date(2022, 12, 30), 100.0, 100.0),
        _bar(date(2023, 1, 3), 100.0, 100.0),
    ]
    with pytest.raises(ValueError, match="niêm phong"):
        read_symbol_bars(_FakeStorage(bars), "AAA")


def test_10b_nen_1730_UTC_ngay_cuoi_nam_khong_bi_coi_la_2023():
    # 2022-12-30 17:00 UTC = 31/12/2022 00:00 gio VN -> van trong niem phong.
    b = Bar(
        symbol="AAA",
        ts=datetime(2022, 12, 30, 17, 0, tzinfo=UTC),
        open=100.0,
        high=100.0,
        low=100.0,
        close=100.0,
        volume=1000,
    )
    kept, junk = read_symbol_bars(_FakeStorage([b]), "AAA")
    assert junk == 0 and len(kept) == 1 and bar_date(kept[0]) == date(2022, 12, 31)


# --- 11. mui gio -------------------------------------------------------------------

def test_11_nen_1730_UTC_la_ngay_hom_sau_theo_gio_VN():
    b = Bar(
        symbol="AAA",
        ts=datetime(2022, 11, 30, 17, 0, tzinfo=UTC),
        open=100.0,
        high=100.0,
        low=100.0,
        close=100.0,
        volume=1000,
    )
    assert bar_date(b) == date(2022, 12, 1)
    assert month_key_of(bar_date(b)) == (2022, 12)
    assert next_month_key((2022, 12)) == (2023, 1)
    assert next_month_key((2022, 11)) == (2022, 12)


# --- 12. test GHIM bat buoc --------------------------------------------------------

def test_12a_nguong_thanh_khoan_dang_ky_la_1_TY():
    assert MIN_TURNOVER_VND == vcp.MIN_TURNOVER_VND
    assert MIN_TURNOVER_VND == 1_000_000_000.0
    assert inspect.signature(eligible_at).parameters["min_turnover"].default == 1_000_000_000.0


def test_12b_ma_DUOI_NGUONG_thanh_khoan_KHONG_duoc_xep_hang():
    # close x volume = 100 x 1.000 = 100.000 dong < 1 ty -> khong du dieu kien.
    bars = _close_series([100.0] * 300, vol=1000.0)
    f_date = bar_date(bars[299])
    assert eligible_at(bars, 299, f_date) == "thieu_thanh_khoan"
    assert eligible_at(bars, 299, f_date, min_turnover=1.0) == "ok"


def test_12c_month_spans_tach_dung_tung_thang():
    bars = _series_with_gaps([(date(2022, 10, 3), 20), (date(2022, 11, 1), 22)])
    spans = month_spans(bars)
    assert sorted(spans) == [(2022, 10), (2022, 11)]
    sp = spans[(2022, 10)]
    assert (sp.first, sp.last) == (0, 19) and sp.last_date == bar_date(bars[19])
    sp = spans[(2022, 11)]
    assert (sp.first, sp.last) == (20, 41) and sp.last_date == bar_date(bars[41])


def test_12d_cac_ham_thong_ke_co_ban():
    # CAGR: 12 thang, moi thang +0,01 -> (1,01)^12 - 1 = 0,12682503...
    assert cagr([0.01] * 12) == pytest.approx(1.01**12 - 1)
    assert cagr([]) is None
    # Max drawdown: +10% roi -50% -> dinh 1,1 ; day 0,55 -> DD = 0,5
    assert max_drawdown([0.10, -0.50]) == pytest.approx(0.5)
    assert max_drawdown([]) == 0.0
    assert share_positive([0.1, -0.1, 0.2, 0.0]) == pytest.approx(0.5)  # 2/4, mau so gom ca 0,0
    assert share_positive([]) == 0.0


def test_12e_momentum_at_voi_chi_so_qua_nho_thi_khong_hop_le():
    bars = _close_series([100.0 + i for i in range(300)])
    with pytest.raises(IndexError):
        momentum_at(bars, 20)
    assert math.isclose(win_size(1000), 100.0 + 0.0)
