# Prompt thực thi: Spike xác nhận lấy được dữ liệu OHLC thật từ HNX + UPCOM (không chỉ HOSE)

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `scripts/spike_ssi_sdk_ohlc.py` (đã có, cùng pattern, chỉ dùng 1 mã
HOSE hardcode `VCB`), `scripts/_ssi_spike_common.py`.

---

## ⚠️ Bối cảnh

Audit xác nhận: `trading/collector/parser.py`/`feed.py`/`backfill.py` không có bất
kỳ ràng buộc board (HOSE/HNX/UPCOM) nào trong code — pipeline xử lý theo symbol
string chung. Nhưng **mọi dữ liệu thật từng dùng để test/config từ trước tới giờ
đều chỉ là mã HOSE** (`VCB, HPG, TCB`, `VNINDEX, VN30`) — chưa từng verify thật với
1 mã HNX hay UPCOM cụ thể nào. Đây là spike xác nhận giả định "kiến trúc symbol-
agnostic nên hoạt động được với mọi sàn" bằng dữ liệu thật, đúng nguyên tắc dự án
(không khẳng định khi chưa verify).

**Đây CHỈ là spike nghiên cứu — KHÔNG sửa `trading/collector/*`, KHÔNG đổi
`config/config.yaml`.** Nếu spike xác nhận hoạt động tốt, việc thêm mã HNX/UPCOM
vào config thật là quyết định RIÊNG của người dùng ở bước sau, không thuộc phạm vi
prompt này.

---

## ⚠️ Giới hạn phạm vi

**Chỉ tạo 1 file mới:** `scripts/spike_ssi_sdk_hnx_upcom_ohlc.py` (dùng lại
`make_auth()` từ `scripts/_ssi_spike_common.py`, không viết lại logic auth).

**KHÔNG sửa** `trading/collector/*`, `config/config.yaml`, hay bất kỳ file nào
khác.

**KHÔNG tự commit, không tự push.**

---

## Task A — Khám phá 1 mã HNX + 1 mã UPCOM thật (không hardcode đoán)

**KHÔNG tự chọn/đoán 1 mã cụ thể** (vd không tự viết "SHS" hay "BSR" vào code) —
dùng API thật để lấy danh sách mã theo board, rồi chọn mã đầu tiên trong danh sách
trả về (đơn giản, không cần logic chọn phức tạp):

```python
from ssi_sdk.enums import Board

async def discover_symbol(data, board: Board) -> str | None:
    securities = await data.market_data.get_securities_info_by_board(board)
    if not securities:
        return None
    return securities[0].symbol
```
(Lưu ý: `get_securities_info_by_board` với `Board.HNX`/`Board.UPCOM` KHÔNG gặp bug
"Board thiếu DERIVATIVES" đã fix ở spike phái sinh — bug đó chỉ xảy ra khi giá trị
board thật trả về là `"DERIVATIVES"`, còn cổ phiếu HNX/UPCOM trả về đúng
`"HNX"`/`"UPCOM"`, khớp enum sẵn có, không cần bypass.)

In ra rõ ràng danh sách vài mã đầu tiên nhận được cho mỗi board (không chỉ mã đã
chọn) để có thể đối chiếu, và ghi 2 mã đã chọn ra
`scripts/.spike_hnx_upcom_symbols.json`:
```json
{"hnx": "<mã HNX chọn>", "upcom": "<mã UPCOM chọn>", "timestamp": "..."}
```

Nếu 1 trong 2 board trả về danh sách rỗng — in rõ, không crash, dùng `None` cho
board đó ở Task B (bỏ qua, không phải lỗi).

## Task B — Lấy OHLC lịch sử thật cho 2 mã vừa khám phá

Với mỗi mã (HNX, UPCOM) tìm được ở Task A, làm giống hệt
`scripts/spike_ssi_sdk_ohlc.py::fetch_ohlc_sample()` (copy logic, đổi `SYMBOL`
thành biến, lặp qua 2 mã):
```python
to_date = datetime.now(VN_TZ).date()
from_date = to_date - timedelta(days=7)
from_str = f"{from_date:%Y/%m/%d} 00:00:00"
to_str = f"{to_date:%Y/%m/%d} 23:59:59"
rows = await data.market_data.get_ohlc_5minute_historical(symbol, from_str, to_str)
```
Lưu riêng từng mã: `scripts/.spike_ohlc_hnx_sample.json`,
`scripts/.spike_ohlc_upcom_sample.json`. In số lượng bar nhận được + 1 bar mẫu cho
mỗi mã (giống format `spike_ssi_sdk_ohlc.py` đã có).

## Task C — Subscribe live 2 mã (tuỳ chọn, giống pattern cũ)

Giống `record_stream()` trong `spike_ssi_sdk_ohlc.py`, nhưng subscribe **cả 2 mã
cùng lúc** trong 1 lần connect (`subscribe_symbol_ohlcv([hnx_symbol, upcom_symbol],
Timeframe.MINUTE_5)`), lắng nghe `--seconds` giây (mặc định 120), ghi mỗi message
ra `scripts/.spike_stream_hnx_upcom_sample.jsonl`. Rỗng ngoài giờ giao dịch là bình
thường, không phải lỗi — in rõ như các script khác đã làm.

**Cập nhật `.gitignore`:** thêm dòng cho 4 file mới:
`scripts/.spike_hnx_upcom_symbols.json`, `scripts/.spike_ohlc_hnx_sample.json`,
`scripts/.spike_ohlc_upcom_sample.json`, `scripts/.spike_stream_hnx_upcom_sample.jsonl`.

CLI giống `spike_ssi_sdk_ohlc.py`: `--seconds N`, `--stream-only`, `--ohlc-only`.

---

## Kiểm chứng

```bash
uv run --with ssi-sdk python -c "
import ast
ast.parse(open('scripts/spike_ssi_sdk_hnx_upcom_ohlc.py', encoding='utf-8').read())
print('OK: syntax hop le')
from ssi_sdk import AsyncAuth, AsyncData, AsyncStream
from ssi_sdk.enums import Board, Timeframe
print('OK: import cac symbol dung ton tai')
"
```

`grep -n "place_order\|place_limit_order\|place_market_order\|place_fco_\|cancel_order"
scripts/spike_ssi_sdk_hnx_upcom_ohlc.py` — phải rỗng (script này chỉ đọc dữ liệu
giá, không liên quan đặt lệnh, nhưng vẫn giữ đúng thói quen kiểm tra ranh giới an
toàn của dự án).

---

## Báo cáo lại

1. Toàn bộ nội dung `scripts/spike_ssi_sdk_hnx_upcom_ohlc.py` + diff `.gitignore`.
2. Kết quả `ast.parse`/import check + grep.

**Sau khi báo cáo xong, KHÔNG dừng ở đây** — báo cho user biết cần **chạy script
này thật** (`uv run --with ssi-sdk python scripts/spike_ssi_sdk_hnx_upcom_ohlc.py
--seconds 120`), rồi báo lại: 2 mã HNX/UPCOM tìm được là gì, có bao nhiêu bar OHLC
lịch sử nhận được cho mỗi mã, và có message stream nào không (hoặc "không nhận
được, ngoài giờ giao dịch" nếu chạy ngoài giờ — kết quả hợp lệ, không phải lỗi).

Không tự commit — chờ Claude audit.
