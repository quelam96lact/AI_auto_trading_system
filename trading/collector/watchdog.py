from collections.abc import Callable
from datetime import datetime, timedelta


class Watchdog:
    def __init__(self, stale_seconds: int, max_failures: int,
                 now_fn: Callable[[], datetime],
                 is_trading_fn: Callable[[datetime], bool],
                 on_stale: Callable[[], None], on_critical: Callable[[], None]):
        self.stale = timedelta(seconds=stale_seconds)
        self.max_failures = max_failures
        self.now_fn = now_fn
        self.is_trading_fn = is_trading_fn
        self.on_stale = on_stale
        self.on_critical = on_critical
        self._last_beat = now_fn()
        self._failures = 0

    def beat(self) -> None:
        self._last_beat = self.now_fn()
        self._failures = 0

    def check(self) -> None:
        now = self.now_fn()
        if not self.is_trading_fn(now):
            return
        if now - self._last_beat > self.stale:
            self._failures += 1
            self.on_stale()
            self._last_beat = now  # reset mốc để không dồn dập mỗi lần check
            if self._failures >= self.max_failures:
                self.on_critical()
                self._failures = 0