# Báo cáo kỹ thuật Đợt 66 — Chuyển handler log bền vững lên logger cha `trading`

- **Ngày thực hiện:** 19/09/2026
- **Người thực thi:** Gemini Flash 3.8
- **Người bàn giao & kiểm định:** Claude (auditor)
- **Base commit:** `3c2d63f`

---

## 1. Kết quả kiểm tra tiền đề (Task 1)

### 1.1. Kiểm tra thuộc tính `propagate`
Lệnh:
```powershell
Select-String -Path trading\*.py, trading\**\*.py -Pattern "propagate"
```
Kết quả:
```text
(Không tìm thấy dòng nào)
```
-> Không có module nào đặt `propagate = False` trên toàn bộ cây `trading.*`. Tất cả bản ghi đều truyền tự nhiên lên logger cha `"trading"`.

### 1.2. Kiểm tra chuỗi `"bars closed"` ở mức WARNING/ERROR
Lệnh:
```powershell
Select-String -Path trading\*.py, trading\**\*.py, scripts\*.py -Pattern "bars closed"
```
Kết quả:
```text
trading\collector\main.py:123:        "bars closed",
scripts\measure_session_stream_metrics.py:105:    # 2. Thu thap cac dong bars closed va late snapshot
scripts\measure_session_stream_metrics.py:131:        if "bars closed" in line:
scripts\measure_session_stream_metrics.py:154:    print(f"So lan chot nen ('bars closed'): {len(bars_closed_events)}")
scripts\stream_health_check.py:5:Trong phien giao dich vua roi, co bao nhieu nen/dong duoc chot tu luong thoi gian thuc ("bars closed")?
scripts\stream_health_check.py:91:    """Dem so dong 'bars closed' roi trong phien giao dich chi dinh."""
scripts\stream_health_check.py:101:        if "bars closed" not in line:
scripts\stream_health_check.py:439:            if "bars closed" in candidate:
scripts\stream_health_check.py:479:                f"dung: {target_name} ngay {check_date.isoformat()} khong co dong 'bars closed' nao tu luong thoi gian thuc (0 nen) [nguon: {source}]\n"
```
Đối chiếu:
- Dòng duy nhất trong thư mục `trading/` là `trading/collector/main.py:123` thuộc lệnh:
  `alert("INFO", "bars closed", ...)`
  phát ra ở mức **INFO** từ logger `trading.alerts`.
- Không có bất kỳ thông điệp log mức WARNING hoặc ERROR nào chứa chuỗi `"bars closed"`.

---

## 2. Git diff `trading/logging_setup.py` (Task 2)

```diff
diff --git a/trading/logging_setup.py b/trading/logging_setup.py
index a157545..3ec28fa 100644
--- a/trading/logging_setup.py
+++ b/trading/logging_setup.py
@@ -1,7 +1,7 @@
 """Module thiết lập logging dùng chung cho collector và engine.
 
 Cung cấp hàm attach_durable_alert_handler để gắn RotatingFileHandler vào
-logger "trading.alerts", ghi log ra volume mount /app/logs một cách bền vững.
+logger cha "trading", ghi log ra volume mount /app/logs một cách bền vững.
 """
 
 import logging
@@ -25,10 +25,22 @@ class AlertUtcIsoFormatter(logging.Formatter):
         return f"{ts} {record.getMessage()}"
 
 
+class DurableAlertFilter(logging.Filter):
+    """Filter cho phép:
+    - Mọi bản ghi từ logger trading.alerts (bất kể mức log).
+    - Bản ghi mức WARNING trở lên từ các logger khác trong cây trading.*.
+    """
+
+    def filter(self, record: logging.LogRecord) -> bool:
+        if record.name.startswith("trading.alerts"):
+            return True
+        return record.levelno >= logging.WARNING
+
+
 def attach_durable_alert_handler(
     log_dir: str | Path = DEFAULT_LOG_DIR,
     filename: str = DEFAULT_LOG_FILE,
 ) -> None:
-    """Gắn RotatingFileHandler vào logger "trading.alerts" nếu thư mục log_dir tồn tại.
+    """Gắn RotatingFileHandler vào logger "trading" nếu thư mục log_dir tồn tại.
 
     - Chỉ gắn khi log_dir là thư mục thực sự (thường là volume mount trong container).
@@ -39,8 +51,8 @@ def attach_durable_alert_handler(
         if not path.is_dir():
             return
 
-        alerts_logger = logging.getLogger("trading.alerts")
-        if any(h.get_name() == HANDLER_NAME for h in alerts_logger.handlers):
+        trading_logger = logging.getLogger("trading")
+        if any(h.get_name() == HANDLER_NAME for h in trading_logger.handlers):
             return
 
         log_file = path / filename
@@ -50,9 +62,10 @@ def attach_durable_alert_handler(
             encoding="utf-8",
         )
         handler.setFormatter(AlertUtcIsoFormatter())
+        handler.addFilter(DurableAlertFilter())
         handler.setLevel(logging.INFO)
         handler.set_name(HANDLER_NAME)
-        alerts_logger.addHandler(handler)
+        trading_logger.addHandler(handler)
     except Exception:
         pass
```

---

## 3. Git diff `tests/test_logging_setup.py` & Kết quả Pytest (Task 3)

### 3.1. Git diff
```diff
diff --git a/tests/test_logging_setup.py b/tests/test_logging_setup.py
index a2d9b23..9b053fc 100644
--- a/tests/test_logging_setup.py
+++ b/tests/test_logging_setup.py
@@ -16,21 +16,24 @@ from trading.logging_setup import (
 @pytest.fixture(autouse=True)
 def _cleanup_alert_handlers():
     """Đảm bảo dọn sạch handler sau mỗi test để không ảnh hưởng lẫn nhau."""
-    alerts_logger = logging.getLogger("trading.alerts")
-    to_remove = [h for h in alerts_logger.handlers if h.get_name() == HANDLER_NAME]
-    for h in to_remove:
-        h.close()
-        alerts_logger.removeHandler(h)
+    for name in ("trading", "trading.alerts"):
+        logger = logging.getLogger(name)
+        to_remove = [h for h in logger.handlers if h.get_name() == HANDLER_NAME]
+        for h in to_remove:
+            h.close()
+            logger.removeHandler(h)
     yield
-    to_remove = [h for h in alerts_logger.handlers if h.get_name() == HANDLER_NAME]
-    for h in to_remove:
-        h.close()
-        alerts_logger.removeHandler(h)
+    for name in ("trading", "trading.alerts"):
+        logger = logging.getLogger(name)
+        to_remove = [h for h in logger.handlers if h.get_name() == HANDLER_NAME]
+        for h in to_remove:
+            h.close()
+            logger.removeHandler(h)
 
 
 def test_attach_durable_alert_handler_idempotent(tmp_path: Path):
-    """1. Test idempotency: gọi attach_durable_alert_handler 2 lần chỉ tạo đúng 1 handler."""
-    alerts_logger = logging.getLogger("trading.alerts")
+    """1. Test idempotency: gọi attach_durable_alert_handler 2 lần chỉ tạo đúng 1 handler trên logger trading."""
+    trading_logger = logging.getLogger("trading")
 
     # Gọi lần 1
     attach_durable_alert_handler(log_dir=tmp_path)
@@ -37,6 +40,6 @@ def test_attach_durable_alert_handler_idempotent(tmp_path: Path):
     attach_durable_alert_handler(log_dir=tmp_path)
 
-    named_handlers = [h for h in alerts_logger.handlers if h.get_name() == HANDLER_NAME]
+    named_handlers = [h for h in trading_logger.handlers if h.get_name() == HANDLER_NAME]
     assert len(named_handlers) == 1
 
@@ -79,15 +82,41 @@ def test_attach_durable_alert_handler_custom_filename(tmp_path: Path):
 
 def test_attach_durable_alert_handler_idempotent_custom_filename(tmp_path: Path):
     """4. Test idempotent với tên file khác (Brief 65 Task 2.2):
-    Gọi hàm 2 lần với filename='engine_alerts.log', khẳng định logger 'trading.alerts'
+    Gọi hàm 2 lần với filename='engine_alerts.log', khẳng định logger 'trading'
     vẫn chỉ có đúng một handler tên HANDLER_NAME ('trading-alerts-file').
     """
-    alerts_logger = logging.getLogger("trading.alerts")
+    trading_logger = logging.getLogger("trading")
 
     attach_durable_alert_handler(log_dir=tmp_path, filename="engine_alerts.log")
     attach_durable_alert_handler(log_dir=tmp_path, filename="engine_alerts.log")
 
-    named_handlers = [h for h in alerts_logger.handlers if h.get_name() == HANDLER_NAME]
+    named_handlers = [h for h in trading_logger.handlers if h.get_name() == HANDLER_NAME]
     assert len(named_handlers) == 1
+
+
+def test_ba_duong_log_va_loc_on(tmp_path: Path):
+    """5. Test ba đường log và lọc ồn (Brief 66 Task 3):
+    - Ba đường log đều vào file bền:
+      + trading.alerts.critical
+      + trading.telegram.warning (đường Telegram gửi trượt được cứu)
+      + trading.engine.real_orders.warning
+    - Lọc ồn:
+      + trading.collector.main.info bị chặn bởi filter, không có trong file.
+    """
+    attach_durable_alert_handler(log_dir=tmp_path, filename="bars_closed.log")
+
+    logging.getLogger("trading.alerts").critical("critical alert from alerts")
+    logging.getLogger("trading.telegram").warning("warning telegram send failed")
+    logging.getLogger("trading.engine.real_orders").warning("warning real orders risk check")
+    logging.getLogger("trading.collector.main").info("noisy collector info message")
+
+    log_file = tmp_path / "bars_closed.log"
+    assert log_file.exists()
+
+    content = log_file.read_text(encoding="utf-8")
+    assert "critical alert from alerts" in content
+    assert "warning telegram send failed" in content
+    assert "warning real orders risk check" in content
+    assert "noisy collector info message" not in content
```

### 3.2. Output chạy `uv run pytest tests/test_logging_setup.py -v`
```text
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0 -- D:\My_Vault_Obsidian\Project\AI_auto_trading_system\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\My_Vault_Obsidian\Project\AI_auto_trading_system
configfile: pyproject.toml
plugins: anyio-4.14.2, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 5 items

tests/test_logging_setup.py::test_attach_durable_alert_handler_idempotent PASSED [ 20%]
tests/test_logging_setup.py::test_attach_durable_alert_handler_writes_log PASSED [ 40%]
tests/test_logging_setup.py::test_attach_durable_alert_handler_custom_filename PASSED [ 60%]
tests/test_logging_setup.py::test_attach_durable_alert_handler_idempotent_custom_filename PASSED [ 80%]
tests/test_logging_setup.py::test_ba_duong_log_va_loc_on PASSED          [100%]

============================== 5 passed in 0.30s ==============================
```

---

## 4. Bằng chứng test phân biệt được (Task 3)

### 4.1. Khi tạm thời gắn lại ở `trading.alerts`: ĐỎ (FAILED)

Lệnh: `uv run pytest tests/test_logging_setup.py -v`
```text
================================== FAILURES ===================================
_________________________ test_ba_duong_log_va_loc_on _________________________
...
        content = log_file.read_text(encoding="utf-8")
        assert "critical alert from alerts" in content
>       assert "warning telegram send failed" in content
E       AssertionError: assert 'warning telegram send failed' in '2026-09-19T10:40:38.924829Z critical alert from alerts\n'

tests\test_logging_setup.py:120: AssertionError
------------------------------ Captured log call ------------------------------
CRITICAL trading.alerts:test_logging_setup.py:110 critical alert from alerts
WARNING  trading.telegram:test_logging_setup.py:111 warning telegram send failed
WARNING  trading.engine.real_orders:test_logging_setup.py:112 warning real orders risk check
=========================== short test summary info ===========================
FAILED tests/test_logging_setup.py::test_attach_durable_alert_handler_idempotent
FAILED tests/test_logging_setup.py::test_attach_durable_alert_handler_idempotent_custom_filename
FAILED tests/test_logging_setup.py::test_ba_duong_log_va_loc_on - AssertionError: assert 'warning telegram send failed' in '2026-09-19T10:40:38.924829Z critical alert from alerts\n'
========================= 3 failed, 2 passed in 0.55s =========================
```
*Ghi nhận:* Đúng như dự kiến, khi gắn ở `trading.alerts`, dòng WARNING của `trading.telegram` bị bỏ sót hoàn toàn.

### 4.2. Khi khôi phục gắn ở `trading`: XANH (PASSED)
```text
tests/test_logging_setup.py::test_attach_durable_alert_handler_idempotent PASSED [ 20%]
tests/test_logging_setup.py::test_attach_durable_alert_handler_writes_log PASSED [ 40%]
tests/test_logging_setup.py::test_attach_durable_alert_handler_custom_filename PASSED [ 60%]
tests/test_logging_setup.py::test_attach_durable_alert_handler_idempotent_custom_filename PASSED [ 80%]
tests/test_logging_setup.py::test_ba_duong_log_va_loc_on PASSED          [100%]
============================== 5 passed in 0.30s ==============================
```

---

## 5. Git diff cập nhật chú thích (Task 4)

Trong `trading/collector/main.py`:
```diff
diff --git a/trading/collector/main.py b/trading/collector/main.py
index a61ce5d..9ab01fa 100644
--- a/trading/collector/main.py
+++ b/trading/collector/main.py
@@ -490,7 +490,7 @@ def _configure_logging() -> None:
     # "Token refreshed successfully", hữu ích và không chứa secret.
     logging.getLogger("ssi_sdk.transport.websocket").setLevel(logging.WARNING)
 
-    # Brief 52 / Brief 63: Gắn RotatingFileHandler vào logger "trading.alerts"
+    # Brief 52 / Brief 63 / Brief 66: Gắn RotatingFileHandler vào logger cha "trading"
     attach_durable_alert_handler()
```

---

## 6. Hồi quy & Linting

1. **Ruff check:**
   ```bash
   uv run ruff check trading tests scripts
   # -> All checks passed!
   ```
2. **Pytest suite:**
   ```bash
   uv run pytest -m "not integration" -q
   # -> 706 passed, 113 deselected in 23.83s
   ```
   *(Tổng test tăng từ 705 lên 706, không có test nào bị hồi quy).*
