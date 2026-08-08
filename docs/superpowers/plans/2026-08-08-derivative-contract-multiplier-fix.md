# Fix: VN30F1M contract multiplier missing in PnL calculation

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development,
> task-by-task, checkbox tracking. **Run `gitnexus_impact`/`gitnexus_context` before
> editing `DerivativePaperBroker.close()` or `_unrealized()` (both already have real
> callers — `derivative_backtest.py`, existing tests). Run `gitnexus_detect_changes`
> before reporting done. Do NOT commit, do NOT push — report back and stop.**

## Vì sao (bug tái hiện được)

Backtest chạy trên dữ liệu VN30F1M **thật** (`scripts/.spike_derivative_ohlc_5m_2m_sample.json`)
cho thấy: BUY @1900.8 → SELL @2009.2 (giá tăng ĐÚNG hướng cho long, +8.4 điểm)
nhưng `close_fill.pnl = -2691.6` — lỗ, dù đoán đúng hướng. Nguyên nhân:
`DerivativePaperBroker.close()` tính `pnl = (price - avg_price) * qty - fee`,
coi **1 điểm chỉ số = 1 VNĐ**. Hợp đồng VN30F1M thật (VN30 Index Futures,
niêm yết HNX) có **hệ số nhân công khai 100,000 VNĐ/điểm** — đây là đặc tả hợp
đồng do sở giao dịch công bố (không phải hành vi SDK/account cần verify bằng
dữ liệu thật như biểu phí), nên dùng được ngay làm hằng số, khác với
`DERIVATIVE_FEE_PER_CONTRACT` (biểu phí SSI thật vẫn CHƯA xác nhận — giữ
nguyên là placeholder, KHÔNG thuộc phạm vi task này).

Thiếu hệ số này khiến phí cố định (2,700đ placeholder) luôn lớn hơn nhiều so
với biến động giá được tính sai theo tỉ lệ 1:1, nên MỌI lệnh khớp đều trông
như lỗ bất kể hướng — làm hỏng hoàn toàn ý nghĩa của win-rate/PnL trong bất
kỳ backtest phái sinh nào (không riêng gì strategy mới `MomentumBreakoutStrategy`
từ `docs/superpowers/plans/2026-08-08-momentum-breakout-strategy.md`).

## Global constraints

- **Chỉ sửa 4 file:** `trading/derivative_position.py`,
  `trading/derivative_backtest.py`, `tests/test_derivative_position.py`,
  `tests/test_derivative_backtest.py`. Không đụng
  `trading/strategies/momentum_breakout.py`,
  `trading/strategies/sma_cross.py`, `trading/derivative_risk.py`,
  `trading/paper_broker.py`, `trading/broker.py`, `trading/engine/*`,
  `trading/collector/*`, hay bất kỳ file cổ phiếu nào.
- `DERIVATIVE_FEE_PER_CONTRACT` giữ nguyên placeholder — task này chỉ thêm hệ
  số nhân điểm, không đụng biểu phí.
- Không đặt lệnh thật, không sửa gì liên quan `place_order`/`AsyncTrading`.

---

### Task 1: Thêm `DERIVATIVE_CONTRACT_MULTIPLIER` + sửa `close()`

**Files:** `trading/derivative_position.py`, `tests/test_derivative_position.py`.

- [ ] **Bước 1 — viết test tái hiện bug trước:** thêm 1 test mới vào
  `tests/test_derivative_position.py` xác nhận đúng công thức có hệ số nhân,
  ví dụ (đặt tên rõ ràng, vd `test_close_pnl_applies_contract_multiplier`):
  mở long tại giá 1900.0, đóng tại 1910.0 (chênh 10 điểm), FEE=2_700.0 →
  `expected_pnl = (1910.0 - 1900.0) * 1 * 100_000.0 - 2_700.0` (=997,300.0).
  Chạy `uv run pytest tests/test_derivative_position.py::test_close_pnl_applies_contract_multiplier -v`
  → phải FAIL (code hiện tại tính `expected_pnl` sai, ra -2690.0).

- [ ] **Bước 2 — implement:** thêm hằng số
  `DERIVATIVE_CONTRACT_MULTIPLIER = 100_000.0` cạnh
  `DERIVATIVE_FEE_PER_CONTRACT` (docstring ghi rõ: đặc tả hợp đồng công khai
  của HNX cho VN30 Index Futures, khác biểu phí — biểu phí vẫn là
  placeholder chưa xác nhận, hệ số nhân điểm là số công khai của sở giao
  dịch). Thêm tham số `contract_multiplier: float =
  DERIVATIVE_CONTRACT_MULTIPLIER` vào `DerivativePaperBroker.__init__`
  (cùng pattern với `fee_per_contract` đã có, lưu vào `self.contract_multiplier`).
  Sửa `close()`: nhân thêm `self.contract_multiplier` vào phần chênh lệch
  giá (trước khi trừ fee) ở cả 2 nhánh long/short.

- [ ] **Bước 3:** chạy lại test ở Bước 1 → PASS.

- [ ] **Bước 4 — cập nhật 3 test cũ đã hardcode công thức sai:**
  `test_open_long_then_close_computes_pnl_fee_cash`,
  `test_open_short_then_close_computes_pnl_for_price_drop`,
  `test_open_short_then_close_at_higher_price_is_a_loss` — sửa dòng
  `expected_pnl = ...` thêm `* 100_000.0` (hoặc `* DERIVATIVE_CONTRACT_MULTIPLIER`
  import từ module) vào đúng vị trí công thức (nhân vào phần chênh lệch giá,
  KHÔNG nhân vào fee). Chạy `uv run pytest tests/test_derivative_position.py -v`
  → tất cả PASS.

---

### Task 2: `_unrealized()` trong `derivative_backtest.py` phải nhất quán

**Files:** `trading/derivative_backtest.py`, `tests/test_derivative_backtest.py`.

`_unrealized()` tự tính `(mark - pos.avg_price) * pos.qty` (long) /
`(pos.avg_price - mark) * abs(pos.qty)` (short) — độc lập với
`DerivativePaperBroker.close()`, nên cũng thiếu hệ số nhân, làm
`unrealized_pnl`/`max_drawdown`/equity curve trong `BacktestReport` sai theo
đúng kiểu bug ở Task 1.

- [ ] **Bước 1 — viết test trước:** thêm 1 test mới (vd
  `test_report_unrealized_pnl_applies_contract_multiplier`) dựng 2 bar: bar1
  mở long qua crossover (dùng lại `new_strategy()`/`bars_from_prices()` có
  sẵn trong file), bar2 KHÔNG đóng vị thế (giữ nguyên xu hướng, không có
  crossover ngược) nhưng giá đã đổi — assert
  `report.unrealized_pnl == (mark_bar2 - open_price) * qty *
  DERIVATIVE_CONTRACT_MULTIPLIER` (không trừ fee — `_unrealized()` hiện tại
  không trừ fee cho vị thế đang mở, giữ nguyên hành vi đó, chỉ thêm hệ số
  nhân). Import `DERIVATIVE_CONTRACT_MULTIPLIER` từ
  `trading.derivative_position`. Chạy test → FAIL.

- [ ] **Bước 2 — implement:** sửa `_unrealized()` trong
  `trading/derivative_backtest.py` — nhân thêm `broker.contract_multiplier`
  (đọc từ instance `broker` đã có, KHÔNG hardcode lại số) vào cả 2 nhánh
  long/short.

- [ ] **Bước 3:** chạy lại test → PASS.

- [ ] **Bước 4 — cập nhật 2 test cũ có `expected_pnl` sai công thức:**
  `test_long_cycle_bull_opens_long_then_bear_closes_it`,
  `test_short_cycle_bear_opens_short_from_flat_then_bull_covers_it` — thêm
  `* 100_000.0` vào phần chênh lệch giá trong `expected_pnl`, cùng cách Task 1
  Bước 4.

- [ ] **Bước 5 — thiết kế lại `test_halted_day_blocks_new_open_after_loss_breaches_threshold`:**
  Chuỗi giá cũ dùng round-trip bull(11)→bear(16) làm "khoản lỗ" chỉ vì phí
  che mất lãi 5 điểm — SAU KHI SỬA BUG, (16-11)*100_000-2700 = +497,300, tức
  là LÃI, không còn kích hoạt halt được nữa. Phải thiết kế lại chuỗi giá cho
  round-trip ĐẦU TIÊN thật sự lỗ (vd mở long rồi giá giảm khi đóng, hoặc mở
  short rồi giá tăng khi đóng — tự chọn, miễn round-trip đầu tiên có
  `(price_close - price_open) * qty * 100_000 - fee < 0` VÀ khoản lỗ đó vượt
  `-capital * max_daily_loss_pct` đã set trong test). Xác nhận chuỗi giá
  bằng cách chạy `SmaCrossStrategy.compute_crossover()` trực tiếp trước
  (cùng kỹ thuật "đã xác nhận thật" ghi trong comment các test khác của file
  này) để biết chính xác bar nào bull/bear, không đoán. Giữ nguyên mục đích
  test: round-trip đầu lỗ vượt ngưỡng → halt → lệnh mở thứ 2 (bull sau đó)
  bị chặn, `len(report.fills) == 2`, `risk.halted_date is not None`.

---

### Task 3: Full-suite verification + report

- [ ] `uv run pytest -m "not integration" -v` — toàn bộ suite PASS (bao gồm
      cả `tests/test_momentum_breakout_strategy.py`,
      `tests/test_momentum_breakout_derivative_integration.py` — 2 file này
      KHÔNG hardcode giá trị pnl tuyệt đối nên không cần sửa, nhưng phải xác
      nhận vẫn PASS vì chúng gọi `run_derivative_backtest()` gián tiếp).
- [ ] `uv run ruff check trading tests` — sạch.
- [ ] Chạy `gitnexus_detect_changes()` — xác nhận phạm vi thay đổi đúng 4
      file đã liệt kê ở Global constraints, không lan ra file khác.
- [ ] Báo cáo lại: test pass/fail, `ruff check` output,
      `gitnexus_detect_changes()` output, và chuỗi giá mới đã chọn cho Task 2
      Bước 5 (kèm giải thích vì sao nó tạo ra lỗ thật). **Không commit,
      không push.**
