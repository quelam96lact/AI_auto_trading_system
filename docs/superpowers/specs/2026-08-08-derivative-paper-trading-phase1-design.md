# Spec: Tín hiệu paper-trading phái sinh (VN30F1M) — Phase 1

**Ngày viết:** 2026-08-08
**Phạm vi:** `PLAN_DERIVATIVE_TRADING.md` Phase 1 — model vị thế paper-trading
+ risk gating + entrypoint backtest cho hợp đồng phái sinh `41I1G8000`
(VN30F1M front-month). **KHÔNG đặt lệnh thật, KHÔNG wire vào
collector/engine đang chạy live.** Chốt phạm vi qua buổi brainstorming với
user ngày 2026-08-08.

## Vì sao

Phase 0 (`PLAN_DERIVATIVE_TRADING.md`) đã xác nhận dữ liệu thật về
account/margin/position (account trống, chưa từng giao dịch), mã hợp đồng
front-month thật (`41I1G8000`), và — ở 1 phiên sau (2026-08-07) — dữ liệu
OHLC REST thật (1m và 5m, `scripts/.spike_derivative_ohlc_sample.json` /
`.spike_derivative_ohlc_5m_2m_sample.json`) cùng dữ liệu stream
TRADE/QUOTE/ROOM thật (`scripts/.spike_derivative_stream_sample.jsonl`).
Plan gốc đã chủ động hoãn thiết kế chiến lược tới khi có dữ liệu bar thật —
giờ dữ liệu đó đã có, nên Phase 1 có thể chốt phạm vi thật sự. Việc đặt lệnh
thật vẫn là 1 quyết định riêng, để sau, đúng tinh thần thận trọng của plan
gốc (rủi ro đòn bẩy cao hơn cổ phiếu) — tài khoản ký quỹ phái sinh vẫn đang
$0, chưa từng giao dịch, nên chưa có số ký quỹ thật/hợp đồng nào để thiết kế
margin-call model theo dữ liệu thật.

## Các quyết định đã chốt (từ buổi brainstorming)

- **Chỉ paper-trading + tín hiệu/cảnh báo.** Không gọi `place_order`/
  `cancel_order` ở đâu trong phase này. Thận trọng theo đúng tinh thần đã áp
  dụng cho `PLAN_REAL_ORDER_PLACEMENT.md` (dry-run trước khi dùng tiền
  thật), nhưng ở mức cao hơn vì phái sinh có đòn bẩy.
- **Chỉ dùng dữ liệu backtest**, không streaming live. Tái sử dụng bảng
  `bars`/`bars_daily` đã có (schema đã generic theo symbol — không cần cột
  riêng cho phái sinh), nạp qua các hàm fetch REST đã có
  `trading/collector/backfill.py::intraday_ohlc()`/`daily_ohlc()` trỏ vào
  `"41I1G8000"`. Việc wire live (streaming bar, NATS, vòng lặp engine) chủ
  động hoãn sang phase sau — phạm vi nhỏ hơn, không đụng code đang chạy live
  cho cổ phiếu.
- **Tái sử dụng nguyên `SmaCrossStrategy.compute_crossover()`, không sửa.**
  Hàm này vốn đã không chứa logic gating theo vị thế (đã tách ra ở fix
  crossover-decouple của `real_orders.py`) — có thể gọi thẳng cho hợp đồng
  phái sinh mà không cần đổi gì trong `trading/strategies/sma_cross.py`.
  Toàn bộ logic gating long/short mới nằm ở module mới, giống cách
  `real_orders.handle_crossover()` tự xây lớp gating riêng trên cùng 1 hàm
  thuần đó.
- **Module vị thế/broker/risk mới, không sửa module chung.** `qty` của 1 vị
  thế phái sinh có thể ÂM (net short) — khái niệm không tồn tại ở
  `trading/broker.py::Position`/`trading/paper_broker.py` (`PaperBroker` cổ
  phiếu không bao giờ bán khống, còn `RealPosition.sellable_qty` là khái
  niệm settlement T+2,5 không áp dụng cho phái sinh T+0). Gắn thêm xử lý dấu
  âm vào class cổ phiếu hiện có sẽ có rủi ro gây regression cho code đang
  chạy live (paper trading cổ phiếu + `real_orders.py`).
- **Giới hạn risk đơn giản, không phải margin-call model thật.**
  `max_contracts` (giới hạn cứng số hợp đồng đang mở) + `max_daily_loss_pct`
  (giống hệt hình dạng `RiskManager.max_daily_loss_pct`) — **không** phải %
  ký quỹ thật đang dùng, vì chưa có số ký quỹ/hợp đồng thật để đối chiếu
  (account chưa từng giao dịch). Đây là khoảng trống được ghi nhận rõ ràng,
  không phải đoán rồi trình bày như sự thật — margin-call model thật cần đợi
  lệnh thật đầu tiên của account mới thiết kế được theo số liệu thật, đúng
  nguyên tắc "verify bằng dữ liệu thật, không đoán hành vi SDK/account" của
  dự án.
- **`lot_size = 1`** (đã xác nhận thật từ Phase 0, khác lô 100 của cổ
  phiếu) — đạt được bằng cách khởi tạo `SmaCrossStrategy(qty=1, ...)` qua
  tham số constructor có sẵn, không cần sửa code strategy.
- **Không có ATR position sizing, không có trailing stop ở Phase 1.** Cả 2
  đã có cho cổ phiếu (`RiskManager.approve_sized()`, `TrailingStopManager`)
  nhưng thêm vào đây nghĩa là phải quyết định cách chúng tương tác với vị
  thế CÓ DẤU — ngoài phạm vi bản đầu tiên này. Mỗi vị thế cố định
  `qty=1` hợp đồng, thoát vị thế chỉ theo crossover (bull đóng short/mở
  long, bear đóng long/mở short).
- **Không tự động roll hợp đồng.** `"41I1G8000"` hardcode cho phase này. Khi
  hợp đồng gần đáo hạn (2026-08-20), mã hợp đồng front-month kế tiếp phải
  được xác nhận lại bằng dữ liệu thật trước khi dùng — không giả định theo
  quy tắc đặt tên (Phase 0 đã phát hiện mã nội bộ SSI KHÔNG theo quy ước
  công khai `VN30F+YYMM`).
- **Phí giao dịch là placeholder chưa xác nhận, ghi rõ trong code.** Biểu
  phí phái sinh của SSI (phí cố định/hợp đồng, không phải % giá trị như cổ
  phiếu) chưa được xác nhận bằng dữ liệu thật — chấp nhận được vì phase này
  hoàn toàn paper (không tiền thật), nhưng không được coi là số đúng nếu
  sau này mở rộng hướng tới đặt lệnh thật.

## Thiết kế

### `trading/derivative_position.py` (mới)

```python
@dataclass
class DerivativePosition:
    symbol: str
    qty: int = 0          # có thể ÂM (short), DƯƠNG (long), 0 (flat)
    avg_price: float = 0.0

DERIVATIVE_FEE_PER_CONTRACT = 2_700.0  # VNĐ, CHƯA xác nhận thật — placeholder cho paper-trading

class DerivativePaperBroker:
    def __init__(self, capital: float, fee_per_contract: float = DERIVATIVE_FEE_PER_CONTRACT): ...

    def position_qty(self, symbol: str) -> int: ...  # có dấu, khác PaperBroker

    def open_long(self, symbol: str, qty: int, price: float, ts: datetime) -> Fill: ...
    def open_short(self, symbol: str, qty: int, price: float, ts: datetime) -> Fill: ...
    def close(self, symbol: str, price: float, ts: datetime) -> Fill:
        """Đóng toàn bộ vị thế đang mở (dù long hay short), tính PnL đúng
        chiều (long: (price - avg_price) * qty; short: (avg_price - price) *
        |qty|)."""
```

Không có hàng đợi `submit()`/`on_bar()` kiểu equity `PaperBroker` — Phase 1
khớp lệnh ngay tại giá `close` của bar (đơn giản hoá có chủ đích: chưa mô
phỏng open/slippage cho giá khớp phái sinh, vì hành vi khớp lệnh thật của
phái sinh chưa từng được quan sát — ghi nhận rõ đây là đơn giản hoá đã biết,
đúng nguyên tắc "không mô phỏng hành vi chưa verify bằng dữ liệu thật").

### `trading/derivative_risk.py` (mới)

```python
@dataclass
class DerivativeRiskManager:
    capital: float
    max_contracts: int = 1
    max_daily_loss_pct: float = 0.03
    halted_date: date | None = field(default=None, init=False)

    def approve_open(self, side: Literal["long", "short"], current_qty: int,
                      daily_pnl: float, today: date) -> bool:
        """Cùng hình dạng halt-check như RiskManager._halt_check(). Chặn 1
        lệnh mở mới (long hoặc short) nếu hôm nay đã bị halt, hoặc nếu mở
        thêm sẽ vượt max_contracts. KHÔNG gate lệnh đóng — đóng vị thế đang
        có luôn được phép, cùng nguyên tắc RiskManager cổ phiếu không bao
        giờ chặn SELL 1 vị thế đang giữ."""
```

### `trading/derivative_backtest.py` (mới, song song `trading/backtest.py`)

```python
def run_derivative_backtest(
    bars: list[Bar],
    strategy: SmaCrossStrategy,
    risk: DerivativeRiskManager,
    capital: float,
) -> BacktestReport:  # tái dùng dataclass BacktestReport đã có ở backtest.py
```

Vòng lặp mỗi bar:
1. `crossover = strategy.compute_crossover(bar)`.
2. `net = broker.position_qty(bar.symbol)`.
3. `bull` + `net < 0` → `broker.close(...)` (cover short).
   `bull` + `net == 0` → nếu `risk.approve_open("long", net, daily_pnl, today)`: `broker.open_long(..., qty=strategy.qty, ...)`.
   `bear` + `net > 0` → `broker.close(...)`.
   `bear` + `net == 0` → nếu `risk.approve_open("short", ...)`: `broker.open_short(...)`.
   (`net != 0` và chiều crossover đã khớp với chiều đang giữ → không làm
   gì, giống cách strategy cổ phiếu không bao giờ vào lại 1 chiều đang giữ.)
4. Theo dõi equity curve dùng qty có dấu (`cash + qty * mark_price`, trong
   đó đóng góp unrealized của vị thế short tương đương
   `-qty * (avg_price - mark)`) — implement thẳng từ `DerivativePosition`,
   không copy từ `unrealized_pnl()` của equity (hàm đó giả định `qty >= 0`).

1 entrypoint CLI (block `if __name__ == "__main__":`, cùng hình dạng
`backtest.py::main()`) đọc bar cho `"41I1G8000"` từ `Storage.read_bars()`
theo khoảng `--from`/`--to`, yêu cầu khoảng đó đã được backfill sẵn vào DB
qua `intraday_ohlc()`/`daily_ohlc()` trỏ vào symbol này (chỉ cần thêm 1 dòng
ở chỗ danh sách symbol backfill hiện đang đọc từ config/CLI arg — không
phải cơ chế fetch mới).

## Testing

- `tests/test_derivative_position.py` (mới): `DerivativePaperBroker` —
  `open_long()` rồi `close()` tính đúng PnL/phí/cash cho long; `open_short()`
  rồi `close()` tính đúng PnL cho short (giá giảm = lãi) /phí/cash;
  `position_qty()` trả về số âm sau `open_short()`.
- `tests/test_derivative_risk.py` (mới): `approve_open()` chặn lệnh mở thứ 2
  vượt `max_contracts`; chặn mọi lệnh mở khi đã halt; halt kích hoạt khi
  `daily_pnl <= -capital * max_daily_loss_pct`; không gate `close` (không
  cần `approve_close` — lệnh đóng không bị gate gì cả, nên đây là test cho
  sự vắng mặt của gating, không phải test 1 method).
- `tests/test_derivative_backtest.py` (mới): chuỗi bar tổng hợp (tái dùng
  pattern helper kiểu `_gen_ohlc_rows` đã có sẵn trong test suite) chứng
  minh đủ chu trình bull→long→bear→close→short→bull→cover cho đúng chuỗi
  `Fill` và đúng dấu; 1 test ngày bị halt trong đó lỗ vượt
  `max_daily_loss_pct` chặn 1 lệnh mở mới nhưng vẫn cho phép vị thế đang mở
  được đóng.
- 1 test trong `tests/test_derivative_backtest.py` đọc trực tiếp
  `scripts/.spike_derivative_ohlc_5m_2m_sample.json` (dữ liệu thật đã
  capture, gitignored — test nên skip gọn nếu file không tồn tại thay vì
  fail, vì file này không commit vào git) và chạy
  `run_derivative_backtest()` trên đó từ đầu tới cuối như 1 smoke test đối
  chiếu hình dạng response thật, không chỉ bar tổng hợp.

## Ngoài phạm vi (nói rõ)

- Đặt lệnh thật cho phái sinh — quyết định riêng để sau, cần margin-call
  model thật dựa trên lệnh thật đầu tiên của account.
- Wire live vào collector/engine (streaming bar từ path account-sync của
  `derivative_sync.py` hoặc kênh WebSocket TRADE vào `bars`/NATS/vòng lặp
  engine) — hoãn sang phase sau.
- ATR position sizing và trailing stop cho vị thế phái sinh — hoãn lại;
  Phase 1 giữ cố định `qty=1`, thoát vị thế chỉ theo crossover.
- Tự động roll hợp đồng — chỉ hardcode `"41I1G8000"`.
- Xác nhận biểu phí phái sinh thật — dùng giá trị placeholder, ghi rõ trong
  code, chấp nhận được vì phase này không đụng tiền thật.
- Không sửa `trading/strategies/sma_cross.py`, `trading/paper_broker.py`,
  `trading/risk.py`, `trading/backtest.py`, `trading/engine/*`,
  `trading/collector/derivative_sync.py` — mọi code path cổ phiếu/monitoring
  giữ nguyên không đổi.
