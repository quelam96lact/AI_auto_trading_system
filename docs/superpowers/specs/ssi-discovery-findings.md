# SSI FastConnect — Discovery Findings (Task 6)

Nguồn: đọc source SDK `ssi-fc-data` đã cài (`site-packages/ssi_fc_data`), ngày 2026-07-19.
Phần đánh dấu **[CHƯA XÁC MINH]** cần chạy thật với credentials (REST) và/hoặc phiên giao dịch (stream).

## Stream B fields

**[CHƯA XÁC MINH]** — cần ghi fixture trong phiên (`python scripts/record_fixtures.py`).
Đã xác minh từ source về CÁCH nhận message:

- `MarketDataStream.start(on_message, on_error, channel)`; `on_message` nhận **dict đã `json.loads`** (không phải string thô) — `fc_md_stream.py:20-26`.
- Hub: `FcMarketDataV2Hub`, listen method `"Broadcast"` + `"Error"`; subscribe qua invoke `SwitchChannels(channel)` khi socket mở — `fc_md_stream.py:46-67`.
- **`start()` NON-BLOCKING**: SDK spawn daemon thread chạy `ws.run_forever()` rồi `return True` ngay — `signalr/transports/_transport.py:63-90`. ⇒ `SSIFeed._run` (Task 8) PHẢI chờ trên event lỗi/đóng thay vì loop sau khi `start` trả về (khớp ghi chú plan dòng 1095).
- Phát hiện kết nối chết: callback `on_close` (truyền qua constructor `MarketDataStream(cfg, client, on_close=...)`); socket error → `on_socket_error` → `_on_close()` + state=disconnected — `_transport.py:162-177`.
- Config stream cần attrs: `auth_type="Bearer"`, `consumerID`, `consumerSecret`, `url`, `stream_url` — `fc_md_stream.py:52-57`.

## Stream MI fields + channel format

**[CHƯA XÁC MINH]** — SDK không hề nêu format channel (grep toàn bộ source chỉ thấy `SwitchChannels`).
Kế hoạch: thử `MI:VNINDEX` bằng `python scripts/record_fixtures.py --channel "MI:VNINDEX"` trong phiên, ghi kết quả vào đây.

## REST daily/intraday: method, params, response, limits

Đã xác minh từ source (`fc_md_client.py`, `model/model.py`, `model/api.py`) + **CALL THẬT 2026-07-19** (fixtures `tests/fixtures/ssi_daily_ohlc.json`, `ssi_intraday_ohlc.json`):

- Auth: `MarketDataClient(cfg)` tự POST `api/v2/Market/AccessToken` `{consumerID, consumerSecret}` → `{status, message, data: {accessToken}}`; token cache + tự refresh khi hết hạn; lỗi auth raise `NameError(message)`.
- **Daily OHLC**: `client.daily_ohlc(_input_data, model.daily_ohlc(...))` — `_input_data` không được dùng bên trong (truyền `None`). GET `api/v2/Market/DailyOhlc`.
  - Params (`model.daily_ohlc`): `symbol: str`, `fromDate: str`, `toDate: str`, `pageIndex=1`, `pageSize=100`, `ascending=True`.
- **Intraday OHLC**: `client.intraday_ohlc(None, model.intraday_ohlc(...))`. GET `api/v2/Market/IntradayOhlc`.
  - Params (`model.intraday_ohlc`): như daily + `resolution=1` (phút; mặc định 1m ⇒ Task 9 phải resample 5m).
- **Format ngày (XÁC MINH từ error response):** `fromDate`/`toDate` dạng `"dd/MM/yyyy"`, ràng buộc `from <= to < now`, **max range 30 ngày** (vượt quá → `{"data": null, "status": "Error", "message": "Date time format dd/MM/yyyy and ('from date' <= 'to date') < now , max range 30 days"}`). ⇒ Task 9 phải chia range thành chunk ≤30 ngày.
- **Envelope response (XÁC MINH):** `{"data": [...] | null, "message": "Success", "status": "Success", "totalRecord": N}` — `status`/`message` là **chuỗi** ("Success"/"Error"), khác `model.Response` (int). Kiểm tra thành công: `status == "Success"` hoặc `data is not None`.
- **Phân trang (XÁC MINH):** page trả đúng `pageSize` record; `totalRecord` = tổng khả dụng. VD intraday 1m ngày 17/07/2026 của VCB: `totalRecord=219`, page 1 (pageSize=100) trả đúng 100 record (09:15:54→10:57:59) ⇒ Task 9 PHẢI loop `pageIndex` tới khi đủ `totalRecord`. Daily range 27 ngày → 20 record, 1 page.
- **Cấu trúc record (XÁC MINH, casing PascalCase):**
  - Daily: `{Symbol, Market, TradingDate: "dd/MM/yyyy", Time: null, Open, High, Low, Close, Volume, Value}` — OHLC/Volume/Value là **chuỗi số** (`"61700"`), giá VND.
  - Intraday: `{Symbol, Value, TradingDate: "dd/MM/yyyy", Time: "HH:MM:SS", Open, High, Low, Close, Volume}` — không có `Market`; `Time` có cả giây (09:15:54, 09:16:55… — giây không căn phút, có vẻ là thời điểm cập nhật cuối của bar 1m; Task 9 floor về bucket 5m). `Value` ở intraday bằng Close (không phải tổng giá trị như daily).
- **Độ sâu lịch sử:** chưa dò tối đa (mới xác minh 27 ngày daily + 1 ngày intraday); giới hạn cứng duy nhất đã biết: range ≤30 ngày/call.

## Điều chưa xác minh được

1. Tên field chính xác (casing, kiểu) + field thời gian của message B và MI — chờ fixture stream trong phiên.
2. Channel MI format (`MI:VNINDEX`?) — chờ thử trong phiên.
3. `SwitchChannels` có nhận nhiều kênh một lúc (chuỗi phân tách) hay phải gọi lặp — chờ thử trong phiên.
4. Độ sâu lịch sử tối đa của daily/intraday REST (ngoài ràng buộc 30 ngày/call).

**Trạng thái Task 6:** Step 1–3 XONG (đọc SDK + script + REST fixtures thật: daily 20 record, intraday 100/219 record page 1 — đủ cho Task 9 phát triển; khi backfill thật Task 9 tự loop page). Step 4 (stream fixtures) HOÃN: ngoài phiên (ghi ngày 2026-07-19, Chủ nhật) — chạy `python scripts/record_fixtures.py` trong phiên giao dịch để sinh `ssi_b_messages.jsonl`/`ssi_mi_messages.jsonl` (điều kiện của Task 7).
