# Đợt 184: kết quả đo order flow crypto (BTCUSDT perp), chạy một lần ngày 12/10/2026

- Thiết kế đăng ký trước: brief 183/183b, mở cổng ở đợt 184 (`HOLDOUT_START_DATE = 2026-10-12`).
- Lệnh: `uv run python scripts/screen_crypto_orderflow.py` tại commit `1bd4803`, cây làm việc sạch. Chạy **một lần**, mã thoát 0.
- Dự đoán ghi trước (183 §1.5): không cặp nào ĐẠT.

## Phán quyết
**TRƯỢT cả 6 cặp.** Kiểm đối chứng ĐẠT (ρ = 0,7242 > 0,3), nghĩa là dữ liệu bên chủ động đáng tin, nên kết luận trượt không phải do dữ liệu hỏng.

- Không cặp nào qua tập CHÍNH. Giá trị p nhỏ nhất là 0,2065 (E1_15m), quá xa ngưỡng 0,05/6.
- Trung bình y của mọi cặp xấp xỉ 0, có cặp âm.
- Tập LẶP LẠI cũng không có tín hiệu. Bảng in LẶP LẠI cho cả 6 cặp chỉ để tham khảo; theo quy tắc, k = 0 nên không xét LẶP LẠI.

Order flow footprint trên BTCUSDT perp (E1 lệch CVD, E2 lệch delta trong nến, E3 hấp thụ chuyển chủ động; H 15/30 phút) **không có lợi thế**. Đây là thêm một phép đo âm cho crypto, sau đợt 42 và đợt 105–106. Theo 183 §1.4, không đảo chiều, không đổi H, không đổi ngưỡng.

## Output nguyên văn
```
====================================================================================
  BRIEF ĐỢT 183b — SÀNG LỌC ORDER FLOW FOOTPRINT BTCUSDT PERP (ĐĂNG KÝ TRƯỚC)
  Ngày hiện tại (giờ VN): 2026-10-12
  Mốc bắt đầu đo        : 2026-10-12
====================================================================================

Kiểm đối chứng rho: 0.7242 > 0.3 (ĐẠT)
Số cặp đạt ở CHÍNH: 0/6 (Ngưỡng p LẶP LẠI: 0.0500)
------------------------------------------------------------------------------------
Cặp        | CHÍNH (N/Buy/Sell)   | Mean y     | p-val    | LẶP LẠI (N/Mean/p)   | Kết luận
------------------------------------------------------------------------------------
E1_15m     | 15862/7139/8723      | 0.0000     | 0.2065   | 14962/-0.0000/0.5550 | TRƯỢT
E1_30m     | 12418/5649/6769      | 0.0000     | 0.3790   | 11312/0.0000/0.3140  | TRƯỢT
E2_15m     | 795/353/442          | -0.0001    | 0.7300   | 1333/0.0001/0.2200   | TRƯỢT
E2_30m     | 743/326/417          | -0.0002    | 0.7545   | 1203/0.0001/0.3275   | TRƯỢT
E3_15m     | 4140/2122/2018       | -0.0000    | 0.8375   | 3763/-0.0000/0.5410  | TRƯỢT
E3_30m     | 3711/1911/1800       | -0.0001    | 0.9160   | 3346/-0.0001/0.8530  | TRƯỢT
====================================================================================
EXIT=0
```
