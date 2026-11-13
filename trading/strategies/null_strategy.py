from __future__ import annotations

from trading.models import Bar
from trading.strategy import Context, Crossover, Signal


class NullStrategy:
    """No-op strategy used when ENGINE_STRATEGY_DISABLED=1."""

    @property
    def warmup_bars(self) -> int:
        # Phải >= 1 để slice history[-(warmup - 1):] trong engine không phát lại
        # toàn bộ lịch sử khi warmup - 1 == 0.
        return 1

    def on_bar(self, bar: Bar, context: Context) -> Signal | None:
        return None

    def compute_crossover(self, bar: Bar) -> Crossover | None:
        return None

    def last_crossover(self, symbol: str) -> Crossover | None:
        return None

    def last_atr(self, symbol: str) -> float | None:
        return None
