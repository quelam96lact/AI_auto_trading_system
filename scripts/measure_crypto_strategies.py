"""Đo lường hiệu suất các chiến lược trên dữ liệu Crypto (Brief đợt 13 / Gói C-b).

- Đọc từ bảng `bars_crypto` (đã nạp từ BingX).
- Chạy các chiến lược trong `trading.backtest.STRATEGIES` qua `run_backtest`.
- Ràng buộc đo lường crypto:
  1. Đơn vị tiền: USDT (ghi rõ vốn).
  2. Lô: Mặc định lot_size = 1 (giả định, tránh thiên lệch loại trừ tài sản giá cao).
  3. Phí: fee_rate=0.0, sell_tax_rate=0.0, slippage_bps=0.0, settle_days=0 (chưa trừ phí — kết quả lạc quan).
  4. Thiên lệch sống sót: 20 mã chọn theo khối lượng năm 2026 đo lùi về quá khứ.
"""

import argparse
import sys
from datetime import date, datetime

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

from trading.backtest import STRATEGIES, _buy_and_hold, run_backtest
from trading.models import Bar
from trading.risk import RiskManager
from trading.trailing_stop import TrailingStopManager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def read_crypto_bars(
    conn: psycopg.Connection,
    symbols: list[str] | None = None,
    interval: str = "1d",
    from_date: datetime | date | None = None,
    to_date: datetime | date | None = None,
) -> dict[str, list[Bar]]:
    """Đọc nến từ bảng bars_crypto thành dict[symbol, list[Bar]], sắp xếp tăng dần theo ts."""
    query = """
        SELECT symbol, ts, open, high, low, close, volume
        FROM bars_crypto
        WHERE interval = %s
    """
    params: list = [interval]

    if symbols:
        query += " AND symbol = ANY(%s)"
        params.append(symbols)
    if from_date:
        query += " AND ts >= %s"
        params.append(from_date)
    if to_date:
        query += " AND ts <= %s"
        params.append(to_date)

    query += " ORDER BY symbol ASC, ts ASC;"

    bars_by_symbol: dict[str, list[Bar]] = {}
    with conn.cursor() as cur:
        cur.execute(query, params)
        for r in cur.fetchall():
            sym = r[0]
            bar = Bar(
                symbol=sym,
                ts=r[1],
                open=float(r[2]),
                high=float(r[3]),
                low=float(r[4]),
                close=float(r[5]),
                volume=float(r[6]),
                source="bingx",
            )
            bars_by_symbol.setdefault(sym, []).append(bar)

    return bars_by_symbol


def run_strategy_on_crypto(
    bars_by_symbol: dict[str, list[Bar]],
    strategy_name: str,
    capital_per_symbol: float = 100_000.0,
    lot_size: int = 1,
    sl_multiplier: float = 2.0,
) -> dict:
    """Chạy 1 chiến lược trên danh mục các mã crypto.
    Áp dụng mô hình phí crypto: fee=0, tax=0, slippage=0, settle_days=0.
    """
    if strategy_name not in STRATEGIES:
        raise ValueError(f"Chiến lược không hợp lệ: {strategy_name}. Hỗ trợ: {list(STRATEGIES.keys())}")

    results_by_symbol = {}
    total_strat_pnl = 0.0
    total_bh_pnl = 0.0
    total_trades = 0
    total_winning_trades = 0
    total_capital = capital_per_symbol * len(bars_by_symbol)

    for sym, bars in bars_by_symbol.items():
        if not bars:
            continue
        strat_cls = STRATEGIES[strategy_name]
        strat = strat_cls()
        risk = RiskManager(capital=capital_per_symbol, lot_size=lot_size)
        ts_mgr = TrailingStopManager(sl_multiplier=sl_multiplier)

        rep = run_backtest(
            bars,
            strat,
            risk,
            ts_mgr,
            capital=capital_per_symbol,
            fee_rate=0.0,
            sell_tax_rate=0.0,
            slippage_bps=0.0,
            settle_days=0,
        )

        pnl = rep.realized_pnl + rep.unrealized_pnl
        bh_pnl = _buy_and_hold(bars, capital_per_symbol, fee_rate=0.0, sell_tax_rate=0.0, slippage_bps=0.0)

        winning_trades = sum(1 for f in rep.fills if f.side == "SELL" and f.pnl is not None and f.pnl > 0)
        total_strat_pnl += pnl
        total_bh_pnl += bh_pnl
        total_trades += rep.trades
        total_winning_trades += winning_trades

        results_by_symbol[sym] = {
            "bars": len(bars),
            "trades": rep.trades,
            "win_rate": rep.win_rate,
            "strat_pnl": pnl,
            "bh_pnl": bh_pnl,
            "max_drawdown": rep.max_drawdown,
            "earliest": bars[0].ts.strftime("%Y-%m-%d"),
            "latest": bars[-1].ts.strftime("%Y-%m-%d"),
        }

    overall_win_rate = (total_winning_trades / total_trades) if total_trades > 0 else 0.0

    return {
        "strategy": strategy_name,
        "lot_size": lot_size,
        "capital_per_symbol": capital_per_symbol,
        "total_capital": total_capital,
        "total_strat_pnl": total_strat_pnl,
        "total_bh_pnl": total_bh_pnl,
        "total_trades": total_trades,
        "win_rate": overall_win_rate,
        "by_symbol": results_by_symbol,
    }


def print_crypto_report(
    results: list[dict],
    interval: str,
    capital_per_symbol: float,
) -> None:
    """In báo cáo định dạng chuẩn kèm 4 cảnh báo bắt buộc."""
    print("\n" + "=" * 95)
    print(f"BÁO CÁO ĐO LƯỜNG CHIẾN LƯỢC TRÊN DỮ LIỆU CRYPTO BINGX (Khung: {interval.upper()})")
    print("=" * 95)

    print("\n" + "-" * 95)
    print("BỐN CẢNH BÁO BẮT BUỘC VỀ PHÉP ĐO (THEO BRIEF):")
    print(f"  1. [ĐƠN VỊ TIỀN] Vốn tính bằng USDT ({capital_per_symbol:,.0f} USDT/mã).")
    print("  2. [LÔ GIẢ ĐỊNH] Dùng lot_size = 1 để tránh thiên lệch loại trừ tài sản giá cao.")
    print("  3. [CHƯA TRỪ PHÍ] Phí giao dịch, thuế và trượt giá = 0 (kết quả là LẠC QUAN).")
    print("  4. [THIÊN LỆCH SỐNG SÓT] 20 mã được chọn theo top thanh khoản năm 2026 đo lùi về quá khứ.")
    print("-" * 95)

    print("\n" + "=" * 95)
    print("BẢNG TỔNG HỢP SO SÁNH CÁC CHIẾN LƯỢC (TỔNG 20 CẶP):")
    print(f"{'Chiến lược':<20} | {'Vốn tổng (USDT)':>16} | {'PnL Chiến lược':>16} | {'PnL Mua-và-Giữ':>16} | {'Lệnh':>6} | {'Win Rate':>8}")
    print("-" * 95)

    for r in results:
        strat_pnl_str = f"{r['total_strat_pnl']:+16,.2f}"
        bh_pnl_str = f"{r['total_bh_pnl']:+16,.2f}"
        print(f"{r['strategy']:<20} | {r['total_capital']:>16,.0f} | {strat_pnl_str} | {bh_pnl_str} | {r['total_trades']:>6} | {r['win_rate']*100:>7.1f}%")
    print("=" * 95)

    # Chi tiết từng mã cho từng chiến lược
    for r in results:
        print(f"\n--- CHI TIẾT THEO MÃ: {r['strategy'].upper()} (Khung {interval.upper()}, lot_size={r['lot_size']}) ---")
        print(f"{'#':<3} {'Mã':<15} {'Nến':>6} {'Giai đoạn':<23} {'PnL Chiến lược (USDT)':>23} {'PnL Mua-Giữ (USDT)':>21} {'Lệnh':>5} {'Win%':>7}")
        print("-" * 115)
        for i, (sym, d) in enumerate(r["by_symbol"].items(), 1):
            date_range = f"{d['earliest']} -> {d['latest']}"
            pnl_s = f"{d['strat_pnl']:+20,.2f}"
            bh_s = f"{d['bh_pnl']:+18,.2f}"
            print(f"{i:<3} {sym:<15} {d['bars']:>6} {date_range:<23} {pnl_s} {bh_s} {d['trades']:>5} {d['win_rate']*100:>6.1f}%")
        print("-" * 115)


def compare_lot_size_effect(
    bars_by_symbol: dict[str, list[Bar]],
    symbols: list[str],
    strategy_name: str = "daily_breakout",
    capital: float = 100_000.0,
) -> None:
    """So sánh tác động của lot_size = 100 vs lot_size = 1 trên các tài sản giá cao."""
    print("\n" + "=" * 90)
    print(f"KIỂM CHỨNG TÁC ĐỘNG CỦA LÔ (lot_size=100 vs lot_size=1) — CHIẾN LƯỢC: {strategy_name.upper()}")
    print("=" * 90)
    print(f"{'Mã':<15} | {'Giá gần nhất':>14} | {'lot_size=100 Lệnh':>18} | {'lot_size=1 Lệnh':>16} | {'PnL (lot=1)':>16}")
    print("-" * 90)

    for sym in symbols:
        bars = bars_by_symbol.get(sym, [])
        if not bars:
            continue
        last_price = bars[-1].close

        # Run lot_size=100
        res100 = run_strategy_on_crypto({sym: bars}, strategy_name, capital_per_symbol=capital, lot_size=100)
        # Run lot_size=1
        res1 = run_strategy_on_crypto({sym: bars}, strategy_name, capital_per_symbol=capital, lot_size=1)

        t100 = res100["total_trades"]
        t1 = res1["total_trades"]
        pnl1 = res1["total_strat_pnl"]

        print(f"{sym:<15} | {last_price:>14,.1f} | {t100:>18} | {t1:>16} | {pnl1:>16,.2f}")
    print("=" * 90)


def main() -> None:
    ap = argparse.ArgumentParser(description="Đo lường chiến lược trên dữ liệu crypto")
    ap.add_argument("--interval", default="1d", choices=["1d", "1h"])
    ap.add_argument("--strategy", default="all", help="daily_breakout, octopus_pullback, sma_cross, all")
    ap.add_argument("--capital", type=float, default=100_000.0, help="Vốn mỗi mã (USDT)")
    ap.add_argument("--lot-size", type=int, default=1, help="Kích thước lô (mặc định 1)")
    ap.add_argument("--symbols", default=None, help="Danh sách mã phân cách dấu phẩy")
    ap.add_argument("--compare-lot-size", action="store_true", help="In bảng so sánh lot_size=100 vs lot_size=1")
    ap.add_argument("--dsn", default=None)
    args = ap.parse_args()

    dsn = resolve_dsn(args.dsn)
    symbols_filter = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] if args.symbols else None

    with psycopg.connect(dsn) as conn:
        bars_by_symbol = read_crypto_bars(conn, symbols=symbols_filter, interval=args.interval)

    if not bars_by_symbol:
        print(f"[Error] Không tìm thấy dữ liệu trong bars_crypto với interval={args.interval}", file=sys.stderr)
        sys.exit(1)

    print(f"Đã nạp {len(bars_by_symbol)} mã từ bars_crypto (khung {args.interval}).")

    if args.compare_lot_size:
        high_val_symbols = [s for s in ["BTC-USDT", "ETH-USDT", "SOL-USDT", "AAVE-USDT", "TAO-USDT"] if s in bars_by_symbol]
        compare_lot_size_effect(bars_by_symbol, high_val_symbols, capital=args.capital)

    strategies_to_run = list(STRATEGIES.keys()) if args.strategy == "all" else [args.strategy]

    results = []
    for sname in strategies_to_run:
        res = run_strategy_on_crypto(
            bars_by_symbol,
            sname,
            capital_per_symbol=args.capital,
            lot_size=args.lot_size,
        )
        results.append(res)

    print_crypto_report(results, args.interval, args.capital)


if __name__ == "__main__":
    main()
