"""Cảnh báo trước khi đĩa đầy (brief đợt 132, 2026-09-29).

Không có dòng code nào canh dung lượng đĩa trước đợt này. Hết đĩa là kiểu chết
âm thầm của máy chủ chạy 24/7: Postgres ngừng ghi, collector chết và bản sao
lưu cũng hỏng cùng lúc.

Kêu khi MỘT TRONG HAI điều kiện chạm:
  - còn trống dưới ngưỡng tuyệt đối (mặc định 10 GB), hoặc
  - còn trống dưới một tỷ lệ (mặc định 10%).

Vì sao cần cả hai: đĩa 500 GB thì 10% là 50 GB (quá sớm, kêu oan nhiều tháng);
đĩa 40 GB thì 10 GB là 25% (hợp lý). Chỉ dùng tỷ lệ thì đĩa lớn kêu quá sớm,
chỉ dùng ngưỡng tuyệt đối thì đĩa nhỏ kêu quá muộn.

Thư mục sao lưu (`--backup-dir`) đo RIÊNG: trên VPS nó có thể nằm trên phân vùng
khác, không được giả định cùng ổ với repo.

Mã thoát (họ "theo gửi được hay không", như backup_check.py — KHÔNG phải họ
"theo phát hiện" của _alert_common.alert_and_fail):
  0: đủ chỗ.
  1: có cảnh báo và đã gửi thành công (hoặc in ra khi --dry-run).
  2: sai cấu hình, hoặc cảnh báo cần gửi mà gửi hỏng.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

from trading.alerts import _print_safe
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
DEFAULT_MIN_FREE_GB = 10.0
DEFAULT_MIN_FREE_PCT = 10.0

_GB = 1024.0**3


def evaluate_disk(
    free_bytes: int,
    total_bytes: int,
    min_free_gb: float,
    min_free_pct: float,
    label: str,
) -> list[str]:
    """Hàm quyết định thuần túy: không đọc đĩa. Trả về 0 hoặc 1 cảnh báo."""
    free_gb = free_bytes / _GB
    free_pct = (free_bytes / total_bytes * 100.0) if total_bytes > 0 else 0.0
    reasons = []
    if free_gb < min_free_gb:
        reasons.append(f"dưới {min_free_gb:.1f} GB")
    if free_pct < min_free_pct:
        reasons.append(f"dưới {min_free_pct:.1f}%")
    if not reasons:
        return []
    msg = (
        f"[CRITICAL] Đĩa sắp đầy ({label}): còn {free_gb:.1f} GB "
        f"({free_pct:.1f}%) — {' và '.join(reasons)}"
    )
    return [msg]


def dir_size_bytes(path: Path) -> int:
    """Tổng dung lượng file dưới `path`; lỗi từng file thì bỏ qua, không ném."""
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def docker_usage() -> str:
    """`docker system df` nguyên văn, hoặc lý do không lấy được. Không ném."""
    try:
        res = subprocess.run(
            ["docker", "system", "df"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if res.returncode == 0:
            return res.stdout.strip()
        return f"(docker system df lỗi: {res.stderr.strip() or res.returncode})"
    except Exception as e:
        return f"(không chạy được docker system df: {type(e).__name__})"


def build_report(path: Path, backup_dir: Path | None) -> str:
    """Cái gì đang chiếm chỗ — để người đọc biết, không chỉ biết 'sắp đầy'."""
    lines = ["Chiếm chỗ:"]
    targets = [("data/orderbook", path / "data" / "orderbook"), ("logs", path / "logs")]
    if backup_dir is not None:
        targets.append((f"sao lưu ({backup_dir})", backup_dir))
    for name, p in targets:
        lines.append(f"  {name}: {dir_size_bytes(p) / (1024.0**2):.1f} MB")
    lines.append("Docker:")
    lines.extend(f"  {ln}" for ln in docker_usage().splitlines())
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cảnh báo dung lượng đĩa sắp hết.")
    parser.add_argument(
        "--path",
        default=".",
        help="Đường dẫn cần đo (mặc định: thư mục hiện tại = repo)",
    )
    parser.add_argument(
        "--backup-dir",
        default=DEFAULT_BACKUP_DIR,
        help="Thư mục sao lưu, đo riêng (có thể nằm trên phân vùng khác)",
    )
    parser.add_argument("--min-free-gb", type=float, default=DEFAULT_MIN_FREE_GB)
    parser.add_argument("--min-free-pct", type=float, default=DEFAULT_MIN_FREE_PCT)
    parser.add_argument(
        "--dry-run", action="store_true", help="In thay vì gửi Telegram"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    path = Path(args.path)
    if not path.is_dir():
        _print_safe(f"LỖI CẤU HÌNH: --path không phải thư mục: {path}")
        return 2
    backup_dir = Path(args.backup_dir) if args.backup_dir else None
    if backup_dir is not None and not backup_dir.is_dir():
        # Viec CHINH cua job nay la do dung luong dia. Thu muc sao luu vang thi ghi
        # chu roi do tiep, KHONG thoat 2 — neu khong, mot cau hinh sai o phep do PHU
        # se lam job khong bao gio chay phep do CHINH (do 29/09 tren Windows).
        # "Co ban sao luu hay khong" da thuoc ve backup_check.py.
        _print_safe(
            f"[disk-check] Bo qua phep do thu muc sao luu: khong phai thu muc ({backup_dir})"
        )
        backup_dir = None

    alerts: list[str] = []
    measured = [("repo", path)]
    if backup_dir is not None:
        measured.append(("sao lưu", backup_dir))
    for label, p in measured:
        try:
            usage = shutil.disk_usage(p)
        except OSError as e:
            _print_safe(f"LỖI: không đo được đĩa của {p}: {e}")
            return 2
        alerts += evaluate_disk(
            usage[2],
            usage[0],
            args.min_free_gb,
            args.min_free_pct,
            f"{label}: {p}",
        )

    if not alerts:
        return 0

    msg = "\n".join(alerts) + "\n" + build_report(path, backup_dir)
    _print_safe(msg)
    if args.dry_run:
        _print_safe("[DRY-RUN] Không gửi Telegram thật.")
        return 1
    try:
        sent = send_telegram(msg)
    except Exception as e:
        _print_safe(f"LỖI: send_telegram ném {type(e).__name__}: {e}")
        return 2
    if sent:
        return 1
    _print_safe("LỖI: Cảnh báo cần gửi nhưng send_telegram trả về thất bại!")
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
