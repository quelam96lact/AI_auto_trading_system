# Spec: ATR indicator + volatility filter for SmaCrossStrategy

**Date:** 2026-08-01
**Scope:** Add a reusable ATR (Average True Range) calculator and use it to
suppress SMA-cross signals during low-volatility periods. First of three
planned ATR use cases (volatility filter, ATR position sizing, ATR
stop-loss/take-profit) — this spec covers only the volatility filter, per
explicit user decision to decompose rather than build all three at once.

## Why

`SmaCrossStrategy` currently fires BUY/SELL purely on MA crossover, with no
regard for whether the market is trending or chopping sideways — a common
source of false signals. ATR-based filtering is the first, simplest of three
planned uses of ATR (the other two — position sizing, stop-loss — are
larger, deferred to separate specs after this one ships and the codebase
has some ATR-based test/backtest experience).

## Design

### `trading/indicators.py` (new, flat module — matches existing style:
`trading/risk.py`, `trading/strategy.py` are flat files, no subpackage)

```python
class AtrCalculator:
    def __init__(self, period: int = 14): ...
    def update(self, bar: Bar) -> float | None:
        """Per-symbol state (dict of deque(maxlen=period) for True Range,
        dict of prev_close per symbol) — same pattern SmaCrossStrategy uses
        for its own per-symbol MA state. Returns None until `period` bars
        have been seen for this symbol (warm-up)."""
```

True Range for a bar = `max(high-low, |high-prev_close|, |low-prev_close|)`
(the first bar for a symbol has no prev_close, so TR = high-low for that bar
only). ATR = simple average of the last `period` True Range values — a
simple moving average, not Wilder's smoothing, to stay consistent with
`SmaCrossStrategy`'s own simple-average MAs rather than mixing smoothing
conventions in the same codebase.

### `trading/strategies/sma_cross.py` — `SmaCrossStrategy` changes

- Constructor gains `atr_period: int = 14`, `atr_pct_threshold: float =
  0.005` (0.5%). Internally holds `self._atr = AtrCalculator(period=atr_period)`.
- `compute_crossover(bar)`: call `self._atr.update(bar)` unconditionally,
  every bar (so ATR state accumulates regardless of whether an MA crossover
  fires this bar). After computing the raw MA-based crossover as today, gate
  it: if `atr is None` (still warming up) or `atr / bar.close <
  atr_pct_threshold`, force the crossover to `None` before storing it in
  `self._last_crossover[bar.symbol]` and returning it — for **both** BUY and
  SELL directions (explicit user decision: no exception for exits).
- This keeps the filter inside `compute_crossover()`, which both `on_bar()`
  (paper trading path) and `last_crossover()` (read separately by
  `trading/engine/logic.py::process_bar()` to drive
  `real_orders.handle_crossover()`) rely on — so paper and real-order flows
  stay consistent automatically, with no changes needed to
  `real_orders.py` or `engine/logic.py`.
- `on_bar()` itself is unchanged — it already just calls
  `compute_crossover()` and reacts to whatever it returns.

### Existing test fallout (in scope, not a tangent)

`tests/test_sma_cross.py`'s existing tests use short (6-8 bar) flat-OHLC
fixtures with the default `atr_period=14` — every one of them would now be
permanently stuck in ATR warm-up and never fire a signal. These tests exist
to verify pure MA-crossover logic, not ATR behavior, so they'll be updated
to construct `SmaCrossStrategy` with `atr_period` small enough to clear
warm-up within their bar count and `atr_pct_threshold=0.0` (accept any
nonzero volatility) — isolating them from the new filter so they keep
testing what they've always tested. New tests are added specifically to
exercise the ATR filter's blocking behavior.

## Testing

- `tests/test_atr.py` (new): `AtrCalculator` in isolation — hand-computed
  TR/ATR values over a fixed OHLC sequence, `None` during warm-up then a
  correct value once `period` bars are seen, independent state per symbol.
- `tests/test_sma_cross.py`: existing tests updated per above; new tests —
  crossover suppressed when ATR% is below threshold (both BUY and SELL
  cases), crossover fires normally once ATR% clears the threshold, crossover
  suppressed during ATR warm-up even when the MA crossover condition is met.

## Out of scope (explicit, deferred to later specs)

- ATR-based position sizing (replacing the fixed `qty` in `Signal`).
- ATR-based stop-loss/take-profit (needs new state tracking entry price +
  ATR after a position opens — no such mechanism exists anywhere in the
  codebase today; explicitly the largest of the three ATR use cases,
  deferred until after this and position sizing are done).
- Any change to `real_orders.py`, `trading/engine/logic.py`, or
  `trading/paper_broker.py` — the filter's placement in
  `compute_crossover()` makes changes to these unnecessary for this spec.
