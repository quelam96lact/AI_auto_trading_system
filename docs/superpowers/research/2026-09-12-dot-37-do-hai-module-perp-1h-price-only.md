# Báo cáo nghiên cứu Đợt 37 — Đo lường hai module perpetual 1H (Price-Only)

- Ngày thực hiện: 12/09/2026 UTC
- Người thực thi: Gemini Flash 3.8
- Người lập kế hoạch & audit: Claude
- Đối tượng kiểm định: `BTC-USDT` perpetual 1H (dữ liệu BingX, 20.742 nến từ 2024-04-27 đến 2026-09-08 UTC).
- File triển khai:
  - `trading/indicators.py`: Bổ sung 3 chỉ báo `DonchianCalculator`, `BollingerCalculator` (+ `percent_b`), `AdxCalculator`.
  - `trading/perp_backtest.py`: Engine mô phỏng độc lập cho `donchian_breakout` và `bollinger_mr`.
  - `scripts/measure_perp_modules.py`: CLI đo lường, phân chia IS/OOS và tính mua-và-giữ đối chứng.

---

## 1. Nguyên văn output của 4 lượt chạy (Copy từ terminal)

### Lượt 1: Baseline IS (`--module all --split is --slippage-bps 0`)

```
--- ĐANG CHẠY TẬP: IS (Số nến: 14726 | 2024-04-27 10:00:00+00:00 -> 2025-12-31 23:00:00+00:00 UTC) ---
=========================================================================================================
BÁO CÁO MODULE: DONCHIAN_BREAKOUT | TẬP: IS | MÃ: BTC-USDT
=========================================================================================================
CẢNH BÁO HỆ THỐNG:
  [1] [PRICE-ONLY] Điều kiện Order Flow / delta / OFI bị BỎ vì không có dữ liệu. Đây không phải bản đầy đủ.
  [2] [CHƯA MÔ HÌNH HOÁ FUNDING] Tổng mốc funding sống qua: 110 mốc (00/08/16 UTC).
  [3] [CHƯA MÔ HÌNH HOÁ THANH LÝ] Không có lệnh nào chạm ngưỡng thanh lý (would_liquidate = 0).
---------------------------------------------------------------------------------------------------------
Signals  Expired  Cancel   Trades   WinRate   Net PnL      PnL%      BH PnL       PF      Expectancy  MaxDD%   Sharpe   AvgBars  Fees      Clip   Liq   FundSpans
---------------------------------------------------------------------------------------------------------
129      1        43       85         31.8%       -42.89    -8.58%     195.13    0.68      -0.50   10.19%   -1.26    10.6    16.75 0      0     110      
---------------------------------------------------------------------------------------------------------
PHÂN RÃ THEO CHIỀU (LONG / SHORT):
  Side     Trades   WinRate   Net PnL (USDT)   Profit Factor 
  ---------------------------------------------------------
  LONG     36         30.6%           -23.75            0.59
  SHORT    49         32.7%           -19.14            0.74
=========================================================================================================

=========================================================================================================
BÁO CÁO MODULE: BOLLINGER_MR | TẬP: IS | MÃ: BTC-USDT
=========================================================================================================
CẢNH BÁO HỆ THỐNG:
  [1] [PRICE-ONLY] Điều kiện Order Flow / delta / OFI bị BỎ vì không có dữ liệu. Đây không phải bản đầy đủ.
  [2] [CHƯA MÔ HÌNH HOÁ FUNDING] Tổng mốc funding sống qua: 8 mốc (00/08/16 UTC).
  [3] [CHƯA MÔ HÌNH HOÁ THANH LÝ] Không có lệnh nào chạm ngưỡng thanh lý (would_liquidate = 0).
---------------------------------------------------------------------------------------------------------
Signals  Expired  Cancel   Trades   WinRate   Net PnL      PnL%      BH PnL       PF      Expectancy  MaxDD%   Sharpe   AvgBars  Fees      Clip   Liq   FundSpans
---------------------------------------------------------------------------------------------------------
20       0        0        15         40.0%        -9.53    -1.91%     195.13    0.55      -0.64    2.67%   -0.84     3.6     4.83 0      0     8        
---------------------------------------------------------------------------------------------------------
PHÂN RÃ THEO CHIỀU (LONG / SHORT):
  Side     Trades   WinRate   Net PnL (USDT)   Profit Factor 
  ---------------------------------------------------------
  LONG     4          25.0%            -4.23            0.33
  SHORT    11         45.5%            -5.30            0.65
=========================================================================================================
```

### Lượt 2: Ablation bật lọc EMA (`--module donchian_breakout --split is --ema-filter`)

```
--- ĐANG CHẠY TẬP: IS (Số nến: 14726 | 2024-04-27 10:00:00+00:00 -> 2025-12-31 23:00:00+00:00 UTC) ---
=========================================================================================================
BÁO CÁO MODULE: DONCHIAN_BREAKOUT | TẬP: IS | MÃ: BTC-USDT
=========================================================================================================
CẢNH BÁO HỆ THỐNG:
  [1] [PRICE-ONLY] Điều kiện Order Flow / delta / OFI bị BỎ vì không có dữ liệu. Đây không phải bản đầy đủ.
  [2] [CHƯA MÔ HÌNH HOÁ FUNDING] Tổng mốc funding sống qua: 74 mốc (00/08/16 UTC).
  [3] [CHƯA MÔ HÌNH HOÁ THANH LÝ] Không có lệnh nào chạm ngưỡng thanh lý (would_liquidate = 0).
---------------------------------------------------------------------------------------------------------
Signals  Expired  Cancel   Trades   WinRate   Net PnL      PnL%      BH PnL       PF      Expectancy  MaxDD%   Sharpe   AvgBars  Fees      Clip   Liq   FundSpans
---------------------------------------------------------------------------------------------------------
80       1        23       56         32.1%       -24.28    -4.86%     195.13    0.72      -0.43    6.68%   -0.88    10.5    11.45 0      0     74       
---------------------------------------------------------------------------------------------------------
PHÂN RÃ THEO CHIỀU (LONG / SHORT):
  Side     Trades   WinRate   Net PnL (USDT)   Profit Factor 
  ---------------------------------------------------------
  LONG     23         34.8%            -7.72            0.77
  SHORT    33         30.3%           -16.56            0.68
=========================================================================================================
```

### Lượt 3: Độ nhạy chi phí (`--module all --split is --slippage-bps 2.0`)

```
--- ĐANG CHẠY TẬP: IS (Số nến: 14726 | 2024-04-27 10:00:00+00:00 -> 2025-12-31 23:00:00+00:00 UTC) ---
=========================================================================================================
BÁO CÁO MODULE: DONCHIAN_BREAKOUT | TẬP: IS | MÃ: BTC-USDT
=========================================================================================================
CẢNH BÁO HỆ THỐNG:
  [1] [PRICE-ONLY] Điều kiện Order Flow / delta / OFI bị BỎ vì không có dữ liệu. Đây không phải bản đầy đủ.
  [2] [CHƯA MÔ HÌNH HOÁ FUNDING] Tổng mốc funding sống qua: 110 mốc (00/08/16 UTC).
  [3] [CHƯA MÔ HÌNH HOÁ THANH LÝ] Không có lệnh nào chạm ngưỡng thanh lý (would_liquidate = 0).
---------------------------------------------------------------------------------------------------------
Signals  Expired  Cancel   Trades   WinRate   Net PnL      PnL%      BH PnL       PF      Expectancy  MaxDD%   Sharpe   AvgBars  Fees      Clip   Liq   FundSpans
---------------------------------------------------------------------------------------------------------
129      1        43       85         29.4%       -58.77   -11.75%     194.85    0.57      -0.69   12.55%   -1.80    10.6    16.37 0      0     110      
---------------------------------------------------------------------------------------------------------
PHÂN RÃ THEO CHIỀU (LONG / SHORT):
  Side     Trades   WinRate   Net PnL (USDT)   Profit Factor 
  ---------------------------------------------------------
  LONG     36         27.8%           -31.05            0.49
  SHORT    49         30.6%           -27.72            0.64
=========================================================================================================

=========================================================================================================
BÁO CÁO MODULE: BOLLINGER_MR | TẬP: IS | MÃ: BTC-USDT
=========================================================================================================
CẢNH BÁO HỆ THỐNG:
  [1] [PRICE-ONLY] Điều kiện Order Flow / delta / OFI bị BỎ vì không có dữ liệu. Đây không phải bản đầy đủ.
  [2] [CHƯA MÔ HÌNH HOÁ FUNDING] Tổng mốc funding sống qua: 7 mốc (00/08/16 UTC).
  [3] [CHƯA MÔ HÌNH HOÁ THANH LÝ] Không có lệnh nào chạm ngưỡng thanh lý (would_liquidate = 0).
---------------------------------------------------------------------------------------------------------
Signals  Expired  Cancel   Trades   WinRate   Net PnL      PnL%      BH PnL       PF      Expectancy  MaxDD%   Sharpe   AvgBars  Fees      Clip   Liq   FundSpans
---------------------------------------------------------------------------------------------------------
20       0        0        15         40.0%        -9.67    -1.93%     194.85    0.55      -0.64    2.57%   -0.84     2.9     4.95 0      0     7        
---------------------------------------------------------------------------------------------------------
PHÂN RÃ THEO CHIỀU (LONG / SHORT):
  Side     Trades   WinRate   Net PnL (USDT)   Profit Factor 
  ---------------------------------------------------------
  LONG     5          40.0%            -2.52            0.61
  SHORT    10         40.0%            -7.14            0.53
=========================================================================================================
```

### Lượt 4: Duy nhất OOS (`--module all --split oos --slippage-bps 0`)

```
==========================================================================================
[CẢNH BÁO OOS] OOS chỉ được chạy MỘT LẦN sau khi tham số đã khoá.
Nếu bạn đang chỉnh tham số, đừng chạy lệnh này.
==========================================================================================

--- ĐANG CHẠY TẬP: OOS (Số nến: 6016 | 2026-01-01 00:00:00+00:00 -> 2026-09-08 15:00:00+00:00 UTC) ---
=========================================================================================================
BÁO CÁO MODULE: DONCHIAN_BREAKOUT | TẬP: OOS | MÃ: BTC-USDT
=========================================================================================================
CẢNH BÁO HỆ THỐNG:
  [1] [PRICE-ONLY] Điều kiện Order Flow / delta / OFI bị BỎ vì không có dữ liệu. Đây không phải bản đầy đủ.
  [2] [CHƯA MÔ HÌNH HOÁ FUNDING] Tổng mốc funding sống qua: 36 mốc (00/08/16 UTC).
  [3] [CHƯA MÔ HÌNH HOÁ THANH LÝ] Không có lệnh nào chạm ngưỡng thanh lý (would_liquidate = 0).
---------------------------------------------------------------------------------------------------------
Signals  Expired  Cancel   Trades   WinRate   Net PnL      PnL%      BH PnL       PF      Expectancy  MaxDD%   Sharpe   AvgBars  Fees      Clip   Liq   FundSpans
---------------------------------------------------------------------------------------------------------
46       0        20       26         38.5%         2.33     0.47%     -52.31    1.06       0.09    3.77%    0.20    11.7     5.37 0      0     36       
---------------------------------------------------------------------------------------------------------
PHÂN RÃ THEO CHIỀU (LONG / SHORT):
  Side     Trades   WinRate   Net PnL (USDT)   Profit Factor 
  ---------------------------------------------------------
  LONG     8          37.5%            -0.92            0.91
  SHORT    18         38.9%             3.25            1.13
=========================================================================================================

=========================================================================================================
BÁO CÁO MODULE: BOLLINGER_MR | TẬP: OOS | MÃ: BTC-USDT
=========================================================================================================
CẢNH BÁO HỆ THỐNG:
  [1] [PRICE-ONLY] Điều kiện Order Flow / delta / OFI bị BỎ vì không có dữ liệu. Đây không phải bản đầy đủ.
  [2] [CHƯA MÔ HÌNH HOÁ FUNDING] Tổng mốc funding sống qua: 4 mốc (00/08/16 UTC).
  [3] [CHƯA MÔ HÌNH HOÁ THANH LÝ] Không có lệnh nào chạm ngưỡng thanh lý (would_liquidate = 0).
---------------------------------------------------------------------------------------------------------
Signals  Expired  Cancel   Trades   WinRate   Net PnL      PnL%      BH PnL       PF      Expectancy  MaxDD%   Sharpe   AvgBars  Fees      Clip   Liq   FundSpans
---------------------------------------------------------------------------------------------------------
4        0        0        4          50.0%        -0.55    -0.11%     -52.31    0.89      -0.14    0.50%   -0.13     4.2     1.07 0      0     4        
---------------------------------------------------------------------------------------------------------
PHÂN RÃ THEO CHIỀU (LONG / SHORT):
  Side     Trades   WinRate   Net PnL (USDT)   Profit Factor 
  ---------------------------------------------------------
  LONG     3          33.3%            -2.49            0.50
  SHORT    1         100.0%             1.94             N/A
=========================================================================================================
```

---

## 2. Bảng tổng hợp IS vs OOS

| Module | Split | Signals | Trades | Win Rate | Net PnL (USDT) | PnL % | BH PnL (USDT) | Profit Factor | Max DD | Sharpe (1H) | Fees (USDT) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Donchian Breakout** (baseline) | **IS** | 129 | 85 | 31.8% | −42.89 | −8.58% | +195.13 | 0.68 | 10.19% | −1.26 | 16.75 |
| **Donchian Breakout** (EMA filter) | **IS** | 80 | 56 | 32.1% | −24.28 | −4.86% | +195.13 | 0.72 | 6.68% | −0.88 | 11.45 |
| **Donchian Breakout** (slip 2.0) | **IS** | 129 | 85 | 29.4% | −58.77 | −11.75% | +194.85 | 0.57 | 12.55% | −1.80 | 16.37 |
| **Donchian Breakout** | **OOS** | 46 | 26 | 38.5% | +2.33 | +0.47% | −52.31 | 1.06 | 3.77% | +0.20 | 5.37 |
| **Bollinger MR** (baseline) | **IS** | 20 | 15 | 40.0% | −9.53 | −1.91% | +195.13 | 0.55 | 2.67% | −0.84 | 4.83 |
| **Bollinger MR** (slip 2.0) | **IS** | 20 | 15 | 40.0% | −9.67 | −1.93% | +194.85 | 0.55 | 2.57% | −0.84 | 4.95 |
| **Bollinger MR** | **OOS** | 4 | 4 | 50.0% | −0.55 | −0.11% | −52.31 | 0.89 | 0.50% | −0.13 | 1.07 |

---

## 3. Kết luận theo tiêu chí chốt trước (§4.2)

Tiêu chí để một module được coi là **"đáng nghiên cứu tiếp"** áp dụng trên tập **OOS**:
1. `net_pnl > 0` sau phí, VÀ
2. `trades >= 30`, VÀ
3. `profit_factor > 1.0`.

### Kết luận từng module:

1. **Donchian Breakout**: **kết quả âm** (`net_pnl = +2.33 USDT`, `trades = 26`, `profit_factor = 1.06`).
   - *Lý do*: Mặc dù PnL dương (+2.33 USDT) và Profit Factor > 1.0 (1.06), nhưng số lệnh OOS chỉ đạt **26 lệnh**, **thiếu 4 lệnh** so với ngưỡng thống kê tối thiểu `trades >= 30`. Theo quy tắc khoá tiêu chí trước, không đạt 3/3 điều kiện thì ghi nhận là kết quả âm, không sửa tham số để cố cứu.

2. **Bollinger Mean Reversion**: **kết quả âm** (`net_pnl = -0.55 USDT`, `trades = 4`, `profit_factor = 0.89`).
   - *Lý do*: Không đạt cả 3 tiêu chí: lỗ −0.55 USDT, chỉ có 4 lệnh trong hơn 8 tháng OOS, và Profit Factor đạt 0.89 (< 1.0). Module phát tín hiệu cực kỳ thưa thớt (chỉ 4 tín hiệu trên 6.016 nến 1H) do 4 bộ lọc regime quá chặt.

---

## 4. So sánh với Mua-và-giữ (Buy & Hold)

- **Trên tập In-Sample (IS: 2024-04-27 → 2025-12-31)**:
  - Mua-và-giữ lãi mạnh **+195.13 USDT (+39.0%)**.
  - Cả hai module ở mọi cấu hình đều **thua lỗ** (Donchian lỗ từ −24.28 đến −58.77 USDT; Bollinger lỗ ~ −9.53 USDT).
  - Không module nào có biên lợi thế trên IS.

- **Trên tập Out-Of-Sample (OOS: 2026-01-01 → 2026-09-08)**:
  - Thị trường BTC giảm giá: Mua-và-giữ lỗ **−52.31 USDT (−10.5%)**.
  - Donchian Breakout giữ được vốn và lãi nhẹ **+2.33 USDT (+0.47%)**, phần lớn nhờ các lệnh Short (+3.25 USDT trên 18 lệnh Short). Mặc dù vượt Buy-and-Hold trong giai đoạn downtrend, nhưng biên lợi nhuận quá mỏng (+0.47% sau 8 tháng) và chưa đủ 30 lệnh.
  - Bollinger MR lỗ nhẹ **−0.55 USDT**, tốt hơn Buy-and-Hold (−52.31 USDT) nhưng không có lợi nhuận dương.

---

## 5. Điều phép đo này KHÔNG trả lời

Báo cáo này có các hạn chế cố hữu sau đây mà người đọc bắt buộc phải hiểu rõ:
1. **Funding chưa được mô hình hoá**: Dữ liệu DB hiện tại không có funding rate lịch sử. Trên thực tế, các lệnh Donchian giữ trung bình 10–12 giờ và sống qua hàng chục mốc funding (110 mốc trên IS, 36 mốc trên OOS). Chi phí funding dương/âm có thể làm thay đổi hoàn toàn PnL mỏng manh +2.33 USDT.
2. **Thanh lý chưa được mô phỏng chi tiết**: Engine chỉ đếm số lệnh có biến động bất lợi vượt quá `1/max_leverage` (`would_liquidate = 0` ở 10x leverage). Mô hình chưa xét đến liquidation fee penalty của sàn BingX.
3. **Order Flow hoàn toàn bị bỏ (Price-Only ablation)**: Các điều kiện xác nhận delta nến, CVD, taker-buy ratio và OFI của tài liệu gốc đều không thể thực hiện do BingX OHLCV không cung cấp delta.
4. **Chỉ duy nhất một sàn (BingX)**: Bảng giá và râu nến (wicks) của BingX có thể khác biệt so với Binance hay Bybit.
5. **Chỉ duy nhất một mã (BTC-USDT)**: Chưa kiểm tra trên ETH hay các Altcoins.
6. **Dữ liệu 2,37 năm (20.742 nến)**: Quãng thời gian tương đối ngắn, bao gồm 1 chu kỳ bull run và 1 đoạn phân phối/điều chỉnh, chưa đủ đại diện cho nhiều chu kỳ vĩ mô.
7. **Chưa có Walk-Forward Analysis**: Phân chia IS/OOS ở đây là 1 lát cắt tĩnh (static split 70/30), chưa kiểm tra độ ổn định tham số lăn (rolling walk-forward).
