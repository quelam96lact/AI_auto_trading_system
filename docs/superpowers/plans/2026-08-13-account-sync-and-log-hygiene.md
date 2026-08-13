# Kế hoạch: sửa account sync, rò token trong log, và rác test

Ngày giao: 2026-08-13 (giờ nghỉ trưa, phiên chiều mở 13:00). Nhánh:
`feature/data-layer`. Base: `ff3a26b`.

**KHÔNG commit, KHÔNG push.** `gitnexus_impact` trước khi sửa symbol,
`gitnexus_detect_changes` khi xong.

**KHÔNG chạy collector.** Nó đang chạy thật với credential thật và đang ghi
vào `bars` của phiên hôm nay. Mọi kiểm chứng dưới đây làm bằng unit test.

**KHÔNG sửa `config/config.yaml`.**

---

## Bối cảnh: ba lỗi này tìm được lúc chạy thật, không phải đọc code

Sáng 13/08 stack được bật lại lần đầu sau 5 ngày. Cả ba lỗi dưới đây lộ ra từ
log và DB thật, không phải từ suy luận.

---

## Việc 1 (SYNC-1) — `get_equity_positions()` trả `None` làm chết cả vòng sync

### Bằng chứng thật

```
HTTP Request: GET .../api/v3/trading/position?clientId=043422&accountNo=0434221 "HTTP/1.1 200 OK"
{"level": "WARN", "msg": "account sync failed, skipping", "error": "'NoneType' object is not iterable"}
```

API trả 200. Chỗ nổ là parse.

### Nguyên nhân — đã xác minh trong mã nguồn SDK, không phải phỏng đoán

`.venv/.../ssi_sdk/models/portfolio.py:322` — `equity: list[EquityPosition] | None = None`

`.venv/.../ssi_sdk/models/portfolio.py:336`:
```python
equity=EquityPosition.from_list(data.get("equity", [])) if data.get("equity") else None,
```

Docstring của chính SDK (dòng 330-331): *"absent or empty sections yield `None`
for that side"*.

`portfolio.py:184` — `get_equity_positions()` trả thẳng `.equity`, **mặc dù
annotation ghi `-> list[EquityPosition]`**. Annotation đó sai với hành vi thật.
Danh mục rỗng → trả `None` → `trading/collector/account_sync.py:56`
`for p in positions` nổ `TypeError`.

Tài khoản `0434221` hiện **đang rỗng** (số dư 21.459 VND), nên đây là đường
chạy mặc định chứ không phải trường hợp hiếm.

### Thiệt hại kèm theo — quan trọng không kém lỗi chính

`sync_account_data()` (dòng 21-23) lặp `for account_no in cfg.ssi_equity_accounts`
với `_sync_balance` và `_sync_positions` **trần, không bọc**. Exception ở tài
khoản đầu (`0434221`) thoát khỏi vòng lặp, nên `0434226` **không được đồng bộ
gì cả** — mất cả balance lẫn position. Log chỉ hiện đúng một WARN, không hề nói
rằng có tài khoản thứ hai bị bỏ qua.

Đã đo: `account_balance_snapshot` chỉ có dòng của `0434221`, không có `0434226`.

### Phải làm

1. Guard `None` ở `_sync_positions`. Danh mục rỗng là trạng thái **hợp lệ**,
   không phải lỗi — không được alert, không được ném.
2. Bọc mỗi tài khoản trong vòng lặp để một tài khoản hỏng không giết các tài
   khoản còn lại. Khi hỏng: `alert("WARN", ...)` **nêu rõ `account_no` nào**,
   rồi `continue`. Đây là tăng khả năng quan sát, không phải nuốt lỗi — hiện
   tại lỗi đang bị nuốt *nhiều hơn* (mất im lặng cả tài khoản thứ hai).

### Ràng buộc

- Sửa: `trading/collector/account_sync.py`.
- **KHÔNG** sửa `trading/storage/db.py` trong việc này (xem "Ngoài phạm vi").
- Giữ style hiện có: docstring tiếng Việt giải thích *tại sao*.

### Kiểm chứng

1. Test `get_equity_positions` trả `None` → `_sync_positions` **không ném**, và
   **không** gọi `save_account_positions` với `None`.
   → kiểm chứng bằng: test mới trong `tests/`, chạy `uv run pytest -k ...`
2. Test tài khoản thứ nhất ném → tài khoản thứ hai **vẫn** được sync đầy đủ, và
   có đúng một WARN **chứa mã tài khoản hỏng**.
   → kiểm chứng bằng: assert trên danh sách alert bắt được + assert
     `save_account_positions`/`save_account_balance` được gọi cho tài khoản 2.
3. **Sức phân biệt (BẮT BUỘC).** Với test số 2: bỏ phần bọc try/except đi →
   test đó phải **FAIL**. Khôi phục → PASS. Dán cả hai output.
   Lý do bắt buộc: test này khẳng định "vòng lặp *không* bị cắt ngang" — một
   sự vắng mặt, rất dễ pass rỗng.

---

## Việc 2 (LOG-1) — access token in nguyên văn ra log

### Bằng chứng thật

`docker compose logs collector` chứa nguyên `Authorization: Bearer eyJ...`
dạng plaintext. Token sống 15 phút, nhưng log thường được thu thập và giữ lâu
hơn thế nhiều.

### Nguyên nhân — đã xác minh

`.venv/.../ssi_sdk/transport/websocket_client.py:76`:
```python
logger.info("Connecting to WebSocket with headers: %s", self._headers)
```
`self._headers` chứa header `Authorization` đầy đủ (gán ở dòng 73-74).

Logger name **không trùng tên file** — dòng 34: `logging.getLogger("ssi_sdk.transport.websocket")`.

Đường sync ở dòng 278 đã dùng `logger.debug` (an toàn sẵn). **Chỉ đường async
dòng 76 rò.** Ta chạy async.

Đây là `logging`, **không phải `print`** — nên chỉnh level là chặn được. Dòng
hiện ra hai lần vì logger vừa propagate lên root handler (`basicConfig` ở
`trading/collector/main.py:227`, format `%(message)s`) vừa đi qua handler riêng
của SDK (`ssi_sdk/utils/logger.py:37`). Nâng level tại chính logger đó chặn cả
hai đường, vì phép lọc level xảy ra ở logger trước khi tới handler.

### Phải làm

Ở `trading/collector/main.py`, ngay sau `logging.basicConfig(...)` (dòng 227),
nâng level của **đúng một logger** `ssi_sdk.transport.websocket` lên `WARNING`.

Kèm comment giải thích: vì sao im lặng nó, cái gì bị mất, và vì sao chấp nhận.

### Đánh đổi phải ghi rõ trong comment

Mất dòng INFO `"WebSocket connected to wss://..."`. Chấp nhận được vì: lỗi kết
nối vẫn hiện (`SSIFeed connection error`), và collector có heartbeat riêng
trong bảng `heartbeat` để biết nó còn sống. **Không** đụng tới logger
`ssi_sdk.services.token_manager` — nó log `"Token refreshed successfully"`,
hữu ích và không chứa secret.

### Ràng buộc

- Sửa: `trading/collector/main.py`. Chỉ thêm, không sửa dòng `basicConfig`.
- **KHÔNG** sửa gì trong `.venv/` — đó là thư viện bên thứ ba.
- **KHÔNG** viết bộ lọc redact regex. Một dòng `setLevel` giải quyết trọn vẹn;
  regex là thứ phải bảo trì và sẽ hỏng lặng lẽ khi SDK đổi định dạng.

### Kiểm chứng

Test dùng `caplog`: gọi `logging.getLogger("ssi_sdk.transport.websocket").info("Bearer FAKE_TOKEN_123")`
sau khi hàm cấu hình logging của collector đã chạy → **không** có record nào.
Và logger `ssi_sdk.services.token_manager` ở mức INFO thì **vẫn** có record
(chứng minh ta bịt đúng một chỗ, không bịt cả SDK).

Nếu cấu hình logging đang nằm trong `main()` không gọi được từ test, **tách nó
ra một hàm nhỏ** rồi test hàm đó — không đổi hành vi, không đổi chữ ký `main()`.

---

## Việc 3 (CLEAN-1) — test để rác trong bảng thật

### Bằng chứng thật

```sql
SELECT * FROM account_position_snapshot;
 account_no | symbol | quantity | sellable_quantity
 ACC_RTS    | ENGT   |      100 |               100
```

Dòng duy nhất trong bảng này trên DB đang chạy là **rác test**, không phải dữ
liệu thật.

### Nguyên nhân

Fixture `storage` ở `tests/test_engine_main.py:56-76` dọn `positions`, `orders`,
`engine_state`, `real_risk_state`, `pending_real_orders` — **thiếu**
`account_position_snapshot` và `real_order_fills`. Test `_seed_real_position()`
(dòng 597-601) ghi vào bảng đó mỗi lần chạy.

Bằng chứng nội tại: dòng 769-774 có một `DELETE` thủ công **ngay giữa thân
test**, kèm comment nói rõ "Fixture storage khong don ...". Đó là triệu chứng
của đúng lỗ hổng này.

### Phải làm

1. Thêm `account_position_snapshot` và `real_order_fills` (lọc
   `account_no = RTS_ACCOUNT`) vào fixture `storage`, ở **cả setup và teardown**
   — theo đúng khuôn đã có sẵn ở đó, kể cả lý do "dọn cả sau" ghi ở dòng 66-70.
2. Sau khi thêm, **thử bỏ** khối `DELETE` thủ công ở dòng 771-774 rồi chạy lại
   test đó:
   - Nếu vẫn PASS → để bỏ luôn (chính thay đổi của bạn làm nó thừa).
   - Nếu FAIL → **khôi phục lại** và báo cáo vì sao nó vẫn cần. Không sửa test
     cho vừa ý mình.

### Ràng buộc

- Sửa: `tests/test_engine_main.py`.
- **KHÔNG** đụng test nào khác, **KHÔNG** đụng `trading/`.
- `RTS_ACCOUNT` và `'ENGT'` là ranh giới dọn dẹp. **Tuyệt đối không**
  `DELETE` không điều kiện trên hai bảng đó — DB này chứa dữ liệu thật.

### Kiểm chứng

1. `docker compose exec -T postgres psql -U trading -d trading -c "DELETE FROM account_position_snapshot WHERE account_no = 'ACC_RTS'"`
   → dọn sạch hiện trạng.
2. `uv run pytest tests/test_engine_main.py -q` → pass.
3. `SELECT count(*) FROM account_position_snapshot WHERE account_no = 'ACC_RTS'`
   → phải bằng **0** sau khi suite chạy xong. Dán output thật.

---

## Toàn bộ

- `uv run pytest -q` → kỳ vọng **≥ 256** (256 hiện tại + test mới).
- `uv run ruff check trading tests` → sạch.

Dán output thật của cả hai. Không tóm tắt, không diễn giải.

---

## Ngoài phạm vi — KHÔNG được đụng

`Storage.save_account_positions()` (`db.py:330`) có `if not positions: return`.
Hệ quả: khi tài khoản bán hết sạch danh mục, snapshot rỗng **không bao giờ
được ghi**, nên `read_real_positions()` (đọc `max(ts)`) vĩnh viễn trả về vị thế
cũ — hệ thống tưởng vẫn đang nắm giữ.

Tôi (planner) đã phát hiện lỗi này nhưng **cố ý không giao**, vì sửa nó là một
quyết định thiết kế (ghi dòng sentinel? bảng "lần sync cuối" riêng?) chứ không
phải một guard. Chủ dự án sẽ quyết.

Nếu bạn thấy cách sửa hiển nhiên, **báo cáo, đừng tự sửa.**

---

## Nếu thấy kế hoạch có chỗ sai

Dừng lại và nói ra trước khi viết code. Cụ thể việc 1 mục 2 (bọc từng tài
khoản): nếu bạn tìm được lý do thuyết phục rằng một tài khoản hỏng *nên* làm
dừng cả vòng sync, hãy phản biện trước. Tôi có thể sai.
