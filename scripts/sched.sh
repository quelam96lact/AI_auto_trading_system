#!/usr/bin/env bash
# Bang cong viec cho lich tu chay. Mot cho duy nhat dinh nghia "job X chay lenh gi"
# — Windows Task Scheduler va cron Ubuntu deu goi qua day, khong ben nao chep
# lai chuoi lenh (bai hoc 4ea4c8d: mot cong thuc hai ban thi som muon lech).
#
#   scripts/sched.sh heartbeat
#   scripts/sched.sh daily-check
#   scripts/sched.sh backfill
#   scripts/sched.sh deploy-drift
#   scripts/sched.sh engine-cam
#   scripts/sched.sh engine-consumer
#   scripts/sched.sh stream-health
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
  *)
    echo "dung: $0 {heartbeat|daily-check|backfill|deploy-drift|engine-cam|engine-consumer|stream-health}" >&2
    exit 2
    ;;
esac
