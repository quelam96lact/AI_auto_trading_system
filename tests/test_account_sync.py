from datetime import datetime
from types import SimpleNamespace

import pytest

from trading.calendar_vn import TZ
from trading.collector import account_sync


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

    def save_account_balance(self, **kwargs):
        self.balance_calls.append(kwargs)

    def save_account_positions(self, account_no, ts, positions):
        self.position_calls.append((account_no, ts, positions))

    def record_position_sync(self, account_no, ts):
        self.sync_recorded.append((account_no, ts))


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
        }
    ]


async def test_sync_balance_skips_missing_equity():
    storage = FakeStorage()
    auth = SimpleNamespace(rest_client=FakeRestClient({}))
    ts = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)

    await account_sync._sync_balance(auth, "043422", "0434228", ts, storage)

    assert storage.balance_calls == []


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
            [{"symbol": "VCB", "quantity": 100, "cost_price": 88.5, "sellable_quantity": 80}],
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

    async def fake_balance(auth, client_id, account_no, ts, storage):
        calls["balance"].append(account_no)
        if account_no == "ACC_BAD":
            raise RuntimeError("parse boom")

    async def fake_positions(portfolio, account_no, ts, storage):
        calls["positions"].append(account_no)

    monkeypatch.setattr(account_sync, "_sync_balance", fake_balance)
    monkeypatch.setattr(account_sync, "_sync_positions", fake_positions)

    cfg = NS(ssi_equity_accounts=["ACC_BAD", "ACC_OK"])
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
