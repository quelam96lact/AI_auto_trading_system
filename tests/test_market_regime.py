"""Unit tests cho market_regime.py và measure_market_regime.py.

Tất định, không chạm DB, không sleep, không so giờ tường.
Test suite:
1. test_breadth_dem_dung: rổ dựng tay, 3/5 mã trên MA200 => breadth = 0.6.
2. test_phan_loai_dung_nguong: None => UNKNOWN, 0.60 => RISK_ON, 0.5999 => NEUTRAL, 0.40 => NEUTRAL, 0.3999 => RISK_OFF.
3. test_khong_nhin_trom_tuong_lai: thêm bar của ngày d+1 vào dữ liệu KHÔNG được làm đổi breadth(d).
4. test_ma_thieu_lich_su_bi_loai: mã có dưới 200 phiên không được tính vào mẫu số.
5. test_khong_du_mau_thi_UNKNOWN (A2): 49 mã => UNKNOWN, 50 mã => RISK_ON.
6. test_che_do_none_chan_mua_nhung_khong_chan_ban (A1): vị thế mở trong RISK_ON, sang NEUTRAL gặp tín hiệu SELL vẫn được thoát.
"""

from datetime import date, datetime, timedelta

import pytest

from scripts.market_regime import classify_regime, compute_breadth
from scripts.measure_market_regime import run_regime_switching_one_symbol
from trading.calendar_vn import TZ
from trading.models import Bar


def _make_bar(symbol: str, d: date, close: float, high: float | None = None, low: float | None = None, open_price: float | None = None) -> Bar:
    ts = datetime(d.year, d.month, d.day, 15, 0, tzinfo=TZ)
    h = high if high is not None else close
    l = low if low is not None else close
    o = open_price if open_price is not None else close
    return Bar(
        symbol=symbol,
        ts=ts,
        open=o,
        high=h,
        low=l,
        close=close,
        volume=10000.0,
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
    for sym in ["SYM1", "SYM2", "SYM3"]:
        bars = [_make_bar(sym, d, 100.0) for d in dates[:-1]]
        bars.append(_make_bar(sym, as_of, 110.0))
        bars_by_symbol[sym] = bars

    for sym in ["SYM4", "SYM5"]:
        bars = [_make_bar(sym, d, 100.0) for d in dates[:-1]]
        bars.append(_make_bar(sym, as_of, 90.0))
        bars_by_symbol[sym] = bars

    breadth = compute_breadth(bars_by_symbol, as_of, min_symbols=5)
    assert breadth is not None
    assert pytest.approx(breadth, rel=1e-6) == 0.6


def test_phan_loai_dung_nguong():
    """2. test_phan_loai_dung_nguong:
    None   => UNKNOWN
    0.60   => RISK_ON
    0.5999 => NEUTRAL
    0.40   => NEUTRAL
    0.3999 => RISK_OFF
    """
    assert classify_regime(None) == "UNKNOWN"
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

    breadth_before = compute_breadth(bars_by_symbol, as_of, min_symbols=5)

    # Thêm bar tương lai d+1 với biến động mạnh
    for sym in ["SYM1", "SYM2", "SYM3"]:
        bars_by_symbol[sym].append(_make_bar(sym, future_date, 10.0))
    for sym in ["SYM4", "SYM5"]:
        bars_by_symbol[sym].append(_make_bar(sym, future_date, 500.0))

    breadth_after = compute_breadth(bars_by_symbol, as_of, min_symbols=5)
    assert breadth_before == breadth_after
    assert breadth_after is not None
    assert pytest.approx(breadth_after, rel=1e-6) == 0.6


def test_ma_thieu_lich_su_bi_loai():
    """4. test_ma_thieu_lich_su_bi_loai:
    Mã có dưới 200 phiên không được tính vào mẫu số.
    """
    base_date = date(2020, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(200)]
    as_of = dates[-1]

    bars_by_symbol = {}
    for sym in ["SYM1", "SYM2"]:
        bars = [_make_bar(sym, d, 100.0) for d in dates[:-1]]
        bars.append(_make_bar(sym, as_of, 110.0))
        bars_by_symbol[sym] = bars

    for sym in ["SYM3", "SYM4"]:
        bars = [_make_bar(sym, d, 100.0) for d in dates[:-1]]
        bars.append(_make_bar(sym, as_of, 90.0))
        bars_by_symbol[sym] = bars

    sym_short = "SHORT1"
    short_dates = dates[100:]  # 100 bars
    bars_short = [_make_bar(sym_short, d, 50.0) for d in short_dates[:-1]]
    bars_short.append(_make_bar(sym_short, as_of, 200.0))
    bars_by_symbol[sym_short] = bars_short

    breadth = compute_breadth(bars_by_symbol, as_of, min_symbols=4)
    assert breadth is not None
    assert pytest.approx(breadth, rel=1e-6) == 0.5


def test_khong_du_mau_thi_UNKNOWN():
    """5. test_khong_du_mau_thi_UNKNOWN (A2):
    - 49 mã đủ 200 phiên (< 50) => compute_breadth trả về None, classify_regime => UNKNOWN.
    - 50 mã đủ 200 phiên (30 mã > MA200, 20 mã <= MA200) => breadth = 0.6, classify_regime => RISK_ON.
    """
    base_date = date(2020, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(200)]
    as_of = dates[-1]

    # Rổ 49 mã
    bars_49 = {}
    for i in range(49):
        sym = f"SYM_{i:02d}"
        bars_49[sym] = [_make_bar(sym, d, 100.0) for d in dates]

    breadth_49 = compute_breadth(bars_49, as_of)
    assert breadth_49 is None
    assert classify_regime(breadth_49) == "UNKNOWN"

    # Thêm 1 mã thành 50 mã (30 mã tăng giá phiên cuối, 20 mã giảm giá)
    bars_50 = {}
    for i in range(30):
        sym = f"UP_{i:02d}"
        b = [_make_bar(sym, d, 100.0) for d in dates[:-1]]
        b.append(_make_bar(sym, as_of, 110.0))
        bars_50[sym] = b
    for i in range(20):
        sym = f"DOWN_{i:02d}"
        b = [_make_bar(sym, d, 100.0) for d in dates[:-1]]
        b.append(_make_bar(sym, as_of, 90.0))
        bars_50[sym] = b

    breadth_50 = compute_breadth(bars_50, as_of, min_symbols=50)
    assert breadth_50 is not None
    assert pytest.approx(breadth_50, rel=1e-6) == 0.6
    assert classify_regime(breadth_50) == "RISK_ON"


def test_che_do_none_chan_mua_nhung_khong_chan_ban():
    """6. test_che_do_none_chan_mua_nhung_khong_chan_ban (A1):
    - Khởi tạo chuỗi bar cho DailyBreakout (N=20, M=10):
      * 20 bar đầu: giá đi ngang 100 với biên độ high=105, low=95 (ATR ~ 10, 3*ATR ~ 30 -> stop ở 112 - 30 = 82).
      * Bar 21 (RISK_ON): giá breakout lên 110 (high=112 > 105) -> sinh BUY signal -> khớp BUY ở bar 22 Open 110.
      * Bar 22: thị trường chuyển sang NEUTRAL (rule: NONE).
      * Bar 23 (NEUTRAL): giá giảm xuống 94 (low=94 < 95 bear crossover, nhưng 94 > stop 82 nên TrailingStop KHÔNG kích hoạt).
        -> DailyBreakout sinh SELL signal theo luật chiến lược.
      * Bar 24 (NEUTRAL): Khớp SELL ở Open 94, đóng vị thế về 0.
    - Khẳng định:
      * Có đúng 1 lệnh BUY và 1 lệnh SELL (thoát bởi strategy SELL trong NEUTRAL).
      * Khi chạy với code cũ (block_sell_in_none=True): lệnh SELL bị nuốt, vị thế bị kẹt (0 SELL fills).
    """
    base_date = date(2020, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(30)]

    bars: list[Bar] = []
    # 20 bars đầu giá 100 (high=105, low=95) -> ATR ~ 10
    for i in range(20):
        bars.append(_make_bar("TEST_SYM", dates[i], 100.0, high=105.0, low=95.0, open_price=100.0))

    # Bar 20 (ngày 20): Breakout lên 110 (high=112 > max(highs)=105) -> BUY signal
    bars.append(_make_bar("TEST_SYM", dates[20], 110.0, high=112.0, low=100.0, open_price=100.0))

    # Bar 21 (ngày 21): Mở vị thế BUY tại Open 110 (T+0). Giá đóng 108.
    bars.append(_make_bar("TEST_SYM", dates[21], 108.0, high=110.0, low=107.0, open_price=110.0))

    # Bar 22 (ngày 22, T+1): Giữ giá 108.
    bars.append(_make_bar("TEST_SYM", dates[22], 108.0, high=109.0, low=106.0, open_price=108.0))

    # Bar 23 (ngày 23, T+2): Giữ giá 107.
    bars.append(_make_bar("TEST_SYM", dates[23], 107.0, high=108.0, low=106.0, open_price=107.0))

    # Bar 24 (ngày 24, T+3 - đã settle): Giá giảm xuống 94.5 (low=94.5 < min(lows)=95 -> bear crossover).
    # Trailing stop lúc này ở ~93.6 nên KHÔNG chạm stop. Strategy sinh SELL signal.
    bars.append(_make_bar("TEST_SYM", dates[24], 94.5, high=100.0, low=94.5, open_price=98.0))

    # Bar 25 (ngày 25): Khớp SELL tại Open 94.5.
    bars.append(_make_bar("TEST_SYM", dates[25], 94.5, high=96.0, low=94.0, open_price=94.5))

    # Thiết lập regime:
    # Bar 0..20: RISK_ON
    # Bar 21..25: NEUTRAL (rule là NONE)
    prior_regime_by_date: dict[date, str] = {}
    for d in dates[:21]:
        prior_regime_by_date[d] = "RISK_ON"
    for d in dates[21:]:
        prior_regime_by_date[d] = "NEUTRAL"

    rule = {
        "RISK_ON": "daily_breakout",
        "NEUTRAL": "NONE",
        "RISK_OFF": "NONE",
    }

    capital = 1_000_000_000.0
    _strat_pnl, _bh_pnl, fills = run_regime_switching_one_symbol(
        bars, rule, prior_regime_by_date, capital, block_sell_in_none=False
    )

    buy_fills = [f for f in fills if f.side == "BUY"]
    sell_fills = [f for f in fills if f.side == "SELL"]

    assert len(buy_fills) == 1, f"Phải có đúng 1 lệnh BUY, nhận được {len(buy_fills)}"
    assert len(sell_fills) == 1, f"Phải có đúng 1 lệnh SELL khi có bear crossover trong NEUTRAL, nhận được {len(sell_fills)}"
    assert sell_fills[0].qty == buy_fills[0].qty
