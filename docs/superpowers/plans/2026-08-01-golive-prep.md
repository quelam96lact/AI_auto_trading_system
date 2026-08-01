# Go-Live Prep (Backfill Fix, Deployment Hardening, Derivative Monitoring) Implementation Plan

> **Status: RETROSPECTIVE — all 3 tasks below were already implemented and
> tested in this session before this plan document was written.** All
> checkboxes are checked to reflect that. This doc exists for traceability
> (the user asked "Plan đâu" after the work was done), not as a forward
> execution plan. No subagent/inline execution handoff applies.
>
> For agentic workers reading this later as a template: if similar work is
> ever re-derived from scratch, use superpowers:subagent-driven-development
> or superpowers:executing-plans to run it task-by-task.

**Goal:** Address 3 of the 4 unimplemented-plan items identified in the
2026-08-01 go-live audit (task `t-fzy7p8ne7yehc`): a real backfill data-loss
bug, missing deployment docs/hardening, and read-only derivative account
monitoring. The 4th item (index streaming) was explicitly declined — see
"Out of scope" at the end.

**Architecture:** Each task is independent and touches a distinct part of the
stack (collector backfill logic, deploy/ops config, a new collector sync
module). No task depends on another.

**Tech Stack:** Python 3.11, pytest (+pytest-asyncio), Postgres/TimescaleDB,
ssi-sdk (AsyncPortfolioService), Docker Compose, Grafana.

## Global Constraints

- TDD: write a failing test before any fix (per this repo's CLAUDE.md
  conventions and prior commit history, e.g. `95f563f`).
- Surgical scope: only touch files listed per task; don't refactor adjacent
  code.
- No guessing SSI SDK behavior — verify field names/shapes against the
  installed `ssi_sdk` package or prior confirmed spike results, never invent.
- Run `uv run pytest -q -m "not integration"` after every task; must stay
  green with no regressions.
- `grep -rn "place_order|cancel_order|modify_order|AsyncTrading"` over any
  new collector code must stay empty — these are read-only/data tasks.

---

### Task 1: Fix production OHLC backfill pagination bug

**Files:**
- Modify: `trading/collector/backfill.py:234-252` (`SSIRestClient._paged_intraday`)
- Test: `tests/test_backfill.py`

**Interfaces:**
- Consumes: nothing new — `_paged_intraday(self, data, symbol: str, frm: date, to: date)` keeps its existing signature and return type (`list[OHLCData]`, un-bucketed), called by `intraday_ohlc()`.
- Produces: same return type as before; no other file depends on the internal implementation.

**Background:** `get_ohlc_5minute_historical`'s `page` parameter is not a real
OFFSET cursor (confirmed real in commit `95f563f`) — increasing `page` over a
single wide date range mostly re-returns the same newest-data window instead
of advancing to older data, silently dropping the oldest requested bars.

- [x] **Step 1: Write the failing regression test**

Added to `tests/test_backfill.py`: `FakeMarketData` that mimics the confirmed
real defect — for any single call spanning >7 days it ignores `page` and
returns the same newest-`size` window (finite via a 2-call cap so the test
terminates); for a <=7-day window it returns the correctly filtered data.

```python
async def test_paged_intraday_dedupes_when_ssi_page_index_overlaps():
    symbol = "VCB"
    days = [date(2026, 7, 1) + timedelta(days=i) for i in range(20)]
    rows = _gen_ohlc_rows(symbol, days, per_day=60)  # 1200 rows: 60/day x 20 days
    fake_data = FakeMarketData(rows)

    client = SSIRestClient.__new__(SSIRestClient)  # no real cfg/storage needed
    result = await client._paged_intraday(fake_data, symbol, days[0], days[-1])

    got_dates = {r.trading_date for r in result}
    expected_dates = {r.trading_date for r in rows}
    assert got_dates == expected_dates
    assert rows[0].trading_date in got_dates
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_backfill.py::test_paged_intraday_dedupes_when_ssi_page_index_overlaps -v`
Result: FAILED — `mat 200 ban ghi` (200 of the oldest records missing),
confirming the bug reproduces on this exact production code path.

- [x] **Step 3: Fix `_paged_intraday` — day-chunking + dedupe**

```python
async def _paged_intraday(self, data, symbol: str, frm: date, to: date):
    size = 1000
    by_ts: dict[str, object] = {}
    chunk_start = frm
    while chunk_start <= to:
        chunk_end = min(chunk_start + timedelta(days=6), to)
        rows = await data.market_data.get_ohlc_5minute_historical(
            symbol,
            self._fmt_intraday(chunk_start, end_of_day=False),
            self._fmt_intraday(chunk_end, end_of_day=True),
            page=1,
            size=size,
        )
        for r in rows:
            by_ts[r.trading_date] = r
        chunk_start = chunk_end + timedelta(days=1)
    return list(by_ts.values())
```

- [x] **Step 4: Run test to verify it passes, then full suite**

Run: `uv run pytest tests/test_backfill.py -v` → 4/4 passed.
Run: `uv run pytest -q -m "not integration"` → 84/84 passed at this point.

- [x] **Step 5: Commit** (not done — user has not asked for a commit yet;
  changes are staged in the working tree only)

---

### Task 2: Deployment hardening

**Files:**
- Create: `README.md`, `DEPLOYMENT.md`, `.env.example`, `scripts/backup_db.sh`
- Modify: `docker-compose.yml`, `DEPLOYMENT_READINESS.md`

**Interfaces:**
- Consumes: env var names already required by `trading/config.py:39-48`
  (`DB_DSN`, `SSI_CONSUMER_ID`, `SSI_CONSUMER_SECRET`, `SSI_API_KEY`,
  `SSI_API_SECRET`, `SSI_PRIVATE_KEY`) and `trading/telegram.py:9-10`
  (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
- Produces: no code interfaces — these are docs/ops config only.

- [x] **Step 1: `.env.example`** — template listing every env var above with
  no real values, matching `trading/config.py`'s required set exactly.

- [x] **Step 2: Fix a real deploy blocker found while doing this** —
  `docker-compose.yml`'s `engine` service only injected `SSI_PRIVATE_KEY`;
  `trading/config.py:44-47` requires `SSI_CONSUMER_ID/SECRET/API_KEY/API_SECRET`
  unconditionally (`os.environ[...]`, no default) — engine would crash on
  startup with `KeyError`. `collector` was likewise missing `SSI_PRIVATE_KEY`.
  Neither service passed through `TELEGRAM_BOT_TOKEN/CHAT_ID`, so Telegram
  alerts were silently dead in the dockerized deployment. Added all of these
  to both services' `environment:` blocks.

- [x] **Step 3: Harden `docker-compose.yml` network/resource exposure** —
  bound `postgres`/`nats` ports to `127.0.0.1` only (were open on all
  interfaces); added `mem_limit`/`cpus` to every service.

  Verify: `docker compose config -q` — must parse with only the expected
  "TELEGRAM_* not set" warnings (values come from `.env` on a real host).

- [x] **Step 4: `scripts/backup_db.sh`** — `pg_dump` via `docker compose exec`,
  gzip, prune backups older than `BACKUP_RETENTION_DAYS` (default 14 days),
  intended for cron.

- [x] **Step 5: `README.md` + `DEPLOYMENT.md`** — setup instructions, Ubuntu
  VPS deployment guide (firewall, nginx/TLS steps requiring a real domain the
  project doesn't have yet, backup cron wiring, log rotation, resource limits
  section referencing Step 3's values).

- [x] **Step 6: Update `DEPLOYMENT_READINESS.md`** — added a dated "Update —
  2026-08-01" section noting which previously-"Missing" checklist items are
  now done, so the doc doesn't contradict the repo state.

- [x] **Step 7: Commit** (not done — pending user request)

---

### Task 3: Derivative account monitoring (Phase 1 of `PLAN_DERIVATIVE_TRADING.md`)

Full design already recorded separately at
`docs/superpowers/specs/2026-08-01-derivative-monitoring-design.md` (written
during brainstorming, approved by the user before implementation). Summarized
here for the plan-doc trail:

**Files:**
- Create: `trading/collector/derivative_sync.py`, `tests/test_derivative_sync.py`
- Modify: `trading/config.py`, `config/config.yaml`, `trading/storage/schema.sql`,
  `trading/storage/db.py`, `trading/collector/main.py`,
  `grafana/provisioning/dashboards/trading.json`, `tests/test_dashboard_queries.py`

**Interfaces:**
- Produces: `sync_derivative_data(cfg: Config, storage: Storage) -> None`,
  wired into `housekeeping()` in `trading/collector/main.py` on the same
  5-minute cadence as `sync_account_data`. Pure helper
  `margin_alert_level(rc_call: bool, account_ratio_ssi: float,
  account_ratio_vsdc: float, level1: float, level2: float, level3: float) ->
  str | None` returns `"CRITICAL"`, `"WARN"`, or `None`.
- `Storage` gains `save_derivative_balance(**kwargs)`,
  `save_derivative_margin(**kwargs)`,
  `save_derivative_positions(account_no, ts, positions: list[dict])`.

- [x] **Step 1: Config field** — `Config.ssi_derivative_account: str = ""`
  (empty = sync disabled), set to `"0434228"` in `config/config.yaml`
  (account confirmed real in `PLAN_DERIVATIVE_TRADING.md` Phase 0).

- [x] **Step 2: Schema** — 3 new tables in `trading/storage/schema.sql`:
  `derivative_balance_snapshot`, `derivative_margin_snapshot`,
  `derivative_position_snapshot` (field names taken from
  `dataclasses.fields()` on the installed `ssi_sdk.models.portfolio`
  classes, not guessed).

- [x] **Step 3: `Storage` methods** — `save_derivative_balance/_margin/_positions`,
  same `ON CONFLICT (...) DO UPDATE` pattern as the existing
  `save_account_balance/_positions`.

- [x] **Step 4: Write failing tests, then `derivative_sync.py`** —
  `tests/test_derivative_sync.py` covers: balance field mapping, margin
  snapshot write + no alert below thresholds, `CRITICAL` alert on `rc_call`,
  and the confirmed SDK bug (`get_derivative_positions()` returns a single
  `AllDerivativePosition` object, not a list — must unpack
  `.open_positions`). Plus a pure unit test of `margin_alert_level` at every
  threshold boundary.

```python
def test_margin_alert_level_thresholds():
    m = derivative_sync.margin_alert_level
    assert m(False, 50, 50, 85, 90, 95) is None
    assert m(False, 86, 50, 85, 90, 95) == "WARN"
    assert m(False, 50, 96, 85, 90, 95) == "CRITICAL"
    assert m(True, 0, 0, 85, 90, 95) == "CRITICAL"
```

  Run: `uv run pytest tests/test_derivative_sync.py -v` → 5/5 passed.

- [x] **Step 5: Wire into `housekeeping()`** in `trading/collector/main.py`,
  same try/except-and-WARN-alert pattern as the existing account sync call
  (a derivative sync failure must not kill the collector loop).

- [x] **Step 6: Grafana panel** — "Derivative Margin" table panel added to
  `grafana/provisioning/dashboards/trading.json`, joining the balance+margin
  snapshots on `(account_no, ts)`, using the same "latest per account_no"
  pattern the existing "Real Positions" panel uses (avoids the stale-row bug
  documented in `PLAN_ACCOUNT_DATA_SYNC.md`).

- [x] **Step 7: Integration test for the panel query** — added
  `test_derivative_margin_panel_query` to `tests/test_dashboard_queries.py`,
  matching the existing panel-query test convention. **Not executed** — no
  local Postgres/Docker available in this session's sandbox. Needs to be run
  once a real DB is reachable, before this is considered fully verified.

- [x] **Step 8: Safety check** — `grep -rn "place_order|cancel_order|modify_order|AsyncTrading" trading/collector/derivative_sync.py` → empty. Confirmed
  no order-placement capability anywhere in `trading/` outside the
  pre-existing `scripts/confirm_real_order.py` (untouched).

- [x] **Step 9: Full suite** — `uv run pytest -q -m "not integration"` →
  89/89 passed (84 baseline + 5 new).

- [x] **Step 10: Commit** (not done — pending user request)

---

## Out of scope (explicitly declined, not deferred by accident)

- **Index streaming (VNINDEX/VN30) production wiring** — the real message
  shape from `AsyncStream.subscribe_index()` has never been observed (the
  existing spike script only ran outside trading hours). Writing a
  production `IndexValue` mapping now would mean guessing the schema, which
  violates this project's own stated principle (verify real data before
  designing, see every `PLAN_*.md`). Needs someone to re-run the spike
  during live trading hours first; no task here depends on it.
- **Derivative order placement / SELL-to-open strategy** — needs real
  intraday bar data from a live VN30F1M session, not yet captured
  (`PLAN_DERIVATIVE_TRADING.md` explicitly defers this).
- **Real order Phase 4 runbook** (place/cancel against a real fill) — needs
  a funded account and a live trading session; not something an agent can
  execute unattended.
