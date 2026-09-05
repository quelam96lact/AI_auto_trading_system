"""Kiểm định độ nhạy tham số (Sensitivity Analysis) cho Octopus Pullback (Brief đợt 9).

Quy tắc đánh giá:
- PnL đổi dấu trong vùng ±20% -> MONG MANH
- PnL thay đổi > 50% so với gốc -> MONG MANH
- Ngược lại -> ỔN ĐỊNH

CLI:
    uv run python scripts/param_sensitivity.py [--dsn ...] [--limit ...] [--capital ...]
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Thêm scripts/ vào sys.path
sys.path.insert(0, str(Path(__file__).parent))
try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

from trading.backtest import run_backtest
from trading.calendar_vn import TZ
from trading.metrics import expectancy, profit_factor
from trading.paper_broker import FEE_RATE, SELL_TAX_RATE, SLIPPAGE_BPS
from trading.risk import RiskManager
from trading.sampling import filter_bars_by_split
from trading.storage.db import Storage
from trading.strategies.octopus_pullback import OctopusPullbackStrategy
from trading.trailing_stop import TrailingStopManager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_CAPITAL = 1_000_000_000.0
DEFAULT_FROM = "2016-01-04"
DEFAULT_TO = "2026-08-13"


def run_eval_for_params(
    bars_dict: dict[str, list],
    capital: float,
    strat_kwargs: dict,
) -> dict:
    """Chạy đánh giá toàn bộ rổ mã với cấu hình tham số cụ thể."""
    total_strat_pnl = 0.0
    all_trade_pnls: list[float] = []
    total_trades = 0
    winning_trades = 0
    traded_symbols = 0

    for bars in bars_dict.values():
        strat = OctopusPullbackStrategy(**strat_kwargs)
        risk = RiskManager(capital=capital)
        ts_mgr = TrailingStopManager()

        rep = run_backtest(
            bars,
            strat,
            risk,
            ts_mgr,
            capital,
            fee_rate=FEE_RATE,
            sell_tax_rate=SELL_TAX_RATE,
            slippage_bps=SLIPPAGE_BPS,
        )
        strat_pnl = rep.realized_pnl + rep.unrealized_pnl
        total_strat_pnl += strat_pnl

        if rep.trades > 0:
            traded_symbols += 1
            total_trades += rep.trades
            for f in rep.fills:
                if f.side == "SELL" and f.pnl is not None:
                    all_trade_pnls.append(f.pnl)
                    if f.pnl > 0:
                        winning_trades += 1

    pf = profit_factor(all_trade_pnls)
    exp = expectancy(all_trade_pnls)
    win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0

    return {
        "pnl": total_strat_pnl,
        "trades": total_trades,
        "traded_symbols": traded_symbols,
        "win_rate": win_rate,
        "pf": pf,
        "exp": exp,
    }


def classify_robustness(base_pnl: float, variant_pnl: float) -> tuple[str, float]:
    """Phân loại độ nhạy (MONG MANH vs ỔN ĐỊNH) và phần trăm biến động."""
    if base_pnl == 0:
        return ("MONG MANH" if variant_pnl != 0 else "ỔN ĐỊNH", 0.0)

    # Đổi dấu -> MONG MANH
    if (base_pnl > 0 and variant_pnl < 0) or (base_pnl < 0 and variant_pnl > 0):
        pct_change = abs(variant_pnl - base_pnl) / abs(base_pnl) * 100.0
        return ("MONG MANH (Đổi dấu)", pct_change)

    pct_change = abs(variant_pnl - base_pnl) / abs(base_pnl) * 100.0
    if pct_change > 50.0:
        return ("MONG MANH (>50%)", pct_change)
    else:
        return ("ỔN ĐỊNH", pct_change)


def main() -> int:
    parser = argparse.ArgumentParser(description="Khảo sát độ nhạy tham số Octopus Pullback")
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--capital", type=float, default=DEFAULT_CAPITAL)
    parser.add_argument("--from", dest="frm", default=DEFAULT_FROM)
    parser.add_argument("--to", dest="to", default=DEFAULT_TO)
    parser.add_argument("--exclude-file", default="exclusions.txt")
    parser.add_argument("--limit", type=int, default=0)
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

    print(f"Đang nạp dữ liệu cho {len(symbols)} mã cổ phiếu VN...", flush=True)
    bars_dict: dict[str, list] = {}
    for sym in symbols:
        bars = storage.read_daily_bars(sym, frm, to)
        if bars:
            bars_dict[sym] = bars

    print(f"Đã nạp {len(bars_dict)} mã. Áp dụng phân chia tập mẫu '{args.split}'...", flush=True)
    filtered_dict: dict[str, list] = {}
    for i, (sym, bars) in enumerate(bars_dict.items()):
        # Ghi log mở khóa đúng 1 lần trên symbol đầu tiên nếu truy cập holdout
        target_log = "docs/holdout-unlock-log.md" if i == 0 else os.devnull
        fb = filter_bars_by_split(
            bars,
            split=args.split,
            unlock_holdout=args.unlock_holdout,
            strategy_name="OctopusPullback",
            config_info=f"Sensitivity Analysis ({args.split})",
            unlock_reason=args.unlock_reason,
            log_file=target_log,
        )
        if fb:
            filtered_dict[sym] = fb
    bars_dict = filtered_dict

    print(f"Tổng số mã có dữ liệu sau khi lọc tập '{args.split}': {len(bars_dict)} mã. Bắt đầu đo cấu hình gốc (Baseline)...", flush=True)

    base_params = {
        "tp_atr_mult": 2.0,
        "pullback_red": 2,
        "pullback_window": 5,
        "ema_fast": 9,
        "ema_slow": 21,
        "ema_trend": 200,
        "min_avg_value_20": 2_000_000_000.0,
    }

    base_res = run_eval_for_params(bars_dict, args.capital, base_params)
    base_pnl = base_res["pnl"]

    print(
        f"Baseline PnL: {base_pnl:+,.0f} VND | Số lệnh: {base_res['trades']:,d} | "
        f"Win Rate: {base_res['win_rate']:.1f}% | PF: {base_res['pf'] or 0:.2f} | Exp: {base_res['exp']:+,.0f} VND\n",
        flush=True,
    )

    # Danh sách tham số cần khảo sát ±20%
    param_variations = [
        ("tp_atr_mult", 1.6, 2.4, "float"),
        ("pullback_red", 1, 3, "int"),
        ("pullback_window", 4, 6, "int"),
        ("ema_fast", 7, 11, "int"),
        ("ema_slow", 17, 25, "int"),
        ("ema_trend", 160, 240, "int"),
        ("min_avg_value_20", 1_600_000_000.0, 2_400_000_000.0, "float"),
    ]

    results_table = []

    for param_name, v_minus, v_plus, p_type in param_variations:
        base_val = base_params[param_name]
        print(f"-> Khảo sát tham số {param_name} (Gốc: {base_val}, -20%: {v_minus}, +20%: {v_plus})...", flush=True)

        # 1. Đo -20%
        kwargs_minus = dict(base_params)
        kwargs_minus[param_name] = v_minus
        res_minus = run_eval_for_params(bars_dict, args.capital, kwargs_minus)
        status_minus, change_minus = classify_robustness(base_pnl, res_minus["pnl"])

        # 2. Đo +20%
        kwargs_plus = dict(base_params)
        kwargs_plus[param_name] = v_plus
        res_plus = run_eval_for_params(bars_dict, args.capital, kwargs_plus)
        status_plus, change_plus = classify_robustness(base_pnl, res_plus["pnl"])

        overall_status = "ỔN ĐỊNH"
        if "MONG MANH" in status_minus or "MONG MANH" in status_plus:
            overall_status = "MONG MANH"

        results_table.append({
            "param": param_name,
            "base_val": base_val,
            "minus_val": v_minus,
            "plus_val": v_plus,
            "res_minus": res_minus,
            "res_plus": res_plus,
            "change_minus": change_minus,
            "change_plus": change_plus,
            "status_minus": status_minus,
            "status_plus": status_plus,
            "overall_status": overall_status,
        })

    # In bảng tổng hợp
    print("\n" + "=" * 135, flush=True)
    print("BÁO CÁO KIỂM ĐỊNH ĐỘ NHẠY THAM SỐ (SENSITIVITY ANALYSIS) ±20% CHO OCTOPUS PULLBACK", flush=True)
    print("=" * 135, flush=True)
    header = (
        f"{'Tham số':<18} | {'Gốc':<10} | {'Biến thể -20%':<28} | "
        f"{'Biến thể +20%':<28} | {'Đánh giá độ nhạy'}"
    )
    print(header, flush=True)
    print("-" * 135, flush=True)

    for r in results_table:
        p_name = r["param"]
        b_val_str = f"{r['base_val']:,.0f}" if isinstance(r['base_val'], (int, float)) and r['base_val'] > 100 else f"{r['base_val']}"
        m_val_str = f"{r['minus_val']:,.0f}" if isinstance(r['minus_val'], (int, float)) and r['minus_val'] > 100 else f"{r['minus_val']}"
        p_val_str = f"{r['plus_val']:,.0f}" if isinstance(r['plus_val'], (int, float)) and r['plus_val'] > 100 else f"{r['plus_val']}"

        minus_desc = f"{m_val_str}: {r['res_minus']['pnl']:+,.0f} ({r['change_minus']:.1f}%)"
        plus_desc = f"{p_val_str}: {r['res_plus']['pnl']:+,.0f} ({r['change_plus']:.1f}%)"

        print(
            f"{p_name:<18} | {b_val_str:<10} | {minus_desc:<28} | {plus_desc:<28} | {r['overall_status']}",
            flush=True,
        )

    print("=" * 135, flush=True)
    print(f"Tổng số tổ hợp đã đánh giá: {len(results_table) * 2 + 1} (1 baseline + {len(results_table)} tham số x 2 biến thể)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
