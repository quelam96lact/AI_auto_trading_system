from contextlib import contextmanager
from datetime import date, datetime
from importlib.resources import files

import psycopg

from trading.broker import Fill, Position
from trading.models import Bar, IndexValue

_UPSERT_BAR = """
INSERT INTO {table} (symbol, ts, open, high, low, close, volume, source)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (symbol, ts) DO UPDATE SET
  open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
  close = EXCLUDED.close, volume = EXCLUDED.volume, source = EXCLUDED.source
"""


class Storage:
    def __init__(self, dsn: str):
        self.dsn = dsn

    @contextmanager
    def conn(self):
        with psycopg.connect(self.dsn) as c:
            yield c

    def init_schema(self) -> None:
        sql = files("trading.storage").joinpath("schema.sql").read_text(encoding="utf-8")
        with self.conn() as c:
            c.execute(sql)

    def _write(self, table: str, bars: list[Bar]) -> None:
        if not bars:
            return
        with self.conn() as c:
            c.cursor().executemany(
                _UPSERT_BAR.format(table=table),
                [(b.symbol, b.ts, b.open, b.high, b.low, b.close, b.volume, b.source) for b in bars],
            )

    def write_bars(self, bars: list[Bar]) -> None:
        self._write("bars", bars)

    def write_daily(self, bars: list[Bar]) -> None:
        self._write("bars_daily", bars)

    def read_bars(self, symbol: str, start: datetime, end: datetime) -> list[Bar]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol, ts, open, high, low, close, volume, source FROM bars "
                "WHERE symbol = %s AND ts >= %s AND ts < %s ORDER BY ts",
                (symbol, start, end),
            ).fetchall()
        return [Bar(*r) for r in rows]

    def last_bar_ts(self, symbol: str) -> datetime | None:
        with self.conn() as c:
            row = c.execute("SELECT max(ts) FROM bars WHERE symbol = %s", (symbol,)).fetchone()
        return row[0]

    def write_index_values(self, vals: list[IndexValue]) -> None:
        if not vals:
            return
        with self.conn() as c:
            c.cursor().executemany(
                "INSERT INTO index_values (index_id, ts, value) VALUES (%s, %s, %s) "
                "ON CONFLICT (index_id, ts) DO UPDATE SET value = EXCLUDED.value",
                [(v.index_id, v.ts, v.value) for v in vals],
            )

    def beat(self, service: str) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO heartbeat (service, last_seen) VALUES (%s, now()) "
                "ON CONFLICT (service) DO UPDATE SET last_seen = now()",
                (service,),
            )

    def upsert_position(self, pos: Position) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO positions (symbol, qty, avg_price, updated_at) VALUES (%s, %s, %s, now()) "
                "ON CONFLICT (symbol) DO UPDATE SET qty = EXCLUDED.qty, avg_price = EXCLUDED.avg_price, "
                "updated_at = now()",
                (pos.symbol, pos.qty, pos.avg_price),
            )

    def read_positions(self) -> dict[str, Position]:
        with self.conn() as c:
            rows = c.execute("SELECT symbol, qty, avg_price FROM positions WHERE qty > 0").fetchall()
        return {r[0]: Position(r[0], r[1], r[2]) for r in rows}

    def write_engine_state(self, cash: float, realized_pnl: float) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO engine_state (id, cash, realized_pnl, updated_at) VALUES (1, %s, %s, now()) "
                "ON CONFLICT (id) DO UPDATE SET cash = EXCLUDED.cash, "
                "realized_pnl = EXCLUDED.realized_pnl, updated_at = now()",
                (cash, realized_pnl),
            )

    def read_engine_state(self) -> tuple[float, float] | None:
        with self.conn() as c:
            row = c.execute("SELECT cash, realized_pnl FROM engine_state WHERE id = 1").fetchone()
        return (row[0], row[1]) if row else None

    def write_order(self, fill: Fill, mode: str = "paper") -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO orders (ts, symbol, side, qty, price, fee, pnl, mode) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (fill.ts, fill.symbol, fill.side, fill.qty, fill.price, fill.fee, fill.pnl, mode),
            )

    def save_ssi_token(self, access_token: str, expires_at: int, refresh_token: str, refresh_token_expires_at: int) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO ssi_auth_state (id, access_token, expires_at, refresh_token, refresh_token_expires_at, updated_at) "
                "VALUES (1, %s, %s, %s, %s, now()) "
                "ON CONFLICT (id) DO UPDATE SET access_token = EXCLUDED.access_token, "
                "expires_at = EXCLUDED.expires_at, refresh_token = EXCLUDED.refresh_token, "
                "refresh_token_expires_at = EXCLUDED.refresh_token_expires_at, updated_at = now()",
                (access_token, expires_at, refresh_token, refresh_token_expires_at),
            )

    def load_ssi_token(self) -> dict | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT access_token, expires_at, refresh_token, refresh_token_expires_at "
                "FROM ssi_auth_state WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        return {
            "access_token": row[0],
            "expires_at": row[1],
            "refresh_token": row[2],
            "refresh_token_expires_at": row[3],
        }

    def update_pnl_daily(self, day: date, realized_delta: float, fee_delta: float, unrealized: float) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO pnl_daily (date, realized, unrealized, fees) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (date) DO UPDATE SET "
                "realized = pnl_daily.realized + EXCLUDED.realized, "
                "fees = pnl_daily.fees + EXCLUDED.fees, "
                "unrealized = EXCLUDED.unrealized",
                (day, realized_delta, unrealized, fee_delta),
            )
