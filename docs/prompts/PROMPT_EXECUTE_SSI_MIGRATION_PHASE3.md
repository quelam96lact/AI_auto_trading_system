# Prompt thực thi: SSI SDK Migration — Phase 3 (viết lại `feed.py`/`parser.py`)

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `PLAN_SSI_SDK_MIGRATION.md` (đặc biệt mục "Phase 3" đã cập nhật với 3 finding từ architecture review, và mục "Phase 0 HOÀN THÀNH").

---

## ⚠️ Ranh giới quan trọng — đọc kỹ trước khi bắt đầu

**Phần lớn Phase 3 viết + test được NGAY, KHÔNG cần phiên giao dịch đang mở** — vì:
- Field/type của `IntervalMessage`/`TradeMessage` đã biết chính xác từ source code SDK (đọc ở Phase 0), chỉ **giá trị thật + format chuỗi thời gian chính xác** (`interval_time`/`trading_time`) là chưa xác nhận.
- Kết nối WebSocket + subscribe đã test thành công ngoài giờ giao dịch (Phase 0) — logic connect/reconnect/restart hoàn toàn test được bằng fake/mock, không cần thị trường mở.

**1 điểm PHẢI đánh dấu rõ ràng "chưa xác nhận" trong code (không được coi là chắc chắn đúng):** format chuỗi của `IntervalMessage.interval_time`/`trading_time`. Giả định trong prompt này: cùng format với REST OHLC đã xác nhận (`"YYYY/MM/DD HH:mm:ss"`) — đây là **suy đoán hợp lý, không phải xác nhận thật**. Code phải viết sao cho nếu suy đoán này sai, **không crash toàn bộ collector** (return `None`, log lỗi, bỏ qua message đó) — sẽ xác nhận/sửa ở Phase 4 khi có phiên giao dịch thật.

**CHỈ sửa:** `trading/collector/feed.py`, `trading/collector/parser.py`, `trading/collector/watchdog.py` (chỉ nếu cần, xem Task 4), `trading/collector/main.py` (phần feed/consume/persist/watchdog wiring — phần backfill đã xong ở Phase 2, không đụng lại), `tests/test_feed.py`, `tests/test_parser.py`.

**KHÔNG xoá code cũ** — đổi tên `SSIFeed` hiện tại → `SSIFeedLegacy` (giữ nguyên logic, giữ `build_channel()` vì `SSIFeedLegacy`/test cũ vẫn dùng), viết `SSIFeed` mới dùng `ssi-sdk`.

**Trước khi sửa symbol nào:** `gitnexus_impact({target: "...", direction: "upstream"})`. Kỳ vọng risk HIGH tương tự Phase 2 (do `main.py::run` là 1 hàm chạm nhiều execution flow) — nếu tất cả caller đều nằm trong danh sách file "CHỈ sửa" ở trên, tiếp tục (như đã thống nhất ở Phase 2); nếu có caller lạ ngoài danh sách, dừng lại hỏi.

**Sau khi xong:** `gitnexus_detect_changes()`, dán kết quả vào báo cáo. **Không tự commit, không tự push.**

---

## Bối cảnh — quyết định kiến trúc đã chốt (không phải mơ hồ)

1. **Bỏ `BarAggregator` cho luồng bar** (finding review #4 + quyết định Phase 0): vì subscribe qua `subscribe_symbol_ohlcv(symbols, Timeframe.MINUTE_5)` (đã test thành công Phase 0) trả **thẳng `IntervalMessage` = bar 5 phút đã đóng sẵn từ SSI**, không phải tick thô — không cần tự gom tick → bar nữa. `BarAggregator`/`add_tick`/`flush` **không xoá file** (dùng cho backtest/resample chỗ khác nếu có — kiểm tra trước khi đụng), chỉ **ngừng gọi** trong luồng streaming mới.
2. **Bỏ thread+queue trong `SSIFeed`** (finding review #5): `ssi-sdk` là async-native (`AsyncStream`), viết lại bằng `asyncio.Task` + `asyncio.Event`, tích hợp thẳng vào loop đã có ở `main.py`, không cần `threading.Thread`/`queue.Queue` cầu nối sang async nữa.
3. **Sửa watchdog "alert-theatre"** (finding review #2): `main.py` hiện tại `on_stale=lambda: alert("WARN", "feed stale, forcing reconnect")` — chỉ log, không có gọi reconnect thật (đã xác nhận đọc code). Phải wire thật.
4. **Index streaming (VNINDEX/VN30) — quyết định cần xác nhận lại với Claude/user trước khi code nếu muốn mở rộng, KHÔNG tự ý bỏ qua âm thầm:** SDK mới không có message type "IndexValue" tương đương MI cũ. Đề xuất: `subscribe_symbol_trade(cfg.indices)` — khi nhận `TradeMessage` với `symbol` nằm trong `cfg.indices`, map `IndexValue(index_id=msg.symbol, ts=parse(msg.trading_time), value=msg.price)`. Đây cũng là suy đoán hợp lý (index "trade price" ≈ giá trị chỉ số), **không chắc đúng 100%** — nếu thấy quá rủi ro/phức tạp so với thời gian, có thể **bỏ qua tạm thời** (index value ngừng cập nhật) và ghi rõ TODO trong code + báo cáo lại, KHÔNG được tự quyết định âm thầm bỏ mà không nói.

---

## Task 1 — Đổi tên `SSIFeed` cũ, giữ nguyên

`class SSIFeed` hiện tại (dùng `ssi_fc_data`) → `class SSIFeedLegacy` (chỉ đổi tên). Giữ `build_channel()` nguyên vẹn (vẫn dùng cho legacy + test cũ `test_build_channel`).

---

## Task 2 — Viết `SSIFeed` mới (async, connect/reconnect/restart)

```python
import asyncio
import logging
from typing import Callable

from trading.collector.ssi_auth import ensure_authenticated
from trading.config import Config
from trading.storage.db import Storage

logger = logging.getLogger("trading.collector.feed")


class SSIFeed:
    """Streaming feed dùng ssi-sdk AsyncStream — async-native, không thread+
    queue (finding review #5: thread+queue là workaround SDK cũ đồng bộ)."""

    def __init__(self, cfg: Config, storage: Storage, on_message: Callable,
                 backoff_base: float = 1.0):
        self._cfg = cfg
        self._storage = storage
        self._on_message = on_message  # nhận raw IntervalMessage/TradeMessage
        self._backoff_base = backoff_base
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._auth = None   # AsyncAuth hiện tại, None nếu chưa/đang không kết nối
        self._stream = None  # AsyncStream hiện tại

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._stream is not None:
            await self._stream.streaming.disconnect()
        if self._task is not None:
            await self._task

    async def restart(self) -> None:
        """Ngắt kết nối hiện tại NGAY (bỏ qua backoff) — dùng khi watchdog
        phát hiện feed stale. Vòng lặp _run() tự phát hiện mất kết nối,
        đóng auth cũ, và reconnect."""
        if self._stream is not None:
            await self._stream.streaming.disconnect()

    async def _run(self) -> None:
        backoff = self._backoff_base
        while not self._stop.is_set():
            connected_at = None
            try:
                from ssi_sdk import AsyncStream
                from ssi_sdk.enums import Timeframe

                self._auth = await ensure_authenticated(self._cfg, self._storage)
                self._stream = AsyncStream(self._auth)
                self._stream.streaming.on_data = self._on_message
                await self._stream.streaming.connect()
                await self._stream.streaming.subscribe_symbol_ohlcv(
                    self._cfg.symbols, Timeframe.MINUTE_5
                )
                # TODO index streaming — xem mục Bối cảnh #4, quyết định lại
                # với Claude/user trước khi thêm subscribe_symbol_trade(indices).
                connected_at = asyncio.get_event_loop().time()
                await self._stream.streaming.wait()  # block tới khi disconnect
            except Exception as e:
                logger.warning("SSIFeed connection error: %s", e)
            finally:
                if self._auth is not None:
                    await self._auth.close()
                self._auth = None
                self._stream = None
            if self._stop.is_set():
                return
            alive = (asyncio.get_event_loop().time() - connected_at) if connected_at else 0
            backoff = self._backoff_base if alive >= 60.0 else min(backoff * 2, 60.0)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                return  # stop được set trong lúc chờ backoff
            except asyncio.TimeoutError:
                pass  # hết backoff, loop lại reconnect
```

**Lý do các quyết định trong code trên:**
- Backoff logic (base → x2 mỗi lần chết sớm, reset nếu sống ≥60s, cap 60s) — giữ nguyên triết lý `SSIFeedLegacy` cũ, chỉ đổi cơ chế đồng bộ hoá (`asyncio.Event`/`wait_for` thay `threading.Event`/`Thread`).
- `restart()` không tự raise nếu gọi khi chưa kết nối (`self._stream is None` → no-op) — an toàn khi gọi từ watchdog bất kỳ lúc nào.
- `_run()` tự đóng `auth` (`await self._auth.close()`) mỗi khi mất kết nối — tránh rò rỉ HTTP client, nhất quán với cách `ssi_auth.py`/`backfill.py::SSIRestClient` đã làm.

**Kiểm chứng Task 2:** viết test mới trong `tests/test_feed.py` dùng fake `AsyncStream`-like object (có `.streaming.connect()`, `.streaming.subscribe_symbol_ohlcv()`, `.streaming.wait()`, `.streaming.disconnect()`, `.streaming.on_data` settable) — mô phỏng: (1) kết nối thành công rồi "chết" → `_run()` phải reconnect (`connect()` được gọi ≥2 lần); (2) gọi `restart()` khi đang kết nối → `disconnect()` được gọi trên stream hiện tại. `uv run pytest tests/test_feed.py -v` pass.

---

## Task 3 — Parser cho `IntervalMessage` (đánh dấu rõ phần chưa xác nhận)

Thêm vào `trading/collector/parser.py` (giữ nguyên `parse_message`/`_parse_b`/`_parse_mi`/`ci_get` cũ — vẫn cần cho fixture cũ nếu còn dùng, kiểm tra `tests/test_parser.py` trước khi quyết định xoá gì):

```python
def parse_interval_message(msg) -> Bar | None:
    """Map IntervalMessage (ssi-sdk) -> Bar.

    !!! CHƯA XÁC NHẬN BẰNG DỮ LIỆU THẬT: format chuỗi interval_time/
    trading_time. Giả định cùng format REST OHLC đã xác nhận
    ("YYYY/MM/DD HH:mm:ss") — suy đoán hợp lý (cùng SDK, cùng field
    naming convention) nhưng KHÔNG chắc chắn. Nếu parse lỗi, trả None
    (không crash) — sẽ xác nhận/sửa ở Phase 4 khi có phiên giao dịch thật.
    """
    try:
        ts = datetime.strptime(msg.interval_time, "%Y/%m/%d %H:%M:%S").replace(tzinfo=TZ)
        return Bar(
            msg.symbol, ts,
            float(msg.open), float(msg.high), float(msg.low), float(msg.close),
            int(msg.volume),
        )
    except (TypeError, ValueError, AttributeError):
        return None
```

Cần thêm `from trading.models import Bar` vào import đầu file (`parser.py` hiện chỉ import `IndexValue, Tick`).

**Kiểm chứng Task 3:** test mới trong `tests/test_parser.py`, dựng `IntervalMessage` thủ công (import `from ssi_sdk.models import IntervalMessage`, biết chính xác field name từ source code — KHÔNG phải fixture thật vì chưa có):
```python
def test_parse_interval_message_maps_fields():
    from ssi_sdk.models import IntervalMessage
    msg = IntervalMessage(
        symbol="VCB", interval_time="2026/07/24 14:45:00", trading_time="2026/07/24 14:45:03",
        open=54100, high=54100, low=54100, close=54100, volume=189100,
    )
    bar = parse_interval_message(msg)
    assert bar is not None
    assert bar.symbol == "VCB" and bar.open == 54100 and bar.volume == 189100
    assert bar.ts == datetime(2026, 7, 24, 14, 45, tzinfo=TZ)


def test_parse_interval_message_bad_format_returns_none():
    from ssi_sdk.models import IntervalMessage
    msg = IntervalMessage(symbol="VCB", interval_time="not-a-date", open=1, high=1, low=1, close=1, volume=1)
    assert parse_interval_message(msg) is None
```
Ghi rõ trong docstring test (đã có ở trên) — đây là test dựa trên **giả định format**, không phải fixture thật, để không ai nhầm là đã verify.

---

## Task 4 — Wire vào `main.py`

**Import (dòng 9-12):**
```python
from trading.collector.feed import SSIFeed  # (SSIFeedLegacy nếu cần tham khảo)
from trading.collector.parser import parse_interval_message  # thêm, giữ parse_message cũ nếu còn dùng cho MI
```

**Khởi tạo feed (thay dòng 37-40 hiện tại — bỏ `BarAggregator`/`queue.Queue`, dùng callback trực tiếp):**
```python
async def persist(bars):
    if bars:
        storage.write_bars(bars)
        for b in bars:
            await pub.publish(b)
        alert("INFO", "bars closed", n=len(bars), symbols=[b.symbol for b in bars])

def on_stream_message(msg):
    bar = parse_interval_message(msg)
    if bar is not None:
        wd.beat()
        asyncio.create_task(persist([bar]))
    # TODO: nếu msg là TradeMessage cho index (xem Bối cảnh #4), xử lý riêng.

feed = SSIFeed(cfg, storage, on_message=on_stream_message)
feed.start()
```
**Lưu ý:** `wd` (Watchdog) phải được tạo TRƯỚC dòng này (đổi thứ tự nếu cần — hiện tại `wd` tạo sau `feed.start()` trong code cũ, dòng 42-49).

**Sửa watchdog wiring (dòng 42-49 hiện tại) — fix alert-theatre (finding #2):**
```python
wd = Watchdog(
    cfg.watchdog_stale_seconds, cfg.watchdog_max_failures,
    now_fn=lambda: datetime.now(TZ),
    is_trading_fn=lambda ts: is_trading_time(ts, cfg.holidays),
    on_stale=lambda: (alert("WARN", "feed stale, forcing reconnect"), asyncio.create_task(feed.restart())),
    on_critical=lambda: alert("CRITICAL", "feed stale beyond max failures"),
)
```
(`on_stale` là callable đồng bộ, không thể `await` trực tiếp — dùng `asyncio.create_task()` để chạy `feed.restart()` mà không block `Watchdog.check()`. Tuple `(alert(...), asyncio.create_task(...))` chỉ để chạy 2 side-effect trong 1 lambda — nếu thấy khó đọc, viết thành hàm riêng `def _on_stale(): ...` thay vì lambda, tự quyết theo style rõ ràng nhất.)

**Xoá/không dùng nữa:** `agg = BarAggregator(...)`, `raw_q: queue.Queue = ...`, hàm `consume()` cũ (logic tick→bar qua `agg.add_tick`), và các import liên quan (`queue`, `BarAggregator`, `parse_message` nếu không còn ai gọi — kiểm tra kỹ trước khi xoá import, `parse_message` có thể vẫn cần nếu giữ xử lý MI/index).

**`housekeeping()`:** đoạn `if end is not None ... await persist(agg.flush())` (đóng bar cuối phiên) — **không còn ý nghĩa** nếu bỏ `BarAggregator` (SSI tự đóng bar, không phải mình). Xoá đoạn này, giữ lại phần EOD backfill (đã xong Phase 2, không đụng) và `wd.check()`/`storage.beat()`.

**Kiểm chứng Task 4:** `uv run --with ssi-sdk python -c "import ast; ast.parse(open('trading/collector/main.py', encoding='utf-8').read()); print('OK')"`.

---

## Task 5 — Live smoke test NGOÀI GIỜ GIAO DỊCH (không cần chờ phiên mở)

Sau khi Task 1-4 xong, **user tự chạy** (cần `SSI_API_KEY`/`SSI_API_SECRET` thật, giống Phase 0 — agent thực thi KHÔNG chạy được vì không có quyền đọc `.env`):

```powershell
uv run --with ssi-sdk python -m trading.collector.main --config config/config.yaml
```

Theo dõi log ~30-60 giây (đợi qua terminal, không cần thị trường mở):
- Kết nối WebSocket thành công (log tương tự Phase 0: "WebSocket connected to wss://stream.ssi.com.vn/ws/v3")
- Không có traceback/crash
- (Optional, để test `restart()`) Ctrl+C sau khi thấy connected, xác nhận `stop()`/cleanup không treo.

**Mục đích:** xác nhận toàn bộ plumbing (auth lazy, connect, subscribe, watchdog wiring) hoạt động — **KHÔNG** xác nhận được nội dung `IntervalMessage` thật (vì market đóng, `on_data` sẽ không được gọi lần nào). Đây chính là ranh giới "test được ngoài giờ" vs "phải chờ Phase 4".

---

## Sau khi hoàn thành

1. `uv run pytest -m "not integration" -v` — tất cả test cũ (≥55) vẫn pass, cộng test mới Task 2-3.
2. `gitnexus_detect_changes()` — dán kết quả.
3. Báo cáo: quyết định đã đưa ra cho mục "Index streaming" (Bối cảnh #4) — làm hay bỏ qua tạm, lý do. File sửa/tạo, test output.
4. **Không commit, không push.**
