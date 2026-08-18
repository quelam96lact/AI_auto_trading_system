"""Sửa backfill_progress đang NÓI DỐI cho khớp thực tế (2026-08-18).

Bug cũ: backfill_universe ghi last_done_date = to bất kể bars rỗng -> 1594 dòng
1d ghi last_done_date = 2026-08-10 trong khi bars_daily không mã nào có bar sau
2026-08-07. Đây là bảng TRẠNG THÁI backfill (không phải dữ liệu thị trường) nên
được phép ghi — nhưng phải chạy CÓ CHỦ ĐÍCH, mặc định CHỈ-XEM-KHÔNG-GHI.

Cách sửa: với mỗi dòng progress (timeframe='1d'), đọc ngày bar cuối THẬT của
symbol đó từ bars_daily; nếu last_done_date > ngày bar cuối thật (hoặc symbol
không còn bar nào) thì sửa:
  last_done_date  -> ngày bar cuối thật (NULL nếu không có bar nào)
  attempted_until -> ngày bar cuối thật (NULL nếu không có bar nào)
Ý nghĩa của attempted_until = ngày bar cuối thật: lần chạy backfill kế tiếp với
to > ngày đó sẽ KHÔNG skip (fetch tiếp từ đó) — đúng, vì dữ liệu thật chưa tới
to. Nếu để attempted_until = to cũ (08-10) thì mã có dữ liệu tới 07-08 sẽ bị
skip khi chạy --to 08-10 — sai (dữ liệu vẫn thiếu 07-09 -> 08-10).

Chỉ sửa dòng status='ok' (dòng error/lỗi không phải đối tượng của bug này).

CHẠY:
  uv run python scripts/fix_backfill_progress.py            # chỉ-xem, không ghi
  uv run python scripts/fix_backfill_progress.py --apply    # ghi thật
KHÔNG đụng bars, bars_daily, hay bất kỳ bảng dữ liệu thị trường nào.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _db_common import resolve_dsn

from trading.storage.db import Storage


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="ghi thật (mặc định: chỉ-xem)")
    ap.add_argument("--timeframe", default="1d")
    args = ap.parse_args()

    storage = Storage(resolve_dsn())
    with storage.conn() as c:
        rows = c.execute(
            "SELECT symbol, last_done_date, attempted_until FROM backfill_progress "
            "WHERE timeframe = %s AND status = 'ok'",
            (args.timeframe,),
        ).fetchall()

    to_fix: list[tuple[str, object, object]] = []  # (symbol, old_done, new_done)
    no_data: list[str] = []
    unchanged = 0
    for symbol, done, attempted in rows:
        with storage.conn() as c:
            row = c.execute(
                "SELECT max(ts) FROM bars_daily WHERE symbol = %s", (symbol,)
            ).fetchone()
        real_last = row[0].date() if row and row[0] is not None else None
        if real_last is None:
            no_data.append(symbol)
            if done is not None:
                to_fix.append((symbol, done, None))
            else:
                unchanged += 1
            continue
        if done is not None and done > real_last:
            to_fix.append((symbol, done, real_last))
        else:
            unchanged += 1

    print(f"Tổng dòng progress {args.timeframe} status=ok: {len(rows)}")
    print(f"  - {len(to_fix)} dòng SẼ SỬA (last_done_date nói quá so với bars_daily)")
    print(f"  - {len(no_data)} symbol KHÔNG có bar nào trong bars_daily (last_done_date -> NULL)")
    print(f"  - {unchanged} dòng đã khớp thực tế (không đổi)")
    if to_fix:
        print("\nChi tiết 10 dòng đầu (symbol: last_done_date CŨ -> MỚI):")
        for symbol, old, new in to_fix[:10]:
            print(f"  {symbol}: {old} -> {new}")
    if no_data:
        print(f"\nSymbol không có bar nào: {len(no_data)} mã, vd {no_data[:5]}")

    if args.apply:
        n = 0
        for symbol, _old, new in to_fix:
            with storage.conn() as c:
                c.execute(
                    "UPDATE backfill_progress SET last_done_date = %s, "
                    "attempted_until = %s, updated_at = now() "
                    "WHERE symbol = %s AND timeframe = %s",
                    (new, new, symbol, args.timeframe),
                )
            n += 1
        print(f"\nĐÃ GHI: {n} dòng (last_done_date + attempted_until -> ngày bar cuối thật)")
    else:
        print("\nCHẾ ĐỘ CHỈ-XEM — chưa ghi gì. Chạy lại với --apply để ghi.")


if __name__ == "__main__":
    main()
