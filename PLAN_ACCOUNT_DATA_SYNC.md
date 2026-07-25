# Plan: Lấy dữ liệu tài khoản giao dịch thật (SSI Portfolio/Account API)

**Ngày viết:** 2026-07-25
**Mục đích đã xác nhận với user:** Chuẩn bị nền tảng cho việc tiến tới đặt lệnh thật sau này.
**Phạm vi plan này:** **CHỈ đọc dữ liệu** (số dư, vị thế thật từ SSI) — lưu Postgres + hiện Grafana. **KHÔNG đặt lệnh thật.**

---

## ⚠️ Ranh giới quan trọng — đọc trước khi làm bất cứ gì

**Việc đặt lệnh thật (real order placement) KHÔNG nằm trong plan này**, dù đây là bước đệm hướng tới đó. Lý do tách riêng:
- Đặt lệnh thật = tiền thật, rủi ro tài chính trực tiếp, cần cơ chế an toàn riêng (giới hạn khối lượng/giá trị, xác nhận thủ công, dry-run mode, kill switch) — chưa thiết kế, chưa nên code.
- Cần `private_key` (RSA ký lệnh) — credential khác, rủi ro khác hẳn `client_id` (chỉ đọc).
- Khi tới lúc làm, cần 1 buổi lên kế hoạch riêng, độc lập với plan này.

Plan này dừng lại ở: **lấy được số dư + vị thế thật, lưu DB, hiện dashboard** — hoàn toàn read-only, không có API call nào có khả năng thay đổi trạng thái tài khoản.

---

## Đã xác nhận từ source code thật (không phải đoán)

Verify bằng `inspect.signature()` trên `ssi-sdk` 3.1.0 đã cài (2026-07-25):

### API methods có sẵn (`AsyncPortfolioService`)
```python
get_equity_balance(account_no: str) -> EquityAccountBalance
get_equity_positions(account_no: str) -> list[EquityPosition]
get_equity_ppmmr(account_no: str) -> EquityPPMMR          # margin/sức mua — hoãn, xem mục "Không làm"
get_historical_orders(account_no, from_date, to_date) -> list[Order]
get_today_orders(account_no: str) -> list[Order]
# + các biến thể derivative (phái sinh) — KHÔNG dùng, dự án chỉ trade cổ phiếu HOSE/HNX
```

### `AsyncAccountService`
```python
get_account_info() -> list[Account]   # không cần account_no, trả danh sách account dưới login
```

### Field shape đã xác nhận (`ssi_sdk.models.portfolio`)
- `EquityAccountBalance`: `account_no`, `available_cash`, `total_debt`, `withdrawal`, `on_hold_cash`, `sell_unmatched/t0/t1/t2`, `buy_unmatched/t0/t1/t2`, `bank_balance`, ... (25 field, xem output đầy đủ trong lịch sử — chọn subset khi thiết kế bảng, không lưu hết).
- `EquityPosition`: `account_no`, `symbol`, `quantity`, `cost_price`, `sellable_quantity`, `block_quantity`, `bought_quantity`, `sold_quantity`, ...

### Cách `client_id` được truyền (quan trọng — khác api_key/api_secret)
```python
class AsyncPortfolioService:
    def __init__(self, rest_client: AsyncRestClient, config: Config):
        self._client_id = config.client_id   # đọc từ Config, KHÔNG truyền per-call
```
→ `client_id` phải có trong `Config` **lúc tạo `AsyncAuth`**, không phải tham số riêng của từng lời gọi API.

### 🎯 Phát hiện quan trọng — có thể KHÔNG cần user tự tìm `client_id`

Giải mã JWT `access_token` đã lấy được ở Phase 0 (migration SDK, xem `PLAN_SSI_SDK_MIGRATION.md` mục 1.1), payload có sẵn:
```json
{
  "sub": "043422",
  "client_id": "043422",
  "accounts": "0434221,0434228,0434226",
  "scopes": "trading:*:*,data:*:*,stream:*:*"
}
```
→ `client_id` **đã nằm sẵn trong access_token đang có**, không cần credential mới, không cần user vào console tìm thêm. Có thể tự động decode JWT ngay sau khi `ensure_authenticated()` thành công, lấy `client_id` + danh sách `accounts` khả dụng — **giả thuyết cần verify ở Phase 0 discovery** (mục dưới), không chắc 100% cho tới khi test thật.

**Câu hỏi mở (Phase 0 phải trả lời):** JWT có 3 `accounts` (`0434221, 0434228, 0434226`) — cái nào là tài khoản cổ phiếu thường (equity) dùng cho `get_equity_balance`/`get_equity_positions`? Có thể cần gọi `get_account_info()` trước để biết loại từng account, hoặc thử cả 3 xem cái nào trả dữ liệu hợp lệ.

---

## Giả định chưa xác nhận (cần Phase 0 discovery, giống cách làm với Data/Stream trước đó)

1. ~~OTP có bắt buộc cho Portfolio API không?~~ ✅ **Xác nhận KHÔNG cần** — xem Phase 0 kết quả bên dưới.
2. ~~`client_id` giải mã từ JWT có đúng không?~~ ✅ **Xác nhận đúng** — `043422`, gọi API thành công.
3. ~~Account nào là equity account?~~ ✅ **Xác nhận** — xem Phase 0 kết quả bên dưới (không như giả định ban đầu).

---

## ✅ Phase 0 — Kết quả thật (2026-07-25, đã chạy)

### 1. Account types (từ `get_account_info()`)
| account_no | Loại | Ghi chú |
|---|---|---|
| `0434221` | Cash | Có tiền (`accountBalance=21459`), **0 vị thế** |
| `0434228` | Derivative | Phái sinh — **không dùng**, dự án chỉ trade cổ phiếu |
| `0434226` | Margin | **Có vị thế thật: CAP, HCM, VCB, TCX** (VCB trùng symbol dự án đang theo dõi!) |

**⚠️ Sửa lại giả định ban đầu:** Vị thế cổ phiếu thật nằm ở account **Margin** (`0434226`), không phải account "Cash" như tôi đoán lúc viết plan. `get_equity_positions()`/`get_equity_balance()` **hoạt động trên cả Cash lẫn Margin** (API gọi là "equity" theo nghĩa "không phải derivative", không phải kiểu tài khoản cụ thể) — cần đồng bộ **cả 2 account** (`0434221` + `0434226`), bỏ qua `0434228` (derivative).

### 2. OTP — KHÔNG cần cho Portfolio API
`get_equity_balance()`/`get_equity_positions()` gọi thành công (HTTP 200) chỉ bằng access_token từ `refresh()` (không OTP) — xác nhận giả định #1 sai theo hướng tốt (không nghiêm ngặt hơn Data/Stream như lo ngại).

### 3. 🐛 Bug SDK đã xác nhận — `EquityAccountBalance.from_dict()` map sai tên field

So sánh field SDK đọc (`ssi_sdk/models/portfolio.py::EquityAccountBalance.from_dict`) với response thật:

| SDK đọc | API thật trả | Khớp? |
|---|---|---|
| `data.get("availableCash")` | field thật tên `accountBalance` (không có `availableCash`) | ❌ luôn `0.0` |
| `data.get("withdrawal")` | field thật tên `withdrawable` | ❌ luôn `0.0` |
| `data.get("advanceCashT0"/"advanceCashT1")` | field thật tên `advancedCashT0`/`advancedCashT1` (có "d") | ❌ luôn `0.0` |
| còn lại (`totalDebt`, `interestLoan`, `sellUnmatched`, `buyT0-2`, `dividend`, `onHoldCash`...) | | ✅ đúng |

**Hệ quả cho thiết kế:** `available_cash`/`withdrawal`/`advance_cash_t0`/`advance_cash_t1` từ `EquityAccountBalance` (qua `get_equity_balance()`) **không dùng được** — luôn trả `0.0` bất kể giá trị thật (bug âm thầm, không raise lỗi — nguy hiểm hơn bug `APIError` ở migration trước vì dễ bị bỏ sót). Đã verify bằng dữ liệu thật: account `0434221` có `accountBalance` thật = `21459`, nhưng `EquityAccountBalance.available_cash` in ra `0.0`.

**Hướng khắc phục (quyết định lúc code Phase 1, không sửa SDK bên thứ 3):** viết hàm map riêng đọc thẳng raw dict (bypass `get_equity_balance()`'s field mapping lỗi, hoặc tự đọc `self._rest.get(EP_ACCOUNT_BALANCE, ...)` ở tầng thấp hơn), dùng tên field đúng đã xác nhận (`accountBalance`, `withdrawable`, `advancedCashT0/1`). `get_equity_positions()` **không có bug này** — field khớp đúng 100% (đã verify: `quantity`, `costPrice`, `sellableQuantity` đều đúng với raw response).

### 4. Bug nhỏ trong script spike (không phải SDK) — đã sửa
- `get_account_info()` crash serialize `AccountType` (Enum) — do `json.dumps()` không tự serialize Enum, sửa bằng `default=str`.
- `get_equity_balance()` trả `None` khi account không có phần "equity" (vd account Derivative) — script cũ gọi `dataclasses.asdict(None)` crash; sửa: check `None` trước, in "account này không có dữ liệu equity" thay vì crash.

---

## Kiến trúc đề xuất

### 1. Config — thêm `ssi_client_id` (tự động, không cần .env mới)
`trading/config.py::Config` thêm field `ssi_client_id: str` — nhưng **không đọc từ env var** như `ssi_api_key`. Thay vào đó: sau khi `ensure_authenticated()` trả token, decode JWT lấy `client_id` claim, set vào `Config`/truyền cho service. (Chi tiết kỹ thuật quyết định lúc code — có thể thêm hàm `decode_client_id(access_token: str) -> str` trong `ssi_auth.py`.)

### 2. Bảng DB mới (theo pattern `pnl_daily`/`positions` đã có)

**⚠️ Cập nhật sau Phase 0:** `available_cash`/`withdrawal`/`advance_cash_t0`/`advance_cash_t1` KHÔNG lấy qua `EquityAccountBalance` (bug SDK, luôn `0.0`) — phải tự map từ raw response (`accountBalance`, `withdrawable`, `advancedCashT0/1`). Đồng bộ **2 account** (`0434221` Cash + `0434226` Margin), bỏ qua `0434228` (derivative).

```sql
CREATE TABLE IF NOT EXISTS account_balance_snapshot (
  account_no text NOT NULL,
  ts timestamptz NOT NULL,
  account_balance double precision NOT NULL,  -- KHÔNG phải available_cash (tên field SDK sai)
  total_debt double precision NOT NULL,
  withdrawable double precision NOT NULL,      -- tên field thật, KHÔNG phải "withdrawal"
  buy_unmatched double precision NOT NULL,
  sell_unmatched double precision NOT NULL,
  PRIMARY KEY (account_no, ts)
);

CREATE TABLE IF NOT EXISTS account_position_snapshot (
  account_no text NOT NULL,
  ts timestamptz NOT NULL,
  symbol text NOT NULL,
  quantity integer NOT NULL,
  cost_price double precision NOT NULL,
  sellable_quantity integer NOT NULL,
  PRIMARY KEY (account_no, ts, symbol)
);
```
(Chỉ chọn subset field hữu ích cho dashboard — không lưu hết 25 field của `EquityAccountBalance`. Điều chỉnh khi code nếu Grafana cần thêm field cụ thể.)

### 3. Job đồng bộ định kỳ
Module mới `trading/collector/account_sync.py` — gọi `get_equity_balance`/`get_equity_positions` cho cả `0434221` và `0434226`. **Viết hàm map balance riêng** (bypass field mapping lỗi của `EquityAccountBalance.from_dict()` — đọc raw dict trực tiếp hoặc gọi REST endpoint tầng thấp hơn với tên field đúng đã xác nhận). `get_equity_positions()` dùng được thẳng, không cần workaround (đã verify field đúng). Ghi snapshot vào 2 bảng trên. Wire vào `main.py::housekeeping()` (đã có sẵn vòng lặp 30s) — gọi mỗi N phút trong giờ giao dịch (đề xuất 5 phút, khớp nhịp bar; có thể chỉnh). Dùng `ensure_authenticated()` sẵn có (Phase 1 migration) — không viết auth mới. **Không cần OTP** (đã xác nhận Phase 0).

### 4. Grafana panel mới
Thêm panel "Real Account Balance" + "Real Positions" vào dashboard hiện có, query 2 bảng trên — theo đúng pattern `test_dashboard_queries.py` đã có cho PnL/positions PaperBroker.

---

## Phase 0 — Discovery spike (bắt buộc trước khi code production)

Script tạm `scripts/spike_ssi_sdk_account.py` (giống `spike_ssi_sdk_ohlc.py`), dùng token đã có (`scripts/.ssi_sdk_token.json`):
1. Decode `access_token` JWT → in `client_id` + `accounts`.
2. Gọi `get_account_info()` → xem loại từng account (tìm account cổ phiếu thường).
3. Gọi `get_equity_balance(account_no)` + `get_equity_positions(account_no)` cho account xác định ở bước 2 — **không cần OTP trước** (test giả thuyết #1), nếu lỗi 401/403 mới cần xem xét OTP.
4. Lưu response thật ra `scripts/.spike_*.json` (đã thêm vào `.gitignore` — KHÔNG tự động commit).

**⚠️ Khác OHLC — không commit thẳng vào `tests/fixtures/`:** OHLC là dữ liệu thị trường công khai, commit thoải mái. Số dư/vị thế là **thông tin tài chính cá nhân thật** (`available_cash`, `total_debt`, số lượng cổ phiếu đang giữ...). Trước khi đưa vào `tests/fixtures/` (nếu cần fixture cho unit test), **phải làm 1 trong 2:**
- Thay số thật bằng số giả (vd `available_cash: 123456789` → `available_cash: 10000000`), giữ nguyên structure/field name, hoặc
- Không dùng fixture thật cho unit test — viết `EquityAccountBalance(...)` thủ công với giá trị bịa (giống cách `test_parser.py::test_parse_interval_message_maps_fields` đã làm với `IntervalMessage`), chỉ dùng response thật (trong `scripts/.spike_*.json`, gitignored) để **verify field name/type đúng 1 lần**, không dùng làm test fixture lâu dài.

**Kiểm chứng:** có dữ liệu thật, biết account_no đúng, biết OTP có cần không, biết field nào thật sự có giá trị (nhiều field trong `EquityAccountBalance`/`EquityPPMMR` có thể luôn = 0 nếu tài khoản không dùng margin — quan trọng để không thiết kế dashboard cho dữ liệu không tồn tại).

---

## Phase 1-3 (sau khi Phase 0 xác nhận, viết prompt thực thi riêng giống migration)

1. **Phase 1:** Schema + `Storage.save_account_balance/save_account_positions` + `ssi_auth.py` thêm decode `client_id`.
2. **Phase 2:** `account_sync.py` + wire vào `housekeeping()`.
3. **Phase 3:** Grafana panel + test.

(Chi tiết từng phase sẽ viết thành prompt thực thi riêng — giống cách đã làm với `PROMPT_EXECUTE_SSI_MIGRATION_PHASE*.md` — SAU KHI Phase 0 discovery xác nhận các giả định ở trên, để không giao việc mơ hồ cho agent thực thi.)

---

## Việc KHÔNG làm trong plan này (nhắc lại)

- Đặt lệnh thật (`AsyncTrading`/`TradingService`, `private_key`/RSA signing) — plan riêng sau.
- `get_equity_ppmmr` (margin/sức mua) — chỉ thêm nếu Phase 0 thấy tài khoản có dùng margin, không mặc định.
- Đồng bộ tài khoản phái sinh (derivative) — dự án chỉ trade cổ phiếu.

---

## Việc cần bạn làm trước

Không cần credential mới (client_id lấy tự động từ JWT theo giả thuyết trên) — chỉ cần xác nhận:
1. Đồng ý chạy Phase 0 discovery spike? (cần chạy với token thật, giống các lần trước — tôi viết script, bạn chạy vì tôi không đọc được `.env`)
2. Trong 3 account (`0434221, 0434228, 0434226`) — bạn có biết cái nào là tài khoản cổ phiếu thường không, hay để `get_account_info()` tự xác định?
