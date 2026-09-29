#!/usr/bin/env bash
# Bang cong viec cho lich tu chay. Mot cho duy nhat dinh nghia "job X chay lenh gi"
# — Windows Task Scheduler va cron Ubuntu deu goi qua day, khong ben nao chep
# lai chuoi lenh (bai hoc 4ea4c8d: mot cong thuc hai ban thi som muon lech).
#
#   scripts/sched.sh heartbeat
#   scripts/sched.sh daily-check
#   scripts/sched.sh backfill
#   scripts/sched.sh deploy-drift
#   scripts/sched.sh container-health
#   scripts/sched.sh engine-cam
#   scripts/sched.sh engine-consumer
#   scripts/sched.sh stream-health
#   scripts/sched.sh orderbook-recorder
#   scripts/sched.sh orderbook-daily-check
#   scripts/sched.sh backup
#   scripts/sched.sh backup-check
#   scripts/sched.sh orderbook-backup
#   scripts/sched.sh disk-check
#   scripts/sched.sh host-preflight
#
# Cong Docker nam trong run_if_docker_up.sh — xem file do.

set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="$REPO/scripts/run_if_docker_up.sh"

# cron tren Ubuntu chay voi PATH toi thieu (/usr/bin:/bin) — `uv` nam o
# /usr/local/bin se KHONG tim thay, job chet ngay dong dau ma log chi co mot
# dong "command not found". Them vao truoc cho chac; tren Windows/Git Bash
# duong dan nay khong ton tai nen vo hai.
export PATH="/usr/local/bin:$PATH"

# Cua so truot cho backfill hang dem: nap lai 7 ngay gan nhat thay vi --from
# cam cung. Cam cung thi khoang nap dai them mot ngay moi ngay, vinh vien
# (sau mot nam la 365 ngay x 175 ma moi dem).
#
# Cach skip cua backfill_universe.py chi so `attempted_until >= to` (dong 94-101),
# KHONG nhin `from`. He qua da kiem chung 01/09:
#   - Chay lai trong cung ngay  -> skip het (ok=0 skip=175). Re, dung y do.
#   - Hom sau `to` tien         -> chay lai tren ca cua so 7 ngay, nen mot phien
#                                  bi lo van duoc nap. UPSERT nen khong sinh
#                                  dong thua.
#
# GIOI HAN phai biet: cua so nay chi chiu duoc gian doan <= BACKFILL_DAYS ngay.
# Neu lich chet lau hon the (vi du may tat 2 tuan) thi phan hong o giua KHONG
# tu vá — phai chay tay mot lan voi --from rong hon. Doi so nay = doi do dai
# gian doan chiu duoc, khong phai doi do "ky" gi ca.
BACKFILL_DAYS=7

case "${1:-}" in
  heartbeat)
    exec "$RUN" heartbeat.log heartbeat-check \
      uv run python scripts/heartbeat_check.py
    ;;
  daily-check)
    exec "$RUN" daily-data-check.log daily-data-check \
      uv run python scripts/daily_data_check.py
    ;;
  backfill)
    exec "$RUN" backfill.log backfill \
      uv run python scripts/backfill_universe.py \
      --timeframe 1d \
      --from "$(date -d "$BACKFILL_DAYS days ago" +%F)" \
      --to "$(date +%F)" \
      --use-universe --sleep-ms 200
    ;;
  deploy-drift)
    exec "$RUN" deploy-drift.log deploy-drift \
      uv run python scripts/deploy_drift_check.py
    ;;
  container-health)
    exec "$RUN" container-health.log container-health \
      uv run python -m scripts.container_health_check
    ;;
  engine-cam)
    exec "$RUN" engine-cam.log engine-cam \
      uv run python scripts/check_silent_engine.py
    ;;
  engine-consumer)
    exec "$RUN" engine-consumer.log engine-consumer \
      uv run python scripts/engine_consumer_check.py
    ;;
  stream-health)
    shift || true
    exec "$RUN" stream-health.log stream-health \
      uv run python scripts/stream_health_check.py \
      --min-coverage-warn 0.90 \
      --min-coverage-crit 0.50 \
      "$@"
    ;;
  orderbook-recorder)
    shift || true
    exec "$RUN" orderbook-recorder.log orderbook-recorder \
      uv run python scripts/record_vn30f_orderbook.py \
      --until 14:46 \
      "$@"
    ;;
  orderbook-daily-check)
    shift || true
    exec "$RUN" orderbook-daily-check.log orderbook-daily-check \
      uv run python scripts/check_orderbook_daily.py \
      "$@"
    ;;
  backup)
    shift || true
  # Thu muc sao luu: tham so 1 neu co, khong thi de CHINH SCRIPT tu suy tu
  # TRADING_BACKUP_DIR (.env). KHONG suy o day: sched.sh chay TRUOC khi
  # run_if_docker_up.sh nap .env, nen o day chua thay bien do. Bia mac dinh
  # "/var/backups/trading-db" o day la nguyen nhan cua ba loi do that 29/09 tren
  # Windows: backup-check gui CANH BAO GIA moi ngay, disk-check thoat 2 va khong
  # he kiem dia, orderbook-backup chet vi "mkdir /var: Permission denied".
    exec "$RUN" backup.log backup \
      bash scripts/backup_db.sh "$@"
    ;;
  backup-check)
    shift || true
    # Tham so vi tri (khong bat dau bang -) doi thanh --backup-dir cho argparse.
    if [ $# -gt 0 ] && [[ "$1" != -* ]]; then
      set -- --backup-dir "$@"
    fi
    exec "$RUN" backup-check.log backup-check \
      uv run python scripts/backup_check.py "$@"
    ;;
  orderbook-backup)
    shift || true
    exec "$RUN" orderbook-backup.log orderbook-backup \
      bash scripts/backup_orderbook.sh "$@"
    ;;
  disk-check)
    shift || true
    if [ $# -gt 0 ] && [[ "$1" != -* ]]; then
      set -- --backup-dir "$@"
    fi
    exec "$RUN" disk-check.log disk-check \
      uv run python scripts/disk_check.py "$@"
    ;;
  host-preflight)
    shift || true
    exec "$RUN" host-preflight.log host-preflight       uv run python scripts/host_preflight.py "$@"
    ;;
  *)
    echo "dung: $0 {heartbeat|daily-check|backfill|deploy-drift|container-health|engine-cam|engine-consumer|stream-health|orderbook-recorder|orderbook-daily-check|backup|backup-check|orderbook-backup|disk-check|host-preflight}" >&2
    exit 2
    ;;
esac

