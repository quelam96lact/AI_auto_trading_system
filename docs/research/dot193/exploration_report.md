# Báo Cáo Khám Phá Danh Mục Biến Động Thấp Xoay Vòng Tháng (Brief 193)

> [!IMPORTANT]
> **CẢNH BÁO THIÊN LỆCH SỐNG SÓT (SURVIVORSHIP BIAS):**
> Dữ liệu `stocks_daily` gần như không có mã đã huỷ niêm yết; theo quyết định của chủ dự án và spec H ngày 25/10, nghiên cứu không dùng mã huỷ. Mã huỷ thường là mã biến động cao và lỗ nặng; khi thiếu chúng, nhóm biến động cao trông tốt hơn thật, nên phép so sánh đang bất lợi tương đối cho chiến lược biến động thấp.

- **Tổng số thử nghiệm EA đã ghi sổ:** 18 cấu hình.
- **Tổng số thử nghiệm EB đã ghi sổ:** 0 cấu hình.
- **Số ứng viên vượt qua toàn bộ 4 bước:** 0.
- **SHA256 của `candidates.json`:** `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`

---

## 1. Kết Quả Từng Ý Tưởng Qua Các Bước

### I1_LOWVOL
- **Trạng thái:** `REJECTED`
- **Lý do loại / Kết luận:** Không đạt cao nguyên: {'L': 120, 'N': 20}: mean_X=0.31%, sharpe_X=0.124
- **Cấu hình chọn (EA):** `{'L': 250, 'N': 20}`

| Giai đoạn | Số tháng | Lãi tháng TB (R_m) | Lãi tháng EW (EW_m) | Vượt trội TB (mean_X) | Sharpe_X | p | CAGR | MDD | Calmar | CAGR EW | Turnover tháng TB | Phí / năm (% NAV) | Mã TB / tháng |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **EA** | 35 | 0.90% | 0.15% | 0.75% | 0.313 | 0.0300 | 10.45% | 18.01% | 0.58 | 0.76% | 48.56% | 2.90% | 20.0 |

- **Cao nguyên:** TRƯỢT.
- **DSR (EA):** không tính

### I2_LOWMAX
- **Trạng thái:** `REJECTED`
- **Lý do loại / Kết luận:** Không đạt cao nguyên: {'W': 60, 'N': 20}: mean_X=0.08%, sharpe_X=0.035, {'W': 120, 'N': 15}: mean_X=0.07%, sharpe_X=0.028
- **Cấu hình chọn (EA):** `{'W': 120, 'N': 20}`

| Giai đoạn | Số tháng | Lãi tháng TB (R_m) | Lãi tháng EW (EW_m) | Vượt trội TB (mean_X) | Sharpe_X | p | CAGR | MDD | Calmar | CAGR EW | Turnover tháng TB | Phí / năm (% NAV) | Mã TB / tháng |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **EA** | 35 | 0.52% | 0.15% | 0.37% | 0.180 | 0.1220 | 5.39% | 21.41% | 0.25 | 0.76% | 56.57% | 3.21% | 20.0 |

- **Cao nguyên:** TRƯỢT.
- **DSR (EA):** không tính

---

## 2. Danh Sách Ứng Viên Chốt

> [!NOTE]
> **Không có ứng viên nào vượt qua toàn bộ 4 bước lọc khắt khe (0 ứng viên là kết quả hợp lệ theo §5).**
> Toàn bộ các ý tưởng được ghi nhận là phép đo âm để bảo vệ vốn và không nới lỏng tiêu chuẩn.
