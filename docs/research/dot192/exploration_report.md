# Báo Cáo Khám Phá Hiệu Ứng Lịch Đầu Tháng Và Trước Nghỉ Lễ (Brief 192)

> [!IMPORTANT]
> **CẢNH BÁO THIÊN LỆCH SỐNG SÓT (SURVIVORSHIP BIAS):**
> Dữ liệu `stocks_daily` gần như không có mã đã huỷ niêm yết; theo quyết định của chủ dự án và spec H ngày 25/10, nghiên cứu không dùng mã huỷ. Mọi đánh giá hiệu quả chỉ mang tính so sánh tương đối với baseline cùng universe.

- **Tổng số thử nghiệm EA đã ghi sổ:** 18 cấu hình.
- **Tổng số thử nghiệm EB đã ghi sổ:** 0 cấu hình.
- **Số ứng viên vượt qua toàn bộ 4 bước:** 0.
- **SHA256 của `candidates.json`:** `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`

---

## 1. Kết Quả Từng Ý Tưởng Qua Các Bước

### I1_TOM
- **Trạng thái:** `REJECTED`
- **Lý do loại / Kết luận:** Không đạt cao nguyên: {'k': 2, 'm': 4}: net_mean=-0.007448826755737871, sharpe=-0.12103249677579497, {'k': 3, 'm': 3}: net_mean=-0.007784940753111767, sharpe=-0.1307321734177946
- **Cấu hình chọn (EA):** `{'k': 3, 'm': 4}`

| Giai đoạn | n | Lãi gộp TB | Lãi ròng TB | Sharpe | p | CAGR | MDD | Calmar | Vượt Baseline Trim1% | Số cửa sổ | Mã TB / cửa sổ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **EA** | 467 | 0.10% | -0.66% | -0.097 | 0.8555 | -8.15% | 30.59% | -0.27 | -1.05% | 47 | 9.9 |

- **Cao nguyên:** TRƯỢT.
- **DSR (EA):** không tính

### I2_PREHOL
- **Trạng thái:** `REJECTED`
- **Lý do loại / Kết luận:** Không đạt cao nguyên: {'n': 3, 'q': 3}: net_mean=-0.005000761840994894, sharpe=-0.07833524010234735, {'n': 4, 'q': 2}: net_mean=-0.003517739514082032, sharpe=-0.0647018783347532
- **Cấu hình chọn (EA):** `{'n': 4, 'q': 3}`

| Giai đoạn | n | Lãi gộp TB | Lãi ròng TB | Sharpe | p | CAGR | MDD | Calmar | Vượt Baseline Trim1% | Số cửa sổ | Mã TB / cửa sổ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **EA** | 198 | 0.40% | -0.36% | -0.054 | 0.6165 | -0.73% | 20.72% | -0.04 | -0.59% | 20 | 9.9 |

- **Cao nguyên:** TRƯỢT.
- **DSR (EA):** không tính

---

## 2. Danh Sách Ứng Viên Chốt

> [!NOTE]
> **Không có ứng viên nào vượt qua toàn bộ 4 bước lọc khắt khe (0 ứng viên là kết quả hợp lệ theo §5).**
> Toàn bộ các ý tưởng được ghi nhận là phép đo âm để bảo vệ vốn và không nới lỏng tiêu chuẩn.
