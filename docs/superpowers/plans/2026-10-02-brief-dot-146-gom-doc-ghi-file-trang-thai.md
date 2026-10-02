# Brief đợt 146 — gom phần đọc/ghi file trạng thái về một chỗ (dọn kỹ thuật nhỏ)

Chủ dự án chọn hướng "dọn kỹ thuật nhỏ". Việc nhỏ, rủi ro chính là **đụng vào chuông đang chạy**; đọc
kỹ mục Giới hạn.

## Hiện trạng (Claude đã đọc code, 02/10/2026)

| Script | Đọc / ghi | Vấn đề |
|---|---|---|
| `scripts/container_health_check.py` `load_state` / `save_state` (≈ dòng 434–461) | đọc chịu lỗi, kiểm `dict`; ghi qua `.tmp` + `os.replace` | — |
| `scripts/heartbeat_check.py` `load_schedule_state` / `save_schedule_state` (≈ dòng 261–290) | **gần như giống hệt** bản trên, chỉ khác tiền tố log `[container-health]` / `[heartbeat]` | lặp code |
| `scripts/engine_consumer_check.py` `load_state` / `save_state` (≈ dòng 64–80) | đọc chịu lỗi nhưng **không kiểm `dict`**; ghi thẳng bằng `write_text`, **không qua file tạm**; đường dẫn `STATE_FILE` **ghim cứng** | file chứa JSON không phải `dict` (vd `[]`) sẽ làm `prev_state.get(...)` ném lỗi giữa phiên; tiến trình chết giữa lúc ghi để lại file dở; test không tiêm được đường dẫn |
| `scripts/docker_down_alert.py` `_read_last_alert` / `_write_last_alert` | file chỉ chứa một số epoch, không phải JSON; đường dẫn đã là tham số | **không đụng** (xem dưới) |

`docker_down_alert` để nguyên có chủ ý. Đổi sang JSON thì file đang có trên đĩa sẽ bị đọc là "hỏng",
và lần Docker tắt kế tiếp có thể kêu lặp một lần. Được ít, mất nhiều.

## Giới hạn — đọc kỹ

- **Lịch chạy THẲNG từ cây làm việc.** `container-health` chạy **mỗi 10 phút, 24/7, kể cả cuối tuần**.
  Lưu một lỗi cú pháp vào `scripts/container_health_check.py` trong repo chính là chuông chết ở lần
  chạy kế tiếp. Vì vậy:
  - **Viết và test trong một git worktree riêng** (`git worktree add --detach <nháp> HEAD`), như đợt 142.
  - Chép vào repo chính **chỉ sau khi** `uv run pytest -q` đầy đủ đã xanh trong worktree. Chép cả ba
    script **cùng lúc**, rồi **ngay lập tức** chạy các lệnh ở tiêu chí 5. Không có phút chờ nào giữa
    lúc chép và lúc kiểm.
  - Heartbeat và engine-consumer chỉ chạy trong phiên ngày giao dịch. Nếu chép vào ngày giao dịch thì
    chép ngoài khung 08:00–15:10.
  - Xong thì `git worktree remove --force` và dán `git worktree list`.
- **KHÔNG commit, KHÔNG push**, không restart/build container, không sửa task, không sửa `.env`, không
  gửi Telegram thật.
- Chỉ sửa: `scripts/_alert_common.py` (thêm hai hàm), ba script trên (chỉ phần đọc/ghi trạng thái, và
  thêm `--state-file` cho `engine_consumer_check`), test tương ứng. **Không** đổi logic phán xử hay
  chuyển trạng thái của script nào. **Không** đụng `docker_down_alert.py`, `trading/`, `DEPLOYMENT.md`.
- Phát hiện "pytest khác đang chạy" phải lọc đúng tiến trình Python, không để lệnh tự đếm chính nó:
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }`
  phải rỗng trước khi chạy bộ đầy đủ. (Lệnh trong brief 142–145 thiếu `-Filter` nên đếm nhầm chính
  tiến trình shell; lỗi của Claude.)
- GitNexus: `impact` trên từng hàm sắp đổi (`load_state`, `save_state` của cả hai script,
  `load_schedule_state`, `save_schedule_state`) **trước khi sửa**, dán kết quả. `detect_changes` sau khi
  sửa; nếu báo 0 thay đổi trong khi có file đổi thì chạy `npx gitnexus analyze` rồi đo lại.

## Việc

1. Thêm vào `scripts/_alert_common.py` hai hàm dùng chung:
   - `load_json_state(path, label) -> dict`: không có file → `{}`; JSON hỏng hoặc không phải `dict` →
     `{}` và in **đúng** câu cảnh báo hiện có (cùng tiền tố `[label]`, cùng nội dung) qua `_print_safe`.
     Không bao giờ ném.
   - `save_json_state(path, state) -> None`: tạo thư mục cha, ghi `.tmp`, `os.replace`. **Giữ đúng
     hành vi ném/không ném của từng nơi gọi hiện nay.** `container_health_check` và `heartbeat_check`
     hiện để lỗi ghi ném lên; `engine_consumer_check` hiện bắt lỗi ghi. Đọc kỹ từng nơi, giữ nguyên,
     và ghi vào báo cáo nơi nào bắt, nơi nào không.
2. `container_health_check.py` và `heartbeat_check.py`: thay thân bốn hàm cũ bằng lời gọi hàm chung.
   Giữ **tên** các hàm cũ (test và code khác đang import chúng); chúng thành lớp mỏng gọi hàm chung.
3. `engine_consumer_check.py`: dùng hai hàm chung, nên được kiểm `dict` và ghi nguyên tử. Thêm cờ
   `--state-file` (mặc định = `STATE_FILE` hiện tại, cron không đổi), truyền đường dẫn xuống chỗ đọc/ghi.
   Câu đầu của `main` vẫn phải là `args = build_parser().parse_args(argv)` (đợt 141 ghim bằng AST).

## Tiêu chí hoàn thành

1. **Không đổi nghĩa ngoài ý muốn:** so AST theo hàm giữa `HEAD` và bản mới của ba script (đợt 141 đã
   làm cách này). Chỉ các hàm đọc/ghi trạng thái, `build_parser` và `main` của `engine_consumer_check`
   được khác. Dán bảng.
2. Test cho hai hàm chung: thiếu file; JSON hỏng; JSON là `[]`; ghi rồi đọc lại khớp; ghi khi thư mục
   cha chưa có; ghi bị ngắt giữa chừng không để lại file đích dở (vd giả `os.replace` ném → file đích
   cũ còn nguyên).
3. Test `engine_consumer_check` với file trạng thái là `[]` → không ném, coi như lần đầu. **Trước khi
   sửa, test này phải đỏ trên code cũ** (dán dòng đỏ). Đó là bằng chứng lỗi có thật.
4. **Phá thử, ghi nguyên văn dòng đỏ, khôi phục và đối chiếu hash:**
   - `save_json_state` ghi thẳng file đích (bỏ `.tmp`) → test ghi nguyên tử đỏ;
   - `load_json_state` bỏ kiểm `dict` → test `[]` đỏ;
   - đổi câu cảnh báo của `load_json_state` → test giữ đúng câu cảnh báo cũ đỏ.
5. **Ngay sau khi chép vào repo chính**, chạy:
   - `scripts/sched.sh container-health --dry-run` → `EXIT=0`, không traceback;
   - `scripts/sched.sh heartbeat --dry-run` → không traceback, không có "ĐÃ CHẠY LẠI" oan;
   - `scripts/sched.sh engine-consumer --khong-ton-tai` → chết mã 2 ở argparse.

   Rồi chờ **một lần chạy theo lịch thật** của `container-health` sau giờ chép (≤ 10 phút) và dán dòng
   `start` + `EXIT=` của nó trong `logs/container-health.log`.
6. `ruff` sạch; `uv run pytest -q` ≥ **1.737 passed** cộng số test mới; lưới an toàn của đợt 145 không đỏ.

## Báo cáo

`docs/superpowers/research/2026-10-02-dot-146-gom-doc-ghi-trang-thai.md`: giờ chép vào repo chính,
bảng AST, nơi nào bắt/không bắt lỗi ghi, số đo nguyên văn, brief sai ở đâu, cái gì không kiểm được.
