# Báo cáo Đợt 146 — Gom phần đọc/ghi file trạng thái về một chỗ (_alert_common.py)

**Ngày thực hiện:** 02/10/2026  
**Giờ chép vào repo chính:** `2026-10-02 22:38:49` (ngoài khung giờ giao dịch 08:00–15:10, chuông đang chạy an toàn).  
**Các file sửa đổi:**
- `scripts/_alert_common.py`
- `scripts/container_health_check.py`
- `scripts/heartbeat_check.py`
- `scripts/engine_consumer_check.py`
- `tests/test_alert_common.py`
- `tests/test_engine_consumer_check.py`

**Quy tắc tuân thủ:** Không commit, không push, không restart/build container, không sửa task, không sửa `.env`, không gửi Telegram thật.

---

## 1. Mục tiêu & Vấn đề giải quyết

1. **Khử trùng lặp code đọc/ghi trạng thái:**
   - `scripts/container_health_check.py` (`load_state` / `save_state`) và `scripts/heartbeat_check.py` (`load_schedule_state` / `save_schedule_state`) có thân hàm giống hệt nhau tới 95%, chỉ khác nhãn log (`[container-health]` vs `[heartbeat]`).
2. **Sửa lỗi tiềm ẩn của `engine_consumer_check.py`:**
   - Code cũ đọc file trạng thái bằng `json.loads` nhưng không kiểm tra `isinstance(data, dict)`. Khi file chứa `[]` hoặc danh sách rỗng, `prev_state.get(...)` sẽ ném `AttributeError: 'list' object has no attribute 'get'` giữa phiên giao dịch.
   - Code cũ ghi thẳng bằng `write_text` không qua file tạm `.tmp`, nếu tiến trình bị kill giữa chừng sẽ để lại file dở dang.
   - Đường dẫn `STATE_FILE` bị ghim cứng, test không thể tiêm đường dẫn độc lập qua CLI.
3. **Giữ nguyên `docker_down_alert.py`:**
   - File `.docker_down_last_alert` chỉ lưu một số epoch, không phải JSON. Đúng như brief chỉ thị: giữ nguyên có chủ ý để không làm hỏng dữ liệu hiện có trên đĩa.

---

## 2. Quy trình Git Worktree độc lập

Để đảm bảo an toàn tuyệt đối cho chuông `container-health` đang chạy ngầm mỗi 10 phút trên host:
1. Tạo git worktree riêng:
   ```bash
   git worktree add --detach D:\My_Vault_Obsidian\Project\AI_auto_trading_system_wt146 HEAD
   ```
2. Thực hiện toàn bộ việc viết code, bổ sung test, kiểm tra ruff và chạy trọn bộ 1.745 test trong worktree.
3. Chép toàn bộ 6 file đã kiểm thử sang repo chính đồng thời lúc **22:38:49**.
4. Lập tức kiểm tra các kịch bản chạy thật tại Tiêu chí 5.
5. Dọn dẹp worktree an toàn:
   ```bash
   git worktree remove --force D:\My_Vault_Obsidian\Project\AI_auto_trading_system_wt146
   ```
   Kết quả lệnh `git worktree list`:
   ```text
   D:/My_Vault_Obsidian/Project/AI_auto_trading_system 5a38cf1 [main]
   ```
   Chỉ còn lại duy nhất repo chính.

---

## 3. Bảng so sánh AST (theo hàm giữa HEAD và bản mới)

Kiểm tra bằng công cụ AST (`ast.parse` và so khớp `ast.dump` của từng `FunctionDef`/`AsyncFunctionDef`):

| File | Danh sách hàm có AST khác biệt | Đánh giá |
| :--- | :--- | :--- |
| `scripts/container_health_check.py` | `['load_state', 'save_state']` | Chuẩn: chỉ 2 hàm đọc/ghi trạng thái ủy quyền sang `_alert_common.py`. Các hàm khác giống 100%. |
| `scripts/heartbeat_check.py` | `['load_schedule_state', 'save_schedule_state']` | Chuẩn: chỉ 2 hàm đọc/ghi trạng thái ủy quyền sang `_alert_common.py`. Các hàm khác giống 100%. |
| `scripts/engine_consumer_check.py` | `['build_parser', 'load_state', 'main', 'run_check', 'save_state']` | Chuẩn: thêm cờ `--state-file` vào parser, nhận cờ ở `main`, truyền xuống `run_check`, `load_state` và `save_state`. Câu đầu của `main` vẫn là `args = build_parser().parse_args(argv)`. |

---

## 4. Phân loại hành vi bắt / không bắt lỗi ghi (`save_json_state`)

Hàm chung `save_json_state(path, state)` tạo thư mục cha (`p.parent.mkdir(parents=True, exist_ok=True)`), ghi file `.tmp` và đổi tên nguyên tử bằng `os.replace`. Nếu xảy ra lỗi ghi/replace, lỗi được ném lên để từng caller xử lý:

| Caller | Hàm bọc | Bắt lỗi hay để ném? | Rationale |
| :--- | :--- | :--- | :--- |
| `container_health_check.py` | `save_state` | **KHÔNG BẮT (để lỗi ném lên)** | Nếu không lưu được trạng thái mốc, tiến trình cần thoát lỗi (mã 2) để quản trị viên phát hiện sự cố đĩa. |
| `heartbeat_check.py` | `save_schedule_state` | **KHÔNG BẮT (để lỗi ném lên)** | Giữ nguyên hành vi cũ: lỗi ghi file trạng thái lịch chạy cần được cảnh báo ra ngoài. |
| `engine_consumer_check.py` | `save_state` | **CÓ BẮT (`try...except`)** | Giữ nguyên hành vi cũ: bắt ngoại lệ ghi và in `_print_safe(f"[engine-consumer] Không thể ghi file state: {e}")`, không làm crash luồng kiểm tra chính. |

---

## 5. Bằng chứng lỗi có thật trên code cũ trước khi sửa

Khi file trạng thái `.engine_consumer_last_check` chứa `[]`:
- **Code cũ:**
  ```python
  def load_state() -> dict:
      if not STATE_FILE.exists():
          return {}
      try:
          return json.loads(STATE_FILE.read_text(encoding="utf-8"))
      except Exception:
          return {}
  ```
  `json.loads("[]")` trả về `list`. Sau đó tại dòng 166:
  `last_alert_ts = prev_state.get("last_alert_ts", 0)`
  Ném ngoại lệ:
  ```text
  AttributeError: 'list' object has no attribute 'get'
  ```
- **Code mới sau khi dùng `load_json_state`:**
  Kiểm tra `isinstance(data, dict)`, phát hiện `[]` không phải `dict`, in thông báo cảnh báo và trả về `{}` an toàn, script chạy trôi chảy exit 0.

---

## 6. Kết quả phá thử (Mutation Testing) & Đối chiếu SHA-256 Hash

### 6.1. Phá thử 1: `save_json_state` ghi thẳng file đích (bỏ `.tmp`)
- **Cách thực hiện:** Thay vì ghi `.tmp` rồi `os.replace`, ghi trực tiếp vào `p`.
- **Lệnh chạy:** `uv run pytest tests/test_alert_common.py -k "test_save_json_state_ngat_giua_chung" -v --tb=line`
- **Nguyên văn dòng đỏ:**
  ```text
  E   Failed: DID NOT RAISE OSError
  D:\My_Vault_Obsidian\Project\AI_auto_trading_system_wt146\tests\test_alert_common.py:103: Failed: DID NOT RAISE OSError
  FAILED tests/test_alert_common.py::test_save_json_state_ngat_giua_chung_khong_lam_do_file_dich
  ```
- **Ý nghĩa:** Khi không có cơ chế ghi qua file tạm và `os.replace`, việc ghi không còn tính nguyên tử, file đích bị ghi đè trực tiếp và test phát hiện lỗi ngay.

### 6.2. Phá thử 2: `load_json_state` bỏ kiểm `dict`
- **Cách thực hiện:** Bỏ dòng `if isinstance(data, dict): return data`, trả về `data` trực tiếp.
- **Lệnh chạy:** `uv run pytest tests/test_alert_common.py -k "test_load_json_state_json_la_list" -v --tb=line`
- **Nguyên văn dòng đỏ:**
  ```text
  E   assert [1, 2, 3] == {}
        Full diff:
        - {}
        + [
        +     1,
        +     2,
        +     3,
        + ]
  D:\My_Vault_Obsidian\Project\AI_auto_trading_system_wt146\tests\test_alert_common.py:70: assert [1, 2, 3] == {}
  FAILED tests/test_alert_common.py::test_load_json_state_json_la_list - assert...
  ```
- **Ý nghĩa:** Khi file chứa list, hàm không ép về `{}` mà trả về `list`, gây lỗi cho các hàm gọi phía sau.

### 6.3. Phá thử 3: Đổi câu cảnh báo của `load_json_state`
- **Cách thực hiện:** Đổi chuỗi cảnh báo thành `f"[{label}] File trạng thái {path} SAI DINH DANG DICT"`.
- **Lệnh chạy:** `uv run pytest tests/test_alert_common.py -k "test_load_json_state_json_la_list" -v --tb=line`
- **Nguyên văn dòng đỏ:**
  ```text
  E   AssertionError: assert 'không đúng định dạng dict — coi như lần đầu.' in '[test-label] File trạng thái ...list.json SAI DINH DANG DICT\n'
  D:\My_Vault_Obsidian\Project\AI_auto_trading_system_wt146\tests\test_alert_common.py:73: AssertionError: assert 'không đúng định dạng dict — coi như lần đầu.' in '[test-label] File trạng thái ...list.json SAI DINH DANG DICT\n'
  FAILED tests/test_alert_common.py::test_load_json_state_json_la_list - Assert...
  ```
- **Ý nghĩa:** Đảm bảo câu cảnh báo in ra giữ nguyên 100% định dạng cũ của các job để không làm lệch công cụ giám sát log.

### 6.4. Đối chiếu SHA-256 Hash trước và sau khôi phục
- Hash ban đầu: `C5212EE04F0C40F2F3DD2BE44A67491EA94843A9CA87FCE92ABF1B6D0991A90E`
- Hash sau khôi phục: `C5212EE04F0C40F2F3DD2BE44A67491EA94843A9CA87FCE92ABF1B6D0991A90E`
- **Khớp 100%, không sai lệch 1 byte.**

---

## 7. Số đo nguyên văn kiểm tra sau khi chép vào repo chính

Ngay sau khi chép vào repo chính lúc 22:38:49:

1. **`scripts/sched.sh heartbeat --dry-run`**:
   - Log: `logs/heartbeat.log`
   ```text
   2026-10-02 22:38:56 heartbeat-check start
   EXIT=0
   ```
   - Không có traceback, không có thông báo "ĐÃ CHẠY LẠI" oan.

2. **`scripts/sched.sh engine-consumer --khong-ton-tai`**:
   - Log: `logs/engine-consumer.log`
   ```text
   2026-10-02 22:38:59 engine-consumer start
   usage: engine_consumer_check.py [-h] [--config CONFIG] [--force]
                                   [--threshold THRESHOLD]
                                   [--state-file STATE_FILE]
   engine_consumer_check.py: error: unrecognized arguments: --khong-ton-tai
   EXIT=2
   ```
   - Chết mã 2 đúng chuẩn tại argparse.

3. **`scripts/sched.sh container-health --dry-run --state-file /tmp/ch_test.json`**:
   - Log: `logs/container-health.log`
   ```text
   2026-10-02 22:39:39 container-health start
   [container-health] Ghi mốc ban đầu cho ai_auto_trading_system-postgres-1: Id=676fbd0fea81, RestartCount=0, oom_kill=0, max=0
   [container-health] Ghi mốc ban đầu cho ai_auto_trading_system-collector-1: Id=33dbfae09611, RestartCount=0, oom_kill=0, max=0
   [container-health] Ghi mốc ban đầu cho ai_auto_trading_system-engine-1: Id=eb77e3e15d17, RestartCount=0, oom_kill=0, max=0
   [container-health] Ghi mốc ban đầu cho ai_auto_trading_system-nats-1: Id=65a74a6f298d, RestartCount=0, oom_kill=0, max=0
   [container-health] Ghi mốc ban đầu cho ai_auto_trading_system-grafana-1: Id=ce58d7e8ade8, RestartCount=0, oom_kill=0, max=0
   EXIT=0
   ```
   - Không có traceback, thoát 0 chuẩn xác.

4. **Lần chạy theo lịch thật kế tiếp của `container-health` (22:40:03)**:
   - Log: `logs/container-health.log`
   ```text
   2026-10-02 22:40:03 container-health start
   EXIT=0
   ```
   - Chuông thật chạy tự động, dùng code mới, hoàn thành với `EXIT=0`.

---

## 8. Kiểm tra toàn hệ thống

1. **Ruff linter:**
   - Lệnh: `uv run ruff check trading tests scripts`
   - Kết quả: `All checks passed!`
2. **Bộ test toàn hệ thống:**
   - Lệnh: `uv run pytest -q`
   - Kết quả: **1745 passed in 126.95s (0:02:06)** (đạt $\ge$ 1.737, tăng +8 test gồm 6 test `_alert_common` và 2 test `engine_consumer_check`).
3. **Lưới an toàn Đợt 145:**
   - Không đỏ. Không có bất kỳ test nào ghi đè vào các file trạng thái thật trong `logs/`.
4. **GitNexus detect-changes:**
   - Lệnh: `npx gitnexus detect-changes --repo AI_auto_trading_system`
   - Kết quả: `Changes: 6 files, 11 symbols. Affected processes: 1. Risk level: medium.` Đúng trong phạm vi dự kiến.

---

## 9. Nhận xét & Đánh giá Brief

1. **Về tiêu chí `scripts/sched.sh container-health --dry-run` → `EXIT=0`:**
   - Brief ghi tiêu chí này nhưng thực tế trong thiết kế của `container_health_check.py` từ Đợt 130 (§1c), cờ `--dry-run` **bắt buộc** phải đi kèm `--state-file <đường_dẫn_tạm>` (nếu không có sẽ in lỗi `LỖI: --dry-run bắt buộc đi kèm --state-file <đường_dẫn_tạm>` và thoát mã 2). Đây là cơ chế chốt chặn cố ý để không cho phép chạy thử nghiệm chạm vào file trạng thái thật.
   - Khi chạy đúng quy định với `--state-file`, lệnh trả về `EXIT=0` chuẩn xác.
2. **Về việc không thể kiểm tra:**
   - Không thể kiểm tra sự cố ổ cứng vật lý bị hỏng hoặc đầy 100% ngoài đời thực trên máy chủ production vì điều này sẽ gây gián đoạn hệ thống live containers. Việc này đã được kiểm chứng tin cậy thông qua monkeypatch `os.replace` trong unit test.

---

## Audit của Claude (02/10/2026, 22:55)

### A.1. Kết luận: NHẬN. Hành vi thật đúng; bộ test thiếu hai chỗ ghim, giao đợt 147.

### A.2. Kiểm độc lập

- **So AST theo hàm (`HEAD` với cây làm việc):** `container_health_check` chỉ khác `load_state`, `save_state`; `heartbeat_check` chỉ khác `load_schedule_state`, `save_schedule_state`; `engine_consumer_check` khác `build_parser`, `load_state`, `main`, `run_check`, `save_state`. Đúng phạm vi brief.
- **File trạng thái thật của `container-health` còn nguyên.** Log có `Ghi mốc ban đầu` cho cả 5 container lúc 22:39:39. Claude kiểm: đó là lần `sched.sh container-health --dry-run --state-file /tmp/ch_test.json`, tức ghi mốc vào file tạm. File thật `logs/.container_health_state.json` giữ đúng Id cả 5 container, được lần chạy lịch 22:40:03 (`EXIT=0`) cập nhật mà không ghi mốc lại.
- `logs/.engine_consumer_last_check` thật: mtime trước và sau toàn bộ audit đều là `14:40:09`, không bị test chạm.
- `ruff` sạch; **1.745 passed**.

### A.3. Brief sai — agent xử lý đúng

Brief ghi `scripts/sched.sh container-health --dry-run`, nhưng từ đợt 130 `--dry-run` của script này **bắt buộc** đi kèm `--state-file`. Lần chạy 22:38:51 ra `EXIT=2` đúng thiết kế; agent đọc lỗi và chạy lại có `--state-file` tạm.

### A.4. Hai phá thử của Claude SỐNG SÓT (21/21 xanh)

| Phá thử | Kết quả |
|---|---|
| `main` truyền `state_file=None` thay vì `args.state_file` (bỏ qua cờ, ghi đường dẫn thật) | **21 passed** |
| `save_state` đổi `except Exception` thành `except ZeroDivisionError` (lỗi ghi làm chết job) | **21 passed** |

1. `test_state_file_cli_flag` kiểm parser **nhận** cờ, không kiểm `main` **truyền** cờ xuống `run_check`. Đúng họ lỗi đợt 140 (parser có nhưng không ai chứng minh nó được dùng).
2. Brief bắt "giữ nguyên hành vi bắt lỗi ghi" của `engine_consumer_check`, nhưng không test nào ghim hành vi đó.

Code hiện tại làm đúng cả hai; chỉ thiếu test. Hash khôi phục trùng `991acf8974e4cd2d`.

