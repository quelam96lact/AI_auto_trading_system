# Báo cáo Nghiệm thu Brief Đợt 140 — Cờ gõ khi chạy tay phải CÓ HIỆU LỰC hoặc BÁO LỖI

## 1. Tổng quan & Mục tiêu

- **Mục tiêu:** Một cờ gõ vào hoặc có hiệu lực, hoặc làm lệnh chết với mã ≠ 0 **TRƯỚC** khi làm bất cứ việc gì (không chạm DB, Docker, mạng hay Telegram).
- **Phạm vi hoàn thành:**
  - `scripts/sched.sh`: Cả 16 nhánh đều có `shift || true` và chuyển đầy đủ `"$@"`.
  - 14 Python scripts được gọi bởi `sched.sh`: Chuẩn hóa hàm `build_parser() -> argparse.ArgumentParser` và gọi phân tích tham số trước mọi logic nghiệp vụ. Cờ lạ chết với mã 2 (argparse `SystemExit: 2`).
  - 2 Shell scripts (`backup_db.sh`, `backup_orderbook.sh`): Thêm kiểm tra cờ lạ `[[ "$1" == -* ]]` và cấm dư tham số `$# -gt 1`, thoát mã 2.
  - `scripts/daily_data_check.py`: Bổ sung cờ `--dry-run` để chạy bù an toàn, in log chi tiết và bỏ qua gửi Telegram.
  - `DEPLOYMENT.md`: Thêm mục `9.6 Chạy bù sau khi máy hoặc Docker tắt` kèm bảng phân tích quy tắc chạy bù cho cả 16 job, bài học sự cố 02/10 và lưu ý múi giờ psql `(ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`.
  - `tests/test_sched_args.py`: Bộ kiểm thử tự động 17 test cases (kiểm tra tĩnh toàn bộ nhánh `sched.sh`, kiểm tra động mọi script Python và Shell script từ chối cờ lạ, kiểm tra cờ `--dry-run`). Đã thực hiện phá thử (mutation testing) thành công cả 2 kịch bản.

---

## 2. Bảng tổng hợp 16 nhánh của `scripts/sched.sh`

| STT | Nhánh `sched.sh` | Lệnh / Script thực thi | Chuyển `"$@"` (Trước đợt) | Chuyển `"$@"` (Sau đợt) | Script có parser trước đợt? | Script có parser sau đợt? | Cờ lạ có chết to chưa? (Mã thoát & Hành vi) |
|:---:|:---|:---|:---:|:---:|:---:|:---:|:---|
| 1 | `heartbeat` | `scripts/heartbeat_check.py` | ❌ Không | ✅ Có | ❌ Không có parser | ✅ `build_parser()` | ✅ Thoát mã 2 (Argparse error, chết trước khi chạm DB/Telegram) |
| 2 | `disk` | `scripts/disk_check.py` | ✅ Có | ✅ Có | ⚠️ Inline parser | ✅ `build_parser()` | ✅ Thoát mã 2 (Chết trước khi kiểm tra ổ đĩa/Telegram) |
| 3 | `orderbook` | `scripts/record_vn30f_orderbook.py` | ✅ Có | ✅ Có | ⚠️ Inline parser | ✅ `build_parser()` | ✅ Thoát mã 2 (Chết trước khi kết nối websocket SSI) |
| 4 | `orderbook-daily` | `scripts/check_orderbook_daily.py` | ✅ Có | ✅ Có | ⚠️ Inline parser | ✅ `build_parser()` | ✅ Thoát mã 2 (Chết trước khi quét file orderbook/Telegram) |
| 5 | `engine-cam` | `scripts/check_silent_engine.py` | ❌ Không | ✅ Có | ⚠️ Inline parser | ✅ `build_parser()` | ✅ Thoát mã 2 (Chết trước khi query DB/Telegram) |
| 6 | `engine-consumer` | `scripts/engine_consumer_check.py` | ❌ Không | ✅ Có | ⚠️ Inline parser | ✅ `build_parser()` | ✅ Thoát mã 2 (Chết trước khi query NATS/Telegram) |
| 7 | `stream` | `scripts/stream_health_check.py` | ✅ Có | ✅ Có | ⚠️ Inline parser | ✅ `build_parser()` | ✅ Thoát mã 2 (Chết trước khi query Redis/Telegram) |
| 8 | `daily-check` | `scripts/daily_data_check.py` | ❌ Không | ✅ Có | ⚠️ Có `--dsn`, `--date` | ✅ `build_parser()` + `--dry-run` | ✅ Thoát mã 2 (Chết trước khi query DB/Telegram) |
| 9 | `backfill` | `scripts/backfill_universe.py` | ❌ Không | ✅ Có | ⚠️ Inline parser | ✅ `build_parser()` | ✅ Thoát mã 2 (Chết trước khi tải dữ liệu) |
| 10 | `backup` | `scripts/backup_db.sh` | ✅ Có | ✅ Có | ❌ Nhận `$1` thành thư mục | ✅ Kiểm tra cờ `-*` | ✅ Thoát mã 2 (`Lỗi: Không chấp nhận cờ lạ`, chết trước khi `pg_dump`) |
| 11 | `orderbook-backup` | `scripts/backup_orderbook.sh` | ✅ Có | ✅ Có | ❌ Nhận `$1` thành thư mục | ✅ Kiểm tra cờ `-*` | ✅ Thoát mã 2 (`Lỗi: Không chấp nhận cờ lạ`, chết trước khi nén zip) |
| 12 | `backup-check` | `scripts/backup_check.py` | ✅ Có | ✅ Có | ⚠️ Inline parser | ✅ `build_parser()` | ✅ Thoát mã 2 (Chết trước khi quét file backup/Telegram) |
| 13 | `restore-drill` | `scripts/restore_drill.py` | ✅ Có | ✅ Có | ⚠️ Inline parser | ✅ `build_parser()` | ✅ Thoát mã 2 (Chết trước khi chạm Docker/Postgres drill) |
| 14 | `preflight` | `scripts/host_preflight.py` | ✅ Có | ✅ Có | ⚠️ Inline parser | ✅ `build_parser()` | ✅ Thoát mã 2 (Chết trước khi kiểm tra host) |
| 15 | `deploy-drift` | `scripts/deploy_drift_check.py` | ❌ Không | ✅ Có | ❌ Không có parser | ✅ `build_parser()` | ✅ Thoát mã 2 (Chết trước khi kiểm tra Docker/Git drift) |
| 16 | `container-health` | `scripts/container_health_check.py` | ❌ Không | ✅ Có | ⚠️ Inline parser | ✅ `build_parser()` | ✅ Thoát mã 2 (Chết trước khi kiểm tra Docker container) |

---

## 3. Số đo & Log dán nguyên văn

### 3.1. Cú pháp và Quyền file `scripts/sched.sh`
```powershell
PS D:\My_Vault_Obsidian\Project\AI_auto_trading_system> & "C:\Program Files\Git\bin\bash.exe" -c "bash -n scripts/sched.sh"
# (Không xuất hiện lỗi, exit code 0)

PS D:\My_Vault_Obsidian\Project\AI_auto_trading_system> git ls-files --eol -s scripts/sched.sh
100755 9e8b3513f5ca733a63960675dfd1f77bac48ab76 0	i/lf    w/lf    attr/text eol=lf      	scripts/sched.sh
```

### 3.2. Chạy Linter & Unit Tests
```powershell
PS D:\My_Vault_Obsidian\Project\AI_auto_trading_system> uv run ruff check trading tests scripts
All checks passed!

PS D:\My_Vault_Obsidian\Project\AI_auto_trading_system> uv run pytest tests/test_deployment_doc.py tests/test_sched_args.py -v
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0 -- D:\My_Vault_Obsidian\Project\AI_auto_trading_system\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\My_Vault_Obsidian\Project\AI_auto_trading_system
configfile: pyproject.toml
plugins: anyio-4.14.2, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 20 items

tests/test_deployment_doc.py::test_crontab_jobs_match_sched_sh PASSED    [  5%]
tests/test_deployment_doc.py::test_deployment_md_contains_vietnam_timezone PASSED [ 10%]
tests/test_deployment_doc.py::test_referenced_scripts_exist PASSED       [ 15%]
tests/test_sched_args.py::test_every_exec_run_branch_forwards_args PASSED [ 20%]
tests/test_sched_args.py::test_python_script_has_build_parser_and_rejects_unknown_flag[scripts.backfill_universe] PASSED [ 25%]
tests/test_sched_args.py::test_python_script_has_build_parser_and_rejects_unknown_flag[scripts.backup_check] PASSED [ 30%]
tests/test_sched_args.py::test_python_script_has_build_parser_and_rejects_unknown_flag[scripts.check_orderbook_daily] PASSED [ 35%]
tests/test_sched_args.py::test_python_script_has_build_parser_and_rejects_unknown_flag[scripts.check_silent_engine] PASSED [ 40%]
tests/test_sched_args.py::test_python_script_has_build_parser_and_rejects_unknown_flag[scripts.container_health_check] PASSED [ 45%]
tests/test_sched_args.py::test_python_script_has_build_parser_and_rejects_unknown_flag[scripts.daily_data_check] PASSED [ 50%]
tests/test_sched_args.py::test_python_script_has_build_parser_and_rejects_unknown_flag[scripts.deploy_drift_check] PASSED [ 55%]
tests/test_sched_args.py::test_python_script_has_build_parser_and_rejects_unknown_flag[scripts.disk_check] PASSED [ 60%]
tests/test_sched_args.py::test_python_script_has_build_parser_and_rejects_unknown_flag[scripts.engine_consumer_check] PASSED [ 65%]
tests/test_sched_args.py::test_python_script_has_build_parser_and_rejects_unknown_flag[scripts.heartbeat_check] PASSED [ 70%]
tests/test_sched_args.py::test_python_script_has_build_parser_and_rejects_unknown_flag[scripts.host_preflight] PASSED [ 75%]
tests/test_sched_args.py::test_python_script_has_build_parser_and_rejects_unknown_flag[scripts.record_vn30f_orderbook] PASSED [ 80%]
tests/test_sched_args.py::test_python_script_has_build_parser_and_rejects_unknown_flag[scripts.restore_drill] PASSED [ 85%]
tests/test_sched_args.py::test_python_script_has_build_parser_and_rejects_unknown_flag[scripts.stream_health_check] PASSED [ 90%]
tests/test_sched_args.py::test_daily_data_check_has_dry_run_flag PASSED  [ 95%]
tests/test_sched_args.py::test_shell_scripts_reject_unknown_flags PASSED [100%]

============================= 20 passed in 1.86s ==============================

PS D:\My_Vault_Obsidian\Project\AI_auto_trading_system> uv run pytest -q
........................................................................ [  4%]
........................................................................ [  8%]
........................................................................ [ 12%]
........................................................................ [ 17%]
........................................................................ [ 21%]
........................................................................ [ 25%]
........................................................................ [ 30%]
........................................................................ [ 34%]
........................................................................ [ 38%]
........................................................................ [ 42%]
........................................................................ [ 47%]
........................................................................ [ 51%]
........................................................................ [ 55%]
........................................................................ [ 60%]
........................................................................ [ 64%]
........................................................................ [ 68%]
........................................................................ [ 72%]
........................................................................ [ 77%]
........................................................................ [ 81%]
........................................................................ [ 85%]
........................................................................ [ 90%]
........................................................................ [ 94%]
........................................................................ [ 98%]
.....................                                                    [100%]
1677 passed in 101.69s (0:01:41)
```

### 3.3. Phá thử (Mutation Testing)
1. **Phá thử `sched.sh`:**
   - Xóa `"$@"` khỏi nhánh `heartbeat)`.
   - Kết quả: `test_every_exec_run_branch_forwards_args` đỏ lập tức:
     `AssertionError: Branch 'heartbeat' in scripts/sched.sh does not forward '$@': exec "$RUN" "$LOG" python scripts/heartbeat_check.py`
   - Hoàn trả lại code.
2. **Phá thử script parser:**
   - Thay `parser.parse_args` bằng `parser.parse_known_args` trong `heartbeat_check.py`.
   - Kết quả: `test_python_script_has_build_parser_and_rejects_unknown_flag[scripts.heartbeat_check]` đỏ lập tức:
     `Failed: DID NOT RAISE <class 'SystemExit'>`
   - Hoàn trả lại code.

### 3.4. Chạy thật an toàn
#### Lệnh 1: `scripts/sched.sh heartbeat --khong-ton-tai`
- **Mã thoát CLI:** `1` (từ wrapper `run_if_docker_up` khi command con trả về mã ≠ 0).
- **Log nguyên văn trong `logs/heartbeat.log`:**
```text
2026-10-02 09:41:14 heartbeat-check start
usage: heartbeat_check.py [-h]
heartbeat_check.py: error: unrecognized arguments: --khong-ton-tai
EXIT=2
```
*Ghi chú:* Mã thoát của script là `2`. Toàn bộ logic kiểm tra heartbeat và gửi Telegram hoàn toàn KHÔNG chạy.

#### Lệnh 2: `scripts/sched.sh daily-check --date 2026-10-01 --dry-run`
- **Mã thoát CLI:** `0`.
- **Log nguyên văn trong `logs/daily-data-check.log`:**
```text
2026-10-02 09:41:26 daily-data-check start
[2026-10-01] Đầy đủ: toàn bộ 174 mã active đều đã có bar daily.
Loại 1 mã chỉ giao dịch thứ Sáu (POM)
EXIT=0
```
*Ghi chú:* Nhánh `daily-check` đã nhận cả hai cờ `--date 2026-10-01` và `--dry-run`. Script truy vấn đúng dữ liệu ngày 01/10 (174 mã active đủ bar, 1 mã POM nghỉ thứ Năm), không gửi bất kỳ thông báo Telegram nào.

#### Lệnh 3: `scripts/sched.sh daily-check --date 2026-10-01 --khong-ton-tai`
- **Mã thoát CLI:** `1`.
- **Log nguyên văn trong `logs/daily-data-check.log`:**
```text
2026-10-02 09:42:11 daily-data-check start
usage: daily_data_check.py [-h] [--dsn DSN] [--date DATE] [--dry-run]
daily_data_check.py: error: unrecognized arguments: --khong-ton-tai
EXIT=2
```
*Ghi chú:* Mã thoát của script là `2`. Script chết ngay ở khâu phân tích tham số trước khi kết nối DB.

---

## 4. Brief sai hoặc underspecified ở đâu?

1. **Về các nhánh chuyển `"$@"` trong `sched.sh`:**
   - Brief ghi nhận 7 nhánh bỏ tham số và 9 nhánh chuyển `"$@"`.
   - Tuy nhiên, trong 9 nhánh có vẻ "đúng", 2 nhánh gọi shell script là `backup` (`backup_db.sh`) và `orderbook-backup` (`backup_orderbook.sh`) thực chất **không có parser**: chúng gán trực tiếp tham số đầu tiên `BACKUP_DIR="${1:-...}"`. Nếu người dùng gõ `scripts/sched.sh backup --dry-run`, script sẽ tạo một thư mục tên là `--dry-run` và dump DB vào đó mà không báo lỗi!
   - *Khắc phục:* Đã bổ sung cơ chế kiểm tra `[[ "$1" == -* ]]` và giới hạn tối đa 1 tham số cho cả hai file shell script, trả về mã thoát 2 nếu gặp cờ lạ.

2. **Về tên file log của `daily-check`:**
   - Trong phân tích sự cố của Brief ghi tắt là `daily_check.log`. Tên file log thực tế được cấu hình trong `sched.sh` là `logs/daily-data-check.log`.

3. **Vấn đề tương tác giữa `argparse` và `pytest`:**
   - Khi thêm `parser.parse_args(argv)` vào các script trước đây không có tham số (`heartbeat_check.py`, `deploy_drift_check.py`), nếu viết hàm `main(argv=None)` mà gọi `parser.parse_args(argv)` trực tiếp khi `argv is None`, thì mặc định `argparse` sẽ đọc `sys.argv[1:]`.
   - Khi chạy qua `pytest` (như trong các test unit cũ `test_storage.py` hay `test_deploy_drift.py`), `sys.argv` chứa các cờ của pytest (ví dụ `-q`, `-v`, filter tests). Điều này khiến parser tưởng pytest flags là cờ của script và văng lỗi `unrecognized arguments: -q`.
   - *Khắc phục chuẩn hóa:*
     ```python
     def main(argv: list[str] | None = None) -> int:
         if argv is not None:
             build_parser().parse_args(argv)
         ...
     if __name__ == "__main__":
         sys.exit(main(sys.argv[1:]))
     ```
     Nhờ vậy: khi gọi từ CLI / `sched.sh`, `sys.argv[1:]` được truyền vào và parser lập tức kiểm tra nghiêm ngặt cờ lạ; khi test unit nội bộ gọi `main()` không truyền tham số, parser không bị rò rỉ flags của pytest.

---

## 5. Những gì không kiểm tra được

1. **Chế độ gửi Telegram thật:**
   - Tuân thủ nghiêm ngặt ranh giới: **KHÔNG gửi tin nhắn Telegram thật đến kênh sản xuất** để tránh gây spam/báo oan cho chủ dự án (đúng với tinh thần cốt lõi của Brief 140).
   - Hành vi gửi Telegram đã được kiểm chứng an toàn qua mock trong bộ test (`test_daily_data_check.py`, `test_engine_consumer_check.py`, v.v.) và cờ `--dry-run` được kiểm chứng bằng logic bypass gửi Telegram.

2. **Chạy qua Cron daemon thật trên Linux:**
   - Môi trường hiện tại là Windows host phát triển; việc chạy `sched.sh` được kiểm tra qua Git Bash và Docker container mô phỏng tương đương chính xác môi trường cron Debian.

---

## Audit của Claude (02/10/2026, 10:30)

### A.1. Kết luận: NHẬN. Hành vi thật đúng; bộ test có một lỗ, giao đợt 141.

### A.2. Code mới đã chạy thật trong phiên hôm nay

Lịch chạy thẳng từ cây làm việc, nên các thay đổi chưa commit đã có hiệu lực từ sáng. Claude đọc log các job chạy theo lịch:

- `heartbeat` 10:00, 10:05, 10:10: `EXIT=0`.
- `engine-consumer` 10:05, 10:10: `OK ... delivered_seq=28746, stream_last_seq=28746`.
- `deploy-drift` 08:00: `OK`.

Không có lỗi phân tích tham số nào ngoài các lần thử cờ lạ có chủ ý.

Ba nhánh trước đây nuốt tham số, chạy qua `sched.sh` với cờ lạ:

```
deploy-drift      ma thoat=2  | deploy_drift_check.py: error: unrecognized arguments: --khong-ton-tai EXIT=2
engine-cam        ma thoat=2  | check_silent_engine.py: error: unrecognized arguments: --khong-ton-tai EXIT=2
container-health  ma thoat=2  | container_health_check.py: error: unrecognized arguments: --khong-ton-tai EXIT=2
```

### A.3. Lỗ trong bộ test — phá thử của Claude

| Phá thử | Kết quả |
|---|---|
| `heartbeat_check.py`: `raise SystemExit(main())` (không truyền argv → parser không bao giờ chạy) | **17/17 vẫn XANH** |
| `deploy_drift_check.py`: bỏ hai dòng `if argv is not None: build_parser().parse_args(argv)` | **17/17 vẫn XANH** |
| `sched.sh`: gỡ `"$@"` khỏi nhánh `container-health` (nhánh dùng `python -m`) | `test_every_exec_run_branch_forwards_args` đỏ |

Test gọi `build_parser().parse_args(["--khong-ton-tai"])`. Nó chứng minh **parser** từ chối cờ lạ, nhưng không chứng minh **`main` có dùng parser**. Với hai script vừa được thêm parser (`heartbeat_check.py`, `deploy_drift_check.py`), `main` chỉ parse khi `argv is not None`. Chỉ cần sửa một dòng ở khối `__main__` là cờ lại bị nuốt im lặng, mà bộ test vẫn xanh. Đây đúng là lỗi đợt này sinh ra để diệt.

Hash khôi phục trùng ở cả ba phá thử. `ruff` sạch; **1.677 passed**.

### A.4. Phát hiện ngoài phạm vi, không do đợt này: hai task giám sát chết cả ngày 02/10

`trading-container-health` (mỗi 10 phút) và `trading-disk-check` (mỗi 6 giờ) **không tự chạy lần nào trong ngày 02/10**. Claude chạy tay cả hai lúc 05:49. Sau đó mọi lần Task Scheduler gọi `container-health` (05:37, 10:07, 10:17:47) đều bị từ chối với `0x800710E0` trước khi wrapper kịp ghi log. Lần lịch 10:20 không chạy.

Hai task này là **hai task duy nhất** dùng trigger hằng ngày neo lúc **00:00** có lặp lại, với `StartWhenAvailable=False`. Cả hai có `NumberOfMissedRuns=1`. Đêm 01/10 → 02/10 máy ngủ từ 17:56 đến 05:21, trượt đúng mốc 00:00, nên chuỗi lặp của ngày 02/10 không khởi động.

Mọi task khác hoặc neo vào giờ máy đang thức (08:00, 08:40, 09:00…), hoặc có `StartWhenAvailable=True` (`backup`, `backup-check`, `orderbook-backup`), và vẫn chạy bình thường. Cấu hình task là việc của chủ dự án; Claude báo, không tự sửa.

