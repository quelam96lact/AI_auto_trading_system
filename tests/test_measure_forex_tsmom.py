"""Unit tests cho module đo lường Time-Series Momentum trên Forex (Brief đợt 118).

Tuân thủ nghiêm ngặt yêu cầu Brief 118 §7:
- Hàm thuần, mỗi hàm một test có ví dụ tính tay ghi rõ trong docstring.
- CẤM dựng expected bằng cách viết lại công thức trong test. Ghim số literal đã tính tay.
- Phục vụ 5 phép phá thử bắt buộc:
  1. Phép phá thử 1: Tín hiệu dùng close_{t+1} thay vì close_t (nhìn trước) -> test đỏ.
  2. Phép phá thử 2: t-250 đếm theo ngày lịch thay vì theo hàng -> test đỏ.
  3. Phép phá thử 3: Đảo chiều tính 1 chân thay vì 2 -> test đỏ.
  4. Phép phá thử 4: Funding tính theo số lần tái cân bằng thay vì số ngày giữ -> test đỏ.
  5. Phép phá thử 5: "Ngày cuối tháng" lấy theo lịch thay vì ngày có dữ liệu cuối cùng -> test đỏ.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from scripts.measure_forex_tsmom import (
    calculate_period_funding,
    calculate_turnover_fee,
    compute_buy_and_hold_benchmark,
    compute_tsmom_signal_at_bar,
    identify_month_ends,
    simulate_tsmom_strategy,
)


def test_identify_month_ends_and_mutation_5():
    """Kiểm tra việc xác định ngày có dữ liệu cuối cùng của mỗi tháng.

    Ví dụ tính tay:
    Tập dữ liệu gồm 5 nến:
    - 2026-05-27 (Thứ Tư): close = 100.0
    - 2026-05-28 (Thứ Năm): close = 101.0
    - 2026-05-29 (Thứ Sáu, ngày giao dịch cuối cùng có dữ liệu trong tháng 5): close = 102.0
    (Ngày 30/05 là Thứ Bảy, 31/05 là Chủ Nhật -> thị trường đóng cửa, không có nến)
    - 2026-06-01 (Thứ Hai): close = 103.0
    - 2026-06-02 (Thứ Ba, ngày cuối cùng có dữ liệu trong tháng 6): close = 104.0

    Kết quả chuẩn:
    Mốc cuối tháng 5 phải là ngày 2026-05-29 với close = 102.0 (hàng index = 2).
    Mốc cuối tháng 6 phải là ngày 2026-06-02 với close = 104.0 (hàng index = 4).
    Tổng cộng có đúng 2 mốc tháng.

    CHỐT PHÁ THỬ 5:
    Nếu hàm bị đột biến lấy 'ngày cuối tháng theo lịch' (ví dụ kiểm tra d.day == 31 cho tháng 5),
    vì trong danh sách không có ngày 2026-05-31 nên tháng 5 sẽ bị bỏ sót (len == 1) hoặc
    bị gán sai mốc -> Test BẮT BUỘC ĐỎ!
    """
    bars = [
        (date(2026, 5, 27), 100.0),
        (date(2026, 5, 28), 101.0),
        (date(2026, 5, 29), 102.0),
        (date(2026, 6, 1), 103.0),
        (date(2026, 6, 2), 104.0),
    ]

    m_ends = identify_month_ends(bars)
    assert len(m_ends) == 2

    # Ghim literal ngày và giá trị đóng cửa
    idx1, d1, c1 = m_ends[0]
    assert idx1 == 2
    assert d1 == date(2026, 5, 29)
    assert c1 == 102.0

    idx2, d2, c2 = m_ends[1]
    assert idx2 == 4
    assert d2 == date(2026, 6, 2)
    assert c2 == 104.0


def test_signal_lookback_rows_and_mutation_1_and_2():
    """Kiểm tra tín hiệu lookback đúng 250 hàng giao dịch (không nhìn trước, không tính theo ngày lịch).

    Ví dụ tính tay:
    Tạo chuỗi 252 nến giao dịch (khoảng 360 ngày lịch do trừ ngày cuối tuần):
    - Hàng 0 (2025-01-02): close = 100.0
    - Hàng 1..249: giá biến động quanh 150.0.
      Đặc biệt: Tại mốc 250 ngày LỊCH trước ngày hiện tại (khoảng hàng 175), giá là 150.0.
    - Hàng 250 (2025-12-30): close = 120.0
    - Hàng 251 (2025-12-31): close = 80.0

    Tính toán chuẩn tại mốc t = hàng 250:
    - 250 hàng trước đó là hàng 0: close_0 = 100.0.
    - Lợi suất lookback r = 120.0 / 100.0 - 1.0 = +0.20 (+20.0%).
    - Vì r > 0 -> pos = +1 (LONG).
    Literal ghim số: r = 0.20000, pos = 1.

    CHỐT PHÁ THỬ 1 (Nhìn trước):
    Nếu hàm bị đột biến lấy close_{t+1} (hàng 251 có close = 80.0) thay vì close_t (120.0):
    r_mutated = 80.0 / 100.0 - 1.0 = -0.20 (-20.0%) -> pos = -1.
    Sai khác hoàn toàn: pos = -1 != 1 -> Test BẮT BUỘC ĐỎ!

    CHỐT PHÁ THỬ 2 (Đếm theo ngày lịch):
    Nếu hàm bị đột biến lấy 250 ngày lịch thay vì 250 hàng:
    250 ngày lịch trước ngày 2025-12-30 rơi vào khoảng tháng 4/2025 (hàng 175 có close = 150.0).
    r_mutated = 120.0 / 150.0 - 1.0 = -0.20 -> pos = -1 != 1 -> Test BẮT BUỘC ĐỎ!
    """
    bars: list[tuple[date, float]] = []
    base_d = date(2025, 1, 2)
    cur_d = base_d

    # Sinh 252 ngày giao dịch (bỏ Thứ 7, CN)
    for i in range(252):
        while cur_d.weekday() >= 5:  # 5=Sat, 6=Sun
            cur_d += timedelta(days=1)
        if i == 0:
            c = 100.0
        elif i == 250:
            c = 120.0
        elif i == 251:
            c = 80.0
        else:
            c = 150.0
        bars.append((cur_d, c))
        cur_d += timedelta(days=1)

    r, pos = compute_tsmom_signal_at_bar(bars, bar_index=250, lookback_rows=250)
    assert pos == 1
    assert pytest.approx(r, abs=1e-5) == 0.20000

    # Kiểm tra warm-up: bar_index < 250 phải trả về 0.0, 0
    r_warm, pos_warm = compute_tsmom_signal_at_bar(bars, bar_index=249, lookback_rows=250)
    assert pos_warm == 0
    assert r_warm == 0.0


def test_turnover_fee_reversal_legs_and_mutation_3():
    """Kiểm tra số chân phí giao dịch: đảo chiều long<->short tốn 2 chân, vào từ phẳng tốn 1 chân.

    Ví dụ tính tay:
    - Vào lệnh từ phẳng (0 -> 1): 1 chân -> phí = 1 * 0.0005 = 0.0005 (0.05%)
    - Đảo chiều (1 -> -1): 2 chân -> phí = 2 * 0.0005 = 0.0010 (0.10%)
    - Giữ nguyên vị thế (-1 -> -1): 0 chân -> phí = 0.0
    - Đảo chiều (-1 -> 1): 2 chân -> phí = 2 * 0.0005 = 0.0010 (0.10%)
    - Thoát về phẳng (1 -> 0): 1 chân -> phí = 1 * 0.0005 = 0.0005 (0.05%)

    CHỐT PHÁ THỬ 3:
    Nếu hàm bị đột biến tính đảo chiều chỉ tốn 1 chân:
    Tại bước (1 -> -1), legs = 1 thay vì 2, phí = 0.0005 thay vì 0.0010 -> Test BẮT BUỘC ĐỎ!
    """
    legs1, fee1 = calculate_turnover_fee(prev_pos=0, curr_pos=1, fee_per_leg=0.0005)
    assert legs1 == 1
    assert pytest.approx(fee1, abs=1e-6) == 0.0005

    # Đảo chiều bắt buộc 2 chân
    legs2, fee2 = calculate_turnover_fee(prev_pos=1, curr_pos=-1, fee_per_leg=0.0005)
    assert legs2 == 2
    assert pytest.approx(fee2, abs=1e-6) == 0.0010

    legs3, fee3 = calculate_turnover_fee(prev_pos=-1, curr_pos=-1, fee_per_leg=0.0005)
    assert legs3 == 0
    assert pytest.approx(fee3, abs=1e-6) == 0.0000


def test_period_funding_days_held_and_mutation_4():
    """Kiểm tra tính phí funding theo số ngày lịch nắm giữ vị thế.

    Ví dụ tính tay:
    - start_date = 2026-01-31, end_date = 2026-02-28 (28 ngày lịch).
    - Mức funding B: 0.016%/ngày = 0.00016 / ngày.
    - pos = 1 (hoặc -1):
      funding = 28 * 0.00016 = 0.00448 (0.448%).
    - Nếu pos = 0 (phẳng):
      funding = 0.0.

    Literal ghim số: days = 28, funding = 0.00448.

    CHỐT PHÁ THỬ 4:
    Nếu hàm bị đột biến tính funding theo 'số lần tái cân bằng' thay vì số ngày giữ (ví dụ lấy 1 * daily_rate):
    funding_mutated = 1 * 0.00016 = 0.00016 != 0.00448 -> Test BẮT BUỘC ĐỎ!
    """
    days, funding = calculate_period_funding(
        pos=1,
        start_date=date(2026, 1, 31),
        end_date=date(2026, 2, 28),
        daily_funding_rate=0.00016,
    )
    assert days == 28
    assert pytest.approx(funding, abs=1e-6) == 0.00448

    # Vị thế phẳng không tốn funding
    days_flat, funding_flat = calculate_period_funding(
        pos=0,
        start_date=date(2026, 1, 31),
        end_date=date(2026, 2, 28),
        daily_funding_rate=0.00016,
    )
    assert days_flat == 28
    assert funding_flat == 0.0


def test_end_to_end_tsmom_simulation_hand_calculated():
    """Kiểm tra mô phỏng hoàn chỉnh 3 kỳ tái cân bằng với số liệu tính tay ghim literal.

    Ví dụ tính tay:
    Giả sử chuỗi có 253 nến.
    - Mốc tháng 0 (2025-10-31): Hàng index 249 (< 250) -> Chưa có tín hiệu, pos = 0.
    - Mốc tháng 1 (2025-11-30): Hàng index 250 (>= 250).
      close = 120.0, close_{t-250} (hàng 0) = 100.0 -> r = +20% > 0 -> pos = 1 (LONG).
      Tín hiệu này điều khiển vị thế trong Tháng 12/2025!
    - Mốc tháng 2 (2025-12-31):
      close = 132.0.
      Khoảng nắm giữ: từ 2025-11-30 đến 2025-12-31 (31 ngày lịch).
      Vào từ phẳng: 1 chân -> phí = 1 * 0.0005 = 0.0005.
      Funding (mức B = 0.00016): 31 * 0.00016 = 0.00496.
      Lợi suất giá: 132.0 / 120.0 - 1.0 = +0.10 (+10.0%).
      Lợi suất ròng Tháng 12: +0.10 - 0.0005 - 0.00496 = +0.09454 (+9.454%).

    Literal ghim số:
    Kỳ tháng 12/2025: ret_net = 0.09454, legs = 1, days = 31.
    """
    bars: list[tuple[date, float]] = []
    base_d = date(2025, 1, 1)
    # Hàng 0
    bars.append((base_d, 100.0))

    # Hàng 1..248
    for i in range(1, 249):
        bars.append((base_d + timedelta(days=i), 110.0))

    # Hàng 249: Ngày 2025-10-31
    bars.append((date(2025, 10, 31), 115.0))

    # Hàng 250: Ngày 2025-11-30
    bars.append((date(2025, 11, 30), 120.0))

    # Hàng 251: Ngày 2025-12-31
    bars.append((date(2025, 12, 31), 132.0))

    periods = simulate_tsmom_strategy(bars, funding_rate=0.00016, fee_per_leg=0.0005, lookback_rows=250)

    # periods[0] là tháng 10 (warm-up), periods[1] là tháng 11 (warm-up tại đầu tháng), periods[2] là tháng 12
    p_dec = next(p for p in periods if p["ym"] == (2025, 12))

    assert p_dec["pos"] == 1
    assert p_dec["legs"] == 1
    assert pytest.approx(p_dec["fee"], abs=1e-6) == 0.0005
    assert p_dec["days"] == 31
    assert pytest.approx(p_dec["funding"], abs=1e-6) == 0.00496
    assert pytest.approx(p_dec["price_ret"], abs=1e-5) == 0.10000
    assert pytest.approx(p_dec["ret_gross"], abs=1e-5) == 0.10000
    assert pytest.approx(p_dec["ret_net"], abs=1e-5) == 0.09454


def test_buy_and_hold_benchmark_hand_calculated():
    """Kiểm tra đối chứng mua và giữ tính tay ghim literal.

    Ví dụ tính tay:
    - start_date = 2026-01-01 (close = 100.0)
    - end_date = 2026-01-31 (close = 110.0)
    - Số ngày lịch = 30 ngày.
    - Gross return = 110.0 / 100.0 - 1.0 = +0.10 (+10.0%).
    - Phí 2 chân: 2 * 0.0005 = 0.0010 (0.10%).
    - Funding (0.00016/ngày): 30 * 0.00016 = 0.0048 (0.48%).
    - Net return = 0.10 - 0.0010 - 0.0048 = +0.0942 (+9.42%).

    Literal ghim số: gross_ret = 0.10000, net_ret = 0.09420.
    """
    bars = [
        (date(2026, 1, 1), 100.0),
        (date(2026, 1, 15), 105.0),
        (date(2026, 1, 31), 110.0),
    ]

    bh = compute_buy_and_hold_benchmark(
        bars,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        funding_rate=0.00016,
        fee_per_leg=0.0005,
    )

    assert bh["days"] == 30
    assert pytest.approx(bh["gross_ret"], abs=1e-5) == 0.10000
    assert pytest.approx(bh["fee"], abs=1e-6) == 0.0010
    assert pytest.approx(bh["funding"], abs=1e-6) == 0.0048
    assert pytest.approx(bh["net_ret"], abs=1e-5) == 0.09420
