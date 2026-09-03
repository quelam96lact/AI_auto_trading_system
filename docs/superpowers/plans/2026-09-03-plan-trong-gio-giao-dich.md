# Plan trong giờ giao dịch — phiên 03/09/2026

Viết 08:45 ngày 03/09, ngay trước phiên. Trạng thái dưới đây đã kiểm bằng lệnh
thật, không phỏng đoán.

---

## 0. Nói thẳng: hôm nay KHÔNG triển khai gì

Phiên 03/09 là **lần đầu tiên toàn bộ `trading/` chạy code hiện tại** kể từ
15/08. Mọi thay đổi chạm đường giao dịch từ giờ tới 14:45 là thêm một biến vào
phép đo — nếu có chuyện, ta mất khả năng trả lời "code nào gây ra".

Nên plan này chỉ có **quan sát và ghi số**. Không sửa `trading/`, không dựng
lại container, không `docker compose up --build`. Việc sửa bắt đầu **sau
14:45**, và hàng đợi đã có sẵn (B1, B2, BingX giai đoạn 2).

Plan này mỏng **có chủ ý**, không phải vì thiếu việc.

---

## 1. Trạng thái tiền phiên (đã xác minh 08:38–08:45)

| Thứ | Số đo thật | Đánh giá |
|---|---|---|
| Sáu container | Up 37 phút, postgres healthy, **restarts = 0** | OK |
| Token SSI | nạp lúc **08:37**, `ssi_auth_state` có 1 dòng | OK — đủ cả hai bước |
| `refresh_token` hết hạn | **16:37** hôm nay | phủ trọn 09:00–14:45 |
| `access_token` hết hạn | **08:52** hôm nay | xem mục 2 |
| Heartbeat | engine 08:38, collector 08:39 | tươi |
| Warm-up engine | HII/IJC/AAA, 21 bar, tới **28/08 14:45** | đúng — 28/08 là phiên gần nhất |
| Bốn tác vụ hẹn giờ | đều `Ready` | OK |
| 31/08, 01/09, 02/09 | đã khai trong `config.yaml: holidays` | đúng, không phải lỗ dữ liệu |

**Kết luận tiền phiên: sẵn sàng.** Không có việc gì phải làm trước 09:00.

---

## 2. T1 — 08:52: lần gia hạn access token đầu tiên (gấp nhất)

`access_token` chết lúc **08:52**, `refresh_token` sống tới 16:37. Tức trong
vài phút nữa đường `refresh` phải tự chạy. Đây là **lần đầu đường đó chạy trên
image mới**, và nó đứng giữa hệ thống với toàn bộ phiên.

Sáng nay log collector đã có một lần thất bại tạm thời:

```
WARN "account sync failed, skipping"
error: "SSI refresh_token missing/expired và tự authenticate() thất bại
        ([Errno -5] No address associated wi..."
```

Đó là **trước** khi token được nạp (08:37), và nguyên nhân là DNS (`Errno -5`)
chứ không phải logic sai — ngay sau đó `POST /auth/token` trả 200 và
`Authentication successful`. Nhưng nó cho thấy đường dự phòng có thật và có lúc
phải chạy.

**Kiểm lúc ~08:55:**

```bash
docker logs --since 10m ai_auto_trading_system-collector-1 2>&1 | grep -i "refresh\|auth"
docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "SELECT to_timestamp(expires_at) AT TIME ZONE 'Asia/Ho_Chi_Minh' FROM ssi_auth_state;"
```

- **Tốt:** `expires_at` đã nhảy quá 08:52, log có `Token refreshed successfully`.
- **Xấu:** `expires_at` đứng yên ở 08:52 và log lặp lỗi ⇒ **nạp lại token thủ
  công ngay** theo `DEPLOYMENT.md §8.5` (hai bước; bước hai là
  `load_token_to_db.py`). Đừng chờ tới 09:00 mới xử lý.

---

## 3. T2 — 09:00–09:10: có bar thật không

Câu hỏi duy nhất: **stream có sống không.** Trước 09:00 bảng `bars` có 0 dòng
hôm nay — đúng, chưa có gì để đếm.

```bash
docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "SELECT count(*), count(distinct symbol), max(ts) FROM bars WHERE ts >= current_date;"
docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "SELECT * FROM heartbeat;"
```

- **Tốt:** tới 09:10 có bar cho cả ba mã; `last_seen` của collector cách hiện
  tại dưới 3 phút.
- **Xấu:** 0 bar sau 09:10 ⇒ **không sửa code**. Đọc log collector, ghi nguyên
  văn lỗi. Nếu buộc phải khởi động lại, chỉ
  `docker compose restart collector` — **không build lại**, vì đổi image là huỷ
  phép đo hôm nay.

**Chốt kỷ luật:** `heartbeat_check` chạy 5 phút một lần trong 08:00–15:00. Nếu
stream chết mà điện thoại **không** kêu, lỗi lớn hơn nằm ở chuông báo chứ không
ở stream — ghi lại cả hai.

---

## 4. T3 — 09:15: chuỗi bar → NATS → engine, lần đầu trên image mới

09:15 là lúc thanh 5 phút đầu tiên đóng. Mắt xích này chưa từng chạy trọn vẹn
trên image hiện tại.

```bash
docker logs --since 20m ai_auto_trading_system-engine-1 2>&1 | tail -30
```

- **Tốt:** engine ghi nhận bar mới cho HII/IJC/AAA sau warm-up.
- **Xấu:** collector có bar trong DB nhưng engine im ⇒ đứt ở NATS. Ghi lại,
  **không sửa**. `real_trading_enabled = false` nên hậu quả duy nhất là mất một
  phiên đo, không mất tiền.

---

## 5. T4 — trong phiên: NAV tài khoản 0434226 = 0 (chỉ đo được lúc này)

Log sáng nay, trên tài khoản **có tiền thật**:

```
WARN "NAV tinh thieu: mot so ma khong dinh gia duoc (tinh 0)"
     account_no = 0434226   symbols = CAP,HCM,SSI,TCX,VCB   nav = 0.0
```

Ngoài giờ không định giá được là **hợp lý** — chưa có giá. Câu hỏi thật:
**trong phiên, khi đã có giá, NAV có tự hồi phục không?** Đây là mục duy nhất
trong plan bắt buộc phải đo trong giờ, không dời được.

**Kiểm lúc ~10:00, rồi lại lúc ~14:00:**

```bash
docker logs --since 30m ai_auto_trading_system-collector-1 2>&1 | grep "NAV"
docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "SELECT account_no, nav, ts FROM account_nav_snapshot ORDER BY ts DESC LIMIT 6;"
```

- **NAV > 0 trong phiên** ⇒ chỉ là hiện tượng ngoài giờ, hạ mức lo.
- **NAV vẫn = 0 giữa phiên** ⇒ lỗi định giá thật, nằm đúng trên đường sizing
  lệnh thật. **Ghi thành task cho sau 14:45**, không sửa trong phiên.

Nhắc lại điều đã biết (không phải phát hiện mới): engine lấy vốn thật từ NAV
của **0434221** (5.021.459 đ) trong khi tiền nằm ở **0434226**. Hôm nay vô hại
vì `config.yaml` bị khoá và `real_trading_enabled = false` — nhưng phải giải
quyết trước khi có ai nghĩ tới việc bật lệnh thật.

---

## 6. T5 — 11:30–13:00: phân biệt "im vì nghỉ trưa" với "im vì hỏng"

Bài học đắt nhất tuần này là hệ thống từng lẫn hai loại im lặng. Giờ nghỉ trưa
là dịp kiểm miễn phí.

- **Đúng:** `heartbeat_check` **không** gửi gì trong 11:30–13:00, rồi chạy bình
  thường trở lại sau 13:00.
- **Sai kiểu 1:** báo động lúc 12:00 ⇒ nó không biết giờ nghỉ trưa.
- **Sai kiểu 2:** im luôn cả sau 13:00 ⇒ nó chết chứ không phải đang chờ.

Kiểm lúc ~13:10: có bar mới sau 13:00 không, `last_seen` của collector có tiến
lên không.

---

## 7. T6 — 14:45: chốt số và mở khoá

```bash
docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "SELECT count(*) AS bars, count(distinct symbol) AS ma, min(ts), max(ts) FROM bars WHERE ts >= current_date;"
docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "SELECT * FROM orders WHERE created_at >= current_date;"
docker inspect -f "{{.RestartCount}}" ai_auto_trading_system-collector-1 ai_auto_trading_system-engine-1
```

Ghi vào báo cáo phiên: tổng bar, số mã, số lệnh giấy, số lần container tự khởi
động lại, và **mọi tin Telegram đã nhận cùng giờ nhận**.

**14:45 là mốc mở khoá.** Sau đó mới được chạm `trading/`: B1 (hợp đồng chiến
lược + sổ đăng ký), B2 (gộp `_print_safe`), rồi BingX giai đoạn 2.

---

## 8. ~~Lỗ dữ liệu 28/08~~ — SAI, KHÔNG CÓ LỖ NÀO (đã đính chính 14:50)

**Mục này viết sai và giữ lại nguyên trạng để không ai lặp lại lỗi.**

Sáng nay tôi kết luận `bars_daily` dừng ở 27/08 và phiên 28/08 thiếu bar daily
cho ~900 mã. **Không đúng.** Truy vấn lại theo giờ Việt Nam:

```
ngay_vn    | gio_vn              | count
2026-08-26 | 2026-08-26 00:00:00 |   912
2026-08-27 | 2026-08-27 00:00:00 |   862
2026-08-28 | 2026-08-28 00:00:00 |   965   <- CO DU
```

HII/IJC/AAA đều có bar 28/08 (8800 / 7410 / 7030).

**Nguyên nhân sai:** tôi dùng `ts::date`, mà `::date` quy đổi theo **UTC**. Bar
daily có `ts = 00:00 giờ VN` = `17:00 UTC ngày hôm trước — nên 28/08 VN hiện ra
thành "27/08" và tôi đọc thành thiếu một ngày.

**Bài học (đã có trong memory, hôm nay lặp lại):** so ngày trên bảng nào cũng
phải ép múi giờ trước — `(ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`. Một phép
so ngày sai múi giờ trông y hệt một lỗ dữ liệu thật.

Không cần chạy backfill bù. Lệnh backfill nêu ở bản cũ chạy ra `ok=0 skip=175`
— đúng, vì không có gì để nạp.

---

## 9. Việc KHÔNG làm hôm nay

| Việc | Vì sao không |
|---|---|
| Diễn tập dead-man's switch (D1) | Phải giết collector giữa phiên. Xếp cho phiên sau |
| Bật `real_trading_enabled` | Không chiến lược nào có lợi thế đo được. Không đổi |
| BingX giai đoạn 2 | `run_backtest` còn đóng cứng phí/thuế/T+3 VN, phải chờ B1 |
| Bất kỳ `docker compose build` nào | Đổi image giữa phiên = huỷ phép đo |
| Cố tình gây 429 để kiểm backoff (D2) | Bị cấm. Chỉ ghi nhận nếu 429 tự xảy ra |

---

## 10. Tiêu chí "phiên hôm nay thành công"

Thành công **không** phải là có lãi — engine chạy giấy, và không chiến lược nào
có lợi thế đo được.

Thành công là trả lời được ba câu, bằng số:

1. Đường dữ liệu SSI → bar → NATS → engine có chạy trọn phiên trên image mới
   không?
2. Bốn chuông báo có kêu đúng lúc cần và im đúng lúc phải im không?
3. Có lỗi nào mới xuất hiện mà hai tuần qua chưa từng thấy không?

Nếu cả ba đều trả lời được thì phiên này thành công — **kể cả khi câu trả lời
là "không, chỗ X hỏng"**. Biết chỗ hỏng vẫn là kết quả. Không biết mới là thất
bại.

---

## 11. Task sau 14:45 — NAV sai hai lớp (đã audit độc lập lúc 10:20)

Xác minh bằng đọc code và truy vấn DB thật, không dựa vào báo cáo.

**Lỗi 1 — `trading/storage/db.py:751`:** `if (now - ts).days > max_price_age_days`
đếm **ngày lịch**, trong khi docstring ngay phía trên hứa "ngay giao dich".
`bars_daily` mới nhất của cả 6 mã là **28/08** (không phải 27/08 — xem đính
chính mục 8); 28/08→03/09 = **6 ngày lịch > 5** ⇒ loại. Tính theo ngày giao
dịch thì giá chỉ **1 phiên tuổi** ⇒ sửa đúng chỗ này là đủ mở lại định giá.

**Lỗi 2 — `trading/collector/account_sync.py:143`:**
`storage.compute_nav(withdrawable, 0.0, ...)` — nợ nạp cứng `0.0`. Trên tài
khoản margin 0434226: `withdrawable = 0`, `total_debt = 68.607.848` ⇒
NAV = 0 + 0 − 0 = **0.0**. Cột `total_debt` **đã có sẵn** trong
`account_balance_snapshot` — sửa là đọc một cột đang nằm đó, không phải gọi
thêm API.

### Cảnh báo thứ tự — KHÔNG sửa lỗi 2 một mình

Sửa riêng lỗi 2 cho NAV = 0 − 68.607.848 = **âm 68,6 triệu**, tệ hơn hiện tại vì
số âm sâu có thể chạm logic rủi ro. **Hai lỗi phải sửa cùng một lần.**

### Số để nghiệm thu (tính từ DB, giá đóng cửa **28/08**)

| Mã | SL | Giá | Giá trị |
|---|---:|---:|---:|
| VCB | 1.500 | 60.100 | 90.150.000 |
| CAP | 1.200 | 43.200 | 51.840.000 |
| HCM | 1.000 | 26.050 | 26.050.000 |
| SSI | 1.200 | 21.350 | 25.620.000 |
| TCX | 160 | 40.800 | 6.528.000 |
| **Tổng** | | | **200.188.000** |

**NAV đúng = 200.188.000 − 68.607.848 = `131.580.152`** (± biến động giá 03/09).

Sau khi sửa, `account_nav_snapshot` của 0434226 phải ra con số cùng bậc này và
`unpriced_symbols` phải **rỗng**. Đó là tiêu chí nghiệm thu, không phải "chạy
được là xong".

### ĐÍNH CHÍNH — 0434221 KHÔNG có lỗi

Báo cáo giữa phiên nói HII cũng bị loại khỏi định giá trên 0434221. **Sai.**
Bằng chứng: `account_nav_snapshot` của 0434221 có `unpriced_symbols = {}`
(rỗng), và `account_position_snapshot` cho thấy 0434221 **không giữ mã nào** —
toàn bộ cổ phiếu nằm ở 0434226. NAV = 5.021.459 = `withdrawable` là **đúng**,
không phải trùng hợp do bị loại.

HII 300 mà engine đang giữ là **vị thế giấy** trong bảng `positions`, không phải
vị thế thật. Điều đáng lo ở 0434221 vẫn là điều đã biết từ trước — tiền thật
nằm ở 0434226 còn cấu hình trỏ 0434221 — nhưng đó là lựa chọn cấu hình, **không
phải lỗi tính NAV**.

---

## 12. Task sau 14:45 — chuông heartbeat kêu giả lúc mở phiên chiều

Bằng chứng, `logs/heartbeat.log:459–461` (đã tự đọc, nguyên văn):

```
2026-09-03 13:00:03 heartbeat-check start
[CRITICAL] dữ liệu ngừng chảy: bar cuối cùng 2026-09-03 04:25:00+00:00
           (95 phút trước) trong cửa sổ kiểm tra
EXIT=1
```

Trước và sau đều sạch: 12:00–12:55 tám lần liên tiếp `EXIT=0` (nghỉ trưa im
**đúng**), 13:05 trở đi `EXIT=0` (tự khỏi).

**Cơ chế:** cửa sổ kiểm tra mở lại lúc 13:00:00, nhưng bar 5 phút đầu của phiên
chiều mãi ~13:05 mới đóng. Ở đúng khoảnh khắc đó, bar mới nhất là bar cuối phiên
sáng (11:25) — cách 95 phút đồng hồ ⇒ vượt ngưỡng ⇒ CRITICAL + Telegram.

### Điều đáng chú ý: hai lỗi hôm nay là CÙNG một hình dạng

| | Đếm cái gì | Lẽ ra phải đếm |
|---|---|---|
| NAV (mục 11) | ngày **lịch** | ngày **giao dịch** |
| Heartbeat (mục này) | phút **đồng hồ** | phút **trong phiên** |

Cả hai đều đo bằng thời gian treo tường ở chỗ đáng lẽ phải đo bằng thời gian thị
trường. Tính theo thời gian trong phiên, bar 11:25 chỉ **5 phút tuổi** lúc
13:00 (11:25→11:30), không phải 95.

**Hệ quả cho cách sửa:** đừng vá riêng lẻ bằng một "dung sai 5 phút đầu phiên" —
đó là che triệu chứng và sẽ hở lại ở ranh giới khác (mở cửa 09:00, sau ngày lễ).
Nên có **một hàm chung tính tuổi theo thời gian thị trường**, đúng kỷ luật
một-công-thức-một-nơi (`4ea4c8d`), rồi cả hai chỗ cùng gọi.

**Ràng buộc bắt buộc:** `scripts/heartbeat_check.py` là dead-man's switch —
FEE-ALARM-2 vẫn có hiệu lực, **nó không bao giờ được ném exception**. Sửa xong
phải có test cho đúng thời điểm 13:00:03 này.

---

## 13. Báo cáo phiên 03/09 — đã kiểm chứng độc lập

| Hạng mục | Số đo | Nguồn |
|---|---|---|
| Bar | **134**, 3 mã, 09:00 → 14:45 | truy vấn DB |
| Lệnh giấy | **2 BUY**: IJC 400 @ 7.353,675 (09:15), AAA 400 @ 7.053,525 (09:20) | bảng `orders` |
| Container tự khởi động lại | **0 / 0** | `docker inspect` |
| Can thiệp tay | 1 — `restart collector` 09:12, **không build** | đúng luật mục 3 |

**Ba câu của mục 10:**

1. **Chuỗi dữ liệu chạy trọn phiên?** Có, sau một lần đứt WebSocket lúc 09:11
   (`Errno -5`, DNS) được xử lý đúng kỷ luật. Lần kết nối lại **lấp cả phần đầu
   phiên** — bar bắt đầu từ 09:00, không thủng.
2. **Chuông kêu đúng/im đúng?** Gần đúng: nghỉ trưa im đúng, chuông Docker của
   đợt 8 **kêu thật lần đầu** lúc 08:00, chuông feed kêu đúng lúc feed chết.
   Một cái sai: CRITICAL giả 13:00:03 (mục 12).
3. **Lỗi mới?** Hai, đều thật, đều đã ghi task và **không sửa trong phiên**.

**Kết luận: phiên thành công theo đúng định nghĩa mục 10** — cả ba câu đều trả
lời được bằng số, kể cả câu trả lời "chỗ X hỏng".

### Đính chính giữ nguyên (báo cáo cuối phiên nhắc lại chỗ đã sai)

Báo cáo nói *"HII 300 cũng bị loại dù có bar 5m hôm nay"*. Đo lại lúc chốt phiên
(`ts = 07:41 UTC`): `account_nav_snapshot` của **0434221** vẫn có
`unpriced_symbols = {}` **rỗng**, và `account_position_snapshot` cho thấy chỉ
**0434226** giữ mã thật (5 mã / 5.060 cp). 0434221 **không giữ vị thế thật nào**
⇒ không có gì để loại. NAV = 5.021.459 = `withdrawable` là **đúng**.

HII 300 là **vị thế giấy** trong bảng `positions`, không đi qua `compute_nav`.
Nhận định *"`read_latest_bar` ưu tiên `bars_daily` nên HII bị loại"* mô tả đúng
code nhưng **không phải điều đang xảy ra** — trên tài khoản thật, HII không có
mặt. Giữ đính chính này để bản sửa mục 11 không đi tìm một lỗi không tồn tại.
