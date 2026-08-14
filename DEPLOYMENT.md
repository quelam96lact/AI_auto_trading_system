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
0 2 * * * /opt/trading/scripts/backup_db.sh /var/backups/trading-db >> /var/log/trading-backup.log 2>&1
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
*/5 8-15 * * 1-5 cd /opt/trading && set -a && . ./.env && set +a && DB_DSN=postgresql://trading:trading@127.0.0.1:5432/trading /usr/local/bin/uv run python scripts/heartbeat_check.py >> /var/log/trading-heartbeat.log 2>&1
```

Script kiểm **bốn thứ** (ngoài giờ giao dịch chỉ nhánh tiền-phiên 8:00-8:59
chạy — các nhánh khác tự bỏ qua):

| Kiểm | Cảnh báo | Từ commit |
|---|---|---|
| Service ngừng heartbeat | CRITICAL | `f1a410f` (gốc, trước đó) |
| Dữ liệu ngừng chảy (bar không về, cửa sổ 9:00-11:30/13:00-14:30) | CRITICAL | `7700992` |
| Token SSI sắp/đã hết hạn (kể cả khung 8:00-8:59) | WARN / CRITICAL | `7700992` |
| Hai sổ sách lệch (`cash + Σ(avg_price×qty) − CAPITAL == realized_pnl`) | CRITICAL | `d775ebb` |

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

## Not covered here (needs a decision, not just infra)

- Derivative trading — no risk-control code exists yet, do not enable.
- Real order placement — code exists but has never been tested against a real
  fill; run the Phase 4 runbook first (see `docs/plans-legacy/PLAN_REAL_ORDER_PLACEMENT.md`).
- CD — `.github/workflows/ci.yml` runs tests + ruff on every push, but there is
  no automated deployment; the steps above are manual
  (`git pull && docker compose up -d --build`).
