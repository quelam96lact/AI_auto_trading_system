"""Unit tests cho Chuông 2C (scripts/engine_consumer_check.py) — Brief đợt 25 Task 2 / Brief đợt 26 Task 5.

Tất định, dùng mock, KHÔNG kết nối NATS/DB thật trong pytest:
1. Consumer khỏe (num_pending=0, seq tiến) => exit 0, không gửi telegram.
2. num_pending vượt ngưỡng trong giờ giao dịch => exit 1, có gọi gửi cảnh báo.
3. Cùng tình huống nhưng ngoài giờ giao dịch => exit 0, không gửi.
4. Không kết nối được NATS => exit 1, gửi cảnh báo, không crash.
"""

from unittest.mock import AsyncMock

import pytest

import scripts.engine_consumer_check as ecc
from trading.config import Config


@pytest.fixture
def mock_cfg():
    return Config(
        symbols=["VCB"],
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


class FakeDelivered:
    def __init__(self, stream_seq):
        self.stream_seq = stream_seq


class FakeConsumerInfo:
    def __init__(self, num_pending=0, stream_seq=100):
        self.num_pending = num_pending
        self.delivered = FakeDelivered(stream_seq)


def test_consumer_healthy_returns_zero(mock_cfg, monkeypatch, tmp_path):
    """1. Consumer khỏe (num_pending=0, seq tiến) => exit 0, không gửi telegram."""
    state_file = tmp_path / ".state.json"
    monkeypatch.setattr(ecc, "STATE_FILE", state_file)
    monkeypatch.setattr(ecc, "load_config", lambda *a: mock_cfg)
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: True)
    monkeypatch.setattr(ecc, "read_today_bars_count", lambda dsn: 50)

    fake_info = FakeConsumerInfo(num_pending=0, stream_seq=100)
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=fake_info))

    sent_alerts = []
    monkeypatch.setattr(ecc, "send_telegram", lambda cfg, msg: sent_alerts.append(msg))

    code = ecc.run_check()
    assert code == 0
    assert len(sent_alerts) == 0


def test_consumer_pending_in_trading_hours_alerts_and_returns_one(mock_cfg, monkeypatch, tmp_path):
    """2. num_pending vượt ngưỡng trong giờ giao dịch => exit 1, có gọi gửi cảnh báo."""
    state_file = tmp_path / ".state.json"
    monkeypatch.setattr(ecc, "STATE_FILE", state_file)
    monkeypatch.setattr(ecc, "load_config", lambda *a: mock_cfg)
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: True)
    monkeypatch.setattr(ecc, "read_today_bars_count", lambda dsn: 50)

    fake_info = FakeConsumerInfo(num_pending=25, stream_seq=100)  # > threshold 20
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=fake_info))

    sent_alerts = []
    monkeypatch.setattr(ecc, "send_telegram", lambda cfg, msg: sent_alerts.append(msg))

    code = ecc.run_check(pending_threshold=20)
    assert code == 1
    assert len(sent_alerts) == 1
    assert "CHUÔNG 2C" in sent_alerts[0]
    assert "num_pending vượt ngưỡng" in sent_alerts[0]


def test_consumer_pending_outside_trading_hours_skipped(mock_cfg, monkeypatch, tmp_path):
    """3. Cùng tình huống nhưng ngoài giờ giao dịch => exit 0, không gửi."""
    state_file = tmp_path / ".state.json"
    monkeypatch.setattr(ecc, "STATE_FILE", state_file)
    monkeypatch.setattr(ecc, "load_config", lambda *a: mock_cfg)
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: False)

    sent_alerts = []
    monkeypatch.setattr(ecc, "send_telegram", lambda cfg, msg: sent_alerts.append(msg))

    code = ecc.run_check(force=False)
    assert code == 0
    assert len(sent_alerts) == 0


def test_nats_connection_failure_alerts_and_returns_one(mock_cfg, monkeypatch, tmp_path):
    """4. Không kết nối được NATS => exit 1, gửi cảnh báo, không crash."""
    state_file = tmp_path / ".state.json"
    monkeypatch.setattr(ecc, "STATE_FILE", state_file)
    monkeypatch.setattr(ecc, "load_config", lambda *a: mock_cfg)
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: True)
    monkeypatch.setattr(ecc, "read_today_bars_count", lambda dsn: 50)

    monkeypatch.setattr(
        ecc,
        "read_nats_consumer_info",
        AsyncMock(side_effect=ConnectionError("NATS server unreachable")),
    )

    sent_alerts = []
    monkeypatch.setattr(ecc, "send_telegram", lambda cfg, msg: sent_alerts.append(msg))

    code = ecc.run_check()
    assert code == 1
    assert len(sent_alerts) == 1
    assert "Không thể kết nối NATS" in sent_alerts[0]
