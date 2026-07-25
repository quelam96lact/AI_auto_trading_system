# Plan: Migrate sang SSI SDK mới (`ssi-sdk`)

**Ngày viết:** 2026-07-21
**Nguồn:** https://developers.ssi.com.vn/docs/sdk/overview (+ /docs/sdk/python/overview, GitHub `SSI-Securities-Inc/ssi-sdk-python`)
**Trạng thái:** ⚠️ **CHƯA THỂ THỰC THI NGAY** — có 1 rủi ro kiến trúc chưa xác minh (xem mục "Câu hỏi cần làm rõ")

---

## 1. Vì sao cần migrate

SSI đã phát hành SDK chính thức mới (`ssi-sdk`, Python/Go/Node.js), thay thế package `ssi_fc_data` mà repo đang dùng. Tài liệu không nêu ngày sunset của package cũ, nhưng thay đổi API là toàn diện (auth, client, response format) — coi đây là **rewrite**, không phải patch nhỏ.

**Giả định cần user xác nhận:**
- Không rõ `ssi-fc-data` (package cũ, PyPI) có bị gỡ/deprecated theo lịch cụ thể không. Nếu không có deadline, có thể migrate theo nhịp độ thong thả, ưu tiên sau khi Task 3 (E2E live trading) hoàn tất.
- Nếu bạn có thông báo/email từ SSI về deadline sunset, cho biết ngày cụ thể để điều chỉnh độ ưu tiên.

---

## 2. So sánh SDK cũ vs mới

| Khía cạnh | Cũ (`ssi_fc_data`, đang dùng) | Mới (`ssi-sdk`) |
|---|---|---|
| Package | `pip install ssi-fc-data` | `pip install ssi-sdk` (Python ≥3.10) |
| Auth credentials | `consumerID` + `consumerSecret` | `client_id` + `api_key` + `api_secret` + `private_key` (**đăng ký lại trên console SSI**) |
| Auth flow | Không cần OTP, config trực tiếp vào `MarketDataClient` | `Config` → `Auth.authenticate(otp=...)` tách biệt; OTP theo tài liệu **không bắt buộc cho market data**, nhưng bảng client liệt kê **Stream = "OTP required"** — mâu thuẫn cần xác minh |
| Kiến trúc | Sync, thread tự quản (SSIFeed dùng `threading.Thread` bọc SDK sync) | Async-first (`AsyncAuth`, `AsyncData`, `AsyncStream`), có bản sync đi kèm |
| REST OHLC | `client.intraday_ohlc(None, model.intraday_ohlc(symbol=, fromDate=, toDate=, pageIndex=, pageSize=, ascending=, resolution=1))` → dict `{data: [...]}`, field PascalCase (`Symbol`, `TradingDate`, `Time`, `Open`...) | `data.market_data.get_ohlc_5minute_historical(symbol, from_date, to_date, page, size)` — tên method đổi hẳn, format response **chưa xác minh** (có thể trả object thay vì dict PascalCase) |
| Streaming subscribe | 1 channel gộp `"B:SYM1-SYM2"` (bar) qua `MarketDataStream.start(on_msg, on_err, channel)`, message envelope `{DataType: "B"/"MI", Content: "<json string>"}` | Tách riêng theo loại: `subscribe_symbol_trade()`, `subscribe_symbol_quote()`, `subscribe_symbol_ohlcv(symbols, interval)` — **có thể thay thế luôn `BarAggregator` tự viết** vì SDK tự trả bar theo interval |
| Message format streaming | Raw dict, cần `parser.py` tự parse JSON string trong `Content` | Typed objects (`TradeMessage`, `QuoteMessage`, `IntervalMessage`) — field name **chưa xác minh đầy đủ** |
| Base URL | Khai báo thủ công `fc-data.ssi.com.vn` / `fc-datahub.ssi.com.vn` trong `_SdkCfg` | Không thấy tài liệu về việc tự khai URL — có thể SDK tự quản lý qua `Config` |

---

## 3. ⚠️ Câu hỏi cần làm rõ trước khi code (Phase 0 bắt buộc)

Đây là điểm dừng theo nguyên tắc lập kế hoạch trong CLAUDE.md — **không được giả định liều rồi giao thẳng cho agent thực thi**.

### 3.1. Rủi ro kiến trúc lớn nhất: OTP cho streaming

Tài liệu SSI mâu thuẫn nội bộ:
- Overview nói: *"OTP không bắt buộc cho dữ liệu thị trường"*
- Bảng client lại liệt kê: **Stream → OTP required**

Nếu OTP thực sự bắt buộc **mỗi lần** kết nối/reconnect streaming, thiết kế hiện tại (`SSIFeed._run()` tự động reconnect với backoff, chạy không người trông trong suốt phiên 09:00-14:45) **sẽ gãy hoàn toàn** — vì OTP cần người nhập (SMS/email), không thể tự động hoá đơn giản.

**Cần xác minh bằng thực nghiệm (không phải đọc tài liệu thêm), vì tài liệu online không trả lời được:**
1. Đăng ký thử credentials mới trên console SSI (client_id/api_key/api_secret/private_key).
2. Viết 1 script nhỏ, **ngoài phạm vi codebase chính** (`scripts/spike_ssi_sdk_auth.py`, không commit vào `trading/`), thử:
   - `AsyncAuth.authenticate()` **không** truyền `otp` → xem có kết nối được `AsyncStream` + `subscribe_symbol_ohlcv` không.
   - Nếu bị từ chối → thử `authenticate(otp=...)` một lần, đo xem token/session sống được bao lâu trước khi cần OTP lại (mục tiêu: phải sống được ≥ 6 giờ để phủ hết 1 phiên giao dịch).
3. Ghi lại kết quả cụ thể: có cần OTP không, token TTL bao lâu, có auto-refresh không cần OTP không.

**Tiêu chí để Phase 0 coi là "qua":**
- [ ] Xác nhận streaming market-data (`subscribe_symbol_ohlcv`/`subscribe_symbol_trade`) chạy được liên tục ≥ 6 giờ **không cần nhập OTP giữa chừng**, HOẶC
- [ ] Xác nhận cần OTP 1 lần/ngày lúc đầu phiên (chấp nhận được — có thể nhập tay lúc 08:55) và token sống hết phiên.

**Nếu cả 2 điều trên đều KHÔNG đúng** (ví dụ cần OTP lặp lại nhiều lần trong phiên) → dừng migration streaming, quay lại hỏi ý kiến bạn về hướng thay thế:
- Option A: Giữ `ssi_fc_data` (SDK cũ) riêng cho streaming, chỉ migrate phần REST OHLC (backfill) sang SDK mới.
- Option B: Liên hệ SSI support xin API key dạng service-account không cần OTP cho market data.
- Option C: Bỏ streaming, chuyển sang polling REST định kỳ (tăng latency, nhưng đơn giản).

### 3.2. Field name response chưa xác minh

Tài liệu không liệt kê field cụ thể của `IntervalMessage` (streaming bar) hay response của `get_ohlc_5minute_historical`. Không thể viết `parser.py`/`backfill.py` chính xác nếu chỉ đọc tài liệu — **phải bắt session thật rồi in ra raw object** (giống cách Task 6 cũ đã làm để lấy field PascalCase thật, xem comment "findings Task 6" rải khắp `backfill.py`/`parser.py`).

### 3.3. Việc cần làm ngay (không phụ thuộc câu trả lời trên)
- Đăng ký app mới trên SSI console để lấy `client_id/api_key/api_secret/private_key` (cần làm dù đi hướng nào).
- Xác nhận `ssi-fc-data` (cũ) còn cài được từ PyPI hay không (fallback an toàn nếu Phase 0 phát hiện vấn đề OTP).

---

## 4. Phạm vi ảnh hưởng (nếu Phase 0 pass và migration tiếp tục)

### Files phải sửa
| File | Thay đổi |
|---|---|
| `pyproject.toml` | `ssi-fc-data` → `ssi-sdk`, bump `requires-python` nếu cần (SDK mới yêu cầu ≥3.10, hiện repo đã ghi `>=3.11` nên OK) |
| `trading/config.py` | `Config` dataclass: bỏ `ssi_consumer_id/secret`, thêm `ssi_client_id`, `ssi_api_key`, `ssi_api_secret`, `ssi_private_key`. `load_config()` đọc env mới. |
| `trading/collector/feed.py` | Viết lại `SSIFeed` hoàn toàn: dùng `AsyncStream`/`subscribe_symbol_ohlcv` thay cho thread + channel string. Cân nhắc: có thể **bỏ luôn `BarAggregator`** nếu SDK tự trả bar 5m — cần quyết định riêng sau khi thấy field thật (không tự ý xoá `aggregator.py` nếu chưa chắc, giữ lại làm fallback). |
| `trading/collector/backfill.py` | Viết lại `SSIRestClient`: đổi tên method (`intraday_ohlc`→`get_ohlc_5minute_historical` hoặc tương đương), field parsing theo response mới. |
| `trading/collector/parser.py` | Viết lại `parse_message()` để nhận typed message mới thay vì dict envelope `{DataType, Content}`. |
| `trading/collector/main.py` | Điều chỉnh integration point (`run()`) cho phù hợp async client mới — hiện đã dùng `asyncio`, nên tích hợp có thể **đơn giản hơn** (bỏ được `queue.Queue` + `run_in_executor` nếu SDK stream native async). |
| `docker-compose.yml`, `.env` | Đổi tên biến môi trường: `SSI_CONSUMER_ID/SECRET` → `SSI_CLIENT_ID/API_KEY/API_SECRET/PRIVATE_KEY`. `PRIVATE_KEY` có thể là file/PEM — cần xác nhận format khi đăng ký console. |
| `tests/test_feed.py`, `tests/test_backfill.py`, `tests/test_parser.py` | Viết lại mock cho client/stream mới. |
| `tests/fixtures/ssi_b_messages.jsonl`, `ssi_mi_messages.jsonl` | **Không xoá** (giữ làm tài liệu lịch sử SDK cũ) — ghi fixtures mới riêng: `ssi_sdk_v2_*` |

### Files KHÔNG được đụng (ngoài phạm vi)
- `trading/engine/*`, `trading/broker/*` — không phụ thuộc SSI SDK trực tiếp.
- `trading/storage/*` — schema DB không đổi (Bar/Tick model giữ nguyên interface).
- `trading/models.py` — **giữ nguyên** `Bar`, `Tick`, `IndexValue` làm lớp trừu tượng nội bộ; SDK mới chỉ ảnh hưởng lớp adapter (`parser.py`, `backfill.py`, `feed.py`), không lan ra domain model.
- `trading/alerts/*`, `grafana/*` — không liên quan.

---

## 5. Kế hoạch theo Phase (mỗi bước có tiêu chí kiểm chứng)

### Phase 0 — Discovery spike (bắt buộc, làm trước, không viết vào `trading/`)
1. Đăng ký credentials mới trên console SSI → kiểm chứng: có đủ 4 giá trị `client_id/api_key/api_secret/private_key`.
2. Viết script `scripts/spike_ssi_sdk_auth.py` (tạm, xoá sau khi xong) test auth + streaming OTP như mục 3.1 → kiểm chứng: trả lời được câu hỏi OTP.
3. Viết script `scripts/spike_ssi_sdk_ohlc.py` gọi REST OHLC 1 symbol, in raw response ra file → kiểm chứng: có sample field thật để dùng cho Phase 2.
4. **Checkpoint với user:** báo cáo kết quả OTP + field mẫu, xin quyết định đi tiếp theo hướng nào (giữ nguyên plan / Option A/B/C ở mục 3.1).

### Phase 1 — Cập nhật credentials & config (sau khi Phase 0 pass)
1. Sửa `trading/config.py` + `.env` + `docker-compose.yml` theo bộ credentials mới → kiểm chứng: `load_config()` load được, có test `test_config.py` cập nhật cho field mới, chạy `uv run pytest tests/test_config.py -v` pass.

### Phase 2 — Migrate REST backfill
1. Viết lại `SSIRestClient` trong `backfill.py` dùng `AsyncData.market_data.get_ohlc_*_historical`.
2. Cập nhật `parse_intraday_response`/`parse_daily_response` theo field thật (lấy từ spike Phase 0).
3. Kiểm chứng: `uv run pytest tests/test_backfill.py -v` pass với fixture mới; chạy backfill thật với 1 symbol, xác nhận số bar trả về hợp lý so với REST cũ (đối chiếu chéo nếu SDK cũ vẫn gọi được).

### Phase 3 — Migrate streaming feed + parser
1. Viết lại `SSIFeed` dùng `AsyncStream`.
2. Viết lại `parse_message()` cho typed message mới.
3. Quyết định giữ hay bỏ `BarAggregator` dựa trên việc SDK có tự trả bar theo interval đúng ý (5 phút, đóng đúng biên giờ) hay không.
4. Kiểm chứng: TDD như Task 2 cũ — ghi fixture thật (`record_fixtures.py` cập nhật hoặc viết lại), viết test trước, làm test pass. `uv run pytest tests/test_feed.py tests/test_parser.py -v` pass.

### Phase 4 — E2E lại (tái sử dụng runbook Task 3)
1. Chạy lại toàn bộ Task 3 runbook (đã có sẵn `EXECUTE_TASK_3_TODAY.md`/`PLAN_TASK_3.md`) nhưng với SDK mới.
2. Kiểm chứng: cùng success criteria cũ (0 parser error, bar liên tục, latency <2s) nhưng chạy trên `ssi-sdk`.

### Phase 5 — Dọn dẹp
1. Gỡ `ssi-fc-data` khỏi `pyproject.toml` (chỉ sau khi Phase 4 pass ổn định vài phiên).
2. Archive fixtures cũ vào `tests/fixtures/legacy_ssi_fc_data/` thay vì xoá — giữ lại vì migration DB/parser tương lai có thể cần đối chiếu.
3. Xoá scripts spike ở Phase 0.

---

## 6. Ước lượng effort

| Phase | Effort | Ghi chú |
|---|---|---|
| Phase 0 (discovery) | 2-4 giờ | Phụ thuộc tốc độ đăng ký console SSI + phản hồi API |
| Phase 1 (config) | 0.5 giờ | Đơn giản |
| Phase 2 (REST backfill) | 2-3 giờ | Tương tự effort Task 6 cũ (đã làm 1 lần cho SDK cũ) |
| Phase 3 (streaming + parser) | 4-6 giờ | Phức tạp nhất — đổi kiến trúc callback + có thể bỏ aggregator |
| Phase 4 (E2E) | 1 phiên giao dịch (~6 giờ theo dõi) | Giống Task 3 |
| Phase 5 (dọn dẹp) | 0.5 giờ | |
| **Tổng** | **~10-14 giờ code + 1 phiên E2E** | Chưa tính thời gian chờ SSI duyệt đăng ký console (không kiểm soát được) |

---

## 7. Rủi ro & rollback

- **Rủi ro cao nhất:** OTP chặn streaming tự động (mục 3.1) — có thể khiến toàn bộ collector phải redesign lại cách vận hành (cần người trực nhập OTP đầu phiên).
- **Rollback:** Vì Phase 2-3 là rewrite adapter layer (không đụng `models.py`/`storage`/`engine`), có thể giữ song song 2 nhánh code (`feed.py` cũ backup tên khác) cho tới khi Phase 4 xác nhận ổn định qua ≥ 2 phiên giao dịch liên tiếp, rồi mới xoá code cũ.
- **Không tự động xoá `ssi_fc_data` khỏi dependencies** cho tới khi Phase 4 pass — để có đường lùi nếu SDK mới có bug ẩn.

---

## 8. Việc cần bạn quyết định trước khi bắt đầu Phase 0

1. Có deadline sunset cụ thể từ SSI cho package cũ không? (ảnh hưởng độ ưu tiên so với việc chạy Task 3 trước)
2. Đồng ý cách tiếp cận Phase 0 (spike script ngoài `trading/`, không phải code production) trước khi cam kết viết lại `feed.py`/`backfill.py`?
3. Nếu Phase 0 phát hiện OTP bắt buộc mỗi phiên — chấp nhận được việc nhập OTP thủ công lúc 08:55 mỗi ngày trước khi collector chạy không, hay cần escalate lên SSI support xin service-account?
