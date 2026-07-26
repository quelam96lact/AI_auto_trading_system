from datetime import datetime
from typing import Callable

from trading.broker import Fill
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.strategy import Signal, Strategy


def process_bar(
    bar: Bar,
    broker: PaperBroker,
    strategy: Strategy,
    risk: RiskManager,
    marks: dict[str, float],
    on_signal: Callable[[Signal, Bar], None] | None = None,
) -> list[Fill]:
    fills = broker.on_bar(bar)
    marks[bar.symbol] = bar.close

    signal = strategy.on_bar(bar, broker)
    if signal is not None:
        if on_signal is not None:
            on_signal(signal, bar)
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
