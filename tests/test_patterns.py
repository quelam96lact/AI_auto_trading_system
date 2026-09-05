"""Unit tests cho các bộ nhận dạng mẫu nến (Gói P1 — brief 2026-09-06-brief-ba-chien-luoc-nen-tu-slide.md).

Kiểm thử:
1. is_doji:
   - Doji hoàn hảo (close == open).
   - Doji thông thường (thân <= 10% chiều dài nến).
   - Nến thân lớn (bị loại).
   - Luật Near Doji: > 2 Doji trước đó thì Doji hiện tại bị loại bỏ (False).
2. is_hammer:
   - Nến búa chuẩn sau xu hướng giảm (True).
   - Nến búa thân đỏ sau xu hướng giảm (True — búa tăng hay giảm đều được).
   - Nến có bóng trên dài (False — vi phạm ĐK4).
   - Nến xuất hiện sau xu hướng tăng (False — vi phạm ĐK1).
   - Nến có bóng dưới ngắn < 2x thân (False — vi phạm ĐK3).
   - Nến thân nằm ở nửa dưới nến (False — vi phạm ĐK2).
3. combo_signal:
   - Combo BUY: Nến xanh + Close > MA20 + MACD_HIST > 0 -> "buy".
   - Combo SELL: Nến đỏ + Close < MA20 + MACD_HIST < 0 -> "sell".
   - Không đủ điều kiện hoặc thiếu chỉ báo -> None.
"""

from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.patterns import combo_signal, is_doji, is_hammer


def _make_bar(
    symbol: str = "TEST",
    idx: int = 0,
    open: float = 100.0,
    high: float = 110.0,
    low: float = 90.0,
    close: float = 100.0,
    volume: int = 10_000,
) -> Bar:
    base_time = datetime(2026, 1, 1, 9, 0, tzinfo=TZ)
    return Bar(
        symbol=symbol,
        ts=base_time + timedelta(days=idx),
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


# ---------------------------------------------------------------------------
# 1. Tests cho is_doji
# ---------------------------------------------------------------------------


def test_perfect_doji():
    """Doji hoàn hảo: close == open."""
    bar = _make_bar(open=100.0, high=110.0, low=90.0, close=100.0)
    assert is_doji(bar) is True


def test_standard_doji():
    """Doji thông thường: thân nến = 1.0 trên toàn bộ dải 20.0 (5% <= 10%)."""
    bar = _make_bar(open=100.0, high=110.0, low=90.0, close=101.0)
    assert is_doji(bar) is True


def test_large_body_candle_is_not_doji():
    """Nến thân lớn: thân nến = 10.0 trên dải 20.0 (50% > 10%) -> False."""
    bar = _make_bar(open=95.0, high=110.0, low=90.0, close=105.0)
    assert is_doji(bar) is False


def test_flat_candle_doji():
    """Nến phẳng: high == low. Hành vi do `require_range` quyết định — xem
    docstring `is_doji`. Mặc định (True) coi nến phẳng KHÔNG phải doji."""
    bar_equal = _make_bar(open=100.0, high=100.0, low=100.0, close=100.0)
    assert is_doji(bar_equal) is False
    assert is_doji(bar_equal, require_range=False) is True

    # close != open trên nến phẳng là dữ liệu vô lý — sai ở cả hai chế độ
    bar_diff = _make_bar(open=100.0, high=100.0, low=100.0, close=101.0)
    assert is_doji(bar_diff) is False
    assert is_doji(bar_diff, require_range=False) is False


def test_near_doji_rule_rejects_third_doji():
    """Luật Near Doji: Nếu đã có > 2 doji (tức 3 doji) trong 5 phiên trước -> Doji hiện tại bị loại."""
    prior_dojis = [
        _make_bar(idx=0, open=100.0, high=110.0, low=90.0, close=100.0),
        _make_bar(idx=1, open=101.0, high=111.0, low=91.0, close=101.0),
        _make_bar(idx=2, open=102.0, high=112.0, low=92.0, close=102.0),
    ]
    cur_doji = _make_bar(idx=3, open=103.0, high=113.0, low=93.0, close=103.0)

    # 3 doji trước đó > max_prior_doji (2) -> False
    assert is_doji(cur_doji, prev_bars=prior_dojis, max_prior_doji=2) is False


def test_doji_allowed_when_within_max_prior_doji():
    """Nếu chỉ có 2 Doji trước đó (<= max_prior_doji 2) -> Doji hiện tại vẫn hợp lệ."""
    prior_bars = [
        _make_bar(idx=0, open=90.0, high=110.0, low=90.0, close=105.0),  # nến lớn
        _make_bar(idx=1, open=101.0, high=111.0, low=91.0, close=101.0),  # doji 1
        _make_bar(idx=2, open=102.0, high=112.0, low=92.0, close=102.0),  # doji 2
    ]
    cur_doji = _make_bar(idx=3, open=103.0, high=113.0, low=93.0, close=103.0)

    assert is_doji(cur_doji, prev_bars=prior_bars, max_prior_doji=2) is True


# ---------------------------------------------------------------------------
# 2. Tests cho is_hammer
# ---------------------------------------------------------------------------


def _make_downtrend_bars() -> list[Bar]:
    """Tạo chuỗi 3 nến giảm liên tiếp."""
    return [
        _make_bar(idx=0, open=150.0, high=155.0, low=138.0, close=140.0),
        _make_bar(idx=1, open=140.0, high=142.0, low=128.0, close=130.0),
        _make_bar(idx=2, open=130.0, high=132.0, low=118.0, close=120.0),
    ]


def test_perfect_hammer_after_downtrend():
    """Búa chuẩn: xuất hiện sau downtrend, thân ở đỉnh (118-120), bóng dưới dài (100-118=18, gấp 9x thân), bóng trên = 0."""
    downtrend = _make_downtrend_bars()
    hammer = _make_bar(idx=3, open=118.0, high=120.0, low=100.0, close=120.0)

    assert is_hammer(hammer, prev_bars=downtrend) is True


def test_bearish_hammer_after_downtrend():
    """Búa thân đỏ (close < open) nhưng thân ở đỉnh, bóng dưới dài (17), bóng trên ngắn (1) -> True."""
    downtrend = _make_downtrend_bars()
    # range = 120 - 100 = 20; body = 2.0; lower = 117 - 100 = 17 (8.5x); upper = 120 - 119 = 1.0 (5% <= 10%)
    hammer = _make_bar(idx=3, open=119.0, high=120.0, low=100.0, close=117.0)

    assert is_hammer(hammer, prev_bars=downtrend) is True


def test_hammer_rejected_if_upper_shadow_too_long():
    """Búa bị loại vì bóng trên quá dài (> 10% dải nến) — vi phạm ĐK4."""
    downtrend = _make_downtrend_bars()
    # range = 125 - 100 = 25; body = 2.0 (116-118); upper = 125 - 118 = 7.0 (28% > 10%)
    rejected_hammer = _make_bar(idx=3, open=116.0, high=125.0, low=100.0, close=118.0)

    assert is_hammer(rejected_hammer, prev_bars=downtrend) is False


def test_hammer_rejected_if_after_uptrend():
    """Búa bị loại nếu xuất hiện sau xu hướng TĂNG (uptrend) — vi phạm ĐK1."""
    uptrend = [
        _make_bar(idx=0, open=100.0, high=112.0, low=98.0, close=110.0),
        _make_bar(idx=1, open=110.0, high=122.0, low=108.0, close=120.0),
        _make_bar(idx=2, open=120.0, high=132.0, low=118.0, close=130.0),
    ]
    hammer = _make_bar(idx=3, open=128.0, high=130.0, low=110.0, close=130.0)

    assert is_hammer(hammer, prev_bars=uptrend) is False


def test_hammer_rejected_if_lower_shadow_too_short():
    """Búa bị loại nếu bóng dưới ngắn (< 2x thân) — vi phạm ĐK3 (11.0 < 2x6.0=12.0)."""
    downtrend = _make_downtrend_bars()
    # range = 118 - 100 = 18; body = 6.0 (33% <= 35%); upper = 1.0 (5.5% <= 10%); lower = 11.0 (1.83x < 2x)
    rejected_hammer = _make_bar(idx=3, open=111.0, high=118.0, low=100.0, close=117.0)

    assert is_hammer(rejected_hammer, prev_bars=downtrend) is False


def test_hammer_rejected_if_body_at_bottom():
    """Búa bị loại nếu thân nến nằm ở nửa dưới dải nến — vi phạm ĐK2."""
    downtrend = _make_downtrend_bars()
    # range = 120 - 100 = 20; body = 2.0 (100-102); lower = 100 - 100 = 0
    rejected_hammer = _make_bar(idx=3, open=102.0, high=120.0, low=100.0, close=100.0)

    assert is_hammer(rejected_hammer, prev_bars=downtrend) is False


# ---------------------------------------------------------------------------
# 3. Tests cho combo_signal
# ---------------------------------------------------------------------------


def test_combo_signal_buy():
    """Combo BUY: Nến xanh + Close > MA20 + MACD_HIST > 0."""
    bar = _make_bar(open=100.0, close=105.0)
    assert combo_signal(bar, ma20=102.0, macd_hist=0.5) == "buy"


def test_combo_signal_sell():
    """Combo SELL: Nến đỏ + Close < MA20 + MACD_HIST < 0."""
    bar = _make_bar(open=105.0, close=100.0)
    assert combo_signal(bar, ma20=102.0, macd_hist=-0.5) == "sell"


def test_combo_signal_none_when_missing_indicators():
    """Trả về None khi thiếu giá trị MA hoặc MACD."""
    bar = _make_bar(open=100.0, close=105.0)
    assert combo_signal(bar, ma20=None, macd_hist=0.5) is None
    assert combo_signal(bar, ma20=102.0, macd_hist=None) is None


def test_combo_signal_none_when_conflicting():
    """Trả về None khi các điều kiện mâu thuẫn nhau."""
    # Nến xanh + Close > MA20 nhưng MACD < 0
    bar_green = _make_bar(open=100.0, close=105.0)
    assert combo_signal(bar_green, ma20=102.0, macd_hist=-0.5) is None

    # Nến đỏ + Close < MA20 nhưng MACD > 0
    bar_red = _make_bar(open=105.0, close=100.0)
    assert combo_signal(bar_red, ma20=102.0, macd_hist=0.5) is None

    # Nến đỏ nhưng Close > MA20
    assert combo_signal(bar_red, ma20=98.0, macd_hist=-0.5) is None


# ---------------------------------------------------------------------------
# require_range — điểm mơ hồ thứ 8, thêm khi Claude audit 06/09
# ---------------------------------------------------------------------------


def _flat_bar(price: float = 100.0) -> Bar:
    """Nến PHẲNG: high == low == open == close, không có giao dịch thật."""
    return Bar(
        symbol="FLAT",
        ts=datetime(2026, 1, 1, 9, 0, tzinfo=TZ),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=0,
    )


def test_flat_bar_khong_phai_doji_theo_mac_dinh():
    """Nến phẳng volume 0 KHÔNG phải doji: không có biên độ thì không có thế
    giằng co. 36,6% bar trong bars_daily là phẳng — tính chúng là doji thổi
    con số tổng lên ~1,8 lần (đo khi audit 06/09)."""
    assert is_doji(_flat_bar()) is False


def test_flat_bar_la_doji_khi_tat_require_range():
    """Đúng chữ của slide (close == open) — giữ được để tái hiện bản đầu."""
    assert is_doji(_flat_bar(), require_range=False) is True


def test_nen_phang_khong_chiem_han_ngach_near_doji():
    """Nến phẳng bị loại thì cũng không được tính vào hạn ngạch Near Doji —
    nếu không, một chuỗi nến phẳng sẽ âm thầm chặn một doji thật phía sau."""
    flats = [_flat_bar() for _ in range(5)]
    doji_that = Bar(
        symbol="FLAT",
        ts=datetime(2026, 1, 2, 9, 0, tzinfo=TZ),
        open=100.0,
        high=110.0,
        low=90.0,
        close=100.5,
        volume=10_000,
    )
    assert is_doji(doji_that, prev_bars=flats) is True
