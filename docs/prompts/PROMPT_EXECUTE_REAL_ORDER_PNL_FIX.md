# Prompt thực thi: Fix — tính `pnl` thật khi ghi `real_order_fills` (circuit breaker ngắt lỗ ngày không bao giờ kích hoạt)

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `PLAN_REAL_ORDER_PLACEMENT.md`, `scripts/confirm_real_order.py`,
`trading/storage/db.py::read_real_positions`/`write_real_order_fill`/`read_real_daily_pnl`.

---

## ⚠️ Bối cảnh — vì sao đây là fix nghiêm trọng nhất từ trước đến nay

Audit định kỳ toàn bộ pipeline lệnh thật phát hiện: `scripts/confirm_real_order.py`
luôn gọi `storage.write_real_order_fill(..., pnl=None, ...)` sau khi đặt lệnh thật
thành công — **không nơi nào khác trong codebase từng ghi giá trị `pnl` thật** vào
bảng `real_order_fills` (đã grep xác nhận). `real_orders.handle_crossover()` gọi
`storage.read_real_daily_pnl(cfg.real_order_account, today)` để tính `daily_pnl`
truyền vào `RiskManager.approve()` — hàm này `SUM(pnl)` từ `real_order_fills`, luôn
trả về `0.0` vì mọi dòng đều có `pnl IS NULL`.

**Hậu quả:** `RiskManager.approve()` chỉ set `halted_date` (ngắt giao dịch cả ngày)
khi `daily_pnl <= -capital * max_daily_loss_pct` — với `daily_pnl` luôn `0.0`, điều
kiện này **không bao giờ đúng**. Circuit breaker ngắt lỗ ngày cho tiền thật — cơ chế
bảo vệ quan trọng nhất trong toàn bộ tính năng — **về cấu trúc chưa từng có khả năng
kích hoạt**, kể cả sau khi Fix persist `halted_date` (đã merge trước đó) đã đúng.

**Vì sao lọt qua mọi audit trước:** mọi test hiện có (`tests/test_real_orders.py`,
`tests/test_engine_main.py`) đều mock `storage.read_real_daily_pnl.return_value =
0.0` cố định — chưa từng test với giá trị pnl thật khác 0, nên phần "không ai từng
ghi pnl thật vào DB" chưa bao giờ bị lộ ra qua test.

**Quyết định đã chốt với người dùng:** tính `pnl` tại `confirm_real_order.py` khi
SELL, dùng `avg_price` thật từ `RealPosition` (qua `storage.read_real_positions`)
so với giá lệnh — `pnl = (price - avg_price) * qty`, giống cách `PaperBroker` tính
realized PnL. Lệnh BUY vẫn `pnl=None` (chưa hiện thực hoá lãi/lỗ khi mua).

---

## ⚠️ Giới hạn phạm vi

**Chỉ sửa 2 file:** `scripts/confirm_real_order.py`, `tests/test_confirm_real_order.py`.

**KHÔNG sửa:** `trading/real_orders.py`, `trading/storage/db.py`, `trading/risk.py`,
`trading/engine/*`. Không đổi signature `write_real_order_fill`/`read_real_daily_pnl`
— các hàm này đã đúng, vấn đề chỉ ở chỗ gọi.

**KHÔNG fix `fee=0.0` hardcode trong cùng prompt này** (vấn đề nhỏ hơn, riêng biệt —
`place_limit_order`/`PlaceOrderResponse` không trả về phí thật theo field đã xác
nhận trước đó (`order_id, client_request_id, status`), cần điều tra API khác để lấy
phí thật — ngoài phạm vi prompt này, để lại làm fix riêng sau).

**KHÔNG tự commit, không tự push.**

---

## Task A — Tính `pnl` thật trong `confirm()` (`scripts/confirm_real_order.py`)

Ngay sau khi đặt lệnh thành công (`placed = await ...place_limit_order(...)` hoặc
`place_order_fn(...)`), **trước** khi gọi `storage.write_real_order_fill(...)`, thêm:

```python
pnl = None
if order["side"] == "SELL":
    positions = storage.read_real_positions(order["account_no"])
    real_pos = positions.get(order["symbol"])
    if real_pos is not None:
        pnl = (order["price"] - real_pos.avg_price) * order["quantity"]
```

Sau đó sửa lời gọi `storage.write_real_order_fill(...)` — đổi `pnl=None,` (đang
hardcode) thành `pnl=pnl,` (biến vừa tính).

**Lưu ý:** `order["price"]` là giá đặt lệnh (limit price) đã lưu từ lúc sinh pending
order — dùng làm giá khớp gần đúng, giống cách `write_real_order_fill(... price=order["price"] ...)`
hiện tại đã làm (không có field giá khớp thật từ `PlaceOrderResponse`, đây là giới
hạn đã biết, không phải bug mới). Nếu `real_pos is None` (vị thế không tồn tại tại
thời điểm confirm — có thể do race condition giữa lúc sinh signal và lúc user xác
nhận), giữ `pnl=None` — không đoán, không tính sai.

## Task B — Test (`tests/test_confirm_real_order.py`)

Thêm 1 test mới, đặt cạnh các test real-mode hiện có:

- `test_confirm_real_mode_computes_pnl_on_sell` — dựng `pending_order["side"] =
  "SELL"`, `pending_order["price"] = 55_000.0`, `pending_order["quantity"] = 100`.
  Mock `storage.read_real_positions` trả về `{"VCB": RealPosition("VCB", 100,
  50_000.0, 100)}` (avg_price=50_000). Gọi `confirm(...)` với `max_buy_sell_fn` giả
  trả về đủ sức bán (như các test real-mode khác đã làm). Assert
  `storage.write_real_order_fill` được gọi với `pnl=500_000.0` (= (55_000 - 50_000)
  * 100) — dùng `storage.write_real_order_fill.call_args.kwargs["pnl"]` để assert
  chính xác giá trị, không assert lỏng lẻo.

**Sửa 1 test hiện có** để không bị breaking do thêm lệnh gọi `read_real_positions`
mới: `test_confirm_real_mode_calls_place_order_and_saves_result` (test BUY hiện có)
— test này KHÔNG vào nhánh `if order["side"] == "SELL"` nên không cần
`storage.read_real_positions` — không cần sửa gì nếu `storage` là `MagicMock()` (tự
trả `MagicMock()` cho mọi method chưa định nghĩa, không lỗi). Chỉ cần xác nhận lại
test này vẫn assert `write_real_order_fill` gọi với `pnl=None` (giữ nguyên hành vi
BUY) — nếu assertion cũ chưa kiểm tra `pnl`, thêm `assert
storage.write_real_order_fill.call_args.kwargs["pnl"] is None` để khẳng định rõ BUY
không đổi hành vi.

**Kiểm chứng:**
```bash
uv run pytest tests/test_confirm_real_order.py -v
```
Toàn bộ pass (test cũ + 1 test mới).

Chạy toàn bộ suite: `docker compose up -d postgres nats && uv run pytest -v` — pass hết.

`grep -n "cancel_order" scripts/confirm_real_order.py` — vẫn rỗng (không đổi phạm vi này).

---

## Báo cáo lại

1. Diff đầy đủ 2 file.
2. Output đầy đủ `uv run pytest -v` (toàn bộ suite) — nêu rõ số lượng test trước/sau.
3. Xác nhận test BUY hiện có vẫn `pnl=None`, test SELL mới đúng `pnl=500_000.0`.

Không tự commit — chờ Claude audit.
