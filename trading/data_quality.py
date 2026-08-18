from bisect import bisect_left, bisect_right
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class SymbolCompleteness:
    symbol: str
    first_date: date | None
    last_date: date | None
    total_bars: int
    dirty_bars: int
    expected_in_lifespan: int
    missing_middle: int
    missing_tail: int


def is_dirty_bar_dict(bar: Mapping[str, Any]) -> bool:
    """SPEC-1c: bar rác = có open/high/low/close <= 0.
    Khớp 100% định nghĩa của trading.backtest::_is_dirty.
    """
    return (
        bar.get("open", 0) <= 0
        or bar.get("high", 0) <= 0
        or bar.get("low", 0) <= 0
        or bar.get("close", 0) <= 0
    )


def infer_trading_sessions(
    daily_counts: Mapping[date, int],
    min_symbols: int = 100,
) -> list[date]:
    """Suy tập phiên giao dịch thực từ dữ liệu bars_daily theo đồng thuận số mã.

    Một ngày là phiên giao dịch nếu số mã có bar trong ngày đó >= min_symbols.
    Trả về danh sách ngày đã được sắp xếp tăng dần.
    """
    valid_dates = [d for d, count in daily_counts.items() if count >= min_symbols]
    return sorted(valid_dates)


def evaluate_symbol_completeness(
    symbol: str,
    first_date: date | None,
    last_date: date | None,
    total_bars: int,
    dirty_bars: int,
    trading_sessions: list[date],
    as_of_date: date | None = None,
) -> SymbolCompleteness:
    """Đánh giá tính đầy đủ của 1 mã dựa trên thống kê tổng hợp (O(log N)).

    - `missing_middle`: số phiên thiếu trong vòng đời [first_date, last_date].
    - `missing_tail`: số phiên thiếu sau last_date đến as_of_date.
    - `dirty_bars`: số bar rác (OHLC <= 0).
    """
    if not trading_sessions or first_date is None or last_date is None or total_bars <= 0:
        if trading_sessions:
            ref_date = as_of_date or trading_sessions[-1]
            idx_as_of = bisect_right(trading_sessions, ref_date)
            tail_missing = idx_as_of
        else:
            tail_missing = 0

        return SymbolCompleteness(
            symbol=symbol,
            first_date=first_date,
            last_date=last_date,
            total_bars=total_bars,
            dirty_bars=dirty_bars,
            expected_in_lifespan=0,
            missing_middle=0,
            missing_tail=tail_missing,
        )

    # 1. Tìm số phiên kỳ vọng trong vòng đời [first_date, last_date]
    idx_first = bisect_left(trading_sessions, first_date)
    idx_last = bisect_right(trading_sessions, last_date) - 1

    if idx_first <= idx_last:
        expected_in_lifespan = idx_last - idx_first + 1
    else:
        expected_in_lifespan = 0

    # Phép trừ số học hợp lệ vì đã chứng minh không có duplicate (symbol, date) trong bars_daily
    missing_middle = max(0, expected_in_lifespan - total_bars)

    # 2. Tìm số phiên thiếu ở đuôi sau last_date đến as_of_date
    ref_date = as_of_date or trading_sessions[-1]
    if ref_date > last_date:
        idx_as_of = bisect_right(trading_sessions, ref_date) - 1
        missing_tail = max(0, idx_as_of - idx_last)
    else:
        missing_tail = 0

    return SymbolCompleteness(
        symbol=symbol,
        first_date=first_date,
        last_date=last_date,
        total_bars=total_bars,
        dirty_bars=dirty_bars,
        expected_in_lifespan=expected_in_lifespan,
        missing_middle=missing_middle,
        missing_tail=missing_tail,
    )


def find_missing_dates(
    present_dates: Collection[date],
    trading_sessions: list[date],
    first_date: date | None = None,
    last_date: date | None = None,
    as_of_date: date | None = None,
) -> tuple[list[date], list[date]]:
    """Tìm danh sách cụ thể các ngày bị thiếu (ở giữa và ở đuôi).

    Chỉ gọi cho các mã thật sự có lỗ hổng (missing_middle > 0 hoặc missing_tail > 0).
    """
    present_set = set(present_dates)
    if not trading_sessions or first_date is None or last_date is None:
        ref_date = as_of_date or (trading_sessions[-1] if trading_sessions else None)
        if not ref_date:
            return [], []
        tail = [d for d in trading_sessions if d <= ref_date and d not in present_set]
        return [], tail

    ref_date = as_of_date or trading_sessions[-1]
    middle_missing = [
        d for d in trading_sessions if first_date <= d <= last_date and d not in present_set
    ]
    tail_missing = [
        d for d in trading_sessions if last_date < d <= ref_date and d not in present_set
    ]
    return middle_missing, tail_missing
