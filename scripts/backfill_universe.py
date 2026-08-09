"""Backfill lịch sử toàn sàn, resumable, cho 1d (bars_daily) hoặc 5m (bars).

CLI:
  uv run python -m scripts.backfill_universe --timeframe 1d --from 2016-01-01 --to 2025-12-31
      [--exchanges HOSE,HNX,UPCOM] [--symbols A,B] [--limit N] [--use-universe]
      [--sleep-ms 200]

Thiết kế (bắt buộc từ plan 2026-08-09-multi-timeframe-data.md Task 5):
- Resumable: trước mỗi mã đọc get_backfill_progress(); nếu status=='ok' và
  last_done_date >= to thì bỏ qua. Sau mỗi mã thành công ghi progress 'ok'.
- Lỗi 1 mã KHÔNG giết cả job: try/except quanh TỪNG mã, ghi status='error',
  đi tiếp (bài học commit ed017c9).
- Rate limit: sleep giữa các mã (--sleep-ms, mặc định 200); gặp lỗi rate-limit
  chờ backoff 1s, 2s, 4s... tối đa 60s, thử lại tối đa 3 lần cho CÙNG mã.
- Chunk daily ≤ 30 ngày/call (giới hạn API); 5m dùng SSIRestClient.intraday_ohlc
  (đã chunk 7 ngày nội bộ).
- write_daily/write_bars UPSERT theo (symbol, ts) — chạy lại an toàn.
"""

import argparse
import asyncio
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from trading.collector.backfill import SSIRestClient
from trading.config import load_config
from trading.storage.db import Storage

MAX_RANGE_DAYS = 366  # chunk theo NAM: 1 nam ~250 bar daily < gioi han 1000 record/call
# (Kiem chung that 2026-08-09: range 10 nam 1 call chi tra 1000 bar window moi nhat
# 2021-2025, mat am tham 2016-2020; chunk 1 nam tra day du 2016=251/2018=248/2021=250)
PROGRESS_EVERY = 25


def load_symbols(cfg, storage, exchanges: set[str] | None = None) -> list[str]:
    """Đọc .spike_all_symbols_classified.json (Task 4b), lọc CỔ PHIẾU đúng:
    listed_shares > 0 AND cw_underlying_symbol is null (loại hết CW/index/TP).
    Ghi universe vào symbol_universe kèm exchange, is_active=false (Task 6
    mới set is_active theo ngưỡng thanh khoản)."""
    path = Path(__file__).parent / ".spike_all_symbols_classified.json"
    if not path.exists():
        raise SystemExit("Chua co .spike_all_symbols_classified.json - chay Task 4b truoc")
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for label, entries in data["boards"].items():
        if exchanges is not None and label not in exchanges:
            continue
        for e in entries:
            shares = e.get("listed_shares") or 0
            if shares > 0 and e.get("cw_underlying_symbol") is None:
                rows.append(
                    {
                        "symbol": e["symbol"],
                        "exchange": label,
                        "is_active": False,
                    }
                )
    storage.upsert_symbol_universe(rows)
    syms = [r["symbol"] for r in rows]
    print(f"[load] {len(syms)} co phieu (listed_shares>0 AND khong CW), da ghi symbol_universe")
    return syms


def fmt_date(d: date) -> str:
    return d.isoformat()


async def fetch_daily(client, symbol: str, frm: date, to: date) -> list:
    """Chunk ≤ 30 ngày/call, gom + dedupe theo (symbol, ts)."""
    by_ts: dict[str, object] = {}
    chunk_start = frm
    while chunk_start <= to:
        chunk_end = min(chunk_start + timedelta(days=MAX_RANGE_DAYS - 1), to)
        for r in await client.daily_ohlc(symbol, chunk_start, chunk_end):
            by_ts[r.ts.isoformat()] = r
        chunk_start = chunk_end + timedelta(days=1)
    return list(by_ts.values())


async def backfill_one(
    client: SSIRestClient,
    storage: Storage,
    symbol: str,
    timeframe: str,
    frm: date,
    to: date,
    sleep_ms: int,
) -> tuple[str, str, str]:
    """Trả về (symbol, status, error_or_empty). Không bao giờ ném ra ngoài."""
    try:
        prog = storage.get_backfill_progress(symbol, timeframe)
        if prog is not None and prog["status"] == "ok" and prog["last_done_date"] is not None and prog["last_done_date"] >= to:
            return symbol, "skip", ""
        if sleep_ms:
            await asyncio.sleep(sleep_ms / 1000)
        last_err = ""
        for attempt in range(3):
            try:
                if timeframe == "1d":
                    bars = await fetch_daily(client, symbol, frm, to)
                    storage.write_daily(bars)
                else:
                    bars = await client.intraday_ohlc(symbol, frm, to)
                    storage.write_bars(bars)
                storage.set_backfill_progress(symbol, timeframe, to, "ok")
                return symbol, "ok", f"{len(bars)} bar"
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"[:200]
                if "rate" in last_err.lower() or "429" in last_err or "too many" in last_err.lower():
                    wait = min(2**attempt, 60)
                    print(f"    rate-limit {symbol}, cho {wait}s (lan {attempt + 1}/3)")
                    await asyncio.sleep(wait)
                    continue
                raise
        storage.set_backfill_progress(symbol, timeframe, None, "error", last_err)
        return symbol, "error", last_err
    except Exception as e:
        err = f"{type(e).__name__}: {e}"[:200]
        storage.set_backfill_progress(symbol, timeframe, None, "error", err)
        return symbol, "error", err


async def run(
    cfg,
    storage,
    timeframe: str,
    frm: date,
    to: date,
    symbols: list[str],
    sleep_ms: int,
) -> None:
    # Access token hết hạn ~1 tiếng, client cũ KHÔNG tự refresh giữa job (đã gặp
    # 401 AuthenticationError sau ~400 mã). Tạo client mới mỗi 25 mã: SSIRestClient
    # lazy-gọi ensure_authenticated (đọc DB, refresh bằng refresh_token nếu cần).
    errors: list[tuple[str, str]] = []
    n_ok = n_skip = n_err = 0
    client: SSIRestClient | None = None
    try:
        for i, sym in enumerate(symbols, 1):
            if client is None or (i % 25 == 1 and i > 1):
                if client is not None:
                    await client.close()
                client = SSIRestClient(cfg, storage)
            _, status, detail = await backfill_one(
                client, storage, sym, timeframe, frm, to, sleep_ms
            )
            if status == "ok":
                n_ok += 1
            elif status == "skip":
                n_skip += 1
            else:
                n_err += 1
                errors.append((sym, detail))
            if i % PROGRESS_EVERY == 0 or i == len(symbols):
                print(
                    f"[{i}/{len(symbols)}] ok={n_ok} skip={n_skip} err={n_err} | "
                    f"cuoi: {sym} {detail}"
                )
    finally:
        if client is not None:
            await client.close()
    print(f"\nDONE: ok={n_ok} skip={n_skip} err={n_err} / {len(symbols)}")
    if errors:
        print("5 loi dau:")
        for sym, err in errors[:5]:
            print(f"  {sym}: {err}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframe", required=True, choices=["1d", "5m"])
    ap.add_argument("--from", dest="frm", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--exchanges", default=None, help="HOSE,HNX,UPCOM (loc tu file)")
    ap.add_argument("--symbols", default=None, help="A,B (thay the toan bo danh sach)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--use-universe", action="store_true")
    ap.add_argument("--sleep-ms", type=int, default=200)
    args = ap.parse_args()

    cfg = load_config("config/config.yaml")
    storage = Storage(cfg.db_dsn)
    storage.init_schema()

    frm = datetime.strptime(args.frm, "%Y-%m-%d").date()
    to = datetime.strptime(args.to, "%Y-%m-%d").date()

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]
    elif args.use_universe:
        symbols = storage.read_active_universe()
        print(f"[load] {len(symbols)} ma tu universe (is_active)")
    else:
        symbols = load_symbols(
            cfg, storage, set(args.exchanges.split(",")) if args.exchanges else None
        )
    if args.limit:
        symbols = symbols[: args.limit]
    print(f"Backfill {args.timeframe}: {len(symbols)} ma, {frm} -> {to}")

    asyncio.run(run(cfg, storage, args.timeframe, frm, to, symbols, args.sleep_ms))


if __name__ == "__main__":
    main()
