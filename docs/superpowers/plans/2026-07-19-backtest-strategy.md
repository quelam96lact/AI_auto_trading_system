# Backtest + Strategy Interface (Sub-project 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Interface `Strategy`/`Broker` dùng chung cho backtest và live; `PaperBroker` khớp lệnh giả lập; `RiskManager` chặn lệnh vượt giới hạn; resampler 5m→15m/1h; chiến lược mẫu SMA cross; CLI backtest đọc bar từ DB, phát lại, xuất báo cáo PnL/drawdown/win-rate.

**Bối cảnh:** Sub-project 2 trong roadmap `docs/superpowers/specs/2026-07-18-autotrading-system-design.md` §9. **Không phụ thuộc phiên giao dịch** — chạy được ngay, chỉ cần bar 5m có sẵn trong TimescaleDB (sub-project 1, Task 4 — schema `bars` đã tồn tại và test qua) để test CLI tích hợp; test đơn vị của backtest engine không cần DB (nhận `list[Bar]` thuần).

**Architecture:** Toàn bộ backtest chạy **in-memory** — không ghi `orders`/`positions`/`pnl_daily` xuống DB (các bảng này thuộc phạm vi sub-project 3, nơi Engine cần persist state qua restart; xem `Ghi chú riêng` cuối file). `PaperBroker` giữ vị thế/PnL trong bộ nhớ suốt một lần chạy backtest hoặc một phiên live; CLI chỉ đọc `bars` (read-only) qua `Storage.read_bars` đã có từ sub-project 1.

**Tech Stack:** Python ≥3.11 thuần (không thêm dependency mới), `pytest`.

## Global Constraints

- **Không commit/push:** agent thực thi KHÔNG chạy `git commit`/`git push`. Cuối mỗi task: dừng, báo cáo kết quả + bằng chứng test. Claude (planner) chạy `gitnexus_detect_changes`, audit, và commit.
- **GitNexus:** trước khi SỬA một hàm/class đã tồn tại từ task trước trong plan này, chạy `gitnexus_impact({target, direction: "upstream"})`, báo risk level.
- **Phạm vi phẫu thuật:** mỗi task chỉ tạo/sửa đúng file liệt kê trong `**Files**`. Phát hiện vấn đề ngoài phạm vi → báo cáo, không tự sửa. **Không đụng vào bất kỳ file nào của `trading/collector/*`, `trading/bus/*` — thuộc sub-project 1.**
- **Timezone:** mọi `datetime` tz-aware `Asia/Ho_Chi_Minh` (`from trading.calendar_vn import TZ`).
- **Test:** unit test thuần chạy `pytest -m "not integration"`; test cần Docker (Postgres) đánh dấu `@pytest.mark.integration`.
- **Tham số mặc định đã chốt (cấu hình được sau, không hardcode-và-quên — nhưng KHÔNG đưa vào `config/config.yaml`/`trading/config.py` trong plan này, đó là việc của sub-project 3 khi engine đọc config; ở đây truyền qua constructor/CLI arg với default):**
  - Vốn paper mặc định: **100,000,000 VND** (`--capital` CLI arg).
  - RiskManager: tối đa **5** vị thế mở đồng thời, giá trị 1 lệnh **BUY** ≤ **20%** vốn, lỗ tối đa **3%** vốn/ngày → chạm ngưỡng thì **chặn TOÀN BỘ lệnh (cả BUY và SELL) đến hết ngày** (đúng nghĩa "dừng giao dịch" trong spec — xem `Ghi chú riêng`).
  - Phí: **0.15%** phí giao dịch (cả mua và bán) + **0.1%** thuế bán (chỉ lệnh bán) — đúng §5.1 spec gốc.
  - Slippage: **5 bps (0.05%)** — bar `open` cộng/trừ slippage tùy chiều lệnh.
  - Khớp lệnh: **giá mở bar KẾ TIẾP** sau khi signal được tạo (không khớp ngay bar hiện tại).
  - SMA cross mẫu: MA nhanh **10** / MA chậm **20**, trên bar **15m**, khối lượng lệnh **100 cổ phiếu** (1 lô VN).
  - **Quyết định phạm vi:** giới hạn giá trị lệnh (20% vốn) chỉ áp cho **BUY** — lệnh SELL không bị chặn bởi giới hạn này để tránh kẹt vị thế không thoát được (spec không nói rõ, đây là quyết định kỹ thuật của plan này, ghi rõ để không âm thầm lệch ý).

---

### Task 1: Domain types (Signal/Context/Strategy/Fill/Position/Broker) + PaperBroker

**Files:**
- Create: `trading/strategy.py`, `trading/broker.py`, `trading/paper_broker.py`, `tests/test_paper_broker.py`

**Interfaces:**
- Produces:
  - `Signal(symbol: str, side: Literal["BUY","SELL"], qty: int)` — frozen dataclass, `trading/strategy.py`.
  - `Context` (Protocol): `position_qty(symbol: str) -> int`.
  - `Strategy` (Protocol): `on_bar(bar: Bar, context: Context) -> Signal | None`.
  - `Fill(symbol, side, qty, price, fee, ts, pnl: float | None = None)` — frozen dataclass, `trading/broker.py`. `pnl` chỉ có giá trị (khác `None`) ở lệnh SELL (lãi/lỗ đã trừ phí của riêng lệnh đó).
  - `Position(symbol, qty=0, avg_price=0.0)` — dataclass thường (mutable).
  - `Broker` (Protocol): `submit(signal) -> None`, `on_bar(bar) -> list[Fill]`, `position_qty(symbol) -> int`.
  - `PaperBroker(capital, fee_rate=0.0015, sell_tax_rate=0.001, slippage_bps=5)` — thỏa mãn cả `Broker` và `Context` (có `position_qty`). Thuộc tính đọc được: `cash`, `positions: dict[str, Position]`, `realized_pnl`. Method `unrealized_pnl(marks: dict[str, float]) -> float`.

- [ ] **Step 1: Viết test fail** — `tests/test_paper_broker.py`:

```python
from datetime import datetime

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.strategy import Signal


def bar(o, h, l, c, sym="VCB", m=0):
    return Bar(sym, datetime(2026, 7, 15, 9, m, tzinfo=TZ), o, h, l, c, 1000)


def test_no_pending_order_no_fill():
    b = PaperBroker(capital=100_000_000)
    assert b.on_bar(bar(10.0, 10.0, 10.0, 10.0)) == []


def test_buy_fills_with_fee_and_slippage():
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("VCB", "BUY", 100))
    fills = b.on_bar(bar(10.0, 10.0, 10.0, 10.0))
    assert len(fills) == 1
    f = fills[0]
    expected_price = 10.0 * (1 + 5 / 10_000)
    assert abs(f.price - expected_price) < 1e-9
    assert f.qty == 100 and f.pnl is None
    expected_fee = expected_price * 100 * 0.0015
    assert abs(f.fee - expected_fee) < 1e-9
    assert b.position_qty("VCB") == 100


def test_sell_computes_realized_pnl_and_caps_oversell():
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("VCB", "BUY", 100))
    b.on_bar(bar(10.0, 10.0, 10.0, 10.0))
    b.submit(Signal("VCB", "SELL", 9999))  # bán nhiều hơn đang giữ → cap về 100
    fills = b.on_bar(bar(11.0, 11.0, 11.0, 11.0, m=5))
    assert len(fills) == 1
    assert fills[0].qty == 100
    assert fills[0].pnl is not None
    assert b.position_qty("VCB") == 0
    assert b.realized_pnl == fills[0].pnl


def test_unrealized_pnl_uses_marks():
    b = PaperBroker(capital=100_000_000)
    b.submit(Signal("VCB", "BUY", 100))
    b.on_bar(bar(10.0, 10.0, 10.0, 10.0))
    pos = b.positions["VCB"]
    expected = (12.0 - pos.avg_price) * 100
    assert abs(b.unrealized_pnl({"VCB": 12.0}) - expected) < 1e-6
```

- [ ] **Step 2: `pytest tests/test_paper_broker.py -v`** → FAIL (module chưa tồn tại).

- [ ] **Step 3: Implement `trading/strategy.py`**

```python
from dataclasses import dataclass
from typing import Literal, Protocol

from trading.models import Bar

Side = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: Side
    qty: int


class Context(Protocol):
    def position_qty(self, symbol: str) -> int: ...


class Strategy(Protocol):
    def on_bar(self, bar: Bar, context: Context) -> Signal | None: ...
```

- [ ] **Step 4: Implement `trading/broker.py`**

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from trading.models import Bar
from trading.strategy import Signal


@dataclass(frozen=True)
class Fill:
    symbol: str
    side: str
    qty: int
    price: float
    fee: float
    ts: datetime
    pnl: float | None = None


@dataclass
class Position:
    symbol: str
    qty: int = 0
    avg_price: float = 0.0


class Broker(Protocol):
    def submit(self, signal: Signal) -> None: ...
    def on_bar(self, bar: Bar) -> list[Fill]: ...
    def position_qty(self, symbol: str) -> int: ...
```

- [ ] **Step 5: Implement `trading/paper_broker.py`**

```python
from trading.broker import Fill, Position
from trading.models import Bar
from trading.strategy import Signal

FEE_RATE = 0.0015       # phí giao dịch, áp cho cả mua và bán
SELL_TAX_RATE = 0.001   # thuế bán, chỉ áp cho lệnh bán
SLIPPAGE_BPS = 5


class PaperBroker:
    def __init__(self, capital: float, fee_rate: float = FEE_RATE,
                 sell_tax_rate: float = SELL_TAX_RATE, slippage_bps: float = SLIPPAGE_BPS):
        self.capital = capital
        self.cash = capital
        self.fee_rate = fee_rate
        self.sell_tax_rate = sell_tax_rate
        self.slippage_bps = slippage_bps
        self.positions: dict[str, Position] = {}
        self.realized_pnl = 0.0
        self._pending: dict[str, Signal] = {}

    def position_qty(self, symbol: str) -> int:
        pos = self.positions.get(symbol)
        return pos.qty if pos else 0

    def submit(self, signal: Signal) -> None:
        self._pending[signal.symbol] = signal

    def on_bar(self, bar: Bar) -> list[Fill]:
        signal = self._pending.pop(bar.symbol, None)
        if signal is None:
            return []
        qty = signal.qty
        if signal.side == "SELL":
            qty = min(qty, self.position_qty(bar.symbol))
            if qty <= 0:
                return []
        slip = bar.open * (self.slippage_bps / 10_000)
        price = bar.open + slip if signal.side == "BUY" else bar.open - slip
        gross = price * qty
        fee = gross * self.fee_rate + (gross * self.sell_tax_rate if signal.side == "SELL" else 0.0)

        pos = self.positions.setdefault(bar.symbol, Position(bar.symbol))
        pnl = None
        if signal.side == "BUY":
            new_qty = pos.qty + qty
            pos.avg_price = (pos.avg_price * pos.qty + gross) / new_qty
            pos.qty = new_qty
            self.cash -= gross + fee
        else:
            pnl = (price - pos.avg_price) * qty - fee
            self.realized_pnl += pnl
            self.cash += gross - fee
            pos.qty -= qty
            if pos.qty == 0:
                pos.avg_price = 0.0

        return [Fill(bar.symbol, signal.side, qty, price, fee, bar.ts, pnl)]

    def unrealized_pnl(self, marks: dict[str, float]) -> float:
        return sum((marks[s] - p.avg_price) * p.qty for s, p in self.positions.items()
                    if p.qty > 0 and s in marks)
```

- [ ] **Step 6: `pytest tests/test_paper_broker.py -v`** → PASS. **DỪNG — báo cáo planner.**

---

### Task 2: RiskManager

**Files:**
- Create: `trading/risk.py`, `tests/test_risk.py`

**Interfaces:**
- Consumes: `Signal` (Task 1), `Position` (Task 1)
- Produces: `RiskManager(capital, max_positions=5, max_order_value_pct=0.20, max_daily_loss_pct=0.03)` với `approve(signal: Signal, ref_price: float, positions: dict[str, Position], daily_pnl: float, today: date) -> bool`. Halt áp dụng cho **mọi** signal (BUY và SELL) trong ngày `today` đã halt; giới hạn giá trị lệnh + số vị thế chỉ áp cho `signal.side == "BUY"`.

- [ ] **Step 1: Viết test fail** — `tests/test_risk.py`:

```python
from datetime import date

from trading.broker import Position
from trading.risk import RiskManager
from trading.strategy import Signal

CAP = 100_000_000
D = date(2026, 7, 15)


def test_rejects_buy_order_value_over_limit():
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "BUY", 10_000)
    assert rm.approve(sig, ref_price=100_000, positions={}, daily_pnl=0, today=D) is False


def test_approves_within_limits():
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "BUY", 100)
    assert rm.approve(sig, ref_price=50_000, positions={}, daily_pnl=0, today=D) is True


def test_rejects_new_symbol_beyond_max_positions():
    rm = RiskManager(capital=CAP, max_positions=2)
    positions = {"A": Position("A", 100, 10), "B": Position("B", 100, 10)}
    sig = Signal("C", "BUY", 10)
    assert rm.approve(sig, ref_price=1_000, positions=positions, daily_pnl=0, today=D) is False


def test_allows_adding_to_already_held_symbol_beyond_max_positions():
    rm = RiskManager(capital=CAP, max_positions=2)
    positions = {"A": Position("A", 100, 10), "B": Position("B", 100, 10)}
    sig = Signal("A", "BUY", 10)
    assert rm.approve(sig, ref_price=1_000, positions=positions, daily_pnl=0, today=D) is True


def test_sell_not_blocked_by_order_value_limit():
    rm = RiskManager(capital=CAP)
    sig = Signal("VCB", "SELL", 10_000)  # giá trị rất lớn nhưng là lệnh thoát, không bị chặn
    assert rm.approve(sig, ref_price=100_000, positions={}, daily_pnl=0, today=D) is True


def test_halts_all_trading_for_rest_of_day_after_max_loss():
    rm = RiskManager(capital=CAP, max_daily_loss_pct=0.03)
    buy = Signal("VCB", "BUY", 10)
    sell = Signal("VCB", "SELL", 10)
    assert rm.approve(buy, ref_price=1_000, positions={}, daily_pnl=-3_000_001, today=D) is False
    assert rm.approve(sell, ref_price=1_000, positions={}, daily_pnl=0, today=D) is False  # vẫn halt
    assert rm.approve(buy, ref_price=1_000, positions={}, daily_pnl=0, today=date(2026, 7, 16)) is True
```

- [ ] **Step 2: `pytest tests/test_risk.py -v`** → FAIL.

- [ ] **Step 3: Implement `trading/risk.py`**

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
    _halted_date: date | None = field(default=None, init=False, repr=False)

    def approve(self, signal: Signal, ref_price: float, positions: dict[str, Position],
                daily_pnl: float, today: date) -> bool:
        if self._halted_date == today:
            return False
        if daily_pnl <= -self.capital * self.max_daily_loss_pct:
            self._halted_date = today
            return False
        if signal.side == "BUY":
            order_value = ref_price * signal.qty
            if order_value > self.capital * self.max_order_value_pct:
                return False
            held_symbols = {s for s, p in positions.items() if p.qty > 0}
            if signal.symbol not in held_symbols and len(held_symbols) >= self.max_positions:
                return False
        return True
```

- [ ] **Step 4: `pytest tests/test_risk.py -v`** → PASS. **DỪNG — báo cáo planner.**

---

### Task 3: Resampler (5m → 15m/1h)

**Files:**
- Create: `trading/resample.py`, `tests/test_resample.py`

**Interfaces:**
- Consumes: `Bar` (`trading/models.py`, đã có)
- Produces: `resample_bars(bars: list[Bar], target_minutes: int) -> list[Bar]` — gom bar cùng symbol vào bucket `target_minutes` (floor theo phút trong giờ, không phụ thuộc giờ mở phiên — với 15 chia hết 60 nên khớp ranh giới phiên VN tự nhiên). Input không cần sort trước; output sort theo `(symbol, ts)`.

- [ ] **Step 1: Viết test fail** — `tests/test_resample.py`:

```python
from datetime import datetime

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.resample import resample_bars


def b5(m, o, h, l, c, v=100, sym="VCB"):
    return Bar(sym, datetime(2026, 7, 15, 9, m, tzinfo=TZ), o, h, l, c, v)


def test_resamples_three_5m_bars_into_one_15m_bar():
    bars = [b5(0, 10, 11, 9, 10.5), b5(5, 10.5, 12, 10, 11), b5(10, 11, 11.5, 10.5, 11.2)]
    out = resample_bars(bars, 15)
    assert len(out) == 1
    r = out[0]
    assert (r.open, r.high, r.low, r.close, r.volume) == (10, 12, 9, 11.2, 300)
    assert r.ts == datetime(2026, 7, 15, 9, 0, tzinfo=TZ)


def test_symbols_kept_independent():
    bars = [b5(0, 1, 2, 1, 1.5, sym="VCB"), b5(0, 2, 3, 2, 2.5, sym="HPG")]
    out = resample_bars(bars, 15)
    assert {r.symbol for r in out} == {"VCB", "HPG"}


def test_incomplete_trailing_bucket_still_emitted():
    bars = [b5(0, 1, 1, 1, 1)]  # chỉ 1 bar 5m, chưa đủ 15m
    out = resample_bars(bars, 15)
    assert len(out) == 1 and out[0].volume == 100
```

- [ ] **Step 2: `pytest tests/test_resample.py -v`** → FAIL.

- [ ] **Step 3: Implement `trading/resample.py`**

```python
from collections import defaultdict
from datetime import datetime

from trading.models import Bar


def resample_bars(bars: list[Bar], target_minutes: int) -> list[Bar]:
    by_bucket: dict[tuple[str, datetime], list[Bar]] = defaultdict(list)
    for b in bars:
        by_bucket[(b.symbol, _bucket(b.ts, target_minutes))].append(b)

    out: list[Bar] = []
    for (symbol, bucket), group in sorted(by_bucket.items(), key=lambda kv: kv[0]):
        group.sort(key=lambda b: b.ts)
        out.append(Bar(
            symbol=symbol, ts=bucket,
            open=group[0].open, high=max(g.high for g in group),
            low=min(g.low for g in group), close=group[-1].close,
            volume=sum(g.volume for g in group), source=group[0].source,
        ))
    return out


def _bucket(ts: datetime, target_minutes: int) -> datetime:
    minute = (ts.minute // target_minutes) * target_minutes
    return ts.replace(minute=minute, second=0, microsecond=0)
```

- [ ] **Step 4: `pytest tests/test_resample.py -v`** → PASS. **DỪNG — báo cáo planner.**

---

### Task 4: Chiến lược SMA cross mẫu

**Files:**
- Create: `trading/strategies/__init__.py`, `trading/strategies/sma_cross.py`, `tests/test_sma_cross.py`

**Interfaces:**
- Consumes: `Bar`, `Context`, `Signal` (Task 1)
- Produces: `SmaCrossStrategy(fast: int = 10, slow: int = 20, qty: int = 100)` thỏa `Strategy` protocol. Tín hiệu BUY khi MA nhanh cắt lên MA chậm **và** đang không giữ vị thế; SELL khi MA nhanh cắt xuống MA chậm **và** đang giữ vị thế (bán toàn bộ số đang giữ). Không đủ `slow` bar lịch sử → không phát tín hiệu.

- [ ] **Step 1: Viết test fail** — `tests/test_sma_cross.py`:

```python
from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.strategies.sma_cross import SmaCrossStrategy


class FakeContext:
    def __init__(self, qty=0):
        self.qty = qty

    def position_qty(self, symbol):
        return self.qty


def bar_at(i, close):
    return Bar("VCB", datetime(2026, 7, 15, 9, 0, tzinfo=TZ) + timedelta(minutes=15 * i),
               close, close, close, close, 100)


def test_no_signal_before_enough_history():
    s = SmaCrossStrategy(fast=2, slow=4)
    ctx = FakeContext()
    for i, price in enumerate([10, 10, 10]):
        assert s.on_bar(bar_at(i, price), ctx) is None


def test_buy_signal_on_fast_crossing_above_slow():
    s = SmaCrossStrategy(fast=2, slow=4, qty=100)
    ctx = FakeContext(qty=0)
    prices = [10, 10, 10, 10, 20, 20]
    signals = [s.on_bar(bar_at(i, p), ctx) for i, p in enumerate(prices)]
    assert any(sig is not None and sig.side == "BUY" and sig.qty == 100 for sig in signals)


def test_sell_signal_when_holding_and_fast_crosses_below():
    s = SmaCrossStrategy(fast=2, slow=4, qty=100)
    ctx = FakeContext(qty=100)
    prices = [10, 10, 10, 10, 20, 20, 10, 10]
    signals = [s.on_bar(bar_at(i, p), ctx) for i, p in enumerate(prices)]
    assert any(sig is not None and sig.side == "SELL" for sig in signals)
```

- [ ] **Step 2: `pytest tests/test_sma_cross.py -v`** → FAIL.

- [ ] **Step 3: Implement `trading/strategies/__init__.py`** (rỗng) và `trading/strategies/sma_cross.py`:

```python
from collections import deque

from trading.models import Bar
from trading.strategy import Context, Signal


class SmaCrossStrategy:
    def __init__(self, fast: int = 10, slow: int = 20, qty: int = 100):
        self.fast = fast
        self.slow = slow
        self.qty = qty
        self._closes: dict[str, deque] = {}
        self._prev_above: dict[str, bool | None] = {}

    def on_bar(self, bar: Bar, context: Context) -> Signal | None:
        closes = self._closes.setdefault(bar.symbol, deque(maxlen=self.slow))
        closes.append(bar.close)
        if len(closes) < self.slow:
            return None

        values = list(closes)
        fast_ma = sum(values[-self.fast:]) / self.fast
        slow_ma = sum(values) / self.slow
        cur_above = fast_ma > slow_ma
        prev_above = self._prev_above.get(bar.symbol)
        self._prev_above[bar.symbol] = cur_above
        if prev_above is None:
            return None

        held = context.position_qty(bar.symbol)
        if cur_above and not prev_above and held == 0:
            return Signal(bar.symbol, "BUY", self.qty)
        if not cur_above and prev_above and held > 0:
            return Signal(bar.symbol, "SELL", held)
        return None
```

- [ ] **Step 4: `pytest tests/test_sma_cross.py -v`** → PASS. **DỪNG — báo cáo planner.**

---

### Task 5: Backtest engine (replay + báo cáo)

**Files:**
- Create: `trading/backtest.py` (chỉ phần engine, KHÔNG viết CLI/`main()` ở task này), `tests/test_backtest.py`

**Interfaces:**
- Consumes: `Bar`, `PaperBroker`, `RiskManager`, `Strategy` (Task 1–4)
- Produces: `BacktestReport(fills, ending_cash, realized_pnl, unrealized_pnl, max_drawdown, win_rate, trades)` — dataclass. `run_backtest(bars: list[Bar], strategy: Strategy, risk: RiskManager, capital: float) -> BacktestReport` — hàm THUẦN (không đọc DB/file); `bars` phải đã sort theo `(ts, symbol)` bởi caller. Chạy 2 lần cùng input → kết quả giống hệt (deterministic, không dùng `datetime.now()`/random).

- [ ] **Step 1: Viết test fail** — `tests/test_backtest.py`:

```python
from datetime import datetime, timedelta

from trading.backtest import run_backtest
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.risk import RiskManager
from trading.strategies.sma_cross import SmaCrossStrategy

CAP = 100_000_000


def make_bars(prices: list[float]) -> list[Bar]:
    start = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    return [Bar("VCB", start + timedelta(minutes=15 * i), p, p, p, p, 1000)
            for i, p in enumerate(prices)]


def test_deterministic_same_input_same_output():
    prices = [10] * 20 + [20] * 10 + [10] * 10
    bars = make_bars(prices)
    strategy = SmaCrossStrategy(fast=10, slow=20, qty=100)
    risk = RiskManager(capital=CAP)
    r1 = run_backtest(bars, strategy, risk, CAP)

    strategy2 = SmaCrossStrategy(fast=10, slow=20, qty=100)
    risk2 = RiskManager(capital=CAP)
    r2 = run_backtest(bars, strategy2, risk2, CAP)

    assert r1 == r2


def test_report_has_at_least_one_round_trip_trade():
    prices = [10] * 20 + [20] * 10 + [10] * 10
    bars = make_bars(prices)
    r = run_backtest(bars, SmaCrossStrategy(fast=10, slow=20, qty=100), RiskManager(capital=CAP), CAP)
    assert r.trades >= 1
    assert 0.0 <= r.win_rate <= 1.0
    assert r.max_drawdown >= 0.0


def test_ending_cash_reflects_fees_when_no_trades():
    bars = make_bars([10] * 5)  # chưa đủ 20 bar cho slow MA → không lệnh nào
    r = run_backtest(bars, SmaCrossStrategy(fast=10, slow=20, qty=100), RiskManager(capital=CAP), CAP)
    assert r.ending_cash == CAP
    assert r.trades == 0
```

- [ ] **Step 2: `pytest tests/test_backtest.py -v`** → FAIL (`BacktestReport` cần `__eq__` — dataclass thường tự có `__eq__` so sánh field-by-field, `fills: list[Fill]` với `Fill` là frozen dataclass cũng so sánh được — không cần thêm gì).

- [ ] **Step 3: Implement `trading/backtest.py`**

```python
from dataclasses import dataclass, field

from trading.broker import Fill
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.strategy import Strategy


@dataclass
class BacktestReport:
    fills: list[Fill] = field(default_factory=list)
    ending_cash: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    trades: int = 0


def run_backtest(bars: list[Bar], strategy: Strategy, risk: RiskManager, capital: float) -> BacktestReport:
    broker = PaperBroker(capital)
    marks: dict[str, float] = {}
    all_fills: list[Fill] = []
    equity_curve: list[float] = [capital]

    for bar in bars:
        all_fills.extend(broker.on_bar(bar))
        marks[bar.symbol] = bar.close

        signal = strategy.on_bar(bar, broker)
        if signal is not None:
            daily_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)
            if risk.approve(signal, bar.close, broker.positions, daily_pnl, bar.ts.date()):
                broker.submit(signal)

        equity = broker.cash + sum(
            p.qty * marks.get(s, p.avg_price) for s, p in broker.positions.items())
        equity_curve.append(equity)

    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak)

    sell_fills = [f for f in all_fills if f.side == "SELL"]
    wins = sum(1 for f in sell_fills if f.pnl is not None and f.pnl > 0)

    return BacktestReport(
        fills=all_fills,
        ending_cash=broker.cash,
        realized_pnl=broker.realized_pnl,
        unrealized_pnl=broker.unrealized_pnl(marks),
        max_drawdown=max_dd,
        win_rate=(wins / len(sell_fills)) if sell_fills else 0.0,
        trades=len(sell_fills),
    )
```

- [ ] **Step 4: `pytest tests/test_backtest.py -v`** → PASS. **DỪNG — báo cáo planner.**

---

### Task 6: CLI backtest + kiểm chứng tích hợp qua DB thật

**Điều kiện:** Docker (`postgres`) đang chạy; không cần phiên giao dịch.

**Files:**
- Create: `tests/test_backtest_cli.py`
- Modify: `trading/backtest.py` (thêm `STRATEGIES` registry + `main()`, KHÔNG sửa `run_backtest`/`BacktestReport` đã viết ở Task 5)

**Interfaces:**
- Consumes: `Storage.read_bars` (sub-project 1, đã có), `resample_bars` (Task 3), `run_backtest` (Task 5)
- Produces: CLI `python -m trading.backtest --strategy sma_cross --symbols VCB,HPG --from 2026-01-01 --to 2026-06-30 --tf 15m [--capital 100000000] [--config config/config.yaml]` — đọc bar từ DB theo từng symbol, resample nếu `--tf` khác `5m`, gộp + sort `(ts, symbol)`, chạy `run_backtest`, in báo cáo ra stdout.

- [ ] **Step 1: Viết integration test fail** — `tests/test_backtest_cli.py`:

```python
import os
from datetime import datetime, timedelta

import pytest

from trading.backtest import STRATEGIES, run_backtest
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.resample import resample_bars
from trading.risk import RiskManager
from trading.storage.db import Storage

DSN = os.environ.get("DB_DSN", "postgresql://trading:trading@localhost:5432/trading")
pytestmark = pytest.mark.integration


@pytest.fixture
def storage():
    s = Storage(DSN)
    s.init_schema()
    with s.conn() as c:
        c.execute("DELETE FROM bars WHERE symbol = 'BTCLI'")
    return s


def _seed_bars(storage, n=25):
    start = datetime(2026, 7, 1, 9, 0, tzinfo=TZ)
    prices = [10.0] * 20 + [20.0] * (n - 20)
    bars = [Bar("BTCLI", start + timedelta(minutes=5 * i), p, p, p, p, 1000)
            for i, p in enumerate(prices)]
    storage.write_bars(bars)
    return bars


def test_cli_registry_has_sma_cross():
    assert "sma_cross" in STRATEGIES


def test_read_resample_replay_is_deterministic_from_real_db(storage):
    _seed_bars(storage, n=25)
    frm = datetime(2026, 7, 1, tzinfo=TZ)
    to = datetime(2026, 7, 2, tzinfo=TZ)

    def run_once():
        rows = storage.read_bars("BTCLI", frm, to)
        resampled = resample_bars(rows, 15)
        return run_backtest(resampled, STRATEGIES["sma_cross"](), RiskManager(capital=100_000_000), 100_000_000)

    r1, r2 = run_once(), run_once()
    assert r1 == r2
    assert len(resample_bars(storage.read_bars("BTCLI", frm, to), 15)) > 0
```

- [ ] **Step 2: `pytest tests/test_backtest_cli.py -v`** → FAIL (`STRATEGIES` chưa tồn tại).

- [ ] **Step 3: Thêm vào cuối `trading/backtest.py`** (nối tiếp file Task 5, không xóa gì đã có):

```python
import argparse
from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.config import load_config
from trading.resample import resample_bars
from trading.storage.db import Storage
from trading.strategies.sma_cross import SmaCrossStrategy

STRATEGIES = {"sma_cross": lambda: SmaCrossStrategy()}
_TF_MINUTES = {"15m": 15, "1h": 60}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True, choices=list(STRATEGIES))
    ap.add_argument("--symbols", required=True, help="VD: VCB,HPG")
    ap.add_argument("--from", dest="frm", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="to", required=True, help="YYYY-MM-DD")
    ap.add_argument("--tf", default="5m", choices=["5m", "15m", "1h"])
    ap.add_argument("--capital", type=float, default=100_000_000.0)
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()

    cfg = load_config(args.config)
    storage = Storage(cfg.db_dsn)
    frm = datetime.strptime(args.frm, "%Y-%m-%d").replace(tzinfo=TZ)
    to = datetime.strptime(args.to, "%Y-%m-%d").replace(tzinfo=TZ) + timedelta(days=1)

    bars: list[Bar] = []
    for sym in args.symbols.split(","):
        rows = storage.read_bars(sym, frm, to)
        bars.extend(rows if args.tf == "5m" else resample_bars(rows, _TF_MINUTES[args.tf]))
    bars.sort(key=lambda b: (b.ts, b.symbol))

    strategy = STRATEGIES[args.strategy]()
    risk = RiskManager(capital=args.capital)
    report = run_backtest(bars, strategy, risk, args.capital)

    print(f"Bars replayed: {len(bars)}")
    print(f"Trades: {report.trades}  Win rate: {report.win_rate:.1%}")
    print(f"Realized PnL: {report.realized_pnl:,.0f}  Unrealized PnL: {report.unrealized_pnl:,.0f}")
    print(f"Ending cash: {report.ending_cash:,.0f}  Max drawdown: {report.max_drawdown:.1%}")


if __name__ == "__main__":
    main()
```

(Thêm `from trading.models import Bar` vào đầu file nếu chưa có từ Task 5 — kiểm tra trước khi thêm trùng import.)

- [ ] **Step 4: `pytest tests/test_backtest_cli.py -v`** (Docker đang chạy) → PASS.

- [ ] **Step 5: Chạy CLI thật trên dữ liệu đã backfill** (nếu sub-project 1 đã chạy backfill thật và có bar trong DB cho `config/config.yaml` symbols; nếu DB đang trống vì chưa qua phiên live, BỎ QUA bước này và ghi rõ lý do trong báo cáo — không phải lỗi của task):

```bash
python -m trading.backtest --strategy sma_cross --symbols VCB --from 2026-01-01 --to 2026-07-19 --tf 15m
```

Ghi lại output. Chạy lại lần 2 với cùng tham số, xác nhận output giống hệt (deterministic).

- [ ] **Step 6: `pytest -m "not integration" -v`** → toàn bộ suite pass (không phá vỡ Task 1-9 sub-project 1). **DỪNG — báo cáo planner** kèm toàn bộ output test + (nếu chạy được) output CLI thật.

---

## Self-review (đã chạy)

- **Spec coverage:** §4 (Strategy, RiskManager, PaperBroker, Backtest, Resampler — Alerter và Engine để sub-project 3/4), §5.1 khớp lệnh (giá mở bar kế tiếp, phí 0.15%, thuế bán 0.1%, slippage bps — Task 1), §5.3 backtest CLI (chữ ký lệnh gần đúng ví dụ spec, Task 6), §8 testing (unit: gom tick→bar đã ở sub-project 1; resampler Task 3; PaperBroker Task 1; RiskManager Task 2; SMA cross Task 4 — đều có; integration: backtest deterministic Task 5+6).
- **Placeholder scan:** không còn "TBD"/placeholder — mọi code block là implementation đầy đủ, kể cả CLI.
- **Type consistency:** `Signal`/`Context`/`Strategy` (Task 1) dùng xuyên suốt Task 2-6 không đổi tên; `PaperBroker` vừa là `Broker` vừa là `Context` (duck-typed qua `position_qty`) — dùng nhất quán khi `run_backtest` gọi `strategy.on_bar(bar, broker)`; `RiskManager.approve` signature cố định từ Task 2, gọi giống hệt ở Task 5.
- **Ghi chú riêng:** `orders`/`positions`/`pnl_daily` (schema phác thảo ở spec gốc §6) **KHÔNG** tạo trong plan này — backtest chạy hoàn toàn in-memory qua `PaperBroker`, không cần bền vững qua restart. Các bảng đó thuộc sub-project 3 (Live engine), nơi Engine cần giữ state qua restart giữa phiên — quyết định này giữ sub-project 2 gọn, đúng nguyên tắc "mỗi sub-project một chu trình riêng".
