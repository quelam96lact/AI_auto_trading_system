"""Chuông báo: Docker tắt trong giờ giao dịch mà không ai biết.

Brief dot 8 (02/09/2026). run_if_docker_up.sh doi mot loai tieng on (loi ket
noi DB) lay mot loai im lang nguy hiem hon: Docker chet => moi job giam sat
bi bo qua, chi ghi dong SKIP vao file log khong ai mo. Do duoc 02/09: 85 lan
SKIP lien tiep, khong mot tin Telegram nao.

Script nay duoc goi TU nhanh Docker-chet cua cong, tu quyet dinh co keu khong.
send_telegram chi dung urllib + 2 bien moi truong (trading/telegram.py:8) —
khong cham DB, khong cham Docker, nen chay duoc DUNG LUC Docker chet.

Exit code: luon 0 (chuong bao khong duoc nem — FEE-ALARM-2).
"""

import os
import sys
from datetime import date, datetime, time

import yaml

from scripts.heartbeat_check import in_bar_check_window

# Dung LAI logic ngay le cua heartbeat_check (4ea4c8d: mot cong thuc hai noi
# thi som muon lech — lech o day nghia la hai chuong bat dong y ve "hom nay co
# phai ngay giao dich khong"). Da kiem: heartbeat_check an toan khi import
# (module-level chi import + dinh nghia, khong chay gi — 0.66s, khong side
# effect). KHONG sua heartbeat_check.py — chi import.
from trading.alerts import _print_safe
from trading.calendar_vn import TZ
from trading.telegram import send_telegram

# Khung 08:00-15:00 T2-T6 la khung cua scheduled task heartbeat
# (DEPLOYMENT.md:225). KHONG tu nghi ra khung khac.
ALERT_START = time(8, 0)
ALERT_END = time(15, 0)

# Chong spam: khong gui lan hai trong vong 30 phut.
SPAM_GUARD_SECONDS = 30 * 60

# File dau moc lan gui cuoi. Nam trong logs/ (gitignored) nhu cac file log.
# Doc hong/khong co => coi nhu chua tung gui (fail-safe nghieng ve KEU).
SPAM_GUARD_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logs",
    ".docker_down_last_alert",
)


def load_holidays() -> frozenset:
    """Nap holidays tu config.yaml — CUNG CACH heartbeat_check main() dong
    217-219 (doc yaml truc tiep; co y KHONG import load_config(): ham do doi
    day du SSI_* trong moi truong, ma chuong bao phai chay duoc ngay ca khi
    cau hinh SSI thieu)."""
    cfg_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config",
        "config.yaml",
    )
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return frozenset(date.fromisoformat(str(h)) for h in (cfg.get("holidays") or []))


def _is_trading_day(now: datetime, holidays: frozenset) -> bool:
    """Hom nay co phai ngay giao dich khong (T2-T6, khong le)?

    Hoi chinh in_bar_check_window cua heartbeat_check tai moc 10:00 — gio do
    LUON nam trong CHECK_SESSIONS (phien sang 9:00-11:30), nen ket qua chi con
    phu thuoc phan NGAY (weekday < 5 va khong nam trong holidays), khong phu
    thuoc gio. Nhu vay neu heartbeat_check doi dinh nghia ngay giao dich
    (them ngay nghi dac biet, doi ngay cuoi tuan...), chuong nay tu theo —
    khong chep lai dieu kien `weekday() >= 5 or date in holidays`.
    """
    probe = now.astimezone(TZ).replace(hour=10, minute=0, second=0, microsecond=0)
    return in_bar_check_window(probe, holidays)


def _read_last_alert(stamp_file: str) -> int | None:
    """Epoch lan gui cuoi; None = chua tung gui / doc hong."""
    try:
        with open(stamp_file, encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def _write_last_alert(now: datetime, stamp_file: str) -> None:
    try:
        with open(stamp_file, "w", encoding="utf-8") as f:
            f.write(str(int(now.timestamp())))
    except Exception:
        pass  # ghi hong khong duoc lam chet chuong — lan sau co the keu lai


def should_alert(now: datetime, holidays: frozenset, last_alert_epoch: int | None) -> bool:
    """Quyet dinh co keu khong, theo bang cua brief dot 8:
    - trong khung 08:00-15:00 ngay giao dich (T2-T6, khong le)  => KEU
    - ngoai khung / T7-CN / ngay le                              => im
    - da gui trong 30 phut gan nhat                              => im
    """
    now = now.astimezone(TZ)
    if not (ALERT_START <= now.time() <= ALERT_END):
        return False
    if not _is_trading_day(now, holidays):
        return False
    return not (last_alert_epoch is not None and now.timestamp() - last_alert_epoch < SPAM_GUARD_SECONDS)


def _message(now: datetime) -> str:
    """Phai tra loi duoc: cai gi dang khong chay va hau qua la gi."""
    now = now.astimezone(TZ)
    return (
        f"[CRITICAL] Docker khong chay luc {now:%H:%M} ngay giao dich {now:%d/%m}.\n"
        "Collector/engine deu dung. Khong co bar moi, khong co lenh.\n"
        "Cac job giam sat dang bi bo qua — day la tin nhan DUY NHAT ban se nhan."
    )
def run_alert(
    now: datetime,
    holidays: frozenset,
    send=send_telegram,
    stamp_file: str = SPAM_GUARD_FILE,
) -> int:
    """Mot lan kiem: quyet dinh, keu neu can. KHONG BAO GIO nem — chuong bao
    chet cam con te hon khong co chuong bao (FEE-ALARM-2). Tra 0 luon."""
    try:
        last = _read_last_alert(stamp_file)
        if not should_alert(now, holidays, last):
            return 0
        msg = _message(now)
        # In ly do ra stdout TRUOC khi gui — neu send_telegram nem exception
        # thi van con ban ghi o log (khuon heartbeat_check).
        _print_safe(msg)
        try:
            ok = send(msg)
            if ok is not False:
                _write_last_alert(now, stamp_file)
            else:
                _print_safe("[docker-down-alert] gui Telegram that bai: send tra ve False")
                return 0
        except Exception as e:
            _print_safe(f"[docker-down-alert] gui Telegram loi: {type(e).__name__}: {e}")
            return 0
        return 0
    except Exception as e:
        # Lop ngoai cung: loi khong lo truoc (vi du load config hong) cung
        # khong duoc giet chuong — in dau vet roi tra 0.
        _print_safe(f"[docker-down-alert] loi khong lo truoc: {type(e).__name__}: {e}")
        return 0


def main() -> int:
    # Ep utf-8 de ly do canh bao con dau tieng Viet; that bai cung khong sao,
    # _print_safe da co duong lui.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        return run_alert(datetime.now(TZ), load_holidays())
    except Exception as e:
        _print_safe(f"[docker-down-alert] loi khoi dong: {type(e).__name__}: {e}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
