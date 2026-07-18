from contextlib import contextmanager
from datetime import datetime
from importlib.resources import files

import psycopg

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