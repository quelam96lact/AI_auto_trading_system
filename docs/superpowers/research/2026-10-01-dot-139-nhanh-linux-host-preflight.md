# Báo cáo đợt 139 — chạy THẬT các nhánh Linux của `host_preflight`, và phép kiểm 14

Không commit, không push, không tạo scheduled task, không sửa `.env`. Không đụng container của dự án. Chỉ dùng `docker run --rm -i ubuntu:24.04` (image có sẵn), **không** `-p`, **không** `--privileged`, **không** `--network host`, **không** mount repo. Mã đưa vào bằng `git ls-files -z --cached --others --exclude-standard | tar --null -T - -cf - | docker run --rm -i ...` (bỏ file bị `.gitignore`, gồm `.env` thật). Hai kịch bản mới ở `scripts/` (`probe_host_preflight_linux.sh` = lệnh chạy; `host_preflight_linux_scenarios.sh` = kịch bản bên trong container); **không** thêm vào `sched.sh`; đã `git add --intent-to-add --chmod=+x` để mode là `100755`.

## 1. Bằng chứng không có `.env` thật trong container (nguyên văn, in TRƯỚC khi tạo `.env` giả)

```
### BANG CHUNG KHONG CO .env THAT TRONG CONTAINER (ls -la thu muc goc repo, TRUOC khi tao .env gia)
-rw-r--r--  1 197608 197121    388 Aug 18 10:45 .dockerignore
-rw-r--r--  1 197608 197121   1707 Sep 29 15:50 .env.example
-rw-r--r--  1 197608 197121     42 Sep  1 04:31 .gitattributes
drwxr-xr-x  2 root   root     4096 Sep 30 23:34 .githooks
... (không có dòng `.env`; chỉ có `.env.example`)
### (het bang chung) — khong co .env. Tu day moi tao .env gia.
```
Kịch bản còn tự dừng (`exit 4`) nếu thấy `.env`.

## 2. Việc 1 — phát hiện (chạy thật dưới root VÀ `trader`)

Cài trong container: `cron logrotate iproute2 python3 python3-yaml tzdata sudo`. Crontab của **root** = khối `DEPLOYMENT.md` §9 (16 job + `CRON_TZ`, dòng 452/995 dùng `sudo crontab -e`); tài khoản `trader` không có crontab. Kho `/opt/trading` thuộc `trader`.

### Chuỗi đầu ra THẬT bắt được

```
trader: crontab -l                          -> "no crontab for trader", rc=1
root  : crontab -l (chưa có crontab)        -> "no crontab for root",   rc=1
trader: sudo -n crontab -l -u root (không sudoers) -> "sudo: a password is required", rc=1
trader: sudo -n crontab -l -u root (có sudoers NOPASSWD crontab) -> nội dung crontab của root, rc=0
os.access(sched.sh, X_OK) với mode 411:  root = True,  trader = False
```

### Phát hiện (không phải thất bại của đợt)

| # | Phát hiện | Đo thật (TRƯỚC) | Sửa |
|---|---|---|---|
| F1 | Chạy tay như tài liệu dạy (không `sudo`) → `crontab -l` đọc crontab của tài khoản thường → phép crontab **HỎNG oan** dù cron của root đủ | `CRON ĐẠT`: root=**ĐẠT**, trader=**HỎNG** ("người dùng chưa có crontab"); tương tự ở hai ca HỎNG | `collect_cron`: không phải root → thử `sudo -n crontab -l -u root`; không được → **BỎ QUA** kèm cách chạy lại (không HỎNG); tài khoản có crontab riêng đủ thì ĐẠT kèm ghi chú "không phải root" |
| F2 | `.env` thuộc root mode 600, chạy dưới `trader` → `PermissionError` → **công cụ chết bằng traceback** | `.ENV: thuoc root`: trader = **CHẾT** (Traceback ở `collect_facts`) | bắt `PermissionError` → `env_crlf` **BỎ QUA** ("không đọc được .env (quyền)") |
| F3 | `sched.sh` không đọc được bởi tài khoản chạy → traceback | `EXEC LẠ` (mode 010): trader = **CHẾT** (Traceback ở `sched_job_labels`) | `main` bắt `OSError` → `LỖI CẤU HÌNH: không đọc được .../sched.sh`, thoát 2, không traceback |
| F4 | Phép cờ thực thi dùng `os.access(X_OK)` → phụ thuộc danh tính (mode 411: root True, trader False) | `os.access`: root=True, trader=False (dòng trên) | `is_executable_mode`: **có bất kỳ bit x** → thực thi được (root/cron chạy được); hai danh tính cùng ĐẠT |
| F5 | Hai danh tính cho kết quả khác nhau mà bảng không nói ai đã đo | — | `render_table` in cảnh báo "Chạy dưới uid=N (không phải root)… chạy lại bằng `sudo scripts/sched.sh host-preflight` để khớp với cron"; JSON có `euid` |

Mỗi phát hiện có test dùng **chuỗi thật** (hoặc chế độ PermissionError thật mô phỏng): `test_cron_tai_khoan_thuong_khong_co_crontab_khong_co_sudo_la_BO_QUA_khong_phai_HONG_oan` (dùng `REAL_NO_CRONTAB`, `REAL_SUDO_DENIED` đúng như trên), `test_cron_root_*`, `test_cron_tai_khoan_thuong_sudo_*`, `test_main_env_khong_doc_duoc_quyen_khong_chet_ma_BO_QUA`, `test_main_sched_sh_khong_doc_duoc_thoat_2_khong_traceback`, `test_is_executable_mode_do_bit_khong_phu_thuoc_danh_tinh`, `test_render_table_canh_bao_khi_khong_chay_duoi_root`, `test_main_json_co_truong_euid`.

### Phương án đã chọn (nêu trước khi làm) — sửa CẢ công cụ VÀ tài liệu

1. **Công cụ** (như bảng trên): không đoán crontab của ai; đọc của root khi có thể, BỎ QUA khi không.
2. **Tài liệu** (`DEPLOYMENT.md` §11 sau Bước 8): đổi lệnh tay thành `sudo scripts/sched.sh host-preflight` (và `sudo uv run python scripts/host_preflight.py`) kèm giải thích **vì sao** (cron của root ⇒ chạy dưới root).
Cả hai đều nằm trong `host_preflight.py` và `DEPLOYMENT.md`, không cần đổi gì ngoài hai file đó.

### Bảng 12 trạng thái (+ phụ), mỗi dòng dưới cả hai danh tính — TRƯỚC và SAU khi sửa

(`✓` = đúng kỳ vọng. Mỗi trạng thái dựng bằng lệnh trong kịch bản `host_preflight_linux_scenarios.sh`, hàm `viec1`.)

| Phép | Trạng thái (lệnh dựng) | root TRƯỚC→SAU | trader TRƯỚC→SAU |
|---|---|---|---|
| crontab | **ĐẠT**: `crontab -u root` = khối §9 | ĐẠT→ĐẠT ✓ | **HỎNG→BỎ QUA** (F1) |
| crontab | **HỎNG**: bỏ dòng `sched.sh backup-check` | HỎNG→HỎNG ✓ | HỎNG→BỎ QUA (F1) |
| crontab | **HỎNG**: bỏ dòng `CRON_TZ` | HỎNG→HỎNG ✓ | HỎNG→BỎ QUA (F1) |
| crontab | ĐẠT qua `sudo -n` (sudoers `trader … NOPASSWD: /usr/bin/crontab`) | — →ĐẠT | — →**ĐẠT** ("crontab của root, đọc qua sudo -n") |
| crontab | HỎNG qua `sudo -n` (root thiếu job) | — →HỎNG | — →**HỎNG** (khớp root) |
| crontab | khối cron chỉ nằm ở crontab của trader | HỎNG→HỎNG | ĐẠT→ĐẠT kèm "không phải root" |
| daemon.json | **ĐẠT**: `max-size=10m, max-file=3` | ĐẠT→ĐẠT ✓ | ĐẠT→ĐẠT ✓ |
| daemon.json | **HỎNG**: `rm /etc/docker/daemon.json` | HỎNG→HỎNG ✓ | HỎNG→HỎNG ✓ |
| daemon.json | **HỎNG**: JSON hỏng `{"log-driver": "json-file", "log-opts": ` | HỎNG→HỎNG ✓ | HỎNG→HỎNG ✓ |
| daemon.json | `chmod 600` (root sở hữu) | ĐẠT | **BỎ QUA** ("không đọc được … (quyền)") ✓ |
| logrotate | **ĐẠT**: `: > /etc/logrotate.d/trading` | ĐẠT→ĐẠT ✓ | ĐẠT→ĐẠT ✓ |
| logrotate | **HỎNG**: `rm` file | HỎNG→HỎNG ✓ | HỎNG→HỎNG ✓ |
| `.env` mode | **ĐẠT**: `chmod 600` | ĐẠT→ĐẠT ✓ | ĐẠT→ĐẠT ✓ |
| `.env` mode | **HỎNG**: `chmod 644` | HỎNG→HỎNG ✓ | HỎNG→HỎNG ✓ |
| `.env` CR | hai dòng CRLF | HỎNG→HỎNG ✓ | HỎNG→HỎNG ✓ |
| `.env` (root 600, chạy trader) | `chown root`, `chmod 600` | ĐẠT/ĐẠT | **CHẾT→BỎ QUA** (F2) |
| múi giờ | **ĐẠT**: `/etc/timezone`=`Asia/Ho_Chi_Minh` | ĐẠT→ĐẠT ✓ | ĐẠT→ĐẠT ✓ |
| múi giờ | **HỎNG**: `Etc/UTC` | HỎNG→HỎNG ✓ | HỎNG→HỎNG ✓ |
| cờ thực thi | **ĐẠT**: `chmod +x scripts/*.sh .githooks/pre-push` | ĐẠT→ĐẠT ✓ | ĐẠT→ĐẠT ✓ |
| cờ thực thi | **HỎNG**: `chmod 644 scripts/sched.sh` | HỎNG→HỎNG ✓ | HỎNG→HỎNG ✓ |
| cờ thực thi | **HỎNG**: `chmod 644 .githooks/pre-push` | HỎNG→HỎNG ✓ | HỎNG→HỎNG ✓ |
| cờ thực thi | mode 411 (chủ sở hữu chỉ `r`) | ĐẠT→ĐẠT | (`os.access` False) →**ĐẠT** (F4) |
| thư mục sao lưu | **ĐẠT**: thuộc `trader`, 755 | ĐẠT→ĐẠT ✓ | ĐẠT→ĐẠT ✓ |
| thư mục sao lưu | thuộc **root**, 755 | **ĐẠT** | **HỎNG** ("không ghi được: /srv/bak") |
| thư mục sao lưu | **HỎNG**: không tồn tại | HỎNG→HỎNG ✓ | HỎNG→HỎNG ✓ |
| thư mục sao lưu | **HỎNG**: chưa đặt biến | HỎNG→HỎNG ✓ | HỎNG→HỎNG ✓ |
| phép 12 (đường đọc file, **lần đầu trên Linux**) | `docker-compose.yml` bản sao trong container | ĐẠT "4 cổng, tất cả bind loopback (nguồn: đọc trực tiếp từ file compose, KHÔNG qua docker compose)" | như root ✓ |
| phép 12 | **HỎNG**: bản sao compose đổi `5432` thành `0.0.0.0` | HỎNG "postgres:5432 (bind 0.0.0.0)" ✓ | như root ✓ |

Hai cột **khớp nhau** ở mọi phép khớp được, trừ hai chỗ khác **đúng có chủ ý**:
- **Thư mục sao lưu thuộc root, 755:** root ĐẠT, trader HỎNG. Đó là hành vi **đúng của `os.access`** (phép này hỏi "tài khoản đang chạy có ghi được không"). Ý nghĩa cho cron (chạy dưới root): root luôn ghi được nên **ĐẠT là thật đối với chính job cron** — `backup_db.sh` sẽ ghi được; nhưng nó **không** chứng minh tài khoản thường ghi được. Vì vậy lệnh tay phải chạy `sudo` (cùng danh tính với cron) và bảng in cảnh báo uid khi không phải root (F5). Chạy dưới root thì hai lần chạy (tay và cron) khớp nhau.
- **Crontab khi không đọc được của root:** trader BỎ QUA (không HỎNG) — đúng và trung thực; có `sudo -n` thì **khớp hoàn toàn** với root (hai dòng `sudo -n` ở bảng).

### ufw và đồng hồ — dự kiến vẫn BỎ QUA, đúng

```
ufw    BỎ QUA  không có ufw trên hệ này
clock  BỎ QUA  không có timedatectl trên hệ này
```
Lý do thật: container không có `ufw` và không có `systemd`/`timedatectl` (không cài; không dùng `--privileged` để ép ĐẠT). Đó vẫn là việc của lần chạy đầu trên VPS.

## 3. Việc 2 — phép kiểm 14 `published_listening`

`ss -ltnH`, chỉ Linux (không phải Linux → BỎ QUA "không phải Linux (ss -ltnH chỉ có trên Linux)"; thiếu `ss` → BỎ QUA "không có lệnh ss trên hệ này"). Cổng xét = các cổng publish mà phép 12 đọc được (`4222 4223 3000 5432` trong container); phép 12 BỎ QUA thì dùng `CLOSED_PORTS`. Nghe ở địa chỉ ngoài loopback → HỎNG nêu cổng và địa chỉ; chỉ loopback → ĐẠT; không có gì nghe → ĐẠT nhưng chi tiết nói thẳng *"không có tiến trình nào nghe … — container có đang chạy không? (phép này kiểm lộ cổng, không kiểm sống/chết; xem container-health)"*. Phân tích bằng hàm thuần `parse_ss_listen` (địa chỉ ở cột 4, bỏ `[]` và `%iface`, chịu cột Process thừa), `_is_loopback` qua `ipaddress` (`*`, `::`, `0.0.0.0` và mọi thứ không phân tích được **không** là loopback).

### Chuỗi `ss -ltnH` THẬT bắt được (dùng làm dữ kiện test)

```
http.server --bind 0.0.0.0 : LISTEN 0      5      0.0.0.0:3000 0.0.0.0:*
http.server --bind 127.0.0.1: LISTEN 0      5      127.0.0.1:3000 0.0.0.0:*
http.server --bind ::       : LISTEN 0      5      *:3000 *:*            (dual-stack, hiện là "*")
http.server --bind ::1      : LISTEN 0      5      [::1]:3000 [::]:*
socket IPV6_V6ONLY bind ::  : LISTEN 0      5      [::]:3000 [::]:*
SO_BINDTODEVICE lo         : LISTEN 0      5      127.0.0.53%lo:3000 0.0.0.0:*
địa chỉ thật của container : LISTEN 0      5      172.17.0.2:3000 0.0.0.0:*
ss -ltnHp (root)           : LISTEN 0      5      0.0.0.0:3000 0.0.0.0:* users:(("python3",pid=3164,fd=3))
không chạy gì              : (rỗng)
```

### Ba đối chứng trong container (dán nguyên văn, cả hai danh tính)

```
PHEP 14: http.server 3000 --bind 0.0.0.0    -> root/trader: HỎNG  cổng đang nghe NGOÀI loopback: 3000 trên 0.0.0.0
PHEP 14: http.server 3000 --bind 127.0.0.1  -> root/trader: ĐẠT   đang nghe chỉ trên loopback: 3000 (127.0.0.1)
PHEP 14: http.server 3000 --bind ::         -> root/trader: HỎNG  cổng đang nghe NGOÀI loopback: 3000 trên *
PHEP 14: http.server 3000 --bind ::1        -> root/trader: ĐẠT   đang nghe chỉ trên loopback: 3000 (::1)
PHEP 14: không chạy gì                      -> root/trader: ĐẠT   không có tiến trình nào nghe trên các cổng [3000, 4222, 4223, 5432] — container có đang chạy không? (phép này kiểm lộ cổng, không kiểm sống/chết; xem container-health)
```

### Test (`tests/test_host_preflight.py`) và phá thử

Bảy ca bắt buộc đều có test bằng chuỗi thật: loopback v4 (`test_ss_loopback_v4_dat`), loopback v6 `[::1]` (`test_ss_loopback_v6_ngoac_vuong_dat`), `0.0.0.0` (`test_ss_0_0_0_0_hong_nem_cong_va_dia_chi`), `*` (`test_ss_sao_dual_stack_hong`), `[::]` (`test_ss_v6_moi_giao_dien_ngoac_vuong_hong`), không có gì nghe (`test_ss_khong_nghe_gi_dat_nhung_noi_thang_khong_co_tien_trinh`), không có `ss` (`test_ss_khong_co_lenh_ss_bo_qua` + `test_collect_ss_khong_phai_linux_bo_qua`); thêm `%lo`, IP thật, cột Process thừa, cổng ngoài dự án bị bỏ qua, và `test_collect_ss_co_ss_chay_that_qua_runner_gia`.

**Phá thử** — coi `[::]` là loopback (`if addr == "::": return True`): `FAILED tests/test_host_preflight.py::test_ss_v6_moi_giao_dien_ngoac_vuong_hong` (`AssertionError: assert ('ĐẠT' == 'HỎNG'`), 1 failed / 95 passed. SHA-256 trước `0c89dd1a584a57c3dc7c4b996afc054681c99b35a49413d056a76e998aacc76c`; sau khôi phục `sha256sum -c` → `scripts/host_preflight.py: OK`, 96 passed.

## 4. Chạy thật `scripts/sched.sh host-preflight` trên máy dev (EXIT=0) — đúng kỳ vọng **6 ĐẠT / 0 HỎNG / 9 BỎ QUA**

```
ĐẠT      TRADING_BACKUP_DIR có mặt, thư mục tồn tại và ghi được         D:/My_Vault_Obsidian/Project/_backups/db
BỎ QUA   crontab có đủ job của sched.sh và CRON_TZ                      không có lệnh crontab trên hệ này
BỎ QUA   /etc/docker/daemon.json giới hạn log (max-size, max-file)      không phải Linux (daemon.json của máy chủ nằm ở /etc/docker)
BỎ QUA   /etc/logrotate.d/trading tồn tại                               không phải Linux (không có logrotate)
BỎ QUA   .env mode 600                                                  không phải Linux (Windows không có mode 600)
ĐẠT      .env không có ký tự \r                                         0 ký tự \r
BỎ QUA   múi giờ hệ thống Asia/Ho_Chi_Minh                              không có timedatectl hay /etc/timezone trên hệ này
BỎ QUA   ufw bật, Postgres 5432 / Grafana 3000 không mở ra ngoài        không có ufw trên hệ này
ĐẠT      đĩa: trống ≥ 10 GB và tổng ≥ 40 GB                             trống 185.8 GB / tổng 449.2 GB
BỎ QUA   scripts/*.sh và .githooks/pre-push thực thi được               không phải Linux (Windows không có bit thực thi)
ĐẠT      config.yaml: real_trading_enabled: false                       false
BỎ QUA   đồng hồ hệ thống đồng bộ                                       không có timedatectl hay /etc/timezone trên hệ này
ĐẠT      mọi cổng Docker publish bind 127.0.0.1                         4 cổng, tất cả bind loopback (nguồn: docker compose config)
ĐẠT      lịch nghỉ được xác nhận tới ≥ hôm nay + 60 ngày                xác nhận tới 2026-12-31, còn 91 ngày
BỎ QUA   cổng đang nghe thật (ss -ltnH) không lộ ra ngoài loopback      không phải Linux (ss -ltnH chỉ có trên Linux)

Tổng kết: 6 ĐẠT, 0 HỎNG, 9 BỎ QUA
```

## 5. Container dự án không bị đụng; không còn container dùng một lần

`StartedAt` **trước** và **sau** (giống hệt): `postgres 2026-09-30T01:23:44.126466309Z`, `engine …44.114725976Z`, `collector …44.098961596Z`, `nats …44.065768163Z`, `nats-test …44.082573151Z`, `grafana …44.120664044Z`. `docker ps -a` sau cùng chỉ còn sáu container dự án (`Up 23 hours`); không còn container `ubuntu:24.04` nào (`--rm`).

## 6. Kiểm chung

`uv run pytest -q` → **1660 passed** (mốc 1630 + 30); `ruff check trading tests scripts` sạch; `test_deployment_doc.py` 3 passed; `bash -n` sạch hai kịch bản mới (LF, `100755`). `gitnexus impact` trên `collect_facts`, `render_table`, `main`: **LOW**, 0 process. `detect_changes`: risk **low**, 0 process bị ảnh hưởng (nhiều `_check_*` hiện là "touched" vì hook định dạng đã xuống dòng lại cả file `host_preflight.py` — xem ghi chú).

## 7. Brief sai / mơ hồ

- Nghi vấn số 2 của brief ("cờ thực thi và thư mục sao lưu có thể ĐẠT giả dưới root") **đúng một nửa**: thư mục sao lưu root 755 cho root ĐẠT — nhưng điều đó **đúng** cho cron (root luôn ghi được); "giả" chỉ khi đọc nó như "tài khoản thường ghi được". Phép cờ thực thi dưới root **không** sai với mode thực tế (git cho 644/755), chỉ sai với mode lạ (411).
- Mode `010` của kịch bản ban đầu làm công cụ chết vì **chính `sched.sh` không đọc được** (chủ sở hữu không có `r`), không phải vì `os.access`; tôi đổi sang mode `411` để cô lập đúng `os.access` (root True / trader False) và giữ ca `010` làm phát hiện F3.
- `DEPLOYMENT.md` §11 đợt 135 có một đoạn mất chữ `\r` (chỉ còn cặp backtick rỗng `` ` ` ``); tôi viết lại "không có ký tự CR" khi sửa đoạn này.

## 8. Không kiểm được

- **`ufw` và đồng hồ (`timedatectl`)**: container không có, BỎ QUA đúng; vẫn là việc của lần chạy đầu trên VPS.
- **Docker thật trên Linux** (đường `docker compose config` trên Linux): container không có Docker; phép 12 chỉ chạy đường đọc file.
- **Daemon cron không chạy** trong container: tôi chỉ kiểm `crontab -l`/`crontab -u root` (đủ cho phép crontab), **không** kiểm cron thật có kích hoạt job không.
- `sudo uv run python ...` dưới root (lệnh tài liệu mới) chưa chạy: không có `uv` trong container và `uv`/venv của root là việc của VPS.
- Hook định dạng (formatter) chạy trên `host_preflight.py` đã xuống dòng lại phần lớn file (diff ồn: 294 thêm / 42 xoá dù bỏ khoảng trắng), nên khi audit nên đọc theo hàm mới: `collect_cron`, `is_executable_mode`, `parse_ss_listen`, `_is_loopback`, `listening_ports`, `_check_published_listening`, `render_table(euid)`, `main` (bắt `OSError`).

---

## Audit của Claude (02/10/2026, 06:00)

### A.1. Kết luận: ĐẠT, nhận toàn bộ.

### A.2. Container Linux riêng của Claude — các ca KHÁC của agent

Claude chạy một container `ubuntu:24.04` dùng một lần, với kịch bản riêng không dùng kịch bản của agent. Mã đưa vào bằng `tar` của cây làm việc (kiểm trước: `tar co .env? 0`). Crontab root được lấy độc lập từ `DEPLOYMENT.md` (17 dòng: `CRON_TZ` + 16 job).

| Ca | root | trader |
|---|---|---|
| [A] trader **không** sudo, crontab root đủ | — | `BỎ QUA` "...không đọc được crontab của root (sudo -n không khả dụng)... chạy lại bằng `sudo scripts/sched.sh host-preflight`" — **không còn HỎNG oan** |
| [B] trader có sudo NOPASSWD | `ĐẠT` đủ 16 job và CRON_TZ | `ĐẠT` đủ 16 job và CRON_TZ (crontab của root, đọc qua sudo -n) |
| [C] crontab root thiếu `restore-drill` | `HỎNG` thiếu job: restore-drill | `HỎNG` thiếu job: restore-drill |
| [D] `sched.sh` mode 0644 | `HỎNG` | `HỎNG` |
| [D] `sched.sh` mode **0711** | `ĐẠT` | `ĐẠT` |
| [E] `.env` của root, mode 644 | `HỎNG` mode 0o644 | `HỎNG` mode 0o644 |
| [E] `.env` của root, mode 600 | `ĐẠT` | `ĐẠT` |
| [F] `http.server --bind ::` cổng 4222 (`ss`: `*:4222`) | `HỎNG` 4222 trên * | `HỎNG` 4222 trên * |
| [F] `--bind 127.0.0.1` cổng 4222 | `ĐẠT` 4222 (127.0.0.1) | — |

Hai cột khớp nhau ở mọi ca. Ở [E] với mode 600, Claude từng ghi kỳ vọng sai là "trader BỎ QUA". Kết quả đúng là ĐẠT: đọc mode chỉ cần quyền trên thư mục, không cần quyền đọc file.

`StartedAt` của sáu container dự án giống hệt trước và sau; không còn container ubuntu nào sót lại.

### A.3. Phá thử của Claude

- Coi `*` (mọi giao diện, dual-stack) là loopback → `test_ss_sao_dual_stack_hong` đỏ.
- Bỏ nhánh `sudo` của `collect_cron` (luôn đọc crontab của chính tài khoản) → **4 test đỏ**, gồm `..._khong_co_sudo_la_BO_QUA_khong_phai_HONG_oan` và `..._sudo_khong_mat_khau_doc_duoc_crontab_cua_root`.

Hash khôi phục trùng `0c89dd1a584a57c3`. `ruff` sạch; unit **1.518 passed** (Docker tắt lúc chạy). Hook pre-push chạy lại đủ cả integration lúc push.

### A.4. Một giới hạn Claude ghi lại (chưa phải rủi ro thực tế)

Phép 14 nhìn socket mà `docker-proxy` mở. Nếu sau này `daemon.json` đặt `"userland-proxy": false`, cổng publish chỉ còn là luật iptables, không có socket nghe, và phép 14 sẽ ra "ĐẠT — không có tiến trình nào nghe". Hiện `DEPLOYMENT.md` không đặt cờ đó, và phép 12 (đọc cấu hình) vẫn che phần này.

### A.5. Chưa kiểm được (đồng ý với agent)

ufw và `timedatectl` thật; Docker thật trên Linux; cron daemon có thực sự gọi job hay không. Đó là việc của lần chạy đầu trên VPS.

