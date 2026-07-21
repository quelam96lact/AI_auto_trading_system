# Fix: Backfill Timeout (60s) — Lần thử 2026-07-21

## Vấn đề

Hôm nay (2026-07-21) thử Task 3 → collector bị timeout ở warm-up phase:
- Backfill "start" log → sau 60s → bị kill (không thấy "backfill done")
- Nguyên nhân: Fetch 365 ngày data từ SSI API quá chậm

## Root cause

`trading/collector/backfill.py:129`:
```python
frm = (last.astimezone(TZ).date() if last else today - timedelta(days=365))
```

Lần đầu chạy (DB empty) → fetch **365 ngày × 3 ký hiệu (VCB, HPG, TCB)** từ SSI API:
- Mỗi call throttle 0.25s
- Có pagination → nhiều call hơn
- **Tổng thời gian: 90-120 giây** ⚠️ vượt quá 60s timeout

## Giải pháp

### Sửa từ 365 → 7 ngày (cho Task 3)

**Lý do:** Task 3 là E2E verification **trong phiên giao dịch sống** (09:00-14:45), không cần 1 năm lịch sử. Chỉ cần:
- Backfill 7 ngày gần nhất (nhanh hơn, ~10-15 giây)
- Hoặc 0 ngày nếu DB đã có data

**File sửa:**
1. ✅ `trading/collector/backfill.py:129` — `timedelta(days=7)` thay vì `timedelta(days=365)`
2. ✅ `PROMPT_TASK_3.md:25` — Xóa credentials fake (SSI_USERNAME → SSI_CONSUMER_ID)
3. ✅ `PLAN_TASK_3.md:45-48` — Xóa credentials fake
4. ✅ `QUICKSTART_TASK_3.md:3` — Thêm note về fix

## Kết quả dự kiến sáng 2026-07-22

### Trước fix
```
docker compose up -d collector
# backfill start → [60s delay] → container killed
# uptime: 0 bars, 0 errors collected
```

### Sau fix
```
docker compose up -d collector
# backfill start → [10-15s delay] → backfill done, 7+ bars per symbol
# feed connected → first bars arrive by 09:05
```

## Test lại hôm nay (tối)?

Có thể test fix ngay bây giờ nếu muốn:
```bash
git add trading/collector/backfill.py PROMPT_TASK_3.md PLAN_TASK_3.md QUICKSTART_TASK_3.md
git commit -m "fix: backfill timeout — reduce range 365→7 days for Task 3"

docker compose down -v
docker compose up -d postgres nats
docker compose up -d collector

# Verify trong ~20 giây:
docker compose logs collector | grep -E "backfill done|ERROR"
# Expect: "backfill done" với counts, 0 errors
```

Nếu "backfill done" xuất hiện → fix thành công ✅

---

**Status:** Ready for 2026-07-22 09:00 execution
