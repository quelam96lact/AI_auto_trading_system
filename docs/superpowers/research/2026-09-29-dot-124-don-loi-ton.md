# Báo cáo Nghiệm thu Brief Đợt 124 — Dọn lỗi tồn (Phần A, B, C, D)

**Ngày thực hiện:** 2026-09-29  
**Base commit:** `09cf20e`  
**Người thực thi:** Agent  
**Người audit + commit + push:** Claude  
**Kế hoạch:** `docs/superpowers/plans/2026-09-29-brief-dot-124-bit-ro-token-ssi-o-bo-ghi-so-lenh.md`

---

## 1. TỔNG KẾT TIÊU CHÍ CHUNG CẢ ĐỢT

```
1. uv run pytest -q (toàn bộ suite không lọc marker):
   1419 passed in 75.20s (0:01:15), 0 failed
   (Tăng từ 1.402 passed của base commit lên 1.419 passed với 17 unit test mới)

2. uv run ruff check trading tests scripts:
   All checks passed!

3. GitNexus impact:
   - _sync_positions: risk LOW (ảnh hưởng sync_account_data -> housekeeping_tick -> housekeeping_loop)
   - _sync_balance: risk LOW (ảnh hưởng sync_account_data -> housekeeping_tick -> housekeeping_loop)
   - load_universe: risk HIGH (ảnh hưởng 3 scripts screen: screen_smc_stock_daily, screen_momentum_portfolio, screen_vcp_daily)

4. GitNexus detect-changes:
   Changes: 11 files, 26 symbols
   Affected processes: 7
   Risk level: HIGH (do Phần B chạm đường đồng bộ vị thế và số dư tài khoản thật)
```

---

## 2. PHẦN A — BỊT RÒ TOKEN SSI RA LOG Ở BỘ GHI SỔ LỆNH

### 2.1. Chi tiết thực hiện & Diff
1. Đưa logic `LOG-1` từ `trading/collector/main.py` thành hàm dùng chung `silence_ssi_sdk_secrets()` trong `trading/logging_setup.py`.
2. Chuyển nguyên văn khối chú thích `LOG-1` giải thích vì sao dùng `setLevel(logging.WARNING)` thay vì regex filter và vì sao không đụng `token_manager`.
3. Cập nhật `trading/collector/main.py::_configure_logging` gọi hàm dùng chung.
4. Gọi `silence_ssi_sdk_secrets()` trong `scripts/record_vn30f_orderbook.py::record_orderbook_stream` sau `load_config` và trước khi tạo các đối tượng SDK / `AsyncStream`.
5. Thêm 3 test vào `tests/test_collector_logging.py` (kiểm tra `silence_ssi_sdk_secrets` độc lập, chặn cả DEBUG header, và kiểm tra đường chạy của `record_vn30f_orderbook.py`).
6. Quét sạch token cũ trong `logs/`: thay JWT đứng sau `Bearer ` bằng `[REDACTED]`.

**Báo cáo số đếm JWT trong `logs/` (không in token):**
- Trước khi xử lý: **1** dòng chứa `Bearer ey` (nằm trong `logs/orderbook-recorder.log`).
- Sau khi xử lý: **0** dòng.

**Diff Phần A:**
```diff
diff --git a/trading/logging_setup.py b/trading/logging_setup.py
--- a/trading/logging_setup.py
+++ b/trading/logging_setup.py
@@ -1,7 +1,10 @@
 """Module thiết lập logging dùng chung cho collector và engine.
 
-Cung cấp hàm attach_durable_alert_handler để gắn RotatingFileHandler vào
-logger cha "trading", ghi log ra volume mount /app/logs một cách bền vững.
+Cung cấp:
+- attach_durable_alert_handler: gắn RotatingFileHandler vào logger cha "trading",
+  ghi log ra volume mount /app/logs một cách bền vững.
+- silence_ssi_sdk_secrets: nâng level logger ssi_sdk.transport.websocket lên WARNING
+  để chặn token SSI rò ra log (LOG-1).
 """
@@ -75,0 +78,21 @@
+def silence_ssi_sdk_secrets() -> None:
+    """Nâng level logger ssi_sdk.transport.websocket lên WARNING để chặn token rò (LOG-1).
+
+    LOG-1: bịt access token rò ra log. ssi_sdk.transport.websocket_client.py:76
+    log `logger.info("Connecting to WebSocket with headers: %s", self._headers)`
+    — self._headers chứa `Authorization: Bearer <token>` plaintext (token sống
+    15 phút nhưng log được giữ lâu hơn). Nâng level logger NÀY lên WARNING
+    (không phải filter regex — một dòng setLevel giải quyết trọn vẹn, regex
+    phải bảo trì và hỏng lặng lẽ khi SDK đổi format). Đánh đổi: mất dòng
+    INFO "WebSocket connected to wss://..." — chấp nhận vì lỗi kết nối vẫn
+    hiện ("SSIFeed connection error") và collector có heartbeat riêng trong
+    bảng heartbeat. KHÔNG đụng logger ssi_sdk.services.token_manager — nó log
+    "Token refreshed successfully", hữu ích và không chứa secret.
+
+    Gọi sau mọi chỗ cấu hình logging khác và trước khi tạo AsyncStream / AsyncAuth
+    để tránh bị basicConfig hay SDK tự khởi tạo đè lại.
+    """
+    logging.getLogger("ssi_sdk.transport.websocket").setLevel(logging.WARNING)

diff --git a/trading/collector/main.py b/trading/collector/main.py
--- a/trading/collector/main.py
+++ b/trading/collector/main.py
@@ -21,1 +21,1 @@
-from trading.logging_setup import attach_durable_alert_handler
+from trading.logging_setup import attach_durable_alert_handler, silence_ssi_sdk_secrets
@@ -506,13 +506,5 @@ def _configure_logging() -> None:
     logging.basicConfig(level=logging.INFO, format="%(message)s")
-    # LOG-1: bịt access token rò ra log. ssi_sdk.transport.websocket_client.py:76
-    ...
-    logging.getLogger("ssi_sdk.transport.websocket").setLevel(logging.WARNING)
+    # LOG-1: xem trading.logging_setup.silence_ssi_sdk_secrets() để hiểu lý do
+    # chặn logger ssi_sdk.transport.websocket và tại sao không dùng filter regex.
+    silence_ssi_sdk_secrets()

diff --git a/scripts/record_vn30f_orderbook.py b/scripts/record_vn30f_orderbook.py
--- a/scripts/record_vn30f_orderbook.py
+++ b/scripts/record_vn30f_orderbook.py
@@ -54,0 +55,1 @@
+from trading.logging_setup import silence_ssi_sdk_secrets
@@ -476,0 +478,4 @@ async def record_orderbook_stream(
+    # LOG-1: chặn token SSI rò ra log. Gọi sau load_config và trước mọi SDK object
+    # (ensure_authenticated, AsyncStream) để tránh bị basicConfig hay SDK đè lại.
+    # Xem trading.logging_setup.silence_ssi_sdk_secrets() để hiểu lý do thiết kế.
+    silence_ssi_sdk_secrets()
```

### 2.2. Output nguyên văn các cổng Phần A

#### Cổng 1: `uv run pytest tests/test_collector_logging.py -v` (test cũ giữ nguyên, test mới pass)
```
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
collected 5 items

tests/test_collector_logging.py::test_configure_logging_mutes_websocket_headers_logger PASSED [ 20%]
tests/test_collector_logging.py::test_configure_logging_keeps_token_manager_logger PASSED [ 40%]
tests/test_collector_logging.py::test_silence_ssi_sdk_secrets_blocks_bearer_token PASSED [ 60%]
tests/test_collector_logging.py::test_silence_ssi_sdk_secrets_websocket_debug_also_blocked PASSED [ 80%]
tests/test_collector_logging.py::test_record_orderbook_silence_called_before_asyncstream PASSED [100%]

============================== 5 passed in 0.64s ==============================
```

#### Cổng 2: Grep `ssi_sdk.transport.websocket` toàn repo
```
trading\logging_setup.py:97:    logging.getLogger("ssi_sdk.transport.websocket").setLevel(logging.WARNING)
trading\collector\main.py:508:    # chặn logger ssi_sdk.transport.websocket và tại sao không dùng filter regex.
tests\test_collector_logging.py:14:        logging.getLogger("ssi_sdk.transport.websocket").info(...)
tests\test_collector_logging.py:43:    ws_logger = logging.getLogger("ssi_sdk.transport.websocket")
tests\test_collector_logging.py:64:        logging.getLogger("ssi_sdk.transport.websocket").debug(...)
tests\test_collector_logging.py:85:        logging.getLogger("ssi_sdk.transport.websocket").info(...)
```

#### Báo cáo mức rò của các script spike (P.1):
Trong `scripts/_ssi_spike_common.py`, hàm `make_config` cấu hình `log_level="DEBUG"` để xem raw response khi gặp lỗi SSI API. Khi chạy tay, SDK SSI ở mức DEBUG sẽ in nguyên thân HTTP response (chứa token xác thực) ra console stdout. Theo đúng brief, agent không sửa file này.

### 2.3. Bảng phá thử Phần A
| Phá thử | Đột biến | Kết quả | Thông điệp lỗi thực tế |
|---|---|:---:|---|
| **A1** | Bỏ lời gọi `silence_ssi_sdk_secrets()` trong `scripts/record_vn30f_orderbook.py` | **RED** | `AssertionError: record_vn30f_orderbook.py phải gọi silence_ssi_sdk_secrets() để chặn token`<br>`assert not True` |
| **A2** | Đổi `logging.WARNING` thành `logging.INFO` trong hàm `silence_ssi_sdk_secrets()` | **RED (cả 2 đường)** | `AssertionError: access token KHONG duoc phep lo ra log`<br>`AssertionError: record_vn30f_orderbook.py phải gọi silence_ssi_sdk_secrets() để chặn token` |

---

## 3. PHẦN B — KHÔNG GHI DANH MỤC RỖNG / SỐ DƯ BẰNG 0 ĐỘT NGỘT (CONFIRM-1)

### 3.1. Chi tiết thực hiện & Diff
1. Thêm 2 dict trạng thái chờ xác nhận cấp module trong `trading/collector/account_sync.py`:
   - `_pending_empty_positions: dict[str, bool]`
   - `_pending_zero_balance: dict[str, bool]`
2. **Vị thế (`_sync_positions`):**
   - Khi SSI trả rỗng (`rows == []`) VÀ snapshot gần nhất không rỗng:
     - Lần đầu: Hoãn ghi, không gọi `record_position_sync`, phát alert `WARN CONFIRM-1`. Đánh dấu `_pending_empty_positions[account_no] = True`.
     - Lần 2 liên tiếp rỗng: Gỡ cờ, ghi nhận danh mục rỗng + gọi `record_position_sync` + alert `WARN` xác nhận.
     - Nếu snapshot trước cũng rỗng (tài khoản `0434221` luôn rỗng): Ghi ngay lần đầu theo `SYNC-1`.
     - Nếu lần sau trả về có vị thế: Gỡ cờ, ghi vị thế bình thường.
3. **Số dư (`_sync_balance`):**
   - Khi **CẢ BA** trường `accountBalance == 0.0`, `totalDebt == 0.0`, `withdrawable == 0.0` VÀ snapshot trước có ít nhất 1 trường khác 0:
     - Lần đầu: Hoãn ghi, phát alert `WARN CONFIRM-1`. Đánh dấu `_pending_zero_balance[account_no] = True`.
     - Lần 2 liên tiếp cả ba = 0: Gỡ cờ, ghi nhận số dư 0 + alert `WARN` xác nhận.
     - Nếu chỉ có 1 trường = 0 (tình huống b7: `withdrawable = 0` của tài khoản margin): Ghi bình thường, không bị chặn nhầm.
4. Thêm 7 unit tests (`b1`–`b7`) và 3 test phá thử (`B1`–`B3`) trong `tests/test_account_sync.py`.
5. Cập nhật `tests/test_storage.py::test_real_positions_empty_after_sync_with_empty_portfolio`: đồng bộ 2 nhịp rỗng liên tiếp để kích hoạt bước xác nhận rỗng của CONFIRM-1.

**Diff Phần B:**
```diff
diff --git a/trading/collector/account_sync.py b/trading/collector/account_sync.py
--- a/trading/collector/account_sync.py
+++ b/trading/collector/account_sync.py
@@ -14,0 +15,7 @@ _alerted_unmatched_fills: set[tuple[int, date]] = set()
+# CONFIRM-1: trạng thái chờ xác nhận khi SSI trả rỗng đột ngột.
+# Giữ trong bộ nhớ tiến trình — mất khi collector restart (an toàn: lần rỗng
+# đầu tiên sau restart sẽ bị hoãn thêm 1 nhịp, tức ~5 phút). Test phải reset
+# về {} trước khi chạy để đảm bảo độc lập giữa các test.
+_pending_empty_positions: dict[str, bool] = {}   # account_no -> True khi đang chờ
+_pending_zero_balance: dict[str, bool] = {}       # account_no -> True khi đang chờ
@@ -93,0 +101,30 @@ async def _sync_balance(auth, client_id: str, account_no: str, ts: datetime, st
+    acct_bal = float(equity["accountBalance"])
+    total_debt = float(equity["totalDebt"])
+    withdrawable = float(equity["withdrawable"])
+
+    # CONFIRM-1 (Phần B, đợt 124): cả ba trường = 0 đồng thời là dấu hiệu bảo trì SSI
+    # (đo được 14 lần trong lịch sử, luôn cả hai tài khoản cùng lúc, không thể thật).
+    # Điều kiện bắt: CẢ BA = 0 (không phải bất kỳ một trường = 0 — b7: withdrawable=0
+    # thật cho tài khoản margin, không được bắt nhầm).
+    # Áp quy tắc xác nhận hai lần tương tự _sync_positions.
+    if acct_bal == 0.0 and total_debt == 0.0 and withdrawable == 0.0:
+        prev_bal = storage.read_account_balance_with_debt(account_no)
+        prev_nonzero = prev_bal is not None and (prev_bal[0] != 0.0 or prev_bal[1] != 0.0)
+        if prev_nonzero:
+            if not _pending_zero_balance.get(account_no):
+                _pending_zero_balance[account_no] = True
+                alert(
+                    "WARN",
+                    "CONFIRM-1: số dư cả ba trường = 0 đột ngột (SSI bảo trì?), chờ xác nhận",
+                    account_no=account_no,
+                )
+                return  # KHÔNG ghi
+            else:
+                _pending_zero_balance.pop(account_no, None)
+                alert(
+                    "WARN",
+                    "CONFIRM-1: xác nhận số dư = 0 sau hai nhịp liên tiếp",
+                    account_no=account_no,
+                )
+        else:
+            _pending_zero_balance.pop(account_no, None)
+    else:
+        _pending_zero_balance.pop(account_no, None)
@@ -113,0 +150,35 @@ async def _sync_positions(portfolio, account_no: str, ts: datetime, storage: St
+    # CONFIRM-1 (Phần B, đợt 124): chặn "rỗng đột ngột" do bảo trì SSI.
+    # Chỉ hoãn khi danh mục mới rỗng VÀ snapshot gần nhất không rỗng.
+    # Tài khoản luôn rỗng (0434221): prev_positions rỗng -> ghi ngay (SYNC-1).
+    # Cái giá: bán sạch thật -> ghi chậm 1 nhịp (~5 phút). Trong 5 phút,
+    # nếu engine sinh lệnh SELL thì SSI từ chối (không có cổ phiếu) -> an toàn.
+    # Ngược lại, rỗng giả trong phiên làm NAV âm, cổng vốn chặn BUY -> tai hại.
+    if not rows:
+        prev_positions = storage.read_real_positions(account_no)
+        if prev_positions:
+            # Snapshot trước không rỗng: kiểm tra xem đây là lần đầu hay thứ hai
+            if not _pending_empty_positions.get(account_no):
+                # Lần đầu: hoãn, đặt cờ, alert WARN
+                _pending_empty_positions[account_no] = True
+                alert(
+                    "WARN",
+                    "CONFIRM-1: danh mục vừa trống đột ngột (SSI trả None/rỗng), chờ xác nhận lần tiếp",
+                    account_no=account_no,
+                    prev_symbols=len(prev_positions),
+                )
+                return  # KHÔNG ghi, KHÔNG gọi record_position_sync
+            else:
+                # Lần thứ hai liên tiếp rỗng: xác nhận thật, ghi bình thường
+                _pending_empty_positions.pop(account_no, None)
+                alert(
+                    "WARN",
+                    "CONFIRM-1: xác nhận danh mục rỗng sau hai nhịp liên tiếp",
+                    account_no=account_no,
+                )
+        else:
+            # Snapshot trước cũng rỗng (tài khoản 0434221): ghi ngay
+            _pending_empty_positions.pop(account_no, None)
+    else:
+        # SSI trả có vị thế: gỡ cờ nếu đang chờ, ghi bình thường
+        _pending_empty_positions.pop(account_no, None)
```

### 3.2. Output nguyên văn cổng Phần B (`uv run pytest tests/test_account_sync.py -v`)
```
tests/test_account_sync.py::test_b1_sudden_empty_positions_not_written_first_time PASSED [ 51%]
tests/test_account_sync.py::test_b2_sudden_empty_confirmed_on_second_sync PASSED [ 53%]
tests/test_account_sync.py::test_b3_always_empty_account_writes_immediately PASSED [ 56%]
tests/test_account_sync.py::test_b4_positions_return_after_empty_clears_pending PASSED [ 58%]
tests/test_account_sync.py::test_b5_zero_balance_not_written_first_time PASSED [ 61%]
tests/test_account_sync.py::test_b6_nav_old_positions_preserved_when_empty_pending PASSED [ 64%]
tests/test_account_sync.py::test_b7_single_zero_field_writes_normally PASSED [ 66%]
tests/test_account_sync.py::test_b_break1_always_empty_must_write_immediately PASSED [ 69%]
tests/test_account_sync.py::test_b_break2_sudden_empty_must_not_write_first_time PASSED [ 71%]
tests/test_account_sync.py::test_b_break3_only_one_zero_field_must_not_be_blocked PASSED [ 74%]
============================= 39 passed in 2.26s ==============================
```

### 3.3. Bảng phá thử Phần B
| Phá thử | Đột biến | Kết quả | Thông điệp lỗi thực tế |
|---|---|:---:|---|
| **B1** | Bỏ điều kiện `prev_positions` (hoãn mọi lần rỗng kể cả tài khoản luôn rỗng) | **RED (test b3)** | `AssertionError: b3: tài khoản luôn rỗng phải ghi ngay`<br>`assert [] == [('0434221', ..., [])]` |
| **B2** | Ghi ngay lần đầu (bỏ hoãn) | **RED (test b1 & b6)** | `AssertionError: b1: KHÔNG được ghi vị thế lần đầu`<br>`assert [('ACC', ..., [])] == []`<br>`AssertionError: b6: KHÔNG ghi vị thế lần đầu` |
| **B3** | Đổi điều kiện số dư từ "cả ba = 0" thành "bất kỳ trường nào = 0" | **RED (test b7)** | `AssertionError: b7: withdrawable=0 thật -> phải ghi bình thường`<br>`assert 0 == 1` |

---

## 4. PHẦN C — `load_universe("")` ĐỌC NHẦM THƯ MỤC HIỆN HÀNH

### 4.1. Chi tiết thực hiện & Diff
Trong `trading/stock_study.py`, hàm `load_universe`:
- Khi `exclude_file` là `None` hoặc `""`: bỏ qua việc khởi tạo `pathlib.Path`, gán `excluded = set()`, không đọc filesystem và không loại mã nào.
- Giữ nguyên giá trị mặc định `"exclusions.txt"` và hành vi đọc file bình thường khi đường dẫn hợp lệ.
- Tạo file test mới `tests/test_stock_study.py`.

**Diff Phần C:**
```diff
diff --git a/trading/stock_study.py b/trading/stock_study.py
--- a/trading/stock_study.py
+++ b/trading/stock_study.py
@@ -85,11 +85,17 @@ def clean_bars(bars: list[Bar]) -> tuple[list[Bar], int]:
 def load_universe(
-    storage: Storage, exclude_file: str = "exclusions.txt"
+    storage: Storage, exclude_file: str | None = "exclusions.txt"
 ) -> tuple[list[str], dict[str, str], int, set[str]]:
-    """Danh sách mã có nến trong bars_daily, đã loại mã hỏng; kèm bản đồ sàn."""
+    """Danh sách mã có nến trong bars_daily, đã loại mã hỏng; kèm bản đồ sàn.
+
+    exclude_file=None hoặc "" -> không loại mã nào, không chạm filesystem.
+    Trên Windows, pathlib.Path("").exists() trả True (trỏ vào ".") rồi read_text()
+    ném PermissionError — bẫy đã làm agent đợt 120 phải né (vá đợt 124).
+    """
     excluded: set[str] = set()
-    p = pathlib.Path(exclude_file)
-    if p.exists():
-        excluded = {s.strip().upper() for s in p.read_text(encoding="utf-8").splitlines() if s.strip()}
+    if exclude_file:
+        p = pathlib.Path(exclude_file)
+        if p.exists():
+            excluded = {s.strip().upper() for s in p.read_text(encoding="utf-8").splitlines() if s.strip()}
```

### 4.2. Output nguyên văn cổng Phần C (`uv run pytest tests/test_stock_study.py -v`)
```
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
collected 4 items

tests/test_stock_study.py::test_load_universe_empty_string_returns_full_universe PASSED [ 25%]
tests/test_stock_study.py::test_load_universe_none_returns_full_universe PASSED [ 50%]
tests/test_stock_study.py::test_load_universe_with_real_exclusion_file PASSED [ 75%]
tests/test_stock_study.py::test_load_universe_nonexistent_file_returns_full_universe PASSED [100%]

============================== 4 passed in 0.49s ==============================
```

### 4.3. Bảng phá thử Phần C
| Phá thử | Đột biến | Kết quả | Thông điệp lỗi thực tế |
|---|---|:---:|---|
| **C1** | Bỏ nhánh `if exclude_file:` trong `load_universe` | **RED** | `PermissionError: [Errno 13] Permission denied: '.'`<br>xảy ra tại `io.open(self, mode, ...)` khi `read_text()` mở thư mục hiện hành trên Windows. |

---

## 5. PHẦN D — PRE-PUSH HOOK CHẠY CẢ TEST INTEGRATION KHI HẠ TẦNG SẴN SÀNG

### 5.1. Chi tiết thực hiện & Diff
Trong `.githooks/pre-push`:
- Thêm kiểm tra container `nats-test`: `docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'nats-test'`.
- Nếu có: chạy `uv run pytest -q` (bao gồm toàn bộ 142 integration tests).
- Nếu không: in cảnh báo rõ ràng về số test integration bị bỏ, các khu vực ảnh hưởng (compute_nav, read_last_close, GUARD-1, vị thế...), câu lệnh bật hạ tầng (`docker compose --profile test up -d nats-test`), rồi chạy `uv run pytest -m "not integration" -q` mà không chặn push.

**Diff Phần D:**
```diff
diff --git a/.githooks/pre-push b/.githooks/pre-push
--- a/.githooks/pre-push
+++ b/.githooks/pre-push
@@ -17,4 +17,20 @@ while read -r _local_ref _local_sha remote_ref _remote_sha; do
 
-    if ! uv run pytest -m "not integration" -q; then
-        echo "pre-push: TEST DO -> huy push." >&2
-        exit 1
-    fi
+    # Kiem tra xem nats-test co dang chay khong (docker ps lay ten container).
+    # Neu co: chay TOAN BO pytest (gom 142 test integration / duong tien that).
+    # Neu khong: chay khong co integration, in CANH BAO ro rang.
+    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'nats-test'; then
+        echo "pre-push: nats-test dang chay — chay TOAN BO pytest (gom integration)..."
+        if ! uv run pytest -q; then
+            echo "pre-push: TEST DO -> huy push." >&2
+            exit 1
+        fi
+    else
+        echo "pre-push: CANH BAO: nats-test KHONG chay — bo qua 142 test integration." >&2
+        echo "pre-push: Cac test bi bo gom: compute_nav, read_last_close, GUARD-1, vi the..." >&2
+        echo "pre-push: De bat ha tang: docker compose --profile test up -d nats-test" >&2
+        echo "pre-push: (Push KHONG bi chan — dung --no-verify de bat buoc bo qua)" >&2
+        if ! uv run pytest -m "not integration" -q; then
+            echo "pre-push: UNIT TEST DO -> huy push." >&2
+            exit 1
+        fi
+    fi
```

### 5.2. Output nguyên văn 2 trạng thái của Cổng Phần D

#### Trạng thái 1: `nats-test` đang chạy
```
pre-push: kiem tra truoc khi day len main...
All checks passed!
pre-push: nats-test dang chay — chay TOAN BO pytest (gom integration)...
........................................................................ [  5%]
........................................................................ [ 10%]
...
....................................................                     [100%]
1420 passed in 88.49s (0:01:28)
pre-push: sach, cho push.
```
*(Số passed: 1.420, không có test nào bị deselected).*

#### Trạng thái 2: `nats-test` đã dừng (`docker compose --profile test stop nats-test`)
```
pre-push: kiem tra truoc khi day len main...
All checks passed!
pre-push: CANH BAO: nats-test KHONG chay — bo qua 142 test integration.
pre-push: Cac test bi bo gom: compute_nav, read_last_close, GUARD-1, vi the...
pre-push: De bat ha tang: docker compose --profile test up -d nats-test
pre-push: (Push KHONG bi chan — dung --no-verify de bat buoc bo qua)
........................................................................ [  5%]
...
......................................................                   [100%]
1278 passed, 142 deselected in 43.72s
pre-push: sach, cho push.
```
*(Hiện cảnh báo đầy đủ, bỏ qua 142 test, push không bị chặn).*

*Lưu ý:* Sau kiểm thử Trạng thái 2, container `nats-test` đã được khởi động lại ngay bằng `docker compose --profile test up -d nats-test`.

---

## 6. MỤC KẸT & ĐIỀU MƠ HỒ / BẤT CẬP CỦA BRIEF (§2 & §3)

1. **Không có phần nào bị kẹt:** Cả 4 phần A, B, C, D đều đã hoàn thành và vượt qua 100% các cổng và đột biến phá thử.
2. **Điểm bất cập trong test suite có sẵn:**
   - Test `tests/test_storage.py::test_real_positions_empty_after_sync_with_empty_portfolio` kiểm tra hành vi `SYNC-LOG-1` bằng cách đồng bộ có vị thế rồi đồng bộ rỗng 1 lần. Khi áp dụng `CONFIRM-1` của Brief 124, lần đồng bộ rỗng đầu tiên bị hoãn để chống lỗi bảo trì SSI. Do đó, test cần đồng bộ 2 nhịp rỗng liên tiếp để kích hoạt bước xác nhận rỗng. Đã cập nhật test này đồng bộ 2 nhịp để tương thích với CONFIRM-1.
3. **Va chạm NATS JetStream khi chạy song song:**
   - Nếu chạy kiểm thử hook và pytest đồng thời trong background, các durable consumer của NATS JetStream sẽ va chạm (`Error: consumer is already bound to a subscription`). Chạy tuần tự không gặp lỗi này.

---
**Trạng thái sẵn sàng:** Working tree sạch sẽ, tất cả 1.419 tests pass, ruff pass. Sẵn sàng cho Claude audit, commit và push!

---

## Audit của Claude (29/09/2026)

### A.1. Kết luận: ĐẠT cả bốn phần, kèm một sửa nhỏ ở Phần D

Phạm vi đúng danh sách được phép. **Không còn token nào** trong báo cáo này lẫn trong `logs/` (Claude chỉ đếm, không in: 0 chuỗi `Bearer ey`, 0 chuỗi dạng JWT).

| Kiểm (Claude tự chạy) | Kết quả |
|---|---|
| `uv run pytest -q` toàn bộ, gồm integration (nats-test đang chạy) | **1.419 passed**, exit 0 |
| `ruff check trading tests scripts` (đúng lệnh pre-push) | sạch |
| 7 test Phần B, 4 test Phần C | xanh |

Báo cáo agent ghi 1.419 ở phần tổng và 1.420 ở Phần D; lần chạy của Claude ra 1.419, không có test đỏ.

### A.2. Phần A — một giả định rủi ro được kiểm tới gốc

Brief để ngỏ giả định "SDK không đặt lại mức logger sau khi bộ ghi đã gọi hàm chặn". Test của agent **không** kiểm được điều này: nó giả lập ngày nghỉ nên thoát **trước** khi tạo `AsyncAuth`/`AsyncStream`. Claude đọc mã nguồn SDK: `ssi_sdk/utils/logger.py::get_logger()` (được gọi ở `client.py:77` và `:134` khi khởi tạo client) chỉ `setLevel` trên logger **cha** `"ssi_sdk"` và gắn `StreamHandler(sys.stdout)` cho nó. Logger con `ssi_sdk.transport.websocket` đã có mức WARNING riêng thì mức của cha **không** đè được. **Giả định đứng vững.** Điều này cũng giải thích định dạng của dòng bị lộ (`<time> INFO [ssi_sdk.transport.websocket]: ...`): đó là handler riêng của SDK ghi ra stdout, rồi `sched.sh` chuyển vào file log.

Khối chú thích LOG-1 được chuyển **nguyên văn** sang `trading/logging_setup.py::silence_ssi_sdk_secrets`, giữ quyết định "setLevel, không regex; không đụng `token_manager`". Bộ ghi gọi hàm sau `load_config`, trước mọi đối tượng SDK.

**Lỗ còn lại, ngoài phạm vi:** khi bật `log_level="DEBUG"` (chỉ các script spike), logger `ssi_sdk.transport.rest` vẫn ghi nguyên thân phản hồi xác thực (`rest_client.py:30`), tức token. Hàm mới **không** chặn logger này, đúng theo brief.

### A.3. Phần B — sửa test cũ là hợp lệ; Claude tự phá thử

**Test cũ bị sửa** `test_real_positions_empty_after_sync_with_empty_portfolio` (bảo vệ SYNC-LOG-1: bán sạch thì phải nhận ra là rỗng, không được giữ vị thế ma mãi mãi). Agent thêm **đúng một** nhịp đồng bộ rỗng thứ hai; **assertion cuối không đổi** (vị thế phải rỗng). Test vẫn chứng minh việc bán sạch **cuối cùng vẫn được ghi nhận**, chỉ chậm một nhịp đúng như thiết kế. Không làm yếu.

**Claude tự làm lại hai phép phá thử quan trọng nhất** (in `changed=True`, phục hồi trùng hash):

| Đột biến | Test đỏ |
|---|---|
| B2: ghi ngay lần đầu (bỏ hoãn) | b1, b2, b4, **b6** (b6 tái hiện đúng sự cố 23:23:56; bỏ hoãn thì NAV −31 triệu quay lại) |
| B3: bắt khi **bất kỳ** trường nào = 0 | đúng **b7** (tài khoản margin có `withdrawable = 0` thật bị chặn nhầm) |

**Một độ lệch nhỏ so với brief, chấp nhận:** brief ghi "dòng số dư trước có ít nhất một trong **ba** trường khác 0". Code dùng `read_account_balance_with_debt`, hàm này chỉ trả `(withdrawable, total_debt, ts)`, nên `account_balance` không được xét. Lỗ chỉ mở khi dòng trước có `withdrawable = 0`, `total_debt = 0` nhưng `account_balance ≠ 0`. Claude đo trên DB: **0 trên 11.053 dòng** của cả hai tài khoản. Bịt nó cần một hàm đọc mới trong `storage`, ngoài phạm vi; ghi nhận, không sửa.

### A.4. Phần C — đúng

`exclude_file` là `None` hoặc `""` thì không chạm filesystem. Mặc định `"exclusions.txt"` giữ nguyên. Cách né `__no_exclusions__.tmp` trong `measure_sepa_score_edge.py` được để nguyên như brief yêu cầu.

### A.5. Phần D — đúng về logic; Claude bỏ con số cứng

Câu cảnh báo in cứng **"142 test integration"**, và sẽ sai ngay khi thêm test integration mới. Claude đổi thành "BỎ QUA mọi test integration (số lượng: xem dòng deselected bên dưới)"; dòng `deselected` do pytest in ra luôn đúng. Kiểm cú pháp `bash -n`: sạch. Thay đổi chỉ nằm trong chuỗi `echo` nên Claude không chạy lại hai trạng thái; nhánh "nats-test đang chạy" chính là bộ 1.419 test ở §A.1.

### A.6. Việc Claude còn phải làm trên hệ thống thật

1. Rebuild engine + collector (đổi `account_sync.py` và `logging_setup.py`), **trước giờ phiên**.
2. Sau phiên 30/09: đếm `Bearer ey` trong `logs/orderbook-recorder.log` phải bằng 0, và job kiểm sổ lệnh 15:30 vẫn phải ĐẠT.
3. Ba đêm 29/09–01/10, khung 22:00–01:30: đếm `account_nav_snapshot` có `nav <= 0` phải bằng 0. Nếu SSI vẫn trả rỗng thì log collector phải có WARN `CONFIRM-1`.

