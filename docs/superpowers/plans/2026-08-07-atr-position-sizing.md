# ATR Position Sizing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `SmaCrossStrategy`'s fixed BUY qty with an ATR-scaled qty
in the paper-trading path only (`backtest.py`, `engine/logic.py`), leaving
`real_orders.py` and its fixed 100-share lot completely untouched.

**Architecture:** `SmaCrossStrategy` gains a `last_atr(symbol)` accessor
(mirrors the existing `last_crossover(symbol)`). `RiskManager` gains a new
method `approve_sized()` — separate from the existing `approve()`, not a
replacement — that computes qty from ATR for BUY signals and returns
`Signal | None`. `approve()` itself keeps its exact current signature and
`bool` return type, used unchanged by `real_orders.py`. Both methods share
one private halt-check helper extracted from `approve()`'s current body, so
halted-day state stays consistent across paper and real flows without
duplicating that logic.

**Tech Stack:** Python 3.11, pytest (`uv run pytest`), existing project
conventions (dataclasses, no new dependencies).

## Global Constraints

- Formula: `qty_raw = (capital × risk_pct) / (atr × atr_multiplier)`,
  `risk_pct` default `0.01`, `atr_multiplier` default `2.0` — both new
  `RiskManager` fields, no `config.yaml`/`Config` changes.
- Rounding: floor `qty_raw` down to the nearest 100-share lot; if the
  floored qty is below 100, reject (no partial-lot orders).
- Scope: BUY only. SELL and everything in `trading/real_orders.py` stay
  exactly as they behave today.
- The existing `max_order_value_pct` cap still applies, evaluated against
  the ATR-sized qty (not the strategy's original fixed qty).
- `trading/real_orders.py`, `trading/paper_broker.py` — do not modify.

---

## Design correction found during planning (read before starting)

The approved spec described changing `RiskManager.approve()`'s signature
and return type directly. While writing this plan, tracing all 3 real call
sites of `approve()` (`trading/backtest.py`, `trading/engine/logic.py`,
`trading/real_orders.py:45`) showed that would silently break
`real_orders.py`: its BUY signals use a fixed `BUY_QTY = 100`, and it never
passes an `atr` value — if `approve()` itself started rejecting/resizing
every BUY based on `atr`, `real_orders.py`'s real-money BUY path would
either always reject (no `atr` → treated as missing) or get silently
resized, both violating the spec's own explicit "real_orders.py unchanged"
requirement. Fix: add a **new** method `approve_sized()` for the paper
path; leave `approve()` byte-for-byte behaviorally identical (same
signature, same `bool` return, same logic), used unchanged by
`real_orders.py`. A private `_halt_check()` helper is extracted so both
methods share the halt/daily-loss logic instead of duplicating it. This
plan implements the corrected design; the spec's intent (formula, rounding,
BUY-only, real_orders.py untouched) is unchanged.

---

### Task 1: `SmaCrossStrategy.last_atr()` accessor

**Files:**
- Modify: `trading/strategies/sma_cross.py:11-78`
- Test: `tests/test_sma_cross.py`

**Interfaces:**
- Produces: `SmaCrossStrategy.last_atr(symbol: str) -> float | None` — the
  ATR value computed by `compute_crossover()`'s most recent call for that
  symbol (same value as the `atr` local variable inside that method, at
  whatever point it was last computed — `None` during ATR warm-up).

- [ ] **Step 1: Run GitNexus impact check before editing**

Run (MCP tool, not a shell command):
```
mcp__gitnexus__impact({ target: "compute_crossover", direction: "upstream", repo: "AI_auto_trading_system", file_path: "trading/strategies/sma_cross.py" })
```
Confirm risk is LOW/MEDIUM before proceeding. Report the result before
continuing to Step 2.

- [ ] **Step 2: Read the current test file to find where to add the new test**

Run: `cat tests/test_sma_cross.py` (or open it) — find the last test
function in the file; the new test goes after it.

- [ ] **Step 3: Write the failing test**

`tests/test_sma_cross.py` already has a module-level `bar_at(i, close)`
helper (always symbol `"VCB"`, `open=high=low=close`) and the file's
existing tests already use `atr_period=1, atr_pct_threshold=0.0` to isolate
MA-crossover behavior from ATR warm-up — reuse both exactly as-is, don't
redefine them. Add this test after the file's last existing test:

```python
def test_last_atr_returns_value_computed_by_compute_crossover():
    strategy = SmaCrossStrategy(fast=2, slow=4, atr_period=1, atr_pct_threshold=0.0)
    assert strategy.last_atr("VCB") is None  # chua co bar nao

    bar1 = bar_at(0, 10)
    strategy.compute_crossover(bar1)
    assert strategy.last_atr("VCB") == 0.0  # bar dau, TR = high-low = 0 (bar_at dung open=high=low=close)

    bar2 = bar_at(1, 20)
    strategy.compute_crossover(bar2)
    assert strategy.last_atr("VCB") == 10.0  # TR = |20-10| = 10, atr_period=1 -> atr = TR
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `uv run pytest tests/test_sma_cross.py::test_last_atr_returns_value_computed_by_compute_crossover -v`
Expected: FAIL with `AttributeError: 'SmaCrossStrategy' object has no attribute 'last_atr'`

- [ ] **Step 5: Implement `last_atr()`**

In `trading/strategies/sma_cross.py`, add a new instance dict next to
`self._last_crossover` in `__init__` (line 26):

```python
        self._last_crossover: dict[str, Crossover | None] = {}
        self._last_atr: dict[str, float | None] = {}
```

In `compute_crossover()`, right after `atr = self._atr.update(bar)` (line 44):

```python
        atr = self._atr.update(bar)
        self._last_atr[bar.symbol] = atr
```

Add the new accessor right after `last_crossover()` (after line 78):

```python
    def last_atr(self, symbol: str) -> float | None:
        """ATR vừa tính ở lần compute_crossover() gần nhất cho symbol này."""
        return self._last_atr.get(symbol)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/test_sma_cross.py::test_last_atr_returns_value_computed_by_compute_crossover -v`
Expected: PASS

- [ ] **Step 7: Run the full sma_cross test file to check for regressions**

Run: `uv run pytest tests/test_sma_cross.py -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add trading/strategies/sma_cross.py tests/test_sma_cross.py
git commit -m "feat: add SmaCrossStrategy.last_atr() accessor"
```

---

### Task 2: `RiskManager.approve_sized()` — ATR-based sizing

**Files:**
- Modify: `trading/risk.py:1-37`
- Test: `tests/test_risk.py`

**Interfaces:**
- Consumes: `Signal` (from `trading.strategy`, fields `symbol: str`,
  `side: "BUY"|"SELL"`, `qty: int`, frozen dataclass), `Position` (from
  `trading.broker`, fields `symbol`, `qty`, `avg_price`).
- Produces: `RiskManager.approve_sized(signal: Signal, ref_price: float,
  atr: float | None, positions: dict[str, Position], daily_pnl: float,
  today: date) -> Signal | None`. `RiskManager.approve()` keeps its current
  signature/return type unchanged (`bool`) — do not modify its behavior,
  only extract the halt check into a shared private helper.

- [ ] **Step 1: Run GitNexus impact check before editing**

Run:
```
mcp__gitnexus__impact({ target: "approve", direction: "upstream", repo: "AI_auto_trading_system", file_path: "trading/risk.py" })
```
This must show exactly 3 callers: `trading/backtest.py`,
`trading/engine/logic.py`, `trading/real_orders.py`. Report the risk level.
If it shows any caller other than these 3, STOP and report back before
continuing — that would mean this plan's blast-radius assumption is wrong.

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_risk.py` (after the existing tests, don't touch them):

```python
def test_approve_sized_computes_qty_from_atr_formula_rounded_to_lot():
    rm = RiskManager(capital=CAP)  # risk_pct=0.01, atr_multiplier=2.0 mac dinh
    sig = Signal("VCB", "BUY", 999)  # qty goc bi bo qua, sized se thay the
    result = rm.approve_sized(sig, ref_price=1_000, atr=333.0, positions={}, daily_pnl=0, today=D)
    # qty_raw = 100_000_000*0.01 / (333.0*2) = 1_000_000/666 = 1501.5015...
    # floor ve boi 100 -> 1500
    assert result == Signal("VCB", "BUY", 1500)


def test_approve_sized_rejects_when_qty_rounds_below_lot():
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "BUY", 100)
    # qty_raw = 1_000_000 / (20_000*2) = 25 -> floor ve boi 100 = 0 < 100
    result = rm.approve_sized(sig, ref_price=1_000, atr=20_000.0, positions={}, daily_pnl=0, today=D)
    assert result is None


def test_approve_sized_rejects_when_atr_is_none():
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "BUY", 100)
    result = rm.approve_sized(sig, ref_price=1_000, atr=None, positions={}, daily_pnl=0, today=D)
    assert result is None


def test_approve_sized_rejects_when_sized_order_value_over_limit():
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "BUY", 100)
    # qty_raw = 1_000_000 / (1_000*2) = 500 (boi 100 san). order_value = 100_000*500 = 50_000_000
    # > max_order_value_pct(0.20)*CAP(100_000_000) = 20_000_000 -> tu choi
    result = rm.approve_sized(sig, ref_price=100_000, atr=1_000.0, positions={}, daily_pnl=0, today=D)
    assert result is None


def test_approve_sized_sell_passes_through_unchanged_qty():
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "SELL", 350)  # so le, KHONG phai boi 100 - chung minh khong bi lam tron
    result = rm.approve_sized(sig, ref_price=1_000, atr=None, positions={}, daily_pnl=0, today=D)
    assert result == sig


def test_approve_sized_rejects_new_symbol_beyond_max_positions():
    rm = RiskManager(capital=CAP, max_positions=2)
    positions = {"A": Position("A", 100, 10), "B": Position("B", 100, 10)}
    sig = Signal("C", "BUY", 100)
    # atr=5_000 -> qty_raw = 1_000_000/(5_000*2) = 100 (boi 100 san, order_value nho)
    result = rm.approve_sized(sig, ref_price=1_000, atr=5_000.0, positions=positions, daily_pnl=0, today=D)
    assert result is None


def test_approve_sized_allows_adding_to_already_held_symbol_beyond_max_positions():
    rm = RiskManager(capital=CAP, max_positions=2)
    positions = {"A": Position("A", 100, 10), "B": Position("B", 100, 10)}
    sig = Signal("A", "BUY", 100)
    result = rm.approve_sized(sig, ref_price=1_000, atr=5_000.0, positions=positions, daily_pnl=0, today=D)
    assert result == Signal("A", "BUY", 100)


def test_approve_sized_shares_halt_state_with_approve():
    rm = RiskManager(capital=CAP, max_daily_loss_pct=0.03)
    buy = Signal("VCB", "BUY", 100)
    # approve() (khong sized) trigger halt truoc
    assert rm.approve(buy, ref_price=1_000, positions={}, daily_pnl=-3_000_001, today=D) is False
    assert rm.halted_date == D
    # approve_sized() cung bi chan boi CUNG mot halted_date, du atr hop le
    result = rm.approve_sized(buy, ref_price=1_000, atr=5_000.0, positions={}, daily_pnl=0, today=D)
    assert result is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_risk.py -k approve_sized -v`
Expected: FAIL with `AttributeError: 'RiskManager' object has no attribute 'approve_sized'`

- [ ] **Step 4: Implement — extract `_halt_check` and add `approve_sized`**

Replace the full contents of `trading/risk.py` with:

```python
from dataclasses import dataclass, field
from datetime import date

from trading.broker import Position
from trading.strategy import Signal


@dataclass
class RiskManager:
    capital: float
    max_positions: int = 5
    max_order_value_pct: float = 0.20
    max_daily_loss_pct: float = 0.03
    risk_pct: float = 0.01
    atr_multiplier: float = 2.0
    halted_date: date | None = field(default=None, init=False, repr=False)

    def _halt_check(self, daily_pnl: float, today: date) -> bool:
        """True nếu bị chặn hôm nay (đã halt trước đó, hoặc vừa halt do lỗ
        vượt max_daily_loss_pct) — dùng chung bởi approve() và
        approve_sized() để 2 luồng paper/thật đồng bộ trạng thái halt."""
        if self.halted_date == today:
            return True
        if daily_pnl <= -self.capital * self.max_daily_loss_pct:
            self.halted_date = today
            return True
        return False

    def approve(
        self,
        signal: Signal,
        ref_price: float,
        positions: dict[str, Position],
        daily_pnl: float,
        today: date,
    ) -> bool:
        if self._halt_check(daily_pnl, today):
            return False
        if signal.side == "BUY":
            order_value = ref_price * signal.qty
            if order_value > self.capital * self.max_order_value_pct:
                return False
            held_symbols = {s for s, p in positions.items() if p.qty > 0}
            if signal.symbol not in held_symbols and len(held_symbols) >= self.max_positions:
                return False
        return True

    def approve_sized(
        self,
        signal: Signal,
        ref_price: float,
        atr: float | None,
        positions: dict[str, Position],
        daily_pnl: float,
        today: date,
    ) -> Signal | None:
        """Giống approve() nhưng cho luồng paper trading: BUY được resize qty
        theo ATR (risk_pct vốn / (atr * atr_multiplier), làm tròn xuống bội
        100) thay vì dùng signal.qty gốc từ Strategy. SELL đi qua nguyên vẹn,
        không đổi qty — chỉ BUY được sizing theo ATR (quyết định phạm vi rõ
        ràng, xem spec). KHÔNG dùng cho real_orders.py — đó vẫn gọi approve()."""
        if self._halt_check(daily_pnl, today):
            return None
        if signal.side == "SELL":
            return signal

        if atr is None or atr <= 0:
            return None
        qty_raw = (self.capital * self.risk_pct) / (atr * self.atr_multiplier)
        qty = int(qty_raw // 100) * 100
        if qty < 100:
            return None

        order_value = ref_price * qty
        if order_value > self.capital * self.max_order_value_pct:
            return None
        held_symbols = {s for s, p in positions.items() if p.qty > 0}
        if signal.symbol not in held_symbols and len(held_symbols) >= self.max_positions:
            return None

        return Signal(signal.symbol, "BUY", qty)
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `uv run pytest tests/test_risk.py -v`
Expected: all PASS, including every pre-existing test in the file
unchanged (they exercise `approve()`, which is behaviorally identical to
before).

- [ ] **Step 6: Commit**

```bash
git add trading/risk.py tests/test_risk.py
git commit -m "feat: add RiskManager.approve_sized() for ATR-based BUY sizing"
```

---

### Task 3: Wire `approve_sized()` into the paper-trading call sites

**Files:**
- Modify: `trading/backtest.py:21-40`, `trading/backtest.py:75-77` (STRATEGIES/imports as needed)
- Modify: `trading/engine/logic.py:12-33`
- Test: `tests/test_backtest.py`, `tests/test_engine_logic.py` (run only — see below, no new test code expected)

**Interfaces:**
- Consumes: `SmaCrossStrategy.last_atr(symbol: str) -> float | None` (Task 1),
  `RiskManager.approve_sized(...) -> Signal | None` (Task 2).

- [ ] **Step 1: Run GitNexus impact check before editing**

Run:
```
mcp__gitnexus__impact({ target: "run_backtest", direction: "upstream", repo: "AI_auto_trading_system", file_path: "trading/backtest.py" })
mcp__gitnexus__impact({ target: "process_bar", direction: "upstream", repo: "AI_auto_trading_system", file_path: "trading/engine/logic.py" })
```
Report both risk levels before continuing.

- [ ] **Step 2: Update `trading/engine/logic.py`**

Current (`trading/engine/logic.py:28-31`):
```python
    if signal is not None:
        daily_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)
        if risk.approve(signal, bar.close, broker.positions, daily_pnl, bar.ts.date()):
            broker.submit(signal)
```
Replace with:
```python
    if signal is not None:
        daily_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)
        sized = risk.approve_sized(
            signal, bar.close, strategy.last_atr(bar.symbol), broker.positions, daily_pnl, bar.ts.date()
        )
        if sized is not None:
            broker.submit(sized)
```

- [ ] **Step 3: Update `trading/backtest.py`**

Current (`trading/backtest.py:21-25`, the `run_backtest` signature):
```python
def run_backtest(
    bars: list[Bar],
    strategy: Strategy,
    risk: RiskManager,
    capital: float,
) -> BacktestReport:
```
Replace the `strategy: Strategy` parameter type with `strategy:
SmaCrossStrategy` (matches what every real caller already passes, and
matches `engine/logic.py`'s existing convention of typing this parameter
concretely rather than via the `Strategy` protocol — needed because
`last_atr()` isn't part of the `Strategy` protocol and shouldn't be, since
not every future strategy will use ATR):
```python
def run_backtest(
    bars: list[Bar],
    strategy: SmaCrossStrategy,
    risk: RiskManager,
    capital: float,
) -> BacktestReport:
```
Update the import at the top of the file — remove `from trading.strategy
import Strategy` if nothing else in the file uses `Strategy` (check with
`grep -n "Strategy" trading/backtest.py` first; only remove if this was its
only use), and add:
```python
from trading.strategies.sma_cross import SmaCrossStrategy
```
(Check first whether this import already exists further down the file at
line 75 inside the `main()`-adjacent section — if so, move it up to the
top-of-file import block instead of duplicating it.)

Current (`trading/backtest.py:36-40`):
```python
        signal = strategy.on_bar(bar, broker)
        if signal is not None:
            daily_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)
            if risk.approve(signal, bar.close, broker.positions, daily_pnl, bar.ts.date()):
                broker.submit(signal)
```
Replace with:
```python
        signal = strategy.on_bar(bar, broker)
        if signal is not None:
            daily_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)
            sized = risk.approve_sized(
                signal, bar.close, strategy.last_atr(bar.symbol), broker.positions, daily_pnl, bar.ts.date()
            )
            if sized is not None:
                broker.submit(sized)
```

- [ ] **Step 4: Run the existing test suites to verify no regressions**

Run: `uv run pytest tests/test_backtest.py tests/test_engine_logic.py tests/test_risk.py tests/test_sma_cross.py -v`
Expected: all PASS. These files are not expected to need new test code for
this task — the existing tests already exercise BUY signals through
`process_bar()`/`run_backtest()` with real (non-flat-forever) price
sequences, so they naturally exercise the new sizing path. If any of them
fail, read the failure carefully before changing anything — a failure here
most likely means either the ATR value at the crossover bar came out `0`
or negative (sizing formula divides by it) or the sized order value tripped
`max_order_value_pct`; both are legitimate scenarios given synthetic flat
test prices, and the fix is to adjust that specific test's price sequence
or `RiskManager` constructor args (e.g. a larger `max_order_value_pct` for
that one test), not to change `trading/risk.py`'s logic from Task 2.

- [ ] **Step 5: Run the full unit test suite**

Run: `uv run pytest -m "not integration" -v`
Expected: all PASS.

- [ ] **Step 6: Run GitNexus detect-changes before committing**

Run:
```
mcp__gitnexus__detect_changes({ repo: "AI_auto_trading_system", scope: "all" })
```
Confirm the changed/affected symbols match this task's scope
(`SmaCrossStrategy`, `RiskManager`, `run_backtest`, `process_bar`, plus
their test files) and no `real_orders.py` symbols appear as changed.

- [ ] **Step 7: Commit**

```bash
git add trading/backtest.py trading/engine/logic.py
git commit -m "feat: wire ATR-based position sizing into paper-trading call sites"
```

---

### Task 4: Re-index GitNexus and final verification

**Files:** none (verification only)

- [ ] **Step 1: Re-index GitNexus**

Run: `npx gitnexus analyze`

- [ ] **Step 2: Run the complete unit test suite one more time**

Run: `uv run pytest -m "not integration" -v`
Expected: all PASS (should match or exceed the pre-change count of 102).

- [ ] **Step 3: Confirm `real_orders.py` is untouched**

Run: `git diff main...HEAD -- trading/real_orders.py` (or `git log
--oneline trading/real_orders.py` since the plan started) — expect no
output / no new commits touching this file.

- [ ] **Step 4: Report back**

Summarize: final test count, confirmation `real_orders.py` was never
touched, and the GitNexus risk levels observed in each task's Step 1 impact
check.
