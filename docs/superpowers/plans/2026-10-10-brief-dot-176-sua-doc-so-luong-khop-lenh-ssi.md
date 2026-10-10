# Brief đợt 176 — Sửa đọc số lượng khớp trong lịch sử lệnh SSI (đối soát lệnh thật)

Ngày: 10/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.

## 0. Lỗi

Đợt 174 phát hiện, Claude kiểm bằng JSON thô ngày 10/10:
- API `/api/v3/trading/orderBook` trả mỗi lệnh với các khóa `avgPrice, cancelQty, clientRequestId, filledQty, inputTime, message, modifiedTime, orderId, orderStatus, orderType, price, quantity, side, symbol`.
- `ssi_sdk.models.portfolio.Order.from_dict` lại đọc `filledQuantity` và `cancelQuantity`, nên `filled_quantity` và `cancel_quantity` **luôn bằng 0**.
- Hệ quả: `trading/real_order_reconcile.py::decide_update` thấy `f == 0`. Mọi lệnh thật đã khớp (`orderStatus` FF) sẽ bị ghi thành **"cancelled", qty 0** trong `real_order_fills`.
- Hiện chưa gây hại vì bảng đang rỗng. Phải sửa trước khi có lệnh thật đầu tiên.
- Lý do test cũ không bắt được: chúng dựng `Order(...)` trực tiếp, không đi qua `from_dict`.

Thêm: SDK `get_historical_orders` chỉ gọi **một trang** (mặc định `pageSize` 1000). Mỗi lần gọi lấy từ ngày của dòng `placed` cũ nhất, nên hiện chưa chạm giới hạn. Vẫn sửa luôn bằng cách đi hết trang.

## 1. Việc làm

1. Thêm `trading/ssi_orders.py` gồm:
   - `order_from_raw(data: dict, account_no: str) -> Order`: chép `data`; nếu thiếu `filledQuantity` mà có `filledQty` thì gán `filledQuantity = filledQty`; tương tự `cancelQuantity` ← `cancelQty`. Sau đó gọi `Order.from_dict`. **Không** monkey-patch SDK.
   - `async fetch_order_history(portfolio, account_no, from_date, to_date, page_size=100) -> list[Order]`:
     - gọi `portfolio._rest.get(EP_ORDER_HISTORY, params={"accountNo", "from", "to", "pageIndex", "pageSize"})`, đi từ trang 1 tới khi đủ `totalRecord` hoặc trang rỗng;
     - parse từng lệnh bằng `order_from_raw`;
     - số lệnh lấy về khác `totalRecord` → `ValueError`.
   → **kiểm chứng bằng:** test 1–4 ở §3.
2. `trading/collector/account_sync.py::_reconcile_real_orders`: thay đúng một dòng `orders = await portfolio.get_historical_orders(...)` bằng `orders = await fetch_order_history(portfolio, account_no, from_date, to_date)`. Không đổi gì khác.
   → **kiểm chứng bằng:** test 5. Test 10–13 cũ của `tests/test_account_sync.py` vẫn xanh. Được sửa **chỉ phần mock** của chúng: thay mock `portfolio.get_historical_orders` bằng monkeypatch `account_sync.fetch_order_history`, trả cùng danh sách `Order`. Không đổi assert nào.
3. `scripts/report_real_account_performance.py` (đợt 174):
   - xóa khối monkey-patch `_compat_order_from_dict`/`Order.from_dict = ...`;
   - xóa `fetch_historical_orders_page` và `fetch_all_historical_orders`;
   - `run_report` gọi `fetch_order_history`.

   Trong `tests/test_report_real_account_performance.py`, test phân trang chuyển sang test 3 của file test mới; bỏ test cũ đó. Sáu test còn lại giữ nguyên.
   → **kiểm chứng bằng:** test còn lại xanh; `grep -n "Order.from_dict =" scripts trading` rỗng.

## 2. Phạm vi
- **Được thêm:** `trading/ssi_orders.py`, `tests/test_ssi_orders.py`.
- **Được sửa:**
  - `trading/collector/account_sync.py`: một dòng và một import;
  - `tests/test_account_sync.py`: chỉ phần mock của test 10–13 và test khác gọi `_reconcile_real_orders`, nếu có;
  - `scripts/report_real_account_performance.py`;
  - `tests/test_report_real_account_performance.py`.
- **Không sửa:** `trading/real_order_reconcile.py`, thư viện `ssi_sdk`, mọi file khác. Không gọi API thật trong test. Không ghi DB thật. Không rebuild hay restart container.
- **GitNexus:** gọi `gitnexus <lệnh> -r AI_auto_trading_system` hoặc `node .gitnexus/run.cjs <lệnh> --repo .`, **không `npx`**.
  - `impact _reconcile_real_orders --direction upstream` trước khi sửa; báo mức rủi ro.
  - `detect-changes --scope all` sau khi xong.

## 3. Kiểm chứng (TDD, client giả, không mạng)
Fixture là JSON **đúng các khóa ở §0**, số tài khoản giả `"0000000"`. Một lệnh FF (quantity 500, filledQty 500, avgPrice 58500), một lệnh FFPC (quantity 400, filledQty 92, cancelQty 308, avgPrice 27150), một lệnh CL (filledQty 0, cancelQty 100).
1. `order_from_raw`: FF → `filled_quantity == 500`, `status == OrderStatus.FILLED`; FFPC → 92 và 308; CL → 0 và 100.
2. Khóa kiểu cũ: dict có sẵn `filledQuantity` vẫn đọc đúng; không ghi đè khi có cả hai khóa.
3. Phân trang: `_rest` giả trả 3 trang (2+2+1, `totalRecord` 5) → đủ 5 lệnh; `params` từng lần gọi có `pageIndex` 1, 2, 3. `totalRecord` 6 mà chỉ có 5 → `ValueError`.
4. Không monkey-patch: sau khi import `trading.ssi_orders`, `Order.from_dict({"filledQty": 7, ...}, "x").filled_quantity == 0`. SDK không bị đổi; chỉ `order_from_raw` mới sửa.
5. **Đầu-cuối đối soát:** JSON FF ở fixture → `fetch_order_history` (với `_rest` giả) → `decide_update` với dòng `placed` cùng `orderId` (qty 500) → `Update.status == "filled"`, `qty == 500`, `price == 58500`. Với FFPC → filled, qty 92, đúng nhánh khớp một phần của `decide_update`.

Kiểm thử phá hoại: sao lưu file ra ngoài repo; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ.
- Bỏ ánh xạ `filledQty` → test 1 và test 5 đỏ.
- Chỉ lấy trang đầu → test 3 đỏ.
- Đổi `fetch_order_history` thành monkey-patch `Order.from_dict` toàn cục → test 4 đỏ.

```
uv run pytest tests/test_ssi_orders.py tests/test_account_sync.py tests/test_real_order_reconcile.py tests/test_report_real_account_performance.py tests/test_scripts_convention.py -v
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts
```

## 4. Hoàn thành khi
- Năm test mới xanh; ba bước phá hoại đỏ đúng test đã nêu.
- Test cũ xanh, không đổi assert. Dán số test trước/sau của toàn bộ bộ test.
- Ruff sạch. `detect-changes` chỉ gồm các file ở §2.
- Chạy lại thật **một lần** `uv run python scripts/report_real_account_performance.py --account 0434226 --from 2026-08-01`. Dòng (A) phải ra đúng như đợt 174: 31 lệnh, mua 274.946.500, bán 252.544.000, phí + thuế 1.729.517. Lệnh chỉ đọc.

## 5. Báo cáo cho Claude
Output pytest/ruff, bảng phá hoại, `impact`/`detect-changes`, diff `account_sync.py`, output chạy thật dòng (A), mọi chỗ phải tự diễn giải.
