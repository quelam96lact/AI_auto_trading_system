# Khảo sát gỡ container engine cũ (đợt 235)

Người khảo sát: Researcher. Chỉ đọc. Không sửa file nào ngoài báo cáo này, không `docker stop/restart/rm`, không `sched.sh`, không chạy script kiểm tra thật (kể cả `--dry-run`), không ghi DB, không `taskkill`, không đọc `.env`/token. Không có số tài khoản, token hay ID trong báo cáo.

Quy ước: **[đo]** = số lấy từ lệnh chỉ đọc (kèm lệnh); **[đọc]** = đọc code (`file:dòng`, đúng HEAD `de236ac`); **[suy luận]** = từ code, chưa quan sát chạy thật; **[chưa kiểm]** = không kiểm được.

Nền: `docs/audit/2026-11-14-khao-sat-engine-truoc-khi-viet-lai.md` phần A (đợt 228, viết lúc `symbols` còn 3 mã). Đã đối chiếu lại với `5050389` (symbols rỗng, NullStrategy), `e753df3` (siết `check_silent_engine`/`stream_health_check`), `45e4db7` (bước `daily-engine` trong scheduler 21:45). **Hai điều của 228 đã đổi** (A.1 dòng 3 và A.3 rủi ro import), xem mục 0.

Đo lúc ~02:55 sáng Chủ nhật 15/11 (giờ VN).

---

## 0. Tóm tắt (đọc mục này là đủ cho Lead)

1. **`docker compose stop engine` hôm nay, chưa sửa gì:** 2 nguồn kêu, 1 nguồn "chớp rồi tắt", 7 nguồn im.
   - **Kêu: `container-health`** — 1 tin `[CRITICAL] …engine-1: container không ở trạng thái running (Status: exited)` trong ≤10 phút sau khi dừng (24/7, kể cả ban đêm).
   - **Kêu: `heartbeat` dead-man** — `[CRITICAL] service ngừng heartbeat quá 300s: engine`, **không có chống lặp**, bắt đầu **08:00 thứ Hai 16/11**, mỗi 5 phút đến 14:45: **≈61 tin/ngày** [đo: 61 lần chạy trong cửa sổ ngày 13/11]. Tin này còn gộp chung vào tin của mọi cảnh báo thật khác trong cùng lần chạy.
   - **Không kêu nữa (khác 228): `engine-consumer`.** Collector `symbols: []` không còn publish; stream `BARS` đứng ở `last_seq=30979` từ 13/11 14:50 VN; consumer `engine` `num_pending=0` [đo, mục 1.2]. Dừng engine không làm pending tăng.
   - **Không kêu:** `engine-cam` (exit 0 vì `symbols` rỗng), `deploy-drift` (image mới hơn commit, dừng không kích hoạt), `golive gate` (chỉ chạy tay), `morning-summary`, bất biến sổ cũ 2C, `schedule-watch`, Grafana (không có alert rule).
2. **Hai thay đổi nhỏ nhất để dừng sạch** (đợt 1): bỏ `engine` khỏi 3 hằng số (`heartbeat_check.py:85`, `container_health_check.py:69`, `deploy_drift_check.py:41`+`:45`). Đo trên bản sao cô lập: **4 test hỏng bắt buộc sửa** (3 `test_heartbeat_check.py`, 1 `test_deploy_drift_check.py`); trên 9 file liên quan: 218 xanh, 4 hỏng. Sửa `scripts/` làm **image scheduler cũ hơn commit** (`deploy_drift_check.py:43-47`: scheduler canh cả `scripts/`), nên phải rebuild scheduler trước 08:00 thứ Hai, nếu không có 1 tin `deploy-drift` giả (đã từng xảy ra 13/11).
3. **Cạm bẫy thứ tự lớn nhất (mới so với 228):** xoá/đổi tên `trading/engine/main.py` **trước** khi gỡ `from trading.engine.main import CAPITAL` (`heartbeat_check.py:81`) làm **ba** script chết ở import, không phải hai: `heartbeat_check` (dead-man + schedule-watch + morning-summary), `container_health_check` (nó import `heartbeat_check`, `container_health_check.py:34-37`) và `docker_down_alert` (`docker_down_alert.py:21`). Đã mô phỏng chặn import `trading.engine`: cả ba `IMPORT FAIL` [đo, mục 2.4]. Mã thoát 1 thuộc `normal_exit_codes` của `heartbeat` và `container-health` → **mù im lặng toàn bộ giám sát container và dead-man**.
4. **Giám sát engine mới còn hở** (mục 3): chỉ có mã thoát (`notify_job_failure` + `schedule-watch`). Không ai báo khi job **không chạy** (scheduler treo/host ngủ lúc 21:45), khi bị **SKIP** do khoá (rc `None`, không báo), hay khi **sổ sai mà mã thoát 0**. Đề xuất 2 phép kiểm nhỏ trong `heartbeat_check.py` theo khuôn có sẵn, và chúng cũng cho phép gỡ import `CAPITAL`.
5. **Đề xuất: chia hai đợt** (mục 4): đợt 1 = giám sát quên engine + dừng container (đảo ngược được, chỉ chạm `scripts/`); đợt 2 = xoá hẳn (compose, consumer NATS, hai nhánh sched, task Windows, tài liệu) sau ≥ 1 tuần và ≥ 2 lần `daily-engine` chạy tốt. **Xoá code `trading/engine/` tách riêng thành đợt 3 tuỳ chọn**, vì nó là đường duy nhất tạo `pending_real_orders` (mục 2.6).

---

## 1. Nếu `docker compose stop engine` HÔM NAY thì từng nguồn cảnh báo có kêu không

### 1.1. Bảng từng nguồn

Lịch tác vụ [đo] bằng `Get-ScheduledTask 'trading-*'` (chỉ đọc): `container-health` Ready, lần cuối 02:40 hôm nay; `heartbeat-check` Ready, kế tiếp 16/11 08:00; `engine-consumer` Ready, kế tiếp 16/11 09:00; `engine-cam` Ready, kế tiếp 16/11 15:15; `deploy-drift` Ready, kế tiếp 16/11 08:00; `schedule-watch` Ready, hằng giờ phút :07.

| # | Nguồn (file:dòng) | Kêu? | Vì sao | Khi nào / bao nhiêu |
|---|---|---|---|---|
| 1 | `container-health` — `container_health_check.py:69` (`DEFAULT_SERVICES` có `engine`), `:401-411` | **CÓ, 1 tin** | Trạng thái `running` → `exited`; tin chỉ phát khi CHUYỂN trạng thái, sau đó ghi INFO `đã báo trước đó` (`:405-410`). State hiện có mục engine `status: running` [đo `logs/.container_health_state.json`] | ≤10 phút sau khi dừng, 24/7. Chỉ 1 tin duy nhất |
| 2 | `heartbeat` dead-man — `heartbeat_check.py:85` (`SERVICES=("collector","engine")`), `:1059-1066` (`stale_services`), `:1874-1878` | **CÓ, mỗi lần chạy** | Hàng `engine` trong bảng `heartbeat` quá 300 s. Hiện engine còn đập (tuổi 50 s) và collector tuổi 9 s [đo `SELECT service,last_seen,now()-last_seen FROM heartbeat`]. Tin được gửi qua `send_with_outbox` mỗi lần có `messages` (`:1962-1977`), **không có chống lặp** | Cửa sổ `in_check_window` (`:1819-1829`): ngày giao dịch 08:00-11:30 và 13:00-14:45. **[đo] 61 lần chạy trong cửa sổ ngày 13/11** (`logs/heartbeat.log`). Tin đầu: **08:00 thứ Hai 16/11** |
| 3 | `engine-consumer` — `engine_consumer_check.py:96-97`, `:140-150`, `:172-185` | **KHÔNG** (đổi so với 228) | Chỉ báo khi `num_pending ≥ 20` hoặc `last_seq` tiến mà `delivered` đứng. Stream **không còn nhận message** (1.2); `num_pending=0` | Quiet. Lưu ý hai điều: log sẽ in `OK: engine đang tiêu thụ bình thường` dù engine đã dừng (an ủi giả); và nếu sau này `symbols` bật lại mà engine vẫn dừng thì pending tích và tin trở lại (≤19/ngày, cooldown 900 s `:40`) |
| 4 | `engine-cam` — `check_silent_engine.py:198-201` | **KHÔNG** | `symbols` rỗng → in `symbols rỗng: bỏ qua`, `return 0`, **trước cả khi** chạm DB hay container (`:185-201`). Không phụ thuộc container | Quiet. Chết im ở import nếu `trading/engine/main.py` biến mất (`:28`, mục 2.4) |
| 5 | `deploy-drift` — `deploy_drift_check.py:41`, `:45`, `:163-198` | **KHÔNG hôm nay** | `docker inspect` chạy được trên container đã dừng. Image engine tạo 14/11 02:58:08Z, **sau** commit gần nhất chạm `trading/` (`45e4db7`, 14/11 02:50:06Z) và `scripts/` (cùng commit) [đo `docker image inspect`, `git log -1 -- trading/ scripts/`]. `de236ac` (15/11 02:36 VN) chỉ chạm test | Quiet. **Kêu khi:** commit sau chạm `trading/` mà engine không được rebuild (mục 2.5), hoặc container bị xoá (→ `container KHÔNG chạy`, `:97-101`) |
| 6 | Cổng go-live — `check_golive_gate.py:131-152`, `:438-448` | **KHÔNG** | Chỉ chạy tay; phần engine là gọi lại `deploy_drift_check.SERVICES` (`:146`) nên **tự đổi theo** khi sửa `SERVICES`. Không có hạng mục đọc heartbeat/tiêu thụ của engine | Chỉ chữ `Image collector/engine` (`:150`, `:438`, `:448`) cần sửa |
| 7 | `morning-summary` — `heartbeat_check.py:1437-1520` | **KHÔNG** | Không đọc dữ liệu engine; chỉ đếm `logs/alert_outbox_*.jsonl`. **[đo]** hiện **không có file outbox nào** trong `logs/` | Quiet. Nếu engine dừng khi đang có tin chờ trong `alert_outbox_engine.jsonl` (`engine/main.py:929` `start_outbox("engine")`) thì mục "hàng đợi" hiện N tin chờ vĩnh viễn |
| 8 | Bất biến sổ cũ 2C — `heartbeat_check.py:1850-1856`, `:1879-1891` (`ledger_deviation` `:1195`) | **KHÔNG** | Đọc `engine_state(id=1)` và `positions(qty≠0)`. **[đo]** `engine_state`: cash 100.043.751,69, realized 43.751,69, cập nhật lần cuối 28/09; `positions`: 3 dòng, 0 dòng `qty≠0` → độ lệch 0. Engine dừng không đổi gì | Quiet (kiểm vô hại nhưng đã cũ, xem 3.2) |
| 9 | `schedule-watch` — `heartbeat_check.py:785-915`, `:1541` | **KHÔNG** | `engine-cam`/`engine-consumer` nằm trong `KHONG_CANH` (`:192-193`), chỉ canh mã thoát (`:264-277`, chuẩn `{0,1}`); không job nào đổi mã thoát khi engine dừng | Quiet |
| 10 | Grafana — `grafana/provisioning/dashboards/trading.json` | **KHÔNG** | Không có thư mục `alerting`. Bảng "Sức khoẻ service" (`:62-68`) cho `age_seconds` engine tăng dần, không ngưỡng; bảng `engine_state`/`pnl_daily`/`positions` đứng | Hình ảnh sai trên dashboard, không tin |
| 11 | `stream-health`, `docker_down_alert`, `host_preflight`, `backup`, `restore-drill` | **KHÔNG** | `stream_health_check` không đọc engine và thoát 0 khi `symbols` rỗng (`e753df3`); `docker_down_alert` chỉ khi **Docker** tắt (`:176` câu chữ); `host_preflight` không có `engine`; backup/restore-drill đếm cả bảng `engine_state` như mọi bảng, bảng còn nguyên | Quiet |

Ngoài tin: `restart: unless-stopped` (`docker-compose.yml:95`) → container đã dừng thủ công không tự chạy lại sau khi Docker khởi động lại [suy luận theo tài liệu Docker, chưa kiểm]. Nhưng **`docker compose up -d` không nêu tên dịch vụ**, hay các lệnh triển khai trong `DEPLOYMENT.md:873`, `:890` (`up -d --no-deps collector engine`), sẽ chạy lại engine.

### 1.2. NATS: còn message vào không? [đo]

Lệnh chỉ đọc (script riêng, nằm ngoài repo: `scratchpad/e235/nats_ro.py`, `nats_msgs.py`; chỉ gọi `stream_info`, `consumer_info`, `get_msg`; không ack, không tạo/xoá consumer):

```
STREAM BARS messages=268 first_seq=30712 last_seq=30979 consumers=1
STREAM config max_age=604800.0s subjects=['bars.>']
CONSUMER engine num_pending=0 num_ack_pending=0 redelivered=0 delivered.stream_seq=30979 ack_floor.stream_seq=30979
30977 bars.ssi.AAA 2026-11-13 07:50:28Z ... "ts": "2026-11-13T14:45:00+07:00"
30978 bars.ssi.HPG 2026-11-13 07:50:28Z
30979 bars.ssi.IJC 2026-11-13 07:50:28Z
```

- **Không còn message vào.** Ba message cuối là nến ATC 14:45 của 13/11 (14:50 VN). Từ đó đến lúc đo ≈ 36 giờ không có message nào. Collector log: `collector chay khong stream: cfg.symbols rong` (`logs/bars_closed.log`, 14/11 19:07Z = 02:07 15/11 VN), khớp `collector/main.py:465-468` (`feed.start()` chỉ chạy khi `cfg.symbols`).
- Nơi duy nhất publish vào `BARS` là collector (`collector/main.py:94`, `:487`; `grep BarPublisher` ngoài test không có chỗ khác). `run_backfill` không nhận `pub` nên không publish.
- Cũ hơn 228: stream thêm ~131 tin/ngày; nay 0/ngày.
- Stream còn 268 message, tự hết hạn sau 7 ngày (`max_age=604800s`, ~20/11). Consumer bền `engine` còn nguyên, một mình.
- **Collector vẫn cần NATS**: `collector/main.py:421-422` `BarPublisher.connect()` lúc khởi động, `depends_on: nats` (`docker-compose.yml:115-117`). Gỡ engine **không** gỡ `nats`.

### 1.3. Những gì đã đổi so với 228 (đối chiếu A.1, A.2, A.3)

| Mục 228 | Trạng thái nay |
|---|---|
| A.1 #1 `container-health` 1 tin | **Giữ nguyên** (`container_health_check.py` không đổi từ 49425b0) |
| A.1 #2 `heartbeat` ~60-63 tin/ngày | **Giữ nguyên**: 61 [đo]. Số dòng dịch: `SERVICES` `:85`, tin `:1877` |
| A.1 #3 `engine-consumer` ≤19 tin/ngày | **Đổi: 0 tin** (không còn message). Script không đổi (`git diff 49425b0..HEAD -- scripts/engine_consumer_check.py` rỗng): vẫn **không có chốt `symbols`** |
| A.1 #4 `deploy-drift` | Giữ. Hiện xanh (image 14/11 02:58Z > commit 02:50Z) |
| A.2 xoá container → EXIT=4 mỗi 10 phút | **Giữ nguyên** (không đổi `container_health_check.py:306-325`) |
| A.2 xoá consumer → ≈49-50 tin/ngày | **Giữ nguyên** (script không đổi, `:144-150` gọi thẳng `send_telegram`, không cooldown) |
| A.3 `check_silent_engine` import `_default_strategy` | Giữ; nay vô nghĩa vì `symbols` rỗng nên script thoát 0 trước khi cần chiến lược |
| A.3 `heartbeat_check` import `CAPITAL` | Giữ `:81`, **blast radius rộng hơn 228 nêu**: xem 2.4 |
| A.4 bất biến sổ sách `:1696-1737` | Dịch sang `:1850-1891` (đợt 211 tách hàm) |
| Dòng 2A đọc `bars` theo `cfg["symbols"]` | Nay có chốt `if symbols:` (`:1842-1849`, `:1892-1893`): rỗng → in `symbols rỗng: bỏ qua kiểm nến stream`, không `IN ()` |

---

## 2. Thay đổi tối thiểu để gỡ hẳn engine cũ

### 2.1. Bảng giữ / sửa / bỏ

| Hạng mục | file:dòng | Quyết định | Ghi chú |
|---|---|---|---|
| Service `engine` | `docker-compose.yml:71-100` (30 dòng, gồm `ENGINE_STRATEGY_DISABLED` `:90-91`, `volumes` `:99-100`) | **Bỏ** (đợt 2) | Collector/scheduler không `depends_on` engine. `test_compose_init.py` kiểm `("engine","collector","scheduler")` → sửa 1 test |
| `DEFAULT_SERVICES` | `container_health_check.py:69`, docstring `:4` | **Sửa** (đợt 1): bỏ `"engine"` | Sau sửa, mục `engine` còn trong file state `logs/.container_health_state.json` là vô hại (vòng lặp theo `stats_map`, `:300-326`); có thể xoá tay |
| `SERVICES` deploy-drift | `deploy_drift_check.py:41`, `SERVICE_WATCH_PATHS` `:45`, docstring `:70`, tin gợi ý `:112-113`, tin OK `:266` | **Sửa** (đợt 1) | `check_golive_gate.py:146` import `SERVICES` nên tự theo; chữ ở `:150`, `:438`, `:448` sửa tay |
| `SERVICES` heartbeat | `heartbeat_check.py:85`; docstring `:1`, `:1208` | **Sửa** (đợt 1): `("collector",)` | Hàng `engine` trong bảng `heartbeat` còn lại bị bỏ qua; panel Grafana (`trading.json:68`) vẫn hiện nó với tuổi tăng mãi → xoá dòng DB (ghi, đợt 2) hoặc lọc trong truy vấn panel |
| Nhánh `engine-consumer` | `sched.sh:14`, `:111-114`, `:212`; `heartbeat_check.py:193`, `:271-277`; `engine_consumer_check.py` (229 dòng); `DEPLOYMENT.md:540-543`, `:639`, `:819`; task Windows `trading-engine-consumer` | **Bỏ** (đợt 2) | Phải gỡ **trước** khi xoá consumer NATS (2.3) |
| Nhánh `engine-cam` | `sched.sh:13`, `:106-109`, `:212`; `heartbeat_check.py:192`, `:264-270`; `check_silent_engine.py` (275 dòng); `DEPLOYMENT.md:548-549`, `:641`, `:818`, `:963-987`; task Windows `trading-engine-cam` | **Bỏ** (đợt 2) | Đã vô nghĩa với `symbols` rỗng. Khi cắm chiến lược thật vào `daily_engine`, thiết kế "chiến lược câm" riêng (không dùng bar 5 phút) |
| Import `CAPITAL` | `heartbeat_check.py:81` (dùng ở `:1196` mặc định tham số và `:1889`) | **Bỏ** (đợt 1 hoặc đầu đợt 2, **trước** mọi đụng chạm `trading/engine/`) | Thay bằng bất biến sổ mới đọc `capital` từ `paper_daily_state` (3.2): không cần hằng số. `runner.py:25` đã có một bản sao `CAPITAL = 100_000_000.0` thứ hai (comment `heartbeat_check.py:77-80` cấm chép số); nên có một hằng duy nhất, ví dụ trong `trading/config.py` |
| Import `_default_strategy` | `check_silent_engine.py:28` | **Biến mất cùng script** (đợt 2) | Người dùng khác của `_default_strategy` chỉ là test (2.6) |
| Consumer bền NATS `engine` | `engine/main.py:704-709` (`durable="engine"`, `DeliverPolicy.ALL`) | **Xoá** (đợt 2, thủ công, ghi) | Sau khi `engine-consumer` đã gỡ và task Windows đã gỡ. Không xoá được trước (≈49-50 tin/ngày, A.2). Không bắt buộc: pending 0 và để yên cũng vô hại, nhưng nếu `symbols` bật lại thì pending tích mãi |
| Hàng `heartbeat.service='engine'` | bảng `heartbeat` | **Xoá** (đợt 2, ghi) | Tránh panel Grafana sai |
| `trading/engine/` (`main.py` 934 dòng, `logic.py` 138) | — | **Tuỳ chọn, đợt 3** | 2.6 |
| Tài liệu | `DEPLOYMENT.md:3`, `:52-56`, `:287`, `:349`, `:447-451`, `:478-481`, `:495`, `:540-549`, `:635-641`, **`:727-728`**, `:818-819`, `:834-890`, `:963-987`, `:997-1017`; `CLAUDE.md`, `README.md`, `scripts/README.md` | **Sửa** | `:727-728` là thủ tục kiểm chứng dead-man bằng cách `docker compose stop engine` — sẽ sai ngay sau đợt 1 (engine không còn được canh). `test_deployment_doc.py` bắt buộc crontab khớp `sched.sh` hai chiều và mọi `scripts/...` nhắc tới phải tồn tại |

### 2.2. Giữ nguyên (không đụng trong đợt nào)

- `postgres`, `nats`, `collector`, `scheduler`, `grafana`; `nats-test`.
- Bảng cũ `engine_state`, `positions`, `orders`, `pnl_daily`, `pending_real_orders` (backup/restore-drill đếm chúng, `verify_backup_restore.py:31-35`); mixin `storage` tương ứng và `test_storage_engine.py` (13 test integration).
- `trading/paper_broker.py` (hằng số được `daily_engine/core.py` import), `risk.py`, `trailing_stop.py`, `real_orders.py`, `real_order_reconcile.py`: còn người dùng ngoài engine (`backtest.py`, `collector/account_sync.py`, `storage/orders.py`, ...).
- `trading/strategies/null_strategy.py`: chỉ `engine/main.py` dùng; chết khi đợt 3, không đụng trước.

### 2.3. NATS consumer durable `engine`

Tạo ở `engine/main.py:704-709`. Không ai khác tạo/đọc nó ngoài `engine_consumer_check.py:43-62`. Thứ tự xoá: (a) gỡ task Windows `engine-consumer` và nhánh sched; (b) dừng engine; (c) `js.delete_consumer("BARS","engine")` (ghi, thủ công, ngoài brief này). Không xoá stream `BARS`: collector `pub.connect()` dựng lại nếu thiếu nhưng không cần xoá.

### 2.4. Dây import: phép thử chặn `trading.engine` [đo]

Chặn import (`sys.modules['trading.engine']=None`, mô phỏng xoá/đổi tên), rồi import từng script:

```
scripts.heartbeat_check            IMPORT FAIL ModuleNotFoundError import of trading.engine.main halted
scripts.container_health_check     IMPORT FAIL  (qua from scripts.heartbeat_check import get_last_called_timestamp, :34-37; nhánh except ImportError :36-37 cũng hỏng vì cùng lỗi gốc)
scripts.docker_down_alert          IMPORT FAIL  (from scripts.heartbeat_check import in_bar_check_window, :21)
scripts.check_silent_engine        IMPORT FAIL  (:28)
scripts.deploy_drift_check         import OK
scripts.check_golive_gate          import OK
scripts.engine_consumer_check      import OK
scripts.stream_health_check        import OK
```

Hệ quả [suy luận từ mã thoát]: traceback → thoát **1**. Mã 1 nằm trong `normal_exit_codes` của `heartbeat` (`:215-221`) và của `container-health` (`:257-262`, chuẩn `{0,1,2}`) → `schedule-watch` (cùng file với heartbeat, cũng chết) **không** báo. Kết quả: dead-man, schedule-watch, morning-summary, container-health, cảnh báo Docker tắt **cùng mù**, không một tin. Tổng 322 test thuộc 14 file import `heartbeat_check` (`grep -l heartbeat_check tests/`) cũng vỡ nếu quên.

### 2.5. `deploy-drift` sau commit gỡ

`SERVICE_WATCH_PATHS` (`deploy_drift_check.py:43-47`): `collector`, `engine` canh `trading/`; `scheduler` canh `trading/` **và** `scripts/`. Cho nên:

- Commit đợt 1/2 chỉ chạm `scripts/`, `tests/`, `docs/`, `docker-compose.yml`: **chỉ scheduler** cũ hơn commit → phải `docker compose build scheduler && docker compose up -d --no-deps scheduler` trước 08:00 ngày giao dịch kế tiếp (đúng sự cố 13/11: `deploy-drift.log` "scheduler: image CŨ … (1 giờ 25 phút)").
- Commit chạm `trading/` (xoá `trading/engine/`, đợt 3): collector **và** scheduler phải rebuild.
- Không rebuild/restart collector trong đợt 1/2 nếu `trading/` không đổi.

### 2.6. Test bị ảnh hưởng (đếm bằng bản sao cô lập từ `git archive HEAD` + `pytest -m "not integration"`; tổng nền 2.450 chạy được, 170 integration không chạy)

**Đợt 1** (3 hằng số): sửa bắt buộc **4 test** hỏng:
- `tests/test_heartbeat_check.py`: `test_service_past_max_age_is_stale` (`:27`), `test_missing_service_row_is_stale` (`:35`), `test_all_services_missing_are_stale` (`:40`) — kỳ vọng `["engine"]`/`["collector","engine"]`, đổi sang `collector`.
- `tests/test_deploy_drift_check.py::test_scheduler_in_services` (`:130`, `SERVICE_WATCH_PATHS["engine"]` `:134` → `KeyError`).
- 9/14 test trong `test_deploy_drift_check.py` còn nhắc `engine` (`:14`, `:18`, `:31`, `:39`, `:47`, `:122`, `:143-155`, `:179`) nhưng **vẫn xanh** (`drift_report` nhận khoá lạ) — nên dọn cho khỏi kiểm một dịch vụ đã không còn.
- `test_container_health_check.py`: không test nào hỏng (`DEFAULT_SERVICES` chỉ khẳng định có `scheduler`, `:503`); `engine` ở `:1060-1103` chỉ là tên container tuỳ ý.
- Mô phỏng (9 file: heartbeat_check, container_health_check, deploy_drift_check, check_golive_gate, schedule_watch, morning_summary, heartbeat_foreign_flow, heartbeat_prev_day_5m, heartbeat_prev_day_bars): 218 xanh, 4 hỏng, 1 bỏ chọn (integration).

**Đợt 2** (thêm: compose, hai nhánh sched, hai policy, xoá hai script và hai file test): bản sao cô lập cho **11 hỏng** sau khi xoá `test_engine_consumer_check.py` (15 test) và `test_silent_engine_guard.py` (11 test) — vậy xoá **26 test**, sửa **11**:
- `test_compose_init.py::test_core_services_have_init_true` (1)
- `test_deploy_drift_check.py::test_scheduler_in_services` (1, như trên)
- `test_entry_exit_code_3.py` (3): hai tham số `engine-cam`, `engine-consumer` và `test_exit_policies_exclude_exit_code_3` (vòng lặp qua `SCRIPTS`)
- `test_heartbeat_check.py` (3, như trên)
- `test_schedule_watch.py` (3): `test_sched_branches_covered_in_exit_policies` (`assert len(sched_branches) == 22` → 20), `test_sched_branches_covered_in_watch_or_khong_canh`, `test_dot225_two_branches_self_healed_emits_two_warns_single_telegram` (`:1180-1212` dùng `engine-cam` làm ví dụ)
- Kết quả bản sao: **2.407 xanh, 11 hỏng, 170 bỏ chọn** (tổng thu thập 2.450 → 2.418: −26 do xoá hai file test, −6 do `tests/test_sched_args.py` tự co lại vì tham số hoá theo danh sách script, 3 test × 2 script). `test_deployment_doc.py` xanh **chỉ khi** `DEPLOYMENT.md` được sửa đồng bộ (crontab khớp `sched.sh`; không nhắc script đã xoá).
- `test_morning_summary.py` dùng tên file `alert_outbox_engine-cam.jsonl` chỉ như tên mẫu: không hỏng.

**Đợt 3** (xoá `trading/engine/`) — liệt kê theo `grep trading.engine` (**không** đo được bằng bản sao cô lập: bản cài editable của venv trỏ `trading.*` về repo thật, nên submodule bị xoá ở bản sao vẫn import được — nên dùng phép chặn import ở 2.4):
- Xoá cùng code: `test_engine_main.py` (66, **toàn bộ integration**), `test_engine_logic.py` (16), `test_engine_gap1.py` (9), `test_null_strategy.py` (14) = **105 test**.
- Sửa/chuyển `_default_strategy`: `test_compare_timeframe_mismatch.py` (4, import mức module `:21`), `test_real_trading_guard.py` (9, `:27`), `test_strategy_conformance.py` (1/5, `:111`). Cần quyết `_default_strategy` (đối chứng cấu hình octopus) ở đâu: ví dụ `trading/strategies/octopus_pullback.py`.
- Chỉ nhắc tên trong chuỗi, không hỏng: `test_logging_setup.py`, `conftest.py:55` (comment), `test_measure_bar_latency.py` (nhưng `scripts/measure_bar_latency.py` đọc `engine_alerts.log`, sẽ không còn dữ liệu).

**Vì sao đợt 3 tách riêng** [đọc]: `engine/main.py` là nơi duy nhất sinh `pending_real_orders` và cảnh báo chạm stop cho tài khoản thật: `real_orders.handle_crossover` (`:744`), `handle_stop_touch` (`:877`), `expire_stale_pending_orders` (`:733`; `storage/orders.py:263`, chỉ nơi này gọi). **[đo]** hiện `pending_real_orders` có 9 dòng, tất cả `expired` (cũ nhất 14/08, mới nhất 04/09), `real_order_fills` 0 dòng; `real_trading_enabled: false`; engine log `vi the that ngoai cfg.symbols, engine khong quan ly` cho các vị thế thật → **dừng engine không làm mất bảo vệ nào đang có**. Nhưng xoá code là xoá luôn đường lệnh thật đã được xây qua nhiều đợt (`confirm_real_order.py`, `check_real_order_readiness.py`, `rehearse_confirm_gate.py` còn đứng trên các bảng đó): đó là quyết định của chủ dự án, không phải của việc "gỡ container".

---

## 3. Giám sát cần thêm cho engine mới (`daily-engine`)

### 3.1. Hiện có và chưa đủ

Hiện có [đọc `trading/scheduler/main.py:468-487`, `:136-218`, `:281-303`, `heartbeat_check.py:355-360`]:

| Tình huống | Có ai báo không |
|---|---|
| Runner thoát ≠ 0 (1 = dữ liệu < 90% mã active; 2 = cấu hình/chiến lược sổ không khớp; 3 = ngoại lệ; 124 = quá 15 phút) | **Có**: `notify_job_failure` → `alert("CRITICAL", …)` ngay trong chuỗi 21:45 (`:480-487`); và `schedule-watch` đọc `daily-engine.log` với chính sách `{0}` (`heartbeat_check.py:355-360`) |
| Container `scheduler` chết/khởi động lại/OOM | **Có**: `container-health` (`DEFAULT_SERVICES` có `scheduler`, đợt 202) |
| Dữ liệu ngày không đủ | **Có**: heartbeat kiểm độ đủ nến ngày liền trước (`prev_day_bars_alert` `:1307`) và runner thoát 1 |

Còn hở (ba lối im lặng):

1. **Job không chạy.** `daily-engine` **không** nằm trong `SCHEDULE_WATCH_JOBS` (`:136-180`) cũng không trong `KHONG_CANH` (`:184-202`): test cố ý trừ nó ra (`test_schedule_watch.py:289-290`, giống `universe-refresh`). Nên scheduler treo/vòng lặp chết/máy ngủ qua 21:45 → không dòng log, không mã thoát, không tin. (Runner **tự bù**: lần sau xử lý mọi phiên chưa xử lý, `runner.py:_execute_engine` vòng `todo_sessions`; nhưng ngày bỏ lỡ không ai biết.)
2. **SKIP do khoá.** `run_job` ghi `SKIP: dang co tien trinh khac` và trả `None` (`scheduler/main.py:160-164`); điều kiện báo là `rc is not None and rc != 0` (`:480`) nên **không báo**; `schedule-watch` đọc mã thoát của lần chạy thật nên cũng bỏ qua.
3. **Mã thoát 0 mà sổ sai/đứng.** Ví dụ `todo_sessions` rỗng vì lịch nghỉ lễ cấu hình sai, hoặc sổ lệch do lỗi tính (trường hợp 228 D "bất biến sổ cũ kêu giả hoặc im sai"). Không phép kiểm nào nhìn `paper_daily_*`.

### 3.2. Đề xuất: hai phép kiểm nhỏ trong `heartbeat_check.py` (khuôn có sẵn, không thêm job)

(a) **Độ trễ xử lý phiên** — theo khuôn `prev_day_bars_alert`/`_check_prev_day_completions` (`:1307`, `:1648`; một tin mỗi ngày nhờ file trạng thái `alerted_for`): trong cửa sổ kiểm của ngày giao dịch D, nếu `paper_daily_state.last_processed_date < previous_trading_day(D)` → `[CRITICAL] daily-engine chưa xử lý phiên …`. Bắt được lối im lặng 1, 2 và một phần 3. Khi chưa có dòng `paper_daily_state` (trước lần chạy đầu 16/11 21:45) → không báo; sau đó thiếu dòng → báo. Truy vấn: `SELECT last_processed_date FROM paper_daily_state`.

(b) **Bất biến sổ mới** — dùng lại `ledger_deviation` (`:1195`). Với sổ mới `lot.cost_per_share = px×(1+FEE)` (`§3` brief 233, đã được `check_233.py` 31/31 kiểm), nên đồng nhất thức sau **đúng chính xác**: `cash + Σ(qty × cost_per_share) − capital == realized_pnl`. Truy vấn: `capital, cash, realized_pnl FROM paper_daily_state` và `SUM(qty*cost_per_share) FROM paper_daily_lots`. Thay cho khối cũ `:1850-1891`, và **chính nó** cho phép bỏ `import CAPITAL` (lấy `capital` từ hàng sổ).

Ước lượng: ~40 dòng + ~10 test theo mẫu `test_heartbeat_prev_day_bars.py`/`test_heartbeat_check.py` (fake cursor, đã trả lời `FROM engine_state` ở 7 chỗ: `test_heartbeat_check.py:247`, `:391`, `:527`, `:954`, `:1089`, `:1372`, `:1407`; `test_heartbeat_foreign_flow.py:202`; `test_heartbeat_prev_day_5m.py:246`; `test_heartbeat_prev_day_bars.py:110` — nếu đổi truy vấn thì cập nhật các fixture này).

Không cần thêm: NAV liên tục, phép kiểm hiệu năng, heartbeat cho `daily-engine` (không phải dịch vụ dài hạn).

Câu trả lời cho câu hỏi của Lead: **mã thoát chưa đủ**; thiếu đúng hai thứ trên.

---

## 4. Một đợt hay hai? Thứ tự an toàn

**Đề xuất: hai đợt chính, đợt 3 tuỳ chọn.**

### Đợt 1 — "giám sát quên engine, rồi dừng" (chỉ `scripts/`, tests; đảo ngược được)

1. Sửa 3 hằng số và 4 test (2.6). Tuỳ chọn gộp 3.2 (a)(b) và gỡ import `CAPITAL` ngay để đợt 3 sau này không có cạm bẫy 2.4.
2. Commit (không chạm `trading/`).
3. Rebuild + `up -d --no-deps scheduler` (ngoài 21:45, tránh lúc đang chạy chuỗi tối); **không** động collector.
4. **Sau đó** `docker compose stop engine` (container còn, dễ `start` lại). Kiểm một chu kỳ `container-health` (10 phút) không tin, và `heartbeat` sáng thứ Hai không có `engine`.
5. Để yên `engine-consumer`, `engine-cam` (quiet, 1.1) hoặc `Disable-ScheduledTask` hai task Windows (đảo ngược được, tránh log "OK engine đang tiêu thụ" sai).

Điều kiện chờ trước khi sang đợt 2: ≥ 1 tuần giao dịch, ≥ 2 lần `daily-engine` exit 0 (lần đầu 16/11 21:45 chỉ khởi tạo, `runner.py` trả 0 khi `state is None`), phép kiểm 3.2 đã chạy ít nhất một ngày thật.

### Đợt 2 — "xoá" (chạm `scripts/`, tests, compose, tài liệu, thao tác ngoài repo)

Thứ tự, mỗi mũi tên là ràng buộc bằng chứng:
1. Gỡ (hoặc `Unregister`) task Windows `trading-engine-cam`, `trading-engine-consumer` **trước** khi xoá nhánh trong `sched.sh` (nếu không, task gọi nhánh không tồn tại; không ai canh LastTaskResult).
2. Xoá nhánh sched + policy + KHONG_CANH + hai script + test (2.1, 2.6) + sửa `DEPLOYMENT.md` đồng bộ (`test_deployment_doc.py`) → rebuild scheduler.
3. `docker compose rm -f engine` **sau** khi `container-health`/`deploy-drift` không còn nhắc `engine` (nếu không: `EXIT=4` mỗi 10 phút và "container KHÔNG chạy" mỗi sáng, 228 A.2); rồi bỏ khối `engine` khỏi `docker-compose.yml` (+ `docker compose up -d --remove-orphans` nếu cần).
4. Xoá consumer NATS `engine` (2.3) **sau** bước 2.
5. Xoá `heartbeat.service='engine'` (hoặc lọc panel).
6. Dọn `logs/engine_alerts.log`, `alert_outbox_engine.jsonl` nếu có (morning-summary đếm mọi `alert_outbox_*.jsonl`).

### Đợt 3 (tuỳ chọn, sau quyết định về đường lệnh thật)

Gỡ `trading/engine/` + 105 test + sửa 14 test dùng `_default_strategy`; **bắt buộc** đã gỡ import `CAPITAL` (2.4). Chạm `trading/` ⇒ rebuild **collector và scheduler** (2.5).

### Rủi ro còn lại / cần Lead quyết

1. Chủ dự án có muốn giữ đường lệnh thật của engine cũ (đợt 3) hay xoá luôn? Quyết trước khi lập brief đợt 3.
2. Gộp 3.2 vào đợt 1 hay làm thành đợt riêng (nó cho phép gỡ `CAPITAL` sớm, giảm rủi ro ở đợt 3).
3. Hằng `CAPITAL` nhân đôi (`engine/main.py:33`, `daily_engine/runner.py:25`): nên có một nguồn duy nhất (`trading/config.py`).
4. `engine-consumer` giờ báo `OK engine đang tiêu thụ bình thường` dù không có engine: nếu để đến đợt 2, chấp nhận câu chữ sai đó hoặc tắt task ngay ở đợt 1.

---

## 5. Phạm vi kiểm và phần chưa kiểm

**Đã làm (chỉ đọc):** đọc `docker-compose.yml`, `container_health_check.py`, `deploy_drift_check.py`, `heartbeat_check.py` (các khối SERVICES, KHONG_CANH, SCHEDULE_EXIT_POLICIES, ledger, cửa sổ kiểm, gửi tin), `engine_consumer_check.py` (toàn bộ), `check_silent_engine.py` (toàn bộ), `sched.sh`, `trading/scheduler/main.py` (`run_job`, `notify_job_failure`, `run_event`), `trading/daily_engine/runner.py` (toàn bộ), `trading/engine/main.py:690-934`, `trading/collector/main.py:405-505`, `DEPLOYMENT.md` các dòng đã trích, tests liên quan (grep + đọc đoạn). Đo: `docker ps/inspect/logs`; `Get-ScheduledTask` (chỉ đọc); `psql SELECT` (heartbeat, engine_state, positions, orders, paper_daily_*, pending_real_orders, real_order_fills); NATS chỉ đọc (`stream_info`, `consumer_info`, `get_msg`); `pytest --collect-only` và `pytest -m "not integration"` trên **bản sao** `git archive HEAD` ở scratchpad (repo thật không bị ghi; `git status` sạch).

**Chưa kiểm:**
- Dừng thật (cấm): mọi con số tin dựa trên đọc code và số lần chạy trong log, chưa quan sát một lần dừng.
- Hành vi `restart: unless-stopped` sau khi Docker Desktop khởi động lại (suy luận từ tài liệu).
- `docker_down_alert` và `morning-summary` chỉ kiểm phần liên quan engine bằng grep + đọc; không chạy.
- Đợt 3: số test không đo bằng bản sao cô lập (xem 2.6), chỉ liệt kê bằng `grep` và đếm bằng `--collect-only` trên repo thật.
- Lần chạy `daily-engine` đầu tiên chưa xảy ra (`paper_daily_state`, `paper_daily_orders`, `paper_daily_nav` đều rỗng [đo]); phép kiểm 3.2 vì thế chưa thử trên dữ liệu thật.
- Thao tác ngoài repo (task Windows, consumer NATS, dòng `heartbeat`) chưa thử và nằm ngoài quyền của khảo sát này.
