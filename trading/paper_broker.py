from datetime import datetime

from trading.broker import Fill, Position
from trading.models import Bar
from trading.strategy import Signal

# 0.25% - biểu phí SSI, đặt lệnh Online (không qua môi giới), giá trị GD
# dưới 100 triệu đồng/ngày/tài khoản. Nguồn: https://www.ssi.com.vn/khach-hang-ca-nhan/bieu-phi/bieu-gia-dich-vu-giao-dich-chung-khoan
# (hiệu lực 10/10/2025, đã bao gồm phí trả Sở). Các bậc giá trị GD cao hơn có
# mức phí khác (0.30% / 0.25%) - chưa hỗ trợ trong PaperBroker (dùng 1 rate cố định).
FEE_RATE = 0.0025
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

    def force_exit(self, symbol: str, price: float, ts: datetime) -> Fill:
        """Đóng TOÀN BỘ vị thế đang giữ ngay lập tức tại `price` — dùng bởi
        trailing stop. KHÔNG qua hàng đợi self._pending như submit()/on_bar()
        (không có độ trễ 1 bar). Giả định caller đã xác nhận vị thế đang mở
        (qty > 0) trước khi gọi, giống cách on_bar()'s SELL branch giả định."""
        pos = self.positions[symbol]
        qty = pos.qty
        gross = price * qty
        fee = gross * self.fee_rate + gross * self.sell_tax_rate
        pnl = (price - pos.avg_price) * qty - fee
        self.realized_pnl += pnl
        self.cash += gross - fee
        pos.qty = 0
        pos.avg_price = 0.0
        return Fill(symbol, "SELL", qty, price, fee, ts, pnl)

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
            # FEE-ALARM-1: gop phi MUA vao gia von — truoc day avg_price dung
            # gross (chua gom phi) trong khi cash ngay duoi tru phi do -> hai
            # so sach lech nhau, realized_pnl bo sot phi mua cua MOI vong giao
            # dich, luon sai mot chieu (bao lo nhe hon thuc te). Do that:
            # cash giam 328.798 nhung realized_pnl chi ghi -209.381 (chenh
            # 119.417 = tong phi 5 lenh mua). avg_price gio la "gia von gom
            # phi" — da kiem: khong ai doc avg_price voi nghia "gia khop"
            # (trailing stop dung tu lich su lenh, engine/main.py:108).
            pos.avg_price = (pos.avg_price * pos.qty + gross + fee) / new_qty
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

    @classmethod
    def restore(
        cls,
        capital: float,
        cash: float,
        realized_pnl: float,
        positions: dict[str, Position],
        **kwargs,
    ) -> "PaperBroker":
        broker = cls(capital, **kwargs)
        broker.cash = cash
        broker.realized_pnl = realized_pnl
        broker.positions = positions
        return broker
