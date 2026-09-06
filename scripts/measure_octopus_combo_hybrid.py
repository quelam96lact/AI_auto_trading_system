"""Đo lường và so sánh hiệu năng chiến lược lai Octopus + Combo Hybrid.

So sánh trực tiếp:
1. Octopus Gốc (Baseline từ run_backtest).
2. Combo Gốc (kTP = 2.0, 2.3, 2.6).
3. Octopus + Combo Hybrid (Fixed TP: kTP = 1.5, 2.0, 2.3, 2.6).
4. Octopus + Combo Hybrid (Trailing Stop: 2.0x ATR).

Trên 2 thị trường:
- Chứng khoán VN: bars_daily (1.308 mã, T+2.5, Phí 0,25% (FEE_RATE — biểu phí SSI có nguồn),
  Thuế 0,1%, Trượt giá 5bps, Lô 100).
- Crypto Perpetual: bars_crypto (20 cặp, Khung 1D & 1H, T+0, Long & Short).

CLI:
    uv run python scripts/measure_octopus_combo_hybrid.py [--market all|vn|crypto] [--capital 100000000]
"""

import argparse
import sys
from pathlib import Path

# Thêm scripts/ vào sys.path
sys.path.insert(0, str(Path(__file__).parent))
from _db_common import resolve_dsn

from trading.crypto_fees import BINGX_PERP_TAKER
from trading.metrics import (
    expectancy,
    max_drawdown,
    portfolio_equity_curve,
    profit_factor,
    sharpe,
)
from trading.models import Bar
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.pattern_backtest import PatternBacktestReport, run_pattern_backtest
from trading.storage.db import Storage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def evaluate_config(
    bars_by_symbol: dict[str, list[Bar]],
    name: str,
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
    min_avg_value_20: float = 0.0,
    use_trailing_sl: bool = False,
    trailing_atr_mult: float = 2.0,
    periods_per_year: float = 252.0,
) -> dict:
    total_symbols = len(bars_by_symbol)
    reports: list[PatternBacktestReport] = []
    pnl_by_symbol_by_date = {}

    for sym, bars in bars_by_symbol.items():
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
            min_avg_value_20=min_avg_value_20,
            use_trailing_sl=use_trailing_sl,
            trailing_atr_mult=trailing_atr_mult,
        )
        reports.append(rep)

        # Thu thập daily PnL theo ngày đóng lệnh
        daily_d = {}
        for t in rep.trades:
            if t.exit_ts:
                d = t.exit_ts.date()
                daily_d[d] = daily_d.get(d, 0.0) + t.pnl
        pnl_by_symbol_by_date[sym] = daily_d

    traded_reports = [r for r in reports if r.total_trades > 0]
    n_traded = len(traded_reports)
    total_trades = sum(r.total_trades for r in reports)
    total_winning = sum(r.winning_trades for r in reports)
    strat_pnl = sum(r.realized_pnl for r in reports)
    both_touched = sum(r.both_touched_count for r in reports)
    premature_touches = sum(r.premature_touch_count for r in reports)

    bh_pnl_traded = (
        sum(r.buy_and_hold_pnl for r in traded_reports) if traded_reports else 0.0
    )
    win_bh_traded_count = sum(
        1 for r in traded_reports if r.realized_pnl > r.buy_and_hold_pnl
    )
    win_bh_pct = (win_bh_traded_count / n_traded * 100.0) if n_traded > 0 else 0.0
    win_rate = (total_winning / total_trades * 100.0) if total_trades > 0 else 0.0

    all_trade_pnls = [t.pnl for r in reports for t in r.trades]
    pf = profit_factor(all_trade_pnls)
    exp = expectancy(all_trade_pnls)

    curve = portfolio_equity_curve(pnl_by_symbol_by_date, capital_per_symbol=capital)
    mdd = max_drawdown(curve)

    daily_returns = []
    if len(curve) >= 2:
        for i in range(1, len(curve)):
            prev = curve[i - 1]
            if prev > 0:
                daily_returns.append((curve[i] - prev) / prev)
    sh = sharpe(daily_returns, periods_per_year=periods_per_year)

    return {
        "name": name,
        "strategy": strategy_name,
        "x": x_atr_ratio,
        "k_tp": k_tp,
        "use_trailing": use_trailing_sl,
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
        "profit_factor": pf,
        "expectancy": exp,
        "max_drawdown": mdd,
        "sharpe": sh,
    }


def print_comparison_table(
    results_sl: list[dict], results_tp: list[dict], title: str, currency: str
) -> None:
    print("\n" + "=" * 165, flush=True)
    print(f"BÁO CÁO ĐO LƯỜNG SO SÁNH: {title.upper()}", flush=True)
    print("=" * 165, flush=True)
    header = (
        f"{'Mô hình / Cấu hình':<35} | {'Mã có lệnh':<10} | {'Tổng lệnh':<10} | {'Win Rate':<9} | "
        f"{'PnL (SL-trước)':<20} | {'PnL (TP-trước)':<20} | {'PF (SL)':>7} | {'Exp (SL)':>12} | {'Max DD':>8} | {'Sharpe':>7} | {'PnL B&H'}"
    )
    print(header, flush=True)
    print("-" * 165, flush=True)

    for r_sl, r_tp in zip(results_sl, results_tp):
        pnl_sl_str = f"{r_sl['strat_pnl']:+,.2f} {currency}"
        pnl_tp_str = f"{r_tp['strat_pnl']:+,.2f} {currency}"
        bh_str = f"{r_sl['bh_pnl_traded']:+,.2f} {currency}"
        wr_str = f"{r_sl['win_rate']:.1f}%"
        pf_str = (
            f"{r_sl['profit_factor']:.2f}"
            if r_sl["profit_factor"] is not None
            else "N/A"
        )
        sh_str = f"{r_sl['sharpe']:.2f}" if r_sl["sharpe"] is not None else "N/A"
        exp_str = f"{r_sl['expectancy']:+12,.2f}"
        mdd_str = f"{r_sl['max_drawdown']*100:>7.1f}%"

        print(
            f"{r_sl['name']:<35} | {r_sl['traded_symbols']:<10} | {r_sl['total_trades']:<10} | {wr_str:<9} | "
            f"{pnl_sl_str:<20} | {pnl_tp_str:<20} | {pf_str:>7} | {exp_str} | {mdd_str} | {sh_str:>7} | {bh_str}",
            flush=True,
        )

        if r_sl["premature_touches"] > 0:
            print(
                f"   └─ [CẢNH BÁO T+2.5]: Có {r_sl['premature_touches']} lần chạm SL/TP trước ngày settle.",
                flush=True,
            )

    print("=" * 165, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Đo lường và so sánh chiến lược lai Octopus Combo Hybrid"
    )
    parser.add_argument("--market", default="all", choices=["all", "crypto", "vn"])
    parser.add_argument("--capital", type=float, default=100_000_000.0)
    parser.add_argument(
        "--cost-multiplier",
        type=float,
        default=1.0,
        help="Hệ số nhân chi phí (1.0, 1.5, 2.0)",
    )
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    dsn = resolve_dsn(args.dsn)
    storage = Storage(dsn)

    # -----------------------------------------------------------------------
    # 1. THỊ TRƯỜNG CHỨNG KHOÁN VIỆT NAM (bars_daily)
    # -----------------------------------------------------------------------
    if args.market in ("all", "vn"):
        print(
            f"Đang nạp dữ liệu Chứng khoán VN (bars_daily | Chi phí: {args.cost_multiplier:.1f}x)...",
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

        vn_daily: dict[str, list[Bar]] = {}
        with storage.conn() as c:
            rows = c.execute(
                "SELECT symbol, ts, open, high, low, close, volume FROM bars_daily ORDER BY symbol, ts"
            ).fetchall()
            for r in rows:
                sym = r[0]
                if sym.upper() in excluded:
                    continue
                vn_daily.setdefault(sym, []).append(
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

        if args.limit > 0:
            vn_daily = {k: vn_daily[k] for k in list(vn_daily.keys())[: args.limit]}

        print(
            f"Đã nạp {len(vn_daily)} mã cổ phiếu VN ({sum(len(v) for v in vn_daily.values()):,} bars).",
            flush=True,
        )

        fee_vn = FEE_RATE * args.cost_multiplier
        tax_vn = SELL_TAX_RATE * args.cost_multiplier
        slip_vn = SLIPPAGE_BPS * args.cost_multiplier

        configs_vn = [
            # Name, strategy, x_atr, k_tp, min_liq, use_trailing, trailing_mult
            ("1. Combo Gốc (kTP=2.0)", "combo", 0.1, 2.0, 0.0, False, 2.0),
            ("2. Combo Gốc (kTP=2.3)", "combo", 0.1, 2.3, 0.0, False, 2.0),
            ("3. Combo Gốc (kTP=2.6)", "combo", 0.1, 2.6, 0.0, False, 2.0),
            (
                "4. Hybrid: Octopus+Combo (kTP=1.5)",
                "octopus_combo",
                0.1,
                1.5,
                2_000_000_000.0,
                False,
                2.0,
            ),
            (
                "5. Hybrid: Octopus+Combo (kTP=2.0)",
                "octopus_combo",
                0.1,
                2.0,
                2_000_000_000.0,
                False,
                2.0,
            ),
            (
                "6. Hybrid: Octopus+Combo (kTP=2.3)",
                "octopus_combo",
                0.1,
                2.3,
                2_000_000_000.0,
                False,
                2.0,
            ),
            (
                "7. Hybrid: Octopus+Combo (kTP=2.6)",
                "octopus_combo",
                0.1,
                2.6,
                2_000_000_000.0,
                False,
                2.0,
            ),
            (
                "8. Hybrid: Octopus+Combo (Trailing 2.0x)",
                "octopus_combo",
                0.1,
                50.0,
                2_000_000_000.0,
                True,
                2.0,
            ),
        ]

        res_vn_sl = []
        res_vn_tp = []
        for name, strat, x_r, ktp, min_liq, use_trail, trail_mult in configs_vn:
            print(f"  -> Đang đo {name}...", flush=True)
            r_sl = evaluate_config(
                bars_by_symbol=vn_daily,
                name=name,
                strategy_name=strat,
                capital=args.capital,
                x_atr_ratio=x_r,
                k_tp=ktp,
                sl_first=True,
                fee_rate=fee_vn,
                sell_tax_rate=tax_vn,
                slippage_bps=slip_vn,
                settle_days=3,
                lot_size=100,
                allow_short=False,
                min_avg_value_20=min_liq,
                use_trailing_sl=use_trail,
                trailing_atr_mult=trail_mult,
                periods_per_year=252.0,
            )
            r_tp = evaluate_config(
                bars_by_symbol=vn_daily,
                name=name,
                strategy_name=strat,
                capital=args.capital,
                x_atr_ratio=x_r,
                k_tp=ktp,
                sl_first=False,
                fee_rate=fee_vn,
                sell_tax_rate=tax_vn,
                slippage_bps=slip_vn,
                settle_days=3,
                lot_size=100,
                allow_short=False,
                min_avg_value_20=min_liq,
                use_trailing_sl=use_trail,
                trailing_atr_mult=trail_mult,
                periods_per_year=252.0,
            )
            res_vn_sl.append(r_sl)
            res_vn_tp.append(r_tp)

        print_comparison_table(
            res_vn_sl,
            res_vn_tp,
            f"Cổ Phiếu VN — Khung 1D ({len(vn_daily)} mã, Long-Only, T+2.5, Vốn {args.capital:,.0f} VND/mã | Chi phí {args.cost_multiplier:.1f}x)",
            "VND",
        )

    # -----------------------------------------------------------------------
    # 2. THỊ TRƯỜNG CRYPTO PERPETUAL (bars_crypto 1D & 1H)
    # -----------------------------------------------------------------------
    if args.market in ("all", "crypto"):
        print(
            f"\nĐang nạp dữ liệu Crypto (bars_crypto | Chi phí: {args.cost_multiplier:.1f}x)...",
            flush=True,
        )
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

        fee_crypto = BINGX_PERP_TAKER * args.cost_multiplier
        slip_crypto = 0.0 * args.cost_multiplier

        configs_crypto = [
            (
                "1. Combo Gốc (Long+Short, kTP=2.0)",
                "combo",
                0.1,
                2.0,
                0.0,
                False,
                2.0,
                True,
            ),
            (
                "2. Combo Gốc (Long+Short, kTP=2.3)",
                "combo",
                0.1,
                2.3,
                0.0,
                False,
                2.0,
                True,
            ),
            (
                "3. Hybrid: Long-Only (kTP=2.3)",
                "octopus_combo",
                0.1,
                2.3,
                0.0,
                False,
                2.0,
                False,
            ),
            (
                "4. Hybrid: Long+Short (kTP=1.5)",
                "octopus_combo",
                0.1,
                1.5,
                0.0,
                False,
                2.0,
                True,
            ),
            (
                "5. Hybrid: Long+Short (kTP=2.0)",
                "octopus_combo",
                0.1,
                2.0,
                0.0,
                False,
                2.0,
                True,
            ),
            (
                "6. Hybrid: Long+Short (kTP=2.3)",
                "octopus_combo",
                0.1,
                2.3,
                0.0,
                False,
                2.0,
                True,
            ),
            (
                "7. Hybrid: Long+Short (kTP=2.6)",
                "octopus_combo",
                0.1,
                2.6,
                0.0,
                False,
                2.0,
                True,
            ),
            (
                "8. Hybrid: Long+Short (Trailing 2.0x)",
                "octopus_combo",
                0.1,
                50.0,
                0.0,
                True,
                2.0,
                True,
            ),
        ]

        # Crypto 1D
        res_c1d_sl = []
        res_c1d_tp = []
        for (
            name,
            strat,
            x_r,
            ktp,
            min_liq,
            use_trail,
            trail_mult,
            allow_s,
        ) in configs_crypto:
            r_sl = evaluate_config(
                crypto_1d,
                name,
                strat,
                100_000.0,
                x_r,
                ktp,
                True,
                fee_crypto,
                0.0,
                slip_crypto,
                0,
                1,
                allow_s,
                min_liq,
                use_trail,
                trail_mult,
                periods_per_year=365.0,
            )
            r_tp = evaluate_config(
                crypto_1d,
                name,
                strat,
                100_000.0,
                x_r,
                ktp,
                False,
                fee_crypto,
                0.0,
                slip_crypto,
                0,
                1,
                allow_s,
                min_liq,
                use_trail,
                trail_mult,
                periods_per_year=365.0,
            )
            res_c1d_sl.append(r_sl)
            res_c1d_tp.append(r_tp)
        print_comparison_table(
            res_c1d_sl,
            res_c1d_tp,
            f"Crypto Perpetual — Khung 1D (20 Cặp BingX, Vốn 100k USDT/mã | Chi phí {args.cost_multiplier:.1f}x)",
            "USDT",
        )

        # Crypto 1H
        res_c1h_sl = []
        res_c1h_tp = []
        for (
            name,
            strat,
            x_r,
            ktp,
            min_liq,
            use_trail,
            trail_mult,
            allow_s,
        ) in configs_crypto:
            r_sl = evaluate_config(
                crypto_1h,
                name,
                strat,
                100_000.0,
                x_r,
                ktp,
                True,
                fee_crypto,
                0.0,
                slip_crypto,
                0,
                1,
                allow_s,
                min_liq,
                use_trail,
                trail_mult,
                periods_per_year=8760.0,
            )
            r_tp = evaluate_config(
                crypto_1h,
                name,
                strat,
                100_000.0,
                x_r,
                ktp,
                False,
                fee_crypto,
                0.0,
                slip_crypto,
                0,
                1,
                allow_s,
                min_liq,
                use_trail,
                trail_mult,
                periods_per_year=8760.0,
            )
            res_c1h_sl.append(r_sl)
            res_c1h_tp.append(r_tp)
        print_comparison_table(
            res_c1h_sl,
            res_c1h_tp,
            f"Crypto Perpetual — Khung 1H (20 Cặp BingX, Vốn 100k USDT/mã | Chi phí {args.cost_multiplier:.1f}x)",
            "USDT",
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
