"""Unit tests cho chốt chặn 'Engine Câm' (Gói X).

Đặc tả:
1. Unit tests:
   - Phát hiện chính xác chiến lược bị nghẽn cổng thanh khoản (0 bar mở).
   - Kiểm tra khi thanh khoản đủ lớn thì cổng mở.
   - Chiến lược không có cổng thanh khoản (vd SmaCross) thì gate_open_bars = 100%.
   - Xử lý mảng bar rỗng (NO_DATA).
2. Kiểm thử luồng check_engine_symbols với MockStorage:
   - Tái hiện chính xác trạng thái câm của OctopusPullbackStrategy trên tập bar mô phỏng HII/IJC/AAA.
   - Đối chứng với SmaCrossStrategy (hoạt động bình thường, sinh tín hiệu 2 chiều).
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from check_silent_engine import analyze_symbol_bars, check_engine_symbols

from trading.calendar_vn import TZ
from trading.engine.main import _default_strategy
from trading.models import Bar
from trading.strategies.octopus_pullback import OctopusPullbackStrategy
from trading.strategies.sma_cross import SmaCrossStrategy


def _make_bars(
    symbol: str = "TEST",
    n: int = 50,
    price: float = 20_000.0,
    volume: int = 1_000,
) -> list[Bar]:
    base_time = datetime(2026, 1, 1, 9, 0, tzinfo=TZ)
    bars = []
    for i in range(n):
        bars.append(
            Bar(
                symbol=symbol,
                ts=base_time + timedelta(days=i),
                open=price,
                high=price + 100,
                low=price - 100,
                close=price,
                volume=volume,
            )
        )
    return bars


class MockStorage:
    def __init__(self, data: dict[str, list[Bar]]):
        self.data = data

    def read_bars(self, symbol: str, start: datetime, end: datetime) -> list[Bar]:
        return self.data.get(symbol, [])


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_silent_engine_detection_with_low_liquidity():
    """Khi giá trị bar (20tr) < ngưỡng thanh khoản 2 tỷ, cổng phải đóng 100%."""
    # 20.000 đ * 1.000 CP = 20.000.000 đ/bar << 2.000.000.000 đ
    bars = _make_bars(n=30, price=20_000.0, volume=1_000)
    strat = OctopusPullbackStrategy(min_avg_value_20=2_000_000_000.0)

    res = analyze_symbol_bars("TEST", bars, strat)

    assert res["is_silent"] is True
    assert res["status"] == "CRITICAL_SILENT"
    assert res["gate_open_bars"] == 0
    assert res["gate_open_pct"] == 0.0
    assert res["bull_signals"] == 0


def test_silent_engine_gate_opens_with_high_liquidity():
    """Khi giá trị bar (5 tỷ) >= ngưỡng thanh khoản 2 tỷ, cổng phải mở sau warmup cửa sổ."""
    # 100.000 đ * 50.000 CP = 5.000.000.000 đ/bar >= 2.000.000.000 đ
    bars = _make_bars(n=50, price=100_000.0, volume=50_000)
    strat = OctopusPullbackStrategy(min_avg_value_20=2_000_000_000.0)

    res = analyze_symbol_bars("TEST", bars, strat)

    assert res["gate_open_bars"] > 0
    assert res["gate_open_pct"] > 0.0


def test_strategy_without_liquidity_gate():
    """Chiến lược không có cổng thanh khoản (như SmaCross) thì không bị nghẽn cổng."""
    bars = _make_bars(n=30, price=20_000.0, volume=1_000)
    strat = SmaCrossStrategy()

    res = analyze_symbol_bars("TEST", bars, strat)

    assert res["has_liquidity_gate"] is False
    assert res["gate_open_bars"] == 30
    assert res["gate_open_pct"] == 100.0


def test_empty_bars_handling():
    """Chuỗi bar rỗng phải báo NO_DATA và is_silent=True."""
    strat = OctopusPullbackStrategy()
    res = analyze_symbol_bars("EMPTY", [], strat)

    assert res["is_silent"] is True
    assert res["status"] == "NO_DATA"
    assert res["total_bars"] == 0


def test_check_engine_symbols_reproduces_silent_state():
    """Tái hiện trạng thái câm của engine mặc định trên 3 mã cấu hình (giá trị bar < 2 tỷ)."""
    # HII (80tr/bar), AAA (150tr/bar), IJC (330tr/bar) đều << 2 tỷ/bar
    mock_data = {
        "HII": _make_bars("HII", n=100, price=10_000.0, volume=8_000),
        "AAA": _make_bars("AAA", n=100, price=15_000.0, volume=10_000),
        "IJC": _make_bars("IJC", n=100, price=20_000.0, volume=16_500),
    }
    storage = MockStorage(mock_data)

    results = check_engine_symbols(["HII", "IJC", "AAA"], _default_strategy, storage)
    res_map = {r["symbol"]: r for r in results}

    assert res_map["HII"]["is_silent"] is True
    assert res_map["HII"]["gate_open_bars"] == 0

    assert res_map["AAA"]["is_silent"] is True
    assert res_map["AAA"]["gate_open_bars"] == 0

    assert res_map["IJC"]["is_silent"] is True
    assert res_map["IJC"]["gate_open_bars"] == 0


def test_check_engine_symbols_with_sma_cross_is_active():
    """Đối chứng: SmaCrossStrategy chạy trên chuỗi bar có xu hướng sinh tín hiệu bình thường."""
    base_time = datetime(2026, 1, 1, 9, 0, tzinfo=TZ)
    bars = []
    price = 10_000.0

    # Pha 1: 25 bar đi ngang/giảm nhẹ để MA ổn định ở trạng thái dưới (fast <= slow)
    for i in range(25):
        price -= 50.0
        bars.append(
            Bar(
                symbol="HII",
                ts=base_time + timedelta(minutes=5 * len(bars)),
                open=price - 100,
                high=price + 200,
                low=price - 200,
                close=price,
                volume=10_000,
            )
        )

    # Pha 2: 25 bar tăng mạnh -> fast cắt lên slow -> phát "bull"
    for i in range(25):
        price += 300.0
        bars.append(
            Bar(
                symbol="HII",
                ts=base_time + timedelta(minutes=5 * len(bars)),
                open=price - 100,
                high=price + 200,
                low=price - 200,
                close=price,
                volume=10_000,
            )
        )

    # Pha 3: 20 bar giảm mạnh -> fast cắt xuống slow -> phát "bear"
    for i in range(20):
        price -= 500.0
        bars.append(
            Bar(
                symbol="HII",
                ts=base_time + timedelta(minutes=5 * len(bars)),
                open=price + 100,
                high=price + 200,
                low=price - 200,
                close=price,
                volume=10_000,
            )
        )

    storage = MockStorage({"HII": bars})
    results = check_engine_symbols(["HII"], SmaCrossStrategy, storage)
    res = results[0]

    assert res["is_silent"] is False
    assert res["bull_signals"] > 0
    assert res["bear_signals"] > 0
    assert res["status"] == "OK"
