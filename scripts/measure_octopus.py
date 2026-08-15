"""Đo diện rộng OctopusPullbackStrategy trên toàn bộ bars_daily (brief
2026-08-15-hermes-octopus-pullback.md, Bước 5).

THIẾT KẾ (giống measure_daily_breakout — đã chốt, không tự đổi):
- Chạy ĐỘC LẬP TỪNG MÃ: mỗi mã một run_backtest() riêng với CÙNG vốn (mặc định
  1e9), rồi CỘNG DỒN. KHÔNG danh mục chung (vốn chung cạn -> chặn tín hiệu mã
  sau — bẫy sizing đã làm hỏng phép đo sma_cross).
- Đọc từng mã một từ bars_daily (2.97M dòng — không nạp hết RAM).
- Kỳ đo: 2016-01-04 -> 2026-08-13, khung 1d.
- Bộ lọc thanh khoản 2 tỷ nằm TRONG strategy (point-in-time, kiểm tại bar tín
  hiệu) — script không cần tự lọc.

Báo cáo trả lời bằng số:
(a) Tổng PnL chiến lược vs tổng mua-và-giữ (+ chênh lệch, kết luận thẳng).
(b) Tổng số lệnh + số mã sinh lệnh + số mã TỪNG đủ thanh khoản (mã có >= 1 bar
    mà rolling-20 close*volume >= 2 tỷ — tính riêng bằng cùng công thức).
(c) Tổng dòng bị loại vì bẩn (OHLC<=0), tách theo mã + mã không đáng tin.
Phân phối theo mã: thắng/thua BH, trung vị chênh lệch.

CLI:
  uv run python scripts/measure_octopus.py [--dsn ...] [--capital 1e9]
      [--from 2016-01-04] [--to 2026-08-13] [--limit N] [--dirty-pct 0.05]
"""

import argparse
import os
import statistics
import sys
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

from trading.backtest import run_backtest
from trading.calendar_vn import TZ
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.strategies.octopus_pullback import OctopusPullbackStrategy
from trading.trailing_stop import TrailingStopManager

# Console/redirect tren Windows mac dinh cp1252: print tieng Viet nem
# UnicodeEncodeError SAU KHI da do xong toan bo 1.551 ma — mat sach ket qua.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_CAPITAL = 1_000_000_000.0
DEFAULT_FROM = "2016-01-04"
DEFAULT_TO = "2026-08-13"
MIN_AVG_VALUE_20 = 2_000_000_000.0
LIQ_WINDOW = 20


def _load_dotenv() -> None:
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
    return dsn.replace("localhost", "127.0.0.1")


def ever_liquid(bars) -> bool:
    """Mã có từng đủ thanh khoản chưa: >= 1 bar mà rolling-20 (KHÔNG tính bar
    hiện tại) của close*volume >= 2 tỷ. Cùng công thức với strategy."""
    vals: deque = deque(maxlen=LIQ_WINDOW)
    for b in bars:
        if (
            b.open <= 0 or b.high <= 0 or b.low <= 0 or b.close <= 0
            or len(vals) < LIQ_WINDOW
        ):
            vals.append(b.close * b.volume)
            continue
        if sum(vals) / LIQ_WINDOW >= MIN_AVG_VALUE_20:
            return True
        vals.append(b.close * b.volume)
    return False


def measure_one(
    storage: Storage,
    symbol: str,
    frm: datetime,
    to: datetime,
    capital: float,
) -> dict:
    bars = storage.read_daily_bars(symbol, frm, to)
    report = run_backtest(
        bars,
        OctopusPullbackStrategy(),
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
        "liquid": ever_liquid(bars),
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
    sym_liquid = sum(1 for r in results if r["liquid"])
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
    print("ĐO DIỆN RỘNG — OCTOPUS PULLBACK (EMA 9/21/200 + MACD 12/26/9, TP 2ATR, T+2,5)")
    print("Lọc thanh khoản: rolling-20 close*volume >= 2 tỷ (point-in-time, "
          "trong strategy)")
    print(f"Kỳ đo: {args.frm} -> {args.to} | vốn MỖI MÃ: {args.capital:,.0f} | "
          f"số mã: {n}")
    print("=" * 78)

    print("\n[1] TỔNG PNL — CHIẾN LƯỢC vs MUA-VÀ-GIỮ (cùng mã, cùng kỳ, cùng vốn, cùng phí)")
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
    print(f"  Số mã TỪNG đủ thanh khoản: {sym_liquid}/{n} "
          f"({sym_liquid / n:.1%} nếu n>0)")
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
    print(f"TỔNG: strat {tot_strat:,.0f} | BH {tot_bh:,.0f} | diff "
          f"{tot_strat - tot_bh:,.0f} | lệnh {tot_trades:,} | mã sinh lệnh "
          f"{sym_with_trades} | mã đủ thanh khoản {sym_liquid} | dòng bẩn "
          f"{tot_filtered:,}")


if __name__ == "__main__":
    main()
