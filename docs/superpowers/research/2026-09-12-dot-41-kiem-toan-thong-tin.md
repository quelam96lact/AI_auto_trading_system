# Báo cáo Nghiên cứu Đợt 41 — Kiểm toán Thông tin Dữ liệu Phi Giá Binance

> **KẾT QUẢ DƯƠNG Ở MỤC 6 ĐÃ BỊ BÁC BỎ. ĐỌC MỤC 8 TRƯỚC.** Hai cặp "vượt ngưỡng" là
> hiện vật của lỗi căn dòng thời gian trong brief của Claude, không phải thông tin dự báo.

**Ngày thực hiện:** 12/09/2026  
**Thực thi:** Gemini Flash 3.8  
**Ràng buộc kiểm định:**
- Kiểm toán thông tin trước khi xây chiến lược (§0.1).
- Áp dụng luật loại bỏ dữ liệu hỏng: `sum_open_interest = 0` được quy về `NULL` (§0.2).
- Chống nhìn trước tuyệt đối (chỉ dùng dữ liệu tại hoặc trước `close_ts`).
- Tập In-Sample (IS): `2024-01-01 00:00:00+00` → `2025-12-31 23:00:00+00` UTC (17,544 nến). **Năm 2026 niêm phong**.
- Hiệu chỉnh đa phép kiểm họ (Family-wise) bằng Block Permutation Test 48h (1,000 lần hoán vị).

---

## 1. Task 1: Tiến độ và Kết quả Nạp 32 Tháng Order Flow

### 1.1. Bảng tiến độ nạp 32 tháng (`2024-01` → `2026-08`)
Toàn bộ 32 tháng được nạp cuốn chiếu, kiểm tra checksum SHA256 và xoá tệp ZIP thô ngay sau khi gộp:

| Tháng | Kích thước ZIP | Thời gian tải | Thời gian gộp | Số lệnh aggTrade | Số nến 1h | Trạng thái |
|---|---|---|---|---|---|---|
| `2024-01` | 498.53 MB | 60.9s | 310.4s | 40,294,620 | 744 | Nạp mới |
| `2024-02` | 450.47 MB | 49.3s | 173.9s | 36,317,913 | 696 | Nạp mới |
| `2024-03` | 808.15 MB | 92.0s | 319.7s | 66,512,993 | 744 | Nạp mới |
| `2024-04` | 642.28 MB | 72.4s | 264.5s | 52,506,247 | 720 | Nạp mới |
| `2024-05` | 478.81 MB | 55.6s | 199.5s | 38,945,717 | 744 | Nạp mới |
| `2024-06` | 324.28 MB | 40.2s | 142.2s | 26,121,815 | 720 | Nạp mới |
| `2024-07` | 465.71 MB | 51.3s | 198.7s | 37,540,956 | 744 | Nạp mới |
| `2024-08` | 592.40 MB | 66.9s | 272.8s | 47,852,373 | 744 | Nạp mới |
| `2024-09` | 436.17 MB | 54.2s | 180.7s | 35,336,026 | 720 | Nạp mới |
| `2024-10` | 458.55 MB | 52.6s | 191.0s | 37,629,336 | 744 | Nạp mới |
| `2024-11` | 696.13 MB | 80.4s | 327.9s | 57,556,232 | 720 | Nạp mới |
| `2024-12` | 652.23 MB | 89.0s | 299.9s | 54,359,176 | 744 | Nạp mới |
| `2025-01` | 660.29 MB | 98.6s | 314.8s | 55,419,154 | 744 | Nạp mới |
| `2025-02` | 541.24 MB | 62.0s | 259.4s | 45,375,119 | 672 | Nạp mới |
| `2025-03` | 675.76 MB | 72.2s | 289.8s | 56,907,638 | 744 | Nạp mới |
| `2025-04` | 568.56 MB | 61.4s | 243.7s | 47,606,423 | 720 | Nạp mới |
| `2025-05` | 480.73 MB | 52.4s | 220.0s | 40,551,557 | 744 | Nạp mới |
| `2025-06` | 388.88 MB | 39.2s | 292.7s | 32,593,669 | 720 | Nạp mới |
| `2025-07` | 374.91 MB | 38.1s | 189.8s | 31,343,481 | 744 | Nạp mới |
| `2025-08` | 410.22 MB | 44.3s | 178.0s | 34,721,406 | 744 | Nạp mới |
| `2025-09` | 322.87 MB | 32.8s | 149.8s | 27,229,666 | 720 | Nạp mới |
| `2025-10` | 647.24 MB | 63.6s | 295.3s | 55,717,206 | 744 | Nạp mới |
| `2025-11` | 740.94 MB | 77.2s | 313.2s | 63,853,937 | 720 | Nạp mới |
| `2025-12` | 581.09 MB | 55.9s | 279.5s | 49,985,748 | 744 | Nạp mới |
| `2026-01` | 517.61 MB | 49.6s | 297.2s | 44,701,670 | 744 | *Đã có (Đợt 40) - Bỏ qua* |
| `2026-02` | 960.08 MB | 97.7s | 406.6s | 84,154,791 | 672 | Nạp mới |
| `2026-03` | 762.20 MB | 80.1s | 359.1s | 65,679,961 | 744 | Nạp mới |
| `2026-04` | 484.66 MB | 49.3s | 223.2s | 41,544,041 | 720 | Nạp mới |
| `2026-05` | 393.92 MB | 44.1s | 182.1s | 33,660,928 | 744 | Nạp mới |
| `2026-06` | 668.46 MB | 73.5s | 341.7s | 58,149,575 | 720 | Nạp mới |
| `2026-07` | 398.98 MB | 40.2s | 198.3s | 34,057,419 | 744 | Nạp mới |
| `2026-08` | 415.49 MB | 44.0s | 208.9s | 35,676,321 | 744 | Nạp mới |

### 1.2. Kết quả kiểm chứng Task 1 toàn kỳ (32 tháng, 23,376 nến):
1. **Số dòng và mốc thời gian:**
   - Tổng số nến: **`23,376` nến** (bằng đúng `binance_klines`, khớp 100%).
   - Mốc đầu: `2024-01-01 00:00:00+00:00 UTC`
   - Mốc cuối: `2026-08-31 23:00:00+00:00 UTC`
2. **Đối soát Taker Buy Volume trên toàn bộ 23,376 nến:**
   - So sánh `orderflow.taker_buy_volume` tự gộp vs `klines.taker_buy_volume` có sẵn:
   - **Trung vị chênh lệch:** **`0.000000%`** (ngưỡng dừng: $> 0.5\%$).
   - **Tỷ lệ nến khớp tuyệt đối:** $\approx 100\%$. Max lệch chỉ xuất hiện ở vài nến mép bảo trì sàn.
3. **Tương quan Delta và Lợi suất cùng giờ:**
   - Spearman rank correlation giữa `delta` và `(close - open) / open`: **`+0.7224`** (dương rất mạnh, khẳng định quy ước cờ maker `is_buyer_maker = false` là Taker Mua là chính xác tuyệt đối).
4. **Idempotent:** Chạy lại toàn bộ lệnh lần 2 $\rightarrow$ Bỏ qua cả 32/32 tháng, số dòng giữ nguyên 23,376.

---

## 2. Task 2: Căn Dòng Thời Gian và 8 Bài Test Kiểm Chứng

Bảng đặc trưng 1 giờ được hiện thực tại `trading/feature_panel.py` với hàm `build_feature_panel`:
- **Chống nhìn trước:** Mọi đặc trưng của nến `[ts, close_ts]` chỉ được sử dụng dữ liệu tại hoặc trước `close_ts` (`ts + 1h`).
- **Funding:** Lấy lần settle gần nhất có `funding_time <= close_ts`.
- **Metrics:** Lấy mốc 5 phút gần nhất có `ts <= close_ts`. Nếu cũ hơn 10 phút $\rightarrow$ trả về `None`.
- **Luật OI = 0:** Nếu `sum_open_interest = 0` hoặc `sum_open_interest_value = 0`, coi là `None` (không nội suy); các cột tỷ lệ L/S ở cùng dòng vẫn dùng bình thường.
- **Suite Test `tests/test_feature_panel.py`:** **8/8 test PASSED** (Funding no-lookahead, metrics staleness, OI=0 to null, 2 endpoints for OI chg, funding_z 90 days, delta_norm math, forward returns, và non-leakage truncation test).

---

## 3. Task 3: Kết Quả Kiểm Toán Thông Tin (In-Sample 2024–2025)

### 3.1. Kiểm toán đối chứng (Controls)
- **Đối chứng Dương (Cheat):** Đặc trưng `cheat = fwd_ret_1h + N(0, 0.0001)` có tương quan $\rho = \mathbf{+0.9995}$ $\rightarrow$ Vượt ngưỡng 95 áp đảo.
- **Đối chứng Âm (Noise):** Đặc trưng `noise = N(0, 1.0)` có tương quan $\rho = \mathbf{-0.0082}$ $\rightarrow$ Hoàn toàn nằm trong vùng nhiễu null.
- **Kết luận:** Công cụ kiểm toán nhạy và phân biệt tuyệt đối giữa tín hiệu thật và nhiễu ngẫu nhiên.

### 3.2. Ngưỡng ý nghĩa Đa phép kiểm (Family-wise Null Distribution)
- Phương pháp: Block Permutation Test theo khối **48 giờ** trên chuỗi lợi suất tương lai, lặp **1,000 lần**, lấy $\max_{k=1..27} |\rho_k|$.
- **Ngưỡng phân vị 95 của phân phối Null lớn nhất:**
  $$\mathbf{Threshold_{95} = 0.075267}$$

### 3.3. Bảng kết quả 27 cặp đặc trưng × biến mục tiêu

| Đặc trưng | Biến mục tiêu | Spearman $\rho$ | Số hàng hợp lệ | Vượt ngưỡng 95 ($|\rho| > 0.075267$)? |
|---|---|---|---|---|
| **`taker_ls_vol_ratio`** | **`fwd_ret_1h`** | **`+0.174257`** | **17,534** | **CÓ (VƯỢT)** |
| **`taker_ls_vol_ratio`** | **`fwd_ret_4h`** | **`+0.106023`** | **17,534** | **CÓ (VƯỢT)** |
| `oi_chg_24h` | `fwd_ret_24h` | `-0.061477` | 17,443 | Không |
| `toptrader_ls_ratio` | `fwd_ret_24h` | `-0.058220` | 17,528 | Không |
| `oi_chg_24h` | `fwd_ret_4h` | `-0.045930` | 17,443 | Không |
| `taker_ls_vol_ratio` | `fwd_ret_24h` | `+0.038672` | 17,534 | Không |
| `cvd_chg_3h` | `fwd_ret_1h` | `-0.036859` | 17,542 | Không |
| `delta_norm` | `fwd_ret_1h` | `-0.029674` | 17,544 | Không |
| `oi_chg_3h` | `fwd_ret_24h` | `-0.025636` | 17,471 | Không |
| `long_short_ratio` | `fwd_ret_24h` | `-0.022193` | 17,529 | Không |
| `oi_chg_3h` | `fwd_ret_4h` | `-0.021347` | 17,471 | Không |
| `toptrader_ls_ratio` | `fwd_ret_4h` | `-0.020515` | 17,528 | Không |
| `oi_chg_24h` | `fwd_ret_1h` | `-0.018458` | 17,443 | Không |
| `cvd_chg_3h` | `fwd_ret_4h` | `-0.018313` | 17,542 | Không |
| `funding_z` | `fwd_ret_24h` | `-0.016732` | 15,385 | Không |
| `delta_norm` | `fwd_ret_4h` | `-0.015713` | 17,544 | Không |
| `delta_norm` | `fwd_ret_24h` | `-0.010347` | 17,544 | Không |
| `funding_z` | `fwd_ret_4h` | `-0.008983` | 15,385 | Không |
| `cvd_chg_3h` | `fwd_ret_24h` | `-0.006540` | 17,542 | Không |
| `toptrader_ls_ratio` | `fwd_ret_1h` | `-0.005597` | 17,528 | Không |
| `oi_chg_3h` | `fwd_ret_1h` | `-0.004782` | 17,471 | Không |
| `funding_rate` | `fwd_ret_4h` | `-0.004587` | 17,544 | Không |
| `funding_rate` | `fwd_ret_24h` | `-0.003675` | 17,544 | Không |
| `funding_z` | `fwd_ret_1h` | `-0.003091` | 15,385 | Không |
| `funding_rate` | `fwd_ret_1h` | `+0.002339` | 17,544 | Không |
| `long_short_ratio` | `fwd_ret_1h` | `+0.001677` | 17,529 | Không |
| `long_short_ratio` | `fwd_ret_4h` | `+0.000500` | 17,529 | Không |

---

## 4. Phân Tích Thập Phân Vị (Decile Analysis) Cho 2 Cặp Mạnh Nhất

### 4.1. Cặp 1: `taker_ls_vol_ratio` × `fwd_ret_1h` ($\rho = +0.1743$)

| Thập phân vị | Số nến | Khoảng giá trị `taker_ls_vol_ratio` | Lợi suất tương lai 1h TB |
|---|---|---|---|
| Nhóm 1 (Taker Bán áp đảo) | 1,753 | `[0.09234, 0.52069]` | **`-0.0911%`** |
| Nhóm 2 | 1,753 | `[0.52071, 0.64769]` | **`-0.1027%`** |
| Nhóm 3 | 1,754 | `[0.64773, 0.75295]` | **`-0.0584%`** |
| Nhóm 4 | 1,753 | `[0.75297, 0.86363]` | **`-0.0479%`** |
| Nhóm 5 (Cận cân bằng) | 1,754 | `[0.86375, 0.98382]` | **`-0.0249%`** |
| Nhóm 6 (Bắt đầu mua ròng) | 1,753 | `[0.98385, 1.11887]` | **`+0.0037%`** |
| Nhóm 7 | 1,753 | `[1.11889, 1.28475]` | **`+0.0684%`** |
| Nhóm 8 | 1,754 | `[1.28481, 1.49752]` | **`+0.0954%`** |
| Nhóm 9 | 1,753 | `[1.49768, 1.86034]` | **`+0.1112%`** |
| Nhóm 10 (Taker Mua áp đảo)| 1,754 | `[1.86080, 11.83468]` | **`+0.1015%`** |

- **Nhận định hình dạng:** **Đơn điệu tăng rõ rệt**. Lợi suất tương lai chuyển từ âm đậm ($-0.10\%$) khi tỷ lệ taker volume mua/bán $< 0.65$ sang dương rõ rệt ($+0.10\% \rightarrow +0.11\%$) khi tỷ lệ $> 1.3$. Điểm xoay chiều nằm đúng tại ngưỡng cân bằng $1.0$. Đây là một quan hệ kinh tế có thực và phân bổ đều qua các nhóm, không phải ngoại lai.

### 4.2. Cặp 2: `taker_ls_vol_ratio` × `fwd_ret_4h` ($\rho = +0.1060$)

| Thập phân vị | Số nến | Khoảng giá trị `taker_ls_vol_ratio` | Lợi suất tương lai 4h TB |
|---|---|---|---|
| Nhóm 1 | 1,753 | `[0.09234, 0.52069]` | **`-0.0981%`** |
| Nhóm 2 | 1,753 | `[0.52071, 0.64769]` | **`-0.1238%`** |
| Nhóm 3 | 1,754 | `[0.64773, 0.75295]` | **`-0.0393%`** |
| Nhóm 4 | 1,753 | `[0.75297, 0.86363]` | **`-0.0314%`** |
| Nhóm 5 | 1,754 | `[0.86375, 0.98382]` | **`+0.0105%`** |
| Nhóm 6 | 1,753 | `[0.98385, 1.11887]` | **`+0.0091%`** |
| Nhóm 7 | 1,753 | `[1.11889, 1.28475]` | **`+0.0862%`** |
| Nhóm 8 | 1,754 | `[1.28481, 1.49752]` | **`+0.1084%`** |
| Nhóm 9 | 1,753 | `[1.49768, 1.86034]` | **`+0.1745%`** |
| Nhóm 10 | 1,754 | `[1.86080, 11.83468]` | **`+0.1223%`** |

- **Nhận định hình dạng:** Tiếp tục duy trì xu hướng **đơn điệu tăng** qua khung 4 giờ, chênh lệch giữa nhóm thấp nhất và nhóm cao nhất đạt gần $0.30\%$.

---

## 5. Kết Luận Kiểm Toán Một Dòng

> **CÓ đúng 2 cặp vượt ngưỡng ý nghĩa đa phép kiểm họ (ngưỡng 0.0753): `taker_ls_vol_ratio` với `fwd_ret_1h` ($\rho = +0.1743$) và với `fwd_ret_4h` ($\rho = +0.1060$), với cấu trúc thập phân vị đơn điệu rõ rệt.**

---

## 6. Điều Kiểm Toán Này KHÔNG Trả Lời

1. **Tương quan không phải lợi nhuận chiến lược:** $\rho = +0.1743$ chứng minh có thông tin dự báo, nhưng chưa trừ phí giao dịch (taker fee Binance 0.04% - 0.05%), trượt giá, và chưa xây dựng luật vào/ra lệnh, điểm dừng lỗ.
2. **Chỉ tuyến tính theo thứ hạng:** Spearman đo lường mối quan hệ đơn điệu theo rank, có thể bỏ sót các mối quan hệ phi tuyến phức tạp (ví dụ: biến động co thắt trước khi bung) hoặc quan hệ phụ thuộc chế độ thị trường (regime-dependent).
3. **Chỉ duy nhất mã `BTCUSDT` và trên sàn Binance:** Chưa kiểm chứng khả năng tổng quát hóa sang ETH hoặc các altcoin khác.
4. **Không có dữ liệu liquidation:** Dữ liệu thanh lý thực tế không tồn tại công khai (Đợt 40 §0.2), nên các mô hình yêu cầu liquidation vẫn bị khuyết.
5. **Năm 2026 chưa đụng tới:** Toàn bộ tập dữ liệu 2026 được niêm phong cho Out-of-Sample tại Đợt 42.

---

## 7. Tổng Kết Tình Trạng Kỹ Thuật

- **Test Suite:** **728 passed** in 60.62s (mốc cũ 716 + 12 test mới trong [tests/test_feature_panel.py](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_feature_panel.py) và [tests/test_audit_information.py](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_audit_information.py)).
- **Ruff:** Clean 100% (0 lỗi).
- **Cổng cứng VN:** Khớp tuyệt đối từng chữ số:
  `TỔNG: strat -1,615,319,902 | BH 1,897,587,481,903 | diff -1,899,202,801,806 | lệnh 1,514 | mã sinh lệnh 439 | mã đủ thanh khoản 748 | dòng bẩn 10,459`

---

## 8. Ghi chú của người kiểm chứng (Claude, 12/09/2026) — BÁC BỎ KẾT QUẢ DƯƠNG

### 8.1. Kết luận

Hai cặp `taker_ls_vol_ratio × fwd_ret_1h` (ρ = +0,1743) và `× fwd_ret_4h` (ρ = +0,1060)
**không phải thông tin dự báo. Chúng là rò rỉ nhìn trước.**

**Đây là lỗi của tôi, không phải của agent.** Brief 41 §2.2 tôi viết luật căn dòng:
*"Lấy mốc 5 phút gần nhất có `ts <= close_ts`."* Agent làm đúng chữ tôi viết. Luật đó sai với
một biến **dòng chảy** được gán nhãn theo **thời điểm bắt đầu** của cửa sổ.

### 8.2. Bằng chứng

`sum_taker_long_short_vol_ratio` là tỷ lệ khối lượng taker mua/bán trong một cửa sổ 5 phút.
Câu hỏi: nhãn `T` chỉ cửa sổ **trước** `T` hay **sau** `T`?

Tôi đo tương quan của nó với lợi suất giờ liền trước và giờ liền sau mốc `T`:

```
               cột                | giờ SAU T | giờ TRƯỚC T
----------------------------------+-----------+-------------
 sum_taker_long_short_vol_ratio   |  +0.1275  |   -0.0333
 count_long_short_ratio           |  -0.0148  |   -0.0314
 count_toptrader_long_short_ratio |  -0.0142  |   -0.0477
 sum_toptrader_long_short_ratio   |  -0.0131  |   -0.0206
```

Và đối chiếu với order flow của chính ta — nguồn có ngữ nghĩa thời gian không mơ hồ, vì nến
giờ `H` gộp các giao dịch trong `[H, H+1h)`:

```
 tỷ lệ taker của metrics tại T   vs   buy_ratio giờ BẮT ĐẦU tại T :  +0.2799
 tỷ lệ taker của metrics tại T   vs   buy_ratio giờ KẾT THÚC tại T :  -0.0045

 (đối chứng) delta của ta        vs   giờ CỦA CHÍNH NÓ            :  +0.7531
 (đối chứng) delta của ta        vs   giờ TRƯỚC ĐÓ                :  +0.0466
```

**Lập luận quyết định:** một biến dòng chảy nhìn về quá khứ **bắt buộc** phải tương quan mạnh
dương với lợi suất cùng kỳ — áp lực mua đẩy giá lên, đó là cơ học. Delta của chính ta cho
`+0,7531` đúng như vậy. Nhưng tỷ lệ taker của Binance tại `T` cho `−0,0333` với giờ trước và
`+0,1275` với giờ sau. Nó **không mô tả quá khứ**.

Kết luận: **giá trị gán nhãn `T` mô tả cửa sổ `[T, T+5 phút)`, và không thể biết được tại
`T`.** Dùng nó tại `close_ts` là đưa 5 phút đầu tiên của chính cửa sổ lợi suất tương lai vào
làm đầu vào.

Điều này giải thích trọn vẹn hình dạng suy giảm `0,174 → 0,106 → 0,039`: phần rò rỉ là 5 trên
60 phút với chân trời 1 giờ, 5 trên 240 với 4 giờ, 5 trên 1440 với 24 giờ. Nó cũng giải thích
vì sao thập phân vị đơn điệu đẹp như vậy — dòng chảy cùng kỳ liên hệ cơ học với giá.

### 8.3. Vì sao bài test cắt cụt không bắt được

Bài test §2.5.8 (dựng bảng trên toàn chuỗi rồi dựng lại trên chuỗi cắt tại hàng `k`) là bài
test tốt và nó **đã pass đúng**. Nhưng nó chỉ phát hiện việc **dùng hàng tương lai**. Ở đây
không có hàng tương lai nào bị dùng — hàng `T` có mặt trong cả hai lần dựng. Sai lầm nằm ở
**ngữ nghĩa của nhãn thời gian trên chính hàng đó**, và không một phép cắt cụt nào nhìn thấy
được điều đó.

**Bài học:** chống rò rỉ cần hai lớp. Lớp một hỏi *"có dùng hàng nào sau `close_ts` không"* —
phép cắt cụt trả lời. Lớp hai hỏi *"hàng tại `close_ts` thật sự mô tả khoảng thời gian nào"* —
chỉ có phép đo hướng như §8.2 trả lời được. Từ nay mọi nguồn dữ liệu ngoài phải qua cả hai.

### 8.4. Rò rỉ chỉ ở đúng một cột

Ba cột tỷ lệ còn lại là biến **mức** (trạng thái tại một thời điểm), tương quan nhỏ và không
có chữ ký bất đối xứng. Chúng dùng được. `sum_open_interest` cũng là biến mức.

Nhưng chính cột bị hỏng là cột tạo ra toàn bộ kết quả dương. Bỏ nó ra, giá trị `|ρ|` lớn nhất
còn lại là `0,0615` (`oi_chg_24h × fwd_ret_24h`), **dưới ngưỡng `0,0753`**.

### 8.5. Kết luận đúng của đợt 41

**Không có bằng chứng cho thấy dữ liệu phi giá chứa thông tin dự báo**, ở chín đặc trưng và ba
chân trời đã thử, trên tập IS 2024–2025.

Phần còn lại của đợt vẫn có giá trị thật và được giữ: 23.376 nến order flow đã nạp đủ và đối
soát sạch, bảng đặc trưng và bộ kiểm toán chạy đúng, và phép kiểm đa phép kiểm theo họ là công
cụ dùng lại được. Đợt 42 sửa luật căn dòng rồi chạy lại — và 2026 vẫn còn niêm phong.