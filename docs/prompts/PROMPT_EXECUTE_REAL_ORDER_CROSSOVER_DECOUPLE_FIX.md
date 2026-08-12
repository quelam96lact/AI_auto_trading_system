# Prompt thực thi: Fix #3 — tách crossover khỏi position-gating (tín hiệu lệnh thật không còn phụ thuộc PaperBroker)

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `PLAN_REAL_ORDER_PLACEMENT.md`. **Đây là fix rủi ro/phạm vi lớn nhất trong số 5 fix đang giao** — đụng vào `SmaCrossStrategy`/`process_bar()` đã ổn định, dùng chung cho paper trading. Đọc kỹ toàn bộ prompt trước khi bắt đầu, đặc biệt phần "Điều kiện bắt buộc" ở cuối.

---

## ⚠️ Bối cảnh — vì sao cần fix này

`trading/engine/logic.py::process_bar()` gọi `strategy.on_bar(bar, broker)` với `broker` là **PaperBroker mô phỏng**. Trong `SmaCrossStrategy.on_bar()`:
```python
held = context.position_qty(bar.symbol)   # context = broker (PaperBroker!)
if cur_above and not prev_above and held == 0:
    return Signal(bar.symbol, "BUY", self.qty)
if not cur_above and prev_above and held > 0:
    return Signal(bar.symbol, "SELL", held)
```
Hậu quả thật: nếu PaperBroker không nắm giữ 1 mã (mô phỏng), nhưng tài khoản Cash thật đang nắm giữ mã đó (mua qua pipeline lệnh thật rồi user chấp nhận, trong khi paper trading tự động lại lỡ bán trước đó, hoặc bất kỳ lý do khiến 2 bên lệch nhau) — khi có bearish crossover, `held` (của paper) bằng 0 → **không có `Signal` SELL nào được sinh ra cả** → vị thế thật đó không bao giờ được hệ thống tự động đề xuất bán, dù tín hiệu kỹ thuật đã bảo phải bán. Đây là lỗ hổng nghiêm trọng hơn vấn đề "SELL sai số lượng" đã fix trước đó (fix trước chỉ chặn số lượng SAI khi CÓ signal, không giải quyết việc signal có thể KHÔNG BAO GIỜ được sinh ra).

**Quyết định (đã hỏi user, chọn sửa tận gốc):** tách việc "phát hiện crossover" (chỉ dựa vào MA, không quan tâm ai đang giữ gì) khỏi việc "quyết định dựa trên vị thế" (paper dùng PaperBroker, lệnh thật dùng tài khoản Cash thật — độc lập nhau).

---

## ⚠️ Giới hạn phạm vi

**Sửa đúng 4 file production:** `trading/strategies/sma_cross.py`, `trading/engine/logic.py`, `trading/engine/main.py`, `trading/real_orders.py`.

**KHÔNG sửa:** `trading/paper_broker.py`, `trading/broker.py`, `trading/risk.py`, `scripts/confirm_real_order.py`, `trading/backtest.py` (dùng `SmaCrossStrategy` trực tiếp qua `on_bar()`, không qua `process_bar()` — xác nhận bằng `grep -n "process_bar" trading/backtest.py` phải rỗng trước khi bắt đầu, nếu không rỗng thì DỪNG và báo cáo lại vì giả định trong prompt này sai).

**Trước khi sửa:** chạy `gitnexus_impact({target: "SmaCrossStrategy", direction: "downstream"})` và `gitnexus_impact({target: "process_bar", direction: "downstream"})` — báo cáo blast radius. Nếu phát hiện caller nào khác ngoài `trading/engine/main.py` + các file test đã biết, DỪNG và báo cáo.

**KHÔNG tự commit, không tự push.**

---

## Task A — `trading/strategies/sma_cross.py`: tách `compute_crossover()` khỏi `on_bar()`

Refactor thành:

```python
from collections import deque
from typing import Literal

from trading.models import Bar
from trading.strategy import Context, Signal

Crossover = Literal["bull", "bear"]


class SmaCrossStrategy:
    def __init__(self, fast: int = 10, slow: int = 20, qty: int = 100):
        self.fast = fast
        self.slow = slow
        self.qty = qty
        self._closes: dict[str, deque] = {}
        self._prev_above: dict[str, bool | None] = {}
        self._last_crossover: dict[str, Crossover | None] = {}

    def compute_crossover(self, bar: Bar) -> Crossover | None:
        """Cập nhật state MA (CHỈ được gọi đúng 1 lần/bar/symbol — có side-effect
        mutate state nội bộ), trả về loại crossover vừa xảy ra (nếu có).

        KHÔNG áp bất kỳ logic vị thế nào ở đây — tách biệt "phát hiện crossover"
        (thuần kỹ thuật, dựa vào MA) khỏi "quyết định dựa trên vị thế" (paper hay
        thật), để real_orders.handle_crossover() có thể tự quyết định độc lập với
        PaperBroker.
        """
        closes = self._closes.setdefault(bar.symbol, deque(maxlen=self.slow))
        closes.append(bar.close)
        if len(closes) < self.slow:
            self._last_crossover[bar.symbol] = None
            return None

        values = list(closes)
        fast_ma = sum(values[-self.fast:]) / self.fast
        slow_ma = sum(values) / self.slow
        cur_above = fast_ma > slow_ma
        prev_above = self._prev_above.get(bar.symbol)
        self._prev_above[bar.symbol] = cur_above
        if prev_above is None:
            self._last_crossover[bar.symbol] = None
            return None

        crossover: Crossover | None = None
        if cur_above and not prev_above:
            crossover = "bull"
        elif not cur_above and prev_above:
            crossover = "bear"
        self._last_crossover[bar.symbol] = crossover
        return crossover

    def last_crossover(self, symbol: str) -> Crossover | None:
        """Crossover vừa tính ở lần compute_crossover() gần nhất cho symbol này."""
        return self._last_crossover.get(symbol)

    def on_bar(self, bar: Bar, context: Context) -> Signal | None:
        crossover = self.compute_crossover(bar)
        held = context.position_qty(bar.symbol)
        if crossover == "bull" and held == 0:
            return Signal(bar.symbol, "BUY", self.qty)
        if crossover == "bear" and held > 0:
            return Signal(bar.symbol, "SELL", held)
        return None
```

**QUAN TRỌNG:** `on_bar()` phải giữ nguyên hành vi quan sát được (observable behavior) — cùng input phải cho cùng output như code cũ, không sai khác dù chỉ 1 trường hợp.

**Kiểm chứng:** `uv run pytest tests/test_sma_cross.py -v` — toàn bộ test CŨ phải pass NGUYÊN VẸN, không sửa file test này ở bước này (nếu cần sửa, đó là dấu hiệu `on_bar()` đã đổi hành vi — DỪNG, xem lại). Sau đó thêm 2 test MỚI vào `tests/test_sma_cross.py`:
- `test_compute_crossover_reports_bear_even_when_never_bought` — dựng price series đi lên đủ để có lịch sử MA rồi đảo chiều xuống tạo bearish crossover, gọi trực tiếp `strategy.compute_crossover(bar)` qua từng bar (KHÔNG qua `on_bar`/context) → assert `strategy.last_crossover(symbol) == "bear"` ở đúng bar xảy ra crossover.
- `test_last_crossover_returns_none_before_enough_history` — gọi `compute_crossover` với chưa đủ `slow` bars → `last_crossover(symbol)` trả `None`.

---

## Task B — `trading/engine/logic.py`: đổi `process_bar()` từ `on_signal` sang `on_crossover`

```python
from typing import Callable

from trading.broker import Fill
from trading.calendar_vn import TZ
from trading.models import Bar
from trading.paper_broker import PaperBroker
from trading.risk import RiskManager
from trading.strategies.sma_cross import Crossover, SmaCrossStrategy


def process_bar(
    bar: Bar,
    broker: PaperBroker,
    strategy: SmaCrossStrategy,
    risk: RiskManager,
    marks: dict[str, float],
    on_crossover: Callable[[Crossover, Bar], None] | None = None,
) -> list[Fill]:
    fills = broker.on_bar(bar)
    marks[bar.symbol] = bar.close

    signal = strategy.on_bar(bar, broker)
    crossover = strategy.last_crossover(bar.symbol)
    if on_crossover is not None and crossover is not None:
        on_crossover(crossover, bar)

    if signal is not None:
        daily_pnl = broker.realized_pnl + broker.unrealized_pnl(marks)
        if risk.approve(signal, bar.close, broker.positions, daily_pnl, bar.ts.date()):
            broker.submit(signal)

    return fills
```

Lưu ý: import `Strategy` từ `trading.strategy` bị thay bằng import `SmaCrossStrategy` cụ thể — chấp nhận được vì `process_bar()` giờ cần gọi `strategy.last_crossover()` (không có trong `Strategy` Protocol, và toàn bộ codebase chỉ có duy nhất 1 strategy cụ thể — xem xác nhận `grep` ở đầu prompt).

**Kiểm chứng:** Trong `tests/test_engine_logic.py`:
- **Xoá/thay** `test_process_bar_calls_on_signal_when_signal_fires` và `test_process_bar_does_not_call_on_signal_when_no_signal` (tham số `on_signal` không còn tồn tại) bằng:
  - `test_process_bar_calls_on_crossover_when_crossover_fires` — tương tự test cũ nhưng dùng `on_crossover=...`, assert callback nhận đúng `("bull"` hoặc `"bear", bar)`.
  - `test_process_bar_does_not_call_on_crossover_when_no_crossover` — tương tự.
  - **Test quan trọng nhất — chứng minh giá trị của fix này:** `test_process_bar_calls_on_crossover_even_when_paper_signal_suppressed` — dựng price series khiến bearish crossover xảy ra NGAY LẦN ĐẦU (PaperBroker chưa từng mua, `held=0` xuyên suốt) → `strategy.on_bar()` trả về `None` (paper không có gì để bán) nhưng `on_crossover` **VẪN phải được gọi** với `"bear"`. Đây là bằng chứng trực tiếp lỗ hổng cũ đã được giải quyết.
- Giữ nguyên `test_process_bar_submits_and_next_bar_fills` (không gọi `on_crossover`, không cần sửa) — xác nhận vẫn pass, chứng minh hành vi paper trading không đổi.

---

## Task C — `trading/real_orders.py`: `handle_signal()` → `handle_crossover()`

**Xoá hoàn toàn `handle_signal()`**, thay bằng:

```python
from datetime import datetime, timedelta

from trading.alerts import alert
from trading.config import Config
from trading.models import Bar
from trading.risk import RiskManager
from trading.storage.db import Storage
from trading.strategies.sma_cross import Crossover
from trading.strategy import Signal

PENDING_ORDER_TTL_MINUTES = 15
BUY_QTY = 100  # lô tối thiểu HOSE/HNX — KHÔNG lấy theo SmaCrossStrategy.qty (đó là
               # tham số mô phỏng cho paper trading, không nên quyết định khối lượng
               # lệnh thật; xem PLAN_REAL_ORDER_PLACEMENT.md).


def handle_crossover(
    cfg: Config, storage: Storage, risk: RiskManager, crossover: Crossover, bar: Bar
) -> None:
    """Gate 1 sự kiện crossover (từ SmaCrossStrategy.last_crossover() — thuần kỹ
    thuật, KHÔNG liên quan PaperBroker) qua RiskManager riêng cho lệnh thật, dựa
    HOÀN TOÀN trên vị thế THẬT của tài khoản Cash.

    KHÔNG gọi bất kỳ API đặt lệnh nào — chỉ ghi DB + cảnh báo. Việc đặt lệnh thật
    là scripts/confirm_real_order.py, chạy thủ công bởi người dùng.
    """
    positions = storage.read_real_positions(cfg.real_order_account)
    real_pos = positions.get(bar.symbol)

    if crossover == "bull":
        if real_pos is not None and real_pos.qty > 0:
            return  # tài khoản thật đã nắm giữ mã này rồi, không mua thêm
        signal = Signal(symbol=bar.symbol, side="BUY", qty=BUY_QTY)
    elif crossover == "bear":
        sellable = real_pos.sellable_qty if real_pos is not None else 0
        if sellable <= 0:
            return  # không nắm giữ, hoặc chưa settle T+2.5 — không có gì để bán
        signal = Signal(symbol=bar.symbol, side="SELL", qty=sellable)
    else:
        return

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

**Kiểm chứng:** Trong `tests/test_real_orders.py` — **xoá các test dùng `handle_signal`** (hàm không còn tồn tại), thay bằng (dùng `RealPosition` từ `trading.storage.db`, đã có sẵn từ fix SELL/T+2.5 trước đó):
- `test_handle_crossover_buy_when_not_held` — `crossover="bull"`, `positions={}` → `create_pending_order` gọi với `side="BUY", quantity=100`.
- `test_handle_crossover_skips_buy_when_already_held` — `crossover="bull"`, `positions={"VCB": RealPosition("VCB", 100, 50_000.0, 100)}` → `create_pending_order` KHÔNG được gọi.
- `test_handle_crossover_sell_caps_to_sellable_qty` — `crossover="bear"`, `positions={"VCB": RealPosition("VCB", 100, 50_000.0, 30)}` → `create_pending_order` gọi với `quantity=30`.
- `test_handle_crossover_skips_sell_when_nothing_sellable` — `crossover="bear"`, `positions={}` → không tạo pending order.
- `test_handle_crossover_does_nothing_when_risk_rejects` — `crossover="bull"`, `positions={}`, `risk=RiskManager(capital=1.0)` (rất nhỏ, chắc chắn reject) → không tạo pending order.

## Task D — `trading/engine/main.py`: wire lại

Đổi:
```python
def on_real_signal(signal, bar) -> None:
    real_orders.handle_signal(cfg, storage, real_risk, signal, bar)
```
thành:
```python
def on_real_crossover(crossover, bar) -> None:
    real_orders.handle_crossover(cfg, storage, real_risk, crossover, bar)
```
và đổi lời gọi `process_bar(..., on_signal=on_real_signal)` thành `process_bar(..., on_crossover=on_real_crossover)`.

**Kiểm chứng:** Trong `tests/test_engine_main.py`, sửa `test_engine_run_calls_real_orders_handle_signal_on_crossover` (patch `trading.real_orders.handle_crossover` thay vì `handle_signal`, assert được gọi với `("bull"` hoặc `"bear", bar)` thay vì `(signal, bar)`).

---

## Điều kiện bắt buộc (không thoả thì DỪNG, báo cáo lại thay vì tự ý xử lý khác)

1. `grep -n "process_bar" trading/backtest.py` phải rỗng.
2. `uv run pytest tests/test_sma_cross.py -v` — mọi test CŨ (chưa sửa) phải pass y nguyên.
3. `uv run pytest tests/test_engine_logic.py -v` — `test_process_bar_submits_and_next_bar_fills` (không đụng tới) phải pass y nguyên, chứng minh hành vi paper trading không đổi.
4. Chạy **toàn bộ** suite: `docker compose up -d postgres nats && uv run pytest -v` — pass hết.
5. `grep -n "AsyncTrading\|place_limit_order\|cancel_order" trading/strategies/sma_cross.py trading/engine/logic.py trading/engine/main.py trading/real_orders.py` — rỗng.

---

## Báo cáo lại

1. Diff đầy đủ 4 file production + 3 file test.
2. Output `gitnexus_impact` cho cả 2 symbol.
3. Output đầy đủ `uv run pytest -v` (toàn bộ suite) — nêu rõ số lượng test trước/sau.
4. Xác nhận từng điều kiện bắt buộc ở trên.

Không tự commit — chờ Claude audit.
