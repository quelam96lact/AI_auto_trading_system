# Brief đợt 138 — bản kê hỏng không được giết bản sao lưu; và phải có người thấy khi thiếu bản kê

Việc nhỏ, hai nửa của cùng một điểm. Cả hai đều do agent đợt 137 tự nêu ra; Claude đồng ý.

## Vì sao

Ở đợt 137, `backup_db.sh` coi **lập bản kê lỗi là lỗi cứng**: thoát khác 0 và **không `pg_dump`**. Bản
kê chỉ là công cụ để *kiểm* bản sao lưu. Để lỗi của công cụ kiểm giết luôn bản sao lưu là đảo ngược
thứ tự ưu tiên: một đêm không có bản kê thì diễn tập Chủ nhật báo; một đêm không có dump thì không
có gì để phục hồi.

Nhưng nếu chỉ đổi sang "cảnh báo rồi vẫn dump" thì lại sinh ra một lỗ im lặng khác: **ngoài diễn tập
Chủ nhật, không gì nhìn `.counts`**. Bản kê có thể thiếu sáu đêm liền mà không ai biết. Hai thay đổi
dưới đây phải đi cùng nhau; làm một mà không làm cái kia là tệ hơn hiện tại.

## Giới hạn

- **KHÔNG commit, KHÔNG push.** Không tạo scheduled task, không restart container, không sửa `.env`.
- Không chạy `restore_drill.py` thật. **Không** chạy `sched.sh backup` thật (đợt 137 đã có bản thật).
- Chỉ sửa `scripts/backup_db.sh`, `scripts/backup_check.py`, test tương ứng, và đúng các dòng liên
  quan trong `DEPLOYMENT.md`. **Không** đụng `restore_drill.py`; hành vi "thiếu bản kê → CRITICAL" của
  nó giữ nguyên.
- GitNexus: `impact` trước khi sửa symbol, `detect_changes` sau khi sửa.

## Việc 1 — `backup_db.sh`: bản kê lỗi thì cảnh báo và vẫn dump

1. Lập bản kê thất bại (psql lỗi, hoặc file rỗng) → in `WARNING: ...` ra stderr, xoá `.counts.tmp`,
   **không** tạo `.counts`, rồi **vẫn chạy tiếp** `pg_dump` + xác minh như bình thường.
2. Dump hoặc xác minh hỏng → vẫn xoá `.counts` như hiện tại. Trap `cleanup_on_failure` giữ nguyên
   hành vi này.
3. Mã thoát của script: như hiện nay (0 nếu dump và xác minh đạt). Bản kê thiếu **không** đổi mã thoát.
   Lý do: người báo là `backup-check` ở Việc 2, không phải mã thoát của job sao lưu.
4. Cẩn thận `set -euo pipefail`: `psql ... | tr ... > tmp` lỗi sẽ giết cả script. Bọc đúng lệnh đó để
   bắt lỗi (`if ! ...; then`), **không** gỡ `pipefail` hay `-e` của cả file.

## Việc 2 — `backup_check.py`: báo khi bản dump mới nhất thiếu bản kê

1. Nếu bản sao lưu DB mới nhất là `trading_*.dump` mà **không** có `trading_*.counts` cùng tên gốc, hoặc
   `.counts` rỗng → `[CRITICAL] Bản sao lưu <tên> không có bản kê số dòng — diễn tập phục hồi Chủ nhật
   sẽ không kiểm được nó`.
2. Chỉ kiểm tồn tại và khác rỗng. **Không** phân tích nội dung; đó là việc của `restore_drill.py`,
   làm hai lần là báo trùng.
3. Bản `.sql.gz` cũ không có bản kê → **không** báo (định dạng cũ, trước đợt 137). Chỉ `.dump` bị đòi.
4. Thêm vào hàm phán xử thuần sẵn có hoặc một hàm thuần mới cạnh nó, theo cách
   `evaluate_orderbook_backup` đã làm ở đợt 135. **Không** đổi ngưỡng 23 giờ, ngưỡng 80 MB, hay
   logic sổ lệnh.

## Tiêu chí hoàn thành

1. Test `backup_db.sh`, dùng `docker` giả có sẵn trong `tests/test_backup_db_counts.py`:
   - psql lập bản kê lỗi → **có** `.dump`, **không** có `.counts`, **không** có `.counts.tmp`, mã
     thoát 0, stderr có `WARNING`;
   - bản kê rỗng → như trên;
   - dump hỏng → không có `.counts` (test đợt 137 phải còn xanh, không sửa).
2. Test `backup_check.py`:
   - `.dump` mới có `.counts` → IM;
   - `.dump` mới **thiếu** `.counts` → BÁO nêu tên;
   - `.counts` rỗng → BÁO;
   - `.sql.gz` mới nhất không có bản kê → IM.
   Mọi test sẵn có của `backup_check` xanh, không sửa dòng nào. Nếu buộc phải sửa thì nói rõ vì sao,
   như agent đợt 135 đã làm.
3. **Phá thử, ghi nguyên văn dòng đỏ, khôi phục và đối chiếu hash:**
   - Trả `backup_db.sh` về lỗi cứng (`exit 1` khi lập bản kê hỏng) → ca "psql lỗi vẫn có dump" phải đỏ.
   - Bỏ kiểm `.counts` trong `backup_check.py` → ca "thiếu `.counts`" phải đỏ.
4. Chạy thật `scripts/sched.sh backup-check --dry-run` trên `_backups/db`. Bản mới nhất
   `trading_20260930_221525.dump` có `.counts`, nên kỳ vọng **không cảnh báo, EXIT=0**. Dán log.
   Nếu từ giờ tới lúc bạn chạy đã có bản 02:00 mới thì bản đó cũng phải có `.counts`; dán `ls -l`.
5. `bash -n scripts/backup_db.sh` sạch. `git ls-files --eol` cho `backup_db.sh` vẫn `i/lf w/lf`, mode
   `100755`; hook định dạng từng đổi file này sang CRLF ở đợt 137. `ruff` sạch; `uv run pytest -q` ≥
   **1.618 passed** cộng số test mới.

## Báo cáo

`docs/superpowers/research/2026-09-30-dot-138-ban-ke-hong-khong-giet-ban-sao-luu.md`:

- Số đo dán nguyên văn.
- Brief sai ở đâu thì nói ra.
- Cái gì không kiểm được thì ghi là không kiểm được.
