# Báo Cáo Khám Phá Chiến Lược Khối Ngoại Chốt Lời +10% (Brief 191)

> [!IMPORTANT]
> **CẢNH BÁO THIÊN LỆCH SỐNG SÓT (SURVIVORSHIP BIAS):**
> Dữ liệu `bars_daily` gần như không có mã đã huỷ niêm yết; theo quyết định của chủ dự án và spec H ngày 10/10, nghiên cứu không dùng mã huỷ. Mọi đánh giá hiệu quả chỉ mang tính so sánh tương đối với baseline cùng universe.

- **Tổng số thử nghiệm EA đã ghi sổ:** 99 cấu hình.
- **Tổng số thử nghiệm EB đã ghi sổ:** 3 cấu hình.
- **Số ứng viên vượt qua toàn bộ 4 bước:** 0.
- **SHA256 của `candidates.json`:** `d13443f3f28f09e45809b94b4d78b0a8b32d0e6e9e23477a575d4e61b06336d0`

---

## 1. Kết Quả Từng Ý Tưởng Qua Các Bước

### IDEA1_FOREIGN_ACCUMULATION_STREAK
- **Trạng thái:** `REJECTED`
- **Lý do loại / Kết luận:** Trượt EB: mean_net=-0.58% <= 0, p=0.6635 >= 0.05, calmar=-0.55 < 0.86, excess_trim1pct=-1.13% <= 0
- **Cấu hình chọn (EA):** `{'k': 3, 'min_ratio': 0.08, 'tp': 0.2}`

| Giai đoạn | n | Lãi ròng TB | Sharpe | p | Calmar | Vượt Baseline Trim1% | Tỷ lệ TP | Tỷ lệ SL | Tỷ lệ TIME | Tỷ lệ END | Lãi TB TP | Lỗ TB SL | Số phiên giữ TB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **EA** | 203 | 4.40% | 0.330 | 0.0010 | 3.88 | -1.75% | 40.4% | 49.3% | 10.3% | 0.0% | 19.26% | -8.27% | 17 |
| **EB** | 525 | -0.58% | -0.047 | 0.6635 | -0.55 | -1.13% | 25.0% | 65.5% | 6.3% | 3.2% | 19.60% | -8.67% | 8 |

- **Cao nguyên:** ĐẠT (tất cả các láng giềng ±1 bước đều có lãi dương và Sharpe >= 50%).

### IDEA2_FOREIGN_CROSS_SECTION_TOP
- **Trạng thái:** `REJECTED`
- **Lý do loại / Kết luận:** Trượt EB: p=0.5015 >= 0.05, calmar=-0.20 < 0.86, excess_trim1pct=-0.73% <= 0
- **Cấu hình chọn (EA):** `{'q': 10, 'threshold': 0.05, 'tp': 0.2}`

| Giai đoạn | n | Lãi ròng TB | Sharpe | p | Calmar | Vượt Baseline Trim1% | Tỷ lệ TP | Tỷ lệ SL | Tỷ lệ TIME | Tỷ lệ END | Lãi TB TP | Lỗ TB SL | Số phiên giữ TB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **EA** | 143 | 3.37% | 0.261 | 0.0020 | 2.39 | -2.80% | 35.0% | 53.8% | 11.2% | 0.0% | 19.19% | -8.12% | 18 |
| **EB** | 423 | 0.02% | 0.002 | 0.5015 | -0.20 | -0.73% | 25.1% | 62.4% | 8.0% | 4.5% | 19.34% | -8.28% | 10 |

- **Cao nguyên:** ĐẠT (tất cả các láng giềng ±1 bước đều có lãi dương và Sharpe >= 50%).

### IDEA3_FOREIGN_DIVERGENCE_DIP
- **Trạng thái:** `REJECTED`
- **Lý do loại / Kết luận:** Thiếu mẫu (không có cấu hình nào n >= 100 trên EA, max n=98)

### IDEA4_FOREIGN_REVERSAL_SURGE
- **Trạng thái:** `REJECTED`
- **Lý do loại / Kết luận:** Trượt EB: mean_net=-0.97% <= 0, p=0.7865 >= 0.05, calmar=-0.51 < 0.86, excess_trim1pct=-1.57% <= 0
- **Cấu hình chọn (EA):** `{'m': 1.5, 'spike_ratio': 0.15, 'tp': 0.2}`

| Giai đoạn | n | Lãi ròng TB | Sharpe | p | Calmar | Vượt Baseline Trim1% | Tỷ lệ TP | Tỷ lệ SL | Tỷ lệ TIME | Tỷ lệ END | Lãi TB TP | Lỗ TB SL | Số phiên giữ TB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **EA** | 178 | 4.95% | 0.377 | 0.0000 | 6.21 | -1.66% | 42.1% | 44.9% | 12.9% | 0.0% | 19.23% | -8.48% | 18 |
| **EB** | 299 | -0.97% | -0.083 | 0.7865 | -0.51 | -1.57% | 22.4% | 67.2% | 7.4% | 3.0% | 19.34% | -8.38% | 11 |

- **Cao nguyên:** ĐẠT (tất cả các láng giềng ±1 bước đều có lãi dương và Sharpe >= 50%).

### IDEA5_FOREIGN_ROOM_EXHAUSTION
- **Trạng thái:** `REJECTED`
- **Lý do loại / Kết luận:** Thiếu mẫu (không có cấu hình nào n >= 100 trên EA, max n=40)

---

## 2. Danh Sách Ứng Viên Chốt

> [!NOTE]
> **Không có ứng viên nào vượt qua toàn bộ 4 bước lọc khắt khe (0 ứng viên là kết quả hợp lệ theo §4.2).**
> Toàn bộ các ý tưởng được ghi nhận là phép đo âm để bảo vệ vốn và không nới lỏng tiêu chuẩn.
