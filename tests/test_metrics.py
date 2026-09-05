"""Unit tests cho module trading/metrics.py (Tiêu chí 1 & 2 của Brief đợt 9)."""

import inspect
from datetime import date

import pytest

from trading.metrics import (
    expectancy,
    max_drawdown,
    portfolio_equity_curve,
    profit_factor,
    sharpe,
)


def test_profit_factor_basic_and_edge_cases():
    # 1. Tính tay: Gains = 100 + 50 = 150, Losses = |-60| = 60 -> PF = 150 / 60 = 2.5
    assert profit_factor([100.0, 50.0, -60.0]) == 2.5

    # 2. Không có lệnh thua -> Trả None (không trả inf)
    assert profit_factor([100.0, 50.0, 20.0]) is None

    # 3. Toàn bộ lệnh thua -> Gains = 0 -> PF = 0.0
    assert profit_factor([-100.0, -50.0]) == 0.0

    # 4. Rỗng -> None
    assert profit_factor([]) is None


def test_expectancy_basic_and_edge_cases():
    # Tính tay: (100 + 50 - 60) / 3 = 90 / 3 = 30.0
    assert expectancy([100.0, 50.0, -60.0]) == pytest.approx(30.0)
    assert expectancy([]) == 0.0


def test_max_drawdown_calculation():
    # Chuỗi: 100 -> 120 (peak) -> 90 -> 110 -> 80 (trough sâu nhất từ peak 120)
    # Drawdown = (120 - 80) / 120 = 40 / 120 = 0.3333333333333333 (33.33%)
    curve = [100.0, 120.0, 90.0, 110.0, 80.0]
    assert max_drawdown(curve) == pytest.approx(40.0 / 120.0)

    # Chuỗi tăng liên tục -> Max drawdown = 0.0
    assert max_drawdown([100.0, 110.0, 120.0, 130.0]) == 0.0

    # Chuỗi rỗng -> 0.0
    assert max_drawdown([]) == 0.0


def test_sharpe_requires_periods_per_year_no_default():
    # Tiêu chí 2: periods_per_year là tham số bắt buộc, không có default
    sig = inspect.signature(sharpe)
    param = sig.parameters["periods_per_year"]
    assert param.default is inspect.Parameter.empty, "periods_per_year KHÔNG ĐƯỢC có giá trị mặc định"

    # Gọi thiếu tham số -> TypeError
    with pytest.raises(TypeError):
        sharpe([0.01, -0.005, 0.02, 0.01])  # type: ignore

    # Chuỗi tính tay: returns = [0.01, 0.02, 0.03], periods_per_year = 252
    # mean = 0.02, stdev = 0.01 -> Sharpe = (0.02 / 0.01) * sqrt(252) = 2.0 * 15.874507866387544 = 31.749015732775088
    ret = [0.01, 0.02, 0.03]
    s_val = sharpe(ret, periods_per_year=252.0)
    assert s_val is not None
    assert s_val == pytest.approx(2.0 * (252.0**0.5))

    # Chuỗi ít hơn 2 phần tử hoặc stdev = 0 -> None
    assert sharpe([0.01], periods_per_year=252.0) is None
    assert sharpe([0.01, 0.01, 0.01], periods_per_year=252.0) is None


def test_portfolio_equity_curve_aggregation():
    # 2 mã, mỗi mã vốn 1.000.000 -> Tổng vốn ban đầu = 2.000.000
    pnl_data = {
        "AAA": {
            date(2026, 1, 5): 10_000.0,
            date(2026, 1, 6): -5_000.0,
        },
        "BBB": {
            date(2026, 1, 5): 20_000.0,
            date(2026, 1, 7): 15_000.0,
        },
    }
    curve = portfolio_equity_curve(pnl_data, capital_per_symbol=1_000_000.0)
    # Ngày 1 (05/01): +10k + +20k = +30k -> Equity = 2.030.000
    # Ngày 2 (06/01): -5k -> Equity = 2.025.000
    # Ngày 3 (07/01): +15k -> Equity = 2.040.000
    assert curve == [2_030_000.0, 2_025_000.0, 2_040_000.0]
