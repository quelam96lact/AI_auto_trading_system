# Fixtures SSI FastConnect

Raw dữ liệu thật ghi từ SSI FastConnect bằng `scripts/record_fixtures.py` (Task 6).
Dữ liệu thị trường công khai — được phép commit. TUYỆT ĐỐI không để credentials lọt vào đây.

| File | Nguồn | Nội dung |
|------|-------|----------|
| `ssi_b_messages.jsonl` | stream kênh `B:*` | mỗi dòng 1 message JSON (dict sau khi SDK `json.loads`) |
| `ssi_mi_messages.jsonl` | stream kênh MI | message index (MI) |
| `ssi_daily_ohlc.json` | REST `MarketDataClient.daily_ohlc` | response thô `{status, message, data}` |
| `ssi_intraday_ohlc.json` | REST `MarketDataClient.intraday_ohlc` | response thô, resolution 1m |

Trạng thái: **CHƯA GHI** — chờ `SSI_CONSUMER_ID`/`SSI_CONSUMER_SECRET` (REST) và phiên giao dịch đang mở (stream).