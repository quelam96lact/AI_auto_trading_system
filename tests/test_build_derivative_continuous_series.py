"""Kiểm thử đơn vị cho scripts/build_derivative_continuous_series.py (Brief 83)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from scripts.build_derivative_continuous_series import (
    FRONT_MONTH_CONTRACTS,
    _ohlc_rows_to_bars,
    _parse_trading_date,
)
from trading.calendar_vn import TZ


@dataclass
class DummyOHLC:
    symbol: str
    trading_date: str
    open_price: str
    high_price: str
    low_price: str
    close_price: str
    volume: str


def test_parse_trading_date():
    dt1 = _parse_trading_date("2026/09/24 14:45:00")
    assert dt1 == datetime(2026, 9, 24, 14, 45, 0, tzinfo=TZ)

    dt2 = _parse_trading_date("2026/09/24")
    assert dt2 == datetime(2026, 9, 24, 0, 0, 0, tzinfo=TZ)


def test_ohlc_rows_to_bars():
    rows = [
        DummyOHLC("41I1GA000", "2026/09/24 09:05:00", "1950.0", "1955.0", "1948.0", "1952.0", "1200"),
        DummyOHLC("41I1GA000", "2026/09/24 09:00:00", "1945.0", "1952.0", "1944.0", "1950.0", "1500"),
    ]
    bars = _ohlc_rows_to_bars(rows)
    assert len(bars) == 2
    # Đã được sắp xếp tăng dần theo ts
    assert bars[0].ts < bars[1].ts
    assert bars[0].open == 1945.0
    assert bars[0].volume == 1500
    assert bars[1].close == 1952.0


def test_front_month_contracts_ordering():
    # Danh sách hợp đồng front-month phải được sắp xếp tăng dần theo last_trading_date
    dates = [c.last_trading_date for c in FRONT_MONTH_CONTRACTS]
    assert dates == sorted(dates)
    assert len(FRONT_MONTH_CONTRACTS) >= 7
    # Hợp đồng đầu tiên là G4 (tháng 4) và kết thúc là GA (tháng 10)
    assert FRONT_MONTH_CONTRACTS[0].symbol == "41I1G4000"
    assert FRONT_MONTH_CONTRACTS[-1].symbol == "41I1GA000"
