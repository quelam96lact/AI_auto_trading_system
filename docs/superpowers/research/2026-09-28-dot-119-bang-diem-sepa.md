# Báo Cáo Nghiên Cứu Đợt 119: Bảng Điểm SEPA (Minervini Trend Template) và Xếp Hạng RS

- **Ngày thực hiện:** 2026-09-28
- **Kế hoạch thực hiện:** `docs/superpowers/plans/2026-09-28-brief-dot-119-bang-diem-sepa-hien-thi.md`
- **Mã nguồn thực thi:** `scripts/score_sepa_daily.py`
- **Unit test suite:** `tests/test_score_sepa_daily.py`
- **Thư mục output độc lập:** `docs/superpowers/research/dot-119-output/`
  - `docs/superpowers/research/dot-119-output/bfc_scorecard_20260925.txt`
  - `docs/superpowers/research/dot-119-output/full_universe_scorecard_20260925.txt`

---

## 1. Kết Luận Hai Dòng

1. **Bảng điểm BFC phiên 25/09/2026:** Khớp hoàn toàn 100% với các con số Claude đã tính tay tại §2.1 của Brief (Giá đóng: 48.350, MA50: 48.071,2, MA150: 53.686,7, MA200: 51.058,5, % trên đáy 252 nến: **+29,9%** < 30% -> không đạt c6, % cách đỉnh 252 nến: **33,6%** > 25% -> không đạt c7, điểm SEPA: **3/7** gồm c2, c3, c5 đạt, RS_rank: **72/99** đạt ngưỡng ≥ 70).
2. **Độ phủ xếp hạng RS:** Tiêu chí Sức mạnh giá tương đối (RS) chạy được trên **167 mã cổ phiếu** (đủ điều kiện ≥ 253 nến sạch và `is_active = true`), 7 mã bị loại do thiếu lịch sử dữ liệu (< 252 nến sạch) và được gán ký hiệu `–` (không bịa hạng 50 hay 0).

---

## 2. Output Nguyên Văn Các Bước Thực Hiện

### 2.1. Bước 1: Bảng điểm chi tiết cho mã BFC (phiên 25/09/2026)
Lệnh chạy: `.venv\Scripts\python.exe scripts/score_sepa_daily.py --symbol BFC --as-of 2026-09-25 --output docs/superpowers/research/dot-119-output/bfc_scorecard_20260925.txt`
Exit code: **0**

```text
========================================================================================
CẢNH BÁO NIÊM PHONG (SEALED HOLDOUT NOTICE):
Dữ liệu đang được đọc sau mốc niêm phong 2023-01-01 (giờ VN).
Bảng điểm này CHỈ PHỤC VỤ MÔ TẢ TRẠNG THÁI KỸ THUẬT HIỆN TẠI (Descriptive Scorecard).
TUYỆT ĐỐI KHÔNG dùng cho bất kỳ phép đo hiệu năng, kiểm định lợi thế hay dự báo lợi suất nào.
========================================================================================

BẢNG ĐIỂM KỸ THUẬT SEPA (MINERVINI TREND TEMPLATE) — MÃ: BFC
Ngày đánh giá: 2026-09-25 (Giờ VN) | Tổng số nến sạch: 2677
Giá đóng cửa: 48,350.0 VND | Điểm xu hướng SEPA: 3/7

#   | Tiêu chí                            | Giá trị kỹ thuật                           | Trạng thái
-----------------------------------------------------------------------------------------------
1   | Giá trên MA150 và MA200             | P=48,350.0, MA150=53,686.7, MA200=51,058.5 | Không đạt
2   | MA150 trên MA200                    | MA150=53,686.7 > MA200=51,058.5            | ĐẠT
3   | MA200 hướng lên ≥ 1 tháng           | MA200=51,058.5 vs MA200_21d=50,436.5       | ĐẠT
4   | MA50 trên cả MA150 và MA200         | MA50=48,071.2 > MA150=53,686.7, MA200=51,058.5 | Không đạt
5   | Giá trên MA50                       | P=48,350.0 > MA50=48,071.2                 | ĐẠT
6   | Giá ≥ 30% trên đáy 52 tuần          | +29.9% trên đáy (Đáy 252=37,223.9)         | Không đạt
7   | Giá trong 25% của đỉnh 52 tuần      | 33.6% cách đỉnh (Đỉnh 252=72,766.4)        | Không đạt
8   | Sức mạnh giá RS ≥ 70 (Thang 1-99)       | RS_rank = 72/99 (Vũ trụ 167 mã)            | ĐẠT
-----------------------------------------------------------------------------------------------
KẾT QUẢ TỔNG HỢP: Điểm SEPA = 3/7 | Tiêu chí RS ≥ 70: ĐẠT

* Lưu ý: RS_rank được tính xấp xỉ theo trọng số 0.4/0.2/0.2/0.2 trên vũ trụ cổ phiếu đủ điều kiện,
  KHÔNG PHẢI là chỉ số bản quyền IBD RS Rating. Bảng điểm mang tính chất mô tả thuần túy kỹ thuật.
```

---

### 2.2. Bước 2: Bảng điểm toàn bộ vũ trụ đủ điều kiện tại phiên 25/09/2026
Lệnh chạy: `.venv\Scripts\python.exe scripts/score_sepa_daily.py --as-of 2026-09-25 --output docs/superpowers/research/dot-119-output/full_universe_scorecard_20260925.txt`
Exit code: **0**
File lưu: `docs/superpowers/research/dot-119-output/full_universe_scorecard_20260925.txt`

- **Số mã đủ điều kiện xu hướng SEPA (≥ 252 nến sạch):** 167 mã
- **Số mã đủ điều kiện xếp hạng RS (≥ 253 nến sạch):** 167 mã
- **Số mã bị loại khỏi vũ trụ đánh giá:** 7 mã
  - `CLI`: Thiếu lịch sử (100 < 252 nến sạch)
  - `DMX`: Thiếu lịch sử (34 < 252 nến sạch)
  - `GEL`: Thiếu lịch sử (155 < 252 nến sạch)
  - `LPS`: Thiếu lịch sử (26 < 252 nến sạch)
  - `TCX`: Thiếu lịch sử (231 < 252 nến sạch)
  - `VCK`: Thiếu lịch sử (191 < 252 nến sạch)
  - `VPX`: Thiếu lịch sử (194 < 252 nến sạch)

*Trích đoạn top các mã đạt điểm SEPA 7/7:*

```text
Mã     | Điểm  | c1 | c2 | c3 | c4 | c5 | c6 | c7 | % trên đáy  | % cách đỉnh  | RS_rank  | Đạt RS? | Giá đóng 
---------------------------------------------------------------------------------------------------------------
PET    | 7/7   | 1  | 1  | 1  | 1  | 1  | 1  | 1  |     +152.3% |         0.3% |    99/99 | ĐẠT     |    48,000
HII    | 7/7   | 1  | 1  | 1  | 1  | 1  | 1  | 1  |     +146.9% |        10.6% |    99/99 | ĐẠT     |    10,550
VIC    | 7/7   | 1  | 1  | 1  | 1  | 1  | 1  | 1  |     +222.4% |        12.5% |    98/99 | ĐẠT     |   232,000
HHP    | 7/7   | 1  | 1  | 1  | 1  | 1  | 1  | 1  |     +125.3% |         0.6% |    97/99 | ĐẠT     |    17,700
ABB    | 7/7   | 1  | 1  | 1  | 1  | 1  | 1  | 1  |      +85.0% |         7.4% |    95/99 | ĐẠT     |    17,500
SSB    | 7/7   | 1  | 1  | 1  | 1  | 1  | 1  | 1  |      +47.0% |        21.6% |    94/99 | ĐẠT     |    19,450
PVP    | 7/7   | 1  | 1  | 1  | 1  | 1  | 1  | 1  |      +51.2% |         1.0% |    94/99 | ĐẠT     |    20,500
STB    | 7/7   | 1  | 1  | 1  | 1  | 1  | 1  | 1  |      +66.5% |         3.2% |    93/99 | ĐẠT     |    76,500
PHP    | 7/7   | 1  | 1  | 1  | 1  | 1  | 1  | 1  |      +55.8% |        11.5% |    92/99 | ĐẠT     |    43,700
MSB    | 7/7   | 1  | 1  | 1  | 1  | 1  | 1  | 1  |      +56.1% |         3.1% |    91/99 | ĐẠT     |    14,050
DHC    | 7/7   | 1  | 1  | 1  | 1  | 1  | 1  | 1  |      +44.9% |         0.6% |    90/99 | ĐẠT     |    39,000
DRI    | 7/7   | 1  | 1  | 1  | 1  | 1  | 1  | 1  |      +55.7% |        10.1% |    87/99 | ĐẠT     |    15,100
QNS    | 7/7   | 1  | 1  | 1  | 1  | 1  | 1  | 1  |      +36.7% |         1.0% |    86/99 | ĐẠT     |    49,800
GMD    | 7/7   | 1  | 1  | 1  | 1  | 1  | 1  | 1  |      +40.0% |        11.0% |    84/99 | ĐẠT     |    77,400
```

---

### 2.3. Bước 3: Kiểm chéo bằng tay qua truy vấn SQL thuần (3 mã: HPG, FPT, VNM)

Truy vấn SQL trích xuất trực tiếp từ cơ sở dữ liệu:
```sql
WITH clean AS (
    SELECT ts, open, high, low, close, volume,
           ROW_NUMBER() OVER (ORDER BY ts DESC) as rn
    FROM bars_daily
    WHERE symbol = :symbol 
      AND ts <= '2026-09-24 17:00:00+00'
      AND open > 0 AND high > 0 AND low > 0 AND close > 0
)
SELECT 
    (SELECT close FROM clean WHERE rn = 1) as p_close,
    (SELECT AVG(close) FROM clean WHERE rn <= 50) as ma50,
    (SELECT AVG(close) FROM clean WHERE rn <= 150) as ma150,
    (SELECT AVG(close) FROM clean WHERE rn <= 200) as ma200,
    (SELECT AVG(close) FROM clean WHERE rn >= 22 AND rn <= 221) as ma200_prev21,
    (SELECT MIN(low) FROM clean WHERE rn <= 252) as low252,
    (SELECT MAX(high) FROM clean WHERE rn <= 252) as high252,
    (SELECT close FROM clean WHERE rn = 64) as p63,
    (SELECT close FROM clean WHERE rn = 127) as p126,
    (SELECT close FROM clean WHERE rn = 190) as p189,
    (SELECT close FROM clean WHERE rn = 253) as p252;
```

#### Phép 1: Mã HPG
- **Số liệu SQL:** Close = 20.650, MA50 = 21.510,00, MA150 = 23.242,01, MA200 = 23.407,71, MA200_prev21 = 23.669,10, Low252 = 20.100, High252 = 26.558,90.
- **Tính tay từng tiêu chí:**
  - c1 (Close > MA150 & MA200): 20.650 < 23.242 và 23.408 -> **0 (Không đạt)**
  - c2 (MA150 > MA200): 23.242 < 23.408 -> **0 (Không đạt)**
  - c3 (MA200 > MA200_prev21): 23.408 < 23.669 -> **0 (Không đạt)**
  - c4 (MA50 > MA150 & MA200): 21.510 < 23.242 -> **0 (Không đạt)**
  - c5 (Close > MA50): 20.650 < 21.510 -> **0 (Không đạt)**
  - c6 (% trên đáy ≥ 30%): (20.650 / 20.100 - 1) = +2,74% < 30% -> **0 (Không đạt)**
  - c7 (% cách đỉnh ≤ 25%): (1 - 20.650 / 26.558,90) = 22,25% ≤ 25% (hoặc Close ≥ 0.75 * 26558.9 = 19919.2) -> **1 (ĐẠT)**
- **Điểm tính tay:** **1/7** | % trên đáy: **+2,7%**, % cách đỉnh: **22,2%**.
- **So với output script:** `HPG | 1/7 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | +2.7% | 22.2% | 39/99 | K.Đạt | 20,650` -> **KHỚP HOÀN TOÀN**.

#### Phép 2: Mã FPT
- **Số liệu SQL:** Close = 64.700, MA50 = 68.704,61, MA150 = 72.976,74, MA200 = 78.961,99, MA200_prev21 = 81.853,99, Low252 = 61.500, High252 = 107.221,68.
- **Tính tay từng tiêu chí:**
  - c1: 64.700 < 72.977 -> **0 (Không đạt)**
  - c2: 72.977 < 78.962 -> **0 (Không đạt)**
  - c3: 78.962 < 81.854 -> **0 (Không đạt)**
  - c4: 68.705 < 72.977 -> **0 (Không đạt)**
  - c5: 64.700 < 68.705 -> **0 (Không đạt)**
  - c6: (64.700 / 61.500 - 1) = +5,20% < 30% -> **0 (Không đạt)**
  - c7: (1 - 64.700 / 107.221,68) = 39,66% > 25% -> **0 (Không đạt)**
- **Điểm tính tay:** **0/7** | % trên đáy: **+5,2%**, % cách đỉnh: **39,7%**.
- **So với output script:** `FPT | 0/7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | +5.2% | 39.7% | 30/99 | K.Đạt | 64,700` -> **KHỚP HOÀN TOÀN**.

#### Phép 3: Mã VNM
- **Số liệu SQL:** Close = 59.800, MA50 = 60.616,00, MA150 = 59.419,91, MA200 = 60.458,61, MA200_prev21 = 60.250,37, Low252 = 53.256,50, High252 = 73.106,65.
- **Tính tay từng tiêu chí:**
  - c1: 59.800 > 59.420 nhưng 59.800 < 60.459 -> **0 (Không đạt)**
  - c2: 59.420 < 60.459 -> **0 (Không đạt)**
  - c3: 60.458,61 > 60.250,37 -> **1 (ĐẠT)**
  - c4: 60.616,00 > 59.419,91 và 60.458,61 -> **1 (ĐẠT)**
  - c5: 59.800 < 60.616 -> **0 (Không đạt)**
  - c6: (59.800 / 53.256,50 - 1) = +12,29% < 30% -> **0 (Không đạt)**
  - c7: (1 - 59.800 / 73.106,65) = 18,20% ≤ 25% -> **1 (ĐẠT)**
- **Điểm tính tay:** **3/7** (c3, c4, c7 đạt) | % trên đáy: **+12,3%**, % cách đỉnh: **18,2%**.
- **So với output script:** `VNM | 3/7 | 0 | 0 | 1 | 1 | 0 | 0 | 1 | +12.3% | 18.2% | 70/99 | ĐẠT | 59,800` -> **KHỚP HOÀN TOÀN**.

---

## 3. Output Pytest, Ruff và Bằng Chứng 4 Phép Phá Thử (Mutations)

### 3.1. Kết quả kiểm thử & linter sạch
1. `uv run pytest tests/test_score_sepa_daily.py -v`: **6 passed in 0.18s** (Exit code: 0).
2. `uv run ruff check trading tests scripts/score_sepa_daily.py`: **All checks passed!** (Exit code: 0).
3. `uv run pytest -m "not integration" -q`: **1233 passed, 137 deselected in 32.04s** (Exit code: 0; 1227 test cũ + 6 test mới = 1233 passed).

### 3.2. Bằng chứng 4 phép phá thử bắt buộc (§6.4)

| Phép phá thử | Đột biến áp vào code | Test tương ứng | Kết quả đột biến (ĐỎ) | Kết quả khôi phục (XANH) |
|---|---|---|---|---|
| **1. Múi giờ VN vs UTC** | Dùng `b.ts.date()` thay cho `bar_date(b)` | `test_bar_date_vs_ts_date_and_mutation_1` | `FAILED: assert 2026-09-24 == 2026-09-25` | `PASSED` |
| **2. Trọng số RS** | Đổi trọng số thành 0.25 đều: `0.25 * (...)` | `test_rs_raw_weights_and_mutation_2` | `FAILED: assert 0.8125 == 0.70` | `PASSED` |
| **3. Mã thiếu nến gán 50** | `if rs_rank is None: rs_rank = 50` | `test_insufficient_bars_rs_and_mutation_3` | `FAILED: assert '\| –' in report_252` | `PASSED` |
| **4. Đổi công thức cách đỉnh** | `pct_below_high = (high252 / close - 1) * 100` | `test_boundary_percentages_and_mutation_4` | `FAILED: assert 25.0 == 20.0` | `PASSED` |

- **Bằng chứng code Đột biến 1:**
  ```python
  # Trong tests/test_score_sepa_daily.py:
  assert bar.ts.date() == date(2026, 9, 25)
  # Lỗi: AssertionError: assert datetime.date(2026, 9, 24) == datetime.date(2026, 9, 25)
  ```
- **Bằng chứng code Đột biến 2:**
  ```python
  # Trong scripts/score_sepa_daily.py:
  return 0.25 * (p / p63 - 1) + 0.25 * (p / p126 - 1) + 0.25 * (p / p189 - 1) + 0.25 * (p / p252 - 1)
  # Lỗi: AssertionError: assert 0.8125 == 0.70
  ```
- **Bằng chứng code Đột biến 3:**
  ```python
  # Trong scripts/score_sepa_daily.py:
  if rs_rank is None:
      rs_rank = 50
  # Lỗi: AssertionError: assert '| –' in report_252
  ```
- **Bằng chứng code Đột biến 4:**
  ```python
  # Trong scripts/score_sepa_daily.py:
  pct_below_high = (high252 / close - 1.0) * 100.0
  # Lỗi: AssertionError: assert 25.0 == 20.0
  ```

Sau mỗi phép phá thử, code được khôi phục nguyên trạng từ bản sao lưu sạch trong `scratch/` (không sử dụng `git checkout`, `git restore`, `git stash`).

---

## 4. Báo Cáo GitNexus Blast Radius & Detect Changes

### 4.1. GitNexus Impact Analysis trước khi import (Brief §8)
- `npx gitnexus impact -r AI_auto_trading_system -d upstream --include-tests trend_conditions`
  - Target: `Function:scripts/screen_vcp_daily.py:trend_conditions`
  - Risk: **MEDIUM** (Impacted count: 18, Direct: 9, Affected processes: 2: `main`, `compact_control_series`).
- `npx gitnexus impact -r AI_auto_trading_system -d upstream --include-tests "Function:scripts/screen_vcp_daily.py:bar_date"`
  - Target: `Function:scripts/screen_vcp_daily.py:bar_date`
  - Risk: **MEDIUM** (Impacted count: 25, Direct: 8, Affected modules: Scripts: 16, Tests: 9).
- `npx gitnexus impact -r AI_auto_trading_system -d upstream --include-tests "Function:scripts/screen_vcp_daily.py:rolling_mean"`
  - Target: `Function:scripts/screen_vcp_daily.py:rolling_mean`
  - Risk: **LOW** (Impacted count: 20, Direct: 4, Affected modules: Scripts: 11, Tests: 9).

Tuân thủ nghiêm ngặt quy định: Không chỉnh sửa bất kỳ dòng nào trong `scripts/screen_vcp_daily.py`, chỉ import thuần túy.

### 4.2. GitNexus Detect Changes
Lệnh: `npx gitnexus detect-changes --repo AI_auto_trading_system` (Exit code: 0)
- Changes: 2 files modified (`AGENTS.md`, `CLAUDE.md` từ phiên trước), các file mới chưa track nằm ngoài nguy cơ phá vỡ execution flow.
- Affected processes: 0. Risk level: LOW.

---

## 5. Những Điều Bất Thường Phát Hiện Được

1. **Hiệu năng truy vấn PostgreSQL trên bảng phân vùng `bars_daily`:**
   Bảng `bars_daily` được phân vùng (partitioned) thành 560 bảng con theo mã cổ phiếu (`symbol`). Nếu thực hiện truy vấn `SELECT ... FROM bars_daily b JOIN symbol_universe u ON b.symbol = u.symbol WHERE u.is_active = true`, bộ tối ưu hóa PostgreSQL không thể thực hiện cắt tỉa phân vùng tĩnh (static partition pruning) mà thực hiện quét tuần tự toàn bộ 560 bảng phân vùng của cả những mã đã ngừng giao dịch, dẫn đến thời gian phản hồi kéo dài.
   Để khắc phục triệt để mà không thay đổi cấu trúc bảng, `load_universe_and_bars` đã tách thành 2 bước tối ưu:
   - Bước 1: `SELECT symbol FROM symbol_universe WHERE is_active = true` (0.01s, lấy 174 mã active).
   - Bước 2: `SELECT ... FROM bars_daily WHERE symbol = ANY(%s)` (5.89s, PostgreSQL cắt tỉa ngay lập tức 386 phân vùng không hoạt động).
   Tổng thời gian tải toàn bộ 394.507 nến của 174 mã chỉ mất ~6 giây.
2. **Ký hiệu RS cho mã thiếu dữ liệu:**
   7 mã thiếu dữ liệu lịch sử (< 252 nến) là `CLI`, `DMX`, `GEL`, `LPS`, `TCX`, `VCK`, `VPX`. Đúng theo yêu cầu thiết kế, các mã này không tham gia vào phân vị RS và hiển thị ký tự gạch ngang `–`.

---

## 6. Danh Sách Những Gì Agent KHÔNG Kiểm Được và Lý Do

1. **Dữ liệu phiên giao dịch hôm nay (28/09/2026):**
   - *Lý do:* Cơ sở dữ liệu `bars_daily` chỉ mới đồng bộ đến hết phiên Thứ Sáu ngày 25/09/2026 (`ts = 2026-09-24 17:00:00+00`). Chưa có dữ liệu nến ngày 28/09/2026 trong DB để tái lập chính xác bảng điểm chụp màn hình thời gian thực mà chủ dự án đã gửi trong phiên 28/09.
2. **Công thức tính RS Rating độc quyền của IBD:**
   - *Lý do:* Investors Business Daily (IBD) bảo mật công thức trọng số độc quyền và sử dụng toàn bộ cơ sở dữ liệu chứng khoán Mỹ (>7.000 mã) để xếp hạng phân vị từ 1 đến 99. Công thức triển khai ở đây là xấp xỉ công khai theo trọng số 4 quý (0.4/0.2/0.2/0.2) trên vũ trụ 167 mã cổ phiếu thanh khoản tại Việt Nam.

---

Tôi không commit, không push, không đặt lệnh, không sửa `screen_vcp_daily.py` hay `trading/`, không tính bất kỳ số hiệu năng nào, không gán hạng RS cho mã thiếu dữ liệu, và mọi output đều có file kèm đường dẫn.

---

# PHẦN AUDIT CỦA CLAUDE — 28/09/2026

## A.1. Kết luận audit

**Đợt này bằng chứng thật từ đầu đến cuối.** Mọi con số Claude kiểm được đều khớp chính xác. Đây là điểm khác hẳn đợt 117 và 118, nơi bằng chứng dán vào báo cáo có phần bịa.

| Hạng mục | Kết quả audit |
|---|---|
| Bảng điểm BFC phiên 25/09 | **ĐÚNG.** Claude chạy lại, khớp **từng chữ số**: 3/7, MA50 48.071,2, MA150 53.686,7, MA200 51.058,5, MA200_21d 50.436,5, đáy 252 = 37.223,9, đỉnh 252 = 72.766,4, RS 72/99 |
| Kiểm chéo tay mã VNM | **ĐÚNG.** Claude tự chạy SQL: 59.800 / 60.616,00 / 59.419,91 / 60.458,61 / 60.250,37 / 53.256,5 / 73.106,65 / +12,3% / 18,2% — khớp cả chín con số, và suy luận từng tiêu chí đúng |
| Vũ trụ | **ĐÚNG.** 174 mã `is_active`, 167 đủ điều kiện, 7 bị loại — Claude đếm lại ra đúng **cùng danh sách và cùng số nến**: CLI(100), DMX(34), GEL(155), LPS(26), TCX(231), VCK(191), VPX(194) |
| Giữ niêm phong | **ĐÚNG.** `grep` cả file: không có `forward_return`, `pnl`, `win_rate`, `sharpe`, `drawdown`, `profit`. Banner cảnh báo có in |
| Không sửa `screen_vcp_daily.py` | **ĐÚNG.** `git status` chỉ có file mới |
| Xử lý múi giờ | **ĐÚNG, và mạnh hơn phép phá thử.** Claude grep toàn file: dùng `bar_date()` ở cả 7 chỗ, **không có** `ts.date()` hay `ts::date` ở đâu. Tức phép phá thử 1 không che một lỗi thật nào |
| RS đúng cách gọi tên | **ĐÚNG.** Có ghi rõ là xấp xỉ, không phải IBD RS Rating, và in số mã trong vũ trụ |
| Mã thiếu nến | **ĐÚNG.** In `–`, không gán 0 hay 50 |
| Suite, ruff | **ĐÚNG.** 1.233 pass (1.227 + 6), ruff sạch |

## A.2. Vì sao BFC ra 3/7 chứ không phải 4/7 như bảng chủ dự án

Không phải lệch. Đối chiếu từng dòng:

| Tiêu chí | Bảng chủ dự án (trong phiên 28/09) | Ta (đóng phiên 25/09) |
|---|---|---|
| c1 Giá trên MA150 và MA200 | ✗ | ✗ |
| c2 MA150 trên MA200 | ✓ | ✓ |
| c3 MA200 hướng lên | ✓ | ✓ |
| c4 MA50 trên MA150 và MA200 | ✗ | ✗ |
| c5 Giá trên MA50 | ✓ | ✓ |
| **c6 Giá ≥ 30% trên đáy 52 tuần** | **✓ (35,7%)** | **✗ (29,9%)** |
| c7 Giá trong 25% của đỉnh | ✗ | ✗ |
| **Tổng** | **4/7** | **3/7** |

Khác đúng **một dòng duy nhất**, và đúng dòng mà giá cao hơn sẽ đổi trạng thái. Giá của bảng chủ dự án ≈ 50.500 (trong phiên 28/09), giá đóng 25/09 là 48.350. Ngưỡng c6 nằm ở 30%, còn ta ở 29,9% — **thiếu 0,1 điểm phần trăm**. Đáy 252 nến script tính là 37.223,9, khớp con số 37.221 mà Claude suy ngược từ bảng chủ dự án trước khi giao brief.

Nói cách khác: cùng một công thức, chỉ khác một phiên. Không có gì sai ở cả hai bên.

## A.3. Lỗi 1 Claude tìm ra — bảng in ra bất đẳng thức SAI

Các dòng 1, 2, 4, 5 ghim cứng ký tự `>` trong chuỗi hiển thị. Nên khi điều kiện **không đạt**, bảng vẫn in một bất đẳng thức sai. Nguyên văn output cũ của BFC:

```
4   | MA50 trên cả MA150 và MA200 | MA50=48,071.2 > MA150=53,686.7, MA200=51,058.5 | Không đạt
```

`48.071,2 > 53.686,7` là **sai**. Cột trạng thái ghi "Không đạt" nên người đọc kỹ sẽ không bị lừa, nhưng công cụ này chỉ có **một việc duy nhất là phát biểu sự thật về trạng thái kỹ thuật**, và nó đang phát biểu sai.

**Đã sửa:** thêm hàm `op(a, b)` trả về `>`, `<` hoặc `=` theo số liệu thật, áp cho cả năm dòng có so sánh. Output sau khi sửa:

```
1   | Giá trên MA150 và MA200     | P=48,350.0 < MA150=53,686.7, < MA200=51,058.5   | Không đạt
4   | MA50 trên cả MA150 và MA200 | MA50=48,071.2 < MA150=53,686.7, < MA200=51,058.5 | Không đạt
5   | Giá trên MA50               | P=48,350.0 > MA50=48,071.2                      | ĐẠT
```

**Test mới** dùng chuỗi giá phẳng (mọi so sánh bằng nhau) nên bắt được cả trường hợp `=`. **Phá thử:** ghim lại `>` thì test đỏ.

## A.4. Lỗi 2 — và đây là lỗ trong brief của Claude, không phải lỗi của agent

Brief 119 **không** yêu cầu loại các mã đã biết là có dữ liệu điều chỉnh giá không tin cậy. Claude bỏ sót, dù dự án đã có sẵn cơ chế: `scripts/check_price_adjustment.py --emit-exclusions` và file `exclusions.txt` ở gốc repo với **246 mã** (mã còn split chưa điều chỉnh, cộng mã có ≥5% nến `OHLC ≤ 0`).

Claude đối chiếu: **4 trong 165 mã của bảng điểm nằm trong danh sách đó** — `PVP`, `KSV`, `VPL`, `HHV`. Và tệ nhất:

> **`PVP` đang đứng trong nhóm 7/7 mà báo cáo nêu bật, với RS 94/99.**

Với những mã này, MA150, MA200 và biên độ 52 tuần **đều có thể sai**, vì một split chưa điều chỉnh làm lệch cả đường trung bình lẫn đáy/đỉnh. In chúng như một dòng bình thường nghĩa là người đọc sẽ hành động trên số sai — đúng thứ mà một bảng điểm để xem hằng ngày dễ gây ra nhất.

**Đã sửa:**
- thêm `load_untrusted_symbols()` đọc `exclusions.txt`;
- mã trong danh sách bị đánh dấu `(!)` ở cột Mã, ví dụ `PVP(!)`;
- in một dòng `[CHU Y]` liệt kê chúng kèm lý do;
- **không có file thì NÓI RA**, không im lặng coi như mọi mã đều sạch.

Output sau khi sửa:

```
[CHU Y] 4/167 ma co du lieu dieu chinh gia KHONG tin cay, danh dau (!) o cot Ma. ...: HHV, KSV, PVP, VPL
PVP(!) | 7/7   | 1  | 1  | 1  | 1  | 1  | 1  | 1  |  +51.2% |   1.0% | 94/99 | ĐẠT | 20,500
```

**Hai test mới** (đọc danh sách, và đánh dấu trong bảng), **phá thử** bỏ đánh dấu thì test đỏ.

**Việc Claude CỐ Ý chưa làm:** không loại các mã đó khỏi **vũ trụ xếp hạng RS**. Loại chúng sẽ đổi hạng của cả 167 mã, và đó là một quyết định thiết kế cần khai trước chứ không nên lặng lẽ đổi số lúc audit. Ghi lại thành câu hỏi mở cho đợt sau.

## A.5. Điều Claude chưa kiểm

- **Phép phá thử 2, 3, 4** (trọng số RS, gán 50 cho mã thiếu nến, đổi công thức cách đỉnh): Claude **chưa tự tái lập**. Riêng phép 1 thì Claude kiểm bằng cách mạnh hơn — grep toàn file xác nhận không tồn tại `ts.date()`/`ts::date` ở đâu.
- **Hạng RS của 165 mã còn lại:** chỉ xác minh BFC ra 72/99 tái lập được. Phép xếp hạng phân vị trên toàn vũ trụ chưa tính lại độc lập.
- **Nhóm 7/7** (PET, HII, VIC, HHP, ABB, SSB, PVP, STB, PHP, MSB, DHC, DRI, QNS, GMD): chỉ kiểm PVP thuộc danh sách không tin cậy. **Chưa kiểm mức giá nào cả** — nhắc lại một điều đã ghi trong dự án: `bars_daily` mang hệ số điều chỉnh riêng từng mã, **không so giá tuyệt đối giữa các mã**, nên "VIC 232.000" không nói được điều gì mà không tra thêm.
- **Nhận định §5 về cắt tỉa phân vùng PostgreSQL:** hợp lý về mặt kỹ thuật, Claude không đo lại thời gian.

## A.6. Điều phải nhắc lại về ý nghĩa của bảng điểm này

Bảy tiêu chí này chính là bộ lọc xu hướng trong phép sàng lọc VCP **đã đo và đã âm** ở đợt 99 (commit `19432af`: "thua rõ đối chứng cùng ngày, phép đo âm thứ bảy"). Bảng điểm là **mô tả trạng thái kỹ thuật**, không phải bằng chứng về lợi thế, và điểm 7/7 không có nghĩa là nên mua.

Câu "điểm SEPA cao có dự báo được lợi suất không" vẫn là một phép đo riêng, phải tiền đăng ký, phải chỉ dùng dữ liệu trước 2023 để giữ holdout, và phải có đối chứng cùng ngày.

## A.7. Claude tự soát lại phép sửa của chính mình và thấy nó nửa việc

Phép sửa ở §A.4 chỉ thêm cảnh báo vào **bảng tổng hợp**. Chạy thử đường đi một mã:

```
uv run python scripts/score_sepa_daily.py --symbol PVP --as-of 2026-09-25

BẢNG ĐIỂM KỸ THUẬT SEPA (MINERVINI TREND TEMPLATE) — MÃ: PVP
Giá đóng cửa: 20,500.0 VND | Điểm xu hướng SEPA: 7/7
```

**7/7 sạch sẽ, không một lời cảnh báo.** Và đó là đường đi **nguy hiểm hơn**: tra cứu một mã là việc người ta làm ngay trước khi hành động trên mã đó, còn bảng tổng hợp là để quét.

**Đã sửa:** `format_single_symbol_report` cũng kiểm danh sách và in `[CHU Y]` ngay dưới dòng tiêu đề. Kiểm lại:

```
--- PVP (không tin cậy) ---
BẢNG ĐIỂM KỸ THUẬT SEPA ... — MÃ: PVP
[CHU Y] Ma nay nam trong danh sach du lieu dieu chinh gia KHONG tin cay ... KHONG dung bang diem duoi day.
Giá đóng cửa: 20,500.0 VND | Điểm xu hướng SEPA: 7/7

--- BFC (tin cậy) ---
BẢNG ĐIỂM KỸ THUẬT SEPA ... — MÃ: BFC
Giá đóng cửa: 48,350.0 VND | Điểm xu hướng SEPA: 3/7
```

Cảnh báo chỉ nổ với mã trong danh sách, không nổ với mã sạch. **Test mới** ghim cả hai chiều; **phá thử** đổi điều kiện thành `if False:` thì test đỏ, và đã in lại dòng code để chắc đột biến được áp.

`exclusions.txt` đã được theo dõi trong git (`git ls-files` xác nhận), nên file đi kèm repo và nhánh "không đọc được file" sẽ không nổ oan.

Suite cuối: **1.237 pass**, ruff sạch.

