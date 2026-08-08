# Plan: Sửa daily-loss halt tính theo NGÀY + ngưỡng giữ lãi EOD tính chi phí qua đêm

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development,
> task-by-task, checkbox tracking. **Run `gitnexus_impact`/`gitnexus_context` TRƯỚC
> khi sửa `run_derivative_backtest` (caller thật — tests, CLI `main`). Run
> `gitnexus_detect_changes` trước khi báo cáo xong. KHÔNG commit, KHÔNG push —
> báo cáo lại cho Claude (planner) review.**

## Vì sao

Phân tích margin với vốn 30,000,000 (`scripts/.spike_margin_analysis_30m.py`) phát hiện 2 vấn đề:

1. **`daily_pnl` truyền vào `approve_open` là PnL TÍCH LŨY từ đầu chuỗi**
   (`broker.realized_pnl + _unrealized(broker, marks)`), không phải theo ngày.
   Với vốn 30tr (ngưỡng 2% = 600,000), lệnh thua đầu tiên -608,250 khiến
   cumulative ≤ -600,000 → halt, và vì cumulative KHÔNG BAO GIỜ phục hồi
   (chỉ giảm thêm), MỌI lệnh mở sau đó đều bị chặn vĩnh viễn: backtest 30tr
   không-EOD chỉ còn **1 lệnh** cả 2 tháng (100tr: 17 lệnh, +20.25%).
   Đúng nghĩa "daily loss" phải là lỗ PHÁT SINH TRONG NGÀY HÔM NAY, reset
   mỗi ngày.

2. **Ngưỡng "giữ lãi qua đêm" (`_unrealized() <= 0` mới đóng) không tính chi
   phí qua đêm.** Lệnh lãi gross nhỏ (vd +50,000) được giữ nhưng phải trả
   phí D+ qua đêm ~87,000/đêm (0.0487%/ngày trên phần tài trợ ≈ 94% giá trị
   HĐ @1900) + phí đóng 8,250 → lỗ ròng. Nên chỉ GIỮ khi lãi đủ bù chi phí
   qua đêm + phí đóng (≈ 1 điểm @1900), phần còn lại đóng tại cutoff.

## Global constraints

- **Chỉ sửa/thêm:** `trading/derivative_backtest.py`,
  `tests/test_derivative_backtest.py`, script
  `scripts/.spike_margin_analysis_30m.py` (đã có, cập nhật), và **append**
  vào `docs/superpowers/research/2026-08-09-derivative-risk-eod-verification.md`.
- **KHÔNG đụng:** `trading/derivative_risk.py` (chỉ sửa CÁCH ENGINE tính
  `daily_pnl` — risk manager giữ nguyên, `approve_open`/`_halt_check` không
  đổi), `trading/strategies/*`, `trading/derivative_position.py`,
  `trading/engine/*`, file cổ phiếu.
- KHÔNG implement mô hình margin đầy đủ (17%, margin call, force-close khi
  equity < margin) — ngoài phạm vi (đã flag từ plan 2026-08-09), cần spec
  riêng. Hằng số D+ (0.0487%/ngày, margin 6%) chỉ dùng trong SCRIPT tính
  toán, KHÔNG hardcode vào engine — ngưỡng là tham số user truyền.
- Giữ nguyên default = hành vi cũ khi không truyền tham số mới.
- KHÔNG đặt lệnh thật.

---

### Task 1: `daily_pnl` tính theo NGÀY trong `run_derivative_backtest`

**Files:** `trading/derivative_backtest.py`, `tests/test_derivative_backtest.py`.

- [ ] **Bước 1 — viết test trước** (vd
  `test_daily_loss_halt_resets_next_day_not_cumulative`): vốn 30,000,000
  (ngưỡng 2% = 600,000). Chuỗi giá ĐÃ XÁC NHẬN qua `compute_crossover()`
  trực tiếp (kỹ thuật comment các test khác trong file):
  - Ngày 1 (08-08): `[10,10,10,10,11,4]` — bull bar4 @11 (mở long), bear
    bar5 @4 (đóng: pnl = (4-11)*100,000 - 8,250 = **-708,250** ≤ -600,000).
  - Ngày 2 (08-09): `[13,16]` — bar @13 không crossover, bar @16 **bull**
    (tín hiệu mở long từ flat).
  Assert: `len(report.fills) == 4` (ngày 2 mở được lệnh mới — daily pnl
  ngày 2 bắt đầu từ 0), `report.trades == 2`, `risk.halted_date is None`.
  Chạy → FAIL (code hiện tại: cumulative -708,250 ≤ -600,000 → lệnh ngày 2
  bị chặn, chỉ 2 fills).

- [ ] **Bước 2 — implement:** trong `run_derivative_backtest`, theo dõi
  `current_day: date | None = None` và `day_start_realized: float = 0.0`.
  Mỗi bar, nếu `bar.ts.date() != current_day`: gán `current_day =
  bar.ts.date()` và `day_start_realized = broker.realized_pnl` (thời điểm
  đầu ngày, trước mọi fill). Đổi dòng
  `daily_pnl = broker.realized_pnl + _unrealized(broker, marks)` thành
  `daily_pnl = (broker.realized_pnl - day_start_realized) +
  _unrealized(broker, marks)` — lỗ/ lãi chỉ tính trong ngày hiện tại
  (realized hôm nay + unrealized vị thế đang mở), reset mỗi ngày.

- [ ] **Bước 3:** chạy lại test Bước 1 → PASS. Chạy
  `uv run pytest tests/test_derivative_backtest.py -v` → toàn bộ PASS
  (test cũ không đổi hành vi: vốn 100tr, không lệnh nào đơn lẻ chạm 2% =
  2,000,000 nên per-day hay cumulative đều không halt — xác minh bằng chạy,
  không giả định).

---

### Task 2: Param `eod_keep_min_profit_points` — chỉ giữ lãi đủ bù chi phí qua đêm

**Files:** `trading/derivative_backtest.py`, `tests/test_derivative_backtest.py`.

- [ ] **Bước 1 — viết test trước** (3 test):
  - `test_eod_keep_min_profit_points_closes_small_profit_below_threshold`:
    `[10,10,10,10,11]` (bull bar4 @11, mở long) + bar 14:25 close=11.5
    (unrealized +50,000, ĐÃ XÁC NHẬN không crossover). Truyền
    `intraday_close_time=time(14,20), eod_keep_min_profit_points=1.0`
    (ngưỡng = 100,000 VND): 50,000 ≤ 100,000 → ĐÓNG tại bar.close=11.5.
    Assert 2 fills, close price 11.5.
  - `test_eod_keep_min_profit_points_keeps_profit_above_threshold`: cùng
    chuỗi nhưng bar 14:25 close=12.5 (unrealized +150,000 > 100,000) →
    GIỮ. Assert 1 fill (chỉ mở long).
  - `test_eod_keep_min_profit_points_default_zero_keeps_any_profit`
    (regression): default 0.0, bar 14:25 close=11.5 (+50,000) → GIỮ (hành
    vi hiện tại). Assert 1 fill.
  Chạy 3 test → FAIL (2 test đầu: TypeError thiếu param; test 3 PASS sẵn).

- [ ] **Bước 2 — implement:** thêm param
  `eod_keep_min_profit_points: float = 0.0` vào `run_derivative_backtest`.
  Trong nhánh EOD close, đổi điều kiện đóng từ
  `_unrealized(broker, marks) <= 0` thành
  `_unrealized(broker, marks) <= eod_keep_min_profit_points *
  DERIVATIVE_CONTRACT_MULTIPLIER` (import hằng số từ
  `trading.derivative_position`, không hardcode 100,000). Default 0.0 =
  hành vi cũ.

- [ ] **Bước 3:** chạy lại 3 test Bước 1 → PASS. Chạy
  `uv run pytest tests/test_derivative_backtest.py -v` → toàn bộ PASS.

---

### Task 3: Backtest lại (30tr vs 100tr) với 2 fix + ghi research doc

**Files:** `scripts/.spike_margin_analysis_30m.py` (cập nhật),
`docs/superpowers/research/2026-08-09-derivative-risk-eod-verification.md` (append).

- [ ] **Bước 1:** cập nhật script `.spike_margin_analysis_30m.py`: thêm 2
  cấu hình cho vốn 30tr với `eod_keep_min_profit_points=1.0` (≈ chi phí D+
  1 đêm ~0.87 điểm + phí đóng 0.08 điểm @1900 — ghi rõ giả định):
  - 30tr không EOD (kiểm tra fix Task 1: giờ phải có nhiều hơn 1 lệnh).
  - 30tr EOD giữ lãi ngưỡng 1.0 điểm (so với ngưỡng 0.0 hiện tại).
  In: số lệnh, win rate, PnL, return, MaxDD, halted_date cho mọi cấu hình
  (100tr/30tr × không-EOD/EOD-0.0/EOD-1.0).

- [ ] **Bước 2:** chạy
  `PYTHONPATH=. uv run python scripts/.spike_margin_analysis_30m.py`, chép
  NGUYÊN VĂN output + nhận xét khách quan vào research doc (append section
  mới "Bổ sung: daily-loss theo ngày + ngưỡng giữ lãi 1.0 điểm (vốn 30tr)"):
  - 100tr có đổi gì không sau fix (regression) — phải giữ nguyên +20.25%
    (không-EOD) và +18.22% (EOD giữ lãi ngưỡng 0.0).
  - 30tr không-EOD sau fix có bao nhiêu lệnh/PnL (trước: 1 lệnh, -2.05%).
  - 30tr EOD ngưỡng 1.0 vs 0.0: ngưỡng cao hơn cắt được bao nhiêu lệnh
    lãi nhỏ giữ qua đêm, PnL/ret đổi thế nào.
  - Ghi caveat: D+ rate/margin là hằng số chưa confirm với SSI; 1 sample 2
    tháng, chưa out-of-sample.

- [ ] **Bước 3:** KHÔNG tự chọn "khuyến nghị cuối" — số liệu khách quan, để
  Claude/user quyết (đánh đổi giữa số lệnh, lợi nhuận, chi phí qua đêm).

---

### Task 4: Regression toàn cục + báo cáo

- [ ] **Bước 1:** `uv run pytest -m "not integration" -v` — toàn bộ suite
  PASS (159 test hiện tại + test mới).
- [ ] **Bước 2:** `uv run ruff check trading tests` — sạch.
- [ ] **Bước 3:** `gitnexus_detect_changes()` — xác nhận phạm vi ĐÚNG các
  file đã liệt kê ở Global constraints.
- [ ] **Bước 4:** báo cáo lại cho Claude (planner): test pass/fail, `ruff
  check` output, `gitnexus_detect_changes()` output, bảng kết quả Task 3.
  **KHÔNG commit, KHÔNG push.**

---

## Ngoài phạm vi (KHÔNG làm trong plan này)

1. **Mô hình margin đầy đủ** trong `DerivativePaperBroker` (ký quỹ 17%,
   margin call, force-close khi equity < yêu cầu ký quỹ, D+ 3%/6%) — thay
   đổi ngữ nghĩa broker, cần spec + plan TDD riêng (đã flag từ plan
   2026-08-09). Plan này chỉ sửa CÁCH tính daily_pnl và thêm NGƯỠNG giữ lãi
   (tham số), không mô phỏng ký quỹ.
2. **Chi phí D+ trong engine** (tự trừ lãi qua đêm vào PnL) — hằng số chưa
   confirm; hiện chỉ dùng trong script tính toán để đề xuất ngưỡng.
3. **Hệ thống EMA 13/55 đa khung, partial TP/breakeven** — đã flag ngoài
   phạm vi từ plan 2026-08-09, giữ nguyên.
