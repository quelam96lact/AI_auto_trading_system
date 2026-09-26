from dataclasses import dataclass
from datetime import datetime

from trading.broker import Fill

# VNĐ/hợp đồng/lượt (mở HOẶC đóng riêng) — biểu phí giao dịch phái sinh SSI + HNX:
# 3.000 (phí dịch vụ SSI gói có chuyên viên TVCK, bậc < 100 HĐ/ngày) + 2.700 (phí trả HNX,
# "đồng/hợp đồng/giao dịch").
# Nguồn: Biểu giá SSI hiệu lực 10/10/2025 & Thông tư 83/2024/TT-BTC.
# Chi tiết xem: docs/superpowers/specs/2026-09-26-bieu-phi-phai-sinh-co-nguon.md.
# Lưu ý: Giữ nguyên tên DERIVATIVE_FEE_PER_CONTRACT vì scripts/.spike_improve_derivative_strategies.py
# đang import tên này.
DERIVATIVE_FEE_PER_CONTRACT = 5_700.0

# VNĐ/hợp đồng/lượt — phí bù trừ phái sinh trả VSDC:
# 2.550 đ/hợp đồng vị thế, thu trên mỗi giao dịch khớp lệnh mở hoặc đóng vị thế (5.100 đ/vòng).
# Nguồn: Thông tư 83/2024/TT-BTC (hiệu lực 10/01/2025), Quy chế VSDC & Biểu giá SSI 10/10/2025.
# Chi tiết xem: docs/superpowers/specs/2026-09-26-bieu-phi-phai-sinh-co-nguon.md (Mục 1b).
DERIVATIVE_VSD_CLEARING_FEE_PER_CONTRACT = 2_550.0

# VNĐ/điểm — hệ số nhân hợp đồng công khai của HNX cho VN30 Index Futures
# (VN30F1M): 100,000 VNĐ/điểm chỉ số. Đây là đặc tả hợp đồng do sở giao dịch
# công bố.
DERIVATIVE_CONTRACT_MULTIPLIER = 100_000.0

# Tỷ lệ ký quỹ ban đầu (Initial Margin - IM) đối với HĐTL chỉ số VN30:
# 17% (0,17). VSDC công bố tỷ lệ này THEO TỪNG MÃ HĐ, định kỳ; nguồn gốc đã kiểm:
# https://vsdc.vn/vi/ad/177750 (17% cho VN30F2501..2506, cập nhật 18/12/2024). CHƯA đọc
# được thông báo hiệu lực 19/12/2025 (file Excel). Thuế tỷ lệ thuận với số này.
# Dùng để tính giá chuyển nhượng làm căn cứ tính thuế TNCN.
# Chi tiết xem: docs/superpowers/specs/2026-09-26-bieu-phi-phai-sinh-co-nguon.md (Mục 1c).
DERIVATIVE_INITIAL_MARGIN_RATE = 0.17

# Thuế suất thuế thu nhập cá nhân (TNCN) đối với chuyển nhượng chứng khoán phái sinh:
# 0,1% (0.001) tính trên giá chuyển nhượng từng lần (cả mở lẫn đóng).
# Căn cứ: CV 11133/BTC-CST (21/08/2017), Luật Thuế TNCN sửa đổi 71/2014, TT 87/2026/TT-BTC.
# Chi tiết xem: docs/superpowers/specs/2026-09-26-bieu-phi-phai-sinh-co-nguon.md (Mục 1a).
DERIVATIVE_PIT_TAX_RATE = 0.001


def derivative_trade_tax(
    price: float,
    qty: int,
    contract_multiplier: float = DERIVATIVE_CONTRACT_MULTIPLIER,
    initial_margin_rate: float = DERIVATIVE_INITIAL_MARGIN_RATE,
    tax_rate: float = DERIVATIVE_PIT_TAX_RATE,
) -> float:
    """Thuế TNCN trên một lần chuyển nhượng HĐTL (mở hoặc đóng vị thế).

    Công thức theo Công văn 11133/BTC-CST và Thông tư 87/2026/TT-BTC:
    Giá chuyển nhượng từng lần = (Giá thanh toán x Hệ số nhân x Số lượng x Tỷ lệ ký quỹ ban đầu) / 2
    Thuế TNCN = Giá chuyển nhượng từng lần x Thuế suất (0,1%)

    Chi tiết: docs/superpowers/specs/2026-09-26-bieu-phi-phai-sinh-co-nguon.md (Mục 1a).
    """
    transfer_value = (price * contract_multiplier * qty * initial_margin_rate) / 2.0
    return transfer_value * tax_rate


def derivative_side_cost(
    price: float,
    qty: int,
    opening: bool = True,
    fee_per_contract: float = DERIVATIVE_FEE_PER_CONTRACT,
    vsd_fee_per_contract: float = DERIVATIVE_VSD_CLEARING_FEE_PER_CONTRACT,
    contract_multiplier: float = DERIVATIVE_CONTRACT_MULTIPLIER,
    initial_margin_rate: float = DERIVATIVE_INITIAL_MARGIN_RATE,
    tax_rate: float = DERIVATIVE_PIT_TAX_RATE,
) -> float:
    """Tổng chi phí VNĐ của MỘT lượt (mở hoặc đóng) theo biểu phí mặc định:
    1. Phí SSI + HNX: fee_per_contract x qty (mặc định 5.700 đ/HĐ)
    2. Phí bù trừ VSDC: vsd_fee_per_contract x qty (mặc định 2.550 đ/HĐ theo TT 83/2024/TT-BTC,
       thu cả lượt mở lẫn lượt đóng theo kết quả Task 1b)
    3. Thuế TNCN: derivative_trade_tax(price, qty) (mặc định 0,1% trên giá chuyển nhượng)

    `opening` HIỆN KHÔNG đổi kết quả: theo Mục 1b cả ba thành phần thu như nhau ở
    lượt mở và lượt đóng. Giữ tham số để nơi gọi ghi rõ lượt nào, và để một biểu phí
    bất đối xứng sau này chỉ sửa ở đây.

    Chi tiết: docs/superpowers/specs/2026-09-26-bieu-phi-phai-sinh-co-nguon.md.
    """
    base_fee = qty * fee_per_contract
    vsd_fee = qty * vsd_fee_per_contract
    tax = derivative_trade_tax(
        price,
        qty,
        contract_multiplier=contract_multiplier,
        initial_margin_rate=initial_margin_rate,
        tax_rate=tax_rate,
    )
    return base_fee + vsd_fee + tax


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
        vsd_fee_per_contract: float = DERIVATIVE_VSD_CLEARING_FEE_PER_CONTRACT,
        contract_multiplier: float = DERIVATIVE_CONTRACT_MULTIPLIER,
        initial_margin_rate: float = DERIVATIVE_INITIAL_MARGIN_RATE,
        tax_rate: float = DERIVATIVE_PIT_TAX_RATE,
    ):
        self.capital = capital
        self.cash = capital
        self.fee_per_contract = fee_per_contract
        self.vsd_fee_per_contract = vsd_fee_per_contract
        self.contract_multiplier = contract_multiplier
        self.initial_margin_rate = initial_margin_rate
        self.tax_rate = tax_rate
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
        fee = derivative_side_cost(
            price,
            qty,
            opening=True,
            fee_per_contract=self.fee_per_contract,
            vsd_fee_per_contract=self.vsd_fee_per_contract,
            contract_multiplier=self.contract_multiplier,
            initial_margin_rate=self.initial_margin_rate,
            tax_rate=self.tax_rate,
        )
        pos = self.positions.setdefault(symbol, DerivativePosition(symbol))
        pos.qty = qty
        pos.avg_price = price
        pos.open_fee = fee  # DERIV-FEE-1
        self.cash -= fee
        return Fill(symbol, "BUY", qty, price, fee, ts, None)

    def open_short(self, symbol: str, qty: int, price: float, ts: datetime) -> Fill:
        """Mở vị thế short (SELL-to-open). Giả định caller đã xác nhận đang
        flat trước khi gọi — không tự kiểm tra."""
        fee = derivative_side_cost(
            price,
            qty,
            opening=True,
            fee_per_contract=self.fee_per_contract,
            vsd_fee_per_contract=self.vsd_fee_per_contract,
            contract_multiplier=self.contract_multiplier,
            initial_margin_rate=self.initial_margin_rate,
            tax_rate=self.tax_rate,
        )
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
        fee = derivative_side_cost(
            price,
            filled_qty,
            opening=False,
            fee_per_contract=self.fee_per_contract,
            vsd_fee_per_contract=self.vsd_fee_per_contract,
            contract_multiplier=self.contract_multiplier,
            initial_margin_rate=self.initial_margin_rate,
            tax_rate=self.tax_rate,
        )
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
        open_fee = pos.open_fee
        self.realized_pnl += pnl - open_fee
        self.cash += pnl
        pos.qty = 0
        pos.avg_price = 0.0
        pos.open_fee = 0.0
        # LEDGER-1 Viec 2: Fill.pnl GỒM cả phí mở — cùng nghĩa với bên cổ phiếu
        # ("lãi/lỗ trọn vòng của lần đóng này"). DA KIEM: khong cho nao cong
        # don fill.pnl ra realized_pnl (realized tinh trong broker; fill.pnl chi
        # dung luu orders ben co phieu + thong ke spike win-rate tung lenh) —
        # doi nay khong dem phi mo hai lan.
        return Fill(symbol, side, filled_qty, price, fee, ts, pnl - open_fee)
