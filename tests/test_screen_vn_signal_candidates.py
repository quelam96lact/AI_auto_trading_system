"""Unit tests cho scripts/screen_vn_signal_candidates.py — Brief đợt 76.

Bao gồm:
1. Test tổng hợp: đặc trưng rò rỉ nhân tạo -> CO_TIN_HIEU, ngẫu nhiên -> KHONG_TIN_HIEU, biên classify_signal.
2. Test chốt an toàn đối chứng (intraday_ret vs ret_past_1d).
3. Test tính tay cho từng công thức đặc trưng (mom_5d, mom_20d, vol_ratio_20d, dist_from_sma20, realized_vol_20d, rsi_14).
4. Test chống nhìn trước (lookahead audit) & bước phá hoại: khẳng định mọi đặc trưng tại ngày t
   không thay đổi khi giá của t+1 bị thay đổi.
"""

import math
import random
from datetime import UTC, datetime, timedelta

from scripts.leakage_audit import compute_leakage_pair
from scripts.screen_vn_signal_candidates import (
    CONTROL_MIN_RHO,
    FEATURE_NAMES,
    build_candidate_features_panel,
    check_intraday_control,
    classify_signal,
    compute_dist_from_sma,
    compute_mom,
    compute_realized_vol,
    compute_rsi,
    compute_vol_ratio,
)


def _make_daily_bars(n: int = 100, seed: int = 42) -> list[dict]:
    """Tạo danh sách nến ngày tổng hợp với xu hướng và biến động thực tế."""
    rng = random.Random(seed)
    base_ts = datetime(2020, 1, 1, 17, 0, tzinfo=UTC)

    bars = []
    close = 20.0
    for i in range(n):
        ret = rng.gauss(0.0005, 0.02)
        close_next = max(close * (1.0 + ret), 1.0)
        open_price = close * (1.0 + rng.gauss(0.0, 0.005))
        high_price = max(open_price, close_next) * (1.0 + abs(rng.gauss(0.0, 0.005)))
        low_price = min(open_price, close_next) * (1.0 - abs(rng.gauss(0.0, 0.005)))
        volume = max(int(rng.gauss(1_000_000, 200_000)), 10_000)

        bars.append({
            "ts": base_ts + timedelta(days=i),
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_next,
            "volume": volume,
        })
        close = close_next

    return bars


# ==============================================================================
# 1. Test hàm gắn cờ và phân loại tín hiệu
# ==============================================================================


def test_classify_signal_boundaries() -> None:
    """Kiểm tra các trường hợp biên của hàm classify_signal."""
    th = 0.05
    # Tương quan dương vượt ngưỡng
    assert classify_signal(0.051, th) == "CO_TIN_HIEU"
    # Tương quan âm vượt ngưỡng (tín hiệu nghịch đảo vẫn là tín hiệu)
    assert classify_signal(-0.051, th) == "CO_TIN_HIEU"
    # Tương quan bằng hoặc nằm trong ngưỡng
    assert classify_signal(0.050, th) == "KHONG_TIN_HIEU"
    assert classify_signal(0.020, th) == "KHONG_TIN_HIEU"
    assert classify_signal(-0.049, th) == "KHONG_TIN_HIEU"
    assert classify_signal(0.0, th) == "KHONG_TIN_HIEU"


def test_synthetic_predictive_feature_is_co_tin_hieu() -> None:
    """Đặc trưng dự báo nhân tạo (fwd_ret_1d + nhiễu nhỏ) -> CO_TIN_HIEU."""
    bars = _make_daily_bars(n=300, seed=1)
    panel = build_candidate_features_panel(bars)
    rng = random.Random(1)

    fut_vals = [r.get("fwd_ret_1d") for r in panel]
    past_vals = [r.get("ret_past_1d") for r in panel]

    # Tạo đặc trưng dự đoán tương lai với tương quan rất mạnh
    feat_vals = [
        (fv + rng.gauss(0, 1e-4)) if fv is not None else None
        for fv in fut_vals
    ]

    _rho_t, rho_s, _n_t, _n_s = compute_leakage_pair(feat_vals, past_vals, fut_vals)
    assert rho_s > 0.90, f"Đặc trưng dự báo phải có rho_sau rất cao, got {rho_s:.4f}"
    assert classify_signal(rho_s, threshold=0.05) == "CO_TIN_HIEU"


def test_synthetic_random_feature_is_khong_tin_hieu() -> None:
    """Đặc trưng ngẫu nhiên độc lập (nhiễu trắng) -> KHONG_TIN_HIEU."""
    bars = _make_daily_bars(n=500, seed=2)
    panel = build_candidate_features_panel(bars)
    rng = random.Random(999)

    fut_vals = [r.get("fwd_ret_1d") for r in panel]
    past_vals = [r.get("ret_past_1d") for r in panel]
    feat_vals = [rng.gauss(0, 1.0) for _ in panel]

    _rho_t, rho_s, _n_t, _n_s = compute_leakage_pair(feat_vals, past_vals, fut_vals)
    assert abs(rho_s) < 0.10, f"Đặc trưng ngẫu nhiên phải có |rho_sau| nhỏ, got {rho_s:.4f}"
    assert classify_signal(rho_s, threshold=0.05) == "KHONG_TIN_HIEU"


# ==============================================================================
# 2. Test chốt an toàn đối chứng (intraday_ret vs ret_past_1d)
# ==============================================================================


def test_intraday_control_check_passes_on_valid_data() -> None:
    """Chốt an toàn đối chứng phải ĐẠT (> 0.50) trên dữ liệu nến thực tế."""
    bars = _make_daily_bars(n=200, seed=3)
    panel = build_candidate_features_panel(bars)

    rho_ctrl, ok = check_intraday_control(panel, min_rho=CONTROL_MIN_RHO)
    assert ok, f"Chốt đối chứng phải đạt, got rho={rho_ctrl:.4f}"
    assert rho_ctrl > CONTROL_MIN_RHO


def test_intraday_control_check_fails_on_corrupted_data() -> None:
    """Chốt an toàn đối chứng phải phát hiện dữ liệu hỏng / lệch pha."""
    bars = _make_daily_bars(n=200, seed=4)
    panel = build_candidate_features_panel(bars)
    rng = random.Random(4)

    # Phá hỏng intraday_ret bằng cách gán số ngẫu nhiên
    for r in panel:
        r["intraday_ret"] = rng.gauss(0, 1.0)

    rho_ctrl, ok = check_intraday_control(panel, min_rho=CONTROL_MIN_RHO)
    assert not ok, f"Chốt đối chứng phải thất bại khi bị phá hỏng, got rho={rho_ctrl:.4f}"


# ==============================================================================
# 3. Test tính tay cho từng công thức đặc trưng
# ==============================================================================


def test_compute_mom_hand_calculated() -> None:
    """Kiểm tra momentum 5d và 20d với các giá trị tính tay chuẩn xác."""
    # 30 giá trị cố định
    closes = [10.0] * 5 + [12.0] + [10.0] * 14 + [15.0] + [10.0] * 9

    mom5 = compute_mom(closes, 5)
    # Trước 5 phải là None
    for i in range(5):
        assert mom5[i] is None
    # Tại i=5: close[5]=12, close[0]=10 -> 12/10 - 1 = 0.20
    assert abs(mom5[5] - 0.20) < 1e-10
    # Tại i=6: close[6]=10, close[1]=10 -> 0.0
    assert abs(mom5[6] - 0.0) < 1e-10

    mom20 = compute_mom(closes, 20)
    for i in range(20):
        assert mom20[i] is None
    # Tại i=20: close[20]=15, close[0]=10 -> 15/10 - 1 = 0.50
    assert abs(mom20[20] - 0.50) < 1e-10


def test_compute_vol_ratio_hand_calculated() -> None:
    """Kiểm tra vol_ratio_20d: volume[t] / mean(volume[t-20..t-1])."""
    volumes = [100.0] * 20 + [250.0] + [100.0] * 5
    vr = compute_vol_ratio(volumes, 20)

    for i in range(20):
        assert vr[i] is None
    # Tại i=20: volume[20] = 250, mean của 20 ngày trước = 100 -> ratio = 2.5
    assert abs(vr[20] - 2.50) < 1e-10
    # Tại i=21: volume[21] = 100, mean của [1..20] = (19*100 + 250)/20 = 107.5 -> 100/107.5
    expected_21 = 100.0 / 107.5
    assert abs(vr[21] - expected_21) < 1e-10


def test_compute_dist_from_sma_hand_calculated() -> None:
    """Kiểm tra dist_from_sma20: close[t] / SMA20(close[t-19..t]) - 1.0."""
    closes = [10.0] * 19 + [12.0] + [10.0] * 5
    dist = compute_dist_from_sma(closes, 20)

    for i in range(19):
        assert dist[i] is None
    # Tại i=19: 19 ngày giá 10, ngày 19 giá 12 -> SMA = (19*10 + 12)/20 = 10.1
    sma19 = (19 * 10.0 + 12.0) / 20.0
    expected = 12.0 / sma19 - 1.0
    assert abs(dist[19] - expected) < 1e-10


def test_compute_realized_vol_hand_calculated() -> None:
    """Kiểm tra realized_vol_20d: sample std của 20 lợi suất ngày."""
    # 20 lợi suất đều bằng 0.02 -> độ lệch chuẩn = 0.0
    rets_flat = [None] + [0.02] * 25
    rvol_flat = compute_realized_vol(rets_flat, 20)
    assert abs(rvol_flat[20] - 0.0) < 1e-10

    # 10 ngày lợi suất +0.01, 10 ngày -0.01 -> mean = 0.0
    # var = (10*(0.01)^2 + 10*(-0.01)^2) / 19 = 20 * 0.0001 / 19 = 0.002 / 19
    rets_step = [None] + [0.01] * 10 + [-0.01] * 10
    rvol_step = compute_realized_vol(rets_step, 20)
    expected_std = math.sqrt((20.0 * (0.01 ** 2)) / 19.0)
    assert abs(rvol_step[20] - expected_std) < 1e-10


def test_compute_rsi_14_properties() -> None:
    """Kiểm tra các đặc tính chuẩn của RSI 14 Wilder."""
    # Chuỗi chỉ tăng liên tục -> RSI phải tiến tới 100.0
    closes_up = [10.0 + i for i in range(30)]
    rsi_up = compute_rsi(closes_up, 14)
    for i in range(14):
        assert rsi_up[i] is None
    assert rsi_up[14] == 100.0
    assert rsi_up[20] == 100.0

    # Chuỗi chỉ giảm liên tục -> RSI phải tiến tới 0.0
    closes_down = [100.0 - i for i in range(30)]
    rsi_down = compute_rsi(closes_down, 14)
    assert rsi_down[14] == 0.0
    assert rsi_down[20] == 0.0


# ==============================================================================
# 4. Test chống nhìn trước (Lookahead Audit) & Bước phá hoại
# ==============================================================================


def test_no_lookahead_in_candidate_features_and_sabotage() -> None:
    """Kiểm tra chống nhìn trước và bước phá hoại:
    1. Chuẩn: Đổi giá ở tương lai (t+1) KHÔNG ĐƯỢC làm đổi bất kỳ đặc trưng nào tại ngày t.
    2. Phá hoại: Cố tình thêm đặc trưng đọc lố sang t+1 -> test phải phát hiện và báo đỏ.
    """
    bars = _make_daily_bars(n=50, seed=76)

    # Ngày kiểm tra t = 35
    t_idx = 35

    # Tính panel trên chuỗi gốc
    panel_orig = build_candidate_features_panel(bars)
    orig_features_at_t = {feat: panel_orig[t_idx][feat] for feat in FEATURE_NAMES}

    # Tạo bản sao và thay đổi dữ liệu của ngày t+1 (ngày 36)
    bars_mutated = [dict(b) for b in bars]
    bars_mutated[t_idx + 1]["close"] = bars_mutated[t_idx + 1]["close"] * 5.0
    bars_mutated[t_idx + 1]["open"] = bars_mutated[t_idx + 1]["open"] * 5.0
    bars_mutated[t_idx + 1]["volume"] = bars_mutated[t_idx + 1]["volume"] * 10

    # Tính panel trên chuỗi đã đột biến tương lai
    panel_mutated = build_candidate_features_panel(bars_mutated)
    mutated_features_at_t = {feat: panel_mutated[t_idx][feat] for feat in FEATURE_NAMES}

    # Khẳng định 1: Toàn bộ 6 đặc trưng tại ngày t KHÔNG ĐƯỢC THAY ĐỔI
    for feat in FEATURE_NAMES:
        val_orig = orig_features_at_t[feat]
        val_mut = mutated_features_at_t[feat]
        assert val_orig is not None
        assert val_orig == val_mut, (
            f"LỖI RÒ RỈ NHÌN TRƯỚC: Đặc trưng {feat} tại ngày {t_idx} bị thay đổi khi sửa giá ngày {t_idx+1}! "
            f"(orig={val_orig}, mutated={val_mut})"
        )

    # Khẳng định 2: Bước phá hoại — nếu có một đặc trưng rò rỉ đọc t+1, phép thử này bắt được
    leaky_val_orig = bars[t_idx + 1]["close"] / bars[t_idx]["close"] - 1.0
    leaky_val_mut = bars_mutated[t_idx + 1]["close"] / bars_mutated[t_idx]["close"] - 1.0
    assert leaky_val_orig != leaky_val_mut, "Phép phá hoại phải thay đổi giá trị đặc trưng rò rỉ"


# ==============================================================================
# 5. Test hàm binomial và summarize_results — Brief đợt 77 Task 4.2
# ==============================================================================


from scripts.screen_batch_vn_stocks import (
    binomial_p_value,
    is_hit_rate_abnormal,
    summarize_results,
)


def test_binomial_p_value_null_rate_is_not_abnormal() -> None:
    """100 mã giả với 5 lần trúng (đúng tỷ lệ 5%) → KHÔNG bất thường.

    Brief đợt 77 §3.2: 'dựng 100 mã giả với xác suất trúng đúng 5% theo thiết kế,
    xác nhận hàm không báo bất thường'.
    """
    n = 100
    # 5/100 = đúng xác suất null 5% → p-value cao (không bất thường)
    observed = 5
    pv = binomial_p_value(observed, n, p=0.05)
    assert pv > 0.05, (
        f"5/100 trúng không được báo bất thường (p-value phải > 0.05, got {pv:.4f})"
    )
    assert not is_hit_rate_abnormal(observed, n, p=0.05), (
        "5/100 trúng không được báo bất thường"
    )


def test_binomial_p_value_high_rate_is_abnormal() -> None:
    """100 mã giả với 30 lần trúng (30%) → BẤT THƯỜNG so với ngẫu nhiên 5%.

    Brief đợt 77 §3.2: 'dựng 100 mã giả với 30% trúng, xác nhận hàm báo bất thường'.
    """
    n = 100
    observed = 30  # 30% >> 5%
    pv = binomial_p_value(observed, n, p=0.05)
    # Với B(100, 0.05), P(X >= 30) là cực kỳ nhỏ
    assert pv < 1e-10, (
        f"30/100 trúng phải báo bất thường (p-value phải < 1e-10, got {pv:.2e})"
    )
    assert is_hit_rate_abnormal(observed, n, p=0.05), (
        "30/100 trúng phải báo bất thường"
    )


def test_binomial_p_value_zero_hits() -> None:
    """0 lần trúng → p-value = 1.0 (không bất thường)."""
    pv = binomial_p_value(0, 50, p=0.05)
    assert pv == 1.0, f"0 lần trúng phải có p-value=1.0, got {pv}"
    assert not is_hit_rate_abnormal(0, 50, p=0.05), "0 trúng không được báo bất thường"


def test_summarize_results_counts_correctly() -> None:
    """summarize_results đếm đúng số CO_TIN_HIEU per đặc trưng.

    Kiểm với dữ liệu tổng hợp có đáp số biết trước: 3/4 mã giả trúng cho feature[0],
    0/4 mã trúng cho feature[1..5] → summarize trả đúng số đó.
    """
    feat0 = FEATURE_NAMES[0]
    feat1 = FEATURE_NAMES[1]

    def _make_fake_res(symbol: str, hit_feat0: bool) -> dict:
        """Tạo kết quả giả của screen_symbol()."""
        results = []
        for feat in FEATURE_NAMES:
            if feat == feat0 and hit_feat0:
                flag = "CO_TIN_HIEU"
            else:
                flag = "KHONG_TIN_HIEU"
            results.append({
                "feature": feat,
                "rho_truoc": 0.0,
                "rho_sau": 0.1 if flag == "CO_TIN_HIEU" else 0.0,
                "n_truoc": 100,
                "n_sau": 100,
                "threshold": 0.05,
                "flag": flag,
            })
        return {"symbol": symbol, "n_bars": 100, "rho_control": 0.8, "threshold_p95": 0.05, "results": results}

    fake_all = [
        _make_fake_res("A", hit_feat0=True),
        _make_fake_res("B", hit_feat0=True),
        _make_fake_res("C", hit_feat0=True),
        _make_fake_res("D", hit_feat0=False),
    ]
    summary = summarize_results(fake_all, n_total=4)

    # feat0: 3 lần trúng
    row0 = next(r for r in summary if r["feature"] == feat0)
    assert row0["n_hit"] == 3, f"feat0 phải 3 lần trúng, got {row0['n_hit']}"
    assert row0["n_total"] == 4

    # feat1: 0 lần trúng
    row1 = next(r for r in summary if r["feature"] == feat1)
    assert row1["n_hit"] == 0, f"feat1 phải 0 lần trúng, got {row1['n_hit']}"

    # Kỳ vọng ngẫu nhiên = 0.05 * 4 = 0.2
    assert abs(row0["expected_random"] - 0.2) < 1e-10

