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
import os
import re
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, NamedTuple

import psycopg
import yaml

try:
    from scripts._alert_common import (
        load_json_state,
        outbox_name,
        save_json_state,
        send_with_outbox,
    )
    from scripts._db_common import REPO_LOGS_DIR
except ImportError:
    from _alert_common import (
        load_json_state,
        outbox_name,
        save_json_state,
        send_with_outbox,
    )
    from _db_common import REPO_LOGS_DIR

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

DEFAULT_LOGS_DIR = REPO_LOGS_DIR
SCHEDULE_STATE_NAME = ".schedule_health_state.json"
DEFAULT_SCHEDULE_STATE_FILE = os.path.join(DEFAULT_LOGS_DIR, SCHEDULE_STATE_NAME)
HEARTBEAT_OUTBOX_NAME = outbox_name("heartbeat")


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

# 11 nhánh sched.sh không canh 24/7 trong heartbeat (kèm lý do phân loại).
# LƯU Ý: Giờ chạy thật của từng job nằm ở DEPLOYMENT.md §9, không chép lại ở đây.
KHONG_CANH: dict[str, str] = {
    "heartbeat": "Chính là heartbeat (tự canh là đệ quy), do container-health canh chéo trong giờ giao dịch.",
    "daily-check": "Chỉ chạy buổi tối ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được.",
    "backfill": "Chỉ chạy buổi tối ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được.",
    "deploy-drift": "Chỉ chạy trước phiên ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được.",
    "engine-cam": "Chỉ chạy sau phiên ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được.",
    "engine-consumer": "Chỉ chạy lặp trong phiên ngày giao dịch, ngoài phiên và cuối tuần ngừng nên không dùng ngưỡng cố định 24/7 được.",
    "stream-health": "Chỉ chạy sau phiên ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được.",
    "orderbook-recorder": "Tiến trình thu thập chỉ chạy trong phiên ngày giao dịch, ngoài phiên và cuối tuần ngừng nên không dùng ngưỡng cố định 24/7 được.",
    "orderbook-daily-check": "Chỉ chạy sau phiên ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được.",
    "host-preflight": "Chạy theo chu kỳ tuần (buổi sáng trước tuần giao dịch mới), khoảng cách một tuần nên không dùng ngưỡng cố định 24/7 được.",
    "restore-drill": "Diễn tập phục hồi theo chu kỳ tuần (ban đêm cuối tuần), khoảng cách một tuần nên không dùng ngưỡng cố định 24/7 được.",
}


class JobExitPolicy(NamedTuple):
    branch: str  # Tên nhánh trong sched.sh
    log_file: str  # Tên file log trong logs/
    label: str  # Nhãn được ghi bởi run_if_docker_up.sh
    normal_exit_codes: frozenset[int]  # Các mã thoát coi là bình thường / đã tự báo
    reason: str  # Căn cứ dòng code và lý do phân loại


# Bảng chính sách mã thoát cho cả 16 nhánh sched.sh (Brief đợt 156)
SCHEDULE_EXIT_POLICIES: dict[str, JobExitPolicy] = {
    "heartbeat": JobExitPolicy(
        branch="heartbeat",
        log_file="heartbeat.log",
        label="heartbeat-check",
        normal_exit_codes=frozenset({0, 1}),
        reason="heartbeat_check.py:653-665. Mã 0 là OK, mã 1 là khi có cảnh báo đã tự gửi Telegram / outbox. Tự canh mã 1 sẽ đệ quy nhân đôi cảnh báo.",
    ),
    "daily-check": JobExitPolicy(
        branch="daily-check",
        log_file="daily-data-check.log",
        label="daily-data-check",
        normal_exit_codes=frozenset({0, 1}),
        reason="daily_data_check.py:237, 244, 277, 304, 310, 312. Mã 0 là đủ dữ liệu/ngày nghỉ; mã 1 là thiếu bar đã tự gửi Telegram. Mã 2 có HAI nghĩa (đo 03/10 trong logs/daily-data-check.log): (a) cờ lạ/argparse hoặc lỗi config/DB — chưa ai báo, đúng diện canh; (b) sự cố dữ liệu nặng 0 mã có bar — script ĐÃ tự gửi Telegram (02/10 05:47 và 05:53). Canh mã 2 nên ca (b) sẽ có tin trùng. Chấp nhận có chủ đích: trùng ở tin to nhất còn hơn bỏ sót ca (a). Muốn hết trùng thì phải phân biệt theo nội dung log, chưa làm.",
    ),
    "backfill": JobExitPolicy(
        branch="backfill",
        log_file="backfill.log",
        label="backfill",
        normal_exit_codes=frozenset({0}),
        reason="backfill_universe.py:223-261. Script không có cơ chế gửi Telegram. Mã 0 là nạp xong bình thường; mọi mã khác 0 là lỗi nạp/mạng/DB chưa ai báo.",
    ),
    "deploy-drift": JobExitPolicy(
        branch="deploy-drift",
        log_file="deploy-drift.log",
        label="deploy-drift",
        normal_exit_codes=frozenset({0, 1}),
        reason="deploy_drift_check.py:156, 215, 219. Mã 0 là không lệch; mã 1 là có lệch đã tự gửi Telegram qua alert_and_fail. Mã 2 là gửi Telegram hỏng hoặc lỗi chưa ai báo.",
    ),
    "container-health": JobExitPolicy(
        branch="container-health",
        log_file="container-health.log",
        label="container-health",
        normal_exit_codes=frozenset({0, 1, 2}),
        reason="container_health_check.py:497-499, 575, 585. Mã 0 là container khỏe; mã 1 là cảnh báo đã gửi Telegram; mã 2 là Docker chưa chạy (đã có docker_down_alert lo) hoặc gửi Telegram hỏng; chỉ mã kill/crash ngoại lai mới chưa ai báo.",
    ),
    "engine-cam": JobExitPolicy(
        branch="engine-cam",
        log_file="engine-cam.log",
        label="engine-cam",
        normal_exit_codes=frozenset({0, 1}),
        reason="check_silent_engine.py:141, 167, 177, 240. Mã 0 là OK; mã 1 là phát hiện engine câm đã tự gửi Telegram qua alert_and_fail. Mã 2 là lỗi config/symbols hoặc gửi Telegram hỏng.",
    ),
    "engine-consumer": JobExitPolicy(
        branch="engine-consumer",
        log_file="engine-consumer.log",
        label="engine-consumer",
        normal_exit_codes=frozenset({0, 1}),
        reason="engine_consumer_check.py:136, 149, 184, 188. Mã 0 là tiêu thụ bình thường/ngoài phiên; mã 1 là sự cố NATS/config/lag đã tự gửi Telegram. Mã khác là lỗi chưa ai báo.",
    ),
    "stream-health": JobExitPolicy(
        branch="stream-health",
        log_file="stream-health.log",
        label="stream-health",
        normal_exit_codes=frozenset({0}),
        reason="stream_health_check.py:546, 556, 572. Script không gửi Telegram. Mã 0 là độ phủ đạt; mã 1 (WARN <90%) và mã 2 (CRITICAL <50%/0 nến) hoàn toàn im lặng trong log chưa ai báo.",
    ),
    "orderbook-recorder": JobExitPolicy(
        branch="orderbook-recorder",
        log_file="orderbook-recorder.log",
        label="orderbook-recorder",
        normal_exit_codes=frozenset({0}),
        reason="record_vn30f_orderbook.py:844-855. Mã 0 là thu thập đủ phiên; mã 1 (crash) và mã 4 (bị Task Scheduler/Windows kill giữa chừng) không thể tự gửi cảnh báo.",
    ),
    "orderbook-daily-check": JobExitPolicy(
        branch="orderbook-daily-check",
        log_file="orderbook-daily-check.log",
        label="orderbook-daily-check",
        normal_exit_codes=frozenset({0, 1, 2}),
        reason="check_orderbook_daily.py:215, 246, 250. Mã 0 là OK; mã 1 (WARN) và mã 2 (CRITICAL) đều đã gọi trading.alerts.alert() nên tự gửi Telegram. LUU Y: script nay KHONG goi start_outbox nen KHONG co hang doi gui lai; gui hong la mat tin (cung lo voi 14 job con lai, xem DEPLOYMENT 8.6). Chỉ crash ngoại lai mới chưa ai báo.",
    ),
    "backup": JobExitPolicy(
        branch="backup",
        log_file="backup.log",
        label="backup",
        normal_exit_codes=frozenset({0}),
        reason="backup_db.sh:18, 22, 85. Shell script không có cơ chế gửi Telegram. Mã 0 là backup xong; mã 1 (lỗi pg_restore verify) và mã 2 (lỗi đối số) chưa ai báo.",
    ),
    "backup-check": JobExitPolicy(
        branch="backup-check",
        log_file="backup-check.log",
        label="backup-check",
        normal_exit_codes=frozenset({0, 1}),
        reason="backup_check.py:418, 421, 423, 431. Mã 0 là backup tốt; mã 1 là phát hiện lỗi backup đã tự gửi Telegram. Mã 2 là gửi Telegram hỏng hoặc crash chưa ai báo.",
    ),
    "orderbook-backup": JobExitPolicy(
        branch="orderbook-backup",
        log_file="orderbook-backup.log",
        label="orderbook-backup",
        normal_exit_codes=frozenset({0}),
        reason="backup_orderbook.sh:22, 26, 41, 60, 75. Shell script không có cơ chế gửi Telegram. Mã 0 là xong/không có file; mã 1 (không thấy thư mục / tar rỗng) và mã 2 chưa ai báo.",
    ),
    "disk-check": JobExitPolicy(
        branch="disk-check",
        log_file="disk-check.log",
        label="disk-check",
        normal_exit_codes=frozenset({0, 1}),
        reason="disk_check.py:150, 171, 181, 194, 196, 204. Mã 0 là đĩa đủ; mã 1 là thiếu đĩa đã tự gửi Telegram. Mã 2 là lỗi config/không đo được đĩa/gửi Telegram hỏng chưa ai báo.",
    ),
    "host-preflight": JobExitPolicy(
        branch="host-preflight",
        log_file="host-preflight.log",
        label="host-preflight",
        normal_exit_codes=frozenset({0}),
        reason="host_preflight.py:459, 825, 830, 847, 855. Script không gửi Telegram. Mã 0 là pass/warn/skip; mã 1 (có kiểm tra FAIL) và mã 2 (lỗi config/repo) chưa ai báo.",
    ),
    "restore-drill": JobExitPolicy(
        branch="restore-drill",
        log_file="restore-drill.log",
        label="restore-drill",
        normal_exit_codes=frozenset({0, 1}),
        reason="restore_drill.py:352, 362, 374, 376, 384. Mã 0 là diễn tập pass; mã 1 là lỗi restore đã tự gửi Telegram. Mã 2 là lỗi config/gửi Telegram hỏng chưa ai báo.",
    ),
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


def get_last_run_exit_code(
    log_path: str, label: str
) -> tuple[datetime | None, int | None, str | None]:
    r"""Đọc mốc thời gian và mã thoát của lần chạy gần nhất của nhãn `label` từ file log.

    Quy ước run_if_docker_up.sh:
      <YYYY-MM-DD HH:MM:SS> <nhãn> start
      ...
      EXIT=<RC>
    Hoặc:
      <YYYY-MM-DD HH:MM:SS> <nhãn> SKIP: ...
      ALERT_EXIT=<RC>

    Quy tắc an toàn (tránh bẫy):
      1. Neo đầu dòng r"^EXIT=(\d+)" để không khớp nhầm "ALERT_EXIT=".
      2. Gắn EXIT= vào đúng lần chạy: tìm dòng EXIT= SAU mốc start gần nhất.
      3. Nếu job đang chạy (đã có start nhưng chưa có EXIT=) -> exit_code = None.
      4. Nếu lần gọi gần nhất là SKIP -> exit_code = None (không tính là thất bại).

    Trả về:
      (start_dt, exit_code, None) nếu đọc được file log và tìm thấy mốc start.
      (None, None, reason) nếu không tìm thấy file hoặc không có dòng nào mang nhãn.
    """
    if not os.path.isfile(log_path):
        return None, None, f"file log không tồn tại ({os.path.basename(log_path)})"

    pattern_start = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
        + re.escape(label)
        + r"\s+start(?:\s|$)"
    )
    pattern_skip = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
        + re.escape(label)
        + r"\s+SKIP:(?:\s|$)"
    )
    pattern_exit = re.compile(r"^EXIT=(\d+)")

    last_start_dt: datetime | None = None
    last_exit_code: int | None = None
    latest_event_is_skip: bool = False

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m_start = pattern_start.match(line)
                if m_start:
                    try:
                        dt = datetime.strptime(
                            m_start.group(1), "%Y-%m-%d %H:%M:%S"
                        ).replace(tzinfo=TZ)
                        last_start_dt = dt
                        last_exit_code = None
                        latest_event_is_skip = False
                    except ValueError:
                        continue
                    continue

                m_skip = pattern_skip.match(line)
                if m_skip:
                    latest_event_is_skip = True
                    last_start_dt = None
                    last_exit_code = None
                    continue

                if last_start_dt is not None:
                    m_exit = pattern_exit.match(line)
                    if m_exit:
                        try:
                            last_exit_code = int(m_exit.group(1))
                        except ValueError:
                            pass
    except Exception as e:
        return None, None, f"không đọc được file log ({e})"

    if last_start_dt is None and not latest_event_is_skip:
        return (
            None,
            None,
            f"không tìm thấy dòng nào mang nhãn '{label}' trong {os.path.basename(log_path)}",
        )

    return last_start_dt, last_exit_code, None


def evaluate_schedule_health(
    job_last_seen: dict[str, tuple[datetime | None, str | None]],
    now: datetime,
    previous_state: dict[str, dict[str, Any]],
    watch_jobs: dict[str, WatchJobConfig] = SCHEDULE_WATCH_JOBS,
    job_exit_codes: (
        dict[str, tuple[datetime | None, int | None, str | None]] | None
    ) = None,
    exit_policies: dict[str, JobExitPolicy] = SCHEDULE_EXIT_POLICIES,
) -> tuple[list[str], dict[str, dict[str, Any]], list[str]]:
    """Đánh giá trạng thái chạy và mã thoát của các job theo lịch (pure function).

    Chỉ báo khi chuyển trạng thái:
      - Canh lịch 24/7 (watch_jobs):
        + từ 'ok' (hoặc lần đầu / thiếu state) sang 'stale' -> báo CRITICAL một lần.
        + từ 'stale' sang 'ok' -> báo INFO hồi phục một lần.
        + kéo dài trạng thái cũ -> im lặng (chỉ ghi log info).
      - Canh mã thoát (exit_policies, nếu job_exit_codes được cung cấp):
        + lần chạy cuối có mã thoát không thuộc normal_exit_codes:
          * nếu trước đó chưa báo hoặc mã khác -> báo CRITICAL một lần.
          * nếu trước đó đã báo cùng mã -> im lặng (ghi log info).
        + lần chạy cuối thành công (thuộc normal_exit_codes):
          * nếu trước đó thất bại -> báo INFO hồi phục một lần.
          * nếu trước đó ok -> im lặng.
        + không có dòng EXIT= (đang chạy hoặc file rỗng) -> im lặng.

    Trả về: (alerts, new_state, info_logs)
    """
    alerts = []
    info_logs = []
    new_state = dict(previous_state)
    now_tz = now.astimezone(TZ)

    # 1. Canh tuổi (staleness) các job 24/7
    for branch, cfg in watch_jobs.items():
        last_dt, reason = job_last_seen.get(branch, (None, "không có dữ liệu"))
        prev = previous_state.get(branch)
        prev_status = prev.get("status") if isinstance(prev, dict) else None

        if last_dt is None:
            current_status = "stale"
            stale_reason = (
                reason or f"không tìm thấy dòng nào của {cfg.label} trong log"
            )
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

        new_record = dict(prev) if isinstance(prev, dict) else {}
        new_record.update(
            {
                "status": current_status,
                "last_called": (
                    last_dt.strftime("%Y-%m-%d %H:%M:%S") if last_dt else None
                ),
                "checked_at": now_tz.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
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

    # 2. Canh mã thoát (exit codes)
    if job_exit_codes is not None:
        for branch, policy in exit_policies.items():
            last_run_dt, exit_code, _err = job_exit_codes.get(
                branch, (None, None, None)
            )
            prev = previous_state.get(branch)
            prev_exit_status = (
                prev.get("exit_status") if isinstance(prev, dict) else None
            )
            prev_exit_code = (
                prev.get("exit_code") if isinstance(prev, dict) else None
            )

            if exit_code is not None:
                if exit_code not in policy.normal_exit_codes:
                    current_exit_status = "failed"
                else:
                    current_exit_status = "ok"
            else:
                current_exit_status = None

            # Cập nhật vào new_state (bảo toàn các trường status/last_called nếu có)
            rec = new_state.get(branch)
            if not isinstance(rec, dict):
                rec = dict(prev) if isinstance(prev, dict) else {}
            if exit_code is not None:
                rec["exit_code"] = exit_code
                rec["exit_status"] = current_exit_status
                if "checked_at" not in rec:
                    rec["checked_at"] = now_tz.strftime("%Y-%m-%d %H:%M:%S")
            new_state[branch] = rec

            if current_exit_status == "failed":
                if prev_exit_status != "failed" or prev_exit_code != exit_code:
                    dt_str = (
                        last_run_dt.strftime("%Y-%m-%d %H:%M:%S")
                        if last_run_dt
                        else "không rõ"
                    )
                    alerts.append(
                        f"[CRITICAL] job theo lịch '{branch}' THẤT BẠI: "
                        f"lần chạy gần nhất lúc {dt_str} kết thúc với mã thoát {exit_code}"
                    )
                else:
                    info_logs.append(
                        f"[heartbeat-sched] INFO: {branch} vẫn thất bại (mã thoát {exit_code}) - đã báo trước đó"
                    )
            elif current_exit_status == "ok" and prev_exit_status == "failed":
                dt_str = (
                    last_run_dt.strftime("%Y-%m-%d %H:%M:%S")
                    if last_run_dt
                    else "không rõ"
                )
                alerts.append(
                    f"[INFO] job theo lịch '{branch}' ĐÃ HỒI PHỤC: "
                    f"lần chạy gần nhất lúc {dt_str} thành công (mã thoát {exit_code})"
                )

    return alerts, new_state, info_logs


def load_schedule_state(filepath: str) -> dict[str, dict[str, Any]]:
    """Đọc file trạng thái JSON. Nếu không tồn tại hoặc lỗi, trả về {}."""
    return load_json_state(filepath, "heartbeat")


def save_schedule_state(
    filepath: str, state: dict[str, dict[str, Any]]
) -> None:
    """Ghi trạng thái ra file JSON an toàn qua file tạm."""
    save_json_state(filepath, state)


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
            outbox_path = Path(args.logs_dir) / HEARTBEAT_OUTBOX_NAME
            ok = send_with_outbox(
                err_msg, send=send_telegram, outbox_path=outbox_path
            )
            if not ok:
                _print_safe(
                    "[heartbeat-check] GUI TELEGRAM HONG: cảnh báo chưa tới được Telegram"
                )
        return 1

    # Việc 2 (Brief 142 + Brief 156): Canh các job theo lịch (đọc log của run_if_docker_up.sh)
    logs_dir = args.logs_dir
    outbox_path = Path(logs_dir) / HEARTBEAT_OUTBOX_NAME
    job_last_seen: dict[str, tuple[datetime | None, str | None]] = {}
    for branch, job_cfg in SCHEDULE_WATCH_JOBS.items():
        log_path = os.path.join(logs_dir, job_cfg.log_file)
        job_last_seen[branch] = get_last_called_timestamp(log_path, job_cfg.label)

    job_exit_codes: dict[str, tuple[datetime | None, int | None, str | None]] = {}
    for branch, policy in SCHEDULE_EXIT_POLICIES.items():
        log_path = os.path.join(logs_dir, policy.log_file)
        job_exit_codes[branch] = get_last_run_exit_code(log_path, policy.label)

    sched_state_file = args.state_file or os.path.join(logs_dir, SCHEDULE_STATE_NAME)
    prev_sched_state = load_schedule_state(sched_state_file)
    sched_alerts, new_sched_state, sched_info_logs = evaluate_schedule_health(
        job_last_seen,
        now,
        prev_sched_state,
        watch_jobs=SCHEDULE_WATCH_JOBS,
        job_exit_codes=job_exit_codes,
        exit_policies=SCHEDULE_EXIT_POLICIES,
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
            ok = send_with_outbox(
                "\n".join(messages), send=send_telegram, outbox_path=outbox_path
            )
            if ok:
                save_schedule_state(sched_state_file, new_sched_state)
            else:
                _print_safe(
                    "[heartbeat-check] GUI TELEGRAM HONG: cảnh báo chưa tới được Telegram"
                )
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
        ok = send_with_outbox(
            "\n".join(messages), send=send_telegram, outbox_path=outbox_path
        )
        if ok:
            save_schedule_state(sched_state_file, new_sched_state)
        else:
            _print_safe(
                "[heartbeat-check] GUI TELEGRAM HONG: cảnh báo chưa tới được Telegram"
            )
        return 1

    if not args.dry_run:
        save_schedule_state(sched_state_file, new_sched_state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
