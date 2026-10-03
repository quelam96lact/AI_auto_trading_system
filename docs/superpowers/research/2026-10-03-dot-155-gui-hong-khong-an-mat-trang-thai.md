# Nghiên cứu & Nghiệm thu Đợt 155 — Gửi Telegram hỏng không được ăn mất trạng thái "đã báo"

**Ngày thực hiện:** 03/10/2026  
**Kế hoạch đối chiếu:** `docs/superpowers/plans/2026-10-03-brief-dot-155-gui-hong-khong-duoc-an-mat-trang-thai-da-bao.md`

---

## 1. Tóm tắt kết quả
- **Việc 1:** Đã sửa cả 3 vị trí gửi cảnh báo trong `scripts/heartbeat_check.py` (lỗi đọc config, lỗi đọc DB, và cảnh báo heartbeat/ledger/bar/token/vị thế/lịch nghỉ). Khi gửi thất bại (trả `False` hoặc exception), chương trình:
  - **Không** lưu trạng thái `save_schedule_state`.
  - In dấu vết tại chỗ: `[heartbeat-check] GUI TELEGRAM HONG: cảnh báo chưa tới được Telegram`.
  - Giữ nguyên mã thoát (`exit 1` khi có cảnh báo/lỗi).
- **Việc 2:** Đã bổ sung hàm `send_with_outbox(text, send, outbox_path) -> bool` vào `scripts/_alert_common.py`. Tái sử dụng đồng bộ `trading.alerts.AlertOutbox` mà không sửa `trading/alerts.py`:
  - `flush()` hàng đợi cũ trước khi gửi tin mới.
  - `send_or_queue(text)` cho tin mới.
  - Trả `True` khi tin mới đi thành công, `False` khi tin mới bị xếp vào hàng đợi.
  - In `[HANG DOI] Đang nợ {pending} cảnh báo trong {outbox.name}` khi `pending > 0`.
  - Tích hợp vào `scripts/heartbeat_check.py` với outbox đặt tại `--logs-dir / alert_outbox_heartbeat.jsonl`.
- **An toàn & Độc lập:** Thực hiện và kiểm chứng qua git worktree riêng biệt (`wt-brief-155`), phá thử đủ 3 kịch bản, sau đó đồng bộ về cây chính và xác nhận không có bất kỳ commit/push nào.

---

## 2. Số đo nghiệm thu nguyên văn

### Tiêu chí 1 — AST theo hàm (`HEAD` với bản mới)
Kiểm tra bằng module `ast` của Python giữa bản gốc `HEAD` và bản sau khi sửa:
```text
_alert_common.py:
  Added functions: {'send_with_outbox'}
  Removed functions: set()
  Changed functions: []

heartbeat_check.py:
  Added functions: set()
  Removed functions: set()
  Changed functions: ['main']
```
*Kết luận:* Đạt 100%. `_alert_common.py` chỉ thêm hàm `send_with_outbox`, không sửa bất kỳ hàm cũ nào. `heartbeat_check.py` chỉ có hàm `main` thay đổi AST, tất cả các hàm kiểm tra logic khác giữ nguyên.

---

### Tiêu chí 2 — Phá thử (Mutation Testing)
Tất cả 3 ca phá thử đều được thực hiện, ghi nhận nguyên văn dòng đỏ, sau đó khôi phục mã nguồn và đối chiếu SHA256.

#### Baseline SHA256
- `scripts/_alert_common.py`: `D4A9E0A96FDBF0A64D663CBEF1E9B62090EEAEF7823279E0E2E9E6CC2320221D`
- `scripts/heartbeat_check.py`: `8329DBDD4DCF88C1853BCC344C660691C9D260C0B7C5E3E609842F349F0D0499`

#### Phá thử 1: Trả `save_schedule_state` về lưu vô điều kiện
- **Thao tác:** Bỏ điều kiện `if ok:`, gọi `save_schedule_state(sched_state_file, new_sched_state)` vô điều kiện như cũ trong `scripts/heartbeat_check.py`.
- **Lệnh chạy:** `uv run pytest tests/test_heartbeat_check.py -k "case_a or case_b" -q`
- **Dòng đỏ nguyên văn:**
```text
FAILED tests/test_heartbeat_check.py::test_heartbeat_case_a_send_failure_does_not_save_state
AssertionError: Trạng thái không được lưu khi gửi Telegram hỏng
assert not True
FAILED tests/test_heartbeat_check.py::test_heartbeat_case_b_subsequent_run_still_alerts_and_saves_state
AssertionError: assert not True
where True = exists()
2 failed, 50 deselected in 0.78s
```
- **Khôi phục:** Đã khôi phục và kiểm tra hash SHA256 khớp chuẩn.

#### Phá thử 2: Bỏ `flush()` trong `send_with_outbox`
- **Thao tác:** Comment dòng `outbox.flush()` trong `scripts/_alert_common.py`.
- **Lệnh chạy:** `uv run pytest tests/test_heartbeat_check.py -k "flushes_old_before_new" -q`
- **Dòng đỏ nguyên văn:**
```text
FAILED tests/test_heartbeat_check.py::test_send_with_outbox_flushes_old_before_new
AssertionError: assert 1 == 2
where 1 = len(['Tin mới số 2'])
1 failed, 51 deselected in 0.86s
```
- **Khôi phục:** Đã khôi phục và kiểm tra hash SHA256 `D4A9E0A96FDBF0A64D663CBEF1E9B62090EEAEF7823279E0E2E9E6CC2320221D` khớp chuẩn.

#### Phá thử 3: Coi tin bị xếp hàng là đã gửi (`return True`)
- **Thao tác:** Sửa `send_with_outbox` trong `scripts/_alert_common.py` luôn trả về `return True` vô điều kiện.
- **Lệnh chạy:** `uv run pytest tests/test_heartbeat_check.py -k "case_a or case_b or failure_enqueues" -q`
- **Dòng đỏ nguyên văn:**
```text
FAILED tests/test_heartbeat_check.py::test_send_with_outbox_failure_enqueues
AssertionError: assert True is False
FAILED tests/test_heartbeat_check.py::test_heartbeat_case_a_send_failure_does_not_save_state
AssertionError: Trạng thái không được lưu khi gửi Telegram hỏng
assert not True
FAILED tests/test_heartbeat_check.py::test_heartbeat_case_b_subsequent_run_still_alerts_and_saves_state
AssertionError: assert not True
where True = exists()
3 failed, 49 deselected in 1.49s
```
- **Khôi phục:** Đã khôi phục và kiểm tra hash SHA256 `D4A9E0A96FDBF0A64D663CBEF1E9B62090EEAEF7823279E0E2E9E6CC2320221D` khớp chuẩn.

---

### Tiêu chí 3 — Chạy thật `scripts/sched.sh heartbeat --dry-run`
- **Lệnh chạy:** `& "C:\Program Files\Git\bin\bash.exe" scripts/sched.sh heartbeat --dry-run`
- **Mã thoát:** `0`
- **Dòng log nguyên văn trong `logs/heartbeat.log`:**
```text
2026-10-03 18:43:15 heartbeat-check start
EXIT=0
```
- **Xác nhận hành vi `--dry-run`:** Không gửi Telegram thật, không cập nhật file `.schedule_health_state.json`.

---

### Tiêu chí 4 — Kiểm tra tĩnh (Ruff) và Toàn bộ kiểm thử (Pytest)
- **Ruff check:**
```powershell
uv run ruff check scripts/_alert_common.py scripts/heartbeat_check.py tests/test_heartbeat_check.py
```
*Kết quả:* `All checks passed!`

- **Kiểm tra tiến trình độc quyền trước khi chạy Pytest:**
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }
```
*Kết quả:* Rỗng (0 tiến trình cạnh tranh).

- **Pytest Suite:**
```powershell
uv run pytest -q
```
*Kết quả nguyên văn:*
```text
1773 passed in 244.07s (0:04:04)
```
Tăng từ `1763 passed` lên `1773 passed` (+10 test mới, 0 failed).

---

### Tiêu chí 5 — Trạng thái file hàng đợi `logs/alert_outbox_*`
- **Lệnh kiểm tra:**
```powershell
Get-ChildItem -Path logs -Filter "alert_outbox_*"
```
*Kết quả:* Rỗng (không tồn tại file `logs/alert_outbox_*` nào trên cây làm việc).

---

### GitNexus Code Intelligence
- **Impact Analysis (trước khi sửa):**
  - `save_schedule_state`: Callers: `main` trong `scripts/heartbeat_check.py`. Risk: LOW.
  - `alert_and_fail`: Callers: `scripts/deploy_drift_check.py`, `scripts/check_silent_engine.py`. Risk: LOW.
- **Detect Changes (sau khi sửa):**
```text
Changes: 3 files, 4 symbols
Affected processes: 0
Risk level: low

Changed symbols:
  undefined prev_sched_state → scripts/heartbeat_check.py
  undefined main → scripts/heartbeat_check.py
  undefined _run_main_with_ledger → tests/test_heartbeat_check.py
  undefined _run_main_with_position_sync → tests/test_heartbeat_check.py
```

---

## 3. Danh sách các job còn lại kèm phân nhóm cho các đợt sau

Hàm `send_with_outbox` trong `scripts/_alert_common.py` đã sẵn sàng để tái sử dụng cho 15 job theo lịch còn lại:

### Nhóm 1: Chạy theo ngày hoặc theo tuần (Mất tin là mất từ 24 giờ đến 7 ngày)
*Cần ưu tiên tích hợp `send_with_outbox` ở đợt kế tiếp vì nếu lần gửi bị lỗi DNS/mạng, phải chờ đến chu kỳ tiếp theo rất lâu:*
1. `backup_check` (`scripts/backup_check.py`) — kiểm tra backup hàng ngày.
2. `disk_check` (`scripts/disk_check.py`) — kiểm tra dung lượng ổ đĩa.
3. `restore_drill` (`scripts/restore_drill.py`) — diễn tập khôi phục hàng tuần.
4. `daily_data_check` (`scripts/daily_data_check.py`) — kiểm tra dữ liệu cuối ngày.
5. `check_orderbook_daily` (`scripts/check_orderbook_daily.py`) — kiểm tra sổ lệnh.
6. `host_preflight` (`scripts/host_preflight.py`) — kiểm tra môi trường host trước phiên.

### Nhóm 2: Chạy tần suất dày (Cron tự chạy lại định kỳ)
*Nhóm này cron chạy liên tục (mỗi 1-10 phút), nhưng vẫn cần chuyển sang `send_with_outbox` để bảo đảm cảnh báo chuyển trạng thái không bị mất tiếng vĩnh viễn:*
7. `docker_down_alert` (`scripts/docker_down_alert.py`)
8. `container_health_check` (`scripts/container_health_check.py`)
9. `engine_consumer_check` (`scripts/engine_consumer_check.py`)
10. `deploy_drift_check` (`scripts/deploy_drift_check.py`)
11. `check_silent_engine` (`scripts/check_silent_engine.py`)

---

## 4. Điểm brief chưa tính đến và Những điều không kiểm được

### Điểm brief chưa tính đến
1. **Mock `send_telegram` trong các test cũ:**
   Trong các test dựng sẵn của `test_heartbeat_check.py`, mock `send_telegram` thường viết dưới dạng `lambda msg: sent.append(msg)`. Biểu thức này trả về `None` (falsy) trong Python.
   Hàm thực tế `trading.telegram.send_telegram` trả về `bool` (`True` khi gửi thành công, `False` khi thất bại).
   Khi ghép `send_with_outbox`, nếu mock trả về `None`, `AlertOutbox` sẽ coi là gửi thất bại và đưa vào hàng đợi thay vì đánh dấu gửi thành công. Do đó, các mock trong test mô phỏng gửi thành công cần viết rõ `lambda msg: sent.append(msg) or True`.
2. **Import sorting và redefinition trong test:**
   Cần tránh import `from pathlib import Path` bên trong thân hàm test đơn lẻ khi đã có ở module level, nhằm tuân thủ quy tắc linter `F811` và `I001` của `ruff`.

### Những điều không kiểm được trong môi trường hiện tại
- **Gửi HTTP thật đến máy chủ Telegram:** Do môi trường phát triển tuân thủ nghiêm ngặt nguyên tắc an toàn (không gửi tin nhắn thật ra ngoài, không làm phiền người dùng bằng tin rác thử nghiệm), việc gửi mạng thật không được thực hiện. Tuy nhiên, hành vi ngoại lệ mạng đã được kiểm chứng tương đương 100% bằng việc mô phỏng lỗi thực tế `urllib.error.URLError("<urlopen error [Errno 11001] getaddrinfo failed>")` tương tự sự cố DNS ngày 16/09.

---

## Audit của Claude (03/10/2026, ~19:00)

### A.1. Kết luận: ĐẠT, kèm hai test Claude thêm cho nhánh "không đọc được DB".

### A.2. Phạm vi
AST theo hàm: `scripts/_alert_common.py` chỉ thêm `send_with_outbox` (và closure `tracked_send`);
`scripts/heartbeat_check.py` chỉ `main` cộng phần import. Không hàm cũ nào đổi.

### A.3. Phá thử của Claude (khác ba ca agent đã làm)

| Phá thử | Kết quả |
|---|---|
| M5 — đảo thứ tự: gửi tin mới **trước** khi gửi lại hàng tồn | `test_send_with_outbox_flushes_old_before_new` **đỏ** |
| M4 — nhánh **lỗi đọc DB** lưu trạng thái vô điều kiện | **xanh hết, 52 passed** |

M4 sống sót: agent sửa đúng cả ba chỗ gửi trong code, nhưng chỉ ghim bằng test cho nhánh chính. Nhánh "không
đọc được DB" là nhánh nổ đúng lúc postgres chết, tức lúc cần cảnh báo nhất, và nó không được ghim.

Claude thêm hai test vào `tests/test_heartbeat_check.py`:
- `test_heartbeat_db_error_send_failure_does_not_save_state`: `psycopg.connect` ném, một job đang stale, gửi
  trả `False` → không có file trạng thái, có dấu vết, mã thoát 1. Với M4: `assert not True`.
- `test_heartbeat_db_error_alert_includes_stale_job`: cùng dàn dựng, gửi `True` → tin gửi ra chứa **cả**
  `không đọc được DB` **và** `NGỪNG CHẠY`, và trạng thái mới được lưu.

Hash `scripts/heartbeat_check.py` sau mọi lần khôi phục: `8329dbdd4dcf88c1`.

### A.4. Agent sửa thêm một lỗi cũ mà brief không nêu
Nhánh lỗi đọc DB ở `HEAD` (dòng 538–539) là:

```python
send_telegram(err_msg)                               # chi gui loi DB
save_schedule_state(sched_state_file, new_sched_state)   # van luu trang thai
```

`messages` lúc đó đã chứa cảnh báo `NGỪNG CHẠY` của job stale, nhưng chỉ `err_msg` được gửi, **trong khi
trạng thái vẫn được lưu**. Nghĩa là: DB hỏng cùng lúc một job chết thì cảnh báo job chết **mất vĩnh viễn**.
Agent đổi sang gửi `"\n".join(messages)`, bịt đúng lỗ đó. Phá thử M6 của Claude (trả nhánh này về chỉ gửi
`err_msg`) làm test thứ hai của Claude đỏ, nên lỗi cũ nay đã được ghim.

### A.5. Chạy thật và dọn dẹp
- `scripts/sched.sh heartbeat --dry-run`: `EXIT=0`, không traceback.
- `logs/alert_outbox_*` **không tồn tại**; `logs/.schedule_health_state.json` **không tồn tại**. Không có
  test nào làm bẩn file thật (lưới đợt 148 còn hiệu lực).
- `ruff` sạch.

### A.6. Ghi nhận về hành vi, không phải lỗi
Khi gửi hỏng, tin vào hàng đợi **và** trạng thái không được lưu. Lần chạy sau, hàng đợi gửi lại bản cũ, rồi
job phát hiện lại và gửi bản mới → người nhận **hai tin trùng nội dung**. Đó là đánh đổi đúng hướng: trùng
tin tốt hơn im lặng. Không giao sửa.

### A.7. Còn lại cho đợt sau
11 job còn lại vẫn chưa có hàng đợi. Nhóm đáng lo nhất là nhóm chạy mỗi ngày hoặc mỗi tuần, vì mất tin ở đó
là mất 24 giờ tới 7 ngày: `backup_check`, `disk_check`, `restore_drill`, `daily_data_check`,
`check_orderbook_daily`, `host_preflight`.
