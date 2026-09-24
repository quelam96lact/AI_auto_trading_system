"""Kiểm thử đơn vị cho phân hệ chuỗi phái sinh liên tục (Brief 83 Task 3).

Kiểm chứng bằng số tính tay độc lập (không dùng code sinh kỳ vọng):
1. Hai hợp đồng, roll 1 lần, gap = +5 điểm: nến cũ cộng 5, nến mới không đổi.
2. Ba hợp đồng, roll 2 lần, gap +5 rồi -3: phần xa nhất cộng dồn +2.
3. Tính bất biến: hiệu giá và spread nến liền kề trước và sau back-adjust y nguyên.
4. Ca không có nến chồng lấn tại mốc roll -> báo lỗi ValueError rõ ràng.
5. Kiểm thử phá hoại (mutation check).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from trading.calendar_vn import TZ
from trading.derivative_series import (
    ContractMetadata,
    build_roll_schedule,
    compute_roll_gaps,
    stitch_continuous,
)
from trading.models import Bar


def _make_bar(
    symbol: str,
    dt_str: str,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int = 100,
) -> Bar:
    # dt_str: "YYYY-MM-DD HH:MM:SS"
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
    return Bar(
        symbol=symbol,
        ts=dt,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def test_build_roll_schedule():
    """Kiểm thử sinh lịch roll chuẩn xác từ metadata hợp đồng."""
    contracts = [
        ContractMetadata("C2", last_trading_date=date(2026, 9, 17), first_trading_date=date(2026, 1, 16)),
        ContractMetadata("C1", last_trading_date=date(2026, 8, 20), first_trading_date=date(2026, 6, 19)),
        ContractMetadata("C3", last_trading_date=date(2026, 10, 15), first_trading_date=date(2026, 8, 21)),
    ]

    sched = build_roll_schedule(contracts)
    assert len(sched) == 3
    # Phải được sắp xếp theo thời gian: C1 -> C2 -> C3
    assert sched[0] == ("C1", date(2026, 6, 19), date(2026, 8, 20))
    # C2 bắt đầu từ ngày sau khi C1 hết hạn (2026-08-21) tới ngày C2 hết hạn (2026-09-17)
    assert sched[1] == ("C2", date(2026, 8, 21), date(2026, 9, 17))
    # C3 bắt đầu từ ngày sau khi C2 hết hạn (2026-09-18) tới ngày C3 hết hạn (2026-10-15)
    assert sched[2] == ("C3", date(2026, 9, 18), date(2026, 10, 15))


def test_stitch_continuous_two_contracts_single_roll_gap_plus_five():
    """Kiểm thử 1: Hai hợp đồng, roll 1 lần, gap = +5.

    Hợp đồng cũ (C1) phải được cộng chính xác +5.0 cho toàn bộ OHLC.
    Hợp đồng mới (C2) giữ nguyên giá trị.
    """
    # Mốc roll: cuối ngày 2026-09-02 (ngày hết hạn của C1)
    # Tại 2026-09-02 14:45:00:
    # C1.close = 1005.0
    # C2.close = 1010.0
    # gap = 1010.0 - 1005.0 = +5.0

    b1_c1 = _make_bar("C1", "2026-09-01 09:00:00", 1000.0, 1005.0, 998.0, 1002.0, 100)
    b2_c1 = _make_bar("C1", "2026-09-02 14:45:00", 1002.0, 1008.0, 1000.0, 1005.0, 200)

    # C2 có nến chồng lấn tại 14:45 ngày 2026-09-02 và nến sau roll ngày 2026-09-03
    b2_c2 = _make_bar("C2", "2026-09-02 14:45:00", 1007.0, 1012.0, 1006.0, 1010.0, 50)
    b3_c2 = _make_bar("C2", "2026-09-03 09:00:00", 1010.0, 1015.0, 1009.0, 1012.0, 300)

    bars_by_symbol = {
        "C1": [b1_c1, b2_c1],
        "C2": [b2_c2, b3_c2],
    }
    sched = [
        ("C1", date(2026, 9, 1), date(2026, 9, 2)),
        ("C2", date(2026, 9, 3), date(2026, 9, 10)),
    ]

    gaps = compute_roll_gaps(bars_by_symbol, sched)
    assert len(gaps) == 1
    assert gaps[0].gap == 5.0
    assert gaps[0].cumulative_adjustment == 5.0
    assert gaps[0].from_close == 1005.0
    assert gaps[0].to_close == 1010.0

    stitched = stitch_continuous(bars_by_symbol, sched)
    assert len(stitched) == 3

    # Kiểm từng giá trị OHLC tính tay của C1 (đều được cộng 5):
    # Nến 1: Open 1000->1005, High 1005->1010, Low 998->1003, Close 1002->1007, Vol 100
    assert stitched[0].symbol == "VN30F1M_CONT"
    assert stitched[0].ts == b1_c1.ts
    assert stitched[0].open == 1005.0
    assert stitched[0].high == 1010.0
    assert stitched[0].low == 1003.0
    assert stitched[0].close == 1007.0
    assert stitched[0].volume == 100

    # Nến 2: Open 1002->1007, High 1008->1013, Low 1000->1005, Close 1005->1010, Vol 200
    assert stitched[1].symbol == "VN30F1M_CONT"
    assert stitched[1].ts == b2_c1.ts
    assert stitched[1].open == 1007.0
    assert stitched[1].high == 1013.0
    assert stitched[1].low == 1005.0
    assert stitched[1].close == 1010.0
    assert stitched[1].volume == 200

    # Nến 3: từ C2 (hợp đồng mới nhất, giữ nguyên giá trị)
    assert stitched[2].symbol == "VN30F1M_CONT"
    assert stitched[2].ts == b3_c2.ts
    assert stitched[2].open == 1010.0
    assert stitched[2].high == 1015.0
    assert stitched[2].low == 1009.0
    assert stitched[2].close == 1012.0
    assert stitched[2].volume == 300


def test_stitch_continuous_three_contracts_cumulative_adjustment():
    """Kiểm thử 2: Ba hợp đồng, roll hai lần, gap +5 rồi -3:

    Phần xa nhất (C1) phải cộng dồn +2.
    Phần giữa (C2) cộng dồn -3.
    Phần mới nhất (C3) cộng 0.
    """
    # Mốc roll 1 (cuối 2026-09-02): C1 -> C2
    # C1.close = 105.0, C2.close = 110.0 -> Gap 1 = +5.0
    # Mốc roll 2 (cuối 2026-09-04): C2 -> C3
    # C2.close = 115.0, C3.close = 112.0 -> Gap 2 = -3.0

    b_c1_d1 = _make_bar("C1", "2026-09-01 10:00:00", 98.0, 102.0, 97.0, 100.0)
    b_c1_d2 = _make_bar("C1", "2026-09-02 14:45:00", 103.0, 106.0, 102.0, 105.0)

    b_c2_d2 = _make_bar("C2", "2026-09-02 14:45:00", 108.0, 111.0, 107.0, 110.0)
    b_c2_d3 = _make_bar("C2", "2026-09-03 10:00:00", 110.0, 114.0, 109.0, 112.0)
    b_c2_d4 = _make_bar("C2", "2026-09-04 14:45:00", 113.0, 116.0, 112.0, 115.0)

    b_c3_d4 = _make_bar("C3", "2026-09-04 14:45:00", 111.0, 113.0, 110.0, 112.0)
    b_c3_d5 = _make_bar("C3", "2026-09-05 10:00:00", 116.0, 120.0, 115.0, 118.0)

    bars_by_symbol = {
        "C1": [b_c1_d1, b_c1_d2],
        "C2": [b_c2_d2, b_c2_d3, b_c2_d4],
        "C3": [b_c3_d4, b_c3_d5],
    }
    sched = [
        ("C1", date(2026, 9, 1), date(2026, 9, 2)),
        ("C2", date(2026, 9, 3), date(2026, 9, 4)),
        ("C3", date(2026, 9, 5), date(2026, 9, 6)),
    ]

    gaps = compute_roll_gaps(bars_by_symbol, sched)
    assert len(gaps) == 2
    assert gaps[0].gap == 5.0
    assert gaps[0].cumulative_adjustment == 2.0  # +5.0 + (-3.0) = +2.0!
    assert gaps[1].gap == -3.0
    assert gaps[1].cumulative_adjustment == -3.0

    stitched = stitch_continuous(bars_by_symbol, sched)
    assert len(stitched) == 5

    # C1 (ngày 1, 2) được cộng dồn +2.0:
    # d1 close: 100 + 2 = 102.0
    assert stitched[0].close == 102.0
    # d2 close: 105 + 2 = 107.0
    assert stitched[1].close == 107.0

    # C2 (ngày 3, 4) được cộng dồn -3.0:
    # d3 close: 112 - 3 = 109.0
    assert stitched[2].close == 109.0
    # d4 close: 115 - 3 = 112.0
    assert stitched[3].close == 112.0

    # C3 (ngày 5) mới nhất: giữ nguyên 0:
    # d5 close: 118 + 0 = 118.0
    assert stitched[4].close == 118.0


def test_invariance_of_price_differences():
    """Kiểm thử 3: Tính bất biến — hiệu giá và spread trước và sau back-adjust y nguyên.

    Với mọi cặp nến liền nhau trong cùng một hợp đồng, (Close_{t+1} - Close_t)
    và (High_t - Low_t) trước và sau back-adjust phải bằng nhau tuyệt đối.
    """
    b1 = _make_bar("C1", "2026-09-01 09:00:00", 1000.0, 1005.0, 995.0, 1002.0)
    b2 = _make_bar("C1", "2026-09-01 09:05:00", 1002.0, 1012.0, 1001.0, 1010.0)
    b3 = _make_bar("C1", "2026-09-01 09:10:00", 1010.0, 1011.0, 1004.0, 1007.0)
    b4 = _make_bar("C1", "2026-09-02 14:45:00", 1007.0, 1015.0, 1006.0, 1014.0)

    b_c2_overlap = _make_bar("C2", "2026-09-02 14:45:00", 1018.0, 1025.0, 1016.0, 1022.0)
    b_c2_next = _make_bar("C2", "2026-09-03 09:00:00", 1022.0, 1028.0, 1020.0, 1026.0)

    raw_c1 = [b1, b2, b3, b4]
    bars_by_symbol = {
        "C1": raw_c1,
        "C2": [b_c2_overlap, b_c2_next],
    }
    sched = [
        ("C1", date(2026, 9, 1), date(2026, 9, 2)),
        ("C2", date(2026, 9, 3), date(2026, 9, 4)),
    ]

    stitched = stitch_continuous(bars_by_symbol, sched)
    stitched_c1 = stitched[:4]

    # Kiểm tra từng cặp nến liền nhau trong C1:
    for i in range(len(raw_c1) - 1):
        raw_diff = round(raw_c1[i + 1].close - raw_c1[i].close, 6)
        stitched_diff = round(stitched_c1[i + 1].close - stitched_c1[i].close, 6)
        assert stitched_diff == raw_diff, f"Lệch biến động close giữa nến {i} và {i+1}"

    # Kiểm tra spread High - Low của từng nến trong C1:
    for i in range(len(raw_c1)):
        raw_spread = round(raw_c1[i].high - raw_c1[i].low, 6)
        stitched_spread = round(stitched_c1[i].high - stitched_c1[i].low, 6)
        assert stitched_spread == raw_spread, f"Lệch spread High-Low tại nến {i}"


def test_missing_overlap_raises_clear_error():
    """Kiểm thử 4: Ca không có nến chồng lấn tại mốc roll -> phải báo lỗi rõ ràng."""
    b_c1 = _make_bar("C1", "2026-09-01 09:00:00", 1000.0, 1005.0, 995.0, 1000.0)
    # C2 chỉ bắt đầu xuất hiện dữ liệu từ ngày 2026-09-03, không hề có nến nào ngày 01 hoặc 02
    b_c2 = _make_bar("C2", "2026-09-03 09:00:00", 1010.0, 1015.0, 1005.0, 1010.0)

    bars_by_symbol = {
        "C1": [b_c1],
        "C2": [b_c2],
    }
    sched = [
        ("C1", date(2026, 9, 1), date(2026, 9, 2)),
        ("C2", date(2026, 9, 3), date(2026, 9, 4)),
    ]

    with pytest.raises(ValueError, match="Không tìm thấy nến chồng lấn"):
        compute_roll_gaps(bars_by_symbol, sched)

    with pytest.raises(ValueError, match="Không tìm thấy nến chồng lấn"):
        stitch_continuous(bars_by_symbol, sched)


def test_classify_bar_atc_equal_high_close():
    """Ca 1: 14:45 & H == C -> SỬA (FIX_ATC)."""
    from trading.derivative_series import (
        BarCleanAction,
        classify_bar_for_cleaning,
        clean_bar,
    )

    # Nến 14:45 với open=0, low=0, high=1970.0, close=1970.0 (H == C)
    bad_atc = _make_bar("41I1GA000", "2026-09-18 14:45:00", 0.0, 1970.0, 0.0, 1970.0, 7492)
    action = classify_bar_for_cleaning(bad_atc)
    assert action == BarCleanAction.FIX_ATC

    cleaned = clean_bar(bad_atc)
    assert cleaned is not None
    assert cleaned.open == 1970.0
    assert cleaned.high == 1970.0
    assert cleaned.low == 1970.0
    assert cleaned.close == 1970.0
    assert cleaned.volume == 7492


def test_classify_bar_atc_unequal_high_close():
    """Ca 2: 14:45 & H != C -> BÁO CÁO (REPORT, không sửa)."""
    from trading.derivative_series import (
        BarCleanAction,
        classify_bar_for_cleaning,
        clean_bar,
    )

    # Nến 14:45 với open=0, low=0, high=1975.0, close=1970.0 (H != C)
    weird_atc = _make_bar("41I1GA000", "2026-09-18 14:45:00", 0.0, 1975.0, 0.0, 1970.0, 5000)
    action = classify_bar_for_cleaning(weird_atc)
    assert action == BarCleanAction.REPORT

    cleaned = clean_bar(weird_atc)
    # Không tự ý sửa giá trị
    assert cleaned == weird_atc


def test_classify_bar_non_atc_delete():
    """Ca 3: 09:00 (hoặc giờ khác 14:45) có giá 0 -> XOÁ (DELETE)."""
    from trading.derivative_series import (
        BarCleanAction,
        classify_bar_for_cleaning,
        clean_bar,
    )

    # Nến 09:00 với open=0, low=0, high=1977.3, close=1975.9
    bad_0900 = _make_bar("41I1GA000", "2026-09-21 09:00:00", 0.0, 1977.3, 0.0, 1975.9, 8544)
    action = classify_bar_for_cleaning(bad_0900)
    assert action == BarCleanAction.DELETE

    cleaned = clean_bar(bad_0900)
    assert cleaned is None


def test_classify_bar_normal_keep():
    """Ca 4: Nến bình thường toàn bộ OHLC > 0 -> GIỮ NGUYÊN (KEEP)."""
    from trading.derivative_series import (
        BarCleanAction,
        classify_bar_for_cleaning,
        clean_bar,
    )

    normal_bar = _make_bar("41I1GA000", "2026-09-21 09:05:00", 1975.0, 1978.0, 1974.0, 1976.0, 3000)
    action = classify_bar_for_cleaning(normal_bar)
    assert action == BarCleanAction.KEEP

    cleaned = clean_bar(normal_bar)
    assert cleaned == normal_bar
