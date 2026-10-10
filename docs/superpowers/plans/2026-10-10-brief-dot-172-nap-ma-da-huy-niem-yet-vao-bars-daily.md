# Brief đợt 172 — Dò xong và nạp mã đã hủy niêm yết vào `bars_daily` (có đánh dấu)

Ngày: 10/10/2026 (thứ Bảy, không có phiên). Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.

## 0. Vì sao

`bars_daily` gần như chỉ có mã còn sống (đợt 169: chỉ 1/1.208 mã có nến cuối trước 30/06/2022). Đợt 170 vòng 2 (`9d4391c`, `cb48f3b`) dựng script dò mọi mã 3 chữ cái trên SSI. Khối `A**` cho đối chứng dương 59/59 và tìm ra 8 mã thiếu. Lần chạy toàn bộ dừng ở **6.836/17.576** mã (28 lỗi), vì Claude Code tự dừng tác vụ nền khi máy thiếu bộ nhớ. Tiến độ vẫn còn trong `data/probe_delisted_progress.json`.

Mục tiêu đợt này: dữ liệu cổ phiếu có cả mã đã chết, để đợt 171 (tối ưu octopus) và mọi phép đo cổ phiếu sau không bị thổi phồng. **Đây là việc dữ liệu, không phải giả thuyết.**

## 1. Việc làm

### Phần A — Dò cho xong (agent chạy)
1. Chạy `uv run python scripts/probe_ssi_delisted_coverage.py` **trong terminal của agent**, không qua tác vụ nền của Claude Code. Script tự bỏ qua mã đã dò và dò lại mã lỗi.
   - Hôm nay thứ Bảy nên được chạy cả ngày. **Ngày giao dịch thì chỉ chạy ngoài 08:45–15:15.**
   - Còn khoảng 10.740 mã, khoảng 4,5 giờ.
2. Báo cáo cuối còn mã lỗi thì chạy lại lệnh, tối đa 3 lần. Sau 3 lần vẫn còn lỗi thì liệt kê và dừng Phần A; **không** coi mã lỗi là "không có dữ liệu".
   → **kiểm chứng bằng:** dán nguyên văn báo cáo cuối: tập S, độ nhạy (phải 100%), số mã còn lỗi, danh sách "mã thiếu" hai nhóm.

### Phần B — Kiểm tác động TRƯỚC khi nạp (đọc code, không sửa)
Thêm nến của mã chết vào `bars_daily` có thể đổi hành vi của mọi chỗ lấy danh sách mã từ bảng này.
3. Tìm **mọi** chỗ đọc danh sách mã từ `bars_daily` (ví dụ `SELECT DISTINCT symbol FROM bars_daily`, `load_universe`, đếm số mã mỗi ngày) trong `trading/`, `scripts/`, `grafana/`. Dùng GitNexus `query` và grep, không chỉ một trong hai.
4. Với từng chỗ, ghi: tên file/hàm; có chạy theo lịch hoặc trong engine/collector không; nạp mã chết thì hành vi đổi thế nào. **Đặc biệt** kiểm `scripts/daily_data_check.py` và nhánh kiểm nến ngày của `scripts/heartbeat_check.py`: chúng lấy "số mã kỳ vọng mỗi ngày" từ đâu? Nếu từ `bars_daily` thì mã chết sẽ bị báo thiếu nến **mỗi ngày** (cảnh báo Telegram giả).
   → **kiểm chứng bằng:** bảng tác động trong báo cáo. Chỗ nào chạy thật mà bị ảnh hưởng thì **dừng trước Phần C** và báo Claude. Không tự sửa các job đó.

### Phần C — Đánh dấu và chuẩn bị nạp (agent viết code; Claude chạy lệnh ghi DB)
5. Bảng mới `delisted_symbols` trong `trading/storage/schema.sql` (`CREATE TABLE IF NOT EXISTS`): `symbol text PRIMARY KEY`, `first_bar date`, `last_bar date`, `n_bars integer`, `source text NOT NULL` (giá trị `'ssi_probe_dot170'`), `found_at timestamptz NOT NULL DEFAULT now()`.
6. Script `scripts/load_delisted_symbols.py`:
   - đọc "mã thiếu" từ file tiến độ (dùng lại `analyze_probe_results` của script dò, không viết lại);
   - **mặc định chạy khô (`--dry-run`)**: chỉ in danh sách mã sẽ ghi vào `delisted_symbols` và lệnh `backfill_universe.py` sẽ chạy;
   - cờ `--apply`: ghi `delisted_symbols` (upsert), rồi gọi nạp nến ngày qua đường có sẵn của `scripts/backfill_universe.py` (`--timeframe 1d --symbols ... --from 2016-01-01 --to <hôm nay>`). **Import hoặc gọi lại, không viết đường nạp mới.**
   - Không đụng `symbol_universe` (bảng đó engine dùng; `is_active` phải giữ nguyên).
7. **Agent chỉ chạy `--dry-run`.** Claude sao lưu DB rồi tự chạy `--apply`.

## 2. Phạm vi
- **Được thêm/sửa:** `trading/storage/schema.sql` (chỉ thêm bảng `delisted_symbols`), `trading/storage/db.py` (chỉ thêm một hàm upsert cho bảng đó), `scripts/load_delisted_symbols.py`, `tests/test_load_delisted_symbols.py`.
- **Được chạy:** script dò (Phần A, chỉ đọc), `load_delisted_symbols.py --dry-run`.
- **Không:** chạy `--apply`, chạy `backfill_universe.py` trực tiếp, chạy `sched.sh`, sửa job kiểm dữ liệu, sửa `symbol_universe`, sửa script dò (thấy lỗi thì báo).
- GitNexus: chạy `npx gitnexus analyze` trước. Chạy `impact` cho mọi hàm trong `db.py` được đụng tới; `detect_changes` sau khi xong.

## 3. Kiểm chứng (TDD; client và DB giả, không gọi mạng)
1. Từ file tiến độ giả gồm mã có nến, mã 0 nến, mã lỗi và mã đã có trong DB → danh sách nạp **chỉ** gồm mã có nến mà DB chưa có; mã lỗi bị báo riêng, không nạp.
2. `--dry-run` (mặc định) không gọi hàm ghi DB nào và không gọi đường nạp (spy).
3. `--apply` gọi upsert `delisted_symbols` đúng số mã, rồi gọi đường nạp với đúng `--symbols`, `--from 2016-01-01`.
4. Không có lời gọi nào ghi `symbol_universe`.
5. `init_schema` hai lần không lỗi (bảng mới idempotent).

Kiểm thử phá hoại: sao lưu file ra ngoài repo; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ.
- Cho mã lỗi vào danh sách nạp → test 1 đỏ.
- Đổi mặc định thành `--apply` → test 2 đỏ.

```
uv run pytest tests/test_load_delisted_symbols.py tests/test_scripts_convention.py -v
docker compose --profile test up -d nats-test
uv run pytest -q
uv run ruff check trading tests scripts
```

## 4. Hoàn thành khi
- Phần A: báo cáo dò cuối, độ nhạy 100%, số mã còn lỗi (lý tưởng 0).
- Phần B: bảng tác động đủ mọi chỗ đọc danh sách mã từ `bars_daily`, kèm kết luận nạp có gây cảnh báo giả không.
- Phần C: 5 test xanh, hai bước phá hoại đỏ đúng test, bộ đầy đủ không có test mới đỏ (mốc: dán số trước/sau), ruff sạch, `detect_changes` chỉ gồm các file ở §2.
- Output `--dry-run` nguyên văn: số mã sẽ nạp, và lệnh nạp sẽ chạy.

## 5. Bước sau (Claude)
Sao lưu DB → chạy `--apply` → kiểm số mã có nến cuối trước 30/06/2022 (phải ≥ 20 để mở cổng đợt 171) → đo lại EW 2017–2022 có/không có mã chết để biết thiên lệch lớn bao nhiêu → chạy phép đo đợt 171.
