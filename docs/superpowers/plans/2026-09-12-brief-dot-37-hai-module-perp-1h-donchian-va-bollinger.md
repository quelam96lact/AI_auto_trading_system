# Brief đợt 37 — Hai module perpetual 1H: Donchian breakout và Bollinger mean reversion

Ngày giao: 12/09/2026.
Base: `6ee3d54` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.
Nguồn yêu cầu: `Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md` (chủ dự án cung cấp).

**Không xung đột với việc VN đang treo.** Brief 36 Task 3 (đo lại tiêu chí B/C phiên thứ Hai
14/09) đụng `trading/collector/*` và scripts giám sát. Brief này không đụng file nào trong số
đó. Hai việc chạy song song được.

---

## 0. Đọc phần này trước. Nó quyết định bạn được làm gì.

### 0.1. Tài liệu nói về Binance. Dữ liệu ta có là BingX.

Tài liệu mô tả bốn module dựa trên dữ liệu **Binance**: cờ `m` của aggregate trades, stream
`forceOrder`, funding đã settle, open interest. Chính tài liệu (§2.2) nói: *"Quy ước phải được
kiểm tra lại nếu đổi venue hoặc nguồn dữ liệu."*

Repo này **chỉ có** bảng `bars_crypto` nạp từ BingX. Tôi đã kiểm:

```
 interval | syms |   n    |           tu           |          den
----------+------+--------+------------------------+------------------------
 1d       |   20 |  27136 | 2021-05-14 00:00:00+00 | 2026-09-08 00:00:00+00
 1h       |   20 | 385651 | 2024-04-27 10:00:00+00 | 2026-09-08 15:00:00+00
```

`BTC-USDT` khung `1h`: **20.742 nến**, 2024-04-27 → 2026-09-08.

Và toàn bộ danh sách bảng trong DB `trading` **không có** bảng funding, open interest,
liquidation hay aggregate trades. Không có. Không phải "chưa nạp" — chưa từng tồn tại schema.

Cột duy nhất ngoài OHLCV là `quote_volume` và `trades` (số lệnh khớp trong nến). **`trades` là
số đếm, không có dấu** — không suy ra được delta mua/bán. Không được dùng nó làm proxy cho
Order Flow.

### 0.2. Hệ quả: chỉ hai trong bốn module chạy được bây giờ

| Module | Dữ liệu tài liệu đòi | Ta có? | Quyết định đợt 37 |
|---|---|---|---|
| **A. Donchian + ATR expansion** | OHLCV + delta xác nhận | OHLCV ✅, delta ❌ | **LÀM** — bản price-only, tắt điều kiện delta |
| **B. Bollinger mean reversion** | OHLCV + ADX + OFI | OHLCV ✅, OFI ❌ | **LÀM** — bản price-only, tắt điều kiện OFI |
| **C. Funding–OI–Liquidation** | funding + OI + liquidation | ❌ ❌ ❌ | **KHÔNG LÀM.** Không có một trong ba điều kiện chính |
| **D. VWAP + Volume Profile + OF** | OHLCV dưới 1H + delta | ❌ (chỉ có 1h và 1d) | **KHÔNG LÀM.** Volume Profile dựng từ 24 nến 1H là vô nghĩa; tài liệu §7.1 đòi 48 rows |

Tài liệu §9.4 gọi bản bỏ Order Flow là **`price-only` ablation** và liệt kê nó như một biến thể
hợp lệ phải chạy. Ta làm đúng thứ đó. **Không** được gọi kết quả là "module A đầy đủ" hay
"module B đầy đủ" trong bất kỳ dòng báo cáo nào — mọi chỗ phải ghi `price-only`.

Và tài liệu §12 chốt thứ tự triển khai: *"chuẩn hóa dữ liệu và execution engine; chạy từng
module standalone; chạy các ablation; sau đó mới xây bộ chọn regime."* Đợt 37 nằm đúng ở hai
bước đầu. **Không xây bộ chọn regime (§8). Không gộp module. Không cộng điểm.**

### 0.3. Vì sao không đi lấy dữ liệu Binance ngay trong đợt này

Vì đó là một đợt khác, và nó lớn: đăng ký nguồn, schema mới cho bốn loại dữ liệu, phân trang
lịch sử hai năm rưỡi, cờ chất lượng từng bar, và — theo chính tài liệu §6.2 — `forceOrder` của
Binance *"có thể tối đa một liquidation order mỗi symbol trong mỗi 1000 ms"*, tức nó **không
phải** tổng liquidation thị trường, nên module C có dữ liệu rồi vẫn còn một câu hỏi chưa xong.

Trộn hai việc đó vào đây sẽ cho ra một đợt không ai kiểm chứng nổi. Nếu A và B price-only
không cho thấy gì, ta tiết kiệm được cả đợt dữ liệu Binance.

### 0.4. Con số bạn phải thắng

Đây là mốc đã đo, đã tái lập độc lập, lưu ở
`docs/superpowers/research/2026-09-10-dot-26-do-lai-benchmark-crypto-sau-khi-sua.md`:

> Cùng giai đoạn 2024-04-27 → 2026-09-08, vốn 500 USDT: **mua-và-giữ BTC cho +122,42 USDT
> (+24,5%)**, trong khi cả bốn chiến lược hiện có trong repo đều **lỗ** từ −15,32 đến
> −21,10 USDT.

Không có chiến lược nào trong repo này từng có lợi thế đo được. Đó là bối cảnh. Đừng viết báo
cáo như thể lần này chắc chắn khác.

### 0.5. Quy tắc dành riêng cho bạn

Brief này viết chi tiết hơn mức bình thường: mọi công thức đều ghi rõ, mọi ngưỡng đều ghi số,
tên file và tên hàm đều chỉ định sẵn. Lý do: bạn chạy nhanh và rẻ, nên tôi trả tiền bằng độ
chi tiết thay vì bằng vòng hỏi lại.

Đổi lại, hai điều **tuyệt đối**:

1. **Không bịa.** Nếu brief thiếu, sai, hoặc bạn không chạy được một bước — ghi thẳng
   **"CHƯA LÀM"** kèm lý do, hoặc hỏi lại. Đợt 29 một agent đã thay bảng tiêu chí của tôi bằng
   tiêu chí tự nghĩ ra (nến 1 phút, phiên 09:15–14:45, ATC — không thứ nào tồn tại trong hệ
   thống này) và bịa output của một lệnh. Việc đó bị phát hiện trong mười phút vì tôi chạy lại
   mọi thứ. Tôi sẽ chạy lại mọi thứ lần này nữa.
2. **Mọi output dán vào báo cáo phải copy từ terminal.** Không gõ lại, không "khoảng chừng",
   không làm tròn. `git diff` dán từ lệnh `git diff` thật.

---

## 1. Ràng buộc phạm vi

### 1.1. File được sửa — chỉ năm file này

| File | Trạng thái | Được làm gì |
|---|---|---|
| `trading/indicators.py` | có sẵn | **CHỈ THÊM** ba lớp mới ở cuối file. Không sửa một dòng nào của `AtrCalculator`, `EmaCalculator`, `MacdCalculator`, `_CloseOnlyBar` |
| `trading/perp_backtest.py` | **mới** | engine mô phỏng |
| `scripts/measure_perp_modules.py` | **mới** | CLI đo lường + báo cáo |
| `tests/test_indicators_perp.py` | **mới** | test ba lớp chỉ báo |
| `tests/test_perp_backtest.py` | **mới** | test engine |

### 1.2. Không được đụng

`trading/pattern_backtest.py`, `trading/derivative_backtest.py`, `trading/backtest.py`,
`trading/paper_broker.py`, `trading/risk.py`, `trading/strategies/*`,
`trading/engine/logic.py`, `trading/collector/*`, `trading/crypto_fees.py`,
`scripts/measure_crypto_strategies.py`, `scripts/heartbeat_check.py`, `config/config.yaml`,
`.env`, `docker-compose.yml`.

Nếu bạn thấy một lỗi trong các file đó: **báo cáo, không sửa**.

### 1.3. Ràng buộc vận hành

- **Không gọi mạng.** Dữ liệu đã có trong DB. Không gọi BingX, không gọi Binance, không gọi SSI.
- **Chỉ đọc DB.** Không `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `DROP`, không tạo bảng.
- Không đụng NATS: không `delete`, `purge`, `add`, `update` stream hay consumer nào.
- `real_trading_enabled` giữ `false`. Không in secret.
- Không xoá file nào. **Không commit, không push.** Claude audit rồi mới commit.
- Không dựng lại container.
- Mọi truy vấn có `ts` mở đầu bằng `SET TimeZone='Asia/Ho_Chi_Minh';` — *nhưng* ở đợt này
  **mọi mốc thời gian crypto là UTC**; xem §2.1.

### 1.4. GitNexus

Chạy `npx gitnexus analyze` trước và sau. Chạy `gitnexus_impact` cho `AtrCalculator` và
`EmaCalculator` trước khi thêm vào `indicators.py` — đây là file dùng chung với
`pattern_backtest` và các chiến lược VN, blast radius thật. MCP `gitnexus` gần đây hay timeout:
**không kết nối được thì ghi rõ trong báo cáo**, đừng lặng lẽ bỏ qua.

---

## 2. Quy ước bắt buộc — sai một điều là hỏng cả phép đo

### 2.1. Múi giờ

Bảng `bars_crypto` lưu `TIMESTAMPTZ`, giá trị gốc là UTC. **Toàn bộ đợt này làm việc bằng UTC.**
Mọi mốc thời gian in ra báo cáo phải kèm hậu tố `UTC`.

Lý do phải nhắc: đợt 28 và 29, agent in giờ UTC mà không nói là UTC, làm tôi đọc nhầm 06:30
thành 13:30. Đây là lần thứ ba bài học này xuất hiện trong repo.

### 2.2. Chống nhìn trước (look-ahead) — năm điều

Tài liệu §2.1 đặt ra, tôi viết lại thành luật kiểm chứng được:

1. **Tín hiệu tính tại giá đóng của bar `t`. Lệnh sớm nhất đặt từ bar `t+1`.** Không có ngoại lệ.
2. **Donchian `Upper20_t` là `max(high)` của 20 bar `t-20 .. t-1`** — **KHÔNG gồm bar `t`.**
   `Lower20_t` là `min(low)` của cùng cửa sổ đó. Nếu gộp bar `t` vào biên thì điều kiện
   `close_t > Upper20_t` gần như không bao giờ đúng, và khi đúng thì đã nhìn trước.
3. **Trung vị ATR14 của 50 bar trước** là `median` của `ATR14` tại các bar `t-50 .. t-1` —
   không gồm `t`.
4. **Phân vị BandWidth** (module B) tính trên 240 bar `t-240 .. t-1` — không gồm `t`.
5. **Không dùng high/low/volume của bar chưa đóng.**

### 2.3. Quy ước khớp lệnh — bốn điều

1. **Nến chạm cả SL lẫn TP trong cùng một bar → SL xảy ra trước.** Giả định bi quan, đúng
   với quy ước sẵn có của repo (`run_pattern_backtest(sl_first=True)`).
2. **Lệnh stop bị gap:** nếu bar mở cửa đã vượt qua trigger theo hướng bất lợi, khớp tại
   **giá mở cửa**, không phải tại trigger. Long: `fill = max(open, trigger)`. Short:
   `fill = min(open, trigger)`.
3. **SL bị gap:** cùng quy ước. Long chạm SL: `fill = min(open, stop)`. Short: `fill = max(open, stop)`.
4. **Không mở lại vị thế trong cùng bar vừa đóng.**

### 2.4. Chi phí

- `fee_rate = trading.crypto_fees.BINGX_PERP_TAKER` (= `0.0005`) cho **cả hai chiều**.
  Lý do đã ghi sẵn trong docstring của `crypto_fees.py`: vào bằng stop-entry và thoát bằng SL
  đều là lệnh dừng — khi kích hoạt sẽ ăn vào sổ lệnh, tức taker. Nhánh thoát bằng TP *có thể*
  là maker, nên lấy taker là hơi thận trọng. **Không tự chẻ thành hai mức.**
- **Không import số `0.0005` bằng tay.** Import hằng số. Nếu bạn gõ lại con số, đó là vi phạm
  "một công thức, một chỗ".
- `slippage_bps` là tham số **bắt buộc khai báo tường minh** (theo tiền lệ
  `run_pattern_backtest`). Baseline `0.0`; §6 yêu cầu một lượt đo với `2.0` bps.
- **Funding KHÔNG được mô hình hoá.** Không có dữ liệu. Đây là hạn chế đã biết, phải in
  thành cảnh báo trong mọi báo cáo (§6.3), và phải đo mức phơi nhiễm (§6.2, chỉ số `funding_spans`).

### 2.5. Vốn và khối lượng

Theo tài liệu §2.4:

```text
risk_budget = equity * risk_fraction
cost_per_unit = 2 * entry_price * fee_rate        # phí vào + phí ra, mỗi đơn vị
qty = risk_budget / (abs(entry - stop) + cost_per_unit)
```

- `equity` = tiền mặt hiện tại (một vị thế tại một thời điểm, PnL thực hiện khi đóng).
- `risk_fraction = 0.005` (0,5% — biên trên của khoảng 0,25–0,50% tài liệu nêu).
- `capital` khởi đầu = **500 USDT** — cùng mức với phép đo đợt 22/26, để so được với
  mua-và-giữ +122,42 USDT.
- `qty` là số thực (BTC chia nhỏ được). Không làm tròn về số nguyên.

**Trần đòn bẩy `max_leverage = 10.0`:** nếu `qty * entry > max_leverage * equity` thì cắt
`qty = max_leverage * equity / entry` và **đếm lệnh đó vào `clipped_trades`**. Tài liệu §2.4
đòi "áp giới hạn notional, leverage, margin ratio".

**Thanh lý KHÔNG được mô hình hoá.** Thay vào đó phải đếm: số lệnh mà biến động bất lợi trong
bar vượt `entry / max_leverage` tính từ giá vào (Long: `low < entry * (1 - 1/max_leverage)`),
tức lệnh *đáng lẽ* đã bị thanh lý. Chỉ số `would_liquidate` trong §6.2. Nếu con số này lớn
hơn 0, ghi rõ rằng kết quả tương ứng là **lạc quan quá mức**.

### 2.6. Tách mẫu trong/ngoài — niêm phong OOS

| Tập | Khoảng | Số nến BTC-USDT 1h (đã đếm) |
|---|---|---|
| **In-sample (IS)** | 2024-04-27 → 2025-12-31 UTC | **14.726** |
| **Out-of-sample (OOS)** | 2026-01-01 → 2026-09-08 UTC | **6.016** |

**Luật, theo tài liệu §9.3 và §10:**

- Phát triển, sửa lỗi, xem kết quả: **chỉ trên IS.**
- OOS chạy **đúng một lần**, ở bước cuối cùng, sau khi mọi tham số đã khoá.
- **Sau khi xem OOS, không được chỉnh bất kỳ tham số nào rồi chạy lại.** Nếu bạn lỡ chỉnh,
  phải ghi thẳng điều đó vào báo cáo — kết quả khi ấy không còn là OOS nữa.
- Mọi tham số trong brief này là **giả thuyết khởi đầu do tài liệu đặt ra** (§10). Không quét
  lưới tham số. Không tối ưu. Không thêm bộ lọc vì nó làm đẹp kết quả.

---

## Task 1 — Ba lớp chỉ báo mới trong `trading/indicators.py`

**Chỉ thêm vào cuối file.** Theo đúng style ba lớp sẵn có: trạng thái theo từng symbol, có
`update(bar)` trả giá trị hiện tại hoặc `None` khi chưa đủ warm-up, và `last(symbol)`.

### 1.1. `DonchianCalculator(period: int = 20)`

Giữ `deque(maxlen=period)` của `high` và `low` **của các bar đã update trước đó**.

```
update(bar) -> tuple[float, float] | None
    # Trả (upper, lower) tính TỪ CÁC BAR TRƯỚC bar này — chưa gồm bar hiện tại.
    # Trả None khi chưa đủ `period` bar trước.
    # Sau khi tính xong mới đẩy high/low của bar hiện tại vào deque.
```

Thứ tự "tính trước, đẩy sau" chính là điều bảo đảm luật §2.2 điều 2. Viết một dòng comment nói
rõ điều đó ngay tại chỗ.

### 1.2. `BollingerCalculator(period: int = 20, num_std: float = 2.0)`

```
update(bar) -> tuple[float, float, float] | None   # (middle, upper, lower)
```

- `middle` = SMA của `period` giá đóng **gồm cả bar hiện tại**.
- Độ lệch chuẩn là **độ lệch chuẩn MẪU** (chia `n-1`, tức `statistics.stdev`), theo đúng chữ
  của tài liệu §5.1: *"SD_t = độ lệch chuẩn mẫu 20"*. Không dùng `pstdev`.
- Trả `None` khi chưa đủ `period` giá đóng.
- Thêm `percent_b(close, upper, lower)` là hàm module-level thuần:
  `(close - lower) / (upper - lower)`, trả `None` khi `upper == lower`.

### 1.3. `AdxCalculator(period: int = 14)` — lớp khó nhất, đọc kỹ

Dùng **làm trơn Wilder** (đây là định nghĩa chuẩn của ADX, khác với trung bình đơn giản mà
`AtrCalculator` dùng — ghi rõ sự khác biệt đó trong docstring, đừng để người sau tưởng nhầm).

```
+DM = high_t - high_{t-1}   nếu > 0 và > (low_{t-1} - low_t),  ngược lại 0
-DM = low_{t-1} - low_t     nếu > 0 và > (high_t - high_{t-1}),  ngược lại 0
TR  = max(high-low, |high - close_{t-1}|, |low - close_{t-1}|)

Làm trơn Wilder, seed = tổng `period` giá trị đầu:
    S_t = S_{t-1} - S_{t-1}/period + X_t

+DI = 100 * S(+DM) / S(TR)
-DI = 100 * S(-DM) / S(TR)
DX  = 100 * |(+DI) - (-DI)| / ((+DI) + (-DI))
ADX = làm trơn Wilder của DX, seed = trung bình `period` giá trị DX đầu tiên
```

- Cần khoảng `2 * period` bar mới có ADX đầu tiên. Trả `None` cho tới khi đó.
- `S(TR) == 0` hoặc `(+DI) + (-DI) == 0` → trả `None` cho bar đó (không chia cho 0, không trả 0
  giả vờ là giá trị thật).

### 1.4. Kiểm chứng Task 1 — `tests/test_indicators_perp.py`

Viết **đúng** các test sau, không thêm không bớt:

1. `DonchianCalculator` trên chuỗi high tăng đều `[10, 11, 12, ...]` với `period=3`: kiểm rằng
   giá trị trả về tại bar thứ 4 là biên của **ba bar đầu**, không gồm bar thứ 4. Đây là bài
   test chống nhìn trước — nếu nó pass ngay cả khi bạn đẩy bar hiện tại vào deque trước, thì
   test sai, viết lại.
2. `DonchianCalculator` trả `None` khi chưa đủ `period` bar.
3. `BollingerCalculator` trên chuỗi hằng số (mọi close = 100): `middle == 100`,
   `upper == lower == 100`, và `percent_b` trả `None`.
4. `BollingerCalculator` trên một chuỗi 20 giá đóng cụ thể bạn tự chọn: đối chiếu `middle` với
   `statistics.mean` và độ lệch chuẩn với `statistics.stdev` tính ngay trong test. Đây là cách
   chứng minh bạn dùng stdev mẫu chứ không phải tổng thể.
5. `AdxCalculator` trên chuỗi tăng đơn điệu mạnh 60 bar: ADX cuối cùng `> 40`.
6. `AdxCalculator` trên chuỗi dao động phẳng 60 bar (high/low quanh một mức, không có xu
   hướng): ADX cuối cùng `< 20`.
7. `AdxCalculator` trả `None` trước khi đủ warm-up.

**Tiêu chí đạt Task 1:** bảy test trên pass, ruff sạch, và **toàn bộ suite hiện có vẫn pass
không sửa một dòng test cũ nào** (thay đổi là thuần bổ sung).

---

## Task 2 — Engine `trading/perp_backtest.py`

Tự chứa. Không import `pattern_backtest`, không import `derivative_backtest`, không import
`backtest.run_backtest`. Được import `trading.models.Bar`, `trading.indicators.*`,
`trading.crypto_fees.BINGX_PERP_TAKER`, `trading.data_quality.is_dirty_bar`,
`trading.metrics.*`.

### 2.1. Kiểu dữ liệu

```python
@dataclass
class PerpTrade:
    symbol: str
    side: Literal["LONG", "SHORT"]
    signal_ts: datetime      # close của bar t (UTC)
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    qty: float
    r_value: float           # abs(entry - stop), mỗi đơn vị
    gross_pnl: float
    fees: float
    net_pnl: float           # gross - fees
    exit_reason: Literal["SL", "TP", "TIME"]
    bars_held: int
    clipped: bool            # đã bị cắt bởi trần đòn bẩy
    would_liquidate: bool    # biến động bất lợi vượt entry/max_leverage
    funding_spans: int       # số mốc 00/08/16 UTC mà lệnh sống qua

@dataclass
class PerpReport:
    module: str              # "donchian_breakout" | "bollinger_mr"
    symbol: str
    trades: list[PerpTrade]
    starting_capital: float
    ending_capital: float
    equity_curve: list[tuple[datetime, float]]
    signals_generated: int   # số tín hiệu phát ra
    orders_expired: int      # lệnh stop hết hạn không khớp
    orders_cancelled: int    # huỷ vì giá chạy quá xa
```

### 2.2. Hàm chính

```python
def run_perp_backtest(
    bars: list[Bar],
    module: Literal["donchian_breakout", "bollinger_mr"],
    *,
    capital: float = 500.0,
    fee_rate: float,            # BẮT BUỘC truyền tường minh
    slippage_bps: float,        # BẮT BUỘC truyền tường minh
    risk_fraction: float = 0.005,
    max_leverage: float = 10.0,
    use_ema_filter: bool = False,   # chỉ module A
) -> PerpReport:
```

Nếu `fee_rate` hoặc `slippage_bps` không được truyền → `TypeError` tự nhiên của Python (tham số
keyword-only không mặc định). Đó là chủ ý: theo tiền lệ `run_pattern_backtest`, cấm để mặc định
0 rồi quên.

Bỏ bar rác bằng `is_dirty_bar` trước khi tính. Nếu còn dưới 260 bar sạch (đủ warm-up cho cửa sổ
240 của module B), trả report rỗng.

Trượt giá: `slippage_bps` áp **bất lợi** lên mọi giá khớp — vào long thì giá cao hơn
`price * (1 + bps/10000)`, thoát long thì thấp hơn; short ngược lại.

Phí mỗi chiều: `qty * fill_price * fee_rate`. Tổng `fees` của một lệnh = phí vào + phí ra.

**Một vị thế tại một thời điểm.** Khi đang có vị thế hoặc đang có lệnh chờ, bỏ qua tín hiệu mới.

### 2.3. Module A — `donchian_breakout` (price-only)

**Điều kiện tín hiệu, tại close bar `t`:**

| Thành phần | Long | Short |
|---|---|---|
| Kênh | `close_t > Upper20_t` | `close_t < Lower20_t` |
| Mở rộng biến động | `ATR14_t / median(ATR14, 50 bar trước) >= 1.20` **và** `ATR14_t > ATR14_{t-1}` | giống Long |
| Biên độ | `high_t - low_t >= 1.0 * ATR14_t` | giống Long |
| CLV | `(close_t - low_t)/(high_t - low_t) >= 0.65` | `<= 0.35` |
| Lọc EMA (tuỳ chọn) | `use_ema_filter` bật: `EMA50 > EMA200` | `EMA50 < EMA200` |

- `high_t == low_t` → CLV không hợp lệ → **bỏ tín hiệu**.
- Điều kiện Order Flow của tài liệu (delta, taker-buy ratio): **KHÔNG có dữ liệu, bỏ.** Viết
  một comment tại chỗ nói rõ điều kiện nào bị bỏ và vì sao.

**Bộ lọc loại bỏ (tài liệu §4.4):**

- Bỏ nếu `ATR14_t / median(ATR14, 50) >= 2.50` (nghi shock / liquidation cascade).
- Bỏ nếu `high_t - low_t > 2.0 * ATR14_t`.

**Trigger (stop-entry):**

```
trigger_long  = Upper20_t + 0.05 * ATR14_t
trigger_short = Lower20_t - 0.05 * ATR14_t
```

Lệnh hiệu lực **hai bar**: `t+1` và `t+2`. Với mỗi bar trong cửa sổ đó, theo thứ tự:

1. Nếu Long và `bar.open > trigger + 0.50 * ATR14_t` → **huỷ** (`orders_cancelled += 1`,
   không đuổi giá). Short đối xứng với `bar.open < trigger - 0.50*ATR14_t`.
2. Nếu Long và `bar.high >= trigger` → khớp tại `max(bar.open, trigger)`.
   Short: `bar.low <= trigger` → khớp tại `min(bar.open, trigger)`.
3. Hết hai bar không khớp → `orders_expired += 1`.

**Stop và mục tiêu:**

```
breakout_low  = low của bar tín hiệu t          (Long)
breakout_high = high của bar tín hiệu t         (Short)

stop_long  = min(breakout_low  - 0.25*ATR14_t,  entry - 1.5*ATR14_t)
stop_short = max(breakout_high + 0.25*ATR14_t,  entry + 1.5*ATR14_t)

R = abs(entry - stop)
target = entry + 2R   (Long)   |   entry - 2R   (Short)
```

**Đây là cố ý lệch khỏi tài liệu, và tôi chịu trách nhiệm.** Tài liệu §4.3 đặt baseline là
chốt 50% tại +1,5R rồi chandelier trail 2,5×ATR, và gọi `2R` cố định là *"một biến thể so sánh
cố định"*. Tôi lấy biến thể `2R` làm bản đầu tiên vì nó trả lời đúng câu hỏi duy nhất đang cần
trả lời — *module này có lợi thế đo được không* — với ít hơn hẳn code và ít hơn hẳn chỗ để sai.
Chốt từng phần + trailing là đợt 38, và chỉ đáng làm nếu đợt 37 cho tín hiệu đáng theo.
**Không tự ý thêm chốt từng phần hay trailing vào đợt này.**

**Time stop:** chưa chạm SL lẫn TP sau **24 bar** kể từ bar vào lệnh → đóng tại close bar thứ 24,
`exit_reason = "TIME"`.

### 2.4. Module B — `bollinger_mr` (price-only)

**Điều kiện chế độ thị trường — cả bốn phải đúng tại bar `t`, nếu không thì không có tín hiệu:**

1. `ADX14_t < 20`
2. `abs(EMA50_t - EMA50_{t-3}) < 0.50 * ATR14_t`
3. `abs(EMA50_t - EMA200_t) <= 0.75 * ATR14_t`
4. `BandWidth_t` nằm trong phân vị **20–80** của `BandWidth` trên **240 bar trước** (không gồm `t`),
   với `BandWidth = (upper - lower) / middle`.

**Điều kiện tín hiệu:**

| Thành phần | Long | Short |
|---|---|---|
| Từ chối biên | `low_t <= lower_t` **và** `close_t > lower_t` | `high_t >= upper_t` **và** `close_t < upper_t` |
| Màu nến | `close_t > open_t` | `close_t < open_t` |
| Vị trí | `%B_t <= 0.25` | `%B_t >= 0.75` |

- Nến đóng **hẳn ngoài** band → bỏ (có thể là band walk / continuation). Điều kiện
  `close_t > lower_t` ở trên đã bao hàm việc này; đừng viết thêm nhánh thứ hai.
- Điều kiện OFI của tài liệu: **KHÔNG có dữ liệu, bỏ.** Comment tại chỗ.

**Vào lệnh — `next-open`, không phải stop-entry:**

- Khớp tại `open` của bar `t+1`.
- **Bỏ lệnh** nếu `open_{t+1}` lệch **bất lợi** quá `0.25 * ATR14_t` so với `close_t`
  (Long: `open_{t+1} > close_t + 0.25*ATR14_t`; Short đối xứng). Đếm vào `orders_cancelled`.

**Stop, mục tiêu, và ba phép loại bỏ:**

```
stop_long  = low_t  - 0.25 * ATR14_t
stop_short = high_t + 0.25 * ATR14_t
R = abs(entry - stop)

Bỏ lệnh nếu R < 0.60 * ATR14_t  hoặc  R > 2.00 * ATR14_t
Bỏ lệnh nếu abs(middle_t - entry) < 0.80 * R
target_long  = min(middle_t, entry + 1.25R)
target_short = max(middle_t, entry - 1.25R)
```

**Time stop: 12 bar.**

### 2.5. Kiểm chứng Task 2 — `tests/test_perp_backtest.py`

Mỗi test dựng chuỗi bar thủ công (không đọc DB, không gọi mạng). Viết **đúng** các test sau:

**Nhóm quy ước khớp lệnh (quan trọng nhất — đây là chỗ dễ sai âm thầm):**

1. **SL trước TP:** dựng một bar sau khi vào lệnh chạm cả stop lẫn target → `exit_reason == "SL"`.
2. **Gap qua trigger:** bar `t+1` mở cửa **trên** trigger long → `entry_price == bar.open`,
   không phải `trigger`.
3. **Gap qua stop:** bar mở cửa **dưới** stop long → `exit_price == bar.open`, không phải `stop`.
4. **Huỷ vì đuổi giá:** bar `t+1` mở cửa trên `trigger + 0.50*ATR` → không có lệnh nào,
   `orders_cancelled == 1`.
5. **Hết hạn:** giá không chạm trigger trong hai bar → `orders_expired == 1`, không có lệnh.

**Nhóm phí và khối lượng:**

6. **Phí hai chiều:** một lệnh khớp và đóng → `trade.fees` bằng đúng
   `qty*entry*fee_rate + qty*exit*fee_rate`, tính lại ngay trong test.
7. **Sizing theo rủi ro:** với `capital=500`, `risk_fraction=0.005`, entry/stop cho trước →
   `qty` khớp công thức §2.5 tính lại trong test.
8. **Trần đòn bẩy cắt khối lượng:** stop rất sát entry làm `qty` vọt lên → `qty*entry` bằng
   đúng `max_leverage * equity` và `trade.clipped is True`.

**Nhóm chống nhìn trước:**

9. **Không vào lệnh tại bar tín hiệu:** `entry_ts > signal_ts` với mọi lệnh trong mọi test.
   Viết thành một test quét toàn bộ `report.trades`.

**Nhóm time stop:**

10. Module A: giá đi ngang 24 bar sau khi vào → `exit_reason == "TIME"`, `bars_held == 24`.
11. Module B: tương tự với **12** bar.

**Nhóm bộ lọc (mỗi bộ lọc một test, chứng minh nó thật sự chặn):**

12. Module A bỏ tín hiệu khi `ATR ratio >= 2.50`.
13. Module A bỏ tín hiệu khi `high - low > 2.0 * ATR14`.
14. Module A bỏ tín hiệu khi `high == low` (CLV không hợp lệ).
15. Module B không phát tín hiệu khi `ADX >= 20`.
16. Module B bỏ lệnh khi `R > 2.00 * ATR14`.
17. Module B bỏ lệnh khi khoảng cách tới đường giữa `< 0.80R`.

**Cách viết test bộ lọc cho đúng:** mỗi test phải có **hai khẳng định** — một chuỗi bar thoả
mọi điều kiện thì **có** lệnh, và cùng chuỗi đó chỉ đổi một yếu tố để vi phạm bộ lọc thì
**không có** lệnh. Test chỉ khẳng định "không có lệnh" là test vô giá trị: nó pass cả khi
engine hỏng hoàn toàn và chẳng bao giờ vào lệnh.

**Tiêu chí đạt Task 2:** 17 test pass, ruff sạch, suite đầy đủ pass, **và cổng cứng VN tái lập
đúng từng chữ số** (§7).

---

## Task 3 — Script đo lường `scripts/measure_perp_modules.py`

**Chỉ bắt đầu Task 3 sau khi Task 2 đã đạt toàn bộ tiêu chí.**

### 3.1. Đọc dữ liệu

Dùng lại `read_crypto_bars` sẵn có:

```python
from scripts.measure_crypto_strategies import read_crypto_bars
```

Nó đã nhận `symbols`, `interval`, `from_date`, `to_date`. **Không viết lại câu SELECT.** DSN lấy
qua `resolve_dsn` như các script khác trong `scripts/`.

### 3.2. Tham số dòng lệnh

```
--symbol       mặc định BTC-USDT
--module       donchian_breakout | bollinger_mr | all   (mặc định all)
--split        is | oos | both                          (mặc định is)
--capital      mặc định 500.0
--risk-fraction mặc định 0.005
--max-leverage mặc định 10.0
--slippage-bps mặc định 0.0
--ema-filter   cờ, chỉ ảnh hưởng module A
--dsn
```

Mốc chia cố định trong code, không cho truyền vào (để không ai vô tình xê dịch ranh giới):
IS `2024-04-27` → `2025-12-31`, OOS `2026-01-01` → `2026-09-08`, tất cả UTC.

**`--split oos` phải in một dòng cảnh báo đỏ ở đầu output:** *"OOS chỉ được chạy MỘT LẦN sau khi
tham số đã khoá. Nếu bạn đang chỉnh tham số, đừng chạy lệnh này."*

### 3.3. Mua-và-giữ đối chứng

Script phải tự tính mua-và-giữ trên **cùng khoảng, cùng vốn, cùng `fee_rate`**: mua tại `open`
của bar đầu, bán tại `close` của bar cuối, trừ phí taker hai chiều, không đòn bẩy. Đây là cột
so sánh bắt buộc — một chiến lược lãi 3% khi mua-và-giữ lãi 24% là một chiến lược thất bại.

### 3.4. Bảng báo cáo

Một bảng cho mỗi (module × split), với **đúng** các cột sau:

| Cột | Ý nghĩa |
|---|---|
| `signals` | số tín hiệu phát ra |
| `orders_expired` / `orders_cancelled` | lệnh không thành |
| `trades` | số lệnh đã đóng |
| `win_rate` | % lệnh `net_pnl > 0` |
| `net_pnl` | USDT, **sau phí** |
| `net_pnl_pct` | % trên vốn |
| `bh_pnl` | mua-và-giữ cùng kỳ, USDT |
| `profit_factor` | dùng `trading.metrics.profit_factor` |
| `expectancy` | dùng `trading.metrics.expectancy` |
| `max_dd` | dùng `trading.metrics.max_drawdown` trên equity curve |
| `sharpe` | dùng `trading.metrics.sharpe`, **`periods_per_year=8760`** (khung 1H) |
| `avg_bars_held` | trung bình `bars_held` |
| `total_fees` | tổng phí đã trả, USDT |
| `clipped_trades` | số lệnh bị trần đòn bẩy cắt |
| `would_liquidate` | số lệnh đáng lẽ đã bị thanh lý (§2.5) |
| `funding_spans_total` | tổng số mốc funding các lệnh sống qua |

Thêm một bảng phân rã **Long / Short riêng** cho mỗi module × split, với các cột
`trades`, `win_rate`, `net_pnl`, `profit_factor`.

### 3.5. Ba cảnh báo bắt buộc in mỗi lần chạy

Theo tiền lệ `print_crypto_report`:

1. `[PRICE-ONLY]` — điều kiện Order Flow / delta / OFI của tài liệu **bị bỏ vì không có dữ
   liệu**. Đây không phải bản đầy đủ của module.
2. `[CHƯA MÔ HÌNH HOÁ FUNDING]` — kèm `funding_spans_total` thật của lượt chạy đó.
3. `[CHƯA MÔ HÌNH HOÁ THANH LÝ]` — kèm `would_liquidate` thật của lượt chạy đó.

### 3.6. Kiểm chứng Task 3

1. `--module all --split is` chạy xong, in đủ hai bảng module + hai bảng Long/Short + ba cảnh báo.
2. Chạy hai lần liên tiếp cùng tham số → **output giống hệt** (không có ngẫu nhiên, không phụ
   thuộc giờ chạy). Dán bằng chứng: hash hoặc `diff` hai lần chạy.
3. Cột `bh_pnl` cho khoảng **toàn bộ** 2024-04-27 → 2026-09-08 với vốn 500 USDT phải ra
   **xấp xỉ +122,42 USDT**. Đây là mốc đã được đo và tái lập độc lập ở đợt 26. Nếu lệch quá
   ±5 USDT: **DỪNG LẠI, báo cáo, đừng chạy tiếp** — nghĩa là cách đọc dữ liệu hoặc cách tính
   phí của bạn khác với phần còn lại của repo, và mọi con số sau đó sẽ vô nghĩa.
   *(Lệch nhỏ là bình thường: đợt 26 dùng `_buy_and_hold` với `lot_size`; bạn mua tại `open`
   bar đầu. Lệch lớn thì không.)*

---

## Task 4 — Chạy đo và ghi kết quả

**Chỉ bắt đầu sau khi Task 3 đạt, và đây là bước CUỐI CÙNG.** Không sửa code sau khi bắt đầu
Task 4 — nếu buộc phải sửa, mọi phép đo trước đó vứt đi và chạy lại từ đầu.

### 4.1. Thứ tự chạy — không đảo

| # | Lượt | Mục đích |
|---|---|---|
| 1 | `--module all --split is --slippage-bps 0` | baseline IS |
| 2 | `--module donchian_breakout --split is --ema-filter` | ablation: bật lọc EMA (tài liệu §9.4) |
| 3 | `--module all --split is --slippage-bps 2.0` | độ nhạy chi phí |
| 4 | **`--module all --split oos --slippage-bps 0`** | **MỘT LẦN DUY NHẤT, cuối cùng** |

Sau lượt 4: **dừng**. Không chỉnh tham số. Không chạy lại.

### 4.2. Tiêu chí "đáng nghiên cứu tiếp" — chốt TRƯỚC khi xem kết quả

Tài liệu §10 đòi khoá tiêu chí trước. Đây là tiêu chí, và nó áp cho **OOS**:

Một module **đáng nghiên cứu tiếp** khi và chỉ khi cả ba đúng trên OOS:

1. `net_pnl > 0` sau phí, **và**
2. `trades >= 30`, **và**
3. `profit_factor > 1.0`.

Thiếu một điều → module đó là **kết quả âm**. Ghi nhận, không chỉnh tham số để cứu nó.

**Vượt mua-và-giữ là một mốc riêng và cao hơn**, phải báo cáo tách bạch: `net_pnl > bh_pnl`.
Một module đạt cả ba điều trên nhưng thua mua-và-giữ vẫn chỉ là "đáng nghiên cứu tiếp", không
phải "đáng triển khai".

### 4.3. File kết quả

Tạo `docs/superpowers/research/2026-09-12-dot-37-do-hai-module-perp-1h-price-only.md`.

**Tạo file MỚI. Không ghi đè file nào.** Đợt 26 một agent đã ghi đè file nghiên cứu lịch sử của
đợt 22 và tôi phải khôi phục bằng `git checkout`.

Nội dung:

1. Nguyên văn output của **cả bốn lượt chạy**, copy từ terminal, trong khối ```.
2. Bảng tổng hợp IS vs OOS cho từng module.
3. Kết luận theo tiêu chí §4.2, cho từng module, một dòng: **"đáng nghiên cứu tiếp"** hoặc
   **"kết quả âm"**, kèm ba con số quyết định.
4. So sánh với mua-và-giữ.
5. Mục **"Điều phép đo này KHÔNG trả lời"** — tối thiểu phải có: funding chưa tính, thanh lý
   chưa mô phỏng, Order Flow bị bỏ, chỉ một sàn BingX, chỉ một mã BTC-USDT, chỉ 2,37 năm dữ
   liệu, chưa có walk-forward.

---

## 5. Báo cáo cho Claude

Ngắn, đủ, đúng thứ tự. **Đừng dán toàn văn `git diff`** — dán `--stat` và con số.

1. `gitnexus_impact` cho `AtrCalculator` và `EmaCalculator` (hoặc ghi rõ MCP timeout).
2. `git diff --stat` và `git status --short`.
3. Task 1: kết quả 7 test. Task 2: kết quả 17 test. Task 3: kết quả 3 tiêu chí, **kèm con số
   `bh_pnl` thật** đối chiếu với +122,42.
4. Task 4: bảng tổng hợp IS/OOS và kết luận từng module theo §4.2.
5. Ba dòng: số test pass (**mốc hiện tại 663**), ruff, cổng cứng VN.
6. Đường dẫn file nghiên cứu mới tạo.

Task nào chưa làm ghi thẳng **"CHƯA LÀM"** kèm lý do. **Không commit, không push.**

---

## 6. Cổng cứng VN — phép kiểm không được phép trượt

`trading/indicators.py` là file dùng chung: `pattern_backtest.py` và các chiến lược VN đều import
nó. Thêm ba lớp vào đó là thay đổi thuần bổ sung, **nhưng phải chứng minh**:

```
uv run python scripts/measure_strategy.py --strategy octopus_pullback --exclude-file exclusions.txt
```

Phải ra **đúng bốn con số này**:

```
-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã
```

**Đây là một backtest, không phải suite test.** Đợt 34 một agent báo *"Cổng cứng VN: 15/15
passed"* — đó là một phép kiểm khác được thay vào chỗ cổng cứng. Phải dán đủ bốn con số. Lệch
một chữ số nghĩa là thay đổi của bạn không thuần bổ sung.

Chạy cổng cứng **hai lần**: một lần sau Task 1, một lần sau Task 2.

---

## 7. Điều KHÔNG thuộc phạm vi đợt này

- **Module C và D.** Thiếu dữ liệu, đã giải thích ở §0.2. Đừng thay bằng proxy tự nghĩ ra —
  tài liệu §12 nói rõ: *"Nếu dữ liệu không đủ để tái lập điều kiện, quyết định đúng là no-trade
  hoặc loại mẫu, không phải tự ý thay thế bằng một proxy không được công bố."*
- **Bộ chọn chế độ thị trường (§8 tài liệu).** Chỉ làm sau khi có kết quả standalone.
- **Chốt từng phần, chandelier trail, breakeven.** Đợt 38, nếu đợt 37 cho tín hiệu đáng theo.
- **Walk-forward.** Cần kết quả IS/OOS trước đã.
- **Nạp dữ liệu Binance** (funding, OI, liquidation, aggTrades). Một đợt riêng, lớn.
- **Giao dịch thật.** Không có gì trong đợt này chạm tới sàn. `real_trading_enabled` giữ `false`.
- **Quét lưới tham số.** Mọi ngưỡng trong brief là giả thuyết khởi đầu của tài liệu. Không tối ưu.

---

## 8. Ba câu hỏi lớn vẫn là quyết định của chủ dự án, không phải việc của agent

Nhắc lại để đừng ai tưởng đợt này trả lời chúng:

- **Q-1:** không chiến lược nào trong repo có lợi thế đo được. Đợt 37 có thể làm danh sách đó
  dài thêm hai dòng, hoặc có thể không. Nó không tự nó biến hệ thống thành đáng go-live.
- **Q-2:** tài khoản `0434221` (NAV 5.021.712) hay `0434226` (NAV 197.517.988).
- **Q-3:** cửa xác nhận lệnh thật 15 phút, với 9/9 lệnh đã hết hạn vì không ai kịp gõ `YES`.
