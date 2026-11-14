"""PostgreSQL store helpers for the daily-candle paper ledger (Brief 233 §1, §2, §5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import psycopg

from trading.calendar_vn import TZ
from trading.daily_engine.core import DailyBar, Lot, OrderOutcome, PendingOrder
from trading.daily_engine.strategy import OrderIntent

READY_NUMERATOR = 9
READY_DENOMINATOR = 10


@dataclass(frozen=True, slots=True)
class DailyEngineState:
    strategy: str
    capital: float
    cash: float
    realized_pnl: float
    last_processed_date: date


def _vn_day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=TZ)
    return start, start + timedelta(days=1)


def is_session_ready(present_count: int, total_active: int) -> bool:
    """Return True when at least 90% of active symbols have daily bars."""
    if total_active <= 0:
        return False
    return present_count * READY_DENOMINATOR >= READY_NUMERATOR * total_active


def load_state(conn: psycopg.Connection) -> DailyEngineState | None:
    row = conn.execute(
        "SELECT strategy, capital, cash, realized_pnl, last_processed_date "
        "FROM paper_daily_state WHERE id = 1"
    ).fetchone()
    if row is None:
        return None
    return DailyEngineState(
        strategy=row[0],
        capital=float(row[1]),
        cash=float(row[2]),
        realized_pnl=float(row[3]),
        last_processed_date=row[4],
    )


def insert_initial_state(
    conn: psycopg.Connection,
    strategy: str,
    capital: float,
    last_processed_date: date,
) -> None:
    conn.execute(
        "INSERT INTO paper_daily_state (id, strategy, capital, cash, realized_pnl, last_processed_date) "
        "VALUES (1, %s, %s, %s, 0.0, %s)",
        (strategy, capital, capital, last_processed_date),
    )


def update_state(
    conn: psycopg.Connection,
    cash: float,
    realized_pnl: float,
    last_processed_date: date,
) -> None:
    conn.execute(
        "UPDATE paper_daily_state "
        "SET cash = %s, realized_pnl = %s, last_processed_date = %s, updated_at = now() "
        "WHERE id = 1",
        (cash, realized_pnl, last_processed_date),
    )


def find_latest_ready_session(
    conn: psycopg.Connection,
    sessions: list[date],
    active_symbols: list[str],
) -> date | None:
    if not sessions or not active_symbols:
        return None
    start_ts, _ = _vn_day_bounds(sessions[0])
    _, end_ts = _vn_day_bounds(sessions[-1])
    rows = conn.execute(
        "SELECT (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS vn_date, "
        "       count(DISTINCT symbol) AS cnt "
        "FROM bars_daily "
        "WHERE symbol = ANY(%s) AND ts >= %s AND ts < %s "
        "GROUP BY 1",
        (active_symbols, start_ts, end_ts),
    ).fetchall()
    session_set = set(sessions)
    total_active = len(active_symbols)
    ready_dates = [
        vn_date
        for vn_date, cnt in rows
        if vn_date in session_set and is_session_ready(int(cnt), total_active)
    ]
    return max(ready_dates) if ready_dates else None


def count_active_bars_on_day(
    conn: psycopg.Connection,
    d: date,
    active_symbols: list[str],
) -> int:
    if not active_symbols:
        return 0
    start_ts, end_ts = _vn_day_bounds(d)
    row = conn.execute(
        "SELECT count(DISTINCT symbol) "
        "FROM bars_daily "
        "WHERE symbol = ANY(%s) AND ts >= %s AND ts < %s",
        (active_symbols, start_ts, end_ts),
    ).fetchone()
    return int(row[0]) if row is not None else 0


def load_pending_orders(conn: psycopg.Connection) -> list[PendingOrder]:
    rows = conn.execute(
        "SELECT id, created_date, symbol, side, qty "
        "FROM paper_daily_orders "
        "WHERE status = 'pending' "
        "ORDER BY id ASC"
    ).fetchall()
    return [
        PendingOrder(
            id=int(row[0]),
            created_date=row[1],
            symbol=row[2],
            side=row[3],
            qty=int(row[4]),
        )
        for row in rows
    ]


def load_lots(conn: psycopg.Connection) -> list[Lot]:
    rows = conn.execute(
        "SELECT symbol, qty, cost_per_share, buy_date "
        "FROM paper_daily_lots "
        "ORDER BY id ASC"
    ).fetchall()
    return [
        Lot(
            symbol=row[0],
            qty=int(row[1]),
            cost_per_share=float(row[2]),
            buy_date=row[3],
        )
        for row in rows
    ]


def load_bars_on_day(
    conn: psycopg.Connection,
    d: date,
    symbols: set[str],
) -> dict[str, DailyBar]:
    if not symbols:
        return {}
    start_ts, end_ts = _vn_day_bounds(d)
    rows = conn.execute(
        "SELECT DISTINCT ON (symbol) symbol, open, high, low, close, volume "
        "FROM bars_daily "
        "WHERE symbol = ANY(%s) AND ts >= %s AND ts < %s "
        "ORDER BY symbol, ts DESC",
        (sorted(symbols), start_ts, end_ts),
    ).fetchall()
    return {
        row[0]: DailyBar(
            symbol=row[0],
            date=d,
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
        )
        for row in rows
    }


def load_last_close_up_to(
    conn: psycopg.Connection,
    d: date,
    symbols: set[str],
) -> dict[str, float]:
    if not symbols:
        return {}
    _, end_ts = _vn_day_bounds(d)
    rows = conn.execute(
        "SELECT DISTINCT ON (symbol) symbol, close "
        "FROM bars_daily "
        "WHERE symbol = ANY(%s) AND ts < %s AND close > 0 "
        "ORDER BY symbol, ts DESC",
        (sorted(symbols), end_ts),
    ).fetchall()
    return {row[0]: float(row[1]) for row in rows}


def load_symbol_history_bars(
    conn: psycopg.Connection,
    symbol: str,
    d: date,
    n: int,
) -> list[DailyBar]:
    if n <= 0:
        return []
    _, end_ts = _vn_day_bounds(d)
    rows = conn.execute(
        "SELECT ts, open, high, low, close, volume "
        "FROM bars_daily "
        "WHERE symbol = %s AND ts < %s "
        "ORDER BY ts DESC "
        "LIMIT %s",
        (symbol, end_ts, n),
    ).fetchall()
    bars = [
        DailyBar(
            symbol=symbol,
            date=row[0].astimezone(TZ).date(),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
        )
        for row in reversed(rows)
    ]
    return bars


def save_order_outcomes(
    conn: psycopg.Connection,
    exec_date: date,
    outcomes: list[OrderOutcome],
) -> None:
    if not outcomes:
        return
    params = [
        (
            exec_date,
            out.status,
            out.filled_qty,
            out.price,
            out.fee,
            out.tax,
            out.reason,
            out.order_id,
        )
        for out in outcomes
    ]
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE paper_daily_orders "
            "SET exec_date = %s, status = %s, filled_qty = %s, "
            "    price = %s, fee = %s, tax = %s, reason = %s "
            "WHERE id = %s",
            params,
        )


def replace_lots(conn: psycopg.Connection, lots: list[Lot]) -> None:
    conn.execute("DELETE FROM paper_daily_lots")
    active_lots = [(lot.symbol, lot.qty, lot.cost_per_share, lot.buy_date) for lot in lots if lot.qty > 0]
    if not active_lots:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO paper_daily_lots (symbol, qty, cost_per_share, buy_date) "
            "VALUES (%s, %s, %s, %s)",
            active_lots,
        )


def upsert_daily_nav(
    conn: psycopg.Connection,
    d: date,
    cash: float,
    market_value: float,
    nav: float,
    n_positions: int,
) -> None:
    conn.execute(
        "INSERT INTO paper_daily_nav (date, cash, market_value, nav, n_positions) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (date) DO UPDATE "
        "SET cash = EXCLUDED.cash, "
        "    market_value = EXCLUDED.market_value, "
        "    nav = EXCLUDED.nav, "
        "    n_positions = EXCLUDED.n_positions",
        (d, cash, market_value, nav, n_positions),
    )


def insert_pending_orders(
    conn: psycopg.Connection,
    strategy_name: str,
    created_date: date,
    intents: list[OrderIntent],
) -> int:
    if not intents:
        return 0
    params = [
        (strategy_name, created_date, intent.symbol, intent.side, intent.qty)
        for intent in intents
    ]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO paper_daily_orders (strategy, created_date, symbol, side, qty, status) "
            "VALUES (%s, %s, %s, %s, %s, 'pending')",
            params,
        )
    return len(params)


def load_latest_nav_or_cash(conn: psycopg.Connection, fallback_cash: float) -> float:
    row = conn.execute(
        "SELECT nav FROM paper_daily_nav ORDER BY date DESC LIMIT 1"
    ).fetchone()
    return float(row[0]) if row is not None else fallback_cash
