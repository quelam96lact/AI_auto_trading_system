"""Chiến lược lai Octopus + Combo (OctopusComboStrategy) cho sổ đăng ký chiến lược.

BẢN CHẤT & RÀNG BUỘC PHẠM VI (Brief đợt 8):
1. Chiến lược này là PHẦN TÍN HIỆU của mô hình hybrid chạy trên mô hình khớp lệnh của
   repo (Market order tại open của bar sau tín hiệu, quản lý thoát bằng TP động trong
   on_bar + TrailingStopManager trong run_backtest). Cơ chế lệnh chờ BUY STOP tại
   High + 0.1*ATR cùng Stop Loss / Take Profit cố định từ trading/pattern_backtest.py
   KHÔNG TỒN TẠI trong class này và đường ống run_backtest.
2. Vì vậy, MỌI CON SỐ QUẢNG CÁO TRONG CÁC BÁO CÁO HYBRID (như +2.13 tỷ VND hay +1.48M USDT)
   KHÔNG ÁP DỤNG CHO CLASS NÀY. Con số thực của class này được đo lường trung thực
   qua đường ống run_backtest.
3. Nền bằng chứng thực nghiệm của mô hình hybrid trước đó có 3 lỗ hổng đã xác minh:
   - Số Crypto tính với phí = 0 và trượt giá = 0 (phí thật có thể làm đảo dấu kết quả).
   - Tham số k_tp = 4.0 là sản phẩm quét lưới trong mẫu (in-sample overfitting).
   - Trên cổ phiếu VN, 54.5% - 88.3% số lệnh chạm SL/TP trước ngày thanh toán T+2.5.

BA KHÁC BIỆT KỸ THUẬT SO VỚI OctopusPullbackStrategy:
1. Thêm điều kiện: close > MA(20).
2. Thêm điều kiện nến xanh: close > open.
3. EMA9 > EMA21 là SO SÁNH MỨC (LEVEL), KHÔNG phải cắt lên (crossover).
   Octopus gốc yêu cầu prev_fast <= prev_slow and ema_fast > ema_slow.
   Điều kiện mức lỏng hơn nhiều và sinh nhiều tín hiệu hơn.
4. ATR period mặc định là 14 (thay vì ATR(5) trong pattern_backtest.py) để đồng bộ
   với quy ước chung của engine/backtest repo.
"""

from collections import deque
from typing import Literal

from trading.indicators import (
    AtrCalculator,
    EmaCalculator,
    MacdCalculator,
)
from trading.models import Bar
from trading.strategies.octopus_pullback import DailyLiquidityTracker
from trading.strategy import Context, Signal

Crossover = Literal["bull", "bear"]


class OctopusComboStrategy:
    def __init__(
        self,
        qty: int = 100,
        ema_fast: int = 9,
        ema_slow: int = 21,
        ema_trend: int = 200,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        pullback_red: int = 2,
        pullback_window: int = 5,
        ma_period: int = 20,
        atr_period: int = 14,
        tp_atr_mult: float = 2.0,
        min_avg_value_20: float = 2_000_000_000.0,
        liquidity_window: int = 20,
    ):
        self.qty = qty
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.ema_trend = ema_trend
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.pullback_red = pullback_red
        self.pullback_window = pullback_window
        self.ma_period = ma_period
        self.atr_period = atr_period
        self.tp_atr_mult = tp_atr_mult
        self.min_avg_value_20 = min_avg_value_20
        self.liquidity_window = liquidity_window

        self._ema_fast = EmaCalculator(period=ema_fast)
        self._ema_slow = EmaCalculator(period=ema_slow)
        self._ema_trend = EmaCalculator(period=ema_trend)
        self._macd = MacdCalculator(fast=macd_fast, slow=macd_slow, signal=macd_signal)
        self._atr = AtrCalculator(period=atr_period)

        # Cửa sổ nến đỏ (theo bar), giá đóng cửa MA20 và bộ theo dõi thanh khoản (theo NGÀY)
        self._reds: dict[str, deque] = {}
        self._ma_closes: dict[str, deque] = {}
        self._liquidity_trackers: dict[str, DailyLiquidityTracker] = {}
        self._tp: dict[str, float] = {}
        self._last_crossover: dict[str, Crossover | None] = {}

    def _track_windows(self, bar: Bar) -> None:
        """Cập nhật cửa sổ nến đỏ, MA closes và bộ theo dõi thanh khoản theo ngày."""
        self._reds.setdefault(
            bar.symbol, deque(maxlen=self.pullback_window + 1)
        ).append(1 if bar.close < bar.open else 0)

        self._ma_closes.setdefault(
            bar.symbol, deque(maxlen=self.ma_period)
        ).append(bar.close)

        tracker = self._liquidity_trackers.setdefault(
            bar.symbol, DailyLiquidityTracker(window=self.liquidity_window)
        )
        tracker.update(bar)

    def _reds_before(self, symbol: str) -> int | None:
        """Số nến đỏ trong `pullback_window` phiên TRƯỚC bar hiện tại
        (phần tử cuối deque là bar hiện tại vừa append — bị loại).
        None nếu chưa đủ window phiên lịch sử (không đoán)."""
        reds = self._reds.get(symbol)
        if not reds or len(reds) < self.pullback_window + 1:
            return None
        return sum(list(reds)[: self.pullback_window])

    def _liquidity_ok(self, symbol: str) -> bool:
        """Bình quân giá trị giao dịch `liquidity_window` NGÀY ĐÃ ĐÓNG trước ngày hiện tại >= min_avg_value_20."""
        tracker = self._liquidity_trackers.get(symbol)
        if not tracker:
            return False
        avg = tracker.current_avg()
        return avg is not None and avg >= self.min_avg_value_20

    def compute_crossover(self, bar: Bar) -> Crossover | None:
        """Cập nhật state (CHỈ gọi đúng 1 lần/bar/symbol), trả về "bull" khi
        Strong Long, None nếu không đủ điều kiện (kể cả thiếu warmup)."""
        ema_fast = self._ema_fast.update(bar)
        ema_slow = self._ema_slow.update(bar)
        ema_trend = self._ema_trend.update(bar)
        hist = self._macd.update(bar)
        self._atr.update(bar)
        self._track_windows(bar)

        # Mặc định: không có crossover mới ở bar này.
        self._last_crossover[bar.symbol] = None

        if ema_fast is None or ema_slow is None or ema_trend is None or hist is None:
            return None  # chưa đủ warmup — không đoán

        # 1. Thanh khoản: bình quân 20 ngày đã đóng >= 2 tỷ
        if not self._liquidity_ok(bar.symbol):
            return None

        # 2. Xu hướng tăng: Close > EMA200 và Close > MA20
        ma_deque = self._ma_closes.get(bar.symbol)
        ma20 = (sum(ma_deque) / self.ma_period) if ma_deque and len(ma_deque) == self.ma_period else None
        if bar.close <= ema_trend or (ma20 is not None and bar.close <= ma20):
            return None

        # 3. Nến xanh đảo chiều: Close > Open và EMA9 > EMA21 và MACD hist > 0
        if not (bar.close > bar.open and ema_fast > ema_slow and hist > 0):
            return None

        # 4. Pullback: >= pullback_red nến đỏ trong window phiên TRƯỚC bar hiện tại
        reds_before = self._reds_before(bar.symbol)
        if reds_before is None or reds_before < self.pullback_red:
            return None

        self._last_crossover[bar.symbol] = "bull"
        return "bull"

    def last_crossover(self, symbol: str) -> Crossover | None:
        """Crossover vừa tính ở lần compute_crossover() gần nhất cho symbol này."""
        return self._last_crossover.get(symbol)

    def last_atr(self, symbol: str) -> float | None:
        """ATR vừa tính ở lần compute_crossover() gần nhất cho symbol này."""
        return self._atr.last(symbol)

    def on_bar(self, bar: Bar, context: Context) -> Signal | None:
        crossover = self.compute_crossover(bar)
        held = context.position_qty(bar.symbol)
        if crossover == "bull" and held == 0:
            return Signal(bar.symbol, "BUY", self.qty)
        if held > 0:
            tp = self._tp.get(bar.symbol)
            if tp is None:
                atr = self._atr.last(bar.symbol) or 0.0
                # Giá vào ~ bar.open của bar đầu tiên thấy vị thế (bar fill)
                tp = bar.open + self.tp_atr_mult * atr
                self._tp[bar.symbol] = tp
            if bar.close >= tp:
                return Signal(bar.symbol, "SELL", held)
        else:
            self._tp.pop(bar.symbol, None)
        return None

    @property
    def warmup_bars(self) -> int:
        """Số bar tối thiểu để sẵn sàng: max(EMA trend 200, MACD slow 26 + signal 9) + 1 = 201."""
        return max(self.ema_trend, self.macd_slow + self.macd_signal) + 1


__all__ = ["Crossover", "OctopusComboStrategy"]
