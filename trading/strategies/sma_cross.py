from collections import deque

from trading.models import Bar
from trading.strategy import Context, Signal


class SmaCrossStrategy:
    def __init__(self, fast: int = 10, slow: int = 20, qty: int = 100):
        self.fast = fast
        self.slow = slow
        self.qty = qty
        self._closes: dict[str, deque] = {}
        self._prev_above: dict[str, bool | None] = {}

    def on_bar(self, bar: Bar, context: Context) -> Signal | None:
        closes = self._closes.setdefault(bar.symbol, deque(maxlen=self.slow))
        closes.append(bar.close)
        if len(closes) < self.slow:
            return None

        values = list(closes)
        fast_ma = sum(values[-self.fast:]) / self.fast
        slow_ma = sum(values) / self.slow
        cur_above = fast_ma > slow_ma
        prev_above = self._prev_above.get(bar.symbol)
        self._prev_above[bar.symbol] = cur_above
        if prev_above is None:
            return None

        held = context.position_qty(bar.symbol)
        if cur_above and not prev_above and held == 0:
            return Signal(bar.symbol, "BUY", self.qty)
        if not cur_above and prev_above and held > 0:
            return Signal(bar.symbol, "SELL", held)
        return None
