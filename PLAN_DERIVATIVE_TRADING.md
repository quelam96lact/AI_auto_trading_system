# Plan: Bổ sung giao dịch phái sinh (VN30F1M)

## Bối cảnh

Hệ thống hiện tại (xem `CLAUDE.md`, `PLAN_ACCOUNT_DATA_SYNC.md`) chỉ trade cổ phiếu
HOSE/HNX. Tài khoản phái sinh (`0434228`, loại `Derivative`) đã được xác nhận tồn tại
thật từ Phase 0 của `PLAN_ACCOUNT_DATA_SYNC.md` nhưng bị loại trừ có chủ đích.

Người dùng yêu cầu bổ sung khả năng giao dịch phái sinh, với 1 điểm khác biệt quan
trọng đã xác nhận: **thị trường phái sinh VN thanh toán T+0** (không phải T+2,5 như
cổ phiếu) — nghĩa là toàn bộ logic `sellable_quantity`/settlement-aware SELL đã xây
cho cổ phiếu (`real_orders.py`, `RealPosition.sellable_qty`) **không áp dụng được**
cho phái sinh, cần model vị thế hoàn toàn khác (long/short theo hợp đồng, không phải
"đã mua bao nhiêu cổ phiếu").

**Quyết định đã chốt với người dùng (2026-07-26):**
1. **Phạm vi plan này: chỉ Phase 0 — spike nghiên cứu.** Chưa thiết kế chiến lược,
   risk model, hay order placement pipeline — vì dự án chưa có bất kỳ dữ liệu thật
   nào về API phái sinh (order placement, margin, giá hợp đồng). Nguyên tắc xuyên
   suốt dự án: không đoán hành vi SDK, luôn verify bằng dữ liệu thật trước khi thiết
   kế (xem cách `PLAN_REAL_ORDER_PLACEMENT.md` đã làm với lệnh thật cổ phiếu).
2. **Sản phẩm: chỉ VN30F1M** (hợp đồng tương lai VN30 tháng gần nhất — thanh khoản
   cao nhất, phổ biến nhất cho retail). Không hỗ trợ nhiều kỳ hạn ở giai đoạn này.
3. **Hướng chiến lược tương lai (chưa implement, chỉ ghi nhận định hướng):** tái sử
   dụng `SmaCrossStrategy` áp lên chỉ số/giá VN30F1M thay vì cổ phiếu. Sẽ cần thêm
   logic SELL-to-open (bán khống) vì phái sinh cho phép short — cổ phiếu thì không.
   Đây là quyết định của Phase 1 (thiết kế), KHÔNG thuộc phạm vi Phase 0.

---

## Đã tra cứu thật qua `inspect` (KHÔNG đoán — xem lệnh chạy trong lịch sử phiên)

Cài đặt `ssi-sdk` hiện có trong venv **đã có sẵn** một bộ API phái sinh tách biệt
hoàn toàn khỏi API cổ phiếu đang dùng:

### Trading (đặt lệnh) — `AsyncTradingService`
- `place_order(account_no, symbol, side, quantity, price, order_type) -> PlaceOrderResponse`
  — generic, nhận `OrderType` (`ATO, ATC, LO, MTL, MP, MOK, MAK, PLO`). **Chưa xác
  nhận có hoạt động với tài khoản Derivative hay không** — docstring dùng ngôn ngữ
  chung ("shares"/"Ticker symbol"), không nói rõ có phân biệt loại tài khoản.
- Nhóm lệnh điều kiện riêng cho phái sinh (tên gọi "FCO" trong SDK — Futures
  Conditional Order): `place_fco_gtd`, `place_fco_bull_bear`, `place_fco_oco`,
  `place_fco_stop`, `place_fco_stop_limit`, `place_fco_trailing_stop`,
  `place_fco_trailing_stop_limit`, `cancel_fco`, `get_fco_by_account_no`,
  `get_fco_by_id`, `get_fco_by_status`. Đây là lệnh điều kiện (stop/trailing/OCO),
  KHÔNG phải lệnh LO/MP đơn giản — không phải thứ cần cho 1 chiến lược MA crossover
  đơn giản (chỉ cần BUY/SELL tại giá thị trường/limit).
- **Chưa rõ**: lệnh LO/MP đơn giản cho phái sinh gọi qua `place_order()` (generic)
  hay có 1 method riêng nào khác chưa liệt kê hết — cần verify bằng spike.

### Portfolio (số dư, vị thế, ký quỹ) — `AsyncPortfolioService`
Có sẵn method + model riêng cho phái sinh, tách biệt hoàn toàn khỏi `Equity*`:
- `get_derivative_balance(account_no) -> DerivativeAccountBalance` — field gồm
  `account_balance, fee, commission, interest, loan, delivery_amount, floating_pl,
  trading_pl, total_pl, withdrawable, cash_ssi, ...`
- `get_derivative_ppmmr(account_no) -> DerivativePPMMR` — đây là dữ liệu **ký quỹ**
  quan trọng nhất cho risk model phái sinh sau này: `marginable, depositable,
  rc_call, margin_req_ssi/vsdc, margin_call_ssi/vsdc, account_ratio_ssi/vsdc,
  used_limit_warning_level1/2/3_ssi/vsdc, total_equity, ...`. Tên field gợi ý rõ
  ràng có sẵn cơ chế cảnh báo margin call nhiều mức — cần đọc kỹ dữ liệu thật để
  hiểu ngưỡng nào tương ứng "sắp bị force-close" trước khi tự động giao dịch bất
  kỳ.
- `get_derivative_positions(account_no) -> list[AllDerivativePosition]`,
  `get_open_derivative_positions(account_no) -> list[DerivativePosition]`,
  `get_closed_derivative_positions(account_no) -> list[DerivativePosition]` — model
  `DerivativePosition` có `long, short, net, bid_avg_price, ask_avg_price,
  trade_price, floating_pl, trading_pl` — xác nhận vị thế phái sinh là long/short
  theo hợp đồng, khác hẳn `Position`/`RealPosition` (qty cổ phiếu) đang dùng cho cổ
  phiếu. **Cảnh báo đã biết:** `Equity*` methods có bug field-mapping thật (đọc sai
  tên JSON key, ví dụ `EquityAccountBalance.available_cash` luôn `0.0`, xem
  `PLAN_ACCOUNT_DATA_SYNC.md`) — **giả định `Derivative*` model KHÔNG có bug tương
  tự là RỦI RO, phải tự verify lại field-by-field với response thật, không suy diễn
  từ việc `Equity*` có bug hay không.**

### Market data / streaming
- `AsyncMarketDataService` có các method OHLC generic (`get_ohlc_1minute`,
  `get_ohlc_1day_historical`, ...) nhận `symbol` dạng string — **chưa xác nhận**
  symbol thật của hợp đồng VN30F1M là gì (khả năng KHÔNG phải chuỗi "VN30F1M" mà là
  mã hợp đồng cụ thể kiểu `VN30F2508` — năm+tháng đáo hạn — cần tra `
  get_securities_info_by_index`/`get_indexes` để lấy đúng mã đang là front-month).
- `AsyncStreamingService.subscribe_symbol(...)` cũng là generic theo symbol string
  — **chưa xác nhận** có nhận đúng symbol phái sinh và trả về message cùng shape
  (`B`/`MI` envelope) như cổ phiếu hay không.

---

## Phase 0 — Mục tiêu (spike, chủ yếu READ-ONLY)

**Nguyên tắc bắt buộc cho Phase 0 này (khác Phase 0 của lệnh thật cổ phiếu):**
KHÔNG đặt lệnh thật nào trong Phase 0 — tài khoản phái sinh có đòn bẩy/ký quỹ, rủi
ro tài chính của 1 lệnh sai lớn hơn nhiều so với cổ phiếu (nơi Phase 0 cũ đã chấp
nhận đặt+huỷ 1 lệnh thật số lượng tối thiểu). Việc đặt lệnh thật (dù tối thiểu) cho
phái sinh phải là quyết định RIÊNG, hỏi lại người dùng ở 1 phase sau, sau khi đã
đọc hiểu đầy đủ dữ liệu ký quỹ thật từ Phase 0 này.

Xem prompt thực thi đầy đủ: `PROMPT_EXECUTE_DERIVATIVE_PHASE0_SPIKE.md`.

Tóm tắt các câu hỏi Phase 0 phải trả lời bằng dữ liệu thật:
1. Mã hợp đồng VN30F1M thật hiện tại là gì (front-month, ví dụ `VN30F2508`)?
2. `get_derivative_balance("0434228")` / `get_derivative_ppmmr("0434228")` trả về
   gì thật — field nào tin được, field nào nghi có bug (giống bài học `Equity*`)?
3. `get_derivative_positions("0434228")` — tài khoản có vị thế mở nào không (kỳ
   vọng rỗng, nhưng phải xác nhận bằng dữ liệu thật, không giả định)?
4. `get_ohlc_1minute("<mã hợp đồng thật>")` hoặc lịch sử — có dữ liệu giá thật trả
   về không, hình dạng field có giống `Bar` cổ phiếu đang dùng không?
5. `subscribe_symbol("<mã hợp đồng thật>")` qua `AsyncStream` trong giờ giao dịch —
   message thật nhận được có cùng shape `B`/`MI` như cổ phiếu, hay khác?

## Sau Phase 0 (chưa làm, chỉ định hướng)

Dựa trên dữ liệu thật thu được, viết plan Phase 1 riêng cho: thiết kế `Position`
model cho phái sinh (long/short/net), risk model ký quỹ (margin call thay vì
max_daily_loss_pct đơn thuần), và quyết định có đặt lệnh thật cho phái sinh hay
chỉ dừng ở mức giám sát/cảnh báo trước. Việc tái sử dụng `SmaCrossStrategy` (đã
chốt hướng) cũng cần thiết kế lại phần SELL-to-open (bán khống) ở Phase 1, không
phải Phase 0.
