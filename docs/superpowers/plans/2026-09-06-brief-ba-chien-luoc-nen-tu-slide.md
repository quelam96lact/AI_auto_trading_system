# Brief — ba chiến lược nến từ slide "Buổi 9&10" (DOJI / Hammer / Combo)

Viết 06/09 sau khi đọc `Buổi 9&10.pdf` (44 trang, slide khoá học của cole.vn,
giảng viên Đồng Nguyễn — chủ đề "Quy trình hoá chiến lược đầu tư").

**File PDF cố ý KHÔNG commit vào repo**: tài liệu khoá học của bên thứ ba, 2 MB,
và nội dung cần dùng đã được trích ra thành §1 dưới đây. Bản trích này là nguồn
tham chiếu cho agent — không cần mở lại PDF (phần lớn slide là ảnh, `pypdf` chỉ
lấy được chữ ở 30/44 trang).

---

## 1. SLIDE NÓI GÌ — bản trích nguyên văn

### 1.1 Bối cảnh chung

- **Thị trường slide nhắm tới** (tr.6): Forex, Vàng, chỉ số (JP225, HK50,
  DEU40, UK100, US30, US100, US500), tiền điện tử. **Không nhắc cổ phiếu.**
- **Khung thời gian** (tr.9): **D1 hoặc H4**.
- **Nguyên tắc** (tr.41): "Don't TRADE without STOP LOSS", "Don't FOLLOW too
  many INDICATORS", "KEEP IT SIMPLE".

### 1.2 Chiến lược DOJI (tr.10–17)

**Nhận dạng** (tr.12):
- Giá đóng cửa gần với giá mở cửa.
- Doji hoàn hảo là close == open.
- Nếu xuất hiện nhiều nến thân nhỏ, hoặc có nhiều hơn 2 Doji trước đó ⇒ Doji
  **không hiệu quả** (Near Doji).

**Chỉ báo** (tr.13): ATR, thông số nến OHLC, **tham số điều chỉnh `x`**.

**Hành động** (tr.14–16): **VÀO 2 LỆNH — HEDGING**, gồm BUY/STOP và SELL/STOP.

```
SELL/STOP   Entry = LOW  − x
            Stop Loss = HIGH + x
            TP = ENTRY − kTP × ATR(5)      kTP = 0,8 – 1,0
```

Nhánh BUY/STOP nằm ở tr.15 dưới dạng **ảnh, không trích được chữ**. Đối xứng
suy ra là `Entry = HIGH + x`, `SL = LOW − x`, `TP = ENTRY + kTP × ATR(5)` —
**nhưng đây là SUY LUẬN, không phải trích dẫn.** Xem §2.

### 1.3 Chiến lược Hammer / Pin bar (tr.18–23)

**Nhận dạng búa — phải thoả cả 4 điều kiện** (tr.19):
1. Xuất hiện **sau một xu hướng GIẢM GIÁ**.
2. Thân búa ở phần **trên** của cây nến (búa tăng hay giảm không quan trọng).
3. Bóng nến **dưới dài gấp 2 lần thân** nến.
4. Bóng nến **trên rất ngắn**, tốt nhất là không có.

**Chỉ báo** (tr.20): ATR(5), OHLC, `x`.

**Hành động** (tr.21–22): **VÀO 1 LỆNH**.

```
BUY/STOP    Entry = HIGH + x
            Stop Loss = LOW − x
            TP = ENTRY + kTP × ATR(5)      kTP = 1,3 – 1,6
```

### 1.4 Chiến lược Combo (tr.24–31)

**Bản chất** (tr.25): "giao dịch **thuận hoàn toàn** theo xu hướng".

**Chỉ báo** (tr.25): **MA(20)**, **ATR(5)**, **MACD(5,25,5)**, OHLC, `x`.

**Combo BUY** (tr.26–27):
```
Điều kiện:  CLOSE > OPEN
            CLOSE > MA(20)
            MACD(5,25,5) > 0
BUY/STOP    Entry = HIGH + x
            Stop Loss = LOW − x
            kTP = 2 – 2,6
```

**Combo SELL** (tr.28–29):
```
Điều kiện:  CLOSE < OPEN
            CLOSE < MA(20)
            MACD(5,25,5) < 0
SELL/STOP   Entry = LOW − x
            Stop Loss = HIGH + x
            kTP = 2 – 2,6
```

**Take profit** (tr.30–31), ba cách:
1. Theo mục tiêu cá nhân.
2. Theo `kTP`.
3. **Dịch chuyển Stop Loss theo giá trị đường MA(20) tại thời điểm thị trường
   đóng cửa.**

---

## 2. SLIDE KHÔNG NÓI GÌ — phải quyết trước khi code

Đây là phần quan trọng nhất của brief này. Bảy chỗ dưới đây **không suy ra
được** từ slide; agent **không được tự chọn rồi im lặng**.

| # | Chỗ mơ hồ | Vì sao không đoán được |
|---|---|---|
| **1** | **`x` là gì, đơn vị nào** | Slide chỉ gọi là "tham số điều chỉnh". Trên forex nó là pip; trên cổ phiếu VN giá tính bằng **đồng** (VCB ~60.000); trên crypto là USDT (PEPE ~0,00001). **Một hằng số duy nhất là bất khả thi** — xem cảnh báo §3 |
| **2** | **`kTP` chọn số nào** | Slide cho **khoảng**: 0,8–1,0 / 1,3–1,6 / 2–2,6. Ba chiến lược ba khoảng khác nhau |
| **3** | **"Close gần open" gần bao nhiêu** | Doji cần một ngưỡng: `\|close−open\| ≤ ε × (high−low)`? hay `≤ ε × ATR`? ε bằng bao nhiêu? |
| **4** | **"Nhiều nến thân nhỏ" / ">2 Doji trước đó"** | Nhìn lại bao nhiêu nến? "Thân nhỏ" theo ngưỡng nào? |
| **5** | **"Sau một xu hướng GIẢM GIÁ"** | Định nghĩa xu hướng giảm: N nến đỏ liên tiếp? close < MA(20)? MA dốc xuống? Mỗi cách cho tập tín hiệu khác hẳn |
| **6** | **MA(20) là SMA hay EMA** | Repo có `EmaCalculator` (`indicators.py:42`); SMA hiện chỉ nằm rải rác trong `sma_cross.py` chứ không có lớp riêng |
| **7** | **Nhánh BUY/STOP của DOJI** | tr.15 là ảnh, không trích được. Công thức đối xứng ở §1.2 là **suy luận của tôi**, cần xác nhận bằng cách mở slide xem |

---

## 3. CẢNH BÁO ĐƠN VỊ — `x` là cái bẫy thứ sáu

Dự án này đã trả giá **năm lần** cho cùng một hình dạng lỗi: một con số đúng
trong hệ quy chiếu này mang sang hệ quy chiếu khác mà nhìn vẫn hợp lý.

1. Lô 100 (HOSE) áp lên crypto.
2. `min_avg_value_20 = 2e9` **VND** áp lên giá trị **USDT**.
3. `1000PEPE` (perp) so với `PEPE` (spot) — lệch 1.000 lần.
4. Ngưỡng 2 tỷ áp lên bar tổng hợp volume 100.000 trong test gói S.
5. **Ở sản xuất**: cùng ngưỡng 2 tỷ tính trên **N bar** thay vì **N ngày**.

`x` là một **độ lệch giá tuyệt đối**. Nếu ai đó viết `x = 0.5`:
- trên VCB (60.000đ) nó nhỏ hơn cả bước giá — vô nghĩa;
- trên PEPE-USDT (~0,00001) nó là **50.000%** giá trị.

**Ràng buộc cứng: `x` KHÔNG được là hằng số tuyệt đối.** Phải biểu diễn theo
một đại lượng cùng đơn vị với giá — đề xuất `x = hệ_số × ATR(5)` (khuyến nghị,
vì ATR đã có sẵn và tự co giãn theo thị trường), hoặc theo bước giá của sàn.
Agent chọn cách nào phải **ghi rõ trong báo cáo**, và tuyệt đối không nhét một
con số trần vào code.

---

## 4. VÌ SAO KHÔNG THỂ LẮP THẲNG VÀO ENGINE — ba rào cản kiến trúc

Đã kiểm bằng cách đọc code, không phải phỏng đoán.

### 4.1 Không có lệnh STOP chờ khớp

Cả ba chiến lược đều vào bằng **BUY/STOP** hoặc **SELL/STOP** — lệnh chờ, chỉ
khớp khi giá chạm mức kích hoạt. Engine hiện tại **không có khái niệm đó**:

- `paper_broker.py:132-142` — `on_bar` lấy lệnh treo ra và khớp tại
  **`bar.open`** của bar kế tiếp cộng trượt giá. Không có mức kích hoạt.
- `derivative_backtest.py:120-140` — khớp tại **`bar.close`** ngay bar tín hiệu.

Nói cách khác, "Entry = HIGH + x" hiện **không mô phỏng được**. Mà mức kích
hoạt không phải chi tiết trang trí: nó chính là bộ lọc "giá phải bứt qua đỉnh
nến mẫu thì mới vào" — bỏ nó đi là bỏ một phần bản chất chiến lược.

### 4.2 Đường cổ phiếu VN chỉ MUA được, không bán khống

`paper_broker.py:141-145`: `SELL` chỉ **giảm vị thế long đã settle**
(`min(qty, sellable_qty)`), không có gì thì trả `[]`. Không có bán khống.

Hệ quả:
- **Combo SELL không chạy được** trên cổ phiếu VN.
- **DOJI hedging không chạy được** — nó cần đồng thời một lệnh mua và một lệnh
  bán khống.

Đường **phái sinh** thì khác: `derivative_position.py:28,72` có `open_short`,
qty âm được, T+0. Nhưng `derivative_backtest.py:122,134` chỉ mở lệnh khi
`net == 0` — tức **giữ một vị thế ròng một chiều**, cũng **không hedging được**.

### 4.3 Không nơi nào trong repo giữ hai vị thế ngược chiều cùng lúc

Cả hai broker đều mô hình hoá một vị thế trên một mã. Hedging của DOJI đòi một
cơ chế mới hoàn toàn.

**Tóm lại:** trong ba chiến lược, **Hammer** (chỉ 1 lệnh, chỉ mua) là cái duy
nhất gần với năng lực hiện có. **Combo** chạy được nửa (nhánh BUY) trên cổ
phiếu, đủ cả hai nhánh trên phái sinh/crypto. **DOJI** không chạy được ở đâu
nếu chưa có cơ chế hedging.

---

## 5. GÓI GIAO ĐƯỢC NGAY — gói P1: ba bộ nhận dạng mẫu nến + đo tần suất

### 5.1 Vì sao gói này trước

Trước khi bỏ công xây cơ chế lệnh STOP và hedging (việc lớn, chạm thẳng vào bộ
mô phỏng tiền mà **mọi con số đo lường trong repo đang dựa vào**), cần biết một
điều rẻ hơn nhiều: **ba mẫu nến này có xuất hiện đủ nhiều để đáng làm không?**

Nếu Hammer chỉ xuất hiện 12 lần trong 10 năm trên cả rổ, câu hỏi về `x` và
`kTP` trở thành vô nghĩa. Đây đúng khuôn gói M (đo độ nhạy ngưỡng trước khi
chọn ngưỡng) đã dùng tốt hôm 04/09.

### 5.2 Việc

Viết **hàm thuần nhận dạng**, không chạm engine, không chạm broker:

1. `is_doji(bar, ...)` — theo §1.2, kèm luật "Near Doji" (>2 doji trước đó ⇒
   không hiệu quả).
2. `is_hammer(bar, ...)` — theo 4 điều kiện §1.3.
3. `combo_signal(bar, ma20, macd_hist) -> "buy"|"sell"|None` — theo §1.4.

Rồi **đo tần suất** trên dữ liệu đã có:
- Cổ phiếu VN khung **1d** (`bars_daily`) và **4h** (`_TF_SPEC` đã hỗ trợ cả
  hai — `backtest.py:293-300`, không cần thêm gì).
- Crypto perpetual khung **1d** và **1h** (`bars_crypto`, quyết định F).

Báo cáo: mỗi mẫu × mỗi khung × mỗi thị trường ⇒ số lần xuất hiện, số mã có ít
nhất một lần, phân bố theo năm.

### 5.3 Ràng buộc cứng

- **Không chạm `trading/broker.py`, `paper_broker.py`, `derivative_*.py`,
  `engine/`.** Gói này không đặt một lệnh nào.
- **Không thêm strategy vào `STRATEGIES`** (`backtest.py:290`) — chưa đến lúc.
- **Không sửa `config/config.yaml`.**
- Đặt hàm nhận dạng ở đâu: `trading/patterns.py` (file mới) — thuần OHLC, dễ
  test, không phụ thuộc broker. **Không nhét vào `strategies/`** vì chúng chưa
  phải strategy theo Protocol.
- Bảy chỗ mơ hồ ở §2: agent **phải chọn một giá trị làm mặc định để đo được**,
  nhưng **phải ghi rõ đã chọn gì và vì sao** trong báo cáo, và để giá trị đó
  thành **tham số có mặc định**, không phải hằng số chôn trong hàm.
- `x` theo ràng buộc §3 — không hằng số tuyệt đối.

### 5.4 Tiêu chí

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Nhận dạng đúng theo slide | Test đơn vị cho từng điều kiện, kể cả ca biên: doji hoàn hảo (close==open), búa có bóng trên dài (phải loại), búa xuất hiện sau xu hướng tăng (phải loại) |
| 2 | Luật "Near Doji" có hiệu lực | Test: chuỗi có 3 doji liên tiếp ⇒ doji thứ 3 phải bị loại |
| 3 | Đo được tần suất thật | Bảng: mẫu × khung (1d/4h VN, 1d/1h crypto) × số lần xuất hiện × số mã |
| 4 | Không hằng số đơn vị | Dán `grep -rn "[0-9]_000_000\|[0-9]e9\|[0-9]e8" trading/patterns.py` — rỗng cũng phải ghi là rỗng |
| 5 | Phá hoại có kiểm soát | Nới một điều kiện nhận dạng (ví dụ bỏ luật "bóng dưới ≥ 2× thân") ⇒ test tương ứng phải ĐỎ. Dán output đỏ, khôi phục, `grep -rn "SABOTAGE"` rỗng |
| 6 | Không hồi quy | 436 unit + 100 integration |
| 7 | Lint | `uv run ruff check trading tests scripts` sạch |

### 5.5 Phạm vi file

- **Sửa/tạo:** `trading/patterns.py` (mới), `tests/test_patterns.py` (mới),
  một script đo trong `scripts/`, một báo cáo trong
  `docs/superpowers/research/`.
- **Không đụng:** mọi thứ còn lại.

---

## 6. KHÔNG giao agent — chờ chủ dự án

| Mã | Câu hỏi | Vì sao không để agent chọn |
|---|---|---|
| **P-a** | Bảy chỗ mơ hồ §2 — đặc biệt `x` và `kTP` | Là tham số kinh tế, quyết định hình dạng chiến lược. Gói P1 chỉ chọn giá trị *để đo được*, không phải để chốt |
| **P-b** | Có đầu tư xây cơ chế **lệnh STOP** không? | Chạm bộ mô phỏng tiền mà mọi con số hiện có dựa vào. Nếu làm, phải làm ở nhánh riêng để không đụng `PaperBroker` đang dùng — xem §4.1 |
| **P-c** | Có đầu tư xây **hedging** không? | Cơ chế mới hoàn toàn (§4.3). DOJI phụ thuộc hẳn vào câu trả lời này |
| **P-d** | Ba chiến lược này chạy trên **thị trường nào** | Slide nhắm forex/chỉ số/crypto (tr.6), không nhắc cổ phiếu. Repo có cổ phiếu VN + phái sinh + crypto perp. Nhánh SELL chỉ chạy được ở hai cái sau |
| **P-e** | Nếu chọn crypto: **có dùng đòn bẩy không** | Quyết định F đã chốt perpetual, nhưng đòn bẩy vẫn chưa quyết |

---

## 7. Điều phải nói thẳng về kỳ vọng

Slide này là **tài liệu giảng dạy**, không phải bằng chứng về lợi thế. Nó không
kèm một phép đo nào: không backtest, không thống kê thắng/thua, không cỡ mẫu.
Trang 39 của chính slide còn xếp "Xây dựng hệ thống Backtest" vào phần **việc
người học phải tự làm**.

Trong khi đó repo này đã đo **bốn** chiến lược trên 10 năm dữ liệu và
**không cái nào thắng mua-và-giữ** (`2026-09-01-strategy-comparison-v2.md`).

Nên gói P1 phải được hiểu đúng: nó **đo xem có gì để đo không**, chứ không phải
bước đầu của việc triển khai một chiến lược đã được chứng minh. Nếu tần suất
mẫu quá thấp hoặc kết quả sơ bộ xấu, **dừng lại ở đó là một kết quả hợp lệ** và
tiết kiệm được toàn bộ công xây cơ chế lệnh STOP.

---

## 8. An toàn — không đổi

`real_trading_enabled` giữ `false`. Không gọi API đặt lệnh. Không sửa
`config/config.yaml`. Không nạp lại `bars_crypto`. Agent **không commit, không
push** — Claude audit rồi mới commit.
