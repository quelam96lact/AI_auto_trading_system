"""Hang doi gui lai cho trading.alerts.alert (brief dot 143, 02/10/2026).

Moi test dung ham gui gia duoc tiem vao — khong goi mang, khong gui Telegram that.
"""

import json
import threading
from datetime import UTC, datetime

import pytest

import trading.alerts as alerts_mod
from trading.alerts import alert, start_outbox, stop_outbox

SU_CO = (
    "phát hiện máy chủ ngủ/gián đoạn 953s (ngoài giờ giao dịch) "
    "từ 07:19:13 đến 07:35:36"
)


class FakeNet:
    """Ham gui gia: `up=False` -> tra False; `raises=True` -> nem; ghi lai tin da toi dich."""

    def __init__(self):
        self.up = True
        self.raises = False
        self.fail_texts: set[str] = set()
        self.delivered: list[str] = []
        self.calls = 0

    def __call__(self, text: str) -> bool:
        self.calls += 1
        if self.raises:
            raise OSError("Name or service not known")
        if not self.up or any(f in text for f in self.fail_texts):
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
    net = FakeNet()
    net.up = False
    box = _box(tmp_path, net)
    for i in (1, 2, 3):
        alert("WARN", f"tin{i}").join()
    net.up = True
    net.fail_texts = {"tin2"}
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
    box = _box(tmp_path, net)
    for i in range(203):
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
