# Nghiên cứu độ tin cậy, cảnh báo và an toàn vận hành (đợt 216)

Ngày đo: Chủ nhật 08/11/2026, 14:00–15:30 giờ VN. Người làm: Researcher. Chỉ đo và báo cáo, không sửa gì.

**Cách đo.** Chỉ đọc: code, `logs/`, `SELECT` trên DB, `docker inspect/ps/history/images`, một lệnh `docker run --rm ... ls -la /app`, `Get-ScheduledTask*` và kết nối TCP thử tới cổng. Không gửi Telegram, không chạy script cảnh báo hay `sched.sh`, không ghi DB hay `logs/`, không mở `.env`.

**Quy ước số.** Số đếm lấy từ dòng tổng kết (`DONE:`, `EXIT=`, `ALERT_EXIT=`, `[kiem]`, dòng tin Telegram đã in), không lấy từ dòng tiến độ. Log cũ bị xoay vòng nên mỗi con số kèm "từ ngày nào". Giờ `logs/*.log` là giờ VN.

**Hai ngôn ngữ về thời gian.** "Trong phiên" nghĩa là cửa sổ chạy của `heartbeat`: 08:00–15:00 T2–T6 (Task Windows, lặp 5 phút; cron VPS `*/5 8-15` kéo dài tới 15:55, tức độ trễ trên VPS ngắn hơn khoảng 55 phút so với bảng dưới).

**Không đề xuất nào trong tài liệu này đụng `postgresql.conf` hay `mem_limit`**, nên ràng buộc shared_buffers 25% / effective_cache_size 75% không phải áp dụng.

---

## 1. Bản đồ "hỏng thì ai báo"

Cột "Trễ tệ nhất" tính từ lúc hỏng tới lúc có người nhận tin, theo lịch thật (Task Windows) và theo code đã đọc. ✗ = **không ai biết** trong thực tế (không có đường báo, hoặc đường báo không bắt được kiểu hỏng đó).

Chú thích đường báo: **TG+hàng đợi** = `send_with_outbox` (gửi lại lần chạy sau); **TG 1 lần** = gửi một lần, hỏng là mất (`send_telegram` timeout 5 giây, `trading/telegram.py:42`); **mã thoát** = chỉ `EXIT=` trong log, do `heartbeat` đọc.

### 1a. Job chạy trên host (Task Windows / cron)

| Job | Kiểu hỏng | Thứ phát hiện (`file:dòng`) | Đường báo | Trễ tệ nhất |
|---|---|---|---|---|
| `heartbeat` (5', trong phiên) | chết hẳn / Task bị tắt | `container_health_check.py:78` `evaluate_heartbeat_watch` (ngưỡng 15', chỉ 08:15–15:00 ngày giao dịch) | TG 1 lần (`:571`) | trong phiên ~25'; **ngoài phiên ✗ vô hạn** |
| | crash (exit 1) | `heartbeat_check.py:212` chính sách `{0,1}` coi 1 là bình thường | — | **✗** (xem F5) |
| | chạy nhưng SKIP vì Docker tắt | dòng `SKIP` được tính là "đã gọi" (`heartbeat_check.py:369`) | chỉ `docker_down_alert` | — |
| `container-health` (10', 24/7) | không chạy | `SCHEDULE_WATCH_JOBS` (`:135`, ngưỡng 25') nhưng `heartbeat` chỉ đánh giá trong phiên | TG 1 lần | **tới 65 giờ** (hỏng sau 15:00 thứ Sáu, biết 08:00 thứ Hai) |
| | crash | `container_health_check.py:590-592` `except Exception: sys.exit(2)` mà chính sách `{0,1,2}` coi 2 là bình thường | — | **✗** |
| `deploy-drift` 08:00 | lệch image | `deploy_drift_check.py:204` `alert_and_fail` | TG 1 lần | tức thì |
| | crash (exit 1) | chính sách `{0,1}` | — | **✗** |
| `engine-consumer` (5', 09:00–15:10) | NATS lag/consumer chết | `engine_consumer_check.py:133,148,178` | TG 1 lần | ≤5' |
| | crash (exit 1) | chính sách `{0,1}` | — | **✗** |
| `stream-health` 15:10 | độ phủ nến thấp | `stream_health_check.py` **không có lệnh gửi nào** | mã thoát | T2–T5 16h50'; **T6 64h50'** |
| `engine-cam` 15:15 | engine câm | `check_silent_engine.py:141` `alert_and_fail` | TG 1 lần | tức thì |
| | crash (exit 1) | chính sách `{0,1}` | — | **✗** |
| `orderbook-recorder` 08:40–14:46 | crash/bị kill (exit 4) | `record_vn30f_orderbook.py:234,658,765,799` `alert()`; kill thì chỉ `EXIT=` | `alert()` (không `start_outbox`) / mã thoát | trong phiên ~5' nếu có dòng `EXIT=` |
| | treo (không có `EXIT=`) | `get_last_run_exit_code` trả `None` → im lặng (`heartbeat_check.py:464-469`) | — | tới 15:30, rồi `orderbook-daily-check` bắt hệ quả |
| `orderbook-daily-check` 15:30 | thiếu/hỏng file sổ lệnh | `check_orderbook_daily.py:208,237` `alert()` | TG 1 lần | tức thì |
| `backup` 02:00 | `pg_dump`/verify lỗi (exit 1, 2) | chỉ `heartbeat` đọc mã thoát (`backup_db.sh` không gửi gì) | mã thoát | T7 02:00 → T2 08:00 = **54 giờ** |
| | **SKIP vì Docker tắt** | `get_last_called_timestamp` coi SKIP là "đã gọi" (`heartbeat_check.py:369,376`) nên phép canh tuổi **không bao giờ thấy** | chỉ `docker_down_alert` | **✗ về "dump cũ N giờ"** (xem F1) |
| `backup-makeup` (mỗi giờ, mới từ đợt 215) | exit 1/2 | chính sách `{0}` (`:299`), không có canh tuổi (`KHONG_CANH`) | mã thoát | hỏng sau 15:00 T6 → T2 08:00 = **~65 giờ** |
| `backup-check` 03:00 | dump cũ >23h / tar sổ lệnh cũ | `backup_check.py:431` | TG+hàng đợi | tức thì (10 lần `EXIT=1` có tin) |
| | gate Docker: SKIP | chạy qua `run_if_docker_up.sh` nên cũng SKIP khi Docker tắt | chỉ `docker_down_alert` | **✗** trong lúc Docker tắt |
| `orderbook-backup` 02:30 | tar lỗi (exit 1, 2) | chỉ `heartbeat` đọc mã thoát | mã thoát | 53,5 giờ |
| `disk-check` (6 giờ/lần) | đĩa thiếu | `disk_check.py:205` | TG+hàng đợi | tức thì |
| | không đo được (exit 2) | chỉ mã thoát | mã thoát | 18:00 T6 → 08:00 T2 = **62 giờ** |
| `host-preflight` CN 07:00 | có phép kiểm HỎNG | script **không gửi Telegram**; mã thoát qua `heartbeat` | mã thoát | 25 giờ; trên Windows 9/14 phép kiểm **BỎ QUA** |
| `restore-drill` CN 04:00 | restore lỗi (exit 1) | `restore_drill.py:384` | TG+hàng đợi | tức thì |
| | crash / exit 2 | chỉ mã thoát | mã thoát | 28 giờ |
| | **SKIP vì Docker tắt** | không ai canh "tuổi lần diễn tập thành công" | chỉ `docker_down_alert` | **✗** (2/5 Chủ nhật bị bỏ, F7) |

### 1b. Job trong container `scheduler`

| Job | Kiểu hỏng | Thứ phát hiện | Đường báo | Trễ tệ nhất |
|---|---|---|---|---|
| `catchup` (khởi động, 06:40, 21:45) | lỗi sau cả ba lần thử | `trading/scheduler/main.py` và `scripts/startup_catchup.py` **không có `send_telegram`/`alert`/`start_outbox`** | mã thoát (chỉ lần chạy CUỐI) | 21:45 T2–T5: 10h15'; **T6: 58h15'**; lần chạy sau thành công xoá dấu vết |
| `daily-check` (21:45 chuỗi) | thiếu nến | `daily_data_check.py:481` `send_with_outbox` | TG+hàng đợi | tức thì |
| | crash (exit 1) | chính sách `{0,1}` | — | **✗** |
| `universe-refresh` | backfill lỗi | `refresh_universe.py:130,149` `send_telegram` (chỉ cho cổng co rút) | TG 1 lần / mã thoát | như `catchup` |
| mọi job | treo | `TIMEOUT_*` (`main.py:35-37`) kill → exit 124 → mã thoát | mã thoát | 3 giờ + như trên |
| vòng lặp scheduler | **treo ngoài `run_job`** | container vẫn `running`; không có hàng `heartbeat` cho scheduler | — | **✗** |

Kết quả của chuỗi này **được kiểm gián tiếp** mỗi sáng: `prev_day_bars_alert` (`heartbeat_check.py:870`), `prev_day_foreign_flow_alert` (`:920`), `prev_day_5m_alert` (`:960`), gọi ở `:1206-1296`, mỗi ngày P báo một lần. Đó là phép kiểm tốt cho nến ngày, khối ngoại và nến 5 phút. Nó **không** phủ `universe-refresh`, `bars_derivative`, `binance_*`, `bars_crypto`.

### 1c. Service

| Service | Kiểu hỏng | Thứ phát hiện | Đường báo | Trễ tệ nhất |
|---|---|---|---|---|
| `collector`, `engine` | ngừng ghi nhịp | `stale_services` (`heartbeat_check.py:645,1130`, ngưỡng 300 giây) | TG+hàng đợi | trong phiên ≤5'; **ngoài phiên không đo** |
| | tiến trình sống nhưng không ra bar | `bar_stale` (`:664,1148`, ngưỡng 15') | TG+hàng đợi | ≤5' trong phiên |
| | lỗi trong tiến trình | `alert()` + `start_outbox` (`collector/main.py:521`, `engine/main.py:837`) | TG+hàng đợi | tức thì |
| `postgres` | restart/OOM/exited | `container_health_check.py:279` (`inspect_container :187`) | TG 1 lần | ≤10' |
| | **chạy nhưng `unhealthy`** | `docker inspect` chỉ lấy `Id RestartCount State.Status OOMKilled StartedAt` (`:193`), **không đọc `State.Health`** | — | **✗** trừ khi trong phiên `heartbeat` không kết nối được DB |
| `nats` | restart/exited | như trên | TG 1 lần | ≤10' |
| | consumer lag | `engine_consumer_check.py` | TG 1 lần | ≤5' trong phiên; ngoài phiên **✗** |
| `scheduler`, `grafana` | restart/exited | như trên | TG 1 lần | ≤10' |
| Docker Desktop/daemon | tắt | `run_if_docker_up.sh:119-126` → `docker_down_alert.py:130` | TG 1 lần | trong phiên ≤30'; ngoài phiên ≥2 giờ rồi 6 giờ/tin |

### 1d. Đối chiếu sự cố thật trong `logs/`

| Sự cố (bằng chứng) | Có tin báo không | Nội dung tin có nói đúng hệ quả không |
|---|---|---|
| Dump DB cách nhau 120 giờ: `trading_20261103_020004.dump` → `trading_20261108_020012.dump` (liệt kê thư mục sao lưu). `backup.log` có **20 dòng `SKIP: docker chua chay` / 49 lần gọi** từ 29/09; 4 đêm 04/11–07/11 | Có tin "Docker tắt" (xem dòng dưới), **không có tin nào nói dump đã cũ** | Không. Tin trong phiên chỉ nói "Collector/engine đều dừng"; tin ngoài phiên chỉ nói "Docker tắt từ HH:MM (Nh)". Ví dụ 14:35 06/11, dump đã 84,6 giờ tuổi mà tin không nhắc |
| Docker tắt 03/11–07/11 | **54 tin trong phiên** (13/14/14/13 tin khác giờ trong 03, 04, 05, 06/11; đếm theo giờ `HH:MM` duy nhất) + **11 tin ngoài phiên** (`container-health.log`, từ 21:10 02/11 tới 69 giờ 04/11). `ALERT_EXIT=0` cho tất cả; 0 `ALERT_EXIT=2` trong giai đoạn này | Báo "Docker tắt", không báo hậu quả cụ thể |
| 4 phiên sổ lệnh VN30F không ghi được: `orderbook-recorder.log` SKIP 08:40 các ngày 03, 04, 05, 06/11 | Chỉ qua tin Docker tắt. `backup-check` 03:00 08/11 báo `EXIT=1` "tar sổ lệnh cũ 120,5h, dữ liệu ngày 06/11 chưa được sao lưu" | Tin này nói "chưa sao lưu", **không** nói phiên đó chưa từng được ghi, không nạp bù được |
| `catchup` lỗi: 02/11 16:09 `EXIT=2` (DB đang khởi động); 04/11 23:06 `EXIT=1`; 08/11 01:01 `EXIT=2`; 08/11 12:29 `EXIT=2` | **Cả 4 lần: 0 tin.** `heartbeat.log` không có dòng nào về `catchup` (lần 1 sau 15:00 rồi Docker tắt; lần 2 lúc `heartbeat` đang SKIP; lần 3 và 4 bị lần chạy thành công sau đó ghi đè lúc 01:05 và 14:04, nên mã thoát cuối đã là 0) | — |
| Chi tiết lần 04/11 23:06 (dòng tổng kết): 1d `DONE: ok=0 err=293 / 293`; 5m `ok=205 err=85 / 290`; thử lại `ok=275 err=18 / 293`, `ok=286 err=4 / 290`; foreign-flow `returned 2`; `[kiem] foreign-flow: thieu ['2026-11-03','2026-11-04']`; `EXIT=1` | Không | — |
| `heartbeat.log`: 1 lần Telegram lỗi, 21/10 14:55, `URLError ... handshake operation timed out`, `ALERT_EXIT=2` (`heartbeat.log:6604-6610`) | Tin "Docker không chạy lúc 14:55" **mất**; tin kế tiếp tới sau | — |
| `bars_closed.log`: **349 dòng** "Loi khi gui tin Telegram" từ 08/10 (205 dòng riêng 27/10, DNS lỗi); `engine_alerts.log`: 2 dòng (04/11 16:16) | Hàng đợi tiến trình dài hạn gửi lại; **0 dòng** "Bỏ 1 cảnh báo", **không có** file `alert_outbox_*` nào tồn tại lúc đo | Hàng đợi dài hạn hoạt động |
| `container-health.log`: 77 lần `EXIT=2` / 2.597 lần; 75 lần là "Docker daemon không chạy" | Đã có tin Docker tắt | — |
| `daily-check` `EXIT=2` 13/10 21:38 | Có `THẤT BẠI` trong `heartbeat.log:5874` (đường mã thoát hoạt động) | Có |
| `engine-consumer` `EXIT=2` 02/10 22:38 | Có `THẤT BẠI` ×3 (`heartbeat.log:4181-4189`) | Có |

---

## 2. Phát hiện (xếp theo mức nghiêm trọng = khả năng hỏng âm thầm × thiệt hại)

| # | Mảng | Hiện trạng (bằng chứng) | Đề xuất | Lợi ích | Rủi ro | Công sức |
|---|---|---|---|---|---|---|
| F1 | Cảnh báo / **mất dữ liệu** | Phép canh tuổi `backup` mù với SKIP: `heartbeat_check.py:369` ghi rõ "dòng SKIP cũng tính là đã được gọi", regex `:376` khớp `backup SKIP`. Dòng khớp cuối trong `backup.log` trước 08/11 là `2026-11-07 02:00:03 backup SKIP`. Khoảng trống dump **120 giờ** (03/11 → 08/11), 54+11 tin Docker tắt, không tin nào nói tuổi dump. `backup_check.py:91-146` (`evaluate_backup_health`) chỉ cần tệp và mtime; chỉ `pg_restore -l` cần Docker (`:262-266`) | Thêm tuổi dump mới nhất (`stat` thư mục sao lưu) và "phiên sổ lệnh chưa ghi" vào nội dung `docker_down_alert._message` (`:166`); hoặc chạy phần kiểm tuổi của `backup_check` ngoài cổng Docker | Biến "Docker tắt" thành "Docker tắt, dump cũ N giờ, N phiên sổ lệnh mất". Tính RPO được trong tin: lần 14:35 06/11 sẽ ghi "84,6 giờ" | Thấp: chỉ thêm đọc tệp | S (<2 giờ) |
| F2 | **Mất dữ liệu / mất máy** | Thư mục sao lưu `D:\My_Vault_Obsidian\Project\_backups` (21 tệp, 1.216 MB trong `db/`) nằm cùng laptop với repo và dữ liệu. Không có `rsync`/`rclone`/`scp` nào trong `backup_db.sh`, `backup_orderbook.sh`, `DEPLOYMENT.md` ngoài kịch bản di chuyển (`DEPLOYMENT.md:1052-1058`). Bản `.env` duy nhất là `_backups/env/envfile_20260929_2353.bak` (2.442 byte, 40 ngày tuổi, cùng máy) | Quyết định của chủ dự án: chọn nơi lưu bản sao ngoài máy (VPS khác, ổ rời, hoặc dịch vụ lưu trữ) cho dump, tar sổ lệnh và `.env`. Việc này vào dịch vụ ngoài nên cần chủ dự án quyết | Mất máy hiện nay = mất DB + sổ lệnh + `.env`. Có bản ngoài máy, RPO khi mất máy từ vô hạn xuống ≤27 giờ (theo thiết kế đợt 215) | Trung bình: gửi dữ liệu ra ngoài (cần mã hoá, chủ dự án quyết) | M (nửa ngày) |
| F3 | Cảnh báo / **hỏng phiên thật** | Scheduler không có đường báo: `trading/scheduler/main.py` và `scripts/startup_catchup.py` không có `send_telegram`, `alert`, `start_outbox` (grep). Chỉ có mã thoát của lần chạy **cuối**. 4/4 lần `catchup` lỗi (02/11, 04/11, 08/11 ×2) không có tin nào. Lần 04/11 kết thúc `EXIT=1`, thiếu khối ngoại 03–04/11 (nạp bù xong 08/11) | Khi `run_job_with_retry` (`main.py:218-270`) vẫn trả 1/2/124 sau lần thử cuối, gửi một tin qua `alert()` với `start_outbox("scheduler")` (đã có mẫu ở collector/engine) | Biết ngay cuối lần thử (≤15 phút sau lỗi) thay vì 10h15' (T2–T5) hoặc 58h15' (T6 21:45) | Thấp: thêm một tin | S–M |
| F4 | Cảnh báo | Mọi kiểm job ngoài giờ chờ cửa sổ `heartbeat`: `heartbeat_check.py:1086-1088` trả 0 trước khi gửi nếu ngoài phiên. Hỏng sau 15:00 T6 → biết 08:00 T2 = **~65 giờ**. Trạng thái `.schedule_health_state.json` ghi lần cuối **02/11 13:56** (Docker tắt, `heartbeat` SKIP 340 lần từ 03/11) nên 6 ngày không có đánh giá nào | Tách phần `evaluate_schedule_health` khỏi cổng phiên: chạy mỗi giờ 24/7 (một dòng lịch thêm) và gửi các tin CRITICAL của 6 job 24/7 ngoài phiên | Độ trễ job 24/7 từ 54–65 giờ xuống ≤1 giờ | Trung bình: có tin ban đêm (đã chấp nhận cho `container-health`, `disk-check`) | M |
| F5 | Cảnh báo | Mã 1 được coi là "bình thường" cho 8 job: `heartbeat`, `daily-check`, `deploy-drift`, `engine-cam`, `engine-consumer`, `backup-check`, `disk-check`, `restore-drill` (`heartbeat_check.py:208-355`); `container-health` và `orderbook-daily-check` coi cả 2 là bình thường. Python gặp exception chưa bắt thoát mã 1; `container_health_check.py:590-592` ép mọi exception thành `sys.exit(2)`. Đã xảy ra thật: `heartbeat.log` có 7 Traceback (5 `UnicodeEncodeError` 01/09 13:00–13:17, 2 `URLError` 14/09 14:25), tất cả `EXIT=1` | Cho crash một mã riêng (ví dụ ngoại lệ chưa bắt → 70) ngoài tập `normal_exit_codes`; hoặc ghi dòng `CRASH:` vào log để `get_last_run_exit_code` nhận ra | Bắt được crash của 10 job hiện nay lọt | Thấp; cần sửa `evaluate_schedule_health` và test | M |
| F6 | Cảnh báo | Gửi một lần, không hàng đợi: `deploy-drift`, `engine-cam`, `engine-consumer`, `orderbook-recorder`, `orderbook-daily-check`, `container-health`, `docker_down_alert`, `refresh_universe` (đối chiếu với `send_with_outbox` chỉ ở 5 job, `DEPLOYMENT.md:478-481`). Lần mất thật: 21/10 14:55 (TLS timeout, `heartbeat.log:6604`). Hai job một lần/ngày (`engine-cam` 15:15, `orderbook-daily-check` 15:30) mất tin là mất 24 giờ | Nối `send_with_outbox` (`_alert_common.py`) cho `engine-cam` và `orderbook-daily-check` trước (mẫu đã có, `alert_and_fail` ở `engine-cam`); phần còn lại tự thử lại theo nhịp | Hết kiểu mất tin im lặng cho hai job hằng ngày | Thấp (mẫu có sẵn; cần test) | S mỗi job |
| F7 | Phục hồi | `restore-drill`: 7 lần `EXIT=0`, 1 lần `EXIT=1` (30/09, sau đó pass); **2 trong 5 Chủ nhật gần nhất bị SKIP** (18/10, 01/11) khi Docker tắt. Lần 08/11: "36 bảng ≥ bản kê", thời gian ≈88 giây (start 04:00:02, log ghi cuối 04:01:30). Không ai canh "ngày lần diễn tập thành công gần nhất" | Thêm vào kiểm tra tuần của `heartbeat` (hoặc `host-preflight`): tuổi dòng `Diễn tập OK` cuối cùng trong `restore-drill.log` >9 ngày → cảnh báo | Hết kiểu "tin rằng restore chạy được" trong lúc 2 tuần liền không diễn tập | Thấp | S |
| F8 | Cảnh báo | Chuỗi canh chéo chỉ cục bộ, trong phiên: `heartbeat` ↔ `container-health` (`container_health_check.py:72-74` chỉ 08:15–15:00); không có tin "còn sống" định kỳ và không có ping ngoài (grep `healthchecks|uptimerobot|cronitor` rỗng). Cả hai chết cùng lúc, hoặc máy chủ chết hẳn → không ai biết cho tới khi chủ dự án tự mở xem | Một tin tóm tắt 08:00 mỗi ngày giao dịch (tuổi lần chạy cuối của các job 24/7, tuổi dump, số tin trong hàng đợi): **không có tin = có gì đó chết**. Tuỳ chọn thứ hai (ping ngoài) vào dịch vụ ngoài nên cần chủ dự án quyết | Thời gian biết "cả hệ thống cảnh báo chết" từ vô hạn xuống ≤1 ngày giao dịch | Thấp (tin tóm tắt); ping ngoài phụ thuộc bên thứ ba | S–M |
| F9 | Cảnh báo | `container-health` không đọc `State.Health` (`:193`): postgres có `healthcheck` (`docker-compose.yml:37`) nhưng trạng thái `unhealthy` không có ai báo. Chỉ `postgres` có `healthcheck`; `collector`, `engine`, `scheduler`, `nats`, `grafana` không có. Scheduler treo (vòng lặp kẹt) giữ container `running` | Thêm `{{.State.Health.Status}}` vào `docker inspect -f` và coi `unhealthy` là CRITICAL; thêm một `healthcheck` nhẹ cho scheduler | Bắt được postgres kẹt nhưng chưa chết | Thấp: đổi định dạng + cập nhật test; `healthcheck` mới chỉ có hiệu lực sau khi tạo lại container | S–M |
| F10 | Cảnh báo | 15 job nằm trong `KHONG_CANH` (`heartbeat_check.py:179-195`): nếu Task bị tắt/xoá thì không ai biết (tuổi không canh). `host-preflight` trên Windows **BỎ QUA** phép kiểm "crontab/Task có đủ job" (9/14 BỎ QUA, 08/11 07:00); trên VPS phép này chạy. Máy dev hiện có 4 Task Disabled có chủ ý, 15 Ready | Với mỗi job khung 24/7 hoặc hằng ngày trong `KHONG_CANH`, thêm canh tuổi theo lịch giao dịch (đã làm ở `engine-cam` qua hệ quả); tối thiểu thêm phép kiểm Task Windows (`Get-ScheduledTask`) cho `host-preflight` | Bắt Task bị tắt trên máy dev | Thấp | M |
| F11 | Cảnh báo | `stream-health` và `host-preflight` không gửi Telegram; `stream-health` thoát 1/2 chỉ có mã thoát. 4 lần `EXIT≠0` (18/09), 0 sự cố kể từ khi chính sách có hiệu lực (02/10) nên chưa chứng minh được tác hại thật | Cho `stream-health` mức CRITICAL (<50%) gửi tin qua `send_with_outbox` | Độ trễ stream coverage thấp từ 16h50' (T2–T5) / 64h50' (T6) xuống tức thì | Thấp | S |

Không có dòng nào đo được ở mức "đã gây mất dữ liệu" ngoài F1/F2 (4 phiên sổ lệnh VN30F không ghi được, đã mất vĩnh viễn: tin Docker tắt ngoài phiên có câu "Nhớ rằng sổ lệnh VN30F không nạp bù được", tin trong phiên thì không).

---

## 3. Đường gửi cảnh báo (trả lời bốn câu hỏi của brief)

- **Gửi đi bằng cách nào.** `trading/telegram.py:14` `send_telegram`: một lần POST `urllib`, timeout 5 giây (`:42`), trả `True` chỉ khi Telegram trả `ok: true`; không bao giờ ném. Thiếu biến môi trường → trả `False` và ghi cảnh báo. Hai lớp bọc: `alert()` (`trading/alerts.py:353`, luồng nền, dùng hàng đợi nếu `start_outbox`) cho tiến trình dài hạn; `send_with_outbox` (`scripts/_alert_common.py`) cho job theo lịch.
- **Gửi lỗi thì sao.** Tiến trình dài hạn (collector, engine): `AlertOutbox` (`alerts.py:69`), file `alert_outbox_<service>.jsonl`, luồng nền thử lại mỗi 60 giây (`:305`), tối đa 200 tin, bỏ tin hỏng vĩnh viễn sau thử lần hai (`:177-284`). Job theo lịch: năm job có hàng đợi (`heartbeat`, `daily-check`, `backup-check`, `disk-check`, `restore-drill`) và gửi lại ở lần chạy kế. Tám job khác (F6) gửi một lần. `container-health` và `docker_down_alert` không ghi trạng thái khi gửi hỏng nên lần chạy kế (≤10') báo lại; vì thế chúng thực tế tự thử lại theo nhịp.
- **Tin kẹt/lỗi từ 01/10.** `ls logs/alert_outbox*` → không có file nào lúc đo. `Bỏ 1 cảnh báo` = 0 dòng trong `bars_closed.log` và `engine_alerts.log`. Lỗi gửi: 349 dòng collector (08/10–08/11), 2 dòng engine (04/11), 1 lần host (21/10) với `ALERT_EXIT=2`; `ALERT_EXIT` cho phần còn lại: 1.224 lần `0` / 1 lần `2` trong `heartbeat.log`, 2.163 / 0 trong `container-health.log`.
- **Dead man's switch cho chính hệ thống cảnh báo.** Có một vòng cục bộ: `container-health` canh `heartbeat` (ngưỡng 15', chỉ 08:15–15:00 ngày giao dịch), `heartbeat` canh `container-health` (ngưỡng 25', chỉ khi `heartbeat` chạy). Thời gian tới khi có người biết `heartbeat` chết: trong phiên ~25 phút; ngoài phiên **không có** (`evaluate_heartbeat_watch` trả `[]`). Biết `container-health` chết: tới **65 giờ**. Cả hai chết, hoặc cả máy: không có ai. Telegram **không biết** nó đã im: không có tin "còn sống" định kỳ.
- **Telegram thật sự tới tay chưa.** Không kiểm được (cấm gửi). Chỉ biết `ALERT_EXIT=0` nghĩa là Telegram API trả `ok: true`.

---

## 4. Phục hồi

**Lần diễn tập gần nhất** (`logs/restore-drill.log`): CN 08/11 04:00:02, `Diễn tập OK: trading_20261108_020012.dump, 36 bảng >= bản kê lúc dump`, `EXIT=0`. Thời gian ≈ 88 giây (log không ghi dòng kết thúc nên lấy mtime 04:01:30 trừ giờ start). Số dòng lớn nhất khớp 100%: `bars_daily` 2.990.578, `foreign_flow_daily` 2.436.999, `bars` 1.591.200. Các lần pass: 30/09 (22:20), 03/10, 04/10 ×2, 11/10, 25/10, 08/11; 18/10 và 01/11 SKIP.

**RPO tệ nhất.**

| Thời kỳ | Thiết kế | RPO tệ nhất | Bằng chứng |
|---|---|---|---|
| Trước đợt 215 | chỉ `backup` 02:00; Docker tắt lúc 02:00 → SKIP | **120 giờ đã xảy ra** | dump 03/11 02:00 → 08/11 02:00 |
| Sau đợt 215 (ef4e9c1, deploy lúc 14:03 08/11) | `backup-makeup` mỗi giờ, dump bù khi dump cũ ≥26 giờ (`BACKUP_SKIP_IF_NEWER_HOURS=26`, `sched.sh`; Task `trading-backup-makeup` Ready, lần cuối 14:15 `LastResult=0`) | **≤27 giờ khi Docker chạy**. Khi Docker tắt vẫn **không giới hạn** (không dump được) | `backup-makeup.log` 2 lần `EXIT=0` |
| Mất máy | không có bản ngoài máy (F2) | **vô hạn** | không có cơ chế chép ra ngoài |

**RTO ước tính** (từ lúc mất volume tới lúc engine chạy lại). Chưa có số đo đầu–cuối; `DEPLOYMENT.md` không ghi RTO. Thành phần đo được: khôi phục 150 MB vào database nháp + so 36 bảng ≈ 88 giây (08/11). Thành phần chưa đo: dựng lại image (không có số trong log), `pre_restore/post_restore` TimescaleDB (`DEPLOYMENT.md` §6, dòng 248–258), gia hạn token SSI bằng OTP thủ công (`RUNBOOK_OTP_AUTH.txt`, `DEPLOYMENT.md` §8.5) và kiểm 6 con số sau khôi phục (§11 Bước 6). Phần OTP phụ thuộc người nên RTO có cận dưới ≈ vài phút máy + thời gian người, không có cận trên.

**Thứ không nằm trong backup DB** (chỉ ghi tên, không mở file bí mật):

| Thứ | Nằm ở đâu | Lấy lại từ đâu nếu mất máy |
|---|---|---|
| `.env` (khoá SSI, Telegram, đường dẫn sao lưu) | gốc repo | Chỉ có `D:\...\_backups\env\envfile_20260929_2353.bak` (cùng máy, 40 ngày tuổi). **Không có bản ngoài máy** |
| `config/config.yaml` (1.210 byte) | repo | git (`origin` GitHub; nhánh `main` đang ahead 1 commit) |
| Token SSI | bảng `ssi_auth_state` (1 hàng, có trong dump) | trong dump, nhưng hết hạn nên cần OTP thủ công |
| `data/orderbook/` (249 MB) | máy | `orderbook-backup` chép tăng dần vào cùng thư mục `_backups/db` (tar mới nhất 03/11, 8 MB). Phiên 03–06/11 chưa từng được ghi |
| `data/dnse_trades/` (145 MB), `crypto_footprint_v2/` (77 MB), `research*/` (~55 MB) | máy, `.gitignore: /data/` | Không có bản sao lưu. Ghi chú dự án cho biết cửa sổ lịch sử DNSE trượt ~200 ngày nên phần cũ có thể không tải lại được |
| `logs/` (trạng thái cảnh báo `.schedule_health_state.json`, `.prev_day_*_state.json`, hàng đợi) | máy, `.gitignore: logs/` | Không cần lấy lại; mất chỉ làm lặp một số tin |
| Image Docker | máy | dựng lại từ repo |

---

## 5. An toàn vận hành

**Cổng.** `docker-compose.yml` bind `127.0.0.1` cho 5432, 4222, 4223, 3000 (`:35,49,64,144`). `docker ps` cho cùng bốn cổng, `engine`/`collector`/`scheduler` không publish cổng nào. `netstat -ano -p TCP`: không có cổng dự án nào ở `0.0.0.0`. Thử kết nối TCP: loopback 4 cổng **mở**, IP LAN của máy 4 cổng **đóng/không kết nối**.

**Bí mật trong image** (`docker history --no-trunc` + `ls`, không `cat`). Ba image `collector`/`engine`/`scheduler`: các lệnh `ENV` chỉ có `PATH`, `PYTHON_VERSION`, `PYTHON_SHA256`, `GPG_KEY` (khóa công khai của Python), `LANG`; không có `ARG`/`ENV` nào mang khoá hay token. `/app` chỉ có `.venv`, `config/` (một tệp `config.yaml`), `scripts/`, `trading/`; không có `.env`, `logs/`, `data/`; tên tệp chứa "token/secret" ngoài `.venv` chỉ có `scripts/load_token_to_db.py` (mã nguồn). `.dockerignore` loại `.env`, `.git`, `.gitnexus`. Lưu ý: image có kèm các script đặt lệnh thật (`confirm_real_order.py`, `drill_place_cancel_order.py`, `bingx_drill_place_cancel.py`), nhưng chúng cần khoá nằm ở môi trường container (không có trong image).

**Grafana.** `GRAFANA_ADMIN_PASSWORD` **có đặt giá trị** trong `.env` (kiểm bằng đếm dòng, không in). `docker-compose.yml:146` vẫn có mặc định `admin` nếu biến trống. Biến Telegram (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) cũng có giá trị.

**Cổng chặn lệnh thật** (kiểm bằng code và test, không gọi API):

| Cổng | `file:dòng` | Test đang bảo vệ |
|---|---|---|
| G1. Engine không có đường đặt lệnh, chỉ ghi `pending_real_orders` + cảnh báo. Chỗ gọi `place_limit_order`: `scripts/confirm_real_order.py:156`, `drill_place_cancel_order.py:339`, `bingx_drill_place_cancel.py:343` (đều chạy tay) | `trading/real_orders.py:71-90` (docstring "KHÔNG gọi bất kỳ API đặt lệnh nào") | `tests/test_real_orders.py` |
| G2. Cờ `real_trading_enabled: false` (`config/config.yaml:14`, đọc ở `trading/config.py:83`); `false` → chỉ ghi DB, không gọi SSI | `confirm_real_order.py:97-112` | `test_confirm_real_order.py:104` (dry-run không gọi `place_order`), `test_real_trading_guard.py:259`; `host_preflight.py:351` kiểm hằng tuần |
| G3. Phải gõ `YES` bằng tay (`input()`) | `confirm_real_order.py:92,242` | `test_confirm_real_order.py:90` |
| G4. Lệnh phải `pending` và chưa hết hạn | `confirm_real_order.py:74` | `:143` |
| G5. BUY phải bội số 100 | `confirm_real_order.py:83` | `:127` |
| G6. Sức mua/bán thật tại lúc xác nhận phải đủ | `confirm_real_order.py:132` | `:316`, `:360` |
| G7. Vị thế đồng bộ không quá 15 phút và có dòng (fail-safe) | `real_orders.py:94,104,252,262` (`POSITION_MAX_AGE_MINUTES=15`, `:18`) | `test_real_orders.py:413`, `:472` |
| G8. Sức mua không quá 15 phút và có dòng | `real_orders.py:129,140` (`BUYING_POWER_MAX_AGE_MINUTES=15`, `:15`) | `test_real_orders.py:211`, `:228` |
| G9. Hàng rào chống tái phát "SMA cross không sinh bear": test ghim | — | `test_real_trading_guard.py:195-259` |

Điểm yếu còn lại: G1–G8 đều là cổng **mềm** chống lệnh nhầm bằng quy trình; người chạy `confirm_real_order.py` bằng tay và gõ `YES` là cổng cuối. `real_trading_enabled` chỉ đổi bằng sửa file `config.yaml` (đã có `host-preflight` kiểm tuần, nhưng trên Windows phép này chạy: "ĐẠT 5").

---

## 6. Đã ổn, không cần làm

| Mục | Số liệu |
|---|---|
| Cổng mạng | 4 cổng chỉ loopback; từ IP LAN không kết nối được; không cổng nào ở `0.0.0.0` |
| Bí mật trong image | 3 image sạch, `/app` không có `.env`/`logs`/`data` |
| Grafana, Telegram | `GRAFANA_ADMIN_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` đều có giá trị |
| Cổng đặt lệnh thật | 8 cổng có test (bảng §5) |
| Đường gửi tin trong ca Docker tắt | 1.225 lần `ALERT_EXIT` trong `heartbeat.log`: 1.224 thành công, 1 lần hỏng (21/10) |
| Hàng đợi tiến trình dài hạn | 0 tin bị bỏ, 0 file `alert_outbox_*` tồn đọng |
| Phát hiện backup hỏng thật | `backup-check` 10 lần `EXIT=1`, tất cả có tin CRITICAL (tar sổ lệnh cũ 27,3h → 192,5h; dump cũ 30,6h) |
| Phục hồi | `restore-drill` 08/11: 36 bảng khớp 100%, ≈88 giây |
| `catchup` sau đợt 215 | image deploy 14:03 08/11; lần chạy 14:04 có dòng `finish dur=11.40s`, `EXIT=0` |
| `container-health` | 2.518 lần `EXIT=0`; 75/77 lần `EXIT=2` là "Docker daemon không chạy" (đã có tin) |
| `deploy-drift` | lần `EXIT=1` cuối 23/10; từ đó 11 lần `EXIT=0` |
| Kiểm kết quả hằng ngày | `prev_day_*` phủ nến ngày, khối ngoại, nến 5 phút |
| `docker_down_alert` | 54 tin trong phiên (03–06/11) và 11 tin ngoài phiên đều `ALERT_EXIT=0` |
| Docker daemon tắt | có tin trong phiên ≤30 phút, ngoài phiên ≥2 giờ rồi 6 giờ/tin |

---

## 7. Chưa kiểm được

| Mục | Lý do |
|---|---|
| Telegram có tới tay người nhận không | cấm gửi/gọi API; chỉ biết `ok: true` |
| Bản sao `D:\My_Vault_Obsidian` có được đồng bộ ra ngoài máy bởi công cụ khác (Obsidian Sync/OneDrive) không | không có bằng chứng trong repo; không kiểm cấu hình máy |
| `crontab` thật của VPS và độ trễ trên VPS | máy đo là Windows; bảng §1 tính theo Task Windows |
| Tải `heartbeat` lúc 08:00 thứ Hai sau 6 ngày trạng thái đóng băng | chỉ có thể đo vào thứ Hai (kịch bản §8, M1) |
| RTO đầu–cuối (build image, OTP) | cần diễn tập thật, bị cấm |
| `healthcheck` của collector/engine/scheduler/nats | chưa có thì chưa đo; đề xuất F9 |
| Ngưỡng và hành vi của `Watchdog` trong collector (`watchdog.py`) khi mạng SSI chết ngoài giờ | chỉ đọc chữ, không mô phỏng |
| NAV/vị thế snapshot, `bars_derivative`, `binance_*` có phép kiểm tuổi riêng không | chỉ quét `heartbeat_check` và `daily_data_check`; chưa duyệt từng loader |

---

## 8. Kịch bản đo cho phiên thứ Hai 09/11 (chỉ lập, không đo hôm nay)

Mọi lệnh **chỉ đọc**. Giờ là giờ VN. Container: `ai_auto_trading_system-<service>-1`.

| # | Mục | Giờ | Lệnh | Ghi lại |
|---|---|---|---|---|
| M1 | `heartbeat` chạy lần đầu sau 6 ngày | 08:00–08:10 | `tail -n 30 logs/heartbeat.log`; `ls -l --time-style=full-iso logs/.schedule_health_state.json`; đọc file trạng thái | giờ dòng `heartbeat-check start` đầu tiên; `EXIT=`; có dòng `THẤT BẠI`/`NGỪNG CHẠY`/`ĐÃ CHẠY LẠI` nào; mtime file trạng thái (hiện 02/11 13:56) |
| M2 | `container-health` canh `heartbeat` | 08:15–08:30 | `tail -n 20 logs/container-health.log` | có dòng "heartbeat check NGỪNG CHẠY" không (kỳ vọng không) |
| M3 | `catchup` 06:40 (có `finish dur=` từ đợt 215) | 06:35 và 06:55 | `docker stats --no-stream`; `tail -n 12 logs/catchup.log` | `dur=` giây; RAM scheduler/postgres trước–sau |
| M4 | `memory.events` postgres quanh `backup` 02:00 | 01:55 và 02:10 (đêm CN → T2) | `docker exec ai_auto_trading_system-postgres-1 sh -c 'cat /sys/fs/cgroup/memory.events'` (hai lần); `docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}'` | hiệu `max`, `oom`, `oom_kill` giữa hai mốc; mốc đối chiếu đợt 214: `max` = 12.464, `oom_kill` = 0 |
| M5 | `docker stats` trong phiên (3 lần) | 09:30, 11:00, 13:30 (+14:35 ATC) | `docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.MemPerc}} {{.CPUPerc}}'` | RAM/CPU từng container so `mem_limit`/`cpus` (`docker-compose.yml`) |
| M6 | Nhịp collector/engine | 09:30, 11:00, 13:30 | `docker compose exec -T postgres psql -U trading -d trading -c "select service,last_seen,now()-last_seen as tuoi from heartbeat order by 1"` | tuổi từng nhịp (ngưỡng canh 300 giây) |
| M7 | Tuổi nến mới nhất | 09:30, 11:00, 13:30 | `... -c "select max(ts), now()-max(ts) from bars where symbol in ('HPG','IJC','AAA')"` | tuổi nến (nến 5 phút đóng; ngưỡng canh 15 phút). Bảng `bars` không có cột thời điểm chèn nên độ trễ chỉ đo từ log (M8) |
| M8 | Độ trễ nến đóng → engine xử lý | sau 15:10 | `uv run python scripts/measure_bar_latency.py` (chỉ đọc hai log `logs/bars_closed.log`, `logs/engine_alerts.log`, chỉ in số) | p50/p90/p99/max cho collector, engine, hiệu số; theo khung mở cửa/giữa phiên/ATC |
| M9 | NATS BARS và consumer | 09:30 và 14:35 | `docker exec ai_auto_trading_system-collector-1 python -c "import asyncio,nats\nasync def m():\n nc=await nats.connect('nats://nats:4222'); js=nc.jetstream()\n s=await js.stream_info('BARS'); print(s.state.messages, s.state.bytes)\n async for c in js.consumers_info('BARS'): print(c.name, c.num_pending, c.num_ack_pending)\n await nc.close()\nasyncio.run(m())"` (không kéo, không ack; cách đã dùng ở đợt 214) | số tin/byte của stream; `num_pending`, `num_ack_pending` |
| M10 | Tin hỏng/hàng đợi | 08:30 và 15:30 | `ls logs/alert_outbox_* 2>/dev/null`; `grep -c "Loi khi gui tin Telegram" logs/bars_closed.log logs/engine_alerts.log` | file hàng đợi có xuất hiện không; số dòng lỗi gửi tăng bao nhiêu so với 349 và 2 |
| M11 | Các Task chạy đúng giờ | 09:15 và 15:45 | PowerShell: `Get-ScheduledTask -TaskName 'trading-*' \| % { $i=Get-ScheduledTaskInfo $_; "$($_.TaskName) $($i.LastRunTime) $($i.LastTaskResult)" }` | `LastRunTime`/`LastTaskResult` của `heartbeat`, `engine-consumer`, `deploy-drift`, `orderbook-recorder`, `stream-health`, `engine-cam`, `orderbook-daily-check` |
| M12 | Lượng tin Telegram sinh ra | 15:45 | `grep -c "^\[CRITICAL\]\|^\[WARN\]" logs/heartbeat.log logs/engine-consumer.log` và đọc 20 dòng cuối từng log | số tin cảnh báo thật so với số lần chạy (độ ồn) |

Những phép đo cần người thức tại giờ cố định (M4 ở 01:55/02:10, M3 ở 06:35) cần Lead quyết cách lấy mẫu; tôi **không** đăng ký tác vụ hẹn giờ.

---

## 9. Lệnh đã chạy

Đọc code: `heartbeat_check.py` (1–360, 358–650, 870–905, 1000–1326), `_alert_common.py`, `alerts.py`, `telegram.py`, `docker_down_alert.py`, `run_if_docker_up.sh`, `container_health_check.py`, `backup_check.py`, `backup_db.sh`, `trading/scheduler/main.py` (1–270), `confirm_real_order.py`, `real_orders.py`, `DEPLOYMENT.md` §6–§11, `docker-compose.yml`.

Log: `grep -c` / `awk` trên `heartbeat.log`, `backup.log`, `backup-check.log`, `backup-makeup.log`, `catchup.log` (dòng 263–404 cho `DONE:`/`[kiem]`/`EXIT=`), `container-health.log`, `restore-drill.log`, `host-preflight.log`, `orderbook-recorder.log`, `bars_closed.log`, `engine_alerts.log`.

DB: `select ... from heartbeat`, `select max(ts) from bars / bars_daily` (chỉ `SELECT`).

Hệ thống: `docker ps/images/inspect/history --no-trunc`, `docker run --rm --entrypoint sh <image> -c 'ls -la /app ...'`, `docker logs --since ... scheduler`, `netstat -ano -p TCP`, TCP connect thử tới 127.0.0.1 và IP LAN, `Get-ScheduledTask`/`Get-ScheduledTaskInfo`, `Get-ChildItem` thư mục sao lưu (tên tệp, kích thước, giờ), `git remote -v`.

Có hai lần hook `.agentignore` chặn lệnh (mẫu `*.pem` và `.env` trong dòng lệnh); tôi bỏ các mẫu đó và không vòng qua.

## Audit của Claude (Lead), 08/11/2026

Tôi đã tự kiểm lại F1, F3, F4 và F5 trên code và log: cả bốn đều đúng.

- **F1:** `heartbeat_check.py:369` có ghi chú "dòng SKIP cũng tính là đã được gọi". Regex ở `:376` khớp với mọi dòng mang nhãn job, nên dòng `backup SKIP` cũng được tính. `backup.log` có 20 dòng SKIP trên 49 lần gọi.
- **F3:** `grep telegram|alert|outbox` trên `trading/scheduler/main.py` và `scripts/startup_catchup.py` không ra kết quả nào.
- **F4:** `heartbeat_check.py:1086-1088` `return 0` khi ngoài cửa sổ kiểm. File `logs/.schedule_health_state.json` được ghi lần cuối lúc 02/11 13:56.
- **F5:** có 10 policy có `normal_exit_codes` chứa 1. `container_health_check.py:590-592` biến mọi exception thành `exit(2)`.

**Quyết định của chủ dự án đang chờ:**
- **F2:** sao lưu ra ngoài máy, tức đưa dữ liệu ra một dịch vụ bên ngoài.
- **F8:** ping ra một dịch vụ bên ngoài để có dead man's switch.

Hai mục này không giao agent làm khi chưa có quyết định.
