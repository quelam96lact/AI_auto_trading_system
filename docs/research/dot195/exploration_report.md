# Báo cáo khám phá Đợt 195: Xu hướng ngày (MA) + Vào lệnh 1 giờ (RSI) + Thoát ATR ngày

> [!WARNING]
> **Cảnh báo thiên lệch (§0):** Danh sách khoảng 300 mã có nến 5 phút là universe collector chọn theo thanh khoản ở thời điểm gần đây, nên có thiên lệch nhìn trước nhẹ; dữ liệu không có mã huỷ niêm yết. Phép so với EW trên cùng universe vẫn đứng vững.

## 1. Cấu hình được chọn (Sharpe_X cao nhất)

- **Tham số:** `n=100`, `theta=40.0`, `k=3.0`
- **Số lệnh:** 110
- **Số tuần:** 17
- **mean_X:** 0.002989
- **sharpe_X:** 0.0324
- **p (bootstrap tuần):** 0.2935
- **mean_r (lãi ròng sau phí):** -0.016857
- **mean_EW:** -0.019846
- **Tỷ lệ thắng (r > 0):** 26.36%
- **Trung vị số nến 1h giữ:** 45.5
- **Trung vị số phiên giữ:** 10.5
- **Thoát lệnh theo lý do:** STOP=38, TREND=58, END=14
- **sharpe_w (tuần):** 0.1460
- **DSR Bước 4:** không tính

## 2. Kiểm tra cao nguyên (Bước 2)

- **Kết quả:** TRƯỢT

| Láng giềng | mean_X | sharpe_X | Ngưỡng sharpe (>= 50%) | Kết quả |
|---|---|---|---|---|
| `n=50, theta=40.0, k=3.0` | -0.002776 | -0.0378 | 0.0162 | TRƯỢT |
| `n=100, theta=30.0, k=3.0` | -0.007308 | -0.1100 | 0.0162 | TRƯỢT |
| `n=100, theta=40.0, k=2.0` | -0.001633 | -0.0212 | 0.0162 | TRƯỢT |

## 3. Tiêu chí lựa chọn (Bước 3 & 4)

- `mean_X > 0` và `p < 0.05`: TRƯỢT (mean_X=0.002989, p=0.2935)
- `mean_r > 0`: TRƯỢT (mean_r=-0.016857)
- `n >= 100`: ĐẠT (n=110)
- `DSR >= 0.95`: không tính

## 4. Bảng tổng hợp 8 cấu hình (Grid)

| n | theta | k | Số lệnh | mean_X | sharpe_X | p | mean_r | Trung vị phiên giữ |
|---|---|---|---|---|---|---|---|---|
| 50 | 30.0 | 2.0 | 46 | -0.005328 | -0.0772 | 0.7170 | -0.024981 | 4.5 |
| 50 | 30.0 | 3.0 | 42 | -0.007535 | -0.1325 | 0.8194 | -0.028175 | 5.0 |
| 50 | 40.0 | 2.0 | 137 | -0.003660 | -0.0518 | 0.7409 | -0.021240 | 6.0 |
| 50 | 40.0 | 3.0 | 113 | -0.002776 | -0.0378 | 0.6731 | -0.023700 | 7.0 |
| 100 | 30.0 | 2.0 | 54 | -0.005773 | -0.0804 | 0.7436 | -0.021177 | 9.0 |
| 100 | 30.0 | 3.0 | 47 | -0.007308 | -0.1100 | 0.8380 | -0.026600 | 10.0 |
| 100 | 40.0 | 2.0 | 141 | -0.001633 | -0.0212 | 0.6636 | -0.016765 | 9.0 |
| 100 | 40.0 | 3.0 | 110 | 0.002989 | 0.0324 | 0.2935 | -0.016857 | 10.5 |

## 5. Kết luận

- **Số ứng viên vào cổng kiểm chứng:** 0
- **SHA256 candidates.json:** `fc25c2ea5e68bdac506901971fa0338e01bc3eb373a118728daa04d0d3e10437`
