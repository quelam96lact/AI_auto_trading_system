"""Tests cho EmaCalculator + MacdCalculator (Octopus Pullback, brief
2026-08-15-hermes-octopus-pullback.md).

Quy ước seed EMA (ghi rõ trong docstring indicators.py): EMA được seed bằng SMA
của N giá trị đầu (bar thứ N-1 trả về SMA), từ bar thứ N trở đi dùng công thức
EMA(t) = alpha*close(t) + (1-alpha)*EMA(t-1) với alpha = 2/(period+1).
"""

from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.indicators import EmaCalculator, MacdCalculator
from trading.models import Bar


def bar(i, close, symbol="VCB", open_=None):
    open_ = close if open_ is None else open_
    return Bar(
        symbol,
        datetime(2026, 7, 15, 9, 0, tzinfo=TZ) + timedelta(minutes=5 * i),
        open_,
        max(open_, close),
        min(open_, close),
        close,
        100,
    )


# ── EMA ──────────────────────────────────────────────────────────────────


def test_ema_returns_none_during_warmup_then_seeds_with_sma():
    ema = EmaCalculator(period=3)
    assert ema.update(bar(0, 10.0)) is None
    assert ema.update(bar(1, 11.0)) is None
    # bar 2 hoàn thành warm-up: seed = SMA(10, 11, 12) = 11
    assert ema.update(bar(2, 12.0)) == 11.0


def test_ema_recursive_formula_after_seed():
    ema = EmaCalculator(period=3)
    for c in (10.0, 11.0, 12.0):
        ema.update(bar(0 if c == 10.0 else 1 if c == 11.0 else 2, c))
    # alpha = 2/(3+1) = 0.5; EMA = 0.5*13 + 0.5*11 = 12
    assert ema.update(bar(3, 13.0)) == 12.0
    # EMA = 0.5*14 + 0.5*12 = 13
    assert ema.update(bar(4, 14.0)) == 13.0


def test_ema_constant_series_converges_to_price():
    ema = EmaCalculator(period=3)
    result = None
    for i in range(30):
        result = ema.update(bar(i, 42.0))
    assert result is not None
    assert abs(result - 42.0) < 1e-9


def test_ema_state_isolated_per_symbol():
    ema = EmaCalculator(period=2)
    assert ema.update(bar(0, 10.0, symbol="VCB")) is None
    assert ema.update(bar(0, 100.0, symbol="HPG")) is None
    # VCB có 2 bar -> seed SMA(10, 12) = 11; HPG mới 1 bar -> None
    assert ema.update(bar(1, 12.0, symbol="VCB")) == 11.0
    assert ema.update(bar(1, 120.0, symbol="HPG")) == 110.0


# ── MACD ─────────────────────────────────────────────────────────────────


def test_macd_returns_none_during_warmup():
    macd = MacdCalculator(fast=2, slow=3, signal=2)
    for i in range(3):  # slow=3 bar cho EMA, còn thiếu signal warm-up
        assert macd.update(bar(i, 10.0)) is None


def test_macd_constant_series_histogram_zero():
    macd = MacdCalculator(fast=2, slow=3, signal=2)
    result = None
    for i in range(30):
        result = macd.update(bar(i, 10.0))
    # macd = EMA2 - EMA3 = 0 với chuỗi hằng -> histogram = 0
    assert result is not None
    assert abs(result) < 1e-9


def test_macd_uptrend_positive_downtrend_negative():
    macd = MacdCalculator(fast=2, slow=3, signal=2)
    # Tăng dần đều: EMA nhanh > EMA chậm -> histogram > 0
    up = None
    for i in range(30):
        up = macd.update(bar(i, 10.0 + i))
    assert up is not None and up > 0

    macd2 = MacdCalculator(fast=2, slow=3, signal=2)
    down = None
    for i in range(30):
        down = macd2.update(bar(i, 50.0 - i))
    assert down is not None and down < 0


def test_macd_histogram_changes_sign_at_trend_reversal():
    macd = MacdCalculator(fast=2, slow=3, signal=2)
    # 15 bar tăng rồi 15 bar giảm: histogram phải từ dương sang âm
    hist = []
    for i in range(15):
        hist.append(macd.update(bar(i, 10.0 + i)))
    for i in range(15, 30):
        hist.append(macd.update(bar(i, 40.0 - (i - 15))))
    non_none = [h for h in hist if h is not None]
    assert len(non_none) >= 2  # ít nhất 2 giá trị sau warm-up
    # Giá trị cuối (sau chuỗi giảm dài) phải âm
    assert non_none[-1] < 0
    # Tại thời điểm đổi chiều phải có ít nhất 1 lần đổi dấu giữa các giá trị liên tiếp
    from itertools import pairwise

    sign_changes = sum(
        1 for a, b in pairwise(non_none) if (a > 0) != (b > 0)
    )
    assert sign_changes >= 1


def test_macd_state_isolated_per_symbol():
    macd = MacdCalculator(fast=2, slow=3, signal=2)
    for i in range(30):
        macd.update(bar(i, 10.0 + i, symbol="VCB"))
    # HPG chỉ mới 1 bar -> None (warm-up riêng của HPG)
    assert macd.update(bar(0, 5.0, symbol="HPG")) is None
    # VCB vẫn trả giá trị sau khi HPG chen vào
    assert macd.update(bar(30, 50.0, symbol="VCB")) is not None
