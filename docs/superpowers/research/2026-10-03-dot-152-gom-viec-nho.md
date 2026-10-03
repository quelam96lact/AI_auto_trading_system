# Báo Cáo Nghiên Cứu & Triển Khai — Đợt 152: Gom Việc Nhỏ (Dotenv, Cổng Go-Live, Test Heartbeat)

**Thời gian thực hiện:** 2026-10-03  
**Kế hoạch thực hiện:** `docs/superpowers/plans/2026-10-03-brief-dot-152-gom-viec-nho-dotenv-cong-golive-test-heartbeat.md`  
**Trạng thái:** HOÀN THÀNH TOÀN BỘ (9/9 files, không commit, không push)

---

## 1. Tóm Tắt Kết Quả Đo Lường & Trạng Thái

- **Bộ kiểm thử toàn diện:** `1763 passed in 122.84s (0:02:02)` (Baseline: 1.762 passed, tăng đúng 1 test mới `test_main_loads_dotenv_even_with_dsn_override`, 0 failed).
- **Linter ruff:** `All checks passed!` trên toàn bộ `trading`, `tests`, `scripts`.
- **Kiểm tra tiến trình nền:** Lệnh kiểm tra tiến trình `pytest` rỗng trước khi chạy suite.
- **Job import an toàn:** `uv run python -c "import scripts.record_vn30f_orderbook, scripts.check_orderbook_daily"` thoát mã `0` thành công.
- **Kiểm tra gom hàm `_load_dotenv`:**
  - `grep -rn "def _load_dotenv" scripts`: **0 dòng**.
  - Kiểm tra đẳng thức đối tượng `mod._load_dotenv is scripts._db_common.load_dotenv`: **True × 6**.
- **Hai lần chạy cổng thật:** Tiêu chí 7 cho kết quả giống hệt nhau `[ĐẠT]` ở cả 2 trường hợp.

---

## 2. Chi Tiết Thực Hiện Từng Việc

### Việc 1 — Cổng go-live không còn đỏ giả mục Telegram khi chạy với `--dsn`
- **Hiện tượng cũ:** Khi chạy `check_golive_gate.py --dsn <DSN>`, hàm `scripts/_db_common.py::resolve_dsn` chỉ gọi `load_dotenv()` khi không có override. Do đó, `os.environ` không có biến Telegram và cổng báo `THIẾU BIẾN MÔI TRƯỜNG ... [CHẶN]`, trong khi chạy không `--dsn` thì lại `[ĐẠT]`.
- **Xử lý:** Trong `scripts/check_golive_gate.py::main`, nạp `load_dotenv()` vô điều kiện trước khi gọi `resolve_dsn`:
  ```python
  try:
      from _db_common import load_dotenv, resolve_dsn
  except ImportError:
      from scripts._db_common import load_dotenv, resolve_dsn

  load_dotenv()
  dsn = resolve_dsn(args.dsn)
  ```
- **Viết test kiểm chứng:** Thêm `test_main_loads_dotenv_even_with_dsn_override` vào `tests/test_check_golive_gate.py` spy hàm `load_dotenv` để khẳng định luôn được gọi dù có `--dsn`.

#### Nguyên văn dòng mục 7 của 2 lần chạy cổng thật:
1. **Chạy không `--dsn`:**
   ```text
   7   | Đường truyền Telegram            | ĐÃ CẤU HÌNH                    | [ĐẠT]      | Không gửi tin kiểm tra, chỉ kiểm cấu hình môi trường
   ```
2. **Chạy có `--dsn` (`--dsn postgresql://trading:trading@localhost:5432/trading`):**
   ```text
   7   | Đường truyền Telegram            | ĐÃ CẤU HÌNH                    | [ĐẠT]      | Không gửi tin kiểm tra, chỉ kiểm cấu hình môi trường
   ```
*(Cả hai lần chạy đều in chính xác `ĐÃ CẤU HÌNH | [ĐẠT]`)*

---

### Việc 2 — Gom 6 bản sao `_load_dotenv` về `_db_common.load_dotenv`
- **6 file được gom:**
  1. `scripts/build_derivative_continuous_series.py`
  2. `scripts/check_orderbook_daily.py`
  3. `scripts/probe_account_balance_22h.py`
  4. `scripts/record_vn30f_orderbook.py`
  5. `scripts/screen_vn30f_intraday.py`
  6. `scripts/verify_orderbook_file.py`
- **Hành động:**
  - Xóa bỏ định nghĩa hàm trùng lặp `def _load_dotenv(env_path: str = ".env") -> None:`.
  - Thay bằng import an toàn:
    ```python
    try:
        from _db_common import load_dotenv as _load_dotenv
    except ImportError:
        from scripts._db_common import load_dotenv as _load_dotenv
    ```
  - Giữ nguyên định danh `_load_dotenv` ở cấp module để tương thích hoàn toàn với monkeypatch tại `tests/test_collector_logging.py:87`.
  - Xóa `import os` thừa ở 5 file (`check_orderbook_daily.py`, `probe_account_balance_22h.py`, `record_vn30f_orderbook.py`, `screen_vn30f_intraday.py`, `verify_orderbook_file.py`). Riêng `build_derivative_continuous_series.py` giữ lại `import os` do dùng `os.environ.get("SSI_API_KEY")`.

#### Kết quả kiểm tra đối tượng hàm:
Chạy script kiểm tra:
```python
import scripts._db_common as dbc
import scripts.build_derivative_continuous_series as s1
import scripts.check_orderbook_daily as s2
import scripts.probe_account_balance_22h as s3
import scripts.record_vn30f_orderbook as s4
import scripts.screen_vn30f_intraday as s5
import scripts.verify_orderbook_file as s6

for name, mod in [
    ("build_derivative_continuous_series", s1),
    ("check_orderbook_daily", s2),
    ("probe_account_balance_22h", s3),
    ("record_vn30f_orderbook", s4),
    ("screen_vn30f_intraday", s5),
    ("verify_orderbook_file", s6),
]:
    is_same = mod._load_dotenv is dbc.load_dotenv
    print(f"{name}: mod._load_dotenv is dbc.load_dotenv -> {is_same}")
```
Output:
```text
build_derivative_continuous_series: mod._load_dotenv is dbc.load_dotenv -> True
check_orderbook_daily: mod._load_dotenv is dbc.load_dotenv -> True
probe_account_balance_22h: mod._load_dotenv is dbc.load_dotenv -> True
record_vn30f_orderbook: mod._load_dotenv is dbc.load_dotenv -> True
screen_vn30f_intraday: mod._load_dotenv is dbc.load_dotenv -> True
verify_orderbook_file: mod._load_dotenv is dbc.load_dotenv -> True
```
Grep trong thư mục `scripts/`:
```text
grep -rn "def _load_dotenv" scripts
-> 0 dòng
```
Test `tests/test_collector_logging.py`: **5 passed in 1.81s**.

---

### Việc 3 — Test heartbeat không gắn cứng số tài khoản
- **Hiện tượng cũ:** `tests/test_heartbeat_check.py` gắn cứng assert `"0434226"` ở các dòng kiểm tra thông báo cảnh báo (test `test_main_alerts_when_position_sync_stale`, `test_main_never_synced_message_has_no_arithmetic`, `test_main_prints_message_to_stdout_before_sending`). Khi đổi tài khoản cấu hình trong `config/config.yaml`, các test này bị fail.
- **Xử lý:** Thêm helper trong `tests/test_heartbeat_check.py`:
  ```python
  def _expected_real_order_account() -> str:
      """Đọc real_order_account từ config/config.yaml giống cách heartbeat_check đọc (Brief 152 Việc 3)."""
      import yaml

      cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml")
      with open(cfg_path, encoding="utf-8") as f:
          cfg = yaml.safe_load(f)
      return cfg["real_order_account"]
  ```
  Thay thế 3 assert cứng `"0434226"` thành `assert _expected_real_order_account() in msg`.

---

## 3. Ba Phá Thử — Dòng Đỏ Nguyên Văn & Đối Chiếu Hash Khôi Phục

### Phá Thử 1 (Việc 1: Cổng Go-Live `--dsn`)
- **Thao tác phá thử:** Đưa lệnh `load_dotenv()` trong `scripts/check_golive_gate.py` vào bên trong khối `if not args.dsn:` (mô phỏng lại hành vi cũ).
- **Dòng đỏ nguyên văn:**
  ```text
  FAILED tests/test_check_golive_gate.py::test_main_loads_dotenv_even_with_dsn_override - AssertionError: load_dotenv() phai duoc goi ke ca khi co --dsn
  assert False is True
  ```
- **Khôi phục & Đối chiếu Hash:**
  - Hash baseline trước phá thử: `7B111C8639238F84652975632C1A2CA9E2728E8B22887E1810EFC57E50052106`
  - Hash sau khi khôi phục: `7B111C8639238F84652975632C1A2CA9E2728E8B22887E1810EFC57E50052106`
  - **Khớp 100%**.

### Phá Thử 2 (Việc 2: Tên `_load_dotenv` trong module)
- **Thao tác phá thử:** Tạm thời comment out dòng gán `_load_dotenv` trong `scripts/record_vn30f_orderbook.py`.
- **Dòng đỏ nguyên văn:**
  ```text
  FAILED tests/test_collector_logging.py::test_record_vn30f_orderbook_has_no_console_handler - AttributeError: <module 'scripts.record_vn30f_orderbook' from 'D:\\My_Vault_Obsidian\\Project\\AI_auto_trading_system_wt152\\scripts\\record_vn30f_orderbook.py'> has no attribute '_load_dotenv'
  ```
- **Khôi phục & Đối chiếu Hash:**
  - Hash baseline trước phá thử: `2F32E7143E067BC035A4E6005DB126472E65FEC22E43E21A6D1F45A9F110340D`
  - Hash sau khi khôi phục: `2F32E7143E067BC035A4E6005DB126472E65FEC22E43E21A6D1F45A9F110340D`
  - **Khớp 100%**.

### Phá Thử 3 (Việc 3: Test Heartbeat Assert Động Theo Config)
- **Thao tác phá thử:** Monkeypatch hàm `_expected_real_order_account()` tạm thời trả về `"9999999"` thay vì đọc từ config thật.
- **Dòng đỏ nguyên văn:**
  ```text
  FAILED tests/test_heartbeat_check.py::test_main_alerts_when_position_sync_stale - AssertionError: tin nhan phai chua ten tai khoan, thuc te: [CRITICAL] vị thế 0434226 ngừng đồng bộ: lần cuối 2026-08-14 09:40:00+07:00 (20 phút trước)
  assert '9999999' in '[CRITICAL] vị thế 0434226 ngừng đồng bộ: lần cuối 2026-08-14 09:40:00+07:00 (20 phút trước)'
  ```
- **Khôi phục & Đối chiếu Hash:**
  - Hash baseline trước phá thử: `8434FBF1D6BF2500CF1B8FDA3218AB48B32A7AC9F3C574EF6FBB851BDC12D99A`
  - Hash sau khi khôi phục: `8434FBF1D6BF2500CF1B8FDA3218AB48B32A7AC9F3C574EF6FBB851BDC12D99A`
  - **Khớp 100%**.

---

## 4. Kiểm Tra AST Theo Hàm (Git Diff)

So sánh giữa `HEAD` và bản sửa đổi cho thấy:
- **`scripts/check_golive_gate.py`:** Chỉ hàm `main()` thay đổi: thêm import `load_dotenv` và gọi `load_dotenv()` trước `resolve_dsn`.
- **6 file scripts (`build_derivative_continuous_series.py`, `check_orderbook_daily.py`, `probe_account_balance_22h.py`, `record_vn30f_orderbook.py`, `screen_vn30f_intraday.py`, `verify_orderbook_file.py`):**
  - Mất duy nhất hàm `_load_dotenv` định nghĩa thủ công.
  - Thêm khối `try: from _db_common import load_dotenv as _load_dotenv except ImportError: ...`.
  - Bỏ `import os` ở 5 file không còn dùng `os`.
  - Không có bất kỳ hàm nghiệp vụ nào khác bị thay đổi cấu trúc AST.
- **`tests/test_check_golive_gate.py`:** Thêm duy nhất 1 hàm test mới `test_main_loads_dotenv_even_with_dsn_override`.
- **`tests/test_heartbeat_check.py`:** Thêm helper `_expected_real_order_account()` và sửa 3 dòng assert sử dụng helper.

---

## 5. Phân Tích GitNexus

1. **Impact Analysis ban đầu:**
   - `scripts/_db_common.py::resolve_dsn`: HIGH risk, 66 call sites trên toàn bộ scripts. Quyết định không sửa `resolve_dsn` là hoàn toàn chính xác để tránh blast radius.
   - `scripts/_db_common.py::load_dotenv`: HIGH risk, được gọi từ nhiều entrypoints. Hàm dùng chung đã ổn định.
   - `scripts/check_golive_gate.py::main`: LOW risk, chỉ là CLI entrypoint.
2. **Detect Changes sau khi hoàn tất:**
   - Lệnh: `npx gitnexus detect-changes --repo AI_auto_trading_system`
   - Kết quả:
     ```text
     Changes: 9 files, 12 symbols
     Affected processes: 0
     Risk level: low

     Changed symbols:
       undefined line → scripts/build_derivative_continuous_series.py
       undefined _load_dotenv → scripts/build_derivative_continuous_series.py
       undefined main → scripts/check_golive_gate.py
       undefined _load_dotenv → scripts/check_orderbook_daily.py
       undefined _load_dotenv → scripts/probe_account_balance_22h.py
       undefined _load_dotenv → scripts/record_vn30f_orderbook.py
       undefined _load_dotenv → scripts/screen_vn30f_intraday.py
       undefined _load_dotenv → scripts/verify_orderbook_file.py
       undefined test_main_alerts_when_position_sync_stale → tests/test_heartbeat_check.py
       undefined test_main_never_synced_message_has_no_arithmetic → tests/test_heartbeat_check.py
       undefined test_main_prints_message_to_stdout_before_sending → tests/test_heartbeat_check.py
       undefined test_main_still_sends_telegram_when_stdout_cannot_encode → tests/test_heartbeat_check.py
     ```
   - Xác nhận: Không ảnh hưởng đến bất kỳ quy trình nghiệp vụ (processes) nào của trading engine. Risk level: **low**.

---

## 6. Đánh Giá Brief: Sai Ở Đâu & Cái Gì Không Kiểm Được

1. **Brief sai / chưa tính hết ở đâu:**
   - **Về lệnh GitNexus CLI đa repo:** Brief gợi ý `npx --no-install gitnexus detect_changes`. Tuy nhiên trên máy người dùng có nhiều repository được index (`Radio_manager`, `auto_trading_system`, `AI_auto_trading_system`), nên GitNexus CLI bắt buộc phải truyền tham số `--repo AI_auto_trading_system`, nếu không sẽ crash với lỗi `Multiple repositories indexed`.
   - **Về thứ tự import linter:** Khi thêm test vào `tests/test_check_golive_gate.py`, linter `ruff` yêu cầu tuân thủ nghiêm ngặt quy tắc `I001` (sắp xếp import block: chuẩn thư viện python `sys`, dòng trống, `pytest`, dòng trống, sau đó mới đến các module nội bộ `scripts._db_common`, `scripts.check_golive_gate`).
2. **Cái gì không kiểm được:**
   - Tiêu chí 8 (Lệch triển khai Image vs Git) trên bảng kiểm định cổng: hiển thị `[CHẶN]` do Docker container collector/engine chưa được build lại với code git mới nhất. Đúng như brief đã nêu rõ: việc build container thuộc về người vận hành hệ thống trước khi go-live, không thuộc phạm vi của agent trong brief này.
   - Không chạy lệnh thực tế gửi tin Telegram thật (`--send`) và không mở socket SSI thật để tuân thủ tuyệt đối quy định an toàn vốn.

---

## Audit của Claude (03/10/2026)

**ĐẠT.**

- **AST theo hàm:** sáu file Việc 2 chỉ khác ở `<module>` (phần import) và mất `_load_dotenv`.
  `check_golive_gate.py` chỉ khác ở `main`. Hai file test chỉ có thêm helper và đổi assert.
- **Đồng nhất đối tượng:** Claude tự chạy, `mod._load_dotenv is _db_common.load_dotenv` ra `True` ×6 khi
  import dạng `scripts.<tên>`.
- **Chạy theo cách job theo lịch khởi động script** (`sys.path[0] = scripts/`, nhánh `from _db_common`):
  Claude import `record_vn30f_orderbook` và `check_orderbook_daily` từ thư mục `scripts/`, cả hai `True`.
  Đây là nhánh import mà test (dạng `scripts.<tên>`) không đi qua.
- **Cổng chạy thật**, cả có lẫn không `--dsn`: mục 7 đều `ĐÃ CẤU HÌNH [ĐẠT]`.
- `ruff` sạch.

