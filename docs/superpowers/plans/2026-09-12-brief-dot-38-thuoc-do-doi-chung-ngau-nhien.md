# Brief đợt 38 — Thước đo: đối chứng vào lệnh ngẫu nhiên

Ngày giao: 12/09/2026.
Base: `deec346` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

**Brief này có đúng một ý.** Nó không tạo ra chiến lược nào. Nó tạo ra cái thước để đo mọi
chiến lược sau này — kể cả đợt 39 (cắt ngang 20 mã) đã được chủ dự án chốt.

---

## 0. Vì sao việc này phải làm trước

### 0.1. Sáu lần đo, sáu lần đọc một con số PnL rồi kết luận

Repo này đã đo bốn chiến lược crypto (đợt 22/26) và hai module perpetual (đợt 37). Cả sáu đều
âm. Nhưng **chưa lần nào ta biết con số đó có khác không một cách có ý nghĩa hay không.**

Một chiến lược 26 lệnh cho `+2,33 USDT` trên vốn 500 với rủi ro 2,5 USDT/lệnh — con số đó
nhỏ hơn một đơn vị rủi ro. Nó có thể là lợi thế mỏng, có thể là nhiễu thuần tuý. Đọc bảng
không phân biệt được. Đó chính xác là tình huống đợt 37 để lại.

### 0.2. Phép mổ xẻ đợt 37 mà tôi chạy sau khi nghiệm thu

```
=== donchian_breakout | IS | 85 lệnh ===
  gross   -26.14   phí   16.75   net   -42.89
  TP   20 lệnh (23.5%)   SL  53 lệnh (62.4%)   TIME 12 lệnh (14.1%)
  R trung bình -0.221 | thắng 31.8% | R thắng tb +1.53 | R thua tb -1.04
```

Ba điều rút ra:

1. **`gross` đã âm trước khi trả đồng phí nào.** Không phải bài toán chi phí.
2. Thiết kế `2R` lãi trên `1R` lỗ, nhưng thực nhận `+1,53R` trên `−1,04R` → tỷ lệ thắng hoà
   vốn nhảy từ **33,3% lên 40,5%**, trong khi thắng thật chỉ **31,8%**.
3. Với bước ngẫu nhiên không xu hướng, chặn `+2R`/`−1R`, xác suất chạm TP trước là đúng `1/3`
   (gambler's ruin). Bỏ các lệnh time-stop ra:

   | | TP trước SL | Mốc ngẫu nhiên |
   |---|---|---|
   | Donchian IS | 20/73 = **27,4%** | 33,3% |
   | Donchian OOS | 7/20 = **35,0%** | 33,3% |
   | Bollinger IS | 5/13 = **38,5%** | 44,4% |

Đây là **phép tính tay trên số tổng**, và nó chỉ gợi ý. Brief này biến nó thành phép kiểm
đúng nghĩa, chạy được cho mọi module về sau.

### 0.3. Ý tưởng, nói một câu

Giữ nguyên **mọi thứ** — cùng chuỗi giá, cùng cách dựng trigger, cùng stop, cùng mục tiêu,
cùng sizing, cùng phí, cùng luật thoát. **Chỉ thay quyết định "có vào lệnh không, và vào chiều
nào" bằng bốc thăm.** Chạy 1000 lần với 1000 hạt giống khác nhau → một phân phối null. Rồi hỏi:
kết quả thật nằm ở phân vị nào của phân phối đó?

Vì đối chứng chạy trên **chính chuỗi giá đó**, phân phối null đã tự động chứa xu hướng và biến
động của giai đoạn đó. Cái còn lại chính là phần đóng góp của tín hiệu — không lẫn gì khác.

### 0.4. Hai đối chứng, không phải một

Đợt 37 phơi ra một giả tạo: Donchian lãi ở OOS vì **18 lệnh short trên 8 lệnh long** trong một
năm BTC giảm. Một đối chứng 50/50 sẽ để giả tạo đó lọt lưới — nó sẽ khen chiến lược vì đã
đánh cược đúng hướng, chứ không phải vì định thời điểm giỏi.

Nên cần **hai** đối chứng, trả lời hai câu khác nhau:

| Đối chứng | Chiều được bốc thăm thế nào | Trả lời câu |
|---|---|---|
| **A — 50/50** | long/short xác suất bằng nhau | *Toàn bộ chiến lược có thắng được tung đồng xu không?* |
| **B — khớp chiều** | giữ đúng tỷ lệ long/short của lượt chạy thật | *Cho sẵn thiên lệch chiều đó, việc định thời điểm có thêm được gì không?* |

Một chiến lược thắng A nhưng thua B nghĩa là: nó chỉ đang cược hướng, và bạn có thể cược hướng
đó rẻ hơn nhiều bằng cách mua-và-giữ.

---

## 1. Phạm vi

### 1.1. File được sửa — chỉ bốn file

| File | Trạng thái | Được làm gì |
|---|---|---|
| `trading/perp_backtest.py` | có sẵn | thêm chế độ vào lệnh ngẫu nhiên + một bộ đếm còn thiếu |
| `scripts/significance_test.py` | **mới** | dựng phân phối null, in phân vị |
| `tests/test_significance.py` | **mới** | test, gồm **đối chứng dương** |
| `docs/superpowers/research/2026-09-12-dot-38-doi-chung-ngau-nhien.md` | **mới** | kết quả |

### 1.2. Không được đụng

`trading/indicators.py` (đợt 37 vừa thêm, đã khoá), `scripts/measure_perp_modules.py`,
`tests/test_perp_backtest.py`, `tests/test_indicators_perp.py`, `trading/pattern_backtest.py`,
`trading/backtest.py`, `trading/derivative_backtest.py`, `trading/paper_broker.py`,
`trading/risk.py`, `trading/strategies/*`, `trading/collector/*`, `trading/crypto_fees.py`,
`config/config.yaml`, `.env`, `docker-compose.yml`.

**17 test của `tests/test_perp_backtest.py` phải pass nguyên vẹn, không sửa một `assert` nào.**
Thay đổi ở Task 1 là thuần bổ sung; nếu phải sửa một `assert` để test xanh thì **hành vi đã
đổi** — dừng lại và báo cáo, đừng sửa `assert`.

### 1.3. Ràng buộc vận hành

Giữ nguyên toàn bộ ràng buộc đợt 37: không gọi mạng, chỉ đọc DB, không đụng NATS,
`real_trading_enabled` giữ `false`, không in secret, không xoá file, **không commit, không
push**. Mọi output dán vào báo cáo copy từ terminal. **Không bịa** — thiếu thì ghi
**"CHƯA LÀM"** kèm lý do.

**GitNexus:** `npx gitnexus analyze` trước và sau; `gitnexus_impact` cho `run_perp_backtest`
trước khi sửa. MCP timeout thì ghi rõ.

---

## Task 1 — Thêm chế độ ngẫu nhiên vào `trading/perp_backtest.py`

### 1.1. Hai tham số mới

Thêm vào chữ ký của `run_perp_backtest`, **cả hai đều keyword-only, đều có mặc định giữ
nguyên hành vi hiện tại**:

```python
    random_entry: RandomEntryConfig | None = None,
```

với

```python
@dataclass(frozen=True)
class RandomEntryConfig:
    seed: int
    signal_prob: float      # xác suất phát tín hiệu tại mỗi bar đủ warm-up
    long_prob: float = 0.5  # xác suất chiều LONG khi đã quyết định phát tín hiệu
```

`random_entry=None` → chạy y như bây giờ. Đây là điều bảo đảm 17 test cũ không đổi.

### 1.2. Thay đúng một chỗ

Trong **bước 4 (phát hiện tín hiệu)**, khi `random_entry is not None`:

- **Bỏ toàn bộ điều kiện tín hiệu của module** (Donchian breakout / Bollinger rejection / bộ
  lọc chế độ thị trường). Giữ nguyên điều kiện **warm-up** — tức vẫn đòi `donchian_val`,
  `atr_val`, `bb_val`, `adx_val`, `ema50_val`, `ema200_val`, `atr_history`, `bw_history`,
  `ema50_history` đủ dài đúng như bản thật. Bar nào bản thật không thể phát tín hiệu vì chưa
  đủ dữ liệu thì bản ngẫu nhiên cũng không được phát.
- Tại mỗi bar đủ điều kiện: bốc `rng.random() < signal_prob`. Nếu trúng, bốc tiếp
  `rng.random() < long_prob` để chọn chiều.
- **Dựng `pending_order` bằng đúng code cũ** — cùng công thức trigger, cùng `breakout_low` /
  `high_t` / `middle_t` / `atr_t`. Không viết lại.

**Mọi thứ khác giữ nguyên tuyệt đối:** bước 2 (thoát lệnh), bước 3 (khớp lệnh chờ), sizing,
phí, trượt giá, trần đòn bẩy, `would_liquidate`, `funding_spans`, time-stop. Bao gồm cả **ba
phép loại bỏ của module B** (`R < 0,60 ATR`, `R > 2,00 ATR`, khoảng cách tới đường giữa
`< 0,80R`) — chúng thuộc phần quản trị lệnh, không thuộc phần tín hiệu, nên đối chứng cũng
phải chịu chúng.

### 1.3. RNG phải cô lập

Dùng `random.Random(random_entry.seed)` tạo trong thân hàm. **Không** dùng `random.random()`
toàn cục — nó sẽ làm kết quả phụ thuộc thứ tự chạy và phá tính tất định của mọi test khác.

### 1.4. Vá bộ đếm còn thiếu — lỗi của brief 37, là của tôi

Module B hiện **đánh rơi lệnh im lặng**: ba phép loại bỏ ở §1.2 đặt `pending_order = None` mà
không tăng bộ đếm nào. Bằng chứng từ lượt chạy IS của đợt 37:

```
Signals  Expired  Cancel   Trades
20       0        0        15        <-- 5 tín hiệu biến mất, không cột nào giải thích
```

Module A thì cộng khớp (`129 = 1 + 43 + 85`, `46 = 20 + 26`). Đây là thiếu sót của brief 37:
tôi định nghĩa `orders_cancelled` nhưng không nói ba phép loại bỏ này đếm vào đâu.

Thêm trường `orders_dropped: int = 0` vào `PerpReport` và tăng nó tại **cả hai** nhánh
`drop_order` (LONG và SHORT) của module B. Sau khi vá, phải luôn đúng:

```
signals_generated == orders_expired + orders_cancelled + orders_dropped + len(trades) + (0 hoặc 1 lệnh còn treo cuối kỳ)
```

Việc này thành bắt buộc ở đợt này vì ta sắp làm thống kê: không giải thích được 5/20 tín hiệu
thì không nói được gì về ý nghĩa thống kê.

### 1.5. Kiểm chứng Task 1

1. **17 test cũ pass, không sửa một `assert` nào.** Dán `git diff` của
   `tests/test_perp_backtest.py` — tôi kỳ vọng nó **rỗng**.
2. Test: cùng `seed`, chạy hai lần → `PerpReport` giống hệt (số lệnh, tổng `net_pnl` khớp tới
   từng chữ số).
3. Test: `seed` khác nhau → kết quả khác nhau.
4. Test: `random_entry` với `long_prob=1.0` → **mọi** lệnh có `side == "LONG"`;
   `long_prob=0.0` → mọi lệnh `SHORT`.
5. Test: `signal_prob=0.0` → không lệnh nào, `signals_generated == 0`.
6. Test: chế độ ngẫu nhiên **không** phát tín hiệu ở bar chưa đủ warm-up (đặt `signal_prob=1.0`
   và khẳng định `signals_generated` nhỏ hơn số bar — phần đầu chuỗi phải bị chặn).
7. Test: phương trình đối soát ở §1.4 đúng, cho **cả hai** module, trên một chuỗi thật.
8. Suite đầy đủ pass (mốc hiện tại **687**), ruff sạch, **cổng cứng VN khớp từng chữ số**.

---

## Task 2 — `scripts/significance_test.py`

**Chỉ bắt đầu sau khi Task 1 đạt toàn bộ.**

### 2.1. Việc nó làm

1. Chạy module **thật** một lần trên tập đã chọn → lấy `net_pnl` thật, số lệnh thật, tỷ lệ
   long thật.
2. **Hiệu chỉnh `signal_prob`:** đếm số bar đủ warm-up trong tập (chạy một lượt với
   `signal_prob=1.0` và đọc `signals_generated`), rồi đặt
   `signal_prob = signals_thật / bars_đủ_điều_kiện`.
3. Chạy **đối chứng A** (`long_prob=0.5`) với `seed = 0 .. N-1`.
4. Chạy **đối chứng B** (`long_prob =` tỷ lệ long thật) với `seed = 0 .. N-1`.
5. In, cho mỗi đối chứng: trung vị, p05, p25, p75, p95, p99 của `net_pnl` trong phân phối null;
   **phân vị của kết quả thật**; và số lệnh trung bình của đối chứng.

### 2.2. Tham số

```
--symbol       mặc định BTC-USDT
--module       donchian_breakout | bollinger_mr
--split        is | oos
--iterations   mặc định 1000
--capital / --risk-fraction / --max-leverage / --slippage-bps / --dsn   như đợt 37
```

Dùng lại `read_crypto_bars` và **đúng hai mốc chia của đợt 37** (IS `2024-04-27`→`2025-12-31`,
OOS `2026-01-01`→`2026-09-08`, UTC). Không định nghĩa lại mốc chia — import hoặc chép nguyên,
và nếu chép thì nêu rõ trong báo cáo.

### 2.3. Ba phép kiểm tra tính lành mạnh của chính công cụ

In ra mỗi lần chạy, vì nếu ba số này sai thì mọi phân vị đều vô nghĩa:

1. **Số lệnh đối chứng trung bình so với số lệnh thật.** Phải trong khoảng **±20%**. Ngoài
   khoảng đó → in cảnh báo rõ ràng; hiệu chỉnh `signal_prob` **một lần** rồi chạy lại, và ghi
   cả hai giá trị vào báo cáo. Không dò lặp tới khi vừa ý.
2. **Tỷ lệ long thật** và tỷ lệ long trung bình của đối chứng B.
3. **Thời gian chạy.** Nếu một lượt `--iterations 1000` quá **20 phút**, hạ xuống 500 và ghi
   rõ con số đã dùng. Đừng im lặng đổi.

### 2.4. Diễn giải — chốt TRƯỚC khi xem kết quả

Một module **có bằng chứng lợi thế** khi và chỉ khi kết quả thật nằm **trên phân vị 95** của
**cả hai** phân phối null.

- Trên 95 ở A nhưng không ở B → **chỉ là cược hướng**, không phải kỹ năng định thời điểm. Ghi
  đúng như vậy.
- Dưới 95 ở cả hai → **không có bằng chứng lợi thế**. Đây là kết luận hợp lệ và hữu ích, không
  phải thất bại của đợt.

**Không chỉnh tham số chiến lược sau khi xem phân vị.** Công cụ này tồn tại để chặn đúng việc
đó.

### 2.5. Kiểm chứng Task 2 — `tests/test_significance.py`

1. **Tất định:** cùng tham số, chạy hai lần → phân vị giống hệt.
2. **ĐỐI CHỨNG DƯƠNG — tiêu chí quan trọng nhất của cả brief.**

   Một công cụ luôn trả lời "không có lợi thế" thì vô dụng, và **không phân biệt được với một
   công cụ hỏng**. Phải chứng minh nó phát hiện được lợi thế khi lợi thế có thật.

   Dựng một chuỗi giá **tổng hợp** trong đó Donchian breakout là tín hiệu thật: mỗi lần giá
   phá đỉnh kênh 20 kèm mở rộng ATR, các bar sau **luôn** tiếp diễn mạnh theo hướng đó; thời
   gian còn lại giá đi ngang nhiễu. Trên chuỗi này, chạy `donchian_breakout` thật và một tập
   đối chứng ngẫu nhiên (ít vòng cũng được, ví dụ 50, để test chạy nhanh).

   **Khẳng định: kết quả thật nằm trên phân vị 95 của phân phối null.**

   Nếu test này đỏ thì công cụ hỏng, và mọi kết luận "không có lợi thế" ở Task 3 đều **không
   có giá trị**. Đây là bài test phải viết trước và phải thấy nó ý nghĩa.

3. **Đối chứng âm:** trên chuỗi giá ngẫu nhiên thuần (bước ngẫu nhiên, hạt giống cố định),
   kết quả thật **không** nằm trên phân vị 95. Cặp đôi với bài 2: một cái chứng minh công cụ
   nhạy, cái kia chứng minh nó không nhạy quá mức.

4. Suite đầy đủ pass, ruff sạch.

---

## Task 3 — Chạy và ghi kết quả

**Bước CUỐI CÙNG.** Không sửa code sau khi bắt đầu.

Bốn lượt, mỗi lượt cho cả hai đối chứng A và B:

| # | Lệnh |
|---|---|
| 1 | `--module donchian_breakout --split is` |
| 2 | `--module donchian_breakout --split oos` |
| 3 | `--module bollinger_mr --split is` |
| 4 | `--module bollinger_mr --split oos` |

Ghi vào `docs/superpowers/research/2026-09-12-dot-38-doi-chung-ngau-nhien.md` (**file mới,
không ghi đè file nào**):

1. Nguyên văn output cả bốn lượt, copy từ terminal.
2. Bảng tổng hợp: mỗi hàng một (module × split), các cột `net_pnl thật`, `trung vị null A`,
   `phân vị thật trong A`, `trung vị null B`, `phân vị thật trong B`.
3. Kết luận từng module theo §2.4, một dòng mỗi cái.
4. Mục **"Điều phép kiểm này KHÔNG trả lời"** — tối thiểu: nó chỉ đo đóng góp của **điểm vào
   lệnh**, không đo chất lượng của luật thoát hay của sizing; nó không nói gì về giai đoạn
   ngoài mẫu đã dùng; funding vẫn chưa mô hình hoá.

---

## 4. Báo cáo cho Claude

1. `gitnexus_impact` cho `run_perp_backtest` (hoặc ghi rõ MCP timeout).
2. `git diff --stat` và `git status --short`.
3. **`git diff` của `tests/test_perp_backtest.py`** — tôi kỳ vọng rỗng.
4. Task 1: kết quả 8 tiêu chí. Task 2: kết quả 4 tiêu chí, **nói rõ đối chứng dương đã xanh**.
5. Task 3: bảng tổng hợp và kết luận từng module.
6. Ba dòng: số test pass (mốc **687**), ruff, cổng cứng VN đủ bốn con số.
7. Đường dẫn file nghiên cứu mới.

**Không commit, không push.**

---

## 5. Điều KHÔNG thuộc phạm vi

- **Không xây chiến lược mới.** Đợt 39 (cắt ngang 20 mã) là việc khác, đã được chốt hướng.
- **Không chỉnh tham số** của Donchian hay Bollinger. Nếu phân vị cho thấy không có lợi thế,
  đó là **kết quả**, không phải lời mời đi dò tham số.
- **Không** đụng tới hai module đợt 37 ngoài việc thêm chế độ ngẫu nhiên và bộ đếm thiếu.
- **Không** nạp dữ liệu Binance, không mở module C/D.
- **Không** bootstrap hay permutation test riêng. Phân phối null từ đối chứng ngẫu nhiên đã
  trả lời đúng câu hỏi cần trả lời, và nó chạy trên chính chuỗi giá thật nên đã bao gồm xu
  hướng và biến động của giai đoạn. Thêm phép kiểm thứ hai lúc này là thừa.
