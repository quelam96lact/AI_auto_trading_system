# Deployment Guide — Ubuntu VPS

This covers deploying the collector/engine/postgres/nats/grafana stack to a
production Ubuntu server via Docker Compose. See `DEPLOYMENT_READINESS.md` for
the full go-live checklist this guide implements the "Critical" items of.

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
until the real-order verification runbook (`PLAN_REAL_ORDER_PLACEMENT.md`) has
been run end-to-end.

## 3. Firewall — only expose what must be public

By default `docker-compose.yml` binds Postgres (5432) and NATS (4222) to
`127.0.0.1` only, so they are not reachable from outside the host even without
a firewall. Grafana (3000) is still bound to all interfaces — put it behind a
reverse proxy with TLS (see §4) rather than exposing it directly.

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

Also change Grafana's default admin password (`GF_SECURITY_ADMIN_PASSWORD` in
`docker-compose.yml`) before exposing it publicly.

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

## Not covered here (needs a decision, not just infra)

- Derivative trading — no risk-control code exists yet, do not enable.
- Real order placement — code exists but has never been tested against a real
  fill; run the Phase 4 runbook first (see `PLAN_REAL_ORDER_PLACEMENT.md`).
- CI/CD — no `.github/workflows` yet; deployment above is manual
  (`git pull && docker compose up -d --build`).
