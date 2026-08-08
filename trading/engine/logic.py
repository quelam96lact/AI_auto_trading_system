from collections.abc import Callable
from datetime import datetime

from trading.broker import Fill
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.strategies.sma_cross import Crossover, SmaCrossStrategy
from trading.trailing_stop import TrailingStopManager


def process_bar(
    bar: Bar,
    broker: PaperBroker,
    strategy: SmaCrossStrategy,
    risk: RiskManager,
    trailing_stop: TrailingStopManager,
    marks: dict[str, float],
    on_crossover: Callable[[Crossover, Bar], None] | None = None,
) -> list[Fill]:
    fills = broker.on_bar(bar)
    marks[bar.symbol] = bar.close
    for f in fills:
        if f.side == "BUY":
            trailing_stop.on_position_opened(f.symbol, f.price)
        else:
            trailing_stop.on_position_closed(f.symbol)

    signal = strategy.on_bar(bar, broker)
    crossover = strategy.last_crossover(bar.symbol)
    if on_crossover is not None and crossover is not None:
        on_crossover(crossover, bar)

    stop_price = None
    if broker.position_qty(bar.symbol) > 0:
        stop_price = trailing_stop.check(bar, strategy.last_atr(bar.symbol))

    if stop_price is not None:
        forced = broker.force_exit(bar.symbol, stop_price, bar.ts)
        trailing_stop.on_position_closed(bar.symbol)
        fills.append(forced)
    elif signal is not None:
        daily_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)
        sized = risk.approve_sized(
            signal,
            bar.close,
            strategy.last_atr(bar.symbol),
            broker.positions,
            daily_pnl,
            bar.ts.date(),
        )
        if sized is not None:
            broker.submit(sized)

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
