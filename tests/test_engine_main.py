import logging
import os
from datetime import datetime, timedelta

import pytest
import nats

from trading.bus.publisher import BarPublisher
from trading.calendar_vn import TZ
from trading.config import Config
from trading.engine.main import run
from trading.models import Bar
from trading.storage.db import Storage

DSN = os.environ.get("DB_DSN", "postgresql://trading:trading@localhost:5432/trading")
pytestmark = pytest.mark.integration


def make_cfg() -> Config:
    return Config(
        symbols=["ENGT"],
        indices=[],
        bar_interval_minutes=15,
        holidays=set(),
        db_dsn=DSN,
        nats_url="nats://localhost:4222",
        nats_stream="BARS",
        watchdog_stale_seconds=180,
        watchdog_max_failures=3,
        ssi_consumer_id="x",
        ssi_consumer_secret="y",
        ssi_api_key="k",
        ssi_api_secret="s",
    )


@pytest.fixture
def storage():
    s = Storage(DSN)
    s.init_schema()
    with s.conn() as c:
        c.execute("DELETE FROM positions WHERE symbol = 'ENGT'")
        c.execute("DELETE FROM orders WHERE symbol = 'ENGT'")
        c.execute("DELETE FROM engine_state WHERE id = 1")
    return s


@pytest.fixture(autouse=True)
async def reset_stream_and_durable_consumer():
    nc = await nats.connect("nats://localhost:4222")
    js = nc.jetstream()
    try:
        await js.delete_consumer("BARS", "engine")
    except Exception:
        pass
    try:
        await js.purge_stream("BARS")
    except Exception:
        pass
    await nc.close()


def make_bars(prices, sym="ENGT"):
    start = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    return [
        Bar(sym, start + timedelta(minutes=15 * i), p, p, p, p, 1000)
        for i, p in enumerate(prices)
    ]


async def _publish(cfg, bars):
    pub = BarPublisher(cfg.nats_url, cfg.nats_stream)
    await pub.connect()
    for bar in bars:
        await pub.publish(bar)
    await pub.close()


async def test_engine_persists_fill_and_restores_state_on_next_run(storage, caplog):
    cfg = make_cfg()
    prices = [10] * 20 + [20] * 5
    bars = make_bars(prices)
    await _publish(cfg, bars)

    await run(cfg, max_messages=len(bars))

    positions = storage.read_positions()
    assert positions["ENGT"].qty == 100
    state = storage.read_engine_state()
    assert state is not None and state[0] < 100_000_000

    with storage.conn() as c:
        n_orders = c.execute("SELECT count(*) FROM orders WHERE symbol = 'ENGT'").fetchone()[0]
    assert n_orders == 1

    await _publish(cfg, make_bars([20], sym="ENGT"))
    with caplog.at_level(logging.INFO):
        await run(cfg, max_messages=1)
    assert any("engine restored state" in r.message for r in caplog.records)
    assert storage.read_positions()["ENGT"].qty == 100


async def test_engine_alerts_critical_on_risk_halt(storage, monkeypatch):
    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main,
        "alert",
        lambda level, msg, **f: alerts_seen.append((level, msg)),
    )

    cfg = make_cfg()
    prices = [90_000] * 20 + [95_000] * 10 + [50_000] * 10
    bars = make_bars(prices)
    await _publish(cfg, bars)

    await run(cfg, max_messages=len(bars))

    assert ("CRITICAL", "risk halt: max daily loss reached") in alerts_seen
