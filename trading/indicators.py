from collections import deque

from trading.models import Bar


class AtrCalculator:
    """Average True Range, per-symbol state (mirrors SmaCrossStrategy's own
    per-symbol MA state). Simple moving average of True Range, not Wilder's
    smoothing - consistent with SmaCrossStrategy's simple-average MAs."""

    def __init__(self, period: int = 14):
        self.period = period
        self._tr: dict[str, deque] = {}
        self._prev_close: dict[str, float | None] = {}

    def update(self, bar: Bar) -> float | None:
        prev_close = self._prev_close.get(bar.symbol)
        if prev_close is None:
            tr = bar.high - bar.low
        else:
            tr = max(
                bar.high - bar.low,
                abs(bar.high - prev_close),
                abs(bar.low - prev_close),
            )
        self._prev_close[bar.symbol] = bar.close

        window = self._tr.setdefault(bar.symbol, deque(maxlen=self.period))
        window.append(tr)
        if len(window) < self.period:
            return None
        return sum(window) / self.period

    def last(self, symbol: str) -> float | None:
        """ATR vừa tính ở lần update() gần nhất cho symbol này."""
        window = self._tr.get(symbol)
        if not window or len(window) < self.period:
            return None
        return sum(window) / self.period


class EmaCalculator:
    """Exponential Moving Average, per-symbol state (mirrors AtrCalculator).

    Seed: EMA được seed bằng SMA của `period` giá đóng cửa đầu tiên (bar thứ
    period-1 trả về SMA), từ bar thứ period trở đi dùng công thức chuẩn:
        alpha = 2 / (period + 1)
        EMA(t) = alpha * close(t) + (1 - alpha) * EMA(t-1)
    (cách seed phổ biến của ta-lib/TradingView — brief 2026-08-15 chốt.)
    """

    def __init__(self, period: int = 9):
        self.period = period
        self._closes: dict[str, deque] = {}
        self._n: dict[str, int] = {}  # số bar đã update (deque maxlen cố định không đủ)
        self._ema: dict[str, float | None] = {}

    def update(self, bar: Bar) -> float | None:
        closes = self._closes.setdefault(bar.symbol, deque(maxlen=self.period))
        closes.append(bar.close)
        n = self._n.get(bar.symbol, 0) + 1
        self._n[bar.symbol] = n
        if n < self.period:
            self._ema[bar.symbol] = None
            return None
        if n == self.period:
            ema = sum(closes) / self.period  # seed = SMA của period giá đầu
        else:
            alpha = 2 / (self.period + 1)
            prev = self._ema.get(bar.symbol)
            if prev is None:  # n > period nên seed đã chạy — chỉ phòng type-checker
                prev = sum(closes) / self.period
            ema = alpha * bar.close + (1 - alpha) * prev
        self._ema[bar.symbol] = ema
        return ema

    def last(self, symbol: str) -> float | None:
        """EMA vừa tính ở lần update() gần nhất cho symbol này."""
        return self._ema.get(symbol)


class MacdCalculator:
    """MACD (12/26/9) histogram = MACD − signal, per-symbol state.

    MACD line = EMA(fast) − EMA(slow); signal = EMA(signal_period) của MACD
    line; histogram = MACD − signal. Cả hai EMA seed bằng SMA như EmaCalculator.
    Trả None tới khi signal đủ warm-up (chưa có histogram hợp lệ).
    """

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self._fast = EmaCalculator(period=fast)
        self._slow = EmaCalculator(period=slow)
        self._signal = EmaCalculator(period=signal)
        self._macd_line: dict[str, float | None] = {}
        self._hist: dict[str, float | None] = {}

    def update(self, bar: Bar) -> float | None:
        fast = self._fast.update(bar)
        slow = self._slow.update(bar)
        if fast is None or slow is None:
            self._hist[bar.symbol] = None
            return None
        macd = fast - slow
        self._macd_line[bar.symbol] = macd
        hist = self._signal.update(_CloseOnlyBar(bar.symbol, bar.ts, macd))
        self._hist[bar.symbol] = hist
        return hist

    def last(self, symbol: str) -> float | None:
        """Histogram vừa tính ở lần update() gần nhất cho symbol này."""
        return self._hist.get(symbol)


class _CloseOnlyBar(Bar):
    """Bar giả chỉ mang close (cho EMA của MACD line) — open/high/low = close."""

    def __init__(self, symbol: str, ts, close: float):
        super().__init__(symbol, ts, close, close, close, close, 0)
