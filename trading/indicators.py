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


import statistics


class DonchianCalculator:
    """Donchian Channel, per-symbol state.

    Upper = max(high) của period bar trước; Lower = min(low) của period bar trước.
    Bảo đảm quy ước chống nhìn trước (§2.2 điều 2): tính biên TỪ CÁC BAR TRƯỚC
    bar hiện tại, sau khi tính xong mới đẩy high/low của bar hiện tại vào deque.
    Trả None khi chưa đủ `period` bar trước.
    """

    def __init__(self, period: int = 20):
        self.period = period
        self._highs: dict[str, deque[float]] = {}
        self._lows: dict[str, deque[float]] = {}
        self._last: dict[str, tuple[float, float] | None] = {}

    def update(self, bar: Bar) -> tuple[float, float] | None:
        highs = self._highs.setdefault(bar.symbol, deque(maxlen=self.period))
        lows = self._lows.setdefault(bar.symbol, deque(maxlen=self.period))

        if len(highs) < self.period:
            res = None
        else:
            res = (max(highs), min(lows))

        self._last[bar.symbol] = res

        # Thứ tự "tính trước, đẩy sau": bảo đảm luật §2.2 điều 2 (không gồm bar hiện tại t)
        highs.append(bar.high)
        lows.append(bar.low)

        return res

    def last(self, symbol: str) -> tuple[float, float] | None:
        """Kênh Donchian (upper, lower) vừa tính ở lần update() gần nhất cho symbol này."""
        return self._last.get(symbol)


class BollingerCalculator:
    """Bollinger Bands, per-symbol state.

    middle = SMA của `period` giá đóng gồm cả bar hiện tại.
    SD_t = độ lệch chuẩn mẫu (chia n-1, tức statistics.stdev) của `period` giá đóng đó (§5.1).
    upper = middle + num_std * SD_t
    lower = middle - num_std * SD_t
    Trả None khi chưa đủ `period` giá đóng.
    """

    def __init__(self, period: int = 20, num_std: float = 2.0):
        self.period = period
        self.num_std = num_std
        self._closes: dict[str, deque[float]] = {}
        self._last: dict[str, tuple[float, float, float] | None] = {}

    def update(self, bar: Bar) -> tuple[float, float, float] | None:
        closes = self._closes.setdefault(bar.symbol, deque(maxlen=self.period))
        closes.append(bar.close)

        if len(closes) < self.period:
            self._last[bar.symbol] = None
            return None

        middle = sum(closes) / self.period
        sd = statistics.stdev(closes)
        upper = middle + self.num_std * sd
        lower = middle - self.num_std * sd
        res = (middle, upper, lower)
        self._last[bar.symbol] = res
        return res

    def last(self, symbol: str) -> tuple[float, float, float] | None:
        """Bollinger Bands (middle, upper, lower) vừa tính ở lần update() gần nhất cho symbol này."""
        return self._last.get(symbol)


def percent_b(close: float, upper: float, lower: float) -> float | None:
    """Hàm module-level thuần tính vị trí %B: (close - lower) / (upper - lower).

    Trả None khi upper == lower.
    """
    if upper == lower:
        return None
    return (close - lower) / (upper - lower)


class AdxCalculator:
    """Average Directional Index (ADX), per-symbol state.

    Dùng làm trơn Wilder (định nghĩa chuẩn của ADX, khác với trung bình đơn giản
    mà AtrCalculator dùng).
    +DM, -DM và TR được làm trơn bằng Wilder smoothing:
        S_t = S_{t-1} - S_{t-1}/period + X_t, seed = tổng period giá trị đầu.
    DX = 100 * |(+DI) - (-DI)| / ((+DI) + (-DI)).
    ADX = làm trơn Wilder của DX, seed = trung bình period giá trị DX đầu tiên:
        ADX_t = (ADX_{t-1} * (period - 1) + DX_t) / period.
    Cần khoảng 2 * period bar mới có ADX đầu tiên. Trả None cho tới khi đó.
    Nếu S(TR) == 0 hoặc (+DI) + (-DI) == 0 -> trả None cho bar đó.
    """

    def __init__(self, period: int = 14):
        self.period = period
        self._prev_bar: dict[str, Bar] = {}
        self._tr_seed: dict[str, list[float]] = {}
        self._dm_plus_seed: dict[str, list[float]] = {}
        self._dm_minus_seed: dict[str, list[float]] = {}
        self._s_tr: dict[str, float] = {}
        self._s_dm_plus: dict[str, float] = {}
        self._s_dm_minus: dict[str, float] = {}
        self._dx_seed: dict[str, list[float]] = {}
        self._adx: dict[str, float] = {}
        self._last: dict[str, float | None] = {}

    def update(self, bar: Bar) -> float | None:
        prev = self._prev_bar.get(bar.symbol)
        self._prev_bar[bar.symbol] = bar
        if prev is None:
            self._last[bar.symbol] = None
            return None

        up_move = bar.high - prev.high
        down_move = prev.low - bar.low

        dm_plus = up_move if (up_move > 0 and up_move > down_move) else 0.0
        dm_minus = down_move if (down_move > 0 and down_move > up_move) else 0.0
        tr = max(
            bar.high - bar.low,
            abs(bar.high - prev.close),
            abs(bar.low - prev.close),
        )

        sym = bar.symbol
        if sym not in self._s_tr:
            tr_buf = self._tr_seed.setdefault(sym, [])
            dmp_buf = self._dm_plus_seed.setdefault(sym, [])
            dmm_buf = self._dm_minus_seed.setdefault(sym, [])

            tr_buf.append(tr)
            dmp_buf.append(dm_plus)
            dmm_buf.append(dm_minus)

            if len(tr_buf) < self.period:
                self._last[sym] = None
                return None

            s_tr = sum(tr_buf)
            s_dmp = sum(dmp_buf)
            s_dmm = sum(dmm_buf)
            self._s_tr[sym] = s_tr
            self._s_dm_plus[sym] = s_dmp
            self._s_dm_minus[sym] = s_dmm
        else:
            s_tr = self._s_tr[sym] - (self._s_tr[sym] / self.period) + tr
            s_dmp = self._s_dm_plus[sym] - (self._s_dm_plus[sym] / self.period) + dm_plus
            s_dmm = self._s_dm_minus[sym] - (self._s_dm_minus[sym] / self.period) + dm_minus
            self._s_tr[sym] = s_tr
            self._s_dm_plus[sym] = s_dmp
            self._s_dm_minus[sym] = s_dmm

        if s_tr == 0:
            self._last[sym] = None
            return None

        plus_di = 100.0 * s_dmp / s_tr
        minus_di = 100.0 * s_dmm / s_tr
        di_sum = plus_di + minus_di
        if di_sum == 0:
            self._last[sym] = None
            return None

        dx = 100.0 * abs(plus_di - minus_di) / di_sum

        if sym not in self._adx:
            dx_buf = self._dx_seed.setdefault(sym, [])
            dx_buf.append(dx)
            if len(dx_buf) < self.period:
                self._last[sym] = None
                return None
            adx = sum(dx_buf) / self.period
            self._adx[sym] = adx
            self._last[sym] = adx
            return adx

        prev_adx = self._adx[sym]
        adx = (prev_adx * (self.period - 1) + dx) / self.period
        self._adx[sym] = adx
        self._last[sym] = adx
        return adx

    def last(self, symbol: str) -> float | None:
        """ADX vừa tính ở lần update() gần nhất cho symbol này."""
        return self._last.get(symbol)
