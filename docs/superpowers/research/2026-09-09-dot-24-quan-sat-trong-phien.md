# Báo Cáo Quan Sát Trực Tiếp Trong Phiên Giao Dịch (09/09/2026)

## 1. Bảng Dữ Liệu Quan Sát Xuyên Suốt 4 Mốc Trong Phiên

| Mốc giờ (VN) | `bars` hôm nay | `bars` HII | `heartbeat` engine | `heartbeat` collector | Lệnh hôm nay | `refresh_token_expires_at` | `num_pending` | `delivered.stream_seq` | `ack_floor.stream_seq` |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **09:43 (Baseline)** | 18 | 6 | 09:43:42 | 09:43:46 | 0 | 1788944137 | 0 | 25,324 | 25,324 |
| **10:30 (Mốc 1)** | 43 | 13 | 10:29:00 | 10:29:11 | 0 | 1788944137 | 0 | 25,558 | 25,558 |
| **11:15 (Mốc 2)** | 71 | 22 | 11:15:06 | 11:15:08 | 0 | 1788944137 | 0 | 25,700 | 25,700 |
| **13:30 (Mốc 3)** | 99 | 31 | 13:30:21 | 13:30:26 | 0 | 1788944137 | 0 | 25,907 | 25,907 |
| **14:45 (Mốc 4)** | 135 | 43 | 14:45:08 | 14:45:08 | 0 | 1788944137 | 0 | 26,184 | 26,184 |

---

## 2. Phân Tích & Trả Lời Các Câu Hỏi Giám Sát Tiêu Thụ Bar

### 2.1. `num_pending` có tăng dần qua các mốc không?
- **Không.** Số lượng `num_pending` (bar đã publish vào NATS mà engine chưa nhận) duy trì liên tục ở mức **0** tại tất cả các mốc (09:43, 10:30, 11:15, 13:30, 14:45). Số lượng `num_ack_pending` (đã giao nhưng chưa ack) và `num_redelivered` (số lần giao lại do lỗi) cũng luôn bằng **0**.
- **Bằng chứng**: Engine tiêu thụ và xác nhận (ACK) ngay lập tức mọi message bar từ stream `BARS` khi được collector phát hành.

### 2.2. `delivered.stream_seq` có tiến lên giữa các mốc không?
- **Có.** Số thứ tự chuỗi `delivered.stream_seq` tăng liên tục qua từng mốc trong phiên:
  - 09:43: `25,324`
  - 10:30: `25,558` (+234 messages)
  - 11:15: `25,700` (+142 messages)
  - 13:30: `25,907` (+207 messages)
  - 14:45: `26,184` (+277 messages)
  - Tổng tăng trưởng: **+860 messages stream seq** (tương ứng `delivered.consumer_seq` tăng từ `8,258` lên `9,118`).
- Kết luận gốc của báo cáo này ghi: *"Số lượng bar trong database tăng tương ứng từ 18 lên 135 bars."* **Câu đó sai** — xem mục 2.2bis, Claude tự đối chiếu lại và tìm ra chênh lệch không nhỏ.

### 2.2bis. BỔ SUNG (Claude, audit sau khi nhận báo cáo) — số message KHÔNG tương ứng với số bar, và nguyên nhân đã tìm ra ở tầng code

Đối chiếu **delta** giữa các mốc liền kề (không phải tổng cộng dồn, để không bị lệch điểm gốc):

| Khoảng | Δ `stream_seq` | Δ bar (3 mã) | Tỷ lệ |
|---|---:|---:|---:|
| 09:43 → 10:30 | 234 | 25 | **9,36×** |
| 10:30 → 11:15 | 142 | 28 | **5,07×** |
| 11:15 → 13:30 | 207 | 28 | **7,39×** |
| 13:30 → 14:45 | 277 | 36 | **7,69×** |

Tỷ lệ dao động **5–9 lần suốt cả phiên**, không hội tụ về 1 và không phải hiện tượng khởi động
buổi sáng. Đây là bổ sung 2.4bis mà brief yêu cầu — báo cáo gốc **không thực hiện phần này**,
dù đã có đủ hai cột số liệu để tự tính ra.

**Nguyên nhân, xác minh trực tiếp trong code, không suy đoán:**

1. `trading/collector/main.py::make_stream_message_handler` (dòng 101-116) gọi
   `persist_bars(storage, pub, [bar])` cho **mọi** message SSI gửi tới qua
   `parse_interval_message`, không đi qua `BarAggregator` — tức không có bước "gộp tick thành
   bar rồi chỉ phát khi đóng".
2. `parse_interval_message` (`trading/collector/parser.py:70-90`) tự ghi trong docstring:
   *"UNCONFIRMED WITH LIVE STREAM DATA"* — định dạng và ngữ nghĩa của `interval_time` chưa
   từng được xác minh với dữ liệu stream thật trước đợt 24.
3. Lớp `IntervalMessage` (`ssi_sdk/models/streaming.py:105-130`) **không có trường nào đánh
   dấu bar đã đóng** — chỉ có `interval_time` (mốc bucket), `trading_time`, và OHLCV. Đây là
   kiểu push "nến đang chạy" tiêu chuẩn của dữ liệu thị trường thời gian thực: SSI gửi lại
   OHLC hiện tại của khung đang hình thành mỗi khi có giao dịch mới, không chỉ một lần khi
   khung đóng.
4. `trading/storage/db.py:31` ghi bar bằng `ON CONFLICT (symbol, ts) DO UPDATE` — nên DB chỉ
   giữ **giá trị mới nhất** của mỗi khung 5 phút, che mất việc nó đã bị ghi đè nhiều lần.
   Nhưng **mỗi lần ghi đè đó vẫn kèm một lần `pub.publish(b)`** — một message NATS mới, độc
   lập với DB.
5. Phía engine, `trading/engine/logic.py::process_bar` xử lý **vô điều kiện** mọi bar nhận
   được: gọi `broker.on_bar`, `strategy.on_bar`, kiểm trailing stop, tính và gửi tín hiệu —
   không có khái niệm "bar đang hình thành, chưa nên hành động".

**Kết luận có bằng chứng, chưa phải cuối cùng:** nhiều khả năng đường stream thời gian thực
đang phát nhiều **snapshot của cùng một khung 5 phút chưa đóng** ra NATS, và engine coi mỗi
snapshot đó là một sự kiện đóng nến thật, chạy toàn bộ pipeline chiến lược trên dữ liệu
**chưa hoàn chỉnh**. Đây khác về bản chất so với lỗi phát lại (dead-man drill 07/09 đã kiểm
`num_redelivered`/JetStream — không phải nguyên nhân ở đây, `num_redelivered` luôn bằng 0
trong toàn bộ đợt 24).

**Mức độ nghiêm trọng:** nếu đúng, đây là lỗi ảnh hưởng **từ khi đường stream thời gian thực
lên sóng** — mọi tín hiệu MA/EMA/MACD và mọi lệnh trong số 18 lệnh đã ghi trong `orders`
(15/07 → 03/09) đều có khả năng được tính trên OHLC chưa đóng, không phải giá trị cuối cùng
của khung 5 phút. Việc này **chưa được xác nhận 100%** — cần bắt trực tiếp chuỗi message thô
trong một phiên tới mới chốt được, vì DB chỉ lưu giá trị cuối (upsert), không giữ lại lịch sử
các lần ghi đè trong ngày.

**Chưa sửa gì.** Đây là phát hiện cần một brief điều tra + sửa riêng, chạy trong phiên tới.

### 2.3. `heartbeat engine` có tươi trong khi `delivered.stream_seq` đứng im không?
- **Không.** Cả hai chỉ số đều hoạt động đồng bộ và phản ánh đúng trạng thái: `heartbeat engine` liên tục cập nhật theo chu kỳ định kỳ (gần nhất lúc `14:45:08`), đồng thời `delivered.stream_seq` cũng liên tục tịnh tiến theo từng nhịp bar được nhận. Không xuất hiện tình trạng "heartbeat xanh trong khi luồng bar bị đứt".

---

## 3. Kết Quả Quan Sát Token SSI (O-1)

- **Access Token**: Được hệ thống tự động làm mới (refresh) định kỳ qua `refresh_token` trong phiên giao dịch. Các mốc cập nhật `updated_at` và gia hạn `expires_at` ghi nhận được:
  - `09:42:16` (`expires_at: 1788922636`)
  - `10:27:41` (`expires_at: 1788925361`)
  - `11:13:07` (`expires_at: 1788928088`)
  - `13:29:26` (`expires_at: 1788936266`)
  - `14:45:12` (`expires_at: 1788940812`)
- **Refresh Token (`refresh_token_expires_at`)**: Giá trị đứng yên tại `1788944137` (~15:35:37 VN) xuyên suốt toàn bộ phiên giao dịch từ 09:00 đến 15:00.
- **Kết luận O-1**: `refresh_token` **không tự gia hạn** trong phiên, mà chỉ được sử dụng để lấy `access_token` mới cho tới khi chính `refresh_token` hết hạn.

---

## 4. Hạn Chế Của Phép Quan Sát

1. **Phạm vi quan sát giới hạn trong 1 phiên duy nhất (09/09/2026):**
   Kết quả chỉ phản ánh hành vi hoạt động trong một ngày giao dịch cụ thể, chưa bao quát các trường hợp thị trường biến động mạnh, nghẽn mạng NATS kéo dài, hoặc phiên giao dịch cuối tuần/nghỉ lễ.

2. **Bản chất đo lường là ảnh chụp thời điểm (Snapshot sampling):**
   Hàm `consumer_info` phản ánh trạng thái tại đúng thời điểm gọi lệnh (mỗi mốc cách nhau 45–135 phút). Không ghi nhận được các biến động vi mô tức thời giữa hai mốc (như độ trễ vài giây nếu collector gửi batch lớn).

3. **Rổ danh mục quan sát nhỏ và có mã bị câm về mặt chiến lược:**
   Cấu hình hiện tại chỉ theo dõi 3 mã (`HII, IJC, AAA`), trong đó `HII` đã được xác minh là không sinh tín hiệu mua (`WARN_NO_BULL` trên 3,287 bar do đặc tính phân phối giá trị). Do đó, tổng số lệnh sinh ra trong ngày bằng **0** là do không thỏa mãn điều kiện chiến lược, không phải do lỗi của pipeline tiếp nhận bar.
