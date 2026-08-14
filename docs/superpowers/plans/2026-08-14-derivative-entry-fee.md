# Kế hoạch: phí mở vị thế bị bỏ sót trong PnL phái sinh

Ngày giao: 2026-08-14 tối. Nhánh: `feature/data-layer`. Base: `f0e68aa`.

**KHÔNG commit, KHÔNG push.**

Đây là việc bạn tự phát hiện và báo cáo (đúng cách) trong FEE-ALARM-1. Chủ dự án
đã quyết: làm.

---

## BỐI CẢNH — vì sao việc này ít rủi ro hơn bản cổ phiếu

`DerivativePaperBroker` **KHÔNG chạy trong sản xuất**. Không có service phái sinh
trong `docker-compose.yml`; chỉ `derivative_backtest.py` và vài script spike dùng
nó. `db.save_derivative_positions` là ảnh chụp tài khoản phái sinh THẬT đồng bộ
từ SSI — thứ khác hẳn, không phải trạng thái của broker này.

Hệ quả: **không có đường `restore`, không cần di trú dữ liệu.** Thứ đổi là kết
quả backtest phái sinh.

- **KHÔNG** đụng dữ liệu phái sinh trong DB. Mã `41I1G8000` trong `bars` giữ nguyên.
- **KHÔNG** restart/rebuild container nào.
- **KHÔNG** đụng `config/config.yaml`, **KHÔNG** bật `real_trading_enabled`.

---

# Lỗi

`trading/derivative_position.py`:

```python
open_long / open_short:
    fee = qty * self.fee_per_contract
    pos.avg_price = price          # phí KHÔNG vào đâu cả
    self.cash -= fee               # cash CÓ trừ

close:
    pnl = (price - pos.avg_price) * qty * multiplier - fee   # chỉ trừ phí ĐÓNG
    self.realized_pnl += pnl
    self.cash += pnl
```

Một vòng trọn vẹn:

```
cash        = -phi_mo + gross - phi_dong      ĐÚNG
realized_pnl =          gross - phi_dong      THIẾU phi_mo
```

Cùng hạng lỗi với `6664cd9`: sai **một chiều**, luôn báo lỗ nhẹ hơn thực tế.

# Cách sửa — KHÁC bản cổ phiếu, đọc kỹ lý do

Bên cổ phiếu tôi gộp phí vào `avg_price`. **Ở đây làm thế là SAI.**

`derivative_backtest.py:72` đọc `avg_price` làm **giá vào lệnh để tính cắt lỗ /
chốt lãi theo điểm**:

```python
entry = broker.positions[bar.symbol].avg_price
if bar.low <= entry - stop_loss_points: ...
```

Gộp phí vào đó sẽ **dịch ngưỡng cắt lỗ và chốt lãi** — đổi hành vi giao dịch chứ
không chỉ kế toán. Bên cổ phiếu không ai đọc `avg_price` với nghĩa giá khớp nên
gộp được; ở đây thì có.

Ngoài ra `avg_price` là **điểm chỉ số**, còn phí là **VNĐ** — gộp thẳng còn sai
đơn vị.

## Thiết kế đã chốt: lưu phí mở riêng trên vị thế

1. `DerivativePosition` thêm một trường, ví dụ `open_fee: float = 0.0`.
2. `open_long` / `open_short`: gán `pos.open_fee = fee`. Giữ nguyên
   `self.cash -= fee` (cash đang đúng, đừng đụng).
3. `close`:

```python
pnl = (...) * multiplier - fee - pos.open_fee   # trừ CẢ HAI đầu
self.realized_pnl += pnl
self.cash += (...) * multiplier - fee           # phi_mo đã trừ lúc mở, KHÔNG trừ lại
pos.open_fee = 0.0                              # dọn cùng chỗ với qty/avg_price
```

Kiểm lại số học: cash ròng = `-phi_mo + gross - phi_dong`, không đổi so với trước.
`realized_pnl` = `gross - phi_dong - phi_mo`. Hai sổ khớp nhau khi phẳng.

`avg_price` **giữ nguyên nghĩa "giá khớp"** — cắt lỗ/chốt lãi không dịch một điểm nào.

## Phần 2 (nhỏ): `_unrealized` cũng thiếu phí mở

`derivative_backtest.py:22-32` tính lãi/lỗ chưa thực hiện thuần theo điểm, không
trừ phí đã trả để vào lệnh — cùng thiếu sót mà bản cổ phiếu đã sửa
(`unrealized_pnl` giờ phản ánh phí vào lệnh).

Trừ `pos.open_fee` cho mỗi vị thế đang mở.

**Nếu bạn cho rằng phần 2 nên tách riêng vì nó đổi đường cong vốn của backtest
theo cách khó so sánh với kết quả cũ — nói ra.** Tôi cho là nên làm cùng lúc để
hai đại lượng nhất quán, nhưng đây là chỗ tôi có thể sai.

---

# Phạm vi

- **Được sửa:** `trading/derivative_position.py`, `trading/derivative_backtest.py`
  (chỉ hàm `_unrealized`), test tương ứng.
- **KHÔNG đụng:** `trading/paper_broker.py` (đã xong ở `6664cd9`),
  `trading/broker.py`, `trading/collector/derivative_sync.py`,
  `trading/storage/db.py`, `scripts/`, `config/config.yaml`.
- **KHÔNG** đổi logic cắt lỗ/chốt lãi, **KHÔNG** đổi `avg_price`.
- `gitnexus_impact` trên `DerivativePaperBroker.close` trước khi sửa, dán blast radius.

# Kiểm chứng — dán output THẬT

1. **RED bắt buộc, LONG:** mở long rồi đóng, khẳng định
   `cash - capital == realized_pnl`. Phải ĐỎ trên code hiện tại, lệch **đúng bằng
   phí mở**. Sửa → xanh.
2. **RED bắt buộc, SHORT:** cùng thế cho `open_short`. Nhánh short có công thức
   PnL riêng (`avg_price - price`) — một bản sửa chỉ đúng nhánh long là chưa xong.
3. **Cắt lỗ/chốt lãi KHÔNG dịch:** dựng một ca chạm cắt lỗ sát ngưỡng, chạy
   `run_derivative_backtest` trước và sau bản sửa → **giá thoát và thời điểm thoát
   y hệt**. Đây là ca quan trọng nhất: nó chứng minh bạn không vô tình đổi hành vi
   giao dịch. Dán số cả hai lần.
4. `_unrealized` phản ánh phí mở: mở vị thế, mark **bằng đúng giá vào** →
   `_unrealized` phải **âm** đúng bằng phí mở, không phải 0.
5. Nhiều vòng liên tiếp: `open_fee` được dọn sạch sau `close`, không rò sang vòng
   sau (mở → đóng → mở → đóng, `realized_pnl` = tổng đúng của hai vòng).
6. Toàn bộ suite + `ruff check trading tests` sạch. **Nếu một test cũ chuyển đỏ:
   DỪNG và báo cáo. Không sửa kỳ vọng của test cũ cho qua.**
7. Chạy lại backtest phái sinh đang có (nếu repo có cấu hình chuẩn), báo cáo
   **cũ so với mới**. Chỉ chép số, không nhận định.

# Nếu thấy kế hoạch sai

Dừng và phản biện. Hai chỗ tôi có thể đã chọn nhầm:

1. **Thêm trường `open_fee` vào `DerivativePosition`.** Nếu bạn thấy cách gọn hơn
   mà vẫn giữ `avg_price` nguyên nghĩa giá khớp — nói ra.
2. **Gộp phần 2 vào cùng lượt** (xem trên).
