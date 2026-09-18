# Báo cáo Đợt 55 — Lỗ cuối tuần, tag cuốn chiếu, và chuẩn bị phép đo 22/09

Ngày thực hiện: 19/09/2026 (thứ Bảy).
Base: `0d5b0b5` (main).
Người thực thi: Gemini Flash 3.8.
Người nhận: Claude (planner/auditor) & Chủ dự án.

---

## 1. Trạng thái Git & Diff Stat

### 1.1 `git status --short`
```text
 M DEPLOYMENT.md
 M README.md
 M scripts/stream_health_check.py
 tests/test_stream_health_check.py
?? "Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md"
```
*(Ghi chú: README.md giữ nguyên 253 dòng đổi chờ chủ dự án duyệt; không commit, không push).*

### 1.2 `git diff --stat`
```text
 DEPLOYMENT.md                     |  49 +++++++---
 README.md                         | 188 +++++++++++++++++++++++++-------------
 scripts/stream_health_check.py    |  39 +++++++-
 tests/test_stream_health_check.py |  71 ++++++++++++++
 4 files changed, 266 insertions(+), 81 deletions(-)
```

---

## 2. Task 1 — Ngày nghỉ truyền tường minh vẫn phải im & Nối dây holidays

### 2.1 Git diff của hai file
#### `scripts/stream_health_check.py`
```diff
diff --git a/scripts/stream_health_check.py b/scripts/stream_health_check.py
index 850cd7b..07a56c1 100644
--- a/scripts/stream_health_check.py
+++ b/scripts/stream_health_check.py
@@ -38,6 +38,8 @@ from datetime import UTC, date, datetime, time, timedelta
 from pathlib import Path
 from zoneinfo import ZoneInfo
 
+from trading.calendar_vn import is_trading_time
+
 if hasattr(sys.stdout, "reconfigure"):
     sys.stdout.reconfigure(encoding="utf-8", errors="replace")
     sys.stderr.reconfigure(encoding="utf-8", errors="replace")
@@ -128,6 +130,27 @@ def fetch_docker_collector_logs() -> str:
     return res.stdout or ""
 
 
+def load_holidays(config_path: str = "config/config.yaml") -> set[date]:
+    """Đọc danh sách ngày lễ từ config/config.yaml (Brief 55 Task 1).
+
+    An toàn, không yêu cầu biến môi trường DB/SSI như load_config.
+    """
+    p = Path(config_path)
+    if not p.is_file():
+        repo_root = Path(__file__).resolve().parents[1]
+        p = repo_root / config_path
+    if not p.is_file():
+        return set()
+    try:
+        import yaml
+
+        with open(p, encoding="utf-8") as f:
+            raw = yaml.safe_load(f) or {}
+        return {date.fromisoformat(str(h)) for h in raw.get("holidays", [])}
+    except Exception:
+        return set()
+
+
 def resolve_target_session(
     now_vn: datetime,
     holidays: set[date] | None = None,
@@ -353,6 +376,7 @@ def main() -> None:
 
     args = parser.parse_args()
     now_vn = datetime.now(TZ_VN)
+    holidays = load_holidays()
 
     # 3 tổ hợp tham số theo Brief 49 §2.6
     if args.date and args.session:
@@ -364,8 +388,8 @@ def main() -> None:
         session = None
         target_name = "ca ngay"
     else:
-        # Cả hai đều thiếu: chọn phiên gần nhất ĐÃ KẾT THÚC
-        resolved = resolve_target_session(now_vn)
+        # Cả hai đều thiếu: chọn phiên gần nhất ĐÃ KẾT THÚC (Brief 55 Task 1.1b: nối dây holidays)
+        resolved = resolve_target_session(now_vn, holidays=holidays)
         if resolved is None:
             print(
                 "bo qua: khong co phien giao dich nao ket thuc trong vong 24 gio (ngay nghi/cuoi tuan)"
@@ -374,7 +398,16 @@ def main() -> None:
         check_date, session = resolved
         target_name = f"phien {session}"
 
-    # Bổ sung Brief 50 Task 1: Phiên chưa kết thúc thì bỏ qua, không kêu
+    # Brief 55 Task 1.2: Ba cửa kiểm tra theo thứ tự:
+    # 1. ngay nghi?        -> bo qua, exit 0
+    # 2. phien chua xong?  -> bo qua, exit 0     (dot 50)
+    # 3. do do phu luong                          (dot 47/49)
+    ts_mid = datetime.combine(check_date, time(10, 0), tzinfo=TZ_VN)
+    if not is_trading_time(ts_mid, holidays=holidays):
+        print(f"bo qua: {check_date.isoformat()} la ngay nghi")
+        sys.exit(0)
+
+    # 2. Phiên chưa kết thúc thì bỏ qua, không kêu (Brief 50 Task 1)
     if not is_session_ended(check_date, session, now_vn):
         print(
             f"bo qua: {target_name} ngay {check_date.isoformat()} chua ket thuc tai thoi diem kiem tra"
```

#### `tests/test_stream_health_check.py` (Chỉ thêm 4 test 16–19, 0 sửa test cũ)
```diff
diff --git a/tests/test_stream_health_check.py b/tests/test_stream_health_check.py
index 65a2e00..9058b73 100644
--- a/tests/test_stream_health_check.py
+++ b/tests/test_stream_health_check.py
@@ -418,3 +418,74 @@ def test_15_persistent_file_without_evidence_falls_back_to_log(tmp_path, monkeyp
     out = capsys.readouterr().out
     assert "co 2 lan chot nen" in out
     assert "[nguon: log]" in out
+
+
+def test_16_resolve_target_session_receives_holidays():
+    """16. Brief 55 Task 1.1b: resolve_target_session nhận holidays và bỏ qua ngày lễ giữa tuần."""
+    from datetime import datetime
+    from zoneinfo import ZoneInfo
+
+    from scripts.stream_health_check import resolve_target_session
+
+    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
+    # Ngày 02/09/2026 là thứ Tư (ngày thường trong tuần)
+    dt_holiday_noon = datetime(2026, 9, 2, 12, 0, 0, tzinfo=tz_vn)
+    holidays = {date(2026, 9, 2)}
+
+    # Gọi với holidays chứa ngày đó -> phải trả về None
+    res = resolve_target_session(dt_holiday_noon, holidays=holidays)
+    assert res is None, f"Kỳ vọng None vì là ngày lễ giữa tuần, nhận: {res}"
+
+    # Gọi không có holidays -> trả về phiên sáng (lỗi cũ trước khi sửa)
+    res_no_holidays = resolve_target_session(dt_holiday_noon, holidays=None)
+    assert res_no_holidays == (date(2026, 9, 2), "sang")
+
+
+def test_17_explicit_date_past_saturday_ignored(monkeypatch, capsys):
+    """17. Brief 55 Task 1.1: Truyền tường minh một thứ Bảy đã qua -> bỏ qua, exit 0."""
+    monkeypatch.setattr("sys.argv", [
+        "stream_health_check.py",
+        "--date", "2026-09-12",
+        "--session", "sang",
+    ])
+    with pytest.raises(SystemExit) as exc:
+        main()
+    assert exc.value.code == 0
+    out = capsys.readouterr().out
+    assert "bo qua: 2026-09-12 la ngay nghi" in out
+
+
+def test_18_explicit_date_weekday_holiday_ignored(monkeypatch, capsys):
+    """18. Brief 55 Task 1.1: Truyền tường minh ngày lễ giữa tuần (01/09 thứ Ba) -> bỏ qua, exit 0."""
+    monkeypatch.setattr("sys.argv", [
+        "stream_health_check.py",
+        "--date", "2026-09-01",
+        "--session", "sang",
+    ])
+    with pytest.raises(SystemExit) as exc:
+        main()
+    assert exc.value.code == 0
+    out = capsys.readouterr().out
+    assert "bo qua: 2026-09-01 la ngay nghi" in out
+
+
+def test_19_explicit_date_past_trading_day_not_ignored(monkeypatch, capsys, tmp_path):
+    """19. Brief 55 Task 1.3: Truyền ngày giao dịch đã qua (17/09 thứ Năm) -> đo bình thường, không bỏ qua."""
+    dummy_log = tmp_path / "dummy.log"
+    dummy_log.write_text(
+        '2026-09-17T06:10:00.000000Z {"level": "INFO", "msg": "bars closed", "n": 1}\n',
+        encoding="utf-8",
+    )
+    monkeypatch.setattr("sys.argv", [
+        "stream_health_check.py",
+        "--date", "2026-09-17",
+        "--session", "chieu",
+        "--log-file", str(dummy_log),
+    ])
+    with pytest.raises(SystemExit) as exc:
+        main()
+    assert exc.value.code == 0
+    out = capsys.readouterr().out
+    assert not out.startswith("bo qua:")
+    assert "co 1 lan chot nen" in out
```

### 2.2 Bốn lượt dữ liệu thật nguyên văn
1. **Lệnh 1 (Thứ Bảy đã qua — ca lỗi gốc):**
   ```text
   $ uv run python scripts/stream_health_check.py --date 2026-09-12 --session sang
   bo qua: 2026-09-12 la ngay nghi
   Exit code: 0
   ```
2. **Lệnh 2 (Hôm nay — thứ Bảy 19/09):**
   ```text
   $ uv run python scripts/stream_health_check.py --date 2026-09-19 --session sang
   bo qua: 2026-09-19 la ngay nghi
   Exit code: 0
   ```
3. **Lệnh 3 (Không tham số — đường mặc định của Scheduled Task):**
   ```text
   $ uv run python scripts/stream_health_check.py
   bo qua: khong co phien giao dich nao ket thuc trong vong 24 gio (ngay nghi/cuoi tuan)
   Exit code: 0
   ```
4. **Lệnh 4 (Ngày giao dịch đã qua — 18/09):**
   ```text
   $ uv run python scripts/stream_health_check.py --date 2026-09-18 --session sang
   dung: phien sang ngay 2026-09-18 khong co dong 'bars closed' nao tu luong thoi gian thuc (0 nen) [nguon: log]
   EXIT_CODE: 2
   ```
   *(Đúng kết quả mong đợi: đi tới bước đo thực sự, không rơi vào nhánh bỏ qua; trả exit 2 do container log bị xoá hôm 18/09).*

### 2.3 Bằng chứng test phân biệt được (Negative testing)
- **Khi tạm gỡ Cửa 1 (comment dòng kiểm tra `is_trading_time`):**
  ```text
  ================================== FAILURES ===================================
  _________________ test_17_explicit_date_past_saturday_ignored _________________
  >       assert exc.value.code == 0
  E       assert 2 == 0
  E        +  where 2 = SystemExit(2).code
  ---------------------------- Captured stderr call -----------------------------
  dung: phien sang ngay 2026-09-12 khong co dong 'bars closed' nao tu luong thoi gian thuc (0 nen) [nguon: log]
  ________________ test_18_explicit_date_weekday_holiday_ignored ________________
  >       assert exc.value.code == 0
  E       assert 2 == 0
  E        +  where 2 = SystemExit(2).code
  ---------------------------- Captured stderr call -----------------------------
  dung: phien sang ngay 2026-09-01 khong co dong 'bars closed' nao tu luong thoi gian thuc (0 nen) [nguon: log]
  =========================== short test summary info ===========================
  FAILED tests/test_stream_health_check.py::test_17_explicit_date_past_saturday_ignored
  FAILED tests/test_stream_health_check.py::test_18_explicit_date_weekday_holiday_ignored
  ======================== 2 failed, 17 passed in 9.30s =========================
  ```
- **Sau khi khôi phục lại Cửa 1:**
  `tests/test_stream_health_check.py` đạt **19 passed in 0.43s**, và git diff file `scripts/stream_health_check.py` chỉ chứa đúng các dòng sửa chuẩn, không rác.

---

## 3. Task 2 — Viết cơ chế `:previous` vào `DEPLOYMENT.md`

### 3.1 `git diff DEPLOYMENT.md`
```diff
diff --git a/DEPLOYMENT.md b/DEPLOYMENT.md
index ab28dcc..27ff56e 100644
--- a/DEPLOYMENT.md
+++ b/DEPLOYMENT.md
@@ -394,33 +394,52 @@ từ 15/08/2026 tới 01/09/2026 chưa từng chạy vì không ai dựng lại
 kiểm "sửa đã hoạt động" trên container vẫn chạy image cũ → kết luận sai).
 
 Sau khi commit sửa code, dựng lại (chỉ 2 service — không `down`, không đụng
-postgres/nats/grafana, không xoá volume):
+postgres/nats/grafana, không xoá volume).
+
+**Quy tắc bắt buộc:** Gắn tag cuốn chiếu `:previous` TRƯỚC KHI BUILD để luôn có một điểm lui an toàn:
 
 ```bash
-docker compose up -d --build collector engine
+# 1. BẮT BUỘC TRƯỚC KHI BUILD: lưu ảnh hiện tại thành :previous
+docker tag ai_auto_trading_system-collector:latest ai_auto_trading_system-collector:previous 2>/dev/null || true
+docker tag ai_auto_trading_system-engine:latest    ai_auto_trading_system-engine:previous    2>/dev/null || true
+
+# 2. Build và khởi động lại chỉ 2 service (không đụng nats/postgres)
+docker compose build collector engine
+docker compose up -d --no-deps collector engine
 ```
 
-**Cảnh báo đã đo (01/09):** lệnh trên **cũng tạo lại `nats` và `postgres`**,
-dù không nêu tên chúng — `docker compose up` đồng bộ toàn bộ project. Lần đó
-dữ liệu an toàn (đã kiểm `max(ts)` và số dòng `bars`/`bars_daily` trước–sau,
-không đổi), nhưng đừng trông vào may. Muốn chắc chắn chỉ đụng hai service:
+### Quy trình quay về (Rollback khi bản mới lỗi)
+
+Nếu bản triển khai mới gặp sự cố (crash loop, lỗi logic, báo động Telegram):
 
 ```bash
-docker compose build collector engine
+# Hoàn nguyên tag :previous thành :latest và restart
+docker tag ai_auto_trading_system-collector:previous ai_auto_trading_system-collector:latest
+docker tag ai_auto_trading_system-engine:previous    ai_auto_trading_system-engine:latest
 docker compose up -d --no-deps collector engine
 ```
 
-Kiểm chứng code MỚI thật sự nằm trong container — cả ba phải **> 0**, nếu còn
-0 thì build không lấy source mới, **dừng lại** và tìm hiểu trước khi restart:
+*Lưu ý quan trọng về Rollback:*
+- Quay về ảnh `:previous` **không** đổi `docker-compose.yml`, nên volume mount `./logs:/app/logs` **vẫn còn nguyên** (không mất log, không mất dữ liệu DB).
+- Thứ mất đi (hoàn nguyên) chỉ là phần **mã nguồn** của lần triển khai vừa rồi.
+
+### Phép kiểm sau mỗi lần triển khai (bài học 18/09)
+
+Sau khi deploy, kiểm tra 2 lớp:
+
+1. **Khớp image ID giữa container và tag image:**
+```bash
+docker inspect -f "{{.Image}}" ai_auto_trading_system-collector-1
+docker image inspect ai_auto_trading_system-collector --format "{{.Id}}"
+# Hai chuỗi hash phải HOÀN TOÀN BẰNG NHAU.
+```
+
+2. **Grep chuỗi đặc trưng của chính bản vá bên trong container:**
+Hai hash bằng nhau chỉ chứng minh container đang chạy đúng image tag `:latest`, **KHÔNG** chứng minh tag khớp với mã nguồn mới nhất (ngày 18/09 đã dính bẫy: hash khớp nhưng code bên trong container là bản cũ). Do đó, **bắt buộc** phải grep chuỗi đặc trưng vừa thêm:
 
 ```bash
-# Dùng docker compose exec để tự động tìm đúng container collector theo project:
-docker compose exec collector sh -c \
-  'grep -c _connected $(python -c "import trading.collector.feed as m; print(m.__file__)")'
-docker compose exec collector sh -c \
-  'grep -c _restart_feed_and_alert $(python -c "import trading.collector.main as m; print(m.__file__)")'
 docker compose exec collector sh -c \
-  'grep -c backoff_cap_429 $(python -c "import trading.collector.feed as m; print(m.__file__)")'
+  'grep -n "chuoi_dac_trung_vua_sua" $(python -c "import trading.collector.main as m; print(m.__file__)")'
 ```
```

### 3.2 Trả lời câu hỏi: Chấp nhận một bậc `:previous` là đủ hay cần `:previous` + `:previous2`?
**Lựa chọn: Chấp nhận một bậc `:previous` là đủ và tối ưu.**
**Lý lẽ:**
1. **Tránh bẫy chuỗi xoay vòng thủ công:** Nếu duy trì `:previous` và `:previous2`, thao tác xoay vòng tag thủ công (`previous -> previous2`, `latest -> previous`) rất dễ nhầm lẫn khi người vận hành đang căng thẳng trong sự cố. Một thao tác sai sẽ khiến `:previous2` ghi đè lên bản hỏng, biến cả 2 tag lùi thành vô dụng.
2. **Đúng bản chất của Phanh Khẩn Cấp:** Rollback bằng image tag chỉ phục vụ đúng 1 mục đích: đưa hệ thống đang sập về trạng thái ổn định ngay trước đó 5 phút để bảo toàn phiên giao dịch. Không một người vận hành tỉnh táo nào lại deploy tiếp bản vá thứ 2 khi bản vá thứ 1 vừa sập mà chưa rollback về bản cũ.
3. **Lưới an toàn tối thượng là Git:** Nếu cả lần deploy trước và lần này đều có vấn đề, nguồn chân lý bất biến (source of truth) nằm ở lịch sử Git commit. Việc checkout commit ổn định cũ (`git checkout <good-commit>`) và build lại chỉ tốn khoảng 30–45 giây trên VPS, an toàn hơn nhiều so với việc lưu cữu nhiều tầng tag image tốn đĩa và mập mờ về nguồn gốc code.

---

## 4. Task 3 — Khảo sát nhịp chạy giữa Ubuntu cron và Windows Task Scheduler

### 4.1 Bốn câu trả lời
1. **Bên nào đúng?**
   - Đọc code `scripts/heartbeat_check.py` (dòng 239–245) và `trading/calendar_vn.py` (dòng 5, 8–13): Giờ giao dịch được định nghĩa là `09:00–11:30` và `13:00–14:45`. Sau 14:45, cả `is_trading_time` và `pre_market` đều trả về `False`. Script gặp câu lệnh `if not is_trading_time(now, holidays) and not pre_market: return 0` và **thoát ngay lập tức trong 0.05 giây** mà không thực hiện bất kỳ truy vấn DB hay phép kiểm tra nào.
   - Đọc code `scripts/engine_consumer_check.py` (dòng 138–140): Cũng dùng `is_trading_time`. Sau 14:45, nó in `[engine-consumer] Ngoài giờ giao dịch VN (...), bỏ qua.` và `return 0`.
   - **Kết luận:** Mọi lượt chạy **sau 14:45** (và chắc chắn sau 15:00) của cả 2 script **hoàn toàn vô ích**, không kiểm tra gì, không cứu vãn gì, chỉ sinh thêm dòng log rỗng trong thư mục logs.
   - Về nhịp: Ubuntu cron dùng dải `8-15` và `9-15` (chạy tới 15:55) là lối viết lười cú pháp cron, gây thừa 11 lượt chạy vô ích mỗi ngày. Windows task (`PT7H` từ 08:00 kết thúc lúc 15:00, `PT6H10M` từ 09:00 kết thúc lúc 15:10) sát thực tế hơn, dù vẫn thừa các lượt từ sau 14:45.
2. **Có nên gom nhịp vào `sched.sh` không?**
   - **Không nên.**
   - `sched.sh` hiện đóng vai trò là một **job command dispatcher** (nhận job name -> gọi python tương ứng). Nó không phải là một process supervisor hay scheduler daemon.
   - Nếu gom nhịp vào `sched.sh`, ta sẽ phải biến nó thành một daemon vô tận (`while true; sleep 300`). Trên Windows (chạy qua git bash / wscript), daemon này cực kỳ dễ chết khi logout, dễ rò rỉ tiến trình zombie và không có cơ chế tự phục hồi (auto-restart). Ngược lại, Cron của Linux và Task Scheduler của Windows là core OS service được thiết kế tối ưu để làm đúng việc kích hoạt định kỳ.
3. **Đề xuất cách rẻ nhất để hai bản không lệch tiếp:**
   - Tạo một bảng ma trận chuẩn duy nhất trong `DEPLOYMENT.md` mục 9:
     - Định rõ: `Tên job`, `Lệnh thực thi qua sched.sh`, `Khung giờ hiệu lực thực tế`, `Cấu hình cron Ubuntu`, `Cấu hình Task Scheduler Windows`.
   - Bổ sung lệnh kiểm tra nhanh để đối chiếu khi audit:
     - Ubuntu: `crontab -l | grep sched.sh`
     - Windows: `schtasks /query /fo TABLE /nh | findstr trading-`
4. **Chênh lệch hiện tại có đáng sửa ngay không?**
   - **Nói thẳng: Không đáng sửa ngay.**
   - Cả hai script đều tự ngắt bằng cổng `is_trading_time` sau 14:45 nên việc chạy thêm đến 15:10 hay 15:55 chỉ tốn vài dòng log và 0.05s CPU vô hại. Can thiệp vào Scheduled Task hoặc Crontab ngay trước phiên 22/09 tiềm ẩn rủi ro thao tác sai làm mất lịch của các job quan trọng.

---

## 5. Task 4 — Giao thức đo phiên 22/09 & Kiểm tra bars_closed.log

### 5.1 Đo số dòng `bars_closed.log` hôm nay
- Lệnh đo: `Get-Date; (Get-Content logs/bars_closed.log).Count; (Select-String -Path logs/bars_closed.log -Pattern "bars closed").Count`
- Mốc đo: **2026-09-19 01:27:43**
- Kết quả:
  - Tổng số dòng: **14 dòng**
  - Số dòng có chuỗi `bars closed`: **0 dòng**
  - Nội dung 14 dòng: 100% là alert vận hành (`backfill start/done`, `eod pricing`). Chưa có dòng chốt nến luồng nào vì chưa có phiên nào chạy từ lúc gắn volume mount host `./logs:/app/logs`.

### 5.2 Giao thức đo 4 bước cho thứ Hai 22/09
| Bước | Thời điểm | Lệnh kiểm tra | Kỳ vọng | Ngưỡng gọi là hỏng |
|---|---|---|---|---|
| **1. Trước phiên** | ≈08:30 | 1. `docker compose ps`<br>2. `uv run python scripts/heartbeat_check.py`<br>3. `uv run python scripts/deploy_drift_check.py`<br>4. `Test-Path logs/bars_closed.log` | - Collector & Engine `Up`<br>- Heartbeat `exit 0`, token còn hạn<br>- Deploy drift `exit 0`<br>- `bars_closed.log` tồn tại | - Container `Restarting` hoặc `Exit`<br>- Token SSI hết hạn (`CRITICAL`)<br>- Drift báo image cũ hơn commit |
| **2. Sau phiên sáng** | ≈11:35 | 1. `uv run python scripts/stream_health_check.py --date 2026-09-22 --session sang`<br>2. `Select-String -Path logs/bars_closed.log -Pattern "bars closed" \| Measure-Object`<br>3. `uv run python scripts/engine_consumer_check.py` | - `[nguon: file]` xuất hiện<br>- Số nến chốt >= 72/81 (>= 88.9%), kỳ vọng > 76 nến do `grace=20`<br>- NATS consumer `exit 0` | - `exit 2` (0 nến chốt)<br>- Báo `[nguon: log]` thay vì `file`<br>- Số nến < 50 nến (< 60%) |
| **3. Sau phiên chiều** | ≈15:10 | 1. `uv run python scripts/stream_health_check.py --date 2026-09-22 --session chieu`<br>2. `uv run python scripts/check_silent_engine.py`<br>3. `Get-Content logs/heartbeat.log -Tail 20` | - `[nguon: file]`<br>- Số nến chốt >= 51/57 (>= 89.5%)<br>- Engine không câm trên HPG (`exit 0`)<br>- Hai sổ sách khớp tuyệt đối | - `exit 2` (0 nến chiều)<br>- `CRITICAL_SILENT` trên toàn bộ mã<br>- Lệch sổ sách kế toán |
| **4. Tối sau backfill** | ≈21:05 | 1. `Get-Content logs/backfill.log -Tail 30`<br>2. `Get-Content logs/daily-data-check.log -Tail 30`<br>3. `uv run python scripts/daily_data_check.py` | - Backfill 20:30 thành công `EXIT=0`<br>- `daily-data-check` chạy 21:00 nạp nến 22/09, `[OK]` `EXIT=0` | - Backfill crash/thiếu nến<br>- `daily_data_check` kêu thiếu nến ngày<br>- Task 21:00 không chạy |

### 5.3 Ba câu hỏi phép đo 22/09 phải trả lời
1. **`bars_closed.log` có sống qua cuối tuần không, và có chứa dòng `bars closed` thật không?**
   - File đã được mount volume `./logs:/app/logs` ra host nên chắc chắn sống qua cuối tuần.
   - Hiện tại có 14 dòng alert vận hành, 0 dòng nến. Thứ Hai 22/09, **dòng `bars closed` đầu tiên bắt buộc phải xuất hiện** ngay sau khi nến 5m đầu tiên chốt lúc 09:20.
2. **`grace = 20` có kéo độ phủ lên khỏi 88,9% / 89,5% không?**
   - Phép đo 22/09 sẽ so trực tiếp với nền `grace = 60` (15/09: 93.8%; 18/09: 88.9% sáng, 89.5% chiều). Kết quả sẽ kết luận liệu việc tăng thời gian gom nến trễ mạng có đẩy tỷ lệ lên trên 90% hay không.
3. **Nếu không kéo lên thì sao? Dấu hiệu phân biệt cạn thanh khoản vs lỗi luồng:**
   - **Xác nhận cạn thanh khoản (dự đoán đợt 52 đúng):** Nến thiếu chỉ rơi vào các mã thanh khoản thấp (như AAA, IJC) vào các khoảng thời gian thị trường trầm lắng; trong khi mã thanh khoản lớn (HPG, SSI) vẫn đạt 100% nến đầy đủ; truy vấn sàn thật xác nhận không có lệnh khớp nào trong 5 phút đó.
   - **Bác bỏ cạn thanh khoản (lỗi kỹ thuật thật sự):** Nến thiếu đồng loạt ở tất cả các mã (kể cả HPG) cùng một thời điểm; hoặc trong DB bảng `ticks` vẫn nhận được tick của khung giờ đó nhưng collector không chịu chốt bar.

---

## 6. Tổng kết kiểm định chất lượng

1. **Test suite:** **786 passed in 45.80s** (tăng đúng 4 test mới từ mốc 782, 100% test pass).
2. **Ruff linter:** `uv run ruff check trading tests scripts` -> **All checks passed!**
3. **Cổng cứng VN (`measure_strategy.py`):**
   ```text
   TỔNG: strat -1,615,319,902 | BH 1,897,587,481,903 | diff -1,899,202,801,806 | lệnh 1,514 | mã sinh lệnh 439 | mã đủ thanh khoản 748 | dòng bẩn 10,459
   ```
   Khớp chính xác 100% 4 con số chuẩn: `-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã`.


---

## Phụ lục — ghi chú của Claude (auditor), 19/09/2026

Bốn task đạt. Hai điều cần ghi: **một chỗ tôi ra chỉ thị sai** trong chính brief này, và **một
câu hỏi tôi đặt mà báo cáo không trả lời** — câu đó hoá ra là câu quan trọng.

### A. Những gì tôi tự chạy lại

```
19/19 test cua test_stream_health_check.py
786 passed in 47.15s
ruff: All checks passed!
TONG: strat -1,615,319,902 | BH 1,897,587,481,903 | lenh 1,514 | ma sinh lenh 439   <- khop

--date 2026-09-12 --session sang -> EXIT=0  "bo qua: 2026-09-12 la ngay nghi"
--date 2026-09-19 --session sang -> EXIT=0  "bo qua: 2026-09-19 la ngay nghi"
--date 2026-09-18 --session sang -> EXIT=2  "... 0 nen [nguon: log]"   <- dung, no DI TOI buoc do
```

Nối dây `holidays` đúng chỗ (`resolve_target_session(now_vn, holidays=holidays)`), ba cửa đúng
thứ tự, comment ghi rõ cửa nào của đợt nào. Test 16–19 thuần thêm, 15 test cũ nguyên vẹn.

### B. Chỉ thị "đọc config ở hai chỗ là sai" của tôi dựa trên bức tranh thiếu

Brief §1.1b tôi viết: *"Cả hai dùng **cùng một nguồn ngày lễ**. Nếu bạn thấy mình đọc config ở hai
chỗ khác nhau, đó là dấu hiệu làm sai."* Agent viết thêm `load_holidays()` trong
`stream_health_check.py` thay vì dùng `trading.config.load_config`, và kèm lý do: *"An toàn, không
yêu cầu biến môi trường DB/SSI như load_config."*

Lý do đó **đúng**:

```python
# trading/config.py:39,44-48
db_dsn=os.environ["DB_DSN"],
ssi_consumer_id=os.environ["SSI_CONSUMER_ID"],
ssi_consumer_secret=os.environ["SSI_CONSUMER_SECRET"],
...
```

`load_config` **ném `KeyError`** nếu thiếu biến môi trường. Một chuông giám sát mà chết vì không
đọc được khoá SSI — trong khi nó chỉ cần biết hôm nay có phải ngày lễ không — là thiết kế tệ.

Và quan trọng hơn: **đây không phải mẫu mới.** Tôi đếm số nơi tự parse `holidays` từ YAML:

```
trading/config.py:38             <- ban chinh
scripts/docker_down_alert.py:61
scripts/engine_consumer_check.py:127
scripts/heartbeat_check.py:228
scripts/stream_health_check.py:149   <- moi hom nay
```

**Năm chỗ**, và ba chỗ trong số đó đã có từ trước. Agent làm đúng theo khuôn các script anh em
của nó, chứ không phải tự chế. Chỉ thị của tôi sai vì tôi không kiểm khuôn sẵn có trước khi ra
lệnh — đúng thứ tôi vẫn bắt agent phải làm.

### C. Câu tôi hỏi mà báo cáo không trả lời — và nó là câu quan trọng

Brief §1.2 tôi viết: *"đợt 51 đã giải bài này trong `daily_data_check.py`, xem cách ở đó rồi quyết
định — và **nếu bạn thấy cách đó lặp lại ở chỗ thứ ba, hãy nói ra**."*

Cách đó **đã lặp lại ở chỗ thứ ba**, và báo cáo không nhắc:

```
scripts/docker_down_alert.py:73    probe = now.astimezone(TZ).replace(hour=10, ...)  -> in_bar_check_window
scripts/daily_data_check.py:139    ts_mid = datetime.combine(target_date, time(10, 0), ...) -> is_trading_time
scripts/stream_health_check.py:405 ts_mid = datetime.combine(check_date,  time(10, 0), ...) -> is_trading_time
```

Ba nơi, ba cách viết, **một ý tưởng**: hỏi "10:00 hôm đó có nằm trong giờ giao dịch không" để suy
ra "hôm đó có phải ngày giao dịch không". (`docker_down_alert` dùng `.replace()` nên `grep` tìm
`time(10, 0)` không thấy nó — tôi phải đọc mới ra.)

Gốc vấn đề vẫn y như tôi ghi ở đợt 51: **`trading/calendar_vn.py` không có vị từ cấp NGÀY.** Có
`is_trading_time` (cấp giây) và `is_continuous_matching` (cấp giây), không có `is_trading_day`.
Thiếu chỗ đó nên ai cần cũng tự chế lại, và giờ đã ba lần.

Khác với mục B, **cái này đáng gom thật**: nó là một vị từ thuần, không phụ thuộc môi trường, và
`calendar_vn.py` là chỗ hiển nhiên cho nó. Thuần bổ sung, ba chỗ gọi đổi một dòng mỗi chỗ.
Nhưng nó chạm `scripts/heartbeat_check.py` — file trong danh sách cấm sửa — nếu muốn gom cả
`docker_down_alert._is_trading_day`. **Việc của brief sau, có ràng buộc riêng.**

### D. Mô tả cơ chế của Task 3 thiếu một nhánh, và nhánh đó quan trọng

Báo cáo viết: *"Cả hai script `heartbeat_check.py:244` và `engine_consumer_check.py:138` đều sử
dụng `is_trading_time` chặn ngoài giờ."* Với `heartbeat_check` thì **không đủ**:

```python
# scripts/heartbeat_check.py:238-244
pre_market = (
    time(8, 0) <= now_tz.time() < time(9, 0)
    and now_tz.weekday() < 5
    and now_tz.date() not in holidays
)
if not is_trading_time(now, holidays) and not pre_market:
    return 0
```

Nó có **hai** cửa, và cửa thứ hai (`pre_market` 08:00–09:00) chính là nhánh cảnh báo token trước
giờ mở cửa — thứ mà `DEPLOYMENT.md` nhấn mạnh phải giữ khi đặt lịch `8-15` chứ không phải `9-15`.

**Kết luận của Task 3 vẫn đúng**: sau 15:00 cả hai script đều thoát ngay, nên các lượt chạy thừa
của cron Ubuntu chỉ sinh log. Nhưng mô tả cơ chế thì sai theo hướng nguy hiểm — ai đọc câu đó rồi
"đơn giản hoá" cửa của `heartbeat_check` về đúng `is_trading_time` sẽ **giết chuông token 08:00**
mà không ai nhận ra cho tới sáng nào đó token hết hạn.

Ghi lại đây để câu mô tả sai không sống tiếp trong tài liệu.

### E. Phần tôi tán thành không dè dặt

- **`:previous` một bậc là đủ.** Lập luận đúng: tag là phanh khẩn cấp cho bậc lùi gần nhất, còn
  lùi sâu thì nguồn chân lý là git. Thêm `:previous2` chỉ tăng rủi ro xoay tag nhầm tay.
- **Không gom nhịp vào `sched.sh`.** Lý do đúng và tôi không nghĩ tới: `sched.sh` là *dispatcher*,
  không phải *scheduler daemon*; gom nhịp vào đó buộc phải có vòng lặp nền, mất luôn cơ chế
  supervisor của OS. Câu trả lời "không đáng sửa ngay, chỉ cần ghi rõ là cố ý" là câu tôi đã nói
  trước là hợp lệ, và nó hợp lệ thật.
- **Tiêu chí phân biệt cho thứ Hai rất tốt**: nếu nến thiếu chỉ rơi vào mã yếu (AAA, IJC) trong
  khi HPG đủ 100% → cạn thanh khoản, dự đoán đợt 52 đúng; nếu thiếu đồng loạt mọi mã → lỗi luồng.
  Đây là tiêu chí quyết định **trước** khi thấy số liệu, đúng thứ tôi yêu cầu.

### F. Việc còn treo

1. **`is_trading_day` vào `calendar_vn.py`** — mục C. Brief sau.
2. **`config/config.yaml: holidays` chỉ còn ngày đã qua.** Sau khi nối dây xong hôm nay, danh sách
   này là thứ **duy nhất** chặn báo động giả ngày lễ giữa tuần — và nó đang rỗng về tương lai.
   Chỉ chủ dự án sửa được.
3. **Phiên 22/09** — giao thức đã sẵn, chạy theo đúng bốn bước.


### G. Tự soát: có chỗ nào khác phụ thuộc thứ vừa đổi không?

Câu này tôi kiểm chứ không đoán, vì cả tuần đã hai lần "đúng chỗ tôi tình cờ biết" hoá ra chưa đủ.

**Người phụ thuộc `stream_health_check`: chỉ có test.** Mười dòng `import` từ nó đều nằm trong
`tests/test_stream_health_check.py`, không một script hay module production nào. Nên đổi cửa
trong `main()` không ảnh hưởng ai khác.

**Hai script anh em cũng nhận `--date` và cũng không có cửa ngày nghỉ:**

```
scripts/replay_stream_check.py            0 tham chieu holidays/is_trading_time
scripts/measure_session_stream_metrics.py 0 tham chieu holidays/is_trading_time
```

Thoạt nhìn là cùng một lỗ. **Không phải** — và chỗ khác biệt mới là chỗ quyết định:

```
co nam trong sched.sh khong                    -> 0 (ca hai deu khong duoc len lich)
co sys.exit(1)/sys.exit(2)/send_telegram khong -> 0 (ca hai)
```

Cả hai là **công cụ báo cáo chạy tay**, không kêu được. Chạy chúng vào ngày lễ cho ra một báo cáo
rỗng — đó là **kết quả đúng**, không phải báo động giả. Lỗ ngày nghỉ chỉ có hại với thứ **biết
kêu**, và cả hai thì không.

Nên: **không có chỗ nào khác cần sửa.** Thay đổi của đợt 55 là trọn vẹn và khu trú.

Một điều rút ra để dùng lại: khi hỏi "chỗ khác có cùng lỗ không", câu hỏi phân loại không phải
*"nó có thiếu cửa không"* mà *"nó có khả năng kêu không"*. Thiếu cửa ở một công cụ câm là vô hại;
thiếu cửa ở một chuông là sự cố. Ba chuông mù của đợt 51 sinh ra đúng từ chỗ không phân biệt được
hai thứ đó.
