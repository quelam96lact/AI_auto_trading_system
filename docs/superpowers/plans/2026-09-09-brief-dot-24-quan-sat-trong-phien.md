# Brief đợt 24 — Việc chỉ làm được TRONG PHIÊN: chứng minh engine đang tiêu thụ bar

Ngày giao: 09/09/2026, **09:50 — phiên đang mở** (09:00–15:00).
Base: `300267d` (main), cây làm việc sạch, 620 test xanh, ruff sạch.
Người giao: Claude (planner/auditor).

**Đây là brief nhạy thời gian.** Mọi task phải xong trước **15:00 hôm nay**. Nếu bắt đầu
muộn, giảm số lần lấy mẫu ở Task 2 chứ không bỏ Task 1.

---

## 1. Việc cần phiên nào ĐÃ ĐÓNG — đừng làm lại

| Việc | Trạng thái |
|---|---|
| **D1** — diễn tập dead-man's switch | **ĐÃ ĐÓNG 07/09.** Chuông kêu thật, độ trễ đo được **3 phút 28 giây**, có bằng chứng tự kiểm trong `2026-09-07-kich-ban-dien-tap-dead-man-switch.md` |
| Chuỗi bar → tín hiệu → lệnh | **Đã chứng minh.** `orders` có 18 lệnh từ 15/07, gần nhất 03/09 (IJC 400, AAA 400) — sinh từ bar thật trong phiên |
| **D2** — backoff 429 thực địa | Không giao được: chỉ xảy ra khi có 429 thật, và **cấm cố tình gây ra** |

**Không tắt Docker lần nữa.** Diễn tập đó đã có kết quả; lặp lại chỉ mất bar.

---

## 2. Khoảng trống thật sự còn lại: không có tín hiệu nào chứng minh engine đang NHẬN bar

Tôi kiểm sáng nay, trong phiên:

- Bar đang chảy: `AAA/HII/IJC` mỗi mã 3 bar, 09:15 → 09:25.
- `heartbeat`: `engine` 09:29:30, `collector` 09:29:08 — cả hai tươi.
- Log engine: im lặng hoàn toàn sau warm-up.

Im lặng đó **không phải lỗi** — `trading/engine/logic.py::process_bar` không log gì cả, chỉ
log khi có tín hiệu. Nhưng nó cũng **không phải bằng chứng đang chạy**. Và hai chuông hiện có
đều không lấp được chỗ này:

| Chuông | Thật sự giám sát cái gì | Có bắt được "NATS → engine đứt" không? |
|---|---|---|
| Dead-man (`heartbeat`) | `storage.beat("engine")` nằm trong `idle_maintenance()` (`engine/main.py:340-344`) — chạy **theo nhịp thời gian** | **Không.** Tiến trình vẫn sống ⇒ vẫn tươi |
| Chuông 2A "dữ liệu ngừng chảy" | Bar trong DB — tức **đầu ra của collector** | **Không.** Collector vẫn ghi bar bình thường |

→ Nếu đường NATS → engine đứt: **2A xanh, dead-man xanh, engine không giao dịch gì**, và nhìn
từ bên ngoài **không phân biệt được** với "hôm nay chiến lược không có tín hiệu".

Đây đúng lớp sự cố dự án đã dính: **14/08** — refresh token hết hạn 13:39, feed chết 14:33,
**heartbeat xanh suốt**. Docstring `scripts/heartbeat_check.py:10-13` ghi rõ 2A không bắt
được sự cố đó, phải thêm 2B mới bắt được. Lần này là cùng một hình dạng, ở một mắt xích khác.

**Vì sao phải làm trong phiên:** ngoài phiên không có bar nào chảy, nên không phân biệt được
"engine không nhận bar" với "không có bar để nhận". Phép đo này chỉ có nghĩa khi thị trường mở.

---

## 3. Ràng buộc — đợt này CHỈ ĐỌC

Phiên đang chạy tiền thật của hệ thống giám sát. Mọi thứ dưới đây là **cấm tuyệt đối hôm nay**:

- **Không** `docker compose stop/start/restart/build/up`. Không restart container nào.
- **Không** sửa `trading/`, `config/config.yaml`, `docker-compose.yml`, `Dockerfile`, `.env`.
- **Không** bật `real_trading_enabled`.
- **Không** `delete`, `purge`, `add`, `update` bất kỳ stream hay consumer NATS nào.
  Nhắc lại sự cố **13/08**: suite test đã **xoá durable consumer của engine thật**, purge
  stream `BARS`, ghi đè `engine_state`. Đó là lý do ISO-1 tồn tại. Đợt này chỉ được gọi
  **`consumer_info()`** — hàm đọc, không có tác dụng phụ.
- **Không** ghi vào DB. Chỉ `SELECT`.
- **Không** gọi SSI, không gọi BingX.
- **Không commit, không push.**
- Sửa code duy nhất được phép: **tạo mới** `scripts/probe_engine_consumer.py` (Task 1).
  Không sửa file nào có sẵn.

**Nếu bất kỳ bước nào đòi restart hay sửa engine để làm tiếp: DỪNG, báo cáo.** Việc vá khoảng
trống quan sát là brief riêng, làm **ngoài phiên**.

---

## Task 1 — Viết probe đọc trạng thái consumer của engine

### 1.1. Việc

Tạo `scripts/probe_engine_consumer.py`. Dùng `nats-py` (đã có trong `pyproject.toml`), kết nối
`NATS_URL` (mặc định `nats://localhost:4222`), rồi gọi **đúng một hàm đọc**:

```python
info = await js.consumer_info("BARS", "engine")
```

Tên đúng đã kiểm: stream `BARS`, durable consumer **`engine`** (`trading/engine/main.py:302-304`).

In ra, mỗi dòng một giá trị, kèm mốc thời gian VN:

| Trường | Ý nghĩa |
|---|---|
| `num_pending` | Bar đã publish mà engine **chưa nhận**. Đây là con số quan trọng nhất |
| `num_ack_pending` | Đã giao, chưa ack |
| `delivered.stream_seq` | Bar cuối engine đã nhận |
| `ack_floor.stream_seq` | Bar cuối engine đã ack |
| `num_redelivered` | Số lần giao lại (dấu hiệu engine xử lý lỗi) |

Nếu SDK không có trường nào trong danh sách: in những gì có và **ghi rõ trường nào không có**,
không bịa.

### 1.2. Ràng buộc code

- **Chỉ đọc.** Trong file không được có `delete`, `purge`, `add_consumer`, `update_consumer`,
  `publish`, `subscribe`. Agent phải tự `grep` file mình vừa viết để xác nhận và dán kết quả.
- Không dùng `--durable` mới, không tạo consumer phụ.
- Đóng kết nối sạch (`await nc.close()`).
- Không ghi DB, không gửi Telegram.

### 1.3. Kiểm chứng

- Chạy được, in ra số, exit 0.
- `git status` chỉ thêm **một** file mới.
- `uv run ruff check scripts` sạch.
- Dán output lần chạy đầu vào báo cáo.

---

## Task 2 — Lấy mẫu xuyên phiên

### 2.1. Bốn mốc

Lấy mẫu tại **10:30, 11:15, 13:30, 14:45** (giờ VN). Nếu bắt đầu muộn hơn mốc nào thì bỏ mốc
đó và ghi rõ là đã bỏ — **không dồn hai mốc sát nhau**, vì mục đích là thấy biến thiên qua
phiên, gồm cả nghỉ trưa 11:30–13:00.

### 2.2. Mỗi mốc ghi đúng năm số

```powershell
# 1. Trang thai consumer
uv run python scripts/probe_engine_consumer.py

# 2-5. Trang thai DB
docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "
SET TimeZone='Asia/Ho_Chi_Minh';
SELECT 'bar hom nay' AS muc, count(*)::text AS gia_tri FROM bars WHERE ts::date = CURRENT_DATE
UNION ALL SELECT 'bar HII hom nay', count(*)::text FROM bars WHERE ts::date = CURRENT_DATE AND symbol='HII'
UNION ALL SELECT 'heartbeat engine', max(last_seen)::text FROM heartbeat WHERE service='engine'
UNION ALL SELECT 'heartbeat collector', max(last_seen)::text FROM heartbeat WHERE service='collector'
UNION ALL SELECT 'lenh hom nay', count(*)::text FROM orders WHERE ts::date = CURRENT_DATE;"
```

### 2.3. Điều phải đọc ra từ số liệu

Câu hỏi cần trả lời, **kèm bằng chứng**:

1. **`num_pending` có tăng dần qua các mốc không?** Tăng đều ⇒ engine **không** tiêu thụ kịp
   hoặc không tiêu thụ. Quanh 0 ⇒ engine đang nhận bar bình thường.
2. **`delivered.stream_seq` có tiến lên giữa các mốc không?** Đứng im trong khi số bar trong DB
   tăng ⇒ **đúng kịch bản NATS → engine đứt**. Đây là phát hiện quan trọng nhất nếu xảy ra.
3. **`heartbeat engine` có tươi trong khi `delivered.stream_seq` đứng im không?** Nếu có,
   đó là **bằng chứng trực tiếp** cho khoảng trống ở §2 — chuông xanh trong khi engine điếc.

### 2.4. Nếu phát hiện engine KHÔNG nhận bar

**Không tự sửa. Không restart.** Báo cáo ngay, kèm cả năm số của mốc phát hiện. Việc khôi phục
là quyết định của chủ dự án — restart engine giữa phiên có cái giá riêng, và JetStream sẽ giao
lại bar chưa ack nên **không mất dữ liệu**, nhưng thời điểm là việc của chủ dự án.

---

## Task 3 — Quan sát token SSI qua phiên (O-1)

Cùng bốn mốc ở Task 2, thêm:

```powershell
docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "
SET TimeZone='Asia/Ho_Chi_Minh'; SELECT * FROM ssi_auth_state;"
```

Ghi lại `refresh_token_expires_at` ở từng mốc. Câu hỏi cần trả lời: **token có tự gia hạn
trong phiên không, hay đứng im cho tới khi hết hạn?** Đây là việc O-1 đang treo, và chỉ trả
lời được bằng cách nhìn nó thay đổi (hoặc không) qua nhiều giờ.

**Không làm OTP, không gọi SSI.** Chỉ đọc bảng.

---

## Task 4 — Báo cáo phiên

Tạo `docs/superpowers/research/2026-09-09-dot-24-quan-sat-trong-phien.md`, **đúng 4 mục**:

1. **Bảng bốn mốc × chín cột** (5 số Task 2 + `refresh_token_expires_at` + 3 trường consumer
   quan trọng). Một bảng, đọc được biến thiên theo hàng.
2. **Trả lời ba câu hỏi ở §2.3**, mỗi câu kèm số cụ thể làm bằng chứng.
3. **Kết quả O-1**: token có gia hạn trong phiên không.
4. **Hạn chế của phép quan sát này** — tối thiểu ba điều:
   - Chỉ một phiên, một ngày. Không suy ra được hành vi mọi phiên.
   - `consumer_info` là ảnh chụp tại thời điểm gọi, không phải chuỗi liên tục — giữa hai mốc có
     thể có biến động không thấy được.
   - Rổ mã chỉ có 3 mã (`HII, IJC, AAA`), và HII đã biết là câm (0 tín hiệu bull trên 3.287
     bar, đợt 22 Task 7). Số lệnh bằng 0 trong phiên **không** chứng minh engine hỏng.

**Không viết kết luận, không khuyến nghị.** Mục 4 là hạn chế, không phải kết luận.

---

## 5. Tiêu chí dừng

| Tình huống | Dừng ở đâu |
|---|---|
| Bất kỳ bước nào đòi restart / rebuild / sửa engine | Ngay |
| `consumer_info` báo consumer `engine` không tồn tại | **Ngay — đây là sự cố nghiêm trọng**, báo cáo, không tự tạo lại |
| Cần gọi hàm NATS có tác dụng phụ mới lấy được số | Ngay — báo cáo là không lấy được, đừng gọi |
| Phát hiện engine không nhận bar | Hoàn tất mốc đang làm, báo cáo ngay, **không sửa** |
| Đã quá 15:00 | Dừng lấy mẫu, viết báo cáo với số mốc đã có |
| Cần gọi SSI hoặc BingX | Ngay |

---

## 6. Báo cáo nghiệm thu — đúng 5 mục

1. Task 1: nội dung `scripts/probe_engine_consumer.py` + kết quả `grep` chứng minh không có
   hàm ghi + output lần chạy đầu + ruff.
2. Task 2: bốn mốc, mỗi mốc năm số, nguyên văn.
3. Task 3: `ssi_auth_state` ở bốn mốc.
4. Task 4: đường dẫn + nội dung file báo cáo.
5. `git status` (kỳ vọng: **một** file script mới + **một** file báo cáo mới, không sửa file
   nào có sẵn), `git diff --stat HEAD` (kỳ vọng **rỗng**), `docker ps` (6 container `Up`,
   **uptime không reset**), `uv run pytest -q`, `uv run ruff check trading tests scripts`.

---

## 7. Việc KHÔNG thuộc đợt này

- **Không** vá khoảng trống quan sát ở §2. Việc thêm một tín hiệu quan sát được theo bar
  (ví dụ: cho `storage.beat` chạy theo bar thay vì theo nhịp, hoặc thêm chuông 2C giám sát
  `num_pending`) đụng `trading/engine/main.py` ⇒ phải rebuild + restart ⇒ **làm ngoài phiên**,
  brief riêng.
- **Không** sửa HII câm.
- **Không** bật giao dịch thật.
- **Không** diễn tập dead-man lần nữa.

## 8. Sau đợt này

Đợt này trả lời đúng một câu: **engine có đang thật sự tiêu thụ bar trong phiên không, và ta
có cách nào biết điều đó không.**

- Nếu `num_pending` quanh 0 và `delivered.stream_seq` tiến đều ⇒ engine khoẻ, và ta vừa có
  **công cụ đọc trạng thái đó bất cứ lúc nào** — thứ trước đây không có.
- Nếu `delivered.stream_seq` đứng im trong khi bar vào DB ⇒ đã tìm ra một lỗi câm mà cả hai
  chuông hiện tại đều không bắt được, đúng lớp sự cố 14/08.

Cả hai kết cục đều là đầu vào cho brief kế tiếp: biến probe này thành **chuông 2C** chạy tự
động, để lần sau không cần ai ngồi canh.
