"""Unit tests cho Brief 198: phép kiểm số mã có nến 5 phút ngày liền trước trong heartbeat.

Bao gồm:
- Các ca kiểm chứng cho prev_day_5m_alert theo §3 Bước 4
- Các ca kiểm chứng nối vào main theo §3 Bước 5 (bọc try/except, --dry-run không ghi state, v.v.)
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import scripts.heartbeat_check as hc
from scripts.heartbeat_check import (
    PREV_DAY_5M_STATE_NAME,
    prev_day_5m_alert,
)
from trading.calendar_vn import TZ

# Thứ Ba 27/10/2026 lúc 09:00 — ngày liền trước P = Thứ Hai 26/10/2026
TUESDAY_27 = datetime(2026, 10, 27, 9, 0, 0, tzinfo=TZ)
MONDAY_26 = date(2026, 10, 26)

# 5 phiên trước P (26/10): T6 23/10, T5 22/10, T4 21/10, T3 20/10, T2 19/10
PRIOR_5_DAYS = [
    date(2026, 10, 23),
    date(2026, 10, 22),
    date(2026, 10, 21),
    date(2026, 10, 20),
    date(2026, 10, 19),
]


class FakeStorage:
    def __init__(self, day_counts: dict[date, int]):
        self._counts = dict(day_counts)

    def read_5m_active_symbol_day_counts(self, frm: date, to: date) -> dict[date, int]:
        return {d: c for d, c in self._counts.items() if frm <= d <= to}


# ============ Bước 4: prev_day_5m_alert ============


def test_prev_day_5m_alert_170_no_alert():
    """4.1: n_P = 170, 5 phiên trước đều 172: không báo (170 >= 0.8 * 172 = 137.6)."""
    counts = {d: 172 for d in PRIOR_5_DAYS}
    counts[MONDAY_26] = 170
    storage = FakeStorage(counts)

    tin, p_iso = prev_day_5m_alert(storage, TUESDAY_27, frozenset(), None)
    assert tin is None
    assert p_iso == "2026-10-26"


def test_prev_day_5m_alert_3_alerts():
    """4.2: n_P = 3, 5 phiên trước đều 172: báo; tin chứa '2026-10-26' và 'sched.sh backfill-5m'."""
    counts = {d: 172 for d in PRIOR_5_DAYS}
    counts[MONDAY_26] = 3
    storage = FakeStorage(counts)

    tin, p_iso = prev_day_5m_alert(storage, TUESDAY_27, frozenset(), None)
    assert tin is not None
    assert p_iso == "2026-10-26"
    assert "2026-10-26" in tin
    assert "sched.sh backfill-5m" in tin
    assert "[WARN]" in tin
    assert "(idempotent)" in tin


def test_prev_day_5m_alert_threshold_boundary_138_no_alert():
    """4.3: Biên ngưỡng 0.8 * 172 = 137.6: n_P = 138 (>= 137.6) -> không báo."""
    counts = {d: 172 for d in PRIOR_5_DAYS}
    counts[MONDAY_26] = 138
    storage = FakeStorage(counts)

    tin, p_iso = prev_day_5m_alert(storage, TUESDAY_27, frozenset(), None)
    assert tin is None
    assert p_iso == "2026-10-26"


def test_prev_day_5m_alert_threshold_boundary_137_alerts():
    """4.4: Biên ngưỡng 0.8 * 172 = 137.6: n_P = 137 (< 137.6) -> báo."""
    counts = {d: 172 for d in PRIOR_5_DAYS}
    counts[MONDAY_26] = 137
    storage = FakeStorage(counts)

    tin, p_iso = prev_day_5m_alert(storage, TUESDAY_27, frozenset(), None)
    assert tin is not None
    assert p_iso == "2026-10-26"
    assert "137 mã thanh khoản" in tin
    assert "172" in tin


def test_prev_day_5m_alert_median_not_min():
    """4.5: Trung vị chứ không phải min: 5 phiên trước [172, 172, 172, 172, 3] và n_P = 100 thì vẫn báo."""
    counts = {
        PRIOR_5_DAYS[0]: 172,
        PRIOR_5_DAYS[1]: 172,
        PRIOR_5_DAYS[2]: 172,
        PRIOR_5_DAYS[3]: 172,
        PRIOR_5_DAYS[4]: 3,
        MONDAY_26: 100,
    }
    storage = FakeStorage(counts)

    tin, _p_iso = prev_day_5m_alert(storage, TUESDAY_27, frozenset(), None)
    assert tin is not None, "Phải báo vì trung vị là 172 và 100 < 0.8 * 172"
    assert "172" in tin


def test_prev_day_5m_alert_already_alerted_silent():
    """4.6: alerted_for == '2026-10-26': không báo (tránh spam)."""
    counts = {d: 172 for d in PRIOR_5_DAYS}
    counts[MONDAY_26] = 3
    storage = FakeStorage(counts)

    tin, p_iso = prev_day_5m_alert(
        storage, TUESDAY_27, frozenset(), alerted_for="2026-10-26"
    )
    assert tin is None
    assert p_iso == "2026-10-26"


def test_prev_day_5m_alert_empty_table_before_p_silent():
    """4.7: Bảng rỗng trước P: không báo."""
    counts = {MONDAY_26: 0}
    storage = FakeStorage(counts)

    tin, p_iso = prev_day_5m_alert(storage, TUESDAY_27, frozenset(), None)
    assert tin is None
    assert p_iso == "2026-10-26"

    empty_storage = FakeStorage({})
    tin_empty, p_iso_empty = prev_day_5m_alert(
        empty_storage, TUESDAY_27, frozenset(), None
    )
    assert tin_empty is None
    assert p_iso_empty == "2026-10-26"


def test_prev_day_5m_alert_monday_p_is_friday():
    """4.8: now là thứ Hai 26/10 thì P = thứ Sáu 23/10 (qua cuối tuần)."""
    now_monday = datetime(2026, 10, 26, 9, 0, 0, tzinfo=TZ)
    friday_23 = date(2026, 10, 23)

    counts = {friday_23: 170, date(2026, 10, 22): 172}
    storage = FakeStorage(counts)

    _tin, p_iso = prev_day_5m_alert(storage, now_monday, frozenset(), None)
    assert p_iso == "2026-10-23"


# ============ Audit đợt 198: các ca phép phá còn sống ============


def test_prev_day_5m_alert_exactly_80_pct_silent():
    """n_P đúng bằng 0.8 * trung vị (8 / 10) thì KHÔNG báo: ngưỡng là '<', không phải '<='."""
    counts = {d: 10 for d in PRIOR_5_DAYS}
    counts[MONDAY_26] = 8
    tin, _ = prev_day_5m_alert(FakeStorage(counts), TUESDAY_27, frozenset(), None)
    assert tin is None


def test_prev_day_5m_alert_p_missing_counts_as_zero():
    """Job SKIP hẳn nên ngày P không có dòng nào: n_P = 0 và phải báo."""
    counts = {d: 172 for d in PRIOR_5_DAYS}
    tin, _ = prev_day_5m_alert(FakeStorage(counts), TUESDAY_27, frozenset(), None)
    assert tin is not None
    assert "0 mã thanh khoản" in tin


def test_prev_day_5m_alert_baseline_excludes_p():
    """Trung vị chỉ lấy các ngày TRƯỚC P. Gộp cả P (8) vào thì trung vị tụt về 10 và lọt."""
    recent_first = [10, 10, 100, 100, 100]
    counts = dict(zip(PRIOR_5_DAYS, recent_first))
    counts[MONDAY_26] = 8
    tin, _ = prev_day_5m_alert(FakeStorage(counts), TUESDAY_27, frozenset(), None)
    assert tin is not None
    assert "trung vị 5 phiên trước 100" in tin


def test_prev_day_5m_alert_uses_5_most_recent_days():
    """Có hơn 5 ngày trước P thì lấy 5 ngày GẦN NHẤT, không phải 5 ngày cũ nhất."""
    older_5 = [date(2026, 10, 12) + timedelta(days=i) for i in range(5)]  # 12-16/10
    counts = {d: 172 for d in older_5}
    counts.update({d: 3 for d in PRIOR_5_DAYS})
    counts[MONDAY_26] = 3
    tin, _ = prev_day_5m_alert(FakeStorage(counts), TUESDAY_27, frozenset(), None)
    assert tin is None


# ============ Bước 5: Nối vào main ============


def _setup_heartbeat_env(monkeypatch, tmp_path, fixed_now=TUESDAY_27):
    """Môi trường giả lập cho main() của heartbeat_check."""
    monkeypatch.setenv("DB_DSN", "postgresql://user:pass@127.0.0.1:5432/trading")

    class FakeDatetime:
        @staticmethod
        def now(tz):
            return fixed_now

        strptime = staticmethod(datetime.strptime)

    monkeypatch.setattr(hc, "datetime", FakeDatetime)

    # Fresh job logs để schedule watch không sinh alert
    stamp = fixed_now.strftime("%Y-%m-%d %H:%M:%S")
    for job in hc.SCHEDULE_WATCH_JOBS.values():
        (tmp_path / job.log_file).write_text(
            f"{stamp} {job.label} start\n", encoding="utf-8"
        )

    # Fake DB queries
    class FakeCur:
        def fetchall(self):
            return []

        def fetchone(self):
            return None

    class FakeConn:
        def execute(self, *a, **k):
            q = str(a[0])
            if "FROM heartbeat" in q:
                return type(
                    "C",
                    (),
                    {
                        "fetchall": lambda s: [
                            ("collector", fixed_now - timedelta(seconds=30)),
                            ("engine", fixed_now - timedelta(seconds=45)),
                        ]
                    },
                )()
            if "max(ts) FROM bars" in q:
                return type(
                    "C", (), {"fetchone": lambda s: (fixed_now - timedelta(minutes=2),)}
                )()
            if "FROM engine_state" in q:
                return type("C", (), {"fetchone": lambda s: (100_000_000.0, 0.0)})()
            if "FROM positions" in q:
                return type("C", (), {"fetchall": lambda s: []})()
            return FakeCur()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(hc.psycopg, "connect", lambda *a, **k: FakeConn())

    # Fake Storage
    class _MockStorage:
        def load_ssi_token(self):
            return {"refresh_token_expires_at": fixed_now.timestamp() + 7200}

        def read_position_sync_ts(self, acct):
            return fixed_now - timedelta(minutes=2)

        def read_foreign_flow_day_counts(self, frm, to):
            return {d: 1557 for d in PRIOR_5_DAYS} | {MONDAY_26: 1557}

        def read_5m_active_symbol_day_counts(self, frm, to):
            return {d: 172 for d in PRIOR_5_DAYS} | {MONDAY_26: 3}

    monkeypatch.setattr(hc, "Storage", lambda dsn: _MockStorage())
    monkeypatch.setattr(
        hc, "assess_date", lambda *a, **k: (0, set(), "Đầy đủ: toàn bộ mã đều có bar.")
    )


def test_heartbeat_main_5m_exception_prints_stderr_and_continues(
    monkeypatch, tmp_path, capsys
):
    """5(i): Khối 5 phút ném exception thì tin của phép kiểm khác vẫn ra stdout,
    và stderr có '[WARN] heartbeat khong kiem duoc nen 5 phut'."""
    _setup_heartbeat_env(monkeypatch, tmp_path)

    def failing_alert(*args, **kwargs):
        raise RuntimeError("Simulated DB connection timeout")

    monkeypatch.setattr(hc, "prev_day_5m_alert", failing_alert)

    # Chạy dry-run
    rc = hc.main(["--logs-dir", str(tmp_path), "--dry-run"])
    assert rc == 0
    captured = capsys.readouterr()

    assert "[WARN] heartbeat khong kiem duoc nen 5 phut" in captured.err
    assert "Simulated DB connection timeout" in captured.err


def test_heartbeat_main_5m_dry_run_does_not_save_state(monkeypatch, tmp_path):
    """5(ii): --dry-run không tạo file trạng thái .prev_day_5m_state.json."""
    _setup_heartbeat_env(monkeypatch, tmp_path)

    state_file = tmp_path / PREV_DAY_5M_STATE_NAME
    assert not state_file.exists()

    rc = hc.main(["--logs-dir", str(tmp_path), "--dry-run"])
    assert rc == 1  # Có alert vì MONDAY_26 có 3 mã (< 137.6)
    assert not state_file.exists(), "--dry-run không được ghi file trạng thái"


def test_heartbeat_main_5m_saves_state_on_alert(monkeypatch, tmp_path):
    """5(iii): Chạy thật (không dry-run) có alert -> tạo file trạng thái lưu alerted_for."""
    _setup_heartbeat_env(monkeypatch, tmp_path)
    sent_msgs = []
    monkeypatch.setattr(
        hc, "send_telegram", lambda msg: bool(sent_msgs.append(msg)) or True
    )

    state_file = tmp_path / PREV_DAY_5M_STATE_NAME
    assert not state_file.exists()

    rc = hc.main(["--logs-dir", str(tmp_path)])
    assert rc == 1  # có cảnh báo
    assert state_file.exists(), "Phải ghi file trạng thái khi có cảnh báo"

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state.get("alerted_for") == "2026-10-26"
