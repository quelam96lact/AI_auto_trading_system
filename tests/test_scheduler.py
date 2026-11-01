"""Unit tests for trading.scheduler (Brief 201).

Kiem chung:
1. Tinh moc ke tiep theo gio VN (Thu Sau 22:00 -> Thu Hai 06:40; Chu nhat 10:00 -> Thu Hai 06:40;
   ngay le khong co 21:45; 06:40 chi T2-T6 khong phai ngay le).
2. Dinh dang log start/EXIT theo run_if_docker_up.sh (heartbeat_check doc duoc).
3. SKIP khi khong lay duoc advisory lock.
4. Job nem exception hoac timeout khong giet chet scheduler.
5. Xoay log giong log_rotate.sh.
"""

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
    calculate_next_event,
    rotate_log_if_needed,
    run_event,
    run_job,
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

    assert lines[0] == "2026-11-02 06:40:00 catchup start"
    assert "Hang 1: dang xu ly" in content
    assert "Hang 2: hoan tat" in content
    assert lines[-1] == "EXIT=0"

    # Kiem tra heartbeat_check doc duoc
    dt, exit_code, reason = get_last_run_exit_code(str(log_path), "catchup")
    assert reason is None
    assert dt == simulated_dt
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


def test_run_startup_and_run_event(tmp_path: Path):
    logs_dir = tmp_path / "logs"

    # Startup goi catchup
    _ = run_startup(
        logs_dir=logs_dir,
        lock_manager=mock_lock_acquired,
        python_exe=sys.executable,
    )
    assert (logs_dir / "catchup.log").exists()

    # Evening event goi catchup roi daily-data-check
    run_event(
        event_type="evening_jobs",
        logs_dir=logs_dir,
        lock_manager=mock_lock_acquired,
        python_exe=sys.executable,
    )
    assert (logs_dir / "daily-data-check.log").exists()


def test_scheduler_loop_once(tmp_path: Path, monkeypatch):
    """scheduler_loop chay startup roi 1 event roi thoat sach se khi once=True."""
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
