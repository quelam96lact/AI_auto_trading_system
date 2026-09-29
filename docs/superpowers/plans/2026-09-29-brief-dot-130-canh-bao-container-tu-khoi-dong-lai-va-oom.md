# Brief đợt 130 — cảnh báo khi container tự khởi động lại hoặc bị kill vì hết bộ nhớ

**Base commit:** `8d413fc`.
**Người thực thi:** agent. **Người audit, nối vào lịch chạy, commit, push:** Claude.
**Chạy SONG SONG với đợt 129** (đợt 129 đang sửa `docker-compose.yml`, `DEPLOYMENT.md`, `.githooks/pre-push`). Xem §4 để không đụng nhau.

---

## §0. Bối cảnh

Đợt 129 phát hiện postgres có cấu hình bộ nhớ gấp đôi giới hạn container, và đã chạm trần 10.195 lần trong một ngày. Câu hỏi tiếp theo: **nếu một container bị kill, có ai biết không?** Claude đã kiểm, câu trả lời là **không**:

- `grep` toàn repo (`*.py`, `*.sh`): **không** có `RestartCount`, `OOMKilled`, `StartedAt`, hay `memory.events` ở đâu cả.
- Mọi service có `restart: unless-stopped`, nên container chết sẽ **tự lên lại sau vài giây**.
- `heartbeat_check.py` chỉ báo khi heartbeat im **quá 300 giây** (`DEFAULT_MAX_AGE_SECONDS`), nên một lần khởi động lại vài giây lọt qua. Trong vài giây đó, collector ghi DB hỏng; nến và NAV của khoảng đó có thể mất **im lặng**.
- **Kiểu hỏng khó thấy hơn:** trên cgroup v2, kernel có thể chỉ kill **một tiến trình con** của postgres. Postmaster sẽ tự khởi động lại mọi backend ngay **trong** container, nên container **không** khởi động lại và `RestartCount` **không** đổi. Dấu vết duy nhất là bộ đếm `oom_kill` trong `/sys/fs/cgroup/memory.events` của container.

Số đo của postgres thật lúc 17:40 hôm nay (mốc để agent đối chiếu): `memory.events: max 10195, oom 0, oom_kill 0`; `OOMKilled=false`, `RestartCount=0`.

---

## §1. Việc: `scripts/container_health_check.py`

### 1a. Đọc gì (chỉ ĐỌC, không bao giờ ghi vào container)

Với mỗi service `postgres`, `collector`, `engine`, `nats`, `grafana` (**không** gồm `nats-test`):
- Tên container: dùng `get_container_name(service)` import từ `scripts/deploy_drift_check.py`, **đúng khuôn** `stream_health_check.py` đang làm. **Không** viết quy tắc suy tên thứ ba.
- `docker inspect -f ...` lấy `Id`, `RestartCount`, `State.Status`, `State.OOMKilled`, `State.StartedAt`.
- `docker exec <container> cat /sys/fs/cgroup/memory.events` lấy `oom_kill` và `max`. Nếu file không đọc được (cgroup v1, hoặc image không có `cat`), ghi rõ "không đọc được" cho service đó. **Không** được coi là 0.
- Mọi `subprocess.run` có `timeout=30`, như `deploy_drift_check.py:96–137`.

### 1b. Quy tắc cảnh báo (hàm THUẦN, test được không cần Docker)

So với **trạng thái lần trước**, lưu theo từng service: `Id`, `RestartCount`, `oom_kill`.

| Tình huống | Hành động |
|---|---|
| Lần chạy đầu (chưa có trạng thái) | ghi mốc, **không** cảnh báo |
| `Id` đổi (container được **tạo lại**, ví dụ triển khai theo §10) | ghi mốc mới, **không** cảnh báo, nhưng in một dòng thông tin |
| Cùng `Id`, `RestartCount` **tăng** | **CRITICAL**: container tự khởi động lại N lần (crash) |
| `State.OOMKilled == true` | **CRITICAL** |
| Cùng `Id`, `oom_kill` **tăng** | **CRITICAL**: kernel kill tiến trình trong container vì hết bộ nhớ (kiểu postgres ở §0) |
| `State.Status != "running"` | **CRITICAL** |
| `memory.events max` tăng | **chỉ in ra log**, KHÔNG cảnh báo. Postgres đang chạm trần liên tục cho tới khi đợt 129 được áp; cảnh báo ở đây là spam |
| `docker` không chạy hoặc hết `timeout` | **không** cảnh báo ở đây: cổng `run_if_docker_up.sh` và `docker_down_alert.py` đã lo. Thoát 2 và ghi rõ lý do |

**Trạng thái chỉ được cập nhật SAU KHI cảnh báo đã gửi thành công.** Gửi hỏng thì giữ trạng thái cũ, để lần chạy sau **báo lại**. Đây là cùng nguyên tắc với stamp của `docker_down_alert.py`, nơi stamp không được ghi khi gửi thất bại. Một lần gửi Telegram gộp mọi cảnh báo của lần chạy đó.

### 1c. Quy ước chung — theo code sẵn có

- Gửi bằng `trading.telegram.send_telegram`, in bằng `trading.alerts._print_safe`, như `heartbeat_check.py`.
- **Mã thoát như `heartbeat_check.py`:** 0 = ổn; 1 = có cảnh báo và đã gửi; 2 = sai cấu hình, không đọc được docker, hoặc **cảnh báo cần gửi mà gửi hỏng** (nguyên tắc đợt 126).
- **Không bao giờ ném ngoại lệ ra ngoài** (FEE-ALARM-2: chuông chết câm tệ hơn không có chuông). Có lỗi thì in dấu vết, trả 2.
- File trạng thái (JSON) đặt **cạnh** file stamp của `docker_down_alert.py`; đọc `SPAM_GUARD_FILE` ở đó để theo đúng thư mục. File hỏng hoặc không đọc được thì coi như lần chạy đầu và **in rõ** điều đó.
- Cờ `--dry-run`: in cảnh báo **thay vì gửi Telegram**. `--dry-run` **bắt buộc** đi kèm `--state-file <đường dẫn>`, và thiếu thì thoát 2. Nhờ vậy phép thử luôn ghi và đọc trạng thái ở file tạm, **không bao giờ** đụng file trạng thái thật.
- Cờ `--containers a,b`: kiểm danh sách tên container **cho sẵn** thay cho 5 service, dùng cho phép thử §2b. Mặc định là 5 service.
- **Không** import gì có side effect khi import. Nếu import từ `trading/engine/main.py` như `heartbeat_check.py:36`, đọc chú thích LEDGER-1 ở đó trước.

GitNexus: `npx gitnexus impact get_container_name --repo AI_auto_trading_system` trước khi import nó (chỉ import, **không** sửa).

---

## §2. Cổng

### 2a. Test đơn vị: `tests/test_container_health_check.py`

Mỗi dòng của bảng 1b có ít nhất một test, dùng trạng thái giả và kết quả `inspect` giả, không gọi Docker thật. Thêm:
- gửi hỏng → mã 2, **và file trạng thái không đổi**;
- file trạng thái hỏng → coi như lần đầu, không ném lỗi;
- `memory.events` không đọc được → báo "không đọc được", **không** coi là 0.

**Phá thử**, dán nguyên văn thông điệp đỏ, rồi phục hồi và kiểm `git diff` rỗng:
- P1: bỏ nhánh `oom_kill` tăng → test tương ứng phải đỏ.
- P2: cập nhật trạng thái **trước** khi gửi → test "gửi hỏng" phải đỏ.
- P3: coi "đổi `Id`" là crash → test "tạo lại" phải đỏ.

### 2b. Đối chứng DƯƠNG TÍNH với container thật — NHÁP, không đụng stack

Không có cách nào chứng minh bắt được OOM thật trừ việc **gây ra** một lần OOM thật. Làm trên container nháp:

```
docker run -d --name cht130 --memory 32m --memory-swap 32m --restart on-failure \
  python:3.12-slim python -c "b=[]; import time; time.sleep(20); [b.append(bytearray(8<<20)) for _ in range(100)]"
```

(Chờ 20 giây để kịp ghi mốc, rồi ăn bộ nhớ đến khi bị kill; `on-failure` khiến nó tự khởi động lại.)

1. Ngay sau khi chạy (trong 20 giây chờ): `container_health_check.py --containers cht130 --dry-run --state-file <tạm>/cht130.json` **không** in cảnh báo (lần đầu), và file tạm có mốc.
2. Chờ tới khi `docker inspect -f '{{.RestartCount}}' cht130` ≥ 1.
3. Chạy lại → phải in **CRITICAL** cho `RestartCount` tăng, và cho `OOMKilled` hoặc `oom_kill` (ghi rõ cái nào xuất hiện).
4. **Đối chứng âm tính:** `docker rm -f cht130`, rồi chạy lại **một** container cùng tên nhưng không ăn bộ nhớ (`sleep 600`). `Id` đổi nên phải **không** cảnh báo (tình huống "tạo lại").
5. Dọn: `docker rm -f cht130`; kiểm `docker ps -a --filter name=cht130` rỗng.

Nếu cgroup trên Docker Desktop không cho `oom_kill` tăng trong container bị kill cả cụm, ghi nguyên văn `memory.events` và `docker inspect` thấy được. **Không** bịa.

### 2c. Chạy CHỈ ĐỌC trên stack thật

`uv run python scripts/container_health_check.py --dry-run --state-file <tạm>/stack.json`, hai lần liên tiếp. Lần 1 ghi mốc, lần 2 không có cảnh báo. Dán nguyên văn cả hai, gồm dòng in `memory.events max` của postgres. Chỉ `docker inspect` và `docker exec ... cat` là đọc; **không** lệnh nào khác chạm container thật.

### 2d. Chung

```
uv run pytest -q   (TOÀN BỘ, nats-test chạy)     → ≥ 1.426 passed + test mới, 0 failed
uv run ruff check trading tests scripts          → sạch
```

`npx gitnexus detect-changes --repo AI_auto_trading_system` ở cuối.

---

## §3. Việc của Claude sau audit (agent KHÔNG làm)

Sau khi **cả** đợt 129 và 130 xong (để hai agent không cùng sửa `DEPLOYMENT.md`):
1. Thêm case `container-health` vào `scripts/sched.sh` (qua `run_if_docker_up.sh`, như các job khác).
2. Thêm dòng cron vào khối §9 của `DEPLOYMENT.md`. Đề xuất `*/10 * * * *`, tức **24/7**, để bắt được cả khung đêm 22:00–01:30 và cuối tuần. `test_deployment_doc.py` bắt buộc hai chỗ này khớp nhau.
3. Nhờ chủ dự án tạo scheduled task trên Windows cho job mới (tạo scheduled task là việc của chủ dự án).

## §4. Phạm vi

**Được tạo:** `scripts/container_health_check.py`, `tests/test_container_health_check.py`, báo cáo `docs/superpowers/research/2026-09-29-dot-130-canh-bao-container.md`.

**KHÔNG được đụng:** `docker-compose.yml`, `DEPLOYMENT.md`, `.githooks/` (đợt 129 đang sửa); `scripts/sched.sh` (Claude nối sau); `scripts/deploy_drift_check.py` (chỉ import); `trading/`; mọi test có sẵn; mọi container của stack thật (chỉ `inspect` và `exec ... cat`).

## §5. Điều cấm

- **Không commit, không push.** Không restart, stop, rebuild container thật nào.
- Không ghi file trạng thái **thật** trong lúc thử: mọi lần chạy đều `--dry-run --state-file <tạm>`.
- Không gửi Telegram thật: mọi phép thử dùng `--dry-run` hoặc `send` giả.
- Không đọc `.env` thật; không in bí mật.
- Không đặt lệnh, không `--send`, không bật `real_trading_enabled`.
- Cấm `git checkout`, `git restore`, `git stash` (trừ `git stash create`).
- Không tạo scheduled task.

## §6. Báo cáo phải có

1. Diff hai file mới; output `gitnexus impact` và `detect-changes`.
2. Bảng test ↔ dòng của bảng 1b; bảng phá thử P1–P3 với thông điệp đỏ **nguyên văn**.
3. §2b: **nguyên văn** mọi lệnh và đầu ra, gồm `docker inspect` và `memory.events` của `cht130` trước và sau khi bị kill.
4. §2c: đầu ra nguyên văn hai lần chạy trên stack thật.
5. Chỗ nào brief sai hoặc mơ hồ. **Nếu brief đảo một quyết định có chủ ý nào** (đọc chú thích trong `heartbeat_check.py`, `docker_down_alert.py`, `deploy_drift_check.py`), **báo ngay**.
