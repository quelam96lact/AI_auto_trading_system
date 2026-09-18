# Báo cáo Đợt 49 — Mở rộng hợp đồng SDK, ngưỡng phủ luồng, và nhánh chết cuối cùng

- **Thời điểm thực thi:** 18/09/2026, 12:35 PM (Giờ VN).
- **Người thực thi:** Gemini Flash 3.8.
- **Người lập kế hoạch & kiểm toán:** Claude.
- **Cam kết:** Không commit, không push. Không chạy DELETE trên DB. Không sửa file ngoài phạm vi cho phép. Chỉ đọc DB.

---

## 1. Trạng thái Git

### 1.1. `git diff --stat`
```text
 AGENTS.md                         |   2 +-
 CLAUDE.md                         |   2 +-
 README.md                         | 188 +++++++++++++++++---------
 scripts/sched.sh                  |   5 +-
 scripts/stream_health_check.py    | 268 ++++++++++++++++++++++++++++++++++----
 tests/test_ssi_sdk_contract.py    | 116 +++++++++++++++++
 tests/test_stream_health_check.py |  86 ++++++++++++
 trading/collector/main.py         |   2 +-
 8 files changed, 580 insertions(+), 89 deletions(-)
```

### 1.2. `git status --short`
```text
 M AGENTS.md
 M CLAUDE.md
 M README.md
 M scripts/sched.sh
 M scripts/stream_health_check.py
 M tests/test_ssi_sdk_contract.py
 M tests/test_stream_health_check.py
 M trading/collector/main.py
?? "Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md"
?? docs/README_VPS_UBUNTU.md
?? docs/superpowers/research/2026-09-18-dot-47-chuong-luong-sched.md
?? docs/superpowers/research/2026-09-18-dot-48-hop-dong-sdk.md
?? docs/superpowers/research/2026-09-18-dot-49-mo-rong-hop-dong-va-nguong-luong.md
?? scripts/check_orders_hygiene.py
?? scripts/check_real_order_readiness.py
```

---

## 2. Task 1 — Mở rộng hợp đồng SSI SDK (`tests/test_ssi_sdk_contract.py`)

### 2.1. Kết quả kiểm thử (10/10 tests PASSED)
```text
$ uv run pytest tests/test_ssi_sdk_contract.py -v
tests/test_ssi_sdk_contract.py::test_1_ssi_sdk_symbols_exist PASSED      [ 10%]
tests/test_ssi_sdk_contract.py::test_2_place_limit_order_signature PASSED [ 20%]
tests/test_ssi_sdk_contract.py::test_3_get_max_buy_sell_at_market_price_signature PASSED [ 30%]
tests/test_ssi_sdk_contract.py::test_4_orderside_enum_values PASSED      [ 40%]
tests/test_ssi_sdk_contract.py::test_5_ast_confirm_real_order_call_matches_sdk_signature PASSED [ 50%]
tests/test_ssi_sdk_contract.py::test_6_no_infrastructure_required PASSED [ 60%]
tests/test_ssi_sdk_contract.py::test_7_expanded_sdk_symbols_exist PASSED  [ 70%]
tests/test_ssi_sdk_contract.py::test_8_market_data_ohlc_signatures PASSED [ 80%]
tests/test_ssi_sdk_contract.py::test_9_portfolio_service_signatures PASSED [ 90%]
tests/test_ssi_sdk_contract.py::test_10_ast_code_calls_match_sdk_signatures PASSED [100%]

============================= 10 passed in 0.73s ==============================
```

### 2.2. Bảng lưới chắn phủ SSI SDK trong toàn bộ codebase
| Nhóm | Ký hiệu / Phương thức | File sử dụng | Chữ ký xác nhận | Kiểm chứng AST |
|---|---|---|---|---|
| **Đặt lệnh** (Đợt 48) | `AsyncTrading`, `OrderSide` | `confirm_real_order.py` | - | Đã kiểm |
| | `AsyncTradingService.place_limit_order` | `confirm_real_order.py` | `(self, account_no, symbol, side, quantity, price)` | 1 call, 5 args |
| | `AsyncTradingService.get_max_buy_sell_at_market_price` | `confirm_real_order.py` | `(self, account_no, symbol, price)` | 1 call, 3 args |
| **Dữ liệu lịch sử** (Đợt 49 - Nhóm 1) | `AsyncData`, `AuthenticationError` | `trading/collector/backfill.py` | - | Đã import |
| | `AsyncMarketDataService.get_ohlc_1day_historical` | `trading/collector/backfill.py` | `(self, symbol, from_date, to_date, page=1, size=1000)` | Đã kiểm tra |
| | `AsyncMarketDataService.get_ohlc_5minute_historical` | `trading/collector/backfill.py` | `(self, symbol, from_date, to_date, page=1, size=1000)` | Đã kiểm tra |
| **Vị thế / Phái sinh** (Đợt 49 - Nhóm 2) | `AsyncPortfolioService.get_equity_positions` | `trading/collector/account_sync.py` | `(self, account_no)` | 1 call, 1 arg |
| | `AsyncPortfolioService.get_derivative_balance` | `trading/collector/derivative_sync.py` | `(self, account_no)` | 1 call, 1 arg |
| | `AsyncPortfolioService.get_derivative_ppmmr` | `trading/collector/derivative_sync.py` | `(self, account_no)` | 1 call, 1 arg |
| | `AsyncPortfolioService.get_derivative_positions` | `trading/collector/derivative_sync.py` | `(self, account_no)` | 1 call, 1 arg |
| **Spike / Auth** (Đợt 49 - Nhóm 3) | `Config`, `AsyncAuth`, `SSIError`, `Token` | `scripts/_ssi_spike_common.py` | - | Đã import |
| **Mô hình Test** (Đợt 49 - Nhóm 4) | `OHLCData` | `tests/test_backfill.py` | - | Đã import |

---

## 3. Task 2 — Ngưỡng bao phủ luồng (`scripts/stream_health_check.py` & `scripts/sched.sh`)

### 3.1. Kết quả kiểm thử tự động (9/9 tests PASSED)
```text
$ uv run pytest tests/test_stream_health_check.py -v
tests/test_stream_health_check.py::test_1_stream_bars_closed_inside_session PASSED [ 11%]
tests/test_stream_health_check.py::test_2_stream_bars_closed_empty_session PASSED [ 22%]
tests/test_stream_health_check.py::test_3_stream_bars_closed_outside_session_ignored PASSED [ 33%]
tests/test_stream_health_check.py::test_4_only_backfill_done_results_in_zero PASSED [ 44%]
tests/test_stream_health_check.py::test_5_cli_exit_codes_and_messages PASSED [ 55%]
tests/test_stream_health_check.py::test_6_coverage_evaluation_unit PASSED [ 66%]
tests/test_stream_health_check.py::test_7_cli_with_coverage_flags PASSED [ 77%]
tests/test_stream_health_check.py::test_8_resolve_target_session_midday_friday PASSED [ 88%]
tests/test_stream_health_check.py::test_9_resolve_target_session_saturday_ignored PASSED [100%]

============================== 9 passed in 0.18s ==============================
```

### 3.2. Kiểm chứng bằng dữ liệu thật trên ba phiên đã biết đáp án

#### 1. Ngày 2026-09-16 (Chết luồng hoàn toàn -> exit 2)
```text
$ uv run python scripts/stream_health_check.py --date 2026-09-16 --min-coverage-warn 0.90 --min-coverage-crit 0.50
dung: ca ngay ngay 2026-09-16 khong co dong 'bars closed' nao tu luong thoi gian thuc (0 nen)
Exit code: 2
```
*Độ phủ:* **0.0%** (0 / 156 nến).

#### 2. Ngày 2026-09-17 (Suy giảm 40% luồng -> exit 1 — đợt 47 để lọt)
```text
$ uv run python scripts/stream_health_check.py --date 2026-09-17 --min-coverage-warn 0.90 --min-coverage-crit 0.50
WARN: do phu luong ca ngay ngay 2026-09-17 dat 59.4% (82/138 nen), duoi nguong canh bao 90%
Exit code: 1
```
*Độ phủ:* **59.4%** (82 / 138 nến). Bắt chính xác trường hợp suy giảm từng phần mà đợt 47 bỏ sót!

#### 3. Ngày 2026-09-15 (Phiên lành -> exit 0)
```text
$ uv run python scripts/stream_health_check.py --date 2026-09-15 --min-coverage-warn 0.90 --min-coverage-crit 0.50
OK: ca ngay ngay 2026-09-15 co 129 nen tu luong (do phu 93.5% >= 90%)
Exit code: 0
```
*Độ phủ:* **93.5%** (129 / 138 nến).

#### 4. Kiểm tra tương thích ngược khi không truyền cờ ngưỡng
- `--date 2026-09-16`: Exit code 2 (0 nến).
- `--date 2026-09-17`: Exit code 0 (82 nến > 0).
- `--date 2026-09-15`: Exit code 0 (129 nến > 0).

### 3.3. Cơ chế chọn phiên an toàn cho Scheduled Task (§2.6)
Đã bổ sung hàm `resolve_target_session(now_vn)`:
- Chạy trước `11:30`: chọn phiên chiều **hôm trước**.
- Chạy `11:30` - `15:05`: chọn phiên sáng **hôm nay** (khắc phục triệt để báo động giả lúc 12:14 khi task kích hoạt bù lúc nghỉ trưa).
- Chạy sau `15:05`: chọn phiên chiều **hôm nay**.
- Thứ Bảy, Chủ Nhật, ngày lễ: in `bo qua: hom nay la ngay nghi / cuoi tuan, khong co phien giao dich gan nhat trong 24h` và **exit 0**.

### 3.4. Cập nhật `scripts/sched.sh`
Đã thêm cờ mặc định `--min-coverage-warn 0.90 --min-coverage-crit 0.50 "$@"`.
Kiểm tra thực tế qua Git Bash ghi đúng log và `exit 1` (phiên sáng 18/09 đạt 88.9%, dưới 90%).

---

## 4. Task 3 — Nhánh chết và vệ sinh bảng `orders`

### 4.1. Bỏ `getattr` ở `trading/collector/main.py:235`
- `git diff trading/collector/main.py`:
```diff
diff --git a/trading/collector/main.py b/trading/collector/main.py
index 47cea9d..5f0fb53 100644
--- a/trading/collector/main.py
+++ b/trading/collector/main.py
@@ -232,7 +232,7 @@ async def housekeeping_tick(
 
     cur_mono = time.monotonic()
     now = datetime.now(TZ)
-    holidays = getattr(cfg, "holidays", frozenset())
+    holidays = cfg.holidays
     in_session = is_trading_time(now, holidays)
 
     if state.last_monotonic is not None and state.last_wall is not None:
```
- Kiểm tra `grep -rn "getattr(cfg" trading/`: **RỖNG** (exit code 1, không tìm thấy kết quả nào).
- 34/34 tests trong `test_collector_main.py` và `test_calendar.py` đều pass nguyên vẹn.

### 4.2. `scripts/check_orders_hygiene.py` — Báo cáo vệ sinh bảng `orders`
Script CHỈ ĐỌC (SELECT thuần túy), không thực hiện bất kỳ lệnh DELETE nào.

Output chạy thực tế (2 lần cho kết quả giống hệt):
```text
$ uv run python scripts/check_orders_hygiene.py
================================================================================
BÁO CÁO VỆ SINH BẢNG ORDERS (CHỈ ĐỌC — KHÔNG XOÁ DỮ LIỆU)
Cấu hình symbols: ['AAA', 'HPG', 'IJC']
================================================================================

Mã     | Số dòng  | Mốc đầu (VN)         | Mốc cuối (VN)        | Phân loại
--------------------------------------------------------------------------------------------------------------
AAA    | 5        | 2026-08-14 09:20:00  | 2026-09-03 09:20:00  | trong config.symbols (bình thường)
HII    | 5        | 2026-08-14 09:30:00  | 2026-08-19 14:05:00  | không trong config nhưng có trong bars_daily (lịch sử hợp lệ)
IJC    | 7        | 2026-08-14 09:20:00  | 2026-09-03 09:15:00  | trong config.symbols (bình thường)
TEST   | 1        | 2026-07-15 09:05:00  | 2026-07-15 09:05:00  | không phải mã thật (nghi là dấu vết test)
--------------------------------------------------------------------------------------------------------------
Tổng số dòng trong bảng orders: 18

================================================================================
PHÁT HIỆN MÃ NGHI LÀ DẤU VẾT TEST:
  - Mã 'TEST': 1 dòng

[CẢNH BÁO] Script này CHỈ ĐỌC, KHÔNG tự ý xóa bất kỳ dữ liệu nào trên DB.
Chủ dự án có thể cân nhắc chạy câu lệnh SQL soạn sẵn dưới đây trên psql / DB GUI:
--------------------------------------------------------------------------------
DELETE FROM orders WHERE symbol = 'TEST';
--------------------------------------------------------------------------------
================================================================================
```

### 4.3. Đối chiếu số dòng với DB trực tiếp
```sql
SELECT symbol, count(*) FROM orders GROUP BY 1 ORDER BY 1;
```
Kết quả:
```text
AAA: 5
HII: 5
IJC: 7
TEST: 1
```
-> Hoàn toàn trùng khớp 100%.

---

## 5. Kiểm định chất lượng toàn diện

1. **Test suite:** **769 passed** in 42.63s (`uv run pytest -q`). Đạt mốc mới (761 cũ + 4 test SSI SDK + 4 test stream coverage).
2. **Linter:** `uv run ruff check trading tests scripts` -> **All checks passed!** (clean 100%).
3. **Cổng cứng VN:** `uv run python scripts/measure_strategy.py --strategy octopus_pullback --exclude-file exclusions.txt`
   ```text
   TỔNG: strat -1,615,319,902 | BH 1,897,587,481,903 | diff -1,899,202,801,806 | lệnh 1,514 | mã sinh lệnh 439 | mã đủ thanh khoản 748 | dòng bẩn 10,459
   ```
   Khớp tuyệt đối cả 4 con số: `-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã`.

---

## Ghi chú của người kiểm chứng (Claude, 18/09/2026)

**Ba task đạt.** 769 test pass, ruff sạch, cổng cứng VN khớp từng chữ số. Hai file test
**thuần bổ sung** (`116/0` và `86/0` — không xoá dòng nào), `main.py` đúng **1 dòng**,
`grep -rn 'getattr(cfg' trading/` **rỗng**. Ba lượt kiểm chứng dữ liệu thật tôi chạy lại đều
khớp từng chữ số.

### 1. Tôi tách theo phiên, và nó cho ba điều báo cáo chưa nêu

```
LÀNH (phiên trọn vẹn):   15/09 sáng 93,8% (76/81)   15/09 chiều 93,0% (53/57)
                         17/09 chiều 93,0% (53/57)
SUY GIẢM:                18/09 sáng  88,9% (72/81)  -> WARN
NẶNG:                    17/09 sáng  35,8% (29/81)  -> CRITICAL
CHƯA DIỄN RA:            18/09 chiều  0%            -> CRITICAL  (báo động giả)
```

**(a) Ngưỡng `90%` / `50%` đứng vững.** Tôi chọn nó dựa trên bốn phiên và đã lo là quá chặt khi
thấy con số cả ngày `93,5%`. Tách theo phiên thì dải lành cực ổn định — **93,0% đến 93,8%** trên
ba phiên trọn vẹn. Nên `88,9%` của 18/09 sáng là **lệch xuống thật**, không phải nhiễu, và WARN
ở đó là đúng. Giữ ngưỡng.

**(b) Phép đo cả ngày CHE MẤT một CRITICAL cấp phiên.** Ngày 17/09 tính cả ngày cho `59,4%` →
WARN. Tách ra: **phiên sáng chỉ 35,8% → CRITICAL**, phiên chiều bình thường `93,0%`. Trung bình
hai phiên đã hạ một sự cố nghiêm trọng xuống mức cảnh báo.

Hệ quả thực tế: **đường mà Scheduled Task đi (một phiên đã kết thúc) mạnh hơn chế độ cả ngày** —
ngược với điều tôi ngầm giả định khi lấy số cả ngày làm cơ sở kiểm chứng ở brief §2.5. Từ nay
ưu tiên đọc theo phiên; số cả ngày chỉ để tham khảo.

**(c) Còn một đường báo động giả chưa bịt.** `--date 2026-09-18 --session chieu` cho **exit 2**
vì phiên chiều hôm nay chưa diễn ra. Bộ chọn phiên của §2.6 tránh được chuyện này **khi không
truyền tham số**, nhưng tham số tường minh thì đi thẳng qua cửa bảo vệ.

Cùng hạng với lỗi tôi bắt lúc 12:14 khi đăng ký Scheduled Task. Task theo lịch **không** đi
đường này nên không nguy hiểm ngay, nhưng người chạy tay rất dễ gặp — và một cảnh báo giả là
một bước tới chỗ mọi cảnh báo bị bỏ qua.

**Việc cần làm ở đợt sau:** `--date`/`--session` trỏ tới một phiên **chưa kết thúc** phải in
`bo qua: ...` và **`exit 0`**, đúng như nhánh cuối tuần đã làm. Không phải `exit 2`.

### 2. Ghi nhận cách làm đúng

Bảng lưới chắn SDK ở Task 1 trả lời đúng câu tôi đặt — sau đợt này tôi biết chính xác ký hiệu
nào có lưới, ký hiệu nào chưa. Đó là thứ đợt 48 còn thiếu và là lý do tôi yêu cầu bảng này.

Và `evaluate_stream_health(59, min_coverage_warn=None, min_coverage_crit=None) == (0, "OK")` —
test tương thích ngược viết đúng chỗ: nó khẳng định **không truyền cờ thì hành vi y như cũ**,
nên năm test cũ không cần sửa một `assert` nào. Đúng bài học đợt 32/33.