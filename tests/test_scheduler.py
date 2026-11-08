"""Unit tests for trading.scheduler (Brief 201).

Kiem chung:
1. Tinh moc ke tiep theo gio VN (Thu Sau 22:00 -> Thu Hai 06:40; Chu nhat 10:00 -> Thu Hai 06:40;
   ngay le khong co 21:45; 06:40 chi T2-T6 khong phai ngay le).
2. Dinh dang log start/EXIT theo run_if_docker_up.sh (heartbeat_check doc duoc).
3. SKIP khi khong lay duoc advisory lock.
4. Job nem exception hoac timeout khong giet chet scheduler.
5. Xoay log giong log_rotate.sh.
"""

import re
import sys
import threading
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from scripts.heartbeat_check import get_last_run_exit_code
from trading.calendar_vn import TZ
from trading.scheduler.main import (
    ADVISORY_LOCK_CATCHUP,
    ADVISORY_LOCK_DAILY_CHECK,
    CATCHUP_MAX_ATTEMPTS,
    CATCHUP_RETRY_DELAY_SEC,
    calculate_next_event,
    rotate_log_if_needed,
    run_event,
    run_job,
    run_job_with_retry,
    run_startup,
    scheduler_loop,
)

# ==============================================================================
# 1. Test tinh moc ke tiep theo gio VN
# ==============================================================================


def test_calculate_next_event_friday_night_to_monday():
    """Thu Sau 22:00 -> Thu Hai 06:40."""
    # 2026-10-30 la Thu Sau
    fri_2200 = datetime(2026, 10, 30, 22, 0, 0, tzinfo=TZ)
    target_dt, event_type = calculate_next_event(fri_2200)

    assert event_type == "morning_catchup"
    assert target_dt == datetime(2026, 11, 2, 6, 40, 0, tzinfo=TZ)  # Thu Hai


def test_calculate_next_event_sunday_morning_to_monday():
    """Chu nhat 10:00 -> Thu Hai 06:40."""
    # 2026-11-01 la Chu Nhat
    sun_1000 = datetime(2026, 11, 1, 10, 0, 0, tzinfo=TZ)
    target_dt, event_type = calculate_next_event(sun_1000)

    assert event_type == "morning_catchup"
    assert target_dt == datetime(2026, 11, 2, 6, 40, 0, tzinfo=TZ)


def test_calculate_next_event_saturday():
    """Thu Bay -> Thu Hai 06:40."""
    sat_1400 = datetime(2026, 10, 31, 14, 0, 0, tzinfo=TZ)
    target_dt, event_type = calculate_next_event(sat_1400)

    assert event_type == "morning_catchup"
    assert target_dt == datetime(2026, 11, 2, 6, 40, 0, tzinfo=TZ)


def test_calculate_next_event_holiday_skip():
    """Ngay le khong co 21:45; 06:40 cung khong chay ngay le."""
    holidays = {date(2026, 11, 2)}  # Thu Hai 02/11 la ngay le
    fri_2200 = datetime(2026, 10, 30, 22, 0, 0, tzinfo=TZ)

    target_dt, event_type = calculate_next_event(fri_2200, holidays=holidays)
    # Bo qua Thu Hai le, moc ke tiep la Thu Ba 03/11 06:40
    assert event_type == "morning_catchup"
    assert target_dt == datetime(2026, 11, 3, 6, 40, 0, tzinfo=TZ)

    # Trong ngay le (Thu Hai 05:00 hoac 10:00): nhay sang Thu Ba
    mon_holiday_0500 = datetime(2026, 11, 2, 5, 0, 0, tzinfo=TZ)
    target_dt2, event_type2 = calculate_next_event(mon_holiday_0500, holidays=holidays)
    assert event_type2 == "morning_catchup"
    assert target_dt2 == datetime(2026, 11, 3, 6, 40, 0, tzinfo=TZ)


def test_calculate_next_event_same_day_transitions():
    """Trong ngay giao dich:
    - Truoc 06:40 -> 06:40
    - Sau 06:40, truoc 21:45 -> 21:45
    - Sau 21:45 -> 06:40 ngay giao dich sau
    """
    mon_0500 = datetime(2026, 11, 2, 5, 0, 0, tzinfo=TZ)
    target_1, event_1 = calculate_next_event(mon_0500)
    assert target_1 == datetime(2026, 11, 2, 6, 40, 0, tzinfo=TZ)
    assert event_1 == "morning_catchup"

    mon_0645 = datetime(2026, 11, 2, 6, 45, 0, tzinfo=TZ)
    target_2, event_2 = calculate_next_event(mon_0645)
    assert target_2 == datetime(2026, 11, 2, 21, 45, 0, tzinfo=TZ)
    assert event_2 == "evening_jobs"

    mon_1500 = datetime(2026, 11, 2, 15, 0, 0, tzinfo=TZ)
    target_3, event_3 = calculate_next_event(mon_1500)
    assert target_3 == datetime(2026, 11, 2, 21, 45, 0, tzinfo=TZ)
    assert event_3 == "evening_jobs"

    mon_2200 = datetime(2026, 11, 2, 22, 0, 0, tzinfo=TZ)
    target_4, event_4 = calculate_next_event(mon_2200)
    assert target_4 == datetime(2026, 11, 3, 6, 40, 0, tzinfo=TZ)
    assert event_4 == "morning_catchup"


# ==============================================================================
# 2. Test dinh dang log start/EXIT va doc boi heartbeat_check
# ==============================================================================


@contextmanager
def mock_lock_acquired(_lock_id: int):
    yield True


@contextmanager
def mock_lock_denied(_lock_id: int):
    yield False


def test_run_job_log_format_and_heartbeat_check_compatibility(tmp_path: Path):
    """Log dung dinh dang run_if_docker_up.sh:
    <YYYY-mm-dd HH:MM:SS> <label> start
    <stdout/stderr>
    <YYYY-mm-dd HH:MM:SS> <label> finish dur=<dur>s
    EXIT=<rc>
    heartbeat_check doc duoc dung start_dt va exit_code.
    """
    logs_dir = tmp_path / "logs"
    simulated_dt = datetime(2026, 11, 2, 6, 40, 0, tzinfo=TZ)

    cmd = [
        sys.executable,
        "-c",
        "print('Hang 1: dang xu ly'); print('Hang 2: hoan tat')",
    ]

    rc = run_job(
        label="catchup",
        log_file="catchup.log",
        command=cmd,
        timeout_seconds=30,
        lock_id=ADVISORY_LOCK_CATCHUP,
        logs_dir=logs_dir,
        lock_manager=mock_lock_acquired,
        now_fn=lambda: simulated_dt,
    )

    assert rc == 0

    log_path = logs_dir / "catchup.log"
    content = log_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    start_idx = next(i for i, l in enumerate(lines) if l.endswith("catchup start"))
    finish_idx = next(i for i, l in enumerate(lines) if "catchup finish dur=" in l)
    exit_idx = next(i for i, l in enumerate(lines) if l == "EXIT=0")

    assert start_idx < finish_idx < exit_idx
    assert lines[0] == "2026-11-02 06:40:00 catchup start"
    assert "Hang 1: dang xu ly" in content
    assert "Hang 2: hoan tat" in content
    assert re.match(
        r"^2026-11-02 06:40:00 catchup finish dur=\d+\.\d{2}s$", lines[-2]
    )
    assert lines[-1] == "EXIT=0"

    # Kiem tra heartbeat_check doc duoc
    dt, exit_code, reason = get_last_run_exit_code(str(log_path), "catchup")
    assert reason is None
    assert dt == simulated_dt
    assert exit_code == 0


def test_heartbeat_check_compatibility_with_finish_dur_line(tmp_path: Path):
    """heartbeat_check doc log mau co dong finish dur= va van ra dung exit code."""
    sample_log = tmp_path / "universe-refresh.log"
    sample_log.write_text(
        "2026-11-02 21:45:10 universe-refresh start\n"
        "Lam moi danh muc: 1595 ma\n"
        "2026-11-02 21:55:30 universe-refresh finish dur=620.15s\n"
        "EXIT=0\n",
        encoding="utf-8",
    )
    dt, exit_code, reason = get_last_run_exit_code(
        str(sample_log), "universe-refresh"
    )
    assert reason is None
    assert dt == datetime(2026, 11, 2, 21, 45, 10, tzinfo=TZ)
    assert exit_code == 0


# ==============================================================================
# 3. Test SKIP khi khong lay duoc lock
# ==============================================================================


def test_run_job_skip_when_lock_not_acquired(tmp_path: Path):
    """Khi khong lay duoc lock:
    - Ghi dong <ts> <label> SKIP: dang co tien trinh khac
    - Khong chay subprocess
    - heartbeat_check nhan dien dung SKIP (exit_code = None, khong bao loi).
    """
    logs_dir = tmp_path / "logs"
    simulated_dt = datetime(2026, 11, 2, 6, 40, 0, tzinfo=TZ)

    cmd = [
        sys.executable,
        "-c",
        "import sys; sys.exit(99)",  # Neu chay thi rc=99
    ]

    rc = run_job(
        label="catchup",
        log_file="catchup.log",
        command=cmd,
        timeout_seconds=30,
        lock_id=ADVISORY_LOCK_CATCHUP,
        logs_dir=logs_dir,
        lock_manager=mock_lock_denied,
        now_fn=lambda: simulated_dt,
    )

    assert rc is None

    log_path = logs_dir / "catchup.log"
    content = log_path.read_text(encoding="utf-8")
    assert (
        content.strip() == "2026-11-02 06:40:00 catchup SKIP: dang co tien trinh khac"
    )

    _dt, exit_code, reason = get_last_run_exit_code(str(log_path), "catchup")
    assert reason is None
    # Quy tac cua get_last_run_exit_code: latest_event_is_skip -> exit_code = None
    assert exit_code is None


# ==============================================================================
# 4. Test timeout va exception khong giet scheduler
# ==============================================================================


def test_run_job_timeout_handling(tmp_path: Path):
    """Job treo qua timeout: kill tien trinh, ghi EXIT=124, khong quang exception."""
    logs_dir = tmp_path / "logs"
    simulated_dt = datetime(2026, 11, 2, 21, 45, 0, tzinfo=TZ)

    # Subprocess ngu 10s nhung timeout 1s
    cmd = [
        sys.executable,
        "-c",
        "import time; time.sleep(10)",
    ]

    rc = run_job(
        label="daily-data-check",
        log_file="daily-data-check.log",
        command=cmd,
        timeout_seconds=1,  # 1s timeout
        lock_id=ADVISORY_LOCK_DAILY_CHECK,
        logs_dir=logs_dir,
        lock_manager=mock_lock_acquired,
        now_fn=lambda: simulated_dt,
    )

    assert rc == 124

    log_path = logs_dir / "daily-data-check.log"
    content = log_path.read_text(encoding="utf-8")
    assert "2026-11-02 21:45:00 daily-data-check start" in content
    assert "TIMEOUT" in content
    assert "EXIT=124" in content


def test_run_job_exception_handling(tmp_path: Path):
    """Lenh loi (vd executable khong ton tai): khong quang exception, tra ve ma loi."""
    logs_dir = tmp_path / "logs"

    rc = run_job(
        label="catchup",
        log_file="catchup.log",
        command=["/khong/ton/tai/lenh_nay_12345"],
        timeout_seconds=5,
        lock_id=ADVISORY_LOCK_CATCHUP,
        logs_dir=logs_dir,
        lock_manager=mock_lock_acquired,
    )

    assert rc == 1
    log_path = logs_dir / "catchup.log"
    content = log_path.read_text(encoding="utf-8")
    assert "ERROR" in content
    assert "EXIT=1" in content


# ==============================================================================
# 5. Test log rotation giong scripts/log_rotate.sh
# ==============================================================================


def test_rotate_log_if_needed(tmp_path: Path):
    log_path = tmp_path / "test.log"
    # Tao file 1.5 KB voi nguong 1 KB
    log_path.write_bytes(b"A" * 1500)

    rotate_log_if_needed(log_path, max_bytes=1000, keep=3)

    assert not log_path.exists()
    assert (tmp_path / "test.log.1").exists()
    assert (tmp_path / "test.log.1").stat().st_size == 1500

    # Tao file moi va xoay tiep
    log_path.write_bytes(b"B" * 1500)
    rotate_log_if_needed(log_path, max_bytes=1000, keep=3)

    assert (tmp_path / "test.log.1").stat().st_size == 1500
    assert (tmp_path / "test.log.2").exists()


# ==============================================================================
# 6. Test run_startup, run_event, scheduler_loop
# ==============================================================================


def test_run_startup_and_run_event(tmp_path: Path, monkeypatch):
    executed_labels = []
    import trading.scheduler.main as sm

    monkeypatch.setattr(sm, "CATCHUP_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(sm, "CATCHUP_RETRY_DELAY_SEC", 0.0)

    orig_run_job = sm.run_job

    def spy_run_job(*args, **kwargs):
        label = kwargs.get("label", args[0] if args else None)
        executed_labels.append(label)
        # Chuyển tiếp logs_dir vào command của daily_data_check để không ghi outbox vào logs/ thật
        if "command" in kwargs and "logs_dir" in kwargs:
            cmd = list(kwargs["command"])
            if any("daily_data_check.py" in str(arg) for arg in cmd):
                cmd.extend(["--logs-dir", str(kwargs["logs_dir"])])
                kwargs["command"] = cmd
        return orig_run_job(*args, **kwargs)

    monkeypatch.setattr(sm, "run_job", spy_run_job)

    # Startup goi catchup
    startup_logs_dir = tmp_path / "startup_logs"
    _ = run_startup(
        logs_dir=startup_logs_dir,
        lock_manager=mock_lock_acquired,
        python_exe=sys.executable,
    )
    assert (startup_logs_dir / "catchup.log").exists()
    assert executed_labels == ["catchup"]

    # Morning event chi goi catchup
    executed_labels.clear()
    morning_logs_dir = tmp_path / "morning_logs"
    run_event(
        event_type="morning_catchup",
        logs_dir=morning_logs_dir,
        lock_manager=mock_lock_acquired,
        python_exe=sys.executable,
    )
    assert (morning_logs_dir / "catchup.log").exists()
    assert not (morning_logs_dir / "daily-data-check.log").exists()
    assert not (morning_logs_dir / "universe-refresh.log").exists()
    assert executed_labels == ["catchup"]

    # Evening event goi ca 3 job theo thu tu: catchup -> daily-data-check -> universe-refresh
    executed_labels.clear()
    evening_logs_dir = tmp_path / "evening_logs"
    run_event(
        event_type="evening_jobs",
        logs_dir=evening_logs_dir,
        lock_manager=mock_lock_acquired,
        python_exe=sys.executable,
    )
    assert (evening_logs_dir / "catchup.log").exists()
    assert (evening_logs_dir / "daily-data-check.log").exists()
    assert (evening_logs_dir / "universe-refresh.log").exists()
    assert executed_labels == ["catchup", "daily-data-check", "universe-refresh"]
    evening_catchup_log = (evening_logs_dir / "catchup.log").read_text(
        encoding="utf-8"
    )
    assert "ngay khong giao dich theo SSI" not in evening_catchup_log


def test_scheduler_loop_once(tmp_path: Path, monkeypatch):
    """scheduler_loop chay startup roi 1 event roi thoat sach se khi once=True."""
    import trading.scheduler.main as sm

    monkeypatch.setattr(sm, "CATCHUP_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(sm, "CATCHUP_RETRY_DELAY_SEC", 0.0)

    logs_dir = tmp_path / "logs"
    # Subprocess that chay `python -m scripts.startup_catchup` voi cwd=tmp_path:
    # khong duoc de PYTHONPATH tro ve repo, neu khong test se chay catchup THAT.
    monkeypatch.delenv("PYTHONPATH", raising=False)

    # Dong ho tat dinh (KHONG dung thread doi gio: startup chay subprocess lau hon
    # 0,1s thi dong ho da qua 06:40 truoc khi tinh moc -> moc thanh 21:45 -> treo).
    # Lan goi dau (tinh moc) = 06:39:59; moi lan sau = 06:40:01.
    calls = [0]

    def mock_now():
        calls[0] += 1
        if calls[0] == 1:
            return datetime(2026, 11, 2, 6, 39, 59, tzinfo=TZ)
        return datetime(2026, 11, 2, 6, 40, 1, tzinfo=TZ)

    stop_event = threading.Event()

    scheduler_loop(
        logs_dir=logs_dir,
        cwd=tmp_path,
        stop_event=stop_event,
        lock_manager=mock_lock_acquired,
        python_exe=sys.executable,
        skip_startup=False,
        once=True,
        now_fn=mock_now,
    )

    assert (logs_dir / "catchup.log").exists()
    # startup + luot 06:40 = hai lan chay catchup
    assert (logs_dir / "catchup.log").read_text(encoding="utf-8").count(
        " catchup start"
    ) == 2


# ==============================================================================
# 7. Test catchup retry handling (Task 2 Brief 215)
# ==============================================================================


def test_run_job_with_retry_rc_1_then_0():
    """rc [1, 0]: chay 2 lan, sleep 1 lan voi 300."""
    sleeps = []
    runs = []
    rc_iter = iter([1, 0])

    def fake_runner(**kwargs):
        runs.append(kwargs.get("label"))
        return next(rc_iter)

    rc = run_job_with_retry(
        label="catchup",
        log_file="catchup.log",
        command=["fake"],
        timeout_seconds=10,
        lock_id=ADVISORY_LOCK_CATCHUP,
        logs_dir=Path("/fake"),
        sleep_fn=lambda s: sleeps.append(s),
        runner_fn=fake_runner,
    )
    assert rc == 0
    assert len(runs) == 2
    assert sleeps == [300.0]


def test_run_job_with_retry_rc_2_all():
    """rc [2, 2, 2]: chay 3 lan, tra ve 2, sleep 2 lan voi 300."""
    sleeps = []
    runs = []
    rc_iter = iter([2, 2, 2])

    def fake_runner(**kwargs):
        runs.append(kwargs.get("label"))
        return next(rc_iter)

    rc = run_job_with_retry(
        label="catchup",
        log_file="catchup.log",
        command=["fake"],
        timeout_seconds=10,
        lock_id=ADVISORY_LOCK_CATCHUP,
        logs_dir=Path("/fake"),
        sleep_fn=lambda s: sleeps.append(s),
        runner_fn=fake_runner,
    )
    assert rc == 2
    assert len(runs) == 3
    assert sleeps == [300.0, 300.0]


def test_run_job_with_retry_rc_0_once():
    """rc [0]: chay 1 lan, khong sleep."""
    sleeps = []
    runs = []

    def fake_runner(**kwargs):
        runs.append(kwargs.get("label"))
        return 0

    rc = run_job_with_retry(
        label="catchup",
        log_file="catchup.log",
        command=["fake"],
        timeout_seconds=10,
        lock_id=ADVISORY_LOCK_CATCHUP,
        logs_dir=Path("/fake"),
        sleep_fn=lambda s: sleeps.append(s),
        runner_fn=fake_runner,
    )
    assert rc == 0
    assert len(runs) == 1
    assert sleeps == []


def test_catchup_constants():
    """Kiem tra hang so retry cua catchup (Task 2 Brief 215)."""
    assert CATCHUP_MAX_ATTEMPTS == 3
    assert CATCHUP_RETRY_DELAY_SEC == 300.0


def test_run_job_with_retry_rc_none_once():
    """rc [None] (SKIP): chay 1 lan, khong sleep."""
    sleeps = []
    runs = []

    def fake_runner(**kwargs):
        runs.append(kwargs.get("label"))
        val: int | None = None
        return val

    rc = run_job_with_retry(
        label="catchup",
        log_file="catchup.log",
        command=["fake"],
        timeout_seconds=10,
        lock_id=ADVISORY_LOCK_CATCHUP,
        logs_dir=Path("/fake"),
        sleep_fn=lambda s: sleeps.append(s),
        runner_fn=fake_runner,
    )
    assert rc is None
    assert len(runs) == 1
    assert sleeps == []


def test_run_job_with_retry_rc_124_once():
    """rc [124] (timeout 3 gio): chay 1 lan, khong sleep."""
    sleeps = []
    runs = []

    def fake_runner(**kwargs):
        runs.append(kwargs.get("label"))
        return 124

    rc = run_job_with_retry(
        label="catchup",
        log_file="catchup.log",
        command=["fake"],
        timeout_seconds=10,
        lock_id=ADVISORY_LOCK_CATCHUP,
        logs_dir=Path("/fake"),
        sleep_fn=lambda s: sleeps.append(s),
        runner_fn=fake_runner,
    )
    assert rc == 124
    assert len(runs) == 1
    assert sleeps == []


def test_evening_jobs_continues_when_catchup_fails():
    """evening_jobs voi catchup luon bang 1: daily-check va universe-refresh van duoc goi."""
    executed = []

    def fake_runner(**kwargs):
        label = kwargs.get("label")
        executed.append(label)
        if label == "catchup":
            return 1
        return 0

    run_event(
        event_type="evening_jobs",
        logs_dir=Path("/fake"),
        sleep_fn=lambda _: None,
        runner_fn=fake_runner,
    )
    assert executed == [
        "catchup",
        "catchup",
        "catchup",
        "daily-data-check",
        "universe-refresh",
    ]


# ==============================================================================
# 8. Test Scheduler Alerting on Job Failure (Task 3 Brief 217)
# ==============================================================================


def test_catchup_alert_on_all_retries_failed():
    """catchup [1, 1, 1]: gui 1 tin canh bao voi catchup va so lan thu 3."""
    alerts = []
    rc_iter = iter([1, 1, 1])

    def fake_runner(**kwargs):
        return next(rc_iter)

    rc = run_startup(
        logs_dir=Path("/fake"),
        sleep_fn=lambda _: None,
        runner_fn=fake_runner,
        alert_fn=alerts.append,
    )
    assert rc == 1
    assert len(alerts) == 1
    assert "catchup" in alerts[0]
    assert "số lần thử: 3" in alerts[0]
    assert "logs/catchup.log" in alerts[0]
    assert "VN" in alerts[0]


def test_catchup_no_alert_when_retry_succeeds():
    """catchup [1, 0]: thanh cong o lan thu 2, khong gui canh bao."""
    alerts = []
    rc_iter = iter([1, 0])

    def fake_runner(**kwargs):
        return next(rc_iter)

    rc = run_startup(
        logs_dir=Path("/fake"),
        sleep_fn=lambda _: None,
        runner_fn=fake_runner,
        alert_fn=alerts.append,
    )
    assert rc == 0
    assert alerts == []


def test_catchup_no_alert_on_lock_skip():
    """catchup [None] (SKIP vi tien trinh khac dang giu lock): khong gui canh bao."""
    alerts = []

    def fake_runner(**kwargs):
        return None

    rc = run_startup(
        logs_dir=Path("/fake"),
        sleep_fn=lambda _: None,
        runner_fn=fake_runner,
        alert_fn=alerts.append,
    )
    assert rc is None
    assert alerts == []


def test_evening_jobs_alerts_on_daily_check_failure():
    """evening_jobs: catchup ok, daily-data-check loi rc=1 -> gui 1 tin cho daily-data-check."""
    alerts = []

    def fake_runner(**kwargs):
        label = kwargs.get("label")
        if label == "daily-data-check":
            return 1
        return 0

    run_event(
        event_type="evening_jobs",
        logs_dir=Path("/fake"),
        sleep_fn=lambda _: None,
        runner_fn=fake_runner,
        alert_fn=alerts.append,
    )
    assert len(alerts) == 1
    assert "daily-data-check" in alerts[0]
    assert "logs/daily-data-check.log" in alerts[0]
    assert "số lần thử: 1" in alerts[0]


def test_evening_jobs_alerts_on_universe_refresh_failure():
    """evening_jobs: catchup ok, daily-check ok, universe-refresh rc=2 -> gui 1 tin."""
    alerts = []

    def fake_runner(**kwargs):
        label = kwargs.get("label")
        if label == "universe-refresh":
            return 2
        return 0

    run_event(
        event_type="evening_jobs",
        logs_dir=Path("/fake"),
        sleep_fn=lambda _: None,
        runner_fn=fake_runner,
        alert_fn=alerts.append,
    )
    assert len(alerts) == 1
    assert "universe-refresh" in alerts[0]
    assert "logs/universe-refresh.log" in alerts[0]
    assert "rc=2" in alerts[0]


def test_alert_exception_does_not_crash_scheduler():
    """Loi nem ra trong alert_fn khong duoc lam sap scheduler."""

    def exploding_alert(msg: str):
        raise RuntimeError("Telegram network down")

    def fake_runner(**kwargs):
        return 1

    # Khong nem exception
    run_event(
        event_type="evening_jobs",
        logs_dir=Path("/fake"),
        sleep_fn=lambda _: None,
        runner_fn=fake_runner,
        alert_fn=exploding_alert,
    )


def test_run_job_with_retry_actual_attempts_counted():
    """run_job_with_retry tra ve dung so lan attempts thuc su chay."""
    rc_iter = iter([1, 2])

    def fake_runner(**kwargs):
        return next(rc_iter)

    rc, attempts = run_job_with_retry(
        label="catchup",
        log_file="catchup.log",
        command=["fake"],
        timeout_seconds=10,
        lock_id=ADVISORY_LOCK_CATCHUP,
        logs_dir=Path("/fake"),
        max_attempts=2,
        sleep_fn=lambda _: None,
        runner_fn=fake_runner,
        return_attempts=True,
    )
    assert rc == 2
    assert attempts == 2


