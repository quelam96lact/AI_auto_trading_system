from dataclasses import dataclass
from typing import Literal, Protocol

from trading.models import Bar

Side = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: Side
    qty: int


class Context(Protocol):
    def position_qty(self, symbol: str) -> int: ...


class Strategy(Protocol):
    def on_bar(self, bar: Bar, context: Context) -> Signal | None: ...
