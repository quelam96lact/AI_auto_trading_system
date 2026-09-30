# Báo cáo đợt 137 — diễn tập so với BẢN KÊ SỐ DÒNG chụp lúc dump

Không commit, không push, không tạo scheduled task, không restart container, không sửa `.env` / `docker-compose.yml` / `verify_backup_restore.py`. **Chưa chạy `restore_drill.py` thật** (brief cấm): đường diễn tập thật với bản kê **chưa chạy** — Claude sẽ chạy. Đã chạy `scripts/sched.sh backup` **đúng một lần** (được phép).

## 0. Hai phép đo tiền đề (chạy lại 30/09, dán nguyên văn)

`timescaledb_information.jobs`:
```
 job_id |           application_name           |             proc_name             | hypertable_name | schedule_interval
--------+--------------------------------------+-----------------------------------+-----------------+-------------------
      1 | Telemetry Reporter [1]               | policy_telemetry                  |                 | 24:00:00
      3 | Job History Log Retention Policy [3] | policy_job_stat_history_retention |                 | 06:00:00
(2 rows)
```
`pg_extension`: `plpgsql timescaledb` (không có pg_cron). Lệnh xoá dòng trong code (`grep -rniE "delete\s+from|truncate\b|drop_chunks|\.delete\("` trên `trading/` + `scripts/`, bỏ `.probe_event_loop_block.py` và `check_orders_hygiene.py` vốn chỉ **in** SQL):
```
scripts/build_derivative_continuous_series.py:374:  "DELETE FROM bars_derivative WHERE symbol = %s",
scripts/merge_bars_daily_chunks.py:120:             "DELETE FROM bars_daily WHERE symbol = %s AND ts = %s",
```
Cả hai là script chạy tay (cộng `.probe_event_loop_block.py`). **Tiền đề "không job định kỳ nào xoá dòng" đúng**, nên `phục_hồi >= bản_kê` hợp lệ. Không có `drop_chunks`/`add_retention_policy` nào.

## 1. Việc 1 — bản kê số dòng

### `scripts/backup_db.sh`

Ngay **trước** `pg_dump`: truy vấn catalog (`pg_class`/`pg_namespace`, `nspname = 'public'`, `relkind IN ('r','p')`, đếm bằng `query_to_xml` nên **không có danh sách viết cứng**) → ghi `trading_<ts>.counts` (`ten_bang<TAB>so_dong`) qua file `.tmp` rồi `mv`. `trap ... EXIT` xoá `.counts` và `.tmp` bất cứ khi nào thoát trước khi dump được xác minh (dump hỏng, `pg_restore -l` hỏng, hoặc chính bản kê lỗi). Dọn theo hạn giữ đã thêm `trading_*.counts`. Chú thích đầu file nêu lý do.

### Chạy thật `scripts/sched.sh backup` (một lần, EXIT=0)

```
Backup written to D:/My_Vault_Obsidian/Project/_backups/db/trading_20260930_221525.dump (100M) + row-count statement D:/My_Vault_Obsidian/Project/_backups/db/trading_20260930_221525.counts
Pruned backups older than 14 days
```
`ls -l`:
```
-rw-r--r-- 1 quelam 197121       670 Sep 30 22:15 trading_20260930_221525.counts
-rw-r--r-- 1 quelam 197121 104680203 Sep 30 22:16 trading_20260930_221525.dump
```
Bản kê (mtime 22:15) chụp **trước** dump (22:16), đúng thứ tự. `wc -l` của `.counts` = **32**. Năm dòng đầu (`cat -A`, tab hiện là `^I`):
```
account_balance_snapshot^I11865$
account_buying_power^I34362$
account_nav_snapshot^I11455$
account_position_snapshot^I33809$
account_sync_log^I2$
```
Số bảng: `.counts` = **32**; `LIST_TABLES_SQL` chạy trên `trading` = **32**, và `diff` tên bảng hai bên **giống hệt**. Mọi dòng khớp `^[^\t]+\t[0-9]+$` (0 dòng hỏng). Không có `.tmp` sót. Kiểm thêm (chỉ đọc): `read_counts_file(find_latest_dump(...))` trên cặp thật đọc được 32 bảng (`bars = 936217`, `orders = 20`).

### Test `backup_db.sh` bằng `docker` giả (`tests/test_backup_db_counts.py`, 7 test — có sẵn khung `tests/test_run_if_docker_up.py`, nên dùng cùng cách: `docker` + `pg_restore` giả trên PATH)

| Test | Kiểm |
|---|---|
| `test_thanh_cong_co_dump_va_ban_ke_cung_ten_goc` | có `.dump` + `.counts` cùng stem, nội dung đúng, không `.tmp` |
| `test_ban_ke_duoc_chup_TRUOC_pg_dump` | lệnh `psql` đứng trước `pg_dump` |
| `test_ban_ke_liet_ke_tu_catalog_khong_danh_sach_cung` | truy vấn có `pg_class`, `relkind IN ('r','p')`, `nspname = 'public'` |
| `test_dump_hong_khong_con_ban_ke` | dump hỏng → không còn `.counts` |
| `test_xac_minh_pg_restore_hong_khong_con_dump_lan_ban_ke` | `pg_restore -l` hỏng → không còn `.dump` lẫn `.counts` |
| `test_lap_ban_ke_hong_thi_khong_pg_dump_...` | lập bản kê lỗi → không `pg_dump`, không bản kê viết dở |
| `test_ban_ke_cu_hon_han_giu_bi_xoa_ban_moi_thi_giu` | `.counts` cũ 20 ngày bị xoá, 1 ngày được giữ |

Phá thử phụ: gỡ `trap` → 3 test đỏ (`test_dump_hong_khong_con_ban_ke`, `test_xac_minh_pg_restore_hong_...`, `test_lap_ban_ke_hong_...`); bỏ `.counts` khỏi lệnh dọn → `test_ban_ke_cu_hon_han_giu_bi_xoa_ban_moi_thi_giu` đỏ. Khôi phục, 7 passed.

### `scripts/restore_drill.py`

Đọc bản kê **cùng tên gốc** (`trading_<ts>.dump` → `trading_<ts>.counts`) **trước khi đụng DB** (thiếu/rỗng/dòng hỏng → `CountsError` → CRITICAL, `runner` không nhận lệnh nào). Không có đường lui về nguồn sống. Tập bảng lấy từ bản kê; quy tắc số dòng `phục_hồi >= bản_kê` (không dung sai); `-1` ở bất kỳ bên nào vẫn CRITICAL (`COUNT_FAILED` giữ nguyên). Đã xoá `MIN_RATIO` và mọi chú thích về băng 99%/Chủ nhật, thay bằng chú thích giải thích bản kê và dẫn số đo. **Diễn tập không còn đếm dòng trên `trading`**, chỉ kiểm `trading` vẫn tồn tại sau khi dọn.

### Bảng test (`tests/test_restore_drill.py`, 39 → 57 test)

| Ca | Test |
|---|---|
| bằng bản kê → IM | `test_counts_bang_ban_ke_IM`, `test_run_drill_bang_ban_ke_IM_va_da_don_dep` |
| nhiều hơn → IM | `test_counts_nhieu_hon_ban_ke_IM`, `test_run_drill_nhieu_hon_ban_ke_IM` |
| ít hơn đúng 1 dòng → BÁO nêu tên + hai số | `test_counts_it_hon_dung_1_dong_...`, `test_counts_bang_lon_it_hon_1_dong_tren_936k_van_bao`, `test_run_drill_it_hon_dung_1_dong_...`, `test_run_drill_bang_lon_thieu_dung_1_dong_bao` |
| không có bản kê → BÁO, không `CREATE DATABASE` | `test_run_drill_khong_co_ban_ke_bao_va_khong_cham_vao_DB` (`runner.calls == []`) |
| bản kê có dòng hỏng → BÁO, không bỏ qua | `test_run_drill_ban_ke_co_dong_hong_...`, `test_read_counts_dong_hong_nem_loi[6 dạng]`, `test_read_counts_file_rong_nem_loi` |
| không đếm trên `trading` | `test_run_drill_khong_dem_dong_tren_database_trading` |
| **exit 137 stderr rỗng** → BÁO | `test_pg_restore_exit_137_stderr_rong_van_bao`, `test_run_drill_pg_restore_bi_giet_137_stderr_rong_bao_va_don_dep`, `test_pg_restore_exit_khac_0_stderr_chi_co_canh_bao_van_bao` |
| chọn đúng bản kê của dump mới nhất | `test_run_drill_dung_ban_dump_moi_nhat_va_ban_ke_cung_ten` |

Các test đợt 136 còn lại giữ nguyên hoặc chỉnh cho đúng quy tắc mới (xem mục "Sửa test" dưới đây).

### Phá thử (nguyên văn) và đối chiếu mã băm

SHA-256 trước: `3f1feeaa289deb05456707dc393c896e987011bc325fad45f463a054fa7179bf`.

- **A. `>=` thành băng 99% cũ** (`elif r < s:` → `elif r < 0.99 * s:`): `FAILED tests/test_restore_drill.py::test_counts_bang_lon_it_hon_1_dong_tren_936k_van_bao` (`assert (0 == 1)`), 1 failed / 55 passed. (Lúc đó chưa có `test_run_drill_bang_lon_thieu_dung_1_dong_bao`; bổ sung sau để ca cấp `run_drill` cũng đỏ.)
- **B. Thiếu bản kê thì rơi về nguồn sống** (thay nhánh báo CRITICAL bằng cho chạy tiếp): `FAILED ...::test_run_drill_khong_co_ban_ke_bao_va_khong_cham_vao_DB`, `FAILED ...::test_run_drill_ban_ke_co_dong_hong_bao_khong_bo_qua` (`assert (0 == 1)`), 2 failed / 54 passed.
- **C. Bỏ nhánh `rc != 0` trong `judge_pg_restore`** (lỗ test đợt 136): `FAILED ...::test_pg_restore_exit_137_stderr_rong_van_bao`, `FAILED ...::test_pg_restore_exit_khac_0_stderr_chi_co_canh_bao_van_bao`, `FAILED ...::test_run_drill_pg_restore_bi_giet_137_stderr_rong_bao_va_don_dep` (`assert 0 == 1`, `AssertionError: assert []`), 3 failed / 53 passed — **đúng như brief yêu cầu**, lỗ đợt 136 đã bịt.
Sau khôi phục: `sha256sum -c` → `scripts/restore_drill.py: OK` (cùng mã băm), 57 passed.

### Sửa test đợt 136 vì quy tắc đổi (nói rõ, không lặng lẽ)

`test_counts_lech_0_01_phan_tram_IM` (đợt 136 khẳng định lệch 0,01% là IM) **mâu thuẫn trực tiếp** với quy tắc mới (thiếu 1 dòng là BÁO) nên được thay bằng `test_counts_bang_lon_it_hon_1_dong_tren_936k_van_bao`. `test_counts_khong_doc_duoc_o_ben_nguon_bao` bỏ vì "bên nguồn" giờ là bản kê (không thể là `-1`; dòng hỏng đã bị `read_counts_file` chặn). `FakeRunner` không còn giả lập truy vấn trên `trading`. `test_run_drill_moi_thu_khop...` và các ca cũ được giữ, chỉnh helper `_dump` để tạo kèm `.counts`.

### `DEPLOYMENT.md`

Chỉ sửa đúng chỗ đợt 136 viết: (1) cảnh báo §6 nay nói đối chiếu với **bản kê `.counts` chụp lúc dump**; (2) mô tả `backup_db.sh` nêu bản kê `.counts`, hạn dọn phủ `.counts`, và quy tắc `phục_hồi >= bản_kê`; (3) chú thích cron job 15 bỏ băng 99% và lý do "độ trôi", giờ **Chủ nhật 04:00 giữ nguyên**, lý do đổi thành "ít tải". `test_deployment_doc.py`: 3 passed.

## 2. Việc 2 — dòng `host-preflight` trong `sched.sh`

Tách lại thành hai dòng có `\` như các nhánh khác. `bash -n scripts/sched.sh` sạch; `scripts/sched.sh host-preflight` thật → `EXIT=0`, `Tổng kết: 6 ĐẠT, 0 HỎNG, 8 BỎ QUA` (đúng kỳ vọng).

## 3. Kiểm chung

`uv run pytest -q` → **1618 passed** (mốc 1593 + 25); `ruff check trading tests scripts` sạch; `test_deployment_doc.py` 3 passed; `bash -n` sạch cả `backup_db.sh` lẫn `sched.sh`; `git ls-files -s`: cả hai **100755**. `gitnexus detect_changes` (MCP, scope `all`): risk **low**, 62 symbol/section đổi, **0 process bị ảnh hưởng**, chỉ nằm trong `DEPLOYMENT.md`, `restore_drill.py`, `test_restore_drill.py` (báo có thay đổi nên không phải `npx gitnexus analyze`; index chưa có `read_counts_file`/`CountsError` mới).

## 4. Chỗ brief mơ hồ / quyết định tôi đã đưa ra

1. **Lập bản kê lỗi thì làm gì.** Brief chỉ nói "dump hỏng → xoá bản kê". *Ruling:* lập bản kê lỗi (hoặc rỗng) là **lỗi cứng** (`set -e`, thoát ≠ 0, không `pg_dump`, không để lại file). Lý do: `psql` cùng Postgres với `pg_dump` nên hỏng thật thường hỏng cả hai; lỗi im lặng sẽ thành dump không có bản kê và chỉ lộ ra ở lần diễn tập Chủ nhật. *Cái giá nếu sai:* một đêm không có dump vì một lỗi SQL riêng của bản kê. Ngược lại có thể đổi thành "cảnh báo rồi vẫn dump".
2. **Bản kê đếm từng bảng tuần tự, không trong một snapshot chung.** Vẫn giữ đúng tính chất cần thiết: mọi lần đếm xảy ra **trước** snapshot của `pg_dump`, nên với mỗi bảng chỉ có dòng được thêm.
3. **Bảng tạo thêm giữa hai mốc** có ở bản phục hồi mà không có trong bản kê: bị bỏ qua có chủ ý (chỉ bảng có trong bản kê mới bị đòi).
4. **Chưa có gì báo khi một dump thiếu `.counts`** ngoài lần diễn tập Chủ nhật (và `backup-check` không nhìn `.counts`). Đề xuất (ngoài phạm vi, chưa làm): cho `backup_check.py` cảnh báo khi dump mới nhất không có bản kê đi kèm.
5. **Các dump cũ (trước đợt 137) không có `.counts`**; diễn tập luôn lấy dump **mới nhất**, nên chạy được với bản `trading_20260930_221525` vừa tạo, và các đêm sau tự có bản kê.
6. **Hại phụ trong lúc làm:** công cụ sửa file đã đổi `backup_db.sh` sang CRLF (`git ls-files --eol` báo `w/crlf`, `attr eol=lf`); tôi đã đổi lại LF (`w/lf`, 0 ký tự `\r`) và kiểm lại ở cuối (`i/lf w/lf` cho `backup_db.sh` và `sched.sh`). Nên soát lại `.sh` nếu hook định dạng chạy sau.

## 5. Không kiểm được

- **Toàn bộ đường diễn tập thật** (Docker + `pg_restore` + TimescaleDB pre/post restore + dọn DB) **chưa chạy**; kể cả hành vi thật của `pg_restore` khi extension đã có sẵn (rủi ro đã nêu ở báo cáo đợt 136 vẫn còn).
- Đường `sched.sh backup` chỉ chạy trên Windows/Git Bash + Docker Desktop; **chưa chạy trên Ubuntu/cron** (đã thêm `tr -d '\r'` cho chắc; vô hại trên Linux).
- Test `backup_db.sh` dùng `docker` giả nên **không thực thi** câu SQL `query_to_xml`; bằng chứng câu SQL đúng là lần chạy thật ở mục 1 (32/32 bảng, tên khớp).

---

## Audit của Claude (30/09/2026, 22:20)

### A.1. Kết luận: ĐẠT, nhận toàn bộ.

### A.2. Diễn tập thật — Claude chạy, đúng lệnh lịch gọi

**[A] `scripts/sched.sh restore-drill --dry-run`, bản `trading_20260930_221525.dump` (bản do agent tạo):** `EXIT=0`. **32/32 bảng khớp tuyệt đối với bản kê**, ví dụ `bars` 936.217 = 936.217, `bars_daily` 2.986.388 = 2.986.388, `orders` 20 = 20. Sáu bảng snapshot tài khoản từng báo oan ở đợt 136 giờ khớp từng dòng. Lỗi cấu trúc đã hết.

(Ba dòng CRITICAL ở đầu `logs/restore-drill.log` là của lần chạy đợt 136 lúc 20:09 — log ghi nối tiếp.)

Ba đối chứng âm tính trên **bản sao** trong thư mục nháp:

| Ca | Kết quả | Thời gian |
|---|---|---|
| **[B]** Bản kê `orders` bị sửa 20 → 21 | `Bảng orders phục hồi thiếu dòng: bản kê=21, phục hồi=20 (thiếu 1)` | 94 giây |
| **[C]** Dump không có bản kê | `không có bản kê số dòng ... FileNotFoundError`, không tạo DB | 0 giây |
| **[D]** Dump cắt 90% + bản kê đúng | `pg_restore thất bại (exit 1): ... end of file` | 48 giây |

Ca [B] là ca băng 99% cũ sẽ để lọt: **thiếu đúng một dòng** trên bảng `orders` giờ bị bắt.

Sau cả bốn lần chạy: DB chỉ còn `postgres, template0, template1, trading, trading_test`; `/tmp` trong container chỉ còn `test.dump` có từ trước. **Rủi ro "extension already exists" không xảy ra** — xác nhận lần thứ hai.

### A.3. Phá thử của Claude

Cho bộ đọc bản kê **lặng lẽ bỏ qua** dòng hỏng thay vì ném lỗi → **7 test đỏ** (6 ca tham số của `test_read_counts_dong_hong_nem_loi` cùng `test_run_drill_ban_ke_co_dong_hong_bao_khong_bo_qua`). Hash khôi phục trùng `3f1feeaa289deb05`.

`backup_db.sh` và `sched.sh`: `i/lf w/lf`, mode `100755`; `bash -n` sạch. `ruff` sạch; **1.618 passed**.

### A.4. Các điểm agent nêu

- **Đổi hai test của đợt 136**: đúng. Test "lệch 0,01% là IM" mâu thuẫn trực tiếp với quy tắc mới.
- **Lập bản kê lỗi là lỗi cứng, cả đêm không có dump**: Claude **không đồng ý giữ nguyên**. Bản kê là công cụ kiểm; bản dump mới là thứ cần giữ. Để lỗi của công cụ kiểm giết mất bản sao lưu là đảo ngược thứ tự ưu tiên. Giao đợt 138: bản kê lỗi thì cảnh báo và vẫn dump.
- **Không gì báo khi dump thiếu `.counts`** ngoài diễn tập Chủ nhật: đúng, và nó đi cặp với điểm trên. Giao đợt 138: `backup-check` báo khi bản dump mới nhất thiếu bản kê.
- **CRLF trên `backup_db.sh`**: đã kiểm, sạch.

