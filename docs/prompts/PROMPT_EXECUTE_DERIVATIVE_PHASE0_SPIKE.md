# Prompt thực thi: Phase 0 — spike xác nhận API phái sinh thật (VN30F1M)

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `PLAN_DERIVATIVE_TRADING.md`, `scripts/_ssi_spike_common.py`,
`scripts/spike_ssi_sdk_account.py` (style tham khảo).

---

## ⚠️ Đây CHỈ là spike nghiên cứu — KHÔNG viết code production, KHÔNG đặt lệnh thật

Tài khoản phái sinh `0434228` có ký quỹ/đòn bẩy — rủi ro tài chính của 1 lệnh sai
lớn hơn cổ phiếu nhiều. **TUYỆT ĐỐI KHÔNG gọi bất kỳ method đặt lệnh nào**
(`place_order`, `place_limit_order`, `place_market_order`, mọi `place_fco_*`) —
prompt này **chỉ đọc dữ liệu** (account info, balance, ppmmr, positions, OHLC,
stream). Nếu code có gọi bất kỳ method đặt lệnh nào, đó là lỗi nghiêm trọng ngoài
phạm vi — DỪNG ngay, không chạy.

---

## ⚠️ Giới hạn phạm vi

**Chỉ tạo file mới, không sửa file nào có sẵn:**
- `scripts/spike_ssi_sdk_derivative_account.py`
- `scripts/spike_ssi_sdk_derivative_ohlc_stream.py`

**KHÔNG sửa** bất kỳ file nào trong `trading/`, `tests/`, hay các script spike đã
có. Dùng lại `make_auth()` từ `scripts/_ssi_spike_common.py` (đã có, không viết lại
logic auth).

**KHÔNG tự commit, không tự push.**

---

## Task A — `scripts/spike_ssi_sdk_derivative_account.py`

Mục đích: xác nhận dữ liệu balance/margin/position thật của tài khoản phái sinh
`0434228`, và tìm mã hợp đồng VN30F1M thật (front-month).

```
Chạy: uv run --with ssi-sdk python scripts/spike_ssi_sdk_derivative_account.py
```

Yêu cầu:
1. Dùng `make_auth()` từ `_ssi_spike_common.py`.
2. `AsyncTrading(auth)` → gọi lần lượt (đều async, đều account_no="0434228"):
   - `trading.portfolio.get_derivative_balance("0434228")`
   - `trading.portfolio.get_derivative_ppmmr("0434228")`
   - `trading.portfolio.get_derivative_positions("0434228")`
   - `trading.portfolio.get_open_derivative_positions("0434228")`
3. Tìm mã hợp đồng VN30F1M thật: `market_data` KHÔNG nằm trên `AsyncTrading` — nó
   nằm trên `AsyncData(auth).market_data` (`AsyncMarketDataService`), instance
   riêng, xem cách `scripts/spike_ssi_sdk_ohlc.py` đã dùng `AsyncData(auth)`. Gọi
   `data.market_data.get_indexes()` và/hoặc
   `data.market_data.get_securities_info_by_index("VN30")` (thử tên tham số/kết
   quả thật — nếu signature khác dự đoán, đọc `inspect.signature()` thật trước khi
   gọi, đừng đoán). Mục tiêu: tìm ra chuỗi symbol thật của hợp đồng tương lai VN30
   tháng gần nhất đang giao dịch (khả năng dạng `VN30F` + năm + tháng, ví dụ
   `VN30F2508` — nhưng PHẢI lấy từ response thật, không hardcode theo đoán).
4. In từng response ra console (dùng `dataclasses.asdict()` nếu là dataclass, hoặc
   `default=str` nếu lỗi serialize) VÀ ghi ra file JSON riêng từng loại:
   `scripts/.spike_derivative_balance.json`, `.spike_derivative_ppmmr.json`,
   `.spike_derivative_positions.json`, `.spike_derivative_contract_symbol.json`
   (file cuối chỉ cần chứa symbol thật tìm được + timestamp).
5. Nếu bất kỳ call nào lỗi (401/403/APIError) — in rõ toàn bộ thông tin lỗi (dùng
   `log_level="DEBUG"` như các script spike khác đã làm để thấy `response_body`
   thật), KHÔNG che giấu, KHÔNG catch-and-continue âm thầm — để lộ rõ nếu API
   không hoạt động với tài khoản Derivative.

**Cập nhật `.gitignore`:** thêm 4 dòng cho 4 file `.json` mới ở trên (theo đúng
pattern các dòng `scripts/.spike_*.json` đã có).

## Task B — `scripts/spike_ssi_sdk_derivative_ohlc_stream.py`

Mục đích: xác nhận có lấy được dữ liệu giá (lịch sử + real-time) cho hợp đồng
VN30F1M hay không, dùng đúng mã hợp đồng thật tìm được ở Task A (đọc từ
`scripts/.spike_derivative_contract_symbol.json`, không hardcode lại).

```
Chạy: uv run --with ssi-sdk python scripts/spike_ssi_sdk_derivative_ohlc_stream.py [--seconds 120]
```

Yêu cầu:
1. Đọc mã hợp đồng thật từ `scripts/.spike_derivative_contract_symbol.json` (nếu
   file không tồn tại, in lỗi rõ ràng yêu cầu chạy Task A trước, exit 1).
2. Dùng `AsyncData(auth).market_data` (KHÔNG phải `trading.market_data` — xem Task
   A điểm 3). Gọi `data.market_data.get_ohlc_1minute(<symbol>)` (hoặc
   `get_ohlc_1minute_historical` nếu bản không-historical yêu cầu tham số khác —
   đọc `inspect.signature()` thật trước khi gọi) — in ra số lượng bar nhận được +
   1 bar mẫu đầy đủ. Ghi ra `scripts/.spike_derivative_ohlc_sample.json`.
3. Dùng `AsyncStream(auth)` → `stream.streaming.on_data = <callback ghi log>` →
   `connect()` → `subscribe_symbol([<symbol>])` (nhận `list[str]`, giống
   `subscribe_index` đã dùng trong `spike_ssi_sdk_index_stream.py`, nhưng ở đây
   dùng `subscribe_symbol` vì đây là 1 mã hợp đồng cụ thể, không phải chỉ số) — lắng
   nghe trong `--seconds` giây (mặc định 120), ghi mỗi message ra
   `scripts/.spike_derivative_stream_sample.jsonl`. Nếu không nhận được message
   nào: in rõ "có thể ngoài giờ giao dịch hoặc symbol sai", KHÔNG coi là lỗi crash,
   exit 0.

**Cập nhật `.gitignore`:** thêm 2 dòng cho `.spike_derivative_ohlc_sample.json` và
`.spike_derivative_stream_sample.jsonl`.

---

## Điều kiện bắt buộc (không thoả thì DỪNG, báo cáo lại thay vì tự ý xử lý khác)

1. `grep -n "place_order\|place_limit_order\|place_market_order\|place_fco_" scripts/spike_ssi_sdk_derivative_account.py scripts/spike_ssi_sdk_derivative_ohlc_stream.py` phải **rỗng** — 2 script này tuyệt đối không được gọi bất kỳ method đặt lệnh nào.
2. Không sửa file nào ngoài 2 file mới + `.gitignore`.

**Kiểm chứng (không cần credentials thật để verify cú pháp — giống các script spike khác):**
```bash
uv run --with ssi-sdk python -c "
import ast
for f in ['scripts/spike_ssi_sdk_derivative_account.py', 'scripts/spike_ssi_sdk_derivative_ohlc_stream.py']:
    ast.parse(open(f, encoding='utf-8').read())
    print(f, 'OK: syntax hop le')
from ssi_sdk import AsyncAuth, AsyncTrading, AsyncStream, AsyncData
print('OK: import cac symbol dung ton tai')
"
```

---

## Báo cáo lại

1. Toàn bộ nội dung 2 file mới + diff `.gitignore`.
2. Kết quả `ast.parse`/import check.
3. Kết quả grep xác nhận không gọi method đặt lệnh nào (điều kiện bắt buộc #1).

**Sau khi báo cáo xong, KHÔNG dừng ở đây** — báo cho user biết cần **chạy cả 2
script này thật** (Task A trước, Task B sau — Task B phụ thuộc file symbol Task A
tạo ra), Task B nên chạy trong giờ giao dịch phái sinh (07:45-11:30, 13:00-14:45,
lưu ý phái sinh có ATO/ATC riêng, khác giờ cổ phiếu chút ít — nếu không chắc giờ
chính xác, cứ chạy trong giờ giao dịch cổ phiếu thông thường trước, verify sau).
Báo lại toàn bộ nội dung các file `.json`/`.jsonl` sinh ra (hoặc kết luận "không
nhận được dữ liệu") để viết plan Phase 1 (thiết kế model vị thế + risk phái sinh)
dựa trên dữ liệu thật, không dựa trên giả định.

Không tự commit — chờ Claude audit.
