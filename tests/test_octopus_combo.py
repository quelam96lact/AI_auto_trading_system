"""Tests cho OctopusComboStrategy (brief 2026-09-06-brief-dot-8-octopus-combo-vao-so-dang-ky.md).

Bốn kiểm chứng bắt buộc theo Tiêu chí 2 & 3:
1. Diff 1: Chuỗi thỏa octopus nhưng close <= MA(20) -> không tín hiệu (None).
2. Diff 2: Chuỗi thỏa octopus nhưng nến hiện tại đỏ (close < open) -> không tín hiệu (None).
3. Diff 3: Chuỗi có EMA9 > EMA21 KHÔNG cắt lên ở bar đó -> OctopusPullback trả None, OctopusCombo trả "bull".
4. Thanh khoản: Bình quân 20 ngày đã đóng < 2 tỷ -> không tín hiệu (None).
"""

from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.strategies.octopus_combo import OctopusComboStrategy
from trading.strategies.octopus_pullback import OctopusPullbackStrategy


def bar_at(i, close, open_=None, high=None, low=None, volume=10_000_000, symbol="VCB"):
    """Tạo bar ngày với timestamp tăng dần."""
    open_ = close if open_ is None else open_
    high = max(open_, close) + 1.0 if high is None else high
    low = min(open_, close) - 1.0 if low is None else low
    return Bar(
        symbol,
        datetime(2026, 1, 1, 9, 0, tzinfo=TZ) + timedelta(days=i),
        open_,
        high,
        low,
        close,
        volume,
    )


def base_combo_series(symbol="VCB", volume=10_000_000):
    """Chuỗi chuẩn:
    - 0..199: Tăng dần từ 100 đến 299 (đảm bảo EMA200, MA20 đều thấp hơn).
    - 200..207: Giảm mỗi phiên 2.0 (tạo 8 nến đỏ pullback liên tiếp).
    - 208: Nến xanh tăng mạnh +15.0 (open = 283, close = 298) -> EMA9 cắt lên EMA21, MACD > 0, close > EMA200 & MA20.
    """
    closes = []
    for i in range(209):
        if i < 200:
            closes.append(100.0 + i)
        elif i < 208:
            closes.append(closes[-1] - 2.0)
        else:
            closes.append(closes[-1] + 15.0)
    bars = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        bars.append(bar_at(i, c, open_=o, volume=volume, symbol=symbol))
    return bars


def feed(strategy, bars):
    return [strategy.compute_crossover(b) for b in bars]


def test_octopus_combo_warmup_and_conformance():
    s = OctopusComboStrategy()
    assert s.warmup_bars == 201
    assert s.qty == 100
    bars = base_combo_series()[:200]
    results = feed(s, bars)
    assert results == [None] * 200


def test_diff_1_fails_when_below_ma20():
    """Diff 1: Chuỗi thỏa mọi điều kiện Octopus nhưng close <= MA(20) -> trả None.

    Xây dựng: Sau 200 bar tăng, cho 19 bar đi ngang/giảm mạnh khiến MA20 cao hơn giá hiện tại
    nhưng close vẫn > EMA200.
    """
    s_combo = OctopusComboStrategy()
    bars = []
    # 0..199: Tăng 100 -> 299
    for i in range(200):
        c = 100.0 + i
        bars.append(bar_at(i, c, open_=c - 1.0))

    # 200..207: Giảm nhẹ mỗi ngày 1.0
    c = 299.0
    for i in range(200, 208):
        c -= 1.0
        bars.append(bar_at(i, c, open_=c + 0.5))  # nến đỏ

    # Giả sử MA20 ở mức ~295, nhưng bar 208 chỉ hồi lên 293 (dưới MA20 nhưng vẫn > EMA200 ~ 200)
    # Cố ý đặt MA20 cao: thêm các bar có close cao trong 20 bar gần nhất
    # Tại bar 208: Close = 292.0, nhưng MA20 = sum(20 bar cuối)/20 ~ 295.0 -> close < MA20
    b_208 = bar_at(208, close=292.0, open_=288.0)  # nến xanh, close > open
    bars.append(b_208)

    # Tính MA20 của 20 bar cuối
    ma20_actual = sum(b.close for b in bars[-20:]) / 20.0
    assert b_208.close < ma20_actual  # Khẳng định close < MA20

    # Chạy qua OctopusComboStrategy
    results = feed(s_combo, bars)
    assert results[208] is None, "Phải trả None khi close <= MA20"


def test_diff_2_fails_when_current_bar_is_red():
    """Diff 2: Chuỗi thỏa octopus (EMA cắt lên, MACD > 0, close > EMA200)
    nhưng nến hiện tại là nến ĐỎ (gap-up rồi giảm: open > close) -> OctopusCombo trả None.
    """
    s_combo = OctopusComboStrategy()
    bars = base_combo_series()
    # Bar 208 gốc là nến xanh (open=283, close=298).
    # Sửa bar 208 thành nến đỏ (gap up open=305, close=298 -> close < open):
    bars[208] = bar_at(208, close=298.0, open_=305.0, high=310.0, low=295.0)

    results = feed(s_combo, bars)
    assert results[208] is None, "Phải trả None khi nến hiện tại là nến đỏ (close <= open)"


def test_diff_3_bull_on_level_without_crossover():
    """Diff 3: Chuỗi có EMA9 > EMA21 từ bar trước (KHÔNG cắt lên ở bar hiện tại).
    - OctopusPullbackStrategy (yêu cầu cắt lên): trả None.
    - OctopusComboStrategy (yêu cầu so sánh mức): trả 'bull'.
    """
    s_octopus = OctopusPullbackStrategy()
    s_combo = OctopusComboStrategy()

    bars = base_combo_series()
    # Bar 208: EMA9 cắt lên EMA21.
    # Thêm Bar 209: Giá tiếp tục tăng xanh (open=298, close=305), EMA9 > EMA21 tiếp diễn (không cắt lên mới)
    b_209 = bar_at(209, close=305.0, open_=298.0, high=310.0, low=297.0)
    bars.append(b_209)

    res_oct = feed(s_octopus, bars)
    res_com = feed(s_combo, bars)

    # Tại bar 209:
    # Octopus gốc không có crossover mới -> None
    assert res_oct[209] is None
    # Octopus Combo thỏa mãn mức EMA9 > EMA21, nến xanh, MACD > 0, pullback trước đó -> 'bull'
    assert res_com[209] == "bull"


def test_fails_when_liquidity_below_2_billion():
    """Thanh khoản: Chuỗi có volume nhỏ khiến GTGD < 2 tỷ/ngày -> trả None."""
    s_combo = OctopusComboStrategy()
    # Volume chỉ 1.000 cổ phiếu * giá 100-300 -> GTGD ~ vài trăm nghìn đến vài triệu VND (< 2 tỷ)
    bars = base_combo_series(volume=1_000)
    results = feed(s_combo, bars)
    assert all(r is None for r in results), "Không được phát tín hiệu khi thanh khoản < 2 tỷ"
