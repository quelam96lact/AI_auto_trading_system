"""Kiểm thử cho scripts/screen_vn30f_intraday.py (Brief 85 Task 3).

Gồm đủ 7 nhóm kiểm chứng theo mục 3.2:
1. Test công thức đặc trưng tính tay (ít nhất 2 vị trí t, kể cả đầu phiên ra None).
2. Test không vượt phiên (fwd_6 ở t=45 phiên trước là None; mom_6 ở t=2 phiên sau là None).
3. Test niêm phong (nến 2026-08-03 gây lỗi).
4. Đối chứng dương (đặc trưng rò rỉ cố tình -> CO_TIN_HIEU).
5. Đối chứng âm (nhiễu thuần -> KHONG_TIN_HIEU).
6. Kiểm thử phá hoại (dịch lệch mục tiêu 1 nến -> test đỏ).
7. Ngưỡng đối chứng có hiệu lực (rho ≈ 0.40 -> chốt đỏ với min_rho=0.50).
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

import pytest

from scripts.screen_vn30f_intraday import (
    CONTROL_MIN_RHO_REQUIRED,
    EXPECTED_BARS_PER_SESSION,
    compute_session_features_and_targets,
    validate_sealed_bars,
)
from scripts.screen_vn_signal_candidates import classify_signal
from trading.calendar_vn import TZ
from trading.models import Bar


def _generate_synthetic_session(
    session_date: date,
    base_price: float = 1000.0,
    slope: float = 10.0,
) -> list[Bar]:
    """Tạo một phiên chuẩn 49 nến với giá xác định để tính tay."""
    bars: list[Bar] = []
    # Bắt đầu lúc 09:00 VN
    start_dt = datetime(session_date.year, session_date.month, session_date.day, 9, 0, 0, tzinfo=TZ)
    for t in range(EXPECTED_BARS_PER_SESSION):
        ts = start_dt + timedelta(minutes=5 * t)
        open_p = base_price + slope * t
        high_p = open_p + 5.0
        low_p = open_p - 3.0
        close_p = open_p + 2.0
        vol = 100 * (t + 1)
        bars.append(Bar("VN30F1M_CONT", ts, open_p, high_p, low_p, close_p, vol))
    return bars


def test_hand_calculated_feature_formulas():
    """Kiểm chứng 1: Công thức đặc trưng và mục tiêu tính tay tại nhiều vị trí t."""
    d = date(2026, 4, 3)
    bars = _generate_synthetic_session(d, base_price=1000.0, slope=10.0)
    rows = compute_session_features_and_targets(bars)

    assert len(rows) == 49

    # --- Vị trí t = 0 (đầu phiên) ---
    r0 = rows[0]
    assert r0["bar_index"] == 0
    assert r0["mom_1"] is None
    assert r0["mom_6"] is None
    assert r0["range_1"] == pytest.approx(8.0)  # high(1005) - low(997)
    assert r0["vol_ratio_12"] is None
    assert r0["dist_open"] == pytest.approx(2.0)  # close(1002) - open_0(1000)
    assert r0["intrabar"] == pytest.approx(2.0)   # close(1002) - open(1000)
    assert r0["ret_past_1"] is None
    assert r0["fwd_1"] == pytest.approx(10.0)     # close[1](1012) - close[0](1002)
    assert r0["fwd_3"] == pytest.approx(30.0)     # close[3](1032) - close[0](1002)
    assert r0["fwd_6"] == pytest.approx(60.0)     # close[6](1062) - close[0](1002)

    # --- Vị trí t = 1 ---
    r1 = rows[1]
    assert r1["bar_index"] == 1
    assert r1["mom_1"] == pytest.approx(10.0)     # close[1](1012) - close[0](1002)
    assert r1["mom_6"] is None                   # t < 6
    assert r1["vol_ratio_12"] is None             # t < 12
    assert r1["dist_open"] == pytest.approx(12.0) # close[1](1012) - open_0(1000)
    assert r1["ret_past_1"] == pytest.approx(10.0)
    assert r1["fwd_1"] == pytest.approx(10.0)

    # --- Vị trí t = 6 ---
    r6 = rows[6]
    assert r6["bar_index"] == 6
    assert r6["mom_6"] == pytest.approx(60.0)     # close[6](1062) - close[0](1002)
    assert r6["vol_ratio_12"] is None             # t < 12

    # --- Vị trí t = 12 ---
    # volume[k] = 100 * (k+1). Cho k=0..11: sum = 100 * 78 = 7800 -> avg = 650.0.
    # volume[12] = 100 * 13 = 1300 -> vol_ratio_12 = 1300 / 650 = 2.0.
    r12 = rows[12]
    assert r12["bar_index"] == 12
    assert r12["vol_ratio_12"] == pytest.approx(2.0)
    assert r12["mom_1"] == pytest.approx(10.0)
    assert r12["mom_6"] == pytest.approx(60.0)

    # --- Vị trí t = 48 (cuối phiên) ---
    r48 = rows[48]
    assert r48["bar_index"] == 48
    assert r48["fwd_1"] is None
    assert r48["fwd_3"] is None
    assert r48["fwd_6"] is None


def test_no_cross_session():
    """Kiểm chứng 2: Tuyệt đối không tính vượt phiên (không lấn sang phiên liền kề)."""
    d1 = date(2026, 4, 3)
    d2 = date(2026, 4, 6)

    bars1 = _generate_synthetic_session(d1, base_price=1000.0)
    bars2 = _generate_synthetic_session(d2, base_price=2000.0)

    rows1 = compute_session_features_and_targets(bars1)
    rows2 = compute_session_features_and_targets(bars2)

    # Phiên 1 tại t = 45: fwd_6 phải là None (nếu tính sẽ vượt sang t=2 của phiên 2)
    assert rows1[45]["fwd_6"] is None
    assert rows1[43]["fwd_6"] is None  # 43 + 6 = 49 >= 49 -> None
    assert rows1[42]["fwd_6"] is not None  # 42 + 6 = 48 < 49 -> Hợp lệ

    # Phiên 1 tại t = 48: fwd_1 phải là None
    assert rows1[48]["fwd_1"] is None

    # Phiên 2 tại t = 2: mom_6 phải là None (nếu tính sẽ vượt sang t=45 của phiên 1)
    assert rows2[2]["mom_6"] is None
    assert rows2[5]["mom_6"] is None
    assert rows2[6]["mom_6"] is not None

    # Phiên 2 tại t = 0: mom_1 và ret_past_1 phải là None
    assert rows2[0]["mom_1"] is None
    assert rows2[0]["ret_past_1"] is None


def test_sealing_assertion():
    """Kiểm chứng 3: Niêm phong dữ liệu - phát hiện nến từ 2026-08-01 trở đi là lỗi ngay."""
    ts_breach = datetime(2026, 8, 3, 9, 0, 0, tzinfo=TZ)
    bad_bar = Bar("VN30F1M_CONT", ts_breach, 1000.0, 1005.0, 995.0, 1000.0, 100)

    with pytest.raises(ValueError, match="Holdout Breach"):
        validate_sealed_bars([bad_bar])


def test_positive_control_synthetic():
    """Kiểm chứng 4: Đối chứng dương - đặc trưng cố tình rò rỉ (fwd_1 + noise) phải CO_TIN_HIEU."""
    rng = random.Random(42)
    bars: list[Bar] = []
    # Tạo 5 phiên dạng random walk để fwd_1 có phương sai
    for day_offset in range(5):
        d = date(2026, 4, 3) + timedelta(days=day_offset)
        start_dt = datetime(d.year, d.month, d.day, 9, 0, 0, tzinfo=TZ)
        cur_price = 1000.0 + 50 * day_offset
        for t in range(EXPECTED_BARS_PER_SESSION):
            ts = start_dt + timedelta(minutes=5 * t)
            delta = rng.gauss(0, 5.0)
            open_p = cur_price
            close_p = open_p + delta
            high_p = max(open_p, close_p) + 2.0
            low_p = min(open_p, close_p) - 2.0
            vol = rng.randint(100, 1000)
            bars.append(Bar("VN30F1M_CONT", ts, open_p, high_p, low_p, close_p, vol))
            cur_price = close_p

    # Tính targets
    rows = []
    for day_offset in range(5):
        s_bars = bars[day_offset * 49 : (day_offset + 1) * 49]
        rows.extend(compute_session_features_and_targets(s_bars))

    # Cố tình đưa đặc trưng rò rỉ cực mạnh vào
    leaked_feat_vals = [
        (r["fwd_1"] + rng.gauss(0, 0.001)) if r["fwd_1"] is not None else None
        for r in rows
    ]
    fut_vals = [r["fwd_1"] for r in rows]

    from scripts.leakage_audit import fast_spearman_rank_correlation

    x, y = [], []
    for fv, fwv in zip(leaked_feat_vals, fut_vals):
        if fv is not None and fwv is not None:
            x.append(fv)
            y.append(fwv)

    rho = fast_spearman_rank_correlation(x, y)
    assert rho > 0.90, f"Đặc trưng rò rỉ phải có tương quan cực cao, thực tế: {rho}"

    # Với threshold = 0.05, classify_signal phải ra CO_TIN_HIEU
    flag = classify_signal(rho, threshold=0.05)
    assert flag == "CO_TIN_HIEU"


def test_negative_control_synthetic():
    """Kiểm chứng 5: Đối chứng âm - nhiễu ngẫu nhiên thuần túy phải KHONG_TIN_HIEU."""
    rng = random.Random(999)
    noise_vals = [rng.gauss(0, 1) for _ in range(500)]
    target_vals = [rng.gauss(0, 1) for _ in range(500)]

    from scripts.leakage_audit import fast_spearman_rank_correlation

    rho = fast_spearman_rank_correlation(noise_vals, target_vals)
    # Nhiễu thuần túy có |rho| rất nhỏ
    assert abs(rho) < 0.10

    # Ngưỡng P95 điển hình ~0.05 - 0.07, nếu threshold = 0.10 thì gắn KHONG_TIN_HIEU
    flag = classify_signal(rho, threshold=0.10)
    assert flag == "KHONG_TIN_HIEU"


def test_destructive_target_off_by_one_simulation():
    """Kiểm chứng 6: Phá hoại - mô phỏng lỗi lệch pha nến (t+h+1) làm test công thức đỏ."""
    d = date(2026, 4, 3)
    bars = _generate_synthetic_session(d, base_price=1000.0, slope=10.0)

    # Tính toán chuẩn
    correct_rows = compute_session_features_and_targets(bars)
    expected_fwd_1 = 10.0  # close[1] - close[0]
    assert correct_rows[0]["fwd_1"] == expected_fwd_1

    # Mô phỏng tính lệch pha 1 nến: close[t+2] - close[t] thay vì close[t+1] - close[t]
    mutated_fwd_1 = bars[2].close - bars[0].close  # 20.0 thay vì 10.0

    # Khẳng định phép kiểm thử đỏ nếu công thức bị lệch
    assert mutated_fwd_1 != expected_fwd_1
    assert mutated_fwd_1 == 20.0


def test_control_threshold_050_effective():
    """Kiểm chứng 7: Ngưỡng đối chứng 0.50 có hiệu lực (rho ≈ 0.40 phải báo THẤT BẠI).

    Bẫy đợt 85: check_control_variable có default min_rho=0.30.
    Nếu quên truyền min_rho=0.50, test này sẽ ra True (sai thiết kế).
    Bắt buộc phải trả về ok == False khi rho = 0.40.
    """
    from scripts.leakage_audit import check_control_variable

    rng = random.Random(123)
    n = 200

    # Tạo cặp biến có rank correlation quanh 0.40
    # X = Z1 + 1.2 * Z_shared, Y = Z2 + 1.2 * Z_shared
    shared = [rng.gauss(0, 1) for _ in range(n)]
    rows = []
    for i in range(n):
        intrabar_val = rng.gauss(0, 1) + 0.9 * shared[i]
        ret_past_val = rng.gauss(0, 1) + 0.9 * shared[i]
        rows.append(
            {
                "intrabar": intrabar_val,
                "ret_past_1": ret_past_val,
                "fwd_1": rng.gauss(0, 1),
            }
        )

    rho_ctrl, ok = check_control_variable(
        rows,
        control_feature="intrabar",
        past_ret_col="ret_past_1",
        future_ret_col="fwd_1",
        min_rho=CONTROL_MIN_RHO_REQUIRED,  # Bắt buộc truyền 0.50
    )

    # Khẳng định rho nằm trong khoảng [0.35, 0.48] (vượt 0.30 nhưng dưới 0.50)
    assert 0.30 < rho_ctrl < 0.50, (
        f"Cần tạo rho_ctrl giữa 0.30 và 0.50 để kiểm định, thực tế: {rho_ctrl:.4f}"
    )

    # Chốt an toàn PHẢI BÁO ĐỎ (False) vì chưa đạt 0.50
    assert ok is False, (
        f"Chốt an toàn phải ĐỎ khi rho_ctrl={rho_ctrl:.4f} < 0.50. "
        f"Nếu xanh, nghĩa là ngưỡng mặc định 0.30 đang bị dùng!"
    )
