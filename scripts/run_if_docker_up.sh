#!/usr/bin/env bash
# Chay mot script giam sat CHI KHI stack docker dang len.
#
# Ly do ton tai: 3 scheduled task (heartbeat 5 phut/lan, daily-data-check,
# backfill) truoc day chay vo dieu kien. Khi may bat len ma Docker Desktop
# chua khoi dong, chung no van chay, van bat cua so, van do loi ket noi DB
# vao log — tieng on che mat cai bao that. Doi lai: khong bao gio "im lang"
# — moi lan bo qua deu ghi mot dong SKIP vao dung file log do.
#
# Dung chung cho Windows Task Scheduler VA cron Ubuntu (xem DEPLOYMENT.md).
#
# Cach dung:
#   scripts/run_if_docker_up.sh <ten-file-log> <nhan> <lenh...>
# Vi du:
#   scripts/run_if_docker_up.sh heartbeat.log heartbeat-check \
#       uv run python scripts/heartbeat_check.py

set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 0

LOG="$REPO/logs/$1"
LABEL="$2"
shift 2

mkdir -p "$REPO/logs"

# Moc kiem: postgres — khong co no thi moi script giam sat deu vo nghia.
if ! docker ps -q \
    --filter name=ai_auto_trading_system-postgres-1 \
    --filter status=running 2>/dev/null | grep -q .; then
  date "+%Y-%m-%d %H:%M:%S $LABEL SKIP: docker chua chay" >> "$LOG"
  exit 0
fi

if [ ! -f "$REPO/.env" ]; then
  date "+%Y-%m-%d %H:%M:%S $LABEL SKIP: khong tim thay .env" >> "$LOG"
  exit 0
fi

date "+%Y-%m-%d %H:%M:%S $LABEL start" >> "$LOG"

set -a
# shellcheck disable=SC1091
. ./.env
set +a
# localhost tren may Windows nay ra IPv6 truoc, treo ~30s moi lan ket noi.
export DB_DSN="${DB_DSN//localhost/127.0.0.1}"

"$@" >> "$LOG" 2>&1
echo "EXIT=$?" >> "$LOG"
