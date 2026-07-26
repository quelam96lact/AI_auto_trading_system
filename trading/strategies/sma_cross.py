from collections import deque
from typing import Literal

from trading.models import Bar
from trading.strategy import Context, Signal

Crossover = Literal["bull", "bear"]


class SmaCrossStrategy:
    def __init__(self, fast: int = 10, slow: int = 20, qty: int = 100):
        self.fast = fast
        self.slow = slow
        self.qty = qty
        self._closes: dict[str, deque] = {}
        self._prev_above: dict[str, bool | None] = {}
        self._last_crossover: dict[str, Crossover | None] = {}

    def compute_crossover(self, bar: Bar) -> Crossover | None:
        """Cập nhật state MA (CHỈ được gọi đúng 1 lần/bar/symbol — có side-effect
        mutate state nội bộ), trả về loại crossover vừa xảy ra (nếu có).

        KHÔNG áp bất kỳ logic vị thế nào ở đây — tách biệt "phát hiện crossover"
        (thuần kỹ thuật, dựa vào MA) khỏi "quyết định dựa trên vị thế" (paper hay
        thật), để real_orders.handle_crossover() có thể tự quyết định độc lập với
        PaperBroker.
        """
        closes = self._closes.setdefault(bar.symbol, deque(maxlen=self.slow))
        closes.append(bar.close)
        if len(closes) < self.slow:
            self._last_crossover[bar.symbol] = None
            return None

        values = list(closes)
        fast_ma = sum(values[-self.fast:]) / self.fast
        slow_ma = sum(values) / self.slow
        cur_above = fast_ma > slow_ma
        prev_above = self._prev_above.get(bar.symbol)
        self._prev_above[bar.symbol] = cur_above
        if prev_above is None:
            self._last_crossover[bar.symbol] = None
            return None

        crossover: Crossover | None = None
        if cur_above and not prev_above:
            crossover = "bull"
        elif not cur_above and prev_above:
            crossover = "bear"
        self._last_crossover[bar.symbol] = crossover
        return crossover

    def last_crossover(self, symbol: str) -> Crossover | None:
        """Crossover vừa tính ở lần compute_crossover() gần nhất cho symbol này."""
        return self._last_crossover.get(symbol)

    def on_bar(self, bar: Bar, context: Context) -> Signal | None:
        crossover = self.compute_crossover(bar)
        held = context.position_qty(bar.symbol)
        if crossover == "bull" and held == 0:
            return Signal(bar.symbol, "BUY", self.qty)
        if crossover == "bear" and held > 0:
            return Signal(bar.symbol, "SELL", held)
        return None


# Re-export for type-safe callers.
__all__ = ["Crossover", "SmaCrossStrategy"]
