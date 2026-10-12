# Brief đợt 187: E2/E3 order flow VN30F với ngưỡng tương đối, đo trên DNSE (ĐĂNG KÝ TRƯỚC)

- Ngày: 12/10/2026.
- Claude: giao việc, audit, commit, push, **chạy phép đo**. Agent khác: thực thi.
- Agent **KHÔNG** commit, **KHÔNG** push, **KHÔNG** gọi API DNSE, **KHÔNG** đọc `.env`, **KHÔNG** mở `data/dnse_trades/` hay `data/orderbook/`.
- Nền: commit sau `f81567c`.

## 0. Bối cảnh và cách hiểu

**Kết quả đợt 186 (12/10, `docs/research/2026-10-dot-186-ket-qua-order-flow-vn30f-dnse.md`):**
- **E1:** đủ mẫu và âm (102/75 sự kiện, trung bình y −0,20/−0,17 điểm).
- **E2 và E3:** chỉ 4–5 sự kiện trong 67 phiên, nên **không đo được**.

**Nguyên nhân, Claude đếm đặc trưng trên tập CHÍNH (không tính mục tiêu):**
- **E3:** min_vol tuyệt đối 5 hợp đồng, trong khi một nến có khoảng 3.500 hợp đồng. Vì vậy 97,9% số nến có imbalance cả hai phía, và điều kiện "không có imbalance phía ngược" gần như không bao giờ đúng. Đây đúng là lỗi của đợt 183 bên crypto (memory `nguong-tuyet-doi-phai-kiem-do-pho-bien`).
- **E2:** delta và thân nến cùng dấu rất chặt (ρ = 0,83). Ở nhóm |delta| ≥ p90 gần như không còn nến nào lệch dấu: 0,08 sự kiện mỗi phiên.

**Phép thử:** đúng ý tưởng của E2 và E3 trong 182 v2, chỉ đổi **ngưỡng sang dạng tương đối**. Ngưỡng được chọn theo **tần suất sự kiện** bằng quy tắc ghi dưới đây, Claude đã đếm xong trước khi viết brief. Đo trên đúng hai cửa sổ của 186. E1 không đo lại.

**Cái đã thấy và cái chưa thấy:**
- Đã thấy: kết quả của E1, và 9 sự kiện E2/E3 theo định nghĩa cũ.
- Chưa thấy: mục tiêu y của mọi sự kiện E2/E3 theo định nghĩa mới.
- Claude chỉ đếm số sự kiện và tỷ lệ imbalance, không tính y.

**Ngân sách:** đây là giả thuyết thứ 11 của tháng 10, vượt ngân sách mục F. Đã ghi spec H ngày 12/10.

**Không có đường tới lệnh thật.**

## 1. Thiết kế đo (khoá trước)

### 1.1 Dữ liệu, cửa sổ, phiên hợp lệ
Giữ y nguyên đợt 186:
- CHÍNH 25/03 → 30/06/2026; LẶP LẠI 01/07 → 24/09/2026.
- Loader `load_dnse_sessions`, quy tắc hợp lệ §1.2 của 186.
- Không bao giờ mở file có ngày ≥ 25/09.
- Cần ≥ 40 phiên CHÍNH và ≥ 30 phiên LẶP LẠI, thiếu thì `return 3`.

### 1.2 Ngưỡng mới (chốt số)

**E3:**
- Imbalance theo ngưỡng tương đối kiểu 183b, tính riêng cho mỗi phiên D từ **5 phiên hợp lệ liền trước**.
- **min_vol(D) = p95** và **denom_floor(D) = p50** của pool. Pool gồm mọi giá trị `buy > 0` và `sell > 0` ở mọi mức giá trong `fp` của mọi nến thuộc 5 phiên đó.
- `ratio = 3,0`, so chéo như `imbalance_levels` của 182.
- 5 phiên đầu tiên (theo thứ tự thời gian trên toàn bộ phiên hợp lệ CHÍNH + LẶP LẠI) không có ngưỡng: imbalance = None.
- Sau đó gọi nguyên `detect_e3_events` của 182.

**E2:**
- Sự kiện khi |delta| ≥ **p25** của |delta| mọi nến có giá trong 5 phiên hợp lệ liền trước.
- Điều kiện còn lại giữ nguyên 182: delta > 0 và close < open ⇒ +1; delta < 0 và close > open ⇒ −1; close == open thì bỏ.

**Quy tắc đã dùng để chọn số** (ghi lại để kiểm, agent **không** chạy lại):

| Ngưỡng | Lưới | Quy tắc | Kết quả đếm của Claude trên CHÍNH |
|---|---|---|---|
| E3 min_vol | p90 / 95 / 97,5 / 99 | mức thấp nhất có tỷ lệ nến imbalance cả hai phía ≤ 50% | p90: 53,0%; **p95: 33,4%**, 118/109 sự kiện không chồng lấn ở H15/H30 |
| E2 \|delta\| | p90 / 75 / 50 / 25 | mức cao nhất có ≥ 100 sự kiện không chồng lấn ở H30 | p50: 74; **p25: 174** |

**Chặn suy biến:** công cụ in tỷ lệ nến có imbalance cả hai phía trên CHÍNH, bỏ 5 phiên khởi động. Nếu tỷ lệ này > 50% thì **E3 bị loại**, Bonferroni giữ 0,05/4.

### 1.3 Thống kê và phán quyết
Giống 186 §1.4, chỉ khác số cặp:
- 4 cặp: E2_H15, E2_H30, E3_H15, E3_H30.
- **Đối chứng:** ρ > 0,3 trên nến CHÍNH, không đạt thì `return 4`.
- **Hurdle:** `compute_economic_hurdle(trung vị close CHÍNH)`, dùng cùng một hurdle cho LẶP LẠI.
- **CHÍNH:** `evaluate_pair_criteria(..., alpha_threshold=0.05/4)`, mặc định của 182 là ≥ 100 sự kiện và mỗi hướng ≥ 30.
- **LẶP LẠI:** chỉ xét k cặp đã ĐẠT ở CHÍNH, dùng `evaluate_repeat_pair` của 186 (p < 0,05/k và trung bình y ≥ hurdle CHÍNH).
- **Phát hiện sự kiện một lần** trên toàn bộ nến hợp lệ CHÍNH + LẶP LẠI, rồi chia theo `session_id`, như 186.
- **Dự đoán ghi trước:** không cặp nào ĐẠT.

## 2. Việc agent làm

### 2.1 File mới `scripts/screen_vn30f_orderflow_dnse_187.py`
- **Import, không chép:**
  - Từ `scripts.screen_vn30f_orderflow_dnse` (186): `load_dnse_sessions`, `evaluate_repeat_pair`, `MAIN_START`, `MAIN_END`, `REPEAT_START`, `REPEAT_END`, `MIN_MAIN_SESSIONS`, `MIN_REPEAT_SESSIONS`.
  - Từ `scripts.screen_vn30f_orderflow` (182): `imbalance_levels`, `calculate_percentile`, `detect_e3_events`, `calculate_event_targets`, `filter_non_overlapping_events`, `block_bootstrap_p_value` (n_bootstrap=2000, seed=42), `check_control_variable_orderflow`, `compute_economic_hurdle`, `evaluate_pair_criteria`, `OrderFlowEvent`.
- **Hằng mới, chỉ những hằng này:** `E3_MIN_VOL_PCT = 95.0`, `E3_DENOM_FLOOR_PCT = 50.0`, `E2_DELTA_PCT = 25.0`, `ALPHA_MAIN = 0.05 / 4`, `MAX_BOTH_SIDES_SHARE = 0.5`, `WARMUP_SESSIONS = 5`.
- **`apply_relative_imbalance_pct(bars, min_vol_pct, floor_pct) -> None`:**
  - Ghi đè `ask_k_min/ask_k_max/bid_k_min/bid_k_max` của từng nến theo §1.2.
  - Logic **giống hệt** `apply_relative_imbalance` của `scripts/screen_crypto_orderflow.py`, chỉ thêm tham số phân vị. Xem test 2.
- **`detect_e2_events_pct(bars, pct) -> list[OrderFlowEvent]`:** giống hệt `detect_e2_events` của 182, thay hằng p90 bằng `pct`. Xem test 3.
- **`both_sides_share(bars, skip_sessions) -> float`:** tỷ lệ nến có giá mà có cả `ask_k_min` lẫn `bid_k_min`, bỏ các phiên trong `skip_sessions`.
- **`run_187(data_dir) -> dict` và `main(args) -> int`**, theo đúng thứ tự:
  1. In số phiên hợp lệ / không hợp lệ, kèm lý do.
  2. Kiểm đối chứng.
  3. Tính hurdle.
  4. Áp imbalance tương đối trên toàn bộ nến hợp lệ CHÍNH + LẶP LẠI.
  5. In `both_sides_share` của CHÍNH, bỏ 5 phiên khởi động; > 50% thì loại E3.
  6. Phát hiện E2/E3.
  7. In bảng CHÍNH (4 cặp), rồi bảng LẶP LẠI (hoặc `LẶP LẠI: không có cặp nào để kiểm`), rồi phán quyết.
  - Mã thoát: 0 / 3 / 4 như 186.
- **Không có cờ phá trong code sản phẩm** (không tham số kiểu `reverse_direction`, `include_current_session`).

### 2.2 Không được sửa
- `scripts/screen_vn30f_orderflow.py`, `scripts/screen_vn30f_orderflow_dnse.py`, `scripts/screen_crypto_orderflow.py`, `scripts/fetch_dnse_vn30f_trades.py`, `scripts/screen_vn30f_orderbook.py`.
- Mọi file trong `trading/`.
- Mọi test hiện có, kể cả 2 test audit `test_4b_*` và `test_11b_*` của đợt 186.

Cần sửa một trong số đó thì **dừng và báo**.

## 3. Test bắt buộc (viết đỏ trước) trong `tests/test_screen_vn30f_orderflow_dnse_187.py`
Chỉ dùng `tmp_path` và nến dựng tay. Có thể import helper dựng phiên DNSE giả từ test 186, nhưng không sửa file test đó.

| # | Kiểm |
|---|---|
| 1 | Hằng mới đúng giá trị §2.1 |
| 2 | Trên cùng một bộ nến có `fp`, `apply_relative_imbalance_pct(bars, 90.0, 50.0)` cho ra `ask_k_min/ask_k_max/bid_k_min/bid_k_max` **trùng từng nến** với `apply_relative_imbalance` của crypto. Với 95.0 thì có ít nhất một nến khác |
| 3 | `detect_e2_events_pct(bars, 90.0)` trùng từng sự kiện (session_id, bar_idx, direction) với `detect_e2_events(bars)` của 182. Với 25.0 thì ra nhiều sự kiện hơn |
| 4 | Ngưỡng chỉ lấy từ 5 phiên **trước**: đổi `fp` hoặc delta của phiên hiện tại thành cực lớn thì ngưỡng của chính phiên đó không đổi |
| 5 | 5 phiên khởi động: không có imbalance, không có E2 |
| 6 | `both_sides_share`: bộ nến dựng tay 3/4 nến có cả hai phía ⇒ 0,75; bỏ phiên khởi động thì mẫu số đúng |
| 7 | Chặn suy biến: dữ liệu giả có tỷ lệ cả hai phía > 50% ⇒ bảng CHÍNH không có dòng E3, ngưỡng in ra vẫn là 0,05/4 |
| 8 | Ngưỡng CHÍNH là 0,05/4: một cặp giả có p = 0,02, đủ mẫu và đủ hurdle ⇒ TRƯỢT |
| 9 | Đầu-cuối: phiên giả CHÍNH + LẶP LẠI ⇒ `main()` trả 0, in đủ 4 cặp E2/E3 và **không có dòng E1**; spy `gzip.open` cho thấy không mở file ngày ≥ 2026-09-25 |
| 10 | Dùng lại: `mod.load_dnse_sessions is screen_vn30f_orderflow_dnse.load_dnse_sessions`, tương tự cho `evaluate_repeat_pair`, `detect_e3_events`, `evaluate_pair_criteria` |

## 4. Phép phá bắt buộc
| Phép phá | Test phải đỏ |
|---|---|
| (a) `E3_MIN_VOL_PCT = 90.0` | 1 |
| (b) pool imbalance gồm cả phiên hiện tại | 4 |
| (c) `detect_e2_events_pct` bỏ qua tham số `pct`, luôn dùng 90 | 3 |
| (d) bỏ bước loại E3 khi > 50% | 7 |
| (e) `ALPHA_MAIN = 0.05 / 6` | 8 (và 1) |
| (f) `denom_floor` lấy p90 thay vì p50 | 2 |
| (g) bỏ kiểm ngày ≥ 25/09: gọi loader với `end=2026-09-25` từ test 9 | 9 |

- Sao lưu ngoài repo, khôi phục bằng `cp`, so `sha256`.
- Cấm `git checkout/restore/stash`.

## 5. Cổng kiểm cuối
- **GitNexus** (`node .gitnexus/run.cjs …`, không dùng `npx`):
  - Trước khi viết: chạy `context` cho `apply_relative_imbalance`, `detect_e2_events`, `load_dnse_sessions`, `evaluate_repeat_pair`. Chỉ đọc.
  - Sau khi viết: `detect-changes --scope all`. Chỉ được có 1 script mới và 1 file test mới.
- `uv run pytest -m "not integration" -q` trước và sau; số test chỉ được tăng.
- `uv run ruff check trading tests scripts` phải sạch.

## 6. Sau khi audit (Claude làm)
1. Commit, push.
2. Chạy phép đo **một lần**: `uv run python scripts/screen_vn30f_orderflow_dnse_187.py --data-dir data/dnse_trades`. Lưu nguyên văn output vào `docs/research/2026-10-dot-187-ket-qua-e2-e3-vn30f-dnse.md`.
3. Kiểm tỷ lệ cả hai phía in ra có khớp 33,4% của §1.2 không. Lệch quá 0,5 điểm % nghĩa là cài đặt khác quy tắc: dừng, không phán quyết.
4. Phán quyết theo §1.3. Không đổi ngưỡng, hướng hay chân trời sau khi thấy số.

## 7. Bất biến
- **Không:** gọi API DNSE/SSI/BingX, đọc `.env`, mở/liệt kê/đếm `data/dnse_trades/` hay `data/orderbook/`.
- **Không:** commit, push, ghi DB, chạy `scripts/sched.sh`.
- **Không** in key/secret.
- Không xoá và không làm yếu test hiện có.

## 8. Báo cáo cho Claude
- pytest trước/sau, ruff, số test.
- Danh sách tên `def test_*` mới.
- Bảng phép phá (a)–(g) kèm sha256 sau khi khôi phục.
- Kết quả `context` và `detect-changes`.
- Mục "brief mơ hồ ở đâu".
- Câu chốt: *"Tôi chưa chạy phép đo trên dữ liệu thật."*
