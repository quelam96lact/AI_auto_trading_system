from trading.broker import Fill, Position
from trading.models import Bar
from trading.strategy import Signal

FEE_RATE = 0.0015
SELL_TAX_RATE = 0.001
SLIPPAGE_BPS = 5


class PaperBroker:
    def __init__(
        self,
        capital: float,
        fee_rate: float = FEE_RATE,
        sell_tax_rate: float = SELL_TAX_RATE,
        slippage_bps: float = SLIPPAGE_BPS,
    ):
        self.capital = capital
        self.cash = capital
        self.fee_rate = fee_rate
        self.sell_tax_rate = sell_tax_rate
        self.slippage_bps = slippage_bps
        self.positions: dict[str, Position] = {}
        self.realized_pnl = 0.0
        self._pending: dict[str, Signal] = {}

    def position_qty(self, symbol: str) -> int:
        pos = self.positions.get(symbol)
        return pos.qty if pos else 0

    def submit(self, signal: Signal) -> None:
        self._pending[signal.symbol] = signal

    def on_bar(self, bar: Bar) -> list[Fill]:
        signal = self._pending.pop(bar.symbol, None)
        if signal is None:
            return []
        qty = signal.qty
        if signal.side == "SELL":
            qty = min(qty, self.position_qty(bar.symbol))
            if qty <= 0:
                return []
        slip = bar.open * (self.slippage_bps / 10_000)
        price = bar.open + slip if signal.side == "BUY" else bar.open - slip
        gross = price * qty
        fee = gross * self.fee_rate + (
            gross * self.sell_tax_rate if signal.side == "SELL" else 0.0
        )

        pos = self.positions.setdefault(bar.symbol, Position(bar.symbol))
        pnl = None
        if signal.side == "BUY":
            new_qty = pos.qty + qty
            pos.avg_price = (pos.avg_price * pos.qty + gross) / new_qty
            pos.qty = new_qty
            self.cash -= gross + fee
        else:
            pnl = (price - pos.avg_price) * qty - fee
            self.realized_pnl += pnl
            self.cash += gross - fee
            pos.qty -= qty
            if pos.qty == 0:
                pos.avg_price = 0.0

        return [Fill(bar.symbol, signal.side, qty, price, fee, bar.ts, pnl)]

    def unrealized_pnl(self, marks: dict[str, float]) -> float:
        return sum(
            (marks[s] - p.avg_price) * p.qty
            for s, p in self.positions.items()
            if p.qty > 0 and s in marks
        )
