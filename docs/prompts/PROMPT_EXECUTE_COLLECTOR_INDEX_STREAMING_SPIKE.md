# Prompt thực thi: Fix #4 — spike xác nhận cách stream VNINDEX/VN30 thật

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** TODO đã ghi trong `trading/collector/main.py:63-64` và `trading/collector/feed.py:146-147`.

---

## ⚠️ Đây CHỈ là spike xác nhận dữ liệu thật — KHÔNG viết code production ở prompt này

TODO cũ đoán cần dùng `subscribe_symbol_trade(cfg.indices)` — **đoán sai, đã tra lại source code thật**: `ssi-sdk` có method riêng cho index, **`AsyncStreamingService.subscribe_index(indices: list[str], on_response=None)`** (docstring: *"Subscribe to trade, quote, and foreign-room channels for the given indices"*). Đây là method đúng cần dùng, KHÔNG phải `subscribe_symbol_trade`.

**Vẫn chưa biết:** hình dạng thật của message nhận được qua `on_data` khi subscribe index bằng method này (có phải `TradeMessage` như cổ phiếu, hay `MarketIndexSummary`/dạng khác — `MarketIndexSummary` tồn tại trong `ssi_sdk.models` nhưng có vẻ dùng cho REST summary query, chưa chắc là shape của message stream). Đây là lý do BẮT BUỘC phải verify bằng dữ liệu thật trong giờ giao dịch trước khi viết `IndexValue` mapping — đúng nguyên tắc đã áp dụng xuyên suốt dự án (không đoán format SDK, luôn verify bằng dữ liệu thật).

---

## ⚠️ Giới hạn phạm vi

**Chỉ tạo 1 file mới:** `scripts/spike_ssi_sdk_index_stream.py` (script tạm, style giống `scripts/spike_ssi_sdk_ohlc.py`/`scripts/spike_ssi_sdk_auth.py` đã có — dùng chung `scripts/_ssi_spike_common.py::make_auth()`).

**KHÔNG sửa** `trading/collector/feed.py`, `trading/collector/main.py`, `trading/collector/parser.py`, `trading/models.py` — việc implement `IndexValue` mapping thật sự là 1 prompt RIÊNG, viết SAU khi có dữ liệu thật từ spike này (giống cách Phase 2 SDK migration đã làm với OHLC/stream trước đây).

**KHÔNG tự commit, không tự push.**

---

## Task A — `scripts/spike_ssi_sdk_index_stream.py`

```
Chạy: uv run --with ssi-sdk python scripts/spike_ssi_sdk_index_stream.py [--seconds 120]
```

Yêu cầu:
1. Dùng `make_auth()` từ `scripts/_ssi_spike_common.py` (đã có, không viết lại logic auth).
2. `AsyncStream(auth)` → `stream.streaming.on_data = <callback ghi log>` → `await stream.streaming.connect()` → `await stream.streaming.subscribe_index(["VNINDEX", "VN30"])`.
3. Callback `on_data` — với MỖI message nhận được, ghi ra `scripts/.spike_index_stream_sample.jsonl` (mỗi dòng 1 JSON, dùng `dataclasses.asdict()` nếu là dataclass, hoặc `json.dumps(raw, default=str)` nếu là dict thô — kiểm tra kiểu dữ liệu thật nhận được, KHÔNG giả định trước là dataclass hay dict).
4. Lắng nghe trong khoảng thời gian truyền qua `--seconds` (mặc định 120), sau đó `await stream.streaming.disconnect()`, in ra tổng số message nhận được và in luôn 1 message mẫu đầy đủ ra console (để dễ đọc ngay không cần mở file).
5. Nếu sau `--seconds` giây mà KHÔNG nhận được message nào: in rõ "Không nhận được message nào — có thể ngoài giờ giao dịch hoặc subscribe_index không hoạt động như kỳ vọng", KHÔNG coi là lỗi crash, exit 0 (đây là kết quả hợp lệ, không phải bug).

**Cập nhật `.gitignore`:** thêm `scripts/.spike_index_stream_sample.jsonl`.

**Kiểm chứng (không cần chạy thật với credentials — giống cách các script spike khác đã verify):**
```bash
uv run --with ssi-sdk python -c "
import ast
src = open('scripts/spike_ssi_sdk_index_stream.py', encoding='utf-8').read()
ast.parse(src)
print('OK: syntax hop le')
from ssi_sdk import AsyncAuth, AsyncStream
print('OK: import cac symbol dung ton tai')
"
```

---

## Báo cáo lại

1. Toàn bộ nội dung `scripts/spike_ssi_sdk_index_stream.py`.
2. Kết quả `ast.parse`/import check.

**Sau khi báo cáo xong, KHÔNG dừng ở đây** — báo cho user biết cần **chạy script này thật trong giờ giao dịch** (09:15-11:30 hoặc 13:00-14:45 giờ VN) để lấy dữ liệu mẫu thật, rồi báo lại kết quả (nội dung `scripts/.spike_index_stream_sample.jsonl` hoặc kết luận "không nhận được message nào"). Việc viết `IndexValue` mapping thật vào `trading/collector/feed.py`/`parser.py` sẽ là 1 prompt riêng, viết SAU khi có dữ liệu thật này — không viết trước để tránh dựa vào giả định chưa kiểm chứng, đúng nguyên tắc lập kế hoạch của dự án.

Không tự commit — chờ Claude audit.
