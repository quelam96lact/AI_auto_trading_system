# Brief đợt 196: `backfill_universe.py` lọc nến giá 0 ở đường 5 phút

- **Ngày:** 25/10/2026.
- **Vai trò:** agent viết test và code, tự kiểm chứng. Claude audit, commit và push.
- **Agent KHÔNG được:**
  - commit hay push;
  - chạy script thật, tức gọi SSI hay ghi DB;
  - chạy `scripts/sched.sh`;
  - đọc `.env`;
  - sửa file nào ngoài hai file ở §2.

## 0. Vấn đề (Claude đã kiểm 25/10)

- **Hai đường nạp 5 phút hiện không đồng nhất:**
  - `trading/collector/backfill.py::run_backfill` (đường nạp của collector) **lọc** nến bẩn bằng `trading.data_quality.is_dirty_bar` trước `write_bars`, từ đợt 109, commit dcda990.
  - `scripts/backfill_universe.py::backfill_one`, nhánh `timeframe == "5m"`, gọi `storage.write_bars(bars)` **không lọc gì**.
- **Bằng chứng:** khi nạp 5 phút 10/08 → 23/10 cho 303 mã ngày 25/10, SSI trả **58 nến bẩn**. Lần đó Claude dùng runner riêng có lọc. Nếu dùng `backfill_universe.py --timeframe 5m` thì 58 nến đó đã vào `bars`.
  - Đợt 01/10 đã phải xoá 261 nến như vậy. Một nến giá 0 làm ATR(14) phồng khoảng 100 lần.
- **Nhánh `1d` cố ý KHÔNG lọc**, và brief này **không đổi nó**. 71.439 dòng giá 0 trong `bars_daily` là ngày không giao dịch thật do nguồn ghi. Chốt chặn nằm ở đường đọc (`39a7e40`). Xem memory `nen-gia-0-ato-atc-trong-bars`.
- **Ai bị ảnh hưởng:** job hằng đêm (`sched.sh backfill`) chỉ chạy `--timeframe 1d`, nên không đổi hành vi. Đường 5 phút chỉ chạy tay.
  - GitNexus không tìm thấy `backfill_one`, kết quả là `UNKNOWN`. Claude đã tìm văn bản: caller duy nhất là `run()` trong cùng file và `tests/test_backfill_universe.py`.

## 1. Luật (chốt)

Trong `backfill_one`, nhánh `5m`:
1. Sau `client.intraday_ohlc(...)`, bỏ mọi nến có `is_dirty_bar(b)` đúng. **Import** từ `trading.data_quality`, không chép điều kiện `<= 0`.
2. Chỉ ghi nến sạch bằng `storage.write_bars(...)`.
3. `last_done_date` tính trên **nến sạch**. Không có nến sạch nào thì không tiến, giống luật "rỗng" hiện có. Nguyên tắc là không ghi nhận độ phủ mình không có.
4. `attempted_until = to` như cũ, vì đã hỏi API tới đó.
5. `detail` trả về ghi thêm số nến bị bỏ khi lớn hơn 0, ví dụ `"1200 bar, bo 3 bar rac"`. Script không gửi Telegram; thông tin này đi vào log qua dòng tiến độ hiện có.

**Nhánh `1d` giữ nguyên từng dòng.**

## 2. Phạm vi file

- **Được sửa:**
  - `scripts/backfill_universe.py`: chỉ phần nhánh `5m` của `backfill_one`, cộng một dòng import và một dòng docstring đầu file nói rằng đường 5 phút lọc nến bẩn;
  - `tests/test_backfill_universe.py`: thêm `write_bars` vào `FakeStorage`, thêm `intraday_ohlc` vào `FakeClient`, thêm test mới.
- **Không đụng:**
  - `trading/collector/backfill.py`, `trading/data_quality.py`, `trading/storage/db.py`, `scripts/sched.sh`;
  - mọi test hiện có. Test cũ phải xanh nguyên trạng, không sửa.
- **Giữ style hiện có:** chú thích tiếng Việt không dấu như phần dưới của file. Không refactor, không đổi tên.
- **GitNexus:**
  - chạy `context` cho `is_dirty_bar` trước khi sửa, và `detect-changes --scope all` sau khi sửa;
  - dùng `node .gitnexus/run.cjs` hoặc `gitnexus`, **không npx**;
  - `backfill_one` có thể không có trong index; ghi nguyên văn kết quả.

## 3. Các bước

1. **Viết test trước** trong `tests/test_backfill_universe.py`, gọi `backfill_one(..., "5m", ...)` thật với fake. Chạy để thấy chúng đỏ trên code hiện tại, rồi ghi tên test đỏ.
   - `test_5m_drops_dirty_bars_before_write`: client trả 3 nến sạch và 2 nến bẩn. Một nến bẩn có `close = 0`, một có `open = 0` còn các giá khác dương. Assert:
     - `write_bars` nhận đúng 3 nến sạch;
     - `status == "ok"`;
     - `detail` chứa số `2`.
   - `test_5m_last_done_date_ignores_dirty_bars`: nến sạch cuối ngày 05/08, nến bẩn ngày 07/08, `to` là 18/08. Assert `last_done_date == 05/08` và `attempted_until == 18/08`.
   - `test_5m_all_dirty_does_not_advance_last_done_date`: progress cũ có `last_done_date` 01/08, client chỉ trả nến bẩn. Assert:
     - không ghi nến nào, tức danh sách ghi rỗng hoặc không gọi;
     - `last_done_date` vẫn là 01/08;
     - `attempted_until == to`.
   - `test_1d_still_writes_zero_price_bars_unchanged`: nhánh `1d` với một nến giá 0. Assert `write_daily` nhận **đủ** nến kể cả nến giá 0. Test này canh luật "cố ý không lọc" ở §0.

   → kiểm chứng bằng: 3 test 5m đỏ, test 1d xanh, trên code chưa sửa.
2. **Sửa `backfill_one`** theo §1. → kiểm chứng bằng: cả 4 test mới xanh, mọi test cũ trong file xanh, không sửa test cũ.
3. **Tự phá thử** rồi khôi phục, mỗi lần chạy lại file test và ghi test nào đỏ:
   - bỏ dòng lọc;
   - lọc cả nhánh `1d`;
   - tính `last_done_date` trên nến thô.

   → kiểm chứng bằng: mỗi phép phá làm đỏ ít nhất một test mới.
4. **Kiểm toàn bộ:**
   - `uv run pytest tests/test_backfill_universe.py -v`;
   - `uv run pytest -m "not integration" -q`, ghi số passed trước và sau;
   - `uv run ruff check scripts/backfill_universe.py tests/test_backfill_universe.py`;
   - `uv run pyright scripts/backfill_universe.py tests/test_backfill_universe.py`.

   → kiểm chứng bằng: tất cả sạch, số passed sau = trước + 4.

## 4. Báo cáo agent phải nộp

1. GitNexus trước và sau, chép nguyên văn phần tóm tắt.
2. Diff của `scripts/backfill_universe.py`. Mọi dòng đổi phải truy được về §1.
3. Danh sách `def test_` mới; kết quả bước 1 (đỏ) và bước 3 (bảng phá thử).
4. Số passed trước và sau; ruff và pyright nguyên văn.
5. Cam kết: không chạy script thật, không gọi SSI, không ghi DB, không chạy `sched.sh`, không commit, không push.

## 5. Claude làm sau khi nhận

- Tự đếm `def test_`, chạy lại test và tự chạy ba phép phá ở bước 3.
- Kiểm diff không đụng nhánh `1d`.
- Chạy `detect-changes`, rồi commit và push.
- Cập nhật memory `du-lieu-5m-rong-chi-den-07-08`: xoá dòng "lỗ hổng repo" và ghi commit sửa.
