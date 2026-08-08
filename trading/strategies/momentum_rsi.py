"""MomentumBreakoutStrategy + RSI filter (tranh mua duoi/bán duoi vung cuc doan).

Subclass cua MomentumBreakoutStrategy - cung interface duck-typed
(compute_crossover(bar) -> "bull"|"bear"|None + .qty), cam thang vao
run_derivative_backtest() ma khong can sua engine.

VAI TRO: "bo GIAM RUI RO" hon "bo TANG LOI NHUAN" - muc tieu chinh la giam
MaxDD + tang win rate bang cach chan tin hieu breakout khi RSI o vung cuc
doan (bull khi RSI >= rsi_high = qua mua; bear khi RSI <= rsi_low = qua
ban). PnL tang nhe la he qua phu (tranh duoc cac lenh mua duoi/bán duoi
lo lon), khong phai muc tieu chinh - xem
docs/superpowers/research/2026-08-09-derivative-risk-eod-verification.md.

LUU Y interface: compute_crossover khong biet vi the dang giu -> filter tac
dong ca lenh MO lan lenh DONG cung chieu (bull cung la tin hieu dong short)
- thiet ke trend-following chu y, giong spike da kiem chung (RSI 70/30:
18 lenh/66.7%/+65.48%/MaxDD 8.1% vs baseline 21/52.4%/+60.05%/9.8%).
"""

from collections import deque

from trading.models import Bar
from trading.strategies.momentum_breakout import Crossover, MomentumBreakoutStrategy


class _RsiState:
    """RSI Wilder (smoothed) - state theo 1 symbol, pattern flat nhu
    TrailingStopManager/AtrCalculator."""

    def __init__(self, period: int):
        self.period = period
        self._closes: deque[float] = deque(maxlen=period + 1)
        self.rsi: float | None = None
        self._avg_gain: float | None = None
        self._avg_loss: float | None = None

    def update(self, close: float) -> float | None:
        """Cap nhat voi close moi, tra ve RSI hien tai (None khi chua du warmup)."""
        self._closes.append(close)
        if len(self._closes) < self.period + 1:
            return None
        if self._avg_gain is None:
            diffs = [self._closes[i + 1] - self._closes[i] for i in range(self.period)]
            gains = [d for d in diffs if d > 0]
            losses = [-d for d in diffs if d < 0]
            ag = sum(gains) / self.period
            al = sum(losses) / self.period
            self._avg_gain = ag
            self._avg_loss = al
        else:
            d = close - self._closes[-2]
            prev_gain = self._avg_gain
            prev_loss = self._avg_loss
            assert prev_gain is not None and prev_loss is not None
            ag = (prev_gain * (self.period - 1) + max(d, 0.0)) / self.period
            al = (prev_loss * (self.period - 1) + max(-d, 0.0)) / self.period
            self._avg_gain = ag
            self._avg_loss = al
        if al == 0:
            self.rsi = 100.0
        else:
            rs = ag / al
            self.rsi = 100.0 - 100.0 / (1.0 + rs)
        return self.rsi


class MomentumRSIStrategy(MomentumBreakoutStrategy):
    """Momentum breakout + RSI filter.

    Params them (ngoai params parent):
      rsi_period: chu ky RSI (mac dinh 14 - Wilder).
      rsi_high: chan "bull" khi RSI >= rsi_high (mac dinh 70.0 - qua mua).
      rsi_low:  chan "bear" khi RSI <= rsi_low (mac dinh 30.0 - qua ban).
    Default trung spike da kiem chung (2026-08-09).

    Luu y an toan ke thua: parent khong co state name-mangled (chi single
    underscore), goi super().compute_crossover(bar) TRUOC la an toan - state
    channel/volume/ATR cap nhat binh thuong, sau do loc tin hieu theo RSI.
    """

    def __init__(
        self,
        qty: int = 1,
        lookback: int = 10,
        volume_multiplier: float = 2.0,
        volume_period: int = 20,
        atr_period: int = 14,
        atr_pct_threshold: float = 0.0,
        rsi_period: int = 14,
        rsi_high: float = 70.0,
        rsi_low: float = 30.0,
    ):
        super().__init__(
            qty=qty,
            lookback=lookback,
            volume_multiplier=volume_multiplier,
            volume_period=volume_period,
            atr_period=atr_period,
            atr_pct_threshold=atr_pct_threshold,
        )
        self.rsi_period = rsi_period
        self.rsi_high = rsi_high
        self.rsi_low = rsi_low
        self._rsi: dict[str, _RsiState] = {}

    def compute_crossover(self, bar: Bar) -> Crossover | None:
        """Side-effect nhu parent: cap nhat state channel/volume/ATR + RSI.
        Tra ve tin hieu parent da loc RSI (bull/None/bear)."""
        sig = super().compute_crossover(bar)
        rsi = self._rsi.setdefault(bar.symbol, _RsiState(self.rsi_period)).update(bar.close)
        if sig is None or rsi is None:
            return None
        if sig == "bull" and rsi >= self.rsi_high:
            return None
        if sig == "bear" and rsi <= self.rsi_low:
            return None
        return sig


# Re-export for type-safe callers.
__all__ = ["MomentumRSIStrategy"]
