from dataclasses import dataclass, field
from datetime import date
from typing import Literal


@dataclass
class DerivativeRiskManager:
    """Giới hạn risk đơn giản cho paper-trading phái sinh — KHÔNG phải
    margin-call model thật (account phái sinh chưa từng giao dịch, chưa có
    số ký quỹ/hợp đồng thật để đối chiếu). Xem spec
    docs/superpowers/specs/2026-08-08-derivative-paper-trading-phase1-design.md.

    Theo file người dùng đề xuất (docs/superpowers/plans/2026-08-09-...):
    dừng giao dịch khi lỗ đạt 2% vốn HOẶC 2 lệnh thua liên tiếp (streak
    reset theo ngày và khi có lệnh thắng)."""

    capital: float
    max_contracts: int = 1
    max_daily_loss_pct: float = 0.02
    max_consecutive_losses: int = 2
    halted_date: date | None = field(default=None, init=False, repr=False)
    _consecutive_losses: int = field(default=0, init=False, repr=False)
    _streak_date: date | None = field(default=None, init=False, repr=False)

    def _halt_check(self, daily_pnl: float, today: date) -> bool:
        if self.halted_date == today:
            return True
        if daily_pnl <= -self.capital * self.max_daily_loss_pct:
            self.halted_date = today
            return True
        if (
            self._consecutive_losses >= self.max_consecutive_losses
            and self._streak_date == today
        ):
            self.halted_date = today
            return True
        return False

    def record_trade_result(self, pnl: float, today: date) -> None:
        """Ghi nhận kết quả 1 lệnh ĐÃ ĐÓNG (pnl thực hiện) để đếm chuỗi thua
        liên tiếp. Streak reset khi đổi ngày hoặc khi có lệnh thắng (pnl >= 0)."""
        if today != self._streak_date:
            self._consecutive_losses = 0
            self._streak_date = today
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

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
        return not abs(current_qty) >= self.max_contracts
