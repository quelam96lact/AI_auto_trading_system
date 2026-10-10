from datetime import datetime
from types import SimpleNamespace

import pytest
from ssi_sdk.enums.trading import OrderStatus
from ssi_sdk.models import Order

from trading.calendar_vn import TZ
from trading.collector import account_sync
from trading.storage.db import PlacedRealFill


class FakeRestClient:
    def __init__(self, raw):
        self.raw = raw
        self.calls = []

    async def get(self, endpoint, params):
        self.calls.append((endpoint, params))
        return self.raw


class FakeStorage:
    def __init__(self):
        self.balance_calls = []
        self.position_calls = []
        self.sync_recorded = []
        # CONFIRM-1: giả lập snapshot trước (mặc định: rỗng / None)
        self._prev_positions: dict = {}           # {account_no: {symbol: ...}}
        self._prev_balance: tuple | None = None   # (withdrawable, total_debt, ts) hoặc None

    def save_account_balance(self, **kwargs):
        self.balance_calls.append(kwargs)

    def save_account_positions(self, account_no, ts, positions):
        self.position_calls.append((account_no, ts, positions))

    def record_position_sync(self, account_no, ts):
        self.sync_recorded.append((account_no, ts))

    # MARGIN-1: stubs cho _sync_buying_power / _sync_nav trong sync_account_data
    def record_buying_power(self, account_no, symbol, ts, **kwargs):
        pass

    def record_nav(self, account_no, ts, nav, unpriced_symbols):
        pass

    def parse_margin_ratio(self, v):
        from trading.storage.db import Storage
        return Storage.parse_margin_ratio(v)

    def read_placed_real_fills(self, account_no):
        return []

    def update_real_order_fill(self, *a, **k):
        return 0

    # CONFIRM-1: stub cho _sync_positions
    def read_real_positions(self, account_no):
        return self._prev_positions.get(account_no, {})

    # CONFIRM-1: stub cho _sync_balance
    def read_account_balance_with_debt(self, account_no):
        return self._prev_balance


async def test_sync_balance_maps_real_api_fields():
    storage = FakeStorage()
    auth = SimpleNamespace(
        rest_client=FakeRestClient(
            {
                "equity": {
                    "accountBalance": "21459",
                    "totalDebt": "10",
                    "withdrawable": "21459",
                    "advancedCashT0": "1",
                    "advancedCashT1": "2",
                    "buyUnmatched": "3",
                    "sellUnmatched": "4",
                }
            }
        )
    )
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)

    await account_sync._sync_balance(auth, "043422", "0434221", ts, storage)

    assert storage.balance_calls == [
        {
            "account_no": "0434221",
            "ts": ts,
            "account_balance": 21459.0,
            "total_debt": 10.0,
            "withdrawable": 21459.0,
            "buy_unmatched": 3.0,
            "sell_unmatched": 4.0,
            "buy_t0": 0.0,
            "buy_t1": 0.0,
            "buy_t2": 0.0,
            "sell_t0": 0.0,
            "sell_t1": 0.0,
            "sell_t2": 0.0,
            "advanced_cash_t0": 1.0,
            "advanced_cash_t1": 2.0,
            "dividend_cash": 0.0,
        }
    ]


async def test_sync_balance_skips_missing_equity():
    storage = FakeStorage()
    auth = SimpleNamespace(rest_client=FakeRestClient({}))
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)

    await account_sync._sync_balance(auth, "043422", "0434228", ts, storage)

    assert storage.balance_calls == []


async def test_sync_balance_maps_all_9_pending_cash_fields():
    """Brief 167 vòng 2: _sync_balance maps all 9 pending cash fields from equity."""
    storage = FakeStorage()
    auth = SimpleNamespace(
        rest_client=FakeRestClient(
            {
                "equity": {
                    "accountBalance": "9595640",
                    "totalDebt": "42760",
                    "withdrawable": "9595640",
                    "buyUnmatched": "0",
                    "sellUnmatched": "0",
                    "buyT0": "100",
                    "buyT1": "200",
                    "buyT2": "23979800",
                    "sellT0": "300",
                    "sellT1": "400",
                    "sellT2": "500",
                    "advancedCashT0": "600",
                    "advancedCashT1": "700",
                    "dividend": "800",
                }
            }
        )
    )
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)

    await account_sync._sync_balance(auth, "043422", "0434226", ts, storage)

    assert storage.balance_calls == [
        {
            "account_no": "0434226",
            "ts": ts,
            "account_balance": 9595640.0,
            "total_debt": 42760.0,
            "withdrawable": 9595640.0,
            "buy_unmatched": 0.0,
            "sell_unmatched": 0.0,
            "buy_t0": 100.0,
            "buy_t1": 200.0,
            "buy_t2": 23979800.0,
            "sell_t0": 300.0,
            "sell_t1": 400.0,
            "sell_t2": 500.0,
            "advanced_cash_t0": 600.0,
            "advanced_cash_t1": 700.0,
            "dividend_cash": 800.0,
        }
    ]


async def test_sync_balance_missing_9_new_keys_still_writes_defaults(monkeypatch):
    """Brief 167 vòng 2: equity thiếu 9 key mới vẫn ghi với giá trị 0.0, không có cảnh báo mới."""
    storage = FakeStorage()
    alerts = []
    monkeypatch.setattr(
        account_sync, "alert", lambda level, msg, **f: alerts.append((level, msg, f))
    )
    auth = SimpleNamespace(
        rest_client=FakeRestClient(
            {
                "equity": {
                    "accountBalance": "10000000",
                    "totalDebt": "2000000",
                    "withdrawable": "5000000",
                }
            }
        )
    )
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)

    await account_sync._sync_balance(auth, "043422", "0434226", ts, storage)

    assert storage.balance_calls == [
        {
            "account_no": "0434226",
            "ts": ts,
            "account_balance": 10000000.0,
            "total_debt": 2000000.0,
            "withdrawable": 5000000.0,
            "buy_unmatched": 0.0,
            "sell_unmatched": 0.0,
            "buy_t0": 0.0,
            "buy_t1": 0.0,
            "buy_t2": 0.0,
            "sell_t0": 0.0,
            "sell_t1": 0.0,
            "sell_t2": 0.0,
            "advanced_cash_t0": 0.0,
            "advanced_cash_t1": 0.0,
            "dividend_cash": 0.0,
        }
    ]
    assert alerts == []


async def test_sync_positions_maps_position_fields():
    storage = FakeStorage()
    portfolio = SimpleNamespace(
        get_equity_positions=lambda account_no: _positions(
            SimpleNamespace(symbol="VCB", quantity=100, cost_price=88.5, sellable_quantity=80)
        )
    )
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)

    await account_sync._sync_positions(portfolio, "0434226", ts, storage)

    assert storage.position_calls == [
        (
            "0434226",
            ts,
            [
                {
                    "symbol": "VCB",
                    "quantity": 100,
                    "cost_price": 88.5,
                    "sellable_quantity": 80,
                    "bought_quantity": 0,
                    "buying_quantity": 0,
                    "sold_quantity": 0,
                    "selling_quantity": 0,
                    "t1_sell_quantity": 0,
                    "t2_sell_quantity": 0,
                    "dividend_quantity": 0,
                }
            ],
        )
    ]


async def test_sync_positions_maps_all_7_pending_quantity_fields():
    """Brief 167: _sync_positions maps all 7 pending quantity fields."""
    storage = FakeStorage()
    portfolio = SimpleNamespace(
        get_equity_positions=lambda account_no: _positions(
            SimpleNamespace(
                symbol="CTD",
                quantity=1200,
                cost_price=58858.0,
                sellable_quantity=800,
                bought_quantity=400,
                buying_quantity=10,
                sold_quantity=20,
                selling_quantity=30,
                t1_sell_quantity=40,
                t2_sell_quantity=100,
                dividend_quantity=50,
            )
        )
    )
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)

    await account_sync._sync_positions(portfolio, "0434226", ts, storage)

    assert storage.position_calls == [
        (
            "0434226",
            ts,
            [
                {
                    "symbol": "CTD",
                    "quantity": 1200,
                    "cost_price": 58858.0,
                    "sellable_quantity": 800,
                    "bought_quantity": 400,
                    "buying_quantity": 10,
                    "sold_quantity": 20,
                    "selling_quantity": 30,
                    "t1_sell_quantity": 40,
                    "t2_sell_quantity": 100,
                    "dividend_quantity": 50,
                }
            ],
        )
    ]


async def _positions(*positions):
    return list(positions)


async def test_sync_positions_handles_none_portfolio():
    """SYNC-1: SDK tra None cho danh muc rong (docstring portfolio.py:330-331:
    'absent or empty sections yield None') — None la trang thai HOP LE, khong
    duoc nem, khong duoc goi save_account_positions voi None. SYNC-LOG-1: van
    ghi record_position_sync (da dong bo va rong != chua dong bo — khong ghi
    thi vi the da ban ve VINH VIEN)."""
    storage = FakeStorage()

    async def _none():
        return None

    portfolio = SimpleNamespace(get_equity_positions=lambda account_no: _none())
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)

    await account_sync._sync_positions(portfolio, "0434221", ts, storage)

    assert storage.position_calls == [("0434221", ts, [])]  # save no-op voi rong
    assert storage.sync_recorded == [("0434221", ts)], (
        "phai ghi su kien dong bo CA KHI danh muc rong"
    )


async def test_sync_positions_not_recorded_when_fetch_raises():
    """SYNC-LOG-1 kiem chung 4: get_equity_positions nem exception -> KHONG
    ghi account_sync_log (ghi mot lan dong bo chua xay ra con te hon khong ghi
    — bien 'chua biet' thanh 'da biet va rong')."""
    storage = FakeStorage()

    async def _boom():
        raise RuntimeError("parse boom")

    portfolio = SimpleNamespace(get_equity_positions=lambda account_no: _boom())
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)

    with pytest.raises(RuntimeError):
        await account_sync._sync_positions(portfolio, "0434221", ts, storage)

    assert storage.sync_recorded == [], (
        f"fetch hong thi KHONG duoc ghi sync, thuc te: {storage.sync_recorded}"
    )
    assert storage.position_calls == []


async def test_sync_account_data_isolates_failing_account(monkeypatch):
    """SYNC-1: tai khoan thu nhat nem -> tai khoan thu hai VAN duoc sync day
    du, va co DUNG MOT WARN chua ma tai khoan hong. Do that 13/08: 0434221
    no -> 0434226 mat im lang ca balance lan position."""
    from types import SimpleNamespace as NS

    warns = []
    # account_sync import `from trading.alerts import alert` (tham chieu truc
    # tiep) -> monkeypatch tren account_sync, khong phai alerts_mod.
    monkeypatch.setattr(
        account_sync, "alert", lambda level, msg, **f: warns.append((level, msg, f.get("account_no")))
    )

    async def fake_auth(cfg, storage):
        return NS(
            token_manager=NS(access_token="tok"),
            config=NS(),
            rest_client=None,
            close=lambda: _noop(),
        )

    async def _noop():
        pass

    monkeypatch.setattr(account_sync, "ensure_authenticated", fake_auth)
    monkeypatch.setattr(account_sync, "decode_client_id", lambda tok: "043422")
    # AsyncPortfolioService duoc import CUC BO trong sync_account_data (dòng 12)
    # -> monkeypatch o module goc cua SDK, khong phai tren account_sync.
    import ssi_sdk.services.portfolio as sdk_portfolio

    monkeypatch.setattr(sdk_portfolio, "AsyncPortfolioService", lambda rc, cfg: NS())

    calls = {"balance": [], "positions": []}

    async def fake_balance(auth, client_id, account_no, ts, storage, *args, **kwargs):
        calls["balance"].append(account_no)
        if account_no == "ACC_BAD":
            raise RuntimeError("parse boom")

    async def fake_positions(portfolio, account_no, ts, storage, *args, **kwargs):
        calls["positions"].append(account_no)

    monkeypatch.setattr(account_sync, "_sync_balance", fake_balance)
    monkeypatch.setattr(account_sync, "_sync_positions", fake_positions)
    # MARGIN-1: 2 ham moi co test rieng (_sync_buying_power o test rieng, _sync_nav
    # o test_nav_vn_market_time.py) — o day no-op de chi kiem SYNC-1
    # (ky vong cua test cu KHONG doi: dung 1 WARN cho ACC_BAD)
    monkeypatch.setattr(account_sync, "_sync_buying_power", lambda *a, **k: _noop())
    monkeypatch.setattr(account_sync, "_sync_nav", lambda *a, **k: _noop())

    cfg = NS(
        ssi_equity_accounts=["ACC_BAD", "ACC_OK"], symbols=["HII"],
        holidays=frozenset(),  # goi A: _sync_nav doc cfg.holidays
    )
    await account_sync.sync_account_data(cfg, FakeStorage())

    assert calls["balance"] == ["ACC_BAD", "ACC_OK"], (
        f"tai khoan 2 van phai duoc sync balance, thuc te: {calls['balance']}"
    )
    assert calls["positions"] == ["ACC_OK"], (
        f"tai khoan 2 van phai duoc sync positions, thuc te: {calls['positions']}"
    )
    assert len(warns) == 1 and warns[0][2] == "ACC_BAD", (
        f"phai co dung 1 WARN chua ma tai khoan hong (ACC_BAD), thuc te: {warns}"
    )


async def test_sync_buying_power_isolates_failing_symbol(monkeypatch):
    """MARGIN-1 kiem chung 3: mot ma nem loi -> WARN + tiep tuc cac ma con lai,
    khong lam hong ca vong dong bo (cung khuon mau SYNC-1)."""
    from types import SimpleNamespace

    from trading.collector import account_sync

    recorded = []

    class FakeStorage:
        def record_buying_power(self, account_no, symbol, ts, **kwargs):
            recorded.append((account_no, symbol, kwargs["max_buy_qty"], kwargs["margin_ratio_pct"]))

        def parse_margin_ratio(self, v):
            from trading.storage.db import Storage
            return Storage.parse_margin_ratio(v)

    async def _get(self, account_no, symbol):
        if symbol == "IJC":
            raise RuntimeError("parse boom")
        return SimpleNamespace(
            max_buy_quantity=100, max_sell_quantity=50, margin_ratio="50%"
        )

    class FakeTrading:
        get_max_buy_sell_at_market_price = _get

    alerts = []
    monkeypatch.setattr(account_sync, "alert", lambda level, msg, **f: alerts.append((level, f.get("symbol"))))
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    await account_sync._sync_buying_power(FakeTrading(), "0434226", ts, ["HII", "IJC", "AAA"], FakeStorage())

    assert recorded == [("0434226", "HII", 100, 50.0), ("0434226", "AAA", 100, 50.0)], f"thuc te: {recorded}"
    assert ("WARN", "IJC") in alerts, f"phai WARN cho ma loi, thuc te: {alerts}"


# =====================================================================
# Brief 88 Task 2: Va loi so 0 im lang o dong bo tai khoan
# 7 nhom test
# =====================================================================


async def test_sync_balance_case1_all_fields_present_no_warn(monkeypatch):
    """Ca 1: equity du ba truong, withdrawable = 5021712 -> ghi dung gia tri, KHONG WARN."""
    storage = FakeStorage()
    alerts = []
    monkeypatch.setattr(
        account_sync, "alert", lambda level, msg, **f: alerts.append((level, msg, f))
    )
    auth = SimpleNamespace(
        rest_client=FakeRestClient(
            {
                "equity": {
                    "accountBalance": "10000000",
                    "totalDebt": "2000000",
                    "withdrawable": "5021712",
                }
            }
        )
    )
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    await account_sync._sync_balance(auth, "043422", "0434221", ts, storage)

    assert len(storage.balance_calls) == 1
    call = storage.balance_calls[0]
    assert call["account_balance"] == 10000000.0
    assert call["total_debt"] == 2000000.0
    assert call["withdrawable"] == 5021712.0
    assert alerts == []


async def test_sync_balance_case2_missing_key_withdrawable(monkeypatch):
    """Ca 2: equity thieu khoa withdrawable -> KHONG ghi, co dung 1 WARN neu ten withdrawable."""
    storage = FakeStorage()
    alerts = []
    monkeypatch.setattr(
        account_sync, "alert", lambda level, msg, **f: alerts.append((level, msg, f))
    )
    auth = SimpleNamespace(
        rest_client=FakeRestClient(
            {
                "equity": {
                    "accountBalance": "10000000",
                    "totalDebt": "2000000",
                }
            }
        )
    )
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    await account_sync._sync_balance(auth, "043422", "0434221", ts, storage)

    assert storage.balance_calls == []
    assert len(alerts) == 1
    level, msg, fields = alerts[0]
    assert level == "WARN"
    assert "withdrawable" in str(fields.get("missing_fields")) or "withdrawable" in msg
    assert fields.get("account_no") == "0434221"


async def test_sync_balance_case3_withdrawable_is_none(monkeypatch):
    """Ca 3: equity co withdrawable = None -> nhu ca 2 (KHONG ghi, co dung 1 WARN neu ten withdrawable)."""
    storage = FakeStorage()
    alerts = []
    monkeypatch.setattr(
        account_sync, "alert", lambda level, msg, **f: alerts.append((level, msg, f))
    )
    auth = SimpleNamespace(
        rest_client=FakeRestClient(
            {
                "equity": {
                    "accountBalance": "10000000",
                    "totalDebt": "2000000",
                    "withdrawable": None,
                }
            }
        )
    )
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    await account_sync._sync_balance(auth, "043422", "0434221", ts, storage)

    assert storage.balance_calls == []
    assert len(alerts) == 1
    level, msg, fields = alerts[0]
    assert level == "WARN"
    assert "withdrawable" in str(fields.get("missing_fields")) or "withdrawable" in msg
    assert fields.get("account_no") == "0434221"


async def test_sync_balance_case4_withdrawable_is_empty_string(monkeypatch):
    """Ca 4: equity co withdrawable = "" -> nhu ca 2 (KHONG ghi, co dung 1 WARN neu ten withdrawable)."""
    storage = FakeStorage()
    alerts = []
    monkeypatch.setattr(
        account_sync, "alert", lambda level, msg, **f: alerts.append((level, msg, f))
    )
    auth = SimpleNamespace(
        rest_client=FakeRestClient(
            {
                "equity": {
                    "accountBalance": "10000000",
                    "totalDebt": "2000000",
                    "withdrawable": "",
                }
            }
        )
    )
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    await account_sync._sync_balance(auth, "043422", "0434221", ts, storage)

    assert storage.balance_calls == []
    assert len(alerts) == 1
    level, msg, fields = alerts[0]
    assert level == "WARN"
    assert "withdrawable" in str(fields.get("missing_fields")) or "withdrawable" in msg
    assert fields.get("account_no") == "0434221"


async def test_sync_balance_case5_legitimate_zeros_recorded_no_warn(monkeypatch):
    """Ca 5 (de sai nhat): withdrawable = 0 va totalDebt = 0 (so 0 THAT) -> ghi binh thuong, KHONG WARN."""
    storage = FakeStorage()
    alerts = []
    monkeypatch.setattr(
        account_sync, "alert", lambda level, msg, **f: alerts.append((level, msg, f))
    )
    auth = SimpleNamespace(
        rest_client=FakeRestClient(
            {
                "equity": {
                    "accountBalance": "10000000",
                    "totalDebt": 0,
                    "withdrawable": 0,
                }
            }
        )
    )
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    await account_sync._sync_balance(auth, "043422", "0434221", ts, storage)

    assert len(storage.balance_calls) == 1
    call = storage.balance_calls[0]
    assert call["account_balance"] == 10000000.0
    assert call["total_debt"] == 0.0
    assert call["withdrawable"] == 0.0
    assert alerts == []


async def test_sync_balance_case6_missing_two_fields_warns_both(monkeypatch):
    """Ca 6: thieu HAI truong -> WARN neu CA HAI ten."""
    storage = FakeStorage()
    alerts = []
    monkeypatch.setattr(
        account_sync, "alert", lambda level, msg, **f: alerts.append((level, msg, f))
    )
    auth = SimpleNamespace(
        rest_client=FakeRestClient(
            {
                "equity": {
                    "accountBalance": "10000000",
                    # totalDebt missing
                    "withdrawable": "",  # withdrawable empty string
                }
            }
        )
    )
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    await account_sync._sync_balance(auth, "043422", "0434221", ts, storage)

    assert storage.balance_calls == []
    assert len(alerts) == 1
    level, msg, fields = alerts[0]
    assert level == "WARN"
    missing = str(fields.get("missing_fields")) + " " + msg
    assert "totalDebt" in missing
    assert "withdrawable" in missing
    assert fields.get("account_no") == "0434221"


async def test_sync_balance_case7_missing_equity_block_no_op(monkeypatch):
    """Ca 7: giu nguyen hanh vi cu: raw khong co khoi equity -> khong ghi, khong no."""
    storage = FakeStorage()
    alerts = []
    monkeypatch.setattr(
        account_sync, "alert", lambda level, msg, **f: alerts.append((level, msg, f))
    )
    auth = SimpleNamespace(rest_client=FakeRestClient({}))
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    await account_sync._sync_balance(auth, "043422", "0434221", ts, storage)

    assert storage.balance_calls == []
    assert alerts == []


# =====================================================================
# Brief 103: Đối soát lệnh thật trong account_sync
# Tests 10, 11, 12, 13
# =====================================================================


class FakePortfolioForReconcile:
    def __init__(self, orders=None, error=None):
        self.orders = orders or []
        self.error = error
        self.historical_calls = []
        self.today_calls = []

    async def get_historical_orders(self, account_no, from_date, to_date):
        self.historical_calls.append((account_no, from_date, to_date))
        if self.error:
            raise self.error
        return self.orders

    async def get_today_orders(self, account_no):
        self.today_calls.append(account_no)
        if self.error:
            raise self.error
        return self.orders


class FakeStorageForReconcile:
    def __init__(self, placed_rows=None):
        self.placed_rows = placed_rows or []
        self.update_calls = []

    def read_placed_real_fills(self, account_no):
        return [r for r in self.placed_rows if r.account_no == account_no]

    def update_real_order_fill(self, id, status, qty, price, fee, pnl):
        self.update_calls.append({
            "id": id,
            "status": status,
            "qty": qty,
            "price": price,
            "fee": fee,
            "pnl": pnl,
        })
        return 1


async def test_10_reconcile_no_placed_rows_zero_ssi_calls():
    """10. Không có dòng placed -> get_historical_orders và get_today_orders được gọi 0 lần."""
    portfolio = FakePortfolioForReconcile(orders=[])
    storage = FakeStorageForReconcile(placed_rows=[])
    ts = datetime(2026, 9, 26, 10, 0, tzinfo=TZ)

    await account_sync._reconcile_real_orders(portfolio, "0434221", ts, storage)

    assert len(portfolio.historical_calls) == 0
    assert len(portfolio.today_calls) == 0


async def test_11_reconcile_two_placed_rows_one_ssi_call_updates_both(monkeypatch):
    """11. Có 2 dòng placed -> SSI được gọi 1 lần; mỗi dòng được cập nhật theo lệnh tương ứng."""
    ts = datetime(2026, 9, 26, 14, 0, tzinfo=TZ)
    row1_ts = datetime(2026, 9, 25, 10, 0, tzinfo=TZ)
    row2_ts = datetime(2026, 9, 26, 9, 30, tzinfo=TZ)

    r1 = PlacedRealFill(
        id=1,
        ts=row1_ts,
        account_no="0434221",
        symbol="HPG",
        side="BUY",
        qty=100,
        price=25000.0,
        fee=625.0,
        pnl=None,
        ssi_order_id="111",
        status="placed",
    )
    r2 = PlacedRealFill(
        id=2,
        ts=row2_ts,
        account_no="0434221",
        symbol="VCB",
        side="SELL",
        qty=200,
        price=50000.0,
        fee=25000.0,
        pnl=100000.0,  # cost_price = 50000 - 100000/200 = 49500
        ssi_order_id="222",
        status="placed",
    )
    storage = FakeStorageForReconcile(placed_rows=[r1, r2])

    o1 = Order(
        order_id="111",
        filled_quantity=100,
        cancel_quantity=0,
        avg_price=25000.0,
        status=OrderStatus.FILLED,
    )
    o2 = Order(
        order_id="222",
        filled_quantity=50,
        cancel_quantity=150,
        avg_price=51000.0,
        status=OrderStatus.PARTIAL_CANCELLED,
    )
    portfolio = FakePortfolioForReconcile(orders=[o1, o2])

    alerts = []
    monkeypatch.setattr(
        account_sync, "alert", lambda level, msg, **f: alerts.append((level, msg, f))
    )

    async def fake_fetch_order_history(port, acc, f_d, t_d, **kwargs):
        return await port.get_historical_orders(acc, f_d, t_d)

    monkeypatch.setattr(account_sync, "fetch_order_history", fake_fetch_order_history)

    await account_sync._reconcile_real_orders(portfolio, "0434221", ts, storage)

    # SSI được gọi đúng 1 lần từ ngày của dòng cũ nhất
    assert len(portfolio.historical_calls) == 1
    assert portfolio.historical_calls[0] == ("0434221", "2026/09/25", "2026/09/26")

    # 2 dòng đều được cập nhật
    assert len(storage.update_calls) == 2
    u1 = storage.update_calls[0]
    assert u1["id"] == 1
    assert u1["status"] == "filled"
    assert u1["qty"] == 100

    u2 = storage.update_calls[1]
    assert u2["id"] == 2
    assert u2["status"] == "filled"
    assert u2["qty"] == 50

    # Khớp 1 phần phải alert WARN, khớp đủ alert INFO
    info_alerts = [a for a in alerts if a[0] == "INFO"]
    warn_alerts = [a for a in alerts if a[0] == "WARN"]
    assert len(info_alerts) == 1
    assert len(warn_alerts) == 1
    assert "khớp một phần" in warn_alerts[0][1]


async def test_12_reconcile_ssi_error_skips_account_other_syncs_normally(monkeypatch):
    """12. SSI ném lỗi -> tài khoản đó bị bỏ qua với WARN như hiện nay, tài khoản kia vẫn đồng bộ bình thường."""
    cfg = SimpleNamespace(
        symbols=["HPG"],
        ssi_equity_accounts=["ACC_ERR", "ACC_OK"],
        holidays=frozenset(),
        real_trading_enabled=False,
    )

    ts = datetime(2026, 9, 26, 10, 0, tzinfo=TZ)
    row_err = PlacedRealFill(
        id=1,
        ts=ts,
        account_no="ACC_ERR",
        symbol="HPG",
        side="BUY",
        qty=100,
        price=25000.0,
        fee=625.0,
        pnl=None,
        ssi_order_id="111",
        status="placed",
    )

    class MultiAccountStorage(FakeStorage):
        def __init__(self):
            super().__init__()
            self.reconcile_storage = FakeStorageForReconcile([row_err])

        def read_placed_real_fills(self, account_no):
            return self.reconcile_storage.read_placed_real_fills(account_no)

        def update_real_order_fill(self, *a, **k):
            return self.reconcile_storage.update_real_order_fill(*a, **k)

        def read_account_balance_with_debt(self, account_no):
            return (1000000.0, 0.0)

        def read_real_positions(self, account_no):
            return {}

        def compute_nav(self, *a, **k):
            return 1000000.0, []

    storage = MultiAccountStorage()

    alerts = []
    monkeypatch.setattr(
        account_sync, "alert", lambda level, msg, **f: alerts.append((level, msg, f))
    )

    # Mock ensure_authenticated
    class MockAuth:
        def __init__(self):
            self.token_manager = SimpleNamespace(access_token="fake.token")
            self.config = SimpleNamespace(client_id="cid")
            self.rest_client = FakeRestClient({
                "equity": {
                    "accountBalance": "1000000",
                    "totalDebt": "0",
                    "withdrawable": "1000000",
                }
            })

        async def close(self):
            pass

    async def fake_auth(c, s):
        return MockAuth()

    monkeypatch.setattr(account_sync, "ensure_authenticated", fake_auth)
    monkeypatch.setattr(account_sync, "decode_client_id", lambda tok: "cid")

    class MockTradingService:
        def __init__(self, *a):
            pass
        async def get_max_buy_sell_at_market_price(self, acc, sym):
            return SimpleNamespace(max_buy_quantity=100, max_sell_quantity=0, margin_ratio="50%")

    class MockPortfolioService:
        def __init__(self, *a):
            pass
        async def get_equity_positions(self, acc):
            return []
        async def get_historical_orders(self, acc, from_date, to_date):
            if acc == "ACC_ERR":
                raise RuntimeError("SSI API blip")
            return []

    async def fake_fetch_order_history(port, acc, f_d, t_d, **kwargs):
        if acc == "ACC_ERR":
            raise RuntimeError("SSI API blip")
        return []

    monkeypatch.setattr(account_sync, "fetch_order_history", fake_fetch_order_history)
    monkeypatch.setattr("ssi_sdk.services.trading.AsyncTradingService", MockTradingService)
    monkeypatch.setattr("ssi_sdk.services.portfolio.AsyncPortfolioService", MockPortfolioService)

    await account_sync.sync_account_data(cfg, storage)

    # ACC_ERR bị WARN và bỏ qua
    err_alerts = [a for a in alerts if a[0] == "WARN" and a[2].get("account_no") == "ACC_ERR"]
    assert len(err_alerts) >= 1
    assert "account sync failed" in err_alerts[0][1]

    # ACC_OK vẫn đồng bộ balance bình thường
    ok_balances = [c for c in storage.balance_calls if c.get("account_no") == "ACC_OK"]
    assert len(ok_balances) == 1


async def test_13_reconcile_stale_unmatched_placed_row_dedup_critical(monkeypatch):
    """13. Dòng placed quá 1 ngày giao dịch không có trong SSI -> đúng 1 CRITICAL trong ngày dù hàm chạy nhiều lần."""
    # Reset alert cache
    account_sync._alerted_unmatched_fills.clear()

    # Dòng đặt từ 3 ngày trước (thứ Tư 23/09, hiện tại là thứ Bảy 26/09 -> cách > 1 ngày giao dịch)
    placed_ts = datetime(2026, 9, 23, 10, 0, tzinfo=TZ)
    now_ts = datetime(2026, 9, 26, 14, 0, tzinfo=TZ)

    stale_fill = PlacedRealFill(
        id=99,
        ts=placed_ts,
        account_no="0434221",
        symbol="HPG",
        side="BUY",
        qty=100,
        price=25000.0,
        fee=625.0,
        pnl=None,
        ssi_order_id="999_NOT_IN_SSI",
        status="placed",
    )
    storage = FakeStorageForReconcile(placed_rows=[stale_fill])
    portfolio = FakePortfolioForReconcile(orders=[])  # Không có lệnh 999

    alerts = []
    monkeypatch.setattr(
        account_sync, "alert", lambda level, msg, **f: alerts.append((level, msg, f))
    )

    async def fake_fetch_order_history(port, acc, f_d, t_d, **kwargs):
        return await port.get_historical_orders(acc, f_d, t_d)

    monkeypatch.setattr(account_sync, "fetch_order_history", fake_fetch_order_history)

    # Chạy lần 1
    await account_sync._reconcile_real_orders(portfolio, "0434221", now_ts, storage)

    # Chạy lần 2 cùng ngày
    await account_sync._reconcile_real_orders(portfolio, "0434221", now_ts, storage)

    # Chạy lần 3 cùng ngày
    await account_sync._reconcile_real_orders(portfolio, "0434221", now_ts, storage)

    crit_alerts = [a for a in alerts if a[0] == "CRITICAL"]
    assert len(crit_alerts) == 1, f"Phải đúng 1 CRITICAL alert trong ngày dù chạy nhiều lần, thực tế: {len(crit_alerts)}"
    assert "lệnh thật không rõ trạng thái" in crit_alerts[0][1]
    assert crit_alerts[0][2].get("fill_id") == 99



@pytest.mark.asyncio
async def test_reconcile_loi_khong_lam_cu_suc_mua_va_nav(monkeypatch):
    """Audit dot 103: doi soat la buoc PHU, phai chay SAU CUNG. Neu no nem loi, suc mua va
    NAV cua CHINH tai khoan do van phai da duoc cap nhat - khong thi cong go-live bao so
    lieu cu va duong lenh that tu choi lenh vi mot buoc phu hong."""
    from types import SimpleNamespace as NS

    monkeypatch.setattr(account_sync, "alert", lambda *a, **k: None)

    async def _noop():
        pass

    async def fake_auth(cfg, storage):
        return NS(token_manager=NS(access_token="tok"), config=NS(), rest_client=None,
                  close=lambda: _noop())

    monkeypatch.setattr(account_sync, "ensure_authenticated", fake_auth)
    monkeypatch.setattr(account_sync, "decode_client_id", lambda tok: "043422")
    import ssi_sdk.services.portfolio as sdk_portfolio

    monkeypatch.setattr(sdk_portfolio, "AsyncPortfolioService", lambda rc, cfg: NS())
    calls = []

    def rec(name, boom=False):
        async def f(*a, **k):
            calls.append(name)
            if boom:
                raise RuntimeError("SSI lich su lenh loi")
        return f

    monkeypatch.setattr(account_sync, "_sync_balance", rec("balance"))
    monkeypatch.setattr(account_sync, "_sync_positions", rec("positions"))
    monkeypatch.setattr(account_sync, "_sync_buying_power", rec("buying_power"))
    monkeypatch.setattr(account_sync, "_sync_nav", rec("nav"))
    monkeypatch.setattr(account_sync, "_reconcile_real_orders", rec("reconcile", boom=True))

    cfg = NS(ssi_equity_accounts=["ACC"], symbols=["HPG"], holidays=frozenset())
    await account_sync.sync_account_data(cfg, FakeStorage())

    assert calls == ["balance", "positions", "buying_power", "nav", "reconcile"], calls

# =============================================================================
# CONFIRM-1 tests (Brief 124, Phần B): xác nhận hai lần trước khi ghi rỗng/0
# =============================================================================

import trading.collector.account_sync as _acct_sync_mod


def _reset_confirm1():
    """Reset trạng thái CONFIRM-1 cấp module trước mỗi test để đảm bảo độc lập."""
    _acct_sync_mod._pending_empty_positions.clear()
    _acct_sync_mod._pending_zero_balance.clear()


def _fake_portfolio_none():
    async def _none():
        return None
    return SimpleNamespace(get_equity_positions=lambda acct: _none())


def _fake_portfolio_with(*symbols):
    from types import SimpleNamespace as SN
    positions = [SN(symbol=s, quantity=100, cost_price=50.0, sellable_quantity=100) for s in symbols]
    async def _get(acct):
        return positions
    return SimpleNamespace(get_equity_positions=_get)


def _fake_auth_balance(acct_bal, total_debt, withdrawable):
    equity = {
        "accountBalance": str(acct_bal),
        "totalDebt": str(total_debt),
        "withdrawable": str(withdrawable),
    }
    return SimpleNamespace(rest_client=FakeRestClient({"equity": equity}))


@pytest.mark.asyncio
async def test_b1_sudden_empty_positions_not_written_first_time():
    """b1: snapshot trước 6 mã, SSI trả None -> KHÔNG ghi, KHÔNG record_position_sync, có WARN."""
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ
    alerts = []
    storage = FakeStorage()
    storage._prev_positions["ACC"] = {s: object() for s in ["HPG", "VCB", "MBB", "TCB", "BID", "VHM"]}
    ts = datetime(2026, 9, 28, 23, 18, tzinfo=_TZ)
    _orig = _acct_sync_mod.alert
    _acct_sync_mod.alert = lambda level, msg, **kw: alerts.append((level, msg))
    try:
        await account_sync._sync_positions(_fake_portfolio_none(), "ACC", ts, storage)
    finally:
        _acct_sync_mod.alert = _orig
    assert storage.position_calls == [], "b1: KHÔNG được ghi vị thế lần đầu"
    assert storage.sync_recorded == [], "b1: KHÔNG được gọi record_position_sync lần đầu"
    assert any("CONFIRM-1" in msg for _, msg in alerts), "b1: phải có WARN CONFIRM-1"


@pytest.mark.asyncio
async def test_b2_sudden_empty_confirmed_on_second_sync():
    """b2: trong phiên, lần đầu pending, lần thứ hai vẫn None -> ghi + record_position_sync + WARN xác nhận."""
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ
    alerts = []
    storage = FakeStorage()
    storage._prev_positions["ACC"] = {"HPG": object(), "VCB": object()}
    ts1 = datetime(2026, 9, 28, 10, 0, tzinfo=_TZ)
    ts2 = datetime(2026, 9, 28, 10, 5, tzinfo=_TZ)
    _orig = _acct_sync_mod.alert
    _acct_sync_mod.alert = lambda level, msg, **kw: alerts.append((level, msg))
    try:
        await account_sync._sync_positions(_fake_portfolio_none(), "ACC", ts1, storage)
        assert storage.position_calls == []
        await account_sync._sync_positions(_fake_portfolio_none(), "ACC", ts2, storage)
    finally:
        _acct_sync_mod.alert = _orig
    assert len(storage.position_calls) == 1, "b2: lần 2 phải ghi vị thế rỗng"
    assert storage.position_calls[0][2] == [], "b2: ghi danh sách rỗng"
    assert len(storage.sync_recorded) == 1, "b2: lần 2 phải gọi record_position_sync"
    assert any("xác nhận" in msg for _, msg in alerts), "b2: WARN 'xác nhận' sau lần 2"


@pytest.mark.asyncio
async def test_b3_always_empty_account_writes_immediately():
    """b3: tài khoản 0434221 luôn rỗng (snapshot trước rỗng) -> ghi ngay (SYNC-1)."""
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ
    storage = FakeStorage()
    ts = datetime(2026, 9, 28, 23, 18, tzinfo=_TZ)
    await account_sync._sync_positions(_fake_portfolio_none(), "0434221", ts, storage)
    assert storage.position_calls == [("0434221", ts, [])], "b3: tài khoản luôn rỗng phải ghi ngay"
    assert storage.sync_recorded == [("0434221", ts)], "b3: record_position_sync phải được gọi"


@pytest.mark.asyncio
async def test_b4_positions_return_after_empty_clears_pending():
    """b4: lần đầu None (pending), lần sau SSI trả 2 mã -> gỡ cờ, ghi bình thường."""
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ
    storage = FakeStorage()
    storage._prev_positions["ACC"] = {"HPG": object(), "VCB": object()}
    ts = datetime(2026, 9, 28, 23, 18, tzinfo=_TZ)
    _orig = _acct_sync_mod.alert
    _acct_sync_mod.alert = lambda *a, **k: None
    try:
        await account_sync._sync_positions(_fake_portfolio_none(), "ACC", ts, storage)
        assert _acct_sync_mod._pending_empty_positions.get("ACC") is True
        await account_sync._sync_positions(_fake_portfolio_with("HPG", "VCB"), "ACC", ts, storage)
    finally:
        _acct_sync_mod.alert = _orig
    assert not _acct_sync_mod._pending_empty_positions.get("ACC"), "b4: cờ phải được gỡ"
    assert len(storage.position_calls) == 1
    assert len(storage.position_calls[0][2]) == 2, "b4: phải ghi 2 vị thế"
    assert len(storage.sync_recorded) == 1


@pytest.mark.asyncio
async def test_b5_zero_balance_not_written_first_time():
    """b5: số dư trước khác 0, SSI trả ba trường = 0 -> KHÔNG ghi lần đầu, có WARN."""
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ
    alerts = []
    storage = FakeStorage()
    storage._prev_balance = (500000.0, 31000000.0)
    ts = datetime(2026, 9, 28, 23, 18, tzinfo=_TZ)
    _orig = _acct_sync_mod.alert
    _acct_sync_mod.alert = lambda level, msg, **kw: alerts.append((level, msg))
    try:
        await account_sync._sync_balance(_fake_auth_balance(0, 0, 0), "cid", "ACC", ts, storage)
    finally:
        _acct_sync_mod.alert = _orig
    assert storage.balance_calls == [], "b5: KHÔNG được ghi số dư khi ba trường = 0 lần đầu"
    assert any("CONFIRM-1" in msg for _, msg in alerts), "b5: phải có WARN CONFIRM-1"


@pytest.mark.asyncio
async def test_b6_nav_old_positions_preserved_when_empty_pending():
    """b6: tái hiện 23:23:56 — vị thế SSI trả None, snapshot trước 6 mã.
    Lần đầu không ghi -> read_real_positions vẫn trả snapshot cũ -> NAV không tính âm."""
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ
    storage = FakeStorage()
    storage._prev_positions["ACC"] = {"HPG": object(), "VCB": object()}
    ts = datetime(2026, 9, 28, 23, 23, 56, tzinfo=_TZ)
    _orig = _acct_sync_mod.alert
    _acct_sync_mod.alert = lambda *a, **k: None
    try:
        await account_sync._sync_positions(_fake_portfolio_none(), "ACC", ts, storage)
    finally:
        _acct_sync_mod.alert = _orig
    prev = storage.read_real_positions("ACC")
    assert "HPG" in prev, "b6: snapshot cũ phải còn nguyên sau khi hoãn lần đầu"
    assert storage.position_calls == [], "b6: KHÔNG ghi vị thế lần đầu"


@pytest.mark.asyncio
async def test_b7_single_zero_field_writes_normally():
    """b7: withdrawable=0 thật của margin (chỉ một trường = 0) -> ghi bình thường.
    Điều kiện CONFIRM-1 chỉ bắt khi CẢ BA trường = 0."""
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ
    storage = FakeStorage()
    storage._prev_balance = (0.0, 31000000.0)
    await account_sync._sync_balance(
        _fake_auth_balance(acct_bal=-31000000, total_debt=31000000, withdrawable=0),
        "cid", "ACC", datetime(2026, 9, 28, 23, 0, tzinfo=_TZ), storage,
    )
    assert len(storage.balance_calls) == 1, "b7: withdrawable=0 thật -> phải ghi bình thường"


@pytest.mark.asyncio
async def test_b_break1_always_empty_must_write_immediately():
    """Phá thử B1: tài khoản luôn rỗng (prev rỗng) -> phải ghi ngay lần đầu."""
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ
    storage = FakeStorage()
    ts = datetime(2026, 9, 28, 23, 18, tzinfo=_TZ)
    await account_sync._sync_positions(_fake_portfolio_none(), "0434221", ts, storage)
    assert storage.position_calls != [], "B1: tài khoản luôn rỗng phải ghi ngay, không được hoãn"


@pytest.mark.asyncio
async def test_b_break2_sudden_empty_must_not_write_first_time():
    """Phá thử B2: rỗng đột ngột lần đầu -> KHÔNG ghi."""
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ
    storage = FakeStorage()
    storage._prev_positions["ACC"] = {"HPG": object()}
    ts = datetime(2026, 9, 28, 23, 18, tzinfo=_TZ)
    _orig = _acct_sync_mod.alert
    _acct_sync_mod.alert = lambda *a, **k: None
    try:
        await account_sync._sync_positions(_fake_portfolio_none(), "ACC", ts, storage)
    finally:
        _acct_sync_mod.alert = _orig
    assert storage.position_calls == [], "B2: lần đầu rỗng đột ngột KHÔNG được ghi ngay"


@pytest.mark.asyncio
async def test_b_break3_only_one_zero_field_must_not_be_blocked():
    """Phá thử B3: chỉ một trường = 0 -> KHÔNG bị chặn."""
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ
    storage = FakeStorage()
    storage._prev_balance = (0.0, 31000000.0)
    await account_sync._sync_balance(
        _fake_auth_balance(acct_bal=-31000000, total_debt=31000000, withdrawable=0),
        "cid", "ACC", datetime(2026, 9, 28, 23, 0, tzinfo=_TZ), storage,
    )
    assert len(storage.balance_calls) == 1, "B3: withdrawable=0 thật không phải CONFIRM-1"


# =============================================================================
# CONFIRM-1 Brief 164 tests: Cửa sổ xác nhận 09:00 - 15:30 ngày giao dịch
# =============================================================================

@pytest.mark.asyncio
async def test_confirm1_night_empty_positions_reproduced_30_09():
    """Test 1 (Tái hiện 30/09 danh mục):
    01:40 rỗng -> không ghi, có WARN đặt cờ.
    01:45 rỗng -> VẪN KHÔNG GHI (ngoài giờ), không phát WARN mới, cờ vẫn giữ.
    01:50 có lại 6 mã -> ghi 6 mã, cờ đã xóa.
    """
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ
    alerts = []
    storage = FakeStorage()
    storage._prev_positions["0434226"] = {s: object() for s in ["HPG", "VCB", "MBB", "TCB", "BID", "VHM"]}
    _orig = _acct_sync_mod.alert
    _acct_sync_mod.alert = lambda level, msg, **kw: alerts.append((level, msg))
    try:
        # Nhịp 01:40
        t1 = datetime(2026, 9, 30, 1, 40, tzinfo=_TZ)
        await account_sync._sync_positions(_fake_portfolio_none(), "0434226", t1, storage)
        assert storage.position_calls == []
        assert storage.sync_recorded == []
        warns_1 = [msg for lvl, msg in alerts if lvl == "WARN"]
        assert len(warns_1) == 1
        assert "CONFIRM-1" in warns_1[0]
        assert _acct_sync_mod._pending_empty_positions.get("0434226") is True

        # Nhịp 01:45 (vẫn rỗng, ngoài giờ giao dịch) -> KHÔNG ghi, KHÔNG thêm WARN mới, cờ vẫn giữ
        t2 = datetime(2026, 9, 30, 1, 45, tzinfo=_TZ)
        await account_sync._sync_positions(_fake_portfolio_none(), "0434226", t2, storage)
        assert storage.position_calls == []
        assert storage.sync_recorded == []
        warns_2 = [msg for lvl, msg in alerts if lvl == "WARN"]
        assert len(warns_2) == 1, "Không được phát WARN mới ngoài giờ giao dịch"
        assert _acct_sync_mod._pending_empty_positions.get("0434226") is True

        # Nhịp 01:50 (có lại 6 mã) -> ghi 6 mã, cờ xóa
        t3 = datetime(2026, 9, 30, 1, 50, tzinfo=_TZ)
        await account_sync._sync_positions(_fake_portfolio_with("HPG", "VCB", "MBB", "TCB", "BID", "VHM"), "0434226", t3, storage)
        assert len(storage.position_calls) == 1
        assert len(storage.position_calls[0][2]) == 6
        assert len(storage.sync_recorded) == 1
        assert not _acct_sync_mod._pending_empty_positions.get("0434226")
    finally:
        _acct_sync_mod.alert = _orig


@pytest.mark.asyncio
async def test_confirm1_night_zero_balance_reproduced_30_09():
    """Test 2 (Tái hiện 30/09 số dư):
    01:40 ba trường = 0 -> không ghi, có WARN đặt cờ.
    01:45 ba trường = 0 -> VẪN KHÔNG GHI (ngoài giờ), không phát WARN mới, cờ vẫn giữ.
    01:50 số dư bình thường -> ghi bình thường, cờ đã xóa.
    """
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ
    alerts = []
    storage = FakeStorage()
    storage._prev_balance = (500000.0, 31000000.0)
    _orig = _acct_sync_mod.alert
    _acct_sync_mod.alert = lambda level, msg, **kw: alerts.append((level, msg))
    try:
        # Nhịp 01:40
        t1 = datetime(2026, 9, 30, 1, 40, tzinfo=_TZ)
        await account_sync._sync_balance(_fake_auth_balance(0, 0, 0), "cid", "0434226", t1, storage)
        assert storage.balance_calls == []
        warns_1 = [msg for lvl, msg in alerts if lvl == "WARN"]
        assert len(warns_1) == 1
        assert "CONFIRM-1" in warns_1[0]
        assert _acct_sync_mod._pending_zero_balance.get("0434226") is True

        # Nhịp 01:45
        t2 = datetime(2026, 9, 30, 1, 45, tzinfo=_TZ)
        await account_sync._sync_balance(_fake_auth_balance(0, 0, 0), "cid", "0434226", t2, storage)
        assert storage.balance_calls == []
        warns_2 = [msg for lvl, msg in alerts if lvl == "WARN"]
        assert len(warns_2) == 1, "Không được phát WARN mới ngoài giờ giao dịch"
        assert _acct_sync_mod._pending_zero_balance.get("0434226") is True

        # Nhịp 01:50
        t3 = datetime(2026, 9, 30, 1, 50, tzinfo=_TZ)
        await account_sync._sync_balance(_fake_auth_balance(500000, 31000000, 500000), "cid", "0434226", t3, storage)
        assert len(storage.balance_calls) == 1
        assert storage.balance_calls[0]["account_balance"] == 500000.0
        assert not _acct_sync_mod._pending_zero_balance.get("0434226")
    finally:
        _acct_sync_mod.alert = _orig


@pytest.mark.asyncio
async def test_confirm1_in_session_confirmed_on_second_sync():
    """Test 3 (Trong phiên): 10:00 rỗng, 10:05 rỗng -> ghi rỗng ở 10:05."""
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ
    alerts = []
    storage = FakeStorage()
    storage._prev_positions["ACC"] = {"HPG": object(), "VCB": object()}
    _orig = _acct_sync_mod.alert
    _acct_sync_mod.alert = lambda level, msg, **kw: alerts.append((level, msg))
    try:
        t1 = datetime(2026, 9, 28, 10, 0, tzinfo=_TZ)
        t2 = datetime(2026, 9, 28, 10, 5, tzinfo=_TZ)
        await account_sync._sync_positions(_fake_portfolio_none(), "ACC", t1, storage)
        assert storage.position_calls == []
        await account_sync._sync_positions(_fake_portfolio_none(), "ACC", t2, storage)
    finally:
        _acct_sync_mod.alert = _orig
    assert len(storage.position_calls) == 1
    assert storage.position_calls[0][2] == []
    assert len(storage.sync_recorded) == 1
    assert any("xác nhận" in msg for _, msg in alerts)


@pytest.mark.asyncio
async def test_confirm1_window_boundary():
    """Test 4 (Biên cửa sổ 15:30):
    - Chờ từ 15:25, nhịp 15:30 rỗng -> XÁC NHẬN (15:30 còn trong cửa sổ).
    - Chờ từ 15:30, nhịp 15:35 rỗng -> KHÔNG XÁC NHẬN (15:35 ngoài cửa sổ).
    """
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ

    # Kịch bản A: 15:25 -> 15:30 (xác nhận)
    storage_a = FakeStorage()
    storage_a._prev_positions["ACC"] = {"HPG": object()}
    t_1525 = datetime(2026, 9, 28, 15, 25, tzinfo=_TZ)
    t_1530 = datetime(2026, 9, 28, 15, 30, tzinfo=_TZ)
    await account_sync._sync_positions(_fake_portfolio_none(), "ACC", t_1525, storage_a)
    assert storage_a.position_calls == []
    await account_sync._sync_positions(_fake_portfolio_none(), "ACC", t_1530, storage_a)
    assert len(storage_a.position_calls) == 1, "15:30 phải được xác nhận"

    # Kịch bản B: 15:30 -> 15:35 (không xác nhận)
    _reset_confirm1()
    storage_b = FakeStorage()
    storage_b._prev_positions["ACC"] = {"HPG": object()}
    t_1535 = datetime(2026, 9, 28, 15, 35, tzinfo=_TZ)
    await account_sync._sync_positions(_fake_portfolio_none(), "ACC", t_1530, storage_b)
    assert storage_b.position_calls == []
    await account_sync._sync_positions(_fake_portfolio_none(), "ACC", t_1535, storage_b)
    assert storage_b.position_calls == [], "15:35 ngoài cửa sổ -> KHÔNG được xác nhận"


@pytest.mark.asyncio
async def test_confirm1_holidays_and_weekends_blocked():
    """Test 5 (Ngày nghỉ):
    - Ngày lễ trong holidays (ví dụ 2026-09-01 Thứ Ba), 10:00 -> 10:05 rỗng -> KHÔNG ghi.
    - Thứ Bảy (2026-10-03), 10:00 -> 10:05 rỗng -> KHÔNG ghi.
    """
    _reset_confirm1()
    from datetime import date as _date

    from trading.calendar_vn import TZ as _TZ

    holidays = frozenset({_date(2026, 9, 1), _date(2026, 9, 2)})

    # Ngày lễ Thứ Ba
    storage_holiday = FakeStorage()
    storage_holiday._prev_positions["ACC"] = {"HPG": object()}
    t_hol1 = datetime(2026, 9, 1, 10, 0, tzinfo=_TZ)
    t_hol2 = datetime(2026, 9, 1, 10, 5, tzinfo=_TZ)
    await account_sync._sync_positions(_fake_portfolio_none(), "ACC", t_hol1, storage_holiday, holidays=holidays)
    assert storage_holiday.position_calls == []
    await account_sync._sync_positions(_fake_portfolio_none(), "ACC", t_hol2, storage_holiday, holidays=holidays)
    assert storage_holiday.position_calls == [], "Ngày lễ 10:05 -> KHÔNG được ghi"

    # Thứ Bảy
    _reset_confirm1()
    storage_sat = FakeStorage()
    storage_sat._prev_positions["ACC"] = {"HPG": object()}
    t_sat1 = datetime(2026, 10, 3, 10, 0, tzinfo=_TZ)
    t_sat2 = datetime(2026, 10, 3, 10, 5, tzinfo=_TZ)
    await account_sync._sync_positions(_fake_portfolio_none(), "ACC", t_sat1, storage_sat, holidays=holidays)
    assert storage_sat.position_calls == []
    await account_sync._sync_positions(_fake_portfolio_none(), "ACC", t_sat2, storage_sat, holidays=holidays)
    assert storage_sat.position_calls == [], "Thứ Bảy 10:05 -> KHÔNG được ghi"


@pytest.mark.asyncio
async def test_confirm1_overnight_confirmed_at_0900_next_trading_day():
    """Test 6 (Qua đêm):
    - Chờ từ 01:40 (đặt cờ), các nhịp đêm 01:45, 02:00, 08:55 không ghi.
    - Nhịp 09:00 ngày giao dịch (2026-09-30) vẫn rỗng -> XÁC NHẬN GHI.
    """
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ
    storage = FakeStorage()
    storage._prev_positions["ACC"] = {"HPG": object()}

    # Các nhịp đêm: 01:40 (lần đầu đặt cờ), 01:45, 02:00 (vẫn ngoài giờ, giữ cờ, không ghi)
    t_0140 = datetime(2026, 9, 30, 1, 40, tzinfo=_TZ)
    t_0145 = datetime(2026, 9, 30, 1, 45, tzinfo=_TZ)
    t_0200 = datetime(2026, 9, 30, 2, 0, tzinfo=_TZ)
    t_0900 = datetime(2026, 9, 30, 9, 0, tzinfo=_TZ)

    await account_sync._sync_positions(_fake_portfolio_none(), "ACC", t_0140, storage)
    assert storage.position_calls == []
    assert _acct_sync_mod._pending_empty_positions.get("ACC") is True

    await account_sync._sync_positions(_fake_portfolio_none(), "ACC", t_0145, storage)
    assert storage.position_calls == []
    assert _acct_sync_mod._pending_empty_positions.get("ACC") is True

    await account_sync._sync_positions(_fake_portfolio_none(), "ACC", t_0200, storage)
    assert storage.position_calls == []
    assert _acct_sync_mod._pending_empty_positions.get("ACC") is True

    # Nhịp 09:00 đúng ngày giao dịch -> xác nhận ghi
    await account_sync._sync_positions(_fake_portfolio_none(), "ACC", t_0900, storage)
    assert len(storage.position_calls) == 1, "09:00 ngày giao dịch -> phải xác nhận ghi"
    assert not _acct_sync_mod._pending_empty_positions.get("ACC")


@pytest.mark.asyncio
async def test_confirm1_always_empty_account_writes_immediately_at_night():
    """Test 7 (Tài khoản vốn rỗng): snapshot trước rỗng, nhịp 01:45 rỗng -> ghi ngay (SYNC-1)."""
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ
    storage = FakeStorage()
    # Không có prev_positions (mặc định rỗng)
    ts = datetime(2026, 9, 30, 1, 45, tzinfo=_TZ)
    await account_sync._sync_positions(_fake_portfolio_none(), "0434221", ts, storage)
    assert storage.position_calls == [("0434221", ts, [])]
    assert storage.sync_recorded == [("0434221", ts)]


@pytest.mark.asyncio
async def test_confirm1_single_zero_field_margin_writes_at_night():
    """Test 8 (Số dư một trường = 0): withdrawable=0 thật của tài khoản margin lúc 01:45 -> ghi ngay."""
    _reset_confirm1()
    from trading.calendar_vn import TZ as _TZ
    storage = FakeStorage()
    storage._prev_balance = (0.0, 31000000.0)
    ts = datetime(2026, 9, 30, 1, 45, tzinfo=_TZ)
    await account_sync._sync_balance(
        _fake_auth_balance(acct_bal=-31000000, total_debt=31000000, withdrawable=0),
        "cid", "0434226", ts, storage,
    )
    assert len(storage.balance_calls) == 1
    assert storage.balance_calls[0]["withdrawable"] == 0.0
    assert storage.balance_calls[0]["total_debt"] == 31000000.0
