from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from trading.models import Bar

Side = Literal["BUY", "SELL"]

# Kieu crossover ma cac strategy dung (moi file strategy tu khai Crossover =
# Literal["bull","bear"] — mot cong thuc mot noi: khai o day lam nguon chuan
# cho Protocol, khong ep cac strategy import vao day).
Crossover = Literal["bull", "bear"]


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: Side
    qty: int


class Context(Protocol):
    def position_qty(self, symbol: str) -> int: ...


@runtime_checkable
class Strategy(Protocol):
    """Hop dong ma CA engine (engine/main.py + engine/logic.py) LAN backtest
    deu goi toi.

    Engine goi NAM thuoc tinh, khong phai ba (brief 04/09 goi B1):
      main.py:81,86  -> warmup_bars        (so bar nap lich su luc khoi dong)
      main.py:91     -> compute_crossover  (nap state ky thuat, khong sinh lenh)
      logic.py:43    -> on_bar
      logic.py:44    -> last_crossover     (goi KHONG dieu kien — thieu la chet)
      logic.py:50    -> last_atr

    `last_crossover` / `last_atr` khong phai phan phu: logic.py:44,50,72 va
    backtest.py:91,95,107 deu dua vao chung de chay trailing stop va sizing.
    """

    def on_bar(self, bar: Bar, context: Context) -> Signal | None: ...

    def last_crossover(self, symbol: str) -> Crossover | None: ...

    def last_atr(self, symbol: str) -> float | None: ...

    # PROPERTY, khong phai method: main.py:81,82,86 doc `strategy.warmup_bars`
    # khong ngoac, va ca ba strategy that deu @property. Khai o day thanh method
    # se khien mot strategy viet DUNG THEO CHU cua Protocol chet o main.py:82
    # ("'<' not supported between instances of 'int' and 'method'").
    @property
    def warmup_bars(self) -> int: ...

    def compute_crossover(self, bar: Bar) -> Crossover | None: ...
