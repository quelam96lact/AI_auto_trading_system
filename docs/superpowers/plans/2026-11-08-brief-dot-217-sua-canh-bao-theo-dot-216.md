# Brief đợt 217: sửa 4 lỗ hổng cảnh báo theo đợt 216 (F1, F3, F4, F5)

Ngày 08/11/2026. Người giao: Claude (Lead). Người làm: **Builder**.

- **Nguồn:** `docs/audit/2026-11-08-nghien-cuu-do-tin-cay-canh-bao.md` (commit ed48ee7). Chủ dự án đã duyệt.
- **Không làm trong đợt này:**
  - F2 (sao lưu ra ngoài máy) và F8 (ping ra dịch vụ ngoài): chờ chủ dự án quyết.
  - F6, F7, F9, F10, F11.

## Quy tắc chung (nhắc lại hai điểm của đợt 215)

- **Impact trước khi sửa mỗi symbol:** chạy `node .gitnexus/run.cjs impact "<tên>" --direction upstream --repo .`.
  - Chạy `node .gitnexus/run.cjs analyze --index-only` trước, vì index đang cũ.
  - Không dùng `npx`.
- **HIGH hoặc CRITICAL thì DỪNG LẠI và gửi Lead** kết quả impact, kèm kế hoạch sửa của task đó. Chỉ làm tiếp khi Lead trả lời.
  - `heartbeat_check.py` và `trading/scheduler/main.py` gần như chắc chắn ra CRITICAL. Hãy làm phần impact của **cả 4 task trước**, rồi gửi Lead **một lần**.
- **Sửa file ngoài danh sách của task: DỪNG LẠI và hỏi Lead.** Ngoại lệ duy nhất là test cấu trúc trong `tests/test_schedule_watch.py` / `tests/test_sched_args.py` bắt khai báo nhánh mới. Trường hợp này cứ làm, rồi ghi rõ trong báo cáo.
- **Sau khi sửa:** chạy `node .gitnexus/run.cjs detect-changes --scope all --repo .`.
- **Cấm:**
  - commit, push;
  - chạy `sched.sh`, `run_if_docker_up.sh` hay script cảnh báo/kiểm tra thật;
  - gửi Telegram thật: mọi test phải dùng hàm gửi giả;
  - restart container;
  - đăng ký Task Windows. Việc này do Lead làm.
- **Test không được ghi vào `logs/` thật,** kể cả các file `alert_outbox_*` và `.schedule_health_state.json`.
  - Chụp `ls -A logs | sort`, cùng nội dung của `logs/alert_outbox_*` và `.schedule_health_state.json`, trước và sau khi chạy test, rồi so sánh.
  - Các file mà job thật trên host ghi định kỳ (`container-health.log`, `.container_health_state.json`, `heartbeat.log`, `engine-consumer.log`, `disk-check.log`, `backup-makeup.log`) thì được phép đổi mtime.

## Task 1 (F1). Bộ canh tuổi job không được coi dòng SKIP là "đã chạy"

- **Hiện trạng:**
  - Hàm đọc lần chạy cuối trong `scripts/heartbeat_check.py`, quanh dòng 360–390, ghi chú "dòng SKIP cũng tính là đã được gọi".
  - Regex của hàm khớp với mọi dòng mang nhãn job, nên dòng `backup SKIP: docker chua chay` vẫn làm job trông "còn tươi".
  - Hậu quả: 120 giờ không có dump mà không có cảnh báo nào.
- **Sửa:** thêm vào `WatchJobConfig` một trường, ví dụ `skip_counts_as_run: bool = True`. Giá trị mặc định giữ hành vi cũ.
  - Đặt `False` cho `backup`, `backup-check` và `orderbook-backup`.
  - Với các job này, tuổi job được tính từ dòng **`start`** cuối cùng.
  - Trước khi chọn danh sách, đọc lý do vì sao SKIP từng được tính là "đã gọi". Nếu lý do đó vẫn đúng cho job nào trong ba job trên thì bỏ job đó ra và báo lại.
  - Tin cảnh báo tuổi job phải ghi rõ hai thông tin: lần chạy thật cuối cùng, và số lần SKIP kể từ đó.
- **Kiểm chứng:** viết test với log mẫu trong `tmp_path`.
  - Log gồm `start` và `EXIT=0` cách đây 60 giờ, sau đó là 3 dòng SKIP gần đây. Kết quả phải là job `backup` **quá hạn**, còn job có `skip_counts_as_run=True` vẫn được tính như cũ.

## Task 2 (F4). Canh tuổi job 24/7 cả ngoài giờ giao dịch

- **Hiện trạng:**
  - `heartbeat_check.py:1086-1088` `return 0` khi ngoài khoảng 08:00–15:00 ngày giao dịch.
  - Task `trading-heartbeat-check` chỉ chạy thứ Hai đến thứ Sáu, từ 08:00, 7 giờ mỗi ngày.
  - Hậu quả: job hỏng sau 15:00 thứ Sáu thì khoảng 65 giờ sau mới có người biết.
- **Sửa:** thêm cờ `--schedule-watch-only` cho `heartbeat_check.py`.
  - Khi có cờ này, script **chỉ** chạy phần canh tuổi job (`SCHEDULE_WATCH_JOBS`), **không phụ thuộc** cửa sổ giờ, rồi thoát.
  - Không chạy phép kiểm thị trường hay nến nào.
  - Dùng đúng cơ chế chống lặp hiện có (`.schedule_health_state.json`, `alerted_for`): **một sự cố chỉ báo một lần**, không báo lại mỗi giờ.
  - Trước khi sửa, Builder phải đọc code và xác nhận cơ chế này hoạt động khi chạy mỗi giờ.
  - Không có cờ thì hành vi y như cũ.
- **Thêm nhánh `schedule-watch` vào `sched.sh`:**
  - Nhánh này chạy `heartbeat_check.py --schedule-watch-only`, ghi vào log riêng `schedule-watch.log`.
  - Khai báo nhánh trong `KHONG_CANH` (kèm lý do) và trong `SCHEDULE_EXIT_POLICIES`.
- **`DEPLOYMENT.md`:** thêm một hàng task `trading-schedule-watch` (mỗi giờ, 24/7) và một dòng cron `0 * * * *`.
- **Kiểm chứng:**
  - Một test chạy lúc 22:00 thứ Bảy với `--schedule-watch-only`, có job quá hạn: báo đúng 1 lần.
  - Chạy lần hai với cùng trạng thái: không báo nữa.
  - Không có cờ, cũng lúc 22:00 thứ Bảy: `return 0` và không gửi gì, y như cũ.
  - Test cho nhánh `sched.sh`.

## Task 3 (F3). Scheduler báo khi job lỗi hẳn

- **Hiện trạng:** `trading/scheduler/main.py` không có đường gửi cảnh báo nào. Catchup lỗi 4 lần từ 02/11 nhưng không có tin nào được gửi.
- **Sửa:**
  - Sau `run_job_with_retry` của catchup: nếu `rc` cuối cùng không phải 0 và không phải `None`, gửi **một** cảnh báo.
  - Với `daily-data-check` và `universe-refresh`: nếu `rc` không phải 0 và không phải `None`, cũng gửi một cảnh báo.
  - Nội dung tin: tên job, `rc`, số lần đã thử, file log cần xem (`logs/catchup.log`, …), và giờ VN.
  - **Dùng cơ chế gửi có sẵn trong `trading/`** (`trading/telegram.py`, `trading/alerts.py` / outbox). Không viết cơ chế mới.
  - Không import từ `scripts/` vào `trading/`. Nếu không có cách gửi có hàng đợi mà không import từ `scripts/` thì DỪNG LẠI và báo Lead.
  - Hàm gửi phải truyền vào được (tiêm), để test dùng hàm giả.
  - Container scheduler đã có `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID` (`docker-compose.yml`). Không sửa compose.
- **Kiểm chứng:** viết test với `runner_fn` giả và hàm gửi giả:
  - catchup ra `[1, 1, 1]`: gửi 1 tin, trong tin có "catchup" và "3".
  - catchup ra `[1, 0]`: không gửi.
  - catchup ra `[None]`: không gửi.
  - daily-check ra 1: gửi 1 tin.
  - Lỗi trong lúc gửi không được làm hỏng vòng lặp của scheduler.

## Task 4 (F5). Phân biệt crash với "đã báo"

- **Hiện trạng:**
  - 8 job coi mã thoát 1 là bình thường, theo nghĩa "đã tự gửi Telegram": `heartbeat`, `daily-check`, `deploy-drift`, `engine-cam`, `engine-consumer`, `backup-check`, `disk-check`, `restore-drill`.
  - Nhưng exception không bắt được của Python cũng thoát với mã 1, nên một lần crash bị hiểu thành "đã báo".
  - `container_health_check.py:590-592` biến mọi exception thành `exit(2)`, mà 2 lại là mã bình thường của job này.
- **Sửa:** với mỗi script Python thuộc các job trên, cùng `container_health_check.py` và script của `orderbook-daily-check`:
  - Ở điểm vào `if __name__ == "__main__":`, bắt `Exception` (không bắt `SystemExit` hay `KeyboardInterrupt`).
  - In traceback ra stderr, rồi `sys.exit(3)`.
  - Trước khi sửa, `git grep` để chắc mã 3 chưa được dùng với nghĩa khác trong các script đó. Nếu đã dùng thì DỪNG LẠI và báo Lead.
  - `SCHEDULE_EXIT_POLICIES` **không** thêm 3 vào `normal_exit_codes`, để heartbeat coi mã 3 là bất thường và báo.
  - Cập nhật `reason` của từng policy cho đúng.
- **Không đổi** logic bên trong `main()` của script nào.
- **Kiểm chứng:**
  - Mỗi script được sửa có một test: monkeypatch `main` để ném `RuntimeError`, chạy khối entry, và assert mã thoát là 3.
  - Test cho policy: mã 3 không nằm trong `normal_exit_codes` của job nào trong danh sách.

## Kiểm chứng cuối

- `uv run pytest -m "not integration" -q`: mốc trước khi sửa là 2309. Sau khi sửa phải là mốc + số test mới, **0 failed**.
- `uv run ruff check trading tests scripts`: sạch.
- So sánh `logs/` như trong phần quy tắc chung.

## Báo cáo cho Lead

1. **Giữa chừng:** bảng impact của mọi symbol sẽ sửa, kèm kế hoạch, gửi Lead **trước khi sửa** nếu có HIGH/CRITICAL.
2. **Cuối đợt:**
   - kết quả `git diff --stat`;
   - kết quả `detect-changes`;
   - với từng task: test mới và kết quả;
   - số test trước và sau;
   - kết quả so sánh `logs/`;
   - mọi file đã sửa ngoài danh sách, kèm lý do.
