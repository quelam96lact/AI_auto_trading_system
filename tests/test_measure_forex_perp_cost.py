"""Unit tests cho module đo chi phí giữ vị thế forex perp BingX (Brief đợt 116).

Tuân thủ nghiêm ngặt TDD:
- Mỗi hàm một test có ví dụ tính tay ghi rõ trong docstring hoặc comment.
- Bao gồm các chốt kiểm định phục vụ 3 phép phá thử bắt buộc:
  1. Phép phá thử 1: Đổi quy đổi funding sang %/ngày từ * (24/chu_kỳ) thành * chu_kỳ -> test đỏ.
  2. Phép phá thử 2: Đổi phí một vòng từ 2 * taker thành 1 * taker -> test đỏ.
  3. Phép phá thử 3: Đổi trung vị |lợi suất ngày| thành trung bình có dấu -> test đỏ.
"""

from __future__ import annotations

import pytest

from scripts.measure_forex_perp_cost import (
    compute_atr14_series_pct,
    compute_cost_to_amplitude_ratio,
    compute_daily_amplitude_pct,
    compute_funding_distribution_daily_pct,
    compute_funding_interval_hours,
    compute_holding_cost_ratio,
    compute_roundtrip_taker_fee_pct,
    convert_funding_rate_to_daily_pct,
)


def test_compute_funding_interval_hours():
    """Kiểm tra tính chu kỳ funding giữa các mốc fundingTime.

    Ví dụ tính tay:
    4 mốc liên tiếp cách nhau đúng 8 giờ = 28_800_000 ms:
    t0 = 1_000_000_000_000
    t1 = 1_000_028_800_000 (diff = 8h)
    t2 = 1_000_057_600_000 (diff = 8h)
    t3 = 1_000_086_400_000 (diff = 8h)
    Khoảng cách: [8.0, 8.0, 8.0]
    Trung vị: 8.0 giờ.
    Số mốc lệch khỏi trung vị: 0.

    Thêm 1 mốc lệch 12h:
    t4 = 1_000_129_600_000 (diff = 43_200_000 ms = 12h)
    Khoảng cách: [8.0, 8.0, 8.0, 12.0]
    Trung vị: 8.0 giờ.
    Số mốc lệch: 1.
    """
    base = 1_000_000_000_000
    ts_list = [
        base,
        base + 28_800_000,
        base + 57_600_000,
        base + 86_400_000,
    ]
    res = compute_funding_interval_hours(ts_list)
    assert res["median_hours"] == 8.0
    assert res["deviated_count"] == 0
    assert len(res["intervals"]) == 3

    # Thêm mốc lệch 12h
    ts_list.append(base + 86_400_000 + 43_200_000)
    res2 = compute_funding_interval_hours(ts_list)
    assert res2["median_hours"] == 8.0
    assert res2["deviated_count"] == 1


def test_convert_funding_rate_to_daily_pct_and_mutation_1():
    """Kiểm tra quy đổi funding rate sang %/ngày.

    CHỐT PHÁ THỬ 1:
    Công thức đúng: rate * (24.0 / interval_hours) * 100.0
    Ví dụ tính tay:
    - rate = 0.000040 (0.0040% cho mỗi 8 giờ)
    - interval_hours = 8.0
    - Số chu kỳ mỗi ngày = 24 / 8 = 3 lần
    - Tỷ lệ theo %/ngày = 0.000040 * 3 * 100 = 0.0120% / ngày

    Nếu bị đột biến thành: rate * interval_hours * 100.0:
    - Kết quả đột biến = 0.000040 * 8 * 100 = 0.0320% / ngày
    - Sai lệch: 0.0320% != 0.0120% -> Test BẮT BUỘC ĐỎ!
    """
    rate = 0.000040
    interval = 8.0
    expected_daily_pct = 0.0120  # 0.000040 * 3 * 100

    daily_pct = convert_funding_rate_to_daily_pct(rate, interval)
    assert pytest.approx(daily_pct, abs=1e-6) == expected_daily_pct

    # Kiểm tra trường hợp rate âm
    rate_neg = -0.000050
    expected_neg = -0.0150  # -0.000050 * 3 * 100
    assert pytest.approx(convert_funding_rate_to_daily_pct(rate_neg, interval), abs=1e-6) == expected_neg


def test_compute_funding_distribution_daily_pct():
    """Kiểm tra tính phân phối funding theo %/ngày (có dấu, trị tuyệt đối, P5, P95).

    Ví dụ tính tay với 5 mốc funding (chu kỳ 8h -> nhân 300 để ra %/ngày):
    rates = [-0.0001, +0.0001, +0.0002, -0.0002, +0.0000]
    daily_rates (%) = [-0.03%, +0.03%, +0.06%, -0.06%, 0.00%]
    abs_daily (%)   = [0.03%, 0.03%, 0.06%, 0.06%, 0.00%]

    Trung bình có dấu: (-0.03 + 0.03 + 0.06 - 0.06 + 0.00) / 5 = 0.0000%
    Trung bình trị tuyệt đối: (0.03 + 0.03 + 0.06 + 0.06 + 0.00) / 5 = 0.18 / 5 = 0.0360%
    """
    rates = [-0.0001, 0.0001, 0.0002, -0.0002, 0.0]
    res = compute_funding_distribution_daily_pct(rates, interval_hours=8.0)
    assert pytest.approx(res["mean_daily_signed_pct"], abs=1e-6) == 0.0
    assert pytest.approx(res["mean_daily_abs_pct"], abs=1e-6) == 0.0360
    assert res["p5_daily_pct"] <= res["p95_daily_pct"]


def test_compute_roundtrip_taker_fee_pct_and_mutation_2():
    """Kiểm tra tính phí một vòng taker (vào lệnh + đóng lệnh).

    CHỐT PHÁ THỬ 2:
    Công thức đúng: 2 * takerFeeRate * 100.0 (%)
    Ví dụ tính tay:
    - takerFeeRate = 0.0005 (0.05% mỗi chiều, theo API BingX contracts)
    - Phí 1 vòng taker = 2 * 0.0005 * 100 = 0.1000%

    Nếu bị đột biến thành: 1 * takerFeeRate * 100.0:
    - Kết quả đột biến = 0.0500%
    - Sai lệch: 0.0500% != 0.1000% -> Test BẮT BUỘC ĐỎ!
    """
    taker_rate = 0.0005
    expected_roundtrip_pct = 0.1000
    actual = compute_roundtrip_taker_fee_pct(taker_rate)
    assert pytest.approx(actual, abs=1e-6) == expected_roundtrip_pct


def test_compute_daily_amplitude_pct_and_mutation_3():
    """Kiểm tra tính biên độ ngày (trung vị |lợi suất ngày| tính bằng %).

    CHỐT PHÁ THỬ 3:
    Công thức đúng: Trung vị của |r_t| với r_t = (P_t / P_{t-1}) - 1, nhân 100%.
    Ví dụ tính tay:
    Chuỗi giá dao động quanh 100:
    P = [100.0, 102.0, 100.0, 102.0, 100.0]
    Lợi suất ngày có dấu r_t:
    - r_1 = 102 / 100 - 1 = +0.020000 (+2.0000%)
    - r_2 = 100 / 102 - 1 = -0.019608 (-1.9608%)
    - r_3 = 102 / 100 - 1 = +0.020000 (+2.0000%)
    - r_4 = 100 / 102 - 1 = -0.019608 (-1.9608%)

    Trị tuyệt đối |r_t| (%):
    [2.0000%, 1.9608%, 2.0000%, 1.9608%]
    Sắp xếp: [1.9608%, 1.9608%, 2.0000%, 2.0000%]
    Trung vị = (1.9608% + 2.0000%) / 2 = 1.9804%

    Nếu bị đột biến thành trung bình có dấu (signed mean):
    - mean(r_t) = (+0.020000 - 0.019608 + 0.020000 - 0.019608) / 4 = +0.000196 (+0.0196%)
    - Sai lệch cực lớn: 0.0196% != 1.9804% -> Test BẮT BUỘC ĐỎ!
    """
    prices = [100.0, 102.0, 100.0, 102.0, 100.0]
    expected_median_abs_pct = (2.0 + (100.0 / 102.0 - 1.0) * -100.0) / 2.0  # ~1.980392%
    actual = compute_daily_amplitude_pct(prices)
    assert pytest.approx(actual, abs=1e-4) == expected_median_abs_pct


def test_compute_cost_to_amplitude_ratio():
    """Kiểm tra tỷ lệ chi phí phí vòng / biên độ ngày gốc.

    Ví dụ tính tay:
    - Phí vòng taker = 0.1000%
    - Biên độ ngày gốc = 0.3103% (FRB_H10 EURUSD)
    - Tỷ lệ = (0.1000 / 0.3103) * 100 = 32.2269%
    """
    # Ghim so literal, KHONG viet lai cong thuc trong than test: neu ca ham va
    # bieu thuc trong test cung bi sua theo nhau thi phep so sanh mat tac dung.
    actual = compute_cost_to_amplitude_ratio(0.1000, 0.3103)
    assert pytest.approx(actual, abs=1e-4) == 32.2269


def test_compute_holding_cost_ratio():
    """Kiểm tra tỷ lệ chi phí giữ H ngày / biên độ ngày gốc.

    Ví dụ tính tay với H = 5 ngày:
    - roundtrip_taker_fee_pct = 0.1000%
    - funding_trung_binh_tuyet_doi = 0.016309% / ngày
    - daily_amplitude_pct = 0.3103%
    - Tổng chi phí giữ 5 ngày:
      0.1000% + 5 * 0.016309% = 0.1000% + 0.081545% = 0.181545%
    - Tỷ lệ so với biên độ ngày gốc:
      (0.181545 / 0.3103) * 100 = 58.5063%
    """
    # Ghim so literal thay vi viet lai cong thuc (xem ly do o test tren).
    actual = compute_holding_cost_ratio(
        roundtrip_taker_fee_pct=0.1000,
        daily_funding_abs_pct=0.016309,
        daily_amplitude_pct=0.3103,
        hold_days=5,
    )
    assert pytest.approx(actual, abs=1e-4) == 58.5063

    # H = 0 nghia la vao ra trong ngay: chi con phi vong, khong co funding.
    assert pytest.approx(
        compute_holding_cost_ratio(
            roundtrip_taker_fee_pct=0.1000,
            daily_funding_abs_pct=0.016309,
            daily_amplitude_pct=0.3103,
            hold_days=0,
        ),
        abs=1e-4,
    ) == 32.2269


def test_compute_atr14_series_pct():
    """ATR14 tren nen 1d theo % Close.

    Vi du tinh tay, CO Y chon chuoi KHONG doi xung de mot cua so sai lech
    (vi du 7 thay vi 14) lam ket qua khac han. Ban truoc dung High-Low co dinh
    nen cua so nao cung ra 2.0%, tuc la test mu -- da phat hien khi pha thu.

    15 nen, Close = 100.0 o moi nen.
    - Nen i = 1..12: High = 100.5, Low = 99.5
      TR = max(100.5 - 99.5, |100.5 - 100|, |99.5 - 100|) = max(1.0, 0.5, 0.5) = 1.0
    - Nen i = 13, 14: High = 104.0, Low = 96.0
      TR = max(104 - 96, |104 - 100|, |96 - 100|) = max(8.0, 4.0, 4.0) = 8.0

    trs = [1.0] * 12 + [8.0, 8.0]  -> dung 14 gia tri, nen chi tinh duoc 1 ATR.
    Tong = 12 * 1.0 + 2 * 8.0 = 12 + 16 = 28.0
    ATR14 = 28.0 / 14 = 2.0
    ATR14 theo % Close = (2.0 / 100.0) * 100 = 2.0000%
    Chi co mot gia tri nen ca trung vi va trung binh deu = 2.0000%.

    Neu cua so bi doi thanh 7:
      atr_pcts = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 3.0] -> trung vi 1.0%, trung binh 1.375%
      Ca hai khac 2.0000% -> test DO. Day la chot chong lech cua so.
    """
    bars = [{"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0}]
    for i in range(1, 15):
        if i <= 12:
            bars.append({"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0})
        else:
            bars.append({"open": 100.0, "high": 104.0, "low": 96.0, "close": 100.0})
    assert len(bars) == 15

    res = compute_atr14_series_pct(bars)
    assert pytest.approx(res["median_atr14_pct"], abs=1e-6) == 2.0
    assert pytest.approx(res["mean_atr14_pct"], abs=1e-6) == 2.0


def test_compute_atr14_raises_when_not_enough_bars():
    """Thieu nen thi phai RAISE, khong duoc tra 0.0.

    0.0 nghia la 'khong bien dong', con thieu nen nghia la 'khong do duoc'.
    Tra 0.0 se lam ty le phi/bien-do thanh vo cuc hoac che mat van de --
    dung lop loi mac-dinh-an-toan da tung pha hai cong go-live cua du an nay.
    """
    bars = [{"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}] * 14
    with pytest.raises(ValueError, match="15 nen"):
        compute_atr14_series_pct(bars)


def test_compute_atr14_raises_on_dirty_bar():
    """Nen co close <= 0 (nen ban) phai RAISE, khong duoc bo qua im lang."""
    bars = [{"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0} for _ in range(15)]
    bars[14] = {"open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0}
    with pytest.raises(ValueError, match="nen ban"):
        compute_atr14_series_pct(bars)
