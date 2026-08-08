# Plan: Chiến lược Momentum + RSI filter (momentum_rsi.py)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development,
> task-by-task, checkbox tracking. Run `gitnexus_impact`/`gitnexus_context` TRƯỚC
> khi sửa symbol có caller thật (strategy mới chưa có caller — kiểm tra vẫn nên
> chạy detect_changes cuối). Run `gitnexus_detect_changes` trước khi báo cáo
> xong. KHÔNG commit, KHÔNG push — báo cáo lại cho Claude (planner) review.**

## Vì sao

Spike `scripts/.spike_new_indicators_5m.py` + `scripts/.spike_rsi_combination_analysis.py`
(2026-08-09, đã ghi vào research doc) chứng minh trên cấu hình vận hành chốt
(EOD 14:20 keep 1.0, risk 2%/ngày + 2-lỗ, fee 8,250, vốn 30tr, 5m):

- **RSI 14 (70/30) CẢI THIỆN nhất quán**: 21 lệnh/52.4%/+60.05%/MaxDD 9.8%
  (baseline) → **18 lệnh/66.7%/+65.48%/MaxDD 8.1%**; ngưỡng liền kề 65/35
  cũng tốt (+62.54%, MaxDD 8.0%, không halt) → không phải đỉnh cô đơn.
- EMA filter thất bại (9/21: +8.96%, MaxDD 28.5%); trailing stop thất bại
  (mọi biến thể, kể cả kích hoạt trễ + kết hợp RSI) — KHÔNG làm ở đây.
- Plan này: đưa RSI filter thành **strategy class mới trong `trading/strategies/`**
  (duck-type `compute_crossover(bar) -> "bull"|"bear"|None` như parent), sẵn
  sàng dùng cho backtest/paper-trading. KHÔNG sửa file gốc.

Lưu ý out-of-sample: bằng chứng hiện tại mới trên 1 sample 2 tháng (~18 lệnh).
Plan này chỉ IMPLEMENT strategy + test theo spike; kiểm chứng out-of-sample
(dữ liệu dài hơn) là việc RIÊNG, ngoài phạm vi.

## Global constraints

- **File MỚI (được tạo):** `trading/strategies/momentum_rsi.py`,
  `tests/test_momentum_rsi.py`.
- **File ĐƯỢC sửa:** không bắt buộc; nếu cần helper/loader có sẵn trong
  `tests/test_derivative_backtest.py` thì được tham chiếu qua import, KHÔNG
  sửa đổi nội dung file đó trừ khi thật cần (ưu tiên self-contained).
- **KHÔNG đụng:** `trading/strategies/momentum_breakout.py` (bất khả xâm
  phạm), `trading/strategies/sma_cross.py`, `trading/derivative_backtest.py`,
  `trading/derivative_risk.py`, `trading/derivative_position.py`, engine.
- KHÔNG thêm param mới vào engine — RSI filter nằm TRONG strategy (cùng
  interface duck-typed), đúng tinh thần tách biệt signal/detection.
- Không đặt lệnh thật; không commit.

---

### Task 1: `MomentumRSIStrategy` (mới) + unit tests (TDD)

**Files:** `trading/strategies/momentum_rsi.py` (mới),
`tests/test_momentum_rsi.py` (mới).

- [ ] **Bước 1 — viết test trước** (`tests/test_momentum_rsi.py`):
  - `test_bull_suppressed_when_rsi_overbought`: chuỗi giá ĐÃ XÁC NHẬN qua
    `compute_crossover()` trực tiếp trước khi viết (kỹ thuật chuẩn của repo):
    20 bar tăng liên tiếp (close = 100..119, high=low=close, volume 100) →
    RSI = 100 (avg_loss = 0); bar thứ 21: close=125, volume=250 (≥ 2×100 =
    volume spike) vượt channel high 5-bar (119) → parent
    `MomentumBreakoutStrategy` trả "bull", `MomentumRSIStrategy` trả **None**
    (RSI 100 ≥ 70).
  - `test_bear_suppressed_when_rsi_oversold`: 20 bar giảm liên tiếp (119..100)
    → RSI = 0; bar 21: close=95, volume=250 → parent "bear",
    `MomentumRSIStrategy` trả **None** (RSI 0 ≤ 30).
  - `test_bull_passes_when_rsi_mid_range`: chuỗi dao động (lên-xuống xen kẽ)
    giữ RSI trong 30-70 → bar breakout → parent "bull", RSI strategy cũng
    "bull" (filter không chặn). Xác nhận RSI thực tế trong khoảng bằng cách
    in giá trị khi verify.
  - `test_warmup_returns_none`: chuỗi ngắn (< 20 bar) → cả 2 đều None (warmup
    kế thừa từ parent: cần đủ `lookback` + `volume_period`).
  Chạy → RED (file strategy chưa tồn tại).

- [ ] **Bước 2 — implement** `trading/strategies/momentum_rsi.py`:
  - `class MomentumRSIStrategy(MomentumBreakoutStrategy)` — override
    `compute_crossover`: gọi `super().compute_crossover(bar)` trước (cập nhật
    state channel/volume/ATR của parent), cập nhật RSI Wilder
    (`rsi_period=14` closes seed → smoothed avg gain/loss), rồi lọc:
    `sig == "bull" and rsi >= rsi_high` → None; `sig == "bear" and rsi <=
    rsi_low` → None; nếu RSI chưa sẵn sàng (warmup) → None.
  - Params: `rsi_period: int = 14`, `rsi_high: float = 70.0`,
    `rsi_low: float = 30.0` (default trùng spike đã chứng minh), `**kw` truyền
    xuống parent.
  - Helper RSI state trong cùng file (pattern flat như `TrailingStopManager`/
    `AtrCalculator`), state theo symbol.
  - Ghi chú design trong docstring: filter tác động cả lệnh MỞ lẫn ĐÓNG cùng
    chiều (bull cũng là tín hiệu đóng short) — trend-following chủ ý, đúng
    spike.

- [ ] **Bước 3:** chạy lại test Bước 1 → PASS. `uv run pytest
  tests/test_momentum_rsi.py -v` xanh.

---

### Task 2: Engine regression test (chốt config trên sample thật)

**Files:** `tests/test_momentum_rsi.py` (mới — self-contained, không sửa file
test cũ).

- [ ] **Bước 1 — viết test trước**
  `test_chot_config_with_rsi_matches_spike_results`: load sample
  `scripts/.spike_derivative_ohlc_5m_2m_sample.json` (loader giống
  `test_real_captured_ohlc_sample_runs_end_to_end` trong
  `tests/test_derivative_backtest.py` — tham chiếu pattern, tự viết loader),
  chạy `run_derivative_backtest(bars, MomentumRSIStrategy(qty=1, lookback=5,
  volume_multiplier=2.0, volume_period=20, atr_pct_threshold=0.001),
  DerivativeRiskManager(capital=30_000_000, max_contracts=1), 30_000_000,
  intraday_close_time=time(14, 20), eod_keep_min_profit_points=1.0)`.
  Assert: `report.trades == 18`, `report.win_rate == pytest.approx(0.6667,
  abs=0.001)`, `report.realized_pnl == 19_081_500.0` (con số spike đã chạy
  thật — nếu lệch, dừng báo cáo, không tự sửa số).
  Chạy → RED (strategy chưa tồn tại / hoặc chưa khớp).

- [ ] **Bước 2:** (strategy đã có từ Task 1) chạy lại → PASS; nếu số lệch
  ± vài trăm nghìn → dừng, báo cáo Claude (có thể do thứ tự bar/loader khác
  spike — cần xác minh, không tự cho qua).

- [ ] **Bước 3:** `uv run pytest tests/test_momentum_rsi.py tests/test_derivative_backtest.py -v`
  → toàn bộ PASS (không phá test cũ).

---

### Task 3: Regression toàn cục + báo cáo

- [ ] **Bước 1:** `uv run pytest -m "not integration" -v` — toàn bộ suite
  PASS (163 test hiện tại + test mới).
- [ ] **Bước 2:** `uv run ruff check trading tests` — sạch.
- [ ] **Bước 3:** `gitnexus_detect_changes()` — xác nhận phạm vi ĐÚNG (chỉ
  file mới `momentum_rsi.py` + `test_momentum_rsi.py`; không lan sang
  momentum_breakout.py/engine/risk).
- [ ] **Bước 4:** báo cáo lại cho Claude (planner): test pass/fail, ruff,
  gitnexus, xác nhận số khớp spike (+65.48%/8.1%/18 lệnh). **KHÔNG commit,
  KHÔNG push.**

---

## Ngoài phạm vi (KHÔNG làm trong plan này)

1. **Out-of-sample / dữ liệu dài hơn 2 tháng** — cần nguồn dữ liệu mới,
   việc riêng (plan riêng khi có data).
2. **EMA trend filter** — spike thất bại (+8.96% MaxDD 28.5%), đóng.
3. **Trailing stop / SL/TP thêm** — spike âm tính toàn diện (thuần, kích
   hoạt trễ, kết hợp RSI), đóng; engine giữ nguyên (chỉ SL/TP cố định đã có).
4. **Đổi hằng số phí / margin model** — theo spec 2026-08-09, giữ 8,250.
