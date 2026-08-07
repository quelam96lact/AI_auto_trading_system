from datetime import datetime

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.trailing_stop import TrailingStopManager


def bar(o, h, l, c, sym="VCB", m=0):
    return Bar(sym, datetime(2026, 7, 15, 9, m, tzinfo=TZ), o, h, l, c, 1000)


def test_check_returns_none_before_position_opened():
    ts = TrailingStopManager(sl_multiplier=2.0)
    assert ts.check(bar(10, 10, 10, 10), atr=1.0) is None


def test_check_returns_none_when_atr_is_none():
    ts = TrailingStopManager(sl_multiplier=2.0)
    ts.on_position_opened("VCB", fill_price=100.0)
    assert ts.check(bar(1, 1, 1, 1), atr=None) is None


def test_highest_price_is_remembered_across_bars_not_just_latest_high():
    # sl_multiplier=2.0, atr=1.0 co dinh moi bar.
    ts = TrailingStopManager(sl_multiplier=2.0)
    ts.on_position_opened("VCB", fill_price=100.0)

    # Bar 1: day highest len 112 (tam range hep de KHONG trigger: stop =
    # 112 - 1*2 = 110, low=111 > 110).
    result1 = ts.check(bar(111, 112, 111, 112, m=0), atr=1.0)
    assert result1 is None

    # Bar 2: high moi (109) THAP HON highest da luu (112). Neu buggy code
    # dung high cua bar nay thay vi nho highest that su, stop se la
    # 109-2=107 va low=108 se KHONG trigger. Code dung phai nho highest=112
    # -> stop=112-2=110, low=108<=110 -> TRIGGER.
    result2 = ts.check(bar(109, 109, 108, 109, m=5), atr=1.0)
    assert result2 == 109  # min(bar.open=109, stop=110) = 109


def test_stop_triggers_at_computed_level_when_no_gap():
    ts = TrailingStopManager(sl_multiplier=1.0)
    ts.on_position_opened("VCB", fill_price=100.0)
    ts.check(bar(100, 130, 100, 130, m=0), atr=1.0)  # highest -> 130
    # stop = 130 - 1*1 = 129, bar mo cua dung tai 129 (khong gap)
    result = ts.check(bar(129, 129, 128, 128, m=5), atr=1.0)
    assert result == 129  # min(129, 129)


def test_stop_fills_at_open_on_gap_down_not_at_nominal_stop_level():
    ts = TrailingStopManager(sl_multiplier=1.0)
    ts.on_position_opened("VCB", fill_price=100.0)
    ts.check(bar(100, 101, 100, 101, m=0), atr=1.0)  # highest -> 101
    # stop = 101 - 1*1 = 100. Bar sau GAP xuong duoi stop: open=95.
    result = ts.check(bar(95, 96, 90, 92, m=5), atr=1.0)
    assert result == 95  # gap-down: khop tai open (95), khong phai stop_level (100)


def test_on_position_closed_resets_highest_for_next_entry():
    ts = TrailingStopManager(sl_multiplier=2.0)
    ts.on_position_opened("VCB", fill_price=100.0)
    ts.check(
        bar(148, 150, 149, 149, m=0), atr=1.0
    )  # highest -> 150, khong trigger (stop=148, low=149>148)

    ts.on_position_closed("VCB")
    assert (
        ts.check(bar(10, 10, 10, 10, m=5), atr=1.0) is None
    )  # khong con vi the nao dang theo doi

    ts.on_position_opened("VCB", fill_price=20.0)
    # Neu highest KHONG duoc reset (con nho 150 tu vi the truoc), stop se la
    # 150-2=148 va low=21 se sai trigger. Code dung: highest moi = max(20,22)=22,
    # stop=22-1*2=20, low=21>20 -> KHONG trigger.
    result = ts.check(bar(21, 22, 21, 21, m=10), atr=1.0)
    assert result is None
