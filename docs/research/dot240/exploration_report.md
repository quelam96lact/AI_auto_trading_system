# Báo Cáo Khám Phá Đảo Chiều Ngắn Hạn (Brief 240)

> [!CAUTION]
> **CẢNH BÁO ĐA SO SÁNH & VƯỢT NGÂN SÁCH MỤC F:**
> Đây là giả thuyết thứ 5 của tháng 11 (vượt ngân sách mục F, chủ dự án cho phép làm tiếp). Tổng số phép thử tính DSR là `N_trials = 9 + 31 = 40` (cộng 31 họ phép đo âm trước đó).

> [!WARNING]
> **CẢNH BÁO THIÊN LỆCH SỐNG SÓT (CÓ LỢI CHO CHIẾN LƯỢC) & GẦN HỌ MOMENTUM:**
> - **Thiên lệch sống sót có lợi cho đảo chiều ngắn hạn:** Dữ liệu `stocks_daily` gần như thiếu các mã đã huỷ niêm yết hoặc phá sản. Những mã giảm sâu không bao giờ hồi phục bị vắng mặt khỏi mẫu, khiến kết quả hồi cứu của chiến lược bắt đáy ngắn hạn (`RET_S` thấp nhất) bị lạc quan hoá một cách giả tạo.
> - **Gần họ đã đo:** Gần họ momentum (đợt 102, chân trời khác) và cùng họ danh mục cổ phiếu xoay vòng tháng (đợt 193, 237, 238).

- **Tổng số dòng EA đã ghi sổ:** 9
- **Tổng số dòng EB đã ghi sổ:** 0
- **Số ứng viên chốt:** 0
- **SHA256 `candidates.json`:** `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`
- **SHA256 `selections.json`:** `f44b90d8de9f22d08b93294ac3249d3460c4dc818de9d2bb053bba12e98d256f`

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
- **Cấu hình chọn (Sharpe_X cao nhất):** `{'S': 5, 'N': 15}` (Sharpe_X = `-0.2965`, mean_X = `-0.94%`).

| Cấu hình | Số tháng | Lãi tháng TB (R_m) | Lãi tháng EW (EW_m) | Vượt trội TB (mean_X) | Sharpe_X | p | CAGR | MDD | Calmar | Cổng cũ Calmar >= 0.86 (chỉ tham khảo) | CAGR EW | Turnover tháng TB | Phí / năm (% NAV) | Mã TB / tháng |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S5_N10 | 35 | -0.80% | 0.51% | -1.31% | -0.3345 | 0.9755 | -11.41% | 50.13% | -0.23 | TRƯỢT (-0.23) | 5.09% | 167.14% | 6.43% | 9.97 |
| **S5_N15 (đỉnh)** | 35 | -0.43% | 0.51% | -0.94% | -0.2965 | 0.9680 | -6.92% | 45.78% | -0.15 | TRƯỢT (-0.15) | 5.09% | 156.89% | 6.69% | 14.97 |
| S5_N20 | 35 | -0.63% | 0.51% | -1.14% | -0.4540 | 0.9980 | -8.79% | 43.76% | -0.20 | TRƯỢT (-0.20) | 5.09% | 148.72% | 6.20% | 19.94 |
| S10_N10 | 35 | -1.69% | 0.51% | -2.20% | -0.6228 | 1.0000 | -19.73% | 55.39% | -0.36 | TRƯỢT (-0.36) | 5.09% | 163.91% | 5.34% | 10.03 |
| S10_N15 | 35 | -1.63% | 0.51% | -2.13% | -0.8148 | 1.0000 | -18.81% | 52.15% | -0.36 | TRƯỢT (-0.36) | 5.09% | 154.09% | 5.23% | 15.00 |
| S10_N20 | 35 | -1.28% | 0.51% | -1.79% | -0.7380 | 1.0000 | -15.43% | 46.88% | -0.33 | TRƯỢT (-0.33) | 5.09% | 144.67% | 5.28% | 20.03 |
| S20_N10 | 35 | -1.87% | 0.51% | -2.38% | -0.4953 | 0.9975 | -22.28% | 58.47% | -0.38 | TRƯỢT (-0.38) | 5.09% | 167.74% | 6.10% | 10.00 |
| S20_N15 | 35 | -1.46% | 0.51% | -1.97% | -0.5982 | 1.0000 | -17.63% | 49.50% | -0.36 | TRƯỢT (-0.36) | 5.09% | 154.74% | 5.75% | 15.00 |
| S20_N20 | 35 | -1.37% | 0.51% | -1.88% | -0.6940 | 1.0000 | -16.57% | 47.89% | -0.35 | TRƯỢT (-0.35) | 5.09% | 141.50% | 5.24% | 20.00 |

### So sánh Turnover & Phí với Đợt 238 (EA)

| Cấu hình (240) | Turnover tháng TB (240) | Phí / năm % NAV (240) | Cấu hình cùng S (238) | Turnover tháng TB (238 cùng S) | Phí / năm % NAV (238 cùng S) | Cấu hình cùng vị trí lưới (238) | Turnover tháng TB (238 vị trí) | Phí / năm % NAV (238 vị trí) |
|---|---|---|---|---|---|---|---|---|
| S5_N10 | 167.14% | 6.43% | — | — | — | S20_N10 | 118.17% | 8.28% |
| S5_N15 | 156.89% | 6.69% | — | — | — | S20_N15 | 106.81% | 6.42% |
| S5_N20 | 148.72% | 6.20% | — | — | — | S20_N20 | 99.55% | 5.55% |
| S10_N10 | 163.91% | 5.34% | — | — | — | S40_N10 | 97.43% | 7.04% |
| S10_N15 | 154.09% | 5.23% | — | — | — | S40_N15 | 90.52% | 5.81% |
| S10_N20 | 144.67% | 5.28% | — | — | — | S40_N20 | 82.80% | 4.59% |
| S20_N10 | 167.74% | 6.10% | S20_N10 | 118.17% | 8.28% | S60_N10 | 90.01% | 5.39% |
| S20_N15 | 154.74% | 5.75% | S20_N15 | 106.81% | 6.42% | S60_N15 | 82.09% | 4.99% |
| S20_N20 | 141.50% | 5.24% | S20_N20 | 99.55% | 5.55% | S60_N20 | 75.41% | 3.95% |

#### Bảng số gốc Turnover & Phí chép từ `docs/research/dot238/exploration_report.md`

| Cấu hình (238) | Turnover tháng TB (238) | Phí / năm % NAV (238) |
|---|---|---|
| S20_N10 | 118.17% | 8.28% |
| S20_N15 | 106.81% | 6.42% |
| S20_N20 | 99.55% | 5.55% |
| S40_N10 | 97.43% | 7.04% |
| S40_N15 | 90.52% | 5.81% |
| S40_N20 | 82.80% | 4.59% |
| S60_N10 | 90.01% | 5.39% |
| S60_N15 | 82.09% | 4.99% |
| S60_N20 | 75.41% | 3.95% |
| EB_S40_N10 | 112.03% | 6.98% |

## Bước 2: Kiểm cao nguyên (±1 bước trên cả `S` và `N`)

- **Kết quả:** **TRƯỢT**
  - Lỗi láng giềng: best {'S': 5, 'N': 15}: mean_X=-0.94% <= 0
  - Lỗi láng giềng: {'S': 10, 'N': 15}: mean_X=-2.13%, sharpe_X=-0.815 (need mean_X > 0 and sharpe_X >= -0.148)
  - Lỗi láng giềng: {'S': 5, 'N': 10}: mean_X=-1.31%, sharpe_X=-0.334 (need mean_X > 0 and sharpe_X >= -0.148)
  - Lỗi láng giềng: {'S': 5, 'N': 20}: mean_X=-1.14%, sharpe_X=-0.454 (need mean_X > 0 and sharpe_X >= -0.148)

## Bước 3: Kiểm định EB (L(12/2019) -> L(12/2022))

- **Mốc ETF EB (`E1VFVN30`):** CAGR = `5.50%` (ngưỡng >= `4.50%`), MDD = `42.29%` (ngưỡng <= `28.19%`).
- **Kết quả:** Không chạy EB (dừng tại Bước 2 - cao nguyên).

## Bước 4: DSR (n_trials = 9 + 31 = 40)

- **DSR (EA):** không tính

## Kết luận Ứng Viên

> **0 ứng viên** vượt qua đủ các cổng. Đóng giả thuyết, không nới cổng.

- *Ghi chú cổng cũ tham khảo:* Calmar >= 0.86 không còn là cổng chính của EB.
