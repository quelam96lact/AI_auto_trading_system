# Báo cáo Đợt 47 — Gắn chuông luồng vào lịch, và triển khai grace = 20

- **Thời điểm thực thi:** 18/09/2026, 10:45 AM (Giờ VN).
- **Người thực thi:** Gemini Flash 3.8.
- **Người lập kế hoạch & kiểm toán:** Claude.
- **Cam kết:** Không commit, không push. Không tự ý sửa ngoài phạm vi cho phép.

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

### 1.2. `git status --short`
```text
 M AGENTS.md
 M CLAUDE.md
 M README.md
 M scripts/run_hidden.vbs
 M scripts/sched.sh
?? "Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md"
?? docs/README_VPS_UBUNTU.md
```
*(Ghi chú: AGENTS.md, CLAUDE.md, README.md và các file untracked là tài liệu từ các tác vụ trước đó của người dùng, được giữ nguyên vẹn).*

### 1.3. `git diff scripts/sched.sh`
```diff
diff --git a/scripts/sched.sh b/scripts/sched.sh
index c5c0337..0d44ccf 100644
--- a/scripts/sched.sh
+++ b/scripts/sched.sh
@@ -9,6 +9,7 @@
 #   scripts/sched.sh deploy-drift
 #   scripts/sched.sh engine-cam
 #   scripts/sched.sh engine-consumer
+#   scripts/sched.sh stream-health
 #
 # Cong Docker nam trong run_if_docker_up.sh — xem file do.
 
@@ -69,8 +70,13 @@ case "${1:-}" in
     exec "$RUN" engine-consumer.log engine-consumer \
       uv run python scripts/engine_consumer_check.py
     ;;
+  stream-health)
+    shift || true
+    exec "$RUN" stream-health.log stream-health \
+      uv run python scripts/stream_health_check.py "$@"
+    ;;
   *)
-    echo "dung: $0 {heartbeat|daily-check|backfill|deploy-drift|engine-cam|engine-consumer}" >&2
+    echo "dung: $0 {heartbeat|daily-check|backfill|deploy-drift|engine-cam|engine-consumer|stream-health}" >&2
     exit 2
     ;;
 esac
```

---

## 2. Task 1 — Gắn job `stream-health` vào `scripts/sched.sh`

Đã thêm job thứ 7 `stream-health` theo đúng cấu trúc của `engine-consumer)` trong `scripts/sched.sh`, hỗ trợ truyền cờ tuỳ chọn thông qua `shift || true` và `"$@"`. Đồng thời cập nhật chú thích danh sách job hỗ trợ trong `scripts/run_hidden.vbs`.

### 2.1. Năm tiêu chí kiểm chứng bằng dữ liệu THẬT (§1.2)

1. **Đối chứng dương (phiên hỏng 16/09):**
   - Lệnh: `uv run python scripts/stream_health_check.py --date 2026-09-16 --session sang`
   - Output stderr: `dung: phien sang ngay 2026-09-16 khong co dong 'bars closed' nao tu luong thoi gian thuc (0 nen)`
   - Exit code: **`2`** (CRITICAL).
   - Lệnh cho phiên chiều: `uv run python scripts/stream_health_check.py --date 2026-09-16 --session chieu`
   - Output stderr: `dung: phien chieu ngay 2026-09-16 khong co dong 'bars closed' nao tu luong thoi gian thuc (0 nen)`
   - Exit code: **`2`** (CRITICAL).
   - **Kết luận:** **ĐỐI CHỨNG DƯƠNG ĐẠT 100% (EXIT 2)**. Công cụ bắt chính xác phiên luồng chết âm thầm.

2. **Đối chứng âm (phiên tốt 15/09):**
   - Sáng: `OK: phien sang ngay 2026-09-15 co 76 lan chot nen tu luong thoi gian thuc.` (`ExitCode=0`)
   - Chiều: `OK: phien chieu ngay 2026-09-15 co 53 lan chot nen tu luong thoi gian thuc.` (`ExitCode=0`)
   - Tổng cộng: **129 nến** chốt từ luồng thời gian thực.
   - **Kết luận:** **ĐỐI CHỨNG ÂM ĐẠT 100% (EXIT 0)**.

3. **Phiên mất 40% (17/09):**
   - Sáng: `OK: phien sang ngay 2026-09-17 co 29 lan chot nen tu luong thoi gian thuc.` (`ExitCode=0`)
   - Chiều: `OK: phien chieu ngay 2026-09-17 co 53 lan chot nen tu luong thoi gian thuc.` (`ExitCode=0`)
   - Tổng cộng: **82 nến** chốt từ luồng (56 nến còn lại do backfill bù).
   - **Kết luận:** Script trả `exit 0` vì ngưỡng hiện tại là "0 nến từ luồng = CRITICAL". Script **không** bắt được tình trạng suy giảm một phần (đây là giới hạn đã biết của ngưỡng nhị phân hiện tại; không tự ý thêm ngưỡng mềm khi chưa có phân phối nền).

4. **Chạy qua `sched.sh stream-health` (không gọi trực tiếp script):**
   - Lệnh: `bash scripts/sched.sh stream-health --date 2026-09-16 --session sang` -> `ExitCode=2`.
   - Lệnh: `bash scripts/sched.sh stream-health --date 2026-09-15 --session sang` -> `ExitCode=0`.
   - Lệnh: `bash scripts/sched.sh stream-health` (phiên sáng 18/09 hiện tại) -> `ExitCode=0`.
   - Log ghi nhận tại `logs/stream-health.log`:
     ```text
     2026-09-18 10:37:15 stream-health start
     dung: phien sang ngay 2026-09-16 khong co dong 'bars closed' nao tu luong thoi gian thuc (0 nen)
     EXIT=2
     2026-09-18 10:37:24 stream-health start
     OK: phien sang ngay 2026-09-15 co 76 lan chot nen tu luong thoi gian thuc.
     EXIT=0
     2026-09-18 10:37:34 stream-health start
     OK: phien sang ngay 2026-09-18 co 45 lan chot nen tu luong thoi gian thuc.
     EXIT=0
     ```
   - Kiểm tra `sched.sh` không tham số và tham số sai:
     `dung: scripts/sched.sh {heartbeat|daily-check|backfill|deploy-drift|engine-cam|engine-consumer|stream-health}` (ExitCode=2).

5. **Test suite chuyên biệt:**
   - Chạy `uv run pytest tests/test_stream_health_check.py -v`:
   - Kết quả: **5 passed in 0.17s** (nguyên vẹn 100%, không sửa bất kỳ dòng assert nào).

### 2.2. Lệnh đăng ký Scheduled Task soạn sẵn (§1.3)

> **Cảnh báo:** Agent **KHÔNG** tự chạy lệnh đăng ký Scheduled Task này theo đúng quy định phân quyền của brief. Chủ dự án mở PowerShell để thực thi:

```powershell
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument '//B //Nologo "D:\My_Vault_Obsidian\Project\AI_auto_trading_system\scripts\run_hidden.vbs" stream-health'

$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At "15:10"

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName "trading-stream-health" `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Giam sat luong SSI thoi gian thuc luc 15:10 moi ngay lam viec (Brief dot 47)"
```

---

## 3. Task 2 — Đo phiên 18/09 (§1.1 & §1.2)

- **Trạng thái:** **CHƯA LÀM TOÀN BỘ — chưa tới 15:05 ngày 18/09/2026** (hiện tại mới 10:45 sáng, phiên chiều 13:00 - 15:05 chưa diễn ra).
- **Số liệu sơ bộ phiên sáng 18/09 (09:00 - 10:40 Giờ VN):**
  - Số nến chốt từ luồng: **47 nến** (45 lần `bars closed`).
  - Số nến trong bảng `bars` DB: **50 nến** (AAA: 16, HPG: 17, IJC: 17).
  - Phân bố `lag_ms`:
    - Min: 3,439.30 ms
    - P25: 3,554.72 ms
    - Trung vị (P50): 18,456.24 ms
    - P75: 45,462.93 ms
    - P90: 77,746.25 ms
    - P95: 86,226.02 ms
    - Max: 89,447.40 ms
    - Số lần `lag_ms > 60s`: 11/45 lần (24.4%).
  - Phân bố `late_ms`:
    - Số lượng: 9 snapshot đến muộn.
    - Trung vị: 447.21 ms
    - P90: 1,054.08 ms
    - Max: 3,424.30 ms
  - Snapshots mỗi nến:
    - Min: 1 | Trung vị: 9.0 | Max: 71
    - Tỷ lệ nến chỉ có 1 snapshot: 2/47 nến (4.3%).
  - Chuông im lặng (120s):
    - Xuất hiện **1 lần** lúc `02:02:10Z` (tức **09:02:10 Giờ VN**).
    - **Nguyên nhân:** Container collector hiện tại là ảnh cũ (chưa build bản vá đợt 46 dùng `is_continuous_matching`, sẽ được cập nhật ở Task 3 sau 15:00).

---

## 4. Task 3 — Triển khai `grace = 20` (§3.1 & §3.2)

- **Trạng thái:** **CHƯA LÀM — phải sau 15:00 theo §3.2**.
- **Tuân thủ ràng buộc:** Không chạm vào container trong giờ giao dịch để bảo toàn phiên nền cuối cùng của `grace = 60`.
- **Bước chuẩn bị đã hoàn thành:**
  - Đã lưu tag rollback an toàn:
    `docker tag sha256:9c66a1dc8ec21c5ed860490fbd0556a9da4cfcd70556d77eaa4ce6ad0ac65a3e dot47-rollback-collector:pre`
  - Image collector hiện tại: `sha256:9c66a1dc8ec21c5ed860490fbd0556a9da4cfcd70556d77eaa4ce6ad0ac65a3e`. Container `ai_auto_trading_system-collector-1` vẫn đang chạy ổn định (`Up 3 hours`).

---

## 5. Ba dòng kiểm định bắt buộc

1. **Test suite:** **755 passed in 45.01s** (khớp chính xác mốc 755).
2. **Ruff check:** Clean 100% (`All checks passed!`).
3. **Cổng cứng VN:** Khớp tuyệt đối 100% từng chữ số (`exit 0`):
   ```text
   TỔNG: strat -1,615,319,902 | BH 1,897,587,481,903 | diff -1,899,202,801,806 | lệnh 1,514 | mã sinh lệnh 439 | mã đủ thanh khoản 748 | dòng bẩn 10,459
   ```
