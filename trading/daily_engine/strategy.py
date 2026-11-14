"""Daily strategy protocol, context, and strategy registry (Brief 233 §4)."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from trading.daily_engine.core import DailyBar


@dataclass(frozen=True, slots=True)
class OrderIntent:
    symbol: str
    side: str
    qty: int


class DailyContext:
    def __init__(
        self,
        d: date,
        universe: list[str],
        cash: float,
        nav: float,
        positions: dict[str, int],
        bars_loader: Callable[[str, int], list[DailyBar]] | None = None,
    ) -> None:
        self.d = d
        self.universe = universe
        self.cash = cash
        self.nav = nav
        self.positions = positions
        self._bars_loader = bars_loader

    def bars(self, symbol: str, n: int) -> list[DailyBar]:
        """Return up to `n` most recent daily bars for `symbol` with date <= ctx.d in chronological order."""
        if n <= 0 or self._bars_loader is None:
            return []
        return self._bars_loader(symbol, n)


class DailyStrategy(Protocol):
    name: str

    def on_day(self, ctx: DailyContext) -> list[OrderIntent]: ...


class NullDailyStrategy:
    name: str = "null"

    def on_day(self, ctx: DailyContext) -> list[OrderIntent]:
        return []


STRATEGIES: dict[str, type[DailyStrategy]] = {
    "null": NullDailyStrategy,
}


class UnknownStrategyError(ValueError):
    """Raised when DAILY_ENGINE_STRATEGY names an unregistered strategy."""


def resolve_strategy(name: str | None = None) -> DailyStrategy:
    """Resolve strategy instance from explicit name or DAILY_ENGINE_STRATEGY env var."""
    raw = os.environ.get("DAILY_ENGINE_STRATEGY", "") if name is None else name
    key = raw.strip().lower() or "null"
    cls = STRATEGIES.get(key)
    if cls is None:
        available = ", ".join(sorted(STRATEGIES))
        raise UnknownStrategyError(f"Unknown DAILY_ENGINE_STRATEGY: {key!r} (available: {available})")
    return cls()
