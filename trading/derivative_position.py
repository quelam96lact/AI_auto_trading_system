from dataclasses import dataclass
from datetime import datetime

from trading.broker import Fill

# VNĐ/hợp đồng — biểu phí phái sinh thật của SSI CHƯA được xác nhận (khác
# equity, phí % giá trị). Placeholder cho paper-trading — không tiền thật,
# xem docs/superpowers/specs/2026-08-08-derivative-paper-trading-phase1-design.md.
DERIVATIVE_FEE_PER_CONTRACT = 2_700.0


@dataclass
class DerivativePosition:
    symbol: str
    qty: int = 0  # CÓ THỂ ÂM (short), DƯƠNG (long), 0 (flat)
    avg_price: float = 0.0


class DerivativePaperBroker:
    """Paper broker cho hợp đồng phái sinh (long/short, T+0, không có khái
    niệm settlement kiểu cổ phiếu). KHÔNG mô phỏng ký quỹ (margin) — cash
    chỉ trừ phí + cộng/trừ PnL đã thực hiện, không khoá vốn theo margin thật
    (chưa có số margin thật/hợp đồng để mô phỏng — xem spec)."""

    def __init__(
        self,
        capital: float,
        fee_per_contract: float = DERIVATIVE_FEE_PER_CONTRACT,
    ):
        self.capital = capital
        self.cash = capital
        self.fee_per_contract = fee_per_contract
        self.positions: dict[str, DerivativePosition] = {}
        self.realized_pnl = 0.0

    def position_qty(self, symbol: str) -> int:
        pos = self.positions.get(symbol)
        return pos.qty if pos else 0

    def open_long(self, symbol: str, qty: int, price: float, ts: datetime) -> Fill:
        """Mở vị thế long (BUY-to-open). Giả định caller đã xác nhận đang
        flat (position_qty(symbol) == 0) trước khi gọi — không tự kiểm tra,
        giống cách PaperBroker.on_bar()'s SELL branch giả định vị thế hợp
        lệ."""
        fee = qty * self.fee_per_contract
        pos = self.positions.setdefault(symbol, DerivativePosition(symbol))
        pos.qty = qty
        pos.avg_price = price
        self.cash -= fee
        return Fill(symbol, "BUY", qty, price, fee, ts, None)

    def open_short(self, symbol: str, qty: int, price: float, ts: datetime) -> Fill:
        """Mở vị thế short (SELL-to-open). Giả định caller đã xác nhận đang
        flat trước khi gọi — không tự kiểm tra."""
        fee = qty * self.fee_per_contract
        pos = self.positions.setdefault(symbol, DerivativePosition(symbol))
        pos.qty = -qty
        pos.avg_price = price
        self.cash -= fee
        return Fill(symbol, "SELL", qty, price, fee, ts, None)

    def close(self, symbol: str, price: float, ts: datetime) -> Fill:
        """Đóng toàn bộ vị thế đang mở (long hoặc short). Giả định caller đã
        xác nhận đang có vị thế mở (position_qty(symbol) != 0) trước khi
        gọi. side trả về phản ánh hành động thật: đóng long = SELL, đóng
        short (cover) = BUY."""
        pos = self.positions[symbol]
        qty = pos.qty
        filled_qty = abs(qty)
        fee = filled_qty * self.fee_per_contract
        if qty > 0:
            pnl = (price - pos.avg_price) * qty - fee
            side = "SELL"
        else:
            pnl = (pos.avg_price - price) * filled_qty - fee
            side = "BUY"
        self.realized_pnl += pnl
        self.cash += pnl
        pos.qty = 0
        pos.avg_price = 0.0
        return Fill(symbol, side, filled_qty, price, fee, ts, pnl)
