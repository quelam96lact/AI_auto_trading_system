# Brief đợt 131 — bản sao lưu chưa ai khôi phục thử, và nó hỏng thì không ai biết

**Base commit:** `b6f97cf`.
**Người thực thi:** agent — **trọn bộ việc 1–7**, gồm cả nối vào lịch chạy và tạo bản sao lưu thật. **Claude:** audit, commit, push (xem §8).

---

## §0. Bối cảnh — số đo của Claude, 29/09 lúc 20:00 (chỉ đọc)

Sao lưu là **lớp phòng vệ cuối**. Thứ Bảy 03/10 Claude sẽ dựa vào `pg_dump` trước khi gộp chunk, và hệ thống sắp chạy 24/7 trên VPS. Claude kiểm, và tình trạng tệ hơn dự đoán:

| Phát hiện | Bằng chứng |
|---|---|
| **Chưa có bản sao lưu DB nào tồn tại** | `/var/backups/trading-db` **rỗng**. `_backups/` chỉ có CSV rời từ các sự cố cũ, không phải dump đêm |
| **`backup_db.sh` chưa bao giờ được lên lịch trên máy này** | 9 scheduled task `trading-*` đang có, **không** có task nào cho backup |
| **`pg_dump` tự cảnh báo dump có thể KHÔNG khôi phục được** | nguyên văn ở dưới |
| **Script trái với chính điều tài liệu bắt buộc** | `DEPLOYMENT.md` §6 ghi "**BẮT BUỘC** sao lưu ở định dạng custom archive (`-Fc`)", còn `backup_db.sh:15` dùng `pg_dump` văn bản thuần |
| **Bản sao lưu đêm không khớp quy trình khôi phục duy nhất đã diễn tập** | §11 khôi phục bằng `pg_restore` + `timescaledb_pre_restore()`/`post_restore()`, tức cho `-Fc`. Dump `.sql.gz` **không** chứa lời gọi nào tới `timescaledb_pre_restore` (Claude đếm: 0) |
| **Hỏng thì im lặng** | `backup_db.sh` không đi qua `run_if_docker_up.sh`, không ghi vào `logs/`, **không** có đường cảnh báo Telegram. Mọi cảnh báo và lỗi chảy vào `/var/log/trading-backup.log` — không ai đọc |

Cảnh báo nguyên văn của `pg_dump` (Claude chạy trên DB thật):

```
pg_dump: warning: there are circular foreign-key constraints on this table:
pg_dump: detail: continuous_agg
pg_dump: hint: You might not be able to restore the dump without using --disable-triggers or temporarily dropping the constraints.
pg_dump: hint: Consider using a full dump instead of a --data-only dump to avoid this problem.
```

**Điều đã đúng, đừng sửa:** dump **có** chứa dữ liệu chunk (Claude đếm 612 lệnh `COPY _timescaledb_internal`, 3.942.554 dòng dữ liệu; `bars_daily` thật có 2.986.048 dòng, phần còn lại là `bars` và `bars_derivative`). Vậy nó **không** rơi vào bẫy `pg_dump -t` mà §6 cảnh báo. `set -euo pipefail` cũng đã có. Bẫy thiếu `cd /opt/trading` đã được ghi trong §6.

**Câu hỏi chưa ai trả lời: bản sao lưu đêm có khôi phục được không?** Chưa từng thử.

---

## §1. Việc 1 — ĐO: bản sao lưu ĐỊNH DẠNG HIỆN TẠI có khôi phục được không

Làm **trước** khi sửa gì. Mục đích là biết sự thật về định dạng đang dùng, không phải để giữ nó.

1. Chạy `bash scripts/backup_db.sh <thư mục tạm>` với `BACKUP_RETENTION_DAYS=9999`. Ghi **nguyên văn** cả stdout và stderr. Trên DB thật đây chỉ là **đọc**.
2. Tạo DB nháp `bk131` trong container postgres đang chạy (`CREATE DATABASE`), `CREATE EXTENSION timescaledb`.
3. Khôi phục: `gunzip -c <file> | psql -U trading -d bk131`, **giữ toàn bộ stderr**. Đếm số dòng `ERROR:`.
4. **Đối soát**, mỗi con số lấy từ cả hai DB:
   - `count(*)` của `bars_daily`, `bars`, `bars_derivative`, `orders`, `positions`, `symbol_universe`, `account_nav_snapshot`, `bars_crypto`;
   - số hypertable trong `timescaledb_information.hypertables`;
   - số chunk của `bars_daily`;
   - checksum của `bars_daily` bằng đúng công thức đợt 128 (`sum(hashtextextended(...))`).
5. Kết luận rõ ràng, một trong ba: **khôi phục đầy đủ** / **khôi phục nhưng thiếu hoặc lệch** (nêu chính xác thiếu gì) / **không khôi phục được** (nêu lỗi).
6. `DROP DATABASE bk131`.

**Đây là phép đo, không có cổng đạt/không đạt.** Dù kết quả nào cũng ghi nguyên văn. **Không** chạy lại để chọn lần đẹp.

---

## §2. Việc 2 — chuyển `backup_db.sh` sang `-Fc`

Quyết định này **không** phụ thuộc kết quả việc 1, vì có ba lý do độc lập: §6 đã tự bắt buộc `-Fc`; §11 là quy trình khôi phục **duy nhất** đã diễn tập và nó cần `-Fc`; và `-Fc` cho phép `pg_restore -l` kiểm nhanh tính toàn vẹn. Một định dạng, một quy trình khôi phục.

**Việc:**
- Dump bằng `-Fc` **ghi vào file TRONG container** rồi `docker compose cp` ra ngoài, rồi xoá file trong container. Đây là khuôn đã ghi ở §11 Bước 3, và nó tránh hẳn chuyện đẩy dữ liệu nhị phân qua ống của shell trên host.
- Sau khi có file: `pg_restore -l <file> | head` phải đọc được. Không đọc được thì **xoá file hỏng** và thoát khác 0. Một file rác mang tên hợp lệ còn tệ hơn không có file, vì nó làm phép kiểm "có bản sao lưu mới" báo xanh.
- **Xoá theo hạn phải phủ CẢ HAI đuôi.** Hiện `find -name 'trading_*.sql.gz' -delete`; đổi định dạng mà không sửa dòng này thì file `.dump` **không bao giờ** bị xoá và đĩa VPS đầy dần, im lặng. Phủ cả `trading_*.sql.gz` (bản cũ) và đuôi mới.
- **Giữ nguyên:** `set -euo pipefail`, tham số thư mục thứ nhất, `BACKUP_RETENTION_DAYS`, và dòng `echo` báo kích thước. Giữ `-U trading`.
- Không nén thêm bằng `gzip`: `-Fc` đã nén.

**Cổng:**
- Chạy bản mới ra thư mục tạm: file tồn tại, `pg_restore -l` đọc được, kích thước hợp lý (so với 99 MB của bản `.sql.gz` hiện tại; ghi con số thực tế).
- **Khôi phục thật** vào DB nháp `bk131b` theo **đúng** quy trình §11 Bước 5 (`timescaledb_pre_restore()` → `pg_restore --no-owner` → `timescaledb_post_restore()`), rồi đối soát **cùng danh sách** ở việc 1 mục 4. Mọi con số phải **bằng tuyệt đối**. Đây là điều kiện then chốt của đợt này.
- Phá thử: cắt ngắn file dump (ví dụ `truncate -s 1M`), chạy lại bước `pg_restore -l` của script; nó phải phát hiện và thoát khác 0, **và** không để lại file rác.
- Phá thử hạn xoá: tạo file `trading_*.dump` và `trading_*.sql.gz` với `touch -d '30 days ago'`, chạy script, cả hai phải bị xoá.
- `bash -n scripts/backup_db.sh` sạch. `DROP DATABASE bk131b` khi xong.

---

## §3. Việc 3 — sao lưu hỏng thì phải KÊU: `scripts/backup_check.py`

`backup_db.sh` là bên **sản xuất**; thêm một bên **kiểm** riêng, đúng khuôn dự án đang dùng (backfill 20:30 sản xuất, `daily_data_check.py` 21:00 kiểm; bộ ghi sổ lệnh và `check_orderbook_daily.py` cũng vậy).

`scripts/backup_check.py` đọc thư mục sao lưu và **cảnh báo Telegram** khi:
- không có file sao lưu nào;
- file mới nhất **cũ hơn** ngưỡng (mặc định 26 giờ, để một lần chạy trượt giờ không kêu oan);
- file mới nhất **nhỏ hơn** ngưỡng tối thiểu (tham số, mặc định chọn theo con số thực đo được ở việc 2);
- `pg_restore -l` trên file mới nhất **hỏng**.

**Quy ước, theo code sẵn có:**
- Gửi bằng `trading.telegram.send_telegram`, in bằng `trading.alerts._print_safe`, giống `heartbeat_check.py`.
- **Mã thoát như `heartbeat_check.py`:** 0 ổn; 1 có cảnh báo và đã gửi; 2 sai cấu hình **hoặc cảnh báo cần gửi mà gửi hỏng** (nguyên tắc đợt 126).
- **Không bao giờ ném ngoại lệ ra ngoài** (FEE-ALARM-2).
- Cờ `--dry-run` in thay vì gửi; `--backup-dir`; `--max-age-hours`; `--min-size-mb`.
- Hàm quyết định phải **thuần**, tách khỏi phần đọc filesystem, để test không cần file thật.

**Cổng:**
- Test cho **từng** điều kiện trên, cộng: thư mục không tồn tại; có file nhưng `pg_restore` không có trên PATH (phải nói rõ "không kiểm được", **không** coi là đạt); gửi hỏng → mã 2.
- Phá thử: bỏ điều kiện tuổi → test tuổi đỏ; bỏ điều kiện kích thước → test kích thước đỏ. Dán thông điệp đỏ nguyên văn.
- Chạy thật `--dry-run` trên thư mục sao lưu **tạm** của việc 2 (phải im) và trên một thư mục rỗng (phải kêu). Dán nguyên văn.

---

## §4. Việc 4 — `DEPLOYMENT.md` §6

**Chỉ** §6, và chỉ những gì việc 1–3 đã chứng minh:
- Đổi phần mô tả sang định dạng mới.
- **Ghi quy trình khôi phục bản sao lưu ĐÊM đã được kiểm thật** ở việc 2 (các bước `pre_restore` → `pg_restore` → `post_restore`, kèm bước đối soát số dòng). Hiện §6 **không** có quy trình khôi phục nào cho bản sao lưu đêm; §11 chỉ nói về dump chuyển máy.
- Nêu cảnh báo `continuous_agg` là **đã biết và vô hại với `-Fc`** nếu việc 2 chứng minh vậy; nếu vẫn còn ảnh hưởng thì ghi đúng ảnh hưởng.
- Khối cron thì sửa ở **việc 5**, không sửa rải rác ở đây.

## §5. Việc 5 — nối vào lịch chạy

Trước đây Claude giữ phần này; chủ dự án yêu cầu agent làm trọn.

- `scripts/sched.sh`: thêm case `backup` và `backup-check`, gọi qua `run_if_docker_up.sh` **đúng khuôn** các case sẵn có. Cập nhật cả khối chú thích đầu file và dòng `dung:` ở case `*)`.
  - `backup` truyền thư mục sao lưu: trên VPS là `/var/backups/trading-db`. **Không** viết cứng đường dẫn Windows vào `sched.sh`.
  - `backup-check` gọi `backup_check.py` với cùng thư mục đó.
- `DEPLOYMENT.md`: thêm hai dòng cron. `backup` giữ **02:00** như §6 đang ghi; `backup-check` chạy **sau đó** (đề xuất 03:00, nêu lý do trong chú thích). Hai job này chạy **hằng ngày, kể cả cuối tuần** — dữ liệu ngày thứ Sáu vẫn cần được sao lưu qua cuối tuần.
- **Chuyển dòng cron `backup` sẵn có ở §6 thành gọi qua `sched.sh`** để nó được cổng Docker và ghi log như 10 job còn lại. Giữ nguyên câu giải thích `cd /opt/trading` là **BẮT BUỘC** (nó vẫn đúng) và đoạn cảnh báo về `pg_dump -t`.
- Đồng bộ luôn `docs/README_VPS_UBUNTU.md:167` nếu nó vẫn ghi dòng cron kiểu cũ.

**Cổng:** `uv run pytest tests/test_deployment_doc.py` xanh — test này bắt buộc tập job trong `sched.sh` **bằng** tập job trong `DEPLOYMENT.md`, nên thiếu một bên là đỏ. `bash -n scripts/sched.sh` sạch. Gọi `scripts/sched.sh` với một job không tồn tại phải in đủ **12** job trong dòng `dung:`.

## §6. Việc 6 — tạo bản sao lưu THẬT đầu tiên trên máy này

Hiện **chưa có bản sao lưu DB nào**. Phải có một bản trước khi Claude gộp chunk thứ Bảy.

- Ghi vào `D:/My_Vault_Obsidian/Project/_backups/db/` — **ngoài repo** (yêu cầu của chủ dự án), và là **thư mục con riêng** để lệnh xoá theo hạn không bao giờ chạm các file rời có sẵn trong `_backups/` (`bars_daily_backup_20260830.csv.gz`, v.v.).
- Chạy qua `scripts/sched.sh backup <thư mục đó>` để kiểm luôn đường dây thật.
- **Trước và sau**, liệt kê `_backups/` (mức trên) và chứng minh **không file nào bị mất**.
- Rồi chạy `scripts/sched.sh backup-check <thư mục đó>`: phải **im** và mã thoát 0.
- Bản này **giữ lại**, không xoá. Dán `ls -l` và kích thước.

## §7. Việc 7 — hai lỗ đợt 130 đã ghi nhận, giờ bịt

Audit đợt 130 (§A.6 của báo cáo đó) ghi nhận hai chỗ, giờ sửa trong `scripts/container_health_check.py`:

1. **`read_error` báo động mọi lần chạy.** Nhánh đó `continue` **trước khi** ghi trạng thái, nên container biến mất sẽ gửi Telegram mỗi 10 phút, mãi mãi. Sửa theo **cùng cách** đã dùng cho `OOMKilled` và `Status` ở đợt 130: chỉ báo khi **chuyển** trạng thái, kéo dài thì ghi log. Cần lưu trạng thái lỗi vào bản ghi để so được.
2. **`memory.events` không đọc được một lần thì mù lần sau.** Khi đọc hỏng, trạng thái lưu `oom_kill = None`, nên lần sau không có mốc để so và **một lần OOM có thể lọt**. Sửa: khi lần này không đọc được, **giữ lại** giá trị `oom_kill`/`mem_max` cũ trong trạng thái thay vì ghi `None` lên, và ghi log rõ là đang dùng mốc cũ. Như vậy lần sau vẫn so được.

**Cổng:** mỗi mục một test; cộng một test chứng minh **sự cố mới vẫn báo** khi sự cố cũ đang kéo dài (cùng loại với test Claude đã thêm ở đợt 130). Phá thử từng mục, dán thông điệp đỏ nguyên văn. Toàn bộ 18 test sẵn có phải vẫn xanh.

## §8. Việc còn lại KHÔNG chuyển được cho agent

Hai thứ này do chính quy tắc của chủ dự án, không phải Claude giữ việc:
1. **Commit và push:** chỉ Claude làm (CLAUDE.md, phân vai planner/executor).
2. **Tạo scheduled task trên Windows:** việc của chủ dự án. Sau đợt này cần **hai** task mới: `container-health` (đợt 130) và `backup` + `backup-check`. Agent **ghi rõ vào báo cáo** tên job và lịch đề xuất để chủ dự án tạo, **không** tự tạo.

## §9. Phạm vi

**Được sửa/tạo:** `scripts/backup_db.sh`; `scripts/backup_check.py` (mới); `tests/test_backup_check.py` (mới); `scripts/container_health_check.py` và `tests/test_container_health_check.py` (**chỉ** việc 7); `scripts/sched.sh` (**chỉ** thêm hai case + chú thích + dòng `dung:`); `DEPLOYMENT.md` (§6, và khối cron §9 cho việc 5); `docs/README_VPS_UBUNTU.md` (**chỉ** dòng cron backup); báo cáo `docs/superpowers/research/2026-09-29-dot-131-ban-sao-luu.md`.

**KHÔNG được đụng:** `trading/`; `docker-compose.yml`; `.githooks/`; `config/`; các case sẵn có trong `sched.sh`; các phần khác của `DEPLOYMENT.md`; test của đợt khác; DB `trading` (chỉ **đọc**: `pg_dump`, `psql -Atc` đếm; mọi lệnh ghi chỉ vào `bk131`/`bk131b`); mọi container đang chạy (không `up`/`restart`/`stop`/`down`); các file rời sẵn có trong `_backups/`.

## §10. Điều cấm

- **Không commit, không push.** Không rebuild, không restart container.
- **Không ghi, không `ALTER`, không `DROP` gì trên DB `trading`.** DB nháp phải `DROP` khi xong.
- Mọi **phép thử** dùng thư mục tạm. Chỉ **việc 6** được ghi thật, và chỉ vào `_backups/db/`; không chạm các file rời ở mức trên.
- Không gửi Telegram thật: dùng `--dry-run` hoặc hàm gửi giả.
- Không đọc `.env` thật; không in bí mật; không kết nối SSI.
- Cấm `git checkout`, `git restore`, `git stash` (trừ `git stash create`).
- Không tạo, sửa, xoá scheduled task.
- **Không chạy `merge_bars_daily_chunks.py` với DSN của DB `trading`** (kể cả dry-run có cờ): việc đó là của Claude thứ Bảy.

## §11. Tiêu chí chung

```
uv run pytest -q   (TOÀN BỘ, nats-test chạy)   → ≥ 1.444 passed + test mới, 0 failed
uv run ruff check trading tests scripts        → sạch
uv run pytest tests/test_deployment_doc.py      → xanh
bash -n cho mọi *.sh đã sửa                     → sạch
git ls-files -s scripts/backup_db.sh scripts/sched.sh → vẫn 100755
```

`npx gitnexus detect-changes --repo AI_auto_trading_system` ở cuối; `impact` trước nếu sửa symbol có người gọi.

## §12. Báo cáo phải có

1. Việc 1: **nguyên văn** stdout/stderr và bảng đối soát, kèm kết luận một trong ba khả năng.
2. Việc 2: diff, kích thước thực tế, **bảng đối soát sau khi khôi phục thật** (phải bằng tuyệt đối), hai phá thử với đầu ra nguyên văn.
3. Việc 3: bảng test ↔ điều kiện, phá thử, và hai lần chạy thật `--dry-run`.
4. Việc 5: diff, đầu ra `test_deployment_doc.py`, và dòng `dung:` có đủ 12 job.
5. Việc 6: `ls -l` trước và sau của `_backups/` **và** `_backups/db/`, kích thước bản sao lưu, kết quả `backup-check`.
6. Việc 7: bảng test ↔ hai lỗ, phá thử, và xác nhận 18 test cũ vẫn xanh.
7. **Tên job và lịch đề xuất cho scheduled task Windows** mà chủ dự án cần tạo (xem §8).
8. Những gì **không** kiểm được, và vì sao.
5. Chỗ nào brief sai hoặc mơ hồ. **Nếu brief đảo một quyết định có chủ ý nào** (đọc chú thích trong `backup_db.sh` và §6 trước khi sửa), **báo ngay**.
