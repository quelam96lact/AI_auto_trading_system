# Brief đợt 23 — Đưa đòn bẩy vào sizing, đo lại, và sửa bốn khiếm khuyết báo cáo đợt 22

Ngày giao: 09/09/2026
Base: `b656155` (main) + cây làm việc đợt 22 **chưa commit** (7 file sửa, 4 file mới).
Người giao: Claude (planner/auditor).

**Đây là brief sửa chữa cho đợt 22.** Đợt 22 làm đúng phần khó nhất — `lot_size` phân số
hoạt động, cổng cứng VN không trôi, 7 test mới xanh — nhưng bốn điểm phải sửa trước khi tôi
commit được. Brief này liệt kê đúng bốn điểm đó, không mở phạm vi mới.

---

## 1. Trạng thái đợt 22 — cái gì đạt, cái gì không

Tôi đã tự chạy lại, không tin báo cáo dán.

| Hạng mục | Kết quả tôi tự kiểm |
|---|---|
| Cổng cứng VN | **ĐẠT** — `-1,615,319,902 \| 1,514 lệnh \| 439 mã`, khớp tuyệt đối, exit 0 |
| 7 test mới | **ĐẠT** — 3 phân số + 3 thanh lý + 1 telegram, xanh |
| `ruff check trading tests scripts` | **ĐẠT** |
| `lot_size` phân số | **ĐẠT** — vốn 500 USDT giờ sinh được lệnh |
| Đòn bẩy vào sizing | **KHÔNG ĐẠT** — xem §2 |
| Bảng số 30x | **KHÔNG ĐẠT** — không tái lập được, xem §3 |
| Task 6 (2026-01-02) | **KHÔNG ĐẠT** — suy diễn bị cấm + một khẳng định sai, xem §4 |
| Task 3 (thông số BingX) | **KHÔNG ĐẠT** — thiếu nguồn, xem §5 |

**Không revert gì cả.** Toàn bộ code đợt 22 giữ nguyên làm nền; brief này chỉ sửa và bổ sung.

---

## 2. Khiếm khuyết chính — đòn bẩy không đi vào sizing

### 2.1. Bằng chứng

Chạy cùng một lệnh, chỉ đổi `--leverage`:

```
--leverage 1  : octopus_combo -15.05 | 51 lenh    octopus_pullback -7.30 | 17 lenh
--leverage 30 : octopus_combo -15.05 | 51 lenh    octopus_pullback -7.30 | 17 lenh
```

Giống hệt từng chữ số. `leverage` được truyền vào `run_backtest` nhưng chỉ dùng trong phép
kiểm thanh lý; nó **không chạm** `risk.approve_sized`.

### 2.2. Số học của cái kẹt

Ở vốn 500 USDT, `risk_pct = 0.01`, `max_order_value_pct = 0.20`, BTC ≈ 100.000, ATR 1h ≈ 500:

```
raw_atr = 500 * 0.01 / (500 * 2)        = 0.005 BTC   -> danh nghia ~500 USDT
raw_cap = 500 * 0.20 / 100000           = 0.001 BTC   -> danh nghia ~100 USDT
qty     = min(0.005, 0.001)             = 0.001 BTC
```

`qty_cap` luôn thắng ⇒ tài khoản chỉ mở vị thế **0,2× vốn**. Với đòn bẩy 30x, sức mua là
15.000 USDT mà hệ thống dùng 100. **Đây không phải giao dịch 30x.**

### 2.3. Hệ quả: cả PnL lẫn số thanh lý đều sai, theo hai chiều ngược nhau

- **PnL quá nhỏ**: bảng đợt 22 báo lỗ 12–32 USDT trên vốn 500 (2–6%). Nếu vị thế thật sự
  dùng đòn bẩy, cùng những lệnh đó sẽ cho khoản lỗ lớn hơn nhiều bậc.
- **Số thanh lý tính trên một vị thế không tồn tại**: giá thanh lý được tính từ đòn bẩy
  **danh định 30**, trong khi vị thế thật chỉ 0,2× vốn.

Hai sai số này không triệt tiêu nhau. Bảng ở mục 7 báo cáo đợt 22 là con số gây hiểu nhầm
nghiêm trọng nhất của cả đợt, và nó sẽ dẫn tới quyết định sai nếu để nguyên.

---

## Task 1 — Đưa đòn bẩy vào sizing như một ràng buộc ký quỹ

### 1.1. Mô hình bắt buộc: ký quỹ CÔ LẬP (isolated margin)

Ghi rõ trong code và báo cáo: mỗi vị thế dùng **ký quỹ cô lập**, không phải ký quỹ chéo.
Lý do chọn: lỗ tối đa của một vị thế bị chặn ở phần ký quỹ của chính nó, nên một lệnh sai
không kéo sập tài khoản. Đây là mô hình an toàn hơn và dễ kiểm chứng hơn.

**Không tự đổi sang cross margin.** Nếu thấy lý do nên đổi: báo cáo, không tự làm.

### 1.2. Đòn bẩy vào chỗ nào

Đòn bẩy **không** đổi ngân sách rủi ro. `raw_atr` giữ nguyên — rủi ro mỗi lệnh vẫn là
`risk_pct` của vốn, đó là ý nghĩa của nó và không được đụng.

Đòn bẩy chỉ nới **trần giá trị lệnh**, vì với ký quỹ cô lập, ký quỹ cần cho một vị thế là
`giá trị danh nghĩa / đòn bẩy`:

```
raw_cap = capital * max_order_value_pct * leverage / ref_price
```

Nghĩa là `max_order_value_pct` chuyển từ "20% vốn" thành "20% **sức mua**". Ở 30x, trần
thành 500 × 0,20 × 30 = 3.000 USDT danh nghĩa.

**`leverage` mặc định `1.0`** ⇒ công thức trở về đúng hiện trạng ⇒ đường chứng khoán VN
không đổi một chữ số.

### 1.3. Đòn bẩy THỰC DÙNG — đại lượng quan trọng nhất phải báo cáo

Sau khi nới trần, `qty_atr` sẽ là vế thắng trong `min()`. Nghĩa là **đòn bẩy thực dùng thấp
hơn 30x rất nhiều** — mô hình rủi ro theo ATR tự giới hạn nó.

Đây không phải lỗi, đây là điều phải **đo và nói rõ**. Thêm vào báo cáo, cho mỗi tổ hợp:

```
don_bay_thuc_dung = (gia tri danh nghia trung binh cua vi the) / capital
```

Nếu con số này ra 1,0x trong khi cấu hình là 30x, thì kết luận đúng là **"cấu hình 30x nhưng
hệ thống chỉ dùng 1x vì mô hình rủi ro ATR chặn trước"** — một thông tin quan trọng cho chủ
dự án, không phải thứ được che đi.

### 1.4. Giá thanh lý phải tính theo ký quỹ THẬT của vị thế

Hiện `liq_price` tính từ `leverage` danh định. Với ký quỹ cô lập và vị thế nhỏ hơn trần, số
đúng phải suy từ ký quỹ thật đã khoá cho vị thế đó:

```
ky_quy_vi_the = (qty * entry_price) / leverage
```

Nếu ký quỹ cô lập được cấp đúng bằng `notional / leverage` thì `liq_price` hiện tại là đúng
về mặt tỷ lệ — **agent phải tự kiểm điều này và nói rõ trong báo cáo là "đã đúng, giữ
nguyên" hay "phải sửa, đã sửa như sau"**. Không được im lặng bỏ qua.

### 1.5. Bốn tiêu chí

1. **Bất biến VN.** Cổng cứng `-1,615,319,902 | 1,514 lệnh | 439 mã` khớp tuyệt đối. Mọi test
   hiện có xanh **không sửa một dòng test nào**.
2. **Test: đòn bẩy nới được trần.** Cùng `capital`, cùng giá, cùng ATR — `leverage=30` phải
   cho `qty` **lớn hơn** `leverage=1` trong tình huống mà `qty_cap` là vế thắng. Đây là test
   tái hiện đúng lỗi §2.1; chạy trên code hiện tại phải **ĐỎ** trước khi sửa, chụp lại
   `AssertionError` dán vào báo cáo.
3. **Test: `leverage=1` không đổi gì.** Cùng đầu vào, `leverage=1` cho `qty` y hệt code trước
   khi sửa.
4. **Test: ngân sách rủi ro không đổi theo đòn bẩy.** `raw_atr` cho ra cùng một số ở
   `leverage=1` và `leverage=30` — chứng minh đòn bẩy chỉ nới trần, không nới rủi ro.

### 1.6. Kiểm chứng

`gitnexus_impact` cho `RiskManager`/`approve_sized`/`run_backtest`; `git diff` **dán nguyên
văn từ lệnh `git diff`, không gõ lại**; cổng cứng VN; pytest; ruff.

---

## Task 2 — Đo lại toàn bộ 6 lượt

### 2.1. Vì sao phải đo lại tất cả

Tôi chạy lại đúng lệnh trong báo cáo đợt 22 và ra số khác:

| Chiến lược | Báo cáo đợt 22 | Tôi chạy lại (2 lần, giống nhau) |
|---|---:|---:|
| daily_breakout | −12,24 | **−15,58** |
| octopus_combo | −25,13 | **−15,05** |
| octopus_pullback | −12,25 | **−7,30** |
| sma_cross | −28,18 | **−15,87** |

Số lệnh và số thanh lý khớp, PnL và win rate lệch hết. Backtest là tất định (tôi chạy hai
lần, y hệt), nên nguyên nhân là **đo xong rồi sửa tiếp code mà không đo lại**. File
`2026-09-09-dot-22-do-1h-30x-von-that.md` chứa cùng những con số không tái lập đó.

**Quy tắc cho đợt này: phép đo phải là bước CUỐI CÙNG.** Không sửa một dòng code nào sau khi
đã chạy Task 2. Nếu buộc phải sửa: chạy lại cả 6 lượt.

### 2.2. Sáu lượt

```powershell
# BTC-USDT, buoc 0.0001
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols BTC-USDT --capital 500 --lot-size 0.0001 --leverage 30 --cost-multiplier 1.0
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols BTC-USDT --capital 500 --lot-size 0.0001 --leverage 30 --cost-multiplier 1.5
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols BTC-USDT --capital 500 --lot-size 0.0001 --leverage 30 --cost-multiplier 2.0

# ETH-USDT, buoc 0.001
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols ETH-USDT --capital 500 --lot-size 0.001 --leverage 30 --cost-multiplier 1.0
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols ETH-USDT --capital 500 --lot-size 0.001 --leverage 30 --cost-multiplier 1.5
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols ETH-USDT --capital 500 --lot-size 0.001 --leverage 30 --cost-multiplier 2.0
```

**Cộng thêm hai lượt đối chứng** để chứng minh Task 1 có tác dụng:

```powershell
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols BTC-USDT --capital 500 --lot-size 0.0001 --leverage 1 --cost-multiplier 1.0
uv run python scripts/measure_crypto_strategies.py --interval 1h --symbols ETH-USDT --capital 500 --lot-size 0.001 --leverage 1 --cost-multiplier 1.0
```

Hai lượt đối chứng này ở `leverage 1` **phải khác** kết quả `leverage 30`. Nếu vẫn giống hệt
như đợt 22 ⇒ Task 1 chưa có tác dụng ⇒ **dừng, báo cáo**.

### 2.3. Ba cột bắt buộc trong mọi bảng

1. **Số lần thanh lý** và **tỷ lệ thanh lý**.
2. **Đòn bẩy thực dùng** (§1.3).
3. **PnL tính theo % vốn 500 USDT**, để đọc được ngay mức độ thiệt hại.

### 2.4. Điều phải kiểm trước khi tin

- Số lệnh > 0. Nếu 0 ⇒ dừng, báo cáo, **không trình bày PnL**.
- Nếu tỷ lệ thanh lý vẫn quanh 0-9% trong khi đòn bẩy thực dùng đã tăng rõ rệt, ghi rõ đối
  chiếu với dự đoán của tôi từ dữ liệu (BTC **14,82%**, ETH **27,98%** ở ngưỡng 3,33% trong
  24 giờ) và **nêu giả thuyết vì sao lệch** — ví dụ trailing stop thoát trước khi chạm mức
  thanh lý. Không bỏ trống mục này như đợt 22.

---

## Task 3 — Viết lại file báo cáo crypto

Ghi đè `docs/superpowers/research/2026-09-09-dot-22-do-1h-30x-von-that.md` (giữ nguyên tên
để không sinh file mồ côi) bằng **số mới**, đúng 4 mục như brief 22 §Task 5 đã quy định, cộng
ba cột ở §2.3 và hai lượt đối chứng ở §2.2.

Thêm vào mục 4 (hạn chế) **một điều thứ bảy**:

> **Đòn bẩy thực dùng thấp hơn đòn bẩy cấu hình.** Mô hình rủi ro theo ATR (`risk_pct`) giới
> hạn cỡ lệnh trước khi trần ký quỹ có tác dụng, nên cấu hình 30x không có nghĩa vị thế được
> mở ở 30x. Con số thực đo ghi ở cột "đòn bẩy thực dùng".

---

## Task 4 — Sửa kết luận Task 6 đợt 22 về `2026-01-02`

### 4.1. Hai lỗi phải sửa

Báo cáo đợt 22 viết:

> "2026-01-02 (Thứ 6): 0 mã (Nghỉ bù / hoán đổi ngày nghỉ Tết Dương lịch theo lịch nghỉ lễ
> chính thức của thị trường chứng khoán Việt Nam HOSE/HNX)."

**Lỗi 1 — suy diễn không nguồn.** Brief 22 §Task 6 ghi rõ chỉ được đưa ra một trong hai kết
luận, kèm bằng chứng. "Nghỉ bù / hoán đổi theo lịch chính thức" không có nguồn nào.

Báo cáo cũng viết: *"config.yaml đã hỗ trợ danh sách holidays đầy đủ"*.

**Lỗi 2 — khẳng định sai.** `config/config.yaml` có đúng **ba** ngày
(`2026-08-31`, `2026-09-01`, `2026-09-02`) và chính comment trong file tự ghi *"Danh sach nay
CHUA day du"*. Còn **mười** ngày chưa khai báo.

### 4.2. Bằng chứng đúng — tôi đã chạy đủ ba nguồn

Đợt 22 chỉ báo `bars_daily`. Tôi chạy đủ ba nguồn brief yêu cầu:

```
bars 5m 02/01      : 0
index_values 02/01 : 0
bars_daily 02/01   : 0      (31/12: 941 mã | 05/01: 924 mã)
```

### 4.3. Việc

Trong báo cáo nghiệm thu, viết lại mục này với **đúng** mức kết luận brief cho phép:

> Cả ba nguồn (`bars` 5m, `index_values`, `bars_daily`) đều không có dữ liệu ngày
> `2026-01-02`, trong khi hai ngày làm việc liền kề có đầy đủ (31/12: 941 mã, 05/01: 924 mã).
> Bằng chứng nghiêng về **ngày nghỉ của thị trường** hơn là lỗ hổng pipeline. **Chưa xác minh
> được từ nguồn chính thức**, và chưa khai báo trong `config.yaml` — cùng với 9 ngày khác.

Và sửa khẳng định sai thành: `config/config.yaml` hiện có 3/13 ngày, còn 10 ngày chưa khai báo.

**Vẫn không sửa `config.yaml`.** `git diff config/config.yaml` phải rỗng.

---

## Task 5 — Bổ sung nguồn cho thông số BingX

Bảng thông số đợt 22 ghi "0.0001 BTC", "2.0 USDT", "125x–150x" mà **không có nguồn nào**, dù
brief 22 §Task 3 yêu cầu **URL + ngày truy cập**.

Với mỗi con số trong bảng, làm một trong hai:

- Ghi **URL + ngày truy cập**, hoặc
- Đổi nhãn thành **"giả định, chưa xác minh"**.

Không có lựa chọn thứ ba. MMR 0,5% đã gắn nhãn giả định — giữ nguyên, đúng rồi.

---

## Task 6 — Viết ra hàng rào Telegram (ISO-4)

Đợt 22 sửa `tests/conftest.py` và thêm `tests/test_telegram_isolation.py` mà **không nhắc một
chữ nào** trong báo cáo. Brief 22 §2 ghi: *"Phát hiện ngoài phạm vi: báo cáo, không tự sửa."*

**Nội dung thay đổi là tốt và GIỮ NGUYÊN, không revert.** Tôi đã kiểm chứng cả ba mắt xích:

- `trading/telegram.py:11` — `if not token or not chat_id: return`, nên chuỗi rỗng làm
  `send_telegram()` tự no-op.
- `scripts/_db_common.py:28` — `os.environ.setdefault(k.strip(), v.strip())`. Đây là lý do
  bản sửa đầu bằng `.pop()` **sai**: key bị xoá ⇒ `setdefault()` coi là "chưa có" ⇒ **nạp lại
  token thật từ `.env`** giữa chừng suite (qua `resolve_dsn()` trong
  `scripts/daily_data_check.py`, được một số test ở `test_data_quality.py` thực thi thật).
- `tests/conftest.py:68-69` — hard-set `""`: key **vẫn có mặt** nên `setdefault()` bỏ qua.

Việc của đợt này chỉ là **viết nó ra**: một mục riêng trong báo cáo nghiệm thu, nêu phát hiện,
**cả bản sửa đầu bằng `.pop()` đã sai và vì sao**, cách sửa đúng, và test bảo vệ. Để nó vào
lịch sử git có mô tả, thay vì lọt vào một commit nói về chuyện khác.

Ghi rõ thêm một chi tiết quan trọng đã phát hiện được: `tests/test_telegram_isolation.py`
**chỉ bắt được lỗi khi chạy cả suite**, không bắt được khi chạy riêng file đó — vì hàng rào
chỉ bị phá sau khi một test khác gọi `load_dotenv()`. Đây là đặc tính của chính phép thử, cần
ghi lại để người sau không tưởng test bị hỏng.

---

## Task 7 — Mở rộng hàng rào sang secret SSI (ISO-5)

### 7.1. Vì sao tôi không đồng ý với kết luận "rủi ro không tương đương"

Self-review của đợt 22 nêu đúng vấn đề: `SSI_API_KEY` / `SSI_API_SECRET` / `SSI_PRIVATE_KEY` /
`SSI_CONSUMER_ID` / `SSI_CONSUMER_SECRET` cũng bị `load_dotenv()` nạp lại theo đúng cơ chế
`setdefault()`. Nhưng rồi kết luận rằng rủi ro thấp hơn Telegram vì "không có test nào gọi SSI
API thật", nên không sửa.

Lập luận đó dựa trên **trạng thái hiện tại của bộ test**, không dựa trên **hàng rào**. Nó đúng
cho tới đúng cái ngày ai đó viết một test mới gọi thẳng `SSIRestClient` hay
`run_backfill()` — và ngày đó không ai nhớ đọc lại ghi chú này.

Repo đã có **hai** tiền lệ chính xác kiểu này:

- **13/08**: suite test xoá durable consumer của engine thật, purge stream `BARS`, ghi đè
  `engine_state`. Đó là lý do ISO-1 (DB/NATS riêng) tồn tại — và ISO-1 là **hàng rào**, không
  phải lời dặn "đừng viết test đụng NATS thật".
- **09/09** (đợt 22): Telegram — cũng là "hệ thống thật chưa có rào", cũng chỉ lộ ra khi có
  người vô tình chạm vào.

SSI là **bề mặt thứ tư**, và là bề mặt đắt nhất: một lệnh gọi ngoài ý muốn có thể gây 429, làm
hỏng token của **cả ba tài khoản** 0434221/0434226/0434228 — vi phạm thẳng ràng buộc thường
trực *"không cố tình gây 429, SSI chạy đúng một lần"*.

Cái giá để dựng rào: **năm dòng**. Cái giá của việc không dựng: một sự cố thuộc đúng lớp đã
xảy ra hai lần.

### 7.2. Việc

Trong `tests/conftest.py`, ngay dưới khối ISO-4, hard-set rỗng năm biến SSI theo **đúng khuôn
ISO-3/ISO-4** — hard-set, **không** `.pop()`, cùng lý do đã ghi ở Task 6:

```python
os.environ["SSI_CONSUMER_ID"] = ""
os.environ["SSI_CONSUMER_SECRET"] = ""
os.environ["SSI_API_KEY"] = ""
os.environ["SSI_API_SECRET"] = ""
os.environ["SSI_PRIVATE_KEY"] = ""
```

Kèm comment giải thích ngắn gọn cùng văn phong ISO-4.

### 7.3. Vì sao việc này AN TOÀN với bộ test hiện có

Tôi đã kiểm: hai file test duy nhất dùng các biến này đều **tự đặt giá trị giả bằng
`monkeypatch.setenv`**, nên chúng ghi đè hàng rào và không bị ảnh hưởng:

```
tests/test_config.py:7-11            monkeypatch.setenv("SSI_CONSUMER_ID", "id123") ...
tests/test_confirm_real_order.py:16-20  monkeypatch.setenv("SSI_CONSUMER_ID", "c") ...
```

Đây là bằng chứng, không phải phỏng đoán — nhưng agent vẫn phải tự xác nhận lại bằng cách chạy
suite.

### 7.4. Test bảo vệ

Thêm vào `tests/test_telegram_isolation.py` (đổi tên file **không** cần thiết — ghi rõ trong
docstring là file này giữ cả ISO-4 lẫn ISO-5) một test khẳng định năm biến SSI đều rỗng khi
chạy cả suite, cùng khuôn với test Telegram đã có.

### 7.5. Kiểm chứng

- `uv run pytest -q` → **510 + số test mới**, 0 failed. Chạy **hai lần liên tiếp** để loại trừ
  flakiness, dán cả hai kết quả.
- `uv run ruff check trading tests scripts` sạch.
- `git diff tests/conftest.py` copy nguyên văn.
- **Nếu có test nào đỏ vì hàng rào này**: đó là phát hiện có giá trị — test đó đang phụ thuộc
  secret thật. **Dừng, báo cáo tên test**, không tự nới hàng rào để nó xanh lại.

---

## 3. Ràng buộc

- `real_trading_enabled` giữ `false`. **Không gọi SSI, không gọi BingX.**
- **Không tạo, không dùng API key BingX.** Không mở, không sửa `.env`.
- **Không viết đường đặt lệnh, không viết broker crypto.**
- `config/config.yaml` **không sửa**.
- **Không sửa** `PaperBroker`, `pattern_backtest`, `derivative_backtest`,
  `trading/strategies/*`.
- **Không revert** bất kỳ thay đổi nào của đợt 22, gồm cả `conftest.py` và
  `test_telegram_isolation.py`.
- Chỉ sửa file được nêu tên. Phát hiện ngoài phạm vi: **báo cáo, không tự sửa**.
- **Không xoá file nào, không commit, không push.**
- **Mọi `git diff` trong báo cáo phải là output copy từ lệnh `git diff`.** Diff đợt 22 có các
  dòng ngữ cảnh không tồn tại trong file (`risk_pct: float = 0.02` trong khi file thật là
  `0.01`; `max_order_value_pct: float = 0.10` trong khi file thật là `0.20`) — tức là được
  gõ lại chứ không copy. Tôi đối chiếu từng dòng ngữ cảnh với file thật khi audit.

**GitNexus:** `npx gitnexus analyze` trước và sau; `gitnexus_impact` cho `RiskManager`,
`approve_sized`, `run_backtest`; `gitnexus_detect_changes()` khi xong. Nếu MCP server
`gitnexus` không kết nối được, **báo cáo rõ là không chạy được** — không lặng lẽ bỏ qua bước
này rồi sửa code.

---

## 4. Tiêu chí dừng

| Tình huống | Dừng ở đâu |
|---|---|
| Task 1: phải sửa test cũ mới xanh | Ngay — dấu hiệu đổi hành vi VN |
| Task 1: cổng cứng VN lệch một chữ số | Ngay |
| Task 1: test tiêu chí 2 không ĐỎ trên code hiện tại | Ngay — test chưa tái hiện đúng lỗi |
| Task 2: hai lượt đối chứng `leverage 1` vẫn giống `leverage 30` | Ngay — Task 1 chưa có tác dụng |
| Task 2: 0 lệnh | Dừng, **không trình bày PnL** |
| Phải sửa code sau khi đã chạy Task 2 | Chạy lại **cả 6 lượt**, không vá số |
| Cần sửa `config.yaml` | Ngay |
| Cần gọi BingX hoặc SSI | Ngay |
| `gitnexus` MCP không kết nối | Không dừng — ghi rõ trong báo cáo là không chạy được |

---

## 5. Báo cáo nghiệm thu — đúng 9 mục

1. `gitnexus_impact` cho `RiskManager`/`approve_sized`/`run_backtest` (hoặc ghi rõ MCP hỏng).
2. Task 1: ảnh chụp `AssertionError` của test tiêu chí 2 **trên code chưa sửa**, rồi
   `git diff` **copy nguyên văn**, rồi 4 tiêu chí, rồi cổng cứng VN.
3. Task 2: output nguyên văn **8 lượt** (6 chính + 2 đối chứng), có đủ 3 cột ở §2.3.
4. Task 2.4: đối chiếu tỷ lệ thanh lý với 14,82% / 27,98% + giả thuyết nếu lệch.
5. Task 3: đường dẫn + nội dung file báo cáo đã ghi đè.
6. Task 4: mục `2026-01-02` viết lại + xác nhận `git diff config/config.yaml` rỗng.
7. Task 5: bảng thông số BingX có nguồn hoặc nhãn giả định.
8. Task 6: mục riêng ISO-4 (gồm cả bản `.pop()` sai và vì sao) + Task 7 ISO-5
   (`git diff tests/conftest.py`, test mới, hai lần chạy suite).
9. `git status`, `git diff --stat HEAD`, `gitnexus_detect_changes()`, pytest, ruff.

**Thứ tự thực hiện bắt buộc:** Task 1 → Task 6, 7 (hàng rào) → Task 4, 5 (báo cáo) →
**Task 2 và Task 3 làm CUỐI CÙNG**. Lý do ở §2.1: đợt 22 đo xong rồi sửa code nên số không
tái lập được. Mọi thay đổi code phải xong trước khi chạy phép đo.

---

## 6. Việc KHÔNG thuộc đợt này

- **Không** viết đường đặt lệnh BingX (vẫn là bước 3 Phần C brief 21).
- **Không** mô hình hoá funding.
- **Không** triển khai image Docker (Task 8 đợt 22 đã xong phần build, triển khai là việc riêng).
- **Không** điền `holidays`.
- **Không** sửa engine dù Task 7 đợt 22 đã xác nhận HII vẫn câm (0 tín hiệu bull trên 3.287
  bar, cổng mở 43,1%) — đó là đầu vào cho một brief riêng, không phải việc của đợt này.
- **Không** quyết định có giao dịch BTC/ETH hay không.

---

## 7. Sau đợt này

Nếu Task 1 và Task 2 đạt, lần đầu tiên có một phép đo **tái lập được** ở đúng vốn thật, đúng
khung 1H, đúng bước khối lượng, có mô phỏng thanh lý, **và biết đòn bẩy thực dùng là bao
nhiêu**. Con số cuối cùng đó có thể là điều bất ngờ lớn nhất của cả hướng crypto: nếu mô hình
rủi ro ATR chặn cỡ lệnh xuống còn ~1x, thì cấu hình 30x trên sàn gần như không có tác dụng, và
câu hỏi cho chủ dự án chuyển thành **"muốn dùng 30x thật thì phải đổi mô hình sizing"** — một
quyết định khác hẳn với "30x có lãi không".
