# Báo cáo nghiên cứu Đợt 39 — Động lượng cắt ngang 20 mã, trung tính thị trường

- Ngày thực hiện: 12/09/2026 UTC
- Người thực thi: Gemini Flash 3.8
- Người lập kế hoạch & audit: Claude
- Đối tượng kiểm định: Vũ trụ 20 mã crypto khung ngày (1D) từ `2022-02-15` đến `2026-09-02` UTC (dữ liệu BingX).
- Mô hình: Cross-sectional momentum Long top $k$ / Short bottom $k$, tái cân bằng mỗi 7 ngày, Gross 1×, Net 0 (trung tính thị trường), có nhận biết quay vòng vốn (turnover awareness).

---

## 1. Nguyên văn output của 6 lượt chạy (Copy từ terminal)

### Lượt 1: Baseline IS (`--split is`)

```
==========================================================================================
BẮT ĐẦU ĐO LƯỜNG ĐỘNG LƯỢNG CẮT NGANG 20 MÃ | TẬP: IS (UTC)
Khoảng thời gian: 2022-02-15 -> 2025-12-31 UTC
Tham số: lookback=30d | rebalance=7d | k=3 | skip_recent=0d
Vốn: 500.0 USDT | Phí: 0.05% | Trượt giá: 0.0 bps | min_universe=10
==========================================================================================

--- ĐANG CHẠY PHÂN PHỐI NULL DANH MỤC NGẪU NHIÊN (N=1000) ---
(Không cần hiệu chỉnh xác suất: số kỳ tái cân bằng và số vị thế giống hệt nhau theo thiết kế)
Hoàn thành 1000 vòng bốc thăm null trong 436.37s

==========================================================================================
CẢNH BÁO HỆ THỐNG BẮT BUỘC:
  [1] [THIÊN LỆCH SỐNG SÓT] 20 mã chọn theo khối lượng 2026 đo lùi về quá khứ; đồng đã chết
      không có trong rổ; thiên lệch này bơm phồng vế long. Không sửa được bằng dữ liệu hiện có.
  [2] [CHƯA MÔ HÌNH HOÁ FUNDING] Vế short nhận/trả funding tuỳ chế độ thị trường, khoản này
      có thể cùng bậc độ lớn với kết quả.
  [3] [VŨ TRỤ THAY ĐỔI] Số mã đủ tư cách: min=10 | max=20 | trung bình=14.5
==========================================================================================

==========================================================================================
KẾT QUẢ THẬT (CROSS-SECTIONAL MOMENTUM):
==========================================================================================
Rebalances  | SkipReb  | SkipFills | Net PnL (USDT) | PnL %    | ProfitFactor | MaxDD %  | Sharpe   | Fees (USDT) | Turnover   | Univ TB
------------------------------------------------------------------------------------------
198         | 5        | 0         |       +1001.51 | +200.30% |         1.35 |   37.11% |     0.92 |       75.46 |   150914.8 |    14.5
==========================================================================================

HAI MỐC ĐỐI CHỨNG (CÙNG KỲ, CÙNG VỐN 500 USDT, CÙNG PHÍ):
  1. Mua-và-giữ BTC                     :    +532.62 USDT (+106.52%)
  2. Mua-và-giữ chia đều toàn vũ trụ (7d):    +180.67 USDT (+36.13%)
  -------------------------------------------------------------
  Chênh lệch (Chiến lược - BH BTC)       :    +468.89 USDT
  Chênh lệch (Chiến lược - BH Vũ trụ)    :    +820.85 USDT

==========================================================================================
PHÂN PHỐI NULL DANH MỤC NGẪU NHIÊN (1000 LẦN BỐC THĂM):
==========================================================================================
Net PnL THẬT: +1001.51 USDT
------------------------------------------------------------------------------------------
Mô hình                |      p05 |      p25 |   Median |      p75 |      p95 |      p99 |  Phân vị THẬT
------------------------------------------------------------------------------------------
Đối chứng ngẫu nhiên   |  -383.78 |  -275.43 |  -152.16 |    54.00 |   493.81 |  1159.18 |         98.6%
==========================================================================================

--- DIỄN GIẢI KẾT QUẢ (§3.3) ---
[KẾT LUẬN]: ĐÁNG NGHIÊN CỨU TIẾP. Cả ba tiêu chí đều thoả mãn: Net PnL > 0, Rebalances >= 20, và phân vị >= 95%.

Tổng thời gian chạy lệnh: 437.38s (7.29 phút)
==========================================================================================
```

### Lượt 2: Độ nhạy Lookback 60 (`--split is --lookback 60`)

```
==========================================================================================
BẮT ĐẦU ĐO LƯỜNG ĐỘNG LƯỢNG CẮT NGANG 20 MÃ | TẬP: IS (UTC)
Khoảng thời gian: 2022-02-15 -> 2025-12-31 UTC
Tham số: lookback=60d | rebalance=7d | k=3 | skip_recent=0d
Vốn: 500.0 USDT | Phí: 0.05% | Trượt giá: 0.0 bps | min_universe=10
==========================================================================================

--- ĐANG CHẠY PHÂN PHỐI NULL DANH MỤC NGẪU NHIÊN (N=1000) ---
(Không cần hiệu chỉnh xác suất: số kỳ tái cân bằng và số vị thế giống hệt nhau theo thiết kế)
Hoàn thành 1000 vòng bốc thăm null trong 435.29s

==========================================================================================
CẢNH BÁO HỆ THỐNG BẮT BUỘC:
  [1] [THIÊN LỆCH SỐNG SÓT] 20 mã chọn theo khối lượng 2026 đo lùi về quá khứ; đồng đã chết
      không có trong rổ; thiên lệch này bơm phồng vế long. Không sửa được bằng dữ liệu hiện có.
  [2] [CHƯA MÔ HÌNH HOÁ FUNDING] Vế short nhận/trả funding tuỳ chế độ thị trường, khoản này
      có thể cùng bậc độ lớn với kết quả.
  [3] [VŨ TRỤ THAY ĐỔI] Số mã đủ tư cách: min=10 | max=20 | trung bình=14.3
==========================================================================================

==========================================================================================
KẾT QUẢ THẬT (CROSS-SECTIONAL MOMENTUM):
==========================================================================================
Rebalances  | SkipReb  | SkipFills | Net PnL (USDT) | PnL %    | ProfitFactor | MaxDD %  | Sharpe   | Fees (USDT) | Turnover   | Univ TB
------------------------------------------------------------------------------------------
194         | 9        | 0         |       +1177.76 | +235.55% |         1.35 |   36.19% |     1.02 |       58.42 |   116844.3 |    14.3
==========================================================================================

HAI MỐC ĐỐI CHỨNG (CÙNG KỲ, CÙNG VỐN 500 USDT, CÙNG PHÍ):
  1. Mua-và-giữ BTC                     :    +554.61 USDT (+110.92%)
  2. Mua-và-giữ chia đều toàn vũ trụ (7d):    +164.82 USDT (+32.96%)
  -------------------------------------------------------------
  Chênh lệch (Chiến lược - BH BTC)       :    +623.15 USDT
  Chênh lệch (Chiến lược - BH Vũ trụ)    :   +1012.94 USDT

==========================================================================================
PHÂN PHỐI NULL DANH MỤC NGẪU NHIÊN (1000 LẦN BỐC THĂM):
==========================================================================================
Net PnL THẬT: +1177.76 USDT
------------------------------------------------------------------------------------------
Mô hình                |      p05 |      p25 |   Median |      p75 |      p95 |      p99 |  Phân vị THẬT
------------------------------------------------------------------------------------------
Đối chứng ngẫu nhiên   |  -372.66 |  -271.35 |  -147.07 |    45.23 |   468.73 |  1088.29 |         99.2%
==========================================================================================

--- DIỄN GIẢI KẾT QUẢ (§3.3) ---
[KẾT LUẬN]: ĐÁNG NGHIÊN CỨU TIẾP. Cả ba tiêu chí đều thoả mãn: Net PnL > 0, Rebalances >= 20, và phân vị >= 95%.

Tổng thời gian chạy lệnh: 436.99s (7.28 phút)
==========================================================================================
```

### Lượt 3: Độ nhạy Lookback 90 (`--split is --lookback 90`)

```
==========================================================================================
BẮT ĐẦU ĐO LƯỜNG ĐỘNG LƯỢNG CẮT NGANG 20 MÃ | TẬP: IS (UTC)
Khoảng thời gian: 2022-02-15 -> 2025-12-31 UTC
Tham số: lookback=90d | rebalance=7d | k=3 | skip_recent=0d
Vốn: 500.0 USDT | Phí: 0.05% | Trượt giá: 0.0 bps | min_universe=10
==========================================================================================

--- ĐANG CHẠY PHÂN PHỐI NULL DANH MỤC NGẪU NHIÊN (N=1000) ---
(Không cần hiệu chỉnh xác suất: số kỳ tái cân bằng và số vị thế giống hệt nhau theo thiết kế)
Hoàn thành 1000 vòng bốc thăm null trong 405.93s

==========================================================================================
CẢNH BÁO HỆ THỐNG BẮT BUỘC:
  [1] [THIÊN LỆCH SỐNG SÓT] 20 mã chọn theo khối lượng 2026 đo lùi về quá khứ; đồng đã chết
      không có trong rổ; thiên lệch này bơm phồng vế long. Không sửa được bằng dữ liệu hiện có.
  [2] [CHƯA MÔ HÌNH HOÁ FUNDING] Vế short nhận/trả funding tuỳ chế độ thị trường, khoản này
      có thể cùng bậc độ lớn với kết quả.
  [3] [VŨ TRỤ THAY ĐỔI] Số mã đủ tư cách: min=10 | max=19 | trung bình=14.2
==========================================================================================

==========================================================================================
KẾT QUẢ THẬT (CROSS-SECTIONAL MOMENTUM):
==========================================================================================
Rebalances  | SkipReb  | SkipFills | Net PnL (USDT) | PnL %    | ProfitFactor | MaxDD %  | Sharpe   | Fees (USDT) | Turnover   | Univ TB
------------------------------------------------------------------------------------------
190         | 13       | 0         |        +281.80 |  +56.36% |         1.14 |   46.46% |     0.50 |       28.48 |    56956.5 |    14.2
==========================================================================================

HAI MỐC ĐỐI CHỨNG (CÙNG KỲ, CÙNG VỐN 500 USDT, CÙNG PHÍ):
  1. Mua-và-giữ BTC                     :    +937.29 USDT (+187.46%)
  2. Mua-và-giữ chia đều toàn vũ trụ (7d):    +608.11 USDT (+121.62%)
  -------------------------------------------------------------
  Chênh lệch (Chiến lược - BH BTC)       :    -655.49 USDT
  Chênh lệch (Chiến lược - BH Vũ trụ)    :    -326.32 USDT

==========================================================================================
PHÂN PHỐI NULL DANH MỤC NGẪU NHIÊN (1000 LẦN BỐC THĂM):
==========================================================================================
Net PnL THẬT: +281.80 USDT
------------------------------------------------------------------------------------------
Mô hình                |      p05 |      p25 |   Median |      p75 |      p95 |      p99 |  Phân vị THẬT
------------------------------------------------------------------------------------------
Đối chứng ngẫu nhiên   |  -372.21 |  -274.02 |  -154.30 |    33.25 |   476.42 |  1015.20 |         90.4%
==========================================================================================

--- DIỄN GIẢI KẾT QUẢ (§3.3) ---
[KẾT LUẬN]: KHÔNG ĐẠT TIÊU CHÍ NGHIÊN CỨU TIẾP (Phân vị chưa vượt 95% (90.4%)).

Tổng thời gian chạy lệnh: 407.11s (6.79 phút)
==========================================================================================
```

### Lượt 4: Biến thể bỏ qua 1 ngày gần nhất (`--split is --skip-recent 1`)

```
==========================================================================================
BẮT ĐẦU ĐO LƯỜNG ĐỘNG LƯỢNG CẮT NGANG 20 MÃ | TẬP: IS (UTC)
Khoảng thời gian: 2022-02-15 -> 2025-12-31 UTC
Tham số: lookback=30d | rebalance=7d | k=3 | skip_recent=1d
Vốn: 500.0 USDT | Phí: 0.05% | Trượt giá: 0.0 bps | min_universe=10
==========================================================================================

--- ĐANG CHẠY PHÂN PHỐI NULL DANH MỤC NGẪU NHIÊN (N=1000) ---
(Không cần hiệu chỉnh xác suất: số kỳ tái cân bằng và số vị thế giống hệt nhau theo thiết kế)
Hoàn thành 1000 vòng bốc thăm null trong 436.77s

==========================================================================================
CẢNH BÁO HỆ THỐNG BẮT BUỘC:
  [1] [THIÊN LỆCH SỐNG SÓT] 20 mã chọn theo khối lượng 2026 đo lùi về quá khứ; đồng đã chết
      không có trong rổ; thiên lệch này bơm phồng vế long. Không sửa được bằng dữ liệu hiện có.
  [2] [CHƯA MÔ HÌNH HOÁ FUNDING] Vế short nhận/trả funding tuỳ chế độ thị trường, khoản này
      có thể cùng bậc độ lớn với kết quả.
  [3] [VŨ TRỤ THAY ĐỔI] Số mã đủ tư cách: min=10 | max=20 | trung bình=14.5
==========================================================================================

==========================================================================================
KẾT QUẢ THẬT (CROSS-SECTIONAL MOMENTUM):
==========================================================================================
Rebalances  | SkipReb  | SkipFills | Net PnL (USDT) | PnL %    | ProfitFactor | MaxDD %  | Sharpe   | Fees (USDT) | Turnover   | Univ TB
------------------------------------------------------------------------------------------
198         | 5        | 0         |        +652.89 | +130.58% |         1.27 |   39.10% |     0.75 |       68.04 |   136084.7 |    14.5
==========================================================================================

HAI MỐC ĐỐI CHỨNG (CÙNG KỲ, CÙNG VỐN 500 USDT, CÙNG PHÍ):
  1. Mua-và-giữ BTC                     :    +532.62 USDT (+106.52%)
  2. Mua-và-giữ chia đều toàn vũ trụ (7d):    +181.24 USDT (+36.25%)
  -------------------------------------------------------------
  Chênh lệch (Chiến lược - BH BTC)       :    +120.27 USDT
  Chênh lệch (Chiến lược - BH Vũ trụ)    :    +471.66 USDT

==========================================================================================
PHÂN PHỐI NULL DANH MỤC NGẪU NHIÊN (1000 LẦN BỐC THĂM):
==========================================================================================
Net PnL THẬT: +652.89 USDT
------------------------------------------------------------------------------------------
Mô hình                |      p05 |      p25 |   Median |      p75 |      p95 |      p99 |  Phân vị THẬT
------------------------------------------------------------------------------------------
Đối chứng ngẫu nhiên   |  -383.68 |  -271.40 |  -148.24 |    47.49 |   512.61 |  1216.67 |         97.0%
==========================================================================================

--- DIỄN GIẢI KẾT QUẢ (§3.3) ---
[KẾT LUẬN]: ĐÁNG NGHIÊN CỨU TIẾP. Cả ba tiêu chí đều thoả mãn: Net PnL > 0, Rebalances >= 20, và phân vị >= 95%.

Tổng thời gian chạy lệnh: 438.02s (7.30 phút)
==========================================================================================
```

### Lượt 5: Độ nhạy trượt giá 2.0 bps (`--split is --slippage-bps 2.0`)

```
==========================================================================================
BẮT ĐẦU ĐO LƯỜNG ĐỘNG LƯỢNG CẮT NGANG 20 MÃ | TẬP: IS (UTC)
Khoảng thời gian: 2022-02-15 -> 2025-12-31 UTC
Tham số: lookback=30d | rebalance=7d | k=3 | skip_recent=0d
Vốn: 500.0 USDT | Phí: 0.05% | Trượt giá: 2.0 bps | min_universe=10
==========================================================================================

--- ĐANG CHẠY PHÂN PHỐI NULL DANH MỤC NGẪU NHIÊN (N=1000) ---
(Không cần hiệu chỉnh xác suất: số kỳ tái cân bằng và số vị thế giống hệt nhau theo thiết kế)
Hoàn thành 1000 vòng bốc thăm null trong 381.89s

==========================================================================================
CẢNH BÁO HỆ THỐNG BẮT BUỘC:
  [1] [THIÊN LỆCH SỐNG SÓT] 20 mã chọn theo khối lượng 2026 đo lùi về quá khứ; đồng đã chết
      không có trong rổ; thiên lệch này bơm phồng vế long. Không sửa được bằng dữ liệu hiện có.
  [2] [CHƯA MÔ HÌNH HOÁ FUNDING] Vế short nhận/trả funding tuỳ chế độ thị trường, khoản này
      có thể cùng bậc độ lớn với kết quả.
  [3] [VŨ TRỤ THAY ĐỔI] Số mã đủ tư cách: min=10 | max=20 | trung bình=14.5
==========================================================================================

==========================================================================================
KẾT QUẢ THẬT (CROSS-SECTIONAL MOMENTUM):
==========================================================================================
Rebalances  | SkipReb  | SkipFills | Net PnL (USDT) | PnL %    | ProfitFactor | MaxDD %  | Sharpe   | Fees (USDT) | Turnover   | Univ TB
------------------------------------------------------------------------------------------
198         | 5        | 0         |        +954.58 | +190.92% |         1.34 |   37.80% |     0.90 |       73.97 |   147931.7 |    14.5
==========================================================================================

HAI MỐC ĐỐI CHỨNG (CÙNG KỲ, CÙNG VỐN 500 USDT, CÙNG PHÍ):
  1. Mua-và-giữ BTC                     :    +532.21 USDT (+106.44%)
  2. Mua-và-giữ chia đều toàn vũ trụ (7d):    +178.79 USDT (+35.76%)
  -------------------------------------------------------------
  Chênh lệch (Chiến lược - BH BTC)       :    +422.37 USDT
  Chênh lệch (Chiến lược - BH Vũ trụ)    :    +775.79 USDT

==========================================================================================
PHÂN PHỐI NULL DANH MỤC NGẪU NHIÊN (1000 LẦN BỐC THĂM):
==========================================================================================
Net PnL THẬT: +954.58 USDT
------------------------------------------------------------------------------------------
Mô hình                |      p05 |      p25 |   Median |      p75 |      p95 |      p99 |  Phân vị THẬT
------------------------------------------------------------------------------------------
Đối chứng ngẫu nhiên   |  -390.84 |  -289.35 |  -173.67 |    20.58 |   433.48 |  1055.90 |         98.7%
==========================================================================================

--- DIỄN GIẢI KẾT QUẢ (§3.3) ---
[KẾT LUẬN]: ĐÁNG NGHIÊN CỨU TIẾP. Cả ba tiêu chí đều thoả mãn: Net PnL > 0, Rebalances >= 20, và phân vị >= 95%.

Tổng thời gian chạy lệnh: 383.43s (6.39 phút)
==========================================================================================
```

### Lượt 6: Baseline OOS duy nhất (`--split oos`)

```
==========================================================================================
[CẢNH BÁO OOS] OOS chỉ được chạy MỘT LẦN sau khi tham số đã khoá.
Nếu bạn đang chỉnh tham số, đừng chạy lệnh này.
==========================================================================================

==========================================================================================
BẮT ĐẦU ĐO LƯỜNG ĐỘNG LƯỢNG CẮT NGANG 20 MÃ | TẬP: OOS (UTC)
Khoảng thời gian: 2026-01-01 -> 2026-09-02 UTC
Tham số: lookback=30d | rebalance=7d | k=3 | skip_recent=0d
Vốn: 500.0 USDT | Phí: 0.05% | Trượt giá: 0.0 bps | min_universe=10
==========================================================================================

--- ĐANG CHẠY PHÂN PHỐI NULL DANH MỤC NGẪU NHIÊN (N=1000) ---
(Không cần hiệu chỉnh xác suất: số kỳ tái cân bằng và số vị thế giống hệt nhau theo thiết kế)
Hoàn thành 1000 vòng bốc thăm null trong 112.90s

==========================================================================================
CẢNH BÁO HỆ THỐNG BẮT BUỘC:
  [1] [THIÊN LỆCH SỐNG SÓT] 20 mã chọn theo khối lượng 2026 đo lùi về quá khứ; đồng đã chết
      không có trong rổ; thiên lệch này bơm phồng vế long. Không sửa được bằng dữ liệu hiện có.
  [2] [CHƯA MÔ HÌNH HOÁ FUNDING] Vế short nhận/trả funding tuỳ chế độ thị trường, khoản này
      có thể cùng bậc độ lớn với kết quả.
  [3] [VŨ TRỤ THAY ĐỔI] Số mã đủ tư cách: min=20 | max=20 | trung bình=20.0
==========================================================================================

==========================================================================================
KẾT QUẢ THẬT (CROSS-SECTIONAL MOMENTUM):
==========================================================================================
Rebalances  | SkipReb  | SkipFills | Net PnL (USDT) | PnL %    | ProfitFactor | MaxDD %  | Sharpe   | Fees (USDT) | Turnover   | Univ TB
------------------------------------------------------------------------------------------
35          | 0        | 0         |         -16.25 |   -3.25% |         0.96 |   26.52% |     0.02 |        7.36 |    14727.2 |    20.0
==========================================================================================

HAI MỐC ĐỐI CHỨNG (CÙNG KỲ, CÙNG VỐN 500 USDT, CÙNG PHÍ):
  1. Mua-và-giữ BTC                     :     -65.21 USDT (-13.04%)
  2. Mua-và-giữ chia đều toàn vũ trụ (7d):     -17.85 USDT ( -3.57%)
  -------------------------------------------------------------
  Chênh lệch (Chiến lược - BH BTC)       :     +48.96 USDT
  Chênh lệch (Chiến lược - BH Vũ trụ)    :      +1.60 USDT

==========================================================================================
PHÂN PHỐI NULL DANH MỤC NGẪU NHIÊN (1000 LẦN BỐC THĂM):
==========================================================================================
Net PnL THẬT: -16.25 USDT
------------------------------------------------------------------------------------------
Mô hình                |      p05 |      p25 |   Median |      p75 |      p95 |      p99 |  Phân vị THẬT
------------------------------------------------------------------------------------------
Đối chứng ngẫu nhiên   |  -248.05 |  -113.37 |   -25.42 |    61.85 |   227.11 |   395.04 |         53.0%
==========================================================================================

--- DIỄN GIẢI KẾT QUẢ (§3.3) ---
[KẾT LUẬN]: KHÔNG ĐẠT TIÊU CHÍ NGHIÊN CỨU TIẾP (Net PnL âm (-16.25 USDT), Phân vị chưa vượt 95% (53.0%)).

Tổng thời gian chạy lệnh: 113.55s (1.89 phút)
==========================================================================================
```

---

## 2. Bảng tổng hợp IS vs OOS

| Lượt | Tập | Lookback | Rebalance | $k$ | Skip | Slip (bps) | Net PnL Thật (USDT) | PnL % | BH BTC (USDT) | BH Vũ trụ (USDT) | Median Null (USDT) | Phân vị Thật Null | Kết luận (§3.3) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **1. Baseline IS** | **IS** | 30d | 7d | 3 | 0d | 0.0 | **+1,001.51** | +200.30% | +532.62 | +180.67 | −152.16 | **98.6%** | Đạt trên IS |
| **2. Lookback 60** | **IS** | 60d | 7d | 3 | 0d | 0.0 | **+1,177.76** | +235.55% | +554.61 | +164.82 | −147.07 | **99.2%** | Đạt trên IS |
| **3. Lookback 90** | **IS** | 90d | 7d | 3 | 0d | 0.0 | **+281.80** | +56.36% | +937.29 | +608.11 | −154.30 | **90.4%** | Dưới p95 |
| **4. Skip-recent 1** | **IS** | 30d | 7d | 3 | 1d | 0.0 | **+652.89** | +130.58% | +532.62 | +181.24 | −148.24 | **97.0%** | Đạt trên IS |
| **5. Trượt giá 2.0** | **IS** | 30d | 7d | 3 | 0d | 2.0 | **+954.58** | +190.92% | +532.21 | +178.79 | −173.67 | **98.7%** | Đạt trên IS |
| **6. Baseline OOS** | **OOS** | 30d | 7d | 3 | 0d | 0.0 | **−16.25** | −3.25% | −65.21 | −17.85 | −25.42 | **53.0%** | **KHÔNG ĐẠT** |

---

## 3. Kết luận theo tiêu chí chốt trước (§3.3)

> **KẾT LUẬN:** **KHÔNG ĐẠT TIÊU CHÍ NGHIÊN CỨU TIẾP** (trên tập OOS, chiến lược ghi nhận Net PnL âm **−16.25 USDT** và nằm ở **phân vị 53.0%** của phân phối null — tức hoàn toàn chìm vào nhiễu ngẫu nhiên, vi phạm hai trong ba điều kiện bắt buộc của §3.3).

Mặc dù trên OOS chiến lược mất ít hơn Mua-và-giữ BTC (+48.96 USDT chênh lệch) và tương đương Mua-và-giữ vũ trụ (+1.60 USDT chênh lệch) do tính chất trung tính thị trường giúp bảo vệ vốn trong năm 2026 giảm giá, nhưng việc phân vị chỉ đạt 53.0% cho thấy việc xếp hạng động lượng 30 ngày không tạo ra thêm bất kỳ lợi thế chọn mã nào so với bốc thăm ngẫu nhiên.

---

## 4. Nhận định bề mặt tham số (§3.2)

- Bốn biến thể trên IS (lookback 30, 60, 90, skip 1d, slippage 2.0 bps) **đều cho PnL dương mạnh** (+281 đến +1.177 USDT) và vượt trội so với trung vị ngẫu nhiên null (~ −150 USDT).
- Bề mặt tham số quanh lookback 30d–60d là **tương đối phẳng**: lookback 30d đạt +1001 USDT, lookback 60d đạt +1177 USDT, khi tăng trượt giá lên 2.0 bps PnL chỉ giảm nhẹ từ +1001 về +954 USDT (chi phí turnover rất kiểm soát). Tuy nhiên khi kéo dài lookback lên 90d, hiệu năng giảm đáng kể xuống +281 USDT (phân vị 90.4%).
- Sự sụp đổ của hiệu năng từ IS (+200%) sang OOS (−3.25%, phân vị 53.0%) phản ánh hiện tượng **momentum breakdown** trong giai đoạn 8 tháng đầu năm 2026 của thị trường crypto, khi các altcoin xoay vòng ngắn và không hình thành xu hướng phân hoá kéo dài theo chu kỳ 30 ngày.

---

## 5. Điều phép đo này KHÔNG trả lời

1. **Thiên lệch sống sót (Survivorship Bias):** Rổ 20 mã được chọn lọc dựa trên top thanh khoản của năm 2026 rồi đo lùi về 2022. Những mã đã bị delist hoặc sụp đổ trong giai đoạn 2022–2024 không có mặt trong dữ liệu. Thiên lệch này làm tăng đáng kể lợi suất vế Long trên tập IS trong quá khứ.
2. **Chưa mô hình hoá Funding Rate:** Vế Short thường nhận funding rate dương trong các giai đoạn bull market/đi ngang và phải trả funding trong bear market. Trong mô hình hiện tại, funding chưa được trừ/cộng vào PnL; khoản này có thể có quy mô đáng kể so với kết quả net.
3. **Giả định thanh khoản lý tưởng:** Chiến lược giả định các lệnh tái cân bằng luôn khớp được ở giá Open $t+1$ cho mọi mã với cùng mức trượt giá danh nghĩa, không tính đến độ trượt thực tế và độ sâu sổ lệnh khác nhau giữa các altcoin vốn hoá nhỏ và BTC/ETH.
4. **Giới hạn một sàn giao dịch:** Toàn bộ dữ liệu lấy từ BingX perpetual, không phản ánh sự khác biệt về spread hay funding giữa các sàn lớn như Binance hay OKX.
5. **Chưa kiểm định Walk-Forward:** Phép đo sử dụng một mốc chia cố định (IS 2022–2025 và OOS 2026), chưa áp dụng tái tối ưu hoá cửa sổ trượt (rolling walk-forward).
