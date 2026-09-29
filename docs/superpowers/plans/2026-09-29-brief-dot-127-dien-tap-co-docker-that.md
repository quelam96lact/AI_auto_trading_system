# Brief đợt 127 — diễn tập VPS **có Docker thật** (Docker-in-Docker), và test tự động cho cổng `run_if_docker_up.sh`

**Base commit:** `ecadbd4`.
**Người thực thi:** agent. **Người audit + commit + push:** Claude.

---

## §0. Bối cảnh

Đợt 125 diễn tập `DEPLOYMENT.md` trong `ubuntu:24.04` sạch nhưng **không có Docker**. Đợt 126 gỡ sáu lỗi chặn đường. Nhưng mọi thứ **chạm Docker** vẫn chưa từng chạy với tên thật của VPS (`/opt/trading` → project `trading`):

| Chưa kiểm thật | Mới chỉ kiểm bằng |
|---|---|
| Stack dựng lên với tên `trading-*` | suy luận |
| Cổng `run_if_docker_up.sh` tìm thấy `trading-postgres-1` | test giả lập |
| `stream-health` đọc log `trading-collector-1` | test giả lập `subprocess` |
| `logs/` do root tạo được chown `10001:10001`, và **container ghi được vào đó** | `stat` trong container không có Docker |
| §10: lưu `:previous` → build → kiểm hash → **rollback** | Claude trích khối lệnh, thay lệnh ghi bằng `echo` |
| §11: dump → xoá DB → khôi phục TimescaleDB → đối soát số dòng | **chưa bao giờ** |

Ngày chuyển máy, máy Windows tắt sau Bước 10. Mọi lỗi ở §11 lộ ra lúc đó là **không còn đường lui**. Đợt này chạy tất cả những bước trên, thật, trong một Docker daemon **riêng**, cách ly khỏi stack đang chạy.

Hai phần. **Phần A làm trước** (nhỏ, không cần chờ giờ). **Phần B chỉ bắt đầu sau 15:00** (xem §B.0).

---

## Phần A — test tự động cho cổng `run_if_docker_up.sh`

**Hiện trạng.** Đợt 126 thêm ba nhánh vào `scripts/run_if_docker_up.sh` (thiếu `.env` → thoát 2; `.env` có CRLF → thoát 2; tạo `logs/` thì chown khi là root). Cả ba chỉ được kiểm tay trong container diễn tập, **không có test**. Audit 126 ghi lại lỗ này.

**Khuôn có sẵn, dùng đúng nó:** `tests/test_log_rotate.py:16–19` chọn bash. Trên Windows, `bash` trong PATH có thể là **WSL relay**, nên gọi thẳng git-bash; trên CI Ubuntu thì dùng `bash`. Chép hai dòng đó (kèm chú thích) sang file test mới. **Không** chuyển vào `conftest.py`: đó là refactor ngoài phạm vi.

**Cách dựng:** script suy `REPO` từ **vị trí của chính nó** (dòng 31). Test chép `scripts/run_if_docker_up.sh` và `scripts/log_rotate.sh` vào `tmp_path/"trading"/"scripts"/`, rồi gọi bản chép. **Không** chạy bản trong repo thật, vì nó sẽ ghi vào `logs/` thật và nạp `.env` thật.

File mới: `tests/test_run_if_docker_up.py`. Lệnh được bọc luôn là một lệnh **ghi file đánh dấu**, để biết nó có chạy hay không.

| Test | Dựng | Phải thấy |
|---|---|---|
| A1 thiếu `.env` | không có `.env` | thoát **2**; stderr **và** file log có `SKIP: khong tim thay .env`; file đánh dấu **không** tồn tại |
| A2 `.env` CRLF | `.env` ghi bằng `b"FOO=bar\r\n"` | thoát **2**; stderr có `CRLF`; file đánh dấu không tồn tại |
| A3 đường thông | `.env` LF; một file `docker` giả **đứng đầu PATH**, in ra một id bất kỳ (cổng qua); `DOCKER_GATE_CONTAINER=x` | thoát 0; file đánh dấu **có**; log có `EXIT=0` |
| A4 `logs/` vắng, **không** root | xoá `logs/`; một file `chown` giả đứng đầu PATH, ghi file đánh dấu riêng nếu bị gọi | `logs/` được tạo; `chown` **không** bị gọi |

**Stub phải chứng minh nó được gọi.** File `docker` giả ở A3 cũng ghi file đánh dấu riêng, và test assert file đó có. Trên Windows, git-bash chuyển PATH kiểu Windows sang kiểu POSIX lúc khởi động, rất dễ sai. Nếu stub không được gọi, script rơi vào `docker` **thật** của máy (chỉ `docker ps`, vô hại) và test phải **đỏ vì lý do đúng**, chứ không được xanh nhờ may.

**Không test được bằng pytest:** nhánh root (`EUID` là biến chỉ-đọc của bash, không giả được). Phần B kiểm nó thật.

**Cổng:**
- 4 test xanh trên máy này (git-bash). CI (Ubuntu) xanh thì Claude kiểm sau push.
- Phá thử, dán **nguyên văn** thông điệp đỏ:
  - P1: đổi `exit 2` của nhánh thiếu `.env` thành `exit 0` → A1 đỏ.
  - P2: xoá khối kiểm CRLF → A2 đỏ.
  - P3: bỏ điều kiện root (chown vô điều kiện) → A4 đỏ.
  - Phục hồi xong, `git diff --stat scripts/run_if_docker_up.sh` phải **rỗng**.

---

## Phần B — diễn tập có Docker thật

### §B.0. Giờ giấc và tài nguyên

- **Chỉ bắt đầu sau 15:00.** Collector và bộ ghi sổ lệnh đang chạy **phiên thật** trên máy này. Build nhiều image và kéo TimescaleDB trong giờ phiên có thể làm nghẽn chúng.
- **Phải xong và dọn sạch trước 20:00.** 20:30 có job nạp `backfill`, 21:00 có `daily-check`. 19:45 chưa xong thì **dừng**, dọn (§B.9), và báo phần đã làm.
- Giới hạn container diễn tập: `--cpus 3 --memory 6g`.

### §B.1. Cách ly — điều quan trọng nhất của đợt này

Stack thật (`ai_auto_trading_system-*`) chạy trên **cùng máy**. Một lệnh `docker compose down -v` gõ nhầm chỗ là **mất toàn bộ DB**.

- Dựng **một** container `ubuntu:24.04` tên `rehearsal127`, `--privileged`, chạy `dockerd` **riêng bên trong**:
  ```
  docker run -d --privileged --name rehearsal127 --hostname rehearsal127 --cpus 3 --memory 6g \
    -v rehearsal127-docker:/var/lib/docker \
    -v <repo>:/src:ro \
    -v <thư mục scratch chứa script diễn tập>:/work:ro \
    ubuntu:24.04 sleep infinity
  ```
  Volume `/var/lib/docker` giúp `overlay2` chạy được; không có nó `dockerd` rơi về `vfs`, chậm và rất tốn đĩa.
- **CẤM mount `/var/run/docker.sock`** hay bất kỳ cách nào cho `rehearsal127` nói chuyện với Docker của máy chủ.
- **Mọi** lệnh `docker`/`docker compose` của Phần B chạy **bên trong** qua `docker exec rehearsal127 bash /work/<file>.sh`. Script viết thành file LF trong scratch, **không** qua đường ống PowerShell (bài học 126: đường ống thêm CRLF).
- Trên **máy chủ**, chỉ được: `docker run`/`exec`/`rm`/`inspect`/`ps` và `docker volume rm` cho **đúng** `rehearsal127` và volume của nó. **Cấm mọi `docker compose` trên máy chủ.**
- **Trước khi bắt đầu và sau khi dọn**, ghi `StartedAt` của 6 container thật: `docker inspect -f '{{.Name}} {{.State.StartedAt}}' $(docker ps -q)`. Hai lần phải **giống hệt**.
- Trong mọi script diễn tập, dòng đầu tiên là `[ -f /.dockerenv ] && [ "$(hostname)" = rehearsal127 ] || { echo "KHONG PHAI rehearsal127" >&2; exit 99; }`. Sau khi đã clone (§B.2), dòng thứ hai là `cd /opt/trading || exit 99`. Đây là chốt để một script lỡ chạy trên máy chủ thì chết ngay.

### §B.2. Dựng máy VPS giả

Theo `DEPLOYMENT.md` §1–§2, **ghi rõ mọi chỗ phải lệch và vì sao**:
- **Dòng cài gói §1: chạy nguyên văn.** Chỗ lệch dự kiến: không có systemd, nên chạy `dockerd > /var/log/dockerd.log 2>&1 &` bằng tay. `timedatectl` không chạy trong container, nên đặt múi giờ bằng `ln -sf /usr/share/zoneinfo/Asia/Ho_Chi_Minh /etc/localtime`.
- **Mã nguồn:** `git config --global --add safe.directory /src` rồi `git clone /src /opt/trading`. **Không** dùng `git archive` (bài học 125: trên Windows nó áp CRLF). Clone lấy **HEAD đã commit**, không lấy Phần A đang sửa dở; như vậy là đúng.
- **`.env` GIẢ:** chép `.env.example`. Mọi khoá `SSI_*`, `BINGX_*` để **rỗng**. `TELEGRAM_BOT_TOKEN=dummy`, `TELEGRAM_CHAT_ID=0` (gửi sẽ hỏng; đó là điều cần thấy ở §B.4). `POSTGRES_PASSWORD=rehearsal`. `DB_DSN` trỏ `127.0.0.1:5432` với mật khẩu đó. **Không** đọc, không chép `.env` thật.
- **`.env` CRLF:** tạo bản CRLF của `.env` giả, chạy **nguyên văn** §11 Bước 5 (0) (`chmod 600`, `sed`), rồi `grep -c $'\r' .env` phải ra `0`.
- `uv sync --python 3.12` như §2.

### §B.3. Collector KHÔNG được chạy thật

Collector chạy thật nghĩa là kết nối SSI. Với khoá rỗng, nó sẽ đăng nhập hỏng liên tục từ IP của chủ dự án. **Cấm.**

- Tạo `docker-compose.override.yml` trong `/opt/trading` **của diễn tập**, với `collector:` → `command: ["sleep", "infinity"]`. Engine chạy thật: nó không import `ssi_sdk` (Claude đã grep `trading/engine/`), chỉ nói chuyện với NATS/DB trong daemon diễn tập, và `real_trading_enabled: false` ở `config/config.yaml:16`.
- **BẪY:** §11 Bước 5 (a) **ghi đè** `docker-compose.override.yml` bằng `cat >`. Sau bước (a), **thêm lại ngay** khối collector vào file đó, trước **bất kỳ** lệnh nào khởi động collector. Ghi việc này vào báo cáo như một phát hiện về tài liệu: trên VPS thật thì không sao, nhưng file override là thứ dùng chung.
- **Sau MỌI lệnh `up`**: `docker inspect -f '{{.Config.Cmd}}' trading-collector-1` phải là `[sleep infinity]`. Khác thì `docker compose stop collector` **ngay**, và báo.
- **Cấm** chạy: `sched.sh backfill`, `sched.sh orderbook-recorder`, `probe_dead_man_switch.py`, §11 Bước 7 (kiểm SSI), Bước 8b (Telegram).

### §B.4. Stack, cổng, log

Mỗi mục: dán **nguyên văn đầu ra**. Không tóm tắt. Đợt 126 báo "hash khớp 100%" cho một khối lệnh mà nếu chạy đúng như tài liệu thì phải hỏng.

1. **Nhánh "lần đầu" của §10:** trên daemon **mới tinh**, trước khi build gì, chạy **phần vòng `for` lưu `:previous`** của khối §10 bước 1, trích **từ file** `DEPLOYMENT.md`, không gõ lại. Phải in "Chưa có ảnh ... (lần đầu triển khai)" cho cả hai service, và `SAVE_OK` vẫn là 1.
2. **§5:** `docker compose up -d --build`. `docker compose ps` phải cho `trading-postgres-1`, `trading-nats-1`, `trading-engine-1`, `trading-collector-1`, `trading-grafana-1`.
3. **`logs/` do root tạo:** `rm -rf logs`, rồi `scripts/run_if_docker_up.sh t.log t echo hi` với **cổng mặc định** (không đặt `DOCKER_GATE_CONTAINER`):
   - log có `EXIT=0`, tức cổng tìm thấy `trading-postgres-1`;
   - `stat -c '%u:%g' logs` ra `10001:10001`;
   - Chứng minh **engine ghi được vào `logs/`**. Đây mới là điều việc 4 đợt 126 muốn bảo đảm, không phải chính lệnh `stat`. Engine gọi `attach_durable_alert_handler(filename="engine_alerts.log")` (`trading/engine/main.py:730`). `RotatingFileHandler` mở file **ngay khi khởi động**, và mọi lỗi quyền bị **nuốt im lặng** (`trading/logging_setup.py:76`, `except Exception: pass`). Vậy:
     - **Đối chứng âm tính trước:** `rm -rf logs && mkdir logs` (root:root), `docker compose restart engine`. `logs/engine_alerts.log` phải **KHÔNG** có. Nếu có, phép kiểm không phân biệt được gì; dừng mục này và báo.
     - **Rồi dương tính:** `rm -rf logs`, chạy lại lệnh `run_if_docker_up.sh` ở trên (nó tạo `logs/` và chown), `docker compose restart engine`. `ls -ln logs/engine_alerts.log` phải có, uid **10001**.
4. **Job cron (chạy bằng tay, không cần cron daemon):** `scripts/sched.sh stream-health`, `sched.sh deploy-drift`, `sched.sh heartbeat`. Dán dòng cuối log của từng job. `stream-health` phải đọc được log của `trading-collector-1` (log rỗng cũng được, miễn **không** có "No such container").
5. **Nhánh Docker-chết:** `docker compose stop postgres`, rồi chạy lại lệnh ở mục 3. Log phải có `SKIP: docker chua chay` và một dòng `ALERT_EXIT=`. Báo giá trị thấy được, và giải thích nó theo `should_alert` (khung giờ, ngày nghỉ, chống spam). Sau 15:00 nhiều khả năng là 0 vì ngoài giờ; nếu vậy, gọi thẳng `run_alert()` với `now` giả trong giờ phiên và `send` thật (token dummy) để thấy **2**. Xong thì `docker compose start postgres`.
6. **Crontab:** ghi khối cron §9 (có `CRON_TZ`) vào file, `crontab <file>`, `crontab -l`. Đầu ra phải khớp đủ 9 dòng job.

### §B.5. §10 — triển khai, kiểm, rollback, THẬT

Trích **ba khối bash** của §10 từ `DEPLOYMENT.md` bằng script, giống cách Claude làm ở audit 126: regex ```` ```bash ... ``` ```` có chứa `PROJECT_NAME=`. Lần này **không** thay lệnh ghi bằng `echo`: daemon diễn tập là của riêng ta.

1. Ghi lại `ID_CU = docker image inspect trading-engine:latest --format '{{.Id}}'`.
2. Trong **bản clone diễn tập**, không phải repo thật, thêm một dòng chú thích `# REHEARSAL127_MARKER` vào `trading/engine/main.py`.
3. Chạy **khối 1**: phải in "Đã lưu ... :previous" cho hai service, rồi build và up. Rồi `docker image inspect trading-engine:previous --format '{{.Id}}'` phải **bằng `ID_CU`**.
4. Chạy **khối 3** (hai hash phải bằng nhau), cộng lệnh grep chuỗi đặc trưng ở §10 mục 2 với chuỗi `REHEARSAL127_MARKER`: phải tìm thấy.
5. Chạy **khối 2** (rollback). Image của `trading-engine-1` phải **bằng `ID_CU`**, và grep `REHEARSAL127_MARKER` trong container phải **không** thấy.
6. **Âm tính:** chạy khối 1 với dòng `PROJECT_NAME=` bị thay bằng `PROJECT_NAME="trading_"` (thay trong **bản trích**, không sửa tài liệu). Phải in `LỖI` và `DỪNG`, và **không** build: `docker images` không có image mới.

### §B.6. §11 — sao lưu và khôi phục TimescaleDB, THẬT

Đây là bước duy nhất không thể làm lại ngày chuyển máy.

1. **Dữ liệu mẫu:** chèn dòng tổng hợp vào **ít nhất một hypertable** (`bars` hoặc `bars_daily`, xem `trading/storage/schema.sql`) và một bảng thường. Đủ nhiều để qua ranh giới chunk (vài nghìn dòng, trải nhiều tháng). Không dùng dữ liệu thật.
2. **Bước 3 nguyên văn**, phiên bản bash: đếm số dòng mốc, và ghi `extversion`. `pg_dump -Fc -f /tmp/...` **bên trong container**, rồi `docker compose cp` ra ngoài. `pg_restore -l | head` phải đọc được.
3. **Giả lập VPS rỗng:** `docker compose down -v`. Lệnh này **chỉ** được chạy trong script có chốt §B.1, bên trong `rehearsal127`. Dán dòng `hostname` in ra ngay trước nó.
4. **Bước 5 (a)(b)(c) nguyên văn**, điền `extversion` từ bước 2. Chú ý bẫy ở §B.3. Các lệnh kiểm "PHẢI bằng" và "PHẢI là 0" phải đạt.
5. **Bước 6:** số dòng mọi bảng mốc phải **bằng** bước 2. Thêm: `SELECT count(*) FROM timescaledb_information.hypertables` phải bằng trước khi dump.
6. **Bước 8:** `docker compose up -d --build`, kiểm collector vẫn `sleep infinity`, engine chạy và ghi được `logs/`.
7. **Sao lưu đêm:** `scripts/backup_db.sh /tmp/bk`. File `.sql.gz` phải khác rỗng và `gunzip -t` qua.

### §B.7. Được sửa gì khi diễn tập tìm ra lỗi

- **`DEPLOYMENT.md`:** chỉ sửa bước mà diễn tập **chứng minh** là hỏng, kèm đầu ra hỏng **và** đầu ra sau khi sửa, cả hai nguyên văn. Chạy lại `tests/test_deployment_doc.py` trên **working tree đã sửa**; đợt 125 đã vấp đúng chỗ này.
- **Code, script, `docker-compose.yml`, `Dockerfile`: KHÔNG sửa.** Báo lại kèm đầu ra; Claude sẽ brief đợt sau. Ngoại lệ: không có.
- Một bước hỏng mà các bước sau vẫn chạy được thì **đi tiếp**. Diễn tập tìm được càng nhiều lỗi trong một lượt càng tốt.

### §B.8. Không kiểm được thì nói rõ

Dự kiến không kiểm được: systemd, `ufw`, TLS/nginx (§3–§4), cron daemon chạy đúng giờ, gửi Telegram thật, SSI, và hiệu năng trên VPS thật. Còn gì khác thì liệt kê.

### §B.9. Dọn dẹp

```
docker rm -f rehearsal127
docker volume rm rehearsal127-docker
docker ps -a --filter name=rehearsal127        → rỗng
docker volume ls --filter name=rehearsal127    → rỗng
```

Rồi so `StartedAt` của 6 container thật với lần ghi ở đầu (§B.1): phải giống hệt.

---

## §C. Tiêu chí chung

```
uv run pytest -q   (TOÀN BỘ, gồm integration; nats-test đang chạy)   → ≥ 1.420 passed + 4 test mới, 0 failed
uv run ruff check trading tests scripts                              → sạch
uv run pytest tests/test_deployment_doc.py                            → xanh (nếu có sửa DEPLOYMENT.md)
git diff --stat                                                       → chỉ tests/test_run_if_docker_up.py (mới),
                                                                        DEPLOYMENT.md (nếu có), báo cáo
```

GitNexus (CLI, `--repo AI_auto_trading_system`, vì MCP đang hỏng): `npx gitnexus query "run_if_docker_up"` trước khi viết Phần A; `npx gitnexus detect-changes` ở cuối.

## §D. Phạm vi

**Được tạo/sửa:** `tests/test_run_if_docker_up.py` (mới); `DEPLOYMENT.md` (chỉ theo §B.7); báo cáo `docs/superpowers/research/2026-09-29-dot-127-dien-tap-co-docker-that.md`; script diễn tập trong thư mục scratch (**không** đặt trong repo).

**KHÔNG được đụng:** `trading/`, `scripts/`, `tests/` có sẵn, `docker-compose.yml`, `Dockerfile`, `config/`, `.github/`; `.env` thật; stack thật và 6 container của nó.

## §E. Điều cấm

- **Không commit, không push.** Không rebuild, không restart stack **thật**.
- **Không `docker compose` nào trên máy chủ.** Không mount Docker socket vào diễn tập.
- **Không đọc, không chép `.env` thật.** Không `scripts/.ssi_sdk_token.json`.
- Không kết nối SSI, không gửi Telegram thật, không chạy `probe_dead_man_switch.py`.
- Không đặt, sửa, huỷ lệnh; không bật `real_trading_enabled`; không `--send`.
- Cấm `git checkout`, `git restore`, `git stash` trên repo thật. Mọi sửa đổi thử (marker, phá thử) trong bản clone diễn tập, hoặc phục hồi bằng tay và kiểm bằng `git diff --stat`.
- Không tạo, sửa, xoá scheduled task của Windows.

## §F. Báo cáo phải có

1. Phần A: file test, 4 test xanh, bảng phá thử P1–P3 với thông điệp đỏ **nguyên văn**, `git diff --stat` sau phục hồi.
2. Phần B, **mỗi mục của §B.4–§B.6**: lệnh đã chạy và đầu ra **nguyên văn**. Chỗ nào ghi "đạt" mà không có đầu ra thì Claude coi là **chưa làm**.
3. Bảng các bước lệch khỏi tài liệu (systemd, `timedatectl`, ...) và lý do.
4. Mọi lỗi tài liệu tìm ra, và cách đã sửa theo §B.7, hoặc lý do chưa sửa.
5. `StartedAt` trước và sau của 6 container thật; đầu ra dọn dẹp §B.9.
6. §B.8: những gì không kiểm được.
7. Chỗ nào brief sai hoặc mơ hồ. **Nếu brief đảo một quyết định có chủ ý nào** (đọc chú thích quanh dòng định sửa), **báo ngay**.
