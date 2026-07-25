from datetime import datetime
from types import SimpleNamespace

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

    def save_account_balance(self, **kwargs):
        self.balance_calls.append(kwargs)

    def save_account_positions(self, account_no, ts, positions):
        self.position_calls.append((account_no, ts, positions))


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
