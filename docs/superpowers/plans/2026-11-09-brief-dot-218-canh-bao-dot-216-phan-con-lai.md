# Brief đợt 218: vá các lỗ hổng cảnh báo còn lại của đợt 216 (F6, F7, F9, F11, F8a)

Ngày 09/11/2026. Người giao: Claude (Lead). Người làm: **Builder**.

- **Nguồn:** `docs/audit/2026-11-08-nghien-cuu-do-tin-cay-canh-bao.md`, các dòng F6, F7, F9, F11 và F8.
- **Đã làm ở đợt 217 (ae7c84b):** F1, F3, F4, F5. Không sửa lại các phần đó.
- **Không làm trong đợt này:**
  - F2 và phần ping ra dịch vụ ngoài của F8: chờ chủ dự án quyết;
  - F10;
  - thêm `healthcheck` mới vào `docker-compose.yml`. Không sửa compose.

## Quy tắc chung

- **Làm trong worktree riêng, KHÔNG sửa thư mục repo chính.**
  - Hôm nay là thứ Hai, có phiên giao dịch, và các script trong `scripts/` đang được Task Windows chạy thật từ thư mục repo chính (container-health mỗi 10 phút, stream-health, engine-cam 15:15, orderbook-daily-check 15:30).
  - Tạo worktree: `git worktree add ../AI_auto_trading_system-wt218 -b dot218 main`, rồi làm mọi việc trong đó.
  - Chạy test trong worktree đó (`uv run ...` tại thư mục worktree).
  - Không commit vào `main`. Có thể commit lên nhánh `dot218` để Lead dễ xem; Lead sẽ tự merge.
- **Impact trước khi sửa mỗi symbol:** chạy `node .gitnexus/run.cjs impact "<tên>" --direction upstream --repo .`. Không dùng `npx`.
  - Gặp HIGH hoặc CRITICAL: **dừng lại**, gửi Lead bảng impact của **cả 5 task** cùng kế hoạch, **một lần**, rồi chờ Lead duyệt.
  - Gặp UNKNOWN: kèm bằng chứng `git grep`.
- **Sửa file ngoài danh sách của task:** dừng lại và hỏi Lead. Ngoại lệ là các test cấu trúc bắt khai báo nhánh mới (`tests/test_schedule_watch.py`, `tests/test_sched_args.py`, `tests/test_deployment_doc.py`); trường hợp này cứ làm, rồi ghi trong báo cáo.
- **Khi sửa `reason` hay chú thích:** chỉ thêm ý mới. Không xoá thông tin cũ còn đúng. Đợt 217 đã phải trả lại một ghi chú bị xoá.
- **Sau khi sửa:** chạy `node .gitnexus/run.cjs detect-changes --scope all --repo .`.
- **Cấm:**
  - push, hoặc commit vào `main`;
  - chạy `sched.sh`, `run_if_docker_up.sh` hay script cảnh báo/kiểm tra thật;
  - gửi Telegram thật: mọi test dùng hàm gửi giả;
  - restart hay rebuild container;
  - đăng ký hay sửa Task Windows.
- **Test không được ghi vào `logs/` thật**, kể cả `alert_outbox_*` và `.schedule_health_state.json`. Dùng `tmp_path` cho outbox và log.

## Task 1 (F6). `engine-cam` và `orderbook-daily-check` gửi qua hàng đợi

- **Hiện trạng:**
  - Hai job này chạy một lần mỗi ngày (15:15 và 15:30) và gửi Telegram đúng một lần, không có hàng đợi. Gửi lỗi là mất tin, và phải 24 giờ sau mới có lần chạy tiếp.
  - `scripts/check_silent_engine.py` gửi qua `alert_and_fail` (`scripts/_alert_common.py:41`).
  - `scripts/check_orderbook_daily.py` gọi `trading.alerts.alert()` ở dòng 209 và 238, nhưng không gọi `start_outbox`.
- **Sửa:** cho tin cảnh báo của hai script này đi qua `send_with_outbox` (`_alert_common.py:100`), với một file outbox riêng cho từng job, đặt tên bằng `outbox_name(...)` theo đúng mẫu `heartbeat_check.py:116`.
  - Giữ nguyên mã thoát và nội dung tin hiện có.
  - Hàm gửi và đường dẫn outbox phải truyền vào được, để test dùng hàm giả và `tmp_path`.
  - Đọc `send_with_outbox` để biết tin đang kẹt trong outbox được gửi lại vào lúc nào. Nếu tin chỉ được gửi lại ở lần chạy sau của chính job (tức 24 giờ sau), thì **ghi rõ điều đó trong báo cáo**. Không tự viết cơ chế gửi lại mới.
- **Kiểm chứng:**
  - Gửi giả ném lỗi: tin nằm trong outbox ở `tmp_path`, mã thoát không đổi.
  - Lần chạy sau, gửi giả thành công: outbox được xả.

## Task 2 (F7). Canh tuổi lần diễn tập phục hồi thành công gần nhất

- **Hiện trạng:**
  - Không ai canh "lần cuối restore chạy được là khi nào".
  - 2 trong 5 Chủ nhật gần nhất `restore-drill` bị SKIP vì Docker tắt.
- **Định dạng `logs/restore-drill.log`:** dòng `Diễn tập OK: <dump>, ...` **không có timestamp**. Mốc thời gian lấy từ dòng `<ts> restore-drill start` gần nhất **đứng trước** dòng OK đó.
- **Sửa trong `scripts/heartbeat_check.py`:** thêm phép kiểm "tuổi lần diễn tập OK cuối cùng".
  - Ngưỡng 9 ngày (lịch tuần cộng 2 ngày dư).
  - Chạy trong **cả** đường `--schedule-watch-only` lẫn heartbeat thường.
  - Chống lặp bằng `.schedule_health_state.json`, theo đúng cơ chế hiện có: một sự cố chỉ báo một lần, và báo "đã chạy lại" khi trở lại bình thường nếu cơ chế hiện có làm vậy với các job khác.
  - Không có file log, hoặc chưa từng có dòng OK: coi là quá hạn.
- **Kiểm chứng:** viết test với log mẫu trong `tmp_path` cho các trường hợp:
  - lần OK cuối cách đây 8 ngày: không báo;
  - lần OK cuối cách đây 10 ngày, và sau đó có 1 dòng SKIP: báo đúng 1 lần, chạy lần hai với cùng trạng thái thì không báo nữa;
  - lần chạy cuối có `start` nhưng không có dòng OK (drill lỗi), còn lần OK trước đó cách đây 10 ngày: báo.

## Task 3 (F9). `container-health` báo khi container `unhealthy`

- **Hiện trạng:** `scripts/container_health_check.py:188-200` gọi `docker inspect -f` nhưng không đọc `State.Health`. Postgres có `healthcheck`, nhưng trạng thái `unhealthy` không được ai báo.
- **Sửa:**
  - Thêm trạng thái health vào lệnh `inspect`. Container không có healthcheck thì phải đọc ra rỗng hoặc `none`, không lỗi; dùng template Go có điều kiện, ví dụ `{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}`.
  - Thêm trường vào `ContainerStats`.
  - `unhealthy` là CRITICAL, gửi theo đúng đường gửi hiện có của script.
  - `starting`, `healthy` và `none` không báo.
  - Giữ nguyên chống lặp hiện có (`.container_health_state.json`).
- **Kiểm chứng:** test với output `docker inspect` giả cho các trường hợp `healthy`, `unhealthy`, `none` và `starting`. Các test cũ phải vẫn xanh; chỉ sửa fixture nếu nó buộc phải đổi theo định dạng mới, và liệt kê các fixture đã sửa trong báo cáo.

## Task 4 (F11). `stream-health` gửi tin khi CRITICAL

- **Hiện trạng:** `scripts/stream_health_check.py` (nhánh `sched.sh:116-122`, `--min-coverage-crit 0.50`) chỉ thoát với mã 1 hoặc 2, không gửi gì.
- **Sửa:** khi kết quả CRITICAL (độ phủ dưới ngưỡng crit), gửi một tin qua `send_with_outbox` với outbox riêng, nêu độ phủ đo được và ngưỡng.
  - Mức WARN: giữ như cũ, không gửi.
  - Giữ nguyên mã thoát.
  - Đọc policy `stream-health` trong `SCHEDULE_EXIT_POLICIES`. Nếu policy đang mô tả là "không gửi Telegram", thì cập nhật `reason` (chỉ thêm ý mới).
- **Kiểm chứng:**
  - Độ phủ 0,4: gửi 1 tin, đúng mã thoát cũ.
  - Độ phủ 0,8: không gửi.
  - Gửi lỗi: tin nằm trong outbox ở `tmp_path`.

## Task 5 (F8a). Tin tóm tắt buổi sáng: "không có tin là có gì đó chết"

- **Mục tiêu:** mỗi ngày giao dịch, lúc 08:00, gửi **một** tin ngắn. Ngày nào chủ dự án không thấy tin thì biết chuỗi cảnh báo đã chết. Không dùng dịch vụ ngoài.
- **Sửa:** thêm cờ `--morning-summary` cho `scripts/heartbeat_check.py`.
  - Chỉ gửi vào ngày giao dịch, dùng `trading.calendar_vn.is_trading_day`. Ngày khác thì thoát 0 và không gửi gì.
  - Nội dung tin, tối đa khoảng 10 dòng:
    - tuổi lần chạy cuối của từng job trong `SCHEDULE_WATCH_JOBS` (theo F1: lần chạy thật);
    - tuổi dump mới nhất (mtime của `trading_*.dump` mới nhất trong thư mục sao lưu, theo cách `backup_check.py` đang tìm thư mục đó; không tự đoán đường dẫn);
    - lần diễn tập OK cuối (từ Task 2);
    - số file `alert_outbox_*` đang có trong `logs/` và tổng số tin đang chờ trong đó.
  - Gửi qua `send_with_outbox`.
  - Không đổi state của schedule-watch.
- **Thêm nhánh `morning-summary` vào `sched.sh`:**
  - log riêng `morning-summary.log`;
  - khai báo trong `KHONG_CANH` (kèm lý do) và `SCHEDULE_EXIT_POLICIES`.
- **`DEPLOYMENT.md`:** thêm một hàng task `trading-morning-summary` (08:00, thứ Hai–thứ Sáu) và dòng cron `0 8 * * 1-5`. Lead tự đăng ký task.
- **Kiểm chứng:**
  - Thứ Hai: gửi đúng 1 tin, có đủ 4 mục.
  - Thứ Bảy: không gửi, thoát 0.
  - Gửi lỗi: tin vào outbox ở `tmp_path`.
  - Test cho nhánh `sched.sh`.

## Kiểm chứng cuối (trong worktree)

- `uv run pytest -m "not integration" -q`: mốc là 2331. Sau khi sửa phải là mốc cộng số test mới, **0 failed**.
- `uv run ruff check trading tests scripts`: sạch.
- `git -C <repo chính> status --short`: thư mục repo chính **không đổi** gì.
- Chụp `ls -A logs | sort` cùng nội dung `alert_outbox_*` và `.schedule_health_state.json` của repo chính trước và sau khi chạy test. Các file mà job thật ghi định kỳ (`container-health.log`, `.container_health_state.json`, `heartbeat.log`, `engine-consumer.log`, `disk-check.log`, `backup-makeup.log`, `schedule-watch.log`, `stream-health.log`) được phép đổi mtime, vì hôm nay có phiên.

## Báo cáo cho Lead

1. **Giữa chừng:** bảng impact cùng kế hoạch, gửi trước khi sửa nếu có HIGH hoặc CRITICAL.
2. **Cuối đợt:**
   - tên nhánh hoặc commit trong worktree;
   - kết quả `git diff --stat main`;
   - kết quả `detect-changes`;
   - với từng task: test mới và kết quả;
   - số test trước và sau;
   - kết quả so sánh `logs/`;
   - các file đã sửa ngoài danh sách, kèm lý do;
   - riêng Task 1: tin kẹt trong outbox được gửi lại vào lúc nào.
