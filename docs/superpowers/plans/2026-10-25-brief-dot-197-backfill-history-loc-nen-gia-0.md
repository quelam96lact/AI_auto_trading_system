# Brief đợt 197: `backfill_history.py` lọc nến giá 0 ở đường 5 phút

- **Ngày:** 25/10/2026.
- **Vai trò:** agent viết test và code, tự kiểm chứng. Claude audit, commit và push.
- **Agent KHÔNG được:**
  - commit hay push;
  - chạy script thật, tức gọi SSI hay ghi DB;
  - chạy `scripts/sched.sh`;
  - đọc `.env`;
  - sửa file nào ngoài hai file ở §2.

## 0. Vấn đề (Claude đã kiểm 25/10)

- **Chỗ hổng còn lại sau đợt 196** (`255b2d8`):
  - Đợt 196 đã cho `scripts/backfill_universe.py` lọc nến bẩn ở đường 5 phút.
  - `scripts/backfill_history.py::backfill_history` dòng 50–51 vẫn gọi `client.intraday_ohlc(...)` rồi `storage.write_bars(intraday)` **không lọc gì**.
- **Các đường ghi 5 phút khác** Claude đã soát bằng `.write_bars(` ngoài `tests/` và `docs/`:
  - `trading/collector/backfill.py::run_backfill` lọc từ đợt 109;
  - `trading/collector/main.py` ghi nến stream, đã chặn ở nguồn từ đợt 109;
  - `backfill_universe.py` lọc từ đợt 196.
  - Chỉ còn file này.
- **Ai bị ảnh hưởng:** đây là script nạp lịch sử dài, chạy tay một lần.
  - `sched.sh` không gọi nó.
  - Tìm văn bản ngoài `docs/`: chỉ có chính file và `tests/test_backfill_history.py`.
- **GitNexus:** `impact backfill_history --direction upstream` báo **risk CRITICAL, 263 symbol**. Claude đã mở kết quả ra kiểm:
  - Caller trực tiếp chỉ có `_run`, một hàm lồng trong `main()` của cùng file.
  - Từ độ sâu 2, danh sách gồm hàng chục script không liên quan, ví dụ `backup_check.py`, `bingx_klines.py`, `check_golive_gate.py`. Đó là do mọi script đều có một hàm tên `main` nên index nối nhầm, không phải lời gọi thật.
  - Claude coi CRITICAL này là dương tính giả do trùng tên. Agent vẫn phải chạy `impact` và chép nguyên văn phần `summary` cùng các caller ở độ sâu 1.
- **Nhánh nến ngày (`write_daily`) cố ý KHÔNG lọc**, giống đợt 196. Dòng giá 0 trong `bars_daily` là ngày không giao dịch thật; chốt chặn nằm ở đường đọc (`39a7e40`).

## 1. Luật (chốt)

Trong `backfill_history`, với mỗi mã:
1. Sau `client.intraday_ohlc(...)`, bỏ mọi nến có `is_dirty_bar(b)` đúng. **Import** từ `trading.data_quality`, không chép điều kiện `<= 0`.
2. Chỉ ghi nến sạch bằng `storage.write_bars(...)`.
3. `counts[sym]["intraday"]` là **số nến sạch đã ghi**. **Không thêm khoá mới** vào `counts`: test cũ so sánh cả dict.
4. **Dòng in tiến độ:**
   - dòng in đầu tiên của mỗi mã ghi thêm `, bo N bar rac` khi N > 0, và chỉ khi N > 0;
   - dòng `5m dau / 5m cuoi` tính trên **nến sạch**;
   - nếu không còn nến sạch thì không in dòng này, giống điều kiện `if intraday:` hiện có.
5. **Phần nến ngày giữ nguyên từng dòng:** `daily_ohlc`, `write_daily`, `counts["daily"]`, dòng in `daily dau / daily cuoi`.

## 2. Phạm vi file

- **Được sửa:**
  - `scripts/backfill_history.py`: chỉ thân vòng lặp `for sym in symbols:` phần 5 phút, cộng một dòng import và một câu trong docstring đầu file nói rằng đường 5 phút lọc nến bẩn;
  - `tests/test_backfill_history.py`: thêm test mới. Nếu cần client trả nến tuỳ ý, **thêm một fake mới**, ví dụ `BarsFakeClient(intraday, daily)`. Không sửa `FakeClient` hay `FakeStorage` cũ.
- **Không đụng:**
  - `main()`, `range_from_days_back`;
  - `trading/data_quality.py`, `trading/collector/backfill.py`, `scripts/backfill_universe.py`, `scripts/sched.sh`;
  - mọi test hiện có. Hai test cũ phải xanh nguyên trạng.
- **Giữ style hiện có:** chú thích, chuỗi in tiếng Việt không dấu. Không refactor, không đổi tên.
- **GitNexus:**
  - trước khi sửa: chạy `context` cho `is_dirty_bar` và `impact backfill_history --direction upstream`;
  - sau khi sửa: chạy `detect-changes --scope all`;
  - dùng `node .gitnexus/run.cjs` hoặc `gitnexus`, **không npx**.

## 3. Các bước

1. **Viết test trước** trong `tests/test_backfill_history.py`, gọi `backfill_history(...)` thật với fake. Chạy để thấy chúng đỏ trên code hiện tại, rồi ghi tên test đỏ.
   - `test_intraday_drops_dirty_bars_before_write`: một mã, client trả 2 nến 5 phút sạch và 2 nến bẩn (một có `close = 0`, một có `low = 0`, các giá khác dương). Assert:
     - `storage.bars` đúng bằng 2 nến sạch;
     - `counts[sym]["intraday"] == 2`.
   - `test_intraday_all_dirty_writes_nothing_and_does_not_crash`: client chỉ trả nến 5 phút bẩn, nến ngày bình thường. Assert:
     - không lỗi, tức không có `IndexError` khi in;
     - `storage.bars == []`;
     - `counts[sym]["intraday"] == 0`;
     - nến ngày vẫn được ghi.
   - `test_progress_line_reports_dropped_count` (dùng `capsys`): với 2 nến bẩn, output chứa `bo 2 bar rac`. Chạy lại với 0 nến bẩn: output **không** chứa `bar rac`.
   - `test_daily_still_writes_zero_price_bars_unchanged`: nến ngày có một nến `close = 0` và một nến sạch. Assert:
     - `storage.daily` có **đủ** 2 nến;
     - `counts[sym]["daily"] == 2`.

   → kiểm chứng bằng: 3 test đầu đỏ, test nến ngày xanh, trên code chưa sửa. Ghi rõ nếu test thứ hai đỏ vì một lý do khác lý do dự kiến.
2. **Sửa `backfill_history`** theo §1. → kiểm chứng bằng: cả 4 test mới xanh, 2 test cũ xanh, không sửa test cũ.
3. **Tự phá thử** rồi khôi phục, mỗi lần chạy lại file test và ghi test nào đỏ:
   - bỏ dòng lọc;
   - lọc cả nến ngày;
   - `counts["intraday"]` đếm nến thô;
   - luôn in `bo N bar rac` kể cả khi N = 0.

   → kiểm chứng bằng: mỗi phép phá làm đỏ ít nhất một test mới.
4. **Kiểm toàn bộ:**
   - `uv run pytest tests/test_backfill_history.py -v`;
   - `uv run pytest -m "not integration" -q`, ghi số passed trước và sau;
   - `uv run ruff check scripts/backfill_history.py tests/test_backfill_history.py`;
   - `uv run pyright scripts/backfill_history.py tests/test_backfill_history.py`. Nếu có lỗi, ghi rõ lỗi nào có từ trước, kiểm bằng cách chạy trên bản `git stash`.

   → kiểm chứng bằng: tất cả sạch, hoặc chỉ còn lỗi pyright có từ trước; số passed sau = trước + 4.

## 4. Báo cáo agent phải nộp

1. GitNexus trước và sau, chép nguyên văn phần tóm tắt, kể cả mức risk của `impact`.
2. Diff của `scripts/backfill_history.py`. Mọi dòng đổi phải truy được về §1.
3. Danh sách `def test_` mới; kết quả bước 1 (đỏ) và bước 3 (bảng phá thử).
4. Số passed trước và sau; ruff và pyright nguyên văn.
5. Cam kết: không chạy script thật, không gọi SSI, không ghi DB, không chạy `sched.sh`, không đọc `.env`, không commit, không push.

## 5. Claude làm sau khi nhận

- Tự đếm `def test_` (trước khi sửa là 2), chạy lại test và tự chạy bốn phép phá ở bước 3, cộng phép phá "ghi nến thô nhưng đếm nến sạch".
- Kiểm diff không đụng phần nến ngày, `main()`, `FakeClient` và `FakeStorage` cũ.
- Chạy `detect-changes`, rồi commit và push.
- Cập nhật memory `du-lieu-5m-rong-chi-den-07-08`: xoá dòng "Still unfiltered" và ghi commit sửa.
