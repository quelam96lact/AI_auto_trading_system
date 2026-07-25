# Plan: Migrate sang SSI SDK mới (`ssi-sdk` v3.1.0)

**Ngày viết:** 2026-07-21 (cập nhật sau khi đọc source code thật)
**Nguồn:** `pip install ssi-sdk` (đã cài thử, version 3.1.0) + source code đọc trực tiếp từ GitHub `SSI-Securities-Inc/ssi-sdk-python`
**Quyết định của user:** Không có deadline sunset cụ thể từ SSI, nhưng muốn **nâng cấp toàn bộ** lên version mới.
**Trạng thái:** ✅ **Đủ thông tin để bắt đầu Phase 0** — nút thắt OTP đã được giải quyết bằng cách đọc source code thật (không cần đoán qua docs nữa).

---

## 1. Thay đổi lớn nhất so với bản plan trước

Bản plan đầu tiên (viết chỉ dựa vào trang docs) có 1 điểm nghẽn: **"OTP có bắt buộc cho streaming không, và bắt buộc mỗi lần hay chỉ 1 lần?"** — docs online mâu thuẫn nhau nên không dám giả định.

Tôi đã cài `ssi-sdk` vào venv tạm và đọc thẳng source code (`token_manager.py`, `client.py`, `services/streaming.py`) để trả lời dứt điểm:

### ✅ Đã xác nhận: OTP chỉ cần **1 lần**, sau đó auto-refresh không cần OTP

```python
# token_manager.py — logic thật của ensure_authenticated()
if self._token is None or self.is_token_expired:
    if self.has_refresh_token:
        self.refresh()          # ← không cần OTP, chỉ cần refresh_token còn hạn
    elif otp:
        self.authenticate(otp)  # ← chỉ cần khi CHƯA có refresh_token (lần đầu)
    else:
        raise AuthenticationError("OTP is required...")
```

Cơ chế: `authenticate(otp=...)` lần đầu trả về `Token` gồm `access_token` + `refresh_token` + `refresh_token_expires_at`. Sau đó `refresh()` dùng `refresh_token` để lấy `access_token` mới **mà không cần OTP**, miễn `refresh_token` chưa hết hạn.

**Điều này thay đổi hoàn toàn thiết kế:** không phải "nhập OTP mỗi lần reconnect" như tôi lo ban đầu, mà là mô hình OAuth2 chuẩn — 1 lần bootstrap, sau đó service tự refresh.

### ⚠️ Vẫn còn 1 điều thật sự chưa biết (chỉ test thật mới biết)
- `refresh_token_expires_at` sống được bao lâu (giờ? ngày? tuần?) — quyết định việc collector có thể chạy **nhiều ngày liên tiếp không cần người can thiệp**, hay cần nhập OTP lại mỗi sáng.
- → Đây là mục tiêu chính của Phase 0 thực nghiệm (mục 4), không còn là câu hỏi kiến trúc mơ hồ nữa mà là **1 con số cần đo**.

---

## 1.1. Phase 0 đã chạy thật (2026-07-25) — kết quả thay đổi thiết kế lần nữa

Đã chạy thật với credentials thật (`SSI_API_KEY`/`SSI_API_SECRET` từ console), qua `scripts/spike_ssi_sdk_auth.py`:

### 🎯 Phát hiện lớn nhất: OTP KHÔNG bắt buộc trên account này

`auth.authenticate()` gọi **KHÔNG kèm `otp`** (chỉ `apiKey`+`apiSecret`) trả về `200 OK` với JWT có:
```json
"scopes": "trading:*:*,data:*:*,stream:*:*"
```
— tức là full scope (kể cả Trading + Stream), **không cần OTP ở bước lấy token**. Xác nhận thêm bằng cách connect WebSocket + subscribe `trade.VCB@5m` bằng token này: `wss://stream.ssi.com.vn/ws/v3` connect OK, subscribe trả `{"status": "ok"}` — không có lỗi permission/OTP nào.

Điều này khác với bảng trong `client.py` docstring (nói Trading/Stream cần `authenticate(otp=...)`). Có thể do: (a) cấu hình riêng cho account này, hoặc (b) OTP thật sự chỉ là gate ở tầng đặt lệnh (ký RSA qua `private_key`, xem mục 2.1.1), không phải ở tầng cấp token. **Chưa rõ đây có phải hành vi ổn định lâu dài hay không** — dự án vẫn nên giữ nguyên thiết kế `ensure_authenticated()` (Phase 1, đã code) có fallback yêu cầu người vận hành can thiệp nếu sau này OTP trở thành bắt buộc.

### 📏 TTL đo được (qua đường không-OTP)
| Token | TTL |
|---|---|
| `access_token` | 900s = **15 phút** |
| `refresh_token` | 28800s = **8 giờ** |

8 giờ đủ cho 1 phiên giao dịch (~6 giờ, 09:00-14:45) nhưng **không đủ chạy nhiều ngày liên tiếp không can thiệp** như kỳ vọng ban đầu. Tuy nhiên, vì `authenticate()` không cần OTP vẫn dùng được lặp lại (không phải one-time), **collector có thể tự gọi lại `authenticate()` (không OTP) mỗi khi cần** thay vì phụ thuộc hoàn toàn vào `refresh_token` — đơn giản hoá đáng kể so với thiết kế Phase 1 ban đầu (bảng `ssi_auth_state` vẫn có giá trị để giảm số lần gọi API, nhưng không còn là **bắt buộc** để tránh OTP nữa).

**Khuyến nghị:** Giữ nguyên code Phase 1 đã commit (không rollback) — thiết kế "ưu tiên `refresh_token`, yêu cầu OTP thủ công khi hết hạn" vẫn an toàn và đúng dù OTP có thật sự cần hay không. Cân nhắc thêm 1 fallback nhẹ trong Phase 3 (khi wire `ensure_authenticated()` vào `main.py`): nếu `refresh_token` hết hạn, thử `authenticate()` không OTP trước khi raise lỗi yêu cầu người vận hành — chỉ raise khi cả 2 đường đều thất bại. Đây là quyết định để lúc code Phase 3, không sửa ngay bây giờ.

---

## 2. Chi tiết kỹ thuật xác nhận từ source code (không còn là giả định)

### 2.1. Credentials & endpoints
| | |
|---|---|
| Base REST URL | `https://api.ssi.com.vn` |
| Base Stream URL | `wss://stream.ssi.com.vn/ws/v3` |
| Endpoint lấy token | `POST /api/v3/auth/token` (body: `apiKey`, `apiSecret`, `otp?`) |
| Endpoint refresh | `POST /api/v3/auth/refresh` (body: `refreshToken`) |
| Endpoint xin OTP | `POST /api/v3/auth/requestOtp` |
| Endpoint OHLC | `GET /api/v3/data/ohlc` |

**`private_key` dùng để làm gì:** SDK dùng nó ký request bằng **RSA PKCS#1 v1.5 SHA-256** (`utils/crypto.py::sign()`), gửi qua header `X-Signature`. Key là chuỗi base64-encode 1 XML RSA key (định dạng kiểu .NET `<RSAKeyValue>`).

### 2.1.1. ⚠️ Sửa lại: `client_id`/`private_key` KHÔNG cần cho scope dự án hiện tại

Grep toàn bộ `ssi_sdk/services/*.py` cho thấy:
- `private_key`/`sign()` **chỉ được dùng trong `services/trading.py`** (đặt lệnh, cần chữ ký RSA).
- `client_id` **chỉ được dùng trong `services/portfolio.py`** (tra số dư/vị thế tài khoản).
- `services/market_data.py` và `services/streaming.py` — 2 module dự án này cần (OHLC + bar streaming) — **không tham chiếu `client_id` hay `private_key` ở đâu cả**.

→ Vì broker hiện tại là **PaperBroker** (giả lập nội bộ, không đặt lệnh thật qua SSI Trading API), dự án **chỉ cần `api_key` + `api_secret`** (+ OTP một lần để lấy `refresh_token`). `client_id`/`private_key` chỉ cần khi nào chuyển sang đặt lệnh thật qua SSI — ngoài scope hiện tại, hoãn lại tới khi có nhu cầu đó.

### 2.2. Mapping REST OHLC (cho `backfill.py`)

| Cũ (`ssi_fc_data`) | Mới (`ssi-sdk`) |
|---|---|
| `client.intraday_ohlc(None, model.intraday_ohlc(symbol=, fromDate="dd/MM/yyyy", toDate=, pageIndex=, pageSize=, ascending=, resolution=1))` | `await data.market_data.get_ohlc_5minute_historical(symbol, from_date="YYYY/MM/DD HH:mm:ss", to_date="YYYY/MM/DD HH:mm:ss", page=1, size=1000)` ⚠️ **intraday PHẢI có giờ** — thiếu giờ → lỗi `400213 "Invalid Date/Timestamp"` (đã gặp thật 2026-07-25, xác nhận qua docs `data-ohlc`: daily dùng `YYYY/MM/DD`, intraday dùng `YYYY/MM/DD HH:mm:ss`) |
| `client.daily_ohlc(...)` | `await data.market_data.get_ohlc_1day_historical(symbol, from_date="YYYY/MM/DD", to_date="YYYY/MM/DD", page, size)` (daily KHÔNG cần giờ; tên method suy ra theo pattern, cần xác nhận khi code) |
| Response: `dict {data: [...]}`, field PascalCase (`Symbol`, `TradingDate`, `Time`, `Open`...) | Response: `list[OHLCData]` — dataclass đã parse sẵn: `symbol`, `trading_date` **✅ xác nhận thật `"YYYY/MM/DD HH:mm:ss"`** (vd `"2026/07/24 14:45:00"`, xem `tests/fixtures/ssi_sdk_ohlc_5m_vcb.json`), `open_price`/`high_price`/`low_price`/`close_price`/`volume`/`value` đã là **số** (SDK tự convert từ string trong raw JSON qua `to_number()`/`to_int()`, không cần tự ép kiểu) |
| Ta tự bucket 1m → 5m (`parse_intraday_response`) | SDK trả **thẳng bar 5m** nếu gọi `get_ohlc_5minute_historical` — **có thể bỏ hẳn logic tự bucket trong `backfill.py`** (giảm code, không phải giữ nguyên bucket logic cũ) |
| Page mặc định: `pageSize=100` (ta tự set) | Page mặc định SDK: `size=1000` (constant `DEFAULT_SIZE`) |
| Không rate limit rõ ràng, ta tự `time.sleep(0.25)` | SDK có `rate_limit_per_second` tích hợp trong `Config` — **có thể bỏ throttle thủ công**, dùng config SDK |

**✅ Đã verify bằng response thật (2026-07-25):** `trading_date` luôn có giờ `"YYYY/MM/DD HH:mm:ss"` cho intraday (kể cả khi request `to_date` là cuối ngày `23:59:59` — server trả đúng timestamp của từng bar, không phải giờ request). Dữ liệu 230 bar thật của VCB khớp đúng ranh giới phiên VN (nghỉ trưa 11:25→13:00, có ATC 14:45) — `_row_ts()` trong `backfill.py` viết lại chỉ cần `strptime(s, "%Y/%m/%d %H:%M:%S")`, đơn giản hơn hẳn bản cũ (không cần ghép `TradingDate`+`Time` riêng như SDK cũ).

### 2.3. Mapping Streaming (cho `feed.py` + `parser.py`)

| Cũ | Mới |
|---|---|
| 1 channel gộp `"B:SYM1-SYM2"`, message có `DataType: "B"/"MI"` + `Content` (JSON string cần tự `json.loads`) | Subscribe tách riêng: `subscribe_symbol_ohlcv(symbols, Timeframe.MINUTE_5)` cho bar, `subscribe_symbol_trade(symbols)` cho tick. Message đã là **dataclass đã parse sẵn**, không cần tự parse JSON string nữa |
| Field bar tự parse từ JSON string, PascalCase | `IntervalMessage`: `symbol`, `open`, `high`, `low`, `close`, `volume`, `interval_time` (raw key `st`), `trading_time` (raw key `t`) — **field đã là số** (`to_number`/`to_int`), không cần tự ép kiểu |
| `MarketDataStream.start(on_msg, on_err, channel)` chạy trong thread riêng, ta tự quản lý reconnect + backoff | `stream.streaming.on_data = callback` (property setter) + `await stream.streaming.connect()` — **native async**, có thể bỏ hẳn `threading.Thread` wrapper hiện tại trong `SSIFeed`, tích hợp thẳng vào `asyncio` loop đã có sẵn ở `main.py` |
| Reconnect tự viết (`_run()` với backoff thủ công trong `feed.py`) | SDK **không thấy có auto-reconnect built-in** trong `AsyncWebSocketClient` (cần đọc thêm `websocket_client.py` ở Phase 0 để xác nhận) — **có thể vẫn cần giữ lại logic backoff/reconnect tự viết**, chỉ thay lớp gọi SDK bên dưới |

**Hệ quả kiến trúc quan trọng:** Vì `IntervalMessage` đã là bar 5 phút sẵn từ SSI (không phải tick thô), **có thể cân nhắc bỏ `BarAggregator` tự viết** (`trading/collector/aggregator.py`) nếu SDK đóng bar đúng ranh giới giờ VN mong muốn. Đây là quyết định cần dữ liệu thật để verify ở Phase 0 — **không tự ý xoá `aggregator.py` khi chưa xác nhận**, giữ làm phương án dự phòng nếu SDK đóng bar sai giờ/lệch múi giờ.

---

## 3. Phạm vi ảnh hưởng (cập nhật, cụ thể hơn bản trước)

### Files phải sửa
| File | Thay đổi |
|---|---|
| `pyproject.toml` | `ssi-fc-data` → `ssi-sdk` |
| `trading/config.py` | `Config`: bỏ `ssi_consumer_id/secret`, thêm `ssi_api_key`, `ssi_api_secret` (chỉ 2 giá trị — `client_id`/`private_key` hoãn tới khi cần Trading API thật, xem mục 2.1.1), thêm `ssi_refresh_token_path` hoặc tương tự để trỏ nơi lưu refresh_token bền vững (xem mục 5) |
| `trading/collector/backfill.py` | Viết lại `SSIRestClient`: dùng `AsyncData.market_data.get_ohlc_5minute_historical`/`get_ohlc_1day_historical`. Có thể **xoá** `parse_intraday_response`'s bucket-5m logic (SDK trả sẵn). Giữ `parse_daily_response` nhưng đổi field mapping theo `OHLCData` |
| `trading/collector/feed.py` | Viết lại `SSIFeed`: dùng `AsyncStream`, `subscribe_symbol_ohlcv`. Cân nhắc bỏ thread wrapper (đổi sang native async task), nhưng **giữ lại cơ chế reconnect+backoff** hiện có (SDK có vẻ không tự làm) |
| `trading/collector/parser.py` | Viết lại `parse_message()`: input giờ là `IntervalMessage`/`TradeMessage` (dataclass), không phải dict envelope `{DataType, Content}` nữa — logic đơn giản hơn hẳn |
| `trading/collector/main.py` | Điều chỉnh `run()`: auth bootstrap (đọc refresh_token đã lưu hoặc yêu cầu OTP), sau đó tạo `AsyncData`/`AsyncStream` |
| `trading/collector/aggregator.py` | **KHÔNG xoá vội** — giữ làm fallback, chỉ quyết định bỏ sau khi Phase 0 xác nhận SDK tự đóng bar đúng giờ VN |
| `docker-compose.yml`, `.env` | Đổi biến môi trường: `SSI_CONSUMER_ID/SECRET` → `SSI_CLIENT_ID`, `SSI_API_KEY`, `SSI_API_SECRET`, `SSI_PRIVATE_KEY` (nội dung dài, base64 — cân nhắc file riêng thay vì env var 1 dòng) |
| `tests/test_feed.py`, `test_backfill.py`, `test_parser.py` | Viết lại mock theo SDK mới |
| `tests/fixtures/` | Giữ nguyên fixtures cũ (archive), ghi fixtures mới riêng biệt |

### Files KHÔNG đụng
- `trading/engine/*`, `trading/broker/*`, `trading/storage/*`, `trading/models.py`, `trading/alerts/*`, `grafana/*` — không đổi, vì SDK migration chỉ ảnh hưởng lớp adapter thu thập dữ liệu.

### Thứ mới cần quản lý: refresh_token persistence
SDK mới đưa ra khái niệm `refresh_token` cần **lưu bền vững qua lần restart container** (khác hẳn SDK cũ không có khái niệm này). Cần quyết định nơi lưu:
- Option A: File trên volume Docker (`./secrets/ssi_refresh_token.json`, gitignore).
- Option B: Bảng riêng trong PostgreSQL đã có sẵn (`collector_auth_state`).
- Đề xuất: **Option B** — nhất quán với cách `Storage` đang quản lý state khác (`storage.beat()`, watchdog), không thêm cơ chế file riêng.

---

## 4. Phase 0 — Discovery spike (cụ thể hoá, thu hẹp phạm vi so với bản trước)

Vì phần lớn API/kiến trúc đã rõ từ source code, Phase 0 giờ chỉ còn 3 việc thực nghiệm thật (cần credentials thật):

1. **Tạo API Key trên console SSI** (`developers.ssi.com.vn` → Bảng điều khiển → Quản lý API Key → Tạo Key mới) → lấy `api_key`, `api_secret`. Không cần `client_id`/`private_key` (xem mục 2.1.1).
   - Kiểm chứng: có đủ 2 giá trị, lưu vào `.env` (`SSI_API_KEY`, `SSI_API_SECRET`). Lưu ý `API Secret` chỉ hiển thị 1 lần lúc tạo.
2. **Script spike xác nhận đường auth + TTL refresh_token** (`scripts/spike_ssi_sdk_auth.py`, tạm, không commit vào `trading/`):
   ```python
   async with AsyncAuth(api_key=..., api_secret=...) as auth:
       otp = await auth.request_otp()   # xin OTP qua SMS/email
       token = await auth.authenticate(otp=input("Nhập OTP: "))
       print("refresh_token_expires_at:", token.refresh_token_expires_at)
       # Lưu refresh_token, đợi vài giờ, thử lại:
       await auth.refresh()  # xác nhận KHÔNG cần OTP lần 2
   ```
   - Kiểm chứng: in ra `refresh_token_expires_at`, tính được TTL bằng giờ/ngày. Xác nhận `refresh()` chạy được không cần OTP.
3. **Script spike lấy sample OHLC + streaming thật** (`scripts/spike_ssi_sdk_ohlc.py`):
   - Gọi `get_ohlc_5minute_historical("VCB", ...)`, in raw `OHLCData` → xác nhận format `trading_date`.
   - Subscribe `subscribe_symbol_ohlcv(["VCB"], Timeframe.MINUTE_5)` trong phiên giao dịch thật, in `IntervalMessage` → xác nhận bar đóng đúng giờ VN (so với giờ hệ thống hiện tại), field `interval_time`/`trading_time` format gì.
   - Kiểm chứng: có sample thật lưu vào file để dùng viết test fixture cho Phase 2-3 (giống cách Task 6 cũ đã làm với SDK cũ).

**Checkpoint sau Phase 0:** báo cáo lại cho user 3 con số — TTL refresh_token, format `trading_date`, SDK có tự đóng bar đúng giờ VN không — trước khi viết code production ở Phase 1-3.

### ✅ Phase 0 HOÀN THÀNH (2026-07-25) — kết quả thực nghiệm

| Câu hỏi | Kết quả |
|---|---|
| `api_key`/`api_secret` hợp lệ? | ✅ Có (`authenticate()` không OTP trả 200) |
| OTP có bắt buộc? | ❌ Không — full scope `trading:*:*,data:*:*,stream:*:*` cấp ngay không cần OTP (xem mục 1.1) |
| TTL `access_token` | 15 phút |
| TTL `refresh_token` | 8 giờ |
| Format `trading_date` | `"YYYY/MM/DD HH:mm:ss"` — xác nhận (xem mục 2.2) |
| Stream connect + subscribe | ✅ Thành công (`wss://stream.ssi.com.vn/ws/v3`, subscribe `trade.VCB@5m` trả `{"status":"ok"}`) — chưa nhận được `IntervalMessage` thật (test ngoài giờ giao dịch, phiên đã đóng) |
| Fixture OHLC thật | ✅ `tests/fixtures/ssi_sdk_ohlc_5m_vcb.json` (230 bar VCB, 5 ngày) |
| Fixture Stream thật (`IntervalMessage`) | ⚠️ **Còn thiếu** — cần chạy lại `scripts/spike_ssi_sdk_ohlc.py --stream-only` **trong giờ giao dịch** (09:00-14:45 VN) để bắt được bar thật, dùng ghi fixture cho Phase 3 |

**Sẵn sàng bắt đầu Phase 2** (viết lại `backfill.py`) ngay — đã có đủ fixture OHLC thật.
**Phase 3** (viết lại `feed.py`/`parser.py`) nên chờ thêm 1 lần chạy trong giờ giao dịch để có sample `IntervalMessage` thật, tránh đoán field như `interval_time`/`trading_time` format (đã biết tên field từ source code nhưng chưa có giá trị thật để đối chiếu).

---

## 5. Kế hoạch theo Phase (giữ cấu trúc bản trước, cập nhật nội dung)

### Phase 1 — Config & auth bootstrap
1. Sửa `trading/config.py` theo bộ credentials mới.
2. Thêm bảng `collector_auth_state` (hoặc tương đương) trong `trading/storage/db.py` để lưu `refresh_token` + `refresh_token_expires_at`.
3. Viết logic bootstrap trong `main.py`: đọc token đã lưu → nếu còn hạn, `refresh()`; nếu hết hạn/chưa có, yêu cầu OTP (đọc từ biến môi trường 1 lần hoặc input thủ công lúc deploy — **không thiết kế OTP tự động hoá qua SMS**, vì đó là quyết định vượt phạm vi code).
4. Kiểm chứng: `uv run pytest tests/test_config.py -v` pass; script thủ công xác nhận bootstrap hoạt động với credentials thật.

### Phase 2 — Migrate REST backfill — ✅ HOÀN THÀNH (2026-07-25)
1. ✅ Viết lại `SSIRestClient` dùng `get_ohlc_5minute_historical`/`get_ohlc_1day_historical` (tên xác nhận thật qua `inspect.signature`, không đoán). Auth lazy qua `ensure_authenticated()` (Phase 1).
2. ✅ Không sửa `parse_daily_response`/`parse_intraday_response` cũ (giữ nguyên cho `SSIRestClientLegacy` — đã đổi tên từ `SSIRestClient`, rollback reference theo mục 7) — viết hàm mới `_ohlc_rows_to_bars()`/`_parse_trading_date()` riêng cho SDK mới, không tái dùng bucket logic cũ (không cần nữa, SDK trả sẵn bar 5m).
3. ✅ Pagination: response mới không expose `totalRecord` — dùng heuristic `len(rows) < size` để dừng.
4. ✅ Kiểm chứng: `uv run pytest tests/test_backfill.py -v` — 3/3 pass (2 test cũ + 1 test mới dùng fixture thật `ssi_sdk_ohlc_5m_vcb.json`, 230 bar). Full suite 55/55 pass.
5. ✅ `main.py` 2 call site cập nhật `async`/`await` + `client.close()`.
6. ✅ `gitnexus detect-changes`: 3 files, 20 symbols, 8 processes, risk HIGH — audit xác nhận HIGH do fan-out (1 hàm chạm 8 execution flow `Main`/`Housekeeping`), không phải rủi ro thật (không flow nào chạm trading/tiền, broker vẫn `PaperBroker`). Tất cả 8 flow đều nằm trong phạm vi đã giao (`main.py` 2 chỗ + `backfill.py::main`).

### Phase 3 — Migrate streaming feed + parser
1. Viết lại `SSIFeed` dùng `AsyncStream`/`subscribe_symbol_ohlcv`, giữ lại backoff/reconnect logic hiện có (đổi lớp gọi bên dưới).
2. Viết lại `parse_message()` nhận `IntervalMessage`.
3. Quyết định giữ/bỏ `BarAggregator` dựa trên kết quả Phase 0.
4. TDD: viết test trước bằng fixture thật ghi ở Phase 0, `uv run pytest tests/test_feed.py tests/test_parser.py -v` pass.

### Phase 4 — E2E lại (tái dùng runbook Task 3)
1. Chạy lại `EXECUTE_TASK_3_TODAY.md`/`PLAN_TASK_3.md` với SDK mới.
2. Theo dõi thêm: token có tự refresh giữa phiên không cần can thiệp (đặc biệt nếu access_token TTL ngắn, vd 1 giờ).
3. Kiểm chứng: cùng success criteria cũ (0 parser error, bar liên tục, latency <2s).

### Phase 5 — Dọn dẹp
1. Gỡ `ssi-fc-data` khỏi `pyproject.toml` sau khi Phase 4 ổn định ≥2 phiên liên tiếp.
2. Archive fixtures cũ vào `tests/fixtures/legacy_ssi_fc_data/`.
3. Xoá scripts spike ở Phase 0 (hoặc giữ lại trong `scripts/` nếu hữu ích cho vận hành sau này — quyết định lúc dọn dẹp).

---

## 6. Ước lượng effort (điều chỉnh giảm nhờ đã đọc source)

| Phase | Effort | Thay đổi so với bản trước |
|---|---|---|
| Phase 0 | 2-3 giờ (không tính thời gian chờ SSI duyệt đăng ký console) | Giảm — phần lớn câu hỏi kiến trúc đã trả lời qua source code, chỉ còn đo TTL + lấy sample |
| Phase 1 | 1-1.5 giờ | Tăng nhẹ — cần thêm bảng lưu refresh_token (không có trong bản trước) |
| Phase 2 | 2 giờ | Giảm — biết chính xác method/field cần map |
| Phase 3 | 4-5 giờ | Giữ nguyên — vẫn là phần phức tạp nhất (đổi kiến trúc callback, quyết định bỏ aggregator) |
| Phase 4 | 1 phiên giao dịch (~6 giờ theo dõi) | Giữ nguyên |
| Phase 5 | 0.5 giờ | Giữ nguyên |
| **Tổng** | **~10-12 giờ code + 1 phiên E2E** | Giảm ~2 giờ so với ước lượng ban đầu |

---

## 7. Rủi ro còn lại & rollback

- **Rủi ro còn lại thật sự (không giải quyết được bằng đọc code, cần test thật):** TTL của `refresh_token`. Nếu ngắn (vài giờ) → vẫn cần người nhập OTP mỗi ngày, chấp nhận được (nhập lúc 08:55 như quy trình Task 3 hiện tại). Nếu SSI thiết kế TTL rất ngắn (vài phút, bất thường) → cần escalate lên SSI support, nhưng đây là kịch bản khó xảy ra với kiến trúc OAuth2 refresh_token chuẩn.
- **Rủi ro nhỏ:** `X-Signature` RSA signing có thể chậm hơn Bearer token đơn giản cũ (mỗi request phải ký) — không đáng kể ở tần suất gọi hiện tại (throttle 0.25s/call cũ, giờ có thể bỏ nhờ SDK tự rate-limit).
- **Rollback:** Giữ song song code cũ (`feed.py`/`backfill.py` hiện tại backup sang tên khác) tới khi Phase 4 ổn định ≥2 phiên. Không gỡ `ssi-fc-data` khỏi dependencies cho tới lúc đó.

---

## 8. Việc cần làm ngay (theo yêu cầu "muốn nâng cấp toàn bộ")

1. **Bạn tạo API Key trên console SSI** (`developers.ssi.com.vn` → Bảng điều khiển → Quản lý API Key → Tạo Key mới) để lấy `api_key` + `api_secret`. **Không cần `client_id`/`private_key`** — 2 giá trị đó chỉ dùng cho Trading/Portfolio API thật, ngoài scope hiện tại (dự án dùng PaperBroker). Đây là bước duy nhất **chỉ bạn làm được** (gắn với tài khoản SSI của bạn) — tôi không có quyền tự tạo thay.
2. Thêm vào `.env`: `SSI_API_KEY=...`, `SSI_API_SECRET=...` (giữ song song `SSI_CONSUMER_ID/SECRET` cũ tới khi migration xong).
3. Báo tôi khi xong → tôi chạy Phase 0 script để đo TTL refresh_token + lấy sample dữ liệu thật.
4. Sau Phase 0, tôi báo cáo lại kết quả cụ thể rồi triển khai Phase 1-5 theo plan trên.
