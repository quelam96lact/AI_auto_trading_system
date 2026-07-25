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
        c.execute("DELETE FROM account_balance_snapshot WHERE account_no = 'DASH_ACC'")
        c.execute("DELETE FROM account_position_snapshot WHERE account_no = 'DASH_ACC'")
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
    storage.update_pnl_daily(
        date(2026, 7, 15), realized_delta=100.0, fee_delta=5.0, unrealized=20.0
    )
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


def test_real_account_balance_panel_query(storage):
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    storage.save_account_balance("DASH_ACC", ts, 21459.0, 0.0, 21459.0, 0.0, 0.0)
    with storage.conn() as c:
        rows = c.execute(
            "SELECT ts AS time, account_no AS metric, account_balance AS value "
            "FROM account_balance_snapshot ORDER BY ts"
        ).fetchall()
    assert (ts, "DASH_ACC", 21459.0) in rows


def test_real_positions_panel_query(storage):
    older = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    newer = datetime(2026, 7, 15, 9, 5, tzinfo=TZ)
    # "DASH_SOLD" chỉ có ở lần sync cũ (mô phỏng vị thế đã bán hết trước lần
    # sync mới) — query "latest" phải bỏ hẳn nó, không được kẹt lại vô thời hạn.
    storage.save_account_positions(
        "DASH_ACC",
        older,
        [
            {
                "symbol": "DASH",
                "quantity": 10,
                "cost_price": 20.0,
                "sellable_quantity": 8,
            },
            {
                "symbol": "DASH_SOLD",
                "quantity": 5,
                "cost_price": 15.0,
                "sellable_quantity": 5,
            },
        ],
    )
    storage.save_account_positions(
        "DASH_ACC",
        newer,
        [
            {
                "symbol": "DASH",
                "quantity": 12,
                "cost_price": 21.0,
                "sellable_quantity": 9,
            }
        ],
    )
    with storage.conn() as c:
        rows = c.execute(
            "SELECT account_no, symbol, quantity, cost_price, sellable_quantity, ts "
            "FROM account_position_snapshot aps "
            "WHERE ts = (SELECT max(ts) FROM account_position_snapshot "
            "WHERE account_no = aps.account_no) "
            "ORDER BY account_no, symbol"
        ).fetchall()
    dash_acc_rows = [r for r in rows if r[0] == "DASH_ACC"]
    assert dash_acc_rows == [("DASH_ACC", "DASH", 12, 21.0, 9, newer)]
    # DASH_SOLD KHÔNG được xuất hiện — nó đã "bán hết" trước lần sync mới nhất
    # (không còn trong snapshot mới), nếu query dùng nhầm "latest per symbol"
    # thay vì "latest per account" thì nó sẽ kẹt lại vĩnh viễn ở đây (bug đã
    # sửa, xem PLAN_ACCOUNT_DATA_SYNC.md).
    assert all(r[1] != "DASH_SOLD" for r in rows)
