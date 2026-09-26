"""Tests cho calendar_vn.trading_days_between / market_minutes_between
(plan 2026-09-03 goi A — thoi gian thi truong).

Hai ham chung nay la "mot cong thuc, hai cho goi": compute_nav (tuoi gia theo
ngay giao dich) va chuong 2A bar_stale (phut trong phien). Tat dinh, khong DB.
"""

from datetime import date, datetime

from trading.calendar_vn import (
    SESSIONS,
    TZ,
    market_minutes_between,
    trading_days_between,
)

# 28/08/2026 = thu 6. 31/08-02/09/2026 = nghi Quoc khanh (config.yaml).
HOLIDAYS = frozenset({date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2)})


def _dt(y, m, d, hh=0, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=TZ)


# ============ trading_days_between ============


def test_ngay_le_khong_tinh_vao_so_ngay_giao_dich():
    """Bar daily 28/08 -> 03/09: 6 ngay LICH nhung chi 1 ngay GIAO DICH (03/09).
    Day chinh la loi NAV 03/09: 28/08 la phien gan nhat truoc le, gia con tuoi."""
    assert trading_days_between(_dt(2026, 8, 28), _dt(2026, 9, 3, 9, 0), HOLIDAYS) == 1


def test_qua_cuoi_tuan_tinh_dung_so_phien():
    """Bar thu 6 21/08 -> thu 2 24/08: 1 phien giao dich (24/08), khong tinh
    thu 7 + chu nhat."""
    assert trading_days_between(_dt(2026, 8, 21), _dt(2026, 8, 24, 9, 0)) == 1


def test_cung_ngay_la_0_ngay():
    assert trading_days_between(_dt(2026, 9, 3, 9, 0), _dt(2026, 9, 3, 14, 0)) == 0


def test_gia_qua_5_ngay_giao_dich_thi_tinh_nhieu():
    """Bar 20/08 -> 03/09: nhieu phien hon 5 -> gia qua cu (loai khoi NAV)."""
    assert trading_days_between(_dt(2026, 8, 20), _dt(2026, 9, 3, 9, 0), HOLIDAYS) > 5


# ============ market_minutes_between ============


def test_nghi_trua_khong_tinh_phut():
    """11:25 -> 13:00:03 cung ngay giao dich. Dong ho 95 phut, nhung trong
    phien chi ~5 phut (11:25-11:30) + 0 (13:00 moi mo cua phien chieu)."""
    mins = market_minutes_between(
        _dt(2026, 9, 3, 11, 25), _dt(2026, 9, 3, 13, 0, 3), sessions=SESSIONS
    )
    assert 4.9 <= mins <= 5.5


def test_qua_dem_khong_tinh_ngoai_gio():
    """14:45 -> 09:00:03 hom sau: sau 14:45 khong con phut phien, sang hom sau
    moi mo cua 0 phut — tru khi den 09:15 tro di."""
    mins = market_minutes_between(
        _dt(2026, 9, 3, 14, 45), _dt(2026, 9, 4, 9, 0, 3), sessions=SESSIONS
    )
    assert 0.0 <= mins <= 0.2


def test_qua_cuoi_tuan_khong_tinh():
    """Thu 6 21/08 14:45 -> thu 2 24/08 08:59 (TRUOC gio mo cua): T7+CN khong
    phai phien, sang T2 chua mo cua -> 0 phut trong phien."""
    mins = market_minutes_between(
        _dt(2026, 8, 21, 14, 45), _dt(2026, 8, 24, 8, 59), sessions=SESSIONS
    )
    assert mins == 0.0


def test_qua_ngay_le_khong_tinh():
    """28/08 14:45 -> 03/09 09:16 (sau 3 ngay le): chi tinh 16 phut phien 03/09."""
    mins = market_minutes_between(
        _dt(2026, 8, 28, 14, 45), _dt(2026, 9, 3, 9, 16), HOLIDAYS, sessions=SESSIONS
    )
    assert 15.5 <= mins <= 16.5


def test_feed_chet_tu_sang_den_chieu_tinh_du():
    """Bar cuoi 09:30 -> 13:00 cung ngay: phien sang 09:30-11:30 = 120 phut
    (nghi trua khong tinh) -> lon hon ngưỡng, phai bao dong."""
    mins = market_minutes_between(
        _dt(2026, 9, 3, 9, 30), _dt(2026, 9, 3, 13, 0), sessions=SESSIONS
    )
    assert mins == 120.0


def test_previous_trading_day_bo_qua_cuoi_tuan_va_ngay_le():
    from datetime import date

    from trading.calendar_vn import previous_trading_day

    assert previous_trading_day(date(2026, 9, 28)) == date(2026, 9, 25)  # T2 -> T6
    assert previous_trading_day(date(2026, 9, 23)) == date(2026, 9, 22)
    assert previous_trading_day(date(2026, 9, 23), {date(2026, 9, 22)}) == date(2026, 9, 21)


def test_trading_days_between_dates_khop_ban_datetime():
    """Ban `date` phai cho dung ket qua cua trading_days_between (ban datetime)."""
    from datetime import date, datetime

    from trading.calendar_vn import TZ, trading_days_between, trading_days_between_dates

    hol = frozenset({date(2026, 9, 2)})
    cases = [(date(2026, 8, 28), date(2026, 9, 3)), (date(2026, 9, 17), date(2026, 9, 22)),
             (date(2026, 9, 25), date(2026, 9, 25))]
    for s_, e_ in cases:
        dt_s = datetime(s_.year, s_.month, s_.day, 12, tzinfo=TZ)
        dt_e = datetime(e_.year, e_.month, e_.day, 12, tzinfo=TZ)
        assert trading_days_between_dates(s_, e_, hol) == trading_days_between(dt_s, dt_e, hol)
    assert trading_days_between_dates(date(2026, 9, 17), date(2026, 9, 22)) == 3

