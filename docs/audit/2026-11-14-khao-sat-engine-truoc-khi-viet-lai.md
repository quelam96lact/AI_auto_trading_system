# Khảo sát engine trước khi dừng và viết lại theo nến ngày (đợt 228)

Người khảo sát: Researcher. Brief: `docs/superpowers/plans/2026-11-13-brief-dot-228-khao-sat-engine-truoc-khi-viet-lai.md`. Chỉ đọc code, log, DB (SELECT). Không sửa file nào ngoài báo cáo này, không dừng/restart container, không chạy script kiểm tra thật (kể cả `--dry-run`), không ghi DB, không mở `data/research227/`, không đọc `scripts/research227_*`, không đọc `.env` hay file token. Không có số tài khoản, token hay ID trong báo cáo.

Quy ước: **[đo]** = số lấy từ log/DB/lệnh có kèm lệnh; **[đọc]** = đọc code (có `file:dòng`); **[suy luận]** = kết luận từ code mà tôi chưa quan sát chạy thật; **[chưa kiểm]** = chưa đọc hết hoặc không thể kiểm.

Trạng thái: **A, B, C, D đều xong** (đo và đọc ngày 13/11, đến ~23:30). A đã báo Lead trước; C kèm trả lời ba câu của Lead (xem C.3, B.6); B và D xong sau. Chỗ chưa đo được: giờ nạp `bars_daily` của 10 phiên (D.1). Cuối báo cáo có danh sách câu hỏi cần quyết.

---

## A. Dừng container engine thì cái gì kêu?

### A.0. Tóm tắt

- **Chỉ `docker compose stop engine` (container còn tồn tại, trạng thái `exited`) sẽ gây ra bốn nguồn tin:**
  1. `container-health`: **1 tin** `[CRITICAL] … engine-1: container không ở trạng thái running (Status: exited)` trong vòng 10 phút sau khi dừng (job chạy 24/7).
  2. `heartbeat` (dead-man): **~60–63 tin/ngày giao dịch**, mỗi 5 phút trong 08:00–11:30 và 13:00–14:45, nội dung `[CRITICAL] service ngừng heartbeat quá 300s: engine`. **Không có chống lặp.**
  3. `engine-consumer`: từ khoảng **39 phút sau khi mở phiên** (hoặc sau lúc dừng, nếu dừng trong phiên), tin `🚨 CHUÔNG 2C (Engine Consumer) … num_pending vượt ngưỡng`, lặp **mỗi ≥15 phút** (≤ 19 tin/ngày), kéo dài tới khi consumer được xoá.
  4. `deploy-drift` (08:00 T2–T6): **chỉ khi** image của engine cũ hơn commit mới nhất chạm `trading/` (rất có thể xảy ra ngay khi bắt đầu viết lại engine): 1 tin/ngày, không chống lặp.
- **Ba tin chỉ phát sinh nếu làm *khác* `stop`:** xoá container (→ `container-health` kẹt `EXIT=4` mỗi 10 phút và `deploy-drift` báo "container KHÔNG chạy" mỗi sáng), xoá consumer NATS `engine` (→ `engine-consumer` gửi tới ~50 tin/ngày không có cooldown), hoặc sửa/xoá `trading/engine/main.py` (→ `heartbeat_check.py` và `check_silent_engine.py` thoát mã 1 im lặng vì `from trading.engine.main import …` ở mức module, xem A.3: mất toàn bộ chuông dead-man mà không có tin nào).
- **Không còn job nào khác phụ thuộc engine** trong 23 nhánh `SCHEDULE_EXIT_POLICIES` (xem bảng A.5; đã đối chiếu đủ 23/23; ghi rõ cái nào đọc kỹ, cái nào chỉ grep).
- **Không có Grafana alert**; Grafana chỉ có dashboard (bảng, không ngưỡng).
- **Collector không phụ thuộc engine** (không có `depends_on` engine, không đọc consumer của engine).
- **Docker Desktop khởi động lại:** engine cấu hình `restart: unless-stopped` → theo tài liệu Docker, container đã bị dừng thủ công **không** tự chạy lại sau khi daemon khởi động lại [suy luận; không kiểm được vì cấm dừng]. Nhưng **`docker compose up -d` (không nêu tên dịch vụ) sẽ chạy lại engine cũ**, và `deploy-drift` còn in sẵn lệnh gợi ý `docker compose up -d --no-deps collector engine scheduler` (A.2, dòng :113).

### A.1. Bảng "nếu chỉ `docker compose stop engine`, tin nào gửi, vào giờ nào"

Lịch chạy lấy từ `DEPLOYMENT.md:635-655` (Windows Task) và số lần chạy thực đo trong log.

| # | Job (file:dòng) | Điều kiện kích hoạt | Giờ kiểm | Tin gửi (mức, nội dung) | Số tin / chống lặp |
|---|---|---|---|---|---|
| 1 | `container-health` — `container_health_check.py:69` (`DEFAULT_SERVICES` có `engine`), `:401-410` | Trạng thái chuyển `running` → `exited` | Mỗi 10 phút, 24/7 (`DEPLOYMENT.md:637`) | `[CRITICAL] ai_auto_trading_system-engine-1: container không ở trạng thái running (Status: exited)` | **1 tin**, sau đó chỉ ghi log `INFO … vẫn ở trạng thái exited (đã báo trước đó)` và thoát `EXIT=0` (`:407-410`). Gửi trong ≤10 phút kể cả ban đêm/Chủ nhật |
| 2 | `heartbeat` — `heartbeat_check.py:85` (`SERVICES = ("collector","engine")`), `:1690`, `:1720-1724` | Hàng `engine` trong bảng `heartbeat` cũ hơn `HEARTBEAT_MAX_AGE_SECONDS` = 300 giây (`:86`), hoặc không có hàng | Cửa sổ kiểm `:1670-1678`: 08:00–08:59 (tiền phiên) + 09:00–11:30 + 13:00–14:45, ngày giao dịch. Task 5 phút/lần 08:00–15:00 T2–T6 (`DEPLOYMENT.md:635`) | `[CRITICAL] service ngừng heartbeat quá 300s: engine` | Mỗi lần chạy trong cửa sổ, **không có chống lặp** (chỉ lịch job có trạng thái). **[đo]** số lần chạy nằm trong cửa sổ: 63 (22/10), 61 (09/11), 60 (13/11) → **≈60–63 tin/ngày**. Tin đầu tiên: **08:00 sáng ngày giao dịch kế tiếp** (nếu dừng cuối tuần: 08:00 thứ Hai 16/11) |
| 3 | `engine-consumer` — `engine_consumer_check.py:96-97`, `:140-142`, `:172-185`, `:40` | Trong giờ giao dịch (`is_trading_time`: 09:00–11:30, 13:00–14:45); `num_pending ≥ 20` (consumer bền `engine` vẫn còn trên NATS) | Task 5 phút/lần 09:00–15:10 T2–T6 (`DEPLOYMENT.md:639`); **[đo]** 49–50 lần/ngày nằm trong giờ giao dịch (09/11: 50, 13/11: 49) | `🚨 CHUÔNG 2C (Engine Consumer): Phát hiện sự cố tiêu thụ bar: num_pending vượt ngưỡng (N >= 20)` | Cooldown 900 giây (`:40`, `:178`): tối đa mỗi 15 phút, ≤ 11 tin (09:00–11:30) + 8 tin (13:00–14:45) = **≤ 19 tin/ngày** (thực tế có thể ít hơn do lệch giờ chạy vài giây). **[đo]** tốc độ tích: stream `BARS` thêm ~131 tin/ngày giao dịch (09/11: 30711→30842; 13/11: 30845→30976 theo `logs/engine-consumer.log`) → chạm 20 sau **≈39 phút giao dịch**; từ ngày thứ hai trở đi tin đầu lúc 09:00 |
| 4 | `deploy-drift` — `deploy_drift_check.py:41` (`SERVICES` có `engine`), `:102-114`, `:163-198` | Image của container engine **cũ hơn** commit mới nhất chạm `trading/` (`:43-47`). `docker inspect -f {{.Image}}` vẫn chạy được trên container đã dừng (chỉ trả `None` khi container không tồn tại, `:178-179`), nên **dừng thôi không kích hoạt, nhưng không dựng lại image sau khi `trading/` đổi thì kích hoạt** | 08:00 T2–T6 (`DEPLOYMENT.md:636`) | `[deploy-drift] engine: image CŨ hơn commit gần nhất chạm trading/ (N giờ M phút) — dựng lại container (docker compose build collector engine scheduler && docker compose up -d --no-deps collector engine scheduler)` | 1 tin/ngày giao dịch cho tới khi image engine được dựng lại; **không chống lặp** (`alert_and_fail` mỗi lần). Collector và scheduler cũng bị báo cùng lúc nếu `trading/` đổi mà không rebuild |

Ghi chú thêm cho bảng:

- **Hàng `heartbeat`/`schedule`:** các cảnh báo "job theo lịch" của `heartbeat_check.py` (`evaluate_schedule_health`, `:691-980`) **không** có engine; chỉ canh `container-health`, `heartbeat`, `disk-check`, `backup`, `orderbook-backup`, `backup-check` (24/7) và mã thoát của 23 nhánh. Dừng engine không làm hỏng mã thoát của job nào: `container-health` vẫn `EXIT=0`/`1`, `engine-consumer` `EXIT=1` thuộc `normal_exit_codes={0,1}` (`:271-277`).
- **Giờ dừng gợi ý để tránh tin trùng:** dừng engine vào buổi tối/cuối tuần, **sau 15:10 thứ Sáu hoặc trước 08:00 sáng thứ Hai**, để tin 1 (một tin duy nhất, ≤10 phút sau khi dừng) không lẫn trong phiên; nhưng tin 2 và 3 vẫn bắt đầu từ sáng thứ Hai nếu không sửa gì.

### A.2. Hai ca "không phải `stop`" (rủi ro khi dọn dẹp)

| Thao tác | Tin | Chi tiết |
|---|---|---|
| `docker compose rm`/`down`/ xoá service `engine` khỏi `docker-compose.yml` (container không còn tồn tại) | `container-health`: 1 tin `[CRITICAL] …engine-1: lỗi đọc container (…)` rồi **`EXIT=4` mỗi 10 phút kéo dài** (`container_health_check.py:306-325`, `:680-681`; `EXIT=4` không thuộc `normal_exit_codes={0,1,2}` của `container-health`, `heartbeat_check.py:257-263`) → `schedule-watch` (hằng giờ phút :07, `DEPLOYMENT.md:650`) báo **1 tin** `[CRITICAL] job theo lịch 'container-health' THẤT BẠI … mã thoát 4` (`heartbeat_check.py:878-888`) | `deploy-drift` thêm `[deploy-drift] engine: container KHÔNG chạy — không xác nhận được đang chạy code hiện tại` mỗi sáng 08:00 T2–T6 (`deploy_drift_check.py:97-101`). `docker inspect` trả mã ≠0 → `status="missing"` (`container_health_check.py:213-226`) |
| Xoá consumer bền `engine` trên NATS (hoặc xoá stream `BARS`) | `engine-consumer`: `🚨 CHUÔNG 2C: [engine-consumer] LỖI: Không thể kết nối NATS hoặc đọc consumer 'engine': …` **mỗi lần chạy trong giờ giao dịch, không cooldown** (`engine_consumer_check.py:144-150`: `send_telegram` gọi thẳng) → **≈49–50 tin/ngày** [suy luận từ code + số lần chạy đo được] | Hàng chờ không còn tích (pending=0) nhưng lỗi vẫn báo |

### A.3. Rủi ro gián tiếp: hai script giám sát **import** từ `trading/engine/main.py`

| Script | Dòng | Phụ thuộc | Hậu quả nếu `trading/engine/main.py` bị đổi/xoá |
|---|---|---|---|
| `scripts/heartbeat_check.py` | `:81` `from trading.engine.main import CAPITAL`; dùng ở `:1132` (`capital: float = CAPITAL`) và `:1735` | hằng `CAPITAL = 100_000_000.0` (`trading/engine/main.py:31`) | `ImportError` xảy ra ở mức module, **ngoài** khối `try` của `__main__` (`:1920-1925`, chỉ bọc `main()`), nên Python in traceback và thoát **mã 1**, không phải 3. Mã 1 thuộc `normal_exit_codes={0,1}` của `heartbeat` (`:215-221`) → **không bị coi là lỗi**. **Cùng file chạy ba nhánh**: `heartbeat` (5 phút), `schedule-watch` (hằng giờ), `morning-summary` (08:00) → **toàn bộ chuông dead-man chết cùng lúc và im lặng**; `schedule-watch` (người đọc mã thoát) cũng là cùng file nên không tự báo được, còn `container-health` canh chéo chỉ thấy dòng `heartbeat-check start` vẫn được ghi [suy luận từ import ở `:81`, `sched.sh` và ngữ nghĩa Python; chưa chạy thử] |
| `scripts/check_silent_engine.py` | `:28` `from trading.engine.main import _default_strategy` | hàm trả về `OctopusPullbackStrategy()` (`main.py:76-120`) | Cùng cơ chế: `engine-cam` (15:15) thoát **mã 1**, thuộc `normal_exit_codes={0,1}` (`heartbeat_check.py:264-270`) → **im lặng**. Nếu `symbols` rỗng: `EXIT=2` (`check_silent_engine.py:185-190`, không thuộc mã bình thường) → `schedule-watch` báo `THẤT BẠI … mã thoát 2` |

Hai tệp `scripts/` khác import `trading.engine`: **không có** (grep `trading\.engine` trong `scripts/` và `trading/` ngoài `trading/engine/` chỉ ra hai dòng trên). **9 tệp test** trong `tests/` cũng import `trading.engine` (kể tên ở B.6).

### A.4. Các chỗ phụ thuộc khác đã đọc (không gây tin khi `stop`, nhưng ảnh hưởng thiết kế)

| Chỗ | file:dòng | Phụ thuộc engine? | Ghi chú |
|---|---|---|---|
| `heartbeat` — bất biến sổ sách (2C) | `heartbeat_check.py:1696-1737`, `:1131-1139` | Đọc `engine_state` (id=1) và `positions` (`qty != 0`); báo `[CRITICAL] hai sổ sách LỆCH` nếu `cash + Σ(avg_price×qty) − CAPITAL − realized_pnl` lệch > 1.000 VND | Engine dừng → số không đổi → **không kêu**. Nhưng **engine mới** dùng lại hai bảng này với ngữ nghĩa khác (vốn, nhiều mã, T+2 ngày) sẽ làm bất biến này kêu giả hoặc im lặng sai; xem D |
| `heartbeat` — nến mới (2A) | `heartbeat_check.py:1599-1607`, `:1692-1695`, `:1738-1752` | Đọc `bars` theo **`cfg["symbols"]`** của `config/config.yaml` (3 mã) | Không phụ thuộc engine, nhưng phụ thuộc **danh sách `symbols`**: nếu `symbols` đổi mà collector không stream cùng danh sách, `bar_stale` báo `[CRITICAL] dữ liệu ngừng chảy`; nếu rỗng, truy vấn `IN ()` lỗi → `[CRITICAL] heartbeat check không đọc được DB` mỗi 5 phút |
| `heartbeat` — vị thế thật | `heartbeat_check.py:1775-1791` | Đọc `account_sync_log` của `real_order_account` (collector ghi) | Không phụ thuộc engine |
| `deploy-drift` / `check_golive_gate` | `check_golive_gate.py:131-152`, `:438-448` | Gọi lại `deploy_drift_check` | `check_golive_gate.py` **không** nằm trong `sched.sh`/Windows Task (chạy tay); chỉ ghi nhận |
| `morning-summary` | `heartbeat_check.py` (`build_morning_summary`; grep `engine` trong phần này: 0) | Đếm file `alert_outbox_*.jsonl` trong `logs/` | Không đọc engine. Nếu engine để lại `alert_outbox_engine.jsonl` chưa gửi (`trading/engine/main.py:837` `start_outbox("engine")`, `trading/alerts.py:350`) thì mục "Hàng đợi cảnh báo" hiện N tin chờ vĩnh viễn. **[đo]** hiện 0 tin chờ (`morning-summary` 08:00 13/11) |
| `docker_down_alert` | `docker_down_alert.py:176` | Câu chữ "Collector/engine đều dừng" khi **Docker** tắt | Không liên quan `stop engine` |
| `host_preflight` | grep `engine`: 0 | Kiểm cổng compose, không kiểm sống/chết | Không liên quan |
| Grafana | `grafana/provisioning/dashboards/trading.json` panel 8 `engine_state`, 2 `pnl_daily`, 3 `positions`, 4 `heartbeat` | Hiển thị dữ liệu engine | **Không có alert rule** (chỉ có `dashboards/` và `datasources/`; không có thư mục `alerting`; `alert` không xuất hiện trong JSON). Bảng "Sức khoẻ service" sẽ cho `age_seconds` của engine tăng dần, không có ngưỡng màu |
| `docker-compose.yml` | `:71-96` engine; `:90-92` `depends_on: postgres(healthy), nats(started)`; `:93` `restart: unless-stopped` | Engine phụ thuộc postgres, NATS | **Collector** (`:99-121`) và **scheduler** (`:122-143`) **không** `depends_on` engine. Chỉ engine `volumes: ./logs:/app/logs` ghi `logs/engine_alerts.log` (`engine/main.py:829`) |
| Collector | grep `engine\|consumer_info\|durable` trong `trading/collector/`: chỉ chú thích (`account_sync.py:201`, `main.py:99,111`) | Chỉ **publish** lên JetStream `BARS` (`trading/bus/publisher.py`), không đọc consumer | Stream giữ tối đa 7 ngày (`publisher.py:13` `STREAM_MAX_AGE_SECONDS = 7*24*3600`) → hàng chờ engine tích tối đa 7 ngày |
| Scheduler | `trading/scheduler/main.py` (grep `engine`: 1 dòng chú thích `:146`) | Không | Chạy `catchup` (khi khởi động, 06:40, 21:45; `:45-46`, `:354-437`), `daily-check` (21:45) và `universe-refresh` (`:466-483`); không gọi engine |

### A.5. Danh sách đã đối chiếu đủ 23 nhánh `SCHEDULE_EXIT_POLICIES` (`heartbeat_check.py:214-376`)

"Đọc" = đọc phần liên quan engine trong code. "Grep" = tìm các từ `engine|positions|engine_state|pnl_daily|FROM heartbeat|paper|PaperBroker|orders|nats|consumer|trading.engine` trong file, **0 kết quả** (ghi rõ nếu có); chưa đọc từng dòng.

| # | Nhánh | Script | Liên quan engine? | Cách đối chiếu |
|---|---|---|---|---|
| 1 | `heartbeat` | `heartbeat_check.py` | **Có** (A.1 #2, A.3, A.4) | Đọc `:60-130`, `:150-376`, `:691-1140`, `:1480-1925` |
| 2 | `daily-check` | `daily_data_check.py` | Không | Grep: 0 kết quả. Đọc/ghi `bars_daily`, nạp và kiểm nến ngày (docstring policy `:222-228`) |
| 3 | `backfill` | `backfill_universe.py` | Không | Grep: 0 |
| 4 | `backfill-5m` | `backfill_universe.py` | Không | Grep: 0 (cùng file) |
| 5 | `foreign-flow` | `backfill_foreign_flow.py` | Không | Grep: chỉ `consumerID/consumerSecret` (khoá API SSI, không phải consumer NATS) |
| 6 | `deploy-drift` | `deploy_drift_check.py` | **Có** (A.1 #4, A.2) | Đọc `:41-267` |
| 7 | `container-health` | `container_health_check.py` | **Có** (A.1 #1, A.2) | Đọc `:60-75`, `:186-285`, `:288-484`, `:500-690` |
| 8 | `engine-cam` | `check_silent_engine.py` | **Có** (A.3; không phụ thuộc container) | Đọc toàn bộ (263 dòng) |
| 9 | `engine-consumer` | `engine_consumer_check.py` | **Có** (A.1 #3, A.2) | Đọc toàn bộ (229 dòng) |
| 10 | `stream-health` | `stream_health_check.py` | Không | Grep: 0. Đọc docstring `:1-40`: đếm "bars closed" trong `logs/bars_closed.log` (collector ghi, `trading/logging_setup.py:16`) và nến trong `bars`; không đọc `engine_alerts.log` |
| 11 | `orderbook-recorder` | `record_vn30f_orderbook.py` | Không | Grep: 0 |
| 12 | `orderbook-daily-check` | `check_orderbook_daily.py` | Không | Grep: 0 |
| 13 | `backup` | `backup_db.sh` | Không (dump toàn DB, gồm `engine_state`, `positions`, `pnl_daily` như mọi bảng) | Đọc toàn bộ `backup_db.sh` (đợt 226); grep: 0 |
| 14 | `backup-makeup` | `backup_db.sh` | Không | Cùng script |
| 15 | `backup-check` | `backup_check.py` | Không | Grep: 0 |
| 16 | `orderbook-backup` | `backup_orderbook.sh` | Không | Grep: 0 |
| 17 | `disk-check` | `disk_check.py` | Không | Grep: 0 |
| 18 | `host-preflight` | `host_preflight.py` | Không | Grep: 0 (chỉ đọc cấu hình compose/cổng) |
| 19 | `restore-drill` | `restore_drill.py` | Không (so đếm hàng theo bảng, gồm `orders`/`engine_state`, so với bản kê chụp lúc backup) | Grep: 1 dòng docstring nhắc bảng `orders`; `scripts/verify_backup_restore.py:31-35` liệt kê `pnl_daily`, `engine_state` trong danh sách bảng (đếm hàng) |
| 20 | `catchup` | `startup_catchup.py` | Không | Grep: 0 |
| 21 | `universe-refresh` | `refresh_universe.py` | Không | Grep: 0 |
| 22 | `schedule-watch` | `heartbeat_check.py` (`--schedule-watch-only`, `:1524-1584`) | **Gián tiếp** (cùng file với #1, A.3) | Đọc `:1524-1584` |
| 23 | `morning-summary` | `heartbeat_check.py` (`:1480-1522`, `build_morning_summary`) | **Gián tiếp** (cùng file với #1; không đọc dữ liệu engine) | Đọc `:1480-1522` |

Phần **chưa kiểm** của A: (a) `docker compose stop engine` thật (cấm); số tin dựa trên đọc code và số lần chạy trong log, chưa quan sát một lần dừng thật; (b) hành vi `restart: unless-stopped` sau khi Docker Desktop khởi động lại với container đã dừng thủ công (suy luận từ tài liệu Docker); (c) không đọc `scripts/_alert_common.py` `send_with_outbox` ngoài việc biết nó xếp hàng khi gửi hỏng; (d) không chạy `build_morning_summary` (chỉ grep `engine`: 0 trong khối này) và không đọc toàn bộ các script ở các hàng có "Grep" (chỉ grep).

### A.6. Đề xuất cách dừng ít sửa nhất (chỉ đề xuất, Lead quyết)

**Phương án 1 (khuyến nghị): một cờ cấu hình, bốn chỗ đọc.** Thêm vào `config/config.yaml` một khoá, ví dụ `engine_enabled: false`, và để các job đọc nó bằng `yaml.safe_load` (cách các job đã đọc config; không import `load_config`):

| File | Dòng | Sửa tối thiểu |
|---|---|---|
| `scripts/heartbeat_check.py` | `:85`, `:1720` | `stale_services(rows, now, max_age, expected=...)` chỉ chứa `("collector",)` khi cờ tắt. (Hàm đã nhận tham số `expected`, `:995`) |
| `scripts/container_health_check.py` | `:69`, `:600` | Bỏ `"engine"` khỏi `DEFAULT_SERVICES` khi cờ tắt |
| `scripts/engine_consumer_check.py` | `:128-142` | Thoát 0 ngay sau khi đọc config nếu cờ tắt |
| `scripts/deploy_drift_check.py` | `:41`, `:260` | Bỏ `engine` khỏi `SERVICES`/`get_service_commit_epochs` khi cờ tắt |

Cộng một việc **bắt buộc trước khi sửa/xoá `trading/engine/main.py`**: gỡ `from trading.engine.main import CAPITAL` khỏi `heartbeat_check.py:81` (đưa `CAPITAL` sang `trading/config.py` hoặc một module trung lập) và `from trading.engine.main import _default_strategy` khỏi `check_silent_engine.py:28` (hoặc ngừng nhánh `engine-cam`: sửa `sched.sh:106-109` và bỏ mục `engine-cam` khỏi `SCHEDULE_EXIT_POLICIES` `:264-270` và `KHONG_CANH` `:192`).

**Phương án 2 (không sửa code giám sát, tốn công engine): engine rỗng.** Giữ container `engine` chạy nhưng chạy một vòng lặp tối thiểu: tiêu thụ consumer `engine` (ack), ghi `heartbeat`, không giao dịch. Không tin nào kêu, không đụng bốn job; đồng thời là khung cho engine mới (đợt 229). Hạn chế: vẫn cần quyết định số phận bất biến sổ sách (`heartbeat_check.py:1696-1737`) và bảng `engine_state`/`positions`.

**Phương án 3 (không sửa gì): chấp nhận tin.** Dừng bằng `docker compose stop engine` vào tối Chủ nhật 15/11: 1 tin (`container-health`), sáng thứ Hai ~60–63 tin `heartbeat`, ≤ 19 tin `engine-consumer`/ngày, và 1 tin `deploy-drift`/ngày khi `trading/` đổi. Không khuyến nghị: dập tắt mọi tin thật khác.

**Không nên làm:** xoá container, xoá consumer NATS, hoặc xoá/đổi `trading/engine/main.py` trước khi gỡ hai import ở trên (A.2, A.3).

### A.7. Câu hỏi cho Lead/chủ dự án về phần A

1. Dừng engine bằng `stop` (container tồn tại) hay xoá container? (A.2)
2. Chọn phương án 1, 2 hay 3 (A.6)? Phương án 1 cần Builder sửa 4 script + 2 import và test.
3. Khi nào dừng: trước 08:00 thứ Hai 16/11 là bắt buộc nếu muốn tránh tin sáng thứ Hai.
4. Có giữ `engine-cam` (đang kiểm chiến lược `octopus_pullback` cũ) hay bỏ nhánh này cùng engine cũ?

---

## B. Engine hiện tại gắn với 3 mã và nến 5 phút ở đâu?

Trạng thái: **xong** (đọc đầy đủ `trading/engine/main.py` 842 dòng và `logic.py` 138 dòng; đọc `paper_broker.py`, `risk.py`, `strategy.py`, `trailing_stop.py`, `config.py`; đọc phần liên quan của `storage/db.py`, `strategies/octopus_pullback.py`, `real_orders.py` (chỉ đầu hai hàm), `collector/main.py`/`bus/publisher.py` (grep); GitNexus cho `PaperBroker`, `RiskManager`, `process_bar`).

### B.1. Bản đồ `trading/engine/main.py` [đọc]

| Phần | file:dòng | Ghi chú gắn với 3 mã / 5 phút |
|---|---|---|
| Hằng vốn | `main.py:31` `CAPITAL = 100_000_000.0` | **Bị `heartbeat_check.py:81` import** (A.3). 100 triệu cho paper |
| Tách vốn thật từ NAV | `:34-54` `real_capital_from_nav` | Đường THẬT, không cần cho paper nến ngày |
| Dừng mềm | `:58-73` `_install_stop_handlers` (SIGTERM/SIGINT → `stop_event`) | Dùng lại được nguyên vẹn |
| **Chiến lược chạy thật** | `:76-120` `_default_strategy()` → `OctopusPullbackStrategy()` | **Bị `check_silent_engine.py:28` import**. Octopus tinh chỉnh trên nến 5 phút (docstring `:83-88`: `warmup_bars` 201 nến 5 phút) |
| Đếm lỗ hổng warm-up | `:123-148` `count_warmup_gap` | Dùng `CONTINUOUS_SESSIONS` 09:15–11:30/13:00–14:30 (`calendar_vn.py:103`) và `bar_interval_minutes`: **gắn chặt lưới nến 5 phút** |
| Ngày cần có nến | `:151-173` `SESSION_DATA_READY_TIME = 15:00`, `last_session_date_needed` | Chờ nến 5 phút của phiên gần nhất trong bảng `bars` |
| `run()` | `:176-824` | |
| — khởi tạo, khôi phục sổ | `:199-235` (`Storage.init_schema`, `read_engine_state`, `read_positions`, `PaperBroker.restore`) | Dùng lại được (bảng theo `symbol`) |
| — chờ dữ liệu phiên | `:243-271` (vòng `for sym in cfg.symbols`, chờ tối đa 600 giây `:181`) | **Gắn 3 mã + bảng `bars` (5 phút)** |
| — warm-up | `:280-312` (`storage.read_last_bars(sym, strategy.warmup_bars)`, `compute_crossover`) | **Gắn 3 mã + 5 phút**; `:306` `clean_hist[-1]` nổ nếu `warmup_bars = 0` (C, câu 3) |
| — rủi ro và trailing | `:313-329` | `RiskManager(capital=CAPITAL)`, `TrailingStopManager()` |
| — khôi phục TP từ lịch sử | `:330-409` (`isinstance(strategy, RestoresTakeProfit)`; `read_last_buy_fill`, `read_anchor_bar`, `read_bars_until` đọc **bảng `bars` 5 phút**) | Gắn 5 phút |
| — vốn THẬT từ NAV, vị thế thật | `:410-505` | Đường THẬT (`real_order_account`); lọc `sym in cfg.symbols` ở `:486` |
| — GUARD-1/GUARD-3 | `:506-556` (chỉ khi `real_trading_enabled`) | Đường THẬT, `for sym in cfg.symbols` `:521`, `:542` |
| — đăng ký NATS | `:565-572` `js.subscribe("bars.>", durable="engine", stream=cfg.nats_stream, config=ConsumerConfig(deliver_policy=DeliverPolicy.ALL))` | Mọi nến đóng của stream `BARS`; **không lọc theo mã** (lọc ở nơi khác) |
| — `persist_fills` | `:574-593` (`upsert_position`, `write_engine_state`, `write_order`, `update_pnl_daily`) | Dùng lại được |
| — `on_real_crossover` | `:600-654` | Đường THẬT |
| — `idle_maintenance` | `:656-666` (`expire_stale_real_orders` + `storage.beat("engine")`) | Heartbeat nằm ở đây |
| — vòng chính | `:668-824`: `next_msg(timeout=60)` `:680`, hết giờ → `idle_maintenance` `:702-704`; giải mã `bar_from_payload` `:706`; chống nạp trùng `:707-729`; GAP-1 `:730-755`; `process_bar` `:758-767`; ghi `engine_lag_ms` + `alert("bar processed")` `:769-780`; `persist_fills` `:781`; `handle_stop_touch` `:785-791`; halt `:792-807`; `ack` `:808`; lỗi → `term` `:809-820`; `idle_maintenance` `:821` | Mỗi nến 5 phút = một message |
| `main()` | `:832-838` (`start_outbox("engine")`, `asyncio.run(run(load_config(...)))`) | `load_config` ở `config.py:62-86` |

`trading/engine/logic.py` [đọc]: `process_bar` `:15-125` (đổi ngày `:31-36`; chặn nến rác `:46-56`; `broker.on_bar` `:58`; `strategy.on_bar` `:66`; trailing stop `:71-95`; duyệt rủi ro + `broker.submit` `:96-123`); `bar_from_payload` `:128-138`. Chỉ `engine/main.py` gọi hai hàm này (GitNexus `impact process_bar` trả `risk UNKNOWN`, nên tôi dùng grep: chỉ `main.py:22`, `:706`, `:758` và `tests/test_engine_logic.py`, `tests/test_engine_main.py`).

### B.2. Chỗ gắn với 3 mã và nến 5 phút [đọc/đo]

| Chỗ | Bằng chứng | Mức gắn |
|---|---|---|
| Danh sách mã | `config/config.yaml` `symbols: [HPG, IJC, AAA]`; `load_config` `config.py:66` | Gắn 3 mã |
| Nguồn nến | Collector chỉ publish **nến 5 phút đã đóng** lên subject `bars.ssi.{symbol}` (`bus/publisher.py:45`; stream `subjects = ["bars.>"]` `:21`; `interval = bar_interval_minutes*60` `collector/main.py:425`) và chỉ cho `cfg.symbols` (`collector/feed.py:36`, `:188`) | Engine không có đường nhận nến NGÀY |
| Dữ liệu lịch sử cho warm-up/khôi phục | `storage.read_last_bars`, `read_bars_until`, `read_anchor_bar`, `read_last_close`, `last_bar_ts` (`db.py:261-282`, `:387-418`, `:478`) đọc bảng **`bars`** | Gắn 5 phút |
| Chiến lược | `OctopusPullbackStrategy` (EMA 200, MACD 26/9, cổng thanh khoản 20 ngày, TP = open + 2×ATR; `octopus_pullback.py:261-265`) | Gắn 5 phút (chưa có phép đo ủng hộ, docstring `main.py:88-93`) |
| Đồng hồ phiên | `CONTINUOUS_SESSIONS`, `SESSION_DATA_READY_TIME` (`main.py:155`), `count_warmup_gap` | Gắn lưới 5 phút |
| Nhịp heartbeat | `idle_maintenance` theo `next_msg` 60 giây và theo từng nến (`:702-704`, `:821`); ngưỡng canh 300 giây (`heartbeat_check.py:86`) | Không gắn 5 phút, nhưng nếu engine ngày chỉ có 1 nến/ngày, `next_msg` hết giờ mỗi 60 giây vẫn giữ nhịp |
| Đường THẬT | `real_orders.handle_crossover`/`handle_stop_touch` (`main.py:652`, `:785`), NAV, GUARD (`:410-556`) | Gắn `real_order_account` và `cfg.symbols`; **không cần** cho engine paper nến ngày (`real_trading_enabled: false`) |

### B.3. Phần nào dùng lại được cho engine nến ngày nhiều mã

| Thành phần | Dùng lại? | Lý do (file:dòng) |
|---|---|---|
| `PaperBroker` | **Dùng lại, có kiểm** | Phí 0,28%/chiều + thuế bán 0,1% (`paper_broker.py:21-22`), slippage 5 bps, T+3 theo FIFO lô (`:28`, `:99-134`), `restore` (`:220-245`). Khớp lệnh ở **open nến kế tiếp** `+/-` slippage (`:169-179`): với nến ngày, tín hiệu cuối ngày T khớp ở open ngày T+1, **đúng nhu cầu "mua ở open phiên sau"**. Lưu ý [suy luận]: `_day_index` đếm ngày theo `ts.date()` của nến (`:70-79`); `bars_daily.ts` lưu 00:00 giờ VN dưới dạng UTC của ngày trước (ví dụ nến 05/11 có `ts` 04/11 17:00Z, xem D), nên phải chuyển sang giờ VN như `bar_from_payload` (`logic.py:131`) trước khi đưa vào. GitNexus `impact PaperBroker upstream`: `impactedCount 67`, `risk HIGH`, 24 nơi import trực tiếp (gồm `trading/backtest.py`, `trading/real_order_reconcile.py`, `scripts/confirm_real_order.py`, `scripts/report_real_account_performance.py` và ~15 script đo) → **sửa PaperBroker tại chỗ ảnh hưởng nhiều thứ; nên bọc/kế thừa thay vì sửa** |
| `RiskManager` | **Dùng lại, đổi tham số** | `max_positions=5`, `max_order_value_pct=0.20`, `risk_pct=0.01`, `max_daily_loss_pct=0.03`, `lot_size=100` (`risk.py:12-20`), `approve_sized` (`:78-155`). Bài toán nhiều mã cần quyết số vị thế và tỷ trọng. GitNexus: `impactedCount 293`, `risk CRITICAL`, 21 nơi import trực tiếp → **không sửa tại chỗ** |
| `TrailingStopManager` | Dùng lại | Theo từng mã, cần ATR từ chiến lược (`trailing_stop.py:26-65`) |
| `Strategy` Protocol | Dùng lại | `strategy.py:26-54`; cần `warmup_bars`, `compute_crossover`, `on_bar`, `last_crossover`, `last_atr` |
| `Storage` (`positions`, `orders`, `engine_state`, `pnl_daily`, `beat`) | Dùng lại | Bảng theo `symbol`, không ràng buộc 3 mã (`schema.sql:106-144`); **trừ** các hàm khôi phục đọc bảng `bars` 5 phút (`db.py:340-418`), cần bản đọc `bars_daily` |
| `trading/alerts.py` (`alert`, `start_outbox`) | Dùng lại | `main.py:12`, `:837` |
| `_install_stop_handlers`, mẫu vòng `next_msg` + `stop_event` (`:670-704`) | Dùng lại (mẫu) | Có comment về bug đo thật khi dừng |
| `process_bar` (`logic.py:15-125`) | Dùng lại một phần | Chặn nến rác `:46-56`, đổi ngày `:31-36`, trailing stop `:71-95`; tính `daily_pnl` theo nến |
| Warm-up, `count_warmup_gap`, chờ dữ liệu phiên (`:123-173`, `:243-312`) | **Gắn chặt 5 phút**, viết lại | |
| Subscribe `bars.>` (`:565-572`) | Gắn stream 5 phút | Engine ngày không cần NATS: có thể chạy **một lần cuối ngày** (job quét) và đọc `bars_daily` (D) |
| Đường THẬT (NAV, GUARD, `on_real_crossover`, `handle_stop_touch`; `main.py:410-556`, `:600-654`) | Không cần cho paper | Giữ tách riêng |

### B.4. `config/config.yaml` — `symbols` được ai đọc, đổi/bỏ thì ảnh hưởng gì [đọc]

Các khoá khác trong file: `indices` (VNINDEX, VN30), `bar_interval_minutes: 5`, `ssi_equity_accounts`, `holidays`, `real_trading_enabled: false`, `real_order_account`, `nats`, `watchdog`.

| Người đọc `symbols` | file:dòng | Ảnh hưởng nếu đổi/bỏ |
|---|---|---|
| Collector (stream 5 phút) | `collector/feed.py:36`, `:188`; `collector/main.py:349`, `:433`; `collector/backfill.py:316`; `collector/account_sync.py:59` (sức mua theo mã) | Đổi danh sách = đổi mã được stream, backfill, và mã được đo sức mua |
| Engine | `engine/main.py:248`, `:281`, `:486`, `:521`, `:542` | Vòng chờ dữ liệu, warm-up, lọc vị thế thật, GUARD |
| `heartbeat_check.py` | `:1607` (cũng `:1191` cho `daily-check`) | Dead-man nến cũ chỉ nhìn các mã này (`:1692-1695`); **rỗng → `IN ()` lỗi → `[CRITICAL] … không đọc được DB` mỗi 5 phút** |
| `check_silent_engine.py` | `:185-190` | Rỗng → `EXIT=2` (A.3) |
| `daily_data_check.py` | `:351` (`read_must_price_symbols(cfg.ssi_equity_accounts, cfg.symbols)`), `:392-404` | "Mã BẮT BUỘC có giá" = `cfg.symbols` + mã đang giữ; ảnh hưởng độ đủ nến ngày |
| `backfill_universe.py` | `:232`, `:255`, `:304` | Bỏ `cfg.symbols` khi nạp 5 phút để tránh ghi đè nến collector stream |
| `startup_catchup.py` | `:264`, `:364`, `:377` | `symbols_5m` = universe **trừ** `cfg.symbols`: bỏ mã khỏi `symbols` thì mã đó vào diện nạp bù 5 phút |
| `storage/db.py` | `:1407` (`read_must_price_symbols`) | Cùng ý trên |
| Công cụ chạy tay | `check_golive_gate.py:502`, `check_orders_hygiene.py:66`, `check_real_order_readiness.py:73`, `:132`, `:196`, `backfill_history.py:90` | Không trong lịch |

Kết luận [suy luận]: **đổi `symbols` không chỉ là chuyện engine**. Nếu engine nến ngày không dùng `symbols` thì giữ nguyên danh sách 3 mã cho collector và các job kiểm; muốn bỏ stream 5 phút của 3 mã thì phải sửa đồng thời `heartbeat_check.py` (2A), `daily_data_check.py` (must-price), `startup_catchup.py`, và (nếu bỏ hẳn) collector.

### B.5. Test gắn với engine [đọc]

9 tệp `tests/` import `trading.engine`: `conftest.py`, `test_compare_timeframe_mismatch.py`, `test_engine_gap1.py` (9 test), `test_engine_logic.py` (16), `test_engine_main.py` (66), `test_logging_setup.py`, `test_real_trading_guard.py` (6), `test_silent_engine_guard.py` (7), `test_strategy_conformance.py`. Viết lại `trading/engine/main.py` phải xử lý các test này (test ghim `warmup_bars`, `_default_strategy` là octopus, và import `CAPITAL`).

### B.6. Ba câu hỏi của Lead

1. **Vị thế paper mở / có tự bán độc lập không:** xem C.1 và C.3 (không có vị thế; trailing stop + TP; không có thoát theo thời gian).
2. **`engine-cam` có báo "engine câm" nếu engine chạy nhưng không sinh tín hiệu?** `check_silent_engine.py` **không nhìn engine đang chạy**: nó đọc bảng `bars` của `cfg.symbols` từ 2020 đến 2030 (`:121-132`, `:207`) rồi **phát lại** `_default_strategy()` bằng `compute_crossover` (`:68-69`). Kết luận câm tại `:86`: `(has_gate and gate_open_bars == 0) or (bull_signals == 0)`; cảnh báo `CRITICAL` ở `:227-250` (outbox, `exit 1`, mỗi lần chạy 15:15). Do đó: (a) **cờ chỉ chặn trong `engine/main.py`** và `_default_strategy()` giữ Octopus ⇒ `engine-cam` vẫn `OK` (nó phát lại Octopus trên dữ liệu DB), **không báo gì**; (b) nếu cờ làm `_default_strategy()` trả chiến lược rỗng ⇒ `bull_signals = 0` ⇒ `CRITICAL` "KHONG THE sinh tin hieu mua tren 3/3 ma" **mỗi ngày giao dịch 15:15** (không chống lặp). [đọc; chưa chạy thử]
3. **Chỗ hẹp nhất để chèn cờ "không chạy chiến lược" mà vẫn ack + heartbeat + ghi nến:** `trading/engine/main.py:237` (`strategy = _default_strategy() if strategy is None else strategy`): khi cờ bật, gán một chiến lược rỗng (cùng Protocol `strategy.py:26-54`: `on_bar → None`, `last_crossover → None`, `last_atr → None`, `compute_crossover → None`, **`warmup_bars ≥ 1`**). Toàn bộ vòng lặp (`:680-704`, `:808`, `:821`), `heartbeat`, `process_bar` và `broker.on_bar` chạy nguyên vẹn, không có tín hiệu ⇒ không lệnh paper, không `on_real_crossover`. "Ghi nến" không phải việc của engine: **collector** ghi `bars`, engine chỉ đọc. Cạm bẫy: `warmup_bars = 0` làm `main.py:282` `read_last_bars(sym, 0)` (`LIMIT 0` → `[]`, `db.py:268-282`) rồi `:306` `clean_hist[-1]` ném `IndexError` lúc khởi động. Cờ lấy từ biến môi trường trong `docker-compose.yml:76-89` (hoặc thêm khoá vào `Config` `config.py:13-31` và `load_config` `:62-86`; `Config` là dataclass `frozen`). Phương án thay: chặn tại `:756` (trước `process_bar`) rồi `ack` và `continue`; nhánh `continue` ở `:716-718`/`:727-729` bỏ qua `idle_maintenance` (`:821`), nên heartbeat chỉ ghi khi `next_msg` hết 60 giây (`:702-704`): đủ ngưỡng 300 giây nhưng kém sạch.

## C. Trạng thái hiện tại trong DB (chỉ SELECT)

Trạng thái: **xong** (đo lúc 13/11 23:14, `docker compose exec -T postgres psql -U trading -d trading -P pager=off -c "<SELECT>"`). Không in số tài khoản/ID.

### C.1. Vị thế, tiền, lệnh paper [đo]

| Bảng | Câu lệnh (SELECT) | Kết quả nguyên văn |
|---|---|---|
| `engine_state` | `select cash, realized_pnl, updated_at at time zone 'Asia/Ho_Chi_Minh' as updated_vn from engine_state` | `cash 100043751.69003572 / realized_pnl 43751.690035727515 / updated_vn 2026-09-28 09:20:37.230694` (1 dòng) |
| `positions` | `select symbol, qty, avg_price, updated_at … from positions order by symbol` | 3 dòng, **cả ba `qty = 0`, `avg_price = 0`**: `AAA` (cập nhật 28/09 09:20:25), `HII` (10/09 18:18:35), `IJC` (28/09 09:20:37). **Không có vị thế paper đang mở** |
| `orders` | `select mode, side, count(*) n, min(ts …), max(ts …), sum(qty), sum(fee), sum(coalesce(pnl,0)) from orders group by mode, side` | `paper BUY n=10, 14/08 09:20 → 03/09 09:20, qty 7.900, fee 154.520, pnl 0`; `paper SELL n=10, 15/07 09:05 → 28/09 09:15, qty 7.700, fee 206.877, pnl −371.298`. **20 lệnh, toàn bộ `mode = paper`**; lệnh cuối cùng 28/09 09:15 (cách 46 ngày) |
| `orders` theo mã | `… where mode='paper' group by symbol, side` | AAA BUY 3 / SELL 3 (pnl +99.613); HII BUY 3 / SELL 2 (−6.461); IJC BUY 4 / SELL 4 (−464.495); **`TEST` SELL 1 (qty 100, pnl +45)** |
| `pnl_daily` | `select count(*), min(date), max(date), sum(realized), sum(fees) from pnl_daily` | 5 dòng, 15/07 → 28/09, `realized −371.298`, `fees 361.397` |
| `heartbeat` | `select service, last_seen …, round(extract(epoch from now()-last_seen)) from heartbeat` | `engine` 23:13:50 (34 giây), `collector` 23:14:08 (16 giây) |

Sáu lệnh cuối: `28/09 09:15 AAA SELL 400 @7.470 (pnl +149.078)`, `28/09 09:15 IJC SELL 400 @6.770 (pnl −250.302)`, `03/09 09:20 AAA BUY 400 @7.054`, `03/09 09:15 IJC BUY 400 @7.354`, `19/08 14:05 HII BUY 300 @8.704`, `19/08 13:55 AAA SELL 400 @6.900 (−33.991)`.

Nhận xét [suy luận từ số đo]:

- **Bất biến sổ sách đang đúng:** `cash − CAPITAL = 100.043.751,69 − 100.000.000 = 43.751,69 = realized_pnl` và không có vị thế (`Σ avg_price×qty = 0`), nên `heartbeat_check.py:1696-1737` không kêu.
- **Tổng `pnl` của `orders` (−371.298) khác `engine_state.realized_pnl` (+43.752): lệch 415.050.** Mô tả panel Grafana 8 (`grafana/provisioning/dashboards/trading.json`) nói nguồn đúng là `engine_state`, "gồm cả các can thiệp thủ công (như đóng vị thế HII ngày 10/09)". Tôi chưa kiểm từng can thiệp; ghi nhận để Lead biết khi engine mới đọc lại `engine_state`.
- **Còn dữ liệu rác:** một lệnh `TEST` (15/07, qty 100) trong `orders` và một dòng `pnl_daily` ngày 15/07 (`realized 45`, `unrealized 200`, `fees 165`) khớp lệnh `TEST`. `scripts/check_orders_hygiene.py` có chuyên dò loại này (chưa chạy, cấm).
- **Lệnh chờ của paper không nằm trong DB:** `PaperBroker._pending` là dict trong bộ nhớ (`paper_broker.py:61`, `:140-141`, `:169`), mất khi engine dừng; không có bảng "lệnh paper chờ khớp". Dừng engine giữa lúc có tín hiệu chưa khớp (khớp ở open bar kế tiếp) thì tín hiệu đó mất.

### C.2. Lệnh THẬT (chỉ đếm) [đo]

| Bảng | Kết quả |
|---|---|
| `pending_real_orders` (`select status, count(*), max(created_at) … group by status`) | `expired 9` (cuối 04/09 09:20:17); **không có `pending`/`confirmed`/`placed`** |
| `real_order_fills` (`select status, side, count(*) … group by …`) | 0 dòng |
| `real_risk_state` | 0 dòng (chưa từng halt) |
| `config/config.yaml` | `real_trading_enabled: false` [đọc, dòng "real_trading_enabled"] |

### C.3. Câu hỏi của Lead (1): nếu tắt chiến lược, vị thế paper có bị bỏ mặc không? Có nhánh tự bán độc lập tín hiệu mua không?

- **[đo] Hiện không có vị thế paper nào mở** (ba hàng `qty = 0`) và không có lệnh THẬT đang chờ/đã đặt. Nên tắt chiến lược **không bỏ mặc vị thế nào**.
- **[đọc] Hai đường bán trong engine, cả hai chỉ làm gì khi `broker.position_qty > 0`:**
  1. **Trailing stop** `trading/engine/logic.py:71-95` (`trailing_stop.check` → `broker.force_exit`): chạy **độc lập với `strategy.on_bar`** nhưng cần `strategy.last_atr(symbol)` (`logic.py:73`); khi `atr is None` thì `check` trả `None` (`trailing_stop.py:62-63`) → **stop không bao giờ chạm**. Nghĩa là một chiến lược rỗng trả `last_atr = None` sẽ vô hiệu hoá luôn trailing stop.
  2. **Chốt lời (take-profit)** nằm **trong chiến lược**: `trading/strategies/octopus_pullback.py:248-256` (`on_bar` trả `Signal(SELL, held)` khi `bar.close >= tp`). Chiến lược rỗng không còn TP.
- **[đọc] Không có nhánh "hết hạn giữ" (thoát theo thời gian):** grep `hold|max_hold|time_stop` trong `octopus_pullback.py`: không có kết quả.
- **[đọc] Đường THẬT:** `real_orders.handle_stop_touch` (`engine/main.py:785`) chỉ ghi lệnh SELL chờ xác nhận tay vào `pending_real_orders` (không đặt lệnh), đọc vị thế THẬT của `real_order_account` và chỉ trailing stop cho mã trong `cfg.symbols`; được gọi **mỗi nến** không phụ thuộc chiến lược (ngoài việc nhận `atr`). [chưa đọc hết `real_orders.py`, mới đọc đầu hai hàm `handle_crossover :71`, `handle_stop_touch :222`.]

### C.4. Các bảng engine ghi vào và job nào đọc chúng [đọc]

| Bảng | Engine ghi ở | Ai đọc |
|---|---|---|
| `heartbeat` (hàng `engine`) | `storage.beat("engine")` trong `idle_maintenance` (`engine/main.py:656-666`, `db.py:300-306`); gọi khi `next_msg` hết 60 giây (`:702-704`) và cuối mỗi vòng xử lý nến (`:821`) | `heartbeat_check.py:1690`, `:1720` (dead-man); Grafana panel 4 |
| `positions` | `persist_fills` → `storage.upsert_position` (`main.py:576`, `db.py:308`) | engine khi khởi động (`main.py:203`, `db.py:317-322`, chỉ `qty > 0`); `heartbeat_check.py:1700-1702` (`qty != 0`); Grafana panel 3 (`qty > 0`); đếm hàng trong `verify_backup_restore.py` |
| `engine_state` | `write_engine_state` (`main.py:577`, `db.py:324`) | engine khi khởi động (`main.py:202`); `heartbeat_check.py:1697-1699`; Grafana panel 8; `verify_backup_restore.py:35` |
| `orders` | `write_order` (`main.py:578`, `db.py:541`) | engine khôi phục (`db.py:340-402`: `read_highest_since_buy`, `read_last_buy_date`, `read_last_buy_fill`, `read_anchor_bar`); `scripts/check_orders_hygiene.py:81`, `scripts/compare_timeframe_mismatch.py:68` (không nằm trong lịch) |
| `pnl_daily` | `update_pnl_daily` (`main.py:579`, `db.py:787`) | Grafana panel 2; `verify_backup_restore.py:34` |
| `pending_real_orders`, `real_order_fills`, `real_risk_state` | `real_orders.py`, `save_real_risk_halt` (`main.py:802`) | `scripts/confirm_real_order.py`, `scripts/check_real_order_readiness.py`, `scripts/check_golive_gate.py:479-485` (đều chạy tay) |
| Log `logs/engine_alerts.log` | `attach_durable_alert_handler(filename="engine_alerts.log")` (`main.py:829`) | `scripts/measure_bar_latency.py` (công cụ đo, không trong lịch) |

Không có job **theo lịch** nào đọc `orders` hay `pnl_daily` (chỉ Grafana và công cụ chạy tay).

## D. Dữ liệu cho engine nến ngày

Trạng thái: **xong, với một chỗ chưa đo được** (giờ có mặt của 10 phiên, xem D.1). Lệnh: `docker compose exec -T postgres psql -U trading -d trading -P pager=off -c "<SELECT>"` và đọc `logs/*.log`, `docker logs … scheduler`.

### D.1. `bars_daily` của phiên T có mặt trong DB lúc mấy giờ?

Có **ba đường nạp**, theo thứ tự thời gian trong ngày [đọc code + đo log 13/11]:

| Đường | Phạm vi | Giờ | Bằng chứng |
|---|---|---|---|
| Collector EOD | **3 mã** `cfg.symbols` (nến 5 phút + ngày) và **mã đang giữ** (chỉ nến ngày, để tính NAV) | **15:05** sau phiên (`collector/main.py:24` `EOD_HOUR, EOD_MINUTE = 15, 5`; `:339-363`) | [đọc]; chưa đối chiếu giờ thật trong log collector |
| Scheduler 21:45 — `catchup` | `--use-universe`: **293 mã active** + 7 mã bắt buộc có giá = 293 mã nến ngày (`[load] 293 ma thanh khoan + 7 ma bat buoc co gia (0 ngoai universe) = 293 ma`); nến 5 phút cho 290 mã (bỏ AAA/HPG/IJC vì collector stream); khối ngoại | **21:45:00 → 21:48:38 ngày 13/11 (219 giây)**; log scheduler `14:45:00Z … catchup finish with EXIT=0 dur=218.94s`. 12/11: 21:53:27 → 21:58:04 (274,7 giây, đây là lần "startup catchup" sau khi Docker chạy lại, nạp 06/11→12/11) | `logs/catchup.log`; `docker logs --since 2026-11-13T13:00:00Z ai_auto_trading_system-scheduler-1` |
| Scheduler 21:45 — `universe-refresh` (sau `daily-check`) | **Toàn thị trường 1.602 mã**, nến ngày | **21:48:42 → 21:55:52 (430 giây)**, `ok=1309 skip=293 err=0`; `backfill_progress` (timeframe `1d`): 1.602 dòng `ok`, `updated_at` từ 21:45:02 đến 21:55:48 ngày 13/11 | **Chỉ chạy khi cách lần trước ≥ 6 ngày** (`scripts/refresh_universe.py:75` `(now - max_updated) < timedelta(days=6)`); lần này sau 11 ngày (lần trước 02/11 23:35, `logs/universe-refresh.log`) |

Kết luận [đo]: nến ngày của phiên T cho **293 mã active có mặt khoảng 21:46–21:48** (nếu máy và Docker chạy lúc 21:45), cho **toàn bộ ~946 mã có giao dịch khoảng 21:56** nhưng chỉ vào ngày chạy `universe-refresh` (~mỗi 6 ngày trở lên). Trước khi bản làm mới tuần này chạy, mỗi ngày 03–12/11 chỉ có 287–291 mã trong `bars_daily` (đo sáng 13/11 bằng `select (ts at time zone 'Asia/Ho_Chi_Minh')::date, count(distinct symbol) from bars_daily where ts >= '2026-11-02' group by 1`: 03–05/11 288, 06/11 291, 09–12/11 287) vì chỉ nạp universe active; sau khi chạy: 871–949 mã/ngày.

**Chưa đo được:** giờ có mặt cho **10 phiên gần nhất** (30/10–13/11). Lý do: `bars_daily` không có cột thời điểm nạp (`schema.sql:63-72`: `symbol, ts, open, high, low, close, volume, source`); `backfill_progress.updated_at` chỉ giữ lần mới nhất (một dòng/mã); `logs/catchup.log` chỉ có các lần 06:40/21:45/khởi động rải rác (02/11 23:23 và 23:35, 03/11 06:40, 04/11 23:06 `EXIT=1`, 08–09/11 nhiều lần, 12/11 21:53, 13/11 21:03 và 21:45); Docker tắt 10–12/11 nên các phiên 10, 11, 12/11 chỉ được nạp bù lúc 21:58 ngày 12/11 (06/11 → 12/11). Chỉ **13/11** có đo trực tiếp giờ nạp theo lịch.

Ghi chú: `bars_daily.ts` lưu **00:00 giờ VN dưới dạng UTC của ngày trước** (`select … from bars_daily where symbol='HPG' order by ts desc limit 3` → `2026-11-12 17:00:00+00` hiển thị `2026-11-13 00:00:00` giờ VN). Engine ngày phải đổi múi giờ trước khi lấy `.date()` (B.3).

### D.2. Dữ liệu ngày có đủ cho 600–1.600 mã mỗi tối không?

[đo, `select … from bars_daily`, `symbol_universe`, ngày 13/11]

| Chỉ số | Giá trị |
|---|---|
| Mã trong `symbol_universe` | **1.602** (active 289, trung bình `avg_value_20d` 46,78 tỷ; không active 1.313, trung bình 0,14 tỷ) |
| Mã có nến ngày 13/11 | **946** (ngày 12/11: 878; 11/11: 874; 10/11: 881; 09/11: 878; 06/11: 947; 05/11: 926; 04/11: 895; 03/11: 871; 02/11: 891; 30/10: 949) → **870–950 mã/phiên** có nến, chủ yếu mã có giao dịch trong ngày |
| Mã có nến 13/11 theo sàn | HOSE 384, HNX 193, UPCOM 369 |
| Chất lượng nến 13/11 | 946 dòng, `volume = 0`: 0, `open/close ≤ 0`: 0 |
| Mã active thiếu nến 13/11 | 287/289 có nến → **thiếu 2** (HIO, SPV; `daily_data_check` đếm 291/293 vì thêm 7 mã bắt buộc có giá) |
| Theo thanh khoản `avg_value_20d` (có nến 13/11 / tổng) | ≥ 10 tỷ: **143/144 (99,3%)**; 5–10 tỷ: **39/39 (100%)**; 1–5 tỷ: **105/114 (92,1%)**; < 1 tỷ: **659/1.305 (50,5%)** |
| Số mã bao quát trong lịch sử | `bars_daily` 2.997.519 dòng, 1.561 mã, từ 2016-01-04 đến 2026-11-13 |

Phân tích [suy luận]:

- **Dữ liệu đủ cho 150–300 mã thanh khoản** (≥ 5–10 tỷ GTGD): nạp hằng tối và gần như đủ nến (99–100%). Một engine lọc "khối lượng lớn, đột biến" trên nến ngày thực tế chỉ cần các mã này (183 mã ≥ 5 tỷ, 297 mã ≥ 1 tỷ).
- **Hơn 600 mã** (toàn thị trường) **chưa được nạp hằng tối**: đường nạp hằng tối chỉ có 293 mã active; 1.602 mã chỉ mỗi ~6 ngày và mất ~430 giây. Nếu cần quét toàn thị trường hằng tối: ước lượng thời gian nạp đủ 1.602 mã khoảng **7–9 phút** (430 giây cho 1.309 mã được nạp + 293 bị bỏ qua, `--sleep-ms 200` mỗi mã), chưa kiểm hạn mức gọi API SSI cho tần suất hằng ngày.
- **Mã không có nến một ngày không đồng nghĩa lỗi nạp**: trong 1.602 mã có 656 mã không có nến 13/11 (41,0%), phần lớn là mã < 1 tỷ không giao dịch trong ngày (so 12/11 với 13/11: 107 mã có nến 12/11 mà không có 13/11, và 175 mã ngược lại, cho thấy tập mã có nến đổi theo ngày). Cảnh báo "mã active thiếu nến" của `daily_data_check` (21:48:38, `EXIT=1`: HIO, SPV) lặp hằng đêm vì HIO ngừng giao dịch và SPV thanh khoản thấp (đo ở báo cáo 13/11 mục M5): scheduler còn bắn thêm một tin `CRITICAL` thứ hai "Scheduler job thất bại: daily-data-check (rc=1)" (log container scheduler, `2026-11-13 14:48:42,231` UTC). Engine nến ngày cần danh sách loại trừ mã ngừng/thiếu dữ liệu.

### D.3. Một job "quét cuối ngày" đặt ở đâu trong hạ tầng hiện có?

[đọc] `trading/scheduler/main.py`:

- Hai mốc cố định: `MORNING_CATCHUP_TIME = 06:40`, `EVENING_JOBS_TIME = 21:45` (`:45-46`), tính bởi `calculate_next_event` (`:304`); `scheduler_loop` (`:488`); `run_startup` (`:340`, chỉ chạy `catchup` khi container khởi động).
- Chuỗi tối 21:45 trong `run_event` (`:379-487`): `catchup` (có retry 3 lần × 300 giây, `CATCHUP_MAX_ATTEMPTS`, `:219-278`) → `daily-data-check` (`:439-462`, timeout 30 phút, khoá advisory `ADVISORY_LOCK_DAILY_CHECK` `:33`) → `universe-refresh` (`:464-487`, timeout 1 giờ, khoá `ADVISORY_LOCK_CATCHUP` `:32`). Mỗi bước `fn_job(label=…, log_file=…, command=[python_exe, "scripts/…"], timeout_seconds=…, lock_id=…)`; rc ≠ 0 → `notify_job_failure` (`:279-300`).
- Scheduler chạy **trong container** (`docker-compose.yml:122-143`) nên script mới phải nằm trong image (deploy-drift canh `trading/` và `scripts/` cho `scheduler`, `deploy_drift_check.py:46`).

Nơi hợp lý cho job quét [đề xuất]: **một bước mới trong chuỗi 21:45, ngay sau `daily-data-check` và trước `universe-refresh`** (vào ~21:49 khi nến ngày của T đã nạp cho 293 mã); hoặc sau `universe-refresh` nếu cần toàn thị trường (kết thúc ~21:56 ngày chạy làm mới). Đặt trong `run_event` đảm bảo chạy tuần tự và có timeout/khoá.

Các job cùng kiểu được canh thế nào [đọc/đo]:

1. **Scheduler tự báo khi rc ≠ 0:** `notify_job_failure` gửi `[CRITICAL] Scheduler job thất bại: <label> (rc=…, số lần thử: …). Xem log: logs/<file>` (**[đo]** 13/11 21:48:42 cho `daily-data-check`).
2. **Bảng mã thoát `SCHEDULE_EXIT_POLICIES`** (`heartbeat_check.py:214-376`): `catchup` `{0}`, `universe-refresh` `{0}`, `daily-check` `{0,1}`; `schedule-watch` đọc mã thoát lần chạy cuối mỗi giờ phút :07 và báo `THẤT BẠI`. Job mới cần một mục ở đây (và ở `KHONG_CANH`, `:184-202`) và một nhánh `sched.sh` (xem `sched.sh:106-114`, `:212`), vì bảng liệt kê "cả 21 nhánh sched.sh" (`:213`).
3. **Canh gián tiếp kết quả:** `heartbeat_check.py:1801-1891` trong cửa sổ kiểm (08:00–11:30, 13:00–14:45 ngày giao dịch) kiểm nến NGÀY của ngày giao dịch liền trước (`prev_day_bars_alert`), nến 5 phút (`prev_day_5m_alert`) và khối ngoại (`prev_day_foreign_flow_alert`); mỗi ngày chỉ báo một lần.
4. **`container-health` canh container `scheduler`** (`DEFAULT_SERVICES`, `container_health_check.py:69`) và **`deploy-drift`** canh image `scheduler` (`deploy_drift_check.py:41`).
5. **Không có chỗ nào canh "ngày hôm nay có bước X trong chuỗi 21:45 hay không" ngoài mã thoát**, và bước chạy lỡ vì máy tắt lúc 21:45 chỉ được bù bởi `catchup` (nạp bù, không bù job quét mới): nếu Docker/máy tắt lúc 21:45 thì job quét **không chạy bù** trừ khi thiết kế thêm [suy luận từ `run_startup` chỉ chạy `catchup`, `:340-376`].

### D.4. Lệnh mua ở open phiên sau: hệ thống có nguồn giá mở cửa nào cho mã ngoài 3 mã đang stream?

- **Giá mở cửa THỜI GIAN THỰC (09:00–09:15) cho mã ngoài 3 mã: không có** [đọc]. Collector chỉ subscribe `cfg.symbols` (`collector/feed.py:36`, `:188`); `SSIRestClient` chỉ có hai hàm lịch sử `get_ohlc_1day_historical` (`backfill.py:183-211`) và `get_ohlc_5minute_historical` (`:212-245`), không có báo giá/snapshot.
- **Giá mở cửa SAU phiên có đủ:** nến 5 phút của **288 mã khác 3 mã** (291 mã có nến 5 phút 13/11 [đo]: `select count(distinct symbol) from bars where ts >= '2026-11-12 17:00:00+00'` → 291; không kể HPG/IJC/AAA → 288) nạp bằng `catchup` 21:45, và `bars_daily.open`. **Giá mở nến 5 phút đầu ngày bằng giá mở nến ngày** [đo, 12/11]: FPT 51.000/51.000, HPG 21.300/21.300, SSI 20.600/20.600, VND 14.850/14.850 (nến 5 phút đầu `09:15:00`, `n5m = 46`).
- **Hệ quả cho engine paper:** `PaperBroker` khớp ở open nến kế tiếp (B.3). Cho nến ngày, lệnh quyết định tối T sẽ khớp ở `bars_daily.open` của T+1, chỉ có mặt trong DB **tối T+1 (~21:46)**: mô phỏng khớp muộn 24 giờ, đủ cho paper. Với tiền thật cần một nguồn giá mở cửa thời gian thực (ATO 09:00–09:15) mà hệ thống **hiện không có** [chưa kiểm: khả năng của FastConnect để lấy báo giá; cấm gọi API trong đợt này].

---

## Câu hỏi cần quyết trước khi viết lại engine

Đã chốt (Lead, 13/11 ~23:20): **giữ engine chạy, thêm cờ `ENGINE_STRATEGY_DISABLED` + `NullStrategy` (`warmup_bars = 1`), không sửa `_default_strategy`**; giao Builder ở đợt 229 (A.6 phương án 2, B.6 câu 3).

Còn mở:

1. **Chuỗi tối 21:45:** job quét đặt sau `daily-data-check` (~21:49, 293 mã active) hay sau `universe-refresh` (toàn thị trường)? Nếu cần quét toàn thị trường hằng tối thì phải đổi lịch `universe-refresh` (hiện ≥ 6 ngày/lần, 430 giây/lần) hoặc nạp nến ngày cho toàn bộ 1.602 mã mỗi tối (ước 7–9 phút; chưa kiểm hạn mức API SSI).
2. **Phạm vi mã của engine mới:** 293 mã active, ~300 mã ≥ 1 tỷ GTGD, hay toàn thị trường? Phạm vi quyết số lần gọi API, độ đủ nến (99–100% với mã ≥ 5 tỷ nhưng 50,5% với mã < 1 tỷ) và danh sách loại trừ (HIO, SPV thiếu nến hằng đêm).
3. **Khớp lệnh paper:** chấp nhận khớp ở `bars_daily.open` của T+1 vào tối T+1 (muộn 24 giờ) hay cần giá mở cửa thời gian thực? Tiền thật cần nguồn giá mở cửa mà hệ thống chưa có.
4. **Số sách paper:** dùng lại `positions`/`orders`/`engine_state`/`pnl_daily` (bất biến `heartbeat_check.py:1696-1737` ràng buộc `cash + Σ giá vốn − CAPITAL = realized_pnl`, `CAPITAL = 100 triệu`) hay bảng mới? Còn 20 lệnh paper cũ (46 ngày không đổi), 1 lệnh rác `TEST`, và chênh 415.050 giữa `Σ orders.pnl` (−371.298) và `engine_state.realized_pnl` (+43.752).
5. **`PaperBroker` và `RiskManager`:** bọc/kế thừa (GitNexus: `PaperBroker` 67 nơi bị ảnh hưởng, `RiskManager` 293, mức `HIGH`/`CRITICAL`) hay sửa tại chỗ? Tham số rủi ro cho nhiều mã (`max_positions = 5`, `max_order_value_pct = 0,20`, `risk_pct = 0,01`, `max_daily_loss_pct = 0,03`).
6. **Số phận 3 mã trong `config.yaml`** (HPG, IJC, AAA): giữ để collector tiếp tục stream và các job kiểm (`heartbeat_check.py` 2A, `daily_data_check`, `startup_catchup`) không đổi; bỏ chúng đòi sửa nhiều chỗ (B.4).
7. **`engine-cam` (15:15) và nhánh `engine-consumer`:** `engine-cam` sẽ im lặng khi cờ chỉ nằm ở `main.py` (B.6 câu 2); có cần một phép kiểm "engine ngày đã chạy hôm nay" thay thế?
8. **Gỡ hai import** `heartbeat_check.py:81` (`CAPITAL`) và `check_silent_engine.py:28` (`_default_strategy`) trước khi viết lại `trading/engine/main.py`, hay giữ nguyên hai tên đó trong module mới (A.3)?
9. **Test cũ:** 9 tệp test gắn `trading.engine` (B.5) giữ, sửa hay thay?
10. **Nến ngày và múi giờ:** `bars_daily.ts` là 00:00 VN dạng UTC ngày trước (D.1); engine mới phải chuyển múi giờ trước khi dùng `PaperBroker._day_index`.
