import argparse
import asyncio
import json
import logging

import nats
from nats.js.api import ConsumerConfig, DeliverPolicy

from trading.alerts import alert
from trading.calendar_vn import TZ
from trading.config import Config, load_config
from trading.engine.logic import bar_from_payload, process_bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.strategies.sma_cross import SmaCrossStrategy

CAPITAL = 100_000_000.0


async def run(cfg: Config, max_messages: int | None = None) -> None:
    storage = Storage(cfg.db_dsn)
    storage.init_schema()

    state = storage.read_engine_state()
    positions = storage.read_positions()
    if state is None:
        broker = PaperBroker(CAPITAL)
        alert("INFO", "engine starting fresh", capital=CAPITAL)
    else:
        cash, realized_pnl = state
        broker = PaperBroker.restore(CAPITAL, cash, realized_pnl, positions)
        alert(
            "INFO",
            "engine restored state",
            cash=cash,
            realized_pnl=realized_pnl,
            positions={s: p.qty for s, p in positions.items()},
        )

    strategy = SmaCrossStrategy()
    risk = RiskManager(capital=CAPITAL)
    marks: dict[str, float] = {}

    nc = await nats.connect(cfg.nats_url)
    js = nc.jetstream()
    sub = await js.subscribe(
        "bars.>",
        durable="engine",
        stream=cfg.nats_stream,
        config=ConsumerConfig(deliver_policy=DeliverPolicy.ALL),
    )

    def persist_fills(fills) -> None:
        for fill in fills:
            storage.upsert_position(broker.positions[fill.symbol])
            storage.write_engine_state(broker.cash, broker.realized_pnl)
            storage.write_order(fill)
            storage.update_pnl_daily(
                fill.ts.astimezone(TZ).date(),
                fill.pnl or 0.0,
                fill.fee,
                broker.unrealized_pnl(marks),
            )
            alert(
                "INFO",
                "order filled",
                symbol=fill.symbol,
                side=fill.side,
                qty=fill.qty,
                price=fill.price,
                pnl=fill.pnl,
            )

    processed = 0
    try:
        while max_messages is None or processed < max_messages:
            try:
                msg = await sub.next_msg(timeout=60)
            except nats.errors.TimeoutError:
                storage.beat("engine")
                continue
            bar = bar_from_payload(json.loads(msg.data))
            fills = process_bar(bar, broker, strategy, risk, marks)
            persist_fills(fills)
            await msg.ack()
            storage.beat("engine")
            processed += 1
    finally:
        await nc.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run(load_config(args.config)))


if __name__ == "__main__":
    main()
