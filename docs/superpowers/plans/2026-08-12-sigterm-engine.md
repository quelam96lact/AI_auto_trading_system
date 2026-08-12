# Kế hoạch: kiểm chứng SIGTERM của engine (B1)

Ngày giao: 2026-08-12. Nhánh: `feature/data-layer`. Base: `9d829f0`.

## Phát hiện làm thay đổi giả định cũ

Trước đây B1 bị xếp là "cần VPS". **Sai.** Toàn bộ stack chạy trong Docker,
container engine chạy Linux nên `loop.add_signal_handler` hoạt động thật
(`trading/engine/main.py:35-36`) chứ không rơi vào nhánh fallback Windows ở
dòng 38-39. Postgres + NATS đã chạy sẵn ở local. Làm được ngay.

## Mục tiêu

Chứng minh: `docker compose stop engine` → engine thoát **sạch** (exit code 0,
không bị SIGKILL) trong vòng 10 giây.

"Sạch" nghĩa là engine tự thoát vì `stop_event` được set, chứ không phải bị
Docker giết sau khi hết grace period.

## Bối cảnh kỹ thuật cần biết

- `docker-compose.yml` **không khai báo `stop_grace_period`**. Docker mặc định
  10s: gửi SIGTERM, chờ 10s, nếu chưa chết thì SIGKILL. Tiêu chí "10 giây" hiện
  đang dựa vào mặc định ngầm này — chưa ai ghi lại nó như một quyết định.
- `engine/main.py:128-139`: vòng lặp đua `next_msg` với `stop_event.wait()`
  bằng `asyncio.wait(..., FIRST_COMPLETED)`, nên SIGTERM lúc engine đang **rảnh**
  (đang chờ message) vẫn phải thoát ngay, không phải chờ hết timeout.
  **Đây chính là trường hợp cần kiểm chứng**, vì không có collector chạy thì
  engine luôn ở trạng thái rảnh.

## Việc cần làm

Chỉ chạy và đo. **Không sửa code nào** trừ khi phát hiện lỗi thật — nếu phát
hiện, báo cáo trước, đừng tự sửa.

### Ràng buộc an toàn (bắt buộc)

- **CHỈ khởi động `engine`.** TUYỆT ĐỐI không chạy `collector` — nó sẽ gọi API
  SSI thật và ghi vào `bars`/`bars_daily`.
- Engine chạy paper mode (`real_trading_enabled=False` trong config) nên không
  đặt lệnh thật. Nó sẽ ghi một dòng vào `heartbeat` — chấp nhận được.
- Không `docker compose down`, không xoá volume. Postgres và NATS đang chạy có
  dữ liệu dev.
- Không đụng `.env`, không in nội dung biến môi trường nào ra log.

### Các bước

1. `docker compose up -d --build engine` → chờ nó lên.
2. Xác nhận engine thật sự đang chạy và đã kết nối (xem `docker compose logs
   engine`), không phải đang crash-loop. Nếu nó restart liên tục, **dừng lại và
   báo cáo** — đó là một lỗi khác, không thuộc task này.
3. Đo thời gian: chạy `docker compose stop engine` và bấm giờ.
4. Lấy exit code: `docker inspect --format '{{.State.ExitCode}}' <container>`.

## Kiểm chứng (dán output THẬT)

1. **Exit code = 0.**
   → Nếu là **137** thì nghĩa là bị SIGKILL (128+9) — engine KHÔNG thoát sạch,
   Docker phải giết nó. Đó là **thất bại**, báo cáo thẳng, đừng diễn giải nhẹ đi.
2. **Thời gian < 10 giây.** Dán con số đo được thật (dùng `Measure-Command`
   hoặc tương đương), không ước lượng.
3. **Log cuối cùng của engine** cho thấy nó thoát chủ động, không phải bị cắt
   giữa chừng. Dán vài dòng cuối của `docker compose logs engine`.
4. **Lặp lại 3 lần** (up → stop → đo). Một lần thoát nhanh có thể là may.
   → Dán cả 3 cặp (exit code, thời gian).

## Câu hỏi cần trả lời trong báo cáo

Ngoài pass/fail, trả lời: **thời gian thoát thực tế là bao nhiêu giây?**
Nếu nó sát 10s thì tiêu chí đang mong manh và ta cần khai báo
`stop_grace_period` tường minh. Nếu nó dưới 2s thì mặc định 10s là dư dả.
Con số này quyết định việc tiếp theo, nên đừng chỉ trả lời "đạt".

## Không được làm

- Không commit, không push.
- Không sửa `docker-compose.yml` (việc thêm `stop_grace_period` là quyết định
  của chủ dự án, sau khi có số đo).
- Không chạy collector.
- Không chạy suite integration trong lúc engine đang chạy — sẽ tranh chấp
  stream BARS và DB.
