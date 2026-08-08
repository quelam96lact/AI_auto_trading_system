from datetime import datetime
from types import SimpleNamespace

from trading.calendar_vn import TZ
from trading.collector import derivative_sync


class FakeStorage:
    def __init__(self):
        self.balance_calls = []
        self.margin_calls = []
        self.position_calls = []

    def save_derivative_balance(self, **kwargs):
        self.balance_calls.append(kwargs)

    def save_derivative_margin(self, **kwargs):
        self.margin_calls.append(kwargs)

    def save_derivative_positions(self, account_no, ts, positions):
        self.position_calls.append((account_no, ts, positions))


def _ppmmr(**overrides):
    base = {
        "rc_call": False,
        "account_ratio_ssi": 0.0,
        "account_ratio_vsdc": 0.0,
        "used_limit_warning_level1_ssi": 85.0,
        "used_limit_warning_level2_ssi": 90.0,
        "used_limit_warning_level3_ssi": 95.0,
        "total_equity": 0.0,
    }
    base.update(overrides)
    return _wrap(SimpleNamespace(**base))


async def _wrap(value):
    return value


async def test_sync_balance_maps_real_field_names():
    storage = FakeStorage()
    portfolio = SimpleNamespace(get_derivative_balance=lambda account_no: _balance())
    ts = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)

    await derivative_sync._sync_balance(portfolio, "0434228", ts, storage)

    assert storage.balance_calls == [
        {
            "account_no": "0434228",
            "ts": ts,
            "account_balance": 0.0,
            "floating_pl": 0.0,
            "trading_pl": 0.0,
            "total_pl": 0.0,
            "withdrawable": 0.0,
        }
    ]


async def _balance():
    return SimpleNamespace(
        account_balance=0, floating_pl=0, trading_pl=0, total_pl=0, withdrawable=0
    )


async def test_sync_margin_writes_snapshot_and_no_alert_when_below_thresholds(
    monkeypatch,
):
    storage = FakeStorage()
    alerts = []
    monkeypatch.setattr(
        derivative_sync, "alert", lambda level, msg, **f: alerts.append((level, msg, f))
    )
    portfolio = SimpleNamespace(get_derivative_ppmmr=lambda account_no: _ppmmr())
    ts = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)

    await derivative_sync._sync_margin(portfolio, "0434228", ts, storage)

    assert len(storage.margin_calls) == 1
    assert storage.margin_calls[0]["rc_call"] is False
    assert alerts == []


async def test_sync_margin_alerts_critical_on_rc_call(monkeypatch):
    storage = FakeStorage()
    alerts = []
    monkeypatch.setattr(
        derivative_sync, "alert", lambda level, msg, **f: alerts.append((level, msg, f))
    )
    portfolio = SimpleNamespace(
        get_derivative_ppmmr=lambda account_no: _ppmmr(rc_call=True)
    )
    ts = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)

    await derivative_sync._sync_margin(portfolio, "0434228", ts, storage)

    assert alerts and alerts[0][0] == "CRITICAL"


async def test_sync_positions_unpacks_single_object_not_list():
    storage = FakeStorage()
    portfolio = SimpleNamespace(
        get_derivative_positions=lambda account_no: _all_positions(
            SimpleNamespace(
                symbol="41I1G8000", long=1, short=0, net=1, floating_pl=50.0
            )
        )
    )
    ts = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)

    await derivative_sync._sync_positions(portfolio, "0434228", ts, storage)

    assert storage.position_calls == [
        (
            "0434228",
            ts,
            [
                {
                    "symbol": "41I1G8000",
                    "long": 1,
                    "short": 0,
                    "net": 1,
                    "floating_pl": 50.0,
                }
            ],
        )
    ]


async def _all_positions(*open_positions):
    return SimpleNamespace(open_positions=list(open_positions), closed_positions=[])


def test_margin_alert_level_thresholds():
    m = derivative_sync.margin_alert_level
    assert m(False, 50, 50, 85, 90, 95) is None
    assert m(False, 86, 50, 85, 90, 95) == "WARN"
    assert m(False, 50, 91, 85, 90, 95) == "WARN"
    assert m(False, 50, 96, 85, 90, 95) == "CRITICAL"
    assert m(True, 0, 0, 85, 90, 95) == "CRITICAL"
