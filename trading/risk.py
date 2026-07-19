from dataclasses import dataclass, field
from datetime import date

from trading.broker import Position
from trading.strategy import Signal


@dataclass
class RiskManager:
    capital: float
    max_positions: int = 5
    max_order_value_pct: float = 0.20
    max_daily_loss_pct: float = 0.03
    _halted_date: date | None = field(default=None, init=False, repr=False)

    def approve(
        self,
        signal: Signal,
        ref_price: float,
        positions: dict[str, Position],
        daily_pnl: float,
        today: date,
    ) -> bool:
        if self._halted_date == today:
            return False
        if daily_pnl <= -self.capital * self.max_daily_loss_pct:
            self._halted_date = today
            return False
        if signal.side == "BUY":
            order_value = ref_price * signal.qty
            if order_value > self.capital * self.max_order_value_pct:
                return False
            held_symbols = {s for s, p in positions.items() if p.qty > 0}
            if signal.symbol not in held_symbols and len(held_symbols) >= self.max_positions:
                return False
        return True
