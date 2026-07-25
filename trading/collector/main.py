import argparse
import asyncio
from datetime import datetime, timedelta

from trading.alerts import alert
from trading.bus.publisher import BarPublisher
from trading.calendar_vn import TZ, is_trading_time
from trading.collector.account_sync import sync_account_data
from trading.collector.backfill import SSIRestClient, run_backfill
from trading.collector.feed import SSIFeed
from trading.collector.parser import parse_interval_message
from trading.collector.watchdog import Watchdog
from trading.config import load_config
from trading.storage.db import Storage

EOD_HOUR, EOD_MINUTE = 15, 5  # EOD gap repair job


async def run(cfg) -> None:
    storage = Storage(cfg.db_dsn)
    storage.init_schema()
    pub = BarPublisher(cfg.nats_url, cfg.nats_stream)
    await pub.connect()

    alert("INFO", "backfill start")
    client = SSIRestClient(cfg, storage)
    try:
        counts = await run_backfill(
            storage, client, cfg.symbols, datetime.now(TZ).date()
        )
        alert("INFO", "backfill done", counts=counts)
    except Exception as e:
        alert("WARN", "backfill failed, skipping", error=str(e)[:100])
        counts = {}
    finally:
        await client.close()

    async def persist(bars):
        if bars:
            storage.write_bars(bars)
            for b in bars:
                await pub.publish(b)
            alert("INFO", "bars closed", n=len(bars), symbols=[b.symbol for b in bars])

    def _on_stale():
        alert("WARN", "feed stale, forcing reconnect")
        asyncio.create_task(feed.restart())

    wd = Watchdog(
        cfg.watchdog_stale_seconds,
        cfg.watchdog_max_failures,
        now_fn=lambda: datetime.now(TZ),
        is_trading_fn=lambda ts: is_trading_time(ts, cfg.holidays),
        on_stale=_on_stale,
        on_critical=lambda: alert("CRITICAL", "feed stale beyond max failures"),
    )

    def on_stream_message(msg):
        bar = parse_interval_message(msg)
        if bar is not None:
            wd.beat()
            asyncio.create_task(persist([bar]))
        # TODO index streaming: if TradeMessage is proven valid for indices,
        # handle it separately here and write IndexValue rows.

    feed = SSIFeed(cfg, storage, on_message=on_stream_message)
    feed.start()

    async def housekeeping():
        eod_done_for: object = None
        last_account_sync: datetime | None = None
        while True:
            await asyncio.sleep(30)
            wd.check()
            storage.beat("collector")
            now = datetime.now(TZ)
            if last_account_sync is None or now - last_account_sync >= timedelta(
                minutes=5
            ):
                last_account_sync = now
                try:
                    await sync_account_data(cfg, storage)
                except Exception as e:
                    alert("WARN", "account sync failed, skipping", error=str(e)[:100])
            if (now.hour, now.minute) >= (
                EOD_HOUR,
                EOD_MINUTE,
            ) and eod_done_for != now.date():
                eod_done_for = now.date()
                eod_client = SSIRestClient(cfg, storage)
                try:
                    counts = await run_backfill(
                        storage, eod_client, cfg.symbols, now.date()
                    )
                    alert("INFO", "eod backfill done", counts=counts)
                finally:
                    await eod_client.close()

    await housekeeping()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run(load_config(args.config)))


if __name__ == "__main__":
    main()
