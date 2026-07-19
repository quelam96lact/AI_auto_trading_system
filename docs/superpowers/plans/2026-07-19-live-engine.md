# Live Engine + Paper Trading (Sub-project 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Service `engine` subscribe bar từ NATS JetStream (durable consumer), chạy `Strategy` → `RiskManager` → `PaperBroker` (đã có từ sub-project 2), **bền vững vị thế/tiền mặt qua restart** bằng cách persist vào TimescaleDB, heartbeat định kỳ.

**Bối cảnh:** Sub-project 3 trong roadmap `docs/superpowers/specs/2026-07-18-autotrading-system-design.md` §9. **Không bắt buộc phải chờ phiên giao dịch thật** — Task 1-4 kiểm chứng đầy đủ bằng Docker (NATS + Postgres) và bar giả lập publish qua `BarPublisher` (đã có, sub-project 1 Task 5); không cần dữ liệu SSI thật. Kiểm chứng "một phiên live đầy đủ" theo đúng nghĩa đen của spec gốc sẽ là một plan bổ sung riêng sau (giống mô hình `2026-07-19-live-session-verification.md` của sub-project 1) — xem `Ghi chú riêng` cuối file.

**Architecture:** `PaperBroker`/`RiskManager`/`Strategy` tái sử dụng nguyên vẹn từ sub-project 2 (không sửa hành vi, chỉ thêm 1 classmethod phục hồi state). Engine đọc bar qua durable JetStream consumer (`durable="engine"`, subject `bars.>`) — nếu engine chết giữa phiên, JetStream giữ vị trí đọc, khởi động lại nhận đúng phần bar đã lỡ, không cần logic vá gap riêng. State (cash, realized PnL, vị thế) ghi TimescaleDB sau **mỗi lần khớp lệnh** — khởi động lại đọc state này để dựng lại `PaperBroker` đúng như trước khi chết, thay vì bắt đầu lại từ vốn ban đầu.

**Tech Stack:** Python ≥3.11, `nats-py` (JetStream durable consumer — API xác minh lại ở Task 4, xem lý do trong Global Constraints), `psycopg`, `pytest`, `pytest-asyncio`.

## Global Constraints

- **Không commit/push:** agent thực thi KHÔNG chạy `git commit`/`git push`. Cuối mỗi task: dừng, báo cáo kết quả + bằng chứng test. Claude (planner) chạy `gitnexus_detect_changes`, audit, và commit.
- **GitNexus:** Task 1 và Task 2 SỬA file đã tồn tại (`trading/storage/db.py`, `trading/storage/schema.sql`, `trading/paper_broker.py` — tất cả từ sub-project 1/2, đã có test pass). Trước khi sửa, chạy `gitnexus_impact({target: "Storage", direction: "upstream"})` và `gitnexus_impact({target: "PaperBroker", direction: "upstream"})`, báo risk level. Cả hai task chỉ **thêm** method mới (không đổi chữ ký/hành vi method cũ) nên risk phải LOW — nếu impact báo khác, DỪNG và báo planner trước khi sửa.
- **Phạm vi phẫu thuật:** mỗi task chỉ tạo/sửa đúng file liệt kê trong `**Files**`. Không đụng `trading/collector/*`, `trading/bus/*`, `trading/backtest.py`, `trading/strategies/*` (đã xong, thuộc sub-project 1/2).
- **Timezone:** mọi `datetime` tz-aware `Asia/Ho_Chi_Minh` (`from trading.calendar_vn import TZ`).
- **Test:** unit test thuần chạy `pytest -m "not integration"`; test cần Docker (Postgres + NATS) đánh dấu `@pytest.mark.integration`.
- **KHÔNG ĐOÁN API nats-py JetStream:** Task 4 dùng durable consumer + ack — trước khi viết code, đọc source `nats-py` đã cài để xác nhận đúng tham số `subscribe()`/`ConsumerConfig`/tên exception timeout/cách `delete_consumer` (nếu cần cho test). Nếu khác với khung code trong plan này, SỬA lại cho khớp thực tế, ghi rõ trong báo cáo — không giữ nguyên code đoán.
- **Quyết định phạm vi đã chốt (không tự ý đổi):**
  - Vốn paper, chiến lược, risk limits: **dùng đúng hằng số đã chốt ở sub-project 2** (`CAPITAL = 100_000_000.0`, `SmaCrossStrategy()` mặc định MA10/20 bar 15m, `RiskManager(capital=100_000_000)` mặc định 5 vị thế / 20% vốn mỗi lệnh BUY / 3% lỗ ngày). Không thêm field mới vào `config/config.yaml`/`trading/config.py`.
  - Engine subscribe `"bars.>"`, durable name **`"engine"`** (đơn), trên stream `cfg.nats_stream` — không tạo nhiều consumer theo symbol.
  - **Không persist halt-state của `RiskManager` qua restart** — đây là giới hạn đã biết, chấp nhận cho bản MVP: nếu engine crash đúng lúc vừa halt vì chạm lỗ tối đa/ngày, khởi động lại trong cùng ngày sẽ KHÔNG nhớ halt (rủi ro thấp — trường hợp hiếm, không mở rộng phạm vi task để xử lý).
  - Bảng `orders` dùng cột `(id, ts, symbol, side, qty, price, fee, pnl, mode)` — khác phác thảo §6 spec gốc (`status` thay bằng `fee`/`pnl` vì `PaperBroker` luôn khớp lệnh ngay lập tức, không có trạng thái "pending"; spec gốc đã ghi rõ "chi tiết cột chốt ở bước implementation plan" nên đây là quyết định hợp lệ của plan này).

---

### Task 1: Schema + Storage — orders/positions/engine_state/pnl_daily

**Files:**
- Modify: `trading/storage/schema.sql` (chỉ THÊM bảng mới vào cuối file, không đổi bảng cũ)
- Modify: `trading/storage/db.py` (chỉ THÊM import + method mới vào cuối class `Storage`, không đổi method cũ)
- Create: `tests/test_storage_engine.py`

**Interfaces:**
- Consumes: `Fill`, `Position` (`trading/broker.py`, sub-project 2), `Storage` (đã có, sub-project 1)
- Produces (method mới trên `Storage`, không đổi API cũ):
  - `upsert_position(pos: Position) -> None`
  - `read_positions() -> dict[str, Position]` — chỉ trả vị thế `qty > 0`
  - `write_engine_state(cash: float, realized_pnl: float) -> None`
  - `read_engine_state() -> tuple[float, float] | None` — `None` nếu engine chưa từng chạy
  - `write_order(fill: Fill, mode: str = "paper") -> None`
  - `update_pnl_daily(day: date, realized_delta: float, fee_delta: float, unrealized: float) -> None` — `realized`/`fees` CỘNG DỒN theo ngày; `unrealized` GHI ĐÈ bằng giá trị mới nhất (snapshot).

- [ ] **Step 1: Viết test fail** — `tests/test_storage_engine.py`:

```python
import os
from datetime import date, datetime

import pytest

from trading.broker import Fill, Position
from trading.calendar_vn import TZ
from trading.storage.db import Storage

DSN = os.environ.get("DB_DSN", "postgresql://trading:trading@localhost:5432/trading")
pytestmark = pytest.mark.integration


@pytest.fixture
def storage():
    s = Storage(DSN)
    s.init_schema()
    with s.conn() as c:
        c.execute("DELETE FROM positions WHERE symbol = 'TEST'")
        c.execute("DELETE FROM orders WHERE symbol = 'TEST'")
        c.execute("DELETE FROM pnl_daily WHERE date = '2026-07-15'")
        c.execute("DELETE FROM engine_state WHERE id = 1")
    return s


def test_position_upsert_and_read(storage):
    storage.upsert_position(Position("TEST", 100, 10.5))
    assert storage.read_positions()["TEST"].qty == 100
    storage.upsert_position(Position("TEST", 200, 11.0))
    assert storage.read_positions()["TEST"].avg_price == 11.0


def test_zero_qty_position_excluded_from_read(storage):
    storage.upsert_position(Position("TEST", 0, 0.0))
    assert "TEST" not in storage.read_positions()


def test_engine_state_roundtrip(storage):
    assert storage.read_engine_state() is None
    storage.write_engine_state(cash=99_000_000, realized_pnl=500_000)
    assert storage.read_engine_state() == (99_000_000, 500_000)


def test_write_order_and_pnl_daily(storage):
    fill = Fill("TEST", "SELL", 100, 11.0, 165.0, datetime(2026, 7, 15, 9, 5, tzinfo=TZ), pnl=45.0)
    storage.write_order(fill)
    storage.update_pnl_daily(date(2026, 7, 15), realized_delta=fill.pnl, fee_delta=fill.fee, unrealized=0.0)
    storage.update_pnl_daily(date(2026, 7, 15), realized_delta=0.0, fee_delta=0.0, unrealized=200.0)
    with storage.conn() as c:
        row = c.execute(
            "SELECT realized, unrealized, fees FROM pnl_daily WHERE date = %s", (date(2026, 7, 15),)
        ).fetchone()
    assert row == (45.0, 200.0, 165.0)
```

- [ ] **Step 2: `pytest tests/test_storage_engine.py -v`** → FAIL (bảng/method chưa tồn tại).

- [ ] **Step 3: Thêm vào cuối `trading/storage/schema.sql`**

```sql

CREATE TABLE IF NOT EXISTS orders (
  id bigserial PRIMARY KEY,
  ts timestamptz NOT NULL,
  symbol text NOT NULL,
  side text NOT NULL,
  qty integer NOT NULL,
  price double precision NOT NULL,
  fee double precision NOT NULL,
  pnl double precision,
  mode text NOT NULL DEFAULT 'paper'
);

CREATE TABLE IF NOT EXISTS positions (
  symbol text PRIMARY KEY,
  qty integer NOT NULL,
  avg_price double precision NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS engine_state (
  id integer PRIMARY KEY DEFAULT 1,
  cash double precision NOT NULL,
  realized_pnl double precision NOT NULL,
  updated_at timestamptz NOT NULL,
  CHECK (id = 1)
);

CREATE TABLE IF NOT EXISTS pnl_daily (
  date date PRIMARY KEY,
  realized double precision NOT NULL DEFAULT 0,
  unrealized double precision NOT NULL DEFAULT 0,
  fees double precision NOT NULL DEFAULT 0
);
```

- [ ] **Step 4: Sửa dòng import đầu `trading/storage/db.py`** — đổi dòng `from datetime import datetime` thành:

```python
from datetime import date, datetime
```

Thêm import mới ngay dưới `from trading.models import Bar, IndexValue`:

```python
from trading.broker import Fill, Position
```

- [ ] **Step 5: Thêm method vào cuối class `Storage`** (giữ nguyên thụt lề trong class, nối tiếp method `beat` đã có):

```python
    def upsert_position(self, pos: Position) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO positions (symbol, qty, avg_price, updated_at) VALUES (%s, %s, %s, now()) "
                "ON CONFLICT (symbol) DO UPDATE SET qty = EXCLUDED.qty, avg_price = EXCLUDED.avg_price, "
                "updated_at = now()",
                (pos.symbol, pos.qty, pos.avg_price),
            )

    def read_positions(self) -> dict[str, Position]:
        with self.conn() as c:
            rows = c.execute("SELECT symbol, qty, avg_price FROM positions WHERE qty > 0").fetchall()
        return {r[0]: Position(r[0], r[1], r[2]) for r in rows}

    def write_engine_state(self, cash: float, realized_pnl: float) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO engine_state (id, cash, realized_pnl, updated_at) VALUES (1, %s, %s, now()) "
                "ON CONFLICT (id) DO UPDATE SET cash = EXCLUDED.cash, "
                "realized_pnl = EXCLUDED.realized_pnl, updated_at = now()",
                (cash, realized_pnl),
            )

    def read_engine_state(self) -> tuple[float, float] | None:
        with self.conn() as c:
            row = c.execute("SELECT cash, realized_pnl FROM engine_state WHERE id = 1").fetchone()
        return (row[0], row[1]) if row else None

    def write_order(self, fill: Fill, mode: str = "paper") -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO orders (ts, symbol, side, qty, price, fee, pnl, mode) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (fill.ts, fill.symbol, fill.side, fill.qty, fill.price, fill.fee, fill.pnl, mode),
            )

    def update_pnl_daily(self, day: date, realized_delta: float, fee_delta: float, unrealized: float) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO pnl_daily (date, realized, unrealized, fees) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (date) DO UPDATE SET "
                "realized = pnl_daily.realized + EXCLUDED.realized, "
                "fees = pnl_daily.fees + EXCLUDED.fees, "
                "unrealized = EXCLUDED.unrealized",
                (day, realized_delta, unrealized, fee_delta),
            )
```

- [ ] **Step 6: `pytest tests/test_storage_engine.py -v`** (Docker Postgres đang chạy) → PASS. Chạy thêm `pytest -m "not integration" -v` để chắc chắn không phá vỡ test cũ (không có test nào ở nhóm này chạm `db.py` không-integration, nhưng vẫn kiểm để an toàn). **DỪNG — báo cáo planner** kèm output `gitnexus_impact` cho `Storage`.

---

### Task 2: PaperBroker.restore — phục hồi state sau restart

**Files:**
- Modify: `trading/paper_broker.py` (chỉ THÊM classmethod, không đổi `__init__`/method cũ)
- Modify: `tests/test_paper_broker.py` (chỉ THÊM test mới vào cuối file)

**Interfaces:**
- Consumes: `Position` (`trading/broker.py`)
- Produces: `PaperBroker.restore(capital: float, cash: float, realized_pnl: float, positions: dict[str, Position], **kwargs) -> PaperBroker` — classmethod, `**kwargs` chuyển tiếp `fee_rate`/`sell_tax_rate`/`slippage_bps` như `__init__` nếu cần ghi đè.

- [ ] **Step 1: Viết test fail** — thêm vào cuối `tests/test_paper_broker.py` (thêm `from trading.broker import Fill, Position` đã có sẵn ở đầu file từ Task 1 sub-project 2 — kiểm tra trước khi thêm trùng import):

```python
def test_restore_resumes_cash_positions_and_realized_pnl():
    positions = {"VCB": Position("VCB", 100, 10.0)}
    b = PaperBroker.restore(capital=100_000_000, cash=95_000_000, realized_pnl=200_000, positions=positions)
    assert b.cash == 95_000_000
    assert b.realized_pnl == 200_000
    assert b.position_qty("VCB") == 100
    assert b.capital == 100_000_000
```

(`Position` chưa được import trong `tests/test_paper_broker.py` ở sub-project 2 — thêm `Position` vào dòng `from trading.broker import Fill` đã tồn tại nếu có, hoặc thêm dòng import mới nếu chưa.)

- [ ] **Step 2: `pytest tests/test_paper_broker.py -v`** → FAIL (`restore` chưa tồn tại).

- [ ] **Step 3: Thêm classmethod vào cuối class `PaperBroker`** (sau method `unrealized_pnl`):

```python
    @classmethod
    def restore(cls, capital: float, cash: float, realized_pnl: float,
                positions: dict[str, Position], **kwargs) -> "PaperBroker":
        broker = cls(capital, **kwargs)
        broker.cash = cash
        broker.realized_pnl = realized_pnl
        broker.positions = positions
        return broker
```

- [ ] **Step 4: `pytest tests/test_paper_broker.py -v`** → PASS. **DỪNG — báo cáo planner** kèm output `gitnexus_impact` cho `PaperBroker`.

---

### Task 3: Engine core logic (thuần, không NATS/DB)

**Files:**
- Create: `trading/engine/__init__.py`, `trading/engine/logic.py`, `tests/test_engine_logic.py`

**Interfaces:**
- Consumes: `Bar`, `Fill`, `PaperBroker`, `RiskManager`, `Strategy` (sub-project 1/2)
- Produces:
  - `bar_from_payload(data: dict) -> Bar` — parse payload JSON đã `json.loads` từ `BarPublisher` (sub-project 1 Task 5: `{"symbol","ts","open","high","low","close","volume","source"}`, `ts` ISO-8601).
  - `process_bar(bar: Bar, broker: PaperBroker, strategy: Strategy, risk: RiskManager, marks: dict[str, float]) -> list[Fill]` — khớp lệnh chờ của bar này, cập nhật `marks`, hỏi chiến lược, xin duyệt risk, đặt lệnh mới nếu được duyệt (KHÔNG persist DB — đó là việc của Task 4). Đây là hàm mà `trading/engine/main.py` (Task 4) gọi cho mỗi bar nhận từ NATS.

- [ ] **Step 1: Viết test fail** — `tests/test_engine_logic.py`:

```python
from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.engine.logic import bar_from_payload, process_bar
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.strategies.sma_cross import SmaCrossStrategy


def bar_at(i, close, sym="VCB"):
    return Bar(sym, datetime(2026, 7, 15, 9, 0, tzinfo=TZ) + timedelta(minutes=15 * i),
               close, close, close, close, 100)


def test_process_bar_submits_and_next_bar_fills():
    broker = PaperBroker(capital=100_000_000)
    strategy = SmaCrossStrategy(fast=2, slow=4, qty=100)
    risk = RiskManager(capital=100_000_000)
    marks: dict[str, float] = {}

    prices = [10, 10, 10, 10, 20, 20]
    all_fills = []
    for i, p in enumerate(prices):
        all_fills.extend(process_bar(bar_at(i, p), broker, strategy, risk, marks))

    assert any(f.side == "BUY" for f in all_fills)


def test_bar_from_payload_roundtrip():
    payload = {
        "symbol": "VCB", "ts": "2026-07-15T09:00:00+07:00",
        "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5, "volume": 1000, "source": "ssi",
    }
    bar = bar_from_payload(payload)
    assert bar.symbol == "VCB" and bar.close == 10.5 and bar.ts.tzinfo is not None
```

- [ ] **Step 2: `pytest tests/test_engine_logic.py -v`** → FAIL (module chưa tồn tại).

- [ ] **Step 3: Implement `trading/engine/__init__.py`** (rỗng) và `trading/engine/logic.py`:

```python
from datetime import datetime

from trading.broker import Fill
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.strategy import Strategy


def process_bar(bar: Bar, broker: PaperBroker, strategy: Strategy, risk: RiskManager,
                 marks: dict[str, float]) -> list[Fill]:
    fills = broker.on_bar(bar)
    marks[bar.symbol] = bar.close

    signal = strategy.on_bar(bar, broker)
    if signal is not None:
        daily_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)
        if risk.approve(signal, bar.close, broker.positions, daily_pnl, bar.ts.date()):
            broker.submit(signal)

    return fills


def bar_from_payload(data: dict) -> Bar:
    return Bar(
        symbol=data["symbol"],
        ts=datetime.fromisoformat(data["ts"]).astimezone(TZ),
        open=data["open"], high=data["high"], low=data["low"], close=data["close"],
        volume=data["volume"], source=data.get("source", "ssi"),
    )
```

- [ ] **Step 4: `pytest tests/test_engine_logic.py -v`** → PASS. **DỪNG — báo cáo planner.**

---

### Task 4: Engine main (NATS wiring + persist) + Docker

**Điều kiện:** Docker (`postgres`, `nats`) đang chạy. Không cần phiên giao dịch — test dùng `BarPublisher` publish bar giả lập.

**Files:**
- Create: `trading/engine/main.py`, `tests/test_engine_main.py`
- Modify: `docker-compose.yml` (chỉ THÊM service `engine`, không đổi service khác — file này có thể đã có service `collector` từ sub-project 1 Task 10 đang chờ commit; KHÔNG động vào block đó, chỉ thêm block `engine` mới)

**Interfaces:**
- Consumes: `Storage` (Task 1), `PaperBroker.restore` (Task 2), `process_bar`/`bar_from_payload` (Task 3), `BarPublisher` (sub-project 1, chỉ dùng trong test để giả lập nguồn bar)
- Produces: `async def run(cfg: Config, max_messages: int | None = None) -> None` — vòng lặp chính; `max_messages=None` chạy vô hạn (dùng cho `main()`), số nguyên dùng cho test (dừng sau khi xử lý đúng số message đó — cho phép test "restart" bằng cách gọi `run()` lần hai). `def main() -> None` — CLI `python -m trading.engine.main --config config/config.yaml`.

- [ ] **Step 1: Xác minh API nats-py JetStream durable consumer TRƯỚC khi viết code** — chạy `python -c "import nats; print(nats.__file__)"`, đọc source `nats/js/client.py` (hàm `subscribe`), `nats/js/api.py` (`ConsumerConfig`, `DeliverPolicy`), và cách bắt lỗi hết-timeout khi gọi `next_msg` (tên exception, ví dụ `nats.errors.TimeoutError` — xác minh đúng tên). Nếu khung code ở Step 3 dưới đây dùng sai tham số/tên, SỬA lại cho khớp thực tế — ghi 2-3 dòng xác nhận vào báo cáo cuối task (không cần file findings riêng, đây không phải khám phá API bên ngoài như SSI).

- [ ] **Step 2: Viết integration test fail** — `tests/test_engine_main.py`:

```python
import logging
import os
from datetime import datetime, timedelta

import pytest

from trading.bus.publisher import BarPublisher
from trading.calendar_vn import TZ
from trading.config import Config
from trading.engine.main import run
from trading.models import Bar
from trading.storage.db import Storage

DSN = os.environ.get("DB_DSN", "postgresql://trading:trading@localhost:5432/trading")
pytestmark = pytest.mark.integration


def make_cfg() -> Config:
    return Config(
        symbols=["ENGT"], indices=[], bar_interval_minutes=15, holidays=set(),
        db_dsn=DSN, nats_url="nats://localhost:4222", nats_stream="BARS",
        watchdog_stale_seconds=180, watchdog_max_failures=3,
        ssi_consumer_id="x", ssi_consumer_secret="y",
    )


@pytest.fixture
def storage():
    s = Storage(DSN)
    s.init_schema()
    with s.conn() as c:
        c.execute("DELETE FROM positions WHERE symbol = 'ENGT'")
        c.execute("DELETE FROM orders WHERE symbol = 'ENGT'")
        c.execute("DELETE FROM engine_state WHERE id = 1")
    return s


def make_bars(prices, sym="ENGT"):
    start = datetime(2026, 7, 15, 9, 0, tzinfo=TZ)
    return [Bar(sym, start + timedelta(minutes=15 * i), p, p, p, p, 1000) for i, p in enumerate(prices)]


async def _publish(cfg, bars):
    pub = BarPublisher(cfg.nats_url, cfg.nats_stream)
    await pub.connect()
    for bar in bars:
        await pub.publish(bar)
    await pub.close()


async def test_engine_persists_fill_and_restores_state_on_next_run(storage, caplog):
    cfg = make_cfg()
    prices = [10] * 20 + [20] * 5  # đủ 20 bar cho slow MA=20 rồi tăng giá để kích BUY
    bars = make_bars(prices)
    await _publish(cfg, bars)

    await run(cfg, max_messages=len(bars))

    positions = storage.read_positions()
    assert positions["ENGT"].qty == 100
    state = storage.read_engine_state()
    assert state is not None and state[0] < 100_000_000  # cash giảm vì đã mua

    with storage.conn() as c:
        n_orders = c.execute("SELECT count(*) FROM orders WHERE symbol = 'ENGT'").fetchone()[0]
    assert n_orders == 1

    # Mô phỏng restart: gọi run() một lần NỮA (tạo PaperBroker mới trong nội bộ run())
    # rồi publish 1 bar để dòng lệnh xử lý — nếu restore đúng, log phải báo "engine restored state"
    # và vị thế không đổi.
    await _publish(cfg, make_bars([20], sym="ENGT"))
    with caplog.at_level(logging.INFO):
        await run(cfg, max_messages=1)
    assert any("engine restored state" in r.message for r in caplog.records)
    assert storage.read_positions()["ENGT"].qty == 100
```

- [ ] **Step 3: `pytest tests/test_engine_main.py -v`** → FAIL (module chưa tồn tại).

- [ ] **Step 4: Implement `trading/engine/main.py`** — khung dưới đây; SỬA lại phần JetStream (`ConsumerConfig`, tên exception timeout) nếu Step 1 phát hiện khác:

```python
import argparse
import asyncio
import json
import logging

import nats
from nats.js.api import ConsumerConfig, DeliverPolicy

from trading.alerts import alert
from trading.calendar_vn import TZ
from trading.config import Config, load_config
from trading.engine.logic import bar_from_payload, process_bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.strategies.sma_cross import SmaCrossStrategy

CAPITAL = 100_000_000.0


async def run(cfg: Config, max_messages: int | None = None) -> None:
    storage = Storage(cfg.db_dsn)
    storage.init_schema()

    state = storage.read_engine_state()
    positions = storage.read_positions()
    if state is None:
        broker = PaperBroker(CAPITAL)
        alert("INFO", "engine starting fresh", capital=CAPITAL)
    else:
        cash, realized_pnl = state
        broker = PaperBroker.restore(CAPITAL, cash, realized_pnl, positions)
        alert("INFO", "engine restored state", cash=cash, realized_pnl=realized_pnl,
              positions={s: p.qty for s, p in positions.items()})

    strategy = SmaCrossStrategy()
    risk = RiskManager(capital=CAPITAL)
    marks: dict[str, float] = {}

    nc = await nats.connect(cfg.nats_url)
    js = nc.jetstream()
    sub = await js.subscribe("bars.>", durable="engine", stream=cfg.nats_stream,
                              config=ConsumerConfig(deliver_policy=DeliverPolicy.ALL))

    def persist_fills(fills) -> None:
        for fill in fills:
            storage.upsert_position(broker.positions[fill.symbol])
            storage.write_engine_state(broker.cash, broker.realized_pnl)
            storage.write_order(fill)
            storage.update_pnl_daily(fill.ts.astimezone(TZ).date(), fill.pnl or 0.0, fill.fee,
                                      broker.unrealized_pnl(marks))
            alert("INFO", "order filled", symbol=fill.symbol, side=fill.side, qty=fill.qty,
                  price=fill.price, pnl=fill.pnl)

    processed = 0
    try:
        while max_messages is None or processed < max_messages:
            try:
                msg = await sub.next_msg(timeout=60)
            except nats.errors.TimeoutError:
                storage.beat("engine")
                continue
            bar = bar_from_payload(json.loads(msg.data))
            fills = process_bar(bar, broker, strategy, risk, marks)
            persist_fills(fills)
            await msg.ack()
            storage.beat("engine")
            processed += 1
    finally:
        await nc.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run(load_config(args.config)))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: `pytest tests/test_engine_main.py -v`** — nếu test flaky do durable consumer `"engine"` còn giữ vị trí đọc từ lần chạy test trước (durable consumer là CHỦ Ý — không phải bug, nhưng gây nhiễu giữa các lần chạy test khác nhau): thêm fixture xóa consumer trước mỗi test, xác minh đúng tên hàm xóa consumer từ source đọc ở Step 1 trước khi dùng:

```python
@pytest.fixture(autouse=True)
async def reset_durable_consumer():
    nc = await nats.connect("nats://localhost:4222")
    js = nc.jetstream()
    try:
        await js.delete_consumer("BARS", "engine")
    except Exception:
        pass
    await nc.close()
```

(Thêm `import nats` vào đầu `tests/test_engine_main.py` nếu dùng fixture này.) Chạy lại `pytest tests/test_engine_main.py -v` → PASS.

- [ ] **Step 6: Thêm service `engine` vào `docker-compose.yml`** — CHỈ thêm block dưới đây, không sửa gì khác trong file (kể cả nếu đã có block `collector` từ trước):

```yaml
  engine:
    build: .
    command: python -m trading.engine.main --config config/config.yaml
    environment:
      DB_DSN: postgresql://trading:trading@postgres:5432/trading
    depends_on:
      postgres: {condition: service_healthy}
      nats: {condition: service_started}
    restart: unless-stopped
```

(Dùng chung `Dockerfile` đã có từ sub-project 1 Task 10 — nếu file đó chưa tồn tại trong working tree khi làm task này, báo cáo lại cho planner, không tự tạo Dockerfile mới.)

- [ ] **Step 7: `pytest -m "not integration" -v`** → toàn bộ suite pass (không phá vỡ sub-project 1/2). **DỪNG — báo cáo planner** kèm: xác nhận API nats-py ở Step 1, output test, output `gitnexus_detect_changes`.

---

## Self-review (đã chạy)

- **Spec coverage:** §4 Engine (subscribe NATS JetStream durable consumer, strategy→RiskManager→PaperBroker, ghi state DB, heartbeat — Task 4), §6 schema `orders`/`positions`/`pnl_daily` (Task 1 — cột đã điều chỉnh, ghi rõ lý do ở Global Constraints), §7.3 "Engine restart giữa phiên: JetStream durable consumer phát lại bar lỡ; vị thế đọc lại từ DB — không mất state" (Task 2 restore + Task 4 durable consumer, kiểm chứng bằng test restart trong Task 4 Step 2). §9.3 tiêu chí "kill engine giữa phiên → tự phục hồi không mất vị thế" được kiểm chứng bằng Docker/BarPublisher (không cần phiên thật); tiêu chí "một phiên live đầy đủ có lệnh paper" cần dữ liệu SSI thật — để plan bổ sung riêng (xem Ghi chú riêng).
- **Placeholder scan:** không còn "TBD" — Task 4 Step 1 (xác minh nats-py) là bước KHÁM PHÁ có chủ đích (giống Task 6 sub-project 1 cho SSI SDK), không phải placeholder; code khung Step 4 đầy đủ, chỉ yêu cầu sửa nếu API thực tế khác.
- **Type consistency:** `Storage` method mới (Task 1) dùng đúng tên/kiểu ở Task 4 (`upsert_position`, `read_positions`, `write_engine_state`, `read_engine_state`, `write_order`, `update_pnl_daily`); `PaperBroker.restore` (Task 2) signature khớp cách gọi ở Task 4; `process_bar`/`bar_from_payload` (Task 3) dùng nguyên trong Task 4, không đổi tên.
- **Ghi chú riêng:** kiểm chứng "một phiên live đầy đủ" (tiêu chí chính thức §9.3) — kill engine thật giữa phiên SSI thật, xác nhận PnL/vị thế đúng — sẽ là một plan `live-session` bổ sung viết SAU khi: (a) plan này (Task 1-4) đã chạy xong và commit, VÀ (b) `docs/superpowers/plans/2026-07-19-live-session-verification.md` (sub-project 1) đã hoàn thành (engine cần collector đang publish bar thật). Không viết plan đó bây giờ vì phụ thuộc trạng thái chưa xảy ra.
