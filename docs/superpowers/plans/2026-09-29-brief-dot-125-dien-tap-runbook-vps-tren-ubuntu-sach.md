# Brief đợt 125 — diễn tập runbook lên VPS trên một Ubuntu sạch, và cho CI kiểm đúng phiên bản Python chạy thật

**Base commit:** `17ff44b`.
**Người thực thi:** agent. **Người audit + commit + push:** Claude.

---

## §0. Vì sao làm việc này bây giờ

Chủ dự án đã chốt (29/09): hệ thống chạy thật sẽ ở **VPS Ubuntu 24/7**, laptop Windows chỉ là tạm. `DEPLOYMENT.md` đã có hướng dẫn đầy đủ: cài đặt (§1–§2), tường lửa, backup, 9 cron job (§9), và runbook chuyển máy 10 bước (§11, cập nhật ở đợt 110). Nhưng runbook đó được viết và sửa dần **trên Windows**, và **chưa từng được chạy từ đầu tới cuối trên một máy Linux sạch**. Runbook chưa từng chạy thật thường hỏng đúng vào ngày cần nó.

Claude đã kiểm trước những gì kiểm được mà không cần chạy:

| Kiểm (29/09) | Kết quả |
|---|---|
| Mọi script mà `sched.sh` gọi tới có được git theo dõi | **có**: 11/11 |
| Ký tự xuống dòng của `*.sh` và hook | `.gitattributes` ép `eol=lf`, nên bản clone trên Linux không dính CRLF |
| Chín job trong `sched.sh` với chín dòng cron ở `DEPLOYMENT.md` §9 | khớp |
| `scripts/probe_dead_man_switch.py` (đợt 58 ghi "cần trên VPS") | đã được đổi tên và theo dõi |
| CI trên GitHub | chạy trên `ubuntu-latest`, cả job unit lẫn integration, **xanh liên tục** |

Còn lại hai khoảng trống thật, cũng là hai phần của đợt này.

---

## §1. Phần A — CI kiểm đúng phiên bản Python chạy thật

| Nơi | Python |
|---|---|
| Container production (`Dockerfile`: `FROM python:3.12-slim`, cả hai stage) | **3.12** |
| Host VPS (`DEPLOYMENT.md` §2: `uv sync --python 3.12`, kèm chú thích vì sao phải ghim) | **3.12** |
| CI (`.github/workflows/ci.yml`, **cả hai job**) | 3.11 |
| Máy dev (`.venv`) | 3.11.15 |
| `pyproject.toml` | `requires-python = ">=3.11"` |

Tức là **không nơi nào chạy test trên đúng phiên bản production**.

**Việc:** đổi `python-version` của **cả hai** job trong `ci.yml` sang `"3.12"`. Không đổi gì khác trong `ci.yml`. **Không** đổi `pyproject.toml` và **không** đụng `.venv` của máy dev: máy dev chạy 3.11 qua pre-push, CI chạy 3.12, nên cả hai phiên bản đều được phủ.

**Cổng:** agent không push, nên không tự chạy được CI. Thay vào đó, chạy bộ unit test trên Python 3.12 ở Phần B (bước B.6) là bằng chứng. Claude kiểm CI thật sau khi push.

---

## §2. Phần B — diễn tập runbook trong container `ubuntu:24.04` sạch

### B.0. Nguyên tắc an toàn — đọc trước

- **Không** đưa `.env` hay bất kỳ bí mật nào vào container. **Không** đặt biến `SSI_*`, `TELEGRAM_*`. Mọi bước cần bí mật thì **ghi nhận là "cần bí mật, bỏ qua"**, không tìm cách lách.
- **Không** mount Docker socket, **không** khởi động stack (`docker compose up`), **không** chạm container `ai_auto_trading_system-*` đang chạy thật trên máy này.
- **Không** kết nối SSI hay Telegram. Mạng chỉ dùng cho `apt`, trình cài `uv` và PyPI.
- Container dùng xong thì bỏ (`--rm`).

### B.1. Lấy mã nguồn đúng như một bản clone sạch

Dùng `git archive HEAD` (sau khi Phần A xong thì dùng thêm bản working tree có sửa `ci.yml`, không quan trọng với Phần B), rồi giải nén vào `/opt/trading` trong container.

**Vì sao không mount thư mục repo vào:** bản mount mang theo mọi file chưa được theo dõi, bị gitignore, và `.venv` Windows. Đó chính là loại file che mất lỗi "trên laptop chạy vì file nằm sẵn trên đĩa". `git archive` chỉ có đúng những gì `git clone` trên VPS sẽ có.

### B.2. Chạy runbook ĐÚNG NGUYÊN VĂN

Làm theo `DEPLOYMENT.md` theo thứ tự, **chép lệnh y như tài liệu**, chỉ thay những gì bắt buộc (không có `sudo` vì đang là root trong container; không có systemd):

| Bước | Mục | Ghi chú cho diễn tập |
|---|---|---|
| B.2.1 | §1 múi giờ | làm đúng như tài liệu; kiểm `date` ra giờ VN |
| B.2.2 | §1 cài gói | cài **mọi** gói tài liệu liệt kê. Riêng Docker engine thì **cài theo tài liệu nhưng không khởi động daemon**; ghi nhận |
| B.2.3 | §1 cài `uv` vào `/usr/local/bin` | đúng lệnh trong tài liệu |
| B.2.4 | §2 `uv sync --python 3.12 ...` | đúng lệnh và cờ trong tài liệu |
| B.2.5 | §2 tạo `logs/`, `data/orderbook/`, phân quyền (uid 10001, 775) | đúng lệnh |
| B.2.6 | §6 dòng cron backup + backup sổ lệnh | cài vào crontab; `bash -n scripts/backup_db.sh` |
| B.2.7 | §8 cấu hình logrotate | tạo file đúng như tài liệu; chạy `logrotate -d <file>` (chế độ debug, không xoay thật) |
| B.2.8 | §9 khối cron (có `CRON_TZ`) | cài đúng khối vào crontab; `crontab -l` phải ra đủ 9 dòng `sched.sh` |
| B.2.9 | §9.5 dòng cron backfill | xem §B.5 mục 1 |

Với **mỗi** bước, ghi: lệnh đã chạy (nguyên văn), exit code, vài dòng output quan trọng, và kết luận **CHẠY ĐƯỢC** / **HỎNG** / **PHẢI LỆCH TÀI LIỆU** (nêu rõ lệch gì, vì sao).

### B.3. Kiểm tĩnh sau khi cài

1. `bash -n` cho **mọi** file `*.sh` và `.githooks/pre-push`.
2. Với **mỗi** dòng cron đã cài: tên job sau `sched.sh` phải có trong `case` của `scripts/sched.sh`, và mọi đường dẫn trong dòng đó phải tồn tại trong `/opt/trading`.
3. Mọi đường dẫn file mà `sched.sh` và `run_if_docker_up.sh` tham chiếu phải tồn tại.

### B.4. Kiểm đường lỗi — khi không có Docker và không có bí mật

Trong container, chạy `scripts/sched.sh heartbeat` (hoặc `sched.sh backfill`). Không có Docker daemon, nên `run_if_docker_up.sh` phải đi nhánh `SKIP: docker chua chay` và **cố gửi cảnh báo**. Không có token Telegram, nên việc gửi phải **thất bại**. Câu hỏi cần trả lời: nó thất bại **ồn** hay **im**?

- Exit code của `sched.sh` là bao nhiêu?
- Dòng `SKIP` và dòng `ALERT_EXIT=` có được ghi vào đúng file log không?
- `ALERT_EXIT` là 0 hay khác 0 khi **không thể** gửi cảnh báo?

Nếu `ALERT_EXIT=0` mà cảnh báo không hề được gửi, đó là một phát hiện quan trọng: trên VPS, một bản cài thiếu token Telegram sẽ **im lặng** bỏ mọi job. **Báo lại, không sửa code**: sửa `run_if_docker_up.sh` là việc của đợt sau.

### B.5. Hai điểm Claude đã thấy trước, bạn kiểm bằng diễn tập

1. **Dòng cron `backfill` bị lặp.** §9 (dòng 353) có `30 20 * * 1-5 cd /opt/trading && scripts/sched.sh backfill`, và §9.5 (dòng 467) có thêm `30 20 * * 1-5 /opt/trading/scripts/sched.sh backfill` (không `cd`). Việc thiếu `cd` **vô hại**: `sched.sh` tự suy ra thư mục repo ở dòng 20. Nhưng người vận hành chép cả hai khối thì **backfill chạy hai lần** lúc 20:30. Hãy xác nhận bằng diễn tập: cài cả hai khối thì `crontab -l` có hai dòng backfill không.
2. **Phiên bản Python của host.** §2 ghim `--python 3.12`. Hãy xác nhận `uv run python --version` trong `/opt/trading` ra 3.12.x sau bước B.2.4.

### B.6. Bộ unit test trên Python 3.12 / Linux

`cd /opt/trading && uv run pytest -m "not integration" -q`, trên môi trường 3.12 vừa cài. Đây cũng là bằng chứng cho Phần A. Mọi test đỏ đều phải báo nguyên văn. **Không sửa code để làm xanh**: một test đỏ ở đây là thông tin (có thể là khác biệt 3.11/3.12 hoặc Windows/Linux), chưa phải lỗi để vá.

Test integration **không** chạy trong đợt này (cần Postgres + NATS thật). CI đã chạy chúng trên Ubuntu.

---

## §3. Được sửa gì

- `.github/workflows/ci.yml`: **chỉ** hai dòng `python-version` (Phần A).
- `DEPLOYMENT.md`: **chỉ** những chỗ mà diễn tập chứng minh là **HỎNG** hoặc **PHẢI LỆCH**, mỗi chỗ sửa kèm tham chiếu tới output diễn tập đã chứng minh nó sai. **Không** sửa văn phong, **không** thêm mục mới, **không** sửa thứ bạn chỉ "nghĩ là" sai mà chưa chạy.
- Tạo mới: báo cáo `docs/superpowers/research/2026-09-29-dot-125-dien-tap-runbook-vps.md`, và nếu cần một script diễn tập (ví dụ `scripts/rehearse_vps_runbook.sh`) để lần sau chạy lại được. Script diễn tập phải **tự chứa**: dựng container, chạy, in bảng kết quả, tự dọn.

**KHÔNG được đụng:** mọi file trong `trading/`, `scripts/` (trừ script diễn tập mới nếu tạo), `docker-compose.yml`, `Dockerfile`, `pyproject.toml`, `uv.lock`, `.env`, `.githooks/`; mọi container đang chạy; mọi scheduled task của Windows.

---

## §4. Tiêu chí hoàn thành

1. **Bảng runbook** (B.2): mọi bước, lệnh nguyên văn, exit code, kết luận CHẠY ĐƯỢC / HỎNG / PHẢI LỆCH.
2. **Output của B.3**: ba phép kiểm tĩnh.
3. **Trả lời ba câu của B.4**, kèm nguyên văn file log trong container.
4. **Kết quả B.5**: hai điểm Claude nêu, xác nhận hoặc bác.
5. **B.6**: output `pytest` trên 3.12 (số passed/failed, nguyên văn mọi test đỏ).
6. **Diff `ci.yml`** và diff `DEPLOYMENT.md` (nếu có), mỗi chỗ sửa `DEPLOYMENT.md` trỏ về đúng dòng bảng B.2 đã chứng minh nó hỏng.
7. **Danh sách những bước KHÔNG diễn tập được**, và vì sao (cần bí mật, cần Docker daemon, cần domain và TLS, cần dữ liệu…). Danh sách này quan trọng ngang phần đã chạy: đó là những gì vẫn phải kiểm trên VPS thật.
8. Xác nhận container đã bị xoá và không container thật nào bị đụng (`docker ps -a` trước và sau).

### §4.1. Hai phép phá thử — chứng minh diễn tập bắt được lỗi, không phải lúc nào cũng "CHẠY ĐƯỢC"

| # | Đột biến (chỉ trong bản sao tài liệu **bên trong container**, không sửa file thật) | Phải thấy |
|---|---|---|
| R1 | Trong khối cron §9 đã chép vào container, đổi một tên job thành `hearbeat` (sai chính tả) | phép kiểm B.3 mục 2 báo **HỎNG** ở đúng dòng đó |
| R2 | Xoá thư mục `logs/` sau bước B.2.5 rồi chạy `sched.sh heartbeat` | nêu rõ điều gì xảy ra: lỗi ồn hay im lặng |

---

## §5. Điều cấm

- **Không commit, không push.**
- **Không** đưa `.env` hay bí mật vào container; **không** mount Docker socket; **không** khởi động stack; **không** kết nối SSI hay Telegram.
- **Không** đụng các container `ai_auto_trading_system-*` đang chạy, **không** rebuild, **không** restart.
- Không đặt, sửa, huỷ lệnh; không bật `real_trading_enabled`; không chạy `--send`.
- Không tạo, sửa, xoá scheduled task của Windows.
- Không in giá trị bí mật; không đọc nội dung `.env`.
- Cấm `git checkout`, `git restore`, `git stash`.

---

## §6. Giả định của tôi — sai thì dừng và báo

1. Docker Desktop trên máy này kéo được và chạy được `ubuntu:24.04`, và container có mạng ra ngoài (`apt`, trình cài `uv`, PyPI). Nếu không có mạng, ghi nhận và làm tiếp mọi bước không cần mạng.
2. `uv.lock` giải được trên Linux x86_64 với Python 3.12. CI đã chứng minh điều này với 3.11; với 3.12 thì chưa.
3. Diễn tập **không** phủ được: khởi động stack, restore DB (§11 bước 5), TLS/Grafana (§4), tường lửa (§3), và mọi thứ cần token SSI. Những phần đó vẫn phải kiểm trên VPS thật, và báo cáo phải liệt kê chúng (§4 mục 7).
