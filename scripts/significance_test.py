"""Thước đo đối chứng vào lệnh ngẫu nhiên (Brief đợt 38).

Xây dựng phân phối null (null distribution) bằng 1.000 lần bốc thăm ngẫu nhiên
điểm vào lệnh trên cùng chuỗi giá và quy tắc quản trị/thoát lệnh.
Hai đối chứng:
- Đối chứng A (50/50): long/short xác suất bằng nhau.
- Đối chứng B (khớp chiều): giữ đúng tỷ lệ long/short của lượt chạy thật.
"""

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
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
from trading.metrics import calculate_percentile, empirical_percentile_rank
from trading.models import Bar
from trading.perp_backtest import RandomEntryConfig, run_perp_backtest

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Mốc chia UTC cố định từ Đợt 37
IS_START = datetime(2024, 4, 27, 0, 0, 0, tzinfo=UTC)
IS_END = datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)
OOS_START = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
OOS_END = datetime(2026, 9, 8, 23, 59, 59, tzinfo=UTC)



def _worker_single_run(args: tuple) -> tuple[float, int, int]:
    """Hàm worker cho ProcessPoolExecutor.

    args: (seed, bars, module, capital, fee_rate, slippage_bps,
           risk_fraction, max_leverage, use_ema_filter, signal_prob, long_prob)
    Trả về: (net_pnl, trade_count, long_trades_count)
    """
    (
        seed,
        bars,
        module,
        capital,
        fee_rate,
        slippage_bps,
        risk_fraction,
        max_leverage,
        use_ema_filter,
        signal_prob,
        long_prob,
    ) = args

    cfg = RandomEntryConfig(
        seed=seed,
        signal_prob=signal_prob,
        long_prob=long_prob,
    )
    report = run_perp_backtest(
        bars,
        module=module,
        capital=capital,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        risk_fraction=risk_fraction,
        max_leverage=max_leverage,
        use_ema_filter=use_ema_filter,
        random_entry=cfg,
    )
    net_pnl = report.ending_capital - report.starting_capital
    trade_count = len(report.trades)
    long_trades = sum(1 for t in report.trades if t.side == "LONG")
    return net_pnl, trade_count, long_trades


@dataclass(frozen=True)
class NullDistributionStats:
    p05: float
    p25: float
    median: float
    p75: float
    p95: float
    p99: float
    avg_trades: float
    avg_long_ratio: float
    real_percentile: float
    raw_pnls: list[float]


def run_null_simulation(
    bars: list[Bar],
    module: str,
    iterations: int,
    signal_prob: float,
    long_prob: float,
    real_pnl: float,
    capital: float,
    fee_rate: float,
    slippage_bps: float,
    risk_fraction: float,
    max_leverage: float,
    use_ema_filter: bool,
    max_workers: int | None = None,
) -> NullDistributionStats:
    """Chạy N lượt mô phỏng ngẫu nhiên với seed = 0 .. N-1."""
    if iterations <= 0:
        raise ValueError("iterations phải > 0")

    tasks = [
        (
            seed,
            bars,
            module,
            capital,
            fee_rate,
            slippage_bps,
            risk_fraction,
            max_leverage,
            use_ema_filter,
            signal_prob,
            long_prob,
        )
        for seed in range(iterations)
    ]

    workers = max_workers or min(os.cpu_count() or 4, 8)
    if iterations <= 10 or workers <= 1:
        results = [_worker_single_run(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(_worker_single_run, tasks, chunksize=max(1, iterations // (workers * 4))))

    pnls = [r[0] for r in results]
    trades = [r[1] for r in results]
    long_counts = [r[2] for r in results]

    avg_trades = sum(trades) / len(trades) if trades else 0.0
    total_trades = sum(trades)
    avg_long_ratio = (sum(long_counts) / total_trades) if total_trades > 0 else 0.0
    pct = empirical_percentile_rank(pnls, real_pnl)

    return NullDistributionStats(
        p05=calculate_percentile(pnls, 5.0),
        p25=calculate_percentile(pnls, 25.0),
        median=calculate_percentile(pnls, 50.0),
        p75=calculate_percentile(pnls, 75.0),
        p95=calculate_percentile(pnls, 95.0),
        p99=calculate_percentile(pnls, 99.0),
        avg_trades=avg_trades,
        avg_long_ratio=avg_long_ratio,
        real_percentile=pct,
        raw_pnls=pnls,
    )


def calibrate_signal_prob(
    bars: list[Bar],
    module: str,
    real_signals: int,
    real_trades: int,
    long_prob: float,
    capital: float,
    fee_rate: float,
    slippage_bps: float,
    risk_fraction: float,
    max_leverage: float,
    use_ema_filter: bool,
    max_rounds: int = 3,
    probe_iterations: int = 50,
) -> tuple[float, list[dict]]:
    """Hiệu chỉnh signal_prob để số lệnh đối chứng trong khoảng +-20% số lệnh thật (§2.1 & §2.3).

    Trả về: (locked_signal_prob, history_rounds)
    """
    history: list[dict] = []

    if real_signals == 0 or real_trades == 0:
        return 0.0, [{"round": 0, "signal_prob": 0.0, "avg_trades": 0.0, "status": "no_real_trades"}]

    # Ước lượng ban đầu (§2.1.2): chạy prob = 1.0, seed = 0
    probe_cfg = RandomEntryConfig(seed=0, signal_prob=1.0, long_prob=long_prob)
    rep_probe = run_perp_backtest(
        bars,
        module=module,  # type: ignore[arg-type]
        capital=capital,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        risk_fraction=risk_fraction,
        max_leverage=max_leverage,
        use_ema_filter=use_ema_filter,
        random_entry=probe_cfg,
    )
    signals_max = rep_probe.signals_generated
    if signals_max == 0:
        current_prob = 0.0
    else:
        current_prob = real_signals / signals_max

    current_prob = max(0.0001, min(1.0, current_prob))

    for r in range(1, max_rounds + 1):
        stats = run_null_simulation(
            bars=bars,
            module=module,
            iterations=probe_iterations,
            signal_prob=current_prob,
            long_prob=long_prob,
            real_pnl=0.0,
            capital=capital,
            fee_rate=fee_rate,
            slippage_bps=slippage_bps,
            risk_fraction=risk_fraction,
            max_leverage=max_leverage,
            use_ema_filter=use_ema_filter,
        )
        avg_tr = stats.avg_trades
        diff_pct = ((avg_tr - real_trades) / real_trades) * 100.0 if real_trades > 0 else 0.0

        history.append({
            "round": r,
            "signal_prob": current_prob,
            "avg_trades": avg_tr,
            "diff_pct": diff_pct,
            "passed": abs(diff_pct) <= 20.0,
        })

        if abs(diff_pct) <= 20.0:
            return current_prob, history

        if avg_tr > 0:
            adjustment = real_trades / avg_tr
            current_prob = max(0.0001, min(1.0, current_prob * adjustment))
        else:
            current_prob = min(1.0, current_prob * 2.0)

    return current_prob, history


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kiểm định đối chứng vào lệnh ngẫu nhiên (Brief đợt 38)",
    )
    parser.add_argument("--symbol", default="BTC-USDT", help="Cặp giao dịch (mặc định BTC-USDT)")
    parser.add_argument(
        "--module",
        choices=["donchian_breakout", "bollinger_mr"],
        required=True,
        help="Module perpetual cần đo",
    )
    parser.add_argument(
        "--split",
        choices=["is", "oos"],
        required=True,
        help="Tập dữ liệu: is hoặc oos",
    )
    parser.add_argument("--iterations", type=int, default=1000, help="Số lần bốc thăm ngẫu nhiên (mặc định 1000)")
    parser.add_argument("--capital", type=float, default=500.0, help="Vốn ban đầu USDT (mặc định 500.0)")
    parser.add_argument("--risk-fraction", type=float, default=0.005, help="Tỷ lệ rủi ro mỗi lệnh (mặc định 0.005)")
    parser.add_argument("--max-leverage", type=float, default=10.0, help="Trần đòn bẩy tối đa (mặc định 10.0)")
    parser.add_argument("--slippage-bps", type=float, default=0.0, help="Trượt giá bps mỗi chiều (mặc định 0.0)")
    parser.add_argument("--fee-rate", type=float, default=BINGX_PERP_TAKER, help="Tỷ lệ phí taker mỗi chiều")
    parser.add_argument("--use-ema-filter", action="store_true", help="Bật lọc EMA50/EMA200 cho module A")
    parser.add_argument("--dsn", default=None, help="Postgres connection string")
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    start_time = time.time()

    dsn = resolve_dsn(args.dsn)
    with psycopg.connect(dsn) as conn:
        data = read_crypto_bars(conn, symbols=[args.symbol], interval="1h")

    all_bars = data.get(args.symbol, [])
    if not all_bars:
        print(f"LỖI: Không tìm thấy nến nào cho mã {args.symbol} trong DB.")
        sys.exit(1)

    if args.split == "is":
        split_bars = [b for b in all_bars if IS_START <= b.ts <= IS_END]
    else:
        split_bars = [b for b in all_bars if OOS_START <= b.ts <= OOS_END]

    if not split_bars:
        print(f"LỖI: Không có nến nào trong tập {args.split.upper()}.")
        sys.exit(1)

    print("=" * 80)
    print(f"BẮT ĐẦU KIỂM ĐỊNH ĐỐI CHỨNG NGẪU NHIÊN: {args.module.upper()} | TẬP: {args.split.upper()} | MÃ: {args.symbol}")
    print(f"Số lượng nến: {len(split_bars)} ({split_bars[0].ts} -> {split_bars[-1].ts})")
    print(f"Số vòng lặp ngẫu nhiên (iterations): {args.iterations}")
    print(f"Vốn: {args.capital:.1f} USDT | Phí: {args.fee_rate*100:.2f}% | Trượt giá: {args.slippage_bps:.1f} bps")
    print("=" * 80)

    rep_real = run_perp_backtest(
        split_bars,
        module=args.module,  # type: ignore[arg-type]
        capital=args.capital,
        fee_rate=args.fee_rate,
        slippage_bps=args.slippage_bps,
        risk_fraction=args.risk_fraction,
        max_leverage=args.max_leverage,
        use_ema_filter=args.use_ema_filter,
    )
    real_pnl = rep_real.ending_capital - rep_real.starting_capital
    real_trades = len(rep_real.trades)
    real_signals = rep_real.signals_generated
    long_trades_real = sum(1 for t in rep_real.trades if t.side == "LONG")
    short_trades_real = sum(1 for t in rep_real.trades if t.side == "SHORT")
    real_long_ratio = (long_trades_real / real_trades) if real_trades > 0 else 0.5

    print("\n--- KẾT QUẢ CHẠY THẬT ---")
    print(f"Tín hiệu phát ra: {real_signals}")
    print(f"Số lệnh khớp:     {real_trades} (LONG: {long_trades_real}, SHORT: {short_trades_real})")
    print(f"Tỷ lệ LONG thật:  {real_long_ratio*100:.1f}%")
    print(f"Net PnL thật:     {real_pnl:+.2f} USDT ({(real_pnl/args.capital)*100:+.2f}%)")

    print("\n--- HIỆU CHỈNH SIGNAL_PROB (§2.1 & §2.3) ---")
    locked_signal_prob, calib_hist = calibrate_signal_prob(
        bars=split_bars,
        module=args.module,
        real_signals=real_signals,
        real_trades=real_trades,
        long_prob=0.5,
        capital=args.capital,
        fee_rate=args.fee_rate,
        slippage_bps=args.slippage_bps,
        risk_fraction=args.risk_fraction,
        max_leverage=args.max_leverage,
        use_ema_filter=args.use_ema_filter,
        max_rounds=3,
        probe_iterations=min(50, args.iterations),
    )
    for step in calib_hist:
        print(f"  Vòng {step['round']}: prob={step['signal_prob']:.6f} -> số lệnh trung bình={step['avg_trades']:.1f} (lệch {step['diff_pct']:+.1f}%) -> {'ĐẠT' if step['passed'] else 'CHƯA ĐẠT'}")

    print(f"=> KHOÁ SIGNAL_PROB: {locked_signal_prob:.6f}")

    print(f"\n--- ĐANG CHẠY ĐỐI CHỨNG A (50/50, long_prob=0.5, N={args.iterations}) ---")
    t_a_start = time.time()
    stats_a = run_null_simulation(
        bars=split_bars,
        module=args.module,
        iterations=args.iterations,
        signal_prob=locked_signal_prob,
        long_prob=0.5,
        real_pnl=real_pnl,
        capital=args.capital,
        fee_rate=args.fee_rate,
        slippage_bps=args.slippage_bps,
        risk_fraction=args.risk_fraction,
        max_leverage=args.max_leverage,
        use_ema_filter=args.use_ema_filter,
    )
    t_a_elapsed = time.time() - t_a_start
    print(f"Hoàn thành Đối chứng A trong {t_a_elapsed:.1f}s")

    print(f"\n--- ĐANG CHẠY ĐỐI CHỨNG B (Khớp chiều thật {real_long_ratio*100:.1f}%, N={args.iterations}) ---")
    t_b_start = time.time()
    stats_b = run_null_simulation(
        bars=split_bars,
        module=args.module,
        iterations=args.iterations,
        signal_prob=locked_signal_prob,
        long_prob=real_long_ratio,
        real_pnl=real_pnl,
        capital=args.capital,
        fee_rate=args.fee_rate,
        slippage_bps=args.slippage_bps,
        risk_fraction=args.risk_fraction,
        max_leverage=args.max_leverage,
        use_ema_filter=args.use_ema_filter,
    )
    t_b_elapsed = time.time() - t_b_start
    print(f"Hoàn thành Đối chứng B trong {t_b_elapsed:.1f}s")

    diff_trades_a_pct = ((stats_a.avg_trades - real_trades) / real_trades) * 100.0 if real_trades > 0 else 0.0
    diff_trades_b_pct = ((stats_b.avg_trades - real_trades) / real_trades) * 100.0 if real_trades > 0 else 0.0

    print("\n" + "=" * 80)
    print("KIỂM TRA TÍNH LÀNH MẠNH CÔNG CỤ (§2.3):")
    print(f"  1. Số lệnh thật: {real_trades}")
    print(f"     Số lệnh tb Đối chứng A: {stats_a.avg_trades:.1f} (lệch {diff_trades_a_pct:+.1f}%) -> {'[HỢP LỆ +-20%]' if abs(diff_trades_a_pct) <= 20.0 else '[LỆCH >20%]'}")
    print(f"     Số lệnh tb Đối chứng B: {stats_b.avg_trades:.1f} (lệch {diff_trades_b_pct:+.1f}%) -> {'[HỢP LỆ +-20%]' if abs(diff_trades_b_pct) <= 20.0 else '[LỆCH >20%]'}")
    print(f"  2. Tỷ lệ LONG thật: {real_long_ratio*100:.1f}%")
    print(f"     Tỷ lệ LONG tb Đối chứng B: {stats_b.avg_long_ratio*100:.1f}%")
    total_time = time.time() - start_time
    print(f"  3. Tổng thời gian chạy: {total_time:.1f}s ({total_time/60:.2f} phút) -> {'[HỢP LỆ <20m]' if total_time < 1200 else '[CẢNH BÁO >20m]'}")
    print("=" * 80)

    print("\n" + "=" * 80)
    print(f"PHÂN PHỐI NULL VÀ PHÂN VỊ KẾT QUẢ THẬT: {args.module} | {args.split}")
    print("=" * 80)
    print(f"Net PnL THẬT: {real_pnl:+.2f} USDT")
    print("-" * 80)
    print(f"{'Đối chứng':<15} | {'p05':>8} | {'p25':>8} | {'Median':>8} | {'p75':>8} | {'p95':>8} | {'p99':>8} | {'Phân vị THẬT':>13}")
    print("-" * 80)
    print(f"{'A (50/50)':<15} | {stats_a.p05:>8.2f} | {stats_a.p25:>8.2f} | {stats_a.median:>8.2f} | {stats_a.p75:>8.2f} | {stats_a.p95:>8.2f} | {stats_a.p99:>8.2f} | {stats_a.real_percentile:>12.1f}%")
    print(f"{'B (khớp chiều)':<15} | {stats_b.p05:>8.2f} | {stats_b.p25:>8.2f} | {stats_b.median:>8.2f} | {stats_b.p75:>8.2f} | {stats_b.p95:>8.2f} | {stats_b.p99:>8.2f} | {stats_b.real_percentile:>12.1f}%")
    print("=" * 80)

    print("\n--- DIỄN GIẢI KẾT QUẢ (§2.4) ---")
    above_95_a = stats_a.real_percentile >= 95.0
    above_95_b = stats_b.real_percentile >= 95.0

    if above_95_a and above_95_b:
        print("[KẾT LUẬN]: CÓ BẰNG CHỨNG LỢI THẾ. Kết quả thật vượt phân vị 95 ở cả hai đối chứng A và B.")
    elif above_95_a and not above_95_b:
        print("[KẾT LUẬN]: CHỈ LÀ CƯỢC HƯỚNG. Kết quả vượt phân vị 95 ở đối chứng A nhưng dưới 95 ở đối chứng B.")
    else:
        print("[KẾT LUẬN]: KHÔNG CÓ BẰNG CHỨNG LỢI THẾ. Kết quả thật không vượt phân vị 95 của phân phối null.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
