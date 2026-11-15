# Brief đợt 240: đảo chiều ngắn hạn, xoay vòng tháng (ĐĂNG KÝ TRƯỚC)

- **Ngày:** 15/11/2026.
- **Spec:** dòng H ngày 15/11/2026 (đợt 240). Giả thuyết thứ 5 của tháng 11, **vượt ngân sách mục F**, chủ dự án cho làm tiếp.
- **Khuôn:** đợt 237 (`docs/superpowers/plans/2026-11-15-brief-dot-237-danh-muc-it-duoc-chu-y.md`) và đợt 238 (cách dùng lại code 237). **Mọi luật giữ đúng như brief 237**, trừ những điểm ở §1. Vai trò, điều cấm, niêm phong như brief 237.
- **Builder KHÔNG được:** commit/push; truy vấn DB; gọi API; đọc file bí mật; mở dữ liệu ngoài `data/research227/explore/`; `sched.sh`; docker; `npx`; `taskkill` theo tên; thêm ý tưởng, bộ lọc hay cấu hình; chạy lại khám phá 237/238; sửa `docs/research/dot237/`, `docs/research/dot238/`.

## 0. Giả thuyết

- **Cơ chế:** nhà đầu tư cá nhân phản ứng thái quá với tin ngắn hạn; mã vừa giảm mạnh trong vài tuần có xu hướng hồi lại trong tháng sau (đảo chiều ngắn hạn).
- **Một ý tưởng `I1_REV`, 9 cấu hình.** Chỉ mua, không học máy, không đòn bẩy.
- **Ước lượng trước của Lead:** khả năng qua đủ cổng là thấp (turnover cao, phí cao; 31 phép đo âm trước). **0 ứng viên là kết quả hợp lệ.**
- Báo cáo ghi cảnh báo: giả thuyết thứ 5 trong tháng (đa so sánh), thiên lệch sống sót **có lợi** cho chiến lược này, gần họ momentum (đợt 102, chân trời khác).

## 1. Khác brief 237

1. **Điểm:** tại `r⁻` (phiên trước `r` trong `S`), với `t` = chỉ số nến `r⁻` của mã: `RET_S = close[t] / close[t − S] − 1` (nến của chính mã). Universe đúng như 237 §3.2 (không phải chứng chỉ quỹ, có nến ở `r⁻`, GTGD20 ≥ 1 tỷ tại `r⁻`, `t ≥ 249`); `close[t − S] <= 0` thì loại mã.
2. **Chọn:** giữ `N` mã có `RET_S` **thấp nhất**; hoà điểm A→Z.
3. **Lưới:** `S ∈ {5, 10, 20}` × `N ∈ {10, 15, 20}`. Láng giềng cao nguyên theo thứ tự lưới (5↔10↔20; 10↔15↔20).
4. `idea_id = "I1_REV"`; thư mục `docs/research/dot240/` (`trial_ledger.csv`, `exploration_report.md`, `candidates.json`, `selections.json` cùng định dạng 237/238, khoá EA `"S5_N10"` … và EB `"EB_S.._N.."`).
5. **DSR:** `n_trials = 9 + 31` (`PRIOR_NEGATIVE_FAMILIES = 31`).
6. `calculate_rotation_metrics(seed=240)`.
7. Báo cáo in turnover tháng TB và phí theo năm cho mọi dòng, kèm số của đợt 238 chép từ `docs/research/dot238/exploration_report.md` để so.

Giữ nguyên: dữ liệu, loại chứng chỉ quỹ, Bước 0 (56, 58, 85, 166, 136), EA `L(01/2017)→L(12/2019)`, EB `L(12/2019)→L(12/2022)`, chọn cấu hình theo `sharpe_X`, cao nguyên, cổng EB (`mean_X > 0` và p < 0,05; MDD ≤ 28,19%; CAGR ≥ 4,50%; số mã giữ TB ≥ 0,8 × N), tối đa 1 ứng viên, cấm chạy EB lần hai.

## 2. Phạm vi file

- **Tạo mới:** `scripts/research240_core.py` (hàm `select_reversal_symbols`), `scripts/research240_explore.py`, `scripts/research240_validate.py`, `tests/test_research240_*.py`, `docs/research/dot240/`.
- **Dùng lại bằng import** từ `scripts/research237_core.py`, `scripts/research237_explore.py`, `scripts/research237_validate.py` (universe, `run_exploration` qua các tham số `select_symbols_fn`, `dsr_fn`, `idea_id`, `seed`… đã thêm ở đợt 238). Nếu còn thiếu tham số thì được **thêm tham số tuỳ chọn có mặc định giữ hành vi cũ**, liệt kê diff; không sửa gì khác. Test 193/237/238 phải vẫn xanh. Không chép-dán hàm rồi sửa.

## 3. Test (TDD)

Phép phá, mỗi phép làm đỏ một test gọi đúng hàm sản phẩm (sao lưu ngoài repo, cấm `git checkout/restore/stash`):

| # | Phép phá | Hàm |
|---|---|---|
| a | Giữ `N` mã `RET_S` **cao** nhất | `select_reversal_symbols` |
| b | `RET_S` tính tới hết `r` thay vì `r⁻` | `select_reversal_symbols` |
| c | `RET_S` lệch một nến (dùng `t − S + 1` hoặc `t − S − 1`), so số **tính tay** | `select_reversal_symbols` |
| d | Bỏ `is_liquid`, hoặc bỏ/lệch yêu cầu 250 nến | `select_reversal_symbols` |
| e | Không loại chứng chỉ quỹ | đường chọn mã của 240 |
| f | Hoà điểm không theo A→Z | `select_reversal_symbols` |
| g | DSR dùng `n_trials` khác `9 + 31` | hàm Bước 4 của 240, so với lời gọi `deflated_sharpe` viết trực tiếp trong test |
| h | `run_exploration` của 240 ghi vào sổ của đợt khác, hoặc bỏ `assert_ledger_safety` | `run_exploration` với sổ trong `tmp_path` |

`research240_validate.py`: CLI như 237/238; test sha sai → 2; chuỗi mà mã giảm mạnh hồi lại đều → ĐẠT; mã giảm mạnh tiếp tục giảm → TRƯỢT.

## 4. Tiêu chí hoàn thành (dán output thật)

1. Diff các chỗ sửa trong file 237 (nếu có), impact/grep trước khi sửa.
2. `uv run pytest` cho test 240, 238, 237, 193; bảng phá a–h với dòng `FAILED` nguyên văn.
3. `uv run ruff check scripts tests`; `uv run pytest -m "not integration" -q`.
4. Bước 0 khớp 5 mốc.
5. Lệnh chạy khám phá (một lần) và output nguyên văn.
6. `detect-changes --scope all`; `git status --short`; `git diff --stat`.
7. Một câu: "Tôi không truy vấn DB và không mở file dữ liệu nào ngoài `data/research227/explore/`."
8. Mọi chỗ brief mơ hồ mà Builder phải tự diễn giải.
