# Báo cáo kỹ thuật Đợt 65 — Đưa log bền vững của engine ra file RIÊNG

- **Ngày thực hiện:** 19/09/2026
- **Người thực thi:** Gemini Flash 3.8
- **Người bàn giao & kiểm định:** Claude (auditor)
- **Base commit:** `62a6405` (trên nền `9b4fb3f`)

---

## 1. Mục đích & Bối cảnh

- Đợt 63 tạo `trading/logging_setup.py::attach_durable_alert_handler()` nhưng `docker-compose.yml` chỉ mount `./logs:/app/logs` cho `collector`. Service `engine` không có mount nào nên kiểm tra thư mục thất bại và im lặng không log bền vững.
- Nếu mount `./logs:/app/logs` cho `engine` mà cùng dùng chung file mặc định `bars_closed.log`, hai tiến trình độc lập trong 2 container sẽ cùng chạy `RotatingFileHandler` trên cùng một file. Khi một bên đạt 5MB và xoay vòng đổi tên file, nó sẽ làm gãy chuỗi file handle của bên kia, gây rủi ro làm hỏng nguồn log của `stream_health_check.py` (vốn ưu tiên đọc `logs/bars_closed.log`).
- **Giải pháp:** Tách file log của engine thành `engine_alerts.log` riêng biệt, mount `./logs:/app/logs` cho engine, đồng bộ tài liệu vận hành và kiểm chứng bằng test.

---

## 2. Git diff `trading/engine/main.py`

Chỉ đổi đúng 1 dòng trong `_configure_logging()`:

```diff
diff --git a/trading/engine/main.py b/trading/engine/main.py
index 1ba2d35..9c0f99f 100644
--- a/trading/engine/main.py
+++ b/trading/engine/main.py
@@ -486,7 +486,7 @@ async def run(cfg: Config) -> None:
 
 def _configure_logging() -> None:
     logging.basicConfig(level=logging.INFO, format="%(message)s")
-    attach_durable_alert_handler()
+    attach_durable_alert_handler(filename="engine_alerts.log")
 
 
 def main() -> None:
```

---

## 3. Git diff `docker-compose.yml`

Chỉ thêm 2 dòng mount volume `./logs:/app/logs` vào service `engine`:

```diff
diff --git a/docker-compose.yml b/docker-compose.yml
index bbc74ec..cb9eb10 100644
--- a/docker-compose.yml
+++ b/docker-compose.yml
@@ -61,6 +61,8 @@ services:
     restart: unless-stopped
     mem_limit: 512m
     cpus: 1.0
+    volumes:
+      - ./logs:/app/logs
   collector:
     build: .
     command: python -m trading.collector.main --config config/config.yaml
```

---

## 4. Kiểm chứng cấu hình Docker Compose (Mục 1.3)

Lệnh:
```powershell
Select-String -Path docker-compose.yml -Pattern "logs:/app/logs" -Context 6,0
```

Kết quả:
```text
  docker-compose.yml:59:      postgres: {condition: service_healthy}
  docker-compose.yml:60:      nats: {condition: service_started}
  docker-compose.yml:61:    restart: unless-stopped
  docker-compose.yml:62:    mem_limit: 512m
  docker-compose.yml:63:    cpus: 1.0
  docker-compose.yml:64:    volumes:
> docker-compose.yml:65:      - ./logs:/app/logs
  docker-compose.yml:80:      postgres: {condition: service_healthy}
  docker-compose.yml:81:      nats: {condition: service_started}
  docker-compose.yml:82:    restart: unless-stopped
  docker-compose.yml:83:    mem_limit: 512m
  docker-compose.yml:84:    cpus: 1.0
  docker-compose.yml:85:    volumes:
> docker-compose.yml:86:      - ./logs:/app/logs
```
Xác nhận: Có **đúng hai** service (`engine` ở dòng 65 và `collector` ở dòng 86) mang volume mount `./logs:/app/logs`.

---

## 5. Test chứng minh hai file tách biệt (`tests/test_logging_setup.py`)

### 5.1. Git diff
```diff
diff --git a/tests/test_logging_setup.py b/tests/test_logging_setup.py
index a2d9b23..4bc3a43 100644
--- a/tests/test_logging_setup.py
+++ b/tests/test_logging_setup.py
@@ -58,3 +58,36 @@ def test_attach_durable_alert_handler_writes_log(tmp_path: Path):
     assert "verified_test" in content
     # Kiểm tra định dạng ISO-8601 UTC kết thúc bằng Z
     assert "Z {" in content or "Z " in content
+
+
+def test_attach_durable_alert_handler_custom_filename(tmp_path: Path):
+    """3. Test tên file tùy biến (Brief 65 Task 2.1): engine ghi ra engine_alerts.log,
+    khẳng định bars_closed.log KHÔNG tồn tại (không làm bẩn bằng chứng collector).
+    """
+    attach_durable_alert_handler(log_dir=tmp_path, filename="engine_alerts.log")
+
+    alert("CRITICAL", "test critical engine alert", component="engine")
+
+    engine_log = tmp_path / "engine_alerts.log"
+    collector_log = tmp_path / "bars_closed.log"
+
+    assert engine_log.exists(), "engine_alerts.log phai ton tai va duoc tao ra"
+    assert not collector_log.exists(), "bars_closed.log KHONG duoc ton tai khi engine log"
+
+    content = engine_log.read_text(encoding="utf-8")
+    assert "test critical engine alert" in content
+    assert "CRITICAL" in content
+    assert "engine" in content
+
+
+def test_attach_durable_alert_handler_idempotent_custom_filename(tmp_path: Path):
+    """4. Test idempotent với tên file khác (Brief 65 Task 2.2):
+    Gọi hàm 2 lần với filename='engine_alerts.log', khẳng định logger 'trading.alerts'
+    vẫn chỉ có đúng một handler tên HANDLER_NAME ('trading-alerts-file').
+    """
+    alerts_logger = logging.getLogger("trading.alerts")
+
+    attach_durable_alert_handler(log_dir=tmp_path, filename="engine_alerts.log")
+    attach_durable_alert_handler(log_dir=tmp_path, filename="engine_alerts.log")
+
+    named_handlers = [h for h in alerts_logger.handlers if h.get_name() == HANDLER_NAME]
+    assert len(named_handlers) == 1
```

### 5.2. Kết quả chạy pytest file logging
Lệnh: `uv run pytest tests/test_logging_setup.py -v`
```text
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0 -- D:\My_Vault_Obsidian\Project\AI_auto_trading_system\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\My_Vault_Obsidian\Project\AI_auto_trading_system
configfile: pyproject.toml
plugins: anyio-4.14.2, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 4 items

tests/test_logging_setup.py::test_attach_durable_alert_handler_idempotent PASSED [ 25%]
tests/test_logging_setup.py::test_attach_durable_alert_handler_writes_log PASSED [ 50%]
tests/test_logging_setup.py::test_attach_durable_alert_handler_custom_filename PASSED [ 75%]
tests/test_logging_setup.py::test_attach_durable_alert_handler_idempotent_custom_filename PASSED [100%]

============================== 4 passed in 0.37s ==============================
```

---

## 6. Git diff đồng bộ tài liệu (`DEPLOYMENT.md` và `docs/README_VPS_UBUNTU.md`)

```diff
diff --git a/DEPLOYMENT.md b/DEPLOYMENT.md
index 27ff56e..6c5b8d4 100644
--- a/DEPLOYMENT.md
+++ b/DEPLOYMENT.md
@@ -22,10 +22,11 @@ cp .env.example .env
 chmod 600 .env
 
 # Tạo thư mục logs trên host và phân quyền cho appuser (uid 10001 trong Dockerfile)
-# BẮT BUỘC: docker-compose.yml gắn mount ./logs:/app/logs cho collector. Nếu không
-# tạo trước, Docker daemon sẽ tự tạo thư mục thuộc root:root, collector (chạy uid 10001)
-# sẽ bị PermissionError khi ghi bars_closed.log, nuốt lỗi và chạy tiếp im lặng
-# làm mất toàn bộ bằng chứng chốt nến luồng mà không có cảnh báo nào!
+# BẮT BUỘC: docker-compose.yml gắn mount ./logs:/app/logs cho collector và engine.
+# Collector ghi logs/bars_closed.log, engine ghi logs/engine_alerts.log. Nếu không
+# tạo trước, Docker daemon sẽ tự tạo thư mục thuộc root:root, tiến trình (chạy uid 10001)
+# sẽ bị PermissionError khi ghi log, nuốt lỗi và chạy tiếp im lặng
+# làm mất toàn bộ bằng chứng chốt nến luồng và cảnh báo engine!
 mkdir -p logs && sudo chown 10001:10001 logs
 ```
 
diff --git a/docs/README_VPS_UBUNTU.md b/docs/README_VPS_UBUNTU.md
index 819d8c1..0497c2e 100644
--- a/docs/README_VPS_UBUNTU.md
+++ b/docs/README_VPS_UBUNTU.md
@@ -75,10 +75,11 @@ cp .env.example .env
 chmod 600 .env
 
 # TẠO THƯ MỤC LOGS VÀ CHOWN (BẮT BUỘC TRƯỚC KHI DỰNG DOCKER):
-# docker-compose.yml mount ./logs:/app/logs cho collector. Tiến trình trong container
+# docker-compose.yml mount ./logs:/app/logs cho collector và engine. Collector ghi
+# logs/bars_closed.log, engine ghi logs/engine_alerts.log. Tiến trình trong container
 # chạy với uid 10001 (appuser). Nếu không tạo trước, Docker daemon sẽ tự tạo thư mục
-# thuộc root:root (755), collector sẽ bị PermissionError khi ghi bars_closed.log,
-# nuốt ngoại lệ và chạy tiếp im lặng làm mất toàn bộ bằng chứng chốt nến luồng!
+# thuộc root:root (755), tiến trình sẽ bị PermissionError khi ghi log,
+# nuốt ngoại lệ và chạy tiếp im lặng làm mất toàn bộ bằng chứng chốt nến luồng và cảnh báo engine!
 mkdir -p logs && sudo chown 10001:10001 logs
 
 uv sync --frozen
```

---

## 7. Nhận xét về cạm bẫy guard theo `HANDLER_NAME` (Task 2.2)

- **Mô tả hành vi hiện có:**
  Trong `trading/logging_setup.py`:
  ```python
  if any(h.get_name() == HANDLER_NAME for h in alerts_logger.handlers):
      return
  ```
  `HANDLER_NAME = "trading-alerts-file"` là một hằng số cố định dùng chung, không phụ thuộc vào giá trị `filename`.
- **Hệ quả / Cạm bẫy:**
  Nếu trong **cùng một tiến trình**, hàm được gọi lần thứ nhất với `filename="bars_closed.log"` và sau đó gọi tiếp lần thứ hai với `filename="engine_alerts.log"`:
  Lời gọi thứ hai sẽ lập tức `return` do thấy handler mang tên `"trading-alerts-file"` đã tồn tại. File thứ hai (`engine_alerts.log`) sẽ hoàn toàn **không được tạo ra**.
- **Đánh giá rủi ro production:**
  Ở production hiện tại, collector và engine chạy ở hai container/tiến trình OS tách biệt hoàn toàn; mỗi bên chỉ khởi tạo logging một lần duy nhất lúc khởi động (`collector` dùng `bars_closed.log`, `engine` dùng `engine_alerts.log`). Do đó, cạm bẫy này không phát sinh lỗi ở runtime hiện tại. Tuy nhiên, nếu tương lai có kịch bản test hoặc ứng dụng đơn khối gộp chung 2 service vào 1 tiến trình thì guard này sẽ bỏ qua handler thứ hai.
- **Tuân thủ brief:** Giữ nguyên 100% mã nguồn của `trading/logging_setup.py`, không tự ý sửa guard.

---

## 8. Trạng thái Docker container (Task 4 - Chỉ đọc)

Lệnh: `docker compose ps`
```text
NAME                                 IMAGE                               COMMAND                  SERVICE     CREATED        STATUS                    PORTS
ai_auto_trading_system-collector-1   ai_auto_trading_system-collector    "python -m trading.c…"   collector   11 hours ago   Up 16 minutes             
ai_auto_trading_system-engine-1      ai_auto_trading_system-engine       "python -m trading.e…"   engine      11 hours ago   Up 16 minutes             
ai_auto_trading_system-grafana-1     grafana/grafana:11.2.0              "/run.sh"                grafana     5 weeks ago    Up 16 minutes             127.0.0.1:3000->3000/tcp
ai_auto_trading_system-nats-1        nats:2.10-alpine                    "docker-entrypoint.s…"   nats        2 weeks ago    Up 16 minutes             127.0.0.1:4222->4222/tcp
ai_auto_trading_system-nats-test-1   nats:2.10-alpine                    "docker-entrypoint.s…"   nats-test   2 weeks ago    Up 16 minutes             127.0.0.1:4223->4222/tcp
ai_auto_trading_system-postgres-1    timescale/timescaledb:latest-pg16   "docker-entrypoint.s…"   postgres    2 weeks ago    Up 16 minutes (healthy)   127.0.0.1:5432->5432/tcp
```
*Ghi chú:* Tuyệt đối không chạy build, up, restart hay down container.

---

## 9. Hồi quy & Linting

1. **Ruff linter:**
   ```bash
   uv run ruff check trading tests scripts
   ```
   Output:
   ```text
   All checks passed!
   ```

2. **Pytest test suite:**
   ```bash
   uv run pytest -m "not integration" -q
   ```
   Output:
   ```text
   705 passed, 113 deselected in 30.27s
   ```
   (Tăng từ 703 lên 705 passed, không có bất kỳ test cũ nào bị hỏng).
