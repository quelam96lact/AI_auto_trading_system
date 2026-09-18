# Báo cáo Đợt 45 — Đo lệch khung nến giữa Backtest và Production

- **Ngày thực hiện:** 15/09/2026.
- **Người thực hiện:** Antigravity (theo Brief đợt 45 của Claude).
- **Mục tiêu:**
  1. Task 1: Lập bảng đơn vị mọi tham số có tính chất cửa sổ thời gian trong `OctopusPullbackStrategy`, đối chiếu ý nghĩa nến NGÀY vs nến 5 PHÚT (giả định 4,0h = 48 nến 5m/phiên). Chỉ rõ tham số nào đã được Gói K sửa, tham số nào chưa.
  2. Task 2: Viết công cụ `scripts/compare_timeframe_mismatch.py` đo 3 mã production `HPG, IJC, AAA` trong khoảng `2026-06-01 -> 2026-09-12`:
     - Bảng 1: Số nến ngày, tín hiệu ngày, số nến 5m, tín hiệu 5m, lệnh giấy thật (kèm dòng TỔNG).
     - Bảng 2: Bảng chẩn đoán từng vế điều kiện trên nến 5m (warmup, xu hướng, pullback, crossover, macd, đảo chiều, thanh khoản, hợp cả vế).
     - 5 tiêu chí kiểm chứng (khớp direct count DB, khớp count orders, đối chiếu `_default_strategy()`, chạy 2 lần tất định, suite pass mốc 748, ruff sạch, cổng cứng VN khớp tuyệt đối).
  3. Task 3: Bảng quyết định "Ba lựa chọn" (A. Engine chạy nến ngày, B. Hiệu chỉnh nến 5m, C. Giữ nguyên) với chi phí, điều phải chấp nhận và số liệu thực nghiệm cụ thể đặt lên bàn chủ dự án.

---

## 1. Task 1 — Bảng đơn vị tham số: Nến NGÀY so với Nến 5 PHÚT

### 1.1. Giả định quy đổi thời gian giao dịch Việt Nam
- Giờ giao dịch chuẩn tại VN: 09:15–11:30 (sáng, 2,25 giờ) và 13:00–14:45 (chiều, 1,75 giờ) $\rightarrow$ Tổng cộng 4,0 giờ giao dịch khớp lệnh liên tục.
- Cộng cả phiên ATC (~15 phút) là ~4,25 giờ.
- **Giả định quy đổi chuẩn tắc của Brief đợt 45:** Dùng **4,0 giờ = 240 phút = 48 nến 5 phút mỗi phiên giao dịch**.

### 1.2. Bảng đối chiếu chi tiết toàn bộ tham số của `OctopusPullbackStrategy`

Mã nguồn đối chiếu: [`trading/strategies/octopus_pullback.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/trading/strategies/octopus_pullback.py#L90-L160).

| Tham số | Giá trị | Đơn vị theo mã nguồn | Ý nghĩa trên nến NGÀY | Ý nghĩa thật trên nến 5 PHÚT (48 bar/phiên) | Trạng thái Gói K (06/09) |
|---|---|---|---|---|---|
| `ema_trend` | 200 | số **bar** | 200 phiên $\approx$ **10 tháng** (chu kỳ xu hướng dài hạn kinh điển) | 200 bar $\times$ 5m = 1000 phút = 16,67h $\approx$ **4,17 phiên** (~4 ngày) | **CHƯA SỬA** (vẫn đếm theo bar) |
| `ema_fast` | 9 | số **bar** | 9 phiên $\approx$ **1,8 tuần** (~2 tuần) | 9 bar $\times$ 5m = 45 phút = 0,75h $\approx$ **0,19 phiên** (< 1/5 phiên) | **CHƯA SỬA** (vẫn đếm theo bar) |
| `ema_slow` | 21 | số **bar** | 21 phiên $\approx$ **1 tháng** (chu kỳ trung hạn ngắn) | 21 bar $\times$ 5m = 105 phút = 1,75h $\approx$ **0,44 phiên** (< nửa phiên) | **CHƯA SỬA** (vẫn đếm theo bar) |
| `macd_fast` | 12 | số **bar** | 12 phiên $\approx$ **2,4 tuần** | 12 bar $\times$ 5m = 60 phút = 1,0h $\approx$ **0,25 phiên** (1/4 phiên) | **CHƯA SỬA** (vẫn đếm theo bar) |
| `macd_slow` | 26 | số **bar** | 26 phiên $\approx$ **5,2 tuần** (~1,2 tháng) | 26 bar $\times$ 5m = 130 phút = 2,17h $\approx$ **0,54 phiên** (~nửa phiên) | **CHƯA SỬA** (vẫn đếm theo bar) |
| `macd_signal` | 9 | số **bar** | 9 phiên $\approx$ **1,8 tuần** | 9 bar $\times$ 5m = 45 phút = 0,75h $\approx$ **0,19 phiên** | **CHƯA SỬA** (vẫn đếm theo bar) |
| `pullback_window` | 5 | số **bar** (deque) | 5 phiên = **1 tuần** (nhịp chỉnh trong 1 tuần) | 5 bar $\times$ 5m = 25 phút $\approx$ **0,10 phiên** (nhịp chỉnh trong 25 phút) | **CHƯA SỬA** (vẫn đếm theo bar) |
| `pullback_red` | 2 | số **nến đỏ** | $\ge 2$ ngày giảm trong 5 ngày gần nhất | $\ge 2$ nến 5m giảm trong 25 phút gần nhất | **CHƯA SỬA** (vẫn đếm theo bar) |
| `atr_period` | 14 | số **bar** | 14 phiên $\approx$ **2,8 tuần** (biến động giá ngày 3 tuần) | 14 bar $\times$ 5m = 70 phút = 1,17h $\approx$ **0,29 phiên** (biến động giá 70 phút) | **CHƯA SỬA** (vẫn đếm theo bar) |
| `tp_atr_mult` | 2.0 | hệ số không thứ nguyên | Chốt lời ở $+ 2 \times \text{ATR}_{\text{daily}}$ (lãi kỳ vọng **+4% đến +10%**) | Chốt lời ở $+ 2 \times \text{ATR}_{\text{5m}}$ (lãi kích hoạt ở **+0.4% đến +1.0%**) | **CHƯA SỬA** |
| `liquidity_window` | 20 | số **ngày đã đóng** | 20 phiên $\approx$ **1 tháng** | 20 phiên $\approx$ **1 tháng** (nhờ `DailyLiquidityTracker`) | **ĐÃ SỬA** (Gói K gom theo ngày) |
| `min_avg_value_20` | 2 tỷ VNĐ | VNĐ / ngày | Bình quân $\ge$ 2 tỷ VNĐ / ngày | Bình quân $\ge$ 2 tỷ VNĐ / ngày | **ĐÃ SỬA** (Gói K tính theo ngày) |
| `warmup_bars` | 201 | số **bar** | 201 phiên $\approx$ **10 tháng** | 201 bar 5m $\approx$ **4,19 phiên** (nhưng tracker đòi 20 ngày) | **CHƯA SỬA** (thuộc tính vẫn báo 201 bars) |

*(Ghi chú: Không có tham số nào rơi vào trạng thái "CHƯA XÁC ĐỊNH". Toàn bộ 13 tham số đều được chỉ định rõ ràng và tường minh trong mã nguồn).*

### 1.3. Nhận định cốt lõi từ Task 1
1. **Biến dạng chỉ báo kỹ thuật:**
   - Khi chuyển từ nến ngày sang nến 5 phút mà giữ nguyên giá trị số học, chỉ báo `EMA(200)` không còn đo xu hướng vĩ mô/dài hạn 10 tháng nữa, mà biến thành đường trung bình trượt của **4,17 phiên** (~4 ngày).
   - Bộ dao động `MACD(12, 26, 9)` và bộ giao cắt `EMA(9) / EMA(21)` từ chỗ đo động lượng tuần/tháng bị co lại thành các dao động chớp nhoáng trong **45 phút đến 2 giờ**.
   - Bộ lọc `pullback_window = 5` và `pullback_red = 2` trên nến ngày là nhịp tích luỹ điều chỉnh lành mạnh trong 1 tuần (5 ngày), nhưng trên nến 5m lại là việc giá giảm trong **25 phút** gần nhất!
2. **Hiệu ứng Gói K (06/09):**
   - Gói K phát hiện engine bị câm vì bộ lọc thanh khoản đếm 20 bar 5m (100 phút) chỉ có vài trăm triệu nên bị lọc sạch.
   - Gói K đã tạo `DailyLiquidityTracker` để gom giá trị theo ngày giao dịch đã đóng $\ge 2$ tỷ VNĐ.
   - Tuy nhiên, **Gói K chỉ sửa duy nhất bộ lọc thanh khoản**. Toàn bộ các chỉ báo kỹ thuật còn lại (EMA, MACD, Pullback, ATR) vẫn tiếp tục đếm theo bar 5 phút!

---

## 2. Task 2 — Thực nghiệm đo tín hiệu: Nến NGÀY so với Nến 5 PHÚT

Công cụ đo đạc được triển khai tại [`scripts/compare_timeframe_mismatch.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/compare_timeframe_mismatch.py).
Khoảng thời gian khảo sát: **2026-06-01 00:00:00+07:00** đến **2026-09-12 23:59:59+07:00** (khớp lệnh múi giờ VN `Asia/Ho_Chi_Minh`).
Đối tượng khảo sát: Ba mã production `HPG`, `IJC`, `AAA`.

### 2.1. Bảng 1: So sánh tín hiệu và lệnh giấy thật (§2.2)

*(In nguyên văn từ terminal khi chạy công cụ đo)*:

```
--- BẢNG 1: TÍN HIỆU NẾN NGÀY SO VỚI NẾN 5 PHÚT & LỆNH GIẤY THẬT (§2.2) ---
Mã     | Số nến ngày  | Tín hiệu ngày (bull/bear) | Số nến 5m    | Tín hiệu 5m (bull/bear) | Lệnh giấy thật
---------------------------------------------------------------------------------------------------------
HPG    | 72           | 0 bull / 0 bear           | 3254         | 5 bull / 0 bear         | 0             
IJC    | 72           | 0 bull / 0 bear           | 3232         | 3 bull / 0 bear         | 7             
AAA    | 72           | 0 bull / 0 bear           | 3125         | 9 bull / 0 bear         | 5             
---------------------------------------------------------------------------------------------------------
TỔNG   | 216          | 0 bull / 0 bear           | 9611         | 17 bull / 0 bear        | 12            
```

### 2.2. Bảng 2: Chẩn đoán từng vế điều kiện trên nến 5 phút (§2.3)

*(In nguyên văn từ terminal khi chạy công cụ đo)*:

```
--- BẢNG 2: CHẨN ĐOÁN TỪNG VẾ ĐIỀU KIỆN TRÊN NẾN 5 PHÚT (§2.3) ---
Mã    | Số bar 5m  | Warmup đủ  | Xu hướng (close>EMA200) | Pullback (>=2 đỏ)  | Crossover (EMA9^21) | MACD hist>0  | Đảo chiều (Cross&MACD) | Thanh khoản (>=2 tỷ) | HỢP CẢ VẾ (Signal)
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
HPG   | 3254       | 3254       | 1403 (43.1%)            | 1429 (43.9%)       | 76 (2.3%)           | 1492 (45.9%) | 19 (0.6%)              | 3254 (100.0%)        | 5 (0.15%)
IJC   | 3232       | 3232       | 1515 (46.9%)            | 1659 (51.3%)       | 68 (2.1%)           | 1380 (42.7%) | 12 (0.4%)              | 3232 (100.0%)        | 3 (0.09%)
AAA   | 3125       | 3125       | 1943 (62.2%)            | 1314 (42.0%)       | 82 (2.6%)           | 1748 (55.9%) | 31 (1.0%)              | 3125 (100.0%)        | 9 (0.29%)
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
TỔNG  | 9611       | 9611       | 4861 (50.6%)            | 4402 (45.8%)       | 226 (2.4%)          | 4620 (48.1%) | 62 (0.6%)              | 9611 (100.0%)        | 17 (0.18%)
```

### 2.3. Phân tích chẩn đoán chuyên sâu
1. **Tại sao nến ngày cho 0 tín hiệu?**
   - Trong giai đoạn từ tháng 06 đến tháng 09/2026, thị trường cơ sở diễn biến phân hoá và giằng co.
   - Để nến ngày phát tín hiệu `bull`, cần đồng thời:
     - Giá đóng cửa trên `EMA(200)` nến ngày (xu hướng 10 tháng).
     - Trong 5 ngày gần nhất phải có ít nhất 2 ngày giảm giá (pullback).
     - Đúng ngày hiện tại: `EMA(9)` phải cắt LÊN `EMA(21)` và `MACD hist > 0`.
   - Cả 3 mã `HPG, IJC, AAA` trong 72 phiên này không có bất kỳ phiên nào hội tụ đầy đủ cả 4 điều kiện khắt khe này. Tín hiệu trên nến ngày của cả rổ 3 mã là **con số 0 tròn trĩnh**!
2. **Tại sao nến 5 phút lại cho 17 tín hiệu?**
   - `EMA(200)` nến 5m chỉ là 4 ngày nên giá liên tục cắt qua lại (thoả mãn ở 50.6% số bar).
   - `Pullback` 2 nến đỏ trong 25 phút xảy ra thường xuyên (45.8% số bar).
   - Tuy nhiên, điều kiện **giao cắt EMA9 cắt lên EMA21** là một sự kiện tức thời (chỉ xảy ra đúng 1 bar duy nhất khi giao cắt xuất hiện), chỉ chiếm **2.4% số bar** (226 bar trên tổng số 9,611 bar).
   - Khi giao cắt này xảy ra và yêu cầu thêm `MACD hist > 0`, số bar đảo chiều chỉ còn **62 bar (0.6%)**.
   - Khi hợp thêm vế `close > EMA200` (xu hướng 4 ngày) và `pullback 2 nến đỏ`, tín hiệu bị lọc xuống chỉ còn **17 bar (0.18%)**.
3. **Đối chiếu với số Lệnh Giấy Thật (12 lệnh trong `orders`):**
   - `HPG`: 0 lệnh giấy thật $\rightarrow$ Khớp với việc lệnh giấy không được kích hoạt/fill trong kỳ.
   - `IJC`: 7 lệnh giấy thật (4 BUY, 3 SELL).
   - `AAA`: 5 lệnh giấy thật (3 BUY, 2 SELL).
   - Tổng cộng có 12 lệnh giấy thật (gồm 7 lệnh BUY và 5 lệnh SELL chốt lời/cắt lỗ).
   - Số lệnh BUY thực tế (7 lệnh) thấp hơn số tín hiệu 5m đo được (17 tín hiệu) vì engine áp dụng cơ chế quản lý vị thế: **khi đã có vị thế (`held > 0`), engine không mua thêm** (`crossover == 'bull' and held == 0`). Ngoài ra, engine chỉ chạy trong các phiên thực tế khi collector hoạt động.

---

### 2.4. Năm Tiêu Chí Kiểm Chứng Task 2 (§2.4)

#### Tiêu chí 1: Số nến ngày và nến 5m khớp truy vấn `count(*)` trực tiếp trên DB

Truy vấn SQL thực hiện:
```sql
SET TimeZone='Asia/Ho_Chi_Minh';

-- 1. bars_daily
SELECT symbol, count(*) FROM bars_daily 
WHERE ts >= '2026-06-01 00:00:00+07:00' AND ts <= '2026-09-12 23:59:59+07:00' AND symbol IN ('HPG', 'IJC', 'AAA')
GROUP BY symbol ORDER BY symbol;

-- 2. bars (5m)
SELECT symbol, count(*) FROM bars 
WHERE ts >= '2026-06-01 00:00:00+07:00' AND ts <= '2026-09-12 23:59:59+07:00' AND symbol IN ('HPG', 'IJC', 'AAA')
GROUP BY symbol ORDER BY symbol;
```

Kết quả đối chiếu:
- `HPG`: bars_daily = **72**, bars (5m) = **3254** $\rightarrow$ Khớp tuyệt đối 100%.
- `IJC`: bars_daily = **72**, bars (5m) = **3232** $\rightarrow$ Khớp tuyệt đối 100%.
- `AAA`: bars_daily = **72**, bars (5m) = **3125** $\rightarrow$ Khớp tuyệt đối 100%.
- Tổng: bars_daily = **216**, bars (5m) = **9611** $\rightarrow$ Khớp tuyệt đối 100%.

#### Tiêu chí 2: Số lệnh giấy khớp `SELECT count(*) FROM orders`

Truy vấn SQL thực hiện:
```sql
SET TimeZone='Asia/Ho_Chi_Minh';
SELECT symbol, count(*) FROM orders 
WHERE ts >= '2026-06-01 00:00:00+07:00' AND ts <= '2026-09-12 23:59:59+07:00' AND symbol IN ('HPG', 'IJC', 'AAA')
GROUP BY symbol ORDER BY symbol;
```

Kết quả đối chiếu:
- `HPG`: orders = **0** $\rightarrow$ Khớp tuyệt đối.
- `IJC`: orders = **7** (4 BUY, 3 SELL) $\rightarrow$ Khớp tuyệt đối.
- `AAA`: orders = **5** (3 BUY, 2 SELL) $\rightarrow$ Khớp tuyệt đối.
- Tổng: **12** lệnh $\rightarrow$ Khớp tuyệt đối 100%.

#### Tiêu chí 3: Xác nhận đã đối chiếu `_default_strategy()`

Mã nguồn trong [`trading/engine/main.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/trading/engine/main.py#L35-L42):
```python
def _default_strategy():
    from trading.strategies.octopus_pullback import OctopusPullbackStrategy
    return OctopusPullbackStrategy()
```
Trong công cụ đo [`scripts/compare_timeframe_mismatch.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/compare_timeframe_mismatch.py#L125), chiến lược được khởi tạo bằng `strat = OctopusPullbackStrategy()`, không truyền tham số override nào khác.
Test unit [`test_1_strategy_parameters_match_default_strategy`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_compare_timeframe_mismatch.py#L26-L44) đã assert từng trường tham số (`qty=100`, `ema_fast=9`, `ema_slow=21`, `ema_trend=200`, `macd_slow=26`, `macd_signal=9`, `pullback_red=2`, `pullback_window=5`, `tp_atr_mult=2.0`, `min_avg_value_20=2_000_000_000.0`, `liquidity_window=20`, `warmup_bars=201`) giữa engine thật và công cụ đo $\rightarrow$ Khớp 100%.

#### Tiêu chí 4: Chạy hai lần tất định (Deterministic Reproducibility)

Chạy 2 lần độc lập liên tiếp công cụ đo trên cùng tập dữ liệu:
- Lần 1: `counts_daily = {'HPG': 72, 'IJC': 72, 'AAA': 72}`, `signals_daily = {all: 0}`, `counts_5m = {'HPG': 3254, 'IJC': 3232, 'AAA': 3125}`, `signals_5m = {'HPG': 5, 'IJC': 3, 'AAA': 9}`.
- Lần 2: Kết quả giống hệt 100% lần 1.
- Unit test [`test_3_deterministic_reproducibility_on_real_db`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_compare_timeframe_mismatch.py#L75) đã khẳng định tính tất định này.

#### Tiêu chí 5: Kiểm tra Suite Pass, Ruff sạch, Cổng cứng VN 4 con số
- **Test suite:** **752 passed** (vượt mốc 748, bổ sung 4 test mới trong `tests/test_compare_timeframe_mismatch.py`).
- **Ruff check:** Clean 100% (`All checks passed!`).
- **Cổng cứng VN:**
  ```
  uv run python scripts/measure_strategy.py --strategy octopus_pullback --exclude-file exclusions.txt
  -1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã
  ```
  *(Khớp tuyệt đối 4 con số mốc).*

---

## 3. Task 3 — Bảng quyết định cho Chủ Dự Án ("Ba Lựa Chọn")

Đặt lên bàn chủ dự án ba phương án khả dĩ, mỗi phương án nêu rõ bản chất, chi phí kỹ thuật, điều phải chấp nhận và căn cứ số liệu thực nghiệm từ Task 2.
**Không có khuyến nghị chủ quan — đây là quyết định chiến lược của chủ dự án.**

| Lựa chọn | Nghĩa là gì | Chi phí kỹ thuật | Phải chấp nhận điều gì | Căn cứ số liệu thực nghiệm Task 2 |
|---|---|---|---|---|
| **A. Engine chạy nến ngày** | Engine chuyển sang tiêu thụ `bars_daily`. Mỗi ngày chỉ chạy một lần sau giờ đóng cửa (15:05), đưa ra tối đa 1 quyết định/ngày/mã. | **Thấp:** Sửa feed nạp vào engine từ stream `bars` sang bảng/stream nến ngày đóng; cấu hình cron/timer kích hoạt lúc 15:05. | **1.** Mất hoàn toàn khả năng phản ứng trong phiên.<br>**2.** Toàn bộ hạ tầng collector realtime, độ trễ thấp, streaming qua NATS xây dựng từ đợt 31–44 trở thành thừa.<br>**3.** Số lượng tín hiệu cực hiếm: rổ 3 mã chỉ có 0 tín hiệu trong hơn 3 tháng! | Cả 3 mã `HPG, IJC, AAA` trong 72 phiên (216 nến ngày) có **0 tín hiệu**. Backtest toàn bộ thị trường 439 mã cho **1,514 lệnh** qua nhiều năm, tức trung bình chỉ ~3.4 lệnh/mã/năm. Nếu chỉ chạy 3 mã thì engine gần như câm lặng quanh năm. |
| **B. Hiệu chỉnh lại cho nến 5 phút** | Giữ nguyên kiến trúc nến 5 phút và hạ tầng realtime. Tìm kiếm và tối ưu lại toàn bộ bộ tham số (EMA, MACD, Pullback, ATR, Take Profit) dành riêng cho khung thời gian 5 phút. | **Rất cao:** Phải xây dựng lại toàn bộ pipeline backtest trên nến 5m cho thị trường cơ sở VN; tuân thủ kỷ luật đợt 38 (đối chứng bước ngẫu nhiên) và đợt 41 (hiệu chỉnh đa phép kiểm Holm-Bonferroni / max-statistic). | **1.** Toàn bộ kết quả backtest cổng cứng hiện có (`-1.615 tỷ \| 1,514 lệnh`) trở nên **vô giá trị** vì nó chỉ đo nến ngày.<br>**2.** Nguy cơ data snooping / overfitting trên khung 5 phút rất cao.<br>**3.** Chi phí giao dịch (thuế 0.1% + phí) trên thị trường VN rất lớn đối với chiến lược tần suất cao trong ngày. | Trên nến 5m, tín hiệu `bull` xuất hiện **17 lần** trong 9,611 bar (tần suất ~0.18%), dẫn tới **12 lệnh giấy thật** trong 3 tháng. Nhịp chốt lời TP dựa trên `ATR(14)` nến 5m chỉ tương đương biến động 0.4% - 1.0%, rất dễ bị triệt tiêu bởi thuế phí giao dịch cơ sở. |
| **C. Giữ nguyên** | Chấp nhận sự thật: Engine production đang chạy một chiến lược **hoàn toàn khác** với thứ đã được backtest trên nến ngày. | **0:** Không cần sửa đổi mã nguồn hay kiến trúc hệ thống hiện tại. | **1.** Cổng cứng VN (`measure_strategy.py`) tiếp tục làm cổng hồi quy kỹ thuật tốt (chống gãy logic), nhưng **không phải là bằng chứng khoa học** về hiệu quả của engine thật.<br>**2.** Chấp nhận hệ thống vận hành thực tế mà không có mô hình backtest định lượng hỗ trợ. | Số liệu Task 2 cho thấy sự lệch pha rõ rệt: Backtest nến ngày của 3 mã cho **0 tín hiệu**, trong khi Engine thật trên nến 5m phát sinh **17 tín hiệu** và sinh ra **12 lệnh giấy**. Hai hệ thống vận hành với hai cơ chế dao động hoàn toàn khác nhau. |

---

## 4. Kết luận & Đường dẫn tệp liên quan

1. **Công cụ đo đạc thực nghiệm:** [`scripts/compare_timeframe_mismatch.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/compare_timeframe_mismatch.py).
2. **Bộ kiểm thử tự động:** [`tests/test_compare_timeframe_mismatch.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_compare_timeframe_mismatch.py).
3. **Báo cáo nghiên cứu đầy đủ:** [`docs/superpowers/research/2026-09-15-dot-45-lech-khung-nen.md`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/docs/superpowers/research/2026-09-15-dot-45-lech-khung-nen.md).

---

## Ghi chú của người kiểm chứng (Claude, 18/09/2026)

**Đợt này đạt.** Tôi chạy lại và mọi con số tái lập đúng từng chữ số: `72 / 72 / 72` nến ngày,
`3254 / 3232 / 3125` nến 5 phút, `0` tín hiệu ngày, `17` tín hiệu 5 phút, `12` lệnh giấy. Số
nến tôi tự truy vấn thẳng DB, khớp.

### 1. Số liệu bác bỏ chính khung lập luận của brief tôi viết

Brief 45 §0.2 tôi viết: *"Engine gần như câm"* và §0.3 quy nó cho việc lệch khung nến. Ngụ ý
là tham số hiệu chỉnh theo phiên chạy trên nến 5 phút làm chiến lược khắt khe quá mức.

**Ngược lại:**

```
nến ngày   :  0 tín hiệu / 216 nến
nến 5 phút : 17 tín hiệu / 9.611 nến
```

Nến 5 phút **hoạt động nhiều hơn**, không phải ít hơn. Nếu chuyển engine sang nến ngày —
lựa chọn A — rổ ba mã này sẽ cho **không một lệnh nào** trong ba tháng.

Nên quan hệ nhân quả tôi giả định là sai. Con số `7 lệnh / 30 ngày` không đến từ lệch khung.
Nó đến từ việc chiến lược vốn rất chọn lọc (`1.514 lệnh / 439 mã` trên toàn bộ kỳ backtest,
tức khoảng `3,4 lệnh mỗi mã`) nhân với một **rổ chỉ ba mã**. Với rổ đó, thưa là điều phải xảy ra.

### 2. Nhưng bản thân sự lệch khung vẫn là vấn đề thật, và bảng Task 1 vẫn đứng

Mười một trên mười ba tham số vẫn đếm theo **bar**, nên trên nến 5 phút chúng mang nghĩa hoàn
toàn khác:

```
ema_trend  200 bar : 200 phiên (~10 tháng)  ->  16,7 giờ (~4,2 phiên)
ema_slow    21 bar :  21 phiên (~1 tháng)   ->  1,75 giờ (<nửa phiên)
atr_period  14 bar :  14 phiên (~3 tuần)    ->  70 phút
```

`tp_atr_mult = 2.0` trên ATR 70 phút cho biên chốt lời **0,4%–1,0%**, trong khi phí và thuế
cơ sở VN một vòng đã ăn phần lớn khoảng đó. Đây là vấn đề độc lập với chuyện engine thưa lệnh,
và nó vẫn cần một quyết định.

### 3. Điều tôi phải nói rõ về cổng cứng

Kết luận của brief §0.4 **giữ nguyên**: cổng cứng VN là backtest trên `bars_daily`, nó là một
cổng hồi quy tốt và đã làm đúng việc đó suốt chín đợt, **nhưng nó không mô tả thứ engine đang
chạy**. Số liệu đợt này làm điều đó rõ hơn nữa: cùng ba mã, cùng chiến lược, cùng kỳ — nến
ngày `0` tín hiệu, nến 5 phút `17`. Hai thế giới khác nhau.

### 4. Hai ghi chú nhỏ

- Bảng `orders` trong cùng cửa sổ còn có `HII: 5` (mã đã bỏ khỏi cấu hình ngày 10/09 — lịch sử
  hợp lệ) và **`TEST: 1`** — một dòng mã thử nằm trong bảng lệnh production. Không ảnh hưởng
  kết quả đợt này vì phép đo lọc theo ba mã, nhưng nên dọn.
- Báo cáo ghi "752 passed (vượt mốc 748, bổ sung 4 test mới)" — đúng, tôi chạy lại ra 752.

### 5. Kết luận

Ba lựa chọn ở Task 3 vẫn là quyết định của chủ dự án, nhưng căn cứ đã đổi: **lựa chọn A không
phải "chậm hơn nhưng đúng hơn" — nó là "không giao dịch gì cả" với rổ ba mã hiện tại.** Nếu
chọn A thì phải mở rộng rổ mã cùng lúc, nếu không engine sẽ im hoàn toàn.