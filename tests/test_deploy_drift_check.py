"""Tests cho scripts/deploy_drift_check.py — cảnh báo lệch triển khai.

Brief 2026-09-01 (đợt 7) Task A: drift_report là hàm thuần tuý, không I/O,
nên test được mà không cần Docker/git.
"""

from scripts import deploy_drift_check
from scripts.deploy_drift_check import drift_report

COMMIT = 1_800_000_000  # mốc giả, chỉ để so sánh


def test_all_images_newer_than_commit_is_ok():
    images = {"collector": COMMIT + 1000, "engine": COMMIT + 2000}
    assert drift_report(COMMIT, images) == []


def test_engine_older_warns_engine_only():
    images = {"collector": COMMIT + 1000, "engine": COMMIT - 3600}
    msgs = drift_report(COMMIT, images)
    assert len(msgs) == 1
    # cảnh báo duy nhất nói VỀ engine (message hướng dẫn có chữ "collector"
    # trong lệnh compose build — nên kiểm theo prefix, không kiểm "không có chữ")
    assert msgs[0].startswith("[deploy-drift] engine:")
    assert "[deploy-drift] collector:" not in msgs[0]
    # phải nêu rõ lệch bao nhiêu (giờ hoặc ngày) — 3600s = "1 giờ"
    assert "giờ" in msgs[0]


def test_both_older_warns_both_services():
    images = {"collector": COMMIT - 7200, "engine": COMMIT - 3600}
    msgs = drift_report(COMMIT, images)
    assert len(msgs) == 2
    assert all("collector" in m or "engine" in m for m in msgs)


def test_none_image_is_a_warning_not_ok():
    """None (không đọc được image) ⇒ phải báo, KHÔNG được coi là ổn."""
    images = {"collector": None, "engine": COMMIT + 1000}
    msgs = drift_report(COMMIT, images)
    assert len(msgs) == 1
    assert "collector" in msgs[0]


def test_image_equal_to_commit_is_ok():
    """image bằng đúng commit_epoch ⇒ ổn (build ngay sau commit)."""
    images = {"collector": COMMIT, "engine": COMMIT + 1000}
    assert drift_report(COMMIT, images) == []


def _capture_sent(monkeypatch):
    """Bat noi dung Telegram thay vi gui that."""
    sent = []
    monkeypatch.setattr(deploy_drift_check, "send_telegram", sent.append)
    return sent


def test_git_that_bai_van_phai_keu(monkeypatch):
    """Chuong tu bao ma im lang dung luc CHINH NO hong thi vo dung.

    Truoc audit 01/09, nhanh nay chi in ra stdout roi return 1 — khong gui
    Telegram. Tuc neu git hong tren VPS thi khong ai biet, va cung khong ai
    biet la khong ai biet.
    """
    monkeypatch.setattr(
        deploy_drift_check, "_git_trading_commit_epoch", lambda: None
    )
    sent = _capture_sent(monkeypatch)
    rc = deploy_drift_check.main()
    assert rc == 1, f"git hong phai bao, rc={rc}"
    assert sent, "git hong PHAI gui Telegram, khong duoc chi in ra stdout"
    assert "KHÔNG đọc được commit" in sent[0]


def test_gui_telegram_hong_van_de_lai_dau_vet(monkeypatch, capsys):
    """send_telegram nem exception khong duoc lam chet script, nhung PHAI de
    lai dau vet o stdout — neu khong thi log noi doi rang canh bao da di.
    """

    def no(_text):
        raise RuntimeError("mang chet")

    monkeypatch.setattr(deploy_drift_check, "send_telegram", no)
    rc = deploy_drift_check._alert(["[deploy-drift] thu nghiem"])
    out = capsys.readouterr().out
    assert rc == 1, "gui hong van phai bao lech"
    assert "[deploy-drift] thu nghiem" in out, "phai in ly do truoc khi gui"
    assert "GUI TELEGRAM HONG" in out, (
        f"gui hong phai de lai dau vet, stdout thuc te: {out!r}"
    )


# ============ Brief Đợt 13 Task 2: Suy ra tên container động ============


def test_get_container_name_default_repo_basename(monkeypatch):
    """Khi không set COMPOSE_PROJECT_NAME, tên container lấy theo thư mục repo (chữ thường)."""
    import re
    from pathlib import Path

    monkeypatch.delenv("COMPOSE_PROJECT_NAME", raising=False)
    repo_name = re.sub(r"[^a-z0-9_-]", "_", Path(__file__).resolve().parents[1].name.lower())
    name = deploy_drift_check.get_container_name("collector")
    assert name == f"{repo_name}-collector-1"


def test_get_container_name_with_env_compose_project_name(monkeypatch):
    """Khi COMPOSE_PROJECT_NAME được set (vd: 'trading' trên VPS), tên container phải theo project đó."""
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "trading")
    name = deploy_drift_check.get_container_name("collector")
    assert name == "trading-collector-1"


def test_get_container_name_with_explicit_project_name():
    """Khi truyền project_name trực tiếp, tên container phải dùng project_name đó."""
    name = deploy_drift_check.get_container_name("engine", project_name="my_custom_project")
    assert name == "my_custom_project-engine-1"


def test_image_missing_warns_specifically():
    """Brief 52 Task 4.1: Container đang chạy nhưng image đã biến mất -> thông điệp riêng, cảnh báo nguy hiểm."""
    images = {"collector": "image_missing", "engine": COMMIT + 1000}
    msgs = drift_report(COMMIT, images)
    assert len(msgs) == 1
    assert "collector" in msgs[0]
    assert "BIẾN MẤT" in msgs[0]
    assert "đang chạy code không ai truy được" in msgs[0]


