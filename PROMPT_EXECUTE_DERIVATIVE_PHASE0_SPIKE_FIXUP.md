# Prompt thực thi: Fix Phase 0 spike phái sinh — thiếu `client_id` + sai cách tìm mã hợp đồng VN30F1M

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `scripts/spike_ssi_sdk_derivative_account.py` (đã có, chạy thật, thấy
2 lỗi cụ thể bên dưới), `scripts/spike_ssi_sdk_account.py` (pattern `client_id` đã
có, tham khảo), `trading/collector/account_sync.py` (cùng pattern dùng trong
production).

---

## ⚠️ Vẫn là spike — KHÔNG viết code production, KHÔNG đặt lệnh thật (như prompt gốc)

---

## Kết quả chạy thật (2026-07-26) — 2 lỗi cụ thể cần fix

### Lỗi 1 — thiếu `client_id`
```
Gọi get_derivative_balance(0434228)...
400 {"errors":{"clientId":["The ClientId field is required."]}}
Gọi get_derivative_positions(0434228)...
400 {"errors":{"clientId":["The ClientId field is required."]}}
Gọi get_open_derivative_positions(0434228)...
400 {"errors":{"clientId":["The ClientId field is required."]}}
```
`get_derivative_ppmmr` lại chạy OK (200, trả dữ liệu thật) — không cần `client_id`.

**Nguyên nhân:** `scripts/spike_ssi_sdk_derivative_account.py` chưa set
`auth.config.client_id` — đây là bước đã biết cần làm cho các API Portfolio cần
`clientId`, xem `scripts/spike_ssi_sdk_account.py`:
```python
def _decode_jwt_claims(access_token: str) -> dict:
    payload_b64 = access_token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))
...
claims = _decode_jwt_claims(auth.token_manager.access_token)
client_id = claims.get("client_id", "")
auth.config.client_id = client_id
```
Và `trading/collector/account_sync.py` dùng cùng pattern qua
`decode_client_id()`/`ensure_authenticated()` trong production.

### Lỗi 2 — không tìm được mã hợp đồng VN30F1M
```
get_indexes() trả về 35 index — KHÔNG có field mã hợp đồng phái sinh nào (chỉ
  index, index_name, board).
get_securities_info_by_index("VN30") trả về 30 mã — đây là 30 CỔ PHIẾU cấu thành
  chỉ số VN30 (PLX, GAS, ACB, BID, VPB, VIC, HPG, ...), KHÔNG PHẢI hợp đồng tương
  lai — 3 endpoint đã thử ĐỀU SAI HƯỚNG, cần cách khác.
get_securities_summary_by_index("VN30") trả về 0 mã (204 No Content).
Board enum chỉ có HOSE/HNX/UPCOM — không có board riêng cho phái sinh.
```

---

## ⚠️ Giới hạn phạm vi

**Chỉ sửa 1 file đã có:** `scripts/spike_ssi_sdk_derivative_account.py`.
**KHÔNG sửa** `scripts/spike_ssi_sdk_derivative_ohlc_stream.py` hay bất kỳ file
nào khác — file đó phụ thuộc output của file này, không cần đổi gì (một khi file
này tạo đúng `.spike_derivative_contract_symbol.json`, file kia tự chạy được).

**KHÔNG tự commit, không tự push.**

---

## Task A — Fix lỗi `client_id`

Copy đúng pattern `_decode_jwt_claims()` từ `scripts/spike_ssi_sdk_account.py` vào
`scripts/spike_ssi_sdk_derivative_account.py` (import `base64`, `json` đã có sẵn
hoặc thêm nếu thiếu). Trong `main()`, ngay sau `auth = await make_auth()` và
**trước** khi tạo `AsyncTrading(auth)`/gọi bất kỳ hàm nào trong
`fetch_derivative_account()`:
```python
claims = _decode_jwt_claims(auth.token_manager.access_token)
client_id = claims.get("client_id", "")
auth.config.client_id = client_id
print(f"client_id (từ JWT): {client_id}")
```

## Task B — Sửa cách tìm mã hợp đồng VN30F1M

**Xoá cách tiếp cận cũ dựa trên `get_indexes()`/`get_securities_info_by_index()`/
`get_securities_summary_by_index()`** trong `find_front_month_contract()` — đã xác
nhận cả 3 đều sai hướng (trả về index list hoặc cổ phiếu cấu thành, không phải hợp
đồng phái sinh).

**Cách mới:** dùng `data.market_data.get_securities_info(symbol: str) ->
SecuritiesInfo | None` (tra 1 mã cụ thể) — thử lần lượt các mã ứng viên theo quy
ước đặt tên hợp đồng tương lai VN30 thật trên HNX (`VN30F` + 2 số năm + 2 số
tháng, ví dụ `VN30F2508` = hợp đồng đáo hạn tháng 8/2025) cho **tháng hiện tại và
5 tháng kế tiếp** (đủ để chắc chắn phủ được hợp đồng front-month đang giao dịch dù
ngày chạy script là ngày nào), tính từ ngày hệ thống thật (`datetime.now()`, KHÔNG
hardcode 1 tháng cụ thể):

```python
from datetime import date

def _candidate_contract_codes(today: date, months_ahead: int = 6) -> list[str]:
    codes = []
    y, m = today.year, today.month
    for _ in range(months_ahead):
        codes.append(f"VN30F{y % 100:02d}{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return codes
```

Với mỗi mã ứng viên, gọi `data.market_data.get_securities_info(code)`:
- Nếu trả về `None` → in `"  {code}: không tồn tại"`, thử mã tiếp theo.
- Nếu trả về `SecuritiesInfo` thật (không `None`) → in đầy đủ record (dùng
  `dataclasses.asdict()`), coi là ứng viên hợp lệ. Ghi lại TẤT CẢ ứng viên hợp lệ
  tìm được (không chỉ lấy 1 cái đầu tiên) — vì có thể nhiều hợp đồng đang cùng
  niêm yết (front-month + các tháng xa hơn).

**Chọn front-month:** trong số các ứng viên hợp lệ, chọn mã có `last_trading_date`
(hoặc `maturity_date` nếu `last_trading_date` rỗng) **gần nhất trong tương lai** so
với hôm nay — đây mới là hợp đồng "front-month" thật (sắp đáo hạn nhất, thanh khoản
cao nhất), không phải mã có tên ngắn nhất như cách cũ (`sorted(..., key=len)[0]`
trong code hiện tại — **cách cũ này sai logic, phải xoá**, độ dài chuỗi symbol
không liên quan gì đến việc là front-month hay không).

Nếu KHÔNG có ứng viên nào hợp lệ (toàn bộ 6 tháng thử đều `None`) — in rõ:
```
Không tìm được mã hợp đồng VN30F nào qua get_securities_info() với các ứng viên
đã thử: {danh sách 6 mã đã thử}. Có thể quy ước đặt tên khác với giả định
(VN30F + YY + MM), hoặc API get_securities_info() không hỗ trợ tra cứu hợp đồng
phái sinh theo cách này — cần tra cứu thủ công trên website SSI/HNX để xác nhận
mã hợp đồng thật, sau đó gọi lại get_securities_info(<mã đã xác nhận>) để verify.
```
KHÔNG coi đây là lỗi crash — exit 0, đây là kết quả hợp lệ (phủ định).

Vẫn ghi `scripts/.spike_derivative_contract_symbol.json` như cũ nếu tìm được (giữ
nguyên cấu trúc `{"symbol": ..., "index": "VN30", "candidates": [...], "timestamp": ...}`,
`candidates` giờ là danh sách mã đã verify tồn tại thật qua `get_securities_info`,
không phải danh sách suy đoán từ field không tồn tại như code cũ).

---

## Kiểm chứng

```bash
uv run --with ssi-sdk python -c "
import ast
ast.parse(open('scripts/spike_ssi_sdk_derivative_account.py', encoding='utf-8').read())
print('OK: syntax hop le')
"
grep -n "place_order\|place_limit_order\|place_market_order\|place_fco_" scripts/spike_ssi_sdk_derivative_account.py
```
Grep phải rỗng (vẫn không được gọi API đặt lệnh).

---

## Báo cáo lại

1. Diff đầy đủ file.
2. Kết quả `ast.parse` + grep.

Không tự commit — chờ Claude audit. Sau khi audit xong, cần chạy lại thật:
```
uv run --with ssi-sdk python scripts/spike_ssi_sdk_derivative_account.py
uv run --with ssi-sdk python scripts/spike_ssi_sdk_derivative_ohlc_stream.py --seconds 120
```
