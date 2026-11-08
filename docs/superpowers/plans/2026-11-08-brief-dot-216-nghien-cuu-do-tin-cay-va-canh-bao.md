# Brief đợt 216: nghiên cứu độ tin cậy, cảnh báo và an toàn vận hành (chỉ đo và báo cáo)

Ngày 08/11/2026. Người giao: Claude (Lead). Người làm: **Researcher**.

Đây là vòng 2 của nghiên cứu cải thiện hệ thống.
- **Vòng 1 (đợt 214):** đo tài nguyên, DB, job, NATS, đĩa, image và test. Kết quả ở `docs/audit/2026-11-08-nghien-cuu-toi-uu-he-thong.md`; các điểm #1–#4 đã sửa ở đợt 215 (ef4e9c1).
- **Vòng 2 trả lời một câu hỏi khác:** *khi có thứ gì hỏng, hệ thống có biết không, và có ai được báo không?*

## Ngoài phạm vi

- Chiến lược giao dịch và lợi thế (edge).
- Refactor code.
- Những gì đợt 214 đã đo và đã ghi vào mục "Đã ổn".
- Nguồn điện, pin, chế độ ngủ của laptop, và Docker tự khởi động: **không đề xuất**. Triển khai thật là VPS 24/7.
- Lịch nghỉ lễ: **không nhắc, không đề xuất kiểm tra**.

## Cấm (giống đợt 214)

- Sửa, xoá, restart hay rebuild bất cứ thứ gì.
- Đăng ký hay sửa Task Windows.
- Chạy `sched.sh`, `run_if_docker_up.sh`, hay script nạp dữ liệu, đo, đặt lệnh, backup.
- Gọi API của SSI, DNSE hay BingX.
- **Gửi Telegram thật.**
- Chạy script cảnh báo hoặc kiểm tra thật để "thử xem có báo không". Muốn biết có báo hay không thì đọc code và test.
- Ghi vào DB thật: chỉ được `SELECT` và đọc `pg_stat_*`.
- Ghi vào `logs/`.
- Chép mật khẩu, token hay DSN có mật khẩu vào báo cáo.
- Dùng `npx`. Muốn dùng GitNexus thì gọi `node .gitnexus/run.cjs`.
- Commit, push.

**Cách trích số:** số đếm phải trích từ **dòng tổng kết** (`DONE:`, `EXIT=`, dòng summary), không lấy từ dòng tiến độ giữa chừng. Đây là bài học từ đợt 214.

## Năm mảng cần làm

### 1. Bản đồ "hỏng thì ai báo" (ưu tiên cao nhất)

- `scripts/heartbeat_check.py` có `SCHEDULE_EXIT_POLICIES`, trong đó khoảng 16 chỗ ghi "chưa ai báo". Lập bảng cho **mọi job**, gồm:
  - mọi nhánh của `sched.sh`;
  - các job trong container scheduler: catchup, daily-data-check, universe-refresh;
  - chính các service collector, engine, nats và postgres.
- Mỗi job một dòng, với các cột:
  - job;
  - cách nó có thể hỏng: EXIT khác 0, treo, không chạy, chạy nhưng ra dữ liệu sai;
  - thứ gì phát hiện được kiểu hỏng đó: tên hàm, `file:dòng`;
  - đường báo: Telegram, outbox, chỉ log, hay không gì cả;
  - **độ trễ phát hiện tệ nhất**, tính theo lịch của heartbeat và container-health.
- Đánh dấu rõ các ô "**không ai biết**".
- Đối chiếu với sự cố thật trong `logs/` từ 01/10. Sự cố nào đã xảy ra mà không có cảnh báo nào được gửi? Ví dụ: backup SKIP 120 giờ ở đợt 214 có ai báo không? Kiểm bằng `backup-check.log` và outbox.

### 2. Đường gửi cảnh báo

- Telegram gửi đi bằng cách nào (`trading/alerts/`, các file `alert_outbox_*`)?
- Nếu Telegram lỗi, hoặc mạng mất lúc gửi, cảnh báo có được gửi lại không, hay mất luôn?
- Từ 01/10, outbox có cảnh báo nào kẹt hoặc gửi lỗi không? Chỉ đọc file, không sửa.
- Có cơ chế nào báo khi **chính** hệ thống cảnh báo chết không (dead man's switch)? Nếu không có, thì heartbeat chết sẽ mất bao lâu mới có người biết?

### 3. Phục hồi

- Từ `restore-drill.log`: lần diễn tập gần nhất, kết quả, thời gian.
- RPO tệ nhất, tức khoảng mất dữ liệu tối đa:
  - trước đợt 215 là 120 giờ;
  - sau đợt 215, tính theo thiết kế mới (dump bù khi dump cũ hơn 26 giờ, kiểm mỗi giờ).
- RTO ước tính: từ lúc mất volume tới lúc engine chạy lại, dựa trên DEPLOYMENT.md và số đo của restore-drill.
- Những gì **không** nằm trong backup DB: `config/`, `.env`, token SSI, file orderbook, `data/`. Mất máy thì những thứ này lấy lại từ đâu? Chỉ ghi tên file và nơi lưu, **không mở** file bí mật.

### 4. An toàn vận hành

- Cổng mở ra ngoài: `docker-compose.yml` đang bind `127.0.0.1` cho 5432, 4222, 4223 và 3000. Kiểm thêm bằng `netstat -ano`, xem có cổng nào của dự án nghe trên `0.0.0.0` không.
- Image có chứa bí mật không. Chạy `docker history --no-trunc` và liệt kê file trong image bằng `docker run --rm --entrypoint sh <image> -c "ls -la /app"`, chỉ liệt kê, không `cat` file nào. Có `.env` hay file token nào lọt vào không?
- Grafana còn dùng mật khẩu mặc định `admin` không: chỉ kiểm biến `GRAFANA_ADMIN_PASSWORD` **có được đặt hay không**, không in giá trị.
- `real_trading_enabled` và tài khoản đặt lệnh thật: những cổng nào chặn một lệnh thật bị gửi nhầm? Ghi `file:dòng` và test đang bảo vệ từng cổng.

### 5. Các phép đo chỉ làm được trong phiên giao dịch (lập kế hoạch, không đo hôm nay)

- Hôm nay là Chủ nhật. Viết **kịch bản đo** cho phiên thứ Hai 09/11, theo các mục "Chưa đo được" của đợt 214:
  - độ trễ từ lúc nến đóng tới lúc engine xử lý;
  - `docker stats` trong phiên;
  - `memory.events` của postgres trước và sau backup 02:00.
- Mỗi phép đo ghi: lệnh, giờ chạy, và số liệu cần ghi lại.
- Lead sẽ giao chạy kịch bản này trong một đợt riêng.

## Đầu ra

**Một file duy nhất:** `docs/audit/2026-11-08-nghien-cuu-do-tin-cay-canh-bao.md`, gồm:
- bảng ở mảng 1;
- các phát hiện dưới dạng bảng: `# | Mảng | Hiện trạng (bằng chứng) | Đề xuất | Lợi ích | Rủi ro | Công sức`. Tối đa 15 dòng, xếp theo mức nghiêm trọng, tức khả năng hỏng âm thầm nhân với thiệt hại;
- mục "Đã ổn";
- mục "Chưa kiểm được";
- kịch bản đo cho thứ Hai.

## Báo cáo cho Lead

- Đường dẫn file.
- Top 5 phát hiện kèm bằng chứng.
- Danh sách job thuộc loại "**hỏng mà không ai biết**".
