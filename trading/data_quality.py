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
    missing_middle_no_trading: int = 0
    missing_middle_collection_error: int = 0


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


def compute_daily_missing_counts(
    summaries: list[dict[str, Any]],
    trading_sessions: list[date],
    daily_counts: Mapping[date, int],
) -> dict[date, int]:
    """Tính số lượng mã đang trong đời sống [first_date, last_date] mà không có bar trên mỗi phiên.

    Phép tính: in_lifespan(d) - present(d).
    """
    first_dates = sorted(
        [s["first_date"] for s in summaries if s.get("first_date") is not None]
    )
    last_dates = sorted(
        [s["last_date"] for s in summaries if s.get("last_date") is not None]
    )
    missing_map: dict[date, int] = {}
    for d in trading_sessions:
        c_started = bisect_right(first_dates, d)
        c_ended = bisect_left(last_dates, d)
        in_lifespan = c_started - c_ended
        present = daily_counts.get(d, 0)
        missing_map[d] = max(0, in_lifespan - present)
    return missing_map


def classify_missing_dates(
    missing_dates: Collection[date],
    session_missing_counts: Mapping[date, int],
    threshold: int = 100,
) -> tuple[list[date], list[date]]:
    """Phân loại các ngày thiếu thành (no_trading_dates, collection_error_dates).

    - session_missing_counts[d] < threshold: vắng riêng lẻ -> không có giao dịch.
    - session_missing_counts[d] >= threshold: vắng tương quan thị trường -> lỗi thu thập.
    """
    no_trading: list[date] = []
    collection_error: list[date] = []
    for d in sorted(missing_dates):
        if session_missing_counts.get(d, 0) >= threshold:
            collection_error.append(d)
        else:
            no_trading.append(d)
    return no_trading, collection_error




def evaluate_symbol_completeness(
    symbol: str,
    first_date: date | None,
    last_date: date | None,
    total_bars: int,
    dirty_bars: int,
    trading_sessions: list[date],
    as_of_date: date | None = None,
    present_dates: Collection[date] | None = None,
    session_missing_counts: Mapping[date, int] | None = None,
    collection_error_threshold: int = 100,
) -> SymbolCompleteness:
    """Đánh giá tính đầy đủ của 1 mã dựa trên thống kê tổng hợp.

    - `missing_middle`: tổng số phiên thiếu trong vòng đời [first_date, last_date].
    - `missing_middle_no_trading`: số phiên thiếu giữa do không có giao dịch (vắng riêng lẻ).
    - `missing_middle_collection_error`: số phiên thiếu giữa do lỗi thu thập (vắng tương quan).
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
            missing_middle_no_trading=0,
            missing_middle_collection_error=0,
        )

    # 1. Tìm số phiên kỳ vọng trong vòng đời [first_date, min(last_date, as_of_date or trading_sessions[-1])]
    ref_last = min(last_date, as_of_date or trading_sessions[-1])
    idx_first = bisect_left(trading_sessions, first_date)
    idx_last = bisect_right(trading_sessions, ref_last) - 1

    if idx_first <= idx_last:
        expected_in_lifespan = idx_last - idx_first + 1
    else:
        expected_in_lifespan = 0

    # 2. Phân loại và tính missing_middle
    if present_dates is not None and session_missing_counts is not None:
        present_set = set(present_dates)
        middle_missing = [
            d
            for d in trading_sessions[max(0, idx_first) : idx_last + 1]
            if d not in present_set
        ]
        no_trading_dates, error_dates = classify_missing_dates(
            middle_missing,
            session_missing_counts,
            threshold=collection_error_threshold,
        )
        missing_middle_no_trading = len(no_trading_dates)
        missing_middle_collection_error = len(error_dates)
        missing_middle = missing_middle_no_trading + missing_middle_collection_error
    else:
        # Ước lượng số học nhanh
        missing_middle = max(0, expected_in_lifespan - total_bars)
        missing_middle_no_trading = missing_middle
        missing_middle_collection_error = 0

    # 3. Tìm số phiên thiếu ở đuôi sau last_date đến as_of_date
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
        missing_middle_no_trading=missing_middle_no_trading,
        missing_middle_collection_error=missing_middle_collection_error,
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
