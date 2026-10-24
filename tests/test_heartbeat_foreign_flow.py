"""Unit tests cho Brief 190b: phép kiểm số dòng khối ngoại ngày liền trước trong heartbeat.

Bao gồm:
- 8 ca kiểm chứng cho prev_day_foreign_flow_alert theo §3 Bước 4
- Các ca kiểm chứng nối vào main theo §3 Bước 5 (bọc try/except, --dry-run không ghi state, v.v.)
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import scripts.heartbeat_check as hc
from scripts.heartbeat_check import (
    PREV_DAY_FOREIGN_FLOW_STATE_NAME,
    prev_day_foreign_flow_alert,
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

    def read_foreign_flow_day_counts(self, frm: date, to: date) -> dict[date, int]:
        return {d: c for d, c in self._counts.items() if frm <= d <= to}


# ============ Bước 4: prev_day_foreign_flow_alert ============


def test_prev_day_foreign_flow_alert_1550_no_alert():
    """4.1: n_P = 1550, 5 phiên trước đều 1557: không báo (1550 >= 0.8 * 1557 = 1245.6)."""
    counts = {d: 1557 for d in PRIOR_5_DAYS}
    counts[MONDAY_26] = 1550
    storage = FakeStorage(counts)

    tin, p_iso = prev_day_foreign_flow_alert(storage, TUESDAY_27, frozenset(), None)
    assert tin is None
    assert p_iso == "2026-10-26"


def test_prev_day_foreign_flow_alert_0_alerts():
    """4.2: n_P = 0: báo, tin chứa '2026-10-26' và 'sched.sh foreign-flow'."""
    counts = {d: 1557 for d in PRIOR_5_DAYS}
    counts[MONDAY_26] = 0
    storage = FakeStorage(counts)

    tin, p_iso = prev_day_foreign_flow_alert(storage, TUESDAY_27, frozenset(), None)
    assert tin is not None
    assert p_iso == "2026-10-26"
    assert "2026-10-26" in tin
    assert "sched.sh foreign-flow" in tin
    assert "[WARN]" in tin
    assert "(idempotent)" in tin


def test_prev_day_foreign_flow_alert_1000_alerts():
    """4.3: n_P = 1000, 5 phiên trước đều 1557: báo, vì 1000 < 0.8 * 1557 = 1245.6."""
    counts = {d: 1557 for d in PRIOR_5_DAYS}
    counts[MONDAY_26] = 1000
    storage = FakeStorage(counts)

    tin, p_iso = prev_day_foreign_flow_alert(storage, TUESDAY_27, frozenset(), None)
    assert tin is not None
    assert p_iso == "2026-10-26"
    assert "1000 dòng" in tin
    assert "1557" in tin


def test_prev_day_foreign_flow_alert_1300_no_alert():
    """4.4: n_P = 1300: không báo, vì 1300 >= 1245.6."""
    counts = {d: 1557 for d in PRIOR_5_DAYS}
    counts[MONDAY_26] = 1300
    storage = FakeStorage(counts)

    tin, p_iso = prev_day_foreign_flow_alert(storage, TUESDAY_27, frozenset(), None)
    assert tin is None
    assert p_iso == "2026-10-26"


def test_prev_day_foreign_flow_alert_median_not_min():
    """4.5: Trung vị chứ không phải min: 5 phiên trước [1557, 1557, 1557, 1557, 10]
    và n_P = 1000 thì vẫn báo (trung vị = 1557 > 1250, min = 10 < 1000)."""
    counts = {
        PRIOR_5_DAYS[0]: 1557,
        PRIOR_5_DAYS[1]: 1557,
        PRIOR_5_DAYS[2]: 1557,
        PRIOR_5_DAYS[3]: 1557,
        PRIOR_5_DAYS[4]: 10,
        MONDAY_26: 1000,
    }
    storage = FakeStorage(counts)

    tin, _p_iso = prev_day_foreign_flow_alert(storage, TUESDAY_27, frozenset(), None)
    assert tin is not None, "Phải báo vì trung vị là 1557 và 1000 < 0.8 * 1557"
    assert "1557" in tin


def test_prev_day_foreign_flow_alert_already_alerted_silent():
    """4.6: alerted_for == '2026-10-26': không báo (tránh spam)."""
    counts = {d: 1557 for d in PRIOR_5_DAYS}
    counts[MONDAY_26] = 0
    storage = FakeStorage(counts)

    tin, p_iso = prev_day_foreign_flow_alert(
        storage, TUESDAY_27, frozenset(), alerted_for="2026-10-26"
    )
    assert tin is None
    assert p_iso == "2026-10-26"


def test_prev_day_foreign_flow_alert_empty_table_before_p_silent():
    """4.7: Bảng rỗng trước P: không báo (tránh báo giả trước khi nạp lịch sử)."""
    # Chỉ có dòng của chính ngày P hoặc không có gì trước P
    counts = {MONDAY_26: 0}
    storage = FakeStorage(counts)

    tin, p_iso = prev_day_foreign_flow_alert(storage, TUESDAY_27, frozenset(), None)
    assert tin is None
    assert p_iso == "2026-10-26"

    # Hoàn toàn rỗng
    empty_storage = FakeStorage({})
    tin_empty, p_iso_empty = prev_day_foreign_flow_alert(
        empty_storage, TUESDAY_27, frozenset(), None
    )
    assert tin_empty is None
    assert p_iso_empty == "2026-10-26"


def test_prev_day_foreign_flow_alert_monday_p_is_friday():
    """4.8: now là thứ Hai 26/10 thì P = thứ Sáu 23/10 (qua cuối tuần)."""
    now_monday = datetime(2026, 10, 26, 9, 0, 0, tzinfo=TZ)
    friday_23 = date(2026, 10, 23)

    counts = {friday_23: 1550, date(2026, 10, 22): 1557}
    storage = FakeStorage(counts)

    _tin, p_iso = prev_day_foreign_flow_alert(storage, now_monday, frozenset(), None)
    assert p_iso == "2026-10-23"


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
        (tmp_path / job.log_file).write_text(f"{stamp} {job.label} start\n", encoding="utf-8")

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
                return type("C", (), {
                    "fetchall": lambda s: [
                        ("collector", fixed_now - timedelta(seconds=30)),
                        ("engine", fixed_now - timedelta(seconds=45)),
                    ]
                })()
            if "max(ts) FROM bars" in q:
                return type("C", (), {"fetchone": lambda s: (fixed_now - timedelta(minutes=2),)})()
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
            return {d: 1557 for d in PRIOR_5_DAYS} | {MONDAY_26: 0}

    monkeypatch.setattr(hc, "Storage", lambda dsn: _MockStorage())
    # Fake daily_data_check assess_date to return OK
    monkeypatch.setattr(
        hc, "assess_date", lambda *a, **k: (0, set(), "Đầy đủ: toàn bộ mã đều có bar.")
    )


def test_heartbeat_main_foreign_flow_exception_prints_stderr_and_continues(
    monkeypatch, tmp_path, capsys
):
    """5(i): Khối khối ngoại ném exception thì tin của phép kiểm khác vẫn ra stdout,
    và stderr có '[WARN] heartbeat khong kiem duoc khoi ngoai'."""
    _setup_heartbeat_env(monkeypatch, tmp_path)

    def failing_alert(*args, **kwargs):
        raise RuntimeError("Simulated DB connection timeout")

    monkeypatch.setattr(hc, "prev_day_foreign_flow_alert", failing_alert)

    # Chạy dry-run
    rc = hc.main(["--logs-dir", str(tmp_path), "--dry-run"])
    assert rc == 0
    captured = capsys.readouterr()

    # Phép kiểm hỏng in ra stderr và không làm chết tiến trình
    assert "[WARN] heartbeat khong kiem duoc khoi ngoai" in captured.err
    assert "Simulated DB connection timeout" in captured.err


def test_heartbeat_main_foreign_flow_dry_run_does_not_save_state(
    monkeypatch, tmp_path
):
    """5(ii): --dry-run không tạo file trạng thái .prev_day_foreign_flow_state.json."""
    _setup_heartbeat_env(monkeypatch, tmp_path)

    state_file = tmp_path / PREV_DAY_FOREIGN_FLOW_STATE_NAME
    assert not state_file.exists()

    rc = hc.main(["--logs-dir", str(tmp_path), "--dry-run"])
    assert rc == 1  # Có alert vì MONDAY_26 có 0 dòng
    assert not state_file.exists(), "--dry-run không được ghi file trạng thái"


def test_heartbeat_main_foreign_flow_saves_state_on_alert(monkeypatch, tmp_path):
    """5(iii): Chạy thật (không dry-run) có alert -> tạo file trạng thái lưu alerted_for."""
    _setup_heartbeat_env(monkeypatch, tmp_path)
    sent_msgs = []
    monkeypatch.setattr(hc, "send_telegram", lambda msg: bool(sent_msgs.append(msg)) or True)

    state_file = tmp_path / PREV_DAY_FOREIGN_FLOW_STATE_NAME
    assert not state_file.exists()

    rc = hc.main(["--logs-dir", str(tmp_path)])
    assert rc == 1  # có cảnh báo
    assert state_file.exists(), "Phải ghi file trạng thái khi có cảnh báo"

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state.get("alerted_for") == "2026-10-26"
