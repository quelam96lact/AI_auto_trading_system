#!/usr/bin/env bash
# Nightly pg_dump backup (-Fc) for the trading Postgres/TimescaleDB volume.
# Usage: ./scripts/backup_db.sh [backup_dir]
# Intended to run via sched.sh on host (Windows Task Scheduler or Ubuntu cron).
set -euo pipefail

# TRADING_BACKUP_DIR (.env) truoc, roi moi den mac dinh Ubuntu. Tren Windows
# "/var/backups/trading-db" khong ton tai va se chet o mkdir (do that 29/09).
BACKUP_DIR="${1:-${TRADING_BACKUP_DIR:-/var/backups/trading-db}}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="${BACKUP_DIR}/trading_${TIMESTAMP}.dump"
CONTAINER_DUMP="/tmp/trading_${TIMESTAMP}.dump"

mkdir -p "$BACKUP_DIR"

# Dump inside container to avoid binary stream issues over shell pipe
# MSYS_NO_PATHCONV=1 prevents Git Bash on Windows from rewriting /tmp to AppData/Local/Temp
MSYS_NO_PATHCONV=1 docker compose exec -T postgres pg_dump -U trading -Fc -f "$CONTAINER_DUMP" trading
docker compose cp "postgres:${CONTAINER_DUMP}" "$OUT_FILE"
MSYS_NO_PATHCONV=1 docker compose exec -T postgres rm -f "$CONTAINER_DUMP"

verify_dump() {
  local f="$1"
  if command -v pg_restore >/dev/null 2>&1; then
    pg_restore -l "$f" >/dev/null
  else
    docker compose exec -T postgres pg_restore -l < "$f" >/dev/null
  fi
}

if ! verify_dump "$OUT_FILE"; then
  echo "ERROR: pg_restore -l verification failed for ${OUT_FILE}. Removing corrupted file." >&2
  rm -f "$OUT_FILE"
  exit 1
fi

echo "Backup written to ${OUT_FILE} ($(du -h "$OUT_FILE" | cut -f1))"

find "$BACKUP_DIR" \( -name 'trading_*.dump' -o -name 'trading_*.sql.gz' \) -mtime "+${RETENTION_DAYS}" -delete

echo "Pruned backups older than ${RETENTION_DAYS} days"
