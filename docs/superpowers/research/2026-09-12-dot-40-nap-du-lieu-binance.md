# Báo cáo Nghiên cứu Đợt 40 — Nạp Dữ Liệu Phi Giá từ Binance Vision

**Ngày thực hiện:** 12/09/2026  
**Thực thi:** Gemini Flash 3.8  
**Ràng buộc mạng:** Tuân thủ tuyệt đối §2.1 (chỉ gọi GET tới `data.binance.vision`, sleep >= 1.05s, đối chiếu SHA256 checksum, exponential backoff).  
**Nguyên tắc dữ liệu:** Độc lập sàn (§0.4 tài liệu), không trộn Binance với BingX, nạp dạng UPSERT idempotent.

---

## 1. Dòng tiêu đề nguyên văn các tệp dữ liệu từ Binance Vision

Được trích xuất trực tiếp từ các tệp ZIP thực tế trên `data.binance.vision`:

| Loại dữ liệu | Tệp mẫu | Dòng tiêu đề nguyên văn (header) |
|---|---|---|
| **Nến (Klines 1h)** | `BTCUSDT-1h-2024-01.zip` | `open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore` |
| **Funding Rate** | `BTCUSDT-fundingRate-2024-01.zip` | `calc_time,funding_interval_hours,last_funding_rate` |
| **Metrics (OI, L/S)** | `BTCUSDT-metrics-2024-01-01.zip` | `create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio` |
| **Order Flow (aggTrades)** | `BTCUSDT-aggTrades-2026-01.zip` | `agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker` |

### Khác biệt Schema thực tế so với đề xuất ban đầu trong Brief:
1. **`binance_funding`**: Tệp thật có thêm cột `funding_interval_hours`. Schema được bổ sung cột này (`funding_interval_hours INT`) để bảo toàn thông tin chu kỳ settle thật của sàn.
2. **`binance_metrics`**: Cột thời gian trong file CSV là `create_time` định dạng `YYYY-MM-DD HH:MM:SS`, được parse chuẩn xác thành UTC `TIMESTAMPTZ` và lưu vào cột `ts`. Các cột tỷ lệ và OI đều khớp 100%.

---

## 2. Thống kê dữ liệu đã nạp vào Cơ sở Dữ liệu

Kỳ nạp: **2024-01-01 → 2026-08-31** (32 tháng trọn vẹn, 974 ngày).

| Bảng | Symbol | Khung / Tần suất | Số dòng thực tế | Số dòng kỳ vọng | Mốc đầu (UTC) | Mốc cuối (UTC) | Tỷ lệ đủ (%) |
|---|---|---|---|---|---|---|---|
| `binance_klines` | `BTCUSDT` | 1h | 23,376 | 23,376 (974 × 24) | 2024-01-01 00:00:00+00 | 2026-08-31 23:00:00+00 | **100.00%** (thiếu 0 nến) |
| `binance_funding` | `BTCUSDT` | ~8h settle | 2,922 | 2,922 (974 × 3) | 2024-01-01 00:00:00+00 | 2026-08-31 16:00:00+00 | **100.00%** (thiếu 0 bản ghi) |
| `binance_orderflow_1h` | `BTCUSDT` | 1h (thí điểm 2026-01) | 744 | 744 (31 × 24) | 2026-01-01 00:00:00+00 | 2026-01-31 23:00:00+00 | **100.00%** (thiếu 0 nến) |
| `binance_metrics` | `BTCUSDT` | 5 phút | 280,379 | 280,512 (974 × 288) | 2024-01-01 00:00:00+00 | 2026-08-31 23:55:00+00 | **99.95%** (thiếu 133 điểm) |

*Ghi chú về chênh lệch 133 điểm của `binance_metrics`:*
- 970 / 974 ngày có đủ trọn vẹn 288 records/ngày (100%).
- Chỉ có đúng 4 ngày bị khuyết một số điểm nến 5m trong tệp gốc của Binance (do bảo trì hệ thống sàn):
  - `2024-02-16`: 163 dòng (bảo trì hệ thống futures)
  - `2024-10-28`: 286 dòng (thiếu 2 điểm)
  - `2025-08-29`: 285 dòng (thiếu 3 điểm)
  - `2026-08-12`: 285 dòng (thiếu 3 điểm)
- Không có ngày nào bị thiếu tệp ZIP (đã tải đủ 974/974 ngày).

### Kiểm chứng tính Idempotent (Nạp lại lần 2):
- `binance_klines`: Nạp lại tháng 2024-01 với cờ `--force` -> Vẫn giữ nguyên đúng 23,376 dòng.
- `binance_funding`: Nạp lại tháng 2024-01 với cờ `--force` -> Vẫn giữ nguyên đúng 2,922 dòng.
- `binance_metrics`: Nạp lại ngày 2024-01-01 với cờ `--force` -> Giữ nguyên đúng 280,379 dòng.
- `binance_orderflow_1h`: UPSERT dựa trên khoá chính `(symbol, ts)` -> 744 nến không đổi.


---

## 3. Đối chiếu chéo Binance ↔ BingX (Task 1.2 mục 4)

Phép kiểm độc lập giá đóng cửa nến 1h giữa `BTCUSDT` (Binance) và `BTC-USDT` (BingX) trên 30 ngày (2026-08-01 00:00:00+00 đến 2026-08-31 23:59:59+00, 744 nến):

```
=== ĐỐI CHIẾU CHÉO BINANCE ↔ BINGX (NẾN 1H, 2026-08-01 -> 2026-08-31) ===
Số nến đối chiếu: 744
Trung vị chênh lệch: 0.0035%
p95 chênh lệch     : 0.0111%
Max chênh lệch     : 0.1057%
[ĐẠT] Chênh lệch nằm trong ngưỡng an toàn.
```

- **Kỳ vọng:** Trung vị < 0.1%. Ngưỡng cảnh báo dừng: Trung vị > 0.5% hoặc Max > 5.0%.
- **Thực tế:** Trung vị chỉ **`0.0035%`** (khoảng 2-3 USD trên giá BTC 60,000 USD), p95 chỉ **`0.0111%`**, và Max chỉ **`0.1057%`**.
- **Kết luận:** Dữ liệu nến Binance khớp hoàn hảo với BingX về mặt thời gian (UTC) và mức giá, không hề bị lệch múi giờ, nhầm cột hay nhầm thang đo.

---

## 4. Phân bố khoảng cách Funding Rate (Task 1.2 mục 5)

Kiểm tra toàn bộ 2,922 lần settle funding rate của `BTCUSDT` từ 2024-01-01 đến 2026-08-31:

```
=== PHÂN BỐ KHOẢNG CÁCH FUNDING RATE ===
Tổng số bản ghi funding: 2922
Phân bố khoảng cách (giờ):
  8.0h: 2921 lần (100.00%)
```

- **Kết luận:** 100% các kỳ funding của BTCUSDT trong 32 tháng qua đều duy trì đều đặn ở chu kỳ **8 giờ/lần** (tại các mốc 00:00, 08:00, 16:00 UTC). Không có sự kiện rút ngắn chu kỳ xuống 4h hay 2h đối với cặp BTCUSDT trong giai đoạn này.

---

## 5. Thí điểm Order Flow Task 2: Tháng 2026-01

### 5.1. Các chỉ số đo lường thực tế

| Chỉ số | Giá trị đo được | Nhận xét |
|---|---|---|
| **Kích thước tệp ZIP** | **517.61 MB** | Kích thước 1 tháng năm 2026 |
| **Thời gian tải** | **49.56 giây** | Băng thông đạt 10.44 MB/s |
| **Thời gian gộp** | **297.15 giây** (~4.95 phút) | Gộp 44.7 triệu giao dịch theo luồng stream |
| **Tổng thời gian 1 tháng** | **346.72 giây** (~5.78 phút) | Tải + gộp + ghi DB + xoá ZIP |
| **Đỉnh dung lượng đĩa** | **517.61 MB** | Đúng bằng tệp zip, xoá ngay sau khi xong, phụ trội = 0 MB |
| **Số dòng aggTrade đã đọc** | **44,701,670 dòng** | ~1.44 triệu trade/ngày |
| **Số nến 1h sinh ra** | **744 nến** | Khớp tuyệt đối 31 ngày × 24h = 744 nến |

### 5.2. Ngoại suy cho 32 tháng (2024-01 → 2026-08)

- Thời gian xử lý 1 tháng: `346.72 giây`
- Ngoại suy 32 tháng: `346.72 × 32 = 11,095 giây` ≈ **`3.08 giờ`** (~3 giờ 5 phút).
- Dung lượng đĩa tối đa tại mọi thời điểm: **< 600 MB** (do xóa cuốn chiếu từng tháng).

### 5.3. Kết quả hai phép đối soát Order Flow (§2.3)

```
--- KẾT QUẢ ĐỐI SOÁT ---
Đối soát 1 (Tổng vol vs klines.volume): Trung vị lệch = 0.000000%, Max lệch = 0.126954% -> PASS
Đối soát 2 (Taker buy vs klines.taker_buy): Trung vị lệch = 0.000000%, Max lệch = 0.191463% -> PASS
```

1. **Đối soát 1 (Tổng khối lượng):** `(taker_buy_volume + taker_sell_volume)` tự tính từ aggTrades so với cột `volume` trong `binance_klines`:
   - Trung vị chênh lệch: **`0.000000%`**
   - Max chênh lệch: **`0.126954%`** (dưới ngưỡng 0.5% rất xa).
2. **Đối soát 2 (Taker buy volume độc lập):** `taker_buy_volume` tự gộp từ aggTrades so với `taker_buy_volume` Binance tính sẵn trong `binance_klines`:
   - Trung vị chênh lệch: **`0.000000%`**
   - Max chênh lệch: **`0.191463%`** (dưới ngưỡng 0.5% rất xa).
3. **Ý nghĩa:**
   - Quy ước cờ maker: `is_buyer_maker = false` là **Taker Mua**, `is_buyer_maker = true` là **Taker Bán** đã được chứng minh là **chính xác tuyệt đối**.
   - Mốc `:00.000` thuộc về giờ mới được phân chia hoàn toàn khớp với logic đóng nến của sàn.
   - Không có hiện tượng thất thoát giao dịch hay lệch delta.

---

## 6. Điều đợt này KHÔNG làm được

1. **Hoàn toàn KHÔNG có dữ liệu liquidation lịch sử trong kho công khai Binance Vision**:
   - Kho lưu trữ `data.binance.vision/data/futures/um/` (cả `daily` lẫn `monthly`) chỉ có các thư mục: `aggTrades`, `bookDepth`, `bookTicker`, `indexPriceKlines`, `klines`, `markPriceKlines`, `metrics`, `premiumIndexKlines`, `trades`.
   - **Không có bất kỳ tệp dữ liệu nào về liquidationSnapshot**.
   - Kênh WebSocket `forceOrder` của Binance chỉ phát thời gian thực, không có API REST lịch sử lưu trữ dài hạn.
   - **Hệ quả kiến trúc:** Module C (Funding–OI–Liquidation) theo tài liệu lý thuyết **không thể tái lập đầy đủ 3 vế**. Khi chuyển sang Đợt 41, module C bắt buộc phải chạy dưới dạng **"module C thiếu vế liquidation"** (chỉ có 2 vế Funding và OI).
   - **Cam kết:** Tuyệt đối không bịa đặt proxy liquidation từ biên độ giá, volume hay biến động OI.

2. **Chưa tải tiếp 31 tháng aggTrades còn lại**:
   - Tuân thủ nghiêm ngặt chỉ dẫn §2.1 và §5: Dừng lại sau 1 tháng thí điểm (2026-01) để báo cáo con số đo đạc thực tế (3.08 giờ ngoại suy) cho Claude và chủ dự án phê duyệt trước khi quyết định nạp tiếp.

---

## 7. Tổng kết tình trạng kỹ thuật

- **Test Suite:** Toàn bộ test pass (mốc ban đầu 708 + các test mới cho binance vision và orderflow).
- **Ruff:** Không còn lỗi linting.
- **Cổng cứng VN:** Khớp từng chữ số:
  `TỔNG: strat -1,615,319,902 | BH 1,897,587,481,903 | diff -1,899,202,801,806 | lệnh 1,514 | mã sinh lệnh 439 | mã đủ thanh khoản 748 | dòng bẩn 10,459`
