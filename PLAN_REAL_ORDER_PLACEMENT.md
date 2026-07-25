# Plan: Đặt lệnh thật trên tài khoản Cash (0434221)

**Ngày viết:** 2026-07-26
**Mức độ rủi ro:** 🔴 **CAO NHẤT trong toàn bộ dự án** — có khả năng làm mất tiền thật. Mọi quyết định thiết kế ưu tiên an toàn hơn tiện lợi/tốc độ.

**Quyết định đã xác nhận với user:**
1. Mức tự động hoá: **Tự động tính tín hiệu, nhưng mỗi lệnh thật cần xác nhận riêng** trước khi gửi SSI.
2. **Bắt buộc có giai đoạn dry-run** trước khi cho phép gửi lệnh thật.
3. Loại lệnh: **Chỉ Limit order (LO)** trước — không làm market/ATO/ATC/FCO ở giai đoạn này.

---

## ⚠️ Điều kiện tiên quyết — chỉ bạn làm được

**Cần credential mới: `private_key` (cặp khoá RSA)** — dùng để ký từng lệnh đặt (`HEADER_SIGNATURE`), khác hẳn `api_key`/`api_secret` đã có. Xác nhận từ source code thật (`services/trading.py::_sign_and_encode`): mọi lệnh đặt/sửa/huỷ đều cần `sign(request_body, private_key)`.

**Tôi không biết chính xác quy trình lấy `private_key` trên console SSI** (trang docs trước đó chỉ mô tả tạo API Key thường, không nhắc RSA) — nhiều khả năng đây là bước đăng ký riêng cho Trading API (có thể cần duyệt thủ công từ SSI, do liên quan đặt lệnh thật). **Việc đầu tiên bạn cần làm:** vào `developers.ssi.com.vn`, tìm mục liên quan "Trading API"/"chữ ký số"/"RSA key" (không phải "Quản lý API Key" thường), xem quy trình cụ thể. Báo lại cho tôi biết console yêu cầu gì (tự generate keypair rồi upload public key, hay SSI tự cấp cặp khoá) để tôi điều chỉnh Phase 0.

---

## Đã xác nhận từ source code thật (`inspect.signature`, không đoán)

```python
# services/trading.py — AsyncTradingService
place_limit_order(account_no, symbol, side: OrderSide, quantity, price) -> PlaceOrderResponse
cancel_order(account_no, client_request_id) -> CancelOrderResponse
cancel_order_by_order_id(account_no, order_id) -> CancelOrderResponse
get_max_buy_sell(account_no, symbol, price) -> MaxBuySellResponse  # kiểm tra sức mua trước khi đặt
```
- `AsyncTradingService(rest_client)` — **không nhận `config`** (khác `AsyncPortfolioService`). Ký lệnh qua `self._rest.get_private_key()` → đọc `Config.private_key` từ **cùng object** `auth.config` đã dùng cho auth (do `AsyncRestClient(self._config)` giữ reference, không copy) — nghĩa là chỉ cần `auth.config.private_key = <key>` (giống pattern đã làm với `client_id` ở account_sync.py), không cần sửa gì khác.
- `PlaceOrderResponse`: `order_id`, `client_request_id`, `status: OrderStatus`.
- `OrderSide.BUY`/`OrderSide.SELL` — enum 2 giá trị.
- Không có ví dụ thật (chưa test bằng lệnh thật) — **response thật khi đặt thành công/thất bại (giá sai, không đủ tiền...) chưa biết hình dạng chính xác**, cần Phase 0 verify bằng 1 lệnh thật khối lượng tối thiểu.

---

## Bối cảnh thuận lợi — rủi ro thấp ở giai đoạn đầu

Account Cash (`0434221`) hiện có `accountBalance ≈ 21,459 VND` (dữ liệu thật lấy được ở `PLAN_ACCOUNT_DATA_SYNC.md`) — **dưới 1 USD**. Ở mức này, bất kỳ lệnh mua nào cũng chỉ mua được khối lượng cực nhỏ (thậm chí có thể không đủ mua 1 lô) — tự nhiên giới hạn rủi ro tuyệt đối trong lúc kiểm chứng cơ chế. **Khuyến nghị:** KHÔNG nạp thêm tiền lớn vào account này cho tới khi toàn bộ pipeline (dry-run → xác nhận → đặt → huỷ) đã chạy ổn định nhiều tuần.

---

## Kiến trúc đề xuất

### 1. Reuse `RiskManager` đã có (`trading/risk.py`)
Class này đã có sẵn, đã test kỹ (`tests/test_risk.py`) cho PaperBroker — logic đúng những gì cần: giới hạn giá trị lệnh theo % capital, giới hạn số symbol nắm giữ, tự halt cả ngày nếu lỗ vượt ngưỡng. **Dùng lại y nguyên** cho lệnh thật, với `capital` = 1 con số **cấu hình riêng, KHÔNG tự động đọc từ `account_balance_snapshot`** (tránh trường hợp đọc nhầm/đọc chậm dẫn tới duyệt lệnh sai) — đặt cứng trong config, bạn tự cập nhật thủ công khi nạp thêm tiền.

### 2. Cơ chế xác nhận — đề xuất ĐƠN GIẢN (không phải bot 2 chiều)

Thay vì xây bot Telegram nhận reply (phức tạp, thêm 1 bề mặt lỗi mới: webhook, polling, xác thực người gửi lệnh đúng là bạn) — đề xuất:

1. Signal (từ chiến lược SmaCross hoặc job riêng) → qua `RiskManager.approve()` → nếu pass, ghi 1 dòng vào bảng `pending_real_orders` (status='pending', hết hạn sau 15 phút) + gửi Telegram **1 chiều** (đã có sẵn, không cần xây mới) báo: *"Lệnh chờ xác nhận: BUY 100 VCB @ 60,000đ — chạy `uv run python scripts/confirm_real_order.py <id>` trong 15 phút để xác nhận, không làm gì thì tự huỷ."*
2. Script `scripts/confirm_real_order.py <id>` (chạy thủ công) — in chi tiết lệnh, hỏi lại 1 lần nữa ("Nhập YES để xác nhận đặt lệnh THẬT"), nếu đồng ý → gọi `place_limit_order()` thật (hoặc chỉ log nếu còn ở chế độ dry-run).
3. Job nền dọn các `pending_real_orders` quá hạn → status='expired', không đặt.

**Đánh đổi:** Bạn phải chủ động chạy lệnh trên máy có `.env` (không xác nhận được từ điện thoại qua Telegram) — bù lại: không cần xây bot nhận webhook, không có rủi ro người khác gửi tin nhắn giả xác nhận hộ. Nếu bạn muốn xác nhận qua Telegram thật (reply trên điện thoại) — nói rõ, tôi thiết kế lại theo hướng bot 2 chiều (phức tạp hơn, cần thêm thời gian).

### 3. Dry-run mode (bắt buộc theo yêu cầu)
Thêm `Config.real_trading_enabled: bool` (mặc định `False` trong `config.yaml`). Khi `False`: toàn bộ pipeline chạy đầy đủ (tính signal, qua RiskManager, ghi `pending_real_orders`, gửi Telegram) nhưng bước cuối (`confirm_real_order.py` gọi `place_limit_order`) **chỉ log ra "SẼ đặt lệnh: ..." chứ không gọi API thật**. Chỉ đổi `real_trading_enabled: true` sau khi quan sát dry-run đủ lâu (đề xuất ≥ 2 tuần giao dịch, bạn tự quyết định thời điểm).

### 4. Bảng DB mới
```sql
CREATE TABLE IF NOT EXISTS pending_real_orders (
  id bigserial PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  account_no text NOT NULL,
  symbol text NOT NULL,
  side text NOT NULL,
  quantity integer NOT NULL,
  price double precision NOT NULL,
  status text NOT NULL DEFAULT 'pending',  -- pending|confirmed|expired|rejected|placed|failed
  ssi_order_id text,
  confirmed_at timestamptz
);
```

### 5. KHÔNG đụng `trading/collector/account_sync.py`
File đó có ranh giới an toàn tường minh (không import `AsyncTrading`) — module đặt lệnh thật là code HOÀN TOÀN MỚI (`trading/trading_real/` hoặc tên tương tự), không chung file với account_sync.

---

## Phase 0 — Discovery (bắt buộc trước khi code bất cứ gì)

1. **Bạn tự tìm hiểu quy trình lấy `private_key`** trên console SSI (xem mục "Điều kiện tiên quyết").
2. Sau khi có `private_key`, tôi viết script spike (`scripts/spike_ssi_sdk_place_order.py`) test:
   - `get_max_buy_sell(account_no, symbol, price)` — xem sức mua thật tính ra sao (KHÔNG đặt lệnh, chỉ đọc).
   - Đặt **1 lệnh LIMIT khối lượng tối thiểu** (thường 100 cổ phiếu — cần xác nhận lô tối thiểu HOSE/HNX) ở mức giá **chắc chắn không khớp** (vd đặt mua giá rất thấp so với giá thị trường) — mục đích: xác nhận lệnh được ghi nhận vào hệ thống SSI mà không thực sự khớp/mất tiền.
   - Gọi `cancel_order()` huỷ ngay lệnh vừa đặt — xác nhận huỷ thành công.
   - Ghi lại response thật (KHÔNG commit vào git — dữ liệu lệnh thật, gitignore giống account balance).
3. **Kiểm chứng:** đặt được lệnh, thấy lệnh ở trạng thái đúng (chưa khớp), huỷ thành công, không có tiền bị trừ ngoài dự kiến (kiểm tra lại `account_balance_snapshot` trước/sau).

**Đây là bước bắt buộc phải làm trước Phase 1** — chưa xác nhận được cơ chế đặt/huỷ lệnh hoạt động đúng thì chưa nên viết code production.

---

## Các Phase sau (viết chi tiết SAU khi Phase 0 xác nhận xong)

- **Phase 1:** Schema `pending_real_orders` + `Config.real_trading_enabled` + risk config riêng cho lệnh thật.
- **Phase 2:** Job sinh signal → `RiskManager.approve()` → ghi pending order + Telegram alert.
- **Phase 3:** `scripts/confirm_real_order.py` + dry-run gate.
- **Phase 4:** Giám sát thủ công nhiều phiên ở chế độ dry-run trước khi bật `real_trading_enabled=true`.

Không viết prompt thực thi cho các phase này ngay bây giờ — chờ Phase 0 xác nhận thật (đặc biệt: quy trình lấy `private_key`, và đặt/huỷ 1 lệnh thật thành công) để tránh giao việc dựa trên giả định chưa kiểm chứng, đúng nguyên tắc lập kế hoạch của dự án.

---

## Quyết định đã chốt (2026-07-26)

2. ~~Cơ chế xác nhận: script thủ công hay Telegram 2 chiều?~~ ✅ **Script thủ công** (`scripts/confirm_real_order.py`) — đơn giản hơn, không xây bot 2 chiều.
3. ~~Vốn tối đa cho `RiskManager`?~~ ✅ **Mặc định = số dư thật hiện tại** (~21,459đ, đọc từ `account_balance_snapshot` lúc viết plan — sẽ hardcode 1 con số cụ thể trong config lúc code, không tự động đọc số dư sống, xem mục Kiến trúc #1).

## ✅ Chặn đã gỡ (2026-07-26)

`SSI_PRIVATE_KEY` đã có sẵn trong `.env` từ trước (thêm cùng lúc với `api_key`/`api_secret` lúc đăng ký console, chỉ là chưa cần dùng tới ở các phase trước). Định dạng khớp đúng dự đoán ban đầu — base64-encode 1 XML RSA key (`<RSAKeyValue>...`), đúng dạng `ssi_sdk.utils.crypto.get_rsa_key()`/`sign()` cần.

**Phase 0 sẵn sàng bắt đầu** — xem `scripts/spike_ssi_sdk_place_order.py`.

### ⚠️ Rủi ro mới phát hiện khi thiết kế script: số dư quá thấp để test "đặt lệnh thành công"
Account Cash chỉ có **~21,459đ**. Giá VCB thật (từ fixture Phase 0 backfill) dao động 53,000-58,800đ/cổ phiếu — 1 lô tối thiểu (100 cổ phiếu) cần **≥ 5,300,000đ**, vượt xa số dư hiện có. Đặt lệnh mua thật (dù giá thấp) nhiều khả năng sẽ bị SSI từ chối ngay vì **không đủ sức mua**, không phải vì cơ chế sai.

**Script xử lý an toàn:** gọi `get_max_buy_sell()` (chỉ đọc, không đặt lệnh) trước — nếu sức mua tính ra < 100 cổ phiếu, script tự dừng, in rõ cần nạp thêm bao nhiêu tiền để test được đầy đủ (đặt + huỷ), không cố đặt lệnh biết trước sẽ thất bại.

## 📋 Kết quả Phase 0 thật (chạy 2026-07-26)

**Kết quả: dừng ở Bước 1 (get_max_buy_sell_at_market_price) — đúng kịch bản dự kiến.**

```
Account 0434221 / VCB: max_buy_quantity=0, max_sell_quantity=0, purchasing_power=21459 (VND)
→ Script tự dừng, KHÔNG đặt lệnh. Không có lỗi 401/403, không có lỗi ký request.
```

**Xác nhận:** cơ chế an toàn (kiểm tra sức mua thật trước khi đặt lệnh) hoạt động đúng. **Chưa xác nhận được** bước đặt lệnh thật + huỷ (`place_limit_order`/`cancel_order`) vì chưa từng chạy tới — số dư không đủ 1 lô của bất kỳ mã nào đã thử.

### 🐛 Bug thứ 3 phát hiện trong `ssi-sdk` 3.1.0 (cùng dạng 2 bug trước — field-mapping sai, không phải giả thuyết)

`AsyncTradingService.get_max_buy_sell_at_market_price()` nằm ở `trading.trading.*`, **không phải** `trading.portfolio.*` — bản nháp đầu của script gọi sai chỗ (`trading.portfolio.get_max_buy_sell_at_market_price`), gây lỗi `AttributeError` khi chạy thật. Đã sửa 1 dòng trong `scripts/spike_ssi_sdk_place_order.py`, xác nhận lại bằng `hasattr()` trên cả hai service class trước khi chấp nhận fix.

Ngoài ra, `MaxBuySellResponse.from_dict()` (trong `ssi_sdk/models`) đọc sai key JSON cho field `purchase_power`: code đọc `data.get("purchasePower", ...)` nhưng response thật trả về key `purchasingPower` (xác nhận qua raw debug log: `{"accountNo":"0434221","maxBuyQty":0,"marginRatio":"0%","purchasingPower":21459,"maxSellQty":0}`) → `purchase_power` luôn là chuỗi rỗng `""`, im lặng. **Không ảnh hưởng Phase 0** vì cơ chế dừng chỉ dựa vào `max_buy_quantity` (map đúng), nhưng **Phase 1-4 không được dùng `mbs.purchase_power`** cho bất kỳ logic nào (ví dụ hiển thị sức mua bằng tiền) — phải tự đọc raw REST response giống cách `account_sync.py` đã làm với `EquityAccountBalance`, hoặc chỉ dùng `max_buy_quantity`/`max_sell_quantity`.

### Còn thiếu để viết Phase 1-4 đầy đủ

`place_limit_order()`/`cancel_order()` chưa từng được gọi thật — response shape thật (đặc biệt trạng thái lệnh, format lỗi khi giá/khối lượng sai) **vẫn là giả định** (dựa trên `inspect.signature`/dataclass fields, không phải response thật). Có 2 lựa chọn:
1. Nạp thêm tiền vào tài khoản Cash (đủ mua 1 lô mã rẻ, ví dụ mã dưới 5,000đ/cp cần ~500,000đ) rồi chạy lại spike để xác nhận nốt bước đặt+huỷ.
2. Viết Phase 1-4 dựa trên phần đã xác nhận (schema, RiskManager, dry-run gate, script xác nhận thủ công) nhưng **giữ nguyên dry-run là bắt buộc** và ghi rõ "chưa test đặt+huỷ lệnh thật" như một rủi ro còn tồn đọng, cần test thủ công trước khi bật `real_trading_enabled=true`.
