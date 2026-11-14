"""CLI runner for the daily-candle paper engine (Brief 233 §5)."""

from __future__ import annotations

import argparse
import sys
import traceback
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

import psycopg

from scripts._db_common import resolve_dsn
from trading.calendar_vn import TZ, is_trading_day
from trading.daily_engine import store
from trading.daily_engine.core import Lot, process_day
from trading.daily_engine.strategy import (
    DailyContext,
    DailyStrategy,
    UnknownStrategyError,
    resolve_strategy,
)
from trading.scheduler.main import load_holidays
from trading.storage.db import Storage

CAPITAL = 100_000_000.0
START_DATE = date(2026, 1, 1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m trading.daily_engine.runner",
        description="Run daily-candle paper engine on ready sessions up to today.",
    )
    parser.add_argument("--dsn", default=None, help="PostgreSQL DSN (mac dinh lay DB_DSN)")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Duong dan file config.yaml chua holidays",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chay thu va rollback toan bo transaction, in tom tat",
    )
    return parser


def _build_sessions(start: date, end: date, holidays: set[date]) -> list[date]:
    sessions: list[date] = []
    cur = start
    while cur <= end:
        if is_trading_day(cur, holidays):
            sessions.append(cur)
        cur += timedelta(days=1)
    return sessions


def _aggregate_positions(lots: list[Lot]) -> dict[str, int]:
    positions: dict[str, int] = defaultdict(int)
    for lot in lots:
        if lot.qty > 0:
            positions[lot.symbol] += lot.qty
    return dict(positions)


def _process_single_session(
    conn: psycopg.Connection,
    d: date,
    sessions: list[date],
    active_symbols: list[str],
    active_strategy: DailyStrategy,
) -> tuple[bool, str | None, int, int, float]:
    """Process one session inside `conn`'s active transaction.

    Returns `(ready, reason, handled_orders, created_orders, nav)`.
    """
    ready_cnt = store.count_active_bars_on_day(conn, d, active_symbols)
    total_active = len(active_symbols)
    if not store.is_session_ready(ready_cnt, total_active):
        reason = (
            f"Dừng tại phiên {d}: mới có {ready_cnt}/{total_active} mã active "
            f"có nến ngày (<90%)."
        )
        return False, reason, 0, 0, 0.0

    state = store.load_state(conn)
    if state is None:
        raise RuntimeError("paper_daily_state missing while processing session")

    lots = store.load_lots(conn)
    pending = store.load_pending_orders(conn)
    symbols = {lot.symbol for lot in lots} | {order.symbol for order in pending}
    bars_on_d = store.load_bars_on_day(conn, d, symbols)
    last_close = store.load_last_close_up_to(conn, d, symbols)

    result = process_day(
        cash=state.cash,
        realized_pnl=state.realized_pnl,
        lots=lots,
        pending=pending,
        bars_on_d=bars_on_d,
        last_close=last_close,
        d=d,
        sessions=sessions,
    )

    store.save_order_outcomes(conn, d, result.outcomes)
    store.replace_lots(conn, result.lots)
    n_positions = len({lot.symbol for lot in result.lots if lot.qty > 0})
    store.upsert_daily_nav(conn, d, result.cash, result.market_value, result.nav, n_positions)
    store.update_state(conn, result.cash, result.realized_pnl, d)

    positions = _aggregate_positions(result.lots)
    ctx = DailyContext(
        d=d,
        universe=list(active_symbols),
        cash=result.cash,
        nav=result.nav,
        positions=positions,
        bars_loader=lambda sym, n, _d=d, _c=conn: store.load_symbol_history_bars(_c, sym, _d, n),
    )
    intents = active_strategy.on_day(ctx)
    created = store.insert_pending_orders(conn, active_strategy.name, d, intents)
    return True, None, len(result.outcomes), created, result.nav


def _execute_engine(
    storage: Storage,
    active_strategy: DailyStrategy,
    active_symbols: list[str],
    holidays: set[date],
    vn_today: date,
    dry_run: bool,
    dry_conn: psycopg.Connection | None,
) -> int:
    @contextmanager
    def tx_scope() -> Iterator[psycopg.Connection]:
        if dry_conn is not None:
            yield dry_conn
        else:
            with storage.conn() as sc, sc.transaction():
                yield sc

    with tx_scope() as conn:
        state = store.load_state(conn)
        if state is None:
            init_sessions = _build_sessions(START_DATE, vn_today, holidays)
            ready_date = store.find_latest_ready_session(conn, init_sessions, active_symbols)
            if ready_date is None:
                print(
                    f"Chưa có phiên nào đủ dữ liệu (>=90% trong {len(active_symbols)} mã active) "
                    f"từ {START_DATE} đến {vn_today}.",
                    file=sys.stderr,
                )
                return 1
            store.insert_initial_state(conn, active_strategy.name, CAPITAL, ready_date)
            if dry_run:
                print(
                    f"[DRY-RUN] init strategy={active_strategy.name} "
                    f"last_processed_date={ready_date} sessions=0 orders=0 nav={CAPITAL:,.0f}"
                )
            return 0

        if state.strategy != active_strategy.name:
            print(
                f"LỖI: paper_daily_state đang lưu strategy={state.strategy!r}, "
                f"không khớp với {active_strategy.name!r}.",
                file=sys.stderr,
            )
            return 2

        existing_lots = store.load_lots(conn)
        last_nav = store.load_latest_nav_or_cash(conn, state.cash)

    min_lot_date = min((lot.buy_date for lot in existing_lots), default=START_DATE)
    session_start = min(START_DATE, state.last_processed_date, min_lot_date)
    sessions = _build_sessions(session_start, vn_today, holidays)
    todo_sessions = [d for d in sessions if state.last_processed_date < d <= vn_today]

    if not todo_sessions:
        if dry_run:
            print(
                f"[DRY-RUN] strategy={active_strategy.name} sessions=0 orders_handled=0 "
                f"orders_created=0 nav={last_nav:,.0f}"
            )
        return 0

    sessions_processed = 0
    total_handled = 0
    total_created = 0
    final_nav = last_nav

    for d in todo_sessions:
        with tx_scope() as conn:
            ready, reason, handled, created, nav = _process_single_session(
                conn=conn,
                d=d,
                sessions=sessions,
                active_symbols=active_symbols,
                active_strategy=active_strategy,
            )
        if not ready:
            print(reason, file=sys.stderr)
            return 1
        sessions_processed += 1
        total_handled += handled
        total_created += created
        final_nav = nav

    if dry_run:
        print(
            f"[DRY-RUN] strategy={active_strategy.name} sessions={sessions_processed} "
            f"orders_handled={total_handled} orders_created={total_created} nav={final_nav:,.0f}"
        )
    return 0


def run_daily_engine(
    dsn: str | None = None,
    config_path: str | Path = "config/config.yaml",
    dry_run: bool = False,
    strategy: DailyStrategy | None = None,
    today: date | None = None,
) -> int:
    try:
        active_strategy = resolve_strategy() if strategy is None else strategy
    except UnknownStrategyError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2

    try:
        resolved_dsn = resolve_dsn(dsn)
    except SystemExit as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2

    vn_today = today or datetime.now(TZ).date()
    holidays = load_holidays(config_path)
    storage = Storage(resolved_dsn)
    storage.init_schema()
    active_symbols = storage.read_active_universe()

    if dry_run:
        with storage.conn() as dry_conn, dry_conn.transaction(force_rollback=True):
            return _execute_engine(
                storage=storage,
                active_strategy=active_strategy,
                active_symbols=active_symbols,
                holidays=holidays,
                vn_today=vn_today,
                dry_run=True,
                dry_conn=dry_conn,
            )

    return _execute_engine(
        storage=storage,
        active_strategy=active_strategy,
        active_symbols=active_symbols,
        holidays=holidays,
        vn_today=vn_today,
        dry_run=False,
        dry_conn=None,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_daily_engine(
        dsn=args.dsn,
        config_path=args.config,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(3)
