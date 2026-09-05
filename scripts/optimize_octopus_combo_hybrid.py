"""Tối ưu hóa đa chiều tham số (Grid Search & Sensitivity Analysis) cho chiến lược Octopus + Combo Hybrid.

Khảo sát các chiều tham số:
1. k_tp: [1.5, 2.0, 2.3, 2.6, 3.0, 3.5, 4.0, 5.0]
2. x_atr_ratio: [0.05, 0.10, 0.15, 0.20]
3. pullback_red: [1, 2, 3] trong window [3, 5, 8]
4. use_breakeven: False vs True (breakeven_atr_mult = 1.0, 1.5)
5. ema_trend_period: [100, 150, 200]

CLI:
    uv run python scripts/optimize_octopus_combo_hybrid.py [--market crypto|vn] [--interval 1h|1d]
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _db_common import resolve_dsn

from trading.models import Bar
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.pattern_backtest import run_pattern_backtest
from trading.sampling import filter_bars_by_split
from trading.storage.db import Storage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def run_single_eval(
    bars_by_symbol: dict[str, list[Bar]],
    capital: float,
    x_atr_ratio: float,
    k_tp: float,
    allow_short: bool,
    pullback_red: int,
    pullback_window: int,
    ema_trend_period: int,
    use_breakeven: bool,
    breakeven_atr_mult: float,
    fee_rate: float,
    sell_tax_rate: float,
    slippage_bps: float,
    settle_days: int,
    lot_size: int,
    min_avg_value_20: float,
) -> dict:
    total_trades = 0
    winning_trades = 0
    realized_pnl_sl = 0.0
    realized_pnl_tp = 0.0
    traded_symbols = 0

    for bars in bars_by_symbol.values():
        # SL First (Bi quan)
        rep_sl = run_pattern_backtest(
            bars=bars,
            strategy_name="octopus_combo",
            capital=capital,
            x_atr_ratio=x_atr_ratio,
            k_tp=k_tp,
            sl_first=True,
            fee_rate=fee_rate,
            sell_tax_rate=sell_tax_rate,
            slippage_bps=slippage_bps,
            settle_days=settle_days,
            lot_size=lot_size,
            allow_short=allow_short,
            min_avg_value_20=min_avg_value_20,
            pullback_red=pullback_red,
            pullback_window=pullback_window,
            ema_trend_period=ema_trend_period,
            use_breakeven=use_breakeven,
            breakeven_atr_mult=breakeven_atr_mult,
        )
        # TP First (Lạc quan)
        rep_tp = run_pattern_backtest(
            bars=bars,
            strategy_name="octopus_combo",
            capital=capital,
            x_atr_ratio=x_atr_ratio,
            k_tp=k_tp,
            sl_first=False,
            fee_rate=fee_rate,
            sell_tax_rate=sell_tax_rate,
            slippage_bps=slippage_bps,
            settle_days=settle_days,
            lot_size=lot_size,
            allow_short=allow_short,
            min_avg_value_20=min_avg_value_20,
            pullback_red=pullback_red,
            pullback_window=pullback_window,
            ema_trend_period=ema_trend_period,
            use_breakeven=use_breakeven,
            breakeven_atr_mult=breakeven_atr_mult,
        )

        if rep_sl.total_trades > 0:
            traded_symbols += 1
            total_trades += rep_sl.total_trades
            winning_trades += rep_sl.winning_trades
            realized_pnl_sl += rep_sl.realized_pnl
            realized_pnl_tp += rep_tp.realized_pnl

    win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0
    avg_pnl = realized_pnl_sl / total_trades if total_trades > 0 else 0.0

    return {
        "x": x_atr_ratio,
        "k_tp": k_tp,
        "pullback_red": pullback_red,
        "pullback_window": pullback_window,
        "ema_trend": ema_trend_period,
        "breakeven": f"{breakeven_atr_mult}x" if use_breakeven else "Off",
        "traded_symbols": traded_symbols,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "pnl_sl": realized_pnl_sl,
        "pnl_tp": realized_pnl_tp,
        "avg_trade_pnl": avg_pnl,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Tối ưu hóa tham số Hybrid Strategy")
    parser.add_argument("--market", default="crypto", choices=["crypto", "vn"])
    parser.add_argument("--interval", default="1h", choices=["1h", "1d"])
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--dsn", default=None)
    parser.add_argument(
        "--split",
        choices=["train", "validation", "holdout", "all"],
        default="train",
        help="Tập mẫu dữ liệu theo thời gian (train: 2016-2022, validation: 2022-2023, holdout: 2024-2026, all: toàn bộ)",
    )
    parser.add_argument(
        "--unlock-holdout",
        action="store_true",
        default=False,
        help="Cờ bắt buộc để mở khóa truy cập tập holdout hoặc tập all",
    )
    parser.add_argument(
        "--unlock-reason",
        type=str,
        default="",
        help="Lý do mở khóa tập holdout (bắt buộc ghi vào nhật ký docs/holdout-unlock-log.md)",
    )
    args = parser.parse_args()

    dsn = resolve_dsn(args.dsn)
    storage = Storage(dsn)

    data: dict[str, list[Bar]] = {}

    if args.market == "crypto":
        capital = args.capital if args.capital != 100_000_000.0 else 100_000.0
        print(f"Đang tải dữ liệu Crypto perpetual {args.interval}...", flush=True)
        with storage.conn() as c:
            rows = c.execute(
                f"SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE \"interval\" = '{args.interval}' ORDER BY symbol, ts"
            ).fetchall()
            for r in rows:
                data.setdefault(r[0], []).append(
                    Bar(
                        symbol=r[0],
                        ts=r[1],
                        open=float(r[2]),
                        high=float(r[3]),
                        low=float(r[4]),
                        close=float(r[5]),
                        volume=int(r[6]),
                        source="bingx",
                    )
                )
        allow_short = True
        fee_rate = 0.0
        sell_tax_rate = 0.0
        slippage_bps = 0.0
        settle_days = 0
        lot_size = 1
        min_liq = 0.0
        currency = "USDT"
    else:
        capital = 100_000_000.0
        print(
            f"Đang tải dữ liệu Cổ phiếu VN (bars_daily | split: {args.split})...",
            flush=True,
        )
        exclude_file = Path("exclusions.txt")
        excluded: set[str] = set()
        if exclude_file.exists():
            excluded = {
                s.strip().upper()
                for s in exclude_file.read_text(encoding="utf-8").splitlines()
                if s.strip()
            }
        with storage.conn() as c:
            rows = c.execute(
                "SELECT symbol, ts, open, high, low, close, volume FROM bars_daily ORDER BY symbol, ts"
            ).fetchall()
            for r in rows:
                sym = r[0]
                if sym.upper() in excluded:
                    continue
                data.setdefault(sym, []).append(
                    Bar(
                        symbol=sym,
                        ts=r[1],
                        open=float(r[2]),
                        high=float(r[3]),
                        low=float(r[4]),
                        close=float(r[5]),
                        volume=int(r[6]),
                    )
                )
        # Áp dụng cơ chế khóa mẫu Holdout
        filtered_data: dict[str, list[Bar]] = {}
        for i, (sym, bars) in enumerate(data.items()):
            target_log = "docs/holdout-unlock-log.md" if i == 0 else os.devnull
            fb = filter_bars_by_split(
                bars,
                split=args.split,
                unlock_holdout=args.unlock_holdout,
                strategy_name="OctopusComboHybrid",
                config_info=f"Grid Optimization ({args.split})",
                unlock_reason=args.unlock_reason,
                log_file=target_log,
            )
            if fb:
                filtered_data[sym] = fb
        data = filtered_data

        allow_short = False
        fee_rate = FEE_RATE
        sell_tax_rate = SELL_TAX_RATE
        slippage_bps = SLIPPAGE_BPS
        settle_days = 3
        lot_size = 100
        min_liq = 2_000_000_000.0
        currency = "VND"

    print(
        f"Đã tải {len(data)} mã. Bắt đầu quét lưới tham số (Grid Search)...", flush=True
    )

    # 1. Quét k_TP và Breakeven
    results = []
    k_tp_list = (
        [1.5, 2.0, 2.3, 2.6, 3.0, 3.5, 4.0]
        if args.market == "vn"
        else [1.5, 2.0, 2.3, 2.6, 3.0, 3.5, 4.0, 5.0]
    )
    x_list = [0.05, 0.10, 0.15]
    pullback_configs = [(1, 3), (2, 5), (3, 7)]
    trend_periods = [100, 200]
    breakeven_configs = (
        [(False, 0.0)]
        if args.market == "vn"
        else [(False, 0.0), (True, 1.0), (True, 1.5)]
    )

    # Bước 1: Khảo sát k_TP và Breakeven trên baseline x=0.1, pullback=(2,5), trend=200
    print("\n--- PHẦN 1: KHẢO SÁT HỆ SỐ CHỐT LỜI (k_TP) ---", flush=True)
    for ktp in k_tp_list:
        for use_be, be_mult in breakeven_configs:
            res = run_single_eval(
                bars_by_symbol=data,
                capital=capital,
                x_atr_ratio=0.1,
                k_tp=ktp,
                allow_short=allow_short,
                pullback_red=2,
                pullback_window=5,
                ema_trend_period=200,
                use_breakeven=use_be,
                breakeven_atr_mult=be_mult,
                fee_rate=fee_rate,
                sell_tax_rate=sell_tax_rate,
                slippage_bps=slippage_bps,
                settle_days=settle_days,
                lot_size=lot_size,
                min_avg_value_20=min_liq,
            )
            results.append(res)
            be_name = f"BE {be_mult}x" if use_be else "No BE"
            print(
                f"kTP={ktp:<4} | {be_name:<8} | Lệnh: {res['total_trades']:<6} | WR: {res['win_rate']:<5.1f}% | "
                f"PnL (SL-trước): {res['pnl_sl']:+19,.2f} {currency} | PnL (TP-trước): {res['pnl_tp']:+19,.2f} {currency}",
                flush=True,
            )

    # Bước 2: Khảo sát độ nhạy của x_atr_ratio và Pullback depth
    print(
        "\n--- PHẦN 2: KHẢO SÁT KHOẢNG ĐỆM STOP (x_ATR) & ĐỘ SÂU PULLBACK ---",
        flush=True,
    )
    for x in x_list:
        for p_red, p_win in pullback_configs:
            for trend_p in trend_periods:
                res = run_single_eval(
                    bars_by_symbol=data,
                    capital=capital,
                    x_atr_ratio=x,
                    k_tp=2.6 if args.market == "vn" else 2.3,
                    allow_short=allow_short,
                    pullback_red=p_red,
                    pullback_window=p_win,
                    ema_trend_period=trend_p,
                    use_breakeven=False,
                    breakeven_atr_mult=0.0,
                    fee_rate=fee_rate,
                    sell_tax_rate=sell_tax_rate,
                    slippage_bps=slippage_bps,
                    settle_days=settle_days,
                    lot_size=lot_size,
                    min_avg_value_20=min_liq,
                )
                results.append(res)
                print(
                    f"x={x:<4} | Pullback={p_red}/{p_win} | EMA={trend_p:<3} | Lệnh: {res['total_trades']:<6} | WR: {res['win_rate']:<5.1f}% | "
                    f"PnL (SL-trước): {res['pnl_sl']:+16,.2f} {currency} | PnL (TP-trước): {res['pnl_tp']:+16,.2f} {currency}",
                    flush=True,
                )

    # Top 5 cấu hình tốt nhất theo PnL (SL-trước)
    results_sorted = sorted(results, key=lambda r: r["pnl_sl"], reverse=True)
    print("\n" + "=" * 130, flush=True)
    print(
        f"TOP 5 CẤU HÌNH TỐI ƯU NHẤT TRÊN {args.market.upper()} ({args.interval}):",
        flush=True,
    )
    print("=" * 130, flush=True)
    header = f"{'Rank':<5} | {'k_TP':<5} | {'x_ATR':<6} | {'Pullback':<10} | {'EMA Trend':<10} | {'Breakeven':<10} | {'Tổng lệnh':<10} | {'Win Rate':<9} | {'PnL Net (SL-trước)':<22} | {'PnL Net (TP-trước)'}"
    print(header, flush=True)
    print("-" * 130, flush=True)
    for rank, r in enumerate(results_sorted[:5], 1):
        pb_str = f"{r['pullback_red']}/{r['pullback_window']}"
        print(
            f"#{rank:<4} | {r['k_tp']:<5} | {r['x']:<6} | {pb_str:<10} | {r['ema_trend']:<10} | {r['breakeven']:<10} | "
            f"{r['total_trades']:<10} | {r['win_rate']:<8.1f}% | {r['pnl_sl']:+19,.2f} {currency} | {r['pnl_tp']:+19,.2f} {currency}",
            flush=True,
        )
    print("=" * 130, flush=True)
    print(f"Tổng số tổ hợp tham số đã đánh giá: {len(results)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
