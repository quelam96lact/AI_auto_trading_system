import json
import logging
import threading

from trading.telegram import send_telegram

_log = logging.getLogger("trading.alerts")
_LEVELS = {"INFO": logging.INFO, "WARN": logging.WARNING, "CRITICAL": logging.CRITICAL}
_NOTIFY_LEVELS = {"WARN", "CRITICAL"}


def alert(level: str, msg: str, **fields) -> None:
    _log.log(_LEVELS[level], json.dumps({"level": level, "msg": msg, **fields}, ensure_ascii=False))
    if level in _NOTIFY_LEVELS:
        text = f"[{level}] {msg}" + (f" {fields}" if fields else "")
        threading.Thread(target=send_telegram, args=(text,), daemon=True).start()
