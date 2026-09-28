"""Unit tests cho module đo bám theo mốc giờ UTC (Brief đợt 117).

Tuân thủ nghiêm ngặt yêu cầu Brief 117 B3:
- Hàm thuần, mỗi hàm một test có ví dụ tính tay ghi rõ trong docstring.
- CẤM dựng expected bằng cách viết lại công thức trong test. Ghim số literal đã tính tay.
- Phục vụ 4 phép phá thử bắt buộc:
  1. Phép phá thử 1: Lấy giờ h+1 thay vì h -> test đỏ.
  2. Phép phá thử 2: Tính lợi suất trên chuỗi thô TRƯỚC khi ghép ngày -> test đỏ.
  3. Phép phá thử 3: Đổi sqrt(252) thành 252 -> test đỏ.
  4. Phép phá thử 4: Đổi trung vị basis thành trung bình -> test đỏ.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from scripts.check_bingx_tracking import (
    compute_basis_stats,
    compute_pearson_correlation,
    compute_tracking_error_annualized,
)
from scripts.check_bingx_tracking_hourly import (
    align_and_evaluate,
    extract_hourly_series,
)


def test_extract_hourly_series_and_mutation_1():
    """Kiểm tra trích xuất chuỗi nến theo đúng mốc giờ UTC.

    Ví dụ tính tay:
    Tập nến gồm 4 nến vào 2 ngày khác nhau:
    - 2026-08-01 15:00 UTC: 100.0
    - 2026-08-01 16:00 UTC: 101.5
    - 2026-08-02 15:00 UTC: 102.0
    - 2026-08-02 16:00 UTC: 103.5

    Khi chọn target_hour = 16:
    - Ngày 2026-08-01: Giá đóng cửa đúng mốc 16:00 là 101.5
    - Ngày 2026-08-02: Giá đóng cửa đúng mốc 16:00 là 103.5
    - Tập kết quả có đúng 2 ngày với các giá trị chính xác là 101.5 và 103.5.

    CHỐT PHÁ THỬ 1:
    Nếu hàm extract_hourly_series bị đột biến lấy giờ h+1 (ví dụ (target_hour + 1) % 24 = 17:00),
    kết quả sẽ rỗng (len == 0) hoặc sai giá trị -> Test BẮT BUỘC ĐỎ!
    """
    bars = [
        (datetime(2026, 8, 1, 15, 0, tzinfo=UTC), 100.0),
        (datetime(2026, 8, 1, 16, 0, tzinfo=UTC), 101.5),
        (datetime(2026, 8, 2, 15, 0, tzinfo=UTC), 102.0),
        (datetime(2026, 8, 2, 16, 0, tzinfo=UTC), 103.5),
    ]

    res = extract_hourly_series(bars, target_hour=16)
    assert len(res) == 2
    assert res[date(2026, 8, 1)] == 101.5
    assert res[date(2026, 8, 2)] == 103.5


def test_match_and_align_dates_order_and_mutation_2():
    """Kiểm tra ghép ngày trước khi tính lợi suất vs tính lợi suất trên chuỗi thô.

    CHỐT PHÁ THỬ 2 (Brief 117 B1, B3):
    'Ghép theo ngày trước, rồi mới tính lợi suất trên các ngày đã khớp — thứ tự này quan trọng'

    Ví dụ tính tay chứng minh sự sai khác lớn:
    - Giả sử BingX có 4 ngày: Day 1, Day 2, Day 3, Day 5 (bị thiếu Day 4).
      Giá BingX: [100.0, 102.0, 104.0, 106.0]
    - Nguồn ngoài có đủ 5 ngày: Day 1, Day 2, Day 3, Day 4, Day 5.
      Giá Ngoài: [100.0, 102.0, 104.0, 105.0, 106.0]

    Cách đúng (Ghép ngày trước rồi tính lợi suất):
    - Các ngày chung: [Day 1, Day 2, Day 3, Day 5]
    - Chuỗi giá BingX chung: [100.0, 102.0, 104.0, 106.0]
    - Chuỗi giá Ngoài chung: [100.0, 102.0, 104.0, 106.0]
    - Lợi suất tính trên chuỗi đã ghép:
      r_bingx: [102/100 - 1, 104/102 - 1, 106/104 - 1] = [+0.02, +0.0196078, +0.0192308]
      r_ext:   [102/100 - 1, 104/102 - 1, 106/104 - 1] = [+0.02, +0.0196078, +0.0192308]
      Hai chuỗi lợi suất giống hệt nhau 100% -> Tương quan Pearson = 1.00000.

    Cách sai (Tính lợi suất trên chuỗi thô TRƯỚC khi ghép ngày):
      Lợi suất thô Ngoài tại Day 5: 106/105 - 1 = +0.0095238 (so với Day 4)
      Lợi suất thô BingX tại Day 5: 106/104 - 1 = +0.0192308 (so với Day 3)
      Lúc này tại Day 5 bị so lệch gốc -> Tương quan bị tụt xuống ~0.9416 != 1.00000!

    Test này ghim literal: corr đúng = 1.00000.
    Nếu hàm bị đột biến tính lợi suất trước khi ghép ngày -> Test BẮT BUỘC ĐỎ!
    """
    d1 = date(2026, 8, 1)
    d2 = date(2026, 8, 2)
    d3 = date(2026, 8, 3)
    d4 = date(2026, 8, 4)
    d5 = date(2026, 8, 5)

    bingx_dict = {d1: 100.0, d2: 102.0, d3: 104.0, d5: 106.0}
    ext_dict = {d1: 100.0, d2: 102.0, d3: 104.0, d4: 105.0, d5: 106.0}

    # Đánh giá độ bám theo chuẩn ghép ngày trước
    eval_res, common_dates = align_and_evaluate(bingx_dict, ext_dict)
    assert len(common_dates) == 4
    assert common_dates == [d1, d2, d3, d5]
    assert eval_res["returns_count"] == 3
    # Literal ghim số: tương quan đúng phải bằng 1.00000
    assert pytest.approx(eval_res["returns_corr"], abs=1e-5) == 1.00000


def test_pearson_correlation_hand_calculated():
    """Kiểm tra tương quan Pearson tính tay trên 4 điểm dữ liệu (không dùng numpy).

    Ví dụ tính tay:
    x = [0.01, 0.02, -0.01, 0.00]
    y = [0.02, 0.04, -0.02, 0.00]
    mean_x = (0.01 + 0.02 - 0.01 + 0.00) / 4 = 0.02 / 4 = 0.005
    mean_y = (0.02 + 0.04 - 0.02 + 0.00) / 4 = 0.04 / 4 = 0.010

    Độ lệch (x - mean_x) = [+0.005, +0.015, -0.015, -0.005]
    Độ lệch (y - mean_y) = [+0.010, +0.030, -0.030, -0.010]

    cov = (0.005*0.010) + (0.015*0.030) + (-0.015*-0.030) + (-0.005*-0.010)
        = 0.00005 + 0.00045 + 0.00045 + 0.00005 = 0.00100
    var_x = 0.005^2 + 0.015^2 + (-0.015)^2 + (-0.005)^2
          = 0.000025 + 0.000225 + 0.000225 + 0.000025 = 0.00050
    var_y = 0.010^2 + 0.030^2 + (-0.030)^2 + (-0.010)^2
          = 0.000100 + 0.000900 + 0.000900 + 0.000100 = 0.00200

    denom = sqrt(0.00050 * 0.00200) = sqrt(0.000001) = 0.00100
    corr = 0.00100 / 0.00100 = 1.00000.
    """
    x = [0.01, 0.02, -0.01, 0.00]
    y = [0.02, 0.04, -0.02, 0.00]
    actual_corr = compute_pearson_correlation(x, y)
    assert pytest.approx(actual_corr, abs=1e-6) == 1.00000

    # Nghịch đảo: z = -y -> corr = -1.00000
    z = [-0.02, -0.04, 0.02, 0.00]
    assert pytest.approx(compute_pearson_correlation(x, z), abs=1e-6) == -1.00000


def test_tracking_error_annualized_and_mutation_3():
    """Kiểm tra Tracking Error năm hóa với hệ số sqrt(252).

    Lý do dùng sqrt(252):
    252 là số ngày giao dịch chuẩn trong một năm tài chính (52 tuần x 5 ngày - ~8 ngày lễ).
    Theo giả định bước ngẫu nhiên (Brownian motion), độ biến động năm hóa tỷ lệ với căn bậc hai
    của thời gian: sigma_annual = sigma_daily * sqrt(252).

    Ví dụ tính tay với 4 mốc chênh lệch lợi suất:
    r_bingx = [0.01, -0.01, 0.01, -0.01]
    r_ext   = [0.00,  0.00, 0.00,  0.00]
    diffs   = [+0.01, -0.01, +0.01, -0.01]
    mean(diffs) = 0.0

    Tổng bình phương sai lệch = 4 * 0.01^2 = 4 * 0.0001 = 0.0004
    Phương sai mẫu (ddof=1) = 0.0004 / (4 - 1) = 0.0004 / 3 = 0.000133333333...
    Độ lệch chuẩn mẫu stdev = sqrt(0.000133333333...) = 0.01154700538...

    Năm hóa chuẩn với sqrt(252):
    TE = 0.01154700538 * sqrt(252) = 0.01154700538 * 15.874507866... = 0.183303027...
    Literal ghim số: 0.183303

    CHỐT PHÁ THỬ 3:
    Nếu bị đột biến nhân thẳng với 252 (không lấy căn):
    TE_mutated = 0.01154700538 * 252 = 2.90984535...
    Sai lệch cực lớn: 2.909845 != 0.183303 -> Test BẮT BUỘC ĐỎ!
    """
    r_bingx = [0.01, -0.01, 0.01, -0.01]
    r_ext = [0.00, 0.00, 0.00, 0.00]

    te = compute_tracking_error_annualized(r_bingx, r_ext, annual_factor=252.0)
    expected_literal_te = 0.183303
    assert pytest.approx(te, abs=1e-5) == expected_literal_te


def test_basis_stats_median_and_mutation_4():
    """Kiểm tra phân phối basis và chốt phân biệt trung vị vs trung bình.

    Ví dụ tính tay với 5 mốc giá:
    ext_prices   = [100.0, 100.0, 100.0, 100.0, 100.0]
    bingx_prices = [101.0,  99.0, 100.5, 102.0,  98.0]

    basis_t = (bingx / ext) - 1:
    basis = [+0.01, -0.01, +0.005, +0.02, -0.02]
    Sắp xếp: [-0.02, -0.01, +0.005, +0.01, +0.02]

    Trung vị (median): Phần tử chính giữa (vị trí thứ 3) = +0.00500 (+0.5000%)
    Trung bình (mean): (-0.02 - 0.01 + 0.005 + 0.01 + 0.02) / 5 = +0.005 / 5 = +0.00100 (+0.1000%)
    Max |basis| = 0.02000 (2.0000%)
    Số ngày |basis| > 1% (0.01): Có 2 ngày (-0.02 và +0.02) -> count = 2, pct = 40.0%

    CHỐT PHÁ THỬ 4:
    Nếu hàm compute_basis_stats bị đột biến đổi median thành mean:
    Kết quả tính ra 0.00100 thay vì 0.00500 -> Test BẮT BUỘC ĐỎ!
    """
    ext = [100.0, 100.0, 100.0, 100.0, 100.0]
    bingx = [101.0, 99.0, 100.5, 102.0, 98.0]

    stats = compute_basis_stats(bingx, ext)
    expected_median = 0.00500
    expected_max = 0.02000

    assert pytest.approx(stats["median_basis"], abs=1e-6) == expected_median
    assert pytest.approx(stats["max_abs_basis"], abs=1e-6) == expected_max
    assert stats["count_basis_gt_1pct"] == 2
    assert pytest.approx(stats["pct_basis_gt_1pct"], abs=1e-2) == 40.0
