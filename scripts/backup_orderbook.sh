#!/usr/bin/env bash
# Nightly backup of data/orderbook/ — INCREMENTAL, so total size grows LINEARLY.
# Usage: ./scripts/backup_orderbook.sh [backup_dir]
# Intended to run via sched.sh on host (Windows Task Scheduler or Ubuntu cron).
#
# Why not `tar -czf ... data/orderbook` (the old DEPLOYMENT.md cron): that packs the
# WHOLE directory every night and nothing deletes old archives, so the archive of day
# N contains days 1..N again -> total size grows with the SQUARE of the session count
# (brief dot 132: ~217 GB after a year for ~2.9 GB of data).
#
# data/orderbook/<symbol>/<date>.jsonl.gz: each session writes a NEW file and never
# edits an old one. So we pack only files NEWER than the newest existing
# orderbook_*.tar.gz in the backup dir ("not yet backed up"). With no archive yet
# (first run) that is everything, once. Running twice in a row packs nothing the
# second time; a non-trading day packs nothing and is NOT an error.
#
# Env: BACKUP_RETENTION_DAYS (default 14), ORDERBOOK_DIR (default <repo>/data/orderbook).
set -euo pipefail

# TRADING_BACKUP_DIR (.env) truoc, roi moi den mac dinh Ubuntu. Tren Windows
# "/var/backups/trading-db" khong ton tai va se chet o mkdir (do that 29/09).
BACKUP_DIR="${1:-${TRADING_BACKUP_DIR:-/var/backups/trading-db}}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ORDERBOOK_DIR:-$REPO/data/orderbook}"
# Archive members are data/orderbook/... (relative to the repo root), so the restore
# runbook (DEPLOYMENT.md §11: tar -xzvf ... -C /opt/trading/) works unchanged.
ROOT="$(dirname "$(dirname "$SRC")")"

if [ ! -d "$SRC" ]; then
  echo "ERROR: orderbook dir not found: ${SRC}" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

# Newest existing archive = the marker of what was already backed up.
LATEST_TAR="$(ls -1t "$BACKUP_DIR"/orderbook_*.tar.gz 2>/dev/null | head -n 1 || true)"

LIST="$(mktemp)"
trap 'rm -f "$LIST"' EXIT

if [ -n "$LATEST_TAR" ]; then
  find "$SRC" -type f -name '*.jsonl.gz' -newer "$LATEST_TAR" -print
else
  find "$SRC" -type f -name '*.jsonl.gz' -print
fi | sed "s#^${ROOT}/##" | sort > "$LIST"

if [ ! -s "$LIST" ]; then
  echo "No orderbook files newer than the last backup (non-trading day, or recorder did not run) — nothing to back up."
  exit 0
fi

OUT_FILE="${BACKUP_DIR}/orderbook_$(date +%Y%m%d).tar.gz"
# Second run the same day with genuinely new files: never overwrite the earlier archive.
if [ -e "$OUT_FILE" ]; then
  OUT_FILE="${BACKUP_DIR}/orderbook_$(date +%Y%m%d_%H%M%S).tar.gz"
fi

tar -czf "$OUT_FILE" -C "$ROOT" -T "$LIST"

# An empty archive with a valid name would make backup_check believe a backup exists.
if ! COUNT="$(tar -tzf "$OUT_FILE" | wc -l)" || [ "$COUNT" -le 0 ]; then
  echo "ERROR: verification failed for ${OUT_FILE} (unreadable or 0 files). Removing it." >&2
  rm -f "$OUT_FILE"
  exit 1
fi

echo "Orderbook backup written to ${OUT_FILE} (${COUNT} files, $(du -h "$OUT_FILE" | cut -f1))"

find "$BACKUP_DIR" -name 'orderbook_*.tar.gz' -mtime "+${RETENTION_DAYS}" -delete

echo "Pruned orderbook backups older than ${RETENTION_DAYS} days"
