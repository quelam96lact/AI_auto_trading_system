# Inventory: chiến lược giao dịch phái sinh hiện có

**Ngày:** 2026-08-09
**Phạm vi:** phái sinh VN30F1M (SSI). Tổng hợp các chiến lược + bằng chứng
backtest từ các research doc đã commit. User yêu cầu bỏ SmaCrossStrategy khỏi
danh sách (chỉ giữ các chiến lược momentum-based).

## 1. Chiến lược trong code (trading/strategies/)

### 1a. MomentumBreakoutStrategy (momentum_breakout.py) — SẢN XUẤT
- Cơ chế: breakout Donchian channel (lookback bar) + volume spike +
  ATR% filter tùy chọn; swing giữ lệnh trung bình 4-5 phiên.
- Tham số: `lookback`, `volume_multiplier`, `volume_period`,
  `atr_pct_threshold` (0.0 = tắt).
- Bằng chứng (100tr, 2 tháng, fee 8,250): default (lb=10) 21 lệnh/47.6%/
  +14.71%/MaxDD 5.3% → tune (lb=5, vm=2.0, vp=20, atr=0.001) 17 lệnh/
  58.8%/+20.25%/MaxDD 2.9%.
- Là nền tảng của cấu hình vận hành chốt (mục 2).

### 1b. MomentumRSIStrategy (momentum_rsi.py — mới, b4331be) — CANDIDATE
- Cơ chế: MomentumBreakoutStrategy + RSI Wilder 14 filter — chặn "bull"
  khi RSI ≥ 70 (quá mua), chặn "bear" khi RSI ≤ 30 (quá bán). Là "bộ GIẢM
  RỦI RO": mục tiêu giảm MaxDD + tăng win rate; PnL tăng nhẹ là hệ quả phụ.
- Tham số: `rsi_period=14`, `rsi_high=70.0`, `rsi_low=30.0` + params parent.
- Bằng chứng (30tr, EOD 14:20 keep 1.0, 2 tháng): 18 lệnh/66.7%/+65.48%/
  MaxDD 8.1% (vs baseline 21/52.4%/+60.05%/9.8%).
- CHƯA out-of-sample — sẵn sàng paper trading khi user muốn.

## 2. Cấu hình vận hành CHỐT (spec 2026-08-09, vốn 30tr)

| Thành phần | Giá trị |
|---|---|
| Strategy | `MomentumBreakoutStrategy(qty=1, lookback=5, volume_multiplier=2.0, volume_period=20, atr_pct_threshold=0.001)` |
| Số HĐ | 1 (tối đa) — margin D+ 3% intraday / 6% qua đêm (base 17% không đủ 30tr) |
| Risk | max_daily_loss_pct=2% (600k/ngày) + max_consecutive_losses=2, tính theo NGÀY |
| EOD | `intraday_close_time=time(14,20)`, `eod_keep_min_profit_points=1.0` (đóng lệnh lỗ, giữ lãi ≥ 1.0 điểm qua đêm) |
| SL/TP | TẮT (bằng chứng: không giúp) |
| Phí | 8,250đ/lượt (conservative; D+ thực tế 7,000đ theo iBoard) |
| Kết quả (2 tháng) | 21 lệnh, 52.4% win, +60.05%, MaxDD 9.8%, chi phí D+ ~1.78tr |

## 3. Nhánh nghiên cứu ĐÃ ĐÓNG (bằng chứng âm tính, đừng làm lại)

- **SL/TP cố định:** SL=5 giảm PnL (49.95% vs 60.05%); TP=10/15 phá chiến
  lược (+10.8%).
- **Trailing stop — mọi biến thể:** thuần (lỗ -17%), kích hoạt theo lãi
  ≥ N điểm (tốt nhất +8.01%), kết hợp RSI filter (+16.40%), gate RSI
  (x3: +44.89%) — ĐỀU kém baseline; trailing luôn cắt sớm hơn crossover
  exit → giảm avgW, tăng phí. Đóng vĩnh viễn.
- **EMA trend filter** (9/21, 13/55, 21/55): thất bại (+8.96% tệ nhất,
  MaxDD 28.5%).
- **Khung 10m/15m:** 10m +70.68% nhưng chỉ 12 lệnh (chưa đủ tin cậy —
  cần out-of-sample); 15m loại (−34% no-EOD, MaxDD 40.7%). GIỮ 5m.
- **Tham số khác:** vp=30 / SL=10 cải thiện nhẹ không đáng kể; lb>5, vm>2,
  atr≠0.001 đều xấu hơn → baseline đã ở vùng tối ưu.

## 4. Nút thắt + việc cần làm

1. **Out-of-sample:** dữ liệu chỉ 2 tháng — mọi kết luận (gồm RSI candidate)
   cần kiểm chứng trên dữ liệu dài hơn trước khi tin.
2. **Paper trading ≥ 50 lệnh** với cấu hình chốt (hoặc RSI candidate) theo
   file đề xuất, đối chiếu backtest trước khi vào tiền thật.
3. **Chưa confirm:** lãi suất D+ qua đêm 0.0487%/ngày (không hiển thị trên
   iBoard — cần xem màn hình chi tiết D+); VSD 2,550đ/hợp đồng per lượt
   (đã xác nhận); phí ký quỹ VSDC 0.0024% + thuế TNCN chưa mô hình.
