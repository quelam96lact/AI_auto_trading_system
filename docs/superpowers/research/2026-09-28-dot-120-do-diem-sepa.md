# Báo cáo kết quả đợt 120 — Đo lường lợi thế dự báo của điểm SEPA (Minervini Trend Template 0–7) và RS ≥ 70

- **Ngày thực hiện**: 28/09/2026
- **Base commit**: `fe9ac1e`
- **Người audit**: Claude. **Người thực thi**: Antigravity agent.
- **Thư mục output dữ liệu**: `docs/superpowers/research/dot-120-output/`

---

## 1. Kết luận ba dòng (§6.1)

1. **Nhóm sự kiện 7/7 tại K = 20 KHÔNG ĐẠT cổng tiền đăng ký** (hỏng 3/4 điều kiện): trung vị lợi suất vượt trội = **-2.50%** (điều kiện 1: False), số sự kiện = **3.329** (điều kiện 2: True), KTC 95% bootstrap khối theo tháng = **[-1.13%, +0.01%]** chứa 0 (điều kiện 3: False), Holm điều chỉnh m=1 với p-value = **0.9715** (điều kiện 4: False).
2. **Điểm SEPA 0–7 HOÀN TOÀN KHÔNG ĐƠN ĐIỆU**: điểm càng cao lợi suất vượt trội càng âm sâu hơn; nhóm 7/7 có trung vị vượt trội kém nhất (-2.50%) trong các nhóm điểm dương, thua cả nhóm điểm 1 (-1.69%), điểm 2 (-1.67%) và điểm 3 (-1.68%).
3. **RS ≥ 70 KHÔNG THÊM ĐƯỢC LỢI THẾ NÀO TRONG NHÓM 7/7**: nhóm RS ≥ 70 có trung vị vượt trội K=20 là **-2.61%**, thậm chí âm sâu hơn nhóm RS < 70 (**-2.15%**).

---

## 2. Bảng chính: Đo lường điểm SEPA (Chuyển trạng thái 0 -> s) và tính đơn điệu (§6.2)

- Cửa sổ tín hiệu: `2016-01-04` đến `2022-11-30`. Đọc tới `2022-12-31`. Niêm phong giữ nguyên (`READ_TO = 2023-01-01`).
- Loại trừ 246 mã không tin cậy theo `exclusions.txt` (Vũ trụ sạch: 1.308 mã).
- Đối chứng cùng ngày: rổ cổ phiếu đạt điều kiện thanh khoản + xu hướng cùng ngày từ `compact_control_series`.
- Bootstrap khối theo tháng dương lịch: `N = 2.000`, `seed = 42`.
- Tệp kết quả gốc: [`docs/superpowers/research/dot-120-output/summary_table_with_exclusions.txt`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/docs/superpowers/research/dot-120-output/summary_table_with_exclusions.txt) (Lệnh chạy: `uv run python scripts/measure_sepa_score_edge.py`, exit code: 0).

| Điểm | Số SK | N Excess hợp lệ | Trung vị Excess K=20 | Trung bình Excess K=20 | KTC 95% Bootstrap | K=5 (Trung vị) | K=10 (Trung vị) | Đạt cổng? |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0 | 1.617 | 1.514 | -2.38% | -1.33% | [-4.43%, +1.93%] | -0.84% | -1.46% | Thứ cấp (N/A) |
| 1 | 2.688 | 2.461 | -1.69% | -0.47% | [-2.82%, +1.90%] | -0.73% | -1.15% | Thứ cấp (N/A) |
| 2 | 2.821 | 2.712 | -1.67% | -0.24% | [-1.98%, +1.47%] | -0.69% | -1.14% | Thứ cấp (N/A) |
| 3 | 2.884 | 2.841 | -1.68% | -0.67% | [-1.91%, +0.61%] | -0.59% | -0.97% | Thứ cấp (N/A) |
| 4 | 3.371 | 3.346 | -2.01% | -0.57% | [-1.63%, +0.54%] | -0.56% | -1.11% | Thứ cấp (N/A) |
| 5 | 3.930 | 3.904 | -2.13% | -0.71% | [-1.59%, +0.17%] | -0.76% | -1.30% | Thứ cấp (N/A) |
| 6 | 4.895 | 4.866 | -2.27% | -0.83% | [-1.43%, -0.17%] | -0.79% | -1.43% | Thứ cấp (N/A) |
| **7** | **3.343** | **3.329** | **-2.50%** | **-0.52%** | **[-1.13%, +0.01%]** | **-1.29%** | **-2.05%** | **KHÔNG ĐẠT** |

> **Nhận xét về tính đơn điệu**:
> - Không hề có xu hướng đơn điệu tăng của lợi suất vượt trội theo điểm (0 -> 7).
> - Từ điểm 2 (-1.67%) lên điểm 7 (-2.50%), trung vị lợi suất vượt trội liên tục xấu đi khi điểm tăng lên.
> - Tại mọi kỳ hạn ($K=5, 10, 20$), tất cả các nhóm điểm từ 0 đến 7 đều có trung vị lợi suất vượt trội âm so với đối chứng cùng ngày.

---

## 3. Bảng tách RS trong nhóm 7/7 (Transition) (§6.3)

| Nhóm RS trong 7/7 | Số SK | N Excess hợp lệ | Trung vị Excess K=20 | Trung bình Excess K=20 | KTC 95% Bootstrap | K=5 (Trung vị) | K=10 (Trung vị) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **RS ≥ 70** | 2.092 | 2.078 | **-2.61%** | -0.77% | [-1.63%, +0.06%] | -1.36% | -2.23% |
| **RS < 70** | 1.251 | 1.251 | **-2.15%** | -0.11% | [-1.22%, +0.85%] | -1.17% | -1.67% |
| **Tất cả 7/7** | 3.343 | 3.329 | **-2.50%** | -0.52% | [-1.13%, +0.01%] | -1.29% | -2.05% |

> **Nhận xét về RS**:
> - Lọc thêm $RS \ge 70$ không những không cải thiện lợi suất vượt trội mà còn làm giảm trung vị vượt trội thêm 0.46% (từ -2.15% xuống -2.61%).
> - Ở cả $K=5$ (-1.36% so với -1.17%) và $K=10$ (-2.23% so với -1.67%), nhóm $RS \ge 70$ đều kém hơn nhóm $RS < 70$.

---

## 4. Bảng so sánh có loại / không loại 246 mã không tin cậy (§6.4)

So sánh giữa kết quả chính (có loại 246 mã theo `exclusions.txt`) và kết quả đối chiếu (không loại mã nào):
- Tệp kết quả có loại: [`docs/superpowers/research/dot-120-output/full_run_output_with_exclusions.txt`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/docs/superpowers/research/dot-120-output/full_run_output_with_exclusions.txt)
- Tệp kết quả không loại: [`docs/superpowers/research/dot-120-output/full_run_output_no_exclusions.txt`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/docs/superpowers/research/dot-120-output/full_run_output_no_exclusions.txt)

| Chỉ số | Có loại 246 mã (Kết quả chính) | Không loại mã nào (Đối chiếu) | Chênh lệch (Mất đi khi loại) |
|---|:---:|:---:|:---:|
| Tổng số mã nạp trong vũ trụ | 1.308 mã | 1.554 mã | -246 mã (-15.8%) |
| Số mã hợp lệ (đủ nến & clean) | 1.187 mã | 1.428 mã | -241 mã |
| Tổng sự kiện Score 7 Transition | 3.343 SK | 3.436 SK | **-93 SK (-2.7%)** |
| N Excess hợp lệ Score 7 | 3.329 SK | 3.422 SK | **-93 SK (-2.7%)** |
| **Trung vị Excess K=20 (Score 7)** | **-2.50%** | **-2.54%** | +0.04% |
| Trung bình Excess K=20 (Score 7) | -0.52% | -0.60% | +0.08% |
| KTC 95% Bootstrap K=20 | [-1.13%, +0.01%] | [-1.20%, -0.08%] | Không đổi kết luận |
| p-value Bootstrap | 0.9715 | 0.9870 | Không đổi kết luận |
| **Kết luận cổng** | **KHÔNG ĐẠT** | **KHÔNG ĐẠT** | Giữ nguyên kết luận |

> **Nhận định**:
> - Việc loại bỏ 246 mã có dữ liệu split lỗi chỉ làm mất 93 sự kiện hợp lệ (khoảng 2.7% mẫu).
> - Trung vị vượt trội hầu như giữ nguyên (-2.50% vs -2.54%).
> - Kết luận không đạt cổng là hoàn toàn vững chắc, không bị ảnh hưởng bởi việc có hay không loại trừ 246 mã này.

---

## 5. Biến thể sự kiện: Trạng thái kéo dài (Mọi ngày ở điểm s, Cooldown 20) (§6.5)

Biến thể báo cáo theo §2.1 (nhận mọi ngày cổ phiếu ở điểm `s`, giãn cách 20 nến, không bắt buộc bước chuyển trạng thái):

| Điểm | Số SK | N Excess hợp lệ | Trung vị Excess K=20 | Trung bình Excess K=20 | KTC 95% Bootstrap | K=5 (Trung vị) | K=10 (Trung vị) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0 | 2.834 | 2.550 | -2.58% | -1.43% | [-4.45%, +1.79%] | -1.10% | -1.76% |
| 1 | 3.161 | 2.906 | -1.70% | -0.55% | [-2.79%, +1.80%] | -0.75% | -1.19% |
| 2 | 3.298 | 3.181 | -1.74% | -0.41% | [-2.10%, +1.31%] | -0.65% | -1.23% |
| 3 | 3.363 | 3.313 | -1.82% | -0.81% | [-2.23%, +0.53%] | -0.59% | -1.04% |
| 4 | 3.814 | 3.784 | -2.01% | -0.72% | [-1.78%, +0.39%] | -0.67% | -1.10% |
| 5 | 4.458 | 4.431 | -1.97% | -0.67% | [-1.56%, +0.20%] | -0.75% | -1.25% |
| 6 | 5.739 | 5.709 | -2.13% | -0.65% | [-1.19%, -0.07%] | -0.80% | -1.36% |
| **7** | **6.928** | **6.906** | **-2.27%** | **-0.06%** | **[-0.42%, +0.29%]** | **-1.05%** | **-1.57%** |

> **Nhận định**:
> - Dưới biến thể trạng thái kéo dài, số sự kiện 7/7 tăng hơn gấp đôi (từ 3.329 lên 6.906), nhưng trung vị lợi suất vượt trội vẫn âm sâu (**-2.27%**).
> - Tính phi đơn điệu vẫn hiện hữu rõ rệt: điểm 7 (-2.27%) vẫn thua điểm 1 (-1.70%), điểm 2 (-1.74%) và điểm 3 (-1.82%).
> - Cách định nghĩa sự kiện không làm thay đổi kết luận.

---

## 6. Output kiểm định, linter và 5 phép phá thử bắt buộc (§6.6)

### 6.1. Suite kiểm định đầy đủ
- Lệnh: `uv run pytest -m "not integration" -q`
- Exit code: 0
- Kết quả: **1.244 passed, 137 deselected in 39.07s** (Đúng chuẩn: 1.237 test cũ + 7 test mới thêm ở đợt 120).

### 6.2. Ruff linter
- Lệnh: `uv run ruff check trading tests scripts/measure_sepa_score_edge.py`
- Exit code: 0
- Kết quả: **All checks passed!**

### 6.3. Bằng chứng 5 phép phá thử bắt buộc (§5)

| # | Đột biến | Dòng mã bị sửa (Diff / Code) | Kết quả Test | Bằng chứng lỗi / Fail | Phục hồi |
|---|---|---|:---:|---|:---:|
| 1 | Điểm tại `t` tính từ nến `t+1` (nhìn trước) | `idx + 2` thay vì `idx + 1` trong `compute_score_series` | **RED** | `IndexError: list index out of range` tại nến cuối, hoặc `assert 6 == 0` | Đã phục hồi GREEN từ backup scratch |
| 2 | Sự kiện = mọi ngày 7/7, bỏ transition | `is_match = (scores[t] == 7)` bỏ `scores[t-1] < 7` | **RED** | `AssertionError: assert [253, 255, 257] == [253, 257]` | Đã phục hồi GREEN từ backup scratch |
| 3 | Bỏ `excess_for_event`, dùng lợi suất thô | `e.excess[k] = e.r.get(k)` trong `assign_event_excess` | **RED** | `AssertionError: assert 0.05 == -0.03` (Lần 1 yếu do chỉ gọi hàm gốc, đã siết test gọi qua `assign_event_excess`) | Đã phục hồi GREEN từ backup scratch |
| 4 | Bỏ `apply_cooldown` | `return cand` thay vì `return apply_cooldown(cand, cooldown)` | **RED** | `AssertionError: assert [260, 265, 275, 281, 305] == [260, 281, 305]` | Đã phục hồi GREEN từ backup scratch |
| 5 | Bỏ lọc `exclusions.txt` | `return load_universe(storage, "__no_exclusions__.tmp")` vô điều kiện | **RED** | `AssertionError: assert ['AAA', 'BAD1', 'BBB', 'BAD2', 'CCC'] == ['AAA', 'BBB', 'CCC']` | Đã phục hồi GREEN từ backup scratch |

---

## 7. Xác nhận nợ kỹ thuật (§1.1) và các điểm bất thường (§6.7)

### 7.1. Xác nhận nợ kỹ thuật §1.1
- Antigravity agent xác nhận đã đọc toàn bộ mục §1.1 của Brief 120.
- `scripts/measure_sepa_score_edge.py` hiện là người dùng thứ tư import từ `scripts/screen_vcp_daily.py`.
- **Rà soát khả năng tương thích khi import**: Tất cả các hàm được chỉ định trong bảng §1 (`trend_conditions`, `rolling_mean`, `rolling_max`, `rolling_min`, `clean_bars`, `bar_date`, `validate_sealed_bars`, `in_is`, `liquidity_ok`, `apply_cooldown`, `entry_status`, `is_ceiling_open`, `limit_rate`, `net_return`, `compute_targets`, `basket_baseline`, `excess_for_event`, `bootstrap_by_month`, `compact_control_series`, `load_universe`, `_describe`, `_percentile`) đều được import và sử dụng trực tiếp nguyên vẹn, **không cần phải sửa đổi bất kỳ dòng mã nào trong `scripts/screen_vcp_daily.py`**.
- **Đặc điểm của `compact_control_series`**: Hàm này lọc rổ đối chứng theo `sd.trend_ok(i) and sd.liq_ok(i)`. Do đó, đối chứng cùng ngày ở đây là tập hợp các cổ phiếu thỏa mãn mẫu hình xu hướng (Trend Template 7 điều kiện) và thanh khoản ≥ 1 tỷ VNĐ.

### 7.2. Điểm bất thường phát hiện
- Khi truyền `no_exclusions = True`, nếu truyền chuỗi rỗng `""` vào `load_universe`, trên môi trường Windows hàm `pathlib.Path("").exists()` trả về `True` (vì trỏ vào thư mục hiện tại `.`), dẫn tới cố gắng đọc thư mục dạng text và gây ra lỗi `PermissionError: [Errno 13] Permission denied: '.'`. Script `measure_sepa_score_edge.py` đã xử lý an toàn bằng cách truyền đường dẫn tệp tạm không tồn tại (`__no_exclusions__.tmp`) khi cờ `--no-exclusions` được bật.
- Cột `ts` trong bảng `bars_daily` lưu `00:00:00+07` nhưng một số dòng có thể lệch múi giờ nếu cast trực tiếp `ts::date`. Truy vấn SQL kiểm chéo bắt buộc phải dùng `(ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`.

---

## 8. Truy vấn SQL kiểm chéo (§6)

Claude có thể chạy lại các truy vấn sau trực tiếp trong cơ sở dữ liệu để kiểm chéo dữ liệu cơ sở:

```sql
-- 1. Kiểm tra số nến và khoảng thời gian trước 2023 (đảm bảo niêm phong 2023-01-01)
SELECT count(*) AS total_bars_pre2023,
       min((ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date) AS min_date,
       max((ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date) AS max_date
FROM bars_daily
WHERE ts < '2023-01-01 00:00:00+07';
-- Kết quả trả về: 2.042.621 nến, từ 2016-01-04 đến 2022-12-30.

-- 2. Kiểm tra số symbol có nến trước 2023
SELECT count(DISTINCT symbol) AS distinct_symbols
FROM bars_daily
WHERE ts < '2023-01-01 00:00:00+07';
-- Kết quả trả về: 1.468 mã.

-- 3. Kiểm tra số lượng nến và thanh khoản trung bình của mã HPG trong In-Sample
SELECT count(*) AS n_bars_is,
       min((ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date) AS min_is,
       max((ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date) AS max_is,
       avg(close * volume) AS avg_turnover_vnd
FROM bars_daily
WHERE symbol = 'HPG'
  AND (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date BETWEEN '2016-01-04' AND '2022-11-30';
-- Kết quả: 1.730 nến, thanh khoản trung bình ~177,3 tỷ VNĐ/phiên (thỏa mãn liq_ok).
```

---

## 9. Danh sách những gì agent KHÔNG kiểm được và lý do (§6.8)

1. **GitNexus index bị stale**:
   - Chạy `npx gitnexus status` báo: `Repository: D:\My_Vault_Obsidian\Project\AI_auto_trading_system`, `Status: ⚠️ stale (re-run gitnexus analyze)`.
   - Lý do không re-index: Brief §7 nghiêm cấm tự ý chạy `npx gitnexus analyze --force`. Agent đã dùng GitNexus ở chế độ tra cứu và kiểm tra diff trực tiếp qua git CLI.
2. **Dữ liệu Out-of-Sample từ 2023-01-01 trở đi**:
   - Hoàn toàn KHÔNG được đọc hoặc kiểm tra theo đúng quy định niêm phong holdout (`READ_TO = 2023-01-01` và `validate_sealed_bars`). Holdout 2023-2026 vẫn được bảo toàn nguyên vẹn.
3. **Quyết định loại trừ 246 mã khỏi vũ trụ RS của `score_sepa_daily.py`**:
   - Đây là câu hỏi mở còn treo (§9) của hệ thống hiển thị bảng điểm trực tiếp hàng ngày, không thuộc phạm vi đợt đo tiền đăng ký này.

---

Tôi không commit, không push, không đặt lệnh, không sửa `screen_vcp_daily.py` hay `trading/`, không đổi hằng số đã đăng ký, không đọc dữ liệu từ 2023-01-01, không đưa phép thứ cấp vào cổng, và mọi output đều có file kèm đường dẫn.

---

# PHẦN AUDIT CỦA CLAUDE — 28/09/2026

## A.1. Kết luận audit, và nó không giống kết luận của báo cáo

**Code đúng. Số đúng. Nhưng phép đo trả lời một câu HẸP HƠN hẳn câu mà brief tưởng là đang hỏi — và đó là lỗi thiết kế của brief Claude.**

Kết luận số 2 của báo cáo ("điểm SEPA hoàn toàn không đơn điệu") và số 3 ("RS không thêm được lợi thế") **không được phép đo này chứng minh**. Kết luận số 1 thì đúng, nhưng phải đọc lại cho chính xác.

| Hạng mục | Kết quả audit |
|---|---|
| Bảng chính | **ĐÚNG.** Claude chạy lại, khớp từng chữ số; nhóm 7 = 3343 / 3329 / −2,50% / −0,52% / [−1,13%, +0,01%] / −1,29% / −2,05% |
| Ba truy vấn SQL kiểm chéo | **ĐÚNG và CHẠY ĐƯỢC.** 2.042.621 nến, 2016-01-04 → 2022-12-30, 1.468 mã — khớp cả ba, và lần này dùng `AT TIME ZONE` đúng |
| Bảng không loại 246 mã | **ĐÚNG.** 3436 / 3422 / −2,54% / −0,60% / [−1,20%, −0,08%] — khớp file output |
| Giữ niêm phong | **ĐÚNG.** `READ_TO` giữ nguyên, gọi `validate_sealed_bars` |
| Không sửa `screen_vcp_daily.py` | **ĐÚNG.** `git status` chỉ có file mới |
| Kỷ luật cổng | **ĐÚNG.** Chỉ một phép gated; mọi thứ khác ghi "Thứ cấp (N/A)", không gọi là đạt |
| Khai báo nợ kỹ thuật §1.1 | **ĐÚNG, và có giá trị.** Xác nhận cả 22 hàm import được mà không cần sửa một dòng |
| Tự khai test yếu | **ĐÚNG và đáng ghi nhận.** Phép phá thử 3 lần đầu yếu, agent tự nói ra rồi siết lại — đúng điều brief đòi |
| **Rổ đối chứng** | **SAI MỤC ĐÍCH — lỗi brief Claude.** Xem §A.2 |
| **Cổng trộn trung vị và trung bình** | **SAI — lỗi brief Claude.** Xem §A.3 |
| **Ba ô trong bảng §4** | **SỐ SAI.** Xem §A.4 |

## A.2. Lỗi nặng nhất: rổ đối chứng là chính nhóm 7/7, không phải thị trường

Agent **đã tự phát hiện và báo** điều này ở §7.1, và Claude xác nhận bằng cách đọc code. `compact_control_series` trong `screen_vcp_daily.py`:

```python
for i in range(n):
    days[i] = bar_date(sd.bars[i]).toordinal()
    if not (sd.trend_ok(i) and sd.liq_ok(i)):
        continue          # <-- chi ma DAT CA BAY dieu kien moi vao ro doi chung
```

`sd.trend_ok(i)` là `trend_filter_ok`, tức **cả bảy điều kiện đều đạt**. Vậy rổ đối chứng cùng ngày gồm **những mã đang ở 7/7** cộng thanh khoản cộng vào lệnh được.

**Hệ quả, và đây là chỗ brief Claude sai:**

1. Phép gated **không** trả lời "7/7 có thắng thị trường không". Nó trả lời: *"một mã **vừa chuyển** vào 7/7 có thắng rổ những mã **đã ở** 7/7 không"*. Câu này hẹp hơn rất nhiều, và số 0 là giá trị kỳ vọng tự nhiên của nó.
2. **Bảng đơn điệu không đọc được như một phát biểu về sức dự báo của điểm.** Mọi nhóm điểm 0…7 đều được trừ đi **cùng một** rổ 7/7 của ngày đó. Nên "điểm càng cao càng âm" không có nghĩa là điểm cao thì xấu — nó chỉ là khoảng cách tới một mốc cố định, và khoảng cách đó nằm gọn trong dải hẹp −1,67% đến −2,50% cho **tất cả** tám nhóm.
3. Đọc cho đúng, dữ liệu đang nói: **mọi nhóm điểm, kể cả nhóm vừa đạt 7/7, đều kém hơn rổ 7/7 đang tồn tại khoảng 1,7–2,5% trung vị sau 20 phiên.** Tức mốc 7/7-đã-thiết-lập là mốc khó vượt. Đó là điều **trái ngược** với kết luận số 2 của báo cáo, và nó cũng **chưa** phải bằng chứng rằng 7/7 thắng thị trường — vì thị trường chưa bao giờ được dùng làm mốc.

**Vì sao brief Claude sai:** brief §1 viết `basket_baseline`, `excess_for_event` là *"đối chứng cùng ngày — trái tim của phép đo"* và bắt import nguyên. Claude không mở `compact_control_series` để xem **rổ đó chứa những mã nào**. Với đợt 99 rổ đó là đúng: câu hỏi ở đó là "nến phá vỡ VCP có thêm gì so với việc đã ở trong xu hướng", nên lấy rổ trong-xu-hướng làm mốc là hợp lý. Đem nguyên sang câu hỏi về **điểm** thì mốc thành sai.

Đây là **cùng một lớp lỗi với đợt 118**: ở đó Claude lấy mẫu số 27 năm cho một tử số 12 tháng; ở đây Claude lấy mốc "đã 7/7" cho câu hỏi "7/7 có tốt không". Cả hai lần đều là **chưa kiểm định nghĩa của cái mốc trước khi dùng nó**.

**Không sửa ở đợt này.** Đổi rổ đối chứng là **một phép đo mới**, phải tiền đăng ký lại, không được thay mốc sau khi đã thấy số. Ghi thành brief kế tiếp ở §A.6.

## A.3. Cổng của brief trộn trung vị với trung bình

Brief §3 đặt điều kiện 1 là *"**trung vị** lợi suất vượt trội tại K = 20 > 0"*, còn điều kiện 3 và 4 dựa vào `bootstrap_by_month`, mà hàm đó bootstrap **trung bình**:

```python
mean_obs = sum(all_vals) / len(all_vals)
...
p = sum(1 for m in means if m <= 0.0) / len(means)
```

Nên KTC [−1,13%, +0,01%] và p = 0,9715 là về **trung bình** (−0,52%, nằm trong KTC ✓), trong khi điều kiện 1 xét **trung vị** (−2,50%, nằm ngoài KTC). Đọc bảng mà không biết điều này sẽ thấy "trung vị nằm ngoài khoảng tin cậy của chính nó" và tưởng có lỗi tính toán.

Lần này **không đổi kết luận** vì cả trung vị (−2,50%) và trung bình (−0,52%) đều âm và p = 0,97. Nhưng đây là lỗi đặc tả của Claude, và là lần thứ tư trong hai ngày Claude trộn hai đại lượng khác định nghĩa. Brief sau phải nói rõ **một** thống kê cho cả bốn điều kiện.

## A.4. Ba ô số sai trong bảng §4 của báo cáo

| Ô | Báo cáo ghi | File output thật |
|---|---|---|
| Số mã hợp lệ, có loại | 1.139 | **1.187** |
| Số mã hợp lệ, không loại | 1.369 | **1.428** |
| Chênh lệch | −230 | **−241** |

(Claude sửa ba ô sai trong §4 bằng một phép thay thế toàn cục, và nó thay luôn cả cột
"Báo cáo ghi" của chính bảng này. Đã dựng lại bằng tay. Bài học nhỏ: sửa số trong một
tài liệu mà chính tài liệu đó đang trích dẫn con số sai thì không dùng được thay thế
toàn cục.)

Mọi ô khác trong bảng §4 (3.436 / 3.422 / −2,54% / −0,60% / KTC / p) Claude kiểm đều **đúng**. Ba ô này là lỗi chép tay, không phải lỗi tính. **Đã sửa** trong báo cáo.

## A.5. Điều Claude chưa kiểm

- **Phép phá thử 2, 3, 4, 5:** Claude **chưa tự tái lập**. Riêng phép 1 thì bằng chứng agent đưa ra là `IndexError: list index out of range` — nó **làm test đỏ**, nhưng đỏ vì sập chứ không vì một khẳng định về giá trị. Yếu hơn bốn phép còn lại; đáng siết lại thành một phép so sánh giá trị ở đợt sau.
- **Bảng biến thể sự kiện §5** và **bảng tách RS §3**: chỉ xác minh dòng "Tất cả 7/7" khớp. Các dòng khác chưa tính lại độc lập.
- **`p-value` và bootstrap 2.000 lượt:** tái lập được khi chạy lại cùng seed 42, nhưng đó là tính tất định, không phải tính đúng.
- **Nhận định về `pathlib.Path("").exists()` trả True trên Windows** (§7.2): hợp lý, Claude không kiểm lại.
- Một lần nữa Claude tự sập bẫy: dùng `>` của PowerShell để hứng output nên file bị ghi UTF-16, làm phép so sánh đầu tiên báo "khác hoàn toàn" một cách giả. Đã ghi trong `dev-env-gotchas` mà vẫn mắc. Kiểm lại bằng `Get-Content -Encoding utf8` thì khớp.

## A.6. Việc phải làm tiếp, theo thứ tự

1. **Đo lại với mốc trung tính** (brief kế tiếp, phải tiền đăng ký): rổ đối chứng là **toàn bộ mã đủ thanh khoản và vào lệnh được trong ngày đó**, bỏ điều kiện `trend_ok`. Chỉ khi đó mới trả lời được "điểm SEPA có dự báo được lợi suất so với thị trường không". Việc này cần một hàm dựng rổ mới, và vì `compact_control_series` nằm trong `screen_vcp_daily.py` đang bị bốn script dùng, **nên làm sau khi trả nợ kỹ thuật §1.1**, không phải trước.
2. **Trả nợ kỹ thuật §1.1** — dời các hàm thuần sang `trading/`, chốt bằng việc `screen_vcp_daily.py` cho ra y nguyên số của đợt 99.
3. Câu hỏi còn treo về vũ trụ xếp hạng RS trong `score_sepa_daily.py`.

## A.7. Kết luận đúng của đợt 120, phát biểu lại

- **Có bằng chứng:** một mã **vừa chuyển** vào 7/7 **không** thắng được rổ các mã **đã ở** 7/7 cùng ngày, ở K = 20. Trung vị −2,50%, trung bình −0,52%, KTC chứa 0, p = 0,97. **Không đạt cổng.** Kết luận này vững, và không đổi khi loại 246 mã dữ liệu không tin cậy.
- **CHƯA có bằng chứng, trái với những gì báo cáo viết:** điểm SEPA 0–7 có hay không có sức dự báo **so với thị trường**. Phép đo này không có mốc trung tính nên không trả lời được.
- Đây vẫn là **phép đo âm thứ mười hai**, nhưng là âm cho một câu hẹp, không phải âm cho câu "bảng điểm SEPA có ích không".

## A.8. Phát hiện về rổ đối chứng lan tới đâu — và rổ trung tính ĐÃ CÓ SẴN

Claude soát tiếp: nếu rổ lọc theo `trend_ok` làm sai một phép đo, nó có làm sai các đợt đo khác không?

**Không. Chỉ hai đợt dùng rổ đó:**

| Script | Đợt | Dùng `compact_control_series` / `excess_for_event`? |
|---|---|---|
| `screen_vcp_daily.py` | 99 | **Có** — và ở đó mốc **đúng**: câu hỏi là "phá vỡ VCP có thêm gì so với việc đã ở trong xu hướng" |
| `measure_sepa_score_edge.py` | 120 | **Có** — và ở đây mốc **sai mục đích**, xem §A.2 |
| `screen_smc_stock_daily.py` | 101 | Không — tự dựng rổ riêng |
| `screen_momentum_portfolio.py` | — | Không |

Nên **kết luận âm của đợt 99 và đợt 101 không bị ảnh hưởng.** Chỉ đợt 120 phải đọc lại.

**Và đây là phần có giá trị nhất của lần soát này: rổ trung tính mà §A.6 cần đã tồn tại trong `screen_smc_stock_daily.py`.**

```python
def make_basket_entry(symbol, bars, i, exchange, min_turnover=MIN_TURNOVER_VND, ks=TARGET_KS):
    """None neu ma nay khong duoc vao ro (duoi thanh khoan, khong vao duoc lenh, khong co du lieu)."""

def basket_for_day(entries, event_symbol):
    """Ro doi chung cua mot ngay: moi ma khac ma su kien (KHONG gom chinh ma su kien)."""
```

`make_basket_entry` loại một mã **chỉ khi**: dưới thanh khoán, không vào được lệnh, hoặc không có dữ liệu kỳ hạn. **Không có điều kiện `trend_ok`.** Đó đúng là mốc trung tính: mọi mã đủ thanh khoản và vào lệnh được trong ngày đó.

Vậy brief đo lại ở §A.6 **không phải viết hàm dựng rổ mới** — phải **dùng lại** `make_basket_entry` và `basket_for_day`. Điều này đổi hẳn hình dạng brief đó: từ "viết mốc mới" thành "đổi nguồn rổ", nhỏ hơn nhiều và ít chỗ sai hơn.

**Thêm một cặp trùng lặp cụ thể cho đợt trả nợ kỹ thuật §1.1:**

| Trong `screen_vcp_daily.py` | Trong `screen_smc_stock_daily.py` | Ghi chú |
|---|---|---|
| `basket_baseline` | `baseline_for_basket` | cùng logic, cùng `MIN_CONTROL = 5` |
| `excess_for_event` | `excess_k` | cùng logic |

Hai cặp hàm này làm đúng một việc với hai cái tên. Đợt trả nợ nên gộp chúng, và **giữ ngữ nghĩa rổ ở phía người gọi** — vì chính việc rổ được quyết định bên trong `compact_control_series` (chứ không phải ở chỗ gọi) là nguyên nhân Claude không thấy nó khi viết brief 120.

**Một chi tiết đã kiểm và không có vấn đề:** cả hai đường đi đều loại mã sự kiện ra khỏi rổ của chính nó (`peers = [c for c in ... if c.symbol != e.symbol]`), nên không có thiên lệch tự-đưa-mình-vào-mốc.

