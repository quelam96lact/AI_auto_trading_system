#!/usr/bin/env python3
"""Script backfill du lieu giao dich khoi ngoai tu SSI DailyStockPrice vao DB.

Brief 190 (2026-10-23):
Doc tu ssi_fc_data MarketDataClient.daily_stock_price, luu vao bang foreign_flow_daily.
Chay tiep duoc tu ngay cuoi da nap thong qua --from.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta

from trading.calendar_vn import TZ
from trading.collector.foreign_flow import fetch_day, parse_daily_stock_price
from trading.config import Config, load_config
from trading.storage.db import Storage

logger = logging.getLogger(__name__)


def build_legacy_client(cfg: Config):
    """Tao client SSI MarketDataClient cu (ssi_fc_data)."""
    from ssi_fc_data.fc_md_client import MarketDataClient

    class _SdkCfg:
        auth_type = "Bearer"
        consumerID = cfg.ssi_consumer_id
        consumerSecret = cfg.ssi_consumer_secret
        url = "https://fc-data.ssi.com.vn/"
        stream_url = "https://fc-datahub.ssi.com.vn/"

    return MarketDataClient(_SdkCfg())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill foreign flow data from SSI DailyStockPrice into DB"
    )
    yesterday = datetime.now(tz=TZ).date() - timedelta(days=1)
    parser.add_argument(
        "--config", default="config/config.yaml", help="Path to config.yaml"
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        default="2020-02-26",
        help="Start date YYYY-MM-DD (default: 2020-02-26)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        default=yesterday.isoformat(),
        help=f"End date YYYY-MM-DD (default: {yesterday.isoformat()})",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=1.1,
        help="Sleep seconds between requests (default: 1.1)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args)


def run(args, client=None, storage=None) -> int:
    try:
        start_date = date.fromisoformat(args.from_date)
        end_date = date.fromisoformat(args.to_date)
    except ValueError as e:
        print(f"ERROR: Invalid date format: {e}", file=sys.stderr)
        return 1

    # Audit 24/10: Config khong co from_yaml; chay that dau tien chet AttributeError
    if storage is None:
        cfg = load_config(args.config)
        storage = Storage(cfg.db_dsn)
    else:
        cfg = None

    allowed = storage.read_symbol_universe()
    if not allowed:
        print("ERROR: symbol_universe is empty", file=sys.stderr)
        return 3

    if client is None:
        if cfg is None:
            cfg = load_config(args.config)
        client = build_legacy_client(cfg)

    cur = start_date
    total_counts = {
        "rows": 0,
        "kept": 0,
        "not_in_universe": 0,
        "bad_row": 0,
        "net_mismatch": 0,
    }
    last_done: date | None = None

    while cur <= end_date:
        if cur.weekday() < 5:  # Thu 2 den Thu 6
            try:
                rows, _meta = fetch_day(client, cur, sleep=args.sleep)
            except Exception as e:
                last_done_str = last_done.isoformat() if last_done else ""
                print(f"API Error at {cur.isoformat()}: {e}", file=sys.stderr)
                print(f"last_done={last_done_str}")
                return 2

            if not rows:
                print(f"{cur.isoformat()} no_session")
            else:
                flows, counts = parse_daily_stock_price({"data": rows}, allowed)
                storage.write_foreign_flow(flows)
                last_done = cur
                for k in total_counts:
                    total_counts[k] += counts[k]
                print(
                    f"{cur.isoformat()} rows={counts['rows']} kept={counts['kept']} "
                    f"not_in_universe={counts['not_in_universe']} bad_row={counts['bad_row']} "
                    f"net_mismatch={counts['net_mismatch']}"
                )

        cur += timedelta(days=1)

    last_done_str = last_done.isoformat() if last_done else ""
    print(
        f"Done. rows={total_counts['rows']} kept={total_counts['kept']} "
        f"not_in_universe={total_counts['not_in_universe']} bad_row={total_counts['bad_row']} "
        f"net_mismatch={total_counts['net_mismatch']} last_done={last_done_str}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
