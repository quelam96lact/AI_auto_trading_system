"""Unit tests cho scripts/disk_check.py (Brief 132)."""

from __future__ import annotations

from unittest.mock import patch

from scripts.disk_check import evaluate_disk

GB = 1024**3


def test_khong_dieu_kien_nao_cham_thi_im():
    # 100 GB, con 50 GB (50%): tren ca hai nguong
    assert evaluate_disk(50 * GB, 100 * GB, 10.0, 10.0, "/x") == []


def test_duoi_nguong_tuyet_doi_nhung_tren_ty_le():
    # 40 GB, con 8 GB = 20%: chi cham nguong 10 GB
    alerts = evaluate_disk(8 * GB, 40 * GB, 10.0, 10.0, "/x")
    assert len(alerts) == 1
    assert "[CRITICAL]" in alerts[0]
    assert "/x" in alerts[0]


def test_duoi_ty_le_nhung_tren_nguong_tuyet_doi():
    # 500 GB, con 40 GB = 8%: chi cham nguong 10%
    alerts = evaluate_disk(40 * GB, 500 * GB, 10.0, 10.0, "/x")
    assert len(alerts) == 1
    assert "[CRITICAL]" in alerts[0]


def test_ca_hai_dieu_kien_cham_thi_van_mot_cau_canh_bao():
    alerts = evaluate_disk(2 * GB, 40 * GB, 10.0, 10.0, "/x")
    assert len(alerts) == 1
    assert "[CRITICAL]" in alerts[0]


def test_dung_o_nguong_thi_chua_keu():
    # Bang nguong tuyet doi (10 GB) va bang nguong ty le (10%) -> chua keu
    assert evaluate_disk(10 * GB, 100 * GB, 10.0, 10.0, "/x") == []


def test_main_gui_hong_tra_2(tmp_path):
    with (
        patch(
            "scripts.disk_check.shutil.disk_usage",
            return_value=(40 * GB, 39 * GB, 1 * GB),
        ),
        patch("scripts.disk_check.send_telegram", return_value=False),
    ):
        from scripts.disk_check import main

        assert main(["--path", str(tmp_path)]) == 2


def test_main_gui_ne_nem_ngoai_le_van_tra_2(tmp_path):
    with (
        patch(
            "scripts.disk_check.shutil.disk_usage",
            return_value=(40 * GB, 39 * GB, 1 * GB),
        ),
        patch("scripts.disk_check.send_telegram", side_effect=RuntimeError("boom")),
    ):
        from scripts.disk_check import main

        assert main(["--path", str(tmp_path)]) == 2


def test_main_gui_thanh_cong_tra_1(tmp_path):
    with (
        patch(
            "scripts.disk_check.shutil.disk_usage",
            return_value=(40 * GB, 39 * GB, 1 * GB),
        ),
        patch("scripts.disk_check.send_telegram", return_value=True) as sent,
    ):
        from scripts.disk_check import main

        assert main(["--path", str(tmp_path)]) == 1
    sent.assert_called_once()


def test_main_dry_run_khong_gui(tmp_path):
    with (
        patch(
            "scripts.disk_check.shutil.disk_usage",
            return_value=(40 * GB, 39 * GB, 1 * GB),
        ),
        patch("scripts.disk_check.send_telegram") as sent,
    ):
        from scripts.disk_check import main

        assert main(["--path", str(tmp_path), "--dry-run"]) == 1
    sent.assert_not_called()


def test_main_du_cho_tra_0_va_khong_gui(tmp_path):
    with (
        patch(
            "scripts.disk_check.shutil.disk_usage",
            return_value=(100 * GB, 20 * GB, 80 * GB),
        ),
        patch("scripts.disk_check.send_telegram") as sent,
    ):
        from scripts.disk_check import main

        assert main(["--path", str(tmp_path)]) == 0
    sent.assert_not_called()


def test_main_duong_dan_khong_ton_tai_tra_2(tmp_path):
    from scripts.disk_check import main

    assert main(["--path", str(tmp_path / "khong-co")]) == 2


def test_backup_dir_vang_KHONG_duoc_giet_phep_kiem_dia(tmp_path, capsys):
    """Thư mục sao lưu vắng: bỏ qua phép đo PHỤ, vẫn chạy phép đo CHÍNH (dung lượng đĩa).

    Trước đây trả 2. Đo thật 29/09 trên Windows: `sched.sh disk-check` truyền mặc
    định `/var/backups/trading-db` (không tồn tại, lại bị Git Bash dịch thành
    `C:\\Program Files\\Git\\var\\...`), nên job thoát 2 và **không bao giờ kiểm
    đĩa** — đúng lúc nó được lập lịch để canh. "Có bản sao lưu hay không" là việc
    của `backup_check.py`, không phải của job này.
    """
    from scripts.disk_check import main

    rc = main(["--path", str(tmp_path), "--backup-dir", str(tmp_path / "khong-co")])
    assert rc == 0, f"phep kiem dia van phai chay, rc={rc}"
    assert "Bo qua phep do thu muc sao luu" in capsys.readouterr().out


def test_backup_dir_do_rieng_khong_gia_dinh_cung_o(tmp_path):
    """Duong --path day, nhung o chua sao luu (--backup-dir) can: van phai keu."""
    repo = tmp_path / "repo"
    bak = tmp_path / "bak"
    repo.mkdir()
    bak.mkdir()

    def fake_usage(p):
        return (
            (40 * GB, 39 * GB, 1 * GB)
            if str(p) == str(bak)
            else (100 * GB, 10 * GB, 90 * GB)
        )

    with (
        patch("scripts.disk_check.shutil.disk_usage", side_effect=fake_usage),
        patch("scripts.disk_check.send_telegram", return_value=True) as sent,
    ):
        from scripts.disk_check import main

        assert main(["--path", str(repo), "--backup-dir", str(bak)]) == 1
    assert str(bak) in sent.call_args[0][0]


def test_bao_cao_liet_ke_cai_dang_chiem_cho(tmp_path):
    ob = tmp_path / "data" / "orderbook" / "VN30F"
    ob.mkdir(parents=True)
    (ob / "2026-09-29.jsonl.gz").write_bytes(b"x" * 2048)
    with (
        patch(
            "scripts.disk_check.shutil.disk_usage",
            return_value=(40 * GB, 39 * GB, 1 * GB),
        ),
        patch("scripts.disk_check.send_telegram", return_value=True) as sent,
    ):
        from scripts.disk_check import main

        main(["--path", str(tmp_path)])
    msg = sent.call_args[0][0]
    assert "orderbook" in msg
    assert "logs" in msg

def test_default_backup_dir_doc_tu_TRADING_BACKUP_DIR(monkeypatch):
    """Mặc định thư mục sao lưu phải đọc TRADING_BACKUP_DIR (.env) trước đường dẫn Ubuntu.

    Đo thật 29/09: khi chưa có cơ chế này, gọi job đúng như lịch sẽ gọi (không tham
    số) thì trên Windows `scripts.disk_check` nhận `/var/backups/trading-db` — vừa không tồn tại,
    vừa bị Git Bash dịch thành `C:\\Program Files\\Git\\var\\...`. Hậu quả đã đo:
    backup-check gửi CẢNH BÁO GIẢ mỗi ngày, disk-check thoát 2 và không kiểm đĩa,
    orderbook-backup chết ở `mkdir /var`. `run_if_docker_up.sh` nạp .env TRƯỚC khi
    chạy job, nên biến này tới được job.
    """
    import importlib

    import scripts.disk_check as m

    monkeypatch.setenv("TRADING_BACKUP_DIR", "/tmp/bk-cua-toi")
    importlib.reload(m)
    assert m.DEFAULT_BACKUP_DIR == "/tmp/bk-cua-toi"

    monkeypatch.delenv("TRADING_BACKUP_DIR", raising=False)
    importlib.reload(m)
    assert m.DEFAULT_BACKUP_DIR == "/var/backups/trading-db"
