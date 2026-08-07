# Spec: ATR-based position sizing for paper trading

**Date:** 2026-08-07
**Scope:** Replace `SmaCrossStrategy`'s fixed BUY qty with an ATR-based size
in the paper-trading path (`backtest.py`, `engine/logic.py`) only. Second of
the three planned ATR use cases (volatility filter — shipped, position
sizing — this spec, stop-loss/take-profit — separate spec after this one),
per the decomposition decision in
`docs/superpowers/specs/2026-08-01-atr-volatility-filter-design.md`.

## Why

`SmaCrossStrategy` currently always signals a fixed `qty` (default 100) on
a BUY crossover, regardless of how volatile the symbol is. A fixed qty means
a highly volatile symbol risks proportionally more capital per lot than a
calm one. ATR-based sizing scales qty down when volatility (ATR) is high and
up when it's low, keeping risk-per-trade roughly constant as a percentage of
capital.

## Design

### Formula

```
qty_raw = (capital × risk_pct) / (atr × atr_multiplier)
qty = floor(qty_raw / 100) × 100          # làm tròn xuống bội lô HOSE/HNX
if atr is None or qty < 100: reject       # không đủ điều kiện, không vào lệnh lẻ lô
```

`risk_pct` (default `0.01`, 1% vốn/lệnh) and `atr_multiplier` (default
`2.0`) are new fields on `RiskManager`, alongside its existing
`max_order_value_pct`/`max_daily_loss_pct` — no `config.yaml`/`Config`
changes, consistent with how those existing fields work today.

### `trading/strategies/sma_cross.py`

Add `self._last_atr: dict[str, float | None] = {}`, set inside
`compute_crossover()` right after `atr = self._atr.update(bar)`. Add
`last_atr(symbol) -> float | None`, mirroring the existing
`last_crossover(symbol)` accessor. No change to `compute_crossover()`'s
existing gating logic or to `on_bar()` — `Signal.qty` from the strategy
stays as today's default; `RiskManager` is what resizes it now (see below).

### `trading/risk.py` — `RiskManager.approve()`

Signature changes: adds `atr: float | None` parameter. **Return type
changes from `bool` to `Signal | None`** — `None` means "reject", any other
value is the (possibly resized) signal to submit.

- Halt / daily-loss checks: unchanged logic, return `None` instead of
  `False`.
- `SELL`: pass through the input `signal` unchanged (no ATR sizing — SELL
  always closes the full held qty, per existing behavior and explicit scope
  decision below).
- `BUY`: compute `qty` per the formula above. If `atr is None` or the
  floored `qty < 100`, return `None` (reject — not a partial-lot order).
  Otherwise build a new `Signal(signal.symbol, "BUY", qty)`, then apply the
  existing `max_order_value_pct` check **against this sized qty** (same
  check as today, just evaluated on the new qty instead of the strategy's
  original fixed qty) — reject (`None`) if it still exceeds the cap.
- `max_positions` check: unchanged, still keyed off `BUY`.

### Call sites

`trading/backtest.py` and `trading/engine/logic.py` both currently do:
```python
if risk.approve(signal, bar.close, broker.positions, daily_pnl, bar.ts.date()):
    broker.submit(signal)
```
Change to:
```python
sized = risk.approve(
    signal, bar.close, broker.positions, daily_pnl, bar.ts.date(),
    atr=strategy.last_atr(bar.symbol),
)
if sized is not None:
    broker.submit(sized)
```

### `trading/real_orders.py` — unchanged

Explicit scope decision: real-order flow keeps its fixed `BUY_QTY = 100`
lot, per the pre-existing design note in that file ("KHÔNG lấy theo
SmaCrossStrategy.qty... không nên quyết định khối lượng lệnh thật"). ATR
sizing only affects the paper/backtest path used to evaluate the strategy,
not money-moving code.

## Testing

- `tests/test_sma_cross.py`: `last_atr()` returns the same value computed
  internally by `compute_crossover()` for that bar/symbol.
- `tests/test_risk.py`:
  - BUY sized correctly per the formula and rounded down to the nearest
    100-lot.
  - BUY rejected (`None`) when the sized qty rounds below 100.
  - BUY rejected when `atr` is `None`.
  - SELL signal passes through with its original qty unchanged.
  - Existing halt/daily-loss/`max_positions` checks still return `None` at
    the right times (behavior unchanged, only the return type changed from
    `False`).
  - `max_order_value_pct` still caps/rejects, now evaluated against the
    sized qty.
- `tests/test_backtest.py`, `tests/test_engine_logic.py`: updated for
  `approve()`'s new signature (`atr` param) and return type (`Signal | None`
  instead of `bool`).

## Out of scope (explicit)

- ATR stop-loss/take-profit — separate spec, after this one ships.
- SELL-side sizing, and derivative/index sizing (both BUY and SELL) — no
  code path exists yet for either; derivative sizing waits on Phase 1 of
  `PLAN_DERIVATIVE_TRADING.md`.
- Any change to `trading/real_orders.py`, `trading/paper_broker.py`, or
  `config.yaml`/`trading/config.py`.
