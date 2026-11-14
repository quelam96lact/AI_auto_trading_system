# Brief đợt 233: engine nến ngày, khung sổ paper (chưa chạy chiến lược nào)

- **Ngày:** 14/11/2026.
- **Nguồn quyết định:**
  - chủ dự án 13/11: nến ngày, khoảng 293 mã active, khớp paper ở open T+1 ghi vào tối T+1, sổ paper 100 triệu mới ở bảng riêng, sổ cũ giữ nguyên;
  - chủ dự án 14/11: (1) dựng **khung**, mặc định **không giao dịch** (chiến lược `null`), chỉ cắm chiến lược khi nó qua cổng; (2) engine là **một bước trong chuỗi 21:45 của scheduler**, không phải container mới.
  - Khảo sát nền: `docs/audit/2026-11-14-khao-sat-engine-truoc-khi-viet-lai.md` (đợt 228), đặc biệt B.3, D.1, D.3.
- **Vai trò:**
  - **Builder** viết code + test, tự kiểm chứng. KHÔNG commit, KHÔNG push.
  - **Researcher** (song song, không xem code của Builder trước khi xong phần mình) dựng kịch bản kiểm tra độc lập từ §3 của brief này.
  - **Lead** audit, chạy kịch bản của Researcher trên code của Builder, commit, push, deploy.

## 0. Không làm trong đợt này (thấy cần thì báo, không tự làm)

- Không sửa `trading/engine/*`, `trading/paper_broker.py`, `trading/risk.py`, `trading/strategies/*`, các mixin trong `trading/storage/` (`db.py`, `accounts.py`, `bars.py`, `orders.py`, `universe.py`), `docker-compose.yml`, `config/config.yaml`.
- Không dừng container `engine` cũ (vẫn chạy `NullStrategy`). Việc gỡ nó là đợt sau.
- Không đụng bảng sổ cũ `positions`, `orders`, `engine_state`, `pnl_daily`.
- Không thêm chiến lược thật, không dò tham số, không thêm nguồn giá mở cửa thời gian thực.
- Không chạy `scripts/sched.sh`, không restart/rebuild container, không `npx`, không `taskkill` theo tên, không gọi API SSI, không đọc `.env`/token.
- Test chạm DB chỉ dùng DB test (`trading_test`, theo `conftest.py` hiện có), đánh dấu `integration`. **Không ghi vào DB `trading` thật.**

## 1. Phạm vi file

**Tạo mới:**
- `trading/daily_engine/__init__.py`
- `trading/daily_engine/core.py`: logic thuần, không I/O (§3).
- `trading/daily_engine/strategy.py`: Protocol, `NullDailyStrategy`, bảng tên → lớp (§4).
- `trading/daily_engine/store.py`: đọc/ghi bảng sổ mới qua `Storage.conn()` (chỉ dùng `conn()`, `read_active_universe()`, `init_schema()` của `Storage` có sẵn).
- `trading/daily_engine/runner.py`: CLI `python -m trading.daily_engine.runner [--dry-run]` (§5).
- `tests/test_daily_engine_core.py` (unit), `tests/test_daily_engine_runner.py` (`integration`).

**Sửa (tối thiểu):**
- `trading/storage/schema.sql`: **chỉ thêm vào cuối** 4 bảng ở §2.
- `trading/scheduler/main.py`: thêm hằng `ADVISORY_LOCK_DAILY_ENGINE = 2026111401`, `TIMEOUT_DAILY_ENGINE_SECONDS = 15 * 60`, và **một bước** trong `run_event` ngay sau `daily-data-check`, trước `universe-refresh`, đúng khuôn bước `daily-data-check` (label `daily-engine`, log `daily-engine.log`, command `[python_exe, "-m", "trading.daily_engine.runner"]`, rc ≠ 0 → `notify_job_failure`).
- `scripts/heartbeat_check.py`: một mục `"daily-engine"` trong `SCHEDULE_EXIT_POLICIES`, khuôn y mục `"universe-refresh"`, `normal_exit_codes=frozenset({0})`, `reason` nêu mã 0/1/2/3 ở §5. Nếu có danh sách/test đồng bộ khác (ví dụ `KHONG_CANH`, test đếm số nhánh) thì làm theo đúng khuôn `universe-refresh` và **liệt kê trong báo cáo**.
- Test hiện có của scheduler và heartbeat: **chỉ thêm** test cho bước/mục mới.

Trước khi sửa `run_event` và `SCHEDULE_EXIT_POLICIES`: chạy impact (`node .gitnexus/run.cjs impact "<ten>" --direction upstream --repo .`, index có thể cũ: bổ sung bằng grep) và dán kết quả.

## 2. Bảng sổ mới (thêm cuối `schema.sql`, `CREATE TABLE IF NOT EXISTS`)

| Bảng | Cột |
|---|---|
| `paper_daily_state` | `id smallint PRIMARY KEY CHECK (id = 1)`, `strategy text NOT NULL`, `capital double precision NOT NULL`, `cash double precision NOT NULL`, `realized_pnl double precision NOT NULL DEFAULT 0`, `last_processed_date date NOT NULL`, `updated_at timestamptz NOT NULL DEFAULT now()` |
| `paper_daily_lots` | `id bigserial PRIMARY KEY`, `symbol text NOT NULL`, `qty integer NOT NULL CHECK (qty > 0)`, `cost_per_share double precision NOT NULL`, `buy_date date NOT NULL` |
| `paper_daily_orders` | `id bigserial PRIMARY KEY`, `strategy text NOT NULL`, `created_date date NOT NULL`, `exec_date date`, `symbol text NOT NULL`, `side text NOT NULL CHECK (side IN ('BUY','SELL'))`, `qty integer NOT NULL`, `filled_qty integer NOT NULL DEFAULT 0`, `status text NOT NULL CHECK (status IN ('pending','filled','expired','rejected'))`, `price double precision`, `fee double precision`, `tax double precision`, `reason text` |
| `paper_daily_nav` | `date date PRIMARY KEY`, `cash double precision NOT NULL`, `market_value double precision NOT NULL`, `nav double precision NOT NULL`, `n_positions integer NOT NULL` |

## 3. Luật thuần (`core.py`) — chốt, code đúng như dưới

Hằng số **import**, không gõ số: `FEE_RATE`, `SELL_TAX_RATE`, `SLIPPAGE_BPS`, `SETTLE_DAYS` từ `trading/paper_broker.py`. `LOT = 100`.

Kiểu dữ liệu (dataclass):
- `DailyBar(symbol, date, open, high, low, close, volume)`
- `Lot(symbol, qty: int, cost_per_share: float, buy_date: date)`
- `PendingOrder(id: int, created_date: date, symbol: str, side: "BUY"|"SELL", qty: int)`
- `OrderOutcome(order_id, status: "filled"|"expired"|"rejected", filled_qty, price, fee, tax, reason)`
- `DayResult(cash, realized_pnl, lots: list[Lot], outcomes: list[OrderOutcome], market_value, nav)`

Hàm chính:
```
process_day(cash, realized_pnl, lots, pending, bars_on_d: dict[str, DailyBar],
            last_close: dict[str, float], d: date, sessions: list[date]) -> DayResult
```
`sessions` là danh sách phiên giao dịch tăng dần, chứa `d` và mọi `buy_date` của lô.

Thứ tự trong `process_day`:
1. Mọi lệnh `pending` được xử lý trong ngày `d` (lệnh chỉ sống **một phiên**: khớp, hết hạn hoặc bị từ chối; không lệnh nào còn `pending` sau `process_day`).
2. **Bán trước, mua sau.** Trong mỗi nhóm theo `id` tăng dần.
3. Kiểm chung cho mọi lệnh: `qty <= 0` hoặc `qty % LOT != 0` → `rejected`, `reason="bad_qty"`. Mã không có trong `bars_on_d`, hoặc `open <= 0` → `expired`, `reason="no_bar"`.
4. **Bán:**
   - `settled` = tổng `qty` các lô của mã có `sessions.index(d) - sessions.index(buy_date) >= SETTLE_DAYS`.
   - Không giữ mã → `rejected`, `"not_held"`. `settled == 0` → `rejected`, `"unsettled"`.
   - `q = min(qty, settled)`; `px = open × (1 − SLIPPAGE_BPS/10_000)`; `val = q × px`; `fee = val × FEE_RATE`; `tax = val × SELL_TAX_RATE`; `cash += val − fee − tax`.
   - Trừ lô **FIFO** (lô `buy_date` cũ trước; cùng ngày thì theo thứ tự trong danh sách), chỉ trong các lô đã settle.
   - `realized_pnl += (val − fee − tax) − Σ(q_lô × cost_per_share)` của phần lô bị trừ.
   - `status="filled"`, `filled_qty=q` (bán một phần vẫn là `filled`, `reason="partial"` nếu `q < qty`).
5. **Mua:**
   - `px = open × (1 + SLIPPAGE_BPS/10_000)`; `afford = floor(cash / (px × (1 + FEE_RATE)) / LOT) × LOT`.
   - `q = min(qty, afford)`; `q == 0` → `rejected`, `"cash"`.
   - `val = q × px`; `fee = val × FEE_RATE`; `cash -= val + fee`; thêm `Lot(symbol, q, px × (1 + FEE_RATE), d)`.
   - `reason="partial"` nếu `q < qty`. `cash` không bao giờ âm.
6. **Định giá** ở close `d`: với mỗi mã đang giữ, giá = `bars_on_d[mã].close` nếu có và > 0, nếu không thì `last_close[mã]` (close > 0 gần nhất ≤ `d`). Không có giá nào → `ValueError` (không đoán). `market_value = Σ qty × giá`; `nav = cash + market_value`.

## 4. Chiến lược (`strategy.py`)

```
OrderIntent(symbol: str, side: "BUY"|"SELL", qty: int)
class DailyContext: d, universe: list[str], cash, nav, positions: dict[str, int],
                    bars(symbol, n) -> list[DailyBar]   # n nến gần nhất có date <= d
class DailyStrategy(Protocol):
    name: str
    def on_day(self, ctx: DailyContext) -> list[OrderIntent]: ...
NullDailyStrategy: name = "null", on_day trả []
STRATEGIES: dict[str, type] = {"null": NullDailyStrategy}
```
Chọn chiến lược bằng biến môi trường `DAILY_ENGINE_STRATEGY` (strip, lower), không đặt/rỗng → `"null"`. Tên không có trong `STRATEGIES` → mã thoát 2.

## 5. Runner (`runner.py`)

1. `Storage(dsn).init_schema()`. DSN lấy như các script scheduler đang lấy (xem `scripts/daily_data_check.py`); không đọc `.env` trực tiếp.
2. `sessions`: các ngày `is_trading_day(d, holidays)` (`trading/calendar_vn.py`, holidays từ `config/config.yaml` như scheduler `load_holidays`), từ 01/01/2026 tới hôm nay (giờ VN).
3. **Phiên `d` "đủ dữ liệu"** khi số mã active (`read_active_universe()`) có dòng `bars_daily` ngày `d` (giờ VN: `(ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`) ≥ 90% số mã active.
4. Chưa có `paper_daily_state`: tạo `strategy`=tên đang chọn, `capital`=`cash`=100_000_000, `last_processed_date` = phiên đủ dữ liệu gần nhất ≤ hôm nay. Không xử lý ngày nào. Thoát 0.
5. Có state nhưng `state.strategy` ≠ tên đang chọn → in `LỖI` ra stderr, không ghi gì, thoát 2.
6. Các phiên `d` sau `last_processed_date`, ≤ hôm nay, xử lý **theo thứ tự**, mỗi phiên **một transaction**:
   - chưa đủ dữ liệu → dừng tại đây (không bỏ qua sang phiên sau), in lý do, thoát 1;
   - đọc lệnh `pending`, lô, `bars_daily` ngày `d` của mã liên quan, `last_close`;
   - `process_day` → ghi kết quả lệnh (`exec_date=d`), thay lô, ghi `paper_daily_nav`, cập nhật `cash`, `realized_pnl`, `last_processed_date=d`;
   - gọi `strategy.on_day(ctx)` → ghi `OrderIntent` thành lệnh `pending`, `created_date=d`.
7. Không có phiên mới → thoát 0. Chạy lại cùng ngày không tạo thêm gì (idempotent).
8. `--dry-run`: chạy y hệt nhưng rollback mọi transaction, in tóm tắt (phiên xử lý, số lệnh, NAV).
9. Mã thoát: 0 ổn; 1 dữ liệu chưa đủ; 2 cấu hình/sổ không khớp; 3 ngoại lệ chưa bắt (bọc `main`, in traceback ra stderr, như đợt 217).

## 6. Test (TDD: viết test đỏ trước)

**Phép phá** — mỗi phép làm đỏ ít nhất một test **gọi đúng hàm sản phẩm**; sao lưu file ra ngoài repo rồi sửa, cấm `git checkout/restore/stash`, không có cờ phá thử trong code sản phẩm:

| # | Phép phá | Hàm |
|---|---|---|
| a | Bán được lô mới `SETTLE_DAYS − 1` phiên | `process_day` |
| b | Bỏ phí mua | `process_day` (so số **tính tay** ghi trong test) |
| c | Bỏ thuế bán | `process_day` (tính tay) |
| d | Trượt giá ngược chiều | `process_day` (tính tay) |
| e | Mua không làm tròn 100 hoặc để `cash` âm | `process_day` |
| f | Lệnh không có nến ngày `d` vẫn khớp | `process_day` |
| g | NAV định giá theo giá vốn thay vì close | `process_day` |
| h | Mua trước bán (tiền bán chưa dùng được cho lệnh mua cùng ngày) | `process_day` |
| i | FIFO sai (trừ lô mới trước) | `process_day` (so `realized_pnl` tính tay) |
| j | Lệnh `pending` sống sang phiên sau | `process_day` |
| k | Runner xử lý lại phiên đã xử lý (lệnh khớp hai lần) | runner, integration |
| l | Runner bỏ qua phiên thiếu dữ liệu để xử lý phiên sau | runner, integration |
| m | Runner không từ chối khi `state.strategy` khác | runner, integration |
| n | `--dry-run` để lại dòng trong DB | runner, integration |

Thêm: một test integration chạy runner với một chiến lược giả lập **chỉ định nghĩa trong file test** (mua 100 cp một mã ngày 1, bán ngày 1 + `SETTLE_DAYS`) qua 5 phiên dữ liệu tổng hợp, so `paper_daily_nav` từng ngày với số tính tay.

Test scheduler: bước `daily-engine` chạy sau `daily-data-check`, trước `universe-refresh`; rc ≠ 0 gọi `notify_job_failure` với label `daily-engine`. Test heartbeat: mục `daily-engine` có trong `SCHEDULE_EXIT_POLICIES` với `{0}`.

## 7. Tiêu chí hoàn thành (dán output thật)

1. Impact/grep trước khi sửa `run_event`, `SCHEDULE_EXIT_POLICIES`.
2. Test mới đỏ trước khi viết code (output), xanh sau.
3. Bảng phép phá a–n: tên test bị đỏ, chép nguyên văn dòng `FAILED`.
4. `uv run ruff check trading tests scripts`.
5. `uv run pytest -m "not integration" -q` và `uv run pytest -m integration -q tests/test_daily_engine_runner.py` (cần `docker compose --profile test up -d nats-test` theo `CLAUDE.md`; chỉ DB test).
6. `node .gitnexus/run.cjs detect-changes --scope all --repo .`, `git status --short`, `git diff --stat`.
7. Một câu: "Tôi không ghi vào DB `trading` thật, không restart container, không sửa file ngoài §1."
8. Mọi chỗ brief mơ hồ mà Builder phải tự diễn giải. Không im lặng chọn.
