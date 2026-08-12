# Prompt thực thi: SSI SDK Migration — Phase 2 (viết lại `backfill.py`)

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `PLAN_SSI_SDK_MIGRATION.md` (đặc biệt mục 1.1, 2.1.1, 2.2, và bảng "Phase 0 HOÀN THÀNH" cuối mục 4) — prompt này chỉ giao đúng **Phase 2**, KHÔNG phải toàn bộ plan.

---

## ⚠️ Giới hạn phạm vi — đọc kỹ trước khi bắt đầu

**CHỈ sửa `trading/collector/backfill.py`, `trading/collector/main.py` (2 đoạn cụ thể, xem Task 2), và `tests/test_backfill.py`. KHÔNG động vào `feed.py`/`parser.py`** — đó là Phase 3, cần chờ 1 lần chạy trong giờ giao dịch để lấy sample `IntervalMessage` thật (chưa có).

**KHÔNG xoá code cũ của SDK cũ (`ssi_fc_data`)** — theo `PLAN_SSI_SDK_MIGRATION.md` mục 7 (Rollback), giữ song song code cũ tới khi Phase 4 E2E ổn định ≥2 phiên. Đổi tên class cũ `SSIRestClient` → `SSIRestClientLegacy` (giữ nguyên logic, không sửa), rồi viết `SSIRestClient` mới dùng `ssi-sdk`.

**Trước khi sửa bất kỳ symbol nào** (đặc biệt `run_backfill`, `SSIRestClient`, `main.py::run`): chạy `gitnexus_impact({target: "<tên symbol>", direction: "upstream"})`, báo cáo blast radius trước khi sửa. `run_backfill`/`SSIRestClient` được gọi từ `main.py` (2 chỗ) — kỳ vọng risk MEDIUM (ảnh hưởng collector service, không phải trực tiếp trading/tiền), không phải HIGH/CRITICAL. Nếu impact analysis báo HIGH/CRITICAL, dừng lại hỏi trước khi tiếp tục.

**Sau khi xong:** chạy `gitnexus_detect_changes()`, dán kết quả vào báo cáo.

**KHÔNG tự commit, không tự push.** Báo cáo lại (diff, test output, `gitnexus_detect_changes()`) để Claude (planner) audit rồi mới commit.

---

## Bối cảnh

Phase 0 đã xác nhận thật (không phải giả định) qua chạy live với credentials thật (xem `PLAN_SSI_SDK_MIGRATION.md` mục 1.1 + bảng cuối mục 4):
- `SSI_API_KEY`/`SSI_API_SECRET` đủ để lấy `access_token` (KHÔNG cần OTP trên account này).
- `trading/collector/ssi_auth.py::ensure_authenticated(cfg, storage)` (đã code, đã test ở Phase 1, **KHÔNG sửa file này**) trả về `AsyncAuth` đã có `access_token` hợp lệ — refresh từ `refresh_token` lưu trong bảng `ssi_auth_state`, raise `RuntimeError` rõ ràng nếu cần OTP thủ công.
- OHLC 5 phút thật đã lấy được: `tests/fixtures/ssi_sdk_ohlc_5m_vcb.json` (230 bar VCB, raw wire JSON — field string, `trading_date` format `"YYYY/MM/DD HH:mm:ss"`).
- `get_ohlc_5minute_historical()` trả `list[OHLCData]` — dataclass đã parse sẵn, field **đã là số** (`open_price`, `high_price`, `low_price`, `close_price`: `float`; `volume`: `int`), không cần tự ép kiểu.
- Intraday (5m) **PHẢI** truyền `from_date`/`to_date` dạng `"YYYY/MM/DD HH:mm:ss"` (có giờ) — thiếu giờ → lỗi `400213 "Invalid Date/Timestamp"` (đã gặp thật). Daily dùng `"YYYY/MM/DD"` (không giờ) — **chưa test thật, theo docs**.
- Response OHLC **không** expose `totalRecord`/tổng số record cho caller (khác SDK cũ) — phải tự đoán còn trang tiếp theo bằng heuristic `len(rows) == size` (xem Task 1.3).

---

## Task 1 — Viết `SSIRestClient` mới trong `backfill.py`

### 1.1. Đổi tên class cũ, giữ nguyên logic
Đổi `class SSIRestClient` hiện tại (dùng `ssi_fc_data`) → `class SSIRestClientLegacy` (chỉ đổi tên, không sửa gì bên trong). Class này hiện không còn ai gọi (Task 2 sẽ đổi cả 2 call site trong `main.py` sang class mới) — **không xoá**, giữ làm rollback reference.

### 1.2. Xác nhận API surface trước khi code (bắt buộc, không đoán)
Chạy lệnh sau để xác nhận `get_ohlc_1day_historical` có tồn tại đúng tên và chữ ký như suy đoán không (KHÔNG cần credentials thật, chỉ cần package cài được):
```bash
uv run --with ssi-sdk python -c "
import inspect
from ssi_sdk.services.market_data import AsyncMarketDataService
for name in dir(AsyncMarketDataService):
    if 'day' in name.lower() or '1d' in name.lower():
        print(name, inspect.signature(getattr(AsyncMarketDataService, name)))
"
```
Nếu tên method khác `get_ohlc_1day_historical`, dùng đúng tên thật tìm được — **không hardcode theo suy đoán trong plan**.

### 1.3. Viết `SSIRestClient` mới

```python
class SSIRestClient:
    def __init__(self, cfg: Config, storage: Storage):
        self._cfg = cfg
        self._storage = storage
        self._auth = None  # AsyncAuth, lazy — xem _ensure_data()
        self._data = None  # AsyncData, lazy

    async def _ensure_data(self):
        if self._data is None:
            from ssi_sdk import AsyncData
            from trading.collector.ssi_auth import ensure_authenticated
            self._auth = await ensure_authenticated(self._cfg, self._storage)
            self._data = AsyncData(self._auth)
        return self._data

    async def close(self) -> None:
        if self._auth is not None:
            await self._auth.close()

    @staticmethod
    def _fmt_day(d: date) -> str:
        return d.strftime("%Y/%m/%d")

    @staticmethod
    def _fmt_intraday(d: date, end_of_day: bool) -> str:
        # intraday BẮT BUỘC có giờ (đã xác nhận thật — xem Bối cảnh phía trên)
        t = "23:59:59" if end_of_day else "00:00:00"
        return f"{d:%Y/%m/%d} {t}"

    async def daily_ohlc(self, symbol: str, frm: date, to: date) -> list[Bar]:
        data = await self._ensure_data()
        rows = await data.market_data.get_ohlc_1day_historical(  # tên xác nhận ở 1.2
            symbol, self._fmt_day(frm), self._fmt_day(to)
        )
        return _ohlc_rows_to_bars(rows)

    async def intraday_ohlc(self, symbol: str, frm: date, to: date) -> list[Bar]:
        data = await self._ensure_data()
        rows = await self._paged_intraday(data, symbol, frm, to)
        return _ohlc_rows_to_bars(rows)

    async def _paged_intraday(self, data, symbol: str, frm: date, to: date):
        # Response KHÔNG expose totalRecord (khác SDK cũ) — heuristic: nếu
        # trang trả đủ `size` dòng thì có thể còn trang sau, gọi tiếp;
        # nếu trả ít hơn `size` thì chắc chắn hết.
        size = 1000
        all_rows, page = [], 1
        while True:
            rows = await data.market_data.get_ohlc_5minute_historical(
                symbol,
                self._fmt_intraday(frm, end_of_day=False),
                self._fmt_intraday(to, end_of_day=True),
                page=page,
                size=size,
            )
            all_rows.extend(rows)
            if len(rows) < size:
                break
            page += 1
        return all_rows
```

**Lý do thiết kế `_ensure_data()` lazy:** giữ nguyên chữ ký `run_backfill(storage, client, symbols, today)` không đổi nhiều — auth phức tạp (async, cần storage) được đóng gói bên trong `SSIRestClient`, caller (`main.py`, tests) chỉ cần `SSIRestClient(cfg, storage)` + `await client.close()` sau khi dùng xong.

### 1.4. Hàm map `OHLCData` → `Bar` (mới, KHÔNG dùng lại `parse_intraday_response`/`parse_daily_response` cũ — field/format khác hẳn)

```python
def _ohlc_rows_to_bars(rows) -> list[Bar]:
    out = [
        Bar(
            r.symbol,
            _parse_trading_date(r.trading_date),
            float(r.open_price),
            float(r.high_price),
            float(r.low_price),
            float(r.close_price),
            int(r.volume),
        )
        for r in rows
    ]
    out.sort(key=lambda b: b.ts)
    return out


def _parse_trading_date(s: str) -> datetime:
    # Xác nhận thật 2026-07-25: "YYYY/MM/DD HH:mm:ss" (xem
    # tests/fixtures/ssi_sdk_ohlc_5m_vcb.json), gán TZ VN.
    dt = datetime.strptime(s, "%Y/%m/%d %H:%M:%S")
    return dt.replace(tzinfo=TZ)
```

**KHÔNG xoá** `parse_intraday_response`, `parse_daily_response`, `_row_ts`, `_f` cũ — vẫn được `test_parse_intraday_fixture` dùng (test cho `SSIRestClientLegacy`/fixture cũ), giữ nguyên.

### 1.5. Sửa `run_backfill()` thành async

```python
async def run_backfill(storage, client, symbols: list[str], today: date) -> dict[str, int]:
    counts: dict[str, int] = {}
    try:
        for sym in symbols:
            last = storage.last_bar_ts(sym)
            frm = last.astimezone(TZ).date() if last else today - timedelta(days=7)
            intraday = [
                b for b in await client.intraday_ohlc(sym, frm, today)
                if last is None or b.ts > last
            ]
            storage.write_bars(intraday)
            storage.write_daily(await client.daily_ohlc(sym, frm, today))
            counts[sym] = len(intraday)
    except Exception as e:
        from trading.alerts import alert
        alert("WARN", "backfill failed, skipping", error=str(e)[:100])
    return counts
```

Giữ nguyên logic vòng lặp/try-except hiện có — chỉ thêm `async`/`await` ở đúng chỗ gọi `client.*`.

### 1.6. `main()` CLI ở cuối `backfill.py`
Bọc lại bằng `asyncio.run()`:
```python
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()
    cfg = load_config(args.config)
    storage = Storage(cfg.db_dsn)
    storage.init_schema()

    async def _run():
        client = SSIRestClient(cfg, storage)
        try:
            counts = await run_backfill(storage, client, cfg.symbols, datetime.now(TZ).date())
        finally:
            await client.close()
        print(counts)

    asyncio.run(_run())
```
Cần thêm `import asyncio` ở đầu file (chưa có).

**Kiểm chứng Task 1:** `uv run --with ssi-sdk python -c "import ast; ast.parse(open('trading/collector/backfill.py', encoding='utf-8').read()); print('OK')"` — không cần credentials thật, chỉ check syntax + import hợp lệ.

---

## Task 2 — Sửa 2 call site trong `main.py` (KHÔNG sửa gì khác trong file này)

**Dòng 10:** `from trading.collector.backfill import SSIRestClient, run_backfill` — giữ nguyên (tên class/hàm không đổi).

**Dòng 27-35** (backfill lúc khởi động):
```python
alert("INFO", "backfill start")
client = SSIRestClient(cfg, storage)
try:
    counts = await run_backfill(storage, client, cfg.symbols, datetime.now(TZ).date())
    alert("INFO", "backfill done", counts=counts)
except Exception as e:
    alert("WARN", "backfill failed, skipping", error=str(e)[:100])
    counts = {}
finally:
    await client.close()
```

**Dòng 86-88** (EOD backfill trong `housekeeping()`):
```python
eod_client = SSIRestClient(cfg, storage)
try:
    counts = await run_backfill(storage, eod_client, cfg.symbols, now.date())
    alert("INFO", "eod backfill done", counts=counts)
finally:
    await eod_client.close()
```

**KHÔNG sửa** `SSIFeed`, `consume()`, `persist()`, phần còn lại của `housekeeping()`, hay `main()` cuối file — đó là Phase 3 hoặc không liên quan.

**Kiểm chứng Task 2:** `uv run --with ssi-sdk python -c "import ast; ast.parse(open('trading/collector/main.py', encoding='utf-8').read()); print('OK')"`.

---

## Task 3 — Test mới trong `tests/test_backfill.py`

**KHÔNG xoá** `test_run_backfill_writes_missing_bars` hay `test_parse_intraday_fixture` hiện có — nhưng `FakeClient`/`test_run_backfill_writes_missing_bars` cần sửa thành async (vì `run_backfill` giờ là `async def`):

```python
class FakeClient:
    async def daily_ohlc(self, symbol, frm, to):
        return [Bar(symbol, datetime(2026, 7, 14, tzinfo=TZ), 1, 2, 1, 2, 10)]
    async def intraday_ohlc(self, symbol, frm, to):
        return [Bar(symbol, datetime(2026, 7, 15, 9, 0, tzinfo=TZ), 1, 2, 1, 2, 10),
                Bar(symbol, datetime(2026, 7, 15, 9, 5, tzinfo=TZ), 2, 3, 2, 3, 20)]


async def test_run_backfill_writes_missing_bars():
    st = FakeStorage(last=datetime(2026, 7, 15, 8, 55, tzinfo=TZ))
    counts = await run_backfill(st, FakeClient(), ["VCB"], today=date(2026, 7, 15))
    assert counts["VCB"] == 2 and len(st.bars) == 2 and len(st.daily) == 1
```

**Thêm test mới** dùng fixture thật `tests/fixtures/ssi_sdk_ohlc_5m_vcb.json` — test hàm `_ohlc_rows_to_bars()` (import từ `trading.collector.backfill`, có thể cần đổi tên hàm thành public nếu muốn import trực tiếp, hoặc test gián tiếp qua mock — tự quyết định theo style file test hiện có):

```python
def test_ohlc_rows_to_bars_from_real_fixture():
    from ssi_sdk.models import OHLCData
    from trading.collector.backfill import _ohlc_rows_to_bars

    raw = json.loads((FIXTURES / "ssi_sdk_ohlc_5m_vcb.json").read_text(encoding="utf-8"))
    rows = OHLCData.from_list(raw["data"])
    bars = _ohlc_rows_to_bars(rows)

    assert len(bars) == 230
    assert all(b.ts.tzinfo is not None for b in bars)
    # dòng đầu fixture: 2026/07/24 14:45:00, open=54100 (xem file fixture)
    first = next(b for b in bars if b.ts == datetime(2026, 7, 24, 14, 45, tzinfo=TZ))
    assert first.symbol == "VCB" and first.open == 54100 and first.volume == 189100
```

**Kiểm chứng Task 3:** `uv run pytest tests/test_backfill.py -v` — tất cả pass (cũ + mới).

---

## Sau khi hoàn thành cả 3 task

1. `uv run pytest -m "not integration" -v` — **tất cả test cũ (≥54) vẫn pass**, cộng test mới.
2. `uv run ruff check trading tests` (nếu `ruff` có sẵn trong môi trường — nếu báo `command not found`, bỏ qua, ghi chú lại là môi trường thiếu, không phải lỗi code).
3. `gitnexus_detect_changes()` — dán kết quả vào báo cáo.
4. Báo cáo: danh sách file sửa/tạo, kết quả test, kết quả `gitnexus_detect_changes()`, và **tên method thật** tìm được ở Task 1.2 (nếu khác `get_ohlc_1day_historical`). **Không commit, không push.**

## Lưu ý về việc test bằng credentials thật

Task này **không cần chạy với `SSI_API_KEY`/`SSI_API_SECRET` thật** — toàn bộ kiểm chứng dùng fixture đã ghi sẵn (`tests/fixtures/ssi_sdk_ohlc_5m_vcb.json`) và `FakeClient`/mock. Nếu muốn tự tin hơn có thể chạy thử `python -m trading.collector.backfill --config config/config.yaml` với credentials thật (giống cách `.env` được nạp thủ công ở Phase 0 — xem hướng dẫn PowerShell trong lịch sử trò chuyện), nhưng **không bắt buộc** để hoàn thành task này.
