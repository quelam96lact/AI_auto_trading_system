"""CLI đo lường hiệu năng các module perpetual 1H (Brief đợt 37).

Hai module (price-only):
- donchian_breakout
- bollinger_mr

Ràng buộc:
- Múi giờ UTC toàn bộ.
- Tách mẫu IS: 2024-04-27 -> 2025-12-31 UTC, OOS: 2026-01-01 -> 2026-09-08 UTC.
- Mua-và-giữ đối chứng trên cùng kỳ, cùng vốn, cùng phí taker.
- Ba cảnh báo bắt buộc: [PRICE-ONLY], [CHƯA MÔ HÌNH HOÁ FUNDING], [CHƯA MÔ HÌNH HOÁ THANH LÝ].
"""

import argparse
import sys
from datetime import UTC, datetime

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

try:
    from scripts.measure_crypto_strategies import read_crypto_bars
except ImportError:
    from measure_crypto_strategies import read_crypto_bars
from trading.crypto_fees import BINGX_PERP_TAKER
from trading.metrics import expectancy, max_drawdown, profit_factor, sharpe
from trading.models import Bar
from trading.perp_backtest import PerpReport, run_perp_backtest

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ranh giới cố định trong code (không cho sửa qua CLI)
IS_START = datetime(2024, 4, 27, 0, 0, 0, tzinfo=UTC)
IS_END = datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)
OOS_START = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
OOS_END = datetime(2026, 9, 8, 23, 59, 59, tzinfo=UTC)


def compute_buy_and_hold(
    bars: list[Bar],
    capital: float,
    fee_rate: float,
    slippage_bps: float = 0.0,
) -> float:
    """Tính PnL mua-và-giữ đối chứng: mua tại open bar đầu, bán tại close bar cuối."""
    if not bars:
        return 0.0
    first = bars[0]
    last = bars[-1]
    slip = slippage_bps / 10_000.0
    buy_price = first.open * (1.0 + slip)
    sell_price = last.close * (1.0 - slip)

    qty = capital / (buy_price * (1.0 + fee_rate))
    buy_cost = qty * buy_price * (1.0 + fee_rate)
    sell_proceeds = qty * sell_price * (1.0 - fee_rate)
    return sell_proceeds - buy_cost


def run_evaluation(
    bars: list[Bar],
    module_name: str,
    split_name: str,
    capital: float,
    fee_rate: float,
    slippage_bps: float,
    risk_fraction: float,
    max_leverage: float,
    use_ema_filter: bool,
) -> tuple[PerpReport, float]:
    """Chạy backtest cho một module trên một tập split, trả về report và bh_pnl."""
    report = run_perp_backtest(
        bars,
        module=module_name,  # type: ignore[arg-type]
        capital=capital,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        risk_fraction=risk_fraction,
        max_leverage=max_leverage,
        use_ema_filter=use_ema_filter,
    )
    bh_pnl = compute_buy_and_hold(bars, capital, fee_rate, slippage_bps)
    return report, bh_pnl


def print_report_table(
    module_name: str,
    split_name: str,
    report: PerpReport,
    bh_pnl: float,
    capital: float,
) -> None:
    """In bảng kết quả module x split cùng bảng phân rã Long/Short và 3 cảnh báo bắt buộc."""
    trades = report.trades
    n_trades = len(trades)
    pnls = [t.net_pnl for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    win_rate = (wins / n_trades * 100.0) if n_trades > 0 else 0.0
    net_pnl = sum(pnls)
    net_pnl_pct = (net_pnl / capital) * 100.0
    pf = profit_factor(pnls)
    pf_str = f"{pf:.2f}" if pf is not None else "N/A"
    exp = expectancy(pnls)

    eq_values = [eq for _, eq in report.equity_curve]
    max_dd = max_drawdown(eq_values) * 100.0 if eq_values else 0.0

    # Hourly returns cho Sharpe
    hourly_rets = (
        [(eq_values[i] - eq_values[i - 1]) / eq_values[i - 1] for i in range(1, len(eq_values))]
        if len(eq_values) >= 2
        else []
    )
    sh = sharpe(hourly_rets, periods_per_year=8760.0)
    sh_str = f"{sh:.2f}" if sh is not None else "N/A"

    avg_bars = (sum(t.bars_held for t in trades) / n_trades) if n_trades > 0 else 0.0
    total_fees = sum(t.fees for t in trades)
    clipped = sum(1 for t in trades if t.clipped)
    would_liq = sum(1 for t in trades if t.would_liquidate)
    funding_spans_total = sum(t.funding_spans for t in trades)

    print("=" * 105)
    print(f"BÁO CÁO MODULE: {module_name.upper()} | TẬP: {split_name.upper()} | MÃ: {report.symbol}")
    print("=" * 105)

    # In 3 cảnh báo bắt buộc (§3.5)
    print("CẢNH BÁO HỆ THỐNG:")
    print("  [1] [PRICE-ONLY] Điều kiện Order Flow / delta / OFI bị BỎ vì không có dữ liệu. Đây không phải bản đầy đủ.")
    print(f"  [2] [CHƯA MÔ HÌNH HOÁ FUNDING] Tổng mốc funding sống qua: {funding_spans_total} mốc (00/08/16 UTC).")
    if would_liq > 0:
        print(f"  [3] [CHƯA MÔ HÌNH HOÁ THANH LÝ] CẢNH BÁO NGUY HIỂM: có {would_liq} lệnh chạm ngưỡng thanh lý! Kết quả là lạc quan quá mức.")
    else:
        print(f"  [3] [CHƯA MÔ HÌNH HOÁ THANH LÝ] Không có lệnh nào chạm ngưỡng thanh lý (would_liquidate = {would_liq}).")
    print("-" * 105)

    # Bảng số đo tổng hợp (§3.4)
    header = (
        f"{'Signals':<8} {'Expired':<8} {'Cancel':<8} {'Trades':<8} {'WinRate':<9} "
        f"{'Net PnL':<12} {'PnL%':<9} {'BH PnL':<12} {'PF':<7} {'Expectancy':<11} "
        f"{'MaxDD%':<8} {'Sharpe':<8} {'AvgBars':<8} {'Fees':<9} {'Clip':<6} {'Liq':<5} {'FundSpans':<9}"
    )
    print(header)
    print("-" * 105)

    row = (
        f"{report.signals_generated:<8} "
        f"{report.orders_expired:<8} "
        f"{report.orders_cancelled:<8} "
        f"{n_trades:<8} "
        f"{win_rate:>6.1f}%   "
        f"{net_pnl:>10.2f}  "
        f"{net_pnl_pct:>7.2f}% "
        f"{bh_pnl:>10.2f}  "
        f"{pf_str:>6} "
        f"{exp:>10.2f} "
        f"{max_dd:>7.2f}% "
        f"{sh_str:>7} "
        f"{avg_bars:>7.1f} "
        f"{total_fees:>8.2f} "
        f"{clipped:<6} "
        f"{would_liq:<5} "
        f"{funding_spans_total:<9}"
    )
    print(row)
    print("-" * 105)

    # Bảng phân rã Long / Short riêng (§3.4)
    long_trades = [t for t in trades if t.side == "LONG"]
    short_trades = [t for t in trades if t.side == "SHORT"]

    print("PHÂN RÃ THEO CHIỀU (LONG / SHORT):")
    print(f"  {'Side':<8} {'Trades':<8} {'WinRate':<9} {'Net PnL (USDT)':<16} {'Profit Factor':<14}")
    print("  " + "-" * 57)

    for side_name, s_trades in [("LONG", long_trades), ("SHORT", short_trades)]:
        s_n = len(s_trades)
        s_pnls = [t.net_pnl for t in s_trades]
        s_wins = sum(1 for p in s_pnls if p > 0)
        s_wr = (s_wins / s_n * 100.0) if s_n > 0 else 0.0
        s_pnl = sum(s_pnls)
        s_pf = profit_factor(s_pnls)
        s_pf_str = f"{s_pf:.2f}" if s_pf is not None else "N/A"
        print(f"  {side_name:<8} {s_n:<8} {s_wr:>6.1f}%   {s_pnl:>14.2f}   {s_pf_str:>13}")

    print("=" * 105 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Đo lường các module crypto perpetual 1H.")
    parser.add_argument("--symbol", default="BTC-USDT", help="Mã giao dịch (mặc định BTC-USDT)")
    parser.add_argument(
        "--module",
        choices=["donchian_breakout", "bollinger_mr", "all"],
        default="all",
        help="Module cần chạy (mặc định all)",
    )
    parser.add_argument(
        "--split",
        choices=["is", "oos", "both"],
        default="is",
        help="Tập dữ liệu: is | oos | both (mặc định is)",
    )
    parser.add_argument("--capital", type=float, default=500.0, help="Vốn ban đầu USDT (mặc định 500.0)")
    parser.add_argument("--risk-fraction", type=float, default=0.005, help="Tỷ lệ rủi ro mỗi lệnh (mặc định 0.005)")
    parser.add_argument("--max-leverage", type=float, default=10.0, help="Trần đòn bẩy tối đa (mặc định 10.0)")
    parser.add_argument("--slippage-bps", type=float, default=0.0, help="Trượt giá bps mỗi chiều (mặc định 0.0)")
    parser.add_argument("--ema-filter", action="store_true", help="Bật lọc EMA50/EMA200 (chỉ module A)")
    parser.add_argument("--dsn", default=None, help="Postgres connection string")

    args = parser.parse_args()

    # In cảnh báo đỏ nếu chạy OOS (§3.2, §569-571)
    if args.split in ("oos", "both"):
        print("\033[91m" + "=" * 90)
        print("[CẢNH BÁO OOS] OOS chỉ được chạy MỘT LẦN sau khi tham số đã khoá.")
        print("Nếu bạn đang chỉnh tham số, đừng chạy lệnh này.")
        print("=" * 90 + "\033[0m\n")

    dsn = resolve_dsn(args.dsn)
    with psycopg.connect(dsn) as conn:
        data = read_crypto_bars(conn, symbols=[args.symbol], interval="1h")

    all_bars = data.get(args.symbol, [])
    if not all_bars:
        print(f"LỖI: Không tìm thấy nến nào cho mã {args.symbol} trong DB.")
        sys.exit(1)

    # Chia tập IS / OOS (mốc cố định UTC)
    is_bars = [b for b in all_bars if IS_START <= b.ts <= IS_END]
    oos_bars = [b for b in all_bars if OOS_START <= b.ts <= OOS_END]

    splits_to_run: list[tuple[str, list[Bar]]] = []
    if args.split == "is":
        splits_to_run.append(("is", is_bars))
    elif args.split == "oos":
        splits_to_run.append(("oos", oos_bars))
    elif args.split == "both":
        splits_to_run.append(("is", is_bars))
        splits_to_run.append(("oos", oos_bars))

    modules_to_run: list[str] = []
    if args.module == "all":
        modules_to_run = ["donchian_breakout", "bollinger_mr"]
    else:
        modules_to_run = [args.module]

    for split_name, s_bars in splits_to_run:
        print(f"--- ĐANG CHẠY TẬP: {split_name.upper()} (Số nến: {len(s_bars)} | {s_bars[0].ts} -> {s_bars[-1].ts} UTC) ---")
        for mod in modules_to_run:
            report, bh_pnl = run_evaluation(
                bars=s_bars,
                module_name=mod,
                split_name=split_name,
                capital=args.capital,
                fee_rate=BINGX_PERP_TAKER,
                slippage_bps=args.slippage_bps,
                risk_fraction=args.risk_fraction,
                max_leverage=args.max_leverage,
                use_ema_filter=args.ema_filter if mod == "donchian_breakout" else False,
            )
            print_report_table(
                module_name=mod,
                split_name=split_name,
                report=report,
                bh_pnl=bh_pnl,
                capital=args.capital,
            )


if __name__ == "__main__":
    main()
