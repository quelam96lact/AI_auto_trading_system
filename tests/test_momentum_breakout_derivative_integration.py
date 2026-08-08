"""Integration test: MomentumBreakoutStrategy cam vao run_derivative_backtest
KHONG sua gi trong trading/derivative_backtest.py.

Chung minh strategy moi duck-type dung interface ma run_derivative_backtest()
can (compute_crossover + .qty), y het cach SmaCrossStrategy da dung - khong
can doi type hint hay code cua derivative_backtest.py.
"""

from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.derivative_backtest import DERIVATIVE_SYMBOL, run_derivative_backtest
from trading.derivative_risk import DerivativeRiskManager
from trading.models import Bar
from trading.strategies.momentum_breakout import MomentumBreakoutStrategy

CAP = 100_000_000


def bars_from_hlcv(
    hlcv: list[tuple[float, float, float, int]], sym: str = DERIVATIVE_SYMBOL
) -> list[Bar]:
    start = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
    return [
        Bar(sym, start + timedelta(minutes=5 * i), close, high, low, close, volume)
        for i, (high, low, close, volume) in enumerate(hlcv)
    ]


def test_momentum_breakout_plugs_into_derivative_backtest_without_changes():
    # Chuoi gia da xac nhan that (chay qua MomentumBreakoutStrategy.compute_crossover
    # truc tiep voi lookback=3/volume_period=3/volume_multiplier=2.0): bull tai
    # bar4 (close=11 > channel_high=10.5, volume 250 >= 2*100), bear tai bar8
    # (close=9.5 < channel_low=11.0, volume 600 >= 2*250) - giong ghi chu
    # "da xac nhan that" trong tests/test_derivative_backtest.py.
    hlcv = [
        (10.5, 9.5, 10.0, 100),  # bar1-3: warm-up gia di ngang
        (10.5, 9.5, 10.0, 100),
        (10.5, 9.5, 10.0, 100),
        (11.5, 10.0, 11.0, 250),  # bar4: bull breakout -> mo long tai 11.0
        (12.5, 11.0, 12.0, 250),
        (13.5, 12.0, 13.0, 250),
        (14.5, 13.0, 14.0, 250),
        (11.0, 9.0, 9.5, 600),  # bar8: bear breakdown -> dong long tai 9.5
        (12.0, 10.0, 11.0, 100),
        (12.5, 10.5, 11.5, 300),
    ]
    bars = bars_from_hlcv(hlcv)
    strategy = MomentumBreakoutStrategy(qty=1, lookback=3, volume_period=3, volume_multiplier=2.0)
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    # Duck-typing co chu dich: run_derivative_backtest chi can compute_crossover
    # + .qty (xem plan 2026-08-08-momentum-breakout-strategy.md) - khong sua
    # type hint cua no. Pyright bao arg-type la dung y, runtime OK.
    report = run_derivative_backtest(bars, strategy, risk, CAP)  # type: ignore[arg-type]

    # It nhat 1 round-trip xay ra (mo long bar4, dong bar8) ma khong can sua
    # gi trong run_derivative_backtest().
    assert report.trades >= 1
