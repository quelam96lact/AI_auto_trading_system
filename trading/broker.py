from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from trading.models import Bar
from trading.strategy import Signal


@dataclass(frozen=True)
class Fill:
    symbol: str
    side: str
    qty: int
    price: float
    fee: float
    ts: datetime
    pnl: float | None = None


@dataclass
class Position:
    symbol: str
    qty: int = 0
    avg_price: float = 0.0


class Broker(Protocol):
    def submit(self, signal: Signal) -> None: ...
    def on_bar(self, bar: Bar) -> list[Fill]: ...
    def position_qty(self, symbol: str) -> int: ...
