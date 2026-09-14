"""Test cho trading/feature_panel.py (Brief đợt 41).

Tám bài test kiểm chứng Task 2 (§2.5):
1. Funding không nhìn trước
2. Metrics quá cũ (staleness)
3. OI bằng 0 thành NULL nhưng các cột tỷ lệ vẫn giữ
4. oi_chg cần đủ cả hai đầu mút
5. funding_z cần đủ 90 ngày lịch sử
6. delta_norm khớp 2 * buy_ratio - 1
7. Biến mục tiêu đúng
8. Test cắt cụt không rò rỉ (Non-leakage truncation test)
"""

from datetime import UTC, datetime, timedelta

from trading.feature_panel import build_feature_panel
from trading.models import Bar


def _make_bar(ts: datetime, close: float, symbol: str = "BTCUSDT") -> Bar:
    return Bar(symbol=symbol, ts=ts, open=close, high=close, low=close, close=close, volume=1000)


def test_1_funding_no_lookahead():
    # Nến 1: ts = 07:00, close_ts = 08:00
    ts = datetime(2024, 1, 1, 7, 0, tzinfo=UTC)
    bar = _make_bar(ts, 40000.0)

    # Lần settle 1: 00:00 (rate = 0.0001)
    # Lần settle 2: đúng 08:00:00 (rate = 0.0002)
    # Lần settle 3: 08:00:01 (1 giây sau close_ts, rate = 0.0005)
    # Trường hợp A: settle đúng 08:00:00 -> ĐƯỢC DÙNG (rate = 0.0002)
    funding_A = [
        (datetime(2024, 1, 1, 0, 0, tzinfo=UTC), 0.0001),
        (datetime(2024, 1, 1, 8, 0, tzinfo=UTC), 0.0002),
    ]
    panel_A = build_feature_panel([bar], funding_A, [], [])
    assert panel_A[0]["funding_rate"] == 0.0002

    # Trường hợp B: settle lúc 08:00:01 -> KHÔNG ĐƯỢC DÙNG -> phải lấy lúc 00:00 (rate = 0.0001)
    funding_B = [
        (datetime(2024, 1, 1, 0, 0, tzinfo=UTC), 0.0001),
        (datetime(2024, 1, 1, 8, 0, 1, tzinfo=UTC), 0.0005),
    ]
    panel_B = build_feature_panel([bar], funding_B, [], [])
    assert panel_B[0]["funding_rate"] == 0.0001


def test_2_metrics_staleness():
    ts = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bar = _make_bar(ts, 40000.0)

    # Mốc metrics gần nhất lúc 00:40 (hoàn tất 00:45, cách close_ts 15 phút, vượt ngưỡng staleness 10 phút)
    stale_metric = {
        "ts": datetime(2024, 1, 1, 0, 40, tzinfo=UTC),
        "sum_open_interest": 50000.0,
        "count_long_short_ratio": 1.5,
        "sum_toptrader_long_short_ratio": 1.2,
        "sum_taker_long_short_vol_ratio": 1.1,
    }
    panel = build_feature_panel([bar], [], [stale_metric], [], max_metric_staleness_minutes=10)
    assert panel[0]["long_short_ratio"] is None
    assert panel[0]["toptrader_ls_ratio"] is None
    assert panel[0]["taker_ls_vol_ratio"] is None
    assert panel[0]["oi_chg_3h"] is None


def test_3_oi_zero_becomes_null_ratio_preserved():
    ts = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bar = _make_bar(ts, 40000.0)

    # Metrics hoàn tất tại close_ts (01:00) có mốc 00:55, sum_open_interest = 0
    m_now = {
        "ts": datetime(2024, 1, 1, 0, 55, tzinfo=UTC),
        "sum_open_interest": 0.0,
        "sum_open_interest_value": 0.0,
        "count_long_short_ratio": 1.68,
        "sum_toptrader_long_short_ratio": 1.35,
        "sum_taker_long_short_vol_ratio": 1.20,
    }
    # Mốc 3h trước hợp lệ
    m_prev = {
        "ts": datetime(2023, 12, 31, 21, 55, tzinfo=UTC),
        "sum_open_interest": 45000.0,
        "count_long_short_ratio": 1.5,
    }
    panel = build_feature_panel([bar], [], [m_prev, m_now], [])

    # oi_chg_3h phải là None vì mốc hiện tại có OI = 0 (coi là None)
    assert panel[0]["oi_chg_3h"] is None
    # Nhưng long_short_ratio vẫn bảo toàn giá trị
    assert panel[0]["long_short_ratio"] == 1.68
    assert panel[0]["toptrader_ls_ratio"] == 1.35


def test_4_oi_chg_needs_both_endpoints():
    ts = datetime(2024, 1, 1, 3, 0, tzinfo=UTC)
    bar = _make_bar(ts, 40000.0)
    # close_ts = 04:00
    # Mốc close_ts có metric
    m_now = {
        "ts": datetime(2024, 1, 1, 4, 0, tzinfo=UTC),
        "sum_open_interest": 50000.0,
        "count_long_short_ratio": 1.5,
    }
    # Thiếu mốc close_ts - 3h (01:00)
    panel = build_feature_panel([bar], [], [m_now], [])
    assert panel[0]["oi_chg_3h"] is None


def test_5_funding_z_needs_90_days():
    start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    # Tạo 200 lần settle (mỗi lần 8h -> ~66 ngày, chưa đủ 90 ngày / 260 lần)
    funding_66d = [(start + timedelta(hours=8 * i), 0.0001) for i in range(200)]
    bar_66d = _make_bar(start + timedelta(hours=8 * 199), 40000.0)
    panel_66d = build_feature_panel([bar_66d], funding_66d, [], [])
    assert panel_66d[0]["funding_z"] is None

    # Tạo đủ 280 lần settle (>90 ngày, >260 lần)
    # Cho các giá trị có biến động để std > 0
    funding_95d = []
    for i in range(280):
        t = start + timedelta(hours=8 * i)
        rate = 0.0001 if i % 2 == 0 else 0.0003
        funding_95d.append((t, rate))

    bar_95d = _make_bar(start + timedelta(hours=8 * 279), 40000.0)
    panel_95d = build_feature_panel([bar_95d], funding_95d, [], [])
    assert panel_95d[0]["funding_z"] is not None


def test_6_delta_norm_equals_two_buy_ratio_minus_one():
    ts = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bar = _make_bar(ts, 40000.0)

    # Buy = 70, Sell = 30 -> Total = 100, Delta = 40
    # buy_ratio = 70 / 100 = 0.70
    # 2 * buy_ratio - 1 = 2 * 0.7 - 1 = 0.40
    # delta_norm = 40 / 100 = 0.40
    of = [{
        "ts": ts,
        "taker_buy_volume": 70.0,
        "taker_sell_volume": 30.0,
        "delta": 40.0,
        "buy_ratio": 0.70,
        "trade_count": 100,
    }]
    panel = build_feature_panel([bar], [], [], of)
    delta_norm = panel[0]["delta_norm"]
    assert delta_norm is not None
    assert abs(delta_norm - 0.40) < 1e-6
    expected_from_buy_ratio = 2 * of[0]["buy_ratio"] - 1.0
    assert abs(delta_norm - expected_from_buy_ratio) < 1e-6


def test_7_forward_returns_correct():
    start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    # Dựng chuỗi 30 nến: giá tăng mỗi giờ 100
    # close[i] = 1000 + 100 * i
    bars = [_make_bar(start + timedelta(hours=i), 1000.0 + 100.0 * i) for i in range(30)]
    panel = build_feature_panel(bars, [], [], [])

    # Tại i = 0: close = 1000
    # close[t+1] = 1100 -> fwd_ret_1h = 1100/1000 - 1 = 0.10
    # close[t+4] = 1400 -> fwd_ret_4h = 1400/1000 - 1 = 0.40
    # close[t+24] = 3400 -> fwd_ret_24h = 3400/1000 - 1 = 2.40
    row0 = panel[0]
    assert abs(row0["fwd_ret_1h"] - 0.10) < 1e-6
    assert abs(row0["fwd_ret_4h"] - 0.40) < 1e-6
    assert abs(row0["fwd_ret_24h"] - 2.40) < 1e-6

    # Hàng cuối cùng (i = 29): không có tương lai -> fwd_ret_24h = None
    assert panel[-1]["fwd_ret_24h"] is None
    assert panel[-1]["fwd_ret_4h"] is None
    assert panel[-1]["fwd_ret_1h"] is None


def test_8_non_leakage_truncation():
    """Bài test cắt cụt không rò rỉ: dựng toàn chuỗi vs dựng chuỗi cắt tại k.

    Chín đặc trưng của hàng k phải GIỐNG HỆT ở hai lần dựng!
    """
    start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    n_hours = 50

    bars = [_make_bar(start + timedelta(hours=i), 40000.0 + i * 10) for i in range(n_hours)]
    funding = [(start + timedelta(hours=8 * i), 0.0001 + (i % 3) * 0.0001) for i in range(10)]
    metrics = []
    for i in range(n_hours * 12):
        m_ts = start + timedelta(minutes=5 * i)
        metrics.append({
            "ts": m_ts,
            "sum_open_interest": 50000.0 + i,
            "count_long_short_ratio": 1.2 + (i % 5) * 0.1,
            "sum_toptrader_long_short_ratio": 1.1 + (i % 4) * 0.1,
            "sum_taker_long_short_vol_ratio": 1.0 + (i % 3) * 0.1,
        })
    orderflow = []
    for i in range(n_hours):
        of_ts = start + timedelta(hours=i)
        orderflow.append({
            "ts": of_ts,
            "taker_buy_volume": 60.0 + i,
            "taker_sell_volume": 40.0 + i,
            "delta": 20.0,
            "buy_ratio": (60.0 + i) / (100.0 + 2 * i),
            "trade_count": 100,
        })

    # Dựng toàn chuỗi
    full_panel = build_feature_panel(bars, funding, metrics, orderflow)

    # Chọn điểm cắt k = 25
    k = 25
    truncated_bars = bars[: k + 1]
    # Dữ liệu ngoài cũng chỉ đến close_ts của bar k
    cut_ts = truncated_bars[-1].ts + timedelta(hours=1)
    truncated_funding = [f for f in funding if f[0] <= cut_ts]
    truncated_metrics = [m for m in metrics if m["ts"] <= cut_ts]
    truncated_of = [o for o in orderflow if o["ts"] <= truncated_bars[-1].ts]

    trunc_panel = build_feature_panel(truncated_bars, truncated_funding, truncated_metrics, truncated_of)

    feature_keys = [
        "funding_rate",
        "funding_z",
        "oi_chg_3h",
        "oi_chg_24h",
        "long_short_ratio",
        "toptrader_ls_ratio",
        "taker_ls_vol_ratio",
        "delta_norm",
        "cvd_chg_3h",
    ]

    for feat in feature_keys:
        val_full = full_panel[k][feat]
        val_trunc = trunc_panel[k][feat]
        if val_full is None:
            assert val_trunc is None, f"Lệch tại {feat}: full=None, trunc={val_trunc}"
        else:
            assert val_trunc is not None, f"Lệch tại {feat}: full={val_full}, trunc=None"
            assert abs(val_full - val_trunc) < 1e-9, f"Lệch giá trị tại {feat}: {val_full} != {val_trunc}"


def test_9_completed_metric_at_close_ts_is_used():
    """Test 9: Mốc hoàn tất đúng lúc close_ts được dùng: mốc 09:55 với close_ts = 10:00 -> dùng được."""
    ts = datetime(2024, 1, 1, 9, 0, tzinfo=UTC)  # bar 09:00 -> close_ts 10:00
    bar = _make_bar(ts, 40000.0)
    m_955 = {
        "ts": datetime(2024, 1, 1, 9, 55, tzinfo=UTC),
        "sum_open_interest": 50000.0,
        "count_long_short_ratio": 1.75,
        "sum_toptrader_long_short_ratio": 1.45,
        "sum_taker_long_short_vol_ratio": 1.30,
    }
    panel = build_feature_panel([bar], [], [m_955], [])
    assert panel[0]["long_short_ratio"] == 1.75
    assert panel[0]["toptrader_ls_ratio"] == 1.45
    assert panel[0]["taker_ls_vol_ratio"] == 1.30


def test_10_uncompleted_metric_at_close_ts_is_rejected():
    """Test 10: Mốc chưa hoàn tất bị loại: mốc 10:00 với close_ts = 10:00 -> không được dùng; hàng phải lấy 09:55."""
    ts = datetime(2024, 1, 1, 9, 0, tzinfo=UTC)  # bar 09:00 -> close_ts 10:00
    bar = _make_bar(ts, 40000.0)
    m_955 = {
        "ts": datetime(2024, 1, 1, 9, 55, tzinfo=UTC),
        "count_long_short_ratio": 1.75,
    }
    m_1000 = {
        "ts": datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
        "count_long_short_ratio": 9.99,  # Giá trị của mốc tương lai (nhìn trước)
    }
    panel = build_feature_panel([bar], [], [m_955, m_1000], [])
    # Phải lấy mốc 09:55 (1.75), KHÔNG ĐƯỢC lấy mốc 10:00 (9.99)
    assert panel[0]["long_short_ratio"] == 1.75


def test_11_metric_lag_10_minutes():
    """Test 11: metric_lag_minutes = 10 -> mốc muộn nhất dùng được tại close_ts = 10:00 là 09:50."""
    ts = datetime(2024, 1, 1, 9, 0, tzinfo=UTC)  # bar 09:00 -> close_ts 10:00
    bar = _make_bar(ts, 40000.0)
    m_950 = {
        "ts": datetime(2024, 1, 1, 9, 50, tzinfo=UTC),
        "count_long_short_ratio": 1.50,
    }
    m_955 = {
        "ts": datetime(2024, 1, 1, 9, 55, tzinfo=UTC),
        "count_long_short_ratio": 1.75,
    }
    m_1000 = {
        "ts": datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
        "count_long_short_ratio": 9.99,
    }
    # Với metric_lag_minutes = 10: mốc 09:55 và 10:00 bị loại, mốc muộn nhất hợp lệ là 09:50
    panel = build_feature_panel([bar], [], [m_950, m_955, m_1000], [], metric_lag_minutes=10)
    assert panel[0]["long_short_ratio"] == 1.50
