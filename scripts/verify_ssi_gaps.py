"""Bước 2 (prompt 2026-08-15-hermes-data-integrity.md): đối chiếu DB vs API SSI
cho các bước nhảy không giải thích được + ACC 2022-01-05 (chia tách đã biết).

Câu hỏi quyết định: cùng một mã/ngày, SSI trả về gì SO VỚI bars_daily?
- (a) giống hệt DB -> dữ liệu hỏng từ NGUỒN (SSI), ta không sửa được bằng backfill.
- (b) khác DB -> lỗi ở đường ingest của ta (backfill.py / parser) — bug thật.
- (c) SSI có tham số/endpoint trả giá đã điều chỉnh mà ta chưa dùng.

CHỈ ĐỌC: không UPDATE/DELETE/INSERT vào bảng hệ thống. Auth qua refresh_token
trong bảng ssi_auth_state (collector đang giữ sống) — KHÔNG làm OTP mới. Nếu
token hết hạn: script DỪNG và báo, không tự xoay.

CLI:
  uv run python scripts/verify_ssi_gaps.py \
      --cases "PPI:2020-05-13,ACM:2019-11-27,RCD:2016-04-13,NAW:2018-05-10,SDY:2017-10-19,NHH:2019-09-09,RCC:2018-12-27,LMC:2019-03-22,ACC:2022-01-05" \
      [--window 5]
"""

import argparse
import asyncio
import sys
from datetime import date, datetime, timedelta

from _db_common import load_dotenv, resolve_dsn

from trading.calendar_vn import TZ
from trading.config import load_config
from trading.storage.db import Storage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")



def _db_rows(storage, symbol: str, frm: datetime, to: datetime) -> dict[date, tuple]:
    """bars_daily trong cửa sổ, key = ngày giao dịch HCM (ts UTC 17:00 -> +1 ngày)."""
    out: dict[date, tuple] = {}
    with storage.conn() as c:
        rows = c.execute(
            "SELECT ts, open, high, low, close, volume FROM bars_daily "
            "WHERE symbol = %s AND ts >= %s AND ts < %s ORDER BY ts",
            (symbol, frm, to),
        ).fetchall()
    for ts, o, h, l, cl, v in rows:
        out[ts.astimezone(TZ).date()] = (float(o), float(h), float(l), float(cl), int(v))
    return out


def _fmt(v) -> str:
    return f"{v:>10,.0f}" if v is not None else f"{'—':>10}"


def _bar_row(o, h, l, c, v) -> str:
    return (f"O {_fmt(o)} H {_fmt(h)} L {_fmt(l)} C {_fmt(c)} V {_fmt(v)}")


def _compare_row(d: date, db: tuple | None, ssi: tuple | None) -> str:
    same = db is not None and ssi is not None and tuple(
        round(float(x), 2) for x in db
    ) == tuple(round(float(x), 2) for x in ssi)
    db_s = _bar_row(*db) if db else f"{'—':>10} (không có bar)"
    ssi_s = _bar_row(*ssi) if ssi else f"{'—':>10} (không có bar)"
    mark = "KHỚP" if same else ("CHỈ DB" if db and not ssi else
                                "CHỈ SSI" if ssi and not db else "KHÁC")
    return f"  {d}  {db_s}  |  {ssi_s}  | {mark}"


async def _run(cases: list[tuple[str, date]], window: int) -> None:
    dsn = resolve_dsn()
    load_dotenv()
    cfg = load_config("config/config.yaml")
    storage = Storage(dsn)

    from trading.collector.backfill import SSIRestClient

    client = SSIRestClient(cfg, storage)
    try:
        for symbol, gap_day in cases:
            frm = datetime.combine(gap_day - timedelta(days=window),
                                   datetime.min.time(), tzinfo=TZ)
            to = datetime.combine(gap_day + timedelta(days=window + 1),
                                  datetime.min.time(), tzinfo=TZ)
            db = _db_rows(storage, symbol, frm, to)
            try:
                ssi_bars = await client.daily_ohlc(
                    symbol, frm.date(), to.date() + timedelta(days=1)
                )
            except Exception as e:  # token hết hạn / lỗi mạng — dừng, không tự xoay
                print(f"\nLỖI gọi SSI cho {symbol} (dừng tại đây, không tự xoay "
                      f"token): {type(e).__name__}: {str(e)[:200]}")
                return
            ssi = {b.ts.date(): (b.open, b.high, b.low, b.close, b.volume)
                   for b in ssi_bars}
            print(f"\n{'=' * 100}")
            print(f"{symbol} — bước nhảy ngày {gap_day} (cửa sổ ±{window} ngày)")
            print(f"{'=' * 100}")
            all_days = sorted(set(db) | set(ssi))
            for d in all_days:
                print(_compare_row(d, db.get(d), ssi.get(d)))
            n_db = len(db)
            n_ssi = len(ssi)
            n_match = sum(
                1 for d in all_days
                if db.get(d) and ssi.get(d)
                and tuple(round(float(x), 2) for x in db[d])
                == tuple(round(float(x), 2) for x in ssi[d])
            )
            print(f"  -> {n_match}/{max(n_db, n_ssi)} ngày chung KHỚP "
                  f"(DB có {n_db} ngày, SSI trả {n_ssi} ngày)")
    finally:
        await client.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True,
                    help="SYM:YYYY-MM-DD,SYM:YYYY-MM-DD — mã:ngày bước nhảy")
    ap.add_argument("--window", type=int, default=5)
    args = ap.parse_args()
    cases = []
    for part in args.cases.split(","):
        sym, _, day = part.strip().partition(":")
        cases.append((sym.strip(), datetime.strptime(day.strip(), "%Y-%m-%d").date()))
    asyncio.run(_run(cases, args.window))


if __name__ == "__main__":
    main()
