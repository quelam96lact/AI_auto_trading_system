# Plan: Stop-loss / take-profit engine support cho derivative backtest

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development,
> task-by-task, checkbox tracking. **Run `gitnexus_impact`/`gitnexus_context` before
> editing `run_derivative_backtest` (đã có caller thật — tests, CLI `main`). Run
> `gitnexus_detect_changes` before reporting done. Do NOT commit, do NOT push —
> report back and stop.**

## Vì sao

Nghiên cứu trên dữ liệu thật (`docs/superpowers/research/2026-08-08-derivative-strategy-params-summary.md`,
thí nghiệm E3 trong `scripts/.spike_improve_derivative_strategies.py`) cho thấy:
engine hiện tại chỉ đóng vị thế khi có crossover ngược → lỗ chạy 5–20 điểm,
11/21 lệnh thua của Momentum default tổng -11,050,750 (avg lỗ -1,004,614),
và lợi nhuận tập trung cực cao (5/21 lệnh > +2tr = 161% tổng PnL). Thêm **stop-loss ~5 điểm, không
take-profit** cải thiện +14.71% → +18.79% trên cùng sample; TP chặt (3 điểm)
PHÁ chiến lược (-3.66%). Plan này thêm khả năng SL/TP vào
`run_derivative_backtest()` — mặc định **tắt (0)**, giữ nguyên hành vi cũ khi
không truyền tham số.

**Caveat trung thực:** sim nghiên cứu fill tại đúng mức SL/TP (lạc quan nhẹ cho
SL khi bar gap qua mức). Production theo quy ước gap ĐÃ CÓ của repo
(`TrailingStopManager.check()`: `min(bar.open, stop_level)`) — PnL thực có thể
thấp hơn spike vài phần trăm.

## Global constraints

- **Chỉ sửa 2 file:** `trading/derivative_backtest.py`,
  `tests/test_derivative_backtest.py`. Không đụng `trading/strategies/*`
  (momentum_breakout, sma_cross), `trading/derivative_position.py` (broker),
  `trading/derivative_risk.py`, `trading/engine/*`, `trading/collector/*`,
  `trading/paper_broker.py`, `trading/broker.py`, hay bất kỳ file cổ phiếu nào.
- KHÔNG đổi tham số strategy (lookback/volume/atr...) — nằm ngoài phạm vi,
  tune riêng.
- KHÔNG đặt lệnh thật, không đụng `place_order`/`AsyncTrading`.

## Thiết kế

`run_derivative_backtest(bars, strategy, risk, capital, stop_loss_points=0.0,
take_profit_points=0.0)` — mỗi bar, SAU `compute_crossover` và TRƯỚC logic
crossover, nếu đang có vị thế mở và SL/TP > 0, kiểm tra theo bar high/low
(SL ưu tiên nếu cả 2 chạm cùng bar — conservative, đúng spike):

- Long (entry E): SL nếu `bar.low <= E - sl` → giá `min(bar.open, E - sl)`;
  TP nếu `bar.high >= E + tp` → giá `max(bar.open, E + tp)`.
- Short (entry E): SL nếu `bar.high >= E + sl` → giá `max(bar.open, E + sl)`;
  TP nếu `bar.low <= E - tp` → giá `min(bar.open, E - tp)`.
- Exit bằng SL/TP qua `broker.close()` như bình thường (pnl đã tính đúng hệ số
  nhân 100,000 sau fix trước) → Fill side phản ánh hành động thật.
- Sau exit SL/TP: **bỏ qua logic crossover cùng bar** (không mở lại ngay) —
  đúng hành vi sim nghiên cứu.
- Giữ nguyên: risk gate chỉ áp cho lệnh MỞ (`approve_open`), không gate đóng.

---

### Task 1: Thêm params + SL long

**Files:** `trading/derivative_backtest.py`, `tests/test_derivative_backtest.py`.

- [x] **Bước 1 — viết test trước** (tên rõ ràng, vd
  `test_stop_loss_long_exits_at_level_on_low_touch`): dùng `bars_from_prices()`/
  `new_strategy()` có sẵn, chọn chuỗi giá đã XÁC NHẬN qua
  `SmaCrossStrategy.compute_crossover()` trực tiếp (kỹ thuật comment các test
  khác của file): bull mở long @E, bar kế tiếp có `low <= E - sl`.
  Gọi `run_derivative_backtest(bars, strategy, risk, CAP, stop_loss_points=3.0)`
  → assert: đúng 2 fill (mở + đóng), close fill giá = `min(open_bar, E-3)`,
  `pnl == (fill_price - E) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE`.
  Chạy `uv run pytest tests/test_derivative_backtest.py::test_stop_loss_long_exits_at_level_on_low_touch -v`
  → FAIL (lần 1: TypeError thiếu param — feature missing; sau Bước 2a: fail
  assertion vì chưa có logic SL).

- [x] **Bước 2 — implement:** thêm `stop_loss_points: float = 0.0` và
  `take_profit_points: float = 0.0` vào signature `run_derivative_backtest`.
  Thêm nhánh kiểm tra SL/TP cho LONG trước (đúng công thức Thiết kế).

- [x] **Bước 3:** chạy lại test Bước 1 → PASS.

---

### Task 2: SL short

**Files:** `trading/derivative_backtest.py`, `tests/test_derivative_backtest.py`.

- [x] **Bước 1 — viết test trước** (vd `test_stop_loss_short_exits_at_level_on_high_touch`):
  chuỗi giá XÁC NHẬN qua `compute_crossover()`: bear mở short @E từ flat, bar
  kế tiếp có `high >= E + sl`. `stop_loss_points=3.0` → assert đúng 2 fill,
  close giá = `max(open_bar, E+3)`,
  `pnl == (E - fill_price) * 1 * DERIVATIVE_CONTRACT_MULTIPLIER - FEE`, pnl < 0.
  Chạy test → FAIL.

- [x] **Bước 2 — implement:** nhánh SL short (đúng công thức Thiết kế).

- [x] **Bước 3:** chạy lại → PASS.

---

### Task 3: TP long + TP short

**Files:** `trading/derivative_backtest.py`, `tests/test_derivative_backtest.py`.

- [x] **Bước 1 — viết test trước** (2 test: `..._take_profit_long...`,
  `..._take_profit_short...`): tương tự Task 1/2 nhưng `take_profit_points>0`
  (SL=0), bar kế tiếp chạm mức TP ngược chiều → close fill giá = `max(open,
  E+tp)` (long) / `min(open, E-tp)` (short), pnl > 0 đúng công thức.
  Chạy cả 2 → FAIL.

- [x] **Bước 2 — implement:** nhánh TP long + short (đúng công thức Thiết kế).

- [x] **Bước 3:** chạy lại cả 2 → PASS.

---

### Task 4: SL ưu tiên khi trùng bar + không mở lại cùng bar

**Files:** `trading/derivative_backtest.py`, `tests/test_derivative_backtest.py`.

- [x] **Bước 1 — viết test trước** (vd `test_stop_loss_takes_priority_when_tp_and_sl_both_hit_same_bar`):
  bar duy nhất có cả `low <= E - sl` lẫn `high >= E + tp` (bar nến rộng) →
  assert close tại mức SL (conservative), không phải TP. Test thứ 2
  (`test_no_reentry_on_same_bar_after_exit`): sau exit SL/TP, crossover cùng
  bar KHÔNG mở vị thế mới → `len(fills)` không tăng thêm open ở bar đó.
  Chạy cả 2 → FAIL.

- [x] **Bước 2 — implement:** ưu tiên SL; sau exit SL/TP `continue` bỏ qua
  logic crossover cùng bar.

- [x] **Bước 3:** chạy lại cả 2 → PASS.

---

### Task 5: Regression — mặc định tắt = hành vi cũ + verify toàn bộ

**Files:** `tests/test_derivative_backtest.py` (không cần sửa — chạy lại).

- [x] **Bước 1:** chạy `uv run pytest tests/test_derivative_backtest.py -v` —
  toàn bộ test cũ (cycle long/short, halted-day, unrealized multiplier, smoke
  data thật) PASS KHÔNG đổi — chứng minh default 0/0 giữ nguyên hành vi.
- [x] **Bước 2:** `uv run pytest -m "not integration" -v` — toàn bộ suite PASS
  (gồm momentum tests gọi `run_derivative_backtest()` gián tiếp, không truyền
  params mới → không đổi hành vi).
- [x] **Bước 3:** `uv run ruff check trading tests` — sạch.
- [x] **Bước 4:** chạy `gitnexus_detect_changes()` — xác nhận phạm vi ĐÚNG 2
  file đã liệt kê, không lan ra file khác.
- [x] **Bước 5:** báo cáo lại: test pass/fail, `ruff check` output,
  `gitnexus_detect_changes()` output, và (nếu có) chuỗi giá mới đã chọn kèm
  bằng chứng `compute_crossover()`. **Không commit, không push.**
