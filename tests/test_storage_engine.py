from datetime import date, datetime

import pytest

from tests.conftest import TEST_DSN
from trading.broker import Fill, Position
from trading.calendar_vn import TZ
from trading.storage.db import Storage

DSN = TEST_DSN
pytestmark = pytest.mark.integration


@pytest.fixture
def storage():
    s = Storage(DSN)
    s.init_schema()
    with s.conn() as c:
        c.execute("DELETE FROM positions WHERE symbol = 'TEST'")
        c.execute("DELETE FROM orders WHERE symbol = 'TEST'")
        c.execute("DELETE FROM pnl_daily WHERE date = '2026-07-15'")
        c.execute("DELETE FROM engine_state WHERE id = 1")
    return s


def test_position_upsert_and_read(storage):
    storage.upsert_position(Position("TEST", 100, 10.5))
    assert storage.read_positions()["TEST"].qty == 100
    storage.upsert_position(Position("TEST", 200, 11.0))
    assert storage.read_positions()["TEST"].avg_price == 11.0


def test_zero_qty_position_excluded_from_read(storage):
    storage.upsert_position(Position("TEST", 0, 0.0))
    assert "TEST" not in storage.read_positions()


def test_engine_state_roundtrip(storage):
    assert storage.read_engine_state() is None
    storage.write_engine_state(cash=99_000_000, realized_pnl=500_000)
    assert storage.read_engine_state() == (99_000_000, 500_000)


def test_write_order_and_pnl_daily(storage):
    fill = Fill(
        "TEST",
        "SELL",
        100,
        11.0,
        165.0,
        datetime(2026, 7, 15, 9, 5, tzinfo=TZ),
        pnl=45.0,
    )
    storage.write_order(fill)
    storage.update_pnl_daily(
        date(2026, 7, 15),
        realized_delta=fill.pnl,
        fee_delta=fill.fee,
        unrealized=0.0,
    )
    storage.update_pnl_daily(
        date(2026, 7, 15),
        realized_delta=0.0,
        fee_delta=0.0,
        unrealized=200.0,
    )
    with storage.conn() as c:
        row = c.execute(
            "SELECT realized, unrealized, fees FROM pnl_daily WHERE date = %s",
            (date(2026, 7, 15),),
        ).fetchone()
    assert row == (45.0, 200.0, 165.0)
