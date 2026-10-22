# Báo cáo kết quả khám phá chiến lược đa khung thời gian (Đợt 188)

- Thời điểm chạy: 2026-10-19T23:56:02.245163+00:00
- Tổng số cấu hình EA đã đánh giá và ghi sổ: 151 / 400 ngân sách.
- Phân bổ thị trường: Cổ phiếu 97 cấu hình, Crypto 54 cấu hình.

## Ý tưởng: `STK_WK_TREND_PULLBACK` (STOCK)

- **Cấu hình đỉnh EA được chọn:** `{'w_period': 10, 'rsi_len': 5, 'rsi_thresh': 25}`
  - $n = 3436$, Lãi ròng TB = 0.36%, Sharpe = 0.0379, p = 0.0495, Calmar = 0.85

❌ **LOẠI TẠI BƯỚC 2 (TRƯỢT CAO NGUYÊN):** Đỉnh bị nhọn, các cấu hình láng giềng sụp đổ hiệu quả:
  - neighbor {'w_period': 20, 'rsi_len': 5, 'rsi_thresh': 25}: mean_net=0.11%, sharpe=0.0121 (cần > 0 và >= 0.0190)
  - neighbor {'w_period': 10, 'rsi_len': 3, 'rsi_thresh': 25}: mean_net=0.14%, sharpe=0.0169 (cần > 0 và >= 0.0190)

## Ý tưởng: `STK_WK_VOL_BREAKOUT` (STOCK)

- **Cấu hình đỉnh EA được chọn:** `{'vol_thresh': 0.05, 'n_days': 20, 'exit_days': 15}`
  - $n = 1423$, Lãi ròng TB = 1.72%, Sharpe = 0.0933, p = 0.0035, Calmar = 1.60

✅ **BƯỚC 2 (CAO NGUYÊN ĐẠT):** Cả 4 cấu hình láng giềng đều duy trì lãi ròng > 0 và Sharpe >= 50% đỉnh.

- **Kết quả kiểm chứng EB (2020-2022 cổ phiếu / 2025-2026 crypto):**
  - $n = 1310$, Lãi ròng TB = 3.81%, p = 0.0100, Calmar = 0.17
  - Vượt baseline sau cắt 1% lãi nhất = -3.05%
❌ **LOẠI TẠI BƯỚC 3 (TRƯỢT CỔNG EB):** calmar=0.17 < 0.86, baseline excess trim 1% = -3.05% <= 0

## Ý tưởng: `STK_MN_TREND_WK_MOM` (STOCK)

- **Cấu hình đỉnh EA được chọn:** `{'m_len': 6, 'k_weeks': 2, 'mom_thresh': 0.04}`
  - $n = 5325$, Lãi ròng TB = -0.34%, Sharpe = -0.0245, p = 0.8730, Calmar = -0.27

❌ **LOẠI TẠI BƯỚC 2 (TRƯỢT CAO NGUYÊN):** Đỉnh bị nhọn, các cấu hình láng giềng sụp đổ hiệu quả:
  - neighbor {'m_len': 9, 'k_weeks': 2, 'mom_thresh': 0.04}: mean_net=-0.42%, sharpe=-0.0303 (cần > 0 và >= -0.0123)
  - neighbor {'m_len': 6, 'k_weeks': 4, 'mom_thresh': 0.04}: mean_net=-0.45%, sharpe=-0.0367 (cần > 0 và >= -0.0123)
  - neighbor {'m_len': 6, 'k_weeks': 2, 'mom_thresh': 0.02}: mean_net=-0.32%, sharpe=-0.0260 (cần > 0 và >= -0.0123)
  - neighbor {'m_len': 6, 'k_weeks': 2, 'mom_thresh': 0.06}: mean_net=-0.39%, sharpe=-0.0250 (cần > 0 và >= -0.0123)

## Ý tưởng: `CRY_1D_TREND_4H_PULLBACK` (CRYPTO)

- **Cấu hình đỉnh EA được chọn:** `{'d_period': 30, 'rsi_low': 35, 'exit_len': 20}`
  - $n = 547$, Lãi ròng TB = -0.78%, Sharpe = -0.1394, p = 0.9695, Calmar = -0.77

❌ **LOẠI TẠI BƯỚC 2 (TRƯỢT CAO NGUYÊN):** Đỉnh bị nhọn, các cấu hình láng giềng sụp đổ hiệu quả:
  - neighbor {'d_period': 20, 'rsi_low': 35, 'exit_len': 20}: mean_net=-1.06%, sharpe=-0.1853 (cần > 0 và >= -0.0697)
  - neighbor {'d_period': 30, 'rsi_low': 30, 'exit_len': 20}: mean_net=-0.90%, sharpe=-0.1586 (cần > 0 và >= -0.0697)
  - neighbor {'d_period': 30, 'rsi_low': 35, 'exit_len': 15}: mean_net=-0.82%, sharpe=-0.1499 (cần > 0 và >= -0.0697)

## Ý tưởng: `CRY_4H_VOL_BREAKOUT` (CRYPTO)

- **Cấu hình đỉnh EA được chọn:** `{'trend_len': 30, 'bb_len': 25, 'bb_std': 2.2}`
  - $n = 926$, Lãi ròng TB = 0.78%, Sharpe = 0.1025, p = 0.0000, Calmar = 4.11

✅ **BƯỚC 2 (CAO NGUYÊN ĐẠT):** Cả 3 cấu hình láng giềng đều duy trì lãi ròng > 0 và Sharpe >= 50% đỉnh.

- **Kết quả kiểm chứng EB (2020-2022 cổ phiếu / 2025-2026 crypto):**
  - $n = 827$, Lãi ròng TB = 0.00%, p = 0.5025, Calmar = 0.43
  - Lãi gộp TB = 0.18% (ngưỡng 1.5 x phí = 0.21%)
❌ **LOẠI TẠI BƯỚC 3 (TRƯỢT CỔNG EB):** p=0.5025 >= 0.05, calmar=0.43 < 0.86, mean_gross=0.18% < 0.21%

## Ý tưởng: `STK_WK_DONCHIAN_CHANNEL` (STOCK)

- **Cấu hình đỉnh EA được chọn:** `{'n_weeks': 20, 'exit_weeks': 12}`
  - $n = 1498$, Lãi ròng TB = 1.95%, Sharpe = 0.0712, p = 0.0285, Calmar = 1.13

✅ **BƯỚC 2 (CAO NGUYÊN ĐẠT):** Cả 3 cấu hình láng giềng đều duy trì lãi ròng > 0 và Sharpe >= 50% đỉnh.

- **Kết quả kiểm chứng EB (2020-2022 cổ phiếu / 2025-2026 crypto):**
  - $n = 2014$, Lãi ròng TB = 8.25%, p = 0.0020, Calmar = 0.43
  - Vượt baseline sau cắt 1% lãi nhất = -3.73%
❌ **LOẠI TẠI BƯỚC 3 (TRƯỢT CỔNG EB):** calmar=0.43 < 0.86, baseline excess trim 1% = -3.73% <= 0

## Kết luận ứng viên

Không có ứng viên nào vượt qua toàn bộ 4 hàng rào chống overfit (**0 ứng viên**).
Đây là kết quả hoàn toàn hợp lệ, phản ánh đúng tính khắc nghiệt của chi phí giao dịch thực tế và hàng rào DSR chống chọn ngẫu nhiên.

**sha256 của candidates.json:** `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`