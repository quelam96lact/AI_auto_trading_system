# Live Session Verification (Sub-project 1, Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hoàn thiện sub-project 1 (lớp dữ liệu) — ghi fixture message SSI thật trong phiên, hoàn thiện parser dựa trên dữ liệu thật, và kiểm chứng end-to-end toàn bộ collector (backfill → stream → aggregate → ghi DB → publish NATS → vá gap) trong một phiên giao dịch thật.

**Bối cảnh:** Đây là phần tiếp nối của `docs/superpowers/plans/2026-07-18-data-layer.md` (Task 1–6, 8, 9 đã xong và commit; Task 10 Bước 1–4 đã có code sẵn trong working tree — `trading/alerts.py`, `trading/collector/main.py`, `Dockerfile` — khớp plan gốc, đã đọc/audit nhưng CHƯA commit). Ba việc còn lại đều cần **phiên giao dịch VN đang mở** (09:00–11:30 hoặc 13:00–14:45 giờ VN, ngày làm việc) và PHẢI làm tuần tự trong cùng một phiên vì mỗi việc là điều kiện của việc sau: ghi fixture (Task 1 dưới đây) → viết parser dựa trên fixture đó (Task 2) → chạy toàn bộ collector thật để kiểm chứng (Task 3, cần Task 2 vì `main.py` đã `import parser`).

**Architecture:** Không có thay đổi kiến trúc — hoàn thiện 3 mảnh còn thiếu của service `collector` đã thiết kế ở `docs/superpowers/specs/2026-07-18-autotrading-system-design.md` và `docs/superpowers/plans/2026-07-18-data-layer.md`.

**Tech Stack:** Python ≥3.11, `ssi-fc-data`, `nats-py`, `psycopg[binary]`, `pytest`, Docker Compose (Postgres/TimescaleDB + NATS đã chạy).

## Global Constraints

- **Không commit/push:** agent thực thi KHÔNG chạy `git commit`/`git push`. Cuối mỗi task: dừng, báo cáo kết quả + bằng chứng. Claude (planner) chạy `gitnexus_detect_changes`, audit, và commit.
- **GitNexus:** trước khi SỬA một hàm/class đã tồn tại (ví dụ sửa `trading/collector/main.py` nếu Bước 5 phát hiện vấn đề), chạy `gitnexus_impact({target, direction: "upstream"})` và báo risk level.
- **Phạm vi phẫu thuật:** mỗi task chỉ tạo/sửa đúng file liệt kê trong `**Files**`. Phát hiện vấn đề ngoài phạm vi → báo cáo, không tự sửa.
- **Timezone:** mọi `datetime` tz-aware `Asia/Ho_Chi_Minh` (`zoneinfo`), serialize ISO-8601 offset `+07:00`.
- **Secrets:** `SSI_CONSUMER_ID`, `SSI_CONSUMER_SECRET`, `DB_DSN` qua biến môi trường, không hardcode, không commit `.env`.
- **KHÔNG ĐOÁN:** tên field message B/MI phải lấy nguyên văn từ fixture thật ghi ở Task 1 — không dùng phỏng đoán nếu fixture cho thấy khác.
- **Điều kiện bắt buộc trước khi bắt đầu:** đang trong phiên giao dịch (kiểm bằng `python -c "from trading.calendar_vn import is_trading_time; from datetime import datetime; from zoneinfo import ZoneInfo; print(is_trading_time(datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))))"` → phải `True`), `SSI_CONSUMER_ID`/`SSI_CONSUMER_SECRET` hợp lệ trong env, Docker (`postgres`, `nats`) đang chạy (`docker compose ps`).

---

### Task 1: Ghi fixture message SSI thật (hoàn tất Task 6 Bước 4)

**Files:**
- Modify (sinh dữ liệu, không sửa tay): `tests/fixtures/ssi_b_messages.jsonl`, `tests/fixtures/ssi_mi_messages.jsonl`
- Modify: `docs/superpowers/specs/ssi-discovery-findings.md`

**Interfaces:**
- Consumes: `scripts/record_fixtures.py` (đã có, Task 6), findings hiện tại (câu hỏi mở #1–#3 trong file findings)
- Produces: fixture thật ≥50 dòng B, field map thật (casing, kiểu dữ liệu, field thời gian) ghi vào findings — đây là input bắt buộc của Task 2.

- [ ] **Step 1: Xác nhận đang trong phiên** — chạy lệnh kiểm tra ở Global Constraints, phải in `True`. Nếu `False`, DỪNG và báo planner (không đoán giờ, không chạy phần còn lại).

- [ ] **Step 2: Ghi fixture kênh B** — chạy:

```bash
python scripts/record_fixtures.py --rest-only  # bỏ qua nếu Task 6 đã có REST fixtures
python scripts/record_fixtures.py
```

Xác nhận `tests/fixtures/ssi_b_messages.jsonl` có ≥50 dòng: `python -c "print(sum(1 for _ in open('tests/fixtures/ssi_b_messages.jsonl', encoding='utf-8')))"`.

- [ ] **Step 3: Thử channel MI** — file `scripts/record_fixtures.py` hiện chỉ subscribe kênh B (`"B:VCB-TCB-HPG"`). Sửa tạm dòng gọi `stream.start(...)` (hoặc thêm 1 lần chạy riêng) để thử subscribe thêm `"MI:VNINDEX"` — thử theo thứ tự cho đến khi có message vào `ssi_mi_messages.jsonl`:
  1. Gọi `stream.start(on_message, on_error, "B:VCB-TCB-HPG,MI:VNINDEX")` (channel nối bằng dấu phẩy)
  2. Nếu không ra dữ liệu MI sau 60s: thử gọi `SwitchChannels` hai lần (một cho B, một cho MI) — đọc lại `fc_md_stream.py` nếu cần biết cách gọi thêm channel sau khi đã `start()`.
  3. Nếu cả hai cách đều không ra dữ liệu MI trong phiên này: dừng thử, ghi rõ vào findings "MI không subscribe được bằng cách X, Y — cần điều tra thêm", **không chặn Task 2** (Task 2 vẫn parse được B, `_parse_mi` cứ để nguyên khung đã có, đánh dấu chưa xác minh).

- [ ] **Step 4: Cập nhật `docs/superpowers/specs/ssi-discovery-findings.md`** — thay các dòng **[CHƯA XÁC MINH]** ở mục `## Stream B fields` bằng: tên field thật (copy nguyên văn 1 dòng JSON mẫu từ fixture), casing, kiểu dữ liệu (string hay number), field nào là giá/khối lượng/thời gian, format thời gian thật. Làm tương tự cho `## Stream MI fields + channel format` với kết quả Step 3 (kể cả nếu là "chưa subscribe được"). Xóa câu hỏi #1–#3 khỏi `## Điều chưa xác minh được` nếu đã trả lời được, giữ lại nếu MI thất bại.

- [ ] **Step 5: DỪNG — báo cáo planner** kèm: số dòng mỗi fixture, 1 dòng JSON mẫu thật của B (và MI nếu có), nội dung mới của mục `## Stream B fields`/`## Stream MI fields`.

---

### Task 2: Parser message SSI (envelope → Tick / IndexValue)

**Điều kiện:** Task 1 xong, fixture + findings đã có field map thật.

**Files:**
- Create: `trading/collector/parser.py`, `tests/test_parser.py`

**Interfaces:**
- Consumes: fixtures Task 1, `Tick`/`IndexValue` (`trading/models.py`, đã có)
- Produces: `parse_message(raw: dict | str) -> Tick | IndexValue | None` — bóc envelope `{"DataType": "B", "Content": "<json string>"}` (casing biến thiên → tra key case-insensitive), map field theo findings; trả `None` với message không quan tâm hoặc lỗi (không raise). Helper `ci_get(d: dict, *names) -> Any | None`. **Đây là hợp đồng `trading/collector/main.py` (đã có sẵn) dùng qua `from trading.collector.parser import parse_message` — không đổi tên hàm.**

- [ ] **Step 1: Viết test dựa trên fixture THẬT** — `tests/test_parser.py`:

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
    assert len(ticks) >= len(lines) * 0.9  # ≥90% message B parse được
    t = ticks[0]
    assert t.symbol and t.price > 0 and t.volume >= 0
    assert t.ts.tzinfo is not None and t.ts.utcoffset().total_seconds() == 7 * 3600


def test_parse_mi_fixtures():
    p = FIXTURES / "ssi_mi_messages.jsonl"
    if not p.exists() or not p.read_text(encoding="utf-8").strip():
        import pytest
        pytest.skip("chưa có fixture MI (xem findings Task 1)")
    lines = p.read_text(encoding="utf-8").splitlines()
    vals = [v for v in (parse_message(json.loads(l)) for l in lines) if isinstance(v, IndexValue)]
    assert vals and vals[0].value > 0


def test_unknown_message_returns_none():
    assert parse_message({"DataType": "X", "Content": "{}"}) is None
    assert parse_message({"garbage": True}) is None
```

- [ ] **Step 2: `pytest tests/test_parser.py -v`** → FAIL (`trading.collector.parser` chưa tồn tại).

- [ ] **Step 3: Implement `trading/collector/parser.py`** — khung dưới là cấu trúc bắt buộc; **thay tên field trong `_parse_b`/`_parse_mi` theo đúng findings Task 1** (khung này dùng tên phổ biến của SDK SSI làm điểm xuất phát — PHẢI đối chiếu và sửa lại cho khớp dữ liệu thật, không giữ nguyên nếu fixture khác):

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
    # Field thời gian + format lấy từ findings Task 1 (ví dụ "Time"/"TradingTime", "HH:MM:SS" trong ngày)
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

- [ ] **Step 4: `pytest tests/test_parser.py -v`** → PASS trên fixture thật (nếu `test_parse_all_b_fixtures` fail vì field không khớp, SỬA field names trong `_parse_b`/`_parse_ts` theo đúng findings — KHÔNG nới lỏng assertion của test để né lỗi).

- [ ] **Step 5: `pytest -m "not integration" -v`** → toàn bộ suite (bao gồm parser mới) PASS. **DỪNG — báo cáo planner** (nêu rõ field map cuối cùng đã dùng, có khác gì so với khung ban đầu).

---

### Task 3: Kiểm chứng end-to-end collector trong phiên thật

**Điều kiện:** Task 2 xong (`trading/collector/main.py` import `parser` thành công); Docker (`postgres`, `nats`) đang chạy; vẫn còn trong phiên giao dịch (nếu đã hết phiên khi tới bước này, dừng và báo planner để dời Bước 3 sang phiên sau — Bước 1–2 dưới đây không cần phiên đang mở).

**Files:** không tạo/sửa file — task này chỉ VẬN HÀNH và QUAN SÁT hệ thống đã có (`docker-compose.yml`, `Dockerfile`, `trading/collector/main.py` — tất cả đã tồn tại từ Task 10 Bước 1–4 của plan gốc).

**Interfaces:**
- Consumes: toàn bộ hệ thống Task 1–9 (plan gốc) + Task 2 (plan này).

- [ ] **Step 1: Build và khởi động collector** —

```bash
docker compose up -d --build
docker compose ps  # xác nhận postgres, nats, collector đều Up/healthy
docker compose logs -f collector  # theo dõi ~2 phút, Ctrl+C khi thấy "backfill done"
```

Kỳ vọng thấy log JSON dòng `{"level": "INFO", "msg": "backfill start"}` rồi `{"level": "INFO", "msg": "backfill done", "counts": {...}}` không có traceback. Nếu có traceback ImportError/AttributeError liên quan `parser`/`feed` → DỪNG, báo planner kèm log đầy đủ (không tự sửa code ngoài file đã liệt kê task trước).

- [ ] **Step 2: Xác nhận bar mới sau ≥15 phút** —

```bash
docker exec -it ai_auto_trading_system-postgres-1 psql -U trading -d trading -c \
  "SELECT symbol, ts, close, volume FROM bars WHERE ts::date = current_date ORDER BY ts DESC LIMIT 10;"
```

Kỳ vọng: có bar 5m của các symbol trong `config/config.yaml` (VCB, HPG, TCB), `ts` cách nhau đúng 5 phút, giờ tăng dần khớp đồng hồ hiện tại. Đối chiếu giá `close` 2-3 bar gần nhất với đồ thị iBoard/TradingView cùng khung giờ — lệch ≤ 1 bước giá là đạt.

- [ ] **Step 3: Xác nhận publish NATS** — chạy script subscribe tạm thời (không tạo file, chạy trực tiếp qua `python -c`):

```bash
python -c "
import asyncio, nats
async def main():
    nc = await nats.connect('nats://localhost:4222')
    js = nc.jetstream()
    sub = await js.subscribe('bars.>', stream='BARS')
    for _ in range(3):
        msg = await sub.next_msg(timeout=310)
        print(msg.subject, msg.data)
    await nc.close()
asyncio.run(main())
"
```

Kỳ vọng: nhận được ≥1 message trong vòng 5 phút+chút, subject dạng `bars.ssi.VCB`, payload JSON có `ts` kết thúc `+07:00`.

- [ ] **Step 4: Test vá gap (watchdog + backfill khi mất kết nối)** —

```bash
docker compose stop collector
```

Chờ đúng 10 phút (giữa phiên, không phải giờ nghỉ trưa/gần đóng cửa). Ghi lại giờ dừng và giờ khởi động lại.

```bash
docker compose start collector
docker compose logs -f collector  # theo dõi tới khi thấy "backfill done" lần 2
```

Sau đó chạy lại query Step 2, xác nhận các bucket 5m rơi vào khoảng 10 phút dừng ĐÃ có mặt trong `bars` (do backfill khởi động lại vá vào, không phải do stream — vì stream không chạy lúc đó).

- [ ] **Step 5: Dừng an toàn** — `docker compose stop collector` (giữ `postgres`/`nats` chạy cho lần sau nếu muốn, hoặc `docker compose down` nếu muốn dọn sạch — hỏi planner trước khi `down` nếu không chắc).

- [ ] **Step 6: DỪNG — báo cáo planner** với đầy đủ: output Step 1 (log backfill), output Step 2 (bảng SQL + so sánh iBoard), output Step 3 (message NATS nhận được), output Step 4 (trước/sau vá gap, có bucket nào bị thiếu không). Đây là tiêu chí hoàn thành cuối cùng của **toàn bộ sub-project 1**.

---

## Self-review (đã chạy)

- **Spec coverage:** hoàn tất 3 phần còn thiếu của sub-project 1 — Task 6 Bước 4 (stream fixtures), Task 7 (parser), Task 10 Bước 5 (kiểm chứng e2e) từ plan gốc `2026-07-18-data-layer.md`. Không việc nào trong 3 việc này làm được ngoài phiên giao dịch, đúng như user yêu cầu.
- **Placeholder scan:** không còn "TBD"/"tương tự Task N" — Task 2 tái sử dụng nguyên code khung từ plan gốc (đã có thật, không phải placeholder) kèm chỉ dẫn rõ ràng phải đối chiếu field thật, không được giữ nguyên nếu sai.
- **Type consistency:** `parse_message(raw: dict | str) -> Tick | IndexValue | None` khớp cách gọi trong `trading/collector/main.py` đã tồn tại (`msg = parse_message(raw)`, `isinstance(msg, Tick)`); không đổi tên hàm/kiểu trả về so với plan gốc.
- **Ghi chú riêng:** Task 10 Bước 1–4 (plan gốc) — `trading/alerts.py`, `trading/collector/main.py`, `Dockerfile`, sửa `docker-compose.yml` — đã có sẵn trong working tree, đã đọc và khớp plan gốc nguyên văn, nhưng **planner chưa commit** (chờ xác nhận riêng ngoài phiên). Task 3 ở trên giả định các file này đúng như hiện trạng; nếu planner sửa gì trước phiên, cập nhật lại plan này trước khi thực thi.
