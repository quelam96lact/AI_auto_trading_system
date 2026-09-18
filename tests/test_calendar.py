from datetime import date, datetime

from trading.calendar_vn import TZ, is_continuous_matching, is_trading_time


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


# ============ Brief đợt 46 Task 2: is_continuous_matching Tests ============


def test_is_continuous_matching_boundaries():
    """Brief 46 Task 2 §2.3 Tiêu chí 1: Kiểm tra ranh giới khớp lệnh liên tục.

    Đúng tại: 09:15, 10:00, 11:29, 13:00, 14:29.
    Sai tại: 09:02, 09:14, 11:31, 12:00, 14:31, 14:40, 15:00.
    Hai mốc 09:02 và 14:32 (hai thời điểm chuông từng kêu sai) bắt buộc False.
    """
    # Các mốc ĐÚNG trong giờ khớp lệnh liên tục
    assert is_continuous_matching(dt(9, 15)) is True
    assert is_continuous_matching(dt(10, 0)) is True
    assert is_continuous_matching(dt(11, 29)) is True
    assert is_continuous_matching(dt(13, 0)) is True
    assert is_continuous_matching(dt(14, 29)) is True

    # Các mốc SAI (ngoài giờ, ATO, nghỉ trưa, ATC, sau đóng cửa)
    assert is_continuous_matching(dt(9, 2)) is False   # ATO (mốc chuông kêu sai 1)
    assert is_continuous_matching(dt(9, 14)) is False  # cuối ATO
    assert is_continuous_matching(dt(11, 31)) is False # vừa hết phiên sáng
    assert is_continuous_matching(dt(12, 0)) is False  # nghỉ trưa
    assert is_continuous_matching(dt(14, 31)) is False # ATC
    assert is_continuous_matching(dt(14, 32)) is False # ATC (mốc chuông kêu sai 2)
    assert is_continuous_matching(dt(14, 40)) is False # giữa ATC
    assert is_continuous_matching(dt(15, 0)) is False  # sau giờ đóng cửa


def test_is_continuous_matching_weekend_and_holiday():
    """Brief 46 Task 2 §2.3 Tiêu chí 2: Ngày nghỉ lễ và cuối tuần -> sai ở mọi giờ."""
    # Thứ Bảy (day=18)
    assert is_continuous_matching(dt(9, 15, day=18)) is False
    assert is_continuous_matching(dt(10, 0, day=18)) is False
    assert is_continuous_matching(dt(13, 30, day=18)) is False

    # Chủ Nhật (day=19)
    assert is_continuous_matching(dt(10, 0, day=19)) is False

    # Ngày lễ chỉ định
    holiday_set = frozenset({date(2026, 7, 15)})
    assert is_continuous_matching(dt(9, 15), holidays=holiday_set) is False
    assert is_continuous_matching(dt(10, 0), holidays=holiday_set) is False
    assert is_continuous_matching(dt(13, 30), holidays=holiday_set) is False