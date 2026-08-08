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

## Caveat

- 1 sample duy nhất 2 tháng, chưa out-of-sample / walk-forward.
- EOD close fill tại `bar.close` của bar cắt — không mô phỏng chênh lệch
  giá/thanh khoản cuối phiên thực tế.
- Phí VSD trong `DERIVATIVE_FEE_PER_CONTRACT` tạm gộp theo lượt; nếu tính
  thêm theo ngày giữ vị thế thì lợi ích tương đối của EOD close (tránh phí
  qua đêm) sẽ cao hơn một chút so với con số trên.
