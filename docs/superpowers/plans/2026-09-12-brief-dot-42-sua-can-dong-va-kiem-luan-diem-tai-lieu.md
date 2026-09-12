# Brief đợt 42 — Sửa lỗi căn dòng, dựng phép phòng, và kiểm chính luận điểm của tài liệu

Ngày giao: 12/09/2026.
Base: `d5dd50c` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Bối cảnh

### 0.1. Lỗi của tôi ở đợt 41

Brief 41 §2.2 tôi viết luật căn dòng: *"Lấy mốc 5 phút gần nhất có `ts <= close_ts`."*
Agent làm đúng chữ tôi viết. **Luật đó sai** với một biến **dòng chảy** được gán nhãn theo
thời điểm **bắt đầu** cửa sổ.

Bằng chứng tôi đo được sau khi nghiệm thu:

```
tỷ lệ taker tại T  vs  buy_ratio giờ BẮT ĐẦU tại T  : +0,2799
tỷ lệ taker tại T  vs  buy_ratio giờ KẾT THÚC tại T : -0,0045

(đối chứng) delta của ta  vs  giờ CỦA CHÍNH NÓ      : +0,7531
(đối chứng) delta của ta  vs  giờ TRƯỚC ĐÓ          : +0,0466
```

`sum_taker_long_short_vol_ratio` gán nhãn `T` mô tả cửa sổ `[T, T+5 phút)` — **không biết được
tại `T`**. Dùng nó tại `close_ts` là đưa 5 phút đầu của chính cửa sổ lợi suất tương lai vào
làm đầu vào. Hai cặp "vượt ngưỡng" của đợt 41 đã bị bác bỏ.

### 0.2. Vì sao bài test cắt cụt không cứu được, và bài học

Bài test §2.5.8 của đợt 41 (dựng bảng rồi dựng lại trên chuỗi cắt tại hàng `k`) **đã pass
đúng** và vẫn mù. Nó hỏi *"có dùng hàng nào sau `close_ts` không"*. Ở đây không hàng tương lai
nào bị dùng — sai lầm nằm ở **ngữ nghĩa nhãn thời gian trên chính hàng đó**.

**Chống rò rỉ cần hai lớp:**

| Lớp | Câu hỏi | Công cụ |
|---|---|---|
| 1 | Có dùng hàng nào sau `close_ts` không? | phép cắt cụt (đã có) |
| 2 | Hàng tại `close_ts` thật sự mô tả khoảng nào? | **phép đo hướng — Task 1** |

Task 1 dựng lớp hai thành công cụ dùng lại được, để lỗi này không thể tái diễn với nguồn dữ
liệu tiếp theo.

### 0.3. Và điều đợt 42 phải trả lời cho xong

Đợt 41 sau khi trừ rò rỉ cho kết luận: không đặc trưng đơn lẻ nào mang thông tin. Nhưng
**tài liệu gốc không hề tuyên bố từng đặc trưng đơn lẻ có tác dụng.** Module C là một **điều
kiện hợp**: funding không quá crowded **và** OI giảm **và** giá tái chiếm EMA **và** delta xác
nhận — cùng lúc.

Một phép kiểm tương quan từng đặc trưng **không thể** nhìn thấy hiệu ứng hợp. Nên đợt 41 chưa
bác bỏ luận điểm của tài liệu; nó mới chỉ bác bỏ phiên bản đơn giản nhất.

Task 4 kiểm **đúng một điều kiện hợp, khai báo trước, lấy nguyên văn từ tài liệu §6.2**. Đó là
việc mà cả đợt 40 và 41 tồn tại để phục vụ. Sau Task 4, hướng dữ liệu phi giá sẽ có câu trả
lời dứt khoát — có hoặc không.

---

## 1. Phạm vi

| File | Trạng thái | Việc |
|---|---|---|
| `scripts/probe_timestamp_semantics.py` | **mới** | Task 1 — phép đo hướng |
| `trading/feature_panel.py` | có sẵn | Task 2 — sửa luật căn dòng |
| `tests/test_feature_panel.py` | có sẵn | Task 2 — test căn dòng mới |
| `scripts/audit_information.py` | có sẵn | Task 3 — chạy lại + biên an toàn |
| `scripts/event_study_module_c.py` | **mới** | Task 4 — kiểm điều kiện hợp |
| `tests/test_event_study.py` | **mới** | Task 4 |
| `docs/superpowers/research/2026-09-12-dot-42-sua-can-dong-va-event-study.md` | **mới** | kết quả |

**Không sửa** `scripts/binance_vision.py`, `scripts/binance_orderflow.py`,
`trading/perp_backtest.py`, `trading/cross_sectional.py`, `trading/indicators.py`,
`trading/metrics.py`, `scripts/significance_test.py`, `trading/storage/db.py`, và mọi thứ
trong `trading/collector/`, `trading/engine/`, `trading/strategies/`.

**Không gọi mạng.** Dữ liệu đã nằm đủ trong DB. Không tạo bảng mới, không ghi DB — mọi thứ
tính trong bộ nhớ. `real_trading_enabled` giữ `false`. Không xoá file. **Không commit, không
push.** Thiếu thì ghi **"CHƯA LÀM"**, **không bịa**.

**GitNexus:** `npx gitnexus analyze` trước và sau.

---

## Task 1 — Phép đo hướng: `scripts/probe_timestamp_semantics.py`

**Làm trước tiên.** Đây là công cụ, không phải phép đo một lần.

### 1.1. Ý tưởng

Với một chuỗi giá trị gán nhãn thời gian `T`, hỏi: nhãn đó mô tả khoảng **trước** hay **sau**
`T`? Trả lời bằng cách so tương quan với biến động giá ở hai phía:

```
r_truoc(T) = lợi suất nến 1 giờ KẾT THÚC tại T   = (close-open)/open của nến [T-1h, T)
r_sau(T)   = lợi suất nến 1 giờ BẮT ĐẦU tại T    = (close-open)/open của nến [T, T+1h)
```

Chỉ dùng các mốc rơi đúng đầu giờ (`phút = 0`).

### 1.2. Phân loại, và mốc hiệu chuẩn

In cho mỗi cột: `n`, `corr_truoc`, `corr_sau`, và nhãn phân loại:

| Điều kiện | Nhãn | Nghĩa |
|---|---|---|
| `corr_truoc` mạnh dương, `>` hẳn `corr_sau` | `NHIN_VE_QUA_KHU` | dùng được tại `T` |
| `corr_sau` `>` hẳn `corr_truoc` | **`NHIN_VE_TUONG_LAI`** | **phải trễ đi, không dùng được tại `T`** |
| cả hai đều nhỏ và tương đương | `BIEN_MUC` | biến trạng thái, dùng được tại `T` |

"Mạnh" và "hẳn" cần một mốc, và ta **có sẵn một mốc hiệu chuẩn hoàn hảo**: order flow của
chính ta. Nến giờ `H` gộp giao dịch trong `[H, H+1h)`, nên `delta` tại `H` là biến dòng chảy
nhìn về quá khứ **theo định nghĩa**. Nó cho `+0,7531` với giờ của chính nó.

**Bắt buộc chạy `delta` của ta như dòng đầu tiên của bảng**, làm đối chứng. Nếu nó không được
phân loại `NHIN_VE_QUA_KHU` thì công cụ hỏng, dừng lại.

Quy tắc cụ thể, dùng đúng thế này:

```
bat_doi_xung = |corr_sau| - |corr_truoc|
NHIN_VE_TUONG_LAI  khi bat_doi_xung >  0.03
NHIN_VE_QUA_KHU    khi bat_doi_xung < -0.03
BIEN_MUC           khi |bat_doi_xung| <= 0.03
```

### 1.3. Chạy trên sáu cột

`delta` (của ta, đối chứng), `sum_open_interest`, `count_long_short_ratio`,
`count_toptrader_long_short_ratio`, `sum_toptrader_long_short_ratio`,
`sum_taker_long_short_vol_ratio`.

**Loại các dòng có `sum_open_interest = 0`** trước khi tính — đó là dữ liệu khuyết (đợt 41 §0.2).

### 1.4. Kiểm chứng Task 1

1. `delta` của ta ra `NHIN_VE_QUA_KHU` với `corr_truoc ≈ +0,75`.
2. `sum_taker_long_short_vol_ratio` ra **`NHIN_VE_TUONG_LAI`**. Đây là phép tái lập chẩn đoán
   của tôi — nếu nó không ra như vậy, dừng lại và báo cáo, đừng sửa ngưỡng cho khớp.
3. Ba cột tỷ lệ còn lại ra `BIEN_MUC`.
4. Chạy hai lần cho kết quả giống hệt.

---

## Task 2 — Sửa luật căn dòng trong `trading/feature_panel.py`

### 2.1. Luật mới

Thay luật cũ (*"mốc 5 phút gần nhất có `ts <= close_ts`"*) bằng:

> Lấy mốc metrics gần nhất thoả **`ts + 5 phút <= close_ts`**.

Tức mốc đó phải có **cửa sổ đã đóng hoàn toàn** tại hoặc trước `close_ts`. Ở `close_ts = 10:00`,
mốc muộn nhất dùng được là `09:55` (phủ `09:55–10:00`, hoàn tất đúng lúc `10:00`).

Áp cho **toàn bộ** các cột metrics, kể cả ba cột `BIEN_MUC`. Lý do: đồng nhất một luật dễ kiểm
hơn ba luật, và chi phí của việc thận trọng thừa với biến mức là 5 phút — bằng không.

Thêm tham số `metric_lag_minutes: int = 5` để §3.2 chạy được biến thể biên an toàn rộng hơn.

Giữ nguyên `max_metric_staleness_minutes` và mọi thứ khác.

### 2.2. Về việc sửa test — đọc kỹ

Thay đổi này **đổi hành vi**, nên các test **có chủ đề là căn dòng metrics** buộc phải đổi.
Đó là hợp lệ. Nhưng:

- **Chỉ được sửa test số 2** (`test_2_metrics_staleness`) và thêm test mới.
- **Bảy test còn lại giữ nguyên, không sửa một `assert` nào.** Đặc biệt test 1 (funding không
  nhìn trước), test 3 (OI bằng 0), test 7 (biến mục tiêu), test 8 (cắt cụt).
- Dán `git diff` của `tests/test_feature_panel.py` để tôi tự đối chiếu từng dòng.

Nếu bạn thấy phải sửa một test ngoài số 2 để nó xanh → **dừng, báo cáo**. Nghĩa là thay đổi đã
lan rộng hơn dự định.

### 2.3. Ba test mới

9. **Mốc hoàn tất đúng lúc `close_ts` được dùng:** mốc `09:55` với `close_ts = 10:00` → dùng được.
10. **Mốc chưa hoàn tất bị loại:** mốc `10:00` với `close_ts = 10:00` → **không** được dùng;
    hàng phải lấy `09:55`. Đây là bài test bắt đúng lỗi của đợt 41.
11. `metric_lag_minutes = 10` → mốc muộn nhất dùng được tại `close_ts = 10:00` là `09:50`.

---

## Task 3 — Chạy lại kiểm toán, kèm phép kiểm biên an toàn

**Chỉ bắt đầu sau khi Task 1 và 2 đạt.**

### 3.1. Chạy lại nguyên xi

Cùng 27 cặp, cùng hoán vị theo khối 48 giờ, cùng 1000 lần, cùng IS `2024-01-01 → 2025-12-31`,
cùng hạt giống. **2026 vẫn niêm phong.** Chỉ khác một điều: bảng đặc trưng đã sửa căn dòng.

Dùng `calculate_percentile` và `empirical_percentile_rank` từ `trading.metrics`. Không viết lại.

### 3.2. Phép kiểm biên an toàn — bắt buộc

Chạy lại toàn bộ lần thứ hai với `metric_lag_minutes = 10` (thêm một chu kỳ 5 phút dư).

Báo cáo **cả hai cột `ρ`** cạnh nhau cho cả 27 cặp.

**Cách đọc:** một quan hệ thật thì `ρ` gần như không đổi khi thêm 5 phút biên — thông tin
không bốc hơi trong 5 phút. Một quan hệ do rò rỉ thì `ρ` **sụt mạnh**. Nêu rõ bạn thấy cái nào.

### 3.3. Kiểm chứng Task 3

1. Đối chứng dương và đối chứng âm của đợt 41 vẫn xanh.
2. `sum_taker_long_short_vol_ratio × fwd_ret_1h`: nêu `ρ` **trước** (đợt 41: `+0,1743`) và
   **sau** khi sửa. Tôi kỳ vọng nó sụt mạnh. Nếu nó **không** sụt → dừng lại và báo cáo, nghĩa
   là chẩn đoán của tôi ở §0.1 sai và cần xem lại.
3. Số hàng mỗi cặp giảm không quá vài chục so với đợt 41 (chỉ mất phần warm-up ở đầu chuỗi).
   Giảm hàng nghìn nghĩa là luật mới đang rớt dữ liệu sai.
4. Ngưỡng phân vị 95 của phân phối null giá trị lớn nhất — nêu con số (đợt 41: `0,075267`).

---

## Task 4 — Kiểm điều kiện hợp của tài liệu: `scripts/event_study_module_c.py`

**Đây là việc mà cả đợt 40 và 41 tồn tại để phục vụ.**

### 4.1. Điều kiện, lấy nguyên văn tài liệu §6.2, chiều LONG

Tất cả tính tại close nến 1 giờ `t`, trên dữ liệu **Binance** (nến Binance, funding Binance,
OI Binance, delta của ta):

| Thành phần | Điều kiện |
|---|---|
| Xu hướng | `close > EMA50` **và** `EMA20 > EMA50` **và** `EMA50_t > EMA50_{t-3}` |
| Funding | `funding_z < +1.0` |
| OI | `OI_t / OI_{t-3h} - 1 <= -0.015` |
| Nến xác nhận | `close > EMA20` |
| Order flow | `delta_norm > 0` **và** `cvd_3h(t) > cvd_3h(t-3)` |
| **Liquidation** | **BỎ — dữ liệu không tồn tại** |

Dùng `EmaCalculator` sẵn có trong `trading/indicators.py` (**chỉ import, không sửa**).
`funding_z` và các đặc trưng khác lấy từ bảng đặc trưng đã sửa ở Task 2.

**Tên gọi bắt buộc trong mọi dòng báo cáo: "module C thiếu vế liquidation".** Không được gọi
là "module C". Giống hệt cách đợt 37 phải dùng chữ `price-only`.

### 4.2. Phép đo

Với các giờ `t` mà điều kiện đúng (gọi là **sự kiện**), tính lợi suất tương lai trung bình ở
`1h`, `4h`, `24h`, so với **trung bình không điều kiện** của toàn bộ giờ trong IS.

**Phép kiểm ý nghĩa — hoán vị vị trí sự kiện:** giữ nguyên **số lượng** sự kiện, đặt chúng vào
các vị trí ngẫu nhiên trong chuỗi (theo khối 48 giờ, cùng lý do §0.3 đợt 41), tính lại lợi
suất trung bình, lặp **1000 lần** → phân phối null. Hạt giống cố định.

**Tiêu chí chốt trước — cả ba phải đúng:**

1. Số sự kiện **≥ 30**, **và**
2. Lợi suất tương lai trung bình **> 0** ở ít nhất một chân trời, **và**
3. Lợi suất đó nằm **trên phân vị 95** của phân phối null.

Thiếu một điều → **kết quả âm**. Không nới điều kiện để có thêm sự kiện. Không thử chiều SHORT
rồi lấy cái nào đẹp hơn — **nếu chạy cả chiều SHORT thì phải báo cáo cả hai**, và khi đó ngưỡng
phải tính trên **giá trị lớn nhất của hai chiều × ba chân trời** (sáu phép kiểm), đúng cách
đợt 41 đã làm với 27 cặp.

### 4.3. Nếu số sự kiện quá ít

Điều kiện có sáu vế cùng lúc nên rất có thể chỉ kích hoạt vài lần trong hai năm. **Nếu dưới 30
sự kiện: báo cáo con số, ghi "không đủ lực thống kê", và DỪNG.**

**Không** nới ngưỡng `-0.015`, **không** bỏ bớt vế, **không** kéo dài cửa sổ để có thêm mẫu.
Nới điều kiện sau khi thấy số sự kiện là dò tham số, và nó sẽ tạo ra một kết quả dương giả mà
không phép kiểm nào cứu được.

Kèm theo, báo cáo **số giờ thoả từng vế riêng lẻ** — để biết vế nào là vế chặn. Đó là thông
tin chẩn đoán hữu ích và nó **không** phải là dò tham số, miễn là bạn không dùng nó để sửa
điều kiện trong cùng đợt này.

### 4.4. Kiểm chứng Task 4 — `tests/test_event_study.py`

1. Chuỗi dựng tay có đúng một giờ thoả cả sáu vế → phát hiện đúng một sự kiện, đúng vị trí.
2. Tắt từng vế một (dựng chuỗi vi phạm đúng vế đó) → không có sự kiện. Sáu bài, mỗi vế một bài.
3. **Đối chứng dương:** chuỗi tổng hợp trong đó mọi sự kiện đều được theo sau bởi mức tăng mạnh
   → lợi suất trung bình vượt phân vị 95 áp đảo.
4. **Đối chứng âm:** chuỗi bước ngẫu nhiên, hạt giống cố định → không vượt.
5. Chạy hai lần cùng hạt giống → giống hệt.

---

## 5. Báo cáo cho Claude

1. `npx gitnexus analyze` trước và sau.
2. `git diff --stat`, `git status --short`, và **`git diff tests/test_feature_panel.py`** để
   tôi đối chiếu từng dòng (§2.2).
3. Task 1: bảng sáu cột với `corr_truoc`, `corr_sau`, nhãn phân loại.
4. Task 2: kết quả 11 test (8 cũ + 3 mới), nói rõ **chỉ test số 2 bị sửa**.
5. Task 3: bảng 27 cặp với **hai cột `ρ`** (biên 5 phút và 10 phút), ngưỡng, và con số
   `taker_ls_vol_ratio × fwd_ret_1h` trước/sau.
6. Task 4: số sự kiện, lợi suất trung bình ba chân trời, phân vị, kết luận theo §4.2, và bảng
   số giờ thoả từng vế.
7. Ba dòng: số test pass (mốc **728**), ruff, cổng cứng VN đủ bốn con số.
8. Đường dẫn file nghiên cứu mới.

**Không commit, không push.**

---

## 6. Điều KHÔNG thuộc phạm vi

- **Không đụng dữ liệu 2026.** Vẫn niêm phong. Kể cả khi Task 4 cho kết quả dương — OOS là của
  đợt 43.
- **Không xây chiến lược, không backtest, không tính phí, không luật vào/ra.** Task 4 là
  event study, không phải backtest: nó đo lợi suất thô sau sự kiện, không mô phỏng lệnh.
- **Không** thêm đặc trưng mới. Chín cái, không hơn.
- **Không** thử biến thể nào của điều kiện module C. Một điều kiện, khai báo trước, chạy một lần.
- **Không** bịa proxy liquidation.
- **Không** nới điều kiện để có thêm sự kiện. Xem §4.3.
- **Không** ghép nến BingX với dữ liệu Binance.
- Ba việc bên đường VN vẫn là quyết định của chủ dự án: `powercfg /change standby-timeout-dc 0`,
  đăng ký scheduled task chuông 2C, và brief 36 Task 3 sau 15:05 thứ Hai 14/09.
