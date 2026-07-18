# Thiết kế hệ thống Auto-Trading — SSI FastConnect

**Ngày:** 2026-07-18 · **Trạng thái:** Đã duyệt qua brainstorming · **Ngôn ngữ:** Python thuần

## 1. Mục tiêu và phạm vi

Xây hệ thống auto-trading cho chứng khoán Việt Nam qua SSI FastConnect API, gồm: thu thập dữ liệu (realtime + lịch sử), lưu trữ, backtest chiến lược, và giao dịch **paper trading** (giả lập khớp lệnh). Hạ tầng xây trước; chiến lược là plugin cắm vào sau — chiến lược đầu tiên (SMA cross) chỉ để chứng minh pipeline chạy đúng.

**Ngoài phạm vi giai đoạn này** (thiết kế sau, không code bây giờ):

- Đẩy lệnh thật qua `ssi-fctrading` (PrivateKey + 2FA).
- Nguồn crypto (Binance/Bybit) — kiến trúc đã chừa chỗ (xem §3).
- Chiến lược ML/AI dự đoán giá.

**Môi trường chạy:** VPS Linux, Docker Compose. Dev trên Windows, code không phụ thuộc OS.

## 2. Quyết định nền tảng

| Quyết định | Lựa chọn | Lý do |
|---|---|---|
| Thị trường | SSI (chứng khoán VN) trước, crypto sau | Memory `ssi-fastconnect-api-facts` đã xác minh API |
| Ngôn ngữ | Python thuần | SSI chỉ có SDK Python chính thức (`ssi-fc-data`); hệ sinh thái backtest mạnh |
| Kiến trúc | 2 service (collector + engine) nối qua NATS JetStream | Collector phải sống liên tục suốt phiên; engine restart thường xuyên lúc dev |
| Storage | PostgreSQL + TimescaleDB (bar + state chung một DB) | Grafana đọc trực tiếp; một DB đơn giản vận hành |
| Bar gốc | 5 phút | Người dùng chốt không cần mịn hơn; 15m/1h resample từ 5m |
| Execution | PaperBroker (giả lập) trước | SSI không có sandbox; lệnh thật là giai đoạn sau, cùng interface |
| Monitoring | Grafana + Telegram bot | Không tự viết UI; cảnh báo phân tầng |

## 3. Kiến trúc tổng thể

```
                 ┌────────────────── VPS Linux (Docker Compose) ──────────────────┐
                 │                                                                │
SSI fc-datahub ──┼─▶ COLLECTOR ──▶ NATS JetStream ──▶ TRADING ENGINE              │
(SignalR tick)   │   tick → bar 5m    bars.ssi.{sym}    strategy → RiskManager    │
SSI fc-data ─────┼─▶ backfill REST                      → PaperBroker → PnL       │
(OHLC lịch sử)   │        │                                   │                   │
                 │        ▼                                   ▼                   │
                 │   PostgreSQL + TimescaleDB (bars, index, orders, positions,    │
                 │   pnl, heartbeat) ◀── Grafana đọc trực tiếp                    │
                 │        ▲                                                       │
                 │        └── BACKTEST CLI (offline, không qua NATS):             │
                 │            đọc bars → cùng Strategy + PaperBroker → báo cáo    │
                 └────────────────────────────────────────────────────────────────┘
                 Telegram bot: cảnh báo INFO/WARN/CRITICAL từ collector + engine
```

Ba nguyên tắc xương sống:

1. **PostgreSQL là nguồn sự thật.** NATS chỉ là đường truyền realtime. Mất bus không mất dữ liệu; mọi gap vá được bằng backfill REST.
2. **Backtest và live dùng chung interface.** Chiến lược chỉ thấy `Strategy` và `Broker`; test xong chạy live không đổi code — chỉ đổi nguồn bar (DB vs NATS).
3. **Ranh giới nguồn dữ liệu nằm trong collector.** Thêm crypto = viết collector mới publish cùng schema bar lên `bars.binance.{sym}`; engine không biết nguồn.

**Container:** `nats`, `postgres` (TimescaleDB), `collector`, `engine`, `grafana`.

## 4. Thành phần

| Thành phần | Loại | Nhiệm vụ | Không làm |
|---|---|---|---|
| **Collector** | service | SSI SignalR kênh `B` (tick từng mã) + `MI` (chỉ số VNINDEX/VN30) → gom bar 5m → ghi DB + publish NATS; backfill REST khi khởi động; job cuối ngày vá gap | Không biết chiến lược/lệnh |
| **Storage** | thư viện | Schema + API đọc/ghi: `read_bars(symbol, tf, from, to)`, `write_bars(...)`, upsert khóa `(symbol, timestamp)` | Không chứa logic nghiệp vụ |
| **Engine** | service | Subscribe NATS (JetStream durable consumer), nạp strategy từ config, signal → RiskManager → PaperBroker, ghi state DB, heartbeat | Không thu thập dữ liệu |
| **Strategy** | interface | `on_bar(bar, context) -> Signal \| None`; ví dụ đầu: SMA cross | Không gọi API/đặt lệnh trực tiếp |
| **RiskManager** | thư viện | Chặn order vượt: số vị thế mở tối đa, giá trị lệnh tối đa, lỗ tối đa/ngày (→ dừng giao dịch + CRITICAL). Áp dụng cả paper | Không sinh signal |
| **PaperBroker** | thư viện | Khớp giả lập theo §5.1; theo dõi vị thế, PnL | Không gửi lệnh thật (SSIBroker sau, cùng interface `Broker`) |
| **Backtest** | CLI | Đọc bar DB → phát lại qua Strategy + RiskManager + PaperBroker → báo cáo PnL, max drawdown, win rate | Không cần NATS/collector |
| **Resampler** | thư viện | Hàm duy nhất gom 5m → 15m/1h, dùng chung live engine (in-memory) và backtest | — |
| **Alerter** | thư viện | Gửi Telegram theo tầng INFO/WARN/CRITICAL (§7.3) | — |

**Cấu hình:** YAML (danh sách mã theo dõi, strategy + tham số, phí/slippage, risk limits, ngưỡng watchdog). **Secrets** (ConsumerID/Secret, Telegram token) qua biến môi trường. Kênh SSI `R` (room nước ngoài) là cờ config bật sau — schema bảng tính trước, chưa code.

## 5. Data flow

### 5.1 Live

1. Tick SignalR (envelope `{"DataType": "B", "Content": "<json string>"}` — Content là JSON string, casing thay đổi) → collector gom bar 5m theo ranh giới đồng hồ, tôn trọng phiên VN: 9h00–11h30, 13h00–14h45, nghỉ trưa, ATO/ATC, lịch nghỉ lễ.
2. Bar đóng → upsert DB + publish `bars.ssi.{symbol}` (JetStream).
3. Engine `on_bar` → strategy trả Signal → RiskManager duyệt → PaperBroker khớp: **giá mở bar kế tiếp** + phí cấu hình được (mặc định VN: phí GD 0.15%, thuế bán 0.1%) + slippage theo bps.
4. Vị thế/PnL ghi DB → Grafana hiển thị; Telegram báo signal/fill (INFO).

### 5.2 Backfill

- Khởi động: so DB với REST (`DailyOhlc`, `IntradayOhlc`), tải phần thiếu, throttle theo rate limit.
- Lần đầu: toàn bộ lịch sử daily SSI cho phép + intraday tối đa API trả được.
- Job cuối ngày: tải bù toàn bộ dữ liệu ngày hôm đó để vá mọi gap còn sót.
- Upsert idempotent — chạy lại không tạo bản ghi trùng.

### 5.3 Backtest

CLI: `backtest --strategy sma_cross --symbols VCB,HPG --from 2024-01-01 --to 2026-06-30 --tf 15m`. Đọc bar DB, resample nếu cần, phát lại qua đúng code path live (Strategy + RiskManager + PaperBroker), xuất báo cáo. Cùng dữ liệu + cùng config → kết quả giống hệt nhau (deterministic).

## 6. Schema dữ liệu chính (phác thảo)

- `bars(symbol, timestamp, open, high, low, close, volume, source)` — hypertable, PK `(symbol, timestamp)`, chỉ lưu 5m.
- `index_values(index_id, timestamp, value, ...)` — kênh MI.
- `orders(id, ts, symbol, side, qty, price, status, mode=paper|live)`.
- `positions(symbol, qty, avg_price, updated_at)`; `pnl_daily(date, realized, unrealized, fees)`.
- `heartbeat(service, last_seen)` — engine/collector ghi định kỳ, Grafana + healthcheck đọc.

Chi tiết cột chốt ở bước implementation plan.

## 7. Xử lý lỗi và độ tin cậy

1. **Đứt SignalR:** reconnect tự động backoff lũy tiến, WARN qua Telegram; nối lại xong vá gap bằng REST.
2. **Watchdog feed đứng im:** trong giờ giao dịch, >3 phút (cấu hình được) không có tick dù kết nối còn sống → WARN + force reconnect; 3 lần liên tiếp thất bại → CRITICAL.
3. **Engine restart giữa phiên:** JetStream durable consumer phát lại bar lỡ; vị thế đọc lại từ DB — không mất state.
4. **NATS chết:** collector vẫn ghi DB; engine đọc bù từ DB khi bus sống lại, CRITICAL nếu quá ngưỡng.
5. **Risk limits (§4 RiskManager):** chạm lỗ tối đa/ngày → dừng giao dịch đến hết ngày + CRITICAL.
6. **Cảnh báo phân tầng:** INFO (signal, fill — có thể gộp), WARN (reconnect, gap đã vá), CRITICAL (mất dữ liệu kéo dài, service chết, chạm risk limit — gửi ngay, lặp đến khi xử lý). Log JSON có cấu trúc.
7. **Tự phục hồi:** mọi container `restart: unless-stopped` + healthcheck riêng (collector: độ tươi tick trong giờ GD; engine: heartbeat DB; NATS/Postgres: ping chuẩn); systemd chạy `docker compose up -d` khi VPS reboot.

## 8. Testing

- **Unit:** gom tick→bar 5m (ranh giới phiên, nghỉ trưa, ATO/ATC); resampler 5m→15m/1h; PaperBroker (khớp, phí, thuế bán, slippage); RiskManager (từng limit); logic SMA cross.
- **Integration:** phát lại fixture message SSI thật đã ghi qua collector → so bar với kỳ vọng; backtest trên bộ dữ liệu cố định → kết quả deterministic.
- **Kiểm chứng theo CLAUDE.md nguyên tắc 4:** mỗi sub-project có tiêu chí bằng chứng riêng (§9); không chấp nhận "đã xong" thiếu bằng chứng.

## 9. Lộ trình sub-project

Mỗi sub-project một chu trình spec → plan → implement riêng, theo thứ tự:

1. **Lớp dữ liệu:** collector (B + MI) + TimescaleDB + backfill + NATS publish + watchdog. *Kiểm chứng:* bar 5m xuất hiện trong DB trong phiên live, khớp giá iBoard; tắt collector 10 phút giữa phiên → gap được vá tự động.
2. **Backtest + interface Strategy:** Strategy/Broker interface, PaperBroker, RiskManager, resampler, backtest CLI, SMA cross. *Kiểm chứng:* backtest trên dữ liệu đã thu chạy 2 lần ra kết quả giống hệt; unit test pass.
3. **Live engine + paper trading:** engine service, JetStream consumer, state DB, heartbeat. *Kiểm chứng:* một phiên live đầy đủ có lệnh paper + PnL ghi đúng; kill engine giữa phiên → tự phục hồi không mất vị thế.
4. **Monitoring:** dashboard Grafana (giá, PnL, vị thế, sức khỏe service) + Telegram alerter phân tầng. *Kiểm chứng:* dashboard hiển thị dữ liệu thật; giả lập đứt feed → nhận WARN đúng tầng.

Giai đoạn 5+ (chưa thiết kế): SSIBroker lệnh thật, crypto collector, chiến lược ML.

## 10. Ràng buộc đã xác minh (từ memory `ssi-fastconnect-api-facts`, 2026-07-12)

- Auth: ConsumerID + ConsumerSecret → Bearer qua `Market/AccessToken`; SDK `ssi-fc-data`.
- URL: REST `https://fc-data.ssi.com.vn/`, stream `https://fc-datahub.ssi.com.vn/` (SignalR). **Không có sandbox data** (`fc-trialdata` không tồn tại).
- Streaming: `MarketDataStream(config, MarketDataClient(config)).start(on_message, on_error, "B:VCB-TCB-HPG")`; config cần đúng attrs `auth_type/consumerID/consumerSecret/url/stream_url`. **Không có** API `client.subscribe(symbol, cb)`.
- Kênh `B` = OHLC theo tick, `Volume` = khối lượng khớp cuối → phải tự gom thành bar.
- FastConnect Trading là sản phẩm riêng (`ssi-fctrading`, PrivateKey + 2FA) — ngoài phạm vi.
- Không tin snippet SSI nào trong repo có trước 2026-07-12.
