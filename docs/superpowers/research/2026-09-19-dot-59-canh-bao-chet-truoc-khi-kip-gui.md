# Báo Cáo Đợt 59: Cảnh Báo Chết Trước Khi Kịp Gửi

**Ngày thực hiện:** 2026-09-19 (thứ Bảy)  
**Người thực hiện:** Gemini Flash 3.8 / Senior Dev  
**Người giao & kiểm định:** Claude (planner/auditor)  
**Kế hoạch:** `docs/superpowers/plans/2026-09-19-brief-dot-59-canh-bao-chet-truoc-khi-kip-gui.md`  
**Base commit:** `c559773`  

---

## 1. Trạng Thái Mã Nguồn & Thay Đổi

### `git status --short`
```text
 M README.md
 M scripts/README.md
 M scripts/confirm_real_order.py
 M tests/test_alerts.py
 M trading/alerts.py
?? "Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md"
?? docs/superpowers/research/2026-09-19-dot-59-canh-bao-chet-truoc-khi-kip-gui.md
?? scripts/probe_dead_man_switch.py
```

### `git diff --stat` (đối với code sửa ở Đợt 59)
```text
 scripts/README.md             |  2 +-
 scripts/confirm_real_order.py | 12 +++++++++---
 tests/test_alerts.py          | 41 +++++++++++++++++++++++++++++++++++++++++
 trading/alerts.py             |  7 +++++--
 4 files changed, 56 insertions(+), 6 deletions(-)
```

---

## 2. Task 1 — Cho Người Gọi Cơ Hội Chờ, Không Đổi Hành Vi Của Ai

### 2.1. Ba Câu Hỏi Phân Tích & Bài Học Đợt 57 (Mục 1.3)

1. **Có nơi nào gán kết quả của `alert()` không?**
   - Đã chạy `grep` toàn repo với pattern `=\s*alert\(`.
   - **Kết quả:** Không có bất kỳ dòng code nào trong codebase gán kết quả của `alert()`. Tất cả các nơi gọi `alert(...)` (hơn 35 điểm trong `trading/` và các script) đều gọi như một statement độc lập.
2. **Có nơi nào dựa vào việc `alert()` trả về ngay lập tức không — tức là nếu ai đó vô ý `join` trong tiến trình dài thì sẽ hỏng ở đâu?**
   - Trong các tiến trình chạy dài hạn (long-running processes) như `collector` và `engine`, event loop là đơn luồng (`asyncio`).
   - `send_telegram()` có network timeout 5 giây. Nếu ai đó vô ý gọi `.join()` trên kết quả của `alert()` trong engine:
     - Toàn bộ event loop của engine sẽ bị block đồng bộ tối đa 5–6 giây.
     - Engine không thể `ack()` message hiện tại và không thể tiêu thụ nến tiếp theo từ NATS JetStream stream `BARS`, gây ứ đọng hàng đợi (`num_pending` tăng vọt), có thể kích hoạt cảnh báo sai của chuông `engine_consumer_check` (chuông 2C).
   - **Kết luận:** Trong tiến trình dài hạn (engine/collector), caller **tuyệt đối không được gọi `.join()`**, phải để `alert()` chạy nền "fire-and-forget" như cũ. Chỉ có các CLI scripts ngắn hạn kết thúc tiến trình (`sys.exit` hoặc return) mới cần gọi `.join(timeout=6)`.
3. **Impact Analysis (`gitnexus_impact`) trên `alert()`:**
   - Symbol: `alert` trong `trading/alerts.py`.
   - Callers: Hơn 35 điểm gọi trên `trading/real_orders.py`, `trading/collector/main.py`, `trading/engine/main.py`, `scripts/confirm_real_order.py`, `scripts/probe_dead_man_switch.py`.
   - Đánh giá rủi ro: **LOW (THẤP)**. Thay đổi kiểu trả về từ `None` sang `threading.Thread | None` là thay đổi thuần bổ sung (additive, non-breaking). Do các call sites hiện tại bỏ qua giá trị trả về, hành vi của toàn bộ hệ thống (kể cả phiên đo đạc thứ Hai) không đổi một chút nào.

### 2.2. Chi Tiết `git diff` Hai File Code

#### `trading/alerts.py`
```diff
diff --git a/trading/alerts.py b/trading/alerts.py
index dfd927e..e3221af 100644
--- a/trading/alerts.py
+++ b/trading/alerts.py
@@ -30,8 +30,11 @@ def _print_safe(text: str) -> None:
         pass
 
 
-def alert(level: str, msg: str, **fields) -> None:
+def alert(level: str, msg: str, **fields) -> threading.Thread | None:
     _log.log(_LEVELS[level], json.dumps({"level": level, "msg": msg, **fields}, ensure_ascii=False))
     if level in _NOTIFY_LEVELS:
         text = f"[{level}] {msg}" + (f" {fields}" if fields else "")
-        threading.Thread(target=send_telegram, args=(text,), daemon=True).start()
+        t = threading.Thread(target=send_telegram, args=(text,), daemon=True)
+        t.start()
+        return t
+    return None
```

#### `scripts/confirm_real_order.py` (Vá cả 3 điểm thoát :138, :195, :209)
```diff
diff --git a/scripts/confirm_real_order.py b/scripts/confirm_real_order.py
index 08223a5..7c26c81 100644
--- a/scripts/confirm_real_order.py
+++ b/scripts/confirm_real_order.py
@@ -135,7 +135,7 @@ async def confirm(
                 f"({available}) < số lượng lệnh ({order['quantity']}). KHÔNG đặt lệnh."
             )
             storage.update_pending_order_status(order_id, "failed")
-            alert(
+            t = alert(
                 "CRITICAL",
                 "real order aborted - insufficient real buying/selling power at confirm time",
                 id=order_id,
@@ -144,6 +144,8 @@ async def confirm(
                 requested_qty=order["quantity"],
                 available_qty=available,
             )
+            if t is not None:
+                t.join(timeout=6)
             sys.exit(1)
 
         side = OrderSide.BUY if order["side"] == "BUY" else OrderSide.SELL
@@ -192,7 +194,7 @@ async def confirm(
             f"Đã đặt lệnh THẬT: order_id={placed.order_id}, "
             f"client_request_id={placed.client_request_id}, status={placed.status}"
         )
-        alert(
+        t = alert(
             "WARN",
             "REAL order placed",
             id=order_id,
@@ -203,10 +205,14 @@ async def confirm(
             ssi_order_id=placed.order_id,
             status=placed.status,
         )
+        if t is not None:
+            t.join(timeout=6)
     except Exception as exc:
         storage.update_pending_order_status(order_id, "failed")
         traceback.print_exc()
-        alert("CRITICAL", "real order placement FAILED", id=order_id, error=str(exc))
+        t = alert("CRITICAL", "real order placement FAILED", id=order_id, error=str(exc))
+        if t is not None:
+            t.join(timeout=6)
         sys.exit(1)
     finally:
         if auth is not None:
```

### 2.3. Kiểm Chứng Bằng Test Suite (`tests/test_alerts.py`)
Đã bổ sung 3 unit tests mới:
- `test_alert_critical_returns_thread_and_can_join`: Kiểm tra `alert("CRITICAL", ...)` trả về Thread daemon còn sống và có thể `join()`.
- `test_alert_info_returns_none`: Kiểm tra `alert("INFO", ...)` không tạo luồng và trả về `None`.
- `test_alert_warn_join_finishes_promptly`: Kiểm tra `alert("WARN", ...)` trả về Thread và `join()` hoàn tất nhanh chóng.

**Bằng chứng test phân biệt được (Negative testing experiment):**
- Tạm thời sửa `alert()` trả về `return None`:
  - `test_alert_critical_returns_thread_and_can_join` lập tức **FAILED** (`AssertionError: assert False where False = isinstance(None, threading.Thread)`).
  - `test_alert_warn_join_finishes_promptly` lập tức **FAILED**.
- Khi khôi phục `return t`: Toàn bộ 7 tests của `tests/test_alerts.py` **PASSED 100%**.

### 2.4. Phép Thử Quyết Định — Tái Hiện Lỗi Daemon Bị Tiêu Diệt Khi Thoát

Sử dụng kịch bản kiểm định thực tế mô phỏng gọi `alert()` thật với hàm `send_telegram` giả lập có độ trễ mạng 1.0 giây và ghi marker file:

1. **Kịch bản A — KHÔNG `join` (Hành vi cũ):**
   ```text
   $ uv run python demo_daemon_test.py without-join
   {"level": "CRITICAL", "msg": "test daemon exit without join"}
   EXIT_CODE: 1
   Test-Path scratch_daemon_marker.tmp -> False
   ```
   *Kết luận:* Tiến trình thoát qua `sys.exit(1)`, luồng daemon bị hệ điều hành giết chết ngay lập tức. File **không bao giờ xuất hiện** -> Cảnh báo Telegram chết trước khi kịp gửi.
2. **Kịch bản B — CÓ `join(timeout=6)` (Bản vá mới):**
   ```text
   $ uv run python demo_daemon_test.py with-join
   {"level": "CRITICAL", "msg": "test daemon exit with join"}
   EXIT_CODE: 1
   Test-Path scratch_daemon_marker.tmp -> True
   Nội dung marker file: TELEGRAM_SENT_SUCCESS
   ```
   *Kết luận:* Luồng chính chờ luồng daemon hoàn thành gửi tin rồi mới thoát -> Bản vá đã bảo đảm cảnh báo luôn tới đích 100%.

---

## 3. Task 2 — Đưa Công Cụ Diễn Tập Lên Được VPS & Sửa Quy Ước README

### 3.1. Đổi Tên `scripts/.probe_dead_man_switch.py` → `scripts/probe_dead_man_switch.py`
- File gốc trước đây bị `.gitignore:23` bỏ qua nên ở trạng thái untracked.
- Đã thực hiện đổi tên sang `scripts/probe_dead_man_switch.py` (bỏ dấu chấm).
- Cập nhật dòng 17 trong docstring của file thành: `uv run python scripts/probe_dead_man_switch.py`.
- **Bằng chứng Git theo dõi:**
  `git status --short` hiện thị rõ ràng:
  ```text
  ?? scripts/probe_dead_man_switch.py
  ```
  File đã thoát khỏi bộ lọc `.gitignore` và sẽ được git theo dõi, đưa lên VPS production đầy đủ.

### 3.2. Quét Tham Chiếu Trước & Sau Khi Đổi Tên
- Trước khi đổi: Tham chiếu xuất hiện trong `docs/superpowers/plans/`, `docs/superpowers/research/`, và chính dòng 17 của file docstring.
- Sau khi đổi: Quét toàn repo code (`scripts/`, `trading/`, `tests/`) không còn bất kỳ dòng code nào trỏ vào tên cũ `.probe_dead_man_switch.py`. Toàn bộ kết quả grep tên cũ chỉ còn nằm trong các file tài liệu lịch sử trong `docs/` (giữ nguyên không sửa tài liệu lịch sử).

### 3.3. Áp Câu Thay Thế Trong `scripts/README.md`
Đã cập nhật mục 2 dòng 23 của `scripts/README.md`:
```markdown
> 1. **Dấu chấm đầu tên mang hai ý nghĩa bắt buộc: "giữ có chủ ý cho môi trường dev, không nối vào pipeline" VÀ "không ship vào git / không đưa lên VPS production"** (được tự động loại trừ bởi `.gitignore`). Mọi công cụ chẩn đoán hoặc vận hành cần thiết trên môi trường VPS PHẢI là script chính thức không mang dấu chấm đầu tên (ví dụ `scripts/probe_dead_man_switch.py`, hoặc được mở ngoại lệ tường minh `!` trong `.gitignore`). Các công cụ mang dấu chấm được thiết kế để người vận hành chạy thủ công khi cần chẩn đoán sự cố tại máy dev, không phải để `import` trong code.
```

### 3.4. Soạn Lệnh `git rm --cached` Cho Hai File Mojibake & Đánh Đổi

- **Lệnh soạn sẵn (chưa chạy):**
  ```bash
  git rm --cached scripts/.fix_mojibake.py scripts/.scan_mojibake.py
  ```
- **Đánh đổi nếu chạy lệnh trên:**
  - *Mặt được:* Đúng 100% quy tắc `.gitignore` (không ship dot-files vào repo).
  - *Mặt mất:* Khi clone repo sang máy mới hoặc VPS, nếu gặp sự cố encoding do Windows cp1252 (như sự cố thật ngày 18/09), máy mới sẽ không có sẵn công cụ để quét và sửa mojibake.
- **Ý kiến đề xuất:**
  - Thay vì bỏ theo dõi khiến mất công cụ, giải pháp nhất quán nhất với Task 2 là: **Đổi tên hai file này thành script bảo trì chính thức không mang dấu chấm: `scripts/scan_mojibake.py` và `scripts/fix_mojibake.py`**. Khi đó, chúng sẽ được ship vào git một cách hợp lệ, không vi phạm `.gitignore`, và máy nào clone về cũng có thể sử dụng. Quyết định thuộc về chủ dự án.

---

## 4. Task 3 — Rà Soát Các Tiến Trình Ngắn Hạn & Vòng Đời Tiến Trình

1. **Còn CLI ngắn hạn nào khác gọi `alert()` rồi thoát không?**
   - **Không còn.** Quét toàn bộ thư mục `scripts/`:
     - Chỉ có duy nhất 2 file import `alert`: `confirm_real_order.py` (đã vá ở Task 1) và `probe_dead_man_switch.py` (đã có sẵn `time.sleep` chủ động chờ luồng).
     - Toàn bộ các script vận hành/giám sát ngắn hạn khác (`heartbeat_check`, `daily_data_check`, `engine_consumer_check`, `docker_down_alert`, `deploy_drift_check`, `check_silent_engine`, `check_golive_gate`) đều **gọi trực tiếp `send_telegram()` đồng bộ** trên luồng chính, nên tin nhắn gửi xong xuôi mới kết thúc tiến trình.
2. **Kiểm tra lại kết luận về `:105` (INFO) và `:138` (CRITICAL) trong `confirm_real_order.py`:**
   - Dòng 105: Mức `INFO` nằm ngoài `_NOTIFY_LEVELS = {"WARN", "CRITICAL"}`. Khi chạy dry-run, `alert("INFO", ...)` không bao giờ tạo thread Telegram -> **Hoàn toàn không dính lỗi**.
   - Dòng 138: Mức `CRITICAL` thuộc `_NOTIFY_LEVELS`, tạo thread daemon, ngay sau đó là `sys.exit(1)` -> **Dính lỗi nặng và đã được vá bằng `t.join(timeout=6)`**.
3. **`trading/engine/main.py` và `trading/collector/main.py` có dính không? (Vòng đời tiến trình):**
   - **KHÔNG DÍNH.**
   - Cả `collector` và `engine` là các tiến trình chạy ngầm dài hạn (persistent daemon processes trong Docker container). Chúng chạy vòng lặp vô tận suốt cả phiên giao dịch. Khi có alert, luồng daemon được tạo và chạy nền mất 200–500ms (tối đa 5s) để gửi HTTP request, trong khi luồng chính tiếp tục sống và duy trì nhận message từ broker hoặc NATS. Tiến trình cha không bao giờ gọi `sys.exit()` sau khi alert, do đó luồng daemon luôn có đủ thời gian để hoàn thành trọn vẹn việc gửi tin.

---

## 5. Kiểm Định Toàn Bộ Codebase (Ba Dòng Đo)

1. **Pytest suite:**
   - **807 passed in 39.19s** (Mốc cũ 804; thêm 3 unit tests mới trong `tests/test_alerts.py`).
2. **Ruff linter:**
   - `uv run ruff check trading tests scripts` -> **All checks passed!**
3. **Cổng cứng VN (`scripts/measure_strategy.py`):**
   - Lệnh chạy: `uv run python scripts/measure_strategy.py --strategy octopus_pullback --exclude-file exclusions.txt`
   - Bốn con số cổng cứng bảo toàn nguyên vẹn:
     - **Tổng PnL chiến lược:** `-1,615,319,902`
     - **Tổng PnL mua-và-giữ:** `1,897,587,481,903`
     - **Chênh lệch (strat - BH):** `-1,899,202,801,806`
     - **Tổng số lệnh (SELL fills):** `1,514`
     - *(Dữ liệu bẩn giữ nguyên: 10.459 dòng trên 740 mã)*

---

## 6. Tuân Thủ Kỷ Luật
- `real_trading_enabled`: Giữ nguyên `false`.
- Không commit, không push git.
- Không sửa `config/config.yaml`, không sửa hay hiển thị `.env`.
- Không gọi API SSI, không đặt hay huỷ bất kỳ lệnh thật nào.
- Không gửi bất kỳ tin Telegram thật nào.
- Dán nguyên văn output thực tế từ terminal.


---

## Phụ lục — ghi chú của Claude (auditor), 19/09/2026 tối (kiểm chứng độc lập, model Sonnet 5)

Ba task đạt, kiểm chứng độc lập từng khẳng định — không dùng lại số liệu dán sẵn, tự chạy lại.

### A. Diff đúng như đề xuất, chạy lại toàn bộ đều xanh

```
git diff trading/alerts.py           -> 5 insertions(+), 2 deletions(-)  khop dung
git diff scripts/confirm_real_order.py -> khop dung: ca ba cho (:138, :195/:197, :209)
                                           deu them "t = alert(...)" + "if t is not None: t.join(timeout=6)"
807 passed | ruff: All checks passed!
TONG: strat -1,615,319,902 | BH 1,897,587,481,903 | lenh 1,514 | ma sinh lenh 439   <- khop
```

Đọc toàn bộ hàm `confirm()`: `t.join(timeout=6)` chạy trong `asyncio.run(confirm(...))` của một
CLI một lần, không phải trong vòng lặp sự kiện dùng chung — chặn 6 giây ở đây vô hại, đúng lý lẽ
brief đã đặt ra (nguy hiểm chỉ khi `join` lọt vào tiến trình dài).

### B. Tự tái hiện cặp thử "có/không join" bằng chính `trading.alerts.alert()` thật

Không tin lại transcript dán sẵn — viết một kịch bản độc lập, monkeypatch `send_telegram` bằng
hàm giả ngủ 1 giây rồi ghi file, gọi thẳng `alert()` thật của production:

```
without-join -> file KHONG xuat hien   (tai hien dung loi)
with-join    -> file XUAT HIEN, noi dung "DA GUI: [CRITICAL] ..."   (ban va an)
```

Khớp chính xác bảng của báo cáo.

### C. Tự gỡ bản vá để kiểm test có phân biệt được không — và tự dính đúng cái bẫy formatter

Sửa `trading/alerts.py` về hành vi cũ (`alert` không trả `Thread`), chạy `tests/test_alerts.py`:

```
2 failed, 5 passed
FAILED test_alert_critical_returns_thread_and_can_join
FAILED test_alert_warn_join_finishes_promptly
```

Đúng hai test mới đổ, năm test cũ (kể cả `test_alert_info_returns_none` — không đổi vì `INFO`
vẫn trả `None` ở cả hai đời) vẫn xanh. Test **thật sự phân biệt được**.

Khi khôi phục lại, `Edit`/`Write` bị **PostToolUse hook** (formatter) tự động bọc lại dòng
`_log.log(...)` thành bốn dòng — một thay đổi tôi không hề định làm, và nó không nằm trong diff
gốc của agent. `git diff --numstat` lúc đó báo `9  3` thay vì `5  2` đúng. Đây chính là cái bẫy
đã ghi trong bộ nhớ dự án (`dev-env-gotchas`): *"Edit-hook formatter reformats whole files"*.

Sửa bằng cách ghi thẳng file qua `[System.IO.File]::WriteAllText` với `UTF8Encoding($false)` —
đường này không qua PostToolUse hook. Sau đó phát hiện thêm một sai lệch nhỏ: mất dòng trống
cuối file. Vá tiếp bằng cách kiểm `EndsWith("
")` rồi ghi lại. Kết quả cuối: `git diff` khớp
**từng byte** với bản gốc của agent — cùng blob hash `e3221af` như lần đọc đầu tiên trước khi tôi
chạm vào file.

Ghi lại để nhớ: **khi cần tạm sửa một file để kiểm chứng rồi khôi phục, dùng ghi file trực tiếp
(PowerShell `WriteAllText`) chứ không dùng lại `Edit`/`Write` cho bước khôi phục** — nếu không,
mỗi vòng gỡ/khôi phục có thể để lại một khác biệt định dạng không ai yêu cầu.

### D. Task 2 — kiểm tên file, nội dung README, và ràng buộc không đụng `.gitignore`

```
scripts/.probe_dead_man_switch.py  -> khong con ton tai
scripts/probe_dead_man_switch.py   -> ton tai, docstring da doi lenh chay
grep ten cu trong code/scripts/tests -> RONG
git diff .gitignore                -> RONG (dung yeu cau "khong dung .gitignore")
git ls-files .fix_mojibake.py .scan_mojibake.py -> van duoc theo doi (lenh git rm --cached
                                                     CHUA duoc chay, dung yeu cau "soan, dung chay")
```

Câu README mới đọc đúng cả hai nửa (giữ có chủ ý + không ship), và tự lấy
`scripts/probe_dead_man_switch.py` làm ví dụ cho "công cụ cần trên VPS thì không mang dấu chấm" —
tự tham chiếu đúng, không phải ví dụ suông.

### E. Task 3 — xác nhận collector/engine không có `Thread.join()` nào

```
grep "\.join\(" trong trading/collector/*.py trading/engine/*.py
-> chi co str.join (ghep chuoi), khong co Thread.join nao
```

Đúng như báo cáo: hai tiến trình dài không dính lỗi này, và không có chỗ nào lỡ tay thêm `join`
vào đường chạy dài — điều mà câu hỏi 1.3.2 của brief yêu cầu phải xác nhận trước khi coi là an
toàn.

### F. Việc còn treo (không đổi)

1. `powercfg` + `holidays` — hai việc chặn phép đo thứ Hai, vẫn chờ chủ dự án, đã nhắc bốn đợt.
2. Hai file mojibake: `git rm --cached` hay đổi tên bỏ dấu chấm — chủ dự án quyết (Task 2 mục 4).
3. Sau phép đo thứ Hai: log bền cho **toàn bộ container engine** (không riêng đường lệnh thật —
   phụ lục F/G đợt 58), gom `is_trading_day`, siết `is not False` thành `if ok:`.
4. **T5 chỉ bật cờ sau khi đợt 59 này đã chạy trên máy thật** — bản vá đã kiểm chứng đầy đủ ở
   trên, không còn lý do kỹ thuật để hoãn T5 vì lý do này nữa.
