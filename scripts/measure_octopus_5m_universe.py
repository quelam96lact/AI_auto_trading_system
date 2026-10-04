"""Đo lường Octopus Pullback trên TOÀN BỘ RỔ có bar 5 phút (Brief đợt 11 - Task 1).

Đặc tả:
- Rổ mã: Toàn bộ mã có trong bảng bars (SELECT DISTINCT symbol FROM bars ORDER BY symbol).
  Hỗ trợ cờ --symbols để lọc một tập con mã (ví dụ --symbols HII,IJC,AAA).
- Dữ liệu: Bảng bars (nến 5m).
- Chi phí: FEE_RATE (0.25%), SELL_TAX_RATE (0.1%), SLIPPAGE_BPS (5) từ trading.paper_broker.
- Dùng lại: measure_symbol_5m từ scripts.measure_octopus_5m (TUYỆT ĐỐI không chép lại logic đo).
- Thước đo danh mục: profit_factor, expectancy, max_drawdown, sharpe, portfolio_equity_curve từ trading.metrics.
- Không áp exclusions.txt, không đọc config.yaml để lấy rổ mã.

CLI:
    uv run python scripts/measure_octopus_5m_universe.py [--symbols HII,IJC,AAA] [--dsn ...] [--capital 100000000]
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Thêm scripts/ vào sys.path
sys.path.insert(0, str(Path(__file__).parent))
try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

try:
    from measure_octopus_5m import measure_symbol_5m
except ImportError:
    from scripts.measure_octopus_5m import measure_symbol_5m

from trading.calendar_vn import TZ
from trading.metrics import (
    expectancy,
    max_drawdown,
    portfolio_equity_curve,
    profit_factor,
    sharpe,
)
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.storage.db import Storage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def get_universe_symbols(storage: Storage) -> list[str]:
    """Lấy danh sách toàn bộ mã có dữ liệu trong bảng bars (5m).

    Tuyệt đối không đọc config.yaml hay exclusions.txt.
    """
    with storage.conn() as c:
        rows = c.execute("SELECT DISTINCT symbol FROM bars ORDER BY symbol").fetchall()
        return [r[0] for r in rows]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Đo lường Octopus Pullback trên toàn bộ rổ nến 5m"
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="Danh sách mã phân tách bởi dấu phẩy (vd: HII,IJC,AAA). Mặc định: toàn rổ DB",
    )
    parser.add_argument("--dsn", default=None, help="Postgres connection DSN")
    parser.add_argument(
        "--capital", type=float, default=100_000_000.0, help="Vốn mỗi mã (VND)"
    )
    parser.add_argument("--from", dest="frm", default="2020-01-01")
    parser.add_argument("--to", dest="to", default="2030-01-01")
    args = parser.parse_args()

    dsn = resolve_dsn(args.dsn)
    storage = Storage(dsn)

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = get_universe_symbols(storage)

    frm = datetime.strptime(args.frm, "%Y-%m-%d").replace(tzinfo=TZ)
    to = datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=TZ)

    print("=" * 115, flush=True)
    print("BÁO CÁO ĐO LƯỜNG OCTOPUS PULLBACK TRÊN TOÀN RỔ NẾN 5 PHÚT (BRIEF ĐỢT 11 - TASK 1)", flush=True)
    print("=" * 115, flush=True)
    print(
        f"Số mã khảo sát: {len(symbols)} | Vốn: {args.capital:,.0f} VND/mã | "
        f"Phí SSI: {FEE_RATE*100:.2f}%, Thuế: {SELL_TAX_RATE*100:.2f}%, Trượt: {SLIPPAGE_BPS} bps",
        flush=True,
    )
    print("-" * 115, flush=True)

    results = []
    for sym in symbols:
        res = measure_symbol_5m(storage, sym, frm, to, args.capital)
        results.append(res)

    # Tổng hợp thống kê
    tot_symbols = len(results)
    trading_results = [r for r in results if r["trades"] > 0]
    trading_symbols_count = len(trading_results)

    tot_trades = sum(r["trades"] for r in results)
    tot_strat_pnl = sum(r["strat_pnl"] for r in results)
    tot_bh_pnl = sum(r["bh_pnl"] for r in results)
    all_trade_pnls = [p for r in results for p in r["trade_pnls"]]
    winning_trades = sum(1 for p in all_trade_pnls if p > 0)
    overall_win_rate = (winning_trades / tot_trades * 100.0) if tot_trades > 0 else 0.0

    pf = profit_factor(all_trade_pnls)
    exp = expectancy(all_trade_pnls)

    pnl_by_symbol_by_date = {r["symbol"]: r["daily_pnl"] for r in results}
    curve = portfolio_equity_curve(pnl_by_symbol_by_date, capital_per_symbol=args.capital)
    mdd_portfolio = max_drawdown(curve)

    daily_returns = []
    if len(curve) >= 2:
        for i in range(1, len(curve)):
            prev = curve[i - 1]
            if prev > 0:
                daily_returns.append((curve[i] - prev) / prev)
    sh_portfolio = sharpe(daily_returns, periods_per_year=252.0)

    pf_str = f"{pf:.2f}" if pf is not None else "N/A (0 lệnh thua / 0 lệnh)"
    sh_str = f"{sh_portfolio:.2f}" if sh_portfolio is not None else "N/A"

    print("KẾT QUẢ TỔNG HỢP TOÀN RỔ:", flush=True)
    print(f"- Số mã có dữ liệu khảo sát : {tot_symbols:,} mã", flush=True)
    print(f"- Số mã sinh ít nhất 1 lệnh : {trading_symbols_count:,} mã ({trading_symbols_count/tot_symbols*100:.1f}%)", flush=True)
    print(f"- Tổng số lệnh thực thi     : {tot_trades:,} lệnh (Thắng: {winning_trades}, Thua: {tot_trades - winning_trades}, Win Rate: {overall_win_rate:.1f}%)", flush=True)
    print(f"- PnL Chiến lược             : {tot_strat_pnl:+,.0f} VND (so với Mua-và-Giữ: {tot_bh_pnl:+,.0f} VND)", flush=True)
    print(f"- Profit Factor              : {pf_str}", flush=True)
    print(f"- Expectancy (TB/lệnh)       : {exp:+,.0f} VND/lệnh", flush=True)
    print(f"- Max Drawdown Danh mục      : {mdd_portfolio * 100:.2f}%", flush=True)
    print(f"- Sharpe Danh mục (252 ngày) : {sh_str}", flush=True)
    print("-" * 115, flush=True)

    # Phân tán theo mã: Top 5 lãi nhất và Top 5 lỗ nhất
    sorted_by_pnl_desc = sorted(results, key=lambda r: r["strat_pnl"], reverse=True)
    sorted_by_pnl_asc = sorted(results, key=lambda r: r["strat_pnl"])

    print("PHÂN TÁN THEO MÃ — TOP 5 MÃ LÃI NHẤT:", flush=True)
    for idx, r in enumerate(sorted_by_pnl_desc[:5], 1):
        print(
            f"  {idx}. {r['symbol']:<6} | PnL: {r['strat_pnl']:+15,.0f} VND | Số lệnh: {r['trades']:<4} | "
            f"Win Rate: {r['win_rate']:<5.1f}% | B&H PnL: {r['bh_pnl']:+15,.0f} VND",
            flush=True,
        )

    print("\nPHÂN TÁN THEO MÃ — TOP 5 MÃ LỖ NHẤT:", flush=True)
    for idx, r in enumerate(sorted_by_pnl_asc[:5], 1):
        print(
            f"  {idx}. {r['symbol']:<6} | PnL: {r['strat_pnl']:+15,.0f} VND | Số lệnh: {r['trades']:<4} | "
            f"Win Rate: {r['win_rate']:<5.1f}% | B&H PnL: {r['bh_pnl']:+15,.0f} VND",
            flush=True,
        )
    print("=" * 115, flush=True)

    # Khối HẠN CHẾ theo đúng yêu cầu Brief
    print("\nHẠN CHẾ (LIMITATIONS):", flush=True)
    print(
        "1. Chỉ 87 ngày giao dịch dùng chung (03/04 -> 07/08/2026), đại diện cho MỘT CHẾ ĐỘ THỊ TRƯỜNG DUY NHẤT.\n"
        "2. Toàn bộ dữ liệu 5m nằm trọn trong kỳ HOLDOUT của khung ngày (01/01/2024 -> 13/08/2026).\n"
        "3. EMA(200) trên nến 5m là bộ lọc xu hướng ~4 ngày, KHÔNG PHẢI chiến lược đã thiết kế ban đầu (xu hướng 10 tháng).",
        flush=True,
    )
    print("=" * 115, flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
