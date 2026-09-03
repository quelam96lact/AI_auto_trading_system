# Plan — BingX giai đoạn 2: đo chiến lược trên dữ liệu crypto

Viết 01:20 ngày 04/09, ngoài giờ giao dịch. Mọi số đã đo trực tiếp trên DB và
mã nguồn tối nay.

**Đính chính ngay từ đầu:** `2026-09-03-plan-xu-ly-ton-dong.md` §5 và câu trả
lời của tôi tối nay đều nói *"gói C chỉ chạm `scripts/`"*. **Sai.** Có một chỗ
chặn nằm trong `trading/risk.py` — mục 2 dưới đây. Gói C phải tách làm hai.

---

## 1. Nền dữ liệu — đã đo, không cần nạp thêm

```sql
select "interval", count(*), count(distinct symbol), min(ts)::date, max(ts)::date
from bars_crypto group by 1;
```

| interval | số nến | số cặp | từ | đến |
|---|---|---|---|---|
| `1d` | 27.124 | 20 | 2021-05-14 | 2026-09-02 |
| `1h` | 385.363 | 20 | 2024-04-27 | 2026-09-02 |

20 cặp: `1000PEPE ADA AAVE ARB BTC CRV DOGE ETH HYPE KAS LDO ORDI SOL STRK TAO
TRX UNI XAUT XRP ZEC` (đều `-USDT`).

Hai chi tiết kỹ thuật đã kiểm:

- Cột khung thời gian tên là **`interval`**, không phải `timeframe`. Nó là từ
  khoá SQL nên mọi truy vấn phải viết `"interval"` có ngoặc kép.
- `bars_crypto` **không phải hypertable** (`timescaledb_information.hypertables`
  chỉ có `bars`, `bars_daily`, `index_values`). Nên cái bẫy `pg_dump -t` ra file
  rỗng 486 byte **không** áp dụng ở đây — sao lưu bảng này bằng `pg_dump` bình
  thường vẫn có dữ liệu.

**Thiên lệch phải nói trước khi đo:** 20 cặp này được chọn ngày 02/09, tức là
chọn trong số coin **còn sống và còn niêm yết hôm nay**. Đây là thiên lệch sống
sót (survivorship bias) và nó làm mọi kết quả đẹp lên. Không sửa được bằng dữ
liệu đang có — nhưng **phải ghi trong báo cáo**, đúng như bài học 245 mã hỏng ở
thị trường VN.

---

## 2. Chỗ chặn thật: `RiskManager` đóng cứng **lô 100 đơn vị**

Đây là phát hiện chính của plan này, và tôi **đã chạy thật để chứng minh**, không
suy luận trên giấy. Phép toán nằm trong `RiskManager.approve_sized`
(`trading/risk.py:64`, phần sizing ở dòng `99-108`):

```python
qty_atr = int((self.capital * self.risk_pct / (atr * self.atr_multiplier)) // 100) * 100
qty_cap = int((self.capital * self.max_order_value_pct / ref_price) // 100) * 100
qty = min(qty_atr, qty_cap)
if qty < 100:
    ... tu choi ("qty sau cap < 1 lo")
```

Lô 100 là luật sàn HOSE. **Crypto không có lô, và giao dịch theo phần lẻ.**

Chạy `approve_sized` trực tiếp trên code hiện tại, ba tình huống:

```
von=        100,000  gia= 60,000.00  -> None
von=  1,000,000,000  gia= 60,000.00  -> Signal(symbol='X', side='BUY', qty=3300)
von=        100,000  gia=      0.20  -> Signal(symbol='X', side='BUY', qty=50000)
```

Đọc ba dòng này theo đúng thứ tự:

1. **Vốn 100.000 USD, BTC giá 60.000 ⇒ `None`.** Không phải lỗi, không phải
   ngoại lệ — lệnh **bị từ chối im lặng**. Đo BTC hôm nay sẽ ra **0 lệnh** và
   báo cáo trông như "chiến lược không vào lệnh nào", chứ không như "công cụ đo
   bị hỏng".
2. **Vốn 1.000.000.000 (mặc định của `measure_strategy`, đơn vị VND) ⇒ 3.300
   BTC.** Vô nghĩa về kinh tế nhưng **trông hoàn toàn hợp lệ** trong bảng kết
   quả.
3. **DOGE giá 0,20 ⇒ 50.000 đơn vị, chạy trơn tru.**

Nên nếu đo ngay hôm nay, thứ nhận được là một bảng trong đó **coin giá cao lặng
lẽ biến mất còn coin giá thấp thì có số** — một thiên lệch chọn mẫu do công cụ
tạo ra, không phải do thị trường, và **không có gì trong đầu ra báo là nó tồn
tại**.

Đó đúng là kiểu hỏng tệ nhất mà gói B tồn tại để chặn: **số ra sai mà trông hợp
lý**. Gói B đã gỡ phí/thuế/T+3; lô 100 là mảnh cuối cùng còn sót của luật VN
nằm trên đường đo.

`Signal.qty` khai `int` (`trading/strategy.py`) nên cả đường đi là số nguyên.
Không đề nghị đổi sang số thực trong plan này — **đổi kiểu là việc lớn hơn nhiều
và không cần cho một phép đo.** Cách nhỏ nhất: cho `RiskManager` nhận **đơn vị
lô** (mặc định 100, crypto truyền 1), giữ nguyên số nguyên.

Với lô = 1 thì "1 đơn vị" là gì do người đo chọn khi ấn định vốn — nếu muốn phần
lẻ BTC thì đo bằng đơn vị nhỏ hơn (ví dụ vốn tính bằng USD và giá tính bằng USD
thì 1 đơn vị = 1 BTC; muốn mịn hơn thì phải scale, và **nếu scale thì phải ghi
rõ hệ số trong báo cáo**, không được giấu trong script).

---

## 3. Tin tốt đã kiểm: `backtest.py` gần như trung lập thị trường

`2026-09-02-tong-hop-ton-dong-va-danh-gia-bingx.md` §6 xếp `backtest.py` vào
nhóm "dính chặt thị trường VN vì import `calendar_vn`". Tôi kiểm lại từng chỗ
dùng:

```
trading/backtest.py:273  from trading.calendar_vn import TZ
trading/backtest.py:324  frm = ...replace(tzinfo=TZ)
trading/backtest.py:325  to  = ...replace(tzinfo=TZ) + timedelta(days=1)
```

**Chỉ dùng `TZ`, không dùng `SESSIONS`, không gọi `is_trading_time`.** Vòng lặp
backtest không lọc bar theo giờ phiên VN. Nên `run_backtest` chạy trên nến
crypto 24/7 mà **không âm thầm vứt bar** — điều tôi lo nhất trước khi đo.

**Nhưng `TZ` vẫn là một cái bẫy lệch một ngày.** `--from 2025-01-01` được hiểu
là `2025-01-01 00:00 +07:00` = `2024-12-31 17:00 UTC`, trong khi nến `1d` crypto
nằm ở `00:00 UTC`. Nên biên cửa sổ **lấy dư một nến của ngày hôm trước**. Với
kỳ ngoài mẫu niêm phong, lệch một nến ở biên là đủ để làm số không tái lập
được. Phải xử lý tường minh và **ghi trong báo cáo**, không im lặng.

Đây là lần thứ ba dự án vấp đúng hình dạng lỗi này (`ts::date` đổi múi giờ ở
UTC; giờ đồng hồ vs giờ thị trường). Ghi lại cho lần sau.

---

## 4. Tách gói C làm hai

| | Chạm | Khi nào | Vì sao |
|---|---|---|---|
| **C-a** | `trading/risk.py` + `tests/` | **cùng đợt B1/B2/C3 tối nay** | vào image ⇒ phải dựng lại |
| **C-b** | chỉ `scripts/` + `docs/` | cuối tuần | không vào image, đo bao nhiêu lần cũng được |

Gộp C-a vào đợt dựng lại tối nay để cuối tuần **không phải dựng lại lần nữa** —
cuối tuần chỉ còn đo.

### 4.1 C-a — `RiskManager` nhận đơn vị lô

**Việc:** thêm tham số đơn vị lô cho `RiskManager`, mặc định **100**. Ba chỗ
trong `risk.py:99-108` dùng hằng số 100 phải đọc từ tham số đó (kể cả điều kiện
từ chối `qty < 100`).

**Ràng buộc cứng — hành vi mặc định bất biến.** Engine dựng `RiskManager` không
truyền đơn vị lô ⇒ phải ra **đúng từng con số** như hôm nay. Đây là ranh giới
giữa gói này và phiên thứ Hai.

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Tham số hoá đơn vị lô | test: lô=1, vốn 100.000, giá 60.000 ⇒ `approve_sized` trả Signal có qty > 0 (hôm nay: **`None`**) |
| 2 | Mặc định bất biến | test khẳng định `RiskManager(capital=...)` không tham số vẫn làm tròn xuống bội 100 và từ chối qty < 100 |
| 3 | Đo lại VN không đổi | chạy `measure_strategy --strategy sma_cross --limit 3` trước/sau, `diff` **rỗng** |
| 4 | Phá hoại | bỏ phần làm tròn theo lô ⇒ test 2 **đỏ**; dán nguyên văn |
| 5 | Không hồi quy | `pytest -m "not integration" -q` **và** `pytest -m integration -q`; nền **393 + 97, 0 đỏ** |
| 6 | Lint | `ruff check trading tests scripts` sạch |

**Phạm vi:** `trading/risk.py`, `tests/`.
**Không đụng:** `trading/strategy.py` (không đổi `qty: int` thành số thực),
`trading/engine/*`, `config/config.yaml`, `trading/backtest.py`.

### 4.2 C-b — script đo crypto (cuối tuần)

**Việc:** một script đọc `bars_crypto` và chạy `run_backtest` với kinh tế
crypto. Gợi ý tái dùng `scripts/measure_strategy.py` bằng cách thêm nguồn dữ
liệu, **không** viết script thứ hai song song — hai script đo là hai công thức
cho một khái niệm, đúng thứ kỷ luật `4ea4c8d` diệt.

Hai chỗ `measure_strategy.py` đang đóng cứng vào VN:

- dòng 131: `SELECT DISTINCT symbol FROM bars_daily`
- `measure_one()`: `storage.read_daily_bars(...)`

**Đọc `bars_crypto` bằng SQL ngay trong script**, không thêm hàm đọc crypto vào
`trading/storage/db.py` — giữ `db.py` trung lập với thị trường, đúng luật đã
đặt ở gói A. Việc này cũng khiến C-b không chạm image.

Tham số kinh tế truyền qua đường gói B đã mở (`run_backtest(..., fee_rate=,
sell_tax_rate=, slippage_bps=, settle_days=)`):

| Tham số | Crypto | Ghi chú |
|---|---|---|
| `sell_tax_rate` | `0.0` | thuế bán là thứ riêng của VN |
| `settle_days` | `0` | không có T+2,5 |
| `fee_rate` | **phải tra** | xem dưới |
| `slippage_bps` | **phải chọn và đóng băng** | xem dưới |

**Không được đoán phí.** Tôi không có số phí BingX đã kiểm chứng, và một con số
phí sai làm hỏng toàn bộ phép đo theo hướng lạc quan. Tra từ tài liệu chính
thức BingX, **ghi nguồn và ngày tra vào báo cáo**, và đóng băng trước khi nhìn
kết quả. Trượt giá cũng vậy — chọn một con số, ghi lý do, rồi mới chạy.

### 4.3 Kỷ luật đo — không thương lượng

Đúng ba chốt đã bắt được một quy tắc lãi +1,11 tỷ trong mẫu hoá ra lỗ −8,82 tỷ
ngoài mẫu:

1. **Đóng băng mọi ngưỡng và tham số TRƯỚC khi nhìn bất kỳ kết quả nào**, ghi
   vào file có commit.
2. **Kỳ ngoài mẫu niêm phong, chạy đúng một lần.** Đề xuất chia (phải chốt
   trước khi chạy): trong mẫu `2021-05-14 → 2024-12-31`, ngoài mẫu
   `2025-01-01 → 2026-09-02`. Với khung `1h` thì trong mẫu `2024-04-27 →
   2024-12-31` — ngắn, và phải nói rõ là ngắn.
3. **Số phải tái lập được:** chạy lại ra đúng từng con số.

**Mốc so sánh bắt buộc là mua-và-giữ**, không phải "có lãi hay không". Ở thị
trường có xu hướng tăng dài như crypto, gần như mọi chiến lược đều "có lãi" —
câu hỏi duy nhất có nghĩa là **có thắng được mua-và-giữ sau phí không**.
`BacktestReport.buy_and_hold_pnl` đã có sẵn.

### 4.4 Tiêu chí hoàn thành C-b

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Tham số đóng băng | file tham số đã commit **trước** commit chứa kết quả (đối chiếu bằng `git log`) |
| 2 | Đọc đúng dữ liệu | số nến đọc được khớp bảng mục 1 theo từng cặp |
| 3 | Không lệch biên múi giờ | test: `--from`/`--to` cho crypto lấy đúng nến `00:00 UTC`, không dư nến hôm trước (mục 3) |
| 4 | Đo trong mẫu | bảng 20 cặp: PnL chiến lược vs mua-và-giữ, số lệnh, số nến |
| 5 | Ngoài mẫu | chạy **một lần**, dán nguyên văn |
| 6 | Tái lập | chạy lại bước 4, `diff` **rỗng** |
| 7 | Không hồi quy VN | `measure_strategy` trên `bars_daily` ra số cũ, `diff` rỗng |

---

## 5. Câu hỏi F — chặn phần nào, không chặn phần nào

**F: spot hay hợp đồng vĩnh cửu? Có đòn bẩy không?**

| | Cần F? |
|---|---|
| C-a (đơn vị lô) | **Không** |
| C-b trên **spot**, không đòn bẩy | **Không** — chạy được ngay |
| C-b trên **perpetual** | **Có** — cần mô hình phí funding |
| Bất kỳ thứ gì có đòn bẩy | **Có** — cần khái niệm thanh lý mà `RiskManager` chưa có |

**Khuyến nghị: đo spot trước, bất kể F trả lời gì.** Lý do không phải né tránh
quyết định: nếu chiến lược không thắng được mua-và-giữ trên spot — nơi không có
funding, không có thanh lý, phí thấp nhất — thì thêm đòn bẩy chỉ khuếch đại một
kết quả âm. Spot là phép thử **rẻ nhất và khắt khe nhất** để loại sớm.

Nếu sau này đo perpetual mà chưa mô hình hoá funding, **phải ghi rõ trong báo
cáo là con số chưa trừ funding** — nó làm vị thế giữ lâu đẹp lên một cách giả
tạo.

---

## 6. Việc KHÔNG làm trong gói này

| Việc | Vì sao |
|---|---|
| Đổi `Signal.qty` từ `int` sang số thực | việc lớn hơn nhiều, không cần cho một phép đo |
| Thêm hàm đọc crypto vào `trading/storage/db.py` | phá tính trung lập thị trường của tầng lưu trữ (luật gói A) |
| Viết script đo thứ hai song song `measure_strategy.py` | hai công thức cho một khái niệm |
| Nạp thêm dữ liệu BingX | đã đủ; và chưa bao giờ được cố tình gây 429, không quá 1 req/s |
| Dùng API key BingX / chạm endpoint đặt lệnh | ngoài phạm vi, không có ngoại lệ |
| Cài plugin skill BingX của bên thứ ba | chủ dự án đã quyết: không |
| Bật `real_trading_enabled` | không đổi |
| Kết luận "crypto tốt hơn" từ phép đo trong mẫu | trong mẫu không kết luận được gì |

**Nhắc lại điều không đổi:** gói C là một **phép đo**, không phải một bước tiến
tới giao dịch thật. Nếu phép đo nói "không có lợi thế", đó cũng là kết quả
thành công — và đó là kết quả đã xảy ra ở cả ba chiến lược cổ phiếu.

---

## 7. Thứ tự

```
Tối nay sau 14:45   B1 + B2 + C3 + C-a  → một commit → MỘT lần dựng lại
Cuối tuần           kiểm đợt trên, rồi C-b (chỉ scripts/ — đo bao nhiêu lần cũng được)
Chờ chủ dự án       F: spot hay perpetual, đòn bẩy — KHÔNG chặn phần spot
```
