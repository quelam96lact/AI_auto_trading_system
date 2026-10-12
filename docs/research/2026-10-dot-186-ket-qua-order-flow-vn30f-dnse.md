# Đợt 186: kết quả đo order flow VN30F trên lịch sử lệnh khớp DNSE, chạy một lần ngày 12/10/2026

- Thiết kế đăng ký trước: `docs/superpowers/plans/2026-10-11-brief-dot-186-order-flow-vn30f-lich-su-dnse.md`.
- Lệnh: `uv run python scripts/screen_vn30f_orderflow_dnse.py --data-dir data/dnse_trades` tại commit `7f3291e`, cây làm việc sạch. Chạy **một lần**, mã thoát 0.
- Dự đoán ghi trước: không cặp nào ĐẠT.

## Dữ liệu (§6 bước 2)
- Tải 25/03 → 24/09/2026: 126 phiên có file. 6 ngày nghỉ không có lệnh nào: 27/04, 30/04, 01/05, 31/08, 01/09, 02/09.
- `--verify`: 123 phiên đạt. **3 phiên thiếu khối lượng trong phiên liên tục:** 28/08 (3,29%), 03/09 (2,43%), 04/09 (3,07%).
- **Tải lại 3 phiên đó:** kết quả giống hệt từng lệnh. Lỗ nằm ở nguồn DNSE: 19–24 đoạn 10–50 giây rải rác trong phiên, không phải lỗi phân trang. Bản cũ giữ ngoài repo để so.
- Theo §1.2, ba phiên này không hợp lệ và bị loại. Không nới ngưỡng.

## Phán quyết
**TRƯỢT cả 6 cặp ở tập CHÍNH.** Vì k = 0 nên không xét tập LẶP LẠI. Kiểm đối chứng ĐẠT (ρ = 0,83), nghĩa là trường `side` của DNSE đáng tin.

- **E1 (lệch CVD) đủ mẫu và âm thật:** 102 và 75 sự kiện, trung bình y −0,20 và −0,17 điểm, tức sai dấu. p là 0,68 và 0,58, trong khi hurdle là 1,06 điểm.
- **E2 và E3 gần như không xảy ra:** chỉ 4–5 sự kiện trong 67 phiên, xa mức tối thiểu 100. Với hai loại này, kết luận đúng là *không đo được*, không phải *đã chứng minh không có lợi thế*.

**Hệ quả cho đợt 182:** đợt 182 dùng cùng ngưỡng sự kiện, đo trên 40 phiên từ 25/09. Gần như chắc chắn E2/E3 cũng chỉ có vài sự kiện, nên sẽ trượt vì thiếu mẫu, còn E1 đã có một kết quả âm độc lập. Đổi ngưỡng E2/E3 *bây giờ* là quyết định của chủ dự án. Ngưỡng mới phải chọn theo tần suất sự kiện, không theo kết quả, và phải ghi vào spec H trước khi 182 đo.

## Output nguyên văn
```
================================================================================================
  BRIEF ĐỢT 186 — SÀNG LỌC ORDER FLOW VN30F TRÊN LỊCH SỬ KHỚP LỆNH DNSE
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

================================================================================================
  BẢNG KẾT QUẢ TẬP CHÍNH (2026-03-25 -> 2026-06-30)
Cặp            N   N Mua   N Bán     Mean y   Hurdle    p-value    Kết quả
------------------------------------------------------------------------------------------------
E1_H15       102      43      59    -0.2029   1.0552     0.6840      TRƯỢT
E1_H30        75      34      41    -0.1733   1.0552     0.5775      TRƯỢT
E2_H15         5       5       0    -0.9000   1.0552     0.5490      TRƯỢT
E2_H30         4       4       0    -6.8000   1.0552     0.9280      TRƯỢT
E3_H15         5       0       5     0.5600   1.0552     0.2765      TRƯỢT
E3_H30         4       0       4     1.5000   1.0552     0.2575      TRƯỢT
================================================================================================

================================================================================================
  BẢNG KẾT QUẢ TẬP LẶP LẠI (2026-07-01 -> 2026-09-24)
LẶP LẠI: không có cặp nào để kiểm
================================================================================================

================================================================================================
  PHÁN QUYẾT CUỐI CÙNG BRIEF ĐỢT 186
  KẾT LUẬN: Không có cặp nào ĐẠT cả hai tập CHÍNH và LẶP LẠI.
================================================================================================
EXIT=0
```
