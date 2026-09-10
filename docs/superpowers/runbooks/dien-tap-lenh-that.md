# Runbook Diễn tập Đường lệnh Thật Đầu-Cuối (SSI Real Order Drill)

> **Mục đích:** Hướng dẫn chi tiết từng bước cho chủ dự án thực hiện diễn tập đặt 01 lệnh thật đầu tiên qua hệ thống kết nối sàn SSI, kiểm chứng toàn bộ chu trình `signal -> risk gate -> pending_real_orders -> manual confirmation -> place_limit_order -> real_order_fills`.
> 
> **Lưu ý quan trọng:** Đây là tài liệu quy trình để chủ dự án tự thực thi khi sẵn sàng. Agent không tự ý chạy các bước trong tài liệu này.

---

## 1. Tiền đề kiểm tra trước khi bắt đầu (Pre-flight Checklist)

Trước khi thực hiện bất kỳ thao tác nào, bắt buộc phải kiểm tra và thỏa mãn toàn bộ 5 điều kiện tiên quyết dưới đây:

### 1.1. Phiên giao dịch đang mở (Trading Session)
- **Thời điểm:** Trong giờ giao dịch khớp lệnh liên tục của sàn HOSE/HNX (09:15-11:30 hoặc 13:00-14:30), vào các ngày từ thứ Hai đến thứ Sáu (không phải ngày nghỉ lễ).
- **Tránh các khung giờ nhạy cảm:** Tránh 15 phút ATO (09:00-09:15) và 15 phút ATC (14:30-14:45) cho lần diễn tập đầu tiên để đảm bảo giá khớp ổn định.

### 1.2. Kiểm tra trạng thái các Docker container
Chạy lệnh kiểm tra container:
```bash
docker ps
```
**Output mong đợi:** Cả 6 container đều ở trạng thái `Up`:
- `ai_auto_trading_system-engine-1` (Up)
- `ai_auto_trading_system-collector-1` (Up)
- `ai_auto_trading_system-postgres-1` (Up / healthy)
- `ai_auto_trading_system-nats-1` (Up)
- `ai_auto_trading_system-nats-test-1` (Up)
- `ai_auto_trading_system-grafana-1` (Up)

### 1.3. Kiểm tra kết nối và độ tươi đồng bộ tài khoản (Account Sync Freshness)
Chạy lệnh kiểm tra đồng bộ vị thế và sức mua trong PostgreSQL:
```bash
docker compose exec -T postgres psql -U trading -d trading -c "SET TimeZone = 'Asia/Ho_Chi_Minh';
SELECT account_no, ts, (now() - ts) as age
FROM account_sync_log
ORDER BY ts DESC LIMIT 2;
"
```
**Output mong đợi:** Có bản ghi cho tài khoản dự định giao dịch với `age < 00:15:00` (độ tuổi đồng bộ dưới 15 phút).

### 1.4. Xác nhận số tài khoản và số dư tiền mặt khả dụng
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
- Tài khoản chọn giao dịch (ví dụ `0434221` hoặc `0434226`) có `withdrawable >= 2.000.000 VNĐ` (đủ tiền mua 1 lô 100 cổ phiếu giá trị ~1-2 triệu đồng).

### 1.5. Kiểm tra cấu hình xác thực SSI API
Kiểm tra biến môi trường SSI trong `.env`:
- `SSI_CONSUMER_ID`, `SSI_CONSUMER_SECRET`, `SSI_API_KEY`, `SSI_API_SECRET`, `SSI_PRIVATE_KEY` đều đã được điền đầy đủ.

---

## 2. Quy mô đề nghị cho lần diễn tập đầu tiên

- **Số lượng lệnh:** Đúng **01 lệnh MUA (BUY)** duy nhất.
- **Mã cổ phiếu chọn lọc:** Chọn 01 mã có thanh khoản cao, biên độ giá ổn định trên HOSE (ví dụ: `IJC`, `AAA` hoặc `TCB`).
- **Khối lượng đặt:** Đúng **01 lô tối thiểu = 100 cổ phiếu** (đã được kẹp trần fail-safe `MAX_REAL_BUY_QTY = 100`).
- **Giá trị lệnh ước tính:** Khoảng **700.000 - 2.500.000 VNĐ** (tùy thị giá cổ phiếu).

---

## 3. Từng bước thực hiện diễn tập (Step-by-Step Execution)

### Bước 1: Cấu hình tài khoản và chế độ lệnh thật
1. Mở file `config/config.yaml`:
   - Xác nhận `real_order_account`: Đặt đúng số tài khoản bạn muốn giao dịch (ví dụ `"0434221"`).
   - Đổi `real_trading_enabled`: từ `false` thành `true`.
2. **Cực kỳ quan trọng — Build lại image engine:**
   Vì `config/config.yaml` được nung trực tiếp vào Docker image lúc build, bạn **phải build lại image** rồi mới restart container, nếu không container vẫn chạy cấu hình cũ:
   ```bash
   docker compose build engine
   docker compose up -d engine
   ```
3. Kiểm tra log engine đã nhận `real_trading_enabled=true`:
   ```bash
   docker compose logs --tail=30 engine
   ```

### Bước 2: Quan sát và chờ tín hiệu giao cắt (Signal Generation)
- Khi chiến lược phát hiện điểm giao cắt (Crossover / Pullback), engine sẽ đánh giá qua Risk Manager.
- Nếu thỏa mãn các lá chắn rủi ro và sức mua, engine sẽ:
  1. Ghi 1 dòng vào bảng `pending_real_orders` với `status = 'pending'`.
  2. Phát cảnh báo `WARN` lên Telegram kèm dòng lệnh xác nhận:
     `uv run python scripts/confirm_real_order.py <id>`

### Bước 3: Xác nhận thủ công lệnh thật (Manual CLI Confirmation)
- **Thời hạn hiệu lực:** Bạn có đúng **15 phút** (`PENDING_ORDER_TTL_MINUTES = 15`) kể từ thời điểm lệnh sinh ra trước khi lệnh tự động hết hạn (`status = 'expired'`).
- Mở terminal trên máy trạm và chạy:
  ```bash
  uv run python scripts/confirm_real_order.py <order_id>
  ```
- Terminal sẽ in thông tin chi tiết lệnh:
  ```text
  Pending order #1227:
    account_no: 0434221
    symbol:     IJC
    side:       BUY
    quantity:   100
    price:      7300.0
    created_at: 2026-09-11 09:30:15+07:00
    expires_at: 2026-09-11 09:45:15+07:00
    status:     pending
  Nhập YES để xác nhận đặt lệnh THẬT (Enter/bất kỳ để huỷ): 
  ```
- Gõ chính xác: `YES` rồi nhấn `Enter`.
- Script sẽ gọi API SSI `place_limit_order` và trả về:
  `Đã đặt lệnh THẬT: order_id=..., status=...`

---

## 4. Cách theo dõi và kiểm chứng trạng thái thời gian thực

### 4.1. Giám sát bảng `pending_real_orders`
```bash
docker compose exec -T postgres psql -U trading -d trading -c "SET TimeZone = 'Asia/Ho_Chi_Minh';
SELECT id, created_at, account_no, symbol, side, quantity, price, status, ssi_order_id, confirmed_at
FROM pending_real_orders
ORDER BY id DESC LIMIT 5;
"
```
- **Chuyển dịch trạng thái:** `pending` -> `placed` (nếu đặt thành công) hoặc `failed` (nếu lỗi).

### 4.2. Giám sát bảng `real_order_fills`
```bash
docker compose exec -T postgres psql -U trading -d trading -c "SET TimeZone = 'Asia/Ho_Chi_Minh';
SELECT id, ts, account_no, symbol, side, qty, price, fee, ssi_order_id, status
FROM real_order_fills
ORDER BY id DESC LIMIT 5;
"
```
- **Bản ghi mong đợi:** Xuất hiện 1 dòng fill mới ghi nhận lệnh thật với `status = 'placed'` hoặc `filled`, `fee` ước tính 0.25%, và đúng mã `ssi_order_id`.

### 4.3. Kiểm tra chéo trên ứng dụng SSI iBoard
- Mở app SSI iBoard hoặc web iBoard, vào mục **Sổ lệnh (Order Book)** của tài khoản để kiểm tra lệnh đã vào sàn thực tế.

---

## 5. Dấu hiệu bất thường cần DỪNG NGAY LẬP TỨC (Emergency Stop Triggers)

Nếu gặp bất kỳ dấu hiệu nào sau đây, dừng diễn tập ngay:
1. **Lỗi xác thực SSI (Auth Failure):** Token hết hạn hoặc sai private key không thể giải mã ký lệnh.
2. **Khối lượng / Giá sai lệch bất thường:** Số lượng đề nghị > 100 cổ phiếu hoặc giá lệch xa biên độ thị trường.
3. **Nhầm số tài khoản:** Mã tài khoản hiển thị trên màn hình xác nhận khác với tài khoản dự định giao dịch.
4. **Sức mua không đủ:** Script báo `insufficient real buying/selling power at confirm time`.
5. **Container Engine crash loop:** Engine liên tục restart hoặc mất kết nối NATS / Postgres.

---

## 6. Cách huỷ giữa chừng và quy trình Rollback về trạng thái an toàn

### 6.1. Huỷ lệnh đang chờ xác nhận (Cancel Pending Order)
- Nếu lệnh đang ở trạng thái `pending`, bạn chỉ cần:
  - Chạy `uv run python scripts/confirm_real_order.py <id>` và nhấn `Enter` (hoặc nhập bất kỳ chữ gì khác `YES`). Script sẽ cập nhật `status = 'rejected'`.
  - HOẶC không làm gì cả, sau 15 phút lệnh sẽ tự động chuyển thành `expired`.

### 6.2. Rollback toàn bộ hệ thống về chế độ an toàn (Safe Mode)
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
