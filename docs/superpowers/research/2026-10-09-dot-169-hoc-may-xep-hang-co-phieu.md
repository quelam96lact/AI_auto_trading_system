# Báo cáo nghiên cứu đợt 169 — Học máy xếp hạng cổ phiếu VN theo tháng (ĐĂNG KÝ TRƯỚC)

Ngày thực hiện: 09/10/2026.  
Tài liệu tham chiếu:
- `docs/superpowers/plans/2026-10-09-brief-dot-169-hoc-may-xep-hang-co-phieu-dang-ky-truoc.md`
- `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`

---

## 1. Tóm tắt điều hành

- **Bài toán:** Học máy xếp hạng mặt cắt cổ phiếu Việt Nam theo chu kỳ tháng (Mô hình tuyến tính Ridge vs. Cây quyết định phi tuyến LightGBM) với 11 đặc trưng giá/khối lượng chuẩn hóa hạng mặt cắt $[0, 1]$, nhãn là hạng mặt cắt lợi nhuận tháng giữ (OPEN phiên đầu $\rightarrow$ CLOSE phiên cuối).
- **Thiết kế kiểm định:** Walk-forward trong In-Sample (IS 2018–2022, 60 tháng thử). Mỗi năm huấn luyện lại 1 lần vào tháng 1, áp dụng purge 1 tháng (bỏ tháng 12 năm trước để tránh rò rỉ nhãn tháng 1). Phép thử bootstrap khối 3 tháng (2.000 lần, seed=42) so sánh danh mục top 10% (WIN) với danh mục mua đều (EW) sau chi phí giao dịch.
- **Kỷ luật niêm phong:** Chỉ đọc dữ liệu nến đến 31/12/2022. Tuyệt đối không đọc bất kỳ nến nào từ 01/01/2023 (`SEALED_START`) và không ghi vào `docs/holdout-unlock-log.md`.
- **Kết luận:** **Học máy xếp hạng cổ phiếu VN (11 đặc trưng giá/khối lượng): KHÔNG có lợi thế trên IS 2018–2022** ($p = 0.4215 \ge 0.05$). Đây là **phép đo âm thứ 15**. **KHÔNG mở niêm phong**.

---

## 2. Dữ liệu và Thiết lập đo lường

- **Universe:** 1.208 mã cổ phiếu trong cơ sở dữ liệu `bars_daily`, đã loại 246 mã lỗi điều chỉnh giá (`exclusions.txt`) và chỉ giữ các mã cổ phiếu (`is_stock_symbol`).
- **Giai đoạn IS:** 2018-01 đến 2022-12 (60 tháng thử).
- **Số mã có nến cuối trước 30/06/2022:** 1 mã. (Cho thấy dữ liệu bảng `bars_daily` hầu như chỉ lưu các mã còn hoạt động tới gần hiện tại, có hiện tượng thiên lệch sống sót - survivorship bias).
- **Số mã đủ điều kiện mỗi tháng (thanh khoản 20 phiên $\ge$ 1 tỷ, đủ 252 phiên lịch sử):**
  - Min: 0 (các tháng đầu lịch sử trước 2017) / Trong 60 tháng thử 2018–2022: Min = 108 mã.
  - Median: 177 mã.
  - Max: 503 mã.
- **Chi phí giao dịch:** Tính theo turnover thực tế: $cost\_rt = 2 \times FEE\_RATE + SELL\_TAX\_RATE + 2 \times SLIPPAGE\_BPS / 10.000 = 2 \times 0.28\% + 0.10\% + 2 \times 0.05\% = 0.76\%$.
- **Đối chứng âm (Negative Control):** Chạy toàn bộ đường ống LightGBM với nhãn bị xáo trộn ngẫu nhiên trong từng tháng (`seed=42`).
  - Kết quả: `excess(LGBM - EW)` trung bình = $-1.46\%$/tháng, $p = 1.0000$.
  - Không xuất hiện lợi thế giả tạo khi không có tín hiệu, khẳng định đường ống xử lý không bị rò rỉ tương lai hay thiên lệch tính toán.

---

## 3. Kết quả đo lường Walk-Forward IS (2018–2022)

### 3.1 Bảng kết quả chính (§1.7) — Phép thử Bootstrap khối 3 tháng (2.000 lần, seed=42)

| Mô hình / Phép so sánh | Mean Net (%/tháng) | Median Net (%/tháng) | p-value (một phía) | KTC 95% [Low; High] | Kết luận lợi thế |
|---|:---:|:---:|:---:|:---:|:---:|
| **WIN_LGBM - EW** | **+0.15%** | **+0.07%** | **0.4215** | **[-0.92%; +1.00%]** | **KHÔNG CÓ LỢI THẾ** ($p \ge 0.05$) |
| **WIN_Ridge - EW** | **+0.34%** | **+0.59%** | **0.4200** | **[-1.08%; +1.31%]** | **KHÔNG CÓ LỢI THẾ** ($p \ge 0.05$) |
| **WIN_LGBM - WIN_Ridge** | **-0.20%** | **+0.33%** | **0.5525** | **[-0.81%; +0.75%]** | LGBM không vượt trội hơn Ridge ($p \ge 0.05$) |

> [!IMPORTANT]
> Cả hai mô hình đều không đạt ngưỡng ý nghĩa thống kê $p < 0.05$. Lợi thế trung bình sau phí của LightGBM so với danh mục mua đều chỉ đạt +0.15%/tháng và khoảng tin cậy 95% bao hàm cả giá trị âm lớn ([-0.92%; +1.00%]).

---

### 3.2 Tổng kết chiến lược toàn kỳ (2018–2022)

| Danh mục | Mean Net (%/tháng) | CAGR Net | Max Drawdown (MDD) |
|---|:---:|:---:|:---:|
| **WIN_LGBM** (Top 10%) | +0.85% | 6.18% | 56.10% |
| **WIN_Ridge** (Top 10%) | +1.05% | 10.83% | 41.30% |
| **EW** (Mua đều) | +0.71% | 3.40% | 53.61% |
| **LOSE_LGBM** (Bottom 10%) | -0.02% | N/A | N/A |

---

### 3.3 Hệ số tương quan hạng Spearman (Information Coefficient - IC)

| Mô hình | Mean IC | Std IC | Tỷ lệ tháng IC > 0 |
|---|:---:|:---:|:---:|
| **Ridge** | +0.0761 | 0.2392 | 66.7% (40/60 tháng) |
| **LightGBM** | +0.0598 | 0.1514 | 66.7% (40/60 tháng) |

Mặc dù cả hai mô hình đạt IC dương trung bình (~0.06 đến ~0.08) và có 2/3 số tháng IC > 0, mức độ dự báo này chưa đủ mạnh để bù đắp chi phí tái cơ cấu danh mục hàng tháng và tạo ra alpha có ý nghĩa thống kê.

---

### 3.4 Kết quả phân rã theo từng năm (CAGR Net)

| Năm | WIN_LGBM | WIN_Ridge | EW | LOSE_LGBM |
|:---:|:---:|:---:|:---:|:---:|
| **2018** | -9.77% | -8.22% | -16.79% | -27.60% |
| **2019** | +3.82% | +10.49% | +1.16% | -30.22% |
| **2020** | +49.82% | +38.59% | +47.96% | +48.21% |
| **2021** | +119.03% | +98.89% | +104.60% | +114.13% |
| **2022** | -56.10% | -40.16% | -53.61% | -60.94% |

Nhận xét:
- Nhóm LOSE_LGBM bị phân hóa và thua lỗ nặng trong các năm 2018 và 2019, cho thấy mô hình có khả năng nhận diện các cổ phiếu yếu kém tốt hơn là tìm ra cổ phiếu siêu vượt trội.
- Trong năm giảm mạnh 2022, toàn bộ các danh mục cổ phiếu đều chịu mức sụt giảm nghiêm trọng (-40% đến -60%).

---

### 3.5 Đối chiếu mốc chuẩn đợt 165 (15% Rủi ro + 85% Tiền gửi 6%/năm)

| Phương án | CAGR | Max Drawdown | MDD $\le$ 4.7% (Backtest) | MDD $\le$ 7.0% (Live) | CAGR $\ge$ 6.0% (Hurdle) |
|---|:---:|:---:|:---:|:---:|:---:|
| **15% WIN_LGBM + 85% Tiền gửi 6%** | **7.94%** | **4.19%** | **ĐẠT** | **ĐẠT** | **ĐẠT** |
| **15% ETF E1VFVN30 + 85% Tiền gửi 6%** | **5.72%** | **0.00%** | **ĐẠT** | **ĐẠT** | K.ĐẠT |

*Ghi chú:* Bảng đối chiếu này mang tính mô tả bổ sung theo §1.8. Do điều kiện tiên quyết ở phép thử chính (§1.7) không đạt ($p = 0.4215 \ge 0.05$), kết quả này không dùng để kết luận chiến lược có lợi thế.

---

### 3.6 Độ quan trọng đặc trưng của LightGBM (Feature Importance năm 2022)

| Đặc trưng | Feature Importance (Split Count) | Ý nghĩa |
|---|:---:|---|
| `ret_3m` | 300.0 | Lợi nhuận 3 tháng gần nhất |
| `ret_1m` | 271.0 | Lợi nhuận 1 tháng gần nhất |
| `dist_high_252` | 270.0 | Khoảng cách tới đỉnh 52 tuần |
| `vol_ratio_5_60` | 266.0 | Tỷ lệ khối lượng ngắn/dài hạn |
| `log_turnover_20` | 258.0 | Quy mô thanh khoản 20 phiên |
| `dist_ma50` | 256.0 | Khoảng cách tới đường MA50 |
| `ret_6m` | 250.0 | Lợi nhuận 6 tháng gần nhất |
| `mom_12_1` | 250.0 | Momentum trung hạn 12-1 tháng |
| `vol_60` | 243.0 | Độ biến động 60 phiên |
| `max_ret_21` | 240.0 | Lợi nhuận ngày lớn nhất trong 21 phiên |
| `vol_20` | 196.0 | Độ biến động 20 phiên |

---

## 4. Đối chiếu kỳ vọng trước của Claude (Brief 169 §0)

- **Kỳ vọng trước của Claude:** "Nhiều khả năng âm" (Dựa trên bằng chứng đợt 102 về momentum 12-1 thua EW có ý nghĩa, dấu hiệu đảo chiều, 14 phép đo trước đều âm, và mốc kiểm định rất khắt khe).
- **Đối chiếu thực tế:** **ĐÚNG**.
  - Cả LightGBM ($p = 0.4215$) và Ridge ($p = 0.4200$) đều không vượt qua ngưỡng ý nghĩa thống kê $p < 0.05$.
  - Tỷ suất vượt trội ròng bình quân của WIN_LGBM chỉ là $+0.15\%$/tháng, không đủ độ tin cậy để khẳng định alpha thực sự.

---

## 5. Kết luận và Kế hoạch tiếp theo

1. **Kết luận chính thức:**
   > **"Học máy xếp hạng cổ phiếu VN (11 đặc trưng giá/khối lượng): KHÔNG có lợi thế trên IS 2018–2022"**
2. **Ghi nhận:** Đây là **phép đo âm thứ 15** trong chuỗi nghiên cứu có đăng ký trước.
3. **Kỷ luật niêm phong:** **KHÔNG mở niêm phong** giai đoạn 2023–2026. File `docs/holdout-unlock-log.md` được giữ nguyên vẹn.

---

## Audit của Claude (09/10/2026)

**Kết luận chính giữ nguyên: KHÔNG có lợi thế** (LGBM − EW +0,15%/tháng, p = 0,42; Ridge − EW +0,34%, p = 0,42; LGBM − Ridge −0,20%, p = 0,55). Phép đo âm thứ 15. Không mở niêm phong.

**Lỗi đã sửa (sửa của Claude, chạy lại lần 2):** dòng mốc chuẩn ETF gọi `max_drawdown` của `scripts/screen_momentum_portfolio.py`. Hàm đó nhận **chuỗi lợi nhuận tháng**, nhưng được đưa vào **đường tài sản** (giá trị quanh 1,0–1,3), nên mỗi giá trị bị hiểu là lợi nhuận +100% và kết quả là MDD = 0,00%. Nay dùng `trading.metrics.max_drawdown` (hàm nhận đường tài sản). Lần chạy thứ hai: mọi số khác giống hệt lần một. Dòng mốc chuẩn thành **15% ETF + 85% tiền gửi 6%: CAGR 5,72%, MDD 4,79%**. Claude tính độc lập bằng `simulate_mix` ra 5,73% / 4,79%, khớp. MDD của WIN, Ridge, EW vẫn đúng vì chúng vốn được đưa vào chuỗi lợi nhuận.

**Sửa của Claude ngoài code đo:** agent thêm `scikit-learn` và `lightgbm` vào một bảng mới `[dependency-groups] dev`. Claude chuyển về `[project.optional-dependencies] dev`, cạnh `arch`, vì CI và pre-push cài bằng `--extra dev`. Image chạy thật vẫn `--no-dev`.

**Ba điều cần biết khi đọc số mô tả:**
1. **Thiên lệch sống sót rất nặng:** chỉ **1/1.208** mã có nến cuối trước 30/06/2022. Nghĩa là `bars_daily` gần như chỉ gồm mã còn niêm yết, nên WIN, Ridge và EW đều bị thổi phồng so với ETF (ETF không bị thiên lệch này). Vì thế việc "15% WIN_LGBM + tiền gửi" (7,94% / 4,19%) đẹp hơn "15% ETF + tiền gửi" (5,72% / 4,79%) **không phải bằng chứng**: EW cũng thắng ETF trong giai đoạn này (CAGR 3,40% so với 1,34%). Lỗi này áp dụng cho mọi phép đo cổ phiếu trước đây dùng `bars_daily`.
2. **Đối chứng âm không quanh 0:** nhãn xáo trộn cho −1,46%/tháng. Không phải dấu hiệu rò rỉ (rò rỉ sẽ cho số dương), nhưng lệch xa 0. Phần lớn có thể giải thích bằng chi phí: WIN xoay vòng gần như toàn bộ mỗi tháng, mất khoảng 0,7%/tháng so với EW. Phần còn lại là nghiêng ngẫu nhiên theo đặc trưng. Chưa đo tách hai phần.
3. **"Min = 0 mã đủ điều kiện"** là giá trị của các tháng đầu chưa đủ 252 phiên lịch sử, không phải tháng thử. Cả 60 tháng thử đều đủ ≥ 100 mã.

**Kỳ vọng trước của Claude ("nhiều khả năng âm"):** đúng. Tín hiệu đảo chiều của đợt 102 không biến thành lợi thế sau phí khi đưa vào mô hình.
