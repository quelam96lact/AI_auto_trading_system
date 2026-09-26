# Brief đợt 103 — Đối soát lệnh thật: "đã đặt" không phải "đã khớp" (chuẩn bị T4)

Ngày giao: 26/09/2026 (thứ Bảy). Base: main `39c049e`.
Người giao, audit, commit, push: Claude. Người thực thi: agent. Agent **KHÔNG** commit, **KHÔNG** push.

## ⛔ Luật tối thượng
- **Không** đặt, huỷ hay sửa lệnh thật dưới mọi hình thức. **Không** bật `real_trading_enabled`.
- Được phép gọi **chỉ đọc** tới SSI (sổ lệnh trong ngày và lịch sử lệnh) để xác nhận tên trường, như đợt 100 đã làm.
- **Không** restart/build container. Việc dựng lại image do Claude làm **sau** khi commit (có sửa `trading/`).

---

## 0. Vấn đề

Sau T3 (đặt rồi huỷ, do chủ tài khoản làm), bước tiếp theo là **T4**: lệnh thật đi qua đường của hệ thống (`pending_real_orders` → `scripts/confirm_real_order.py`). Claude đọc đường này và thấy:

- `confirm_real_order.py:185-196` ghi một dòng vào `real_order_fills` với `status='placed'` **ngay khi đặt lệnh**, ở **giá đặt**, **đủ khối lượng**, và với lệnh BÁN thì kèm `pnl = (giá đặt − giá vốn) × khối lượng`.
- Schema đã có sẵn ba trạng thái `placed` / `cancelled` / `filled` (`schema.sql:201`). Hai nơi đọc quan trọng đã lọc bỏ `cancelled` qua `EFFECTIVE_FILL_STATUSES` (`db.py:25`):
  - `read_real_daily_pnl` (cầu dao lỗ trong ngày);
  - `read_real_highest_since_buy` (mốc trailing stop của vị thế thật).
- **Nhưng không có đoạn code nào chuyển `placed` sang `filled` hay `cancelled`.** Hệ quả:
  1. Lệnh BÁN **không khớp** (hoặc khớp một phần, hoặc khớp ở giá khác) vẫn bị cộng `pnl` như đã khớp. Cầu dao lỗ trong ngày có thể ngắt oan, hoặc không ngắt khi cần.
  2. Lệnh MUA **đã huỷ** vẫn được coi là "lần mua gần nhất", làm lệch mốc trailing stop.
  3. Tiêu chí 9 của cổng go-live ("Lịch sử lệnh thật đã khớp", `check_golive_gate.py:540`) đếm **mọi** dòng, tức đếm cả lệnh mới **đặt**.

Đợt 100 đã xác nhận SDK có `portfolio.get_today_orders(account)` và `portfolio.get_historical_orders(account, from, to)`, trả về `Order` có `order_id`, `client_request_id`, `status`, `filled_quantity`, `cancel_quantity`.

---

## 1. Trước khi sửa

- `gitnexus_impact` (upstream) cho `sync_account_data`, `write_real_order_fill`; `gitnexus_context` cho `read_real_daily_pnl`. Dán kết quả. HIGH hoặc CRITICAL thì **dừng**.
- **Đọc mã nguồn SDK, không đoán** (thư mục cài đặt `ssi_sdk`, model `Order`). Liệt kê trong báo cáo:
  (a) **mọi** trường của `Order`, đặc biệt trường **giá khớp trung bình** nếu có;
  (b) **mọi** giá trị có thể có của `Order.status` (enum hoặc hằng số), kèm vị trí file:dòng;
  (c) định dạng ngày mà `get_historical_orders` nhận.
- **Chạy một lần chỉ đọc** `get_today_orders("0434221")` và `get_historical_orders("0434221", <30 ngày trước>, <hôm nay>)`. Dán số lệnh trả về và tên các khoá của một phần tử, **không** dán dữ liệu cá nhân khác. Hôm nay là thứ Bảy nên sổ lệnh trong ngày nhiều khả năng rỗng; đó không phải lỗi.

Không tìm thấy trường giá khớp thì dùng **giá đặt** làm giá khớp, và ghi rõ đây là xấp xỉ.

---

## Task 1 — Hàm thuần quyết định cập nhật

Trong file mới `trading/real_order_reconcile.py`:

```python
def decide_update(row, order, terminal_statuses) -> Update | None
```

- `row`: một dòng `real_order_fills` có `status='placed'` (gồm `qty`, `price`, `side`, `fee`, `pnl`).
- `order`: `Order` tương ứng của SSI.
- Trả `None` nếu **chưa** cần cập nhật; ngược lại trả `Update(status, qty, price, fee, pnl)`.

Gọi `f = filled_quantity`, `c = cancel_quantity`, `q = row.qty`. Lệnh được coi là **đã kết thúc** khi `f + c ≥ q` **hoặc** `order.status` thuộc `terminal_statuses`, là tập **lấy từ mã nguồn SDK** ở §1(b); ghi file:dòng của từng giá trị trong docstring.

| Tình huống | Kết quả |
|---|---|
| Chưa kết thúc | `None`; giữ `placed` |
| Kết thúc, `f == q` | `filled`, `qty = q` |
| Kết thúc, `0 < f < q` | `filled`, `qty = f` (chỉ phần đã khớp) |
| Kết thúc, `f == 0` | `cancelled`, `fee = 0`, `pnl = 0` |

- **Giá khớp:** trường giá khớp trung bình của SDK nếu có và > 0; nếu không thì `row.price`.
- **Phí:** `fee = giá_khớp × qty_khớp × FEE_RATE_ESTIMATE`. **Import** hằng số từ nơi `confirm_real_order.py` đang dùng; **không** gõ 0,0025.
- **`pnl` của lệnh BÁN:** tính lại theo **giá vốn gốc**. Giá vốn không được lưu, nhưng suy ra được **chính xác** từ dòng gốc: `giá_vốn = row.price − row.pnl / row.qty`, vì `confirm_real_order.py:178` ghi `pnl = (giá đặt − giá vốn) × khối lượng`. Nên `pnl_mới = (giá_khớp − giá_vốn) × qty_khớp`. Nếu `row.pnl` là `None` thì giữ `None`.
- Lệnh MUA: `pnl` giữ `None`.

## Task 2 — Storage (chỉ **thêm** hàm, không sửa hàm có sẵn)

Trong `trading/storage/db.py`:
- `read_placed_real_fills(account_no) -> list[...]`: các dòng `status='placed'` của tài khoản, có `ssi_order_id`.
- `update_real_order_fill(id, status, qty, price, fee, pnl)`: cập nhật **một** dòng theo `id`, và **chỉ khi** trạng thái hiện tại vẫn là `placed` (`WHERE id = %s AND status = 'placed'`). Trả số dòng bị ảnh hưởng. Điều kiện này ngăn hai lần đối soát chồng nhau ghi đè.

## Task 3 — Gắn vào `account_sync`

Trong `trading/collector/account_sync.py`, thêm `_reconcile_real_orders(portfolio, account_no, storage)`, gọi **sau** `_sync_positions`, **bên trong** khối `try` cô lập từng tài khoản đang có (SYNC-1).
1. Không có dòng `placed` nào thì **không gọi SSI** (đa số chu kỳ rơi vào trường hợp này).
2. Có thì gọi `get_historical_orders(account_no, <ngày của dòng placed cũ nhất>, <hôm nay>)` một lần, rồi ghép theo `ssi_order_id == order.order_id`. Nếu định dạng hoặc hành vi của `get_historical_orders` không cho phép thì dùng `get_today_orders`, và ghi rõ trong báo cáo.
3. Mỗi cập nhật → `alert("INFO", ...)` nêu mã, trạng thái mới, số lượng khớp. Riêng **khớp một phần** → `WARN`.
4. Dòng `placed` có `ts` cách hiện tại **quá 1 ngày giao dịch** (dùng `trading_days_between` của `calendar_vn`) mà **không** tìm thấy lệnh trong SSI → `alert("CRITICAL", "lệnh thật không rõ trạng thái — kiểm tra iBoard", ...)`. Khử trùng lặp **một lần mỗi dòng mỗi ngày** theo cách sẵn có trong module; nếu module chưa có cơ chế khử trùng lặp nào thì **dừng và báo** trước khi tự chế.

## Task 4 — Cổng go-live đếm đúng

Trong `scripts/check_golive_gate.py`: tiêu chí 9 đếm `status = 'filled'`, không đếm mọi dòng. Ghi chú hiển thị thêm số `placed` và `cancelled` để người đọc thấy đủ.
Trong `scripts/check_real_order_readiness.py` (chỉ phần hiển thị): in số dòng theo **từng** trạng thái thay vì một tổng.

**Không được sửa:** `confirm_real_order.py`, `real_orders.py`, `read_real_daily_pnl`, `read_real_highest_since_buy`, `EFFECTIVE_FILL_STATUSES`, schema.

---

## 2. Kiểm chứng (TDD: viết test trước, thấy đỏ, rồi mới sửa)

### 2.1 `decide_update`, tính tay
1. Lệnh chưa kết thúc (`f=0, c=0`, status không thuộc tập kết thúc) → `None`.
2. MUA 100 @10.000, khớp 100 → `filled`, `qty=100`, `fee = 10.000 × 100 × FEE_RATE_ESTIMATE`.
3. BÁN 100 @12.000, `row.pnl = 200.000` (tức giá vốn 10.000), khớp 40, huỷ 60, **giá khớp** 11.900 → `filled`, `qty=40`, `pnl = (11.900 − 10.000) × 40 = 76.000`. Tính tay trong docstring.
4. `f=0, c=100` → `cancelled`, `fee=0`, `pnl=0`.
5. `f=0, c=0` nhưng status thuộc tập kết thúc (ví dụ bị từ chối) → `cancelled`.
6. Không có trường giá khớp → dùng `row.price`.
7. `row.pnl = None` với lệnh BÁN → `pnl` giữ `None`, không nổ.

### 2.2 Storage (integration, `TEST_DSN`, nhãn `integration`)
8. `update_real_order_fill` trên dòng đã `filled` → **0** dòng bị ảnh hưởng, dữ liệu không đổi.
9. Sau khi một dòng BÁN chuyển `cancelled`, `read_real_daily_pnl` của ngày đó **không** còn tính `pnl` của nó. Test này **dùng hàm có sẵn**, không sửa hàm.

### 2.3 Gắn vào `account_sync` (dùng `portfolio` giả)
10. Không có dòng `placed` → `get_historical_orders` và `get_today_orders` được gọi **0** lần.
11. Có 2 dòng `placed` → SSI được gọi **1** lần; mỗi dòng được cập nhật theo lệnh tương ứng.
12. SSI ném lỗi → tài khoản đó bị bỏ qua với `WARN` như hiện nay, **tài khoản kia vẫn đồng bộ bình thường**.
13. Dòng `placed` quá 1 ngày giao dịch không có trong SSI → **đúng 1** `CRITICAL` trong ngày dù hàm chạy nhiều lần.

### 2.4 Cổng
14. Bảng có 1 `filled`, 2 `placed`, 1 `cancelled` → tiêu chí 9 báo **1**.

### 2.5 Kiểm thử phá hoại (bắt buộc)
Sao lưu **ra ngoài repo**. **Cấm** `git checkout`, `git restore`, `git stash`.
- Bỏ điều kiện `AND status = 'placed'` trong `update_real_order_fill` → test 8 đỏ.
- Tính `pnl` mới bằng giá đặt thay cho giá khớp → test 3 đỏ.
- Luôn gọi SSI kể cả khi không có dòng `placed` → test 10 đỏ.
- Bỏ khử trùng lặp CRITICAL → test 13 đỏ.
- Cổng đếm mọi dòng → test 14 đỏ.
- Khôi phục, chạy lại, sạch. Báo tên test đỏ từng bước.

### 2.6 Tổng
```
uv run pytest -m "not integration" -q     # mốc: 1040 passed
uv run pytest tests/test_storage_engine.py -m integration -q
uv run ruff check trading tests scripts
```
Sau khi sửa: `gitnexus_detect_changes()`.

---

## 3. Báo cáo cho Claude

1. GitNexus impact/context và detect_changes.
2. §1: các trường của `Order`, các giá trị `status` (file:dòng), định dạng ngày, và kết quả của lần gọi chỉ đọc.
3. Diff từng file; test; kiểm thử phá hoại (tên test đỏ từng bước).
4. Pytest (unit và integration) và ruff.
5. **Xác nhận một câu:** "Tôi không đặt, huỷ hay sửa lệnh thật nào."
6. Mọi điều ngoài phạm vi: **báo cáo, không sửa.**
