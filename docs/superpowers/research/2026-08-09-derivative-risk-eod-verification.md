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

## Caveat

- 1 sample duy nhất 2 tháng, chưa out-of-sample / walk-forward.
- EOD close fill tại `bar.close` của bar cắt — không mô phỏng chênh lệch
  giá/thanh khoản cuối phiên thực tế.
- Phí VSD trong `DERIVATIVE_FEE_PER_CONTRACT` tạm gộp theo lượt; nếu tính
  thêm theo ngày giữ vị thế thì lợi ích tương đối của EOD close (tránh phí
  qua đêm) sẽ cao hơn một chút so với con số trên.
