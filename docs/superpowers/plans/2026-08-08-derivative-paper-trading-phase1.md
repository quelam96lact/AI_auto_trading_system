# Derivative (VN30F1M) Paper-Trading Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a paper-trading (simulated) long/short position model, a
simple risk gate, and a backtest entrypoint for the VN30F1M derivative
contract (`41I1G8000`), reusing `SmaCrossStrategy.compute_crossover()`
unmodified. No real order placement, no live collector/engine wiring — see
`docs/superpowers/specs/2026-08-08-derivative-paper-trading-phase1-design.md`
for the full rationale.

**Architecture:** Three new, independent modules parallel the existing
equity paper-trading stack without touching it: `DerivativePaperBroker`
(signed `qty` — negative means short — unlike equity `PaperBroker`, which
never goes short), `DerivativeRiskManager` (fixed `max_contracts` +
`max_daily_loss_pct` halt, no real margin model — none exists yet),
and `run_derivative_backtest()` (parallels `trading/backtest.py::run_backtest()`,
reuses its `BacktestReport` dataclass). Position-gating logic (which
direction to open/close on a crossover) lives in the backtest loop itself,
calling `strategy.compute_crossover(bar)` directly — the same pure function
`real_orders.py` already calls independently of `PaperBroker`.

**Tech Stack:** Python 3.11, pytest (`uv run pytest`), no new dependencies.

## Global Constraints

- Paper-trading and signal-only. No `place_order`/`cancel_order`/
  `AsyncTrading`/`AsyncTradingService` anywhere in this plan.
- Backtest-only. No changes to `trading/collector/*`, `trading/engine/*`,
  or NATS/live streaming.
- Do not modify `trading/strategies/sma_cross.py`, `trading/paper_broker.py`,
  `trading/risk.py`, `trading/backtest.py`, `trading/engine/*`,
  `trading/collector/derivative_sync.py`. Only import from `trading/backtest.py`
  (its `BacktestReport` dataclass) — do not edit that file.
- Hardcoded contract symbol `"41I1G8000"` (VN30F1M front-month, confirmed
  real 2026-07-26, expires 2026-08-20). No roll-over logic.
- `DERIVATIVE_FEE_PER_CONTRACT = 2_700.0` VNĐ — explicitly an unverified
  placeholder (real SSI derivative fee schedule not yet confirmed), fine
  because this plan never touches real money.
- No ATR position sizing, no trailing stop. Fixed `qty=1` per position.
- Every new module/test file must carry the same "no guessing, verify
  against real data" discipline as the rest of the project — see the design
  spec's "Decisions" section for what's already verified vs. still a
  documented placeholder.

---

### Task 1: `DerivativePosition` / `DerivativePaperBroker`

**Files:**
- Create: `trading/derivative_position.py`
- Test: `tests/test_derivative_position.py` (new)

**Interfaces:**
- Consumes: `Fill` (from `trading.broker`, fields `symbol`, `side`, `qty`,
  `price`, `fee`, `ts`, `pnl`).
- Produces: `DerivativePosition(symbol: str, qty: int = 0, avg_price: float
  = 0.0)` (dataclass, `qty` can be negative). `DerivativePaperBroker(capital:
  float, fee_per_contract: float = DERIVATIVE_FEE_PER_CONTRACT)`,
  `.position_qty(symbol: str) -> int` (signed), `.open_long(symbol: str,
  qty: int, price: float, ts: datetime) -> Fill`, `.open_short(symbol: str,
  qty: int, price: float, ts: datetime) -> Fill`, `.close(symbol: str,
  price: float, ts: datetime) -> Fill`. `.positions: dict[str,
  DerivativePosition]`, `.cash: float`, `.realized_pnl: float`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_derivative_position.py`:

```python
from datetime import datetime

from trading.calendar_vn import TZ
from trading.derivative_position import DerivativePaperBroker

CAP = 100_000_000
SYM = "41I1G8000"
TS = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
FEE = 2_700.0


def test_open_long_then_close_computes_pnl_fee_cash():
    b = DerivativePaperBroker(capital=CAP, fee_per_contract=FEE)
    open_fill = b.open_long(SYM, qty=1, price=1900.0, ts=TS)

    assert open_fill.side == "BUY" and open_fill.qty == 1
    assert open_fill.pnl is None
    assert abs(open_fill.fee - FEE) < 1e-9
    assert b.position_qty(SYM) == 1
    assert abs(b.cash - (CAP - FEE)) < 1e-9

    close_fill = b.close(SYM, price=1910.0, ts=TS)
    expected_pnl = (1910.0 - 1900.0) * 1 - FEE

    assert close_fill.side == "SELL" and close_fill.qty == 1
    assert abs(close_fill.pnl - expected_pnl) < 1e-9
    assert b.position_qty(SYM) == 0
    assert b.positions[SYM].avg_price == 0.0
    assert abs(b.realized_pnl - expected_pnl) < 1e-9
    assert abs(b.cash - (CAP - FEE + expected_pnl)) < 1e-9


def test_open_short_then_close_computes_pnl_for_price_drop():
    b = DerivativePaperBroker(capital=CAP, fee_per_contract=FEE)
    open_fill = b.open_short(SYM, qty=1, price=1900.0, ts=TS)

    assert open_fill.side == "SELL" and open_fill.qty == 1
    assert open_fill.pnl is None
    assert b.position_qty(SYM) == -1

    close_fill = b.close(SYM, price=1880.0, ts=TS)  # gia giam = lai cho short
    expected_pnl = (1900.0 - 1880.0) * 1 - FEE

    assert close_fill.side == "BUY" and close_fill.qty == 1
    assert abs(close_fill.pnl - expected_pnl) < 1e-9
    assert b.position_qty(SYM) == 0
    assert abs(b.realized_pnl - expected_pnl) < 1e-9


def test_open_short_then_close_at_higher_price_is_a_loss():
    b = DerivativePaperBroker(capital=CAP, fee_per_contract=FEE)
    b.open_short(SYM, qty=1, price=1900.0, ts=TS)

    close_fill = b.close(SYM, price=1920.0, ts=TS)  # gia tang = lo cho short
    expected_pnl = (1900.0 - 1920.0) * 1 - FEE

    assert abs(close_fill.pnl - expected_pnl) < 1e-9
    assert close_fill.pnl < 0


def test_position_qty_zero_for_unknown_symbol():
    b = DerivativePaperBroker(capital=CAP)
    assert b.position_qty("UNKNOWN") == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_derivative_position.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'trading.derivative_position'`

- [ ] **Step 3: Implement `trading/derivative_position.py`**

```python
from dataclasses import dataclass
from datetime import datetime

from trading.broker import Fill

# VNĐ/hợp đồng — biểu phí phái sinh thật của SSI CHƯA được xác nhận (khác
# equity, phí % giá trị). Placeholder cho paper-trading — không tiền thật,
# xem docs/superpowers/specs/2026-08-08-derivative-paper-trading-phase1-design.md.
DERIVATIVE_FEE_PER_CONTRACT = 2_700.0


@dataclass
class DerivativePosition:
    symbol: str
    qty: int = 0  # CÓ THỂ ÂM (short), DƯƠNG (long), 0 (flat)
    avg_price: float = 0.0


class DerivativePaperBroker:
    """Paper broker cho hợp đồng phái sinh (long/short, T+0, không có khái
    niệm settlement kiểu cổ phiếu). KHÔNG mô phỏng ký quỹ (margin) — cash
    chỉ trừ phí + cộng/trừ PnL đã thực hiện, không khoá vốn theo margin thật
    (chưa có số margin thật/hợp đồng để mô phỏng — xem spec)."""

    def __init__(
        self,
        capital: float,
        fee_per_contract: float = DERIVATIVE_FEE_PER_CONTRACT,
    ):
        self.capital = capital
        self.cash = capital
        self.fee_per_contract = fee_per_contract
        self.positions: dict[str, DerivativePosition] = {}
        self.realized_pnl = 0.0

    def position_qty(self, symbol: str) -> int:
        pos = self.positions.get(symbol)
        return pos.qty if pos else 0

    def open_long(self, symbol: str, qty: int, price: float, ts: datetime) -> Fill:
        """Mở vị thế long (BUY-to-open). Giả định caller đã xác nhận đang
        flat (position_qty(symbol) == 0) trước khi gọi — không tự kiểm tra,
        giống cách PaperBroker.on_bar()'s SELL branch giả định vị thế hợp
        lệ."""
        fee = qty * self.fee_per_contract
        pos = self.positions.setdefault(symbol, DerivativePosition(symbol))
        pos.qty = qty
        pos.avg_price = price
        self.cash -= fee
        return Fill(symbol, "BUY", qty, price, fee, ts, None)

    def open_short(self, symbol: str, qty: int, price: float, ts: datetime) -> Fill:
        """Mở vị thế short (SELL-to-open). Giả định caller đã xác nhận đang
        flat trước khi gọi — không tự kiểm tra."""
        fee = qty * self.fee_per_contract
        pos = self.positions.setdefault(symbol, DerivativePosition(symbol))
        pos.qty = -qty
        pos.avg_price = price
        self.cash -= fee
        return Fill(symbol, "SELL", qty, price, fee, ts, None)

    def close(self, symbol: str, price: float, ts: datetime) -> Fill:
        """Đóng toàn bộ vị thế đang mở (long hoặc short). Giả định caller đã
        xác nhận đang có vị thế mở (position_qty(symbol) != 0) trước khi
        gọi. side trả về phản ánh hành động thật: đóng long = SELL, đóng
        short (cover) = BUY."""
        pos = self.positions[symbol]
        qty = pos.qty
        filled_qty = abs(qty)
        fee = filled_qty * self.fee_per_contract
        if qty > 0:
            pnl = (price - pos.avg_price) * qty - fee
            side = "SELL"
        else:
            pnl = (pos.avg_price - price) * filled_qty - fee
            side = "BUY"
        self.realized_pnl += pnl
        self.cash += pnl
        pos.qty = 0
        pos.avg_price = 0.0
        return Fill(symbol, side, filled_qty, price, fee, ts, pnl)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_derivative_position.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add trading/derivative_position.py tests/test_derivative_position.py
git commit -m "feat: add DerivativePaperBroker for long/short paper positions"
```

---

### Task 2: `DerivativeRiskManager`

**Files:**
- Create: `trading/derivative_risk.py`
- Test: `tests/test_derivative_risk.py` (new)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `DerivativeRiskManager(capital: float, max_contracts: int = 1,
  max_daily_loss_pct: float = 0.03)`, `.halted_date: date | None`,
  `.approve_open(side: Literal["long", "short"], current_qty: int,
  daily_pnl: float, today: date) -> bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_derivative_risk.py`:

```python
from datetime import date

from trading.derivative_risk import DerivativeRiskManager


def test_approve_open_allows_first_open_when_flat():
    risk = DerivativeRiskManager(capital=100_000_000, max_contracts=1)
    assert risk.approve_open("long", current_qty=0, daily_pnl=0.0, today=date(2026, 8, 8)) is True


def test_approve_open_blocks_beyond_max_contracts():
    risk = DerivativeRiskManager(capital=100_000_000, max_contracts=1)
    # Da co 1 hop dong dang mo (current_qty=1) - mo them se vuot max_contracts=1.
    assert risk.approve_open("long", current_qty=1, daily_pnl=0.0, today=date(2026, 8, 8)) is False


def test_approve_open_blocks_when_daily_loss_exceeds_threshold():
    risk = DerivativeRiskManager(capital=100_000_000, max_daily_loss_pct=0.03)
    today = date(2026, 8, 8)
    # Lo vuot 3% von (-3,000,000) -> halt ngay lan goi nay.
    assert risk.approve_open("long", current_qty=0, daily_pnl=-3_000_001, today=today) is False
    assert risk.halted_date == today


def test_approve_open_stays_blocked_rest_of_day_even_if_pnl_recovers():
    risk = DerivativeRiskManager(capital=100_000_000, max_daily_loss_pct=0.03)
    today = date(2026, 8, 8)
    risk.approve_open("long", current_qty=0, daily_pnl=-3_000_001, today=today)
    # Cung ngay, daily_pnl da hoi phuc ve 0 - van bi chan vi halted_date da khoa ca ngay.
    assert risk.approve_open("short", current_qty=0, daily_pnl=0.0, today=today) is False


def test_halt_does_not_persist_to_next_day():
    risk = DerivativeRiskManager(capital=100_000_000, max_daily_loss_pct=0.03)
    day1 = date(2026, 8, 8)
    day2 = date(2026, 8, 9)
    risk.approve_open("long", current_qty=0, daily_pnl=-3_000_001, today=day1)
    assert risk.approve_open("long", current_qty=0, daily_pnl=0.0, today=day2) is True


def test_no_approve_close_method_exists_closes_are_never_gated():
    # Lenh dong vi the KHONG bi gate boi bat ky method nao cua
    # DerivativeRiskManager (khac approve_open danh cho lenh mo).
    risk = DerivativeRiskManager(capital=100_000_000)
    assert not hasattr(risk, "approve_close")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_derivative_risk.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'trading.derivative_risk'`

- [ ] **Step 3: Implement `trading/derivative_risk.py`**

```python
from dataclasses import dataclass, field
from datetime import date
from typing import Literal


@dataclass
class DerivativeRiskManager:
    """Giới hạn risk đơn giản cho paper-trading phái sinh — KHÔNG phải
    margin-call model thật (account phái sinh chưa từng giao dịch, chưa có
    số ký quỹ/hợp đồng thật để đối chiếu). Xem spec
    docs/superpowers/specs/2026-08-08-derivative-paper-trading-phase1-design.md."""

    capital: float
    max_contracts: int = 1
    max_daily_loss_pct: float = 0.03
    halted_date: date | None = field(default=None, init=False, repr=False)

    def _halt_check(self, daily_pnl: float, today: date) -> bool:
        if self.halted_date == today:
            return True
        if daily_pnl <= -self.capital * self.max_daily_loss_pct:
            self.halted_date = today
            return True
        return False

    def approve_open(
        self,
        side: Literal["long", "short"],
        current_qty: int,
        daily_pnl: float,
        today: date,
    ) -> bool:
        """Chỉ gate lệnh MỞ vị thế mới (long hoặc short) — KHÔNG gate lệnh
        đóng (đóng vị thế đang giữ luôn được phép, không có
        approve_close())."""
        if self._halt_check(daily_pnl, today):
            return False
        if abs(current_qty) >= self.max_contracts:
            return False
        return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_derivative_risk.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add trading/derivative_risk.py tests/test_derivative_risk.py
git commit -m "feat: add DerivativeRiskManager for paper-trading risk gating"
```

---

### Task 3: `run_derivative_backtest()` + CLI entrypoint

**Files:**
- Create: `trading/derivative_backtest.py`
- Test: `tests/test_derivative_backtest.py` (new)

**Interfaces:**
- Consumes: `DerivativePaperBroker`, `DerivativePosition` (Task 1),
  `DerivativeRiskManager` (Task 2), `BacktestReport` (from
  `trading.backtest`, **imported, not modified**), `SmaCrossStrategy`
  (from `trading.strategies.sma_cross`, used via its existing
  `compute_crossover(bar) -> Literal["bull", "bear"] | None` and `.qty`
  attribute — **unmodified**).
- Produces: `DERIVATIVE_SYMBOL = "41I1G8000"` (module constant),
  `run_derivative_backtest(bars: list[Bar], strategy: SmaCrossStrategy,
  risk: DerivativeRiskManager, capital: float) -> BacktestReport`.

- [ ] **Step 1: Run GitNexus impact check before editing `trading/backtest.py`'s neighborhood**

Run (MCP tool):
```
mcp__gitnexus__impact({ target: "BacktestReport", direction: "downstream", repo: "AI_auto_trading_system", file_path: "trading/backtest.py" })
```
This task only *imports* `BacktestReport` — it must not modify
`trading/backtest.py`. Report the result; if it shows anything suggesting
`BacktestReport`'s fields differ from what's used below, STOP and report
back instead of guessing.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_derivative_backtest.py`:

```python
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from trading.calendar_vn import TZ
from trading.derivative_backtest import DERIVATIVE_SYMBOL, run_derivative_backtest
from trading.derivative_risk import DerivativeRiskManager
from trading.models import Bar
from trading.strategies.sma_cross import SmaCrossStrategy

CAP = 100_000_000
FEE = 2_700.0


def bars_from_prices(prices: list[float], sym: str = DERIVATIVE_SYMBOL) -> list[Bar]:
    start = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
    return [
        Bar(sym, start + timedelta(minutes=5 * i), p, p, p, p, 100)
        for i, p in enumerate(prices)
    ]


def new_strategy() -> SmaCrossStrategy:
    # fast=2/slow=4, atr_pct_threshold=0.0: tat filter ATR% de crossover
    # khong bi che (cung ky thuat da dung trong tests/test_engine_logic.py
    # cho trailing-stop test) - qty=1 vi lot_size phai sinh = 1.
    return SmaCrossStrategy(fast=2, slow=4, qty=1, atr_period=1, atr_pct_threshold=0.0)


def test_long_cycle_bull_opens_long_then_bear_closes_it():
    # Chuoi gia da xac nhan that (chay qua SmaCrossStrategy.compute_crossover
    # truc tiep de lay index bull/bear that, khong doan tay): bull tai bar4
    # (close=11), bear tai bar10 (close=16).
    prices = [10, 10, 10, 10, 11, 13, 16, 20, 24, 20, 16, 12, 9, 7]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(bars, strategy, risk, CAP)

    assert len(report.fills) == 2
    open_fill, close_fill = report.fills
    assert open_fill.side == "BUY" and open_fill.qty == 1 and abs(open_fill.price - 11.0) < 1e-9
    assert close_fill.side == "SELL" and close_fill.qty == 1 and abs(close_fill.price - 16.0) < 1e-9
    expected_pnl = (16.0 - 11.0) * 1 - FEE
    assert abs(close_fill.pnl - expected_pnl) < 1e-9
    assert abs(report.realized_pnl - expected_pnl) < 1e-9
    assert report.trades == 1


def test_short_cycle_bear_opens_short_from_flat_then_bull_covers_it():
    # Chuoi gia da xac nhan that: bear tai bar5 (close=9, tu trang thai
    # flat - chua tung mo long truoc do), bull tai bar8 (close=12, cover).
    prices = [10, 11, 12, 14, 12, 9, 6, 9, 12, 15]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    risk = DerivativeRiskManager(capital=CAP, max_contracts=1)

    report = run_derivative_backtest(bars, strategy, risk, CAP)

    assert len(report.fills) == 2
    open_fill, close_fill = report.fills
    assert open_fill.side == "SELL" and open_fill.qty == 1 and abs(open_fill.price - 9.0) < 1e-9
    assert close_fill.side == "BUY" and close_fill.qty == 1 and abs(close_fill.price - 12.0) < 1e-9
    expected_pnl = (9.0 - 12.0) * 1 - FEE
    assert abs(close_fill.pnl - expected_pnl) < 1e-9
    assert close_fill.pnl < 0
    assert abs(report.realized_pnl - expected_pnl) < 1e-9


def test_halted_day_blocks_new_open_after_loss_breaches_threshold():
    # Cung chuoi bull/bear cua test_long_cycle (bull bar4, bear bar10) roi
    # them 1 bull thu 2 tai bar15 (close=12) - da xac nhan that bang cach
    # chay qua compute_crossover truc tiep.
    prices = [10, 10, 10, 10, 11, 13, 16, 20, 24, 20, 16, 12, 9, 7, 9, 12, 16, 20]
    bars = bars_from_prices(prices)
    strategy = new_strategy()
    # Von nho de khoan lo round-trip dau tien ((16-11)*1-2700=-2695) vuot
    # nguong 3% cua 50,000 (=-1,500).
    risk = DerivativeRiskManager(capital=50_000, max_contracts=1, max_daily_loss_pct=0.03)

    report = run_derivative_backtest(bars, strategy, risk, 50_000)

    # Chi co dung 2 fill (mo bar4, dong bar10) - bull thu 2 tai bar15 KHONG
    # duoc mo vi da bi halt do lo round-trip dau vuot nguong.
    assert len(report.fills) == 2
    assert risk.halted_date is not None


def test_real_captured_ohlc_sample_runs_end_to_end():
    # Smoke test doi voi du lieu OHLC that da capture (Phase 0/khao sat
    # 2026-08-07) - dam bao code chay duoc voi shape response that, khong
    # chi bar tong hop. File nay gitignored (du lieu that), khong commit -
    # skip gon neu khong co san thay vi fail.
    sample_path = Path("scripts/.spike_derivative_ohlc_5m_2m_sample.json")
    if not sample_path.exists():
        pytest.skip("scripts/.spike_derivative_ohlc_5m_2m_sample.json khong co san (gitignored)")

    raw = json.loads(sample_path.read_text())
    bars = sorted(
        (
            Bar(
                row["symbol"],
                datetime.strptime(row["trading_date"], "%Y/%m/%d %H:%M:%S").replace(tzinfo=TZ),
                row["open_price"],
                row["high_price"],
                row["low_price"],
                row["close_price"],
                int(row["volume"]),
            )
            for row in raw
        ),
        key=lambda b: b.ts,
    )
    strategy = SmaCrossStrategy(qty=1)  # tham so mac dinh (fast=10/slow=20) - khong ep crossover
    risk = DerivativeRiskManager(capital=CAP)

    report = run_derivative_backtest(bars, strategy, risk, CAP)

    # Khong assert crossover cu the nao xay ra (du lieu that, khong kiem
    # soat duoc) - chi chung minh code chay het toan bo bar that ma khong
    # loi/crash, va bao cao co hinh dang hop le: moi fill "mo" (pnl=None)
    # phai co dung 1 fill "dong" (pnl khong None) di kem, tru toi da 1 vi
    # the con dang mo o cuoi chuoi du lieu (chua co bar nao dong no).
    opens = [f for f in report.fills if f.pnl is None]
    closes = [f for f in report.fills if f.pnl is not None]
    assert report.trades == len(closes)
    assert len(opens) - len(closes) in (0, 1)
    assert isinstance(report.realized_pnl, float)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_derivative_backtest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'trading.derivative_backtest'`

- [ ] **Step 4: Implement `trading/derivative_backtest.py`**

```python
import argparse
from datetime import datetime, timedelta

from trading.backtest import BacktestReport
from trading.broker import Fill
from trading.calendar_vn import TZ
from trading.config import load_config
from trading.derivative_position import DerivativePaperBroker
from trading.derivative_risk import DerivativeRiskManager
from trading.models import Bar
from trading.storage.db import Storage
from trading.strategies.sma_cross import SmaCrossStrategy

# VN30F1M front-month - xac nhan that 2026-07-26, dao han 2026-08-20.
# KHONG tu dong roll - xem spec.
DERIVATIVE_SYMBOL = "41I1G8000"


def _unrealized(broker: DerivativePaperBroker, marks: dict[str, float]) -> float:
    total = 0.0
    for symbol, pos in broker.positions.items():
        if pos.qty == 0 or symbol not in marks:
            continue
        mark = marks[symbol]
        if pos.qty > 0:
            total += (mark - pos.avg_price) * pos.qty
        else:
            total += (pos.avg_price - mark) * abs(pos.qty)
    return total


def run_derivative_backtest(
    bars: list[Bar],
    strategy: SmaCrossStrategy,
    risk: DerivativeRiskManager,
    capital: float,
) -> BacktestReport:
    broker = DerivativePaperBroker(capital)
    marks: dict[str, float] = {}
    all_fills: list[Fill] = []
    equity_curve: list[float] = [capital]

    for bar in bars:
        crossover = strategy.compute_crossover(bar)
        marks[bar.symbol] = bar.close
        net = broker.position_qty(bar.symbol)
        daily_pnl = broker.realized_pnl + _unrealized(broker, marks)
        today = bar.ts.date()

        if crossover == "bull" and net < 0:
            all_fills.append(broker.close(bar.symbol, bar.close, bar.ts))
        elif crossover == "bull" and net == 0:
            if risk.approve_open("long", net, daily_pnl, today):
                all_fills.append(
                    broker.open_long(bar.symbol, strategy.qty, bar.close, bar.ts)
                )
        elif crossover == "bear" and net > 0:
            all_fills.append(broker.close(bar.symbol, bar.close, bar.ts))
        elif crossover == "bear" and net == 0:
            if risk.approve_open("short", net, daily_pnl, today):
                all_fills.append(
                    broker.open_short(bar.symbol, strategy.qty, bar.close, bar.ts)
                )

        equity = broker.cash + _unrealized(broker, marks)
        equity_curve.append(equity)

    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak)

    close_fills = [f for f in all_fills if f.pnl is not None]
    wins = sum(1 for f in close_fills if f.pnl is not None and f.pnl > 0)

    return BacktestReport(
        fills=all_fills,
        ending_cash=broker.cash,
        realized_pnl=broker.realized_pnl,
        unrealized_pnl=_unrealized(broker, marks),
        max_drawdown=max_dd,
        win_rate=(wins / len(close_fills)) if close_fills else 0.0,
        trades=len(close_fills),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--capital", type=float, default=100_000_000.0)
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()

    cfg = load_config(args.config)
    storage = Storage(cfg.db_dsn)
    frm = datetime.strptime(args.frm, "%Y-%m-%d").replace(tzinfo=TZ)
    to = datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=TZ) + timedelta(days=1)

    bars = storage.read_bars(DERIVATIVE_SYMBOL, frm, to)

    strategy = SmaCrossStrategy(qty=1)
    risk = DerivativeRiskManager(capital=args.capital)
    report = run_derivative_backtest(bars, strategy, risk, args.capital)

    print(f"Bars replayed: {len(bars)}")
    print(f"Trades: {report.trades}  Win rate: {report.win_rate:.1%}")
    print(
        f"Realized PnL: {report.realized_pnl:,.0f}  Unrealized PnL: {report.unrealized_pnl:,.0f}"
    )
    print(
        f"Ending cash: {report.ending_cash:,.0f}  Max drawdown: {report.max_drawdown:.1%}"
    )


if __name__ == "__main__":
    main()
```

Note: `bars` for `DERIVATIVE_SYMBOL` must already exist in the `bars` table
before this CLI is useful — that's a one-off operational step using the
*existing* `scripts/backfill_history.py --symbols 41I1G8000 ...` (it
already accepts a `--symbols` override independent of `config.yaml`'s
`symbols` list — confirmed by reading the script; no code change needed
there), not part of this plan's code changes.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_derivative_backtest.py -v`
Expected: all PASS (4 tests pass; the real-data smoke test either PASSes or
SKIPs depending on whether the gitignored sample file is present locally —
both are acceptable outcomes, do not treat a SKIP as a failure).

- [ ] **Step 6: Run GitNexus detect-changes before committing**

Run:
```
mcp__gitnexus__detect_changes({ repo: "AI_auto_trading_system", scope: "all" })
```
Confirm the changed/affected symbols are limited to the three new modules
from Tasks 1–3 and their test files, and that no symbols in
`trading/strategies/sma_cross.py`, `trading/paper_broker.py`,
`trading/risk.py`, `trading/backtest.py`, `trading/engine/*`, or
`trading/collector/derivative_sync.py` appear as changed.

- [ ] **Step 7: Commit**

```bash
git add trading/derivative_backtest.py tests/test_derivative_backtest.py
git commit -m "feat: add derivative paper-trading backtest (VN30F1M, long/short)"
```

---

### Task 4: Full suite verification and report

**Files:** none (verification only)

- [ ] **Step 1: Run the full unit test suite**

Run: `uv run pytest -m "not integration" -v`
Expected: all PASS, including every test from Tasks 1–3.

- [ ] **Step 2: Confirm no forbidden files were touched**

Run: `git diff main...HEAD --stat -- trading/strategies/sma_cross.py trading/paper_broker.py trading/risk.py trading/backtest.py trading/engine/ trading/collector/derivative_sync.py`
Expected: empty output (no changes to any of these files/directories).

- [ ] **Step 3: Confirm no real order APIs were introduced**

Run: `grep -rn "place_order\|place_limit_order\|cancel_order\|AsyncTrading" trading/derivative_position.py trading/derivative_risk.py trading/derivative_backtest.py`
Expected: no matches.

- [ ] **Step 4: Report back**

Summarize: final test count (pass/skip breakdown for the real-data smoke
test), confirmation the 6 forbidden files/directories were never touched,
`gitnexus_detect_changes()` result from Task 3, and whether the real-data
smoke test ran (sample file present) or skipped in this environment.

Do not commit anything beyond what each task's Step already committed — no
final "wrap up" commit. Do not push.
