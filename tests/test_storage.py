import os
from datetime import datetime, timedelta

import pytest

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
        c.execute("DELETE FROM bars WHERE symbol = 'TEST'")
        c.execute("DELETE FROM account_balance_snapshot WHERE account_no = 'ACC_TEST'")
        c.execute("DELETE FROM account_position_snapshot WHERE account_no = 'ACC_TEST'")
    return s


def bar(minute, close=101.0):
    return Bar("TEST", datetime(2026, 7, 15, 9, minute, tzinfo=TZ), 100.0, 102.0, 99.0, close, 1000)


def test_write_read_roundtrip(storage):
    storage.write_bars([bar(0), bar(5)])
    got = storage.read_bars("TEST", bar(0).ts, bar(0).ts + timedelta(minutes=10))
    assert [b.ts.astimezone(TZ).minute for b in got] == [0, 5]
    assert got[0].close == 101.0


def test_upsert_idempotent(storage):
    storage.write_bars([bar(0)])
    storage.write_bars([bar(0, close=105.0)])  # ghi lại cùng khóa → update
    got = storage.read_bars("TEST", bar(0).ts, bar(0).ts + timedelta(minutes=5))
    assert len(got) == 1 and got[0].close == 105.0


def test_last_bar_ts(storage):
    assert storage.last_bar_ts("TEST") is None
    storage.write_bars([bar(0), bar(5)])
    assert storage.last_bar_ts("TEST") == bar(5).ts


def test_save_account_balance_upsert(storage):
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    storage.save_account_balance("ACC_TEST", ts, 100.0, 10.0, 90.0, 1.0, 2.0)
    storage.save_account_balance("ACC_TEST", ts, 200.0, 20.0, 180.0, 3.0, 4.0)

    with storage.conn() as c:
        row = c.execute(
            "SELECT account_balance, total_debt, withdrawable, buy_unmatched, sell_unmatched "
            "FROM account_balance_snapshot WHERE account_no = 'ACC_TEST' AND ts = %s",
            (ts,),
        ).fetchone()
    assert row == (200.0, 20.0, 180.0, 3.0, 4.0)


def test_save_account_positions_upsert(storage):
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    storage.save_account_positions(
        "ACC_TEST",
        ts,
        [{"symbol": "TEST", "quantity": 10, "cost_price": 20.5, "sellable_quantity": 7}],
    )
    storage.save_account_positions(
        "ACC_TEST",
        ts,
        [{"symbol": "TEST", "quantity": 12, "cost_price": 21.5, "sellable_quantity": 8}],
    )

    with storage.conn() as c:
        row = c.execute(
            "SELECT symbol, quantity, cost_price, sellable_quantity "
            "FROM account_position_snapshot WHERE account_no = 'ACC_TEST' AND ts = %s",
            (ts,),
        ).fetchone()
    assert row == ("TEST", 12, 21.5, 8)
