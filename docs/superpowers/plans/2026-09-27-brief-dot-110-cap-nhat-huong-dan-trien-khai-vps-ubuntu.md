# Brief đợt 110 — Cập nhật hướng dẫn triển khai Docker trên VPS Ubuntu

Ngày giao: Chủ nhật 27/09/2026. Base: main `dcda990`.
Người audit: Claude. Người thực thi: agent.

Agent **không** commit, **không** push, **không** build hay restart container của stack đang chạy, **không** sửa Task Scheduler, **không** ghi DB thật. Container thử nghiệm tạm thì được phép, nhưng phải đặt tên riêng và xoá sau khi dùng (xem §3).

## 0. Bối cảnh

**Đã có sẵn hướng dẫn:** `DEPLOYMENT.md` ở gốc repo, 526 dòng, tiêu đề "Deployment Guide — Ubuntu VPS". **Không viết file mới.** Việc của đợt này là **cập nhật file đó** cho khớp với hệ thống hiện tại.

Lần cuối file được sửa là 19/09 (`3c2d63f`, đợt 65). Từ đó đến nay hệ thống đã đổi, còn file thì không. Claude kiểm ngày 27/09 và thấy các chỗ lệch sau:

| Chỗ lệch | Bằng chứng |
|---|---|
| **Múi giờ.** Mọi giờ cron trong file là giờ VN, nhưng file không nhắc tới `timedatectl`, `CRON_TZ` hay `Asia/Ho_Chi_Minh` (đếm được 0 lần). VPS mặc định chạy UTC, nên mọi job sẽ chạy **lệch 7 tiếng**: backfill 20:30 thành 03:30 sáng hôm sau, heartbeat chạy lúc đêm. | grep `DEPLOYMENT.md` |
| **Thiếu 2 job.** File ghi "7 job", nhưng `scripts/sched.sh` và Task Scheduler đã có **9**. Hai job thiếu là `orderbook-recorder` (08:40) và `orderbook-daily-check` (15:30), thêm ở đợt 89–94. File nhắc "orderbook" 0 lần. | `sched.sh`, `Get-ScheduledTask` |
| **Thư mục `data/orderbook/`.** Máy ghi sổ lệnh chạy **trên host** (`uv run` qua `sched.sh`) và ghi file `.jsonl.gz` vào đây. File không nói cách tạo thư mục, phân quyền, sao lưu hay tính dung lượng cho thư mục này. | `sched.sh:83-89` |
| **Công cụ trên host.** Mọi job cron gọi `uv run python ...` trên host, nên host cần có `uv` và phải chạy `uv sync`. File nhắc `uv sync` 0 lần. | `sched.sh:23-27` |
| **Chuyển từ máy Windows hiện tại sang VPS.** File chưa có mục nào cho việc này: chuyển DB TimescaleDB, `data/orderbook`, `logs`, và thứ tự cắt chuyển để **không bao giờ có hai stack cùng chạy**. | không có |

**Lịch hiện tại trên máy Windows** (Claude đọc bằng `Get-ScheduledTask` ngày 27/09). Tất cả chạy **T2–T6** (`dow=62`), giờ VN:

| Job trong `sched.sh` | Giờ bắt đầu | Lặp |
|---|---|---|
| heartbeat | 08:00 | mỗi 5 phút (Windows không ghi giờ kết thúc; file hiện ghi 08:00–15:55) |
| deploy-drift | 08:00 | một lần |
| orderbook-recorder | 08:40 | một lần (tự dừng `--until 14:46`) |
| engine-consumer | 09:00 | mỗi 5 phút (file hiện ghi đến 15:10) |
| stream-health | 15:10 | một lần |
| engine-cam | 15:15 | một lần |
| orderbook-daily-check | 15:30 | một lần |
| backfill | 20:30 | một lần |
| daily-check | 21:00 | một lần |

Agent tự đọc lại `Get-ScheduledTask` (chỉ đọc), đối chiếu với bảng này, và ghi mọi chỗ khác nguyên văn.

## 1. Giả định (không chắc thì ghi vào báo cáo, không tự quyết)

- **VPS:** Ubuntu **24.04 LTS**, x86_64, có quyền sudo. Chỗ nào 22.04 khác thì ghi chú một dòng.
- **Vai trò của VPS:** chạy **thay** máy Windows, không chạy song song. Hướng dẫn phải có hai đường:
  - (a) cài mới hoàn toàn;
  - (b) chuyển dữ liệu từ máy Windows sang.
- **`real_trading_enabled` giữ `false`** trên VPS. Bật lệnh thật là quyết định riêng của chủ dự án, sau các bước diễn tập T3/T4. Hướng dẫn phải nói rõ điều này.
- **SSI chưa được kiểm từ IP nước ngoài.** Chưa ai kiểm SSI FastConnect có chấp nhận IP của VPS không, nhất là VPS đặt ngoài Việt Nam. Hướng dẫn phải có bước **kiểm trước khi cắt chuyển**: chạy một lệnh chỉ đọc (xác thực và lấy dữ liệu thị trường) từ VPS. **Không khẳng định** SSI có hay không có whitelist IP nếu không có nguồn; không có nguồn thì viết "chưa xác minh".

## 2. Phạm vi file

| File | Được làm gì |
|---|---|
| `DEPLOYMENT.md` | Sửa tại chỗ. **Giữ** các mục đang đúng, như §10 rollback `:previous` và các phép kiểm sau triển khai. Không viết lại từ đầu, không đổi giọng văn. |
| `tests/test_deployment_doc.py` | **Mới.** Test chống lệch tài liệu, xem §3 bước 5. |
| `.env.example` | Chỉ thêm biến còn thiếu so với các biến `docker-compose.yml` và `trading/config.py` đọc. **Không** ghi giá trị thật. |

**Không được đụng:**
- `sched.sh`, `run_if_docker_up.sh`, `backup_db.sh`, `log_rotate.sh`: chỉ đọc. Nếu thấy lỗi chạy trên Linux thì **báo lại**, không sửa.
- `docker-compose.yml`, `Dockerfile`, `config/`, code trong `trading/`, Task Scheduler.

## 3. Các bước

GitNexus không cần cho đợt này, vì không sửa symbol code nào. Riêng test mới thì chạy `detect-changes` cuối đợt.

1. **Kiểm kê, chỉ đọc.** Lập 4 bảng:
   - (a) mọi job trong `sched.sh` ↔ dòng cron trong `DEPLOYMENT.md` ↔ task Windows;
   - (b) mọi biến môi trường mà `docker-compose.yml` và `trading/config.py` đọc ↔ `.env.example` ↔ `DEPLOYMENT.md`;
   - (c) mọi volume và bind mount (`pgdata`, `natsdata`, `./logs`, `./grafana/provisioning`) cùng mọi thư mục host mà script ghi vào (`logs/`, `data/orderbook/`, thư mục backup) ↔ hướng dẫn tạo và phân quyền;
   - (d) mọi lệnh trong `DEPLOYMENT.md` có tham chiếu tới file hoặc script: file đó có tồn tại không.

   → **Kiểm chứng bằng:** dán 4 bảng, đánh dấu từng dòng thiếu hoặc sai.

2. **Sửa `DEPLOYMENT.md`.** Tối thiểu phải có:
   - **Múi giờ:** `sudo timedatectl set-timezone Asia/Ho_Chi_Minh` **và** `CRON_TZ=Asia/Ho_Chi_Minh` ở đầu khối crontab (dùng cả hai cho chắc), kèm lệnh kiểm `timedatectl` / `date`.
   - **Khối crontab đủ 9 job,** mỗi job một dòng dạng `cd /opt/trading && scripts/sched.sh <job>`, giờ khớp bảng §0. Chỗ nào giờ kết thúc của job lặp khác nhau giữa Windows và file cũ thì **chọn theo file cũ** và ghi rõ đã chọn.
   - **Host:** cài `uv` (lệnh cài chính thức, ghi nguồn URL), `uv sync --frozen`, và kiểm bằng `uv run python -c "import trading"`.
   - **`data/orderbook/`:** tạo thư mục, xác định chủ sở hữu (job cron chạy bằng user nào thì user đó ghi được), ước dung lượng mỗi ngày (đo cỡ các file `.jsonl.gz` đang có rồi ghi số), và đưa vào mục sao lưu.
   - **Mục mới "Chuyển từ máy Windows sang VPS":**
     1. dừng lịch trên Windows **trước** (tắt các task `trading-*`);
     2. `docker compose stop engine collector` trên Windows;
     3. sao lưu DB;
     4. chép sang VPS;
     5. khôi phục;
     6. kiểm số dòng các bảng chính;
     7. kiểm SSI từ VPS;
     8. khởi động VPS;
     9. kiểm cổng go-live;
     10. chỉ khi mọi bước trên đạt mới xoá hoặc tắt hẳn stack Windows.

     Làm vào **ngày không có phiên** (tối thứ Sáu hoặc cuối tuần), vì có một khoảng mất dữ liệu nếu làm trong phiên.
   - **Sao lưu / khôi phục TimescaleDB:** đây là chỗ dễ sai. Lấy theo **tài liệu chính thức của TimescaleDB**, ghi URL: `pg_dump` toàn DB dạng custom, và khi khôi phục thì gọi `timescaledb_pre_restore()` / `timescaledb_post_restore()` nếu tài liệu yêu cầu. Ghi rõ bẫy đã gặp: `pg_dump -t <hypertable>` ra file rỗng. Hướng dẫn phải có bước **đếm số dòng trước và sau** cho `bars`, `bars_daily`, `orders`, `positions`, `engine_state`, `real_order_fills`.
   - **Kiểm SSI từ VPS trước khi cắt chuyển:** chọn một script chỉ đọc **có sẵn** trong `scripts/` (ví dụ spike xác thực/OHLC). Ghi đúng tên file và lệnh chạy.
   - **Mọi lệnh phải chạy được nguyên văn.** Không để placeholder mơ hồ. Chỗ bắt buộc do người dùng điền (tên miền, IP) thì đánh dấu `<ĐIỀN: ...>` và liệt kê hết ở đầu file.

3. **Thử trên Ubuntu thật, trong container tạm.** Thử các lệnh phía host của hướng dẫn trong `ubuntu:24.04`, dùng một bản sao repo sạch:
   ```
   git clone <repo cục bộ> <thư mục tạm ngoài repo>
   docker run --rm --name dot110-ubuntu-test -v <thư mục tạm>:/opt/trading -w /opt/trading ubuntu:24.04 bash -lc "<các lệnh cài công cụ host + uv sync --frozen + uv run python -c 'import trading' + bash -n scripts/*.sh + scripts/sched.sh (không tham số, phải in dòng 'dung:' và exit 2)>"
   ```
   → **Kiểm chứng bằng:** dán output nguyên văn. Lệnh nào hỏng thì sửa **hướng dẫn** rồi chạy lại. Nếu hỏng vì script thì báo lại, không sửa script.

4. **Build từ bản sao sạch.** Chạy `docker compose -p dot110test build engine` trong thư mục tạm, để kiểm `Dockerfile` không phụ thuộc file chỉ có trên máy dev (`.env`, file bị ignore). `-p dot110test` là bắt buộc, để **không** đè image của stack thật. Xong thì xoá image tạm và dán lệnh xoá.
   → **Kiểm chứng bằng:** output build, và `docker compose config -q` (exit 0).

5. **Test chống lệch `tests/test_deployment_doc.py`** (TDD, viết test đỏ trên `DEPLOYMENT.md` cũ trước):
   - Tập job lấy từ các nhãn `case` trong `sched.sh` phải **bằng** tập job xuất hiện trong khối crontab của `DEPLOYMENT.md`.
   - `DEPLOYMENT.md` phải có chuỗi `Asia/Ho_Chi_Minh`.
   - Mọi đường dẫn `scripts/...` nhắc trong `DEPLOYMENT.md` phải tồn tại trong repo.

   → **Kiểm chứng bằng:** test đỏ trên file cũ (dán output), xanh trên file mới.
   Phá thử: xoá một dòng cron trong bản sao `DEPLOYMENT.md` → test đỏ. Khôi phục từ bản sao lưu ngoài repo. **Cấm `git checkout`, `git restore`, `git stash`.**

6. **Kiểm tra toàn cục:**
   - `uv run pytest -m "not integration" -q` (mốc 1131 + số test mới)
   - `uv run ruff check trading tests`
   - `npx gitnexus detect-changes --scope all --repo AI_auto_trading_system`

## 4. Báo cáo cho Claude

Báo cáo gồm các phần sau, theo thứ tự:
1. Kết luận ngắn.
2. 4 bảng kiểm kê.
3. Danh sách thay đổi của `DEPLOYMENT.md` theo từng mục, kèm lý do.
4. Output bước 3 và bước 4.
5. Test đỏ rồi xanh, và phép phá thử.
6. Những gì **chưa xác minh được**. Bắt buộc có mục SSI với IP VPS.
7. Lỗi thấy trong script mà không sửa.

Kết thúc bằng câu: "Tôi không commit, không push, không đụng stack đang chạy hay Task Scheduler, không ghi DB thật; container/image thử đã xoá."
