# Báo Cáo Đo Lường & So Sánh Chiến Lược Trên Khung Bar 1 Giờ & 1 Ngày

> **Ngày lập**: 2026-09-06  
> **Phạm vi khảo sát**:
> 1. Dữ liệu Crypto (20 cặp BingX): Khung **1 Ngày (1D)** và **1 Giờ (1H)**.
> 2. Dữ liệu Chứng khoán VN: Khung **1 Ngày (1D)** (`bars_daily`) và đối chiếu với khung **5 Phút (5M)**.
> 3. Cơ chế thanh khoản gộp theo ngày (Gói K — `DailyLiquidityTracker`).

---

## 1. BẢNG TỔNG HỢP HIỆU SUẤT TRÊN CRYPTO (20 CẶP BINGX)

*Điều kiện đo lường*: Vốn 100.000 USDT/mã (Tổng vốn: 2.000.000 USDT), `lot_size=1`, mô hình phí crypto (`fee=0`, `tax=0`, `slippage=0`, `settle_days=0`).

### A. Khung 1 Ngày (1D — 27.124 nến, từ 05/2021 đến 09/2026)

| Chiến lược | Tổng vốn (USDT) | PnL Chiến lược (USDT) | PnL Mua & Giữ (USDT) | Tổng lệnh | Win Rate (%) |
|---|---|---|---|---|---|
| **Octopus Pullback** *(TK 0 - 1M USD)* | 2.000.000 | **−6.380,49** | +247.749,94 | 46 | 30,4% |
| **Octopus Pullback** *(TK 2 tỷ VND = 2B USD)* | 2.000.000 | **−829,14** | +247.749,94 | 1 | 0,0% |
| **Daily Breakout** | 2.000.000 | **−48.092,83** | +247.749,94 | 264 | 28,4% |
| **Sma Cross** *(fast=10, slow=20)* | 2.000.000 | **−45.151,16** | +247.749,94 | 324 | 27,5% |

### B. Khung 1 Giờ (1H — 385.363 nến, từ 04/2024 đến 09/2026)

| Chiến lược | Tổng vốn (USDT) | PnL Chiến lược (USDT) | PnL Mua & Giữ (USDT) | Tổng lệnh | Win Rate (%) |
|---|---|---|---|---|---|
| **Octopus Pullback** *(TK 0 - 1M USD)* | 2.000.000 | **−54.304,23** | +146.685,11 | 533 | 29,1% |
| **Octopus Pullback** *(TK 2 tỷ VND = 2B USD)* | 2.000.000 | **−298,85** | +146.685,11 | 2 | 0,0% |
| **Daily Breakout** | 2.000.000 | **−58.090,67** | +146.685,11 | 1.237 | 32,2% |
| **Sma Cross** *(fast=10, slow=20)* | 2.000.000 | **−56.946,34** | +146.685,11 | 766 | 33,0% |

---

## 2. BẢNG ĐỘ NHẠY THANH KHOẢN CỦA OCTOPUS TRÊN 1D VÀ 1H

### Độ nhạy thanh khoản trên Khung 1D (20 cặp crypto)
| Ngưỡng (USDT) | Mã đủ TK | Mã có lệnh | Tổng lệnh | Win Rate | PnL Chiến lược (USDT) | PnL Mua & Giữ (USDT) |
|---|---|---|---|---|---|---|
| **0** | 20/20 | 13/20 | 46 | 30,4% | **−6.380,49** | +247.749,94 |
| **100.000** | 20/20 | 13/20 | 46 | 30,4% | **−6.380,49** | +247.749,94 |
| **1.000.000** | 20/20 | 13/20 | 46 | 30,4% | **−6.380,49** | +247.749,94 |
| **10.000.000** | 20/20 | 12/20 | 41 | 29,3% | **−7.110,00** | +247.749,94 |
| **100.000.000** | 14/20 | 4/20 | 14 | 28,6% | **−3.440,80** | +247.749,94 |
| **500.000.000** | 4/20 | 1/20 | 4 | 50,0% | **−758,68** | +247.749,94 |
| **2.000.000.000** | 2/20 | 1/20 | 1 | 0,0% | **−829,14** | +247.749,94 |

### Độ nhạy thanh khoản trên Khung 1H (20 cặp crypto)
| Ngưỡng (USDT) | Mã đủ TK | Mã có lệnh | Tổng lệnh | Win Rate | PnL Chiến lược (USDT) | PnL Mua & Giữ (USDT) |
|---|---|---|---|---|---|---|
| **0** | 20/20 | 19/20 | 533 | 29,1% | **−54.304,23** | +146.685,11 |
| **100.000** | 20/20 | 19/20 | 533 | 29,1% | **−54.304,23** | +146.685,11 |
| **1.000.000** | 20/20 | 19/20 | 533 | 29,1% | **−54.304,23** | +146.685,11 |
| **10.000.000** | 20/20 | 19/20 | 443 | 29,1% | **−46.901,02** | +146.685,11 |
| **100.000.000** | 9/20 | 6/20 | 110 | 28,2% | **−14.577,99** | +146.685,11 |
| **500.000.000** | 4/20 | 3/20 | 81 | 32,1% | **−3.472,32** | +146.685,11 |
| **2.000.000.000** | 2/20 | 1/20 | 2 | 0,0% | **−298,85** | +146.685,11 |

---

## 3. ĐỐI CHIẾU VỚI THỊ TRƯỜNG CHỨNG KHOÁN VN

| Khung thời gian | Dữ liệu | Octopus Pullback | Sma Cross / Daily Breakout | Mua & Giữ (Buy & Hold) | Nhận định |
|---|---|---|---|---|---|
| **1 Ngày (1D)** | `bars_daily` (1.308 mã) | **−1.615.319.902 đ** (1.514 lệnh) | DailyBreakout: −696 triệu đ | +1.897,6 tỷ đ | Thị trường tăng trưởng dài hạn, Buy & Hold vượt trội |
| **5 Phút (5M)** | `bars` (310 mã) | **−120.697.348 đ** (574 lệnh) | SmaCross: −503.191.542 đ | −2.930.966.837 đ | Giai đoạn đi ngang/giảm, Octopus thắng B&H trên 75,9% số mã |

---

## 4. NHẬN XÉT CỐT LÕI

1. **Về cơ chế thanh khoản gộp theo ngày (Gói K)**:
   - Trên cả khung **1D**, **1H**, và **5M**, `DailyLiquidityTracker` hoạt động ổn định và nhất quán: 1 bar ngày = 1 ngày đã đóng; nhiều bar trong phiên (5m, 1h) được gom trọn vẹn theo `bar.ts.date()`.
2. **Về hiệu suất chiến lược**:
   - Trên khung **1 Ngày (1D)**: Tần suất giao dịch thấp hơn (crypto: 46 lệnh/20 mã trong 5 năm), tỷ lệ thắng ~30%, lỗ nhẹ hơn so với các khung nhỏ.
   - Trên khung **1 Giờ (1H)**: Tần suất giao dịch tăng ~11 lần (533 lệnh trong 2 năm), nhưng do đặc tính nhiễu sóng trong phiên và chưa có bộ lọc xu hướng đa khung thời gian (MTF), PnL bị bào mòn nhanh hơn (−54k USDT).
3. **Cảnh báo về thiên lệch sống sót & phí**:
   - Crypto 20 mã là top coin còn niêm yết năm 2026.
   - Kết quả crypto ở trên là **chưa trừ phí** (phí = 0, trượt giá = 0) nên mang tính chất lạc quan nhất.
