"""Unit tests cho market_regime.py.

Tất định, không chạm DB, không sleep, không so giờ tường.
Bốn test bắt buộc:
1. test_breadth_dem_dung: rổ dựng tay, 3/5 mã trên MA200 => breadth = 0.6.
2. test_phan_loai_dung_nguong: 0.60 => RISK_ON, 0.5999 => NEUTRAL, 0.40 => NEUTRAL, 0.3999 => RISK_OFF.
3. test_khong_nhin_trom_tuong_lai: thêm bar của ngày d+1 vào dữ liệu KHÔNG được làm đổi breadth(d).
4. test_ma_thieu_lich_su_bi_loai: mã có dưới 200 phiên không được tính vào mẫu số.
"""

from datetime import date, datetime, timedelta

import pytest

from scripts.market_regime import classify_regime, compute_breadth
from trading.calendar_vn import TZ
from trading.models import Bar


def _make_bar(symbol: str, d: date, close: float) -> Bar:
    ts = datetime(d.year, d.month, d.day, 15, 0, tzinfo=TZ)
    return Bar(
        symbol=symbol,
        ts=ts,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
        source="test",
    )


def test_breadth_dem_dung():
    """1. test_breadth_dem_dung: rổ 5 mã, mỗi mã 200 phiên.
    3 mã có close > SMA200 (100 -> 110 ở phiên cuối).
    2 mã có close <= SMA200 (100 -> 90 ở phiên cuối).
    => breadth = 3/5 = 0.6.
    """
    base_date = date(2020, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(200)]
    as_of = dates[-1]

    bars_by_symbol = {}
    # 3 mã tăng ở phiên 200: SMA200 ~ 100.05, close = 110 > SMA200
    for sym in ["SYM1", "SYM2", "SYM3"]:
        bars = [_make_bar(sym, d, 100.0) for d in dates[:-1]]
        bars.append(_make_bar(sym, as_of, 110.0))
        bars_by_symbol[sym] = bars

    # 2 mã giảm ở phiên 200: SMA200 ~ 99.95, close = 90 <= SMA200
    for sym in ["SYM4", "SYM5"]:
        bars = [_make_bar(sym, d, 100.0) for d in dates[:-1]]
        bars.append(_make_bar(sym, as_of, 90.0))
        bars_by_symbol[sym] = bars

    breadth = compute_breadth(bars_by_symbol, as_of)
    assert pytest.approx(breadth, rel=1e-6) == 0.6


def test_phan_loai_dung_nguong():
    """2. test_phan_loai_dung_nguong:
    0.60   => RISK_ON
    0.5999 => NEUTRAL
    0.40   => NEUTRAL
    0.3999 => RISK_OFF
    """
    assert classify_regime(0.60) == "RISK_ON"
    assert classify_regime(0.75) == "RISK_ON"
    assert classify_regime(0.5999) == "NEUTRAL"
    assert classify_regime(0.40) == "NEUTRAL"
    assert classify_regime(0.3999) == "RISK_OFF"
    assert classify_regime(0.10) == "RISK_OFF"


def test_khong_nhin_trom_tuong_lai():
    """3. test_khong_nhin_trom_tuong_lai:
    Thêm bar của ngày d+1 vào dữ liệu KHÔNG được làm đổi breadth(d).
    """
    base_date = date(2020, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(200)]
    as_of = dates[-1]
    future_date = as_of + timedelta(days=1)

    bars_by_symbol = {}
    for sym in ["SYM1", "SYM2", "SYM3"]:
        bars = [_make_bar(sym, d, 100.0) for d in dates[:-1]]
        bars.append(_make_bar(sym, as_of, 110.0))
        bars_by_symbol[sym] = bars

    for sym in ["SYM4", "SYM5"]:
        bars = [_make_bar(sym, d, 100.0) for d in dates[:-1]]
        bars.append(_make_bar(sym, as_of, 90.0))
        bars_by_symbol[sym] = bars

    breadth_before = compute_breadth(bars_by_symbol, as_of)

    # Thêm bar tương lai d+1 với biến động mạnh làm đảo ngược toàn bộ nếu nhìn trộm
    for sym in ["SYM1", "SYM2", "SYM3"]:
        bars_by_symbol[sym].append(_make_bar(sym, future_date, 10.0))
    for sym in ["SYM4", "SYM5"]:
        bars_by_symbol[sym].append(_make_bar(sym, future_date, 500.0))

    breadth_after = compute_breadth(bars_by_symbol, as_of)
    assert breadth_before == breadth_after
    assert pytest.approx(breadth_after, rel=1e-6) == 0.6


def test_ma_thieu_lich_su_bi_loai():
    """4. test_ma_thieu_lich_su_bi_loai:
    Mã có dưới 200 phiên không được tính vào mẫu số (denominator).
    Ví dụ: 4 mã đủ 200 phiên (2 trên MA200, 2 dưới MA200) + 1 mã chỉ có 100 phiên (giá tăng mạnh).
    => breadth = 2 / 4 = 0.5 (không phải 3 / 5 = 0.6).
    """
    base_date = date(2020, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(200)]
    as_of = dates[-1]

    bars_by_symbol = {}
    # 2 mã đủ 200 bar, close > SMA200
    for sym in ["SYM1", "SYM2"]:
        bars = [_make_bar(sym, d, 100.0) for d in dates[:-1]]
        bars.append(_make_bar(sym, as_of, 110.0))
        bars_by_symbol[sym] = bars

    # 2 mã đủ 200 bar, close <= SMA200
    for sym in ["SYM3", "SYM4"]:
        bars = [_make_bar(sym, d, 100.0) for d in dates[:-1]]
        bars.append(_make_bar(sym, as_of, 90.0))
        bars_by_symbol[sym] = bars

    # 1 mã chỉ có 100 bar, close tăng mạnh
    sym_short = "SHORT1"
    short_dates = dates[100:]  # 100 bars
    bars_short = [_make_bar(sym_short, d, 50.0) for d in short_dates[:-1]]
    bars_short.append(_make_bar(sym_short, as_of, 200.0))
    bars_by_symbol[sym_short] = bars_short

    breadth = compute_breadth(bars_by_symbol, as_of)
    # Mẫu số là 4 mã, tử số là 2 mã => 2/4 = 0.5
    assert pytest.approx(breadth, rel=1e-6) == 0.5
