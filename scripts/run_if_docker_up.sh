#!/usr/bin/env bash
# Chay mot script giam sat CHI KHI stack docker dang len.
#
# Ly do ton tai: 3 scheduled task (heartbeat 5 phut/lan, daily-data-check,
# backfill) truoc day chay vo dieu kien. Khi may bat len ma Docker Desktop
# chua khoi dong, chung no van chay, van bat cua so, van do loi ket noi DB
# vao log — tieng on che mat cai bao that. Doi lai: khong bao gio "im lang"
# — moi lan bo qua deu ghi mot dong SKIP vao dung file log do.
#
# Brief dot 8 (02/09/2026): im lang cua nhanh Docker-chet la NGuy HIEM —
# Docker tat ca ngay ma khong mot tin Telegram nao (85 lan SKIP lien tiep,
# do duoc 02/09). Nhanh do bay gio goi them scripts/docker_down_alert.py,
# tu quyet dinh co keu khong (khung gio, ngay le, chong spam). Và `.env`
# phai nap TRUOC kiem Docker: nhanh nay can TELEGRAM_BOT_TOKEN de gui —
# truoc day nap sau kiem, token chua ton tai khi Docker chet.
#
# Dung chung cho Windows Task Scheduler VA cron Ubuntu (xem DEPLOYMENT.md).
#
# Cach dung:
#   scripts/run_if_docker_up.sh <ten-file-log> <nhan> <lenh...>
# Vi du:
#   scripts/run_if_docker_up.sh heartbeat.log heartbeat-check \
#       uv run python scripts/heartbeat_check.py
#
# De kiem chung nhanh Docker-chet ma khong can tat Docker that (brief dot 8):
#   DOCKER_GATE_CONTAINER=khong-ton-tai scripts/run_if_docker_up.sh \
#       test-gate.log test-gate echo hi

set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 0

LOG="$REPO/logs/$1"
LABEL="$2"
shift 2

mkdir -p "$REPO/logs"

# Xoay log theo kich thuoc TRUOC khi ghi dong nao (brief agent B phan 1).
# Mot cong thuc mot noi: Windows Task Scheduler VA cron Ubuntu deu goi job qua
# file nay, nen log_rotate.sh source o day la du cho ca hai ben — khong viet
# ban Ubuntu rieng (4ea4c8d). Xoay hong khong bao gio duoc chan ghi log:
# rotate_log tu nuot moi loi (xem file do).
# shellcheck disable=SC1091
. "$REPO/scripts/log_rotate.sh"
rotate_log "$LOG"

# 1. .env phai co — khong co thi khong co gi de chay ca (ke ca docker_down_alert
# can token de gui). Giu nguyen hanh vi cu.
if [ ! -f "$REPO/.env" ]; then
  date "+%Y-%m-%d %H:%M:%S $LABEL SKIP: khong tim thay .env" >> "$LOG"
  exit 0
fi

# 2. Nap .env TRUOC kiem Docker (brief dot 8): nhanh Docker-chet goi
# docker_down_alert.py can TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID. Truoc day nap
# sau kiem nen nhanh chet thoat truoc khi token ton tai — send_telegram lang
# le return (gui hut khong bao loi).
set -a
# shellcheck disable=SC1091
. ./.env
set +a
# localhost tren may Windows nay ra IPv6 truoc, treo ~30s moi lan ket noi.
export DB_DSN="${DB_DSN//localhost/127.0.0.1}"

# 3. Stdout o day LUON chuyen huong ra file, nen Python khong doan duoc encoding
# va tren Windows chon cp1252. Moi script trong dam nay deu in tieng Viet: mot
# ky tu ngoai cp1252 (vd "d" trong "du lieu") lam UnicodeEncodeError giet ca
# tien trinh. Da xay ra that 01/09: heartbeat_check chet 5 lan lien, khong gui
# duoc canh bao nao dung luc feed dang chet.
export PYTHONIOENCODING=utf-8

# 4. Moc kiem: postgres — khong co no thi moi script giam sat deu vo nghia.
# Ten container doc tu DOCKER_GATE_CONTAINER (mac dinh postgres) de kiem chung
# duoc nhanh Docker-chet ma khong phai tat Docker that (brief dot 8).
GATE_CONTAINER="${DOCKER_GATE_CONTAINER:-ai_auto_trading_system-postgres-1}"
if ! docker ps -q \
    --filter name="$GATE_CONTAINER" \
    --filter status=running 2>/dev/null | grep -q .; then
  date "+%Y-%m-%d %H:%M:%S $LABEL SKIP: docker chua chay" >> "$LOG"
  # Docker chet trong gio giao dich khong duoc im lang (brief dot 8).
  # docker_down_alert.py tu quyet dinh co keu khong — luc nay .env da nap
  # nen token co san. Ket qua ghi cung vao file log nay.
  # Chay bang `python -m` (KHONG phai `python scripts/x.py`): script import
  # scripts.heartbeat_check nen can repo root trong sys.path — script mode
  # dat sys.path[0] = scripts/ nen `import scripts.*` se ModuleNotFoundError.
  uv run python -m scripts.docker_down_alert >> "$LOG" 2>&1
  echo "ALERT_EXIT=$?" >> "$LOG"
  exit 0
fi

date "+%Y-%m-%d %H:%M:%S $LABEL start" >> "$LOG"

"$@" >> "$LOG" 2>&1
echo "EXIT=$?" >> "$LOG"
