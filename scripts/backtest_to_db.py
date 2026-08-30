"""Chay mo phong chien luoc tung ma -> ghi vao DB -> Grafana doc.

Grafana chi doc SQL, khong chay duoc Python. Script nay la cau noi: chay
run_backtest (nguon su that duy nhat — khong tinh lai equity o day, commit
4ea4c8d) roi ghi 3 bang backtest_runs / backtest_equity / backtest_fills.

Ví dụ:
    PYTHONPATH=. uv run python scripts/backtest_to_db.py \
        --symbols VCB,HPG,FPT --strategy daily_breakout --timeframe 1d \
        --from 2020-01-01 --to 2025-12-31
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

from trading.backtest import _TF_SPEC, STRATEGIES, run_backtest
from trading.calendar_vn import TZ
from trading.config import load_config
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.trailing_stop import TrailingStopManager

sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", required=True, help="VD: VCB,HPG,FPT")
    ap.add_argument("--strategy", required=True, choices=list(STRATEGIES))
    ap.add_argument("--timeframe", default="1d", choices=list(_TF_SPEC), help="Khung thoi gian (5m..1M)")
    ap.add_argument("--from", dest="frm", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--capital", type=float, default=100_000_000.0)
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()

    dsn = os.environ.get("DB_DSN") or load_config(args.config).db_dsn
    storage = Storage(dsn)
    # Tao bang neu chua co (CREATE IF NOT EXISTS, idempotent) — script chay
    # tren DB that, khong qua migration rieng.
    storage.init_schema()

    frm = datetime.strptime(args.frm, "%Y-%m-%d").replace(tzinfo=TZ)
    to = datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=TZ) + timedelta(days=1)

    source, resample_fn = _TF_SPEC[args.timeframe]
    read = storage.read_bars if source == "bars" else storage.read_daily_bars

    for sym in args.symbols.split(","):
        sym = sym.strip()
        rows = read(sym, frm, to)
        bars = resample_fn(rows)
        if not bars:
            print(f"[SKIP] {sym}: khong co du lieu {args.timeframe} trong ky")
            continue

        strategy = STRATEGIES[args.strategy]()
        risk = RiskManager(capital=args.capital)
        trailing_stop = TrailingStopManager()
        report = run_backtest(bars, strategy, risk, trailing_stop, args.capital)

        run_id = storage.save_backtest_run(
            symbol=sym,
            strategy=args.strategy,
            timeframe=args.timeframe,
            frm=frm.date(),
            to_date=datetime.strptime(args.to, "%Y-%m-%d").date(),
            capital=args.capital,
            realized_pnl=report.realized_pnl,
            unrealized_pnl=report.unrealized_pnl,
            buy_and_hold_pnl=report.buy_and_hold_pnl,
            max_drawdown=report.max_drawdown,
            win_rate=report.win_rate,
            trades=report.trades,
            filtered_bars=report.filtered_bars,
        )
        storage.save_backtest_equity(
            run_id, report.equity_curve, report.buy_and_hold_curve
        )
        storage.save_backtest_fills(run_id, report.fills)

        strat_pnl = report.realized_pnl + report.unrealized_pnl
        print(
            f"[OK] {sym} run_id={run_id} trades={report.trades} "
            f"win_rate={report.win_rate:.1%} "
            f"strat_pnl={strat_pnl:,.0f} buy_and_hold={report.buy_and_hold_pnl:,.0f} "
            f"max_dd={report.max_drawdown:.1%} filtered={sum(report.filtered_bars.values())}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
