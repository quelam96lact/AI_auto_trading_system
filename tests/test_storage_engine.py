from datetime import date, datetime

import pytest

from tests.conftest import TEST_DSN
from trading.broker import Fill, Position
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.storage.db import Storage

DSN = TEST_DSN
pytestmark = pytest.mark.integration


@pytest.fixture
def storage():
    s = Storage(DSN)
    s.init_schema()
    with s.conn() as c:
        c.execute("DELETE FROM positions WHERE symbol = 'TEST'")
        c.execute("DELETE FROM bars_daily WHERE symbol IN ('TESTFRI', 'TESTOTH')")
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


def test_read_last_buy_date(storage):
    """Brief 96 Task 1a / Test 6:
    Đọc ngày mua gần nhất của mã từ bảng orders.
    - Không có lệnh BUY: trả về None.
    - Có lệnh BUY cũ: ngày 10/09/2026.
    - Có lệnh BUY mới hơn lúc 00:30 giờ VN ngày 15/09/2026 (UTC là 17:30 ngày 14/09).
      Bắt buộc trả về đúng ngày 15/09/2026 giờ VN (bắt bẫy múi giờ).
    - Có lệnh SELL sau đó (16/09/2026): hàm chỉ lấy BUY gần nhất nên vẫn trả 15/09/2026.
    """
    assert storage.read_last_buy_date("TEST") is None

    # BUY 1: 10/09/2026 10:00 VN
    f1 = Fill("TEST", "BUY", 100, 10.0, 10.0, datetime(2026, 9, 10, 10, 0, tzinfo=TZ))
    storage.write_order(f1)
    assert storage.read_last_buy_date("TEST") == date(2026, 9, 10)

    # BUY 2: 00:30 VN ngày 15/09/2026 (17:30 UTC ngày 14/09/2026)
    f2 = Fill("TEST", "BUY", 100, 10.5, 10.0, datetime(2026, 9, 15, 0, 30, tzinfo=TZ))
    storage.write_order(f2)
    assert storage.read_last_buy_date("TEST") == date(2026, 9, 15)

    # SELL: 16/09/2026 (không phải BUY)
    f_sell = Fill("TEST", "SELL", 100, 11.0, 10.0, datetime(2026, 9, 16, 14, 0, tzinfo=TZ), pnl=50.0)
    storage.write_order(f_sell)
    assert storage.read_last_buy_date("TEST") == date(2026, 9, 15)


def test_read_daily_bar_dates_tra_ngay_vn(storage):
    """Dot 97: nen daily luu 00:00 VN (= 17:00 UTC hom truoc). Ham phai tra NGAY VN,
    va chi trong [start, end). ts::date se tra thu Nam cho nen thu Sau."""
    bars = [
        Bar("TESTFRI", datetime(2026, 9, 18, 0, 0, tzinfo=TZ), 1, 1, 1, 1, 10),  # thu Sau
        Bar("TESTFRI", datetime(2026, 9, 25, 0, 0, tzinfo=TZ), 1, 1, 1, 1, 10),  # thu Sau, = end
        Bar("TESTOTH", datetime(2026, 9, 18, 0, 0, tzinfo=TZ), 1, 1, 1, 1, 10),
    ]
    storage.write_daily(bars)
    out = storage.read_daily_bar_dates(["TESTFRI"], date(2026, 9, 1), date(2026, 9, 25))
    assert out == {"TESTFRI": [date(2026, 9, 18)]}

