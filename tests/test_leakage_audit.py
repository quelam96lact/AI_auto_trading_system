"""Tests cho scripts/leakage_audit.py — Brief đợt 71.

4 test cases:
1. Đặc trưng rò rỉ nhân tạo (feature = future_ret + noise) → NGHI_VAN.
2. Đặc trưng sạch nhân tạo (feature = past_ret + noise) → SACH.
3. Đặc trưng vô nghĩa (random, seed cố định) → SACH, cả hai rho gần 0.
4. Chốt an toàn hỏng: delta_norm không mạnh dương → RuntimeError.
"""

import random

import pytest

from scripts.leakage_audit import (
    CONTROL_MIN_RHO_TRUOC,
    add_past_return_to_panel,
    align_raw_series_to_returns,
    check_control_variable,
    classify_leakage,
    compute_leakage_pair,
    run_leakage_audit,
)


def _make_panel(n: int = 500, seed: int = 0) -> list[dict]:
    """Dựng panel tổng hợp với n hàng có close, ts, fwd_ret_1h, ret_past_1h và delta_norm mạnh."""
    from datetime import UTC, datetime, timedelta

    rng = random.Random(seed)
    base_ts = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)

    rows = []
    close = 50_000.0
    for i in range(n + 1):  # +1 để tính ret_past_1h cho hàng đầu
        close *= 1.0 + rng.gauss(0, 0.005)
        rows.append({"_close": close, "ts": base_ts + timedelta(hours=i)})

    # Tính ret giữa các nến liền nhau
    result = []
    for i in range(1, n + 1):
        prev_close = rows[i - 1]["_close"]
        cur_close = rows[i]["_close"]
        # Nếu còn hàng tiếp theo
        if i < n:
            next_close = rows[i + 1]["_close"]
            fwd_ret = (next_close / cur_close) - 1.0
        else:
            fwd_ret = None
        past_ret = (cur_close / prev_close) - 1.0

        # delta_norm mạnh tương quan với past_ret (áp lực mua ≈ lợi suất cùng kỳ)
        delta_norm = past_ret + rng.gauss(0, 0.001)

        result.append({
            "ts": rows[i]["ts"],
            "close": cur_close,
            "fwd_ret_1h": fwd_ret,
            "ret_past_1h": past_ret,
            "delta_norm": delta_norm,
        })
    return result


def test_leaky_feature_flagged_as_nghi_van() -> None:
    """Đặc trưng rò rỉ nhân tạo: feature ≈ future_ret → NGHI_VAN."""
    panel = _make_panel(n=500, seed=1)
    rng = random.Random(1)

    # Gắn feature rò rỉ: chính là fwd_ret_1h + nhiễu nhỏ
    feat_vals = []
    past_vals = []
    fut_vals = []
    for row in panel:
        fwd = row.get("fwd_ret_1h")
        if fwd is None:
            feat_vals.append(None)
        else:
            feat_vals.append(fwd + rng.gauss(0, 1e-5))
        past_vals.append(row.get("ret_past_1h"))
        fut_vals.append(row.get("fwd_ret_1h"))

    rho_truoc, rho_sau, _n_truoc, _n_sau = compute_leakage_pair(feat_vals, past_vals, fut_vals)

    # rho_sau phải cực cao (≈ 1), rho_truoc phải gần 0 hoặc nhỏ hơn
    assert rho_sau > 0.9, f"Feature ro ri phai co rho_sau cao, got {rho_sau:.4f}"
    assert rho_sau > rho_truoc, "Feature ro ri phai co rho_sau > rho_truoc"

    # Ngưỡng nhỏ để test gắn cờ (trong thực tế ngưỡng ≈ 0.05–0.10)
    threshold = 0.05
    flag = classify_leakage(rho_truoc, rho_sau, threshold)
    assert flag == "NGHI_VAN", f"Ky vong NGHI_VAN, got {flag!r}"


def test_clean_feature_flagged_as_sach() -> None:
    """Đặc trưng sạch nhân tạo: feature ≈ past_ret → SACH."""
    panel = _make_panel(n=500, seed=2)
    rng = random.Random(2)

    feat_vals = []
    past_vals = []
    fut_vals = []
    for row in panel:
        past = row.get("ret_past_1h")
        if past is None:
            feat_vals.append(None)
        else:
            feat_vals.append(past + rng.gauss(0, 1e-5))
        past_vals.append(row.get("ret_past_1h"))
        fut_vals.append(row.get("fwd_ret_1h"))

    rho_truoc, rho_sau, _n_truoc, _n_sau = compute_leakage_pair(feat_vals, past_vals, fut_vals)

    # rho_truoc phải cực cao (≈ 1), rho_sau nhỏ (thị trường không có autocorr mạnh)
    assert rho_truoc > 0.9, f"Feature sach phai co rho_truoc cao, got {rho_truoc:.4f}"

    # Điều kiện NGHI_VAN là rho_sau > rho_truoc → không thoả → SACH
    threshold = 0.05
    flag = classify_leakage(rho_truoc, rho_sau, threshold)
    assert flag == "SACH", f"Ky vong SACH, got {flag!r}"


def test_random_feature_is_sach_with_small_rho() -> None:
    """Đặc trưng vô nghĩa (random seed cố định) → SACH, cả hai rho gần 0."""
    panel = _make_panel(n=500, seed=3)
    rng = random.Random(99)  # seed khác để tạo noise độc lập

    feat_vals = [rng.gauss(0, 1.0) for _ in panel]
    past_vals = [row.get("ret_past_1h") for row in panel]
    fut_vals = [row.get("fwd_ret_1h") for row in panel]

    rho_truoc, rho_sau, _n_truoc, _n_sau = compute_leakage_pair(feat_vals, past_vals, fut_vals)

    # Cả hai rho phải gần 0 (|rho| < 0.15 với n=500 là hợp lý)
    assert abs(rho_truoc) < 0.15, f"Random feature: rho_truoc phai gan 0, got {rho_truoc:.4f}"
    assert abs(rho_sau) < 0.15, f"Random feature: rho_sau phai gan 0, got {rho_sau:.4f}"

    # Ngưỡng thực tế, không cần rho_sau > rho_truoc với biên độ lớn → SACH
    threshold = 0.05
    flag = classify_leakage(rho_truoc, rho_sau, threshold)
    assert flag == "SACH", f"Random feature phai la SACH, got {flag!r}"


def test_safety_check_fails_when_control_broken() -> None:
    """Chốt an toàn: nếu delta_norm không cho rho_truoc mạnh dương → RuntimeError.

    Mô phỏng tình huống: delta_norm bị thay bằng random noise → phép đo hỏng.
    """
    panel = _make_panel(n=200, seed=4)
    rng = random.Random(4)

    # Phá delta_norm: thay bằng nhiễu ngẫu nhiên
    broken_panel = []
    for row in panel:
        rc = dict(row)
        rc["delta_norm"] = rng.gauss(0, 1.0)  # không còn tương quan với past_ret
        broken_panel.append(rc)

    # check_control_variable phải trả về ok=False
    rho_ctrl, ok = check_control_variable(broken_panel)
    assert not ok, (
        f"Chot an toan phai phat hien delta_norm hong (rho={rho_ctrl:.4f} <= {CONTROL_MIN_RHO_TRUOC})"
    )

    # run_leakage_audit phải raise RuntimeError
    with pytest.raises(RuntimeError, match="CHOT AN TOAN THAT BAI"):
        run_leakage_audit(broken_panel, n_permutations=10)


def test_classify_leakage_edge_cases() -> None:
    """Unit test cho hàm classify_leakage với các trường hợp biên."""
    # rho_sau > rho_truoc VÀ |rho_sau| > threshold → NGHI_VAN
    assert classify_leakage(0.05, 0.20, 0.10) == "NGHI_VAN"

    # rho_sau > rho_truoc NHƯNG |rho_sau| <= threshold → SACH
    assert classify_leakage(0.05, 0.08, 0.10) == "SACH"

    # rho_sau <= rho_truoc dù |rho_sau| lớn → SACH (feature biết quá khứ nhiều hơn tương lai)
    assert classify_leakage(0.80, 0.60, 0.10) == "SACH"

    # Cả hai âm, rho_sau < rho_truoc (bởi vì rho_sau âm hơn) → SACH
    assert classify_leakage(-0.10, -0.30, 0.10) == "SACH"

    # rho_sau dương cao, rho_truoc âm → rho_sau > rho_truoc VÀ |rho_sau| > threshold → NGHI_VAN
    assert classify_leakage(-0.05, 0.20, 0.10) == "NGHI_VAN"


def test_add_past_return_to_panel() -> None:
    """Kiểm tra hàm add_past_return_to_panel tính ret_past_1h đúng."""
    from datetime import UTC, datetime, timedelta

    base = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    raw_panel = [
        {"ts": base + timedelta(hours=i), "close": 100.0 * (1.01 ** i), "fwd_ret_1h": None}
        for i in range(5)
    ]

    enriched = add_past_return_to_panel(raw_panel)

    # Hàng đầu không có nến trước → None
    assert enriched[0]["ret_past_1h"] is None

    # Hàng 1: close[1]/close[0] - 1
    expected = (raw_panel[1]["close"] / raw_panel[0]["close"]) - 1.0
    assert abs(enriched[1]["ret_past_1h"] - expected) < 1e-10

    # Hàng 2: close[2]/close[1] - 1
    expected2 = (raw_panel[2]["close"] / raw_panel[1]["close"]) - 1.0
    assert abs(enriched[2]["ret_past_1h"] - expected2) < 1e-10


def test_align_raw_series_to_returns() -> None:
    """Kiểm tra hàm align_raw_series_to_returns căn giờ T với lợi suất quá khứ/tương lai."""
    from datetime import UTC, datetime, timedelta

    base = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    # close_by_t[T]: giá đóng tại T
    close_by_t = {base + timedelta(hours=i): 100.0 * (1.02 ** i) for i in range(5)}
    raw_series = {"raw_metric": {base + timedelta(hours=i): float(i * 10) for i in range(5)}}

    rows = align_raw_series_to_returns(close_by_t, raw_series)

    # Hàng 0: không có T-1h -> ret_past = None
    assert rows[0]["ret_past_1h"] is None
    assert abs(rows[0]["fwd_ret_1h"] - 0.02) < 1e-10
    assert rows[0]["raw_metric"] == 0.0

    # Hàng 1: có cả T-1h và T+1h
    assert abs(rows[1]["ret_past_1h"] - 0.02) < 1e-10
    assert abs(rows[1]["fwd_ret_1h"] - 0.02) < 1e-10
    assert rows[1]["raw_metric"] == 10.0

    # Hàng cuối: không có T+1h -> fwd_ret = None
    assert abs(rows[-1]["ret_past_1h"] - 0.02) < 1e-10
    assert rows[-1]["fwd_ret_1h"] is None
    assert rows[-1]["raw_metric"] == 40.0


def test_raw_mode_control_variable_delta() -> None:
    """Kiểm tra chốt an toàn hoạt động với biến đối chứng 'delta' trong mode raw."""
    panel = _make_panel(n=200, seed=10)
    # Đổi tên delta_norm -> delta
    raw_rows = []
    for r in panel:
        row = dict(r)
        row["delta"] = row.pop("delta_norm")
        raw_rows.append(row)

    # Chốt an toàn phải nhận diện 'delta' và pass
    rho_ctrl, ok = check_control_variable(raw_rows, control_feature="delta")
    assert ok, f"delta hop le phai dat chot an toan, got rho={rho_ctrl:.4f}"
    assert rho_ctrl > CONTROL_MIN_RHO_TRUOC

    # Khi delta bị hỏng -> raise RuntimeError
    rng = random.Random(11)
    broken_rows = [dict(r, delta=rng.gauss(0, 1.0)) for r in raw_rows]
    with pytest.raises(RuntimeError, match="CHOT AN TOAN THAT BAI"):
        run_leakage_audit(broken_rows, feature_names=["delta"], control_feature="delta", n_permutations=10)


def test_dual_input_paths_produce_identical_correlations() -> None:
    """Brief đợt 72 Task 3.3: Cùng một chuỗi dữ liệu đưa qua cả hai đường vào
    (cột thô và feature panel) phải ra cùng rho_truoc và rho_sau.
    """
    from datetime import UTC, datetime, timedelta

    from trading.feature_panel import build_feature_panel
    from trading.models import Bar

    rng = random.Random(72)
    base = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    n_hours = 120

    klines = []
    metrics = []
    orderflow = []

    close = 40_000.0
    for i in range(n_hours):
        t_open = base + timedelta(hours=i)
        t_close = t_open + timedelta(hours=1)
        close *= 1.0 + rng.gauss(0, 0.01)

        klines.append(Bar("BTCUSDT", t_open, close * 0.99, close * 1.01, close * 0.98, close, 1000.0))
        # Metric được ghi nhận tại mốc đóng nến t_close
        metrics.append({
            "ts": t_close,
            "sum_open_interest": 1000.0,
            "sum_open_interest_value": 1000.0 * close,
            "sum_taker_long_short_vol_ratio": 1.2 + rng.gauss(0, 0.15),
        })
        orderflow.append({
            "ts": t_open,
            "delta": rng.gauss(0, 20.0),
            "taker_buy_volume": 500.0,
            "taker_sell_volume": 500.0,
            "buy_ratio": 0.5,
            "trade_count": 100,
        })

    # Đường vào 1: Feature Panel (với metric_lag_minutes=0 để metric tại T được lấy tại đúng T)
    panel = build_feature_panel(klines, [], metrics, orderflow, metric_lag_minutes=0)
    panel = add_past_return_to_panel(panel)

    feat_vals_panel = [r.get("taker_ls_vol_ratio") for r in panel]
    past_vals_panel = [r.get("ret_past_1h") for r in panel]
    fut_vals_panel = [r.get("fwd_ret_1h") for r in panel]

    rho_t_panel, rho_s_panel, n_t_panel, n_s_panel = compute_leakage_pair(
        feat_vals_panel, past_vals_panel, fut_vals_panel
    )

    # Đường vào 2: Cột thô từ DB (align_raw_series_to_returns)
    close_by_t = {b.ts + timedelta(hours=1): b.close for b in klines}
    raw_series = {
        "sum_taker_long_short_vol_ratio": {m["ts"]: m["sum_taker_long_short_vol_ratio"] for m in metrics}
    }
    raw_rows = align_raw_series_to_returns(close_by_t, raw_series)

    feat_vals_raw = [r.get("sum_taker_long_short_vol_ratio") for r in raw_rows]
    past_vals_raw = [r.get("ret_past_1h") for r in raw_rows]
    fut_vals_raw = [r.get("fwd_ret_1h") for r in raw_rows]

    rho_t_raw, rho_s_raw, n_t_raw, n_s_raw = compute_leakage_pair(
        feat_vals_raw, past_vals_raw, fut_vals_raw
    )

    # Khẳng định số hàng hợp lệ bằng nhau
    assert n_t_panel == n_t_raw
    assert n_s_panel == n_s_raw
    assert n_t_panel > 10

    # Khẳng định cả hai đường vào cho cùng rho_truoc và rho_sau chính xác
    assert abs(rho_t_panel - rho_t_raw) < 1e-12, (
        f"rho_truoc khong khop: panel={rho_t_panel}, raw={rho_t_raw}"
    )
    assert abs(rho_s_panel - rho_s_raw) < 1e-12, (
        f"rho_sau khong khop: panel={rho_s_panel}, raw={rho_s_raw}"
    )

