import math
import statistics
from datetime import UTC, datetime

from trading.indicators import (
    AdxCalculator,
    BollingerCalculator,
    DonchianCalculator,
    percent_b,
)
from trading.models import Bar


def _make_bar(
    symbol: str,
    idx: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    vol: float = 100.0,
) -> Bar:
    ts = datetime(2024, 1, 1, 0, 0, tzinfo=UTC).timestamp() + idx * 3600
    dt = datetime.fromtimestamp(ts, tz=UTC)
    return Bar(
        symbol=symbol,
        ts=dt,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=vol,
    )


def test_donchian_lookahead_prevention():
    """1. DonchianCalculator trên chuỗi high tăng đều [10, 11, 12, ...] với period=3:
    kiểm rằng giá trị trả về tại bar thứ 4 là biên của ba bar đầu, không gồm bar thứ 4.
    """
    calc = DonchianCalculator(period=3)
    sym = "BTC-USDT"

    # Bar 1: high=10, low=5
    b1 = _make_bar(sym, 0, 8.0, 10.0, 5.0, 9.0)
    # Bar 2: high=11, low=6
    b2 = _make_bar(sym, 1, 9.0, 11.0, 6.0, 10.0)
    # Bar 3: high=12, low=7
    b3 = _make_bar(sym, 2, 10.0, 12.0, 7.0, 11.0)
    # Bar 4: high=13, low=8
    b4 = _make_bar(sym, 3, 11.0, 13.0, 8.0, 12.0)

    assert calc.update(b1) is None
    assert calc.update(b2) is None
    assert calc.update(b3) is None

    res = calc.update(b4)
    assert res is not None
    upper, lower = res
    # Phải là max/min của 3 bar đầu (10..12 và 5..7), KHÔNG gồm bar thứ 4 (high=13, low=8)
    assert upper == 12.0
    assert lower == 5.0
    assert calc.last(sym) == (12.0, 5.0)


def test_donchian_returns_none_before_period():
    """2. DonchianCalculator trả None khi chưa đủ period bar."""
    calc = DonchianCalculator(period=5)
    sym = "BTC-USDT"

    for i in range(5):
        b = _make_bar(sym, i, 100.0, 105.0, 95.0, 102.0)
        assert calc.update(b) is None
        assert calc.last(sym) is None

    b6 = _make_bar(sym, 5, 100.0, 110.0, 90.0, 102.0)
    res = calc.update(b6)
    assert res is not None
    assert res == (105.0, 95.0)


def test_bollinger_constant_series():
    """3. BollingerCalculator trên chuỗi hằng số (mọi close = 100):
    middle == 100, upper == lower == 100, và percent_b trả None.
    """
    calc = BollingerCalculator(period=20, num_std=2.0)
    sym = "BTC-USDT"

    res = None
    for i in range(20):
        b = _make_bar(sym, i, 100.0, 100.0, 100.0, 100.0)
        res = calc.update(b)

    assert res is not None
    middle, upper, lower = res
    assert middle == 100.0
    assert upper == 100.0
    assert lower == 100.0
    assert calc.last(sym) == (100.0, 100.0, 100.0)

    # percent_b trả None khi upper == lower
    assert percent_b(100.0, upper, lower) is None


def test_bollinger_sample_stdev():
    """4. BollingerCalculator trên một chuỗi 20 giá đóng cụ thể:
    đối chiếu middle với statistics.mean và độ lệch chuẩn với statistics.stdev (mẫu n-1).
    """
    calc = BollingerCalculator(period=20, num_std=2.0)
    sym = "BTC-USDT"

    prices = [
        10.0, 11.5, 12.0, 11.0, 13.0, 14.5, 13.5, 15.0, 16.0, 15.5,
        17.0, 16.5, 18.0, 19.5, 19.0, 20.0, 21.5, 20.5, 22.0, 23.0,
    ]
    assert len(prices) == 20

    res = None
    for i, p in enumerate(prices):
        b = _make_bar(sym, i, p, p + 1.0, p - 1.0, p)
        res = calc.update(b)

    assert res is not None
    middle, upper, lower = res

    expected_mean = statistics.mean(prices)
    expected_sd = statistics.stdev(prices)  # stdev mẫu (n-1)
    expected_upper = expected_mean + 2.0 * expected_sd
    expected_lower = expected_mean - 2.0 * expected_sd

    assert math.isclose(middle, expected_mean, rel_tol=1e-9)
    assert math.isclose(upper, expected_upper, rel_tol=1e-9)
    assert math.isclose(lower, expected_lower, rel_tol=1e-9)


def test_adx_strongly_trending_series():
    """5. AdxCalculator trên chuỗi tăng đơn điệu mạnh 60 bar: ADX cuối cùng > 40."""
    calc = AdxCalculator(period=14)
    sym = "BTC-USDT"

    adx = None
    for i in range(60):
        # Tăng mạnh mỗi bar: high tăng 5, low tăng 5
        base = 100.0 + i * 5.0
        b = _make_bar(sym, i, base, base + 5.0, base, base + 4.0)
        adx = calc.update(b)

    assert adx is not None
    assert adx > 40.0
    assert calc.last(sym) == adx


def test_adx_flat_oscillating_series():
    """6. AdxCalculator trên chuỗi dao động phẳng 60 bar: ADX cuối cùng < 20."""
    calc = AdxCalculator(period=14)
    sym = "BTC-USDT"

    adx = None
    for i in range(60):
        # Dao động quanh mức 100, không có xu hướng
        if i % 2 == 0:
            b = _make_bar(sym, i, 100.0, 102.0, 99.0, 100.0)
        else:
            b = _make_bar(sym, i, 100.0, 101.0, 98.0, 100.0)
        adx = calc.update(b)

    assert adx is not None
    assert adx < 20.0
    assert calc.last(sym) == adx


def test_adx_warmup():
    """7. AdxCalculator trả None trước khi đủ warm-up."""
    calc = AdxCalculator(period=14)
    sym = "BTC-USDT"

    # Với period=14, cần 1 bar khởi đầu prev_bar + 14 bar để seed S(TR)/S(DM)
    # + 13 bar DX tiếp theo = 28 bar (index 0..27) mới có ADX đầu tiên tại bar thứ 28 (idx 27)
    for i in range(27):
        base = 100.0 + i * 2.0
        b = _make_bar(sym, i, base, base + 2.0, base, base + 1.0)
        assert calc.update(b) is None, f"Bar {i} should be None during warmup"
        assert calc.last(sym) is None

    b28 = _make_bar(sym, 27, 100.0 + 27 * 2.0, 100.0 + 27 * 2.0 + 2.0, 100.0 + 27 * 2.0, 100.0 + 27 * 2.0 + 1.0)
    assert calc.update(b28) is not None
