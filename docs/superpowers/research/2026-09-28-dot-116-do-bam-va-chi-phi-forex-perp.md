# Báo cáo Đợt 116 — Đo độ bám của Forex Perp BingX và Chi phí giữ vị thế

**Ngày thực hiện:** 2026-09-28 (thứ Hai)  
**Base commit:** `b9a5a04` (trên main)  
**Người audit:** Claude. **Người thực thi:** Agent.  
**Cam kết an toàn:** Không commit, không push, không đặt lệnh, không gọi endpoint có ký, không sửa `trading/`, không đọc dữ liệu từ 2026-09-01. Mọi hằng số phí/funding đều có URL nguồn.

---

## 1. Kết luận ba dòng cốt lõi (§2.1 Brief 116)

1. **EUR/USD:** **KHÔNG ĐẠT** tiêu chuẩn để đo tiếp (Số năm gốc = 27,6 năm ≥ 10 năm [ĐẠT]; |basis| trung vị = 0,0121% ≤ 0,5% [ĐẠT]; Tương quan lợi suất ngày tốt nhất = 0,7345 < 0,95 [KHÔNG ĐẠT]).
2. **USD/JPY:** **KHÔNG ĐẠT** tiêu chuẩn để đo tiếp (Số năm gốc = 55,6 năm ≥ 10 năm [ĐẠT]; |basis| trung vị = 0,0323% ≤ 0,5% [ĐẠT]; Tương quan lợi suất ngày tốt nhất = 0,8605 < 0,95 [KHÔNG ĐẠT]).
3. **Chi phí giữ vị thế:** Chi phí giữ 5 ngày chiếm **60,82%** biên độ một ngày với EUR/USD (`FRB_H10`) và **63,64%** biên độ một ngày với USD/JPY (`FRB_H10`).

---

## 2. Output Task A — Nạp nến Forex và Đo độ bám

### 2.1. A1. Nạp nến và đối chiếu cơ sở dữ liệu

Lệnh nạp nến khung 1d (đến hết mốc niêm phong `2026-08-31`):
```text
uv run python scripts/bingx_klines.py --symbols NCFXEUR2USD-USDT,NCFXUSD2JPY-USDT --interval 1d --to 2026-08-31
Bắt đầu nạp nến BingX cho 2 cặp (khung 1d)...
Danh sách: NCFXEUR2USD-USDT, NCFXUSD2JPY-USDT
[ 1/2] NCFXEUR2USD-USDT:   316 nến (2025-08-27 -> 2026-08-31) |  1 calls |   0.7s
[ 2/2] NCFXUSD2JPY-USDT:   315 nến (2025-08-28 -> 2026-08-31) |  1 calls |   0.2s

==============================================================================
TỔNG KẾT NẠP NẾN BINGX (1D): 631 nến | 2 calls | 0.9s
==============================================================================
```

Lệnh nạp nến khung 1h (đến hết mốc niêm phong `2026-08-31`):
```text
uv run python scripts/bingx_klines.py --symbols NCFXEUR2USD-USDT,NCFXUSD2JPY-USDT --interval 1h --to 2026-08-31
Bắt đầu nạp nến BingX cho 2 cặp (khung 1h)...
Danh sách: NCFXEUR2USD-USDT, NCFXUSD2JPY-USDT
[ 1/2] NCFXEUR2USD-USDT:   724 nến (2026-07-20 -> 2026-08-31) |  1 calls |   0.3s
[ 2/2] NCFXUSD2JPY-USDT:   724 nến (2026-07-20 -> 2026-08-31) |  1 calls |   0.2s

==============================================================================
TỔNG KẾT NẠP NẾN BINGX (1H): 1,448 nến | 2 calls | 0.6s
==============================================================================
```

Kết quả truy vấn kiểm chứng trong `bars_crypto`:
```sql
SELECT symbol, interval, count(*), min(ts)::date, max(ts)::date
FROM bars_crypto WHERE symbol LIKE 'NCFX%' GROUP BY 1,2 ORDER BY 1,2;
```
```text
symbol           | interval | count | min_ts     | max_ts
NCFXEUR2USD-USDT | 1d       |   316 | 2025-08-27 | 2026-08-31
NCFXEUR2USD-USDT | 1h       |   724 | 2026-07-20 | 2026-08-31
NCFXUSD2JPY-USDT | 1d       |   315 | 2025-08-28 | 2026-08-31
NCFXUSD2JPY-USDT | 1h       |   724 | 2026-07-20 | 2026-08-31
```

> **Ghi nhận về số nến 1d (315 – 316 nến):**
> Trong 369 ngày theo lịch từ ngày niêm yết (cuối tháng 08/2025) đến 31/08/2026:
> - Số nến thứ Bảy (Day of Week = 5): **0 nến** (BingX đóng phiên, không vẽ nến thứ Bảy).
> - Số nến Chủ nhật (Day of Week = 6): **52 nến** (BingX mở phiên sớm vào chiều tối Chủ nhật ~21:00 UTC và vẽ nến 1d cho khoảng 2-3 tiếng trước 00:00 UTC).
> - Các ngày trong tuần (T2 đến T6): 52–53 nến mỗi ngày.
> Tổng số nến 1d là 5 ngày làm việc + Chủ nhật = 6 ngày/tuần × 52 tuần ≈ 315–316 nến.

---

### 2.2. A2. Kiểm chất lượng nến vừa nạp

Bảng tổng hợp kiểm định chất lượng dữ liệu:

| Mã | Khung | Tổng số nến | Nến bẩn (`is_dirty_bar`) | Nến `volume = 0` | Ngày trùng lặp | Khoảng trống max (giờ) | Ghi chú khoảng trống |
|---|---|---|---|---|---|---|---|
| `NCFXEUR2USD-USDT` | `1d` | 316 | 0 | 0 | 0 | 72,0h | Thứ Sáu 00:00 UTC $\rightarrow$ Thứ Hai 00:00 UTC (cuối tuần) |
| `NCFXEUR2USD-USDT` | `1h` | 724 | 0 | 0 | 0 | 47,0h | Thứ Sáu 20:00 UTC $\rightarrow$ Chủ nhật 19:00 UTC (cuối tuần) |
| `NCFXUSD2JPY-USDT` | `1d` | 315 | 0 | 0 | 0 | 72,0h | Thứ Sáu 00:00 UTC $\rightarrow$ Thứ Hai 00:00 UTC (cuối tuần) |
| `NCFXUSD2JPY-USDT` | `1h` | 724 | 0 | 0 | 0 | 47,0h | Thứ Sáu 20:00 UTC $\rightarrow$ Chủ nhật 19:00 UTC (cuối tuần) |

Câu lệnh SQL kiểm chứng đã chạy:
```sql
-- 1. Kiểm nến bẩn, volume=0, duplicate
SELECT symbol, interval,
  COUNT(*) as total,
  COUNT(*) FILTER (WHERE open <= 0 OR high <= 0 OR low <= 0 OR close <= 0) as dirty_count,
  COUNT(*) FILTER (WHERE volume = 0) as zero_volume_count,
  COUNT(*) - COUNT(DISTINCT ts) as duplicate_ts_count
FROM bars_crypto
WHERE symbol LIKE 'NCFX%'
GROUP BY symbol, interval
ORDER BY symbol, interval;

-- 2. Kiểm khoảng trống max (giờ)
WITH lag_cte AS (
    SELECT symbol, interval, ts,
           LAG(ts) OVER (PARTITION BY symbol, interval ORDER BY ts) as prev_ts
    FROM bars_crypto
    WHERE symbol LIKE 'NCFX%'
)
SELECT symbol, interval,
       ROUND(MAX(EXTRACT(EPOCH FROM (ts - prev_ts)) / 3600.0)::numeric, 1) as max_gap_hours
FROM lag_cte
WHERE prev_ts IS NOT NULL
GROUP BY symbol, interval
ORDER BY symbol, interval;
```

---

### 2.3. A3. Đo độ bám

Output nguyên văn khi chạy script chuẩn `scripts/check_bingx_tracking.py`:
```text
uv run python scripts/check_bingx_tracking.py

========================================================================================================================
BẢNG CHÍNH: TỔNG HỢP KIỂM TRA ĐỘ BÁM CỦA BINGX SO VỚI TÀI SẢN GỐC (BRIEF ĐỢT 115)
========================================================================================================================
Tài sản          | Nguồn (điều khoản)           | Năm BĐ | Số ngày | Basis trung vị (P5–P95) | Tương quan |   TE năm | Căn ngày tốt hơn | Đủ đo tiếp? 
------------------------------------------------------------------------------------------------------------------------
Vàng (XAU/USD sp | Không có nguồn đạt chuẩn     |    N/A |       0 | N/A                    |        N/A |      N/A | N/A              | KHÔNG ĐỦ    
S&P 500          | Không có nguồn đạt chuẩn     |    N/A |       0 | N/A                    |        N/A |      N/A | N/A              | KHÔNG ĐỦ    
NASDAQ 100       | Không có nguồn đạt chuẩn     |    N/A |       0 | N/A                    |        N/A |      N/A | N/A              | KHÔNG ĐỦ    
EUR/USD          | FRB_H10 (Federal Reserve Boa |   1999 |    6937 | -0.01% (-0.22% đến +0. |     0.7345 |    4.11% | Cùng ngày (Shift | KHÔNG ĐỦ    
EUR/USD (ECB)    | ECB (European Central Bank D |   1999 |    7082 | +0.02% (-0.35% đến +0. |     0.6104 |    4.98% | Shift +1d        | KHÔNG ĐỦ    
USD/JPY          | FRB_H10 (Federal Reserve Boa |   1971 |   13952 | +0.03% (-0.16% đến +0. |     0.8605 |    4.23% | Cùng ngày (Shift | KHÔNG ĐỦ    
========================================================================================================================
```

Chi tiết độ bám cho cả 3 cách căn ngày (`shift = 0, +1, -1`):

| Cặp tài sản × Nguồn | Căn ngày (Shift) | Số ngày khớp | Basis trung vị | Basis P5–P95 | max \|basis\| | Tương quan lợi suất ngày | Tracking error năm | Số ngày \|basis\| > 1% | Đánh giá |
|---|---|---|---|---|---|---|---|---|---|
| **EUR/USD × FRB_H10** | **Shift 0d** | **253** | **-0,0121%** | **-0,2183% đến +0,2735%** | **0,9999%** | **0,7345** | **4,11%** | **0** | **Tốt nhất** |
| EUR/USD × FRB_H10 | Shift +1d | 251 | +0,0184% | -0,4434% đến +0,4183% | 0,8785% | 0,3404 | 6,56% | 0 | Kém hơn |
| EUR/USD × FRB_H10 | Shift -1d | 202 | -0,0328% | -0,6073% đến +0,6430% | 1,3453% | 0,2159 | 7,98% | 5 | Kém nhất |
| EUR/USD × ECB | Shift 0d | 258 | +0,0026% | -0,3485% đến +0,4823% | 1,1223% | 0,4355 | 5,94% | 2 | Kém hơn |
| **EUR/USD × ECB** | **Shift +1d** | **256** | **+0,0217%** | **-0,3508% đến +0,3802%** | **0,7660%** | **0,6104** | **4,98%** | **0** | **Tốt nhất** |
| EUR/USD × ECB | Shift -1d | 208 | -0,0327% | -0,6559% đến +0,8074% | 1,7734% | 0,1548 | 8,29% | 5 | Kém nhất |
| **USD/JPY × FRB_H10** | **Shift 0d** | **252** | **+0,0323%** | **-0,1642% đến +0,2601%** | **1,1113%** | **0,8605** | **4,23%** | **1** | **Tốt nhất** |
| USD/JPY × FRB_H10 | Shift +1d | 250 | -0,0295% | -0,6295% đến +0,7086% | 2,4080% | 0,2494 | 9,76% | 8 | Kém hơn |
| USD/JPY × FRB_H10 | Shift -1d | 201 | +0,0861% | -0,7886% đến +0,7807% | 2,2403% | 0,2726 | 11,18% | 15 | Kém nhất |

> **Phân tích căn ngày lệch:**
> - Đối với `FRB_H10`: Cả EUR/USD và USD/JPY đều đạt tương quan cao nhất ở `Shift 0d` (cùng ngày). Mặc dù FRB chốt tỷ giá vào 12:00 trưa New York (17:00 UTC) còn BingX chốt nến 1d vào 00:00 UTC, khoảng cách 7 tiếng vẫn nằm trọn trong cùng ngày làm việc.
> - Đối với `ECB`: Tương quan cao hơn rõ rệt ở `Shift +1d` (0,6104 so với 0,4355 của Shift 0). Do tỷ giá tham chiếu ECB chốt vào 14:15 CET (13:15 UTC) tại châu Âu, biến động buổi chiều New York của ngày hôm trước thường phản ánh sang fixing ECB của ngày hôm sau.

#### Kiểm tra chéo bắt buộc bằng tính tay (3 ngày cụ thể):
Lấy trực tiếp giá `close` từ database:
1. **Ngày 2025-09-15:**
   - BingX Close: `1.17651`
   - FRB_H10 Close: `1.1772`
   - Phép tính tay: $basis = \frac{1.17651}{1.1772} - 1 = -0.000586136595... = \mathbf{-0.0586\%}$
   - Số script in ra: `-0.0586%` (Khớp tuyệt đối).
2. **Ngày 2026-01-15:**
   - BingX Close: `1.16089`
   - FRB_H10 Close: `1.1605`
   - Phép tính tay: $basis = \frac{1.16089}{1.1605} - 1 = +0.000336062042... = \mathbf{+0.0336\%}$
   - Số script in ra: `+0.0336%` (Khớp tuyệt đối).
3. **Ngày 2026-06-15:**
   - BingX Close: `1.15911`
   - FRB_H10 Close: `1.1599`
   - Phép tính tay: $basis = \frac{1.15911}{1.1599} - 1 = -0.000681093197... = \mathbf{-0.0681\%}$
   - Số script in ra: `-0.0681%` (Khớp tuyệt đối).

---

### 2.4. A4. Phân loại theo 3 tiêu chí Brief 115

| Mã tài sản | Tiêu chí 1: $\ge 10$ năm dữ liệu gốc | Tiêu chí 2: Tương quan lợi suất $\ge 0,95$ | Tiêu chí 3: \|basis\| trung vị $\le 0,5\%$ | Kết luận phân loại |
|---|---|---|---|---|
| **EUR/USD** | **ĐẠT** (27,6 năm, 6.937 ngày) | **KHÔNG ĐẠT** (max 0,7345 < 0,95) | **ĐẠT** (0,0121% $\le$ 0,5%) | **KHÔNG ĐỦ ĐỂ ĐO TIẾP** |
| **USD/JPY** | **ĐẠT** (55,6 năm, 13.952 ngày) | **KHÔNG ĐẠT** (max 0,8605 < 0,95) | **ĐẠT** (0,0323% $\le$ 0,5%) | **KHÔNG ĐỦ ĐỂ ĐO TIẾP** |

---

## 3. Output Task B — Chi phí giữ vị thế Forex Perp

Tất cả các số liệu dưới đây được lấy từ endpoint API công khai hoặc tính toán thuần toán học bởi script [scripts/measure_forex_perp_cost.py](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/measure_forex_perp_cost.py).

### 3.1. Bảng 1: Thông số hợp đồng từ API BingX
Endpoint: `GET /openApi/swap/v2/quote/contracts`  
URL tài liệu chính thức: `https://bingx-api.github.io/docs/#/swap/market-api` (Contract Information)

| Mã perp | Tên | Maker Fee | Taker Fee | Phí 1 vòng Taker (`2 × taker`) | Bước giá (Price Prec) | Bước lượng (Qty Prec) | Lượng min (Min Qty) | Giá trị min (Min USDT) |
|---|---|---|---|---|---|---|---|---|
| `NCFXEUR2USD-USDT` | EUR/USD | 0,020% | 0,050% | **0,100%** | 5 chữ số | 2 chữ số | 1,76 | 2,0 USDT |
| `NCFXUSD2JPY-USDT` | USD/JPY | 0,020% | 0,050% | **0,100%** | 3 chữ số | 2 chữ số | 2,00 | 2,0 USDT |

---

### 3.2. Bảng 2: Thống kê Funding Rate
Endpoint: `GET /openApi/swap/v2/quote/fundingRate?symbol={symbol}&limit=1000` (phân trang bằng `endTime`, niêm phong đến `2026-08-31 23:59:59 UTC`)  
URL tài liệu chính thức: `https://bingx-api.github.io/docs/#/swap/market-api` (Get Funding Rate History)

| Mã perp | Tổng số mốc | Chu kỳ funding | Mốc lệch | Mean có dấu (%/ngày) | Mean \|abs\| (%/ngày) | P5 (%/ngày) | P95 (%/ngày) |
|---|---|---|---|---|---|---|---|
| `NCFXEUR2USD-USDT` | 1.109 | **8,0h** | 0 | +0,005447% | **0,017745%** | -0,013200% | +0,030000% |
| `NCFXUSD2JPY-USDT` | 1.106 | **8,0h** | 0 | -0,002293% | **0,017956%** | -0,012000% | +0,012000% |

> **Quy ước hướng dấu của Funding Rate:**
> `fundingRate > 0` nghĩa là bên **Long trả tiền cho bên Short**.
> `fundingRate < 0` nghĩa là bên **Short trả tiền cho bên Long**.

---

### 3.3. Bảng 3: Biên độ ngày và Chi phí giữ vị thế so với biên độ ngày gốc

| Mã | Biên độ gốc trung vị (`bars_ext_daily`) | Biên độ BingX trung vị (`bars_crypto`) | ATR14 BingX (% giá) | Phí vòng / BĐ gốc | Giữ 1d / BĐ gốc | Giữ 3d / BĐ gốc | Giữ 5d / BĐ gốc | Giữ 10d / BĐ gốc |
|---|---|---|---|---|---|---|---|---|
| **EUR/USD** | **0,3103%** (`FRB_H10`) | 0,1678% | 0,4560% | **32,23%** | 37,94% | 49,38% | **60,82%** | **89,41%** |
| **USD/JPY** | **0,2982%** (`FRB_H10`) | 0,1978% | 0,5865% | **33,53%** | 39,56% | 51,60% | **63,64%** | **93,75%** |

*Ghi chú thêm cho EUR/USD so với ECB:* Nếu lấy mẫu số là biên độ gốc ECB EURUSD (0,3144%), các tỷ lệ lần lượt là: Phí vòng = 31,81%; Giữ 1d = 37,45%; Giữ 3d = 48,74%; Giữ 5d = 60,03%; Giữ 10d = 88,25%.

> **So sánh ATR14 và Biên độ ngày trung vị của BingX:**
> - `NCFXEUR2USD-USDT`: ATR14 trung vị = 0,4560%, cao gấp **2,72 lần** biên độ ngày (0,1678%).
> - `NCFXUSD2JPY-USDT`: ATR14 trung vị = 0,5865%, cao gấp **2,96 lần** biên độ ngày (0,1978%).
> **Nguyên nhân lệch quá 2 lần:**
> 1. ATR phản ánh biên độ High-Low trong phiên, trong khi lợi suất ngày chỉ đo khoảng cách Close-to-Close.
> 2. Sự hiện diện của 52 nến Chủ nhật (phiên giao dịch ngắn 2-3 tiếng trước 00:00 UTC với biến động giá rất nhỏ) đã kéo tụt giá trị trung vị của lợi suất Close-to-Close trên BingX.

---

## 4. Kiểm thử, Linter và Ba phép phá thử bắt buộc (§1.B3 Brief 116)

### 4.1. Kết quả kiểm thử Unit Test và Ruff
Lệnh chạy unit test:
```text
uv run pytest tests/test_measure_forex_perp_cost.py -v
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0 -- D:\My_Vault_Obsidian\Project\AI_auto_trading_system\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\My_Vault_Obsidian\Project\AI_auto_trading_system
configfile: pyproject.toml
plugins: anyio-4.14.2, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 8 items

tests/test_measure_forex_perp_cost.py::test_compute_funding_interval_hours PASSED [ 12%]
tests/test_measure_forex_perp_cost.py::test_convert_funding_rate_to_daily_pct_and_mutation_1 PASSED [ 25%]
tests/test_measure_forex_perp_cost.py::test_compute_funding_distribution_daily_pct PASSED [ 37%]
tests/test_measure_forex_perp_cost.py::test_compute_roundtrip_taker_fee_pct_and_mutation_2 PASSED [ 50%]
tests/test_measure_forex_perp_cost.py::test_compute_daily_amplitude_pct_and_mutation_3 PASSED [ 62%]
tests/test_measure_forex_perp_cost.py::test_compute_cost_to_amplitude_ratio PASSED [ 75%]
tests/test_measure_forex_perp_cost.py::test_compute_holding_cost_ratio PASSED [ 87%]
tests/test_measure_forex_perp_cost.py::test_compute_atr14_series_pct PASSED [100%]

============================== 8 passed in 0.14s ==============================
```

Lệnh chạy ruff linter:
```text
uv run ruff check trading tests scripts/measure_forex_perp_cost.py
All checks passed!
```

---

### 4.2. Ba phép phá thử bắt buộc (Destructive Testing)

Toàn bộ quy trình phá thử được thực hiện bằng cách sao lưu file ra thư mục scratch bên ngoài workspace repo (`C:\Users\quelam\.gemini\antigravity-cli\brain\5b76cfc8-8cc1-4571-89b8-877653ab965f\scratch\measure_forex_perp_cost.py.clean`), gây đột biến, chạy test để xác nhận **ĐỎ (FAILED)**, và khôi phục lại từ file sao lưu scratch (tuyệt đối không dùng `git checkout`, `git restore`, `git stash`).

#### Phép phá thử 1: Đổi quy đổi funding sang %/ngày từ `* (24/chu_kỳ)` thành `* chu_kỳ`
- **Mã đột biến:** Trong `convert_funding_rate_to_daily_pct`, sửa thành `return rate * interval_hours * 100.0`.
- **Output ĐỎ (FAILED):**
```text
uv run pytest tests/test_measure_forex_perp_cost.py -k "test_convert_funding_rate_to_daily_pct" -v
FAILED tests/test_measure_forex_perp_cost.py::test_convert_funding_rate_to_daily_pct_and_mutation_1 - AssertionError: assert 0.032 == 0.012
======================= 1 failed, 7 deselected in 0.38s =======================
```
- Khôi phục file từ scratch backup $\rightarrow$ Test XANH trở lại.

#### Phép phá thử 2: Đổi phí một vòng từ `2 * taker` thành `1 * taker`
- **Mã đột biến:** Trong `compute_roundtrip_taker_fee_pct`, sửa thành `return 1.0 * taker_fee_rate * 100.0`.
- **Output ĐỎ (FAILED):**
```text
uv run pytest tests/test_measure_forex_perp_cost.py -k "test_compute_roundtrip_taker_fee_pct" -v
FAILED tests/test_measure_forex_perp_cost.py::test_compute_roundtrip_taker_fee_pct_and_mutation_2 - AssertionError: assert 0.05 == 0.1
======================= 1 failed, 7 deselected in 0.26s =======================
```
- Khôi phục file từ scratch backup $\rightarrow$ Test XANH trở lại.

#### Phép phá thử 3: Đổi trung vị `|lợi suất ngày|` thành trung bình có dấu (signed mean)
- **Mã đột biến:** Trong `compute_daily_amplitude_pct`, sửa thành tính trung bình có dấu `statistics.mean(signed_returns)`.
- **Output ĐỎ (FAILED):**
```text
uv run pytest tests/test_measure_forex_perp_cost.py -k "test_compute_daily_amplitude_pct" -v
FAILED tests/test_measure_forex_perp_cost.py::test_compute_daily_amplitude_pct_and_mutation_3 - AssertionError: assert 0.0196 == 1.9804
======================= 1 failed, 7 deselected in 0.29s =======================
```
- Khôi phục file từ scratch backup $\rightarrow$ Test XANH trở lại.

---

## 5. Những điều bất thường phát hiện được (§2.5 Brief 116)

1. **Hiện tượng bất nhất quán bộ nhớ đệm (Cache Inconsistency) giữa các cụm node API của BingX:**
   Khi truy vấn lịch sử funding (`/openApi/swap/v2/quote/fundingRate`) với tham số `limit=1000&endTime=1788220799000`, nếu request được điều hướng đến một số node phụ của BingX, API chỉ trả về đúng **418 bản ghi** (tương đương khoảng 140 ngày gần nhất, lùi về `2026-04-14 16:00:00 UTC`), và gọi tiếp trang thứ 2 với `endTime < 1776182400000` sẽ trả về `data: null`. Trong khi đó, các node chính khác của BingX trả về đủ **1.000 bản ghi** và trang thứ 2 trả tiếp **109 bản ghi** (lùi trọn vẹn về ngày niêm yết `2025-08-27`). Script đã bổ sung cơ chế phát hiện số lượng trả về bất thường trên trang đầu và retry để định tuyến đến node đầy đủ, thu thập trọn vẹn 1.109 bản ghi cho EUR và 1.106 bản ghi cho JPY.
2. **Quy ước trả dữ liệu khi chạm đáy lịch sử:**
   Khi `endTime` nằm trước thời điểm niêm yết của hợp đồng, API BingX trả về `{"code": 0, "msg": "", "data": null}` (`data` là `null` trong JSON thay vì mảng rỗng `[]`).
3. **Cấu trúc nến ngày 1d của BingX cho Forex:**
   BingX không tạo nến ngày thứ Bảy (0 nến), nhưng tạo nến ngày Chủ nhật (52 nến). Do thị trường Forex mở cửa lúc chiều tối Chủ nhật (khoảng 21:00 UTC), nến ngày Chủ nhật chỉ phản ánh 2-3 giờ giao dịch với thanh khoản và biên độ rất nhỏ, dẫn đến việc trung vị lợi suất ngày của BingX thấp hơn đáng kể so với tài sản gốc.
4. **Tỷ lệ chi phí ăn mòn biên độ cực lớn:**
   Phí giao dịch và funding rate chiếm tỷ lệ áp đảo so với biên độ tự nhiên của Forex. Chỉ riêng phí vào/ra lệnh taker (0,100%) đã ngốn 32% - 34% biên độ một ngày; nếu giữ lệnh 5 ngày, chi phí ăn mòn hơn 60% biên độ một ngày; nếu giữ lệnh 10 ngày, chi phí ăn hết 90% - 94% biên độ một ngày.

---

## 6. Danh sách những gì agent KHÔNG kiểm được và lý do (§2.6 Brief 116)

1. **Không kiểm được độ trượt giá (Slippage) lịch sử:**
   API công khai của BingX không cung cấp dữ liệu sổ lệnh (Orderbook Depth) lịch sử dạng lưu trữ nén (chỉ có snapshot L2 tại thời điểm gọi qua REST). Do đó, chi phí trượt giá thực tế trong quá khứ chưa thể lượng hóa qua các endpoint này.
2. **Không kiểm được WebSocket streaming thời gian thực:**
   Trong phiên thực thi này, agent tuân thủ nguyên tắc không duy trì tiến trình daemon dài hạn và không tương tác phiên live WebSocket để tránh rủi ro treo tiến trình nền.
3. **MCP GitNexus không được đăng ký trong danh sách công cụ runtime:**
   Môi trường của agent không có sẵn các tool `gitnexus_*` qua MCP. Agent đã sử dụng trực tiếp GitNexus CLI qua terminal (`npx gitnexus status`, `npx gitnexus query --repo AI_auto_trading_system`, `npx gitnexus detect-changes --repo AI_auto_trading_system`) kết hợp lệnh `git grep` để khảo sát codebase.
4. **GitNexus Index hiện tại bị cảnh báo stale và thiếu FTS index:**
   Lệnh `npx gitnexus status` báo: `Indexed commit: e3fa18a, Current commit: fc26c04, Status: stale (re-run gitnexus analyze)`. Agent không tự ý chạy `npx gitnexus analyze --force` để tránh ghi đè tài nguyên lớn ngoài phạm vi được giao; tuy nhiên `detect-changes` vẫn xác nhận 0 symbol mã nguồn cũ nào bị ảnh hưởng.

---

Tôi không commit, không push, không đặt lệnh, không gọi endpoint có ký, không sửa `trading/`, không đọc dữ liệu từ 2026-09-01, và mọi hằng số phí/funding trong báo cáo đều có URL nguồn.


---

# PHẦN AUDIT CỦA CLAUDE — 28/09/2026

Phần trên là báo cáo của agent. Phần này là kiểm tra độc lập của Claude. **Kết luận chính của agent bị lật**, và nguyên nhân gốc nằm ở brief của Claude, không phải ở agent.

## A. Những gì tái lập được đúng

| Số liệu agent báo | Claude tái lập độc lập | Khớp? |
|---|---|---|
| Nến 1d EUR/USD = 316, không có nến thứ Bảy, có 52 nến Chủ nhật | `EXTRACT(DOW)`: dow 0 = 52, dow 6 = 0, dow 1–5 = 52–53 | Khớp |
| Tương quan EUR/USD × FRB_H10, shift 0 = 0,7345; TE 4,11%; n = 252 | SQL ghép-ngày-trước-rồi-tính-lợi-suất: 0,7345 / 4,11% / 252 | Khớp chính xác |
| Biên độ BingX EUR/USD = 0,1678% | 0,1678% trên cả 315 nến | Khớp |
| Funding USD/JPY: chu kỳ 8,0h, mean abs 0,017956%/ngày, 1106 mốc | Kéo lại từ API: 1106 mốc, 8,0h, 0,017956% | Khớp chính xác |
| Basis 3 ngày tính tay | Kiểm lại: khớp | Khớp |
| Không dùng mặc định an toàn khi thiếu trường API | Đọc code: thiếu trường thì `raise`, không `.get(k, 0)` | Đúng |

Phương pháp tính tương quan của agent (ghép ngày trước, rồi tính lợi suất trên các ngày đã khớp) là đúng hơn cách Claude thử đầu tiên (tính lợi suất trên chuỗi thô rồi mới ghép, cho 0,6711). Claude đã sai ở lần thử đầu, agent đúng.

## B. Lỗi 1 — `bingx_klines.py` cắt ngắn lịch sử, im lặng

**Đây là lỗi nghiêm trọng nhất của đợt này, và nó có từ trước đợt 116.**

`collect_symbol_klines` có dòng:

```python
if len(raw_bars) < limit:
    break
```

tức là "trang trả về ít hơn `limit` thì coi như hết lịch sử". Với mã NCFX, BingX trả **một trang ngắn ngay từ trang đầu** trong khi lịch sử vẫn còn. Claude kiểm trực tiếp:

| Mã | Số dòng trang đầu (`limit=1000`, khung 1h) |
|---|---|
| `NCFXEUR2USD-USDT` | **724** |
| `NCCOGOLD2USD-USDT` | 1000 |
| `BTC-USDT` | 1000 |

Hệ quả:
- Đợt 116 chỉ nạp **724 nến 1h** (từ 2026-07-20, 42 ngày) rồi báo như thể đó là toàn bộ lịch sử. Thực tế lịch sử 1h lùi được tới **2025-08-27**, tức ngày niêm yết.
- **Đợt 114 cũng bị**: báo cáo đợt 114 kết luận "vàng nến 1h chỉ từ 02/2026" và dùng nó để loại vàng. Claude kéo tay bằng phân trang riêng: nến 1h của vàng lùi được tới **2025-10-14**, cũng là ngày niêm yết. Kết luận đó của đợt 114 **sai**, và sai vì công cụ, không vì dữ liệu.

**Đã sửa:** bỏ dòng `len(raw_bars) < limit: break`. Vòng lặp vẫn dừng an toàn nhờ điều kiện đã có sẵn ở trên (`min_ms >= prev_min_ms`) cộng với trang rỗng. Giá phải trả là mỗi mã tốn thêm một request rỗng.

**Test mới:** `test_trang_ngan_giua_lich_su_khong_lam_dung_som` — trang đầu 724/1000 nhưng còn 276 nến cũ hơn.
**Phá thử:** trả lại dòng `break` cũ thì test đỏ với đúng thông điệp `assert 724 == 1000`, tức tái hiện đúng lỗi thật.
**Một test cũ phải sửa:** `test_phan_trang_ghep_du_khong_trung` từng ghim `calls == 2`, tức ghim chính hành vi sai. Đổi thành 3, kèm lý do.

**Nạp lại sau khi sửa:**

```
[ 1/2] NCFXEUR2USD-USDT:  6131 nến (2025-08-27 -> 2026-08-31) | 10 calls |  12.4s
[ 2/2] NCFXUSD2JPY-USDT:  6115 nến (2025-08-28 -> 2026-08-31) | 10 calls |  13.1s
```

6.131 nến thay cho 724, nhiều hơn 8,5 lần.

## C. Lỗi 2 — kết luận "KHÔNG ĐẠT" là ảo giác do lệch giờ chốt, và do brief của Claude

Brief của Claude bắt so nến **1d của BingX chốt 00:00 UTC** với **fixing H.10 chốt trưa New York**. Hai mốc cách nhau khoảng 7–8 giờ. Hai cửa sổ lợi suất 24 giờ lệch nhau `h` giờ thì tương quan tối đa chỉ khoảng `(24 − h)/24`, nên **ngưỡng 0,95 là không thể đạt bằng cấu hình đó**, bất kể BingX bám tốt đến đâu. Ngưỡng ấy do Claude đặt ra ở brief 115 và nó sai về mặt thiết kế phép đo.

Sau khi có nến 1h đầy đủ (phần B), Claude quét thử toàn bộ 24 giờ, lấy giá BingX tại từng giờ UTC rồi so với cùng chuỗi H.10:

| Cặp | Nguồn | Giờ UTC tốt nhất | n | Tương quan |
|---|---|---|---|---|
| EUR/USD | FRB_H10 | **16:00** | 248 | **0,9776** |
| EUR/USD | FRB_H10 | 15:00 | 251 | 0,9727 |
| EUR/USD | FRB_H10 | 00:00 (cách agent đo) | 252 | 0,7345 |
| USD/JPY | FRB_H10 | **16:00** | 247 | **0,9907** |
| USD/JPY | FRB_H10 | 00:00 (cách agent đo) | 252 | 0,8605 |
| EUR/USD | ECB | 11:00 | 256 | 0,9370 |

16:00 UTC đúng là trưa New York theo giờ mùa hè, tức đúng mốc chốt của H.10.

**Kết luận đúng:** so ở cùng mốc giờ, BingX **bám** cả hai cặp ở mức **0,978 và 0,991**, tức **vượt** ngưỡng 0,95. Nguồn ECB đạt 0,937, thấp hơn, vì mốc 14:15 CET không rơi đúng biên nến giờ; với việc đo, **H.10 là nguồn nên dùng**.

Ba con số cổng, đọc lại cho đúng:

| Điều kiện | EUR/USD | USD/JPY |
|---|---|---|
| ≥ 10 năm dữ liệu gốc | 27,6 năm — ĐẠT | 55,6 năm — ĐẠT |
| \|basis\| trung vị ≤ 0,5% | 0,0121% — ĐẠT | 0,0323% — ĐẠT |
| Tương quan ≥ 0,95, **đo ở cùng mốc giờ** | 0,9776 — ĐẠT | 0,9907 — ĐẠT |

Agent không làm sai. Agent chạy đúng cấu hình mà brief bắt chạy, và tự báo đầy đủ cả ba cách căn ngày. Lỗi là của brief.

## D. Lỗi 3 — mẫu số lệch cửa sổ thời gian, làm chi phí bị nhẹ đi

Brief của Claude viết: biên độ tài sản gốc tính "trên **toàn bộ** lịch sử được phép". Agent làm đúng thế. Nhưng tử số (funding) chỉ có từ 08/2025, còn mẫu số trải 27 năm với EUR/USD và 55 năm với USD/JPY. Biên độ EUR/USD giai đoạn 2025–2026 thấp hơn hẳn trung bình dài hạn:

| Chuỗi | Trung vị \|lợi suất ngày\| toàn bộ | Cùng cửa sổ BingX |
|---|---|---|
| FRB_H10 EURUSD | 0,3103% (6.936 ngày) | **0,1972%** (253 ngày) |
| FRB_H10 USDJPY | 0,2982% (13.951 ngày) | **0,2431%** (253 ngày) |

**Đã sửa** trong `measure_forex_perp_cost.py`: thêm `first_bingx_date`, thêm tham số `date_from` cho `load_ext_daily_prices`, và in thêm Bảng 4 với mẫu số cùng cửa sổ. Hai mẫu số in cạnh nhau, không thay cái nào bằng cái nào.

**Chi phí đọc lại cho đúng:**

| Mã | | Phí một vòng | Giữ 1 ngày | Giữ 5 ngày | Giữ 10 ngày |
|---|---|---|---|---|---|
| EUR/USD | mẫu số dài hạn (agent báo) | 32,23% | 37,94% | 60,82% | 89,41% |
| EUR/USD | **mẫu số cùng cửa sổ** | **50,71%** | **59,70%** | **95,70%** | **140,69%** |
| USD/JPY | mẫu số dài hạn (agent báo) | 33,53% | 38,98% | 60,78% | 88,03% |
| USD/JPY | **mẫu số cùng cửa sổ** | **41,14%** | **47,82%** | **74,56%** | **107,99%** |

Đây là con số nặng nhất của cả đợt: với EUR/USD, chỉ riêng phí vào-ra đã ăn **quá nửa** biên độ một ngày, và giữ 10 ngày thì chi phí **vượt** biên độ một ngày.

## E. Lỗi 4 — hai mặc định an toàn giả trong `compute_atr14_series_pct`

```python
if len(bars) < 15:
    return {"median_atr14_pct": 0.0, "mean_atr14_pct": 0.0}
...
    if c > 0:
        atr_pcts.append((atr / c) * 100.0)
if not atr_pcts:
    return {"median_atr14_pct": 0.0, "mean_atr14_pct": 0.0}
```

Trả `0.0` khi thiếu nến là biến "không đo được" thành "không biến động", đúng lớp lỗi đã hai lần phá cổng go-live của dự án này. Và `if c > 0` bỏ qua nến bẩn im lặng.

**Đã sửa:** cả ba nhánh `raise ValueError`.

## F. Test ATR của agent bị mù — phá thử chứng minh

Test cũ dùng 15 nến **giống hệt nhau** (High 101, Low 99, Close 100), nên TR nào cũng bằng 2,0 và **cửa sổ trung bình là bao nhiêu cũng ra 2,0%**.

Claude phá thử: đổi cửa sổ ATR từ 14 xuống 7.

```
uv run pytest tests/test_measure_forex_perp_cost.py::test_compute_atr14_series_pct -q
.                                                    [100%]
1 passed in 0.19s
```

Test **vẫn xanh**. Tức phép phá thử thứ tư này lẽ ra phải có trong brief mà Claude không yêu cầu, và test của agent không đủ chặt.

**Đã siết:** chuỗi nến mới không đối xứng — 12 nến TR = 1,0 rồi 2 nến TR = 8,0, tổng 28,0, ATR14 = 2,0000%. Với cửa sổ 7 thì trung vị thành 1,0% và trung bình 1,375%. Phá thử lại:

```
E       assert 1.0 ± 1.0e-06 == 2.0
FAILED tests/test_measure_forex_perp_cost.py::test_compute_atr14_series_pct
```

Thêm hai test cho nhánh `raise`: thiếu nến, và nến bẩn.

## G. Điều Claude KHÔNG tái lập được

- **Funding EUR/USD:** agent báo 1.109 mốc lùi tới ngày niêm yết. Claude kéo lại chỉ nhận **418 mốc** (lùi tới 2026-04-14), mean abs 0,016309%/ngày so với 0,017745% của agent. Lần chạy lại script sau khi sửa lại ra 1.109 mốc cho EUR/USD nhưng **1.091** mốc cho USD/JPY (agent: 1.106). Tức lịch sử funding **không ổn định giữa các lần gọi** — khớp với hiện tượng bất nhất giữa các node mà chính agent đã báo. Chênh lệch nhỏ (0,0163–0,0180%/ngày) nên không đổi kết luận, nhưng **không được coi con số funding là chốt**; lần đo nào cũng phải in lại số mốc.
- **Hai test tỷ lệ chi phí** (`ratio`, `holding_cost`) dựng `expected` bằng cách viết lại đúng công thức trong thân test. Không phải tautology, vẫn bắt được đột biến, nhưng yếu về kiểu: nên ghim số literal. Chưa sửa.
- **Độ trượt giá** và **sổ lệnh lịch sử**: agent nói không có, Claude không kiểm lại.

## H. Việc còn lại

1. **Nạp lại toàn bộ nến 1h của đợt 114** bằng loader đã sửa, rồi viết lại kết luận đợt 114. Riêng vàng có thể từ "1h chỉ từ 02/2026" thành gần một năm đầy đủ.
2. **Viết phép đo bám theo mốc giờ** thành script có test, thay cho đoạn SQL rời của Claude ở phần C.
3. Ghim số literal cho hai test tỷ lệ chi phí ở phần G.

**Vẫn chưa đo chiến lược nào.** Hai cổng của đợt này: cổng bám **đạt** khi đo đúng mốc giờ; cổng chi phí **rất xấu** với EUR/USD.
