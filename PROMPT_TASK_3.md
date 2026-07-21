# Prompt: Sub-project 1 Phase 2 Task 3 — E2E Verification (Live Trading)

**Dùng prompt này để gọi Claude Code vào sáng 2026-07-22 09:00 VN**

---

```
# E2E Verification: SSI Data Layer Live Trading

## Mục tiêu
Verify SSI data layer works end-to-end with REAL trading data today (2026-07-22, 09:00-14:45 VN).

Confirm:
- Collector receives real-time ticks from SSI FastConnect
- Parser (parse_message) handles B/MI messages correctly
- Data persists to PostgreSQL + publishes to NATS correctly
- Engine can subscribe bars without errors
- 0 parser errors over 6+ hour session

## Setup (before 09:00)

### 1. Verify environment
```bash
cat .env | grep -E "SSI_|NATS_"
# Must have: SSI_USERNAME=quelam96lact, SSI_PASSWORD=***, SSI_APP_ID=***, NATS_URL=nats://nats:4222
```

### 2. Fresh start
```bash
docker compose down -v
docker compose up -d postgres nats
sleep 5
docker compose ps
# Expect: postgres, nats = "Up"
```

### 3. Start collector
```bash
docker compose up -d collector
sleep 5
docker compose logs collector | head -30
# Look for: "Connected" or "Listening" message (no ERROR)
```

## Execution (09:00 - 14:45)

### Phase 1: Warm-up (09:00-09:30)
Verify system starts and first bars arrive.

**Actions:**
1. Monitor collector logs for first real-time tick
2. Wait for first bar close (09:05 at latest)
3. Verify bar appears in NATS
4. Verify bar appears in PostgreSQL

**Monitoring (open 3 terminals):**

Terminal A - Collector logs:
```bash
docker compose logs -f collector | grep -E "Tick|Bar emitted|ERROR|Connected"
```

Terminal B - NATS subscription:
```bash
nats sub bars.ssi.* --server nats://localhost:4222
# Should see JSON messages like:
# {"symbol":"VNM","close":78500,"volume":1000,"time":"2026-07-22T09:05:00+07:00","tradingDate":"2026-07-22"}
```

Terminal C - Database:
```bash
psql postgresql://postgres:postgres@localhost:5432/trading
# Then: SELECT symbol, time, close, volume FROM bars ORDER BY time DESC LIMIT 5;
```

**Success markers for Phase 1:**
- [ ] Collector log: "Connected to SSI" or similar initialization message
- [ ] NATS: ≥1 bar message received (symbol, close, volume, time fields)
- [ ] DB: ≥1 row in bars table with today's data
- [ ] Collector log: 0 ERROR or EXCEPTION messages

If any marker missing → check error messages and retry setup.

---

### Phase 2: Bar closure verification (09:30-14:45)
Verify complete bar lifecycle throughout trading session.

**Every bar close (XX:00, XX:05, XX:10, ... until 14:45):**

1. **Check collector emitted bar:**
   ```bash
   docker compose logs collector --tail=30 | grep "Bar emitted"
   # Expect: message like "Bar emitted: VNM close=78500 volume=500000"
   ```

2. **Verify NATS message received** (should appear within 1 second):
   ```bash
   # Watch Terminal B (NATS) for JSON message with correct symbol and close price
   ```

3. **Verify PostgreSQL updated** (within 2 seconds):
   ```bash
   psql postgresql://postgres:postgres@localhost:5432/trading -c \
     "SELECT symbol, time, open, high, low, close, volume FROM bars \
      WHERE time > NOW() - INTERVAL '1 minute' ORDER BY time DESC LIMIT 3;"
   # Expect: 3 rows (bars from last 3 symbols that just closed)
   ```

**Every 30 minutes: Cumulative stats**
```bash
psql postgresql://postgres:postgres@localhost:5432/trading -c \
  "SELECT symbol, COUNT(*) as bars_last_30min FROM bars \
   WHERE time > NOW() - INTERVAL '30 minutes' \
   GROUP BY symbol ORDER BY symbol;"

# Expected: ~6 bars per symbol (1 per 5 minutes)
# Example output:
# symbol | bars_last_30min
# -----+-----------
# ACB    |     6
# VNM    |     6
# etc.
```

**Continuous: Check for parser errors**
```bash
docker compose logs collector --tail=100 | grep -iE "ERROR|EXCEPTION|FATAL"

# Should output: (nothing, 0 errors)
# Unknown message types silently return None (by design)
```

**Latency check (at ~12:00, midday):**
```bash
# Compare timestamps to estimate latency:
# collector logs → NATS publish → DB insert

# Watch a single bar close event:
# 1. Note time in collector log: "Bar emitted: ... time=2026-07-22T12:00:00+07:00"
# 2. Check NATS message timestamp (should be ≤1s after)
# 3. Check DB timestamp (should be ≤2s after emitted)

# Expected: DB latency = emit_time to insert_time < 2 seconds
```

---

### Phase 3: Gap recovery test (optional, ~14:30)

**Only if you have time and want to test backfill:**

1. Stop collector mid-session:
   ```bash
   docker compose stop collector
   sleep 10
   ```

2. Check logs for backfill message:
   ```bash
   docker compose logs collector | grep -iE "backfill|gap|missing"
   # Should show: "Backfilled X bars from SSI API" or similar
   ```

3. Restart and watch recovery:
   ```bash
   docker compose up -d collector
   sleep 15
   docker compose logs collector | tail -50
   # Look for recovery/backfill completion message
   ```

4. Verify no duplicate bars after recovery:
   ```bash
   psql postgresql://postgres:postgres@localhost:5432/trading -c \
     "SELECT symbol, time, COUNT(*) as cnt FROM bars \
      WHERE DATE(time) = CURRENT_DATE \
      GROUP BY symbol, time HAVING COUNT(*) > 1 ORDER BY cnt DESC;"
   # Expected: (no rows = 0 duplicates)
   ```

✅ If gap filled automatically with no duplicates: backfill works!

---

## Success Criteria (all must be TRUE at 14:45)

- [ ] Collector uptime: 6+ hours without crash
- [ ] Bars collected: ≥1 bar per symbol (5 symbols minimum)
- [ ] Bar closures: Clean (no partial/stale bars in DB)
- [ ] Parser errors: Exactly 0 (grep "ERROR" in logs)
- [ ] NATS latency: ≤1 second from emission to publish
- [ ] DB latency: ≤2 seconds from emission to insert
- [ ] Bar timestamps: Consistent 5-minute intervals, no gaps
- [ ] Duplicate bars: Exactly 0 in database
- [ ] SSI connection: Stable (no reconnects after 09:05)

If ALL criteria TRUE → Task 3 complete ✅

---

## Troubleshooting

**Issue: Collector crashes immediately**
- Check `.env`: SSI_USERNAME, SSI_PASSWORD, SSI_APP_ID present
- Re-run: `docker compose up -d collector`
- Check logs: `docker compose logs collector`

**Issue: No bars arriving by 09:10**
- Check market status: Is trading actually happening?
- Verify SSI connection: `docker compose logs collector | grep -i "connected\|error"`
- Check NATS: `docker compose logs nats | tail -20`
- Try restart: `docker compose stop collector && sleep 2 && docker compose up -d collector`

**Issue: Parser errors in logs**
- Note the error message + message format
- Check if B/MI format changed: `docker compose logs collector | grep -i "error\|parse" | head -5`
- If new format: Run `uv run pytest tests/test_parser.py -v` to verify fixtures still valid
- Report issue with exact error

**Issue: High latency (>5 seconds)**
- Check network: `docker network ls` and verify connectivity
- Check NATS: `docker compose logs nats | tail -20`
- Check PostgreSQL: `docker compose logs postgres | tail -20`
- If persistent, may be system bottleneck (acceptable for today)

**Issue: Database locked or connection errors**
- Stop collector: `docker compose stop collector`
- Restart DB: `docker compose restart postgres`
- Wait 5 seconds
- Restart collector: `docker compose up -d collector`

---

## End-of-session (14:45+)

### 1. Collect metrics
```bash
# Total bars today
psql postgresql://postgres:postgres@localhost:5432/trading -c \
  "SELECT symbol, COUNT(*) as total_bars, MIN(time) as first, MAX(time) as last \
   FROM bars WHERE DATE(time) = CURRENT_DATE GROUP BY symbol ORDER BY symbol;"

# Check for duplicates (should be 0)
psql postgresql://postgres:postgres@localhost:5432/trading -c \
  "SELECT symbol, time, COUNT(*) as cnt FROM bars \
   WHERE DATE(time) = CURRENT_DATE GROUP BY symbol, time \
   HAVING COUNT(*) > 1;"

# Count errors in logs (should be 0)
docker compose logs collector | grep -ic "ERROR"
```

### 2. Document results
Note the following:
- Total bars collected (per symbol)
- Total parser errors (should = 0)
- Peak latency observed (collector → DB)
- Any anomalies or gaps
- Gap recovery tested? (yes/no + result)
- Session duration: 09:00-14:45 (6h 45min)

### 3. Commit Phase 2 Task 3
```bash
git add -A
git commit -m "feat: phase 2 task 3 — E2E verification (live trading)

- Live session: 2026-07-22 09:00-14:45 VN
- Collector uptime: 6h 45min (0 crashes)
- Bars collected: {TOTAL} across {SYMBOLS}
- Parser errors: 0 (all messages parsed correctly)
- NATS latency: {AVG}ms (max {PEAK}ms)
- DB latency: {AVG}ms (max {PEAK}ms)
- Duplicate bars: 0 (verified in DB)
- Gap recovery: [tested successfully / not tested]

Verified SSI data layer end-to-end. Ready for Phase 3.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

Then: `git log --oneline -3` to confirm commit

---

## Quick reference

Start fresh:
```bash
docker compose down -v && docker compose up -d postgres nats && sleep 5 && docker compose up -d collector
```

Monitor live:
```bash
# Terminal 1
docker compose logs -f collector | grep -E "Tick|Bar|ERROR"

# Terminal 2
nats sub bars.ssi.* --server nats://localhost:4222

# Terminal 3
watch "psql postgresql://postgres:postgres@localhost:5432/trading -c 'SELECT symbol, COUNT(*) FROM bars WHERE time > NOW() - INTERVAL \"10 min\" GROUP BY symbol;'"
```

Check status:
```bash
docker compose ps
docker compose logs collector | head -50
psql postgresql://postgres:postgres@localhost:5432/trading -c "SELECT COUNT(*) as total_bars FROM bars WHERE DATE(time) = CURRENT_DATE;"
```

---

## Questions before starting?

Check:
- [ ] PLAN_TASK_3.md read and understood?
- [ ] `.env` file has all SSI credentials (not fabricated)?
- [ ] Docker + PostgreSQL + NATS installed and working?
- [ ] Collector service can start (no port conflicts)?
- [ ] Market will be open 09:00-14:45 today?

If all YES → ready to execute at 09:00!
```

---

## Sử dụng ngay sáng mai

**Lúc 08:55 VN:**
```bash
# Trong Claude Code terminal, copy toàn bộ prompt trên (từ # E2E Verification... đến cuối)
# Gán vào một file hoặc paste trực tiếp vào Claude Code message
```

**Lúc 09:00:**
```bash
# Gọi Claude Code với prompt (hoặc /run để execute)
# Bắt đầu monitor 3 terminals: collector, NATS, PostgreSQL
```

**Lúc 14:45:**
```bash
# Khi market close, chạy metrics collection commands
# Commit kết quả
```

---

## Tải file sẵn sàng

- ✅ **PLAN_TASK_3.md** — Chi tiết full plan
- ✅ **PROMPT_TASK_3.md** — Prompt này (dùng với Claude Code)
- ✅ **tests/fixtures/** — Real fixtures from last session
- ✅ **trading/collector/parser.py** — Parser ready

Everything is ready. Just execute tomorrow morning! 🚀
