# Đợt 8 — OctopusCombo vào sổ đăng ký `STRATEGIES`: Báo cáo audit

**Người audit:** Claude · **Ngày:** 2026-09-06 · **Brief:**
`2026-09-06-brief-dot-8-octopus-combo-vao-so-dang-ky.md`

## Kết luận

Đạt cả 7 tiêu chí. Đã tự tay tái lập độc lập (không tin số agent dán), tự tay
phá hoại cả 4 điều kiện phân biệt (không tin output đỏ agent dán) — mọi thứ
khớp. Commit.

## 1. Đối chiếu code với đặc tả brief

`trading/strategies/octopus_combo.py` — `OctopusComboStrategy` implement đúng
4 tầng đặc tả §2.1 của brief, đúng thứ tự: (1) thanh khoản 2 tỷ/20 ngày đã đóng
qua `DailyLiquidityTracker` **import lại**, không viết tay; (2)
`close>EMA200 và close>MA20`; (3) nến xanh + `EMA9>EMA21` (so sánh **mức**,
không phải cắt lên — đúng khác biệt cốt lõi §2.1 brief) + `MACD hist>0`; (4)
≥2 nến đỏ trong 5 phiên trước. `warmup_bars=201` khớp công thức brief.
`atr_period=14` (khác ATR(5) của `pattern_backtest.py`, đúng lý do brief nêu:
đồng bộ quy ước sizing/trailing của `run_backtest`).

`trading/backtest.py` — diff đúng **2 dòng** (1 import + 1 entry dict), tự
`git diff` xác nhận, không chạm `_TF_SPEC`, `run_backtest`, hay bất cứ gì khác.

## 2. Tự tay phá hoại 4 điều kiện — không tin output đỏ agent dán

Restore từ backup trước, sabotage từng điều kiện một, chạy `pytest
tests/test_octopus_combo.py`, chụp lại, khôi phục, lặp lại cho điều kiện kế:

| Sabotage | Test đỏ | Kết quả |
|---|---|---|
| Bỏ check thanh khoản | `test_fails_when_liquidity_below_2_billion` | `assert False` |
| Bỏ vế `close<=MA20` khỏi điều kiện xu hướng | `test_diff_1_fails_when_below_ma20` | `assert 'bull' is None` |
| Bỏ vế `close>open` khỏi điều kiện nến | `test_diff_2_fails_when_current_bar_is_red` | `assert 'bull' is None` |
| Đổi so sánh mức `EMA9>EMA21` thành crossover thật (`prev_fast<=prev_slow`) | `test_diff_3_bull_on_level_without_crossover` | `assert None == 'bull'` |

Khôi phục nguyên bản, `grep -rn "SABOTAGE" trading tests scripts` rỗng,
`pytest -m "not integration" -q` → 473 passed, `ruff check` sạch.

## 3. Tự chạy lại hai script đo — không tin bảng agent dán

### Cổng cứng (`measure_octopus_matched_basket.py`)

```
Tổng số lệnh (SELL fills)        |                1,514 |                 1,514 |                  1,514
PnL Chiến lược Octopus (VND)     |       -1,615,319,902 |        -1,615,319,902 |         -1,615,319,902
```

Khớp tuyệt đối với baseline đã ghim từ gói Q — `octopus_combo` không làm trôi.

### Đo trung thực qua `run_backtest` (`measure_octopus_combo_matched_basket.py`, mới)

Chạy độc lập trên đủ 1.308 mã, kỳ 2016-01-04 → 2026-08-13, vốn 1 tỷ/mã:

| | Octopus Baseline | Octopus Combo |
|---|---:|---:|
| Mã sinh lệnh | 439 | 653 |
| Tổng lệnh | 1.514 | **11.316** |
| PnL chiến lược | −1.615.319.902 | **−9.826.136.733** |

Khớp tuyệt đối với số agent báo cáo, tự tái lập lần thứ hai độc lập.

**Kết luận về bản chất, xác nhận đúng suy luận của agent:** khi tách phần tín
hiệu ra khỏi cơ chế BUY STOP + SL/TP cố định của `pattern_backtest.py` và chạy
qua mô hình khớp market + trailing-stop của `run_backtest`, chiến lược sinh
gấp ~7,5 lần số lệnh (do `EMA9>EMA21` là so sánh mức, lỏng hơn nhiều so với
yêu cầu cắt lên của octopus gốc) và lỗ nặng hơn octopus gốc. **Điều này chứng
minh bằng thực nghiệm — không chỉ bằng lập luận — rằng lợi nhuận dương được
quảng cáo trong các báo cáo hybrid phụ thuộc hoàn toàn vào cơ chế khớp lệnh
BUY STOP/SL/TP cố định, không phải vào bản thân bộ lọc tín hiệu.** Đây là
bằng chứng mạnh hơn nhiều so với suy luận đã ghi trong phụ lục audit hybrid
(`2026-09-06-tong-hop-ban-giao-claude-audit.md`, §3b).

## 4. Không đụng thứ bị cấm

`git diff --stat` cho `trading/engine/main.py`, `tests/test_strategy_conformance.py`,
`config/config.yaml`, `trading/paper_broker.py`, `trading/pattern_backtest.py`,
`trading/strategies/octopus_pullback.py` — **rỗng**. `real_trading_enabled: false`
nguyên vẹn. `test_default_strategy_la_octopus` vẫn xanh — `_default_strategy()`
vẫn ghim `OctopusPullbackStrategy`, chạy thật không đổi.

## 5. Ý nghĩa cho việc go-live

Không. `octopus_combo` lỗ nặng hơn cả octopus gốc khi đo trung thực qua
`run_backtest` (−9,8 tỷ so với −1,6 tỷ). Việc đăng ký vào `STRATEGIES` chỉ có
nghĩa "có sẵn để đo, tự động được conformance test phủ" — đúng bản chất sổ
đăng ký đã ghi ở `backtest.py:286-289`. Không có căn cứ nào ở đây để bật chạy
thật bất cứ biến thể nào của octopus_combo hay hybrid.
