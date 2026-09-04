import json
import logging
import threading

from trading.telegram import send_telegram

_log = logging.getLogger("trading.alerts")
_LEVELS = {"INFO": logging.INFO, "WARN": logging.WARNING, "CRITICAL": logging.CRITICAL}
_NOTIFY_LEVELS = {"WARN", "CRITICAL"}


def _print_safe(text: str) -> None:
    """In ly do canh bao ma KHONG BAO GIO nem (mot ban duy nhat — gop tu
    heartbeat_check/deploy_drift_check/docker_down_alert, goi B2 04/09).

    2026-09-01: print() da lam CHET chuong bao tren Windows. Scheduled task
    chuyen huong stdout ra file, Python chon cp1252, ky tu tieng Viet khong ma
    hoa duoc -> UnicodeEncodeError nem ra TRUOC send_telegram. Nguyen tac
    FEE-ALARM-2: dead-man's switch tuyet doi khong duoc nem.
    """
    try:
        print(text)
        return
    except Exception:
        pass
    # Ha cap: mat dau tieng Viet con hon mat ca canh bao.
    try:
        print(text.encode("ascii", "replace").decode("ascii"))
    except Exception:
        pass


def alert(level: str, msg: str, **fields) -> None:
    _log.log(_LEVELS[level], json.dumps({"level": level, "msg": msg, **fields}, ensure_ascii=False))
    if level in _NOTIFY_LEVELS:
        text = f"[{level}] {msg}" + (f" {fields}" if fields else "")
        threading.Thread(target=send_telegram, args=(text,), daemon=True).start()
