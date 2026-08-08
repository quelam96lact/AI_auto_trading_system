# Plan: Risk halt (2% + 2 lệnh thua liên tiếp) + đóng vị thế cuối phiên cho derivative backtest

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development,
> task-by-task, checkbox tracking. **Run `gitnexus_impact`/`gitnexus_context` TRƯỚC
> khi sửa `DerivativeRiskManager.approve_open`/`_halt_check` và
> `run_derivative_backtest` (đều có caller thật — tests, CLI `main`,
> `tests/test_momentum_breakout_derivative_integration.py`). Run
> `gitnexus_detect_changes` trước khi báo cáo xong. KHÔNG commit, KHÔNG push —
> báo cáo lại cho Claude (planner) review.**

## Vì sao

Nguồn: file người dùng đưa (đã copy vào repo root,
`tổng hợp lại nội dung để tôi đưa vào xây dựng chiế.md`, tổng hợp Perplexity
về giao dịch HĐTL VN30 tại SSI) + đối chiếu hiện trạng repo.

Đối chiếu nhanh với hiện trạng:

| Đề xuất trong file | Hiện trạng repo | Kết luận |
|---|---|---|
| Rủi ro/ngày: dừng khi lỗ 2% vốn **HOẶC** 2 lệnh thua liên tiếp | `DerivativeRiskManager.max_daily_loss_pct=0.03`, không có rule chuỗi thua | **Điều chỉnh — plan này** |
| Không giữ lệnh qua đêm theo quán tính; xử lý vị thế trước 14:20 nếu không giữ | `run_derivative_backtest` không có force-close theo giờ; chiến lược tốt nhất hiện tại (Momentum lb=5+ATR) hold time median ~317 bar (~4-5 phiên) | **Điều chỉnh — plan này, backtest cả 2 phương án vì mâu thuẫn trực tiếp với hiệu năng hiện tại (xem Task 3)** |
| Phí ~7.250đ/lượt | Repo đã dùng 8.250đ/lượt (3.000 SSI + 2.700 HNX + 2.550 VSD, có nguồn) | Repo đã chi tiết/mới hơn — **không đổi** |
| Ký quỹ cơ sở 17%, vốn 1 HĐ ~32,3tr @1900đ, nên có đệm 1,25-1,5x | `max_contracts=1` đã ép cứng 1 hợp đồng; chưa có mô hình margin | **Không có code cần sửa** (giới hạn số HĐ đã đúng theo đề xuất); mô phỏng ký quỹ đầy đủ là thay đổi kiến trúc lớn — **ngoài phạm vi plan này, xem mục "Ngoài phạm vi"** |
| Hệ thống vào lệnh EMA 13/55 đa khung (H1/H4 xu hướng + M5/M15 vào lệnh + pullback + R:R 1,5:1 + partial TP 1R + breakeven stop) | Chưa có (chưa có EMA indicator, chỉ có `AtrCalculator`); `MomentumBreakoutStrategy` (Donchian breakout) đã có backtest thắng rõ SMA cross | Chiến lược mới, **chưa có bằng chứng backtest nào để so với Momentum Breakout đang thắng** — **ngoài phạm vi plan này, xem mục "Ngoài phạm vi"** |
| Thước đo: kỳ vọng/lệnh, theo dõi ≥50 lệnh, đổi 1 biến/lần | Đã là cách nghiên cứu hiện tại (`docs/superpowers/research/2026-08-08-derivative-strategy-params-summary.md`) | Không cần code — quy trình đã tuân thủ |

**Giả định đã chọn (nêu rõ để user/Hermes xác nhận nếu sai):** plan này CHỈ áp
2 điều chỉnh risk/exit có thể backtest-kiểm-chứng ngay lên **chiến lược đang
thắng** (`MomentumBreakoutStrategy`, tham số khuyến nghị `lookback=5,
atr_pct_threshold=0.001` từ research doc), KHÔNG build hệ thống EMA đa khung
mới và KHÔNG mô phỏng ký quỹ đầy đủ — hai việc đó lớn, chưa có bằng chứng, và
nên là plan riêng nếu user muốn.

## Global constraints

- **Chỉ sửa/thêm các file sau:** `trading/derivative_risk.py`,
  `trading/derivative_backtest.py`, `tests/test_derivative_risk.py`,
  `tests/test_derivative_backtest.py`, 1 script throwaway mới
  `scripts/.spike_risk_eod_derivative_strategies.py` (dot-prefixed, theo quy
  ước `scripts/.spike_improve_derivative_strategies.py` đã có), và **append**
  (không viết lại) vào 1 file research mới
  `docs/superpowers/research/2026-08-09-derivative-risk-eod-verification.md`.
- **KHÔNG đụng:** `trading/strategies/*` (momentum_breakout.py, sma_cross.py —
  không đổi tham số/logic strategy), `trading/derivative_position.py`
  (broker — không thêm margin model), `trading/engine/*`,
  `trading/collector/*`, `trading/paper_broker.py`, `trading/broker.py`, file
  cổ phiếu, và không đổi `docs/superpowers/research/2026-08-08-derivative-strategy-params-summary.md`
  đã có (chỉ tạo research doc mới, tránh conflict nội dung cũ).
- KHÔNG implement mô hình ký quỹ (margin call), KHÔNG implement partial
  TP/breakeven-stop, KHÔNG implement hệ thống EMA 13/55 đa khung — nằm ngoài
  phạm vi, xem mục "Ngoài phạm vi" cuối plan.
- KHÔNG đặt lệnh thật, không đụng `place_order`/`AsyncTrading`.
- Giữ nguyên default = hành vi cũ khi không truyền tham số mới (đúng convention
  đã dùng cho SL/TP ở plan `2026-08-08-derivative-stop-loss-engine.md`) —
  NGOẠI TRỪ `max_daily_loss_pct` đổi default 0.03→0.02 theo đúng con số file
  đề xuất (đây là điều chỉnh có chủ đích, không phải regression — Task 1 phải
  cập nhật test nào assert default cũ, nếu có).

---

### Task 1: `DerivativeRiskManager` — daily loss 2% + halt sau 2 lệnh thua liên tiếp

**Files:** `trading/derivative_risk.py`, `tests/test_derivative_risk.py`.

- [ ] **Bước 1 — đọc test hiện có:** `tests/test_derivative_risk.py` dùng
  `max_daily_loss_pct=0.03` tường minh trong hầu hết test (không phụ thuộc
  default) — xác nhận đổi default không phá test cũ trước khi sửa. Nếu có
  test nào dựa vào default 0.03 không tường minh, cập nhật giá trị ngưỡng
  trong chính test đó (KHÔNG đổi hành vi test, chỉ đổi số cho khớp default
  mới).

- [ ] **Bước 2 — viết test trước:**
  - `test_default_max_daily_loss_pct_is_2_percent`: `DerivativeRiskManager(capital=100_000_000)` → assert field `max_daily_loss_pct == 0.02`.
  - `test_approve_open_blocks_after_two_consecutive_losing_trades`: tạo risk
    (`max_consecutive_losses=2` mặc định), gọi
    `risk.record_trade_result(pnl=-100_000, today=D)` 1 lần → `approve_open(...)`
    vẫn `True` (mới 1 lệnh thua). Gọi `record_trade_result(pnl=-50_000, today=D)`
    lần 2 → `approve_open(...)` phải `False`, `risk.halted_date == D`.
  - `test_consecutive_loss_streak_resets_on_winning_trade`: thua, thắng, thua
    (`record_trade_result` lần lượt -1, +1, -1 cùng ngày) → `approve_open`
    vẫn `True` (streak chỉ còn 1 sau lệnh thắng reset).
  - `test_consecutive_loss_streak_resets_next_day`: 2 lệnh thua ngày D1 → halt
    D1; sang D2 gọi `approve_open(..., today=D2)` → phải `True` (streak reset
    theo ngày, độc lập với `halted_date` logic đã có).
  Chạy 4 test → FAIL (`record_trade_result` chưa tồn tại → AttributeError,
  default test → assertion fail).

- [ ] **Bước 3 — implement:** đổi `max_daily_loss_pct: float = 0.02` (từ
  0.03). Thêm field `max_consecutive_losses: int = 2`, state nội bộ
  `_consecutive_losses: int = field(default=0, init=False, repr=False)` và
  `_streak_date: date | None = field(default=None, init=False, repr=False)`.
  Thêm method `record_trade_result(self, pnl: float, today: date) -> None`:
  nếu `today != self._streak_date`, reset `_consecutive_losses = 0` và
  `_streak_date = today`; nếu `pnl < 0`, `_consecutive_losses += 1`, ngược
  lại (`pnl >= 0`) reset về 0. Trong `_halt_check`, thêm điều kiện halt khi
  `self._consecutive_losses >= self.max_consecutive_losses` (cùng cơ chế set
  `halted_date` như nhánh daily-loss hiện có).

- [ ] **Bước 4:** chạy lại 4 test Bước 2 → PASS. Chạy toàn bộ
  `uv run pytest tests/test_derivative_risk.py -v` → PASS hết (bao gồm test
  cũ không đổi hành vi ngoài default).

---

### Task 2: Wire `record_trade_result` vào `run_derivative_backtest`

**Files:** `trading/derivative_backtest.py`, `tests/test_derivative_backtest.py`.

- [ ] **Bước 1 — viết test trước** (vd
  `test_two_consecutive_losing_trades_halt_third_open_same_day`): dựng chuỗi
  giá qua `compute_crossover()` XÁC NHẬN thật (kỹ thuật đã dùng trong file
  test này) tạo 2 lệnh mở/đóng liên tiếp đều lỗ, rồi 1 tín hiệu mở thứ 3 cùng
  ngày → assert lệnh mở thứ 3 KHÔNG được fill (bị risk chặn bởi
  consecutive-loss, không phải bởi daily-loss-pct — chọn PnL lỗ đủ nhỏ để
  không chạm ngưỡng 2% vốn, chứng minh đúng nhánh chặn). Chạy → FAIL (vì
  `record_trade_result` chưa được gọi trong `run_derivative_backtest`, lệnh 3
  vẫn fill được).

- [ ] **Bước 2 — implement:** sau mỗi `broker.close(...)` (cả nhánh SL/TP
  hiện có lẫn nhánh crossover-close hiện có), gọi
  `risk.record_trade_result(fill.pnl, bar.ts.date())` ngay sau khi append
  fill vào `all_fills` (fill.pnl luôn có giá trị vì đây là fill đóng vị thế).

- [ ] **Bước 3:** chạy lại test Bước 1 → PASS. Chạy
  `uv run pytest tests/test_derivative_backtest.py -v` → toàn bộ PASS (test
  cũ không truyền risk có `max_consecutive_losses` khác 2 → không đổi hành
  vi vì các test cũ không có 2 lệnh thua liên tiếp trong kịch bản của
  chúng — xác minh lại bằng cách chạy, không giả định).

---

### Task 3: Đóng vị thế bắt buộc trước giờ cắt (mặc định TẮT — regression)

**Files:** `trading/derivative_backtest.py`, `tests/test_derivative_backtest.py`.

- [ ] **Bước 1 — viết test trước:**
  - `test_intraday_close_time_none_default_keeps_position_open_past_1420`
    (regression): bars kéo dài qua 14:20 với vị thế đang mở, không truyền
    `intraday_close_time` → vị thế vẫn mở cuối chuỗi bar (không có fill đóng
    ngoài ý strategy), y hệt hành vi hiện tại.
  - `test_intraday_close_time_force_closes_open_position_at_cutoff`: truyền
    `intraday_close_time=time(14, 20)`, dựng vị thế mở trước 14:20, bar tiếp
    theo có `ts.time() >= time(14, 20)` → assert có đúng 1 fill đóng thêm tại
    giá `bar.close` của bar cắt đó, và không có lệnh mở mới cùng bar dù có
    crossover ngược chiều đúng lúc đó (giống rule "không mở lại cùng bar" đã
    có ở SL/TP).
  - `test_intraday_close_time_does_not_fire_when_already_flat`: không có vị
    thế mở tại/sau giờ cắt → không phát sinh fill thừa.
  Chạy 3 test → FAIL (`intraday_close_time` chưa tồn tại → TypeError).

- [ ] **Bước 2 — implement:** thêm param
  `intraday_close_time: time | None = None` vào `run_derivative_backtest`
  (import `time` từ `datetime`, dùng `trading.calendar_vn.TZ` để lấy giờ địa
  phương từ `bar.ts` giống cách `calendar_vn.py` làm — convert
  `bar.ts.astimezone(TZ).time()`). Đặt nhánh kiểm tra NGAY SAU nhánh SL/TP
  hiện có (nếu SL/TP đã đóng vị thế ở bar này thì bỏ qua nhánh EOD — dùng lại
  `continue` đã có), TRƯỚC logic crossover: nếu `net != 0` và
  `intraday_close_time is not None` và
  `bar.ts.astimezone(TZ).time() >= intraday_close_time`, đóng bằng
  `broker.close(bar.symbol, bar.close, bar.ts)`, gọi
  `risk.record_trade_result(...)` (Task 2), append fill + equity, `continue`
  bỏ qua crossover cùng bar.

- [ ] **Bước 3:** chạy lại 3 test Bước 1 → PASS. Chạy
  `uv run pytest tests/test_derivative_backtest.py -v` → toàn bộ PASS (bao
  gồm test cũ không truyền `intraday_close_time` → mặc định `None` giữ
  nguyên hành vi).

---

### Task 4: Backtest kiểm chứng trên dữ liệu thật + ghi nhận kết quả

**Files:** `scripts/.spike_risk_eod_derivative_strategies.py` (mới, throwaway,
dot-prefixed), `docs/superpowers/research/2026-08-09-derivative-risk-eod-verification.md` (mới).

- [ ] **Bước 1:** viết script throwaway (theo mẫu
  `scripts/.spike_improve_derivative_strategies.py`, load
  `scripts/.spike_derivative_ohlc_5m_2m_sample.json`, cùng vốn 100,000,000,
  fee 8,250, entry cố định `MomentumBreakoutStrategy(qty=1, lookback=5,
  volume_multiplier=2.0, volume_period=20, atr_pct_threshold=0.001)` — tham
  số khuyến nghị đã kiểm chứng trong research doc 2026-08-08, KHÔNG đổi), so
  sánh tối thiểu 4 cấu hình risk/exit:
  1. Baseline (risk cũ 3%, không consecutive-loss halt, không EOD close) — để
     đối chiếu ngược với số đã có trong research doc 2026-08-08 (phải khớp
     +20.25%, MaxDD 2.9%, 17 lệnh — nếu không khớp, DỪNG và báo cáo sai lệch
     trước khi đi tiếp).
  2. Risk mới (2% + 2-loss halt), không EOD close.
  3. Risk cũ, có EOD close `time(14, 20)`.
  4. Risk mới + EOD close `time(14, 20)`.
  In ra: số lệnh, win rate, PnL, return %, MaxDD cho cả 4 cấu hình.

- [ ] **Bước 2:** chạy
  `PYTHONPATH=. uv run python scripts/.spike_risk_eod_derivative_strategies.py`,
  chép NGUYÊN VĂN output vào file research doc mới, kèm nhận xét khách quan
  (KHÔNG tô hồng): cấu hình nào PnL/MaxDD tốt hơn baseline, cấu hình nào tệ
  hơn, và đặc biệt nêu rõ nếu EOD close làm giảm PnL đáng kể (vì chiến lược
  đang thắng có hold time trung vị ~317 bar — ép đóng cuối phiên nhiều khả
  năng cắt đứt các lệnh thắng lớn đang chạy, đúng lo ngại đã nêu ở "Vì sao").
  Ghi rõ caveat: 1 sample 2 tháng, chưa out-of-sample.

- [ ] **Bước 3:** không tự ý chọn cấu hình "khuyến nghị cuối cùng" thay
  research doc 2026-08-08 nếu EOD close làm giảm hiệu năng — chỉ trình bày số
  liệu khách quan, để Claude/user quyết định đánh đổi (an toàn vốn theo quy
  tắc D+ vs. giữ lợi nhuận) ở bước review.

---

### Task 5: Regression toàn cục + báo cáo

- [ ] **Bước 1:** `uv run pytest -m "not integration" -v` — toàn bộ suite
  PASS (gồm `tests/test_momentum_breakout_derivative_integration.py` gọi
  `run_derivative_backtest()` gián tiếp, không truyền `intraday_close_time`
  → không đổi hành vi; risk mặc định đổi 3%→2% — xác nhận test đó có phụ
  thuộc số này không, nếu FAIL vì lý do này thì sửa số trong đúng test đó).
- [ ] **Bước 2:** `uv run ruff check trading tests` — sạch.
- [ ] **Bước 3:** `gitnexus_detect_changes()` — xác nhận phạm vi ĐÚNG các
  file đã liệt kê ở Global constraints, không lan ra file khác.
- [ ] **Bước 4:** báo cáo lại cho Claude (planner): test pass/fail, `ruff
  check` output, `gitnexus_detect_changes()` output, bảng kết quả Task 4.
  **KHÔNG commit, KHÔNG push.**

---

## Ngoài phạm vi (đề xuất trong file nhưng KHÔNG làm trong plan này)

Nêu rõ để user quyết định có giao plan riêng hay không:

1. **Mô phỏng ký quỹ thật (margin model)** trong `DerivativePaperBroker` theo
   công thức 17% (`Giá VN30F × 100,000 × 17% × số HĐ`) — hiện broker cố tình
   không khoá vốn theo margin (quyết định đã ghi trong code). File cung cấp
   công thức margin công khai nên quyết định "chưa có số thật" có thể không
   còn đúng — nhưng đây là thay đổi ngữ nghĩa broker, cần spec + plan TDD
   riêng, không nhét vào plan risk/exit này.
2. **Hệ thống vào lệnh EMA 13/55 đa khung** (H1/H4 xu hướng, M5/M15 pullback,
   R:R 1,5:1, partial TP tại 1R + breakeven stop) — chiến lược hoàn toàn mới,
   chưa có `EmaCalculator`, chưa có bằng chứng backtest nào để so sánh với
   `MomentumBreakoutStrategy` đang thắng. Cần: (a) thêm EMA indicator, (b)
   dùng `trading.resample.resample_bars()` có sẵn để tạo H1 (60')/H4 (240'),
   (c) backtest so sánh trực tiếp với Momentum Breakout trên cùng sample
   trước khi quyết định thay thế hay chỉ dùng tham khảo.
3. **Đệm vốn 1,25–1,5× margin / quy tắc tăng số HĐ sau 50-100 lệnh ổn định**
   — không cần code (quyết định phân bổ vốn của người dùng, `max_contracts=1`
   đã ép cứng đúng theo đề xuất "chỉ 1 HĐ" của file).
