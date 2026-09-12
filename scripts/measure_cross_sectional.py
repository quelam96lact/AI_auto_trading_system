"""CLI đo lường chiến lược động lượng cắt ngang 20 mã, trung tính thị trường (Brief đợt 39).

Quy ước bắt buộc:
- Khung ngày (1D), múi giờ UTC toàn bộ.
- Tách mẫu IS: 2022-02-15 -> 2025-12-31 UTC, OOS: 2026-01-01 -> 2026-09-02 UTC.
- Hai mốc đối chứng: Mua-và-giữ BTC và Mua-và-giữ chia đều toàn vũ trụ.
- Phân phối null: 1.000 lần bốc thăm ngẫu nhiên danh mục trên cùng chuỗi giá và ngày tái cân bằng.
- Ba cảnh báo bắt buộc: [THIÊN LỆCH SỐNG SÓT], [CHƯA MÔ HÌNH HOÁ FUNDING], [VŨ TRỤ THAY ĐỔI].
"""

import argparse
import random
import sys
import time
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

from trading.cross_sectional import CrossSectionalReport, run_cross_sectional
from trading.crypto_fees import BINGX_PERP_TAKER
from trading.metrics import (
    calculate_percentile,
    empirical_percentile_rank,
    max_drawdown,
    profit_factor,
    sharpe,
)
from trading.models import Bar

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Mốc tách mẫu cố định trong code (không nhận từ CLI)
IS_START = datetime(2022, 2, 15, 0, 0, 0, tzinfo=UTC)
IS_END = datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)
OOS_START = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
OOS_END = datetime(2026, 9, 2, 23, 59, 59, tzinfo=UTC)


def compute_btc_buy_and_hold(
    btc_bars: list[Bar],
    start: datetime,
    end: datetime,
    capital: float,
    fee_rate: float,
    slippage_bps: float,
) -> float:
    """Tính PnL mua-và-giữ BTC trên cùng kỳ, cùng vốn, cùng phí."""
    valid_bars = [b for b in btc_bars if start <= b.ts <= end]
    if len(valid_bars) < 2:
        return 0.0

    first = valid_bars[0]
    last = valid_bars[-1]
    slip = slippage_bps / 10000.0

    buy_price = first.open * (1.0 + slip)
    qty = capital / (buy_price * (1.0 + fee_rate))

    sell_price = last.close * (1.0 - slip)
    sell_proceeds = qty * sell_price * (1.0 - fee_rate)
    return sell_proceeds - capital


def _random_portfolio_selector(
    eligible: list[str],
    returns: dict[str, float],
    k: int,
    rng: random.Random | None,
) -> tuple[list[str], list[str]]:
    """Selector bốc thăm ngẫu nhiên k mã long và k mã short từ tập đủ tư cách."""
    assert rng is not None
    shuffled = sorted(eligible)
    rng.shuffle(shuffled)
    return shuffled[:k], shuffled[k : 2 * k]


def compute_period_pnls(report: CrossSectionalReport) -> list[float]:
    """Tính lãi/lỗ (PnL) từng kỳ tái cân bằng để tính Profit Factor."""
    if not report.rebalances:
        return []

    equity_by_day = dict(report.equity_curve)
    pnls: list[float] = []

    for i, reb in enumerate(report.rebalances):
        eq_start = equity_by_day.get(reb.fill_ts, report.starting_capital)
        if i + 1 < len(report.rebalances):
            next_fill_ts = report.rebalances[i + 1].fill_ts
            eq_end = equity_by_day.get(next_fill_ts, eq_start)
        else:
            eq_end = report.ending_capital
        pnls.append(eq_end - eq_start)

    return pnls


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Đo lường chiến lược động lượng cắt ngang 20 mã, trung tính thị trường (Brief đợt 39)",
    )
    parser.add_argument("--split", choices=["is", "oos"], default="is", help="Tập dữ liệu: is hoặc oos")
    parser.add_argument("--lookback", type=int, default=30, help="Số ngày nhìn lại (mặc định 30)")
    parser.add_argument("--rebalance", type=int, default=7, help="Chu kỳ tái cân bằng (mặc định 7 ngày)")
    parser.add_argument("--k", type=int, default=3, help="Số mã mỗi vế (mặc định 3)")
    parser.add_argument("--skip-recent", type=int, default=0, help="Số ngày gần nhất bỏ qua (mặc định 0)")
    parser.add_argument("--iterations", type=int, default=1000, help="Số vòng lặp ngẫu nhiên (mặc định 1000)")
    parser.add_argument("--capital", type=float, default=500.0, help="Vốn ban đầu USDT (mặc định 500.0)")
    parser.add_argument("--slippage-bps", type=float, default=0.0, help="Trượt giá bps mỗi chiều (mặc định 0.0)")
    parser.add_argument("--fee-rate", type=float, default=BINGX_PERP_TAKER, help="Tỷ lệ phí taker mỗi chiều")
    parser.add_argument("--min-universe", type=int, default=10, help="Ngưỡng tối thiểu số mã đủ tư cách (mặc định 10)")
    parser.add_argument("--dsn", default=None, help="Postgres connection string")
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    start_wall_time = time.time()

    # In cảnh báo đỏ nếu chạy OOS (§2.3 & §3.1)
    if args.split == "oos":
        print("\033[91m" + "=" * 90)
        print("[CẢNH BÁO OOS] OOS chỉ được chạy MỘT LẦN sau khi tham số đã khoá.")
        print("Nếu bạn đang chỉnh tham số, đừng chạy lệnh này.")
        print("=" * 90 + "\033[0m\n")

    # Xác định mốc thời gian split
    if args.split == "is":
        split_start = IS_START
        split_end = IS_END
    else:
        split_start = OOS_START
        split_end = OOS_END

    # 1. Đọc dữ liệu 1D toàn bộ mã từ DB
    dsn = resolve_dsn(args.dsn)
    with psycopg.connect(dsn) as conn:
        bars_by_symbol = read_crypto_bars(conn, interval="1d")

    if not bars_by_symbol:
        print("LỖI: Không tìm thấy dữ liệu nến ngày nào trong bars_crypto.")
        sys.exit(1)

    print("=" * 90)
    print(f"BẮT ĐẦU ĐO LƯỜNG ĐỘNG LƯỢNG CẮT NGANG 20 MÃ | TẬP: {args.split.upper()} (UTC)")
    print(f"Khoảng thời gian: {split_start.strftime('%Y-%m-%d')} -> {split_end.strftime('%Y-%m-%d')} UTC")
    print(f"Tham số: lookback={args.lookback}d | rebalance={args.rebalance}d | k={args.k} | skip_recent={args.skip_recent}d")
    print(f"Vốn: {args.capital:.1f} USDT | Phí: {args.fee_rate*100:.2f}% | Trượt giá: {args.slippage_bps:.1f} bps | min_universe={args.min_universe}")
    print("=" * 90)

    # 2. Chạy chiến lược THẬT
    rep_real = run_cross_sectional(
        bars_by_symbol,
        start=split_start,
        end=split_end,
        lookback_days=args.lookback,
        rebalance_days=args.rebalance,
        k=args.k,
        min_universe=args.min_universe,
        capital=args.capital,
        fee_rate=args.fee_rate,
        slippage_bps=args.slippage_bps,
        skip_recent_days=args.skip_recent,
        selector=None,
    )

    real_pnl = rep_real.ending_capital - rep_real.starting_capital
    real_pnl_pct = (real_pnl / rep_real.starting_capital) * 100.0
    turnover_tong = sum(r.turnover_notional for r in rep_real.rebalances)
    total_skipped_fills = sum(r.skipped_fills for r in rep_real.rebalances)

    # Universe stats
    universe_sizes = [r.universe_size for r in rep_real.rebalances]
    univ_min = min(universe_sizes) if universe_sizes else 0
    univ_max = max(universe_sizes) if universe_sizes else 0
    univ_avg = (sum(universe_sizes) / len(universe_sizes)) if universe_sizes else 0.0

    # Risk metrics
    equity_values = [e[1] for e in rep_real.equity_curve]
    max_dd_val = max_drawdown(equity_values) * 100.0 if equity_values else 0.0

    daily_returns = [
        (equity_values[i] - equity_values[i - 1]) / equity_values[i - 1]
        for i in range(1, len(equity_values))
        if equity_values[i - 1] > 0
    ]
    sharpe_val = sharpe(daily_returns, periods_per_year=365.0)

    period_pnls = compute_period_pnls(rep_real)
    pf_val = profit_factor(period_pnls)

    # 3. Tính hai mốc đối chứng
    # (a) Mua-và-giữ BTC
    btc_bars = bars_by_symbol.get("BTC-USDT", [])
    first_fill_ts = rep_real.rebalances[0].fill_ts if rep_real.rebalances else split_start
    bh_btc_pnl = compute_btc_buy_and_hold(
        btc_bars=btc_bars,
        start=first_fill_ts,
        end=split_end,
        capital=args.capital,
        fee_rate=args.fee_rate,
        slippage_bps=args.slippage_bps,
    )

    # (b) Mua-và-giữ chia đều toàn vũ trụ (long-only equal-weight, cùng chu kỳ 7 ngày)
    rep_bh_univ = run_cross_sectional(
        bars_by_symbol,
        start=split_start,
        end=split_end,
        lookback_days=args.lookback,
        rebalance_days=args.rebalance,
        k=args.k,
        min_universe=args.min_universe,
        capital=args.capital,
        fee_rate=args.fee_rate,
        slippage_bps=args.slippage_bps,
        skip_recent_days=args.skip_recent,
        long_only=True,
    )
    bh_univ_pnl = rep_bh_univ.ending_capital - rep_bh_univ.starting_capital

    # 4. Chạy phân phối null (N iterations bốc thăm ngẫu nhiên danh mục)
    print(f"\n--- ĐANG CHẠY PHÂN PHỐI NULL DANH MỤC NGẪU NHIÊN (N={args.iterations}) ---")
    print("(Không cần hiệu chỉnh xác suất: số kỳ tái cân bằng và số vị thế giống hệt nhau theo thiết kế)")
    t_null_start = time.time()
    null_pnls: list[float] = []

    for seed in range(args.iterations):
        rng = random.Random(seed)
        rep_null = run_cross_sectional(
            bars_by_symbol,
            start=split_start,
            end=split_end,
            lookback_days=args.lookback,
            rebalance_days=args.rebalance,
            k=args.k,
            min_universe=args.min_universe,
            capital=args.capital,
            fee_rate=args.fee_rate,
            slippage_bps=args.slippage_bps,
            skip_recent_days=args.skip_recent,
            selector=_random_portfolio_selector,
            rng=rng,
        )
        null_pnl = rep_null.ending_capital - rep_null.starting_capital
        null_pnls.append(null_pnl)

    t_null_elapsed = time.time() - t_null_start
    print(f"Hoàn thành {args.iterations} vòng bốc thăm null trong {t_null_elapsed:.2f}s")

    # Thống kê phân phối null
    p05 = calculate_percentile(null_pnls, 5.0)
    p25 = calculate_percentile(null_pnls, 25.0)
    median_val = calculate_percentile(null_pnls, 50.0)
    p75 = calculate_percentile(null_pnls, 75.0)
    p95 = calculate_percentile(null_pnls, 95.0)
    p99 = calculate_percentile(null_pnls, 99.0)
    real_pct = empirical_percentile_rank(null_pnls, real_pnl)

    # 5. In Ba cảnh báo bắt buộc (§2.2)
    print("\n" + "=" * 90)
    print("CẢNH BÁO HỆ THỐNG BẮT BUỘC:")
    print("  [1] [THIÊN LỆCH SỐNG SÓT] 20 mã chọn theo khối lượng 2026 đo lùi về quá khứ; đồng đã chết")
    print("      không có trong rổ; thiên lệch này bơm phồng vế long. Không sửa được bằng dữ liệu hiện có.")
    print("  [2] [CHƯA MÔ HÌNH HOÁ FUNDING] Vế short nhận/trả funding tuỳ chế độ thị trường, khoản này")
    print("      có thể cùng bậc độ lớn với kết quả.")
    print(f"  [3] [VŨ TRỤ THAY ĐỔI] Số mã đủ tư cách: min={univ_min} | max={univ_max} | trung bình={univ_avg:.1f}")
    print("=" * 90)

    # 6. In Bảng kết quả thật (§2.1a)
    print("\n" + "=" * 90)
    print("KẾT QUẢ THẬT (CROSS-SECTIONAL MOMENTUM):")
    print("=" * 90)
    pf_str = f"{pf_val:.2f}" if pf_val is not None else "N/A"
    sharpe_str = f"{sharpe_val:.2f}" if sharpe_val is not None else "N/A"
    print(f"{'Rebalances':<11} | {'SkipReb':<8} | {'SkipFills':<9} | {'Net PnL (USDT)':<14} | {'PnL %':<8} | {'ProfitFactor':<12} | {'MaxDD %':<8} | {'Sharpe':<8} | {'Fees (USDT)':<11} | {'Turnover':<10} | {'Univ TB':<7}")
    print("-" * 90)
    print(f"{len(rep_real.rebalances):<11} | {rep_real.skipped_rebalances:<8} | {total_skipped_fills:<9} | {real_pnl:>+14.2f} | {real_pnl_pct:>+7.2f}% | {pf_str:>12} | {max_dd_val:>7.2f}% | {sharpe_str:>8} | {rep_real.total_fees:>11.2f} | {turnover_tong:>10.1f} | {univ_avg:>7.1f}")
    print("=" * 90)

    # 7. In Hai mốc đối chứng (§2.1b)
    print("\nHAI MỐC ĐỐI CHỨNG (CÙNG KỲ, CÙNG VỐN 500 USDT, CÙNG PHÍ):")
    print(f"  1. Mua-và-giữ BTC                     : {bh_btc_pnl:>+10.2f} USDT ({(bh_btc_pnl/args.capital)*100:>+6.2f}%)")
    print(f"  2. Mua-và-giữ chia đều toàn vũ trụ (7d): {bh_univ_pnl:>+10.2f} USDT ({(bh_univ_pnl/args.capital)*100:>+6.2f}%)")
    print("  -------------------------------------------------------------")
    print(f"  Chênh lệch (Chiến lược - BH BTC)       : {real_pnl - bh_btc_pnl:>+10.2f} USDT")
    print(f"  Chênh lệch (Chiến lược - BH Vũ trụ)    : {real_pnl - bh_univ_pnl:>+10.2f} USDT")

    # 8. In Phân phối null và phân vị (§2.1c)
    print("\n" + "=" * 90)
    print(f"PHÂN PHỐI NULL DANH MỤC NGẪU NHIÊN ({args.iterations} LẦN BỐC THĂM):")
    print("=" * 90)
    print(f"Net PnL THẬT: {real_pnl:+.2f} USDT")
    print("-" * 90)
    print(f"{'Mô hình':<22} | {'p05':>8} | {'p25':>8} | {'Median':>8} | {'p75':>8} | {'p95':>8} | {'p99':>8} | {'Phân vị THẬT':>13}")
    print("-" * 90)
    print(f"{'Đối chứng ngẫu nhiên':<22} | {p05:>8.2f} | {p25:>8.2f} | {median_val:>8.2f} | {p75:>8.2f} | {p95:>8.2f} | {p99:>8.2f} | {real_pct:>12.1f}%")
    print("=" * 90)

    # 9. Kết luận tiêu chí (§3.3)
    print("\n--- DIỄN GIẢI KẾT QUẢ (§3.3) ---")
    cond1 = real_pnl > 0
    cond2 = len(rep_real.rebalances) >= 20
    cond3 = real_pct >= 95.0

    if cond1 and cond2 and cond3:
        print("[KẾT LUẬN]: ĐÁNG NGHIÊN CỨU TIẾP. Cả ba tiêu chí đều thoả mãn: Net PnL > 0, Rebalances >= 20, và phân vị >= 95%.")
    else:
        reasons = []
        if not cond1:
            reasons.append(f"Net PnL âm ({real_pnl:+.2f} USDT)")
        if not cond2:
            reasons.append(f"Số kỳ tái cân bằng chưa đủ 20 ({len(rep_real.rebalances)})")
        if not cond3:
            reasons.append(f"Phân vị chưa vượt 95% ({real_pct:.1f}%)")
        print(f"[KẾT LUẬN]: KHÔNG ĐẠT TIÊU CHÍ NGHIÊN CỨU TIẾP ({', '.join(reasons)}).")

    total_wall_time = time.time() - start_wall_time
    print(f"\nTổng thời gian chạy lệnh: {total_wall_time:.2f}s ({total_wall_time/60:.2f} phút)")
    print("=" * 90 + "\n")


if __name__ == "__main__":
    main()
