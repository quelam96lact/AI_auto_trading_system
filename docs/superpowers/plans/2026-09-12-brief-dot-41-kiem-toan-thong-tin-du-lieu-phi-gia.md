# Brief đợt 41 — Kiểm toán thông tin của dữ liệu phi giá

Ngày giao: 12/09/2026.
Base: `91a44d9` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

**Đợt này vẫn KHÔNG xây chiến lược.** Nó hỏi một câu duy nhất: *dữ liệu mới có chứa thông tin
dự báo nào không?* Xây luật vào lệnh là đợt 42, và chỉ nếu đợt này trả lời có.

---

## 0. Vì sao kiểm toán thông tin trước khi xây chiến lược

### 0.1. Bảy lần xây trước rồi đo sau, bảy lần âm

Đợt 22/26 bốn chiến lược, đợt 37 hai module, đợt 39 một danh mục cắt ngang. Mỗi lần ta xây
xong toàn bộ luật vào lệnh, thoát lệnh, sizing, phí — rồi mới biết tín hiệu gốc không mang
thông tin. Đợt 38 đo ra con số rõ nhất: điểm vào lệnh của Donchian nằm ở **phân vị 19%** của
nhiễu ngẫu nhiên trên IS. Tệ hơn bốc thăm.

Toàn bộ công sức dựng luật thoát và sizing của ba đợt đó là công sức bọc quanh một tín hiệu
rỗng.

Giờ ta có dữ liệu **mới về bản chất** — funding, open interest, tỷ lệ long/short, order flow.
Câu hỏi đúng không phải *"xây chiến lược gì với nó"* mà **"nó có tương quan gì với lợi suất
tương lai không"**. Câu đó trả lời được bằng một đợt rẻ, và nó quyết định có đáng làm đợt 42
hay không.

### 0.2. Cái bẫy đợt 40 bỏ sót — tôi tìm ra khi audit

Đợt 40 đếm số dòng và kết luận dữ liệu đủ. Nhưng **không ai kiểm giá trị**. Tôi kiểm:

```
oi_bang_0 | oi_duoi_1000 | oiv_bang_0 |  tong
      330 |          330 |        330 | 280379
```

**330 mốc có `sum_open_interest = 0` và `sum_open_interest_value = 0`**, trong khi các cột tỷ
lệ long/short ở cùng dòng vẫn có giá trị bình thường. Đây là dữ liệu gốc của Binance khuyết,
không phải lỗi loader. Trải trên **14 ngày**, phần lớn dồn vào tuần `2024-07-09 → 2024-07-15`,
lác đác tới `2025-07-21`.

**Vì sao nó nguy hiểm:** điều kiện OI của tài liệu là `OI_t / OI_{t-3} - 1 <= -0,015`. Một mẫu
số bằng 0 cho vô cực; một tử số bằng 0 cho **−100%** — trông y hệt một cú deleveraging khổng
lồ. Đó là máy sinh tín hiệu giả, và nó sẽ rơi đúng vào tuần biến động tháng 7/2024.

**Luật cho đợt này:** `sum_open_interest = 0` và `sum_open_interest_value = 0` **được coi là
thiếu dữ liệu (NULL)**, không phải giá trị thật. Mọi đại lượng cần OI phải có **cả hai đầu mút
hợp lệ**, nếu không thì trả `NULL` và bị loại khỏi phép đo — **không nội suy, không điền**.

### 0.3. Bài học tôi tự rút cho các brief sau

Brief 40 của tôi yêu cầu đếm dòng, đối chiếu chéo giá, và đối soát order flow — nhưng **không
yêu cầu kiểm khoảng giá trị** của các cột mới. Đếm dòng không phát hiện được 330 số 0 nằm giữa
280 nghìn dòng đúng.

Từ đợt này trở đi, mọi brief nạp dữ liệu phải có một mục **"khoảng giá trị hợp lệ"**: min, max,
số `NULL`, số `0`, và số dòng ngoài khoảng hợp lý — cho **từng cột số**.

---

## 1. Phạm vi

### 1.1. File

| File | Trạng thái | Việc |
|---|---|---|
| `scripts/binance_orderflow.py` | có sẵn | **Task 1** — thêm cờ khoảng tháng, không đổi logic gộp |
| `trading/feature_panel.py` | **mới** | dựng bảng đặc trưng 1 giờ, chống nhìn trước |
| `scripts/audit_information.py` | **mới** | kiểm toán tương quan + phép kiểm hoán vị |
| `tests/test_feature_panel.py` | **mới** | test căn dòng thời gian |
| `docs/superpowers/research/2026-09-12-dot-41-kiem-toan-thong-tin.md` | **mới** | kết quả |

**Không sửa** `scripts/binance_vision.py`, `trading/cross_sectional.py`,
`trading/perp_backtest.py`, `trading/indicators.py`, `trading/metrics.py`,
`scripts/significance_test.py`, `trading/storage/db.py`, và mọi thứ trong
`trading/collector/`, `trading/engine/`, `trading/strategies/`.

**Không đụng** `bars_crypto` hay bất kỳ bảng BingX nào. Không tạo bảng mới — bảng đặc trưng
dựng trong bộ nhớ, không ghi DB.

### 1.2. Ràng buộc vận hành

Như đợt 40. Mạng: **chỉ** `GET` tới `data.binance.vision` và host S3 của nó, cho Task 1. Không
API key, không `POST`, không BingX, không SSI. `real_trading_enabled` giữ `false`. Không xoá
file. **Không commit, không push.** Mọi output copy từ terminal, thiếu thì ghi **"CHƯA LÀM"**.

**GitNexus:** index đang **stale** (đợt 40 không chạy lại). Chạy `npx gitnexus analyze`
**trước** khi bắt đầu, và lại một lần khi xong. Đợt 40 bỏ bước này — đừng lặp lại.

---

## Task 1 — Nạp nốt 31 tháng order flow

Đợt 40 đo được: **5,78 phút/tháng**, ngoại suy **≈ 3,1 giờ** cho đủ 32 tháng. Chủ dự án đã
duyệt tải tiếp.

### 1.1. Việc

`scripts/binance_orderflow.py` hiện chỉ nhận `--year` và `--month`, một tháng mỗi lần. Thêm
hai cờ khoảng:

```
--from-month YYYY-MM
--to-month   YYYY-MM
```

Chạy tuần tự từng tháng trong khoảng. **Không đổi một dòng nào của `aggregate_aggtrades_stream`**
hay logic gộp — chỉ thêm vòng lặp và phân tích tham số. Giữ nguyên `--year`/`--month` cho
tương thích ngược.

Bắt buộc giữ:
- **Bỏ qua tháng đã nạp đủ** (kiểm số nến trong DB trước khi tải). Nối lại được sau khi đứt.
- **Xoá tệp thô ngay sau khi gộp**, đúng như đợt 40.
- Đối chiếu SHA256 với tệp `.CHECKSUM`.
- In tiến độ từng tháng: tên tháng, MB, giây tải, giây gộp, số nến sinh ra.

### 1.2. Chạy

`--from-month 2024-01 --to-month 2026-08`. Tháng `2026-01` đã có → phải bị **bỏ qua**, không
tải lại. Đó chính là bài kiểm tra cơ chế nối lại.

### 1.3. Kiểm chứng

1. Sau khi xong: `binance_orderflow_1h` có đúng **23.376** dòng (bằng `binance_klines`), mốc
   đầu `2024-01-01 00:00 UTC`, mốc cuối `2026-08-31 23:00 UTC`. Nêu cả ba con số.
2. **Đối soát trên TOÀN bộ 23.376 nến** (đợt 40 chỉ làm 744): trung vị và max chênh lệch
   tương đối của `taker_buy_volume` tự gộp so với `binance_klines.taker_buy_volume`. Ngưỡng
   dừng: trung vị `> 0,5%`.
3. **Tương quan giữa `delta` và lợi suất cùng giờ** `(close-open)/open` trên toàn bộ dữ liệu.
   Tôi đo trên tháng thí điểm được **`+0,687`**. Nếu con số toàn kỳ ra **âm** → dừng ngay, quy
   ước cờ maker đã sai ở đâu đó.
4. Chạy lại lệnh đó lần hai → mọi tháng đều bị bỏ qua, số dòng không đổi.
5. Suite đầy đủ pass (mốc **716**), ruff sạch, cổng cứng VN khớp từng chữ số.

---

## Task 2 — Bảng đặc trưng 1 giờ: `trading/feature_panel.py`

**Đây là task dễ sai nhất của cả đợt.** Mọi thứ sau nó phụ thuộc vào việc căn dòng thời gian
ở đây đúng.

### 2.1. Hàm

```python
def build_feature_panel(
    klines: list[Bar],                    # 1h, Binance
    funding: list[tuple[datetime, float]],# (funding_time, funding_rate)
    metrics: list[dict],                  # mốc 5 phút
    orderflow: list[dict],                # mốc 1 giờ
    *,
    max_metric_staleness_minutes: int = 10,
) -> list[dict]:
```

Trả một hàng cho mỗi nến 1 giờ, khoá theo `ts` (thời điểm **mở** nến, đúng quy ước `Bar` của
repo).

### 2.2. Luật căn dòng — chống nhìn trước, đọc từng dòng

Gọi `close_ts = ts + 1 giờ` là thời điểm nến đóng. **Mọi đặc trưng của hàng này chỉ được dùng
thông tin có tại hoặc trước `close_ts`.**

| Nguồn | Luật |
|---|---|
| **funding** | Lấy bản ghi **đã settle gần nhất** có `funding_time <= close_ts`. **Tuyệt đối không** dùng lần settle kế tiếp. Tài liệu §6.2: *"Không dùng predicted funding tương lai như funding đã thực trả."* |
| **metrics** | Lấy mốc 5 phút gần nhất có `ts <= close_ts`. Nếu mốc đó cũ hơn `max_metric_staleness_minutes` → **`NULL`**, không dùng mốc cũ hơn. |
| **orderflow** | Dùng đúng hàng có cùng `ts` với nến. Delta của nến được biết tại `close_ts`, hợp lệ. |

**Luật OI bằng 0 (§0.2):** khi đọc `metrics`, nếu `sum_open_interest = 0` **hoặc**
`sum_open_interest_value = 0` thì coi **cả hai** là `NULL`. Các cột tỷ lệ ở cùng dòng vẫn dùng
được bình thường — chúng không bị hỏng.

### 2.3. Chín đặc trưng

| # | Tên | Công thức |
|---|---|---|
| 1 | `funding_rate` | funding đã settle gần nhất |
| 2 | `funding_z` | z-score của (1) trên **90 ngày các lần settle trước đó**, không gồm hiện tại |
| 3 | `oi_chg_3h` | `OI(close_ts) / OI(close_ts - 3h) - 1` |
| 4 | `oi_chg_24h` | như trên, 24 giờ |
| 5 | `long_short_ratio` | `count_long_short_ratio` |
| 6 | `toptrader_ls_ratio` | `sum_toptrader_long_short_ratio` |
| 7 | `taker_ls_vol_ratio` | `sum_taker_long_short_vol_ratio` |
| 8 | `delta_norm` | `delta / (taker_buy_volume + taker_sell_volume)` |
| 9 | `cvd_chg_3h` | tổng `delta` của 3 nến gần nhất chia tổng khối lượng 3 nến đó |

Đặc trưng 3 và 4 **phải có cả hai đầu mút hợp lệ**, nếu không → `NULL`. Đặc trưng 2 cần đủ 90
ngày lịch sử settle, nếu không → `NULL`.

### 2.4. Ba biến mục tiêu

```
fwd_ret_1h  = close[t+1]  / close[t] - 1
fwd_ret_4h  = close[t+4]  / close[t] - 1
fwd_ret_24h = close[t+24] / close[t] - 1
```

Đây là **thứ duy nhất** trong bảng nhìn về tương lai, và nó là đích chứ không phải đầu vào.
Hàng không đủ dữ liệu tương lai → `NULL` cho biến đó.

### 2.5. Kiểm chứng Task 2 — `tests/test_feature_panel.py`

Dựng dữ liệu thủ công, không đọc DB.

1. **Funding không nhìn trước:** một lần settle tại đúng `close_ts` → **được dùng**. Một lần
   settle một giây **sau** `close_ts` → **không** được dùng, hàng phải lấy lần settle trước đó.
   Đây là bài test quan trọng nhất của cả task.
2. **Metrics quá cũ:** mốc 5 phút gần nhất cách `close_ts` 15 phút, với ngưỡng 10 phút → mọi
   đặc trưng từ metrics là `NULL`.
3. **OI bằng 0 thành NULL:** một hàng metrics có `sum_open_interest = 0` → `oi_chg_3h` tại các
   hàng dùng nó là `NULL`, **và** `long_short_ratio` ở cùng hàng vẫn **có giá trị**.
4. **`oi_chg` cần hai đầu mút:** thiếu đầu mút `t-3h` → `NULL`, không thay bằng mốc gần nhất.
5. **`funding_z` cần đủ 90 ngày** → trước đó là `NULL`.
6. `delta_norm` bằng đúng `2 * buy_ratio - 1`, tính lại trong test.
7. **Biến mục tiêu đúng:** dựng chuỗi giá đã biết đáp án, kiểm `fwd_ret_4h` của hàng `t` bằng
   đúng `close[t+4]/close[t] - 1`, và hàng cuối cùng có `fwd_ret_24h = NULL`.
8. **Không rò rỉ:** với mọi hàng, mọi đặc trưng chỉ phụ thuộc dữ liệu `<= close_ts`. Viết
   thành một test cắt cụt: dựng bảng trên toàn chuỗi, rồi dựng lại trên chuỗi **cắt tại hàng
   `k`** — chín đặc trưng của hàng `k` phải **giống hệt** ở hai lần dựng. Đây là bài test
   phát hiện rò rỉ mạnh nhất; nếu nó đỏ thì có đặc trưng đang nhìn trước.

---

## Task 3 — Kiểm toán thông tin: `scripts/audit_information.py`

**Chỉ bắt đầu sau khi Task 2 đạt toàn bộ.**

### 3.1. Phép đo

Với mỗi cặp (9 đặc trưng × 3 biến mục tiêu) = **27 cặp**, tính **tương quan hạng Spearman**
trên các hàng có cả hai giá trị không `NULL`. Báo số hàng dùng cho từng cặp.

**Chỉ chạy trên IS:** `2024-01-01 → 2025-12-31 UTC`. Năm **2026 niêm phong** cho đợt 42.

### 3.2. Vấn đề đa phép kiểm — và cách xử lý đúng

Thử 27 cặp ở mức ý nghĩa 5% thì **kỳ vọng có ~1,4 cặp "có ý nghĩa" hoàn toàn do may rủi**. Báo
cáo cặp đẹp nhất trong 27 cặp rồi gọi nó là phát hiện chính là data snooping mà tài liệu §10
cảnh báo.

**Cách xử lý, chốt trước:** phân phối null của **giá trị lớn nhất**.

1. Hoán vị chuỗi lợi suất bằng **hoán vị theo khối** (block permutation), độ dài khối **48
   giờ** — dài hơn biến mục tiêu dài nhất (24h) để giữ tự tương quan do chồng lấn.
2. Tính lại **cả 27** tương quan trên chuỗi đã hoán vị.
3. Lấy **`max |ρ|` trong 27 cặp** của lần hoán vị đó.
4. Lặp **1000 lần** → phân phối null của thống kê lớn nhất.

Một cặp **có thông tin** khi và chỉ khi `|ρ|` thật của nó **vượt phân vị 95 của phân phối null
của giá trị lớn nhất**. Đây là hiệu chỉnh theo họ (family-wise), và nó **tự động** tính đến
việc ta đã thử 27 lần.

Dùng `calculate_percentile` và `empirical_percentile_rank` **import từ `trading.metrics`**.
Không viết lại — đợt 39 Task 0 đã gom chúng về đó.

RNG cô lập bằng `random.Random(seed)`, hạt giống cố định, chạy hai lần phải giống hệt.

### 3.3. Vì sao hoán vị theo khối chứ không hoán vị từng điểm

`fwd_ret_24h` của hai giờ liền nhau chồng lấn 23 giờ, nên chuỗi lợi suất **tự tương quan
mạnh**. Hoán vị từng điểm sẽ phá hết tự tương quan đó và cho một phân phối null **quá hẹp** —
mọi thứ trông có ý nghĩa. Khối 48 giờ giữ lại cấu trúc đó.

### 3.4. Phân tích thập phân vị cho cặp mạnh nhất

Với **hai** cặp có `|ρ|` lớn nhất (bất kể có vượt ngưỡng hay không), in bảng: chia các hàng
thành 10 nhóm theo giá trị đặc trưng, mỗi nhóm in số hàng và **lợi suất tương lai trung bình**.

Câu hỏi không phải "nhóm cao nhất có lãi không" mà **"có đơn điệu không"**. Một quan hệ thật
thì lợi suất tăng dần đều qua các thập phân vị. Một quan hệ do một vài điểm ngoại lai tạo ra
thì chỉ có nhóm đầu hoặc nhóm cuối lệch hẳn, giữa thì lộn xộn. **Nói rõ bạn thấy hình dạng
nào.**

### 3.5. Kiểm chứng Task 3

1. Chạy hai lần cùng hạt giống → mọi con số giống hệt.
2. **Đối chứng dương:** thêm một đặc trưng giả `cheat = fwd_ret_1h + nhiễu nhỏ` vào bảng, chạy
   kiểm toán → cặp `(cheat, fwd_ret_1h)` phải vượt ngưỡng phân vị 95 một cách áp đảo. Nếu
   không, công cụ hỏng và mọi kết luận "không có thông tin" đều vô giá trị. **Xoá đặc trưng
   giả này khỏi lượt chạy chính thức** — nó chỉ tồn tại trong test.
3. **Đối chứng âm:** thêm một đặc trưng ngẫu nhiên thuần (hạt giống cố định) → **không** vượt
   ngưỡng.
4. Số hàng dùng cho mỗi cặp là hợp lý: với `funding_rate` × `fwd_ret_1h` trên IS phải cỡ
   **17.000+** hàng (2 năm × 8.760 giờ, trừ warm-up và `NULL`). Con số nhỏ hơn nhiều nghĩa là
   phép ghép đang rớt dữ liệu — điều tra trước khi chạy tiếp.

---

## Task 4 — Báo cáo

`docs/superpowers/research/2026-09-12-dot-41-kiem-toan-thong-tin.md` (**file mới, không ghi đè**).

1. Task 1: bảng tiến độ 31 tháng, ba con số đối soát toàn kỳ, tương quan delta–lợi suất toàn kỳ.
2. **Bảng 27 cặp**: đặc trưng × biến mục tiêu, `ρ` Spearman, số hàng, và **có/không vượt ngưỡng**.
3. Ngưỡng phân vị 95 của phân phối null giá trị lớn nhất — **một con số**, in rõ.
4. Bảng thập phân vị cho hai cặp mạnh nhất, kèm nhận định hình dạng (§3.4).
5. Kết luận **một dòng**: có cặp nào vượt ngưỡng không, và nếu có thì cặp nào.
6. Mục **"Điều kiểm toán này KHÔNG trả lời"** — tối thiểu: tương quan không phải lợi nhuận
   (chưa tính phí, chưa có luật vào/ra); chỉ tuyến tính theo hạng nên bỏ sót quan hệ phi đơn
   điệu và quan hệ có điều kiện theo chế độ thị trường; chỉ một mã; chỉ một sàn; **không có
   liquidation**; và 2026 chưa đụng tới.

---

## 5. Báo cáo cho Claude

1. `npx gitnexus analyze` trước và sau, `gitnexus_detect_changes()` (hoặc ghi rõ MCP timeout).
2. `git diff --stat`, `git status --short`, và **`git diff` của phần `aggregate_aggtrades_stream`
   trong `binance_orderflow.py` — tôi kỳ vọng rỗng.**
3. Task 1: năm tiêu chí.
4. Task 2: tám test.
5. Task 3: bốn tiêu chí, **nói rõ đối chứng dương đã xanh**.
6. Task 4: bảng 27 cặp, ngưỡng, kết luận một dòng.
7. Ba dòng: số test pass (mốc **716**), ruff, cổng cứng VN đủ bốn con số.

**Không commit, không push.**

---

## 6. Điều KHÔNG thuộc phạm vi

- **Không xây chiến lược, không backtest, không luật vào/ra, không tính phí.** Đợt 42.
- **Không đụng dữ liệu 2026.** Niêm phong.
- **Không** thêm đặc trưng ngoài chín cái ở §2.3. Muốn thêm thì báo cáo đề xuất, đừng tự thêm —
  mỗi đặc trưng thêm vào làm ngưỡng đa phép kiểm chặt hơn cho tất cả.
- **Không** bịa proxy liquidation. Dữ liệu đó không tồn tại (đợt 40 §0.2).
- **Không** ghép nến BingX với dữ liệu Binance. Toàn bộ đợt này chạy trên Binance.
- **Không** tối ưu tham số nào. Không có tham số nào để tối ưu ở đợt này — nếu bạn thấy mình
  đang chỉnh một con số để kết quả đẹp hơn, dừng lại và báo cáo.
