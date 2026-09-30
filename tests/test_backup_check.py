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
            [
                "--dry-run",
                "--backup-dir",
                str(tmp_path),
                "--min-size-mb",
                "80.0",
                "--no-orderbook",
                "--no-counts",
            ]
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


def test_default_backup_dir_doc_tu_TRADING_BACKUP_DIR(monkeypatch):
    """Mặc định thư mục sao lưu phải đọc TRADING_BACKUP_DIR (.env) trước đường dẫn Ubuntu.

    Đo thật 29/09: khi chưa có cơ chế này, gọi job đúng như lịch sẽ gọi (không tham
    số) thì trên Windows `scripts.backup_check` nhận `/var/backups/trading-db` — vừa không tồn tại,
    vừa bị Git Bash dịch thành `C:\\Program Files\\Git\\var\\...`. Hậu quả đã đo:
    backup-check gửi CẢNH BÁO GIẢ mỗi ngày, disk-check thoát 2 và không kiểm đĩa,
    orderbook-backup chết ở `mkdir /var`. `run_if_docker_up.sh` nạp .env TRƯỚC khi
    chạy job, nên biến này tới được job.
    """
    import importlib

    import scripts.backup_check as m

    monkeypatch.setenv("TRADING_BACKUP_DIR", "/tmp/bk-cua-toi")
    importlib.reload(m)
    assert m.DEFAULT_BACKUP_DIR == "/tmp/bk-cua-toi"

    monkeypatch.delenv("TRADING_BACKUP_DIR", raising=False)
    importlib.reload(m)
    assert m.DEFAULT_BACKUP_DIR == "/var/backups/trading-db"


# ---------------------------------------------------------------------------
# Dot 135: ban sao luu SO LENH (orderbook_*.tar.gz) — tuoi theo LICH GIAO DICH.
# ---------------------------------------------------------------------------
import tarfile
from datetime import date, datetime

from scripts.backup_check import (
    check_orderbook_tar,
    evaluate_orderbook_backup,
)
from trading.calendar_vn import TZ, previous_trading_day

HOLS = frozenset({date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2)})


def _ts(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=TZ).timestamp()


def _ob(mtime):
    return BackupFileInfo(
        name="orderbook_x.tar.gz",
        path="/b/orderbook_x.tar.gz",
        size_bytes=1,
        mtime=mtime,
    )


def _eval(now, latest, integrity="OK", holidays=HOLS):
    return evaluate_orderbook_backup(
        latest_file=latest,
        integrity_status=integrity,
        now=now,
        holidays=holidays,
        backup_dir="/b",
    )


def test_previous_trading_day_khong_gom_chinh_ngay_d():
    """Chung minh ham tra ngay TRUOC d: thu Hai 28/09 -> thu Sau 25/09, khong phai 28/09."""
    assert previous_trading_day(date(2026, 9, 28), HOLS) == date(2026, 9, 25)
    assert previous_trading_day(date(2026, 9, 29), HOLS) == date(2026, 9, 28)
    # sau ky nghi 31/08-02/09: 03/09 -> thu Sau 28/08
    assert previous_trading_day(date(2026, 9, 3), HOLS) == date(2026, 8, 28)


def test_lich_thu_ba_03h_ban_thu_ba_0230_IM():
    now = datetime(2026, 9, 29, 3, 0, tzinfo=TZ)
    assert _eval(now, _ob(_ts(2026, 9, 29, 2, 30))) == []


def test_lich_chu_nhat_03h_ban_thu_bay_0230_IM():
    now = datetime(2026, 9, 27, 3, 0, tzinfo=TZ)
    assert _eval(now, _ob(_ts(2026, 9, 26, 2, 30))) == []


def test_lich_thu_hai_03h_ban_thu_bay_0230_IM():
    """Dong QUAN TRONG NHAT: ban 48,5 gio tuoi van la dung, khong duoc bao oan."""
    now = datetime(2026, 9, 28, 3, 0, tzinfo=TZ)
    assert _eval(now, _ob(_ts(2026, 9, 26, 2, 30))) == []


def test_lich_sau_ky_nghi_dai_IM():
    now = datetime(2026, 9, 3, 3, 0, tzinfo=TZ)
    assert _eval(now, _ob(_ts(2026, 8, 29, 2, 30))) == []


def test_job_thu_bay_hong_PHAI_bao_va_neu_ngay_D():
    """Thu Hai 03:00, job thu Bay hong -> ban moi nhat la thu Sau 02:30 (truoc 14:46) -> bao."""
    now = datetime(2026, 9, 28, 3, 0, tzinfo=TZ)
    alerts = _eval(now, _ob(_ts(2026, 9, 25, 2, 30)))
    assert len(alerts) == 1
    assert "2026-09-25" in alerts[0]
    assert "[CRITICAL]" in alerts[0]


def test_khong_co_ban_so_lenh_nao_PHAI_bao():
    alerts = _eval(datetime(2026, 9, 29, 3, 0, tzinfo=TZ), None)
    assert len(alerts) == 1
    assert "sổ lệnh" in alerts[0]


def test_ban_so_lenh_hong_toan_ven_PHAI_bao():
    now = datetime(2026, 9, 29, 3, 0, tzinfo=TZ)
    alerts = _eval(now, _ob(_ts(2026, 9, 29, 2, 30)), integrity="FAIL: 0 file")
    assert len(alerts) == 1
    assert "0 file" in alerts[0]


def test_ban_so_lenh_nho_KHONG_bi_bao_vi_kich_thuoc():
    """Khong co nguong kich thuoc (orderbook-daily-check lo chat luong du lieu)."""
    now = datetime(2026, 9, 29, 3, 0, tzinfo=TZ)
    small = BackupFileInfo("orderbook_x.tar.gz", "/b/x", 10, _ts(2026, 9, 29, 2, 30))
    assert _eval(now, small) == []


def test_check_orderbook_tar_doc_duoc_va_dem_file(tmp_path):
    src = tmp_path / "a.jsonl.gz"
    src.write_bytes(b"x")
    good = tmp_path / "orderbook_good.tar.gz"
    with tarfile.open(good, "w:gz") as t:
        t.add(src, arcname="data/orderbook/A/a.jsonl.gz")
    assert check_orderbook_tar(good) == "OK"

    empty = tmp_path / "orderbook_empty.tar.gz"
    with tarfile.open(empty, "w:gz"):
        pass
    assert check_orderbook_tar(empty).startswith("FAIL")

    bad = tmp_path / "orderbook_bad.tar.gz"
    bad.write_bytes(b"khong phai tar")
    assert check_orderbook_tar(bad).startswith("FAIL")


def _dump(tmp_path):
    f = tmp_path / "trading_20260929_020000.dump"
    f.write_bytes(b"PGDMP" + b"\x00" * (90 * 1024 * 1024))


def test_main_thu_muc_chi_co_dump_PHAI_bao_thieu_so_lenh(tmp_path, capsys):
    _dump(tmp_path)
    with patch("scripts.backup_check.check_pg_restore", return_value="OK"):
        code = main(["--dry-run", "--backup-dir", str(tmp_path)])
    assert code == 1
    assert "sổ lệnh" in capsys.readouterr().out


def test_main_co_ca_dump_va_ban_so_lenh_moi_thi_IM(tmp_path):
    _dump(tmp_path)
    src = tmp_path / "a.jsonl.gz"
    src.write_bytes(b"x")
    (tmp_path / "trading_20260929_020000.counts").write_text(
        "bars\t1\n", encoding="utf-8"
    )
    tar = tmp_path / "orderbook_20260929.tar.gz"
    with tarfile.open(tar, "w:gz") as t:
        t.add(src, arcname="data/orderbook/A/a.jsonl.gz")
    with patch("scripts.backup_check.check_pg_restore", return_value="OK"):
        assert main(["--dry-run", "--backup-dir", str(tmp_path)]) == 0


# ---------------------------------------------------------------------------
# Dot 138: ban sao luu DB `.dump` moi nhat phai co ban ke `.counts` (ton tai, khac rong).
# Chi kiem ton tai va khac rong — noi dung la viec cua restore_drill.py (lam hai lan la bao trung).
# ---------------------------------------------------------------------------
from scripts.backup_check import evaluate_counts_statement


def _bf(name):
    return BackupFileInfo(
        name=name, path="/b/" + name, size_bytes=100 * 1024 * 1024, mtime=0.0
    )


def test_counts_dump_co_ban_ke_IM():
    assert evaluate_counts_statement(_bf("trading_20260930_221525.dump"), 670) == []


def test_counts_dump_thieu_ban_ke_BAO_neu_ten():
    a = evaluate_counts_statement(_bf("trading_20260930_221525.dump"), None)
    assert len(a) == 1
    assert "[CRITICAL]" in a[0] and "trading_20260930_221525.dump" in a[0]
    assert "bản kê" in a[0] and "Chủ nhật" in a[0]


def test_counts_dump_ban_ke_rong_BAO():
    assert len(evaluate_counts_statement(_bf("trading_20260930_221525.dump"), 0)) == 1


def test_counts_sql_gz_cu_khong_co_ban_ke_IM():
    """Dinh dang cu (truoc dot 137): khong dong hoi ban ke."""
    assert evaluate_counts_statement(_bf("trading_20260920_020000.sql.gz"), None) == []


def test_counts_khong_co_ban_sao_luu_nao_khong_bao_them():
    assert evaluate_counts_statement(None, None) == []


def _write_dump(d, stem="trading_20260930_221525"):
    (d / f"{stem}.dump").write_bytes(b"PGDMP" + b"\x00" * (90 * 1024 * 1024))


def test_main_dump_moi_thieu_ban_ke_PHAI_bao(tmp_path, capsys):
    _write_dump(tmp_path)
    with patch("scripts.backup_check.check_pg_restore", return_value="OK"):
        code = main(["--dry-run", "--backup-dir", str(tmp_path), "--no-orderbook"])
    assert code == 1
    assert "bản kê" in capsys.readouterr().out


def test_main_dump_moi_co_ban_ke_thi_IM(tmp_path):
    _write_dump(tmp_path)
    (tmp_path / "trading_20260930_221525.counts").write_text(
        "bars\t1\n", encoding="utf-8"
    )
    with patch("scripts.backup_check.check_pg_restore", return_value="OK"):
        assert main(["--dry-run", "--backup-dir", str(tmp_path), "--no-orderbook"]) == 0


def test_main_ban_ke_rong_PHAI_bao(tmp_path):
    _write_dump(tmp_path)
    (tmp_path / "trading_20260930_221525.counts").write_text("", encoding="utf-8")
    with patch("scripts.backup_check.check_pg_restore", return_value="OK"):
        assert main(["--dry-run", "--backup-dir", str(tmp_path), "--no-orderbook"]) == 1


def test_main_sql_gz_moi_nhat_khong_ban_ke_IM(tmp_path):
    f = tmp_path / "trading_20260920_020000.sql.gz"
    f.write_bytes(b"\x1f\x8b" + b"\x00" * (90 * 1024 * 1024))
    with patch("scripts.backup_check.check_pg_restore", return_value="OK"):
        assert main(["--dry-run", "--backup-dir", str(tmp_path), "--no-orderbook"]) == 0


def test_main_ban_ke_cua_dump_CU_khong_cuu_dump_moi(tmp_path):
    """Ban ke phai CUNG TEN GOC voi dump moi nhat, khong phai bat ky .counts nao."""
    import os

    old = tmp_path / "trading_20260929_020000.dump"
    old.write_bytes(b"PGDMP" + b"\x00" * (90 * 1024 * 1024))
    (tmp_path / "trading_20260929_020000.counts").write_text(
        "bars\t1\n", encoding="utf-8"
    )
    os.utime(old, (1, 1))
    _write_dump(tmp_path)  # moi nhat, khong co .counts
    with patch("scripts.backup_check.check_pg_restore", return_value="OK"):
        assert main(["--dry-run", "--backup-dir", str(tmp_path), "--no-orderbook"]) == 1
