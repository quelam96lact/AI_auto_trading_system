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
    s = SmaCrossStrategy(fast=2, slow=4, atr_period=1, atr_pct_threshold=0.0)
    ctx = FakeContext()
    for i, price in enumerate([10, 10, 10]):
        assert s.on_bar(bar_at(i, price), ctx) is None


def test_buy_signal_on_fast_crossing_above_slow():
    s = SmaCrossStrategy(fast=2, slow=4, qty=100, atr_period=1, atr_pct_threshold=0.0)
    ctx = FakeContext(qty=0)
    prices = [10, 10, 10, 10, 20, 20]
    signals = [s.on_bar(bar_at(i, p), ctx) for i, p in enumerate(prices)]
    assert any(
        sig is not None and sig.side == "BUY" and sig.qty == 100 for sig in signals
    )


def test_sell_signal_when_holding_and_fast_crosses_below():
    s = SmaCrossStrategy(fast=2, slow=4, qty=100, atr_period=1, atr_pct_threshold=0.0)
    ctx = FakeContext(qty=100)
    prices = [10, 10, 10, 10, 20, 20, 10, 10]
    signals = [s.on_bar(bar_at(i, p), ctx) for i, p in enumerate(prices)]
    assert any(sig is not None and sig.side == "SELL" for sig in signals)


def test_compute_crossover_reports_bear_even_when_never_bought():
    s = SmaCrossStrategy(fast=2, slow=4, qty=100, atr_period=1, atr_pct_threshold=0.0)
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
    s = SmaCrossStrategy(fast=2, slow=4, qty=100, atr_period=1, atr_pct_threshold=0.0)
    for i, p in enumerate([10, 10]):
        s.compute_crossover(bar_at(i, p))
    assert s.last_crossover("VCB") is None


# Same MA shape used by the tests above (fast=2, slow=4): flat at 10, jumps to
# 20 (bull crossover), then back to 10 (bear crossover). The jump itself
# produces a large True Range (|high-prev_close| = 10), so atr_pct_threshold
# alone decides whether the crossover is reported.
_CROSSOVER_PRICES = [10, 10, 10, 10, 20, 20, 10, 10]


def test_crossover_suppressed_when_atr_pct_below_threshold():
    # atr/close peaks at 1.0 (bear leg: TR=10 on close=10) -> threshold=1.5
    # is unreachable by either leg -> every crossover, bull and bear, must be
    # suppressed.
    s = SmaCrossStrategy(fast=2, slow=4, atr_period=1, atr_pct_threshold=1.5)
    crossovers = [
        s.compute_crossover(bar_at(i, p)) for i, p in enumerate(_CROSSOVER_PRICES)
    ]
    assert "bull" not in crossovers
    assert "bear" not in crossovers


def test_crossover_fires_when_atr_pct_above_threshold():
    s = SmaCrossStrategy(fast=2, slow=4, atr_period=1, atr_pct_threshold=0.005)
    crossovers = [
        s.compute_crossover(bar_at(i, p)) for i, p in enumerate(_CROSSOVER_PRICES)
    ]
    assert "bull" in crossovers
    assert "bear" in crossovers


def test_crossover_suppressed_during_atr_warmup():
    # atr_period longer than the whole series -> ATR never leaves warm-up
    # (always None) -> every crossover suppressed regardless of threshold.
    s = SmaCrossStrategy(fast=2, slow=4, atr_period=20, atr_pct_threshold=0.0)
    crossovers = [
        s.compute_crossover(bar_at(i, p)) for i, p in enumerate(_CROSSOVER_PRICES)
    ]
    assert "bull" not in crossovers
    assert "bear" not in crossovers


def test_compute_crossover_does_not_crash_on_zero_close():
    # A degenerate/malformed bar with close=0 lands exactly on a real bear
    # crossover (fast MA drops to 0, below slow MA) - must not crash the
    # ATR% check (atr / bar.close). A single bad bar must not be able to
    # take down the whole engine loop, which has no exception handling
    # around process_bar().
    s = SmaCrossStrategy(fast=1, slow=3, atr_period=1, atr_pct_threshold=0.005)
    prices = [10, 10, 10, 20, 0]
    crossovers = [s.compute_crossover(bar_at(i, p)) for i, p in enumerate(prices)]
    # must not raise ZeroDivisionError, and a close<=0 bar can't validly pass
    # the ATR% check either way, so it's suppressed rather than trusted.
    assert crossovers[-1] is None
