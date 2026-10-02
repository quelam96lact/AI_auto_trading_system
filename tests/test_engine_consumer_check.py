"""Unit tests cho Chuông 2C (scripts/engine_consumer_check.py) — Brief đợt 25 Task 2 / Brief đợt 26 Task 5 / Brief đợt 27 Task 1.

Tất định, dùng mock, KHÔNG kết nối NATS/DB thật trong pytest:
1. Consumer khỏe (num_pending=0, seq tiến) => exit 0, không gửi telegram.
2. num_pending vượt ngưỡng trong giờ giao dịch => exit 1, có gọi gửi cảnh báo.
3. Cùng tình huống nhưng ngoài giờ giao dịch => exit 0, không gửi.
4. Không kết nối được NATS => exit 1, gửi cảnh báo, không crash.
5. Biến môi trường SSI_* rỗng => script vẫn chạy bình thường không crash / không exit 2 do thiếu SSI.
"""

from unittest.mock import AsyncMock, MagicMock

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

    fake_info = FakeConsumerInfo(num_pending=0, stream_seq=100)
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=(fake_info, 100)))

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

    fake_info = FakeConsumerInfo(num_pending=25, stream_seq=100)  # > threshold 20
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=(fake_info, 125)))

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

    fake_info = FakeConsumerInfo(num_pending=0, stream_seq=50)
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=(fake_info, 50)))

    sent_alerts = []
    monkeypatch.setattr(ecc, "send_telegram", lambda msg: sent_alerts.append(msg))

    code = ecc.run_check()
    assert code == 0
    assert len(sent_alerts) == 0


def test_backfill_db_bars_increase_but_stream_seq_unchanged_does_not_alert(monkeypatch, tmp_path):
    """Tái hiện lỗi chuông 2C: DB tăng sau backfill nhưng stream last_seq và delivered không đổi -> KHÔNG được kêu."""
    state_file = tmp_path / ".state.json"
    monkeypatch.setattr(ecc, "STATE_FILE", state_file)
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: True)

    # Giả lập state trước đó: seq=100, last_seq=100
    ecc.save_state({"stream_seq": 100, "last_seq": 100, "ts": 1000.0, "last_alert_ts": 0})

    # Giả lập lần đọc hiện tại: stream_seq vẫn 100, last_seq vẫn 100, num_pending=0
    fake_info = FakeConsumerInfo(num_pending=0, stream_seq=100)
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=(fake_info, 100)))

    sent_alerts = []
    monkeypatch.setattr(ecc, "send_telegram", lambda msg: sent_alerts.append(msg))

    code = ecc.run_check()
    assert code == 0
    assert len(sent_alerts) == 0


def test_stream_advances_but_consumer_stalled_alerts_and_returns_one(monkeypatch, tmp_path):
    """last_seq tiến, delivered.stream_seq đứng im, khoảng cách vượt ngưỡng => kêu."""
    state_file = tmp_path / ".state.json"
    monkeypatch.setattr(ecc, "STATE_FILE", state_file)
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: True)

    # State trước: seq=100, last_seq=100
    ecc.save_state({"stream_seq": 100, "last_seq": 100, "ts": 1000.0, "last_alert_ts": 0})

    # Lần này: stream_seq vẫn 100, last_seq tiến lên 125 (gap 25 >= threshold 20), num_pending=0
    fake_info = FakeConsumerInfo(num_pending=0, stream_seq=100)
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=(fake_info, 125)))

    sent_alerts = []
    monkeypatch.setattr(ecc, "send_telegram", lambda msg: sent_alerts.append(msg))

    code = ecc.run_check(pending_threshold=20)
    assert code == 1
    assert len(sent_alerts) == 1
    assert "CHUÔNG 2C" in sent_alerts[0]
    assert "engine dừng tiêu thụ bar" in sent_alerts[0]
    assert "stream_last_seq" in sent_alerts[0]


def test_both_stream_and_consumer_advance_healthy_returns_zero(monkeypatch, tmp_path):
    """Cả stream last_seq và delivered.stream_seq cùng tiến => không kêu."""
    state_file = tmp_path / ".state.json"
    monkeypatch.setattr(ecc, "STATE_FILE", state_file)
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: True)

    # State trước: seq=100, last_seq=100
    ecc.save_state({"stream_seq": 100, "last_seq": 100, "ts": 1000.0, "last_alert_ts": 0})

    # Lần này: cả hai cùng tiến lên 125
    fake_info = FakeConsumerInfo(num_pending=0, stream_seq=125)
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=(fake_info, 125)))

    sent_alerts = []
    monkeypatch.setattr(ecc, "send_telegram", lambda msg: sent_alerts.append(msg))

    code = ecc.run_check(pending_threshold=20)
    assert code == 0
    assert len(sent_alerts) == 0


def test_send_telegram_failure_does_not_update_last_alert_ts(monkeypatch, tmp_path):
    """Brief 57 Task 2: Khi send_telegram trả False -> last_alert_ts KHÔNG được cập nhật."""
    state_file = tmp_path / ".state.json"
    monkeypatch.setattr(ecc, "STATE_FILE", state_file)
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: True)

    ecc.save_state({"stream_seq": 100, "last_seq": 100, "ts": 1000.0, "last_alert_ts": 0.0})

    fake_info = FakeConsumerInfo(num_pending=0, stream_seq=100)
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=(fake_info, 130)))
    monkeypatch.setattr(ecc, "send_telegram", lambda msg: False)

    code = ecc.run_check(pending_threshold=20)
    assert code == 1

    new_state = ecc.load_state()
    assert new_state.get("last_alert_ts") == 0.0, "last_alert_ts không được cập nhật khi gửi thất bại"


def test_send_telegram_success_updates_last_alert_ts(monkeypatch, tmp_path):
    """Brief 57 Task 2: Khi send_telegram trả True -> last_alert_ts CÓ được cập nhật."""
    state_file = tmp_path / ".state.json"
    monkeypatch.setattr(ecc, "STATE_FILE", state_file)
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: True)

    ecc.save_state({"stream_seq": 100, "last_seq": 100, "ts": 1000.0, "last_alert_ts": 0.0})

    fake_info = FakeConsumerInfo(num_pending=0, stream_seq=100)
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=(fake_info, 130)))
    monkeypatch.setattr(ecc, "send_telegram", lambda msg: True)

    code = ecc.run_check(pending_threshold=20)
    assert code == 1

    new_state = ecc.load_state()
    assert new_state.get("last_alert_ts") > 0.0, "last_alert_ts phải được cập nhật khi gửi thành công"


def test_state_file_la_list_khong_nem_coi_nhu_lan_dau(monkeypatch, tmp_path):
    """Brief 146: File trạng thái chứa JSON là list [] thay vì dict: coi như lần đầu, không ném exception."""
    state_file = tmp_path / ".state.json"
    state_file.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(ecc, "STATE_FILE", state_file)
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: True)

    fake_info = FakeConsumerInfo(num_pending=0, stream_seq=100)
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=(fake_info, 100)))

    sent_alerts = []
    monkeypatch.setattr(ecc, "send_telegram", lambda msg: sent_alerts.append(msg))

    code = ecc.run_check(state_file=state_file)
    assert code == 0
    saved = ecc.load_state(state_file)
    assert saved["stream_seq"] == 100
    assert saved["last_seq"] == 100
    assert saved["last_alert_ts"] == 0


def test_state_file_cli_flag(tmp_path):
    """Brief 146: Cờ --state-file được parser nhận diện chính xác."""
    sf = tmp_path / "custom_state.json"
    parser = ecc.build_parser()
    args = parser.parse_args(["--state-file", str(sf)])
    assert args.state_file == str(sf)


def test_main_passes_state_file_to_run_check(monkeypatch, tmp_path):
    """Brief 147: main() truyền cờ --state-file xuống run_check và file được ghi tại tmp_path."""
    custom_state = tmp_path / "custom_engine_state.json"
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: True)

    fake_info = FakeConsumerInfo(num_pending=0, stream_seq=100)
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=(fake_info, 100)))
    monkeypatch.setattr(ecc, "send_telegram", lambda msg: True)

    real_run_check = ecc.run_check
    spy_kwargs = {}

    def spy_run_check(*args, **kwargs):
        spy_kwargs.update(kwargs)
        return real_run_check(*args, **kwargs)

    monkeypatch.setattr(ecc, "run_check", spy_run_check)

    with pytest.raises(SystemExit) as exc_info:
        ecc.main(["--state-file", str(custom_state)])
    assert exc_info.value.code == 0

    # Khẳng định 1: run_check nhận đúng tham số state_file
    assert spy_kwargs.get("state_file") == str(custom_state)

    # Khẳng định 2: file trạng thái được ghi đúng tại tmp_path và có nội dung đúng
    assert custom_state.is_file()
    saved = ecc.load_state(custom_state)
    assert saved["stream_seq"] == 100
    assert saved["last_seq"] == 100


def test_save_state_error_healthy_does_not_crash(monkeypatch, tmp_path, capsys):
    """Brief 147: Lỗi ghi file trạng thái khi engine khỏe không làm chết job, exit 0."""
    custom_state = tmp_path / "state.json"
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: True)

    fake_info = FakeConsumerInfo(num_pending=0, stream_seq=100)
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=(fake_info, 100)))
    monkeypatch.setattr(ecc, "save_json_state", MagicMock(side_effect=OSError("Disk full")))

    code = ecc.run_check(state_file=custom_state)
    assert code == 0

    captured = capsys.readouterr()
    assert "Không thể ghi file state" in captured.out
    assert "Disk full" in captured.out


def test_save_state_error_faulty_does_not_crash(monkeypatch, tmp_path, capsys):
    """Brief 147: Lỗi ghi file trạng thái khi có sự cố không làm chết job, exit 1."""
    custom_state = tmp_path / "state.json"
    monkeypatch.setattr(ecc, "is_trading_time", lambda now, hol: True)

    fake_info = FakeConsumerInfo(num_pending=25, stream_seq=100)
    monkeypatch.setattr(ecc, "read_nats_consumer_info", AsyncMock(return_value=(fake_info, 125)))
    monkeypatch.setattr(ecc, "send_telegram", lambda msg: True)
    monkeypatch.setattr(ecc, "save_json_state", MagicMock(side_effect=OSError("Permission denied")))

    code = ecc.run_check(pending_threshold=20, state_file=custom_state)
    assert code == 1

    captured = capsys.readouterr()
    assert "Không thể ghi file state" in captured.out
    assert "Permission denied" in captured.out



