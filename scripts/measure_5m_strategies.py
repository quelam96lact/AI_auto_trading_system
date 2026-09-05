"""Đo diện rộng các chiến lược trên toàn bộ bar 5 PHÚT (Gói Y — plan 2026-09-05).

Đo lường và so sánh hiệu suất trên khung bar 5 phút:
1. OctopusPullbackStrategy với các ngưỡng thanh khoản khác nhau:
   - 2 tỷ đ/bar (mặc định hiện tại)
   - 200 triệu đ/bar
   - 50 triệu đ/bar
   - 0 đ (tắt lọc thanh khoản)
2. SmaCrossStrategy (mặc định fast=10, slow=20)
3. Mốc Mua-và-Giữ (Buy & Hold) cùng kỳ, cùng mã, cùng vốn, cùng biểu phí.

CLI:
    uv run python scripts/measure_5m_strategies.py [--capital 100000000] [--dsn ...]
"""

import argparse
import statistics
import sys
from datetime import datetime
from pathlib import Path

# Thêm scripts/ vào sys.path để import _db_common
sys.path.insert(0, str(Path(__file__).parent))
from _db_common import resolve_dsn

from trading.backtest import run_backtest
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.strategies.octopus_pullback import OctopusPullbackStrategy
from trading.strategies.sma_cross import SmaCrossStrategy
from trading.trailing_stop import TrailingStopManager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


DEFAULT_CAPITAL = 100_000_000.0  # 100 triệu VND / mã


def run_strategy_on_symbols(
    symbols: list[str],
    strategy_factory,
    storage: Storage,
    capital: float = DEFAULT_CAPITAL,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict:
    """Chạy backtest cho một chiến lược trên danh sách mã đọc từ bảng bars."""
    if start is None:
        start = datetime(2020, 1, 1)
    if end is None:
        end = datetime(2030, 1, 1)

    results = []
    strat_name = strategy_factory().__class__.__name__

    for sym in symbols:
        bars = storage.read_bars(sym, start, end)
        strat = strategy_factory()

        if len(bars) < strat.warmup_bars:
            continue

        risk = RiskManager(capital=capital)
        ts_mgr = TrailingStopManager()
        report = run_backtest(bars, strat, risk, ts_mgr, capital)
        total_pnl = report.realized_pnl + report.unrealized_pnl

        results.append(
            {
                "symbol": sym,
                "n_bars": len(bars),
                "trades": report.trades,
                "strat_pnl": total_pnl,
                "realized_pnl": report.realized_pnl,
                "unrealized_pnl": report.unrealized_pnl,
                "bh_pnl": report.buy_and_hold_pnl,
                "diff": total_pnl - report.buy_and_hold_pnl,
                "win_rate": report.win_rate,
                "max_dd": report.max_drawdown,
            }
        )

    return summarize_results(results, strat_name)


def summarize_results(results: list[dict], strat_name: str) -> dict:
    """Tổng hợp thống kê từ danh sách kết quả từng mã."""
    n_symbols = len(results)
    if n_symbols == 0:
        return {
            "name": strat_name,
            "n_symbols": 0,
            "traded_symbols": 0,
            "total_trades": 0,
            "strat_pnl": 0.0,
            "bh_pnl": 0.0,
            "diff": 0.0,
            "win_bh_count": 0,
            "win_bh_pct": 0.0,
            "median_strat_pnl": 0.0,
            "median_bh_pnl": 0.0,
            "median_diff": 0.0,
            "results": [],
        }

    total_trades = sum(r["trades"] for r in results)
    traded_symbols = sum(1 for r in results if r["trades"] > 0)
    strat_pnl = sum(r["strat_pnl"] for r in results)
    bh_pnl = sum(r["bh_pnl"] for r in results)
    diff = strat_pnl - bh_pnl

    win_bh_count = sum(1 for r in results if r["diff"] > 0)
    win_bh_pct = (win_bh_count / n_symbols * 100.0) if n_symbols > 0 else 0.0

    strat_pnls = [r["strat_pnl"] for r in results]
    bh_pnls = [r["bh_pnl"] for r in results]
    diffs = [r["diff"] for r in results]

    median_strat_pnl = statistics.median(strat_pnls) if strat_pnls else 0.0
    median_bh_pnl = statistics.median(bh_pnls) if bh_pnls else 0.0
    median_diff = statistics.median(diffs) if diffs else 0.0

    return {
        "name": strat_name,
        "n_symbols": n_symbols,
        "traded_symbols": traded_symbols,
        "total_trades": total_trades,
        "strat_pnl": strat_pnl,
        "bh_pnl": bh_pnl,
        "diff": diff,
        "win_bh_count": win_bh_count,
        "win_bh_pct": win_bh_pct,
        "median_strat_pnl": median_strat_pnl,
        "median_bh_pnl": median_bh_pnl,
        "median_diff": median_diff,
        "results": results,
    }


def get_all_5m_symbols(storage: Storage) -> list[str]:
    """Lấy toàn bộ danh sách mã có trong bảng bars."""
    with storage.conn() as c:
        rows = c.execute("SELECT DISTINCT symbol FROM bars ORDER BY symbol").fetchall()
    return [r[0] for r in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="Đo diện rộng chiến lược trên bar 5m")
    parser.add_argument("--capital", type=float, default=DEFAULT_CAPITAL, help="Vốn mỗi mã (VND)")
    parser.add_argument("--dsn", default=None, help="Postgres DSN")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn N mã (0 = tất cả)")
    args = parser.parse_args()

    dsn = resolve_dsn(args.dsn)
    storage = Storage(dsn)

    all_symbols = get_all_5m_symbols(storage)
    if args.limit > 0:
        all_symbols = all_symbols[: args.limit]

    print(f"Đang tải và đo lường trên {len(all_symbols)} mã có dữ liệu bar 5 phút (vốn: {args.capital:,.0f} đ/mã)...")

    strategies_to_test = [
        ("Octopus (2 tỷ/20 bar - Mặc định)", lambda: OctopusPullbackStrategy(min_avg_value_20=2_000_000_000.0)),
        ("Octopus (200 triệu/20 bar)", lambda: OctopusPullbackStrategy(min_avg_value_20=200_000_000.0)),
        ("Octopus (50 triệu/20 bar)", lambda: OctopusPullbackStrategy(min_avg_value_20=50_000_000.0)),
        ("Octopus (0 đ - Không lọc TK)", lambda: OctopusPullbackStrategy(min_avg_value_20=0.0)),
        ("SmaCross (fast=10, slow=20)", lambda: SmaCrossStrategy()),
    ]

    summary_tables = []
    for label, factory in strategies_to_test:
        summary = run_strategy_on_symbols(all_symbols, factory, storage, capital=args.capital)
        summary["label"] = label
        summary_tables.append(summary)

    print("\n" + "=" * 120)
    print("BÁO CÁO KẾT QUẢ ĐO LƯỜNG TRÊN KHUNG BAR 5 PHÚT (GÓI Y)")
    print("=" * 120)
    header = (
        f"{'Cấu hình Chiến lược':<35} | {'Mã đủ bar':<10} | {'Mã có lệnh':<10} | "
        f"{'Tổng số lệnh':<12} | {'PnL Chiến lược (VND)':<22} | {'PnL Mua & Giữ (VND)':<20} | {'Thắng B&H (%)'}"
    )
    print(header)
    print("-" * 120)

    for s in summary_tables:
        strat_pnl_str = f"{s['strat_pnl']:+,.0f} đ"
        bh_pnl_str = f"{s['bh_pnl']:+,.0f} đ"
        win_str = f"{s['win_bh_count']}/{s['n_symbols']} ({s['win_bh_pct']:.1f}%)"
        print(
            f"{s['label']:<35} | {s['n_symbols']:<10} | {s['traded_symbols']:<10} | "
            f"{s['total_trades']:<12} | {strat_pnl_str:<22} | {bh_pnl_str:<20} | {win_str}"
        )

    print("=" * 120)
    return 0


if __name__ == "__main__":
    sys.exit(main())
