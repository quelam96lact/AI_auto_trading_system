"""Dead-man's switch: cảnh báo Telegram khi collector/engine ngừng đập heartbeat.

Chạy bằng cron TRÊN HOST (không phải trong container) — nếu chạy trong chính
container đang chết thì nó cũng chết theo. Xem DEPLOYMENT.md §9.

Exit code: 0 = ổn, 1 = có cảnh báo đã gửi, 2 = sai cấu hình.

FEE-ALARM-1 Việc 2 — hai cảnh báo bổ sung cho kiểu hỏng âm thầm (tiến trình
còn sống nhưng việc thật đã chết):
- 2A "dữ liệu ngừng chảy": bar không về trong cửa sổ kiểm tra.
- 2B "token SSI sắp/đã hết hạn": bắt đúng sự cố 14/08 — refresh token hết hạn
  13:39, feed chết 14:33, heartbeat vẫn xanh suốt. 2A KHÔNG bắt được sự cố đó
  (bar chảy đủ); 2B mới bắt được.
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, time, timedelta
from typing import Any, NamedTuple

import psycopg
import yaml

from trading.alerts import _print_safe
from trading.calendar_vn import (
    TZ,
    is_trading_day,
    is_trading_time,
    market_minutes_between,
)

# LEDGER-1: import hang so tu trading/ —
# da kiem main.py module-level KHONG chay side effect (chi import + dinh nghia;
# storage/nats nam trong ham). KHONG chep so sang day (hai noi lech = bao lao
# mai mai hoac im mai mai).
from trading.engine.main import CAPITAL
from trading.storage.db import Storage
from trading.telegram import send_telegram

SERVICES = ("collector", "engine")
DEFAULT_MAX_AGE_SECONDS = 300

# LEDGER-1 2C: dung sai so sach. Can cu: float double tich luy qua hang nghin
# lenh sai so ~< 0.01 VND (15-17 chu so); 1.000 VND = ~100.000x bien an toan
# chong bao lao vi lam tron, dong thoi nho hon MỌI khoan lech that (phi mua
# nho nhat trong ho so la 6.670d/lenh — 6664cd9 lech 119.417).
LEDGER_TOLERANCE = 1_000.0

# 2A: cửa sổ kiểm tra bar — KHÔNG dùng SESSIONS của calendar_vn (coi tới 14:45
# là giờ giao dịch). Khung ATC 14:30-14:45 lúc có lúc không tùy mã tùy ngày
# (đo thật 12/08: 0 bar; 13/08: 3 bar trong 14:30-14:40) — kiểm qua đó báo láo.
# Cắt ở 14:30, chấp nhận mù 15 phút cuối phiên (FEE-ALARM-1).
CHECK_SESSIONS = [(time(9, 0), time(11, 30)), (time(13, 0), time(14, 30))]
# Ngưỡng bar cũ: ĐO trên dữ liệu thật (21 ngày, trong cửa sổ 2A, tách theo
# từng phiên) cho ĐÚNG đại lượng code đang đo — max(ts) GỘP các mã cấu hình
# (khoảng trống chỉ tồn tại khi KHÔNG mã nào ra bar; mã thanh khoản thấp có
# khung rỗng nhưng các mã khác lấp vào): gap lớn nhất = 5 PHÚT, 0 lần > 15.
# Ngưỡng 15 phút = 3x biên độ đo được, vẫn dư biên. (Bản đầu đặt 30 vì đo
# gap TỪNG MÃ — HII 35 phút — sai đại lượng; 30 sẽ làm feed chết 30 phút mới
# kêu, mù 1/3 phiên chiều 90 phút.)
DEFAULT_STALE_BAR_MINUTES = 15

# 2D: ngưỡng vị thế cũ — ĐO trên DB thật (30/08/2026): account_sync_log + 8 mốc
# liên tiếp account_position_snapshot cho nhịp 5 phút 05 giây, rất đều (7 dòng
# mỗi mốc). Ngưỡng 15 phút = ~3x nhịp đo được — cùng hệ số an toàn với 2A.
DEFAULT_STALE_POSITION_SYNC_MINUTES = 15

DEFAULT_LOGS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
)
SCHEDULE_STATE_NAME = ".schedule_health_state.json"
DEFAULT_SCHEDULE_STATE_FILE = os.path.join(DEFAULT_LOGS_DIR, SCHEDULE_STATE_NAME)


class WatchJobConfig(NamedTuple):
    branch: str  # Tên nhánh trong sched.sh
    log_file: str  # Tên file log trong logs/
    label: str  # Nhãn được ghi bởi run_if_docker_up.sh
    max_age_seconds: int  # Ngưỡng tuổi tối đa của lần gọi gần nhất (giây)
    schedule_desc: str  # Mô tả lịch (cho báo cáo / alert)
    formula_note: str  # Câu số học giải thích ngưỡng


# Bảng kỳ vọng các job chạy 24/7 (Việc 2 - Brief 142)
SCHEDULE_WATCH_JOBS: dict[str, WatchJobConfig] = {
    "container-health": WatchJobConfig(
        branch="container-health",
        log_file="container-health.log",
        label="container-health",
        max_age_seconds=25 * 60,  # 25 phút
        schedule_desc="mỗi 10 phút (24/7)",
        formula_note="chạy đúng tuổi lớn nhất ~10p, lỡ 1 lần tuổi ~20p (≤ 25p cho phép lỡ 1 lần), lỡ lần 2 tuổi ~30p > 25p -> bắt từ lần lỡ thứ 2",
    ),
    "disk-check": WatchJobConfig(
        branch="disk-check",
        log_file="disk-check.log",
        label="disk-check",
        max_age_seconds=int(6.5 * 3600),  # 6 giờ 30 phút = 23,400 giây
        schedule_desc="mỗi 6 giờ (00/06/12/18, 24/7)",
        formula_note="chạy đúng tuổi lớn nhất 6h, lỡ 1 lần (vd 06:00) thì lúc mở phiên 08:00 tuổi đã 8h > 6.5h -> bắt ngay",
    ),
    "backup": WatchJobConfig(
        branch="backup",
        log_file="backup.log",
        label="backup",
        max_age_seconds=26 * 3600,  # 26 giờ = 93,600 giây
        schedule_desc="02:00 hằng ngày",
        formula_note="chạy đúng trong phiên 08:00-15:00 tuổi 6h-13h (< 24h), lỡ lần 02:00 sáng thì lúc 08:00 tuổi 30h > 26h -> bắt ngay",
    ),
    "orderbook-backup": WatchJobConfig(
        branch="orderbook-backup",
        log_file="orderbook-backup.log",
        label="orderbook-backup",
        max_age_seconds=26 * 3600,  # 26 giờ = 93,600 giây
        schedule_desc="02:30 hằng ngày",
        formula_note="chạy đúng trong phiên 08:00-15:00 tuổi 5.5h-12.5h (< 24h), lỡ lần 02:30 sáng thì lúc 08:00 tuổi 29.5h > 26h -> bắt ngay",
    ),
    "backup-check": WatchJobConfig(
        branch="backup-check",
        log_file="backup-check.log",
        label="backup-check",
        max_age_seconds=26 * 3600,  # 26 giờ = 93,600 giây
        schedule_desc="03:00 hằng ngày",
        formula_note="chạy đúng trong phiên 08:00-15:00 tuổi 5h-12h (< 24h), lỡ lần 03:00 sáng thì lúc 08:00 tuổi 29h > 26h -> bắt ngay",
    ),
}

# 11 nhánh sched.sh không canh 24/7 trong heartbeat (kèm lý do một câu)
KHONG_CANH: dict[str, str] = {
    "heartbeat": "Chính là heartbeat, không tự canh mà do container-health canh riêng trong giờ giao dịch.",
    "daily-check": "Chỉ chạy 21:00 ngày giao dịch, cần lịch giao dịch và ngày nghỉ để canh đúng.",
    "backfill": "Chỉ chạy 21:15 ngày giao dịch, cần lịch giao dịch và ngày nghỉ để canh đúng.",
    "deploy-drift": "Chỉ chạy 08:30 và 13:15 ngày giao dịch, không chạy 24/7.",
    "engine-cam": "Chỉ chạy trong giờ giao dịch 09:15-14:45 ngày giao dịch.",
    "engine-consumer": "Chỉ chạy trong giờ giao dịch 09:00-14:50 ngày giao dịch.",
    "stream-health": "Chỉ chạy các mốc cụ thể trong phiên ngày giao dịch (09:20, 11:35, 13:20, 14:50).",
    "orderbook-recorder": "Chỉ chạy tiến trình ghi sổ lệnh trong giờ giao dịch (08:55-14:46).",
    "orderbook-daily-check": "Chỉ chạy 15:05 cuối ngày giao dịch.",
    "host-preflight": "Chỉ chạy 07:45 trước giờ giao dịch.",
    "restore-drill": "Chỉ chạy 03:30 sáng Chủ nhật hằng tuần (chu kỳ tuần).",
}


def get_last_called_timestamp(
    log_path: str, label: str
) -> tuple[datetime | None, str | None]:
    """Đọc mốc thời gian lần gọi gần nhất của nhãn `label` từ file log.

    Quy ước run_if_docker_up.sh:
      <YYYY-MM-DD HH:MM:SS> <nhãn> start
      <YYYY-MM-DD HH:MM:SS> <nhãn> SKIP: ...
      <YYYY-MM-DD HH:MM:SS> <nhãn> ERROR: ...

    Trả về:
      (dt, None) nếu tìm thấy dòng hợp lệ (dòng SKIP cũng tính là đã được gọi).
      (None, reason) nếu không tìm thấy file hoặc không có dòng nào mang nhãn.
    """
    if not os.path.isfile(log_path):
        return None, f"file log không tồn tại ({os.path.basename(log_path)})"

    pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+" + re.escape(label) + r"(?:\s|$)"
    )
    last_dt = None
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = pattern.match(line)
                if m:
                    try:
                        dt = datetime.strptime(
                            m.group(1), "%Y-%m-%d %H:%M:%S"
                        ).replace(tzinfo=TZ)
                        last_dt = dt
                    except ValueError:
                        continue
    except Exception as e:
        return None, f"không đọc được file log ({e})"

    if last_dt is None:
        return None, f"không tìm thấy dòng nào mang nhãn '{label}' trong {os.path.basename(log_path)}"
    return last_dt, None


def evaluate_schedule_health(
    job_last_seen: dict[str, tuple[datetime | None, str | None]],
    now: datetime,
    previous_state: dict[str, dict[str, Any]],
    watch_jobs: dict[str, WatchJobConfig] = SCHEDULE_WATCH_JOBS,
) -> tuple[list[str], dict[str, dict[str, Any]], list[str]]:
    """Đánh giá trạng thái chạy của các job theo lịch 24/7 (pure function).

    Chỉ báo khi chuyển trạng thái:
      - từ 'ok' (hoặc lần đầu / thiếu state) sang 'stale' -> báo CRITICAL một lần.
      - từ 'stale' sang 'ok' -> báo INFO hồi phục một lần.
      - kéo dài trạng thái cũ -> im lặng (chỉ ghi log info).
      - không có file log hoặc log không có nhãn -> coi là 'stale'.
      - file trạng thái lỗi hoặc thiếu -> coi như lần chạy đầu, KHÔNG nuốt job đang ngừng.

    Trả về: (alerts, new_state, info_logs)
    """
    alerts = []
    info_logs = []
    new_state = dict(previous_state)
    now_tz = now.astimezone(TZ)

    for branch, cfg in watch_jobs.items():
        last_dt, reason = job_last_seen.get(branch, (None, "không có dữ liệu"))
        prev = previous_state.get(branch)
        prev_status = prev.get("status") if isinstance(prev, dict) else None

        if last_dt is None:
            current_status = "stale"
            stale_reason = reason or f"không tìm thấy dòng nào của {cfg.label} trong log"
        else:
            age_seconds = (now_tz - last_dt).total_seconds()
            if age_seconds > cfg.max_age_seconds:
                current_status = "stale"
                age_minutes = age_seconds / 60
                max_minutes = cfg.max_age_seconds / 60
                stale_reason = (
                    f"lần gọi gần nhất lúc {last_dt:%Y-%m-%d %H:%M:%S} "
                    f"({age_minutes:.0f} phút trước > ngưỡng {max_minutes:.0f} phút, lịch: {cfg.schedule_desc})"
                )
            else:
                current_status = "ok"
                stale_reason = None

        new_record = {
            "status": current_status,
            "last_called": (
                last_dt.strftime("%Y-%m-%d %H:%M:%S") if last_dt else None
            ),
            "checked_at": now_tz.strftime("%Y-%m-%d %H:%M:%S"),
        }
        new_state[branch] = new_record

        if current_status == "stale":
            if prev_status != "stale":
                alerts.append(
                    f"[CRITICAL] job theo lịch '{branch}' NGỪNG CHẠY: {stale_reason}"
                )
            else:
                info_logs.append(
                    f"[heartbeat-sched] INFO: {branch} vẫn ngừng chạy ({stale_reason}) - đã báo trước đó"
                )
        else:  # current_status == "ok"
            if prev_status == "stale":
                alerts.append(
                    f"[INFO] job theo lịch '{branch}' ĐÃ CHẠY LẠI: lần gọi gần nhất lúc {last_dt:%Y-%m-%d %H:%M:%S}"
                )
            else:
                pass

    return alerts, new_state, info_logs


def load_schedule_state(filepath: str) -> dict[str, dict[str, Any]]:
    """Đọc file trạng thái JSON. Nếu không tồn tại hoặc lỗi, trả về {}."""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            _print_safe(
                f"[heartbeat] File trạng thái {filepath} không đúng định dạng dict — coi như lần đầu."
            )
            return {}
    except Exception as e:
        _print_safe(
            f"[heartbeat] File trạng thái {filepath} hỏng hoặc không đọc được ({e}) — coi như lần chạy đầu."
        )
        return {}


def save_schedule_state(
    filepath: str, state: dict[str, dict[str, Any]]
) -> None:
    """Ghi trạng thái ra file JSON an toàn qua file tạm."""
    dir_path = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(dir_path, exist_ok=True)
    tmp_path = filepath + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, filepath)


def stale_services(rows, now, max_age_seconds, expected=SERVICES) -> list[str]:
    """rows: list[(service, last_seen)] đọc từ bảng heartbeat.

    Trả về tên các service thiếu hẳn dòng heartbeat hoặc có last_seen quá hạn.
    """
    seen = {r[0]: r[1] for r in rows}
    limit = timedelta(seconds=max_age_seconds)
    return [svc for svc in expected if seen.get(svc) is None or now - seen[svc] > limit]


def in_bar_check_window(ts: datetime, holidays: frozenset = frozenset()) -> bool:
    """Trong cửa sổ kiểm tra bar 2A (9:00-11:30 / 13:00-14:30, ngày giao dịch)?"""
    ts = ts.astimezone(TZ)
    if not is_trading_day(ts.date(), holidays):
        return False
    t = ts.time()
    return any(start <= t <= end for start, end in CHECK_SESSIONS)


def bar_stale(
    max_ts,
    now,
    stale_minutes=DEFAULT_STALE_BAR_MINUTES,
    holidays: frozenset = frozenset(),
) -> bool:
    """2A: dữ liệu ngừng chảy. max_ts = max(ts) gộp các mã ĐANG CẤU HÌNH
    (None = không có bar nào cả ngày — ca "feed chưa từng nối được").

    Chỉ báo trong cửa sổ kiểm tra 2A. Ngoài cửa sổ (cuối tuần, khung ATC,
    ngoài giờ) -> False.

    2026-09-01: hạn chế "ngày lễ báo láo cả ngày" ĐÃ ĐÓNG. Trước đó hàm này bỏ
    qua tham số holidays nên ngày 01/09 (nghỉ Quốc khánh) 2A nổ mỗi 5 phút suốt
    cả ngày — cảnh báo dương tính giả, và dương tính giả lặp lại thì lần sau
    không ai đọc nữa. Danh sách ngày nghỉ lấy từ config.yaml, KHÔNG tự dựng.
    """
    if not in_bar_check_window(now, holidays):
        return False
    if max_ts is None:
        return True  # "feed chưa từng nối được" — không có bar nào cả ngày
    # 2026-09-03 (goi A): do phut TRONG PHIEN (bo nghi trua/cuoi tuan/ngay le),
    # khong phai phut dong ho. Truoc day 13:00:03 voi bar cuoi 11:25 (phien
    # sang) tinh la 95 phut -> bao dong GIA moi phien chieu. Phut trong phien
    # = 5 phut (11:25-11:30) + ~0 (13:00 moi mo) -> khong bao. Nguong 15 phut
    # GIU NGUYEN (khong noi) — chi doi dai luong do.
    return (
        market_minutes_between(max_ts, now, holidays, sessions=CHECK_SESSIONS)
        > stale_minutes
    )


def position_sync_stale(
    sync_ts, now, stale_minutes=DEFAULT_STALE_POSITION_SYNC_MINUTES
) -> bool:
    """2D: vị thế ngừng đồng bộ. sync_ts = mốc đồng bộ gần nhất của
    real_order_account (từ Storage.read_position_sync_ts — None = chưa từng
    đồng bộ, bảng account_sync_log chưa có dòng).

    None -> True: "chưa từng đồng bộ" là ca dễ tuột nhất (nếu sync có lỗi
    logic không ném exception, đường đặt lệnh THẬT vẫn đọc vị thế cũ và không
    ai được báo). Không cần cửa sổ kiểm tra riêng: main() đã chặn ngoài giờ
    giao dịch ở đầu hàm (tiền lệ 2C).
    """
    if sync_ts is None:
        return True
    return now - sync_ts > timedelta(minutes=stale_minutes)


def token_expiry_status(
    refresh_expires_at, now, holidays: frozenset = frozenset()
) -> str | None:
    """2B: token SSI sắp/đã hết hạn. refresh_expires_at = epoch seconds
    (từ Storage.load_ssi_token) hoặc None (ssi_auth_state rỗng).

    Trả về: None (ổn) | "WARN" (còn < 60 phút) | "CRITICAL" (đã hết hạn hoặc
    không có dòng nào).

    Chỉ báo trong giờ giao dịch (is_trading_time dùng nguyên vẹn — 2B không
    liên quan khung ATC), CỘNG THÊM khung 8:00-9:00 sáng ngày giao dịch để
    cảnh báo kịp hành động trước giờ mở cửa (điểm khác biệt so với 2A).
    """
    now_tz = now.astimezone(TZ)
    t = now_tz.time()
    pre_market = time(8, 0) <= t < time(9, 0) and is_trading_day(
        now_tz.date(), holidays
    )
    if not (is_trading_time(now, holidays) or pre_market):
        return None
    # Kiem "khong co token" phai nam SAU cong gio giao dich, dung nhu docstring
    # hua. Truoc day no nam TRUOC nen ham bao CRITICAL 24/7; main() vo tinh che
    # mat vi da gac cong san — nhung hop dong cua ham thi sai, va ngay 01/09 test
    # ngay le lam lo ra.
    if refresh_expires_at is None:
        return "CRITICAL"
    remaining = refresh_expires_at - now.timestamp()
    if remaining < 0:
        return "CRITICAL"
    if remaining < 3600:
        return "WARN"
    return None


def check_holiday_exhaustion(
    holidays: frozenset[date] | set[date], now: datetime
) -> str | None:
    """Kiểm tra lịch nghỉ lễ trong config đã cạn hay chưa.

    Luật: Cảnh báo WARN khi không còn ngày lễ nào >= hôm nay trong config VÀ
    hôm nay đã qua 01/10 ((now.month, now.day) >= (10, 1)).

    Vì sao có mốc 01/10: trước tháng 10 thì lịch năm sau chưa công bố chính thức,
    cảnh báo lúc đó là nhiễu vô ích vì không ai hành động được. Từ 01/10 trở đi,
    thông báo chính thức bắt đầu ra, cảnh báo mới có chỗ để hành động.
    """
    today = now.astimezone(TZ).date()
    if (today.month, today.day) < (10, 1):
        return None

    future_holidays = [h for h in holidays if h >= today]
    if not future_holidays:
        return (
            "[WARN] lịch nghỉ lễ trong config/config.yaml đã cạn (không còn ngày lễ >= hôm nay) — "
            "cần cập nhật lịch nghỉ giao dịch năm mới của HOSE/HNX (lấy ngày sàn đóng cửa, "
            "lưu ý ngày nghỉ bù/liền kề) vào config.yaml"
        )
    return None


def ledger_deviation(
    cash: float, realized_pnl: float, positions_value: float, capital: float = CAPITAL
) -> float:
    """2C: độ lệch hai sổ sách. Bất biến (đúng LUÔN, không chỉ khi phẳng):
        cash + Σ(avg_price × qty) − capital == realized_pnl
    Trả về vế trái − vế phải. > LEDGER_TOLERANCE (hoặc < −LEDGER_TOLERANCE)
    → hai sổ lệch (hai lỗi 6664cd9 / 2982900 đều là cash đúng, realized sai).
    """
    return (cash + positions_value - capital) - realized_pnl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dead-man's switch: cảnh báo Telegram khi collector/engine ngừng đập heartbeat."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chế độ chạy thử: in cảnh báo thay vì gửi Telegram, không ghi file trạng thái.",
    )
    # Brief 145: cờ dòng lệnh (không phải tham số của main) vì parser là cổng vào
    # duy nhất đã được test_sched_args ghim; test gọi main([...]) như cron gọi.
    parser.add_argument(
        "--logs-dir",
        default=DEFAULT_LOGS_DIR,
        help="Thư mục log để đọc (mặc định: logs/ của repo — cron không truyền).",
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help="File trạng thái lịch (mặc định: .schedule_health_state.json "
        "trong --logs-dir).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    # Vô điều kiện, câu đầu tiên (brief 141): `if argv is not None` từng làm `main()` nuốt im lặng
    # mọi cờ lạ. argv=None thì argparse tự đọc sys.argv. tests/test_sched_args.py ghim bằng AST.
    args = build_parser().parse_args(argv)
    # Ep utf-8 de ly do canh bao con dau tieng Viet; that bai cung khong sao,
    # _print_safe da co duong lui.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    dsn = os.environ.get("DB_DSN")
    if not dsn:
        print("DB_DSN chưa được set", file=sys.stderr)
        return 2
    max_age = int(os.environ.get("HEARTBEAT_MAX_AGE_SECONDS", DEFAULT_MAX_AGE_SECONDS))

    now = datetime.now(TZ)

    # Doc config TRUOC cong gio giao dich: chinh cong do can biet hom nay co la
    # ngay nghi khong. Truoc 2026-09-01 config duoc doc SAU cong, nen danh sach
    # holidays khong bao gio toi duoc cho quyet dinh — ngay le van bao lao ca ngay.
    # Doi lai: config hong se bao CRITICAL ke ca ngoai gio giao dich. Chap nhan —
    # config hong la van de that, va im lang ve no moi la sai.
    # 2A: chỉ nhìn mã ĐANG CẤU HÌNH — bảng bars còn 302 mã universe nạp theo
    # lô, gộp chúng vào sẽ che mất một feed đã chết.
    try:
        cfg_path = os.path.join(
            os.path.dirname(__file__), "..", "config", "config.yaml"
        )
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        symbols = cfg["symbols"]
        # 2D: dung LAI real_order_account — dung tai khoan ma read_real_positions() dung
        real_order_account = cfg["real_order_account"]
        # Cung cach doc nhu trading/config.py:38. Co y KHONG import load_config():
        # ham do doi day du SSI_* trong moi truong, ma chuong bao phai chay duoc
        # ngay ca khi cau hinh SSI thieu.
        holidays = frozenset(
            date.fromisoformat(str(h)) for h in (cfg.get("holidays") or [])
        )
    except Exception as e:
        err_msg = f"[CRITICAL] heartbeat check không đọc được config/config.yaml: {type(e).__name__}: {e}"[:300]
        _print_safe(err_msg)
        if not args.dry_run:
            send_telegram(err_msg)
        return 1

    # Việc 2 (Brief 142): Canh các job 24/7 theo lịch (đọc log của run_if_docker_up.sh)
    logs_dir = args.logs_dir
    job_last_seen: dict[str, tuple[datetime | None, str | None]] = {}
    for branch, job_cfg in SCHEDULE_WATCH_JOBS.items():
        log_path = os.path.join(logs_dir, job_cfg.log_file)
        job_last_seen[branch] = get_last_called_timestamp(log_path, job_cfg.label)

    sched_state_file = args.state_file or os.path.join(logs_dir, SCHEDULE_STATE_NAME)
    prev_sched_state = load_schedule_state(sched_state_file)
    sched_alerts, new_sched_state, sched_info_logs = evaluate_schedule_health(
        job_last_seen, now, prev_sched_state
    )

    # Chỉ cảnh báo trong giờ giao dịch (trừ khi chạy --dry-run để chẩn đoán/test)
    now_tz = now.astimezone(TZ)
    pre_market = time(8, 0) <= now_tz.time() < time(9, 0) and is_trading_day(
        now_tz.date(), holidays
    )
    if not is_trading_time(now, holidays) and not pre_market and not args.dry_run:
        return 0

    if args.dry_run:
        for info in sched_info_logs:
            _print_safe(info)

    messages = []
    if sched_alerts:
        messages.extend(sched_alerts)

    try:
        with psycopg.connect(dsn, connect_timeout=10) as c:
            rows = c.execute("SELECT service, last_seen FROM heartbeat").fetchall()
            placeholders = ",".join(["%s"] * len(symbols))
            max_ts_row = c.execute(
                f"SELECT max(ts) FROM bars WHERE symbol IN ({placeholders})",
                list(symbols),
            ).fetchone()
            # 2C: doc engine_state + positions de kiem bat bien so sach
            es = c.execute(
                "SELECT cash, realized_pnl FROM engine_state WHERE id = 1"
            ).fetchone()
            pos_rows = c.execute(
                "SELECT avg_price, qty FROM positions WHERE qty != 0"
            ).fetchall()
    except Exception as e:
        err_msg = f"[CRITICAL] heartbeat check không đọc được DB: {type(e).__name__}: {e}"[:300]
        _print_safe(err_msg)
        messages.append(err_msg)
        if not args.dry_run:
            send_telegram(err_msg)
            save_schedule_state(sched_state_file, new_sched_state)
        return 1
    max_ts = max_ts_row[0] if max_ts_row else None

    stale = stale_services(rows, now, max_age)
    if stale:
        messages.append(
            f"[CRITICAL] service ngừng heartbeat quá {max_age}s: {', '.join(stale)}"
        )
    # 2C: bat bien so sach — cash + Σ(avg_price*qty) - capital == realized_pnl
    if es is not None:
        cash, realized = float(es[0]), float(es[1])
        positions_value = sum(float(r[0]) * float(r[1]) for r in pos_rows)
        dev = ledger_deviation(cash, realized, positions_value)
        if abs(dev) > LEDGER_TOLERANCE:
            # FEE-ALARM-2 bai hoc: chuong bao tuyet doi khong duoc nem exception —
            # dung lenh dang kiem, moi so lay tu DB, khong tinh gi them.
            messages.append(
                f"[CRITICAL] hai sổ sách LỆCH: vế trái (cash + giá vốn − vốn) "
                f"= {cash + positions_value - CAPITAL:,.2f}, vế phải (realized_pnl) "
                f"= {realized:,.2f}, độ lệch {dev:,.2f} VND"
            )
    if bar_stale(max_ts, now, holidays=holidays):
        # FEE-ALARM-2 Lỗi 1: max_ts=None (feed chưa từng nối được) mà dựng
        # tin nhắn với `now - max_ts` -> TypeError, chuông báo CHẾT đúng lúc
        # cần nhất. Dead-man's switch tuyệt đối không được ném exception.
        if max_ts is None:
            messages.append(
                "[CRITICAL] dữ liệu ngừng chảy: không có bar nào cả ngày "
                "(feed chưa từng nối được) trong cửa sổ kiểm tra"
            )
        else:
            messages.append(
                f"[CRITICAL] dữ liệu ngừng chảy: bar cuối cùng {max_ts} "
                f"({(now - max_ts).total_seconds() / 60:.0f} phút trước) "
                f"trong cửa sổ kiểm tra"
            )
    # 2B: dùng lại Storage.load_ssi_token — không viết truy vấn mới
    saved = Storage(dsn).load_ssi_token()
    expiry = saved.get("refresh_token_expires_at") if saved else None
    status = token_expiry_status(expiry, now, holidays)
    if status == "WARN":
        messages.append(
            f"[WARN] token SSI sắp hết hạn ({datetime.fromtimestamp(expiry, TZ):%H:%M %d/%m}) — "
            f"chạy scripts/spike_ssi_sdk_auth.py RỒI scripts/load_token_to_db.py "
            f"(bước thứ hai là cầu nối sang DB — chính nó hay bị bỏ quên)"
        )
    elif status == "CRITICAL":
        messages.append(
            "[CRITICAL] token SSI đã hết hạn hoặc không có trong DB — "
            "chạy scripts/spike_ssi_sdk_auth.py RỒI scripts/load_token_to_db.py "
            "(bước thứ hai là cầu nối sang DB — chính nó hay bị bỏ quên)"
        )

    # 2D: vi the ngung dong bo — dung LAI Storage.read_position_sync_ts (tien le
    # 2B dung lai Storage.load_ssi_token), KHONG viet truy van SQL moi
    sync_ts = Storage(dsn).read_position_sync_ts(real_order_account)
    if position_sync_stale(sync_ts, now):
        # FEE-ALARM-2 bai hoc: sync_ts=None (chua tung dong bo) ma dung
        # `now - sync_ts` -> TypeError, chuong bao CHET dung luc can nhat.
        if sync_ts is None:
            messages.append(
                f"[CRITICAL] vị thế {real_order_account} chưa từng đồng bộ "
                "(không có dòng account_sync_log) — đặt lệnh trên vị thế cũ"
            )
        else:
            messages.append(
                f"[CRITICAL] vị thế {real_order_account} ngừng đồng bộ: "
                f"lần cuối {sync_ts} "
                f"({(now - sync_ts).total_seconds() / 60:.0f} phút trước)"
            )

    # Brief dot 10 Task 4: Cảnh báo cạn lịch nghỉ lễ từ 01/10
    holiday_warn = check_holiday_exhaustion(holidays, now)
    if holiday_warn:
        messages.append(holiday_warn)

    if messages:
        # Brief 2026-09-01 (dot 3) Task B: in ly do ra stdout TRUOC khi gui —
        # truoc day chi gui Telegram roi return 1, log chi co EXIT=1 khong biet
        # nhanh nao no; va neu send_telegram nem exception thi khong con ban ghi
        # nao o dau. Chuong bao phai de lai dau vet tai cho.
        _print_safe("\n".join(messages))
        if args.dry_run:
            _print_safe(
                "[DRY-RUN] Không gửi Telegram thật. Không cập nhật file trạng thái."
            )
            return 1
        send_telegram("\n".join(messages))
        save_schedule_state(sched_state_file, new_sched_state)
        return 1

    if not args.dry_run:
        save_schedule_state(sched_state_file, new_sched_state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
