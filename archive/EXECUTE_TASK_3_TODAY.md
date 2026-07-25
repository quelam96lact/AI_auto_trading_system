# Plan: Task 3 Execution TODAY (2026-07-21)

**Ngày:** 2026-07-21 (hôm nay)  
**Giờ:** 10:30 VN (phiên giao dịch còn: 10:30-14:45 = 4h 15min)  
**Status:** 🔥 REAL-TIME execution với dữ liệu thật

---

## 🎯 Mục tiêu

Xác minh SSI data layer **end-to-end** với dữ liệu **live trading hôm nay**:
- Collector nhận real-time ticks từ SSI FastConnect
- Parser xử lý B/MI messages chính xác
- Data → PostgreSQL + NATS đúng format
- Engine subscribe bars mà không lỗi
- **0 parser errors** trong 4h+ giao dịch còn lại

---

## ⏱️ Timeline

| Giờ | Task | Expected |
|-----|------|----------|
| 10:30 | Start collector | Backfill done ~10:40 |
| 10:40 | Feed connected | "Connected to SSI" log |
| 10:45 | First bars | Real-time ticks flowing |
| 10:45-14:45 | Monitor | 4+ giờ continuous data |
| 14:45 | Market close | Collect metrics, commit |

---

## 📊 Phase 1: Setup (10:30-10:40)

### 1. Fresh start
```bash
docker compose down -v
docker compose up -d postgres nats
sleep 5
docker compose ps
# Expect: postgres, nats = "Up"
```

### 2. Start collector
```bash
docker compose up -d collector
sleep 2
docker compose logs collector | head -10
# Look for: "backfill start" ✓
```

### 3. Monitor logs (mở 3 terminal riêng)

**Terminal A: Collector logs**
```bash
docker compose logs -f collector | grep -E "backfill|Connected|ERROR|Bar emitted"
# Expected by 10:40: "backfill done" + "Connected" or similar
```

**Terminal B: NATS subscription**
```bash
nats sub bars.ssi.* --server nats://localhost:4222
# Expected 10:45+: JSON bar messages (symbol, close, volume, time)
```

**Terminal C: Database (query every 5 min)**
```bash
watch -n 300 "psql postgresql://trading:trading@localhost:5432/trading -c 'SELECT symbol, COUNT(*) as bars, MAX(time) as latest FROM bars WHERE time > NOW() - INTERVAL \"5 minutes\" GROUP BY symbol ORDER BY symbol;'"
```

### ✅ Warm-up success criteria (by 10:50)
- [ ] Backfill completed ("backfill done" log)
- [ ] Feed connected to SSI (log shows connection)
- [ ] First real-time ticks received (NATS has messages)
- [ ] DB has bars (at least 1 per symbol)
- [ ] 0 ERROR messages in logs

---

## 📈 Phase 2: Bar closure verification (10:50-14:45)

**Every 5 minutes (at XX:00, XX:05, XX:10, ...):**

### Kiểm tra 1: Collector log
```bash
docker compose logs collector --tail=20 | grep "Bar emitted"
# Expected: "Bar emitted: VCB close=123000 volume=50000" (or similar)
```

### Kiểm tra 2: NATS message
```bash
# Watch Terminal B — should see JSON with correct symbol + timestamp
# Example: {"symbol":"VCB","close":123000,"volume":50000,"time":"2026-07-21T10:45:00+07:00"}
```

### Kiểm tra 3: Database
```bash
psql postgresql://trading:trading@localhost:5432/trading -c \
  "SELECT symbol, time, open, high, low, close, volume FROM bars \
   WHERE time > NOW() - INTERVAL '1 minute' ORDER BY time DESC LIMIT 5;"
# Expected: 3-5 rows (last bar from each symbol that just closed)
```

### Kiểm tra 4: Error count (mỗi 30 phút)
```bash
docker compose logs collector --tail=200 | grep -ic "ERROR"
# Expected: 0 (or very small number)
```

### Kiểm tra 5: Bar consistency (mỗi giờ)
```bash
psql postgresql://trading:trading@localhost:5432/trading -c \
  "SELECT symbol, COUNT(*) as bar_count FROM bars \
   WHERE time > NOW() - INTERVAL '60 minutes' \
   GROUP BY symbol ORDER BY symbol;"
# Expected: ~12 bars per symbol (1 every 5 min, 60 min = 12 bars)
```

---

## 🔍 Phase 3: Deep verification (continuous)

### Latency check (lấy sample)
```bash
# At ~13:00 (midday), check latency on ONE bar close:
# 1. Note time in collector log: "Bar emitted: ... time=2026-07-21T13:00:00+07:00"
# 2. Check NATS publish time (should be ≤1s after)
# 3. Check DB insert time (should be ≤2s after)
# Document: emit_time → publish_time → insert_time
```

### Duplicate check (mỗi 2 giờ)
```bash
psql postgresql://trading:trading@localhost:5432/trading -c \
  "SELECT symbol, time, COUNT(*) FROM bars \
   WHERE DATE(time) = CURRENT_DATE \
   GROUP BY symbol, time HAVING COUNT(*) > 1;"
# Expected: (no rows = 0 duplicates)
```

### Parser error check (mỗi 1 giờ)
```bash
docker compose logs collector | grep -iE "ERROR|EXCEPTION|Parse" | tail -20
# Expected: 0 errors (unknown messages silently → None)
```

---

## ⚠️ Troubleshooting (if issues)

| Issue | Nguyên nhân | Fix |
|-------|-----------|-----|
| Collector crash | SSI cred invalid | Verify .env, restart |
| No bars by 10:50 | Feed not connected | Check collector logs for "Connected" |
| High latency (>5s) | Network/DB slow | Check docker resources, restart services |
| Parser errors | Unknown message type | Note message format, report |
| Duplicates in DB | Backfill overlap | Check backfill timestamps |

---

## 📋 Monitoring checklist

| Giờ | Kiểm tra | ✓ |
|-----|---------|---|
| 10:30 | Start | |
| 10:40 | Backfill done | |
| 10:45 | Feed connected | |
| 10:50 | First bars in DB | |
| 11:00 | Bar closure ✓ | |
| 11:05 | Latency <2s | |
| 12:00 | Error count = 0 | |
| 12:30 | Bar count ~18 per symbol | |
| 13:00 | Latency sample | |
| 13:30 | Duplicate check | |
| 14:00 | Final error check | |
| 14:45 | Market close | |

---

## 🎯 Success Criteria (phải ALL TRUE)

Sau 14:45, collect metrics:

```bash
# Total bars
psql postgresql://trading:trading@localhost:5432/trading -c \
  "SELECT symbol, COUNT(*) as total, MIN(time) as start, MAX(time) as end \
   FROM bars WHERE DATE(time) = CURRENT_DATE \
   GROUP BY symbol ORDER BY symbol;"

# Duplicates
psql postgresql://trading:trading@localhost:5432/trading -c \
  "SELECT COUNT(*) as duplicate_count FROM ( \
   SELECT symbol, time FROM bars WHERE DATE(time) = CURRENT_DATE \
   GROUP BY symbol, time HAVING COUNT(*) > 1) t;"

# Errors
docker compose logs collector | grep -ic "ERROR"

# Uptime
docker compose ps | grep collector
# Should show: "Up 4+ hours"
```

**Criteria:**
- [ ] Collector: 4+ hours uptime (0 crashes)
- [ ] Bars: 40+ per symbol (5-min intervals, 4h+ session)
- [ ] Parser errors: = 0
- [ ] Duplicate bars: = 0
- [ ] Latency: NATS <1s, DB <2s (samples)
- [ ] Feed: Stable connection (0 reconnects)

**Result: ALL TRUE → Task 3 ✅ PASSED**

---

## 📝 Commit sau 14:45

```bash
git add TEST_RESULT_2026_07_21.md # (or update)
git commit -m "feat: phase 2 task 3 — E2E verification complete (LIVE TRADING 2026-07-21)

Session: 2026-07-21 10:30-14:45 VN (~4h 15min)

Results:
- Collector uptime: 4+ hours (0 crashes)
- Bars collected: [TOTAL] across VCB/HPG/TCB
- Parser errors: 0 (all messages parsed correctly)
- Latency: NATS [AVG]ms, DB [AVG]ms
- Duplicates: 0 (verified in DB)

Phase 2 COMPLETE ✅
- Task 1: Fixtures (real 1813 B messages + 26 MI)
- Task 2: Parser (TDD verified, 5/5 tests pass)
- Task 3: E2E verification (live trading verified ✅)

Ready for Sub-project 2 or next phase.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

## 🚀 Start execution

**Bây giờ (10:30+):**

```bash
# Terminal 1: Setup + Collector
docker compose down -v
docker compose up -d postgres nats
sleep 5
docker compose up -d collector

# Terminal 2: Monitor collector
docker compose logs -f collector | grep -E "backfill|Connected|Bar|ERROR"

# Terminal 3: Monitor NATS
nats sub bars.ssi.* --server nats://localhost:4222

# Terminal 4: Monitor DB (every 5 min)
psql postgresql://trading:trading@localhost:5432/trading
# Then: SELECT COUNT(*) FROM bars;
```

---

## 💡 Notes

- Phiên giao dịch còn 4h 15min (10:30-14:45)
- **Enough time để verify end-to-end** ✅
- Real market data = **actual test** (không mock)
- Kết quả hôm nay sẽ là **proof of concept** cho Task 3

**Let's execute! 🔥**
