# Bảo trì 28/09/2026 — xoá 261 nến giá 0, rebuild engine + collector, và một lỗ niêm phong crypto

**Người chạy:** Claude (không giao agent — đây là việc chỉ Claude được làm: xoá dữ liệu thật + rebuild container).
**Thời điểm:** 28/09/2026 21:27–21:40 (sau 15:40, phiên đã đóng — điều kiện của brief đợt 108).
**Base commit:** `ad1842a`.

## 1. Xoá 261 nến giá 0 trong bảng `bars`

### 1.1. Kiểm trước khi xoá

Script `_backups/delete_bars_zero_ohlc_20260926.sql` tự bảo vệ: đếm trước, `RAISE EXCEPTION` nếu ≠ 261, đếm lại sau, `ROLLBACK` nếu còn dòng bẩn. Nhưng tôi vẫn kiểm độc lập trước khi chạy, vì **điều kiện xoá phải giống hệt điều kiện sao lưu** — nếu sao lưu là một tập khác cùng số lượng thì script vẫn chạy trót lọt mà dữ liệu mất không lấy lại được.

| Nguồn | Tổng | AAA | HII | HPG | IJC | TCB | VCB |
|---|---|---|---|---|---|---|---|
| DB (`open<=0 OR high<=0 OR low<=0 OR close<=0`) | 261 | 76 | 67 | 39 | 73 | 3 | 3 |
| CSV sao lưu `bars_zero_ohlc_20260926.csv` | 261 | 76 | 67 | 39 | 73 | 3 | 3 |

Khớp từng mã. Khoảng thời gian DB: `2026-08-13 02:00:00+00` → `2026-09-16 07:40:00+00`, 6 mã.

### 1.2. Kết quả chạy

```
BEGIN
NOTICE:  So dong khop dieu kien truoc khi xoa: 261
NOTICE:  Da xoa 261 dong
NOTICE:  So dong ban con lai: 0
NOTICE:  XONG: xoa 261 dong, con lai 0 dong ban.
DO
COMMIT
 dong_ban_con_lai
------------------
                0
EXIT=0
```

## 2. Rebuild engine + collector

### 2.1. Vì sao cần

Ảnh container build **2026-09-26 14:42**, nhưng sau đó có ba commit chạm đường chạy:

| Commit | Ngày | Nội dung |
|---|---|---|
| `9d841d2` | 26/09 | đợt 107 — tái dùng take-profit octopus sau restart thay vì neo lại theo giá mở cửa |
| `a5eda8c` | 27/09 | đợt 108 — engine bỏ nến bẩn (`is_dirty_bar`) ở bar sống, warm-up và khôi phục TP |
| `dcda990` | 27/09 | đợt 109 — collector chặn nến giá 0 tại nguồn ghi (stream + backfill intraday) |

Container đang chạy **không có cái nào trong ba**.

### 2.2. Một rủi ro đã kiểm trước khi build

`d49ca96` đổi `calculate_percentile` / `empirical_percentile_rank` trong `trading/metrics.py` từ trả `0.0` sang **raise** khi danh sách rỗng. Nếu engine gọi hai hàm đó thì rebuild sẽ biến một giá trị sai âm thầm thành một cú chết hẳn giữa phiên. Đã grep: không có caller nào trong `trading/` — chỉ `scripts/` dùng. An toàn.

### 2.3. Kết quả

Build xong cả hai ảnh, recreate cả hai container, `EXIT=0`. Log 6 phút sau khi khởi động: **không có dòng WARN / ERROR / CRITICAL / Traceback nào** ở cả engine lẫn collector.

## 3. Phép kiểm TP của đợt 107 — không chạy được như dự kiến, và cách kiểm thay thế

### 3.1. Vì sao không chạy được

Brief đợt 108 hẹn kiểm log khởi động để thấy `IJC TP 7.398,57` và `AAA TP 7.094,29`. Nhưng log khởi động cho:

```
{"level": "INFO", "msg": "engine restored state", "cash": 100043751.69, "realized_pnl": 43751.69, "positions": {}}
```

**Sổ trống.** Hai vị thế đã đóng sáng nay lúc `2026-09-28 02:15:00+00` (09:15 VN), trước khi tôi kịp chạy bảo trì:

| ts | mã | chiều | KL | giá | PnL |
|---|---|---|---|---|---|
| 2026-09-28 02:15+00 | IJC | SELL | 400 | 6.770 | −250.301,67 |
| 2026-09-28 02:15+00 | AAA | SELL | 400 | 7.470 | +149.078,48 |
| 2026-09-03 02:15+00 | IJC | BUY | 400 | 7.353,675 | |
| 2026-09-03 02:20+00 | AAA | BUY | 400 | 7.053,525 | |

Không còn vị thế thì đường khôi phục TP không chạy, nên không có dòng log để đọc.

### 3.2. Một nhầm lẫn của tôi cần nói rõ

Tôi từng ghi 7.398,57 / 7.094,29 là **giá trị phồng** cần biến mất. Sai. Thông điệp commit `a5eda8c` nói rõ: đó là giá trị **sau khi lọc** (tức đúng); giá trị phồng là **~11.588 / ~11.098**.

### 3.3. Phép kiểm thay thế — và nó mạnh hơn phép kiểm ban đầu

Sau khi xoá 261 dòng, cửa sổ ATR thô **phải bằng** cửa sổ đã lọc, nên TP tính lại phải ra y hệt hai số đã đăng ký. Chạy lại `restore_take_profit` trên DB đã dọn, neo tại đúng bar lệnh BUY 03/09:

```
warmup_bars = 201  atr_period = 14
IJC: fill_ts=2026-09-03 02:15:00+00 anchor_open=7350.0
   window=201 ban=0 clean=201
   TP(thô)=7398.571428571428  TP(lọc)=7398.571428571428  mong đợi=7398.57
AAA: fill_ts=2026-09-03 02:20:00+00 anchor_open=7050.0
   window=201 ban=0 clean=201
   TP(thô)=7094.285714285715  TP(lọc)=7094.285714285715  mong đợi=7094.29
```

Ba số trùng khít, và `ban=0`. **Bản sửa dữ liệu (xoá) và bản sửa code (lọc) đồng quy:** bộ lọc `is_dirty_bar` giờ là vô tác dụng trên đúng các cửa sổ từng bị hỏng — đúng điều phải xảy ra sau khi dọn. Giữ bộ lọc vẫn cần, vì nó chặn nến bẩn **tương lai**, không phải nến đã xoá.

## 4. Quyết định về `bars_crypto` vượt mốc niêm phong 01/09

### 4.1. Không xoá

| interval | tổng | vượt mốc | tỷ lệ | đến |
|---|---|---|---|---|
| 1d | 29.430 | 52 | 0,18% | 2026-09-08 |
| 1h | 433.542 | 1.088 | 0,25% | 2026-09-08 15:00 |

BTC-USDT và ETH-USDT tới 08/09 (184 nến 1h mỗi mã); 18 mã còn lại tới 02/09 (40 nến 1h mỗi mã).

**Xoá là sai hướng.** Holdout phải còn nguyên để sau này kiểm định — xoá nó là tự phá thứ mình đang giữ. Câu hỏi đúng không phải "xoá hay không" mà là **"có script nào đọc quá mốc được không"**.

### 4.2. Và có — sáu script không chặn trên

| Script | Cách đọc | Chặn trên? |
|---|---|---|
| `measure_crypto_strategies.py` | `read_crypto_bars(conn, symbols=..., interval=...)` | **Không** — `to_date` là tham số **tuỳ chọn mặc định `None`**, caller dòng 369 không truyền |
| `measure_cross_sectional.py` | `read_crypto_bars(conn, interval="1d")` | **Không** |
| `measure_candlestick_strategies.py` | SQL trực tiếp, `WHERE "interval" = '1d'` / `'1h'` | **Không** |
| `measure_candlestick_patterns.py` | SQL trực tiếp | **Không** |
| `measure_octopus_combo_hybrid.py` | SQL trực tiếp | **Không** |
| `optimize_octopus_combo_hybrid.py` | SQL trực tiếp | **Không** |

Đây lại đúng **lớp lỗi mặc-định-sai-an-toàn** mà dự án gặp lặp đi lặp lại: một mốc chặn tồn tại nhưng **tuỳ chọn**, và mặc định của nó là "không chặn". Niêm phong hiện chỉ được giữ bởi *thời điểm người ta tình cờ chạy script*, không bởi code.

Đối chiếu: nhóm script forex/BingX mới (đợt 116, 117, 118) **đều** ghim `SEALED_MAX_DATE = 2026-08-31` và truyền vào SQL. Nhóm crypto cũ ra đời trước khi mốc 01/09 được đặt nên không có.

### 4.3. Kết luận cũ có phải xem lại không — Không

0,18% và 0,25% dữ liệu, trên các phép đo vốn đã âm rõ. Không kết luận nào của đợt 105/106 hay các đợt crypto trước bị ảnh hưởng. Nhưng **mọi lần chạy lại từ hôm nay trở đi sẽ lặng lẽ ăn holdout** — phải bịt trước khi chạy lại, không phải sau.

## 5. Việc còn treo sau đợt bảo trì này

1. **Trả nợ kỹ thuật `screen_vcp_daily.py`** (đã hẹn ở §A.6 đợt 120) — dời hàm thuần sang `trading/`, chốt bằng việc tái lập y nguyên số của đợt 99.
2. **Đo lại SEPA với mốc trung tính** — dùng lại `make_basket_entry` + `basket_for_day` của `screen_smc_stock_daily.py`, không viết hàm mới (§A.8 đợt 120).
3. **Bịt mốc niêm phong crypto cho sáu script ở §4.2** — nên gộp vào đợt trả nợ, và **mốc phải bắt buộc, không tuỳ chọn**: hàm đọc nến crypto không được có đường đi nào trả về dữ liệu không chặn trên.
