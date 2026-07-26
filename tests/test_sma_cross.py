from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.strategies.sma_cross import SmaCrossStrategy


class FakeContext:
    def __init__(self, qty=0):
        self.qty = qty

    def position_qty(self, symbol):
        return self.qty


def bar_at(i, close):
    return Bar(
        "VCB",
        datetime(2026, 7, 15, 9, 0, tzinfo=TZ) + timedelta(minutes=15 * i),
        close,
        close,
        close,
        close,
        100,
    )


def test_no_signal_before_enough_history():
    s = SmaCrossStrategy(fast=2, slow=4)
    ctx = FakeContext()
    for i, price in enumerate([10, 10, 10]):
        assert s.on_bar(bar_at(i, price), ctx) is None


def test_buy_signal_on_fast_crossing_above_slow():
    s = SmaCrossStrategy(fast=2, slow=4, qty=100)
    ctx = FakeContext(qty=0)
    prices = [10, 10, 10, 10, 20, 20]
    signals = [s.on_bar(bar_at(i, p), ctx) for i, p in enumerate(prices)]
    assert any(sig is not None and sig.side == "BUY" and sig.qty == 100 for sig in signals)


def test_sell_signal_when_holding_and_fast_crosses_below():
    s = SmaCrossStrategy(fast=2, slow=4, qty=100)
    ctx = FakeContext(qty=100)
    prices = [10, 10, 10, 10, 20, 20, 10, 10]
    signals = [s.on_bar(bar_at(i, p), ctx) for i, p in enumerate(prices)]
    assert any(sig is not None and sig.side == "SELL" for sig in signals)


def test_compute_crossover_reports_bear_even_when_never_bought():
    s = SmaCrossStrategy(fast=2, slow=4, qty=100)
    # Build enough history with rising prices so fast MA is above slow MA,
    # then reverse down to trigger a bearish crossover. We never call on_bar,
    # so no position context is involved.
    prices = [10, 10, 10, 10, 20, 20, 10, 10]
    crossovers = [s.compute_crossover(bar_at(i, p)) for i, p in enumerate(prices)]

    # Crossover happens at bar #6, but because last_crossover only reflects the
    # most recent compute_crossover() call, by the end of the loop (after a
    # non-crossover bar) it is None. Assert that the crossover did fire during
    # the series by checking the returned values directly.
    assert "bear" in crossovers
    assert crossovers.index("bear") < len(prices) - 1


def test_last_crossover_returns_none_before_enough_history():
    s = SmaCrossStrategy(fast=2, slow=4, qty=100)
    for i, p in enumerate([10, 10]):
        s.compute_crossover(bar_at(i, p))
    assert s.last_crossover("VCB") is None
