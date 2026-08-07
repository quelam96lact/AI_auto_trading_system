from dataclasses import dataclass, field

from trading.broker import Fill
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.strategies.sma_cross import SmaCrossStrategy
from trading.trailing_stop import TrailingStopManager


@dataclass
class BacktestReport:
    fills: list[Fill] = field(default_factory=list)
    ending_cash: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    trades: int = 0


def run_backtest(
    bars: list[Bar],
    strategy: SmaCrossStrategy,
    risk: RiskManager,
    trailing_stop: TrailingStopManager,
    capital: float,
) -> BacktestReport:
    broker = PaperBroker(capital)
    marks: dict[str, float] = {}
    all_fills: list[Fill] = []
    equity_curve: list[float] = [capital]

    for bar in bars:
        fills = broker.on_bar(bar)
        all_fills.extend(fills)
        marks[bar.symbol] = bar.close
        for f in fills:
            if f.side == "BUY":
                trailing_stop.on_position_opened(f.symbol, f.price)
            else:
                trailing_stop.on_position_closed(f.symbol)

        signal = strategy.on_bar(bar, broker)

        stop_price = None
        if broker.position_qty(bar.symbol) > 0:
            stop_price = trailing_stop.check(bar, strategy.last_atr(bar.symbol))

        if stop_price is not None:
            forced = broker.force_exit(bar.symbol, stop_price, bar.ts)
            trailing_stop.on_position_closed(bar.symbol)
            all_fills.append(forced)
        elif signal is not None:
            daily_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)
            sized = risk.approve_sized(
                signal,
                bar.close,
                strategy.last_atr(bar.symbol),
                broker.positions,
                daily_pnl,
                bar.ts.date(),
            )
            if sized is not None:
                broker.submit(sized)

        equity = broker.cash + sum(
            p.qty * marks.get(s, p.avg_price) for s, p in broker.positions.items()
        )
        equity_curve.append(equity)

    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak)

    sell_fills = [f for f in all_fills if f.side == "SELL"]
    wins = sum(1 for f in sell_fills if f.pnl is not None and f.pnl > 0)

    return BacktestReport(
        fills=all_fills,
        ending_cash=broker.cash,
        realized_pnl=broker.realized_pnl,
        unrealized_pnl=broker.unrealized_pnl(marks),
        max_drawdown=max_dd,
        win_rate=(wins / len(sell_fills)) if sell_fills else 0.0,
        trades=len(sell_fills),
    )


import argparse
from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.config import load_config
from trading.resample import resample_bars
from trading.storage.db import Storage

STRATEGIES = {"sma_cross": lambda: SmaCrossStrategy()}
_TF_MINUTES = {"15m": 15, "1h": 60}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True, choices=list(STRATEGIES))
    ap.add_argument("--symbols", required=True, help="VD: VCB,HPG")
    ap.add_argument("--from", dest="frm", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--tf", default="5m", choices=["5m", "15m", "1h"])
    ap.add_argument("--capital", type=float, default=100_000_000.0)
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()

    cfg = load_config(args.config)
    storage = Storage(cfg.db_dsn)
    frm = datetime.strptime(args.frm, "%Y-%m-%d").replace(tzinfo=TZ)
    to = datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=TZ) + timedelta(days=1)

    bars: list[Bar] = []
    for sym in args.symbols.split(","):
        rows = storage.read_bars(sym, frm, to)
        bars.extend(
            rows if args.tf == "5m" else resample_bars(rows, _TF_MINUTES[args.tf])
        )
    bars.sort(key=lambda b: (b.ts, b.symbol))

    strategy = STRATEGIES[args.strategy]()
    risk = RiskManager(capital=args.capital)
    trailing_stop = TrailingStopManager()
    report = run_backtest(bars, strategy, risk, trailing_stop, args.capital)

    print(f"Bars replayed: {len(bars)}")
    print(f"Trades: {report.trades}  Win rate: {report.win_rate:.1%}")
    print(
        f"Realized PnL: {report.realized_pnl:,.0f}  Unrealized PnL: {report.unrealized_pnl:,.0f}"
    )
    print(
        f"Ending cash: {report.ending_cash:,.0f}  Max drawdown: {report.max_drawdown:.1%}"
    )


if __name__ == "__main__":
    main()
