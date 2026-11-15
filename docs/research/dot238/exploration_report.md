# Báo Cáo Khám Phá Danh Mục Đang Được Chú Ý (Brief 238)

> [!CAUTION]
> **CẢNH BÁO GIẢ THUYẾT SINH SAU KHI XEM DỮ LIỆU (EA ĐÃ NHIỄM) & ĐA SO SÁNH:**
> Đợt 237 cho 9/9 cấu hình `AT_S` thấp thua EW trên EA; đợt 238 thử chiều ngược (`AT_S` cao) là giả thuyết sinh sau khi đã thấy kết quả EA và vượt ngân sách mục F (suất thứ 4 tháng 11, tổng `N_trials = 9 + 9 + 30 = 48` khi tính DSR). Kết quả EA chỉ dùng để chọn đỉnh và kiểm cao nguyên; bằng chứng nằm ở EB (chưa mở trước đó) và V1/V2.

> [!WARNING]
> **CẢNH BÁO TRÁI CHIỀU ĐỢT 227 & THIÊN LỆCH SỐNG SÓT:**
> - Trái chiều với đợt 227 và giả thuyết ban đầu của đợt 237 về quá giá do chú ý ngắn hạn.
> - Dữ liệu `stocks_daily` gần như không có mã huỷ niêm yết (thiên lệch sống sót), làm sai lệch phân phối lợi nhuận/turnover tương đối.

- **Tổng số dòng EA đã ghi sổ:** 9
- **Tổng số dòng EB đã ghi sổ:** 1
- **Số ứng viên chốt:** 0
- **SHA256 `candidates.json`:** `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`
- **SHA256 `selections.json`:** `a794f81a4c2f5af1b3bc4b97455ddaca296ad68ce27c48809b36f24b1c81ae36`

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
- **Cấu hình chọn (Sharpe_X cao nhất):** `{'S': 40, 'N': 10}` (Sharpe_X = `0.4488`, mean_X = `2.65%`).

| Cấu hình | Số tháng | Lãi tháng TB (R_m) | Lãi tháng EW (EW_m) | Vượt trội TB (mean_X) | Sharpe_X | p | CAGR | MDD | Calmar | Cổng cũ Calmar >= 0.86 (chỉ tham khảo) | CAGR EW | Turnover tháng TB | Phí / năm (% NAV) | Mã TB / tháng |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S20_N10 | 35 | 2.63% | 0.51% | 2.12% | 0.3821 | 0.0070 | 31.79% | 20.37% | 1.56 | ĐẠT (1.56) | 5.09% | 118.17% | 8.28% | 9.83 |
| S20_N15 | 35 | 1.49% | 0.51% | 0.98% | 0.2515 | 0.0565 | 16.28% | 26.30% | 0.62 | TRƯỢT (0.62) | 5.09% | 106.81% | 6.42% | 14.83 |
| S20_N20 | 35 | 1.38% | 0.51% | 0.87% | 0.2631 | 0.0490 | 15.24% | 24.83% | 0.61 | TRƯỢT (0.61) | 5.09% | 99.55% | 5.55% | 19.86 |
| **S40_N10 (đỉnh)** | 35 | 3.16% | 0.51% | 2.65% | 0.4488 | 0.0025 | 39.79% | 26.37% | 1.51 | ĐẠT (1.51) | 5.09% | 97.43% | 7.04% | 9.89 |
| S40_N15 | 35 | 2.11% | 0.51% | 1.61% | 0.3848 | 0.0070 | 24.66% | 25.70% | 0.96 | ĐẠT (0.96) | 5.09% | 90.52% | 5.81% | 14.86 |
| S40_N20 | 35 | 1.31% | 0.51% | 0.80% | 0.2372 | 0.0705 | 13.95% | 30.76% | 0.45 | TRƯỢT (0.45) | 5.09% | 82.80% | 4.59% | 19.89 |
| S60_N10 | 35 | 2.06% | 0.51% | 1.55% | 0.2724 | 0.0460 | 22.60% | 29.71% | 0.76 | TRƯỢT (0.76) | 5.09% | 90.01% | 5.39% | 9.86 |
| S60_N15 | 35 | 1.88% | 0.51% | 1.37% | 0.3054 | 0.0315 | 21.05% | 27.31% | 0.77 | TRƯỢT (0.77) | 5.09% | 82.09% | 4.99% | 14.83 |
| S60_N20 | 35 | 0.99% | 0.51% | 0.49% | 0.1375 | 0.1985 | 9.68% | 33.45% | 0.29 | TRƯỢT (0.29) | 5.09% | 75.41% | 3.95% | 19.83 |

### So sánh Turnover & Phí với Đợt 237 (EA)

| Cấu hình | Turnover tháng TB (238) | Turnover tháng TB (237) | Phí / năm % NAV (238) | Phí / năm % NAV (237) |
|---|---|---|---|---|
| S20_N10 | 118.17% | 96.82% | 8.28% | 3.71% |
| S20_N15 | 106.81% | 86.66% | 6.42% | 3.53% |
| S20_N20 | 99.55% | 78.81% | 5.55% | 3.36% |
| S40_N10 | 97.43% | 84.73% | 7.04% | 3.35% |
| S40_N15 | 90.52% | 81.01% | 5.81% | 3.11% |
| S40_N20 | 82.80% | 72.41% | 4.59% | 3.00% |
| S60_N10 | 90.01% | 83.66% | 5.39% | 3.27% |
| S60_N15 | 82.09% | 75.29% | 4.99% | 2.96% |
| S60_N20 | 75.41% | 72.04% | 3.95% | 3.10% |

## Bước 2: Kiểm cao nguyên (±1 bước trên cả `S` và `N`)

- **Kết quả:** **ĐẠT**
  - Mọi láng giềng ±1 bước theo cả `S` và `N` đều có `mean_X > 0` và `sharpe_X >= 50%` đỉnh.

## Bước 3: Kiểm định EB (L(12/2019) -> L(12/2022))

- **Mốc ETF EB (`E1VFVN30`):** CAGR = `5.50%` (ngưỡng >= `4.50%`), MDD = `42.29%` (ngưỡng <= `28.19%`).
- **Kết quả:** **TRƯỢT**

| Cấu hình | Số tháng | Lãi tháng TB (R_m) | Lãi tháng EW (EW_m) | Vượt trội TB (mean_X) | Sharpe_X | p | CAGR | MDD | Calmar | Cổng cũ Calmar >= 0.86 (chỉ tham khảo) | CAGR EW | Turnover tháng TB | Phí / năm (% NAV) | Mã TB / tháng |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EB_S40_N10 | 36 | 0.53% | 1.51% | -0.98% | -0.1250 | 0.7790 | -3.02% | 65.83% | -0.05 | TRƯỢT (-0.05) | 11.01% | 112.03% | 6.98% | 9.92 |

  - Lý do trượt: mean_X=-0.98% <= 0
  - Lý do trượt: p=0.7790 >= 0.05
  - Lý do trượt: MDD=65.83% > 28.19% (2/3 ETF MDD)
  - Lý do trượt: CAGR=-3.02% < 4.50% (ETF CAGR - 1pp)

## Bước 4: DSR (n_trials = 9 + 9 + 30 = 48)

- **DSR (EA):** không tính

## Kết luận Ứng Viên

> **0 ứng viên** vượt qua đủ các cổng. Đóng giả thuyết, không nới cổng.

- *Ghi chú cổng cũ tham khảo:* Calmar >= 0.86 không còn là cổng chính của EB.
