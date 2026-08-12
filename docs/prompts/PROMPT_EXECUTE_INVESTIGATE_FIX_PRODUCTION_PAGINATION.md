# Prompt thực thi: Điều tra + fix (nếu xác nhận) bug phân trang trong production `backfill.py`

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `trading/collector/backfill.py` (đặc biệt `SSIRestClient._paged_intraday`
dòng 234-252, `run_backfill()` dòng 255-273), `tests/test_backfill.py`,
`scripts/spike_ssi_sdk_derivative_ohlc_stream.py` (bản đã fix, commit `95f563f`
— tham khảo cách chunk-theo-ngày đã chứng minh hoạt động đúng).

---

## ⚠️ Bối cảnh — vì sao nghi ngờ production dính bug

Spike gần đây xác nhận thật (không phải đoán): `get_ohlc_5minute_historical(symbol,
from, to, page=N, size=1000)` của ssi-sdk **KHÔNG phân trang kiểu OFFSET chuẩn**
— `page=2` trả lại gần như y hệt cửa sổ dữ liệu của `page=1` (mỗi bản ghi bị lặp),
khiến vòng lặp tốn hết "ngân sách" trang vào dữ liệu trùng thay vì tiến tới dữ
liệu cũ hơn, và **âm thầm mất dữ liệu** ở phần xa nhất của khoảng ngày yêu cầu.

`SSIRestClient._paged_intraday()` trong `trading/collector/backfill.py` (dùng
CHO PRODUCTION — service `collector` thật) gọi **CÙNG METHOD SDK**
(`get_ohlc_5minute_historical`) với **CÙNG HEURISTIC PHÂN TRANG** (`page += 1`
tới khi trang trả < `size`) — nhiều khả năng dính đúng bug này khi khoảng
`(frm, to)` đủ lớn để vượt 1000 dòng 5 phút (~1 tuần dữ liệu 5 phút của 1 mã
thanh khoản cao).

**Mức độ ảnh hưởng thực tế hiện tại**: `run_backfill()` (dòng 255-273) gọi
`intraday_ohlc(sym, frm, today)` với `frm = last.astimezone(TZ).date() if last
else today - timedelta(days=7)` — nghĩa là trong vận hành bình thường (backfill
gap nhỏ, ≤7 ngày), số dòng 5 phút thường KHÔNG vượt 1000, nên `page` có thể
chưa từng thực sự vượt quá 1 trong thực tế. Nhưng nếu collector down lâu ngày,
hoặc backfill lần đầu cho 1 mã mới với gap lớn hơn, bug này sẽ kích hoạt và
làm mất dữ liệu bar mà không có cảnh báo nào — cần điều tra + fix trước khi
xảy ra thật.

**KHÔNG được giả định bug này chắc chắn tồn tại chỉ vì spike script đã gặp** —
phải tự verify thật trên đúng code path `_paged_intraday()` (tham số/endpoint
gọi có thể khác biệt nhỏ) trước khi sửa, đúng nguyên tắc dự án.

---

## ⚠️ Giới hạn phạm vi

**Chỉ được sửa:**
1. `trading/collector/backfill.py` — CHỈ sửa `SSIRestClient._paged_intraday()`.
   **KHÔNG sửa** `daily_ohlc()`, `run_backfill()`, `SSIRestClientLegacy`, hay
   bất kỳ hàm nào khác trong file này.
2. `tests/test_backfill.py` — thêm test mới cho `_paged_intraday()`.

**KHÔNG sửa** `trading/collector/main.py`, `trading/engine/*`, hay bất kỳ file
production nào khác ngoài 2 file trên.

**KHÔNG tự commit, không tự push.**

---

## Task — Bước 1: Điều tra thật trên đúng code path (BẮT BUỘC trước khi sửa)

Viết 1 script tạm (KHÔNG cần giữ lại, có thể xoá sau khi điều tra xong, hoặc
đặt tạm trong `scripts/` rồi báo cáo có xoá hay không) gọi trực tiếp
`SSIRestClient._paged_intraday()` (hoặc `intraday_ohlc()`) với 1 mã thanh
khoản cao (vd `VCB`, đã có trong `config/config.yaml`) và khoảng `frm`/`to`
đủ rộng để chắc chắn vượt 1000 dòng (vd 20 ngày gần nhất). Log rõ mỗi trang:
số dòng, ngày đầu/ngày cuối của trang đó (giống cách đã làm ở spike derivative
trước — xem `PROMPT_EXECUTE_FIX_OHLC_PAGINATION_BUG.md` bước điều tra).

Ghi lại kết quả quan sát được: page 2 có thực sự lặp lại phần lớn dữ liệu
page 1 không? Có bị mất dữ liệu ở đầu khoảng ngày yêu cầu (20 ngày trước)
không?

## Task — Bước 2: Fix (CHỈ nếu bước 1 xác nhận bug thật xảy ra)

Nếu xác nhận: thay thế cơ chế `page += 1` trong `_paged_intraday()` bằng
chunk-theo-ngày (giống pattern đã chứng minh hoạt động ở
`spike_ssi_sdk_derivative_ohlc_stream.py::fetch_ohlc_5m_2months`, commit
`95f563f`) — chunk 7 ngày, dedupe theo `trading_date` (dict), **giữ nguyên
signature `async def _paged_intraday(self, data, symbol: str, frm: date, to:
date)`** và giá trị trả về (`list[OHLCData]`, chưa qua `_ohlc_rows_to_bars`)
để không phải sửa `intraday_ohlc()` gọi nó.

Nếu bước 1 KHÔNG xác nhận được bug (vd server trả đúng, không lặp/không mất
dữ liệu trong code path này dù spike script kia có vấn đề) — **KHÔNG sửa gì
cả**, báo cáo lại lý do và bằng chứng, dừng ở đây.

## Task — Bước 3: Test tái hiện bug (viết TRƯỚC khi fix, theo đúng nguyên tắc dự án)

Thêm 1 test mới trong `tests/test_backfill.py` mock `data.market_data.
get_ohlc_5minute_historical` để trả về dữ liệu **giả lập đúng hành vi lỗi đã
quan sát thật** (page 2 lặp lại phần lớn page 1, dẫn tới mất dữ liệu cũ nhất
nếu code không fix) — test này phải **FAIL** với code `_paged_intraday()` cũ
(`page += 1`) và **PASS** sau khi fix. Đặt tên rõ ràng, vd
`test_paged_intraday_dedupes_when_ssi_page_index_overlaps`.

---

## Kiểm chứng

```bash
uv run pytest tests/test_backfill.py -v
uv run pytest -q -m "not integration"
```
Cả 2 phải pass, số lượng test không giảm (chỉ tăng thêm test mới).

`grep -n "place_order\|cancel_order"` trên `trading/collector/backfill.py`
sau khi sửa — phải rỗng (vốn đã rỗng, không được thêm mới).

---

## Báo cáo lại

1. Kết quả điều tra bước 1 (log per-page, có bug thật hay không trên đúng
   code path này — không chỉ suy luận từ spike script khác).
2. Nếu có fix: diff đầy đủ `trading/collector/backfill.py` +
   `tests/test_backfill.py`.
3. Nếu KHÔNG có bug thật trên code path này: giải thích rõ vì sao khác với
   spike script (vd request params khác, hay may mắn chưa từng vượt 1 trang
   trong lần test) — không tự bịa lý do, chỉ báo cáo bằng chứng quan sát được.
4. Kết quả 2 lệnh pytest ở trên.

Không tự commit — chờ Claude audit (sẽ tự chạy lại investigation script nếu
cần để xác nhận độc lập).
