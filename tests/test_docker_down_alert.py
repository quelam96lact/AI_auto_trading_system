"""Tests cho scripts/docker_down_alert.py (brief dot 8).

Tat dinh: khong sleep, khong so gio tuong (Windows clock ~15,6ms lam test
chap chon). Truyen `now` vao ham, monkeypatch phan gui.
"""

from datetime import date, datetime

from scripts.docker_down_alert import load_holidays, run_alert
from trading.calendar_vn import TZ


def _fake_send(sent):
    def _send(msg):
        sent.append(msg)
        return True
    return _send


def test_gio_giao_dich_docker_chet_thi_keu(tmp_path):
    """Khung 08:00-15:00, ngay giao dich, chua tung gui -> CO gui."""
    sent = []
    now = datetime(2026, 9, 3, 9, 15, tzinfo=TZ)  # thu 5, khong ngay le
    rc = run_alert(now, frozenset(), send=_fake_send(sent), stamp_file=str(tmp_path / "stamp"))
    assert rc == 0
    assert len(sent) == 1
    assert "Docker khong chay" in sent[0]
    # ghi dau moc de lan sau khoi spam
    assert (tmp_path / "stamp").exists()


def test_ngay_le_thi_im(tmp_path):
    """02/09 la ngay le trong config.yaml -> im lang, khong gui."""
    holidays = load_holidays()
    assert date(2026, 9, 2) in holidays  # neu sua config.yaml thi sua test
    sent = []
    now = datetime(2026, 9, 2, 9, 15, tzinfo=TZ)
    rc = run_alert(now, holidays, send=_fake_send(sent), stamp_file=str(tmp_path / "stamp"))
    assert rc == 0
    assert sent == []


def test_da_gui_trong_30_phut_thi_im(tmp_path):
    """File dau moi (gui < 30 phut truoc) -> im lang, khong gui lan hai."""
    now = datetime(2026, 9, 3, 9, 15, tzinfo=TZ)
    stamp = tmp_path / "stamp"
    stamp.write_text(str(int(now.timestamp()) - 60))  # 60 giay truoc
    sent = []
    rc = run_alert(now, frozenset(), send=_fake_send(sent), stamp_file=str(stamp))
    assert rc == 0
    assert sent == []


def test_gui_hong_khong_lam_chet_script(tmp_path, capsys):
    """send_telegram nem exception -> tra 2 (Brief 126 §2b) va de lai dau vet stdout."""

    def boom(text):
        raise RuntimeError("telegram chet")

    now = datetime(2026, 9, 3, 9, 15, tzinfo=TZ)
    rc = run_alert(now, frozenset(), send=boom, stamp_file=str(tmp_path / "stamp"))
    # Brief 126 §2b: can keu nhung gui exception -> tra 2 de run_if_docker_up ghi ALERT_EXIT=2
    assert rc == 2
    out = capsys.readouterr().out
    assert "gui Telegram loi" in out  # dau vet CU THE cua loi gui, khong phai
    # loi chung chung — neu bo try/except trong, exception bi lop ngoai cung
    # bat va chi in "loi khong lo truoc" => test nay do


def test_gui_telegram_that_bai_khong_ghi_dau_stamp(tmp_path, capsys):
    """Brief 57 Task 2: send_telegram trả False -> KHÔNG ghi dấu stamp, để lần sau còn thử lại."""
    now = datetime(2026, 9, 3, 9, 15, tzinfo=TZ)
    stamp = tmp_path / "stamp"
    rc = run_alert(now, frozenset(), send=lambda text: False, stamp_file=str(stamp))
    # Brief 126 §2b: can keu nhung send tra ve False -> tra 2 de he thong biet gui that bai
    assert rc == 2
    assert not stamp.exists()
    out = capsys.readouterr().out
    assert "gui Telegram that bai" in out


def test_gui_telegram_thanh_cong_ghi_dau_stamp(tmp_path):
    """Brief 57 Task 2: send_telegram trả True -> CÓ ghi dấu stamp chống spam."""
    now = datetime(2026, 9, 3, 9, 15, tzinfo=TZ)
    stamp = tmp_path / "stamp"
    rc = run_alert(now, frozenset(), send=lambda text: True, stamp_file=str(stamp))
    assert rc == 0
    assert stamp.exists()


def test_send_tra_none_bi_coi_la_that_bai(tmp_path):
    """Brief 63 Task 2.4: send trả None (như list.append cũ) bị coi là THẤT BẠI, KHÔNG ghi stamp."""
    now = datetime(2026, 9, 3, 9, 15, tzinfo=TZ)
    stamp = tmp_path / "stamp"
    rc = run_alert(now, frozenset(), send=lambda text: None, stamp_file=str(stamp))
    # Brief 126 §2b: can keu nhung send tra ve None -> coi la that bai, tra 2
    assert rc == 2
    assert not stamp.exists()

