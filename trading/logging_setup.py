"""Module thiết lập logging dùng chung cho collector và engine.

Cung cấp hàm attach_durable_alert_handler để gắn RotatingFileHandler vào
logger "trading.alerts", ghi log ra volume mount /app/logs một cách bền vững.
"""

import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_LOG_DIR = "/app/logs"
DEFAULT_LOG_FILE = "bars_closed.log"
HANDLER_NAME = "trading-alerts-file"
MAX_BYTES = 5 * 1024 * 1024  # 5MB
BACKUP_COUNT = 5


class AlertUtcIsoFormatter(logging.Formatter):
    """Formatter ISO-8601 UTC kết thúc bằng Z giống định dạng docker logs -t."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        return f"{ts} {record.getMessage()}"


def attach_durable_alert_handler(
    log_dir: str | Path = DEFAULT_LOG_DIR,
    filename: str = DEFAULT_LOG_FILE,
) -> None:
    """Gắn RotatingFileHandler vào logger "trading.alerts" nếu thư mục log_dir tồn tại.

    - Chỉ gắn khi log_dir là thư mục thực sự (thường là volume mount trong container).
    - Idempotent: không gắn trùng nếu handler "trading-alerts-file" đã tồn tại.
    - Xoay vòng: maxBytes=5MB, backupCount=5, mã hoá utf-8.
    - Bọc try/except toàn bộ: tuyệt đối không ném exception.
    """
    try:
        path = Path(log_dir)
        if not path.is_dir():
            return

        alerts_logger = logging.getLogger("trading.alerts")
        if any(h.get_name() == HANDLER_NAME for h in alerts_logger.handlers):
            return

        log_file = path / filename
        handler = RotatingFileHandler(
            str(log_file),
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(AlertUtcIsoFormatter())
        handler.setLevel(logging.INFO)
        handler.set_name(HANDLER_NAME)
        alerts_logger.addHandler(handler)
    except Exception:
        pass
