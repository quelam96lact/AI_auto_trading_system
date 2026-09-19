"""Unit test kiểm chứng logic chia ranh giới theo năm cho Buy-and-Hold theo nhịp (Brief 64).

Yêu cầu Task 2.1:
1. Dựng bars giả trải dài đúng 2 năm dương lịch liên tiếp (2023-2024), có phiên sát ranh giới 31/12 và 01/01.
2. Chạy hàm chia theo năm (get_year_ranges) cho 2 năm này và chạy benchmark.
3. Độc lập, gọi run_regime_hold_benchmark thủ công 2 lần với ranh giới [2023-01-01, 2023-12-31 23:59:59]
   và [2024-01-01, 2024-12-31 23:59:59].
4. Khẳng định kết quả hai cách giống hệt nhau ở mọi trường metrics: strat_pnl, bh_pnl, strat_mdd,
   bh_mdd, total_buy_trades, total_sell_trades.
"""

from datetime import date, datetime

import pytest

from scripts.measure_regime_hold import (
    TZ,
    get_year_ranges,
    run_regime_hold_benchmark,
)
from trading.models import Bar


class DummyStorage:
    """Mock storage cho phép lọc daily bars theo start <= ts < end."""

    def __init__(self, bars: list[Bar]):
        self._bars = bars

    def read_daily_bars(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[Bar]:
        return [
            b
            for b in self._bars
            if b.symbol == symbol and start <= b.ts < end
        ]


def _make_bar(d: date, open_p: float, close_p: float, symbol: str = "TEST") -> Bar:
    dt = datetime(d.year, d.month, d.day, 15, 0, 0, tzinfo=TZ)
    return Bar(
        symbol=symbol,
        ts=dt,
        open=open_p,
        high=max(open_p, close_p) * 1.01,
        low=min(open_p, close_p) * 0.99,
        close=close_p,
        volume=100_000.0,
    )


def test_ranh_gioi_chia_nam_chinh_xac_khong_lech_va_khong_ro_ri():
    """Kiểm chứng chia năm độc lập khớp 100% với gọi thủ công từng ranh giới năm."""
    # 1. Dựng bars giả trải dài 2 năm 2023 - 2024, có phiên sát ranh giới 31/12/2023 và 01/01/2024
    d_2023_1 = date(2023, 3, 15)
    d_2023_2 = date(2023, 8, 20)
    d_2023_edge = date(2023, 12, 31)  # Bar sát ranh giới cuối năm 2023

    d_2024_edge = date(2024, 1, 1)   # Bar sát ranh giới đầu năm 2024
    d_2024_1 = date(2024, 6, 10)
    d_2024_2 = date(2024, 12, 31)   # Bar cuối năm 2024

    bars = [
        _make_bar(d_2023_1, 10.0, 12.0),
        _make_bar(d_2023_2, 12.0, 11.0),
        _make_bar(d_2023_edge, 11.0, 15.0),
        _make_bar(d_2024_edge, 20.0, 22.0),
        _make_bar(d_2024_1, 22.0, 18.0),
        _make_bar(d_2024_2, 18.0, 25.0),
    ]

    prior_regime_by_date = {
        d_2023_1: "RISK_ON",
        d_2023_2: "RISK_OFF",
        d_2023_edge: "RISK_ON",
        d_2024_edge: "RISK_ON",
        d_2024_1: "RISK_OFF",
        d_2024_2: "RISK_ON",
    }

    storage = DummyStorage(bars)
    symbols = ["TEST"]
    capital = 1_000_000_000.0

    # 2. Chạy qua logic get_year_ranges cho 2 năm 2023-2024
    year_ranges = get_year_ranges(2023, 2024)
    assert len(year_ranges) == 2

    by_year_results = {}
    for y, y_frm, y_to in year_ranges:
        res = run_regime_hold_benchmark(
            storage, symbols, y_frm, y_to, prior_regime_by_date, capital
        )
        by_year_results[y] = res

    # 3. Chạy độc lập thủ công 2 lần với đúng ranh giới
    manual_2023_frm = datetime(2023, 1, 1, tzinfo=TZ)
    manual_2023_to = datetime(2023, 12, 31, 23, 59, 59, tzinfo=TZ)
    res_manual_2023 = run_regime_hold_benchmark(
        storage, symbols, manual_2023_frm, manual_2023_to, prior_regime_by_date, capital
    )

    manual_2024_frm = datetime(2024, 1, 1, tzinfo=TZ)
    manual_2024_to = datetime(2024, 12, 31, 23, 59, 59, tzinfo=TZ)
    res_manual_2024 = run_regime_hold_benchmark(
        storage, symbols, manual_2024_frm, manual_2024_to, prior_regime_by_date, capital
    )

    # 4. Khẳng định kết quả hai cách giống hệt nhau ở từng metrics
    metric_keys = [
        "strat_pnl",
        "bh_pnl",
        "strat_mdd",
        "bh_mdd",
        "total_buy_trades",
        "total_sell_trades",
    ]

    # Kiểm tra năm 2023
    for key in metric_keys:
        assert by_year_results[2023][key] == pytest.approx(res_manual_2023[key]), (
            f"Năm 2023 lệch ở metric {key}: {by_year_results[2023][key]} != {res_manual_2023[key]}"
        )

    # Kiểm tra năm 2024
    for key in metric_keys:
        assert by_year_results[2024][key] == pytest.approx(res_manual_2024[key]), (
            f"Năm 2024 lệch ở metric {key}: {by_year_results[2024][key]} != {res_manual_2024[key]}"
        )

    # Đảm bảo bar ngày 31/12/2023 thực sự được xử lý trong 2023
    bars_in_2023 = storage.read_daily_bars("TEST", year_ranges[0][1], year_ranges[0][2])
    assert len(bars_in_2023) == 3
    assert bars_in_2023[-1].ts.date() == date(2023, 12, 31)

    # Đảm bảo bar ngày 01/01/2024 thực sự được xử lý trong 2024
    bars_in_2024 = storage.read_daily_bars("TEST", year_ranges[1][1], year_ranges[1][2])
    assert len(bars_in_2024) == 3
    assert bars_in_2024[0].ts.date() == date(2024, 1, 1)
