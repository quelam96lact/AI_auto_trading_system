import argparse
from datetime import datetime, timedelta

from trading.backtest import BacktestReport
from trading.broker import Fill
from trading.calendar_vn import TZ
from trading.config import load_config
from trading.derivative_position import DerivativePaperBroker
from trading.derivative_risk import DerivativeRiskManager
from trading.models import Bar
from trading.storage.db import Storage
from trading.strategies.sma_cross import SmaCrossStrategy

# VN30F1M front-month - xac nhan that 2026-07-26, dao han 2026-08-20.
# KHONG tu dong roll - xem spec.
DERIVATIVE_SYMBOL = "41I1G8000"


def _unrealized(broker: DerivativePaperBroker, marks: dict[str, float]) -> float:
    total = 0.0
    for symbol, pos in broker.positions.items():
        if pos.qty == 0 or symbol not in marks:
            continue
        mark = marks[symbol]
        if pos.qty > 0:
            total += (mark - pos.avg_price) * pos.qty * broker.contract_multiplier
        else:
            total += (pos.avg_price - mark) * abs(pos.qty) * broker.contract_multiplier
    return total


def run_derivative_backtest(
    bars: list[Bar],
    strategy: SmaCrossStrategy,
    risk: DerivativeRiskManager,
    capital: float,
    stop_loss_points: float = 0.0,
    take_profit_points: float = 0.0,
) -> BacktestReport:
    broker = DerivativePaperBroker(capital)
    marks: dict[str, float] = {}
    all_fills: list[Fill] = []
    equity_curve: list[float] = [capital]

    for bar in bars:
        crossover = strategy.compute_crossover(bar)
        marks[bar.symbol] = bar.close
        net = broker.position_qty(bar.symbol)
        daily_pnl = broker.realized_pnl + _unrealized(broker, marks)
        today = bar.ts.date()

        # Exit SL/TP (kiem tra TRUOC logic crossover; SL uu tien khi trung bar
        # - conservative; bar gap qua muc thi fill tai open - quy uoc gap cua
        # repo, giong TrailingStopManager). Sau exit khong mo lai cung bar.
        if net != 0 and (stop_loss_points > 0 or take_profit_points > 0):
            entry = broker.positions[bar.symbol].avg_price
            exit_price: float | None = None
            if net > 0:  # long
                if stop_loss_points > 0 and bar.low <= entry - stop_loss_points:
                    exit_price = min(bar.open, entry - stop_loss_points)
                elif take_profit_points > 0 and bar.high >= entry + take_profit_points:
                    exit_price = max(bar.open, entry + take_profit_points)
            else:  # short
                if stop_loss_points > 0 and bar.high >= entry + stop_loss_points:
                    exit_price = max(bar.open, entry + stop_loss_points)
                elif take_profit_points > 0 and bar.low <= entry - take_profit_points:
                    exit_price = min(bar.open, entry - take_profit_points)
            if exit_price is not None:
                all_fills.append(broker.close(bar.symbol, exit_price, bar.ts))
                equity = broker.cash + _unrealized(broker, marks)
                equity_curve.append(equity)
                continue

        if crossover == "bull" and net < 0:
            all_fills.append(broker.close(bar.symbol, bar.close, bar.ts))
        elif crossover == "bull" and net == 0:
            if risk.approve_open("long", net, daily_pnl, today):
                all_fills.append(
                    broker.open_long(bar.symbol, strategy.qty, bar.close, bar.ts)
                )
        elif crossover == "bear" and net > 0:
            all_fills.append(broker.close(bar.symbol, bar.close, bar.ts))
        elif (
            crossover == "bear"
            and net == 0
            and risk.approve_open("short", net, daily_pnl, today)
        ):
            all_fills.append(
                broker.open_short(bar.symbol, strategy.qty, bar.close, bar.ts)
            )

        equity = broker.cash + _unrealized(broker, marks)
        equity_curve.append(equity)

    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak)

    close_fills = [f for f in all_fills if f.pnl is not None]
    wins = sum(1 for f in close_fills if f.pnl is not None and f.pnl > 0)

    return BacktestReport(
        fills=all_fills,
        ending_cash=broker.cash,
        realized_pnl=broker.realized_pnl,
        unrealized_pnl=_unrealized(broker, marks),
        max_drawdown=max_dd,
        win_rate=(wins / len(close_fills)) if close_fills else 0.0,
        trades=len(close_fills),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--capital", type=float, default=100_000_000.0)
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()

    cfg = load_config(args.config)
    storage = Storage(cfg.db_dsn)
    frm = datetime.strptime(args.frm, "%Y-%m-%d").replace(tzinfo=TZ)
    to = datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=TZ) + timedelta(days=1)

    bars = storage.read_bars(DERIVATIVE_SYMBOL, frm, to)

    strategy = SmaCrossStrategy(qty=1)
    risk = DerivativeRiskManager(capital=args.capital)
    report = run_derivative_backtest(bars, strategy, risk, args.capital)

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
