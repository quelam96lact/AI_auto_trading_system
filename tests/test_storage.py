import os
from datetime import date, datetime, timedelta

import pytest

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.storage.db import RealPosition, Storage

DSN = os.environ.get("DB_DSN", "postgresql://trading:trading@127.0.0.1:5432/trading")
pytestmark = pytest.mark.integration


@pytest.fixture
def storage():
    s = Storage(DSN)
    s.init_schema()
    with s.conn() as c:
        c.execute("DELETE FROM bars WHERE symbol = 'TEST'")
        c.execute("DELETE FROM account_balance_snapshot WHERE account_no = 'ACC_TEST'")
        c.execute("DELETE FROM account_position_snapshot WHERE account_no = 'ACC_TEST'")
        c.execute("DELETE FROM pending_real_orders WHERE account_no = 'ACC_TEST'")
        c.execute("DELETE FROM real_order_fills WHERE account_no = 'ACC_TEST'")
        c.execute("DELETE FROM real_risk_state WHERE id = 1")
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


def test_storage_instances_share_pool_by_dsn():
    """Hai Storage cùng DSN phải dùng CHUNG một pool (cấp module) — mỗi
    instance một pool sẽ cạn connection Postgres khi test tạo hàng chục Storage."""
    from trading.storage.db import _get_pool

    s1 = Storage(DSN)
    s2 = Storage(DSN)
    assert _get_pool(s1.dsn) is _get_pool(s2.dsn), "pool phai dung chung theo DSN"
    assert _get_pool(s1.dsn).max_size == 8, "khoi tao min_size=1, max_size=8"


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


def test_create_and_get_pending_order(storage):
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    oid = storage.create_pending_order(
        account_no="ACC_TEST",
        symbol="VCB",
        side="BUY",
        quantity=100,
        price=50000.0,
        expires_at=ts + timedelta(minutes=15),
    )
    got = storage.get_pending_order(oid)
    assert got is not None
    assert got["account_no"] == "ACC_TEST"
    assert got["symbol"] == "VCB"
    assert got["side"] == "BUY"
    assert got["quantity"] == 100
    assert got["price"] == 50000.0
    assert got["status"] == "pending"
    assert got["ssi_order_id"] is None
    assert got["confirmed_at"] is None


def test_update_pending_order_status(storage):
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    oid = storage.create_pending_order(
        account_no="ACC_TEST",
        symbol="VCB",
        side="BUY",
        quantity=100,
        price=50000.0,
        expires_at=ts + timedelta(minutes=15),
    )
    storage.update_pending_order_status(oid, "confirmed", ssi_order_id="SSI-123")
    got = storage.get_pending_order(oid)
    assert got["status"] == "confirmed"
    assert got["ssi_order_id"] == "SSI-123"
    assert got["confirmed_at"] is not None


def test_expire_stale_pending_orders(storage):
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    oid = storage.create_pending_order(
        account_no="ACC_TEST",
        symbol="VCB",
        side="BUY",
        quantity=100,
        price=50000.0,
        expires_at=ts - timedelta(minutes=1),
    )
    n = storage.expire_stale_pending_orders()
    assert n == 1
    got = storage.get_pending_order(oid)
    assert got["status"] == "expired"


def test_read_real_positions_ignores_older_snapshot_for_sold_symbol(storage):
    ts_old = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    ts_new = datetime(2026, 7, 15, 10, 0, tzinfo=TZ)
    storage.save_account_positions(
        "ACC_TEST",
        ts_old,
        [
            {"symbol": "VCB", "quantity": 100, "cost_price": 50000.0, "sellable_quantity": 100},
            {"symbol": "HPG", "quantity": 50, "cost_price": 20000.0, "sellable_quantity": 50},
        ],
    )
    storage.save_account_positions(
        "ACC_TEST",
        ts_new,
        [
            {"symbol": "HPG", "quantity": 50, "cost_price": 20000.0, "sellable_quantity": 50},
        ],
    )
    got = storage.read_real_positions("ACC_TEST")
    assert "VCB" not in got
    assert "HPG" in got
    assert got["HPG"] == RealPosition("HPG", 50, 20000.0, 50)


def test_read_real_positions_reports_sellable_qty_lower_than_qty(storage):
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    storage.save_account_positions(
        "ACC_TEST",
        ts,
        [{"symbol": "VCB", "quantity": 100, "cost_price": 50000.0, "sellable_quantity": 30}],
    )
    got = storage.read_real_positions("ACC_TEST")
    assert "VCB" in got
    assert got["VCB"] == RealPosition("VCB", 100, 50000.0, 30)


def test_read_real_daily_pnl_sums_same_day(storage):
    day = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    storage.write_real_order_fill(
        account_no="ACC_TEST",
        ts=day,
        symbol="VCB",
        side="SELL",
        qty=100,
        price=55000.0,
        fee=10.0,
        pnl=50000.0,
        ssi_order_id="SSI-1",
        status="filled",
    )
    storage.write_real_order_fill(
        account_no="ACC_TEST",
        ts=day + timedelta(hours=2),
        symbol="HPG",
        side="SELL",
        qty=50,
        price=21000.0,
        fee=5.0,
        pnl=5000.0,
        ssi_order_id="SSI-2",
        status="filled",
    )
    storage.write_real_order_fill(
        account_no="ACC_TEST",
        ts=day + timedelta(days=1),
        symbol="VCB",
        side="SELL",
        qty=100,
        price=56000.0,
        fee=10.0,
        pnl=60000.0,
        ssi_order_id="SSI-3",
        status="filled",
    )
    assert storage.read_real_daily_pnl("ACC_TEST", day.date()) == 55000.0
    assert storage.read_real_daily_pnl("ACC_TEST", (day + timedelta(days=1)).date()) == 60000.0


def test_read_real_daily_pnl_uses_vn_calendar_day_not_utc(storage):
    # 2026-07-16 01:00 ICT == 2026-07-15 18:00 UTC — a naive `ts::date` cast under a
    # UTC session timezone would attribute this fill to 2026-07-15, not the VN
    # calendar day it actually happened on.
    late_night_ict = datetime(2026, 7, 16, 1, 0, tzinfo=TZ)
    storage.write_real_order_fill(
        account_no="ACC_TEST",
        ts=late_night_ict,
        symbol="VCB",
        side="SELL",
        qty=100,
        price=55000.0,
        fee=10.0,
        pnl=12345.0,
        ssi_order_id="SSI-4",
        status="filled",
    )
    assert storage.read_real_daily_pnl("ACC_TEST", date(2026, 7, 16)) == 12345.0
    assert storage.read_real_daily_pnl("ACC_TEST", date(2026, 7, 15)) == 0.0


def test_update_pending_order_status_raises_on_unknown_id(storage):
    with pytest.raises(ValueError):
        storage.update_pending_order_status(999_999_999, "confirmed")


def test_save_and_read_real_risk_halt(storage):
    day = date(2026, 7, 15)
    storage.save_real_risk_halt(day)
    assert storage.read_real_risk_halt() == day


def test_read_real_risk_halt_returns_none_when_never_set(storage):
    assert storage.read_real_risk_halt() is None


def test_save_real_risk_halt_upsert(storage):
    storage.save_real_risk_halt(date(2026, 7, 15))
    storage.save_real_risk_halt(date(2026, 7, 16))
    assert storage.read_real_risk_halt() == date(2026, 7, 16)


def test_symbol_universe_upsert_and_read_active(storage):
    with storage.conn() as c:
        c.execute("DELETE FROM symbol_universe WHERE symbol LIKE 'ZZ%'")
    storage.upsert_symbol_universe([
        {"symbol": "ZZA", "exchange": "HOSE", "avg_value_20d": 5e9,
         "avg_volume_20d": 100000, "is_active": True},
        {"symbol": "ZZB", "exchange": "UPCOM", "avg_value_20d": 1e6,
         "avg_volume_20d": 100, "is_active": False},
    ])
    active = storage.read_active_universe()
    assert "ZZA" in active
    assert "ZZB" not in active

    # upsert lai phai GHI DE, khong tao dong trung
    storage.upsert_symbol_universe([
        {"symbol": "ZZA", "exchange": "HOSE", "avg_value_20d": 1.0,
         "avg_volume_20d": 1, "is_active": False},
    ])
    assert "ZZA" not in storage.read_active_universe()


def test_backfill_progress_roundtrip(storage):
    with storage.conn() as c:
        c.execute("DELETE FROM backfill_progress WHERE symbol = 'ZZA'")
    assert storage.get_backfill_progress("ZZA", "1d") is None

    storage.set_backfill_progress("ZZA", "1d", date(2026, 1, 31), "ok")
    got = storage.get_backfill_progress("ZZA", "1d")
    assert got["last_done_date"] == date(2026, 1, 31)
    assert got["status"] == "ok"

    storage.set_backfill_progress("ZZA", "1d", date(2026, 2, 28), "error", "boom")
    got = storage.get_backfill_progress("ZZA", "1d")
    assert got["status"] == "error" and got["error"] == "boom"


def test_bars_daily_is_hypertable(storage):
    """bars_daily se chua ~4 trieu dong (1600 ma x 10 nam); khong hypertable thi
    query theo khoang thoi gian khong duoc chunk pruning."""
    with storage.conn() as c:
        row = c.execute(
            "SELECT count(*) FROM timescaledb_information.hypertables "
            "WHERE hypertable_name = 'bars_daily'"
        ).fetchone()
    assert row[0] == 1, "bars_daily phai la hypertable"


def test_pool_survives_postgres_restart_first_query():
    """Restart postgres -> query NGAY phai thanh cong o LAN DAU (khong retry).

    Regression canh bao (Claude repro): pool khong check connection -> dua
    connection BAD ra caller -> query dau sau restart that bai
    (OperationalError: could not receive data from server), chi lan thu hai
    moi OK. Truoc khi co pool moi query tu mo connection moi nen sau khi
    postgres song lai query ke tiep THANH CONG NGAY - mat di hieu qua do la
    regression khong the chap nhan (persist_bars -> alert CRITICAL mat 1 nen;
    persist_fills -> term() mat 1 fill).
    """
    import subprocess
    import time

    s = Storage(DSN)
    with s.conn() as c:
        c.execute("SELECT 1")

    subprocess.run(
        ["docker", "compose", "restart", "postgres"],
        check=True,
        capture_output=True,
        timeout=60,
    )
    # chờ postgres sẵn sàng (kết nối trực tiếp, không qua pool)
    import psycopg

    for _ in range(60):
        try:
            with psycopg.connect(DSN) as c:
                c.execute("SELECT 1")
            break
        except Exception:
            time.sleep(0.5)
    else:
        raise AssertionError("postgres khong san sang sau 30s")

    with s.conn() as c:  # QUERY ĐẦU TIÊN sau restart — phải thành công ngay
        row = c.execute("SELECT 1").fetchone()
    assert row == (1,), "pool phai thay connection chet trong pool, khong nem ra caller"
