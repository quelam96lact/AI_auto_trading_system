# Kế hoạch: nối trailing stop vào luồng lệnh thật

Ngày giao: 2026-08-13. Nhánh: `feature/data-layer`. Base: `1e801ec`.
KHÔNG commit, KHÔNG push. `gitnexus_impact` trước khi sửa symbol,
`gitnexus_detect_changes` khi xong.

Quyết định của chủ dự án ngày 2026-08-13 (xem `GO_LIVE_AUDIT.md`): nối trailing
stop vào luồng thật **trước** khi go-live.

## Điều phải hiểu đúng trước khi viết dòng nào

**Đây KHÔNG phải stop-loss tự động.** Kiến trúc hiện tại là người bấm nút:
`real_orders.handle_crossover()` chỉ ghi lệnh chờ + cảnh báo, việc đặt lệnh là
`scripts/confirm_real_order.py` chạy tay, phải gõ `YES` trong 15 phút. Cái ta
nối vào là **cảnh báo chạm stop**, sinh ra một lệnh SELL chờ xác nhận.

Đừng viết bất kỳ comment, docstring hay thông điệp alert nào ngụ ý rằng vị thế
sẽ được tự động cắt lỗ. Nếu người vận hành tin nhầm điều đó, tính năng này gây
hại nhiều hơn không có.

## Thiết kế đã chốt

### 1. Nơi móc vào: `trading/engine/main.py`, KHÔNG phải `logic.py`

`logic.py::process_bar` chỉ gọi `on_crossover` **khi có crossover**. Trailing
stop phải chạy **mỗi bar**. Đừng đổi chữ ký `process_bar` — nó đang được nhiều
test dùng và việc đó làm blast radius phình ra vô ích.

Thay vào đó, gọi ngay **sau** `process_bar(...)` trong vòng lặp message của
`main.py`. Ở đó đã có sẵn `bar`, `storage`, `cfg`, và `strategy.last_atr(...)`.

### 2. Instance riêng, không dùng chung với paper

Vị thế thật khác vị thế paper. Tạo `real_trailing_stop = TrailingStopManager()`
riêng, đặt cạnh `real_risk`.

### 3. Tái dựng lúc khởi động, cùng cách đã làm cho paper

Giống `read_highest_since_buy()` (`db.py`, thêm ở `7b5d6aa`) nhưng cho luồng
thật: đỉnh giá kể từ BUY fill gần nhất trong **`real_order_fills`** (không phải
`orders`), lọc theo `account_no`.

Vị thế thật có thể do chủ tài khoản tự mua ngoài hệ thống → không có
`real_order_fills` nào. Khi đó **không tái dựng được**: `alert("WARN")` nêu rõ
mã, đúng như đã làm ở `main.py` cho luồng paper. **Không im lặng.**

### 4. Khi chạm stop: bỏ qua halt lỗ ngày — có tiền lệ

`RiskManager.approve()` chặn cả SELL khi `halted_date == today`
(`risk.py:37-38` → `_halt_check`). Với một lệnh cắt lỗ thì điều đó nguy hiểm:
halt xảy ra vì đang lỗ, rồi chính nó khoá luôn đường thoát.

**Tiền lệ trong repo:** luồng paper đã bỏ qua risk cho stop-loss —
`logic.py:51-54`, nhánh `force_exit` chạy TRƯỚC và độc lập với
`risk.approve_sized()` ở nhánh `elif`.

Vậy: lệnh SELL do chạm stop **không đi qua `risk.approve()`**. Ghi rõ lý do này
vào comment ngay tại chỗ, kèm tham chiếu `logic.py:51-54`.

### 5. Số lượng bán bị chặn bởi T+2.5

Dùng `RealPosition.sellable_qty`, **không** dùng `qty`. Nếu `sellable_qty <= 0`
(chưa settle) thì không sinh lệnh được — **`alert("WARN")`** nêu rõ là vị thế
đã chạm stop nhưng chưa bán được vì chưa settle. Đây là thông tin người vận
hành thật sự cần, không được nuốt.

### 6. Không sinh lệnh trùng

Nếu đã có một pending order SELL còn hiệu lực cho cùng `account_no` + `symbol`,
đừng tạo thêm. Mỗi bar đều chạm stop sẽ đẻ ra một lệnh chờ mới nếu không chặn.
Kiểm tra trước khi tạo.

## Ràng buộc

- Sửa: `trading/real_orders.py`, `trading/engine/main.py`, `trading/storage/db.py`.
- **KHÔNG** sửa `trading/logic.py`, `trading/risk.py`, `trading/trailing_stop.py`,
  `config/config.yaml`, `GO_LIVE_AUDIT.md`.
- Giữ nguyên style hiện có (docstring tiếng Việt giải thích *tại sao*).
- Dùng `on_position_opened()` để nạp lại, không chọc thẳng vào `_highest`.

## Kiểm chứng (dán output THẬT)

1. **Test chạm stop sinh lệnh chờ SELL.** Vị thế thật có `sellable_qty > 0`,
   giá bứt lên rồi sụp xuống dưới `đỉnh - 2*ATR` → có pending SELL với đúng
   `sellable_qty`, và có alert.
2. **Test bỏ qua halt.** Cùng kịch bản nhưng `real_risk.halted_date = today`
   → **VẪN** sinh lệnh SELL. Đây là điểm dễ làm sai nhất.
3. **Test chưa settle.** `sellable_qty = 0` → không sinh lệnh, **có** alert WARN.
4. **Test không sinh trùng.** Hai bar liên tiếp đều chạm stop → chỉ **một**
   pending order.
5. **Test tái dựng lúc khởi động** + **test cảnh báo khi không tái dựng được**
   (không có `real_order_fills`).
6. **Sức phân biệt (BẮT BUỘC).** Với test số 2: tạm cho lệnh SELL đi qua
   `risk.approve()` → test đó phải FAIL. Khôi phục → PASS.
   Lý do bắt buộc: "bỏ qua halt" là một điều **không xảy ra**; test khẳng định
   sự vắng mặt của một rào chắn rất dễ pass một cách rỗng.
7. `uv run pytest -q` (kỳ vọng ≥ 248 + số test mới) + `uv run ruff check trading tests`.

## Nếu phát hiện thiết kế trên có chỗ sai

Dừng lại và báo cáo. Đặc biệt mục 4 (bỏ qua halt) — nếu bạn tìm được lý do
thuyết phục rằng lệnh cắt lỗ thật *nên* bị halt chặn, hãy nói ra trước khi
viết code. Tôi có thể sai.
