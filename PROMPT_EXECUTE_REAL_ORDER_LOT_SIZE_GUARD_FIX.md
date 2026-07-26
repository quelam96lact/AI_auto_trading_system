# Prompt thực thi: Fix #5 — kiểm tra lô tối thiểu (100 cp) cho lệnh BUY trước khi đặt

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `scripts/confirm_real_order.py` hiện có.

---

## ⚠️ Bối cảnh — phạm vi cố tình thu hẹp

Mức độ rủi ro thấp nhất trong 5 fix (SSI tự chặn nếu sai lô ở tầng sàn) — nhưng thêm 1 lớp defense-in-depth rẻ, không tốn công.

**CHỈ áp dụng cho lệnh BUY.** Lệnh **SELL không cần check này** — tài khoản có thể đang giữ lô lẻ (odd lot, vd còn dư 37 cổ phiếu sau nhiều lần khớp lệnh, hoặc từ thưởng cổ phiếu) và **được phép bán hết số lẻ đó**, không phải bội số 100. Áp lô tối thiểu cho SELL sẽ **chặn nhầm** giao dịch hợp lệ — không làm.

---

## ⚠️ Giới hạn phạm vi

**Chỉ sửa 2 file:** `scripts/confirm_real_order.py`, `tests/test_confirm_real_order.py`.

**KHÔNG sửa file nào khác.** Không thêm check biên độ giá (±7%) — quá phức tạp để làm đúng (khác nhau theo sàn HOSE/HNX/UPCoM, dự án hiện không có dữ liệu giá tham chiếu theo từng mã/sàn), rủi ro thấp vì SSI đã tự chặn — cố tình bỏ qua, không tự ý mở rộng phạm vi.

**KHÔNG tự commit, không tự push.**

---

## Task A — Thêm check trong `confirm()`

Trong `scripts/confirm_real_order.py`, ngay sau `_print_order(order)` và **trước** khi hỏi xác nhận `input()`/so khớp `"YES"` (áp dụng cho CẢ dry-run lẫn real-mode — đây là lỗi dữ liệu, phát hiện càng sớm càng tốt, không cần đợi tới lúc gọi SSI):

```python
if order["side"] == "BUY" and order["quantity"] % 100 != 0:
    print(
        f"!! Lỗi dữ liệu: lệnh BUY số lượng {order['quantity']} không phải bội số "
        f"100 (lô tối thiểu HOSE/HNX). Không xác nhận lệnh này — kiểm tra lại "
        f"trading/real_orders.py, có thể có bug ở nơi sinh pending order."
    )
    storage.update_pending_order_status(order_id, "failed")
    sys.exit(1)
```

(Không cần `alert()` — đây là lỗi dữ liệu nội bộ phát hiện sớm, không phải sự kiện vận hành cần cảnh báo khẩn.)

## Task B — Test

Thêm 1 test vào `tests/test_confirm_real_order.py`:
- `test_confirm_rejects_buy_with_invalid_lot_size` — sửa `pending_order["quantity"] = 137` (không phải bội số 100), `pending_order["side"] = "BUY"` → gọi `confirm(...)` → assert `SystemExit(1)`, `storage.update_pending_order_status` gọi với `(42, "failed")`.

**Đảm bảo KHÔNG thêm check này cho test SELL nào** — nếu có test SELL hiện có dùng quantity không phải bội 100 (không nên có, nhưng kiểm tra lại), test đó phải KHÔNG bị ảnh hưởng bởi check mới.

**Kiểm chứng:**
```bash
uv run pytest tests/test_confirm_real_order.py -v
```
Toàn bộ pass (test cũ + 1 test mới).

Chạy toàn bộ suite: `docker compose up -d postgres nats && uv run pytest -v` — pass hết.

---

## Báo cáo lại

1. Diff đầy đủ 2 file.
2. Output đầy đủ `uv run pytest -v`.

Không tự commit — chờ Claude audit.
