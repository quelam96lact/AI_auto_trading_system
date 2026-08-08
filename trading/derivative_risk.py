from dataclasses import dataclass, field
from datetime import date
from typing import Literal


@dataclass
class DerivativeRiskManager:
    """Giới hạn risk đơn giản cho paper-trading phái sinh — KHÔNG phải
    margin-call model thật (account phái sinh chưa từng giao dịch, chưa có
    số ký quỹ/hợp đồng thật để đối chiếu). Xem spec
    docs/superpowers/specs/2026-08-08-derivative-paper-trading-phase1-design.md."""

    capital: float
    max_contracts: int = 1
    max_daily_loss_pct: float = 0.03
    halted_date: date | None = field(default=None, init=False, repr=False)

    def _halt_check(self, daily_pnl: float, today: date) -> bool:
        if self.halted_date == today:
            return True
        if daily_pnl <= -self.capital * self.max_daily_loss_pct:
            self.halted_date = today
            return True
        return False

    def approve_open(
        self,
        side: Literal["long", "short"],
        current_qty: int,
        daily_pnl: float,
        today: date,
    ) -> bool:
        """Chỉ gate lệnh MỞ vị thế mới (long hoặc short) — KHÔNG gate lệnh
        đóng (đóng vị thế đang giữ luôn được phép, không có
        approve_close())."""
        if self._halt_check(daily_pnl, today):
            return False
        if abs(current_qty) >= self.max_contracts:
            return False
        return True
