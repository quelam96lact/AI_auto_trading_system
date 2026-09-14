"""BarLatch: Chỉ phát khung nến ĐÃ ĐÓNG ra NATS.

Một IntervalMessage từ SSI là snapshot của khung đang hình thành (volume luỹ kế,
close tạm thời). BarLatch giữ snapshot mới nhất cho mỗi mã. Chỉ khi sang khung mới
(ts > ts hiện tại) hoặc khi quá hạn (flush_due), khung cũ mới được CHỐT và trả về
để publish ra NATS.
"""

import time
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
        self._snapshot_counts: dict[str, int] = {}
        self.total_snapshots_received: int = 0
        self.last_snapshot_mono: float | None = None
        self.last_snapshot_ts: datetime | None = None

    def get_snapshot_count(self, symbol: str) -> int:
        """Lấy số snapshot hiện tại của khung đang mở cho symbol."""
        return self._snapshot_counts.get(symbol, 0)

    def offer(self, bar: Bar) -> Bar | None:
        """Nhận một snapshot bar.
        - Nếu snapshot thuộc khung đã CHỐT (bar.ts <= last_closed_ts): bỏ qua, trả None.
        - Nếu mã chưa có khung mở: ghi nhận khung này, trả None.
        - Nếu bar.ts == cur.ts: cập nhật snapshot mới (đầy đủ hơn), trả None.
        - Nếu bar.ts > cur.ts: khung cũ đã CHỐT -> cập nhật last_closed_ts, lưu bar mới, trả về khung cũ.
        - Nếu bar.ts < cur.ts: snapshot đến muộn -> alert WARN, bỏ qua, trả None.
        """
        sym = bar.symbol
        self.total_snapshots_received += 1
        self.last_snapshot_mono = time.monotonic()
        self.last_snapshot_ts = bar.ts

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
            self._snapshot_counts[sym] = 1
            return None

        if bar.ts == cur.ts:
            self._current_bars[sym] = bar
            self._snapshot_counts[sym] = self._snapshot_counts.get(sym, 0) + 1
            return None

        if bar.ts > cur.ts:
            closed = cur
            self._last_closed_ts[sym] = closed.ts
            count = self._snapshot_counts.get(sym, 1)
            object.__setattr__(closed, "snapshot_count", count)
            self._current_bars[sym] = bar
            self._snapshot_counts[sym] = 1
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
            count = self._snapshot_counts.pop(sym, 1)
            object.__setattr__(bar, "snapshot_count", count)
            del self._current_bars[sym]

        return due_bars

    def flush_all(self) -> list[Bar]:
        """Chốt tất cả các khung đang mở, dùng khi shutdown."""
        bars = list(self._current_bars.values())
        for bar in bars:
            self._last_closed_ts[bar.symbol] = bar.ts
            count = self._snapshot_counts.pop(bar.symbol, 1)
            object.__setattr__(bar, "snapshot_count", count)
        self._current_bars.clear()
        self._snapshot_counts.clear()
        return bars
