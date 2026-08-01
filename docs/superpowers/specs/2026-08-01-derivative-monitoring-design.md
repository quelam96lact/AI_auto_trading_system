# Spec: Derivative account monitoring (Phase 1 of PLAN_DERIVATIVE_TRADING.md)

**Date:** 2026-08-01
**Scope:** read-only sync of derivative account balance/margin/positions into
Postgres + Telegram alert on margin-call risk. **No order placement, no
strategy/signal wiring.** Mirrors `PLAN_ACCOUNT_DATA_SYNC.md`'s already-shipped
pattern (equity balance/position sync), applied to account `0434228`
(Derivative, confirmed real in `PLAN_DERIVATIVE_TRADING.md` Phase 0).

## Why this scope

`PLAN_DERIVATIVE_TRADING.md` Phase 0 confirmed balance/margin/position API
shape with real (if currently zero-balance) data, but explicitly deferred
strategy/signal design until real intraday price data is captured from a live
trading session (not yet done). Order placement was also explicitly deferred
to a separate decision. This phase only does what Phase 0's real data already
supports: reading and alerting on account state.

## Data confirmed real (Phase 0, PLAN_DERIVATIVE_TRADING.md)

- Account `0434228`, type Derivative.
- `get_derivative_balance`/`get_derivative_ppmmr`/`get_derivative_positions`
  need `auth.config.client_id` set (same `decode_client_id()` already used by
  `account_sync.py`).
- `get_derivative_positions()` returns a single `AllDerivativePosition` object
  (`.open_positions`/`.closed_positions`), not a list — SDK type hint is wrong.
- Field names verified directly from the installed `ssi_sdk` package
  (`dataclasses.fields()`, not guessed):
  - `DerivativeAccountBalance`: `account_balance, floating_pl, trading_pl,
    total_pl, withdrawable, ...`
  - `DerivativePPMMR`: `rc_call` (bool-like margin-call flag),
    `account_ratio_ssi/vsdc` (current usage ratio),
    `used_limit_warning_level1/2/3_ssi/vsdc` (warning thresholds),
    `margin_call_ssi/vsdc`, `total_equity`.
  - `DerivativePosition`: `symbol, long, short, net, floating_pl, trading_pl`.

**Caveat (stated explicitly, not hidden):** the account has never been funded
or traded, so all values are currently 0 — field *names* are verified real,
but the actual semantics of `account_ratio_*` vs `used_limit_warning_level*`
under real margin usage has not been observed. Alert thresholds below are a
best-effort mapping from field names. Re-verify once the account carries a
real position.

## Design

### Config
Add `ssi_derivative_account: str = ""` to `Config`/`config.yaml` (empty =
sync disabled, same convention as other optional fields). Set to `"0434228"`.

### DB schema (`trading/storage/schema.sql`)
```sql
CREATE TABLE IF NOT EXISTS derivative_balance_snapshot (
  account_no text NOT NULL,
  ts timestamptz NOT NULL,
  account_balance double precision NOT NULL,
  floating_pl double precision NOT NULL,
  trading_pl double precision NOT NULL,
  total_pl double precision NOT NULL,
  withdrawable double precision NOT NULL,
  PRIMARY KEY (account_no, ts)
);

CREATE TABLE IF NOT EXISTS derivative_margin_snapshot (
  account_no text NOT NULL,
  ts timestamptz NOT NULL,
  rc_call boolean NOT NULL,
  account_ratio_ssi double precision NOT NULL,
  account_ratio_vsdc double precision NOT NULL,
  used_limit_warning_level1_ssi double precision NOT NULL,
  used_limit_warning_level2_ssi double precision NOT NULL,
  used_limit_warning_level3_ssi double precision NOT NULL,
  total_equity double precision NOT NULL,
  PRIMARY KEY (account_no, ts)
);

CREATE TABLE IF NOT EXISTS derivative_position_snapshot (
  account_no text NOT NULL,
  ts timestamptz NOT NULL,
  symbol text NOT NULL,
  long integer NOT NULL,
  short integer NOT NULL,
  net integer NOT NULL,
  floating_pl double precision NOT NULL,
  PRIMARY KEY (account_no, ts, symbol)
);
```
(Subset of available fields, same "pick what the dashboard needs" convention
as `account_balance_snapshot`.)

### `trading/collector/derivative_sync.py` (new)
`sync_derivative_data(cfg, storage)` — same shape as `sync_account_data()`:
auth via `ensure_authenticated()` + `decode_client_id()`, call the 3 methods
above (bypassing the 2 confirmed SDK bugs), write snapshots via new
`Storage.save_derivative_balance/save_derivative_margin/save_derivative_positions`
methods (same `ON CONFLICT DO UPDATE` pattern as existing `save_account_*`).
No-op (returns immediately) if `cfg.ssi_derivative_account` is empty.

After writing the margin snapshot, check thresholds and alert:
- `rc_call` truthy → `alert("CRITICAL", "derivative margin call", ...)`
- `account_ratio_ssi/vsdc >= used_limit_warning_level3_*` → CRITICAL
- `>= used_limit_warning_level2_*` or `level1_*` → WARN
- otherwise → no alert (checked every sync, not spammy — only fires on the
  syncs where a threshold is actually crossed, matching how `Watchdog`
  already avoids repeat alerts... actually: keep it simple, alert every time
  over threshold, matching existing `RiskManager`/watchdog style which does
  not deduplicate either; acceptable since this is a 5-minute cadence, not a
  tight loop).

### Wiring (`trading/collector/main.py`)
Add a `sync_derivative_data(cfg, storage)` call in `housekeeping()` right next
to the existing `sync_account_data()` call, same 5-minute cadence, same
try/except-and-alert-WARN-on-failure pattern (don't let a derivative sync
failure kill the collector loop).

### Grafana
New panel "Derivative Margin" (balance, account_ratio, rc_call) added to
`grafana/provisioning/dashboards/trading.json`, same pattern as the existing
"Real Account Balance" panel.

### Testing
- `tests/test_derivative_sync.py`: mock `AsyncPortfolioService`/rest client
  returning realistic (if hollow) field shapes; assert correct DB writes and
  correct bug-bypasses (client_id set, single-object position response
  unpacked correctly, not treated as list).
- Alert-threshold test: construct a fake margin snapshot crossing each level,
  assert correct alert level triggered (unit test on the pure threshold
  function, no network).
- `tests/test_storage.py`: round-trip test for the 3 new `save_derivative_*`
  methods.
- `grep -rn "place_order|cancel_order|modify_order" trading/collector/derivative_sync.py`
  must be empty — same independent safety check `PLAN_ACCOUNT_DATA_SYNC.md`
  used.

## Out of scope (explicit)
- `Position`/`RiskManager` classes wired to any strategy or order flow.
- Order placement of any kind for derivatives.
- SELL-to-open / short-selling logic.
- Re-deriving margin-call semantics from real non-zero account data (flagged
  above as a follow-up once the account is actually used).
