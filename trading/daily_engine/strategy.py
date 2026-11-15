"""Daily strategy protocol, context, and strategy registry (Brief 233 §4)."""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from trading.daily_engine.core import LOT, DailyBar


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
        next_trading_day: date | None = None,
    ) -> None:
        self.d = d
        self.universe = universe
        self.cash = cash
        self.nav = nav
        self.positions = positions
        self._bars_loader = bars_loader
        self.next_trading_day = next_trading_day

    def bars(self, symbol: str, n: int) -> list[DailyBar]:
        """Return up to `n` most recent daily bars for `symbol` with date <= ctx.d in chronological order."""
        if n <= 0 or self._bars_loader is None:
            return []
        return self._bars_loader(symbol, n)


class DailyStrategy(Protocol):
    name: str
    cash_rate: float

    def on_day(self, ctx: DailyContext) -> list[OrderIntent]: ...


class NullDailyStrategy:
    name: str = "null"
    cash_rate: float = 0.0

    def on_day(self, ctx: DailyContext) -> list[OrderIntent]:
        return []


class EtfDepositStrategy:
    """15% E1VFVN30 + cash deposit at 6%/year, rebalanced annually (Brief 239 §3).

    Deliberate differences vs Brief 165 simulation (`scripts/measure_etf_deposit_mix.py`):
    - Order quantities are floored to lots of 100 shares (Brief 165 uses fractional shares).
    - Initial buy quantity divides by the decision day's close price and fills at next open
      (with engine slippage/fees).
    - If an order expires due to missing bar on execution day (`no_bar`), the initial buy
      automatically re-submits on the next valid session while `pos == 0`, whereas a missed
      annual rebalance is skipped for that year.
    """

    name: str = "etf_deposit"
    ETF_SYMBOL: str = "E1VFVN30"
    ETF_WEIGHT: float = 0.15
    cash_rate: float = 0.06

    def on_day(self, ctx: DailyContext) -> list[OrderIntent]:
        bars = ctx.bars(self.ETF_SYMBOL, 1)
        if not bars:
            return []
        bar = bars[-1]
        if bar.date != ctx.d or bar.close <= 0.0:
            return []

        target = math.floor(self.ETF_WEIGHT * ctx.nav / bar.close / LOT) * LOT
        pos = ctx.positions.get(self.ETF_SYMBOL, 0)

        if pos == 0:
            if target > 0:
                return [OrderIntent(symbol=self.ETF_SYMBOL, side="BUY", qty=target)]
            return []

        if (
            pos > 0
            and ctx.next_trading_day is not None
            and ctx.next_trading_day.year > ctx.d.year
        ):
            diff = target - pos
            if diff >= LOT:
                return [OrderIntent(symbol=self.ETF_SYMBOL, side="BUY", qty=diff)]
            if diff <= -LOT:
                return [OrderIntent(symbol=self.ETF_SYMBOL, side="SELL", qty=-diff)]
        return []


STRATEGIES: dict[str, type[DailyStrategy]] = {
    "null": NullDailyStrategy,
    "etf_deposit": EtfDepositStrategy,
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
