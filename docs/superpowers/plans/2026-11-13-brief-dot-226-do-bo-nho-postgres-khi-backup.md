# Brief đợt 226: đo bộ nhớ postgres trong cửa sổ backup 02:00 (đêm 13→14/11)

Ngày 13/11/2026. Người giao: Claude (Lead). Người làm: **Researcher**. Việc này chỉ đo, không sửa gì.

## Câu hỏi cần trả lời

Đêm 12→13/11, `memory.events max` của container postgres tăng thêm khoảng 1.046 trong cửa sổ 02:00–02:10 (A8, báo cáo `docs/audit/2026-11-13-do-phien-sau-dot-220-221.md`). `oom_kill` vẫn bằng 0. Cần trả lời ba câu:

1. Lần tăng đó có lặp lại đêm nay không, và tăng bao nhiêu? Mốc hiện tại là cgroup mới từ 13/11 07:46, khi đó `max` bằng 0.
2. Bộ nhớ chạm trần vì loại nào: page cache của file (`file`, thu hồi được, vô hại) hay `shmem`/`anon` (không thu hồi được, nguy hiểm, đúng kiểu sự cố ngày 29/09 đã sửa ở `2d113df`)?
3. `backup_db.sh` ghi dump vào `/tmp` **bên trong container** (xem `logs/backup.log`: `/tmp/trading_YYYYMMDD_HHMMSS.dump`, khoảng 150M), rồi `docker cp` ra ngoài. `/tmp` của container là tmpfs hay overlay? Nếu là tmpfs, 150M dump bị tính vào `shmem` của cgroup postgres.

## Cách đo (chỉ đọc)

- Container: `ai_auto_trading_system-postgres-1`. Trên Git Bash dùng `MSYS_NO_PATHCONV=1` như báo cáo 13/11 đã làm.
- Đọc các file sau trong `/sys/fs/cgroup/`:
  - `memory.events`;
  - `memory.current`, `memory.max`, `memory.peak` (nếu có);
  - từ `memory.stat`, các dòng `anon`, `file`, `shmem`, `file_dirty`, `file_writeback`.
- Lấy mẫu:
  - **Trước:** một mẫu lúc khoảng 01:50.
  - **Trong cửa sổ:** từ 01:58 đến 02:15, mỗi **30 giây** một mẫu.
  - **Sau:** một mẫu lúc 02:30 và một mẫu lúc 03:05.
  
  Chạy bằng vòng lặp nền của chính bạn. Ghi kết quả ra file trong **scratchpad của bạn**, không ghi vào `logs/`.
- Kiểu của `/tmp`: `docker exec ... sh -c 'df -h /tmp; mount | grep " /tmp "'`, chỉ đọc. Làm được ngay, không cần đợi đêm.
- Đọc `scripts/backup_db.sh` để biết lệnh `pg_dump` dùng tham số gì (`-Fc`, `-j`, ...) và file `/tmp` có bị xoá sau `docker cp` không. Mở thêm mục `logs/backup.log` của đêm nay (giờ start/EXIT, kích thước dump).
- So với mốc ngày 29/09 sau khi sửa: `memory.peak` ≈ 62,6 MB, `shmem` 35 MB, `max` 0.

## Niêm phong và cấm

- **Không** chạy `sched.sh`, `backup_db.sh`, `pg_dump`, hay bất kỳ backup hoặc restore nào bằng tay. Chỉ quan sát lần backup theo lịch.
- **Không** restart, rebuild hay đổi cài đặt container hoặc Docker. **Không** xoá file trong `/tmp` của container.
- **Không** ghi DB, chỉ SELECT nếu cần. Không gọi API SSI/DNSE/BingX, không gửi Telegram, không đọc file token SDK, không ghi `logs/`.
- Không commit, không push, không dùng `npx`.
- Nếu đêm nay backup không chạy (Docker tắt, máy ngủ, `SKIP`), ghi đúng như vậy cùng bằng chứng log. **Không** chạy bù.

## Tiêu chí hoàn thành

Viết báo cáo vào `docs/audit/2026-11-14-do-bo-nho-postgres-khi-backup.md` (Lead sẽ audit và commit). Báo cáo gồm:

1. Bảng mẫu: giờ, `max`, `oom_kill`, `memory.current`, `anon`, `file`, `shmem`, `file_dirty`. Ghi đủ, không chỉ mẫu đẹp.
2. Kiểu `/tmp` kèm output nguyên văn.
3. Các mốc giờ của backup đêm nay lấy từ `backup.log`: start, ghi xong dump, `docker cp`, `EXIT`.
4. Trả lời ba câu hỏi ở trên. Tách rõ **đo được** với **suy luận**.
5. Đề xuất, nếu có: ví dụ ghi dump ra volume hoặc stream thẳng ra host. Chỉ đề xuất, Lead quyết.

Gửi Lead một tin ngắn khi báo cáo xong, kèm đường dẫn file.
