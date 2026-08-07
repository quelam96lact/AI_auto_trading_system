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
    risk_pct: float = 0.01
    atr_multiplier: float = 2.0
    halted_date: date | None = field(default=None, init=False, repr=False)

    def _halt_check(self, daily_pnl: float, today: date) -> bool:
        """True nếu bị chặn hôm nay (đã halt trước đó, hoặc vừa halt do lỗ
        vượt max_daily_loss_pct) — dùng chung bởi approve() và
        approve_sized() để 2 luồng paper/thật đồng bộ trạng thái halt."""
        if self.halted_date == today:
            return True
        if daily_pnl <= -self.capital * self.max_daily_loss_pct:
            self.halted_date = today
            return True
        return False

    def approve(
        self,
        signal: Signal,
        ref_price: float,
        positions: dict[str, Position],
        daily_pnl: float,
        today: date,
    ) -> bool:
        if self._halt_check(daily_pnl, today):
            return False
        if signal.side == "BUY":
            order_value = ref_price * signal.qty
            if order_value > self.capital * self.max_order_value_pct:
                return False
            held_symbols = {s for s, p in positions.items() if p.qty > 0}
            if (
                signal.symbol not in held_symbols
                and len(held_symbols) >= self.max_positions
            ):
                return False
        return True

    def approve_sized(
        self,
        signal: Signal,
        ref_price: float,
        atr: float | None,
        positions: dict[str, Position],
        daily_pnl: float,
        today: date,
    ) -> Signal | None:
        """Giống approve() nhưng cho luồng paper trading: BUY được resize qty
        theo ATR (risk_pct vốn / (atr * atr_multiplier), làm tròn xuống bội
        100) thay vì dùng signal.qty gốc từ Strategy. SELL đi qua nguyên vẹn,
        không đổi qty — chỉ BUY được sizing theo ATR (quyết định phạm vi rõ
        ràng, xem spec). KHÔNG dùng cho real_orders.py — đó vẫn gọi approve()."""
        if self._halt_check(daily_pnl, today):
            return None
        if signal.side == "SELL":
            return signal

        if atr is None or atr <= 0:
            return None
        qty_raw = (self.capital * self.risk_pct) / (atr * self.atr_multiplier)
        qty = int(qty_raw // 100) * 100
        if qty < 100:
            return None

        order_value = ref_price * qty
        if order_value > self.capital * self.max_order_value_pct:
            return None
        held_symbols = {s for s, p in positions.items() if p.qty > 0}
        if (
            signal.symbol not in held_symbols
            and len(held_symbols) >= self.max_positions
        ):
            return None

        return Signal(signal.symbol, "BUY", qty)
