from trading.models import Bar


class TrailingStopManager:
    """Trailing stop-loss theo ATR, state theo tung symbol (cung pattern
    voi AtrCalculator/SmaCrossStrategy). KHONG co take-profit - chi trailing
    stop-loss, de loi chay (trend-following)."""

    def __init__(self, sl_multiplier: float = 2.0):
        self.sl_multiplier = sl_multiplier
        self._highest: dict[str, float] = {}

    def on_position_opened(self, symbol: str, fill_price: float) -> None:
        """Goi khi 1 vi the moi mo (BUY fill) - khoi tao highest_price."""
        self._highest[symbol] = fill_price

    def on_position_closed(self, symbol: str) -> None:
        """Goi khi vi the dong hoan toan (bat ke ly do) - xoa state de lan
        mo vi the tiep theo bat dau lai tu dau."""
        self._highest.pop(symbol, None)

    def is_tracking(self, symbol: str) -> bool:
        """Trailing stop co dang theo doi symbol nay khong (on_position_opened
        da duoc goi). Phan biet voi check() tra None — None la MO HO (co the
        la 'chua theo doi', co the la 'chua cham stop'); dung method cong khai
        nay thay vi doc _highest tu ben ngoai (RTS-2: vi the that mo GIUA
        PHIEN can duoc khoi tao truoc khi check)."""
        return symbol in self._highest

    def check(self, bar: Bar, atr: float | None) -> float | None:
        """Cap nhat highest_price_since_entry, tra ve gia khop neu bar nay
        cham stop, else None. Khong lam gi neu chua co vi the dang theo doi
        cho symbol nay (on_position_opened chua duoc goi)."""
        highest = self._highest.get(bar.symbol)
        if highest is None:
            return None
        highest = max(highest, bar.high)
        self._highest[bar.symbol] = highest

        if atr is None:
            return None
        stop_level = highest - atr * self.sl_multiplier
        if bar.low <= stop_level:
            return min(bar.open, stop_level)
        return None
