"""Đo diện rộng MỘT chiến lược bất kỳ trên toàn bộ bars_daily.

Gộp từ measure_daily_breakout.py + measure_octopus.py (2026-08-15) — hai file đó
cài đặt CÙNG một giao thức, chỉ khác chiến lược được dựng. Giữ nguyên giao thức,
không đổi phép đo: chạy lại file này phải ra ĐÚNG con số của hai file cũ.

THIẾT KẾ ĐÃ CHỐT — làm đúng, không tự đổi:
- Chạy ĐỘC LẬP TỪNG MÃ: mỗi mã một run_backtest() riêng với CÙNG một số vốn
  (mặc định 1.000.000.000), rồi CỘNG DỒN. KHÔNG chạy một danh mục chung 1.551
  mã: vốn chung sẽ bị cạn và lặng lẽ chặn tín hiệu của các mã phía sau — đúng
  cái bẫy sizing đã từng làm hỏng phép đo sma_cross (xem GO_LIVE_AUDIT.md,
  mục "Luồng paper không thể mua").
- Đọc từng mã một từ bars_daily (2.969.328 dòng — KHÔNG nạp hết vào RAM).
- T+2,5 và mốc mua-và-giữ do run_backtest/PaperBroker lo (từ 4a61186).

Báo cáo trả lời bằng số:
1. Tổng PnL chiến lược vs tổng PnL mua-và-giữ (+ chênh lệch, kết luận thẳng).
2. Tổng số lệnh + số mã thực sự sinh lệnh (đủ cỡ mẫu hay không).
3. Tổng số dòng bị loại vì bẩn (OHLC<=0), tách theo mã + mã không đáng tin.
Kèm phân phối theo mã: số mã thắng/thua mua-và-giữ, trung vị chênh lệch.

Chiến lược nào tự lọc thanh khoản (có thuộc tính `min_avg_value_20` +
`liquidity_window`, hiện là octopus_pullback) thì báo cáo thêm dòng "số mã TỪNG
đủ thanh khoản", tính bằng CHÍNH ngưỡng/cửa sổ của strategy đó — không hardcode
lại, để hai nơi không thể lệch nhau.

CLI:
  uv run python scripts/measure_strategy.py --strategy octopus_pullback
      [--dsn ...] [--capital 1e9] [--from 2016-01-04] [--to 2026-08-13]
      [--limit N] [--dirty-pct 0.05] [--exclude-file FILE]
--limit: chỉ đo N mã đầu (smoke test); mặc định 0 = tất cả.
--exclude-file: file 1 mã/dòng, loại khỏi phép đo trước khi chạy. Sinh ra bằng
`check_price_adjustment.py --emit-exclusions FILE` (mã còn chia tách chưa điều
chỉnh + mã quá bẩn). Đo 2026-08-15: với daily_breakout, loại 245 mã thì khoản
"lãi" +33,5 tỷ biến mất hoàn toàn (-696 triệu) — nó nằm trọn trong số mã bị loại.
--dirty-pct: tỷ lệ bar rác của mã >= ngưỡng này thì kết quả mã đó bị gắn cờ
"không đáng tin".
"""

import argparse
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

from _db_common import resolve_dsn

from trading.backtest import STRATEGIES, ever_liquid, run_backtest
from trading.calendar_vn import TZ
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.trailing_stop import TrailingStopManager

# Console/redirect tren Windows mac dinh cp1252: print tieng Viet nem
# UnicodeEncodeError SAU KHI da do xong toan bo 1.551 ma — mat sach ket qua.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_CAPITAL = 1_000_000_000.0
DEFAULT_FROM = "2016-01-04"
DEFAULT_TO = "2026-08-13"



def liquidity_spec(strategy) -> tuple[float, int] | None:
    """(ngưỡng, cửa sổ) nếu chiến lược tự lọc thanh khoản, None nếu không."""
    threshold = getattr(strategy, "min_avg_value_20", None)
    window = getattr(strategy, "liquidity_window", None)
    if threshold is None or window is None:
        return None
    return float(threshold), int(window)


def measure_one(
    storage: Storage,
    symbol: str,
    frm: datetime,
    to: datetime,
    capital: float,
    make_strategy,
    liq: tuple[float, int] | None,
) -> dict:
    bars = storage.read_daily_bars(symbol, frm, to)
    report = run_backtest(
        bars,
        make_strategy(),
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
        "liquid": ever_liquid(bars, *liq) if liq else False,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True, choices=list(STRATEGIES))
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--capital", type=float, default=DEFAULT_CAPITAL)
    ap.add_argument("--from", dest="frm", default=DEFAULT_FROM, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="to", default=DEFAULT_TO, help="YYYY-MM-DD")
    ap.add_argument("--limit", type=int, default=0, help="0 = tất cả mã")
    ap.add_argument("--dirty-pct", type=float, default=0.05)
    ap.add_argument(
        "--exclude-file",
        default=None,
        help="file 1 mã/dòng — loại khỏi phép đo (xem check_price_adjustment.py --emit-exclusions)",
    )
    args = ap.parse_args()
    dsn = resolve_dsn(args.dsn)

    make_strategy = STRATEGIES[args.strategy]
    liq = liquidity_spec(make_strategy())

    frm = datetime.strptime(args.frm, "%Y-%m-%d").replace(tzinfo=TZ)
    to = datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=TZ) + timedelta(days=1)

    storage = Storage(dsn)
    with storage.conn() as c:
        symbols = [
            r[0]
            for r in c.execute("SELECT DISTINCT symbol FROM bars_daily ORDER BY symbol")
        ]

    excluded: set[str] = set()
    if args.exclude_file:
        excluded = {
            s.strip().upper()
            for s in Path(args.exclude_file).read_text(encoding="utf-8").splitlines()
            if s.strip()
        }
        symbols = [s for s in symbols if s.upper() not in excluded]
    if args.limit > 0:
        symbols = symbols[: args.limit]

    results: list[dict] = []
    for i, sym in enumerate(symbols, 1):
        results.append(
            measure_one(storage, sym, frm, to, args.capital, make_strategy, liq)
        )
        if i % 200 == 0:
            print(f"  ...đã đo {i}/{len(symbols)} mã", file=sys.stderr)

    n = len(results)
    tot_strat = sum(r["strat_pnl"] for r in results)
    tot_bh = sum(r["bh_pnl"] for r in results)
    tot_trades = sum(r["trades"] for r in results)
    sym_with_trades = sum(1 for r in results if r["trades"] > 0)
    sym_liquid = sum(1 for r in results if r["liquid"])
    tot_filtered = sum(r["filtered"] for r in results)
    sym_with_dirty = sum(1 for r in results if r["filtered"] > 0)

    diffs = [r["strat_pnl"] - r["bh_pnl"] for r in results]
    n_win = sum(1 for d in diffs if d > 0)
    n_lose = sum(1 for d in diffs if d < 0)
    n_even = n - n_win - n_lose
    median_diff = statistics.median(diffs) if diffs else 0.0
    median_strat = (
        statistics.median([r["strat_pnl"] for r in results]) if results else 0.0
    )
    median_bh = statistics.median([r["bh_pnl"] for r in results]) if results else 0.0

    print("=" * 78)
    print(f"ĐO DIỆN RỘNG — {args.strategy.upper()} (khung 1d, T+2,5, có phí)")
    if liq:
        print(
            f"Lọc thanh khoản: rolling-{liq[1]} close*volume >= {liq[0]:,.0f} "
            "(point-in-time, trong strategy)"
        )
    print(
        f"Kỳ đo: {args.frm} -> {args.to} | vốn MỖI MÃ: {args.capital:,.0f} | số mã: {n}"
    )
    if excluded:
        print(
            f"Đã LOẠI {len(excluded)} mã không đáng tin trước khi đo (file: {args.exclude_file})"
        )
    print("=" * 78)

    print(
        "\n[1] TỔNG PNL — CHIẾN LƯỢC vs MUA-VÀ-GIỮ (cùng mã, cùng kỳ, cùng vốn, cùng phí)"
    )
    print(f"  Tổng PnL chiến lược : {tot_strat:>18,.0f}")
    print(f"  Tổng PnL mua-và-giữ : {tot_bh:>18,.0f}")
    print(f"  Chênh lệch (strat - BH): {tot_strat - tot_bh:>12,.0f}")
    if tot_strat < tot_bh:
        print("  KẾT LUẬN: THUA mua-và-giữ — không có biên lợi thế trên diện rộng.")
    else:
        print("  KẾT LUẬN: VƯỢT mua-và-giữ trên diện rộng.")

    print("\n[2] CỠ MẪU")
    print(f"  Tổng số lệnh (SELL fills): {tot_trades:,}")
    print(f"  Số mã thực sự sinh lệnh  : {sym_with_trades}/{n}")
    if liq:
        print(
            f"  Số mã TỪNG đủ thanh khoản: {sym_liquid}/{n} "
            f"({sym_liquid / n:.1%} nếu n>0)"
        )
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
        print(
            f"    {r['symbol']:<8} {r['filtered']:>6} dòng  ({pct:.1%} số bar của mã)"
        )
    unreliable = [
        r
        for r in results
        if r["n_bars"] > 0 and r["filtered"] / r["n_bars"] >= args.dirty_pct
    ]
    if unreliable:
        print(
            f"  Mã KHÔNG ĐÁNG TIN (bar rác >= {args.dirty_pct:.0%} số bar): "
            f"{len(unreliable)} mã — {', '.join(r['symbol'] for r in unreliable)}"
        )
    else:
        print(f"  Không mã nào đạt ngưỡng bar rác >= {args.dirty_pct:.0%}.")

    print("\n[4] PHÂN PHỐI THEO MÃ")
    print(f"  Số mã thắng mua-và-giữ : {n_win}")
    print(f"  Số mã thua mua-và-giữ  : {n_lose}")
    print(f"  Số mã hòa (diff = 0)   : {n_even}")
    print(f"  Trung vị chênh lệch (strat - BH)/mã : {median_diff:,.0f}")
    print(f"  Trung vị PnL chiến lược/mã          : {median_strat:,.0f}")
    print(f"  Trung vị PnL mua-và-giữ/mã          : {median_bh:,.0f}")
    print(f"  Tỷ lệ mã thắng BH: {n_win / n:.1%}" if n else "  (không có mã)")

    print("\n" + "=" * 78)
    liq_part = f" | mã đủ thanh khoản {sym_liquid}" if liq else ""
    print(
        f"TỔNG: strat {tot_strat:,.0f} | BH {tot_bh:,.0f} | diff {tot_strat - tot_bh:,.0f} "
        f"| lệnh {tot_trades:,} | mã sinh lệnh {sym_with_trades}{liq_part} "
        f"| dòng bẩn {tot_filtered:,}"
    )


if __name__ == "__main__":
    main()
