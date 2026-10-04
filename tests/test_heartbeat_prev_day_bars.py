"""Đợt 160 — sáng ngày giao dịch, nến NGÀY của ngày giao dịch liền trước phải có người biết.

Sự cố thật 02/10/2026 (thứ Sáu): `bars_daily` chỉ có 8/174 mã. Backfill 20:30 in
`SKIP: docker chua chay`, daily-check 21:00 không ghi dòng nào, và **không ai được
báo** — cả hai job đều nằm trong `KHONG_CANH` nên heartbeat không canh tuổi.

Vì sao kiểm KẾT QUẢ chứ không canh job: canh tuổi job buổi tối không được (tuổi phụ
thuộc cuối tuần). Kiểm hệ quả — độ đủ nến ngày của ngày giao dịch liền trước — thì
bắt được mọi nguyên nhân (Docker tắt, máy ngủ, task bị từ chối) mà không phải chép
giờ chạy job nào vào heartbeat.

Khuôn theo `tests/test_heartbeat_check.py`: DB giả, mọi file trạng thái nằm trong
`tmp_path` — không chạm DB thật, không ghi `logs/` thật.
"""

import json
from datetime import date, datetime, timedelta

from trading.calendar_vn import TZ

# Thứ Hai 05/10/2026 09:00 (trong phiên sáng) — ngày giao dịch liền trước là thứ Sáu 02/10.
MONDAY_0900 = datetime(2026, 10, 5, 9, 0, tzinfo=TZ)
FRIDAY = date(2026, 10, 2)

# Tin GIỐNG THẬT của `evaluate_daily_completeness` khi sót mã (có đủ số mã có/tổng).
MSG_8_174 = (
    "⚠️ [AI Trading] CẢNH BÁO: Sót bar daily sau phiên!\n"
    "Tổng số mã active: 174\n"
    "Số mã có bar: 8\n"
    "Số mã THIẾU bar (166 mã): AAA, VCB, ... (+151 mã nữa)"
)


def _fresh_job_logs(logs_dir, now):
    """Log tươi cho mọi job canh 24/7 — để phép kiểm lịch cũ im lặng."""
    import scripts.heartbeat_check as hc

    stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    for job in hc.SCHEDULE_WATCH_JOBS.values():
        (logs_dir / job.log_file).write_text(
            f"{stamp} {job.label} start" + chr(10), encoding="utf-8"
        )


def _run_heartbeat(
    monkeypatch,
    tmp_path,
    fixed_now=MONDAY_0900,
    assess_result=(0, set(), "Đầy đủ: toàn bộ 174 mã active đều đã có bar daily."),
    assess_exc=None,
    ledger_mismatch=False,
    extra_args=(),
):
    """Chạy `main` với DB giả. Trả (rc, sent, calls, stdout).

    `sent` = các tin đã gửi Telegram (giả); `calls` = các ngày đã gọi `assess_date`.
    """
    import scripts.heartbeat_check as hc

    sent = []
    calls = []

    def fake_assess(storage, cfg, target_date, backfill_log):
        calls.append(target_date)
        if assess_exc is not None:
            raise assess_exc
        return assess_result

    monkeypatch.setattr(hc, "assess_date", fake_assess)
    monkeypatch.setattr(hc, "send_telegram", lambda msg: bool(sent.append(msg)) or True)
    monkeypatch.setenv("DB_DSN", "postgresql://x:x@127.0.0.1:5432/trading")

    class FakeDatetime:
        @staticmethod
        def now(tz):
            return fixed_now

        strptime = staticmethod(datetime.strptime)

    monkeypatch.setattr(hc, "datetime", FakeDatetime)

    class FakeCur:
        def __init__(self, result=None, rows=None):
            self._result = result
            self._rows = rows or []

        def fetchall(self):
            return self._rows

        def fetchone(self):
            return self._result

    class FakeConn:
        def execute(self, *a, **k):
            q = str(a[0])
            if "FROM heartbeat" in q:
                return FakeCur(
                    rows=[
                        ("collector", fixed_now - timedelta(seconds=30)),
                        ("engine", fixed_now - timedelta(seconds=45)),
                    ]
                )
            if "max(ts) FROM bars" in q:
                return FakeCur(result=(fixed_now - timedelta(minutes=2),))
            if "FROM engine_state" in q:
                # So sach: cash 99.000.000 + 1.000 cp * 1.000 d = 100.000.000 -> lech 0.
                return FakeCur(result=(99_000_000.0, 0.0) if not ledger_mismatch else (1.0, 0.0))
            if "FROM positions" in q:
                return FakeCur(rows=[(1_000.0, 1_000)] if not ledger_mismatch else [])
            return FakeCur()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(hc.psycopg, "connect", lambda *a, **k: FakeConn())
    monkeypatch.setattr(
        hc,
        "Storage",
        lambda dsn: type(
            "S",
            (),
            {
                "load_ssi_token": lambda self: {
                    "refresh_token_expires_at": fixed_now.timestamp() + 7200
                },
                "read_position_sync_ts": lambda self, account_no: fixed_now
                - timedelta(minutes=2),
            },
        )(),
    )

    _fresh_job_logs(tmp_path, fixed_now)
    rc = hc.main(["--logs-dir", str(tmp_path), *extra_args])
    return rc, sent, calls


# ============ Ca 1: tái hiện 02/10 ============


def test_bao_dung_mot_lan_khi_thieu_8_tren_174(monkeypatch, tmp_path):
    """Thứ Hai 05/10 09:00, ngày liền trước là thứ Sáu 02/10 có 8/174 mã.

    Phải có ĐÚNG MỘT cảnh báo, và tin phải nêu ngày, số mã, câu lệnh khắc phục.
    """
    rc, sent, calls = _run_heartbeat(
        monkeypatch, tmp_path, assess_result=(1, {"AAA"}, MSG_8_174)
    )

    assert calls == [FRIDAY], f"phải kiểm đúng ngày liền trước, thực tế {calls}"
    assert rc == 1
    assert len(sent) == 1, f"phải có đúng MỘT tin, thực tế {len(sent)}: {sent}"
    tin = sent[0]
    assert "2026-10-02" in tin, tin
    assert "8" in tin and "174" in tin, tin
    assert "sched.sh backfill" in tin, tin
    assert "§9.6" in tin, tin
    assert "[WARN]" in tin, tin


def test_muc_2_thi_la_critical(monkeypatch, tmp_path):
    """`code` 2 (sự cố dữ liệu thật / backfill 2 ngày liên tiếp) -> CRITICAL."""
    rc, sent, calls = _run_heartbeat(
        monkeypatch,
        tmp_path,
        assess_result=(2, {"AAA"}, "🚨 [AI Trading] SỰ CỐ DỮ LIỆU: 0/174 mã có bar."),
    )
    assert calls == [FRIDAY]
    assert rc == 1
    assert len(sent) == 1 and "[CRITICAL]" in sent[0], sent


# ============ Ca 2: mỗi ngày P chỉ báo một lần ============


def test_goi_lan_hai_cung_trang_thai_thi_khong_bao_them(monkeypatch, tmp_path):
    rc1, sent1, _calls1 = _run_heartbeat(
        monkeypatch, tmp_path, assess_result=(1, {"AAA"}, MSG_8_174)
    )
    assert rc1 == 1 and len(sent1) == 1

    import scripts.heartbeat_check as hc

    state_file = tmp_path / hc.PREV_DAY_BARS_STATE_NAME
    assert state_file.is_file(), "phải ghi trạng thái 'đã báo ngày P'"
    assert json.loads(state_file.read_text(encoding="utf-8"))["alerted_for"] == "2026-10-02"

    rc2, sent2, calls2 = _run_heartbeat(
        monkeypatch, tmp_path, assess_result=(1, {"AAA"}, MSG_8_174)
    )
    assert rc2 == 0, f"lần hai không có gì để báo, rc={rc2}"
    assert sent2 == [], f"lần hai KHÔNG được gửi thêm tin nào: {sent2}"
    assert calls2 == [], "đã báo cho 2026-10-02 rồi thì không gọi assess_date nữa"


# ============ Ca 3: đủ mã thì im ============


def test_du_174_tren_174_thi_khong_bao(monkeypatch, tmp_path):
    import scripts.heartbeat_check as hc

    rc, sent, calls = _run_heartbeat(monkeypatch, tmp_path, assess_result=(0, set(), "Đầy đủ."))
    assert calls == [FRIDAY], "vẫn phải HỎI (để biết là đủ), chỉ không báo"
    assert rc == 0
    assert sent == [], f"đủ mã thì không tin nào: {sent}"
    assert not (tmp_path / hc.PREV_DAY_BARS_STATE_NAME).exists(), (
        "không báo thì không ghi trạng thái — để nếu tối nay hỏng thì sáng mai còn báo được"
    )


# ============ Ca 4: P lùi qua ngày nghỉ ============


def test_ngay_lien_truoc_la_ngay_nghi_thi_lui_tiep(monkeypatch, tmp_path):
    """Thứ Năm 03/09/2026: 02/09, 01/09, 31/08 đều là ngày nghỉ trong config -> P = 28/08."""
    thursday = datetime(2026, 9, 3, 9, 0, tzinfo=TZ)
    rc, sent, calls = _run_heartbeat(
        monkeypatch, tmp_path, fixed_now=thursday, assess_result=(1, {"AAA"}, MSG_8_174)
    )
    assert calls == [date(2026, 8, 28)], f"P phải lùi qua ngày nghỉ, thực tế {calls}"
    assert rc == 1 and len(sent) == 1
    assert "2026-08-28" in sent[0], sent[0]


# ============ Ca 5: --dry-run không ghi trạng thái ============


def test_dry_run_in_tin_nhung_khong_ghi_trang_thai(monkeypatch, tmp_path, capsys):
    import scripts.heartbeat_check as hc

    rc, _sent, calls = _run_heartbeat(
        monkeypatch,
        tmp_path,
        assess_result=(1, {"AAA"}, MSG_8_174),
        extra_args=("--dry-run",),
    )
    out = capsys.readouterr().out
    assert calls == [FRIDAY]
    assert rc == 1
    assert "2026-10-02" in out and "sched.sh backfill" in out, out
    assert not (tmp_path / hc.PREV_DAY_BARS_STATE_NAME).exists(), (
        "--dry-run không được ghi trạng thái, nếu không lần chạy thật sẽ im lặng"
    )


# ============ Ca 6: lỗi ở phép kiểm mới không được giết chuông báo ============


def test_assess_date_nem_loi_thi_cac_phep_kiem_khac_van_chay(
    monkeypatch, tmp_path, capsys
):
    rc, sent, _calls = _run_heartbeat(
        monkeypatch,
        tmp_path,
        assess_exc=RuntimeError("khong ket noi duoc DB"),
        ledger_mismatch=True,
    )
    captured = capsys.readouterr()
    # Lỗi đi ra STDERR (stdout phải giữ hợp đồng "bằng đúng nội dung gửi Telegram")
    assert "heartbeat khong kiem duoc nen ngay" in captured.err, captured.err
    assert "heartbeat khong kiem duoc nen ngay" not in captured.out, captured.out
    assert rc == 1, "phép kiểm 2C (sổ sách lệch) vẫn phải báo"
    assert any("LỆCH" in m for m in sent), f"tin 2C bị ăn mất: {sent}"


# ============ Ca 7: ngoài giờ giao dịch thì không gọi ============


def test_ngoai_gio_giao_dich_thi_khong_goi_assess_date(monkeypatch, tmp_path):
    evening = datetime(2026, 10, 5, 20, 0, tzinfo=TZ)
    rc, _sent, calls = _run_heartbeat(
        monkeypatch,
        tmp_path,
        fixed_now=evening,
        assess_result=(1, {"AAA"}, MSG_8_174),
        extra_args=("--dry-run",),
    )
    assert calls == [], f"ngoài giờ giao dịch không được kiểm, thực tế {calls}"
    assert rc == 0
