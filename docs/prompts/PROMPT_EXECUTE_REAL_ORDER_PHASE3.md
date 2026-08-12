# Prompt thực thi: Đặt lệnh thật — Phase 3 (Script xác nhận thủ công + dry-run gate)

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `PLAN_REAL_ORDER_PLACEMENT.md` + **Phase 1 và Phase 2 phải đã merge xong**. Nếu chưa, DỪNG, báo lại.

**🔴 Đây là phần rủi ro cao nhất trong toàn bộ dự án — file này, khi `real_trading_enabled=true`, sẽ gọi API đặt lệnh THẬT lên sàn bằng tiền thật.** Viết cẩn thận, không đoán response shape (dùng đúng field đã xác nhận ở `PLAN_REAL_ORDER_PLACEMENT.md` mục "Đã xác nhận từ source code thật"), không tự thêm tính năng ngoài yêu cầu (không auto-retry, không tự đặt lệnh khác nếu lệnh đầu fail — dừng và báo lỗi rõ ràng).

---

## ⚠️ Giới hạn phạm vi

**Chỉ tạo 1 file mới:** `scripts/confirm_real_order.py`. **KHÔNG sửa** `trading/real_orders.py`, `trading/engine/main.py`, `trading/engine/logic.py`, `trading/collector/ssi_auth.py` (đặc biệt `ensure_authenticated()` — không đụng).

**KHÔNG tự động hoá việc chạy script này** (không thêm vào docker-compose, không thêm cronjob, không gọi từ engine) — đây là script **chạy thủ công bởi người dùng**, đúng theo quyết định đã chốt ("Tự động tính tín hiệu, nhưng mỗi lệnh thật cần xác nhận riêng").

**Trước khi viết:** verify lại bằng `inspect.signature()` thật (không tin vào plan doc nếu nghi ngờ đã đổi):
```bash
uv run python -c "
import inspect
from ssi_sdk.services.trading import AsyncTradingService
print(inspect.signature(AsyncTradingService.place_limit_order))
print(inspect.signature(AsyncTradingService.cancel_order))
from ssi_sdk.models import PlaceOrderResponse, CancelOrderResponse
import dataclasses
print([f.name for f in dataclasses.fields(PlaceOrderResponse)])
print([f.name for f in dataclasses.fields(CancelOrderResponse)])
"
```
Nếu kết quả khác với plan doc đã ghi, DỪNG, báo lại thay vì tự điều chỉnh theo giả định.

**KHÔNG tự commit, không tự push.**

---

## Task A — `scripts/confirm_real_order.py`

**File tạo mới:** `scripts/confirm_real_order.py`

Yêu cầu hành vi (theo đúng thứ tự, không đảo, không bỏ bước):

```
Chạy: uv run --with ssi-sdk python scripts/confirm_real_order.py <id>
```

1. Load config qua `load_config("config/config.yaml")` (hoặc pattern tương tự `trading/engine/main.py::main()` — đọc file đó để khớp style CLI argparse).
2. `storage.get_pending_order(id)` — nếu không tồn tại: in lỗi rõ, exit code khác 0.

**Lưu ý (đã đổi sau khi viết prompt này):** `storage.update_pending_order_status()` giờ raise `ValueError` nếu `id` không khớp dòng nào (thay vì âm thầm no-op — fix bảo mật, xem `PLAN_REAL_ORDER_PLACEMENT.md`). Vì bước 2 đã đọc dòng này thành công ngay trước đó, tình huống này chỉ xảy ra do race condition (vd 2 người chạy script cùng lúc trên cùng `id`) — không cần xử lý đặc biệt, để exception tự nổi lên (traceback rõ ràng) là đủ, KHÔNG bắt và nuốt lỗi này.
3. Kiểm tra `status == 'pending'` và `expires_at > now()` — nếu không (đã hết hạn/đã xử lý), in rõ trạng thái hiện tại, exit, **không làm gì thêm**.
4. In đầy đủ chi tiết lệnh (account_no, symbol, side, quantity, price, tạo lúc nào, hết hạn lúc nào).
5. Hỏi xác nhận qua `input()`: `"Nhập YES để xác nhận đặt lệnh THẬT (Enter/bất kỳ để huỷ): "`.
   - Nếu khác `"YES"` (so khớp chính xác, phân biệt hoa thường): gọi `storage.update_pending_order_status(id, "rejected")`, in "Đã huỷ, không đặt lệnh.", exit 0.
6. Nếu `"YES"`:
   - Nếu `cfg.real_trading_enabled` là `False` (dry-run mode, mặc định):
     - In rõ: `f"[DRY-RUN] SẼ đặt lệnh: {side} {quantity} {symbol} @ {price} (account {account_no}) — real_trading_enabled=false nên KHÔNG gọi API thật."`
     - Gọi `storage.update_pending_order_status(id, "confirmed")` (không phải "placed" — chưa thật sự đặt).
     - Gọi `alert("INFO", "real order dry-run confirmed", id=id, symbol=symbol, side=side, qty=quantity, price=price)`.
     - Exit 0. **KHÔNG import/khởi tạo `AsyncAuth`/`AsyncTrading` ở nhánh này** — dry-run không cần kết nối SSI.
   - Nếu `cfg.real_trading_enabled` là `True`:
     - `auth = await ensure_authenticated(cfg, storage)` (import từ `trading.collector.ssi_auth`, dùng nguyên, không sửa).
     - `auth.config.private_key = cfg.ssi_private_key`.
     - `trading_client = AsyncTrading(auth)` (import `from ssi_sdk import AsyncTrading`).
     - Gọi `placed = await trading_client.trading.place_limit_order(account_no, symbol, OrderSide.BUY if side == "BUY" else OrderSide.SELL, quantity, price)`.
     - Nếu thành công: `storage.update_pending_order_status(id, "placed", ssi_order_id=placed.order_id)`, `storage.write_real_order_fill(account_no, datetime.now(TZ), symbol, side, quantity, price, fee=0.0, pnl=None, ssi_order_id=placed.order_id, status="placed")`, in rõ `order_id`/`client_request_id`/`status` trả về, gọi `alert("WARN", "REAL order placed", ...)`.
     - Nếu lỗi (exception từ SDK): `storage.update_pending_order_status(id, "failed")`, in traceback đầy đủ, `alert("CRITICAL", "real order placement FAILED", id=id, error=str(exc))`, **KHÔNG tự retry**, exit code khác 0.
     - Luôn `await auth.close()` trong `finally`.
7. **KHÔNG** thêm chức năng huỷ lệnh (`cancel_order`) vào script này — đó là thao tác riêng, ngoài phạm vi Phase 3 (nếu cần huỷ lệnh đã đặt thật, đó là 1 script/thao tác thủ công khác, chưa yêu cầu ở đây).

**Cập nhật `.gitignore`:** không cần — script này không ghi file output cục bộ nào (mọi thứ ghi vào DB).

---

## Kiểm chứng (KHÔNG chạy thật với credentials/tiền thật — đó là việc thủ công của user sau khi Claude audit xong)

1. Syntax + import hợp lệ (giống cách các script spike trước đã được verify):
```bash
uv run --with ssi-sdk python -c "
import ast
src = open('scripts/confirm_real_order.py', encoding='utf-8').read()
ast.parse(src)
print('OK: syntax hop le')
from ssi_sdk import AsyncTrading
from ssi_sdk.enums import OrderSide
print('OK: import cac symbol dung ton tai')
"
```
2. Viết `tests/test_confirm_real_order.py` — test các NHÁNH LOGIC bằng cách import hàm chính (tách logic thành 1 hàm `async def confirm(cfg, storage, order_id, confirm_input, place_order_fn=None) -> None` hoặc tương tự có thể test được — không bắt buộc CLI `main()` phải test được trực tiếp, nhưng logic nhánh dry-run/thật/rejected/expired phải tách ra hàm gọi được từ test, dùng fake `Storage`/fake auth giống style `tests/test_account_sync.py`):
   - `test_confirm_rejects_when_input_not_yes` — input khác "YES" → status thành "rejected", không gọi place_order.
   - `test_confirm_dry_run_does_not_call_place_order` — `real_trading_enabled=False`, input "YES" → status thành "confirmed", **fake place_order KHÔNG được gọi** (assert call count = 0).
   - `test_confirm_expired_order_does_nothing` — pending order có `expires_at` trong quá khứ → không hỏi input, không đổi status thêm (giữ nguyên hoặc để nguyên "pending", tuỳ cách bạn thiết kế — miễn nhất quán, ghi rõ trong docstring), không gọi place_order.
   - `test_confirm_real_mode_calls_place_order_and_saves_result` — `real_trading_enabled=True`, input "YES", fake `place_order` trả về response giả (order_id, status) → xác nhận `storage.update_pending_order_status` được gọi với `"placed"` + đúng `ssi_order_id`, `storage.write_real_order_fill` được gọi.
   - `test_confirm_real_mode_marks_failed_on_exception` — fake `place_order` raise exception → xác nhận status thành `"failed"`, không crash không rõ lý do (exception được bắt, log rõ).

Chạy `uv run pytest tests/test_confirm_real_order.py -v` — pass toàn bộ.

3. Chạy **toàn bộ suite**: `uv run pytest -v` (với `docker compose up -d postgres nats` nếu cần integration) — pass hết, không phá bất kỳ test nào khác.

4. `grep -n "place_limit_order\|cancel_order" scripts/confirm_real_order.py` — xác nhận `place_limit_order` chỉ xuất hiện đúng 1 lần (trong nhánh `real_trading_enabled=True`), `cancel_order` KHÔNG xuất hiện ở đâu cả (theo giới hạn phạm vi Task A bước 7).

---

## Báo cáo lại

1. Toàn bộ nội dung `scripts/confirm_real_order.py`.
2. Output `inspect.signature()` thật đã chạy ở bước "Trước khi viết" — xác nhận khớp/không khớp plan doc.
3. Output đầy đủ `uv run pytest -v` (toàn bộ suite).
4. Kết quả `gitnexus_detect_changes()`.
5. Kết quả `grep` xác nhận giới hạn `place_limit_order`/`cancel_order` như trên.

Không tự commit — chờ Claude audit.

---

## Phase 4 — Sau khi Phase 3 merge xong (KHÔNG phải code, việc của người dùng)

**Không giao cho agent coding.** Sau khi Phase 1-3 đã merge và audit xong:

1. Để `real_trading_enabled: false` (dry-run) chạy thật trong môi trường live **ít nhất 2 tuần giao dịch** — quan sát: tín hiệu có sinh ra hợp lý không, Telegram có báo đúng không, `pending_real_orders` có tự hết hạn (`expire_stale_pending_orders`) đúng như kỳ vọng không (cần thêm 1 cronjob/lời gọi định kỳ hàm này — **CHƯA có trong Phase 1-3**, sẽ cần 1 task nhỏ riêng nếu muốn tự động, hoặc chạy tay định kỳ).
2. **Trước khi bật `real_trading_enabled=true` lần đầu:** bắt buộc nạp thêm tiền vào tài khoản Cash `0434221` (đủ 1 lô mã rẻ, ví dụ mã <5,000đ/cp cần ~500,000đ) và chạy lại `scripts/spike_ssi_sdk_place_order.py` (Phase 0, đã có sẵn) để xác nhận nốt bước `place_limit_order`/`cancel_order` thật — **chưa từng được test thật tính đến thời điểm viết prompt này** (xem `PLAN_REAL_ORDER_PLACEMENT.md` mục "Kết quả Phase 0 thật").
3. Chỉ sau khi (1) và (2) đều xác nhận ổn, tự tay đổi `real_order_capital` trong `config/config.yaml` thành số dư thật hiện có, đổi `real_trading_enabled: true`, deploy lại engine.
4. Theo dõi sát trong vài phiên đầu tiên sau khi bật thật — không rời mắt khỏi Telegram/log trong giờ giao dịch.
