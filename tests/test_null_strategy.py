"""Unit tests cho Brief Đợt 229: NullStrategy và cờ ENGINE_STRATEGY_DISABLED."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import nats.errors

from trading.calendar_vn import TZ
from trading.config import Config
from trading.engine import main as engine_main
from trading.models import Bar
from trading.strategies.null_strategy import NullStrategy
from trading.strategy import Strategy


def _make_cfg(symbols: list[str] | None = None) -> Config:
    return Config(
        symbols=["HPG"] if symbols is None else symbols,
        indices=[],
        bar_interval_minutes=5,
        ssi_equity_accounts=[],
        holidays=set(),
        db_dsn="postgresql://x:***@localhost/db",
        nats_url="nats://localhost:4222",
        nats_stream="BARS",
        watchdog_stale_seconds=180,
        watchdog_max_failures=3,
        ssi_consumer_id="c",
        ssi_consumer_secret="s",
        ssi_api_key="k",
        ssi_api_secret="a",
        ssi_private_key="pk",
        real_trading_enabled=False,
        real_order_account="ACC",
    )


def _make_fake_storage(history_bars: list[Bar] | None = None):
    now_dt = datetime(2026, 11, 13, 14, 0, tzinfo=TZ)
    storage = MagicMock()
    storage.read_engine_state.return_value = None
    storage.read_positions.return_value = {}
    storage.last_bar_ts.return_value = now_dt
    storage.read_last_bars.return_value = history_bars or []
    storage.read_nav.return_value = (100_000_000.0, now_dt, [])
    storage.read_real_risk_halt.return_value = None
    storage.read_real_positions.return_value = {}
    storage.read_position_sync_ts.return_value = now_dt
    storage.expire_stale_pending_orders.return_value = 0
    return storage


class _FakeMsg:
    def __init__(self, bar: Bar) -> None:
        self.data = json.dumps(
            {
                "symbol": bar.symbol,
                "ts": bar.ts.isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "source": bar.source,
            }
        ).encode("utf-8")
        self.acked = False
        self.termed = False

    async def ack(self) -> None:
        self.acked = True

    async def term(self) -> None:
        self.termed = True


class _FakeSub:
    def __init__(self, actions: list[object], stop_event: asyncio.Event | None = None):
        self._actions = list(actions)
        self._stop_event = stop_event

    async def next_msg(self, timeout: float = 60):
        if self._actions:
            item = self._actions.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item
        if self._stop_event is not None:
            self._stop_event.set()
        raise nats.errors.TimeoutError()


def _install_fake_nats(monkeypatch, sub: _FakeSub) -> None:
    class FakeJS:
        async def subscribe(self, *args, **kwargs):
            return sub

    class FakeNC:
        def jetstream(self):
            return FakeJS()

        async def close(self):
            pass

    async def fake_connect(*args, **kwargs):
        return FakeNC()

    monkeypatch.setattr(engine_main.nats, "connect", fake_connect)


def test_e_null_strategy_protocol_and_warmup_bars():
    """(e) NullStrategy tuân thủ Strategy Protocol và warmup_bars >= 1."""
    strat = NullStrategy()
    assert isinstance(strat, Strategy)
    assert strat.warmup_bars >= 1
    bar = Bar("HPG", datetime(2026, 11, 13, 9, 15, tzinfo=TZ), 25_000, 25_500, 24_800, 25_200, 10_000)
    assert strat.compute_crossover(bar) is None
    assert strat.last_crossover("HPG") is None
    assert strat.last_atr("HPG") is None
    ctx = MagicMock()
    ctx.position_qty.return_value = 0
    assert strat.on_bar(bar, ctx) is None


async def test_a_disabled_flag_runs_cleanly_places_no_orders_and_acks(monkeypatch):
    """(a) ENGINE_STRATEGY_DISABLED=1: warm-up không lỗi, không đặt lệnh, vẫn ack message."""
    monkeypatch.setenv("ENGINE_STRATEGY_DISABLED", "1")
    alerts: list[tuple[str, str, dict]] = []
    monkeypatch.setattr(engine_main, "alert", lambda lvl, msg, **kw: alerts.append((lvl, msg, kw)))

    base = datetime(2026, 11, 13, 9, 0, tzinfo=TZ)
    hist = [
        Bar("HPG", base + timedelta(minutes=5 * i), 25_000, 25_100, 24_900, 25_000, 1_000)
        for i in range(5)
    ]
    storage = _make_fake_storage(history_bars=hist)
    monkeypatch.setattr(engine_main, "Storage", lambda dsn: storage)

    live_bar = Bar("HPG", base + timedelta(minutes=30), 25_000, 26_000, 24_900, 25_900, 50_000)
    msg = _FakeMsg(live_bar)
    _install_fake_nats(monkeypatch, _FakeSub([msg]))

    await engine_main.run(
        _make_cfg(["HPG"]),
        max_messages=1,
        stop_event=asyncio.Event(),
        now=datetime(2026, 11, 13, 14, 0, tzinfo=TZ),
    )

    assert msg.acked is True, f"msg not acked, termed={msg.termed}, alerts={alerts}"
    assert msg.termed is False
    storage.write_order.assert_not_called()
    assert any("ENGINE_STRATEGY_DISABLED" in m and kw.get("strategy") == "NullStrategy" for _, m, kw in alerts)


async def test_b_disabled_flag_still_beats_heartbeat(monkeypatch):
    """(b) ENGINE_STRATEGY_DISABLED=1 vẫn ghi heartbeat storage.beat('engine')."""
    monkeypatch.setenv("ENGINE_STRATEGY_DISABLED", "1")
    monkeypatch.setattr(engine_main, "alert", lambda *a, **kw: None)

    storage = _make_fake_storage()
    monkeypatch.setattr(engine_main, "Storage", lambda dsn: storage)

    stop_event = asyncio.Event()
    _install_fake_nats(monkeypatch, _FakeSub([nats.errors.TimeoutError()], stop_event=stop_event))

    await engine_main.run(
        _make_cfg([]),
        stop_event=stop_event,
        now=datetime(2026, 11, 13, 14, 0, tzinfo=TZ),
    )

    storage.beat.assert_called_with("engine")


async def test_c_unset_or_zero_flag_uses_default_strategy(monkeypatch):
    """(c) Không đặt hoặc đặt ENGINE_STRATEGY_DISABLED='0' -> gọi _default_strategy()."""
    real_default = engine_main._default_strategy
    for val in (None, "0"):
        if val is None:
            monkeypatch.delenv("ENGINE_STRATEGY_DISABLED", raising=False)
        else:
            monkeypatch.setenv("ENGINE_STRATEGY_DISABLED", val)
        monkeypatch.setattr(engine_main, "alert", lambda *a, **kw: None)

        called = {"default": 0}

        def _spy_default(counter=called):
            counter["default"] += 1
            return real_default()

        monkeypatch.setattr(engine_main, "_default_strategy", _spy_default)
        storage = _make_fake_storage()
        monkeypatch.setattr(engine_main, "Storage", lambda dsn, st=storage: st)

        stop_event = asyncio.Event()
        stop_event.set()
        _install_fake_nats(monkeypatch, _FakeSub([], stop_event=stop_event))

        await engine_main.run(
            _make_cfg([]),
            stop_event=stop_event,
            now=datetime(2026, 11, 13, 14, 0, tzinfo=TZ),
        )
        assert called["default"] == 1


async def test_d_explicit_strategy_overrides_disabled_flag(monkeypatch):
    """(d) Truyền strategy= tường minh luôn ưu tiên hơn ENGINE_STRATEGY_DISABLED='1'."""
    monkeypatch.setenv("ENGINE_STRATEGY_DISABLED", "1")
    alerts: list[tuple[str, str, dict]] = []
    monkeypatch.setattr(engine_main, "alert", lambda lvl, msg, **kw: alerts.append((lvl, msg, kw)))

    storage = _make_fake_storage()
    monkeypatch.setattr(engine_main, "Storage", lambda dsn: storage)

    custom_strat = MagicMock()
    custom_strat.warmup_bars = 1
    custom_strat.on_bar.return_value = None
    custom_strat.last_crossover.return_value = None
    custom_strat.last_atr.return_value = None

    msg = _FakeMsg(Bar("HPG", datetime(2026, 11, 13, 10, 0, tzinfo=TZ), 25_000, 25_100, 24_900, 25_000, 1_000))
    _install_fake_nats(monkeypatch, _FakeSub([msg]))

    await engine_main.run(
        _make_cfg(["HPG"]),
        max_messages=1,
        stop_event=asyncio.Event(),
        strategy=custom_strat,
        now=datetime(2026, 11, 13, 14, 0, tzinfo=TZ),
    )

    assert msg.acked is True, f"msg not acked, termed={msg.termed}, alerts={alerts}"
    custom_strat.on_bar.assert_called_once()
