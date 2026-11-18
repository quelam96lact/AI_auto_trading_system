# Brief đợt 246: chạy bù `daily-engine` khi scheduler khởi động

- **Ngày:** 19/11/2026. Chủ dự án: "thêm daily-engine vào chạy bù khi khởi động".
- **Vấn đề:** máy tắt 16/11 17:06 → 19/11 04:07; ba lần 21:45 (chuỗi `catchup → daily-data-check → daily-engine` trong `run_event("evening_jobs")`) đều lỡ. `run_startup` chỉ chạy `scripts.startup_catchup`, không gọi engine → `paper_daily_*` vẫn trống.
- **Bẫy phải tránh:** `runner._execute_engine` xử lý mọi phiên `last_processed_date < d <= vn_today`; nếu khởi động ban ngày, phiên hôm nay chưa đủ nến → `_process_single_session` trả not ready → exit 1 → `notify_job_failure` báo **lỗi giả** mỗi lần khởi động trong giờ.

## 1. Sửa

1. `trading/daily_engine/runner.py`: thêm cờ CLI `--through-yesterday` (mặc định tắt = hành vi cũ). Khi bật: dùng `vn_today − 1 ngày` làm mốc cuối thay cho `vn_today` ở **cả** bước khởi tạo (`_build_sessions(START_DATE, ...)`) lẫn `todo_sessions`. Không đổi gì khác.
2. `trading/scheduler/main.py::run_startup`: sau catchup (bất kể rc của catchup), chạy `daily-engine` đúng như nhánh `evening_jobs` (cùng `label="daily-engine"`, cùng log file, cùng lock id, cùng timeout, cùng cách báo lỗi) nhưng command thêm `--through-yesterday`. Giá trị trả về của `run_startup` giữ là rc của catchup.
3. Nhánh `evening_jobs` và `morning_catchup` **không đổi**.

## 2. Phạm vi file

- **Sửa:** `trading/daily_engine/runner.py`, `trading/scheduler/main.py`; test trong `tests/test_daily_engine_runner.py` và test scheduler hiện có (tìm file test của `run_startup`). Không xoá/sửa test cũ.
- **Không đụng:** `core.py`, `store.py`, `strategy.py`, `scripts/heartbeat_check.py`, docker-compose.
- Builder KHÔNG: commit/push, docker/rebuild, truy vấn DB thật, `sched.sh`, `npx`.

## 3. Tiêu chí hoàn thành

1. GitNexus `impact` upstream cho `run_startup` và `_execute_engine` trước khi sửa (index lỗi → báo + text search); báo caller.
2. Test mới:
   - (a) `run_startup` gọi đúng thứ tự `catchup` rồi `daily-engine`, command engine có `--through-yesterday`; engine vẫn chạy khi catchup rc ≠ 0; `run_startup` trả rc của catchup.
   - (b) engine rc ≠ 0 lúc startup → `notify_job_failure(label="daily-engine", ...)` được gọi.
   - (c) runner với `--through-yesterday`: state có `last_processed_date` = hôm kia, hôm nay chưa có nến → chỉ xử lý hôm qua, exit 0 (không exit 1).
   - (d) runner với `--through-yesterday` và chưa có state: khởi tạo ở phiên sẵn sàng gần nhất ≤ hôm qua.
   - (e) không có cờ → hành vi cũ y hệt (test cũ xanh).
3. `uv run pytest tests/test_daily_engine_runner.py <file test scheduler> -v` xanh; `uv run pytest -m "not integration" -q` xanh; `uv run ruff check trading tests` sạch.
4. `detect_changes` chỉ thấy các file §2.
5. Báo cáo: diff, `def test_*` mới, output thô bước 3–4.

## 4. Triển khai (Lead)

Sau audit + commit: rebuild image `scheduler` (và `collector`, `engine` để giữ deploy-drift), restart `scheduler`. Kiểm: log `daily-engine` sau startup, `paper_daily_state` có dòng.
