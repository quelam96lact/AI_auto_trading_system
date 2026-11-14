# Báo Cáo Khám Phá Danh Mục Ít Được Chú Ý (Brief 237)

> [!IMPORTANT]
> **CẢNH BÁO THIÊN LỆCH SỐNG SÓT (SURVIVORSHIP BIAS):**
> Dữ liệu `stocks_daily` gần như không có mã đã huỷ niêm yết. Các mã bị huỷ niêm yết thường có thanh khoản/giá biến động xấu ở giai đoạn cuối; thiếu chúng làm kết quả hồi cứu có nguy cơ lạc quan hoặc sai lệch phân bố tương đối.

> [!WARNING]
> **CẢNH BÁO ĐA SO SÁNH & GẦN HỌ ĐÃ ĐÓNG (ĐỢT 193):**
> Chiến lược `I1_LOWATTN` nằm cùng họ danh mục cổ phiếu xoay vòng tháng với họ biến động thấp (đợt 193 đã đóng) và đã thử tổng cộng 9 cấu hình EA cộng 29 họ âm trước đó (`N_trials = 38` khi tính DSR). Nếu trượt bất kỳ cổng nào ở EA/Cao nguyên/EB/DSR, **0 ứng viên** là kết quả hợp lệ và không được nới cổng.

- **Tổng số dòng EA đã ghi sổ:** 9
- **Tổng số dòng EB đã ghi sổ:** 0
- **Số ứng viên chốt:** 0
- **SHA256 `candidates.json`:** `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`
- **SHA256 `selections.json`:** `ae6185ef64cdde47c7955e633d7e1567224c77079ee36ccad4fd173d645c07de`

## Bước 0: Kiểm đếm Universe (§1 & §3.2)

| Mốc | Số mã thực tế | Số mã Lead đếm trước |
|---|---|---|
| L(01/2017) | 56 | 56 |
| L(06/2018) | 58 | 58 |
| L(12/2019) | 85 | 85 |
| L(06/2021) | 166 | 166 |
| L(12/2022) | 136 | 136 |

## Bước 1: Kết quả toàn bộ 9 cấu hình EA (L(01/2017) -> L(12/2019))

- **Mốc ETF EA (`E1VFVN30`):** CAGR = `12.51%`, MDD = `27.88%`.
- **Cấu hình chọn (Sharpe_X cao nhất):** `{'S': 60, 'N': 20}` (Sharpe_X = `-0.3670`, mean_X = `-1.04%`).

| Cấu hình | Số tháng | Lãi tháng TB (R_m) | Lãi tháng EW (EW_m) | Vượt trội TB (mean_X) | Sharpe_X | p | CAGR | MDD | Calmar | Cổng cũ Calmar >= 0.86 (chỉ tham khảo) | CAGR EW | Turnover tháng TB | Phí / năm (% NAV) | Mã TB / tháng |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S20_N10 | 35 | -1.24% | 0.51% | -1.75% | -0.5692 | 0.9995 | -15.27% | 49.56% | -0.31 | TRƯỢT (-0.31) | 5.09% | 96.82% | 3.71% | 10.09 |
| S20_N15 | 35 | -0.83% | 0.51% | -1.34% | -0.4810 | 0.9990 | -10.99% | 40.82% | -0.27 | TRƯỢT (-0.27) | 5.09% | 86.66% | 3.53% | 15.11 |
| S20_N20 | 35 | -0.83% | 0.51% | -1.33% | -0.6223 | 1.0000 | -10.58% | 39.13% | -0.27 | TRƯỢT (-0.27) | 5.09% | 78.81% | 3.36% | 20.11 |
| S40_N10 | 35 | -1.20% | 0.51% | -1.70% | -0.4846 | 0.9990 | -14.82% | 47.55% | -0.31 | TRƯỢT (-0.31) | 5.09% | 84.73% | 3.35% | 10.00 |
| S40_N15 | 35 | -1.14% | 0.51% | -1.64% | -0.5067 | 0.9990 | -14.18% | 45.84% | -0.31 | TRƯỢT (-0.31) | 5.09% | 81.01% | 3.11% | 15.00 |
| S40_N20 | 35 | -0.73% | 0.51% | -1.24% | -0.4435 | 0.9955 | -9.76% | 40.56% | -0.24 | TRƯỢT (-0.24) | 5.09% | 72.41% | 3.00% | 20.14 |
| S60_N10 | 35 | -1.07% | 0.51% | -1.58% | -0.3958 | 0.9895 | -13.75% | 45.54% | -0.30 | TRƯỢT (-0.30) | 5.09% | 83.66% | 3.27% | 10.00 |
| S60_N15 | 35 | -0.81% | 0.51% | -1.32% | -0.4123 | 0.9920 | -10.55% | 38.27% | -0.28 | TRƯỢT (-0.28) | 5.09% | 75.29% | 2.96% | 15.00 |
| **S60_N20 (đỉnh)** | 35 | -0.53% | 0.51% | -1.04% | -0.3670 | 0.9835 | -7.56% | 37.74% | -0.20 | TRƯỢT (-0.20) | 5.09% | 72.04% | 3.10% | 20.00 |

## Bước 2: Kiểm cao nguyên (±1 bước trên cả `S` và `N`)

- **Kết quả:** **TRƯỢT**
  - Lỗi láng giềng: best {'S': 60, 'N': 20}: mean_X=-1.04% <= 0
  - Lỗi láng giềng: {'S': 40, 'N': 20}: mean_X=-1.24%, sharpe_X=-0.443 (need mean_X > 0 and sharpe_X >= -0.183)
  - Lỗi láng giềng: {'S': 60, 'N': 15}: mean_X=-1.32%, sharpe_X=-0.412 (need mean_X > 0 and sharpe_X >= -0.183)

## Bước 3: Kiểm định EB (L(12/2019) -> L(12/2022))

- **Mốc ETF EB (`E1VFVN30`):** CAGR = `5.50%` (ngưỡng >= `4.50%`), MDD = `42.29%` (ngưỡng <= `28.19%`).
- **Kết quả:** Không chạy EB (dừng tại Bước 2 - cao nguyên).

## Bước 4: DSR (n_trials = 9 + 29 = 38)

- **DSR (EA):** không tính

## Kết luận Ứng Viên

> **0 ứng viên** vượt qua đủ các cổng. Đóng giả thuyết, không nới cổng.
