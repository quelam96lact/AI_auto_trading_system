"""Đo diện rộng DailyBreakoutStrategy trên toàn bộ bars_daily (spec
2026-08-15-daily-breakout, Bước 3).

THIẾT KẾ ĐÃ CHỐT — làm đúng, không tự đổi:
- Chạy ĐỘC LẬP TỪNG MÃ: mỗi mã một run_backtest() riêng với CÙNG một số vốn
  (mặc định 1.000.000.000), rồi CỘNG DỒN. KHÔNG chạy một danh mục chung 1.551
  mã: vốn chung sẽ bị cạn và lặng lẽ chặn tín hiệu của các mã phía sau — đúng
  cái bẫy sizing đã từng làm hỏng phép đo sma_cross (xem GO_LIVE_AUDIT.md,
  mục "Luồng paper không thể mua").
- Đọc từng mã một từ bars_daily (2.969.328 dòng — KHÔNG nạp hết vào RAM).
- Kỳ đo: 2016-01-04 -> 2026-08-13, khung 1d.

Báo cáo trả lời 3 câu hỏi của đặc tả bằng số:
1. Tổng PnL chiến lược vs tổng PnL mua-và-giữ (+ chênh lệch, kết luận thẳng).
2. Tổng số lệnh + số mã thực sự sinh lệnh (đủ cỡ mẫu hay không).
3. Tổng số dòng bị loại vì bẩn (OHLC<=0), tách theo mã + mã không đáng tin.
Kèm phân phối theo mã: số mã thắng/thua mua-và-giữ, trung vị chênh lệch.

CLI:
  uv run python scripts/measure_daily_breakout.py [--dsn ...] [--capital 1e9]
      [--from 2016-01-04] [--to 2026-08-13] [--limit N] [--dirty-pct 0.05]
--limit: chỉ đo N mã đầu (smoke test); mặc định 0 = tất cả.
--dirty-pct: tỷ lệ bar rác của mã >= ngưỡng này thì kết quả mã đó bị gắn cờ
"không đáng tin".
"""

import argparse
import os
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

from trading.backtest import run_backtest
from trading.calendar_vn import TZ
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.strategies.daily_breakout import DailyBreakoutStrategy
from trading.trailing_stop import TrailingStopManager

DEFAULT_CAPITAL = 1_000_000_000.0
DEFAULT_FROM = "2016-01-04"
DEFAULT_TO = "2026-08-13"


def _load_dotenv() -> None:
    """uv run KHÔNG nạp .env — script tự đọc, không nhúng secret vào file."""
    p = Path(__file__).resolve().parents[1] / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


def resolve_dsn(override: str | None) -> str:
    if override:
        return override
    _load_dotenv()
    dsn = os.environ.get("DB_DSN")
    if not dsn:
        raise SystemExit("DB_DSN chưa set — cần .env hoặc --dsn")
    # Windows máy này: DSN dùng localhost bị IPv6 làm mỗi kết nối chậm ~130s.
    return dsn.replace("localhost", "127.0.0.1")


def measure_one(
    storage: Storage,
    symbol: str,
    frm: datetime,
    to: datetime,
    capital: float,
) -> dict:
    """Chạy backtest ĐỘC LẬP cho 1 mã, trả về số liệu tổng hợp của mã đó."""
    bars = storage.read_daily_bars(symbol, frm, to)
    report = run_backtest(
        bars,
        DailyBreakoutStrategy(),
        RiskManager(capital=capital),
        TrailingStopManager(),
        capital,
    )
    strat_pnl = report.realized_pnl + report.unrealized_pnl
    return {
        "symbol": symbol,
        "n_bars": len(bars),
        "trades": report.trades,
        "strat_pnl": strat_pnl,
        "bh_pnl": report.buy_and_hold_pnl,
        "filtered": sum(report.filtered_bars.values()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--capital", type=float, default=DEFAULT_CAPITAL)
    ap.add_argument("--from", dest="frm", default=DEFAULT_FROM, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="to", default=DEFAULT_TO, help="YYYY-MM-DD")
    ap.add_argument("--limit", type=int, default=0, help="0 = tất cả mã")
    ap.add_argument("--dirty-pct", type=float, default=0.05)
    args = ap.parse_args()
    dsn = resolve_dsn(args.dsn)

    frm = datetime.strptime(args.frm, "%Y-%m-%d").replace(tzinfo=TZ)
    to = datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=TZ) + timedelta(days=1)

    storage = Storage(dsn)
    with storage.conn() as c:
        symbols = [r[0] for r in c.execute(
            "SELECT DISTINCT symbol FROM bars_daily ORDER BY symbol"
        )]
    if args.limit > 0:
        symbols = symbols[: args.limit]

    results: list[dict] = []
    for i, sym in enumerate(symbols, 1):
        results.append(measure_one(storage, sym, frm, to, args.capital))
        if i % 200 == 0:
            print(f"  ...đã đo {i}/{len(symbols)} mã", file=sys.stderr)

    n = len(results)
    tot_strat = sum(r["strat_pnl"] for r in results)
    tot_bh = sum(r["bh_pnl"] for r in results)
    tot_trades = sum(r["trades"] for r in results)
    sym_with_trades = sum(1 for r in results if r["trades"] > 0)
    tot_filtered = sum(r["filtered"] for r in results)
    sym_with_dirty = sum(1 for r in results if r["filtered"] > 0)

    diffs = [r["strat_pnl"] - r["bh_pnl"] for r in results]
    n_win = sum(1 for d in diffs if d > 0)
    n_lose = sum(1 for d in diffs if d < 0)
    n_even = n - n_win - n_lose
    median_diff = statistics.median(diffs) if diffs else 0.0
    median_strat = statistics.median([r["strat_pnl"] for r in results]) if results else 0.0
    median_bh = statistics.median([r["bh_pnl"] for r in results]) if results else 0.0

    print("=" * 78)
    print("ĐO DIỆN RỘNG — DAILY BREAKOUT N=20/M=10, KHUNG 1D (T+2,5, có phí)")
    print(f"Kỳ đo: {args.frm} -> {args.to} | vốn MỖI MÃ: {args.capital:,.0f} | "
          f"số mã: {n}")
    print("=" * 78)

    print("\n[1] TỔNG PNL — CHIẾN LƯỢC vs MUA-VÀ-GIỮ (cùng mã, cùng kỳ, cùng vốn, cùng phí)")
    print(f"  Tổng PnL chiến lược : {tot_strat:>18,.0f}")
    print(f"  Tổng PnL mua-và-giữ : {tot_bh:>18,.0f}")
    print(f"  Chênh lệch (strat - BH): {tot_strat - tot_bh:>12,.0f}")
    if tot_strat < tot_bh:
        print("  KẾT LUẬN: THUA mua-và-giữ — không có biên lợi thế trên diện rộng.")

    print("\n[2] CỠ MẪU")
    print(f"  Tổng số lệnh (SELL fills): {tot_trades:,}")
    print(f"  Số mã thực sự sinh lệnh  : {sym_with_trades}/{n} "
          f"({sym_with_trades / n:.1%} nếu có mã — {n} mã đo)")
    if tot_trades < 300:
        print("  CẢNH BÁO: tổng lệnh < 300 — kết luận dễ rơi vào bẫy cỡ mẫu nhỏ.")

    print("\n[3] DỮ LIỆU BẨN (OHLC<=0)")
    print(f"  Tổng số dòng bị loại: {tot_filtered:,} trên {sym_with_dirty} mã")
    dirty_sorted = sorted(
        (r for r in results if r["filtered"] > 0), key=lambda r: -r["filtered"]
    )
    print("  Top 10 mã bẩn nhất:")
    for r in dirty_sorted[:10]:
        pct = r["filtered"] / r["n_bars"] if r["n_bars"] else 0.0
        print(f"    {r['symbol']:<8} {r['filtered']:>6} dòng  "
              f"({pct:.1%} số bar của mã)")
    unreliable = [
        r for r in results
        if r["n_bars"] > 0 and r["filtered"] / r["n_bars"] >= args.dirty_pct
    ]
    if unreliable:
        print(f"  Mã KHÔNG ĐÁNG TIN (bar rác >= {args.dirty_pct:.0%} số bar): "
              f"{len(unreliable)} mã — {', '.join(r['symbol'] for r in unreliable)}")
    else:
        print(f"  Không mã nào đạt ngưỡng bar rác >= {args.dirty_pct:.0%} "
              f"(không đáng tin).")

    print("\n[4] PHÂN PHỐI THEO MÃ")
    print(f"  Số mã thắng mua-và-giữ : {n_win}")
    print(f"  Số mã thua mua-và-giữ  : {n_lose}")
    print(f"  Số mã hòa (diff = 0)   : {n_even}")
    print(f"  Trung vị chênh lệch (strat - BH)/mã : {median_diff:,.0f}")
    print(f"  Trung vị PnL chiến lược/mã          : {median_strat:,.0f}")
    print(f"  Trung vị PnL mua-và-giữ/mã          : {median_bh:,.0f}")
    pct_win = n_win / n if n else 0.0
    print(f"  Tỷ lệ mã thắng BH: {pct_win:.1%}")

    print("\n" + "=" * 78)
    print(f"TỔNG: strat {tot_strat:,.0f} | BH {tot_bh:,.0f} | diff "
          f"{tot_strat - tot_bh:,.0f} | lệnh {tot_trades:,} | mã sinh lệnh "
          f"{sym_with_trades} | dòng bẩn {tot_filtered:,}")


if __name__ == "__main__":
    main()
