# Báo cáo Đợt 48 — Hợp đồng SDK và mức sẵn sàng của đường lệnh thật

- **Thời điểm thực thi:** 18/09/2026, 11:38 AM (Giờ VN).
- **Người thực thi:** Gemini Flash 3.8.
- **Người lập kế hoạch & kiểm toán:** Claude.
- **Cam kết:** Không commit, không push. Không sửa file có sẵn nào trong repo. Chỉ đọc DB, không ghi DB, không gọi mạng/SSI SDK.

---

## 1. Trạng thái Git

### 1.1. `git diff --stat`
```text
 AGENTS.md              |   2 +-
 CLAUDE.md              |   2 +-
 README.md              | 188 ++++++++++++++++++++++++++++++++-----------------
 scripts/run_hidden.vbs |   2 +-
 scripts/sched.sh       |   8 ++-
 5 files changed, 135 insertions(+), 67 deletions(-)
```
*(Ghi chú: Toàn bộ thay đổi ở trên thuộc về công việc trước đó của người dùng và Đợt 47. Trong Đợt 48, **không có bất kỳ file có sẵn nào bị chỉnh sửa**).*

### 1.2. `git status --short`
```text
 M AGENTS.md
 M CLAUDE.md
 M README.md
 M scripts/run_hidden.vbs
 M scripts/sched.sh
?? "Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md"
?? docs/README_VPS_UBUNTU.md
?? docs/superpowers/research/2026-09-18-dot-47-chuong-luong-sched.md
?? docs/superpowers/research/2026-09-18-dot-48-hop-dong-sdk.md
?? scripts/check_real_order_readiness.py
?? tests/test_ssi_sdk_contract.py
```

---

## 2. Task 1 — Test hợp đồng SSI SDK (`tests/test_ssi_sdk_contract.py`)

### 2.1. Kết quả kiểm thử
Đã tạo file mới `tests/test_ssi_sdk_contract.py` gồm 6 bài kiểm tra độc lập:
```text
$ uv run pytest tests/test_ssi_sdk_contract.py -v
tests/test_ssi_sdk_contract.py::test_1_ssi_sdk_symbols_exist PASSED      [ 16%]
tests/test_ssi_sdk_contract.py::test_2_place_limit_order_signature PASSED [ 33%]
tests/test_ssi_sdk_contract.py::test_3_get_max_buy_sell_at_market_price_signature PASSED [ 50%]
tests/test_ssi_sdk_contract.py::test_4_orderside_enum_values PASSED      [ 66%]
tests/test_ssi_sdk_contract.py::test_5_ast_confirm_real_order_call_matches_sdk_signature PASSED [ 83%]
tests/test_ssi_sdk_contract.py::test_6_no_infrastructure_required PASSED [100%]

============================== 6 passed in 0.70s ==============================
```

### 2.2. Chi tiết các kiểm định cốt lõi (§1.3)
1. **Tồn tại ký hiệu:** Mọi ký hiệu trong bảng §1.2 (`AsyncTrading`, `OrderSide`, `AsyncTradingService.place_limit_order`, `AsyncTradingService.get_max_buy_sell_at_market_price`, `AsyncAuth`, `Config`, `Token`, `EP_ACCOUNT_BALANCE`, `AsyncPortfolioService`, `AsyncStream`, `Timeframe`) đều import thành công và tồn tại trên lớp.
2. **Chữ ký `place_limit_order`:**
   - Chữ ký thực tế: `(self, account_no: 'str', symbol: 'str', side: 'OrderSide', quantity: 'int', price: 'float') -> 'PlaceOrderResponse'`
   - Danh sách tham số và thứ tự: `['self', 'account_no', 'symbol', 'side', 'quantity', 'price']` — khớp chính xác 100%.
3. **Chữ ký `get_max_buy_sell_at_market_price`:**
   - Chữ ký thực tế: `(self, account_no: 'str', symbol: 'str') -> 'MaxBuySellResponse'`
   - Danh sách tham số và thứ tự: `['self', 'account_no', 'symbol']` — khớp chính xác 100%.
4. **Enum `OrderSide`:** Chứa đúng hai thuộc tính `BUY` và `SELL`.
5. **Khớp nối AST giữa code thật và SDK (Test số 5 — ĐÃ XANH):**
   - Phân tích cú pháp AST của file `scripts/confirm_real_order.py`:
     - Lời gọi tại dòng 151: `trading_client.trading.place_limit_order(order["account_no"], order["symbol"], side, order["quantity"], order["price"])`.
     - Số lượng đối số vị trí: **đúng 5 đối số**, 0 từ khóa (`keywords=[]`).
     - Khớp chính xác với 5 tham số bắt buộc của `AsyncTradingService.place_limit_order` (loại trừ `self`).
6. **Không phụ thuộc hạ tầng:** Test chạy thuần túy trên phân tích lớp (`inspect`, `ast`), không khởi tạo client, không gọi mạng, không đọc `.env`, không cần Docker hay DB.

### 2.3. Báo cáo các vị trí sử dụng SDK ngoài bảng §1.2 (theo yêu cầu §1.2)
Quét toàn bộ codebase phát hiện các điểm sử dụng `ssi_sdk` ngoài bảng §1.2 như sau:
1. `trading/collector/backfill.py`:
   - Dòng 207: `from ssi_sdk import AsyncData`
   - Dòng 237: `from ssi_sdk.exceptions import AuthenticationError`
2. `trading/collector/derivative_sync.py`:
   - Dòng 108: `from ssi_sdk.services.portfolio import AsyncPortfolioService` (sử dụng cùng class trong `account_sync.py` nhưng nằm tại module phái sinh).
3. `scripts/_ssi_spike_common.py`:
   - Dòng 32: `from ssi_sdk import Config`
   - Dòng 63: `from ssi_sdk import AsyncAuth`
   - Dòng 64: `from ssi_sdk.exceptions import SSIError`
   - Dòng 65: `from ssi_sdk.models import Token`
4. `tests/test_backfill.py`:
   - Dòng 214, 230, 343...: `from ssi_sdk.models import OHLCData`
   - Dòng 403, 502, 540: `from ssi_sdk.exceptions import AuthenticationError`

Tuân thủ nghiêm ngặt chỉ dẫn: Không tự ý thêm các ký hiệu này vào test hợp đồng để Claude ghi nhận việc quét sót.

---

## 3. Task 2 — Báo cáo mức sẵn sàng của đường lệnh thật (`scripts/check_real_order_readiness.py`)

### 3.1. Toàn văn output terminal khi chạy `scripts/check_real_order_readiness.py`

```text
================================================================================
BÁO CÁO MỨC ĐỘ SẴN SÀNG CỦA ĐƯỜNG LỆNH THẬT — 2026-09-18 11:36:00 (GIỜ VN)
Tài khoản đang cấu hình (real_order_account): 0434221
Danh mục theo dõi: HPG, IJC, AAA
================================================================================

(a) TRẠNG THÁI ĐƯỜNG LỆNH THẬT
----------------------------------------
  • Tổng số pending_real_orders : 9 (expired: 9)
  • Số lệnh có ssi_order_id     : 0 (chưa từng đặt thành công lên sàn)
  • Số dòng real_order_fills    : 0
  • Thời điểm lệnh gần nhất     : 2026-09-04 09:20:17

(b) SỨC MUA SO VỚI NHU CẦU (Tài khoản cấu hình: 0434221)
--------------------------------------------------------------------------------
Mã     | Max Buy Qty  | Giá gần nhất    | Giá trị mua tối đa   | Đủ 1 lô (100cp)?  
--------------------------------------------------------------------------------
HPG    | 221          | 21,450 VND      | 4,740,450 VND        | ĐỦ (>= 100)       
IJC    | 677          | 6,920 VND       | 4,684,840 VND        | ĐỦ (>= 100)       
AAA    | 641          | 7,330 VND       | 4,698,530 VND        | ĐỦ (>= 100)       
--------------------------------------------------------------------------------
  • Tuổi bản ghi sức mua HPG: 2m 27s (lúc 11:33:33)
  • Tuổi bản ghi sức mua IJC: 2m 27s (lúc 11:33:33)
  • Tuổi bản ghi sức mua AAA: 2m 27s (lúc 11:33:33)

(c) SO SÁNH HAI TÀI KHOẢN (0434221 vs 0434226 - Dữ liệu cho Q-2)
--------------------------------------------------------------------------------
  Tài khoản 0434221:
    - NAV mới nhất        : 5,021,712 VND (lúc 2026-09-18 11:33:33)
    - Mã chưa định giá    : Không có
  Tài khoản 0434226:
    - NAV mới nhất        : 193,878,191 VND (lúc 2026-09-18 11:33:33)
    - Mã chưa định giá    : Không có

  So sánh sức mua (max_buy_qty) giữa hai tài khoản:
  Mã     | 0434221 (Đang cấu hình)   | 0434226 (Tài khoản lớn)   | Tỷ lệ chênh lệch  
  ----------------------------------------------------------------------------
  HPG    | 221                       | 5,824                     | 26.4x             
  IJC    | 677                       | 17,835                    | 26.3x             
  AAA    | 641                       | 14,352                    | 22.4x             

(d) TUỔI DỮ LIỆU CỦA MỌI LÁ CHẮN (Fail-safes)
--------------------------------------------------------------------------------
  1. Lá chắn độ tươi vị thế (account_sync_log):
     Mốc sync gần nhất: 2026-09-18 11:33:33
     Trạng thái: Tuổi: 2m 27s (ngưỡng <= 15m) -> ĐẠT
  2. Lá chắn độ tươi sức mua (account_buying_power):
     Mốc sync gần nhất: 2026-09-18 11:33:33
     Trạng thái: Tuổi: 2m 27s (ngưỡng <= 15m) -> ĐẠT

  => KẾT LUẬN CỦA BỘ LÁ CHẮN TẠI THỜI ĐIỂM HIỆN TẠI:
     [SẴN SÀNG] Nếu phát sinh tín hiệu lúc này, lệnh SẼ ĐƯỢC CHẤP THUẬN qua các lá chắn bảo vệ.
================================================================================
```

### 3.2. Kiểm chứng 2 lần chạy liên tiếp (§2.2.1)
- Lần chạy 1 (11:36:00): Tuổi bản ghi 2m 27s.
- Lần chạy 2 (11:36:06): Tuổi bản ghi 2m 33s (+6 giây đúng theo thời gian thực).
- Mọi con số khác về trạng thái lệnh, NAV, `max_buy_qty`, giá gần nhất, trạng thái ĐẠT/TỪ CHỐI hoàn toàn giống hệt 100%.

### 3.3. Đối chiếu trực tiếp bằng truy vấn SQL (§2.2.2)

1. **SQL Đối chiếu 1 — NAV mới nhất mỗi tài khoản:**
   ```sql
   SET TimeZone='Asia/Ho_Chi_Minh';
   SELECT DISTINCT ON (account_no) account_no, nav, ts
   FROM account_nav_snapshot
   WHERE account_no IN ('0434221', '0434226')
   ORDER BY account_no, ts DESC;
   ```
   *Kết quả thực tế:*
   - `('0434221', 5021712.0, 2026-09-18 11:33:33.080006+07:00)`
   - `('0434226', 193878191.2, 2026-09-18 11:33:33.080006+07:00)`
   *Khớp 100% với báo cáo.*

2. **SQL Đối chiếu 2 — `max_buy_qty` của tài khoản `0434221`:**
   ```sql
   SET TimeZone='Asia/Ho_Chi_Minh';
   SELECT DISTINCT ON (symbol) symbol, max_buy_qty, ts
   FROM account_buying_power
   WHERE account_no = '0434221' AND symbol IN ('HPG', 'IJC', 'AAA')
   ORDER BY symbol, ts DESC;
   ```
   *Kết quả thực tế:*
   - `AAA: 641 (ts: 2026-09-18 11:33:33.080006+07:00)`
   - `HPG: 221 (ts: 2026-09-18 11:33:33.080006+07:00)`
   - `IJC: 677 (ts: 2026-09-18 11:33:33.080006+07:00)`
   *Khớp 100% với báo cáo.*

3. **SQL Đối chiếu 3 — Trạng thái pending real orders:**
   ```sql
   SELECT status, count(*), count(ssi_order_id)
   FROM pending_real_orders
   GROUP BY status;
   ```
   *Kết quả thực tế:* `('expired', 9, 0)` -> 9 lệnh hết hạn, 0 lệnh có mã SSI.

### 3.4. Xác nhận không ghi DB (§2.2.3)
`scripts/check_real_order_readiness.py` chỉ dùng `psycopg.connect()` kết nối trực tiếp, chỉ thực thi các truy vấn `SELECT`, không import bất kỳ hàm ghi nào của `Storage` (`record_*`, `write_*`, `create_*`, `update_*`).

---

## 4. Ba dòng kiểm định bắt buộc

1. **Test suite:** **761 passed in 44.72s** (mốc cũ 755 + 6 test SDK contract mới = 761, 100% passed).
2. **Ruff check:** Clean 100% (`All checks passed!`).
3. **Cổng cứng VN:** Khớp tuyệt đối bốn con số (`exit 0`):
   ```text
   -1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã
   ```
   *(Toàn văn: `TỔNG: strat -1,615,319,902 | BH 1,897,587,481,903 | diff -1,899,202,801,806 | lệnh 1,514 | mã sinh lệnh 439 | mã đủ thanh khoản 748 | dòng bẩn 10,459`)*.
