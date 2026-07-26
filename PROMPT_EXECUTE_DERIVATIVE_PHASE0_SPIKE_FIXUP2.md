# Prompt thực thi: Fix Phase 0 spike phái sinh (lần 2) — `get_derivative_positions` không phải list + `get_securities_info` crash với board phái sinh

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `scripts/spike_ssi_sdk_derivative_account.py` (đã chạy thật, 2 lỗi
bên dưới), `scripts/_ssi_spike_common.py` (docstring `make_config()` đã ghi nhận
tiền lệ tương tự: SDK map field sai, phải bypass bằng cách đọc thẳng REST endpoint).

---

## ⚠️ Vẫn là spike — KHÔNG viết code production, KHÔNG đặt lệnh thật

---

## Kết quả chạy thật (2026-07-26, sau fix lần 1) — 2 lỗi mới cần fix

### Lỗi 1 — `get_derivative_positions()` không phải `list`, là 1 object
```
Gọi get_derivative_positions(0434228)...
200 {"equity":null,"derivative":{"accountNo":"0434228","derOpenPositions":[],"derClosePositions":[]}}
!! get_derivative_positions(0434228) lỗi: 'AllDerivativePosition' object is not iterable
```
Response HTTP đã đúng (200, dữ liệu thật). Đã tra `inspect`: type hint
`get_derivative_positions() -> list[AllDerivativePosition]` là **SAI** — thực tế
trả về **1 instance `AllDerivativePosition` duy nhất**, có field
`open_positions: list[DerivativePosition]` và `closed_positions:
list[DerivativePosition]` (khớp đúng raw JSON `derOpenPositions`/`derClosePositions`).
Code hiện tại (`for p in positions`) coi nó là list nên crash.

**Fix:** đổi trong `fetch_derivative_account()`:
```python
result = await trading.portfolio.get_derivative_positions(ACCOUNT_NO)
payload = {
    "open_positions": [dataclasses.asdict(p) for p in result.open_positions],
    "closed_positions": [dataclasses.asdict(p) for p in result.closed_positions],
} if result is not None else {"open_positions": [], "closed_positions": []}
_save_json(POSITIONS_OUT, payload)
print(f"OK — {len(payload['open_positions'])} mở, {len(payload['closed_positions'])} đã đóng → {POSITIONS_OUT}")
```
(Xoá dòng `[dataclasses.asdict(p) for p in positions] if positions else []` cũ —
sai bản chất, không phải chỉ sai cú pháp.)

### Lỗi 2 — `get_securities_info()` crash với mọi mã phái sinh (bug SDK thật)
```
200 [{"symbol":"41I1G8000",...,"board":"DERIVATIVES",...,"firstTradingDate":"2026/06/19","lastTradingDate":"2026/08/20",...}]
41I1G8000: lỗi khi gọi get_securities_info — 'DERIVATIVES' is not a valid Board
```
Đã tra nguồn SDK (`ssi_sdk.models.SecuritiesInfo.from_list()`):
```python
board=Board(item.get("board", "").upper()) if item.get("board") else None,
```
`Board` enum (`ssi_sdk.enums.Board`) chỉ có `HOSE, HNX, UPCOM` — **không có
`DERIVATIVES`** — bug SDK thật (enum thiếu giá trị), không phải lỗi cách gọi. HTTP
response đã về đúng 200 với đầy đủ dữ liệu thật (`firstTradingDate`,
`lastTradingDate`), nhưng bước parse response thành `SecuritiesInfo` dataclass bị
crash trước khi trả về được cho caller — **giống hệt tiền lệ bug
`EquityAccountBalance` đã gặp trước đây** (SDK bên thứ 3 lỗi field-mapping, không
sửa SDK, bypass bằng cách gọi REST endpoint thấp hơn và tự parse raw dict).

**Fix — bypass, đọc thẳng REST endpoint** (đã tra xác nhận qua `inspect`):
```python
async def _fetch_securities_info_raw(data, symbol: str) -> dict | None:
    """Bypass SecuritiesInfo.from_list() — SDK crash khi board='DERIVATIVES'
    (Board enum chỉ có HOSE/HNX/UPCOM, thiếu DERIVATIVES). Gọi thẳng REST endpoint
    thật (đã tra: /api/v3/data/securitiesByBoard, param symbol=<symbol>) và tự đọc
    field cần thiết từ dict thô, không qua Board(...) enum conversion bị lỗi."""
    raw = await data.market_data._rest.get(
        "/api/v3/data/securitiesByBoard", params={"symbol": symbol}
    )
    if not raw:
        return None
    return raw[0]
```
Thay lời gọi `data.market_data.get_securities_info(symbol)` trong
`find_front_month_contract()` bằng `await _fetch_securities_info_raw(data, symbol)`
— hàm mới trả về `dict` thô (hoặc `None`) thay vì `SecuritiesInfo`, nên các chỗ sau
đó dùng field phải đổi từ `record.get("maturity_date")`/`record.get("last_trading_date")`
(snake_case, kiểu `SecuritiesInfo`) sang `record.get("maturityDate")`/
`record.get("lastTradingDate")` (camelCase, kiểu raw JSON thật — xem log thật ở
trên: `"firstTradingDate":"2026/06/19","lastTradingDate":"2026/08/20"`). Cập nhật
`_parse_date()` nếu cần cho khớp field name mới (giữ nguyên logic parse
`YYYY/MM/DD`, chỉ đổi tên field truy cập).

`verified.append(record)` vẫn giữ nguyên (giờ `record` là raw dict thay vì
`dataclasses.asdict(SecuritiesInfo)` — không đổi cấu trúc lưu JSON output khác).

**Không cần sửa gì ở `_ssi_spike_common.py` hay bất kỳ file nào khác** — endpoint
này gọi qua `data.market_data._rest` (thuộc tính có sẵn trên
`AsyncMarketDataService`, không cần thêm import/dependency mới).

---

## ⚠️ Giới hạn phạm vi

**Chỉ sửa 1 file:** `scripts/spike_ssi_sdk_derivative_account.py`.
**KHÔNG sửa** file nào khác.
**KHÔNG tự commit, không tự push.**

---

## Kiểm chứng

```bash
uv run --with ssi-sdk python -c "
import ast
ast.parse(open('scripts/spike_ssi_sdk_derivative_account.py', encoding='utf-8').read())
print('OK: syntax hop le')
"
grep -n "place_order\|place_limit_order\|place_market_order\|place_fco_" scripts/spike_ssi_sdk_derivative_account.py
```
Grep phải rỗng.

`uv run pytest -v` — toàn bộ suite vẫn 118 passed (file này không có test, chỉ xác
nhận không phá vỡ gì khác).

---

## Báo cáo lại

1. Diff đầy đủ file.
2. Kết quả `ast.parse` + grep.

Không tự commit — chờ Claude audit. Sau khi audit xong, cần chạy lại thật cả 2
script theo đúng thứ tự (Task A trước Task B) như prompt gốc.
