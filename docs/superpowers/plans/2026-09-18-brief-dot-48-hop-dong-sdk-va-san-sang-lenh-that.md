# Brief đợt 48 — Hợp đồng SDK và mức sẵn sàng của đường lệnh thật

Ngày giao: 18/09/2026, 11:30.
Base: `57e1da4` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

**Chạy được ngay trong phiên.** Mọi việc ở đây là **đọc thuần hoặc chỉ sửa file trong repo**:
không dựng lại container, không gọi mạng, không ghi DB. Không có một dòng nào đụng tới đường
chạy thật của hệ thống.

---

## 0. Bối cảnh — điểm chặn go-live thật sự còn lại

### 0.1. Đường lệnh thật chưa từng chạy một lần

```
pending_real_orders : 9 lệnh, TẤT CẢ expired, 0 lệnh có ssi_order_id
real_order_fills    : 0 dòng
```

Nghĩa là toàn bộ đoạn mã gọi SSI để **đặt lệnh** chưa bao giờ thực thi. Ngày đầu tiên nó chạy
sẽ là ngày có tiền thật trong đó.

### 0.2. Hai giả thuyết tôi đã kiểm và **cả hai đều sai**

Tôi ghi lại vì chúng cho biết vấn đề **không** nằm ở đâu:

1. *"Cảnh báo lệnh chờ ở mức `INFO` nên không tới Telegram."* **Sai** — nó là `WARN`
   (`real_orders.py:209-219`), kèm sẵn `confirm_cmd`.
2. *"`place_limit_order` không tồn tại trên SDK đã cài."* **Sai.** Lần đầu tôi tra nhầm đích
   (`AsyncTrading` dùng thuộc tính động nên `dir()` trả rỗng). Tra đúng chỗ thì:

```
ssi_sdk 3.1.0 — AsyncTradingService.place_limit_order
   (self, account_no: str, symbol: str, side: OrderSide,
    quantity: int, price: float) -> PlaceOrderResponse
```

khớp **chính xác** lời gọi ở `confirm_real_order.py:151-157` — năm tham số, đúng thứ tự.

### 0.3. Nhưng chính việc kiểm đó lộ ra lỗ hổng thật

Tôi chỉ biết chữ ký khớp vì **tôi vừa gõ tay để tra**. Trong repo **không có gì** buộc điều đó
đúng: mọi test của đường lệnh thật đều tiêm hàm giả (`place_order_fn`, `max_buy_sell_fn`), nên
nếu SDK nâng cấp và đổi chữ ký, **toàn bộ suite vẫn xanh** và ta chỉ biết vào đúng lúc đặt
lệnh bằng tiền thật.

Đây **chính xác** là hạng lỗi của đợt 26: `send_telegram(cfg, msg)` gọi vào
`send_telegram(text: str)` — một TypeError chắc chắn, bị che vì mock được viết theo đúng chữ ký
sai. Lần đó mất một đợt để phát hiện. Lần này cái giá là một lệnh thật hỏng.

**Task 1 dựng lưới chắn đó.** Nó là việc có giá trị go-live cao nhất mà agent làm được lúc này.

---

## 1. Phạm vi

| File | Trạng thái | Task |
|---|---|---|
| `tests/test_ssi_sdk_contract.py` | **mới** | 1 — hợp đồng SDK |
| `scripts/check_real_order_readiness.py` | **mới** | 2 — báo cáo sẵn sàng |
| `docs/superpowers/research/2026-09-18-dot-48-hop-dong-sdk.md` | **mới** | báo cáo |

**Không sửa file có sẵn nào.** Đặc biệt **không đụng** `scripts/confirm_real_order.py`,
`trading/real_orders.py`, `trading/collector/*`, `trading/risk.py`, `config/config.yaml`,
`scripts/sched.sh`, và toàn bộ đường crypto.

### 1.1. Ràng buộc riêng cho việc chạy trong phiên

- **Không `docker compose build`, `restart`, `up`, `down`, `stop`.** Không đụng container.
- **Không gọi mạng.** Import một module **không** phải gọi mạng — nhưng **cấm khởi tạo client**
  (`AsyncTrading(...)`, `AsyncAuth(...)`) và cấm `await` bất kỳ phương thức SDK nào. Task 1 chỉ
  được dùng `inspect`, `hasattr`, `getattr` trên **lớp**, không trên **thực thể**.
- **Chỉ đọc DB.** Không `INSERT`/`UPDATE`/`DELETE`, không tạo bảng, không tạo pending order giả.
- `real_trading_enabled` giữ `false`. Không in secret, không mở `.env`.
- Không xoá file. **Không commit, không push.** Thiếu thì ghi **"CHƯA LÀM"**, **không bịa**.

---

## Task 1 — Test hợp đồng SDK: `tests/test_ssi_sdk_contract.py`

### 1.1. Ý tưởng

Với **mỗi** ký hiệu SSI SDK mà hệ thống phụ thuộc, khẳng định nó **tồn tại** và — với các hàm
ta gọi — **chữ ký đúng như ta gọi**. Test này không gọi mạng, không cần Docker, và nó đỏ ngay
khi SDK nâng cấp phá hợp đồng.

### 1.2. Bề mặt phụ thuộc — tôi đã quét, đây là đủ

| Nơi dùng | Ký hiệu |
|---|---|
| `scripts/confirm_real_order.py` | `ssi_sdk.AsyncTrading`, `ssi_sdk.enums.OrderSide`, `AsyncTradingService.place_limit_order`, `AsyncTradingService.get_max_buy_sell_at_market_price` |
| `trading/collector/ssi_auth.py` | `ssi_sdk.AsyncAuth`, `ssi_sdk.Config`, `ssi_sdk.models.Token` |
| `trading/collector/account_sync.py` | `ssi_sdk.constant.EP_ACCOUNT_BALANCE`, `ssi_sdk.services.portfolio.AsyncPortfolioService`, `ssi_sdk.services.trading.AsyncTradingService` |
| `trading/collector/feed.py` | `ssi_sdk.AsyncStream`, `ssi_sdk.enums.Timeframe` |

Nếu bạn tìm thấy chỗ dùng SDK nào **ngoài** bảng này: **báo cáo, đừng tự thêm vào test** — tôi
cần biết mình quét sót ở đâu.

### 1.3. Các test phải viết

1. **Tồn tại:** mọi ký hiệu trong bảng §1.2 import được.
2. **`place_limit_order` — chữ ký chính xác.** Khẳng định tên tham số **và thứ tự**:
   `(self, account_no, symbol, side, quantity, price)`.
   Cách làm: `inspect.signature(AsyncTradingService.place_limit_order)`, so danh sách tên tham
   số với danh sách kỳ vọng viết thẳng trong test. **Không** chỉ đếm số tham số — đổi thứ tự
   `quantity`/`price` vẫn đủ năm tham số mà đặt sai lệnh hoàn toàn.
3. **`get_max_buy_sell_at_market_price` — chữ ký chính xác**, cùng cách.
4. **`OrderSide` có đúng `BUY` và `SELL`** (đây là hai giá trị `confirm_real_order.py` dùng).
5. **Lời gọi trong code khớp chữ ký:** đọc `scripts/confirm_real_order.py` bằng `ast`, tìm lời
   gọi `place_limit_order`, đếm số đối số vị trí, và khẳng định nó bằng số tham số bắt buộc của
   chữ ký thật (trừ `self`).

   *Đây là test giá trị nhất của cả brief* — nó nối **code ta viết** với **SDK đã cài**, thứ mà
   mock không bao giờ làm được. Nếu thấy cách làm bằng `ast` quá rườm, **báo cáo đề xuất khác
   thay vì bỏ qua**.
6. **Đánh dấu không cần hạ tầng:** test chạy được với `uv run pytest tests/test_ssi_sdk_contract.py`
   mà **không** cần Docker, không cần DB, không cần mạng. Nêu rõ đã xác nhận điều này.

### 1.4. Cấm tuyệt đối trong Task 1

- **Không khởi tạo** `AsyncTrading()`, `AsyncAuth()`, `AsyncStream()` hay bất kỳ client nào.
- **Không `await`** bất kỳ phương thức SDK nào.
- **Không đọc `.env`**, không dùng thông tin xác thực.

Nếu một test buộc phải khởi tạo client để chạy được → **đừng viết test đó**, báo cáo lại.

---

## Task 2 — Báo cáo sẵn sàng: `scripts/check_real_order_readiness.py`

**Chỉ đọc DB. Không ghi. Không gọi SSI.**

### 2.1. In bốn phần

**(a) Trạng thái đường lệnh thật**

Số `pending_real_orders` theo `status`, số dòng có `ssi_order_id`, số dòng `real_order_fills`,
ngày lệnh gần nhất.

**(b) Sức mua so với nhu cầu — phần quan trọng nhất**

Với mỗi mã trong `config.symbols`, lấy bản ghi `account_buying_power` mới nhất của **tài khoản
đang cấu hình** (`real_order_account`) và so với giá gần nhất trong `bars`:

| Mã | `max_buy_qty` | Giá gần nhất | Giá trị mua tối đa | Đủ 1 lô (100 cp)? |
|---|---|---|---|---|

Tôi đã đo thử lúc 11:23 hôm nay: `0434221` có HPG **221**, IJC **677**, AAA **641** — đều trên
một lô. Nhưng đó là một lát cắt; báo cáo cần con số tại lúc chạy và **tuổi của bản ghi** (nếu
nó cũ hơn `BUYING_POWER_MAX_AGE_MINUTES = 15` thì lá chắn sẽ từ chối lệnh, và đó là một lý do
hỏng khác hẳn).

**(c) So sánh hai tài khoản**

`account_nav_snapshot` mới nhất cho cả hai tài khoản, và `max_buy_qty` của cả hai. Đây là dữ
liệu cho câu hỏi Q-2 của chủ dự án — **in số, không khuyến nghị**.

**(d) Tuổi dữ liệu của mọi lá chắn**

`read_position_sync_ts` và tuổi bản ghi sức mua, so với ngưỡng
`POSITION_MAX_AGE_MINUTES` / `BUYING_POWER_MAX_AGE_MINUTES` trong `trading/real_orders.py`
(**import hằng số, không gõ lại số**). Với mỗi lá chắn, in **ĐẠT** hoặc **SẼ TỪ CHỐI LỆNH**.

Đây trả lời một câu chưa ai hỏi: *nếu ngay bây giờ có tín hiệu, lệnh có đi qua được các lá chắn
không, hay bị chặn ngay từ cửa đầu?*

### 2.2. Kiểm chứng Task 2

1. Chạy hai lần liên tiếp → output giống hệt (trừ các trường tuổi dữ liệu tính theo thời gian
   thực — nêu rõ trường nào được phép đổi).
2. Đối chiếu ít nhất **hai** con số với truy vấn SQL trực tiếp, dán cả truy vấn lẫn kết quả.
   Mọi truy vấn có `ts` mở đầu bằng `SET TimeZone='Asia/Ho_Chi_Minh';`.
3. Script **không** ghi gì vào DB — chứng minh bằng cách nêu rõ chỉ dùng `SELECT`, và không
   import `Storage` method nào có chữ `write`/`create`/`update`.

---

## 2. Báo cáo cho Claude

1. `git diff --stat`, `git status --short` — tôi kỳ vọng **không file có sẵn nào bị sửa**.
2. Task 1: kết quả 6 test, **nói rõ test số 5 (`ast` nối code với SDK) đã xanh**, và xác nhận
   test chạy không cần Docker/DB/mạng.
3. Task 2: bốn phần đầu ra, hai đối chiếu SQL.
4. Ba dòng: số test pass (mốc **755**), ruff, cổng cứng VN đủ bốn con số:
   `-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã`.
5. Đường dẫn file nghiên cứu mới.

**Không commit, không push.**

---

## 3. Điều KHÔNG thuộc phạm vi

- **Không đụng container.** Việc triển khai `grace = 20` là của brief 47 Task 3, **sau 15:00**,
  và phải sau khi brief 47 Task 2 đo xong phiên nền cuối cùng.
- **Không sửa `confirm_real_order.py`.** Đợt này chỉ **kiểm** nó, không đổi. Nếu test phát hiện
  sai lệch → **báo cáo, đừng sửa** — sửa đường lệnh thật cần một brief riêng với đủ ràng buộc.
- **Không bật `real_trading_enabled`.** Không bao giờ, không ở đợt nào, trừ khi chủ dự án nói rõ.
- **Không tạo pending order giả** để thử. Ghi DB là cấm.
- **Không khuyến nghị chọn tài khoản nào.** In số, để chủ dự án quyết.
- **Không quyết định A/B/C** của đợt 45.

---

## 4. Việc của chủ dự án — xếp theo ảnh hưởng tới go-live

1. **Đăng ký Scheduled Task cho `stream-health`** — lệnh đã soạn sẵn ở báo cáo đợt 47. Năm
   phiên gần nhất có hai phiên luồng chết và một phiên mất 40%, không lần nào có cảnh báo.
2. **Quyết định A / B / C** (đợt 45). Nhắc lại: lựa chọn A với rổ ba mã hiện tại nghĩa là
   **không giao dịch gì cả** — nến ngày cho 0 tín hiệu trong ba tháng.
3. **9/9 lệnh hết hạn** — cảnh báo `WARN` có đi Telegram kèm lệnh xác nhận sẵn. Ông có nhận
   được không, và 15 phút có đủ không? Câu trả lời quyết định cửa xác nhận nên đổi thế nào, và
   đây là điểm chặn go-live **ngang hàng** với việc chiến lược có edge hay không.
4. **Q-2**: `0434221` (NAV 5.021.712, mua được HPG 221 cp) hay `0434226` (NAV 192.582.832, mua
   được HPG 5.824 cp)?
5. **`powercfg /change standby-timeout-dc 0`** và **chuyển VPS**.
6. **Q-1 vẫn chưa có lời giải:** tám chiến lược crypto đều âm, và backtest VN thua mua-và-giữ
   `-1,6 tỷ` so với `+1.897 tỷ`. Không có đợt kỹ thuật nào thay được câu trả lời cho câu hỏi
   này.
