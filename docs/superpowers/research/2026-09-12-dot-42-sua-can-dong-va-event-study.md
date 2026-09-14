# Báo cáo Nghiên cứu Đợt 42 — Sửa Lỗi Căn Dòng, Dựng Phép Phòng và Kiểm Luận Điểm Tài Liệu

- **Ngày thực hiện:** 14/09/2026
- **Mã thực thi:** Gemini Flash 3.8
- **Auditor / Planner:** Claude
- **Mục tiêu:**
  1. Dựng công cụ đo hướng ngữ nghĩa timestamp (`scripts/probe_timestamp_semantics.py`) để xác định biến dòng chảy/mức nhìn về quá khứ hay tương lai.
  2. Sửa luật căn dòng trong `trading/feature_panel.py` chống nhìn trước (`ts + metric_lag_minutes <= close_ts` với `metric_lag_minutes = 5`).
  3. Kiểm toán lại 27 cặp đặc trưng phi giá trên In-Sample (2024–2025) kèm phép kiểm biên an toàn 10 phút.
  4. Thực hiện Event Study kiểm chứng điều kiện hợp lấy nguyên văn §6.2 tài liệu: **"module C thiếu vế liquidation"**.

---

## 1. Task 1 — Phép Đo Hướng Ngữ Nghĩa Timestamp

- Script: [`scripts/probe_timestamp_semantics.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/probe_timestamp_semantics.py)
- Đo tương quan Pearson giữa giá trị tại mốc $T$ (đầu giờ, `minute = 0`) với:
  - $r_{\text{truoc}}(T)$: Lợi suất nến 1h kết thúc tại $T$ ($[T-1h, T)$).
  - $r_{\text{sau}}(T)$: Lợi suất nến 1h bắt đầu tại $T$ ($[T, T+1h)$).
  - Bất đối xứng: $|corr_{\text{sau}}| - |corr_{\text{truoc}}|$. Ngưỡng: $> +0.03 \implies$ `NHIN_VE_TUONG_LAI`, $< -0.03 \implies$ `NHIN_VE_QUA_KHU`, còn lại `BIEN_MUC`.
- Lọc bỏ các dòng có `sum_open_interest <= 0` hoặc `sum_open_interest_value <= 0`.

### Kết quả đo trên 6 cột:

| Cột | $N$ | `corr_truoc` | `corr_sau` | Bất đối xứng | Phân loại | Ghi chú |
|---|---|---|---|---|---|---|
| **delta (của ta, đối chứng)** | 23,375 | **+0.7531** | +0.0021 | -0.7509 | `NHIN_VE_QUA_KHU` | Đối chứng mốc chuẩn đạt chuẩn xác |
| `sum_open_interest` | 23,334 | -0.0034 | -0.0118 | +0.0084 | `BIEN_MUC` | Biến trạng thái |
| `count_long_short_ratio` | 23,332 | -0.0314 | -0.0148 | -0.0166 | `BIEN_MUC` | Biến trạng thái |
| `count_toptrader_long_short_ratio` | 23,330 | -0.0477 | -0.0142 | -0.0335 | `NHIN_VE_QUA_KHU` | Trạng thái / nhìn về quá khứ nhẹ |
| `sum_toptrader_long_short_ratio` | 23,331 | -0.0206 | -0.0131 | -0.0076 | `BIEN_MUC` | Biến trạng thái |
| **`sum_taker_long_short_vol_ratio`** | 23,334 | -0.0333 | **+0.1275** | **+0.0942** | **`NHIN_VE_TUONG_LAI`** | **Xác nhận 100% chẩn đoán rò rỉ!** |

- Kết quả chạy 2 lần độc lập cho ra các giá trị giống hệt 100%.
- Kết luận Task 1: `sum_taker_long_short_vol_ratio` mang nhãn $T$ mô tả cửa sổ $[T, T+5m)$, nên dùng nó tại $T = \text{close\_ts}$ là đưa 5 phút tương lai của nến tiếp theo vào. Bắt buộc phải lùi ít nhất 5 phút.

---

## 2. Task 2 — Sửa Luật Căn Dòng Trong `trading/feature_panel.py`

- Luật căn dòng mới:
  $$\text{metric.ts} + \text{timedelta}(\text{minutes}=\text{metric\_lag\_minutes}) \le \text{target\_ts}$$
  Mặc định: `metric_lag_minutes = 5`. Áp dụng đồng nhất cho toàn bộ các cột metrics.
  Tại $\text{close\_ts} = 10:00$, mốc muộn nhất hợp lệ là $09:55$. Mốc $10:00$ bị loại bỏ.
- Test suite [`tests/test_feature_panel.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_feature_panel.py):
  - Sửa `test_2_metrics_staleness`: chuyển timestamp sang `00:40` (hoàn tất lúc `00:45`, cách `close_ts` 15m > 10m) để kiểm tra staleness đúng chuẩn.
  - Test 3 (`test_3_oi_zero_becomes_null_ratio_preserved`): Chuyển timestamp `m_now` từ `01:00` sang `00:55` (mốc hoàn tất đúng lúc `close_ts = 01:00`) để tuân thủ luật căn dòng mới; toàn bộ các dòng `assert` giữ nguyên 100%.
  - Thêm 3 bài test mới:
    - Test 9: Mốc hoàn tất đúng lúc `close_ts` (`09:55` với `close_ts = 10:00`) được chấp nhận.
    - Test 10: Mốc chưa hoàn tất (`10:00` với `close_ts = 10:00`) bị loại bỏ, panel lấy mốc `09:55`.
    - Test 11: `metric_lag_minutes = 10` $\implies$ mốc muộn nhất hợp lệ tại `close_ts = 10:00` là `09:50`.
  - Kết quả: **11/11 tests pass**. 7 bài test còn lại giữ nguyên toàn bộ assertions.

---

## 3. Task 3 — Chạy Lại Kiểm Toán và Phép Kiểm Biên An Toàn

- Script: [`scripts/audit_information.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/audit_information.py)
- Cấu hình: In-Sample 2024-01-01 $\to$ 2025-12-31 UTC (17,544 hàng). Năm 2026 niêm phong. Hoán vị khối 48h x 1,000 lần.
- Ngưỡng phân vị 95 của phân phối Null $\max(|\rho|)$: **`0.075288`** (đợt 41: `0.075267`).
- Đối chứng:
  - Dương (`ctrl_cheat × fwd_ret_1h`): $\rho = +0.9995$ (vượt ngưỡng áp đảo).
  - Âm (`ctrl_noise × fwd_ret_1h`): $\rho = -0.0082$ (không vượt ngưỡng).

### Bảng đối chiếu 27 cặp (Lag 5m vs Lag 10m biên an toàn):

| Đặc trưng | Mục tiêu | $\rho$ (lag 5m) | $\rho$ (lag 10m) | $\Delta \rho$ | Số hàng (5m) | Vượt ngưỡng Null P95? |
|---|---|---|---|---|---|---|
| `oi_chg_24h` | `fwd_ret_24h` | -0.062189 | -0.060291 | +0.001898 | 17,442 | Không |
| `toptrader_ls_ratio` | `fwd_ret_24h` | -0.058300 | -0.058351 | -0.000051 | 17,530 | Không |
| `oi_chg_24h` | `fwd_ret_4h` | -0.046196 | -0.045208 | +0.000988 | 17,442 | Không |
| `cvd_chg_3h` | `fwd_ret_1h` | -0.036859 | -0.036859 | 0.000000 | 17,542 | Không |
| `delta_norm` | `fwd_ret_1h` | -0.029674 | -0.029674 | 0.000000 | 17,544 | Không |
| **`taker_ls_vol_ratio`** | **`fwd_ret_1h`** | **-0.028403** | **-0.014434** | **+0.013969** | **17,533** | **Không** |
| `oi_chg_3h` | `fwd_ret_24h` | -0.027656 | -0.026342 | +0.001314 | 17,469 | Không |
| `long_short_ratio` | `fwd_ret_24h` | -0.022431 | -0.022497 | -0.000065 | 17,531 | Không |
| `toptrader_ls_ratio` | `fwd_ret_4h` | -0.020599 | -0.020522 | +0.000077 | 17,530 | Không |
| `oi_chg_3h` | `fwd_ret_4h` | -0.020163 | -0.019517 | +0.000646 | 17,469 | Không |
| `oi_chg_24h` | `fwd_ret_1h` | -0.018387 | -0.017501 | +0.000886 | 17,442 | Không |
| `cvd_chg_3h` | `fwd_ret_4h` | -0.018313 | -0.018313 | 0.000000 | 17,542 | Không |
| `funding_z` | `fwd_ret_24h` | -0.016732 | -0.016732 | 0.000000 | 15,385 | Không |
| `delta_norm` | `fwd_ret_4h` | -0.015713 | -0.015713 | 0.000000 | 17,544 | Không |
| `taker_ls_vol_ratio` | `fwd_ret_4h` | -0.010732 | -0.012957 | -0.002225 | 17,533 | Không |
| `delta_norm` | `fwd_ret_24h` | -0.010347 | -0.010347 | 0.000000 | 17,544 | Không |
| `funding_z` | `fwd_ret_4h` | -0.008983 | -0.008983 | 0.000000 | 15,385 | Không |
| `cvd_chg_3h` | `fwd_ret_24h` | -0.006540 | -0.006540 | 0.000000 | 17,542 | Không |
| `taker_ls_vol_ratio` | `fwd_ret_24h` | -0.006090 | -0.006935 | -0.000845 | 17,533 | Không |
| `toptrader_ls_ratio` | `fwd_ret_1h` | -0.005842 | -0.005845 | -0.000003 | 17,530 | Không |
| `oi_chg_3h` | `fwd_ret_1h` | -0.005689 | -0.004077 | +0.001612 | 17,469 | Không |
| `funding_rate` | `fwd_ret_4h` | -0.004587 | -0.004587 | 0.000000 | 17,544 | Không |
| `funding_rate` | `fwd_ret_24h` | -0.003675 | -0.003675 | 0.000000 | 17,544 | Không |
| `funding_z` | `fwd_ret_1h` | -0.003091 | -0.003091 | 0.000000 | 15,385 | Không |
| `funding_rate` | `fwd_ret_1h` | +0.002339 | +0.002339 | 0.000000 | 17,544 | Không |
| `long_short_ratio` | `fwd_ret_1h` | +0.000535 | +0.000516 | -0.000019 | 17,531 | Không |
| `long_short_ratio` | `fwd_ret_4h` | +0.000134 | +0.000121 | -0.000013 | 17,531 | Không |

### Nhận xét kiểm chứng:
1. `taker_ls_vol_ratio × fwd_ret_1h`: Ở đợt 41 là `+0.1743` (vượt ngưỡng giả do rò rỉ). Sau khi căn dòng chuẩn 5m, $\rho$ sụt mạnh xuống **`-0.028403`**. Khi lùi thêm 10m biên an toàn, $\rho = -0.014434$. Hiện tượng sụt giảm mạnh này xác nhận chính xác rằng con số `+0.1743` trước đây hoàn toàn là do rò rỉ 5 phút đầu cửa sổ.
2. Số hàng hợp lệ: giảm từ 17,543 xuống 17,533 (chỉ mất 10 hàng do warm-up đầu chuỗi).
3. **Kết luận kiểm toán đơn lẻ:** **KHÔNG CÓ bất kỳ cặp nào trong 27 cặp vượt ngưỡng ý nghĩa đa phép kiểm Null P95 (`0.075288`).**

---

## 4. Task 4 — Kiểm Luận Điểm Tài Liệu: Event Study "Module C Thiếu Vế Liquidation"

- Script: [`scripts/event_study_module_c.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/event_study_module_c.py)
- Tests: [`tests/test_event_study.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_event_study.py) (5/5 tests pass).
- Tên gọi bắt buộc: **"module C thiếu vế liquidation"** (do Binance không có liquidation feed lịch sử).
- 6 điều kiện LONG nguyên văn §6.2:
  - Xu hướng: `close > EMA50` và `EMA20 > EMA50` và $\text{EMA50}_t > \text{EMA50}_{t-3}$
  - Funding: `funding_z < +1.0`
  - OI: `oi_chg_3h <= -0.015`
  - Nến xác nhận: `close > EMA20`
  - Order flow: `delta_norm > 0` và $\text{cvd\_chg\_3h}(t) > \text{cvd\_chg\_3h}(t-3)$
  - Liquidation: BỎ.

### 4.1. Bảng số giờ thoả mãn từng vế riêng lẻ (IS 17,544 nến):

| Vế | Điều kiện | Số giờ thoả | Tỷ lệ (%) | Nhận định |
|---|---|---|---|---|
| 1 | Xu hướng EMA (`close>EMA50 & EMA20>EMA50 & EMA50_t>EMA50_{t-3}`) | 7,850 | 44.74% | Bình thường |
| 2 | Funding (`funding_z < +1.0`) | 12,820 | 73.07% | Đa số thời gian |
| 3 | **OI (`oi_chg_3h <= -0.015`)** | **1,173** | **6.69%** | **VẾ CHẶN CHÍNH** (co cụm lệnh) |
| 4 | Nến xác nhận (`close > EMA20`) | 9,304 | 53.03% | Bình thường |
| 5 | Order flow (`delta_norm > 0 & cvd_3h_t > cvd_3h_{t-3}`) | 5,048 | 28.77% | Chọn lọc dòng tiền mua chủ động |
| **HỢP** | **HỢP CẢ 5 VẾ (module C thiếu vế liquidation)** | **72** | **0.41%** | **$N = 72 \ge 30$ (ĐỦ LỰC THỐNG KÊ)** |

### 4.2. Phép đo lợi suất tương lai và kiểm định ý nghĩa (Hoán vị khối 48h x 1,000 lần):

| Chân trời | Lợi suất TB Sự kiện | Lợi suất TB Không điều kiện | Chênh lệch (Excess Return) | Ngưỡng Null P95 | Vượt P95? |
|---|---|---|---|---|---|
| **1h** | **+0.1285%** | **+0.0055%** | **+0.1231%** | **+0.1083%** | **CÓ (VƯỢT)** |
| **4h** | **+0.2334%** | +0.0218% | +0.2116% | +0.2426% | Không (sát P95) |
| **24h** | **+0.1972%** | +0.1288% | +0.0684% | +0.7511% | Không |

### 4.3. Đánh giá theo 3 tiêu chí chốt trước (§4.2):
1. **Số sự kiện $\ge 30$:** $N = 72 \ge 30 \implies$ **ĐẠT** (đủ lực thống kê).
2. **Lợi suất tương lai TB $> 0$ ở ít nhất một chân trời:** Cả 3 chân trời đều có lợi suất TB dương ($+0.1285\%$, $+0.2334\%$, $+0.1972\%$) $\implies$ **ĐẠT**.
3. **Lợi suất nằm trên phân vị 95 của phân phối null:** Chân trời 1h đạt $+0.1285\% > +0.1083\%$ (Null P95) $\implies$ **ĐẠT**.

### Kết luận Task 4:
**KẾT QUẢ: DƯƠNG.**
Luận điểm của tài liệu §6.2 về **điều kiện hợp "module C thiếu vế liquidation"** là **CÓ CƠ SỞ THỐNG KÊ** trên tập In-Sample Binance BTCUSDT. Dù từng đặc trưng đơn lẻ không có tương quan tuyến tính riêng lẻ, nhưng sự kết hợp đồng thời của bộ lọc xu hướng + funding bình tĩnh + OI sụt giảm (thanh lý/ép vị thế) + lực mua chủ động xác nhận (delta & CVD tăng) tạo ra lợi thế thống kê thực sự có ý nghĩa ở khung 1 giờ.

---

## Ghi chú của người kiểm chứng (Claude, 14/09/2026) — BÁC BỎ KẾT LUẬN "DƯƠNG"

**Task 1, 2, 3 đạt và tôi giữ nguyên.** Phép đo hướng tái lập đúng chẩn đoán: `delta` của ta
ra `NHIN_VE_QUA_KHU` (+0,7531), `sum_taker_long_short_vol_ratio` ra `NHIN_VE_TUONG_LAI`
(+0,1275 với giờ sau, −0,0333 với giờ trước). Rò rỉ đã bịt: `+0,1743 → −0,0284`.

**Task 4 kết luận "DƯƠNG" không đứng được.** Ba lý do, xếp theo sức nặng.

### 1. Ba chân trời được thử, đúng một cái vượt

```
Chân trời | Lợi suất TB SK | Null P95  | Vượt?
1h        | +0.1285%       | +0.1083%  | CÓ
4h        | +0.2334%       | +0.2426%  | Không
24h       | +0.1972%       | +0.7511%  | Không
```

Thử ba phép kiểm ở mức 95% thì xác suất **ít nhất một** cái vượt do may rủi là
`1 − 0,95³ ≈ 14%`. Kết quả này nằm gọn trong vùng may rủi.

Ngưỡng đúng là phân vị 95 của **giá trị lớn nhất** trên ba chân trời — chính phương pháp tôi
bắt buộc ở brief 41 §3.2 cho 27 cặp, và repo đã có sẵn công cụ (`calculate_percentile`,
`empirical_percentile_rank` trong `trading.metrics`). Với ba phép kiểm, ngưỡng đó tương đương
phân vị ~98,3 chứ không phải 95. Kết quả 1h không tới đó.

**Đây là lỗi của tôi.** Brief 42 §4.2 tôi viết *"> 0 ở ít nhất một chân trời, và lợi suất đó
nằm trên phân vị 95"* — cách viết đó cho phép ngưỡng theo từng chân trời. Tôi có nghĩ tới đa
phép kiểm (điều khoản về chiều SHORT nói rõ "sáu phép kiểm") nhưng quên áp cho ba chân trời.

### 2. Biên vượt nhỏ hơn một phần ba sai số chuẩn

Biên là `+0,0202` điểm phần trăm trên 72 sự kiện. Độ lệch chuẩn lợi suất giờ của BTC cỡ `0,5%`,
nên sai số chuẩn của trung bình là `0,5% / √72 ≈ 0,059%`. Biên vượt bằng **khoảng một phần ba
của một sai số chuẩn**.

### 3. Và đây là lý do không cần tới thống kê

Lợi thế, lấy đúng mặt giá trị: **+12,85 điểm cơ bản mỗi sự kiện**.

Phí taker một vòng mua-bán: **10 điểm cơ bản** (5 mỗi chiều). Còn lại **~2,85 điểm cơ bản**
trước trượt giá, trước funding, trước mọi sai lệch khớp lệnh.

Một lợi thế 2,85 điểm cơ bản trên 72 lệnh trong hai năm không phải là một chiến lược. Kể cả
khi nó có thật.

### Kết luận đúng của Task 4

**Không có bằng chứng** cho điều kiện hợp "module C thiếu vế liquidation" trên IS 2024–2025.

Bảng số giờ thoả từng vế vẫn là thông tin hữu ích và được giữ: vế chặn là **OI (6,69%)**,
và hợp cả năm vế chỉ còn **72 giờ / 0,41%**.

Đợt sau nếu quay lại hướng này: dùng thống kê giá trị lớn nhất trên **mọi** chân trời và
**mọi** chiều, và đặt ngưỡng lợi thế tối thiểu **trên chi phí vòng lệnh** trước khi chạy bất
kỳ phép kiểm nào. 2026 vẫn niêm phong.