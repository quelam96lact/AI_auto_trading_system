# Brief đợt 178 — Công cụ diễn tập đặt/hủy lệnh đọc đúng số lượng khớp và hủy

Ngày: 10/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.

## 0. Lỗi

`scripts/drill_place_cancel_order.py` (đợt 100), bước 10 (khoảng dòng 388–445):
- Công cụ đọc sổ lệnh bằng `portfolio.get_today_orders(account)` của SDK. SDK parse bằng `Order.from_dict`, mà hàm này đọc `filledQuantity`/`cancelQuantity`. API thật trả `filledQty`/`cancelQty` (đã kiểm bằng JSON thô ở đợt 174/176).
- Vì vậy `found.filled_quantity` và `found.cancel_quantity` **luôn bằng 0**. Hệ quả:
  - mọi lần diễn tập thật đều báo động giả "CHƯA XÁC NHẬN HUỶ ĐỦ 100 CỔ PHIẾU";
  - **nguy hiểm hơn:** nếu lệnh diễn tập lỡ khớp, công cụ **không** báo "LỆNH ĐÃ KHỚP".
- Đợt 176 đã có hàm đọc đúng: `trading/ssi_orders.py::fetch_order_history(portfolio, account_no, from_date, to_date)`. Hàm này gọi `portfolio._rest`, đi hết trang và ánh xạ `filledQty`/`cancelQty`.
- `trading_client.portfolio` thật là `AsyncPortfolioService` (`ssi_sdk/client.py:245`), có `_rest`, nên dùng được hàm đó.

## 1. Việc làm

1. Trong `run_drill`, bước 10:
   - thay `await portfolio.get_today_orders(account)` bằng `await fetch_order_history(portfolio, account, today, today)`, với `today = datetime.now(TZ).strftime("%Y/%m/%d")` (giờ VN; `TZ` từ `trading.calendar_vn`);
   - điều kiện vào vòng đọc đổi từ `portfolio is not None and hasattr(portfolio, "get_today_orders")` thành `portfolio is not None`.
   - Không đổi gì khác: số lần đọc, cách ghép `client_request_id`/`order_id`, ngưỡng báo, mã thoát, thông điệp.
   → **kiểm chứng bằng:** test 1–3 ở §3.
2. `tests/test_drill_place_cancel_order.py`: các test đang mock `portfolio.get_today_orders` chuyển sang monkeypatch `scripts.drill_place_cancel_order.fetch_order_history`, trả cùng danh sách. Assert `get_today_orders.call_count == 3` đổi thành assert số lần gọi mock mới == 3. **Không đổi assert nào khác.**
   → **kiểm chứng bằng:** mọi test cũ của file xanh.

## 2. Phạm vi
- **Được sửa:** `scripts/drill_place_cancel_order.py` (bước 10 và import), `tests/test_drill_place_cancel_order.py`.
- **Không sửa:** `trading/ssi_orders.py`, thư viện SDK, mọi file khác.
- **TUYỆT ĐỐI KHÔNG chạy công cụ với `--send`.** Không gửi lệnh thật. Không chạy công cụ trên tài khoản thật kể cả không có `--send`. Chỉ chạy test.
- **GitNexus:** gọi `gitnexus <lệnh> -r AI_auto_trading_system` hoặc `node .gitnexus/run.cjs`, **không `npx`**.
  - `impact run_drill --direction upstream` trước khi sửa;
  - `detect-changes --scope all` sau khi xong.

## 3. Kiểm chứng (TDD, không mạng)
Thêm vào `tests/test_drill_place_cancel_order.py`:
1. **Đầu-cuối với JSON thô:** `portfolio` giả có `_rest.get` trả
   `{"totalRecord": 1, "orderList": [{"orderId": "<id lệnh giả đã đặt>", "clientRequestId": "<id giả>", "orderStatus": "FFPC", "quantity": 100, "filledQty": 40, "cancelQty": 60, "avgPrice": 1000, "side": "B", "symbol": "VCB", "inputTime": "2026/10/12 10:00:00"}]}`.
   Gọi `run_drill` với `send=True`, các client giả như test hiện có, **không** monkeypatch `fetch_order_history` → CRITICAL, mã thoát 2, thông điệp chứa "ĐÃ KHỚP".
2. **Hủy đủ:** cùng cách, `orderStatus` "CL", `filledQty` 0, `cancelQty` 100 → mã thoát 0, không có CRITICAL.
3. **Ngày đúng giờ VN:** `params` gửi tới `_rest.get` có `from == to ==` ngày VN hôm nay theo `"%Y/%m/%d"`.

Kiểm thử phá hoại: sao lưu file ra ngoài repo; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ.
- Quay lại `portfolio.get_today_orders` → test 1 đỏ (với portfolio giả không có `get_today_orders` thì `found is None`, mã 1 thay vì 2).
- Ghi cứng ngày `"2026/01/01"` → test 3 đỏ.

```
uv run pytest tests/test_drill_place_cancel_order.py tests/test_ssi_orders.py tests/test_scripts_convention.py -v
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts
```

## 4. Hoàn thành khi
- Ba test mới xanh; hai bước phá hoại đỏ đúng test.
- Test cũ xanh, chỉ đổi phần mock và assert số lần gọi.
- Dán số test trước/sau. Ruff sạch. `detect-changes` chỉ gồm hai file ở §2.
- `grep -n "get_today_orders" scripts/drill_place_cancel_order.py` rỗng.

## 5. Báo cáo cho Claude
Output pytest/ruff, bảng phá hoại, `impact`/`detect-changes`, diff `scripts/drill_place_cancel_order.py`, mọi chỗ phải tự diễn giải.
