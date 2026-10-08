"""Hang doi gui lai cho trading.alerts.alert (brief dot 143, 02/10/2026).

Moi test dung ham gui gia duoc tiem vao — khong goi mang, khong gui Telegram that.
"""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

import trading.alerts as alerts_mod
from trading.alerts import alert, start_outbox, stop_outbox

SU_CO = (
    "phát hiện máy chủ ngủ/gián đoạn 953s (ngoài giờ giao dịch) "
    "từ 07:19:13 đến 07:35:36"
)


class FakeNet:
    """Ham gui gia: `up=False` -> tra False; `raises=True` -> nem; ghi lai tin da toi dich.
    Gia lap gioi han 4096 ky tu cua Telegram: tra False neu len(text) > 4096."""

    def __init__(self, max_len: int = 4096):
        self.up = True
        self.raises = False
        self.fail_texts: set[str] = set()
        self.delivered: list[str] = []
        self.calls = 0
        self.max_len = max_len

    def __call__(self, text: str) -> bool:
        self.calls += 1
        if self.raises:
            raise OSError("Name or service not known")
        if not self.up or any(f in text for f in self.fail_texts) or len(text) > self.max_len:
            return False
        self.delivered.append(text)
        return True


class Clock:
    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture(autouse=True)
def _sach_outbox():
    stop_outbox()
    yield
    stop_outbox()


def _box(tmp_path, net, clock=None):
    return start_outbox(
        "test", directory=tmp_path, send_fn=net, clock=clock, run_thread=False
    )


def _file(tmp_path):
    return tmp_path / "alert_outbox_test.jsonl"


def _lines(tmp_path):
    return [ln for ln in _file(tmp_path).read_text(encoding="utf-8").splitlines() if ln]


def test_gui_duoc_ngay_thi_khong_co_file(tmp_path):
    net = FakeNet()
    _box(tmp_path, net)
    alert("CRITICAL", "x").join()
    assert net.delivered == ["[CRITICAL] x"]
    assert not _file(tmp_path).exists()


def test_gui_hong_thi_dung_mot_dong_co_emitted_at_va_noi_dung(tmp_path):
    net = FakeNet()
    net.up = False
    clock = Clock(datetime(2026, 10, 2, 0, 35, 36, tzinfo=UTC))
    _box(tmp_path, net, clock)
    alert("CRITICAL", "boom", a=1).join()
    rows = [json.loads(ln) for ln in _lines(tmp_path)]
    assert len(rows) == 1
    assert rows[0]["text"] == "[CRITICAL] boom {'a': 1}"
    assert datetime.fromisoformat(rows[0]["emitted_at"]) == clock.now


def test_ham_gui_nem_thi_alert_khong_nem_va_tin_vao_hang_doi(tmp_path):
    net = FakeNet()
    net.raises = True
    _box(tmp_path, net)
    t = alert("CRITICAL", "nem")
    t.join()
    assert len(_lines(tmp_path)) == 1


def test_mang_hoi_lai_gui_dung_thu_tu_co_tien_to_va_file_rong(tmp_path):
    net = FakeNet()
    net.up = False
    clock = Clock(datetime(2026, 10, 2, 0, 0, 0, tzinfo=UTC))
    box = _box(tmp_path, net, clock)
    for i in (1, 2, 3):
        clock.now = datetime(2026, 10, 2, 0, i, 0, tzinfo=UTC)
        alert("WARN", f"tin{i}").join()
    net.up = True
    assert box.flush() == 3
    assert [d.split("] ")[-1] for d in net.delivered] == ["tin1", "tin2", "tin3"]
    assert net.delivered[0].startswith("[GỬI TRỄ — phát lúc 07:01:00 02/10]")
    assert not _file(tmp_path).exists()


def test_tin_thu_2_trong_3_con_hong_thi_tin_1_di_va_2_3_o_lai_dung_thu_tu(tmp_path):
    # Mo phong mat mang tu tin 2: ca tin 2 va 3 deu hong -> khong go, giu nguyen thu tu
    net = FakeNet()
    net.up = False
    box = _box(tmp_path, net)
    for i in (1, 2, 3):
        alert("WARN", f"tin{i}").join()
    net.up = True
    net.fail_texts = {"tin2", "tin3"}
    assert box.flush() == 1
    assert len(net.delivered) == 1 and "tin1" in net.delivered[0]
    left = [json.loads(ln)["text"] for ln in _lines(tmp_path)]
    assert left == ["[WARN] tin2", "[WARN] tin3"]


def test_khoi_dong_lai_gui_nhung_tin_con_ton(tmp_path):
    _file(tmp_path).write_text(
        json.dumps(
            {"emitted_at": "2026-10-02T00:35:36+00:00", "text": "[CRITICAL] cu"},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    net = FakeNet()
    box = start_outbox("test", directory=tmp_path, send_fn=net, interval=3600)
    assert box.first_flush_done.wait(5)
    stop_outbox()
    assert len(net.delivered) == 1 and net.delivered[0].endswith("[CRITICAL] cu")
    assert not _file(tmp_path).exists()


def test_qua_200_tin_bo_tin_cu_nhat_va_lan_gui_ke_tiep_co_dong_da_bo(tmp_path):
    net = FakeNet()
    net.up = False
    lines = [
        json.dumps(
            {"emitted_at": "2026-10-02T00:00:00+00:00", "text": f"[WARN] t{i}"},
            ensure_ascii=False,
        )
        for i in range(200)
    ]
    _file(tmp_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    box = _box(tmp_path, net)
    for i in range(200, 203):
        box.enqueue(f"[WARN] t{i}")
    assert len(_lines(tmp_path)) == 200
    assert json.loads(_lines(tmp_path)[0])["text"] == "[WARN] t3"
    net.up = True
    box.flush()
    assert "đã bỏ 3 cảnh báo cũ vì hàng đợi đầy" in net.delivered[0]
    assert "đã bỏ" not in "".join(net.delivered[1:])
    assert not _file(tmp_path).exists()


def test_file_hong_khong_chet_giu_dong_tot_va_bao_dong_hong(tmp_path):
    good = json.dumps({"emitted_at": "2026-10-02T00:00:00+00:00", "text": "[WARN] tot"})
    _file(tmp_path).write_text(
        good + "\nday khong phai json\n" + good.replace("tot", "tot2") + "\n",
        encoding="utf-8",
    )
    net = FakeNet()
    box = _box(tmp_path, net)
    box.flush()
    assert len(net.delivered) == 3
    assert "tot" in net.delivered[0]
    assert "dong hong" in net.delivered[1] and "day khong phai json" in net.delivered[1]
    assert "tot2" in net.delivered[2]


def test_khong_goi_khoi_dong_thi_y_nhu_cu_va_khong_tao_file(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        alerts_mod, "send_telegram", lambda text: called.append(text) or False
    )
    alert("CRITICAL", "y nhu cu").join()
    assert called == ["[CRITICAL] y nhu cu"]
    assert list(tmp_path.iterdir()) == []
    assert alerts_mod._outbox is None


def test_thu_muc_khong_ton_tai_thi_khong_bat_gi(tmp_path):
    assert start_outbox("test", directory=tmp_path / "khong-co") is None
    assert alerts_mod._outbox is None


def test_hai_luong_cung_alert_khi_mang_hong_khong_mat_tin_khong_hong_file(tmp_path):
    net = FakeNet()
    net.up = False
    _box(tmp_path, net)
    n = 60
    barrier = threading.Barrier(2)

    def worker(tag):
        barrier.wait()
        ts = [alert("WARN", f"{tag}{i}") for i in range(n // 2)]
        for t in ts:
            t.join()

    ths = [threading.Thread(target=worker, args=(tag,)) for tag in ("a", "b")]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    texts = [json.loads(ln)["text"] for ln in _lines(tmp_path)]
    assert len(texts) == n
    assert len(set(texts)) == n


def test_tai_hien_su_co_953s_gui_hong_3_lan_roi_toi_dich_voi_gio_viet_nam(tmp_path):
    net = FakeNet()
    net.up = False
    clock = Clock(datetime(2026, 10, 2, 0, 35, 36, tzinfo=UTC))
    box = _box(tmp_path, net, clock)
    alert("CRITICAL", SU_CO).join()
    assert box.flush() == 0  # hong lan 2
    clock.now = datetime(2026, 10, 2, 0, 36, 36, tzinfo=UTC)
    assert box.flush() == 0  # hong lan 3
    assert net.delivered == []
    net.up = True
    assert box.flush() == 1
    assert net.delivered == [f"[GỬI TRỄ — phát lúc 07:35:36 02/10] [CRITICAL] {SU_CO}"]
    assert not _file(tmp_path).exists()


def test_ca_a2_tin_dai_va_hai_tin_thuong_toi_dich_co_ghi_ro_so_ky_tu_cat(tmp_path):
    # Ca A.2: tin 4.070 ky tu + hai tin thuong, mat mang roi co mang -> ca ba toi dich
    net = FakeNet(max_len=4096)
    net.up = False
    clock = Clock(datetime(2026, 10, 2, 0, 0, 0, tzinfo=UTC))
    box = _box(tmp_path, net, clock)

    # Tin dau dai dung 4.070 ky tu: "[CRITICAL] " (11 ky tu) + 4059 ky tu 'A'
    msg_dai = "A" * (4070 - len("[CRITICAL] "))
    alert("CRITICAL", msg_dai).join()
    alert("WARN", "lệnh thật bị từ chối 1").join()
    alert("WARN", "lệnh thật bị từ chối 2").join()

    assert len(_lines(tmp_path)) == 3
    # Mang hoi phuc
    net.up = True
    sent = box.flush()
    assert sent == 3
    assert len(net.delivered) == 3
    # Ca 3 tin toi dich, khong tin nao vuot 4.096 (va deu <= 3.900)
    assert all(len(m) <= 4096 for m in net.delivered)
    assert all(len(m) <= 3900 for m in net.delivered)
    # Tin dai bi cat va ghi ro so ky tu da cat
    assert "... [cắt " in net.delivered[0] and "ký tự]" in net.delivered[0]
    # Hai tin sau toi dich
    assert "lệnh thật bị từ chối 1" in net.delivered[1]
    assert "lệnh thật bị từ chối 2" in net.delivered[2]
    # Hang doi da sach
    assert not _file(tmp_path).exists()


def test_tin_hong_vinh_vien_bi_go_va_tin_sau_toi_dich(tmp_path):
    # Mot tin hong vinh vien o dau, hai tin sau tot -> hai tin sau toi dich, tin hong bi go khoi file
    net = FakeNet()
    net.up = False
    box = _box(tmp_path, net)
    alert("CRITICAL", "tin_hong_vinh_vien").join()
    alert("WARN", "tin2_tot").join()
    alert("WARN", "tin3_tot").join()

    net.up = True
    net.fail_texts = {"tin_hong_vinh_vien"}
    sent = box.flush()

    assert sent == 2
    # tin2_tot va tin3_tot toi dich
    assert any("tin2_tot" in m for m in net.delivered)
    assert any("tin3_tot" in m for m in net.delivered)
    # Co dong thong bao bo 1 canh bao
    assert any("bỏ 1 cảnh báo không gửi được" in m for m in net.delivered)
    # Tin hong da bi go khoi file
    assert not _file(tmp_path).exists()


def test_mat_mang_hoan_toan_khong_go_tin_giu_nguyen_thu_tu(tmp_path):
    # Mat mang hoan toan -> khong tin nao bi go, thu tu giu nguyen (khong coi mat mang la tin hong)
    net = FakeNet()
    net.up = False
    box = _box(tmp_path, net)
    alert("CRITICAL", "tin1").join()
    alert("WARN", "tin2").join()

    sent = box.flush()
    assert sent == 0
    assert net.delivered == []
    # Khong tin nao bi go, thu tu giu nguyen
    lines = _lines(tmp_path)
    assert len(lines) == 2
    assert json.loads(lines[0])["text"] == "[CRITICAL] tin1"
    assert json.loads(lines[1])["text"] == "[WARN] tin2"


def test_mang_chap_tin_dau_hong_mot_lan_roi_duoc_khong_bi_go(tmp_path):
    # Tin dau hong 1 lan roi gui duoc (mang chap dung luc do), tin thu hai duoc -> tin dau khong bi go
    class FlakyNet(FakeNet):
        def __init__(self):
            super().__init__()
            self.tin1_attempts = 0

        def __call__(self, text: str) -> bool:
            self.calls += 1
            if not self.up:
                return False
            if "tin1" in text:
                self.tin1_attempts += 1
                if self.tin1_attempts == 1:
                    return False
            self.delivered.append(text)
            return True

    net = FlakyNet()
    net.up = False
    box = _box(tmp_path, net)
    alert("CRITICAL", "tin1").join()
    alert("WARN", "tin2").join()

    net.up = True
    sent = box.flush()
    assert sent == 2
    assert any("tin1" in m for m in net.delivered)
    assert any("tin2" in m for m in net.delivered)
    # Khong bi go oan, khong co dong thong bao bo tin
    assert not any("bỏ 1 cảnh báo" in m for m in net.delivered)
    assert not _file(tmp_path).exists()


def test_hang_doi_chi_mot_tin_va_no_hong_giu_nguyen_khong_doan(tmp_path):
    # Hang doi chi 1 tin va no hong -> van con trong file sau flush()
    net = FakeNet()
    net.up = False
    box = _box(tmp_path, net)
    alert("CRITICAL", "tin_doc_nhat").join()

    net.up = True
    net.fail_texts = {"tin_doc_nhat"}
    sent = box.flush()
    assert sent == 0
    assert net.delivered == []
    assert len(_lines(tmp_path)) == 1
    assert json.loads(_lines(tmp_path)[0])["text"] == "[CRITICAL] tin_doc_nhat"


def test_thu_muc_khong_ghi_duoc_khong_bat_va_alert_khong_nem(tmp_path, monkeypatch):
    # Thu muc khong ghi duoc -> start_outbox tra None, co dong CRITICAL, alert() van khong nem
    ro_dir = tmp_path / "readonly_dir"
    ro_dir.mkdir()

    orig_write_text = Path.write_text

    def fake_write_text(self, data, encoding=None, errors=None):
        if ".probe_write" in self.name:
            raise PermissionError("Access is denied")
        return orig_write_text(self, data, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "write_text", fake_write_text)

    net = FakeNet()
    box = start_outbox("collector", directory=ro_dir, send_fn=net)
    assert box is None
    assert alerts_mod._outbox is None
    assert len(net.delivered) == 1
    assert "[CRITICAL]" in net.delivered[0]
    assert "collector" in net.delivered[0]
    assert "không ghi được" in net.delivered[0]

    # alert() van hoat dong, khong nem ngoai le
    t = alert("WARN", "sau_khi_outbox_tat")
    assert t is not None
    t.join()

