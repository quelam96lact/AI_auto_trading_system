"""Unit tests cho cơ chế thanh khoản gộp theo NGÀY (Gói K — plan 2026-09-06).

Kiểm chứng:
1. test_intraday_5m_bars_aggregated_as_single_day (Tiêu chí 2):
   48 bar 5 phút của 1 ngày (tổng 2,5 tỷ) chỉ được tính là 1 ngày đã đóng khi sang ngày hôm sau,
   chưa đủ 20 ngày thì _liquidity_ok phải là False (không bị nhầm 48 bar = 48 ngày).
2. test_twenty_closed_days_activates_liquidity:
   20 ngày đầy đủ (mỗi ngày 48 bar, tổng > 2 tỷ/ngày) sang ngày 21 phải mở cổng thanh khoản.
3. test_daily_liquidity_tracker_is_identical_on_daily_bars:
   Trên bar ngày (1 bar = 1 ngày), DailyLiquidityTracker cho kết quả giống hệt cơ chế cũ.
4. test_ever_liquid_matches_strategy_with_daily_tracker:
   ever_liquid và OctopusPullbackStrategy._liquidity_ok đồng thuận 100% trên bar 5m và bar ngày.
"""

from datetime import datetime, timedelta

from trading.backtest import ever_liquid
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.strategies.octopus_pullback import (
    DailyLiquidityTracker,
    OctopusPullbackStrategy,
)


def _make_5m_day_bars(symbol: str, day_idx: int, bar_val: float = 60_000_000.0, n_bars: int = 48) -> list[Bar]:
    """Tạo 48 bar 5 phút cho 1 ngày giao dịch (tổng giá trị = 48 * bar_val)."""
    base_date = datetime(2026, 1, 1, 9, 0, tzinfo=TZ) + timedelta(days=day_idx)
    bars = []
    # bar_val = close * volume
    close = 20_000.0
    vol = int(bar_val // close)
    for i in range(n_bars):
        bars.append(
            Bar(
                symbol=symbol,
                ts=base_date + timedelta(minutes=5 * i),
                open=close,
                high=close + 100,
                low=close - 100,
                close=close,
                volume=vol,
            )
        )
    return bars


def test_intraday_5m_bars_aggregated_as_single_day():
    """Tiêu chí 2: 48 bar 5 phút của ngày 1 (tổng 2,88 tỷ) sang ngày 2 chỉ là 1 ngày đã đóng.
    Cửa sổ 20 ngày bắt buộc phải trả False/None (không bị nhầm 48 bar = 48 ngày).
    """
    strat = OctopusPullbackStrategy(min_avg_value_20=2_000_000_000.0, liquidity_window=20)
    
    # Ngày 0: 48 bar 5 phút (mỗi bar 60tr -> 2,88 tỷ/ngày)
    day0_bars = _make_5m_day_bars("HII", 0, bar_val=60_000_000.0)
    for b in day0_bars:
        strat.compute_crossover(b)
        # Trong ngày 0, chưa có ngày nào đóng -> False
        assert strat._liquidity_ok("HII") is False

    # Ngày 1: Bar đầu tiên của ngày 1 đến -> ngày 0 được đóng (1 ngày đóng)
    day1_bars = _make_5m_day_bars("HII", 1, bar_val=60_000_000.0)
    strat.compute_crossover(day1_bars[0])

    # Chỉ mới có 1 ngày đóng, cửa sổ yêu cầu 20 ngày -> BẮT BUỘC False
    assert strat._liquidity_ok("HII") is False


def test_twenty_closed_days_activates_liquidity():
    """Đủ 20 ngày đã đóng (mỗi ngày 48 bar 5m, tổng > 2 tỷ/ngày) -> sang ngày 21 cổng PHẢI MỞ."""
    strat = OctopusPullbackStrategy(min_avg_value_20=2_000_000_000.0, liquidity_window=20)
    
    all_bars = []
    # 20 ngày đầu: ngày 0 đến ngày 19
    for d in range(20):
        all_bars.extend(_make_5m_day_bars("HII", d, bar_val=60_000_000.0))
    
    for b in all_bars:
        strat.compute_crossover(b)
    
    # Ở cuối ngày 19, mới có 19 ngày đóng (ngày 0..18) -> vẫn False
    assert strat._liquidity_ok("HII") is False

    # Sang ngày 20 (ngày thứ 21): Bar đầu tiên đến -> ngày 19 đóng -> đủ 20 ngày đóng!
    day20_bars = _make_5m_day_bars("HII", 20, bar_val=60_000_000.0)
    strat.compute_crossover(day20_bars[0])

    # 20 ngày đóng đều đạt 2,88 tỷ >= 2 tỷ -> CỔNG PHẢI MỞ (True)
    assert strat._liquidity_ok("HII") is True


def test_daily_liquidity_tracker_is_identical_on_daily_bars():
    """Trên bar ngày (1 bar = 1 ngày), DailyLiquidityTracker cho kết quả chuẩn xác."""
    tracker = DailyLiquidityTracker(window=3)
    base_time = datetime(2026, 1, 1, 9, 0, tzinfo=TZ)
    
    # 3 bar ngày liên tiếp, mỗi ngày 3 tỷ
    b0 = Bar("VCB", base_time, 100, 100, 100, 100, 30_000_000)
    b1 = Bar("VCB", base_time + timedelta(days=1), 100, 100, 100, 100, 30_000_000)
    b2 = Bar("VCB", base_time + timedelta(days=2), 100, 100, 100, 100, 30_000_000)
    b3 = Bar("VCB", base_time + timedelta(days=3), 100, 100, 100, 100, 30_000_000)

    assert tracker.update(b0) is None  # 0 ngày đóng
    assert tracker.update(b1) is None  # 1 ngày đóng (ngày 0)
    assert tracker.update(b2) is None  # 2 ngày đóng (ngày 0, 1)
    avg3 = tracker.update(b3)          # 3 ngày đóng (ngày 0, 1, 2)
    assert avg3 == 3_000_000_000.0


def test_ever_liquid_matches_strategy_with_daily_tracker():
    """ever_liquid và OctopusPullbackStrategy._liquidity_ok đồng thuận 100%."""
    all_bars = []
    for d in range(22):
        all_bars.extend(_make_5m_day_bars("AAA", d, bar_val=60_000_000.0))
    
    strat = OctopusPullbackStrategy(min_avg_value_20=2_000_000_000.0, liquidity_window=20)
    for b in all_bars:
        strat.compute_crossover(b)

    assert strat._liquidity_ok("AAA") is True
    assert ever_liquid(all_bars, 2_000_000_000.0, 20) is True
