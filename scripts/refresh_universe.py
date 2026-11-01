"""Lam moi danh muc ma (symbol_universe.is_active) tu dong hang tuan (Brief dot 206).

Thu tu:
1. Doc config, xac dinh moc end = catchup_end(now, holidays).
2. Cong tuan: neu max(updated_at) cua symbol_universe cach now < 6 ngay va khong co --force thi bo qua.
3. Doc progress 1d, tinh ngay bat dau (plan_universe_start), goi backfill_universe voi --all-universe.
4. Neu backfill loi thi giu nguyen is_active, tra 1.
5. screen_liquidity.compute(20, 30, dsn), tinh new = active_set(...), lay old = read_active_universe().
6. Cong co rut: neu len(new) < 0.5 * len(old) thi chan ghi, gui Telegram, tra 1.
7. Qua cong thi apply(...) vao DB, in them/bo, tra 0.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta

from scripts import backfill_universe, screen_liquidity
from scripts.screen_liquidity import active_set
from scripts.startup_catchup import catchup_end, plan_universe_start
from trading.calendar_vn import TZ
from trading.config import load_config
from trading.storage.db import Storage
from trading.telegram import send_telegram

MAX_BACKFILL_ERROR_RATIO = 0.2


def get_max_updated_at(storage: Storage) -> datetime | None:
    """Lay updated_at moi nhat trong bang symbol_universe."""
    with storage.conn() as c:
        row = c.execute("SELECT max(updated_at) FROM symbol_universe").fetchone()
        return row[0] if row else None


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Lam moi danh muc ma active hang tuan.")
    ap.add_argument(
        "--config", default="config/config.yaml", help="Duong dan config.yaml"
    )
    ap.add_argument(
        "--max-days", type=int, default=120, help="Gioi han so ngay nap bu 1d"
    )
    ap.add_argument("--force", action="store_true", help="Bo qua cong tuan 6 ngay")
    ap.add_argument(
        "--dry-run", action="store_true", help="Chay thu, khong backfill, khong ghi DB"
    )
    return ap


def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    args = build_parser().parse_args(argv)

    if now is None:
        now = datetime.now(TZ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=TZ)
    else:
        now = now.astimezone(TZ)

    # 1. Doc config va xac dinh moc end
    cfg = load_config(args.config)
    storage = Storage(cfg.db_dsn)
    end = catchup_end(now, cfg.holidays)

    # 2. Cong tuan: neu max(updated_at) cach now < 6 ngay va khong co --force thi dung
    max_updated = get_max_updated_at(storage)
    if max_updated is not None:
        if max_updated.tzinfo is None:
            max_updated = max_updated.replace(tzinfo=TZ)
        else:
            max_updated = max_updated.astimezone(TZ)

        if (now - max_updated) < timedelta(days=6) and not args.force:
            print(f"[universe] lan lam moi gan nhat {max_updated}, chua can")
            return 0

    # 3. Lay danh muc va progress 1d
    symbols = sorted(storage.read_symbol_universe())
    progress = {s: storage.get_backfill_progress(s, "1d") for s in symbols}
    start, clamped = plan_universe_start(progress, end, max_days=args.max_days)
    if clamped:
        print(
            f"[universe] canh bao: khoang cach nap bi cat boi max-days {args.max_days}"
        )

    if args.dry_run:
        plan_str = f"nap {start} -> {end}" if start is not None else "khong can nap"
        print(f"[dry-run] [universe] ke hoach 1d: {plan_str} cho {len(symbols)} ma")
    else:
        # 4. Goi backfill 1d toan danh muc
        if start is not None:
            try:
                ret = backfill_universe.main(
                    [
                        "--timeframe",
                        "1d",
                        "--from",
                        start.isoformat(),
                        "--to",
                        end.isoformat(),
                        "--all-universe",
                        "--sleep-ms",
                        "200",
                    ]
                )
                if ret is not None and ret != 0:
                    print(f"[universe] LOI: backfill_universe tra ma {ret}")
                    return 1
            except Exception as e:
                print(f"[universe] LOI backfill ném lỗi: {e}")
                return 1

            # backfill_universe nuot loi tung ma (status='error') va tra None:
            # SSI hong ca loat thi ma cu van "thanh cong". Dem lai sau khi nap.
            n_err = sum(
                1
                for s in symbols
                if (p := storage.get_backfill_progress(s, "1d")) is not None
                and p.get("status") == "error"
            )
            if n_err > MAX_BACKFILL_ERROR_RATIO * len(symbols):
                msg = (
                    f"[CRITICAL] [universe] backfill 1d loi {n_err}/{len(symbols)} ma "
                    f"(> {MAX_BACKFILL_ERROR_RATIO:.0%}). Khong ghi de is_active."
                )
                print(msg)
                try:
                    send_telegram(msg)
                except Exception as e:
                    print(f"[universe] gui Telegram loi: {e}")
                return 1

    # 5. Tinh toan tap active moi va lay tap cu
    stats, cutoff = screen_liquidity.compute(20, 30, cfg.db_dsn)
    new = active_set(stats, cutoff, 1e9)
    old = set(storage.read_active_universe())

    # 6. Cong co rut: neu len(new) < 0.5 * len(old) thi chan ghi
    if len(new) < 0.5 * len(old):
        msg = (
            f"[CRITICAL] [universe] Cong co rut chan: active moi={len(new)} < 50% active cu={len(old)}.\n"
            "Khong ghi de is_active. Kiem tra lai du lieu 1d bars_daily!"
        )
        print(msg)
        if not args.dry_run:
            try:
                send_telegram(msg)
            except Exception as e:
                print(f"[universe] gui Telegram loi: {e}")
        return 1

    added = sorted(new - old)
    removed = sorted(old - new)

    if args.dry_run:
        print(
            f"[dry-run] [universe] active cu={len(old)} moi={len(new)} "
            f"them={added[:30]} (tong {len(added)}) bo={removed[:30]} (tong {len(removed)})"
        )
        return 0

    # 7. Ghi vao DB va in thong bao
    screen_liquidity.apply(stats, cutoff, 1e9, cfg.db_dsn)
    print(
        f"[universe] active cu={len(old)} moi={len(new)} "
        f"them={added[:30]} (tong {len(added)}) bo={removed[:30]} (tong {len(removed)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
