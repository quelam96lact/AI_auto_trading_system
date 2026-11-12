# Brief đợt 221: `init: true` cho engine, collector, scheduler

Ngày 12/11/2026. Người giao: Claude (Lead). Người làm: **Builder**.

## Vì sao

- **Ngày 09/11, lúc deploy đợt 218:** `docker compose up --force-recreate` báo lỗi:

  ```
  cannot stop container: 1fc00abaf770...: container 1fc00abaf770 PID 5310 is zombie and can not be killed.
  Use the --init option when creating containers to run an init inside the container that forwards signals and reaps processes
  ```

  Cả ba container cũ đều thoát mã **137** (bị SIGKILL), và Lead phải xoá tay 6 container kẹt ở trạng thái `Created`.
- **Cả ba service chạy `python` làm PID 1, không có init** (`docker-compose.yml:71-136`; `docker top` chỉ có một tiến trình `python`):
  - Với PID 1, kernel không áp hành động mặc định của SIGTERM. Scheduler không cài trình bắt SIGTERM (`trading/scheduler/main.py` chỉ dùng `threading.Event`), nên mỗi lần dừng nó phải chờ hết 10 giây rồi bị SIGKILL.
  - Scheduler chạy job bằng `subprocess.Popen` (`trading/scheduler/main.py:180`). Khi hết thời gian chờ, nó chỉ `proc.kill()` tiến trình con trực tiếp. Các tiến trình cháu (`uv run` → `python`) mồ côi sẽ về PID 1, mà PID 1 là `python`, không dọn tiến trình đã chết, nên thành zombie.
  - `init: true` cho Docker chạy `docker-init` (tini) làm PID 1. Nó chuyển tiếp tín hiệu và dọn zombie. Đây là cách Docker tự gợi ý trong thông báo lỗi.

## Quy tắc chung

- **Worktree riêng:**
  - Tạo bằng `git worktree add ../AI_auto_trading_system-wt221 -b dot221 main`.
  - Làm và chạy test trong đó. Có thể commit lên nhánh `dot221`; Lead tự merge.
- **Impact:** `docker-compose.yml` không phải symbol Python. Chạy `node .gitnexus/run.cjs impact "docker-compose.yml" --direction upstream --repo .` và đưa kết quả vào báo cáo. Không dùng `npx`.
- **Cấm:**
  - push, hoặc commit vào `main`;
  - chạy `docker compose up`, `stop`, `restart` hay `build`;
  - đổi service khác ngoài ba service nói trên (postgres, nats, nats-test, grafana giữ nguyên);
  - đổi `command`, `mem_limit`, `cpus`, `restart` hay bất kỳ khoá nào khác;
  - thêm trình bắt SIGTERM vào scheduler (không thuộc đợt này).
- **Sau khi sửa:** chạy `node .gitnexus/run.cjs detect-changes --scope all --repo .`.

## Task 1. Thêm `init: true`

- **Sửa:** trong `docker-compose.yml`, thêm `init: true` cho đúng ba service `engine`, `collector`, `scheduler`.
  - Đặt ngay dưới dòng `command:` của mỗi service.
  - Thêm một chú thích ngắn (một lần, ở service đầu tiên) nêu lý do, kèm mốc "đợt 221, lỗi zombie khi deploy 09/11".
- **Kiểm chứng:**
  - Test mới `tests/test_compose_init.py`:
    - đọc `docker-compose.yml` bằng `yaml.safe_load`;
    - assert ba service `engine`, `collector`, `scheduler` có `init` bằng `True`;
    - assert `postgres`, `nats`, `grafana` **không** có khoá `init`, để chặn việc sửa tràn.
  - `docker compose config --quiet` thoát 0. Lệnh này chỉ đọc, được phép chạy; nó không khởi động gì.

## Kiểm chứng cuối (trong worktree)

- `uv run pytest -m "not integration" -q`: mốc **2366**. Sau khi sửa phải là 2366 cộng số test mới, **0 failed**.
- `uv run ruff check trading tests scripts`: sạch.
- `git diff --stat main`: chỉ có `docker-compose.yml` và `tests/test_compose_init.py`.

## Lead tự làm sau khi merge (Builder không làm)

- gắn tag `:previous` cho image, rồi `up -d --no-deps --force-recreate collector engine scheduler`;
- `docker top` từng container: PID 1 phải là `docker-init` (hoặc `tini`), `python` là con của nó;
- đo một lần `docker compose stop scheduler` (thời gian dừng và mã thoát), rồi `up` lại ngay. Làm ngoài giờ giao dịch.

## Báo cáo cho Lead

- nhánh hoặc commit, kèm `git diff --stat main`;
- kết quả `impact` và `detect-changes`;
- test mới và kết quả; số test trước và sau;
- kết quả `docker compose config --quiet`.
