# Báo cáo điều tra Đợt 68 — Truy nguyên lệch PnL giữa `engine_state` và `pnl_daily`

Ngày thực hiện: 19/09/2026.  
Người thực hiện: Gemini Flash 3.8.  
Đối tượng điều tra: Sự chênh lệch **415.050,10 đồng và trái dấu** giữa:
- `engine_state.realized_pnl` = `+144.974,89` (trạng thái tài khoản paper khôi phục lúc khởi động engine).
- `pnl_daily` tổng cột `realized` = `-270.075,21` (và tổng cột `fees` = `341.460,56`).

---

## 1. Tóm tắt kết quả điều tra

Bí ẩn chênh lệch `415.050,10 đồng` đã được giải mã **chính xác tuyệt đối đến từng xu**, cấu thành từ hai nguyên nhân lịch sử:

$$\Delta = (+144.974,89) - (-270.075,21) = +415.050,10 \text{ VNĐ}$$

1. **Nguyên nhân 1 (+534.512,28 đồng): Thao tác đóng thủ công 300 cổ phiếu HII ngày 10/09/2026.**  
   Vào ngày 10/09/2026 lúc 18:18 (được ghi chép chi tiết tại [`docs/superpowers/research/2026-09-10-dong-thu-cong-vi-the-giay-hii.md`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/docs/superpowers/research/2026-09-10-dong-thu-cong-vi-the-giay-hii.md)), vị thế 300 cp HII bị kẹt (do HII bị gỡ khỏi `config.yaml`) đã được Claude và chủ dự án đóng thủ công trực tiếp bằng câu lệnh SQL:
   ```sql
   UPDATE engine_state SET cash=94367687.69003572, realized_pnl=144974.89003572706 WHERE id=1;
   UPDATE positions SET qty=0, avg_price=0 WHERE symbol='HII';
   ```
   Khoản lãi thực hiện từ HII là **+534.512,28 đồng**. Tuy nhiên, theo chủ đích đã ghi ở Mục 6 của tài liệu đó: **không chèn lệnh vào bảng `orders`** và **không ghi dòng vào bảng `pnl_daily`**.  
   -> Do đó, `engine_state` đã cộng khoản lãi này, còn `orders` và `pnl_daily` hoàn toàn không có sự kiện này!

2. **Nguyên nhân 2 (-119.462,18 đồng): Bug FEE-ALARM-1 ngày 14/08 và 1 lệnh test ngày 15/07.**  
   - Trước commit `6664cd9` (14/08/2026 lúc 18:09), `PaperBroker` chưa gộp phí mua vào `avg_price`. Do đó, các lệnh SELL ngày 14/08 ghi vào bảng `orders` và `pnl_daily` **bị bỏ sót 119.417,18 đồng phí mua** của 5 lệnh mua ngày 14/08 (báo lỗ nhẹ hơn thực tế: `-209.381,13` thay vì `-328.798,31`).
   - Đến ngày 19/08, bug đã được fix nên các lệnh ngày 19/08 ghi nhận đúng (-60.739,08).
   - Lệnh rác `TEST` ngày 15/07 có PnL ghi nhận là `+45,00 đồng`.
   - Tiền mặt `cash` và `engine_state.realized_pnl` trước ngày 10/09 phản ánh chuẩn kế toán tiền mặt thực tế đã trừ phí mua: `-328.798,31 + (-60.739,08) = -389.537,39 đồng`.
   - Chênh lệch do phí mua bị sót trong `orders`/`pnl_daily`: `-119.417,18 - 45,00 = -119.462,18 đồng`.

**Kiểm chứng phương trình cân bằng:**
$$+534.512,28 - 119.417,18 - 45,00 = +415.050,10 \text{ VNĐ (Khớp 100% từng chữ số!)}$$

---

## 2. Task 1 — Dựng số gốc độc lập từ bảng `orders`

### 2.1. Tra cứu `price` và biểu phí trong `trading/paper_broker.py`
Theo `trading/paper_broker.py`:
- `FEE_RATE = 0.0025` (0.25% phí giao dịch).
- `SELL_TAX_RATE = 0.001` (0.10% thuế bán).
- `SLIPPAGE_BPS = 5` (5 bps = 0.05% trượt giá).
- Trong hàm `on_bar(bar)` (dòng 146-151):
  ```python
  slip = bar.open * (self.slippage_bps / 10_000)
  price = bar.open + slip if signal.side == "BUY" else bar.open - slip
  gross = price * qty
  fee = gross * self.fee_rate + (gross * self.sell_tax_rate if signal.side == "SELL" else 0.0)
  ```
- **Kết luận về trường `price` trong bảng `orders`:**
  - `price` **ĐÃ GỒM TRƯỢT GIÁ** (slippage).
  - `price` **CHƯA GỒM PHÍ VÀ THUẾ**.
  - Doanh thu / giá trị khớp gộp: `gross = price * qty`.
  - Phí mua = `gross * 0.0025`.
  - Phí bán + thuế = `gross * (0.0025 + 0.0010) = gross * 0.0035`.

### 2.2. Quy ước khớp lệnh (FIFO vs Bình quân gia quyền)
- Toàn bộ 18 lệnh trong bảng `orders` bao gồm 8 vòng giao dịch.
- Trong mọi chu kỳ mua - bán (IJC, AAA, HII), hệ thống luôn **mua một lô và bán sạch 100% số lượng về 0** trước khi có lệnh mua tiếp theo.
- Không có bất kỳ trường hợp nào một mã tồn tại nhiều lô mua ở mức giá khác nhau rồi bán một phần.
- **Hệ quả:** Quy ước **FIFO** và quy ước **Bình quân gia quyền** (Weighted Average) cho kết quả **TRÙNG NHAU 100%**.

### 2.3. Bảng phân tích chi tiết 18 lệnh trong `orders`

| ID | Thời gian (VN) | Mã | Side | Qty | Price (đã slip) | Gross (VNĐ) | Phí & Thuế (VNĐ) | PnL lưu trong DB |
|---|---|---|---|---|---:|---:|---:|---:|
| 1690 | 2026-07-15 09:05 | TEST | SELL | 100 | 11,00 | 1.100,00 | 165,00 | +45,00 |
| 1691 | 2026-08-14 09:20 | IJC | BUY | 400 | 7.703,85 | 3.081.540,00 | 7.703,85 | *None* |
| 1692 | 2026-08-14 09:20 | AAA | BUY | 400 | 7.183,59 | 2.873.436,00 | 7.183,59 | *None* |
| 1693 | 2026-08-14 09:25 | IJC | SELL | 400 | 7.673,85 | 3.069.540,00 | 10.743,39 | -22.743,39 |
| 1694 | 2026-08-14 09:25 | AAA | SELL | 400 | 7.170,00 | 2.868.000,00 | 10.038,00 | -15.474,00 |
| 1695 | 2026-08-14 09:30 | HII | BUY | 300 | 8.894,44 | 2.668.333,50 | 6.670,83 | *None* |
| 1696 | 2026-08-14 09:30 | HII | SELL | 300 | 8.840,16 | 2.652.047,79 | 9.282,17 | -25.567,88 |
| 1697 | 2026-08-14 13:50 | IJC | BUY | 2600 | 7.443,72 | 19.353.672,00 | 48.384,18 | *None* |
| 1698 | 2026-08-14 13:55 | IJC | SELL | 2600 | 7.406,30 | 19.256.367,00 | 67.397,28 | -164.702,28 |
| 1699 | 2026-08-14 13:55 | HII | BUY | 2300 | 8.604,30 | 19.789.890,00 | 49.474,72 | *None* |
| 1700 | 2026-08-14 14:05 | HII | SELL | 2300 | 8.642,86 | 19.878.571,43 | 69.575,00 | +19.106,43 |
| 1701 | 2026-08-19 13:40 | AAA | BUY | 400 | 6.943,47 | 2.777.388,00 | 6.943,47 | *None* |
| 1702 | 2026-08-19 13:50 | IJC | BUY | 400 | 7.223,61 | 2.889.444,00 | 7.223,61 | *None* |
| 1703 | 2026-08-19 13:55 | AAA | SELL | 400 | 6.900,00 | 2.760.000,00 | 9.660,00 | -33.991,47 |
| 1704 | 2026-08-19 13:55 | IJC | SELL | 400 | 7.200,00 | 2.880.000,00 | 10.080,00 | -26.747,61 |
| 1705 | 2026-08-19 14:05 | HII | BUY | 300 | 8.704,35 | 2.611.305,00 | 6.528,26 | *None* |
| 1706 | 2026-09-03 09:15 | IJC | BUY | 400 | 7.353,68 | 2.941.470,00 | 7.353,68 | *None* |
| 1707 | 2026-09-03 09:20 | AAA | BUY | 400 | 7.053,52 | 2.821.410,00 | 7.053,53 | *None* |

Ba vị thế mở sau ngày 03/09:
- HII: 300 cp (ID=1705, ngày 19/08).
- IJC: 400 cp (ID=1706, ngày 03/09).
- AAA: 400 cp (ID=1707, ngày 03/09).

### 2.4. Bảng tính PnL từng vòng giao dịch khép kín (Cycles)

Hai phương pháp tính:
- **Cách 1 (Công thức cũ trước fix FEE-ALARM-1):**  
  $\text{PnL} = (\text{Price}_{\text{sell}} - \text{Price}_{\text{buy}}) \times \text{Qty} - \text{Fee}_{\text{sell}}$ (Bỏ sót phí mua).
- **Cách 2 (Chuẩn kế toán tiền mặt / Sau fix FEE-ALARM-1):**  
  $\text{PnL} = (\text{Gross}_{\text{sell}} - \text{Fee}_{\text{sell}}) - (\text{Gross}_{\text{buy}} + \text{Fee}_{\text{buy}})$ (Trừ đủ phí mua và bán).

| Vòng giao dịch | Mã | Qty | PnL Cách 1 (Cũ) | PnL Cách 2 (Chuẩn) | PnL trong DB (`orders.pnl`) | Phí mua sót |
|---|---|---|---:|---:|---:|---:|
| 0. TEST (15/07) | TEST | 100 | +45,00 | +45,00 | +45,00 | 0,00 |
| 1. IJC (14/08 sáng) | IJC | 400 | -22.743,39 | -30.447,24 | -22.743,39 | 7.703,85 |
| 2. AAA (14/08 sáng) | AAA | 400 | -15.474,00 | -22.657,59 | -15.474,00 | 7.183,59 |
| 3. HII (14/08 sáng) | HII | 300 | -25.567,88 | -32.238,72 | -25.567,88 | 6.670,83 |
| 4. IJC (14/08 chiều) | IJC | 2600 | -164.702,28 | -213.086,46 | -164.702,28 | 48.384,18 |
| 5. HII (14/08 chiều) | HII | 2300 | +19.106,43 | -30.368,30 | +19.106,43 | 49.474,72 |
| 6. AAA (19/08 chiều) | AAA | 400 | -27.048,00 | -33.991,47 | -33.991,47 | 6.943,47 |
| 7. IJC (19/08 chiều) | IJC | 400 | -19.524,00 | -26.747,61 | -26.747,61 | 7.223,61 |
| **TỔNG CỘNG** | | | **-255.908,13** | **-389.492,39** | **-270.075,21** | **133.584,26** |

**Phát hiện bất đối xứng trong bảng `orders`:**
- **Ngày 14/08:** Chạy bằng code cũ (trước commit `6664cd9`), nên `orders.pnl` ghi theo **Cách 1** (sót 119.417,18 đồng phí mua).
- **Ngày 19/08:** Chạy bằng code mới (sau commit `6664cd9`), nên `orders.pnl` ghi theo **Cách 2** (chuẩn kế toán).
- Do đó, tổng cột `orders.pnl` = `-270.075,21` là **tổng lai ghép**: ngày 14/08 thiếu phí mua, ngày 19/08 đủ phí mua.

---

## 3. Task 2 — Tìm nơi mỗi con số được sinh ra

### 3.1. `engine_state.realized_pnl`
- **Đường dẫn:dòng trong codebase:**  
  [`trading/engine/main.py:312`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/trading/engine/main.py#L312) trong hàm `persist_fills(fills)`:
  ```python
  storage.write_engine_state(broker.cash, broker.realized_pnl)
  ```
  Và [`trading/storage/db.py:207-217`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/trading/storage/db.py#L207-L217):
  ```sql
  INSERT INTO engine_state (id, cash, realized_pnl, updated_at)
  VALUES (1, %s, %s, now())
  ON CONFLICT (id) DO UPDATE SET cash = EXCLUDED.cash, realized_pnl = EXCLUDED.realized_pnl, updated_at = EXCLUDED.updated_at
  ```
- **Công thức tính:**  
  `broker.realized_pnl` được cộng dồn mỗi khi khớp lệnh SELL trong `trading/paper_broker.py:171-172`:
  ```python
  pnl = (price - pos.avg_price) * qty - fee
  self.realized_pnl += pnl
  ```
- **Vì sao `updated_at` là 2026-09-10 trong khi lệnh cuối là 2026-09-03?**  
  Ngày 10/09/2026 lúc 18:18:35, Claude đã chạy câu lệnh `UPDATE` thủ công trực tiếp trên DB để đóng vị thế 300 HII:
  ```sql
  UPDATE engine_state SET cash=94367687.69003572, realized_pnl=144974.89003572706, updated_at=now() WHERE id=1;
  UPDATE positions SET qty=0, avg_price=0, updated_at=now() WHERE symbol='HII';
  ```
  Giá trị trước khi UPDATE: `realized_pnl = -389.537,39`.  
  Lãi đóng 300 HII ở giá 10.550 (sau slip 5 bps và trừ phí+thuế): `+534.512,28`.  
  `-389.537,39 + 534.512,28 = +144.974,89`.

### 3.2. `pnl_daily`
- **Đường dẫn:dòng trong codebase:**  
  [`trading/engine/main.py:314-319`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/trading/engine/main.py#L314-L319) trong hàm `persist_fills(fills)`:
  ```python
  storage.update_pnl_daily(
      fill.ts.astimezone(TZ).date(),
      fill.pnl or 0.0,
      fill.fee,
      broker.unrealized_pnl(marks),
  )
  ```
  Và [`trading/storage/db.py:528-539`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/trading/storage/db.py#L528-L539):
  ```sql
  INSERT INTO pnl_daily (date, realized, unrealized, fees) VALUES (%s, %s, %s, %s)
  ON CONFLICT (date) DO UPDATE SET
      realized = pnl_daily.realized + EXCLUDED.realized,
      fees = pnl_daily.fees + EXCLUDED.fees,
      unrealized = EXCLUDED.unrealized
  ```
- **Cột `realized` là gộp cả phí hay chưa trừ phí?**  
  - Cột `realized` nhận trực tiếp giá trị `fill.pnl`.
  - Như đã chỉ ra ở Task 1:
    - Với các lệnh ngày 14/08: `fill.pnl` **CHỈ TRỪ PHÍ BÁN, CHƯA TRỪ PHÍ MUA**.
    - Với các lệnh ngày 19/08: `fill.pnl` **ĐÃ TRỪ CẢ PHÍ MUA LẪN PHÍ BÁN**.
- **Bảng này có ghi dòng cho ngày không có lệnh không?**  
  **KHÔNG.** Hàm `update_pnl_daily()` chỉ nằm trong `persist_fills()`. Khi không có tín hiệu khớp lệnh nào, hàm này hoàn toàn không được gọi. Đó là lý do bảng `pnl_daily` hiện tại chỉ có đúng **4 dòng** tương ứng với 4 ngày có lệnh (15/07, 14/08, 19/08, 03/09).

### 3.3. Đối chiếu ba con số

| Nguồn số | Realized PnL (VNĐ) | Phí mua ngày 14/08 | Đóng vị thế HII 10/09 | Ghi chú |
|---|---:|:---:|:---:|---|
| **`pnl_daily`** (tổng 4 dòng) | **-270.075,21** | Bị sót | Không có | Khớp 100% với tổng cột `orders.pnl` |
| **Tự tính từ `orders` (chuẩn tiền mặt)** | **-389.492,39** | Đã trừ | Không có | Gồm cả lệnh test 15/07 (+45đ). Bỏ test ra đúng **-389.537,39** |
| **`engine_state`** (trước 10/09) | **-389.537,39** | Đã trừ | Chưa đóng | Khớp 100% chuẩn tiền mặt (đã trừ phí mua) |
| **`engine_state`** (sau 10/09) | **+144.974,89** | Đã trừ | **ĐÃ CỘNG (+534.512,28)** | Nhất quán tuyệt đối với NAV và Cash |

---

## 4. Task 3 — Kết luận

**Kết luận: Trường hợp (b) kết hợp (c) — Cả hai đều có lý do tồn tại độc lập, nhưng mâu thuẫn do một thao tác can thiệp thủ công không đồng bộ.**

Cụ thể:

1. **`pnl_daily` đúng về mặt "sổ nhật ký tự động" của engine:**
   - Nó phản ánh trung thực 100% những gì engine đã khớp và ghi nhận trong 4 ngày giao dịch tự động.
   - Nhưng nó **bị khiếm khuyết 2 điểm**:
     - Kế thừa bug lịch sử ngày 14/08 (thiếu 119.417đ phí mua).
     - **Không biết gì về sự kiện đóng HII ngày 10/09**, vì ngày đó thao tác được thực hiện bằng tay ngoài engine và cố ý không ghi nhận vào hệ thống lệnh.

2. **`engine_state` đúng về mặt "trạng thái tài sản thực tế" (Balance Sheet / Cash Flow):**
   - Tiền mặt `cash` = 94.367.687,69 VNĐ.
   - Giá vốn 2 vị thế đang giữ:
     - 400 cp IJC: $400 \times 7.372,059 = 2.948.823,68$ VNĐ.
     - 400 cp AAA: $400 \times 7.071,159 = 2.828.463,53$ VNĐ.
     - Tổng giá vốn cổ phiếu: $5.777.287,20$ VNĐ.
   - Tổng tài sản theo giá vốn:
     $$\text{NAV}_{\text{cost}} = 94.367.687,69 + 5.777.287,20 = 100.144.974,89 \text{ VNĐ}$$
   - Chênh lệch so với vốn gốc 100.000.000 VNĐ:
     $$\Delta \text{Vốn} = 100.144.974,89 - 100.000.000 = +144.974,89 \text{ VNĐ}$$
   - **Con số `realized_pnl` của `engine_state` hoàn toàn tự nhất quán 100% với tài sản và tiền mặt thực tế!** Tài khoản paper thực sự đang lãi 144.975 đồng nhờ cú đóng lãi hơn nửa triệu của HII gánh khoản lỗ trước đó.

3. **Nguy cơ hệ thống nếu không thống nhất:**
   - Việc `engine_state` mang số lãi `+144k` trong khi Grafana đọc từ `pnl_daily` mang số lỗ `-270k` tạo ra sự phân mảnh thông tin nghiêm trọng.
   - Khi vận hành tiền thật (`real_trading_enabled`), việc can thiệp thủ công (như đóng vị thế bằng tay ngoài sàn/ngoài engine) **bắt buộc phải ghi nhận một sự kiện giao dịch đầy đủ (lệnh manual fill)** để cả sổ lệnh (`orders`), sổ nhật ký (`pnl_daily`) và trạng thái tài khoản (`engine_state`) cùng được cập nhật đồng thời.

---

## 5. Xác nhận tuân thủ ràng buộc

- **Không sửa code:** Không có bất kỳ file mã nguồn (`.py`, `.sh`, `.sql`, `.yaml`) nào bị thay đổi.
- **Không ghi DB:** Không thực hiện bất kỳ câu lệnh `INSERT`, `UPDATE`, `DELETE` nào trên database (chỉ chạy `SELECT`).
- **Trạng thái Git:** Sạch sẽ, không commit, không push.
