# Báo cáo đợt 135 — canh sao lưu sổ lệnh theo lịch giao dịch, và kiểm THẲNG cổng Docker

Không commit, không push, không sửa `docker-compose.yml` thật, không restart container, không gửi Telegram thật, không đụng `_backups/` và `data/orderbook/` (chỉ đọc).

## ⚠ Brief tự mâu thuẫn — một test DB cũ phải sửa MỘT dòng

Brief đòi (a) "mọi test DB sẵn có xanh y nguyên, không sửa một dòng" và (b) thư mục chỉ có bản dump DB **phải báo** thiếu sao lưu sổ lệnh. `tests/test_backup_check.py::test_main_dry_run_silent_on_valid_dir` dùng đúng thư mục chỉ có dump và đòi im lặng nên **không thể cùng xanh với (b)**.

**Ruling:** giữ (b) (đó là mục đích của đợt), và thêm cờ `--no-orderbook` (mặc định: **có** kiểm) rồi thêm đúng cờ đó vào dòng args của test trên. Diff của test cũ đúng một dòng: `- [..., "80.0"]` → `+ [..., "80.0", "--no-orderbook"]`. Logic DB, ngưỡng 23 giờ và test ghim `test_mot_dem_backup_hong_PHAI_bi_bat_voi_nguong_MAC_DINH` không đổi. Nếu sai: chỉ một dòng test. Cần cờ vì `sched.sh` (cấm sửa) không truyền tham số nào ngoài thư mục, nên sản xuất phải mặc định **bật**.

## 1. Việc 1 — `backup_check.py` canh bản sao lưu sổ lệnh

### `previous_trading_day` — trích thực tế (`trading/calendar_vn.py:55-63`)

```python
def previous_trading_day(d, holidays=frozenset()) -> date:
    """Ngay giao dich gan nhat TRUOC d (khong gom d), bo qua cuoi tuan va ngay le. ..."""
    cur = d - timedelta(days=1)
    while not is_trading_day(cur, holidays):
        cur -= timedelta(days=1)
    return cur
```

Đúng là **không gồm `d`**. Đã ghim bằng `test_previous_trading_day_khong_gom_chinh_ngay_d`: thứ Hai 28/09 → thứ Sáu 25/09; 29/09 → 28/09; 03/09 (sau nghỉ lễ 31/08–02/09) → 28/08.

### Bảng test ↔ phép kiểm (`tests/test_backup_check.py`, 13 test mới)

| Test | Phép kiểm |
|---|---|
| `test_khong_co_ban_so_lenh_nao_PHAI_bao` | 1. tồn tại |
| `test_lich_*` / `test_job_thu_bay_hong_PHAI_bao_va_neu_ngay_D` | 2. tuổi theo lịch |
| `test_check_orderbook_tar_doc_duoc_va_dem_file` | 3. toàn vẹn (tốt / archive rỗng / không phải tar) |
| `test_ban_so_lenh_hong_toan_ven_PHAI_bao` | 3. |
| `test_ban_so_lenh_nho_KHONG_bi_bao_vi_kich_thuoc` | 4. cố ý không có ngưỡng kích thước |
| `test_main_thu_muc_chi_co_dump_PHAI_bao_thieu_so_lenh`, `test_main_co_ca_dump_va_ban_so_lenh_moi_thi_IM` | tích hợp `main` |

### Bốn dòng bảng lịch (giờ giả, ngày lễ 31/08–02/09/2026)

| Lúc kiểm | Bản mới nhất | D (cutoff) | Kết quả |
|---|---|---|---|
| Thứ Ba 29/09 03:00 | Thứ Ba 02:30 | Thứ Hai 28/09 14:46 | **IM** |
| Chủ nhật 27/09 03:00 | Thứ Bảy 26/09 02:30 | Thứ Sáu 25/09 14:46 | **IM** |
| **Thứ Hai 28/09 03:00** | Thứ Bảy 26/09 02:30 (48,5 giờ) | Thứ Sáu 25/09 14:46 | **IM** |
| Thứ Năm 03/09 03:00 (sau nghỉ lễ) | Thứ Bảy 29/08 02:30 | Thứ Sáu 28/08 14:46 | **IM** |
| Thứ Hai 28/09 03:00, **job thứ Bảy hỏng** | Thứ Sáu 25/09 02:30 | Thứ Sáu 25/09 14:46 | **BÁO** (nêu `2026-09-25`) |

### Phá thử: thay quy tắc lịch bằng ngưỡng cố định 23 giờ

Ba test đỏ (nguyên văn): `FAILED test_lich_chu_nhat_03h_ban_thu_bay_0230_IM`, `FAILED test_lich_thu_hai_03h_ban_thu_bay_0230_IM`, `FAILED test_lich_sau_ky_nghi_dai_IM` — `AssertionError: assert ['[CRITICAL] ...\u0111\u01b0\u1ee3c sao l\u01b0u'] == []`. Đã khôi phục; 26 passed.

### Hai lần chạy thật `--dry-run`

- **A. `_backups/db`** (có `orderbook_20260930.tar.gz` + dump DB): không in gì, `EXIT=0`.
- **B. thư mục tạm chỉ có dump DB, không có bản sổ lệnh**:
  ```
  [CRITICAL] Không tìm thấy bản sao lưu sổ lệnh (orderbook_*.tar.gz) nào trong C:\Users\quelam\AppData\Local\Temp\tmpmgj3t1wv
  [DRY-RUN] Không gửi Telegram thật.
  EXIT= 1
  ```
  **Lưu ý trung thực:** hook `.agentignore` chặn lệnh có glob `trading_*.dump`, nên ở B tôi dùng file dump **giả** (90 MB, `pg_restore` được stub thành `OK`), không copy dump thật. Ở A, `pg_restore -l` chạy thật trên dump thật trong `_backups/db`.

### Quyết định thiết kế

- Kiểm toàn vẹn dùng `tarfile` của Python (đọc được + số file > 0) thay vì `tar -tzf`: cùng phép kiểm, không phụ thuộc `tar` trên PATH, không dính lỗi `D:/...`→`host:path` (đợt 134), nên không cần `--force-local`.
- Ngày lễ đọc từ `config/config.yaml`. Không đọc được thì thêm CRITICAL nêu rõ ("có thể báo oan sau kỳ nghỉ") và dùng danh sách rỗng — ồn ào chứ không im lặng.
- Chú thích đầu file ghi rõ hai quy tắc DB (23 giờ) và sổ lệnh (lịch) khác nhau vì bản chất khác nhau.

## 2. Việc 2 — `host_preflight.py` phép kiểm 12 `published_ports`

Nguồn: `docker compose --profile "*" config --format json` (đã gộp override; `"*"` để không bỏ sót service dưới profile như `nats-test`). Không gọi được → đọc thẳng `docker-compose.yml` + `docker-compose.override.yml/.yaml` (ports override được **cộng thêm**, đúng ngữ nghĩa compose) và **ghi rõ trong chi tiết** "đọc trực tiếp từ file compose, KHÔNG qua docker compose". Chỉ `BỎ QUA` khi không đọc được cả hai. Bind ngoài `127.0.0.1`/`::1`/`localhost` (kể cả `0.0.0.0`, `::`, không ghi địa chỉ) là `HỎNG`, nêu service và cổng.

`_check_ufw` giờ luôn kèm câu: *"ufw KHÔNG chi phối cổng do Docker publish ... ĐẠT ở đây không có nghĩa cổng đã kín; xem phép kiểm published_ports"* (ĐẠT, HỎNG đều có).

### Bảng test ↔ trường hợp (`tests/test_host_preflight.py`, +11 test → 55)

| Trường hợp | Test |
|---|---|
| tất cả loopback → ĐẠT | `test_ports_tat_ca_loopback_dat` |
| `0.0.0.0` → HỎNG nêu đúng service (và không nêu service sạch) | `test_ports_mot_cong_0_0_0_0_hong_va_neu_service` |
| `::` → HỎNG | `test_ports_ipv6_moi_giao_dien_hong` |
| không ghi địa chỉ (`None`, `""`) → HỎNG | `test_ports_khong_ghi_dia_chi_hong` |
| đọc từ file, cả HỎNG và ĐẠT, kèm ghi chú nguồn | `test_ports_doc_tu_file_van_ket_luan_va_ghi_nguon` |
| không đọc được gì → BỎ QUA kèm lý do | `test_ports_khong_doc_duoc_gi_bo_qua_kem_ly_do`, `test_collect_ports_khong_compose_khong_file_bo_qua` |
| compose vắng → đọc file + gộp override, bắt cổng `0.0.0.0` do override thêm | `test_collect_ports_compose_vang_doc_tu_file_va_gop_override` |
| qua `compose config` JSON | `test_collect_ports_qua_compose_config_json` |
| ufw ĐẠT phải nói không chi phối Docker | `test_ufw_dat_phai_noi_ro_khong_chi_phoi_cong_docker` |
| parse `ip:pub:tgt`, `[::1]:…`, `/tcp`, chỉ cổng | `test_parse_port_spec` |

### Hai phá thử

1. Phép kiểm luôn `ĐẠT` (bỏ nhánh HỎNG): **5 test đỏ**, gồm `test_ports_mot_cong_0_0_0_0_hong_va_neu_service` — `AssertionError: assert 'ĐẠT' == 'HỎNG'`.
2. `BỎ QUA` khi Docker vắng (`return {"skip": ...}` trước nhánh đọc file): đỏ `test_collect_ports_compose_vang_doc_tu_file_va_gop_override`.
Cả hai đã khôi phục; 55 passed.

### Chạy thật `scripts/sched.sh host-preflight` (EXIT=0) — nguyên văn từ `logs/host-preflight.log`

```
ĐẠT      TRADING_BACKUP_DIR có mặt, thư mục tồn tại và ghi được         D:/My_Vault_Obsidian/Project/_backups/db
BỎ QUA   crontab có đủ job của sched.sh và CRON_TZ                      không có lệnh crontab trên hệ này
BỎ QUA   /etc/docker/daemon.json giới hạn log (max-size, max-file)      không phải Linux (daemon.json của máy chủ nằm ở /etc/docker)
BỎ QUA   /etc/logrotate.d/trading tồn tại                               không phải Linux (không có logrotate)
BỎ QUA   .env mode 600                                                  không phải Linux (Windows không có mode 600)
ĐẠT      .env không có ký tự \r                                         0 ký tự \r
BỎ QUA   múi giờ hệ thống Asia/Ho_Chi_Minh                              không có timedatectl hay /etc/timezone trên hệ này
BỎ QUA   ufw bật, Postgres 5432 / Grafana 3000 không mở ra ngoài        không có ufw trên hệ này
ĐẠT      đĩa: trống ≥ 10 GB và tổng ≥ 40 GB                             trống 185.9 GB / tổng 449.2 GB
BỎ QUA   scripts/*.sh và .githooks/pre-push thực thi được               không phải Linux (Windows không có bit thực thi)
ĐẠT      config.yaml: real_trading_enabled: false                       false
BỎ QUA   đồng hồ hệ thống đồng bộ                                       không có timedatectl hay /etc/timezone trên hệ này
ĐẠT      mọi cổng Docker publish bind 127.0.0.1                         4 cổng, tất cả bind loopback (nguồn: docker compose config)

Tổng kết: 5 ĐẠT, 0 HỎNG, 8 BỎ QUA
```

Đúng kỳ vọng **5 ĐẠT / 0 HỎNG / 8 BỎ QUA**; phép 12 ĐẠT với nguồn `docker compose config`, 4 cổng.

### Đối chứng âm tính

`docker-compose.yml` được **sao chép** ra thư mục tạm, `sed` đổi `"127.0.0.1:5432:5432"` → `"0.0.0.0:5432:5432"` (dòng 35 của bản sao), chạy `collect_published_ports` với Docker "ngắt" (đường đọc file):
```
HỎNG | cổng lộ ra ngoài: postgres:5432 (bind 0.0.0.0) (nguồn: đọc trực tiếp từ file compose, KHÔNG qua docker compose)
```
`git diff --stat docker-compose.yml` rỗng — file thật không bị đụng.

## 3. Kiểm chung

`uv run pytest -q` → **1543 passed** (≥ 1520 + 23 mới); `ruff check trading tests scripts` sạch (đã `--fix` các cảnh báo `RUF100`/`I001` do phần tôi thêm ở hai file test); `test_deployment_doc.py` xanh; `docker compose config -q` sạch. `DEPLOYMENT.md`: chỉ thêm 3 dòng chú thích ở §9 job `backup-check` và một mệnh đề ở §11.

## 4. Không kiểm được / còn mở

- `npx --no-install gitnexus detect-changes --repo AI_auto_trading_system` trả **"No changes detected"** dù có 5 file đã sửa (index có thể cũ) — **không dùng được làm bằng chứng**; phạm vi đã đối chiếu bằng `git status`/`git diff --stat`.
- Chưa chạy trên Linux/VPS thật. Nhánh đọc file đã kiểm bằng file tạm, nhánh `docker compose config` kiểm bằng lần chạy thật trên máy này và bằng runner giả.
- `docker compose --profile "*"` cần Compose ≥ bản có hỗ trợ ký tự `*`; nếu bản cũ hơn thì tự rơi về đọc file (có ghi nguồn), không im lặng.
- Phép 12 chỉ nhìn cấu hình compose, không nhìn cổng đang nghe thật trên host (`ss -ltn`); container chưa được tạo lại theo compose mới thì hai thứ có thể lệch.
- Bản sao lưu DB thật không được thử nghiệm ở kịch bản B (xem lưu ý về hook).

---

## Audit của Claude (30/09/2026)

### A.1. Kết luận: ĐẠT, nhận toàn bộ.

### A.2. Mâu thuẫn trong brief là lỗi của Claude — chấp nhận cách agent xử lý

Brief vừa cấm sửa test DB cũ vừa đòi thư mục chỉ có dump phải báo thiếu sổ lệnh; hai điều không cùng đúng được. Agent nêu rõ mâu thuẫn, giữ đúng mục đích của đợt và chỉ đổi đúng một dòng args. Cờ `--no-orderbook` mặc định **tắt**, nên job thật vẫn kiểm (`sched.sh` không truyền cờ).

### A.3. Kiểm độc lập — Claude tự viết ca, không dùng test của agent

Lịch, với ngày khác các ca trong test của agent:

| Lúc kiểm | Bản mới nhất | Kết quả |
|---|---|---|
| T4 30/09 03:00 | T4 02:30 | IM |
| CN 04/10 03:00 | T7 03/10 02:30 | IM |
| **T2 05/10 03:00** | T7 03/10 02:30 (48,5 giờ) | IM |
| T5 03/09 03:00 (sau lễ) | T7 29/08 | IM |
| T2 05/10 03:00, job T7 hỏng | T6 02/10 02:30 | **BÁO** (72,5 giờ) |
| T4 30/09 03:00, job đêm qua hỏng | T3 02:30 | **BÁO** (24,5 giờ) |
| `now` truyền vào là UTC | — | quy đổi đúng, IM |

Toàn vẹn: bản thật `orderbook_20260930.tar.gz` (15,5 MB) → `OK`; file rác → `ReadError`; bản thật **bị cắt nửa** → `EOFError`. Ca cắt nửa là ca thật nhất (đĩa đầy giữa chừng), agent không thử; nó bị bắt.

Cổng (trên bản sao, không đụng file thật):
- Grafana ghi `"3000:3000"` (không ghi IP) → HỎNG, đọc từ file.
- File override thêm `0.0.0.0:5433:5432` → HỎNG ở **cả hai đường**: đọc file và `docker compose config` thật. Đây là kịch bản VPS (§11 Bước 5 tạo override), agent chỉ thử nhánh đọc file.

Phá thử của Claude: đổi mốc thành `now - 23h` → đúng ba test lịch đỏ (CN, T2, sau lễ); khôi phục, hash trùng `36aa036d884dbabe`.

Chạy đúng lệnh lịch gọi: `sched.sh backup-check --dry-run` EXIT=0, không cảnh báo (có bản sổ lệnh 00:06 hôm nay); `sched.sh host-preflight` → **5 ĐẠT / 0 HỎNG / 8 BỎ QUA**, EXIT=0. `ruff` sạch; **1.543 passed**.

GitNexus: agent đúng — `detect-changes` trả "No changes" vì index cũ. Claude chạy `analyze` rồi đo lại: 4 luồng, đều trong `host_preflight` (`evaluate`, `collect_facts`, `collect_published_ports`, `parse_port_spec`); không có luồng nào ngoài phạm vi.

### A.4. Lỗ còn lại — không phải lỗi của đợt này, nhưng đợt này làm nó lộ ra

`config/config.yaml` **không có Tết Nguyên Đán 2027** (và giỗ Tổ 2027). Danh sách hiện có: 31/08–02/09/2026, 01/01, 30/04, 01/05, 02/09/2027. Hậu quả:
- Phép kiểm sổ lệnh sẽ **báo oan mỗi sáng** trong kỳ nghỉ Tết (tháng 2/2027). Ồn chứ không im — đúng hướng an toàn, nhưng vẫn là báo oan.
- Mọi job theo lịch khác (heartbeat, stream-health, daily-check, engine-consumer…) cùng đọc danh sách này.

Hạn chót: trước **đầu tháng 2/2027**. Ngày nghỉ chính thức do nhà nước công bố hằng năm, nên chủ dự án điền theo thông báo của sở giao dịch; Claude không tự đoán ngày.

Ghi nhận đúng của agent (mục 4): phép 12 nhìn **cấu hình**, không nhìn cổng đang nghe thật (`ss -ltn`). Trên VPS, lần đầu nên đối chiếu tay một lần.

