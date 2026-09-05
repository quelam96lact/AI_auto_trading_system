"""Đo lường trung thực OctopusComboStrategy trên đường ống run_backtest (Brief đợt 8).

Chạy song song và đặt cạnh nhau:
1. OctopusPullbackStrategy (Baseline)
2. OctopusComboStrategy (Đăng ký mới)

Giao thức giữ nguyên của Gói Q / Báo cáo 01/09:
- bars_daily 2.982.903 dòng (kỳ 2016-01-04 -> 2026-08-13).
- Vốn 1.000.000.000 VND / mã, chạy độc lập từng mã rồi cộng dồn.
- Biểu phí VN, T+2.5, loại bỏ mã trong exclusions.txt.
"""

import argparse
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from _db_common import resolve_dsn
    from measure_strategy import liquidity_spec
except ImportError:
    from scripts._db_common import resolve_dsn
    from scripts.measure_strategy import liquidity_spec

from trading.backtest import STRATEGIES, ever_liquid, run_backtest
from trading.calendar_vn import TZ
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.trailing_stop import TrailingStopManager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_CAPITAL = 1_000_000_000.0
DEFAULT_FROM = "2016-01-04"
DEFAULT_TO = "2026-08-13"


def measure_symbol_for_strat(
    bars,
    capital: float,
    strategy_cls,
    liq_spec: tuple[float, int] | None,
) -> dict:
    strat = strategy_cls()
    risk = RiskManager(capital=capital)
    ts_mgr = TrailingStopManager()

    rep = run_backtest(bars, strat, risk, ts_mgr, capital)
    strat_pnl = rep.realized_pnl + rep.unrealized_pnl

    return {
        "n_bars": len(bars),
        "trades": rep.trades,
        "win_rate": rep.win_rate,
        "strat_pnl": strat_pnl,
        "bh_pnl": rep.buy_and_hold_pnl,
        "diff": strat_pnl - rep.buy_and_hold_pnl,
        "liquid": ever_liquid(bars, *liq_spec) if liq_spec else False,
    }


def analyze_basket(results: list[dict], name: str) -> dict:
    n = len(results)
    if n == 0:
        return {
            "name": name,
            "n_symbols": 0,
            "total_trades": 0,
            "strat_pnl": 0.0,
            "bh_pnl": 0.0,
            "diff": 0.0,
            "win_bh_count": 0,
            "win_bh_pct": 0.0,
            "median_diff": 0.0,
            "median_strat": 0.0,
            "median_bh": 0.0,
        }

    tot_strat = sum(r["strat_pnl"] for r in results)
    tot_bh = sum(r["bh_pnl"] for r in results)
    tot_trades = sum(r["trades"] for r in results)
    diffs = [r["diff"] for r in results]
    win_bh_count = sum(1 for d in diffs if d > 0)
    win_bh_pct = (win_bh_count / n) * 100.0

    return {
        "name": name,
        "n_symbols": n,
        "total_trades": tot_trades,
        "strat_pnl": tot_strat,
        "bh_pnl": tot_bh,
        "diff": tot_strat - tot_bh,
        "win_bh_count": win_bh_count,
        "win_bh_pct": win_bh_pct,
        "median_diff": statistics.median(diffs) if diffs else 0.0,
        "median_strat": (
            statistics.median([r["strat_pnl"] for r in results]) if results else 0.0
        ),
        "median_bh": (
            statistics.median([r["bh_pnl"] for r in results]) if results else 0.0
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Đo lường trung thực OctopusComboStrategy và đối chiếu Octopus Baseline")
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--capital", type=float, default=DEFAULT_CAPITAL)
    ap.add_argument("--from", dest="frm", default=DEFAULT_FROM)
    ap.add_argument("--to", dest="to", default=DEFAULT_TO)
    ap.add_argument("--exclude-file", default="exclusions.txt")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    frm = datetime.strptime(args.frm, "%Y-%m-%d").replace(tzinfo=TZ)
    to = datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=TZ) + timedelta(days=1)

    storage = Storage(resolve_dsn(args.dsn))
    with storage.conn() as c:
        symbols = [
            r[0]
            for r in c.execute("SELECT DISTINCT symbol FROM bars_daily ORDER BY symbol")
        ]

    excluded: set[str] = set()
    if args.exclude_file and Path(args.exclude_file).exists():
        excluded = {
            s.strip().upper()
            for s in Path(args.exclude_file).read_text(encoding="utf-8").splitlines()
            if s.strip()
        }
        symbols = [s for s in symbols if s.upper() not in excluded]

    if args.limit > 0:
        symbols = symbols[:args.limit]

    print(f"Đang nạp dữ liệu cho {len(symbols)} mã...", flush=True)

    oct_cls = STRATEGIES["octopus_pullback"]
    combo_cls = STRATEGIES["octopus_combo"]

    oct_liq_spec = liquidity_spec(oct_cls())
    combo_liq_spec = liquidity_spec(combo_cls())

    res_oct_all = []
    res_combo_all = []

    for i, sym in enumerate(symbols, 1):
        bars = storage.read_daily_bars(sym, frm, to)
        r_oct = measure_symbol_for_strat(bars, args.capital, oct_cls, oct_liq_spec)
        r_combo = measure_symbol_for_strat(bars, args.capital, combo_cls, combo_liq_spec)
        res_oct_all.append(r_oct)
        res_combo_all.append(r_combo)
        if i % 200 == 0 or i == len(symbols):
            print(f"  ...đã đo {i}/{len(symbols)} mã", file=sys.stderr, flush=True)

    # Lọc rổ sinh lệnh
    oct_traded = [r for r in res_oct_all if r["trades"] > 0]
    combo_traded = [r for r in res_combo_all if r["trades"] > 0]

    st_oct_all = analyze_basket(res_oct_all, "Toàn bộ rổ")
    st_oct_traded = analyze_basket(oct_traded, "Rổ sinh lệnh")

    st_combo_all = analyze_basket(res_combo_all, "Toàn bộ rổ")
    st_combo_traded = analyze_basket(combo_traded, "Rổ sinh lệnh")

    print("\n" + "=" * 125, flush=True)
    print("BÁO CÁO ĐO LƯỜNG ĐỐI CHIẾU TRUNG THỰC QUA ĐƯỜNG ỐNG run_backtest (BRIEF ĐỢT 8)", flush=True)
    print("=" * 125, flush=True)

    header = f"{'Tiêu chí':<35} | {'Octopus Baseline (Toàn bộ)':<26} | {'Octopus Baseline (Sinh lệnh)':<28} | {'Octopus Combo (Toàn bộ)':<24} | {'Octopus Combo (Sinh lệnh)'}"
    print(header, flush=True)
    print("-" * 145, flush=True)

    print(f"{'Số lượng mã trong rổ':<35} | {st_oct_all['n_symbols']:>26,d} | {st_oct_traded['n_symbols']:>28,d} | {st_combo_all['n_symbols']:>24,d} | {st_combo_traded['n_symbols']:>26,d}", flush=True)
    print(f"{'Tổng số lệnh (SELL fills)':<35} | {st_oct_all['total_trades']:>26,d} | {st_oct_traded['total_trades']:>28,d} | {st_combo_all['total_trades']:>24,d} | {st_combo_traded['total_trades']:>26,d}", flush=True)
    print(f"{'PnL Chiến lược (VND)':<35} | {st_oct_all['strat_pnl']:>26,.0f} | {st_oct_traded['strat_pnl']:>28,.0f} | {st_combo_all['strat_pnl']:>24,.0f} | {st_combo_traded['strat_pnl']:>26,.0f}", flush=True)
    print(f"{'PnL Mua-và-Giữ (VND)':<35} | {st_oct_all['bh_pnl']:>26,.0f} | {st_oct_traded['bh_pnl']:>28,.0f} | {st_combo_all['bh_pnl']:>24,.0f} | {st_combo_traded['bh_pnl']:>26,.0f}", flush=True)
    print(f"{'Chênh lệch (Strat − BH) (VND)':<35} | {st_oct_all['diff']:>26,.0f} | {st_oct_traded['diff']:>28,.0f} | {st_combo_all['diff']:>24,.0f} | {st_combo_traded['diff']:>26,.0f}", flush=True)
    print(f"{'Số mã thắng Mua-và-Giữ':<35} | {st_oct_all['win_bh_count']:>18}/{st_oct_all['n_symbols']} ({st_oct_all['win_bh_pct']:.1f}%) | {st_oct_traded['win_bh_count']:>20}/{st_oct_traded['n_symbols']} ({st_oct_traded['win_bh_pct']:.1f}%) | {st_combo_all['win_bh_count']:>16}/{st_combo_all['n_symbols']} ({st_combo_all['win_bh_pct']:.1f}%) | {st_combo_traded['win_bh_count']:>18}/{st_combo_traded['n_symbols']} ({st_combo_traded['win_bh_pct']:.1f}%)", flush=True)
    print(f"{'Trung vị PnL Chiến lược/mã':<35} | {st_oct_all['median_strat']:>26,.0f} | {st_oct_traded['median_strat']:>28,.0f} | {st_combo_all['median_strat']:>24,.0f} | {st_combo_traded['median_strat']:>26,.0f}", flush=True)
    print(f"{'Trung vị PnL Mua-và-Giữ/mã':<35} | {st_oct_all['median_bh']:>26,.0f} | {st_oct_traded['median_bh']:>28,.0f} | {st_combo_all['median_bh']:>24,.0f} | {st_combo_traded['median_bh']:>26,.0f}", flush=True)
    print(f"{'Trung vị chênh lệch/mã':<35} | {st_oct_all['median_diff']:>26,.0f} | {st_oct_traded['median_diff']:>28,.0f} | {st_combo_all['median_diff']:>24,.0f} | {st_combo_traded['median_diff']:>26,.0f}", flush=True)
    print("=" * 145, flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
