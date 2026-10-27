"""Startup catchup script (Brief 199).

Tu dong kiem tra va nap bu du lieu moi lan khoi dong he thong.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from datetime import date, datetime, timedelta
from typing import Any

from scripts import backfill_foreign_flow, backfill_universe
from scripts.backfill_universe import resolve_use_universe_symbols
from trading.calendar_vn import TZ, is_trading_day, previous_trading_day
from trading.config import load_config
from trading.storage.db import Storage

# Reconfigure stdout for UTF-8 compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

_sleep = time.sleep
_now = lambda: datetime.now(TZ)


def catchup_end(now: datetime, holidays: Any = frozenset()) -> date:
    """Tinh ngay ket thuc cua buoc nap bu (Brief 199).

    Bat bien so 1: khong bao gio nap ngay giao dich hom nay truoc 21:30.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ)
    else:
        now = now.astimezone(TZ)

    d = now.date()
    from datetime import time as dt_time

    if is_trading_day(d, holidays) and now.time() >= dt_time(21, 30):
        return d
    return previous_trading_day(d, holidays)


def plan_universe_start(
    progress: dict[str, dict[str, Any] | None],
    end: date,
    max_days: int,
    default_days: int = 7,
) -> tuple[date | None, bool]:
    """Lap ke hoach ngay bat dau nap cho danh muc (Brief 199 §1.1).

    Tra ve (start, is_clamped).
    start = None nghia la moi ma da duoc hoi toi end, khong can nap.
    is_clamped = True nghia la khoang hong vuot qua max_days va da bi cat.
    """
    if not progress:
        return (end - timedelta(days=default_days), False)

    thresholds: list[date] = []
    for p in progress.values():
        if (
            p is not None
            and p.get("status") == "ok"
            and p.get("attempted_until") is not None
        ):
            attempted = p["attempted_until"]
            if isinstance(attempted, str):
                attempted = date.fromisoformat(attempted)
            thresholds.append(attempted)
        else:
            thresholds.append(end - timedelta(days=default_days))

    start = min(thresholds)
    if start >= end:
        return (None, False)

    if (end - start).days > max_days:
        return (end - timedelta(days=max_days), True)

    return (start, False)


def plan_foreign_flow_start(
    day_counts: dict[date, int],
    end: date,
    max_days: int,
) -> tuple[date | None, bool]:
    """Lap ke hoach ngay bat dau nap cho khoi ngoai (Brief 199 §1.1).

    Tra ve (start, is_clamped).
    start = None nghia la last >= end, khong can nap.
    """
    positive_days = [d for d, c in day_counts.items() if c > 0]
    if not positive_days:
        return (end - timedelta(days=max_days), True)

    last = max(positive_days)
    if last >= end:
        return (None, False)

    return (last + timedelta(days=1), False)


def find_short_days(
    counts: dict[date, int],
    check_days: list[date],
    baseline_days: list[date],
    ratio: float = 0.8,
) -> list[date]:
    """Tim cac ngay co so ma it hon ratio * median(baseline) (Brief 199 §1.1)."""
    base_vals = [counts[d] for d in baseline_days if counts.get(d, 0) > 0]
    if not base_vals:
        return sorted(check_days)

    base = statistics.median(base_vals)
    short = [d for d in check_days if counts.get(d, 0) < ratio * base]
    return sorted(short)


def build_parser() -> argparse.ArgumentParser:
    """Tao argument parser cho scripts.startup_catchup."""
    parser = argparse.ArgumentParser(
        description="Tu dong kiem tra va nap bu du lieu khi khoi dong he thong."
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Duong dan file cau hinh (mac dinh: config/config.yaml).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="In ke hoach va chay buoc kiem, khong goi ham nap.",
    )
    parser.add_argument(
        "--max-days",
        type=int,
        default=90,
        help="So ngay toi da de nap bu (mac dinh: 90).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    cfg = load_config(args.config)
    storage = Storage(cfg.db_dsn)

    # 2. Cho DB san sang
    db_ready = False
    for attempt in range(30):
        try:
            storage.read_active_universe()
            db_ready = True
            break
        except Exception:
            if attempt < 29:
                _sleep(10)

    if not db_ready:
        print("[catchup] DB chua san sang sau 300s")
        return 1

    # 3. Ngay cuoi
    end = catchup_end(_now(), cfg.holidays)
    print(f"[catchup] ngay cuoi = {end}")

    has_error = False

    # 4. Nen ngay (1d)
    start_1d: date | None = None
    clamped_1d = False
    try:
        symbols, *_ = resolve_use_universe_symbols(storage, cfg)
        progress_1d = {s: storage.get_backfill_progress(s, "1d") for s in symbols}
        start_1d, clamped_1d = plan_universe_start(
            progress_1d, end, max_days=args.max_days
        )
        if start_1d is not None and not args.dry_run:
            ret = backfill_universe.main(
                [
                    "--timeframe",
                    "1d",
                    "--from",
                    start_1d.isoformat(),
                    "--to",
                    end.isoformat(),
                    "--use-universe",
                    "--sleep-ms",
                    "200",
                ]
            )
            if ret is not None and ret != 0:
                has_error = True
                print(
                    f"[catchup] LOI 1d: ExitCodeError: backfill_universe returned {ret}"
                )
    except Exception as e:
        has_error = True
        msg = f"{type(e).__name__}: {e}"[:300]
        print(f"[catchup] LOI 1d: {msg}")

    # 5. Nen 5 phut (5m)
    start_5m: date | None = None
    clamped_5m = False
    try:
        symbols, *_ = resolve_use_universe_symbols(storage, cfg)
        symbols_5m = [s for s in symbols if s not in set(cfg.symbols)]
        progress_5m = {s: storage.get_backfill_progress(s, "5m") for s in symbols_5m}
        start_5m, clamped_5m = plan_universe_start(
            progress_5m, end, max_days=args.max_days
        )
        if start_5m is not None and not args.dry_run:
            ret = backfill_universe.main(
                [
                    "--timeframe",
                    "5m",
                    "--from",
                    start_5m.isoformat(),
                    "--to",
                    end.isoformat(),
                    "--use-universe",
                    "--skip-config-symbols",
                    "--sleep-ms",
                    "200",
                ]
            )
            if ret is not None and ret != 0:
                has_error = True
                print(
                    f"[catchup] LOI 5m: ExitCodeError: backfill_universe returned {ret}"
                )
    except Exception as e:
        has_error = True
        msg = f"{type(e).__name__}: {e}"[:300]
        print(f"[catchup] LOI 5m: {msg}")

    # 6. Khoi ngoai (foreign-flow)
    start_ff: date | None = None
    clamped_ff = False
    try:
        day_counts = storage.read_foreign_flow_day_counts(
            end - timedelta(days=args.max_days), end
        )
        start_ff, clamped_ff = plan_foreign_flow_start(
            day_counts, end, max_days=args.max_days
        )
        if start_ff is not None and not args.dry_run:
            ret = backfill_foreign_flow.main(
                [
                    "--from",
                    start_ff.isoformat(),
                    "--to",
                    end.isoformat(),
                ]
            )
            if ret != 0:
                has_error = True
                print(
                    f"[catchup] LOI foreign-flow: ExitCodeError: backfill_foreign_flow returned {ret}"
                )
    except Exception as e:
        has_error = True
        msg = f"{type(e).__name__}: {e}"[:300]
        print(f"[catchup] LOI foreign-flow: {msg}")

    # 8. Buoc kiem
    planned_starts = [s for s in [start_1d, start_5m, start_ff] if s is not None]
    if planned_starts:
        check_from = min(min(planned_starts), end - timedelta(days=14))
    else:
        check_from = end - timedelta(days=14)

    cur = check_from
    check_days: list[date] = []
    while cur <= end:
        if is_trading_day(cur, cfg.holidays):
            check_days.append(cur)
        cur += timedelta(days=1)

    cur = end - timedelta(days=30)
    baseline_days: list[date] = []
    while cur <= end:
        if is_trading_day(cur, cfg.holidays):
            baseline_days.append(cur)
        cur += timedelta(days=1)

    counts_from = min(check_from, end - timedelta(days=30))
    counts_1d = storage.read_daily_active_symbol_day_counts(counts_from, end)
    counts_5m = storage.read_5m_active_symbol_day_counts(counts_from, end)
    counts_ff = storage.read_foreign_flow_day_counts(counts_from, end)

    short_1d = find_short_days(counts_1d, check_days, baseline_days)
    short_5m = find_short_days(counts_5m, check_days, baseline_days)
    short_ff = find_short_days(counts_ff, check_days, baseline_days)

    print(
        f"[kiem] 1d: {len(check_days)} ngay, thieu: {[d.isoformat() for d in short_1d]}"
    )
    print(
        f"[kiem] 5m: {len(check_days)} ngay, thieu: {[d.isoformat() for d in short_5m]}"
    )
    print(
        f"[kiem] foreign-flow: {len(check_days)} ngay, thieu: {[d.isoformat() for d in short_ff]}"
    )

    # 9. Ma thoat
    clamped = False
    if clamped_1d and start_1d is not None:
        clamped = True
        print(
            f"[catchup] CANH BAO: khoang hong vuot {args.max_days} ngay, can chay tay --from {start_1d.isoformat()}"
        )
    if clamped_5m and start_5m is not None:
        clamped = True
        print(
            f"[catchup] CANH BAO: khoang hong vuot {args.max_days} ngay, can chay tay --from {start_5m.isoformat()}"
        )
    if clamped_ff and start_ff is not None:
        clamped = True
        print(
            f"[catchup] CANH BAO: khoang hong vuot {args.max_days} ngay, can chay tay --from {start_ff.isoformat()}"
        )

    has_short = bool(short_1d or short_5m or short_ff)
    if has_error or has_short or clamped:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
