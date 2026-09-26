"""Test cho scripts/screen_vn30f_smc.py (Brief dot 98).

Test tren PHIEN DUNG TAY, khong dung DB. Bon nhom theo muc 3 cua brief:
3.1 tung su kien voi so tinh tay; 3.2 chong nhin trom tuong lai (test quan trong
nhat); 3.3 duong ong (bo ATC, ghep cot, dau cua m).
"""

from datetime import date, datetime, timedelta

import pytest

from scripts.screen_vn30f_smc import (
    SESS_LEN,
    SWEEP_N,
    add_smc_columns,
    build_smc_panel,
    compute_smc_columns,
    count_events,
    drop_atc_bars,
    event_mean_move,
    round_trip_cost_points,
)
from trading.calendar_vn import TZ
from trading.models import Bar

NGAY = date(2026, 5, 5)
# Moc phien VN30F1M do tu DB ngay 26/09/2026: 30 nen sang 09:00..11:25,
# 18 nen chieu 13:00..14:25, va 1 nen ATC 14:45 -> 49 nen/ngay.
SANG = [datetime(2026, 5, 5, 9, 0, tzinfo=TZ) + timedelta(minutes=5 * i) for i in range(30)]
CHIEU = [datetime(2026, 5, 5, 13, 0, tzinfo=TZ) + timedelta(minutes=5 * i) for i in range(18)]
ATC = [datetime(2026, 5, 5, 14, 45, tzinfo=TZ)]


def _bar(ts: datetime, o: float, h: float, low: float, c: float, vol: float = 100.0) -> Bar:
    return Bar(symbol="VN30F1M_CONT", ts=ts, open=o, high=h, low=low, close=c, volume=vol)


def _session(n: int, highs: list[float], lows: list[float], closes: list[float]) -> list[Bar]:
    """Phien n nen voi high/low/close cho truoc (open = close truoc do)."""
    assert len(highs) == len(lows) == len(closes) == n
    base = datetime(2026, 5, 5, 9, 0, tzinfo=TZ)
    out = []
    for i in range(n):
        ts = base + timedelta(minutes=5 * i)
        out.append(_bar(ts, closes[i - 1] if i else closes[0], highs[i], lows[i], closes[i]))
    return out


def _cols(bars: list[Bar]) -> list[dict]:
    return compute_smc_columns(bars)


# --- 3.1.1 sweep ------------------------------------------------------------------

def test_1a_sweep_quet_dinh_tra_ve_tru_1():
    n = 13
    highs = [100.0] * 12 + [101.0]
    lows = [95.0] * 12 + [96.0]
    closes = [99.0] * 12 + [99.5]          # dong cua 99,5 < H = 100
    cols = _cols(_session(n, highs, lows, closes))
    assert cols[SWEEP_N]["sweep"] == -1


def test_1b_sweep_quet_dinh_nhung_dong_cua_tren_H_thi_khong_tinh():
    highs = [100.0] * 12 + [101.0]
    lows = [95.0] * 12 + [96.0]
    closes = [99.0] * 12 + [100.5]         # dong cua 100,5 >= H -> khong quay dau
    cols = _cols(_session(13, highs, lows, closes))
    assert cols[SWEEP_N]["sweep"] == 0


def test_1c_sweep_quet_day_tra_ve_cong_1():
    highs = [105.0] * 12 + [104.0]
    lows = [100.0] * 12 + [99.0]           # L = 100, low 99 < 100
    closes = [101.0] * 12 + [100.5]        # dong cua 100,5 > L
    cols = _cols(_session(13, highs, lows, closes))
    assert cols[SWEEP_N]["sweep"] == 1


def test_1d_sweep_rau_hai_dau_tra_ve_0_va_duoc_dem_rieng():
    # 12 nen dau: H = 101, L = 99. Nen 13 quet CA HAI dau va dong cua o giua.
    highs = [101.0] * 12 + [102.0]
    lows = [99.0] * 12 + [98.0]
    closes = [100.0] * 13                  # 100 < H = 101 va 100 > L = 99 -> ca hai
    cols = _cols(_session(13, highs, lows, closes))
    assert cols[SWEEP_N]["sweep"] == 0
    assert cols[SWEEP_N]["sweep_double"] is True
    assert sum(1 for c in cols if c["sweep_double"]) == 1


# --- 3.1.2 bos --------------------------------------------------------------------

def _bos_session() -> list[Bar]:
    """Swing high ro tai j = 2 (high 12 > 10 hai ben), dong cua pha len tai t = 4."""
    highs = [10.0, 10.0, 12.0, 11.0, 10.0, 10.0]
    lows = [9.0, 9.0, 9.0, 9.0, 9.0, 9.0]
    closes = [10.0, 10.0, 11.0, 11.5, 12.5, 12.6]
    return _session(6, highs, lows, closes)


def test_2a_bos_swing_chua_xac_nhan_thi_khong_dung():
    # j = 2 -> chi biet tu nen j+2 = 4. Tai t = 3 phai la None (khong phai 0).
    cols = _cols(_bos_session())
    assert cols[3]["bos"] is None


def test_2b_bos_pha_len_tra_ve_cong_1():
    cols = _cols(_bos_session())
    assert cols[4]["bos"] == 1


def test_2c_bos_pha_xuong_tra_ve_tru_1():
    highs = [11.0, 11.0, 11.0, 11.0, 11.0, 11.0]
    lows = [10.0, 10.0, 8.0, 9.5, 9.0, 9.0]      # swing low tai j = 2
    closes = [10.5, 10.5, 10.0, 9.8, 7.5, 7.4]   # t = 4: close 7,5 < S_l = 8
    cols = _cols(_session(6, highs, lows, closes))
    assert cols[4]["bos"] == -1


def test_2d_bos_khong_co_swing_nao_thi_None():
    # High bang phang khong tao swing (khong "lon hon han") -> chua co swing -> None
    highs = [10.0] * 6
    lows = [9.0] * 6
    closes = [9.5] * 6
    cols = _cols(_session(6, highs, lows, closes))
    assert all(c["bos"] is None for c in cols)


# --- 3.1.3 fvg --------------------------------------------------------------------

def test_3a_fvg_khoang_trong_tang_tra_ve_cong_1():
    highs = [100.0, 100.0, 105.0]
    lows = [99.0, 99.0, 105.5]              # low[2] = 105,5 > high[0] = 100
    closes = [99.5, 99.5, 105.6]
    cols = _cols(_session(3, highs, lows, closes))
    assert cols[2]["fvg"] == 1


def test_3b_fvg_bang_nhau_thi_khong_phai_khoang_trong():
    highs = [104.0, 100.0, 105.0]
    lows = [99.0, 99.0, 104.0]              # low[2] = 104 == high[0] = 104 -> 0
    closes = [100.0, 100.0, 104.5]
    cols = _cols(_session(3, highs, lows, closes))
    assert cols[2]["fvg"] == 0


def test_3c_fvg_khoang_trong_giam_tra_ve_tru_1():
    highs = [105.0, 100.0, 99.0]
    lows = [104.0, 99.0, 98.0]              # high[2] = 99 < low[0] = 104
    closes = [104.5, 100.0, 98.5]
    cols = _cols(_session(3, highs, lows, closes))
    assert cols[2]["fvg"] == -1


# --- 3.1.4 thieu lich su -> None, khong phai 0 -----------------------------------

def test_4a_thieu_lich_su_tra_None_khong_phai_0():
    highs = [100.0] * 13
    lows = [99.0] * 13
    closes = [99.5] * 13
    cols = _cols(_session(13, highs, lows, closes))
    # sweep can t >= 12; fvg can t >= 2
    assert all(cols[t]["sweep"] is None for t in range(SWEEP_N))
    assert cols[0]["fvg"] is None and cols[1]["fvg"] is None
    assert cols[2]["fvg"] is not None
    # 0 la gia tri THAT (khong co su kien), phan biet voi None
    assert cols[12]["sweep"] == 0


# --- 3.2.5 bat bien theo tuong lai (test quan trong nhat) --------------------------

def test_5_bat_bien_theo_tuong_lai_moi_t_trong_phien():
    """Sua tuy y moi nen SAU t -> ba cot tai moi nen <= t phai giong het."""
    n = 20
    highs = [100.0 + 3 * ((i * 7) % 5) for i in range(n)]
    lows = [95.0 + 2 * ((i * 3) % 4) for i in range(n)]
    closes = [97.0 + 2.5 * ((i * 5) % 6) for i in range(n)]
    bars = _session(n, highs, lows, closes)
    base = _cols(bars)

    for t in range(n):
        mutated = list(bars)
        for i in range(t + 1, n):
            b = bars[i]
            mutated[i] = _bar(b.ts, b.open, 999.0, 1.0, 500.0, vol=1.0)
        got = _cols(mutated)
        assert got[: t + 1] == base[: t + 1], f"cot tai nen <= {t} doi khi sua nen sau {t}"


# --- 3.2.6 khong vuot phien --------------------------------------------------------

def test_6_khong_dung_du_lieu_cua_phien_truoc():
    """Phien 1 co swing/dinh ro rang; phien 2 (it hon 12 nen) phai khong an theo."""
    s1 = _bos_session()
    s2 = _session(6, [10.0, 10.0, 12.0, 11.0, 10.0, 10.0], [9.0] * 6, [10.0, 10.0, 11.0, 11.5, 12.5, 12.6])
    d1, d2 = date(2026, 5, 5), date(2026, 5, 6)
    rows, _ = build_smc_panel({d1: s1, d2: s2})
    # sweep cua phien 2: t < 12 -> None, du phien 1 co du high
    assert all(r["sweep"] is None for r in rows[6:12])
    # va gia tri phien 2 phai bang dung tinh rieng le (khong tron phien 1)
    only2 = _cols(s2)
    assert [r["bos"] for r in rows[6:12]] == [c["bos"] for c in only2]


# --- 3.3.7 bo nen ATC 14:45 --------------------------------------------------------

def test_7_bo_nen_145_phien_49_nen_con_48():
    from scripts.screen_vn30f_intraday import filter_and_group_sessions

    moc = SANG + CHIEU + ATC
    assert len(moc) == 49                      # dung so nen that trong bars_derivative

    bars = [_bar(ts, 100.0, 101.0, 99.0, 100.5) for ts in moc]
    kept = drop_atc_bars(bars)
    assert len(kept) == 49 - 1
    assert all(b.ts.astimezone(TZ).time().strftime("%H:%M") != "14:45" for b in kept)

    valid, dropped = filter_and_group_sessions(kept, expected_bars_per_session=SESS_LEN)
    assert len(valid) == 1
    assert len(valid[NGAY]) == SESS_LEN == 48
    assert dropped == []


# --- 3.3.8 ghep cot vao hang co san ------------------------------------------------

def test_8_them_ba_cot_ma_khong_doi_cot_cu():
    from scripts.screen_vn30f_intraday import compute_session_features_and_targets

    bars = _session(13, [100.0] * 12 + [101.0], [95.0] * 12 + [96.0], [99.0] * 12 + [99.5])
    base_rows = compute_session_features_and_targets(bars)
    merged, n_double = add_smc_columns(base_rows, bars)

    assert len(merged) == len(base_rows) == 13
    for old, new in zip(base_rows, merged, strict=True):
        for k, v in old.items():                       # moi cot cu giu nguyen gia tri
            assert new[k] == v, f"cot cu {k} bi doi"
    for r in merged:
        assert "sweep" in r and "bos" in r and "fvg" in r
    assert merged[12]["sweep"] == -1
    assert n_double == 0


# --- 3.3.9 dau cua m --------------------------------------------------------------

def test_9_m_dung_dau_su_kien_am_voi_fwd_am_cho_dong_gop_duong():
    rows = [
        {"sweep": -1, "fwd_1": -2.0, "fwd_3": None, "fwd_6": None},
        {"sweep": 0, "fwd_1": 50.0, "fwd_3": None, "fwd_6": None},   # khong su kien -> bo qua
    ]
    assert event_mean_move(rows, "sweep", "fwd_1") == pytest.approx(2.0)


def test_9b_m_bo_qua_hang_khong_co_su_kien_va_muc_tieu_None():
    rows = [
        {"bos": 1, "fwd_1": 3.0},
        {"bos": 0, "fwd_1": 100.0},
        {"bos": None, "fwd_1": 7.0},
        {"bos": 1, "fwd_1": None},
    ]
    assert event_mean_move(rows, "bos", "fwd_1") == pytest.approx(3.0)
    assert event_mean_move(rows, "bos", "fwd_3") is None       # khong co cot fwd_3


def test_9c_dem_su_kien_theo_dau():
    rows = [{"sweep": 1}, {"sweep": 1}, {"sweep": -1}, {"sweep": 0}, {"sweep": None}]
    c = count_events(rows, "sweep")
    assert c["plus"] == 2 and c["minus"] == 1 and c["total"] == 3


# --- chi phi mot vong (muc 1.4) ----------------------------------------------------

def test_10_chi_phi_mot_vong_tinh_bang_diem_tu_ham_that():
    from trading.derivative_position import (
        DERIVATIVE_CONTRACT_MULTIPLIER,
        derivative_side_cost,
    )

    p = 1950.0
    expected = (
        derivative_side_cost(p, 1, opening=True) + derivative_side_cost(p, 1, opening=False)
    ) / DERIVATIVE_CONTRACT_MULTIPLIER
    assert round_trip_cost_points(p) == pytest.approx(expected)
    assert 0.0 < round_trip_cost_points(p) < 1.0        # cung do lon ~0,5 diem
