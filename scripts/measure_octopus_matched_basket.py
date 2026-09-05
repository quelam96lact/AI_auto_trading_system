"""Đo lường Octopus Pullback trên ĐÚNG RỔ MÃ SINH LỆNH (Brief đợt 4 / Gói Q).

Giải quyết câu hỏi §3.1:
Trên đúng những mã mà octopus thật sự vào lệnh (439 mã), nó thắng hay thua mua-và-giữ
của chính những mã đó?

Giao thức giữ nguyên của báo cáo 2026-09-01:
- bars_daily 2.982.903 dòng (kỳ 2016-01-04 -> 2026-08-13).
- Vốn 1.000.000.000 VND / mã, chạy độc lập từng mã rồi cộng dồn.
- Biểu phí VN, T+2,5, loại bỏ 246 mã trong exclusions.txt.
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


def measure_symbol(
    storage: Storage,
    symbol: str,
    frm: datetime,
    to: datetime,
    capital: float,
    strategy_cls,
    liq_spec: tuple[float, int] | None,
) -> dict:
    """Đo 1 mã với chiến lược và trả về kết quả chi tiết."""
    bars = storage.read_daily_bars(symbol, frm, to)
    strat = strategy_cls()
    risk = RiskManager(capital=capital)
    ts_mgr = TrailingStopManager()

    rep = run_backtest(bars, strat, risk, ts_mgr, capital)
    strat_pnl = rep.realized_pnl + rep.unrealized_pnl

    return {
        "symbol": symbol,
        "n_bars": len(bars),
        "trades": rep.trades,
        "win_rate": rep.win_rate,
        "strat_pnl": strat_pnl,
        "bh_pnl": rep.buy_and_hold_pnl,
        "diff": strat_pnl - rep.buy_and_hold_pnl,
        "filtered": sum(rep.filtered_bars.values()),
        "liquid": ever_liquid(bars, *liq_spec) if liq_spec else False,
    }


def analyze_basket(results: list[dict], name: str) -> dict:
    """Tổng hợp thống kê cho một tập rổ mã."""
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


def run_matched_measurement(
    dsn: str | None = None,
    capital: float = DEFAULT_CAPITAL,
    frm_str: str = DEFAULT_FROM,
    to_str: str = DEFAULT_TO,
    exclude_file: str = "exclusions.txt",
    limit: int = 0,
) -> tuple[dict, dict, dict, list[dict]]:
    """Chạy đo lường toàn diện và phân rổ cho Octopus Pullback."""
    frm = datetime.strptime(frm_str, "%Y-%m-%d").replace(tzinfo=TZ)
    to = datetime.strptime(to_str, "%Y-%m-%d").replace(tzinfo=TZ) + timedelta(days=1)

    storage = Storage(resolve_dsn(dsn))
    with storage.conn() as c:
        symbols = [
            r[0]
            for r in c.execute("SELECT DISTINCT symbol FROM bars_daily ORDER BY symbol")
        ]

    excluded: set[str] = set()
    if exclude_file and Path(exclude_file).exists():
        excluded = {
            s.strip().upper()
            for s in Path(exclude_file).read_text(encoding="utf-8").splitlines()
            if s.strip()
        }
        symbols = [s for s in symbols if s.upper() not in excluded]

    if limit > 0:
        symbols = symbols[:limit]

    strategy_cls = STRATEGIES["octopus_pullback"]
    # Dùng lại liquidity_spec của measure_strategy.py — cùng một công thức một
    # nơi (bài học 4ea4c8d). Rổ 2 của bảng này phải trùng khít rổ "đủ thanh
    # khoản" mà báo cáo 01/09 đếm, nên hai bên không được phép lệch định nghĩa.
    liq_spec = liquidity_spec(strategy_cls())

    all_results: list[dict] = []
    for i, sym in enumerate(symbols, 1):
        res = measure_symbol(storage, sym, frm, to, capital, strategy_cls, liq_spec)
        all_results.append(res)
        if i % 200 == 0 or i == len(symbols):
            print(f"  ...đã đo {i}/{len(symbols)} mã", file=sys.stderr)

    # Phân thành 3 rổ
    res_all = all_results
    res_liquid = [r for r in all_results if r["liquid"]]
    res_traded = [r for r in all_results if r["trades"] > 0]

    stats_all = analyze_basket(res_all, "Rổ 1: Toàn bộ rổ đã lọc")
    stats_liquid = analyze_basket(
        res_liquid, "Rổ 2: Các mã từng đủ thanh khoản (>= 2 tỷ)"
    )
    stats_traded = analyze_basket(res_traded, "Rổ 3: Các mã THỰC SỰ SINH LỆNH")

    return stats_all, stats_liquid, stats_traded, all_results


def print_comparison_report(
    stats_all: dict, stats_liquid: dict, stats_traded: dict
) -> None:
    """In bảng so sánh 3 rổ mã chi tiết."""
    print("\n" + "=" * 105)
    print("BÁO CÁO ĐO LƯỜNG ĐỐI CHIẾU ĐÚNG RỔ MÃ CHO OCTOPUS PULLBACK (GÓI Q)")
    print("=" * 105)

    print("\n" + "-" * 105)
    # Nhãn lấy từ chính số đo, không ghi cứng 1.308/748/439: chạy với --limit
    # thì ba con số đó sai, mà tiêu đề sai còn khó phát hiện hơn dữ liệu sai.
    h1 = f"Rổ 1: Toàn bộ ({stats_all['n_symbols']} mã)"
    h2 = f"Rổ 2: Đủ TK ({stats_liquid['n_symbols']} mã)"
    h3 = f"Rổ 3: Sinh lệnh ({stats_traded['n_symbols']} mã)"
    print(f"{'Tiêu chí':<32} | {h1:>20} | {h2:>21} | {h3:>22}")
    print("-" * 105)

    print(
        f"{'Số lượng mã trong rổ':<32} | {stats_all['n_symbols']:>20} | {stats_liquid['n_symbols']:>21} | {stats_traded['n_symbols']:>22}"
    )
    print(
        f"{'Tổng số lệnh (SELL fills)':<32} | {stats_all['total_trades']:>20,d} | {stats_liquid['total_trades']:>21,d} | {stats_traded['total_trades']:>22,d}"
    )
    print(
        f"{'PnL Chiến lược Octopus (VND)':<32} | {stats_all['strat_pnl']:>20,.0f} | {stats_liquid['strat_pnl']:>21,.0f} | {stats_traded['strat_pnl']:>22,.0f}"
    )
    print(
        f"{'PnL Mua-và-Giữ (VND)':<32} | {stats_all['bh_pnl']:>20,.0f} | {stats_liquid['bh_pnl']:>21,.0f} | {stats_traded['bh_pnl']:>22,.0f}"
    )
    print(
        f"{'Chênh lệch (Strat − BH) (VND)':<32} | {stats_all['diff']:>20,.0f} | {stats_liquid['diff']:>21,.0f} | {stats_traded['diff']:>22,.0f}"
    )
    print(
        f"{'Số mã thắng Mua-và-Giữ':<32} | {stats_all['win_bh_count']:>14}/{stats_all['n_symbols']} ({stats_all['win_bh_pct']:.1f}%) | {stats_liquid['win_bh_count']:>15}/{stats_liquid['n_symbols']} ({stats_liquid['win_bh_pct']:.1f}%) | {stats_traded['win_bh_count']:>16}/{stats_traded['n_symbols']} ({stats_traded['win_bh_pct']:.1f}%)"
    )
    print(
        f"{'Trung vị PnL Chiến lược/mã':<32} | {stats_all['median_strat']:>20,.0f} | {stats_liquid['median_strat']:>21,.0f} | {stats_traded['median_strat']:>22,.0f}"
    )
    print(
        f"{'Trung vị PnL Mua-và-Giữ/mã':<32} | {stats_all['median_bh']:>20,.0f} | {stats_liquid['median_bh']:>21,.0f} | {stats_traded['median_bh']:>22,.0f}"
    )
    print(
        f"{'Trung vị chênh lệch/mã':<32} | {stats_all['median_diff']:>20,.0f} | {stats_liquid['median_diff']:>21,.0f} | {stats_traded['median_diff']:>22,.0f}"
    )
    print("=" * 105)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Đo Octopus Pullback trên đúng rổ mã sinh lệnh"
    )
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--capital", type=float, default=DEFAULT_CAPITAL)
    ap.add_argument("--from", dest="frm", default=DEFAULT_FROM)
    ap.add_argument("--to", dest="to", default=DEFAULT_TO)
    ap.add_argument("--exclude-file", default="exclusions.txt")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    print("Bắt đầu đo lường phân rổ cho Octopus Pullback...")
    stats_all, stats_liquid, stats_traded, _ = run_matched_measurement(
        dsn=args.dsn,
        capital=args.capital,
        frm_str=args.frm,
        to_str=args.to,
        exclude_file=args.exclude_file,
        limit=args.limit,
    )

    print_comparison_report(stats_all, stats_liquid, stats_traded)


if __name__ == "__main__":
    main()
