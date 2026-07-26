from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from trading.calendar_vn import TZ
from trading.config import Config
from trading.models import Bar
from trading.real_orders import PENDING_ORDER_TTL_MINUTES, handle_signal
from trading.risk import RiskManager
from trading.storage.db import RealPosition
from trading.strategy import Signal


@pytest.fixture
def cfg():
    return Config(
        symbols=["VCB"],
        indices=[],
        bar_interval_minutes=5,
        ssi_equity_accounts=["0434221"],
        holidays=set(),
        db_dsn="postgresql://x:x@localhost/db",
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
        real_order_capital=1_000_000_000.0,
        real_order_account="ACC_REAL",
    )


@pytest.fixture
def bar():
    return Bar("VCB", datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 50_000, 50_000, 50_000, 50_000, 100)


def test_handle_signal_writes_pending_order_when_approved(cfg, bar):
    storage = MagicMock()
    storage.read_real_positions.return_value = {}
    storage.read_real_daily_pnl.return_value = 0.0
    storage.create_pending_order.return_value = 42

    risk = RiskManager(capital=cfg.real_order_capital)
    signal = Signal(symbol="VCB", side="BUY", qty=100)

    with patch("trading.real_orders.alert") as mock_alert:
        handle_signal(cfg, storage, risk, signal, bar)

    storage.create_pending_order.assert_called_once()
    args = storage.create_pending_order.call_args.kwargs
    assert args["account_no"] == "ACC_REAL"
    assert args["symbol"] == "VCB"
    assert args["side"] == "BUY"
    assert args["quantity"] == 100
    assert args["price"] == 50_000
    expires_at = args["expires_at"]
    assert expires_at.tzinfo is not None
    assert expires_at > datetime.now(TZ)
    assert expires_at <= datetime.now(TZ) + timedelta(minutes=PENDING_ORDER_TTL_MINUTES)

    mock_alert.assert_called_once()
    alert_kwargs = mock_alert.call_args.kwargs
    assert alert_kwargs["id"] == 42
    assert alert_kwargs["confirm_cmd"] == "uv run python scripts/confirm_real_order.py 42"


def test_handle_signal_does_nothing_when_risk_rejects(cfg, bar):
    storage = MagicMock()
    storage.read_real_positions.return_value = {}
    storage.read_real_daily_pnl.return_value = 0.0

    risk = RiskManager(capital=1.0)
    signal = Signal(symbol="VCB", side="BUY", qty=100)

    with patch("trading.real_orders.alert") as mock_alert:
        handle_signal(cfg, storage, risk, signal, bar)

    storage.create_pending_order.assert_not_called()
    mock_alert.assert_not_called()


def test_handle_signal_caps_sell_quantity_to_sellable_qty(cfg, bar):
    storage = MagicMock()
    storage.read_real_positions.return_value = {
        "VCB": RealPosition("VCB", 100, 50_000.0, 30)
    }
    storage.read_real_daily_pnl.return_value = 0.0
    storage.create_pending_order.return_value = 42

    risk = RiskManager(capital=cfg.real_order_capital)
    signal = Signal(symbol="VCB", side="SELL", qty=100)

    with patch("trading.real_orders.alert") as mock_alert:
        handle_signal(cfg, storage, risk, signal, bar)

    storage.create_pending_order.assert_called_once()
    args = storage.create_pending_order.call_args.kwargs
    assert args["quantity"] == 30
    mock_alert.assert_called_once()


def test_handle_signal_skips_sell_when_nothing_sellable(cfg, bar):
    storage = MagicMock()
    storage.read_real_positions.return_value = {}
    storage.read_real_daily_pnl.return_value = 0.0

    risk = RiskManager(capital=cfg.real_order_capital)
    signal = Signal(symbol="VCB", side="SELL", qty=100)

    with patch("trading.real_orders.alert") as mock_alert:
        handle_signal(cfg, storage, risk, signal, bar)

    storage.create_pending_order.assert_not_called()
    mock_alert.assert_not_called()
