# Brief đợt 140 — cờ gõ khi chạy tay phải CÓ HIỆU LỰC hoặc BÁO LỖI, không bao giờ bị nuốt im lặng

## Vì sao — sự cố thật sáng 02/10/2026

Máy ngủ qua tối 01/10 nên lỡ job kiểm dữ liệu 21:00. Sáng 02/10 Claude chạy bù và **gửi hai cảnh báo
Telegram oan** cho chủ dự án:

1. **05:47** — chạy bù bằng `Start-ScheduledTask`. Job kiểm ngày *hôm nay* (`datetime.now(TZ).date()`),
   mà 05:47 thì chưa thể có nến ngày 02/10 → "Ngày giao dịch nhưng 0 mã có bar daily".
2. **05:53** — chạy lại `scripts/sched.sh daily-check --date 2026-10-01`. Nhánh `daily-check)` của
   `sched.sh` gọi script **không kèm `"$@"`**, nên `--date` bị **nuốt im lặng**: job lại kiểm 02/10 và
   lại gửi Telegram.

Claude rà toàn bộ `sched.sh`: **7/16 nhánh bỏ tham số** — `backfill`, `container-health`, `daily-check`,
`deploy-drift`, `engine-cam`, `engine-consumer`, `heartbeat`. 9 nhánh kia chuyển `"$@"`. Tệ hơn,
`heartbeat_check.py` và `deploy_drift_check.py` **không có bộ phân tích tham số nào**, nên kể cả khi
`sched.sh` chuyển `"$@"` thì cờ vẫn bị nuốt ở tầng script. Ví dụ `sched.sh heartbeat --dry-run` sẽ
**gửi cảnh báo thật**.

Khi cron chạy thì không có tham số nào, nên lịch hằng ngày không bị ảnh hưởng. Lỗ này chỉ cắn đúng lúc
người vận hành chạy tay để chữa cháy. Đó cũng là lúc họ đang dựa vào cờ để an toàn.

Nguyên tắc của đợt: **một cờ gõ vào hoặc có hiệu lực, hoặc làm lệnh chết với mã khác 0 TRƯỚC khi làm
bất cứ việc gì.** Không có trạng thái thứ ba.

## Giới hạn

- **KHÔNG commit, KHÔNG push.** Không tạo scheduled task, không restart container, không sửa `.env`.
- **KHÔNG chạy bất kỳ job cảnh báo nào ở chế độ gửi thật.** Mọi lần chạy thật phải có `--dry-run`, hoặc
  phải là lệnh chắc chắn chết ở bước phân tích tham số. Gửi oan cho chủ dự án là đúng cái lỗi đợt này
  diệt.
- Chỉ sửa: `scripts/sched.sh`, bảy script của bảy nhánh trên (chỉ phần phân tích tham số và `main`),
  test tương ứng, và một mục mới trong `DEPLOYMENT.md`. **Không** đổi logic phán xử của job nào.
- GitNexus: `impact` trước khi sửa symbol, `detect_changes` sau khi sửa.

## Việc 1 — `sched.sh`: mọi nhánh chuyển `"$@"`

Thêm `"$@"` vào bảy nhánh. Nhánh nào đã có `shift || true` thì giữ, nhánh nào chưa có thì thêm, cho
đồng bộ với các nhánh đã đúng. Không đổi thứ tự hay tên log.

## Việc 2 — mọi script được gọi đều từ chối cờ lạ

1. Với **mỗi** script Python mà `sched.sh` gọi (không chỉ bảy cái trên; Claude chưa đếm chính xác, có nhánh gọi file `.sh` và có nhánh gọi bằng `python -m`), kiểm: gọi với một cờ không
   tồn tại thì phải thoát mã ≠ 0 **trước** khi chạm DB, Docker, mạng hay Telegram.
2. Script nào chưa có `argparse` (ít nhất `heartbeat_check.py` và `deploy_drift_check.py`, tự kiểm phần
   còn lại) thì thêm một parser **không có tuỳ chọn nào ngoài những gì cần cho Việc 3**. Mục đích chỉ là
   để cờ lạ chết to.
3. Tách việc dựng parser thành một hàm `build_parser()` trong mỗi script, để test gọi
   `build_parser().parse_args(["--khong-ton-tai"])` mà **không bao giờ chạy logic thật**. Không test
   bằng cách chạy script với cờ lạ qua subprocess: nếu sau này ai đó gỡ parser thì test đó sẽ chạy job
   thật và gửi Telegram.
4. Với các file `.sh` mà `sched.sh` gọi (`backup_db.sh`, `backup_orderbook.sh`, `record_vn30f…` nếu là
   shell): kiểm chúng xử lý tham số thế nào và **báo lại**. Chỉ sửa nếu có chỗ nuốt cờ im lặng; nếu
   sửa thì nêu rõ.

## Việc 3 — `daily_data_check.py --dry-run`

Đây là job đã cắn. Thêm `--dry-run`: in cảnh báo thay vì gửi Telegram, mã thoát giữ đúng họ hiện tại.
Kết hợp với `--date` sẵn có, đó là cách chạy bù an toàn duy nhất. Không thêm `--dry-run` cho script
khác trong đợt này, trừ khi nó **đã** có.

## Việc 4 — `DEPLOYMENT.md`: mục "Chạy bù sau khi máy hoặc Docker tắt"

Ngắn, dạng bảng, mỗi job một dòng: chạy bù được không, bằng lệnh nào, cờ nào bắt buộc. Ít nhất:

- `backfill`: chạy bù an toàn (nạp lại là idempotent).
- `daily-check`: **chỉ** `scripts/sched.sh daily-check --date <ngày lỡ> --dry-run` trước; xem kết quả
  rồi mới quyết định. **Không** dùng `Start-ScheduledTask` vào hôm sau. Ghi lý do bằng đúng sự cố 02/10.
- `backup`, `orderbook-backup`: chạy bù an toàn.
- `backup-check`: chạy bù thì nó sẽ đánh giá theo *bây giờ*. Nêu rõ điều đó có nghĩa gì.
- Ghi chú: trong psql, `ts::date` trên `bars_daily` là theo UTC và lệch một ngày; dùng
  `(ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`. Claude đã đọc sai đúng chỗ này sáng 02/10.

Mỗi dòng trong bảng phải là thứ bạn đã đọc code để xác nhận, không phải đoán từ tên job.

## Tiêu chí hoàn thành

1. **Test ghim cho `sched.sh`:** một test đọc `sched.sh`, và với **mọi** nhánh có `exec "$RUN"`, khẳng
   định lệnh có `"$@"`. Phá thử: gỡ `"$@"` khỏi một nhánh → test đỏ, nêu tên nhánh.
2. **Test cho mọi script:** `build_parser().parse_args(["--khong-ton-tai"])` ném `SystemExit` với mã
   ≠ 0, cho mọi script Python mà `sched.sh` gọi. Viết dạng tham số hoá, danh sách script **lấy từ
   chính `sched.sh`**, không viết cứng, để nhánh thêm về sau tự được kiểm. Phá thử: cho một script
   dùng `parse_known_args` → test đỏ.
3. **Chạy thật, an toàn:**
   - `scripts/sched.sh heartbeat --khong-ton-tai` → mã ≠ 0, log có lỗi argparse, **không** có dòng nào
     cho thấy job đã chạy.
   - `scripts/sched.sh daily-check --date 2026-10-01 --dry-run` → kiểm đúng ngày 01/10 (tôi đã đo bằng
     DB: 174 mã), **không gửi Telegram**, dán log.
   - `scripts/sched.sh daily-check --date 2026-10-01 --khong-ton-tai` → chết trước khi kiểm.
4. `bash -n scripts/sched.sh` sạch; `git ls-files --eol -s scripts/sched.sh` vẫn `i/lf w/lf`, mode
   `100755`. `ruff` sạch; `uv run pytest -q` ≥ **1.660 passed** cộng số test mới; `test_deployment_doc.py`
   xanh.

## Báo cáo

`docs/superpowers/research/2026-10-02-dot-140-co-chay-tay.md`:

- Bảng 16 nhánh: trước/sau có `"$@"`, script có parser chưa, cờ lạ có chết to chưa.
- Số đo dán nguyên văn.
- Brief sai ở đâu thì nói ra.
- Cái gì không kiểm được thì ghi là không kiểm được.
