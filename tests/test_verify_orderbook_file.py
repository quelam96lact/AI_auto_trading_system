"""Kiểm thử đơn vị cho scripts/verify_orderbook_file.py (Brief 92 Task 2).

Kiểm chứng các hàm thuần:
1. Đủ tin, phủ 100% -> đạt, is_valid = True.
2. Thiếu vài ô, phủ 85% -> không đạt, nêu đúng các ô trống.
3. Có 1 dòng rác không parse được -> không đạt, đếm đúng 1.
4. Ca biên: file chỉ có tin ngoài giờ (ATO 08:45-08:55) -> độ phủ 0%, không đạt, không crash.
5. Đếm ô đúng: nghỉ trưa 11:30-13:00 hoàn toàn không nằm trong mẫu số (mẫu số luôn là 51 ô).
6. Mã hợp đồng không phải front-month / không gọi được SSI -> không đạt.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest

from scripts.verify_orderbook_file import (
    OrderbookMetrics,
    compute_slot_coverage,
    evaluate_orderbook_verification,
    generate_continuous_session_slots,
    scan_orderbook_stream,
)
from trading.calendar_vn import TZ


def test_task2_slots_exclude_lunch_break():
    """Ca 5: Đếm ô đúng — nghỉ trưa 11:30 - 13:00 KHÔNG nằm trong mẫu số.

    - Sáng 09:00 -> 11:30 (150 phút = 30 ô 5 phút)
    - Chiều 13:00 -> 14:45 (105 phút = 21 ô 5 phút)
    - Tổng mẫu số: đúng 51 ô.
    """
    d = date(2026, 9, 28)
    slots = generate_continuous_session_slots(d, slot_minutes=5)
    assert len(slots) == 51

    # Kiểm tra nhãn ô
    slot_labels = [s[2] for s in slots]
    assert slot_labels[0] == "09:00-09:05"
    assert slot_labels[29] == "11:25-11:30"
    assert slot_labels[30] == "13:00-13:05"
    assert slot_labels[50] == "14:40-14:45"

    # Tuyệt đối không có ô nào thuộc khoảng nghỉ trưa 11:30 - 13:00
    for s_start, s_end, label in slots:
        assert not (
            s_start.time() >= datetime.strptime("11:30", "%H:%M").time()
            and s_end.time() <= datetime.strptime("13:00", "%H:%M").time()
        ), f"Ô {label} bị lọt vào giờ nghỉ trưa!"


def test_task2_full_coverage_100_percent_passes():
    """Ca 1: Đủ tin, phủ 100% -> ĐẠT (is_valid = True)."""
    d = date(2026, 9, 28)
    slots = generate_continuous_session_slots(d, slot_minutes=5)

    # Tạo mỗi ô 1 timestamp
    timestamps = [s[0] + timedelta(minutes=1) for s in slots]
    total, covered, ratio, empty = compute_slot_coverage(timestamps, d)

    assert total == 51
    assert covered == 51
    assert ratio == 1.0
    assert len(empty) == 0

    metrics = OrderbookMetrics(
        symbol="41I1GA000",
        target_date=d,
        counts={"QUOTE": 10000, "TRADE": 1000, "OTHER": 0},
        unparseable_lines=0,
        first_recv_ts=timestamps[0],
        last_recv_ts=timestamps[-1],
        total_slots=total,
        covered_slots=covered,
        coverage_ratio=ratio,
        empty_slots=empty,
    )

    result = evaluate_orderbook_verification(metrics, expected_symbol="41I1GA000")
    assert result.is_valid is True
    assert len(result.reasons) == 0
    assert result.criteria_status == {
        "parseable": True,
        "coverage": True,
        "front_month": True,
    }


def test_task2_partial_coverage_85_percent_fails_and_lists_empty_slots():
    """Ca 2: Thiếu vài ô, độ phủ ~84.3% (< 90%) -> KHÔNG ĐẠT và nêu đúng các ô trống."""
    d = date(2026, 9, 28)
    slots = generate_continuous_session_slots(d, slot_minutes=5)

    # Bỏ qua 8 ô giữa phiên sáng (ô index 10 -> 17, tức 09:50 -> 10:30)
    # Còn lại 43 ô / 51 = 84.31% độ phủ
    covered_indices = [i for i in range(51) if i < 10 or i > 17]
    timestamps = [slots[i][0] + timedelta(minutes=1) for i in covered_indices]

    total, covered, ratio, empty = compute_slot_coverage(timestamps, d)
    assert total == 51
    assert covered == 43
    assert ratio == pytest.approx(43 / 51, rel=1e-3)
    assert len(empty) == 8

    # Nêu đúng danh sách 8 ô trống
    expected_empty_labels = [slots[i][2] for i in range(10, 18)]
    assert empty == expected_empty_labels

    metrics = OrderbookMetrics(
        symbol="41I1GA000",
        target_date=d,
        counts={"QUOTE": 8000, "TRADE": 800, "OTHER": 0},
        unparseable_lines=0,
        first_recv_ts=timestamps[0],
        last_recv_ts=timestamps[-1],
        total_slots=total,
        covered_slots=covered,
        coverage_ratio=ratio,
        empty_slots=empty,
    )

    result = evaluate_orderbook_verification(metrics, expected_symbol="41I1GA000")
    assert result.is_valid is False
    assert result.criteria_status["coverage"] is False
    assert any("Độ phủ phiên chỉ đạt" in r for r in result.reasons)


def test_task2_unparseable_line_fails_and_counts_exact_1():
    """Ca 3: Có đúng 1 dòng rác không parse được -> KHÔNG ĐẠT, đếm đúng 1."""
    ts = datetime(2026, 9, 28, 9, 15, 0, tzinfo=TZ).isoformat()

    valid_line_1 = json.dumps({"symbol": "41I1GA000", "type": "QUOTE", "recv_ts": ts})
    garbage_line = "CORRUPTED_NON_JSON_RAW_DATA_12345"
    valid_line_2 = json.dumps({"symbol": "41I1GA000", "type": "TRADE", "recv_ts": ts})

    lines = [valid_line_1, garbage_line, valid_line_2]
    metrics = scan_orderbook_stream(lines)

    assert metrics.unparseable_lines == 1
    assert metrics.counts["QUOTE"] == 1
    assert metrics.counts["TRADE"] == 1
    assert metrics.symbol == "41I1GA000"

    result = evaluate_orderbook_verification(metrics, expected_symbol="41I1GA000")
    assert result.is_valid is False
    assert result.criteria_status["parseable"] is False
    assert any("Có 1 dòng dữ liệu không parse được" in r for r in result.reasons)


def test_task2_edge_case_only_ato_messages_gives_0_percent_coverage_no_crash():
    """Ca 4: Biên — file chỉ có tin ngoài giờ (ATO 08:45–08:55) -> độ phủ 0%, không đạt, KHÔNG CRASH."""
    t_ato_1 = datetime(2026, 9, 28, 8, 45, 0, tzinfo=TZ)
    t_ato_2 = datetime(2026, 9, 28, 8, 55, 0, tzinfo=TZ)

    lines = [
        json.dumps({"symbol": "41I1GA000", "type": "QUOTE", "recv_ts": t_ato_1.isoformat()}),
        json.dumps({"symbol": "41I1GA000", "type": "QUOTE", "recv_ts": t_ato_2.isoformat()}),
    ]
    metrics = scan_orderbook_stream(lines)

    assert metrics.unparseable_lines == 0
    assert metrics.total_slots == 51
    assert metrics.covered_slots == 0
    assert metrics.coverage_ratio == 0.0
    assert len(metrics.empty_slots) == 51

    result = evaluate_orderbook_verification(metrics, expected_symbol="41I1GA000")
    assert result.is_valid is False
    assert result.criteria_status["coverage"] is False


def test_task2_wrong_contract_symbol_or_ssi_error_fails():
    """Kiểm tra tiêu chí 3: Mã ghi được sai front-month, hoặc không gọi được SSI -> KHÔNG ĐẠT."""
    d = date(2026, 9, 28)
    metrics = OrderbookMetrics(
        symbol="41I1GB000",  # Mã ghi là GB (tháng 11)
        target_date=d,
        counts={"QUOTE": 10000, "TRADE": 1000, "OTHER": 0},
        unparseable_lines=0,
        first_recv_ts=datetime(2026, 9, 28, 9, 0, tzinfo=TZ),
        last_recv_ts=datetime(2026, 9, 28, 14, 45, tzinfo=TZ),
        total_slots=51,
        covered_slots=51,
        coverage_ratio=1.0,
        empty_slots=[],
    )

    # 1. Sai mã (kỳ vọng 41I1GA000, thực tế 41I1GB000)
    res_wrong = evaluate_orderbook_verification(metrics, expected_symbol="41I1GA000")
    assert res_wrong.is_valid is False
    assert res_wrong.criteria_status["front_month"] is False
    assert any("không phải front-month" in r for r in res_wrong.reasons)

    # 2. Không gọi được SSI
    res_ssi_err = evaluate_orderbook_verification(
        metrics, expected_symbol=None, front_month_error="SSI timeout"
    )
    assert res_ssi_err.is_valid is False
    assert res_ssi_err.criteria_status["front_month"] is False
    assert any("Không gọi được SSI" in r for r in res_ssi_err.reasons)
