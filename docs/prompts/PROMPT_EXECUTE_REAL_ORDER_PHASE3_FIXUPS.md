# Prompt thực thi: Đặt lệnh thật — Phase 3 fixups (sau audit)

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `PROMPT_EXECUTE_REAL_ORDER_PHASE3.md` (prompt gốc đã thực thi) + `scripts/confirm_real_order.py` + `tests/test_confirm_real_order.py` (đã có, chưa commit).

Audit độc lập Phase 3 xác nhận implementation khớp đúng spec, không có bug chức năng. Prompt này chỉ sửa 3 điểm nhỏ audit tìm thấy — **không phải fix bug, không đổi hành vi runtime của `confirm()`**.

---

## ⚠️ Giới hạn phạm vi

**Chỉ sửa đúng 2 file:** `scripts/confirm_real_order.py` (chỉ thêm 1 comment, KHÔNG đổi logic) và `tests/test_confirm_real_order.py` (thêm docstring + assertion vào test đã có, KHÔNG tạo test mới, KHÔNG đổi cách gọi `confirm()`).

**KHÔNG:**
- Đổi thứ tự các bước trong `confirm()`, không refactor control flow.
- Thêm test mới ngoài 3 việc liệt kê dưới đây.
- Đụng vào bất kỳ file nào khác (Phase 1/2 files, `PLAN_REAL_ORDER_PLACEMENT.md`, v.v.).
- Di chuyển import `AsyncTrading`/`OrderSide` vào trong nhánh real — xem Task A, chỉ thêm comment, không restructure (lý do: các script khác trong dự án — vd `spike_ssi_sdk_place_order.py` — đều import symbol SDK ở đầu file bất kể nhánh nào chạy; import không có I/O nên đổi sang local-import sẽ chỉ tạo phong cách khác biệt không cần thiết so với phần còn lại của codebase).

**KHÔNG tự commit, không tự push.**

---

## Task A — Comment làm rõ import không có I/O (`scripts/confirm_real_order.py`)

Thêm 1 dòng comment ngay dưới 2 dòng import SDK ở đầu file:

```python
from ssi_sdk import AsyncTrading
from ssi_sdk.enums import OrderSide
# 2 import trên chỉ tham chiếu class/enum, không có I/O — dry-run (real_trading_enabled=false)
# không thực sự kết nối SSI dù các symbol này được import ở module level.
```

**Kiểm chứng:** `uv run python -c "import ast; ast.parse(open('scripts/confirm_real_order.py', encoding='utf-8').read()); print('OK')"`.

---

## Task B — Docstring cho `test_confirm_expired_order_does_nothing`

Thêm docstring giải thích quyết định thiết kế "để nguyên status khi order đã hết hạn" (không update thành 'expired' ở đây — việc đó là của `expire_stale_pending_orders()` chạy riêng, không phải trách nhiệm của `confirm_real_order.py`):

```python
async def test_confirm_expired_order_does_nothing(cfg, pending_order):
    """Order đã hết hạn (expires_at trong quá khứ) → confirm() không làm gì thêm,
    không tự đổi status. Việc đánh dấu 'expired' là trách nhiệm của
    Storage.expire_stale_pending_orders() (chạy định kỳ, ngoài phạm vi script này),
    không phải của confirm_real_order.py.
    """
    ...
```

(Giữ nguyên toàn bộ phần thân hàm, chỉ thêm docstring.)

---

## Task C — Assertion trên `alert(...)` cho 4 test đã có

Sửa **cùng 4 test hiện có** (không tạo test mới) trong `tests/test_confirm_real_order.py`, thêm assertion trên `mock_alert`:

1. `test_confirm_rejects_when_input_not_yes` — thêm cuối hàm:
   ```python
   mock_alert.assert_not_called()
   ```
   (nhánh reject hiện không gọi `alert()` — assert rõ điều này để nếu sau này có ai thêm `alert()` vào nhánh reject mà quên update test, test sẽ báo đỏ.)

2. `test_confirm_dry_run_does_not_call_place_order` — thêm:
   ```python
   mock_alert.assert_called_once()
   alert_args = mock_alert.call_args
   assert alert_args.args[0] == "INFO"
   assert alert_args.kwargs["id"] == 42
   assert alert_args.kwargs["symbol"] == "VCB"
   assert alert_args.kwargs["side"] == "BUY"
   assert alert_args.kwargs["qty"] == 100
   assert alert_args.kwargs["price"] == 50_000.0
   ```
   (Điều chỉnh cách lấy positional/keyword args cho khớp đúng cách `alert()` được gọi thật trong `confirm_real_order.py` — đọc lại source trước khi viết assertion, đừng đoán.)

3. `test_confirm_real_mode_calls_place_order_and_saves_result` — thêm:
   ```python
   mock_alert.assert_called_once()
   alert_args = mock_alert.call_args
   assert alert_args.args[0] == "WARN"
   assert alert_args.kwargs["ssi_order_id"] == "SSI-123"
   assert alert_args.kwargs["status"] == "MATCHED"
   ```

4. `test_confirm_real_mode_marks_failed_on_exception` — thêm:
   ```python
   mock_alert.assert_called_once()
   alert_args = mock_alert.call_args
   assert alert_args.args[0] == "CRITICAL"
   assert "SSI down" in alert_args.kwargs["error"]
   ```

Lưu ý: các test hiện dùng `with patch("scripts.confirm_real_order.alert") as ???` — kiểm tra xem `patch(...)` đã có biến `as mock_alert` chưa; nếu context manager hiện tại không gán biến (`with patch("scripts.confirm_real_order.alert"):`), sửa thành `with patch("scripts.confirm_real_order.alert") as mock_alert:` để lấy được mock object.

**Kiểm chứng:**
```bash
uv run pytest tests/test_confirm_real_order.py -v
```
Toàn bộ 5 test pass (4 test sửa assertion + 1 test chỉ thêm docstring).

Sau đó chạy **toàn bộ suite** (không chỉ file này — bài học đã ghi nhận nhiều lần trong dự án):
```bash
docker compose up -d postgres nats
uv run pytest -v
```
Pass hết (kỳ vọng 100 passed, khớp số lượng trước khi sửa — không thêm/bớt test nào).

---

## Báo cáo lại

1. Diff đầy đủ 2 file.
2. Output `uv run pytest tests/test_confirm_real_order.py -v` và `uv run pytest -v` (toàn bộ suite).
3. Xác nhận không có test nào bị xoá/thêm ngoài phạm vi (chỉ 4 test sửa assertion + 1 test thêm docstring).

Không tự commit — chờ Claude audit.
