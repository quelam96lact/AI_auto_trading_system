"""Tests cho scripts/event_study_module_c.py (Brief đợt 42 Task 4 §4.4).

5 bài kiểm chứng:
1. Chuỗi dựng tay có đúng một giờ thoả cả 6 vế -> phát hiện đúng 1 sự kiện, đúng vị trí.
2. Tắt từng vế một (vi phạm đúng vế đó) -> không có sự kiện (6 bài kiểm tra).
3. Đối chứng dương: chuỗi tổng hợp trong đó mọi sự kiện được theo sau bởi mức tăng mạnh -> vượt P95.
4. Đối chứng âm: chuỗi bước ngẫu nhiên, hạt giống cố định -> không vượt P95.
5. Chạy hai lần cùng hạt giống -> kết quả giống hệt 100%.
"""

import random
from datetime import UTC, datetime, timedelta

from scripts.event_study_module_c import (
    check_module_c_conditions,
    run_event_study,
)
from trading.models import Bar


def _make_bar(ts: datetime, close: float, symbol: str = "BTCUSDT") -> Bar:
    return Bar(symbol=symbol, ts=ts, open=close, high=close * 1.001, low=close * 0.999, close=close, volume=1000)


def _build_synthetic_dataset(
    n_hours: int = 100,
    start_ts: datetime = datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
    base_price: float = 40000.0,
):
    """Tạo bộ dữ liệu chuỗi nến, funding, metrics, orderflow cơ bản dài n_hours."""
    bars = []
    orderflow = []
    metrics = []
    funding = []

    for i in range(n_hours):
        t = start_ts + timedelta(hours=i)
        bars.append(_make_bar(t, base_price + i * 10))
        # Orderflow mặc định: delta âm nhẹ, cvd đi ngang
        orderflow.append({
            "ts": t,
            "taker_buy_volume": 40.0,
            "taker_sell_volume": 60.0,
            "delta": -20.0,
            "buy_ratio": 0.4,
            "trade_count": 100,
        })
        # Funding 8h/lần: 300 lần để funding_z đủ 90 ngày
        if i % 8 == 0:
            funding.append((t, 0.0001))

        # Metrics 5m
        for m in range(12):
            mt = t + timedelta(minutes=5 * m)
            metrics.append({
                "ts": mt,
                "sum_open_interest": 50000.0,
                "count_long_short_ratio": 1.5,
                "sum_toptrader_long_short_ratio": 1.2,
                "sum_taker_long_short_vol_ratio": 1.1,
            })

    # Thêm funding quá khứ để đủ 260 lần settle (>90 ngày)
    past_funding = [
        (start_ts - timedelta(hours=8 * (300 - i)), 0.0001 if i % 2 == 0 else 0.0002)
        for i in range(300)
    ]
    funding = past_funding + funding

    return bars, funding, metrics, orderflow


def test_1_single_event_detected_at_exact_position():
    """1. Chuỗi dựng tay có đúng một giờ thoả cả sáu vế -> phát hiện đúng một sự kiện, đúng vị trí."""
    n_hours = 120
    start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars, funding, metrics, orderflow = _build_synthetic_dataset(n_hours=n_hours, start_ts=start)

    # Đặt sự kiện tại k = 80 (sau khi EMA20, EMA50 đã warmup hoàn toàn)
    k = 80
    # Đẩy giá tăng dần để EMA20 > EMA50 và EMA50_t > EMA50_{t-3}
    for idx in range(50, n_hours):
        bars[idx] = _make_bar(bars[idx].ts, 40000.0 + (idx - 50) * 100.0)

    # Tại k:
    # 1. Xu hướng: close > EMA50, EMA20 > EMA50, EMA50 tăng
    # 2. Funding: funding_z < 1.0 (funding rate bình thường quanh mean)
    # 3. OI giảm mạnh: oi_chg_3h <= -0.015 (giảm 3% so với 3h trước)
    # Mốc k có close_ts = bar[k].ts + 1h
    close_ts_k = bars[k].ts + timedelta(hours=1)
    close_ts_k_minus_3h = close_ts_k - timedelta(hours=3)

    # Tìm metric mốc 5m trước close_ts_k (tức close_ts_k - 5m)
    target_metric_ts_now = close_ts_k - timedelta(minutes=5)
    target_metric_ts_prev3 = close_ts_k_minus_3h - timedelta(minutes=5)

    for m in metrics:
        if m["ts"] == target_metric_ts_now:
            m["sum_open_interest"] = 48000.0  # Giảm từ 50000 -> 48000 (-4%)
        elif m["ts"] == target_metric_ts_prev3:
            m["sum_open_interest"] = 50000.0

    # 4. Confirm: close > EMA20 (đã có từ việc giá tăng liên tục)
    # 5. Orderflow: delta_norm > 0 và cvd_3h_t > cvd_3h_{t-3}
    orderflow[k]["taker_buy_volume"] = 80.0
    orderflow[k]["taker_sell_volume"] = 20.0
    orderflow[k]["delta"] = 60.0  # delta_norm = 60 / 100 = +0.6 > 0

    res = run_event_study(
        bars, funding, metrics, orderflow,
        is_start=bars[60].ts,
        is_end=bars[110].ts,
        n_permutations=10,
    )

    assert res["n_events"] == 1
    assert res["events"][0]["ts"] == bars[k].ts


def test_2_disable_each_condition_one_by_one():
    """2. Tắt từng vế một (vi phạm đúng vế đó) -> không có sự kiện."""
    # Test trực tiếp qua hàm check_module_c_conditions
    bar = _make_bar(datetime(2024, 1, 1, 12, 0, tzinfo=UTC), 50000.0)

    # Trạng thái cơ sở thoả mãn cả 6 vế
    base_feat = {
        "funding_z": 0.5,       # < 1.0
        "oi_chg_3h": -0.02,     # <= -0.015
        "delta_norm": 0.3,      # > 0
        "cvd_chg_3h": 0.25,     # > cvd_3h_prev3 (0.10)
    }
    ema20_now = 49000.0         # close (50k) > ema20 (49k)
    ema50_now = 48000.0         # ema20 (49k) > ema50 (48k), close > ema50
    ema50_prev3 = 47500.0       # ema50_now > ema50_prev3
    cvd_prev3 = 0.10

    # Baseline: thoả mãn
    base_res = check_module_c_conditions(bar, base_feat, ema20_now, ema50_now, ema50_prev3, cvd_prev3)
    assert base_res["all_combined"] is True

    # Vế 1a vi phạm: close <= EMA50
    r1a = check_module_c_conditions(_make_bar(bar.ts, 47000.0), base_feat, ema20_now, ema50_now, ema50_prev3, cvd_prev3)
    assert r1a["all_combined"] is False

    # Vế 1b vi phạm: EMA20 <= EMA50
    r1b = check_module_c_conditions(bar, base_feat, 47000.0, ema50_now, ema50_prev3, cvd_prev3)
    assert r1b["all_combined"] is False

    # Vế 1c vi phạm: EMA50_t <= EMA50_{t-3}
    r1c = check_module_c_conditions(bar, base_feat, ema20_now, ema50_now, 48500.0, cvd_prev3)
    assert r1c["all_combined"] is False

    # Vế 2 vi phạm: funding_z >= +1.0
    feat_v2 = dict(base_feat, funding_z=1.2)
    r2 = check_module_c_conditions(bar, feat_v2, ema20_now, ema50_now, ema50_prev3, cvd_prev3)
    assert r2["funding"] is False
    assert r2["all_combined"] is False

    # Vế 3 vi phạm: oi_chg_3h > -0.015 (ví dụ 0.0)
    feat_v3 = dict(base_feat, oi_chg_3h=-0.010)
    r3 = check_module_c_conditions(bar, feat_v3, ema20_now, ema50_now, ema50_prev3, cvd_prev3)
    assert r3["oi"] is False
    assert r3["all_combined"] is False

    # Vế 4 vi phạm: close <= EMA20 (nến xác nhận)
    r4 = check_module_c_conditions(_make_bar(bar.ts, 48500.0), base_feat, 49000.0, 48000.0, ema50_prev3, cvd_prev3)
    assert r4["confirm"] is False
    assert r4["all_combined"] is False

    # Vế 5a vi phạm: delta_norm <= 0
    feat_v5a = dict(base_feat, delta_norm=-0.05)
    r5a = check_module_c_conditions(bar, feat_v5a, ema20_now, ema50_now, ema50_prev3, cvd_prev3)
    assert r5a["orderflow"] is False
    assert r5a["all_combined"] is False

    # Vế 5b vi phạm: cvd_chg_3h <= cvd_3h_prev3
    feat_v5b = dict(base_feat, cvd_chg_3h=0.05)
    r5b = check_module_c_conditions(bar, feat_v5b, ema20_now, ema50_now, ema50_prev3, cvd_prev3)
    assert r5b["orderflow"] is False
    assert r5b["all_combined"] is False


def test_3_positive_control():
    """3. Đối chứng dương: chuỗi tổng hợp trong đó mọi sự kiện được theo sau bởi mức tăng mạnh -> vượt P95 áp đảo."""
    n_hours = 360
    start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars, funding, metrics, orderflow = _build_synthetic_dataset(n_hours=n_hours, start_ts=start)

    # Tạo 35 sự kiện cách nhau 7 giờ (để t-3h không dính vào bar t của sự kiện trước)
    event_indices = [70 + i * 7 for i in range(35)]
    event_set = set(event_indices)

    # 1. Dựng giá tăng đơn điệu: các nến bình thường tăng 10, ngay sau sự kiện nhảy vọt +5%
    p = 40000.0
    for idx in range(n_hours):
        t = start + timedelta(hours=idx)
        if (idx - 1) in event_set:
            p += p * 0.05
        else:
            p += 10.0
        bars[idx] = _make_bar(t, p)

    # 2. Cài đặt các điều kiện tại từng event
    oi_event_ts = set()
    for ev_i in event_indices:
        t_ev = bars[ev_i].ts
        close_ts = t_ev + timedelta(hours=1)
        m_ts_now = close_ts - timedelta(minutes=5)
        oi_event_ts.add(m_ts_now)

        # Orderflow tại event
        orderflow[ev_i]["taker_buy_volume"] = 80.0
        orderflow[ev_i]["taker_sell_volume"] = 20.0
        orderflow[ev_i]["delta"] = 60.0

    for m in metrics:
        if m["ts"] in oi_event_ts:
            m["sum_open_interest"] = 48000.0  # Giảm 4% so với 50000
        else:
            m["sum_open_interest"] = 50000.0

    res = run_event_study(
        bars, funding, metrics, orderflow,
        is_start=bars[65].ts,
        is_end=bars[320].ts,
        n_permutations=100,
        seed=42,
    )

    assert res["n_events"] >= 30
    assert res["details_horizons"]["1h"]["mean_event"] > 0.03
    assert res["details_horizons"]["1h"]["above_p95"] is True


def test_4_negative_control():
    """4. Đối chứng âm: chuỗi bước ngẫu nhiên, hạt giống cố định -> không vượt."""
    rng = random.Random(42)
    n_hours = 250
    start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars = []
    p = 40000.0
    for i in range(n_hours):
        t = start + timedelta(hours=i)
        p += rng.gauss(0, 10.0)
        bars.append(_make_bar(t, p))

    _, funding, metrics, orderflow = _build_synthetic_dataset(n_hours=n_hours, start_ts=start)

    res = run_event_study(
        bars, funding, metrics, orderflow,
        is_start=bars[60].ts,
        is_end=bars[200].ts,
        n_permutations=100,
        seed=42,
    )

    # Trong chuỗi ngẫu nhiên không có setup, số sự kiện hoặc < 30 hoặc không vượt null p95
    assert res["overall_pass"] is False


def test_5_deterministic_reproducibility():
    """5. Chạy hai lần cùng hạt giống -> kết quả giống hệt 100%."""
    n_hours = 120
    start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    bars, funding, metrics, orderflow = _build_synthetic_dataset(n_hours=n_hours, start_ts=start)

    res1 = run_event_study(
        bars, funding, metrics, orderflow,
        is_start=bars[60].ts,
        is_end=bars[110].ts,
        n_permutations=50,
        seed=12345,
    )
    res2 = run_event_study(
        bars, funding, metrics, orderflow,
        is_start=bars[60].ts,
        is_end=bars[110].ts,
        n_permutations=50,
        seed=12345,
    )

    assert res1["n_events"] == res2["n_events"]
    for h in ("1h", "4h", "24h"):
        assert abs(res1["null_p95"][h] - res2["null_p95"][h]) < 1e-12
        assert abs(res1["event_mean"][h] - res2["event_mean"][h]) < 1e-12
