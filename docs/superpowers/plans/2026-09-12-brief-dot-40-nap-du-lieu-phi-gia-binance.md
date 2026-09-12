# Brief đợt 40 — Nạp dữ liệu phi giá từ Binance

Ngày giao: 12/09/2026.
Base: `343c6c9` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

**Đợt này KHÔNG xây chiến lược nào.** Nó chỉ nạp dữ liệu và chứng minh dữ liệu đó dùng được.
Chiến lược là đợt 41, và chỉ sau khi đợt này cho thấy dữ liệu đủ chất lượng.

**Đợt này phá một ràng buộc đã đứng suốt từ đầu: nó được phép gọi mạng.** Đọc §2.1 kỹ trước
khi gõ dòng code đầu tiên.

---

## 0. Tôi đã trinh sát trước. Đây là sự thật, không phải giả định.

Tôi tự kiểm bằng cách gọi thẳng danh sách kho dữ liệu công khai của Binance, ngày 12/09/2026.
Đừng tin lại từ trí nhớ — nhưng cũng đừng đi kiểm lại từ đầu, ba việc dưới đây đã chốt.

### 0.1. Cái gì có

| Dữ liệu | Đường dẫn | Phủ | Khối lượng |
|---|---|---|---|
| **Nến** | `data/futures/um/monthly/klines/BTCUSDT/` | có | nhỏ |
| **Funding đã settle** | `data/futures/um/monthly/fundingRate/BTCUSDT/` | có | rất nhỏ |
| **Open interest + tỷ lệ long/short + tỷ lệ taker** | `data/futures/um/daily/metrics/BTCUSDT/` | **từ 2020-09-01** | nhỏ |
| **Aggregate trades** (để tính delta) | `data/futures/um/monthly/aggTrades/BTCUSDT/` | từ 2020-01 | **rất lớn — xem §0.3** |

Tất cả là tệp ZIP tĩnh trên HTTPS công khai, **không cần API key**.

Thư mục `metrics` chỉ có bản **theo ngày**, không có bản theo tháng. `fundingRate` thì ngược
lại, chỉ có bản **theo tháng**. Đừng đoán, đừng thử đường còn lại.

### 0.2. Cái KHÔNG có — và nó giết một module

**Không có dữ liệu liquidation lịch sử. Ở đâu cũng không có.**

- Danh sách thư mục `data/futures/um/daily/` có đúng chín mục: `aggTrades`, `bookDepth`,
  `bookTicker`, `indexPriceKlines`, `klines`, `markPriceKlines`, `metrics`,
  `premiumIndexKlines`, `trades`. **Không có `liquidationSnapshot`.** Bản theo tháng cũng không.
- `forceOrder` chỉ là luồng WebSocket thời gian thực, không có REST lịch sử.

Nghĩa là **module C của tài liệu (Funding–OI–Liquidation) không bao giờ tái lập được đầy đủ**
bằng dữ liệu công khai. Ta sẽ có funding ✅ và OI ✅, thiếu liquidation ❌ — hai trên ba điều
kiện chính.

Tài liệu §12 đã chốt sẵn cách xử lý: *"Nếu dữ liệu không đủ để tái lập điều kiện, quyết định
đúng là no-trade hoặc loại mẫu, không phải tự ý thay thế bằng một proxy không được công bố."*

**Cấm tuyệt đối:** bịa một proxy liquidation từ biên độ nến, từ volume, hay từ sụt OI rồi gọi
nó là liquidation. Nếu đợt 41 chạy module C thì phải chạy dưới tên **"module C thiếu vế
liquidation"**, đúng như đợt 37 phải dùng chữ `price-only`.

### 0.3. Rủi ro khối lượng — con số thật

Aggregate trades của BTCUSDT, kích thước ZIP theo tháng tôi đọc được:

```
2020-12: 455 MB      2021-01: 917 MB      2021-02: 741 MB      2021-03: 825 MB
```

Và đó là số của **năm 2021**; khối lượng giao dịch từ đó tới nay còn lớn hơn. Nếu tải thô
30 tháng thì đang nói tới **hàng chục GB tải về** và nhiều giờ giải nén, phân tích.

**Cách giải quyết, và nó là bắt buộc:** ta **không cần** giao dịch thô. Ta chỉ cần **số gộp
theo từng nến 1 giờ** — khối lượng taker mua, khối lượng taker bán, delta, số lệnh. Nên quy
trình là **tải một tháng → gộp ngay → ghi số gộp vào DB → XOÁ tệp thô → sang tháng sau**.
Dung lượng đĩa giữ ở mức vài trăm MB tại mọi thời điểm, không bao giờ tích luỹ.

Và **không tải 30 tháng ngay.** Task 2 chạy **một tháng thí điểm**, đo tốc độ thật, rồi báo
cáo. Tôi quyết định có tải tiếp hay không dựa trên con số đó, không dựa trên phỏng đoán.

### 0.4. Bẫy trộn sàn — đọc kỹ, đây là chỗ dễ hỏng nhất

Toàn bộ dữ liệu crypto hiện có trong repo là **BingX**. Dữ liệu mới là **Binance**. Giá, khối
lượng, và giờ mở cửa hai sàn đều khác nhau.

Tài liệu §6.4 cấm thẳng: *"Không dùng dữ liệu liquidation của sàn A với OI của sàn B nếu không
có phép tổng hợp và weighting được định nghĩa trước."*

Nên đợt này **phải nạp cả nến 1 giờ của Binance**, dù repo đã có nến BingX. Sau đợt 40, mọi
phép đo dùng dữ liệu phi giá phải chạy **hoàn toàn trên Binance**: nến Binance, funding
Binance, OI Binance, delta Binance. **Không được ghép nến BingX với funding Binance.**

`bars_crypto` **không đụng tới**. Bảng đó là BingX, giữ nguyên, không thêm cột, không thêm
dòng Binance vào (khoá chính `(symbol, interval, ts)` sẽ đụng nhau và làm hỏng cả dữ liệu cũ
lẫn mới).

---

## 1. Phạm vi

### 1.1. File được sửa — tất cả đều mới

| File | Việc |
|---|---|
| `scripts/binance_vision.py` | tải + nạp: nến, funding, metrics |
| `scripts/binance_orderflow.py` | tải + gộp aggTrades thành số theo nến 1 giờ |
| `tests/test_binance_vision.py` | test phân tích cú pháp và nạp |
| `tests/test_binance_orderflow.py` | test phép gộp |
| `docs/superpowers/research/2026-09-12-dot-40-nap-du-lieu-binance.md` | báo cáo chất lượng dữ liệu |

**Không sửa file có sẵn nào.** Đặc biệt không đụng `scripts/bingx_klines.py`,
`scripts/measure_crypto_strategies.py`, `trading/cross_sectional.py`,
`trading/perp_backtest.py`, `trading/storage/db.py`, và mọi thứ trong `trading/collector/`,
`trading/engine/`.

Được import: `scripts._db_common.resolve_dsn`, `trading.data_quality.is_dirty_bar`.

### 1.2. Ràng buộc vận hành

Giữ nguyên mọi ràng buộc cũ **trừ đúng một điều được nới ở §2.1**:

- `real_trading_enabled` giữ `false`. **Không gọi SSI. Không gọi BingX.**
- Không in secret. `.env` không sửa, không mở.
- Không `TRUNCATE`/`DROP`/xoá dòng trên bảng có sẵn nào.
- Không đụng NATS.
- Không xoá file trong repo. **Không commit, không push.**
- Mọi output dán vào báo cáo copy từ terminal. Thiếu thì ghi **"CHƯA LÀM"**, **không bịa**.

---

## 2. Quy ước bắt buộc

### 2.1. Quyền gọi mạng — nới đúng chừng này, không hơn

**Được phép:** `GET` qua HTTPS tới đúng hai tên miền:

```
https://data.binance.vision/...
https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?...
```

**Không được phép, kể cả khi tiện tay:**

- Bất kỳ endpoint nào của `api.binance.com`, `fapi.binance.com`, hay bất kỳ API giao dịch nào.
- Bất kỳ endpoint nào cần API key, chữ ký, hay xác thực.
- Bất kỳ `POST`, `PUT`, `DELETE` nào tới bất kỳ đâu.
- BingX, SSI — vẫn cấm tuyệt đối như cũ.

**Lịch sự với máy chủ:** nghỉ tối thiểu `1.0s` giữa các lượt tải. Gặp `429` hoặc `5xx` thì
lùi theo cấp số nhân, trần `300s`. Theo đúng khuôn `scripts/bingx_klines.py` đã làm — **đọc
file đó trước** để giữ cùng style, nhưng **không sửa nó**.

**Kiểm tra tính toàn vẹn:** mỗi tệp `.zip` đều có tệp `.CHECKSUM` đi kèm. Tải cả hai và
**đối chiếu SHA256**. Tệp lệch checksum → bỏ, tải lại một lần, vẫn lệch thì ghi vào báo cáo và
bỏ qua tháng đó. Một tệp hỏng lặng lẽ sẽ thành một lỗ hổng dữ liệu mà không ai biết.

### 2.2. Múi giờ

Binance dùng **UTC** và timestamp mili-giây. Lưu vào `TIMESTAMPTZ`. Mọi thứ in ra kèm hậu tố
`UTC`. Không đụng tới giờ Việt Nam ở đợt này.

### 2.3. Nạp lại được nhiều lần

Mọi phép ghi là **UPSERT** theo khoá chính. Chạy lại toàn bộ script hai lần phải cho **cùng
một số dòng**, không nhân đôi. Đây là tiêu chí kiểm chứng, không phải lời khuyên.

Trước khi tải một tháng, **kiểm tra xem tháng đó đã nạp đủ chưa** và bỏ qua nếu rồi — tải
hàng chục GB mà không nối lại được sau khi đứt là hỏng cả đợt.

---

## Task 0 — Bốn bảng mới

Tạo bằng `CREATE TABLE IF NOT EXISTS`, đặt trong `scripts/binance_vision.py` theo đúng khuôn
`init_crypto_schema` của `scripts/bingx_klines.py`. **Không đụng bảng có sẵn.**

```sql
binance_klines (symbol, interval, ts, open, high, low, close, volume,
                quote_volume, trades, taker_buy_volume, taker_buy_quote_volume)
    PRIMARY KEY (symbol, interval, ts)

binance_funding (symbol, funding_time, funding_rate)
    PRIMARY KEY (symbol, funding_time)

binance_metrics (symbol, ts, sum_open_interest, sum_open_interest_value,
                 count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
                 count_long_short_ratio, sum_taker_long_short_vol_ratio)
    PRIMARY KEY (symbol, ts)

binance_orderflow_1h (symbol, ts, taker_buy_volume, taker_sell_volume,
                      delta, buy_ratio, trade_count)
    PRIMARY KEY (symbol, ts)
```

**Cột của `binance_metrics` phải khớp đúng tệp CSV thật.** Tôi đọc được tên cột từ nguồn thứ
cấp, **chưa tự mở tệp**. Task 1 bắt đầu bằng việc tải **một** tệp metrics, in **dòng tiêu đề
nguyên văn**, và dán vào báo cáo. Nếu tên cột khác những gì tôi viết ở trên → **sửa schema cho
khớp tệp thật và ghi rõ khác biệt**, đừng ép tệp vào schema của tôi.

Tất cả cột số dùng `DOUBLE PRECISION`. Cột nào tệp thật để trống → cho phép `NULL`, không điền `0`.

---

## Task 1 — Nạp nến, funding, metrics

Ba nguồn này **nhỏ**. Làm xong cả ba rồi mới sang Task 2.

### 1.1. Phạm vi nạp

- Mã: **`BTCUSDT`** và chỉ `BTCUSDT`.
- Nến: khung **`1h`**.
- Khoảng: **2024-01-01 → 2026-08-31** (tháng trọn vẹn). Chọn khoảng này để phủ được cả tập IS
  lẫn OOS mà các đợt trước đã dùng, có dư đầu cho warm-up chỉ báo.
- `metrics` là tệp theo ngày → lặp theo ngày trong khoảng đó.

### 1.2. Kiểm chứng

1. **Dòng tiêu đề nguyên văn** của một tệp mỗi loại (klines, fundingRate, metrics), dán vào
   báo cáo. Đây là bằng chứng schema khớp tệp thật.
2. Số dòng mỗi bảng sau khi nạp. Với `binance_klines` khung 1h, số dòng kỳ vọng ≈
   `số ngày × 24` — nêu cả con số kỳ vọng lẫn con số thật và **giải thích chênh lệch nếu có**.
3. **Nạp lại lần hai cho đúng cùng số dòng.** Dán cả hai con số.
4. **Đối chiếu chéo với BingX** — phép kiểm quan trọng nhất của Task 1:

   Lấy giá đóng cửa nến 1h của `BTCUSDT` (Binance) và `BTC-USDT` (BingX) trên 30 ngày bất kỳ
   trong khoảng đã nạp, tính **chênh lệch phần trăm** tại từng nến, rồi báo cáo **trung vị,
   p95 và max**.

   Kỳ vọng: trung vị dưới `0,1%`. Nếu trung vị vượt `0,5%` hoặc max vượt `5%` → **dừng lại,
   báo cáo, đừng nạp tiếp**: nghĩa là ta đang đọc nhầm cột, nhầm đơn vị, hoặc lệch múi giờ.

5. **Funding**: đếm số bản ghi và kiểm khoảng cách giữa hai lần settle liên tiếp. Báo cáo
   **phân bố khoảng cách** đó (bao nhiêu lần 8 giờ, bao nhiêu lần khác). Tài liệu §2.3 cảnh
   báo interval có thể thay đổi — đây là chỗ ta tự kiểm thay vì tin.
6. Suite đầy đủ pass (mốc hiện tại **708**), ruff sạch, **cổng cứng VN khớp từng chữ số**.

---

## Task 2 — Order flow: MỘT tháng thí điểm, rồi dừng

**Đây là task duy nhất có rủi ro thời gian. Đọc §0.3 lại trước khi bắt đầu.**

### 2.1. Quy trình bắt buộc

Với **đúng một tháng** — chọn **`2026-01`**:

1. Tải `BTCUSDT-aggTrades-2026-01.zip` **và** tệp `.CHECKSUM`, đối chiếu SHA256.
2. **Gộp theo luồng (streaming).** Đọc ZIP mà **không** giải nén toàn bộ ra đĩa và **không**
   nạp toàn bộ vào RAM. Đọc từng dòng, cộng dồn vào bucket giờ.
3. Quy ước Binance, theo đúng tài liệu §2.2:

   ```
   taker_buy_volume  = tổng qty khi is_buyer_maker = false
   taker_sell_volume = tổng qty khi is_buyer_maker = true
   delta             = taker_buy_volume - taker_sell_volume
   buy_ratio         = taker_buy_volume / (taker_buy_volume + taker_sell_volume)
   ```

   **Cột `is_buyer_maker` là cột nào, đọc từ dòng tiêu đề thật của tệp** — đừng đếm theo vị
   trí từ trí nhớ. In dòng tiêu đề vào báo cáo.
4. Ghi số gộp vào `binance_orderflow_1h`.
5. **Xoá tệp thô ngay sau khi gộp xong.** Không giữ lại.
6. **DỪNG. Báo cáo. Không tải tháng thứ hai.**

### 2.2. Số phải đo và báo cáo

| Chỉ số | Vì sao cần |
|---|---|
| Kích thước tệp ZIP (MB) | ước lượng tổng dung lượng 32 tháng |
| Thời gian tải (giây) | ước lượng tổng thời gian tải |
| Thời gian gộp (giây) | ước lượng tổng thời gian xử lý — thường mới là phần đắt |
| Đỉnh dung lượng đĩa dùng (MB) | chứng minh quy trình xoá-ngay có hiệu lực |
| Số dòng aggTrade đã đọc | đối chiếu với số nến |
| Số nến 1h sinh ra | phải đúng `24 × 31 = 744` cho tháng 1 |

Rồi **ngoại suy**: với tốc độ đó, nạp đủ 2024-01 → 2026-08 (32 tháng) mất bao lâu. Nêu con số
giờ. Đó là con số tôi cần để quyết định.

### 2.3. Kiểm chứng Task 2

1. **Phép kiểm đối soát quan trọng nhất:** với mỗi nến 1h, `taker_buy_volume +
   taker_sell_volume` phải **khớp** cột `volume` của cùng nến trong `binance_klines` (đã nạp ở
   Task 1). Báo cáo **chênh lệch tương đối trung vị và max** trên cả 744 nến.

   Kỳ vọng: chênh lệch gần bằng 0. Lệch quá `0,5%` nghĩa là quy ước `is_buyer_maker` đang bị
   hiểu ngược, hoặc gộp sót giao dịch. **Lệch thì dừng, báo cáo** — một delta sai dấu sẽ làm
   mọi kết luận của đợt 41 đảo ngược mà không ai phát hiện.

2. **Đối chiếu chéo thứ hai:** `binance_klines.taker_buy_volume` (Binance đã tính sẵn trong
   tệp klines) so với `taker_buy_volume` ta tự gộp từ aggTrades. Hai con số này phải khớp.
   Đây là phép kiểm độc lập cho quy ước cờ maker, và nó **mạnh hơn** mục 1.

3. Test phép gộp trên dữ liệu dựng tay: một tập giao dịch nhỏ đã biết trước đáp án, gồm cả
   `is_buyer_maker` true lẫn false, trải qua ranh giới giờ → kiểm `delta` và `buy_ratio` đúng,
   và giao dịch rơi đúng bucket giờ.

4. Test: giao dịch đúng tại mốc giây `:00` của đầu giờ thuộc bucket **giờ mới**, không phải
   giờ cũ.

5. Nạp lại tháng đó lần hai → cùng số dòng, `UPSERT` không nhân đôi.

---

## Task 3 — Báo cáo chất lượng dữ liệu

Ghi vào `docs/superpowers/research/2026-09-12-dot-40-nap-du-lieu-binance.md` (**file mới,
không ghi đè**):

1. Dòng tiêu đề nguyên văn của cả bốn loại tệp.
2. Bảng: mỗi bảng DB — số dòng, mốc đầu, mốc cuối (UTC), số ngày/nến thiếu so với kỳ vọng.
3. Kết quả đối chiếu chéo Binance ↔ BingX (§1.2 mục 4).
4. Phân bố khoảng cách funding (§1.2 mục 5).
5. Kết quả hai phép đối soát order flow (§2.3 mục 1 và 2).
6. Bảng đo tốc độ và **con số ngoại suy giờ** cho 32 tháng (§2.2).
7. Mục **"Điều đợt này KHÔNG làm được"**, tối thiểu phải có: **không có dữ liệu liquidation
   lịch sử, ở đâu cũng không có** (§0.2), nên module C của tài liệu vĩnh viễn thiếu một trong
   ba điều kiện chính.

---

## 4. Báo cáo cho Claude

1. `gitnexus_detect_changes()` (hoặc ghi rõ MCP timeout).
2. `git diff --stat` và `git status --short`.
3. Task 0: schema cuối cùng, **nêu rõ chỗ nào khác với schema tôi viết và vì sao**.
4. Task 1: sáu tiêu chí, kèm bảng đối chiếu chéo BingX.
5. Task 2: sáu chỉ số tốc độ, **con số ngoại suy giờ**, và hai phép đối soát order flow.
6. Ba dòng: số test pass (mốc **708**), ruff, cổng cứng VN đủ bốn con số.
7. Đường dẫn file nghiên cứu mới.

**Không commit, không push.**

---

## 5. Điều KHÔNG thuộc phạm vi

- **Không xây chiến lược, không backtest, không tính chỉ báo.** Đợt 41.
- **Không tải tháng aggTrades thứ hai.** Task 2 dừng sau một tháng. Quyết định tải tiếp là của
  tôi, sau khi đọc con số.
- **Không nạp mã nào ngoài `BTCUSDT`.**
- **Không** tải `bookDepth`, `bookTicker`, `trades`, `indexPriceKlines`, `markPriceKlines`,
  `premiumIndexKlines`. Chưa có câu hỏi nào cần tới chúng.
- **Không** đụng `bars_crypto` hay bất kỳ bảng BingX nào.
- **Không** bịa proxy liquidation. Xem §0.2.
- **Không** ghép nến BingX với funding/OI Binance. Xem §0.4.
- Ba câu hỏi lớn của đường VN vẫn là quyết định của chủ dự án.
