"""Chiến lược breakout khung ngày (Dự án con 2, spec 2026-08-15).

Tín hiệu (THUẦN giá đóng cửa so với cửa sổ các phiên TRƯỚC):
- "bull": close vượt đỉnh cao nhất N=20 phiên gần nhất, KHÔNG tính bar hiện tại.
- "bear": close thủng đáy thấp nhất M=10 phiên gần nhất, KHÔNG tính bar hiện tại.
- N=20, M=10 chốt TRƯỚC khi đo, không tinh chỉnh trong lần đo đầu.
- Chưa đủ lịch sử (warmup) -> None, không đoán.

State theo từng symbol (giống SmaCrossStrategy). Kèm ATR tracker vì
run_backtest gọi strategy.last_atr() cho TrailingStopManager lẫn
RiskManager.approve_sized — thiếu ATR thì mọi BUY bị từ chối im lặng.
Tín hiệu breakout vẫn thuần close-vs-window; ATR chỉ nuôi risk/trailing.

warmup_bars = max(N, M) + 1: cần max(N,M) phiên TRƯỚC bar hiện tại để có cửa
sổ đầy đủ, cộng bar hiện tại. Cửa sổ được đánh giá TRƯỚC khi append bar hiện
tại vào deque (bar hiện tại không bao giờ nằm trong cửa sổ của chính nó).
"""

from collections import deque
from typing import Literal

from trading.indicators import AtrCalculator
from trading.models import Bar
from trading.strategy import Context, Signal

Crossover = Literal["bull", "bear"]


class DailyBreakoutStrategy:
    def __init__(
        self,
        n: int = 20,
        m: int = 10,
        qty: int = 100,
        atr_period: int = 14,
    ):
        self.n = n
        self.m = m
        self.qty = qty
        self._highs: dict[str, deque] = {}
        self._lows: dict[str, deque] = {}
        self._last_crossover: dict[str, Crossover | None] = {}
        self._last_atr: dict[str, float | None] = {}
        self._atr = AtrCalculator(period=atr_period)

    def compute_crossover(self, bar: Bar) -> Crossover | None:
        """Cập nhật state (CHỈ được gọi đúng 1 lần/bar/symbol — có side-effect
        mutate state nội bộ), trả về tín hiệu breakout của bar này (nếu có).

        So sánh close với cửa sổ các phiên TRƯỚC bar hiện tại:
        - len(highs) >= n thì đỉnh cửa sổ = max(highs) — bar hiện tại chưa
          được append nên không bao giờ tự tính vào cửa sổ của chính nó.
        - Tương tự cho đáy với lows (m phiên).
        - bull/bear loại trừ nhau (m-low <= n-high), ưu tiên bull.
        """
        atr = self._atr.update(bar)
        self._last_atr[bar.symbol] = atr

        highs = self._highs.setdefault(bar.symbol, deque(maxlen=self.n))
        lows = self._lows.setdefault(bar.symbol, deque(maxlen=self.m))

        crossover: Crossover | None = None
        if len(highs) >= self.n and bar.close > max(highs):
            crossover = "bull"
        elif len(lows) >= self.m and bar.close < min(lows):
            crossover = "bear"

        highs.append(bar.high)
        lows.append(bar.low)
        self._last_crossover[bar.symbol] = crossover
        return crossover

    def last_crossover(self, symbol: str) -> Crossover | None:
        """Tín hiệu vừa tính ở lần compute_crossover() gần nhất cho symbol này."""
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
        """So bar toi thieu de san sang: max(N, M) phien TRUOC bar hien tai
        + 1 bar hien tai (xem docstring lop)."""
        return max(self.n, self.m) + 1


# Re-export for type-safe callers.
__all__ = ["Crossover", "DailyBreakoutStrategy"]
