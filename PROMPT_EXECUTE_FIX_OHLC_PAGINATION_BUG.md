# Prompt thực thi: Fix bug phân trang trùng lặp + thiếu dữ liệu ở 2 spike script OHLC

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `scripts/spike_ssi_sdk_derivative_ohlc_stream.py` (hàm
`fetch_ohlc_5m_2months`), `scripts/spike_ssi_sdk_equity_10y_history.py` (hàm
`fetch_daily_10y`), và `trading/collector/backfill.py` dòng 102-136
(`SSIRestClientLegacy._paged_rows` — pattern chia theo chunk ngày đã dùng
trước đây, ổn định, không phụ thuộc `pageIndex` server có hoạt động đúng
kiểu OFFSET hay không).

---

## ⚠️ Bối cảnh — bug thật đã xác nhận

Chạy thật `fetch_ohlc_5m_2months("41I1G8000")` (2 tháng gần nhất, `size=1000`,
lặp `page=1,2,3...` tới khi trang < 1000):
- Nhận **2028 dòng** raw nhưng chỉ có **1014 timestamp duy nhất** — 514
  timestamp bị lặp (có timestamp lặp tới 3 lần).
- **Nghiêm trọng hơn**: khoảng ngày request là "2 tháng gần nhất" (~60 ngày,
  từ khoảng 2026-05-27), nhưng dữ liệu thật nhận được chỉ trải từ
  **2026-06-19** đến nay — **THIẾU ~3.5 tuần dữ liệu cũ nhất**. Vòng lặp
  `page=1,2,3` đã "tốn" 2 trang đầu vào dữ liệu trùng lặp/chồng lấn thay vì
  tiến tới phần dữ liệu cũ hơn, rồi dừng sớm ở trang 3 (chỉ 28 dòng, < 1000)
  trước khi phủ hết 60 ngày yêu cầu.

**Nguyên nhân nghi ngờ**: tham số `pageIndex` gửi lên SSI (xác nhận qua
`inspect.getsource` — `OHLCRequest.to_dict()` gửi `pageIndex`/`pageSize`)
có thể KHÔNG hoạt động theo kiểu OFFSET chuẩn (page sau = dữ liệu tiếp theo)
như code hiện tại giả định — đây là giả định CHƯA được verify thật khi viết
2 hàm này ban đầu, giờ có bằng chứng thật cho thấy giả định đó sai.

`scripts/spike_ssi_sdk_equity_10y_history.py::fetch_daily_10y()` dùng
**y hệt pattern `page += 1` này** cho 10 năm dữ liệu ngày — nhiều khả năng
dính cùng bug (thiếu dữ liệu ở phần xa nhất), dù chưa có bằng chứng thật vì
hàm này chưa từng chạy xong lần nào tạo ra output.

---

## ⚠️ Giới hạn phạm vi

**Chỉ sửa 2 file đã có, KHÔNG tạo file mới:**
1. `scripts/spike_ssi_sdk_derivative_ohlc_stream.py` — sửa `fetch_ohlc_5m_2months`.
2. `scripts/spike_ssi_sdk_equity_10y_history.py` — sửa `fetch_daily_10y`.

**KHÔNG sửa** `trading/collector/backfill.py` hay bất kỳ production code
nào khác trong task này — file đó chỉ dùng để THAM KHẢO pattern, việc
`_paged_intraday()` trong production có dính bug tương tự hay không là
CÂU HỎI RIÊNG, không thuộc phạm vi task này (báo cáo lại nếu thấy dấu hiệu,
không tự sửa).

**KHÔNG sửa** `scripts/backfill_spike_data_to_db.py` — không cần đổi, upsert
theo `(symbol, ts)` đã tự xử lý đúng dù input có trùng lặp.

**KHÔNG tự commit, không tự push.**

---

## Task — Bước 1: Điều tra thật (BẮT BUỘC trước khi chọn cách fix)

Trước khi sửa code, chạy lại `fetch_ohlc_5m_2months("41I1G8000")` với 1 dòng
debug thêm vào, in ra **ngày đầu/ngày cuối của mỗi trang** để xác nhận thật
hành vi server (không đoán tiếp):
```python
print(f"  page {page}: {len(rows)} bar, "
      f"từ {rows[0].trading_date if rows else '-'} "
      f"đến {rows[-1].trading_date if rows else '-'}")
```
Ghi lại kết quả quan sát được (page 1/2/3 có thực sự lấy 3 khoảng ngày khác
nhau, hay page 1 và 2 trả đúng y hệt cùng 1 khoảng?) — đây là bằng chứng
quyết định cách fix ở bước 2.

## Task — Bước 2: Fix bằng chia theo khoảng ngày (không dựa vào pageIndex)

Bất kể kết quả điều tra ở bước 1 ra sao, cách fix AN TOÀN nhất (không phụ
thuộc `pageIndex` có đúng kiểu OFFSET hay không) là **tự chia nhỏ khoảng
ngày request thành nhiều chunk nhỏ, mỗi chunk gọi 1 lần với `size` đủ lớn để
chắc chắn chunk đó chỉ cần 1 trang** (giống tinh thần
`SSIRestClientLegacy._paged_rows`, nhưng đơn giản hơn — không cần
`pageIndex` nếu chunk đủ nhỏ):

```python
async def fetch_ohlc_5m_2months(symbol: str) -> None:
    from ssi_sdk import AsyncData

    async with await make_auth() as auth:
        data = AsyncData(auth)
        to_date = datetime.now(VN_TZ).date()
        start_date = to_date - timedelta(days=60)

        bars_by_ts: dict[str, dict] = {}  # key = trading_date string, dedupe tự nhiên
        chunk_start = start_date
        while chunk_start <= to_date:
            chunk_end = min(chunk_start + timedelta(days=6), to_date)  # chunk 7 ngày
            from_str = f"{chunk_start:%Y/%m/%d} 00:00:00"
            to_str = f"{chunk_end:%Y/%m/%d} 23:59:59"
            print(f"Gọi chunk {from_str} -> {to_str}...")
            rows = await data.market_data.get_ohlc_5minute_historical(
                symbol, from_str, to_str, page=1, size=1000
            )
            print(f"  nhận {len(rows)} bar (chunk 7 ngày, kỳ vọng << 1000)")
            for r in rows:
                bars_by_ts[r.trading_date] = r  # dedupe theo timestamp, ghi đè nếu trùng
            chunk_start = chunk_end + timedelta(days=1)

        all_rows = sorted(bars_by_ts.values(), key=lambda r: r.trading_date)
        payload = [dataclasses.asdict(r) for r in all_rows]
        OHLC_5M_2M_OUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"Tổng {len(all_rows)} bar 5 phút DUY NHẤT (2 tháng) → {OHLC_5M_2M_OUT}")
        if all_rows:
            print("Bar đầu:", payload[0])
            print("Bar cuối:", payload[-1])
```
Nếu 1 chunk 7 ngày vẫn trả đúng 1000 dòng (nghĩa là 7 ngày cũng vượt 1 trang
— khó xảy ra với 5 phút phái sinh nhưng cứ phòng), in cảnh báo rõ ràng thay
vì âm thầm mất dữ liệu, không cần tự động giảm chunk nhỏ hơn (báo cáo lại
cho Claude quyết định).

Áp dụng **cùng pattern chunk theo ngày** (dùng chunk lớn hơn, ví dụ 90 ngày,
vì dữ liệu NGÀY thưa hơn 5 phút rất nhiều) cho `fetch_daily_10y()` trong
`scripts/spike_ssi_sdk_equity_10y_history.py` — thay `page += 1` loop hiện
tại bằng vòng lặp chunk theo ngày tương tự, dedupe theo `trading_date` giống
hệt.

**Xoá logic `page`/`while True: ... page += 1 ... page > 20` cũ trong CẢ 2
hàm** — thay hoàn toàn bằng chunk-theo-ngày, không giữ song song 2 cách.

---

## Kiểm chứng

```bash
uv run --with ssi-sdk python -c "
import ast
ast.parse(open('scripts/spike_ssi_sdk_derivative_ohlc_stream.py', encoding='utf-8').read())
ast.parse(open('scripts/spike_ssi_sdk_equity_10y_history.py', encoding='utf-8').read())
print('OK: syntax hop le')
"
```
`grep -n "place_order\|place_limit_order\|place_market_order\|place_fco_\|cancel_order"`
trên cả 2 file — phải rỗng (không đổi).

**Chạy thật lại** cả 2 script, xác nhận:
1. `fetch_ohlc_5m_2months("41I1G8000")`: tổng số bar DUY NHẤT (không trùng),
   và **bar đầu tiên phải có ngày ≈ 60 ngày trước hôm nay** (không còn thiếu
   3.5 tuần như lần trước) — nếu SSI thực sự giới hạn range ngắn hơn 60 ngày
   (không phải bug code mà là giới hạn API thật), in rõ và báo lại, KHÔNG cố
   ép đủ 60 ngày bằng cách khác.
2. `fetch_daily_10y()` cho 3 mã bất kỳ: tổng bar + ngày đầu/ngày cuối, xem có
   phủ gần 10 năm không hay bị giới hạn ngắn hơn (báo cáo thật, không giả định).

---

## Báo cáo lại

1. Kết quả điều tra bước 1 (log page-by-page ngày đầu/cuối trước khi fix).
2. Diff đầy đủ cả 2 file sau khi fix.
3. Kết quả chạy thật (bar count, ngày đầu/cuối) cho cả derivative và ít nhất
   1-2 mã cổ phiếu.
4. `ast.parse` + grep + kết quả `uv run pytest -q -m "not integration"`
   (phải vẫn đúng baseline, không có test nào liên quan 2 file này).

Sau khi có dữ liệu thật đúng (đủ 60 ngày / gần 10 năm), chạy lại
`scripts/backfill_spike_data_to_db.py` (không cần sửa file này) để đồng bộ
DB với dữ liệu đã fix — upsert theo `(symbol, ts)` sẽ tự cập nhật đúng, không
cần xoá dữ liệu cũ trước.

Không tự commit — chờ Claude audit.
