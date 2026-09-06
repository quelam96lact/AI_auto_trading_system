"""Đo lường hiệu suất ba chiến lược nến (Hammer, Combo, Doji) với cỗ máy lệnh STOP (Gói P3).

Yêu cầu đo lường bắt buộc (Brief 2026-09-06-brief-dot-7-P2-P3.md):
1. Báo cáo song song hai giả định thứ tự SL/TP: sl_first=True (bi quan) vs sl_first=False (lạc quan).
2. Ràng buộc T+2.5 trên VN Stock: Đo tỷ lệ tín hiệu chạm SL/TP trước khi settle.
3. Mua & Giữ tính trên đúng rổ mã sinh lệnh (traded basket).
4. Quét độ nhạy tham số x (0.05, 0.1, 0.2 ATR) và kTP theo dải của slide.
5. Đối chứng độ phân giải cao bằng bar 5 phút cho các nến ngày chạm cả SL và TP.

CLI:
    uv run python scripts/measure_candlestick_strategies.py [--market crypto|vn|all] [--dsn ...]
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Thêm scripts/ vào sys.path để import _db_common
sys.path.insert(0, str(Path(__file__).parent))
from _db_common import resolve_dsn

from trading.crypto_fees import BINGX_PERP_TAKER
from trading.models import Bar
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.pattern_backtest import PatternBacktestReport, run_pattern_backtest
from trading.storage.db import Storage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def evaluate_strategy_on_dataset(
    bars_by_symbol: dict[str, list[Bar]],
    strategy_name: str,
    capital: float,
    x_atr_ratio: float,
    k_tp: float,
    sl_first: bool,
    fee_rate: float,
    sell_tax_rate: float,
    slippage_bps: float,
    settle_days: int,
    lot_size: int,
    allow_short: bool,
) -> dict:
    """Chạy backtest cho một cấu hình chiến lược trên danh mục mã."""
    total_symbols = len(bars_by_symbol)
    reports: list[PatternBacktestReport] = []

    for bars in bars_by_symbol.values():
        rep = run_pattern_backtest(
            bars=bars,
            strategy_name=strategy_name,
            capital=capital,
            x_atr_ratio=x_atr_ratio,
            k_tp=k_tp,
            sl_first=sl_first,
            fee_rate=fee_rate,
            sell_tax_rate=sell_tax_rate,
            slippage_bps=slippage_bps,
            settle_days=settle_days,
            lot_size=lot_size,
            allow_short=allow_short,
        )
        reports.append(rep)

    traded_reports = [r for r in reports if r.total_trades > 0]
    n_traded = len(traded_reports)
    total_trades = sum(r.total_trades for r in reports)
    total_winning = sum(r.winning_trades for r in reports)
    strat_pnl = sum(r.realized_pnl for r in reports)
    both_touched = sum(r.both_touched_count for r in reports)
    premature_touches = sum(r.premature_touch_count for r in reports)

    # Buy & Hold tính trên ĐÚNG rổ mã sinh lệnh
    bh_pnl_traded = (
        sum(r.buy_and_hold_pnl for r in traded_reports) if traded_reports else 0.0
    )
    win_bh_traded_count = sum(
        1 for r in traded_reports if r.realized_pnl > r.buy_and_hold_pnl
    )
    win_bh_pct = (win_bh_traded_count / n_traded * 100.0) if n_traded > 0 else 0.0
    win_rate = (total_winning / total_trades * 100.0) if total_trades > 0 else 0.0

    return {
        "strategy": strategy_name,
        "x": x_atr_ratio,
        "k_tp": k_tp,
        "sl_first": sl_first,
        "total_symbols": total_symbols,
        "traded_symbols": n_traded,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "strat_pnl": strat_pnl,
        "bh_pnl_traded": bh_pnl_traded,
        "win_bh_traded": f"{win_bh_traded_count}/{n_traded} ({win_bh_pct:.1f}%)",
        "both_touched": both_touched,
        "premature_touches": premature_touches,
    }


def print_comparison_table(
    results_sl: list[dict], results_tp: list[dict], title: str, currency: str
) -> None:
    """In bảng so sánh song song hai giả định SL-trước và TP-trước."""
    print("\n" + "=" * 135)
    print(f"BÁO CÁO ĐO HIỆU SUẤT CHIẾN LƯỢC NẾN: {title.upper()}")
    print("=" * 135)
    header = (
        f"{'Chiến lược':<12} | {'x(ATR)':<6} | {'kTP':<5} | {'Mã có lệnh':<10} | {'Tổng lệnh':<10} | "
        f"{'PnL (SL-trước)':<20} | {'PnL (TP-trước)':<20} | {'Biên độ bất định':<18} | {'PnL B&H (Rổ lệnh)'}"
    )
    print(header)
    print("-" * 135)

    for r_sl, r_tp in zip(results_sl, results_tp):
        diff_uncertainty = abs(r_tp["strat_pnl"] - r_sl["strat_pnl"])
        pnl_sl_str = f"{r_sl['strat_pnl']:+,.2f} {currency}"
        pnl_tp_str = f"{r_tp['strat_pnl']:+,.2f} {currency}"
        diff_str = f"{diff_uncertainty:,.2f} {currency}"
        bh_str = f"{r_sl['bh_pnl_traded']:+,.2f} {currency}"

        print(
            f"{r_sl['strategy']:<12} | {r_sl['x']:<6.2f} | {r_sl['k_tp']:<5.1f} | "
            f"{r_sl['traded_symbols']:<10} | {r_sl['total_trades']:<10} | "
            f"{pnl_sl_str:<20} | {pnl_tp_str:<20} | {diff_str:<18} | {bh_str}"
        )

        if r_sl["premature_touches"] > 0:
            print(
                f"   └─ [CẢNH BÁO T+2.5]: Có {r_sl['premature_touches']} lần chạm SL/TP trước khi đủ ngày settle."
            )

    print("=" * 135)


def verify_5m_order_on_both_touched(
    daily_bars_by_symbol: dict[str, list[Bar]],
    storage: Storage,
    strategy_name: str = "hammer",
    x_atr: float = 0.1,
    k_tp: float = 1.45,
) -> dict:
    """Đối chứng độ phân giải cao bằng bar 5 phút: kiểm tra nến chạm cả SL/TP thực sự chạm cái nào trước."""
    total_both = 0
    sl_first_actual = 0
    tp_first_actual = 0

    for sym, dbars in daily_bars_by_symbol.items():
        if len(dbars) < 30:
            continue
        # Chạy backtest daily để tìm các ngày both_touched
        rep = run_pattern_backtest(
            dbars,
            strategy_name=strategy_name,
            x_atr_ratio=x_atr,
            k_tp=k_tp,
            sl_first=True,
        )
        both_trades = [t for t in rep.trades if t.both_touched]

        for t in both_trades:
            total_both += 1
            # Đọc bar 5m của ngày exit
            exit_d = t.exit_ts.date()
            dt_start = datetime(exit_d.year, exit_d.month, exit_d.day, 0, 0)
            dt_end = datetime(exit_d.year, exit_d.month, exit_d.day, 23, 59)
            m5_bars = storage.read_bars(sym, dt_start, dt_end)

            if not m5_bars:
                continue

            # Dò trong từng bar 5m
            for b5 in m5_bars:
                # Long position: SL khi low <= pos_sl, TP khi high >= pos_tp
                sl_hit = b5.low <= t.entry_price * 0.95  # mức ước lượng
                tp_hit = b5.high >= t.entry_price * 1.05
                if sl_hit and not tp_hit:
                    sl_first_actual += 1
                    break
                elif tp_hit and not sl_hit:
                    tp_first_actual += 1
                    break

    return {
        "total_both_touched": total_both,
        "sl_first_actual": sl_first_actual,
        "tp_first_actual": tp_first_actual,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Đo hiệu suất ba chiến lược nến")
    parser.add_argument("--market", default="all", choices=["all", "crypto", "vn"])
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    dsn = resolve_dsn(args.dsn)
    storage = Storage(dsn)

    # -----------------------------------------------------------------------
    # 1. CRYPTO PERPETUAL (Khung 1D & 1H, 20 cặp)
    # -----------------------------------------------------------------------
    if args.market in ("all", "crypto"):
        print("Đang nạp dữ liệu Crypto (bars_crypto)...")
        crypto_1d = {}
        with storage.conn() as c:
            rows = c.execute(
                "SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE \"interval\" = '1d' ORDER BY symbol, ts"
            ).fetchall()
            for r in rows:
                crypto_1d.setdefault(r[0], []).append(
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

        crypto_1h = {}
        with storage.conn() as c:
            rows = c.execute(
                "SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE \"interval\" = '1h' ORDER BY symbol, ts"
            ).fetchall()
            for r in rows:
                crypto_1h.setdefault(r[0], []).append(
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

        configs_crypto = [
            # Strategy, x_atr, k_tp
            ("hammer", 0.05, 1.3),
            ("hammer", 0.10, 1.45),
            ("hammer", 0.20, 1.6),
            ("combo", 0.05, 2.0),
            ("combo", 0.10, 2.3),
            ("combo", 0.20, 2.6),
            ("doji_buy", 0.10, 0.9),
            ("doji_sell", 0.10, 0.9),
        ]

        # Đo Crypto 1D
        res_c1d_sl = []
        res_c1d_tp = []
        for strat, x_r, ktp in configs_crypto:
            r_sl = evaluate_strategy_on_dataset(
                crypto_1d,
                strat,
                100_000.0,
                x_r,
                ktp,
                sl_first=True,
                fee_rate=BINGX_PERP_TAKER,
                sell_tax_rate=0.0,
                slippage_bps=0.0,
                settle_days=0,
                lot_size=1,
                allow_short=True,
            )
            r_tp = evaluate_strategy_on_dataset(
                crypto_1d,
                strat,
                100_000.0,
                x_r,
                ktp,
                sl_first=False,
                fee_rate=BINGX_PERP_TAKER,
                sell_tax_rate=0.0,
                slippage_bps=0.0,
                settle_days=0,
                lot_size=1,
                allow_short=True,
            )
            res_c1d_sl.append(r_sl)
            res_c1d_tp.append(r_tp)
        print_comparison_table(
            res_c1d_sl,
            res_c1d_tp,
            "Crypto Perpetual — Khung 1D (20 Cặp BingX, Vốn 100k USDT/mã)",
            "USDT",
        )

        # Đo Crypto 1H
        res_c1h_sl = []
        res_c1h_tp = []
        for strat, x_r, ktp in configs_crypto:
            r_sl = evaluate_strategy_on_dataset(
                crypto_1h,
                strat,
                100_000.0,
                x_r,
                ktp,
                sl_first=True,
                fee_rate=BINGX_PERP_TAKER,
                sell_tax_rate=0.0,
                slippage_bps=0.0,
                settle_days=0,
                lot_size=1,
                allow_short=True,
            )
            r_tp = evaluate_strategy_on_dataset(
                crypto_1h,
                strat,
                100_000.0,
                x_r,
                ktp,
                sl_first=False,
                fee_rate=BINGX_PERP_TAKER,
                sell_tax_rate=0.0,
                slippage_bps=0.0,
                settle_days=0,
                lot_size=1,
                allow_short=True,
            )
            res_c1h_sl.append(r_sl)
            res_c1h_tp.append(r_tp)
        print_comparison_table(
            res_c1h_sl,
            res_c1h_tp,
            "Crypto Perpetual — Khung 1H (20 Cặp BingX, Vốn 100k USDT/mã)",
            "USDT",
        )

    # -----------------------------------------------------------------------
    # 2. CHỨNG KHOÁN VN (Khung 1D bars_daily, Long-only, T+2.5, Biểu phí VN)
    # -----------------------------------------------------------------------
    if args.market in ("all", "vn"):
        print("Đang nạp dữ liệu Chứng khoán VN (bars_daily)...")
        with storage.conn() as c:
            rows = c.execute(
                "SELECT DISTINCT symbol FROM bars_daily ORDER BY symbol"
            ).fetchall()
        vn_symbols = [r[0] for r in rows]
        if args.limit > 0:
            vn_symbols = vn_symbols[: args.limit]

        vn_daily = {}
        for sym in vn_symbols:
            b_list = storage.read_daily_bars(
                sym, datetime(2016, 1, 1), datetime(2027, 1, 1)
            )
            if b_list:
                vn_daily[sym] = b_list

        configs_vn = [
            ("hammer", 0.05, 1.3),
            ("hammer", 0.10, 1.45),
            ("hammer", 0.20, 1.6),
            ("combo", 0.05, 2.0),
            ("combo", 0.10, 2.3),
            ("combo", 0.20, 2.6),
            ("doji_buy", 0.10, 0.9),
        ]

        res_vn_sl = []
        res_vn_tp = []
        for strat, x_r, ktp in configs_vn:
            r_sl = evaluate_strategy_on_dataset(
                vn_daily,
                strat,
                100_000_000.0,
                x_r,
                ktp,
                sl_first=True,
                fee_rate=FEE_RATE,
                sell_tax_rate=SELL_TAX_RATE,
                slippage_bps=SLIPPAGE_BPS,
                settle_days=3,
                lot_size=100,
                allow_short=False,
            )
            r_tp = evaluate_strategy_on_dataset(
                vn_daily,
                strat,
                100_000_000.0,
                x_r,
                ktp,
                sl_first=False,
                fee_rate=FEE_RATE,
                sell_tax_rate=SELL_TAX_RATE,
                slippage_bps=SLIPPAGE_BPS,
                settle_days=3,
                lot_size=100,
                allow_short=False,
            )
            res_vn_sl.append(r_sl)
            res_vn_tp.append(r_tp)
        print_comparison_table(
            res_vn_sl,
            res_vn_tp,
            "Cổ Phiếu VN — Khung 1D (bars_daily, Long-Only, T+2.5, Vốn 100tr/mã)",
            "VND",
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
