# Spec: Derivative (VN30F1M) paper-trading signal — Phase 1

**Date:** 2026-08-08
**Scope:** `PLAN_DERIVATIVE_TRADING.md` Phase 1 — paper-trading position
model + risk gating + backtest entrypoint for the derivative contract
`41I1G8000` (VN30F1M front-month). **No real order placement, no live
collector/engine wiring.** Scoped via brainstorming with the user on
2026-08-08.

## Why

Phase 0 (`PLAN_DERIVATIVE_TRADING.md`) confirmed real account/margin/position
data (account empty, never traded), the real front-month contract code
(`41I1G8000`), and — in a later session (2026-08-07) — real OHLC REST data
(1m and 5m, `scripts/.spike_derivative_ohlc_sample.json` /
`.spike_derivative_ohlc_5m_2m_sample.json`) and real TRADE/QUOTE/ROOM stream
data (`scripts/.spike_derivative_stream_sample.jsonl`). The plan explicitly
deferred designing a strategy until real bar data existed; that data now
exists, so Phase 1 can be scoped for real. Real order placement stays a
separate, later decision per the plan's own risk framing (leverage risk
higher than equities) — the derivative margin account is still at $0 and has
never traded, so there is no real margin-per-contract figure to design a
live margin-call model against yet.

## Decisions (from brainstorming)

- **Paper-trading + signal/alert only.** No `place_order`/`cancel_order`
  call anywhere in this phase. Mirrors the caution already applied to
  `PLAN_REAL_ORDER_PLACEMENT.md` (dry-run before real capital), taken
  further here because derivatives are leveraged.
- **Backtest-only data source**, not live streaming. Reuses the existing
  `bars`/`bars_daily` tables (schema is already generic by symbol — no
  derivative-specific columns needed) fed via the existing
  `trading/collector/backfill.py::intraday_ohlc()`/`daily_ohlc()` REST
  fetchers pointed at `"41I1G8000"`. Live collector/engine wiring (streaming
  bars, NATS, engine loop) is explicitly deferred to a later phase — smaller
  surface area, doesn't touch code currently running live for equities.
- **Reuse `SmaCrossStrategy.compute_crossover()` unmodified.** It already
  has no position-gating logic (decoupled in the `real_orders.py`
  crossover-decouple fix) — it can be called directly for the derivative
  contract without changing `trading/strategies/sma_cross.py` at all. All
  new long/short position-gating logic lives in new modules, analogous to
  how `real_orders.handle_crossover()` layers its own gating on top of the
  same pure function.
- **New position/broker/risk modules, not modified shared ones.** A
  derivative position's `qty` can be negative (net short) — a concept that
  doesn't exist in `trading/broker.py::Position`/`trading/paper_broker.py`
  (equity `PaperBroker` never goes short, and `RealPosition.sellable_qty` is
  a T+2.5-settlement concept that doesn't apply to T+0 derivatives).
  Bolting sign-handling onto the existing equity classes risks a regression
  in code paths used by live equity paper trading and `real_orders.py`.
- **Simple risk limits, not a real margin-call model.** `max_contracts`
  (flat cap on open contracts) + `max_daily_loss_pct` (same shape as
  `RiskManager.max_daily_loss_pct`) — explicitly NOT a percentage of real
  margin usage, because there is no real per-contract margin figure to
  verify against yet (account has never traded). This is a documented
  known gap, not a guess presented as fact — a real margin-call model needs
  the account's first real trade before it can be designed against real
  numbers, consistent with this project's "verify against real data, don't
  guess SDK/account behavior" convention.
- **`lot_size = 1`** (confirmed real from Phase 0, unlike equities' lot of
  100) — achieved by constructing `SmaCrossStrategy(qty=1, ...)` via its
  existing constructor parameter, no strategy code change needed.
- **No ATR position sizing, no trailing stop in Phase 1.** Both exist for
  equities (`RiskManager.approve_sized()`, `TrailingStopManager`) but adding
  them here means deciding how they interact with a *signed* position — out
  of scope for a first version. Fixed `qty=1` contract per position,
  crossover-only exit (bull closes short/opens long, bear closes
  long/opens short).
- **No contract roll-over.** `"41I1G8000"` is hardcoded for this phase. When
  the contract nears its 2026-08-20 expiry, the next front-month contract
  code must be re-confirmed against real data before use — not assumed to
  follow a naming pattern (Phase 0 already found SSI's internal code is
  *not* the public `VN30F+YYMM` convention).
- **Fee is an unverified placeholder, explicitly marked.** SSI's derivative
  fee schedule (flat per-contract, not `%` of notional like equities) has
  not been confirmed from real data — acceptable here because this phase is
  paper-only (no real money), but must not be treated as accurate if this
  code is ever extended toward real order placement.

## Design

### `trading/derivative_position.py` (new)

```python
@dataclass
class DerivativePosition:
    symbol: str
    qty: int = 0          # có thể ÂM (short), DƯƠNG (long), 0 (flat)
    avg_price: float = 0.0

DERIVATIVE_FEE_PER_CONTRACT = 2_700.0  # VNĐ, CHƯA xác nhận thật — placeholder cho paper-trading

class DerivativePaperBroker:
    def __init__(self, capital: float, fee_per_contract: float = DERIVATIVE_FEE_PER_CONTRACT): ...

    def position_qty(self, symbol: str) -> int: ...  # có dấu, khác PaperBroker

    def open_long(self, symbol: str, qty: int, price: float, ts: datetime) -> Fill: ...
    def open_short(self, symbol: str, qty: int, price: float, ts: datetime) -> Fill: ...
    def close(self, symbol: str, price: float, ts: datetime) -> Fill:
        """Đóng toàn bộ vị thế đang mở (dù long hay short), tính PnL đúng
        chiều (long: (price - avg_price) * qty; short: (avg_price - price) *
        |qty|)."""
```

No `submit()`/`on_bar()` pending-signal queue like equity `PaperBroker` —
Phase 1 fills immediately at the bar's `close` (simplification: no
open/slippage modeling for the derivative fill price yet, since real fill
behavior for derivatives has never been observed — documented as a known
simplification, consistent with "don't model behavior we haven't verified
real data for").

### `trading/derivative_risk.py` (new)

```python
@dataclass
class DerivativeRiskManager:
    capital: float
    max_contracts: int = 1
    max_daily_loss_pct: float = 0.03
    halted_date: date | None = field(default=None, init=False)

    def approve_open(self, side: Literal["long", "short"], current_qty: int,
                      daily_pnl: float, today: date) -> bool:
        """Same halt-check shape as RiskManager._halt_check(). Blocks a new
        open (long or short) if already halted today, or if opening would
        exceed max_contracts. Does NOT gate closes — closing an existing
        position is always allowed, same principle as equity RiskManager
        never blocking a SELL of an already-held position."""
```

### `trading/derivative_backtest.py` (new, parallels `trading/backtest.py`)

```python
def run_derivative_backtest(
    bars: list[Bar],
    strategy: SmaCrossStrategy,
    risk: DerivativeRiskManager,
    capital: float,
) -> BacktestReport:  # reuse existing BacktestReport dataclass from backtest.py
```

Per-bar loop:
1. `crossover = strategy.compute_crossover(bar)`.
2. `net = broker.position_qty(bar.symbol)`.
3. `bull` + `net < 0` → `broker.close(...)` (cover short).
   `bull` + `net == 0` → if `risk.approve_open("long", net, daily_pnl, today)`: `broker.open_long(..., qty=strategy.qty, ...)`.
   `bear` + `net > 0` → `broker.close(...)`.
   `bear` + `net == 0` → if `risk.approve_open("short", ...)`: `broker.open_short(...)`.
   (`net != 0` and crossover direction already matches current side → no-op, same as equity strategy never re-entering an already-held side.)
4. Track equity curve using signed qty (`cash + qty * mark_price`, where a
   short position's mark contribution is `-qty * (avg_price - mark)`
   equivalent — implemented directly from `DerivativePosition`, not copied
   from equity's `unrealized_pnl()` which assumes `qty >= 0`).

A CLI entrypoint (`if __name__ == "__main__":` block, same shape as
`backtest.py::main()`) reads bars for `"41I1G8000"` from `Storage.read_bars()`
over a `--from`/`--to` range, requiring that range to already be backfilled
into the DB via `intraday_ohlc()`/`daily_ohlc()` pointed at that symbol (a
one-line addition wherever the existing backfill script's symbol list is
read from config/CLI arg — not a new fetching mechanism).

## Testing

- `tests/test_derivative_position.py` (new): `DerivativePaperBroker` —
  `open_long()` then `close()` computes correct long PnL/fee/cash;
  `open_short()` then `close()` computes correct short PnL (price drop =
  profit) /fee/cash; `position_qty()` returns negative after `open_short()`.
- `tests/test_derivative_risk.py` (new): `approve_open()` blocks a second
  open beyond `max_contracts`; blocks any open once halted; halt triggers
  when `daily_pnl <= -capital * max_daily_loss_pct`; does not gate `close`
  (no `approve_close` needed — closes aren't gated at all, so this is a test
  of absence, not a method).
- `tests/test_derivative_backtest.py` (new): synthetic bar sequence (reuse
  the `_gen_ohlc_rows`-style helper pattern already in the test suite)
  proving the full cycle bull→long→bear→close→short→bull→cover produces the
  expected `Fill` sequence and signs; a halted-day test where a loss beyond
  `max_daily_loss_pct` blocks a would-be new open but still allows an
  in-progress position to close.
- One test in `tests/test_derivative_backtest.py` loads
  `scripts/.spike_derivative_ohlc_5m_2m_sample.json` directly (real captured
  data, gitignored — test should skip gracefully if the file is absent
  rather than fail, since it's not checked into git) and runs
  `run_derivative_backtest()` against it end-to-end as a smoke test against
  real response shape, not just synthetic bars.

## Out of scope (explicit)

- Real order placement for derivatives — separate future decision, needs a
  real margin-call model backed by the account's first real trade.
- Live collector/engine wiring (streaming bars from `derivative_sync.py`'s
  account-sync path or the WebSocket TRADE channel into `bars`/NATS/engine
  loop) — deferred to a later phase.
- ATR position sizing and trailing stop for derivative positions — deferred;
  Phase 1 stays fixed `qty=1`, crossover-only exit.
- Contract roll-over automation — hardcoded `"41I1G8000"` only.
- Verifying the real derivative fee schedule — placeholder value used,
  explicitly marked, acceptable because this phase never touches real
  money.
- Any change to `trading/strategies/sma_cross.py`, `trading/paper_broker.py`,
  `trading/risk.py`, `trading/backtest.py`, `trading/engine/*`,
  `trading/collector/derivative_sync.py` — all equity/monitoring code paths
  stay untouched.
