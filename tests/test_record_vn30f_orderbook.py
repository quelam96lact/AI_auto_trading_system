"""Kiểm thử đơn vị cho scripts/record_vn30f_orderbook.py (Brief 87 Task 0).

Kiểm tra 3 hàm thuần không cần mạng/SSI:
1. classify_message: Phân loại đúng QUOTE, TRADE, OTHER.
2. get_orderbook_filepath: Tạo đúng đường dẫn data/orderbook/<symbol>/<YYYY-MM-DD>.jsonl.gz theo giờ VN.
3. detect_silence_gaps: Đạt đủ ba tiêu chí của công cụ phát hiện:
   - Bắt đúng: Khoảng lặng 15s trong phiên phải được phát hiện.
   - Không báo giả: Khoảng nghỉ trưa 11:30 - 13:00 tuyệt đối không tính là khoảng lặng.
   - Mẫu số: Trả về và kiểm tra đúng số tin đã xét.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from pathlib import Path

import pytest

from scripts.record_vn30f_orderbook import (
    _parse_until_time,
    classify_message,
    compute_market_silence_seconds,
    detect_silence_gaps,
    get_orderbook_filepath,
)
from trading.calendar_vn import TZ


def test_classify_message():
    """Kiểm tra phân loại tin WebSocket SSI."""
    # 1. QUOTE
    q1 = {
        "type": "DataType.QUOTE",
        "symbol": "41I1GA000",
        "bid_prices": [1950.0],
        "ask_prices": [1950.5],
    }
    assert classify_message(q1) == "QUOTE"

    q2 = {
        "symbol": "41I1GA000",
        "bid_prices": [1950.0, 1949.5],
        "bid_volumes": [10, 20],
    }
    assert classify_message(q2) == "QUOTE"

    # 2. TRADE
    t1 = {
        "type": "DataType.TRADE",
        "symbol": "41I1GA000",
        "price": 1950.0,
        "quantity": 2,
        "side": "B",
    }
    assert classify_message(t1) == "TRADE"

    t2 = {
        "symbol": "41I1GA000",
        "price": 1950.0,
        "quantity": 5,
        "side": "S",
        "total_volume": 50000,
    }
    assert classify_message(t2) == "TRADE"

    # 3. OTHER (subscribe confirmation, heartbeat, rác)
    o1 = {"method": "subscribe", "channel": "DATA", "status": "ok"}
    assert classify_message(o1) == "OTHER"

    o2 = {"heartbeat": 12345678}
    assert classify_message(o2) == "OTHER"

    assert classify_message({}) == "OTHER"
    assert classify_message(None) == "OTHER"  # type: ignore


def test_get_orderbook_filepath(tmp_path: Path):
    """Kiểm tra quy tắc đặt tên file theo symbol và ngày giờ VN."""
    symbol = "41I1GA000"

    # Nến trong ngày giờ VN
    dt_vn = datetime(2026, 9, 25, 9, 15, 0, tzinfo=TZ)
    path = get_orderbook_filepath(tmp_path, symbol, dt_vn)

    expected = tmp_path / symbol / "2026-09-25.jsonl.gz"
    assert path == expected
    assert (tmp_path / symbol).exists()

    # Bẫy múi giờ UTC: 17:30 UTC ngày 24/09 = 00:30 VN ngày 25/09
    dt_utc = datetime(2026, 9, 24, 17, 30, 0, tzinfo=UTC)
    path_utc = get_orderbook_filepath(tmp_path, symbol, dt_utc)
    expected_utc = tmp_path / symbol / "2026-09-25.jsonl.gz"
    assert path_utc == expected_utc


def test_compute_market_silence_seconds_lunch_break_handling():
    """Kiểm tra tính số giây trong phiên - bỏ qua nghỉ trưa."""
    # 1. Cùng trong phiên sáng
    t1 = datetime(2026, 9, 25, 9, 15, 0, tzinfo=TZ)
    t2 = datetime(2026, 9, 25, 9, 15, 12, tzinfo=TZ)
    assert compute_market_silence_seconds(t1, t2) == pytest.approx(12.0)

    # 2. Xuyên qua nghỉ trưa (11:29:55 -> 13:00:03)
    # Thời gian trong phiên: 5s cuối phiên sáng + 3s đầu phiên chiều = 8s
    # Mặc dù đồng hồ trôi qua 1h 30m 8s!
    t3 = datetime(2026, 9, 25, 11, 29, 55, tzinfo=TZ)
    t4 = datetime(2026, 9, 25, 13, 0, 3, tzinfo=TZ)
    assert compute_market_silence_seconds(t3, t4) == pytest.approx(8.0)

    # 3. Hoàn toàn nằm trong giờ nghỉ trưa (11:35 -> 12:45) -> 0.0s
    t5 = datetime(2026, 9, 25, 11, 35, 0, tzinfo=TZ)
    t6 = datetime(2026, 9, 25, 12, 45, 0, tzinfo=TZ)
    assert compute_market_silence_seconds(t5, t6) == 0.0


def test_detect_silence_gaps_three_criteria():
    """Kiểm tra công cụ dò khoảng lặng đạt đủ ba tiêu chí:

    1. Bắt đúng: Khoảng lặng 15s trong phiên phải được phát hiện.
    2. Không báo giả: Khoảng nghỉ trưa 11:30 - 13:00 không được báo khoảng lặng.
    3. Mẫu số: Trả về chính xác số tin đã xem xét.
    """
    # Chuỗi dựng tay gồm 5 tin:
    # m0: 11:29:30
    # m1: 11:29:32 (gap = 2s)
    # m2: 11:29:47 (gap = 15s -> BẮT ĐÚNG)
    # m3: 11:29:56 (gap = 9s)
    # m4: 13:00:03 (3s sau mở phiên chiều -> market gap = 4s + 3s = 7s -> KHÔNG BÁO GIẢ)
    m0 = datetime(2026, 9, 25, 11, 29, 30, tzinfo=TZ)
    m1 = datetime(2026, 9, 25, 11, 29, 32, tzinfo=TZ)
    m2 = datetime(2026, 9, 25, 11, 29, 47, tzinfo=TZ)
    m3 = datetime(2026, 9, 25, 11, 29, 56, tzinfo=TZ)
    m4 = datetime(2026, 9, 25, 13, 0, 3, tzinfo=TZ)

    timestamps = [m0, m1, m2, m3, m4]

    max_gap, long_gaps, total_considered = detect_silence_gaps(
        timestamps, min_gap_seconds=10.0
    )

    # Tiêu chí 3: Mẫu số đúng
    assert total_considered == 5

    # Tiêu chí 1: Bắt đúng khoảng lặng 15s
    assert max_gap == pytest.approx(15.0)
    assert len(long_gaps) == 1
    assert long_gaps[0][0] == m1
    assert long_gaps[0][1] == m2
    assert long_gaps[0][2] == pytest.approx(15.0)

    # Tiêu chí 2: Không báo giả khoảng nghỉ trưa (m3 -> m4 có đồng hồ > 1.5h nhưng gap phiên chỉ 7s)
    gaps_between_m3_m4 = [g for g in long_gaps if g[0] == m3 and g[1] == m4]
    assert len(gaps_between_m3_m4) == 0


def test_parse_until_time():
    """Kiểm tra parse chuỗi giờ tự dừng."""
    assert _parse_until_time("09:05") == time(9, 5, 0)
    assert _parse_until_time("14:46:30") == time(14, 46, 30)
    assert _parse_until_time(None) is None

    with pytest.raises(ValueError):
        _parse_until_time("invalid_time")
