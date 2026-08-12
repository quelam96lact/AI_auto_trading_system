# Prompt thực thi: Fix lệnh SELL thật không tôn trọng T+2,5 (sellable_quantity)

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `PLAN_REAL_ORDER_PLACEMENT.md` (đặc biệt mục lỗ hổng SELL mới phát hiện) — prompt này sửa đúng 1 lỗ hổng thiết kế, KHÔNG phải thêm tính năng mới.

---

## ⚠️ Bối cảnh — vì sao cần fix này

Thị trường CK Việt Nam: cổ phiếu mua về **T+2,5** (về tài khoản cuối T+2, chỉ bán được từ sáng T+3), tiền bán về **T+2**. Tài khoản Cash (không margin) **chỉ được bán cổ phiếu đã thực sự khả dụng** — SSI trả về đúng số này qua field `sellable_quantity` (khác `quantity` là tổng nắm giữ, gồm cả phần chưa settle).

**Lỗ hổng đã audit xác nhận:** pipeline sinh lệnh thật hiện tại lấy `signal.qty` cho tín hiệu SELL từ `PaperBroker.position_qty()` (mô phỏng giấy, `trading/engine/logic.py::process_bar()` gọi `strategy.on_bar(bar, broker)` với `broker` là `PaperBroker`) — **hoàn toàn không liên quan** tài khoản Cash thật đang nắm giữ bao nhiêu. Đồng thời `Storage.read_real_positions()` (dùng bởi `real_orders.handle_signal()`) chỉ đọc `quantity` (tổng), bỏ qua `sellable_quantity` — nghĩa là ngay cả khi số lượng đúng tình cờ, hệ thống vẫn không biết cổ phiếu đó đã settle (T+2,5) hay chưa. `RiskManager.approve()` cũng không có nhánh kiểm tra SELL theo holdings (chỉ nhánh BUY check capital/max_positions).

**Fix này KHÔNG sửa nguồn signal** (đó là thiết kế cả hệ thống signal-generation, ngoài phạm vi 1 fix nhỏ) — chỉ thêm 1 lớp bảo vệ ở đúng ranh giới giữa "signal chung" và "pipeline lệnh thật": trước khi ghi `pending_real_orders`, **cap số lượng SELL theo `sellable_quantity` thật của tài khoản Cash**, và **bỏ qua hoàn toàn** (không tạo pending order) nếu không có gì khả dụng để bán.

---

## ⚠️ Giới hạn phạm vi

**Chỉ sửa 2 file production:** `trading/storage/db.py` (thêm dataclass `RealPosition`, sửa `read_real_positions()`), `trading/real_orders.py` (thêm logic cap SELL trong `handle_signal()`).

**KHÔNG sửa:**
- `trading/broker.py::Position` — dùng chung với `PaperBroker`, không thêm field vào đây (tránh ảnh hưởng paper trading).
- `trading/risk.py::RiskManager` — không thêm nhánh kiểm tra SELL vào `approve()` (PaperBroker đã tự cap sell nội bộ rồi, không cần sửa logic dùng chung; risk.py giữ nguyên type hint `dict[str, Position]`, vì `RealPosition` chỉ cần có cùng attribute `.qty` để tương thích — không cần Protocol/type nghiêm ngặt hơn, giữ đơn giản).
- `trading/engine/logic.py`, `trading/engine/main.py`, `scripts/confirm_real_order.py` — không đụng.
- `trading/strategies/sma_cross.py` — vấn đề "SELL signal quantity lấy từ PaperBroker" là kiến trúc tổng thể của signal-generation, KHÔNG sửa ở đây (out of scope, cần thiết kế lại rộng hơn nếu muốn giải quyết tận gốc — báo cáo lại nếu thấy cần, không tự ý mở rộng).

**KHÔNG tự commit, không tự push.**

---

## Task A — `trading/storage/db.py`

1. Thêm dataclass mới (đặt gần import `Position`/`Fill` ở đầu file):
   ```python
   @dataclass
   class RealPosition:
       symbol: str
       qty: int
       avg_price: float
       sellable_qty: int
   ```
   (Cần `from dataclasses import dataclass` — kiểm tra đã import chưa, `db.py` hiện chưa dùng dataclass trực tiếp nên có thể cần thêm import này.)

2. Sửa `read_real_positions()` — đổi kiểu trả về, thêm cột `sellable_quantity` vào SELECT:
   ```python
   def read_real_positions(self, account_no: str) -> dict[str, RealPosition]:
       """Đọc account_position_snapshot, lấy ts mới nhất theo account_no.

       KHÔNG correlate thêm theo symbol — nếu correlate cả symbol, mã đã bán hết
       sẽ không bao giờ bị ghi đè, hiện vĩnh viễn. Trả về dict[symbol, RealPosition]
       chỉ gồm các symbol có quantity > 0. `sellable_qty` (khác `qty` — tổng nắm giữ)
       là số cổ phiếu THẬT SỰ khả dụng để bán (SSI đã tự trừ phần chưa settle T+2,5) —
       dùng để cap số lượng SELL ở real_orders.handle_signal(), KHÔNG được bỏ qua.
       """
       with self.conn() as c:
           rows = c.execute(
               "SELECT symbol, quantity, cost_price, sellable_quantity FROM account_position_snapshot "
               "WHERE account_no = %s AND ts = (SELECT max(ts) FROM account_position_snapshot WHERE account_no = %s) "
               "AND quantity > 0",
               (account_no, account_no),
           ).fetchall()
       return {r[0]: RealPosition(r[0], r[1], r[2], r[3]) for r in rows}
   ```

**Kiểm chứng:** Sửa test hiện có `tests/test_storage.py::test_read_real_positions_ignores_older_snapshot_for_sold_symbol` — đổi assertion cuối từ `Position("HPG", 50, 20000.0)` thành `RealPosition("HPG", 50, 20000.0, 50)` (import `RealPosition` từ `trading.storage.db`, dữ liệu test hiện có `sellable_quantity=50` cho HPG). Thêm 1 test mới `test_read_real_positions_reports_sellable_qty_lower_than_qty` — seed 1 snapshot với `quantity=100, sellable_quantity=30` (mô phỏng cổ phiếu chưa settle T+2,5), assert `read_real_positions()` trả về `RealPosition(symbol, 100, cost_price, 30)` — 2 số khác nhau, không bị nhầm lẫn.

Chạy `docker compose up -d postgres nats && uv run pytest tests/test_storage.py -v` — pass hết (test cũ đã sửa + test mới).

---

## Task B — `trading/real_orders.py`

Trong `handle_signal()`, thêm logic cap/skip cho SELL **ngay sau khi có `positions`, TRƯỚC khi gọi `risk.approve()`**:

```python
positions = storage.read_real_positions(cfg.real_order_account)
today = bar.ts.date()
daily_pnl = storage.read_real_daily_pnl(cfg.real_order_account, today)

if signal.side == "SELL":
    pos = positions.get(signal.symbol)
    sellable = pos.sellable_qty if pos is not None else 0
    if sellable <= 0:
        # Không có gì khả dụng để bán (chưa nắm giữ, hoặc cổ phiếu chưa settle T+2,5) —
        # không tạo pending order, không cố gửi lệnh biết trước sẽ sai/bị SSI từ chối.
        return
    if signal.qty > sellable:
        signal = Signal(symbol=signal.symbol, side=signal.side, qty=sellable)

if not risk.approve(signal, bar.close, positions, daily_pnl, today):
    return
```

(`Signal` là frozen dataclass, không sửa được tại chỗ — phải tạo instance mới. Đã import `Signal` sẵn trong file, không cần thêm import.)

**Kiểm chứng:** Thêm 2 test mới vào `tests/test_real_orders.py` (giữ nguyên các test cũ, không sửa):
- `test_handle_signal_caps_sell_quantity_to_sellable_qty` — `storage.read_real_positions.return_value = {"VCB": RealPosition("VCB", 100, 50_000.0, 30)}` (import `RealPosition` từ `trading.storage.db`), `signal = Signal(symbol="VCB", side="SELL", qty=100)` → gọi `handle_signal(...)` → assert `storage.create_pending_order` được gọi với `quantity=30` (không phải 100).
- `test_handle_signal_skips_sell_when_nothing_sellable` — `storage.read_real_positions.return_value = {}` (không nắm giữ), `signal = Signal(symbol="VCB", side="SELL", qty=100)` → assert `storage.create_pending_order.assert_not_called()` và `alert` (patch `trading.real_orders.alert`) không được gọi.

Đảm bảo 2 test BUY hiện có (`test_handle_signal_writes_pending_order_when_approved`, `test_handle_signal_does_nothing_when_risk_rejects`) vẫn pass nguyên vẹn — logic mới chỉ áp dụng khi `signal.side == "SELL"`, không ảnh hưởng nhánh BUY.

Chạy `uv run pytest tests/test_real_orders.py -v` — pass hết (2 test cũ + 2 test mới).

---

## Kiểm chứng cuối — bắt buộc chạy toàn bộ suite

```bash
docker compose up -d postgres nats
uv run pytest -v
```
Kỳ vọng: toàn bộ pass (số lượng tăng thêm đúng 3 test mới so với trước — 1 ở `test_storage.py`, 2 ở `test_real_orders.py`), không phá bất kỳ test nào khác (đặc biệt `tests/test_engine_logic.py`, `tests/test_engine_main.py` — không đụng file liên quan nhưng vẫn chạy lại full suite theo đúng nguyên tắc dự án).

`grep -n "AsyncTrading\|place_limit_order\|cancel_order" trading/storage/db.py trading/real_orders.py` — phải rỗng (không có gì thay đổi về ranh giới an toàn này).

---

## Báo cáo lại

1. Diff đầy đủ `trading/storage/db.py` và `trading/real_orders.py` + 2 file test.
2. Output đầy đủ `uv run pytest -v` (toàn bộ suite).
3. Xác nhận `grep` không có API đặt lệnh nào bị đụng tới.

Không tự commit — chờ Claude audit.
