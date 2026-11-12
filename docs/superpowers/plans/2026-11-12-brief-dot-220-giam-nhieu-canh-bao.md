# Brief đợt 220: bớt nhiễu cảnh báo token SSI, ghi log khi gửi lại outbox (A4, A3 của đợt 219)

Ngày 12/11/2026. Người giao: Claude (Lead). Người làm: **Builder**.

- **Nguồn:** `docs/audit/2026-11-09-do-trong-phien.md`, mục A3, A4 và M15.
- **Không làm trong đợt này:** F2, phần ping ra dịch vụ ngoài của F8, F10; mọi thay đổi về Docker, Task Windows hay `docker-compose.yml`.

## Quy tắc chung

- **Worktree riêng:**
  - Tạo bằng `git worktree add ../AI_auto_trading_system-wt220 -b dot220 main`.
  - Làm và chạy test trong đó; không sửa thư mục repo chính.
  - Có thể commit lên nhánh `dot220`; Lead tự merge.
- **Impact trước khi sửa mỗi symbol:** chạy `node .gitnexus/run.cjs impact "<tên>" --direction upstream --repo .`. Không dùng `npx`.
  - Gặp HIGH hoặc CRITICAL: dừng lại, gửi Lead bảng impact của **cả 2 task** cùng kế hoạch, một lần, rồi chờ duyệt.
  - Gặp UNKNOWN: kèm bằng chứng `git grep`.
- **Sửa file ngoài danh sách của task:** dừng lại và hỏi Lead.
- **Sửa chú thích hay docstring:** chỉ thêm ý mới. Nếu một câu cũ hết đúng, ghi mốc thời gian cho nó ("trước đợt 220: ..."), không để hai ý trái nhau đứng cạnh nhau.
- **Sau khi sửa:** chạy `node .gitnexus/run.cjs detect-changes --scope all --repo .`.
- **Cấm:**
  - push, hoặc commit vào `main`;
  - chạy `sched.sh`, `run_if_docker_up.sh` hay script cảnh báo/kiểm tra thật;
  - gửi Telegram thật: test dùng hàm gửi giả;
  - restart hay rebuild container, đăng ký hay sửa Task Windows;
  - đọc `.ssi_sdk_token.json`.
- **Test không được ghi vào `logs/` thật.** Dùng `tmp_path`.

## Task 1 (A4). Cảnh báo "token SSI sắp hết hạn" không còn gửi Telegram

- **Hiện trạng:**
  - `scripts/heartbeat_check.py:1592-1606` đẩy tin `[WARN] token SSI sắp hết hạn ... chạy scripts/spike_ssi_sdk_auth.py RỒI scripts/load_token_to_db.py` vào `messages` ở mọi lần chạy heartbeat (5 phút một lần) trong 60 phút trước hạn.
  - Ngày 09/11, tin này được gửi 11 lần từ 08:05 đến 09:00.
  - Lời khuyên trong tin đã sai: `trading/collector/ssi_auth.py` (`ensure_authenticated`) tự xác thực lại khi `refresh_token` hết hạn. Ngày 09/11, hạn là 09:03:34, collector tự xác thực lúc 09:03:45, hạn mới là 17:03:45 (M15).
- **Sửa trong `scripts/heartbeat_check.py`:**
  1. Khi `token_expiry_status` trả `"WARN"`: **không** thêm vào `messages`. Chỉ in một dòng log bằng hàm in hiện có (`_print_safe`), dạng `[INFO] token SSI hết hạn lúc HH:MM dd/mm — collector sẽ tự xác thực lại`. Mã thoát không vì dòng này mà thành 1.
  2. **Thời gian ân hạn cho CRITICAL:** collector cần vài giây sau mốc hạn để tự xác thực, và một lần heartbeat rơi đúng khe đó sẽ báo CRITICAL oan.
     - Trong `token_expiry_status`, hạn đã qua **dưới 10 phút** thì trả `"WARN"` (tức chỉ ghi log), qua 10 phút trở lên mới trả `"CRITICAL"`.
     - Đặt 10 phút thành hằng số có tên trong module, kèm chú thích nêu số đo 09/11 (chênh 11 giây).
     - Trường hợp không có token (`None`) giữ nguyên là `"CRITICAL"`.
  3. **Câu chữ của tin CRITICAL:** thêm ý "collector không tự xác thực lại được", rồi giữ nguyên hướng dẫn chạy `spike_ssi_sdk_auth.py` và `load_token_to_db.py`.
  4. Cập nhật docstring `token_expiry_status` theo hành vi mới (chỉ thêm ý, ghi mốc đợt 220).
- **Kiểm chứng (test mới, giờ giả trong phiên của một ngày giao dịch):**
  - Còn 30 phút tới hạn: `token_expiry_status` trả `"WARN"`; `main` không gửi tin token nào qua hàm gửi giả; log có dòng `[INFO]`.
  - Đã qua hạn 5 phút: trả `"WARN"` (đang trong ân hạn).
  - Đã qua hạn 11 phút: trả `"CRITICAL"`; tin gửi đi có chữ "không tự xác thực lại được".
  - `None`: trả `"CRITICAL"`.
  - Ngoài giờ: trả `None` như cũ.
  - Các test hiện có của `token_expiry_status` phải xanh. Nếu test nào buộc phải đổi vì hành vi mới, liệt kê nó trong báo cáo, kèm lý do.

## Task 2 (A3). Ghi log khi gửi lại tin kẹt trong outbox thành công

- **Hiện trạng:**
  - `AlertOutbox.flush()` (`trading/alerts.py:177`) trả số tin đã gửi.
  - Hai nơi gọi bỏ qua giá trị đó: `send_with_outbox` (`scripts/_alert_common.py:129`) và vòng lặp nền `AlertOutbox._loop` (`trading/alerts.py:286`).
  - Ngày 09/11, tin heartbeat kẹt lúc 08:10 được gửi lại trong khoảng 08:18–08:22 mà không để lại dòng log nào. Chỉ biết được nhờ file outbox biến mất.
- **Sửa:**
  - Trong `send_with_outbox`: nhận giá trị trả về của `outbox.flush()`. Nếu lớn hơn 0, in `[HANG DOI] Đã gửi lại {n} cảnh báo tồn trong {tên file}` bằng `_print_safe`.
  - Trong `AlertOutbox._loop`: nếu `flush()` trả số lớn hơn 0, ghi `_log.info(...)` có số tin.
  - Không đổi gì khác trong `AlertOutbox`.
- **Kiểm chứng:**
  - Outbox ở `tmp_path` có sẵn 2 tin, hàm gửi giả thành công: `send_with_outbox` in đúng dòng "Đã gửi lại 2", và file outbox được xả.
  - Outbox rỗng: không in dòng "Đã gửi lại".
  - Hàm gửi giả ném lỗi: không in "Đã gửi lại"; hành vi xếp hàng như cũ.
  - `_loop`: test với `caplog` cho trường hợp `flush` trả 1 (có log) và trả 0 (không log). Nếu khó test vòng lặp trực tiếp, tách phần thân một vòng thành hàm nhỏ và test hàm đó; ghi rõ trong báo cáo.

## Kiểm chứng cuối (trong worktree)

- `uv run pytest -m "not integration" -q`: mốc là **2354**. Sau khi sửa phải là mốc cộng số test mới, **0 failed**.
- `uv run ruff check trading tests scripts`: sạch.
- `git -C <repo chính> status --short`: thư mục repo chính không đổi.
- Chụp `ls -A logs | sort` cùng nội dung `alert_outbox_*` và `.schedule_health_state.json` của repo chính, trước và sau khi chạy test, rồi so sánh. File do job thật ghi định kỳ được phép đổi mtime.

## Báo cáo cho Lead

- tên nhánh hoặc commit, kèm `git diff --stat main`;
- kết quả `detect-changes`;
- với từng task: test mới và kết quả, các test cũ đã sửa (nếu có) kèm lý do;
- số test trước và sau;
- kết quả so sánh `logs/`.
