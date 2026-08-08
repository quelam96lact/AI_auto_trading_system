# Momentum Breakout Strategy (VN30F1M) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:test-driven-development
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Before editing
> anything, run `gitnexus_context`/`gitnexus_impact` per CLAUDE.md; run
> `gitnexus_detect_changes` before reporting done. Do NOT commit, do NOT push —
> report back and stop.**

## Nguồn & rationale

Nguồn: video YouTube "Growing a $2k Account to $65,662.04 in 30 Days" (Ross
Cameron / Warrior Trading) — chiến lược momentum scalping cổ phiếu nhỏ vốn
hoá Mỹ. Các quy tắc cốt lõi đã xác nhận qua warriortrading.com +
myoptionsjournal.com:

- Scanner: float thấp, volume ≥ 5× trung bình, gap ≥ 2%.
- Entry: **bull flag** — breakout khỏi đỉnh vùng pullback, xác nhận bằng
  volume.
- R:R tối thiểu 2:1, cắt lỗ nhanh, không average-down.
- Có short các setup yếu tương tự (bear flag/breakdown).

**Quyết định adapt cho hệ thống này** (đã chốt qua brainstorm với user
2026-08-08, xem `[[golive-prep-status-2026-08-01]]`-style ghi chú): áp dụng
cho **phái sinh VN30F1M** (`41I1G8000`), KHÔNG áp dụng cho cổ phiếu — vì cổ
phiếu VN settlement T+2.5, không short được, không round-trip trong ngày;
phái sinh T+0 + long/short đã có sẵn hạ tầng paper-trading từ
`docs/superpowers/plans/2026-08-08-derivative-paper-trading-phase1.md`.

Vì hợp đồng phái sinh chỉ có 1 instrument (không phải scan hàng trăm mã), bộ
quy tắc dịch sang:

| Quy tắc gốc (Ross Cameron) | Dịch cho VN30F1M |
|---|---|
| Scanner volume ≥ 5× avg | Volume bar hiện tại ≥ `volume_multiplier`× volume trung bình `volume_period` bar gần nhất |
| Bull flag: breakout đỉnh vùng pullback | Đóng cửa > kênh giá cao nhất (Donchian high) của `lookback` bar trước đó |
| Bear flag/breakdown (short) | Đóng cửa < kênh giá thấp nhất (Donchian low) của `lookback` bar trước đó |
| Tránh thị trường đi ngang | ATR% filter tuỳ chọn (tái dùng `AtrCalculator`, cùng cơ chế `SmaCrossStrategy` đã có) |

**Ngoài phạm vi, để lại phase sau** (không đoán, không scope creep):
- R:R cố định 2:1 / profit target / quarter-size cushion / scale-in khi
  thắng — đòi hỏi sửa vòng lặp khớp lệnh intrabar (`run_derivative_backtest`
  hiện chỉ thoát theo crossover ngược chiều), ngoài phạm vi 1 module strategy
  mới.
- Không sửa `run_derivative_backtest()` — strategy mới chỉ cần khớp đúng
  interface hiện có (`compute_crossover(bar) -> "bull"|"bear"|None` +
  `.qty`) để cắm thẳng vào, không cần đổi backtest loop.
- Không có số volume_multiplier/lookback "đúng" nào được verify bằng dữ liệu
  thật VN30F1M — đây là tham số có default hợp lý (ghi rõ trong docstring là
  chưa tune bằng dữ liệu thật), không phải số đã kiểm chứng.

## Global constraints

- **Chỉ tạo file mới:** `trading/strategies/momentum_breakout.py`,
  `tests/test_momentum_breakout_strategy.py`. Không sửa bất kỳ file nào
  khác — đặc biệt: `trading/strategies/sma_cross.py`,
  `trading/derivative_backtest.py`, `trading/derivative_position.py`,
  `trading/derivative_risk.py`, `trading/indicators.py`,
  `trading/engine/*`, `trading/collector/*`, mọi file cổ phiếu.
- Không đặt lệnh thật — module này chỉ tính tín hiệu (giống
  `SmaCrossStrategy.compute_crossover`), không tự gọi broker/order API nào.
- Tái sử dụng `AtrCalculator` từ `trading/indicators.py` (import, không sửa).
- `qty` mặc định `1` (lot_size phái sinh, khớp `SmaCrossStrategy(qty=1)`
  dùng cho VN30F1M trong `derivative_backtest.py`).

---

### Task 1: `MomentumBreakoutStrategy`

**Files:** create `trading/strategies/momentum_breakout.py`,
`tests/test_momentum_breakout_strategy.py`.

**Interface (phải khớp chính xác để duck-type vào `run_derivative_backtest`
mà không cần sửa nó):**

```python
class MomentumBreakoutStrategy:
    def __init__(
        self,
        qty: int = 1,
        lookback: int = 10,
        volume_multiplier: float = 2.0,
        volume_period: int = 20,
        atr_period: int = 14,
        atr_pct_threshold: float = 0.0,  # 0.0 = tắt filter (mặc định, chưa có số đã verify)
    ): ...

    def compute_crossover(self, bar: Bar) -> Literal["bull", "bear"] | None:
        """Side-effect: cập nhật state nội bộ (kênh giá, volume trung bình,
        ATR) — CHỈ được gọi đúng 1 lần/bar/symbol, cùng contract với
        SmaCrossStrategy.compute_crossover(). KHÔNG tự gate theo vị thế đang
        giữ (tách biệt phát hiện tín hiệu khỏi quyết định mở/đóng, giống
        SmaCrossStrategy)."""

    def last_crossover(self, symbol: str) -> Literal["bull", "bear"] | None: ...
    def last_atr(self, symbol: str) -> float | None: ...
```

**Thuật toán `compute_crossover(bar)`:**

1. `atr = self._atr.update(bar)` (luôn gọi mỗi bar, kể cả lúc warm-up —
   cùng lý do `SmaCrossStrategy` đã document).
2. Lấy 2 deque per-symbol, `maxlen=lookback` cho (high, low), và 1 deque
   `maxlen=volume_period` cho volume — **tất cả đều chứa các bar TRƯỚC bar
   hiện tại** (chưa append bar hiện tại vào lúc tính toán ở bước 3).
3. Nếu chưa đủ dữ liệu (`len(highs) < lookback` hoặc `len(volumes) <
   volume_period`) → `crossover = None`, vẫn phải append bar hiện tại vào
   cả 3 deque trước khi return (để warm-up tiến triển đúng), rồi return
   `None`.
4. `channel_high = max(highs)`, `channel_low = min(lows)`,
   `avg_volume = sum(volumes) / len(volumes)`.
5. `volume_spike = avg_volume > 0 and bar.volume >= volume_multiplier * avg_volume`.
6. `candidate = "bull"` nếu `bar.close > channel_high and volume_spike`;
   `candidate = "bear"` nếu `bar.close < channel_low and volume_spike`;
   ngược lại `None`. (Không thể vừa bull vừa bear cùng lúc vì channel_high ≥
   channel_low.)
7. Filter ATR% (chỉ áp dụng nếu `atr_pct_threshold > 0`, giữ tinh thần "tắt
   mặc định vì chưa verify số"): nếu `candidate is not None` và
   (`atr is None` hoặc `bar.close <= 0` hoặc `atr / bar.close <
   atr_pct_threshold`) → `candidate = None`. Guard `bar.close <= 0` bắt
   buộc phải có dù filter tắt hay bật, để tránh `ZeroDivisionError` khi bar
   dị dạng (đã có tiền lệ bug thật trong repo này — xem
   `[[golive-prep-status-2026-08-01]]`).
8. Append `bar.high`/`bar.low`/`bar.volume` vào 3 deque (SAU khi đã tính
   channel/avg_volume ở bước 4, để bar hiện tại không tự tham chiếu chính
   nó).
9. Lưu `self._last_crossover[bar.symbol] = candidate`,
   `self._last_atr[bar.symbol] = atr`, return `candidate`.

**Test cases** (`tests/test_momentum_breakout_strategy.py`, dùng
`lookback=3, volume_period=3, volume_multiplier=2.0, atr_pct_threshold=0.0`
để chuỗi test ngắn gọn, dựng bar tổng hợp qua helper giống pattern
`bars_from_prices` đã có trong `tests/test_derivative_backtest.py` nhưng
cần volume tuỳ chỉnh từng bar — viết helper riêng nhận `list[tuple[high,
low, close, volume]]`):

1. `test_no_signal_during_warmup` — 3 bar đầu (chưa đủ `lookback=3` bar
   trước đó) → `compute_crossover` trả `None` cho cả 3.
2. `test_bull_breakout_with_volume_spike` — 3 bar warm-up giá đi ngang
   (close=10, high=10.5, low=9.5, volume=100), bar thứ 4: close=11
   (> channel_high=10.5), volume=250 (≥ 2×100) → trả `"bull"`.
3. `test_no_signal_breakout_without_volume_spike` — giống bar thứ 4 ở trên
   nhưng volume=150 (< 2×100) → trả `None` (breakout giá đúng nhưng thiếu
   volume).
4. `test_bear_breakdown_with_volume_spike` — 3 bar warm-up đi ngang, bar
   thứ 4: close=9 (< channel_low=9.5), volume=250 → trả `"bear"`.
5. `test_no_signal_close_inside_channel` — bar thứ 4: close=10.2 (trong
   khoảng [9.5, 10.5]), volume=250 → trả `None` dù volume đủ.
6. `test_atr_filter_blocks_signal_when_enabled` — dựng strategy với
   `atr_pct_threshold=0.5` (cao bất thường có chủ đích để chắc chắn chặn),
   cùng chuỗi bull breakout ở test 2 → trả `None` (bị ATR filter chặn).
7. `test_last_crossover_and_last_atr_reflect_last_call` — sau 1 lần gọi
   `compute_crossover` có tín hiệu bull, `last_crossover(symbol) ==
   "bull"` và `last_atr(symbol)` không phải `None`.
8. `test_zero_close_does_not_crash` — bar warm-up bình thường rồi 1 bar có
   `close=0.0` (bất kể high/low/volume) → không raise exception, trả
   `None`.

**Definition of done cho Task 1:**
- [ ] `uv run pytest tests/test_momentum_breakout_strategy.py -v` — tất cả
      PASS.

---

### Task 2: Integration test — cắm vào `run_derivative_backtest` không sửa gì

**Files:** create `tests/test_momentum_breakout_derivative_integration.py`
(test-only, KHÔNG sửa `trading/derivative_backtest.py`).

Mục đích: chứng minh `MomentumBreakoutStrategy` khớp interface duck-typed
mà `run_derivative_backtest()` cần (`compute_crossover` + `.qty`), y hệt
cách `SmaCrossStrategy` đã dùng, mà không cần đổi type hint hay code của
`derivative_backtest.py`.

```python
from trading.derivative_backtest import DERIVATIVE_SYMBOL, run_derivative_backtest
from trading.derivative_risk import DerivativeRiskManager
from trading.strategies.momentum_breakout import MomentumBreakoutStrategy
# ... dựng 1 chuỗi Bar tổng hợp (dùng DERIVATIVE_SYMBOL) đủ dài để tạo ít
# nhất 1 bull breakout + 1 bear breakdown sau đó (tự chọn giá/volume rõ ràng
# tạo được tín hiệu theo đúng thuật toán Task 1 — verify bằng cách chạy thử
# compute_crossover() trực tiếp trước khi viết assert, giống cách
# test_derivative_backtest.py đã ghi chú "da xac nhan that" cho chuoi gia).

def test_momentum_breakout_plugs_into_derivative_backtest_without_changes():
    strategy = MomentumBreakoutStrategy(qty=1, lookback=3, volume_period=3,
                                         volume_multiplier=2.0)
    risk = DerivativeRiskManager(capital=100_000_000, max_contracts=1)
    report = run_derivative_backtest(bars, strategy, risk, 100_000_000)
    assert report.trades >= 1  # it nhat 1 round-trip xay ra
```

**Definition of done cho Task 2:**
- [ ] `uv run pytest tests/test_momentum_breakout_derivative_integration.py -v`
      — PASS.
- [ ] `git diff --stat -- trading/derivative_backtest.py trading/derivative_position.py trading/derivative_risk.py trading/strategies/sma_cross.py`
      — output rỗng (không file nào trong nhóm này bị đổi).

---

### Task 3: Full-suite verification + report

- [ ] `uv run pytest -m "not integration" -v` — toàn bộ suite PASS (không
      chỉ 2 file mới).
- [ ] `uv run ruff check trading tests` — sạch, không finding mới.
- [ ] Chạy `gitnexus_detect_changes()` — xác nhận symbol thay đổi chỉ giới
      hạn ở `trading/strategies/momentum_breakout.py` và 2 file test mới.
- [ ] Báo cáo lại: số test pass/fail, output `ruff check`, output
      `gitnexus_detect_changes()`, và xác nhận không file nào ngoài phạm vi
      bị đụng vào. **Không commit, không push** — dừng ở đây để Claude
      review.
