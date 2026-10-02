"""Kiểm tra tính toàn vẹn và độ tươi của bản sao lưu database.

Brief đợt 131 (2026-09-29):
Kiểm tra thư mục sao lưu:
- Không có file sao lưu nào (hoặc thư mục không tồn tại)
- File mới nhất cũ hơn ngưỡng (--max-age-hours, mặc định 26h)
- File mới nhất nhỏ hơn ngưỡng tối thiểu (--min-size-mb, mặc định 80MB)
- pg_restore -l trên file mới nhất hỏng

Mã thoát:
  0: Mọi thứ ổn (file tươi, đủ lớn, kiểm tra toàn vẹn đạt).
  1: Có cảnh báo và đã gửi thành công (hoặc in ra khi --dry-run).
  2: Sai cấu hình, lỗi hệ thống, hoặc cảnh báo cần gửi mà gửi hỏng.

Đợt 135: canh cả bản sao lưu SỔ LỆNH (`orderbook_*.tar.gz` do `backup_orderbook.sh`
sinh ra) — trước đó job đó hỏng thì không cảnh báo nào nổ. HAI LOẠI SAO LƯU CÓ HAI
QUY TẮC KHÁC NHAU VÌ BẢN CHẤT KHÁC NHAU, đừng gộp lại:
  - DB: dump MỖI ĐÊM kể cả cuối tuần -> ngưỡng tuổi cố định 23 giờ (xem dưới).
  - Sổ lệnh: chỉ sinh ra vào NGÀY GIAO DỊCH, job chỉ tạo file khi có dữ liệu mới
    -> tuổi hợp lệ dao động 0,5 giờ (thứ Ba) tới 48,5 giờ (thứ Hai) và hơn 8 ngày
    sau kỳ nghỉ Tết. Không ngưỡng cố định nào đúng cả bốn; dùng LỊCH GIAO DỊCH.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import time
import traceback
from datetime import date, datetime
from datetime import time as dtime
from pathlib import Path
from typing import NamedTuple

import yaml

from trading.alerts import _print_safe
from trading.calendar_vn import TZ, previous_trading_day
from trading.telegram import send_telegram

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Thu muc sao luu. MAC DINH chi dung cho VPS Ubuntu; tren Windows duong dan nay
# vua KHONG ton tai, vua bi Git Bash dich thanh "C:\\Program Files\\Git\\var\\..."
# (do 29/09: backup-check gui CANH BAO GIA moi ngay, disk-check thoat 2 va khong
# he kiem dia). Dat TRADING_BACKUP_DIR trong .env de cai dat nao cung dung duong
# dan cua chinh no; run_if_docker_up.sh nap .env TRUOC khi chay job nen job thay.
DEFAULT_BACKUP_DIR = os.environ.get("TRADING_BACKUP_DIR") or "/var/backups/trading-db"

# 23h, KHONG phai 26h. Phep tinh: job backup chay 02:00, job check chay 03:00.
#   - backup thanh cong -> ban moi nhat 1 gio tuoi.
#   - backup HONG dem nay -> ban moi nhat la cua hom qua, 25 gio tuoi.
# Nguong 26h (ban dau cua brief dot 131) lon hon 25h, nen mot dem backup hong
# KHONG bi phat hien, va phai doi them 24 gio nua. Da do that 29/09: file 25 gio
# tuoi -> cong im, EXIT=0. Nguong phai nam GIUA 1h va 25h; 23h de du bien cho
# backup chay tre hoac lau, ma van bat duoc mot dem bi mat.
# Doi gio cua hai job thi phai tinh lai so nay.
DEFAULT_MAX_AGE_HOURS = 23.0
DEFAULT_MIN_SIZE_MB = 80.0


# Phiên giao dịch kết thúc 14:46 giờ VN (recorder tự dừng lúc đó). Bản sao lưu sổ lệnh
# hợp lệ phải được tạo SAU mốc này của ngày giao dịch gần nhất trước hôm nay.
ORDERBOOK_SESSION_END = dtime(14, 46)
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "config.yaml"


class BackupFileInfo(NamedTuple):
    name: str
    path: str
    size_bytes: int
    mtime: float


def evaluate_backup_health(
    dir_exists: bool,
    latest_file: BackupFileInfo | None,
    pg_restore_status: str,
    now_epoch: float,
    backup_dir: str = DEFAULT_BACKUP_DIR,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    min_size_mb: float = DEFAULT_MIN_SIZE_MB,
) -> list[str]:
    """Hàm đánh giá thuần túy (pure function) cho sức khỏe bản sao lưu.

    pg_restore_status: "OK", "FAIL: <lý do>", hoặc "UNAVAILABLE: <lý do>"
    """
    alerts: list[str] = []

    if not dir_exists:
        alerts.append(f"[CRITICAL] Thư mục sao lưu không tồn tại: {backup_dir}")
        return alerts

    if latest_file is None:
        alerts.append(f"[CRITICAL] Không tìm thấy bản sao lưu nào trong {backup_dir}")
        return alerts

    # 1. Kiểm tra tuổi
    age_hours = (now_epoch - latest_file.mtime) / 3600.0
    if age_hours > max_age_hours:
        alerts.append(
            f"[CRITICAL] Bản sao lưu mới nhất ({latest_file.name}) đã cũ: "
            f"{age_hours:.1f}h (ngưỡng: {max_age_hours:.1f}h)"
        )

    # 2. Kiểm tra kích thước
    size_mb = latest_file.size_bytes / (1024.0 * 1024.0)
    if size_mb < min_size_mb:
        alerts.append(
            f"[CRITICAL] Bản sao lưu mới nhất ({latest_file.name}) quá nhỏ: "
            f"{size_mb:.1f} MB (ngưỡng tối thiểu: {min_size_mb:.1f} MB)"
        )

    # 3. Kiểm tra tính toàn vẹn (pg_restore -l)
    if pg_restore_status.startswith("UNAVAILABLE"):
        reason = (
            pg_restore_status.split(":", 1)[1].strip()
            if ":" in pg_restore_status
            else pg_restore_status
        )
        alerts.append(
            f"[CRITICAL] Không kiểm được tính toàn vẹn của {latest_file.name}: {reason}"
        )
    elif pg_restore_status != "OK":
        alerts.append(
            f"[CRITICAL] Bản sao lưu {latest_file.name} hỏng (pg_restore -l thất bại): {pg_restore_status}"
        )

    return alerts


def evaluate_orderbook_backup(
    latest_file: BackupFileInfo | None,
    integrity_status: str,
    now: datetime,
    holidays: frozenset[date] | set[date],
    backup_dir: str = DEFAULT_BACKUP_DIR,
) -> list[str]:
    """Hàm thuần cho bản sao lưu SỔ LỆNH. Không có ngưỡng kích thước (cố ý).

    Tuổi theo lịch: D = ngày giao dịch gần nhất TRƯỚC hôm nay (`previous_trading_day`
    không gồm hôm nay). Bản mới nhất phải có mtime SAU khi phiên ngày D kết thúc
    (14:46 giờ VN). Không kiểm kích thước: phiên mà bộ ghi chết sớm để lại file nhỏ
    vẫn là bản sao lưu ĐÚNG của dữ liệu đã có; chất lượng dữ liệu là việc của
    `orderbook-daily-check`, thêm ngưỡng ở đây sẽ báo trùng và báo oan.

    integrity_status: "OK" hoặc "FAIL: <lý do>".
    """
    if latest_file is None:
        return [
            f"[CRITICAL] Không tìm thấy bản sao lưu sổ lệnh (orderbook_*.tar.gz) nào trong {backup_dir}"
        ]

    alerts: list[str] = []
    now = now.astimezone(TZ)
    d = previous_trading_day(now.date(), frozenset(holidays))
    cutoff = datetime.combine(d, ORDERBOOK_SESSION_END, tzinfo=TZ)
    latest_dt = datetime.fromtimestamp(latest_file.mtime, tz=TZ)
    if latest_dt <= cutoff:
        age_hours = (now - latest_dt).total_seconds() / 3600.0
        alerts.append(
            f"[CRITICAL] Bản sao lưu sổ lệnh mới nhất ({latest_file.name}) quá cũ: {age_hours:.1f}h, "
            f"được tạo trước khi phiên ngày giao dịch {d.isoformat()} kết thúc "
            f"({cutoff.strftime('%Y-%m-%d %H:%M')}) — dữ liệu ngày {d.isoformat()} chưa được sao lưu"
        )
    if integrity_status != "OK":
        alerts.append(
            f"[CRITICAL] Bản sao lưu sổ lệnh {latest_file.name} hỏng: {integrity_status}"
        )
    return alerts


def evaluate_counts_statement(
    latest_file: BackupFileInfo | None, counts_size: int | None
) -> list[str]:
    """Bản sao lưu DB `.dump` mới nhất phải có bản kê số dòng `.counts` (đợt 138).

    Chỉ kiểm TỒN TẠI và KHÁC RỖNG; nội dung là việc của `restore_drill.py` (phân tích ở cả hai
    nơi là báo trùng). Lý do có phép kiểm này: `backup_db.sh` chỉ CẢNH BÁO rồi vẫn dump khi lập bản
    kê lỗi (bản kê là công cụ kiểm, lỗi của nó không được giết bản sao lưu), nên ngoài diễn tập
    Chủ nhật không gì khác nhìn `.counts` — thiếu sáu đêm liền cũng không ai biết.

    Bản `.sql.gz` cũ (định dạng trước đợt 137) không bị đòi bản kê.
    counts_size: kích thước byte của `.counts` cùng tên gốc, None nếu không có file.
    """
    if latest_file is None or not latest_file.name.endswith(".dump"):
        return []
    if not counts_size:
        msg = (
            f"[CRITICAL] Bản sao lưu {latest_file.name} không có bản kê số dòng — "
            "diễn tập phục hồi Chủ nhật sẽ không kiểm được nó"
        )
        return [msg]
    return []


def check_orderbook_tar(file_path: Path) -> str:
    """Đọc được và có > 0 file bên trong. "OK" hoặc "FAIL: <lý do>".

    Dùng `tarfile` thay cho `tar -tzf`: cùng phép kiểm, không phụ thuộc `tar` trên PATH
    và không dính lỗi `D:/...` bị `tar` hiểu là `host:path` trên Windows (đợt 134).
    """
    try:
        with tarfile.open(file_path, "r:gz") as t:
            n = sum(1 for _ in t)
    except Exception as e:
        return f"FAIL: {type(e).__name__}: {e}"
    if n <= 0:
        return "FAIL: archive không chứa file nào"
    return "OK"


def load_holidays(config_path: Path) -> frozenset[date]:
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return frozenset(date.fromisoformat(str(h)) for h in (raw.get("holidays") or []))


def check_pg_restore(file_path: Path) -> str:
    """Chạy pg_restore -l kiểm tra tính toàn vẹn của file dump.

    Thử host pg_restore trước. Nếu host không có, thử container postgres qua docker.
    Returns:
      "OK" nếu archive đọc được.
      "FAIL: <chi tiết>" nếu pg_restore báo lỗi hỏng.
      "UNAVAILABLE: <chi tiết>" nếu không tìm thấy công cụ kiểm tra.
    """
    # 1. Thử host pg_restore nếu có trên PATH
    pg_restore_bin = shutil.which("pg_restore")
    if pg_restore_bin:
        try:
            res = subprocess.run(
                [pg_restore_bin, "-l", str(file_path)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if res.returncode == 0:
                return "OK"
            err = res.stderr.strip() or f"exit code {res.returncode}"
            return f"FAIL: {err}"
        except Exception as e:
            return f"FAIL: {e}"

    # 2. Thử qua docker container nếu có docker
    try:
        with open(file_path, "rb") as f:
            res = subprocess.run(
                ["docker", "compose", "exec", "-T", "postgres", "pg_restore", "-l"],
                stdin=f,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        if res.returncode == 0:
            return "OK"
        err = res.stderr.strip() or f"exit code {res.returncode}"
        return f"FAIL: {err}"
    except Exception:
        pass

    return "UNAVAILABLE: pg_restore không có trên PATH"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kiểm tra sao lưu DB hàng ngày.")
    parser.add_argument(
        "--backup-dir",
        default=DEFAULT_BACKUP_DIR,
        help="Thư mục chứa bản sao lưu",
    )
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=DEFAULT_MAX_AGE_HOURS,
        help="Ngưỡng tuổi tối đa (giờ)",
    )
    parser.add_argument(
        "--min-size-mb",
        type=float,
        default=DEFAULT_MIN_SIZE_MB,
        help="Ngưỡng kích thước tối thiểu (MB)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="In cảnh báo ra stdout thay vì gửi Telegram",
    )
    parser.add_argument(
        "--no-orderbook",
        action="store_true",
        help="Bỏ kiểm bản sao lưu sổ lệnh (mặc định: có kiểm)",
    )
    parser.add_argument(
        "--no-counts",
        action="store_true",
        help="Bỏ kiểm bản kê số dòng .counts của bản dump DB (mặc định: có kiểm)",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="config.yaml để đọc danh sách ngày lễ (kiểm sổ lệnh theo lịch giao dịch)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    backup_dir = Path(args.backup_dir)
    now_epoch = time.time()

    if not backup_dir.exists() or not backup_dir.is_dir():
        alerts = evaluate_backup_health(
            dir_exists=False,
            latest_file=None,
            pg_restore_status="",
            now_epoch=now_epoch,
            backup_dir=str(backup_dir),
            max_age_hours=args.max_age_hours,
            min_size_mb=args.min_size_mb,
        )
    else:
        # Tìm các file backup: trading_*.dump hoặc trading_*.sql.gz
        files: list[Path] = [
            f
            for f in backup_dir.iterdir()
            if f.is_file()
            and f.name.startswith("trading_")
            and (f.name.endswith(".dump") or f.name.endswith(".sql.gz"))
        ]
        if not files:
            alerts = evaluate_backup_health(
                dir_exists=True,
                latest_file=None,
                pg_restore_status="",
                now_epoch=now_epoch,
                backup_dir=str(backup_dir),
                max_age_hours=args.max_age_hours,
                min_size_mb=args.min_size_mb,
            )
        else:
            latest_p = max(files, key=lambda f: f.stat().st_mtime)
            st = latest_p.stat()
            latest_info = BackupFileInfo(
                name=latest_p.name,
                path=str(latest_p),
                size_bytes=st.st_size,
                mtime=st.st_mtime,
            )
            pg_status = check_pg_restore(latest_p)
            alerts = evaluate_backup_health(
                dir_exists=True,
                latest_file=latest_info,
                pg_restore_status=pg_status,
                now_epoch=now_epoch,
                backup_dir=str(backup_dir),
                max_age_hours=args.max_age_hours,
                min_size_mb=args.min_size_mb,
            )
            if not args.no_counts:
                counts_file = latest_p.with_suffix(".counts")
                counts_size = (
                    counts_file.stat().st_size if counts_file.is_file() else None
                )
                alerts += evaluate_counts_statement(latest_info, counts_size)

    if not args.no_orderbook and backup_dir.is_dir():
        try:
            holidays = load_holidays(Path(args.config))
        except Exception as e:
            holidays = frozenset()
            alerts.append(
                f"[CRITICAL] Không đọc được ngày lễ từ {args.config} ({type(e).__name__}): "
                "kiểm sổ lệnh chạy chỉ theo T2–T6, có thể báo oan sau kỳ nghỉ"
            )
        ob_files = [
            f
            for f in backup_dir.iterdir()
            if f.is_file()
            and f.name.startswith("orderbook_")
            and f.name.endswith(".tar.gz")
        ]
        if ob_files:
            latest_ob = max(ob_files, key=lambda f: f.stat().st_mtime)
            st = latest_ob.stat()
            ob_info: BackupFileInfo | None = BackupFileInfo(
                latest_ob.name, str(latest_ob), st.st_size, st.st_mtime
            )
            integrity = check_orderbook_tar(latest_ob)
        else:
            ob_info, integrity = None, "OK"
        alerts += evaluate_orderbook_backup(
            latest_file=ob_info,
            integrity_status=integrity,
            now=datetime.now(TZ),
            holidays=holidays,
            backup_dir=str(backup_dir),
        )

    if alerts:
        msg = "\n".join(alerts)
        _print_safe(msg)
        if args.dry_run:
            _print_safe("[DRY-RUN] Không gửi Telegram thật.")
            return 1
        sent = send_telegram(msg)
        if sent:
            return 1
        else:
            _print_safe("LỖI: Cảnh báo cần gửi nhưng send_telegram trả về thất bại!")
            return 2

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
