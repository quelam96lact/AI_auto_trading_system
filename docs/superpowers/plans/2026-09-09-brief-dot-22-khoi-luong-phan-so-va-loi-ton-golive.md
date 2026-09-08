# Brief đợt 22 — Đòn bẩy 30x: mô phỏng thanh lý + khối lượng phân số, và lỗi tồn go-live

Ngày giao: 09/09/2026
Base: `295666f` (main), cây làm việc sạch, 609 test xanh, ruff sạch.
Người giao: Claude (planner/auditor).

**Quyết định chủ dự án:** giao dịch crypto **hợp đồng có đòn bẩy 30x**, khung **1H**, vốn
thật **dưới 500 USDT**, tự động có cầu dao. (Cập nhật 09/09 — thay cho mức "trên 3x" chốt
ngày 08/09 ở brief 21 Phần C.)

---

## 1. Hai chốt chặn phải mở, theo đúng thứ tự

Trước khi viết brief này tôi kiểm hai câu hỏi. Cả hai đều cho kết quả chặn đường.

### 1.1. Chốt thứ nhất — ở vốn thật, hệ thống sinh 0 lệnh

```
=== 1H, von 500 USDT (von that du kien) ===
daily_breakout     |  +0.00 |  +0.00 | 0 lenh
octopus_combo      |  +0.00 |  +0.00 | 0 lenh
octopus_pullback   |  +0.00 |  +0.00 | 0 lenh
sma_cross          |  +0.00 |  +0.00 | 0 lenh
```

Cả bốn chiến lược, cả hai mã, **0 lệnh** — ngay cả mua-và-giữ cũng 0,00, tức không mua nổi
một đơn vị nào. Nguyên nhân ở `trading/risk.py:103-105`:

```python
qty_atr = int(
    (self.capital * self.risk_pct / (atr * self.atr_multiplier))
    // self.lot_size
)
```

`risk_pct = 0.01`, `lot_size: int = 100`. Vốn 500 USDT ⇒ ngân sách rủi ro **5 USDT**, mà
`qty` là **số nguyên** nên `floor(5 / (ATR × mult)) = 0`. Thêm trần
`max_order_value_pct = 0.20` (dòng 12) ⇒ giá trị lệnh tối đa 100 USDT, nhỏ hơn giá một đơn
vị BTC (62.766 → 125.977 trong kỳ) rất nhiều.

Cùng lỗi này đã bóp méo báo cáo đợt 21: "BTC 0 lệnh khung 1H" **không phải vì thiếu tín
hiệu**. Nâng vốn lên 10.000.000 USDT cho BTC sizing được, cùng dữ liệu, cùng khung 1H:

| Chiến lược | Lệnh | PnL chiến lược | PnL mua-và-giữ |
|---|---:|---:|---:|
| daily_breakout | 35 | −308.189,03 | +2.448.331,49 |
| octopus_combo | 51 | −302.884,87 | +2.448.331,49 |
| octopus_pullback | 17 | −150.538,00 | +2.448.331,49 |
| sma_cross | 50 | −324.124,75 | +2.448.331,49 |

BTC **có** tín hiệu, và cả bốn chiến lược đều lỗ trên BTC. Đây là lỗi của brief 21 do tôi
viết — tôi ghim `--capital 100000` mà không kiểm mức vốn đó có sizing được BTC không.

### 1.2. Chốt thứ hai — backtest KHÔNG mô phỏng thanh lý, nên mọi số ở 30x đều là hư cấu

```
git grep -i -E "liquidat|margin|leverage" -- trading/backtest.py trading/paper_broker.py trading/risk.py
=> rỗng
```

Và `trading/derivative_position.py:38-40` tự ghi:

> "KHÔNG mô phỏng ký quỹ (margin) — cash chỉ trừ phí + cộng/trừ PnL đã thực hiện, không khoá
> vốn theo margin thật (chưa có số margin thật/hợp đồng để mô phỏng)."

Ở **30x**, biên chịu đựng trước khi mất sạch ký quỹ là khoảng **1/30 ≈ 3,33%** (thực tế còn
hẹp hơn vì có ký quỹ duy trì). Một backtest không biết đến thanh lý sẽ báo "lỗ 3%" ở đúng
tình huống mà thực tế là **mất 100% ký quỹ**.

Đây không phải sai số. Đây là **sai về bản chất**: mọi con số PnL sinh ra cho 30x bằng công
cụ hiện tại đều vô nghĩa, kể cả khi Task về khối lượng phân số đã xong.

### 1.3. Thanh lý ở 30x xảy ra thường xuyên đến mức nào — số đo từ chính DB

Tôi tính trên `bars_crypto` khung 1H, ngưỡng 3,33%:

**Tần suất một điểm vào lệnh bị thanh lý trong vòng 24 giờ:**

| Mã | LONG bị thanh lý | SHORT bị thanh lý |
|---|---:|---:|
| BTC-USDT | **14,82%** | 14,22% |
| ETH-USDT | **27,98%** | 25,59% |

**Biên độ từng nến 1H:**

| Mã | % nến có biên độ ≥ 3,33% | % nến giảm ≥ 3,33% | Nến giảm mạnh nhất |
|---|---:|---:|---:|
| BTC-USDT | 0,44% | 0,17% | **−11,09%** |
| ETH-USDT | 1,55% | 0,67% | **−16,23%** |

Đọc bảng này:

- Khoảng **1 trong 7** lệnh BTC và **hơn 1 trong 4** lệnh ETH sẽ chạm thanh lý trong đúng
  một ngày, thuần do giá — chưa tính phí, chưa tính funding.
- Nến 1H tệ nhất của ETH là **−16,23%**, gấp gần **5 lần** biên thanh lý 30x. Một cây nến
  duy nhất đủ để xoá sạch tài khoản, không kịp cắt lỗ.

### 1.4. Nói thẳng một lần, rồi xây

Ghép ba dữ kiện: chiến lược **đã đo là âm** trên cả BTC và ETH; đòn bẩy 30x làm **1/7 đến
1/4 số lệnh bị thanh lý trong 24 giờ**; và công cụ đo **chưa từng mô phỏng thanh lý**.

Với 500 USDT ở 30x, kết cục nhiều khả năng nhất là mất hết, và mất nhanh — tính bằng tuần
chứ không phải tháng.

Điều này không có nghĩa là không làm. Nó có nghĩa là **mục tiêu của giai đoạn này là kiểm
chứng đường lệnh và các chốt an toàn, không phải kiếm lời** — đúng như brief 21 Phần C đã
ghi. Nhận đúng mục tiêu thì thiết kế mới đúng, và thiết kế đúng ở đây bắt đầu bằng: **không
sinh ra một con số 30x nào trước khi mô phỏng được thanh lý.**

### 1.5. Vì vậy đợt này vẫn KHÔNG xây đường lệnh BingX

Brief 21 Phần C xếp bước 3 là "ký request + đường chỉ đọc". **Bước đó tiếp tục lùi.** Thứ tự
bắt buộc:

```
Task 1  khoi luong phan so      -> he thong sinh duoc lenh
Task 2  mo phong thanh ly 30x   -> con so 30x moi co nghia
Task 3  buoc khoi luong that    -> khong do bang so nghe lai
Task 4  do lai o von that + 30x -> du lieu cho cong quyet dinh
   |
   +--> chu du an quyet (cong buoc 2 Phan C) --> moi den duong lenh BingX
```

---

## 2. Ràng buộc

- `real_trading_enabled` giữ `false`. Không đổi.
- **Không gọi SSI. Không gọi BingX** (kể cả endpoint công khai). `bars_crypto` đã đủ tới 08/09.
- **Không tạo, không dùng API key BingX.** Không thêm biến vào `.env`, không mở `.env`.
- **Không viết đường đặt lệnh, không viết broker crypto.**
- `config/config.yaml` **không sửa**. Không in secret.
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB. Task 7 chỉ `SELECT`.
- **Không sửa** `PaperBroker`, `pattern_backtest`, `derivative_backtest`,
  `trading/strategies/*`.
- `trading/risk.py` **được sửa** theo Task 1, `trading/backtest.py` **được sửa** theo Task 2 —
  cả hai phải giữ nguyên hành vi chứng khoán VN, xem tiêu chí bất biến trong từng task.
- Chỉ sửa file được nêu tên. Phát hiện ngoài phạm vi: báo cáo, không tự sửa.
- **Không xoá file nào, không commit, không push.**
- **Không kết luận thay chủ dự án.**

**GitNexus:** `npx gitnexus analyze` trước và sau. **`gitnexus_impact` bắt buộc** cho
`RiskManager`, `size_buy` và `run_backtest` — đều nằm trên đường lệnh thật của chứng khoán
VN. Báo blast radius trước khi sửa; nếu HIGH/CRITICAL thì dừng chờ tôi duyệt.

---

# PHẦN A — MỞ HAI CHỐT CHẶN

## Task 1 — Khối lượng phân số cho `RiskManager`

### 1.1. Việc

`lot_size: int = 100` và `qty` là số nguyên. Chứng khoán VN đúng là lô 100 và số nguyên —
**không được đổi**. Crypto giao dịch theo bước phân số.

Cho `RiskManager` chấp nhận `lot_size` số thực và trả `qty` số thực khi `lot_size` là số
thực. Cách làm do agent chọn, phải thoả cả bốn tiêu chí ở 1.2 và giữ style code hiện có.

**Cạm bẫy số thực:** `0.1 + 0.2 != 0.3`. Làm tròn xuống theo bội `0.0001` bằng phép chia
trực tiếp sẽ sinh `0.00019999999`. Phải xử lý, và phải có test riêng (tiêu chí 4).

### 1.2. Bốn tiêu chí — cả bốn phải xanh

1. **Bất biến chứng khoán VN (quan trọng nhất).** Mọi test hiện có xanh **không sửa một dòng
   test nào**. Nếu thấy "cần sửa test cho hợp" ⇒ **dừng, báo cáo** — dấu hiệu hành vi VN đã đổi.
2. **Tái hiện lỗi trước khi sửa.** Viết test **thất bại trên code hiện tại**:
   `RiskManager(capital=500, lot_size=0.0001)` với ATR/giá BTC phải sinh `qty > 0`. Chạy trên
   code cũ, chụp `AssertionError`, dán vào báo cáo. Rồi mới sửa cho xanh.
3. **Trần 20% vẫn hiệu lực với số thực.** `capital=500`, giá 125.977 ⇒ giá trị lệnh ≤ 100 USDT.
4. **Bước khối lượng chính xác.** Với `lot_size=0.0001`, mọi `qty` phải là bội đúng của
   `0.0001` kiểm bằng `round(qty/0.0001)*0.0001` dung sai `1e-9`.

### 1.3. Kiểm chứng

- `uv run pytest -q` → 609 + test mới, 0 failed. `ruff` sạch.
- `git diff trading/risk.py` nguyên văn + `gitnexus_impact`.
- `git diff` **rỗng** cho `trading/paper_broker.py`, `trading/real_orders.py`,
  `trading/engine/main.py`, `config/config.yaml`.

---

## Task 2 — Mô phỏng đòn bẩy và thanh lý

**Đây là task quan trọng nhất của đợt.** Không có nó, Task 4 không được phép chạy.

### 2.1. Việc

Thêm khả năng mô phỏng vị thế có đòn bẩy vào đường đo crypto. Ba đại lượng tối thiểu:

| Đại lượng | Ý nghĩa |
|---|---|
| Ký quỹ ban đầu | `giá trị danh nghĩa / đòn bẩy` |
| Giá thanh lý | Giá mà tại đó lỗ chưa thực hiện ăn hết ký quỹ trừ ký quỹ duy trì |
| Sự kiện thanh lý | Khi `low` (LONG) hoặc `high` (SHORT) của **nến** chạm giá thanh lý |

**Quy ước bắt buộc — kiểm bằng `low`/`high`, không phải `close`.** Kiểm bằng `close` sẽ bỏ
sót phần lớn thanh lý: dữ liệu cho thấy nến 1H tệ nhất của ETH là −16,23%, và giá có thể
chạm thanh lý rồi hồi trong cùng một nến. Bỏ sót kiểu đó làm kết quả **lạc quan giả**.

Khi thanh lý xảy ra: vị thế đóng tại giá thanh lý, **mất toàn bộ ký quỹ của vị thế đó**, và
sự kiện được **đếm riêng** để báo cáo.

### 2.2. Ký quỹ duy trì — không được bịa

Ký quỹ duy trì của BingX theo bậc giá trị vị thế, và repo **không có số này**. Agent:

1. Tra tài liệu công khai BingX, ghi rõ URL và ngày truy cập.
2. Nếu không tìm được nguồn chắc chắn: dùng **0,5%** làm giả định, và ghi nhãn
   **"giả định, chưa xác minh"** ở mọi bảng có dùng nó.

**Cấm** ghi một con số mà không kèm nguồn hoặc không kèm nhãn giả định.

### 2.3. Bất biến — đường chứng khoán VN không được đổi

Đòn bẩy mặc định phải là **1x**, và ở 1x kết quả phải **giống hệt** hiện nay. Kiểm chứng:
chạy lại phép đo VN và so với cổng cứng đã ghim từ đợt 4:

```
TỔNG: strat -1,615,319,902 | BH 1,897,587,481,903 | lệnh 1,514 | mã sinh lệnh 439
```

Lệch bất kỳ chữ số nào ⇒ **dừng, báo cáo**.

### 2.4. Ba test bắt buộc

1. **Thanh lý xảy ra đúng lúc.** LONG 30x, giá vào 100, ký quỹ duy trì 0,5% ⇒ giá thanh lý
   ≈ 96,8. Nến có `low = 96` phải kích thanh lý; nến có `low = 97` thì không.
2. **`low` bắt được thứ `close` bỏ sót.** Nến `open=100, low=96, close=101` **phải** kích
   thanh lý cho LONG 30x. Test này tồn tại riêng để chống việc kiểm bằng `close`.
3. **1x không thanh lý.** Cùng chuỗi giá, đòn bẩy 1x ⇒ 0 sự kiện thanh lý, PnL khớp kết quả
   không đòn bẩy.

### 2.5. Kiểm chứng

`git diff` nguyên văn, `gitnexus_impact` cho `run_backtest`, cổng cứng VN khớp tuyệt đối,
ba test xanh, pytest + ruff.

---

## Task 3 — Tra thông số THẬT của BingX

Con số "BTC 0,0001 / ETH 0,001" được nhắc lại nhiều lần từ báo cáo đợt 13 nhưng **chưa ai
xác minh**. Đo bằng số nghe lại là lặp đúng lỗi vừa làm hỏng đợt 21.

Tra tài liệu công khai BingX (**không gọi API** — mục 2 cấm), ghi **URL + ngày truy cập**
cho bốn thông số:

1. Bước khối lượng tối thiểu của `BTC-USDT` và `ETH-USDT` perpetual.
2. Giá trị lệnh tối thiểu.
3. **Đòn bẩy tối đa cho phép** — xác nhận 30x có nằm trong giới hạn không.
4. Ký quỹ duy trì (dùng chung với Task 2.2).

Không tìm được ⇒ ghi **"chưa xác minh được"** và dùng giả định có nhãn.

---

## Task 4 — Đo lại: khung 1H, vốn thật, đòn bẩy 30x

**Chỉ chạy sau khi Task 1 và Task 2 đều xanh.**

### 4.1. Sáu lần chạy

Hai mã (bước khối lượng khác nhau nên chạy riêng) × ba mức chi phí, tất cả ở **30x**:

```powershell
# BTC-USDT
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols BTC-USDT --capital 500 --lot-size 0.0001 --leverage 30 --cost-multiplier 1.0
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols BTC-USDT --capital 500 --lot-size 0.0001 --leverage 30 --cost-multiplier 1.5
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols BTC-USDT --capital 500 --lot-size 0.0001 --leverage 30 --cost-multiplier 2.0

# ETH-USDT
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols ETH-USDT --capital 500 --lot-size 0.001 --leverage 30 --cost-multiplier 1.0
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols ETH-USDT --capital 500 --lot-size 0.001 --leverage 30 --cost-multiplier 1.5
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols ETH-USDT --capital 500 --lot-size 0.001 --leverage 30 --cost-multiplier 2.0
```

`--lot-size` phải nhận số thực (`type=float`, hiện là `type=int` ở dòng 313) và `--leverage`
là tham số mới. Cập nhật **mục 2 và mục 3 của docstring** cho khớp. Giữ mặc định
`--lot-size 1` và `--leverage 1` để mọi lệnh của đợt 21 tái lập y nguyên.

### 4.2. Hai điều PHẢI kiểm trước khi tin bất kỳ con số nào

**(a) Số lệnh > 0.** Vẫn 0 lệnh ⇒ Task 1 chưa giải quyết được vấn đề ⇒ **dừng, báo cáo 0
lệnh, không trình bày PnL như một kết quả.**

**(b) Số lần thanh lý được báo riêng.** Mỗi bảng phải có cột **số lần thanh lý** và **số lệnh
kết thúc bằng thanh lý / tổng số lệnh**. Một bảng PnL 30x không có cột này là bảng chưa dùng
được.

### 4.3. Đối chiếu với dự đoán từ dữ liệu

Tôi đã tính trước từ `bars_crypto`: ở ngưỡng 3,33%, **14,82% điểm vào lệnh BTC** và **27,98%
điểm vào lệnh ETH** chạm thanh lý trong 24 giờ (chiều LONG).

Nếu tỷ lệ thanh lý thực đo ở Task 4 **thấp hơn nhiều** hai con số đó, nhiều khả năng mô phỏng
thanh lý đang bỏ sót — quay lại kiểm Task 2.4 test 2. Ghi rõ đối chiếu này trong báo cáo.

### 4.4. Kiểm chứng

Chép **nguyên văn** cả 6 output. Giữ mọi dòng `CẢNH BÁO` cỡ mẫu. Ghi rõ mỗi bảng dùng
`--lot-size`/ký quỹ duy trì bao nhiêu và **đã xác minh hay giả định**.

---

## Task 5 — Báo cáo crypto

Tạo `docs/superpowers/research/2026-09-09-dot-22-do-1h-30x-von-that.md`, **đúng 4 mục**:

1. Output nguyên văn 6 lần chạy.
2. Bảng tổng hợp (mã × mức phí × chiến lược): số lệnh, **số lần thanh lý**, **tỷ lệ thanh
   lý**, PnL chiến lược, PnL mua-và-giữ.
3. Bảng đối chiếu cho thấy vốn và đòn bẩy bóp méo phép đo thế nào:

   | Vốn | lot_size | Đòn bẩy | BTC: lệnh | ETH: lệnh | Thanh lý | Nguồn |
   |---|---|---|---|---|---|---|
   | 100.000 | 1 (nguyên) | 1x | 0 | 22-37 | không mô phỏng | đợt 21 |
   | 10.000.000 | 1 (nguyên) | 1x | 17-51 | — | không mô phỏng | Claude đo 09/09 |
   | 500 | phân số | **30x** | (điền) | (điền) | (điền) | đợt này |

4. Hạn chế đã biết — bắt buộc đủ sáu điều:
   - **Funding chưa mô hình hoá.** Ở 30x, funding tính trên giá trị danh nghĩa (~15.000 USDT
     với vốn 500), nên nó ăn vào **ký quỹ** nhanh gấp 30 lần so với cảm nhận trực giác.
   - Bước khối lượng **đã xác minh hay giả định** (Task 3).
   - Ký quỹ duy trì **đã xác minh hay giả định** (Task 2.2).
   - Chỉ 2 mã, cỡ mẫu nhỏ.
   - Khung 1H chỉ có dữ liệu từ 2024-04-27.
   - **Thanh lý mô phỏng theo nến, không theo tick.** Trong một nến 1H, giá có thể chạm mức
     thanh lý theo đường đi mà dữ liệu OHLC không ghi lại. Mô phỏng theo nến vẫn **lạc quan
     hơn thực tế**.

**Không viết kết luận, không khuyến nghị.**

---

# PHẦN B — LỖI TỒN CHUẨN BỊ GO-LIVE

Ba task độc lập, không cái nào chạm đường chạy thật.

## Task 6 — Làm rõ `2026-01-02`: ngày nghỉ hay lỗ hổng dữ liệu

Đợt 21 báo 12 ngày làm việc không có bar; tôi chạy lại ra **13** — agent bỏ sót
`2026-01-02` (thứ Sáu), dòng duy nhất không trùng ngày lễ phổ biến nào.

**Bẫy múi giờ, ghi lại để không lặp:** `ts::date` phụ thuộc `TimeZone` phiên. Với `UTC` câu
SQL ra **46 dòng** (mọi thứ Sáu rỗng — giả tạo do dời múi giờ); với `Asia/Ho_Chi_Minh` ra
**13 dòng**. Mọi truy vấn ngày tháng trên `bars_daily` **phải** ghim múi giờ.

Xác định bằng **ba nguồn trong hệ thống**, không đoán:

```sql
SET TimeZone='Asia/Ho_Chi_Minh';
SELECT count(*), count(DISTINCT symbol) FROM bars WHERE ts::date = '2026-01-02';
SELECT * FROM index_values WHERE ts::date = '2026-01-02';
SELECT * FROM backfill_progress WHERE updated_at::date BETWEEN '2026-01-01' AND '2026-01-05';
```

Đối chiếu ngày liền kề (`2025-12-31`, `2026-01-05`) làm mốc.

**Kết luận cho phép:** chỉ hai khả năng kèm bằng chứng — "không có dữ liệu ở cả ba nguồn ⇒
nhiều khả năng là ngày nghỉ" hoặc "có dữ liệu ở nguồn X ⇒ lỗ hổng của `bars_daily`".
**Không tự thêm vào `config.yaml`** dù kết luận là gì. `git diff config/config.yaml` phải rỗng.

## Task 7 — Kiểm engine có còn câm không

`CLAUDE.md` ghi gói K (06/09) sửa phần lớn lỗi "engine câm" nhưng **HII vẫn câm vì lý do
khác**. Phần A đợt này vừa chứng minh cùng một lớp lỗi trên crypto: **ngưỡng sizing hiệu
chỉnh cho một quy mô vốn, áp lên quy mô khác, làm hệ thống câm mà không báo lỗi.** Đáng kiểm
đường VN có dính biến thể nào không.

```powershell
uv run python scripts/check_silent_engine.py --config config/config.yaml
```

Chỉ **chạy và báo cáo** — output nguyên văn + exit code. Không sửa gì dựa trên kết quả.

## Task 8 — `/app` thuộc root trong image Docker

Đợt 20 phát hiện `/app` thuộc `root` còn `.venv`/`trading`/`config` thuộc `appuser`. Không
gây hại hiện tại nhưng lệch ý định của `Dockerfile`. Sửa một dòng, đặt **sau** `useradd` và
**trước** các `COPY`.

**Build ra tag riêng, KHÔNG đụng stack đang chạy:**

```powershell
docker build -t dot22-test:new .
docker run --rm --entrypoint sh dot22-test:new -c "id; stat -c '%U %n' /app /app/.venv /app/trading /app/config"
docker run --rm --entrypoint python dot22-test:new -c "import trading.collector.main, trading.engine.main; print('OK')"
docker images dot22-test:new --format "{{.Size}}"
```

Cả **bốn** đường dẫn thuộc `appuser`; import hai entrypoint OK; kích thước không tăng quá
2 MB so với 227 MB; `docker ps` vẫn 6 container `Up`. **Không** `docker compose build`,
**không** `docker compose up`.

---

## 3. Tiêu chí dừng

| Tình huống | Dừng ở đâu |
|---|---|
| Task 1: phải sửa test cũ mới xanh | Ngay — dấu hiệu đổi hành vi VN |
| Task 1/2: `gitnexus_impact` báo HIGH/CRITICAL | Báo blast radius, chờ tôi duyệt |
| Task 2: cổng cứng VN (`-1.615.319.902` / `1.514` lệnh) lệch | Ngay |
| Task 2: không nghĩ ra cách mô phỏng thanh lý mà không sửa `PaperBroker` | Ngay — báo cáo, đừng sửa file bị cấm |
| Task 3: không tìm được nguồn | Không dừng — ghi "chưa xác minh", đi tiếp |
| Task 4 chạy khi Task 2 chưa xanh | **Không được phép** — Task 4 phụ thuộc Task 2 |
| Task 4: vẫn 0 lệnh | Dừng, báo cáo 0 lệnh, **không trình bày PnL** |
| Task 4: tỷ lệ thanh lý thấp hơn nhiều 14,82%/27,98% | Kiểm lại Task 2.4 test 2 trước khi báo |
| Task 6: cần sửa `config.yaml` | Ngay — task chỉ đọc |
| Task 8: image tăng > 2 MB | Báo cáo, không tự tối ưu thêm |
| Bất kỳ lúc nào cần gọi BingX hoặc SSI | Ngay |

---

## 4. Báo cáo nghiệm thu — đúng 11 mục

1. `npx gitnexus analyze` trước.
2. Task 1: `gitnexus_impact` + ảnh chụp `AssertionError` trên code cũ + `git diff` + 4 tiêu chí.
3. Task 2: `git diff` + `gitnexus_impact` + **cổng cứng VN khớp tuyệt đối** + 3 test.
4. Task 3: 4 thông số + **nguồn và ngày truy cập**, hoặc "chưa xác minh được".
5. Task 4: output nguyên văn 6 lần chạy, có cột thanh lý.
6. Task 4.3: đối chiếu tỷ lệ thanh lý thực đo với 14,82% / 27,98%.
7. Task 5: đường dẫn + nội dung file báo cáo.
8. Task 6: 4 truy vấn + kết luận kèm bằng chứng + `git diff config.yaml` rỗng.
9. Task 7: output + exit code.
10. Task 8: 4 output Docker + `docker ps`.
11. `git status`, `git diff --stat HEAD`, `gitnexus_detect_changes()`, pytest, ruff.

Kỳ vọng mục 11: chỉ `trading/risk.py`, `trading/backtest.py`,
`scripts/measure_crypto_strategies.py`, `Dockerfile`, file test mới, file báo cáo mới, cộng
`AGENTS.md`/`CLAUDE.md`. **Không** `config/config.yaml`, **không** `trading/paper_broker.py`,
**không** `trading/real_orders.py`.

---

## 5. Việc KHÔNG thuộc đợt này

- **Không** viết đường đặt lệnh BingX, không tạo API key, không gọi BingX.
- **Không** triển khai image mới (Task 8 chỉ build tag thử nghiệm).
- **Không** điền `holidays` (Task 6 chỉ điều tra).
- **Không** sửa engine dù Task 7 phát hiện câm.
- **Không** mô hình hoá funding — vẫn là hạn chế, chỉ nêu.
- **Không** quyết định có giao dịch BTC/ETH hay không.

## 6. Sau đợt này

Nếu Task 4 cho số lệnh > 0 **và** có cột thanh lý, chủ dự án lần đầu có phép đo ở **đúng vốn
thật, đúng khung 1H, đúng bước khối lượng, đúng đòn bẩy 30x, có mô phỏng thanh lý**. Đó mới
là dữ liệu để mở cổng bước 2 Phần C brief 21 — cổng mà đợt 21 chưa đủ dữ liệu để mở.

Ba kết cục có thể, và cả ba đều là kết quả dùng được:

- **Tỷ lệ thanh lý cao, PnL âm nặng** — khớp dự đoán từ dữ liệu. Khi đó câu hỏi cho chủ dự án
  là hạ đòn bẩy, đổi chiến lược, hay dừng.
- **Tỷ lệ thanh lý thấp bất ngờ** — phải nghi mô phỏng bỏ sót trước khi mừng (Task 4.3).
- **Vẫn 0 lệnh** — 500 USDT quá nhỏ cho họ chiến lược này ở khung 1H ngay cả với 30x; lựa
  chọn còn lại là tăng vốn hoặc đổi cách sizing, đều là quyết định của chủ dự án.
