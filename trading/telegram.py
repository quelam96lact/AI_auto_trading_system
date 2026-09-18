import json
import logging
import os
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram(text: str) -> bool:
    """Gửi tin nhắn cảnh báo tới Telegram bot.

    FEE-ALARM-2: Chuông báo chết câm còn tệ hơn không có chuông báo.
    Hàm này KHÔNG BAO GIỜ ném exception ra ngoài caller:
    - Trả True nếu Telegram API xác nhận đã nhận (HTTP 200 và response JSON có 'ok': True).
    - Trả False nếu thiếu cấu hình, lỗi mạng, HTTP error, hoặc Telegram trả 'ok': False.
      Mọi trường hợp thất bại đều được ghi log mức WARNING kèm lý do chi tiết.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    missing_vars = []
    if not token:
        missing_vars.append("TELEGRAM_BOT_TOKEN")
    if not chat_id:
        missing_vars.append("TELEGRAM_CHAT_ID")
    if missing_vars:
        logger.warning(
            "Khong the gui Telegram vi thieu bien moi truong: %s",
            ", ".join(missing_vars),
        )
        return False

    data = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        _API_URL.format(token=token),
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw_body = resp.read()
            payload: dict[str, Any] = json.loads(raw_body.decode("utf-8"))
            if payload.get("ok") is True:
                return True
            logger.warning("Telegram API tra ve loi: %s", payload)
            return False
    except Exception as e:
        logger.warning("Loi khi gui tin Telegram: %s: %s", type(e).__name__, e)
        return False
