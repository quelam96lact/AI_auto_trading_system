import json
import logging
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

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


# --- Hang doi gui lai (brief dot 143, 02/10/2026) ---------------------------
# Do 72 gio log collector: 12 lan "Loi khi gui tin Telegram: URLError ... Name or
# service not known" — gui hong la canh bao MAT VINH VIEN, dung luc mang te nhat
# (may vua thuc day). Gui hong -> noi mot dong JSON vao file; mot luong nen cu 60s
# gui lai THEO THU TU. Khong goi start_outbox() (script, test) thi hanh vi y nhu cu.
OUTBOX_MAX = 200
OUTBOX_INTERVAL_SECONDS = 60.0
DEFAULT_OUTBOX_DIR = "/app/logs"
_VN_TZ = timezone(timedelta(hours=7))


class AlertOutbox:
    def __init__(
        self,
        path: Path,
        send_fn: Callable[[str], bool] | None = None,
        clock: Callable[[], datetime] | None = None,
        max_items: int = OUTBOX_MAX,
    ) -> None:
        self.path = Path(path)
        # Tra cuu send_telegram luc GOI (khong chup luc dung) de test monkeypatch duoc.
        self._send = send_fn or (lambda text: send_telegram(text))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._max = max_items
        self._lock = threading.Lock()  # moi thao tac doc/ghi file
        self._flush_lock = threading.Lock()  # chi mot lan gui lai tai mot thoi diem
        self._dropped = 0
        self.first_flush_done = threading.Event()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    # -- file (chi goi khi dang giu self._lock) --
    def _read_locked(self) -> list[str]:
        """Cac dong tho cua file. Dong khong phai JSON hop le bi thay bang mot muc
        canh bao (khong lang le bo), roi ghi lai file."""
        try:
            raw = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        lines: list[str] = []
        repaired = False
        for ln in raw:
            if not ln.strip():
                continue
            try:
                d = json.loads(ln)
                if not (isinstance(d, dict) and "text" in d and "emitted_at" in d):
                    raise ValueError("thieu truong")
                lines.append(ln)
            except Exception:
                repaired = True
                lines.append(
                    self._dump(
                        f"[CANH BAO HANG DOI] file {self.path.name} co dong hong, "
                        f"khong doc duoc: {ln[:200]!r}"
                    )
                )
        if repaired:
            self._write_locked(lines)
        return lines

    def _write_locked(self, lines: list[str]) -> None:
        if not lines:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            return
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def _dump(self, text: str) -> str:
        return json.dumps(
            {"emitted_at": self._clock().isoformat(), "text": text},
            ensure_ascii=False,
        )

    # -- API --
    def enqueue(self, text: str) -> None:
        with self._lock:
            lines = self._read_locked()
            lines.append(self._dump(text))
            over = len(lines) - self._max
            if over > 0:
                lines = lines[over:]
                self._dropped += over
            self._write_locked(lines)

    def send_or_queue(self, text: str) -> None:
        """Gui mot lan; hong (False hoac nem) thi vao hang doi. Khong bao gio nem."""
        try:
            ok = bool(self._send(text))
        except Exception:
            ok = False
        if ok:
            return
        try:
            self.enqueue(text)
        except Exception as e:
            _print_safe(
                f"LOI: khong ghi duoc hang doi canh bao ({type(e).__name__}): {text}"
            )

    def pending(self) -> int:
        with self._lock:
            return len(self._read_locked())

    @staticmethod
    def _render(entry: dict) -> str:
        try:
            when = datetime.fromisoformat(entry["emitted_at"]).astimezone(_VN_TZ)
            stamp = when.strftime("%H:%M:%S %d/%m")
        except Exception:
            stamp = str(entry.get("emitted_at"))
        return f"[GỬI TRỄ — phát lúc {stamp}] {entry['text']}"

    def flush(self) -> int:
        """Gui lai theo thu tu, dung o tin dau tien con hong. Tra ve so tin da gui."""
        sent = 0
        with self._flush_lock:
            while True:
                with self._lock:
                    lines = self._read_locked()
                    dropped = self._dropped
                if not lines:
                    return sent
                head = lines[0]
                text = self._render(json.loads(head))
                if dropped:
                    text += f"\n(đã bỏ {dropped} cảnh báo cũ vì hàng đợi đầy)"
                try:
                    ok = bool(self._send(text))
                except Exception:
                    ok = False
                if not ok:
                    return sent
                with self._lock:
                    cur = self._read_locked()
                    if head in cur:
                        cur.remove(head)
                    self._write_locked(cur)
                    self._dropped = max(0, self._dropped - dropped)
                sent += 1

    def _loop(self, interval: float) -> None:
        while not self.stop_event.is_set():
            try:
                self.flush()
            except Exception as e:
                _log.warning("alert outbox flush loi: %s", type(e).__name__)
            self.first_flush_done.set()
            self.stop_event.wait(interval)

    def start(self, interval: float = OUTBOX_INTERVAL_SECONDS) -> None:
        self.thread = threading.Thread(
            target=self._loop, args=(interval,), daemon=True, name="alert-outbox"
        )
        self.thread.start()


_outbox: AlertOutbox | None = None


def start_outbox(
    service: str,
    directory: str | Path | None = None,
    send_fn: Callable[[str], bool] | None = None,
    clock: Callable[[], datetime] | None = None,
    interval: float = OUTBOX_INTERVAL_SECONDS,
    run_thread: bool = True,
) -> AlertOutbox | None:
    """Bat hang doi gui lai cho tien trinh nay. Thu muc khong ton tai (may dev) thi
    KHONG bat gi va tra None — hanh vi y nhu cu."""
    global _outbox
    d = Path(directory if directory is not None else DEFAULT_OUTBOX_DIR)
    if not d.is_dir():
        return None
    box = AlertOutbox(d / f"alert_outbox_{service}.jsonl", send_fn=send_fn, clock=clock)
    _outbox = box
    if run_thread:
        box.start(interval)
    return box


def stop_outbox() -> None:
    global _outbox
    if _outbox is not None:
        _outbox.stop_event.set()
    _outbox = None


def alert(level: str, msg: str, **fields) -> threading.Thread | None:
    _log.log(
        _LEVELS[level],
        json.dumps({"level": level, "msg": msg, **fields}, ensure_ascii=False),
    )
    if level in _NOTIFY_LEVELS:
        text = f"[{level}] {msg}" + (f" {fields}" if fields else "")
        box = _outbox
        if box is not None:
            t = threading.Thread(target=box.send_or_queue, args=(text,), daemon=True)
        else:
            t = threading.Thread(target=send_telegram, args=(text,), daemon=True)
        t.start()
        return t
    return None
