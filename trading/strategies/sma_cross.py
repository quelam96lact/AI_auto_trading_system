from collections import deque
from typing import Literal

from trading.indicators import AtrCalculator
from trading.models import Bar
from trading.strategy import Context, Signal

Crossover = Literal["bull", "bear"]


class SmaCrossStrategy:
    def __init__(
        self,
        fast: int = 10,
        slow: int = 20,
        qty: int = 100,
        atr_period: int = 14,
        atr_pct_threshold: float = 0.005,
    ):
        self.fast = fast
        self.slow = slow
        self.qty = qty
        self.atr_pct_threshold = atr_pct_threshold
        self._closes: dict[str, deque] = {}
        self._prev_above: dict[str, bool | None] = {}
        self._last_crossover: dict[str, Crossover | None] = {}
        self._last_atr: dict[str, float | None] = {}
        self._atr = AtrCalculator(period=atr_period)

    def compute_crossover(self, bar: Bar) -> Crossover | None:
        """Cập nhật state MA (CHỈ được gọi đúng 1 lần/bar/symbol — có side-effect
        mutate state nội bộ), trả về loại crossover vừa xảy ra (nếu có).

        KHÔNG áp bất kỳ logic vị thế nào ở đây — tách biệt "phát hiện crossover"
        (thuần kỹ thuật, dựa vào MA + ATR) khỏi "quyết định dựa trên vị thế" (paper
        hay thật), để real_orders.handle_crossover() có thể tự quyết định độc lập
        với PaperBroker.

        Lọc theo ATR%: crossover bị ép về None (cả bull lẫn bear) nếu ATR chưa đủ
        dữ liệu (warm-up), close<=0 (bar dị dạng, không tính được tỷ lệ % hợp lệ —
        chặn an toàn thay vì crash chia cho 0), hoặc atr/close < atr_pct_threshold
        — tránh trade lúc thị trường đi ngang. atr.update() luôn gọi mỗi bar, kể cả
        lúc MA đang warm-up, để state ATR tích lũy độc lập với MA.
        """
        atr = self._atr.update(bar)
        self._last_atr[bar.symbol] = atr

        closes = self._closes.setdefault(bar.symbol, deque(maxlen=self.slow))
        closes.append(bar.close)
        if len(closes) < self.slow:
            self._last_crossover[bar.symbol] = None
            return None

        values = list(closes)
        fast_ma = sum(values[-self.fast :]) / self.fast
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

        if crossover is not None and (
            atr is None or bar.close <= 0 or atr / bar.close < self.atr_pct_threshold
        ):
            crossover = None

        self._last_crossover[bar.symbol] = crossover
        return crossover

    def last_crossover(self, symbol: str) -> Crossover | None:
        """Crossover vừa tính ở lần compute_crossover() gần nhất cho symbol này."""
        return self._last_crossover.get(symbol)

    def last_atr(self, symbol: str) -> float | None:
        """ATR vừa tính ở lần compute_crossover() gần nhất cho symbol này."""
        return self._last_atr.get(symbol)

    def on_bar(self, bar: Bar, context: Context) -> Signal | None:
        crossover = self.compute_crossover(bar)
        held = context.position_qty(bar.symbol)
        if crossover == "bull" and held == 0:
            return Signal(bar.symbol, "BUY", self.qty)
        if crossover == "bear" and held > 0:
            return Signal(bar.symbol, "SELL", held)
        return None

    @property
    def warmup_bars(self) -> int:
        """So bar toi thieu de MA va ATR san sang: du slow close cho MA + du
        atr_period cho ATR, cong 1 bar nua de _prev_above thoat khoi None (lan
        dau du slow bar van tra None vi prev_above is None — xem
        compute_crossover). WARM-1 rui ro 5: so bar nap luc engine khoi dong
        phai do CHINH CHIEN LUOC quyet, khong hardcode o main.py — ai do doi
        atr_period=30 ma main van nap 21 bar thi ATR khong bao gio san sang,
        hong im lang."""
        return max(self.slow, self._atr.period) + 1


# Re-export for type-safe callers.
__all__ = ["Crossover", "SmaCrossStrategy"]
