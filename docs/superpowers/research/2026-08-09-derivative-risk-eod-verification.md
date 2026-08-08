# Kiểm chứng: risk mới (2% + 2 lệnh thua liên tiếp) × EOD close 14:20

> Plan: `docs/superpowers/plans/2026-08-09-derivative-risk-eod-adjustments.md`
> Script: `scripts/.spike_risk_eod_derivative_strategies.py` (throwaway, dot-prefixed)
> Dữ liệu: `scripts/.spike_derivative_ohlc_5m_2m_sample.json` — 1493 bars 5m,
> 2026-06-19 → 2026-08-07, vốn 100,000,000, fee 8,250đ/lượt, qty=1.
> Entry cố định: `MomentumBreakoutStrategy(qty=1, lookback=5,
> volume_multiplier=2.0, volume_period=20, atr_pct_threshold=0.001)` (tham số
> khuyến nghị từ research doc 2026-08-08, KHÔNG đổi).

## Kết quả (output nguyên văn)

```
====================================================================================================
SPIKE: risk moi (2% + 2 lenh thua lien tiep) x EOD close 14:20 - MomentumBreakout lb=5 atr=0.001
Data: 1493 bars 5m | 2026-06-19 -> 2026-08-07 | von 100,000,000 | fee 8,250
====================================================================================================
Cau hinh                                    Trd   Win%       avgW           PnL      Ret   MaxDD  halt
1. Baseline (risk cu 3%, khong streak, khong EOD)   17 58.8%  2,582,750    20,069,750 +20.25%   2.9%  None
2. Risk moi (2% + 2-loss halt), khong EOD    17 58.8%  2,582,750    20,069,750 +20.25%   2.9%  None
3. Risk cu, EOD close 14:20                  36 61.1%    974,023     9,093,000  +9.51%   3.6%  None
4. Risk moi + EOD close 14:20                36 61.1%    974,023     9,093,000  +9.51%   3.6%  None
```

## Nhận xét khách quan (không tô hồng)

1. **Baseline khớp chính xác research doc 2026-08-08** (+20.25%, MaxDD 2.9%,
   17 lệnh) — script chạy đúng, số liệu tái lập được.

2. **Risk mới (2% + 2 lệnh thua liên tiếp) KHÔNG thay đổi kết quả trên sample
   này** (cấu hình 2 = cấu hình 1; cấu hình 4 = cấu hình 3): không có chuỗi
   2 lệnh thua liên tiếp, và không có ngày nào lỗ chạm 2% vốn trong 2 tháng.
   → Chi phí an toàn = 0 trên sample, NHƯNG cũng đồng nghĩa: chưa có bằng
   chứng từ dữ liệu này rằng hai rule mới thực sự bảo vệ được gì. Đây là
   rule phòng thủ cho kịch bản xấu (streak thua, ngày lỗ lớn) chưa xuất
   hiện trong sample.

3. **EOD close 14:20 làm giảm PnL đáng kể: +20.25% → +9.51% (giảm ~53%)**,
   đúng lo ngại đã nêu trong plan "Vì sao": chiến lược đang thắng có hold
   time trung vị ~317 bar (4-5 phiên), ép đóng cuối phiên cắt đứt các lệnh
   thắng lớn đang chạy. Bằng chứng: win rate TĂNG (58.8% → 61.1%) nhưng
   avgW GIẢM mạnh (2,582,750 → 974,023) — thắng nhiều lệnh nhỏ hơn, mất
   đuôi lãi. MaxDD hơi tăng (2.9% → 3.6%) do số lệnh nhiều hơn (17 → 36).

4. **KHÔNG chọn cấu hình "khuyến nghị cuối" ở đây** — theo yêu cầu plan Task
   4 Bước 3: số liệu chỉ được trình bày khách quan, để Claude/user quyết
   định đánh đổi giữa an toàn vốn theo quy tắc D+ (không giữ qua đêm) và
   giữ lợi nhuận (giữ vị thế nhiều ngày).

## Bổ sung (theo yêu cầu user: "đến 14h20 lệnh đang lãi thì giữ qua đêm")

Engine đã tinh chỉnh: tại/sau `intraday_close_time`, CHỈ đóng lệnh đang LỖ
(`_unrealized() <= 0`); lệnh đang LÃI được GIỮ qua đêm và tiếp tục quản lý
bình thường (SL/TP/crossover vẫn áp dụng). Chạy lại script với engine mới:

```
Cau hinh                                    Trd   Win%       avgW           PnL      Ret   MaxDD  halt
1. Baseline (risk cu 3%, khong streak, khong EOD)   17 58.8%  2,582,750    20,069,750 +20.25%   2.9%  None
2. Risk moi (2% + 2-loss halt), khong EOD    17 58.8%  2,582,750    20,069,750 +20.25%   2.9%  None
3. Risk cu + EOD 14:20 (engine moi: chi dong lo, giu lenh lai)   23 43.5%  2,550,750    17,700,250 +18.22%   4.3%  None
4. Risk moi + EOD 14:20 (engine moi: chi dong lo, giu lenh lai)   23 43.5%  2,550,750    17,700,250 +18.22%   4.3%  None
```

Nhận xét khách quan:
- Rule "giữ lệnh lãi qua đêm" phục hồi gần hết lợi nhuận so với "đóng hết":
  +18.22% vs +9.51% (chỉ giảm ~10% so với baseline +20.25%, thay vì ~53%).
- Cơ chế: avgW được bảo toàn (2,550,750 ≈ baseline 2,582,750) — đuôi lãi
  của các lệnh thắng lớn (hold nhiều ngày) không bị cắt tại 14:20; các
  lệnh đang lỗ cuối phiên vẫn bị đóng sớm (trades 17 → 23, win rate giảm
  58.8% → 43.5% do nhiều lệnh lỗ nhỏ được realize).
- MaxDD hơi tăng (2.9% → 4.3%) do nhiều lệnh hơn và vẫn còn rủi ro gap
  qua đêm cho phần lệnh lãi được giữ.
- Lưu ý ngưỡng "có lãi": dùng `unrealized > 0` (gross, chưa trừ phí đóng).
  Lệnh lãi gross nhưng nhỏ hơn tổng phí round-trip (16,500đ ≈ 0.165 điểm)
  sẽ được giữ nhưng thực chất net âm — có thể tinh chỉnh ngưỡng sau nếu cần.
- KHÔNG chọn cấu hình "khuyến nghị cuối" ở đây — số liệu khách quan, để
  Claude/user quyết đánh đổi.

## Bổ sung: daily-loss theo ngày + ngưỡng giữ lãi 1.0 điểm (vốn 30tr)

Plan: `docs/superpowers/plans/2026-08-09-derivative-daily-loss-and-eod-threshold-fix.md`.
2 fix: (1) `daily_pnl` tính theo NGÀY (snapshot realized đầu ngày, reset khi
đổi ngày — trước đây tích lũy từ đầu backtest, khiến vốn 30tr halt vĩnh viễn
sau lệnh thua đầu tiên); (2) param `eod_keep_min_profit_points` (default 0.0
= hành vi cũ) — chỉ giữ lãi qua đêm khi lãi đủ bù chi phí D+ + phí đóng
(~1 điểm @1900). Chạy lại script (output nguyên văn):

```
A) YEU CAU KY QUY 1 HOP DONG VN30F (gia tri = gia x 100,000)
 Gia VN30F     Gia tri    Base 17%  D+ intra 3% D+ qua dem 6%
    1796.3     179.6tr     30.54tr       5.39tr       10.78tr
    1900.0     190.0tr     32.30tr       5.70tr       11.40tr
    2022.8     202.3tr     34.39tr       6.07tr       12.14tr
Von 30tr chi du base 17% khi gia <= 1765 diem
  (voi dem 1.25x: <= 1412 diem; 1.5x: <= 1176)
Von 30tr du D+ qua dem 6% toi gia <= 5000 diem (dem 1.25x: 4000)
  -> trong sample (1796-2022), base 17% KHONG du voi 30tr; chi kha thi qua D+ (3%/6%)

B) BACKTEST 100tr vs 30tr - sau fix daily-theo-ngay + nguong giu lai 1.0 diem
Config                                Trd   Win%          PnL      Ret   MaxDD       halt O/N dem
100tr khong EOD                        17 58.8%   20,069,750 +20.25%   2.9%       None      33
100tr EOD 14:20 nguong 0.0             22 45.5%   19,038,500 +19.57%   4.0% 2026-07-27      21
100tr EOD 14:20 nguong 1.0             22 54.5%   19,328,500 +19.86%   3.9% 2026-07-27      21
30tr khong EOD                         15 46.7%    9,766,250 +34.51%  17.0% 2026-08-06      32
30tr EOD 14:20 nguong 0.0              21 42.9%   17,186,750 +59.08%  10.1% 2026-08-06      20
30tr EOD 14:20 nguong 1.0              21 52.4%   17,476,750 +60.05%   9.8% 2026-08-06      20

C) CHI PHI D+ QUA DEM (0.0487%/ngay tren phan tai tro = gia tri x 94%)
  So lenh giu qua dem: 9/21 round-trip
  Tong phi D+ qua dem uoc tinh: 1,778,924 VND (tren 1493 bars, 2 thang)
  Phi D+ trung binh/lenh qua dem: 197,658 VND
  So sanh: tong phi giao dich (fee 8,250 x 2 x 21 lenh) = 346,500 VND
```

Nhận xét khách quan:
- **100tr regression OK:** không-EOD giữ nguyên +20.25%/2.9%/17 lệnh — đúng
  dự đoán plan (không ngày nào chạm 2% = 2tr nên per-day = cumulative).
  EOD giờ có halt 2026-07-27 (ngày lỗ > 2tr khi đóng lệnh lỗ sớm) — hành vi
  đúng nghĩa "dừng ngày khi lỗ 2%".
- **Fix daily khôi phục 30tr:** trước fix chỉ 1 lệnh (-2.05%), sau fix 15 lệnh
  (+34.51% không-EOD). Cảnh báo: MaxDD 17% (vốn nhỏ + 1 HĐ → biến động %
  vốn gấp ~3.3x so với 100tr) — cần đệm vốn hoặc chấp nhận rủi ro cao.
- **Ngưỡng 1.0 điểm cải thiện win rate rõ:** 30tr 42.9% → 52.4%, 100tr
  45.5% → 54.5% (các lệnh lãi gross < 1 điểm giờ bị đóng thay vì giữ qua
  đêm trả D+ — không còn biến lãi nhỏ thành lỗ ròng). PnL tăng nhẹ.
- **Chi phí D+ qua đêm vẫn đáng kể** (~1.78tr/2 tháng ≈ 5x phí giao dịch,
  ~198k/lệnh giữ qua đêm) — nhưng chỉ rơi vào các lệnh lãi lớn (pnl
  1-5.6tr) nên vẫn có lời ròng; cần xác nhận lại cơ chế tính với SSI.
- Caveat: D+ rate/margin (0.0487%, 6%) là hằng số chưa confirm với SSI; 1
  sample 2 tháng, chưa out-of-sample. KHÔNG chọn "khuyến nghị cuối" — số
  liệu khách quan để Claude/user quyết.

## Bổ sung: độ nhạy khung thời gian (5m vs 10m vs 15m)

Script: `scripts/.spike_timeframe_sensitivity.py` (throwaway). Resample dữ
liệu 5m gốc (1493 bars, 2026-06-19 → 2026-08-07) sang 10m/15m theo session
VN (09:00-11:30 / 13:00-14:45, không trộn qua giờ nghỉ), chạy lại CẤU HÌNH
VẬN HÀNH CHỐT (Momentum lb=5+ATR 0.001, 1 HĐ, risk 2% ngày + 2-lỗ liên
tiếp, EOD 14:20 ngưỡng giữ lãi 1.0, fee 8,250, vốn 30tr). Lưu ý: ATR/lookback
tính trên bar đã resample (ý nghĩa thời gian khác nhau); EOD 14:20 với bar
15m rơi vào bar 14:15-14:30 → đóng tại 14:30. Output:

```
===== 5m (goc): 1493 bars =====
Config                  Trd   Win%    PnL(real)      Eq cuoi      Ret   MaxDD       halt  O/N
khong EOD                15 46.7%    9,766,250   40,354,250 +34.51%  17.0% 2026-08-06   32
EOD 14:20 1.0            21 52.4%   17,476,750   48,015,250 +60.05%   9.8% 2026-08-06   20

===== 10m: 817 bars =====
khong EOD                 9 66.7%   22,975,750   52,901,500 +76.34%  15.8% 2026-07-08   37
EOD 14:20 1.0            12 41.7%   20,981,000   51,203,750 +70.68%  11.5% 2026-07-08   23

===== 15m: 566 bars =====
khong EOD                 8 25.0%  -10,006,000   19,789,750 -34.03%  40.7% 2026-07-20   18
EOD 14:20 1.0            11 18.2%     -780,750   36,190,250 +20.63%  19.7% 2026-07-20   10
```

Nhận xét khách quan:
- **15m: loại khỏi xem xét.** Không EOD lỗ -34.03% (MaxDD 40.7%), có EOD
  chỉ +20.63% (MaxDD 19.7% — gấp đôi 5m). Tín hiệu/ATR 15m quá trễ, cắt
  lỗ lớn, halt kích hoạt sớm (chuỗi thua liên tiếp).
- **10m: return cao hơn 5m trên sample** (+70.68% vs +60.05% EOD; +76.34%
  vs +34.51% không EOD) NHƯNG chỉ 12 lệnh (5m: 21) → độ tin cậy thống kê
  thấp; win rate thấp hơn (41.7% vs 52.4%); kết quả phụ thuộc vài lệnh lớn
  → rủi ro overfit sample cao. MaxDD 11.5% (cao hơn 5m 9.8%).
- **Risk system hoạt động trên cả 3 khung** (halt 2%/ngày + 2-lỗ kích hoạt).
- Kết luận: GIỮ 5m làm khung vận hành (nhiều lệnh nhất, MaxDD thấp nhất,
  đã qua nhiều vòng audit). 10m đáng kiểm chứng thêm với dữ liệu dài hơn
  (out-of-sample) trước khi tin — chưa đủ bằng chứng. Quyết định cuối để
  Claude/user.

## Bổ sung: indicator mới — RSI 14 (70/30) kết hợp chiến lược hiện tại

Script: `scripts/.spike_new_indicators_5m.py` + `scripts/.spike_rsi_combination_analysis.py`
(throwaway). Cách tiếp cận: KHÔNG sửa `trading/strategies/momentum_breakout.py`
(bất khả xâm phạm) — subclass trong script, override `compute_crossover` để
áp filter lên tín hiệu gốc:
- `MomentumEMA(ema_fast, ema_slow)`: chặn "bull" khi EMA_fast ≤ EMA_slow
  (downtrend), chặn "bear" khi EMA_fast ≥ EMA_slow (uptrend).
- `MomentumRSI(rsi_period=14, rsi_high=70, rsi_low=30)`: chặn "bull" khi
  RSI ≥ 70 (quá mua), chặn "bear" khi RSI ≤ 30 (quá bán).
- LƯU Ý interface: `compute_crossover` không biết vị thế đang giữ → filter
  tác động cả lệnh MỞ lẫn lệnh ĐÓNG cùng chiều (bull cũng là tín hiệu đóng
  short) — đây là thiết kế trend-following chủ ý.

Kết quả (cấu hình chốt: EOD 14:20 keep 1.0, risk 2%/ngày + 2-lỗ, fee 8,250,
vốn 30tr, 5m):

```
Strategy                        Trd  Win%    PnL(real)    Ret     MaxDD  halt
Baseline (khong filter)          21 52.4%   17,476,750  +60.05%   9.8%  08-06
EMA 9/21                         14 28.6%    2,804,500   +8.96%  28.5%  08-06
EMA 13/55                        10 50.0%   10,937,500  +36.18%  10.1%  07-29
EMA 21/55                        12 41.7%    8,711,000  +28.71%  17.2%  07-29
RSI 14 (70/30)                   18 66.7%   19,081,500  +65.48%   8.1%  07-27
RSI 14 (65/35)                   17 58.8%   18,189,750  +62.54%   8.0%  None
RSI 7 (70/30)                    14 57.1%   16,664,500  +60.84%  11.4%  None
EMA 9/21 + RSI 70/30              8 62.5%    7,684,000  +25.39%  17.6%  None
EMA 21/55 + RSI 70/30             5 60.0%    4,148,750  +13.69%  12.4%  None
```

Phân tích cơ chế (RSI 70/30 chặn 6/21 lệnh baseline):

```
2026-07-10 SHORT  -188,250   (chan dung - lo nho)
2026-07-13 SHORT +5,661,750  (CHAN NHAM - bo lo lenh THANG LON NHAT!)
2026-07-20 SHORT  -178,250   (chan dung)
2026-07-27 LONG  -2,018,250  (chan dung - mua duoi khi RSI >= 70)
2026-08-05 LONG  -1,038,250  (chan dung)
2026-08-06 LONG  -2,258,250  (chan dung - lo lon nhat, mua duoi dinh)
Tong 6 lenh bi chan: -19,500 (gan hoa: chan duoc 5 lo -5.68tr, bo lo 1 thang +5.66tr)
```

Kết luận khách quan:
- **RSI 70/30 = "bộ GIẢM RỦI RO" hơn "bộ TĂNG LỢI NHUẬN":** win rate
  52.4→66.7%, MaxDD 9.8→8.1% (EOD) / 17.0→13.6% (no-EOD), không halt trên
  no-EOD — nhờ tránh mua đuổi/bán đuổi vùng cực đoan (RSI ≥ 70 / ≤ 30).
- PnL tăng nhẹ +1.6tr dù bỏ lỡ lệnh thắng lớn nhất (+5.66tr) — do cascade
  (chặn 1 lệnh đổi trạng thái các lệnh sau) + chặn được 2 lệnh LONG mua
  đuổi cuối tháng 8 (-2tr, -2.26tr).
- EMA filter: THẤT BẠI (9/21 hủy hoại +8.96% MaxDD 28.5% — chặn cả exit
  giữ lệnh sai hướng lâu; 13/55 và 21/55 đều kém baseline). Kết hợp
  EMA+RSI quá ít lệnh (5-8) — không đáng.
- vp=30 KHÔNG cộng dồn với RSI (+63.93% vs RSI đơn +65.48%).
- 2 ngưỡng liền kề (70/30, 65/35) đều tốt → không phải đỉnh cô đơn, nhưng
  vẫn chỉ 1 sample 2 tháng (~18 lệnh). Cần out-of-sample trước khi chốt làm
  chiến lược sản phẩm. Quyết định cuối để Claude/user.

## Bổ sung: trailing stop (thuần, kích hoạt trễ, kết hợp RSI) — ÂM TÍNH

Script: `scripts/.spike_trailing_stop.py` (throwaway). Engine phái sinh CHƯA
hỗ trợ trailing (chỉ SL/TP cố định) — spike copy loop `run_derivative_backtest`
nguyên văn + thêm ATR-trailing (mirror quy ước repo: long stop = highest −
ATR×mult, fill `min(bar.open, stop)`; short mirror; ATR hiện tại từ
`strategy.last_atr`; activation ≥ N điểm tính theo bar.high/low intrabar).
Cấu hình chốt (EOD 14:20 keep 1.0, risk 2%/ngày + 2-lỗ, fee 8,250, 30tr, 5m).

```
Config                                Trd  Win%   PnL(real)    Ret     MaxDD  halt
Baseline (khong gi)                    21 52.4%  17,476,750  +60.05%   9.8%  08-06
RSI 70/30 (khong trailing)             18 66.7%  19,081,500  +65.48%   8.1%  07-27
--- trailing thuan (khong RSI) ---
Trailing ATR x1.5                      51 31.4%  -4,677,536  -16.99%   21.3%
Trailing ATR x2.0                      43 32.6%  -4,879,036  -17.45%   21.5%
Trailing ATR x3.0                      34 47.1%   5,989,500  +19.03%    9.3%
Trailing ATR x4.0                      29 37.9%   9,410,750  +32.94%   10.8%
Trail x2 + act 3..15 diem             29-40  -31.4% .. +8.01%   MaxDD 17-35%
Trail x2 + act 8 (no EOD)              35 71.4%   7,245,536  +23.19%   12.9%
--- ket hop RSI 70/30 + trailing ---
RSI + trail x2 + act 5..15             23-31  -13.88% .. +10.75%  MaxDD 13-23%
RSI + trail x3 + act 8/10              23-25 ~58%  +15.43/+16.40%  MaxDD 13.5-14.9%
RSI 65/35 + trail x2 act 8             25 60.0%   1,259,464   +3.51%   12.6%  None
RSI + trail x2 act 8/10 (no EOD)      18-19 ~65%    ~0.6-1tr   -0.7/-1.9%  20.4-20.7%
```

Kết luận khách quan:
- **Trailing stop (mọi biến thể) KHÔNG phù hợp chiến lược này.** Thuần:
  lỗ -17% (x1.5-2, whipsaw — cắt lệnh ngay cú hồi nhẹ, số lệnh 21→43-51);
  rộng nhất (x4) vẫn kém baseline (32.94% vs 60.05%).
- **Kích hoạt trễ (lãi ≥ N điểm) giúp đỡ hại dần** (x2: -17.45% → act8
  -5.93% → act15 +8.01%) NHƯNG mọi ngưỡng vẫn tệ xa baseline cả return lẫn
  MaxDD — trailing luôn cắt sớm hơn crossover exit → giảm avgW, tăng phí.
- **RSI KHÔNG "cứu" được trailing**: kết hợp tốt nhất +16.40% (x3+act10) —
  vẫn kém RSI đơn (+65.48%) và kém cả baseline. Trailing làm tăng số lệnh
  (23-31 vs 18 RSI đơn).
- Lý do gốc: chiến lược swing kiếm tiền từ việc GIỮ lệnh qua cú hồi;
  crossover exit + EOD giữ lãi là bộ exit tối ưu. KHÔNG làm plan TDD trailing
  cho derivative engine.

## Caveat

- 1 sample duy nhất 2 tháng, chưa out-of-sample / walk-forward.
- EOD close fill tại `bar.close` của bar cắt — không mô phỏng chênh lệch
  giá/thanh khoản cuối phiên thực tế.
- Phí VSD trong `DERIVATIVE_FEE_PER_CONTRACT` tạm gộp theo lượt; nếu tính
  thêm theo ngày giữ vị thế thì lợi ích tương đối của EOD close (tránh phí
  qua đêm) sẽ cao hơn một chút so với con số trên.
