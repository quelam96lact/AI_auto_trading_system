import argparse
import asyncio
import queue
from datetime import datetime, timedelta

from trading.alerts import alert
from trading.bus.publisher import BarPublisher
from trading.calendar_vn import TZ, is_trading_time, session_end_after
from trading.collector.aggregator import BarAggregator
from trading.collector.backfill import SSIRestClient, run_backfill
from trading.collector.feed import SSIFeed
from trading.collector.parser import parse_message
from trading.collector.watchdog import Watchdog
from trading.config import load_config
from trading.models import IndexValue, Tick
from trading.storage.db import Storage

EOD_HOUR, EOD_MINUTE = 15, 5  # job vá gap cuối ngày


async def run(cfg) -> None:
    storage = Storage(cfg.db_dsn)
    storage.init_schema()
    pub = BarPublisher(cfg.nats_url, cfg.nats_stream)
    await pub.connect()

    alert("INFO", "backfill start")
    client = SSIRestClient(cfg, storage)
    try:
        counts = await run_backfill(storage, client, cfg.symbols, datetime.now(TZ).date())
        alert("INFO", "backfill done", counts=counts)
    except Exception as e:
        alert("WARN", "backfill failed, skipping", error=str(e)[:100])
        counts = {}
    finally:
        await client.close()

    agg = BarAggregator(cfg.bar_interval_minutes, cfg.holidays)
    raw_q: queue.Queue = queue.Queue()
    feed = SSIFeed(cfg, on_raw=raw_q.put)
    feed.start()

    wd = Watchdog(
        cfg.watchdog_stale_seconds,
        cfg.watchdog_max_failures,
        now_fn=lambda: datetime.now(TZ),
        is_trading_fn=lambda ts: is_trading_time(ts, cfg.holidays),
        on_stale=lambda: alert("WARN", "feed stale, forcing reconnect"),
        on_critical=lambda: alert("CRITICAL", "feed stale beyond max failures"),
    )

    async def persist(bars):
        if bars:
            storage.write_bars(bars)
            for b in bars:
                await pub.publish(b)
            alert("INFO", "bars closed", n=len(bars), symbols=[b.symbol for b in bars])

    async def consume():
        loop = asyncio.get_running_loop()
        while True:
            raw = await loop.run_in_executor(None, raw_q.get)
            wd.beat()
            msg = parse_message(raw)
            if isinstance(msg, Tick):
                await persist(agg.add_tick(msg))
            elif isinstance(msg, IndexValue):
                storage.write_index_values([msg])

    async def housekeeping():
        eod_done_for: object = None
        while True:
            await asyncio.sleep(30)
            wd.check()
            storage.beat("collector")
            now = datetime.now(TZ)
            end = session_end_after(now)
            if end is not None and now >= end - timedelta(seconds=1):
                await persist(
                    agg.flush()
                )  # đóng bar cuối phiên (không còn tick đẩy nó đóng)
            if (now.hour, now.minute) >= (
                EOD_HOUR,
                EOD_MINUTE,
            ) and eod_done_for != now.date():
                eod_done_for = now.date()
                eod_client = SSIRestClient(cfg, storage)
                try:
                    counts = await run_backfill(storage, eod_client, cfg.symbols, now.date())
                    alert("INFO", "eod backfill done", counts=counts)
                finally:
                    await eod_client.close()

    await asyncio.gather(consume(), housekeeping())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run(load_config(args.config)))


if __name__ == "__main__":
    main()
