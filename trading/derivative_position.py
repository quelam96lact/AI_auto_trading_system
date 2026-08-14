from dataclasses import dataclass
from datetime import datetime

from trading.broker import Fill

# VNĐ/hợp đồng/lượt (mở HOẶC đóng riêng) — biểu phí phái sinh SSI công khai
# (VN30/VN100 futures, Online = qua môi giới, cùng mức), gồm 3 phần cộng dồn:
# 3.000 (phí dịch vụ SSI, bậc dưới 100 HĐ/ngày) + 2.700 (phí trả HNX,
# "đồng/hợp đồng/giao dịch") + 2.550 (phí bù trừ VSD, "đồng/hợp đồng vị thế" —
# CHƯA xác nhận rõ tính theo lượt hay theo ngày giữ vị thế, tạm cộng dồn theo
# lượt cho khớp cơ chế per-transaction hiện có của DerivativePaperBroker).
# Nguồn: https://www.ssi.com.vn/khach-hang-ca-nhan/bieu-phi/bieu-gia-dich-vu-giao-dich-chung-khoan
# (hiệu lực 10/10/2025). Vẫn là ước tính bậc thấp nhất (dưới 100 HĐ/ngày) cho
# paper-trading — không tiền thật, xem
# docs/superpowers/specs/2026-08-08-derivative-paper-trading-phase1-design.md.
DERIVATIVE_FEE_PER_CONTRACT = 8_250.0

# VNĐ/điểm — hệ số nhân hợp đồng công khai của HNX cho VN30 Index Futures
# (VN30F1M): 100,000 VNĐ/điểm chỉ số. Đây là đặc tả hợp đồng do sở giao dịch
# công bố (khác biểu phí — biểu phí vẫn là placeholder CHƯA xác nhận, còn hệ
# số nhân điểm là số công khai của sở, dùng được ngay làm hằng số).
DERIVATIVE_CONTRACT_MULTIPLIER = 100_000.0


@dataclass
class DerivativePosition:
    symbol: str
    qty: int = 0  # CÓ THỂ ÂM (short), DƯƠNG (long), 0 (flat)
    avg_price: float = 0.0
    open_fee: float = 0.0  # DERIV-FEE-1: phí MỞ vị thế — trường RIÊNG, KHÔNG
    # gộp vào avg_price (avg_price là ĐIỂM chỉ số, phí là VNĐ — gộp sai đơn vị,
    # và derivative_backtest.py:72 dùng avg_price làm giá vào lệnh tính cắt
    # lỗ/chốt lãi theo điểm — gộp phí sẽ DỊCH ngưỡng, đổi hành vi giao dịch).


class DerivativePaperBroker:
    """Paper broker cho hợp đồng phái sinh (long/short, T+0, không có khái
    niệm settlement kiểu cổ phiếu). KHÔNG mô phỏng ký quỹ (margin) — cash
    chỉ trừ phí + cộng/trừ PnL đã thực hiện, không khoá vốn theo margin thật
    (chưa có số margin thật/hợp đồng để mô phỏng — xem spec)."""

    def __init__(
        self,
        capital: float,
        fee_per_contract: float = DERIVATIVE_FEE_PER_CONTRACT,
        contract_multiplier: float = DERIVATIVE_CONTRACT_MULTIPLIER,
    ):
        self.capital = capital
        self.cash = capital
        self.fee_per_contract = fee_per_contract
        self.contract_multiplier = contract_multiplier
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
        pos.open_fee = fee  # DERIV-FEE-1
        self.cash -= fee
        return Fill(symbol, "BUY", qty, price, fee, ts, None)

    def open_short(self, symbol: str, qty: int, price: float, ts: datetime) -> Fill:
        """Mở vị thế short (SELL-to-open). Giả định caller đã xác nhận đang
        flat trước khi gọi — không tự kiểm tra."""
        fee = qty * self.fee_per_contract
        pos = self.positions.setdefault(symbol, DerivativePosition(symbol))
        pos.qty = -qty
        pos.avg_price = price
        pos.open_fee = fee  # DERIV-FEE-1
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
            pnl = (price - pos.avg_price) * qty * self.contract_multiplier - fee
            side = "SELL"
        else:
            pnl = (pos.avg_price - price) * filled_qty * self.contract_multiplier - fee
            side = "BUY"
        # DERIV-FEE-1: realized trừ CẢ phí mở lẫn phí đóng — trước đây bỏ sót
        # phí mở (cùng hạng lỗi 6664cd9 bên cổ phiếu, sai một chiều). cash
        # KHÔNG trừ lại open_fee — nó đã trừ lúc mở (cash ròng giữ nguyên:
        # -phi_mo + gross - phi_dong). open_fee dọn cùng chỗ qty/avg_price.
        self.realized_pnl += pnl - pos.open_fee
        self.cash += pnl
        pos.qty = 0
        pos.avg_price = 0.0
        pos.open_fee = 0.0
        return Fill(symbol, side, filled_qty, price, fee, ts, pnl)
