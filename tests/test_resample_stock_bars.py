"""Kiểm thử đơn vị và tích hợp cho resample dữ liệu nến cổ phiếu VN đa khung thời gian."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from scripts.resample_stock_bars import (
    INTERVAL_MINUTES_MAP,
    resample_stock_bars_series,
)
from tests.conftest import TEST_DSN
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.storage.db import Storage


def make_dummy_stock_5m_bars(n: int = 12, symbol: str = "TEST_STOCK") -> list[Bar]:
    """Tạo chuỗi nến 5m mẫu bắt đầu từ 09:15 giờ VN (chuẩn khớp lệnh liên tục HOSE)."""
    base = datetime(2026, 10, 16, 9, 15, 0, tzinfo=TZ)
    bars = []
    for i in range(n):
        ts = base + timedelta(minutes=5 * i)
        bars.append(
            Bar(
                symbol=symbol,
                ts=ts,
                open=50.0 + i * 0.5,
                high=51.0 + i * 0.5,
                low=49.5 + i * 0.5,
                close=50.5 + i * 0.5,
                volume=10000 + i * 500,
                source="ssi",
            )
        )
    return bars


def test_stock_interval_minutes_map():
    assert INTERVAL_MINUTES_MAP["15m"] == 15
    assert INTERVAL_MINUTES_MAP["1h"] == 60
    assert INTERVAL_MINUTES_MAP["4h"] == 240


def test_resample_stock_bars_15m():
    bars_5m = make_dummy_stock_5m_bars(6)  # 6 nến 5m = 30 phút -> 2 nến 15m
    b15 = resample_stock_bars_series(bars_5m, "15m")
    assert len(b15) == 2
    assert b15[0].open == bars_5m[0].open
    assert b15[0].close == bars_5m[2].close
    assert b15[0].high == max(b.high for b in bars_5m[:3])
    assert b15[0].low == min(b.low for b in bars_5m[:3])
    assert b15[0].volume == sum(b.volume for b in bars_5m[:3])


def test_resample_stock_bars_1h():
    bars_5m = make_dummy_stock_5m_bars(9)  # 9 nến từ 09:15 đến 09:55 -> cùng bucket 09:00
    b1h = resample_stock_bars_series(bars_5m, "1h")
    assert len(b1h) == 1
    assert b1h[0].open == bars_5m[0].open
    assert b1h[0].close == bars_5m[-1].close
    assert b1h[0].high == max(b.high for b in bars_5m)
    assert b1h[0].low == min(b.low for b in bars_5m)
    assert b1h[0].volume == sum(b.volume for b in bars_5m)


def test_resample_stock_bars_invalid_interval():
    bars_5m = make_dummy_stock_5m_bars(2)
    with pytest.raises(ValueError, match="Khoảng thời gian không hợp lệ"):
        resample_stock_bars_series(bars_5m, "45m")


@pytest.mark.integration
@pytest.mark.integration
def test_storage_stock_tf_write_read():
    storage = Storage(TEST_DSN)
    storage.init_schema()

    sym = "TEST_STOCK_TF"
    bars_5m = make_dummy_stock_5m_bars(6, symbol=sym)
    bars_15m = resample_stock_bars_series(bars_5m, "15m")

    # Ghi vào DB
    storage.write_stock_tf_bars(bars_15m, "15m")

    # Đọc lại bằng read_stock_tf_bars
    read_bars = storage.read_stock_tf_bars(sym, "15m")
    assert len(read_bars) >= 2

    # Đọc lại bằng read_bars với tham số interval="15m"
    t_start = datetime(2026, 10, 16, 0, 0, 0, tzinfo=TZ)
    t_end = datetime(2026, 10, 17, 0, 0, 0, tzinfo=TZ)
    read_via_wrapper = storage.read_bars(sym, t_start, t_end, interval="15m")
    assert len(read_via_wrapper) >= 2
    assert read_via_wrapper[0].open == bars_15m[0].open
    assert read_via_wrapper[0].volume == bars_15m[0].volume
