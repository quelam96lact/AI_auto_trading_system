"""Chiến lược "Octopus Pullback" (EMA + MACD) trên bar ngày (brief
2026-08-15-hermes-octopus-pullback.md). Nguồn là indicator trên TradingView
không công bố tham số — mọi con số là lựa chọn có chủ ý của người lập kế hoạch,
KHÔNG tinh chỉnh trong lần đo đầu.

Strong Long (chỉ triển khai mức này; Medium Long / Early Alert ngoài phạm vi):
1. Xu hướng tăng: close > EMA(200).
2. Pullback: >= 2 nến đỏ (close < open) trong cửa sổ 5 phiên gần nhất,
   tính TRƯỚC bar hiện tại.
3. Đảo chiều xác nhận: EMA(9) cắt LÊN EMA(21) (phiên trước EMA9 <= EMA21,
   phiên này EMA9 > EMA21) VÀ MACD histogram > 0 (MACD 12/26/9).

Luật ra lệnh (thay TP 0,2/0,5/1,0% bất khả thi của bản gốc — phí khứ hồi
~0,3-0,4% + T+2,5):
- Chốt lời: TP = giá vào + 2,0 x ATR(14) tại thời điểm vào lệnh. Giá vào ước
  lượng = bar.open của bar đầu tiên thấy vị thế (chính là giá mở bar fill —
  PaperBroker khớp BUY tại open bar sau signal, chênh đúng slippage ~5bps).
- Cắt lỗ: TrailingStopManager đã có sẵn trong run_backtest (sl_multiplier=2.0),
  strategy không tự làm.
- Cả hai tôn trọng T+2,5 qua PaperBroker (mua D bán từ D+3).

Bộ lọc thanh khoản point-in-time (KHÔNG dùng symbol_universe.avg_value_20d —
ảnh chụp 2026-08-13, dùng là look-ahead bias):
- gia_tri_gd(t) = close(t) * volume(t); binh_quan_20(t) = trung bình của 20
  phiên gần nhất KHÔNG tính bar t; đủ điều kiện <=> binh_quan_20(t) >= 2 tỷ.
- Kiểm tại bar sinh tín hiệu: không đủ thì bỏ qua tín hiệu, không mua.
- HẠN CHẾ ĐƠN VỊ: bars_daily là giá ĐÃ back-adjust nên close*volume không phải
  giá trị giao dịch danh nghĩa thật — con số tuyệt đối lệch, nhưng thứ tự
  tương đối giữa các mã/phiên vẫn dùng được cho việc sàng thanh khoản (đã báo
  cáo, không tự đổi định nghĩa giữa chừng).
- VWAP trong mô tả gốc KHÔNG áp dụng cho bar ngày (VWAP là khái niệm trong
  phiên) — bỏ, ghi rõ như yêu cầu.

Interface duck-typed giống DailyBreakoutStrategy: compute_crossover(bar) ->
"bull"|None (không có luật "bear" — ra lệnh bằng TP/trailing), .qty,
.warmup_bars, .last_atr(). State theo từng symbol.
"""

from collections import deque
from datetime import date
from typing import Literal

from trading.indicators import AtrCalculator, EmaCalculator, MacdCalculator
from trading.models import Bar
from trading.strategy import Context, Signal

Crossover = Literal["bull", "bear"]


class DailyLiquidityTracker:
    """Theo dõi và tính bình quân thanh khoản gộp theo NGÀY giao dịch (Gói K).

    Lưu tổng giá trị giao dịch (close * volume) của `window` ngày ĐÃ ĐÓNG
    trước ngày của bar hiện tại. Khi bar thuộc ngày mới đến (bar.ts.date() != _cur_day),
    ngày trước đó được coi là đã đóng và đẩy vào cửa sổ trượt `_closed_days` (maxlen=window).
    """

    def __init__(self, window: int = 20):
        self.window = window
        self._closed_days: deque[float] = deque(maxlen=window)
        self._cur_day: date | None = None
        self._cur_day_val: float = 0.0

    def update(self, bar: Bar) -> float | None:
        """Cập nhật bar. Trả về bình quân thanh khoản `window` ngày đã đóng
        TRƯỚC ngày của bar hiện tại, hoặc None nếu chưa đủ `window` ngày đã đóng."""
        d = bar.ts.date()
        if self._cur_day is None:
            self._cur_day = d
            self._cur_day_val = bar.close * bar.volume
        elif d != self._cur_day:
            self._closed_days.append(self._cur_day_val)
            self._cur_day = d
            self._cur_day_val = bar.close * bar.volume
        else:
            self._cur_day_val += bar.close * bar.volume

        if len(self._closed_days) < self.window:
            return None
        return sum(self._closed_days) / self.window

    def current_avg(self) -> float | None:
        """Bình quân của `window` ngày đã đóng gần nhất TRƯỚC ngày hiện tại."""
        if len(self._closed_days) < self.window:
            return None
        return sum(self._closed_days) / self.window


class OctopusPullbackStrategy:
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
        self.tp_atr_mult = tp_atr_mult
        self.min_avg_value_20 = min_avg_value_20
        self.liquidity_window = liquidity_window

        self._ema_fast = EmaCalculator(period=ema_fast)
        self._ema_slow = EmaCalculator(period=ema_slow)
        self._ema_trend = EmaCalculator(period=ema_trend)
        self._macd = MacdCalculator(fast=macd_fast, slow=macd_slow, signal=macd_signal)
        self._atr = AtrCalculator(period=atr_period)

        # Cửa sổ nến đỏ (theo bar) và bộ theo dõi thanh khoản (theo NGÀY)
        self._reds: dict[str, deque] = {}
        self._liquidity_trackers: dict[str, DailyLiquidityTracker] = {}
        self._tp: dict[str, float] = {}
        self._last_crossover: dict[str, Crossover | None] = {}

    def _track_windows(self, bar: Bar) -> None:
        """Cập nhật cửa sổ nến đỏ và bộ theo dõi thanh khoản theo ngày với bar hiện tại.
        Chạy cho MỌI bar (kể cả bar chưa đủ warmup / trả None) để cửa sổ không bị lệch.
        """
        self._reds.setdefault(
            bar.symbol, deque(maxlen=self.pullback_window + 1)
        ).append(1 if bar.close < bar.open else 0)
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
        prev_fast = self._ema_fast.last(bar.symbol)
        prev_slow = self._ema_slow.last(bar.symbol)
        ema_fast = self._ema_fast.update(bar)
        ema_slow = self._ema_slow.update(bar)
        ema_trend = self._ema_trend.update(bar)
        hist = self._macd.update(bar)
        self._atr.update(bar)
        self._track_windows(bar)
        # Mac dinh: khong co crossover moi o bar nay. Ghi state O MOI bar (ke ca
        # return None giua chung) de last_crossover khong tra ket qua cu cua bar
        # truoc — khuon giong sma_cross.compute_crossover (line 51, 61, 75).
        self._last_crossover[bar.symbol] = None

        if ema_fast is None or ema_slow is None or ema_trend is None or hist is None:
            return None  # chưa đủ warmup — không đoán
        if prev_fast is None or prev_slow is None:
            return None  # chưa có EMA của phiên trước

        # 3. Đảo chiều: EMA9 cắt LÊN EMA21 + MACD hist > 0
        cross_up = prev_fast <= prev_slow and ema_fast > ema_slow
        if not cross_up or hist <= 0:
            return None

        # 1. Xu hướng tăng
        if bar.close <= ema_trend:
            return None

        # 2. Pullback: >= pullback_red nến đỏ trong window TRƯỚC bar hiện tại
        reds_before = self._reds_before(bar.symbol)
        if reds_before is None or reds_before < self.pullback_red:
            return None

        # Bộ lọc thanh khoản point-in-time
        if not self._liquidity_ok(bar.symbol):
            return None

        self._last_crossover[bar.symbol] = "bull"
        return "bull"

    def last_crossover(self, symbol: str) -> Crossover | None:
        """Crossover vừa tính ở lần compute_crossover() gần nhất cho symbol này.
        logic.py:44 gọi KHÔNG điều kiện sau on_bar — thiếu method này là
        AttributeError ngay bar đầu (đã xảy ra ở octopus trước 04/09)."""
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
        """So bar toi thieu de san sang: max(EMA trend 200, MACD slow 26 + signal 9)
        + 1 bar hien tai (xem docstring lop)."""
        return max(self.ema_trend, self.macd_slow + self.macd_signal) + 1


# Re-export for type-safe callers.
__all__ = ["Crossover", "OctopusPullbackStrategy"]
