from datetime import datetime, timedelta

from trading.backtest import run_backtest
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.risk import RiskManager
from trading.strategies.sma_cross import SmaCrossStrategy

CAP = 100_000_000


def make_bars(prices: list[float]) -> list[Bar]:
    start = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    return [
        Bar("VCB", start + timedelta(minutes=15 * i), p, p, p, p, 1000)
        for i, p in enumerate(prices)
    ]


def test_deterministic_same_input_same_output():
    prices = [10] * 20 + [20] * 10 + [10] * 10
    bars = make_bars(prices)
    strategy = SmaCrossStrategy(fast=10, slow=20, qty=100)
    risk = RiskManager(capital=CAP)
    r1 = run_backtest(bars, strategy, risk, CAP)

    strategy2 = SmaCrossStrategy(fast=10, slow=20, qty=100)
    risk2 = RiskManager(capital=CAP)
    r2 = run_backtest(bars, strategy2, risk2, CAP)

    assert r1 == r2


def test_report_has_at_least_one_round_trip_trade():
    prices = [10] * 20 + [20] * 10 + [10] * 10
    bars = make_bars(prices)
    r = run_backtest(
        bars,
        SmaCrossStrategy(fast=10, slow=20, qty=100),
        # max_daily_loss_pct mac dinh (3%) khong con phu hop sau khi BUY qty
        # duoc ATR sizing quyet dinh (lon hon nhieu so voi fixed-100 truoc
        # day) - swing gia 20->10 tren qty lon trong test nay tao unrealized
        # loss ~7% von, se bi halt truoc khi kip SELL round-trip. Noi len
        # nguong o day chi de test nay khong bi chan boi 1 tinh huong tong
        # hop bien do lon bat thuong - KHONG doi default cua RiskManager.
        RiskManager(capital=CAP, max_daily_loss_pct=0.5),
        CAP,
    )
    assert r.trades >= 1
    assert 0.0 <= r.win_rate <= 1.0
    assert r.max_drawdown >= 0.0


def test_ending_cash_reflects_fees_when_no_trades():
    bars = make_bars([10] * 5)
    r = run_backtest(
        bars,
        SmaCrossStrategy(fast=10, slow=20, qty=100),
        RiskManager(capital=CAP),
        CAP,
    )
    assert r.ending_cash == CAP
    assert r.trades == 0
