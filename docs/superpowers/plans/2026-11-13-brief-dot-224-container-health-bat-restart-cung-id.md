# Brief đợt 224: container-health phải bắt được restart cùng Id (StartedAt đổi, RestartCount đứng yên)

Ngày 13/11/2026, 08:15. Người giao: Claude (Lead). Người làm: **Builder**.

## Bối cảnh (Researcher báo 08:04, Lead đã tự kiểm)

- Lúc 07:45, Docker Desktop tự cập nhật từ 29.9.2 lên 29.9.3 và khởi động lại. Docker dừng khoảng 67 giây.
- Cả 7 container có `StartedAt = 2026-11-13T00:46:18Z`, **cùng Id cũ**, `RestartCount = 0`.
- Lần chạy `container-health` lúc 07:50:05 ra `EXIT=0` và **không ghi gì**. Script có lưu `started_at` vào file trạng thái, nhưng không dùng để so sánh.
- Hệ quả: các trường hợp sau đều vô hình với `container-health`:
  - daemon restart;
  - `docker restart` bằng tay;
  - container được Docker Desktop dựng lại sau khi cập nhật.

  Nếu chuyện này xảy ra trong phiên, collector mất stream mà không có tin báo nào từ job này.
- Kèm theo: `memory.events` của postgres reset về 0 vì cgroup mới. Bộ đếm `oom_kill` và `max` cũng về 0 khi container khởi động lại.

## Việc phải làm

**Trước khi sửa:** chạy `node .gitnexus/run.cjs impact ... --repo .` cho hàm đánh giá trạng thái. `scripts/` không được GitNexus index, nên kết quả sẽ ra UNKNOWN; khi đó tìm caller bằng grep và báo lại. **Không dùng npx.**

### 1. Cùng Id, `StartedAt` đổi, `RestartCount` không tăng: CRITICAL một lần

- Nội dung tin phải nêu tên container, `StartedAt` cũ và `StartedAt` mới.
- Nếu `RestartCount` cũng tăng thì nhánh restart hiện có đã báo rồi. **Không** báo trùng hai tin cho cùng một container trong cùng một lần chạy.
- Nhiều container cùng restart trong một lần chạy thì gom vào **một** tin Telegram. Hiện các cảnh báo đã được nối vào `alert_body`; kiểm lại cho chắc là vẫn như vậy.
- Trạng thái cũ thiếu `started_at`, hoặc giá trị là chuỗi rỗng (các bản ghi từ thời còn mù): coi là ghi mốc, **không** báo.

### 2. Đặt lại mốc `memory.events` khi `StartedAt` đổi

- Khi container khởi động lại, mốc `oom_kill` và `max` phải lấy theo giá trị mới (thường là 0).
- Mục tiêu: một lần OOM sau đó (0 → 1) **vẫn** bị bắt.
- Viết test cho đúng chuỗi sau:
  - mốc `oom_kill = 2`;
  - restart, `oom_kill` về 0;
  - lần chạy sau `oom_kill = 1`;
  - kỳ vọng: có CRITICAL OOM.
- Kiểm xem code hiện tại có trượt chuỗi này không. Báo lại kết quả, kể cả khi code hiện tại đã đúng.

### 3. Test

Viết test cho các trường hợp sau, dùng `evaluate_container_health` với trạng thái giả và `tmp_path`, không đụng `logs/` thật:

- cùng Id, `StartedAt` đổi → 1 CRITICAL;
- `StartedAt` không đổi → không báo;
- trạng thái cũ có `started_at = ""` → không báo;
- cùng Id, `StartedAt` đổi **và** `RestartCount` tăng → đúng 1 cảnh báo cho container đó;
- 6 container cùng đổi `StartedAt` → `main()` gửi đúng 1 tin (mock `send_telegram`);
- chuỗi OOM ở mục 2.

Các test mới phải **thất bại trên code hiện tại** (trừ test ở mục 2 nếu code hiện tại đã đúng). Gửi output chạy test trên code cũ để chứng minh.

## Cách làm việc: BẮT BUỘC dùng worktree riêng

Script này chạy thật mỗi 10 phút, **thẳng từ thư mục làm việc chính**. Lần chạy 00:10 hôm nay đã chạy code đợt 223 trước cả khi Lead commit. Vì vậy:

- Tạo worktree: `git worktree add ../AI_auto_trading_system-dot224 -b dot224 HEAD`, rồi làm mọi việc trong đó.
- **Không sửa file nào trong thư mục chính** `D:\My_Vault_Obsidian\Project\AI_auto_trading_system`.
- Chạy test trong worktree bằng `uv run pytest ...`. Test chỉ đọc container thật thì được phép.
- Lead sẽ tự audit, rồi merge hoặc cherry-pick vào main **sau 15:00** (hết phiên).

## Phạm vi

- **Được sửa** (trong worktree): `scripts/container_health_check.py`, `tests/test_container_health_check.py`.
- **Không đụng:** `scripts/heartbeat_check.py`, `scripts/sched.sh`, `scripts/run_if_docker_up.sh`, Task Windows, `docker-compose.yml`, `trading/`, cài đặt Docker Desktop.
- Giữ nguyên style, không refactor. Thấy vấn đề khác thì báo lại.

## Cấm

- Chạy `sched.sh`, chạy `container_health_check` thật, gửi Telegram.
- Ghi vào `logs/` thật.
- Restart hoặc rebuild container. Đổi cài đặt Docker.
- Commit lên `main`, push, dùng `npx`. Commit trong nhánh `dot224` của worktree thì được.

## Tiêu chí hoàn thành (bằng chứng phải gửi)

1. Output impact (hoặc grep caller nếu ra UNKNOWN).
2. Tên các test mới, kèm output chạy chúng **trên code cũ** (thất bại) và **trên code mới** (pass).
3. `uv run pytest tests/test_container_health_check.py tests/test_schedule_watch.py -q` pass.
4. `uv run pytest -m "not integration" -q`: tổng số pass/fail, chạy trong worktree.
5. `uv run ruff check scripts tests` sạch.
6. `git -C <worktree> log --oneline main..dot224` và `git diff --stat main..dot224`.
