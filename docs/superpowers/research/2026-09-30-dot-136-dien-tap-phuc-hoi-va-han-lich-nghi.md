# Báo cáo đợt 136 — diễn tập phục hồi THẬT, và hạn của danh sách ngày nghỉ

Không commit, không push. **Diễn tập phục hồi chưa được chạy thật lần nào** (brief cấm — nó tạo và xoá database): độ tin cậy của `restore_drill.py` đến từ test với runner giả và hai phá thử dưới đây, **không** từ một lần chạy trên Docker/Postgres thật. Không đụng `verify_backup_restore.py`, `backup_db.sh`, `backup_orderbook.sh`, `docker-compose.yml`, `.env` (đã kiểm `git diff --quiet`).

## Chỗ brief mơ hồ / mâu thuẫn và cách tôi xử lý (ruling)

1. **"mặc định `--dry-run`"**. Nếu cờ này mặc định bật, job cron `restore-drill` **không bao giờ gửi cảnh báo** — đúng cái "chuông giả" mà đợt này muốn diệt. *Ruling:* `--dry-run` là cờ **tuỳ chọn**, mặc định **gửi** (giống `backup_check.py`, `disk_check.py`); tôi chỉ chạy với `--dry-run`/guard. Sai thì mất: đổi mặc định một dòng.
2. **"HỎNG nếu `< hôm nay + 60 ngày`" và "chuyển HỎNG từ 01/11/2026"** lệch nhau một ngày: 31/12 − 60 ngày = 01/11, tại 01/11 còn đúng 60 ngày nên `<` cho **ĐẠT**; phép kiểm chuyển HỎNG từ **02/11/2026** (còn 59). *Ruling:* giữ quy tắc `<` (nói trước trong brief); test ghim cả hai biên; chú thích trong `config.yaml` ghi "từ 02/11/2026".
3. **`pg_restore` có thể báo lỗi lành tính khác `continuous_agg`** — *chưa kiểm được, rủi ro thật cho lần chạy đầu*: theo brief, bước 4 tạo `CREATE EXTENSION timescaledb` **trước** rồi `pg_restore`; một dump `-Fc` có thể chứa `CREATE EXTENSION timescaledb`, khi đó `pg_restore` có thể in `error: ... extension "timescaledb" already exists` và trả exit 1. `DEPLOYMENT.md` không ghi mã thoát của bước tương tự nên tôi **không đoán**; hiện mọi lỗi trừ đúng cảnh báo `continuous_agg` (vốn không chứa `error:`) đều là CRITICAL. Nếu lần chạy thật đầu tiên của Claude báo đúng lỗi này thì đó là báo động giả cần một ngoại lệ có chủ ý, **không** phải bản sao lưu hỏng.
3b. Nhánh exit 0 của `judge_pg_restore` chỉ bắt dòng `error:`; các `warning:` khác (ngoài `continuous_agg`) không bị coi là lỗi (brief ghi "chỉ chấp nhận cảnh báo continuous_agg" nhưng không nói rõ cảnh báo khác phải báo hay không). Nếu muốn chặt hơn: đổi một hàm.

## Việc 1 — `scripts/restore_drill.py`

Luồng: dump `trading_*.dump` mới nhất → kiểm đĩa (≥ 3× dump, không đủ thì dừng, **không** `CREATE DATABASE`) → xoá DB nháp cũ nếu sót → `CREATE DATABASE trading_restore_drill` → `docker compose cp` → `CREATE EXTENSION timescaledb` → `timescaledb_pre_restore()` → `pg_restore --no-owner` → `timescaledb_post_restore()` → phán xử mã thoát **và** stderr → so **tập bảng** hai bên bằng truy vấn catalog (`public`, `relkind IN ('r','p')`, không danh sách cứng) → so số dòng **từng bảng** (< 99% hoặc `-1` ở **bất kỳ** bên nào → CRITICAL) → `finally`: xoá file tạm + `DROP DATABASE ... WITH (FORCE)` rồi **kiểm chứng** bản nháp đã mất và `trading` còn. Chốt cứng tên DB đích (`trading`, rỗng, `postgres`, `template0/1`) → thoát 2 **trước mọi lệnh**. Mã thoát họ "theo gửi được hay không" (0 / 1 / 2). Mọi lệnh ra ngoài đi qua `runner` thay được; phán xử là các hàm thuần `judge_pg_restore`, `judge_tables`, `judge_counts`.

Sửa một lỗi tôi tự mắc khi viết: bản đầu dùng `return alerts + [...]` trong `try`, nên cảnh báo dọn dẹp của `finally` bị **mất** (không tới người gọi). Đã tách `_drill_steps` để `run_drill` luôn trả `alerts + cleanup_alerts` (test `test_run_drill_lenh_don_dep_hong_thi_co_CRITICAL` ghim).

### Bảng test ↔ tiêu chí (`tests/test_restore_drill.py`, 39 test)

| Ca yêu cầu | Test |
|---|---|
| mọi thứ khớp → IM | `test_run_drill_moi_thu_khop_IM_va_da_don_dep`, `test_counts_khop_IM` |
| `pg_restore` exit 1 → BÁO (nêu dòng lỗi đầu) | `test_pg_restore_exit_1_bao_kem_dong_loi_dau`, `test_run_drill_pg_restore_exit_1_bao_va_van_don_dep` |
| exit 0 nhưng stderr có `error:` → BÁO | `test_pg_restore_exit_0_nhung_stderr_co_error_van_bao` |
| exit 0 với đúng cảnh báo `continuous_agg` → IM | `test_pg_restore_exit_0_voi_dung_canh_bao_continuous_agg_IM` |
| thiếu một bảng → BÁO nêu tên | `test_tables_thieu_mot_bang_bao_neu_ten`, `test_run_drill_thieu_bang_bao_neu_ten` |
| một bảng còn 90% → BÁO nêu hai số | `test_counts_mot_bang_con_90_phan_tram_bao_neu_ten_va_hai_so`, `test_run_drill_bang_con_90_phan_tram_bao` |
| ca thật 30/09 (`bars` 99,99%, `orders`=0) → BÁO | `test_counts_bang_nho_ve_0_bao_du_bang_lon_con_99_99` |
| lệch 0,01% → IM | `test_counts_lech_0_01_phan_tram_IM` |
| không đọc được số dòng ở một bên → BÁO | `..._o_ben_nguon_bao`, `..._o_ben_phuc_hoi_bao` |
| **cả hai bên** (`-1 == -1`) → BÁO | `test_counts_khong_doc_duoc_o_CA_HAI_ben_van_bao_khong_phai_khop` |
| tên DB đích `trading` → thoát 2 (không gọi runner) | `test_ten_db_dich_bi_cam[...]`, `test_main_ten_db_trading_thoat_2_va_khong_goi_runner` |
| ngoại lệ khi phục hồi → runner **vẫn** nhận `DROP DATABASE` | `test_run_drill_ngoai_le_o_buoc_phuc_hoi_van_DROP_DATABASE` |
| lệnh dọn hỏng / DB nháp còn sót → CRITICAL | `..._lenh_don_dep_hong_...`, `..._db_nhap_con_sot_...` |
| không có file dump → CRITICAL, không `CREATE DATABASE` | `test_run_drill_khong_co_file_dump_bao_va_khong_CREATE_DATABASE` |
| đĩa thiếu → CRITICAL nêu số, không `CREATE DATABASE` | `test_run_drill_dia_thieu_bao_neu_so_va_khong_CREATE_DATABASE` |
| thứ tự `CREATE EXTENSION` < `pre_restore` < `pg_restore` < `post_restore` | `test_run_drill_thu_tu_...` |
| gửi hỏng → 2, gửi được → 1, dry-run → 1 không gửi | `test_main_*` |

### Hai phá thử (nguyên văn) và đối chiếu mã băm

SHA-256 trước: `b5101838b3466ab36fb3648104533976f6bcbc3fc7c3841e79a8f3b1c0108f3e`.

1. Bỏ phép so tập bảng (`if missing:` → `if False:`): **3 test đỏ**
   `FAILED tests/test_restore_drill.py::test_tables_thieu_mot_bang_bao_neu_ten`,
   `FAILED ...::test_tables_phuc_hoi_rong_bao`,
   `FAILED ...::test_run_drill_thieu_bang_bao_neu_ten` (`assert (0 == 1)`, `assert ([])`) — ca "thiếu một bảng" đỏ đúng như yêu cầu.
2. Đổi `-1 == -1` thành "khớp" (thêm `if s == r: continue` và bỏ chốt `COUNT_FAILED`): **2 test đỏ**
   `FAILED tests/test_restore_drill.py::test_counts_khong_doc_duoc_o_CA_HAI_ben_van_bao_khong_phai_khop`,
   `FAILED ...::test_counts_khong_doc_duoc_o_ben_nguon_bao` (`assert (0 == 1)`).
Sau khôi phục: `sha256sum -c` → `scripts/restore_drill.py: OK` (cùng mã băm `b5101838...`), 39 passed.

### Nối lịch + tài liệu

`sched.sh`: case `restore-drill` (qua `run_if_docker_up.sh`), chú thích đầu file, dòng `dung:` in đủ **16** job (`bogus` → 16 nhãn). `DEPLOYMENT.md`: cảnh báo "`pg_restore -l` không chứng minh phục hồi được" kèm bảng bốn dòng số đo ở §6; §9 job 15 **Chủ nhật 04:00** kèm lý do chọn Chủ nhật (sau backup 02:00, backup-check 03:00, trước host-preflight 07:00); bảng Windows có dòng `trading-restore-drill`; các số "15" → "16". `test_deployment_doc.py`: 3 passed.

Chạy thật duy nhất: `restore_drill.py --dry-run --target-db trading` → `LỖI CẤU HÌNH: tên database đích bị cấm: 'trading' ...`, `EXIT=2` (chốt cứng hoạt động, không lệnh Docker nào được gọi).

## Việc 2 — phép kiểm 13 `holidays_confirmed`

`config/config.yaml` thêm `holidays_confirmed_through: '2026-12-31'` (đúng hạn mà chú thích sẵn có nêu; không suy đoán ngày nghỉ) kèm chú thích. `host_preflight.py`: phép kiểm 13, `evaluate(..., today=None)` để tiêm ngày (test **không** dùng `date.today()` thật; sản xuất dùng ngày theo múi giờ VN). HỎNG khi `confirmed < today + 60`; thiếu khoá → **HỎNG** (không BỎ QUA); giá trị không phải ngày → HỎNG; không đọc được `config.yaml` → BỎ QUA kèm lý do. Đọc khoá, **không** đo bằng `max(holidays)`.

Test (`tests/test_host_preflight.py`, +11 → 66): ĐẠT còn 92 ngày; HỎNG còn 59 ngày; biên 60/59; quá hạn; thiếu khoá; giá trị hỏng; BỎ QUA khi không đọc được; và 4 test qua `main --json` trên `config.yaml` tạm (holidays tới 2027-09-02 nhưng xác nhận chỉ tới 2026-10-15 → **vẫn HỎNG**; ngày YAML không đặt trong dấu nháy; thiếu khoá; không có config).

**Phá thử:** đổi phép kiểm sang đo `max(holidays)` → **2 test đỏ**: `FAILED tests/test_host_preflight.py::test_collect_khong_do_bang_max_holidays`, `FAILED ...::test_collect_doc_duoc_ngay_khong_dat_trong_dau_nhay`. Khôi phục: `sha256sum -c` OK, 66 passed.

### Chạy thật `scripts/sched.sh host-preflight` (EXIT=0) — kỳ vọng 6 ĐẠT / 0 HỎNG / 8 BỎ QUA, đúng

```
ĐẠT      TRADING_BACKUP_DIR có mặt, thư mục tồn tại và ghi được         D:/My_Vault_Obsidian/Project/_backups/db
BỎ QUA   crontab có đủ job của sched.sh và CRON_TZ                      không có lệnh crontab trên hệ này
BỎ QUA   /etc/docker/daemon.json giới hạn log (max-size, max-file)      không phải Linux (daemon.json của máy chủ nằm ở /etc/docker)
BỎ QUA   /etc/logrotate.d/trading tồn tại                               không phải Linux (không có logrotate)
BỎ QUA   .env mode 600                                                  không phải Linux (Windows không có mode 600)
ĐẠT      .env không có ký tự \r                                         0 ký tự \r
BỎ QUA   múi giờ hệ thống Asia/Ho_Chi_Minh                              không có timedatectl hay /etc/timezone trên hệ này
BỎ QUA   ufw bật, Postgres 5432 / Grafana 3000 không mở ra ngoài        không có ufw trên hệ này
ĐẠT      đĩa: trống ≥ 10 GB và tổng ≥ 40 GB                             trống 186.1 GB / tổng 449.2 GB
BỎ QUA   scripts/*.sh và .githooks/pre-push thực thi được               không phải Linux (Windows không có bit thực thi)
ĐẠT      config.yaml: real_trading_enabled: false                       false
BỎ QUA   đồng hồ hệ thống đồng bộ                                       không có timedatectl hay /etc/timezone trên hệ này
ĐẠT      mọi cổng Docker publish bind 127.0.0.1                         4 cổng, tất cả bind loopback (nguồn: docker compose config)
ĐẠT      lịch nghỉ được xác nhận tới ≥ hôm nay + 60 ngày                xác nhận tới 2026-12-31, còn 92 ngày

Tổng kết: 6 ĐẠT, 0 HỎNG, 8 BỎ QUA
```

### Điều phải nói rõ về phép kiểm 13

**Nó chỉ chạy khi task `trading-host-preflight` (task thứ 15, Chủ nhật 07:00) đã được tạo** — task đó vẫn nằm ở phía chủ dự án; cho tới lúc đó phép kiểm này chỉ chạy khi có người gọi tay `sched.sh host-preflight`. Task `trading-restore-drill` (Chủ nhật 04:00, tham số `restore-drill`) cũng chưa tạo; **trên máy Windows này Docker Desktop chạy nên nó tạo được**, nhưng mục đích thật là VPS.

## Kiểm chung

`uv run pytest -q` → **1593 passed** (mốc 1543 + 50 mới); `ruff check trading tests scripts` sạch; `docker compose config -q` sạch; `bash -n scripts/sched.sh` sạch; `sched.sh` mode 100755. `gitnexus detect_changes` (MCP, scope `all`): risk **medium**, 30 symbol/section đổi — toàn bộ trong `DEPLOYMENT.md` và `scripts/host_preflight.py`, 4 process bị ảnh hưởng đều là các luồng `main` của chính `host_preflight.py`; không phải chạy `npx gitnexus analyze` (báo có thay đổi, không phải "No changes"), nhưng file mới `restore_drill.py` chưa có trong index.

## Không kiểm được

- **Toàn bộ đường thật của diễn tập** (Docker, `pg_restore`, TimescaleDB pre/post restore, dọn DB) — chỉ kiểm bằng runner giả. Đặc biệt: hành vi thật của `pg_restore` khi extension đã có sẵn (mục 3 ở trên), tính đúng của truy vấn catalog `LIST_TABLES_SQL` trên schema thật, và `DROP DATABASE ... WITH (FORCE)` trên bản Postgres đang chạy (cần PG ≥ 13; image là `latest-pg16`).
- Chỉ đếm bảng `public` loại `r`/`p`; view/continuous aggregate và bảng trong schema khác **không** được đối chiếu.
- Kiểm đĩa đo ổ chứa repo (`shutil.disk_usage(repo)`), giả định cùng ổ với volume Docker (đúng trên VPS một ổ; sai nếu volume nằm ổ khác).
- Hook `.agentignore` chặn lệnh Bash chứa glob dump DB, nên tôi không chạm bản dump thật ở bất kỳ bước nào và viết mã bằng công cụ ghi file thay vì lệnh Bash.

---

## Audit của Claude (30/09/2026, tối)

### A.1. Kết luận: NHẬN, kèm một lỗi thiết kế của chính brief — sửa ở đợt 137.

Code làm đúng brief. Nhưng lần diễn tập thật đầu tiên cho thấy **quy tắc so số dòng mà Claude viết trong brief là sai**. Agent không có lỗi ở phần này.

### A.2. Lần diễn tập thật đầu tiên (Claude chạy, như brief quy định)

**[A] Bản dump TỐT, chạy qua `scripts/sched.sh restore-drill --dry-run` lúc 20:09 (140 giây):**

```
[CRITICAL] Bảng account_balance_snapshot phục hồi thiếu dòng: nguồn=11,817, phục hồi=11,423 (96.67% < 99%)
[CRITICAL] Bảng account_buying_power phục hồi thiếu dòng: nguồn=34,218, phục hồi=33,036 (96.55% < 99%)
[CRITICAL] Bảng account_nav_snapshot phục hồi thiếu dòng: nguồn=11,407, phục hồi=11,013 (96.55% < 99%)
[CRITICAL] Bảng account_position_snapshot phục hồi thiếu dòng: nguồn=33,665, phục hồi=32,483 (96.49% < 99%)
[CRITICAL] Bảng derivative_balance_snapshot phục hồi thiếu dòng: nguồn=5,967, phục hồi=5,765 (96.61% < 99%)
[CRITICAL] Bảng derivative_margin_snapshot phục hồi thiếu dòng: nguồn=5,967, phục hồi=5,765 (96.61% < 99%)
EXIT=1
```

Đây là **6 báo động oan** trên một bản sao lưu tốt. Nguyên nhân: brief giả định "Chủ nhật không có phiên nên nguồn gần như không đổi". Giả định đó đo trên mỗi bảng `bars`. Các bảng snapshot tài khoản được ghi **24/7**: `account_nav_snapshot` tăng 22 dòng/giờ; riêng khung 02:00–04:00 Chủ nhật 27/09 có 48 dòng. Dump chụp lúc 02:00 nên đến 20:09 đã trôi 18 giờ, tức khoảng 3,5%.

Đúng 04:00 Chủ nhật thì độ trôi khoảng 0,4% nên vẫn qua. Nhưng **kết quả phụ thuộc vào giờ chạy**: task chạy bù trễ vài giờ là báo oan, và bảng nhỏ hoặc mới thì hỏng sớm hơn. Ngược lại, băng 1% trên bảng lớn lại **để lọt** mất mát nhỏ hơn 1% (với `bars` là khoảng 9.000 dòng). So với nguồn đang sống là sai về cấu trúc. Đợt 137 thay bằng **bản kê số dòng chụp lúc dump**.

**[B] Đối chứng âm tính: bản dump thật cắt còn 90%:**

```
[CRITICAL] pg_restore thất bại (exit 1): pg_restore: error: could not read from input file: end of file
```

Bị bắt sau 53 giây. Đây là ca mà ba phép kiểm hằng đêm đều để lọt.

**Dọn dẹp:** sau cả hai lần chạy chỉ còn `postgres, template0, template1, trading, trading_test`; `/tmp` trong container chỉ còn `test.dump`, có từ trước.

**Rủi ro "extension already exists" mà agent nêu: KHÔNG xảy ra.** Ở [A], `pg_restore` qua sạch sau `CREATE EXTENSION`. Agent nêu ra đúng cách: không đoán, chỉ ghi là rủi ro cho lần chạy đầu.

### A.3. Phá thử của Claude

- Bỏ dọn dẹp trong `finally`: 2 test đỏ (`test_run_drill_lenh_don_dep_hong_thi_co_CRITICAL`, `test_run_drill_db_nhap_con_sot_sau_don_dep_bao`). Tốt.
- **Bỏ nhánh `rc != 0` của `judge_pg_restore`: 39/39 vẫn XANH.** Mọi ca hỏng trong test đều kèm dòng `error:` ở stderr, nên nhánh xét stderr gánh luôn phần việc. Ca **exit ≠ 0 với stderr rỗng** (pg_restore bị giết vì OOM, exit 137 — container này từng có tiền sử [[postgres-bo-nho-vuot-gioi-han-container]]) không có test ghim. Code hiện tại xử lý ca đó **đúng**; chỉ thiếu test. Giao đợt 137.

Khôi phục xong, hash trùng `b5101838b3466ab3`.

### A.4. Ba điểm agent nêu — cả ba agent đúng, brief sai

- `--dry-run` mặc định sẽ khiến cron không bao giờ gửi cảnh báo. Đồng ý với cách của agent.
- Phép kiểm 13 chuyển HỎNG từ **02/11**, không phải 01/11: `2026-12-31 < hôm nay + 60` nghĩa là hôm nay > 01/11. Claude tính lệch một ngày.
- Dòng `host-preflight` trong `sched.sh` bị mất dấu `\` xuống dòng từ đợt 133. Chạy vẫn đúng; giao đợt 137 cho gọn.

### A.5. Số liệu

`sched.sh host-preflight`: **6 ĐẠT / 0 HỎNG / 8 BỎ QUA**, phép 13 "xác nhận tới 2026-12-31, còn 92 ngày". `ruff` sạch; **1.593 passed**.

