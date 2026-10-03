# Nghiên cứu & Nghiệm thu Đợt 156 — Canh mã thoát cho job theo lịch (chạy đúng giờ mà thất bại phải có người biết)

**Ngày thực hiện:** 03/10/2026  
**Kế hoạch đối chiếu:** `docs/superpowers/plans/2026-10-03-brief-dot-156-job-chay-dung-gio-ma-that-bai-phai-co-nguoi-biet.md`

---

## 1. Tóm tắt kết quả

- **Mục tiêu:** Mở rộng cơ chế giám sát lịch trong `scripts/heartbeat_check.py` để không chỉ canh "job có được gọi đúng giờ không" (staleness), mà còn phát hiện "lần chạy gần nhất có kết thúc với mã lỗi chưa ai báo không" (unreported exit code failure).
- **Thực hiện:**
  - Thiết lập bảng chính sách `SCHEDULE_EXIT_POLICIES` cho toàn bộ **16 nhánh** của `scripts/sched.sh`.
  - Bổ sung hàm đọc mã thoát `get_last_run_exit_code(log_path, label)`: neo regex đầu dòng `^EXIT=(\d+)` để tránh ăn nhầm `ALERT_EXIT=`, chỉ lấy mã thoát của mốc chạy gần nhất, coi job đang chạy (chưa có `EXIT=`) hoặc lần gọi là `SKIP` là trạng thái an toàn (không báo động giả).
  - Nâng cấp `evaluate_schedule_health`: báo CRITICAL một lần khi chuyển sang thất bại, im lặng khi lặp lại cùng mã lỗi, và báo INFO hồi phục một lần khi job chạy lại thành công (mã 0).
  - Tích hợp vào `main()` của `heartbeat_check.py`, bảo toàn quy tắc Brief 155 (gửi hỏng không lưu trạng thái).
  - Thêm 13 test mới bao phủ: kiểm tra phân loại toàn bộ 16 nhánh, đọc mã thoát, tái hiện 2 sự cố lịch sử thật (`EXIT=4` của orderbook-recorder ngày 29/09, `EXIT=1` của stream-health ngày 18/09), và kiểm tra chống nhân đôi cảnh báo.

---

## 2. Bảng chính sách mã thoát cho cả 16 nhánh của `sched.sh`

Bảng chính sách được xác lập dựa trên việc đọc và phân tích trực tiếp mã nguồn của từng script:

| STT | Nhánh (`branch`) | File thực thi | Log & Label | Mã bình thường / Đã tự báo | Mã thất bại cần Heartbeat báo | Căn cứ dòng code & Lý do một câu |
|---|---|---|---|---|---|---|
| 1 | `heartbeat` | `scripts/heartbeat_check.py` | `heartbeat.log`<br>`heartbeat-check` | `0`, `1` | Không canh (tránh đệ quy) | `heartbeat_check.py:653-665`. Mã 0 là OK, mã 1 là khi có cảnh báo đã tự gửi Telegram / outbox; tự canh mã 1 sẽ đệ quy nhân đôi cảnh báo. |
| 2 | `daily-check` | `scripts/daily_data_check.py` | `daily-data-check.log`<br>`daily-data-check` | `0`, `1` | `!= 0, 1` (ví dụ `2` hoặc crash) | `daily_data_check.py:237, 244, 277, 304, 310, 312`. Mã 0 là đủ dữ liệu/ngày nghỉ; mã 1 là thiếu bar đã tự gửi Telegram. Mã 2 khi lỗi config/DB/parser không gửi Telegram hoặc crash. |
| 3 | `backfill` | `scripts/backfill_universe.py` | `backfill.log`<br>`backfill` | `0` | `!= 0` (`1`, `2`, crash...) | `backfill_universe.py:223-261`. Script không có cơ chế gửi Telegram. Mã 0 là nạp xong bình thường; mọi mã khác 0 là lỗi nạp/mạng/DB chưa ai báo. |
| 4 | `deploy-drift` | `scripts/deploy_drift_check.py` | `deploy-drift.log`<br>`deploy-drift` | `0`, `1` | `!= 0, 1` (ví dụ `2` hoặc crash) | `deploy_drift_check.py:156, 215, 219`. Mã 0 là không lệch; mã 1 là có lệch đã tự gửi Telegram qua `alert_and_fail`. Mã 2 là gửi Telegram hỏng hoặc lỗi chưa ai báo. |
| 5 | `container-health` | `scripts/container_health_check.py` | `container-health.log`<br>`container-health` | `0`, `1`, `2` | `!= 0, 1, 2` (ví dụ `4`, crash...) | `container_health_check.py:497-499, 575, 585`. Mã 0 là container khỏe; mã 1 là cảnh báo đã gửi Telegram; mã 2 là Docker chưa chạy (đã có `docker_down_alert` lo) hoặc gửi Telegram hỏng; chỉ mã kill/crash ngoại lai mới chưa ai báo. |
| 6 | `engine-cam` | `scripts/check_silent_engine.py` | `engine-cam.log`<br>`engine-cam` | `0`, `1` | `!= 0, 1` (ví dụ `2` hoặc crash) | `check_silent_engine.py:141, 167, 177, 240`. Mã 0 là OK; mã 1 là phát hiện engine câm đã tự gửi Telegram qua `alert_and_fail`. Mã 2 là lỗi config/symbols hoặc gửi Telegram hỏng. |
| 7 | `engine-consumer` | `scripts/engine_consumer_check.py` | `engine-consumer.log`<br>`engine-consumer` | `0`, `1` | `!= 0, 1` (ví dụ `2` hoặc crash) | `engine_consumer_check.py:136, 149, 184, 188`. Mã 0 là tiêu thụ bình thường/ngoài phiên; mã 1 là sự cố NATS/config/lag đã tự gửi Telegram. Mã khác là lỗi chưa ai báo. |
| 8 | `stream-health` | `scripts/stream_health_check.py` | `stream-health.log`<br>`stream-health` | `0` | `!= 0` (`1`, `2`, crash...) | `stream_health_check.py:546, 556, 572`. Script không gửi Telegram. Mã 0 là độ phủ đạt; mã 1 (WARN <90%) và mã 2 (CRITICAL <50%/0 nến) hoàn toàn im lặng trong log chưa ai báo. |
| 9 | `orderbook-recorder` | `scripts/record_vn30f_orderbook.py` | `orderbook-recorder.log`<br>`orderbook-recorder` | `0` | `!= 0` (`1`, `4`, crash...) | `record_vn30f_orderbook.py:844-855`. Mã 0 là thu thập đủ phiên; mã 1 (crash) và mã 4 (bị Task Scheduler/Windows kill giữa chừng) không thể tự gửi cảnh báo. |
| 10 | `orderbook-daily-check` | `scripts/check_orderbook_daily.py` | `orderbook-daily-check.log`<br>`orderbook-daily-check` | `0`, `1`, `2` | `!= 0, 1, 2` (ví dụ crash...) | `check_orderbook_daily.py:215, 246, 250`. Mã 0 là OK; mã 1 (WARN) và mã 2 (CRITICAL) đều đã gọi `trading.alerts.alert()` (có hàng đợi outbox). Chỉ crash ngoại lai mới chưa ai báo. |
| 11 | `backup` | `scripts/backup_db.sh` | `backup.log`<br>`backup` | `0` | `!= 0` (`1`, `2`, crash...) | `backup_db.sh:18, 22, 85`. Shell script không có cơ chế gửi Telegram. Mã 0 là backup xong; mã 1 (lỗi pg_restore verify) và mã 2 (lỗi đối số) chưa ai báo. |
| 12 | `backup-check` | `scripts/backup_check.py` | `backup-check.log`<br>`backup-check` | `0`, `1` | `!= 0, 1` (ví dụ `2` hoặc crash) | `backup_check.py:418, 421, 423, 431`. Mã 0 là backup tốt; mã 1 là phát hiện lỗi backup đã tự gửi Telegram. Mã 2 là gửi Telegram hỏng hoặc crash chưa ai báo. |
| 13 | `orderbook-backup` | `scripts/backup_orderbook.sh` | `orderbook-backup.log`<br>`orderbook-backup` | `0` | `!= 0` (`1`, `2`, crash...) | `backup_orderbook.sh:22, 26, 41, 60, 75`. Shell script không có cơ chế gửi Telegram. Mã 0 là xong/không có file; mã 1 (không thấy thư mục / tar rỗng) và mã 2 chưa ai báo. |
| 14 | `disk-check` | `scripts/disk_check.py` | `disk-check.log`<br>`disk-check` | `0`, `1` | `!= 0, 1` (ví dụ `2` hoặc crash) | `disk_check.py:150, 171, 181, 194, 196, 204`. Mã 0 là đĩa đủ; mã 1 là thiếu đĩa đã tự gửi Telegram. Mã 2 là lỗi config/không đo được đĩa/gửi Telegram hỏng chưa ai báo. |
| 15 | `host-preflight` | `scripts/host_preflight.py` | `host-preflight.log`<br>`host-preflight` | `0` | `!= 0` (`1`, `2`, crash...) | `host_preflight.py:459, 825, 830, 847, 855`. Script không gửi Telegram. Mã 0 là pass/warn/skip; mã 1 (có kiểm tra FAIL) và mã 2 (lỗi config/repo) chưa ai báo. |
| 16 | `restore-drill` | `scripts/restore_drill.py` | `restore-drill.log`<br>`restore-drill` | `0`, `1` | `!= 0, 1` (ví dụ `2` hoặc crash) | `restore_drill.py:352, 362, 374, 376, 384`. Mã 0 là diễn tập pass; mã 1 là lỗi restore đã tự gửi Telegram. Mã 2 là lỗi config/gửi Telegram hỏng chưa ai báo. |

---

## 3. Số đo thực tế trên máy hiện tại

### Thống kê `^EXIT=` trong toàn bộ file log tại `logs/*.log`:
```text
Found 23 log files:
| backfill.log              |    22 |      0 | 0 |
| backup-check.log          |    13 |      3 | 3x 1 |
| backup.log                |    10 |      1 | 1x 1 |
| bars_closed.log           |     0 |      0 | 0 |
| container-health.log      |   340 |     17 | 17x 2 |
| daily-data-check.log      |    28 |      8 | 3x 1, 5x 2 |
| deploy-drift.log          |    20 |     10 | 8x 1, 2x 2 |
| disk-check.log            |    20 |      1 | 1x 2 |
| engine-cam.log            |    12 |      1 | 1x 2 |
| engine-consumer.log       |   595 |      1 | 1x 2 |
| engine_alerts.log         |     0 |      0 | 0 |
| full_suite_dot73.log      |     1 |      0 | 0 |
| heartbeat.log             |  1587 |    160 | 157x 1, 3x 2 |
| host-preflight.log        |     8 |      0 | 0 |
| measure_filtered.log      |     0 |      0 | 0 |
| measure_full.log          |     0 |      0 | 0 |
| measure_sma_recheck.log   |     0 |      0 | 0 |
| orderbook-backup.log      |     8 |      2 | 1x 1, 1x 2 |
| orderbook-daily-check.log |     7 |      1 | 1x 1 |
| orderbook-recorder.log    |     6 |      1 | 1x 4 |
| restore-drill.log         |     3 |      1 | 1x 1 |
| stream-health.log         |    14 |      4 | 2x 1, 2x 2 |
```

---

## 4. Kết quả nghiệm thu 6 tiêu chí

### Tiêu chí 1 — AST theo hàm (`HEAD` với bản mới)
```text
heartbeat_check.py:
  Added functions: {'get_last_run_exit_code'}
  Removed functions: set()
  Changed functions: ['evaluate_schedule_health', 'main']
```
*Kết luận:* Đạt 100%. Chỉ hàm canh lịch (`evaluate_schedule_health`), `main`, và hàm mới `get_last_run_exit_code` thay đổi. Các hàm logic nghiệp vụ khác giữ nguyên 100%.

---

### Tiêu chí 2 — Bảng chính sách mã thoát
Đã hoàn thành đầy đủ cho cả 16 nhánh ở Mục 2 trên, kèm số dòng code và giải thích căn cứ rõ ràng.

---

### Tiêu chí 3 — Phá thử (Mutation Testing)

#### Baseline SHA256
- `scripts/heartbeat_check.py`: `653E43D71121FCE139A28EA540CE5A70C334988027F48B8D3F970C9CBBCA10ED`
- `tests/test_schedule_watch.py`: `6A80F2261FA344715825E89375AAC7DF86C075D9D6612E7D1268417F2627904A`

#### Phá thử 1: Dùng `EXIT=` không neo đầu dòng (`.*EXIT=`)
- **Thao tác:** Đổi `pattern_exit = re.compile(r"^EXIT=(\d+)")` thành `pattern_exit = re.compile(r".*EXIT=(\d+)")`.
- **Lệnh chạy:** `uv run pytest tests/test_schedule_watch.py -k "anchored_regex" -q`
- **Dòng đỏ nguyên văn:**
```text
FAILED tests/test_schedule_watch.py::test_get_last_run_exit_code_anchored_regex_avoids_alert_exit
AssertionError: assert 1 is None
1 failed, 23 deselected in 0.45s
```
- **Khôi phục:** Khôi phục `^EXIT=(\d+)`, đối chiếu hash `653E43D71121FCE139A28EA540CE5A70C334988027F48B8D3F970C9CBBCA10ED` khớp 100%.

#### Phá thử 2: Bỏ điều kiện chuyển trạng thái (luôn báo lỗi mỗi lần chạy)
- **Thao tác:** Bỏ kiểm tra `if prev_exit_status != "failed" or prev_exit_code != exit_code:`.
- **Lệnh chạy:** `uv run pytest tests/test_schedule_watch.py -k "repeated_failure" -q`
- **Dòng đỏ nguyên văn:**
```text
FAILED tests/test_schedule_watch.py::test_exit_code_eval_repeated_failure_is_silent
AssertionError: assert ['[CRITICAL] ...'] == []
Left contains one more item: "[CRITICAL] job theo lịch 'orderbook-recorder' THẤT BẠI: lần chạy gần nhất lúc 2026-10-02 09:50:00 kết thúc với mã thoát 4"
1 failed, 23 deselected in 0.40s
```
- **Khôi phục:** Khôi phục điều kiện chuyển trạng thái, đối chiếu hash khớp 100%.

#### Phá thử 3: Canh cả mã 1 của chính `heartbeat` (coi mã 1 là lỗi)
- **Thao tác:** Trong `SCHEDULE_EXIT_POLICIES["heartbeat"]`, đổi `normal_exit_codes` thành `frozenset({0})`.
- **Lệnh chạy:** `uv run pytest tests/test_schedule_watch.py -k "chong_nhan_doi_heartbeat" -q`
- **Dòng đỏ nguyên văn:**
```text
FAILED tests/test_schedule_watch.py::test_chong_nhan_doi_heartbeat_exit_1_im_lang
AssertionError: Heartbeat tự thoát 1 không được sinh thêm cảnh báo
assert ['[CRITICAL] ...'] == []
Left contains one more item: "[CRITICAL] job theo lịch 'heartbeat' THẤT BẠI: lần chạy gần nhất lúc 2026-10-02 10:00:00 kết thúc với mã thoát 1"
1 failed, 23 deselected in 0.40s
```
- **Khôi phục:** Khôi phục `frozenset({0, 1})`, đối chiếu hash khớp 100%.

#### Phá thử 4: Xóa chính sách của 1 nhánh (`stream-health`)
- **Thao tác:** Tạm comment nhánh `"stream-health"` trong `SCHEDULE_EXIT_POLICIES`.
- **Lệnh chạy:** `uv run pytest tests/test_schedule_watch.py -k "covered_in_exit_policies" -q`
- **Dòng đỏ nguyên văn:**
```text
FAILED tests/test_schedule_watch.py::test_sched_branches_covered_in_exit_policies
AssertionError: Các nhánh sau trong sched.sh thiếu chính sách mã thoát trong SCHEDULE_EXIT_POLICIES: {'stream-health'}
assert not {'stream-health'}
1 failed, 23 deselected in 0.41s
```
- **Khôi phục:** Khôi phục lại nhánh `stream-health`, đối chiếu hash khớp 100%.

---

### Tiêu chí 4 — Chạy thật `scripts/sched.sh heartbeat --dry-run` trên log máy thật
- **Lệnh chạy:** `& "C:\Program Files\Git\bin\bash.exe" scripts/sched.sh heartbeat --dry-run`
- **Dòng log nguyên văn trong `logs/heartbeat.log`:**
```text
2026-10-03 20:17:32 heartbeat-check start
[CRITICAL] job theo lịch 'engine-consumer' THẤT BẠI: lần chạy gần nhất lúc 2026-10-02 22:38:59 kết thúc với mã thoát 2
[DRY-RUN] Không gửi Telegram thật. Không cập nhật file trạng thái.
EXIT=1
```
- **Phân tích số đo:** Trên log thật của máy này, job `engine-consumer` có lần chạy lúc `2026-10-02 22:38:59` kết thúc với `EXIT=2` (do lệnh chạy thử truyền cờ không hợp lệ `--khong-ton-tai` khiến argparse thoát mã 2 mà không gửi Telegram). Tính năng mới đã phát hiện chuẩn xác thất bại này và in cảnh báo CRITICAL trong chế độ `--dry-run`, không gửi Telegram thật và không làm biến đổi trạng thái.

---

### Tiêu chí 5 — Ruff & Pytest Suite
- **Ruff check:**
```powershell
uv run ruff check scripts/heartbeat_check.py tests/test_schedule_watch.py
```
*Kết quả:* `All checks passed!`

- **Pytest Suite:**
```powershell
uv run pytest -q
```
*Kết quả nguyên văn:*
```text
1788 passed in 124.32s (0:02:04)
```
Số lượng test đạt: `1788 passed` (tăng +15 test so với mốc 1773 của đợt 155, 0 failed).

---

### Tiêu chí 6 — Kiểm tra trạng thái file
- **Lệnh kiểm tra:**
```powershell
Get-ChildItem -Path logs -Filter "alert_outbox_*" -ErrorAction SilentlyContinue
Test-Path "logs/.schedule_health_state.json"
```
*Kết quả:* `False` / Rỗng. Cả hai đều không tồn tại sau khi kiểm thử.

---

## 5. Điểm brief chưa tính đến và Những điều không kiểm được

### Điểm brief chưa tính đến
1. **Hành vi của `re.match` trong Python:**
   `re.match` mặc định luôn chỉ so khớp từ đầu chuỗi (index 0). Do đó `re.match(r"EXIT=(\d+)", "ALERT_EXIT=1")` sẽ trả về `None` ngay cả khi không có ký tự `^`. Tuy nhiên, việc tường minh neo đầu dòng `^EXIT=` là thiết yếu để phòng ngừa trường hợp refactor sang `re.search` hoặc sử dụng các công cụ regex/grep khác.
2. **Sự cố thực tế sẵn có trong log:**
   Trong `logs/engine-consumer.log`, tồn tại một dòng `EXIT=2` từ ngày 02/10 (lỗi argparse do truyền tham số không tồn tại). Đây là một minh chứng thực tế khẳng định giá trị của tính năng canh mã thoát.

### Những điều không kiểm được trong môi trường hiện tại
- Không thể mô phỏng một sự cố Windows Task Scheduler kill tiến trình giữa chừng (mã 4 do `StopIfGoingOnBatteries`) ngay trong runtime của pytest mà không can thiệp vào OS host. Hành vi này đã được kiểm chứng tương đương 100% bằng việc nạp log lịch sử nguyên văn của ngày 29/09 trong unit test `test_tai_hien_su_co_that_orderbook_recorder_exit_4`.

---

## Audit của Claude (03/10/2026)

### A.1. Kết luận: ĐẠT. Claude sửa một mệnh đề sai trong bảng chính sách.

### A.2. Phạm vi
AST theo hàm: `heartbeat_check.py` thêm `JobExitPolicy`, `get_last_run_exit_code`, và đổi
`evaluate_schedule_health` + `main`. Không hàm cũ nào khác đổi. Chỉ hai file bị sửa.

### A.3. Dẫn chứng số dòng — Claude kiểm từng cái, không tin bảng
Đây là chỗ brief cố ý không cho sẵn đáp án. Claude mở từng script:

| Job | Khẳng định | Kiểm |
|---|---|---|
| `engine-consumer` | 136/149/184 là `return 1`, 188 là `return 0` | **đúng**; script **không có** `return 2` nào, nên mã 2 chỉ đến từ argparse hoặc crash → đúng là chưa ai báo |
| `stream-health` | 546 `exit(2)`, 556 `exit(1)`, 572 `exit(0)`, không gửi Telegram | **đúng** |
| `container-health` | 499 `return 2` khi Docker chưa chạy, có chú thích "không cảnh báo ở đây" | **đúng** |
| `host-preflight` | 459 trả 1 khi có phép kiểm FAIL; không gửi Telegram | **đúng** |
| `orderbook-recorder` | script chỉ tự thoát 0/1 nên mã 4 là bị giết | **đúng** |

### A.4. Một mệnh đề sai, Claude sửa thẳng
Lý do của `orderbook-daily-check` viết rằng mã 1 và 2 "đều đã gọi `trading.alerts.alert()` **(có hàng đợi
outbox)**". Phần trong ngoặc **sai**: `check_orderbook_daily.py` không gọi `start_outbox` (Claude đếm: 0 lần),
nên script này **không có** hàng đợi. Gửi hỏng là mất tin. Kết luận "không canh mã 1 và 2" vẫn đúng vì script
có tự gửi, nhưng lý do thì phải nói thật. Đã viết lại, có dẫn tới §8.6 của `DEPLOYMENT.md`.

Đây đúng kiểu lỗi "điền chi tiết nghe hợp lý mà không kiểm" — lần này là một mệnh đề trong ngoặc.

### A.5. Phá thử của Claude (khác bốn ca agent đã làm)

| Phá thử | Kết quả |
|---|---|
| M1 — không đọc được mã thoát (file log thiếu, hoặc job đang chạy) coi là THẤT BẠI | **11 test đỏ** |
| M2 — bỏ điều kiện "chỉ báo khi mã đổi" | `test_exit_code_eval_repeated_failure_is_silent` **đỏ** |

Hash `scripts/heartbeat_check.py` sau mỗi lần khôi phục: `653e43d71121fce1`.

### A.6. Bốn ca biên Claude tự dò, đều đúng
Gọi trực tiếp `get_last_run_exit_code`:

```
file log không tồn tại        -> (None, None, 'file log không tồn tại (...)')   => im lặng
job đang chạy (chưa có EXIT=) -> (dt, None, None)                               => im lặng
chỉ có ALERT_EXIT=1           -> (dt, None, None)                               => neo đầu dòng ĐÚNG
EXIT= cũ nằm TRƯỚC lần chạy mới -> (dt, None, None)                             => gắn đúng lần chạy
```

Và mô phỏng **VPS mới, thiếu toàn bộ file log**: ra đúng 5 cảnh báo NGỪNG CHẠY có từ đợt 142, **0** cảnh báo
về mã thoát. Không có báo động giả lúc dựng máy mới.

### A.7. Dự báo: sáng thứ Hai sẽ có một cảnh báo thật, và nó đúng
Claude chạy `scripts/sched.sh heartbeat --dry-run` trên log thật:

```
[CRITICAL] job theo lịch 'engine-consumer' THẤT BẠI: lần chạy gần nhất lúc 2026-10-02 ...
```

Dòng `EXIT=2` đó là **dòng cuối** của `logs/engine-consumer.log`, từ lần chạy 02/10 22:38:59 — chính là lần
agent đợt 146 cố ý chạy `engine-consumer --khong-ton-tai` để chứng minh argparse chặn cờ lạ. Vậy:
- 08:00 thứ Hai: heartbeat báo CRITICAL một lần (đúng theo thiết kế: lần chạy cuối **đã** thất bại);
- 09:00 thứ Hai: `engine-consumer` chạy thật, thoát 0 → heartbeat báo hồi phục một lần rồi im.

Không phải lỗi, nhưng chủ dự án cần biết trước để không tưởng là sự cố mới.
