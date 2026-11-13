# Brief đợt 225: schedule-watch phải thấy cả những lần thất bại đã tự hồi phục giữa hai lần kiểm

Ngày 13/11/2026. Người giao: Claude (Lead). Người làm: **Builder**.

## Bối cảnh (đo 13/11, báo cáo `docs/audit/2026-11-13-do-phien-sau-dot-220-221.md`, mục M3/A6)

- `schedule-watch` (`scripts/heartbeat_check.py --schedule-watch-only`) chạy mỗi giờ lúc :07. Nhánh heartbeat thường cũng gọi cùng hàm `evaluate_schedule_health`.
- Cả hai đường gọi đều lấy mã thoát qua `get_last_run_exit_code` (`heartbeat_check.py:475`). Hàm này **chỉ trả lần chạy CUỐI** của mỗi job.
- Hệ quả đo được 13/11: `container-health` thoát `EXIT=4` lúc 13:46:39 rồi về `EXIT=0` lúc 13:50:57. Mốc kiểm 14:07 chỉ thấy lần cuối (`EXIT=0`), nên **0 tin THẤT BẠI**. Mọi job chạy dày hơn 1 giờ (container-health 10 phút, heartbeat, engine-cam, ...) đều có lỗ này. Một sự cố kéo dài dưới ~1 giờ sẽ không bao giờ được báo.

## Hành vi mong muốn

Gọi "lần chạy mới" là lần chạy đã có `EXIT=` và có mốc `start` **sau** mốc đã xem ở lần kiểm trước.

1. **Lưu con trỏ** trong file trạng thái, theo từng nhánh: mốc `start` của lần chạy mới nhất đã đánh giá. Tên trường do bạn chọn, ví dụ `exit_seen_until`, định dạng `"%Y-%m-%d %H:%M:%S"` như các trường khác.
2. **Lần đầu, khi state chưa có con trỏ:** giữ đúng hành vi cũ (chỉ xét lần cuối), rồi đặt con trỏ. **Không** báo lại lịch sử cũ trong log. Đây là điều kiện bắt buộc vì log hiện có hàng trăm lần chạy, gồm cả 30 lần `EXIT=2` ngày 09/11.
3. **Có lần chạy mới bị thất bại** (mã không thuộc `normal_exit_codes`), **nhưng lần cuối không thất bại** (ok, hoặc đang chạy):
   - báo **một** tin cho nhánh đó trong lần kiểm này, mức `[WARN]`;
   - tin nêu tên nhánh, số lần thất bại, các mã thoát, mốc start lần thất bại đầu và cuối, kèm chữ "đã tự hồi phục";
   - ví dụ: `[WARN] job theo lịch 'container-health' THẤT BẠI rồi tự hồi phục: 1 lần (mã 4) lúc 2026-11-13 13:46:39`.
4. **Lần cuối thất bại:** giữ nguyên logic cũ (CRITICAL một lần, im nếu đã báo cùng mã). **Không** thêm tin `[WARN]` riêng cho các lần thất bại trước đó trong cùng cửa sổ. Một nhánh, một lần kiểm: tối đa một tin về mã thoát.
5. **Tin HỒI PHỤC** (`prev_exit_status == "failed"` và lần cuối ok): giữ nguyên.
6. **Chỉ lưu con trỏ khi state được lưu.** Hiện state chỉ được lưu sau khi gửi Telegram thành công, hoặc khi không có cảnh báo. Không đổi điều đó. Gửi hỏng nghĩa là con trỏ không tiến, và lần sau báo lại. Như vậy là đúng.
7. Cả hai đường gọi (nhánh `--schedule-watch-only` và nhánh heartbeat thường) dùng chung hàm và chung file state, nên phải cùng hành vi.

Không đổi: phần canh tuổi (mục 1 của `evaluate_schedule_health`), phần diễn tập phục hồi, `normal_exit_codes`.

### Thêm: sửa chuỗi `reason` (chỉ chuỗi)

`SCHEDULE_EXIT_POLICIES["container-health"].reason` (khoảng dòng 262) mới mô tả mã 4 là "Docker daemon không phản hồi". Từ đợt 223 (`a561847`), mã 4 còn gồm **lỗi đọc container kéo dài**. Thêm ý đó vào chuỗi. Không đổi `normal_exit_codes`.

## Trước khi sửa

- Chạy `node .gitnexus/run.cjs impact get_last_run_exit_code --direction upstream --repo .` và `... impact evaluate_schedule_health ...`. `scripts/` không được GitNexus index, nên kết quả sẽ ra UNKNOWN. Khi đó grep caller trong `scripts/` và `tests/`, rồi báo danh sách. **Không dùng npx.**
- Đọc `tests/test_schedule_watch.py` (33 test). Mọi test cũ phải còn pass **mà không sửa**. Nếu thấy buộc phải sửa test cũ, dừng lại và báo Lead kèm lý do.

## Cách làm việc: BẮT BUỘC dùng worktree riêng

`heartbeat_check.py` chạy thật từ thư mục chính, mỗi 10 phút (heartbeat) và mỗi giờ (schedule-watch).

- `git worktree add ../AI_auto_trading_system-dot225 -b dot225 HEAD`. Làm mọi việc trong đó.
- **Không sửa file nào** trong `D:\My_Vault_Obsidian\Project\AI_auto_trading_system`.
- Lead sẽ audit, rồi merge vào main **ngoài giờ phiên** (sau 15:00 hoặc tối).

## Phạm vi

- **Được sửa** (trong worktree): `scripts/heartbeat_check.py` (chỉ phần đọc mã thoát, `evaluate_schedule_health` mục 2, chuỗi reason nói trên, và chỗ truyền dữ liệu ở 2 đường gọi trong `main`), `tests/test_schedule_watch.py` (chỉ thêm test).
- **Không đụng:** `scripts/container_health_check.py`, `scripts/sched.sh`, `scripts/run_if_docker_up.sh`, Task Windows, `docker-compose.yml`, `trading/`, các nhánh khác của `main()` trong heartbeat (DB, nến, token, ...).
- Giữ style hiện có, không refactor. Thấy vấn đề khác thì báo lại, không tự sửa.

## Test bắt buộc (dùng log giả trong `tmp_path` và state giả, không đọc `logs/` thật)

1. Con trỏ ở 13:07. Log có `EXIT=4` lúc 13:46 rồi `EXIT=0` lúc 13:50 (container-health). Kỳ vọng: **1 `[WARN]`** nêu mã 4 và 13:46:39, đồng thời con trỏ tiến tới 13:50.
2. Như (1), nhưng chạy kiểm lần hai với state mới và không có lần chạy mới. Kỳ vọng: **0 tin**.
3. State **không có** con trỏ, log có 30 lần `EXIT=2` (backfill, mã 2 là thất bại) rồi `EXIT=0`. Kỳ vọng: **0 tin**, và con trỏ được đặt.
4. Lần chạy mới có `EXIT=4`, `EXIT=4`, rồi lần cuối `EXIT=4`. Kỳ vọng: **đúng 1 CRITICAL** như logic cũ, không kèm `[WARN]`.
5. Hai nhánh cùng có thất bại tự hồi phục. Kỳ vọng: 2 dòng `[WARN]`, và `main(--schedule-watch-only)` gửi **đúng 1 tin Telegram** (mock `send_with_outbox` hoặc `send_telegram`, `logs_dir` trỏ vào `tmp_path`).
6. Gửi Telegram hỏng trong ca (1). Kỳ vọng: state **không** được lưu, và lần kiểm sau vẫn báo.
7. Lần chạy mới thất bại bằng mã thuộc `normal_exit_codes` (container-health `EXIT=1`). Kỳ vọng: 0 tin.
8. Có dòng `SKIP` xen giữa các lần chạy mới. Kỳ vọng: không làm lệch việc ghép `EXIT=` với `start`, và không có `ALERT_EXIT=` nào bị đọc thành `EXIT=` (quy tắc 1–2 trong docstring `get_last_run_exit_code`).

Các test (1), (5), (6) phải **thất bại trên code hiện tại**. Gửi output thật khi chạy trên code cũ (chép nguyên văn, không tóm tắt; đợt 224 đã có một lần báo sai "pass trên code cũ").

## Cấm

- Chạy `sched.sh`, chạy `heartbeat_check.py` thật lên `logs/`, gửi Telegram.
- Ghi vào `logs/` thật.
- Restart hoặc rebuild container.
- Commit lên `main`, push, dùng `npx`. Commit trong nhánh `dot225` thì được.

## Tiêu chí hoàn thành (bằng chứng phải gửi)

1. Output impact, và grep caller nếu kết quả ra UNKNOWN.
2. Tên các test mới, kèm output chạy **trên code cũ** (các test 1, 5, 6 thất bại) và **trên code mới** (tất cả pass).
3. `uv run pytest tests/test_schedule_watch.py tests/test_container_health_check.py tests/test_heartbeat_check.py -q` pass. Nếu không có `test_heartbeat_check.py` thì nêu file test heartbeat tương ứng.
4. `uv run pytest -m "not integration" -q`: tổng số pass/fail, chạy trong worktree.
5. `uv run ruff check scripts tests` sạch.
6. `git -C <worktree> log --oneline main..dot225` và `git -C <worktree> diff --stat main..dot225`.
7. Một đoạn ngắn: kích thước lớn nhất của các log đang bị đọc (`ls -l logs/*.log`, chỉ đọc). Ghi rõ việc đọc cả file mỗi lần kiểm có chậm không. Không cần tối ưu nếu dưới vài MB.
