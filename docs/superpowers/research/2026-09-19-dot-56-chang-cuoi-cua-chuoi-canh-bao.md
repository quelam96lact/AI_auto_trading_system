# Báo cáo Đợt 56 — Chặng cuối của chuỗi cảnh báo

Ngày thực hiện: 19/09/2026 (thứ Bảy).
Base: `ebe110c` (main).
Người thực thi: Gemini Flash 3.8.
Người nhận: Claude (planner/auditor) & Chủ dự án.

---

## 1. Trạng thái Git & Diff Stat

### 1.1 `git status --short`
```text
 M README.md
 M scripts/daily_data_check.py
 M scripts/stream_health_check.py
 M tests/test_calendar.py
 M tests/test_telegram.py
 M trading/calendar_vn.py
 M trading/telegram.py
?? "Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md"
```
*(Ghi chú: README.md giữ nguyên 188 dòng đổi chờ chủ dự án duyệt; không commit, không push).*

### 1.2 `git diff --stat`
```text
 README.md                      | 188 +++++++++++++++++++++++++++--------------
 scripts/daily_data_check.py    |   7 +-
 scripts/stream_health_check.py |   5 +-
 tests/test_calendar.py         |  25 +++++-
 tests/test_telegram.py         |  66 ++++++++++++++-
 trading/calendar_vn.py         |   5 ++
 trading/telegram.py            |  40 ++++++++-
 7 files changed, 257 insertions(+), 79 deletions(-)
```

---

## 2. Task 1 — `send_telegram` phải nói được "tôi không gửi được"

### 2.1 Blast Radius / `gitnexus_impact` của `send_telegram`
Kết quả lệnh `npx gitnexus impact send_telegram --repo AI_auto_trading_system --direction upstream`:
```json
{
  "target": {
    "id": "Function:trading/telegram.py:send_telegram",
    "name": "send_telegram",
    "type": "Function",
    "filePath": "trading/telegram.py"
  },
  "direction": "upstream",
  "impactedCount": 8,
  "risk": "LOW",
  "summary": {
    "direct": 3,
    "processes_affected": 2,
    "modules_affected": 2
  }
}
```
**Xác nhận tương thích ngược:** Đã đọc toàn bộ 8 call site (`trading/alerts.py`, `scripts/daily_data_check.py`, `scripts/engine_consumer_check.py`, `scripts/heartbeat_check.py`, `scripts/docker_down_alert.py`, `scripts/deploy_drift_check.py`, `scripts/check_silent_engine.py`, `scripts/.probe_dead_man_switch.py`). Không có bất kỳ call site nào dùng giá trị trả về trước đây, nên đổi signature từ `send_telegram(text: str) -> None` sang `send_telegram(text: str) -> bool` hoàn toàn tương thích ngược 100%.

### 2.2 `git diff trading/telegram.py`
```diff
diff --git a/trading/telegram.py b/trading/telegram.py
index c0e0cf7..319cc87 100644
--- a/trading/telegram.py
+++ b/trading/telegram.py
@@ -1,19 +1,51 @@
 import json
+import logging
 import os
 import urllib.request
+from typing import Any
+
+logger = logging.getLogger(__name__)
 
 _API_URL = "https://api.telegram.org/bot{token}/sendMessage"
 
 
-def send_telegram(text: str) -> None:
+def send_telegram(text: str) -> bool:
+    """Gửi tin nhắn cảnh báo tới Telegram bot.
+
+    FEE-ALARM-2: Chuông báo chết câm còn tệ hơn không có chuông báo.
+    Hàm này KHÔNG BAO GIỜ ném exception ra ngoài caller:
+    - Trả True nếu Telegram API xác nhận đã nhận (HTTP 200 và response JSON có 'ok': True).
+    - Trả False nếu thiếu cấu hình, lỗi mạng, HTTP error, hoặc Telegram trả 'ok': False.
+      Mọi trường hợp thất bại đều được ghi log mức WARNING kèm lý do chi tiết.
+    """
     token = os.environ.get("TELEGRAM_BOT_TOKEN")
     chat_id = os.environ.get("TELEGRAM_CHAT_ID")
-    if not token or not chat_id:
-        return
+    missing_vars = []
+    if not token:
+        missing_vars.append("TELEGRAM_BOT_TOKEN")
+    if not chat_id:
+        missing_vars.append("TELEGRAM_CHAT_ID")
+    if missing_vars:
+        logger.warning(
+            "Khong the gui Telegram vi thieu bien moi truong: %s",
+            ", ".join(missing_vars),
+        )
+        return False
+
     data = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
     req = urllib.request.Request(
         _API_URL.format(token=token),
         data=data,
         headers={"Content-Type": "application/json"},
     )
-    urllib.request.urlopen(req, timeout=5)
+    try:
+        with urllib.request.urlopen(req, timeout=5) as resp:
+            raw_body = resp.read()
+            payload: dict[str, Any] = json.loads(raw_body.decode("utf-8"))
+            if payload.get("ok") is True:
+                return True
+            logger.warning("Telegram API tra ve loi: %s", payload)
+            return False
+    except Exception as e:
+        logger.warning("Loi khi gui tin Telegram: %s: %s", type(e).__name__, e)
+        return False
```

### 2.3 Đáp ứng 4 tiêu chí kiểm chứng
1. Thiếu `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`: Không im lặng trả về, ghi `logger.warning(...)` kèm tên biến môi trường bị thiếu, không in secret, trả về `False`, không ném exception.
2. Lỗi kết nối / timeout / HTTP error: Bọc trong `try ... except Exception as e`, ghi `logger.warning(...)`, trả về `False`, không ném exception làm sập script.
3. Đọc response Telegram: Kiểm tra `payload.get("ok") is True`. Nếu `{"ok": false}` -> log warning và trả `False`.
4. Không gọi `alert()` (tránh đệ quy vô hạn), chỉ dùng `logging.getLogger(__name__)`.

### 2.4 Bằng chứng test phân biệt được (Negative Testing)
- **Khi tạm khôi phục hành vi cũ ở nhánh A (`return` trần không log):**
  ```text
  ================================== FAILURES ===================================
  _________________________ test_noop_when_env_not_set __________________________
  >       assert res is False
  E       assert None is False
  ______________ test_missing_token_logs_warning_and_returns_false ______________
  >       assert res is False
  E       assert None is False
  =========================== short test summary info ===========================
  FAILED tests/test_telegram.py::test_noop_when_env_not_set - assert None is False
  FAILED tests/test_telegram.py::test_missing_token_logs_warning_and_returns_false
  ========================= 2 failed, 4 passed in 0.51s =========================
  ```
- **Sau khi khôi phục lại code chuẩn:**
  Cả 6 test trong `tests/test_telegram.py` đều **PASSED**, `tests/test_telegram_isolation.py` 2 test **PASSED**.

### 2.5 Lần gửi thật đúng một tin (`scripts/.probe_dead_man_switch.py --part-a`)
Thực hiện lệnh nạp biến môi trường từ `.env` và chạy Phần A:
```text
OK: TELEGRAM_BOT_TOKEN da duoc thiet lap (an secret), TELEGRAM_CHAT_ID=<da che>

=== PHAN A: gui thang 1 tin qua send_telegram() (khong qua alert) ===
Telegram API xac nhan da nhan: THANH CONG (send_telegram tra ve True).
```
**Kết luận:** Đã gửi đúng **một** tin duy nhất. Telegram API xác nhận nhận tin (`send_telegram` trả về `True`). Người vận hành không cần mở điện thoại mà script đã tự khẳng định chặng cuối của chuỗi cảnh báo hoạt động hoàn hảo.

---

## 3. Task 2 — Bảng: Mỗi chuông có thể bị nuốt ở đâu?

### 3.1 Bảng khảo sát 7 job trong `sched.sh`
| Job | Phát cảnh báo bằng gì | Có bọc `try` quanh việc gửi không | Nếu gửi hỏng thì sao | Có ghi lại dấu vết không |
|---|---|---|---|---|
| **`heartbeat`** (`heartbeat_check.py`) | Gọi trực tiếp `send_telegram(...)` (dòng 231, 261, 347) | **KHÔNG** | *Trước T1:* Sập script (`EXIT=1`).<br>*Sau T1:* Ghi warning log, `return 1` | Có: stdout/stderr và traceback/warning được ghi vào `logs/heartbeat.log`. |
| **`daily-check`** (`daily_data_check.py`) | Gọi `send_telegram(...)` (dòng 151) | **CÓ** (`try ... except`) | Bắt exception, in "Lỗi khi gửi Telegram", `sys.exit(code)` | Có: lý do in trước ở dòng 147, mã thoát exit 1/2 ghi vào `logs/daily-data-check.log`. |
| **`backfill`** (`backfill_universe.py`) | **Không có chuông Telegram** | N/A | N/A | Có: toàn bộ tiến trình ghi vào `logs/backfill.log`. Bàn giao việc kiểm tra cho `daily-check` lúc 21:00. |
| **`deploy-drift`** (`deploy_drift_check.py`) | `alert_and_fail` qua `_alert_common.py` | **CÓ** (`try ... except`) | Bắt exception, in "GUI TELEGRAM HONG", trả `exit 1` | Có: in lý do ra stdout trước khi gửi, lưu vào `logs/deploy-drift.log`, `EXIT=1`. |
| **`engine-cam`** (`check_silent_engine.py`) | `alert_and_fail` qua `_alert_common.py` | **CÓ** (`try ... except`) | Bắt exception, in "GUI TELEGRAM HONG", trả `exit 1` | Có: in bảng mã câm ra stdout trước khi gửi, lưu vào `logs/engine-cam.log`, `EXIT=1`. |
| **`engine-consumer`** (`engine_consumer_check.py`) | Gọi trực tiếp `send_telegram(...)` (dòng 132, 147, 176) | **KHÔNG** | *Trước T1:* Sập script (`EXIT=1`).<br>*Sau T1:* Ghi warning log, return 1 | Có: in lý do ra stdout trước khi gửi (dòng 146, 173), lưu vào `logs/engine-consumer.log`. |
| **`stream-health`** (`stream_health_check.py`) | **Không gọi Telegram nội tại** | N/A | N/A | Có: in tỷ lệ và số nến chốt ra stderr/stdout, ghi vào `logs/stream-health.log`, trả exit code 1 hoặc 2. |

### 3.2 Trả lời hai câu hỏi
1. **Job nào hỏng im lặng nhất?**
   - **Đường cảnh báo của chính `collector`/`engine` qua `trading/alerts.py:alert()`:** Khi `alert()` spawn thread daemon chạy `send_telegram`, trước Task 1 nếu thiếu biến môi trường Telegram nó sẽ im lặng `return` trần — **không một dòng log nào, không traceback, biến mất hoàn toàn**.
   - **Trong 7 job `sched.sh`:**
     - `daily-check`: Trước Task 1, nếu thiếu biến môi trường Telegram, nó im lặng return, và dòng tiếp theo script in ra: `-> Đã gửi cảnh báo qua Telegram.` và ghi vào `logs/daily-data-check.log`! Đây là dạng hỏng **dối trá nhất**: log khẳng định đã gửi tin nhưng thực chất điện thoại không bao giờ rung.
     - `stream-health`: Là chuông hoàn toàn không có Telegram; nếu rơi rụng nến trong phiên (exit 2) thì chỉ để lại log trong `logs/stream-health.log`, người dùng không mở xem sẽ không biết.
2. **Sau Task 1, job nào vẫn còn lỗ?**
   - **`daily_data_check.py:150-155`:** Vẫn bỏ qua giá trị trả về của `send_telegram`. Khi `send_telegram` trả về `False`, script không kiểm tra mà vẫn in dòng `-> Đã gửi cảnh báo qua Telegram.`.
   - **`engine_consumer_check.py:176-177`:** Bỏ qua giá trị trả về của `send_telegram`. Kể cả khi gửi thất bại (`send_telegram` trả `False`), script vẫn cập nhật `new_state["last_alert_ts"] = now.timestamp()`. Hậu quả: thời gian cooldown 15 phút chống spam bắt đầu kích hoạt và nó sẽ **ngậm tăm trong 15 phút tiếp theo**, không gửi lại dù tin đầu tiên chưa từng tới Telegram!
   - **`trading/alerts.py:37`:** Gọi trong thread daemon nền và không kiểm tra giá trị trả về, không có cơ chế retry hay hàng đợi lưu lại tin gửi hỏng.

---

## 4. Task 3 — `is_trading_day` về đúng nhà

### 4.1 `git diff` ba file
#### 1. `trading/calendar_vn.py`
```diff
diff --git a/trading/calendar_vn.py b/trading/calendar_vn.py
index bfbd2a2..7c7a899 100644
--- a/trading/calendar_vn.py
+++ b/trading/calendar_vn.py
@@ -13,6 +13,11 @@ def is_trading_time(ts: datetime, holidays: set[date] = frozenset()) -> bool:
     return any(start <= t <= end for start, end in SESSIONS)
 
 
+def is_trading_day(d: date, holidays: set[date] | frozenset = frozenset()) -> bool:
+    """Kiểm tra một ngày có phải ngày giao dịch VN (T2-T6, không phải ngày lễ)."""
+    return d.weekday() < 5 and d not in holidays
+
+
 def trading_days_between(
     start: datetime, end: datetime, holidays: frozenset = frozenset()
 ) -> int:
```

#### 2. `scripts/daily_data_check.py`
```diff
diff --git a/scripts/daily_data_check.py b/scripts/daily_data_check.py
index 23d7abd..075f9f5 100644
--- a/scripts/daily_data_check.py
+++ b/scripts/daily_data_check.py
@@ -16,7 +16,7 @@ CLI:
 
 import argparse
 import sys
-from datetime import datetime, time
+from datetime import datetime
 from pathlib import Path
 
 # Đảm bảo import được _db_common và trading
@@ -26,7 +26,7 @@ sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
 from _db_common import resolve_dsn
 
 from trading.alerts import _print_safe
-from trading.calendar_vn import TZ, is_trading_time
+from trading.calendar_vn import TZ, is_trading_day
 from trading.config import load_config
 from trading.storage.db import Storage
 from trading.telegram import send_telegram
@@ -136,9 +136,8 @@ def main() -> None:
         _print_safe(f"LỖI TRUY VẤN DB: {e}")
         sys.exit(2)
 
-    ts_mid = datetime.combine(target_date, time(10, 0), tzinfo=TZ)
     holidays = cfg.holidays
-    trading_day = is_trading_time(ts_mid, holidays)
+    trading_day = is_trading_day(target_date, holidays)
 
     code, _missing, msg = evaluate_daily_completeness(
         active_symbols, present_symbols, is_trading_day=trading_day
```

#### 3. `scripts/stream_health_check.py`
```diff
diff --git a/scripts/stream_health_check.py b/scripts/stream_health_check.py
index 07a56c1..6e766bb 100644
--- a/scripts/stream_health_check.py
+++ b/scripts/stream_health_check.py
@@ -38,7 +38,7 @@ from datetime import UTC, date, datetime, time, timedelta
 from pathlib import Path
 from zoneinfo import ZoneInfo
 
-from trading.calendar_vn import is_trading_time
+from trading.calendar_vn import is_trading_day
 
 if hasattr(sys.stdout, "reconfigure"):
     sys.stdout.reconfigure(encoding="utf-8", errors="replace")
@@ -402,8 +402,7 @@ def main() -> None:
     # 1. ngay nghi?        -> bo qua, exit 0
     # 2. phien chua xong?  -> bo qua, exit 0     (dot 50)
     # 3. do do phu luong                          (dot 47/49)
-    ts_mid = datetime.combine(check_date, time(10, 0), tzinfo=TZ_VN)
-    if not is_trading_time(ts_mid, holidays=holidays):
+    if not is_trading_day(check_date, holidays=holidays):
         print(f"bo qua: {check_date.isoformat()} la ngay nghi")
         sys.exit(0)
```

### 4.2 Bốn lượt dữ liệu thật nguyên văn
1. **Lệnh 1:**
   ```text
   $ uv run python scripts/stream_health_check.py --date 2026-09-12 --session sang
   bo qua: 2026-09-12 la ngay nghi
   Exit code: 0
   ```
2. **Lệnh 2:**
   ```text
   $ uv run python scripts/stream_health_check.py --date 2026-09-19 --session sang
   bo qua: 2026-09-19 la ngay nghi
   Exit code: 0
   ```
3. **Lệnh 3:**
   ```text
   $ uv run python scripts/stream_health_check.py --date 2026-09-18 --session sang
   dung: phien sang ngay 2026-09-18 khong co dong 'bars closed' nao tu luong thoi gian thuc (0 nen) [nguon: log]
   EXIT_CODE: 2
   ```
4. **Lệnh 4:**
   ```text
   $ uv run python scripts/daily_data_check.py --date 2026-09-19
   [2026-09-19] Không có mã nào có bar trong ngày (ngày nghỉ hoặc feed ngừng toàn diện — nhường Heartbeat 2A).
   EXIT_CODE: 0
   ```
*(Tất cả 4 lệnh đều cho kết quả nguyên văn y hệt đợt 55, chứng minh refactor không làm đổi hành vi bên ngoài).*

### 4.3 Kết quả `grep` sau khi gom
```text
$ grep -n "def is_trading_day" **/*.py
trading/calendar_vn.py:16:def is_trading_day(d: date, holidays: set[date] | frozenset = frozenset()) -> bool:

$ grep -n "is_trading_day(" **/*.py
trading/calendar_vn.py:16:def is_trading_day(d: date, holidays: set[date] | frozenset = frozenset()) -> bool:
tests/test_calendar.py:81:    assert is_trading_day(date(2026, 7, 18)) is False
tests/test_calendar.py:83:    assert is_trading_day(date(2026, 7, 19)) is False
tests/test_calendar.py:85:    assert is_trading_day(date(2026, 7, 15), holidays={date(2026, 7, 15)}) is False
tests/test_calendar.py:87:    assert is_trading_day(date(2026, 7, 15), holidays=set()) is True
tests/test_calendar.py:88:    assert is_trading_day(date(2026, 7, 15)) is True
scripts/daily_data_check.py:140:    trading_day = is_trading_day(target_date, holidays)
scripts/docker_down_alert.py:64:def _is_trading_day(now: datetime, holidays: frozenset) -> bool:
scripts/docker_down_alert.py:104:    if not _is_trading_day(now, holidays):
scripts/stream_health_check.py:405:    if not is_trading_day(check_date, holidays=holidays):
```
- Đúng duy nhất **1 nơi** định nghĩa `is_trading_day`: `trading/calendar_vn.py:16`.
- Hai nơi gọi chính thức đã gom xong: `scripts/daily_data_check.py` và `scripts/stream_health_check.py`.
- Chỗ thứ ba còn lại: `scripts/docker_down_alert.py:64` định nghĩa `_is_trading_day` riêng có chủ đích (gọi `in_bar_check_window` của `heartbeat_check.py` để bám theo heartbeat, không gom để tránh phá vỡ thiết kế có chủ ý).

---

## 5. Tổng kết kiểm định chất lượng

1. **Test suite:** **791 passed in 62.32s** (tăng đúng 5 test từ mốc 786; gồm 4 test trong `test_telegram.py` và 1 test trong `test_calendar.py`).
2. **Ruff linter:** `uv run ruff check trading tests scripts` -> **All checks passed!**
3. **Cổng cứng VN (`measure_strategy.py`):**
   ```text
   TỔNG: strat -1,615,319,902 | BH 1,897,587,481,903 | diff -1,899,202,801,806 | lệnh 1,514 | mã sinh lệnh 439 | mã đủ thanh khoản 748 | dòng bẩn 10,459
   ```
   Khớp chính xác 100% 4 con số chuẩn: `-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã`.


---

## Phụ lục — ghi chú của Claude (auditor), 19/09/2026

Ba task đạt, và **câu hỏi sáu đợt của tôi đã có lời đáp**. Bốn điều ghi thêm: một chỗ tôi tự sửa,
một chỗ nên che, một cái bẫy mới sinh ra, và một phát hiện của agent mà tôi muốn nhấn mạnh.

### A. Những gì tôi tự chạy lại

```
792 passed (791 cua agent + 1 test toi them o muc B)
ruff: All checks passed!
TONG: strat -1,615,319,902 | BH 1,897,587,481,903 | lenh 1,514 | ma sinh lenh 439   <- khop

--date 2026-09-12 --session sang  -> EXIT=0  "bo qua: 2026-09-12 la ngay nghi"
--date 2026-09-19 --session sang  -> EXIT=0  "bo qua: 2026-09-19 la ngay nghi"
--date 2026-09-18 --session sang  -> EXIT=2  "... 0 nen [nguon: log]"
daily_data_check --date 2026-09-19 -> EXIT=0  nhanh ngay nghi
```

Bản vá `telegram.py` đúng hợp đồng: `logger.warning` chứ không `alert()` (tránh đệ quy), nêu
**tên biến** thiếu chứ không nêu giá trị, đọc `payload.get("ok") is True`, bắt mọi exception.
Tôi kiểm thêm một điều báo cáo không nhắc: **thông điệp lỗi không rò token**. `HTTPError.__str__`
cho `"HTTP Error 401: Unauthorized"` và `URLError` cho lý do mạng — cả hai **không kèm URL**, mà
URL mới là chỗ chứa token.

### B. Tôi sửa thêm một chỗ: `daily_data_check` đang nói dối

Báo cáo Task 2 tự nêu ra lỗ này rồi **không sửa** — đúng phạm vi, vì Task 2 là "lập bảng, đừng
sửa". Nhưng nó là một câu sai sự thật in ra cho người vận hành đọc:

```python
# truoc
send_telegram(f"[{target_date}] {msg}")
_print_safe("-> Đã gửi cảnh báo qua Telegram.")     # in VO DIEU KIEN
```

Thiếu biến môi trường hoặc mạng hỏng → vẫn khẳng định "Đã gửi". Sau Task 1 thì `send_telegram`
trả `bool`, nên sửa chỉ còn một dòng:

```python
# sau
if send_telegram(f"[{target_date}] {msg}"):
    _print_safe("-> Đã gửi cảnh báo qua Telegram.")
else:
    _print_safe("-> KHÔNG gửi được cảnh báo qua Telegram (xem log để biết lý do).")
```

`try/except` cũ bỏ đi được vì hợp đồng mới cấm hàm ném.

**Và tôi thêm một test canh nó**, rồi chứng minh test phân biệt được:

```
khoi phuc hanh vi cu -> test_daily_data_check_khong_noi_doi_khi_gui_telegram_that_bai DO
khoi phuc ban va     -> 792 passed
```

Không có test đó thì ai gỡ bản vá cũng không có gì kêu — đúng bệnh cả tháng này chống.

### C. Báo cáo in `TELEGRAM_CHAT_ID` ra nguyên văn

Brief cấm in secret. `chat_id` **không phải** cấp token — có nó mà không có bot token thì không
gửi được gì — nên đây không phải sự cố. Nhưng nó là định danh riêng của chủ dự án và không nên
nằm trong báo cáo hay commit.

Công bằng với agent: **probe in nó từ trước**, dòng đó có sẵn trong
`scripts/.probe_dead_man_switch.py`, agent chỉ che thêm phần token. Việc cần làm là che nốt
`chat_id` trong probe — **việc của brief sau**, và tôi không nhắc lại con số đó ở đây.

### D. Một cái bẫy vừa được tạo ra, chưa cắn ai

`scripts/daily_data_check.py` giờ có **hai thứ cùng tên `is_trading_day`**:

```python
from trading.calendar_vn import TZ, is_trading_day          # :29  ham
def evaluate_daily_completeness(..., is_trading_day: bool = False):   # :56  tham so bool
```

Trong thân hàm đó, `is_trading_day` là **bool**, che mất hàm. Hôm nay vô hại vì hàm ấy không cần
gọi hàm lịch. Nhưng ai sau này muốn gọi `is_trading_day(d, holidays)` bên trong nó sẽ nhận
`TypeError: 'bool' object is not callable` — và sẽ mất thời gian mới hiểu vì sao.

Đợt 51 thêm tham số, đợt 56 thêm import; **không đợt nào sai, cái bẫy sinh ra ở chỗ giao nhau**.
Chữa là đổi tên tham số thành `trading_day`, nhưng test gọi nó bằng từ khoá nên phải sửa test —
**việc của brief sau**, không làm lén tối nay.

### E. Phát hiện của agent mà tôi muốn nhấn mạnh

Trong hai "lỗ còn lại sau Task 1", cái thứ hai đáng giá hơn vẻ ngoài:

> `engine_consumer_check.py` cập nhật `last_alert_ts` **kể cả khi `send_telegram` trả `False`**,
> làm kích hoạt cooldown 15 phút ngậm tăm tiếp theo.

Nghĩa là: mạng hỏng lúc chuông định kêu → tin không đi → **và chuông tự khoá miệng 15 phút nữa**.
Một lần trượt thành hai lần im. Đúng loại tương tác giữa hai cơ chế đều-hợp-lý mà không ai thấy
cho tới khi đi đọc từng dòng.

`engine_consumer_check.py` nằm trong danh sách cấm sửa của đợt này nên agent báo cáo là đúng.
**Ghi vào việc của brief sau**, và nó nên đứng trước hai việc ở mục C và D.

### F. Việc còn treo

1. **`config/config.yaml: holidays` chỉ còn ngày đã qua.** Sau đợt 55–56, `is_trading_day` đã
   được nối dây khắp nơi — nhưng nó đọc một danh sách **rỗng về tương lai**. Chỉ chủ dự án sửa được.
2. **`engine_consumer_check` khoá miệng sau khi gửi trượt** (mục E).
3. **Che `chat_id` trong probe** (mục C) và **đổi tên tham số** (mục D).
4. **Phiên 22/09** — giao thức bốn bước ở báo cáo đợt 55.


### G. Tự soát: `is_trading_day` vừa sinh ra — còn chỗ nào nên dùng nó?

Đếm mọi nơi tự viết lại cùng một vị từ:

```
trading/calendar_vn.py:10    if ts.weekday() >= 5 or ts.date() in holidays        (is_trading_time)
trading/calendar_vn.py:39    if d.weekday() < 5 and d not in holidays             (trading_days_between)
trading/calendar_vn.py:72    if day.weekday() < 5 and day not in holidays         (market_minutes_between)
trading/calendar_vn.py:91    if ts.weekday() >= 5 or ts.date() in holidays        (is_continuous_matching)
scripts/stream_health_check.py:171  if now_vn.weekday() in (5, 6) or current_date in check_holidays
scripts/stream_health_check.py:179  while prev_date.weekday() in (5, 6) or prev_date in check_holidays
scripts/heartbeat_check.py:80, :145, :241                                        (CAM SUA)
```

**Mười chỗ.** Sáu chỗ trong tầm với (bốn ngay trong `calendar_vn.py`, hai trong
`stream_health_check.py`), ba chỗ trong file cấm sửa. Dòng 39 và 72 **chính là thân của
`is_trading_day`**, chép nguyên văn.

Nghĩa là đợt 56 mới gom được *người dùng*, chưa gom *chính ngôi nhà*: `calendar_vn` có vị từ
chuẩn nhưng bốn hàm của nó vẫn tự viết lại vị từ đó.

Và một chi tiết đáng chú ý: `docker_down_alert.py:72` có comment ghi *"không chép lại điều kiện
`weekday() >= 5 or date in holidays`"* — tức là đợt 8 đã **nhìn thấy** vấn đề này và né nó bằng
cách hỏi lại `heartbeat_check`. Bây giờ đã có vị từ chuẩn, cách né đó không còn là cách duy nhất.

**Không làm tối nay, và lý do là thứ tự chứ không phải ngại:** `calendar_vn` được **collector
import** (`is_continuous_matching` là chuông im lặng trong phiên). Thứ Hai 22/09 là phép đo quyết
định của đợt 52 — sửa module ấy đêm nay là thêm một biến vào phép đo, đổi lấy **0 thay đổi hành
vi**. Việc đúng là đo xong đã.

Ghi vào brief sau, **sau** việc `engine_consumer_check` ở mục E.
