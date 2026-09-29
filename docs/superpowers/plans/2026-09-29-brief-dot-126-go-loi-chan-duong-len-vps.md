# Brief đợt 126 — gỡ các lỗi chặn đường lên VPS mà diễn tập đợt 125 tìm ra

**Base commit:** `59a88be`.
**Người thực thi:** agent. **Người audit + commit + push:** Claude.

---

## §0. Bối cảnh

Đợt 125 diễn tập `DEPLOYMENT.md` trong `ubuntu:24.04` sạch, và Claude audit. Đã vá: gói `docker-compose-v2`, **cờ thực thi trong git** cho 5 script (trước đó `100644`, nên trên VPS cả chín cron job sẽ chết), dòng cron `backfill` lặp, và CI chạy ma trận 3.11 + 3.12 (cả ba job xanh ở `59a88be`).

Còn lại năm việc. **Mỗi việc là một cách hệ thống trên VPS hỏng mà không ai biết.** Đợt này gỡ chúng.

| # | Việc | Hậu quả nếu không làm |
|---|---|---|
| 1 | `stream_health_check.py` viết cứng tên container | job cron `stream-health` hỏng **mỗi ngày** trên VPS |
| 2 | Cài thiếu `.env` hoặc thiếu token Telegram thì mọi job **im lặng** | một VPS cài dở sẽ không bao giờ kêu |
| 3 | `.env` chép từ Windows sang là CRLF | mọi giá trị, kể cả token, dính `\r` |
| 4 | `logs/` bị tạo lại với `root:root` | container mất log **im lặng** |
| 5 | CI chạy `ubuntu-latest`, sẽ thành Ubuntu 26 từ 19/10/2026 | CI kiểm hệ điều hành khác VPS (24.04) |

Làm theo thứ tự. Mỗi việc có cổng riêng; một việc kẹt thì báo lại và làm tiếp việc sau.

---

## §1. Việc 1 — tên container viết cứng

**Hiện trạng.** `scripts/stream_health_check.py:155` chạy `docker logs -t ai_auto_trading_system-collector-1`. Đây là job cron `stream-health` (`sched.sh:78`). `docker compose` đặt tên container theo **tên thư mục** chứa `docker-compose.yml`. Trên VPS, `DEPLOYMENT.md` clone vào `/opt/trading`, nên container sẽ tên là **`trading-collector-1`**.

Hai chỗ khác **đã** làm đúng, suy tên từ `COMPOSE_PROJECT_NAME` hoặc tên thư mục:
- `scripts/deploy_drift_check.py::get_container_name()`, được `check_golive_gate.py:138` import;
- `scripts/run_if_docker_up.sh:83`. Đây là **bản sao có chủ ý** (chú thích dòng 77–82: cổng Docker phải chạy được cả khi Python hỏng). **Không gộp nó.**

**Việc:**
- `stream_health_check.py` dùng `get_container_name("collector")` import từ `deploy_drift_check`, **đúng khuôn** `check_golive_gate.py` đang làm.
- `scripts/measure_session_stream_metrics.py:75` (script đo tay): sửa cùng cách.
- `tests/test_deploy_drift_check.py::test_get_container_name_default_repo_basename` (dòng 96) đỏ khi repo nằm ở thư mục tên khác (diễn tập 125 ra đỏ trên `/opt/trading`). Sửa test để **tính** giá trị mong đợi từ tên thư mục repo theo **đúng** quy tắc chuẩn hoá của hàm, thay vì viết cứng `ai_auto_trading_system`. **Không** sửa hàm.

**Cổng:**
- Test mới cho `stream_health_check`: với `COMPOSE_PROJECT_NAME=trading`, lệnh `docker logs` được gọi với `trading-collector-1` (giả lập `subprocess`, không gọi Docker thật).
- Chạy test đã sửa với repo đặt ở thư mục tên khác (ví dụ trong container diễn tập, xem §6): phải xanh.
- Phá thử 1: đưa lại tên viết cứng, test mới phải đỏ.

---

## §2. Việc 2 — cài thiếu thì phải KÊU, không được im

### 2a. Thiếu `.env`

`run_if_docker_up.sh:51–53`: không có `.env` thì ghi `SKIP: khong tim thay .env` và **`exit 0`**. Trên một VPS vừa clone mà quên chép `.env`, cả chín job cứ thế bỏ qua, và mọi dấu hiệu đều là "thành công".

Không thể gửi Telegram (token nằm trong chính `.env`). Nên phải làm **ồn bằng mọi đường còn lại**:
- ghi dòng SKIP như cũ **và** in cùng nội dung ra **stderr** (cron gửi mail cho stderr nếu có `MAILTO`; systemd/journal cũng thấy);
- **thoát khác 0** (dùng `2`), để cron và Task Scheduler ghi nhận là lỗi.

### 2b. `docker_down_alert.py` trả 0 cả khi không gửi được

`run_alert()` có docstring: *"KHÔNG BAO GIỜ nem — chuông báo chết câm còn tệ hơn không có chuông báo (FEE-ALARM-2). Trả 0 luôn."* **Giữ nguyên nguyên tắc "không bao giờ ném"**: nó đúng, và là quyết định có chủ ý.

Nhưng **"không ném" khác "luôn trả 0"**. Trả mã khác 0 không làm chết gì cả: `run_if_docker_up.sh:97` chỉ ghi nó vào dòng `ALERT_EXIT=` rồi `exit 0`. Hiện dòng đó luôn là `ALERT_EXIT=0`, nên không phân biệt được "không cần kêu" với "cần kêu mà không kêu được".

**Việc:** tách ba trạng thái:

| Tình huống | Mã trả |
|---|---|
| không cần kêu (ngoài giờ, ngày nghỉ, chống spam) | 0 |
| đã gửi thành công | 0 |
| **cần kêu nhưng gửi thất bại** (send trả `False` / `None` / ném lỗi, hoặc thiếu token) | **2** |

Lớp `except` ngoài cùng (lỗi không lường trước) cũng trả **2**, vì lúc đó không biết đã kêu hay chưa. **Vẫn không bao giờ ném.**

**Ba test hiện ghim `rc == 0` cho ca gửi thất bại** (`tests/test_docker_down_alert.py` dòng 61–62, 73–74, 93–94). Đổi chúng thành `rc == 2`, **kèm chú thích dẫn brief đợt 126 và lý do** ở trên. Mọi test khác của file giữ nguyên `rc == 0`. **Không sửa test nào khác để làm xanh.**

`run_if_docker_up.sh`: giữ `exit 0` ở nhánh Docker chết (hành vi cũ). Chỉ cần dòng `ALERT_EXIT=` nay có nghĩa.

### 2c. Runbook phải có bước chứng minh Telegram tới nơi

`DEPLOYMENT.md` **không có bước nào** xác nhận cảnh báo thực sự tới được điện thoại. `scripts/probe_dead_man_switch.py` làm đúng việc đó (gửi qua đúng code sản xuất `trading.alerts.alert()` / `send_telegram()`), nhưng hướng dẫn trong docstring **chỉ có PowerShell**.

**Việc (chỉ tài liệu):**
- Thêm vào `DEPLOYMENT.md` §11 (sau bước cài cron) một bước: nạp `.env` bằng bash rồi chạy `uv run python scripts/probe_dead_man_switch.py`, và **chủ dự án xác nhận đã nhận tin** trước khi coi việc chuyển máy là xong.
- Thêm hướng dẫn chạy bằng bash vào docstring của `probe_dead_man_switch.py`, bên cạnh hướng dẫn PowerShell có sẵn. **Không** đổi code của probe.
- **Agent không chạy probe**: nó gửi Telegram thật.

**Cổng việc 2:**
- Test: `run_if_docker_up.sh` với repo không có `.env` thì thoát 2 và có chữ `SKIP` trong **stderr** (chạy trong container diễn tập, §6).
- Test: `run_alert` trả 2 cho ba ca gửi thất bại, và trả 0 cho mọi ca còn lại.
- Phá thử 2: đổi lại `return 2` thành `return 0` ở ca gửi thất bại, test phải đỏ.

---

## §3. Việc 3 — `.env` chép từ Windows mang CRLF

`.env` **không nằm trong git**, nên `.gitattributes` không bảo vệ được nó. Khi chuyển máy, chủ dự án sẽ chép `.env` từ laptop Windows sang, và file đó là CRLF. `run_if_docker_up.sh:62` và `DEPLOYMENT.md` (dòng 296 ở §8.5, dòng 753 ở §11) nạp nó bằng `. ./.env`, nên mọi giá trị dính `\r` ở cuối, **kể cả token SSI và Telegram**. Bash in `$'\r': command not found` cho dòng trống, và các giá trị hỏng thì **không báo gì**.

**Việc:**
1. `run_if_docker_up.sh`: **trước** khi nạp, nếu `.env` chứa ký tự CR thì ghi rõ ra log **và** stderr, rồi thoát **2**. **Không** tự sửa file: đó là file bí mật của chủ dự án, không được sửa ngầm.
2. `DEPLOYMENT.md` §11, ngay sau bước chép `.env`: thêm `sed -i 's/\r$//' .env` kèm một câu giải thích vì sao.
3. **Tự kiểm, đừng đoán:** container của `docker compose` đọc `.env` qua `env_file`. Nó có tự bỏ `\r` không? Kiểm trên máy này bằng một thư mục tạm có `docker-compose.yml` tối thiểu (image `busybox`, lệnh `env`) và một `.env` CRLF **giả** (`FOO=bar`). **Không** dùng `.env` thật. Ghi kết quả vào báo cáo: nếu compose **không** bỏ `\r`, đó là rủi ro thứ hai, và bước `sed` ở trên càng bắt buộc.

**Cổng:** trong container diễn tập, `.env` giả dạng CRLF làm `run_if_docker_up.sh` thoát 2 kèm thông điệp rõ ràng; `.env` giả dạng LF thì đi tiếp bình thường.

---

## §4. Việc 4 — `logs/` bị tạo lại với `root:root`

`run_if_docker_up.sh:38` chạy `mkdir -p "$REPO/logs"`. Cron trên VPS chạy bằng root (`sudo crontab`), nên nếu `logs/` chưa có thì nó được tạo với chủ `root:root`. `DEPLOYMENT.md` §2 (quanh dòng 55) ghi rõ hậu quả: container (uid 10001) ghi log vào đó thì **nuốt `PermissionError` và chạy tiếp im lặng**, mất toàn bộ log chốt nến và cảnh báo engine.

**Việc:** nếu `logs/` **chưa tồn tại** và script đang chạy bằng root (`EUID=0`), thì tạo nó **và** `chown 10001:10001`, đúng như `DEPLOYMENT.md` §2. Nếu không phải root thì giữ `mkdir -p` như cũ. **Không** đổi quyền của một `logs/` **đã có sẵn**.

**Cổng:** trong container diễn tập, chạy bằng root khi chưa có `logs/`: sau khi chạy, `stat -c '%u:%g' logs` ra `10001:10001`. Phá thử 3: bỏ lệnh `chown`, phép kiểm này phải hỏng.

---

## §5. Việc 5 — ghim hệ điều hành của CI

CI in cảnh báo: *"The ubuntu-latest label will migrate to Ubuntu 26 beginning October 19, 2026."* VPS nhắm **Ubuntu 24.04** (`DEPLOYMENT.md` §1). **Việc:** đổi `runs-on: ubuntu-latest` thành `runs-on: ubuntu-24.04` ở **cả hai** job trong `.github/workflows/ci.yml`, kèm một dòng chú thích lý do. Không đổi gì khác. Claude kiểm CI thật sau khi push.

---

## §6. Môi trường kiểm cho việc 1–4

Dùng lại cách của đợt 125: container `ubuntu:24.04` `--rm`, mã nguồn lấy bằng `git archive`.

**Bài học của đợt 125, phải tránh:**
- Đợt 125 chạy bộ test trên `git archive HEAD`, tức **trước** khi sửa tài liệu, nên phần sửa `DEPLOYMENT.md` chưa từng qua test. Hook pre-push của Claude chặn lại vì `test_deployment_doc.py` đỏ (regex bắt chữ "v" của "và" như một tên job). **Lần này, đưa bản working tree ĐÃ SỬA vào container**, ví dụ `git stash create` rồi `git archive <sha>`, hoặc chép các file đã sửa đè lên. **Cấm `git stash` dạng lưu/đổi working tree**; `git stash create` chỉ tạo commit tạm và **không** đụng working tree, được phép.
- `git archive` chạy trên Windows áp `core.autocrlf` vào đầu ra (đợt 125 báo nhầm `.env.example` là CRLF vì việc này). Với file **không** có thuộc tính `eol=lf`, đừng kết luận CRLF từ bản archive; kiểm bằng `git ls-files --eol`.
- Chạy `bash` trong container bằng file mount (`-v file:/t.sh`), **không** qua đường ống PowerShell: đường ống thêm CRLF vào script.

**An toàn, như đợt 125:** không `.env` thật, không bí mật, không Docker socket trong container, không SSI, không Telegram. Kiểm `docker compose` ở việc 3 chạy trên máy này nhưng trong **thư mục tạm riêng**, với project name riêng, **không** chạm stack `ai_auto_trading_system`.

---

## §7. Tiêu chí chung

```
uv run pytest -q   (TOÀN BỘ, gồm integration; nats-test đang chạy)   → ≥ 1.419 passed + test mới, 0 failed
uv run ruff check trading tests scripts                              → sạch
bash -n cho mọi *.sh đã sửa                                          → sạch
uv run pytest tests/test_deployment_doc.py                            → xanh (đợt 125 đã vấp ở đây)
Toàn bộ suite -m "not integration" trong container, repo ở /opt/trading → 0 failed
```

`gitnexus impact` cho `get_container_name`, `run_alert`, và `detect-changes` (CLI, `--repo AI_auto_trading_system`).

---

## §8. Phạm vi

**Được sửa:** `scripts/stream_health_check.py`, `scripts/measure_session_stream_metrics.py`, `scripts/docker_down_alert.py`, `scripts/run_if_docker_up.sh`, `scripts/probe_dead_man_switch.py` (**chỉ** docstring), `.github/workflows/ci.yml` (**chỉ** `runs-on`), `DEPLOYMENT.md` (**chỉ** §11 cho việc 2c và 3), các test liên quan.

**KHÔNG được đụng:** `trading/`; `scripts/sched.sh`; `scripts/deploy_drift_check.py` (chỉ được import từ nó); quy tắc tên container trong `run_if_docker_up.sh:77–85` (bản sao có chủ ý); `docker-compose.yml`, `Dockerfile`; `.env` thật; mọi container đang chạy.

## §9. Điều cấm

- **Không commit, không push.** Không rebuild, không restart stack.
- **Không đọc, không chép, không sửa `.env` thật.** Mọi phép kiểm `.env` dùng file giả.
- **Không chạy `probe_dead_man_switch.py`**, không gửi Telegram, không kết nối SSI.
- Không đặt, sửa, huỷ lệnh; không bật `real_trading_enabled`; không chạy `--send`.
- Cấm `git checkout`, `git restore`, và `git stash` dạng lưu/đổi working tree (`git stash create` được phép, xem §6).
- Không tạo, sửa, xoá scheduled task của Windows.

## §10. Báo cáo phải có

1. Với mỗi việc 1–5: diff, output cổng nguyên văn, và bảng phá thử với thông điệp lỗi thật.
2. Kết quả thí nghiệm `env_file` CRLF của việc 3.
3. Những gì **không** kiểm được, và vì sao.
4. Chỗ nào brief sai hoặc mơ hồ. Brief của Claude đã sai ở đợt 125 (đảo ngược quyết định `ci.yml` 3.11 mà không đọc chú thích); nếu brief này đảo một quyết định có chủ ý nào khác, **báo ngay**.
