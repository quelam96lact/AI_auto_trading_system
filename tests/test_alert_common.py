"""Tests cho scripts/_alert_common.py — khuôn chuông tự kêu.

Brief đợt 58 (2026-09-19) Task 1:
- send trả False -> in GUI TELEGRAM HONG: send tra ve False, trả 1.
- send ném Exception -> in GUI TELEGRAM HONG: {type(e)}: {e}, trả 1.
- send trả True -> KHÔNG in GUI TELEGRAM HONG, trả 1.
"""

import os
from pathlib import Path

import pytest

from scripts._alert_common import alert_and_fail, load_json_state, save_json_state


def test_send_tra_false_in_gui_telegram_hong_va_tra_1(capsys):
    """Khi send trả False -> in câu báo gửi hỏng và vẫn thoát với mã 1."""
    ret = alert_and_fail("[test-alert]", ["canh bao 1", "canh bao 2"], lambda msg: False)
    assert ret == 1
    out = capsys.readouterr().out
    assert "canh bao 1" in out
    assert "[test-alert] GUI TELEGRAM HONG: send tra ve False" in out


def test_send_nem_exception_in_gui_telegram_hong_va_tra_1(capsys):
    """Khi send ném Exception -> bắt được exception, in loại lỗi và vẫn thoát mã 1."""
    def _exploding_send(msg):
        raise ConnectionResetError("Connection lost to Telegram")

    ret = alert_and_fail("[test-alert]", ["loi mang"], _exploding_send)
    assert ret == 1
    out = capsys.readouterr().out
    assert "loi mang" in out
    assert "[test-alert] GUI TELEGRAM HONG: ConnectionResetError: Connection lost to Telegram" in out


def test_send_tra_true_khong_in_gui_telegram_hong_va_tra_1(capsys):
    """Khi send trả True -> in nội dung cảnh báo ban đầu, KHÔNG in câu gửi hỏng, trả 1."""
    ret = alert_and_fail("[test-alert]", ["noi dung binh thuong"], lambda msg: True)
    assert ret == 1
    out = capsys.readouterr().out
    assert "noi dung binh thuong" in out
    assert "GUI TELEGRAM HONG" not in out


def test_load_json_state_thieu_file(tmp_path: Path):
    """File trạng thái không tồn tại -> trả về {} mà không in cảnh báo gì."""
    missing = tmp_path / "nonexistent.json"
    res = load_json_state(missing, "test-label")
    assert res == {}


def test_load_json_state_json_hong(tmp_path: Path, capsys):
    """File trạng thái chứa JSON hỏng -> trả về {} và in đúng câu cảnh báo qua _print_safe."""
    corrupted = tmp_path / "corrupted.json"
    corrupted.write_text("{invalid json", encoding="utf-8")
    res = load_json_state(corrupted, "test-label")
    assert res == {}
    out = capsys.readouterr().out
    assert "[test-label] File trạng thái" in out
    assert "hỏng hoặc không đọc được" in out
    assert "coi như lần chạy đầu." in out


def test_load_json_state_json_la_list(tmp_path: Path, capsys):
    """File trạng thái chứa JSON là [] -> trả về {} và in đúng câu cảnh báo không đúng định dạng dict."""
    list_file = tmp_path / "list.json"
    list_file.write_text("[1, 2, 3]", encoding="utf-8")
    res = load_json_state(list_file, "test-label")
    assert res == {}
    out = capsys.readouterr().out
    assert "[test-label] File trạng thái" in out
    assert "không đúng định dạng dict — coi như lần đầu." in out


def test_save_va_load_json_state_khop(tmp_path: Path):
    """Ghi và đọc lại trạng thái JSON khớp hoàn toàn."""
    target = tmp_path / "state.json"
    data = {"service": {"restarts": 1, "status": "ok"}}
    save_json_state(target, data)
    assert load_json_state(target, "test-label") == data


def test_save_json_state_thu_muc_cha_chua_co(tmp_path: Path):
    """Ghi trạng thái khi thư mục cha chưa tồn tại -> tự tạo thư mục cha."""
    nested = tmp_path / "sub" / "dir" / "state.json"
    data = {"status": "created_parent"}
    save_json_state(nested, data)
    assert load_json_state(nested, "test-label") == data


def test_save_json_state_ngat_giua_chung_khong_lam_do_file_dich(tmp_path: Path, monkeypatch):
    """Ghi bị ngắt giữa chừng (os.replace ném) -> file đích cũ còn nguyên vẹn."""
    target = tmp_path / "state.json"
    old_data = {"version": 1, "data": "old"}
    save_json_state(target, old_data)

    def fake_replace(src, dst):
        raise OSError("Disk simulated replace failure")

    monkeypatch.setattr(os, "replace", fake_replace)

    with pytest.raises(OSError, match="Disk simulated replace failure"):
        save_json_state(target, {"version": 2, "data": "new"})

    # File dich cu van con nguyen ven
    assert load_json_state(target, "test-label") == old_data

