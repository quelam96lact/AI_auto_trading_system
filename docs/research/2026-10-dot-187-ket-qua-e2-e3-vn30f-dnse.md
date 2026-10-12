# Đợt 187: kết quả đo E2/E3 order flow VN30F với ngưỡng tương đối trên DNSE, chạy một lần ngày 12/10/2026

- Thiết kế đăng ký trước: `docs/superpowers/plans/2026-10-12-brief-dot-187-e2-e3-vn30f-nguong-tuong-doi-dnse.md`, spec H ngày 12/10.
- Lệnh: `uv run python scripts/screen_vn30f_orderflow_dnse_187.py --data-dir data/dnse_trades` tại commit `f5f1e8f`. Chạy **một lần**, mã thoát 0.
- Dự đoán ghi trước: không cặp nào ĐẠT.

## Kiểm cài đặt (§6 bước 3)
Trước khi chạy, Claude đếm lại bằng code riêng, chỉ đếm, không tính y. Output khớp tuyệt đối:
- tỷ lệ nến có imbalance cả hai phía 33,4%;
- N và số sự kiện mua/bán của cả 4 cặp: 175 (68/107), 133 (52/81), 110 (53/57), 90 (42/48).

## Phán quyết
**TRƯỢT cả 4 cặp ở tập CHÍNH.** k = 0 nên không xét LẶP LẠI.

| Cặp | Trung bình y (điểm) | p | Hurdle |
|---|---|---|---|
| E2_H15 | +0,09 | 0,39 | 1,06 |
| E2_H30 | −0,10 | 0,61 | 1,06 |
| E3_H15 | −0,34 | 0,85 | 1,06 |
| E3_H30 | −0,28 | 0,69 | 1,06 |

- Không cặp nào gần ngưỡng p = 0,0125. Trung bình y cao nhất (+0,09) chưa bằng 1/10 hurdle.
- **E3_H30 chỉ có 90 sự kiện**, dưới mức tối thiểu 100. Lỗi hiệu chỉnh của Claude: lưới tần suất đếm sự kiện *trước* bước loại sự kiện không có giá thoát (gần cuối phiên), nên ước 109 thay vì 90. Lỗi này không đổi kết luận, vì E3_H30 trượt cả p lẫn hurdle, với trung bình y âm.

**Kết luận chung của 186 + 187:** cả ba sự kiện order flow footprint (E1 lệch CVD, E2 lệch delta trong nến, E3 hấp thụ chuyển chủ động) đều **không có lợi thế** trên VN30F, đo trên 123 phiên DNSE có bên chủ động thật. Order flow VN30F theo bộ sự kiện này coi như đã đóng.

## Output nguyên văn
```
================================================================================================
  BRIEF ĐỢT 187 — SÀNG LỌC E2/E3 ORDER FLOW VN30F VỚI NGƯỠNG TƯƠNG ĐỐI (DNSE)
  Tập CHÍNH  : 2026-03-25 -> 2026-06-30 (yêu cầu >= 40 phiên hợp lệ)
  Tập LẶP LẠI: 2026-07-01 -> 2026-09-24 (yêu cầu >= 30 phiên hợp lệ)
================================================================================================

[TẬP CHÍNH] Tổng phiên: 67 | Hợp lệ: 67 | Không hợp lệ: 0

[TẬP LẶP LẠI] Tổng phiên: 59 | Hợp lệ: 56 | Không hợp lệ: 3
  * Ngày 2026-08-28 (41I1G9000): thiếu KL liên tục 3.3%
  * Ngày 2026-09-03 (41I1G9000): thiếu KL liên tục 2.4%
  * Ngày 2026-09-04 (41I1G9000): thiếu KL liên tục 3.1%

[BIẾN ĐỐI CHỨNG] Spearman rho giữa delta và ret_same_5m trên CHÍNH: 0.8295
[TIÊU CHUẨN KINH TẾ] Trung vị Close CHÍNH: 1990.80 | Hurdle CHÍNH: 1.0552 điểm

[CHẶN SUY BIẾN] Tỷ lệ nến CHÍNH có imbalance cả 2 phía (bỏ 5 phiên đầu): 33.4%

================================================================================================
  BẢNG KẾT QUẢ TẬP CHÍNH (2026-03-25 -> 2026-06-30)
  Ngưỡng alpha = 0.0125 (Bonferroni 0.05 / 4)
Cặp            N   N Mua   N Bán     Mean y   Hurdle    p-value    Kết quả
------------------------------------------------------------------------------------------------
E2_H15       175      68     107     0.0897   1.0552     0.3895      TRƯỢT
E2_H30       133      52      81    -0.1000   1.0552     0.6140      TRƯỢT
E3_H15       110      53      57    -0.3400   1.0552     0.8515      TRƯỢT
E3_H30        90      42      48    -0.2800   1.0552     0.6875      TRƯỢT
================================================================================================

================================================================================================
  BẢNG KẾT QUẢ TẬP LẶP LẠI (2026-07-01 -> 2026-09-24)
LẶP LẠI: không có cặp nào để kiểm
================================================================================================

================================================================================================
  PHÁN QUYẾT CUỐI CÙNG BRIEF ĐỢT 187
  KẾT LUẬN: Không có cặp nào ĐẠT cả hai tập CHÍNH và LẶP LẠI.
================================================================================================
EXIT=0
```
