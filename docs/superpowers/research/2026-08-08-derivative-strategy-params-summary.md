# Tổng hợp thông số chiến lược giao dịch phái sinh (VN30F1M)

> **Nguồn:** backtest so sánh + nghiên cứu cải thiện trên dữ liệu THẬT
> `scripts/.spike_derivative_ohlc_5m_2m_sample.json` (1493 bars 5m,
> 2026-06-19 → 2026-08-07, giá 1796.3–2022.8).
> **Cảnh báo:** mọi con số là kết quả trên 1 sample duy nhất, chưa có
> slippage, chưa out-of-sample / walk-forward — dùng để chọn hướng, KHÔNG
> phải khẳng định lợi nhuận production.
>
> **Ghi chú cập nhật fee (sau commit 31abd04):** tài liệu gốc ghi fee
> 2,700đ — SAI. Xác minh lại sau khi `git pull`: mọi con số trong tài liệu
> này đã được tính với `DERIVATIVE_FEE_PER_CONTRACT = 8,250đ/HĐ/lượt`
> (commit 31abd04 nằm sẵn trong working tree trước khi các backtest được
> chạy; kiểm tra fill thực: lệnh đầu `(1959.1-1965.1)*100,000-8,250 =
> -608,250` — với fee 2,700 sẽ ra -602,700). Kết quả chạy lại SAU pull
> **không đổi** (E1–E4 giống hệt), nên mọi kết luận bên dưới đứng nguyên —
> chỉ sửa phần mô tả fee cho đúng.

## 1. Bối cảnh chung (áp dụng cho cả 2 chiến lược)

| Thông số | Giá trị | Ghi chú |
|---|---|---|
| Instrument | VN30F1M (`41I1G8000`) | HNX, front-month, T+0 long/short |
| Khung bar | 5 phút | |
| Vốn khởi tạo | 100,000,000 VND | |
| Qty / lệnh | 1 hợp đồng | lot_size phái sinh = 1 |
| Phí | 8,250 VND/hợp đồng/lượt | Biểu phí SSI công khai (hiệu lực 10/10/2025): 3,000 phí dịch vụ SSI + 2,700 phí trả HNX + 2,550 phí bù trừ VSD (ước tính bậc <100 HĐ/ngày; cơ chế VSD theo lượt/ngày chưa xác nhận rõ — tạm gộp theo lượt) |
| Hệ số nhân điểm | 100,000 VND/điểm | Đặc tả hợp đồng công khai HNX (đã fix) |
| Risk manager | max_contracts=1, max_daily_loss_pct=3% | Không halt xảy ra trong 2 tháng này |
| Engine | `run_derivative_backtest()` | Mở/đóng theo crossover, không TP/SL |

## 2. Chiến lược khuyến nghị: Momentum Breakout (đã thắng rõ ràng)

### 2a. Thông số ENTRY (khuyến nghị — áp dụng được NGAY, chỉ đổi constructor)

| Tham số | Khuyến nghị | Default hiện tại | Kết quả (sample 2 tháng) |
|---|---|---|---|
| `lookback` | **5** | 10 | lb=5: 25 lệnh, 52.0% win, +17.08%, MaxDD 4.0% |
| `volume_multiplier` | **2.0** | 2.0 | 2.0 là điểm ngọt robust; 1.5 quá nhiều lệnh nhiễu, 3.0 quá ít lệnh (rủi ro variance) |
| `volume_period` | **20** | 20 | 20 ổn định nhất qua mọi lookback |
| `atr_pct_threshold` | **0.0005 – 0.001** | 0.0 (tắt) | 0.001: 14 lệnh, 57.1% win, +15.02%, MaxDD 4.8% — ít lệnh hơn, win rate cao hơn, MaxDD thấp hơn |

**Cấu hình khuyến nghị (entry):**
```python
MomentumBreakoutStrategy(
    qty=1,
    lookback=5,
    volume_multiplier=2.0,
    volume_period=20,
    atr_pct_threshold=0.001,  # hoặc 0.0005 nếu muốn nhiều lệnh hơn
)
```
→ 25 lệnh, win 52.0%, PnL +16,963,750 (+17.08%), MaxDD 4.0% (sample).

**Cập nhật sau khi engine có SL/TP thật (chạy lại với fee 8,250):** kết hợp
`lookback=5` + `atr_pct_threshold=0.001` tốt hơn nữa — **17 lệnh, win 58.8%,
PnL +20,069,750 (+20.25%), MaxDD chỉ 2.9%** (ATR filter cắt breakout giả ở
chu kỳ nhanh). Đây là cấu hình entry khuyến nghị CUỐI CÙNG.

**Phương án thay thế đáng cân nhắc:**
- `lookback=15, vmult=2.0, vper=20`: 16 lệnh, 50.0%, +17.10%, MaxDD 4.8% — ít lệnh
  hơn, PnL tương đương (nếu muốn ít giao dịch hơn).
- ATR filter 0.0005 giữ 20 lệnh, +15.33%, MaxDD 4.8% — cân bằng giữa số lệnh và win rate.

### 2b. Thông số EXIT (nghiên cứu — CHƯA implement trong engine, cần code mới)

Thí nghiệm sim (fill tại đúng mức TP/SL trên bar high/low — LẠC QUAN, cần verify
bằng engine thật với xử lý gap như trailing stop):

| Cấu hình | Lệnh | Win% | PnL | Ret | Nhận xét |
|---|---|---|---|---|---|
| Không exit (engine hiện tại) | 21 | 47.6% | 14,556,750 | +14.71% | Baseline |
| **SL=5 điểm, không TP** | 28 | 35.7% | 18,699,000 | **+18.79%** | **Tốt nhất** — cắt lỗ sớm, giữ nguyên upside |
| SL=8, không TP | 24 | 41.7% | 17,692,000 | +17.82% | Gần tương đương |
| SL=3, không TP | 33 | 27.3% | 17,027,750 | +17.47% | Nhiều lệnh hơn, lỗ cắt sớm hơn |
| TP=8 + SL=8 | 50 | 64.0% | 11,247,500 | +10.84% | Win cao nhưng chặn đuôi lãi |
| TP=3, không SL | 20 | 65.0% | -3,495,000 | **-3.66%** | TP quá chặt PHÁ HỦY chiến lược |

**Kết luận exit:**
- Chỉ nên thêm **stop-loss ~5 điểm** (không take-profit, hoặc TP rất rộng).
- TP chặt (3 điểm) cắt mất đuôi lãi — chiến lược này kiếm tiền từ vài lệnh lớn.
- Lưu ý: SL=5 tương ứng lỗ round-trip -500,000 - 16,500 = -516,500 VND/lệnh
  (≈0.52% vốn/lệnh, gồm phí 2 lượt × 8,250).

**Xác minh bằng ENGINE THẬT (sau khi implement SL/TP, fee 8,250):**

| Cấu hình | Lệnh | Win% | PnL | Ret | MaxDD |
|---|---|---|---|---|---|
| default entry, không exit | 21 | 47.6% | 14,556,750 | +14.71% | 5.3% |
| default entry, SL=5 | 28 | 35.7% | 18,599,000 | **+18.69%** | 4.4% |
| default entry, SL=3 | 33 | 27.3% | 16,917,750 | +17.36% | 3.4% |
| default entry, SL=8 | 24 | 41.7% | 17,692,000 | +17.82% | 4.4% |
| default entry, SL=5 + TP=8 | 53 | 52.8% | 8,712,750 | +8.28% | 2.3% |
| **lb=5 + ATR 0.001, không exit** | 17 | 58.8% | 20,069,750 | **+20.25%** | **2.9%** |
| lb=5 + ATR 0.001, SL=5 | 24 | 37.5% | 18,252,000 | +18.38% | 3.6% |

- SL=5 engine (+18.69%) gần khớp sim (+18.79%) — chênh nhẹ đúng caveat
  (sim fill tại mức; engine fill min/max theo open khi gap, conservative).
- SL vẫn giúp default entry rõ (+14.71% → +18.69%, MaxDD 5.3% → 4.4%) nhưng
  VỚI entry lb=5+ATR 0.001, SL=5 làm giảm nhẹ lợi nhuận (+20.25% → +18.38%):
  ATR filter đã lọc breakout giả nên SL ít giá trị, lại cắt vài lệnh thắng lớn.
  → Chọn theo khẩu vị rủi ro: entry tốt nhất + không SL (+20.25%, MaxDD 2.9%)
    hoặc entry tốt nhất + SL=5 (+18.38%, lỗ/lệnh có trần). TP luôn gây hại.

### 2c. Điểm yếu đã đo được (cần theo dõi)

- **Tập trung lợi nhuận cực cao:** 5/21 lệnh > +2tr chiếm 161% tổng PnL
  (+23,438,750 / +14,556,750) — 11 lệnh thua còn lại tổng -11,050,750
  (avg lỗ -1,004,614). SL=5 giải quyết trực tiếp vấn đề này.
- Hold time: median 317 bar (≈26 giờ giao dịch ≈ 4-5 phiên) — đây là swing,
  không phải scalping; kỳ vọng giữ vị thế nhiều ngày.
- Phí KHÔNG phải vấn đề lớn với entry default: chỉ 1/21 lệnh có |pnl| < 1
  điểm (fee-killer) — với fee 8,250đ/lượt, round-trip = 16,500đ = 0.165
  điểm, vẫn nhỏ so với biến động giá thực tế (đa số lệnh đi 5-20 điểm).
  Tuy nhiên các cấu hình exit NHIỀU lệnh (vd SL=3 → 33 lệnh = 66 lượt)
  chịu thêm đáng kể: 66 × 8,250 = 544,500đ tổng phí — đã nằm trong các
  con số E3 ở trên (không phải chi phí phát sinh thêm ngoài bảng).

## 3. Chiến lược SMA Cross (KHÔNG khuyến nghị — chỉ tham khảo)

| Cấu hình | Lệnh | Win% | PnL | Ret | MaxDD | Ghi chú |
|---|---|---|---|---|---|---|
| 10/20, atr_th=0.005 (default) | 0 | – | 0 | 0% | – | Filter chặn hết: max ATR/close=0.0044 < 0.005 |
| 10/20, atr_th=0.0 | 18 | 27.8% | -3,348,500 | -3.50% | 5.9% | Chỉ bắt LONG (0 short) trên sample uptrend |
| 5/10, atr_th=0.001 | 60 | 41.7% | 6,915,000 | +6.42% | 8.6% | Tốt nhất của SMA; trade 2 chiều (55 short mở) |
| 5/10, atr_th=0.0 | 36 | 27.8% | -3,117,000 | -3.41% | 5.7% | Vẫn long-only |

**Kết luận:** SMA kém hơn Momentum trên mọi cấu hình (PnL thấp hơn, MaxDD cao
hơn). Không đầu tư thêm trừ khi có lý do cụ thể (vd regime filter, khung lớn hơn).

## 4. Thông số RISK (khuyến nghị giữ nguyên + hướng phát triển)

| Thông số | Hiện tại | Đề xuất | Lý do |
|---|---|---|---|
| `max_contracts` | 1 | Giữ 1 | Chưa có mô hình margin thật; tăng size cần ký quỹ + slippage thực |
| `max_daily_loss_pct` | 3% | Giữ 3% | Hợp lý; chưa từng chạm ngưỡng trong sample |
| Position sizing | Cố định 1 hợp đồng | (Tương lai) ATR-based risk sizing | Vốn 100tr vs rủi ro ~0.5tr/lệnh → dư địa lớn, nhưng cần margin thật trước |

## 5. Trạng thái implement

| Mục | Trạng thái |
|---|---|
| Entry params khuyến nghị (lb=5, vmult=2.0, vper=20, atr 0.001) | Áp dụng NGAY được — constructor đã hỗ trợ, không cần sửa code |
| SL/TP exit | **ĐÃ IMPLEMENT trong engine** (`stop_loss_points`/`take_profit_points` của `run_derivative_backtest`, TDD, gap rule theo TrailingStopManager) — plan `2026-08-08-derivative-stop-loss-engine.md` đã execute |
| Slippage model | CHƯA có — nên thêm trước khi chốt thông số production |
| Out-of-sample / walk-forward | CHƯA — bắt buộc trước khi dùng thông số thật |
| Momentum params tune thêm (chỉnh tinh quanh lb=5) | Nên làm cùng dữ liệu dài hơn (>2 tháng) |

## 6. Script nghiên cứu

`scripts/.spike_improve_derivative_strategies.py` (throwaway, dot-prefixed) —
chạy lại được: `PYTHONPATH=. uv run python scripts/.spike_improve_derivative_strategies.py`
