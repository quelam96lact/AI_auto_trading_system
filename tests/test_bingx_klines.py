"""Unit tests cho scripts/bingx_klines.py (Brief đợt 12).

Tất định, không gọi mạng thật, không chạm DB.
4 tests bắt buộc:
1. test_phan_trang_ghep_du_khong_trung: hai trang liền nhau ghép lại đúng số nến, không lặp.
2. test_dung_khi_khong_tien_len: trang trả về nến cuối không mới hơn lần trước => dừng, không lặp vô hạn.
3. test_parse_nen_dung_thu_tu_truong: mảng [openTime, o, h, l, c, vol, closeTime, ...] ánh xạ đúng, close != closeTime.
4. test_loi_tan_suat_thi_lui_dan_va_khong_ne: gặp 100410 => exponential backoff có trần 600s, không ném exception ra ngoài.
"""

import json
from datetime import UTC, datetime

import pytest

from scripts.bingx_klines import (
    collect_symbol_klines,
    fetch_klines_http,
    parse_kline,
)


def test_phan_trang_ghep_du_khong_trung():
    """1. test_phan_trang_ghep_du_khong_trung:
    Hai trang liền nhau ghép lại đúng số nến, không nến nào bị lặp.
    Giả lập trang 1: nến 501..1000 (mới nhất), trang 2: nến 1..500.
    """
    # Tạo 900 nến mẫu: trang 1 = 500 nến, trang 2 = 400 nến (< limit 500 -> dừng tự nhiên)
    base_ms = 1600000000000
    day_ms = 86400000
    all_sample_bars = [
        {
            "time": base_ms + i * day_ms,
            "open": "100.0",
            "high": "110.0",
            "low": "90.0",
            "close": "105.0",
            "volume": "1000.0",
        }
        for i in range(900)
    ]

    # Trang 1: 500 nến mới nhất (index 400..899, xếp mới trước cũ sau theo quy ước BingX)
    page1 = list(reversed(all_sample_bars[400:900]))
    # Trang 2: 400 nến cũ hơn (index 0..399)
    page2 = list(reversed(all_sample_bars[0:400]))

    def mock_fetch(symbol: str, interval: str, end_time_ms: int | None = None, limit: int = 1000):
        if end_time_ms is None:
            return page1
        elif end_time_ms <= page1[-1]["time"]:
            return page2
        return []

    sleep_calls = []
    collected_bars, calls = collect_symbol_klines(
        "BTC-USDT",
        "1d",
        limit=500,
        fetch_fn=mock_fetch,
        sleep_fn=lambda s: sleep_calls.append(s),
        rate_limit_sleep=0,
    )

    assert calls == 2
    assert len(collected_bars) == 900
    # Đảm bảo không trùng timestamps
    unique_ts = {b["open_time_ms"] for b in collected_bars}
    assert len(unique_ts) == 900
    # Đảm bảo xếp tăng dần thời gian
    for i in range(len(collected_bars) - 1):
        assert collected_bars[i]["open_time_ms"] < collected_bars[i + 1]["open_time_ms"]


def test_dung_khi_khong_tien_len():
    """2. test_dung_khi_khong_tien_len:
    Trang trả về nến cuối KHÔNG mới hơn lần trước => dừng, không lặp vô hạn.
    """
    stuck_bar = {
        "time": 1620000000000,
        "open": "100.0",
        "high": "110.0",
        "low": "90.0",
        "close": "105.0",
        "volume": "500.0",
    }

    call_count = 0

    def mock_stuck_fetch(symbol: str, interval: str, end_time_ms: int | None = None, limit: int = 1000):
        nonlocal call_count
        call_count += 1
        if call_count > 10:
            return []
        # Luôn trả về 1000 nến với cùng min_time, không bao giờ tiến lên
        return [stuck_bar] * 1000

    collected_bars, calls = collect_symbol_klines(
        "BTC-USDT",
        "1d",
        fetch_fn=mock_stuck_fetch,
        sleep_fn=lambda s: None,
        rate_limit_sleep=0,
    )

    # Phải dừng ở lần gọi thứ 2 khi phát hiện min_time không tiến lên
    assert calls == 2
    assert len(collected_bars) == 1


def test_parse_nen_dung_thu_tu_truong():
    """3. test_parse_nen_dung_thu_tu_truong:
    Mảng [openTime, o, h, l, c, volume, closeTime, quoteVolume, trades] ánh xạ đúng;
    đặc biệt không lẫn close với closeTime.
    """
    open_time = 1577836800000  # 2020-01-01 00:00:00 UTC
    close_time = 1577923199000  # 2020-01-01 23:59:59 UTC

    raw_array = [
        open_time,
        "100.5",  # open
        "115.0",  # high
        "95.2",  # low
        "108.7",  # close
        "5000.0",  # volume
        close_time,
        "540000.0",  # quoteVolume
        150,  # trades
    ]

    parsed = parse_kline(raw_array, "BTC-USDT", "1d")

    assert parsed["symbol"] == "BTC-USDT"
    assert parsed["interval"] == "1d"
    assert parsed["open_time_ms"] == open_time
    assert parsed["close_time_ms"] == close_time
    assert parsed["ts"] == datetime(2020, 1, 1, 0, 0, tzinfo=UTC)

    # Kiểm tra giá
    assert pytest.approx(parsed["open"], rel=1e-6) == 100.5
    assert pytest.approx(parsed["high"], rel=1e-6) == 115.0
    assert pytest.approx(parsed["low"], rel=1e-6) == 95.2
    assert pytest.approx(parsed["close"], rel=1e-6) == 108.7

    # ĐẶC BIỆT: close không bao giờ bằng close_time
    assert parsed["close"] != float(close_time)

    # Khối lượng và trades
    assert pytest.approx(parsed["volume"], rel=1e-6) == 5000.0
    assert pytest.approx(parsed["quote_volume"], rel=1e-6) == 540000.0
    assert parsed["trades"] == 150


def test_loi_tan_suat_thi_lui_dan_va_khong_ne(monkeypatch):
    """4. test_loi_tan_suat_thi_lui_dan_va_khong_ne:
    Gặp mã lỗi 100410 (hoặc HTTP 429) => lùi theo cấp số nhân, có trần 600s,
    và không ném exception ra ngoài.
    """
    sleeps = []

    def mock_sleep(d: float):
        sleeps.append(d)

    attempts = 0

    class MockResponse:
        def __init__(self, status_code: int, data: dict):
            self.status_code = status_code
            self._data = data
            self.text = json.dumps(data)

        def json(self):
            return self._data

    class MockSession:
        def get(self, url, params=None, timeout=15):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                # Lần 1: Lỗi 100410 (code trong body)
                return MockResponse(200, {"code": 100410, "msg": "Request too frequent"})
            elif attempts == 2:
                # Lần 2: HTTP 429
                return MockResponse(429, {"code": 429, "msg": "Too Many Requests"})
            else:
                # Lần 3: Thành công
                return MockResponse(200, {
                    "code": 0,
                    "data": [{"time": 1600000000000, "open": "100", "high": "100", "low": "100", "close": "100", "volume": "10"}],
                })

    mock_sess = MockSession()
    res = fetch_klines_http("BTC-USDT", "1d", session=mock_sess, sleep_fn=mock_sleep)

    assert len(res) == 1
    assert attempts == 3
    # Kiểm tra backoff cấp số nhân: lần 1 = 2.0s, lần 2 = 4.0s
    assert len(sleeps) == 2
    assert sleeps[0] == 2.0
    assert sleeps[1] == 4.0
    # Không vượt trần 600s
    for s in sleeps:
        assert s <= 600.0
