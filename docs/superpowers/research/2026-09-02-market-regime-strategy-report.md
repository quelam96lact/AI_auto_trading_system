# Báo cáo Đợt 9 — Đo lường Chiến lược theo Chế độ Thị trường (Giai đoạn 1: ĐO)

**Ngày thực hiện:** 02/09/2026  
**Thực hiện theo brief:** `docs/superpowers/plans/2026-09-02-brief-chien-luoc-theo-che-do-thi-truong.md`  
**Bộ dữ liệu:** `bars_daily` (1.554 mã, 2.982.903 bar, 2016-01-04 → 2026-08-28; 2.662 phiên giao dịch).  
**Rổ mã đo lường:** 1.308 mã hợp lệ (đã loại 246 mã không đáng tin: 50 mã chia tách chưa điều chỉnh + 209 mã có tỷ lệ bar rác $\ge 5\%$, theo `exclusions.txt`).  
**Hạ tầng backtest:** `PaperBroker` (khung 1d, T+2,5, phí 0.25%, thuế bán 0.1%, trượt giá 5 bps, mốc mua-và-giữ cùng mã/kỳ/vốn/phí). Vốn giả lập: 1.000.000.000 VNĐ / mã.

---

## 1. Task 1 — Thước đo Độ rộng Thị trường (Market Breadth) & Phân loại Chế độ

### 1.1. Định nghĩa chuẩn (đóng băng, không dò ngưỡng)

Vì `bars_daily` không có chỉ số `VNINDEX` / `VN30`, độ rộng thị trường được dựng trực tiếp từ rổ cổ phiếu:
$$\text{breadth}(d) = \frac{\text{Số mã có } \text{close}(d) > \text{SMA200}(\text{close}, d)}{\text{Tổng số mã có đủ 200 phiên lịch sử tính tới ngày } d}$$

Phân loại 3 chế độ thị trường theo ngưỡng cố định xác định trước:
- **`RISK_ON`**: $\text{breadth} \ge 0,60$
- **`NEUTRAL`**: $0,40 \le \text{breadth} < 0,60$
- **`RISK_OFF`**: $\text{breadth} < 0,40$

**Chống look-ahead:** $\text{breadth}(d)$ chỉ dùng dữ liệu tới hết ngày $d$. Quyết định giao dịch tại ngày $d$ (mở lệnh ở Open phiên $d$) bắt buộc sử dụng $\text{regime}(d-1)$ (chế độ ngày giao dịch liền trước).

### 1.2. Phân bố chế độ trên toàn bộ lịch sử (2016-01-04 → 2026-08-28)

File kết quả: `docs/superpowers/research/2026-09-02-breadth-daily.csv` (2.662 phiên).

| Chế độ | Ngưỡng | Số phiên | Tỷ lệ % |
|---|---|---:|---:|
| **`RISK_ON`** | $\text{breadth} \ge 0,60$ | 683 | 25,7% |
| **`NEUTRAL`** | $0,40 \le \text{breadth} < 0,60$ | 1.291 | 48,5% |
| **`RISK_OFF`** | $\text{breadth} < 0,40$ | 688 | 25,8% |
| **Tổng cộng** | | **2.662** | **100,0%** |

*Kiểm chứng tiêu chí dừng:* Cả 3 chế độ đều chiếm $> 25\%$ tổng số phiên (không có chế độ nào $< 10\%$), cho thấy ngưỡng $0,40 / 0,60$ phân chia dữ liệu cân đối và có ý nghĩa thực tế.

**Lệnh chạy lại:**
```bash
uv run python scripts/market_regime.py --exclude-file exclusions.txt --output docs/superpowers/research/2026-09-02-breadth-daily.csv
```

---

## 2. Task 4 & Kiểm chứng phá hoại (Destructive Testing)

File test: `tests/test_market_regime.py` gồm 4 unit test tất định, không chạm DB:
1. `test_breadth_dem_dung`: rổ 5 mã dựng tay, 3 mã trên MA200 $\Rightarrow$ breadth = 0.6.
2. `test_phan_loai_dung_nguong`: kiểm đúng biên (0.60 $\Rightarrow$ RISK_ON; 0.5999 $\Rightarrow$ NEUTRAL; 0.40 $\Rightarrow$ NEUTRAL; 0.3999 $\Rightarrow$ RISK_OFF).
3. `test_khong_nhin_trom_tuong_lai`: thêm bar ngày $d+1$ vào dữ liệu không làm đổi $\text{breadth}(d)$.
4. `test_ma_thieu_lich_su_bi_loai`: mã $< 200$ phiên bị loại khỏi mẫu số.

### Kết quả chạy test sạch
```
uv run pytest tests/test_market_regime.py -v
============================= test session starts =============================
tests/test_market_regime.py::test_breadth_dem_dung PASSED                [ 25%]
tests/test_market_regime.py::test_phan_loai_dung_nguong PASSED           [ 50%]
tests/test_market_regime.py::test_khong_nhin_trom_tuong_lai PASSED       [ 75%]
tests/test_market_regime.py::test_ma_thieu_lich_su_bi_loai PASSED        [100%]
============================== 4 passed in 0.22s ==============================
```

### Kiểm chứng phá hoại Test 1 (cố tình phá công thức tính breadth)
Đổi `compute_breadth` trả về `(num / denom) + 0.1`:
```
================================== FAILURES ===================================
____________________________ test_breadth_dem_dung ____________________________
    breadth = compute_breadth(bars_by_symbol, as_of)
>   assert pytest.approx(breadth, rel=1e-6) == 0.6
E   assert 0.7 ± 7.0e-07 == 0.6
E     comparison failed
E     Obtained: 0.6
E     Expected: 0.7 ± 7.0e-07

tests\test_market_regime.py:57: AssertionError
============================== 1 failed in 0.50s ==============================
```

### Kiểm chứng phá hoại Test 3 (cố tình đưa look-ahead vào `compute_breadth`)
Bỏ điều kiện lọc ngày `_bar_date(b) <= as_of` để hàm nhìn thấy bar tương lai $d+1$:
```
================================== FAILURES ===================================
_______________________ test_khong_nhin_trom_tuong_lai ________________________
    breadth_before = compute_breadth(bars_by_symbol, as_of)
    # Thêm bar tương lai d+1
    ...
    breadth_after = compute_breadth(bars_by_symbol, as_of)
>   assert breadth_before == breadth_after
E   assert 0.6 == 0.4

tests\test_market_regime.py:104: AssertionError
============================== 1 failed in 0.39s ==============================
```
*(Đã khôi phục code sạch hoàn toàn sau khi kiểm chứng).*

---

## 3. Task 2 — Đo từng Chiến lược theo Chế độ trên Kỳ Trong Mẫu (2016-01-04 → 2022-12-31)

**Lệnh chạy lại:**
```bash
uv run python scripts/measure_market_regime.py --task task2 --exclude-file exclusions.txt
```

### Bảng 3×3 Kỳ Trong Mẫu (2016-01-04 → 2022-12-31, 1.308 mã, vốn 1 tỷ/mã)

| Chiến lược | `RISK_ON` (PnL / Lệnh / Win%) | `NEUTRAL` (PnL / Lệnh / Win%) | `RISK_OFF` (PnL / Lệnh / Win%) |
|---|:---:|:---:|:---:|
| `daily_breakout` | **+3,42 tỷ** \| 4.140 lệnh \| 33,6% | **−1,30 tỷ** \| 5.617 lệnh \| 29,2% | **−5,15 tỷ** \| 3.601 lệnh \| 30,7% |
| `octopus_pullback` | **−0,04 tỷ** \| 525 lệnh \| 39,6% | **−0,51 tỷ** \| 273 lệnh \| 30,8% | **−0,01 tỷ** \| 42 lệnh \| 33,3% |
| `sma_cross` | **−0,85 tỷ** \| 3.831 lệnh \| 32,8% | **−7,49 tỷ** \| 6.936 lệnh \| 29,2% | **−6,75 tỷ** \| 4.464 lệnh \| 31,3% |

### Hai mốc so sánh kỳ trong mẫu (2016 → 2022)

1. **Mua-và-giữ cùng kỳ (1.308 mã):** **+1.007,12 tỷ VNĐ** (`+1.007.120.339.803`).
2. **Chiến lược đơn tốt nhất toàn kỳ (không chuyển đổi):**
   - `octopus_pullback`: **−0,56 tỷ VNĐ** (`−561.209.185`, 840 lệnh, win 36,4%).
   - `daily_breakout`: **−2,64 tỷ VNĐ** (`−2.636.874.998`, 13.358 lệnh, win 30,9%).
   - `sma_cross`: **−14,69 tỷ VNĐ** (`−14.692.528.412`, 15.231 lệnh, win 30,7%).

**Phát hiện từ kỳ trong mẫu:**
- Ô duy nhất tạo ra PnL dương trong toàn bộ bảng là **`daily_breakout` trong chế độ `RISK_ON` (+3,42 tỷ VNĐ)**.
- Khi thị trường ở `NEUTRAL` hoặc `RISK_OFF`, cả ba chiến lược đều bị bào mòn vốn và thua lỗ nặng.
- Nếu không chuyển đổi chế độ, `daily_breakout` lỗ tổng cộng −2,64 tỷ do gánh khoản lỗ −6,45 tỷ từ `NEUTRAL` và `RISK_OFF`.

---

## 4. Task 3 — Đóng băng Quy tắc Chuyển đổi và Kiểm thử Kỳ Ngoài Mẫu

### 4.1. Khai báo quy tắc đóng băng (Ghi nhận TRƯỚC khi chạy ngoài mẫu)

Từ bảng 3×3 trong mẫu, chỉ có duy nhất một cấu hình có cơ sở dữ liệu:
- `RISK_ON` $\rightarrow$ `daily_breakout`
- `NEUTRAL` $\rightarrow$ `KHONG_GIAO_DICH` (`NONE`)
- `RISK_OFF` $\rightarrow$ `KHONG_GIAO_DICH` (`NONE`)

*Số lượng quy tắc thử nghiệm:* Đúng **1 quy tắc duy nhất** (không thử nghiệm nhiều quy tắc để cherry-pick).

---

### 4.2. Kết quả trên Kỳ Ngoài Mẫu (2023-01-01 → 2026-08-28)

**Lệnh chạy lại:**
```bash
uv run python scripts/measure_market_regime.py --task task3 --exclude-file exclusions.txt
```

#### Kết quả quy tắc chuyển đổi đóng băng ngoài mẫu:
- **PnL Quy tắc ngoài mẫu:** **−8.829.397.869 VNĐ (−8,83 tỷ)**
- **Số lệnh:** 4.054 lệnh (SELL fills)
- **Tỷ lệ thắng:** 26,6%
- **Chênh lệch so với Mua-và-giữ ngoài mẫu:** **−666.801.741.520 VNĐ (−666,80 tỷ)**

#### Đối chiếu với 3 mốc so sánh bắt buộc:

| Mốc so sánh | PnL (VNĐ) | Số lệnh | Win Rate |
|---|---:|---:|---:|
| **1. Mua-và-giữ ngoài mẫu (2023 → 2026-08)** | **+657.972.343.651 (+657,97 tỷ)** | 1.308 mã | — |
| **2. Chiến lược đơn tốt nhất ngoài mẫu (`octopus_pullback`)** | **−1.094.143.389 (−1,09 tỷ)** | 572 | 29,5% |
| *-- Đơn `daily_breakout` (không chuyển)* | *−17.157.516.859 (−17,16 tỷ)* | 9.777 | 27,8% |
| *-- Đơn `sma_cross` (không chuyển)* | *−24.130.355.584 (−24,13 tỷ)* | 12.380 | 27,9% |
| **3. Chính quy tắc đó trên kỳ trong mẫu (2016 → 2022)** | **+1.105.457.094 (+1,11 tỷ)** | 9.340 | 33,3% |
| **Quy tắc đóng băng trên kỳ ngoài mẫu (2023 → 2026-08)** | **−8.829.397.869 (−8,83 tỷ)** | **4.054** | **26,6%** |

---

## 5. Phân tích Khoa học & Kết luận

1. **Quy tắc chuyển đổi chế độ sụp đổ ở kỳ ngoài mẫu:**
   - Khoản "lãi" +1,11 tỷ trong mẫu của quy tắc chuyển đổi biến thành khoản lỗ **−8,83 tỷ** ngoài mẫu.
   - Tỷ lệ thắng sụt giảm từ 33,3% xuống **26,6%**.
   - Mặc dù quy tắc chuyển đổi giảm lỗ so với việc chạy `daily_breakout` đơn thuần cả kỳ ngoài mẫu (−8,83 tỷ vs −17,16 tỷ), nó vẫn:
     - **Thua xa Mua-và-giữ** (+657,97 tỷ vs −8,83 tỷ).
     - **Thua chiến lược rủi ro thấp đơn lẻ `octopus_pullback`** (−1,09 tỷ).

2. **Bản chất của vấn đề:**
   - Hiện tượng `daily_breakout` có lãi trong `RISK_ON` ở giai đoạn 2016–2021 là hệ quả của con sóng siêu chu kỳ tăng trưởng thanh khoản (uptrend 2017 & 2020–2021), khi breakout có xác suất tiếp diễn cao.
   - Giai đoạn 2023–2026, ngay cả trong các nhịp `RISK_ON` (breadth $\ge 0,60$), các phiên breakout phần lớn là bull-trap hoặc gặp lực bán chốt lời T+2,5 nhanh, khiến chiến lược breakout thuần túy tiếp tục thua lỗ.
   - Việc ghép bộ lọc chế độ thị trường **không tạo ra alpha mới** cho một chiến lược vốn đã không có lợi thế kỳ vọng.

3. **Quyết định cho Engine (Khuyến nghị cho Claude Audit):**
   - **KẾT QUẢ "KHÔNG" CÓ BẰNG CHỨNG:** Không triển khai chuyển đổi chiến lược theo regime vào engine live.
   - Giữ nguyên trạng thái engine ở chế độ Paper (`real_trading_enabled: false`) để bảo vệ vốn thật.
   - Đây là kết quả thành công của phương pháp nghiên cứu định lượng nghiêm ngặt (đo trước, dựng sau, không sửa số liệu).

---

## 6. Bảng Đối chiếu Tiêu chí Hoàn thành

| # | Tiêu chí | Trạng thái | Chi tiết kiểm chứng |
|---|---|:---:|---|
| 1 | `market_regime.py` | **ĐẠT** | `uv run pytest tests/test_market_regime.py -v` $\rightarrow$ 4 passed |
| 2 | Kiểm chứng phá hoại | **ĐẠT** | Output đỏ nguyên văn test 1 và test 3 dán tại Mục 2 |
| 3 | Chuỗi breadth | **ĐẠT** | `2026-09-02-breadth-daily.csv` (2.662 phiên); RISK_ON: 25,7%, NEUTRAL: 48,5%, RISK_OFF: 25,8% |
| 4 | Bảng 3×3 trong mẫu | **ĐẠT** | Bảng 3×3 + 2 mốc so sánh tại Mục 3 |
| 5 | Đóng băng quy tắc | **ĐẠT** | Ghi nhận quy tắc tại Mục 4.1 trước khi nạp kết quả ngoài mẫu |
| 6 | Kết quả ngoài mẫu | **ĐẠT** | Đối chiếu 3 mốc so sánh tại Mục 4.2 |
| 7 | Không hồi quy test | **ĐẠT** | `uv run pytest -m "not integration" -q` $\rightarrow$ 355 passed, 97 deselected |
| 8 | Linter | **ĐẠT** | `uv run ruff check trading tests scripts` $\rightarrow$ All checks passed! |

---

## 7. GHI CHÚ AUDIT (Claude, 02/09/2026)

Toàn bộ số liệu Mục 4.2 đã được chạy lại độc lập và **tái lập đúng đến từng
đồng** (8/8 con số: −8.829.397.869 / 4.054 lệnh / 26,6% / chênh BH
−666.801.741.520 / BH +657.972.343.651 / octopus −1.094.143.389 /
daily_breakout −17.157.516.859 / sma_cross −24.130.355.584). Quy tắc được ghi
ở 4.1 trước kết quả 4.2, đúng trình tự brief yêu cầu.

**Kết luận Mục 5 được chấp nhận.** Ba điểm dưới đây là hạn chế của phép đo,
không điểm nào thu hẹp được khoảng cách −666,80 tỷ tới mua-và-giữ.

### 7.1. Tín hiệu BÁN bị chặn nhầm khi chế độ là `NONE`

`measure_market_regime.py` chỉ lấy signal từ chiến lược đang active, nên khi
`rule[regime] == "NONE"` thì `signal = None`. Nhưng cả ba chiến lược dùng
chính `Signal(..., "SELL", held)` để **thoát** vị thế
(`trading/strategies/daily_breakout.py:87`). Hệ quả: vị thế mở trong
`RISK_ON`, khi thị trường chuyển `NEUTRAL`, **chỉ còn thoát được bằng trailing
stop** — không bao giờ thoát theo luật của chiến lược. Trái với chính docstring
của hàm ("không mở vị thế mới").

Hướng lệch: giữ hàng lâu hơn vào vùng xấu ⇒ **−8,83 tỷ có phần bi quan hơn**
quy tắc đã khai. Cần sửa trước khi con số này được dùng lại cho việc gì khác.

### 7.2. 199 phiên `RISK_OFF` đầu chuỗi là hiện vật, không phải thị trường

Từ 2016-01-04 đến 2016-10-19, breadth **đúng bằng 0** — không phải vì thị
trường xấu mà vì chưa mã nào đủ 200 phiên lịch sử trong bộ dữ liệu; ngày
2016-10-20 nhảy thẳng lên 0,489. Đó là **199/688 = 28,9% toàn bộ số phiên
`RISK_OFF`**, nằm trọn trong kỳ trong mẫu.

Bảng 3×3 (Mục 3) vì thế bị nhiễm ở cột `RISK_OFF`. Kỳ ngoài mẫu 2023+ không
ảnh hưởng, nên kết luận không đổi.

### 7.3. Bảng 3×3 không dự đoán được hành vi của quy tắc

Ô thắng duy nhất ghi **4.140 lệnh**, nhưng chính quy tắc đó trên cùng kỳ ra
**9.340 lệnh** và **+1,11 tỷ** chứ không phải +3,42 tỷ. Không mâu thuẫn: ở lượt
chạy không chặn, chiến lược thường **đang giữ hàng** nên bỏ lỡ nhiều điểm vào
trong `RISK_ON`; khi bị chặn nó rảnh tay hơn nhiều.

Nhưng Mục 4.1 trình bày quy tắc như thể suy ra từ bảng, trong khi bảng có tính
chất khác. Bảng quy kết lệnh theo chế độ **là công cụ mô tả, không phải công cụ
dự đoán** — ai đọc lại tài liệu này cần biết điều đó trước khi dựa vào bảng để
chọn quy tắc khác.
