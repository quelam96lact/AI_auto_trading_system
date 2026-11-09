# Brief đợt 219: đo trong phiên thứ Hai 09/11 (chỉ đo và báo cáo)

Ngày 09/11/2026. Người giao: Claude (Lead). Người làm: **Researcher**.

Đợt này chạy kịch bản M1–M12 ở mục 8 của `docs/audit/2026-11-08-nghien-cuu-do-tin-cay-canh-bao.md`, kịch bản do chính Researcher viết.

## Những gì đã thay đổi so với lúc viết kịch bản

- **Đợt 217 (ae7c84b) đã deploy lúc 01:19 hôm nay:**
  - Có task mới `trading-schedule-watch`, chạy mỗi giờ (log `logs/schedule-watch.log`).
  - Scheduler gửi cảnh báo khi job lỗi.
  - Các script kiểm tra thoát mã 3 khi crash.
- **M3 và M4 Lead đã đo, Researcher không đo lại:**
  - **M3:** catchup 06:40 có `finish dur=2.55s`, `EXIT=0`.
  - **M4:** postgres khởi động lúc 01:03. Tới 07:21, qua cả backup 02:00, `memory.events` có `max` 1.391, `oom` 0, `oom_kill` 0. Postgres dùng 717,7 MiB trên 1 GiB.
  - Backup 02:00 `EXIT=0` (dump 150 MB).
- **Builder làm đợt 218 trong worktree riêng.** Thư mục repo chính và container không bị đổi trong phiên. Nếu thấy container restart hay file trong `scripts/` thay đổi giữa phiên, ghi lại giờ và báo Lead ngay.

## Phạm vi

Đo M1, M2 và M5–M12 đúng giờ trong kịch bản. Giờ nào đã lỡ (ví dụ M1 lúc 08:00) thì đo ngay khi nhận brief và ghi giờ thực tế. Ngoài ra đo thêm:

- **M13:** đọc `logs/schedule-watch.log` cả ngày. Ghi số lần chạy, giờ từng lần, và mọi `EXIT` khác 0. Task đặt chạy ở phút :07; nếu giờ chạy thực tế lệch xa thì ghi lại độ lệch.
- **M14:** `docker logs --since 2026-11-08T18:00:00Z ai_auto_trading_system-scheduler-1`. Có dòng cảnh báo nào ("Scheduler job thất bại") không? Có lỗi `start_outbox` nào không?

## Cấm (giống đợt 216)

- Sửa, xoá, restart hay rebuild bất cứ thứ gì; đăng ký hay sửa Task Windows.
- Chạy `sched.sh`, `run_if_docker_up.sh`, script nạp dữ liệu, đặt lệnh hay backup.
- Chạy script cảnh báo hoặc kiểm tra thật. Riêng `scripts/measure_bar_latency.py` (M8) thì được chạy, vì nó chỉ đọc log.
- Gọi API của SSI, DNSE hay BingX; gửi Telegram thật.
- Ghi vào DB: chỉ `SELECT`. Ghi vào `logs/`: không.
- Chép mật khẩu, token hay DSN vào báo cáo.
- Dùng `npx`; commit; push.

**Cách trích số:** lấy từ dòng tổng kết (`DONE:`, `EXIT=`, summary), không lấy từ dòng tiến độ giữa chừng.

## Đầu ra

**Một file duy nhất:** `docs/audit/2026-11-09-do-trong-phien.md`, gồm:

- bảng M1–M14, với các cột `# | Giờ đo thực tế | Lệnh | Kết quả (số) | So với kỳ vọng/ngưỡng | Ghi chú`;
- mục "Bất thường", xếp theo mức nghiêm trọng, mỗi dòng kèm bằng chứng;
- mục "Chưa đo được", kèm lý do.

## Báo cáo cho Lead

- **Ngay khi thấy:** container restart, cảnh báo CRITICAL thật, hoặc dữ liệu ngừng chảy (tuổi nến hay nhịp vượt ngưỡng). Báo ngay, không đợi hết phiên.
- **Sau 15:45:**
  - đường dẫn file báo cáo;
  - 5 kết quả đáng chú ý nhất, kèm số đo;
  - mọi bất thường.
