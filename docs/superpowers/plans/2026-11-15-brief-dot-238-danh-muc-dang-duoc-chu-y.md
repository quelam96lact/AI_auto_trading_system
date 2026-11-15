# Brief đợt 238: danh mục "đang được chú ý" (abnormal turnover cao), xoay vòng tháng (ĐĂNG KÝ TRƯỚC)

- **Ngày:** 15/11/2026.
- **Spec:** dòng H ngày 15/11/2026 (đợt 238). Giả thuyết thứ 4 của tháng 11, **vượt ngân sách mục F**, chủ dự án cho phép.
- **Khuôn:** đợt 237 (`docs/superpowers/plans/2026-11-15-brief-dot-237-danh-muc-it-duoc-chu-y.md`). **Mọi luật giữ đúng như brief 237**, trừ các điểm nêu ở §1. Vai trò, điều cấm và niêm phong như brief 237.
- **Builder KHÔNG được:** commit/push; truy vấn DB; gọi API; đọc file bí mật; mở dữ liệu ngoài `data/research227/explore/`; `sched.sh`; docker; `npx`; `taskkill` theo tên; thêm ý tưởng, bộ lọc hay cấu hình.

## 0. Giả thuyết

Đợt 237 cho 9/9 cấu hình "ít được chú ý" **thua** EW có ý nghĩa trên EA. Đợt này đo chiều ngược: giữ `N` mã có `AT_S` **cao nhất**.

- **EA đã nhiễm.** Kết quả chiều ngược trên EA đã thấy. EA của đợt này chỉ để chọn cấu hình và kiểm cao nguyên. Bằng chứng là EB (2020–2022, chưa chạy cho chiều nào), rồi V1 và V2 do Lead chạy.
- **Ước lượng trước của Lead:** EA sẽ dương (gần như biết trước). Khả năng qua EB là thấp: mã nóng đổi nhanh (phí cao) và thường sụt mạnh năm 2022 (cổng MDD ≤ 28,19%). **0 ứng viên là kết quả hợp lệ.**
- Báo cáo ghi các cảnh báo: giả thuyết sinh sau khi xem dữ liệu, đa so sánh, trái chiều với đợt 227, thiên lệch sống sót.

## 1. Khác brief 237

1. **Chọn mã:** `AT_S` tính đúng như 237 §3.3 (cùng universe §3.2). Giữ `N` mã có `AT_S` **cao nhất**; hoà điểm xếp mã A→Z.
2. `idea_id = "I1_HIGHATTN"`; thư mục `docs/research/dot238/` (`trial_ledger.csv`, `exploration_report.md`, `candidates.json`, `selections.json` cùng định dạng 237, khoá `"S20_N10"` … và `"EB_S.._N.."`).
3. **DSR:** `n_trials = 9 + 9 + 30` (`MIRROR_TRIALS = 9`, `PRIOR_NEGATIVE_FAMILIES = 30`); `sr_trials_var` = phương sai `sharpe_X` của 9 dòng EA đợt này.
4. `calculate_rotation_metrics(seed=238)`.
5. Báo cáo in thêm **turnover tháng TB và phí theo năm** cạnh số của đợt 237 nếu có sẵn trong `docs/research/dot237/exploration_report.md` (chỉ chép số, không chạy lại 237).

Giữ nguyên: dữ liệu, loại chứng chỉ quỹ, Bước 0 (56, 58, 85, 166, 136), lưới, EA/EB, cao nguyên, cổng EB (`mean_X > 0`, p < 0,05; MDD ≤ 28,19%; CAGR ≥ 4,50%; số mã giữ TB ≥ 0,8 × N), tối đa 1 ứng viên, cấm chạy EB lần hai.

## 2. Phạm vi file

- **Tạo mới:** `scripts/research238_core.py` (hàm chọn mã `select_highattn_symbols`), `scripts/research238_explore.py`, `scripts/research238_validate.py`, `tests/test_research238_*.py`, `docs/research/dot238/`.
- **Dùng lại bằng import** từ `scripts/research237_core.py` và `scripts/research237_explore.py` (universe, `AT`, `select_best_ea_config`, `check_plateau`, `check_eb_gates`, …). Nếu một hàm của 237 thiếu tham số để dùng lại (ví dụ `n_trials`, đường dẫn sổ, `idea_id`, chiều xếp hạng), được **thêm tham số tuỳ chọn có mặc định giữ nguyên hành vi cũ**; không sửa gì khác trong file 237. Toàn bộ test 237 và 193 phải vẫn xanh. Liệt kê từng chỗ đã sửa trong báo cáo. Không chép-dán hàm rồi sửa.
- Không sửa `docs/research/dot237/`, không chạy lại khám phá 237.

## 3. Test (TDD)

Phép phá, mỗi phép làm đỏ một test gọi đúng hàm sản phẩm (sao lưu ngoài repo, cấm `git checkout/restore/stash`):

| # | Phép phá | Hàm |
|---|---|---|
| a | Giữ `N` mã `AT` **thấp** nhất | `select_highattn_symbols` |
| b | Điểm tính tới hết `r` thay vì `r⁻` | `select_highattn_symbols` |
| c | Bỏ `is_liquid` hoặc yêu cầu 250 nến | `select_highattn_symbols` |
| d | Hoà điểm không theo A→Z | `select_highattn_symbols` |
| e | Không loại chứng chỉ quỹ | đường chọn mã của 238 |
| f | DSR dùng `n_trials` thiếu `+ 9` hoặc `+ 30` | hàm Bước 4 của 238, so với lời gọi `deflated_sharpe` viết trực tiếp trong test |
| g | `run_exploration` của 238 ghi vào sổ `dot237`, hoặc bỏ `assert_ledger_safety` | `run_exploration` với sổ trong `tmp_path` |
| h | Cổng EB bỏ một trong bốn điều kiện | hàm cổng EB được 238 gọi |

`research238_validate.py`: CLI như 237; test sha sai → 2, chuỗi mà mã `AT` cao lãi đều → ĐẠT, lỗ đều → TRƯỢT.

## 4. Tiêu chí hoàn thành (dán output thật)

1. Danh sách chỗ đã sửa trong file 237 (diff), impact/grep trước khi sửa.
2. `uv run pytest tests/test_research238_core.py tests/test_research238_validate.py tests/test_research237_core.py tests/test_research237_validate.py tests/test_research193_core.py tests/test_research193_validate.py -q`; bảng phá a–h với dòng `FAILED` nguyên văn.
3. `uv run ruff check scripts tests`; `uv run pytest -m "not integration" -q`.
4. Bước 0 khớp 5 mốc.
5. Lệnh chạy khám phá (một lần) và output nguyên văn.
6. `detect-changes --scope all`; `git status --short`; `git diff --stat`.
7. Một câu: "Tôi không truy vấn DB và không mở file dữ liệu nào ngoài `data/research227/explore/`."
8. Mọi chỗ brief mơ hồ mà Builder phải tự diễn giải.
