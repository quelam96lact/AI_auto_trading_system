# Brief đợt 206 — Làm mới danh mục mã (symbol_universe.is_active) tự động hằng tuần

Ngày: 01/11/2026. Người giao: Lead (Claude). Người làm: Builder.

## 0. Bối cảnh đã đo (không cần đo lại)

- `symbol_universe`: 1.595 mã, 174 `is_active`, mọi dòng `updated_at = 2026-09-01 01:19 UTC`. Chỉ `scripts/screen_liquidity.py` ghi `is_active`, và chưa ai chạy lại từ 01/09.
- Job nạp 1d hằng đêm (`startup_catchup` → `backfill_universe --use-universe`) chỉ nạp **174 mã active + mã bắt buộc có giá**. 1.421 mã còn lại có bar ngày cuối nằm trong 28/08–03/09 (đo bằng DB 01/11).
- Hệ quả: chạy lại `screen_liquidity` hôm nay thì cutoff stale = 30/10 − 30 ngày = 30/09, nên **cả 1.421 mã bị coi là chết**. Danh mục chỉ có thể co lại, không bao giờ nhận mã mới lên thanh khoản. Muốn lọc đúng thì phải nạp 1d cho toàn bộ danh mục trước.
- Bẫy có sẵn: `backfill_universe.py` chạy KHÔNG có `--use-universe`/`--symbols` sẽ gọi `load_symbols()`, hàm này upsert lại toàn bộ `symbol_universe` với `is_active=False` và xóa sạch cờ active. Không được dùng đường này để nạp toàn danh mục.
- Chi phí: 174 mã 1d mất khoảng 75 giây (logs/catchup.log 01/11 13:43). Chunk 1d dài 366 ngày nên mỗi mã chỉ tốn 1 lần gọi bất kể khoảng ngày. Toàn danh mục ≈ 1.595 lần gọi ≈ 11–12 phút, chạy mỗi tuần một lần.
- Engine chỉ giao dịch `cfg.symbols` (HPG, IJC, AAA). `is_active` chỉ quyết định nạp dữ liệu, `daily_data_check` và bảng điểm SEPA. Không đổi ngưỡng: 1 tỷ, 20 phiên, stale 30 ngày (đúng bộ đã tạo ra 174 mã ngày 01/09).

## 1. Việc phải làm

**Bắt buộc trước khi sửa:** dùng GitNexus `impact` (upstream) cho `main` của `scripts/backfill_universe.py`, `main` và `compute` của `scripts/screen_liquidity.py`, và `run_event` của `trading/scheduler/main.py`. Dùng CLI `gitnexus` hoặc `node .gitnexus/run.cjs`, KHÔNG dùng npx. Gặp UNKNOWN hoặc "not found" thì xác nhận bằng text search và ghi kết quả vào báo cáo.

### 1.1 `scripts/backfill_universe.py`: thêm cờ `--all-universe`
- Nhánh mới trong `main`, đặt sau `--symbols`, trước `--use-universe`: `symbols = sorted(storage.read_symbol_universe())`. **Không** gọi `load_symbols`/`upsert_symbol_universe`.
- Kiểm chứng: test dùng storage giả. Gọi `main([... "--all-universe"])` thì `upsert_symbol_universe` không bị gọi, và `run` nhận đúng toàn bộ mã của `read_symbol_universe()`.

### 1.2 `scripts/screen_liquidity.py`: tách phần ghi ra hàm
- Tách vòng UPDATE trong `main` thành `apply(stats, cutoff, min_value, dsn) -> int` (trả số mã active). Thêm `active_set(stats, cutoff, min_value) -> set[str]` theo đúng biểu thức hiện có.
- `main(argv=None)` phải giữ nguyên hành vi và output: các cờ cũ, dry-run in như cũ.
- Kiểm chứng: test `active_set` (mã stale bị loại; dưới ngưỡng bị loại; đủ ngưỡng và mới thì vào).

### 1.3 Script mới `scripts/refresh_universe.py`
Thứ tự trong `main(argv=None) -> int`:
1. Đọc config. Lấy `end = catchup_end(now, cfg.holidays)` (import từ `scripts.startup_catchup`).
2. **Cổng tuần:** nếu `max(updated_at)` của `symbol_universe` cách `now` dưới 6 ngày và không có `--force` thì in `[universe] lan lam moi gan nhat <ts>, chua can` và trả 0. Dùng `max` nên lần chạy đầu (01/09) cũng qua cổng.
3. `symbols = read_symbol_universe()`. Lấy progress 1d từng mã bằng `get_backfill_progress(s, "1d")`, rồi `start, clamped = plan_universe_start(progress, end, max_days=args.max_days)` với `--max-days` mặc định 120. Nếu `start` khác None thì gọi `backfill_universe.main(["--timeframe","1d","--from",start,"--to",end,"--all-universe","--sleep-ms","200"])`. Nếu `clamped` thì in cảnh báo, nhưng vẫn đi tiếp.
4. Nếu bước 3 ném lỗi thì **không lọc**, giữ nguyên `is_active` cũ, trả 1.
5. `stats, cutoff = screen_liquidity.compute(20, 30, dsn)`, rồi `new = active_set(stats, cutoff, 1e9)` và `old = read_active_universe()`.
6. **Cổng co rút:** nếu `len(new) < 0.5 * len(old)` thì KHÔNG ghi. In cả hai số, gửi Telegram (cùng cách `daily_data_check.py` gửi) và trả 1. Lý do: dữ liệu 1d hỏng thì không được phép làm mất cả danh mục.
7. Nếu qua cổng thì `apply(...)`. In `[universe] active cu=<n> moi=<m> them=[...] bo=[...]` (liệt kê tối đa 30 mã mỗi chiều kèm tổng số), rồi trả 0.
- Có `--dry-run`: chạy bước 1–6, không gọi backfill, không ghi gì, chỉ in kế hoạch và tập mới tính trên dữ liệu hiện có.
- Kiểm chứng bằng unit test, monkeypatch mọi thứ, KHÔNG chạm DB thật và KHÔNG ghi file trong `logs/`. Các ca phải có:
  - (a) cổng tuần chặn;
  - (b) `--force` bỏ qua cổng;
  - (c) backfill lỗi thì không gọi `apply` và trả 1;
  - (d) co rút >50% thì không gọi `apply`, có gửi Telegram và trả 1;
  - (e) đường bình thường gọi `apply`, in đúng them/bo và trả 0;
  - (f) `--dry-run` không gọi backfill lẫn `apply`.

### 1.4 `trading/scheduler/main.py`
- Trong nhánh `evening_jobs`, **sau** daily-data-check, thêm `run_job(label="universe-refresh", log_file="universe-refresh.log", command=[python_exe, "-m", "scripts.refresh_universe"], timeout_seconds=3600, lock_id=ADVISORY_LOCK_CATCHUP, ...)`. Dùng chung khóa catchup để không chạy chồng một catchup gọi SSI. Đặt hằng `TIMEOUT_UNIVERSE_REFRESH_SECONDS = 3600`.
- Không chạy ở morning và startup.
- Kiểm chứng: sửa hoặc thêm test trong `tests/test_scheduler.py` để chứng minh evening gọi đủ 3 job theo đúng thứ tự, còn morning vẫn chỉ gọi catchup. **Giữ nguyên** `test_scheduler_loop_once` với đồng hồ tất định và `monkeypatch.delenv("PYTHONPATH")`; không viết lại test này.

### 1.5 `scripts/heartbeat_check.py`
- Thêm `"universe-refresh": JobExitPolicy(branch="universe-refresh", log_file="universe-refresh.log", label="universe-refresh", normal_exit_codes=frozenset({0}), reason="refresh_universe.py. Mã 0 là làm mới xong hoặc chưa tới hạn; mã 1 là backfill lỗi hoặc cổng co rút chặn (cổng đã gửi Telegram).")`. Nếu dict này có test đếm hoặc liệt kê khóa thì cập nhật cho khớp.

### 1.6 Tài liệu
- `DEPLOYMENT.md`: trong mục service `scheduler`, thêm một dòng mô tả universe-refresh (21:45 ngày giao dịch, tối đa 1 lần mỗi 6 ngày, có cổng co rút 50%). `tests/test_deployment_doc.py` phải pass, nhất là kiểm tra mọi `scripts/...` được nhắc đều tồn tại.

## 2. KHÔNG được đụng
- `scripts/startup_catchup.py` (chỉ import, không sửa).
- `load_symbols`, `resolve_use_universe_symbols`, ngưỡng mặc định của `screen_liquidity`.
- Engine, collector, `trading/storage/db.py` (đã có đủ `read_symbol_universe`, `read_active_universe`, `get_backfill_progress`).
- Không chạy `scripts/refresh_universe.py` thật, không chạy `screen_liquidity` không có `--dry-run`, không chạy `sched.sh`. Lead sẽ tự chạy lần đầu.
- Không commit, không push. Gặp dead code hoặc vấn đề ngoài phạm vi thì báo lại, không tự sửa.

## 3. Tiêu chí hoàn thành (gửi kèm bằng chứng)
1. `uv run pytest tests/test_backfill_universe*.py tests/test_screen_liquidity*.py tests/test_refresh_universe.py tests/test_scheduler.py tests/test_heartbeat_check.py tests/test_deployment_doc.py -q`: dán dòng tổng kết. Tên file test hiện có thì dùng `ls tests | grep` để tìm.
2. `uv run pytest -m "not integration" -q`: dán dòng tổng kết (số passed/deselected thật, không làm tròn).
3. `uv run ruff check trading scripts tests`: sạch với các file đã sửa.
4. `node .gitnexus/run.cjs detect-changes --scope all --repo .`: dán danh sách symbol bị ảnh hưởng.
5. Bảng liệt kê từng file đã sửa, kèm task (1.1–1.6) mà từng thay đổi truy về.
