# Plan: Sub-project 1 Phase 2 Task 3 — E2E Verification (Live Trading)

**Date:** 2026-07-22 (Tuesday)  
**Time:** 09:00 - 14:45 VN (Asia/Ho_Chi_Minh)  
**Status:** ⏸️ Awaiting trading session

---

## Mục tiêu chính

Xác minh SSI data layer hoạt động **end-to-end** với dữ liệu **thực tế** từ phiên giao dịch sống:

1. ✅ Collector nhận real-time ticks từ SSI FastConnect API
2. ✅ Parser (`parse_message`) xử lý B/MI messages **chính xác**
3. ✅ Dữ liệu persist vào PostgreSQL + publish lên NATS đúng format
4. ✅ Engine subscribe bars từ NATS mà không lỗi
5. ✅ 0 parser errors trong 6+ giờ giao dịch

---

## Success Criteria (tất cả phải TRUE)

| Tiêu chí | Giá trị mong đợi | Cách kiểm tra |
|----------|-----------------|--------------|
| Collector không crash | Uptime 6+ giờ | `docker compose ps` |
| Bars collected | ≥ 1 bar/symbol | `SELECT COUNT(*) FROM bars` |
| Bar closure | Đóng sạch | No partial/stale bars in logs |
| Parser errors | = 0 | `docker compose logs collector \| grep -i error` |
| NATS latency | ≤ 1 giây | Monitor NATS logs |
| DB latency | ≤ 2 giây | Compare timestamps |
| Bar consistency | 5-min intervals, no gaps | `SELECT * FROM bars ORDER BY time` |
| Duplicate bars | = 0 | `SELECT symbol, time, COUNT(*) FROM bars GROUP BY symbol, time HAVING COUNT(*) > 1` |
| SSI credentials | Valid | `.env` SSI_USERNAME = quelam96lact |

---

## Chuẩn bị (trước 09:00)

### 1. Verify environment
```bash
# Check .env có đủ credentials
cat .env | grep -E "SSI_|NATS_"

# Expected:
# SSI_USERNAME=quelam96lact
# SSI_PASSWORD=***
# SSI_APP_ID=***
# NATS_URL=nats://nats:4222
```

### 2. Fresh start (xóa DB cũ)
```bash
# DEV ONLY - xóa tất cả data cũ
docker compose down -v

# Start infrastructure
docker compose up -d postgres nats

# Verify healthy (cho ~5-10 giây)
docker compose ps
# Expected: postgres, nats = "Up"
```

### 3. Start collector
```bash
docker compose up -d collector

# Verify connected to SSI (trong 30 giây)
docker compose logs collector | grep -E "Connected|Listening|ERROR"
```

---

## Triển khai (09:00 - 14:45 VN)

### Phase 1: Warm-up (09:00 - 09:30)
**Verify system starts + first bars arrive**

**Actions:**
1. Monitor collector connection to SSI
2. Wait for first real-time tick → first bar close
3. Verify bar in NATS + PostgreSQL

**Verification:**
```bash
# Terminal 1: Watch collector logs
docker compose logs -f collector | grep -E "Tick|Bar emitted|ERROR"

# Terminal 2: Watch NATS
nats sub bars.ssi.* --server nats://localhost:4222 2>/dev/null | head -10

# Terminal 3: Check DB
psql postgresql://postgres:postgres@localhost:5432/trading \
  -c "SELECT symbol, time, close, volume FROM bars ORDER BY time DESC LIMIT 5;"
```

**Success markers:**
- [ ] Collector log shows "Connected to SSI" or similar
- [ ] ≥ 1 bar message in NATS (`bars.ssi.{symbol}`)
- [ ] ≥ 1 row in PostgreSQL bars table

---

### Phase 2: Bar closure verification (09:30 - 14:45)
**Verify complete bar lifecycle throughout session**

**Every bar close (XX:00, XX:05, XX:10, ...):**

1. **Verify bar emitted** (collector log):
   ```bash
   # Look for: "Bar emitted: {symbol} close={price}"
   docker compose logs collector --tail=20 | grep "Bar emitted"
   ```

2. **Verify NATS message** (within 1 second):
   ```bash
   # Should see JSON: {"symbol":"...", "close":..., "volume":..., "time":"..."}
   ```

3. **Verify PostgreSQL write** (within 2 seconds):
   ```bash
   psql postgresql://postgres:postgres@localhost:5432/trading \
     -c "SELECT symbol, time, open, high, low, close, volume FROM bars \
         WHERE time > NOW() - INTERVAL '1 minute' ORDER BY time DESC;"
   ```

**Every 30 minutes: Check cumulative stats**
```bash
psql postgresql://postgres:postgres@localhost:5432/trading \
  -c "SELECT symbol, COUNT(*) as bar_count, MIN(time) as first_bar, MAX(time) as latest_bar \
      FROM bars WHERE time > NOW() - INTERVAL '30 minutes' \
      GROUP BY symbol ORDER BY symbol;"

# Expected: ~6 bars per symbol per 30 min (1 bar every 5 min)
```

**Continuous: Monitor for errors**
```bash
docker compose logs collector --tail=50 | grep -iE "ERROR|EXCEPTION|FATAL"

# Expected: 0 errors (unknown messages silently → None)
```

---

### Phase 3: Gap recovery test (optional, ~14:30)

**If missing bars detected:**

1. Stop collector mid-session:
   ```bash
   docker compose stop collector
   ```

2. Check backfill triggered:
   ```bash
   docker compose logs collector | grep -iE "backfill|gap"
   ```

3. Restart + monitor recovery:
   ```bash
   docker compose up -d collector
   sleep 10
   docker compose logs collector | tail -50
   # Look for: "Backfilled X bars from SSI API"
   ```

4. Verify no duplicates:
   ```bash
   psql postgresql://postgres:postgres@localhost:5432/trading \
     -c "SELECT symbol, time, COUNT(*) as cnt FROM bars \
         GROUP BY symbol, time HAVING COUNT(*) > 1;"
   # Expected: 0 rows
   ```

---

## Monitoring dashboard (real-time)

Open 4 terminals in parallel:

| Terminal | Command | Purpose |
|----------|---------|---------|
| 1 | `docker compose logs -f collector` | Watch collector (ticks, bars, errors) |
| 2 | `nats sub bars.ssi.* --server nats://localhost:4222` | Watch NATS messages live |
| 3 | Watch PostgreSQL (query every 5 min) | Track DB writes |
| 4 | Note timestamps | Manual verification of latency |

---

## Common issues & fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| Collector crashes immediately | SSI cred invalid | Verify `.env`, re-run collector |
| No bars arriving | SSI halted or no trading | Check market status, wait |
| Parser errors in logs | Unknown message type | Check collector logs, report with message format |
| High latency (>5 sec) | Network delay | Check Docker network, NATS health |
| Duplicate bars | Backfill overlap | Check backfill logic (no overlaps) |
| NATS not running | Service didn't start | `docker compose logs nats`, restart |

---

## End-of-session summary

**After 14:45 (market close):**

1. **Collect metrics:**
   ```bash
   # Total bars collected
   psql postgresql://postgres:postgres@localhost:5432/trading \
     -c "SELECT symbol, COUNT(*) as total_bars, \
            MIN(time) as session_start, MAX(time) as session_end \
         FROM bars WHERE DATE(time) = CURRENT_DATE \
         GROUP BY symbol ORDER BY symbol;"
   
   # Check for duplicates (should be 0)
   psql postgresql://postgres:postgres@localhost:5432/trading \
     -c "SELECT symbol, time, COUNT(*) FROM bars \
         WHERE DATE(time) = CURRENT_DATE \
         GROUP BY symbol, time HAVING COUNT(*) > 1;"
   
   # Parser errors (should be 0)
   docker compose logs collector | grep -ic "ERROR"
   ```

2. **Document results:**
   - Total bars per symbol
   - Parser errors (should = 0)
   - Latency samples (collector → NATS → DB)
   - Any anomalies or gaps
   - Gap recovery test result (if run)

3. **Commit Phase 2 Task 3:**
   ```bash
   git add -A
   git commit -m "feat: phase 2 task 3 — E2E verification (live trading)
   
   - Verified collector live for 6+ hours
   - Collected X bars across Y symbols
   - Parser 0 errors, bars closed cleanly
   - NATS latency: <1s, DB latency: <2s
   - No duplicate bars
   - Gap recovery: [tested/not tested]
   
   Session: 2026-07-22 09:00-14:45 VN
   
   Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
   ```

---

## Next steps after Task 3

- **✅ Phase 2 complete** (fixtures + parser + E2E verified)
- **→ Sub-project 2** (if applicable) or **Phase 3** (next feature)
- Archive this plan + results for post-mortem

---

## Quick reference

| Command | Purpose |
|---------|---------|
| `docker compose up -d collector` | Start collector |
| `docker compose logs -f collector` | Watch logs |
| `docker compose stop collector` | Stop (for backfill test) |
| `nats sub bars.ssi.* --server nats://localhost:4222` | Subscribe NATS |
| `psql postgresql://postgres:postgres@localhost:5432/trading` | Connect DB |
| `SELECT COUNT(*) FROM bars;` | Total bars |
| `SELECT DISTINCT symbol FROM bars;` | Symbols traded |

