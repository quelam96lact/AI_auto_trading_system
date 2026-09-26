# Runbook Diễn tập Đường lệnh Thật Đầu-Cuối (SSI Real Order Drill)

> **Cập nhật:** 26/09/2026 (Brief đợt 100).
> **Các thay đổi so với bản trước:**
> 1. Thêm **Bước 0**: Chủ tài khoản chọn và ghi rõ tài khoản giao dịch (`0434221` hay `0434226`) kèm lý do trước khi thực hiện.
> 2. Cập nhật **Pre-flight Checklist**: Thêm cổng kiểm tra tự động `uv run python scripts/check_golive_gate.py` (bắt buộc EXIT 0); cập nhật danh sách container thực tế từ lệnh `docker compose ps` ngày 26/09/2026.
> 3. Tách bạch hai giai đoạn diễn tập:
>    - **Giai đoạn T3 (Spike Drill):** Diễn tập đặt và huỷ ngay 01 lệnh thật qua công cụ mới `scripts/drill_place_cancel_order.py` (thay thế script spike cũ đã vô hiệu hoá). Quy trình gồm chạy thử (dry-run), đọc kế hoạch lệnh, chạy thật với `--send`, gõ `YES`, đối chiếu trên iBoard và phương án xử lý sự cố khi huỷ thất bại (huỷ tay trên iBoard, vị thế bán từ T+2,5).
>    - **Giai đoạn T4 (System Flow Drill):** Diễn tập đường lệnh tự động của hệ thống (`signal -> risk gate -> pending_real_orders -> confirm_real_order.py`).
>
> **Lưu ý quan trọng:** Đây là tài liệu quy trình để chủ dự án tự thực thi khi sẵn sàng. Agent TUYỆT ĐỐI KHÔNG tự ý gửi bất kỳ lệnh thật nào lên sàn.

---

## Bước 0: Chọn và ghi nhận tài khoản giao dịch (Bắt buộc trước mọi thao tác)

Trước khi tiến hành, chủ tài khoản **phải chọn và ghi rõ** tài khoản sẽ dùng cho buổi diễn tập vào nhật ký vận hành:
> **Đính chính của Claude (audit đợt 100):** bản agent nộp mô tả **ngược** hai tài khoản (gọi 0434221 là margin, 0434226 là tiền mặt). Số liệu thật đọc từ DB lúc 11:45 ngày 26/09/2026:

| Tài khoản | Loại | Tiền rút được | Nợ vay | NAV |
|---|---|---|---|---|
| `0434221` | **tiền mặt** (không nợ) | 5.021.712 | 0 | 5,02 triệu |
| `0434226` | **margin** (đang vay) | 0 | 31.225.333 | 192,6 triệu |

- **`0434221`**: vốn nhỏ, không dùng nợ vay. Sức mua đủ 1 lô cho HPG/IJC/AAA, **không** đủ cho VCB (đo 26/09: VCB tối đa 80 cổ phiếu). Hợp với diễn tập T3: rủi ro tối đa là 1 lô.
- **`0434226`**: tài khoản margin đang có nợ ~31 triệu. Sức mua theo **từng mã** và lớn hơn nhiều; lệnh mua ở đây có thể dùng tiền vay. Lưu ý cho T4: đổi `real_order_account` sang tài khoản này đồng thời **nhân cỡ lệnh của hệ thống lên khoảng 38 lần** (NAV 192,6 triệu so với 5,02 triệu, đo 26/09) vì cỡ lệnh tính theo NAV.

**Lý do chọn:** Ghi rõ lý do chọn tài khoản (ví dụ: đã nạp tiền mặt vào tài khoản này, kiểm tra đúng số dư khả dụng).

---

## 1. Tiền đề kiểm tra trước khi bắt đầu (Pre-flight Checklist)

Trước khi thực hiện bất kỳ thao tác nào, bắt buộc phải kiểm tra và thỏa mãn toàn bộ 6 điều kiện tiên quyết dưới đây:

### 1.1. Khung giờ giao dịch phiên liên tục (Trading Session)
- **Thời điểm:** Trong giờ giao dịch khớp lệnh liên tục của sàn HOSE/HNX:
  - **Phiên sáng:** 09:15 – 11:30.
  - **Phiên chiều:** 13:00 – 14:30.
  - Các ngày từ thứ Hai đến thứ Sáu (không phải ngày nghỉ lễ).
- **Tránh tuyệt đối các khung giờ nhạy cảm:**
  - Tránh 15 phút ATO (09:00 – 09:15).
  - Tránh 15 phút ATC (14:30 – 14:45).
  - Không diễn tập vào giờ nghỉ trưa (11:30 – 13:00) hoặc ngoài giờ hành chính.

### 1.2. Cổng kiểm định Go-Live tự động (Check Go-Live Gate)
Chạy script kiểm định toàn bộ lá chắn an toàn:
```bash
uv run python scripts/check_golive_gate.py
```
**Yêu cầu bắt buộc:** Lệnh phải kết thúc với **EXIT 0** (`>>> KẾT LUẬN: ĐỦ ĐIỀU KIỆN GO-LIVE (EXIT 0)`). Nếu có bất kỳ lá chắn nào bị FAIL (EXIT 2), dừng ngay lập tức.

### 1.3. Kiểm tra trạng thái các Docker container
Chạy lệnh kiểm tra container thực tế:
```bash
docker compose ps
```
**Danh sách container thực tế (đo ngày 26/09/2026) — cả 6 container đều phải ở trạng thái `Up`:**
- `ai_auto_trading_system-collector-1`: `Up` (thu thập dữ liệu thời gian thực).
- `ai_auto_trading_system-engine-1`: `Up` (động cơ xử lý tín hiệu và quản trị rủi ro).
- `ai_auto_trading_system-grafana-1`: `Up` (cổng 127.0.0.1:3000->3000/tcp).
- `ai_auto_trading_system-nats-1`: `Up` (cổng 127.0.0.1:4222->4222/tcp).
- `ai_auto_trading_system-nats-test-1`: `Up` (cổng 127.0.0.1:4223->4222/tcp).
- `ai_auto_trading_system-postgres-1`: `Up (healthy)` (cổng 127.0.0.1:5432->5432/tcp).

### 1.4. Kiểm tra kết nối và độ tươi đồng bộ tài khoản (Account Sync Freshness)
Chạy lệnh kiểm tra đồng bộ vị thế và sức mua trong PostgreSQL:
```bash
docker compose exec -T postgres psql -U trading -d trading -c "SET TimeZone = 'Asia/Ho_Chi_Minh';
SELECT account_no, ts, (now() - ts) as age
FROM account_sync_log
ORDER BY ts DESC LIMIT 2;
"
```
**Output mong đợi:** Có bản ghi cho tài khoản đã chọn ở Bước 0 với `age < 00:15:00` (độ tuổi đồng bộ dưới 15 phút).

### 1.5. Xác nhận số tài khoản và số dư tiền mặt khả dụng
Kiểm tra NAV và số dư tiền mặt của tài khoản trong snapshot:
```bash
docker compose exec -T postgres psql -U trading -d trading -c "SET TimeZone = 'Asia/Ho_Chi_Minh';
SELECT n.account_no, n.nav, b.withdrawable, b.total_debt, n.ts
FROM account_nav_snapshot n
JOIN account_balance_snapshot b ON n.account_no = b.account_no
ORDER BY n.ts DESC LIMIT 2;
"
```
**Output mong đợi:** 
- Tài khoản chọn giao dịch có `withdrawable >= 2.000.000 VNĐ` (đủ tiền mua 1 lô 100 cổ phiếu giá trị ~1-2 triệu đồng).

### 1.6. Kiểm tra cấu hình xác thực SSI API
Kiểm tra biến môi trường SSI trong `.env`:
- `SSI_CONSUMER_ID`, `SSI_CONSUMER_SECRET`, `SSI_API_KEY`, `SSI_API_SECRET`, `SSI_PRIVATE_KEY` đều đã được điền đầy đủ.

---

## 2. Giai đoạn T3: Diễn tập Đặt và Huỷ Ngay 01 Lệnh Thật (Spike Drill)

Đây là bước kiểm chứng kết nối thực tế với tiền thật: ký lệnh bằng RSA private key, gửi lệnh LO BUY cách xa thị trường, rồi huỷ ngay lập tức trên sàn SSI.

### 2.1. Quy mô lệnh diễn tập T3
- **Mã cổ phiếu:** Mặc định `VCB` (hoặc mã khác trên HOSE/HNX có trong `symbol_universe`).
- **Khối lượng:** Đúng 01 lô tối thiểu = 100 cổ phiếu.
- **Giá đặt:** Tự động tính qua công thức `drill_price`:
  - HOSE: Giá sàn = `ceil(ref * 0.93)`; Giá đặt = `ceil(ref * 0.94)` (cao hơn sàn ~1%, thấp hơn tham chiếu ~6%).
  - HNX: Giá sàn = `ceil(ref * 0.90)`; Giá đặt = `ceil(ref * 0.91)` (cao hơn sàn ~1%, thấp hơn tham chiếu ~9%).
  - Giá này nằm trong biên độ cho phép của sàn nhưng cách rất xa giá thị trường đang khớp, gần như không thể khớp trong vài giây trước khi huỷ.

### 2.2. Các bước thực hiện T3 chính xác theo thứ tự

#### Bước 1: Chạy thử (Dry-Run — Chỉ đọc)
Chạy script **không có cờ `--send`**:
```bash
uv run python scripts/drill_place_cancel_order.py --account <TK_DA_CHON> --symbol VCB
```
Script sẽ đọc dữ liệu nến ngày từ SSI, kiểm tra sức mua, tính giá tham chiếu và in bảng kế hoạch lệnh:
```text
=================================================================
 KẾ HOẠCH LỆNH DIỄN TẬP ĐẶT-HUỶ (T3 DRILL ORDER PLAN)
=================================================================
 Tài khoản:        0434221
 Mã cổ phiếu:      VCB
 Sàn giao dịch:    HOSE
 Giá tham chiếu:   90,000 VNĐ
 Giá sàn:          83,700 VNĐ
 Giá đặt (LO BUY): 84,600 VNĐ (thấp hơn ref ~6.0%)
 Khối lượng đặt:   100 cổ phiếu (01 lô tối thiểu)
 Sức mua tối đa:   500 cổ phiếu
=================================================================
[CHẠY THỬ] không gửi lệnh. (Dùng cờ --send để kích hoạt gửi lệnh thật)
```

#### Bước 2: Đọc kỹ kế hoạch lệnh
Kiểm tra các thông tin trên màn hình:
1. Đúng số tài khoản dự định diễn tập chưa?
2. Giá tham chiếu có khớp với giá đóng cửa phiên trước trên bảng điện iBoard không?
3. Giá đặt có đúng là `floor <= price < ref` không?
4. Sức mua có đủ >= 100 cổ phiếu không?

#### Bước 3: Chạy thật có `--send` và gõ YES
Khi đã chắc chắn mọi thông số chính xác:
```bash
uv run python scripts/drill_place_cancel_order.py --account <TK_DA_CHON> --symbol VCB --send
```
Script in lại kế hoạch và dừng lại yêu cầu xác nhận:
```text
Gõ YES để GỬI LỆNH THẬT: 
```
- Gõ chính xác: `YES` rồi nhấn `Enter`. (Gõ bất kỳ chữ nào khác như `yes`, `y` hoặc để trống sẽ huỷ an toàn ngay lập tức).
- Script sẽ:
  1. Gửi lệnh `place_limit_order` lên sàn SSI.
  2. In phản hồi `order_id`, `client_request_id`.
  3. Gọi ngay `cancel_order` để huỷ lệnh trên sàn.
  4. Tra cứu lại trạng thái sổ lệnh trong ngày (`portfolio.get_today_orders`).
  5. Lưu audit log vào file JSON tại `logs/drill_order_<YYYYMMDD_HHMMSS>.json`.

#### Bước 4: Đối chiếu trên ứng dụng SSI iBoard
- Mở ngay ứng dụng SSI iBoard hoặc web iBoard, vào mục **Sổ lệnh (Order Book)** của tài khoản.
- Xác nhận: Lệnh mua 100 VCB ở giá đặt đã xuất hiện và chuyển sang trạng thái **Đã huỷ (Cancelled)**.

### 2.3. Xử lý sự cố nếu huỷ thất bại (Contingency Plan)

Nếu script báo lỗi ở bước huỷ lệnh hoặc thoát với mã 2:
1. **Màn hình terminal sẽ in khối cảnh báo đỏ:**
   ```text
   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    CẢNH BÁO NGHIÊM TRỌNG: HUỶ LỆNH THẤT BẠI!
    LỆNH THẬT CÓ THỂ ĐANG TREO — HUỶ TAY NGAY TRÊN iBoard/ứng dụng SSI
     - Tài khoản:          ...
     - Mã cổ phiếu:        ...
     - Giá đặt:            ... VNĐ
     - Số lượng:           100 cổ phiếu
     - Order ID:           ...
     - Client Request ID:  ...
   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
   ```
2. **Hành động ngay lập tức:**
   - Mở app SSI iBoard trên điện thoại hoặc trình duyệt web.
   - Vào Sổ lệnh -> Tìm lệnh đang treo -> **Bấm Huỷ lệnh bằng tay**.
3. **Nếu lệnh đã vô tình khớp (rất hiếm):**
   - Không hoảng sợ: Lệnh được đặt ở mức giá thấp hơn giá tham chiếu khoảng 6% (HOSE) hoặc 9% (HNX), đây là mức giá mua rất có lợi.
   - Vị thế 100 cổ phiếu này sẽ về tài khoản và được phép bán ra từ **chiều ngày T+2,5** theo quy định thanh toán T+2 hiện hành của VSDC.
   - Rủi ro tối đa chỉ là mức biến động giá của đúng 100 cổ phiếu trong 2,5 ngày.

---

## 3. Giai đoạn T4: Diễn tập Đường lệnh Tự động của Hệ thống (Sau khi T3 ĐẠT)

Sau khi giai đoạn T3 thành công (chứng minh đường xác thực, ký lệnh và huỷ lệnh trên sàn thật chạy tốt), chủ dự án tiến hành diễn tập kiểm chứng toàn bộ chu trình tự động của hệ thống:
`signal -> risk gate -> pending_real_orders -> manual confirmation -> place_limit_order -> real_order_fills`.

Quy trình chi tiết của T4 được giữ nguyên như thiết kế chuẩn:
- Xem chi tiết tại: **Mục 3, 4, 5, 6** của tài liệu này (cấu hình `real_trading_enabled: true`, build lại Docker image engine, chờ tín hiệu và xác nhận qua `scripts/confirm_real_order.py <order_id>`).

---

## 4. Từng bước thực hiện diễn tập T4 (System Flow Execution)

### Bước 1: Cấu hình tài khoản và chế độ lệnh thật
1. Mở file `config/config.yaml`:
   - Xác nhận `real_order_account`: Đặt đúng số tài khoản đã chọn ở Bước 0 (ví dụ `"0434221"`).
   - Đổi `real_trading_enabled`: từ `false` thành `true`.
2. **Cực kỳ quan trọng — Build lại image engine:**
   Vì `config/config.yaml` được nung trực tiếp vào Docker image lúc build, bạn **phải build lại image** rồi mới restart container:
   ```bash
   docker compose build engine
   docker compose up -d engine
   ```
3. Kiểm tra log engine đã nhận `real_trading_enabled=true`:
   ```bash
   docker compose logs --tail=30 engine
   ```

### Bước 2: Quan sát và chờ tín hiệu giao cắt (Signal Generation)
- Khi chiến lược phát hiện điểm giao cắt, engine sẽ đánh giá qua Risk Manager.
- Nếu thỏa mãn các lá chắn rủi ro và sức mua, engine sẽ:
  1. Ghi 1 dòng vào bảng `pending_real_orders` với `status = 'pending'`.
  2. Phát cảnh báo `WARN` lên Telegram kèm dòng lệnh xác nhận:
     `uv run python scripts/confirm_real_order.py <id>`

### Bước 3: Xác nhận thủ công lệnh thật (Manual CLI Confirmation)
- **Thời hạn hiệu lực:** Đúng **15 phút** (`PENDING_ORDER_TTL_MINUTES = 15`) kể từ thời điểm lệnh sinh ra.
- Mở terminal trên máy trạm và chạy:
  ```bash
  uv run python scripts/confirm_real_order.py <order_id>
  ```
- Gõ chính xác: `YES` rồi nhấn `Enter`.
- Script gọi API SSI `place_limit_order` và ghi nhận fill vào `real_order_fills`.

---

## 5. Giám sát và Kiểm chứng trạng thái thời gian thực

### 5.1. Giám sát bảng `pending_real_orders`
```bash
docker compose exec -T postgres psql -U trading -d trading -c "SET TimeZone = 'Asia/Ho_Chi_Minh';
SELECT id, created_at, account_no, symbol, side, quantity, price, status, ssi_order_id, confirmed_at
FROM pending_real_orders
ORDER BY id DESC LIMIT 5;
"
```

### 5.2. Giám sát bảng `real_order_fills`
```bash
docker compose exec -T postgres psql -U trading -d trading -c "SET TimeZone = 'Asia/Ho_Chi_Minh';
SELECT id, ts, account_no, symbol, side, qty, price, fee, ssi_order_id, status
FROM real_order_fills
ORDER BY id DESC LIMIT 5;
"
```

### 5.3. Kiểm tra chéo trên ứng dụng SSI iBoard
- Mở app SSI iBoard vào mục **Sổ lệnh (Order Book)** để kiểm tra lệnh đã vào sàn thực tế.

---

## 6. Rollback về trạng thái an toàn sau khi kết thúc diễn tập

Sau khi kết thúc diễn tập hoặc khi cần ngắt khẩn cấp:
1. Sửa file `config/config.yaml`:
   ```yaml
   real_trading_enabled: false
   ```
2. **Rebuild và restart container engine:**
   ```bash
   docker compose build engine
   docker compose up -d engine
   ```
3. Kiểm tra log để khẳng định engine đã quay lại chế độ Dry-run:
   ```bash
   docker compose logs --tail=20 engine
   ```
   Xác nhận dòng log: `real_trading_enabled=False`.
