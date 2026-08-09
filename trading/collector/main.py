import argparse
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from trading.alerts import alert
from trading.bus.publisher import BarPublisher
from trading.calendar_vn import TZ, is_trading_time
from trading.collector.account_sync import sync_account_data
from trading.collector.backfill import SSIRestClient, run_backfill
from trading.collector.derivative_sync import sync_derivative_data
from trading.collector.feed import SSIFeed
from trading.collector.parser import parse_interval_message
from trading.collector.watchdog import Watchdog
from trading.config import load_config
from trading.storage.db import Storage

EOD_HOUR, EOD_MINUTE = 15, 5  # EOD gap repair job


async def persist_bars(storage, pub, bars) -> None:
    """Ghi bar vào DB + publish NATS. KHÔNG BAO GIỜ ném: hàm này được gọi qua
    asyncio.create_task() fire-and-forget, exception thoát ra sẽ bị asyncio nuốt
    thành 'Task exception was never retrieved' — bar mất mà không ai biết."""
    if not bars:
        return
    try:
        storage.write_bars(bars)
        for b in bars:
            await pub.publish(b)
        alert("INFO", "bars closed", n=len(bars), symbols=[b.symbol for b in bars])
    except Exception as e:
        alert(
            "CRITICAL",
            "bar persist/publish failed, bars dropped",
            error=f"{type(e).__name__}: {e}"[:200],
            symbols=[b.symbol for b in bars],
            ts=[b.ts.isoformat() for b in bars],
        )


def make_stream_message_handler(wd, storage, pub):
    """Callback cho AsyncStream.streaming.on_data. Một message dị dạng không
    được ném ngược vào vòng stream của SDK."""

    def on_stream_message(msg):
        try:
            bar = parse_interval_message(msg)
        except Exception as e:
            alert(
                "WARN",
                "failed to parse stream message, skipping",
                error=f"{type(e).__name__}: {e}"[:200],
            )
            return
        if bar is not None:
            wd.beat()
            asyncio.create_task(persist_bars(storage, pub, [bar]))
        # Index streaming (VNINDEX/VN30): không có nguồn dữ liệu real-time nào
        # trong ssi-sdk hiện tại — xem PLAN_INDEX_STREAMING.md (điều tra thật
        # 2026-08-07). Không viết IndexValue cho tới khi có nguồn dữ liệu khác.

    return on_stream_message


@dataclass
class HousekeepingState:
    eod_done_for: date | None = None
    last_account_sync: datetime | None = None


async def housekeeping_tick(cfg, storage, wd, state: HousekeepingState) -> None:
    """Một vòng housekeeping. Được phép ném — housekeeping_loop chịu trách nhiệm bắt."""
    wd.check()
    storage.beat("collector")
    now = datetime.now(TZ)
    if state.last_account_sync is None or now - state.last_account_sync >= timedelta(
        minutes=5
    ):
        state.last_account_sync = now
        try:
            await sync_account_data(cfg, storage)
        except Exception as e:
            alert("WARN", "account sync failed, skipping", error=str(e)[:100])
        try:
            await sync_derivative_data(cfg, storage)
        except Exception as e:
            alert("WARN", "derivative sync failed, skipping", error=str(e)[:100])
    if (now.hour, now.minute) >= (
        EOD_HOUR,
        EOD_MINUTE,
    ) and state.eod_done_for != now.date():
        state.eod_done_for = now.date()
        eod_client = SSIRestClient(cfg, storage)
        try:
            counts = await run_backfill(storage, eod_client, cfg.symbols, now.date())
            alert("INFO", "eod backfill done", counts=counts)
        finally:
            await eod_client.close()


async def housekeeping_loop(
    cfg,
    storage,
    wd,
    sleep_seconds: float = 30.0,
    max_ticks: int | None = None,
) -> None:
    """Vòng housekeeping vô hạn. Một lỗi (vd Postgres restart) KHÔNG được giết
    collector — bắt hết, alert WARN, rồi chạy tiếp vòng sau.
    `max_ticks` chỉ dùng cho test, cùng pattern với run(max_messages) của engine."""
    state = HousekeepingState()
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        await asyncio.sleep(sleep_seconds)
        try:
            await housekeeping_tick(cfg, storage, wd, state)
        except Exception as e:
            alert(
                "WARN",
                "housekeeping tick failed, continuing",
                error=f"{type(e).__name__}: {e}"[:200],
            )
        ticks += 1


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

    feed = SSIFeed(
        cfg, storage, on_message=make_stream_message_handler(wd, storage, pub)
    )
    feed.start()

    await housekeeping_loop(cfg, storage, wd)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run(load_config(args.config)))


if __name__ == "__main__":
    main()
