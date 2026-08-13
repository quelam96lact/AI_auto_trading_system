from datetime import datetime, timedelta

import pytest

from tests.conftest import TEST_DSN
from trading.backtest import STRATEGIES, run_backtest
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.resample import resample_bars
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.trailing_stop import TrailingStopManager

DSN = TEST_DSN
pytestmark = pytest.mark.integration


@pytest.fixture
def storage():
    s = Storage(DSN)
    s.init_schema()
    with s.conn() as c:
        c.execute("DELETE FROM bars WHERE symbol = 'BTCLI'")
    return s


def _seed_bars(storage, n=25):
    start = datetime(2026, 7, 1, 9, 0, tzinfo=TZ)
    prices = [10.0] * 20 + [20.0] * (n - 20)
    bars = [
        Bar("BTCLI", start + timedelta(minutes=5 * i), p, p, p, p, 1000)
        for i, p in enumerate(prices)
    ]
    storage.write_bars(bars)
    return bars


def test_cli_registry_has_sma_cross():
    assert "sma_cross" in STRATEGIES


def test_read_resample_replay_is_deterministic_from_real_db(storage):
    _seed_bars(storage, n=25)
    frm = datetime(2026, 7, 1, tzinfo=TZ)
    to = datetime(2026, 7, 2, tzinfo=TZ)

    def run_once():
        rows = storage.read_bars("BTCLI", frm, to)
        resampled = resample_bars(rows, 15)
        return run_backtest(
            resampled,
            STRATEGIES["sma_cross"](),
            RiskManager(capital=100_000_000),
            TrailingStopManager(),
            100_000_000,
        )

    r1, r2 = run_once(), run_once()
    assert r1 == r2
    assert len(resample_bars(storage.read_bars("BTCLI", frm, to), 15)) > 0


def test_tf_registry_covers_all_timeframes_and_sources():
    from trading.backtest import _TF_SPEC

    assert set(_TF_SPEC) == {"5m", "10m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"}
    # khung noi ngay doc bang `bars`, khung tu 1d tro len doc `bars_daily`
    assert {tf for tf, (src, _) in _TF_SPEC.items() if src == "bars"} == {
        "5m", "10m", "15m", "30m", "1h", "4h"
    }
    assert {tf for tf, (src, _) in _TF_SPEC.items() if src == "bars_daily"} == {
        "1d", "1w", "1M"
    }
