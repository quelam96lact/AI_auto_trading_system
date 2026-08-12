# Prompt thực thi: Fix #2 — kiểm tra lại sức mua/bán thật ngay trước khi đặt lệnh

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `PLAN_REAL_ORDER_PLACEMENT.md`, `scripts/confirm_real_order.py` hiện có.

---

## ⚠️ Bối cảnh

`pending_real_orders` có thể chờ xác nhận thủ công tới 15 phút (`PENDING_ORDER_TTL_MINUTES` trong `trading/real_orders.py`), dùng giá + số lượng chốt tại thời điểm sinh tín hiệu. `scripts/confirm_real_order.py` hiện tại đi thẳng từ "user gõ YES" → `place_limit_order()` — **không kiểm tra lại sức mua/bán thật ngay tại thời điểm đặt lệnh**, dù cơ chế này đã được chứng minh hoạt động đúng ở Phase 0 (`get_max_buy_sell_at_market_price` — xem `scripts/spike_ssi_sdk_place_order.py`) nhưng chưa từng đưa vào pipeline sản xuất.

**Fix:** ngay trước khi gọi `place_limit_order`, gọi `get_max_buy_sell_at_market_price(account_no, symbol)` — nếu sức mua/bán thật tại thời điểm đó không đủ so với số lượng lệnh, **DỪNG, không đặt lệnh**, đánh dấu `failed`, KHÔNG cố đặt lệnh biết trước sẽ sai.

---

## ⚠️ Giới hạn phạm vi

**Chỉ sửa 2 file:** `scripts/confirm_real_order.py`, `tests/test_confirm_real_order.py`.

**KHÔNG sửa:** `trading/real_orders.py`, `trading/storage/db.py`, `trading/engine/*`.

**Trước khi viết:** verify lại signature thật (đừng tin vào con số trong prompt này nếu nghi ngờ đã đổi):
```bash
uv run python -c "
import inspect
from ssi_sdk.services.trading import AsyncTradingService
print(inspect.signature(AsyncTradingService.get_max_buy_sell_at_market_price))
from ssi_sdk.models import MaxBuySellResponse
import dataclasses
print([f.name for f in dataclasses.fields(MaxBuySellResponse)])
"
```
Kỳ vọng: `get_max_buy_sell_at_market_price(account_no, symbol) -> MaxBuySellResponse`, fields gồm `account_no, symbol, max_buy_quantity, max_sell_quantity, margin_ratio, purchase_power`. **Lưu ý đã biết:** field `purchase_power` có bug field-mapping thật trong `ssi-sdk` (đọc sai key JSON, luôn rỗng) — **KHÔNG dùng field này cho bất kỳ logic nào**, chỉ dùng `max_buy_quantity`/`max_sell_quantity`.

**KHÔNG tự commit, không tự push.**

---

## Task A — Thêm bước kiểm tra trong `confirm()` (`scripts/confirm_real_order.py`)

Trong nhánh `real_trading_enabled=True`, **ngay sau** `trading_client = AsyncTrading(auth)` và **trước** khi gọi `place_limit_order`/`place_order_fn`:

```python
if max_buy_sell_fn is None:
    mbs = await trading_client.trading.get_max_buy_sell_at_market_price(
        order["account_no"], order["symbol"]
    )
else:
    mbs = await max_buy_sell_fn(order["account_no"], order["symbol"])

available = mbs.max_buy_quantity if order["side"] == "BUY" else mbs.max_sell_quantity
if available < order["quantity"]:
    print(
        f"!! DỪNG — sức {'mua' if order['side'] == 'BUY' else 'bán'} thật hiện tại "
        f"({available}) < số lượng lệnh ({order['quantity']}). KHÔNG đặt lệnh."
    )
    storage.update_pending_order_status(order_id, "failed")
    alert(
        "CRITICAL",
        "real order aborted - insufficient real buying/selling power at confirm time",
        id=order_id,
        symbol=order["symbol"],
        side=order["side"],
        requested_qty=order["quantity"],
        available_qty=available,
    )
    sys.exit(1)
```

Thêm tham số `max_buy_sell_fn=None` vào signature `confirm()` (cùng style với `place_order_fn=None` đã có — cho phép test inject fake, không cần mock sâu vào SDK):
```python
async def confirm(
    cfg: Config,
    storage: Storage,
    order_id: int,
    confirm_input: str,
    place_order_fn=None,
    max_buy_sell_fn=None,
) -> None:
```

**Không đổi gì khác trong nhánh dry-run** (nhánh này không gọi SSI, không cần check này).

## Task B — Cập nhật test

Trong `tests/test_confirm_real_order.py`:

1. **Sửa 2 test real-mode hiện có** (`test_confirm_real_mode_calls_place_order_and_saves_result`, `test_confirm_real_mode_marks_failed_on_exception`) — thêm `max_buy_sell_fn` giả trả về đủ sức mua/bán (vd `AsyncMock(return_value=MagicMock(max_buy_quantity=1000, max_sell_quantity=1000))`), truyền vào `confirm(...)`. Không đổi assertion cũ nào — chỉ đảm bảo các test này vẫn pass với bước check mới (giả lập "đủ sức mua/bán" để không chặn).

2. **Thêm 2 test mới:**
   - `test_confirm_real_mode_aborts_when_insufficient_buy_power` — `order["side"]="BUY"`, `max_buy_sell_fn` trả về `max_buy_quantity=50` (ít hơn `order["quantity"]=100`) → assert `SystemExit(1)`, `storage.update_pending_order_status` gọi với `(42, "failed")`, `place_order_fn` (fake) **KHÔNG được gọi**, `write_real_order_fill` không được gọi.
   - `test_confirm_real_mode_aborts_when_insufficient_sell_power` — tương tự với `pending_order["side"]="SELL"` (cần sửa fixture hoặc dùng `pending_order` biến thể), `max_buy_sell_fn` trả về `max_sell_quantity` nhỏ hơn số lượng lệnh → cùng assertion.

**Kiểm chứng:**
```bash
uv run pytest tests/test_confirm_real_order.py -v
```
Toàn bộ pass (2 test cũ sửa + 2 test mới = ít nhất 7 test trong file).

Chạy toàn bộ suite: `docker compose up -d postgres nats && uv run pytest -v` — pass hết.

`grep -n "place_limit_order\|cancel_order" scripts/confirm_real_order.py` — vẫn đúng 1 call site `place_limit_order`, không có `cancel_order`.

---

## Báo cáo lại

1. Diff đầy đủ 2 file.
2. Output `inspect.signature()` đã chạy ở bước "Trước khi viết".
3. Output đầy đủ `uv run pytest -v` (toàn bộ suite).
4. Kết quả `grep` xác nhận ranh giới an toàn.

Không tự commit — chờ Claude audit.
