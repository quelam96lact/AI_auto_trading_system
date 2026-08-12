# Kế hoạch: engine tests tự dọn stream BARS (đóng nốt C1)

Ngày giao: 2026-08-12. Nhánh: `feature/data-layer`. Base: `ef7ae0a`.

## Bối cảnh — đọc trước khi làm

Sau commit `ef7ae0a`, stream `BARS` vẫn còn **25 message** sau mỗi lần chạy full
suite (đo được, xác định qua 3 lần: 25/25/25). Nguồn là engine tests trong
`tests/test_engine_main.py`.

25 message đó bị purge bởi fixture `reset_stream_and_durable_consumer` ở đầu
engine test **đầu tiên của lần chạy KẾ TIẾP**. Nghĩa là isolation của toàn bộ
engine tests phụ thuộc vào **đúng một lần purge thành công** — đúng điểm gãy
đơn mà `d62384d` chỉ ra. Nhiệm vụ lần này là xoá bỏ điểm gãy đó.

**Nguyên nhân gốc của flake NATS vẫn chưa biết.** Việc này KHÔNG phải là sửa
flake. Nó là loại bỏ điều kiện cần. Đừng viết bất kỳ câu nào tuyên bố đã tìm ra
nguyên nhân.

## Việc cần làm

Chỉ sửa **`tests/test_engine_main.py`**, và chỉ fixture
`reset_stream_and_durable_consumer` (dòng 81-99).

Hiện fixture chỉ dọn **trước** test. Chuyển nó thành fixture có cả teardown
(`yield`) để dọn **cả sau** test. Mục tiêu: sau khi chạy xong full suite, stream
`BARS` còn **0 message**.

### Ràng buộc

- **Không** sửa `_reset_stream_and_consumer()` (dòng 62-78). Phần assert nghiêm
  ngặt ở đó là dành cho SETUP — nơi message sót thật sự làm hỏng test.
- Phần teardown **không được assert / không được raise**. Nếu teardown fail thì
  nó sẽ che mất lỗi thật của chính test đó, biến một lỗi rõ ràng thành một lỗi
  khó đọc. Teardown chỉ cần dọn.
- Không đụng `tests/test_publisher.py` (vừa sửa ở `ef7ae0a`), không đụng
  `trading/bus/publisher.py`, không đụng bất kỳ file production nào.
- Giữ nguyên toàn bộ comment tiếng Việt đã có trong fixture — chúng ghi lại lý
  do lịch sử, không phải rác.
- Lưu ý `test_fixture_fails_loudly_when_stream_not_empty` (dòng 102) **cố ý** để
  lại message `bars.FIXTURE_PROBE` bằng cách monkeypatch `purge_stream`. Teardown
  phải dọn được cả message đó. Monkeypatch chỉ áp lên object `js` cục bộ của test
  nên connection riêng của fixture không bị ảnh hưởng — nhưng hãy tự kiểm chứng
  điều này bằng phép đo, đừng tin lời tôi.

## Kiểm chứng (bắt buộc đủ 4 bước, dán output THẬT)

1. **Full suite → 0.** Chạy `uv run pytest -q`, rồi đếm message trong `BARS`.
   Có sẵn probe: `uv run python scripts/.probe_bars_count.py` (đã gitignored).
   → **Kỳ vọng: `BARS messages = 0`** (trước khi sửa là 25).

2. **Lặp lại 3 lần.** → **Kỳ vọng: 0, 0, 0.**

3. **Sức phân biệt (BẮT BUỘC).** Comment phần teardown đi, chạy lại full suite,
   đếm. → **Kỳ vọng: quay lại 25** (chứng minh teardown thật sự là thứ tạo ra
   con số 0, không phải trùng hợp). Khôi phục, chạy lại, xác nhận về 0.

4. **Teardown không che lỗi.** Cố ý làm một engine test bất kỳ fail (sửa một
   assert), chạy nó, xác nhận thông báo lỗi hiện ra vẫn là **assert của test
   đó**, không phải lỗi từ teardown. Khôi phục.
   → kiểm chứng bằng: dán vài dòng đầu của phần FAILED.

5. `uv run pytest -q` xanh toàn bộ (kỳ vọng 242 passed) và
   `uv run ruff check trading tests`.

## Không được làm

- Không commit, không push.
- Không "tiện thể" sửa test nào khác.
- Không tuyên bố đã tìm ra nguyên nhân flake.

## Báo cáo

Dán output thật của cả 5 bước. Nếu bước 3 không quay lại 25, nói thẳng — nghĩa
là phân tích nguồn rác của tôi sai và cần xem lại trước khi commit.
