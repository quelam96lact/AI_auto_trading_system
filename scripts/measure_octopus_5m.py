"""Đo lường Octopus Pullback trên chuỗi nến 5 PHÚT (Brief đợt 10 - Task 1).

Đặc tả:
- Rổ mã: Đúng các mã trong config/config.yaml (HII, IJC, AAA).
- Dữ liệu: Bảng bars (nến 5m).
- Chi phí: FEE_RATE (0.28% từ 04/10/2026 = 0.25% môi giới + 0.03% phí trả Sở), SELL_TAX_RATE (0.1%), SLIPPAGE_BPS (5) từ trading.paper_broker.
- Thước đo: profit_factor, expectancy, max_drawdown, sharpe từ trading.metrics.
- periods_per_year cho 5m: 51 bar/ngày * 252 ngày/năm = 12,852 kỳ/năm.

CLI:
    uv run python scripts/measure_octopus_5m.py [--config config/config.yaml] [--dsn ...] [--capital 100000000]
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import yaml

# Thêm scripts/ vào sys.path
sys.path.insert(0, str(Path(__file__).parent))
try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

from trading.backtest import run_backtest
from trading.calendar_vn import TZ
from trading.metrics import (
    expectancy,
    max_drawdown,
    portfolio_equity_curve,
    profit_factor,
    sharpe,
)
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.strategies.octopus_pullback import OctopusPullbackStrategy
from trading.trailing_stop import TrailingStopManager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# "51 bar/ngày" là số BUCKET lý thuyết của khung SESSIONS (9:00-11:30 + 13:00-14:45,
# calendar_vn.py:5), KHÔNG phải số bar thực có cú khớp. Đợt 12 (2026-09-07) đo
# thực tế trên toàn rổ: HOSE tối đa 46 bar/ngày có cú khớp (9:00-9:10 và 14:30-14:40
# là phiên đấu giá ATO/ATC, không khớp liên tục nên không sinh bar) — 51 chưa từng
# đúng với dữ liệu thật. Hằng số dưới đây KHÔNG được dùng để tính Sharpe (xem dòng
# `periods_per_year=252.0` ở cuối file, tính trên equity đã gộp NGÀY, không phụ
# thuộc số bar/ngày) — chỉ còn tác dụng làm nhãn mô tả quy ước trong output, giữ
# nguyên số 51 gốc của khung SESSIONS để không lẫn với "46 bar thực" của đợt 12.
PERIODS_PER_YEAR_5M = 51.0 * 252.0  # 12,852 — nhãn mô tả, không dùng để tính Sharpe


def measure_symbol_5m(
    storage: Storage,
    symbol: str,
    frm: datetime,
    to: datetime,
    capital: float,
    fee_rate: float = FEE_RATE,
    sell_tax_rate: float = SELL_TAX_RATE,
    slippage_bps: float = SLIPPAGE_BPS,
) -> dict:
    """Đo 1 mã trên khung 5m với chiến lược Octopus Pullback."""
    bars = storage.read_bars(symbol, frm, to)
    strat = OctopusPullbackStrategy()
    risk = RiskManager(capital=capital)
    ts_mgr = TrailingStopManager()

    rep = run_backtest(
        bars,
        strat,
        risk,
        ts_mgr,
        capital,
        fee_rate=fee_rate,
        sell_tax_rate=sell_tax_rate,
        slippage_bps=slippage_bps,
    )

    strat_pnl = rep.realized_pnl + rep.unrealized_pnl
    trade_pnls = [f.pnl for f in rep.fills if f.side == "SELL" and f.pnl is not None]
    winning_trades = sum(1 for p in trade_pnls if p > 0)
    win_rate = (winning_trades / len(trade_pnls) * 100.0) if trade_pnls else 0.0

    daily_dict = {}
    if rep.equity_curve:
        prev_eq = capital
        for ts, eq in rep.equity_curve:
            if ts is not None:
                d = ts.date()
                delta = eq - prev_eq
                daily_dict[d] = daily_dict.get(d, 0.0) + delta
                prev_eq = eq

    return {
        "symbol": symbol,
        "n_bars": len(bars),
        "start_date": bars[0].ts.strftime("%Y-%m-%d") if bars else "N/A",
        "end_date": bars[-1].ts.strftime("%Y-%m-%d") if bars else "N/A",
        "trades": rep.trades,
        "winning_trades": winning_trades,
        "win_rate": win_rate,
        "strat_pnl": strat_pnl,
        "bh_pnl": rep.buy_and_hold_pnl,
        "diff": strat_pnl - rep.buy_and_hold_pnl,
        "trade_pnls": trade_pnls,
        "daily_pnl": daily_dict,
        "max_drawdown": rep.max_drawdown,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Đo lường Octopus Pullback trên bar 5m"
    )
    parser.add_argument(
        "--config",
        default=str(Path(__file__).parent.parent / "config" / "config.yaml"),
        help="Đường dẫn file config.yaml",
    )
    parser.add_argument("--dsn", default=None)
    parser.add_argument(
        "--capital", type=float, default=100_000_000.0, help="Vốn mỗi mã (VND)"
    )
    parser.add_argument("--from", dest="frm", default="2020-01-01")
    parser.add_argument("--to", dest="to", default="2030-01-01")
    args = parser.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.is_file():
        print(f"LỖI: Không tìm thấy file config tại {cfg_path}", file=sys.stderr)
        return 2

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg_data = yaml.safe_load(f) or {}

    symbols = cfg_data.get("symbols", ["HII", "IJC", "AAA"])
    dsn = resolve_dsn(args.dsn)
    storage = Storage(dsn)

    frm = datetime.strptime(args.frm, "%Y-%m-%d").replace(tzinfo=TZ)
    to = datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=TZ)

    print("=" * 115, flush=True)
    print(
        "BÁO CÁO ĐO LƯỜNG HIỆU NĂNG CHIẾN LƯỢC OCTOPUS PULLBACK TRÊN BAR 5 PHÚT (BRIEF ĐỢT 10 - TASK 1)",
        flush=True,
    )
    print("=" * 115, flush=True)
    print(
        f"Rổ mã cấu hình engine: {symbols} | Vốn: {args.capital:,.0f} VND/mã | Phí SSI: {FEE_RATE*100:.2f}%, Thuế: {SELL_TAX_RATE*100:.2f}%, Trượt: {SLIPPAGE_BPS} bps",
        flush=True,
    )
    print(
        f"Quy ước chuẩn hóa Sharpe: 51 bars/ngày * 252 ngày = {PERIODS_PER_YEAR_5M:,.0f} kỳ/năm (hoặc 252 kỳ nếu gộp ngày)",
        flush=True,
    )
    print("-" * 115, flush=True)

    results = []
    for sym in symbols:
        res = measure_symbol_5m(storage, sym, frm, to, args.capital)
        results.append(res)

    print(
        f"{'Mã':<6} | {'Số bar 5m':<10} | {'Khoảng thời gian':<23} | {'Số lệnh':<8} | {'Win Rate':<9} | "
        f"{'PnL Chiến lược (VND)':<22} | {'PnL B&H (VND)':<18} | {'Max DD':<8}",
        flush=True,
    )
    print("-" * 115, flush=True)

    for r in results:
        period_str = f"{r['start_date']} -> {r['end_date']}"
        print(
            f"{r['symbol']:<6} | {r['n_bars']:<10,} | {period_str:<23} | {r['trades']:<8} | {r['win_rate']:<8.1f}% | "
            f"{r['strat_pnl']:+21,.0f} | {r['bh_pnl']:+17,.0f} | {r['max_drawdown']*100:<7.1f}%",
            flush=True,
        )

    print("-" * 115, flush=True)

    # Tổng hợp danh mục 3 mã
    tot_trades = sum(r["trades"] for r in results)
    tot_strat_pnl = sum(r["strat_pnl"] for r in results)
    tot_bh_pnl = sum(r["bh_pnl"] for r in results)
    all_trade_pnls = [p for r in results for p in r["trade_pnls"]]
    winning_trades = sum(1 for p in all_trade_pnls if p > 0)
    overall_win_rate = (winning_trades / tot_trades * 100.0) if tot_trades > 0 else 0.0

    pf = profit_factor(all_trade_pnls)
    exp = expectancy(all_trade_pnls)

    pnl_by_symbol_by_date = {r["symbol"]: r["daily_pnl"] for r in results}
    curve = portfolio_equity_curve(
        pnl_by_symbol_by_date, capital_per_symbol=args.capital
    )
    mdd_portfolio = max_drawdown(curve)

    daily_returns = []
    if len(curve) >= 2:
        for i in range(1, len(curve)):
            prev = curve[i - 1]
            if prev > 0:
                daily_returns.append((curve[i] - prev) / prev)
    sh_portfolio = sharpe(daily_returns, periods_per_year=252.0)

    pf_str = f"{pf:.2f}" if pf is not None else "N/A (0 lệnh thua / 0 lệnh)"
    sh_str = f"{sh_portfolio:.2f}" if sh_portfolio is not None else "N/A"

    print("TỔNG HỢP DANH MỤC 3 MÃ KHUNG 5 PHÚT:", flush=True)
    print(
        f"- Tổng số lệnh thực thi : {tot_trades:,} lệnh (Thắng: {winning_trades}, Thua: {tot_trades - winning_trades}, Win Rate: {overall_win_rate:.1f}%)",
        flush=True,
    )
    print(
        f"- PnL Chiến lược         : {tot_strat_pnl:+,.0f} VND (so với Mua-và-Giữ: {tot_bh_pnl:+,.0f} VND)",
        flush=True,
    )
    print(f"- Profit Factor          : {pf_str}", flush=True)
    print(f"- Expectancy (TB/lệnh)   : {exp:+,.0f} VND/lệnh", flush=True)
    print(f"- Max Drawdown Danh mục  : {mdd_portfolio * 100:.2f}%", flush=True)
    print(f"- Sharpe Danh mục (252)  : {sh_str}", flush=True)

    print("\n" + "=" * 115, flush=True)
    print("ĐỐI CHIẾU VỚI BASELINE KHUNG NGÀY (DAILY BARS - 1.308 MÃ):", flush=True)
    print("=" * 115, flush=True)
    print(
        f"{'Chỉ số':<30} | {'Khung Ngày (Daily Baseline - 1308 mã)':<40} | {'Khung 5 Phút (3 mã Engine)':<35}",
        flush=True,
    )
    print("-" * 115, flush=True)
    print(
        f"{'Tổng số mã':<30} | {'1,308 mã (439 mã sinh lệnh)':<40} | {f'{len(results)} mã (HII, IJC, AAA)':<35}",
        flush=True,
    )
    print(
        f"{'Tổng số lệnh':<30} | {'1,514 lệnh':<40} | {f'{tot_trades} lệnh':<35}",
        flush=True,
    )
    print(
        f"{'Tổng PnL':<30} | {'-1,615,319,902 VND':<40} | {f'{tot_strat_pnl:+,.0f} VND':<35}",
        flush=True,
    )
    print(f"{'Profit Factor':<30} | {'0.74':<40} | {pf_str:<35}", flush=True)
    print(
        f"{'Expectancy':<30} | {'-1,068,152 VND/lệnh':<40} | {f'{exp:+,.0f} VND/lệnh':<35}",
        flush=True,
    )
    print(
        f"{'Max Drawdown':<30} | {'0.1% (toàn bộ) / 0.4% (sinh lệnh)':<40} | {f'{mdd_portfolio * 100:.2f}%':<35}",
        flush=True,
    )
    print(f"{'Sharpe Ratio':<30} | {'-0.96':<40} | {sh_str:<35}", flush=True)
    print("=" * 115, flush=True)

    print("\nĐÁNH GIÁ TRUNG THỰC VỀ CỠ MẪU (SAMPLE SIZE):", flush=True)
    if tot_trades < 30:
        print(
            f"-> CỠ MẪU QUÁ NHỎ ({tot_trades} lệnh trên ~12,500 bar 5m): KHÔNG ĐỦ Ý NGHĨA THỐNG KÊ ĐỂ KẾT LUẬN.\n"
            f"   Nguyên nhân: Chiến lược Octopus Pullback chỉ sinh lệnh khi thỏa mãn cả 4 điều kiện khắt khe\n"
            f"   (EMA trend, Liquidity gate, Crossover, Pullback red bars). Trên khung 5m của 3 mã, tín hiệu\n"
            f"   xuất hiện cực kỳ thưa thớt (~0.1% số bar).",
            flush=True,
        )
    else:
        print(f"-> Cỡ mẫu: {tot_trades} lệnh.", flush=True)
    print("=" * 115, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
