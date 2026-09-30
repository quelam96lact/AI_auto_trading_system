#!/usr/bin/env bash
# Nightly pg_dump backup (-Fc) for the trading Postgres/TimescaleDB volume.
# Usage: ./scripts/backup_db.sh [backup_dir]
# Intended to run via sched.sh on host (Windows Task Scheduler or Ubuntu cron).
#
# Besides trading_<ts>.dump this writes trading_<ts>.counts (same stem): one line
# "table<TAB>rows" for EVERY table of schema public, snapshotted just BEFORE pg_dump.
# scripts/restore_drill.py compares the restored copy against THIS statement, not
# against the live database (the live one keeps growing: comparing against it made
# a GOOD dump look 96.5% complete 18 hours later, brief dot 137). Rows can only be
# added between the snapshot and pg_dump's own snapshot, so restored >= statement.
# A statement without its dump is misleading junk: any failure removes it.
set -euo pipefail

# TRADING_BACKUP_DIR (.env) truoc, roi moi den mac dinh Ubuntu. Tren Windows
# "/var/backups/trading-db" khong ton tai va se chet o mkdir (do that 29/09).
BACKUP_DIR="${1:-${TRADING_BACKUP_DIR:-/var/backups/trading-db}}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="${BACKUP_DIR}/trading_${TIMESTAMP}.dump"
CONTAINER_DUMP="/tmp/trading_${TIMESTAMP}.dump"
COUNTS_FILE="${BACKUP_DIR}/trading_${TIMESTAMP}.counts"

mkdir -p "$BACKUP_DIR"

# Any exit before the dump is verified removes the statement (and a half-written temp).
BACKUP_OK=0
cleanup_on_failure() {
  if [ "$BACKUP_OK" != 1 ]; then
    rm -f "$COUNTS_FILE" "${COUNTS_FILE}.tmp"
  fi
}
trap cleanup_on_failure EXIT

# Tables come from the catalog (same query as restore_drill.py LIST_TABLES_SQL), never a
# hard-coded list: a table added later must be covered without touching this file.
COUNTS_SQL="$(cat <<'SQL'
SELECT c.relname, (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM public.%I', c.relname), false, true, '')))[1]::text
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r','p') ORDER BY 1
SQL
)"
COUNTS_SQL="${COUNTS_SQL//$'\n'/ }"

# Write to a temp file then rename: never leave a half-written statement behind.
MSYS_NO_PATHCONV=1 docker compose exec -T postgres psql -U trading -d trading -At -F $'\t' -v ON_ERROR_STOP=1 -c "$COUNTS_SQL" | tr -d '\r' > "${COUNTS_FILE}.tmp"
if [ ! -s "${COUNTS_FILE}.tmp" ]; then
  echo "ERROR: row-count statement is empty (no tables listed)." >&2
  exit 1
fi
mv "${COUNTS_FILE}.tmp" "$COUNTS_FILE"

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

BACKUP_OK=1
echo "Backup written to ${OUT_FILE} ($(du -h "$OUT_FILE" | cut -f1)) + row-count statement ${COUNTS_FILE}"

find "$BACKUP_DIR" \( -name 'trading_*.dump' -o -name 'trading_*.sql.gz' -o -name 'trading_*.counts' \) -mtime "+${RETENTION_DAYS}" -delete

echo "Pruned backups older than ${RETENTION_DAYS} days"
