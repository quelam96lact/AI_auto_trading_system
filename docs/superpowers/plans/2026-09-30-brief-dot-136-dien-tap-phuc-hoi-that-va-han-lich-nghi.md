# Brief đợt 136 — diễn tập phục hồi THẬT, và hạn của danh sách ngày nghỉ

Hai việc. Việc 1 là chính và nặng; việc 2 nhỏ.

Cả hai cùng một họ lỗi đã đeo dai dẳng dự án này: **thứ hiển thị không phải thứ được kiểm**
([[golive-gate-den-xanh-gia]]). Đợt 135 vừa bịt hai lỗ kiểu đó; đợt này bịt lỗ lớn nhất còn lại.

## Giới hạn (đọc trước khi làm)

- **KHÔNG commit, KHÔNG push.** Claude làm việc đó sau khi audit.
- **KHÔNG chạy diễn tập phục hồi thật.** Agent viết script + test với runner giả; Claude tự chạy lần
  thật đầu tiên. Lý do: nó tạo và xoá database, agent không đụng vào cụm DB thật.
- **KHÔNG sửa** `scripts/verify_backup_restore.py` (di sản đợt 13, còn giá trị tham chiếu),
  `scripts/backup_db.sh`, `scripts/backup_orderbook.sh`, `docker-compose.yml`, `.env`.
- **KHÔNG tạo scheduled task** — việc của chủ dự án. Chỉ thêm nhánh vào `sched.sh` và dòng cron
  tham chiếu trong `DEPLOYMENT.md` §9.
- Không restart/rebuild container. Không gửi Telegram thật (dùng `--dry-run`).
- Đọc GitNexus trước khi sửa: `gitnexus_impact` trên symbol sắp sửa, `gitnexus_detect_changes` sau
  khi xong. Nếu `detect-changes` báo "No changes" trong khi có file đã sửa thì index cũ — chạy
  `npx gitnexus analyze` rồi đo lại, và **ghi rõ trong báo cáo** là đã phải làm vậy.

---

## Việc 1 — `scripts/restore_drill.py`: chứng minh bản sao lưu phục hồi ĐƯỢC

### Lỗ đang có, tôi đã đo, đây là số thật

Job `backup-check` mỗi đêm gọi `pg_restore -l` rồi coi là "đã kiểm tính toàn vẹn". `pg_restore -l`
chỉ đọc **mục lục ở đầu file**, không đọc dữ liệu. Tôi cắt bản dump thật `trading_20260930_020002.dump`
(104.656.147 byte) còn **90%** rồi đo:

| Phép | Kết quả trên bản đã mất 10% dữ liệu |
|---|---|
| `pg_restore -l` | **exit 0**, đúng **3.224 dòng** mục lục — y như bản nguyên |
| ngưỡng kích thước 80 MB | 89,8 MB → **qua** |
| `evaluate_backup_health(...)` | **`[]`** — không một cảnh báo nào |
| `pg_restore` phục hồi thật | **exit 1**, `could not read from input file: end of file` |

Và điều đáng chú ý nhất: bản phục hồi dở dang **trông gần như đủ** — `bars` 936.083 so với nguồn
936.217 (99,99%), `bars_daily` khớp tuyệt đối 2.986.214 — **nhưng `orders` = 0**.

Hai kết luận cho thiết kế, đừng bỏ cái nào:
1. **Chỉ riêng việc phục hồi thật chạy được đã bắt được lỗi này**, trong khi ba phép kiểm hiện tại
   đều mù.
2. **Đếm dòng "> 0" trên vài bảng lớn thì vẫn mù** — bảng lớn gần đủ, bảng nhỏ về 0. Phải đối chiếu
   từng bảng với nguồn.

Đây là rủi ro thật, không phải giả định: chủ dự án sẽ chỉ biết bản sao lưu vô dụng vào đúng lúc cần
nó ([[backfill-books-still-poisoned]] đã có sẵn cái bẫy sao lưu hypertable).

### Script phải làm gì

`scripts/restore_drill.py`, chạy được qua `scripts/sched.sh restore-drill`, mặc định `--dry-run`
không gửi Telegram. Các bước, theo thứ tự, **dừng và cảnh báo ngay khi một bước hỏng**:

1. Tìm `trading_*.dump` **mới nhất** trong `TRADING_BACKUP_DIR` (mặc định như `backup_check.py`).
   Không có file → CRITICAL.
2. Kiểm dung lượng đĩa trống trước khi bắt đầu: cần ít nhất **3× kích thước file dump**. Thiếu →
   CRITICAL nêu rõ con số, **không** chạy tiếp. (VPS chỉ 60–80 GB — xem `DEPLOYMENT.md` §7.)
3. Tạo database nháp, mặc định tên `trading_restore_drill`.
   **Chốt cứng: nếu tên database đích rơi vào `trading` hoặc rỗng thì thoát mã 2 ngay**, cùng kiểu
   chốt như `merge_bars_daily_chunks.py`.
4. `CREATE EXTENSION timescaledb` → `timescaledb_pre_restore()` → `pg_restore --no-owner` →
   `timescaledb_post_restore()`. Theo đúng `DEPLOYMENT.md` §"khôi phục".
5. **Phán xử mã thoát VÀ stderr của `pg_restore`**: mã khác 0 → CRITICAL kèm nguyên văn dòng lỗi
   đầu tiên. Mã 0 nhưng stderr có `error:` → cũng CRITICAL. (`pg_restore` có thể trả 0 kèm cảnh báo;
   chỉ chấp nhận cảnh báo `circular foreign-key constraints on this table: continuous_agg`, đã được
   ghi là vô hại trong `DEPLOYMENT.md` §"Cảnh báo continuous_agg".)
6. **Liệt kê tập bảng ở hai bên bằng truy vấn catalog, KHÔNG dùng danh sách bảng viết cứng trong
   code.** Bảng có ở nguồn mà thiếu ở bản phục hồi → CRITICAL nêu tên. Lý do: danh sách cứng nghĩa
   là bảng thêm về sau không bao giờ được kiểm, và đó lại là một đèn xanh giả nữa — chính đợt 13 đã
   dính (`daily_pnl` viết sai tên nên `-1 == -1` bị tính là "khớp").
7. Đếm dòng từng bảng ở hai bên. Quy tắc phán xử:
   - Không đọc được số dòng ở **bất kỳ** bên nào → CRITICAL. **`-1 == -1` không bao giờ là "khớp"**
     (hằng `COUNT_FAILED` của `verify_backup_restore.py` giải thích rõ; đọc nó).
   - `so_dong_phuc_hoi < 99% so_dong_nguon` → CRITICAL, nêu tên bảng và cả hai con số.
   - Vì sao 99% mà không phải khớp tuyệt đối, và vì sao chạy **Chủ nhật**: bản dump chụp lúc 02:00,
     diễn tập chạy sau đó, nên nguồn chỉ **nhiều hơn**. Chủ nhật không có phiên nên độ trôi gần như
     bằng 0 (đo thật: `bars` lệch 134/936.217 = 0,014%). Băng 1% vừa đủ rộng để không báo oan, vừa
     đủ chặt để bắt ca mất 10% ở trên.
8. **Dọn dẹp trong `finally`**: `DROP DATABASE` bản nháp và xoá file tạm trong container, kể cả khi
   các bước trên hỏng hoặc ngoại lệ. Rồi **kiểm chứng lại**: bản nháp đã mất và database `trading`
   vẫn còn. Dọn không xong → CRITICAL (không được im lặng để lại một DB 100 MB trên đĩa).
9. Mã thoát: theo họ "by delivery" như `backup_check.py` — 0 sạch, 1 có cảnh báo và gửi được,
   2 sai cấu hình / gửi hỏng. Bảng hai họ mã thoát nằm trong docstring `scripts/_alert_common.py`,
   đọc trước khi chọn.

Tách phần phán xử thành **hàm thuần** (nhận số dòng hai bên, tập bảng, mã thoát, stderr → trả danh
sách cảnh báo) để test được không cần Docker, đúng như `evaluate_backup_health`. Mọi lệnh gọi ra
ngoài đi qua một `runner` có thể thay được, để test tiêm kết quả giả.

### Tiêu chí hoàn thành — từng bước kiểm chứng bằng gì

1. Hàm phán xử xong → `uv run pytest tests/test_restore_drill.py -q` xanh, có đủ các ca: mọi thứ
   khớp (IM); `pg_restore` exit 1 (BÁO); exit 0 nhưng stderr có `error:` (BÁO); exit 0 với đúng cảnh
   báo `continuous_agg` (IM); thiếu một bảng (BÁO nêu tên); một bảng còn 90% (BÁO nêu hai số);
   một bảng lệch 0,01% (IM); số dòng đọc không được ở một bên (BÁO); ở **cả hai** bên (BÁO — đây là
   ca `-1 == -1`); tên database đích là `trading` (thoát 2).
2. Đường dọn dẹp → test rằng khi bước phục hồi ném ngoại lệ, `runner` **vẫn** nhận được lệnh
   `DROP DATABASE`; và khi lệnh dọn hỏng thì có CRITICAL.
3. Không có file dump / đĩa thiếu → hai test riêng, CRITICAL, và **không** có lệnh `CREATE DATABASE`
   nào được gọi.
4. `sched.sh restore-drill` + dòng cron trong `DEPLOYMENT.md` §9 → `uv run pytest
   tests/test_deployment_doc.py -q` xanh (`test_crontab_jobs_match_sched_sh` sẽ bắt nếu lệch).
   Lịch đề xuất: **Chủ nhật 04:00** — sau backup 02:00, sau backup-check 03:00, trước
   host-preflight 07:00. Ghi trong §9 lý do chọn Chủ nhật (mục 7 ở trên).
5. **Hai phá thử, ghi nguyên văn dòng test đỏ vào báo cáo:**
   - Bỏ phép so tập bảng (coi như luôn khớp) → ca "thiếu một bảng" phải đỏ.
   - Đổi `-1` thành "khớp" (bỏ chốt `COUNT_FAILED`) → ca "cả hai bên không đọc được" phải đỏ.
   Khôi phục xong, chạy lại cho xanh, và **đối chiếu mã băm file** trước/sau để chứng minh đã khôi
   phục đúng nguyên trạng.
6. `uv run ruff check trading tests scripts` sạch; `uv run pytest -q` ≥ **1.543 passed** (mốc hiện
   tại) cộng số test mới.

### Ghi vào `DEPLOYMENT.md`

Một mục ngắn ở §9 (job mới) và vài dòng ở mục sao lưu: **`pg_restore -l` không chứng minh phục hồi
được**, kèm đúng bảng bốn dòng số đo ở trên. Đó là thứ người vận hành cần biết, và là lý do job này
tồn tại. Không viết lại toàn bộ mục, không "tiện thể" sửa văn phong chỗ khác.

---

## Việc 2 — phép kiểm 13: danh sách ngày nghỉ đã được xác nhận tới đâu

`config/config.yaml` đã có chú thích tự nói ra rằng còn **thiếu Tết Nguyên Đán 2027 và Giỗ Tổ 2027**,
và chủ dự án phải bổ sung **trước 31/12/2026**. Nhưng **không gì kiểm hạn đó**. Từ đợt 135, job
`backup-check` phán xử bản sao lưu sổ lệnh theo lịch giao dịch, nên danh sách thiếu sẽ thành **báo oan
mỗi sáng suốt kỳ nghỉ Tết**; `heartbeat`, `stream-health`, `daily-check`, `engine-consumer` cũng đọc
chung danh sách này.

**Đừng đo bằng `max(holidays)`.** Hiện `max` là `2027-09-02`, tức một phép kiểm kiểu "danh sách có
vươn tới 60 ngày nữa không" sẽ **ĐẠT** trong khi Tết 2027 vẫn khuyết — lại đúng cái đèn xanh giả mà
đợt này muốn diệt.

Cách đo đúng là hỏi "**đã có người xác nhận lịch tới ngày nào**":

1. Thêm vào `config/config.yaml` một khoá `holidays_confirmed_through: '2026-12-31'` với chú thích
   ngắn: ai cập nhật, cập nhật khi nào. Giá trị `2026-12-31` là sự thật hiện tại, lấy đúng theo hạn
   mà chú thích sẵn có trong file đã nêu — **không suy đoán ngày nghỉ**; ngày nghỉ do Chính phủ công
   bố, chủ dự án điền.
2. `scripts/host_preflight.py` thêm phép kiểm 13: **HỎNG nếu `holidays_confirmed_through` < hôm nay
   + 60 ngày**, nêu rõ giá trị đang có và việc cần làm. Thiếu khoá → HỎNG (không phải BỎ QUA: khoá
   này nằm trong repo, luôn đọc được). Không đọc được `config.yaml` → BỎ QUA kèm lý do, giống phép
   `real_trading` sẵn có.
3. Với hôm nay 30/09/2026 thì kết quả phải là **ĐẠT** (còn 92 ngày), và phép kiểm sẽ chuyển HỎNG từ
   **01/11/2026** — sớm hơn Tết khoảng ba tháng, đủ thời gian xử lý.

### Tiêu chí hoàn thành

1. Test: ĐẠT khi còn dư ngày; HỎNG khi sát hạn (dùng ngày "hôm nay" tiêm vào, **không** dùng
   `date.today()` thật trong test); HỎNG khi thiếu khoá; BỎ QUA khi không đọc được file.
2. Chạy thật `scripts/sched.sh host-preflight` → kỳ vọng **6 ĐẠT / 0 HỎNG / 8 BỎ QUA** (thêm một
   ĐẠT so với đợt 135). Dán nguyên văn bảng vào báo cáo.
3. Phá thử: đổi phép kiểm sang đo `max(holidays)` → phải có test đỏ. Nếu **không** test nào đỏ thì
   bộ test của bạn chưa đủ — viết thêm cho đủ rồi làm lại phá thử này.
4. Nêu trong báo cáo: phép kiểm này **chỉ chạy khi task `trading-host-preflight` đã được tạo**, mà
   task đó vẫn còn nằm ở phía chủ dự án (task thứ 15, Chủ nhật 07:00).

---

## Báo cáo

`docs/superpowers/research/2026-09-30-dot-136-*.md`. Trong đó:

- Số đo thật, dán nguyên văn, kể cả khi trái với brief này.
- **Chỗ nào brief sai hoặc tự mâu thuẫn thì nói ra và đề xuất cách xử lý**, đừng lặng lẽ lách. Đợt
  135 brief của tôi tự mâu thuẫn và agent đã nêu đúng — làm lại như vậy.
- Việc gì không kiểm được thì ghi là **không kiểm được**, đừng ghi là đạt.
- Phần diễn tập phục hồi: nói rõ rằng **chưa chạy thật lần nào**, vì brief cấm; độ tin cậy đến từ
  test và hai phá thử.
