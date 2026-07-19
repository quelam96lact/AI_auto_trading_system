from dataclasses import dataclass, field

from trading.broker import Fill
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.strategy import Strategy


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
    strategy: Strategy,
    risk: RiskManager,
    capital: float,
) -> BacktestReport:
    broker = PaperBroker(capital)
    marks: dict[str, float] = {}
    all_fills: list[Fill] = []
    equity_curve: list[float] = [capital]

    for bar in bars:
        all_fills.extend(broker.on_bar(bar))
        marks[bar.symbol] = bar.close

        signal = strategy.on_bar(bar, broker)
        if signal is not None:
            daily_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)
            if risk.approve(signal, bar.close, broker.positions, daily_pnl, bar.ts.date()):
                broker.submit(signal)

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
