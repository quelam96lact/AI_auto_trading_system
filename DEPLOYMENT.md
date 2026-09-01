# Deployment Guide — Ubuntu VPS

This covers deploying the collector/engine/postgres/nats/grafana stack to a
production Ubuntu server via Docker Compose. See `GO_LIVE_AUDIT.md` for what is
still blocking go-live — read it before enabling real trading.

## 1. Server prerequisites

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin ufw
sudo systemctl enable --now docker
```

## 2. Get the code + secrets onto the server

```bash
git clone <this-repo-url> /opt/trading
cd /opt/trading
cp .env.example .env
# edit .env with real SSI credentials + Telegram token (see README.md for
# which variables config.py requires). Never commit this file.
chmod 600 .env
```

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
    server_name grafana.YOUR_DOMAIN;
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
sudo certbot --nginx -d grafana.YOUR_DOMAIN
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

`scripts/backup_db.sh` runs `pg_dump` inside the `postgres` container, gzips
it, and prunes backups older than 14 days (override with
`BACKUP_RETENTION_DAYS`). Schedule it via cron on the host:

```bash
chmod +x scripts/backup_db.sh
sudo crontab -e
# add:
# `cd /opt/trading` la BAT BUOC: script goi `docker compose exec`, ma lenh do tim
# docker-compose.yml o THU MUC HIEN TAI. Cron chay voi cwd = home cua user
# (thuong /root) nen thieu `cd` se bao "no configuration file provided" va
# backup that bai NGAY DEM DAU — khong co canh bao Telegram cho backup, nen
# se khong ai biet cho toi luc CAN restore.
0 2 * * * cd /opt/trading && ./scripts/backup_db.sh /var/backups/trading-db >> /var/log/trading-backup.log 2>&1
```

Restore:

```bash
gunzip -c /var/backups/trading-db/trading_YYYYMMDD_HHMMSS.sql.gz | \
  docker compose exec -T postgres psql -U trading trading
```

Test the restore path at least once against a scratch database before relying
on it — an untested backup is not a backup.

## 7. Resource limits

Each service in `docker-compose.yml` has `mem_limit`/`cpus` set (postgres 1g/1
cpu, collector/engine 512m/1 cpu each, grafana 512m/0.5 cpu, nats 256m/0.5
cpu) as a starting point against runaway memory/CPU use. Adjust based on
observed usage (`docker stats`) once running for a few days.

## 8. Log rotation

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
# thêm — chạy 8:00-15:59 ngày giao dịch. KHÔNG ghi 9-15: script có nhánh
# tiền-phiên 8:00-8:59 (cảnh báo token trước giờ mở cửa, 7700992) — lịch 9-15
# sẽ không bao giờ gọi nhánh đó (CRON-1).
*/5 8-15 * * 1-5 /opt/trading/scripts/sched.sh heartbeat

# Kiểm tra sót bar daily sau phiên giao dịch (chạy 15:30 thứ 2 - thứ 6 hàng tuần)
30 15 * * 1-5 /opt/trading/scripts/sched.sh daily-check
```

### Windows (máy dev / máy chạy thật nếu dùng Windows)

Máy Windows dùng Task Scheduler, không phải cron. Ba task tương ứng với ba dòng
cron ở trên (tên task `trading-*`):

Cả ba gọi **cùng một bảng job** với cron Ubuntu — `scripts/sched.sh` — nên
không bên nào chép lại chuỗi lệnh (bài học `4ea4c8d`: một công thức hai bản thì
sớm muộn lệch). Khác biệt duy nhất là lớp bọc để ẩn cửa sổ:

| Task | Lịch | Action |
|---|---|---|
| `trading-heartbeat-check` | 5 phút/lần, 08:00–15:00, T2–T6 | `wscript.exe //B //Nologo "D:\...\scripts\run_hidden.vbs" heartbeat` |
| `trading-daily-data-check` | 15:30 T2–T6 | cùng vbs, tham số `daily-check` |
| `trading-backfill-universe` | 20:30 T2–T6 | cùng vbs, tham số `backfill` |

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
log — tiếng ồn che mất cái báo thật. Wrapper kiểm container
`ai_auto_trading_system-postgres-1` đang chạy hay không:

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

Chạy bằng cron **trên host**, sau giờ đóng cửa, ngày trong tuần:

```bash
sudo crontab -e
# backfill bars_daily toàn vũ trụ — 20:30 thứ 2 - thứ 6 hàng tuần.
# Lần chạy ĐẦU sau thời gian dài không chạy sẽ NẶNG: nhiều ngày × ~1.594 mã,
# có thể chạm SSI rate-limit. Giới hạn phạm vi nếu cần: thêm --symbols A,B,C
# (vài mã ưu tiên) hoặc --limit N (N mã đầu) — chạy nhiều đêm cho kịp.
30 20 * * 1-5 /opt/trading/scripts/sched.sh backfill
```

Lưu ý:

- `--use-universe` đọc `symbol_universe` (cổ phiếu thật, `is_active`). Bỏ qua
  thêm `--sleep-ms` nếu muốn nhanh hơn — mặc định 200ms/mã ~ 5 phút cho toàn
  bộ.
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

## Not covered here (needs a decision, not just infra)

- Derivative trading — no risk-control code exists yet, do not enable.
- Real order placement — code exists but has never been tested against a real
  fill; run the Phase 4 runbook first (see `docs/plans-legacy/PLAN_REAL_ORDER_PLACEMENT.md`).
- CD — `.github/workflows/ci.yml` runs tests + ruff on every push, but there is
  no automated deployment; the steps above are manual
  (`git pull && docker compose up -d --build`).
