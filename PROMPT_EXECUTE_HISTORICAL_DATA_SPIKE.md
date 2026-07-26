# Prompt thực thi: Spike xác nhận lấy dữ liệu lịch sử dài hạn (10 năm cổ phiếu 3 sàn + 2 tháng phái sinh)

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `scripts/spike_ssi_sdk_hnx_upcom_ohlc.py`, `scripts/spike_ssi_sdk_derivative_ohlc_stream.py`,
`scripts/_ssi_spike_common.py`.

---

## ⚠️ Bối cảnh

Spike trước (`spike_ssi_sdk_hnx_upcom_ohlc.py`) đã xác nhận lấy được OHLC 5 phút
thật cho 1 mã HNX + 1 mã UPCOM. Lần này cần verify sâu hơn 2 việc:

1. **Cổ phiếu cơ sở**: lấy dữ liệu **ngày (daily)** trong **10 năm gần đây** cho
   vài mã mỗi sàn (HOSE/HNX/UPCOM) — không chỉ 5 phút gần đây.
2. **Phái sinh**: lấy dữ liệu **5 phút** (SDK không có "10 phút" — 5 phút là
   khung gần nhất, đã chốt với user) cho hợp đồng front-month
   (`41I1G8000`, đã xác nhận ở spike trước) trong **2 tháng gần nhất**.

Cả 2 method (`get_ohlc_1day_historical`, `get_ohlc_5minute_historical`)
**KHÔNG tự phân trang** — trả về tối đa `size` bar (mặc định 1000) cho `page`
được truyền vào. 10 năm dữ liệu ngày ≈ 2500+ phiên, 2 tháng dữ liệu 5 phút cho
phái sinh ≈ 2000-2500 bar — cả 2 đều **có thể vượt 1000**, nên **BẮT BUỘC** phải
tự lặp `page=1,2,3,...` cho đến khi 1 trang trả về ít hơn `size` (nghĩa là hết
dữ liệu). Dùng `size=1000` (giữ mặc định, không đoán server có chấp nhận size
lớn hơn hay không).

**Đây CHỈ là spike đọc dữ liệu — KHÔNG ghi vào DB thật, KHÔNG sửa
`trading/storage/*`, KHÔNG sửa `trading/collector/*`, KHÔNG sửa
`config/config.yaml`.** Việc lưu trữ đã được audit riêng, xác nhận không cần
đổi schema — chỉ cần xác nhận API trả dữ liệu đúng ở bước này.

---

## ⚠️ Giới hạn phạm vi

**Chỉ tạo/sửa các file sau:**
1. Tạo mới `scripts/spike_ssi_sdk_equity_10y_history.py` (Task A).
2. Sửa `scripts/spike_ssi_sdk_derivative_ohlc_stream.py` — **thêm hàm mới**,
   không đổi hàm `fetch_ohlc_sample()`/`record_stream()` đã có (Task B).
3. Cập nhật `.gitignore` (thêm output file mới).

**KHÔNG sửa** bất kỳ file nào khác. **KHÔNG tự commit, không tự push.**

---

## Task A — Cổ phiếu: dữ liệu ngày 10 năm, vài mã mỗi sàn

File mới: `scripts/spike_ssi_sdk_equity_10y_history.py` (copy pattern
`_ssi_spike_common.make_auth()` giống các spike khác).

**Khám phá mã — không hardcode đoán:** với mỗi board (`Board.HOSE`,
`Board.HNX`, `Board.UPCOM`), gọi `get_securities_info_by_board(board)`, lấy
**3 mã đầu tiên** trong danh sách trả về (thay vì chỉ 1 mã như spike trước —
lần này cần chắc chắn hơn 1 mã không phải trường hợp đặc biệt). In rõ danh
sách mã đã chọn, ghi ra `scripts/.spike_equity_10y_symbols.json`:
```json
{"hose": ["...", "...", "..."], "hnx": ["...", "...", "..."], "upcom": ["...", "...", "..."]}
```

**Lấy dữ liệu ngày 10 năm, có phân trang thủ công:**
```python
async def fetch_daily_10y(data, symbol: str) -> list:
    to_date = datetime.now(VN_TZ).date()
    from_date = to_date.replace(year=to_date.year - 10)
    from_str = f"{from_date:%Y/%m/%d}"
    to_str = f"{to_date:%Y/%m/%d}"
    all_rows = []
    page = 1
    while True:
        rows = await data.market_data.get_ohlc_1day_historical(
            symbol, from_str, to_str, page=page, size=1000
        )
        all_rows.extend(rows)
        print(f"  page {page}: {len(rows)} bar")
        if len(rows) < 1000:
            break
        page += 1
        if page > 20:  # guard chống loop vô hạn nếu API trả sai
            print(f"  !! dừng ở page {page} — vượt guard 20 trang, kiểm tra lại")
            break
    return all_rows
```
Với mỗi mã (9 mã: 3 board × 3 mã), gọi hàm trên, lưu riêng
`scripts/.spike_equity_10y_<symbol>.json`, in tổng số bar + bar đầu tiên +
bar cuối cùng (để thấy khoảng ngày thực tế nhận được, có thể ngắn hơn 10 năm
nếu mã mới niêm yết hoặc SSI giới hạn range).

## Task B — Phái sinh: dữ liệu 5 phút, 2 tháng gần nhất

Sửa `scripts/spike_ssi_sdk_derivative_ohlc_stream.py`: **thêm hàm mới**
`fetch_ohlc_5m_2months(symbol)` (không đổi các hàm đã có), đọc mã hợp đồng từ
`.spike_derivative_contract_symbol.json` (đã có, không đổi cách đọc):
```python
async def fetch_ohlc_5m_2months(symbol: str) -> None:
    from ssi_sdk import AsyncData

    async with await make_auth() as auth:
        data = AsyncData(auth)
        to_date = datetime.now(VN_TZ).date()  # cần import VN_TZ giống các spike khác
        from_date = to_date - timedelta(days=60)
        from_str = f"{from_date:%Y/%m/%d} 00:00:00"
        to_str = f"{to_date:%Y/%m/%d} 23:59:59"
        all_rows = []
        page = 1
        while True:
            rows = await data.market_data.get_ohlc_5minute_historical(
                symbol, from_str, to_str, page=page, size=1000
            )
            all_rows.extend(rows)
            print(f"  page {page}: {len(rows)} bar")
            if len(rows) < 1000:
                break
            page += 1
            if page > 20:
                print(f"  !! dừng ở page {page} — vượt guard 20 trang, kiểm tra lại")
                break
        payload = [dataclasses.asdict(r) for r in all_rows]
        OHLC_5M_2M_OUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"Tổng {len(all_rows)} bar 5 phút (2 tháng) → {OHLC_5M_2M_OUT}")
        if all_rows:
            print("Bar đầu:", payload[0])
            print("Bar cuối:", payload[-1])
```
Thêm hằng số `OHLC_5M_2M_OUT = Path(__file__).parent / ".spike_derivative_ohlc_5m_2m_sample.json"`
cạnh các hằng số output đã có. Gọi hàm này trong `if __name__ == "__main__":`
cùng điều kiện với `fetch_ohlc_sample()` hiện có (chạy khi không có
`--stream-only`) — thêm 1 dòng gọi, không đổi cấu trúc `if` đã có.

**Cập nhật `.gitignore`:** thêm `scripts/.spike_equity_10y_symbols.json`,
`scripts/.spike_equity_10y_*.json` (pattern chung cho 9 file mã), và
`scripts/.spike_derivative_ohlc_5m_2m_sample.json`.

---

## Kiểm chứng

```bash
uv run --with ssi-sdk python -c "
import ast
ast.parse(open('scripts/spike_ssi_sdk_equity_10y_history.py', encoding='utf-8').read())
ast.parse(open('scripts/spike_ssi_sdk_derivative_ohlc_stream.py', encoding='utf-8').read())
print('OK: syntax hop le')
from ssi_sdk import AsyncAuth, AsyncData, AsyncStream
from ssi_sdk.enums import Board, Timeframe
print('OK: import dung ton tai')
"
```

`grep -n "place_order\|place_limit_order\|place_market_order\|place_fco_\|cancel_order"
scripts/spike_ssi_sdk_equity_10y_history.py scripts/spike_ssi_sdk_derivative_ohlc_stream.py`
— phải rỗng.

---

## Báo cáo lại

1. Toàn bộ nội dung `scripts/spike_ssi_sdk_equity_10y_history.py` + diff
   `scripts/spike_ssi_sdk_derivative_ohlc_stream.py` + diff `.gitignore`.
2. Kết quả `ast.parse`/import check + grep.

**Sau khi báo cáo xong, KHÔNG dừng ở đây** — báo user cần **chạy thật cả 2
script trong giờ giao dịch phái sinh/cổ phiếu** (khoảng 8:45–11:30, 13:00–14:45,
giờ VN — user tự xác nhận lại giờ chính xác):
```bash
uv run --with ssi-sdk python scripts/spike_ssi_sdk_equity_10y_history.py
uv run --with ssi-sdk python scripts/spike_ssi_sdk_derivative_ohlc_stream.py --seconds 120
```
(Lưu ý: phần fetch dữ liệu lịch sử — ngày 10 năm, 5 phút 2 tháng — có thể chạy
**bất kỳ lúc nào**, không cần đợi giờ giao dịch. Chỉ phần **stream sống**
[`record_stream()` trong cả 2 script HNX/UPCOM và phái sinh] mới cần chạy đúng
giờ giao dịch để nhận được tick thật thay vì chỉ có ack rỗng.)

Báo lại: số mã mỗi sàn lấy được, tổng số bar ngày mỗi mã (đối chiếu xem có đủ
gần 10 năm không hay bị SSI giới hạn ngắn hơn), tổng số bar 5 phút 2 tháng của
hợp đồng phái sinh, và có cần lặp trang (page > 1) hay không ở bất kỳ mã nào.

Không tự commit — chờ Claude audit.
