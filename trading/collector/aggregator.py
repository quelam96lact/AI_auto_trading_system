from dataclasses import dataclass
from datetime import date, datetime, timedelta

from trading.calendar_vn import is_trading_time
from trading.models import Bar, Tick


@dataclass
class _OpenBar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class BarAggregator:
    def __init__(self, interval_min: int, holidays: set[date]):
        self.interval = timedelta(minutes=interval_min)
        self.holidays = holidays
        self._open: dict[str, _OpenBar] = {}

    def _bucket(self, ts: datetime) -> datetime:
        minute = (ts.minute // (self.interval.seconds // 60)) * (self.interval.seconds // 60)
        return ts.replace(minute=minute, second=0, microsecond=0)

    def add_tick(self, t: Tick) -> list[Bar]:
        if not is_trading_time(t.ts, self.holidays):
            return []
        bucket = self._bucket(t.ts)
        closed: list[Bar] = []
        cur = self._open.get(t.symbol)
        if cur is not None and bucket > cur.ts:
            closed.append(self._freeze(t.symbol, cur))
            cur = None
        if cur is None:
            self._open[t.symbol] = _OpenBar(bucket, t.price, t.price, t.price, t.price, t.volume)
        else:
            cur.high = max(cur.high, t.price)
            cur.low = min(cur.low, t.price)
            cur.close = t.price
            cur.volume += t.volume
        return closed

    def flush(self) -> list[Bar]:
        bars = [self._freeze(sym, ob) for sym, ob in self._open.items()]
        self._open.clear()
        return bars

    @staticmethod
    def _freeze(symbol: str, ob: _OpenBar) -> Bar:
        return Bar(symbol, ob.ts, ob.open, ob.high, ob.low, ob.close, ob.volume)