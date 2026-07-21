# Quick Start: Task 3 Execution (2026-07-22)

## 🟢 Before 09:00 (Setup 10 min)

```bash
# 1. Verify env (30 sec)
cat .env | grep -E "SSI_|NATS_"

# 2. Fresh start (5 min)
docker compose down -v
docker compose up -d postgres nats
sleep 5

# 3. Start collector (2 min)
docker compose up -d collector
sleep 5
docker compose logs collector | head -20
```

**✅ Success:** Collector shows "Connected" message, no ERROR

---

## 🔵 During trading (09:00-14:45)

### Watch in parallel (4 terminals)

**Terminal A:** Collector logs
```bash
docker compose logs -f collector | grep -E "Bar emitted|ERROR"
```

**Terminal B:** NATS messages
```bash
nats sub bars.ssi.* --server nats://localhost:4222
```

**Terminal C:** Database (every 5 min)
```bash
psql postgresql://postgres:postgres@localhost:5432/trading -c \
  "SELECT symbol, COUNT(*) FROM bars WHERE time > NOW() - INTERVAL '5 min' GROUP BY symbol;"
```

**Terminal D:** Error check (every 30 min)
```bash
docker compose logs collector --tail=100 | grep -ic "ERROR"
# Should output: 0
```

---

## 🟠 Checklist during session

**Every bar close (XX:00, XX:05, XX:10, ...):**
- [ ] Collector shows "Bar emitted"
- [ ] NATS shows JSON message
- [ ] DB query returns recent bars

**Every 30 minutes:**
- [ ] Error count = 0
- [ ] Bar count consistent (~6 per symbol)

**If issues found:**
- Document timestamp + error message
- Check PLAN_TASK_3.md troubleshooting section

---

## 🔴 After 14:45 (Verify & Commit 5 min)

```bash
# 1. Final metrics
psql postgresql://postgres:postgres@localhost:5432/trading -c \
  "SELECT symbol, COUNT(*) as bars, MIN(time) as start, MAX(time) as end \
   FROM bars WHERE DATE(time) = CURRENT_DATE GROUP BY symbol;"

# 2. Check duplicates (should be 0)
psql postgresql://postgres:postgres@localhost:5432/trading -c \
  "SELECT COUNT(*) as duplicate_bars FROM ( \
   SELECT symbol, time, COUNT(*) FROM bars WHERE DATE(time) = CURRENT_DATE \
   GROUP BY symbol, time HAVING COUNT(*) > 1) t;"

# 3. Check errors (should be 0)
docker compose logs collector | grep -ic "ERROR"

# 4. Commit
git add PLAN_TASK_3.md PROMPT_TASK_3.md
git commit -m "feat: phase 2 task 3 — E2E verification complete

- Session: 2026-07-22 09:00-14:45
- Bars: [TOTAL] collected
- Errors: 0
- Status: ✅ PASSED

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

## 📋 Success Criteria (all must be TRUE)

- [ ] Collector: 6+ hours, 0 crashes
- [ ] Bars: ≥ 1 per symbol
- [ ] Errors: Exactly 0
- [ ] Latency: NATS <1s, DB <2s
- [ ] Duplicates: Exactly 0
- [ ] Timestamps: 5-min intervals, no gaps

**Result:** If all checked → Task 3 ✅ DONE

---

## 🆘 Common fixes

| Problem | Fix |
|---------|-----|
| Collector won't start | Check `.env` SSI credentials + `docker compose logs collector` |
| No bars arriving | Market open? Check `docker compose logs collector` for "Connected" |
| Parser errors | See PLAN_TASK_3.md troubleshooting |
| High latency | Check Docker network + restart services |
| DB locked | `docker compose restart postgres` |

**Full details:** See PLAN_TASK_3.md

---

## 📁 Files ready

- ✅ PLAN_TASK_3.md (detailed plan + criteria)
- ✅ PROMPT_TASK_3.md (full prompt for Claude Code)
- ✅ QUICKSTART_TASK_3.md (this file)
- ✅ Parser + fixtures (code ready)
- ✅ Collector service (ready)
- ✅ Docker setup (ready)

**Just execute at 09:00!** 🚀

