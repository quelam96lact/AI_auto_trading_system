"""Module thiết lập logging dùng chung cho collector và engine.

Cung cấp:
- attach_durable_alert_handler: gắn RotatingFileHandler vào logger cha "trading",
  ghi log ra volume mount /app/logs một cách bền vững.
- silence_ssi_sdk_secrets: nâng level logger ssi_sdk.transport.websocket lên WARNING
  để chặn token SSI rò ra log (LOG-1).
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


class DurableAlertFilter(logging.Filter):
    """Filter cho phép:
    - Mọi bản ghi từ logger trading.alerts (bất kể mức log).
    - Bản ghi mức WARNING trở lên từ các logger khác trong cây trading.*.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith("trading.alerts"):
            return True
        return record.levelno >= logging.WARNING


def attach_durable_alert_handler(
    log_dir: str | Path = DEFAULT_LOG_DIR,
    filename: str = DEFAULT_LOG_FILE,
) -> None:
    """Gắn RotatingFileHandler vào logger "trading" nếu thư mục log_dir tồn tại.

    - Chỉ gắn khi log_dir là thư mục thực sự (thường là volume mount trong container).
    - Idempotent: không gắn trùng nếu handler "trading-alerts-file" đã tồn tại.
    - Xoay vòng: maxBytes=5MB, backupCount=5, mã hoá utf-8.
    - Bọc try/except toàn bộ: tuyệt đối không ném exception.
    """
    try:
        path = Path(log_dir)
        if not path.is_dir():
            return

        trading_logger = logging.getLogger("trading")
        if any(h.get_name() == HANDLER_NAME for h in trading_logger.handlers):
            return

        log_file = path / filename
        handler = RotatingFileHandler(
            str(log_file),
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(AlertUtcIsoFormatter())
        handler.addFilter(DurableAlertFilter())
        handler.setLevel(logging.INFO)
        handler.set_name(HANDLER_NAME)
        trading_logger.addHandler(handler)
    except Exception:
        pass


def silence_ssi_sdk_secrets() -> None:
    """Nâng level logger ssi_sdk.transport.websocket lên WARNING để chặn token rò (LOG-1).

    LOG-1: bịt access token rò ra log. ssi_sdk.transport.websocket_client.py:76
    log `logger.info("Connecting to WebSocket with headers: %s", self._headers)`
    — self._headers chứa `Authorization: Bearer <token>` plaintext (token sống
    15 phút nhưng log được giữ lâu hơn). Nâng level logger NÀY lên WARNING
    (không phải filter regex — một dòng setLevel giải quyết trọn vẹn, regex
    phải bảo trì và hỏng lặng lẽ khi SDK đổi format). Đánh đổi: mất dòng
    INFO "WebSocket connected to wss://..." — chấp nhận vì lỗi kết nối vẫn
    hiện ("SSIFeed connection error") và collector có heartbeat riêng trong
    bảng heartbeat. KHÔNG đụng logger ssi_sdk.services.token_manager — nó log
    "Token refreshed successfully", hữu ích và không chứa secret.

    Gọi sau mọi chỗ cấu hình logging khác và trước khi tạo AsyncStream / AsyncAuth
    để tránh bị basicConfig hay SDK tự khởi tạo đè lại.
    """
    logging.getLogger("ssi_sdk.transport.websocket").setLevel(logging.WARNING)
