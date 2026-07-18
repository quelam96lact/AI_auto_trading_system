from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Tick:
    symbol: str
    price: float
    volume: int  # khối lượng khớp của riêng tick này
    ts: datetime


@dataclass(frozen=True)
class Bar:
    symbol: str
    ts: datetime  # thời điểm MỞ bar
    open: float
    high: float
    low: float
    close: float
    volume: int
    source: str = "ssi"


@dataclass(frozen=True)
class IndexValue:
    index_id: str
    ts: datetime
    value: float