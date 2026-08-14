# Kế hoạch: sửa lỗi phí mua trong PnL giấy + hai cảnh báo hỏng-âm-thầm

Ngày giao: 2026-08-14 chiều (17:40). Nhánh: `feature/data-layer`. Base: `55df5dd`.

**KHÔNG commit, KHÔNG push.** `gitnexus_detect_changes` khi xong.

Hai việc **độc lập** — làm được song song, không việc nào phụ thuộc việc kia.

---

## BỐI CẢNH VẬN HÀNH

Phiên đã đóng (14:45). Stack thật đang chạy nhưng **không có gì cần gấp trong đêm**.

- **KHÔNG** restart/rebuild container. Người audit sẽ quyết lúc nào rebuild.
- **KHÔNG** đụng `config/config.yaml`. **KHÔNG** bật `real_trading_enabled`.
- **KHÔNG** đụng dữ liệu phái sinh. Mã `41I1G8000` trong `bars` giữ nguyên.
- Chạy `pytest` an toàn (hạ tầng test tách từ `51eb353` — DB `trading_test`,
  NATS 4223). Nếu `nats-test` chưa chạy: `docker compose --profile test up -d nats-test`.
- Token SSI vừa nạp lại, hết hạn **01:27 sáng mai**. Không cần dùng tới nó.

---

# VIỆC 1 — `realized_pnl` bỏ sót phí mua

## Bằng chứng (đã đo trên DB sản xuất, không suy luận từ code)

Hôm nay luồng giấy chạy 5 vòng mua-bán trọn vẹn, **mọi vị thế đều đã đóng**
(`positions`: HII/IJC/AAA đều `qty=0`). Khi đã phẳng hết, tiền mặt là sự thật
duy nhất và nó phải khớp với PnL luỹ kế.

```
capital ban đầu                  100.000.000
engine_state.cash                 99.671.202   -> tiền thực giảm  328.798
engine_state.realized_pnl           -209.381   -> hệ thống tự báo  209.381
                                                 chênh lệch       119.417
```

119.417 đúng bằng tổng phí của 5 lệnh MUA hôm nay
(49.474,725 + 48.384,18 + 6.670,83 + 7.703,85 + 7.183,59).

Kiểm chứng độc lập trên một lệnh, HII vòng thứ hai:

```
BUY  2300 @ 8.604,300   fee 49.474,725
SELL 2300 @ 8.642,857   fee 69.575
(8.642,857 - 8.604,300) * 2300            =  88.681,4   (lãi gộp theo giá)
                          - 69.575        =  19.106,4   = ĐÚNG pnl đã ghi
```

Phí MUA không xuất hiện ở đâu trong phép tính đó.

## Nguyên nhân

`trading/paper_broker.py`, nhánh BUY của `on_bar`:

```python
:76   pos.avg_price = (pos.avg_price * pos.qty + gross) / new_qty   # gross CHƯA gồm phí
:78   self.cash -= gross + fee                                       # cash thì CÓ trừ phí
```

`gross = price * qty` (`:67`). Giá vốn dựng từ `gross` nên **không mang phí vào**,
trong khi `cash` ngay dòng dưới lại trừ đúng phí đó. Hai sổ sách lệch nhau kể từ
lệnh mua đầu tiên.

Đến lúc bán (`:80`) `pnl = (price - pos.avg_price) * qty - fee` chỉ trừ phí BÁN.
Phí MUA biến mất khỏi PnL vĩnh viễn.

**Sai một chiều:** luôn báo lỗ nhẹ hơn / lãi đậm hơn thực tế, mỗi vòng một lần.

## Cách sửa đã chốt

Gộp phí mua vào giá vốn:

```python
pos.avg_price = (pos.avg_price * pos.qty + gross + fee) / new_qty
```

**Vì sao chọn hướng này** thay vì cộng dồn phí vào một biến riêng rồi trừ lúc bán:
`cash` đã hạch toán theo đúng quy ước "giá vốn gồm phí" rồi, nên sửa `avg_price`
làm hai sổ khớp nhau bằng một dòng. Nó cũng sửa luôn `unrealized_pnl` (`:91`),
vốn đang cùng một lỗi — vị thế đang mở hiện được định giá như thể vào lệnh miễn phí.

`force_exit` (`:49`) và nhánh SELL (`:80`) **không cần sửa** — chúng đọc
`avg_price`, nên tự đúng theo. Xác nhận điều này bằng test chứ đừng chỉ tin.

## Thời điểm triển khai — đọc kỹ

`PaperBroker.restore` nạp `avg_price` từ bảng `positions`. Vị thế lưu trước bản
sửa mang giá vốn **chưa gồm phí**; sau khi sửa chúng sẽ bị tính sai chiều ngược lại.

**Ngay lúc này cả ba mã đều `qty=0`** (đã kiểm 17:35 hôm nay) nên không có gì để
di trú. Nếu bạn thấy `positions` có `qty > 0` khi bắt đầu làm — **DỪNG và báo cáo**,
đừng tự viết script di trú.

## Phạm vi việc 1

- **Được sửa:** `trading/paper_broker.py`, test tương ứng trong `tests/`.
- **KHÔNG đụng:** `trading/derivative_position.py`, `trading/derivative_backtest.py`
  (lớp riêng, cùng khuôn mẫu nhưng **ngoài phạm vi** — nếu thấy nó cũng dính lỗi
  tương tự thì **báo cáo, đừng sửa**), `trading/real_orders.py` (dùng
  `RealPosition` từ SSI, khác lớp), `trading/risk.py`, `trading/storage/db.py`,
  `trading/engine/main.py`.
- `gitnexus_impact` trên `PaperBroker.on_bar` **trước khi sửa**, dán blast radius.

## Kiểm chứng việc 1 — dán output THẬT

1. **RED bắt buộc.** Viết test: một vòng BUY→SELL trọn vẹn, kết thúc `qty == 0`,
   khẳng định `broker.cash - broker.capital == broker.realized_pnl`.
   Test này **phải ĐỎ trên code hiện tại**, và lệch đúng bằng phí mua. Dán dòng
   fail. Rồi sửa → xanh.
2. **Tái hiện đúng số sản xuất.** Dựng lại 5 vòng hôm nay từ bảng `orders`
   (giá/khối lượng ở phần bằng chứng trên) qua `PaperBroker`. Sau bản sửa,
   `realized_pnl` phải ra **≈ −328.798** (sai số làm tròn chấp nhận được), tức
   khớp mức giảm tiền mặt thật. Đây là bằng chứng mạnh nhất — dán số.
3. `force_exit` cũng đúng: BUY rồi `force_exit` toàn bộ → `cash - capital == realized_pnl`.
4. `unrealized_pnl` phản ánh phí vào lệnh: mua xong, mark **bằng đúng giá mua**
   → `unrealized_pnl` phải **âm** đúng bằng phí, không phải 0.
5. Toàn bộ suite + `ruff check trading tests` sạch. **Nếu một test cũ chuyển đỏ:
   DỪNG và báo cáo. Tuyệt đối không sửa kỳ vọng của test cũ cho qua.**

## Chạy lại backtest sau khi sửa

`trading/backtest.py` dùng chính `PaperBroker`, nên mọi con số cũ đều mang lỗi này.

Chạy lại **đúng 4 cấu hình** đã chạy hôm qua, **không chỉnh một tham số nào**:

```
sma_cross, 5m, 2026-04-03 -> 2026-08-07
  HII,IJC,AAA / 5.021.459
  HII,IJC,AAA / 1.000.000.000
  VCB,HPG,TCB / 5.021.459
  VCB,HPG,TCB / 1.000.000.000
```

Báo cáo dạng bảng **cũ so với mới**: số lệnh, tỉ lệ thắng, PnL, MaxDD.
**Chỉ chép số. Không thêm nhận định, không khuyến nghị, không an ủi.**

Kèm một con số tách bạch cho mỗi cấu hình, vì nó là thứ chủ dự án đang cần:
**tổng phí + thuế** đã trả, đặt cạnh **PnL gộp trước mọi loại phí**.

---

# VIỆC 2 — hai cảnh báo cho kiểu hỏng âm thầm

## Vì sao cần, và ranh giới giữa hai cái

Sự cố hôm nay, dựng lại theo log:

```
13:39  refresh token hết hạn -> account sync + derivative sync bắt đầu hỏng
       feed VẪN chạy (websocket đang mở), bar vẫn về đều
14:25  bar cuối cùng
14:33  feed thử nối lại -> xác thực hỏng -> chết hẳn
14:45  MẤT bar ATC
       suốt 4 tiếng: heartbeat collector XANH (tuổi 4 giây)
```

`scripts/heartbeat_check.py` chỉ đo **tiến trình còn sống**. Tiến trình sống suốt.

**Điểm mấu chốt phải hiểu trước khi viết code:** cảnh báo "dữ liệu ngừng chảy"
(2A) **sẽ KHÔNG bắt được sự cố hôm nay** — bar chảy đủ trong toàn bộ cửa sổ kiểm
tra. Thứ bắt được hôm nay là cảnh báo token (2B). Cả hai đều cần, nhưng đừng
nhầm cái nọ làm được việc của cái kia.

Cả hai bổ sung vào `scripts/heartbeat_check.py` — cùng một cron, cùng một lớp
sự cố. **Giữ kiểu hàm thuần + `main()` mỏng** như `stale_services` đang có, để
test được mà không cần DB.

## 2A — cảnh báo khi bar ngừng về

Bắt được: feed chết giữa phiên, feed chưa từng nối được cả ngày, đứt mạng.

### Cửa sổ kiểm tra: 9:00–11:30 và 13:00–**14:30** (KHÔNG tới 14:45)

`calendar_vn.is_trading_time` coi tới 14:45 là giờ giao dịch — **không dùng
trực tiếp được cho 2A**. Đo trên dữ liệu thật, khung 14:30–14:45:

```
mã đang cấu hình, số bar trong khung 14:30-14:40:
  12/08:  AAA 0 | HII 0 | IJC 0 | VCB 0
  13/08:  AAA 3 | HII 3 | IJC 3 | VCB 0
bar 14:45 (ATC): luôn có, cả 4 mã, cả 2 ngày
```

Khung ATC **lúc có lúc không, tuỳ mã tuỳ ngày**. Kiểm tra qua đó là chuông báo
láo. Cắt ở 14:30, chấp nhận mù 15 phút cuối.

**KHÔNG sửa `SESSIONS` trong `calendar_vn.py`** — hằng số đó đang chi phối hành
vi giao dịch thật. Định nghĩa cửa sổ riêng cho 2A ngay trong `heartbeat_check.py`.

### Chỉ nhìn mã đang cấu hình

Truy vấn `max(ts)` **chỉ trên `cfg.symbols`**. Bảng `bars` còn 302 mã universe
nạp theo lô — gộp chúng vào sẽ che mất một feed đã chết.

### Ngưỡng: đo, đừng đoán

`ts` của bar là **mốc đầu khung 5 phút** (`aggregator.py:26` làm tròn xuống), nên
`max(ts)` tụt sau hiện tại một khoảng tự nhiên, chưa kể mã thanh khoản thấp có
khung rỗng (hôm nay HII 38 bar so với IJC 45).

Xuất phát từ **15 phút**, nhưng **phải kiểm chứng bằng dữ liệu thật**: với 10
ngày giao dịch khỏe gần nhất, tính khoảng cách lớn nhất giữa hai bar liên tiếp
(lấy `max(ts)` gộp các mã cấu hình) **bên trong cửa sổ kiểm tra**. Dán con số đó.
Ngưỡng phải lớn hơn nó và còn dư biên. **Nếu đo ra > 15 phút thì nâng ngưỡng và
nói rõ đã nâng lên bao nhiêu, vì sao.**

### Hạn chế phải ghi vào docstring

`is_trading_time(holidays=frozenset())` mặc định rỗng → **ngày lễ VN sẽ báo láo
cả ngày** (không có bar nào). Ghi rõ đây là hạn chế đã biết và tham số `holidays`
là chỗ mở rộng. **KHÔNG tự dựng lịch nghỉ lễ** — chưa được giao.

## 2B — cảnh báo token SSI sắp/đã hết hạn

Bắt được: đúng sự cố hôm nay, và cái vòng lặp OTP 8 tiếng đã cắn hai lần.

Đọc `refresh_token_expires_at` từ bảng `ssi_auth_state` (`Storage.load_ssi_token`
đã có sẵn — dùng lại, đừng viết truy vấn mới):

- còn **dưới 60 phút** → `WARN`
- **đã hết hạn** → `CRITICAL`
- **không có dòng nào** trong `ssi_auth_state` → `CRITICAL`

Chỉ báo trong giờ giao dịch (`is_trading_time`, dùng được nguyên vẹn ở đây —
2B không liên quan gì tới ATC), **cộng thêm một lần trong khung 8:00–9:00** để
cảnh báo còn kịp hành động trước giờ mở cửa. Đây là điểm khác biệt so với 2A,
đừng bỏ sót.

Nội dung tin nhắn phải nói rõ **phải làm gì**, vì runbook hiện tại gây hiểu lầm:
chạy `scripts/spike_ssi_sdk_auth.py` **rồi `scripts/load_token_to_db.py`** —
bước thứ hai là cầu nối duy nhất sang DB và chính nó đã bị bỏ quên chiều nay.

**CẢNH BÁO BẢO MẬT:** tin nhắn **chỉ** được chứa mốc thời gian hết hạn.
Tuyệt đối không đưa token, một phần token, hay độ dài token vào log/Telegram.

## Phạm vi việc 2

- **Được sửa:** `scripts/heartbeat_check.py`, test trong `tests/`.
- **KHÔNG đụng:** `trading/calendar_vn.py`, `trading/collector/watchdog.py`,
  `trading/collector/feed.py`, `trading/telegram.py`, và **toàn bộ `trading/`**.
- Giữ nguyên mã thoát đang có: `0` ổn, `1` đã gửi cảnh báo, `2` sai cấu hình.
- Giữ nguyên hành vi `stale_services` — **không refactor tiện tay**.

## Kiểm chứng việc 2 — dán output THẬT

Test hàm thuần, không cần DB, cùng khuôn mẫu `test_heartbeat_check` đang có:

**2A**
1. bar mới → không báo
2. bar cũ, đang trong phiên → có báo
3. bar cũ, **14:35** (khung ATC) → **KHÔNG** báo
4. bar cũ, ngoài giờ / cuối tuần → không báo
5. **không có bar nào cả ngày**, đang trong phiên → **có** báo
   (đây là ca "feed chưa từng nối được" — dễ tuột nhất, đừng bỏ)
6. **RED bắt buộc:** đổi biên cửa sổ từ 14:30 thành 14:45 → ca (3) phải ĐỎ.
   Dán dòng fail, rồi khôi phục.

**2B**
7. còn 90 phút → không báo · còn 30 phút → WARN · đã hết hạn → CRITICAL
8. `ssi_auth_state` rỗng → CRITICAL
9. 8:30 sáng (ngoài `is_trading_time`) mà token đã hết hạn → **có** báo
10. **RED bắt buộc:** bỏ nhánh khung 8:00–9:00 → ca (9) phải ĐỎ.

**Đối chiếu với thực tế hôm nay**
11. Cho `now = 14:00 hôm nay`, dữ liệu thật hôm nay: **2A phải IM LẶNG**
    (bar chảy đủ) và **2B phải KÊU** (token hết hạn 13:39). Đây là kiểm chứng
    quan trọng nhất của cả việc 2 — nó chứng minh hai cảnh báo phân vai đúng.
    Nếu 2A kêu ở đây thì thiết kế sai, **dừng và báo cáo**.

12. Toàn bộ suite + ruff sạch.

---

# Toàn bộ

- `uv run pytest -q` → ≥ 279 + test mới, không test cũ nào đỏ.
- `uv run ruff check trading tests` → sạch.
- `gitnexus_detect_changes` → dán mức rủi ro + danh sách file.
- **KHÔNG commit, KHÔNG push.**

# Nếu thấy kế hoạch sai

Dừng và phản biện. Ba chỗ tôi có thể đã chọn sai:

1. **Việc 1, gộp phí vào `avg_price`.** Nó làm `avg_price` không còn là "giá khớp
   trung bình" mà thành "giá vốn gồm phí". Nếu có chỗ nào trong hệ thống đang
   đọc `avg_price` với nghĩa "giá khớp" — trailing stop, hiển thị, so sánh với
   giá thị trường — thì hướng này sai và phải tách biến. Tôi đã dò và tin là
   không có (`engine/main.py:108` dựng trailing stop từ giá BUY trong lịch sử
   lệnh, không từ `avg_price`), nhưng **bạn kiểm lại độc lập**.
2. **Việc 2A, cắt cửa sổ ở 14:30.** Đánh đổi mù 15 phút cuối phiên để khỏi báo
   láo. Nếu bạn nghĩ ra cách bắt được cả khung ATC mà không báo láo, nói ra.
3. **Việc 2B là phạm vi tôi tự thêm**, chủ dự án không yêu cầu. Lý do: nếu chỉ
   làm 2A thì sự cố hôm nay vẫn lọt. Nếu bạn thấy nó nên tách thành việc riêng,
   nói ra — đừng âm thầm làm nửa vời.
