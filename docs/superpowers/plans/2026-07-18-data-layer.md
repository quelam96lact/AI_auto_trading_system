# Lớp dữ liệu (Sub-project 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collector thu tick SSI FastConnect (kênh B + MI) → bar 5m → ghi TimescaleDB + publish NATS JetStream, kèm backfill REST, watchdog, và job vá gap cuối ngày.

**Architecture:** Service Python duy nhất (`collector`) chạy asyncio; SDK `ssi-fc-data` chạy thread riêng đẩy raw message vào `queue.Queue`; main loop parse → aggregate → ghi DB (nguồn sự thật) → publish NATS. Backfill REST chạy lúc khởi động và cuối ngày. Spec gốc: `docs/superpowers/specs/2026-07-18-autotrading-system-design.md`.

**Tech Stack:** Python ≥3.11, `ssi-fc-data`, `nats-py`, `psycopg[binary]` (v3), `PyYAML`, `pytest`, TimescaleDB (Docker), NATS 2.x JetStream (Docker).

## Global Constraints

- **Không commit/push:** agent thực thi KHÔNG chạy `git commit`/`git push`. Cuối mỗi task: dừng, báo cáo kết quả + bằng chứng test. Claude (planner) chạy `gitnexus_detect_changes`, audit, và commit.
- **GitNexus:** trước khi SỬA một hàm/class đã tồn tại từ task trước, chạy `gitnexus_impact({target, direction: "upstream"})`; nếu index báo stale thì bỏ qua bước này và ghi chú lại (repo đang là dự án mới, index thưa).
- **Phạm vi phẫu thuật:** mỗi task chỉ tạo/sửa đúng các file liệt kê trong `**Files**`. Phát hiện vấn đề ngoài phạm vi → báo cáo, không tự sửa.
- **Timezone:** mọi `datetime` là tz-aware `Asia/Ho_Chi_Minh` (`zoneinfo`). Serialize ISO-8601 có offset `+07:00`.
- **Secrets:** `SSI_CONSUMER_ID`, `SSI_CONSUMER_SECRET`, `DB_DSN` qua biến môi trường. KHÔNG hardcode, KHÔNG commit file `.env` (thêm vào `.gitignore` ở Task 1).
- **NATS:** stream `BARS`, subject `bars.ssi.{symbol}`. **DB:** bảng `bars` chỉ chứa bar 5m; daily nằm ở `bars_daily`.
- **Test:** unit test thuần chạy bằng `pytest -m "not integration"`; test cần Docker (Postgres/NATS) đánh dấu `@pytest.mark.integration`.
- Phiên giao dịch VN: 09:00–11:30 và 13:00–14:45 (bao gồm ATC 14:45), nghỉ T7/CN + lịch nghỉ lễ trong config.

---

### Task 1: Skeleton dự án + config loader

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `config/config.yaml`, `trading/__init__.py`, `trading/config.py`, `tests/__init__.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `load_config(path: str) -> Config` — dataclass `Config` với các field: `symbols: list[str]`, `indices: list[str]`, `bar_interval_minutes: int`, `holidays: set[date]`, `db_dsn: str`, `nats_url: str`, `nats_stream: str`, `watchdog_stale_seconds: int`, `watchdog_max_failures: int`, `ssi_consumer_id: str`, `ssi_consumer_secret: str`. DSN/credentials đọc từ env, phần còn lại từ YAML.

- [ ] **Step 1: Tạo `pyproject.toml`, `.gitignore`**

```toml
[project]
name = "trading"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "ssi-fc-data",
    "nats-py>=2.6",
    "psycopg[binary]>=3.1",
    "PyYAML>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]

[tool.pytest.ini_options]
markers = ["integration: cần Docker Postgres/NATS đang chạy"]
asyncio_mode = "auto"

[tool.setuptools]
packages = { find = { include = ["trading*"] } }
```

`.gitignore`:

```
__pycache__/
*.egg-info/
.venv/
.env
.pytest_cache/
```

- [ ] **Step 2: Viết test fail cho config**

`tests/test_config.py`:

```python
from datetime import date
from trading.config import load_config

def test_load_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SSI_CONSUMER_ID", "id123")
    monkeypatch.setenv("SSI_CONSUMER_SECRET", "sec456")
    monkeypatch.setenv("DB_DSN", "postgresql://t:t@localhost:5432/trading")
    p = tmp_path / "c.yaml"
    p.write_text(
        "symbols: [VCB, HPG]\n"
        "indices: [VNINDEX]\n"
        "bar_interval_minutes: 5\n"
        "holidays: ['2026-09-02']\n"
        "nats: {url: 'nats://localhost:4222', stream: BARS}\n"
        "watchdog: {stale_seconds: 180, max_failures: 3}\n",
        encoding="utf-8",
    )
    cfg = load_config(str(p))
    assert cfg.symbols == ["VCB", "HPG"]
    assert cfg.holidays == {date(2026, 9, 2)}
    assert cfg.ssi_consumer_id == "id123"
    assert cfg.db_dsn.startswith("postgresql://")
    assert cfg.nats_stream == "BARS"
    assert cfg.watchdog_stale_seconds == 180
```

- [ ] **Step 3: Chạy test, xác nhận FAIL** — `pip install -e .[dev]` rồi `pytest tests/test_config.py -v` → FAIL (`ModuleNotFoundError` hoặc `ImportError`).

- [ ] **Step 4: Implement `trading/config.py`**

```python
import os
from dataclasses import dataclass
from datetime import date

import yaml


@dataclass(frozen=True)
class Config:
    symbols: list[str]
    indices: list[str]
    bar_interval_minutes: int
    holidays: set[date]
    db_dsn: str
    nats_url: str
    nats_stream: str
    watchdog_stale_seconds: int
    watchdog_max_failures: int
    ssi_consumer_id: str
    ssi_consumer_secret: str


def load_config(path: str) -> Config:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Config(
        symbols=list(raw["symbols"]),
        indices=list(raw.get("indices", [])),
        bar_interval_minutes=int(raw.get("bar_interval_minutes", 5)),
        holidays={date.fromisoformat(str(h)) for h in raw.get("holidays", [])},
        db_dsn=os.environ["DB_DSN"],
        nats_url=raw["nats"]["url"],
        nats_stream=raw["nats"]["stream"],
        watchdog_stale_seconds=int(raw["watchdog"]["stale_seconds"]),
        watchdog_max_failures=int(raw["watchdog"]["max_failures"]),
        ssi_consumer_id=os.environ["SSI_CONSUMER_ID"],
        ssi_consumer_secret=os.environ["SSI_CONSUMER_SECRET"],
    )
```

`config/config.yaml` (giá trị thật ban đầu):

```yaml
symbols: [VCB, HPG, TCB]
indices: [VNINDEX, VN30]
bar_interval_minutes: 5
holidays: ['2026-09-02']
nats: {url: 'nats://localhost:4222', stream: BARS}
watchdog: {stale_seconds: 180, max_failures: 3}
```

- [ ] **Step 5: Chạy `pytest tests/test_config.py -v`** → PASS. **DỪNG — báo cáo planner** (kèm output test).

---

### Task 2: Models + lịch giao dịch VN

**Files:**
- Create: `trading/models.py`, `trading/calendar_vn.py`, `tests/test_calendar.py`

**Interfaces:**
- Produces: `Tick(symbol, price, volume, ts)`, `Bar(symbol, ts, open, high, low, close, volume, source="ssi")`, `IndexValue(index_id, ts, value)` — dataclass frozen; `Bar.ts` là thời điểm MỞ bar. `TZ = ZoneInfo("Asia/Ho_Chi_Minh")`. `is_trading_time(ts, holidays) -> bool`, `session_end_after(ts) -> datetime | None` (thời điểm kết thúc phiên hiện tại/kế tiếp trong ngày, dùng để flush bar).

- [ ] **Step 1: Viết test fail** — `tests/test_calendar.py`:

```python
from datetime import date, datetime
from trading.calendar_vn import TZ, is_trading_time

def dt(h, m, day=15):  # 2026-07-15 là thứ Tư
    return datetime(2026, 7, day, h, m, tzinfo=TZ)

def test_in_morning_session():
    assert is_trading_time(dt(9, 0))
    assert is_trading_time(dt(11, 29))

def test_lunch_break_and_after_close():
    assert not is_trading_time(dt(12, 0))
    assert not is_trading_time(dt(14, 46))

def test_atc_inclusive():
    assert is_trading_time(dt(14, 45))

def test_weekend_and_holiday():
    assert not is_trading_time(dt(10, 0, day=18))  # thứ Bảy
    assert not is_trading_time(dt(10, 0), holidays={date(2026, 7, 15)})
```

- [ ] **Step 2: `pytest tests/test_calendar.py -v`** → FAIL (module chưa tồn tại).

- [ ] **Step 3: Implement**

`trading/models.py`:

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Tick:
    symbol: str
    price: float
    volume: int  # khối lượng khớp của riêng tick này
    ts: datetime


@dataclass(frozen=True)
class Bar:
    symbol: str
    ts: datetime  # thời điểm MỞ bar
    open: float
    high: float
    low: float
    close: float
    volume: int
    source: str = "ssi"


@dataclass(frozen=True)
class IndexValue:
    index_id: str
    ts: datetime
    value: float
```

`trading/calendar_vn.py`:

```python
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SESSIONS = [(time(9, 0), time(11, 30)), (time(13, 0), time(14, 45))]


def is_trading_time(ts: datetime, holidays: set[date] = frozenset()) -> bool:
    ts = ts.astimezone(TZ)
    if ts.weekday() >= 5 or ts.date() in holidays:
        return False
    t = ts.time()
    return any(start <= t <= end for start, end in SESSIONS)


def session_end_after(ts: datetime) -> datetime | None:
    """Thời điểm kết thúc của phiên chứa/ngay sau ts trong cùng ngày, None nếu hết phiên."""
    ts = ts.astimezone(TZ)
    for _, end in SESSIONS:
        end_dt = ts.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
        if ts <= end_dt:
            return end_dt
    return None
```

- [ ] **Step 4: `pytest tests/test_calendar.py -v`** → PASS. **DỪNG — báo cáo planner.**

---

### Task 3: BarAggregator (tick → bar 5m)

**Files:**
- Create: `trading/collector/__init__.py`, `trading/collector/aggregator.py`, `tests/test_aggregator.py`

**Interfaces:**
- Consumes: `Tick`, `Bar`, `is_trading_time` (Task 2)
- Produces: `BarAggregator(interval_min: int, holidays: set[date])` với `add_tick(t: Tick) -> list[Bar]` (trả các bar vừa đóng, thường rỗng) và `flush() -> list[Bar]` (đóng mọi bar đang mở — gọi cuối phiên/shutdown).

- [ ] **Step 1: Viết test fail** — `tests/test_aggregator.py`:

```python
from datetime import datetime
from trading.calendar_vn import TZ
from trading.collector.aggregator import BarAggregator
from trading.models import Tick

def tick(h, m, s, price, vol=100, sym="VCB"):
    return Tick(sym, price, vol, datetime(2026, 7, 15, h, m, s, tzinfo=TZ))

def test_aggregates_ohlcv_and_closes_on_boundary():
    agg = BarAggregator(5, set())
    assert agg.add_tick(tick(9, 0, 5, 100.0)) == []
    assert agg.add_tick(tick(9, 1, 0, 102.0)) == []
    assert agg.add_tick(tick(9, 4, 59, 99.0)) == []
    closed = agg.add_tick(tick(9, 5, 1, 101.0))  # sang bucket mới → đóng bar cũ
    assert len(closed) == 1
    b = closed[0]
    assert (b.open, b.high, b.low, b.close, b.volume) == (100.0, 102.0, 99.0, 99.0, 300)
    assert b.ts == datetime(2026, 7, 15, 9, 0, tzinfo=TZ)

def test_ignores_out_of_session_tick():
    agg = BarAggregator(5, set())
    assert agg.add_tick(tick(12, 30, 0, 100.0)) == []
    assert agg.flush() == []

def test_flush_closes_open_bars():
    agg = BarAggregator(5, set())
    agg.add_tick(tick(14, 44, 0, 50.0))
    bars = agg.flush()
    assert len(bars) == 1 and bars[0].close == 50.0
    assert agg.flush() == []  # flush lần 2 không nhân đôi

def test_symbols_are_independent():
    agg = BarAggregator(5, set())
    agg.add_tick(tick(9, 0, 0, 100.0, sym="VCB"))
    agg.add_tick(tick(9, 0, 0, 20.0, sym="HPG"))
    closed = agg.add_tick(tick(9, 5, 0, 101.0, sym="VCB"))
    assert [b.symbol for b in closed] == ["VCB"]  # HPG vẫn mở
```

- [ ] **Step 2: `pytest tests/test_aggregator.py -v`** → FAIL.

- [ ] **Step 3: Implement `trading/collector/aggregator.py`**

```python
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from trading.calendar_vn import is_trading_time
from trading.models import Bar, Tick


@dataclass
class _OpenBar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class BarAggregator:
    def __init__(self, interval_min: int, holidays: set[date]):
        self.interval = timedelta(minutes=interval_min)
        self.holidays = holidays
        self._open: dict[str, _OpenBar] = {}

    def _bucket(self, ts: datetime) -> datetime:
        minute = (ts.minute // (self.interval.seconds // 60)) * (self.interval.seconds // 60)
        return ts.replace(minute=minute, second=0, microsecond=0)

    def add_tick(self, t: Tick) -> list[Bar]:
        if not is_trading_time(t.ts, self.holidays):
            return []
        bucket = self._bucket(t.ts)
        closed: list[Bar] = []
        cur = self._open.get(t.symbol)
        if cur is not None and bucket > cur.ts:
            closed.append(self._freeze(t.symbol, cur))
            cur = None
        if cur is None:
            self._open[t.symbol] = _OpenBar(bucket, t.price, t.price, t.price, t.price, t.volume)
        else:
            cur.high = max(cur.high, t.price)
            cur.low = min(cur.low, t.price)
            cur.close = t.price
            cur.volume += t.volume
        return closed

    def flush(self) -> list[Bar]:
        bars = [self._freeze(sym, ob) for sym, ob in self._open.items()]
        self._open.clear()
        return bars

    @staticmethod
    def _freeze(symbol: str, ob: _OpenBar) -> Bar:
        return Bar(symbol, ob.ts, ob.open, ob.high, ob.low, ob.close, ob.volume)
```

- [ ] **Step 4: `pytest tests/test_aggregator.py -v`** → PASS. Chạy cả `pytest -m "not integration" -v` → tất cả PASS. **DỪNG — báo cáo planner.**

---

### Task 4: Docker infra + schema + Storage

**Files:**
- Create: `docker-compose.yml`, `trading/storage/__init__.py`, `trading/storage/schema.sql`, `trading/storage/db.py`, `tests/test_storage.py`

**Interfaces:**
- Consumes: `Bar`, `IndexValue` (Task 2)
- Produces: `Storage(dsn: str)` với: `init_schema()`, `write_bars(bars: list[Bar])` (upsert), `read_bars(symbol: str, start: datetime, end: datetime) -> list[Bar]` (end exclusive, sắp theo ts), `last_bar_ts(symbol: str) -> datetime | None`, `write_index_values(vals: list[IndexValue])`, `write_daily(rows: list[Bar])` (vào `bars_daily`), `beat(service: str)` (upsert heartbeat).

- [ ] **Step 1: `docker-compose.yml`** (mới chỉ chứa infra; service collector thêm ở Task 10):

```yaml
services:
  postgres:
    image: timescale/timescaledb:latest-pg16
    environment:
      POSTGRES_USER: trading
      POSTGRES_PASSWORD: trading
      POSTGRES_DB: trading
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U trading"]
      interval: 5s
      timeout: 3s
      retries: 10
    restart: unless-stopped
  nats:
    image: nats:2.10-alpine
    command: ["-js", "-sd", "/data"]
    ports: ["4222:4222"]
    volumes: [natsdata:/data]
    restart: unless-stopped
volumes:
  pgdata:
  natsdata:
```

Chạy `docker compose up -d postgres nats` và xác nhận cả hai healthy/running (`docker compose ps`).

- [ ] **Step 2: `trading/storage/schema.sql`**

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS bars (
  symbol text NOT NULL,
  ts timestamptz NOT NULL,
  open double precision NOT NULL,
  high double precision NOT NULL,
  low double precision NOT NULL,
  close double precision NOT NULL,
  volume bigint NOT NULL,
  source text NOT NULL DEFAULT 'ssi',
  PRIMARY KEY (symbol, ts)
);
SELECT create_hypertable('bars', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS bars_daily (
  symbol text NOT NULL,
  ts timestamptz NOT NULL,
  open double precision NOT NULL,
  high double precision NOT NULL,
  low double precision NOT NULL,
  close double precision NOT NULL,
  volume bigint NOT NULL,
  source text NOT NULL DEFAULT 'ssi',
  PRIMARY KEY (symbol, ts)
);

CREATE TABLE IF NOT EXISTS index_values (
  index_id text NOT NULL,
  ts timestamptz NOT NULL,
  value double precision NOT NULL,
  PRIMARY KEY (index_id, ts)
);
SELECT create_hypertable('index_values', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS heartbeat (
  service text PRIMARY KEY,
  last_seen timestamptz NOT NULL
);
```

- [ ] **Step 3: Viết integration test fail** — `tests/test_storage.py`:

```python
import os
from datetime import datetime, timedelta

import pytest

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.storage.db import Storage

DSN = os.environ.get("DB_DSN", "postgresql://trading:trading@localhost:5432/trading")
pytestmark = pytest.mark.integration


@pytest.fixture
def storage():
    s = Storage(DSN)
    s.init_schema()
    with s.conn() as c:
        c.execute("DELETE FROM bars WHERE symbol = 'TEST'")
    return s


def bar(minute, close=101.0):
    return Bar("TEST", datetime(2026, 7, 15, 9, minute, tzinfo=TZ), 100.0, 102.0, 99.0, close, 1000)


def test_write_read_roundtrip(storage):
    storage.write_bars([bar(0), bar(5)])
    got = storage.read_bars("TEST", bar(0).ts, bar(0).ts + timedelta(minutes=10))
    assert [b.ts.astimezone(TZ).minute for b in got] == [0, 5]
    assert got[0].close == 101.0


def test_upsert_idempotent(storage):
    storage.write_bars([bar(0)])
    storage.write_bars([bar(0, close=105.0)])  # ghi lại cùng khóa → update
    got = storage.read_bars("TEST", bar(0).ts, bar(0).ts + timedelta(minutes=5))
    assert len(got) == 1 and got[0].close == 105.0


def test_last_bar_ts(storage):
    assert storage.last_bar_ts("TEST") is None
    storage.write_bars([bar(0), bar(5)])
    assert storage.last_bar_ts("TEST") == bar(5).ts
```

- [ ] **Step 4: `pytest tests/test_storage.py -v`** → FAIL (`trading.storage.db` chưa tồn tại).

- [ ] **Step 5: Implement `trading/storage/db.py`**

```python
from contextlib import contextmanager
from datetime import datetime
from importlib.resources import files

import psycopg

from trading.models import Bar, IndexValue

_UPSERT_BAR = """
INSERT INTO {table} (symbol, ts, open, high, low, close, volume, source)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (symbol, ts) DO UPDATE SET
  open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
  close = EXCLUDED.close, volume = EXCLUDED.volume, source = EXCLUDED.source
"""


class Storage:
    def __init__(self, dsn: str):
        self.dsn = dsn

    @contextmanager
    def conn(self):
        with psycopg.connect(self.dsn) as c:
            yield c

    def init_schema(self) -> None:
        sql = files("trading.storage").joinpath("schema.sql").read_text(encoding="utf-8")
        with self.conn() as c:
            c.execute(sql)

    def _write(self, table: str, bars: list[Bar]) -> None:
        if not bars:
            return
        with self.conn() as c:
            c.cursor().executemany(
                _UPSERT_BAR.format(table=table),
                [(b.symbol, b.ts, b.open, b.high, b.low, b.close, b.volume, b.source) for b in bars],
            )

    def write_bars(self, bars: list[Bar]) -> None:
        self._write("bars", bars)

    def write_daily(self, bars: list[Bar]) -> None:
        self._write("bars_daily", bars)

    def read_bars(self, symbol: str, start: datetime, end: datetime) -> list[Bar]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol, ts, open, high, low, close, volume, source FROM bars "
                "WHERE symbol = %s AND ts >= %s AND ts < %s ORDER BY ts",
                (symbol, start, end),
            ).fetchall()
        return [Bar(*r) for r in rows]

    def last_bar_ts(self, symbol: str) -> datetime | None:
        with self.conn() as c:
            row = c.execute("SELECT max(ts) FROM bars WHERE symbol = %s", (symbol,)).fetchone()
        return row[0]

    def write_index_values(self, vals: list[IndexValue]) -> None:
        if not vals:
            return
        with self.conn() as c:
            c.cursor().executemany(
                "INSERT INTO index_values (index_id, ts, value) VALUES (%s, %s, %s) "
                "ON CONFLICT (index_id, ts) DO UPDATE SET value = EXCLUDED.value",
                [(v.index_id, v.ts, v.value) for v in vals],
            )

    def beat(self, service: str) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO heartbeat (service, last_seen) VALUES (%s, now()) "
                "ON CONFLICT (service) DO UPDATE SET last_seen = now()",
                (service,),
            )
```

Lưu ý: thêm `[tool.setuptools.package-data] "trading.storage" = ["*.sql"]` vào `pyproject.toml` để `schema.sql` đi kèm package (được phép sửa `pyproject.toml` trong task này cho mục đích đó).

- [ ] **Step 6: `pytest tests/test_storage.py -v`** (Docker đang chạy) → PASS. **DỪNG — báo cáo planner** (kèm output test + `docker compose ps`).

---

### Task 5: NATS JetStream publisher

**Files:**
- Create: `trading/bus/__init__.py`, `trading/bus/publisher.py`, `tests/test_publisher.py`

**Interfaces:**
- Consumes: `Bar` (Task 2)
- Produces: `BarPublisher(url: str, stream: str)` với `await connect()` (tạo stream idempotent, subjects `bars.>`), `await publish(bar: Bar)` (subject `bars.ssi.{symbol}`, payload JSON), `await close()`. JSON payload: `{"symbol","ts","open","high","low","close","volume","source"}` với `ts` ISO-8601 `+07:00` — **schema này là hợp đồng với engine ở sub-project 3.**

- [ ] **Step 1: Viết integration test fail** — `tests/test_publisher.py`:

```python
import json
from datetime import datetime

import nats
import pytest

from trading.bus.publisher import BarPublisher
from trading.calendar_vn import TZ
from trading.models import Bar

pytestmark = pytest.mark.integration


async def test_publish_roundtrip():
    pub = BarPublisher("nats://localhost:4222", "BARS")
    await pub.connect()
    bar = Bar("VCB", datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 100.0, 102.0, 99.0, 101.0, 1000)
    await pub.publish(bar)

    nc = await nats.connect("nats://localhost:4222")
    js = nc.jetstream()
    sub = await js.subscribe("bars.ssi.VCB", stream="BARS")
    msg = await sub.next_msg(timeout=5)
    data = json.loads(msg.data)
    assert data["symbol"] == "VCB" and data["close"] == 101.0
    assert data["ts"].endswith("+07:00")
    await nc.close()
    await pub.close()
```

- [ ] **Step 2: `pytest tests/test_publisher.py -v`** → FAIL.

- [ ] **Step 3: Implement `trading/bus/publisher.py`**

```python
import json
from dataclasses import asdict

import nats
from nats.js.api import StreamConfig
from nats.js.errors import BadRequestError

from trading.models import Bar


class BarPublisher:
    def __init__(self, url: str, stream: str):
        self.url = url
        self.stream = stream
        self.nc = None
        self.js = None

    async def connect(self) -> None:
        self.nc = await nats.connect(self.url)
        self.js = self.nc.jetstream()
        try:
            await self.js.add_stream(StreamConfig(name=self.stream, subjects=["bars.>"]))
        except BadRequestError:
            pass  # stream đã tồn tại với config tương đương

    async def publish(self, bar: Bar) -> None:
        payload = asdict(bar)
        payload["ts"] = bar.ts.isoformat()
        await self.js.publish(f"bars.ssi.{bar.symbol}", json.dumps(payload).encode())

    async def close(self) -> None:
        if self.nc:
            await self.nc.close()
```

- [ ] **Step 4: `pytest tests/test_publisher.py -v`** → PASS. **DỪNG — báo cáo planner.**

---

### Task 6: Discovery — ghi fixture message SSI thật + xác minh SDK REST

**Điều kiện:** cần `SSI_CONSUMER_ID`/`SSI_CONSUMER_SECRET` hợp lệ; phần stream phải chạy **trong phiên giao dịch** (9h00–11h30 / 13h00–14h45 giờ VN, ngày làm việc). Nếu ngoài phiên: chạy phần REST trước, phần stream ghi chú lại chờ phiên sau.

**Files:**
- Create: `scripts/record_fixtures.py`, `tests/fixtures/README.md`, `docs/superpowers/specs/ssi-discovery-findings.md`
- Sinh ra (bởi script, commit lại): `tests/fixtures/ssi_b_messages.jsonl`, `tests/fixtures/ssi_mi_messages.jsonl`, `tests/fixtures/ssi_daily_ohlc.json`, `tests/fixtures/ssi_intraday_ohlc.json`

**Interfaces:**
- Produces: fixtures thật + `ssi-discovery-findings.md` ghi: tên field chính xác của message B/MI (casing thật), format channel MI, chữ ký method REST của SDK (daily/intraday OHLC: tên hàm, tham số, cấu trúc response, giới hạn độ sâu lịch sử + page size). **Task 7 và 9 code dựa trên file findings này.**

- [ ] **Step 1: Đọc SDK đã cài để xác minh API REST** — chạy `python -c "import ssi_fc_data; print(ssi_fc_data.__file__)"` rồi ĐỌC source trong thư mục đó (client, model). Ghi vào findings: tên method lấy daily OHLC / intraday OHLC, tham số bắt buộc, cách truyền config. KHÔNG đoán — chỉ ghi những gì đọc được từ source.

- [ ] **Step 2: Viết `scripts/record_fixtures.py`**

```python
"""Ghi raw message SSI thành fixtures. Chạy: python scripts/record_fixtures.py [--rest-only]
Cần env SSI_CONSUMER_ID, SSI_CONSUMER_SECRET. Phần stream cần phiên giao dịch đang mở."""
import json
import os
import sys
import time


class _Cfg:  # đúng attrs SDK yêu cầu (memory ssi-fastconnect-api-facts)
    auth_type = "Bearer"
    consumerID = os.environ["SSI_CONSUMER_ID"]
    consumerSecret = os.environ["SSI_CONSUMER_SECRET"]
    url = "https://fc-data.ssi.com.vn/"
    stream_url = "https://fc-datahub.ssi.com.vn/"


def record_stream(seconds: int = 180) -> None:
    from ssi_fc_data.fc_md_stream import MarketDataStream  # đường import xác minh lại ở Step 1
    from ssi_fc_data.fc_md_client import MarketDataClient

    out_b = open("tests/fixtures/ssi_b_messages.jsonl", "a", encoding="utf-8")
    out_mi = open("tests/fixtures/ssi_mi_messages.jsonl", "a", encoding="utf-8")

    def on_message(msg):
        line = json.dumps(msg, ensure_ascii=False, default=str)
        dt = str(msg.get("DataType", msg.get("datatype", ""))) if isinstance(msg, dict) else ""
        (out_mi if dt.upper() == "MI" else out_b).write(line + "\n")

    def on_error(err):
        print("ERROR:", err, file=sys.stderr)

    cfg = _Cfg()
    stream = MarketDataStream(cfg, MarketDataClient(cfg))
    # Kênh MI: xác minh format ở Step 1; nếu SDK không nêu, thử "MI:VNINDEX" và ghi kết quả vào findings
    stream.start(on_message, on_error, "B:VCB-TCB-HPG")
    time.sleep(seconds)


def record_rest() -> None:
    # Điền theo đúng method đọc được ở Step 1; lưu response thô:
    # json.dump(resp, open("tests/fixtures/ssi_daily_ohlc.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    raise SystemExit("Điền method REST theo findings Step 1 rồi chạy lại")


if __name__ == "__main__":
    if "--rest-only" not in sys.argv:
        record_stream()
    record_rest()
```

(Script này là công cụ khám phá — được phép chỉnh `record_rest`/đường import/channel MI ngay trong task này theo những gì đọc được từ SDK; mọi thay đổi phải ghi vào findings.)

- [ ] **Step 3: Chạy REST phần trước** — `python scripts/record_fixtures.py --rest-only`, xác nhận 2 file JSON fixture có dữ liệu thật (mở xem, ghi cấu trúc + độ sâu lịch sử tối đa vào findings).

- [ ] **Step 4: Chạy stream trong phiên** — `python scripts/record_fixtures.py`, xác nhận `ssi_b_messages.jsonl` có ≥50 dòng và (nếu MI thành công) `ssi_mi_messages.jsonl` có dữ liệu. Ghi tên field thật (casing, kiểu dữ liệu, field thời gian) của cả hai loại message vào findings.

- [ ] **Step 5: Hoàn thiện `docs/superpowers/specs/ssi-discovery-findings.md`** theo cấu trúc: `## Stream B fields`, `## Stream MI fields + channel format`, `## REST daily/intraday: method, params, response, limits`, `## Điều chưa xác minh được`. **DỪNG — báo cáo planner** (kèm số dòng fixture, findings). ⚠️ Fixtures chứa dữ liệu thị trường công khai — commit được; KHÔNG được để credentials lọt vào fixture/findings.

---

### Task 7: Parser message SSI (envelope → Tick / IndexValue)

**Điều kiện:** Task 6 xong, có fixtures + findings.

**Files:**
- Create: `trading/collector/parser.py`, `tests/test_parser.py`

**Interfaces:**
- Consumes: fixtures Task 6, `Tick`/`IndexValue` (Task 2)
- Produces: `parse_message(raw: dict | str) -> Tick | IndexValue | None` — bóc envelope `{"DataType": "B", "Content": "<json string>"}` (casing biến thiên → tra key case-insensitive), map field theo findings; trả `None` với message không quan tâm (không raise). Helper `ci_get(d: dict, *names) -> Any | None`.

- [ ] **Step 1: Viết test fail dựa trên fixture THẬT** — `tests/test_parser.py`:

```python
import json
from pathlib import Path

from trading.collector.parser import ci_get, parse_message
from trading.models import IndexValue, Tick

FIXTURES = Path(__file__).parent / "fixtures"


def test_ci_get():
    assert ci_get({"LastPrice": 5}, "lastprice") == 5
    assert ci_get({"lastPrice": 5}, "LastPrice") == 5
    assert ci_get({}, "x") is None


def test_parse_all_b_fixtures():
    lines = (FIXTURES / "ssi_b_messages.jsonl").read_text(encoding="utf-8").splitlines()
    ticks = [t for t in (parse_message(json.loads(l)) for l in lines) if isinstance(t, Tick)]
    assert len(ticks) >= 50 * 0.9  # ≥90% message B parse được
    t = ticks[0]
    assert t.symbol and t.price > 0 and t.volume >= 0
    assert t.ts.tzinfo is not None and t.ts.utcoffset().total_seconds() == 7 * 3600


def test_parse_mi_fixtures():
    p = FIXTURES / "ssi_mi_messages.jsonl"
    if not p.exists() or not p.read_text(encoding="utf-8").strip():
        import pytest
        pytest.skip("chưa có fixture MI")
    lines = p.read_text(encoding="utf-8").splitlines()
    vals = [v for v in (parse_message(json.loads(l)) for l in lines) if isinstance(v, IndexValue)]
    assert vals and vals[0].value > 0


def test_unknown_message_returns_none():
    assert parse_message({"DataType": "X", "Content": "{}"}) is None
    assert parse_message({"garbage": True}) is None
```

- [ ] **Step 2: `pytest tests/test_parser.py -v`** → FAIL.

- [ ] **Step 3: Implement `trading/collector/parser.py`** — khung dưới đây là cấu trúc bắt buộc; **tên field trong `_parse_b`/`_parse_mi` phải lấy từ findings Task 6**, không dùng nguyên văn nếu findings khác:

```python
import json
from datetime import datetime
from typing import Any

from trading.calendar_vn import TZ
from trading.models import IndexValue, Tick


def ci_get(d: dict, *names: str) -> Any | None:
    lower = {k.lower(): v for k, v in d.items()}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def _parse_ts(content: dict) -> datetime | None:
    # Field thời gian + format lấy từ findings Task 6 (ví dụ "Time"/"TradingTime", "HH:MM:SS" trong ngày)
    raw = ci_get(content, "Time", "TradingTime")
    if raw is None:
        return None
    t = datetime.strptime(str(raw), "%H:%M:%S").time()
    return datetime.now(TZ).replace(hour=t.hour, minute=t.minute, second=t.second, microsecond=0)


def _parse_b(content: dict) -> Tick | None:
    symbol = ci_get(content, "Symbol")
    price = ci_get(content, "LastPrice", "Close")
    volume = ci_get(content, "LastVol", "Volume")
    ts = _parse_ts(content)
    if symbol is None or price is None or ts is None:
        return None
    return Tick(str(symbol), float(price), int(volume or 0), ts)


def _parse_mi(content: dict) -> IndexValue | None:
    index_id = ci_get(content, "IndexId", "IndexName")
    value = ci_get(content, "IndexValue", "Value")
    ts = _parse_ts(content)
    if index_id is None or value is None or ts is None:
        return None
    return IndexValue(str(index_id), ts, float(value))


def parse_message(raw: dict | str):
    try:
        if isinstance(raw, str):
            raw = json.loads(raw)
        dtype = str(ci_get(raw, "DataType") or "").upper()
        content = ci_get(raw, "Content")
        if isinstance(content, str):
            content = json.loads(content)
        if not isinstance(content, dict):
            return None
        if dtype == "B":
            return _parse_b(content)
        if dtype == "MI":
            return _parse_mi(content)
        return None
    except (ValueError, KeyError, TypeError):
        return None
```

- [ ] **Step 4: `pytest tests/test_parser.py -v`** → PASS trên fixture thật. **DỪNG — báo cáo planner** (nêu rõ field map cuối cùng đã dùng).

---

### Task 8: SSI feed wrapper (reconnect) + Watchdog

**Files:**
- Create: `trading/collector/feed.py`, `trading/collector/watchdog.py`, `tests/test_watchdog.py`, `tests/test_feed.py`

**Interfaces:**
- Consumes: `Config` (Task 1), findings Task 6
- Produces:
  - `SSIFeed(cfg: Config, on_raw: Callable[[dict], None])` — `.start()` chạy SDK trong thread daemon, tự reconnect backoff (1s, 2s, 4s… tối đa 60s) khi `on_error`/thread chết; `.stop()`. Channel build từ `cfg.symbols`: `"B:VCB-TCB-HPG"` (+ MI theo findings).
  - `Watchdog(stale_seconds, max_failures, now_fn, is_trading_fn, on_stale, on_critical)` — `.beat()` mỗi khi có message; `.check() -> None` gọi định kỳ: trong giờ giao dịch mà `now - last_beat > stale_seconds` → `on_stale()` (lần thứ `max_failures` liên tiếp → `on_critical()`); ngoài giờ không bao giờ báo.

- [ ] **Step 1: Viết test fail cho Watchdog** — `tests/test_watchdog.py`:

```python
from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.collector.watchdog import Watchdog


class Clock:
    def __init__(self):
        self.t = datetime(2026, 7, 15, 9, 30, tzinfo=TZ)
    def now(self):
        return self.t


def make(clock, trading=True):
    calls = {"stale": 0, "critical": 0}
    wd = Watchdog(
        stale_seconds=180, max_failures=3, now_fn=clock.now,
        is_trading_fn=lambda ts: trading,
        on_stale=lambda: calls.__setitem__("stale", calls["stale"] + 1),
        on_critical=lambda: calls.__setitem__("critical", calls["critical"] + 1),
    )
    return wd, calls


def test_no_alert_when_fresh():
    c = Clock(); wd, calls = make(c)
    wd.beat(); c.t += timedelta(seconds=60); wd.check()
    assert calls["stale"] == 0


def test_stale_then_critical_after_max_failures():
    c = Clock(); wd, calls = make(c)
    wd.beat()
    for i in range(3):
        c.t += timedelta(seconds=181); wd.check()
    assert calls["stale"] == 3 and calls["critical"] == 1


def test_beat_resets_failure_count():
    c = Clock(); wd, calls = make(c)
    wd.beat(); c.t += timedelta(seconds=181); wd.check()
    wd.beat(); c.t += timedelta(seconds=181); wd.check()
    assert calls["stale"] == 2 and calls["critical"] == 0


def test_silent_outside_trading_hours():
    c = Clock(); wd, calls = make(c, trading=False)
    wd.beat(); c.t += timedelta(seconds=9999); wd.check()
    assert calls["stale"] == 0
```

- [ ] **Step 2: `pytest tests/test_watchdog.py -v`** → FAIL.

- [ ] **Step 3: Implement `trading/collector/watchdog.py`**

```python
from datetime import datetime, timedelta
from typing import Callable


class Watchdog:
    def __init__(self, stale_seconds: int, max_failures: int,
                 now_fn: Callable[[], datetime],
                 is_trading_fn: Callable[[datetime], bool],
                 on_stale: Callable[[], None], on_critical: Callable[[], None]):
        self.stale = timedelta(seconds=stale_seconds)
        self.max_failures = max_failures
        self.now_fn = now_fn
        self.is_trading_fn = is_trading_fn
        self.on_stale = on_stale
        self.on_critical = on_critical
        self._last_beat = now_fn()
        self._failures = 0

    def beat(self) -> None:
        self._last_beat = self.now_fn()
        self._failures = 0

    def check(self) -> None:
        now = self.now_fn()
        if not self.is_trading_fn(now):
            return
        if now - self._last_beat > self.stale:
            self._failures += 1
            self.on_stale()
            self._last_beat = now  # reset mốc để không dồn dập mỗi lần check
            if self._failures >= self.max_failures:
                self.on_critical()
                self._failures = 0
```

- [ ] **Step 4: `pytest tests/test_watchdog.py -v`** → PASS.

- [ ] **Step 5: Viết test cho SSIFeed (fake SDK, không mạng)** — `tests/test_feed.py`:

```python
import time

from trading.collector.feed import SSIFeed, build_channel


def test_build_channel():
    assert build_channel(["VCB", "TCB", "HPG"]) == "B:VCB-TCB-HPG"


def test_feed_reconnects_on_error(monkeypatch):
    starts = []

    class FakeStream:
        def __init__(self, cfg, client):
            pass
        def start(self, on_message, on_error, channel):
            starts.append(channel)
            if len(starts) == 1:
                on_error("boom")  # lần đầu lỗi → feed phải thử lại
            else:
                on_message({"DataType": "B", "Content": "{}"})
                time.sleep(10)  # giữ "kết nối" sống

    received = []
    feed = SSIFeed.__new__(SSIFeed)
    feed._init_for_test(FakeStream, on_raw=received.append,
                        symbols=["VCB"], backoff_base=0.01)
    feed.start()
    time.sleep(0.5)
    feed.stop()
    assert len(starts) >= 2 and received
```

- [ ] **Step 6: Implement `trading/collector/feed.py`**

```python
import threading
import time
from typing import Callable

from trading.config import Config


def build_channel(symbols: list[str]) -> str:
    return "B:" + "-".join(symbols)


class SSIFeed:
    def __init__(self, cfg: Config, on_raw: Callable[[dict], None]):
        from ssi_fc_data.fc_md_client import MarketDataClient  # import xác minh ở Task 6
        from ssi_fc_data.fc_md_stream import MarketDataStream

        class _SdkCfg:
            auth_type = "Bearer"
            consumerID = cfg.ssi_consumer_id
            consumerSecret = cfg.ssi_consumer_secret
            url = "https://fc-data.ssi.com.vn/"
            stream_url = "https://fc-datahub.ssi.com.vn/"

        self._sdk_cfg = _SdkCfg()
        self._client_cls = MarketDataClient
        self._stream_cls = MarketDataStream
        self._make_stream = lambda: MarketDataStream(self._sdk_cfg, MarketDataClient(self._sdk_cfg))
        self._common(on_raw, cfg.symbols, backoff_base=1.0)

    def _init_for_test(self, stream_cls, on_raw, symbols, backoff_base):
        self._make_stream = lambda: stream_cls(None, None)
        self._common(on_raw, symbols, backoff_base)

    def _common(self, on_raw, symbols, backoff_base):
        self.on_raw = on_raw
        self.symbols = symbols
        self.backoff_base = backoff_base
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        backoff = self.backoff_base
        while not self._stop.is_set():
            errored = threading.Event()
            try:
                stream = self._make_stream()
                stream.start(self.on_raw, lambda e: errored.set(), build_channel(self.symbols))
            except Exception:
                errored.set()
            if self._stop.is_set():
                return
            # stream.start trả về / lỗi ⇒ kết nối đã chết → reconnect với backoff
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0) if errored.is_set() else self.backoff_base
```

Lưu ý cho agent: hành vi blocking của `MarketDataStream.start` phải đối chiếu findings Task 6 (nếu SDK tự chạy thread riêng và `start` trả về ngay thì `_run` phải chờ trên event lỗi thay vì loop — chỉnh theo thực tế SDK, cập nhật test tương ứng, ghi chú báo cáo).

- [ ] **Step 7: `pytest -m "not integration" -v`** → tất cả PASS. **DỪNG — báo cáo planner.**

---

### Task 9: Backfill REST + job cuối ngày

**Điều kiện:** Task 6 findings + fixtures REST.

**Files:**
- Create: `trading/collector/backfill.py`, `tests/test_backfill.py`

**Interfaces:**
- Consumes: `Storage` (Task 4), `Config` (Task 1), findings/fixtures REST (Task 6), `BarAggregator` (Task 3 — nếu intraday trả 1m thì resample 5m bằng cách gom OHLC theo bucket)
- Produces:
  - `SSIRestClient(cfg: Config)` — `.daily_ohlc(symbol, frm: date, to: date) -> list[Bar]`, `.intraday_ohlc(symbol, frm: date, to: date) -> list[Bar]` (đã chuẩn hóa thành `Bar` 5m, ts tz-aware; tên method SDK bên trong lấy từ findings; throttle `time.sleep(0.25)` giữa các call).
  - `run_backfill(storage: Storage, client, symbols: list[str], today: date) -> dict[str, int]` — với mỗi symbol: xác định từ `storage.last_bar_ts` đến nay, gọi client, upsert `bars` + `bars_daily`; trả số bar ghi mỗi symbol. Hàm thuần nhận `client` inject được → test bằng fake.
  - CLI: `python -m trading.collector.backfill --config config/config.yaml` chạy backfill một lần rồi thoát (dùng cho job cuối ngày lẫn chạy tay).

- [ ] **Step 1: Viết test fail (fake client, unit)** — `tests/test_backfill.py`:

```python
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from trading.calendar_vn import TZ
from trading.collector.backfill import parse_intraday_response, run_backfill
from trading.models import Bar

FIXTURES = Path(__file__).parent / "fixtures"


class FakeStorage:
    def __init__(self, last=None):
        self.last = last
        self.bars, self.daily = [], []
    def last_bar_ts(self, symbol):
        return self.last
    def write_bars(self, bars):
        self.bars.extend(bars)
    def write_daily(self, bars):
        self.daily.extend(bars)


class FakeClient:
    def daily_ohlc(self, symbol, frm, to):
        return [Bar(symbol, datetime(2026, 7, 14, tzinfo=TZ), 1, 2, 1, 2, 10)]
    def intraday_ohlc(self, symbol, frm, to):
        return [Bar(symbol, datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 1, 2, 1, 2, 10),
                Bar(symbol, datetime(2026, 7, 15, 9, 5, tzinfo=TZ), 2, 3, 2, 3, 20)]


def test_run_backfill_writes_missing_bars():
    st = FakeStorage(last=datetime(2026, 7, 15, 8, 55, tzinfo=TZ))
    counts = run_backfill(st, FakeClient(), ["VCB"], today=date(2026, 7, 15))
    assert counts["VCB"] == 2 and len(st.bars) == 2 and len(st.daily) == 1


def test_parse_intraday_fixture():
    raw = json.loads((FIXTURES / "ssi_intraday_ohlc.json").read_text(encoding="utf-8"))
    bars = parse_intraday_response(raw)
    assert bars and all(b.ts.tzinfo is not None for b in bars)
    assert all(b.ts.minute % 5 == 0 for b in bars)  # đã chuẩn hóa 5m
```

- [ ] **Step 2: `pytest tests/test_backfill.py -v`** → FAIL.

- [ ] **Step 3: Implement `trading/collector/backfill.py`** — cấu trúc bắt buộc (phần gọi SDK điền theo findings Task 6):

```python
import argparse
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

from trading.calendar_vn import TZ
from trading.config import Config, load_config
from trading.models import Bar
from trading.storage.db import Storage


def parse_intraday_response(raw: dict) -> list[Bar]:
    """Chuẩn hóa response intraday (cấu trúc theo findings Task 6) thành Bar 5m.
    Nếu API trả 1m: gom theo bucket 5m (open đầu, high max, low min, close cuối, volume tổng)."""
    rows = raw.get("data") or raw.get("Data") or []
    by_bucket: dict[tuple, list] = defaultdict(list)
    out: list[Bar] = []
    for r in rows:
        # field names theo findings Task 6 — chỉnh nếu khác
        sym = r.get("Symbol") or r.get("symbol")
        ts = _row_ts(r)  # helper: ghép TradingDate + Time theo findings, gán TZ
        bucket = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        by_bucket[(sym, bucket)].append((ts, r))
    for (sym, bucket), items in sorted(by_bucket.items(), key=lambda kv: kv[0]):
        items.sort(key=lambda x: x[0])
        opens = float(_f(items[0][1], "Open")); closes = float(_f(items[-1][1], "Close"))
        highs = max(float(_f(r, "High")) for _, r in items)
        lows = min(float(_f(r, "Low")) for _, r in items)
        vol = sum(int(float(_f(r, "Volume") or 0)) for _, r in items)
        out.append(Bar(sym, bucket, opens, highs, lows, closes, vol))
    return out


def _f(row: dict, name: str):
    return row.get(name) or row.get(name.lower())


def _row_ts(row: dict) -> datetime:
    raise NotImplementedError("điền theo findings Task 6 trước khi chạy test fixture")


class SSIRestClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg  # khởi tạo SDK client theo findings Task 6

    def daily_ohlc(self, symbol: str, frm: date, to: date) -> list[Bar]:
        time.sleep(0.25)
        raise NotImplementedError("điền call SDK theo findings Task 6")

    def intraday_ohlc(self, symbol: str, frm: date, to: date) -> list[Bar]:
        time.sleep(0.25)
        raise NotImplementedError("điền call SDK theo findings Task 6")


def run_backfill(storage, client, symbols: list[str], today: date) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sym in symbols:
        last = storage.last_bar_ts(sym)
        frm = (last.astimezone(TZ).date() if last else today - timedelta(days=365))
        intraday = [b for b in client.intraday_ohlc(sym, frm, today)
                    if last is None or b.ts > last]
        storage.write_bars(intraday)
        storage.write_daily(client.daily_ohlc(sym, frm, today))
        counts[sym] = len(intraday)
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()
    cfg = load_config(args.config)
    storage = Storage(cfg.db_dsn)
    storage.init_schema()
    counts = run_backfill(storage, SSIRestClient(cfg), cfg.symbols, datetime.now(TZ).date())
    print(counts)


if __name__ == "__main__":
    main()
```

**Bắt buộc:** thay mọi `NotImplementedError` bằng code thật theo findings Task 6 TRONG task này — plan chấp nhận khung này chỉ vì tên method SDK phải lấy từ findings, không được đoán. Nếu findings thiếu thông tin → DỪNG, báo planner, không đoán.

- [ ] **Step 4: `pytest tests/test_backfill.py -v`** → PASS (fake + fixture). Chạy thật: `python -m trading.collector.backfill --config config/config.yaml` (cần Docker + credentials) → in số bar ghi được, kiểm tra chéo bằng SQL: `SELECT symbol, count(*) FROM bars GROUP BY symbol;`. **DỪNG — báo cáo planner** (kèm số liệu).

---

### Task 10: Collector main — wiring + Dockerfile + kiểm chứng end-to-end

**Files:**
- Create: `trading/collector/main.py`, `trading/alerts.py`, `Dockerfile`, `tests/test_alerts.py`
- Modify: `docker-compose.yml` (thêm service `collector`)

**Interfaces:**
- Consumes: mọi thứ từ Task 1–9.
- Produces: `python -m trading.collector.main --config config/config.yaml` chạy service hoàn chỉnh; `alert(level: str, msg: str)` (INFO/WARN/CRITICAL → structured log JSON một dòng; Telegram là sub-project 4, KHÔNG làm ở đây).

- [ ] **Step 1: Viết test fail cho alerts** — `tests/test_alerts.py`:

```python
import json
import logging

from trading.alerts import alert


def test_alert_emits_structured_json(caplog):
    with caplog.at_level(logging.INFO):
        alert("WARN", "feed stale", symbol="VCB")
    record = json.loads(caplog.records[0].message)
    assert record == {"level": "WARN", "msg": "feed stale", "symbol": "VCB"}
```

- [ ] **Step 2: `pytest tests/test_alerts.py -v`** → FAIL, rồi implement `trading/alerts.py`:

```python
import json
import logging

_log = logging.getLogger("trading.alerts")
_LEVELS = {"INFO": logging.INFO, "WARN": logging.WARNING, "CRITICAL": logging.CRITICAL}


def alert(level: str, msg: str, **fields) -> None:
    _log.log(_LEVELS[level], json.dumps({"level": level, "msg": msg, **fields}, ensure_ascii=False))
```

`pytest tests/test_alerts.py -v` → PASS.

- [ ] **Step 3: Implement `trading/collector/main.py`**

```python
import argparse
import asyncio
import queue
from datetime import datetime, timedelta

from trading.alerts import alert
from trading.bus.publisher import BarPublisher
from trading.calendar_vn import TZ, is_trading_time, session_end_after
from trading.collector.aggregator import BarAggregator
from trading.collector.backfill import SSIRestClient, run_backfill
from trading.collector.feed import SSIFeed
from trading.collector.parser import parse_message
from trading.collector.watchdog import Watchdog
from trading.config import load_config
from trading.models import IndexValue, Tick
from trading.storage.db import Storage

EOD_HOUR, EOD_MINUTE = 15, 5  # job vá gap cuối ngày


async def run(cfg) -> None:
    storage = Storage(cfg.db_dsn)
    storage.init_schema()
    pub = BarPublisher(cfg.nats_url, cfg.nats_stream)
    await pub.connect()

    alert("INFO", "backfill start")
    counts = run_backfill(storage, SSIRestClient(cfg), cfg.symbols, datetime.now(TZ).date())
    alert("INFO", "backfill done", counts=counts)

    agg = BarAggregator(cfg.bar_interval_minutes, cfg.holidays)
    raw_q: queue.Queue = queue.Queue()
    feed = SSIFeed(cfg, on_raw=raw_q.put)
    feed.start()

    wd = Watchdog(
        cfg.watchdog_stale_seconds, cfg.watchdog_max_failures,
        now_fn=lambda: datetime.now(TZ),
        is_trading_fn=lambda ts: is_trading_time(ts, cfg.holidays),
        on_stale=lambda: alert("WARN", "feed stale, forcing reconnect"),
        on_critical=lambda: alert("CRITICAL", "feed stale beyond max failures"),
    )

    async def persist(bars):
        if bars:
            storage.write_bars(bars)
            for b in bars:
                await pub.publish(b)
            alert("INFO", "bars closed", n=len(bars), symbols=[b.symbol for b in bars])

    async def consume():
        loop = asyncio.get_running_loop()
        while True:
            raw = await loop.run_in_executor(None, raw_q.get)
            wd.beat()
            msg = parse_message(raw)
            if isinstance(msg, Tick):
                await persist(agg.add_tick(msg))
            elif isinstance(msg, IndexValue):
                storage.write_index_values([msg])

    async def housekeeping():
        eod_done_for: object = None
        while True:
            await asyncio.sleep(30)
            wd.check()
            storage.beat("collector")
            now = datetime.now(TZ)
            end = session_end_after(now)
            if end is not None and now >= end - timedelta(seconds=1):
                await persist(agg.flush())  # đóng bar cuối phiên (không còn tick đẩy nó đóng)
            if (now.hour, now.minute) >= (EOD_HOUR, EOD_MINUTE) and eod_done_for != now.date():
                eod_done_for = now.date()
                counts = run_backfill(storage, SSIRestClient(cfg), cfg.symbols, now.date())
                alert("INFO", "eod backfill done", counts=counts)

    await asyncio.gather(consume(), housekeeping())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run(load_config(args.config)))


if __name__ == "__main__":
    main()
```

Ghi chú: `on_stale` mới chỉ cảnh báo; force-reconnect thực hiện bằng cách `feed.stop()` + tạo `SSIFeed` mới — nếu SDK không tự hồi phục trong thực tế (quan sát ở Step 5), agent báo planner để thêm, không tự mở rộng.

- [ ] **Step 4: `Dockerfile` + service collector trong compose**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY trading ./trading
COPY config ./config
RUN pip install --no-cache-dir .
CMD ["python", "-m", "trading.collector.main", "--config", "config/config.yaml"]
```

Thêm vào `docker-compose.yml` (chỉ thêm block này, không sửa phần khác):

```yaml
  collector:
    build: .
    environment:
      DB_DSN: postgresql://trading:trading@postgres:5432/trading
      SSI_CONSUMER_ID: ${SSI_CONSUMER_ID}
      SSI_CONSUMER_SECRET: ${SSI_CONSUMER_SECRET}
    depends_on:
      postgres: {condition: service_healthy}
      nats: {condition: service_started}
    restart: unless-stopped
```

- [ ] **Step 5: Kiểm chứng end-to-end (tiêu chí sub-project 1, cần phiên live)**

1. `docker compose up -d --build` trong phiên giao dịch.
2. Sau ≥15 phút: `SELECT * FROM bars WHERE ts::date = current_date ORDER BY ts DESC LIMIT 10;` → có bar 5m mới; đối chiếu giá close vài bar với đồ thị iBoard cùng khung — lệch ≤ 1 bước giá thì đạt.
3. Kiểm tra NATS: chạy script nhỏ subscribe `bars.>` in message — thấy bar mới mỗi 5 phút.
4. **Test vá gap:** `docker compose stop collector`, chờ 10 phút giữa phiên, `docker compose start collector` → xem log `backfill done`, rồi query SQL xác nhận các bucket 5m trong khoảng dừng ĐÃ có mặt trong `bars`.
5. Chụp/lưu output các bước trên vào báo cáo. **DỪNG — báo cáo planner với đầy đủ bằng chứng.**

---

## Self-review (đã chạy)

- **Spec coverage:** §5.1 live (Task 3, 7, 8, 10), §5.2 backfill + EOD (Task 9, 10), kênh B + MI (Task 6, 7), watchdog §7.2 (Task 8), schema §6 (Task 4 — thêm `bars_daily` vì §5.2 yêu cầu daily mà §6 thiếu chỗ chứa), NATS §3 (Task 5), tự phục hồi §7.7 (restart policy Task 4/10; healthcheck container chi tiết + Telegram thuộc sub-project 4), cảnh báo phân tầng §7.6 (Task 10 — log JSON, Telegram để sub-project 4).
- **Placeholder:** hai chỗ `NotImplementedError` trong Task 9 là chủ đích — bắt buộc điền từ findings Task 6 trong cùng task, có ghi rõ "không được đoán"; không còn "TBD/tương tự task N".
- **Type consistency:** `add_tick -> list[Bar]` dùng nhất quán Task 3/10; `Storage` signatures Task 4 khớp cách gọi Task 9/10; `Watchdog` signature Task 8 khớp Task 10; payload JSON Task 5 là hợp đồng ghi rõ cho sub-project 3.
