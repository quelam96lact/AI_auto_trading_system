# Tổng hợp tồn đọng + đánh giá mở sang BingX (crypto/forex)

Viết tối 02/09/2026, sau đợt 11. Bảy commit đã push, cây làm việc sạch.

---

## PHẦN I — Tồn đọng hệ thống hiện tại

### 1. Khoá tới sau 14:45 ngày 03/09 (chạm `trading/` ⇒ phải dựng lại container)

| Mã | Việc | Ghi chú |
|---|---|---|
| **B1** | Hợp đồng chiến lược + sổ đăng ký + conformance test | Việc lớn nhất còn lại. Brief đã viết sẵn ở `2026-09-02-brief-agent-A-che-do-va-chien-luoc.md` phần 2 |
| **B2** | Gộp `_print_safe` vào `trading/alerts.py` | Nay có **ba** bản; `daily_data_check.py` là hộ tiêu thụ thứ tư khi gộp. Brief ở `...-brief-agent-B-chuong-bao-va-log.md` phần 2 |

**B1 gồm 5 mục con:** `Protocol` khai thiếu `warmup_bars`/`compute_crossover`;
`octopus_pullback` thiếu `last_crossover` (backtest sạch nhưng nạp vào engine
chết ngay bar đầu); test ép mọi chiến lược thoả hợp đồng; trường chọn chiến
lược trong `Config`; và quyết định số phận test đỏ
`test_cli_registry_no_longer_offers_sma_cross`.

**Lưu ý thiết kế đã ghi:** repo có **hai** hợp đồng chiến lược (cổ phiếu và
phái sinh), không phải một cái bị thiếu. Ép cả năm chiến lược vào một khuôn sẽ
phá đường phái sinh.

### 2. Cần một phiên giao dịch, KHÔNG phải 03/09

| Mã | Việc |
|---|---|
| **D1** | Diễn tập dead-man's switch (`2026-08-20-deadman-switch-live-drill.md`) — viết 20/08, **chưa từng chạy** |
| **D2** | Kiểm chứng backoff 429 thực địa — chỉ xảy ra khi có 429 thật, cấm cố tình gây ra |

D1 ghi rõ ngay tiêu đề là phải chạy **trong giờ giao dịch**. Làm ngày 03/09
nghĩa là giết collector giữa phiên đầu tiên chạy code mới — xếp cho phiên sau.

### 3. Chờ quyết định của chủ dự án

| Mã | Việc |
|---|---|
| **C1** | VPS Ubuntu — `sched.sh` và `DEPLOYMENT.md §1–§10` đã sẵn, cần chọn nhà cung cấp/thời điểm |
| **C2** | Docker Desktop tự khởi động cùng Windows — 02/09 chứng minh nó không tự lên |
| **C3** | Lịch nghỉ lễ 2026 — đã yêu cầu bỏ; hệ quả treo: ngày lễ chưa khai báo làm 2A báo láo cả ngày |

### 4. Đã đóng trong ngày 02/09

Cổng Docker hết im lặng (`0c9c85b`); xoay log Windows (`38629ff`); hai khiếm
khuyết phép đo chế độ (`14a5ff3`); `daily_data_check` có test (`7df1217`).
**Bốn chuông báo nay đều có test.**

---

## PHẦN II — BingX: hệ thống hiện tại tái dùng được bao nhiêu

Đo bằng cách quét phụ thuộc, không phỏng đoán.

### 5. Phần dùng lại được nguyên vẹn (19 module)

Không dính `calendar_vn`, không dính SSI:

```
trading/strategies/*  (cả 5 chiến lược)   trading/strategy.py
trading/indicators.py                     trading/trailing_stop.py
trading/alerts.py                         trading/telegram.py
trading/broker.py                         trading/collector/watchdog.py
trading/derivative_risk.py
```

`risk.py` và `models.py` chỉ nhắc SSI trong **một dòng chú thích** và một giá
trị mặc định `source="ssi"` — coi như trung lập.

**Đây là tin tốt thật:** tầng chiến lược, chỉ báo, trailing stop, cảnh báo —
những thứ tốn nhiều công nhất và đã có test — không phải viết lại.

### 6. Phần dính chặt thị trường Việt Nam, phải làm lại

| Chỗ | Vì sao không mang sang được |
|---|---|
| `calendar_vn.py` | `SESSIONS = [(9:00,11:30),(13:00,14:45)]`, T2–T6, ngày lễ. **Crypto chạy 24/7** |
| `paper_broker.py` | `SETTLE_DAYS = 3` (T+2,5), `FEE_RATE = 0.0025`, `SELL_TAX_RATE = 0.001` — thuế bán và chu kỳ thanh toán **không tồn tại** ở crypto |
| `collector/*` | Toàn bộ dựng quanh SSI FastConnect: auth, stream, parser B/MI, backfill |
| `real_orders.py` | Đường đặt lệnh SSI |
| `engine/main.py`, `engine/logic.py`, ~~`backtest.py`~~ | Đều import `calendar_vn`. **ĐÍNH CHÍNH 04/09: `backtest.py` KHÔNG thuộc nhóm này** — nó chỉ dùng `TZ` (dòng 273/324/325), không dùng `SESSIONS`, không gọi `is_trading_time`, nên `run_backtest` chạy được trên nến crypto 24/7 mà không âm thầm vứt bar. Chỗ chặn thật nằm ở `risk.py` (lô 100) — xem `2026-09-04-plan-bingx-giai-doan-2-do-chien-luoc.md` |
| Bốn chuông báo | **Tất cả** dựng trên khung giờ phiên VN |

### 7. Ba thứ crypto có mà hệ thống hiện tại chưa có khái niệm

Đây là phần rủi ro nhất, và không phải là "sửa" mà là **code mới**:

1. **Đòn bẩy và thanh lý.** `RiskManager` hiện không biết margin, đòn bẩy, giá
   thanh lý. Ở crypto, sai sót về sizing không làm lỗ — nó làm **mất sạch vị
   thế**. Đây là khác biệt bản chất so với cổ phiếu VN không đòn bẩy.
2. **Phí funding của hợp đồng vĩnh cửu.** Một khoản chi định kỳ mà mô hình phí
   hiện tại (phí + thuế một lần lúc khớp) không biểu diễn được. Backtest bỏ qua
   funding sẽ cho kết quả đẹp một cách giả tạo với vị thế giữ lâu.
3. **24/7 phá vỡ mọi giả định "ngoài giờ thì im".** Bài học đắt nhất trong hai
   ngày qua là hệ thống lẫn "im vì ngày nghỉ" với "im vì hỏng". Ở crypto không
   còn ngày nghỉ — **mọi khoảng im lặng đều là bất thường**. Logic chuông báo
   phải viết lại, nhưng viết lại theo hướng **đơn giản hơn**.

### 8. Điều phải nói thẳng trước khi giao việc

**Không chiến lược nào trong repo có lợi thế đo được.** Kết luận `711683a` và
`14a5ff3` (audit hôm nay): cả ba chiến lược cổ phiếu đều thua mua-và-giữ, và
lọc theo chế độ thị trường không cứu được. `real_trading_enabled` vẫn `false`.

Sang thị trường mới **không sửa được điều đó** — nó chỉ đặt lại phép đo về số
không. Crypto có hai đặc điểm khiến việc này vừa dễ hơn vừa nguy hiểm hơn:

- **Dễ hơn:** dữ liệu 24/7, lịch sử dài, API công khai ⇒ đo nhanh và nhiều hơn
  hẳn. Cùng một tuần có thể chạy số phép đo bằng cả tháng ở thị trường VN.
- **Nguy hiểm hơn:** đòn bẩy biến một chiến lược lỗ nhẹ thành mất vốn, và biến
  một lỗi sizing thành thanh lý. Ở thị trường VN, sai lầm tệ nhất hai tuần qua
  là *chạy sai image trong hai tuần*. Cũng lỗi ấy ở crypto có đòn bẩy thì hậu
  quả không dừng ở "đo lại".

Khuyến nghị: **paper trước, và giữ nguyên kỷ luật đo đã có** — đóng băng quy
tắc trước khi chạy ngoài mẫu, kiểm chứng phá hoại, con số phải tái lập được.
Chính ba chốt đó đã bắt được một quy tắc lãi +1,11 tỷ trong mẫu hoá ra lỗ
−8,82 tỷ ngoài mẫu.

---

## PHẦN III — Những quyết định cần chủ dự án trả lời trước khi giao task

Không phải việc kỹ thuật, và không nên để agent tự chọn:

1. **Sản phẩm nào trên BingX?** Spot, hay hợp đồng vĩnh cửu (perpetual)? Hai
   đường code khác nhau: spot gần với cổ phiếu (không đòn bẩy, không funding);
   perpetual cần toàn bộ mục 7.
2. **Có đòn bẩy không, và trần bao nhiêu?** Trả lời "không dùng đòn bẩy" làm
   việc này nhỏ đi rất nhiều.
3. **Crypto và forex cùng lúc, hay crypto trước?** Forex trên BingX có giờ
   giao dịch (T2–T6, nghỉ cuối tuần) — tức lại có "khoảng im hợp lệ", ngược
   với crypto 24/7. Làm cả hai cùng lúc nghĩa là hai mô hình lịch trong một hệ.
4. **Hệ thống VN đi tiếp hay đóng băng?** Đang có tồn đọng B1/B2 và một phiên
   đo sạch vào 03/09. Chạy song song hai thị trường sẽ chia đôi sự chú ý —
   quyết định này ảnh hưởng tới thứ tự mọi thứ trong Phần I.
5. **Vốn thật hay giấy, và mốc nào mới chuyển?** Nên định trước tiêu chí bằng
   số, trước khi có kết quả — nếu định sau, tiêu chí sẽ bị uốn theo kết quả.

---

## PHẦN IV — Hình dạng công việc BingX nếu được duyệt

Chưa phải brief. Chỉ là khung để ước lượng.

| Giai đoạn | Nội dung | Chạm gì |
|---|---|---|
| 0 | Tách lịch thị trường khỏi `calendar_vn` — một giao diện, hai bản (VN, 24/7) | `trading/` |
| 1 | Thu thập dữ liệu BingX (REST lịch sử trước, stream sau) + lưu vào schema hiện có | mới |
| 2 | Mô hình phí/thanh toán theo thị trường: bỏ T+3 và thuế bán, thêm maker/taker (+funding nếu perpetual) | `paper_broker.py` |
| 3 | **Đo chiến lược trên dữ liệu crypto** — dùng lại `run_backtest` và 5 chiến lược sẵn có | chỉ `scripts/` |
| 4 | Chuông báo cho thị trường 24/7 | `scripts/` |
| 5 | Đường đặt lệnh BingX (paper trước) | mới |

**Giai đoạn 3 nên làm sớm nhất có thể** — nó chỉ cần dữ liệu và không cần
đường đặt lệnh, mà nó trả lời chính câu hỏi quyết định có nên làm tiếp hay
không. Xây đường đặt lệnh trước khi biết có lợi thế là làm ngược.

**Điều kiện tiên quyết cho tất cả:** B1 (hợp đồng chiến lược + sổ đăng ký) nên
xong trước giai đoạn 3. Không có hợp đồng rõ ràng thì việc chạy cùng bộ chiến
lược trên hai thị trường sẽ nhân đôi đúng cái bẫy đã tìm thấy hôm nay —
`octopus_pullback` backtest sạch nhưng nạp vào engine thì chết.
