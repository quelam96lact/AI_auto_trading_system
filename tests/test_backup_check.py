"""Unit tests cho scripts/backup_check.py (Brief 131)."""

from __future__ import annotations

import time
from unittest.mock import patch

from scripts.backup_check import (
    DEFAULT_MAX_AGE_HOURS,
    BackupFileInfo,
    evaluate_backup_health,
    main,
)


def test_evaluate_dir_not_exists():
    """Thư mục sao lưu không tồn tại phải báo [CRITICAL]."""
    alerts = evaluate_backup_health(
        dir_exists=False,
        latest_file=None,
        pg_restore_status="",
        now_epoch=time.time(),
        backup_dir="/non/existent/path",
    )
    assert len(alerts) == 1
    assert "[CRITICAL] Thư mục sao lưu không tồn tại" in alerts[0]
    assert "/non/existent/path" in alerts[0]


def test_evaluate_no_files():
    """Thư mục rỗng không có file sao lưu phải báo [CRITICAL]."""
    alerts = evaluate_backup_health(
        dir_exists=True,
        latest_file=None,
        pg_restore_status="",
        now_epoch=time.time(),
        backup_dir="/var/backups/empty",
    )
    assert len(alerts) == 1
    assert "[CRITICAL] Không tìm thấy bản sao lưu nào" in alerts[0]


def test_evaluate_file_too_old():
    """File sao lưu mới nhất vượt quá ngưỡng tuổi tối đa phải báo [CRITICAL]."""
    now = 1_700_000_000.0
    # 30 hours old (> 26h)
    mtime = now - 30 * 3600
    file_info = BackupFileInfo(
        name="trading_old.dump",
        path="/backups/trading_old.dump",
        size_bytes=100 * 1024 * 1024,
        mtime=mtime,
    )
    alerts = evaluate_backup_health(
        dir_exists=True,
        latest_file=file_info,
        pg_restore_status="OK",
        now_epoch=now,
        max_age_hours=26.0,
        min_size_mb=80.0,
    )
    assert any(
        "[CRITICAL] Bản sao lưu mới nhất (trading_old.dump) đã cũ" in a for a in alerts
    )


def test_evaluate_file_too_small():
    """File sao lưu mới nhất nhỏ hơn ngưỡng tối thiểu phải báo [CRITICAL]."""
    now = 1_700_000_000.0
    mtime = now - 2 * 3600  # 2h old (fresh)
    file_info = BackupFileInfo(
        name="trading_tiny.dump",
        path="/backups/trading_tiny.dump",
        size_bytes=10 * 1024 * 1024,  # 10 MB (< 80 MB)
        mtime=mtime,
    )
    alerts = evaluate_backup_health(
        dir_exists=True,
        latest_file=file_info,
        pg_restore_status="OK",
        now_epoch=now,
        max_age_hours=26.0,
        min_size_mb=80.0,
    )
    assert any(
        "[CRITICAL] Bản sao lưu mới nhất (trading_tiny.dump) quá nhỏ" in a
        for a in alerts
    )


def test_evaluate_pg_restore_fail():
    """File sao lưu bị hỏng (pg_restore -l thất bại) phải báo [CRITICAL]."""
    now = 1_700_000_000.0
    mtime = now - 2 * 3600
    file_info = BackupFileInfo(
        name="trading_corrupt.dump",
        path="/backups/trading_corrupt.dump",
        size_bytes=100 * 1024 * 1024,
        mtime=mtime,
    )
    alerts = evaluate_backup_health(
        dir_exists=True,
        latest_file=file_info,
        pg_restore_status="FAIL: end of file reached prematurely",
        now_epoch=now,
        max_age_hours=26.0,
        min_size_mb=80.0,
    )
    assert any("[CRITICAL] Bản sao lưu trading_corrupt.dump hỏng" in a for a in alerts)


def test_evaluate_pg_restore_unavailable():
    """pg_restore không có trên PATH phải nói rõ không kiểm được, không coi là đạt."""
    now = 1_700_000_000.0
    mtime = now - 2 * 3600
    file_info = BackupFileInfo(
        name="trading_ok.dump",
        path="/backups/trading_ok.dump",
        size_bytes=100 * 1024 * 1024,
        mtime=mtime,
    )
    alerts = evaluate_backup_health(
        dir_exists=True,
        latest_file=file_info,
        pg_restore_status="UNAVAILABLE: pg_restore không có trên PATH",
        now_epoch=now,
        max_age_hours=26.0,
        min_size_mb=80.0,
    )
    assert any("Không kiểm được tính toàn vẹn" in a for a in alerts)


def test_evaluate_all_ok():
    """File tươi, kích thước chuẩn, pg_restore đạt -> không có cảnh báo nào."""
    now = 1_700_000_000.0
    mtime = now - 2 * 3600
    file_info = BackupFileInfo(
        name="trading_good.dump",
        path="/backups/trading_good.dump",
        size_bytes=100 * 1024 * 1024,
        mtime=mtime,
    )
    alerts = evaluate_backup_health(
        dir_exists=True,
        latest_file=file_info,
        pg_restore_status="OK",
        now_epoch=now,
        max_age_hours=26.0,
        min_size_mb=80.0,
    )
    assert alerts == []


def test_main_dry_run_silent_on_valid_dir(tmp_path):
    """--dry-run trên thư mục có file đạt yêu cầu phải im và thoát mã 0."""
    dump_file = tmp_path / "trading_20260929_020000.dump"
    # Ghi giả định file 90 MB
    dump_file.write_bytes(b"PGDMP" + b"\x00" * (90 * 1024 * 1024))

    with patch("scripts.backup_check.check_pg_restore", return_value="OK"):
        code = main(
            ["--dry-run", "--backup-dir", str(tmp_path), "--min-size-mb", "80.0"]
        )
        assert code == 0


def test_main_dry_run_alerts_on_empty_dir(tmp_path):
    """--dry-run trên thư mục rỗng phải kêu (thoát mã 1) mà không gửi Telegram thật."""
    with patch("scripts.backup_check.send_telegram") as mock_send:
        code = main(["--dry-run", "--backup-dir", str(tmp_path)])
        assert code == 1
        mock_send.assert_not_called()


def test_main_send_telegram_success(tmp_path):
    """Có cảnh báo và gửi Telegram thành công -> thoát mã 1."""
    with patch("scripts.backup_check.send_telegram", return_value=True) as mock_send:
        code = main(["--backup-dir", str(tmp_path)])
        assert code == 1
        assert mock_send.called


def test_main_send_telegram_failure_returns_2(tmp_path):
    """Có cảnh báo nhưng gửi Telegram thất bại -> thoát mã 2 (nguyên tắc đợt 126)."""
    with patch("scripts.backup_check.send_telegram", return_value=False) as mock_send:
        code = main(["--backup-dir", str(tmp_path)])
        assert code == 2
        assert mock_send.called


def test_mot_dem_backup_hong_PHAI_bi_bat_voi_nguong_MAC_DINH():
    """Một đêm backup hỏng phải bị bắt NGAY, không đợi thêm 24 giờ.

    Lịch: backup 02:00, check 03:00. Hỏng một đêm => bản mới nhất 25 giờ tuổi.
    Ngưỡng 26h ban đầu (lỗi brief đợt 131 của Claude) LỚN HƠN 25h nên cổng im
    lặng — đo thật 29/09: file 25 giờ tuổi cho EXIT=0. Test này ghim ngưỡng
    MẶC ĐỊNH, không truyền max_age_hours, nên nếu ai nâng lại quá 25h thì đỏ.
    """
    now = 1_700_000_000.0
    file_info = BackupFileInfo(
        name="trading_hom_qua.dump",
        path="/backups/trading_hom_qua.dump",
        size_bytes=100 * 1024 * 1024,
        mtime=now - 25 * 3600,
    )
    alerts = evaluate_backup_health(
        dir_exists=True,
        latest_file=file_info,
        pg_restore_status="OK",
        now_epoch=now,
        min_size_mb=80.0,
    )
    assert any(
        "đã cũ" in a for a in alerts
    ), f"Ngưỡng mặc định {DEFAULT_MAX_AGE_HOURS}h không bắt được bản 25 giờ tuổi: {alerts}"


def test_backup_vua_chay_xong_KHONG_bao_oan():
    """Backup 02:00 thành công, check 03:00: bản 1 giờ tuổi phải IM."""
    now = 1_700_000_000.0
    file_info = BackupFileInfo(
        name="trading_moi.dump",
        path="/backups/trading_moi.dump",
        size_bytes=100 * 1024 * 1024,
        mtime=now - 1 * 3600,
    )
    alerts = evaluate_backup_health(
        dir_exists=True,
        latest_file=file_info,
        pg_restore_status="OK",
        now_epoch=now,
        min_size_mb=80.0,
    )
    assert alerts == [], alerts
