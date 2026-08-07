# Spec: ATR trailing stop for paper trading

**Date:** 2026-08-07
**Scope:** Add a per-bar ATR-based trailing stop-loss to the paper-trading
path (`backtest.py`, `engine/logic.py`) only. Third and final of the three
planned ATR use cases (volatility filter — shipped, position sizing —
shipped, this spec — trailing stop only, no fixed take-profit), per the
decomposition decision in
`docs/superpowers/specs/2026-08-01-atr-volatility-filter-design.md`. Scoped
via brainstorming with the user on 2026-08-07; several decisions below
depart from that original spec's mention of "stop-loss/take-profit" — see
"Decisions" for what was explicitly cut and why.

## Why

Today a paper-trading position only closes on a bear MA crossover — a
position can sit through an arbitrarily large drawdown before the MA
catches up and signals an exit. A trailing ATR stop closes the position as
soon as price gives back more than `sl_multiplier × current ATR` from its
highest point since entry, independent of whether/when the next bear
crossover happens — a faster, volatility-aware safety net layered on top of
the existing crossover-based exit (which stays unchanged).

## Decisions (from brainstorming)

- **Checked every bar**, not only on crossover bars — a real stop has to
  react the moment price touches it, not wait for the strategy's next
  signal.
- **Paper trading only** (`backtest.py`, `engine/logic.py`).
  `trading/real_orders.py` is unchanged — it still only exits a real
  position on a bear crossover via `handle_crossover()`.
- **Trailing, not fixed-at-entry**: the stop follows the highest bar-high
  seen since the position opened, never moving down.
- **No take-profit.** Trend-following convention — let winners run, exit
  only via the trailing stop (or the existing bear-crossover exit).
  Explicitly cuts the "take-profit" half of what the original ATR filter
  spec called "stop-loss/take-profit" as one item.
- **Stop distance uses the current bar's ATR** (`strategy.last_atr(symbol)`
  at that bar), not the ATR frozen at entry — the stop's width breathes
  with current volatility.
- **Fills immediately within the bar that touches the stop** — not the
  existing 1-bar-lag `submit()`/`on_bar()` pattern crossover signals use.
  Waiting a full extra bar after price has already touched the stop would
  defeat the point of a protective stop.
- **Not blocked by `RiskManager`'s halt check.** Halting exists to stop
  *new* risk (a big daily loss halts further BUYs); it should not also trap
  an open position through the worst part of a bad day. This is
  intentionally inconsistent with the existing bear-crossover SELL path
  (still gated by `approve_sized()`, still blocked by halt) — that
  inconsistency is accepted as correct rather than "fixed", and is not in
  scope to change here.

## Design

### `trading/trailing_stop.py` (new, flat module — same pattern as
`trading/indicators.py`)

```python
class TrailingStopManager:
    def __init__(self, sl_multiplier: float = 2.0): ...

    def on_position_opened(self, symbol: str, fill_price: float) -> None:
        """Gọi khi 1 vị thế mới mở (BUY fill) — khởi tạo highest_price."""

    def on_position_closed(self, symbol: str) -> None:
        """Gọi khi vị thế đóng hoàn toàn (bất kể lý do) — xoá state để lần
        mở vị thế tiếp theo bắt đầu lại từ đầu."""

    def check(self, bar: Bar, atr: float | None) -> float | None:
        """Cập nhật highest_price_since_entry = max(hiện tại, bar.high).
        Nếu atr is None hoặc chưa có vị thế đang theo dõi cho symbol này,
        trả về None (không trigger). Ngược lại tính
        stop_level = highest_price - atr * sl_multiplier; nếu
        bar.low <= stop_level, trả về giá khớp = min(bar.open, stop_level)
        (khớp tại open nếu bar gap xuống dưới stop — không khớp giá tốt hơn
        thực tế thị trường cho phép). Nếu không trigger, trả về None."""
```

Separate file, not folded into `RiskManager` — this is an exit *signal
generator* ("should we get out now"), a different responsibility than
`RiskManager`'s *request gate* ("should this order be let through").
Per-symbol state (`dict[str, float]` for highest price), same pattern as
`AtrCalculator`/`SmaCrossStrategy`'s own per-symbol dicts.

### `trading/paper_broker.py::PaperBroker` — new `force_exit()` method

```python
def force_exit(self, symbol: str, price: float, ts: datetime) -> Fill:
    """Đóng TOÀN BỘ vị thế đang giữ ngay lập tức tại `price` — dùng bởi
    trailing stop. KHÔNG qua hàng đợi self._pending như submit()/on_bar()
    (không có độ trễ 1 bar). Giả định caller đã xác nhận vị thế đang mở
    (qty > 0) trước khi gọi."""
```

Same PnL/fee/cash accounting as the existing `SELL` branch inside
`on_bar()` (fee = `gross * fee_rate + gross * sell_tax_rate`, no slippage
applied — the stop price passed in already reflects the intrabar level, not
a fresh order needing its own slippage model), returns a `Fill` with
`side="SELL"`.

### Wiring into `process_bar()` (`trading/engine/logic.py`) and
`run_backtest()` (`trading/backtest.py`)

Both functions gain a new required parameter `trailing_stop:
TrailingStopManager`. Per-bar order of operations (identical shape in both
functions):

1. `fills = broker.on_bar(bar)` — fills any pending signal from the
   *previous* bar (as today). For each fill this returns: if `side ==
   "BUY"`, call `trailing_stop.on_position_opened(symbol, fill.price)`; if
   `side == "SELL"`, call `trailing_stop.on_position_closed(symbol)` (this
   covers a position closed via the existing bear-crossover path).
2. `signal = strategy.on_bar(bar, broker)` (unchanged — also updates
   `last_atr` internally via `compute_crossover()`).
3. If `broker.position_qty(bar.symbol) > 0`: `stop_price =
   trailing_stop.check(bar, strategy.last_atr(bar.symbol))`.
4. If `stop_price is not None`: call `broker.force_exit(bar.symbol,
   stop_price, bar.ts)`, then `trailing_stop.on_position_closed(bar.symbol)`,
   append the returned `Fill` to this bar's fills. **The `signal` from step
   2 is discarded this bar** — the position that signal would have
   affected just closed.
5. Otherwise (no stop trigger), proceed exactly as today: if `signal is not
   None`, `risk.approve_sized(...)` then `broker.submit(...)` if approved.

`process_bar()`'s existing `on_crossover` callback (used by
`real_orders.py` via `engine/main.py`) is unaffected — it still fires from
`strategy.last_crossover()` independent of any of the above, so real-order
behavior doesn't change.

### Call site construction

`engine/main.py` and `backtest.py::main()` each construct one
`TrailingStopManager()` per run (default `sl_multiplier=2.0`), alongside
their existing `RiskManager(...)` construction, and pass it through.

## Testing

- `tests/test_trailing_stop.py` (new): `TrailingStopManager` in isolation —
  `check()` returns `None` before `on_position_opened()`; highest price
  updates correctly across bars (never decreases); stop triggers exactly
  when `bar.low <= highest - atr*sl_multiplier`; trigger price is
  `min(bar.open, stop_level)` for a gap-down case; `check()` returns `None`
  when `atr is None`; `on_position_closed()` resets state so a later
  `on_position_opened()` starts a fresh `highest_price`.
- `tests/test_paper_broker.py`: `force_exit()` closes the full position,
  computes PnL/fee/cash correctly, does not touch `self._pending`, and
  raises/is not called for a symbol with no open position (documented as
  caller responsibility above, not defended inside `force_exit()` itself —
  consistent with `on_bar()`'s existing SELL branch, which also assumes a
  valid position).
- `tests/test_engine_logic.py`, `tests/test_backtest.py`: updated call
  sites to construct and pass a `TrailingStopManager`; a new test
  demonstrating a trailing stop exit happening *before* the next bear
  crossover would have fired (proving the two paths are independent and
  the earlier one wins).

## Out of scope (explicit)

- Fixed take-profit — cut per the decision above.
- Trailing stop for `real_orders.py` — stays bear-crossover-only.
- Trailing stop for derivative/index positions — waits on Phase 1 of
  `PLAN_DERIVATIVE_TRADING.md`.
- Any change to `RiskManager` (`approve()`, `approve_sized()`, or the halt
  check) — the trailing stop bypasses `RiskManager` entirely rather than
  changing its halt semantics.
