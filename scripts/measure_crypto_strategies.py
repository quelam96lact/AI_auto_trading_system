"""Đo lường hiệu suất các chiến lược trên dữ liệu Crypto (Brief đợt 13 / Gói C-b / Brief đợt 22).

- Đọc từ bảng `bars_crypto` (đã nạp từ BingX).
- Chạy các chiến lược trong `trading.backtest.STRATEGIES` qua `run_backtest`.
- Ràng buộc đo lường crypto:
  1. Đơn vị tiền: USDT (ghi rõ vốn).
  2. Lô: Mặc định lot_size = 1.0 (nhận số thực float cho crypto).
  3. Đòn bẩy & Phí: --leverage (mặc định 1.0), fee_rate = BINGX_PERP_TAKER (BingX perpetual VIP0 taker 0.05%), sell_tax_rate=0.0, settle_days=0. Mô phỏng thanh lý theo low của nến khi leverage > 1.
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
from trading.crypto_fees import BINGX_PERP_TAKER
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


from trading.metrics import (
    expectancy,
    max_drawdown,
    portfolio_equity_curve,
    profit_factor,
    sharpe,
)


def run_strategy_on_crypto(
    bars_by_symbol: dict[str, list[Bar]],
    strategy_name: str,
    capital_per_symbol: float = 100_000.0,
    lot_size: float = 1.0,
    sl_multiplier: float = 2.0,
    fee_rate: float = BINGX_PERP_TAKER,
    slippage_bps: float = 0.0,
    periods_per_year: float = 365.0,
    leverage: float = 1.0,
    maintenance_margin_rate: float = 0.005,
) -> dict:
    """Chạy 1 chiến lược trên danh mục các mã crypto.
    Ap dung mo hinh phi crypto: fee_rate = BINGX_PERP_TAKER (BingX perpetual VIP0
    taker 0,05%), tax=0, slippage_bps, settle_days=0. Xem trading/crypto_fees.py.
    (Brief đợt 22): hỗ trợ leverage và mô phỏng thanh lý.
    """
    if strategy_name not in STRATEGIES:
        raise ValueError(f"Chiến lược không hợp lệ: {strategy_name}. Hỗ trợ: {list(STRATEGIES.keys())}")

    results_by_symbol = {}
    total_strat_pnl = 0.0
    total_bh_pnl = 0.0
    total_trades = 0
    total_liquidations = 0
    total_winning_trades = 0
    total_capital = capital_per_symbol * len(bars_by_symbol)
    all_trade_pnls: list[float] = []
    pnl_by_symbol_by_date: dict[str, dict[date, float]] = {}

    total_buy_notional = 0.0
    total_buy_trades = 0

    for sym, bars in bars_by_symbol.items():
        if not bars:
            continue
        strat_cls = STRATEGIES[strategy_name]
        strat = strat_cls()
        risk = RiskManager(capital=capital_per_symbol, lot_size=lot_size, leverage=leverage)
        ts_mgr = TrailingStopManager(sl_multiplier=sl_multiplier)

        rep = run_backtest(
            bars,
            strat,
            risk,
            ts_mgr,
            capital=capital_per_symbol,
            fee_rate=fee_rate,
            sell_tax_rate=0.0,
            slippage_bps=slippage_bps,
            settle_days=0,
            leverage=leverage,
            maintenance_margin_rate=maintenance_margin_rate,
            lot_size=lot_size,
        )

        pnl = rep.realized_pnl + rep.unrealized_pnl
        bh_pnl = _buy_and_hold(bars, capital_per_symbol, fee_rate=fee_rate, sell_tax_rate=0.0, slippage_bps=slippage_bps, lot_size=lot_size)

        winning_trades = sum(1 for f in rep.fills if f.side == "SELL" and f.pnl is not None and f.pnl > 0)
        buy_fills = [f for f in rep.fills if f.side == "BUY"]
        sym_buy_notional = sum(f.qty * f.price for f in buy_fills)
        sym_avg_notional = (sym_buy_notional / len(buy_fills)) if buy_fills else 0.0
        sym_eff_leverage = sym_avg_notional / capital_per_symbol if capital_per_symbol > 0 else 0.0

        total_buy_notional += sym_buy_notional
        total_buy_trades += len(buy_fills)

        total_strat_pnl += pnl
        total_bh_pnl += bh_pnl
        total_trades += rep.trades
        total_liquidations += rep.liquidations
        total_winning_trades += winning_trades

        # Thu thập PnL từng lệnh
        for f in rep.fills:
            if f.side == "SELL" and f.pnl is not None:
                all_trade_pnls.append(f.pnl)

        daily_dict: dict[date, float] = {}
        if rep.equity_curve:
            prev_eq = capital_per_symbol
            for ts, eq in rep.equity_curve:
                if ts is not None:
                    d = ts.date()
                    delta = eq - prev_eq
                    daily_dict[d] = daily_dict.get(d, 0.0) + delta
                    prev_eq = eq
        pnl_by_symbol_by_date[sym] = daily_dict

        results_by_symbol[sym] = {
            "bars": len(bars),
            "trades": rep.trades,
            "liquidations": rep.liquidations,
            "liq_rate": (rep.liquidations / rep.trades) if rep.trades > 0 else 0.0,
            "win_rate": rep.win_rate,
            "strat_pnl": pnl,
            "strat_pnl_pct": (pnl / capital_per_symbol) * 100 if capital_per_symbol > 0 else 0.0,
            "bh_pnl": bh_pnl,
            "eff_leverage": sym_eff_leverage,
            "max_drawdown": rep.max_drawdown,
            "earliest": bars[0].ts.strftime("%Y-%m-%d"),
            "latest": bars[-1].ts.strftime("%Y-%m-%d"),
        }

    overall_win_rate = (total_winning_trades / total_trades) if total_trades > 0 else 0.0
    overall_liq_rate = (total_liquidations / total_trades) if total_trades > 0 else 0.0
    overall_avg_notional = (total_buy_notional / total_buy_trades) if total_buy_trades > 0 else 0.0
    overall_eff_leverage = overall_avg_notional / capital_per_symbol if capital_per_symbol > 0 else 0.0
    pf = profit_factor(all_trade_pnls)
    exp = expectancy(all_trade_pnls)

    # Portfolio curve & Max DD & Sharpe
    curve = portfolio_equity_curve(pnl_by_symbol_by_date, capital_per_symbol=capital_per_symbol)
    mdd = max_drawdown(curve)

    daily_returns = []
    if len(curve) >= 2:
        for i in range(1, len(curve)):
            prev = curve[i - 1]
            if prev > 0:
                daily_returns.append((curve[i] - prev) / prev)
    sh = sharpe(daily_returns, periods_per_year=periods_per_year)

    return {
        "strategy": strategy_name,
        "lot_size": lot_size,
        "leverage": leverage,
        "effective_leverage": overall_eff_leverage,
        "capital_per_symbol": capital_per_symbol,
        "total_capital": total_capital,
        "total_strat_pnl": total_strat_pnl,
        "total_strat_pnl_pct": (total_strat_pnl / total_capital) * 100 if total_capital > 0 else 0.0,
        "total_bh_pnl": total_bh_pnl,
        "total_trades": total_trades,
        "total_liquidations": total_liquidations,
        "liquidation_rate": overall_liq_rate,
        "win_rate": overall_win_rate,
        "profit_factor": pf,
        "expectancy": exp,
        "max_drawdown": mdd,
        "sharpe": sh,
        "by_symbol": results_by_symbol,
    }


def print_crypto_report(
    results: list[dict],
    interval: str,
    capital_per_symbol: float,
    fee_rate: float,
    cost_multiplier: float,
    leverage: float = 1.0,
) -> None:
    """In báo cáo định dạng chuẩn kèm 3 cảnh báo bắt buộc."""
    print("\n" + "=" * 165)
    print(
        f"BÁO CÁO ĐO LƯỜNG CHIẾN LƯỢC TRÊN DỮ LIỆU CRYPTO BINGX (Khung: {interval.upper()} | "
        f"Đòn bẩy: {leverage:.0f}x | Chi phí: {cost_multiplier:.1f}x)"
    )
    print("=" * 165)

    print("\n" + "-" * 165)
    print("BA ĐIỀU BẮT BUỘC PHẢI GHI RÕ VỀ PHÉP ĐO CRYPTO (BRIEF ĐỢT 9 / ĐỢT 22 / ĐỢT 23):")
    print(f"  1. [VIP0 TAKER 0.05% THẬN TRỌNG]: fee_rate={fee_rate:.6f} cho cả hai chiều. Giả định VIP0 là thận trọng nhất.")
    print("  2. [CHƯA MÔ HÌNH HÓA FUNDING]: Phí funding chưa được tính (hạn chế đã biết, thường bất lợi cho phía Long trong uptrend).")
    print(f"  3. [PHÍ TRÊN NOTIONAL]: Phí tính trên giá trị danh nghĩa (~{capital_per_symbol:,.0f} USDT/lệnh), tốn ~{capital_per_symbol*fee_rate*2:,.1f} USDT/vòng mua-bán.")
    print("-" * 165)

    print("\n" + "=" * 175)
    print("BẢNG TỔNG HỢP SO SÁNH CÁC CHIẾN LƯỢC (TỔNG 20 CẶP BINGX):")
    header = (
        f"{'Chiến lược':<18} | {'PnL Chiến lược':>16} | {'% Vốn':>7} | {'PnL Mua-và-Giữ':>16} | "
        f"{'Lệnh':>6} | {'Đòn bẩy thực':>12} | {'Thanh lý':>8} | {'Tỷ lệ TL':>8} | {'Win Rate':>8} | "
        f"{'Profit Factor':>13} | {'Expectancy':>12} | {'Max DD':>8} | {'Sharpe':>8}"
    )
    print(header)
    print("-" * 175)

    for r in results:
        strat_pnl_str = f"{r['total_strat_pnl']:+16,.2f}"
        pnl_pct_str = f"{r['total_strat_pnl_pct']:>6.1f}%"
        bh_pnl_str = f"{r['total_bh_pnl']:+16,.2f}"
        pf_str = f"{r['profit_factor']:.2f}" if r['profit_factor'] is not None else "N/A"
        sh_str = f"{r['sharpe']:.2f}" if r['sharpe'] is not None else "N/A"
        exp_str = f"{r['expectancy']:+12,.2f}"
        mdd_str = f"{r['max_drawdown']*100:>7.1f}%"
        liq_rate_str = f"{r['liquidation_rate']*100:>7.1f}%"
        eff_lev_str = f"{r['effective_leverage']:>10.2f}x"
        print(
            f"{r['strategy']:<18} | {strat_pnl_str} | {pnl_pct_str} | {bh_pnl_str} | "
            f"{r['total_trades']:>6} | {eff_lev_str} | {r['total_liquidations']:>8} | {liq_rate_str:>8} | "
            f"{r['win_rate']*100:>7.1f}% | {pf_str:>13} | {exp_str} | {mdd_str} | {sh_str:>8}"
        )
    print("=" * 175)

    # Chi tiết từng mã cho từng chiến lược
    for r in results:
        print(f"\n--- CHI TIẾT THEO MÃ: {r['strategy'].upper()} (Khung {interval.upper()}, lot_size={r['lot_size']}, leverage={r['leverage']}x) ---")
        print(f"{'#':<3} {'Mã':<15} {'Nến':>6} {'Giai đoạn':<23} {'PnL Chiến lược (USDT)':>23} {'% Vốn':>8} {'PnL Mua-Giữ (USDT)':>21} {'Lệnh':>5} {'Đòn bẩy thực':>13} {'Thanh lý':>8} {'Tỷ lệ TL':>8} {'Win%':>7}")
        print("-" * 155)
        for i, (sym, d) in enumerate(r["by_symbol"].items(), 1):
            date_range = f"{d['earliest']} -> {d['latest']}"
            pnl_s = f"{d['strat_pnl']:+20,.2f}"
            pnl_pct_s = f"{d['strat_pnl_pct']:>7.1f}%"
            bh_s = f"{d['bh_pnl']:+18,.2f}"
            lr_s = f"{d['liq_rate']*100:>7.1f}%"
            eff_s = f"{d['eff_leverage']:>11.2f}x"
            print(f"{i:<3} {sym:<15} {d['bars']:>6} {date_range:<23} {pnl_s} {pnl_pct_s} {bh_s} {d['trades']:>5} {eff_s} {d['liquidations']:>8} {lr_s:>8} {d['win_rate']*100:>6.1f}%")
        print("-" * 155)
def compare_lot_size_effect(
    bars_by_symbol: dict[str, list[Bar]],
    symbols: list[str],
    strategy_name: str = "daily_breakout",
    capital: float = 100_000.0,
    fee_rate: float = BINGX_PERP_TAKER,
    slippage_bps: float = 0.0,
    periods_per_year: float = 365.0,
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
        res100 = run_strategy_on_crypto(
            {sym: bars},
            strategy_name,
            capital_per_symbol=capital,
            lot_size=100,
            fee_rate=fee_rate,
            slippage_bps=slippage_bps,
            periods_per_year=periods_per_year,
        )
        # Run lot_size=1
        res1 = run_strategy_on_crypto(
            {sym: bars},
            strategy_name,
            capital_per_symbol=capital,
            lot_size=1,
            fee_rate=fee_rate,
            slippage_bps=slippage_bps,
            periods_per_year=periods_per_year,
        )

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
    ap.add_argument("--lot-size", type=float, default=1.0, help="Kích thước lô (mặc định 1.0)")
    ap.add_argument("--leverage", type=float, default=1.0, help="Đòn bẩy vị thế (mặc định 1.0)")
    ap.add_argument("--maintenance-margin-rate", type=float, default=0.005, help="Tỷ lệ ký quỹ duy trì (mặc định 0.005 = 0.5%)")
    ap.add_argument("--symbols", default=None, help="Danh sách mã phân cách dấu phẩy")
    ap.add_argument("--compare-lot-size", action="store_true", help="In bảng so sánh lot_size=100 vs lot_size=1")
    ap.add_argument("--cost-multiplier", type=float, default=1.0, help="Hệ số nhân chi phí (1.0, 1.5, 2.0)")
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

    base_fee = BINGX_PERP_TAKER * args.cost_multiplier
    base_slippage = 0.0 * args.cost_multiplier
    periods = 365.0 if args.interval == "1d" else 8760.0

    if args.compare_lot_size:
        high_val_symbols = [s for s in ["BTC-USDT", "ETH-USDT", "SOL-USDT", "AAVE-USDT", "TAO-USDT"] if s in bars_by_symbol]
        compare_lot_size_effect(
            bars_by_symbol,
            high_val_symbols,
            capital=args.capital,
            fee_rate=base_fee,
            slippage_bps=base_slippage,
            periods_per_year=periods,
        )

    strategies_to_run = list(STRATEGIES.keys()) if args.strategy == "all" else [args.strategy]

    results = []
    for sname in strategies_to_run:
        res = run_strategy_on_crypto(
            bars_by_symbol,
            sname,
            capital_per_symbol=args.capital,
            lot_size=args.lot_size,
            fee_rate=base_fee,
            slippage_bps=base_slippage,
            periods_per_year=periods,
            leverage=args.leverage,
            maintenance_margin_rate=args.maintenance_margin_rate,
        )
        results.append(res)

    print_crypto_report(
        results,
        args.interval,
        args.capital,
        fee_rate=base_fee,
        cost_multiplier=args.cost_multiplier,
        leverage=args.leverage,
    )


if __name__ == "__main__":
    main()
