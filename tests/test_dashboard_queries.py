import os
from datetime import date, datetime

import pytest

from trading.broker import Position
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.storage.db import Storage

DSN = os.environ.get("DB_DSN", "postgresql://trading:trading@localhost:5432/trading")
pytestmark = pytest.mark.integration


@pytest.fixture
def storage():
    s = Storage(DSN)
    s.init_schema()
    with s.conn() as c:
        c.execute("DELETE FROM bars WHERE symbol = 'DASH'")
        c.execute("DELETE FROM positions WHERE symbol = 'DASH'")
        c.execute("DELETE FROM pnl_daily WHERE date = '2026-07-15'")
        c.execute("DELETE FROM heartbeat WHERE service = 'dash_test'")
    return s


def test_price_panel_query(storage):
    bar = Bar("DASH", datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 10, 11, 9, 10.5, 1000)
    storage.write_bars([bar])
    with storage.conn() as c:
        rows = c.execute(
            "SELECT ts AS time, close FROM bars WHERE symbol = 'DASH' ORDER BY ts"
        ).fetchall()
    assert rows == [(bar.ts, 10.5)]


def test_pnl_panel_query(storage):
    storage.update_pnl_daily(date(2026, 7, 15), realized_delta=100.0, fee_delta=5.0, unrealized=20.0)
    with storage.conn() as c:
        row = c.execute(
            "SELECT date AS time, realized, unrealized, fees FROM pnl_daily ORDER BY date"
        ).fetchone()
    assert row == (date(2026, 7, 15), 100.0, 20.0, 5.0)


def test_positions_panel_query(storage):
    storage.upsert_position(Position("DASH", 100, 10.5))
    with storage.conn() as c:
        rows = c.execute(
            "SELECT symbol, qty, avg_price FROM positions WHERE qty > 0 AND symbol = 'DASH'"
        ).fetchall()
    assert rows == [("DASH", 100, 10.5)]


def test_heartbeat_panel_query(storage):
    storage.beat("dash_test")
    with storage.conn() as c:
        row = c.execute(
            "SELECT service, extract(epoch from (now() - last_seen)) AS age_seconds "
            "FROM heartbeat WHERE service = 'dash_test'"
        ).fetchone()
    assert row[0] == "dash_test" and row[1] < 5
