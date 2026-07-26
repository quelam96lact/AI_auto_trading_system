from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ssi_sdk.enums import OrderSide

from trading.calendar_vn import TZ
from trading.config import Config
from trading.storage.db import Storage

from scripts.confirm_real_order import confirm


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.setenv("DB_DSN", "postgresql://t:t@localhost:5432/trading")
    monkeypatch.setenv("SSI_CONSUMER_ID", "c")
    monkeypatch.setenv("SSI_CONSUMER_SECRET", "s")
    monkeypatch.setenv("SSI_API_KEY", "k")
    monkeypatch.setenv("SSI_API_SECRET", "a")
    monkeypatch.setenv("SSI_PRIVATE_KEY", "pk")
    return Config(
        symbols=["VCB"],
        indices=[],
        bar_interval_minutes=5,
        ssi_equity_accounts=["0434221"],
        holidays=set(),
        db_dsn="postgresql://t:t@localhost:5432/trading",
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
def pending_order():
    future = datetime.now(TZ) + timedelta(minutes=15)
    return {
        "id": 42,
        "account_no": "ACC_REAL",
        "symbol": "VCB",
        "side": "BUY",
        "quantity": 100,
        "price": 50_000.0,
        "created_at": datetime.now(TZ) - timedelta(minutes=5),
        "expires_at": future,
        "status": "pending",
        "ssi_order_id": None,
        "confirmed_at": None,
    }


def make_storage(order):
    storage = MagicMock(spec=Storage)
    storage.get_pending_order.return_value = order
    return storage


def with_real_trading_enabled(cfg):
    """Tạo Config mới vì Config là frozen dataclass."""
    return Config(
        symbols=cfg.symbols,
        indices=cfg.indices,
        bar_interval_minutes=cfg.bar_interval_minutes,
        ssi_equity_accounts=cfg.ssi_equity_accounts,
        holidays=cfg.holidays,
        db_dsn=cfg.db_dsn,
        nats_url=cfg.nats_url,
        nats_stream=cfg.nats_stream,
        watchdog_stale_seconds=cfg.watchdog_stale_seconds,
        watchdog_max_failures=cfg.watchdog_max_failures,
        ssi_consumer_id=cfg.ssi_consumer_id,
        ssi_consumer_secret=cfg.ssi_consumer_secret,
        ssi_api_key=cfg.ssi_api_key,
        ssi_api_secret=cfg.ssi_api_secret,
        ssi_private_key=cfg.ssi_private_key,
        real_trading_enabled=True,
        real_order_capital=cfg.real_order_capital,
        real_order_account=cfg.real_order_account,
    )


@pytest.mark.asyncio
async def test_confirm_rejects_when_input_not_yes(cfg, pending_order):
    storage = make_storage(pending_order)
    with patch("scripts.confirm_real_order.alert") as mock_alert:
        with pytest.raises(SystemExit) as exc:
            await confirm(cfg, storage, 42, "no")
    assert exc.value.code == 0
    storage.update_pending_order_status.assert_called_once_with(42, "rejected")
    storage.write_real_order_fill.assert_not_called()
    mock_alert.assert_not_called()


@pytest.mark.asyncio
async def test_confirm_dry_run_does_not_call_place_order(cfg, pending_order):
    storage = make_storage(pending_order)
    fake_place = MagicMock()
    with patch("scripts.confirm_real_order.alert") as mock_alert:
        with pytest.raises(SystemExit) as exc:
            await confirm(cfg, storage, 42, "YES", place_order_fn=fake_place)
    assert exc.value.code == 0
    storage.update_pending_order_status.assert_called_once_with(42, "confirmed")
    fake_place.assert_not_called()
    storage.write_real_order_fill.assert_not_called()
    mock_alert.assert_called_once()
    alert_args = mock_alert.call_args
    assert alert_args.args[0] == "INFO"
    assert alert_args.kwargs["id"] == 42
    assert alert_args.kwargs["symbol"] == "VCB"
    assert alert_args.kwargs["side"] == "BUY"
    assert alert_args.kwargs["qty"] == 100
    assert alert_args.kwargs["price"] == 50_000.0


@pytest.mark.asyncio
async def test_confirm_rejects_buy_with_invalid_lot_size(cfg, pending_order):
    pending_order["quantity"] = 137
    pending_order["side"] = "BUY"
    storage = make_storage(pending_order)
    with patch("scripts.confirm_real_order.alert") as mock_alert:
        with pytest.raises(SystemExit) as exc:
            await confirm(cfg, storage, 42, "YES")
    assert exc.value.code == 1
    storage.update_pending_order_status.assert_called_once_with(42, "failed")
    storage.write_real_order_fill.assert_not_called()
    mock_alert.assert_not_called()


@pytest.mark.asyncio
async def test_confirm_expired_order_does_nothing(cfg, pending_order):
    """Order đã hết hạn (expires_at trong quá khứ) → confirm() không làm gì thêm,
    không tự đổi status. Việc đánh dấu 'expired' là trách nhiệm của
    Storage.expire_stale_pending_orders() (chạy định kỳ, ngoài phạm vi script này),
    không phải của confirm_real_order.py.
    """
    pending_order["expires_at"] = datetime(2026, 7, 15, 8, 0, tzinfo=TZ)
    storage = make_storage(pending_order)
    fake_place = MagicMock()
    with patch("scripts.confirm_real_order.alert"):
        with pytest.raises(SystemExit) as exc:
            await confirm(cfg, storage, 42, "YES", place_order_fn=fake_place)
    assert exc.value.code == 0
    storage.update_pending_order_status.assert_not_called()
    fake_place.assert_not_called()
    storage.write_real_order_fill.assert_not_called()


@pytest.mark.asyncio
async def test_confirm_real_mode_calls_place_order_and_saves_result(cfg, pending_order):
    cfg_real = with_real_trading_enabled(cfg)
    storage = make_storage(pending_order)
    placed = MagicMock()
    placed.order_id = "SSI-123"
    placed.client_request_id = "CR-123"
    placed.status = "MATCHED"
    fake_place = AsyncMock(return_value=placed)
    fake_mbs = AsyncMock(
        return_value=MagicMock(max_buy_quantity=1000, max_sell_quantity=1000)
    )

    fake_auth = MagicMock()
    fake_auth.config = MagicMock()
    fake_auth.close = AsyncMock()

    with patch("scripts.confirm_real_order.alert") as mock_alert:
        with patch("scripts.confirm_real_order.ensure_authenticated", return_value=fake_auth):
            await confirm(cfg_real, storage, 42, "YES", place_order_fn=fake_place, max_buy_sell_fn=fake_mbs)

    fake_mbs.assert_awaited_once_with("ACC_REAL", "VCB")

    fake_place.assert_called_once_with("ACC_REAL", "VCB", OrderSide.BUY, 100, 50_000.0)
    mock_alert.assert_called_once()
    alert_args = mock_alert.call_args
    assert alert_args.args[0] == "WARN"
    assert alert_args.kwargs["ssi_order_id"] == "SSI-123"
    assert alert_args.kwargs["status"] == "MATCHED"
    storage.update_pending_order_status.assert_called_once_with(42, "placed", ssi_order_id="SSI-123")
    storage.write_real_order_fill.assert_called_once()
    args = storage.write_real_order_fill.call_args.kwargs
    assert args["account_no"] == "ACC_REAL"
    assert args["symbol"] == "VCB"
    assert args["side"] == "BUY"
    assert args["qty"] == 100
    assert args["price"] == 50_000.0
    assert args["ssi_order_id"] == "SSI-123"
    assert args["status"] == "placed"
    fake_auth.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_confirm_real_mode_marks_failed_on_exception(cfg, pending_order):
    cfg_real = with_real_trading_enabled(cfg)
    storage = make_storage(pending_order)
    fake_place = AsyncMock(side_effect=RuntimeError("SSI down"))
    fake_mbs = AsyncMock(
        return_value=MagicMock(max_buy_quantity=1000, max_sell_quantity=1000)
    )

    fake_auth = MagicMock()
    fake_auth.config = MagicMock()
    fake_auth.close = AsyncMock()

    with patch("scripts.confirm_real_order.alert") as mock_alert:
        with patch("scripts.confirm_real_order.ensure_authenticated", return_value=fake_auth):
            with pytest.raises(SystemExit) as exc:
                await confirm(cfg_real, storage, 42, "YES", place_order_fn=fake_place, max_buy_sell_fn=fake_mbs)

    fake_mbs.assert_awaited_once_with("ACC_REAL", "VCB")

    assert exc.value.code == 1
    storage.update_pending_order_status.assert_called_once_with(42, "failed")
    storage.write_real_order_fill.assert_not_called()
    fake_auth.close.assert_awaited_once()
    mock_alert.assert_called_once()
    alert_args = mock_alert.call_args
    assert alert_args.args[0] == "CRITICAL"
    assert "SSI down" in alert_args.kwargs["error"]


@pytest.mark.asyncio
async def test_confirm_real_mode_aborts_when_insufficient_buy_power(cfg, pending_order):
    cfg_real = with_real_trading_enabled(cfg)
    storage = make_storage(pending_order)
    fake_place = AsyncMock()
    fake_mbs = AsyncMock(return_value=MagicMock(max_buy_quantity=50, max_sell_quantity=1000))

    fake_auth = MagicMock()
    fake_auth.config = MagicMock()
    fake_auth.close = AsyncMock()

    with patch("scripts.confirm_real_order.alert") as mock_alert:
        with patch("scripts.confirm_real_order.ensure_authenticated", return_value=fake_auth):
            with pytest.raises(SystemExit) as exc:
                await confirm(cfg_real, storage, 42, "YES", place_order_fn=fake_place, max_buy_sell_fn=fake_mbs)

    assert exc.value.code == 1
    fake_mbs.assert_awaited_once_with("ACC_REAL", "VCB")
    fake_place.assert_not_called()
    storage.update_pending_order_status.assert_called_once_with(42, "failed")
    storage.write_real_order_fill.assert_not_called()
    mock_alert.assert_called_once()
    alert_args = mock_alert.call_args
    assert alert_args.args[0] == "CRITICAL"
    assert alert_args.kwargs["id"] == 42
    assert alert_args.kwargs["symbol"] == "VCB"
    assert alert_args.kwargs["side"] == "BUY"
    assert alert_args.kwargs["requested_qty"] == 100
    assert alert_args.kwargs["available_qty"] == 50


@pytest.mark.asyncio
async def test_confirm_real_mode_aborts_when_insufficient_sell_power(cfg, pending_order):
    pending_order["side"] = "SELL"
    cfg_real = with_real_trading_enabled(cfg)
    storage = make_storage(pending_order)
    fake_place = AsyncMock()
    fake_mbs = AsyncMock(return_value=MagicMock(max_buy_quantity=1000, max_sell_quantity=30))

    fake_auth = MagicMock()
    fake_auth.config = MagicMock()
    fake_auth.close = AsyncMock()

    with patch("scripts.confirm_real_order.alert") as mock_alert:
        with patch("scripts.confirm_real_order.ensure_authenticated", return_value=fake_auth):
            with pytest.raises(SystemExit) as exc:
                await confirm(cfg_real, storage, 42, "YES", place_order_fn=fake_place, max_buy_sell_fn=fake_mbs)

    assert exc.value.code == 1
    fake_mbs.assert_awaited_once_with("ACC_REAL", "VCB")
    fake_place.assert_not_called()
    storage.update_pending_order_status.assert_called_once_with(42, "failed")
    storage.write_real_order_fill.assert_not_called()
    mock_alert.assert_called_once()
    alert_args = mock_alert.call_args
    assert alert_args.args[0] == "CRITICAL"
    assert alert_args.kwargs["id"] == 42
    assert alert_args.kwargs["symbol"] == "VCB"
    assert alert_args.kwargs["side"] == "SELL"
    assert alert_args.kwargs["requested_qty"] == 100
    assert alert_args.kwargs["available_qty"] == 30
