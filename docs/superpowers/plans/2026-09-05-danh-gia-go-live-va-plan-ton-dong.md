# Đánh giá khả năng go-live + plan xử lý tồn đọng

Viết 05/09/2026 (thứ Bảy, không có phiên). HEAD `6caa997`.
Mọi con số dưới đây **đo hôm nay**, không lấy lại từ tài liệu cũ.

---

## 0. Kết luận ngắn

**Chưa go-live được.** Nhưng lý do quan trọng nhất không nằm trong danh sách tồn
đọng cũ — nó được tìm ra trong chính lượt rà soát này:

> **Engine hiện tại không thể sinh ra một tín hiệu mua nào.** Không phải "ít
> lệnh", mà là **không bao giờ**. Chạy octopus trên toàn bộ bar 5 phút đang có
> trong DB cho ba mã đang cấu hình: **0 tín hiệu `bull`**.

Hệ thống đang chạy, chuông kêu đúng, heartbeat tươi, test xanh — và **câm**.
Đây là dạng hỏng tệ nhất: mọi đèn đều xanh.

---

## 1. Phát hiện chính — ngưỡng thanh khoản là ngưỡng của bar NGÀY, engine ăn bar 5 PHÚT

### 1.1 Bằng chứng

`octopus_pullback.min_avg_value_20 = 2_000_000_000` nghĩa là "bình quân giá trị
giao dịch 20 **phiên** trước ≥ 2 tỷ" — một ngưỡng hợp lý cho **bar ngày**. Engine
thì nhận bar **5 phút** (`main.py:279` subscribe `bars.>`, collector gộp 1m→5m).
Với bar 5 phút, cùng con số đó có nghĩa "bình quân 20 **bar 5 phút** (≈100 phút)
≥ 2 tỷ" — cao gấp khoảng 78 lần ý định ban đầu.

Đo trên chính bảng `bars` mà engine đọc lúc warm-up:

```
ma      so bar 5 phut   BQ gia tri/bar        cong thanh khoan MO    tin hieu bull
HII             3.211      158.777.024                    0 bar               0
IJC             4.719      313.289.307                   24 bar               0
AAA             4.597      180.083.902                    0 bar               0
```

Bình quân giá trị một bar 5 phút của ba mã này là **159–313 triệu**, thấp hơn
ngưỡng 2 tỷ khoảng **6–12 lần**. Trong hơn 12.500 bar lịch sử, cổng mở đúng
**24 lần** (0,2%), và không lần nào đủ để thành tín hiệu.

### 1.2 Vì sao chưa ai thấy

- `real_trading_enabled: false`, nên "engine không đặt lệnh" trông đúng như
  thiết kế.
- PaperBroker vẫn giữ ba vị thế mở (HII 300, IJC 400, AAA 400) — **mở từ thời
  sma_cross**, lệnh cuối 03/09. Nhìn dashboard vẫn thấy vị thế, vẫn thấy NAV.
- Octopus vẫn **thoát** được lệnh: `on_bar` đặt TP cho vị thế thừa kế ngay bar
  đầu thấy `held > 0`. Nên hệ thống có thể BÁN, chỉ không bao giờ MUA.
- Đổi sang octopus lúc 04/09 sau giờ đóng cửa ⇒ **chưa có phiên nào chạy thật
  với octopus**. Thứ Hai 07/09 mới là phiên đầu tiên.

### 1.3 Đây là lần thứ NĂM cùng một hình dạng lỗi

Một con số đúng trong hệ quy chiếu này, mang sang hệ quy chiếu khác mà nhìn vẫn
hợp lý:

| # | Ở đâu | Nội dung |
|---|---|---|
| 1 | phép đo crypto | lô 100 (HOSE) áp lên crypto |
| 2 | phép đo crypto | `min_avg_value_20` = 2 tỷ **VND** áp lên giá trị **USDT** |
| 3 | rổ BingX | `1000PEPE` (perp) so với `PEPE` (spot), lệch 1.000 lần |
| 4 | test gói S | cùng ngưỡng 2 tỷ áp lên bar tổng hợp volume 100.000 |
| **5** | **SẢN XUẤT** | **cùng ngưỡng 2 tỷ áp lên bar 5 phút thay vì bar ngày** |

Bốn lần đầu ở phòng thí nghiệm. Lần này ở engine đang chạy.

### 1.4 Hệ quả rộng hơn con số đó — toàn bộ phép đo là bar NGÀY

Không chỉ ngưỡng thanh khoản. **Mọi tham số** của cả hai chiến lược đều được đo
trên `bars_daily`, trong khi engine chạy trên bar 5 phút:

| tham số | ý nghĩa khi đo (bar ngày) | ý nghĩa khi chạy (bar 5 phút) |
|---|---|---|
| octopus `ema_trend=200` | xu hướng 200 phiên ≈ 10 tháng | ≈ 200 bar ≈ **4 phiên** |
| octopus `min_avg_value_20` | thanh khoản 20 phiên | thanh khoản **100 phút** |
| sma_cross `fast=10 / slow=20` | 10/20 phiên | **50/100 phút** |
| `atr_period=14` | 14 phiên | **70 phút** |

Nên báo cáo `2026-09-01-strategy-comparison-v2.md` (−1,6 tỷ cho octopus, −14,1
tỷ cho sma_cross) **không mô tả cái engine đang chạy**. Nó mô tả cùng đoạn code
với một ý nghĩa tham số hoàn toàn khác. Kết luận "không chiến lược nào thắng
mua-và-giữ" vẫn đứng cho khung ngày; còn khung 5 phút thì **chưa ai đo**.

sma_cross không lộ ra vì nó **không có cổng thanh khoản** — nó vẫn ra lệnh
(18 lệnh trong `orders`), chỉ là ra lệnh theo một bộ tham số chưa từng được đo ở
khung này. Octopus có cổng, nên cổng đóng sập và lộ ra vấn đề.

---

## 2. Trạng thái hệ thống hôm nay — cái gì đang lành

Ghi lại cho công bằng: phần hạ tầng chạy tốt.

| Hạng mục | Trạng thái đo hôm nay |
|---|---|
| 6 container | Up, postgres healthy |
| Heartbeat | collector 09:19, engine 09:18 (tươi) |
| Log 24h | **1 WARN** duy nhất: `account sync failed` — lỗi DNS thoáng qua |
| 4 tác vụ hẹn giờ | cả 4 chạy 04/09, `result=0`, lịch kế 07/09 |
| Dữ liệu phiên 04/09 | có bar cho cả ba mã, 09:00→14:45 |
| `bars_daily` | 2.983.253 dòng, mới nhất 03/09 |
| Snapshot tài khoản thật | tươi (02:15 UTC hôm nay), cả balance/position/buying-power |
| Test | 423 unit + 100 integration xanh, ruff sạch |
| Đường lệnh thật | **có người bấm nút**: engine chỉ tạo `pending_order` + WARN, người chạy `confirm_real_order.py <id>` mới đặt |

Kiến trúc an toàn vẫn nguyên: không có đường nào đặt lệnh tự động.

---

## 3. Các chặn go-live, xếp theo thứ tự thật

### Tầng 1 — chặn bất kể kỹ thuật

**1.1 Chiến lược chưa có lợi thế đo được, và cái đang chạy thì không đo được.**
Khung ngày: cả ba chiến lược đều thua mua-và-giữ (báo cáo 01/09). Gói Q hôm qua
đóng thêm một đinh: octopus **không chọn sai mã** — trên đúng 439 mã nó vào
lệnh, mua-và-giữ lãi trung vị +765 triệu/mã, còn nó **lỗ** trung vị −5,1
triệu/mã. Khung 5 phút (cái engine thật sự chạy): **chưa có phép đo nào**.

Bật tiền thật lúc này là trả phí thật để chạy một chiến lược hoặc đã đo là lỗ,
hoặc chưa từng đo ở khung nó đang chạy.

**1.2 Engine đang câm** (mục 1). Bật `real_trading_enabled` bây giờ cũng không
sinh lệnh nào — trừ lệnh BÁN vị thế thừa kế.

### Tầng 2 — chặn cứng nếu vẫn muốn bật

**2.1 Mục J.** Octopus không bao giờ phát `"bear"`, mà `real_orders.py:46,75` rẽ
nhánh theo `"bull"`/`"bear"` ⇒ đường lệnh thật chỉ MUA, không bao giờ BÁN. Đã có
chốt test chặn (`tests/test_real_trading_guard.py`) — bật cờ mà chưa xử J thì
suite đỏ.

**2.2 Mục E — nặng hơn "cấu hình nhầm tài khoản".** Đo hôm nay:

```
0434221  balance =   5.021.712   withdrawable = 5.021.712   debt =          0
0434226  balance = -17.328.293   withdrawable =         0   debt = 17.328.020
```

Engine đang lấy NAV từ **0434221** (log: `"NAV lam real capital", nav 5021712`).
Tiền thật nằm ở **0434226** — nhưng tài khoản đó **rút được 0 đồng**, đang nợ
margin 17,3 triệu, và giữ sẵn vị thế thật (VCB 1.500, FOX 1.100, SSI 1.200,
HCM 1.000, TCX 160). Nên E **không phải sửa một dòng config**: phải quyết bot
được dùng bao nhiêu vốn và trên tài khoản nào, khi tài khoản "có tiền" thực ra
là tài khoản đang vay.

### Tầng 3 — vận hành

| Mã | Việc | Trạng thái |
|---|---|---|
| **C1** | VPS Ubuntu | `DEPLOYMENT.md` (446 dòng) đã sẵn, **chưa thực hiện** — hệ thống đang chạy trên máy dev Windows |
| **C2** | Docker tự khởi động | vẫn bật tay |
| **D1** | Diễn tập dead-man's switch | **chưa từng diễn tập** — chuông chưa bao giờ được chứng minh là kêu thật |
| — | Image cũ | lệch **9 giờ 3 phút** so với commit gần nhất chạm `trading/` |
| **C3** | Lịch nghỉ lễ | 2026 xong (kiểm ngược DB, 13/13 ngày). **2027 chưa có nguồn** |

---

## 4. Plan xử lý — thứ tự đề xuất

### 4.1 Việc của Claude, làm được ngay (không cần quyết định gì)

**Z1. Dựng lại image.** Ba gói Q/R/S không chạm `trading/`, nhưng gói L (`bb8d340`)
thì có. Hôm nay thứ Bảy, dựng lúc nào cũng an toàn. **Nên gộp với quyết định
mục 1** nếu chủ dự án trả lời sớm — nếu đổi ngưỡng hoặc đổi chiến lược thì dựng
một lần là đủ.

### 4.2 Giao được cho agent ngay — không phụ thuộc quyết định nào

**Gói X — chốt chặn "engine câm".** Lỗi ở mục 1 lẽ ra phải tự lộ ra. Viết một
chốt: với mỗi mã trong `cfg.symbols`, dùng chính dữ liệu bar mà engine tiêu thụ,
kiểm xem cổng của chiến lược có **từng** mở trong N phiên gần nhất không; không
mở lần nào ⇒ **CRITICAL**, vì đó là engine không thể ra lệnh.

- Đối chứng dương có sẵn và rất mạnh: chạy hôm nay nó **phải đỏ** cho HII và AAA
  (0/3.211 và 0/4.597 bar). Sửa ngưỡng xong thì phải xanh. Không cần dựng dữ
  liệu giả — đây là lý do gói này đáng làm trước.
- Phạm vi: `scripts/` + `tests/`. **Không sửa `trading/`**, không sửa config.

**Gói Y — đo octopus (và sma_cross) trên bar 5 PHÚT.** Phép đo còn thiếu, và nó
là đầu vào cho mọi quyết định về chiến lược. Dùng lại `run_backtest`, nhưng đọc
`bars` thay vì `bars_daily`, trên rổ mã có bar 5 phút. Báo cáo cả hai chiến lược
cạnh mốc mua-và-giữ cùng kỳ.

- Ràng buộc: **không sửa `trading/`**, đặc biệt không tự ý đổi `min_avg_value_20`
  — muốn thử ngưỡng khác thì truyền tham số vào strategy khi khởi tạo, và nói rõ
  trong báo cáo đã dùng ngưỡng nào.
- Kết quả cần trả lời được: ở khung 5 phút, ngưỡng thanh khoản nào cho cỡ mẫu đủ
  để kết luận, và ở ngưỡng đó chiến lược lãi hay lỗ.

### 4.3 Chờ chủ dự án — không nên để agent tự chọn

| Mã | Câu hỏi | Ghi chú mới sau lượt rà soát này |
|---|---|---|
| **G** | Giữ octopus, quay lại sma_cross, hay không chạy chiến lược nào? | **Câu hỏi đã đổi bản chất.** "Giữ octopus" hiện nghĩa là "giữ một engine câm". Giữ thì phải kèm sửa ngưỡng cho khung 5 phút — mà con số mới thì chưa ai đo (gói Y) |
| **K** | Ngưỡng `min_avg_value_20` | Không còn là câu chuyện riêng của crypto: **sai cả cho bar 5 phút cổ phiếu VN**. Có thể lời giải đúng là tham số theo khung thời gian, không phải một hằng số |
| **J** | Nối đường thoát lệnh thật vào tín hiệu SELL của `on_bar`, hay đổi chiến lược? | Chỉ cần trả lời nếu chọn tiến tới tiền thật |
| **E** | Bot dùng vốn nào, tài khoản nào? | Xem 2.2 — 0434226 rút được 0 đồng và đang nợ |
| **F** | BingX spot hay perpetual, có đòn bẩy không? | số liệu đã có và đã đính chính |
| **C1/C2** | VPS Ubuntu, Docker tự khởi động | tài liệu sẵn, chỉ cần quyết làm |
| **C3** | Lịch nghỉ lễ 2027 | phải tra lại có nguồn; 2026 đã xong |
| **D1** | Ngày diễn tập dead-man's switch | cần một phiên thật, sớm nhất thứ Hai 07/09 |

### 4.4 Thứ tự tôi khuyến nghị

1. **Gói X trước tiên.** Nó biến lỗi vừa tìm được thành lỗi không thể tái diễn
   trong im lặng. Đây là lần thứ năm của cùng một hình dạng lỗi — chi phí của
   việc không có chốt đã được chứng minh năm lần.
2. **Gói Y song song.** Không có nó thì mục G và K không có cơ sở để trả lời.
3. **Trả lời G + K** khi có số của Y.
4. **Dựng lại image** một lần, sau khi G/K đã chốt.
5. **D1** vào một phiên thật, sớm nhất 07/09.
6. C1/C2 khi nào chủ dự án muốn rời máy dev.
7. J và E chỉ cần trước khi thật sự bật tiền thật — mà điều đó còn xa, vì tầng 1
   chưa gỡ.

---

## 5. Điều KHÔNG làm

- Không bật `real_trading_enabled`, kể cả để thử.
- **Không "sửa nhanh" `min_avg_value_20` cho hết câm.** Ngưỡng đó là câu hỏi kinh
  tế, và một con số đoán bừa sẽ mở cổng cho một chiến lược chưa được đo ở khung
  5 phút — thay một lỗi im lặng bằng một lỗi ồn ào hơn.
- Không đổi `config/config.yaml` (kể cả `symbols`) khi chưa có số của gói Y.
- Không đưa ngày lễ 2027 vào config khi chưa có nguồn.
