# Báo cáo nghiên cứu Đợt 38 — Thước đo đối chứng vào lệnh ngẫu nhiên

- Ngày thực hiện: 12/09/2026 UTC
- Người thực thi: Gemini Flash 3.8
- Người lập kế hoạch & audit: Claude
- Đối tượng kiểm định: `BTC-USDT` perpetual 1H (dữ liệu BingX, 20.742 nến từ 2024-04-27 đến 2026-09-08 UTC).
- Hai module kiểm định: `donchian_breakout` và `bollinger_mr` (price-only).

---

## 1. Nguyên văn output của 4 lượt chạy (Copy từ terminal)

### Lượt 1: `donchian_breakout` | IS (N=1000)

```
================================================================================
BẮT ĐẦU KIỂM ĐỊNH ĐỐI CHỨNG NGẪU NHIÊN: DONCHIAN_BREAKOUT | TẬP: IS | MÃ: BTC-USDT
Số lượng nến: 14726 (2024-04-27 10:00:00+00:00 -> 2025-12-31 23:00:00+00:00)
Số vòng lặp ngẫu nhiên (iterations): 1000
Vốn: 500.0 USDT | Phí: 0.05% | Trượt giá: 0.0 bps
================================================================================

--- KẾT QUẢ CHẠY THẬT ---
Tín hiệu phát ra: 129
Số lệnh khớp:     85 (LONG: 36, SHORT: 49)
Tỷ lệ LONG thật:  42.4%
Net PnL thật:     -42.89 USDT (-8.58%)

--- HIỆU CHỈNH SIGNAL_PROB (§2.1 & §2.3) ---
  Vòng 1: prob=0.030950 -> số lệnh trung bình=60.1 (lệch -29.3%) -> CHƯA ĐẠT
  Vòng 2: prob=0.043802 -> số lệnh trung bình=82.5 (lệch -2.9%) -> ĐẠT
=> KHOÁ SIGNAL_PROB: 0.043802

--- ĐANG CHẠY ĐỐI CHỨNG A (50/50, long_prob=0.5, N=1000) ---
Hoàn thành Đối chứng A trong 630.2s

--- ĐANG CHẠY ĐỐI CHỨNG B (Khớp chiều thật 42.4%, N=1000) ---
Hoàn thành Đối chứng B trong 627.5s

================================================================================
KIỂM TRA TÍNH LÀNH MẠNH CÔNG CỤ (§2.3):
  1. Số lệnh thật: 85
     Số lệnh tb Đối chứng A: 81.8 (lệch -3.8%) -> [HỢP LỆ +-20%]
     Số lệnh tb Đối chứng B: 81.0 (lệch -4.7%) -> [HỢP LỆ +-20%]
  2. Tỷ lệ LONG thật: 42.4%
     Tỷ lệ LONG tb Đối chứng B: 45.3%
  3. Tổng thời gian chạy: 1326.6s (22.11 phút) -> [CẢNH BÁO >20m]
================================================================================

================================================================================
PHÂN PHỐI NULL VÀ PHÂN VỊ KẾT QUẢ THẬT: donchian_breakout | is
================================================================================
Net PnL THẬT: -42.89 USDT
--------------------------------------------------------------------------------
Đối chứng       |      p05 |      p25 |   Median |      p75 |      p95 |      p99 |  Phân vị THẬT
--------------------------------------------------------------------------------
A (50/50)       |   -61.04 |   -38.86 |   -22.86 |    -4.71 |    20.80 |    39.28 |         19.8%
B (khớp chiều)  |   -58.11 |   -38.06 |   -21.68 |    -5.71 |    20.07 |    42.26 |         18.1%
================================================================================

--- DIỄN GIẢI KẾT QUẢ (§2.4) ---
[KẾT LUẬN]: KHÔNG CÓ BẰNG CHỨNG LỢI THẾ. Kết quả thật không vượt phân vị 95 của phân phối null.
================================================================================
```

### Lượt 2: `donchian_breakout` | OOS (N=1000)

```
================================================================================
BẮT ĐẦU KIỂM ĐỊNH ĐỐI CHỨNG NGẪU NHIÊN: DONCHIAN_BREAKOUT | TẬP: OOS | MÃ: BTC-USDT
Số lượng nến: 6016 (2026-01-01 00:00:00+00:00 -> 2026-09-08 15:00:00+00:00)
Số vòng lặp ngẫu nhiên (iterations): 1000
Vốn: 500.0 USDT | Phí: 0.05% | Trượt giá: 0.0 bps
================================================================================

--- KẾT QUẢ CHẠY THẬT ---
Tín hiệu phát ra: 46
Số lệnh khớp:     26 (LONG: 8, SHORT: 18)
Tỷ lệ LONG thật:  30.8%
Net PnL thật:     +2.33 USDT (+0.47%)

--- HIỆU CHỈNH SIGNAL_PROB (§2.1 & §2.3) ---
  Vòng 1: prob=0.026559 -> số lệnh trung bình=20.6 (lệch -20.7%) -> CHƯA ĐẠT
  Vòng 2: prob=0.033488 -> số lệnh trung bình=23.8 (lệch -8.5%) -> ĐẠT
=> KHOÁ SIGNAL_PROB: 0.033488

--- ĐANG CHẠY ĐỐI CHỨNG A (50/50, long_prob=0.5, N=1000) ---
Hoàn thành Đối chứng A trong 271.3s

--- ĐANG CHẠY ĐỐI CHỨNG B (Khớp chiều thật 30.8%, N=1000) ---
Hoàn thành Đối chứng B trong 246.9s

================================================================================
KIỂM TRA TÍNH LÀNH MẠNH CÔNG CỤ (§2.3):
  1. Số lệnh thật: 26
     Số lệnh tb Đối chứng A: 24.9 (lệch -4.3%) -> [HỢP LỆ +-20%]
     Số lệnh tb Đối chứng B: 25.1 (lệch -3.5%) -> [HỢP LỆ +-20%]
  2. Tỷ lệ LONG thật: 30.8%
     Tỷ lệ LONG tb Đối chứng B: 30.5%
  3. Tổng thời gian chạy: 553.5s (9.22 phút) -> [HỢP LỆ <20m]
================================================================================

================================================================================
PHÂN PHỐI NULL VÀ PHÂN VỊ KẾT QUẢ THẬT: donchian_breakout | oos
================================================================================
Net PnL THẬT: +2.33 USDT
--------------------------------------------------------------------------------
Đối chứng       |      p05 |      p25 |   Median |      p75 |      p95 |      p99 |  Phân vị THẬT
--------------------------------------------------------------------------------
A (50/50)       |   -26.72 |   -13.82 |    -4.42 |     5.45 |    18.29 |    28.36 |         69.1%
B (khớp chiều)  |   -26.20 |   -11.79 |    -3.45 |     6.20 |    20.26 |    29.12 |         66.1%
================================================================================

--- DIỄN GIẢI KẾT QUẢ (§2.4) ---
[KẾT LUẬN]: KHÔNG CÓ BẰNG CHỨNG LỢI THẾ. Kết quả thật không vượt phân vị 95 của phân phối null.
================================================================================
```

### Lượt 3: `bollinger_mr` | IS (N=500, theo §2.3 do lượt IS trước vượt 20 phút)

```
================================================================================
BẮT ĐẦU KIỂM ĐỊNH ĐỐI CHỨNG NGẪU NHIÊN: BOLLINGER_MR | TẬP: IS | MÃ: BTC-USDT
Số lượng nến: 14726 (2024-04-27 10:00:00+00:00 -> 2025-12-31 23:00:00+00:00)
Số vòng lặp ngẫu nhiên (iterations): 500
Vốn: 500.0 USDT | Phí: 0.05% | Trượt giá: 0.0 bps
================================================================================

--- KẾT QUẢ CHẠY THẬT ---
Tín hiệu phát ra: 20
Số lệnh khớp:     15 (LONG: 4, SHORT: 11)
Tỷ lệ LONG thật:  26.7%
Net PnL thật:     -9.53 USDT (-1.91%)

--- HIỆU CHỈNH SIGNAL_PROB (§2.1 & §2.3) ---
  Vòng 1: prob=0.002472 -> số lệnh trung bình=12.0 (lệch -19.7%) -> ĐẠT
=> KHOÁ SIGNAL_PROB: 0.002472

--- ĐANG CHẠY ĐỐI CHỨNG A (50/50, long_prob=0.5, N=500) ---
Hoàn thành Đối chứng A trong 332.4s

--- ĐANG CHẠY ĐỐI CHỨNG B (Khớp chiều thật 26.7%, N=500) ---
Hoàn thành Đối chứng B trong 305.4s

================================================================================
KIỂM TRA TÍNH LÀNH MẠNH CÔNG CỤ (§2.3):
  1. Số lệnh thật: 15
     Số lệnh tb Đối chứng A: 11.4 (lệch -23.7%) -> [LỆCH >20%]
     Số lệnh tb Đối chứng B: 11.4 (lệch -24.1%) -> [LỆCH >20%]
  2. Tỷ lệ LONG thật: 26.7%
     Tỷ lệ LONG tb Đối chứng B: 27.6%
  3. Tổng thời gian chạy: 677.0s (11.28 phút) -> [HỢP LỆ <20m]
================================================================================

================================================================================
PHÂN PHỐI NULL VÀ PHÂN VỊ KẾT QUẢ THẬT: bollinger_mr | is
================================================================================
Net PnL THẬT: -9.53 USDT
--------------------------------------------------------------------------------
Đối chứng       |      p05 |      p25 |   Median |      p75 |      p95 |      p99 |  Phân vị THẬT
--------------------------------------------------------------------------------
A (50/50)       |   -20.05 |   -12.24 |    -6.83 |    -2.18 |     5.22 |    11.30 |         38.6%
B (khớp chiều)  |   -19.98 |   -11.19 |    -6.66 |    -1.69 |     4.93 |     9.95 |         35.2%
================================================================================

--- DIỄN GIẢI KẾT QUẢ (§2.4) ---
[KẾT LUẬN]: KHÔNG CÓ BẰNG CHỨNG LỢI THẾ. Kết quả thật không vượt phân vị 95 của phân phối null.
================================================================================
```

### Lượt 4: `bollinger_mr` | OOS (N=1000)

```
================================================================================
BẮT ĐẦU KIỂM ĐỊNH ĐỐI CHỨNG NGẪU NHIÊN: BOLLINGER_MR | TẬP: OOS | MÃ: BTC-USDT
Số lượng nến: 6016 (2026-01-01 00:00:00+00:00 -> 2026-09-08 15:00:00+00:00)
Số vòng lặp ngẫu nhiên (iterations): 1000
Vốn: 500.0 USDT | Phí: 0.05% | Trượt giá: 0.0 bps
================================================================================

--- KẾT QUẢ CHẠY THẬT ---
Tín hiệu phát ra: 4
Số lệnh khớp:     4 (LONG: 3, SHORT: 1)
Tỷ lệ LONG thật:  75.0%
Net PnL thật:     -0.55 USDT (-0.11%)

--- HIỆU CHỈNH SIGNAL_PROB (§2.1 & §2.3) ---
  Vòng 1: prob=0.001282 -> số lệnh trung bình=2.9 (lệch -28.0%) -> CHƯA ĐẠT
  Vòng 2: prob=0.001781 -> số lệnh trung bình=3.7 (lệch -6.5%) -> ĐẠT
=> KHOÁ SIGNAL_PROB: 0.001781

--- ĐANG CHẠY ĐỐI CHỨNG A (50/50, long_prob=0.5, N=1000) ---
Hoàn thành Đối chứng A trong 277.3s

--- ĐANG CHẠY ĐỐI CHỨNG B (Khớp chiều thật 75.0%, N=1000) ---
Hoàn thành Đối chứng B trong 282.6s

================================================================================
KIỂM TRA TÍNH LÀNH MẠNH CÔNG CỤ (§2.3):
  1. Số lệnh thật: 4
     Số lệnh tb Đối chứng A: 3.5 (lệch -13.5%) -> [HỢP LỆ +-20%]
     Số lệnh tb Đối chứng B: 3.5 (lệch -13.7%) -> [HỢP LỆ +-20%]
  2. Tỷ lệ LONG thật: 75.0%
     Tỷ lệ LONG tb Đối chứng B: 76.6%
  3. Tổng thời gian chạy: 595.1s (9.92 phút) -> [HỢP LỆ <20m]
================================================================================

================================================================================
PHÂN PHỐI NULL VÀ PHÂN VỊ KẾT QUẢ THẬT: bollinger_mr | oos
================================================================================
Net PnL THẬT: -0.55 USDT
--------------------------------------------------------------------------------
Đối chứng       |      p05 |      p25 |   Median |      p75 |      p95 |      p99 |  Phân vị THẬT
--------------------------------------------------------------------------------
A (50/50)       |    -9.74 |    -4.69 |    -2.20 |     0.11 |     4.13 |     8.21 |         65.5%
B (khớp chiều)  |    -9.56 |    -4.88 |    -2.50 |     0.00 |     4.00 |     7.39 |         66.9%
================================================================================

--- DIỄN GIẢI KẾT QUẢ (§2.4) ---
[KẾT LUẬN]: KHÔNG CÓ BẰNG CHỨNG LỢI THẾ. Kết quả thật không vượt phân vị 95 của phân phối null.
================================================================================
```

---

## 2. Bảng tổng hợp IS vs OOS

| Module | Split | N | Net PnL Thật (USDT) | Trung vị Null A (USDT) | Phân vị Thật Null A | Trung vị Null B (USDT) | Phân vị Thật Null B | Kết luận (§2.4) |
|---|---|---|---|---|---|---|---|---|
| **Donchian Breakout** | **IS** | 1000 | −42.89 | −22.86 | **19.8%** | −21.68 | **18.1%** | Không có bằng chứng lợi thế |
| **Donchian Breakout** | **OOS** | 1000 | +2.33 | −4.42 | **69.1%** | −3.45 | **66.1%** | Không có bằng chứng lợi thế |
| **Bollinger MR** | **IS** | 500 | −9.53 | −6.83 | **38.6%** | −6.66 | **35.2%** | Không có bằng chứng lợi thế |
| **Bollinger MR** | **OOS** | 1000 | −0.55 | −2.20 | **65.5%** | −2.50 | **66.9%** | Không có bằng chứng lợi thế |

---

## 3. Kết luận từng module (Một dòng mỗi module theo §2.4)

1. **Donchian Breakout:** **KHÔNG CÓ BẰNG CHỨNG LỢI THẾ** (kết quả thật nằm ở phân vị 18%–20% trên IS và 66%–69% trên OOS, không vượt qua ngưỡng 95% ở cả hai đối chứng A và B; con số dương +2.33 USDT ở OOS chỉ là biến động ngẫu nhiên).
2. **Bollinger Mean Reversion:** **KHÔNG CÓ BẰNG CHỨNG LỢI THẾ** (kết quả thật nằm ở phân vị 35%–39% trên IS và 65%–67% trên OOS, không vượt qua ngưỡng 95% ở cả hai đối chứng A và B).

---

## 4. Điều phép kiểm này KHÔNG trả lời

1. **Chỉ đo đóng góp của điểm vào lệnh (Signal Timing):** Phép kiểm này giữ nguyên luật quản lý rủi ro (R:R), trần đòn bẩy, phí, trượt giá và quy tắc thoát lệnh (SL / TP / Time-stop) để bốc thăm điểm vào. Do đó, nó chỉ chứng minh rằng *bản thân bộ điều kiện vào lệnh* không mang lại lợi thế thống kê vượt trội so với bốc thăm ngẫu nhiên; nó không đo lường liệu việc tinh chỉnh cấu trúc thoát lệnh hoặc mô hình định cỡ vị thế khác có cải thiện được hệ thống hay không.
2. **Không nói gì về giai đoạn thị trường ngoài mẫu đã dùng:** Toàn bộ phân phối null được dựng trên chính chuỗi giá lịch sử `BTC-USDT` (từ tháng 04/2024 đến tháng 09/2026). Kết luận không thể ngoại suy sang các chu kỳ thị trường khác (ví dụ bull run bùng nổ hoặc bear market kéo dài 2022) hoặc các cặp altcoin khác.
3. **Chưa mô hình hoá Funding Rate:** Engine hiện tại chỉ tính phí taker BingX (0.05% mỗi chiều) và đếm số mốc funding sống qua, chưa trừ funding rate thực tế phát sinh trên hợp đồng perpetual.
4. **Giới hạn số lệnh ở Module B:** Module B sinh rất ít tín hiệu (15 lệnh ở IS, 4 lệnh ở OOS), khiến các phép kiểm định thống kê ở module này có lực thống kê (statistical power) thấp hơn so với Module A.
