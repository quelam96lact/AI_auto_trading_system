# Báo cáo đợt 138 — bản kê hỏng không được giết bản sao lưu; phải có người thấy khi thiếu bản kê

Không commit, không push, không tạo scheduled task, không restart container, không sửa `.env`. **Không** chạy `restore_drill.py`, **không** chạy `sched.sh backup` (đợt 137 đã có bản thật). Không đụng `restore_drill.py` (hành vi "thiếu bản kê → CRITICAL" giữ nguyên). `gitnexus impact` trên `backup_check.main`: **LOW**, 0 process.

## Việc 1 — `backup_db.sh`: bản kê lỗi thì cảnh báo và vẫn dump

Lệnh lập bản kê nay nằm trong `if MSYS_NO_PATHCONV=1 docker compose exec ... psql ... | tr -d '\r' > "$tmp" && [ -s "$tmp" ]; then mv ...; else ...; fi`. `if` che `set -e` và `pipefail` **cho đúng lệnh đó**, không gỡ chúng của cả file. Nhánh `else`: in `WARNING: could not build the row-count statement ...; continuing with the dump WITHOUT <file>.` ra stderr, `rm -f .counts.tmp`, **không** tạo `.counts`, rồi chạy tiếp `pg_dump` + xác minh. Trap `cleanup_on_failure` giữ nguyên: dump hoặc xác minh hỏng vẫn xoá `.counts`. Mã thoát không đổi (0 nếu dump và xác minh đạt). Dòng thông báo cuối chỉ nhắc `.counts` khi file tồn tại; thiếu thì ghi "WITHOUT a row-count statement". Chú thích đầu file nêu rõ chiều ngược lại không đúng (dump hỏng xoá bản kê; bản kê hỏng không xoá dump).

### Test (`tests/test_backup_db_counts.py`, 7 → 9 test; dùng `docker` giả có sẵn, thêm nhánh `FAKE_PSQL_EMPTY`)

| Ca | Test | Kết quả kỳ vọng |
|---|---|---|
| `psql` lập bản kê lỗi | `test_lap_ban_ke_loi_van_dump_canh_bao_khong_giet_ban_sao_luu` | **có** `.dump`, không `.counts`, không `.tmp`, mã thoát 0, stderr có `WARNING`, log có `pg_dump` |
| bản kê rỗng | `test_ban_ke_rong_van_dump_canh_bao_khong_de_lai_file_rong` | như trên |
| bản kê lỗi **và** dump hỏng | `test_ban_ke_loi_roi_dump_hong_van_thoat_khac_0_va_khong_con_ban_ke` | thoát ≠ 0, không `.counts` |
| dump hỏng | `test_dump_hong_khong_con_ban_ke` (đợt 137, **không sửa**) | vẫn xanh |
| `pg_restore -l` hỏng | `test_xac_minh_pg_restore_hong_...` (đợt 137, không sửa) | vẫn xanh |

## Việc 2 — `backup_check.py`: báo khi `.dump` mới nhất thiếu bản kê

Hàm thuần mới `evaluate_counts_statement(latest_file, counts_size)` cạnh `evaluate_orderbook_backup`, theo đúng khuôn đợt 135. `.dump` mới nhất mà `.counts` **cùng tên gốc** không tồn tại hoặc rỗng → `[CRITICAL] Bản sao lưu <tên> không có bản kê số dòng — diễn tập phục hồi Chủ nhật sẽ không kiểm được nó`. **Chỉ** kiểm tồn tại và khác rỗng (không phân tích nội dung). `.sql.gz` không bị đòi. Không đổi ngưỡng 23 giờ, 80 MB, hay logic sổ lệnh. Trong `main`: cờ `--no-counts` (mặc định **có** kiểm), tìm `.counts` bằng `latest_p.with_suffix(".counts")` của đúng bản dump mới nhất.

### Test (`tests/test_backup_check.py`, +11)

| Ca | Test |
|---|---|
| `.dump` mới có `.counts` → IM | `test_counts_dump_co_ban_ke_IM`, `test_main_dump_moi_co_ban_ke_thi_IM` |
| `.dump` mới **thiếu** `.counts` → BÁO nêu tên | `test_counts_dump_thieu_ban_ke_BAO_neu_ten`, `test_main_dump_moi_thieu_ban_ke_PHAI_bao` |
| `.counts` rỗng → BÁO | `test_counts_dump_ban_ke_rong_BAO`, `test_main_ban_ke_rong_PHAI_bao` |
| `.sql.gz` mới nhất không có bản kê → IM | `test_counts_sql_gz_cu_khong_co_ban_ke_IM`, `test_main_sql_gz_moi_nhat_khong_ban_ke_IM` |
| bản kê của dump **cũ** không cứu dump mới | `test_main_ban_ke_cua_dump_CU_khong_cuu_dump_moi` |
| không có bản sao lưu nào → không báo thêm (đã có báo khác) | `test_counts_khong_co_ban_sao_luu_nao_khong_bao_them` |

### Hai test có sẵn buộc phải chỉnh (nói rõ vì sao)

Cùng loại xung đột với đợt 135: thư mục chỉ có dump, không có `.counts`, nay **đúng là** trường hợp cần báo.
1. `test_main_dry_run_silent_on_valid_dir` (đợt 131): thêm đúng một đối số `"--no-counts"` vào dòng args (`...,"--no-orderbook"` → `...,"--no-orderbook","--no-counts"`). Ý định của test là logic DB, không đổi; logic và ngưỡng DB không bị sửa.
2. `test_main_co_ca_dump_va_ban_so_lenh_moi_thi_IM` (đợt 135, của tôi): thêm một dòng tạo `trading_20260929_020000.counts` để nó vẫn là ca "mọi thứ đủ → IM" thật, thay vì thêm cờ.
Ngoài ra `ruff format` (hook) giãn cách lại vài dòng trong chính các test đợt 135 tôi đã viết; không có test sẵn có nào khác đổi hành vi.

Cũng buộc phải **thay** một test đợt 137: `test_lap_ban_ke_hong_thi_khong_pg_dump_va_khong_con_ban_ke_viet_do` khẳng định `psql` lỗi ⇒ thoát ≠ 0 và **không** `pg_dump` — **mâu thuẫn trực tiếp** với Việc 1. Brief chỉ nêu test "dump hỏng" là phải giữ; test này không nằm trong danh sách đó nên tôi thay bằng hai test mới ở bảng trên (nêu trong docstring).

## Phá thử (nguyên văn) và đối chiếu mã băm

SHA-256 trước: `backup_db.sh` `0fdfa0013ae34eb79c569e1d9075bb724aee56c96881c8e24b1da81f4405ca7c`, `backup_check.py` `d5b7508e78c8db40f3bde9fceeb069a03ed6aab744ad6e7cc0667425032bd8fe`.

1. **Trả `backup_db.sh` về lỗi cứng** (thêm `exit 1` ở nhánh `else`): `FAILED tests/test_backup_db_counts.py::test_lap_ban_ke_loi_van_dump_canh_bao_khong_giet_ban_sao_luu` (`assert 1 == 0`), `FAILED ...::test_ban_ke_rong_van_dump_canh_bao_khong_de_lai_file_rong` (`assert 1 == 0`) — 2 failed / 7 passed.
2. **Bỏ kiểm `.counts` trong `backup_check.py`** (`if not counts_size:` → `if False:`): 5 failed / 31 passed — `test_counts_dump_thieu_ban_ke_BAO_neu_ten`, `test_counts_dump_ban_ke_rong_BAO`, `test_main_dump_moi_thieu_ban_ke_PHAI_bao`, `test_main_ban_ke_rong_PHAI_bao`, `test_main_ban_ke_cua_dump_CU_khong_cuu_dump_moi` (`assert 0 == 1`).
Khôi phục: `sha256sum -c` → `scripts/backup_db.sh: OK`, `scripts/backup_check.py: OK`, 45 passed. (Sau đó tôi còn sửa hai lỗi lint nhỏ trong `backup_check.py`/`test_backup_check.py` nên mã băm cuối khác mã băm trên; đã chạy lại toàn bộ test.)

## Chạy thật `scripts/sched.sh backup-check --dry-run` trên `_backups/db`

```
-rw-r--r-- 1 quelam 197121       670 Sep 30 22:15 trading_20260930_221525.counts
-rw-r--r-- 1 quelam 197121 104680203 Sep 30 22:16 trading_20260930_221525.dump
(các dump cũ trước đợt 137: trading_20260930_020002, ..._20260929_235344, ..._20260929_215253 — không có .counts, đúng)

EXIT=0
2026-09-30 23:14:35 backup-check start
EXIT=0
```
Bản mới nhất `trading_20260930_221525.dump` có `.counts` (670 byte) → **không cảnh báo, EXIT=0**. Chưa có bản 02:00 mới hơn tại thời điểm chạy (23:14), nên không có bản nào khác cần dán `ls -l`.

## Kiểm chung

`bash -n scripts/backup_db.sh` sạch; `git ls-files --eol scripts/backup_db.sh` = `i/lf w/lf`, `git ls-files -s` = `100755` (đã kiểm sau **mọi** lần sửa, kể cả lần cuối). `ruff check trading tests scripts` sạch. `uv run pytest -q` → **1630 passed** (mốc 1618 + 12). `test_deployment_doc.py` 3 passed. `gitnexus detect_changes` (MCP, scope `all`): risk **low**, 17 symbol/section, **0 process bị ảnh hưởng**, chỉ nằm trong 5 file đã sửa.

`DEPLOYMENT.md`: hai chỗ — mô tả `backup_db.sh` thêm câu bản kê lỗi chỉ cảnh báo và ai là người báo; chú thích job 11 nêu `backup-check` đòi `.counts` cho `.dump` mới nhất.

## Brief sai / mơ hồ

- Brief nói "test đợt 137 phải còn xanh, không sửa" nhưng một test đợt 137 (`psql` lỗi ⇒ không `pg_dump`) **phải thay** vì nó khẳng định đúng hành vi bị đảo ngược; xem trên. Tương tự "mọi test sẵn có của `backup_check` xanh, không sửa dòng nào" **không thể** giữ (một test đợt 131, một test đợt 135) — cùng loại lỗi brief đã gặp ở đợt 135.

## Không kiểm được

- Nhánh `WARNING` chỉ được kiểm bằng `docker` giả; chưa thử làm `psql` thật lỗi trên DB thật (không tạo lỗi giả trên hệ thống sống).
- Chưa thấy một bản dump **đêm** (02:00) thật do `backup_db.sh` mới sinh ra kèm `.counts`; bản duy nhất có `.counts` là bản chạy tay ở đợt 137. Lần 02:00 tới sẽ là bằng chứng đầu tiên trong vận hành (nhưng nhớ rằng task `trading-backup` chạy `sched.sh backup` trên máy này, còn Ubuntu/cron chưa từng chạy).
- Chưa kiểm trên Ubuntu/cron.

---

## Audit của Claude (01/10/2026, 06:10)

### A.1. Kết luận: ĐẠT, nhận toàn bộ.

### A.2. Bằng chứng thật đầu tiên từ lịch đêm qua

- Job sao lưu 02:00 (lịch thật) sinh cặp `trading_20261001_020002.dump` (104.684.265 byte) + `.counts` (670 byte, **32 dòng**, đúng dạng `ten<TAB>so`).
- Job `backup-check` 03:00 (lịch thật): `EXIT=0`, không cảnh báo.
- Chạy lại `sched.sh backup-check --dry-run` lúc 06:06: `EXIT=0`.

### A.3. Nhánh WARNING chạy TRỌN ĐƯỜNG THẬT — thứ agent ghi là "chưa kiểm được"

Claude đặt một `docker` giả **chỉ làm hỏng lệnh `psql`**. Mọi lệnh khác (`pg_dump`, `docker compose cp`, `pg_restore -l`) đi thẳng vào Docker thật. Rồi chạy `backup_db.sh` vào một thư mục nháp:

```
shim: psql bi lam hong co y
WARNING: could not build the row-count statement (psql failed or listed no tables); continuing with the dump WITHOUT .../trading_20261001_060758.counts.
Backup written to .../trading_20261001_060758.dump (100M) WITHOUT a row-count statement (see WARNING above)
ma thoat=0
```

Thư mục nháp chỉ có `.dump` (104.688.701 byte), **không** có `.counts` và **không** có `.counts.tmp`. Chạy `backup_check.py` trên đúng thư mục đó:

```
[CRITICAL] Bản sao lưu trading_20261001_060758.dump không có bản kê số dòng — diễn tập phục hồi Chủ nhật sẽ không kiểm được nó
```

Hai nửa của đợt này khớp nhau trên đường thật: lỗi bản kê **không** giết bản sao lưu, và **có** người báo.

(Lần thử đầu của Claude hỏng vì lỗi của chính script kiểm: đường dẫn `C:/...` trong `PATH` có dấu `:` nên shim bị bỏ qua, psql chạy bình thường và bản kê vẫn được tạo. Claude phát hiện vì đầu ra ghi "+ row-count statement" trái với kỳ vọng; đã chạy lại với `/c/...`.)

Đối chứng âm tính trên bản dump thật 02:00 chép sang thư mục không có `.counts`: báo đúng CRITICAL, mã thoát 1.

### A.4. Các test cũ bị sửa: chấp nhận

Diff test cũ chỉ đổi một dòng args (thêm `--no-counts`) và một dòng bị hook định dạng xuống dòng lại. Test đợt 137 "psql lỗi thì không pg_dump" mâu thuẫn trực tiếp với Việc 1 nên phải thay. Brief không lường trước — lỗi brief, lần thứ hai trong bốn đợt.

### A.5. Số liệu

`backup_db.sh`: `i/lf w/lf`, mode `100755`. Thư mục nháp đã xoá; `/tmp` trong container chỉ còn `test.dump` có từ trước. `ruff` sạch; **1.630 passed**.

