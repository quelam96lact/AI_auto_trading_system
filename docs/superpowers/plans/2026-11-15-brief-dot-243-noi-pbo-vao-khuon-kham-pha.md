# Brief đợt 243: nối PBO (đợt 241) vào khuôn khám phá 237 + sổ đếm số lần thử

- **Ngày:** 15/11/2026. Chủ dự án hỏi "còn phần chiến lược giao dịch?" → Lead: chưa mở giả thuyết mới trong tháng 11 (đã vượt ngân sách, 32 phép đo âm); làm hạ tầng để mọi giả thuyết tháng 12 đo bằng PBO + DSR theo tổng số lần thử.
- **Hạ tầng, không phải giả thuyết.** Không chạy lại khám phá nào, không mở dữ liệu, không đổi cổng EB hiện có.
- **Builder KHÔNG:** commit/push, DB, API, docker, `sched.sh`, `npx`; sửa `docs/research/dot2*/`; chạy `run_exploration` thật.

## 1. Việc

1. **Sổ đếm:** tạo `scripts/trial_ledger.py` với `PRIOR_NEGATIVE_FAMILIES = 32` và docstring liệt kê nguồn (đợt 240 là phép đo âm thứ 32, xem `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`). **Không** sửa hằng cũ trong `research195_core.py`, `research227_core.py`, `research237_explore.py` (giữ tái lập lịch sử).
2. **PBO trong khuôn:** `scripts/research237_explore.py::run_exploration` thêm tham số tuỳ chọn `pbo_fn: Callable[[np.ndarray], float] | None = None` (mặc định `None` = hành vi cũ, báo cáo cũ không đổi byte nào).
   - Khi `pbo_fn` khác `None`: sau Bước 1 (EA), dựng ma trận T×N với cột = cấu hình theo thứ tự lưới, hàng = tháng EA, giá trị = `monthly_r − monthly_ew` của cấu hình đó; gọi `pbo_fn(matrix)`; ghi `pbo_ea` vào dict kết quả trả về và một dòng `PBO (EA, CSCV): x.xxx` vào báo cáo (qua `report_builder_fn`, tham số tuỳ chọn mặc định `None` → không in dòng).
   - PBO **chỉ báo cáo**, chưa là cổng (ngưỡng chờ chốt).
3. Hàm tiện ích `pbo_for_exploration(matrix) -> float` trong `scripts/trial_ledger.py`: `S` = số chẵn lớn nhất ≤ min(16, T // 2); gọi `overfit_core.pbo_cscv(matrix, n_splits=S).pbo`. T < 4 → `ValueError`.

## 2. Phạm vi file

- **Tạo:** `scripts/trial_ledger.py`, `tests/test_trial_ledger.py`.
- **Sửa:** `scripts/research237_explore.py` (chỉ thêm tham số tuỳ chọn + nhánh PBO), thêm test vào `tests/test_research237_*.py` hiện có hoặc file test mới. Không xoá/sửa test cũ.
- Không đụng `scripts/overfit_core.py` (đợt 241 đã đóng).

## 3. Tiêu chí hoàn thành

1. `gitnexus impact run_exploration --direction upstream` (và `_build_report_markdown`) trước khi sửa; báo risk + caller (238, 240 import khuôn này).
2. Test: (a) `pbo_fn=None` → kết quả và chuỗi báo cáo **y hệt** trước (so trên dữ liệu giả nhỏ); (b) `pbo_fn` giả trả 0.25 → `pbo_ea == 0.25` và báo cáo có đúng một dòng PBO; (c) ma trận truyền cho `pbo_fn` có shape (số tháng EA, 9) và cột đúng thứ tự lưới, giá trị = r − ew; (d) `pbo_for_exploration`: T=36 → S=16; T=10 → S=4; T=3 → ValueError.
3. `uv run pytest tests/test_research237_*.py tests/test_research238_core.py tests/test_research240_core.py tests/test_trial_ledger.py -v` xanh; `uv run pytest -m "not integration" -q` xanh; `uv run ruff check trading tests scripts` sạch.
4. `detect_changes` chỉ thấy các file §2.
5. Báo cáo: diff `research237_explore.py`, danh sách `def test_*` mới, output thô bước 3–4, chỗ mơ hồ đã tự quyết.
