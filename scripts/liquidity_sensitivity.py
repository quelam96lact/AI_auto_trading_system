"""Đo bảng độ nhạy ngưỡng thanh khoản trên dữ liệu Crypto (Brief đợt 3 / Gói M).

Khảo sát dải ngưỡng min_avg_value_20 cho OctopusPullbackStrategy trên 20 cặp crypto.
Không sửa đổi trading/. Tái sử dụng read_crypto_bars và run_backtest.
"""

import argparse
import sys

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

try:
    from measure_crypto_strategies import read_crypto_bars
except ImportError:
    from scripts.measure_crypto_strategies import read_crypto_bars

from trading.backtest import _buy_and_hold, ever_liquid, run_backtest
from trading.models import Bar
from trading.risk import RiskManager
from trading.strategies.octopus_pullback import OctopusPullbackStrategy
from trading.trailing_stop import TrailingStopManager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_THRESHOLDS = [0.0, 1e5, 1e6, 1e7, 1e8, 5e8, 1e9, 2e9]


def run_threshold_backtest(
    bars_by_symbol: dict[str, list[Bar]],
    threshold: float,
    capital_per_symbol: float = 100_000.0,
    lot_size: int = 1,
) -> dict:
    """Chạy OctopusPullbackStrategy với một ngưỡng thanh khoản cụ thể."""
    total_strat_pnl = 0.0
    total_bh_pnl = 0.0
    total_trades = 0
    total_winning_trades = 0
    qualifying_symbols = 0
    symbols_with_trades = 0
    by_symbol_stats = {}

    for sym, bars in bars_by_symbol.items():
        if not bars:
            continue

        strat = OctopusPullbackStrategy(min_avg_value_20=threshold)
        risk = RiskManager(capital=capital_per_symbol, lot_size=lot_size)
        ts_mgr = TrailingStopManager(sl_multiplier=2.0)

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

        # Kiểm tra xem mã có bao giờ đủ thanh khoản trong suốt chuỗi bar không
        if ever_liquid(bars, threshold, window=20):
            qualifying_symbols += 1
        if rep.trades > 0:
            symbols_with_trades += 1

        by_symbol_stats[sym] = {
            "bars": len(bars),
            "trades": rep.trades,
            "pnl": pnl,
            "bh_pnl": bh_pnl,
            "win_rate": rep.win_rate,
        }

    overall_win_rate = (total_winning_trades / total_trades) if total_trades > 0 else 0.0

    return {
        "threshold": threshold,
        "qualifying_symbols": qualifying_symbols,
        "symbols_with_trades": symbols_with_trades,
        "total_trades": total_trades,
        "win_rate": overall_win_rate,
        "total_strat_pnl": total_strat_pnl,
        "total_bh_pnl": total_bh_pnl,
        "by_symbol": by_symbol_stats,
    }


def compute_sensitivity_table(
    bars_by_symbol: dict[str, list[Bar]],
    thresholds: list[float] | None = None,
    capital_per_symbol: float = 100_000.0,
    lot_size: int = 1,
) -> list[dict]:
    """Tính bảng độ nhạy cho danh sách các ngưỡng thanh khoản."""
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS

    table = []
    for th in thresholds:
        res = run_threshold_backtest(
            bars_by_symbol,
            threshold=th,
            capital_per_symbol=capital_per_symbol,
            lot_size=lot_size,
        )
        table.append(res)
    return table


def print_sensitivity_report(
    table: list[dict],
    interval: str,
    capital_per_symbol: float,
) -> None:
    """In bảng độ nhạy kèm 4 cảnh báo bắt buộc."""
    print("\n" + "=" * 95)
    print(f"BẢNG ĐỘ NHẠY THANH KHOẢN OCTOPUS PULLBACK (Khung: {interval.upper()})")
    print("=" * 95)

    print("\n" + "-" * 95)
    print("BỐN CẢNH BÁO BẮT BUỘC VỀ PHÉP ĐO (THEO BRIEF):")
    print(f"  1. [ĐƠN VỊ TIỀN] Vốn tính bằng USDT ({capital_per_symbol:,.0f} USDT/mã x 20 mã = {capital_per_symbol*20:,.0f} USDT).")
    print("  2. [LÔ GIẢ ĐỊNH] Dùng lot_size = 1 để tránh thiên lệch loại trừ tài sản giá cao.")
    print("  3. [CHƯA TRỪ PHÍ] Phí giao dịch, thuế và trượt giá = 0 (kết quả là LẠC QUAN).")
    print("  4. [THIÊN LỆCH SỐNG SÓT] 20 mã được chọn theo top thanh khoản năm 2026 đo lùi về quá khứ.")
    print("-" * 95)

    print("\n" + "=" * 95)
    print(f"{'Ngưỡng (USDT)':<15} | {'Mã đủ TK':>10} | {'Mã có lệnh':>10} | {'Tổng lệnh':>10} | {'Win Rate':>9} | {'PnL Chiến lược (USDT)':>23} | {'PnL B&H (USDT)':>16}")
    print("-" * 105)

    for row in table:
        th_str = f"{row['threshold']:,.0f}" if row["threshold"] < 1e6 else f"{row['threshold']:.0e}"
        pnl_str = f"{row['total_strat_pnl']:+23,.2f}"
        bh_str = f"{row['total_bh_pnl']:+16,.2f}"
        print(f"{th_str:<15} | {row['qualifying_symbols']:>10}/20 | {row['symbols_with_trades']:>10}/20 | {row['total_trades']:>10} | {row['win_rate']*100:>8.1f}% | {pnl_str} | {bh_str}")
    print("=" * 105)


def main() -> None:
    ap = argparse.ArgumentParser(description="Khảo sát độ nhạy thanh khoản Octopus trên crypto")
    ap.add_argument("--interval", default="1d", choices=["1d", "1h", "both"])
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--lot-size", type=int, default=1)
    ap.add_argument("--dsn", default=None)
    args = ap.parse_args()

    dsn = resolve_dsn(args.dsn)
    intervals = ["1d", "1h"] if args.interval == "both" else [args.interval]

    with psycopg.connect(dsn) as conn:
        for itv in intervals:
            bars = read_crypto_bars(conn, interval=itv)
            if not bars:
                print(f"[Error] Không có dữ liệu cho interval={itv}", file=sys.stderr)
                continue
            table = compute_sensitivity_table(bars, capital_per_symbol=args.capital, lot_size=args.lot_size)
            print_sensitivity_report(table, itv, args.capital)


if __name__ == "__main__":
    main()
