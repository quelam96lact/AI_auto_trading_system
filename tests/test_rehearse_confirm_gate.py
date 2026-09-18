"""Tests cho scripts/rehearse_confirm_gate.py (Brief đợt 52 Task 2).

Kiểm chứng các hàng rào an toàn cứng và luồng diễn tập dry-run.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from scripts.rehearse_confirm_gate import rehearse, verify_safety_barriers
from trading.calendar_vn import TZ
from trading.config import Config
from trading.storage.db import Storage


def make_dummy_config(dsn: str, real_trading_enabled: bool = False) -> Config:
    return Config(
        symbols=["IJC"],
        indices=[],
        bar_interval_minutes=5,
        ssi_equity_accounts=["0434221"],
        holidays=set(),
        db_dsn=dsn,
        nats_url="nats://127.0.0.1:4223",
        nats_stream="BARS",
        watchdog_stale_seconds=180,
        watchdog_max_failures=3,
        ssi_consumer_id="",
        ssi_consumer_secret="",
        ssi_api_key="",
        ssi_api_secret="",
        ssi_private_key="",
        real_trading_enabled=real_trading_enabled,
        real_order_account="0434221",
    )


def test_barrier_rejects_production_dsn():
    """Hàng rào 1: DSN không kết thúc bằng '_test' (vd trỏ vào DB trading thật) -> từ chối chạy."""
    cfg = make_dummy_config("postgresql://trading:trading@127.0.0.1:5432/trading")
    with pytest.raises(ValueError) as exc:
        verify_safety_barriers(cfg)
    assert "HÀNG RÀO AN TOÀN CHẶN: DSN database 'trading' không kết thúc bằng '_test'" in str(exc.value)


def test_barrier_rejects_real_trading_enabled():
    """Hàng rào 2: real_trading_enabled = True -> từ chối chạy ngay cả khi DSN là trading_test."""
    cfg = make_dummy_config("postgresql://trading:trading@127.0.0.1:5432/trading_test", real_trading_enabled=True)
    with pytest.raises(ValueError) as exc:
        verify_safety_barriers(cfg)
    assert "real_trading_enabled đang là True" in str(exc.value)


@pytest.mark.asyncio
async def test_rehearse_flow_unit(monkeypatch, capsys):
    """Kiểm tra toàn bộ 4 bước của rehearse() với mock storage."""
    cfg = make_dummy_config("postgresql://trading:trading@127.0.0.1:5432/trading_test", real_trading_enabled=False)

    orders_db = {}
    current_id = [1230]

    def fake_create_pending_order(account_no, symbol, side, quantity, price, expires_at):
        oid = current_id[0]
        current_id[0] += 1
        orders_db[oid] = {
            "id": oid,
            "account_no": account_no,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "created_at": datetime.now(TZ),
            "expires_at": expires_at,
            "status": "pending",
        }
        return oid

    def fake_get_pending_order(oid):
        return orders_db.get(oid)

    def fake_update_pending_order_status(oid, status, ssi_order_id=None):
        if oid in orders_db:
            orders_db[oid]["status"] = status

    mock_storage = MagicMock(spec=Storage)
    mock_storage.create_pending_order.side_effect = fake_create_pending_order
    mock_storage.get_pending_order.side_effect = fake_get_pending_order
    mock_storage.update_pending_order_status.side_effect = fake_update_pending_order_status

    oid = await rehearse(cfg, mock_storage)

    assert oid == 1230
    assert orders_db[1230]["status"] == "confirmed"

    out = capsys.readouterr().out
    assert "=== BƯỚC 1: ĐÃ TẠO ĐƠN CHỜ DIỄN TẬP ===" in out
    assert "Order ID: 1230" in out
    assert "=== BƯỚC 2: CÂU LỆNH XÁC NHẬN CẦN GÕ ===" in out
    assert "uv run --with ssi-sdk python scripts/confirm_real_order.py 1230" in out
    assert "=== BƯỚC 3: TIẾN HÀNH XÁC NHẬN (CONFIRM YES / DRY-RUN) ===" in out
    assert "[DRY-RUN] SẼ đặt lệnh: BUY 100 IJC @ 7330.0" in out
    assert "=== BƯỚC 4: TRẠNG THÁI ĐƠN SAU KHI XÁC NHẬN ===" in out
    assert "Order ID: 1230 | Status: confirmed" in out
