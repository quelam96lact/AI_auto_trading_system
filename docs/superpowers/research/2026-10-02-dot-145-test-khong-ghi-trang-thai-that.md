# Đợt 145 — test không bao giờ được ghi vào file trạng thái THẬT (báo cáo)

Ngày 02/10/2026 (thứ Sáu). Chưa commit, chưa push. Không restart container, không sửa task, không gửi Telegram thật.

**Giờ chép vào repo chính:** làm thẳng trong repo chính, từ khoảng 16:10 đến 16:35 thứ Sáu, tức **ngoài khung heartbeat** (08:00–15:00 ngày giao dịch) và cuối tuần heartbeat không chạy. Không dùng worktree.

## 1. Tái hiện trước khi sửa (nguyên văn)

Lúc 16:13:11, `logs/.schedule_health_state.json` không tồn tại. Chạy `tests/test_heartbeat_check.py`:

```
38 passed in 1.46s
sau: ton tai=True
```

Nội dung file xuất hiện (cả 5 job, đúng như brief):

```
"container-health": {"status": "stale", "last_called": null, "checked_at": "2026-08-14 10:00:00"}
(disk-check, backup, orderbook-backup, backup-check: giống hệt)
```

Hai file test còn lại (đã xoá file bẩn trước đó):

```
test_schedule_watch        -> 11 passed, ton tai=False
test_container_health_check-> 21 passed, ton tai=False
```

Khớp brief: chỉ `test_heartbeat_check.py` ghi.

## 2. Đã sửa gì

| File | Thay đổi |
|---|---|
| `scripts/heartbeat_check.py` | Thêm hằng `DEFAULT_LOGS_DIR`, `SCHEDULE_STATE_NAME` (`DEFAULT_SCHEDULE_STATE_FILE` giữ nguyên giá trị). Thêm cờ `--logs-dir` và `--state-file`. `main` dùng `args.logs_dir` và `args.state_file or <logs-dir>/.schedule_health_state.json`. Không đổi logic phán xử. |
| `tests/test_heartbeat_check.py` | Mọi lần gọi `main` truyền `--logs-dir <tmp_path>`. Thêm `_fresh_job_logs`, thêm `strptime` vào 3 lớp `FakeDatetime`, thêm 2 test mới. |
| `tests/conftest.py` | Lưới an toàn `autouse` cấp phiên (mục 4). |
| `tests/test_schedule_watch.py` | **Không cần sửa**: file này chỉ gọi hàm thuần, không gọi `main`, không ghi. |

**Vì sao cờ dòng lệnh mà không phải tham số của `main`:** `build_parser().parse_args(argv)` là cổng vào duy nhất đã được `test_sched_args` ghim bằng AST (đợt 141). Test gọi `main([...])` đúng như cron gọi. Mặc định giữ nguyên, cron không truyền gì. Nếu chỉ truyền `--logs-dir` thì file trạng thái tự nằm trong thư mục đó, nên không thể quên một nửa.

`impact` trên `main` (heartbeat_check): LOW, 1 gọi trực tiếp, 0 luồng. `build_parser`: GitNexus không tìm thấy symbol (trùng tên với 14 script khác). `detect_changes`: `risk_level: low` nhưng `changed_count: 0` dù có 5 file đổi, nên **chỉ số này không dùng được để kết luận** (có vẻ chỉ mục chưa cập nhật). Xem mục "Không kiểm được".

## 3. Phát hiện thêm: lỗi che lỗi

Khi truyền thư mục tạm rỗng, test `test_main_silent_when_ledger_matches_with_open_position` **đỏ**: nhánh canh lịch báo "file log không tồn tại" cho cả 5 job. Nguyên nhân: các test "im lặng" **chỉ xanh nhờ file trạng thái bẩn** do test `no_crash` ghi trước đó trong cùng file (trạng thái trước = `stale` ⇒ "đã báo rồi" ⇒ im). Nghĩa là test cũ phụ thuộc thứ tự chạy và phụ thuộc vào chính lỗi này. Sửa bằng cách dựng log giả "vừa chạy 30 giây trước" cho từng job trong thư mục tạm (`_fresh_job_logs`), và thêm `strptime = staticmethod(datetime.strptime)` vào `FakeDatetime` để `get_last_called_timestamp` đọc được log (trước đây nó bị nuốt thành "không đọc được file log").

## 4. Lưới an toàn cho cả bộ test

**Cách chọn: audit hook (`sys.addaudithook`), không so sánh trước/sau trên đĩa.** Brief gợi ý so tồn tại/mtime/băm trước và sau phiên. Tôi không làm vậy làm cơ chế chính vì cron ghi `.container_health_state.json` thật mỗi 10 phút ngay trong lúc test chạy (tiến trình khác), so sánh đĩa sẽ đỏ oan. Audit hook chỉ thấy việc **của chính tiến trình pytest**: mở-để-ghi, xoá, đổi tên một file `logs/.*state*` hoặc `logs/.*last*`, và ghi tên test đang chạy (`PYTEST_CURRENT_TEST`). Cuối phiên, fixture `autouse` cấp phiên `pytest.fail` (lỗi ERROR lúc dọn, mã thoát khác 0), nêu tên file, sự kiện và tên test.

File kiểu này trong `logs/` (tự tìm, bằng `ls` và grep `scripts/ trading/`):

| File | Ai ghi |
|---|---|
| `.schedule_health_state.json` | `heartbeat_check.py` |
| `.container_health_state.json` | `container_health_check.py` |
| `.docker_down_last_alert` | `docker_down_alert.py` |
| `.engine_consumer_last_check` | `engine_consumer_check.py` |

Không tìm thấy file trạng thái nào của "bản ghi sổ lệnh". Lưới bắt cả bốn nhờ quy tắc tên.

**Giới hạn:** tiến trình con (subprocess do test sinh ra) không bị audit hook bắt. Hiện test nào chạy `sched.sh` trong subprocess đều chết ở argparse.

### Phá thử (băm file test trước = sau = `14cc42ba461a2ddb`)

A. Một test tạm ghi `logs/.schedule_health_state.json` thật:

```
.E
ERROR at teardown of test_ghi_that
Test da GHI/XOA/DOI TEN file trang thai THAT trong logs/ (cron doc file nay): .schedule_health_state.json [open] boi tests/test_tmp_sabotage145.py::test_ghi_that (call) - truyen thu muc tam (tmp_path) cho script, xem brief dot 145.
1 passed, 1 error in 0.32s
```

B. Trả một lời gọi về `hc.main([])`: `1 failed, 39 passed, 1 error`; lỗi ERROR nêu `test_main_ghi_trang_thai_vao_thu_muc_tam...`, file thật xuất hiện (`ton tai=True`), đã xoá. File test khôi phục, băm khớp, file tạm đã xoá.

## 5. Không đỏ oan khi cron đang chạy

Hai lần `uv run pytest -q` đầy đủ liên tiếp trong repo chính:

```
RUN1 16:28:02 -> 16:29:34   1737 passed in 89.00s (0:01:28)
RUN2 16:29:34 -> 16:31:17   1737 passed in 98.97s (0:01:38)
```

Dòng log container-health rơi vào giữa (`logs/container-health.log`):

```
2026-10-02 16:30:06 container-health start
```

và `logs/.container_health_state.json` được cron ghi lúc `16:30:21` — tức **trong** RUN2. Cả hai xanh, lưới không đỏ.

Số đếm "pytest khác đang chạy" ngay trước mỗi lần chạy là **1**, không phải 0. Tôi không xác định được tiến trình nào (không phải lệnh kiểm của tôi, đã loại). Có khả năng là agent đợt 144 chạy song song. Cả hai lần đều xanh với 1737 passed nên không thấy lỗi giả, nhưng ghi lại là chưa đạt đúng điều kiện "rỗng" của brief.

## 6. `sched.sh heartbeat --dry-run` (16:22:40)

Trước và sau: `logs/.schedule_health_state.json` không tồn tại. Đoạn log của lần chạy này (từ dòng `start`):

```
2026-10-02 16:22:40 heartbeat-check start
EXIT=0
```

Không có dòng "ĐÃ CHẠY LẠI" nào, không gửi Telegram. (Các dòng "ĐÃ CHẠY LẠI" phía trên đó trong `heartbeat.log` là của lần dry-run cũ chạy trên trạng thái bẩn.)

## 7. Kết quả cuối

- `logs/.schedule_health_state.json`: **không tồn tại** sau mọi lần chạy.
- `ruff check trading tests scripts`: `All checks passed!`
- `uv run pytest -q`: **1737 passed** (mốc brief ≥ 1729 + 2 test của tôi = 1731; chênh +6 do đợt 144 đang thêm test song song, tôi không đo từng đợt).

## Brief sai / lệch ở đâu

1. Brief nói "chỉ sửa chỗ chọn đường dẫn state/log" trong `heartbeat_check.py`. Đúng, nhưng phải thêm `FakeDatetime.strptime` và log giả vào test, vì các test cũ im lặng nhờ file bẩn (mục 3). Brief không nhắc.
2. `tests/test_schedule_watch.py` không cần sửa gì.
3. Brief đề xuất so sánh trước/sau trên đĩa; tôi chọn audit hook (lý do mục 4).
4. Điều kiện "không có pytest nào khác" không đạt đúng 0 (mục 5).
5. `tests/test_alert_outbox.py` và `trading/alerts.py` hiện cũng báo đã sửa trong `git status`: **không phải của tôi**, của đợt 144 chạy song song.
6. Lần chạy container-health lúc 16:20:18 ghi "Docker daemon không chạy hoặc không phản hồi trong 10s, EXIT=2" trong khi `docker ps` 2 phút sau vẫn thấy mọi container `Up 11 hours`. Không thuộc phạm vi đợt này, ghi lại để Claude xem.

## Không kiểm được

- Heartbeat thật lần đầu lúc 08:00 thứ Hai 05/10 với code mới.
- `detect_changes` của GitNexus (trả 0 symbol; chỉ mục chưa phản ánh).
- Test nào chạy subprocess ghi vào `logs/` (audit hook không thấy).
- Danh tính tiến trình pytest thứ nhất ở mục 5.

---

## Audit của Claude (02/10/2026, 16:45)

### A.1. Kết luận: ĐẠT, xong trước hạn 08:00 thứ Hai.

### A.2. Kiểm độc lập

- **Không còn làm bẩn file thật:** chạy `tests/test_heartbeat_check.py` trong repo chính → `40 passed`; `logs/.schedule_health_state.json` không tồn tại trước lẫn sau.
- **Phá thử của Claude** (kiểu lỗi khác phá thử của agent): cho `main` bỏ qua `--logs-dir` khi chọn file trạng thái (`args.state_file or os.path.join(logs_dir, ...)` → `DEFAULT_SCHEDULE_STATE_FILE`). Kết quả: `test_main_ghi_trang_thai_vao_thu_muc_tam_khong_phai_logs_that` **FAILED**, và lưới an toàn trong `conftest.py` báo **ERROR lúc dọn**, nêu từng test đã ghi `.schedule_health_state.json` thật (`test_main_alerts_when_ledger_mismatch`, `test_main_no_crash_when_no_bar_any_day`, …). Hash khôi phục trùng `fc6429f6978c1a56`. Phá thử này có ghi file thật một lần; Claude đã xoá.
- **Chạy thật `sched.sh heartbeat --dry-run` lúc 16:43:11:** `EXIT=0`, **không còn dòng "ĐÃ CHẠY LẠI" oan nào** (các dòng đó trong log là của lần 15:13:36, trước khi sửa). File thật vẫn không tồn tại sau đó.

### A.3. Phát hiện thêm của agent — đáng ghi lại

Một số test "im lặng" cũ **chỉ xanh nhờ chính file trạng thái bẩn**: trạng thái `stale` do test khác ghi trước làm nhánh canh lịch tưởng "đã báo rồi". Lỗi ghi file thật vì thế còn che giấu test sai. Agent dựng log giả "vừa chạy 30 giây trước" cho từng job.

### A.4. Đánh giá thiết kế lưới an toàn

Agent chọn `sys.addaudithook` thay vì so file trên đĩa trước/sau phiên như brief gợi ý. Đúng: cron ghi `.container_health_state.json` thật mỗi 10 phút từ một tiến trình khác, nên so trên đĩa sẽ đỏ oan; audit hook chỉ thấy việc của chính tiến trình pytest. Giới hạn đã nêu và chấp nhận: tiến trình con không bị bắt.

