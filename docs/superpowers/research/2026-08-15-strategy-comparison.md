# So sánh ba chiến lược đã đo — 2026-08-15

Base: `11d1c7b`, nhánh `feature/data-layer`.

Tất cả số dưới đây đo trên **cùng một bộ máy**: `run_backtest()` hiện tại, bar ngày,
T+2,5 trong `PaperBroker`, biểu phí VN, mốc **mua-và-giữ** cùng mã / cùng kỳ / cùng vốn
/ cùng phí, lọc bar `OHLC <= 0`.

> Mọi số đo `sma_cross` từng công bố TRƯỚC `4a61186` đều **không so sánh được** với bảng
> này: lúc đó `PaperBroker` chưa cưỡng chế T+2,5 và chưa có mốc mua-và-giữ. Bảng dưới là
> lần đầu cả ba chiến lược được đo trên cùng một thước.

---

## 1. Đối đầu trực tiếp — VCB, HPG, TCB (2016-01-04 → 2026-08-13, vốn 1 tỷ)

Cùng mã, cùng kỳ, cùng vốn, cùng bộ máy. Đây là phép so sánh sạch nhất.

| chiến lược | lệnh | win | PnL chiến lược | mua-và-giữ | chênh lệch | MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| `sma_cross` | 61 | 39,3% | −31.998.591 | 3.995.081.090 | −4.027.079.681 | 12,7% |
| `daily_breakout` | 72 | 36,1% | −66.945.194 | 3.995.081.090 | −4.062.026.284 | 14,4% |
| `octopus_pullback` | 25 | 56,0% | **+50.029.238** | 3.995.081.090 | −3.945.051.852 | **2,0%** |

## 2. Diện rộng — 1.551 mã, mỗi mã một lần chạy độc lập vốn 1 tỷ, rồi cộng dồn

| chiến lược | PnL chiến lược | chênh so mua-và-giữ | lệnh | mã sinh lệnh | mã thắng BH | trung vị chênh/mã |
|---|---:|---:|---:|---:|---:|---:|
| `sma_cross` | +11.360.948.249 | −3.468.750.766.392 | 21.750 | 1.513 | 526 (33,9%) | −585.867.335 |
| `daily_breakout` | +33.478.916.106 | −3.446.632.798.534 | 19.293 | 1.514 | 530 (34,2%) | −578.168.839 |
| `octopus_pullback` | −1.792.424.948 | −3.481.904.139.589 | 1.547 | 455 | 533 (34,4%) | −576.496.789 |

Mua-và-giữ trong cùng phép đo: **+3.480.111.714.641** cho cả ba.

**Không so sánh trực tiếp được về rổ mã:** `octopus_pullback` có bộ lọc thanh khoản
point-in-time ≥ 2 tỷ **bên trong chiến lược**, nên nó chỉ giao dịch 455 mã; hai chiến
lược kia giao dịch mọi thứ. Ít lệnh hơn ~14 lần là do bộ lọc, không phải do tín hiệu
hiếm hơn.

---

## Ba điều bảng này nói ra

### 1. Khoảng cách tới mốc gần như giống hệt nhau

Chênh lệch so mua-và-giữ: **−3.469 / −3.447 / −3.482 nghìn tỷ**. Ba con số nằm trong
khoảng 1% của nhau. Nghĩa là **sự khác biệt giữa ba chiến lược là nhiễu** so với khoảng
cách chung tới mốc. Không phải "cái này tốt hơn cái kia" — cả ba đều cách mốc đúng một
quãng như nhau.

Tỉ lệ mã thắng mua-và-giữ cũng vậy: 33,9% / 34,2% / 34,4%.

### 2. PnL dương KHÔNG có nghĩa là có lợi thế — và hai con số dương ở đây đáng ngờ

`sma_cross` (+11,4 tỷ) và `daily_breakout` (+33,5 tỷ) đều lãi tuyệt đối trên diện rộng.
Nhưng với `daily_breakout` đã chứng minh được khoản lãi đó là **artifact dữ liệu**: loại
245 mã không đáng tin thì +33,5 tỷ biến thành **−696 triệu** (xem `a7c6c41`).

`sma_cross` **chưa được đo lại trên rổ đã lọc** — nhiều khả năng khoản +11,4 tỷ của nó
cũng cùng nguồn gốc, nhưng đó là suy đoán, không phải số đo. Ghi lại đúng như vậy.

Thị trường VN 2016–2026 tăng rất mạnh (mua-và-giữ +3.480 tỷ trên vốn 1.551 tỷ ≈ +224%).
Bất kỳ chiến lược long-only nào đứng ngoài phần lớn thời gian đều sẽ thua nó.

### 3. Việc bỏ `sma_cross` không được số liệu ủng hộ như đã tưởng

`sma_cross` bị bỏ ngày 2026-08-15 (quyết định của chủ dự án, `11d1c7b`). Nhưng đo trên
cùng thước thì nó **không tệ hơn hai chiến lược còn lại một cách phân biệt được** — chênh
so mốc của nó nằm giữa hai cái kia.

Điều đó không có nghĩa là quyết định sai. Nó có nghĩa là: **lý do bỏ không phải "cái
này tệ hơn cái khác", mà là "không cái nào trong họ này có lợi thế"** — và đó mới là
cách nói đúng khi ghi lại quyết định.

---

## Điểm sáng duy nhất, và vì sao chưa được coi là lợi thế

`octopus_pullback` trên ba mã lớn: lãi thật (+50 triệu), win 56,0%, **MaxDD 2,0%** so
với 12,7% và 14,4% của hai cái kia — rủi ro thấp hơn 6 lần với 25 lệnh.

Chưa đủ để gọi là lợi thế, vì ba lý do:
1. **25 lệnh** trên 3 mã là cỡ mẫu quá nhỏ — đúng cái bẫy đã kết luận sai với `sma_cross`.
2. Trên diện rộng nó **lỗ** (−1,79 tỷ) và vẫn thua mốc.
3. Nó vẫn thua mua-và-giữ trên chính ba mã đó (−3,945 tỷ).

Nếu muốn theo hướng này thì câu hỏi đúng là: *MaxDD 2,0% với 1.547 lệnh trên diện rộng
có phải tính chất bền không, hay chỉ là hệ quả của việc giao dịch ít?* — đo được, chưa đo.

## Giao thức tái lập

- Đối đầu 3 mã: `uv run python -m trading.backtest --strategy <tên> --symbols VCB,HPG,TCB
  --from 2016-01-04 --to 2026-08-13 --tf 1d --capital 1000000000`
  (`sma_cross` đã bị gỡ khỏi `STRATEGIES` nên phải gọi trực tiếp `SmaCrossStrategy()`).
- Diện rộng: `scripts/measure_strategy.py --strategy <tên>` (gộp từ hai script
  `measure_daily_breakout.py` + `measure_octopus.py`, kiểm chứng tái lập đúng số của cả
  hai). Với `sma_cross` chạy một lần bằng script tạm cùng giao thức (mỗi mã một
  `run_backtest()` riêng, vốn 1e9, cộng dồn) — không thêm script vào repo, và nay
  `sma_cross` cũng không còn trong `STRATEGIES` nên không chạy được qua script này.
