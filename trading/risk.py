import math
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
    # C-a (04/09): don vi lo — 100 = lo san HOSE (mac dinh bat bien), 1 = crypto
    # (khong co lo). Ca phep lam tron xuong lan nguong tu choi qty < lot_size
    # doc tu tham so nay — mot cong thuc mot noi.
    lot_size: int | float = 100
    # (Brief dot 23): Don bay cho ky quy co lap (isolated margin). Mac dinh 1.0 = khong don bay (bat bien VN).
    leverage: float = 1.0
    halted_date: date | None = field(default=None, init=False, repr=False)
    # SIZE-1 Viec 2: ly do tu choi gan nhat (None = lan duyet truoc thanh cong
    # hoac chua duyet) — caller (logic.py / real_orders.py) ghi log INFO. Giua
    # risk.py thuan logic, KHONG import alert vao day.
    last_reject_reason: str | None = field(default=None, init=False, repr=False)

    def _halt_check(self, daily_pnl: float, today: date) -> bool:
        """True nếu bị chặn hôm nay (đã halt trước đó, hoặc vừa halt do lỗ
        vượt max_daily_loss_pct) — dùng chung bởi approve() và
        approve_sized() để 2 luồng paper/thật đồng bộ trạng thái halt."""
        if self.halted_date == today:
            return True
        if self.capital <= 0:
            return False
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
            self.last_reject_reason = "halt lỗ ngày"
            return False
        if signal.side == "BUY":
            if self.capital <= 0:
                self.last_reject_reason = (
                    "vốn <= 0 (NAV không dùng được) — không định cỡ được lệnh"
                )
                return False
            order_value = ref_price * signal.qty
            if order_value > self.capital * self.max_order_value_pct * self.leverage:
                self.last_reject_reason = (
                    f"giá trị lệnh {order_value:,.0f} > trần "
                    f"{self.capital * self.max_order_value_pct * self.leverage:,.0f} (max_order_value_pct)"
                )
                return False
            held_symbols = {s for s, p in positions.items() if p.qty > 0}
            if (
                signal.symbol not in held_symbols
                and len(held_symbols) >= self.max_positions
            ):
                self.last_reject_reason = (
                    f"đã đủ max_positions ({len(held_symbols)})"
                )
                return False
        self.last_reject_reason = None  # duyet thanh cong — xoa ly do cu
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
        """Giống approve() nhưng BUY được resize qty theo ATR (risk_pct vốn /
        (atr * atr_multiplier), làm tròn xuống bội 100) thay vì dùng signal.qty
        gốc từ Strategy. SELL đi qua nguyên vẹn, không đổi qty — chỉ BUY được
        sizing theo ATR (quyết định phạm vi rõ ràng, xem spec).

        Plan 2026-09-01 T1: KHÔNG còn giới hạn cho riêng paper — real_orders.py
        (nhánh BUY thật) cũng gọi hàm này, sau đó kẹp trần max_buy_qty từ SSI.
        Phép toán ATR sizing + trần 20% CHỈ tồn tại ở đây, một nguồn duy nhất
        (bài học 4ea4c8d: một công thức hai bản = hai tập bar khác nhau).

        SIZE-1: qty = min(qty_atr, qty_cap) — cap cho vừa trần 20% thay vì từ
        chối thẳng (logic cũ triệt tiêu capital hai vế -> đòi ATR/giá >= 2,5%,
        không mã nào đạt -> paper KHÔNG THỂ mua về mặt số học, 0 giao dịch
        4 tháng). min() giữ hai bất biến: không vượt mức ATR sizing cho phép,
        không vượt trần giá trị lệnh. Đánh đổi (đã báo cáo): khi vướng trần,
        rủi ro mỗi lệnh < risk_pct (nhỏ hơn, không bao giờ lớn hơn)."""
        if self._halt_check(daily_pnl, today):
            self.last_reject_reason = "halt lỗ ngày"
            return None
        if signal.side == "SELL":
            self.last_reject_reason = None
            return signal

        if self.capital <= 0:
            self.last_reject_reason = (
                "vốn <= 0 (NAV không dùng được) — không định cỡ được lệnh"
            )
            return None

        if atr is None or atr <= 0:
            self.last_reject_reason = "ATR không hợp lệ (atr=None hoặc <=0)"
            return None
        raw_atr = self.capital * self.risk_pct / (atr * self.atr_multiplier)
        raw_cap = self.capital * self.max_order_value_pct * self.leverage / ref_price

        if isinstance(self.lot_size, int):
            qty_atr = int(raw_atr // self.lot_size) * self.lot_size
            qty_cap = int(raw_cap // self.lot_size) * self.lot_size
            qty = min(qty_atr, qty_cap)
        else:
            steps_atr = math.floor(raw_atr / self.lot_size + 1e-9)
            steps_cap = math.floor(raw_cap / self.lot_size + 1e-9)
            steps = min(steps_atr, steps_cap)
            qty = round(steps * self.lot_size, 8)
            qty_atr = round(steps_atr * self.lot_size, 8)
            qty_cap = round(steps_cap * self.lot_size, 8)

        if qty < self.lot_size:
            self.last_reject_reason = (
                f"qty sau cap < 1 lô (qty_atr={qty_atr}, qty_cap={qty_cap})"
            )
            return None

        # Khong can kiem order_value > capital * max_order_value_pct nua:
        # qty_cap (o tren) da bao dam qty <= capital * max_order_value_pct /
        # ref_price — kiem tra cu khong bao gio dung, de lai la code chet
        # (SIZE-1, da xoa).
        held_symbols = {s for s, p in positions.items() if p.qty > 0}
        if (
            signal.symbol not in held_symbols
            and len(held_symbols) >= self.max_positions
        ):
            self.last_reject_reason = (
                f"đã đủ max_positions ({len(held_symbols)})"
            )
            return None

        self.last_reject_reason = None  # duyet thanh cong — xoa ly do cu
        return Signal(signal.symbol, "BUY", qty)
