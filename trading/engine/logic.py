from datetime import datetime
from typing import Callable

from trading.broker import Fill
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.strategies.sma_cross import Crossover, SmaCrossStrategy


def process_bar(
    bar: Bar,
    broker: PaperBroker,
    strategy: SmaCrossStrategy,
    risk: RiskManager,
    marks: dict[str, float],
    on_crossover: Callable[[Crossover, Bar], None] | None = None,
) -> list[Fill]:
    fills = broker.on_bar(bar)
    marks[bar.symbol] = bar.close

    signal = strategy.on_bar(bar, broker)
    crossover = strategy.last_crossover(bar.symbol)
    if on_crossover is not None and crossover is not None:
        on_crossover(crossover, bar)

    if signal is not None:
        daily_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)
        if risk.approve(signal, bar.close, broker.positions, daily_pnl, bar.ts.date()):
            broker.submit(signal)

    return fills


def bar_from_payload(data: dict) -> Bar:
    return Bar(
        symbol=data["symbol"],
        ts=datetime.fromisoformat(data["ts"]).astimezone(TZ),
        open=data["open"],
        high=data["high"],
        low=data["low"],
        close=data["close"],
        volume=data["volume"],
        source=data.get("source", "ssi"),
    )
