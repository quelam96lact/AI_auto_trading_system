# Monitoring: Telegram Alerter + Grafana (Sub-project 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `alert()` (đã có, sub-project 1) gửi WARN/CRITICAL qua Telegram; thêm cảnh báo CRITICAL còn thiếu khi RiskManager chạm lỗ tối đa/ngày; Grafana đọc trực tiếp TimescaleDB hiển thị giá, PnL, vị thế, sức khỏe service.

**Bối cảnh:** Sub-project 4 trong roadmap `docs/superpowers/specs/2026-07-18-autotrading-system-design.md` §9. **Không cần phiên giao dịch** — mọi thứ kiểm chứng bằng dữ liệu giả lập (Docker) hoặc dữ liệu đã backfill. Riêng bước gửi Telegram thật cần bot Telegram thật (Task 5, tuỳ chọn nếu chưa có).

**Architecture:** `alert()` giữ nguyên chữ ký `alert(level, msg, **fields)` (không đổi bất kỳ call site nào đã có ở collector/engine) — chỉ thêm side-effect: WARN/CRITICAL spawn 1 thread daemon gọi `send_telegram()` (không chặn event loop asyncio của collector/engine, không cần thêm dependency async HTTP). Grafana không có logic riêng — chỉ đọc SQL trực tiếp từ các bảng đã có (`bars`, `pnl_daily`, `positions`, `heartbeat`), cấu hình bằng provisioning file (datasource + dashboard JSON), không viết UI.

**Tech Stack:** Python ≥3.11 thuần (`urllib.request` từ stdlib — không thêm dependency), Grafana (Docker image), `pytest`.

## Global Constraints

- **Không commit/push:** agent thực thi KHÔNG chạy `git commit`/`git push`. Cuối mỗi task: dừng, báo cáo kết quả + bằng chứng. Claude (planner) chạy `gitnexus_detect_changes`, audit, và commit.
- **Phụ thuộc chưa commit:** plan này SỬA `trading/alerts.py` (Task 2) — file này đã tồn tại trong working tree từ sub-project 1 Task 10 nhưng **CHƯA được commit** (đang chờ kiểm chứng e2e riêng). Nếu file không tồn tại khi bắt đầu Task 2, DỪNG và báo planner — không tự tạo lại từ đầu.
- **GitNexus:** Task 2, 3 SỬA file đã tồn tại (`trading/alerts.py`, `trading/risk.py`, `trading/engine/main.py`). Chạy `gitnexus_impact` cho từng symbol bị sửa (`alert`, `RiskManager`, `run`), báo risk level. Mọi thay đổi đều CỘNG THÊM hành vi (không đổi chữ ký hàm/method cũ, chỉ 1 chỗ đổi tên field private → public ở `RiskManager` — xem Task 3) nên risk kỳ vọng LOW; nếu khác, DỪNG và báo trước khi sửa.
- **Phạm vi phẫu thuật:** mỗi task chỉ tạo/sửa đúng file liệt kê trong `**Files**`. Không đụng `trading/collector/*`, `trading/bus/*`, `trading/backtest.py`, `trading/strategies/*`, `trading/storage/*`.
- **Test:** unit test thuần chạy `pytest -m "not integration"`; test cần Docker (Postgres/NATS) đánh dấu `@pytest.mark.integration`.
- **Secrets:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` qua biến môi trường (đã có `.env` trong `.gitignore` từ sub-project 1). `send_telegram()` KHÔNG raise khi thiếu env — im lặng bỏ qua (hệ thống không được crash chỉ vì chưa cấu hình Telegram).
- **Quyết định phạm vi đã chốt:**
  - **INFO không gửi Telegram** — chỉ log JSON (đã có sẵn qua `_log.log`). Chỉ WARN và CRITICAL gửi Telegram.
  - **CRITICAL "lặp đến khi xử lý":** KHÔNG cần bộ đếm giờ (scheduler) riêng trong `alerts.py`. Với cảnh báo feed-chết, `Watchdog` (sub-project 1, đã có) đã tự lặp gọi `on_critical()` mỗi `max_failures` lần kiểm tra liên tiếp thất bại (mặc định 9 phút = 3×180s) cho đến khi hết hạn — `alert()` chỉ cần gửi mỗi lần được gọi, việc "lặp" là hành vi có sẵn của call site. Với cảnh báo risk-halt (Task 3), điều kiện chỉ chuyển trạng thái MỘT LẦN mỗi ngày (không tự hết cho tới hôm sau, hệ thống đã tự dừng giao dịch) → chỉ gửi 1 lần lúc chuyển trạng thái, không lặp — quyết định hợp lý vì không có hành động nào thêm để "xử lý" ngoài chờ qua ngày mới.
  - Grafana dùng **datasource Postgres trỏ thẳng TimescaleDB** (không qua API riêng). Mỗi panel test bằng SQL độc lập qua `pytest`; xác nhận UI cuối cùng bằng mở trình duyệt (Task 5, không tự động hóa được).
  - Không xử lý "NATS chết → CRITICAL" (spec §7.4) trong plan này — đó là tính năng phát hiện-mất-kết-nối cần thêm logic cho `trading/engine/main.py` (thuộc phạm vi resilience của sub-project 3, không phải "monitoring"), ghi nhận là giới hạn đã biết.

---

### Task 1: Telegram sender

**Files:**
- Create: `trading/telegram.py`, `tests/test_telegram.py`

**Interfaces:**
- Produces: `send_telegram(text: str) -> None` — đọc `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` từ env; nếu thiếu 1 trong 2, return ngay không gọi mạng; nếu đủ, POST tới Telegram Bot API `sendMessage`.

- [ ] **Step 1: Viết test fail** — `tests/test_telegram.py`:

```python
import json

import trading.telegram as telegram_mod
from trading.telegram import send_telegram


def test_noop_when_env_not_set(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    calls = []
    monkeypatch.setattr(telegram_mod.urllib.request, "urlopen", lambda *a, **k: calls.append(a))
    send_telegram("hello")
    assert calls == []


def test_sends_request_when_env_set(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        captured["timeout"] = timeout

    monkeypatch.setattr(telegram_mod.urllib.request, "urlopen", fake_urlopen)
    send_telegram("feed stale")
    assert captured["url"] == "https://api.telegram.org/bottok123/sendMessage"
    assert captured["body"] == {"chat_id": "999", "text": "feed stale"}
    assert captured["timeout"] == 5
```

- [ ] **Step 2: `pytest tests/test_telegram.py -v`** → FAIL (module chưa tồn tại).

- [ ] **Step 3: Implement `trading/telegram.py`**

```python
import json
import os
import urllib.request

_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    data = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        _API_URL.format(token=token), data=data,
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=5)
```

- [ ] **Step 4: `pytest tests/test_telegram.py -v`** → PASS. **DỪNG — báo cáo planner.**

---

### Task 2: Wire `alert()` → Telegram cho WARN/CRITICAL

**Điều kiện:** `trading/alerts.py` phải đã tồn tại (xem Global Constraints).

**Files:**
- Modify: `trading/alerts.py` (chỉ THÊM side-effect, không đổi chữ ký `alert()`)
- Modify: `tests/test_alerts.py` (chỉ THÊM test mới, không đổi test cũ `test_alert_emits_structured_json`)

**Interfaces:**
- Consumes: `send_telegram` (Task 1)
- Produces: `alert(level: str, msg: str, **fields) -> None` — hành vi cũ (log JSON) giữ nguyên; THÊM: nếu `level in {"WARN", "CRITICAL"}`, spawn `threading.Thread(daemon=True)` gọi `send_telegram(text)` với `text = f"[{level}] {msg}" + (thông tin fields nếu có)`.

- [ ] **Step 1: Đọc `trading/alerts.py` hiện tại**, xác nhận đúng nội dung:

```python
import json
import logging

_log = logging.getLogger("trading.alerts")
_LEVELS = {"INFO": logging.INFO, "WARN": logging.WARNING, "CRITICAL": logging.CRITICAL}


def alert(level: str, msg: str, **fields) -> None:
    _log.log(_LEVELS[level], json.dumps({"level": level, "msg": msg, **fields}, ensure_ascii=False))
```

Nếu khác, DỪNG và báo planner trước khi tiếp tục (không tự "sửa cho khớp" nội dung đã có từ task khác).

- [ ] **Step 2: Viết test fail** — thêm vào cuối `tests/test_alerts.py` (giữ nguyên test `test_alert_emits_structured_json` đã có, thêm `import threading` và `import trading.alerts as alerts_mod` vào đầu file nếu chưa có):

```python
def test_info_does_not_trigger_telegram(monkeypatch):
    called = threading.Event()
    monkeypatch.setattr(alerts_mod, "send_telegram", lambda text: called.set())
    alert("INFO", "bars closed", n=1)
    assert not called.wait(timeout=0.3)


def test_warn_triggers_telegram(monkeypatch):
    received = {}
    done = threading.Event()

    def fake_send(text):
        received["text"] = text
        done.set()

    monkeypatch.setattr(alerts_mod, "send_telegram", fake_send)
    alert("WARN", "feed stale", symbol="VCB")
    assert done.wait(timeout=1.0)
    assert "feed stale" in received["text"]


def test_critical_triggers_telegram(monkeypatch):
    done = threading.Event()
    monkeypatch.setattr(alerts_mod, "send_telegram", lambda text: done.set())
    alert("CRITICAL", "feed stale beyond max failures")
    assert done.wait(timeout=1.0)
```

- [ ] **Step 3: `pytest tests/test_alerts.py -v`** → 3 test mới FAIL (chưa có `send_telegram` trong module).

- [ ] **Step 4: Sửa `trading/alerts.py`** — thay TOÀN BỘ nội dung file bằng:

```python
import json
import logging
import threading

from trading.telegram import send_telegram

_log = logging.getLogger("trading.alerts")
_LEVELS = {"INFO": logging.INFO, "WARN": logging.WARNING, "CRITICAL": logging.CRITICAL}
_NOTIFY_LEVELS = {"WARN", "CRITICAL"}


def alert(level: str, msg: str, **fields) -> None:
    _log.log(_LEVELS[level], json.dumps({"level": level, "msg": msg, **fields}, ensure_ascii=False))
    if level in _NOTIFY_LEVELS:
        text = f"[{level}] {msg}" + (f" {fields}" if fields else "")
        threading.Thread(target=send_telegram, args=(text,), daemon=True).start()
```

- [ ] **Step 5: `pytest tests/test_alerts.py -v`** → PASS (cả 4 test, kể cả test cũ). Chạy thêm `pytest -m "not integration" -v` để chắc không phá vỡ gì (test cũ ở collector gọi `alert("WARN"/"CRITICAL", ...)` sẽ spawn thread gọi `send_telegram` thật — an toàn vì env Telegram chưa set trong CI nên no-op). **DỪNG — báo cáo planner** kèm output `gitnexus_impact` cho `alert`.

---

### Task 3: Cảnh báo CRITICAL khi RiskManager chạm lỗ tối đa/ngày

**Files:**
- Modify: `trading/risk.py` (đổi tên field private `_halted_date` → public `halted_date`, KHÔNG đổi hành vi `approve()`)
- Modify: `tests/test_risk.py` (chỉ THÊM test mới)
- Modify: `trading/engine/main.py` (thêm phát hiện chuyển trạng thái halt + gọi `alert`)
- Modify: `tests/test_engine_main.py` (chỉ THÊM test mới)

**Interfaces:**
- Produces: `RiskManager.halted_date: date | None` — public (trước là `_halted_date`), đọc được từ ngoài để engine phát hiện thời điểm VỪA chuyển sang halt.

- [ ] **Step 1: Viết test fail** — thêm vào cuối `tests/test_risk.py`:

```python
def test_halted_date_publicly_readable_for_alerting():
    rm = RiskManager(capital=CAP, max_daily_loss_pct=0.03)
    assert rm.halted_date is None
    buy = Signal("VCB", "BUY", 10)
    rm.approve(buy, ref_price=1_000, positions={}, daily_pnl=-3_000_001, today=D)
    assert rm.halted_date == D
```

- [ ] **Step 2: `pytest tests/test_risk.py -v`** → FAIL (`_halted_date` chưa public).

- [ ] **Step 3: Sửa `trading/risk.py`** — đổi tên field và 2 chỗ dùng nó trong `approve` (bỏ dấu `_` ở đầu, giữ nguyên `field(default=None, init=False, repr=False)`):

```python
@dataclass
class RiskManager:
    capital: float
    max_positions: int = 5
    max_order_value_pct: float = 0.20
    max_daily_loss_pct: float = 0.03
    halted_date: date | None = field(default=None, init=False, repr=False)

    def approve(
        self,
        signal: Signal,
        ref_price: float,
        positions: dict[str, Position],
        daily_pnl: float,
        today: date,
    ) -> bool:
        if self.halted_date == today:
            return False
        if daily_pnl <= -self.capital * self.max_daily_loss_pct:
            self.halted_date = today
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

- [ ] **Step 4: `pytest tests/test_risk.py -v`** → PASS (toàn bộ, kể cả test cũ — logic không đổi, chỉ đổi tên field).

- [ ] **Step 5: Viết test fail cho engine** — thêm vào cuối `tests/test_engine_main.py`:

```python
async def test_engine_alerts_critical_on_risk_halt(storage, monkeypatch):
    import trading.engine.main as engine_main
    alerts_seen = []
    monkeypatch.setattr(engine_main, "alert", lambda level, msg, **f: alerts_seen.append((level, msg)))

    cfg = make_cfg()
    prices = [90_000] * 20 + [95_000] * 10 + [50_000] * 10  # BUY quanh 95k rồi lỗ nặng khi bán ở 50k
    bars = make_bars(prices)
    await _publish(cfg, bars)

    await run(cfg, max_messages=len(bars))

    assert ("CRITICAL", "risk halt: max daily loss reached") in alerts_seen
```

- [ ] **Step 6: `pytest tests/test_engine_main.py -v`** → test mới FAIL (chưa phát hiện chuyển trạng thái halt).

- [ ] **Step 7: Sửa `trading/engine/main.py`** — trong vòng lặp `while max_messages is None or processed < max_messages:`, đổi đoạn:

```python
            bar = bar_from_payload(json.loads(msg.data))
            fills = process_bar(bar, broker, strategy, risk, marks)
            persist_fills(fills)
```

thành:

```python
            bar = bar_from_payload(json.loads(msg.data))
            was_halted = risk.halted_date
            fills = process_bar(bar, broker, strategy, risk, marks)
            persist_fills(fills)
            if risk.halted_date is not None and risk.halted_date != was_halted:
                alert("CRITICAL", "risk halt: max daily loss reached", date=str(risk.halted_date))
```

- [ ] **Step 8: `pytest tests/test_engine_main.py -v`** (Docker đang chạy) → PASS toàn bộ (3 test, kể cả 2 test cũ). Chạy `pytest -m "not integration" -v` → pass hết. **DỪNG — báo cáo planner** kèm output `gitnexus_impact` cho `RiskManager` và `run`.

---

### Task 4: Grafana provisioning (datasource + dashboard) + test SQL từng panel

**Điều kiện:** Docker Postgres đang chạy. Không cần NATS/phiên giao dịch.

**Files:**
- Create: `grafana/provisioning/datasources/postgres.yml`, `grafana/provisioning/dashboards/dashboard.yml`, `grafana/provisioning/dashboards/trading.json`, `tests/test_dashboard_queries.py`
- Modify: `docker-compose.yml` (chỉ THÊM service `grafana`, không đụng service khác — file có thể đã có block `collector` chờ commit riêng, KHÔNG động vào)

**Interfaces:**
- Không có API Python mới — chỉ config + 4 câu SQL cố định (dùng nguyên văn trong cả `trading.json` và test):
  - Giá: `SELECT ts AS time, close FROM bars WHERE symbol = 'VCB' ORDER BY ts`
  - PnL: `SELECT date AS time, realized, unrealized, fees FROM pnl_daily ORDER BY date`
  - Vị thế: `SELECT symbol, qty, avg_price, updated_at FROM positions WHERE qty > 0`
  - Sức khỏe: `SELECT service, last_seen, extract(epoch from (now() - last_seen)) AS age_seconds FROM heartbeat`

- [ ] **Step 1: Viết test fail** — `tests/test_dashboard_queries.py`:

```python
import os
from datetime import date, datetime

import pytest

from trading.broker import Position
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
        c.execute("DELETE FROM bars WHERE symbol = 'DASH'")
        c.execute("DELETE FROM positions WHERE symbol = 'DASH'")
        c.execute("DELETE FROM pnl_daily WHERE date = '2026-07-15'")
        c.execute("DELETE FROM heartbeat WHERE service = 'dash_test'")
    return s


def test_price_panel_query(storage):
    bar = Bar("DASH", datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 10, 11, 9, 10.5, 1000)
    storage.write_bars([bar])
    with storage.conn() as c:
        rows = c.execute(
            "SELECT ts AS time, close FROM bars WHERE symbol = 'DASH' ORDER BY ts"
        ).fetchall()
    assert rows == [(bar.ts, 10.5)]


def test_pnl_panel_query(storage):
    storage.update_pnl_daily(date(2026, 7, 15), realized_delta=100.0, fee_delta=5.0, unrealized=20.0)
    with storage.conn() as c:
        row = c.execute(
            "SELECT date AS time, realized, unrealized, fees FROM pnl_daily ORDER BY date"
        ).fetchone()
    assert row == (date(2026, 7, 15), 100.0, 20.0, 5.0)


def test_positions_panel_query(storage):
    storage.upsert_position(Position("DASH", 100, 10.5))
    with storage.conn() as c:
        rows = c.execute(
            "SELECT symbol, qty, avg_price FROM positions WHERE qty > 0 AND symbol = 'DASH'"
        ).fetchall()
    assert rows == [("DASH", 100, 10.5)]


def test_heartbeat_panel_query(storage):
    storage.beat("dash_test")
    with storage.conn() as c:
        row = c.execute(
            "SELECT service, extract(epoch from (now() - last_seen)) AS age_seconds "
            "FROM heartbeat WHERE service = 'dash_test'"
        ).fetchone()
    assert row[0] == "dash_test" and row[1] < 5
```

- [ ] **Step 2: `pytest tests/test_dashboard_queries.py -v`** (Docker đang chạy) → PASS ngay (bảng đã tồn tại từ sub-project 1/3, chỉ kiểm tra câu SQL đúng — không có FAIL trước ở task này vì không tạo hàm Python mới, chỉ xác nhận SQL hoạt động trước khi đưa vào dashboard JSON).

- [ ] **Step 3: Tạo `grafana/provisioning/datasources/postgres.yml`**

```yaml
apiVersion: 1
datasources:
  - name: TimescaleDB
    type: postgres
    access: proxy
    url: postgres:5432
    database: trading
    user: trading
    secureJsonData:
      password: trading
    jsonData:
      sslmode: disable
      postgresVersion: 1600
      timescaledb: true
    isDefault: true
```

- [ ] **Step 4: Tạo `grafana/provisioning/dashboards/dashboard.yml`**

```yaml
apiVersion: 1
providers:
  - name: trading
    folder: ""
    type: file
    options:
      path: /etc/grafana/provisioning/dashboards
```

- [ ] **Step 5: Tạo `grafana/provisioning/dashboards/trading.json`**

```json
{
  "title": "Trading Overview",
  "uid": "trading-overview",
  "schemaVersion": 39,
  "panels": [
    {
      "id": 1, "title": "Gia (VCB)", "type": "timeseries",
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
      "datasource": {"type": "postgres", "uid": "TimescaleDB"},
      "targets": [{"rawSql": "SELECT ts AS time, close FROM bars WHERE symbol = 'VCB' ORDER BY ts", "format": "time_series"}]
    },
    {
      "id": 2, "title": "PnL theo ngay", "type": "timeseries",
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
      "datasource": {"type": "postgres", "uid": "TimescaleDB"},
      "targets": [{"rawSql": "SELECT date AS time, realized, unrealized, fees FROM pnl_daily ORDER BY date", "format": "time_series"}]
    },
    {
      "id": 3, "title": "Vi the hien tai", "type": "table",
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
      "datasource": {"type": "postgres", "uid": "TimescaleDB"},
      "targets": [{"rawSql": "SELECT symbol, qty, avg_price, updated_at FROM positions WHERE qty > 0", "format": "table"}]
    },
    {
      "id": 4, "title": "Suc khoe service", "type": "table",
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
      "datasource": {"type": "postgres", "uid": "TimescaleDB"},
      "targets": [{"rawSql": "SELECT service, last_seen, extract(epoch from (now() - last_seen)) AS age_seconds FROM heartbeat", "format": "table"}]
    }
  ]
}
```

- [ ] **Step 6: Thêm service `grafana` vào `docker-compose.yml`** — CHỈ thêm block dưới đây, không đụng service nào khác:

```yaml
  grafana:
    image: grafana/grafana:11.2.0
    ports: ["3000:3000"]
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning
    depends_on:
      postgres: {condition: service_healthy}
    restart: unless-stopped
```

- [ ] **Step 7: `docker compose up -d grafana`**, `docker compose ps` xác nhận `grafana` Up. **DỪNG — báo cáo planner** kèm output test Step 2 và `docker compose ps`.

---

### Task 5: Kiểm chứng cuối (trực quan — không tự động hóa được)

**Điều kiện:** Task 1-4 xong. Docker `grafana` đang chạy.

**Files:** không tạo/sửa file — task này chỉ QUAN SÁT.

- [ ] **Step 1: Mở `http://localhost:3000`**, đăng nhập `admin`/`admin` (đổi mật khẩu nếu Grafana yêu cầu — ghi lại nếu có bước đổi mật khẩu bắt buộc lần đầu).

- [ ] **Step 2: Xác nhận datasource "TimescaleDB"** — vào Connections → Data sources → TimescaleDB → nút "Save & test" phải báo thành công (kết nối được Postgres).

- [ ] **Step 3: Mở dashboard "Trading Overview"** — xác nhận cả 4 panel load không lỗi (có thể trống dữ liệu nếu DB chưa có bar/pnl thật — đó không phải lỗi, chỉ cần panel KHÔNG báo lỗi truy vấn). Nếu panel báo lỗi, đối chiếu với kết quả Task 4 Step 2 (test SQL đã pass) — khả năng cao là lỗi cấu hình JSON, sửa `trading.json`, không sửa câu SQL đã test.

- [ ] **Step 4: (Tuỳ chọn, cần bot Telegram thật)** Nếu đã có `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` thật, chạy:

```bash
python -c "from trading.alerts import alert; alert('WARN', 'test alert tu Task 5')"
```

Xác nhận tin nhắn xuất hiện trong Telegram trong vài giây. Nếu CHƯA có bot thật, bỏ qua bước này và ghi rõ lý do trong báo cáo — không phải lỗi của task.

- [ ] **Step 5: DỪNG — báo cáo planner** với: ảnh chụp/mô tả dashboard, kết quả test datasource, kết quả (hoặc lý do bỏ qua) test Telegram thật.

---

## Self-review (đã chạy)

- **Spec coverage:** §4 Alerter (Task 1-2), §7.6 cảnh báo phân tầng INFO/WARN/CRITICAL (Task 2 — INFO cố ý không gửi Telegram, quyết định ghi rõ ở Global Constraints), §7.5 risk limit → CRITICAL (Task 3 — gap thực sự trong code trước đó, nay đã vá), §9.4 dashboard Grafana (giá/PnL/vị thế/sức khỏe — Task 4, đúng 4 mục nêu trong spec). "Giả lập đứt feed → nhận WARN đúng tầng" (tiêu chí §9.4) đã được kiểm chứng ở mức đơn vị qua `Watchdog` (sub-project 1) + Task 2 (alert→Telegram); kiểm chứng Telegram thật cần bot thật, để tuỳ chọn ở Task 5.
- **Placeholder scan:** không còn "TBD" — mọi code/config đầy đủ; dashboard JSON là cấu hình tối thiểu hợp lệ, không phải khung dở dang.
- **Type consistency:** `send_telegram(text: str) -> None` (Task 1) dùng nguyên trong Task 2; `RiskManager.halted_date` (Task 3) đổi tên field DUY NHẤT, không đổi kiểu (`date | None`); `alert()` giữ nguyên chữ ký `(level, msg, **fields)` xuyên suốt — không có call site nào ở collector/engine cần sửa.
- **Ghi chú riêng:** phát hiện gap thực sự khi viết plan này — `RiskManager` (sub-project 2) không hề gọi `alert()` khi chạm lỗ tối đa/ngày, dù spec §7.5 yêu cầu CRITICAL. Task 3 vá gap này bằng cách đọc `halted_date` từ engine (không đổi `RiskManager` thành có side-effect alert — giữ nguyên tính "thuần" của RiskManager, đúng nguyên tắc thiết kế sub-project 2). "NATS chết → CRITICAL" (§7.4) CHƯA làm — cần logic phát hiện mất kết nối trong `trading/engine/main.py`, thuộc phạm vi resilience của sub-project 3, không phải monitoring — để plan riêng nếu cần.
