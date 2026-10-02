# Deployment Guide — Ubuntu VPS

This covers deploying the collector/engine/postgres/nats/grafana stack to a
production Ubuntu server via Docker Compose. See `GO_LIVE_AUDIT.md` for what is
still blocking go-live — read it before enabling real trading.

> [!IMPORTANT]
> **Danh sách các placeholder cần điền trước khi thực hiện các lệnh trong tài liệu:**
> - `<ĐIỀN: repo-url>`: URL git clone của repository (ví dụ: `https://github.com/quelam96lact/AI_auto_trading_system.git`).
> - `<ĐIỀN: YOUR_DOMAIN>`: Tên miền trỏ về IP của VPS để dùng cho Grafana TLS (ví dụ: `grafana.example.com`).
> - `<ĐIỀN: VPS_IP>`: Địa chỉ IP public của VPS Ubuntu.
> - `<ĐIỀN: USER>`: Tên tài khoản người dùng có quyền sudo trên VPS Ubuntu (ví dụ: `ubuntu`).

## 1. Server prerequisites

```bash
# 1. Cấu hình múi giờ Việt Nam (BẮT BUỘC để cron và log khớp đúng giờ phiên giao dịch VN)
sudo timedatectl set-timezone Asia/Ho_Chi_Minh
timedatectl   # Xác nhận: Time zone: Asia/Ho_Chi_Minh (+07, +0700)

# 2. Cài đặt Docker, Compose plugin, UFW và các tiện ích cần thiết
# (Áp dụng cho Ubuntu 24.04 LTS: gói docker-compose-v2 cung cấp lệnh 'docker compose' từ kho
# apt chuẩn của Ubuntu. Nếu cài từ kho chính thức download.docker.com thì dùng docker-compose-plugin.
# Cài thêm logrotate cho mục §8).
sudo apt update && sudo apt install -y docker.io docker-compose-v2 ufw curl git ca-certificates logrotate
sudo systemctl enable --now docker

# 3. Cài đặt uv trên host (công cụ quản lý môi trường Python cho các cron job trên host)
# Nguồn chính thức Astral: https://docs.astral.sh/uv/getting-started/installation/
# Cài đặt vào /usr/local/bin để cả user và crontab đều thực thi được:
curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR="/usr/local/bin" sh
uv --version
```

## 2. Get the code + secrets onto the server

```bash
git clone <ĐIỀN: repo-url> /opt/trading
cd /opt/trading
cp .env.example .env
# edit .env with real SSI credentials + Telegram token (see README.md for
# which variables config.py requires). Never commit this file.
chmod 600 .env

# Đồng bộ môi trường Python trên host bằng uv (chạy các cron job ngoài container)
uv sync --frozen --python 3.12
# --python 3.12: KHOP voi image (Dockerfile: FROM python:3.12-slim). Khong ghim thi uv tu
# lay ban Python moi nhat (thu 27/09 ra 3.14) -> job cron tren host chay khac Python voi container.
uv run python -c "import sys, trading; print('trading module OK', sys.version)"

# Tạo thư mục logs trên host và phân quyền cho appuser (uid 10001 trong Dockerfile)
# BẮT BUỘC: docker-compose.yml gắn mount ./logs:/app/logs cho collector và engine.
# Collector ghi logs/bars_closed.log, engine ghi logs/engine_alerts.log. Nếu không
# tạo trước, Docker daemon sẽ tự tạo thư mục thuộc root:root, tiến trình (chạy uid 10001)
# sẽ bị PermissionError khi ghi log, nuốt lỗi và chạy tiếp im lặng
# làm mất toàn bộ bằng chứng chốt nến luồng và cảnh báo engine!
mkdir -p logs && sudo chown 10001:10001 logs

# Tạo thư mục data/orderbook/ cho máy ghi sổ lệnh thời gian thực (orderbook-recorder)
# Thư mục này được ghi trực tiếp bởi cron job trên host (chạy dưới quyền user hiện tại).
# Phân quyền 775 để user hiện tại và cron đều ghi được:
mkdir -p data/orderbook && chmod 775 data/orderbook

# Phân quyền thực thi cho các script vận hành và cron job trên host
# (BẮT BUỘC: git checkout/archive không đảm bảo cờ executable cho scripts/*.sh;
# thiếu lệnh này thì các script sched.sh, run_if_docker_up.sh sẽ báo Permission denied ở cron).
chmod +x scripts/*.sh
```

**Ước tính dung lượng sổ lệnh (`data/orderbook/`):**
Dữ liệu sổ lệnh phái sinh VN30F được lưu theo từng hợp đồng dưới dạng các file `.jsonl.gz` nén gzip (ví dụ `data/orderbook/VN30F2610/2026-09-25.jsonl.gz`).
- Đo lường thực tế (ngày 25/09/2026): **~10.3 MB/ngày** (giao dịch trọn phiên).
- Dung lượng ước tính: **~220 MB/tháng** (~22 ngày giao dịch), **~2.5 GB/năm**.
- Khuyến nghị: VPS nên có ít nhất **10–20 GB** dung lượng đĩa trống dự phòng cho thư mục này trong năm đầu tiên và đưa `data/orderbook/` vào lịch sao lưu định kỳ (§6).

Review `config/config.yaml` — in particular keep `real_trading_enabled: false`
until the real-order verification runbook (`docs/plans-legacy/PLAN_REAL_ORDER_PLACEMENT.md`) has
been run end-to-end.

## 3. Firewall — only expose what must be public

`docker-compose.yml` binds Postgres (5432), NATS (4222) **and Grafana (3000)**
to `127.0.0.1` only, so none of them is reachable from outside the host even
without a firewall. To reach Grafana remotely, either tunnel over SSH
(`ssh -L 3000:127.0.0.1:3000 user@server`) or put it behind nginx + TLS (§4).

```bash
sudo ufw default deny incoming
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## 4. TLS for Grafana

This repo does not ship an nginx config, because it depends on a domain name
this project doesn't have yet. Once you have a domain pointed at the server:

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

Minimal reverse-proxy config (`/etc/nginx/sites-available/trading-grafana`):

```nginx
server {
    listen 80;
    server_name <ĐIỀN: YOUR_DOMAIN>;
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/trading-grafana /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d <ĐIỀN: YOUR_DOMAIN>
```

Also change Grafana's default admin password before exposing it: set
`GRAFANA_ADMIN_PASSWORD` in the environment file (compose reads it; the
fallback is still `admin`, which is only acceptable because port 3000 is bound
to localhost).

`POSTGRES_PASSWORD` works the same way, with one trap: Postgres only applies it
when the `pgdata` volume is initialised the **first** time. On an existing
database you must run `ALTER USER trading WITH PASSWORD '...'` inside the
container first, then set the same value in the environment file.

## 5. Start the stack

```bash
docker compose up -d --build
docker compose ps        # all services should be healthy/running
docker compose logs -f collector
```

Docker's `restart: unless-stopped` (already set on every service) handles
restart-on-boot and restart-on-crash — no separate systemd units are needed
for the services themselves.

## 6. Backups

### Sao lưu cơ sở dữ liệu hàng ngày

> [!WARNING]
> **`pg_restore -l` không chứng minh phục hồi được (đợt 136, đo 30/09).** Nó chỉ đọc **mục lục ở đầu file**,
> không đọc dữ liệu. Cắt một bản dump thật (104.656.147 byte) còn 90% rồi đo:
>
> | Phép | Kết quả trên bản đã mất 10% dữ liệu |
> |---|---|
> | `pg_restore -l` | **exit 0**, đúng 3.224 dòng mục lục — y như bản nguyên |
> | ngưỡng kích thước 80 MB | 89,8 MB → **qua** |
> | `evaluate_backup_health(...)` | **`[]`** — không một cảnh báo nào |
> | `pg_restore` phục hồi thật | **exit 1**, `could not read from input file: end of file` |
>
> Bản phục hồi dở dang còn *trông gần đủ* (`bars` 99,99%) trong khi `orders` = 0. Vì vậy có job
> `restore-drill` (§9, Chủ nhật 04:00): phục hồi thật vào database nháp rồi đối chiếu **từng bảng** với
> **bản kê số dòng `.counts` chụp lúc dump** (không phải với database đang sống — xem mô tả `backup_db.sh` dưới đây).

`scripts/backup_db.sh` xuất dữ liệu TimescaleDB dạng custom archive (`-Fc`) bên trong container `postgres`, sao chép ra host bằng `docker compose cp`, kiểm tra tính toàn vẹn bằng `pg_restore -l`, và dọn dẹp các bản sao lưu cũ hơn 14 ngày (ghi đè bằng `BACKUP_RETENTION_DAYS`, phủ cả đuôi `.dump`, `.sql.gz` và `.counts`). Ngay **trước** `pg_dump` nó ghi thêm **bản kê số dòng** `trading_<ts>.counts` cạnh file `.dump` (mỗi dòng `ten_bang<TAB>so_dong`, mọi bảng `public` liệt kê từ catalog); bản kê chỉ được giữ khi dump đã qua xác minh — dump hỏng thì bản kê bị xoá. Ngược lại, **lập bản kê lỗi không được giết bản sao lưu** (đợt 138): script chỉ in `WARNING` ra stderr, không tạo `.counts`, rồi vẫn `pg_dump` và thoát 0; người báo là `backup-check` (dump `.dump` mới nhất thiếu hoặc có `.counts` rỗng → CRITICAL) và diễn tập Chủ nhật. `restore-drill` đối chiếu bản phục hồi với bản kê này (`phục_hồi >= bản_kê`, không dung sai). Được lên lịch qua `scripts/sched.sh` trên host để được cổng Docker và xoay log tự động (xem §9):

```bash
chmod +x scripts/backup_db.sh
# KHONG cai dong cron o day — no da nam trong khoi cron §9 (job 11 va 12).
# Cai ca hai noi = backup chay HAI LAN moi dem (dung loi trung dong cron ma
# dot 125 da phai sua o §9.5).
#
# Tham khao (da co trong khoi cron §9):
# `cd /opt/trading` la BAT BUOC: script goi `docker compose exec`, ma lenh do tim
# docker-compose.yml o THU MUC HIEN TAI. Cron chay voi cwd = home cua user
# (thuong /root) nen thieu `cd` se bao "no configuration file provided".
# 0 2 * * * cd /opt/trading && scripts/sched.sh backup
```

#### `TRADING_BACKUP_DIR` — nơi để bản sao lưu

Bốn job sao lưu (`backup`, `backup-check`, `orderbook-backup`, `disk-check`) tìm thư mục
sao lưu theo thứ tự: **tham số dòng lệnh** → **`TRADING_BACKUP_DIR` trong `.env`** →
mặc định `/var/backups/trading-db`.

- **VPS Ubuntu:** để trống, mặc định đã đúng.
- **Windows: BẮT BUỘC đặt** `TRADING_BACKUP_DIR` (hoặc truyền tham số cho mọi task).
  Đường dẫn Ubuntu vừa không tồn tại, vừa bị Git Bash dịch thành
  `C:\Program Files\Git\var\backups\trading-db`.

Đo thật 29/09 khi chưa có biến này, gọi đúng như lịch sẽ gọi:

| Job | Hậu quả |
|---|---|
| `backup-check` | gửi **CẢNH BÁO GIẢ** mỗi ngày: *"Thư mục sao lưu không tồn tại"* |
| `disk-check` | thoát 2 và **không bao giờ kiểm đĩa** — đúng việc nó được lập lịch để làm |
| `orderbook-backup` | chết: `mkdir: cannot create directory '/var': Permission denied` |

`run_if_docker_up.sh` nạp `.env` **trước** khi chạy job, nên job thấy biến này;
`sched.sh` thì **không** (nó chạy trước bước nạp), nên đừng suy mặc định ở đó.

### Sao lưu thư mục sổ lệnh `data/orderbook/`

Thư mục `data/orderbook/` chứa toàn bộ dữ liệu khớp lệnh và sổ lệnh phái sinh thời gian thực ghi được mỗi ngày. Cần tạo thư mục `/var/backups/trading-db` và sao lưu định kỳ:

```bash
# Tạo thư mục chứa backup trên host:
sudo mkdir -p /var/backups/trading-db

# KHÔNG cài dòng cron ở đây — job `orderbook-backup` (02:30 hàng ngày) đã nằm trong khối cron §9
# (job 12). Cài ở hai nơi = hai bản lệch nhau (bài học đợt 131).
```

**Vì sao không còn `tar -czf ... data/orderbook` mỗi đêm (đợt 132):** lệnh cũ nén lại
**toàn bộ** thư mục mỗi đêm mà không có gì xoá file cũ, nên bản ngày N chứa lại ngày 1..N —
tổng dung lượng tăng theo **bình phương** số phiên (~217 GB sau một năm cho ~2,9 GB dữ liệu).
`scripts/backup_orderbook.sh` chỉ đóng gói các file **chưa từng được sao lưu** (mới hơn bản
`orderbook_*.tar.gz` mới nhất) nên tổng tăng **tuyến tính**, kèm hạn xoá `BACKUP_RETENTION_DAYS`
(mặc định 14). Ngày nghỉ không có file mới thì không tạo gì và thoát 0. Bản lưu có đường dẫn
`data/orderbook/...`, khôi phục bằng đúng lệnh ở §11 Bước 5 (`tar -xzvf ... -C /opt/trading/`).
Lưu ý: hạn xoá 14 ngày nghĩa là kho sao lưu chỉ giữ ~14 ngày gần nhất; bản gốc là `data/orderbook/`.

### Quy chuẩn sao lưu & khôi phục TimescaleDB (Tài liệu chính thức)

> [!WARNING]
> **Bẫy chết người khi sao lưu TimescaleDB (`pg_dump -t`):**
> Trong TimescaleDB, dữ liệu của các hypertable (như bảng `bars`, `bars_daily`) không nằm trực tiếp trong bảng gốc mà được phân chia thành các chunk table nằm trong schema nội bộ `_timescaledb_internal`. Nếu chạy `pg_dump -t bars`, pg_dump chỉ xuất schema catalog của bảng mẹ mà **KHÔNG DUMP DỮ LIỆU CÁC CHUNK**, dẫn tới khi restore bảng sẽ hoàn toàn rỗng (0 dòng) mà không hề có thông báo lỗi!
> 
> BẮT BUỘC sao lưu toàn bộ cơ sở dữ liệu ở định dạng custom archive (`-Fc`). Lưu ý KHÔNG dùng toán tử pipe `>` trên host Windows/PowerShell vì sẽ làm hỏng dữ liệu nhị phân:
> ```bash
> docker compose exec -T postgres pg_dump -U trading -Fc -f /tmp/trading_manual.dump trading
> docker compose cp postgres:/tmp/trading_manual.dump /var/backups/trading-db/trading_manual.dump
> docker compose exec -T postgres rm -f /tmp/trading_manual.dump
> ```
> Nguồn tài liệu chính thức: https://docs.timescale.com/use-timescale/latest/backup-restore/pg-dump-and-restore/
> 
> **Cảnh báo `continuous_agg`:** Khi chạy `pg_dump`, Postgres in cảnh báo `warning: there are circular foreign-key constraints on this table: continuous_agg`. Đây là catalog nội bộ của TimescaleDB, hoàn toàn vô hại với định dạng `-Fc` khi kết hợp cùng `timescaledb_pre_restore()` và `timescaledb_post_restore()` (đã kiểm chứng đối soát khớp 100% dữ liệu ở đợt 131).

**Quy trình khôi phục bản sao lưu đêm TimescaleDB (đã diễn tập đợt 131):**

Khi cần khôi phục dữ liệu từ bản sao lưu đêm (`trading_YYYYMMDD_HHMMSS.dump`) vào DB rỗng:

```bash
# 1. Gọi pre_restore trước khi khôi phục dữ liệu:
docker compose exec -T postgres psql -U trading -d trading -c "SELECT timescaledb_pre_restore();"

# 2. Chép file dump vào container rồi restore với cờ --no-owner:
docker compose cp /var/backups/trading-db/trading_20260929_020000.dump postgres:/tmp/trading_restore.dump
docker compose exec -T postgres pg_restore -U trading -d trading --no-owner /tmp/trading_restore.dump

# 3. Gọi post_restore sau khi khôi phục xong để kích hoạt lại catalog và chỉ mục:
docker compose exec -T postgres psql -U trading -d trading -c "SELECT timescaledb_post_restore();"

# 4. Xoá file dump tạm trong container:
docker compose exec -T postgres rm -f /tmp/trading_restore.dump
```

**Bắt buộc kiểm tra số dòng các bảng chính và checksum sau khi khôi phục:**

Chạy truy vấn đối soát để đảm bảo dữ liệu không bị thất thoát:

```bash
docker compose exec -T postgres psql -U trading -d trading -c "
SELECT 'bars' AS tbl, count(*) FROM bars
UNION ALL SELECT 'bars_daily', count(*) FROM bars_daily
UNION ALL SELECT 'bars_derivative', count(*) FROM bars_derivative
UNION ALL SELECT 'orders', count(*) FROM orders
UNION ALL SELECT 'positions', count(*) FROM positions
UNION ALL SELECT 'symbol_universe', count(*) FROM symbol_universe
UNION ALL SELECT 'account_nav_snapshot', count(*) FROM account_nav_snapshot
UNION ALL SELECT 'bars_crypto', count(*) FROM bars_crypto;
"

# Kiểm tra checksum bảng bars_daily (chuẩn đợt 128):
docker compose exec -T postgres psql -U trading -d trading -Atc \
  "SELECT sum(hashtextextended(symbol||ts::text||open::text||high::text||low::text||close::text||volume::text||source, 0)) FROM bars_daily;"
```
```

## 7. Resource limits

Each service in `docker-compose.yml` has `mem_limit`/`cpus` set (postgres 1g/1
cpu, collector/engine 512m/1 cpu each, grafana 512m/0.5 cpu, nats 256m/0.5
cpu) as a starting point against runaway memory/CPU use. Adjust based on
observed usage (`docker stats`) once running for a few days.

**Postgres memory tuning (dot 129, 2026-09-29):** `timescaledb-tune` probes
the *host* RAM at `initdb` time, not the container limit — on a 16 GB machine
it sets `shared_buffers ≈ 1.9 GB`, far above the 1 g container ceiling. To
override both the on-disk `postgresql.conf` *and* any future `initdb`, the
`postgres` service now passes `-c` flags via `command:`. These flags win over
`postgresql.conf` and `postgresql.auto.conf`. If you change `mem_limit`,
update the `-c` values at the same time: `shared_buffers = 25 %` of the new
limit, `effective_cache_size = 75 %`, `maintenance_work_mem` capped at 128 MB
(enough for index builds on `bars_daily`). `max_parallel_workers_per_gather`
and `max_parallel_maintenance_workers` are set to 0 because the container has
only 1 CPU; parallelism only wastes shared memory there.

### Mô hình dung lượng đĩa (đợt 132)

Không có dòng code nào canh đĩa trước đợt 132; job `disk-check` (§9) giờ báo Telegram khi còn
trống dưới 10 GB **hoặc** dưới 10%. Số đo thật 29/09: `data/orderbook` 25 MB, tốc độ ~10–15 MB/phiên;
`tar -czf` lên file đã là `.gz` chỉ nén còn 0,59.

Tổng dung lượng các file tar theo cách **cũ** (nén cả thư mục mỗi đêm, 12 MB/phiên, hệ số 0,59):

| Số phiên | `data/orderbook` | **Tổng các file tar (cũ)** |
|---|---|---|
| 20 (~1 tháng) | 0,2 GB | **1,5 GB** |
| 60 (~3 tháng) | 0,7 GB | **12,7 GB** |
| 125 (~6 tháng) | 1,5 GB | **54 GB** |
| 250 (~1 năm) | 2,9 GB | **217 GB** |

Với `backup_orderbook.sh` (tăng tuyến tính, giữ 14 ngày) kho sao lưu sổ lệnh chỉ còn ~0,2 GB.

**VPS cần tối thiểu bao nhiêu GB** (trạng thái ổn định sau 1 năm, hạn xoá 14 ngày):

| Khoản | GB |
|---|---|
| Hệ điều hành + Docker | ~10 |
| Docker image (3,2) + build cache (0,8, dọn theo §10) | ~4 |
| Volume DB (1,8 hiện tại, tăng dần) | ~3 |
| `data/orderbook` sau 1 năm | ~3 |
| Sao lưu DB: 100 MB × 14 ngày | ~1,4 |
| Sao lưu sổ lệnh (14 ngày) + log | ~1 |
| **Cộng** | **~22** |
| Chỗ trống tối thiểu để `disk-check` không kêu | +10 |

=> **Tối thiểu ~40 GB; khuyến nghị 60–80 GB** cho năm đầu. Gói 20–25 GB sẽ đầy trong vài tháng.

### Dọn rác Docker an toàn

Mỗi lần triển khai theo §10 sinh image mới; image cũ thành *dangling* và build cache tích dần
(máy dev 29/09: 6 image dangling, 118 mục build cache 827 MB). Đặt ở §7 vì đây là việc tài nguyên
đĩa, chạy tay sau khi §10 đã kiểm xong (không phải một bước của quy trình triển khai):

```bash
docker image prune -f                          # CHỈ image dangling, không đụng tag nào
docker builder prune -f --filter until=168h    # build cache cũ hơn 7 ngày
```

> [!CAUTION]
> **CẤM `docker image prune -a`** (và `docker system prune -a`): nó xoá **mọi** image không có
> container đang dùng — kể cả `:previous`, tức là xoá mất đường lui rollback của §10.
> Đã kiểm 29/09: `ai_auto_trading_system-collector:previous` và `-engine:previous` **không** nằm
> trong danh sách dangling, nên `image prune -f` (không `-a`) giữ nguyên. `docker image prune`
> bản 29.8.0 không có `--dry-run`, nên phép kiểm trước khi chạy là `docker image ls --filter dangling=true`.

## 8. Log rotation

**Lớp chính (đợt 133): khối `logging` nằm TRONG `docker-compose.yml`** (`json-file`, `max-size: 10m`,
`max-file: 3`, qua neo YAML `x-logging`, áp cho cả 6 service). Cấu hình nằm trong repo thì không thể
quên và áp cho cả VPS. Giới hạn chỉ có hiệu lực sau khi container được **tạo lại** (`docker compose up -d`);
`restart` không đủ. Mức thực tế không lớn (~0,25 GB/năm ngoài giờ phiên) — đây là việc dọn cho gọn.

**Lớp phụ: `daemon.json`** cho các container **không** thuộc compose (và làm mặc định của máy).
Docker's default `json-file` log driver is unbounded. Add to
`/etc/docker/daemon.json` (creates it if absent) and restart Docker:

```json
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" }
}
```

```bash
sudo systemctl restart docker
```

Khối trên chỉ xoay log **Docker**. Hai file log trên **host** mà §6 và §9 tự tạo
ra không được xoay — thêm cấu hình logrotate trên host (KHÔNG phải trong
container), xoay theo tuần, giữ vài bản, nén:

```bash
# /etc/logrotate.d/trading  (tạo mới; chạy logrotate mặc định hàng ngày qua cron)
/var/log/trading-backup.log /var/log/trading-heartbeat.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
}
```

Test cấu hình: `sudo logrotate -d /etc/logrotate.d/trading` (dry-run).

### Windows (máy dev) — xoay theo kích thước, ngay trong cổng ghi log

Không có logrotate trên Windows. Các file log của đám scheduled task
(`logs/heartbeat.log`, `daily-data-check.log`, `backfill.log`,
`deploy-drift.log`) được xoay bởi `scripts/log_rotate.sh`, **source từ
`run_if_docker_up.sh`** — cửa ngõ duy nhất ghi log, và cron Ubuntu cũng gọi
job qua chính file này nên không cần bản Ubuntu riêng (4ea4c8d: một công thức
một nơi).

- **Xoay theo kích thước, không theo ngày**: ngày nghỉ không sinh log, xoay
  theo ngày chỉ tạo đống file rỗng. Mặc định xoay khi file vượt **1 MB**
  (`LOG_MAX_BYTES`, đổi được bằng biến môi trường), giữ **5 bản cũ**
  (`LOG_KEEP`) rồi xoá dần. Con số dựa trên đo 02/09: ~14 KB/ngày cao nhất
  (8,6 KB thường + ~85 dòng SKIP khi Docker tắt) ⇒ 1 MB ≈ 2-3 tháng liên tục,
  5 bản ≈ hơn 1 năm hồi cứu trước khi bản cũ nhất bị xoá (~6 MB/file tối đa).
- **Không bao giờ làm hỏng việc ghi log**: mọi lỗi xoay (đĩa đầy, file bị
  khoá bởi tiến trình khác) đều bị nuốt trong `rotate_log` — ưu tiên mất bản
  xoay còn hơn mất dòng log. Test: `tests/test_log_rotate.py` (gọi thẳng
  `scripts/log_rotate.sh`, chạy được trên CI không cần Docker).
- Test xoay hằng chạy bằng tay:
  `LOG_MAX_BYTES=200 scripts/run_if_docker_up.sh demo.log demo echo hi` —
  file vượt 200 byte sẽ thành `demo.log.1` và file mới nhận dòng ghi tiếp.

## 8.5 SSI token — quy trình ngày giao dịch (DEPGAP-1)

Collector đọc token từ **DB** (`ssi_auth_state`), không đọc file. Refresh token
sống **8 giờ** và **KHÔNG được gia hạn** bằng việc làm mới access token — hết là
hết, phải làm lại từ đầu. Đây là thao tác phải làm mỗi ngày giao dịch, và là
nguyên nhân của hai sự cố (14/08: đồng bộ tài khoản chết 4 tiếng vì quên bước 2).

Hai bước, đúng thứ tự. `uv run` KHÔNG tự nạp `.env` — phải nạp trước (như §9):

```bash
cd /opt/trading
set -a && . ./.env && set +a
export DB_DSN=postgresql://trading:trading@127.0.0.1:5432/trading   # 127.0.0.1 như §9 —
                                                               # localhost có thể resolve ::1 (treo)
uv run python scripts/spike_ssi_sdk_auth.py   # 1. nhập OTP (thủ công, SSI bắt buộc)
uv run python scripts/load_token_to_db.py     # 2. CẦU NỐI DUY NHẤT sang DB — làm OTP
                                              #    mà quên bước này thì không có gì thay đổi
```

- **Thời điểm nên làm: khung 8:00–9:00 ngày giao dịch.** Làm lúc 8:30 thì token
  chết ~16:30, phủ trọn phiên (9:00–14:45). Làm quá sớm sẽ chết giữa phiên chiều.
- **Không cần restart collector** — nó tự nối lại khi DB có token hợp lệ (đã
  chứng minh 14/08: token nạp 17:29:39 → phục hồi 17:30:16, không ai restart).
- **BẢO MẬT:** không dán nội dung file token vào chat/issue/log. Nếu cần báo cáo,
  chỉ dẫn `expires_at` / `refresh_token_expires_at`.
- Cảnh báo token (§9) sẽ nhắc lúc 8:00–8:59 nếu quên — nhưng **chỉ khi cron đã
  được cài** (xem §9).

KHÔNG tự động hoá OTP — SSI yêu cầu OTP thủ công.

## 9. Dead-man's switch (heartbeat)

`collector` và `engine` ghi vào bảng `heartbeat` mỗi ~30-60 giây. Nếu một
service chết, Docker `restart: unless-stopped` sẽ thử khởi động lại — nhưng nếu
nó chết lặp (crash loop) hoặc treo mà không thoát, container vẫn "đang chạy" và
không ai biết. `scripts/heartbeat_check.py` đọc bảng đó và bắn Telegram khi một
service quá hạn.

Chạy bằng cron **trên host**, không phải trong container:

```bash
sudo crontab -e
# Cài đặt đầy đủ 16 job vận hành tự động (tất cả gọi qua scripts/sched.sh):
# BẮT BUỘC: Đặt CRON_TZ để cron chạy chuẩn theo giờ Việt Nam
CRON_TZ=Asia/Ho_Chi_Minh

# 1. Kiểm tra token trước giờ mở cửa và heartbeat trong phiên (08:00–15:55, mỗi 5 phút, T2–T6)
# Chạy từ 8:00 để kích hoạt nhánh tiền-phiên (cảnh báo token SSI trước 09:00, CRON-1)
# (Lựa chọn giờ: Windows Task Scheduler lặp 7h đến 15:00; trên VPS giữ khung 8-15 tức đến 15:55 theo
# cấu hình chuẩn cũ để giám sát hậu phiên khi hệ thống chốt sổ và xử lý cuối ngày).
*/5 8-15 * * 1-5 cd /opt/trading && scripts/sched.sh heartbeat

# 2. Phát hiện image container cũ hơn commit git trước phiên giao dịch (08:00, T2–T6)
0 8 * * 1-5 cd /opt/trading && scripts/sched.sh deploy-drift

# 2b. Container tự khởi động lại / bị kernel kill vì hết bộ nhớ (mỗi 10 phút, 24/7 — đợt 130)
# 24/7 CÓ CHỦ Ý, không giới hạn giờ phiên: `restart: unless-stopped` làm container chết tự lên
# lại trong vài giây nên heartbeat (ngưỡng 300 giây) lọt qua, và postgres có thể bị kernel kill
# MỘT tiến trình con mà container không hề restart — dấu vết duy nhất là bộ đếm oom_kill trong
# cgroup. Khung đêm 22:00–01:30 và cuối tuần cũng phải được phủ.
#
# Khi BẢO TRÌ có chủ ý (đo thật 29/09, cùng container):
#   docker compose up -d --build  -> container được TẠO LẠI (Id đổi)      -> KHÔNG báo
#   docker compose restart X      -> Id và RestartCount không đổi          -> KHÔNG báo
#   docker compose stop X         -> Status=exited                         -> BÁO CRITICAL một lần
# Nên nếu để một container DỪNG qua mốc 10 phút (ví dụ §11 Bước 5 chỉ bật postgres),
# sẽ có một tin Telegram — đúng hành vi, không phải lỗi. Muốn im thì tạm bỏ dòng cron này
# trong cửa sổ bảo trì rồi cài lại.
*/10 * * * * cd /opt/trading && scripts/sched.sh container-health

# 3. Ghi dữ liệu sổ lệnh và dòng lệnh VN30F phái sinh thời gian thực (08:40, T2–T6)
# Script tự dừng lúc 14:46 (--until 14:46). Ghi dữ liệu vào data/orderbook/
40 8 * * 1-5 cd /opt/trading && scripts/sched.sh orderbook-recorder

# 4. Giám sát NATS consumer của engine trong giờ giao dịch (mỗi 5 phút, 09:00–15:55, T2–T6)
# (Lựa chọn giờ: Windows Task Scheduler lặp 6h10m đến 15:10; trên VPS giữ khung 9-15 tức đến 15:55 theo
# cấu hình chuẩn cũ để giám sát thông suốt cho đến khi các khâu xử lý sau phiên hoàn tất).
*/5 9-15 * * 1-5 cd /opt/trading && scripts/sched.sh engine-consumer

# 5. Kiểm tra độ phủ nến luồng thời gian thực sau khi chốt phiên chiều (15:10, T2–T6)
10 15 * * 1-5 cd /opt/trading && scripts/sched.sh stream-health

# 6. Phát hiện engine câm không sinh tín hiệu sau phiên giao dịch (15:15, T2–T6)
15 15 * * 1-5 cd /opt/trading && scripts/sched.sh engine-cam

# 7. Kiểm tra tính toàn vẹn của file sổ lệnh phái sinh sau phiên (15:30, T2–T6)
30 15 * * 1-5 cd /opt/trading && scripts/sched.sh orderbook-daily-check

# 8. Backfill nến ngày lịch sử toàn vũ trụ mã ban đêm (20:30, T2–T6)
30 20 * * 1-5 cd /opt/trading && scripts/sched.sh backfill

# 9. Kiểm tra tính toàn vẹn dữ liệu ngày sau khi backfill xong (21:00, T2–T6 — KHÔNG chạy 15:30)
# BẮT BUỘC 21:00: backfill đêm nạp nến lúc 20:30; kiểm trước giờ đó thì bảng nến ngày luôn rỗng!
0 21 * * 1-5 cd /opt/trading && scripts/sched.sh daily-check

# 10. Sao lưu cơ sở dữ liệu TimescaleDB ban đêm (02:00 hàng ngày, 24/7 kể cả cuối tuần — đợt 131)
# BẮT BUỘC 24/7: Dữ liệu nến ngày thứ Sáu vẫn cần được bảo vệ qua cuối tuần trước khi bảo trì.
0 2 * * * cd /opt/trading && scripts/sched.sh backup

# 11. Kiểm tra tính toàn vẹn và độ tươi của bản sao lưu DB (03:00 hàng ngày, 24/7 kể cả cuối tuần — đợt 131)
# BẮT BUỘC chạy sau job backup (02:00) ít nhất 30-60 phút để đảm bảo dump đã hoàn tất.
# Đợt 135: job này cũng canh bản sao lưu SỔ LỆNH (orderbook_*.tar.gz). Tuổi hợp lệ theo LỊCH GIAO DỊCH
# (bản mới nhất phải tạo sau 14:46 của ngày giao dịch gần nhất trước hôm nay), không dùng ngưỡng cố định:
# thứ Hai 03:00 bản 48,5 giờ tuổi vẫn đúng. Bản sao lưu DB giữ ngưỡng 23 giờ (dump mỗi đêm).
# Đợt 138: bản dump DB `.dump` mới nhất phải có bản kê `.counts` (chỉ kiểm tồn tại và khác rỗng;
# nội dung do `restore-drill` phán xử). `.sql.gz` cũ không bị đòi bản kê.
0 3 * * * cd /opt/trading && scripts/sched.sh backup-check

# 12. Sao lưu sổ lệnh data/orderbook/ TĂNG DẦN (02:30 hàng ngày, 24/7 — đợt 132)
# Chỉ đóng gói file chưa sao lưu (xem §6); thay dòng `tar -czf` toàn thư mục cũ. 02:30 vì sau backup DB (02:00).
30 2 * * * cd /opt/trading && scripts/sched.sh orderbook-backup

# 13. Cảnh báo đĩa sắp đầy (mỗi 6 giờ, 24/7 — đợt 132)
# 24/7 CÓ CHỦ Ý: đĩa đầy không chọn giờ, cuối tuần vẫn ghi log và sao lưu. Mỗi 6 giờ vì đĩa đầy
# theo ngày/tuần chứ không theo phút, còn 10 GB là còn vài tuần đệm — 4 tin/ngày là đủ sớm mà không spam.
0 */6 * * * cd /opt/trading && scripts/sched.sh disk-check

# 14. Kiểm các bước làm tay trên host (mỗi tuần một lần, Chủ nhật 07:00 — đợt 133)
# Mỗi tuần một lần là đủ: cấu hình host (cron, daemon.json, ufw, múi giờ, quyền .env) hiếm khi đổi;
# chạy dày chỉ thêm nhiễu. Chủ nhật sáng để lệch cấu hình (ai đó sửa tay giữa tuần) lộ ra trước phiên thứ Hai.
# Job này CHỈ ĐỌC và in bảng ĐẠT/HỎNG/BỎ QUA; BỎ QUA không phải ĐẠT (xem log host-preflight.log).
0 7 * * 0 cd /opt/trading && scripts/sched.sh host-preflight

# 15. Diễn tập phục hồi THẬT bản sao lưu DB mới nhất (mỗi tuần một lần, Chủ nhật 04:00 — đợt 136)
# Vì sao `backup-check` (pg_restore -l) không đủ: xem §6 "pg_restore -l không chứng minh phục hồi được".
# Chủ nhật 04:00: sau backup 02:00 và backup-check 03:00, trước host-preflight 07:00; CHỦ NHẬT vì ít tải
# (diễn tập phục hồi ~100 MB và tạo/xoá một database nháp, không nên chạy giữa phiên).
# So với bản kê `.counts` chụp lúc dump (đợt 137), KHÔNG so với nguồn sống, nên giờ chạy không ảnh hưởng kết quả.
# Job TẠO rồi XOÁ database nháp `trading_restore_drill` (không bao giờ đụng `trading`), cần trống >= 3x dump.
0 4 * * 0 cd /opt/trading && scripts/sched.sh restore-drill
```

### Windows (máy dev / máy chạy thật nếu dùng Windows)

Máy Windows dùng Task Scheduler, không phải cron. Mười sáu task tương ứng với các dòng
cron ở trên (tên task `trading-*`):

Cả mười sáu gọi **cùng một bảng job** với cron Ubuntu — `scripts/sched.sh` — nên
không bên nào chép lại chuỗi lệnh (bài học `4ea4c8d`: một công thức hai bản thì
sớm muộn lệch). Khác biệt duy nhất là lớp bọc để ẩn cửa sổ:

| Task | Lịch | Action |
|---|---|---|
| `trading-heartbeat-check` | 5 phút/lần, 08:00–15:00, T2–T6 (lặp 7h) | `wscript.exe //B //Nologo "D:\...\scripts\run_hidden.vbs" heartbeat` |
| `trading-deploy-drift` | 08:00 T2–T6 | cùng vbs, tham số `deploy-drift` |
| `trading-container-health` | 10 phút/lần, 24/7 | cùng vbs, tham số `container-health` |
| `trading-orderbook-recorder` | 08:40 T2–T6 (tự dừng 14:46) | cùng vbs, tham số `orderbook-recorder` |
| `trading-engine-consumer` | 5 phút/lần, 09:00–15:10, T2–T6 (lặp 6h10m) | cùng vbs, tham số `engine-consumer` |
| `trading-stream-health` | 15:10 T2–T6 | cùng vbs, tham số `stream-health` |
| `trading-engine-cam` | 15:15 T2–T6 | cùng vbs, tham số `engine-cam` |
| `trading-orderbook-daily-check` | 15:30 T2–T6 | cùng vbs, tham số `orderbook-daily-check` |
| `trading-backfill-universe` | 20:30 T2–T6 | cùng vbs, tham số `backfill` |
| `trading-daily-data-check` | **21:00 T2–T6** (sau backfill) | cùng vbs, tham số `daily-check` |
| `trading-backup` | 02:00 hàng ngày (24/7) | cùng vbs, tham số `backup` |
| `trading-backup-check` | 03:00 hàng ngày (24/7) | cùng vbs, tham số `backup-check` |
| `trading-orderbook-backup` | 02:30 hàng ngày (24/7) | cùng vbs, tham số `orderbook-backup` |
| `trading-disk-check` | 6 giờ/lần, 24/7 | cùng vbs, tham số `disk-check` |
| `trading-host-preflight` | Chủ nhật 07:00 (hàng tuần) | cùng vbs, tham số `host-preflight` |
| `trading-restore-drill` | Chủ nhật 04:00 (hàng tuần) | cùng vbs, tham số `restore-drill` |

#### Vì sao qua `wscript.exe` chứ không gọi thẳng `bash.exe`

Task chạy với `LogonType=Interactive` nên Windows cấp console cho `bash.exe` —
cửa sổ nhảy lên **mỗi 5 phút suốt giờ giao dịch**. Cách sạch hơn là đổi principal
sang **S4U** (`New-ScheduledTaskPrincipal -LogonType S4U`), nhưng việc đó **cần
PowerShell elevated**; không có quyền admin thì `Set-ScheduledTask` trả
`Access is denied` (đã gặp 01/09). `scripts/run_hidden.vbs` chạy `bash.exe` với
window style `0` (ẩn) và `bWaitOnReturn = True` — Task Scheduler biết thời lượng
thật nên lần chạy sau không chồng lên lần trước. VPS Ubuntu không cần file này.

#### Cổng Docker — `scripts/run_if_docker_up.sh`

Trước 01/09 ba task chạy vô điều kiện. Khi máy bật lên mà Docker Desktop chưa
khởi động, chúng vẫn chạy, vẫn bật cửa sổ console, vẫn đổ lỗi kết nối DB vào
log — tiếng ồn che mất cái báo thật. Wrapper kiểm container postgres
(`${COMPOSE_PROJECT_NAME:-<tên-thư-mục>}-postgres-1`, vd `trading-postgres-1`
trên VPS hoặc `ai_auto_trading_system-postgres-1` trên máy dev) đang chạy hay không:

- Không chạy ⇒ ghi **một dòng** `SKIP: docker chua chay` vào đúng file log đó
  rồi thoát 0. Bỏ qua thì bỏ qua, nhưng **không bao giờ im lặng**.
- Đang chạy ⇒ nạp `.env`, thay `localhost` → `127.0.0.1` trong `DB_DSN`, chạy
  lệnh, ghi `EXIT=<code>`.

Wrapper dùng chung cho **cả cron Ubuntu** — dòng cron ở §9 gọi cùng script,
không phải dựng lại chuỗi `set -a && . ./.env`.

Kiểm chứng cổng (đã chạy 01/09): giả lập Docker tắt bằng một `docker` giả trong
`PATH` trả mã 1 ⇒ payload **không** chạy, log ra dòng `SKIP`, exit 0.

Điểm bắt buộc khi tạo trên Windows:

- **`DB_DSN` phải dùng `127.0.0.1`, KHÔNG `localhost`** — trên Windows
  `localhost` phân giải IPv6 trước, pool treo ~30s mỗi lần. Lệnh trên thay
  inline bằng `sed`.
- **`bash.exe` chứ không phải `cmd.exe`** — script cần `set -a && . ./.env`
  (cú pháp shell). Đường dẫn: `C:\Program Files\Git\bin\bash.exe`.
- Log ghi vào `logs/<tên>.log` trong repo; mỗi lần chạy ghi thêm dòng
  timestamp + `EXIT=<code>` để phân biệt "đã chạy" với "chưa bao giờ chạy".
- Kiểm chứng task thật sự chạy: `schtasks /query /fo LIST /v` phải cho
  `Last Run Time` khác rỗng **và** file log có dòng mới — "đã tạo task"
  không tính (sự cố 31/08: chuông có sẵn nhưng chưa từng được cài lịch).
- Cấu hình XML (repetition 5 phút trong khung 08:00–15:00 T2–T6, bỏ chặn
  pin/battery): xem bản đã đăng ký trên máy dev
  (`schtasks /query /tn trading-heartbeat-check /xml`).

Script kiểm **năm thứ** (ngoài giờ giao dịch chỉ nhánh tiền-phiên 8:00-8:59
chạy — các nhánh khác tự bỏ qua):

| Kiểm | Cảnh báo | Từ commit |
|---|---|---|
| Service ngừng heartbeat | CRITICAL | `f1a410f` (gốc, trước đó) |
| Dữ liệu ngừng chảy (bar không về, cửa sổ 9:00-11:30/13:00-14:30) | CRITICAL | `7700992` |
| Token SSI sắp/đã hết hạn (kể cả khung 8:00-8:59) | WARN / CRITICAL | `7700992` |
| Hai sổ sách lệch (`cash + Σ(avg_price×qty) − CAPITAL == realized_pnl`) | CRITICAL | `d775ebb` |
| Vị thế ngừng đồng bộ (`account_position_snapshot` của `real_order_account` quá 15 phút chưa cập nhật, hoặc chưa từng đồng bộ) | CRITICAL | `ebfec3c` |

Thay `trading:trading` bằng user/password Postgres thật nếu bạn đã đổi khỏi giá
trị mặc định trong `docker-compose.yml`.

Ngưỡng mặc định 300 giây, đổi bằng `HEARTBEAT_MAX_AGE_SECONDS`.

Kiểm chứng một lần sau khi cài: `docker compose stop engine`, đợi >5 phút trong
giờ giao dịch, xác nhận có tin Telegram, rồi `docker compose start engine`.

Kiểm chứng nhánh tiền-phiên (8:00-8:59) — KHÔNG giả mạo thời gian hệ thống:
chạy tay đúng lệnh cron trên trong khung 8:00-8:59 một lần. Kỳ vọng: script
thoát 0 im lặng nếu token còn > 60 phút; nếu token còn < 60 phút hoặc đã hết
hạn sẽ thấy WARN/CRITICAL trong `/var/log/trading-heartbeat.log`. Nếu không
thấy gì trong khung đó — cron chưa gọi đúng giờ (kiểm `crontab -l`).

## 9.5 Backfill vũ trụ (bars_daily/bars lịch sử)

`bars_daily` toàn vũ trụ là dữ liệu BACKTEST — nó không tự cập nhật. Collector
real-time chỉ ghi `config.symbols` + danh mục đang nắm; phần còn lại của ~1.594
mã phải được backfill thủ công. Không chạy định kỳ thì dữ liệu cũ dần và mọi
backtest lặng lẽ dùng dữ liệu cũ (sự cố 08/2026: bars_daily dừng ở 07/08 trong
khi hôm nay là 18/08 — 11 ngày lệch, không ai nhìn).

Chạy bằng cron **trên host**, sau giờ đóng cửa, ngày trong tuần.
*(Lưu ý: Dòng cron này ĐÃ ĐƯỢC BAO GỒM trong khối 9 job ở §9 — nếu đã cài §9 thì KHÔNG thêm lại vào crontab để tránh chạy lặp hai lần lúc 20:30).*

```bash
# Tham khảo (đã có trong khối cron §9):
# 30 20 * * 1-5 cd /opt/trading && scripts/sched.sh backfill
#
# Lần chạy ĐẦU sau thời gian dài không chạy sẽ NẶNG: nhiều ngày × ~1.594 mã,
# có thể chạm SSI rate-limit. Giới hạn phạm vi nếu cần: thêm --symbols A,B,C
# (vài mã ưu tiên) hoặc --limit N (N mã đầu) — chạy nhiều đêm cho kịp.
```

Lưu ý:

- `--use-universe` đọc `symbol_universe` (cổ phiếu thật, `is_active`). Chuỗi
  nạp: `scripts/spike_ssi_symbols_classify.py` → `scripts/.spike_all_symbols_classified.json`
  → `scripts/backfill_universe.py --use-universe` → `symbol_universe`. File JSON
  `scripts/.spike_all_symbols_classified.json` đã nằm trong git nên bản clone mới
  chạy được ngay. Bỏ qua thêm `--sleep-ms` nếu muốn nhanh hơn — mặc định 200ms/mã
  ~ 5 phút cho toàn bộ.
- Progress (`backfill_progress`) tách hai cột từ 2026-08-18: `attempted_until`
  = ngày đã HỎI API tới (kể cả khi mã không giao dịch — chống fetch lại vĩnh
  viễn), `last_done_date` = ngày bar THẬT cuối (chỉ tiến khi có dữ liệu). Skip
  dựa trên `attempted_until >= to`; `last_done_date` thấp hơn `to` là BÌNH
  THƯỜNG (mã ít thanh khoản không giao dịch mỗi ngày), không phải lỗi.
- Nếu progress cũ nói dối (ghi `last_done_date = to` dù rỗng — bug đã sửa
  2026-08-18): chạy `scripts/fix_backfill_progress.py` (chỉ-xem trước, `--apply`
  để ghi) để sửa lại cho khớp bars_daily. Chỉ sửa bảng TRẠNG THÁI, không đụng
  dữ liệu thị trường.
- 5m (`--timeframe 5m`) backfill toàn vũ trụ KHÔNG nên chạy định kỳ — chỉ
  backtest các mã cần thiết qua `--symbols` (7 ngày/lượt chunk, tốn API).

## 9.6 Chạy bù sau khi máy hoặc Docker tắt

Khi máy chủ bị tắt nguồn, khởi động lại, hoặc Docker daemon ngừng hoạt động qua đêm/cuối tuần, một số tác vụ định kỳ sẽ bị lỡ. Bảng dưới đây hướng dẫn quy tắc chạy bù an toàn cho từng job.

> [!WARNING]
> **Sự cố thật sáng 02/10/2026:** Máy ngủ qua đêm lỡ job `daily-check` lúc 21:00 tối 01/10. Sáng 02/10 lúc 05:47 chạy bù bằng lệnh `Start-ScheduledTask` (hoặc chạy cron không tham số). Job lấy ngày mặc định là hôm nay (`datetime.now(TZ).date()` = 02/10) lúc thị trường chưa mở cửa → báo "0 mã có bar" và bắn cảnh báo Telegram oan. Chạy lại với cờ `--date 2026-10-01` nhưng lúc đó `sched.sh` nuốt cờ → tiếp tục kiểm ngày 02/10 và bắn cảnh báo oan lần 2!

### Bảng quy tắc chạy bù cho các job định kỳ

| Job | Chạy bù được không? | Lệnh chạy bù khuyến nghị | Cờ bắt buộc / Lưu ý quan trọng |
|---|---|---|---|
| `backfill` | **Có** (rất an toàn) | `scripts/sched.sh backfill` | Idempotent (UPSERT theo mã và ts). Cửa sổ trượt mặc định nạp 7 ngày gần nhất (`BACKFILL_DAYS=7`). Nếu máy tắt > 7 ngày, thêm cờ `--from YYYY-MM-DD`. |
| `daily-check` | **Có** (chỉ với cờ) | `scripts/sched.sh daily-check --date <ngày_lỡ> --dry-run` | **BẮT BUỘC** `--date <ngày_lỡ>` VÀ `--dry-run`. Xem kết quả in ra màn hình trước; chỉ bỏ `--dry-run` khi thực sự muốn gửi cảnh báo. **TUYỆT ĐỐI KHÔNG** dùng `Start-ScheduledTask` hoặc chạy không cờ vào hôm sau vì sẽ kiểm nhầm ngày hôm nay. |
| `backup` | **Có** (rất an toàn) | `scripts/sched.sh backup` | Dump lại database Postgres và lập bản kê `.counts`. Nên chạy bù trước khi chạy `backup-check`. |
| `orderbook-backup` | **Có** (rất an toàn) | `scripts/sched.sh orderbook-backup` | Sao lưu tăng dần các file nén sổ lệnh mới hơn tarball trước đó. |
| `backup-check` | **Có** (lưu ý ngữ nghĩa) | `scripts/sched.sh backup-check --dry-run` | Đánh giá theo **thời điểm hiện tại**: nếu bản dump DB cũ hơn 23h (do lỡ job `backup`), nó sẽ báo CRITICAL đúng theo thiết kế. Do đó, hãy chạy bù `backup` thành công trước rồi mới chạy `backup-check`. |
| `stream-health` | **Có** (có điều kiện) | `scripts/sched.sh stream-health --date <ngày_lỡ> --session <sang\|chieu>` | Chỉ chạy bù được nếu log collector của phiên đó vẫn còn trong container hoặc trong `logs/bars_closed.log`. |
| `orderbook-daily-check` | **Có** (chỉ với cờ) | `scripts/sched.sh orderbook-daily-check --date <ngày_lỡ>` | Kiểm tra tính toàn vẹn file `.jsonl.gz` của ngày bị lỡ. |
| `orderbook-recorder` | **KHÔNG** | *Không thể chạy bù* | Luồng WebSocket L2 thời gian thực đã trôi qua thì không thể lấy lại từ API. |
| `heartbeat` | **Không cần** | `scripts/sched.sh heartbeat` | Dead-man's switch giám sát thời gian thực (ngoài phiên tự thoát 0). Chạy tay chỉ để kiểm tra trạng thái ngay lúc bấm. |
| `deploy-drift` | **Không cần** | `scripts/sched.sh deploy-drift` | So sánh commit git và container đang chạy. Chạy tay bất cứ lúc nào. |
| `container-health` | **Không cần** | `scripts/sched.sh container-health` | Giám sát trạng thái sống và OOM của container tại thời điểm hiện tại. |
| `engine-cam` | **Không cần** | `scripts/sched.sh engine-cam` | Kiểm tra chốt chặn engine trên toàn bộ dữ liệu bar 5m trong DB. |
| `engine-consumer` | **Không cần** | `scripts/sched.sh engine-consumer` | Giám sát hàng đợi tiêu thụ NATS JetStream trong phiên. Không có ý nghĩa bù quá khứ. |
| `disk-check` | **Không cần** | `scripts/sched.sh disk-check` | Kiểm tra dung lượng đĩa hiện tại của host. |
| `host-preflight` | **Không cần** | `scripts/sched.sh host-preflight` | Kiểm tra các cấu hình tĩnh trên host. |
| `restore-drill` | **Có** (an toàn) | `scripts/sched.sh restore-drill --dry-run` | Diễn tập phục hồi bản dump DB mới nhất vào DB tạm và tự xoá. |

> [!NOTE]
> **Lưu ý quan trọng về múi giờ khi truy vấn psql:**
> Cột `ts` trong `bars` và `bars_daily` lưu theo kiểu `timestamptz`. Nếu gõ `ts::date` trong psql, Postgres sẽ cast theo múi giờ session (mặc định UTC nếu chưa cấu hình), dẫn đến ngày bị **lùi lại 1 ngày** so với ngày lịch Việt Nam (ví dụ nến ngày `2026-10-02 00:00:00+07` được lưu là `2026-10-01 17:00:00Z` -> `ts::date` ra `2026-10-01`).
> Khi kiểm tra bằng tay trong psql, **BẮT BUỘC** dùng:
> ```sql
> SELECT (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date, count(*) FROM bars_daily GROUP BY 1 ORDER BY 1 DESC LIMIT 5;
> ```

## 10. Sau khi sửa code trong `trading/` — BẮT BUỘC dựng lại container

Sửa file trên host **không có tác dụng gì** với stack đang chạy: collector/engine
chạy code **trong image**, không phải từ repo. Toàn bộ thay đổi trong `trading/`
từ 15/08/2026 tới 01/09/2026 chưa từng chạy vì không ai dựng lại (sự cố đợt 5:
kiểm "sửa đã hoạt động" trên container vẫn chạy image cũ → kết luận sai).

Sau khi commit sửa code, dựng lại (chỉ 2 service — không `down`, không đụng
postgres/nats/grafana, không xoá volume).

**Quy tắc bắt buộc:** Gắn tag cuốn chiếu `:previous` TRƯỚC KHI BUILD để luôn có một điểm lui an toàn:

```bash
# 1. BẮT BUỘC TRƯỚC KHI BUILD: lưu ảnh hiện tại thành :previous
# Tên project do CHÍNH compose quyết định (đã tính .env, biến môi trường, tên thư mục),
# không tự suy lại — tự suy từng ra sai tên (`trading_`) và bỏ qua :previous im lặng.
# sed -n chỉ in dòng name:, không in phần config chứa bí mật.
PROJECT_NAME="$(docker compose config | sed -n 's/^name: //p')"
SAVE_OK=1
[ -n "$PROJECT_NAME" ] || { echo "LỖI: không đọc được tên project từ docker compose config." >&2; SAVE_OK=0; }
for svc in collector engine; do
  img="${PROJECT_NAME}-${svc}"
  if docker image inspect "${img}:latest" >/dev/null 2>&1; then
    if docker tag "${img}:latest" "${img}:previous"; then
      echo "Đã lưu ${img}:latest thành ${img}:previous"
    else
      SAVE_OK=0
    fi
  elif [ -n "$(docker compose ps -aq "$svc")" ]; then
    # Có container mà không thấy image => KHÔNG phải lần đầu; bỏ qua ở đây
    # nghĩa là không có bản cũ để rollback.
    echo "LỖI: đã có container ${svc} nhưng không thấy ảnh ${img}:latest." >&2
    SAVE_OK=0
  else
    echo "Chưa có ảnh ${img}:latest và ${svc} chưa chạy (lần đầu triển khai), bỏ qua lưu :previous"
  fi
done

# 2. Build và khởi động lại chỉ 2 service (không đụng nats/postgres) — CHỈ khi bước 1 ổn,
# kể cả khi dán nguyên khối này vào terminal.
if [ "$SAVE_OK" = 1 ]; then
  docker compose build collector engine && docker compose up -d --no-deps collector engine
else
  echo "DỪNG: chưa lưu được :previous, KHÔNG build. Sửa lỗi ở trên rồi chạy lại." >&2
fi
```

### Quy trình quay về (Rollback khi bản mới lỗi)

Nếu bản triển khai mới gặp sự cố (crash loop, lỗi logic, báo động Telegram):

```bash
# Hoàn nguyên tag :previous thành :latest và restart (tên project lấy như bước lưu ở trên)
PROJECT_NAME="$(docker compose config | sed -n 's/^name: //p')"
for svc in collector engine; do
  img="${PROJECT_NAME}-${svc}"
  docker tag "${img}:previous" "${img}:latest"
done
docker compose up -d --no-deps collector engine
```

*Lưu ý quan trọng về Rollback:*
- Quay về ảnh `:previous` **không** đổi `docker-compose.yml`, nên volume mount `./logs:/app/logs` **vẫn còn nguyên** (không mất log, không mất dữ liệu DB).
- Thứ mất đi (hoàn nguyên) chỉ là phần **mã nguồn** của lần triển khai vừa rồi.

### Phép kiểm sau mỗi lần triển khai (bài học 18/09)

Sau khi deploy, kiểm tra 2 lớp:

1. **Khớp image ID giữa container và tag image:**
```bash
PROJECT_NAME="$(docker compose config | sed -n 's/^name: //p')"   # như bước lưu :previous
docker inspect -f "{{.Image}}" "$(docker compose ps -q collector)"
docker image inspect "${PROJECT_NAME}-collector:latest" --format "{{.Id}}"
# Hai chuỗi hash phải HOÀN TOÀN BẰNG NHAU.
```

2. **Grep chuỗi đặc trưng của chính bản vá bên trong container:**
Hai hash bằng nhau chỉ chứng minh container đang chạy đúng image tag `:latest`, **KHÔNG** chứng minh tag khớp với mã nguồn mới nhất (ngày 18/09 đã dính bẫy: hash khớp nhưng code bên trong container là bản cũ). Do đó, **bắt buộc** phải grep chuỗi đặc trưng vừa thêm:

```bash
docker compose exec collector sh -c \
  'grep -n "chuoi_dac_trung_vua_sua" $(python -c "import trading.collector.main as m; print(m.__file__)")'
```

Ba con số này là chữ ký của code mới (`_connected` + backoff 429 trong
`trading/collector/feed.py` từ `f8e3392`, `_restart_feed_and_alert` trong
`trading/collector/main.py`).

**Nhược điểm phải biết:** phép kiểm chữ ký **tự hết hạn**. Sáu tháng nữa ba
tên đó vẫn còn trong code, `grep` vẫn trả `> 0`, và nó sẽ báo "đã triển khai"
cho một image cũ ba tháng — đúng lớp lỗi mà chính nó sinh ra để bắt. Dùng nó
để trả lời *"bản sửa CỤ THỂ này đã vào chưa"*, không phải *"stack có cũ không"*.

### Phép kiểm không hết hạn: so mốc build với commit gần nhất chạm `trading/`

```bash
C=$(git log -1 --format=%ct -- trading/)
I=$(date -d "$(docker inspect -f '{{.Created}}' \
     $(docker inspect -f '{{.Image}}' $(docker compose ps -q collector)))" +%s)
[ "$I" -ge "$C" ] && echo 'OK: da trien khai' || echo 'CANH BAO: image CU hon commit'
```

Đúng với mọi thay đổi tương lai, không cần bảo trì. Chạy nó sau mỗi lần
`git pull` là biết ngay stack có đang chạy code hiện tại hay không.

**Bắt buộc dùng `%ct` (epoch), KHÔNG dùng `%cI`.** Git in giờ theo múi địa
phương (`+07:00`) còn `docker inspect` in UTC (`Z`); so hai chuỗi đó bằng
`>` cho kết quả NGƯỢC. Đo thật 01/09: commit `18:51:10+07:00` (= `11:51:10Z`)
so với image `13:33:33Z` bị đọc thành "image cũ hơn" trong khi thực tế image
mới hơn 1 giờ 42 phút. Lỗi này bị bắt lúc thử lệnh trước khi viết vào đây.

### Job tự kêu: `scripts/deploy_drift_check.py` (từ `f831344`)

Phép kiểm trên chỉ có giá trị nếu có người nhớ chạy — nên nó đã được đóng
thành **job chạy 08:00 T2–T6** (trước giờ mở cửa 09:00, biết stack chạy code
cũ kịp xử lý). Cảnh báo lệch triển khai KHÔNG khẩn cấp theo phút nên có chuông
riêng, KHÔNG thêm vào `heartbeat_check.py` (chuông đó chỉ được phụ thuộc
DB + config — docker/git là mở rộng bề mặt phụ thuộc của chính chuông báo).

- Windows (máy dev): scheduled task `trading-deploy-drift`, 08:00 T2–T6, qua
  `scripts/run_hidden.vbs` (khuôn ba task cũ, một lần/ngày — không lặp 5 phút).
- Ubuntu: `0 8 * * 1-5 /opt/trading/scripts/sched.sh deploy-drift`
  (job `deploy-drift` trong `scripts/sched.sh`, log ra `logs/deploy-drift.log`).

Có cảnh báo ⇒ in lý do ra log, gửi Telegram, exit 1; ổn ⇒ in một dòng `OK` và
exit 0. Test: `tests/test_deploy_drift_check.py` (hàm `drift_report` thuần
tuý — không cần Docker). Kiểm chứng task đã cài: `schtasks /run /tn
trading-deploy-drift` rồi xem `logs/deploy-drift.log` có dòng mới — "đã tạo
task" không tính (bài học 31/08: chuông có sẵn nhưng chưa từng được cài lịch).

### Job tự kêu: `scripts/check_silent_engine.py` (gói X, 05/09)

Chuông cho một dạng hỏng mà mọi chuông cũ đều bỏ lọt: **engine chạy đủ, log
sạch, heartbeat tươi — và không thể sinh lệnh nào**. Xảy ra thật 04/09 khi engine
đổi sang `octopus_pullback`: ngưỡng `min_avg_value_20 = 2 tỷ` là ngưỡng cho bar
NGÀY, còn engine ăn bar 5 PHÚT, nên cổng thanh khoản đóng ở gần như mọi bar.
Heartbeat vẫn tươi vì engine vẫn nhận bar và vẫn ghi nhịp — nó chỉ không bao giờ
quyết định mua.

Script chạy chiến lược `_default_strategy()` trên chính bảng `bars` mà engine
warm-up từ đó, cho từng mã trong `config.symbols`, rồi kêu nếu:

- cổng thanh khoản đóng 100% (`CRITICAL_SILENT`), hoặc
- không có tín hiệu `bull` nào trong toàn bộ lịch sử (`WARN_NO_BULL`).

- Windows (máy dev): scheduled task `trading-engine-cam`, **15:15 T2–T6**, qua
  `scripts/run_hidden.vbs` (sau khi đóng phiên 15:00, kiểm tra xem cả phiên engine có bị câm không).
- Ubuntu: `15 15 * * 1-5 /opt/trading/scripts/sched.sh engine-cam`
  (job `engine-cam` trong `scripts/sched.sh`, log ra `logs/engine-cam.log`).

Có mã câm ⇒ in bảng ra log, gửi Telegram, exit 1; ổn ⇒ in `[OK]` và exit 0.
Test: `tests/test_silent_engine_guard.py` (dùng MockStorage — không cần DB).

**Kiểm chứng task đã cài** (không phải "đã tạo task"): `schtasks /run /tn
trading-engine-cam` rồi xem `logs/engine-cam.log` có dòng mới. Hôm nay job này
**phải kêu** — HII và AAA đang câm 100%, đó là đối chứng dương sẵn có.

## 11. Chuyển từ máy Windows sang VPS Ubuntu (Migration Runbook)

Mục này hướng dẫn quy trình chuyển toàn bộ dữ liệu và vận hành hệ thống từ máy Windows hiện tại sang VPS Ubuntu.

> [!CAUTION]
> **QUY TẮC BẮT BUỘC ĐỂ TRÁNH XUNG ĐỘT VÀ MẤT DỮ LIỆU:**
> 1. **Thời điểm thực hiện:** BẮT BUỘC thực hiện vào **ngày không có phiên giao dịch** (tối thứ Sáu sau 21:30 khi các job cuối ngày hoàn tất, hoặc vào ngày cuối tuần Thứ Bảy / Chủ Nhật). Tuyệt đối KHÔNG chuyển đổi trong phiên giao dịch vì sẽ làm đứt quãng dòng nến luồng thời gian thực và ghi sổ lệnh.
> 2. **Không chạy song song:** VPS chạy **thay thế** máy Windows, KHÔNG chạy song song. Tuyệt đối không để cả 2 máy cùng chạy collector/engine vì sẽ xung đột luồng stream của SSI FastConnect và consumer NATS.
> 3. **Trạng thái an toàn (`real_trading_enabled: false`):** Trên VPS, luôn giữ cấu hình `real_trading_enabled: false` trong `config/config.yaml`. Việc kích hoạt đặt lệnh thật là quyết định riêng của chủ dự án sau khi hoàn thành các bước diễn tập và đối soát lệnh thật (Phase 4).
> 4. **Chưa xác minh kết nối SSI từ IP nước ngoài:** Chưa có tài liệu xác minh chính thức liệu SSI FastConnect có áp dụng IP whitelist hay giới hạn truy cập từ các dải IP VPS ngoài Việt Nam hay không. Vì vậy, **bắt buộc phải chạy bước kiểm tra kết nối SSI chỉ đọc (Bước 7)** từ VPS trước khi tiến hành cắt chuyển chính thức.

---

### Quy trình cắt chuyển 10 bước

#### Bước 1: Dừng toàn bộ Scheduled Tasks trên máy Windows
Mở PowerShell trên máy Windows và vô hiệu hóa tất cả 9 task `trading-*`:
```powershell
Get-ScheduledTask -TaskName "trading-*" | Disable-ScheduledTask
# Xác nhận toàn bộ State đã chuyển sang Disabled:
Get-ScheduledTask -TaskName "trading-*" | Select-Object TaskName, State
```

#### Bước 2: Dừng engine và collector trên máy Windows
Chỉ dừng 2 service nghiệp vụ, giữ postgres chạy để trích xuất dữ liệu:
```powershell
cd D:\My_Vault_Obsidian\Project\AI_auto_trading_system
docker compose stop engine collector
```

#### Bước 3: Đếm số dòng mốc và sao lưu dữ liệu trên Windows
1. Đếm và ghi lại số dòng mốc của 6 bảng chính trên Windows:
```powershell
docker compose exec -T postgres psql -U trading -d trading -c "
SELECT 'bars' AS tbl, count(*) FROM bars
UNION ALL SELECT 'bars_daily', count(*) FROM bars_daily
UNION ALL SELECT 'orders', count(*) FROM orders
UNION ALL SELECT 'positions', count(*) FROM positions
UNION ALL SELECT 'engine_state', count(*) FROM engine_state
UNION ALL SELECT 'real_order_fills', count(*) FROM real_order_fills;
"
```

2. Xuất dữ liệu TimescaleDB dạng custom archive (`-Fc`) ra file.

> [!CAUTION]
> **KHÔNG** dùng `docker compose exec ... pg_dump -Fc > file` trong Windows PowerShell 5.1: toán tử `>` mã hoá lại luồng ra thành văn bản UTF-16, file `.dump` nhị phân **hỏng**, và bạn chỉ phát hiện lúc restore trên VPS — khi máy Windows đã tắt. Ghi file **bên trong container** rồi chép ra bằng `docker compose cp`:

```powershell
docker compose exec -T postgres pg_dump -U trading -Fc -f /tmp/backup_migration.dump trading
docker compose cp postgres:/tmp/backup_migration.dump .\backup_migration.dump
# Claude thử 27/09 trên máy Windows: 59 giây, 98,7 MB, 5 byte đầu = `PGDMP` (đúng định dạng).
# pg_dump in cảnh báo `circular foreign-key constraints ... continuous_agg`: đó là catalog nội bộ
# của TimescaleDB, gặp ở mọi bản dump toàn DB; exit code vẫn 0. Không phải lỗi.
# Kiểm file dump đọc được (liệt kê mục lục; phải có dòng, không lỗi):
docker compose exec -T postgres pg_restore -l /tmp/backup_migration.dump | Select-Object -First 5
```

3. Ghi lại phiên bản TimescaleDB đang chạy (VPS **phải** khôi phục trên đúng phiên bản này):
```powershell
docker compose exec -T postgres psql -U trading -d trading -Atc "SELECT extversion FROM pg_extension WHERE extname='timescaledb';"
# 27/09/2026 ra: 2.27.2
```

4. Nén thư mục sổ lệnh `data/orderbook`:
```powershell
tar -czvf orderbook_migration.tar.gz data/orderbook
```

#### Bước 4: Chép file sao lưu và cấu hình sang VPS Ubuntu
Sử dụng SCP hoặc SFTP để chuyển các file sang VPS:
```powershell
# Chép file dump DB và sổ lệnh sang thư mục /tmp của VPS:
scp backup_migration.dump orderbook_migration.tar.gz <ĐIỀN: USER>@<ĐIỀN: VPS_IP>:/tmp/

# Chép file cấu hình bảo mật .env từ Windows sang /opt/trading trên VPS:
scp .env <ĐIỀN: USER>@<ĐIỀN: VPS_IP>:/opt/trading/.env
```

#### Bước 5: Khôi phục dữ liệu trên VPS Ubuntu
Đăng nhập SSH vào VPS (`ssh <ĐIỀN: USER>@<ĐIỀN: VPS_IP>`):
```bash
cd /opt/trading

# (0) Phân quyền bảo mật và chuẩn hoá dòng cho file .env:
chmod 600 .env
sed -i 's/\r$//' .env
# Giải thích: Do .env được chép từ máy Windows sang mang định dạng xuống dòng CRLF (\r\n),
# lệnh sed trên loại bỏ ký tự \r thừa để tránh làm hỏng các biến môi trường (token SSI, Telegram).

# (a) GHIM phiên bản TimescaleDB bằng đúng số đã ghi ở Bước 3 (compose dùng tag `latest-pg16`,
#     VPS kéo về hôm nay có thể là bản mới hơn — TimescaleDB yêu cầu khôi phục trên CÙNG phiên bản).
#     File override chỉ nằm trên VPS, không commit:
cat > docker-compose.override.yml <<'EOF'
services:
  postgres:
    image: timescale/timescaledb:<ĐIỀN: extversion ở Bước 3, vd 2.27.2>-pg16
EOF

# (b) CHỈ khởi động postgres (KHÔNG engine/collector — chúng sẽ tạo bảng và ghi dữ liệu vào DB
#     trước khi restore). DB phải còn RỖNG:
docker compose up -d postgres
docker compose exec postgres pg_isready -U trading
docker compose exec -T postgres psql -U trading -d trading -Atc "SELECT extversion FROM pg_extension WHERE extname='timescaledb';"
# -> PHẢI bằng số ở Bước 3. Khác thì dừng lại, sửa override.
#    Ra RỖNG (hoặc lỗi kết nối) ngay sau khi volume mới được tạo: Postgres còn đang khởi tạo
#    lần đầu (pg_isready đã báo sẵn sàng từ máy chủ tạm) — chờ 5 giây rồi chạy lại lệnh trên,
#    ĐỪNG coi rỗng là "sai phiên bản" (diễn tập đợt 127).
docker compose exec -T postgres psql -U trading -d trading -Atc "SELECT count(*) FROM pg_tables WHERE schemaname='public';"
# -> PHẢI là 0 (DB rỗng). Không phải 0 thì dừng lại: đang restore đè lên dữ liệu có sẵn.

# (c) Chép dump vào container rồi khôi phục từ file (không qua pipe, không --clean vì DB rỗng):
docker compose cp /tmp/backup_migration.dump postgres:/tmp/backup_migration.dump
docker compose exec -T postgres psql -U trading -d trading -c "SELECT timescaledb_pre_restore();"
docker compose exec -T postgres pg_restore -U trading -d trading --no-owner /tmp/backup_migration.dump
docker compose exec -T postgres psql -U trading -d trading -c "SELECT timescaledb_post_restore();"

# 4. Giải nén thư mục sổ lệnh:
tar -xzvf /tmp/orderbook_migration.tar.gz -C /opt/trading/
chmod -R 775 /opt/trading/data/orderbook
```

#### Bước 6: Kiểm tra đối soát số dòng sau khi khôi phục trên VPS
Chạy truy vấn đếm dòng trên VPS:
```bash
docker compose exec -T postgres psql -U trading -d trading -c "
SELECT 'bars' AS tbl, count(*) FROM bars
UNION ALL SELECT 'bars_daily', count(*) FROM bars_daily
UNION ALL SELECT 'orders', count(*) FROM orders
UNION ALL SELECT 'positions', count(*) FROM positions
UNION ALL SELECT 'engine_state', count(*) FROM engine_state
UNION ALL SELECT 'real_order_fills', count(*) FROM real_order_fills;
"
```
**BẮT BUỘC:** Đối chiếu 6 con số này với số đo được ở Bước 3 trên Windows. Tất cả phải trùng khớp 100%.

#### Bước 7: Kiểm tra kết nối SSI FastConnect từ VPS (Chỉ đọc)
Chạy script kiểm tra xác thực SSI chỉ đọc (không yêu cầu OTP, không sinh lệnh):
```bash
cd /opt/trading
set -a && . ./.env && set +a
uv run python scripts/spike_ssi_sdk_auth.py --no-otp
```
- Nếu thành công: In thông báo xác thực thành công hoặc token hợp lệ.
- Nếu gặp lỗi mạng / HTTP 403 / Forbidden: Chứng tỏ IP của VPS đang bị SSI từ chối (chưa xác minh whitelist). Cần liên hệ SSI hoặc sử dụng proxy/VPN IP Việt Nam trước khi tiếp tục.

#### Bước 8: Khởi động toàn bộ stack và kích hoạt crontab trên VPS
```bash
cd /opt/trading
# Khởi động toàn bộ các service container
docker compose up -d --build

# Kiểm tra trạng thái các container:
docker compose ps

# Cài đặt 16 cron job vào crontab theo hướng dẫn tại §9:
sudo crontab -e
```

**Chạy `host-preflight` ngay sau Bước 8, trước khi coi là xong** (đợt 133): nó kiểm các bước làm tay
mà không gì khác kiểm (cron + `CRON_TZ`, `daemon.json`, logrotate, `chmod 600 .env` và không có ký tự CR,
múi giờ, `ufw`, thư mục sao lưu, đĩa, cờ thực thi, đồng hồ; đợt 135: cổng Docker publish có bind
`127.0.0.1` không, đọc thẳng từ `docker compose config` vì `ufw` không chi phối cổng Docker; đợt 139:
cổng **đang nghe thật** qua `ss -ltnH`). Đọc bảng: mọi dòng phải `ĐẠT`; dòng `BỎ QUA` không phải `ĐẠT` —
nó có nghĩa là công cụ không đo được, phải tự kiểm tay.

**Chạy bằng `sudo`, đúng danh tính của cron** (đợt 139, đo thật trong container Ubuntu): cron §9 được cài
bằng `sudo crontab -e`, tức crontab của **root**, nên job `host-preflight` chạy dưới root. Chạy tay không
`sudo` thì `crontab -l` đọc crontab của tài khoản thường (rỗng) — công cụ sẽ ra `BỎ QUA` ở phép crontab và in
cảnh báo "chạy dưới uid=..." ở cuối bảng; các phép phụ thuộc danh tính (crontab, thư mục sao lưu ghi được)
chỉ khớp với lần chạy cron khi chạy dưới root.
```bash
cd /opt/trading && sudo scripts/sched.sh host-preflight   # bảng in ra logs/host-preflight.log
sudo uv run python scripts/host_preflight.py              # hoặc chạy trực tiếp để xem bảng
```

#### Bước 8b: Chứng minh cảnh báo Telegram tới nơi
Chạy probe để xác nhận thông báo Telegram hoạt động thực sự từ VPS trước khi hoàn tất chuyển đổi (Brief 126 §2c):
```bash
cd /opt/trading
set -a && . ./.env && set +a
uv run python scripts/probe_dead_man_switch.py
```
> [!IMPORTANT]
> **Yêu cầu chủ dự án xác nhận:** Kiểm tra ứng dụng Telegram trên điện thoại. Chủ dự án BẮT BUỘC phải nhận được tin nhắn probe và xác nhận thành công trước khi coi việc chuyển máy là hoàn tất.

#### Bước 9: Kiểm tra cổng go-live an toàn
Xác minh chắc chắn lệnh thật chưa bị vô tình bật trên VPS:
```bash
uv run python -c "
from trading.config import load_config
cfg = load_config('config/config.yaml')
assert not cfg.real_trading_enabled, 'LỖI NGUY HIỂM: real_trading_enabled đang bật!'
print('GO-LIVE GATE CHECK: OK (real_trading_enabled is False)')
"
```
Đọc lại file `GO_LIVE_AUDIT.md` để đối chiếu các điều kiện tiên quyết.

#### Bước 10: Tắt hoàn toàn stack Windows sau khi nghiệm thu
Chỉ sau khi VPS đã hoạt động ổn định và vượt qua các phép kiểm trên:
```powershell
# Trên máy Windows: Dừng toàn bộ container
cd D:\My_Vault_Obsidian\Project\AI_auto_trading_system
docker compose down
```
Lúc này toàn bộ hệ thống đã chuyển sang vận hành chính thức trên VPS.

## 12. Not covered here (needs a decision, not just infra)

- Derivative trading — no risk-control code exists yet, do not enable.
- Real order placement — code exists but has never been tested against a real
  fill; run the Phase 4 runbook first (see `docs/plans-legacy/PLAN_REAL_ORDER_PLACEMENT.md`).
- CD — `.github/workflows/ci.yml` runs tests + ruff on every push, but there is
  no automated deployment; the steps above are manual
  (`git pull && docker compose up -d --build`).
