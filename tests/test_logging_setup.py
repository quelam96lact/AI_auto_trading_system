"""Unit tests cho trading/logging_setup.py (Brief 63 Task 3)."""

import logging
from pathlib import Path

import pytest

from trading.alerts import alert
from trading.logging_setup import (
    DEFAULT_LOG_FILE,
    HANDLER_NAME,
    attach_durable_alert_handler,
)


@pytest.fixture(autouse=True)
def _cleanup_alert_handlers():
    """Đảm bảo dọn sạch handler sau mỗi test để không ảnh hưởng lẫn nhau."""
    alerts_logger = logging.getLogger("trading.alerts")
    to_remove = [h for h in alerts_logger.handlers if h.get_name() == HANDLER_NAME]
    for h in to_remove:
        h.close()
        alerts_logger.removeHandler(h)
    yield
    to_remove = [h for h in alerts_logger.handlers if h.get_name() == HANDLER_NAME]
    for h in to_remove:
        h.close()
        alerts_logger.removeHandler(h)


def test_attach_durable_alert_handler_idempotent(tmp_path: Path):
    """1. Test idempotency: gọi attach_durable_alert_handler 2 lần chỉ tạo đúng 1 handler."""
    alerts_logger = logging.getLogger("trading.alerts")

    # Gọi lần 1
    attach_durable_alert_handler(log_dir=tmp_path)
    # Gọi lần 2
    attach_durable_alert_handler(log_dir=tmp_path)

    named_handlers = [h for h in alerts_logger.handlers if h.get_name() == HANDLER_NAME]
    assert len(named_handlers) == 1


def test_attach_durable_alert_handler_writes_log(tmp_path: Path):
    """2. Test bền vững: ghi log qua trading.alerts/alert() và kiểm tra file log tồn tại, có nội dung."""
    attach_durable_alert_handler(log_dir=tmp_path)

    # Ghi alert CRITICAL qua hàm alert() dùng chung của toàn hệ thống
    alert("CRITICAL", "test durable alert from engine or collector", detail="verified_test")

    log_file = tmp_path / DEFAULT_LOG_FILE
    assert log_file.exists()

    content = log_file.read_text(encoding="utf-8")
    assert "test durable alert from engine or collector" in content
    assert "CRITICAL" in content
    assert "verified_test" in content
    # Kiểm tra định dạng ISO-8601 UTC kết thúc bằng Z
    assert "Z {" in content or "Z " in content
