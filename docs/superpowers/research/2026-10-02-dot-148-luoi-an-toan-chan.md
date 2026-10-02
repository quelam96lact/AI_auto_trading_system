# Báo Cáo Đợt 148 — Lưới an toàn phải CHẶN việc ghi file trạng thái thật, không chỉ báo sau

- **Thời gian thực hiện:** 2026-10-02 23:33 – 23:45 (Giờ VN)
- **Mục tiêu:** Nâng cấp lưới an toàn trong [tests/conftest.py](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/conftest.py): Khi phát hiện thao tác mở-để-ghi, xoá hoặc đổi tên vào file trạng thái thật trong `logs/`, **ném ngay ngoại lệ `PermissionError` trong audit hook** để huỷ thao tác trước khi chạm đĩa; không để phá thử làm bẩn file thật.
- **Phạm vi tác động:** Chỉ sửa duy nhất [tests/conftest.py](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/conftest.py). Tuyệt đối không đụng `scripts/` hay `trading/`.

---

## 1. Cơ chế nâng cấp trong `tests/conftest.py`

Trước đây (Đợt 145), `_audit_real_state_files` chỉ ghi nhận vào `_STATE_WRITES` và báo lỗi ở teardown session:
```python
# CŨ: Chỉ ghi nhận, không ngăn chặn -> OS vẫn ghi file thật ra đĩa
if name:
    _STATE_WRITES.append((test_name, event, name))
```

Bây giờ (Đợt 148), khi phát hiện thao tác ghi/xoá/đổi tên vào file trạng thái thật:
1. Ghi nhận vi phạm vào `_STATE_WRITES` (để session teardown vẫn báo cáo danh sách vi phạm đầy đủ).
2. **Ném ngay `PermissionError`** trong hook:
```python
if violation:
    name, ev, test = violation
    raise PermissionError(
        f"[LUOI AN TOAN 148] CHẶN thao tác '{ev}' vào file trạng thái thật 'logs/{name}' bởi {test}"
    )
```
- Khi `open(..., "w")` bị ném lỗi trong hook, Python runtime huỷ việc mở file trước khi HĐH cấp file handle -> File hoàn toàn không được tạo hoặc ghi đè trên đĩa.
- Thao tác mở để đọc (`not writing`) vẫn được cho phép bình thường.

---

## 2. Thực nghiệm Đối chứng (Tiêu chí 2 — Trước khi sửa)

Kiểm tra hành vi với lưới an toàn CŨ (chưa có bước ném ngoại lệ):
- Trước test: `logs/.engine_consumer_last_check` không tồn tại (`Test-Path` = `False`).
- Phá thử trong `scripts/engine_consumer_check.py`: `main` truyền `state_file=None`.
- Chạy: `uv run pytest tests/test_engine_consumer_check.py -k test_main_passes_state_file_to_run_check`
- **Kết quả:**
  - Test đỏ (`AssertionError`) và session đỏ (teardown fixture).
  - Nhưng file thật **ĐÃ BỊ TẠO VÀ GHI ĐÈ TRÊN ĐĨA**:
    ```powershell
    Name                        Length LastWriteTime        
    ----                        ------ -------------        
    .engine_consumer_last_check     96 10/2/2026 11:35:46 PM
    ```
  - Nội dung file bẩn trên đĩa:
    ```json
    {
      "stream_seq": 100,
      "last_seq": 100,
      "ts": 1790958946.011972,
      "last_alert_ts": 0
    }
    ```
- **Dọn dẹp:** Đã chạy `Remove-Item logs/.engine_consumer_last_check -Force` để xoá sạch file bẩn này; khôi phục `scripts/engine_consumer_check.py`.

---

## 3. Thực nghiệm Tái hiện & Xác nhận chặn (Tiêu chí 1 — Sau khi sửa)

Kiểm tra hành vi với lưới an toàn MỚI (đã ném `PermissionError` trong hook):
- Trước test: `logs/.engine_consumer_last_check` và `.tmp` không tồn tại (`Test-Path` = `False`, `False`).
- Phá thử: Đổi `state_file=args.state_file` thành `state_file=None` trong `main()`.
- Chạy: `uv run pytest tests/test_engine_consumer_check.py -k test_main_passes_state_file_to_run_check`
- **Kết quả nguyên văn:**
  - Lệnh `open` bị chặn đứng ngay lập tức trước khi chạm đĩa:
    ```text
    [engine-consumer] Không thể ghi file state: [LUOI AN TOAN 148] CHẶN thao tác 'open' vào file trạng thái thật 'logs/.engine_consumer_last_check.tmp' bởi tests/test_engine_consumer_check.py::test_main_passes_state_file_to_run_check (call)
    ```
  - Test đỏ: `AssertionError: assert None == '...'`
  - Session đỏ:
    ```text
    Test da GHI/XOA/DOI TEN file trang thai THAT trong logs/ (cron doc file nay): .engine_consumer_last_check.tmp [open] boi tests/test_engine_consumer_check.py::test_main_passes_state_file_to_run_check (call)
    ```
    *(Lưu ý: Chỉ ghi nhận sự kiện `[open]` của file `.tmp`. Thao tác `[os.rename]` của file chính hoàn toàn không xuất hiện vì `open` đã bị chặn ngay từ đầu).*
  - **Kiểm tra trên đĩa sau test:**
    ```powershell
    Test-Path logs/.engine_consumer_last_check; Test-Path logs/.engine_consumer_last_check.tmp
    False
    False
    ```
    **File thật hoàn toàn KHÔNG bị tạo hay ghi đè! Đĩa sạch 100%!**
- **Khôi phục:** Khôi phục `state_file=args.state_file`.
- **Đối chiếu Hash SHA-256:**
  - Trước: `991ACF8974E4CD2D81BAD3954A5DAF0872DEAD92D6CC0BFAE94FAE7F3AB63F3C`
  - Sau: `991ACF8974E4CD2D81BAD3954A5DAF0872DEAD92D6CC0BFAE94FAE7F3AB63F3C` (Khớp 100%).

---

## 4. Kiểm tra mở để ĐỌC file thật (Tiêu chí Việc 2)

- Đã tích hợp bộ đếm các thao tác `open` với mode đọc (`not writing`) vào các file trạng thái thật trong `logs/`.
- Khi chạy toàn bộ 1.748 test trong suite: **Số lần mở đọc file trạng thái thật là 0**.
- Mọi test đều tuân thủ việc dùng mock hoặc truyền đường dẫn thư mục tạm (`tmp_path`).

---

## 5. Cron không bị ảnh hưởng (Tiêu chí 3)

Đã chạy toàn bộ test suite `uv run pytest -q` trong khung giờ vắt qua chu kỳ chạy 10 phút của `container-health` (bắt đầu lúc 23:39:54, kết thúc lúc 23:41:18):
- Cron Windows Task Scheduler kích hoạt tiến trình riêng lúc 23:40:04 độc lập với pytest:
  - Trích xuất `logs/container-health.log`:
    ```text
    2026-10-02 23:20:02 container-health start
    EXIT=0
    2026-10-02 23:30:05 container-health start
    EXIT=0
    2026-10-02 23:40:04 container-health start
    EXIT=0
    ```
  - Kiểm tra mtime của file trạng thái thật:
    ```powershell
    Name                         Length LastWriteTime        
    ----                         ------ -------------        
    .container_health_state.json   1596 10/2/2026 11:40:14 PM
    ```
  - File `.container_health_state.json` được cron ghi thành công lúc 11:40:14 PM.
- Cùng lúc đó, tiến trình pytest chạy song song và kết thúc thành công:
  ```text
  1748 passed in 83.16s (0:01:23)
  ```
  Không có xung đột, không có sự can thiệp chéo giữa audit hook của pytest và tiến trình cron của hệ thống.

---

## 6. Tổng hợp đo lường & Tiêu chí hoàn thành

| Tiêu chí | Yêu cầu | Kết quả |
|---|---|---|
| 1. Tái hiện sự cố với lưới mới | Test đỏ, file thật không đổi | Đạt (Test đỏ, `PermissionError` ném, `Test-Path` = False) |
| 2. Đối chứng lưới cũ | File thật bị ghi, dán bằng chứng & xoá | Đạt (File bị ghi lúc 23:35:46, đã dán log & xoá sạch) |
| 3. Cron không bị ảnh hưởng | Cron chạy song song, start/EXIT=0 | Đạt (start 23:40:04, EXIT=0, mtime 11:40:14 PM) |
| 4. Kiểm tra mở đọc | Kiểm tra có test nào đọc file thật | Đạt (0/1.748 test đọc file thật) |
| 5. Linter & Test Suite | `ruff` sạch; `pytest -q` $\ge 1.748$ | Đạt (`All checks passed`, **1748 passed**) |
| 6. Git diff stat | Chỉ sửa `tests/conftest.py` | Đạt (`tests/conftest.py \| 32 ++++++++++---`) |

---

## 7. Đánh giá: Brief sai ở đâu & Cái gì không kiểm được

1. **Brief sai ở đâu:**
   - Không có điểm nào sai. Phân tích nguyên nhân và phương án chặn trước khi chạm đĩa trong brief là hoàn toàn chính xác.
2. **Cái gì không kiểm được:**
   - Audit hook của Python hoạt động trong tiến trình hiện tại (`sys.addaudithook`). Nếu một test tương lai chạy subprocess độc lập qua `subprocess.Popen` mà không kế thừa hook, tiến trình con đó sẽ không bị bắt bởi audit hook của process cha (đây là đặc tính thiết kế của Python audit hook đã được ghi nhận từ Đợt 145).

---

## Audit của Claude (02/10/2026, 23:50)

**Kết luận: ĐẠT.**

- **Phá thử của Claude, chạy cả file test** (không chỉ một test): `main` truyền `state_file=None` → `test_main_passes_state_file_to_run_check` FAILED, lưới báo `CHẶN thao tác 'open' vào file trạng thái thật 'logs/.engine_consumer_last_check.tmp'`. `logs/.engine_consumer_last_check` **không tồn tại trước, không tồn tại sau**; không có `.tmp`. Hash `scripts/engine_consumer_check.py` khôi phục trùng `991acf8974e4cd2d`.
- **Chi tiết đáng ghi:** ngoại lệ `PermissionError` của lưới bị chính khối `except Exception` trong `engine_consumer_check.save_state` nuốt (in `Không thể ghi file state: [LUOI AN TOAN 148] ...`). Lưới vẫn làm phiên đỏ nhờ `pytest.fail` lúc dọn. Hai lớp này đều cần: chặn ở hook để đĩa sạch, báo ở cuối phiên để phiên đỏ dù code nuốt ngoại lệ.
- **Đối chứng của Claude (tắt `raise` trong hook) HỎNG do lỗi script của Claude**: thay dòng đầu của một `raise PermissionError(...)` nhiều dòng thành `pass` gây `IndentationError`. Không làm lại, vì bằng chứng "lưới cũ không chặn thì file thật bị ghi" đã có độc lập: Claude quan sát nó lúc 23:27:26 ở audit đợt 147, và agent tái hiện lúc 23:35:46. Cả hai file đã khôi phục, hash trùng.
- `ruff` sạch; bộ đầy đủ xanh; file thật vẫn không tồn tại sau bộ đầy đủ.
