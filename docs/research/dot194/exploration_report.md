# Báo Cáo Khám Phá: Xu Hướng Tuần + RSI Ngày + ATR Chandelier Stop (Brief 194)

> [!IMPORTANT]
> **CẢNH BÁO THIÊN LỆCH SỐNG SÓT (SURVIVORSHIP BIAS):**
> Dữ liệu `stocks_daily` gần như không có mã đã huỷ niêm yết. Mã huỷ thường sụt dài, tức là loại mã mà bộ lọc xu hướng tránh được. Như vậy phép so với EW thiên vị nhẹ cho EW, bất lợi tương đối cho chiến lược.

- **Tổng số thử nghiệm EA đã ghi sổ:** 18 cấu hình.
- **Tổng số thử nghiệm EB đã ghi sổ:** 0 cấu hình.
- **Số ứng viên vượt qua toàn bộ 4 bước:** 0.
- **SHA256 của `candidates.json`:** `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`

---

## 1. Kết Quả Chiến Lược Qua Các Bước

- **Ý tưởng:** `I1_WKMA_RSI_ATR`
- **Cấu hình chọn (EA):** `{'n': 40, 'theta': 45, 'k': 3}`
- **Kết luận / Lý do loại:** Trượt cao nguyên: {'n': 20, 'theta': 45, 'k': 3}: mean_X=-1.09%, sharpe_X=-0.312, {'n': 40, 'theta': 40, 'k': 3}: mean_X=-0.88%, sharpe_X=-0.280, {'n': 40, 'theta': 45, 'k': 2}: mean_X=-1.18%, sharpe_X=-0.444, {'n': 40, 'theta': 45, 'k': 4}: mean_X=-0.65%, sharpe_X=-0.191

### Bảng Chỉ Số EA và EB Của Cấu Hình Được Chọn

| Giai đoạn | Số tháng | Lãi tháng TB (R_m) | Lãi tháng EW (EW_m) | Vượt trội TB (mean_X) | Sharpe_X | p | CAGR | MDD | Calmar | CAGR EW | Lệnh đóng | Thắng % | Lãi ròng TB/lệnh | Median giữ | STOP / TREND / END | Vốn trong CP | Phí / năm (% NAV) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **EA** | 36 | -0.48% | 0.15% | -0.64% | -0.165 | 0.8545 | -7.19% | 38.68% | -0.19 | 0.98% | 252 | 32.5% | -0.71% | 17.0 | 178 / 65 / 9 | 84.7% | 5.34% |

- **Cao nguyên:** TRƯỢT
- **DSR (EA):** không tính

---

## 2. Bảng Phụ Cho Cả 18 Cấu Hình EA (§5)

| n | θ | k | Vượt trội TB (mean_X) | Sharpe_X (tháng) | Median số phiên giữ | Lãi ròng TB / lệnh |
|---|---|---|---|---|---|---|
| 20 | 35 | 2 | -1.09% | -0.330 | 6.0 | -2.31% |
| 20 | 35 | 3 | -1.16% | -0.356 | 7.0 | -2.54% |
| 20 | 35 | 4 | -1.23% | -0.373 | 8.0 | -2.79% |
| 20 | 40 | 2 | -1.90% | -0.685 | 8.0 | -2.45% |
| 20 | 40 | 3 | -2.41% | -0.963 | 10.5 | -3.49% |
| 20 | 40 | 4 | -2.21% | -0.896 | 12.0 | -3.46% |
| 20 | 45 | 2 | -1.49% | -0.573 | 10.0 | -1.34% |
| 20 | 45 | 3 | -1.09% | -0.312 | 15.0 | -1.33% |
| 20 | 45 | 4 | -0.95% | -0.251 | 18.0 | -1.36% |
| 40 | 35 | 2 | -1.49% | -0.463 | 12.0 | -2.11% |
| 40 | 35 | 3 | -1.47% | -0.425 | 17.0 | -2.43% |
| 40 | 35 | 4 | -1.04% | -0.306 | 19.0 | -2.26% |
| 40 | 40 | 2 | -1.47% | -0.515 | 12.0 | -1.66% |
| 40 | 40 | 3 | -0.88% | -0.280 | 19.0 | -1.17% |
| 40 | 40 | 4 | -0.91% | -0.251 | 23.0 | -1.95% |
| 40 | 45 | 2 | -1.18% | -0.444 | 12.0 | -0.82% |
| 40 | 45 | 3 | -0.64% | -0.165 | 17.0 | -0.71% |
| 40 | 45 | 4 | -0.65% | -0.191 | 22.0 | -0.93% |

---

## 3. Danh Sách Ứng Viên Chốt

> [!NOTE]
> **Không có ứng viên nào vượt qua toàn bộ 4 bước lọc khắt khe (0 ứng viên là kết quả hợp lệ theo §5).**
> Toàn bộ cấu hình được ghi nhận là phép đo âm để bảo vệ vốn và không nới lỏng tiêu chuẩn.
