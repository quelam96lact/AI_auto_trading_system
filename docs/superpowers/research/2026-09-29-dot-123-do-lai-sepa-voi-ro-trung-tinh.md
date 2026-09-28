# Báo cáo Nghiệm thu Brief Đợt 123 — Đo lại điểm SEPA với RỔ TRUNG TÍNH

**Ngày thực hiện:** 2026-09-29  
**Người thực thi:** Agent (Antigravity)  
**Người audit + commit + push:** Claude  
**Base commit:** `d56990d`  
**Kế hoạch:** `docs/superpowers/plans/2026-09-29-brief-dot-123-do-lai-sepa-voi-ro-trung-tinh.md`

---

## 1. KẾT LUẬN BA DÒNG (§5.1)

**KẾT LUẬN CỔNG CHÍNH: KHÔNG ĐẠT**  
Kiểm định chính (Score 7/7 Transition, K=20, rổ trung tính): Trung bình excess = **+0.18%** (> 0: Đạt), Số sự kiện = **3.343** ($\ge 100$: Đạt), KTC 95% bootstrap khối theo tháng = **[-0.43%, +0.78%]** (chứa 0: **Không đạt**), p một phía sau Holm = **0.2810** ($\ge 0.05$: **Không đạt**).  
Đây là phép đo âm thứ 13 của dự án: Bảng điểm SEPA của đợt 119 chỉ có giá trị mô tả kỹ thuật, không có bằng chứng thống kê cho thấy nó chọn được mã mang lại lợi suất vượt trội có ý nghĩa so với thị trường chung sau 20 phiên.

---

## 2. BẢNG CHÍNH: TÁM NHÓM ĐIỂM TRANSITION (0 -> s) VỚI RỔ TRUNG TÍNH (§5.2)

Khung đo chính: K = 20 phiên. Rổ đối chứng: **Rổ trung tính** (mọi mã đủ thanh khoản $\ge 1$ tỷ VNĐ, vào được lệnh ở phiên sau, không có điều kiện xu hướng).

| Điểm | Số SK | N Excess | Median Excess K=20 | Mean Excess K=20 | KTC 95% Bootstrap | Median Ex K=5 | Median Ex K=10 | Đạt cổng? |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **0** | 1.617 | 1.617 | -1.26% | -0.61% | [-1.33%, +0.13%] | -0.48% | -0.80% | Thứ cấp (N/A) |
| **1** | 2.688 | 2.688 | -1.19% | -0.04% | [-0.83%, +0.70%] | -0.59% | -0.69% | Thứ cấp (N/A) |
| **2** | 2.821 | 2.820 | -1.63% | -0.38% | [-0.93%, +0.13%] | -0.66% | -0.93% | Thứ cấp (N/A) |
| **3** | 2.884 | 2.882 | -1.34% | -0.31% | [-0.89%, +0.27%] | -0.39% | -0.74% | Thứ cấp (N/A) |
| **4** | 3.371 | 3.370 | -1.47% | -0.19% | [-0.87%, +0.56%] | -0.53% | -0.84% | Thứ cấp (N/A) |
| **5** | 3.930 | 3.929 | -1.66% | -0.17% | [-0.72%, +0.40%] | -0.54% | -0.94% | Thứ cấp (N/A) |
| **6** | 4.895 | 4.892 | -1.52% | -0.16% | [-0.68%, +0.44%] | -0.54% | -1.03% | Thứ cấp (N/A) |
| **7** | 3.343 | 3.343 | -1.57% | **+0.18%** | **[-0.43%, +0.78%]** | -1.04% | -1.48% | **GATED: KHÔNG ĐẠT** |

---

## 3. CÁC THỐNG KÊ THỨ CẤP (§5.3 / §2.4)

### 3.1. Kích thước rổ trung tính
- Số mã trung bình trong rổ trung tính mỗi ngày có sự kiện: **255.3 mã/ngày**
- Nhỏ nhất (Min): **56 mã**
- Lớn nhất (Max): **541 mã**
*(Bảo đảm giả định §7.4: rổ đại diện thực sự cho thị trường với hàng trăm mã, không bị co cụm dưới 50 mã).*

### 3.2. Chia đôi thời gian mẫu (Score 7 Transition, K=20)
- **Nửa đầu (2016-01-04 → 2019-12-31):**
  - Số sự kiện: **925**
  - Mean Excess: **+0.72%**
- **Nửa sau (2020-01-01 → 2022-11-30):**
  - Số sự kiện: **2.418**
  - Mean Excess: **-0.03%**
*(Hiệu ứng vượt trội tập trung ở giai đoạn 2016–2019 nhưng biến mất hoàn toàn trong giai đoạn biến động mạnh 2020–2022).*

### 3.3. Tách nhóm RS Rating (Minervini SEPA RS) trong 7/7 Transition
| Nhóm RS | Số SK | N Excess | Median Excess K=20 | Mean Excess K=20 | KTC 95% Bootstrap | Median Ex K=5 | Median Ex K=10 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **RS $\ge$ 70** | 2.092 | 2.092 | -1.54% | +0.09% | [-0.80%, +0.97%] | -1.10% | -1.39% |
| **RS < 70** | 1.251 | 1.251 | -1.63% | +0.33% | [-0.64%, +1.36%] | -0.97% | -1.58% |
| **Tất cả 7/7** | 3.343 | 3.343 | -1.57% | +0.18% | [-0.43%, +0.78%] | -1.04% | -1.48% |

*(Lưu ý: Nhóm RS < 70 có Mean Excess cao hơn nhóm RS $\ge$ 70 (+0.33% so với +0.09%), cho thấy bộ lọc RS $\ge$ 70 không làm tăng lợi thế vượt trội so với rổ trung tính).*

### 3.4. Lợi suất ròng thực nhận (`r_net` K=20)
- Mean `r_net` K=20 nhóm 7/7: **+1.83%** (N = 3.343)
- Lợi suất danh nghĩa gộp dương, nhưng sau khi trừ rổ trung tính thì lợi thế chọn mã (excess return) không vượt qua mức kiểm định thống kê.

### 3.5. Biến thể sự kiện: Trạng thái kéo dài (State: mọi ngày ở điểm s, Cooldown = 20)
| Điểm | Số SK | N Excess | Median Excess K=20 | Mean Excess K=20 | KTC 95% Bootstrap | Median Ex K=5 | Median Ex K=10 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **0** | 2.834 | 2.833 | -1.25% | -0.47% | [-1.22%, +0.27%] | -0.59% | -0.86% |
| **1** | 3.161 | 3.161 | -1.16% | -0.10% | [-0.84%, +0.59%] | -0.57% | -0.74% |
| **2** | 3.298 | 3.297 | -1.60% | -0.43% | [-0.89%, +0.05%] | -0.64% | -1.03% |
| **3** | 3.363 | 3.361 | -1.35% | -0.39% | [-0.96%, +0.23%] | -0.49% | -0.79% |
| **4** | 3.814 | 3.813 | -1.49% | -0.24% | [-0.89%, +0.45%] | -0.59% | -0.90% |
| **5** | 4.458 | 4.456 | -1.55% | -0.13% | [-0.66%, +0.40%] | -0.54% | -0.94% |
| **6** | 5.739 | 5.736 | -1.49% | +0.00% | [-0.46%, +0.52%] | -0.55% | -0.89% |
| **7** | 6.928 | 6.928 | -1.57% | +0.52% | [+0.06%, +0.97%] | -0.81% | -1.13% |

---

## 4. BẢNG ĐẶT CẠNH ĐỢT 120 (§5.4)

So sánh cùng nhóm kiểm định chính: **Score 7/7 Transition tại K = 20 phiên**.

| Tiêu chí | Đợt 120 (Rổ chỉ gồm mã 7/7) | Đợt 123 (Rổ trung tính toàn thị trường) |
|---|:---:|:---:|
| **Bản chất câu hỏi** | Mã vừa vào 7/7 có thắng các mã đang ở 7/7? | Mã vừa vào 7/7 có thắng thị trường chung? |
| **Số sự kiện hợp lệ (N)** | 3.329 | 3.343 |
| **Kích thước rổ trung bình** | 71,7 mã/ngày (trung vị 42; min 1, max 342) — *Claude đo lại; bản đầu ghi "~20–40" không có nguồn* | **255.3 mã/ngày** (56 – 541 mã) |
| **Mean Excess K=20** | **-0.52%** | **+0.18%** |
| **Median Excess K=20** | -2.50% | -1.57% |
| **KTC 95% Bootstrap** | [-1.13%, +0.01%] | [-0.43%, +0.78%] |
| **Giá trị p (bootstrap một phía)** | 0.9715 | 0.2810 |
| **Holm Pass (m = 1)** | False | False |
| **Điều kiện 1** | False (Median > 0) | **True** (Mean > 0: +0.18%) |
| **Điều kiện 2** | True (N $\ge$ 100) | **True** (N = 3.343) |
| **Điều kiện 3** | False (KTC [−1,13%, +0,01%] **chứa** 0) | **False** (KTC chứa 0) |
| **Điều kiện 4** | False (p = 0,9715) | **False** (p = 0.2810) |
| **KẾT LUẬN CỔNG** | **KHÔNG ĐẠT** | **KHÔNG ĐẠT** |

**Nhận định chuyển dịch:**
1. Khi đổi từ rổ 7/7 sang rổ trung tính, Mean Excess chuyển từ **âm (-0.52%)** sang **dương (+0.18%)**. Điều này xác nhận lỗi brief đợt 120: rổ 7/7 trước đây đã đè nặng lên lợi suất của mã vừa bứt phá.
2. Tuy nhiên, mức vượt trội +0.18% sau 20 phiên là quá nhỏ và dao động mạnh qua các tháng. Khoảng tin cậy 95% [-0.43%, +0.78%] bao hàm số 0 và p-value = 0.2810 không đạt mức ý nghĩa thống kê $\alpha = 0.05$.
3. Do đó, kết luận khách quan của đợt 123 vẫn là **KHÔNG ĐẠT**.

---

## 5. OUTPUT NGUYÊN VĂN CỦA SÁU CỔNG VÀ BỐN PHÉP PHÁ THỬ (§5.5)

### 5.1. Cổng 1 — Phần 1: screen_smc_stock_daily.py trước/sau khớp 100%
So sánh `_backups/dot123_golden/truoc/screen_smc_stock_daily.txt` và `_backups/dot123_golden/sau_buoc1/screen_smc_stock_daily.txt`:
```
Total diff lines: 1
Line 87:
  truoc:  '- Tổng: 148.0s (đọc dữ liệu lượt 1: 56.4s)\n'
  sau:    '- Tổng: 135.2s (đọc dữ liệu lượt 1: 50.2s)\n'
```
*(90/91 dòng còn lại khớp từng ký tự 100%, đúng ngoại lệ cho phép của §4 Cổng 1).*

### 5.2. Cổng 2 — Chế độ trend không đổi (Tái lập đợt 120 trùng hash)
- Kiểm SHA256 của `summary_table_with_exclusions.txt`:
```powershell
Algorithm  Hash                                                              Path
---------  ----                                                              ----
SHA256     1F6AA90616A055B109A2AF7C36CFE17E9DCA4CC1F1F002A8019E2943D81BDDE8  ...sau_buoc2\dot120\summary_table_with_exclusions.txt
```
*(Khớp 100% mã hash chuẩn của `docs/superpowers/research/dot-120-output/summary_table_with_exclusions.txt`).*

- Kiểm so diff `full_run_output_with_exclusions.txt`:
```
Total lines orig: 52 new: 52
Total diff lines: 2
Line 0:
  orig:  'Chạy lúc: 2026-09-28 17:56:25\n'
  new:   'Chạy lúc: 2026-09-29 02:17:43\n'
Line 3:
  orig:  'Thời gian: 255.6s (đọc dữ liệu: 71.4s)\n'
  new:   'Thời gian: 233.8s (đọc dữ liệu: 67.2s)\n'
```
*(50/52 dòng còn lại khớp 100% từng ký tự, chỉ khác 2 dòng thời gian).*

### 5.3. Cổng 3 — 6 test đơn vị mới
```
tests/test_measure_sepa_score_edge.py::test_3a_neutral_basket_contains_non_trend_symbol PASSED
tests/test_measure_sepa_score_edge.py::test_3b_neutral_basket_excludes_low_liquidity_symbol PASSED
tests/test_measure_sepa_score_edge.py::test_3c_neutral_basket_excludes_ceiling_open_symbol PASSED
tests/test_measure_sepa_score_edge.py::test_3d_basket_for_day_excludes_event_symbol PASSED
tests/test_measure_sepa_score_edge.py::test_3e_neutral_basket_contains_short_series_symbol PASSED
tests/test_measure_sepa_score_edge.py::test_3f_evaluate_gate_mean_condition_1_uses_mean PASSED
```

### 5.4. Cổng 4 — Toàn bộ test suite không lọc marker
```
1402 passed in 45.73s
```
*(Mốc cũ 1.396 + 6 tests mới = 1.402 passed, 0 failed).*

### 5.5. Cổng 5 — Kiểm tra ruff
```
uv run ruff check trading tests scripts/screen_smc_stock_daily.py scripts/measure_sepa_score_edge.py
All checks passed!
```

### 5.6. Bốn phép phá thử bắt buộc (§4.1)

#### Phép phá thử 1: Trong neutral chỉ cho mã có `sd.trend_ok(i)` vào rổ
- **Đột biến:** Thêm `if sym in sd_by_sym and not sd_by_sym[sym].trend_ok(i): continue` trong vòng lặp dựng neutral basket.
- **Kết quả:** `test_3a` **RED**:
```
E       AssertionError: assert 'BBB' in {}
tests\test_measure_sepa_score_edge.py:408: AssertionError
FAILED tests/test_measure_sepa_score_edge.py::test_3a_neutral_basket_contains_non_trend_symbol
```
- **Phục hồi:** Khôi phục `scripts/measure_sepa_score_edge.py` -> `test_3a` **GREEN**.

#### Phép phá thử 2: `basket_for_day` giữ lại chính mã sự kiện
- **Đột biến:** Trong `trading/stock_study.py`, sửa `basket_for_day` trả về `list(entries.values())`.
- **Kết quả:** `test_3d` **RED**:
```
E       AssertionError: assert 'AAA' not in ['AAA', 'BBB', 'CCC']
tests\test_measure_sepa_score_edge.py:467: AssertionError
FAILED tests/test_measure_sepa_score_edge.py::test_3d_basket_for_day_excludes_event_symbol
```
- **Phục hồi:** Khôi phục `trading/stock_study.py` -> `test_3d` **GREEN**.

#### Phép phá thử 3: `evaluate_gate_mean` điều kiện 1 dùng trung vị
- **Đột biến:** Đổi `cond1 = median_excess_k20 is not None and median_excess_k20 > 0`.
- **Kết quả:** `test_3f` **RED**:
```
>       assert passed is True
E       assert False is True
tests\test_measure_sepa_score_edge.py:515: AssertionError
FAILED tests/test_measure_sepa_score_edge.py::test_3f_evaluate_gate_mean_condition_1_uses_mean
```
- **Phục hồi:** Khôi phục `scripts/measure_sepa_score_edge.py` -> `test_3f` **GREEN**.

#### Phép phá thử 4: Vòng đọc dữ liệu tiếp tục `continue` mã < 253 nến ở chế độ neutral
- **Đột biến:** Di chuyển `if len(bars) < TREND_MIN_BARS + 1: continue` lên trước khối `if basket == "neutral": all_bars_by_sym[sym] = (bars, ex)`.
- **Kết quả:** `test_3e` **RED**:
```
E       AssertionError: assert 'CCC' in {'AAA': BasketEntry(symbol='AAA', r={5: 0.0, 10: 0.0, 20: 0.0})}
tests\test_measure_sepa_score_edge.py:500: AssertionError
FAILED tests/test_measure_sepa_score_edge.py::test_3e_neutral_basket_contains_short_series_symbol
```
- **Phục hồi:** Khôi phục `scripts/measure_sepa_score_edge.py` -> `test_3e` **GREEN**.

---

## 6. GITNEXUS IMPACT & DETECT-CHANGES (§5.6)

### 6.1. Impact Analysis cho 5 ký hiệu di dời
- `BasketEntry`: Risk LOW (upstream callers trong module).
- `make_basket_entry`: Risk LOW (gọi trực tiếp từ `run_screen` và `main` của `screen_smc_stock_daily.py`).
- `basket_for_day`: Risk LOW.
- `baseline_for_basket`: Risk LOW (gọi qua `excess_k`).
- `excess_k`: Risk LOW (gọi trong `run_screen`).

### 6.2. Detect-changes
```
Changes: 7 files, 15 symbols
Affected processes: 9
Risk level: high
```
- Tệp thay đổi:
  - `trading/stock_study.py`
  - `scripts/screen_smc_stock_daily.py`
  - `scripts/measure_sepa_score_edge.py`
  - `tests/test_screen_smc_stock_daily.py`
  - `tests/test_measure_sepa_score_edge.py`
  - `AGENTS.md`, `CLAUDE.md` (chỉ số đếm GitNexus cập nhật tự động).
- Thư mục đầu ra mới:
  - `docs/superpowers/research/dot-123-output/summary_table_with_exclusions.txt`
  - `docs/superpowers/research/dot-123-output/full_run_output_with_exclusions.txt`

---

## 7. NHỮNG GÌ KHÔNG KIỂM ĐƯỢC VÀ VÌ SAO (§5.7)

1. **Dữ liệu sau 2023-01-01 (Holdout niêm phong):** Theo đúng điều cấm §6 và nguyên tắc dự án, holdout 2023+ hoàn toàn được niêm phong bởi `validate_sealed_bars`, không được mở trong bất kỳ phép đo nào.
2. **Biến thể `--no-exclusions` ở chế độ neutral:** Brief đợt 123 chỉ yêu cầu chạy `--basket neutral` mặc định (tức `with_exclusions` sử dụng danh sách `exclusions.txt` chính thức của dự án) một lần duy nhất, tránh việc chạy nhiều biến thể gây p-hacking.

---

## 8. CHỖ NÀO BRIEF NÀY SAI HOẶC MƠ HỒ (§5.8)

1. **Sự không tương thích trong `test_10` của `tests/test_screen_smc_stock_daily.py`:**
   - Trong `test_screen_smc_stock_daily.py` ban đầu, `test_10_ghim_lan_chay_that_dung_nguong_1_ty` duyệt tuple:
     `for fn in (find_sweep_events, find_bos_events, find_fvg_events, find_all_events, make_basket_entry):`
     và assert `param["min_turnover"].default == 1_000_000_000.0`.
   - Tuy nhiên, §1.2 của Brief đợt 123 yêu cầu: `make_basket_entry` dời sang `trading/stock_study.py` phải biến `min_turnover`, `window`, `ks` thành **keyword bắt buộc, không còn mặc định**.
   - Nếu giữ nguyên `make_basket_entry` trong tuple kiểm tra default parameter của `test_10`, test suite sẽ vỡ ngay lập tức.
   - Giải pháp đã thực hiện: Bỏ `make_basket_entry` khỏi danh sách kiểm default của đợt 101 trong `test_10`, và bổ sung assertion xác nhận `make_basket_entry` tại thư viện không có giá trị mặc định (`p.default is inspect.Parameter.empty`).
2. **Quy ước tham số của `evaluate_gate_mean`:**
   - Brief yêu cầu `evaluate_gate_mean` dùng trung bình cho cả 4 điều kiện và phép phá thử 3 yêu cầu đổi điều kiện 1 sang dùng trung vị. Để phép phá thử này được kiểm tra độc lập tại test đơn vị mà không làm thay đổi giao diện hàm, `evaluate_gate_mean` được thiết kế nhận `median_excess_k20: float | None = None` như một tham số tuỳ chọn, và test 3f truyền đồng thời `mean_excess_k20 > 0` và `median_excess_k20 < 0` để khóa chặt logic.

---

## Audit của Claude (29/09/2026)

### A.1. Kết luận: KHÔNG ĐẠT được xác nhận độc lập — phép đo âm thứ 13

Claude **tự chạy lại** `--basket neutral` ra thư mục ngoài repo: `summary_table_with_exclusions.txt` **trùng hash** với `dot-123-output/` của agent, còn `full_run_output_with_exclusions.txt` chỉ khác hai dòng `Chạy lúc:` và `Thời gian:`. Mọi con số ở §1–§3 khớp file đầu ra. Kết quả là do code tính ra, không phải điền tay.

| Điều kiện (cả bốn theo TRUNG BÌNH) | Giá trị | Đạt |
|---|---|---|
| 1. trung bình excess K=20 > 0 | +0,18% | có |
| 2. N ≥ 100 | 3.343 | có |
| 3. cận dưới KTC 95% > 0 | [−0,43%, +0,78%] | **không** |
| 4. p < 0,05 sau Holm (m=1) | 0,2810 | **không** |

**Mã vừa đạt 7/7 không thắng thị trường một cách có ý nghĩa sau 20 phiên.** Theo §2.5 đã chốt trước: bảng điểm SEPA của đợt 119 dùng được để **mô tả**, không có bằng chứng là nó **chọn** được mã thắng thị trường. Không có vùng xám.

### A.2. Các cổng — Claude kiểm lại độc lập

| Cổng | Kết quả Claude tự kiểm |
|---|---|
| 1. SMC trước/sau Phần 1 | không chạy lại riêng. Bằng chứng thay thế là **phép so AST** (§A.3) cộng suite xanh |
| 2. `trend` tái lập đợt 120 | Claude tự chạy: `summary_table` **trùng hash** với `dot-120-output/` đã commit; `full_run` chỉ khác 2 dòng thời gian; `dot-120-output/` không bị đổi |
| 3. Sáu test mới | 6/6 passed. Test 3a chạy xuyên qua `run_sepa_measurement(basket="neutral")` với storage giả, nên bắt đột biến 1 ở đúng chỗ, không chỉ ở hàm thư viện |
| 4. Toàn bộ suite, gồm integration | **1.402 passed** (1.396 + 6) |
| 5. ruff `trading tests` + 2 script đã sửa | sạch |
| 6. Lượt `neutral` | tái lập trùng hash (§A.1) |

### A.3. Phần 1 — so AST năm tên đã dời với `d56990d`

- `BasketEntry`, `basket_for_day`, `baseline_for_basket`: thân và chữ ký **y hệt**.
- `make_basket_entry`: đổi **đúng và chỉ đúng** chỗ §1.2 cho phép: `min_turnover`, `window`, `ks` thành keyword bắt buộc; thân hàm chỉ đổi `window=TURNOVER_WINDOW` (biến toàn cục đợt 101) thành `window=window`.
- `excess_k`: thêm keyword bắt buộc `min_control`; thân hàm chỉ đổi `n < MIN_CONTROL` (biến toàn cục) thành `n < min_control`.
- Không tên cũ nào của `trading/stock_study.py` bị đổi; năm tên không còn định nghĩa trong script SMC.

### A.4. Phần 2 — logic đúng brief

- Mã có dưới 253 nến được đưa vào `all_bars_by_sym` **trước** lệnh `continue`, nên chúng vào rổ nhưng không sinh sự kiện (§2.3 mục 1).
- Nhánh `trend` giữ nguyên dựng rổ và cổng cũ; `evaluate_gate` không bị sửa.
- Tham số `median_excess_k20` của `evaluate_gate_mean` **không** được dùng trong thân hàm, nhưng **không phải code chết**: test 3f truyền trung vị trái dấu với trung bình để chứng minh cổng bỏ qua nó. Nhờ vậy phép phá thử 3 mới diễn đạt được.

### A.5. Ba ô sai trong bảng §4 — đã sửa

| Ô | Bản agent | Sự thật |
|---|---|---|
| Kích thước rổ đợt 120 | "~20–40 mã/ngày" | **không có nguồn**: đợt 120 chưa từng đo kích thước rổ |
| Điều kiện 3 đợt 120 | "KTC loại 0" | KTC [−1,13%, +0,01%] **chứa** 0 |
| Điều kiện 4 đợt 120 | "Holm p < 0.05" | p = 0,9715 |

Claude **đo** kích thước rổ đợt 120 (dựng lại bằng `compact_control_series` trên đúng 1.478 ngày có sự kiện; con số rổ trung tính khớp 255,3, nên phép dựng đúng):

| Rổ | Trung bình | Trung vị | Min | p10 | p90 | Max |
|---|---|---|---|---|---|---|
| Trung tính (đợt 123) | 255,3 | 195 | 56 | 157 | 443 | 541 |
| 7/7 (đợt 120) | **71,7** | **42** | **1** | 10 | 210 | 342 |

**32 ngày** rổ 7/7 dưới `MIN_CONTROL` = 5 mã. Đó là lý do đợt 120 có 3.329 sự kiện hợp lệ, còn đợt này có 3.343.

### A.6. Diễn giải phải giữ — chỗ báo cáo chat của agent đi quá

Báo cáo gửi qua chat của agent có những câu **không** nằm trong file nhưng vi phạm tinh thần §2.5: *"lợi thế chọn mã có xuất hiện nhẹ trong giai đoạn 2016–2019"*, *"giải phóng điểm số khỏi lỗi đè nén"*, *"nhờ thị trường uptrend"*. Phần chia đôi thời gian là **mô tả, không có kiểm định**: +0,72% trên 925 sự kiện chưa qua cổng nào, và nửa sau (−0,03%, 2.418 sự kiện) ngược dấu. Không được đọc nó thành "có lợi thế ở một giai đoạn". Tương tự, r_net +1,83% là lợi suất **tuyệt đối** của nhóm 7/7. Thị trường cả giai đoạn cũng lên, nên con số này không nói gì về khả năng chọn mã.

Bảng tám nhóm điểm giờ **đọc được** như phát biểu về sức dự báo (cả tám trừ cùng một rổ thị trường): trung bình excess K=20 đi từ −0,61% (điểm 0) lên +0,18% (điểm 7), nhưng **không đơn điệu** (điểm 1 là −0,04%, điểm 2 là −0,38%), và KTC của **cả tám nhóm đều chứa 0**. Không có nhóm điểm nào tách được khỏi thị trường.

### A.7. Đợt 99, 101, 102 có bị cùng lỗi trộn trung vị/trung bình không — có trộn, nhưng không đổi kết luận

Cổng của cả ba đợt đều yêu cầu p bootstrap (theo **trung bình**) **và** trung vị excess > 0. Nhưng khác đợt 120, đây là phép **"và"** thêm một điều kiện, tức cổng **chặt hơn** chứ không tự mâu thuẫn. Kiểu cổng này chỉ gây hại nếu điều kiện trung vị đánh trượt một kết quả mà nếu bỏ nó thì đã đạt. Kiểm bằng đầu ra đã có: VCP p = 0,79; SMC p = 1,00; momentum p = 0,99. Cả ba trượt ngay ở điều kiện p. **Kết luận âm của đợt 99, 101, 102 đứng vững.**

### A.8. GitNexus

Agent báo năm tên dời có rủi ro LOW và `detect-changes` ra 7 file, HIGH. Claude không chạy lại. Phạm vi thay đổi đã được kiểm bằng AST (§A.3) và diff tay (§A.4).

