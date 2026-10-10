# Đợt 171 — Tối ưu tham số `octopus_pullback` trên nến ngày, walk-forward: KHÔNG ĐẠT

Ngày chạy: 10/10/2026. Người chạy: Claude (theo brief §1.8: Claude chạy sau khi cho phép). Brief: `docs/superpowers/plans/2026-10-09-brief-dot-171-toi-uu-tham-so-octopus-walk-forward.md` (gồm §7).

## 0. Kết luận

**KHÔNG ĐẠT.** Bộ được chọn trên 2016–2019 là `tp_atr_mult=1,5, pullback_window=10, ema_trend=100` (PF 0,82). Ở 2020–2022, nó đạt 4/5 điều kiện nhưng **PF ròng 1,048 < 1,2**. Ghi theo quy tắc §5:

> **Tối ưu tham số octopus_pullback (12 bộ, walk-forward 2016–2019 / 2020–2022): KHÔNG có bộ tham số bền.** Phép đo âm thứ 16.

**Đề xuất:** ngừng phát triển `octopus_pullback`. Ở giai đoạn chọn, **không bộ nào có PF ≥ 1** (cao nhất 0,82). Ở giai đoạn kiểm, cao nhất là 1,11. Trên cùng mã, mua-và-giữ lãi 387,8 tỷ (2016–2019) và 668,9 tỷ (2020–2022), còn chiến lược dao động trong khoảng ±0,5 tỷ.

**Cảnh báo bắt buộc** (spec mục H 09/10 và 10/10):
1. Đây là giả thuyết thứ 4 trong tháng (vượt ngân sách mục F), 12 bộ tham số, nên có đa so sánh.
2. Thiên lệch sống sót: universe gần như chỉ gồm mã còn sống (1/1.284 mã có nến cuối trước 30/06/2022), theo quyết định không dùng mã đã hủy niêm yết. Mua-và-giữ cùng mã cũng bị thổi phồng; kết luận "thua mua-và-giữ" không đổi chiều vì chênh lệch quá lớn.

## 1. Hai lần chạy (§1.8 yêu cầu báo cả hai)

| Lần | Giờ | Kết quả | Lý do |
|---|---|---|---|
| 1 | 10:34 | EXIT=1 lúc **import**, chưa đọc dữ liệu, không có số nào | Refactor `2dc80b1` (của Claude) import `is_stock_symbol` từ `screen_momentum_portfolio.py`; chạy trực tiếp thì thiếu thư mục gốc repo trong `sys.path`. Sửa ở `33272e1` |
| 2 | 10:38 | EXIT=0, kết quả dưới đây | — |

Trước đó, ngày 09/10, một lệnh kiểm cổng của Claude đã vô tình khởi động phép đo và bị dừng trước khi in bất kỳ kết quả nào; output chỉ có `[killed]` (bộ nhớ "khong-chay-lenh-that-de-kiem-cong").

## 2. Kết quả nguyên văn

Universe 1.284 mã cổ phiếu (sau `exclusions.txt`), vốn 1 tỷ/mã, phí/thuế/T+2,5 theo `run_backtest`.

**Giai đoạn CHỌN 2016–2019** (xếp hạng theo PF ròng):

| Bộ | Hạng | Lệnh | Win | PF ròng | PnL ròng (VND) |
|---|---|---|---|---|---|
| TP=1.5_W=10_EMA=100 | **1** | 426 | 38,3% | **0,8203** | −303.858.553 |
| TP=2.0_W=10_EMA=100 | 2 | 426 | 35,7% | 0,7931 | −351.784.646 |
| TP=3.0_W=10_EMA=100 | 3 | 426 | 35,0% | 0,7597 | −409.149.952 |
| TP=1.5_W=5_EMA=100 | 4 | 333 | 37,5% | 0,7535 | −334.506.619 |
| TP=1.5_W=10_EMA=200 | 5 | 338 | 37,9% | 0,7433 | −359.681.416 |
| TP=2.0_W=10_EMA=200 | 6 | 338 | 35,2% | 0,7299 | −381.010.847 |
| TP=1.5_W=5_EMA=200 | 7 | 265 | 37,7% | 0,7100 | −321.503.205 |
| TP=2.0_W=5_EMA=100 | 8 | 333 | 34,2% | 0,7025 | −409.224.276 |
| TP=3.0_W=10_EMA=200 | 9 | 338 | 34,9% | 0,6966 | −427.989.597 |
| **TP=2.0_W=5_EMA=200 (mặc định)** | 10 | 265 | 34,3% | 0,6770 | −362.949.391 |
| TP=3.0_W=5_EMA=100 | 11 | 333 | 33,3% | 0,6434 | −492.804.948 |
| TP=3.0_W=5_EMA=200 | 12 | 265 | 34,0% | 0,6178 | −430.680.450 |

Mua-và-giữ cùng mã: 387.794.127.076.

**Giai đoạn KIỂM 2020–2022:**

| Bộ | Hạng | Lệnh | Win | PF ròng | PnL ròng (VND) |
|---|---|---|---|---|---|
| TP=1.5_W=10_EMA=200 | 1 | 750 | 43,2% | 1,1084 | 280.412.732 |
| TP=2.0_W=10_EMA=200 | 2 | 750 | 40,4% | 1,0679 | 178.386.997 |
| **TP=1.5_W=10_EMA=100 (được chọn)** | **3** | 797 | 42,0% | **1,0478** | 135.213.161 |
| TP=3.0_W=10_EMA=200 | 4 | 750 | 39,9% | 1,0350 | 92.083.220 |
| TP=2.0_W=10_EMA=100 | 5 | 797 | 39,4% | 1,0142 | 40.549.241 |
| TP=3.0_W=10_EMA=100 | 6 | 797 | 38,9% | 0,9828 | −49.632.168 |
| TP=1.5_W=5_EMA=200 | 7 | 574 | 40,2% | 0,9567 | −91.093.553 |
| TP=1.5_W=5_EMA=100 | 8 | 612 | 39,4% | 0,9181 | −190.703.549 |
| **TP=2.0_W=5_EMA=200 (mặc định)** | 9 | 574 | 37,5% | 0,9048 | −203.817.443 |
| TP=3.0_W=5_EMA=200 | 10 | 574 | 36,9% | 0,8748 | −268.593.548 |
| TP=2.0_W=5_EMA=100 | 11 | 612 | 36,8% | 0,8712 | −303.909.959 |
| TP=3.0_W=5_EMA=100 | 12 | 612 | 36,3% | 0,8418 | −373.939.323 |

Mua-và-giữ cùng mã: 668.851.032.061.

**Năm điều kiện** (bộ được chọn, 2020–2022): ≥ 100 lệnh ĐẠT (797) · **PF > 1,2 KHÔNG ĐẠT (1,0478)** · PnL > 0 ĐẠT · PF > mặc định ĐẠT (1,0478 > 0,9048) · top 3/12 ĐẠT (hạng 3).

Tương quan hạng Spearman của PF giữa hai giai đoạn (12 bộ): **0,615, p = 0,033**.

## 3. Kiểm chứng độc lập của Claude
Chạy `scripts/measure_strategy.py` (công cụ đo có sẵn, không dùng code đợt 171) với `--strategy octopus_pullback --from 2016-01-01 --to 2019-12-31` trên đúng 1.284 mã. Kết quả: **265 lệnh, −362.949.391**, mua-và-giữ 387.794.127.076. **Khớp chính xác** dòng bộ mặc định ở giai đoạn chọn.

## 4. Đọc thêm (mô tả, không đổi kết luận)
- Thứ hạng tham số **khá bền** (Spearman 0,62, p = 0,03): `pullback_window = 10` đứng trên `= 5` ở **cả 12 cặp so sánh** của hai giai đoạn. Đây là quan sát về hình dạng, không phải lợi thế, vì ngay bộ tốt nhất vẫn có PF dưới 1 ở 2016–2019.
- Giai đoạn 2020–2022 đẹp hơn 2016–2019 với mọi bộ tham số. Nhiều khả năng do thị trường 2020–2021 tăng mạnh hơn, không phải do tham số.
- Không dùng con số nào ở đây để đổi tham số engine. Theo §5, chỉ khi ĐẠT mới có bước paper forward.
