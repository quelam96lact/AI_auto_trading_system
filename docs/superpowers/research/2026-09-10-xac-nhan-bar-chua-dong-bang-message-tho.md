# Xác nhận dứt điểm: stream phát nhiều snapshot của cùng một khung chưa đóng

Ngày: 10/09/2026, 08:30–08:45 (trước giờ mở cửa).
Người thực hiện: Claude (planner/auditor). Không có agent tham gia.
Trạng thái phát hiện: **đã xác nhận 100% bằng message thô**, không còn là giả thuyết.

---

## 1. Vì sao xác nhận được ngay, không phải đợi phiên sau

Brief đợt 24 kết luận "cần bắt message thô trong một phiên tới mới chốt được", vì DB dùng
`ON CONFLICT ... DO UPDATE` nên chỉ giữ giá trị cuối. **Kết luận đó đã bỏ sót một nguồn dữ
liệu:** JetStream giữ message 7 ngày (`STREAM_MAX_AGE_SECONDS = 7 * 24 * 3600`,
`trading/bus/publisher.py`). Toàn bộ message của phiên 09/09 vẫn còn nguyên trong stream.

Trạng thái stream đo lúc 08:26 ngày 10/09:

```
messages   : 4085
first_seq  : 22100
last_seq   : 26184
--- so message theo subject ---
    1664  bars.ssi.AAA
    1319  bars.ssi.IJC
    1102  bars.ssi.HII
```

`first_seq = 22.100` < `25.324` (mốc baseline 09:43 của đợt 24), nên dải seq
**25.325 → 26.184** của phiên 09/09 đọc lại được đầy đủ.

## 2. Phương pháp — chỉ đọc, không đụng stream

Dùng `js.get_msg("BARS", seq=N)`, ánh xạ tới `$JS.API.STREAM.MSG.GET` — lệnh **đọc** một
message theo số thứ tự. **Không** tạo consumer, **không** subscribe, **không** publish,
**không** xoá. Tuân thủ ràng buộc sau sự cố 13/08 (suite test từng xoá durable consumer của
engine thật và purge stream `BARS`).

Script: `scratchpad/replay_check.py` (chạy một lần, không lưu vào repo).

## 3. Kết quả

```
doc duoc      : 860 / 860 message
so bar duy nhat (symbol, ts): 120
trung binh message / bar     : 7.17
```

**860 message NATS ↔ chỉ 120 khung 5 phút duy nhất.** Tỷ lệ 7,17× khớp với dải 5,07–9,36×
mà tôi tính từ delta của đợt 24 — hai phép đo độc lập, cùng một kết luận.

Phân bố số lần một khung bị phát:

```
  phat   1 lan :   14 bar        phat  11 lan :    6 bar
  phat   2 lan :   11 bar        phat  12 lan :    5 bar
  phat   3 lan :   13 bar        phat  14 lan :    2 bar
  phat   4 lan :   12 bar        phat  15 lan :    2 bar
  phat   5 lan :    7 bar        phat  17 lan :    1 bar
  phat   6 lan :    9 bar        phat  18 lan :    2 bar
  phat   7 lan :   11 bar        phat  19 lan :    1 bar
  phat   8 lan :    5 bar        phat  20 lan :    1 bar
  phat   9 lan :    7 bar        phat  24 lan :    1 bar
  phat  10 lan :    6 bar        phat  25 lan :    1 bar
                                 phat  26 lan :    1 bar
                                 phat  27 lan :    1 bar
                                 phat  30 lan :    1 bar
```

Chỉ 14/120 khung được phát đúng một lần. Một khung bị phát tới **30 lần**.

## 4. Bằng chứng quyết định: OHLCV tiến hoá bên trong cùng một khung

Đây là phần loại bỏ mọi cách giải thích khác (phát lại, trùng lặp mạng, redelivery). Nếu là
phát lại thì payload phải **giống hệt nhau**. Thực tế payload **thay đổi đơn điệu**:

`AAA @ 2026-09-09T09:50:00+07:00` — 30 message, trích các mốc:

| seq | open | high | low | close | volume |
|---:|---:|---:|---:|---:|---:|
| 25369 | 7360 | 7360 | 7360 | 7360 | 200 |
| 25373 | 7360 | 7360 | 7350 | 7350 | 6.200 |
| 25380 | 7360 | 7370 | 7350 | 7370 | 20.000 |
| 25391 | 7360 | 7370 | 7350 | 7360 | 51.000 |
| 25403 | 7360 | **7380** | 7350 | **7380** | **123.800** |

- `volume` tăng đơn điệu 200 → 123.800: đây là volume **luỹ kế trong khung**, không phải
  volume của tick.
- `high` nới rộng dần 7360 → 7370 → 7380; `low` co xuống 7360 → 7350.
- `open` **bất biến** 7360 suốt 30 message — đúng đặc trưng của một khung đang hình thành.
- `close` dao động qua lại (7360 → 7350 → 7370 → 7360 → 7380) — đây chính là giá cuối **tạm
  thời** tại mỗi thời điểm.

Hai khung khác kiểm chứng chéo, cùng một hình thái:

- `AAA @ 13:05` — 27 message, close 7280 → 7320, volume 100 → 109.600.
- `AAA @ 09:45` — 26 message, close 7390 → **7350** (đảo chiều giảm), volume 100 → 166.400.

Khung 09:45 đáng chú ý nhất: engine nhận `close = 7390` ngay message đầu, rồi 7400, 7380,
7370, 7360... và giá trị **đúng** khi khung đóng là 7350. Engine đã chạy toàn bộ pipeline
chiến lược **26 lần** trên 26 giá trị close khác nhau của cùng một cây nến.

## 5. Kết luận

1. `IntervalMessage` của SSI là **snapshot nến đang chạy**, không phải sự kiện đóng nến.
   Không có trường nào đánh dấu khung đã đóng (`ssi_sdk/models/streaming.py:105-130`).
2. `on_stream_message` (`trading/collector/main.py:101-116`) gọi `persist_bars` cho **mọi**
   snapshot → mỗi snapshot là một message NATS riêng.
3. `process_bar` (`trading/engine/logic.py`) xử lý **vô điều kiện** → chiến lược, trailing
   stop, và sinh tín hiệu chạy trên OHLC **chưa hoàn chỉnh**, trung bình 7 lần mỗi cây nến.
4. `BarAggregator` (`trading/collector/aggregator.py`) tồn tại và có test, nhưng **không nằm
   trong đường chạy thật** — chỉ được tham chiếu ở `aggregator.py`, `test_aggregator.py`.
   Nó cũng **không dùng lại được trực tiếp**: `add_tick` nhận `Tick` và **cộng dồn**
   `volume` (dòng 43), trong khi snapshot SSI đã mang volume luỹ kế sẵn → đưa snapshot vào
   sẽ nhân volume lên nhiều lần.

## 6. Phạm vi thiệt hại — và phần KHÔNG bị ảnh hưởng

**Bị ảnh hưởng:** mọi tín hiệu engine sinh ra theo thời gian thực kể từ khi đường stream lên
sóng, gồm cả 18 lệnh trong bảng `orders` (15/07 → 03/09). Chúng được tính trên giá chưa
chốt.

**KHÔNG bị ảnh hưởng — đã kiểm chứng:** bảng `bars` trong DB **không hỏng**. Vì
`ON CONFLICT (symbol, ts) DO UPDATE` (`trading/storage/db.py:31`) luôn ghi đè bằng snapshot
mới nhất, giá trị còn lại trong DB chính là snapshot **cuối cùng** của khung — tức giá trị
đúng khi khung đóng. Do đó:

- Mọi backtest (đọc từ DB) **không bị sai lệch** vì lỗi này.
- Cổng cứng VN `-1.615.319.902 | 1.514 lệnh | 439 mã` **vẫn là mốc so sánh hợp lệ**.
- Không cần chạy lại phép đo crypto vì lý do này.

**Chưa sửa gì tại thời điểm viết báo cáo.** Hướng sửa giao trong brief đợt 26.
