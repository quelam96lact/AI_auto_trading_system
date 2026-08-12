# Prompt thực thi: Ghi dữ liệu spike thật (5 phút) vào DB, có kiểm tra trùng lặp

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `trading/storage/db.py`, `trading/models.py`,
`trading/collector/backfill.py` (đặc biệt `_parse_trading_date()`,
`_ohlc_rows_to_bars()` dòng 157-182 — pattern chuẩn để map OHLCData → `Bar`,
tái dùng cùng format string/TZ, không tự nghĩ ra cách parse khác).

---

## ⚠️ Bối cảnh

Các spike trước đã lấy được dữ liệu 5 phút **thật** và lưu ra file JSON local
(gitignored, không có trong git, chỉ nằm trên máy đang chạy):
- `scripts/.spike_derivative_ohlc_5m_2m_sample.json` — mã `41I1G8000`, 2028 bar,
  5 phút, ~5 tuần gần nhất.
- `scripts/.spike_ohlc_hnx_sample.json` — mã `PDB`, 78 bar 5 phút.
- `scripts/.spike_ohlc_upcom_sample.json` — mã `BCA`, 15 bar 5 phút.

User muốn ghi 3 file này vào DB thật (bảng `bars` — đây là dữ liệu **intraday
5 phút**, không phải `bars_daily`), và **kiểm tra trùng lặp** trước/sau khi ghi.

**Lưu ý quan trọng — KHÔNG có dữ liệu ngày (daily) 10 năm để ghi lúc này.**
`scripts/.spike_equity_10y_symbols.json` chỉ chứa danh sách mã đã khám phá
(`fetch_all()` của `spike_ssi_sdk_equity_10y_history.py` chưa chạy xong / chưa
tạo ra file `.spike_equity_10y_<symbol>.json` nào). **KHÔNG tự bịa/tạo dữ liệu
ngày giả để ghi vào `bars_daily`** — task này CHỈ ghi 3 file 5-phút đã có thật
ở trên. Phần cổ phiếu 10 năm sẽ là 1 prompt riêng sau khi user chạy lại spike
đó và có dữ liệu thật.

Bảng `bars` dùng upsert `ON CONFLICT (symbol, ts) DO UPDATE` (xem
`trading/storage/db.py::_UPSERT_BAR`) — nghĩa là trùng khóa `(symbol, ts)` tự
động được ghi đè, không tạo dòng trùng lặp ở tầng DB. Nhưng user muốn **thấy
rõ** có bao nhiêu dòng đã tồn tại sẵn (sẽ bị ghi đè) và bao nhiêu dòng thực sự
mới — script phải tự đếm và in ra, không chỉ dựa vào việc DB tự xử lý ngầm.

---

## ⚠️ Giới hạn phạm vi

**Chỉ tạo 1 file mới:** `scripts/backfill_spike_data_to_db.py`.

**KHÔNG sửa** `trading/storage/*`, `trading/collector/*`, `trading/models.py`,
hay bất kỳ file production nào khác — script này chỉ ĐỌC các module đó
(import `Storage`, `Bar`, `load_config`), không sửa chúng.

**KHÔNG gọi bất kỳ SSI API nào** (không cần `_ssi_spike_common.make_auth()`) —
task này chỉ đọc file JSON local đã có sẵn rồi ghi vào DB, hoàn toàn offline
với SSI.

**KHÔNG tự commit, không tự push.**

---

## Task — Đọc 3 file JSON, map sang `Bar`, ghi vào `bars`, báo cáo trùng lặp

```python
import json
import os
from datetime import datetime
from pathlib import Path

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.storage.db import Storage

SPIKE_FILES = [
    Path(__file__).parent / ".spike_derivative_ohlc_5m_2m_sample.json",
    Path(__file__).parent / ".spike_ohlc_hnx_sample.json",
    Path(__file__).parent / ".spike_ohlc_upcom_sample.json",
]


def _parse_trading_date(s: str) -> datetime:
    # Cùng format/TZ với trading/collector/backfill.py::_parse_trading_date
    return datetime.strptime(s, "%Y/%m/%d %H:%M:%S").replace(tzinfo=TZ)


def _rows_to_bars(rows: list[dict]) -> list[Bar]:
    return [
        Bar(
            r["symbol"],
            _parse_trading_date(r["trading_date"]),
            float(r["open_price"]),
            float(r["high_price"]),
            float(r["low_price"]),
            float(r["close_price"]),
            int(r["volume"]),
        )
        for r in rows
    ]
```

Với mỗi file trong `SPIKE_FILES`:
1. Nếu file không tồn tại → in rõ "bỏ qua, chưa có file X", không crash.
2. Đọc JSON, map sang `list[Bar]` bằng `_rows_to_bars()`.
3. Lấy symbol từ bar đầu tiên (tất cả bar trong 1 file cùng 1 symbol).
4. **Trước khi ghi**: đếm số dòng đã có sẵn trong DB khớp `(symbol, ts)` với
   dữ liệu sắp ghi:
   ```python
   with storage.conn() as c:
       existing_ts = {
           row[0] for row in c.execute(
               "SELECT ts FROM bars WHERE symbol = %s", (symbol,)
           ).fetchall()
       }
   incoming_ts = {b.ts for b in bars}
   n_duplicate = len(existing_ts & incoming_ts)
   n_new = len(incoming_ts - existing_ts)
   print(f"{symbol}: {len(bars)} bar sắp ghi — {n_duplicate} trùng (sẽ ghi đè), "
         f"{n_new} dòng mới.")
   ```
5. Gọi `storage.write_bars(bars)`.
6. **Sau khi ghi**: đếm lại tổng số dòng trong `bars` cho symbol đó
   (`SELECT count(*) FROM bars WHERE symbol = %s`), in ra để đối chiếu với
   dự đoán ở bước 4 (`count_after` phải bằng `len(existing_ts | incoming_ts)`).

Dùng `storage = Storage(os.environ["DB_DSN"])` — **KHÔNG dùng
`trading.config.load_config()`** (nó bắt buộc đủ các biến môi trường SSI
không liên quan gì tới script này, chỉ cần `DB_DSN`). **KHÔNG gọi
`storage.init_schema()`** trong script này (schema đã tồn tại sẵn trên DB
đang chạy, không phải việc của script này).

CLI: không cần argument, chạy thẳng `python scripts/backfill_spike_data_to_db.py`.

---

## Kiểm chứng

```bash
uv run python -c "
import ast
ast.parse(open('scripts/backfill_spike_data_to_db.py', encoding='utf-8').read())
print('OK: syntax hop le')
"
```

`grep -n "place_order\|place_limit_order\|place_market_order\|place_fco_\|cancel_order\|AsyncAuth\|AsyncData\|AsyncStream"
scripts/backfill_spike_data_to_db.py` — phải rỗng (script này không gọi SSI
API, chỉ đọc file JSON + ghi DB).

Sau đó chạy full test suite để đảm bảo không đụng gì tới code production:
```bash
uv run pytest -q -m "not integration"
```
Phải vẫn pass đúng số lượng như trước (không giảm/tăng test nào — script mới
không có test, không có production code nào bị sửa).

---

## Báo cáo lại

1. Toàn bộ nội dung `scripts/backfill_spike_data_to_db.py`.
2. Kết quả `ast.parse` + grep + `pytest` ở trên.
3. Chạy thật (docker compose có sẵn postgres đang healthy — dùng
   `DB_DSN=postgresql://trading:trading@localhost:5432/trading` nếu
   `config/config.yaml` không tự trỏ đúng localhost) và báo lại output đầy đủ
   (số bar mỗi symbol, số trùng/mới, số dòng sau khi ghi).

Không tự commit — chờ Claude audit (Claude sẽ tự query DB thật để xác nhận
độc lập, không chỉ tin vào output báo cáo).
