"""BarLatch: Chỉ phát khung nến ĐÃ ĐÓNG ra NATS.

Một IntervalMessage từ SSI là snapshot của khung đang hình thành (volume luỹ kế,
close tạm thời). BarLatch giữ snapshot mới nhất cho mỗi mã. Chỉ khi sang khung mới
(ts > ts hiện tại) hoặc khi quá hạn (flush_due), khung cũ mới được CHỐT và trả về
để publish ra NATS.
"""

from datetime import datetime, timedelta

from trading.alerts import alert
from trading.models import Bar


class BarLatch:
    def __init__(
        self,
        interval_seconds: int = 300,
        grace_seconds: int = 60,
    ) -> None:
        self.interval = timedelta(seconds=interval_seconds)
        self.grace = timedelta(seconds=grace_seconds)
        self._current_bars: dict[str, Bar] = {}
        self._last_closed_ts: dict[str, datetime] = {}

    def offer(self, bar: Bar) -> Bar | None:
        """Nhận một snapshot bar.
        - Nếu snapshot thuộc khung đã CHỐT (bar.ts <= last_closed_ts): bỏ qua, trả None.
        - Nếu mã chưa có khung mở: ghi nhận khung này, trả None.
        - Nếu bar.ts == cur.ts: cập nhật snapshot mới (đầy đủ hơn), trả None.
        - Nếu bar.ts > cur.ts: khung cũ đã CHỐT -> cập nhật last_closed_ts, lưu bar mới, trả về khung cũ.
        - Nếu bar.ts < cur.ts: snapshot đến muộn -> alert WARN, bỏ qua, trả None.
        """
        sym = bar.symbol
        last_closed = self._last_closed_ts.get(sym)
        if last_closed is not None and bar.ts <= last_closed:
            alert(
                "WARN",
                "out-of-order snapshot received for already closed frame, skipping",
                symbol=sym,
                incoming_ts=bar.ts.isoformat(),
                last_closed_ts=last_closed.isoformat(),
            )
            return None

        cur = self._current_bars.get(sym)
        if cur is None:
            self._current_bars[sym] = bar
            return None

        if bar.ts == cur.ts:
            self._current_bars[sym] = bar
            return None

        if bar.ts > cur.ts:
            closed = cur
            self._last_closed_ts[sym] = closed.ts
            self._current_bars[sym] = bar
            return closed

        # bar.ts < cur.ts: snapshot đến muộn
        alert(
            "WARN",
            "out-of-order bar snapshot received, skipping",
            symbol=sym,
            incoming_ts=bar.ts.isoformat(),
            current_ts=cur.ts.isoformat(),
        )
        return None

    def flush_due(self, now: datetime) -> list[Bar]:
        """Chốt mọi khung đang mở đã quá hạn an toàn (now >= ts + interval + grace)."""
        due_bars: list[Bar] = []
        due_syms: list[str] = []
        for sym, bar in self._current_bars.items():
            threshold = bar.ts + self.interval + self.grace
            if now >= threshold:
                due_bars.append(bar)
                due_syms.append(sym)

        for sym, bar in zip(due_syms, due_bars):
            self._last_closed_ts[sym] = bar.ts
            del self._current_bars[sym]

        return due_bars

    def flush_all(self) -> list[Bar]:
        """Chốt tất cả các khung đang mở, dùng khi shutdown."""
        bars = list(self._current_bars.values())
        for bar in bars:
            self._last_closed_ts[bar.symbol] = bar.ts
        self._current_bars.clear()
        return bars
