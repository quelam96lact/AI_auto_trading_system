"""Tests cho MomentumBreakoutStrategy (bull flag / bear breakdown + volume spike).

Dung helper bars_from_hlcv nhan list[(high, low, close, volume)] - giong pattern
bars_from_prices trong tests/test_derivative_backtest.py nhung co volume tuy chinh
tung bar (strategy nay can volume).

Tham so test: lookback=3, volume_period=3, volume_multiplier=2.0,
atr_pct_threshold=0.0 (tat ATR% filter) - chuoi test ngan gon.
"""

from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.derivative_backtest import DERIVATIVE_SYMBOL
from trading.models import Bar
from trading.strategies.momentum_breakout import MomentumBreakoutStrategy


def bars_from_hlcv(
    hlcv: list[tuple[float, float, float, int]], sym: str = DERIVATIVE_SYMBOL
) -> list[Bar]:
    start = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
    return [
        Bar(sym, start + timedelta(minutes=5 * i), close, high, low, close, volume)
        for i, (high, low, close, volume) in enumerate(hlcv)
    ]


def new_strategy(**kwargs: object) -> MomentumBreakoutStrategy:
    # lookback/volume_period nho de chuoi test ngan; volume_multiplier=2.0,
    # atr_pct_threshold=0.0 (tat ATR% filter) - cung ky thuat new_strategy()
    # trong tests/test_derivative_backtest.py (tat filter de tin hieu khong
    # bi che), qty=1 vi lot_size phai sinh = 1.
    params: dict[str, object] = {
        "qty": 1,
        "lookback": 3,
        "volume_period": 3,
        "volume_multiplier": 2.0,
        "atr_pct_threshold": 0.0,
    }
    params.update(kwargs)
    return MomentumBreakoutStrategy(**params)  # type: ignore[arg-type]


# 3 bar warm-up gia di ngang: channel_high=10.5, channel_low=9.5, avg_volume=100.
WARMUP = [(10.5, 9.5, 10.0, 100)] * 3


def test_no_signal_during_warmup():
    bars = bars_from_hlcv(WARMUP)
    strategy = new_strategy()
    # 3 bar dau chua du lookback=3 bar TRUOC do -> None cho ca 3.
    for bar in bars:
        assert strategy.compute_crossover(bar) is None


def test_bull_breakout_with_volume_spike():
    bars = bars_from_hlcv(WARMUP + [(11.0, 10.0, 11.0, 250)])
    strategy = new_strategy()
    for bar in bars[:3]:
        strategy.compute_crossover(bar)
    # close=11 > channel_high=10.5, volume=250 >= 2*100 -> bull.
    assert strategy.compute_crossover(bars[3]) == "bull"


def test_no_signal_breakout_without_volume_spike():
    bars = bars_from_hlcv(WARMUP + [(11.0, 10.0, 11.0, 150)])
    strategy = new_strategy()
    for bar in bars[:3]:
        strategy.compute_crossover(bar)
    # Breakout gia dung (11 > 10.5) nhung volume=150 < 2*100 -> None.
    assert strategy.compute_crossover(bars[3]) is None


def test_bear_breakdown_with_volume_spike():
    bars = bars_from_hlcv(WARMUP + [(9.5, 8.5, 9.0, 250)])
    strategy = new_strategy()
    for bar in bars[:3]:
        strategy.compute_crossover(bar)
    # close=9 < channel_low=9.5, volume=250 >= 2*100 -> bear.
    assert strategy.compute_crossover(bars[3]) == "bear"


def test_no_signal_close_inside_channel():
    bars = bars_from_hlcv(WARMUP + [(10.6, 9.9, 10.2, 250)])
    strategy = new_strategy()
    for bar in bars[:3]:
        strategy.compute_crossover(bar)
    # close=10.2 nam trong [9.5, 10.5] -> None du volume du.
    assert strategy.compute_crossover(bars[3]) is None


def test_atr_filter_blocks_signal_when_enabled():
    bars = bars_from_hlcv(WARMUP + [(11.0, 10.0, 11.0, 250)])
    # atr_pct_threshold=0.5 cao bat thuong co chu dich de chac chan chan;
    # atr_period=14 mac dinh -> ATR chua warm-up (moi 4 bar) -> atr=None
    # -> candidate bi ep ve None.
    strategy = new_strategy(atr_pct_threshold=0.5)
    for bar in bars[:3]:
        strategy.compute_crossover(bar)
    assert strategy.compute_crossover(bars[3]) is None


def test_last_crossover_and_last_atr_reflect_last_call():
    bars = bars_from_hlcv(WARMUP + [(11.0, 10.0, 11.0, 250)])
    # atr_period=1 de ATR san sau 1 bar (khong phai None).
    strategy = new_strategy(atr_period=1)
    for bar in bars[:3]:
        strategy.compute_crossover(bar)
    assert strategy.compute_crossover(bars[3]) == "bull"
    assert strategy.last_crossover(DERIVATIVE_SYMBOL) == "bull"
    assert strategy.last_atr(DERIVATIVE_SYMBOL) is not None


def test_zero_close_does_not_crash():
    bars = bars_from_hlcv(WARMUP + [(11.0, 10.0, 0.0, 250)])
    strategy = new_strategy()
    for bar in bars[:3]:
        strategy.compute_crossover(bar)
    # Bar dich dang close=0.0: khong duoc raise, tra None (guard close<=0).
    assert strategy.compute_crossover(bars[3]) is None
