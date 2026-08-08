from collections import deque
from typing import Literal

from trading.indicators import AtrCalculator
from trading.models import Bar

Crossover = Literal["bull", "bear"]


class MomentumBreakoutStrategy:
    """Bull flag / bear breakdown breakout theo Donchian channel + volume spike.

    Dich tu chien luoc momentum scalping cua Ross Cameron (Warrior Trading)
    sang phai sinh VN30F1M (1 instrument duy nhat, long/short T+0) - xem
    docs/superpowers/plans/2026-08-08-momentum-breakout-strategy.md.

    Interface duck-typed de cam thang vao run_derivative_backtest() ma khong
    can sua no: compute_crossover(bar) -> "bull"|"bear"|None + thuoc tinh .qty
    (giong SmaCrossStrategy).

    THAM SO CHUA DUOC TUNE BANG DU LIEU THAT VN30F1M - day la default hop ly
    (lookback=10, volume_multiplier=2.0, volume_period=20), khong phai so da
    kiem chung; atr_pct_threshold=0.0 = tat ATR% filter mac dinh.
    """

    def __init__(
        self,
        qty: int = 1,
        lookback: int = 10,
        volume_multiplier: float = 2.0,
        volume_period: int = 20,
        atr_period: int = 14,
        atr_pct_threshold: float = 0.0,  # 0.0 = tat filter (mac dinh)
    ):
        self.qty = qty
        self.lookback = lookback
        self.volume_multiplier = volume_multiplier
        self.volume_period = volume_period
        self.atr_pct_threshold = atr_pct_threshold
        self._highs: dict[str, deque] = {}
        self._lows: dict[str, deque] = {}
        self._volumes: dict[str, deque] = {}
        self._last_crossover: dict[str, Crossover | None] = {}
        self._last_atr: dict[str, float | None] = {}
        self._atr = AtrCalculator(period=atr_period)

    def compute_crossover(self, bar: Bar) -> Crossover | None:
        """Side-effect: cap nhat state noi bo (kenh gia, volume TB, ATR) -
        CHI duoc goi dung 1 lan/bar/symbol, cung contract voi
        SmaCrossStrategy.compute_crossover(). KHONG tu gate theo vi the dang
        giu (tach biet phat hien tin hieu khoi quyet dinh mo/dong, giong
        SmaCrossStrategy).

        Tin hieu "bull" khi close vuot kenh gia cao nhat (Donchian high) cua
        `lookback` bar truoc do + volume spike; "bear" nguoc lai voi Donchian
        low. ATR% filter tuy chon (mac dinh tat) de tranh thit truong di
        ngang - giong co che SmaCrossStrategy.
        """
        atr = self._atr.update(bar)

        highs = self._highs.setdefault(bar.symbol, deque(maxlen=self.lookback))
        lows = self._lows.setdefault(bar.symbol, deque(maxlen=self.lookback))
        volumes = self._volumes.setdefault(bar.symbol, deque(maxlen=self.volume_period))

        # Tat ca deque chua cac bar TRUOC bar hien tai - tinh channel/avg
        # TRUOC khi append de bar hien tai khong tu tham chieu chinh no.
        if len(highs) < self.lookback or len(volumes) < self.volume_period:
            highs.append(bar.high)
            lows.append(bar.low)
            volumes.append(bar.volume)
            self._last_crossover[bar.symbol] = None
            self._last_atr[bar.symbol] = atr
            return None

        channel_high = max(highs)
        channel_low = min(lows)
        avg_volume = sum(volumes) / len(volumes)

        volume_spike = avg_volume > 0 and bar.volume >= self.volume_multiplier * avg_volume

        candidate: Crossover | None = None
        if bar.close > channel_high and volume_spike:
            candidate = "bull"
        elif bar.close < channel_low and volume_spike:
            candidate = "bear"

        # ATR% filter (chi ap dung khi bat) + guard close<=0 BAT BUOC co du
        # filter tat hay bat, tranh ZeroDivisionError voi bar di dang (da co
        # tien le bug that trong repo nay - xem golive-prep-status-2026-08-01).
        if candidate is not None and (
            bar.close <= 0
            or (
                self.atr_pct_threshold > 0
                and (atr is None or atr / bar.close < self.atr_pct_threshold)
            )
        ):
            candidate = None

        highs.append(bar.high)
        lows.append(bar.low)
        volumes.append(bar.volume)

        self._last_crossover[bar.symbol] = candidate
        self._last_atr[bar.symbol] = atr
        return candidate

    def last_crossover(self, symbol: str) -> Crossover | None:
        """Crossover vua tinh o lan compute_crossover() gan nhat cho symbol nay."""
        return self._last_crossover.get(symbol)

    def last_atr(self, symbol: str) -> float | None:
        """ATR vua tinh o lan compute_crossover() gan nhat cho symbol nay."""
        return self._last_atr.get(symbol)


# Re-export for type-safe callers.
__all__ = ["Crossover", "MomentumBreakoutStrategy"]
