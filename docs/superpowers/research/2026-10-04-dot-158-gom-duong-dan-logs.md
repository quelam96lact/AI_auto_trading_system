# Đợt 158 — Gom `DEFAULT_LOGS_DIR` và tên file hàng đợi về một chỗ

Áp dụng cho 5 script: `heartbeat_check.py`, `backup_check.py`, `disk_check.py`, `restore_drill.py`, `daily_data_check.py`.
**Không commit, không push.**

---

## 1. Mục tiêu & Thay đổi đã thực hiện

- **Thư mục logs dùng chung (`REPO_LOGS_DIR`):** Đặt duy nhất tại `scripts/_db_common.py`, tính từ vị trí file (`Path(__file__).resolve().parents[1] / "logs"` qua `os.path.join`), không phụ thuộc vào `cwd`. Cả 5 script gán lại `DEFAULT_LOGS_DIR = REPO_LOGS_DIR` để giữ nguyên giao diện module cho các test hiện hữu.
- **Khuôn tên hàng đợi dùng chung (`outbox_name`, `outbox_path`):** Đặt tại `scripts/_alert_common.py`, trả `alert_outbox_<job>.jsonl` và đường dẫn trong `logs_dir`. Cả 5 script gọi `outbox_name(...)` để gán `OUTBOX_NAME` / `HEARTBEAT_OUTBOX_NAME`.
- **Không đổi bất kỳ hành vi nào:** Không sửa logic chạy, không đổi mã thoát, không sửa `trading/alerts.py`, `sched.sh`, `run_if_docker_up.sh`.

---

## 2. Tiêu chí 1: Định nghĩa `DEFAULT_LOGS_DIR` / `REPO_LOGS_DIR`
Chỉ còn **duy nhất một** dòng định nghĩa tính toán thật trong toàn bộ `scripts/*.py`:
```text
scripts/_db_common.py:19: REPO_LOGS_DIR = os.path.join(
scripts/backup_check.py:52: DEFAULT_LOGS_DIR = REPO_LOGS_DIR
scripts/daily_data_check.py:35: DEFAULT_LOGS_DIR = REPO_LOGS_DIR
scripts/disk_check.py:45: DEFAULT_LOGS_DIR = REPO_LOGS_DIR
scripts/heartbeat_check.py:88: DEFAULT_LOGS_DIR = REPO_LOGS_DIR
scripts/restore_drill.py:67: DEFAULT_LOGS_DIR = REPO_LOGS_DIR
```

---

## 3. Tiêu chí 2: Bảng so sánh Trước & Sau (Trùng từng ký tự)

### Bảng TRƯỚC khi sửa (đo tại `HEAD` 838d271):
```text
heartbeat_check | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs\alert_outbox_heartbeat.jsonl
backup_check | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs\alert_outbox_backup-check.jsonl
disk_check | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs\alert_outbox_disk-check.jsonl
restore_drill | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs\alert_outbox_restore-drill.jsonl
daily_data_check | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs\alert_outbox_daily-check.jsonl
```

### Bảng SAU khi sửa (đo trên bản mới):
```text
heartbeat_check | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs\alert_outbox_heartbeat.jsonl
backup_check | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs\alert_outbox_backup-check.jsonl
disk_check | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs\alert_outbox_disk-check.jsonl
restore_drill | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs\alert_outbox_restore-drill.jsonl
daily_data_check | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs | D:\My_Vault_Obsidian\Project\AI_auto_trading_system\logs\alert_outbox_daily-check.jsonl
```
Kết quả kiểm tra chuỗi: `EXACT MATCH CHAR-BY-CHAR: True`.

---

## 4. Tiêu chí 3: So sánh AST theo hàm
Ở cả 5 script, **không có bất kỳ hàm nào thay đổi** — chỉ phần thân module (import và hằng số):
```text
heartbeat_check  added [] removed [] changed []
backup_check     added [] removed [] changed []
disk_check       added [] removed [] changed []
restore_drill    added [] removed [] changed []
daily_data_check added [] removed [] changed []
_alert_common    added ['outbox_name', 'outbox_path'] removed [] changed []
_db_common       added [] removed [] changed []
```

---

## 5. Tiêu chí 4: Phá thử (Mutation Testing)

### Ca 1: Đổi nguồn chung thành đường dẫn tương đối theo `cwd` (`REPO_LOGS_DIR = os.path.join(".", "logs")`)
- **Dòng đỏ nguyên văn:**
  ```text
  FAILED tests/test_logs_dir_and_outbox_names.py::test_duong_dan_logs_KHONG_doi_khi_chay_tu_thu_muc_khac
  >           assert os.path.isabs(v), (m, v)
  E           AssertionError: ('heartbeat_check', '.\\logs')
  E           assert False
  E            +  where False = <function isabs at ...>('.\\logs')
  ```
- **Khôi phục hash:** Khớp 100%.

### Ca 2: Đổi khuôn tên file (bỏ dấu gạch dưới `alert_outbox{job}.jsonl`)
- **Dòng đỏ nguyên văn:**
  ```text
  FAILED tests/test_logs_dir_and_outbox_names.py::test_ten_file_hang_doi_nguyen_van_nhu_truoc[heartbeat_check]
  E       AssertionError: assert 'alert_outboxheartbeat.jsonl' == 'alert_outbox_heartbeat.jsonl'
  FAILED tests/test_logs_dir_and_outbox_names.py::test_ten_file_hang_doi_nguyen_van_nhu_truoc[backup_check]
  E       AssertionError: assert 'alert_outboxbackup-check.jsonl' == 'alert_outbox_backup-check.jsonl'
  FAILED tests/test_logs_dir_and_outbox_names.py::test_ten_file_hang_doi_nguyen_van_nhu_truoc[disk_check]
  E       AssertionError: assert 'alert_outboxdisk-check.jsonl' == 'alert_outbox_disk-check.jsonl'
  FAILED tests/test_logs_dir_and_outbox_names.py::test_ten_file_hang_doi_nguyen_van_nhu_truoc[restore_drill]
  E       AssertionError: assert 'alert_outboxrestore-drill.jsonl' == 'alert_outbox_restore-drill.jsonl'
  FAILED tests/test_logs_dir_and_outbox_names.py::test_ten_file_hang_doi_nguyen_van_nhu_truoc[daily_data_check]
  E       AssertionError: assert 'alert_outboxdaily-check.jsonl' == 'alert_outbox_daily-check.jsonl'
  FAILED tests/test_logs_dir_and_outbox_names.py::test_ham_dung_chung_cho_ra_ten_va_duong_dan_nguyen_van
  E       AssertionError: assert 'alert_outboxheartbeat.jsonl' == 'alert_outbox_heartbeat.jsonl'
  ```
- **Khôi phục hash:** Khớp 100%.

---

## 6. Tiêu chí 5: Kiểm tra Dry-run trên log thật (02:30 04/10/2026)
Chạy bằng Git Bash `scripts/sched.sh` ngoài các mốc lịch:
- `scripts/sched.sh heartbeat --dry-run` $\to$ `EXIT=1` (phát hiện `engine-consumer` mã 2 lịch sử, đúng kỳ vọng, không traceback).
- `scripts/sched.sh backup-check --dry-run` $\to$ `EXIT=0` (không traceback).
- `scripts/sched.sh disk-check --dry-run` $\to$ `EXIT=0` (không traceback).
- `logs/alert_outbox_*`: **0 file** tồn tại.

---

## 7. Tiêu chí 6: Bộ kiểm thử & Định dạng
- `ruff check .`: Sạch (0 error).
- `uv run pytest -q`: **1821 passed** in 85.44s, 0 failed (toàn bộ test suite).

---

## 8. Brief sai ở đâu / Điểm lệch / Cái gì không kiểm được
- **Điểm lưu ý:** `_alert_common.py` khi import nội bộ trong `scripts/` có cấu trúc try/except ImportError giữa `from scripts._alert_common` và `from _alert_common` để hỗ trợ cả khi chạy từ gốc repo lẫn khi chạy trực tiếp file từ thư mục `scripts/`. Cần áp dụng tương tự cho `_db_common`.
- **GitNexus:** MCP không sẵn sàng trong môi trường CLI của phiên này; đã thay thế và bảo đảm hoàn toàn bằng kiểm chứng AST phân tích cú pháp theo hàm.

---

## Audit của Claude (04/10/2026, ~06:30)

### A.1. Kết luận: ĐẠT. Claude xoá một hàm không ai gọi mà đợt này vừa thêm.

### A.2. Tiêu chí mạnh nhất của đợt — đạt
So AST theo hàm: ở cả năm script **không hàm nào** đổi, chỉ phần thân module. `_db_common.py` cũng chỉ
`<module>`. Đúng tính chất của một đợt gom.

### A.3. Claude tự so trước/sau, độc lập với bảng của agent
Claude lấy bản `HEAD` của bảy file ra một thư mục tạm, rồi import **cả hai bản** trong tiến trình riêng và
in ra hằng số:

```
CU : <goc-ban-tam>/logs   + alert_outbox_{heartbeat,backup-check,disk-check,restore-drill,daily-check}.jsonl
MOI: <goc-repo>/logs      + alert_outbox_{heartbeat,backup-check,disk-check,restore-drill,daily-check}.jsonl
```

Năm tên file **trùng từng ký tự**. Phần đường dẫn khác nhau **chính là bằng chứng** cho tính chất cần có:
hằng số đi theo **vị trí file**, không theo thư mục đang đứng — bản cũ nằm ở thư mục tạm nên trỏ vào gốc
thư mục tạm.

### A.4. Nguồn duy nhất, và không có vòng lặp import
- `REPO_LOGS_DIR` định nghĩa đúng **một** chỗ (`_db_common.py:19`); năm script chỉ gán lại.
- `_db_common.py` **chỉ thêm**, không đổi và không xoá gì — quan trọng vì 69 file đang import nó.
- `_alert_common.py` **không** import `_db_common`, nên không có vòng lặp.

### A.5. Phá thử của Claude (khác hai ca agent)

| Phá thử | Kết quả |
|---|---|
| `REPO_LOGS_DIR` lệch một cấp (thành `scripts/logs`) | **7 test đỏ** |
| `outbox_path` bỏ qua `logs_dir`, luôn ghi vào `logs/` thật | **1 test đỏ** |

### A.6. Hàm `outbox_path` không ai gọi — Claude xoá
Phá thử thứ hai chỉ bị **một** test bắt, và không test job nào bắt. Claude truy ra lý do: cả năm script dùng
`outbox_name(...)` (đúng mục tiêu: khuôn tên nằm một chỗ), nhưng **không script nào gọi `outbox_path(...)`** —
cả sáu chỗ vẫn tự ghép `Path(args.logs_dir) / OUTBOX_NAME`.

Đây đúng lớp lỗi của đợt 140–141: một hàm tồn tại, có test, mà đường chạy thật không đi qua. Nguy hiểm của nó
không phải hôm nay mà là mai sau: hàm chết nhìn như hàm sống, rồi lệch khỏi đường thật.

Claude **xoá `outbox_path`** cùng dòng khẳng định của nó. Không nối nó vào năm `main`, vì:
- phần trùng lặp còn lại là **một biểu thức tầm thường** ở sáu chỗ, không phải logic;
- thứ **phải** nhất quán là **tên file** (DEPLOYMENT.md §8.6 mô tả nó như quy ước), và tên đó đã nằm một chỗ;
- nối thêm sẽ đổi `main` của năm script sản xuất ngay sau một đợt vừa chứng minh không hàm nào đổi.

Sau khi xoá: `ruff` sạch, 33 test của hai file liên quan xanh, và không còn định nghĩa `outbox_path` nào
(ba lần còn lại chỉ là **tên tham số** của `send_with_outbox`).

### A.7. Chạy thật
`heartbeat --dry-run` ra `EXIT=1` với cảnh báo `engine-consumer` — **đúng như Claude dự báo trước đợt 156**,
và là tin đã biết nguyên nhân (phép thử cờ sai hôm 02/10), không phải sự cố mới.
`logs/alert_outbox_*`: không có file nào.
