# Prompt thực thi: Đặt lệnh thật — Phase 2 (Sinh tín hiệu từ engine đang chạy)

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `PLAN_REAL_ORDER_PLACEMENT.md` + **Phase 1 phải đã merge xong** (`trading/storage/db.py` đã có `create_pending_order`/`read_real_positions`/`read_real_daily_pnl`, `Config` đã có `real_order_capital`/`real_order_account`/`real_trading_enabled`). Nếu Phase 1 chưa merge, DỪNG, báo lại.

**KHÔNG làm Phase 3** (`scripts/confirm_real_order.py`, lệnh `place_limit_order`/`cancel_order` thật) — phase đó có prompt riêng.

---

## ⚠️ Giới hạn phạm vi

**Phase 2 KHÔNG gọi bất kỳ API đặt lệnh nào** — chỉ tính tín hiệu, ghi vào `pending_real_orders` (đã có ở Phase 1), gửi Telegram. Việc thật sự gửi lệnh lên SSI là Phase 3, do người dùng tự xác nhận thủ công.

**Tuyệt đối KHÔNG import** `AsyncTrading`/`AsyncTradingService`/`place_limit_order`/`cancel_order` ở bất kỳ đâu trong Phase 2.

**Quyết định thiết kế đã chốt với user (không tự đổi):** gắn logic sinh tín hiệu lệnh thật **vào ngay tiến trình engine đang chạy** (`trading/engine/main.py`), KHÔNG viết job/script riêng đọc lại lịch sử bar — lý do: `SmaCrossStrategy` giữ trạng thái (moving average) trong bộ nhớ theo từng lần gọi `on_bar()`, chỉ tồn tại đúng bên trong tiến trình engine; một job riêng sẽ phải viết lại logic replay lịch sử bar (rủi ro bug mới), trong khi engine đã tính tín hiệu đúng, sẵn có, đã test kỹ.

**Trước khi sửa `process_bar()` hoặc `run()`:** chạy `gitnexus_impact({target: "process_bar", direction: "upstream"})` và tương tự cho `run` — báo cáo blast radius trước khi sửa.

**KHÔNG đổi hành vi hiện có của paper trading** (PaperBroker, RiskManager của paper, `broker.submit`, `persist_fills`) — thay đổi ở Phase 2 chỉ được PHỤ THÊM (additive), không sửa logic tính fills/PnL của paper trading. Tiêu chí kiểm chứng: `tests/test_engine_logic.py` (test cũ, không đổi assertion) vẫn pass nguyên vẹn sau khi thêm tham số mới (chỉ được thêm optional param có default, không đổi behaviour khi không truyền).

**KHÔNG tự commit, không tự push.**

---

## Task A — Thêm optional callback vào `process_bar()`

**File sửa:** `trading/engine/logic.py`

Thêm tham số optional `on_signal: Callable[[Signal, Bar], None] | None = None` vào `process_bar()`. Ngay sau dòng `signal = strategy.on_bar(bar, broker)`, nếu `signal is not None` và `on_signal is not None`, gọi `on_signal(signal, bar)` — gọi **TRƯỚC** logic `risk.approve()`/`broker.submit()` hiện có (để lệnh thật có gate `RiskManager` RIÊNG, độc lập với việc paper trading có duyệt tín hiệu này hay không — 2 luồng hoàn toàn tách biệt, dùng cùng 1 tín hiệu nhưng risk/capital khác nhau).

```python
from typing import Callable
# ...
def process_bar(
    bar: Bar,
    broker: PaperBroker,
    strategy: Strategy,
    risk: RiskManager,
    marks: dict[str, float],
    on_signal: Callable[[Signal, Bar], None] | None = None,
) -> list[Fill]:
    fills = broker.on_bar(bar)
    marks[bar.symbol] = bar.close

    signal = strategy.on_bar(bar, broker)
    if signal is not None:
        if on_signal is not None:
            on_signal(signal, bar)
        daily_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)
        if risk.approve(signal, bar.close, broker.positions, daily_pnl, bar.ts.date()):
            broker.submit(signal)

    return fills
```

Import `Signal` từ `trading.strategy` (thêm vào import nếu chưa có).

**Kiểm chứng:** `uv run pytest tests/test_engine_logic.py -v` — pass nguyên vẹn (test cũ không gọi `on_signal` nên hành vi giữ nguyên). Thêm 1 test mới `test_process_bar_calls_on_signal_when_signal_fires` — verify callback được gọi đúng 1 lần với đúng `Signal`/`Bar` khi có crossover, KHÔNG gọi khi không có signal.

---

## Task B — Module mới `trading/real_orders.py`

**File tạo mới:** `trading/real_orders.py`

```python
from datetime import datetime, timedelta

from trading.alerts import alert
from trading.config import Config
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.strategy import Signal
from trading.models import Bar

PENDING_ORDER_TTL_MINUTES = 15


def handle_signal(cfg: Config, storage: Storage, risk: RiskManager, signal: Signal, bar: Bar) -> None:
    """Gate 1 Signal qua RiskManager RIÊNG cho lệnh thật; nếu duyệt, ghi pending_real_orders + Telegram.

    KHÔNG gọi bất kỳ API đặt lệnh nào — chỉ ghi DB + cảnh báo. Việc đặt lệnh thật
    là scripts/confirm_real_order.py (Phase 3), chạy thủ công bởi người dùng.
    """
    positions = storage.read_real_positions(cfg.real_order_account)
    today = bar.ts.date()
    daily_pnl = storage.read_real_daily_pnl(cfg.real_order_account, today)

    if not risk.approve(signal, bar.close, positions, daily_pnl, today):
        return

    expires_at = datetime.now(bar.ts.tzinfo) + timedelta(minutes=PENDING_ORDER_TTL_MINUTES)
    order_id = storage.create_pending_order(
        account_no=cfg.real_order_account,
        symbol=signal.symbol,
        side=signal.side,
        quantity=signal.qty,
        price=bar.close,
        expires_at=expires_at,
    )
    alert(
        "WARN",
        "real order pending confirmation",
        id=order_id,
        symbol=signal.symbol,
        side=signal.side,
        qty=signal.qty,
        price=bar.close,
        expires_in_minutes=PENDING_ORDER_TTL_MINUTES,
        confirm_cmd=f"uv run python scripts/confirm_real_order.py {order_id}",
    )
```

(Điều chỉnh tên/kiểu tham số nếu khớp thực tế signature `Storage`/`RiskManager` sau khi đọc lại code thật — đoạn trên là khung tham khảo, không phải chép y nguyên nếu có sai lệch nhỏ về kiểu dữ liệu.)

**Kiểm chứng:** Thêm `tests/test_real_orders.py` theo style `tests/test_account_sync.py` (dùng fake/stub `Storage`, không cần Postgres thật cho unit test này):
- `test_handle_signal_writes_pending_order_when_approved` — risk cho phép → xác nhận gọi đúng `storage.create_pending_order` với args đúng, và `alert()` được gọi (có thể mock `trading.alerts.alert` hoặc kiểm tra qua caplog).
- `test_handle_signal_does_nothing_when_risk_rejects` — dùng `RiskManager(capital=1.0)` (capital cực nhỏ, chắc chắn reject vì order_value vượt max_order_value_pct) → xác nhận `create_pending_order` KHÔNG được gọi.

Chạy `uv run pytest tests/test_real_orders.py -v` — pass.

---

## Task C — Wire vào `trading/engine/main.py`

**File sửa:** `trading/engine/main.py`

Trong `run()`:
1. Sau dòng `risk = RiskManager(capital=CAPITAL)`, thêm 1 instance `RiskManager` riêng cho lệnh thật, tạo **1 lần duy nhất** ngoài vòng lặp (để giữ trạng thái `halted_date` xuyên suốt phiên, giống cách `risk` hiện có được dùng):
   ```python
   real_risk = RiskManager(capital=cfg.real_order_capital)
   ```
2. Định nghĩa closure (đặt gần `persist_fills`):
   ```python
   def on_real_signal(signal, bar) -> None:
       real_orders.handle_signal(cfg, storage, real_risk, signal, bar)
   ```
3. Sửa lời gọi `process_bar(bar, broker, strategy, risk, marks)` thành `process_bar(bar, broker, strategy, risk, marks, on_signal=on_real_signal)`.
4. Thêm import `from trading import real_orders` ở đầu file.

**KHÔNG sửa gì khác trong `run()`** — không đổi thứ tự khởi tạo hiện có, không đổi logic `persist_fills`/vòng lặp NATS.

**Kiểm chứng:** `tests/test_engine_main.py` (đọc file trước để khớp style — file này dùng `make_cfg()` construct `Config()` trực tiếp, **PHẢI** thêm đủ 4 field mới (`ssi_private_key`, `real_trading_enabled`, `real_order_capital`, `real_order_account`) vào `make_cfg()` nếu không sẽ lỗi `TypeError` giống lỗi đã gặp ở Phase account-sync trước đây). Thêm 1 test `test_engine_run_calls_real_orders_handle_signal_on_crossover` — mock/patch `trading.real_orders.handle_signal`, chạy `run()` với đủ bar để có crossover, xác nhận `handle_signal` được gọi với đúng `Signal`/`Bar`.

**Chạy toàn bộ suite** (không chỉ file liên quan): `docker compose up -d postgres nats` rồi `uv run pytest -v` — pass hết, không phá bất kỳ test nào khác trong dự án.

---

## Báo cáo lại

1. Diff đầy đủ 3 file (`trading/engine/logic.py`, `trading/real_orders.py` mới, `trading/engine/main.py`) + file test mới/sửa.
2. Output đầy đủ `uv run pytest -v` (toàn bộ suite).
3. Kết quả `gitnexus_detect_changes()`.
4. Xác nhận bằng `grep` KHÔNG có `AsyncTrading`/`place_limit_order`/`cancel_order` ở bất kỳ file bạn tạo/sửa.
5. Xác nhận `tests/test_engine_logic.py` cũ (trước khi bạn sửa) và sau khi sửa cho cùng kết quả pass — dán output trước/sau nếu có nghi ngờ.

Không tự commit — chờ Claude audit.
