#!/usr/bin/env bash
# Nightly pg_dump backup for the trading Postgres/TimescaleDB volume.
# Usage: ./scripts/backup_db.sh [backup_dir]
# Intended to run via cron on the host, e.g.:
#   0 2 * * * /path/to/repo/scripts/backup_db.sh >> /var/log/trading-backup.log 2>&1
set -euo pipefail

BACKUP_DIR="${1:-/var/backups/trading-db}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="${BACKUP_DIR}/trading_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

docker compose exec -T postgres pg_dump -U trading trading | gzip > "$OUT_FILE"

echo "Backup written to ${OUT_FILE} ($(du -h "$OUT_FILE" | cut -f1))"

find "$BACKUP_DIR" -name 'trading_*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete

echo "Pruned backups older than ${RETENTION_DAYS} days"
