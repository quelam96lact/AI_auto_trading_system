"""Tests cho Task 5 (F8a) — Tin tóm tắt buổi sáng 08:00 ngày giao dịch.

Bao gồm:
- Hàm build_morning_summary tạo đủ 4 mục (lịch chạy, dump DB, restore-drill, outbox).
- Thứ Hai (ngày giao dịch): gửi đúng 1 tin, thoát 0.
- Thứ Bảy (ngày nghỉ): không gửi gì, thoát 0.
- Gửi lỗi: tin nằm trong outbox ở tmp_path, thoát 1 (Lead Điều chỉnh 4).
- Kiểm tra nhánh morning-summary trong sched.sh.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import scripts.heartbeat_check as hc
from trading.alerts import AlertOutbox
from trading.calendar_vn import TZ


def test_build_morning_summary_contains_four_items(tmp_path: Path):
    """build_morning_summary tạo đúng 4 mục theo yêu cầu brief đợt 218 và Lead Điều chỉnh 3."""
    now = datetime(2026, 11, 9, 8, 0, 0, tzinfo=TZ)  # Thứ Hai

    # 1. Tạo log cho các job theo lịch
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # container-health: 10 phút trước
    ts_ch = (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    (logs_dir / "container-health.log").write_text(
        f"{ts_ch} container-health start\nEXIT=0\n", encoding="utf-8"
    )

    # backup: 6 giờ trước, kèm 1 SKIP
    ts_bk = (now - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
    (logs_dir / "backup.log").write_text(
        f"{ts_bk} backup start\nEXIT=0\n"
        f"{(now - timedelta(hours=2)):%Y-%m-%d %H:%M:%S} backup SKIP: docker chua chay\n",
        encoding="utf-8",
    )

    # 2. Tạo file dump DB
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dump_file = backup_dir / "trading_20261109_020000.dump"
    dump_file.write_bytes(b"dummy dump")
    # Đặt mtime cách đây 6 giờ
    mtime_bk = (now - timedelta(hours=6)).timestamp()
    os.utime(dump_file, (mtime_bk, mtime_bk))

    # 3. Tạo restore-drill log có Diễn tập OK
    ts_drill = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    (logs_dir / "restore-drill.log").write_text(
        f"{ts_drill} restore-drill start\n"
        "Diễn tập OK: trading_20261108.dump, 36 bảng >= bản kê lúc dump\n"
        "EXIT=0\n",
        encoding="utf-8",
    )

    # 4. Tạo outbox có tin đang chờ
    outbox_file = logs_dir / "alert_outbox_engine-cam.jsonl"
    outbox = AlertOutbox(outbox_file, send_fn=lambda _: False)
    outbox.send_or_queue("Cảnh báo 1")
    outbox.send_or_queue("Cảnh báo 2")
    assert outbox.pending() == 2

    # Gọi build_morning_summary
    text = hc.build_morning_summary(
        now=now,
        logs_dir=logs_dir,
        backup_dir=backup_dir,
    )

    lines = text.strip().splitlines()
    assert lines[0].startswith("[TÓM TẮT SÁNG]")
    # Mục 1: Lịch chạy
    assert any("1. Lịch chạy 24/7:" in line for line in lines)
    assert any("container-health" in line for line in lines)
    assert any("backup" in line and "SKIP" in line for line in lines)
    # Mục 2: Dump DB mới nhất
    assert any("2. Dump DB mới nhất:" in line and "trading_20261109_020000.dump" in line for line in lines)
    # Mục 3: Lần diễn tập OK cuối cùng
    assert any("3. Diễn tập phục hồi:" in line and "OK lúc" in line for line in lines)
    # Mục 4: Outbox và tên từng file có tin chờ (Lead Điều chỉnh 3)
    assert any("4. Hàng đợi cảnh báo:" in line for line in lines)
    assert any("alert_outbox_engine-cam.jsonl: 2" in line for line in lines)


def test_morning_summary_monday_sends_and_exits_0(tmp_path: Path, monkeypatch):
    """Thứ Hai: gửi đúng 1 tin, có đủ 4 mục, thoát 0."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    mon_8am = datetime(2026, 11, 9, 8, 0, 0, tzinfo=TZ)

    class FakeDatetime:
        @staticmethod
        def now(tz):
            return mon_8am

        strptime = staticmethod(datetime.strptime)
        fromtimestamp = staticmethod(datetime.fromtimestamp)

    monkeypatch.setattr(hc, "datetime", FakeDatetime)

    sent = []

    def mock_send(msg: str) -> bool:
        sent.append(msg)
        return True

    monkeypatch.setattr(hc, "send_telegram", mock_send)

    rc = hc.main([
        "--morning-summary",
        "--logs-dir", str(logs_dir),
        "--backup-dir", str(backup_dir),
    ])

    assert rc == 0
    assert len(sent) == 1
    msg = sent[0]
    assert "[TÓM TẮT SÁNG]" in msg
    assert "1. Lịch chạy 24/7:" in msg
    assert "2. Dump DB mới nhất:" in msg
    assert "3. Diễn tập phục hồi:" in msg
    assert "4. Hàng đợi cảnh báo:" in msg


def test_morning_summary_saturday_exits_0_no_send(tmp_path: Path, monkeypatch):
    """Thứ Bảy: ngày nghỉ -> thoát 0 và không gửi gì."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    sat_8am = datetime(2026, 11, 7, 8, 0, 0, tzinfo=TZ)

    class FakeDatetime:
        @staticmethod
        def now(tz):
            return sat_8am

        strptime = staticmethod(datetime.strptime)

    monkeypatch.setattr(hc, "datetime", FakeDatetime)

    sent = []
    monkeypatch.setattr(hc, "send_telegram", lambda msg: sent.append(msg) or True)

    rc = hc.main([
        "--morning-summary",
        "--logs-dir", str(logs_dir),
    ])

    assert rc == 0
    assert len(sent) == 0, "Thứ Bảy không được gửi tóm tắt sáng"


def test_morning_summary_send_failure_queues_and_exits_1(tmp_path: Path, monkeypatch):
    """Gửi lỗi: tin nằm trong outbox ở tmp_path, thoát 1 (Lead Điều chỉnh 4)."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    mon_8am = datetime(2026, 11, 9, 8, 0, 0, tzinfo=TZ)

    class FakeDatetime:
        @staticmethod
        def now(tz):
            return mon_8am

        strptime = staticmethod(datetime.strptime)
        fromtimestamp = staticmethod(datetime.fromtimestamp)

    monkeypatch.setattr(hc, "datetime", FakeDatetime)

    def fail_send(msg: str) -> bool:
        raise RuntimeError("Telegram down")

    monkeypatch.setattr(hc, "send_telegram", fail_send)

    rc = hc.main([
        "--morning-summary",
        "--logs-dir", str(logs_dir),
    ])

    # Lead Điều chỉnh 4: Thoát 1 khi gửi hỏng để schedule-watch bắt
    assert rc == 1
    outbox_file = logs_dir / hc.outbox_name("morning-summary")
    assert outbox_file.exists()
    outbox = AlertOutbox(outbox_file)
    assert outbox.pending() == 1


def test_morning_summary_exit_policy_normal_exit_codes_is_zero():
    """Policy morning-summary trong SCHEDULE_EXIT_POLICIES có normal_exit_codes = {0}."""
    policy = hc.SCHEDULE_EXIT_POLICIES.get("morning-summary")
    assert policy is not None
    assert policy.normal_exit_codes == frozenset({0}), "normal_exit_codes phải là {0} để mã 1 báo CRITICAL"
