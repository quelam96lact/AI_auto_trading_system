# Prompt thực thi: Fix 2 vấn đề nhỏ còn lại từ audit định kỳ — ước tính `fee` thật + wiring `expire_stale_pending_orders()`

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `PLAN_REAL_ORDER_PLACEMENT.md`, `scripts/confirm_real_order.py`,
`trading/engine/main.py`, `trading/storage/db.py::expire_stale_pending_orders`.

2 vấn đề **độc lập nhau, không liên quan gì nhau** — làm rõ ranh giới file để agent
không nhầm lẫn giữa 2 task.

---

## Task A — Ước tính `fee` thật khi ghi `real_order_fills` (`scripts/confirm_real_order.py`)

### Bối cảnh
Đã xác nhận (audit trước): `PlaceOrderResponse` (`order_id, client_request_id,
status`) và `Order` (từ `get_today_orders`/`get_historical_orders`) **không có
field phí per-order**. Chỉ có `EquityPPMMR.fees` — tổng phí luỹ kế cấp tài khoản,
không tách theo từng lệnh. **Không có cách lấy phí thật cho 1 lệnh cụ thể từ SDK.**

**Quyết định đã chốt với người dùng:** ước tính bằng tỷ lệ phí cố định **0.15%**
giá trị lệnh (biểu phí môi giới thật của tài khoản người dùng) — đây là **ước
lượng, KHÔNG phải số thật từ SSI** — phải ghi rõ trong code đây là estimate, không
phải giá trị chính xác, để người đọc sau không hiểu nhầm.

### Giới hạn phạm vi
**Chỉ sửa 2 file:** `scripts/confirm_real_order.py`, `tests/test_confirm_real_order.py`.
**KHÔNG sửa** `trading/real_orders.py`, `trading/storage/db.py`, `trading/risk.py`.
Áp dụng cho **cả BUY và SELL** (phí môi giới VN áp cho cả 2 chiều, khác thuế bán
0.1% chỉ áp SELL — KHÔNG làm thuế bán trong prompt này, chỉ phí môi giới, phạm vi
hẹp có chủ đích).

### Thực hiện
Thêm hằng số ở đầu file (cạnh các import, trước `def _print_order`):
```python
FEE_RATE_ESTIMATE = 0.0015  # 0.15% giá trị lệnh — ƯỚC TÍNH theo biểu phí môi giới
# đã ký của tài khoản, KHÔNG PHẢI phí thật từ SSI. SDK hiện không có field phí
# per-order (PlaceOrderResponse/Order chỉ có id/status/giá/số lượng, EquityPPMMR.fees
# chỉ là tổng luỹ kế cấp tài khoản) — xem PLAN_REAL_ORDER_PLACEMENT.md.
```

Trong `confirm()`, thay dòng `fee=0.0,` (trong lời gọi `storage.write_real_order_fill`)
bằng:
```python
fee=order["price"] * order["quantity"] * FEE_RATE_ESTIMATE,
```
(Đặt tính toán trước lời gọi `write_real_order_fill`, giống cách biến `pnl` đã tính
ở fix trước — không đổi cấu trúc gì khác trong hàm.)

### Test
Thêm assertion vào **2 test real-mode hiện có** (không tạo test trùng lặp):
- `test_confirm_real_mode_calls_place_order_and_saves_result` (BUY, quantity=100,
  price=50_000.0) — thêm `assert args["fee"] == 100 * 50_000.0 * 0.0015` (=
  `7_500.0`).
- `test_confirm_real_mode_computes_pnl_on_sell` (SELL, quantity=100, price=55_000.0)
  — thêm `assert args["fee"] == 100 * 55_000.0 * 0.0015` (= `8_250.0`).

**Kiểm chứng:** `uv run pytest tests/test_confirm_real_order.py -v` — toàn bộ pass
(không thêm/bớt số lượng test, chỉ thêm assertion).

---

## Task B — Wiring `expire_stale_pending_orders()` vào engine loop (`trading/engine/main.py`)

### Bối cảnh
`Storage.expire_stale_pending_orders()` đã viết, có unit test riêng
(`tests/test_storage.py::test_expire_stale_pending_orders`), nhưng **không nơi nào
trong `trading/`/`scripts/` gọi nó** (đã grep xác nhận) — lệnh chờ xác nhận (`pending_real_orders`)
mà không ai xác nhận/từ chối trong `PENDING_ORDER_TTL_MINUTES` (15 phút) sẽ nằm mãi
ở `status='pending'` trong DB, dù `confirm_real_order.py` đã tự kiểm tra hết hạn khi
có ai đó cố xác nhận muộn (không phải lỗi an toàn, chỉ là rác dữ liệu tích tụ).

### Giới hạn phạm vi
**Chỉ sửa 2 file:** `trading/engine/main.py`, `tests/test_engine_main.py`.
**KHÔNG sửa** `trading/storage/db.py` (hàm đã đúng, chỉ thiếu chỗ gọi),
`trading/real_orders.py`, `scripts/confirm_real_order.py`.

### Thực hiện
Trong `run()`, thêm 1 hàm cục bộ cạnh `persist_fills`/`on_real_crossover`:
```python
def expire_stale_real_orders() -> None:
    n = storage.expire_stale_pending_orders()
    if n > 0:
        alert("WARN", "real pending orders expired without confirmation", count=n)
```

Gọi `expire_stale_real_orders()` ở **2 chỗ** trong vòng lặp chính (ngay cạnh mỗi
lời gọi `storage.beat("engine")` đã có — không thay thế, gọi thêm):
1. Trong nhánh `except nats.errors.TimeoutError:` (cạnh `storage.beat("engine")`).
2. Sau khi xử lý xong 1 bar, cạnh `storage.beat("engine")` ở cuối vòng lặp (dòng
   `await msg.ack()` / `storage.beat("engine")` / `processed += 1`).

(Gọi ở cả 2 chỗ để việc dọn dẹp không phụ thuộc có bar mới đến hay không — nhưng
chỉ cần viết test cho nhánh xử lý bar bình thường, vì test timeout thật (chờ NATS
60s) tốn thời gian không cần thiết cho việc này.)

### Test
Thêm 1 test mới vào `tests/test_engine_main.py` (đọc file trước để khớp style
fixture `storage`/`make_cfg`/`make_bars`/`_publish` đã có):
- `test_engine_run_expires_stale_pending_real_order` — dùng `storage` fixture thật
  (Postgres), gọi `storage.create_pending_order(...)` tạo 1 pending order với
  `expires_at` **trong quá khứ** (vd `datetime.now(TZ) - timedelta(minutes=1)`),
  publish 1 bar bình thường, chạy `run(cfg, max_messages=1)`, sau đó
  `storage.get_pending_order(order_id)["status"] == "expired"`.

**Kiểm chứng:**
```bash
uv run pytest tests/test_engine_main.py -v
```
Toàn bộ pass (test cũ + 1 test mới).

---

## Điều kiện chung cho cả 2 task

Chạy **toàn bộ suite** (không chỉ 2 file test đã sửa):
```bash
docker compose up -d postgres nats
uv run pytest -v
```
Pass hết (kỳ vọng 119 passed — 117 hiện tại + 1 test Task A [assertion thêm vào
test cũ, không tăng số lượng] + 1 test Task B mới = 118... **lưu ý: Task A CHỈ
thêm assertion vào test đã có, KHÔNG tăng số lượng test; Task B thêm đúng 1 test
mới** — báo cáo lại số lượng test thật sự sau khi chạy, đừng cố khớp con số dự đoán
nếu thực tế khác).

`grep -n "cancel_order" scripts/confirm_real_order.py` — vẫn rỗng.

---

## Báo cáo lại

1. Diff đầy đủ 4 file (2 file Task A + 2 file Task B).
2. Output đầy đủ `uv run pytest -v` (toàn bộ suite).
3. Xác nhận rõ ràng: Task A có đúng là "chỉ thêm assertion, không thêm test mới"
   không; Task B thêm đúng 1 test mới.

Không tự commit — chờ Claude audit.
