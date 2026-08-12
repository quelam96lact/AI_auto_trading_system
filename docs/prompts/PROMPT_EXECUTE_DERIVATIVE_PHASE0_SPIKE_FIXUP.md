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

**⚠️ CẬP NHẬT QUAN TRỌNG (sau khi viết bản đầu prompt này):** người dùng chụp màn
hình thật màn "Giao dịch phái sinh" trên nền tảng SSI, xác nhận **quy ước đặt tên
`VN30F` + năm + tháng (kiểu HNX công khai) KHÔNG PHẢI mã SSI dùng nội bộ** — mã thật
theo ảnh chụp có dạng khác hẳn, ví dụ **`41I1G8000`** với tooltip xác nhận rõ:
*"HDTL VN30 đáo hạn 20/08/2026"* (hợp đồng tương lai VN30, đáo hạn 20/08/2026) —
và đây cũng là mã có OI (khối lượng mở) cao nhất trong nhóm (39,352), đúng nghĩa
front-month thanh khoản cao nhất, tính từ ngày hôm nay (2026-07-26).

Các mã khác nhìn thấy trong cùng nhóm (cùng "Giao dịch phái sinh", đều có OI thật,
xếp theo OI giảm dần — nhiều khả năng là chuỗi hợp đồng VN30 các kỳ hạn xa hơn hoặc
1 series phái sinh khác, KHÔNG chắc chắn 100% ý nghĩa từng mã, không suy diễn thêm):
`41I1G8000` (OI 39,352), `41I1G9000` (OI 1,140), `41I1GC000` (OI 843), `41I1H3000`
(OI 36), `41I2G8000` (OI 68), `41I2G9000` (OI 19), `41I2GC000` (OI 42), `41I2H3000`
(OI 6).

**Bỏ hoàn toàn giả định "VN30F+YYMM" — dùng thẳng các mã thật đã quan sát ở trên
để verify qua API**, xem Task B đã sửa lại bên dưới.

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
SecuritiesInfo | None` (tra 1 mã cụ thể) — verify từng mã trong danh sách mã **THẬT
đã quan sát trực tiếp trên giao diện SSI** (không phải suy đoán quy ước đặt tên):

```python
OBSERVED_CANDIDATES = [
    # (symbol, open_interest quan sát được trên UI SSI 2026-07-26 — dùng để sắp
    # xếp ưu tiên, KHÔNG phải dữ liệu lấy qua API, chỉ để chọn thứ tự thử trước)
    ("41I1G8000", 39_352),
    ("41I1G9000", 1_140),
    ("41I1GC000", 843),
    ("41I1H3000", 36),
    ("41I2G8000", 68),
    ("41I2G9000", 19),
    ("41I2GC000", 42),
    ("41I2H3000", 6),
]
```

Với mỗi mã trong `OBSERVED_CANDIDATES` (thử theo đúng thứ tự liệt kê ở trên, OI
giảm dần), gọi `data.market_data.get_securities_info(symbol)`:
- Nếu trả về `None` → in `"  {symbol}: không tồn tại qua get_securities_info()"`,
  thử mã tiếp theo.
- Nếu trả về `SecuritiesInfo` thật (không `None`) → in đầy đủ record (dùng
  `dataclasses.asdict()`), coi là ứng viên hợp lệ. Thử **hết cả danh sách**, không
  dừng ở mã đầu tiên hợp lệ — ghi lại toàn bộ ứng viên hợp lệ tìm được.

**Chọn front-month:** trong số các ứng viên hợp lệ (`get_securities_info()` trả về
khác `None`), chọn mã `41I1G8000` nếu nó hợp lệ (đã xác nhận qua UI thật: "HDTL
VN30 đáo hạn 20/08/2026", OI cao nhất — đúng nghĩa front-month tính từ hôm nay
2026-07-26). Nếu `41I1G8000` không hợp lệ (trả `None`) nhưng có ứng viên hợp lệ
khác, chọn ứng viên có `last_trading_date` (hoặc `maturity_date` nếu
`last_trading_date` rỗng) **gần nhất trong tương lai** so với hôm nay.

Nếu **KHÔNG có ứng viên nào trong `OBSERVED_CANDIDATES` hợp lệ** — in rõ:
```
Không mã nào trong danh sách quan sát từ UI SSI hợp lệ qua get_securities_info().
Đã thử: {danh sách 8 mã}. get_securities_info() có thể không hỗ trợ tra cứu hợp
đồng phái sinh theo symbol dạng này, hoặc mã đã đổi — cần đối chiếu lại UI SSI
tại thời điểm chạy script, không suy đoán thêm.
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
