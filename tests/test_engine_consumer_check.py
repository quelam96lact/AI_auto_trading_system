"""Unit tests cho Chuông 2C (scripts/engine_consumer_check.py) — Brief đợt 25 Task 2 / Brief đợt 26 Task 5 / Brief đợt 27 Task 1.

Tất định, dùng mock, KHÔNG kết nối NATS/DB thật trong pytest:
1. Consumer khỏe (num_pending=0, seq tiến) => exit 0, không gửi telegram.
2. num_pending vượt ngưỡng trong giờ giao dịch => exit 1, có gọi gửi cảnh báo.
3. Cùng tình huống nhưng ngoài giờ giao dịch => exit 0, không gửi.
4. Không kết nối được NATS => exit 1, gửi cảnh báo, không crash.
5. Biến môi trường SSI_* rỗng => script vẫn chạy bình thường không crash / không exit 2 do thiếu SSI.
"""

from unittest.mock import AsyncMock

import pytest

import scripts.engine_consumer_check as ecc


class FakeDelivered:
    def __init__(self, stream_seq):
        self.stream_seq = stream_seq


class FakeConsumerInfo:
    def __init__(self, num_pending=0, stream_seq=100):
        self.num_pending = num_pending
        self.delivered = FakeDelivered(stream_seq)


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    monkeypatch.setenv("DB_DSN", "postgresql://trading:trading@localhost:5432/trading")


def test_consumer_healthy_returns_zero(monkeypatch, tmp_path):
    """1. Consumer khỏe (num_pending=0, seq tiến) => exit 0, không gửi telegram."""
    state_file = tmp_path / ".state.json"
    monkeypatch.setattr(ecc, "STATE_FILE", state_file)
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: True)
    monkeypatch.setattr(ecc, "read_today_bars_count", lambda dsn: 50)

    fake_info = FakeConsumerInfo(num_pending=0, stream_seq=100)
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=fake_info))

    sent_alerts = []
    monkeypatch.setattr(ecc, "send_telegram", lambda msg: sent_alerts.append(msg))

    code = ecc.run_check()
    assert code == 0
    assert len(sent_alerts) == 0


def test_consumer_pending_in_trading_hours_alerts_and_returns_one(monkeypatch, tmp_path):
    """2. num_pending vượt ngưỡng trong giờ giao dịch => exit 1, có gọi gửi cảnh báo."""
    state_file = tmp_path / ".state.json"
    monkeypatch.setattr(ecc, "STATE_FILE", state_file)
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: True)
    monkeypatch.setattr(ecc, "read_today_bars_count", lambda dsn: 50)

    fake_info = FakeConsumerInfo(num_pending=25, stream_seq=100)  # > threshold 20
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=fake_info))

    sent_alerts = []
    monkeypatch.setattr(ecc, "send_telegram", lambda msg: sent_alerts.append(msg))

    code = ecc.run_check(pending_threshold=20)
    assert code == 1
    assert len(sent_alerts) == 1
    assert "CHUÔNG 2C" in sent_alerts[0]
    assert "num_pending vượt ngưỡng" in sent_alerts[0]


def test_consumer_pending_outside_trading_hours_skipped(monkeypatch, tmp_path):
    """3. Cùng tình huống nhưng ngoài giờ giao dịch => exit 0, không gửi."""
    state_file = tmp_path / ".state.json"
    monkeypatch.setattr(ecc, "STATE_FILE", state_file)
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: False)

    sent_alerts = []
    monkeypatch.setattr(ecc, "send_telegram", lambda msg: sent_alerts.append(msg))

    code = ecc.run_check(force=False)
    assert code == 0
    assert len(sent_alerts) == 0


def test_nats_connection_failure_alerts_and_returns_one(monkeypatch, tmp_path):
    """4. Không kết nối được NATS => exit 1, gửi cảnh báo, không crash."""
    state_file = tmp_path / ".state.json"
    monkeypatch.setattr(ecc, "STATE_FILE", state_file)
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: True)
    monkeypatch.setattr(ecc, "read_today_bars_count", lambda dsn: 50)

    monkeypatch.setattr(
        ecc,
        "read_nats_consumer_info",
        AsyncMock(side_effect=ConnectionError("NATS server unreachable")),
    )

    sent_alerts = []
    monkeypatch.setattr(ecc, "send_telegram", lambda msg: sent_alerts.append(msg))

    code = ecc.run_check()
    assert code == 1
    assert len(sent_alerts) == 1
    assert "Không thể kết nối NATS" in sent_alerts[0]


def test_missing_ssi_env_vars_still_reaches_consumer_check(monkeypatch, tmp_path):
    """5. Biến môi trường SSI_* rỗng => script vẫn chạy bình thường tới bước đọc consumer."""
    for ssi_key in [
        "SSI_CONSUMER_ID",
        "SSI_CONSUMER_SECRET",
        "SSI_API_KEY",
        "SSI_API_SECRET",
        "SSI_PRIVATE_KEY",
    ]:
        monkeypatch.setenv(ssi_key, "")

    state_file = tmp_path / ".state.json"
    monkeypatch.setattr(ecc, "STATE_FILE", state_file)
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: True)
    monkeypatch.setattr(ecc, "read_today_bars_count", lambda dsn: 10)

    fake_info = FakeConsumerInfo(num_pending=0, stream_seq=50)
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=fake_info))

    sent_alerts = []
    monkeypatch.setattr(ecc, "send_telegram", lambda msg: sent_alerts.append(msg))

    code = ecc.run_check()
    assert code == 0
    assert len(sent_alerts) == 0
