# Prompt thực thi: Đặt lệnh thật — Phase 1 (Schema + Config + Storage CRUD)

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `PLAN_REAL_ORDER_PLACEMENT.md` (kế hoạch đầy đủ, đã audit, có kết quả Phase 0 thật) — prompt này chỉ giao đúng Phase 1. **KHÔNG làm Phase 2/3** (job sinh tín hiệu, script xác nhận đặt lệnh) — các phase đó có prompt riêng, sẽ giao sau khi Phase 1 được audit xong.

---

## ⚠️ Giới hạn phạm vi — đọc kỹ trước khi bắt đầu

**Đây là tính năng rủi ro cao nhất dự án (có thể liên quan tiền thật).** Phase 1 **KHÔNG gọi bất kỳ API đặt lệnh nào** — chỉ tạo nền tảng (bảng DB, config, hàm CRUD). Nếu bạn thấy code ở Phase 1 có vẻ "tiện thể" viết luôn phần sinh tín hiệu hoặc gọi `place_limit_order`/`cancel_order` — **đừng làm**, đó là phạm vi Phase 2/3, báo cáo lại thay vì tự mở rộng.

**Tuyệt đối KHÔNG import hoặc gọi** `AsyncTrading`, `AsyncTradingService`, `place_limit_order`, `cancel_order` ở bất kỳ đâu trong Phase 1 — đây chỉ là lớp lưu trữ/cấu hình.

**KHÔNG sửa** `trading/collector/account_sync.py`, `trading/collector/ssi_auth.py` (đặc biệt hàm `ensure_authenticated()` — đã audit kỹ, tuyệt đối không đụng), `trading/engine/main.py`, `trading/engine/logic.py` — các file này thuộc phạm vi Phase 2.

**Trước khi sửa `trading/config.py` hoặc `trading/storage/db.py`:** chạy `gitnexus_impact({target: "Config", direction: "upstream"})` và `gitnexus_impact({target: "Storage", direction: "upstream"})`, báo cáo blast radius trước khi sửa. Nếu risk HIGH/CRITICAL ở phần không liên quan tới thay đổi của bạn, dừng lại và hỏi thay vì tự quyết.

**Sau khi xong:** chạy `gitnexus_detect_changes()`, xác nhận thay đổi chỉ ảnh hưởng đúng các file liệt kê dưới đây.

**KHÔNG tự commit, không tự push.** Báo cáo lại (diff + test output) để Claude (planner) audit rồi mới commit.

---

## Bối cảnh

Dự án cần đặt lệnh LIMIT thật trên tài khoản Cash `0434221`, với cơ chế: tín hiệu tự động tính → `RiskManager.approve()` (đã có sẵn, không sửa) → ghi vào bảng chờ xác nhận → cảnh báo Telegram (1 chiều, đã có sẵn qua `trading.alerts.alert()`) → người dùng tự chạy script xác nhận thủ công (Phase 3) mới thực sự gửi lệnh lên SSI.

**Quyết định thiết kế quan trọng (đã chốt, áp dụng ở Phase 1 này):** Dữ liệu lệnh thật (`pending_real_orders`, `real_order_fills`) dùng **bảng DB hoàn toàn riêng**, không tái sử dụng `orders`/`positions`/`pnl_daily`/`engine_state` — các bảng đó thuộc về `PaperBroker` và được dashboard Grafana + engine loop paper-trading dùng. Trộn lẫn sẽ làm tăng rủi ro (bug ở lệnh thật ảnh hưởng số liệu paper, hoặc ngược lại).

---

## Task A — Thêm 2 bảng DB mới

**File sửa:** `trading/storage/schema.sql` — thêm 2 bảng mới ở cuối file (theo đúng style các bảng hiện có, dùng `CREATE TABLE IF NOT EXISTS`):

```sql
CREATE TABLE IF NOT EXISTS pending_real_orders (
  id bigserial PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  account_no text NOT NULL,
  symbol text NOT NULL,
  side text NOT NULL,
  quantity integer NOT NULL,
  price double precision NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  ssi_order_id text,
  confirmed_at timestamptz
);

CREATE TABLE IF NOT EXISTS real_order_fills (
  id bigserial PRIMARY KEY,
  ts timestamptz NOT NULL,
  account_no text NOT NULL,
  symbol text NOT NULL,
  side text NOT NULL,
  qty integer NOT NULL,
  price double precision NOT NULL,
  fee double precision NOT NULL DEFAULT 0,
  pnl double precision,
  ssi_order_id text,
  status text NOT NULL
);
```

`status` trong `pending_real_orders` là 1 trong: `pending`, `confirmed`, `expired`, `rejected`, `placed`, `failed`. `status` trong `real_order_fills` là 1 trong: `placed`, `cancelled`, `filled` (Phase 1 chỉ tạo bảng, không cần enforce bằng CHECK constraint — giữ đơn giản như các bảng khác trong file).

**Kiểm chứng:** không cần chạy DB thật ở bước này (integration test ở Task C sẽ verify). Chỉ cần `uv run python -c "import trading.storage.db"` không lỗi cú pháp SQL (file `.sql` không parse bằng Python nên chỉ cần đọc lại bằng mắt, khớp style file hiện có).

---

## Task B — Thêm field vào `Config`

**File sửa:** `trading/config.py`

1. Thêm 4 field vào `Config` dataclass (frozen):
   - `ssi_private_key: str`
   - `real_trading_enabled: bool`
   - `real_order_capital: float`
   - `real_order_account: str`
2. Trong `load_config()`:
   - `ssi_private_key=os.environ["SSI_PRIVATE_KEY"]`
   - `real_trading_enabled=bool(raw.get("real_trading_enabled", False))`
   - `real_order_capital=float(raw["real_order_capital"])` (bắt buộc có trong yaml, không mặc định — tránh trường hợp quên cấu hình mà lỡ dùng capital sai)
   - `real_order_account=str(raw["real_order_account"])`

**File sửa:** `config/config.yaml` — thêm 3 dòng:
```yaml
real_trading_enabled: false
real_order_capital: 21459
real_order_account: "0434221"
```
(Giá trị `21459` khớp số dư thật đo được ở Phase 0 — chỉ là giá trị khởi tạo, người dùng tự cập nhật thủ công khi nạp thêm tiền, theo đúng quyết định trong `PLAN_REAL_ORDER_PLACEMENT.md` mục Kiến trúc #1 — KHÔNG tự động đọc số dư sống.)

**File sửa:** `docker-compose.yml` — trong service `engine` (không phải `collector` — vì Phase 2 sẽ gắn logic đặt lệnh thật vào tiến trình engine), thêm vào `environment:`:
```yaml
SSI_PRIVATE_KEY: ${SSI_PRIVATE_KEY}
```

**Kiểm chứng:** Đọc `tests/test_config.py` trước để khớp style test hiện có (cách set env giả rồi gọi `load_config()`). Thêm test cho 4 field mới. Chạy `uv run pytest tests/test_config.py -v` — pass, không phá test cũ.

---

## Task C — Thêm CRUD methods vào `Storage`

**File sửa:** `trading/storage/db.py` — thêm các method sau (theo đúng style các method hiện có trong file — xem `save_account_balance`/`save_account_positions` làm mẫu):

```python
def create_pending_order(
    self, account_no: str, symbol: str, side: str, quantity: int,
    price: float, expires_at: datetime,
) -> int:
    """Insert 1 dòng pending, trả về id vừa tạo."""

def get_pending_order(self, order_id: int) -> dict | None:
    """Trả về dict các cột của 1 dòng pending_real_orders theo id, hoặc None nếu không có."""

def update_pending_order_status(
    self, order_id: int, status: str, ssi_order_id: str | None = None,
) -> None:
    """Cập nhật status (và ssi_order_id nếu có); set confirmed_at = now() khi status != 'pending'."""

def expire_stale_pending_orders(self) -> int:
    """UPDATE status='expired' WHERE status='pending' AND expires_at < now(). Trả về số dòng bị ảnh hưởng."""

def read_real_positions(self, account_no: str) -> dict[str, "Position"]:
    """Đọc account_position_snapshot, lấy ts mới nhất theo account_no (KHÔNG correlate thêm theo symbol —
    xem cách Grafana panel 'Real Positions' đã fix bug tương tự trước đó: nếu correlate cả symbol,
    mã đã bán hết sẽ không bao giờ bị ghi đè, hiện vĩnh viễn). Trả về dict[symbol, Position(symbol, qty=quantity, avg_price=cost_price)]
    chỉ gồm các symbol có quantity > 0."""

def read_real_daily_pnl(self, account_no: str, day: date) -> float:
    """SUM(pnl) từ real_order_fills WHERE account_no = ... AND ts::date = day. Trả về 0.0 nếu không có dòng nào."""

def write_real_order_fill(
    self, account_no: str, ts: datetime, symbol: str, side: str, qty: int,
    price: float, fee: float, pnl: float | None, ssi_order_id: str | None, status: str,
) -> None:
    """INSERT 1 dòng vào real_order_fills."""
```

Import `Position` từ `trading.broker` (đã có sẵn trong file, xem đầu `db.py`) và `date` từ `datetime` (đã import `datetime`, thêm `date` vào cùng dòng import).

**Kiểm chứng:** Thêm test vào `tests/test_storage.py` (file này đã có `pytestmark = pytest.mark.integration`, cần Postgres thật qua `docker compose up -d postgres` — xem fixture `storage` đầu file làm mẫu). Viết ít nhất:
- `test_create_and_get_pending_order` — tạo 1 dòng, đọc lại, so khớp field.
- `test_update_pending_order_status` — tạo, update status='confirmed', đọc lại xác nhận `confirmed_at` không còn None.
- `test_expire_stale_pending_orders` — tạo 1 dòng với `expires_at` trong quá khứ, gọi hàm, xác nhận status thành 'expired'.
- `test_read_real_positions_ignores_older_snapshot_for_sold_symbol` — seed 2 snapshot (cũ có symbol X qty>0, mới không còn X), xác nhận X không xuất hiện trong kết quả (regression test, cùng dạng bug đã fix ở Grafana panel).
- `test_read_real_daily_pnl_sums_same_day` — insert 2-3 dòng `real_order_fills` cùng ngày, khác ngày, xác nhận chỉ cộng đúng ngày cần.

Chạy: `docker compose up -d postgres` rồi `uv run pytest tests/test_storage.py -v` — toàn bộ pass (cũ + mới). Sau đó chạy **toàn bộ** test suite (`uv run pytest -v`, không chỉ file liên quan — bài học từ lần trước: giới hạn checklist vào vài file cụ thể đã bỏ sót 1 test hỏng) — phải pass hết, không phá bất kỳ test nào khác.

---

## Báo cáo lại

1. Diff đầy đủ của 3 file sửa (`trading/storage/schema.sql`, `trading/config.py`, `trading/storage/db.py`) + 2 file config (`config/config.yaml`, `docker-compose.yml`) + file test mới/sửa.
2. Output đầy đủ của `uv run pytest -v` (toàn bộ suite, cả `-m "not integration"` và integration với Postgres đã bật).
3. Kết quả `gitnexus_detect_changes()`.
4. Xác nhận bằng `grep` rằng KHÔNG có `AsyncTrading`/`AsyncTradingService`/`place_limit_order`/`cancel_order` ở bất kỳ file nào bạn tạo/sửa.

Không tự commit — chờ Claude audit.
