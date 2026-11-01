"""Tests cho scripts/docker_down_alert.py (brief dot 8).

Tat dinh: khong sleep, khong so gio tuong (Windows clock ~15,6ms lam test
chap chon). Truyen `now` vao ham, monkeypatch phan gui.
"""

from datetime import date, datetime
from pathlib import Path

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


def test_t7_ngoai_khung_down_1h_im_down_3h_keu(tmp_path):
    """b. T7 10:00, down_since 1h truoc -> KHONG keu; down_since 3h truoc, chua gui lan nao -> KEU 1 tin, noi dung co gio bat dau tat va '3h'."""
    now = datetime(2026, 9, 5, 10, 0, tzinfo=TZ)  # T7
    stamp_file = tmp_path / "stamp"
    since_file = tmp_path / "since"

    # Case 1: down_since 1h truoc (< 2h) -> KHONG keu
    since_file.write_text(str(int(now.timestamp()) - 3600))
    sent = []
    rc = run_alert(
        now,
        frozenset(),
        send=_fake_send(sent),
        stamp_file=str(stamp_file),
        since_file=str(since_file),
    )
    assert rc == 0
    assert sent == []
    assert not stamp_file.exists()

    # Case 2: down_since 3h truoc (>= 2h), chua gui lan nao -> KEU 1 tin
    down_epoch = int(now.timestamp()) - 3 * 3600
    since_file.write_text(str(down_epoch))
    down_dt = datetime.fromtimestamp(down_epoch, TZ)
    sent = []
    rc = run_alert(
        now,
        frozenset(),
        send=_fake_send(sent),
        stamp_file=str(stamp_file),
        since_file=str(since_file),
    )
    assert rc == 0
    assert len(sent) == 1
    assert f"{down_dt:%H:%M}" in sent[0]
    assert "3h" in sent[0]
    assert "Docker tat tu" in sent[0]
    assert "systemctl status docker" in sent[0]
    assert "VN30F" in sent[0]
    assert stamp_file.exists()


def test_ngoai_khung_da_gui_2h_im_da_gui_7h_keu_lai(tmp_path):
    """c. Ngoai khung, da gui 2h truoc -> im; da gui 7h truoc va van tat -> keu lai."""
    now = datetime(2026, 9, 5, 10, 0, tzinfo=TZ)
    stamp_file = tmp_path / "stamp"
    since_file = tmp_path / "since"
    # Tat tu 10h truoc
    since_file.write_text(str(int(now.timestamp()) - 10 * 3600))

    # Da gui 2h truoc (< 6h) -> im
    stamp_file.write_text(str(int(now.timestamp()) - 2 * 3600))
    sent = []
    rc = run_alert(
        now,
        frozenset(),
        send=_fake_send(sent),
        stamp_file=str(stamp_file),
        since_file=str(since_file),
    )
    assert rc == 0
    assert sent == []

    # Da gui 7h truoc (>= 6h) va van tat -> keu lai
    stamp_file.write_text(str(int(now.timestamp()) - 7 * 3600))
    sent = []
    rc = run_alert(
        now,
        frozenset(),
        send=_fake_send(sent),
        stamp_file=str(stamp_file),
        since_file=str(since_file),
    )
    assert rc == 0
    assert len(sent) == 1
    assert "10h" in sent[0]


def test_lan_dau_goi_chua_co_since_file_ghi_now_va_im(tmp_path):
    """d. Lan dau goi (khong co since_file) -> ghi file voi now va KHONG keu ngoai khung (moi tat 0 gio)."""
    now = datetime(2026, 9, 5, 10, 0, tzinfo=TZ)
    stamp_file = tmp_path / "stamp"
    since_file = tmp_path / "since"
    assert not since_file.exists()

    sent = []
    rc = run_alert(
        now,
        frozenset(),
        send=_fake_send(sent),
        stamp_file=str(stamp_file),
        since_file=str(since_file),
    )
    assert rc == 0
    assert sent == []
    assert since_file.exists()
    assert int(since_file.read_text().strip()) == int(now.timestamp())


def test_since_file_hong_ghi_lai_bang_now_khong_nem(tmp_path):
    """e. since_file hong (noi dung rac) -> ghi lai = now, khong nem."""
    now = datetime(2026, 9, 5, 10, 0, tzinfo=TZ)
    stamp_file = tmp_path / "stamp"
    since_file = tmp_path / "since"
    since_file.write_text("corrupted_garbage_content_xyz!@#")

    sent = []
    rc = run_alert(
        now,
        frozenset(),
        send=_fake_send(sent),
        stamp_file=str(stamp_file),
        since_file=str(since_file),
    )
    assert rc == 0
    assert sent == []
    assert int(since_file.read_text().strip()) == int(now.timestamp())


def test_gui_that_bai_ngoai_khung_tra_2_khong_ghi_stamp(tmp_path, capsys):
    """f. Gui that bai ngoai khung -> tra 2, KHONG ghi spam stamp."""
    now = datetime(2026, 9, 5, 10, 0, tzinfo=TZ)
    stamp_file = tmp_path / "stamp"
    since_file = tmp_path / "since"
    since_file.write_text(str(int(now.timestamp()) - 3 * 3600))

    rc = run_alert(
        now,
        frozenset(),
        send=lambda text: False,
        stamp_file=str(stamp_file),
        since_file=str(since_file),
    )
    assert rc == 2
    assert not stamp_file.exists()
    out = capsys.readouterr().out
    assert "gui Telegram that bai" in out


def test_run_if_docker_up_co_dong_xoa_since_file():
    """g. Shell: test kiem run_if_docker_up.sh co dong rm -f "$REPO/logs/.docker_down_since"
    NAM SAU khoi kiem docker ps (dong phat SKIP) va TRUOC dong ghi "start" (doc file text, khong chay shell)."""
    sh_path = Path(__file__).parent.parent / "scripts" / "run_if_docker_up.sh"
    content = sh_path.read_text(encoding="utf-8")

    rm_line = 'rm -f "$REPO/logs/.docker_down_since"'
    skip_marker = 'SKIP: docker chua chay'
    start_marker = 'start" >> "$LOG"'

    assert rm_line in content, f"Khong tim thay dong '{rm_line}' trong run_if_docker_up.sh"
    assert skip_marker in content, "Khong tim thay dong phat SKIP trong run_if_docker_up.sh"
    assert start_marker in content, "Khong tim thay dong start trong run_if_docker_up.sh"

    skip_pos = content.index(skip_marker)
    rm_pos = content.index(rm_line)
    start_pos = content.index(start_marker)

    assert skip_pos < rm_pos < start_pos, (
        f"Thu tu khong dung: skip_pos={skip_pos}, rm_pos={rm_pos}, start_pos={start_pos}. "
        f"rm_line phai nam SAU skip va TRUOC start."
    )

