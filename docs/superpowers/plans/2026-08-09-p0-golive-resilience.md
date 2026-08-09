# P0 Go-Live Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vá 4 lỗi resilience khiến hệ thống không thể chạy tự động 24/7 trên
VPS Ubuntu: engine crash-loop vì một message hỏng, collector chết vì một lỗi DB
tạm thời, bar bị mất im lặng khi ghi DB lỗi, và không có cảnh báo nào khi một
service chết.

**Architecture:** Không đổi kiến trúc. Bốn thay đổi cục bộ: (1) bọc thân vòng
lặp message của engine bằng try/except + `msg.term()`; (2) tách thân vòng
housekeeping của collector thành 2 hàm module-level (`housekeeping_tick` /
`housekeeping_loop`) để bọc được try/except **và** unit-test được; (3) tách
`persist` + `on_stream_message` (đang là closure) thành `persist_bars` /
`make_stream_message_handler` module-level có xử lý lỗi; (4) thêm
`scripts/heartbeat_check.py` chạy bằng cron trên host, đọc bảng `heartbeat`
và bắn Telegram khi service ngừng đập.

**Tech Stack:** Python 3.11+, pytest (`uv run pytest`), ruff, psycopg 3,
nats-py. **Không thêm dependency mới.**

## Global Constraints

- **Bắt buộc chạy `gitnexus_impact({target: "<symbol>", direction: "upstream"})`
  trước khi sửa bất kỳ function/method nào**, và báo cáo blast radius. Dừng lại
  hỏi nếu kết quả là HIGH/CRITICAL. (CLAUDE.md § GitNexus — Always Do)
- **Agent thực thi KHÔNG được `git commit`, KHÔNG được `git push`.** Làm xong
  mỗi task thì báo cáo kèm bằng chứng (output test) rồi dừng. Claude (planner)
  audit và commit.
- **Chạy `gitnexus_detect_changes()` sau khi sửa xong mỗi task**, đính kèm kết
  quả vào báo cáo.
- Chỉ sửa đúng các file liệt kê trong từng task. **Không** refactor code xung
  quanh, **không** dọn dead code có sẵn. Nếu phát hiện vấn đề ngoài phạm vi thì
  báo cáo, không tự sửa.
- Giữ nguyên style hiện có: alert qua `trading.alerts.alert(level, msg, **fields)`,
  comment tiếng Việt, `except Exception` rộng là **cố ý** cho hệ trading live
  (đã ghi nhận ở `pyproject.toml` ignore `BLE001`).
- Tiêu chí chung cho MỌI task: `uv run pytest -m "not integration" -v` pass toàn
  bộ (baseline hiện tại: **168 passed**), và `uv run ruff check trading tests
  scripts` sạch.
- Mọi chuỗi lỗi đưa vào alert phải cắt ngắn (`[:200]`) để không làm vỡ log/Telegram.

## Quyết định thiết kế đã chốt (không tự đổi)

1. **Engine gặp lỗi khi xử lý bar → `msg.term()` (bỏ hẳn message), không `nak()`
   retry.** Lý do: `broker` là state in-memory đã bị `process_bar` mutate trước
   khi lỗi xảy ra, và `storage.write_order()` là INSERT thuần không idempotent —
   redeliver sẽ ghi trùng lệnh và tính trùng PnL. Bỏ tín hiệu của 1 nến 5 phút
   ít tệ hơn nhiều so với vào lệnh nhân đôi. Bù lại bằng alert CRITICAL kèm
   payload để người vào điều tra.
2. **`housekeeping_loop` / `run()` nhận tham số `max_ticks` / `max_messages` chỉ
   để test được.** Đây không phải tính năng mới: `trading/engine/main.py::run()`
   đã có sẵn `max_messages` đúng theo pattern này.
3. **Dead-man's switch làm bằng script Python + cron trên host, KHÔNG dùng
   Grafana alert rule.** Lý do: logic thành hàm thuần unit-test được (tiêu chí
   kiểm chứng rõ ràng theo CLAUDE.md nguyên tắc 4), còn YAML alert rule của
   Grafana thì không test được và thêm một điểm chết nữa (Grafana phải sống).
4. **Test của Task 1 là integration test** (`tests/test_engine_main.py` — cả
   file này đã là `pytest.mark.integration`, cần Docker Postgres + NATS). Tách
   thân vòng lặp engine ra thành hàm module-level để unit-test được sẽ phải kéo
   theo 7 collaborator (broker/strategy/risk/trailing_stop/marks/real_risk/storage)
   — vi phạm phạm vi phẫu thuật. **Hệ quả phải chấp nhận: CI (`-m "not
   integration"`) sẽ không chạy test này**; agent phải tự chạy nó với Docker và
   dán output vào báo cáo.

---

## File Structure

| File | Trách nhiệm | Task |
|------|-------------|------|
| `trading/engine/main.py` | Bọc lỗi thân vòng lặp message + housekeeping của engine | 1 |
| `tests/test_engine_main.py` | Integration test: poison message không giết engine | 1 |
| `trading/collector/main.py` | Tách `housekeeping_tick`/`housekeeping_loop`/`persist_bars`/`make_stream_message_handler` module-level, có xử lý lỗi | 2, 3 |
| `tests/test_collector_main.py` | **Tạo mới** — unit test cho 4 hàm trên | 2, 3 |
| `scripts/heartbeat_check.py` | **Tạo mới** — dead-man's switch, cron trên host | 4 |
| `tests/test_heartbeat_check.py` | **Tạo mới** — unit test hàm thuần `stale_services` | 4 |
| `DEPLOYMENT.md` | Thêm §9 hướng dẫn cài cron cho heartbeat check | 4 |

---

### Task 1: Engine không chết vì một message hỏng

**Files:**
- Modify: `trading/engine/main.py:88-129` (vòng lặp trong `run()`)
- Test: `tests/test_engine_main.py` (thêm 1 test vào cuối file)

**Interfaces:**
- Consumes: `trading.alerts.alert`, `nats.aio.msg.Msg.term()` (đã có sẵn ở
  `.venv/Lib/site-packages/nats/aio/msg.py:148`, không cần thêm dependency).
- Produces: không có API mới. `run(cfg, max_messages)` giữ nguyên chữ ký.

**Yêu cầu bắt buộc trước khi sửa:**

- [ ] **Step 0: GitNexus impact**

Chạy `gitnexus_impact({target: "run", direction: "upstream"})` (symbol
`trading/engine/main.py::run`) và dán kết quả vào báo cáo. Nếu HIGH/CRITICAL →
dừng, hỏi lại.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `tests/test_engine_main.py`. Test publish một payload hỏng (thiếu
key `close` → `bar_from_payload` ném `KeyError`) rồi một bar tốt, và đòi hỏi
engine **không** ném exception, có alert CRITICAL, và vẫn xử lý bar tốt phía sau.

```python
async def test_engine_survives_poison_message_and_keeps_processing(storage, monkeypatch):
    import json

    import trading.engine.main as engine_main

    alerts_seen = []
    monkeypatch.setattr(
        engine_main,
        "alert",
        lambda level, msg, **f: alerts_seen.append((level, msg)),
    )

    cfg = make_cfg()
    nc = await nats.connect(cfg.nats_url)
    js = nc.jetstream()
    await js.publish("bars.ssi.ENGT", json.dumps({"symbol": "ENGT"}).encode())
    await nc.close()
    await _publish(cfg, make_bars([10]))

    # Không được ném exception: message hỏng phải bị term(), không được giết engine.
    await run(cfg, max_messages=2)

    assert any(
        lvl == "CRITICAL" and "engine failed to process bar" in m
        for lvl, m in alerts_seen
    )
    with storage.conn() as c:
        n = c.execute(
            "SELECT count(*) FROM heartbeat WHERE service = 'engine'"
        ).fetchone()[0]
    assert n == 1, "engine phải vẫn đập heartbeat sau khi gặp message hỏng"
```

- [ ] **Step 2: Chạy test để xác nhận nó FAIL**

Đảm bảo Docker đang chạy trước: `docker compose up -d postgres nats`

Run:
```bash
uv run pytest tests/test_engine_main.py::test_engine_survives_poison_message_and_keeps_processing -v
```
Expected: **FAIL** với `KeyError: 'close'` thoát ra khỏi `run()`.

- [ ] **Step 3: Sửa `trading/engine/main.py`**

Thay nguyên khối `processed = 0` … `processed += 1` (dòng 88-129) bằng:

```python
    def idle_maintenance() -> None:
        """expire + heartbeat, không được để lỗi DB tạm thời giết engine."""
        try:
            expire_stale_real_orders()
            storage.beat("engine")
        except Exception as e:
            alert(
                "WARN",
                "engine maintenance failed, continuing",
                error=f"{type(e).__name__}: {e}"[:200],
            )

    processed = 0
    try:
        while max_messages is None or processed < max_messages:
            try:
                msg = await sub.next_msg(timeout=60)
            except nats.errors.TimeoutError:
                idle_maintenance()
                continue
            try:
                bar = bar_from_payload(json.loads(msg.data))
                was_halted = risk.halted_date
                was_real_halted = real_risk.halted_date
                fills = process_bar(
                    bar,
                    broker,
                    strategy,
                    risk,
                    trailing_stop,
                    marks,
                    on_crossover=on_real_crossover,
                )
                persist_fills(fills)
                if risk.halted_date is not None and risk.halted_date != was_halted:
                    alert(
                        "CRITICAL",
                        "risk halt: max daily loss reached",
                        date=str(risk.halted_date),
                    )
                if (
                    real_risk.halted_date is not None
                    and real_risk.halted_date != was_real_halted
                ):
                    storage.save_real_risk_halt(real_risk.halted_date)
                    alert(
                        "CRITICAL",
                        "REAL risk halt: max daily loss reached",
                        date=str(real_risk.halted_date),
                    )
                await msg.ack()
            except Exception as e:
                # term() chứ không nak(): broker là state in-memory đã bị
                # process_bar mutate, và write_order() là INSERT thuần không
                # idempotent — redeliver sẽ ghi trùng lệnh + tính trùng PnL.
                # Bỏ 1 nến an toàn hơn vào lệnh nhân đôi. Xem plan P0 Task 1.
                alert(
                    "CRITICAL",
                    "engine failed to process bar, message dropped",
                    error=f"{type(e).__name__}: {e}"[:200],
                    payload=msg.data.decode("utf-8", "replace")[:200],
                )
                await msg.term()
            idle_maintenance()
            processed += 1
    finally:
        await nc.close()
```

Lưu ý: `processed += 1` phải nằm **ngoài** try/except (cả nhánh lỗi cũng tăng),
nếu không `max_messages` sẽ không bao giờ đạt và test treo 60s mỗi vòng.

- [ ] **Step 4: Chạy test để xác nhận PASS**

Run:
```bash
uv run pytest tests/test_engine_main.py -v -m integration
```
Expected: **PASS** toàn bộ file (6 test cũ + 1 test mới = 7 passed).

- [ ] **Step 5: Regression + lint**

Run:
```bash
uv run pytest -m "not integration" -q
uv run ruff check trading tests
```
Expected: `168 passed` (không giảm), ruff `All checks passed!`.

- [ ] **Step 6: GitNexus + báo cáo (KHÔNG commit)**

Chạy `gitnexus_detect_changes()`. Báo cáo gồm: kết quả impact ở Step 0, output
Step 4 và Step 5, kết quả detect_changes. **Dừng, chờ audit.**

---

### Task 2: Collector không chết vì một lỗi DB tạm thời

**Files:**
- Modify: `trading/collector/main.py:71-107` (closure `housekeeping` + lời gọi)
- Test: `tests/test_collector_main.py` (**tạo mới**)

**Interfaces:**
- Consumes: `cfg` (Config), `storage` (Storage), `wd` (Watchdog) — đã có trong `run()`.
- Produces (Task 3 không dùng, nhưng test dùng):
  - `HousekeepingState` — dataclass, field `eod_done_for: date | None = None`,
    `last_account_sync: datetime | None = None`.
  - `async def housekeeping_tick(cfg, storage, wd, state: HousekeepingState) -> None`
    — chạy đúng 1 vòng, **được phép ném exception**.
  - `async def housekeeping_loop(cfg, storage, wd, sleep_seconds: float = 30.0,
    max_ticks: int | None = None) -> None` — vòng lặp, **nuốt mọi exception của
    tick** và alert WARN.

- [ ] **Step 0: GitNexus impact**

Chạy `gitnexus_impact({target: "run", direction: "upstream"})` cho
`trading/collector/main.py::run`. Dán kết quả. Dừng nếu HIGH/CRITICAL.

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/test_collector_main.py`:

```python
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from trading.calendar_vn import TZ
from trading.collector.main import (
    HousekeepingState,
    housekeeping_loop,
    housekeeping_tick,
)
from trading.config import Config


@pytest.fixture
def cfg():
    return Config(
        symbols=["VCB"],
        indices=[],
        bar_interval_minutes=5,
        ssi_equity_accounts=[],
        holidays=set(),
        db_dsn="postgresql://x:x@localhost/db",
        nats_url="nats://localhost:4222",
        nats_stream="BARS",
        watchdog_stale_seconds=180,
        watchdog_max_failures=3,
        ssi_consumer_id="c",
        ssi_consumer_secret="s",
        ssi_api_key="k",
        ssi_api_secret="a",
        ssi_private_key="pk",
        real_trading_enabled=False,
        real_order_capital=1_000_000_000.0,
        real_order_account="ACC",
    )


async def test_housekeeping_loop_survives_db_failure(cfg, monkeypatch):
    """Postgres restart vài giây không được giết collector."""
    import trading.collector.main as collector_main

    alerts_seen = []
    monkeypatch.setattr(
        collector_main,
        "alert",
        lambda level, msg, **f: alerts_seen.append((level, msg)),
    )

    storage = MagicMock()
    storage.beat.side_effect = OSError("connection refused")
    wd = MagicMock()

    # Không được ném exception ra ngoài.
    await housekeeping_loop(cfg, storage, wd, sleep_seconds=0, max_ticks=2)

    assert storage.beat.call_count == 2, "loop phải chạy tiếp sau lần lỗi đầu"
    assert (
        sum(1 for lvl, m in alerts_seen if lvl == "WARN" and "housekeeping tick failed" in m)
        == 2
    )


async def test_housekeeping_tick_beats_and_checks_watchdog(cfg, monkeypatch):
    import trading.collector.main as collector_main

    async def fake_sync(*args):
        return None

    monkeypatch.setattr(collector_main, "sync_account_data", fake_sync)
    monkeypatch.setattr(collector_main, "sync_derivative_data", fake_sync)
    monkeypatch.setattr(collector_main, "alert", lambda *a, **k: None)

    storage = MagicMock()
    wd = MagicMock()
    state = HousekeepingState()

    await housekeeping_tick(cfg, storage, wd, state)

    wd.check.assert_called_once()
    storage.beat.assert_called_once_with("collector")
    assert state.last_account_sync is not None


async def test_housekeeping_tick_skips_account_sync_within_5_minutes(cfg, monkeypatch):
    import trading.collector.main as collector_main

    calls = []

    async def fake_sync(*args):
        calls.append(args)

    monkeypatch.setattr(collector_main, "sync_account_data", fake_sync)
    monkeypatch.setattr(collector_main, "sync_derivative_data", fake_sync)
    monkeypatch.setattr(collector_main, "alert", lambda *a, **k: None)

    storage = MagicMock()
    wd = MagicMock()
    state = HousekeepingState(last_account_sync=datetime.now(TZ) - timedelta(minutes=1))

    await housekeeping_tick(cfg, storage, wd, state)

    assert calls == [], "chưa đủ 5 phút thì không sync account"
```

- [ ] **Step 2: Chạy test để xác nhận nó FAIL**

Run:
```bash
uv run pytest tests/test_collector_main.py -v
```
Expected: **FAIL** với `ImportError: cannot import name 'HousekeepingState' from 'trading.collector.main'`.

- [ ] **Step 3: Sửa `trading/collector/main.py`**

Thêm import ở đầu file (gộp vào dòng import sẵn có, giữ thứ tự ruff):

```python
from dataclasses import dataclass
from datetime import date, datetime, timedelta
```

Thêm ngay sau dòng `EOD_HOUR, EOD_MINUTE = 15, 5`:

```python
@dataclass
class HousekeepingState:
    eod_done_for: date | None = None
    last_account_sync: datetime | None = None


async def housekeeping_tick(cfg, storage, wd, state: HousekeepingState) -> None:
    """Một vòng housekeeping. Được phép ném — housekeeping_loop chịu trách nhiệm bắt."""
    wd.check()
    storage.beat("collector")
    now = datetime.now(TZ)
    if state.last_account_sync is None or now - state.last_account_sync >= timedelta(
        minutes=5
    ):
        state.last_account_sync = now
        try:
            await sync_account_data(cfg, storage)
        except Exception as e:
            alert("WARN", "account sync failed, skipping", error=str(e)[:100])
        try:
            await sync_derivative_data(cfg, storage)
        except Exception as e:
            alert("WARN", "derivative sync failed, skipping", error=str(e)[:100])
    if (now.hour, now.minute) >= (
        EOD_HOUR,
        EOD_MINUTE,
    ) and state.eod_done_for != now.date():
        state.eod_done_for = now.date()
        eod_client = SSIRestClient(cfg, storage)
        try:
            counts = await run_backfill(storage, eod_client, cfg.symbols, now.date())
            alert("INFO", "eod backfill done", counts=counts)
        finally:
            await eod_client.close()


async def housekeeping_loop(
    cfg,
    storage,
    wd,
    sleep_seconds: float = 30.0,
    max_ticks: int | None = None,
) -> None:
    """Vòng housekeeping vô hạn. Một lỗi (vd Postgres restart) KHÔNG được giết
    collector — bắt hết, alert WARN, rồi chạy tiếp vòng sau.
    `max_ticks` chỉ dùng cho test, cùng pattern với run(max_messages) của engine."""
    state = HousekeepingState()
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        await asyncio.sleep(sleep_seconds)
        try:
            await housekeeping_tick(cfg, storage, wd, state)
        except Exception as e:
            alert(
                "WARN",
                "housekeeping tick failed, continuing",
                error=f"{type(e).__name__}: {e}"[:200],
            )
        ticks += 1
```

Rồi **xóa toàn bộ** closure `async def housekeeping():` (dòng 71-106 bản cũ) và
thay dòng `await housekeeping()` bằng:

```python
    await housekeeping_loop(cfg, storage, wd)
```

- [ ] **Step 4: Chạy test để xác nhận PASS**

Run:
```bash
uv run pytest tests/test_collector_main.py -v
```
Expected: **3 passed**.

- [ ] **Step 5: Regression + lint**

Run:
```bash
uv run pytest -m "not integration" -q
uv run ruff check trading tests
```
Expected: `171 passed` (168 + 3 mới), ruff sạch.

- [ ] **Step 6: GitNexus + báo cáo (KHÔNG commit)**

`gitnexus_detect_changes()` → phạm vi phải chỉ chạm `trading/collector/main.py`.
Báo cáo rồi dừng.

---

### Task 3: Bar không bị mất im lặng

**Files:**
- Modify: `trading/collector/main.py:39-44` (closure `persist`) và `:59-66`
  (closure `on_stream_message`)
- Test: `tests/test_collector_main.py` (thêm vào file đã tạo ở Task 2)

**Interfaces:**
- Consumes: `HousekeepingState` không liên quan; dùng `storage` (Storage),
  `pub` (`trading.bus.publisher.BarPublisher`), `wd` (Watchdog).
- Produces:
  - `async def persist_bars(storage, pub, bars) -> None` — ghi DB + publish NATS,
    **không bao giờ ném**; lỗi → alert CRITICAL.
  - `def make_stream_message_handler(wd, storage, pub)` → trả về callback
    `on_stream_message(msg)` đồng bộ (khớp chữ ký `AsyncStream.streaming.on_data`).

- [ ] **Step 0: GitNexus impact**

Chạy `gitnexus_impact({target: "run", direction: "upstream"})` cho
`trading/collector/main.py::run` (lại, vì Task 2 đã đổi file). Dán kết quả.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `tests/test_collector_main.py`:

```python
async def test_persist_bars_alerts_critical_instead_of_raising(monkeypatch):
    """DB lỗi không được nuốt im lặng thành 'Task exception was never retrieved'."""
    import trading.collector.main as collector_main
    from trading.models import Bar

    alerts_seen = []
    monkeypatch.setattr(
        collector_main,
        "alert",
        lambda level, msg, **f: alerts_seen.append((level, msg)),
    )

    storage = MagicMock()
    storage.write_bars.side_effect = OSError("connection refused")
    pub = MagicMock()
    bar = Bar("VCB", datetime(2026, 7, 15, 9, 5, tzinfo=TZ), 1.0, 1.0, 1.0, 1.0, 10)

    await collector_main.persist_bars(storage, pub, [bar])

    assert any(
        lvl == "CRITICAL" and "bar persist/publish failed" in m
        for lvl, m in alerts_seen
    )


async def test_stream_handler_skips_unparsable_message_without_raising(monkeypatch):
    import trading.collector.main as collector_main

    alerts_seen = []
    monkeypatch.setattr(
        collector_main,
        "alert",
        lambda level, msg, **f: alerts_seen.append((level, msg)),
    )
    monkeypatch.setattr(
        collector_main,
        "parse_interval_message",
        MagicMock(side_effect=ValueError("bad payload")),
    )

    wd = MagicMock()
    handler = collector_main.make_stream_message_handler(wd, MagicMock(), MagicMock())

    handler({"DataType": "X", "Content": "{{{"})

    wd.beat.assert_not_called()
    assert any(
        lvl == "WARN" and "failed to parse stream message" in m for lvl, m in alerts_seen
    )
```

- [ ] **Step 2: Chạy test để xác nhận nó FAIL**

Run:
```bash
uv run pytest tests/test_collector_main.py -v -k "persist_bars or stream_handler"
```
Expected: **FAIL** với `AttributeError: module 'trading.collector.main' has no attribute 'persist_bars'`.

- [ ] **Step 3: Sửa `trading/collector/main.py`**

Thêm 2 hàm module-level (đặt ngay trên `HousekeepingState`):

```python
async def persist_bars(storage, pub, bars) -> None:
    """Ghi bar vào DB + publish NATS. KHÔNG BAO GIỜ ném: hàm này được gọi qua
    asyncio.create_task() fire-and-forget, exception thoát ra sẽ bị asyncio nuốt
    thành 'Task exception was never retrieved' — bar mất mà không ai biết."""
    if not bars:
        return
    try:
        storage.write_bars(bars)
        for b in bars:
            await pub.publish(b)
        alert("INFO", "bars closed", n=len(bars), symbols=[b.symbol for b in bars])
    except Exception as e:
        alert(
            "CRITICAL",
            "bar persist/publish failed, bars dropped",
            error=f"{type(e).__name__}: {e}"[:200],
            symbols=[b.symbol for b in bars],
            ts=[b.ts.isoformat() for b in bars],
        )


def make_stream_message_handler(wd, storage, pub):
    """Callback cho AsyncStream.streaming.on_data. Một message dị dạng không
    được ném ngược vào vòng stream của SDK."""

    def on_stream_message(msg):
        try:
            bar = parse_interval_message(msg)
        except Exception as e:
            alert(
                "WARN",
                "failed to parse stream message, skipping",
                error=f"{type(e).__name__}: {e}"[:200],
            )
            return
        if bar is not None:
            wd.beat()
            asyncio.create_task(persist_bars(storage, pub, [bar]))
        # Index streaming (VNINDEX/VN30): không có nguồn dữ liệu real-time nào
        # trong ssi-sdk hiện tại — xem PLAN_INDEX_STREAMING.md (điều tra thật
        # 2026-08-07). Không viết IndexValue cho tới khi có nguồn dữ liệu khác.

    return on_stream_message
```

Trong `run()`: **xóa** closure `async def persist(bars):` (dòng 39-44 bản gốc) và
closure `def on_stream_message(msg):` (dòng 59-66 bản gốc). Đổi dòng tạo feed
thành:

```python
    feed = SSIFeed(
        cfg, storage, on_message=make_stream_message_handler(wd, storage, pub)
    )
    feed.start()
```

**Cảnh báo thứ tự:** `wd` đang được khai báo **sau** `on_stream_message` trong
bản gốc. Sau khi sửa, lời gọi `make_stream_message_handler(wd, ...)` phải nằm
sau block `wd = Watchdog(...)`. Giữ nguyên `_on_stale` và `wd = Watchdog(...)`
ở vị trí cũ, chỉ di chuyển phần tạo `feed` xuống dưới nếu cần.

- [ ] **Step 4: Chạy test để xác nhận PASS**

Run:
```bash
uv run pytest tests/test_collector_main.py -v
```
Expected: **5 passed** (3 của Task 2 + 2 mới).

- [ ] **Step 5: Regression + lint**

Run:
```bash
uv run pytest -m "not integration" -q
uv run ruff check trading tests
```
Expected: `173 passed`, ruff sạch.

- [ ] **Step 6: GitNexus + báo cáo (KHÔNG commit)**

`gitnexus_detect_changes()` → chỉ `trading/collector/main.py`. Báo cáo rồi dừng.

---

### Task 4: Dead-man's switch — cảnh báo khi service chết

**Files:**
- Create: `scripts/heartbeat_check.py`
- Create: `tests/test_heartbeat_check.py`
- Modify: `DEPLOYMENT.md` (thêm §9 ở cuối, trước mục "Not covered here")

**Interfaces:**
- Consumes: `trading.calendar_vn.TZ` / `is_trading_time`,
  `trading.telegram.send_telegram`, `psycopg` (đã là dependency).
- Produces:
  - `SERVICES: tuple[str, ...] = ("collector", "engine")`
  - `def stale_services(rows, now, max_age_seconds, expected=SERVICES) -> list[str]`
    — hàm thuần, `rows` là `list[tuple[str, datetime]]`.
  - `def main() -> int` — exit code 0 = ổn, 1 = có cảnh báo, 2 = sai cấu hình.

- [ ] **Step 0: GitNexus impact**

Không sửa symbol có sẵn (chỉ tạo file mới + sửa docs) → không cần
`gitnexus_impact`. Vẫn phải chạy `gitnexus_detect_changes()` ở Step 6.

- [ ] **Step 1: Viết test thất bại**

Tạo `tests/test_heartbeat_check.py`:

```python
from datetime import datetime, timedelta

from scripts.heartbeat_check import stale_services
from trading.calendar_vn import TZ

NOW = datetime(2026, 7, 15, 10, 0, tzinfo=TZ)


def test_no_stale_when_all_services_fresh():
    rows = [
        ("collector", NOW - timedelta(seconds=30)),
        ("engine", NOW - timedelta(seconds=45)),
    ]
    assert stale_services(rows, NOW, 300) == []


def test_service_past_max_age_is_stale():
    rows = [
        ("collector", NOW - timedelta(seconds=30)),
        ("engine", NOW - timedelta(seconds=600)),
    ]
    assert stale_services(rows, NOW, 300) == ["engine"]


def test_missing_service_row_is_stale():
    rows = [("collector", NOW - timedelta(seconds=30))]
    assert stale_services(rows, NOW, 300) == ["engine"]


def test_all_services_missing_are_stale():
    assert stale_services([], NOW, 300) == ["collector", "engine"]
```

- [ ] **Step 2: Chạy test để xác nhận nó FAIL**

Run:
```bash
uv run pytest tests/test_heartbeat_check.py -v
```
Expected: **FAIL** với `ModuleNotFoundError: No module named 'scripts.heartbeat_check'`.

`scripts/` **không có** `__init__.py` và **không cần** thêm — pytest đã đặt
rootdir vào `sys.path`, nên `from scripts.X import Y` chạy được. Đây đúng là
cách `tests/test_confirm_real_order.py:6` và `tests/test_backfill_history.py:3`
đang làm. Đừng tạo `scripts/__init__.py`.

- [ ] **Step 3: Viết `scripts/heartbeat_check.py`**

```python
"""Dead-man's switch: cảnh báo Telegram khi collector/engine ngừng đập heartbeat.

Chạy bằng cron TRÊN HOST (không phải trong container) — nếu chạy trong chính
container đang chết thì nó cũng chết theo. Xem DEPLOYMENT.md §9.

Exit code: 0 = ổn, 1 = có cảnh báo đã gửi, 2 = sai cấu hình.
"""

import os
import sys
from datetime import datetime, timedelta

import psycopg

from trading.calendar_vn import TZ, is_trading_time
from trading.telegram import send_telegram

SERVICES = ("collector", "engine")
DEFAULT_MAX_AGE_SECONDS = 300


def stale_services(rows, now, max_age_seconds, expected=SERVICES) -> list[str]:
    """rows: list[(service, last_seen)] đọc từ bảng heartbeat.

    Trả về tên các service thiếu hẳn dòng heartbeat hoặc có last_seen quá hạn.
    """
    seen = {r[0]: r[1] for r in rows}
    limit = timedelta(seconds=max_age_seconds)
    return [
        svc
        for svc in expected
        if seen.get(svc) is None or now - seen[svc] > limit
    ]


def main() -> int:
    dsn = os.environ.get("DB_DSN")
    if not dsn:
        print("DB_DSN chưa được set", file=sys.stderr)
        return 2
    max_age = int(os.environ.get("HEARTBEAT_MAX_AGE_SECONDS", DEFAULT_MAX_AGE_SECONDS))

    now = datetime.now(TZ)
    # Chỉ cảnh báo trong giờ giao dịch: cả 2 service đều đập 24/7, nhưng ngoài
    # phiên thì service chết không gây hại ngay — tránh spam đêm/cuối tuần.
    if not is_trading_time(now):
        return 0

    try:
        with psycopg.connect(dsn, connect_timeout=10) as c:
            rows = c.execute("SELECT service, last_seen FROM heartbeat").fetchall()
    except Exception as e:
        send_telegram(
            f"[CRITICAL] heartbeat check không đọc được DB: {type(e).__name__}: {e}"[:300]
        )
        return 1

    stale = stale_services(rows, now, max_age)
    if stale:
        send_telegram(
            f"[CRITICAL] service ngừng heartbeat quá {max_age}s: {', '.join(stale)}"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Chạy test để xác nhận PASS**

Run:
```bash
uv run pytest tests/test_heartbeat_check.py -v
```
Expected: **4 passed**.

- [ ] **Step 5: Kiểm chứng thủ công + docs**

Chạy thật với DB đang sống (Docker đã up ở Task 1):
```bash
DB_DSN=postgresql://trading:trading@localhost:5432/trading uv run python scripts/heartbeat_check.py; echo "exit=$?"
```
Expected: exit 0 nếu đang trong giờ giao dịch và heartbeat tươi, hoặc exit 0
(thoát sớm) nếu chạy ngoài giờ. Dán output vào báo cáo.

Chạy với DSN sai để xác nhận nhánh lỗi:
```bash
DB_DSN=postgresql://trading:trading@localhost:59999/trading uv run python scripts/heartbeat_check.py; echo "exit=$?"
```
Expected: exit 1 (hoặc 0 nếu ngoài giờ giao dịch — nói rõ trong báo cáo bạn chạy
lúc mấy giờ).

Thêm vào `DEPLOYMENT.md`, ngay trước mục `## Not covered here`:

````markdown
## 9. Dead-man's switch (heartbeat)

`collector` và `engine` ghi vào bảng `heartbeat` mỗi ~30-60 giây. Nếu một
service chết, Docker `restart: unless-stopped` sẽ thử khởi động lại — nhưng nếu
nó chết lặp (crash loop) hoặc treo mà không thoát, container vẫn "đang chạy" và
không ai biết. `scripts/heartbeat_check.py` đọc bảng đó và bắn Telegram khi một
service quá hạn.

Chạy bằng cron **trên host**, không phải trong container:

```bash
sudo crontab -e
# thêm (chỉ chạy trong giờ giao dịch VN, script tự bỏ qua ngoài phiên):
*/5 9-15 * * 1-5 cd /opt/trading && set -a && . ./.env && set +a && DB_DSN=postgresql://trading:trading@127.0.0.1:5432/trading /usr/local/bin/uv run python scripts/heartbeat_check.py >> /var/log/trading-heartbeat.log 2>&1
```

Ngưỡng mặc định 300 giây, đổi bằng `HEARTBEAT_MAX_AGE_SECONDS`.

Kiểm chứng một lần sau khi cài: `docker compose stop engine`, đợi >5 phút trong
giờ giao dịch, xác nhận có tin Telegram, rồi `docker compose start engine`.
````

- [ ] **Step 6: Regression + lint + báo cáo (KHÔNG commit)**

Run:
```bash
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts
```
Expected: `177 passed` (173 + 4 mới), ruff sạch.

Chạy `gitnexus_detect_changes()`, báo cáo, dừng chờ audit.

---

## Tiêu chí nghiệm thu toàn kế hoạch

Claude (planner) chỉ chấp nhận khi có đủ bằng chứng:

1. `uv run pytest -m "not integration" -q` → **177 passed** (từ baseline 168).
2. `uv run pytest tests/test_engine_main.py -m integration -v` → **7 passed**
   (cần Docker Postgres + NATS).
3. `uv run ruff check trading tests scripts` → `All checks passed!`
4. Output `gitnexus_detect_changes()` của cả 4 task, xác nhận phạm vi chỉ gồm:
   `trading/engine/main.py`, `trading/collector/main.py`,
   `scripts/heartbeat_check.py`, `tests/test_engine_main.py`,
   `tests/test_collector_main.py`, `tests/test_heartbeat_check.py`,
   `DEPLOYMENT.md`.
5. Không có commit/push nào do agent thực thi tạo ra.

## Ngoài phạm vi kế hoạch này (cố ý không làm)

Các mục P1/P2 trong audit 2026-08-09 — **không** đụng vào trong 4 task trên:
bug `daily_pnl` tích lũy ở `trading/engine/logic.py:44`, Dockerfile dùng
`uv.lock`, `.dockerignore`, non-root user, password Grafana/Postgres, retention
JetStream, connection pool cho `Storage`, xử lý SIGTERM. Nếu agent thấy chúng
trong lúc làm, **báo cáo, không sửa**.
