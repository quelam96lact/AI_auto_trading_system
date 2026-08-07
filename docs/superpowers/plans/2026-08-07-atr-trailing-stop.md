# ATR Trailing Stop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-bar ATR trailing stop-loss to the paper-trading path
(`backtest.py`, `engine/logic.py`) that closes a position immediately
within the bar that touches the stop, independent of the existing bear-MA-
crossover exit — leaving `trading/real_orders.py` completely untouched.

**Architecture:** A new `TrailingStopManager` class (new file, mirrors the
`AtrCalculator`/`SmaCrossStrategy` per-symbol-state pattern) tracks the
highest bar-high seen since a position opened and, given the current bar's
ATR, reports whether this bar's low touched the trailing stop. A new
`PaperBroker.force_exit()` method closes a position immediately at a given
price, bypassing the existing 1-bar-lag `submit()`/`on_bar()` queue.
`process_bar()` and `run_backtest()` are wired to check the trailing stop
every bar, before falling back to the existing crossover-based signal path.

**Tech Stack:** Python 3.11, pytest (`uv run pytest`), no new dependencies.

## Global Constraints

- Checked every bar (not only on crossover bars).
- Paper trading only: `trading/backtest.py`, `trading/engine/logic.py`,
  `trading/engine/main.py`. Do not modify `trading/real_orders.py`.
- Trailing, not fixed-at-entry: stop follows the highest bar-high since
  entry, never moves down.
- No take-profit — trailing stop is the only new exit mechanism.
- Stop distance uses the *current bar's* ATR
  (`strategy.last_atr(symbol)`), not the ATR at entry.
- Fills immediately within the bar that touches the stop, at
  `min(bar.open, stop_level)` — not the existing 1-bar-lag pattern.
- NOT gated by `RiskManager`'s halt check — bypasses `RiskManager`
  entirely. Do not modify `trading/risk.py` in this plan.
- Default `sl_multiplier = 2.0`.

---

### Task 1: `TrailingStopManager`

**Files:**
- Create: `trading/trailing_stop.py`
- Test: `tests/test_trailing_stop.py` (new)

**Interfaces:**
- Consumes: `Bar` (from `trading.models`, fields `symbol`, `open`, `high`,
  `low`, `close`, frozen dataclass).
- Produces: `TrailingStopManager(sl_multiplier: float = 2.0)`,
  `.on_position_opened(symbol: str, fill_price: float) -> None`,
  `.on_position_closed(symbol: str) -> None`,
  `.check(bar: Bar, atr: float | None) -> float | None` (returns the fill
  price if this bar's low touched the trailing stop, else `None`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_trailing_stop.py`:

```python
from datetime import datetime

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.trailing_stop import TrailingStopManager


def bar(o, h, l, c, sym="VCB", m=0):
    return Bar(sym, datetime(2026, 7, 15, 9, m, tzinfo=TZ), o, h, l, c, 1000)


def test_check_returns_none_before_position_opened():
    ts = TrailingStopManager(sl_multiplier=2.0)
    assert ts.check(bar(10, 10, 10, 10), atr=1.0) is None


def test_check_returns_none_when_atr_is_none():
    ts = TrailingStopManager(sl_multiplier=2.0)
    ts.on_position_opened("VCB", fill_price=100.0)
    assert ts.check(bar(1, 1, 1, 1), atr=None) is None


def test_highest_price_is_remembered_across_bars_not_just_latest_high():
    # sl_multiplier=2.0, atr=1.0 co dinh moi bar.
    ts = TrailingStopManager(sl_multiplier=2.0)
    ts.on_position_opened("VCB", fill_price=100.0)

    # Bar 1: day highest len 112 (tam range hep de KHONG trigger: stop =
    # 112 - 1*2 = 110, low=111 > 110).
    result1 = ts.check(bar(111, 112, 111, 112, m=0), atr=1.0)
    assert result1 is None

    # Bar 2: high moi (109) THAP HON highest da luu (112). Neu buggy code
    # dung high cua bar nay thay vi nho highest that su, stop se la
    # 109-2=107 va low=108 se KHONG trigger. Code dung phai nho highest=112
    # -> stop=112-2=110, low=108<=110 -> TRIGGER.
    result2 = ts.check(bar(109, 109, 108, 109, m=5), atr=1.0)
    assert result2 == 109  # min(bar.open=109, stop=110) = 109


def test_stop_triggers_at_computed_level_when_no_gap():
    ts = TrailingStopManager(sl_multiplier=1.0)
    ts.on_position_opened("VCB", fill_price=100.0)
    ts.check(bar(100, 130, 100, 130, m=0), atr=1.0)  # highest -> 130
    # stop = 130 - 1*1 = 129, bar mo cua dung tai 129 (khong gap)
    result = ts.check(bar(129, 129, 128, 128, m=5), atr=1.0)
    assert result == 129  # min(129, 129)


def test_stop_fills_at_open_on_gap_down_not_at_nominal_stop_level():
    ts = TrailingStopManager(sl_multiplier=1.0)
    ts.on_position_opened("VCB", fill_price=100.0)
    ts.check(bar(100, 101, 100, 101, m=0), atr=1.0)  # highest -> 101
    # stop = 101 - 1*1 = 100. Bar sau GAP xuong duoi stop: open=95.
    result = ts.check(bar(95, 96, 90, 92, m=5), atr=1.0)
    assert result == 95  # gap-down: khop tai open (95), khong phai stop_level (100)


def test_on_position_closed_resets_highest_for_next_entry():
    ts = TrailingStopManager(sl_multiplier=2.0)
    ts.on_position_opened("VCB", fill_price=100.0)
    ts.check(bar(148, 150, 149, 149, m=0), atr=1.0)  # highest -> 150, khong trigger (stop=148, low=149>148)

    ts.on_position_closed("VCB")
    assert ts.check(bar(10, 10, 10, 10, m=5), atr=1.0) is None  # khong con vi the nao dang theo doi

    ts.on_position_opened("VCB", fill_price=20.0)
    # Neu highest KHONG duoc reset (con nho 150 tu vi the truoc), stop se la
    # 150-2=148 va low=21 se sai trigger. Code dung: highest moi = max(20,22)=22,
    # stop=22-1*2=20, low=21>20 -> KHONG trigger.
    result = ts.check(bar(21, 22, 21, 21, m=10), atr=1.0)
    assert result is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_trailing_stop.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'trading.trailing_stop'`

- [ ] **Step 3: Implement `TrailingStopManager`**

Create `trading/trailing_stop.py`:

```python
from trading.models import Bar


class TrailingStopManager:
    """Trailing stop-loss theo ATR, state theo tung symbol (cung pattern
    voi AtrCalculator/SmaCrossStrategy). KHONG co take-profit - chi trailing
    stop-loss, de loi chay (trend-following)."""

    def __init__(self, sl_multiplier: float = 2.0):
        self.sl_multiplier = sl_multiplier
        self._highest: dict[str, float] = {}

    def on_position_opened(self, symbol: str, fill_price: float) -> None:
        """Goi khi 1 vi the moi mo (BUY fill) - khoi tao highest_price."""
        self._highest[symbol] = fill_price

    def on_position_closed(self, symbol: str) -> None:
        """Goi khi vi the dong hoan toan (bat ke ly do) - xoa state de lan
        mo vi the tiep theo bat dau lai tu dau."""
        self._highest.pop(symbol, None)

    def check(self, bar: Bar, atr: float | None) -> float | None:
        """Cap nhat highest_price_since_entry, tra ve gia khop neu bar nay
        cham stop, else None. Khong lam gi neu chua co vi the dang theo doi
        cho symbol nay (on_position_opened chua duoc goi)."""
        highest = self._highest.get(bar.symbol)
        if highest is None:
            return None
        highest = max(highest, bar.high)
        self._highest[bar.symbol] = highest

        if atr is None:
            return None
        stop_level = highest - atr * self.sl_multiplier
        if bar.low <= stop_level:
            return min(bar.open, stop_level)
        return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_trailing_stop.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add trading/trailing_stop.py tests/test_trailing_stop.py
git commit -m "feat: add TrailingStopManager for ATR trailing stop-loss"
```

---

### Task 2: `PaperBroker.force_exit()`

**Files:**
- Modify: `trading/paper_broker.py:1-25`
- Test: `tests/test_paper_broker.py`

**Interfaces:**
- Consumes: `Position` (from `trading.broker`, fields `symbol`, `qty`,
  `avg_price`) — caller must ensure `positions[symbol].qty > 0` before
  calling (same assumption `on_bar()`'s existing SELL branch makes).
- Produces: `PaperBroker.force_exit(symbol: str, price: float, ts:
  datetime) -> Fill`.

- [ ] **Step 1: Run GitNexus impact check before editing**

Run (MCP tool):
```
mcp__gitnexus__impact({ target: "PaperBroker", direction: "upstream", repo: "AI_auto_trading_system", file_path: "trading/paper_broker.py" })
```
Report the risk level before continuing. Adding a new method should not
show any existing callers affected (nothing calls a method that doesn't
exist yet) — if the tool reports unexpected existing callers of a method
named `force_exit`, STOP and report back.

- [ ] **Step 2: Write the failing test**

Add to `tests/test_paper_broker.py` (the file already has a module-level
`bar(o, h, l, c, sym="VCB", m=0)` helper — reuse it, don't redefine it):

```python
def test_force_exit_closes_full_position_and_computes_pnl():
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("VCB", "BUY", 100))
    b.on_bar(bar(10.0, 10.0, 10.0, 10.0))
    entry_price = b.positions["VCB"].avg_price

    fill = b.force_exit("VCB", price=9.0, ts=datetime(2026, 7, 15, 9, 10, tzinfo=TZ))

    expected_fee = 9.0 * 100 * (b.fee_rate + b.sell_tax_rate)
    expected_pnl = (9.0 - entry_price) * 100 - expected_fee
    assert fill.symbol == "VCB" and fill.side == "SELL" and fill.qty == 100
    assert abs(fill.price - 9.0) < 1e-9
    assert abs(fill.fee - expected_fee) < 1e-9
    assert fill.pnl is not None and abs(fill.pnl - expected_pnl) < 1e-6
    assert b.position_qty("VCB") == 0
    assert b.positions["VCB"].avg_price == 0.0
    assert b.realized_pnl == fill.pnl
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_paper_broker.py::test_force_exit_closes_full_position_and_computes_pnl -v`
Expected: FAIL with `AttributeError: 'PaperBroker' object has no attribute 'force_exit'`

- [ ] **Step 4: Implement `force_exit()`**

In `trading/paper_broker.py`, add the `datetime` import at the top:

```python
from datetime import datetime

from trading.broker import Fill, Position
from trading.models import Bar
from trading.strategy import Signal
```

Add the new method after `submit()` (right before `on_bar()`):

```python
    def force_exit(self, symbol: str, price: float, ts: datetime) -> Fill:
        """Dong TOAN BO vi the dang giu ngay lap tuc tai `price` - dung boi
        trailing stop. KHONG qua hang doi self._pending nhu submit()/on_bar()
        (khong co do tre 1 bar). Gia dinh caller da xac nhan vi the dang mo
        (qty > 0) truoc khi goi, giong cach on_bar()'s SELL branch gia dinh."""
        pos = self.positions[symbol]
        qty = pos.qty
        gross = price * qty
        fee = gross * self.fee_rate + gross * self.sell_tax_rate
        pnl = (price - pos.avg_price) * qty - fee
        self.realized_pnl += pnl
        self.cash += gross - fee
        pos.qty = 0
        pos.avg_price = 0.0
        return Fill(symbol, "SELL", qty, price, fee, ts, pnl)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_paper_broker.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add trading/paper_broker.py tests/test_paper_broker.py
git commit -m "feat: add PaperBroker.force_exit() for immediate same-bar position close"
```

---

### Task 3: Wire trailing stop into `process_bar()` and `run_backtest()`

**Files:**
- Modify: `trading/engine/logic.py:1-41`
- Modify: `trading/backtest.py:1-53`, `trading/backtest.py:84-114` (call-site construction)
- Modify: `trading/engine/main.py:13-45`, `trading/engine/main.py:98`
- Test: `tests/test_engine_logic.py`, `tests/test_backtest.py`

**Interfaces:**
- Consumes: `TrailingStopManager` (Task 1) — `.on_position_opened()`,
  `.on_position_closed()`, `.check()`. `PaperBroker.force_exit()` (Task 2).
- Produces: `process_bar(bar, broker, strategy, risk, trailing_stop, marks,
  on_crossover=None) -> list[Fill]` (new parameter `trailing_stop` inserted
  before `marks`). `run_backtest(bars, strategy, risk, trailing_stop,
  capital) -> BacktestReport` (new parameter `trailing_stop` inserted
  before `capital`).

- [ ] **Step 1: Run GitNexus impact checks before editing**

Run:
```
mcp__gitnexus__impact({ target: "process_bar", direction: "upstream", repo: "AI_auto_trading_system", file_path: "trading/engine/logic.py" })
mcp__gitnexus__impact({ target: "run_backtest", direction: "upstream", repo: "AI_auto_trading_system", file_path: "trading/backtest.py" })
```
Report both risk levels. Confirm the callers match: `engine/main.py::run`
for `process_bar`; `backtest.py::main` for `run_backtest`; plus test files
for both.

- [ ] **Step 2: Update `trading/engine/logic.py`**

Replace the full contents of the file:

```python
from datetime import datetime
from typing import Callable

from trading.broker import Fill
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.strategies.sma_cross import Crossover, SmaCrossStrategy
from trading.trailing_stop import TrailingStopManager


def process_bar(
    bar: Bar,
    broker: PaperBroker,
    strategy: SmaCrossStrategy,
    risk: RiskManager,
    trailing_stop: TrailingStopManager,
    marks: dict[str, float],
    on_crossover: Callable[[Crossover, Bar], None] | None = None,
) -> list[Fill]:
    fills = broker.on_bar(bar)
    marks[bar.symbol] = bar.close
    for f in fills:
        if f.side == "BUY":
            trailing_stop.on_position_opened(f.symbol, f.price)
        else:
            trailing_stop.on_position_closed(f.symbol)

    signal = strategy.on_bar(bar, broker)
    crossover = strategy.last_crossover(bar.symbol)
    if on_crossover is not None and crossover is not None:
        on_crossover(crossover, bar)

    stop_price = None
    if broker.position_qty(bar.symbol) > 0:
        stop_price = trailing_stop.check(bar, strategy.last_atr(bar.symbol))

    if stop_price is not None:
        forced = broker.force_exit(bar.symbol, stop_price, bar.ts)
        trailing_stop.on_position_closed(bar.symbol)
        fills.append(forced)
    elif signal is not None:
        daily_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)
        sized = risk.approve_sized(
            signal,
            bar.close,
            strategy.last_atr(bar.symbol),
            broker.positions,
            daily_pnl,
            bar.ts.date(),
        )
        if sized is not None:
            broker.submit(sized)

    return fills


def bar_from_payload(data: dict) -> Bar:
    return Bar(
        symbol=data["symbol"],
        ts=datetime.fromisoformat(data["ts"]).astimezone(TZ),
        open=data["open"],
        high=data["high"],
        low=data["low"],
        close=data["close"],
        volume=data["volume"],
        source=data.get("source", "ssi"),
    )
```

- [ ] **Step 3: Update `trading/backtest.py`**

Read the file first (`cat trading/backtest.py`) since a formatter may have
reformatted lines from earlier work. Replace `run_backtest`'s signature and
body:

```python
def run_backtest(
    bars: list[Bar],
    strategy: SmaCrossStrategy,
    risk: RiskManager,
    trailing_stop: TrailingStopManager,
    capital: float,
) -> BacktestReport:
    broker = PaperBroker(capital)
    marks: dict[str, float] = {}
    all_fills: list[Fill] = []
    equity_curve: list[float] = [capital]

    for bar in bars:
        fills = broker.on_bar(bar)
        all_fills.extend(fills)
        marks[bar.symbol] = bar.close
        for f in fills:
            if f.side == "BUY":
                trailing_stop.on_position_opened(f.symbol, f.price)
            else:
                trailing_stop.on_position_closed(f.symbol)

        signal = strategy.on_bar(bar, broker)

        stop_price = None
        if broker.position_qty(bar.symbol) > 0:
            stop_price = trailing_stop.check(bar, strategy.last_atr(bar.symbol))

        if stop_price is not None:
            forced = broker.force_exit(bar.symbol, stop_price, bar.ts)
            trailing_stop.on_position_closed(bar.symbol)
            all_fills.append(forced)
        elif signal is not None:
            daily_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)
            sized = risk.approve_sized(
                signal,
                bar.close,
                strategy.last_atr(bar.symbol),
                broker.positions,
                daily_pnl,
                bar.ts.date(),
            )
            if sized is not None:
                broker.submit(sized)

        equity = broker.cash + sum(
            p.qty * marks.get(s, p.avg_price) for s, p in broker.positions.items()
        )
        equity_curve.append(equity)
```
(Leave everything after this point — the `peak`/`max_dd` loop through
`return BacktestReport(...)` — unchanged.)

Add the import at the top of the file, alongside the other `trading.*`
imports:
```python
from trading.trailing_stop import TrailingStopManager
```

In `main()` (near the bottom of the file), find:
```python
    strategy = STRATEGIES[args.strategy]()
    risk = RiskManager(capital=args.capital)
    report = run_backtest(bars, strategy, risk, args.capital)
```
Replace with:
```python
    strategy = STRATEGIES[args.strategy]()
    risk = RiskManager(capital=args.capital)
    trailing_stop = TrailingStopManager()
    report = run_backtest(bars, strategy, risk, trailing_stop, args.capital)
```

- [ ] **Step 4: Update `trading/engine/main.py`**

Add the import alongside the other `trading.*` imports:
```python
from trading.trailing_stop import TrailingStopManager
```

Find:
```python
    strategy = SmaCrossStrategy()
    risk = RiskManager(capital=CAPITAL)
    real_risk = RiskManager(capital=cfg.real_order_capital)
```
Replace with:
```python
    strategy = SmaCrossStrategy()
    risk = RiskManager(capital=CAPITAL)
    trailing_stop = TrailingStopManager()
    real_risk = RiskManager(capital=cfg.real_order_capital)
```

Find:
```python
            fills = process_bar(bar, broker, strategy, risk, marks, on_crossover=on_real_crossover)
```
Replace with:
```python
            fills = process_bar(
                bar, broker, strategy, risk, trailing_stop, marks, on_crossover=on_real_crossover
            )
```

- [ ] **Step 5: Update existing test call sites**

In `tests/test_engine_logic.py`, add the import:
```python
from trading.trailing_stop import TrailingStopManager
```
Then in each of the 4 existing tests that call `process_bar(...)`
(`test_process_bar_submits_and_next_bar_fills`,
`test_process_bar_calls_on_crossover_when_crossover_fires`,
`test_process_bar_does_not_call_on_crossover_when_no_crossover`,
`test_process_bar_calls_on_crossover_even_when_paper_signal_suppressed`):
add `trailing_stop = TrailingStopManager()` next to the existing `risk =
RiskManager(...)` line, and add `trailing_stop` as the 5th positional
argument in every `process_bar(...)` call in that test (immediately after
`risk`, before `marks`).

In `tests/test_backtest.py`, add the import:
```python
from trading.trailing_stop import TrailingStopManager
```
Then in each of the 3 existing tests that call `run_backtest(...)`
(`test_deterministic_same_input_same_output`,
`test_report_has_at_least_one_round_trip_trade`,
`test_ending_cash_reflects_fees_when_no_trades`): add
`trailing_stop = TrailingStopManager()` (a fresh instance per call — note
`test_deterministic_same_input_same_output` already constructs two separate
`RiskManager` instances for its two `run_backtest` calls; do the same for
`TrailingStopManager`, one fresh instance per call, so state doesn't leak
between the two runs) next to the `RiskManager(...)` construction, and add
`trailing_stop` as the 4th positional argument in every `run_backtest(...)`
call (immediately after `risk`, before `capital`).

- [ ] **Step 6: Write the new integration test**

Add to `tests/test_engine_logic.py` (uses the module's existing `bar_at(i,
close, sym="VCB")` helper — reuse it, don't redefine it):

```python
def test_trailing_stop_exits_before_bear_crossover_would_fire():
    broker = PaperBroker(capital=100_000_000)
    strategy = SmaCrossStrategy(fast=2, slow=4, atr_period=1, atr_pct_threshold=0.0)
    risk = RiskManager(capital=100_000_000)
    trailing_stop = TrailingStopManager(sl_multiplier=1.0)
    marks: dict[str, float] = {}

    # Tang manh 10->23 (bull crossover + vi the mo), roi giat lui vua phai
    # xuong 21 - du de cham trailing stop (theo ATR%1.0) nhung KHONG du de
    # lam MA (fast=2,slow=4) dao chieu thanh bear crossover trong chuoi nay.
    prices = [10, 10, 10, 10, 20, 21, 22, 23, 21]
    all_fills = []
    crossovers = []
    for i, p in enumerate(prices):
        fills = process_bar(bar_at(i, p), broker, strategy, risk, trailing_stop, marks)
        all_fills.extend(fills)
        crossovers.append(strategy.last_crossover("VCB"))

    sell_fills = [f for f in all_fills if f.side == "SELL"]
    assert len(sell_fills) == 1
    assert sell_fills[0].price == 21.0
    assert broker.position_qty("VCB") == 0
    # Crossover KHONG BAO GIO thanh "bear" trong ca chuoi nay - chung minh
    # lenh thoat den tu trailing stop, khong phai tu crossover.
    assert "bear" not in crossovers
```

- [ ] **Step 7: Run the targeted test files**

Run: `uv run pytest tests/test_engine_logic.py tests/test_backtest.py tests/test_paper_broker.py tests/test_trailing_stop.py tests/test_risk.py tests/test_sma_cross.py -v`

Expected: all PASS, including the new test from Step 6. If any of the 7
pre-existing `test_backtest.py`/`test_engine_logic.py` tests fail: read the
failure carefully. A trailing stop can only add an *earlier or coincident*
exit opportunity compared to before — it should not change whether a round
trip trade completes, only possibly *which* fill closes it and at what
price. If a loose bound (like `r.trades >= 1`) fails, the likely cause is
the same category covered in the position-sizing plan (an unrealistic
synthetic price swing interacting with a constructor default) — the fix is
adjusting that specific test's price sequence or constructor args, not
changing `trading/trailing_stop.py`'s or `trading/paper_broker.py`'s logic
from Tasks 1–2.

- [ ] **Step 8: Run the full unit test suite**

Run: `uv run pytest -m "not integration" -v`
Expected: all PASS (should meet or exceed the pre-change count of 111).

- [ ] **Step 9: Run GitNexus detect-changes before committing**

Run:
```
mcp__gitnexus__detect_changes({ repo: "AI_auto_trading_system", scope: "all" })
```
Confirm the changed/affected symbols match this task's scope
(`process_bar`, `run_backtest`, `engine/main.py::run`, plus their test
files and the new `TrailingStopManager`/`force_exit` symbols from Tasks
1–2) and no `real_orders.py` symbols appear as changed.

- [ ] **Step 10: Commit**

```bash
git add trading/engine/logic.py trading/backtest.py trading/engine/main.py tests/test_engine_logic.py tests/test_backtest.py
git commit -m "feat: wire ATR trailing stop into paper-trading call sites"
```

---

### Task 4: Re-index GitNexus and final verification

**Files:** none (verification only)

- [ ] **Step 1: Re-index GitNexus**

Run: `npx gitnexus analyze`

- [ ] **Step 2: Run the complete unit test suite one more time**

Run: `uv run pytest -m "not integration" -v`
Expected: all PASS.

- [ ] **Step 3: Confirm `real_orders.py` is untouched**

Run: `git diff main...HEAD -- trading/real_orders.py` (or `git log
--oneline trading/real_orders.py` since this plan started) — expect no
output / no new commits touching this file.

- [ ] **Step 4: Report back**

Summarize: final test count, confirmation `real_orders.py` was never
touched, and the GitNexus risk levels observed in each task's Step 1 impact
check.
