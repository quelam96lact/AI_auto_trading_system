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

Đợt 160 — "ngày nến thiếu phải có người biết vào sáng hôm sau":
- Kiểm KẾT QUẢ của chuỗi `backfill` -> `daily-check`: độ đủ nến NGÀY của ngày giao
  dịch liền trước, dùng lại `daily_data_check.assess_date` (KHÔNG chép logic đủ/thiếu).
  Hai job đó nằm trong `KHONG_CANH` (tuổi phụ thuộc cuối tuần) nên kết quả của chúng
  được kiểm gián tiếp ở đây.
- TRÙNG TIN CÓ CHỦ Ý với `daily-check`: nếu tối hôm trước nó đã báo thiếu thì sáng hôm
  sau heartbeat báo LẠI — "thiếu lúc 21:00" và "sáng ra vẫn chưa ai vá" là hai việc
  khác nhau. Mỗi ngày P chỉ báo một lần (xem PREV_DAY_BARS_STATE_NAME).
"""

import argparse
import os
import re
import statistics
import sys
import traceback
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
    from scripts._db_common import REPO_LOGS_DIR, default_backup_dir
    from scripts.daily_data_check import (
        NON_TRADING_DAY_MSG,
        NON_TRADING_DAY_PATTERN,
        NON_TRADING_DAYS_PREFIX,
        assess_date,
    )
except ImportError:
    from _alert_common import (
        load_json_state,
        outbox_name,
        save_json_state,
        send_with_outbox,
    )
    from _db_common import REPO_LOGS_DIR, default_backup_dir
    from daily_data_check import (
        NON_TRADING_DAY_MSG,
        NON_TRADING_DAY_PATTERN,
        NON_TRADING_DAYS_PREFIX,
        assess_date,
    )

from trading.alerts import AlertOutbox, _print_safe
from trading.calendar_vn import (
    TZ,
    is_trading_day,
    is_trading_time,
    market_minutes_between,
    previous_trading_day,
)
from trading.config import Config

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
# Đợt 160: trạng thái "đã báo thiếu nến ngày cho ngày P" — file RIÊNG, không nhét vào
# .schedule_health_state.json: file kia bị evaluate_schedule_health dựng lại toàn bộ
# mỗi lần chạy nên khoá lạ sẽ bị xoá mất.
PREV_DAY_BARS_STATE_NAME = ".prev_day_bars_state.json"
PREV_DAY_FOREIGN_FLOW_STATE_NAME = ".prev_day_foreign_flow_state.json"
PREV_DAY_5M_STATE_NAME = ".prev_day_5m_state.json"


class WatchJobConfig(NamedTuple):
    branch: str  # Tên nhánh trong sched.sh
    log_file: str  # Tên file log trong logs/
    label: str  # Nhãn được ghi bởi run_if_docker_up.sh
    max_age_seconds: int  # Ngưỡng tuổi tối đa của lần gọi gần nhất (giây)
    schedule_desc: str  # Mô tả lịch (cho báo cáo / alert)
    formula_note: str  # Câu số học giải thích ngưỡng
    skip_counts_as_run: bool = True  # Mặc định True: dòng SKIP tính là đã được gọi


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
        skip_counts_as_run=False,
    ),
    "orderbook-backup": WatchJobConfig(
        branch="orderbook-backup",
        log_file="orderbook-backup.log",
        label="orderbook-backup",
        max_age_seconds=26 * 3600,  # 26 giờ = 93,600 giây
        schedule_desc="02:30 hằng ngày",
        formula_note="chạy đúng trong phiên 08:00-15:00 tuổi 5.5h-12.5h (< 24h), lỡ lần 02:30 sáng thì lúc 08:00 tuổi 29.5h > 26h -> bắt ngay",
        skip_counts_as_run=False,
    ),
    "backup-check": WatchJobConfig(
        branch="backup-check",
        log_file="backup-check.log",
        label="backup-check",
        max_age_seconds=26 * 3600,  # 26 giờ = 93,600 giây
        schedule_desc="03:00 hằng ngày",
        formula_note="chạy đúng trong phiên 08:00-15:00 tuổi 5h-12h (< 24h), lỡ lần 03:00 sáng thì lúc 08:00 tuổi 29h > 26h -> bắt ngay",
        skip_counts_as_run=False,
    ),
}

# 16 nhánh sched.sh không canh 24/7 trong heartbeat (kèm lý do phân loại).
# LƯU Ý: Giờ chạy thật của từng job nằm ở DEPLOYMENT.md §9, không chép lại ở đây.
KHONG_CANH: dict[str, str] = {
    "heartbeat": "Chính là heartbeat (tự canh là đệ quy), do container-health canh chéo trong giờ giao dịch.",
    "daily-check": "Chỉ chạy buổi tối ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được. Kết quả của nó được heartbeat kiểm GIÁN TIẾP (đợt 160): mỗi ngày giao dịch, heartbeat kiểm độ đủ nến NGÀY của ngày giao dịch liền trước, nên job này chết thì sáng hôm sau có tin.",
    "backfill": "Chỉ chạy buổi tối ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được. Kết quả của nó được heartbeat kiểm GIÁN TIẾP (đợt 160): mỗi ngày giao dịch, heartbeat kiểm độ đủ nến NGÀY của ngày giao dịch liền trước, nên lần chạy SKIP thì sáng hôm sau có tin.",
    "backfill-5m": "Chỉ chạy buổi tối ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được. Kết quả của nó được heartbeat kiểm GIÁN TIẾP (đợt 198): mỗi ngày giao dịch, heartbeat kiểm số mã thanh khoản có nến 5 phút của ngày giao dịch liền trước, nên lần chạy SKIP thì sáng hôm sau có tin.",
    "foreign-flow": "Chỉ chạy buổi tối ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được. Kết quả của nó được heartbeat kiểm GIÁN TIẾP (đợt 190b): mỗi ngày giao dịch, heartbeat kiểm số dòng khối ngoại của ngày giao dịch liền trước, nên lần chạy SKIP thì sáng hôm sau có tin.",
    "catchup": "Chạy khi khởi động máy và buổi sáng thứ Hai–thứ Sáu, tuổi phụ thuộc ngày nghỉ, cuối tuần và lần khởi động nên không canh tuổi được; kết quả được canh bằng mã thoát.",
    "deploy-drift": "Chỉ chạy trước phiên ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được.",
    "engine-cam": "Chỉ chạy sau phiên ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được.",
    "engine-consumer": "Chỉ chạy lặp trong phiên ngày giao dịch, ngoài phiên và cuối tuần ngừng nên không dùng ngưỡng cố định 24/7 được.",
    "stream-health": "Chỉ chạy sau phiên ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được.",
    "orderbook-recorder": "Tiến trình thu thập chỉ chạy trong phiên ngày giao dịch, ngoài phiên và cuối tuần ngừng nên không dùng ngưỡng cố định 24/7 được.",
    "orderbook-daily-check": "Chỉ chạy sau phiên ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được.",
    "host-preflight": "Chạy theo chu kỳ tuần (buổi sáng trước tuần giao dịch mới), khoảng cách một tuần nên không dùng ngưỡng cố định 24/7 được.",
    "restore-drill": "Diễn tập phục hồi theo chu kỳ tuần (ban đêm cuối tuần), khoảng cách một tuần nên không dùng ngưỡng cố định 24/7 được; tuổi lần diễn tập OK được canh riêng qua get_last_successful_restore_timestamp (ngưỡng 9 ngày, đợt 218).",
    "backup-makeup": "Chạy bù mỗi giờ 24/7 khi thiếu dump; tự thoát 0 khi dump còn mới nên không canh theo lịch cố định.",
    "schedule-watch": "Chạy định kỳ mỗi giờ 24/7 để canh tuổi các job theo lịch ngoài giờ giao dịch; tự canh các job khác nên không canh đệ quy.",
    "morning-summary": "Chỉ chạy buổi sáng trước phiên các ngày giao dịch, tuổi phụ thuộc ngày nghỉ và cuối tuần nên không dùng ngưỡng cố định 24/7 được; kết quả được canh bằng mã thoát.",
}


class JobExitPolicy(NamedTuple):
    branch: str  # Tên nhánh trong sched.sh
    log_file: str  # Tên file log trong logs/
    label: str  # Nhãn được ghi bởi run_if_docker_up.sh
    normal_exit_codes: frozenset[int]  # Các mã thoát coi là bình thường / đã tự báo
    reason: str  # Căn cứ dòng code và lý do phân loại


# Bảng chính sách mã thoát cho cả 21 nhánh sched.sh (Brief đợt 156, cập nhật đợt 217)
SCHEDULE_EXIT_POLICIES: dict[str, JobExitPolicy] = {
    "heartbeat": JobExitPolicy(
        branch="heartbeat",
        log_file="heartbeat.log",
        label="heartbeat-check",
        normal_exit_codes=frozenset({0, 1}),
        reason="heartbeat_check.py:653-665. Mã 0 là OK, mã 1 là khi có cảnh báo đã tự gửi Telegram / outbox; mã 3 là crash/ngoại lệ chưa bắt (đợt 217). Tự canh mã 1 sẽ đệ quy nhân đôi cảnh báo.",
    ),
    "daily-check": JobExitPolicy(
        branch="daily-check",
        log_file="daily-data-check.log",
        label="daily-data-check",
        normal_exit_codes=frozenset({0, 1}),
        reason="daily_data_check.py:237, 244, 277, 304, 310, 312. Mã 0 là đủ dữ liệu/ngày nghỉ; mã 1 là thiếu bar đã tự gửi Telegram; mã 3 là crash/ngoại lệ chưa bắt (đợt 217). Mã 2 có HAI nghĩa (đo 03/10 trong logs/daily-data-check.log): (a) cờ lạ/argparse hoặc lỗi config/DB — chưa ai báo, đúng diện canh; (b) sự cố dữ liệu nặng 0 mã có bar — script ĐÃ tự gửi Telegram (02/10 05:47 và 05:53). Canh mã 2 nên ca (b) sẽ có tin trùng. Chấp nhận có chủ đích: trùng ở tin to nhất còn hơn bỏ sót ca (a). Muốn hết trùng thì phải phân biệt theo nội dung log, chưa làm.",
    ),
    "backfill": JobExitPolicy(
        branch="backfill",
        log_file="backfill.log",
        label="backfill",
        normal_exit_codes=frozenset({0}),
        reason="backfill_universe.py:223-261. Script không có cơ chế gửi Telegram. Mã 0 là nạp xong bình thường; mọi mã khác 0 là lỗi nạp/mạng/DB chưa ai báo.",
    ),
    "backfill-5m": JobExitPolicy(
        branch="backfill-5m",
        log_file="backfill-5m.log",
        label="backfill-5m",
        normal_exit_codes=frozenset({0}),
        reason="backfill_universe.py:220-271. Script không có cơ chế gửi Telegram. Mã 0 là nạp xong bình thường; mọi mã khác 0 là lỗi nạp/mạng/DB chưa ai báo.",
    ),
    "foreign-flow": JobExitPolicy(
        branch="foreign-flow",
        log_file="foreign-flow.log",
        label="foreign-flow",
        normal_exit_codes=frozenset({0}),
        reason="backfill_foreign_flow.py:78 (mã 1 sai định dạng ngày), :115 (mã 2 lỗi API SSI), :90 (mã 3 universe rỗng). Mã 0 là nạp xong bình thường; script không gửi Telegram nên mọi mã khác 0 là lỗi chưa ai báo.",
    ),
    "deploy-drift": JobExitPolicy(
        branch="deploy-drift",
        log_file="deploy-drift.log",
        label="deploy-drift",
        normal_exit_codes=frozenset({0, 1}),
        reason="deploy_drift_check.py:156, 215, 219. Mã 0 là không lệch; mã 1 là có lệch đã tự gửi Telegram qua alert_and_fail; mã 3 là crash/ngoại lệ chưa bắt (đợt 217). Mã 2 là gửi Telegram hỏng hoặc lỗi chưa ai báo.",
    ),
    "container-health": JobExitPolicy(
        branch="container-health",
        log_file="container-health.log",
        label="container-health",
        normal_exit_codes=frozenset({0, 1, 2}),
        reason="container_health_check.py:497-499, 575, 585. Mã 0 là container khỏe; mã 1 là cảnh báo đã gửi Telegram; mã 2 là Docker chưa chạy (đã có docker_down_alert lo) hoặc gửi Telegram hỏng; mã 3 là crash/ngoại lệ chưa bắt (đợt 217); mã 4 là Docker daemon đang chạy nhưng không phản hồi trong 30s sau khi thử lại (đợt 218 Task 6) hoặc lỗi đọc container kéo dài (đợt 223), không thuộc normal_exit_codes để chuông báo thất bại.",
    ),
    "engine-cam": JobExitPolicy(
        branch="engine-cam",
        log_file="engine-cam.log",
        label="engine-cam",
        normal_exit_codes=frozenset({0, 1}),
        reason="check_silent_engine.py:149, 180, 197, 201, 266, 274. Mã 0 là OK hoặc `symbols: []` (bỏ qua có chủ đích, đợt 231); mã 1 là phát hiện engine câm đã tự gửi Telegram qua outbox; mã 3 là crash/ngoại lệ chưa bắt (đợt 217). Mã 2 là config thiếu/hỏng khoá symbols hoặc gửi Telegram hỏng.",
    ),
    "engine-consumer": JobExitPolicy(
        branch="engine-consumer",
        log_file="engine-consumer.log",
        label="engine-consumer",
        normal_exit_codes=frozenset({0, 1}),
        reason="engine_consumer_check.py:136, 149, 184, 188. Mã 0 là tiêu thụ bình thường/ngoài phiên; mã 1 là sự cố NATS/config/lag đã tự gửi Telegram; mã 3 là crash/ngoại lệ chưa bắt (đợt 217). Mã khác là lỗi chưa ai báo.",
    ),
    "stream-health": JobExitPolicy(
        branch="stream-health",
        log_file="stream-health.log",
        label="stream-health",
        normal_exit_codes=frozenset({0}),
        reason="stream_health_check.py:546, 556, 572. Mã 0 là độ phủ đạt. Trước đợt 218 script không gửi Telegram: mã 1 (WARN <90%) và mã 2 (CRITICAL <50%/0 nến) hoàn toàn im lặng trong log, chưa ai báo. Từ đợt 218: mã 2 (CRITICAL) gửi Telegram qua send_with_outbox (outbox stream-health); mã 1 (WARN) vẫn không gửi Telegram.",
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
        reason="check_orderbook_daily.py:215, 246, 250. Mã 0 là OK; mã 1 (WARN) và mã 2 (CRITICAL) đều đã gọi trading.alerts.alert() nên tự gửi Telegram. Mã 3 là crash/ngoại lệ chưa bắt (đợt 217). LUU Y: script nay KHONG goi start_outbox nen KHONG co hang doi gui lai; gui hong la mat tin (cung lo voi 14 job con lai, xem DEPLOYMENT 8.6).",
    ),
    "backup": JobExitPolicy(
        branch="backup",
        log_file="backup.log",
        label="backup",
        normal_exit_codes=frozenset({0}),
        reason="backup_db.sh:18, 22, 85. Shell script không có cơ chế gửi Telegram. Mã 0 là backup xong; mã 1 (lỗi pg_restore verify) và mã 2 (lỗi đối số) chưa ai báo.",
    ),
    "backup-makeup": JobExitPolicy(
        branch="backup-makeup",
        log_file="backup-makeup.log",
        label="backup-makeup",
        normal_exit_codes=frozenset({0}),
        reason="backup_db.sh. Shell script không có cơ chế gửi Telegram. Mã 0 là backup xong hoặc skip vì dump còn mới; mã 1 và 2 chưa ai báo.",
    ),
    "backup-check": JobExitPolicy(
        branch="backup-check",
        log_file="backup-check.log",
        label="backup-check",
        normal_exit_codes=frozenset({0, 1}),
        reason="backup_check.py:418, 421, 423, 431. Mã 0 là backup tốt; mã 1 là phát hiện lỗi backup đã tự gửi Telegram; mã 3 là crash/ngoại lệ chưa bắt (đợt 217). Mã 2 là gửi Telegram hỏng hoặc lỗi config chưa ai báo.",
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
        reason="disk_check.py:150, 171, 181, 194, 196, 204. Mã 0 là đĩa đủ; mã 1 là thiếu đĩa đã tự gửi Telegram; mã 3 là crash/ngoại lệ chưa bắt (đợt 217). Mã 2 là lỗi config/không đo được đĩa/gửi Telegram hỏng chưa ai báo.",
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
        reason="restore_drill.py:352, 362, 374, 376, 384. Mã 0 là diễn tập pass; mã 1 là lỗi restore đã tự gửi Telegram; mã 3 là crash/ngoại lệ chưa bắt (đợt 217). Mã 2 là lỗi config/gửi Telegram hỏng chưa ai báo.",
    ),
    "catchup": JobExitPolicy(
        branch="catchup",
        log_file="catchup.log",
        label="catchup",
        normal_exit_codes=frozenset({0}),
        reason="startup_catchup.py. Mã 0 là nạp bù xong và kiểm tra đủ; mã 1 là có bước lỗi, ngày thiếu, hoặc khoảng hỏng vượt --max-days.",
    ),
    "daily-engine": JobExitPolicy(
        branch="daily-engine",
        log_file="daily-engine.log",
        label="daily-engine",
        normal_exit_codes=frozenset({0}),
        reason="trading.daily_engine.runner: mã 0 là ổn (khớp/cập nhật xong hoặc không có phiên mới); mã 1 là dữ liệu chưa đủ (>=90% mã active); mã 2 là cấu hình hoặc strategy sổ không khớp; mã 3 là ngoại lệ chưa bắt.",
    ),
    "universe-refresh": JobExitPolicy(
        branch="universe-refresh",
        log_file="universe-refresh.log",
        label="universe-refresh",
        normal_exit_codes=frozenset({0}),
        reason="refresh_universe.py. Mã 0 là làm mới xong hoặc chưa tới hạn; mã 1 là backfill lỗi hoặc cổng co rút chặn (cổng đã gửi Telegram).",
    ),
    "schedule-watch": JobExitPolicy(
        branch="schedule-watch",
        log_file="schedule-watch.log",
        label="schedule-watch",
        normal_exit_codes=frozenset({0, 1}),
        reason="heartbeat_check.py: mã 0 khi mọi job bình thường; mã 1 khi có cảnh báo đã tự gửi Telegram; mã 3 khi crash/ngoại lệ chưa bắt (đợt 217).",
    ),
    "morning-summary": JobExitPolicy(
        branch="morning-summary",
        log_file="morning-summary.log",
        label="morning-summary",
        normal_exit_codes=frozenset({0}),
        reason="heartbeat_check.py: tóm tắt sáng lúc 08:00 ngày giao dịch. Thoát 0 khi gửi thành công hoặc ngày nghỉ; thoát 1 khi gửi hỏng vào outbox để schedule-watch bắt (Lead điều chỉnh 4 đợt 218).",
    ),
}


class LastCalledTimestamp(tuple):
    """2-tuple (dt, reason) hỗ trợ thuộc tính skip_count và tương thích ngược hoàn toàn."""

    skip_count: int

    def __new__(cls, dt: datetime | None, reason: str | None, skip_count: int = 0):
        obj = super().__new__(cls, (dt, reason))
        obj.skip_count = skip_count
        return obj


def get_last_called_timestamp(
    log_path: str, label: str, skip_counts_as_run: bool = True
) -> LastCalledTimestamp:
    """Đọc mốc thời gian lần gọi gần nhất của nhãn `label` từ file log.

    Quy ước run_if_docker_up.sh:
      <YYYY-MM-DD HH:MM:SS> <nhãn> start
      <YYYY-MM-DD HH:MM:SS> <nhãn> SKIP: ...
      <YYYY-MM-DD HH:MM:SS> <nhãn> ERROR: ...

    Nếu skip_counts_as_run=True (mặc định):
      Khớp mọi dòng mang nhãn (dòng SKIP cũng tính là đã được gọi).
    Nếu skip_counts_as_run=False:
      Chỉ tính dòng `start` là lần chạy thật cuối cùng. Đếm số dòng SKIP kể từ lần start đó.

    Trả về:
      LastCalledTimestamp(dt, None, skip_count) nếu tìm thấy mốc hợp lệ.
      LastCalledTimestamp(None, reason, skip_count) nếu không đọc được hoặc không tìm thấy.
    """
    if not os.path.isfile(log_path):
        return LastCalledTimestamp(
            None, f"file log không tồn tại ({os.path.basename(log_path)})", 0
        )

    pattern_any = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+" + re.escape(label) + r"(?:\s|$)"
    )
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

    last_dt = None
    skip_count_since_start = 0

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if skip_counts_as_run:
                    m = pattern_any.match(line)
                    if m:
                        try:
                            dt = datetime.strptime(
                                m.group(1), "%Y-%m-%d %H:%M:%S"
                            ).replace(tzinfo=TZ)
                            last_dt = dt
                        except ValueError:
                            continue
                else:
                    m_start = pattern_start.match(line)
                    if m_start:
                        try:
                            dt = datetime.strptime(
                                m_start.group(1), "%Y-%m-%d %H:%M:%S"
                            ).replace(tzinfo=TZ)
                            last_dt = dt
                            skip_count_since_start = 0
                        except ValueError:
                            pass
                    elif pattern_skip.match(line):
                        skip_count_since_start += 1
    except Exception as e:
        return LastCalledTimestamp(None, f"không đọc được file log ({e})", 0)

    if last_dt is None:
        if not skip_counts_as_run and skip_count_since_start > 0:
            return LastCalledTimestamp(
                None,
                f"chưa từng chạy thật (đã có {skip_count_since_start} lần SKIP)",
                skip_count_since_start,
            )
        return LastCalledTimestamp(
            None,
            f"không tìm thấy dòng nào mang nhãn '{label}' trong {os.path.basename(log_path)}",
            0,
        )
    return LastCalledTimestamp(last_dt, None, skip_count_since_start)


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


def get_job_runs(
    log_path: str, label: str
) -> tuple[list[tuple[datetime, int | None]], str | None]:
    r"""Đọc tất cả các lần chạy của nhãn `label` từ file log theo thứ tự thời gian.

    Quy tắc an toàn (tránh bẫy):
      1. Neo đầu dòng r"^EXIT=(\d+)" để không khớp nhầm "ALERT_EXIT=".
      2. Gắn EXIT= vào đúng lần chạy: mỗi start ghi nhận một run; khi gặp start
         tiếp theo hoặc SKIP hoặc EOF thì đóng run đó.
      3. Nếu job đang chạy (đã có start nhưng chưa có EXIT=) -> exit_code = None.
      4. Dòng SKIP không tạo run mới và kết thúc run đang mở (nếu có).

    Trả về:
      (runs, None) với runs = [(start_dt, exit_code), ...].
      ([], reason) nếu file không tồn tại hoặc lỗi đọc.
    """
    if not os.path.isfile(log_path):
        return [], f"file log không tồn tại ({os.path.basename(log_path)})"

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

    runs: list[tuple[datetime, int | None]] = []
    current_start_dt: datetime | None = None
    current_exit_code: int | None = None

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m_start = pattern_start.match(line)
                if m_start:
                    if current_start_dt is not None:
                        runs.append((current_start_dt, current_exit_code))
                    try:
                        current_start_dt = datetime.strptime(
                            m_start.group(1), "%Y-%m-%d %H:%M:%S"
                        ).replace(tzinfo=TZ)
                        current_exit_code = None
                    except ValueError:
                        current_start_dt = None
                        current_exit_code = None
                    continue

                m_skip = pattern_skip.match(line)
                if m_skip:
                    if current_start_dt is not None:
                        runs.append((current_start_dt, current_exit_code))
                    current_start_dt = None
                    current_exit_code = None
                    continue

                if current_start_dt is not None:
                    m_exit = pattern_exit.match(line)
                    if m_exit:
                        try:
                            current_exit_code = int(m_exit.group(1))
                        except ValueError:
                            pass
    except Exception as e:
        return runs, f"không đọc được file log ({e})"

    if current_start_dt is not None:
        runs.append((current_start_dt, current_exit_code))

    return runs, None


RESTORE_DRILL_MAX_AGE_SECONDS = 9 * 86400  # 9 ngày (chu kỳ tuần 7 ngày + 2 ngày dư)


def get_last_successful_restore_timestamp(
    log_path: str,
) -> tuple[datetime | None, str | None]:
    """Đọc mốc thời gian của lần diễn tập phục hồi thành công gần nhất từ log_path.

    Định dạng logs/restore-drill.log:
      <YYYY-MM-DD HH:MM:SS> restore-drill start
      ...
      Diễn tập OK: <dump>, ...
      EXIT=0

    Dòng 'Diễn tập OK:' không có timestamp. Mốc thời gian lấy từ dòng
    '<ts> restore-drill start' gần nhất đứng trước dòng OK đó.

    Trả về:
      (dt, None) nếu tìm thấy lần diễn tập OK.
      (None, reason) nếu không tìm thấy file hoặc chưa từng có dòng Diễn tập OK.
    """
    if not os.path.isfile(log_path):
        return None, f"file log không tồn tại ({os.path.basename(log_path)})"

    pattern_start = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+restore-drill\s+start(?:\s|$)"
    )

    last_ok_dt = None
    current_start_dt = None

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m_start = pattern_start.match(line)
                if m_start:
                    try:
                        current_start_dt = datetime.strptime(
                            m_start.group(1), "%Y-%m-%d %H:%M:%S"
                        ).replace(tzinfo=TZ)
                    except ValueError:
                        current_start_dt = None
                elif "Diễn tập OK:" in line and current_start_dt is not None:
                    last_ok_dt = current_start_dt
    except Exception as e:
        return None, f"không đọc được file log ({e})"

    if last_ok_dt is None:
        return (
            None,
            "chưa từng diễn tập thành công (không tìm thấy dòng 'Diễn tập OK:' sau mốc start)",
        )
    return last_ok_dt, None


def _eval_watch_jobs_staleness(
    job_last_seen: dict[str, tuple[datetime | None, str | None]],
    now_tz: datetime,
    previous_state: dict[str, dict[str, Any]],
    watch_jobs: dict[str, WatchJobConfig],
    new_state: dict[str, dict[str, Any]],
    alerts: list[str],
    info_logs: list[str],
) -> None:
    """Canh tuổi (staleness) các job 24/7 và cập nhật `new_state`, `alerts`, `info_logs`."""
    for branch, cfg in watch_jobs.items():
        val = job_last_seen.get(branch, (None, "không có dữ liệu"))
        if len(val) >= 3:
            last_dt, reason, skip_count = val[0], val[1], val[2]
        else:
            last_dt, reason = val[0], val[1]
            skip_count = getattr(val, "skip_count", 0)

        prev = previous_state.get(branch)
        prev_status = prev.get("status") if isinstance(prev, dict) else None

        if last_dt is None:
            current_status = "stale"
            if not getattr(cfg, "skip_counts_as_run", True) and skip_count > 0:
                stale_reason = (
                    f"chưa từng chạy thật (đã có {skip_count} lần SKIP trong log, lịch: {cfg.schedule_desc})"
                )
            else:
                stale_reason = (
                    reason or f"không tìm thấy dòng nào của {cfg.label} trong log"
                )
        else:
            age_seconds = (now_tz - last_dt).total_seconds()
            if age_seconds > cfg.max_age_seconds:
                current_status = "stale"
                age_minutes = age_seconds / 60
                max_minutes = cfg.max_age_seconds / 60
                if not getattr(cfg, "skip_counts_as_run", True):
                    skip_info = (
                        f", đã có {skip_count} lần SKIP kể từ đó"
                        if skip_count > 0
                        else ""
                    )
                    stale_reason = (
                        f"lần chạy thật cuối cùng lúc {last_dt:%Y-%m-%d %H:%M:%S} "
                        f"({age_minutes:.0f} phút trước > ngưỡng {max_minutes:.0f} phút, lịch: {cfg.schedule_desc})"
                        f"{skip_info}"
                    )
                else:
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
        if not getattr(cfg, "skip_counts_as_run", True):
            new_record["skip_count"] = skip_count
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


def _eval_job_exit_codes(
    job_exit_codes: dict[str, tuple[datetime | None, int | None, str | None]] | None,
    job_runs: dict[str, list[tuple[datetime, int | None]]] | None,
    now_tz: datetime,
    previous_state: dict[str, dict[str, Any]],
    exit_policies: dict[str, JobExitPolicy],
    new_state: dict[str, dict[str, Any]],
    alerts: list[str],
    info_logs: list[str],
) -> None:
    """Canh mã thoát của các job theo lịch và cập nhật `new_state`, `alerts`, `info_logs`."""
    for branch, policy in exit_policies.items():
        branch_runs: list[tuple[datetime, int | None]] = []
        if job_runs is not None and branch in job_runs:
            branch_runs = list(job_runs[branch])
        elif job_exit_codes is not None and branch in job_exit_codes:
            val = job_exit_codes[branch]
            if len(val) >= 4 and isinstance(val[3], list):
                branch_runs = list(val[3])
            elif val[0] is not None:
                branch_runs = [(val[0], val[1])]

        if branch_runs:
            last_run_dt, last_exit_code = branch_runs[-1]
        elif job_exit_codes is not None and branch in job_exit_codes:
            last_run_dt, last_exit_code = (
                job_exit_codes[branch][0],
                job_exit_codes[branch][1],
            )
        else:
            last_run_dt, last_exit_code = None, None

        prev = previous_state.get(branch)
        prev_exit_status = (
            prev.get("exit_status") if isinstance(prev, dict) else None
        )
        prev_exit_code = (
            prev.get("exit_code") if isinstance(prev, dict) else None
        )
        prev_cursor_str = (
            prev.get("exit_seen_until") if isinstance(prev, dict) else None
        )
        prev_cursor_dt: datetime | None = None
        if prev_cursor_str:
            try:
                prev_cursor_dt = datetime.strptime(
                    prev_cursor_str, "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=TZ)
            except ValueError:
                prev_cursor_dt = None

        if last_exit_code is not None:
            if last_exit_code not in policy.normal_exit_codes:
                current_exit_status = "failed"
            else:
                current_exit_status = "ok"
        else:
            current_exit_status = None

        # Cập nhật vào new_state (bảo toàn các trường status/last_called nếu có)
        rec = new_state.get(branch)
        if not isinstance(rec, dict):
            rec = dict(prev) if isinstance(prev, dict) else {}
        if last_exit_code is not None:
            rec["exit_code"] = last_exit_code
            rec["exit_status"] = current_exit_status
            if "checked_at" not in rec:
                rec["checked_at"] = now_tz.strftime("%Y-%m-%d %H:%M:%S")

        # Cập nhật con trỏ: mốc start của lần chạy mới nhất đã đánh giá (đã có EXIT=)
        completed_runs = [r for r in branch_runs if r[1] is not None]
        if completed_runs:
            newest_eval_dt = completed_runs[-1][0]
            rec["exit_seen_until"] = newest_eval_dt.strftime("%Y-%m-%d %H:%M:%S")
        elif prev_cursor_str:
            rec["exit_seen_until"] = prev_cursor_str
        elif last_run_dt is not None:
            rec["exit_seen_until"] = last_run_dt.strftime("%Y-%m-%d %H:%M:%S")

        new_state[branch] = rec

        if current_exit_status == "failed":
            if prev_exit_status != "failed" or prev_exit_code != last_exit_code:
                dt_str = (
                    last_run_dt.strftime("%Y-%m-%d %H:%M:%S")
                    if last_run_dt
                    else "không rõ"
                )
                alerts.append(
                    f"[CRITICAL] job theo lịch '{branch}' THẤT BẠI: "
                    f"lần chạy gần nhất lúc {dt_str} kết thúc với mã thoát {last_exit_code}"
                )
            else:
                info_logs.append(
                    f"[heartbeat-sched] INFO: {branch} vẫn thất bại (mã thoát {last_exit_code}) - đã báo trước đó"
                )
        elif current_exit_status == "ok" and prev_exit_status == "failed":
            dt_str = (
                last_run_dt.strftime("%Y-%m-%d %H:%M:%S")
                if last_run_dt
                else "không rõ"
            )
            alerts.append(
                f"[INFO] job theo lịch '{branch}' ĐÃ HỒI PHỤC: "
                f"lần chạy gần nhất lúc {dt_str} thành công (mã thoát {last_exit_code})"
            )
        elif prev_cursor_dt is not None:
            new_failed_runs = [
                r
                for r in completed_runs
                if r[0] > prev_cursor_dt
                and r[1] not in policy.normal_exit_codes
            ]
            if new_failed_runs:
                count = len(new_failed_runs)
                unique_codes = sorted({r[1] for r in new_failed_runs})
                codes_str = ", ".join(str(c) for c in unique_codes)
                first_ts = new_failed_runs[0][0].strftime("%Y-%m-%d %H:%M:%S")
                last_ts = new_failed_runs[-1][0].strftime("%Y-%m-%d %H:%M:%S")
                time_str = (
                    f"lúc {first_ts}"
                    if first_ts == last_ts
                    else f"từ {first_ts} đến {last_ts}"
                )
                alerts.append(
                    f"[WARN] job theo lịch '{branch}' THẤT BẠI rồi tự hồi phục: "
                    f"{count} lần (mã {codes_str}) {time_str}"
                )


def _eval_restore_drill_staleness(
    restore_drill_last_ok: tuple[datetime | None, str | None],
    restore_drill_max_age_seconds: int,
    now_tz: datetime,
    previous_state: dict[str, dict[str, Any]],
    new_state: dict[str, dict[str, Any]],
    alerts: list[str],
    info_logs: list[str],
) -> None:
    """Canh tuổi lần diễn tập phục hồi thành công gần nhất (Task 2 - Brief đợt 218)."""
    last_ok_dt, ok_reason = restore_drill_last_ok
    prev_drill = previous_state.get("restore-drill-ok")
    prev_drill_status = (
        prev_drill.get("status") if isinstance(prev_drill, dict) else None
    )

    if last_ok_dt is None:
        current_drill_status = "stale"
        drill_stale_reason = ok_reason or "chưa từng diễn tập phục hồi thành công"
    else:
        age_seconds = (now_tz - last_ok_dt).total_seconds()
        if age_seconds > restore_drill_max_age_seconds:
            current_drill_status = "stale"
            age_days = age_seconds / 86400
            drill_stale_reason = (
                f"lần diễn tập thành công cuối cùng lúc {last_ok_dt:%Y-%m-%d %H:%M:%S} "
                f"({age_days:.1f} ngày trước > ngưỡng 9 ngày, lịch: chủ nhật hàng tuần)"
            )
        else:
            current_drill_status = "ok"
            drill_stale_reason = None

    new_drill_record = dict(prev_drill) if isinstance(prev_drill, dict) else {}
    new_drill_record.update(
        {
            "status": current_drill_status,
            "last_called": (
                last_ok_dt.strftime("%Y-%m-%d %H:%M:%S")
                if last_ok_dt
                else None
            ),
            "checked_at": now_tz.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    new_state["restore-drill-ok"] = new_drill_record

    if current_drill_status == "stale":
        if prev_drill_status != "stale":
            alerts.append(
                f"[CRITICAL] diễn tập phục hồi 'restore-drill' QUÁ HẠN: {drill_stale_reason}"
            )
        else:
            info_logs.append(
                f"[heartbeat-sched] INFO: restore-drill vẫn quá hạn diễn tập phục hồi ({drill_stale_reason}) - đã báo trước đó"
            )
    else:  # current_drill_status == "ok"
        if prev_drill_status == "stale":
            alerts.append(
                f"[INFO] diễn tập phục hồi 'restore-drill' ĐÃ THÀNH CÔNG: "
                f"lần diễn tập gần nhất lúc {last_ok_dt:%Y-%m-%d %H:%M:%S}"
            )


def evaluate_schedule_health(
    job_last_seen: dict[str, tuple[datetime | None, str | None]],
    now: datetime,
    previous_state: dict[str, dict[str, Any]],
    watch_jobs: dict[str, WatchJobConfig] = SCHEDULE_WATCH_JOBS,
    job_exit_codes: (
        dict[str, tuple[datetime | None, int | None, str | None]] | None
    ) = None,
    exit_policies: dict[str, JobExitPolicy] = SCHEDULE_EXIT_POLICIES,
    restore_drill_last_ok: tuple[datetime | None, str | None] | None = None,
    restore_drill_max_age_seconds: int = RESTORE_DRILL_MAX_AGE_SECONDS,
    job_runs: dict[str, list[tuple[datetime, int | None]]] | None = None,
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
    alerts: list[str] = []
    info_logs: list[str] = []
    new_state = dict(previous_state)
    now_tz = now.astimezone(TZ)

    # 1. Canh tuổi (staleness) các job 24/7
    _eval_watch_jobs_staleness(
        job_last_seen, now_tz, previous_state, watch_jobs, new_state, alerts, info_logs
    )

    # 2. Canh mã thoát (exit codes)
    if job_exit_codes is not None or job_runs is not None:
        _eval_job_exit_codes(
            job_exit_codes,
            job_runs,
            now_tz,
            previous_state,
            exit_policies,
            new_state,
            alerts,
            info_logs,
        )

    # 3. Canh tuổi lần diễn tập phục hồi thành công gần nhất (Task 2 - Brief đợt 218)
    if restore_drill_last_ok is not None:
        _eval_restore_drill_staleness(
            restore_drill_last_ok,
            restore_drill_max_age_seconds,
            now_tz,
            previous_state,
            new_state,
            alerts,
            info_logs,
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


# 10 phút (600 giây). Số đo ngày 09/11 cho thấy collector tự xác thực lại chỉ mất 11 giây sau khi hết hạn (M15).
SSI_TOKEN_GRACE_PERIOD_SECONDS: int = 10 * 60


def token_expiry_status(
    refresh_expires_at, now, holidays: frozenset = frozenset()
) -> str | None:
    """2B: token SSI sắp/đã hết hạn. refresh_expires_at = epoch seconds
    (từ Storage.load_ssi_token) hoặc None (ssi_auth_state rỗng).

    Trước đợt 220: quá hạn (< 0) trả CRITICAL ngay lập tức.
    Từ đợt 220: thêm ân hạn 10 phút (SSI_TOKEN_GRACE_PERIOD_SECONDS) trước khi báo CRITICAL
    vì collector tự xác thực lại sau khi hết hạn; trong ân hạn trả WARN.

    Trả về: None (ổn) | "WARN" (còn < 60 phút hoặc đã quá hạn < 10 phút) | "CRITICAL"
    (đã quá hạn >= 10 phút hoặc không có dòng nào).

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
    if remaining <= -SSI_TOKEN_GRACE_PERIOD_SECONDS:
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
    parser.add_argument(
        "--schedule-watch-only",
        action="store_true",
        help="Chỉ canh tuổi và mã thoát các job theo lịch 24/7, không kiểm tra thị trường/nến.",
    )
    parser.add_argument(
        "--morning-summary",
        action="store_true",
        help="Gửi tin tóm tắt sáng lúc 08:00 ngày giao dịch.",
    )
    parser.add_argument(
        "--backup-dir",
        default=None,
        help="Thư mục backup (dùng cho --morning-summary và test).",
    )
    return parser


def app_cfg_for_daily_check(raw_cfg: dict[str, Any], dsn: str) -> Config:
    """Dựng `Config` cho `daily_data_check.assess_date` từ YAML heartbeat đã đọc.

    CỐ Ý không gọi `trading.config.load_config`: hàm đó đòi đầy đủ SSI_* trong môi
    trường, mà chuông báo phải chạy được cả khi cấu hình SSI thiếu (cùng lý do đã ghi
    ở khối đọc config trong `main`). Các trường SSI để rỗng vì `assess_date` chỉ đọc
    `symbols`, `ssi_equity_accounts` và `holidays`.
    """
    return Config(
        symbols=list(raw_cfg.get("symbols") or []),
        indices=list(raw_cfg.get("indices") or []),
        bar_interval_minutes=int(raw_cfg.get("bar_interval_minutes") or 5),
        ssi_equity_accounts=list(raw_cfg.get("ssi_equity_accounts") or []),
        holidays={date.fromisoformat(str(h)) for h in (raw_cfg.get("holidays") or [])},
        db_dsn=dsn,
        nats_url="",
        nats_stream="",
        watchdog_stale_seconds=0,
        watchdog_max_failures=0,
        ssi_consumer_id="",
        ssi_consumer_secret="",
        ssi_api_key="",
        ssi_api_secret="",
        ssi_private_key="",
        real_trading_enabled=False,
        real_order_account=str(raw_cfg.get("real_order_account") or ""),
    )


def _is_confirmed_non_trading_day(p: date, logs_dir: Path) -> bool:
    """Kiểm tra xem ngày P đã được xác nhận là ngày không giao dịch trong log
    của scheduler (daily-data-check.log hoặc catchup.log) hay chưa (đợt 209b).
    """
    p_iso = p.isoformat()
    # 1. Kiểm tra daily-data-check.log
    ddc_log = logs_dir / "daily-data-check.log"
    if ddc_log.is_file():
        try:
            content = ddc_log.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                if NON_TRADING_DAY_MSG.format(target_date=p) in line or (
                    p_iso in line and NON_TRADING_DAY_PATTERN in line
                ):
                    return True
        except Exception:
            pass

    # 2. Kiểm tra catchup.log
    catchup_log = logs_dir / "catchup.log"
    if catchup_log.is_file():
        try:
            content = catchup_log.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                if NON_TRADING_DAYS_PREFIX in line and p_iso in line:
                    return True
        except Exception:
            pass

    return False


def prev_day_bars_alert(
    storage: Storage,
    app_cfg: Config,
    now: datetime,
    backfill_log: Path,
    alerted_for: str | None,
    logs_dir: Path | None = None,
) -> tuple[str | None, str]:
    """Tin cảnh báo độ đủ nến NGÀY của ngày giao dịch liền trước (đợt 160).

    Trả về (tin, ngày P dạng ISO). Tin là None khi không có gì để báo: hoặc đủ nến,
    hoặc đã báo cho đúng ngày P đó rồi.

    Kiểm KẾT QUẢ chứ không canh job: `backfill` và `daily-check` chỉ chạy buổi tối
    ngày giao dịch, tuổi phụ thuộc cuối tuần nên không canh tuổi được (xem KHONG_CANH).
    Nhưng hệ quả của việc chúng không chạy thì luôn giống nhau: sáng hôm sau
    `bars_daily` thiếu ngày. Kiểm đúng hệ quả đó bắt được mọi nguyên nhân (Docker tắt,
    máy ngủ, task bị từ chối, backfill lỗi mạng) mà không phải chép giờ chạy của job
    nào vào đây.

    TRÙNG TIN CÓ CHỦ Ý với daily-check: nếu tối hôm trước daily-check đã báo thiếu thì
    sáng hôm sau heartbeat báo LẠI. Chấp nhận, vì hai tin nói hai việc khác nhau:
    "thiếu lúc 21:00 (còn kịp vá trong đêm)" và "sáng ra rồi mà vẫn CHƯA ai vá".
    """
    p = previous_trading_day(now.date(), app_cfg.holidays)
    p_iso = p.isoformat()
    if alerted_for == p_iso:
        return None, p_iso

    code, _missing, msg = assess_date(storage, app_cfg, p, backfill_log)
    if code not in (1, 2):
        return None, p_iso

    if code == 2:
        effective_logs_dir = (
            Path(logs_dir) if logs_dir is not None else backfill_log.parent
        )
        if _is_confirmed_non_trading_day(p, effective_logs_dir):
            return None, p_iso

    level = "WARN" if code == 1 else "CRITICAL"
    tin = (
        f"[{level}] nến NGÀY của ngày giao dịch liền trước ({p_iso}) KHÔNG đầy đủ "
        f"— heartbeat kiểm lúc {now:%H:%M %d/%m}:\n{msg}\n"
        "Khắc phục: ./scripts/sched.sh backfill (idempotent — DEPLOYMENT.md §9.6), "
        "chạy TRƯỚC khi account_sync định giá vị thế bằng giá bars_daily cũ."
    )
    return tin, p_iso


def prev_day_foreign_flow_alert(
    storage: Storage,
    now: datetime,
    holidays: frozenset[date],
    alerted_for: str | None,
) -> tuple[str | None, str]:
    """Tin cảnh báo số dòng khối ngoại của ngày giao dịch liền trước (đợt 190b).

    Trả về (tin, ngày P dạng ISO). Tin là None khi không có gì để báo: hoặc đủ dòng,
    hoặc đã báo cho đúng ngày P đó rồi, hoặc không có ngày nào trước P (bảng rỗng).
    """
    p = previous_trading_day(now.date(), holidays)
    p_iso = p.isoformat()
    if alerted_for == p_iso or alerted_for == p:
        return None, p_iso

    counts = storage.read_foreign_flow_day_counts(p - timedelta(days=30), p)
    n_p = counts.get(p, 0)

    prior_days = sorted([d for d in counts if d < p], reverse=True)[:5]
    if not prior_days:
        return None, p_iso

    prior_counts = [counts[d] for d in prior_days]
    base = statistics.median(prior_counts)
    if isinstance(base, float) and base.is_integer():
        base_display = int(base)
    else:
        base_display = base

    if n_p < 0.8 * base:
        tin = (
            f"[WARN] khối ngoại ngày {p_iso}: {n_p} dòng (trung vị 5 phiên trước {base_display}) "
            "— Khắc phục: ./scripts/sched.sh foreign-flow (idempotent)"
        )
        return tin, p_iso

    return None, p_iso


def prev_day_5m_alert(
    storage: Storage,
    now: datetime,
    holidays: frozenset[date],
    alerted_for: str | None,
) -> tuple[str | None, str]:
    """Tin cảnh báo số mã thanh khoản có nến 5 phút của ngày giao dịch liền trước (đợt 198).

    Trả về (tin, ngày P dạng ISO). Tin là None khi không có gì để báo: hoặc đủ mã,
    hoặc đã báo cho đúng ngày P đó rồi, hoặc không có ngày nào trước P.
    """
    p = previous_trading_day(now.date(), holidays)
    p_iso = p.isoformat()
    if alerted_for == p_iso or alerted_for == p:
        return None, p_iso

    counts = storage.read_5m_active_symbol_day_counts(p - timedelta(days=30), p)
    n_p = counts.get(p, 0)

    prior_days = sorted([d for d in counts if d < p], reverse=True)[:5]
    if not prior_days:
        return None, p_iso

    prior_counts = [counts[d] for d in prior_days]
    base = statistics.median(prior_counts)
    if isinstance(base, float) and base.is_integer():
        base_display = int(base)
    else:
        base_display = base

    if n_p < 0.8 * base:
        tin = (
            f"[WARN] nến 5 phút ngày {p_iso}: {n_p} mã thanh khoản (trung vị 5 phiên trước {base_display}) "
            "— Khắc phục: ./scripts/sched.sh backfill-5m (idempotent)"
        )
        return tin, p_iso

    return None, p_iso


def build_morning_summary(
    now: datetime,
    logs_dir: Path | str,
    backup_dir: Path | str | None = None,
    holidays: frozenset[date] = frozenset(),
) -> str:
    """Xây dựng nội dung tin tóm tắt sáng lúc 08:00 ngày giao dịch (Task 5 - Brief 218).

    Bao gồm 4 mục:
      1. Tuổi lần chạy thật cuối cùng của từng job trong SCHEDULE_WATCH_JOBS (F1).
      2. Tuổi bản dump DB mới nhất (theo discovery của backup_check / default_backup_dir).
      3. Lần diễn tập phục hồi (restore-drill) OK cuối cùng (Task 2).
      4. Số file alert_outbox_* và tổng số tin chờ, kèm TÊN từng file outbox có tin chờ (Lead Adj 3).
    """
    now_tz = now.astimezone(TZ)
    logs_p = Path(logs_dir)
    lines = [f"[TÓM TẮT SÁNG] {now_tz:%Y-%m-%d %H:%M:%S}"]

    # 1. Tuổi các job trong SCHEDULE_WATCH_JOBS
    lines.append("1. Lịch chạy 24/7:")
    for branch, cfg in SCHEDULE_WATCH_JOBS.items():
        log_path = logs_p / cfg.log_file
        val = get_last_called_timestamp(
            str(log_path), cfg.label, skip_counts_as_run=cfg.skip_counts_as_run
        )
        last_dt = val[0]
        skip_count = getattr(val, "skip_count", 0)
        if last_dt is not None:
            age_sec = (now_tz - last_dt).total_seconds()
            if age_sec < 3600:
                age_str = f"{age_sec / 60:.0f}p trước"
            else:
                age_str = f"{age_sec / 3600:.1f}h trước"
            skip_str = f" ({skip_count} SKIP)" if not cfg.skip_counts_as_run else ""
            lines.append(f"  - {branch}: {age_str}{skip_str}")
        else:
            skip_str = f" ({skip_count} SKIP)" if skip_count > 0 else ""
            lines.append(f"  - {branch}: chưa có mốc chạy{skip_str}")

    # 2. Tuổi bản dump DB mới nhất
    b_dir = Path(backup_dir) if backup_dir else Path(default_backup_dir())
    dump_str = "không tìm thấy bản dump"
    if b_dir.exists() and b_dir.is_dir():
        dumps = [
            f
            for f in b_dir.iterdir()
            if f.is_file()
            and f.name.startswith("trading_")
            and (f.name.endswith(".dump") or f.name.endswith(".sql.gz"))
        ]
        if dumps:
            latest_dump = max(dumps, key=lambda f: f.stat().st_mtime)
            mtime = datetime.fromtimestamp(latest_dump.stat().st_mtime, TZ)
            age_hours = (now_tz - mtime).total_seconds() / 3600
            dump_str = f"{latest_dump.name} ({age_hours:.1f}h trước)"
    lines.append(f"2. Dump DB mới nhất: {dump_str}")

    # 3. Lần diễn tập phục hồi OK cuối cùng
    restore_log = logs_p / "restore-drill.log"
    restore_dt, _ = get_last_successful_restore_timestamp(str(restore_log))
    if restore_dt is not None:
        age_days = (now_tz - restore_dt).total_seconds() / 86400
        restore_str = f"OK lúc {restore_dt:%Y-%m-%d %H:%M} ({age_days:.1f} ngày trước)"
    else:
        restore_str = "chưa từng diễn tập OK"
    lines.append(f"3. Diễn tập phục hồi: {restore_str}")

    # 4. Outbox và tin đang chờ (Lead Adjustment 3: liệt kê tên từng file có tin chờ)
    outbox_files = sorted(logs_p.glob("alert_outbox_*.jsonl"))
    total_outbox = len(outbox_files)
    pending_files = {}
    total_pending = 0
    for of in outbox_files:
        try:
            cnt = AlertOutbox(of).pending()
            if cnt > 0:
                pending_files[of.name] = cnt
                total_pending += cnt
        except Exception:
            pass

    if pending_files:
        details = ", ".join(f"{k}: {v}" for k, v in pending_files.items())
        outbox_str = f"{total_pending} tin chờ trong {len(pending_files)}/{total_outbox} file ({details})"
    else:
        outbox_str = f"0 tin chờ (0/{total_outbox} file)"
    lines.append(f"4. Hàng đợi cảnh báo: {outbox_str}")

    return "\n".join(lines)


def _collect_and_evaluate_schedule(
    logs_dir: str, sched_state_file: str, now: datetime
) -> tuple[list[str], dict[str, dict[str, Any]], list[str]]:
    """Thu thập log của các job theo lịch và đánh giá trạng thái qua `evaluate_schedule_health`."""
    job_last_seen: dict[str, tuple[datetime | None, str | None]] = {}
    for branch, job_cfg in SCHEDULE_WATCH_JOBS.items():
        log_path = os.path.join(logs_dir, job_cfg.log_file)
        job_last_seen[branch] = get_last_called_timestamp(
            log_path, job_cfg.label, skip_counts_as_run=job_cfg.skip_counts_as_run
        )

    job_exit_codes: dict[str, tuple[datetime | None, int | None, str | None]] = {}
    job_runs: dict[str, list[tuple[datetime, int | None]]] = {}
    for branch, policy in SCHEDULE_EXIT_POLICIES.items():
        log_path = os.path.join(logs_dir, policy.log_file)
        runs, err = get_job_runs(log_path, policy.label)
        job_runs[branch] = runs
        if runs:
            last_dt, last_code = runs[-1]
            job_exit_codes[branch] = (last_dt, last_code, err)
        else:
            job_exit_codes[branch] = (None, None, err)

    restore_drill_log = os.path.join(logs_dir, "restore-drill.log")
    restore_drill_last_ok = get_last_successful_restore_timestamp(restore_drill_log)

    prev_sched_state = load_schedule_state(sched_state_file)
    return evaluate_schedule_health(
        job_last_seen,
        now,
        prev_sched_state,
        watch_jobs=SCHEDULE_WATCH_JOBS,
        job_exit_codes=job_exit_codes,
        exit_policies=SCHEDULE_EXIT_POLICIES,
        restore_drill_last_ok=restore_drill_last_ok,
        job_runs=job_runs,
    )


def _run_morning_summary_mode(args: Any, logs_dir: str, now: datetime) -> int:
    """Thực thi chế độ `--morning-summary` lúc 08:00 ngày giao dịch."""
    now_tz = now.astimezone(TZ)
    holidays = frozenset()
    try:
        cfg_path = os.path.join(
            os.path.dirname(__file__), "..", "config", "config.yaml"
        )
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        holidays = frozenset(
            date.fromisoformat(str(h)) for h in (cfg.get("holidays") or [])
        )
    except Exception:
        pass

    if not is_trading_day(now_tz.date(), holidays):
        _print_safe(
            f"[morning-summary] {now_tz.date()} không phải ngày giao dịch -> bỏ qua"
        )
        return 0

    summary_text = build_morning_summary(
        now=now,
        logs_dir=logs_dir,
        backup_dir=args.backup_dir,
        holidays=holidays,
    )
    _print_safe(summary_text)

    if args.dry_run:
        _print_safe("[DRY-RUN] Không gửi Telegram thật.")
        return 0

    outbox_file = Path(logs_dir) / outbox_name("morning-summary")
    ok = send_with_outbox(
        summary_text, send=send_telegram, outbox_path=outbox_file
    )
    if ok:
        return 0
    _print_safe(
        "[morning-summary] GUI TELEGRAM HONG: tin đã được xếp vào outbox"
    )
    return 1


def _run_schedule_watch_only_mode(
    args: Any, logs_dir: str, outbox_path: Path, sched_state_file: str, now: datetime
) -> int:
    """Thực thi chế độ `--schedule-watch-only` (chỉ canh tuổi và mã thoát 24/7)."""
    sched_alerts, new_sched_state, sched_info_logs = _collect_and_evaluate_schedule(
        logs_dir, sched_state_file, now
    )

    if args.dry_run:
        for info in sched_info_logs:
            _print_safe(info)

    if sched_alerts:
        _print_safe("\n".join(sched_alerts))
        if args.dry_run:
            _print_safe(
                "[DRY-RUN] Không gửi Telegram thật. Không cập nhật file trạng thái."
            )
            return 1
        ok = send_with_outbox(
            "\n".join(sched_alerts), send=send_telegram, outbox_path=outbox_path
        )
        if ok:
            save_schedule_state(sched_state_file, new_sched_state)
        else:
            _print_safe(
                "[schedule-watch] GUI TELEGRAM HONG: cảnh báo chưa tới được Telegram"
            )
        return 1

    if not args.dry_run:
        save_schedule_state(sched_state_file, new_sched_state)
    return 0


def _check_prev_day_completions(
    dsn: str,
    cfg: dict[str, Any],
    holidays: frozenset[date],
    now: datetime,
    logs_dir: str,
    dry_run: bool,
    messages: list[str],
) -> None:
    """Kiểm tra độ đủ dữ liệu ngày giao dịch liền trước (bars 1d, khối ngoại, nến 5m)."""
    # Đợt 160: kiểm KẾT QUẢ của chuỗi `backfill` -> `daily-check` (đêm hôm trước) bằng
    # đúng một câu hỏi: nến NGÀY của ngày giao dịch liền trước có đủ chưa. Chỉ trong
    # giờ giao dịch, và mỗi ngày P chỉ báo MỘT lần (nếu không thì 5 phút một tin).
    try:
        prev_state_file = Path(logs_dir) / PREV_DAY_BARS_STATE_NAME
        prev_state = load_json_state(prev_state_file, "prev-day-bars")
        tin, p_iso = prev_day_bars_alert(
            Storage(dsn),
            app_cfg_for_daily_check(cfg, dsn),
            now,
            Path(logs_dir) / "backfill.log",
            prev_state.get("alerted_for"),
            logs_dir=Path(logs_dir),
        )
        if tin:
            messages.append(tin)
            # Ghi trạng thái NGAY, không chờ gửi xong: send_with_outbox đã xếp tin
            # vào hàng đợi khi gửi hỏng nên tin không mất, còn nếu không ghi thì mỗi
            # 5 phút lại báo lại cùng một ngày cho tới hết phiên.
            if not dry_run:
                save_json_state(prev_state_file, {"alerted_for": p_iso})
    except Exception as e:
        # Brief 147 (đã ghim cho engine-consumer) + brief 160 §Việc 2.5: phép kiểm
        # mới KHÔNG được làm chết các phép kiểm khác. Hỏng thì in ra rồi đi tiếp —
        # đây là job canh mọi thứ khác, im lặng mới là sai.
        #
        # In ra STDERR, không phải stdout: test cũ
        # `test_main_prints_message_to_stdout_before_sending` ghim hợp đồng "stdout
        # phải bằng đúng nội dung gửi Telegram". Không dấu tiếng Việt và bọc try:
        # stderr không được reconfigure utf-8 như stdout, in dấu ở đây có thể ném
        # UnicodeEncodeError — bên trong except thì chuông báo chết theo.
        try:
            print(
                "[WARN] heartbeat khong kiem duoc nen ngay cua ngay lien truoc: "
                f"{type(e).__name__}: {e}"[:300],
                file=sys.stderr,
            )
        except Exception:
            pass

    # Đợt 190b: kiểm số dòng khối ngoại của ngày giao dịch liền trước
    try:
        prev_flow_state_file = Path(logs_dir) / PREV_DAY_FOREIGN_FLOW_STATE_NAME
        prev_flow_state = load_json_state(
            prev_flow_state_file, "prev-day-foreign-flow"
        )
        tin, p_iso = prev_day_foreign_flow_alert(
            Storage(dsn),
            now,
            holidays,
            prev_flow_state.get("alerted_for"),
        )
        if tin:
            messages.append(tin)
            if not dry_run:
                save_json_state(prev_flow_state_file, {"alerted_for": p_iso})
    except Exception as e:
        try:
            print(
                "[WARN] heartbeat khong kiem duoc khoi ngoai: "
                f"{type(e).__name__}: {e}"[:300],
                file=sys.stderr,
            )
        except Exception:
            pass

    # Đợt 198: kiểm số mã thanh khoản có nến 5 phút của ngày giao dịch liền trước
    try:
        prev_5m_state_file = Path(logs_dir) / PREV_DAY_5M_STATE_NAME
        prev_5m_state = load_json_state(prev_5m_state_file, "prev-day-5m")
        tin, p_iso = prev_day_5m_alert(
            Storage(dsn),
            now,
            holidays,
            prev_5m_state.get("alerted_for"),
        )
        if tin:
            messages.append(tin)
            if not dry_run:
                save_json_state(prev_5m_state_file, {"alerted_for": p_iso})
    except Exception as e:
        try:
            print(
                "[WARN] heartbeat khong kiem duoc nen 5 phut: "
                f"{type(e).__name__}: {e}"[:300],
                file=sys.stderr,
            )
        except Exception:
            pass


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
    logs_dir = args.logs_dir
    outbox_path = Path(logs_dir) / HEARTBEAT_OUTBOX_NAME
    sched_state_file = args.state_file or os.path.join(logs_dir, SCHEDULE_STATE_NAME)

    if args.morning_summary:
        return _run_morning_summary_mode(args, logs_dir, datetime.now(TZ))

    if args.schedule_watch_only:
        return _run_schedule_watch_only_mode(
            args, logs_dir, outbox_path, sched_state_file, datetime.now(TZ)
        )

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
            ok = send_with_outbox(
                err_msg, send=send_telegram, outbox_path=outbox_path
            )
            if not ok:
                _print_safe(
                    "[heartbeat-check] GUI TELEGRAM HONG: cảnh báo chưa tới được Telegram"
                )
        return 1

    # Việc 2 (Brief 142 + Brief 156): Canh các job theo lịch (đọc log của run_if_docker_up.sh)
    sched_alerts, new_sched_state, sched_info_logs = _collect_and_evaluate_schedule(
        logs_dir, sched_state_file, now
    )

    # Chỉ cảnh báo trong giờ giao dịch (trừ khi chạy --dry-run để chẩn đoán/test)
    now_tz = now.astimezone(TZ)
    pre_market = time(8, 0) <= now_tz.time() < time(9, 0) and is_trading_day(
        now_tz.date(), holidays
    )
    # Đợt 160: "đang trong giờ giao dịch" được dùng LẠI cho phép kiểm nến ngày. Ngoài
    # cửa sổ thì không kiểm — kể cả khi --dry-run (dry-run bỏ qua `return 0` dưới đây
    # để chẩn đoán được, nhưng không được kéo theo một phép kiểm chỉ có nghĩa trong phiên).
    in_check_window = is_trading_time(now, holidays) or pre_market
    if not in_check_window and not args.dry_run:
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
            if symbols:
                placeholders = ",".join(["%s"] * len(symbols))
                max_ts_row = c.execute(
                    f"SELECT max(ts) FROM bars WHERE symbol IN ({placeholders})",
                    list(symbols),
                ).fetchone()
            else:
                max_ts_row = None
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
    if not symbols:
        _print_safe("symbols rỗng: bỏ qua kiểm nến stream")
    elif bar_stale(max_ts, now, holidays=holidays):
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
        exp_dt = datetime.fromtimestamp(expiry, TZ) if expiry else None
        exp_str = exp_dt.strftime("%H:%M %d/%m") if exp_dt else "?"
        if expiry is not None and now.timestamp() >= expiry:
            _print_safe(
                f"[INFO] token SSI đã hết hạn lúc {exp_str} — đang chờ collector tự xác thực lại (ân hạn 10 phút)"
            )
        else:
            _print_safe(
                f"[INFO] token SSI hết hạn lúc {exp_str} — collector sẽ tự xác thực lại"
            )
    elif status == "CRITICAL":
        messages.append(
            "[CRITICAL] token SSI đã hết hạn hoặc không có trong DB (collector không tự xác thực lại được) — "
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

    if in_check_window:
        _check_prev_day_completions(
            dsn, cfg, holidays, now, logs_dir, args.dry_run, messages
        )

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
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception:
        traceback.print_exc()
        sys.exit(3)
