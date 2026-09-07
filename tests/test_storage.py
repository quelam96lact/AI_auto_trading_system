from datetime import date, datetime, timedelta

import pytest

from tests.conftest import TEST_DSN
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.storage.db import RealPosition, Storage

DSN = TEST_DSN
pytestmark = pytest.mark.integration


def test_conn_default_timeout_unchanged(monkeypatch):
    """WARM-1 Viec B: conn() khong truyen timeout -> connection(timeout=None) —
    dung hanh vi cu (pool 30s). Timeout ngan CHI khi caller chu dong truyen.
    Day la dieu kien khiến ban kinh anh huong cua thay doi bang 0 (khong dong
    duong dat lenh that / moi caller cu)."""
    import trading.storage.db as db_mod

    calls = []

    class FakePool:
        def connection(self, timeout=None):
            calls.append(timeout)

            class FakeConn:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

            return FakeConn()

    monkeypatch.setattr(db_mod, "_get_pool", lambda dsn: FakePool())
    s = Storage("postgresql://x:x@127.0.0.1:1/x")  # khong ket noi that — pool gia
    with s.conn():
        pass
    with s.conn(timeout=5):
        pass
    assert calls == [None, 5], f"mac dinh phai giu None (hanh vi cu), thuc te: {calls}"


@pytest.fixture
def storage():
    s = Storage(DSN)
    s.init_schema()
    with s.conn() as c:
        c.execute("DELETE FROM bars WHERE symbol = 'TEST'")
        c.execute("DELETE FROM account_balance_snapshot WHERE account_no = 'ACC_TEST'")
        c.execute("DELETE FROM account_position_snapshot WHERE account_no IN ('ACC_TEST', 'ACC_TEST2')")
        c.execute("DELETE FROM account_sync_log WHERE account_no IN ('ACC_TEST', 'ACC_TEST2')")
        c.execute("DELETE FROM pending_real_orders WHERE account_no = 'ACC_TEST'")
        c.execute("DELETE FROM real_order_fills WHERE account_no = 'ACC_TEST'")
        c.execute("DELETE FROM real_risk_state WHERE id = 1")
        c.execute("DELETE FROM backtest_runs")  # cascade xoa equity/fills
        c.execute("DELETE FROM account_buying_power WHERE account_no = 'ACC_TEST'")
        c.execute("DELETE FROM account_position_snapshot WHERE account_no IN ('ACC_TEST', 'ACC_TEST2')")
        c.execute("DELETE FROM account_sync_log WHERE account_no IN ('ACC_TEST', 'ACC_TEST2')")
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


def test_read_real_daily_pnl_filters_by_effective_status(storage):
    day = datetime(2026, 7, 15, 10, 0, tzinfo=TZ)
    storage.write_real_order_fill(
        account_no="ACC_TEST",
        ts=day,
        symbol="VCB",
        side="SELL",
        qty=100,
        price=55000.0,
        fee=10.0,
        pnl=100.0,
        ssi_order_id="SSI-P1",
        status="placed",
    )
    storage.write_real_order_fill(
        account_no="ACC_TEST",
        ts=day + timedelta(minutes=30),
        symbol="HPG",
        side="SELL",
        qty=50,
        price=21000.0,
        fee=5.0,
        pnl=200.0,
        ssi_order_id="SSI-F1",
        status="filled",
    )
    storage.write_real_order_fill(
        account_no="ACC_TEST",
        ts=day + timedelta(hours=1),
        symbol="MSN",
        side="SELL",
        qty=20,
        price=70000.0,
        fee=5.0,
        pnl=9999.0,
        ssi_order_id="SSI-C1",
        status="cancelled",
    )
    assert storage.read_real_daily_pnl("ACC_TEST", day.date()) == 300.0


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


def test_pool_replaces_dead_connection_before_handing_out():
    """Pool phải thay connection ĐÃ CHẾT trong pool, không đưa ra caller.

    Regression: pool không check connection -> đưa connection BAD ra caller ->
    query sau khi connection bị giết FAIL (AdminShutdown), chỉ lần 2 mới OK.
    Trước khi có pool mỗi query tự mở connection mới nên query kế tiếp thành
    công NGAY — mất đi hiệu quả đó là regression không chấp nhận được
    (persist_bars -> alert CRITICAL mất 1 nến; persist_fills trong try của
    engine -> term() mất 1 fill; mỗi blip mạng/postgres restart mất 1 nến/lệnh).

    Giết connection bằng pg_terminate_backend(pid) — pid của CHÍNH connection
    pool vừa trả về, KHÔNG giết mọi connection của DB (bài học flaky: bản đầu
    giết TẤT CẢ connection tới DB trading -> phá các test khác trong suite,
    cả lần chạy sau — vì pool connection của chính process đang bị giết giữa
    lúc pool đang cầm chúng)."""
    import psycopg

    s = Storage(DSN)
    with s.conn() as c:
        pid = c.execute("SELECT pg_backend_pid()").fetchone()[0]
        # connection vừa dùng được trả về pool khi thoát block — giờ giết nó

    with psycopg.connect(DSN) as killer:
        killer.execute("SELECT pg_terminate_backend(%s)", (pid,))

    with s.conn() as c:  # query NGAY sau đó — phải thành công ở LẦN ĐẦU
        row = c.execute("SELECT 1").fetchone()
    assert row == (1,), "pool phai thay connection chet trong pool, khong nem ra caller"

# ============ SYNC-LOG-1 Phan 1: account_sync_log ============


def _seed_snapshot(storage, account, ts, symbols):
    """Ghi mot lo anh chup (dung save_account_positions — cac test goi
    record_position_sync rieng de kiem soat)."""
    storage.save_account_positions(
        account, ts, [
            {"symbol": s, "quantity": q, "cost_price": 100.0, "sellable_quantity": q}
            for s, q in symbols
        ]
    )


def test_real_positions_empty_after_sync_with_empty_portfolio(storage):
    """SYNC-LOG-1 kiem chung 1 (ca gay — trong tam): dong bo VCB 1500 -> dong
    bo lan 2 RONG -> read_real_positions tra {} (truoc day max(ts) dung o lan
    cu -> VCB 1500 VINH VIEN, nhanh SELL sinh lenh ban co phieu khong ton tai).
    RED bat buoc: bo record_position_sync trong _sync_positions (production)
    -> tra VCB 1500 nhu cu. Seed QUA _sync_positions (production path) chu
    khong goi record truc tiep — neu khong, test khong chung minh duoc gi."""
    import asyncio
    from types import SimpleNamespace

    from trading.collector.account_sync import _sync_positions

    async def _run():
        ts1 = datetime(2026, 7, 15, 10, 0, tzinfo=TZ)
        ts2 = ts1 + timedelta(minutes=35)

        async def _with_vcb():
            return [
                SimpleNamespace(symbol="VCB", quantity=1500, cost_price=100.0, sellable_quantity=1500)
            ]

        async def _empty():
            return None  # SDK: danh muc rong tra None

        portfolio1 = SimpleNamespace(get_equity_positions=lambda a: _with_vcb())
        await _sync_positions(portfolio1, "ACC_TEST", ts1, storage)
        portfolio2 = SimpleNamespace(get_equity_positions=lambda a: _empty())
        await _sync_positions(portfolio2, "ACC_TEST", ts2, storage)

        return storage.read_real_positions("ACC_TEST")

    pos = asyncio.run(_run())
    assert pos == {}


def test_real_positions_follow_latest_sync(storage):
    """SYNC-LOG-1 kiem chung 2 (khong pha ca thuong): dong bo VCB+HPG -> dong
    bo chi con VCB -> read tra dung VCB, khong con HPG."""
    ts1 = datetime(2026, 7, 15, 10, 0, tzinfo=TZ)
    ts2 = ts1 + timedelta(minutes=35)
    _seed_snapshot(storage, "ACC_TEST", ts1, [("VCB", 1500), ("HPG", 1000)])
    storage.record_position_sync("ACC_TEST", ts1)
    _seed_snapshot(storage, "ACC_TEST", ts2, [("VCB", 1500)])
    storage.record_position_sync("ACC_TEST", ts2)
    pos = storage.read_real_positions("ACC_TEST")
    assert set(pos.keys()) == {"VCB"}
    assert pos["VCB"].qty == 1500


def test_real_positions_fallback_when_no_sync_record(storage):
    """SYNC-LOG-1 kiem chung 3 (fallback co chu dich): co dong snapshot nhung
    KHONG co ban ghi account_sync_log (bang moi them, du lieu cu) -> van tra
    nhu hanh vi cu max(ts) — khong doi ket qua dot ngot, tu khoi sau lan dong
    bo dau tien."""
    ts1 = datetime(2026, 7, 15, 10, 0, tzinfo=TZ)
    _seed_snapshot(storage, "ACC_TEST", ts1, [("VCB", 1500)])
    # KHONG goi record_position_sync
    pos = storage.read_real_positions("ACC_TEST")
    assert set(pos.keys()) == {"VCB"}
    assert pos["VCB"].qty == 1500


# ============ SYNC-LOG-1 Phan 2: load_ssi_token timeout ============


def test_load_ssi_token_default_timeout_unchanged(monkeypatch):
    """SYNC-LOG-1 Phan 2 kiem chung 1: load_ssi_token() khong truyen ->
    connection(timeout=None) (hanh vi cu); truyen 5 -> 5. Cung khuon mau test
    conn/beat da co."""
    import trading.storage.db as db_mod

    calls = []

    class FakePool:
        def connection(self, timeout=None):
            calls.append(timeout)

            class FakeConn:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def execute(self, *a, **k):
                    class R:
                        def fetchone(self):
                            return None
                    return R()

            return FakeConn()

    monkeypatch.setattr(db_mod, "_get_pool", lambda dsn: FakePool())
    s = Storage("postgresql://x:x@127.0.0.1:1/x")  # khong ket noi that — pool gia
    s.load_ssi_token()
    s.load_ssi_token(timeout=5)
    assert calls == [None, 5], f"mac dinh phai giu None (hanh vi cu), thuc te: {calls}"


# ============ MARGIN-1 (phan 1): NAV + suc mua ============


def _nav_now():
    return datetime(2026, 8, 14, 15, 0, tzinfo=TZ)


def test_compute_nav_fresh_price():
    """MARGIN-1 kiem chung 1a: vi the co gia TUOI -> tinh dung vao NAV."""
    nav, unpriced = Storage.compute_nav(
        100_000.0, 10_000.0, {"VCB": 100},
        lambda sym: (90.0, datetime(2026, 8, 14, tzinfo=TZ)),
        _nav_now(),
    )
    assert nav == 100_000.0 - 10_000.0 + 100 * 90.0
    assert unpriced == []


def test_compute_nav_missing_price_zero_and_warned():
    """MARGIN-1 kiem chung 1b: ma KHONG CO GIA -> tinh 0 + co trong danh sach."""
    nav, unpriced = Storage.compute_nav(
        100_000.0, 0.0, {"MIRHCM261": 1000},
        lambda sym: None,
        _nav_now(),
    )
    assert nav == 100_000.0
    assert unpriced == ["MIRHCM261"]


def test_compute_nav_stale_price_zero_and_warned():
    """MARGIN-1 kiem chung 1c: ma gia QUA CU (> 5 ngay giao dich) -> tinh 0 +
    co trong danh sach."""
    nav, unpriced = Storage.compute_nav(
        100_000.0, 0.0, {"CAP": 100},
        lambda sym: (20.0, datetime(2026, 8, 6, tzinfo=TZ)),  # cu 8 ngay
        _nav_now(),
    )
    assert nav == 100_000.0
    assert unpriced == ["CAP"]


def test_compute_nav_fresh_price_within_threshold():
    """Gia moi (khong qua cu) van tinh — ca phan biet voi stale."""
    nav, unpriced = Storage.compute_nav(
        100_000.0, 0.0, {"VCB": 100},
        lambda sym: (90.0, datetime(2026, 8, 13, tzinfo=TZ)),  # cu 1 ngay
        _nav_now(),
    )
    assert nav == 100_000.0 + 9_000.0
    assert unpriced == []


def test_parse_margin_ratio_variants():
    """MARGIN-1 kiem chung 4: '50%' -> 50.0; dang la -> None (khong doan)."""
    assert Storage.parse_margin_ratio("50%") == 50.0
    assert Storage.parse_margin_ratio("0%") == 0.0
    assert Storage.parse_margin_ratio("abc") is None
    assert Storage.parse_margin_ratio(None) is None


# ============ backtest-grafana: bang backtest_runs / equity / fills ============


def test_save_and_read_backtest_run(storage):
    """Ghi 1 dong backtest_runs -> doc lai dung cac truong; run_id tu tang."""
    rid1 = storage.save_backtest_run(
        symbol="VCB", strategy="daily_breakout", timeframe="1d",
        frm=date(2020, 1, 1), to_date=date(2020, 12, 31),
        capital=100_000_000.0, realized_pnl=12_345.0, unrealized_pnl=0.0,
        buy_and_hold_pnl=50_000.0, max_drawdown=0.05, win_rate=0.6,
        trades=10, filtered_bars={"VCB": 3},
    )
    rid2 = storage.save_backtest_run(
        symbol="HPG", strategy="octopus_pullback", timeframe="1d",
        frm=date(2020, 1, 1), to_date=date(2020, 12, 31),
        capital=100_000_000.0, realized_pnl=-1_000.0, unrealized_pnl=0.0,
        buy_and_hold_pnl=20_000.0, max_drawdown=0.1, win_rate=0.3,
        trades=5, filtered_bars={},
    )
    assert rid2 > rid1, "run_id phai tu tang"
    runs = storage.read_backtest_runs()
    assert len(runs) == 2
    row = next(r for r in runs if r["run_id"] == rid2)
    assert row["symbol"] == "HPG"
    assert row["strategy"] == "octopus_pullback"
    assert row["timeframe"] == "1d"
    assert row["realized_pnl"] == -1_000.0
    assert row["buy_and_hold_pnl"] == 20_000.0
    assert row["win_rate"] == 0.3
    assert row["trades"] == 5
    assert row["filtered_bars"] == 0  # dict rong -> 0


def test_save_and_read_backtest_equity(storage):
    """Duong von ghi theo run_id, doc lai dung thu tu (ts, equity)."""
    rid = storage.save_backtest_run(
        symbol="VCB", strategy="daily_breakout", timeframe="1d",
        frm=date(2020, 1, 1), to_date=date(2020, 12, 31),
        capital=100_000_000.0, realized_pnl=0.0, unrealized_pnl=0.0,
        buy_and_hold_pnl=0.0, max_drawdown=0.0, win_rate=0.0,
        trades=0, filtered_bars={},
    )
    ts0 = datetime(2020, 1, 2, 9, 0, tzinfo=TZ)
    ts1 = ts0 + timedelta(days=1)
    storage.save_backtest_equity(
        rid,
        [(ts0, 100_000_000.0), (ts1, 101_000_000.0)],
        [(ts0, 100_000_000.0), (ts1, 99_000_000.0)],
    )
    curve = storage.read_backtest_equity(rid)
    assert curve == [
        (ts0, 100_000_000.0, 100_000_000.0),
        (ts1, 101_000_000.0, 99_000_000.0),
    ]


def test_backtest_equity_rejects_mismatched_buy_and_hold_curve(storage):
    """Hai duong phai cung so diem. Neu lech -> ValueError chu KHONG ghi lech
    roi de Grafana ve chong sai moc."""
    import pytest

    rid = storage.save_backtest_run(
        symbol="VCB", strategy="daily_breakout", timeframe="1d",
        frm=date(2020, 1, 1), to_date=date(2020, 12, 31),
        capital=100_000_000.0, realized_pnl=0.0, unrealized_pnl=0.0,
        buy_and_hold_pnl=0.0, max_drawdown=0.0, win_rate=0.0,
        trades=0, filtered_bars={},
    )
    ts0 = datetime(2020, 1, 2, 9, 0, tzinfo=TZ)
    with pytest.raises(ValueError, match="cung moc ts"):
        storage.save_backtest_equity(
            rid,
            [(ts0, 1.0), (ts0 + timedelta(days=1), 2.0)],
            [(ts0, 1.0)],
        )


def test_save_and_read_backtest_fills(storage):
    """Lenh ghi theo run_id, doc lai dung side/qty/price/fee."""
    from trading.broker import Fill

    rid = storage.save_backtest_run(
        symbol="VCB", strategy="daily_breakout", timeframe="1d",
        frm=date(2020, 1, 1), to_date=date(2020, 12, 31),
        capital=100_000_000.0, realized_pnl=0.0, unrealized_pnl=0.0,
        buy_and_hold_pnl=0.0, max_drawdown=0.0, win_rate=0.0,
        trades=0, filtered_bars={},
    )
    ts = datetime(2020, 1, 5, 9, 0, tzinfo=TZ)
    storage.save_backtest_fills(rid, [
        Fill("VCB", "BUY", 100, 20_000.0, 12_000.0, ts),
        Fill("VCB", "SELL", 100, 21_000.0, 12_600.0, ts + timedelta(days=3), pnl=88_000.0),
    ])
    fills = storage.read_backtest_fills(rid)
    assert len(fills) == 2
    # row = (ts, side, qty, price, fee) — khuon plan: backtest_fills khong co pnl
    assert fills[0][1] == "BUY" and fills[0][2] == 100 and fills[0][3] == 20_000.0
    assert fills[1][1] == "SELL" and fills[1][3] == 21_000.0


# ============ real-order-sizing: read_buying_power tra them moc thoi gian ============


def test_read_buying_power_returns_latest_ts(storage):
    """Plan 2026-09-01 T1-B1: ghi 2 dong cung (account, symbol) khac ts,
    doc ra phai la dong MOI NHAT kem dung ts (de engine tinh tuoi sức mua)."""
    ts1 = datetime(2026, 9, 1, 9, 0, tzinfo=TZ)
    ts2 = datetime(2026, 9, 1, 9, 5, tzinfo=TZ)
    storage.record_buying_power("ACC_TEST", "VCB", ts1, 1000, 500, 50.0)
    storage.record_buying_power("ACC_TEST", "VCB", ts2, 800, 600, 40.0)

    got = storage.read_buying_power("ACC_TEST", "VCB")
    assert got == (800, 600, 40.0, ts2), f"phai la dong moi nhat kem ts, thuc te: {got}"


def test_read_buying_power_none_when_no_row(storage):
    """Khong co dong nao -> None (khong phai tuple gia gia)."""
    assert storage.read_buying_power("ACC_TEST", "VCB") is None


# ============ brief 2026-09-01 dot 2: tach hai vai cua is_active ============


def test_read_must_price_symbols_union_of_all_sources(storage):
    """B1 (a): read_must_price_symbols = extra hop voi ma dang nam giu cua
    TUNG tai khoan — ca ba nguon deu co mat."""
    ts = datetime(2026, 9, 1, 9, 0, tzinfo=TZ)
    # Tai khoan 1 nam VCB + CAP; tai khoan 2 nam SSI
    storage.record_position_sync("ACC_TEST", ts)
    storage.save_account_positions(
        "ACC_TEST", ts, [
            {"symbol": "VCB", "quantity": 100, "cost_price": 10.0, "sellable_quantity": 100},
            {"symbol": "CAP", "quantity": 50, "cost_price": 5.0, "sellable_quantity": 0},
        ],
    )
    storage.record_position_sync("ACC_TEST2", ts)
    storage.save_account_positions(
        "ACC_TEST2", ts, [
            {"symbol": "SSI", "quantity": 200, "cost_price": 20.0, "sellable_quantity": 200},
        ],
    )
    got = storage.read_must_price_symbols(["ACC_TEST", "ACC_TEST2"], ["HII"])
    assert got == ["CAP", "HII", "SSI", "VCB"], f"hop ca 3 nguon, sap xep, thuc te: {got}"


def test_read_must_price_symbols_deduplicates(storage):
    """B1 (b): cung ma xuat hien o ca extra lan vi the -> chi 1 lan."""
    ts = datetime(2026, 9, 1, 9, 0, tzinfo=TZ)
    storage.record_position_sync("ACC_TEST", ts)
    storage.save_account_positions(
        "ACC_TEST", ts, [{"symbol": "HII", "quantity": 100, "cost_price": 10.0, "sellable_quantity": 100}],
    )
    got = storage.read_must_price_symbols(["ACC_TEST"], ["HII"])
    assert got == ["HII"], f"khong trung lap, thuc te: {got}"


def test_read_must_price_symbols_excludes_zero_qty(storage):
    """B1 (c): ma DA BAN HET (quantity=0 VA cost_price=0) KHONG xuat hien.

    DOI Y NGHIA ngay 04/09 (goi H). Ban truoc cua test nay seed VCB
    `quantity=0, cost_price=10.0` roi khang dinh phai loai — tuc la no khang
    dinh dung cai loi H sinh ra: ma vua mua, dang trong cua so thanh toan T+2,
    bi loai khoi danh sach bat buoc co gia dung nhung ngay no can nhat (FOX,
    5 phien). Dieu kien loai bay gio la `cost_price = 0` chu khong phai
    `quantity = 0`. Truong hop cost_price > 0 do test ..._includes_unsettled
    ngay duoi phu trach.
    """
    ts = datetime(2026, 9, 1, 9, 0, tzinfo=TZ)
    storage.record_position_sync("ACC_TEST", ts)
    storage.save_account_positions(
        "ACC_TEST", ts, [
            {"symbol": "VCB", "quantity": 0, "cost_price": 0.0, "sellable_quantity": 0},
            {"symbol": "CAP", "quantity": 50, "cost_price": 5.0, "sellable_quantity": 50},
        ],
    )
    got = storage.read_must_price_symbols(["ACC_TEST"], [])
    assert got == ["CAP"], f"ma da ban het phai bi loai, thuc te: {got}"


# ============ goi H (04/09): ma trong cua so thanh toan phai co gia ============


def test_read_must_price_symbols_includes_unsettled_buy(storage):
    """H tieu chi 1+2: tai hien dung canh FOX — mua 28/08, T+2 chua ve nen
    `quantity = 0` nhung `cost_price = 65000`. Ma nay PHAI nam trong danh sach
    bat buoc co gia, neu khong backfill dem bo qua no va NAV dung gia cu."""
    ts = datetime(2026, 9, 1, 9, 0, tzinfo=TZ)
    storage.record_position_sync("ACC_TEST", ts)
    storage.save_account_positions(
        "ACC_TEST", ts, [
            {"symbol": "FOX", "quantity": 0, "cost_price": 65000.0, "sellable_quantity": 0},
            {"symbol": "CAP", "quantity": 0, "cost_price": 0.0, "sellable_quantity": 0},
            {"symbol": "VCB", "quantity": 1500, "cost_price": 60706.0, "sellable_quantity": 1500},
        ],
    )
    got = storage.read_must_price_symbols(["ACC_TEST"], [])
    assert got == ["FOX", "VCB"], (
        f"FOX (chua ve, cost_price>0) phai co; CAP (da ban, cost_price=0) khong "
        f"duoc co. Thuc te: {got}"
    )


def test_read_real_positions_mac_dinh_van_loai_ma_chua_ve(storage):
    """H tieu chi 3 — QUAN TRONG NGANG tieu chi 2.

    `read_real_positions` MAC DINH phai giu nguyen hanh vi cu: loai het
    `quantity = 0`, KE CA khi cost_price > 0. Bay chỗ gọi con lai dua vao dieu
    nay, trong do real_orders.py:42,174 la duong dat lenh THAT — neu ma chua ve
    lot vao day thi nhanh SELL sinh lenh ban co phieu chua co trong tai khoan.
    """
    ts = datetime(2026, 9, 1, 9, 0, tzinfo=TZ)
    storage.record_position_sync("ACC_TEST", ts)
    storage.save_account_positions(
        "ACC_TEST", ts, [
            {"symbol": "FOX", "quantity": 0, "cost_price": 65000.0, "sellable_quantity": 0},
            {"symbol": "VCB", "quantity": 1500, "cost_price": 60706.0, "sellable_quantity": 1500},
        ],
    )
    mac_dinh = storage.read_real_positions("ACC_TEST")
    assert "FOX" not in mac_dinh, (
        "ma chua ve KHONG duoc hien ra o hanh vi mac dinh — duong SELL that doc "
        f"ham nay. Thuc te: {sorted(mac_dinh)}"
    )
    assert "VCB" in mac_dinh

    # chi khi bat co moi thay — va qty van la 0, khong bia so
    co_bat = storage.read_real_positions("ACC_TEST", include_unsettled=True)
    assert "FOX" in co_bat
    assert co_bat["FOX"].qty == 0
    assert co_bat["FOX"].sellable_qty == 0


def test_read_real_positions_unsettled_khong_keo_ma_da_ban_ve(storage):
    """Ranh gioi song con: bat include_unsettled KHONG duoc lam ma da ban het
    (cost_price = 0) song lai. Doi chung am do duoc tren du lieu that 04/09:
    CAP va MIRHCM261 deu quantity=0, cost_price=0."""
    ts = datetime(2026, 9, 1, 9, 0, tzinfo=TZ)
    storage.record_position_sync("ACC_TEST", ts)
    storage.save_account_positions(
        "ACC_TEST", ts, [
            {"symbol": "CAP", "quantity": 0, "cost_price": 0.0, "sellable_quantity": 0},
            {"symbol": "MIRHCM261", "quantity": 0, "cost_price": 0.0, "sellable_quantity": 0},
            {"symbol": "FOX", "quantity": 0, "cost_price": 65000.0, "sellable_quantity": 0},
        ],
    )
    co_bat = storage.read_real_positions("ACC_TEST", include_unsettled=True)
    assert sorted(co_bat) == ["FOX"], (
        f"chi ma co gia von moi duoc keo ve, thuc te: {sorted(co_bat)}"
    )


def test_read_must_price_symbols_unsynced_account_no_crash(storage):
    """B1 (d): tai khoan CHUA TUNG dong bo (khong co account_sync_log) ->
    khong lam ham no, chi bo qua tai khoan do."""
    ts = datetime(2026, 9, 1, 9, 0, tzinfo=TZ)
    # Chi seed ACC_TEST, khong seed ACC_UNSYNCED
    storage.record_position_sync("ACC_TEST", ts)
    storage.save_account_positions(
        "ACC_TEST", ts, [{"symbol": "VCB", "quantity": 100, "cost_price": 10.0, "sellable_quantity": 100}],
    )
    got = storage.read_must_price_symbols(["ACC_TEST", "ACC_UNSYNCED"], ["AAA"])
    assert got == ["AAA", "VCB"], f"tai khoan chua dong bo phai duoc bo qua, thuc te: {got}"
