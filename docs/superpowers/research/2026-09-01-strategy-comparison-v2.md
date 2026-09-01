# Đo lại lợi thế chiến lược trên dữ liệu đã sạch — 2026-09-01 (v2)

Brief 2026-09-01 (đợt 4). Đo trên `bars_daily` hiện tại: **2.982.903 dòng, 1.554
mã, 2016-01-03 → 2026-08-28** (nạp lại toàn bộ 30/08; bảng 15/08 chỉ có
2.969.328 dòng). Cùng bộ máy `run_backtest()`: bar ngày, T+2,5 trong
`PaperBroker`, biểu phí VN, mốc mua-và-giữ cùng mã / cùng kỳ / cùng vốn / cùng
phí, lọc bar `OHLC <= 0`. Mỗi mã một lần chạy độc lập vốn 1 tỷ rồi cộng dồn
(không danh mục chung — tránh bẫy sizing).

## 1. Đối đầu trực tiếp — VCB, HPG, TCB (2016-01-04 → 2026-08-13, vốn 1 tỷ)

> **ĐÍNH CHÍNH 2026-09-01 — Claude audit.** Bản đầu của mục này ghi 113/103/23
> lệnh, mua-và-giữ `11.844.464.091`, và giải thích rằng đợt nạp lại 30/08 đã
> back-adjust khiến mốc BH gấp ~3 lần và sma_cross nhảy từ 61 lên 113 lệnh.
> **Không tái lập được.** Chạy lại đúng tham số:
>
> ```
> uv run python -m trading.backtest --strategy <X> --symbols VCB,HPG,TCB \
>     --from 2016-01-04 --to 2026-08-13 --tf 1d --capital 1000000000
> ```
>
> ra đúng bảng dưới. Lời giải thích "back-adjust" nghe hợp lý nhưng mô tả một
> hiện tượng **không tồn tại** — kiểu sai khó thấy nhất, vì nó tự vá lỗ hổng
> logic của chính nó. Số dưới đây là số đo lại, không phải số báo cáo.

| chiến lược | lệnh | win | PnL | mua-và-giữ | chênh lệch | MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| `sma_cross` | 61 | 39,3% | −31.998.591 | 3.948.143.113 | −3.980.141.704 | 12,7% |
| `daily_breakout` | 72 | 36,1% | −66.945.194 | 3.948.143.113 | −4.015.088.308 | 14,4% |
| `octopus_pullback` | 25 | 56,0% | +50.029.238 | 3.948.143.113 | −3.898.113.875 | 2,0% |

Bảng 15/08 (cùng ba mã, dữ liệu trước đợt nạp lại):

| chiến lược | lệnh | win | PnL | mua-và-giữ | MaxDD |
|---|---:|---:|---:|---:|---:|
| `sma_cross` | 61 | 39,3% | −31.998.591 | 3.995.081.090 | 12,7% |
| `daily_breakout` | 72 | 36,1% | −66.945.194 | 3.995.081.090 | 14,4% |
| `octopus_pullback` | 25 | 56,0% | +50.029.238 | 3.995.081.090 | 2,0% |

**Điều bảng này thật sự nói ra:** PnL, số lệnh, win rate và MaxDD của cả ba
**không đổi một đồng nào** so với 15/08. Chỉ mốc mua-và-giữ đổi, và chỉ **−1,2%**
(3.995.081.090 → 3.948.143.113). Đợt nạp lại 30/08 gần như không đụng tới chuỗi
giá của ba mã lớn này — hợp lý, vì VCB/HPG/TCB là những mã ít khả năng nằm trong
nhóm chia tách chưa điều chỉnh. Mọi so sánh ở mục 1 vì thế giữ nguyên.

## 2. Diện rộng — hai rổ

### 2a. Rổ đầy đủ (1.554 mã, không loại trừ)

| chiến lược | PnL | chênh so mua-và-giữ | lệnh | mã sinh lệnh | mã thắng BH | trung vị chênh/mã |
|---|---:|---:|---:|---:|---:|---:|
| `sma_cross` | +11.389.511.350 | −3.500.510.886.356 | 21.750 | 1.515 | 33,9% | −582.794.852 |
| `daily_breakout` | +33.342.004.538 | −3.478.558.393.168 | 19.304 | 1.514 | 34,0% | −555.806.308 |
| `octopus_pullback` | −1.786.944.664 | −3.513.687.342.370 | 1.547 | 455 | 34,2% | −559.537.634 |

Bảng 15/08 (cùng rổ đầy đủ, dữ liệu cũ): sma_cross +11.360.948.249 (21.750
lệnh), daily_breakout +33.478.916.106 (19.293 lệnh), octopus −1.792.424.948
(1.547 lệnh). **Các con số gần như không đổi sau đợt nạp lại** — rổ đầy đủ cho
kết quả ổn định bất chấp back-adjust.

### 2b. Rổ đã lọc (1.308 mã — loại 246 mã không đáng tin)

Danh sách loại trừ dựng LẠI trên dữ liệu hiện tại bằng
`check_price_adjustment.py --emit-exclusions` (KHÔNG dùng lại file 245 mã của
15/08): **246 mã** (chia tách chưa điều chỉnh: 50, bar rác >= 5%: 209, trùng
nhau) — so với 245 mã lần trước, chênh +1, không phải phát hiện lớn về chất
lượng đợt nạp lại.

| chiến lược | PnL | chênh so mua-và-giữ | lệnh | mã sinh lệnh | mã thắng BH | trung vị chênh/mã |
|---|---:|---:|---:|---:|---:|---:|
| `sma_cross` | **−14.086.713.488** | −1.911.674.195.391 | 18.391 | 1.283 | 34,6% | −507.494.779 |
| `daily_breakout` | **−726.392.997** | −1.898.313.874.900 | 16.198 | 1.276 | 34,7% | −501.479.663 |
| `octopus_pullback` | **−1.615.319.902** | −1.899.202.801.806 | 1.514 | 439 | 35,4% | −492.942.447 |

**Câu trả lời thẳng cho câu hỏi của brief:** khoản **+11,4 tỷ của `sma_cross`
CÓ biến mất trên rổ đã lọc** — từ +11.389.511.350 xuống **−14.086.713.488**
(thay đổi −25,5 tỷ), y hệt `daily_breakout` (+33,5 tỷ → −0,7 tỷ). Cả hai khoản
"lãi" khổng lồ trên rổ đầy đủ đều là **artifact dữ liệu**: nằm trọn trong số mã
còn chia tách chưa điều chỉnh. Lỗ hổng 1 của brief (sma_cross chưa từng đo trên
rổ đã lọc) đã được đóng: **sma_cross cũng không có lợi thế, đúng như dự đoán
của research 15/08.**

Trên rổ đã lọc, cả ba chiến lược đều **thua mua-và-giữ** với chênh lệch ~1,9
nghìn tỷ (mốc BH của rổ lọc thấp hơn rổ đầy đủ vì loại bỏ các mã giá nhảy ảo).
Tỷ lệ mã thắng BH chỉ ~34-35% — tức khoảng 2/3 số mã thua mốc.

## 3. Kết luận — CHỌN KẾT CỤC 2

**Không có chiến lược nào trong ba chiến lược thắng mua-và-giữ trên rổ đã lọc.**

> **Engine chỉ chạy paper để hoàn thiện hạ tầng — không bật tiền thật.**

Đây là kết cục hợp lệ, không phải thất bại — và đúng như bảng 15/08 dự đoán.
Việc đổi `engine/main.py:71` (nếu sau này có chiến lược khác được chứng minh)
là task riêng, không thuộc brief này. `sma_cross` giờ đã được đo trên rổ sạch
và nằm cùng họ: không lợi thế, y hệt hai chiến lược kia — việc gỡ nó khỏi
registry đo lường ngày 15/08 không cần đảo ngược (nó có mặt lại chỉ để đo).

### `octopus_pullback` MaxDD 2,0%: còn giữ được không?

Trên dữ liệu hiện tại: **MaxDD 2,0%** (25 lệnh, rổ đối đầu) — **không đổi** so
với 15/08, và vẫn thấp hơn 6-7 lần so với sma_cross 12,7% và daily_breakout
14,4%, nhưng **tình trạng cỡ mẫu nhỏ vẫn y hệt** (25 lệnh là chưa đủ để gọi là
lợi thế thống kê; khoảng tin cậy
rộng). Điểm sáng duy nhất trong bảng cũ vẫn là điểm sáng duy nhất trong bảng
mới — **chưa có gì thay đổi về kết luận**: rủi ro thấp là thật nhưng chưa đủ
bằng chứng để gọi là lợi thế. Nếu muốn theo đuổi, cần đo thêm trên cỡ mẫu lớn
hơn (nhiều mã hơn hoặc khung nhỏ hơn 1d) — ngoài phạm vi brief này.

## Ghi chú đo lường

- `octopus_pullback` tự lọc thanh khoản ≥ 2 tỷ trong chiến lược (748/1.308 mã
  đủ thanh khoản trên rổ đã lọc) nên **không so trực tiếp được về rổ mã** với
  hai chiến lược kia — số lệnh ít hơn ~12 lần là do bộ lọc, không phải do tín
  hiệu hiếm hơn.
- Số đo `sma_cross` công bố trước `4a61186` (PaperBroker chưa cưỡng chế T+2,5,
  chưa có mốc mua-và-giữ) không so sánh được — bảng này chỉ so với 15/08 trở đi.
- Phép đo chỉ ĐỌC `bars_daily`, không ghi gì vào DB.

## Kiểm chứng độc lập (Claude audit, 2026-09-01 13:2x–13:38)

Không nhận số theo lời khai. Đã tự chạy lại:

| Kiểm | Kết quả |
|---|---|
| Đối đầu 3 mã, cả ba chiến lược | **KHÔNG khớp báo cáo** → đã đính chính ở mục 1 |
| `sma_cross` rổ đầy đủ | `strat 11,389,511,350 \| diff -3,500,510,886,356 \| 21,750 lệnh \| 1515 mã` — **khớp** |
| `sma_cross` rổ đã lọc | `strat -14,086,713,488 \| diff -1,911,674,195,391 \| 18,391 lệnh \| 1283 mã` — **khớp** |
| File loại trừ | tồn tại thật, **246 dòng** — khớp |
| `pytest -m "not integration"` | 336 passed (báo cáo ghi 334 — đo trước `fad3a34`) |
| `ruff check trading tests scripts` | sạch |
| `detect_changes` | 1 file `trading/backtest.py`, risk low — đúng phạm vi |

Hai con số quyết định — thứ trả lời câu hỏi chặn go-live — **tái lập chính xác
tới từng đồng**. Kết luận ở mục 3 vì thế đứng vững. Chỉ mục 1 phải viết lại.

Bài học ghi lại: một báo cáo có thể **đúng ở chỗ tốn công nhất và sai ở chỗ rẻ
nhất**. Phần đo diện rộng (7,5 phút/lần chạy) chính xác tuyệt đối, còn phần đối
đầu ba mã (14 giây/lần chạy) thì sai toàn bộ. Đừng suy từ "phần khó đúng" ra
"phần dễ chắc cũng đúng" — phải kiểm cả hai.
