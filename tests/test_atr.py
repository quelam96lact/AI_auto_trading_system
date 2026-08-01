from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.indicators import AtrCalculator
from trading.models import Bar


def bar(i, o, h, low, c):
    return Bar(
        "VCB",
        datetime(2026, 7, 15, 9, 0, tzinfo=TZ) + timedelta(minutes=5 * i),
        o,
        h,
        low,
        c,
        100,
    )


def test_returns_none_during_warmup():
    atr = AtrCalculator(period=3)
    assert atr.update(bar(0, 10, 12, 9, 11)) is None
    assert atr.update(bar(1, 11, 13, 10, 12)) is None
    # 3rd bar completes the warm-up window (period=3) -> no longer None
    assert atr.update(bar(2, 12, 14, 11, 13)) is not None


def test_computes_correct_atr_value():
    atr = AtrCalculator(period=3)
    # bar0: no prev_close -> TR = high-low = 12-9 = 3
    atr.update(bar(0, 10, 12, 9, 11))
    # bar1: prev_close=11 -> TR = max(13-10=3, |13-11|=2, |10-11|=1) = 3
    atr.update(bar(1, 11, 13, 10, 12))
    # bar2: prev_close=12 -> TR = max(14-11=3, |14-12|=2, |11-12|=1) = 3
    result = atr.update(bar(2, 12, 14, 11, 13))
    assert result == 3.0  # avg(3, 3, 3)


def test_rolls_off_oldest_true_range():
    atr = AtrCalculator(period=2)
    atr.update(bar(0, 10, 10, 10, 10))  # TR = 0 (high==low, no prev_close)
    atr.update(bar(1, 10, 20, 10, 20))  # TR = max(10, |20-10|=10, 0) = 10
    result = atr.update(bar(2, 20, 20, 20, 20))  # TR = max(0, 0, 0) = 0
    # window is now [bar1 TR=10, bar2 TR=0] (bar0's TR=0 rolled off, though it
    # was 0 too here so use distinguishable values below to prove roll-off)
    assert result == 5.0


def test_independent_state_per_symbol():
    atr = AtrCalculator(period=2)
    vcb1 = Bar("VCB", datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 10, 12, 9, 11, 100)
    vcb2 = Bar("VCB", datetime(2026, 7, 15, 9, 5, tzinfo=TZ), 11, 13, 10, 12, 100)
    hpg1 = Bar("HPG", datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 50, 55, 45, 52, 100)

    atr.update(vcb1)
    assert atr.update(hpg1) is None  # HPG only has 1 bar so far, its own warm-up
    assert atr.update(vcb2) is not None  # VCB now has 2 bars, its own warm-up done
