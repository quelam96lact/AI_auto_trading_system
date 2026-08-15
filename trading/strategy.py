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
    """Hop dong ma CA engine (engine/logic.py) LAN backtest deu goi toi.

    `last_crossover` / `last_atr` khong phai phan phu: logic.py:44,50,72 va
    backtest.py:91,95,107 deu dua vao chung de chay trailing stop va sizing.
    """

    def on_bar(self, bar: Bar, context: Context) -> Signal | None: ...

    def last_crossover(self, symbol: str) -> str | None: ...

    def last_atr(self, symbol: str) -> float | None: ...
