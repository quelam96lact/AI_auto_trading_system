# Brief đợt 214: nghiên cứu tối ưu toàn hệ thống (chỉ đo và báo cáo)

Ngày 08/11/2026. Người giao: Claude (Lead). Người làm: **Researcher**.

## Mục tiêu

Lập **danh sách cơ hội tối ưu có số đo** cho hệ thống đang chạy thật: tài nguyên, độ trễ, độ tin cậy, dung lượng và thời gian chạy test. Đợt này **không sửa gì cả**.

Ngoài phạm vi:
- **Chiến lược giao dịch và lợi thế (edge).** Đã có 28 phép đo âm; đó là việc riêng của chủ dự án.
- **Refactor code.** Đã làm ở đợt 211–213, xem `docs/audit/2026-11-08-ra-soat-refactor.md`.

## Giả định (Lead đã chốt)

- "Tối ưu" ở đây nghĩa là **vận hành**: hệ thống chạy nhanh hơn, nhẹ hơn, ít hỏng hơn và ít tốn đĩa hơn. Không có nghĩa là tối ưu tham số chiến lược.
- Máy đo là laptop hiện tại. Triển khai thật là VPS chạy 24/7. **Không đề xuất** chỉnh nguồn điện, pin, chế độ ngủ hay việc Docker tự khởi động.

## Cấm

- Sửa, xoá, restart hoặc rebuild bất cứ thứ gì: code, config, container, image, volume, cron, Task Windows.
- Chạy `sched.sh`, script nạp dữ liệu, script đo hay script đặt lệnh, và gọi API của SSI, DNSE hay BingX.
- Ghi vào DB thật:
  - Chỉ được chạy `SELECT` và đọc các view `pg_stat_*` hoặc `timescaledb_information.*`.
  - Không chạy `EXPLAIN ANALYZE` trên câu lệnh có ghi.
  - Không chạy `VACUUM` hay `ANALYZE`.
  - Không bật extension nào.
- Ghi vào `logs/`. Chỉ được đọc.
- Chép mật khẩu, token hay DSN có mật khẩu vào báo cáo.
- Dùng `npx`. Muốn dùng GitNexus thì gọi `node .gitnexus/run.cjs`.
- Commit, push.

**Kết nối DB:** chỉ dùng `docker compose exec -T postgres psql -U trading -d trading -c "<SELECT ...>"`, hoặc host `127.0.0.1`. Không dùng `localhost`.

## Bảy mảng cần đo

Với mỗi mảng, ghi lại **lệnh đã chạy và output rút gọn**.

1. **Tài nguyên container.**
   - Chụp `docker stats --no-stream` 3 lần, cách nhau 1 phút, và nói rõ đang trong hay ngoài phiên giao dịch.
   - So mức dùng với `mem_limit` và `cpus` trong `docker-compose.yml`.
   - Đọc `memory.events` (các dòng `max`, `oom`, `oom_kill`) của từng container.
   - Bối cảnh: postgres từng vượt giới hạn bộ nhớ và đã được sửa ở 2d113df. Kiểm xem lỗi đó có tái diễn không.
2. **Postgres / TimescaleDB.**
   - Kích thước từng bảng và hypertable, số chunk của mỗi bảng.
   - Trạng thái chính sách nén và retention.
   - Index có `idx_scan = 0` và kích thước của chúng.
   - Số dead tuple và lần autovacuum gần nhất.
   - Nếu `pg_stat_statements` đã bật sẵn: top 10 truy vấn theo tổng thời gian. Nếu chưa bật thì ghi là chưa bật, **không bật**.
   - Tỉ lệ cache hit.
3. **Các job của scheduler.**
   - Đọc log container scheduler từ 01/11 tới nay.
   - Với mỗi job (catchup, 06:40, 21:45 và các job con), lấy thời gian chạy, EXIT và số lần lỗi.
   - Chỉ ra job chậm nhất, các job chạy chồng lên nhau, và job nào có thể chạy song song.
   - Nhớ rằng timestamp trong log là UTC.
4. **Đường dữ liệu collector → NATS → engine.**
   - `nats stream info` hoặc endpoint monitor: kích thước stream BARS, giới hạn của stream, độ trễ của consumer.
   - Khoảng cách từ lúc nến đóng tới lúc engine xử lý, nếu đo được từ log hoặc DB mà không cần ghi gì.
   - Số lần reconnect hay lỗi trong 7 ngày qua.
5. **Đĩa và backup.**
   - Mức tăng của volume `pgdata`: so `pg_database_size` với các số liệu cũ trong docs, nếu có.
   - Kích thước và cách giữ backup trong thư mục backup.
   - Dự báo số ngày còn lại trước khi đầy đĩa theo mức tăng hiện tại.
6. **Image và build.**
   - Kích thước image.
   - Thứ tự layer trong `Dockerfile`: sửa code có làm mất cache của bước `uv sync` hay không.
   - Thời gian build, nếu tìm được trong log hay ghi chép cũ. Không tự build.
7. **Bộ test.**
   - Chạy `uv run pytest -m "not integration" -q --durations=25`.
   - Bộ test đầy đủ ở pre-push mất khoảng 4 phút. Chỉ ra các test chậm nhất và lý do (sleep, gọi DB, dữ liệu lớn).
   - Không chạy suite integration.

## Đầu ra

**Một file duy nhất:** `docs/audit/2026-11-08-nghien-cuu-toi-uu-he-thong.md`. Mỗi cơ hội là một dòng trong bảng:

| # | Mảng | Hiện trạng (số đo) | Đề xuất | Lợi ích ước tính (có số) | Rủi ro | Công sức | Bằng chứng (lệnh + output rút gọn) |

- Tối đa 20 dòng, xếp theo lợi ích chia rủi ro, cao nhất lên đầu.
- **Không có số đo thì không được ghi.** Thứ gì chưa đo được thì đưa vào mục "Chưa đo được", kèm lý do.
- Thêm mục **"Đã ổn, không cần làm"**: những chỗ đã đo và thấy tốt, kèm số liệu. Mục này để tránh đề xuất thừa.
- Đề xuất nào đụng tới `postgresql.conf` hay `mem_limit` thì phải nêu rõ ràng buộc trong chú thích ở `docker-compose.yml`: shared_buffers bằng 25% và effective_cache_size bằng 75% của mem_limit, và phải đổi cùng lúc.

## Báo cáo cho Lead

- Đường dẫn file.
- Top 5 cơ hội, mỗi cơ hội kèm số đo.
- Mục nào có rủi ro gây mất dữ liệu hoặc làm hỏng phiên giao dịch thật thì nêu riêng.
