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

from datetime import UTC, date, datetime, time
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.measure_derivative_contract_volume import ContractInfo
from scripts.record_vn30f_orderbook import (
    EarlyStopError,
    _parse_until_time,
    check_quote_rate_alarm,
    classify_message,
    compute_continuous_session_minutes,
    compute_market_silence_seconds,
    compute_reconnect_backoff,
    compute_total_downtime_seconds,
    detect_silence_gaps,
    get_orderbook_filepath,
    record_orderbook_stream,
    resolve_front_month_symbol,
    should_alert_early_stop,
    should_reconnect,
)
from trading.calendar_vn import TZ, is_trading_day


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


# =====================================================================
# C1: Test cho nhánh tự kết nối lại (pure functions)
# =====================================================================


def test_c1_case_1_should_not_reconnect_when_connected():
    """C1 Ca 1: Kết nối đang sống -> KHÔNG kết nối lại."""
    assert (
        should_reconnect(
            is_connected=True,
            current_time=time(10, 0),
            until_time=time(14, 46),
        )
        is False
    )


def test_c1_case_2_should_reconnect_when_disconnected_before_until():
    """C1 Ca 2: Kết nối đã đóng, chưa tới --until -> KẾT NỐI LẠI."""
    assert (
        should_reconnect(
            is_connected=False,
            current_time=time(10, 0),
            until_time=time(14, 46),
        )
        is True
    )


def test_c1_case_3_should_not_reconnect_after_until():
    """C1 Ca 3: Kết nối đã đóng, đã quá --until -> KHÔNG kết nối lại, dừng sạch."""
    # Đã quá mốc 14:46 (14:47)
    assert (
        should_reconnect(
            is_connected=False,
            current_time=time(14, 47),
            until_time=time(14, 46),
        )
        is False
    )
    # Đúng mốc 14:46:00
    assert (
        should_reconnect(
            is_connected=False,
            current_time=time(14, 46),
            until_time=time(14, 46),
        )
        is False
    )


def test_c1_case_4_retry_limit_and_exponential_backoff():
    """C1 Ca 4: Giới hạn số lần thử và khoảng nghỉ tăng dần, không quay tít."""
    # Đã vượt quá số lần thử tối đa (10 lần)
    assert (
        should_reconnect(
            is_connected=False,
            current_time=time(10, 0),
            until_time=time(14, 46),
            consecutive_failures=10,
            max_retries=10,
        )
        is False
    )
    # Chưa vượt quá
    assert (
        should_reconnect(
            is_connected=False,
            current_time=time(10, 0),
            until_time=time(14, 46),
            consecutive_failures=9,
            max_retries=10,
        )
        is True
    )

    # Khoảng nghỉ tăng dần
    b1 = compute_reconnect_backoff(1)
    b2 = compute_reconnect_backoff(2)
    b3 = compute_reconnect_backoff(3)
    b4 = compute_reconnect_backoff(4)
    assert 0 < b1 < b2 < b3 < b4
    # Cap tại max_delay = 60s
    assert compute_reconnect_backoff(10) <= 60.0
    assert compute_reconnect_backoff(20) == 60.0


# =====================================================================
# C2: Tách khoảng lặng thị trường khỏi thời gian máy ghi chết
# =====================================================================


def test_c2_decouple_recorder_downtime_from_market_silence():
    """C2: Dựng chuỗi có quãng mất kết nối 600s và khoảng lặng thật 15s.

    Phải báo đúng hai con số riêng biệt:
    - Thời gian máy ghi mất kết nối: 600s
    - Khoảng lặng thị trường dài nhất: 15s (KHÔNG được là 600s hay 607s).
    """
    m0 = datetime(2026, 9, 25, 10, 0, 0, tzinfo=TZ)
    m1 = datetime(2026, 9, 25, 10, 0, 15, tzinfo=TZ)  # Market gap = 15s

    # Mất kết nối từ 10:00:20 đến 10:10:20 (600 giây downtime)
    d_start = datetime(2026, 9, 25, 10, 0, 20, tzinfo=TZ)
    d_end = datetime(2026, 9, 25, 10, 10, 20, tzinfo=TZ)
    disconnects = [(d_start, d_end)]

    # Tin m2 đến sau khi nối lại 2s (10:10:22)
    m2 = datetime(2026, 9, 25, 10, 10, 22, tzinfo=TZ)

    timestamps = [m0, m1, m2]

    # 1. Thống kê downtime máy ghi riêng biệt
    total_downtime, detailed = compute_total_downtime_seconds(disconnects)
    assert total_downtime == pytest.approx(600.0)
    assert len(detailed) == 1
    assert detailed[0][2] == pytest.approx(600.0)

    # 2. Thống kê khoảng lặng thị trường riêng biệt (đã trừ downtime)
    max_gap, long_gaps, total_considered = detect_silence_gaps(
        timestamps, min_gap_seconds=10.0, disconnect_intervals=disconnects
    )

    assert total_considered == 3
    # Khoảng lặng thị trường lớn nhất là 15.0s (giữa m0 và m1), KHÔNG phải 600s hay 607s!
    assert max_gap == pytest.approx(15.0)
    assert max_gap != pytest.approx(600.0)
    assert max_gap != pytest.approx(607.0)

    # Đúng 1 khoảng lặng thị trường > 10.0s (m0 -> m1)
    assert len(long_gaps) == 1
    assert long_gaps[0][0] == m0
    assert long_gaps[0][1] == m1
    assert long_gaps[0][2] == pytest.approx(15.0)


# =====================================================================
# C3: Lên lịch ghi hằng ngày & chọn hợp đồng front-month động
# =====================================================================


async def test_c3_resolve_front_month_symbol_october_and_november():
    """C3: Chọn hợp đồng VN30F còn sống có lastTradingDate gần nhất trong tương lai.

    - 14/10 -> chọn 41I1GA000 (đáo hạn 15/10/2026).
    - 16/10 -> chọn 41I1GB000 (41I1GA000 đã hết hạn, hợp đồng kế tiếp đáo hạn 19/11/2026).
    """
    assert await resolve_front_month_symbol(date(2026, 10, 14)) == "41I1GA000"
    assert await resolve_front_month_symbol(date(2026, 10, 16)) == "41I1GB000"
    assert await resolve_front_month_symbol(date(2026, 9, 25)) == "41I1GA000"


# =====================================================================
# Brief 91 Task 1: Một nguồn sự thật cho ngày đáo hạn (SSI + Fallback)
# =====================================================================


async def test_task1_ssi_success_selects_front_month_no_warn():
    """Ca 1: Lấy thành công từ SSI -> chọn đúng mã theo SSI, KHÔNG phát WARN."""
    contracts = [
        ContractInfo(
            symbol="41I1GA000",
            name="VN30F 10/2026",
            board="DERIVATIVES",
            first_trading_date="",
            last_trading_date="2026/10/15",
        ),
        ContractInfo(
            symbol="41I1GB000",
            name="VN30F 11/2026",
            board="DERIVATIVES",
            first_trading_date="",
            last_trading_date="2026/11/19",
        ),
    ]
    with patch("scripts.record_vn30f_orderbook.alert") as mock_alert:
        symbol = await resolve_front_month_symbol(
            as_of=date(2026, 10, 14),
            ssi_fetcher=lambda: contracts,
        )
        assert symbol == "41I1GA000"
        mock_alert.assert_not_called()


async def test_task1_ssi_error_falls_back_to_formula_with_warn():
    """Ca 2: Gọi SSI thất bại -> rơi về công thức tự tính, chọn đúng mã, CÓ ĐÚNG 1 WARN."""
    def _failing_fetcher():
        raise ConnectionResetError("SSI connection reset by peer")

    with patch("scripts.record_vn30f_orderbook.alert") as mock_alert:
        symbol = await resolve_front_month_symbol(
            as_of=date(2026, 10, 14),
            ssi_fetcher=_failing_fetcher,
        )
        assert symbol == "41I1GA000"
        mock_alert.assert_called_once()
        args, kwargs = mock_alert.call_args
        assert args[0] == "WARN"
        assert "41I1GA000" in args[1]
        assert "SSI connection reset by peer" in str(kwargs.get("ssi_error", ""))


async def test_task1_ca_phan_biet_hai_nguon_holiday_shift_prefers_ssi():
    """Ca 3 (BẮT BUỘC): Phân biệt 2 nguồn khi thứ Năm thứ 3 trùng ngày lễ.

    - Ngày xét: 14/10/2026.
    - Công thức tự tính (get_third_thursday): tính thứ Năm thứ ba của tháng 10/2026 là 15/10/2026.
      Do 14/10 <= 15/10, công thức coi 41I1GA000 còn sống -> chọn 41I1GA000.
    - Thực tế HNX (phản ánh qua SSI): do 15/10 nghỉ lễ, HNX đẩy ngày đáo hạn sớm lên 13/10/2026.
      Tại ngày 14/10, hợp đồng 41I1GA000 đã hết hạn (13/10 < 14/10). Hợp đồng còn sống gần nhất là 41I1GB000 (19/11/2026).
    -> Máy ghi PHẢI chọn 41I1GB000 (theo SSI), KHÔNG ĐƯỢC chọn 41I1GA000 (theo công thức).
    -> KHÔNG phát WARN vì SSI trả về thành công.
    """
    ssi_contracts = [
        # Hợp đồng tháng 10 bị đẩy đáo hạn về 13/10 do ngày lễ
        ContractInfo(
            symbol="41I1GA000",
            name="VN30F 10/2026",
            board="DERIVATIVES",
            first_trading_date="",
            last_trading_date="2026/10/13",
        ),
        # Hợp đồng tháng 11 đáo hạn 19/11
        ContractInfo(
            symbol="41I1GB000",
            name="VN30F 11/2026",
            board="DERIVATIVES",
            first_trading_date="",
            last_trading_date="2026/11/19",
        ),
    ]

    with patch("scripts.record_vn30f_orderbook.alert") as mock_alert:
        chosen = await resolve_front_month_symbol(
            as_of=date(2026, 10, 14),
            ssi_fetcher=lambda: ssi_contracts,
        )
        assert chosen == "41I1GB000", "Phải chọn hợp đồng theo ngày đáo hạn thực tế của SSI!"
        assert chosen != "41I1GA000", "Không được chọn theo công thức tự tính chưa trừ ngày lễ!"
        mock_alert.assert_not_called()


async def test_task1_both_sources_fail_raises_runtime_error():
    """Ca 4: Cả SSI và công thức tự tính đều thất bại -> ném RuntimeError, không tạo file."""
    def _failing_fetcher():
        raise RuntimeError("SSI down")

    def _failing_generator(d: date) -> list[ContractInfo]:
        return []

    with pytest.raises(RuntimeError) as exc_info:
        await resolve_front_month_symbol(
            as_of=date(2026, 10, 14),
            ssi_fetcher=_failing_fetcher,
            fallback_generator=_failing_generator,
        )

    assert "Cả hai nguồn" in str(exc_info.value)


# =====================================================================
# Brief 91 Task 2: Chuông cho ca ghi sai mã (Quote Rate Alarm)
# =====================================================================


def test_task2_quote_rate_alarm_normal():
    """Task 2 Ca 1: Phiên bình thường sau 10 phút (>= 1,000 QUOTE) -> Không báo động."""
    # Front-month bình thường nhận ~17,000 QUOTE / 10 phút
    assert check_quote_rate_alarm(quote_count=17000, elapsed_minutes=10.0) is False
    # Ngay tại ngưỡng 1,000 QUOTE
    assert check_quote_rate_alarm(quote_count=1000, elapsed_minutes=10.0) is False
    # Phiên chạy lâu hơn 10 phút và đạt lưu lượng
    assert check_quote_rate_alarm(quote_count=5000, elapsed_minutes=15.0) is False


def test_task2_quote_rate_alarm_low_triggers():
    """Task 2 Ca 2: Lưu lượng thấp bất thường sau 10 phút (< 1,000 QUOTE) -> BÁO ĐỘNG."""
    # Hợp đồng không phải front-month chỉ nhận ~35 QUOTE / 10 phút (0.2% volume)
    assert check_quote_rate_alarm(quote_count=35, elapsed_minutes=10.0) is True
    # Dưới ngưỡng: 999 tin
    assert check_quote_rate_alarm(quote_count=999, elapsed_minutes=10.0) is True
    # Hoàn toàn không nhận được tin nào
    assert check_quote_rate_alarm(quote_count=0, elapsed_minutes=10.0) is True
    assert check_quote_rate_alarm(quote_count=500, elapsed_minutes=12.0) is True


def test_task2_quote_rate_alarm_not_yet_ten_minutes():
    """Task 2 Ca 3: Chưa đủ 10 phút -> KHÔNG báo động (chưa đủ dữ liệu để kết luận)."""
    assert check_quote_rate_alarm(quote_count=0, elapsed_minutes=0.0) is False
    assert check_quote_rate_alarm(quote_count=50, elapsed_minutes=5.0) is False
    assert check_quote_rate_alarm(quote_count=500, elapsed_minutes=9.9) is False
    assert check_quote_rate_alarm(quote_count=0, elapsed_minutes=9.99) is False


def test_task2_compute_continuous_session_minutes():
    """Task 2: Tính số phút giao dịch liên tục (09:00-11:30 và 13:00-14:45)."""
    # 1. Trước giờ mở cửa (08:50) -> 0 phút
    t_pre = datetime(2026, 9, 28, 8, 50, tzinfo=TZ)
    assert compute_continuous_session_minutes(t_pre) == 0.0

    # 2. Sau 10 phút mở phiên sáng (09:10) -> 10.0 phút
    t_10m = datetime(2026, 9, 28, 9, 10, tzinfo=TZ)
    assert compute_continuous_session_minutes(t_10m) == pytest.approx(10.0)

    # 3. Hết phiên sáng (11:30) -> 150.0 phút
    t_m_end = datetime(2026, 9, 28, 11, 30, tzinfo=TZ)
    assert compute_continuous_session_minutes(t_m_end) == pytest.approx(150.0)

    # 4. Giữa giờ nghỉ trưa (12:15) -> vẫn là 150.0 phút (không tính nghỉ trưa)
    t_lunch = datetime(2026, 9, 28, 12, 15, tzinfo=TZ)
    assert compute_continuous_session_minutes(t_lunch) == pytest.approx(150.0)

    # 5. Đầu phiên chiều (13:10) -> 150 + 10 = 160.0 phút
    t_afternoon = datetime(2026, 9, 28, 13, 10, tzinfo=TZ)
    assert compute_continuous_session_minutes(t_afternoon) == pytest.approx(160.0)

    # 6. Với since_dt: chạy từ 10:00 đến 10:10 -> 10.0 phút
    t_start = datetime(2026, 9, 28, 10, 0, tzinfo=TZ)
    t_end = datetime(2026, 9, 28, 10, 10, tzinfo=TZ)
    assert compute_continuous_session_minutes(t_end, since_dt=t_start) == pytest.approx(10.0)


def test_c3_calendar_trading_day_skips_weekends_and_holidays():
    """C3: Tái sử dụng is_trading_day từ calendar_vn, không chạy cuối tuần và ngày lễ."""
    assert is_trading_day(date(2026, 9, 26)) is False  # Thứ Bảy
    assert is_trading_day(date(2026, 9, 27)) is False  # Chủ Nhật
    assert is_trading_day(date(2026, 9, 28)) is True   # Thứ Hai (ngày GD tiếp theo)
    # Ngày lễ
    holidays = {date(2026, 9, 2)}
    assert is_trading_day(date(2026, 9, 2), holidays=holidays) is False


# =====================================================================
# Brief 94 Task 1: Máy ghi phải kêu khi nó chết
# =====================================================================


def test_task1_should_alert_early_stop_on_time():
    """Nhóm 1: Dừng đúng --until (14:46) -> KHÔNG báo."""
    assert (
        should_alert_early_stop(
            actual_stop_time=time(14, 46, 0),
            until_time=time(14, 46, 0),
            is_trading_day=True,
        )
        is False
    )


def test_task1_should_alert_early_stop_three_hours_early():
    """Nhóm 2: Dừng trước --until 3 giờ, là ngày giao dịch -> BÁO CRITICAL."""
    # Dừng lúc 11:46 trong khi đến 14:46 mới hết phiên
    assert (
        should_alert_early_stop(
            actual_stop_time=time(11, 46, 0),
            until_time=time(14, 46, 0),
            is_trading_day=True,
        )
        is True
    )
    # Thử với kiểu datetime
    dt_early = datetime(2026, 9, 28, 11, 46, 0, tzinfo=TZ)
    assert (
        should_alert_early_stop(
            actual_stop_time=dt_early,
            until_time=time(14, 46, 0),
            is_trading_day=True,
        )
        is True
    )


def test_task1_should_alert_early_stop_non_trading_day():
    """Nhóm 3: Không phải ngày giao dịch -> KHÔNG báo, dù dừng "sớm"."""
    # Chủ nhật hay thứ Bảy chạy kiểm tra, dừng lúc 11:46 -> không báo
    assert (
        should_alert_early_stop(
            actual_stop_time=time(11, 46, 0),
            until_time=time(14, 46, 0),
            is_trading_day=False,
        )
        is False
    )


def test_task1_should_alert_early_stop_after_until():
    """Nhóm 4 (Ca biên): Dừng sau --until vài giây (làm tròn/cleanup) -> KHÔNG báo."""
    assert (
        should_alert_early_stop(
            actual_stop_time=time(14, 46, 5),
            until_time=time(14, 46, 0),
            is_trading_day=True,
        )
        is False
    )
    assert (
        should_alert_early_stop(
            actual_stop_time=time(14, 47, 0),
            until_time=time(14, 46, 0),
            is_trading_day=True,
        )
        is False
    )


async def test_task1_unhandled_exception_emits_critical_alert_with_counts(tmp_path: Path):
    """Nhóm 5: Lỗi chưa xử lý -> có đúng 1 alert CRITICAL, và nêu đúng số tin đã ghi."""
    # Tạo file dữ liệu có sẵn 3 tin đã ghi trước đó
    symbol = "41I1GA000"
    today_str = datetime.now(TZ).strftime("%Y-%m-%d")
    file_path = tmp_path / symbol / f"{today_str}.jsonl.gz"
    file_path.parent.mkdir(parents=True, exist_ok=True)

    import gzip
    import json

    with gzip.open(file_path, "wt", encoding="utf-8") as gf:
        gf.write(json.dumps({"type": "QUOTE", "symbol": symbol, "recv_ts": f"{today_str}T09:00:01+07:00"}) + "\n")
        gf.write(json.dumps({"type": "QUOTE", "symbol": symbol, "recv_ts": f"{today_str}T09:00:02+07:00"}) + "\n")
        gf.write(json.dumps({"type": "TRADE", "symbol": symbol, "price": 1950.0, "recv_ts": f"{today_str}T09:00:03+07:00"}) + "\n")

    real_gzip_open = gzip.open

    def mock_gzip_open(filename, mode="rb", **kwargs):
        if mode == "at":
            raise OSError("Không còn dung lượng ổ đĩa (Disk full)")
        return real_gzip_open(filename, mode=mode, **kwargs)

    with (
        patch("scripts.record_vn30f_orderbook.is_trading_day", return_value=True),
        patch("scripts.record_vn30f_orderbook.Storage") as mock_storage,
        patch("scripts.record_vn30f_orderbook.gzip.open", side_effect=mock_gzip_open),
        patch("scripts.record_vn30f_orderbook.alert") as mock_alert,
    ):
        mock_storage.return_value = None

        with pytest.raises(OSError) as exc_info:
            await record_orderbook_stream(
                symbol=symbol,
                until_time=time(14, 46),
                data_dir=tmp_path,
            )

        assert "Không còn dung lượng ổ đĩa" in str(exc_info.value)

        # Kiểm tra đúng 1 alert CRITICAL
        assert mock_alert.call_count == 1
        call_args, call_kwargs = mock_alert.call_args
        assert call_args[0] == "CRITICAL"
        msg = call_args[1]

        # Kiểm tra nội dung alert nêu loại lỗi, thông điệp, mã hợp đồng, và số tin
        assert "OSError" in msg
        assert "Không còn dung lượng ổ đĩa (Disk full)" in msg
        assert symbol in msg
        assert "3" in msg  # Tổng số tin đã ghi được nạp từ file

        # Kiểm tra kwargs chi tiết
        assert call_kwargs.get("symbol") == symbol
        assert call_kwargs.get("error_type") == "OSError"
        assert call_kwargs.get("total_recorded") == 3
        counts = call_kwargs.get("recorded_counts")
        assert counts == {"QUOTE": 2, "TRADE": 1, "OTHER": 0}


async def test_task1_early_stop_in_stream_emits_critical_alert(tmp_path: Path):
    """Tiến trình kết thúc trước --until trên ngày giao dịch -> alert CRITICAL và raise EarlyStopError."""
    symbol = "41I1GA000"

    with (
        patch("scripts.record_vn30f_orderbook.is_trading_day", return_value=True),
        patch("scripts.record_vn30f_orderbook.Storage") as mock_storage,
        patch("scripts.record_vn30f_orderbook.ensure_authenticated") as mock_auth,
        patch("scripts.record_vn30f_orderbook.should_reconnect", return_value=False),  # Giả lập vòng kết nối bỏ cuộc
        patch("scripts.record_vn30f_orderbook.alert") as mock_alert,
        patch("scripts.record_vn30f_orderbook.should_alert_early_stop", return_value=True),  # Giả lập xác nhận dừng sớm
    ):
        mock_storage.return_value = None
        mock_auth.return_value = None

        with pytest.raises(EarlyStopError) as exc_info:
            await record_orderbook_stream(
                symbol=symbol,
                until_time=time(14, 46),
                data_dir=tmp_path,
            )

        assert "dừng sớm ngoài ý muốn" in str(exc_info.value)
        assert mock_alert.call_count == 1
        call_args, call_kwargs = mock_alert.call_args
        assert call_args[0] == "CRITICAL"
        assert symbol in call_args[1]
        assert call_kwargs.get("symbol") == symbol

def test_task1_early_stop_tolerance_60s_no_false_alarm():
    """Dung sai 60 giay: som duoi 60s la BINH THUONG, som nhieu van phai BAO.

    Vong lap may ghi co the thoat ngay truoc moc --until vai phan giay (lam tron
    giay, do tre stream.wait()). Khong co dung sai thi mot phien hoan toan binh
    thuong se bi bao CRITICAL oan ngay lan chay tu dong dau tien.
    """
    until = time(14, 46, 0)
    # Som 1 giay va som 59 giay -> KHONG bao (trong dung sai)
    assert not should_alert_early_stop(
        time(14, 45, 59), until, is_trading_day=True, tolerance_seconds=60.0
    )
    assert not should_alert_early_stop(
        time(14, 45, 1), until, is_trading_day=True, tolerance_seconds=60.0
    )
    # Som 61 giay -> VAN BAO
    assert should_alert_early_stop(
        time(14, 44, 59), until, is_trading_day=True, tolerance_seconds=60.0
    )
    # Ca hong that 25/09 (som ~4,75 gio) -> VAN BAO
    assert should_alert_early_stop(
        time(10, 0, 33), until, is_trading_day=True, tolerance_seconds=60.0
    )
