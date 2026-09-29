# Brief đợt 129 — postgres cấu hình vượt giới hạn bộ nhớ container; hook pre-push kiểm sai thứ

**Base commit:** `6df0a73`.
**Người thực thi:** agent. **Người áp lên stack thật, audit, commit, push:** Claude.

---

## §0. Bối cảnh — số đo của Claude, 29/09 lúc 17:40 (chỉ đọc)

### Việc 1 (GẤP): postgres sẽ bị kill vì hết bộ nhớ

`docker-compose.yml` giới hạn postgres `mem_limit: 1g`, `cpus: 1.0`. Nhưng `postgresql.conf` trong volume, do `timescaledb-tune` sinh lúc `initdb` bằng cách dò **RAM của máy** chứ không phải giới hạn của container, đặt:

| Tham số | Giá trị hiện tại | So với giới hạn 1 GiB |
|---|---|---|
| `shared_buffers` | 250496 × 8 kB ≈ **1,9 GB** | **gấp đôi** giới hạn |
| `maintenance_work_mem` | 1002447 kB ≈ **979 MB** | một lần `CREATE INDEX`/`VACUUM` là đủ chạm trần |
| `effective_cache_size` | ≈ 5,7 GB | không cấp phát, nhưng sai khiến planner nghĩ sai |
| `max_parallel_workers_per_gather` / `max_parallel_maintenance_workers` | **4** / **2** (`max_parallel_workers` 8) | container chỉ có **1 CPU**; song song chỉ tốn thêm bộ nhớ chia sẻ |

cgroup của container (`/sys/fs/cgroup`, khởi động lúc 09:42 hôm nay):

```
memory.max:  1073741824
memory.peak: 1073750016        <- đã chạm trần
shmem 876867584                <- shared_buffers đã chiếm 877 MB, KHÔNG thu hồi được
anon  29257728
memory.events: max 10195  oom 0  oom_kill 0
```

`shmem` chỉ tăng, và còn được phép tăng đến 1,9 GB. Khi một truy vấn đọc thêm khoảng 150 MB dữ liệu chưa có trong bộ đệm, **kernel sẽ kill postgres**, và collector, engine, NAV đều dừng theo. Hai ứng viên sắp tới là: phép gộp chunk thứ Bảy 03/10 (đợt 128, đọc và ghi lại toàn bộ `bars_daily` 474 MB), và bất kỳ script đo nào quét cả `bars_daily`.

**Lên VPS vẫn y như vậy:** `initdb` trên VPS lại dò RAM của VPS, trong khi compose vẫn giới hạn 1 GiB. Vì vậy cách sửa phải **nằm trong repo**, không nằm trong volume.

### Việc 2: hook pre-push kiểm working tree, không kiểm commit được push

`.githooks/pre-push:13` và `:23` chạy `ruff`/`pytest` trên **thư mục làm việc**, không chạy trên `_local_sha` đang được push. Hai hậu quả, cả hai đều đã xảy ra hôm nay:
- **Đỏ giả:** file dở dang **chưa commit** của agent (đợt 128) làm hook chặn push của Claude (đợt 127). Claude phải tự tạo `git worktree` để push đúng trạng thái commit.
- **Xanh giả (nguy hiểm hơn):** sửa một file mà quên `git add`, thì hook kiểm **bản đã sửa** và cho qua, còn lên GitHub là **bản hỏng**. Đây đúng là kiểu "cổng báo xanh giả" đã ghi trong bộ nhớ dự án.

---

## §1. Việc 1 — đặt bộ nhớ postgres khớp giới hạn container

### 1a. Thay đổi (chỉ `docker-compose.yml`, service `postgres`)

Thêm `command:` truyền cờ `-c`. **Cờ dòng lệnh thắng cả `postgresql.conf` lẫn `postgresql.auto.conf`**, nên áp được cho volume đang có trên máy này **và** cho `initdb` mới trên VPS. **Không** sửa file trong volume, **không** dùng `ALTER SYSTEM`.

Giá trị đăng ký trước. Không tự đổi; muốn đổi thì báo lý do kèm số đo.

| Tham số | Giá trị | Lý do |
|---|---|---|
| `shared_buffers` | `256MB` | 25% của 1 GiB (khuyến nghị chuẩn của Postgres) |
| `effective_cache_size` | `768MB` | 75% của 1 GiB |
| `maintenance_work_mem` | `128MB` | đủ cho index của `bars_daily`; không đẩy container chạm trần |
| `work_mem` | `8MB` | giữ gần giá trị hiện tại (7.831 kB) |
| `max_parallel_workers_per_gather` | `0` | `cpus: 1.0`: song song không nhanh hơn, chỉ tốn bộ nhớ chia sẻ |
| `max_parallel_maintenance_workers` | `0` | cùng lý do |

Giữ nguyên `max_worker_processes` và `timescaledb.max_background_workers`: job nền của TimescaleDB cần chúng.

Image đang chạy có `ENTRYPOINT=["docker-entrypoint.sh"] CMD=["postgres"]` (Claude đã kiểm bằng `docker image inspect`). Vì vậy `command: ["postgres", "-c", "shared_buffers=256MB", ...]` là dạng đúng, và entrypoint vẫn chạy.

Cập nhật đoạn §7 "Resource limits" của `DEPLOYMENT.md`, 2–4 câu: tham số bộ nhớ nằm ở `command:` của compose và phải đổi **cùng lúc** với `mem_limit`; kèm lý do (tune dò RAM máy, không dò giới hạn container).

### 1b. Chứng minh trên container NHÁP, không đụng postgres thật

- Container nháp `pgmem129`:
  - chạy **đúng image ID** của postgres thật (`docker inspect -f '{{.Image}}' ai_auto_trading_system-postgres-1`, hiện là `sha256:51ac20ec…`, TimescaleDB 2.27.2);
  - `--memory 1g --cpus 1`;
  - volume riêng `pgmem129-data`;
  - **không** publish cổng ra `5432`.
- **Dữ liệu:** chép **toàn bộ** `bars_daily` (khoảng 3 triệu dòng) vào nháp, với bảng hypertable 7 ngày như DB thật. Chạy đường ống **bên trong** container nháp (`psql -h host.docker.internal -p 5432 ... COPY ... TO STDOUT | psql ... COPY ... FROM STDIN`), **không** qua đường ống PowerShell. Bên DB thật chỉ là **đọc**. Nếu `host.docker.internal:5432` không vào được (postgres thật chỉ bind `127.0.0.1`), dùng dự phòng: `COPY ... TO STDOUT` bằng `docker compose exec -T postgres psql ...` ghi vào file **trong** container postgres thật (`/tmp`), rồi `docker cp` sang nháp, rồi **xoá file đó** trong container thật. **Không** nối `pgmem129` vào mạng của stack thật.
- **Hai lượt, cùng dữ liệu, cùng khối việc:**
  - **Lượt CŨ:** `-c` với **đúng** giá trị hiện tại của DB thật (lấy từ `pg_settings`: `shared_buffers`, `maintenance_work_mem`, `effective_cache_size`, `work_mem`, `max_parallel_workers_per_gather`, `max_parallel_maintenance_workers`).
  - **Lượt MỚI:** các giá trị ở 1a.
  - Mỗi lượt khởi động lại container, để cgroup đếm từ 0.
- **Khối việc** (giống việc thật sắp tới):
  1. quét toàn bảng 3 lần: `SELECT symbol, count(*), avg(close) FROM bars_daily GROUP BY symbol`;
  2. `CREATE INDEX` trên `(symbol, ts)` rồi `DROP` nó;
  3. `scripts/merge_bars_daily_chunks.py --dsn <nháp> --apply` (**chính** việc thứ Bảy);
  4. Q1 và Q2 của đợt 128, mỗi truy vấn 3 lần.
- **Ghi cho mỗi lượt:** `memory.peak`, `memory.events` (`max`, `oom`, `oom_kill`), `shmem` và `anon` trong `memory.stat`, trạng thái `OOMKilled`/`RestartCount`, mọi dòng log postgres có `out of memory|could not resize shared memory|terminated by signal`, và thời gian từng bước.

### 1c. Cổng (đăng ký trước)

| Điều kiện | Ngưỡng cho lượt MỚI |
|---|---|
| `oom_kill` | **0** |
| `OOMKilled` | `false`, `RestartCount` 0 |
| `shmem` cuối khối việc | **≤ 300 MB** |
| log postgres | **không** có dòng nào khớp mẫu trên |
| `merge_bars_daily_chunks.py --apply` | xong, số dòng và checksum trước = sau |
| thời gian mỗi bước | ghi lại; **không** là cổng, nhưng chậm hơn lượt CŨ quá 3 lần thì báo |

Lượt CŨ **không có cổng**: nó là số đo đối chứng. Nó hỏng thì ghi nguyên văn cách hỏng; nó không hỏng thì ghi `shmem`/`memory.events` để so. **Không** chạy lại để chọn lần đẹp.

**Dọn:** `docker rm -f pgmem129`, `docker volume rm pgmem129-data`, và kiểm cả hai đã hết.

---

## §2. Việc 2 — hook pre-push kiểm đúng commit được push

Viết lại `.githooks/pre-push` để ruff và pytest chạy trên **đúng `_local_sha`**:
1. Bỏ qua ref không phải `refs/heads/main` (như cũ), và bỏ qua `_local_sha` toàn số 0 (xoá nhánh).
2. `git worktree add --detach "$tmp" "$_local_sha"` vào thư mục tạm **ngoài repo**. `trap` phải xoá worktree (`git worktree remove --force`) cả khi thành công, cả khi thất bại, cả khi bị ngắt.
3. Trong worktree: `uv sync --frozen --extra dev`, rồi ruff và pytest **giữ nguyên** logic hiện tại (nats-test có thì chạy toàn bộ, không có thì bỏ integration và in cảnh báo).
4. Mọi lệnh con đọc stdin phải `< /dev/null`. Vòng `while read` đang đọc danh sách ref từ stdin, và một lệnh con nuốt stdin sẽ làm hook bỏ sót ref.
5. **Giữ nguyên:** thông điệp tiếng Việt không dấu, mã thoát, và dòng `--no-verify` trong chú thích đầu file. Giữ `#!/bin/sh`, POSIX; hook chạy bằng Git Bash trên Windows **và** bash trên Linux.

**Cổng.** Dùng một repo **nháp**: `git clone` repo này vào thư mục tạm, đặt `core.hooksPath`, và remote là một bare repo tạm. **Không** push lên GitHub.

| Tình huống | Phải thấy |
|---|---|
| T1: commit sạch | push qua; worktree tạm đã bị xoá |
| T2: **xanh giả cũ**: commit chứa lỗi ruff, working tree đã sửa nhưng **chưa `git add`** | push **bị chặn** (hook cũ cho qua; chạy cả hook cũ để chứng minh) |
| T3: **đỏ giả cũ**: commit sạch, working tree có file **chưa theo dõi** bị lỗi ruff | push **qua** (hook cũ chặn; chạy cả hook cũ để chứng minh) |
| T4: test đỏ trong commit | push bị chặn, worktree vẫn bị xoá |
| T5: ngắt giữa chừng (`kill` tiến trình hook) | không còn worktree nào mồ côi (`git worktree list`) |

Dán **nguyên văn** đầu ra của cả năm tình huống, cho cả hook cũ lẫn hook mới ở T2 và T3.

---

## §3. Tiêu chí chung

```
uv run pytest -q   (TOÀN BỘ, nats-test chạy)        → ≥ 1.426 passed, 0 failed
uv run ruff check trading tests scripts             → sạch
uv run pytest tests/test_deployment_doc.py           → xanh
docker compose config -q                             → không lỗi (compose hợp lệ)
bash -n .githooks/pre-push                           → sạch
git ls-files -s .githooks/pre-push                   → vẫn 100755
```

GitNexus (CLI, `--repo AI_auto_trading_system`): `detect-changes` ở cuối. Không đổi symbol Python nào; nếu phải đổi, chạy `impact` trước.

## §4. Phạm vi

**Được sửa:** `docker-compose.yml` (**chỉ** thêm `command:` cho `postgres`); `DEPLOYMENT.md` (**chỉ** §7); `.githooks/pre-push`; báo cáo `docs/superpowers/research/2026-09-29-dot-129-bo-nho-postgres-va-hook.md`.

**KHÔNG được đụng:** postgres thật và mọi container đang chạy (**không** `docker compose up`/`restart`/`down` trên stack thật; Claude áp); volume `pgdata`; `postgresql.conf`/`ALTER SYSTEM`; `trading/`, `scripts/`, `tests/`; `mem_limit`/`cpus` (giữ 1g/1.0; đổi giới hạn là quyết định khác).

## §5. Điều cấm

- **Không commit, không push** (trừ push vào bare repo **nháp** ở §2).
- Không đọc `.env` thật. Mật khẩu DB đọc được qua `resolve_dsn` như các script khác; **không in nó ra**.
- Không kết nối SSI, không gửi Telegram, không đặt lệnh, không `--send`.
- Cấm `git checkout`, `git restore`, `git stash` trên repo thật (`git worktree` và `git stash create` được phép).
- Đợt 128 **chưa** được chạy trên DB thật. **Không** chạy `merge_bars_daily_chunks.py` với DSN của DB `trading`, kể cả dry-run có cờ.

## §6. Báo cáo phải có

1. Diff của cả ba file.
2. §1b: bảng số đo của hai lượt, **nguyên văn** `memory.events`/`memory.stat`, log postgres, thời gian từng bước. Kết quả gộp chunk (số dòng, checksum).
3. §2: đầu ra nguyên văn T1–T5, cả hook cũ lẫn hook mới ở T2 và T3.
4. Thời gian chạy của hook mới so với hook cũ trên máy này.
5. Chỗ nào brief sai hoặc mơ hồ. **Nếu brief đảo một quyết định có chủ ý nào** (đọc chú thích quanh dòng định sửa, nhất là trong `docker-compose.yml` và `.githooks/pre-push`), **báo ngay**.

---

## §7. Việc của Claude sau audit

1. **Áp việc 1 lên stack thật trước thứ Bảy**, lý tưởng là tối nay sau 21:05 (sau `daily-check`): `docker compose up -d postgres`. Kiểm `SHOW shared_buffers`, rồi kiểm collector ghi NAV lại bình thường, engine không lỗi. Bắt buộc làm xong **trước** phép gộp chunk thứ Bảy.
2. Theo dõi `memory.events`/`shmem` của postgres thật trong một phiên.
3. Push hook mới, và dùng nó ngay cho chính commit đó.
