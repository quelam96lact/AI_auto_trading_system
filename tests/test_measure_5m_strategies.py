"""Unit tests cho scripts/measure_5m_strategies.py (Gói Y).

Kiểm chứng:
1. test_summarize_results_empty: Xử lý danh sách kết quả rỗng an toàn.
2. test_summarize_results_calculations: Tính toán đúng tổng PnL, chênh lệch, trung vị và tỷ lệ thắng BH.
3. test_run_strategy_on_symbols_with_mock: Chạy backtest trên MockStorage kiểm tra warm-up và tổng hợp.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from measure_5m_strategies import run_strategy_on_symbols, summarize_results

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.strategies.sma_cross import SmaCrossStrategy


class MockStorage:
    def __init__(self, data: dict[str, list[Bar]]):
        self.data = data

    def read_bars(self, symbol: str, start: datetime, end: datetime) -> list[Bar]:
        return self.data.get(symbol, [])


def _make_bars(symbol: str, n: int, base_price: float = 10_000.0) -> list[Bar]:
    base_time = datetime(2026, 1, 1, 9, 0, tzinfo=TZ)
    bars = []
    price = base_price
    for i in range(n):
        price += 10.0
        bars.append(
            Bar(
                symbol=symbol,
                ts=base_time + timedelta(minutes=5 * i),
                open=price,
                high=price + 100,
                low=price - 100,
                close=price,
                volume=1_000,
            )
        )
    return bars


def test_summarize_results_empty():
    """Xử lý an toàn khi không có kết quả mã nào."""
    res = summarize_results([], "EmptyStrategy")
    assert res["name"] == "EmptyStrategy"
    assert res["n_symbols"] == 0
    assert res["strat_pnl"] == 0.0
    assert res["win_bh_count"] == 0


def test_summarize_results_calculations():
    """Kiểm tra logic tổng hợp chỉ số, chênh lệch và trung vị."""
    mock_items = [
        {"symbol": "A", "trades": 2, "strat_pnl": 10_000_000.0, "bh_pnl": 5_000_000.0, "diff": 5_000_000.0},
        {"symbol": "B", "trades": 0, "strat_pnl": 0.0, "bh_pnl": -2_000_000.0, "diff": 2_000_000.0},
        {"symbol": "C", "trades": 3, "strat_pnl": -5_000_000.0, "bh_pnl": 10_000_000.0, "diff": -15_000_000.0},
    ]
    res = summarize_results(mock_items, "TestStrat")
    assert res["n_symbols"] == 3
    assert res["traded_symbols"] == 2
    assert res["total_trades"] == 5
    assert res["strat_pnl"] == 5_000_000.0
    assert res["bh_pnl"] == 13_000_000.0
    assert res["diff"] == -8_000_000.0
    assert res["win_bh_count"] == 2  # A và B có diff > 0
    assert res["win_bh_pct"] == pytest.approx(66.6666, rel=1e-3)
    assert res["median_strat_pnl"] == 0.0
    assert res["median_bh_pnl"] == 5_000_000.0
    assert res["median_diff"] == 2_000_000.0


def test_run_strategy_on_symbols_with_mock():
    """Chạy quy trình backtest với MockStorage, lọc mã thiếu warmup_bars."""
    # SmaCrossStrategy có warmup_bars = 21
    mock_data = {
        "SHORT": _make_bars("SHORT", 10),  # < 21 bar -> bị bỏ qua
        "LONG": _make_bars("LONG", 50),    # 50 bar >= 21 -> được tính
    }
    storage = MockStorage(mock_data)

    summary = run_strategy_on_symbols(["SHORT", "LONG"], SmaCrossStrategy, storage, capital=10_000_000.0)
    assert summary["n_symbols"] == 1
    assert summary["results"][0]["symbol"] == "LONG"
