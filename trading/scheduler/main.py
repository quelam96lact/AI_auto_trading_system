"""Scheduler daemon inside Docker (Brief 201).

Tu dong chay catchup khi khoi dong va dinh ky theo gio VN:
- 06:40 T2-T6 (ngay giao dich): catchup
- 21:45 ngay giao dich: catchup roi daily-check
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import threading
import time as time_module
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import yaml

from trading.alerts import alert, start_outbox
from trading.calendar_vn import TZ, is_trading_day

logger = logging.getLogger("trading.scheduler")

# Advisory lock IDs for pg_try_advisory_lock
ADVISORY_LOCK_CATCHUP = 2026110101
ADVISORY_LOCK_DAILY_CHECK = 2026110102

# Job timeouts
TIMEOUT_CATCHUP_SECONDS = 3 * 3600  # 3 hours (10,800s)
TIMEOUT_DAILY_CHECK_SECONDS = 30 * 60  # 30 minutes (1,800s)
TIMEOUT_UNIVERSE_REFRESH_SECONDS = 3600  # 1 hour (3,600s)

# Retry settings for catchup
CATCHUP_MAX_ATTEMPTS = 3
CATCHUP_RETRY_DELAY_SEC = 300.0

# Schedule times
MORNING_CATCHUP_TIME = time(6, 40)
EVENING_JOBS_TIME = time(21, 45)

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_holidays(config_path: str | Path = "config/config.yaml") -> set[date]:
    """Doc danh sach ngay le tu config.yaml."""
    p = Path(config_path)
    if not p.is_file():
        p = REPO_ROOT / config_path
    if not p.is_file():
        return set()
    try:
        with open(p, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return {date.fromisoformat(str(h)) for h in raw.get("holidays", [])}
    except Exception as e:
        logger.warning("Khong the doc holidays tu %s: %s", config_path, e)
        return set()


def rotate_log_if_needed(
    log_path: Path, max_bytes: int = 1_048_576, keep: int = 5
) -> None:
    """Xoay log theo kich thuoc giong scripts/log_rotate.sh.

    Moi loi xoay deu bi nuot de khong bao gio chan viec ghi log.
    """
    try:
        if not log_path.is_file():
            return
        if log_path.stat().st_size < max_bytes:
            return

        oldest = log_path.with_name(f"{log_path.name}.{keep}")
        if oldest.exists():
            try:
                oldest.unlink()
            except OSError:
                pass

        for i in range(keep - 1, 0, -1):
            src = log_path.with_name(f"{log_path.name}.{i}")
            dst = log_path.with_name(f"{log_path.name}.{i + 1}")
            if src.exists():
                try:
                    src.replace(dst)
                except OSError:
                    pass

        target = log_path.with_name(f"{log_path.name}.1")
        log_path.replace(target)
    except Exception:
        pass


@contextmanager
def pg_advisory_lock(dsn: str | None, lock_id: int) -> Iterator[bool]:
    """Context manager lay session advisory lock tren PostgreSQL bang pg_try_advisory_lock."""
    if not dsn:
        yield False
        return

    import psycopg

    conn = None
    acquired = False
    try:
        conn = psycopg.connect(dsn, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s);", (lock_id,))
            row = cur.fetchone()
            acquired = bool(row and row[0])
        yield acquired
    finally:
        if acquired and conn is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s);", (lock_id,))
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def run_job(
    label: str,
    log_file: str,
    command: list[str],
    timeout_seconds: int,
    lock_id: int,
    logs_dir: Path,
    cwd: Path | None = None,
    dsn: str | None = None,
    lock_manager: Callable[[int], AbstractContextManager[bool]] | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> int | None:
    """Chay mot job va ghi log dung dinh dang run_if_docker_up.sh cho heartbeat_check doc."""
    now_dt = (now_fn() if now_fn else datetime.now(TZ)).astimezone(TZ)
    ts = now_dt.strftime("%Y-%m-%d %H:%M:%S")

    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / log_file
    rotate_log_if_needed(log_path)

    ctx = lock_manager(lock_id) if lock_manager is not None else pg_advisory_lock(dsn, lock_id)

    try:
        with ctx as acquired:
            if not acquired:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"{ts} {label} SKIP: dang co tien trinh khac\n")
                logger.info("%s SKIP: dang co tien trinh khac", label)
                return None

            t0 = time_module.monotonic()
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{ts} {label} start\n")
                f.flush()

                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"

                effective_cwd = (
                    str(cwd)
                    if cwd is not None
                    else (str(REPO_ROOT) if REPO_ROOT.exists() else None)
                )

                rc = 1
                try:
                    proc = subprocess.Popen(
                        command,
                        stdout=f,
                        stderr=subprocess.STDOUT,
                        cwd=effective_cwd,
                        env=env,
                    )
                    try:
                        rc = proc.wait(timeout=timeout_seconds)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                        f.write(
                            f"\n[scheduler] TIMEOUT sau {timeout_seconds}s: da kill tien trinh\n"
                        )
                        rc = 124
                except Exception as e:
                    f.write(f"\n[scheduler] ERROR khi chay tien trinh: {e}\n")
                    rc = 1

                dur = time_module.monotonic() - t0
                finish_dt = (now_fn() if now_fn else datetime.now(TZ)).astimezone(TZ)
                finish_ts = finish_dt.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{finish_ts} {label} finish dur={dur:.2f}s\n")
                f.write(f"EXIT={rc}\n")
                f.flush()
                logger.info("%s finish with EXIT=%d dur=%.2fs", label, rc, dur)
                return rc
    except Exception as e:
        logger.error("Loi ngoai le khi chay job %s: %s", label, e)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{ts} {label} ERROR: {e}\n")
                f.write("EXIT=2\n")
        except Exception:
            pass
        return 2


def run_job_with_retry(
    label: str,
    log_file: str,
    command: list[str],
    timeout_seconds: int,
    lock_id: int,
    logs_dir: Path,
    cwd: Path | None = None,
    dsn: str | None = None,
    lock_manager: Callable[[int], AbstractContextManager[bool]] | None = None,
    now_fn: Callable[[], datetime] | None = None,
    max_attempts: int | None = None,
    retry_delay_sec: float | None = None,
    sleep_fn: Callable[[float], Any] = time_module.sleep,
    runner_fn: Callable[..., int | None] | None = None,
    return_attempts: bool = False,
) -> int | None | tuple[int | None, int]:
    """Boc run_job de tu thu lai toi da max_attempts lan khi rc la 1 hoac 2.

    Khong thu lai khi rc la 0, None (SKIP) hoac 124 (timeout).
    Neu return_attempts=True, tra ve (last_rc, actual_attempts).
    """
    fn = runner_fn if runner_fn is not None else run_job
    eff_max = max_attempts if max_attempts is not None else CATCHUP_MAX_ATTEMPTS
    eff_delay = (
        retry_delay_sec if retry_delay_sec is not None else CATCHUP_RETRY_DELAY_SEC
    )
    last_rc: int | None = None
    actual_attempts = 0
    for attempt in range(1, eff_max + 1):
        actual_attempts = attempt
        last_rc = fn(
            label=label,
            log_file=log_file,
            command=command,
            timeout_seconds=timeout_seconds,
            lock_id=lock_id,
            logs_dir=logs_dir,
            cwd=cwd,
            dsn=dsn,
            lock_manager=lock_manager,
            now_fn=now_fn,
        )
        if last_rc not in (1, 2):
            break
        if attempt < eff_max:
            logger.warning(
                "%s that bai (rc=%s), thu lai lan %d/%d sau %.0fs...",
                label,
                last_rc,
                attempt + 1,
                eff_max,
                eff_delay,
            )
            sleep_fn(eff_delay)
    if return_attempts:
        return last_rc, actual_attempts
    return last_rc


def notify_job_failure(
    label: str,
    rc: int,
    attempts: int,
    log_file: str,
    alert_fn: Callable[[str], Any] | None = None,
) -> None:
    """Gui canh bao khi scheduler job that bai.

    Khong bao gio nem exception lam chet scheduler loop.
    """
    time_str = datetime.now(TZ).strftime("%H:%M:%S %d/%m/%Y")
    msg = (
        f"Scheduler job thất bại: {label} (rc={rc}, số lần thử: {attempts}). "
        f"Xem log: logs/{log_file} ({time_str} VN)"
    )
    try:
        if alert_fn is not None:
            alert_fn(msg)
        else:
            alert("CRITICAL", msg)
    except Exception as e:
        logger.warning("Khong the gui canh bao scheduler cho job %s: %s", label, e)


def calculate_next_event(
    now: datetime,
    holidays: set[date] | frozenset[date] = frozenset(),
) -> tuple[datetime, str]:
    """Tinh moc thoi gian ke tiep va loai su kien theo gio VN (trading.calendar_vn.TZ).

    Cac moc trong ngay giao dich (T2-T6, khong phai ngay le):
    - 06:40: "morning_catchup"
    - 21:45: "evening_jobs"
    """
    if now.tzinfo is None:
        now_vn = now.replace(tzinfo=TZ)
    else:
        now_vn = now.astimezone(TZ)

    cur_date = now_vn.date()

    if is_trading_day(cur_date, holidays):
        morning_dt = datetime.combine(cur_date, MORNING_CATCHUP_TIME, tzinfo=TZ)
        if now_vn < morning_dt:
            return morning_dt, "morning_catchup"

        evening_dt = datetime.combine(cur_date, EVENING_JOBS_TIME, tzinfo=TZ)
        if now_vn < evening_dt:
            return evening_dt, "evening_jobs"

    # Ngay hien tai khong con moc nao (qua 21:45 hoac khong phai ngay giao dich),
    # tim ngay giao dich tiep theo
    check_date = cur_date + timedelta(days=1)
    while not is_trading_day(check_date, holidays):
        check_date += timedelta(days=1)

    next_morning = datetime.combine(check_date, MORNING_CATCHUP_TIME, tzinfo=TZ)
    return next_morning, "morning_catchup"


def run_startup(
    logs_dir: Path,
    cwd: Path | None = None,
    dsn: str | None = None,
    lock_manager: Callable[[int], AbstractContextManager[bool]] | None = None,
    python_exe: str = sys.executable,
    sleep_fn: Callable[[float], Any] = time_module.sleep,
    runner_fn: Callable[..., int | None] | None = None,
    alert_fn: Callable[[str], Any] | None = None,
) -> int | None:
    """Chay catchup ngay khi khoi dong (co tu thu lai toi da 3 lan)."""
    logger.info("Chay startup catchup...")
    command = [python_exe, "-m", "scripts.startup_catchup"]
    res = run_job_with_retry(
        label="catchup",
        log_file="catchup.log",
        command=command,
        timeout_seconds=TIMEOUT_CATCHUP_SECONDS,
        lock_id=ADVISORY_LOCK_CATCHUP,
        logs_dir=logs_dir,
        cwd=cwd,
        dsn=dsn,
        lock_manager=lock_manager,
        sleep_fn=sleep_fn,
        runner_fn=runner_fn,
        return_attempts=True,
    )
    rc, attempts = res  # type: ignore[misc]
    if rc is not None and rc != 0:
        notify_job_failure(
            label="catchup",
            rc=rc,
            attempts=attempts,
            log_file="catchup.log",
            alert_fn=alert_fn,
        )
    return rc


def run_event(
    event_type: str,
    logs_dir: Path,
    cwd: Path | None = None,
    dsn: str | None = None,
    lock_manager: Callable[[int], AbstractContextManager[bool]] | None = None,
    python_exe: str = sys.executable,
    sleep_fn: Callable[[float], Any] = time_module.sleep,
    runner_fn: Callable[..., int | None] | None = None,
    alert_fn: Callable[[str], Any] | None = None,
) -> None:
    """Thuc thi su kien theo lich."""
    if event_type == "morning_catchup":
        logger.info("Chay lich 06:40 (catchup)...")
        command = [python_exe, "-m", "scripts.startup_catchup"]
        res = run_job_with_retry(
            label="catchup",
            log_file="catchup.log",
            command=command,
            timeout_seconds=TIMEOUT_CATCHUP_SECONDS,
            lock_id=ADVISORY_LOCK_CATCHUP,
            logs_dir=logs_dir,
            cwd=cwd,
            dsn=dsn,
            lock_manager=lock_manager,
            sleep_fn=sleep_fn,
            runner_fn=runner_fn,
            return_attempts=True,
        )
        rc, attempts = res  # type: ignore[misc]
        if rc is not None and rc != 0:
            notify_job_failure(
                label="catchup",
                rc=rc,
                attempts=attempts,
                log_file="catchup.log",
                alert_fn=alert_fn,
            )
    elif event_type == "evening_jobs":
        logger.info("Chay lich 21:45 (catchup + daily-check)...")
        cmd_catchup = [python_exe, "-m", "scripts.startup_catchup"]
        res = run_job_with_retry(
            label="catchup",
            log_file="catchup.log",
            command=cmd_catchup,
            timeout_seconds=TIMEOUT_CATCHUP_SECONDS,
            lock_id=ADVISORY_LOCK_CATCHUP,
            logs_dir=logs_dir,
            cwd=cwd,
            dsn=dsn,
            lock_manager=lock_manager,
            sleep_fn=sleep_fn,
            runner_fn=runner_fn,
            return_attempts=True,
        )
        rc_catchup, attempts = res  # type: ignore[misc]
        if rc_catchup is not None and rc_catchup != 0:
            notify_job_failure(
                label="catchup",
                rc=rc_catchup,
                attempts=attempts,
                log_file="catchup.log",
                alert_fn=alert_fn,
            )

        fn_job = runner_fn if runner_fn is not None else run_job
        cmd_daily_check = [python_exe, "scripts/daily_data_check.py"]
        rc_daily = fn_job(
            label="daily-data-check",
            log_file="daily-data-check.log",
            command=cmd_daily_check,
            timeout_seconds=TIMEOUT_DAILY_CHECK_SECONDS,
            lock_id=ADVISORY_LOCK_DAILY_CHECK,
            logs_dir=logs_dir,
            cwd=cwd,
            dsn=dsn,
            lock_manager=lock_manager,
        )
        if rc_daily is not None and rc_daily != 0:
            notify_job_failure(
                label="daily-data-check",
                rc=rc_daily,
                attempts=1,
                log_file="daily-data-check.log",
                alert_fn=alert_fn,
            )

        cmd_universe_refresh = [python_exe, "-m", "scripts.refresh_universe"]
        rc_univ = fn_job(
            label="universe-refresh",
            log_file="universe-refresh.log",
            command=cmd_universe_refresh,
            timeout_seconds=TIMEOUT_UNIVERSE_REFRESH_SECONDS,
            lock_id=ADVISORY_LOCK_CATCHUP,
            logs_dir=logs_dir,
            cwd=cwd,
            dsn=dsn,
            lock_manager=lock_manager,
        )
        if rc_univ is not None and rc_univ != 0:
            notify_job_failure(
                label="universe-refresh",
                rc=rc_univ,
                attempts=1,
                log_file="universe-refresh.log",
                alert_fn=alert_fn,
            )


def scheduler_loop(
    config_path: str | Path = "config/config.yaml",
    logs_dir: Path | None = None,
    cwd: Path | None = None,
    dsn: str | None = None,
    stop_event: threading.Event | None = None,
    lock_manager: Callable[[int], AbstractContextManager[bool]] | None = None,
    python_exe: str = sys.executable,
    skip_startup: bool = False,
    once: bool = False,
    now_fn: Callable[[], datetime] | None = None,
    alert_fn: Callable[[str], Any] | None = None,
) -> None:
    """Vong lap chinh cua scheduler daemon."""
    if stop_event is None:
        stop_event = threading.Event()

    effective_logs_dir = (
        logs_dir
        if logs_dir is not None
        else (Path("/app/logs") if Path("/app/logs").is_dir() else REPO_ROOT / "logs")
    )
    effective_cwd = (
        cwd
        if cwd is not None
        else (Path("/app") if Path("/app").is_dir() else REPO_ROOT)
    )

    if not skip_startup and not stop_event.is_set():
        run_startup(
            logs_dir=effective_logs_dir,
            cwd=effective_cwd,
            dsn=dsn,
            lock_manager=lock_manager,
            python_exe=python_exe,
            alert_fn=alert_fn,
        )

    while not stop_event.is_set():
        holidays = load_holidays(config_path)
        cur_now = now_fn() if now_fn else datetime.now(TZ)
        target_dt, event_type = calculate_next_event(cur_now, holidays)
        logger.info("Moc ke tiep: %s (%s)", target_dt.isoformat(), event_type)

        while not stop_event.is_set():
            now = now_fn() if now_fn else datetime.now(TZ)
            remaining = (target_dt - now).total_seconds()
            if remaining <= 0:
                break
            stop_event.wait(timeout=min(remaining, 5.0))

        if stop_event.is_set():
            break

        run_event(
            event_type=event_type,
            logs_dir=effective_logs_dir,
            cwd=effective_cwd,
            dsn=dsn,
            lock_manager=lock_manager,
            python_exe=python_exe,
            alert_fn=alert_fn,
        )

        if once:
            break


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Trading Scheduler Daemon")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Duong dan file cau hinh (mac dinh: config/config.yaml)",
    )
    parser.add_argument(
        "--logs-dir",
        default=None,
        help="Thu muc ghi logs (mac dinh: /app/logs hoac logs/)",
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help="Working directory cho subprocess (mac dinh: /app hoac repo root)",
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="Postgres DSN (mac dinh tu DB_DSN)",
    )
    parser.add_argument(
        "--skip-startup",
        action="store_true",
        help="Bo qua luot chay catchup ngay khi khoi dong",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Chay 1 su kien ke tiep roi thoat (dung de test)",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    start_outbox("scheduler")

    dsn = args.dsn or os.environ.get("DB_DSN")
    if not dsn:
        try:
            from scripts._db_common import resolve_dsn

            dsn = resolve_dsn()
        except Exception:
            pass

    logs_dir = Path(args.logs_dir) if args.logs_dir else None
    cwd = Path(args.cwd) if args.cwd else None

    stop_event = threading.Event()

    def _sig_handler(signum: int, _frame: Any) -> None:
        logger.info("Nhan tin hieu %d, dung scheduler...", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    scheduler_loop(
        config_path=args.config,
        logs_dir=logs_dir,
        cwd=cwd,
        dsn=dsn,
        stop_event=stop_event,
        skip_startup=args.skip_startup,
        once=args.once,
    )


if __name__ == "__main__":
    main()
