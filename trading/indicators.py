from collections import deque

from trading.models import Bar


class AtrCalculator:
    """Average True Range, per-symbol state (mirrors SmaCrossStrategy's own
    per-symbol MA state). Simple moving average of True Range, not Wilder's
    smoothing - consistent with SmaCrossStrategy's simple-average MAs."""

    def __init__(self, period: int = 14):
        self.period = period
        self._tr: dict[str, deque] = {}
        self._prev_close: dict[str, float | None] = {}

    def update(self, bar: Bar) -> float | None:
        prev_close = self._prev_close.get(bar.symbol)
        if prev_close is None:
            tr = bar.high - bar.low
        else:
            tr = max(
                bar.high - bar.low,
                abs(bar.high - prev_close),
                abs(bar.low - prev_close),
            )
        self._prev_close[bar.symbol] = bar.close

        window = self._tr.setdefault(bar.symbol, deque(maxlen=self.period))
        window.append(tr)
        if len(window) < self.period:
            return None
        return sum(window) / self.period
