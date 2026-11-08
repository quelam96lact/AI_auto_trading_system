# Brief đợt 215: sửa 4 điểm vận hành theo kết quả đợt 214

Ngày 08/11/2026. Người giao: Claude (Lead). Người làm: **Builder**.

Nguồn: `docs/audit/2026-11-08-nghien-cuu-toi-uu-he-thong.md` (commit 4e505e5), các dòng 1, 2, 3 và 5. Chủ dự án đã duyệt làm cả bốn.

## Quy tắc chung

- **Trước khi sửa mỗi symbol:** chạy `node .gitnexus/run.cjs impact "<tên>" --direction upstream --repo .`. Không dùng `npx`.
  - Index đang cũ (lần cuối ở 9c1f059), nên chạy `node .gitnexus/run.cjs analyze --index-only` trước.
  - HIGH hoặc CRITICAL thì dừng lại và báo Lead.
  - UNKNOWN thì phải có thêm bằng chứng `git grep`.
- **Sau khi sửa:** chạy `node .gitnexus/run.cjs detect-changes --scope all --repo .`.
- Giữ nguyên style code. Không "tiện thể" sửa thứ khác; vấn đề ngoài phạm vi thì ghi vào báo cáo.
- **Cấm:**
  - commit, push;
  - chạy `sched.sh`, `run_if_docker_up.sh` hay `backup_db.sh` thật;
  - restart hoặc rebuild container;
  - sửa Task Scheduler của Windows. Việc đăng ký task do Lead làm.
- **Test không được ghi file nào vào `logs/` thật.**
  - Trước và sau khi chạy test, chụp `ls -A logs | sort` rồi so hai danh sách.
  - Riêng các file mà job thật trên host ghi định kỳ thì được phép đổi mtime, gồm `container-health.log`, `.container_health_state.json`, `heartbeat.log`, `engine-consumer.log` và `disk-check.log`. Ghi rõ những file này trong báo cáo.

## Task 1. Test BingX drill ghi file giả vào `logs/` thật

- **Hiện trạng:** `scripts/bingx_drill_place_cancel.py:38` có `LOGS_DIR = pathlib.Path("logs")`, và dòng 474 ghi `bingx_drill_<ts>.json`. Một test trong `tests/test_bingx_drill.py` chạy tới đường này, nên mỗi lần chạy pytest lại sinh một file giả (`order_id 99999`).
- **Sửa trong test, không sửa script:** test nào chạy tới chỗ ghi file thì `monkeypatch.setattr(drill, "LOGS_DIR", tmp_path)`. Đúng cách này đã có sẵn trong các test khác của repo.
- Script thật vẫn ghi vào `logs/`. Không đổi hành vi của script.

→ **Kiểm chứng:**
- Chạy `uv run pytest tests/test_bingx_drill.py -q`. Sau khi chạy, `ls logs/bingx_drill_*` không có file nào.
- Test phải assert rằng file JSON **có** được ghi vào `tmp_path`, để không mất phần kiểm tra cũ.

## Task 2. Catchup tự thử lại khi gặp lỗi tạm thời

- **Hiện trạng:** catchup tối 04/11 bị EXIT=1 vì lỗi DNS lúc Docker vừa lên, nên thiếu foreign-flow 03–04/11 suốt khoảng 3 ngày. Có 2 lần EXIT=2 vì `database system is starting up`, phát sinh từ `pg_advisory_lock` trong `run_job`.
- **Sửa trong `trading/scheduler/main.py`:** thêm một hàm bọc quanh `run_job`, chỉ dùng cho job `catchup` ở 3 chỗ: `run_startup`, `morning_catchup` và bước catchup của `evening_jobs`.
  - Thử lại khi `rc` là **1 hoặc 2**.
  - **Không** thử lại khi `rc` là 0, `None` (SKIP vì đang có tiến trình khác giữ lock) hoặc 124 (timeout 3 giờ).
  - Tối đa 3 lần chạy, tức 2 lần thử lại, mỗi lần cách nhau 300 giây. Đặt thành hằng số module, theo kiểu các hằng `TIMEOUT_*` đang có.
  - Hàm `sleep` phải truyền vào được, để test không phải ngủ thật.
  - Mỗi lần chạy vẫn đi qua `run_job`, nên vẫn ghi đủ dòng `start` và `EXIT=`. `heartbeat_check` đọc dòng `EXIT=` sau dòng `start` cuối cùng, nên sẽ thấy kết quả của lần chạy cuối. Builder phải xác nhận điều này bằng cách đọc `scripts/heartbeat_check.py` quanh dòng 399–430.
  - Trong `evening_jobs`, `daily-data-check` và `universe-refresh` vẫn chạy sau catchup như cũ, kể cả khi catchup vẫn lỗi sau 3 lần.
- **Không** sửa `scripts/startup_catchup.py`. Job này chạy lại được nhiều lần mà không gây sai, vì kế hoạch nạp được tính lại từ DB mỗi lần.

→ **Kiểm chứng:** viết test trong `tests/test_scheduler.py`, dùng `run_job` giả và `sleep` giả, cho các kịch bản sau:
- rc lần lượt `[1, 0]`: chạy 2 lần, sleep 1 lần với 300.
- rc lần lượt `[2, 2, 2]`: chạy 3 lần, trả về 2.
- rc `[0]`: chạy 1 lần.
- rc `[None]`: chạy 1 lần.
- rc `[124]`: chạy 1 lần.
- `evening_jobs` với catchup luôn bằng 1: daily-check và universe-refresh vẫn được gọi.

## Task 3. Backup bù khi Docker lên trễ

- **Hiện trạng:**
  - Task `trading-backup` chạy lúc 02:00, gọi `sched.sh backup`, rồi `run_if_docker_up.sh`, rồi `backup_db.sh`.
  - Đêm nào Docker tắt thì bị `SKIP` và không có lần chạy bù. Kết quả là 120 giờ không có dump nào (03/11 tới 08/11).
- **Sửa `scripts/backup_db.sh`:**
  - Thêm biến môi trường tuỳ chọn `BACKUP_SKIP_IF_NEWER_HOURS`. Không thêm tham số dòng lệnh, vì script đang chặn mọi option.
  - Nếu biến được đặt, và file `trading_*.dump` mới nhất trong `BACKUP_DIR` có tuổi (theo mtime) nhỏ hơn số giờ đó, thì in đúng một dòng `SKIP: dump moi nhat <ten> moi <N> gio (< <nguong>)` rồi `exit 0`.
  - Bước kiểm này phải chạy **trước** mọi thao tác ghi hay dump.
  - Biến không được đặt thì hành vi giữ y như cũ.
- **Sửa `scripts/sched.sh`:** thêm lệnh con `backup-makeup`.
  - Lệnh này đặt `BACKUP_SKIP_IF_NEWER_HOURS=26` rồi chạy `"$RUN" backup-makeup.log backup-makeup bash scripts/backup_db.sh "$@"`.
  - Dùng **file log riêng** để không làm lẫn `backup.log`.
  - Thêm `backup-makeup` vào dòng `dung:` ở cuối file.
- **Sửa `DEPLOYMENT.md`:**
  - Thêm một hàng `trading-backup-makeup` (mỗi giờ, 24/7, tham số `backup-makeup`) vào bảng task Windows quanh dòng 643.
  - Thêm một dòng cron Ubuntu tương ứng (`0 * * * *`) cạnh dòng 581.
  - Đây chỉ là tài liệu; Lead tự đăng ký task.

→ **Kiểm chứng:**
- Viết test trong `tests/test_backup_db_counts.py`, hoặc một file test mới, theo đúng cách các test bash đang có. Các test phải chạy trong `tmp_path` và không gọi docker thật:
  - Có dump mtime cách đây 1 giờ, ngưỡng 26: in `SKIP`, exit 0, không có file mới.
  - Không có dump nào, hoặc dump cách đây 30 giờ: đi tiếp vào nhánh dump (dùng cách giả docker mà các test hiện có đang dùng).
  - Biến không được đặt: hành vi y như cũ, tức các test cũ vẫn xanh.
- Thêm test vào `tests/test_sched_args.py` cho `backup-makeup`, theo đúng mẫu các lệnh con khác.

## Task 4. Ghi thời lượng job vào log của scheduler

- **Hiện trạng:** `run_job` chỉ ghi `<ts> <label> start` và `EXIT=<rc>`. Đợt 214 vì thế không đo được thời gian chạy của từng job.
- **Sửa `run_job`:** ngay **trước** dòng `EXIT=`, ghi thêm một dòng `<ts_ket_thuc> <label> finish dur=<giay>s`.
  - Dùng `time.monotonic()` để tính thời lượng.
  - `ts_ket_thuc` lấy theo cùng định dạng với dòng `start`.
  - Dòng `EXIT=<rc>` phải giữ **nguyên văn** như cũ.
- **Trước khi sửa:** dùng `git grep` tìm mọi chỗ đọc `catchup.log`, `daily-data-check.log`, `universe-refresh.log`, cùng các regex `start` và `EXIT=`, chủ yếu trong `scripts/heartbeat_check.py` và `scripts/schedule_watch*.py`. Liệt kê chúng trong báo cáo, và chứng minh dòng `finish` mới không khớp nhầm regex nào.

→ **Kiểm chứng:**
- Test cho `run_job`: log có đúng thứ tự `start`, rồi `finish dur=`, rồi `EXIT=`.
- Thêm một test dùng parser thật của `heartbeat_check` đọc log mẫu có dòng `finish`, và vẫn ra đúng exit code.

## Kiểm chứng cuối

- `uv run pytest -m "not integration" -q`: ghi số passed trước khi sửa (mốc 2297). Sau khi sửa phải là mốc + số test mới, **0 failed**.
- `uv run ruff check trading tests scripts`: sạch.
- Danh sách `logs/` trước và sau giống nhau, trừ các file job host nêu ở trên.

## Báo cáo cho Lead

- Kết quả `git diff --stat`.
- Kết quả `impact` của từng symbol đã sửa (`run_job`, `run_startup`, `run_event`, cùng hàm mới), gồm số caller và mức risk.
- Kết quả `detect-changes`.
- Task 4: danh sách nơi đọc log và lý do dòng `finish` an toàn.
- Số test trước và sau, số test mới.
- So sánh danh sách `logs/` trước và sau.
