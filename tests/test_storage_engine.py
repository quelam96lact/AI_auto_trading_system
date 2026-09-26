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
        c.execute("DELETE FROM real_order_fills WHERE account_no = 'ACC_RECONCILE_TEST'")
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


def test_8_update_real_order_fill_on_filled_is_noop(storage):
    """8. update_real_order_fill trên dòng đã 'filled' -> 0 dòng bị ảnh hưởng, dữ liệu không đổi."""
    ts = datetime(2026, 9, 26, 10, 0, tzinfo=TZ)
    account_no = "ACC_RECONCILE_TEST"
    storage.write_real_order_fill(
        account_no=account_no,
        ts=ts,
        symbol="HPG",
        side="BUY",
        qty=100,
        price=25000.0,
        fee=625.0,
        pnl=None,
        ssi_order_id="SSI-RECON-8",
        status="filled",
    )
    # Tìm id vừa tạo
    with storage.conn() as c:
        row = c.execute("SELECT id, status, qty, price, fee, pnl FROM real_order_fills WHERE ssi_order_id = 'SSI-RECON-8'").fetchone()
        fill_id = row[0]

    affected = storage.update_real_order_fill(
        id=fill_id,
        status="cancelled",
        qty=0,
        price=0.0,
        fee=0.0,
        pnl=0.0,
    )
    assert affected == 0

    # Dữ liệu trong DB không đổi
    with storage.conn() as c:
        updated_row = c.execute("SELECT status, qty, price, fee, pnl FROM real_order_fills WHERE id = %s", (fill_id,)).fetchone()
        assert updated_row[0] == "filled"
        assert updated_row[1] == 100
        assert updated_row[2] == 25000.0
        assert updated_row[3] == 625.0
        assert updated_row[4] is None


def test_9_update_real_order_fill_cancelled_excludes_from_daily_pnl(storage):
    """9. Sau khi một dòng BÁN chuyển 'cancelled', read_real_daily_pnl của ngày đó không còn tính pnl của nó."""
    ts = datetime(2026, 9, 26, 11, 0, tzinfo=TZ)
    account_no = "ACC_RECONCILE_TEST"
    storage.write_real_order_fill(
        account_no=account_no,
        ts=ts,
        symbol="HPG",
        side="SELL",
        qty=100,
        price=26000.0,
        fee=650.0,
        pnl=100000.0,
        ssi_order_id="SSI-RECON-9",
        status="placed",
    )
    # Ban đầu status='placed', nằm trong EFFECTIVE_FILL_STATUSES nên được tính pnl
    initial_pnl = storage.read_real_daily_pnl(account_no, ts.date())
    assert initial_pnl == 100000.0

    with storage.conn() as c:
        fill_id = c.execute("SELECT id FROM real_order_fills WHERE ssi_order_id = 'SSI-RECON-9'").fetchone()[0]

    # Cập nhật sang cancelled
    affected = storage.update_real_order_fill(
        id=fill_id,
        status="cancelled",
        qty=0,
        price=26000.0,
        fee=0.0,
        pnl=0.0,
    )
    assert affected == 1

    # read_real_daily_pnl không còn tính dòng này nữa
    after_pnl = storage.read_real_daily_pnl(account_no, ts.date())
    assert after_pnl == 0.0


def test_read_placed_real_fills_filters_correctly(storage):
    """Kiểm tra read_placed_real_fills chỉ trả về các dòng placed có ssi_order_id của đúng tài khoản."""
    ts = datetime(2026, 9, 26, 10, 0, tzinfo=TZ)
    acc = "ACC_RECONCILE_TEST"
    # Dòng 1: placed có ssi_order_id -> PHẢI ĐƯỢC CHỌN
    storage.write_real_order_fill(
        account_no=acc,
        ts=ts,
        symbol="HPG",
        side="BUY",
        qty=100,
        price=25000.0,
        fee=625.0,
        pnl=None,
        ssi_order_id="SSI-P-VALID",
        status="placed",
    )
    # Dòng 2: placed không có ssi_order_id -> BỊ LOẠI
    storage.write_real_order_fill(
        account_no=acc,
        ts=ts,
        symbol="HPG",
        side="BUY",
        qty=100,
        price=25000.0,
        fee=625.0,
        pnl=None,
        ssi_order_id=None,
        status="placed",
    )
    # Dòng 3: filled có ssi_order_id -> BỊ LOẠI
    storage.write_real_order_fill(
        account_no=acc,
        ts=ts,
        symbol="HPG",
        side="BUY",
        qty=100,
        price=25000.0,
        fee=625.0,
        pnl=None,
        ssi_order_id="SSI-F-OTHER",
        status="filled",
    )
    # Dòng 4: tài khoản khác -> BỊ LOẠI
    storage.write_real_order_fill(
        account_no="OTHER_ACC",
        ts=ts,
        symbol="HPG",
        side="BUY",
        qty=100,
        price=25000.0,
        fee=625.0,
        pnl=None,
        ssi_order_id="SSI-P-OTHERACC",
        status="placed",
    )

    placed = storage.read_placed_real_fills(acc)
    assert len(placed) == 1
    assert placed[0].ssi_order_id == "SSI-P-VALID"
    assert placed[0].account_no == acc
    assert placed[0].status == "placed"



