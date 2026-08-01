"""One-off long-range historical backfill for backtest/strategy prep.

The regular collector service (trading/collector/backfill.py::run_backfill)
only ever fetches a 7-day gap for a symbol with no prior bars - enough for
the live engine's SMA warm-up, not enough to backtest a strategy. This
script pulls a much wider range (5m intraday + daily) using the same
SSIRestClient/Storage the production collector uses, so it benefits from
the day-chunked pagination fix in _paged_intraday().

Requires real SSI credentials in the environment (SSI_CONSUMER_ID,
SSI_CONSUMER_SECRET, SSI_API_KEY, SSI_API_SECRET, SSI_PRIVATE_KEY) and
DB_DSN - same variables trading/config.py already requires for the
collector/engine services. Writes directly to the real `bars`/`bars_daily`
tables (not a spike/dry-run).

Usage:
    uv run python scripts/backfill_history.py --config config/config.yaml \
        --intraday-days 90 --daily-days 730

Symbols come from config.yaml's `symbols` list unless --symbols is given.
"""

import argparse
import asyncio
from datetime import date, datetime, timedelta

from trading.calendar_vn import TZ
from trading.collector.backfill import SSIRestClient
from trading.config import load_config
from trading.storage.db import Storage


def range_from_days_back(days: int, today: date) -> tuple[date, date]:
    return today - timedelta(days=days), today


async def backfill_history(
    storage: Storage,
    client: SSIRestClient,
    symbols: list[str],
    today: date,
    intraday_days: int,
    daily_days: int,
) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    intraday_frm, _ = range_from_days_back(intraday_days, today)
    daily_frm, _ = range_from_days_back(daily_days, today)

    for sym in symbols:
        intraday = await client.intraday_ohlc(sym, intraday_frm, today)
        storage.write_bars(intraday)
        daily = await client.daily_ohlc(sym, daily_frm, today)
        storage.write_daily(daily)
        counts[sym] = {"intraday": len(intraday), "daily": len(daily)}
        print(
            f"{sym}: {len(intraday)} bar 5m ({intraday_frm}..{today}), "
            f"{len(daily)} bar daily ({daily_frm}..{today})"
        )
        if intraday:
            print(f"  5m dau: {intraday[0].ts}  5m cuoi: {intraday[-1].ts}")
        if daily:
            print(f"  daily dau: {daily[0].ts}  daily cuoi: {daily[-1].ts}")

    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument(
        "--symbols", nargs="*", default=None, help="mac dinh: symbols trong config.yaml"
    )
    ap.add_argument(
        "--intraday-days", type=int, default=90, help="so ngay lui lai cho bar 5 phut"
    )
    ap.add_argument(
        "--daily-days", type=int, default=730, help="so ngay lui lai cho bar ngay"
    )
    args = ap.parse_args()

    cfg = load_config(args.config)
    storage = Storage(cfg.db_dsn)
    storage.init_schema()
    symbols = args.symbols or cfg.symbols

    async def _run():
        client = SSIRestClient(cfg, storage)
        try:
            counts = await backfill_history(
                storage,
                client,
                symbols,
                datetime.now(TZ).date(),
                args.intraday_days,
                args.daily_days,
            )
        finally:
            await client.close()
        print(counts)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
