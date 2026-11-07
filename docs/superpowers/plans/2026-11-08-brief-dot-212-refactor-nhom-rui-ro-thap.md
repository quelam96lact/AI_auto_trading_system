# Brief đợt 212: refactor nhóm rủi ro thấp (theo rà soát đợt 211)

Ngày 08/11/2026. Người giao: Claude (Lead). Người làm: **Builder**.

Nguồn: `docs/audit/2026-11-08-ra-soat-refactor.md` (commit 7e3e317), lấy các dòng 9, 10, 11, 12, 16, 18 và 6.

## Không làm, và lý do

- **Dòng 7, 14, 15:** đây là script đo hoặc research đã công bố kết quả. Sửa chúng thì không còn chạy lại được đúng code đã ra con số. Giữ nguyên.
- **Dòng 1, 2, 3, 5:** đụng engine và storage đang chạy thật. Mỗi dòng sẽ có brief riêng.

## Quy tắc chung

- **Trước khi sửa mỗi symbol:** chạy `node .gitnexus/run.cjs impact "<tên>" --direction upstream --repo .` (không dùng `npx`).
  - Index cũ thì chạy `node .gitnexus/run.cjs analyze --index-only` trước.
  - Kết quả HIGH hoặc CRITICAL: dừng lại và báo Lead.
  - Kết quả UNKNOWN: phải có thêm `git grep` chứng minh.
- **Sau khi sửa:** chạy `node .gitnexus/run.cjs detect-changes --scope all --repo .`.
- Giữ nguyên style code. Không "tiện thể" sửa thứ khác. Thấy vấn đề ngoài phạm vi thì ghi vào báo cáo.
- Không commit, không push. Không chạy `sched.sh`, không chạy script thật để thử, không gọi DB hay API thật.

## Các task

### 1. Xoá code chết (dòng 9–12)

- `trading/collector/latch.py`: xoá `BarLatch.get_snapshot_count`.
- `trading/storage/db.py`: xoá `Storage.write_index_values`. Nếu import `IndexValue` trở thành thừa **chỉ vì** việc xoá này thì xoá import đó, ngoài ra không xoá gì khác.
- `trading/crypto_fees.py`: xoá `BINGX_PERP_MAKER` cùng chú thích đi kèm, nếu chú thích đó chỉ nói về hằng số này.
- `trading/collector/backfill.py`: xoá lớp `SSIRestClientLegacy`.
  - Docstring của lớp ghi "giữ tới khi Phase 4 E2E ổn định ≥2 phiên". Điều kiện này đã thoả: hệ thống đã chạy thật nhiều tháng.
  - Import trở thành thừa vì việc xoá này thì xoá theo.

→ **Kiểm chứng:** với cả 4 tên, `git grep -n "<tên>" -- trading scripts tests` không còn dòng nào. `uv run ruff check trading tests scripts` sạch.

### 2. Fallback NATS (dòng 16)

- `scripts/engine_consumer_check.py:130`: đổi `"nats://localhost:4222"` thành `"nats://127.0.0.1:4222"`.

→ **Kiểm chứng:** `git grep -n "nats://localhost" -- trading scripts` không còn dòng nào.

### 3. Một nguồn cho thư mục backup (dòng 18)

- `scripts/backup_check.py:65`, `scripts/disk_check.py:58`, `scripts/restore_drill.py:75` cùng định nghĩa `DEFAULT_BACKUP_DIR`. Đưa định nghĩa về một chỗ, rồi cả 3 script import từ đó.
- **Trước khi chọn chỗ đặt:** ghi vào báo cáo cách từng script được chạy (host Task, `scripts/*.sh`, hay container scheduler) và cách mỗi script hiện import module khác trong `scripts/`.
  - Chỉ dùng cơ chế import mà **cả 3 script đã dùng sẵn**.
  - Nếu không có cơ chế chung nào chắc chắn thì **bỏ task này** và báo lại.
- Giữ nguyên hành vi: biến môi trường `TRADING_BACKUP_DIR` được ưu tiên, nếu không có thì dùng `/var/backups/trading-db`. Thời điểm đọc giá trị vẫn là lúc import module.

→ **Kiểm chứng:**
- Test hiện có của 3 script vẫn xanh.
- Thêm 1 test mới: với `monkeypatch.setenv("TRADING_BACKUP_DIR", ...)` rồi reload module, giá trị phải bằng giá trị đã đặt.

### 4. Một nguồn cho URL SSI (dòng 6)

- Sau task 1, URL `https://fc-data.ssi.com.vn/` và `https://fc-datahub.ssi.com.vn/` còn ở `trading/collector/feed.py`, `scripts/backfill_foreign_flow.py` và `scripts/record_fixtures.py`.
- Đặt hai hằng số `SSI_FC_DATA_URL` và `SSI_FC_STREAM_URL` trong `trading/config.py`, rồi cho cả 3 file import từ đó.
- Giá trị phải **giữ nguyên từng ký tự**, kể cả dấu `/` cuối.

→ **Kiểm chứng:**
- `git grep -n "fc-data.ssi.com.vn\|fc-datahub.ssi.com.vn" -- trading scripts` chỉ còn đúng 2 dòng, đều trong `trading/config.py`. Dòng chú thích trong `record_fixtures.py:4` không tính.
- Test của collector, feed và backfill vẫn xanh.

## Kiểm chứng cuối

- `uv run pytest -m "not integration" -q`: mốc trước refactor là 2283 passed. Sau refactor phải là 2283 + số test mới thêm, **0 failed**. Ghi rõ số test đã thêm.
  - Riêng test của các symbol vừa xoá thì không có, vì đó là code chết. Nếu có test nào gọi tới những symbol này thì dừng lại và báo Lead.
- `uv run ruff check trading tests scripts`: sạch.
- Nội dung `logs/alert_outbox_*` thật không đổi trước và sau khi chạy test.

## Báo cáo cho Lead

- Danh sách file đã sửa, và với mỗi task là số dòng thêm và bớt (`git diff --stat`).
- Kết quả `impact` của từng symbol: số caller và mức risk.
- Kết quả `detect-changes`.
- Task 3: cách từng script đang chạy và cơ chế import đã chọn, hoặc lý do bỏ task.
- Số test pass và số test mới.
