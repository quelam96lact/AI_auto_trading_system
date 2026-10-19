"""Kiểm thử đơn vị và tích hợp cho resample dữ liệu phái sinh đa khung thời gian."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from scripts.resample_derivative_bars import INTERVAL_MINUTES_MAP, resample_symbol_bars
from trading.calendar_vn import TZ
from trading.models import Bar


def make_dummy_5m_bars(n: int = 12) -> list[Bar]:
    """Tạo chuỗi nến 5m mẫu bắt đầu từ 09:00 giờ VN."""
    base = datetime(2026, 10, 16, 9, 0, 0, tzinfo=TZ)
    bars = []
    for i in range(n):
        ts = base + timedelta(minutes=5 * i)
        bars.append(
            Bar(
                symbol="VN30F1M_CONT",
                ts=ts,
                open=1850.0 + i,
                high=1855.0 + i,
                low=1848.0 + i,
                close=1852.0 + i,
                volume=1000 + i * 100,
                source="ssi",
            )
        )
    return bars


def test_interval_minutes_map():
    assert INTERVAL_MINUTES_MAP["15m"] == 15
    assert INTERVAL_MINUTES_MAP["1h"] == 60
    assert INTERVAL_MINUTES_MAP["4h"] == 240


def test_resample_symbol_bars_15m():
    bars_5m = make_dummy_5m_bars(6)  # 6 nến 5m = 30 phút -> 2 nến 15m
    b15 = resample_symbol_bars(bars_5m, "15m")
    assert len(b15) == 2
    # Nến 15m đầu tiên gộp từ bar 0, 1, 2
    assert b15[0].open == bars_5m[0].open
    assert b15[0].close == bars_5m[2].close
    assert b15[0].high == max(b.high for b in bars_5m[:3])
    assert b15[0].low == min(b.low for b in bars_5m[:3])
    assert b15[0].volume == sum(b.volume for b in bars_5m[:3])


def test_resample_symbol_bars_1h():
    bars_5m = make_dummy_5m_bars(12)  # 12 nến 5m = 60 phút -> 1 nến 1h
    b1h = resample_symbol_bars(bars_5m, "1h")
    assert len(b1h) == 1
    assert b1h[0].open == bars_5m[0].open
    assert b1h[0].close == bars_5m[-1].close
    assert b1h[0].high == max(b.high for b in bars_5m)
    assert b1h[0].low == min(b.low for b in bars_5m)
    assert b1h[0].volume == sum(b.volume for b in bars_5m)


def test_resample_symbol_bars_invalid_interval():
    bars_5m = make_dummy_5m_bars(2)
    with pytest.raises(ValueError, match="Khoảng thời gian không hợp lệ"):
        resample_symbol_bars(bars_5m, "99m")


@pytest.mark.integration
@pytest.mark.integration
def test_storage_derivative_tf_write_read():
    from tests.conftest import TEST_DSN
    from trading.storage.db import Storage

    storage = Storage(TEST_DSN)
    storage.init_schema()

    bars_5m = make_dummy_5m_bars(6)
    bars_15m = resample_symbol_bars(bars_5m, "15m")

    # Ghi vào DB
    storage.write_derivative_tf_bars(bars_15m, "15m")

    # Đọc lại bằng read_derivative_tf_bars
    read_bars = storage.read_derivative_tf_bars("VN30F1M_CONT", "15m")
    assert len(read_bars) >= 2

    # Đọc lại bằng read_derivative_bars với tham số interval
    t_start = datetime(2026, 10, 16, 0, 0, 0, tzinfo=TZ)
    t_end = datetime(2026, 10, 17, 0, 0, 0, tzinfo=TZ)
    read_via_wrapper = storage.read_derivative_bars(
        "VN30F1M_CONT", t_start, t_end, interval="15m"
    )
    assert len(read_via_wrapper) >= 2
    assert read_via_wrapper[0].open == bars_15m[0].open
