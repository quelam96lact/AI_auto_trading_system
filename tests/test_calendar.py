from datetime import date, datetime

from trading.calendar_vn import TZ, is_trading_time


def dt(h, m, day=15):  # 2026-07-15 là thứ Tư
    return datetime(2026, 7, day, h, m, tzinfo=TZ)

def test_in_morning_session():
    assert is_trading_time(dt(9, 0))
    assert is_trading_time(dt(11, 29))

def test_lunch_break_and_after_close():
    assert not is_trading_time(dt(12, 0))
    assert not is_trading_time(dt(14, 46))

def test_atc_inclusive():
    assert is_trading_time(dt(14, 45))

def test_weekend_and_holiday():
    assert not is_trading_time(dt(10, 0, day=18))  # thứ Bảy
    assert not is_trading_time(dt(10, 0), holidays={date(2026, 7, 15)})