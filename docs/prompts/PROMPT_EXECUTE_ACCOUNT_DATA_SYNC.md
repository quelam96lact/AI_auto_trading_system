# Prompt thực thi: Account Data Sync — Phase 1-3 (schema, sync job, Grafana)

**Dùng prompt này để giao việc cho 1 agent coding khác.**
**Đọc trước:** `PLAN_ACCOUNT_DATA_SYNC.md` (đặc biệt mục "Phase 0 — Kết quả thật") — prompt này giả định đã đọc, không lặp lại toàn bộ bối cảnh.

---

## ⚠️ Giới hạn phạm vi

**CHỈ đọc dữ liệu tài khoản (số dư, vị thế). TUYỆT ĐỐI KHÔNG import/dùng `AsyncTrading`, `TradingService`, hay bất kỳ API đặt/sửa/huỷ lệnh nào.** Đây không chỉ là quy ước — code KHÔNG được có khả năng đặt lệnh, dù vô tình: dùng thẳng `AsyncPortfolioService(auth.rest_client, auth.config)`, KHÔNG dùng `AsyncTrading(auth)` (class đó bundle cả `.trading` — order placement — không cần cho phạm vi này).

**File được sửa/tạo:** `config/config.yaml`, `trading/config.py`, `trading/storage/schema.sql`, `trading/storage/db.py`, `trading/collector/ssi_auth.py` (chỉ thêm 1 hàm mới, không sửa `ensure_authenticated()` đã có), `trading/collector/account_sync.py` (mới), `trading/collector/main.py` (1 đoạn nhỏ trong `housekeeping()`), `grafana/provisioning/dashboards/trading.json`, `tests/test_ssi_auth.py`, `tests/test_storage.py`, `tests/test_account_sync.py` (mới), `tests/test_dashboard_queries.py`.

**KHÔNG sửa** `ensure_authenticated()` hiện có trong `ssi_auth.py` (đã audit, đang chạy production cho backfill/feed) — chỉ thêm hàm mới bên cạnh.

**Trước khi sửa symbol nào:** `gitnexus_impact`. **Sau khi xong:** `gitnexus_detect_changes()`. **Không tự commit/push.**

---

## Bối cảnh đã xác nhận (Phase 0, không phải giả định)

- Account cần đồng bộ: `0434221` (Cash), `0434226` (Margin) — bỏ `0434228` (Derivative).
- `client_id` decode từ JWT `access_token` claim (`"client_id"`), không cần credential mới.
- **Bug SDK xác nhận:** `EquityAccountBalance.from_dict()` (trong `ssi-sdk` 3.1.0) đọc sai tên field cho 4 field (`availableCash`→thật là `accountBalance`; `withdrawal`→thật là `withdrawable`; `advanceCashT0/T1`→thật là `advancedCashT0/T1`, có thêm chữ "d"). **KHÔNG dùng `AsyncPortfolioService.get_equity_balance()`** — bypass bằng cách gọi thẳng `auth.rest_client.get(EP_ACCOUNT_BALANCE, params=...)` và tự map field đúng (xem Task 3).
- `get_equity_positions()` **không có bug**, dùng thẳng được.
- Không cần OTP cho Portfolio API.
- `AsyncAuth.rest_client` là property public, dùng để bypass bug ở trên.

---

## Task 1 — Config

### `config/config.yaml` — thêm
```yaml
ssi_equity_accounts: ["0434221", "0434226"]
```

### `trading/config.py::Config` — thêm field + đọc trong `load_config()`
```python
ssi_equity_accounts: list[str]
```
```python
ssi_equity_accounts=raw["ssi_equity_accounts"],
```

**Kiểm chứng:** đọc file test hiện có (`tests/test_config.py`) để khớp style, thêm assertion cho field mới, `uv run pytest tests/test_config.py -v` pass.

---

## Task 2 — `decode_client_id()` trong `ssi_auth.py`

Thêm hàm mới (KHÔNG sửa `ensure_authenticated()` đã có):
```python
def decode_client_id(access_token: str) -> str:
    """Giải mã claim 'client_id' từ payload JWT access_token — không verify
    signature (chỉ đọc claim). SSI tự cấp JWT này nên không cần verify thêm."""
    import base64
    import json

    payload_b64 = access_token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload_b64))
    return claims.get("client_id", "")
```

**Kiểm chứng:** test mới trong `tests/test_ssi_auth.py` — dựng 1 JWT giả (tự encode base64 1 payload dict có `client_id`), assert decode đúng. Không cần token thật.

---

## Task 3 — Schema + `Storage` methods

### `trading/storage/schema.sql` — thêm (đọc file trước để khớp style/convention hiện có)
```sql
CREATE TABLE IF NOT EXISTS account_balance_snapshot (
  account_no text NOT NULL,
  ts timestamptz NOT NULL,
  account_balance double precision NOT NULL,
  total_debt double precision NOT NULL,
  withdrawable double precision NOT NULL,
  buy_unmatched double precision NOT NULL,
  sell_unmatched double precision NOT NULL,
  PRIMARY KEY (account_no, ts)
);

CREATE TABLE IF NOT EXISTS account_position_snapshot (
  account_no text NOT NULL,
  ts timestamptz NOT NULL,
  symbol text NOT NULL,
  quantity integer NOT NULL,
  cost_price double precision NOT NULL,
  sellable_quantity integer NOT NULL,
  PRIMARY KEY (account_no, ts, symbol)
);
```

### `trading/storage/db.py::Storage` — thêm 2 method (đọc file trước, khớp pattern `save_ssi_token`/`write_bars` đã có)
```python
def save_account_balance(
    self, account_no: str, ts: datetime,
    account_balance: float, total_debt: float, withdrawable: float,
    buy_unmatched: float, sell_unmatched: float,
) -> None: ...

def save_account_positions(self, account_no: str, ts: datetime, positions: list[dict]) -> None:
    """positions: list of {"symbol": str, "quantity": int, "cost_price": float, "sellable_quantity": int}."""
    ...
```

**Kiểm chứng:** test mới trong `tests/test_storage.py` (đọc file trước để khớp style — dùng fixture `storage`/`DSN` đã có, `pytestmark = pytest.mark.integration` nếu file đó cần Postgres thật). `uv run pytest tests/test_storage.py -v` (cần Postgres chạy — `docker compose up -d postgres` trước).

---

## Task 4 — `trading/collector/account_sync.py` (module mới)

```python
from datetime import datetime

from trading.calendar_vn import TZ
from trading.collector.ssi_auth import decode_client_id, ensure_authenticated
from trading.config import Config
from trading.storage.db import Storage

EP_ACCOUNT_BALANCE = "/api/v3/trading/accountBalance"  # xác nhận từ ssi_sdk.constant


async def sync_account_data(cfg: Config, storage: Storage) -> None:
    from ssi_sdk.services.portfolio import AsyncPortfolioService
    # KHÔNG import AsyncTrading/TradingService — xem "Giới hạn phạm vi" đầu prompt.

    auth = await ensure_authenticated(cfg, storage)
    try:
        client_id = decode_client_id(auth.token_manager.access_token)
        auth.config.client_id = client_id
        portfolio = AsyncPortfolioService(auth.rest_client, auth.config)
        now = datetime.now(TZ)

        for account_no in cfg.ssi_equity_accounts:
            await _sync_balance(auth, client_id, account_no, now, storage)
            await _sync_positions(portfolio, account_no, now, storage)
    finally:
        await auth.close()


async def _sync_balance(auth, client_id: str, account_no: str, ts: datetime, storage: Storage) -> None:
    # Bypass AsyncPortfolioService.get_equity_balance() — bug SDK xác nhận
    # (xem PLAN_ACCOUNT_DATA_SYNC.md mục "Phase 0 — Kết quả thật" #3): map
    # sai field name, luôn trả 0.0 cho availableCash/withdrawal/advanceCashT0/1.
    # Gọi thẳng REST + tự map tên field ĐÚNG đã xác nhận bằng dữ liệu thật.
    raw = await auth.rest_client.get(
        EP_ACCOUNT_BALANCE, params={"clientId": client_id, "accountNo": account_no}
    )
    equity = raw.get("equity")
    if not equity:
        return  # account này không có phần equity (vd derivative), bỏ qua
    storage.save_account_balance(
        account_no=account_no,
        ts=ts,
        account_balance=float(equity.get("accountBalance") or 0),
        total_debt=float(equity.get("totalDebt") or 0),
        withdrawable=float(equity.get("withdrawable") or 0),
        buy_unmatched=float(equity.get("buyUnmatched") or 0),
        sell_unmatched=float(equity.get("sellUnmatched") or 0),
    )


async def _sync_positions(portfolio, account_no: str, ts: datetime, storage: Storage) -> None:
    positions = await portfolio.get_equity_positions(account_no)  # không có bug, dùng thẳng
    rows = [
        {
            "symbol": p.symbol,
            "quantity": p.quantity,
            "cost_price": p.cost_price,
            "sellable_quantity": p.sellable_quantity,
        }
        for p in positions
    ]
    storage.save_account_positions(account_no, ts, rows)
```

**Lưu ý khi code thật:** `EP_ACCOUNT_BALANCE = "/api/v3/trading/accountBalance"` và format params `{"clientId": ..., "accountNo": ...}` **đã verify thật** (chạy `AccountBalanceRequest(...).to_dict()` trên package cài thật trước khi viết prompt này — không phải suy đoán). Viết code thật dùng `from ssi_sdk.constant import EP_ACCOUNT_BALANCE` (import từ package, không hardcode string trùng lặp) thay vì chép lại hằng số như bản blueprint ở trên (chỉ để dễ đọc).

**Kiểm chứng:** test mới `tests/test_account_sync.py` — mock `ensure_authenticated`/`auth.rest_client.get`/`AsyncPortfolioService.get_equity_positions` (theo pattern `tests/test_ssi_auth.py` đã dùng — fake class, monkeypatch). Test case bắt buộc:
1. `_sync_balance` map đúng `accountBalance`/`withdrawable`/`advancedCashT0/1` (raw dict giả lập ĐÚNG format thật đã xác nhận: `{"equity": {"accountBalance": "21459", "withdrawable": "21459", ...}}`) → `storage.save_account_balance` được gọi với `account_balance=21459.0` (KHÔNG phải 0.0 — test này chính là bảo vệ chống regression nếu ai đó lỡ quay lại dùng `get_equity_balance()` bị bug).
2. `equity=None`/thiếu key → không crash, không gọi `save_account_balance`.
3. `_sync_positions` map đúng field, gọi `save_account_positions` đúng tham số.

---

## Task 5 — Wire vào `main.py::housekeeping()`

Thêm biến đếm/thời điểm đồng bộ gần nhất (giống pattern `eod_done_for` đã có), chạy mỗi 5 phút:
```python
from trading.collector.account_sync import sync_account_data
from datetime import timedelta

# trong housekeeping(), trước vòng while:
last_account_sync: datetime | None = None

# trong vòng while, sau wd.check()/storage.beat():
if last_account_sync is None or now - last_account_sync >= timedelta(minutes=5):
    last_account_sync = now
    try:
        await sync_account_data(cfg, storage)
    except Exception as e:
        alert("WARN", "account sync failed, skipping", error=str(e)[:100])
```
**Không sửa gì khác trong `main.py`** (phần feed/consume/backfill giữ nguyên).

**Kiểm chứng:** `uv run --with ssi-sdk python -c "import ast; ast.parse(open('trading/collector/main.py', encoding='utf-8').read()); print('OK')"`.

---

## Task 6 — Grafana panel

Đọc `grafana/provisioning/dashboards/trading.json` trước để khớp style (mỗi panel có `targets[0].rawSql`). Thêm 2 panel mới:
1. **"Real Account Balance"** (time series) — query `account_balance_snapshot`, group theo `account_no`.
2. **"Real Positions"** (table) — query `account_position_snapshot`, lấy snapshot mới nhất mỗi `(account_no, symbol)`.

Thêm test tương ứng vào `tests/test_dashboard_queries.py` (theo đúng pattern các test panel khác đã có — dùng `storage` fixture, insert data giả, chạy raw SQL y hệt panel, assert kết quả).

---

## Sau khi hoàn thành

1. `uv run pytest -m "not integration" -v` — tất cả pass.
2. `uv run pytest tests/test_storage.py tests/test_dashboard_queries.py -v` (cần `docker compose up -d postgres`) — tất cả pass.
3. `gitnexus_detect_changes()` — dán kết quả.
4. Báo cáo: file sửa/tạo, xác nhận **không có import `AsyncTrading`/`TradingService` ở đâu trong diff** (tự kiểm bằng `grep -rn "AsyncTrading\|TradingService" trading/` trước khi báo cáo — phải rỗng). **Không commit, không push.**
