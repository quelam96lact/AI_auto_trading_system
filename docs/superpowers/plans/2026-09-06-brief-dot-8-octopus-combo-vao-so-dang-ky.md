# Brief đợt 8 — Đưa Octopus+Combo vào sổ đăng ký chiến lược (`STRATEGIES`)

**Người giao:** Claude (planner/auditor) · **Ngày:** 2026-09-06
**Quyết định của chủ dự án:** đưa chiến lược lai Octopus+Combo thành một chiến lược
trong danh sách chiến lược ở nhánh chính.

---

## 0. ĐIỀU PHẢI ĐỌC TRƯỚC KHI VIẾT DÒNG CODE ĐẦU TIÊN

### 0.1. Thứ được đăng ký KHÔNG phải thứ đã đo. Đây là chủ ý, không phải sơ suất.

Con số quảng cáo của hybrid (+2,13 tỷ VND ở `k_tp`=2,6; +1,48M USDT trên crypto)
đến từ `trading/pattern_backtest.py` — một bộ mô phỏng **riêng**, có:

- lệnh chờ **BUY STOP** tại `High + 0,1×ATR`, tự huỷ nếu bar kế không phá đỉnh;
- **SL cố định** tại `Low − 0,1×ATR`;
- **TP cố định** tại `entry + k_tp×ATR`.

`STRATEGIES` (`trading/backtest.py:290-294`) thì nạp các đối tượng thoả
`Strategy` Protocol (`trading/strategy.py:41-54`) và chạy qua `run_backtest`, nơi:

- lệnh vào là **market**, `PaperBroker` khớp tại `open` của bar sau tín hiệu;
- không có khái niệm lệnh chờ, không có SL/TP cố định;
- thoát lệnh bằng TP tự tính trong `on_bar` + `TrailingStopManager`.

**Ba cơ chế tạo ra biên lợi nhuận của hybrid không tồn tại trong `run_backtest`.**
Cho nên chiến lược được đăng ký ở đợt này là **phần tín hiệu** của hybrid chạy
trên mô hình khớp lệnh của repo — một chiến lược *khác* với thứ đã đo.

Việc mở rộng `run_backtest` để hỗ trợ lệnh chờ + TP cố định **ngoài phạm vi đợt
này** và đang bị chặn bởi ràng buộc thường trực (không sửa `run_backtest`,
`PaperBroker`, `derivative_backtest`).

### 0.2. Đăng ký vào `STRATEGIES` KHÔNG phải là cho phép chạy thật

`trading/backtest.py:286-289` đã ghi rõ: đây là *"SO DANG KY DE DO, khong phai
danh sach chien luoc duoc phep chay that"*. Chiến lược chạy thật do
`trading/engine/main.py::_default_strategy()` quyết định và đang bị ghim bằng
test (`tests/test_strategy_conformance.py:103-117`).

**Cấm tuyệt đối:** đổi `_default_strategy()`, đổi test ghim nó, hay đụng vào
`config/config.yaml`. `real_trading_enabled` giữ nguyên `false`.

### 0.3. Nền bằng chứng của hybrid có ba lỗ hổng đã được audit xác minh

Ghi ở đây để không ai đọc code về sau tưởng các con số kia đã được kiểm chứng:

1. **Số crypto tính với phí = 0 và trượt giá = 0**
   (`scripts/measure_octopus_combo_hybrid.py:281-282`,
   `scripts/optimize_octopus_combo_hybrid.py:158`). Với 13.612–27.571 lệnh,
   phí thật gần như chắc chắn đảo dấu kết quả.
2. **"Bộ tham số vàng" (`k_tp`=4,0) là sản phẩm quét lưới trong mẫu** — chọn đỉnh
   PnL trên chính bộ dữ liệu dùng để đo, không có tập kiểm định tách rời.
   Đó là lý do brief này **không** lấy `k_tp`=4,0 (xem §2.3).
3. **T+2,5 trên cổ phiếu VN**: đo lại trên đủ 1.308 mã cho thấy 54,5%–88,3% số
   lệnh chạm SL/TP **trước** ngày được phép bán, tức phần lớn lệnh không thoát ở
   mức đã thiết kế. Riêng cấu hình được quảng cáo "lãi cao nhất" (`k_tp`=2,6):
   7.991/14.662 = 54,5%.

---

## 1. MỤC TIÊU

Thêm `octopus_combo` vào `STRATEGIES` như một chiến lược thoả `Strategy`
Protocol, **và đo lại nó một cách trung thực trên đường ống `run_backtest`** để
có con số thật của chính thứ vừa đăng ký — thay vì thừa hưởng con số của một
mô hình khớp lệnh khác.

---

## 2. ĐẶC TẢ

### 2.1. File mới: `trading/strategies/octopus_combo.py`

Class `OctopusComboStrategy`, khuôn theo `OctopusPullbackStrategy`
(`trading/strategies/octopus_pullback.py:90-238`) — cùng style, cùng cách giữ
state theo symbol, cùng cách trả `None` khi chưa đủ warmup.

**Điều kiện tín hiệu — chép ĐÚNG từ `trading/pattern_backtest.py:391-408`,
không diễn giải lại:**

| # | Điều kiện | Nguồn |
|---|---|---|
| 1 | Thanh khoản: bình quân 20 **ngày đã đóng** ≥ 2 tỷ VND | `pattern_backtest.py:391-395` |
| 2 | `close > EMA(200)` **và** `close > MA(20)` | `:399` |
| 3 | `close > open` (nến xanh) **và** `EMA(9) > EMA(21)` **và** `MACD hist > 0` | `:400-402` |
| 4 | ≥ 2 nến đỏ trong 5 phiên **trước** bar hiện tại | `:403-406` |

**Ba khác biệt so với `OctopusPullbackStrategy` — phải ghi rõ trong docstring:**

1. thêm điều kiện `close > MA(20)`;
2. thêm điều kiện nến xanh `close > open`;
3. `EMA9 > EMA21` là **so sánh mức**, KHÔNG phải cắt lên. Octopus yêu cầu
   `prev_fast <= prev_slow and ema_fast > ema_slow`
   (`octopus_pullback.py:182`). Điều kiện mức **lỏng hơn nhiều** và sẽ sinh
   nhiều tín hiệu hơn hẳn. Đây là khác biệt quan trọng nhất — đừng "sửa" nó
   thành cắt lên cho giống octopus.

**Bắt buộc dùng lại, không viết lại:**

- `DailyLiquidityTracker` — `from trading.strategies.octopus_pullback import DailyLiquidityTracker`.
  Một công thức một chỗ. Công thức thanh khoản đã từng lệch nhau giữa hai bản
  chép tay một lần trong dự án này (`4ea4c8d`).
- `EmaCalculator`, `MacdCalculator`, `AtrCalculator` từ `trading.indicators`.

**Tham số mặc định:**

- `ema_fast=9, ema_slow=21, ema_trend=200`
- `macd_fast=12, macd_slow=26, macd_signal=9`
- `pullback_red=2, pullback_window=5`
- `ma_period=20`
- `min_avg_value_20=2_000_000_000.0, liquidity_window=20`
- `atr_period=14` — **chú ý:** `pattern_backtest.py:115` dùng ATR(5). Ở đây lấy
  14 cho khớp quy ước đường ống engine/backtest (`octopus_pullback.py:102`,
  `backtest.py` dùng `last_atr` cho sizing và trailing). Ghi rõ khác biệt này
  trong docstring.
- `tp_atr_mult=2.0` — xem §2.3.

**Năm thuộc tính bắt buộc** (`trading/strategy.py:41-54`, đã có test quét):
`on_bar`, `last_crossover`, `last_atr`, `warmup_bars` (**property**, không phải
method), `compute_crossover`.

`warmup_bars` = `max(ema_trend, macd_slow + macd_signal) + 1` = 201, giống
octopus. (Bộ lọc thanh khoản cần 20 **ngày** đã đóng nên trên bar 5m thực tế cần
nhiều bar hơn — đây là hạn chế **có sẵn** của octopus, không phải việc của đợt
này, đừng sửa.)

### 2.2. Thoát lệnh

Khuôn đúng `octopus_pullback.py:212-228`: TP = `bar.open + tp_atr_mult × ATR`
tại bar đầu tiên thấy vị thế; cắt lỗ để `TrailingStopManager` trong
`run_backtest` lo, strategy không tự làm.

### 2.3. Vì sao `tp_atr_mult=2.0` chứ không phải 4.0

`k_tp=4,0` là đỉnh của một phép quét lưới **trong mẫu** (§0.3.2). Lấy 2,0 —
đúng bằng octopus — biến chiến lược mới thành một **phép thử có kiểm soát**:
mọi thứ giống octopus trừ ba điều kiện tín hiệu ở §2.1. Khi đó chênh lệch đo
được quy được về đúng ba điều kiện đó, thay vì lẫn với việc nới TP.

Vẫn để `tp_atr_mult` là tham số của `__init__` để quét sau này; chỉ **mặc định**
là 2,0. Mục trong `STRATEGIES` dùng mặc định.

### 2.4. Đăng ký

Thêm đúng **một** dòng vào `trading/backtest.py:290-294`:

```python
    "octopus_combo": lambda: OctopusComboStrategy(),
```

cộng dòng import tương ứng. **Không đụng bất cứ thứ gì khác trong
`trading/backtest.py`** — đặc biệt `_TF_SPEC`, `run_backtest`, `_is_dirty`.

---

## 3. TIÊU CHÍ HOÀN THÀNH (kiểm chứng được, không mơ hồ)

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Viết `OctopusComboStrategy` | `uv run pytest tests/test_strategy_conformance.py -q` xanh — test này tự quét mọi mục `STRATEGIES` (`:49`), nên mục mới được phủ ngay khi đăng ký |
| 2 | Test riêng cho **ba** khác biệt §2.1 | 3 test: (a) chuỗi thoả octopus nhưng `close < MA20` → không tín hiệu; (b) chuỗi thoả nhưng nến đỏ → không tín hiệu; (c) chuỗi có `EMA9 > EMA21` **không** cắt lên ở bar đó → octopus trả `None`, octopus_combo trả `"bull"` |
| 3 | Test thanh khoản | Chuỗi < 2 tỷ/ngày → không tín hiệu, kể cả khi mọi điều kiện khác đủ |
| 4 | Đăng ký vào `STRATEGIES` | `uv run python -c "from trading.backtest import STRATEGIES; s=STRATEGIES['octopus_combo'](); print(type(s).__name__, s.warmup_bars)"` in ra `OctopusComboStrategy 201` |
| 5 | **Đo lại trung thực** | Chạy `octopus_combo` qua `run_backtest` trên **đúng rổ** mà `scripts/measure_octopus_matched_basket.py` dùng; báo cáo: tổng lệnh, số mã sinh lệnh, PnL, đặt **cạnh** baseline octopus `−1.615.319.902 / 1.514 lệnh / 439 mã` |

> **Đừng dùng CLI `python -m trading.backtest` làm bước kiểm chứng.** Nó gọi
> `load_config` (`trading/backtest.py:322`), mà `trading/config.py` đọc
> `os.environ["DB_DSN"]` cùng 5 biến SSI — thiếu là `KeyError`, không liên quan
> gì tới việc đăng ký đúng hay sai. Script đo ở bước 5 phải lấy DSN bằng
> `resolve_dsn` từ `scripts/_db_common.py`, đúng khuôn
> `scripts/measure_octopus_matched_basket.py`.
| 6 | Không trôi baseline | `uv run python scripts/measure_octopus_matched_basket.py` vẫn ra **đúng** `−1.615.319.902 / 1.514 / 439 / 748` |
| 7 | Nền xanh | `uv run pytest -m "not integration" -q` (hiện 468 passed) và `uv run ruff check trading tests scripts` |

**Chứng minh test không rỗng (bắt buộc, theo lệ dự án):** với mỗi test ở bước 2,
cố ý phá điều kiện tương ứng trong code, dán **output đỏ thô**, khôi phục, rồi
`grep -rn "SABOTAGE" trading tests scripts` phải rỗng. Test xanh mà phá không đỏ
là test vô nghĩa — dự án này đã gặp hai lần.

---

## 4. PHẠM VI PHẪU THUẬT

**Được sửa/tạo:**
- `trading/strategies/octopus_combo.py` (mới)
- `tests/test_octopus_combo.py` (mới)
- `trading/backtest.py` — **chỉ** 1 dòng trong dict `STRATEGIES` + 1 dòng import
- `scripts/` — script đo ở bước 5 (mới, hoặc tham số hoá script sẵn có nếu sạch hơn)

**Cấm đụng:**
- `trading/engine/main.py::_default_strategy()` và test ghim nó
- `run_backtest`, `PaperBroker`, `derivative_backtest`, `TrailingStopManager`
- `trading/pattern_backtest.py` (giữ nguyên — nó là bộ mô phỏng riêng, không
  phải thứ đang đăng ký)
- `trading/strategies/octopus_pullback.py` — **chỉ import** `DailyLiquidityTracker`,
  không sửa một dòng nào
- `config/config.yaml`, `.env`, `_TF_SPEC`
- Không `TRUNCATE`/`DROP`/xoá dòng dữ liệu; không nạp lại `bars_crypto`

**Quy tắc chung:** chỉ xoá import/biến/hàm mà chính thay đổi này làm thừa; phát
hiện ngoài phạm vi thì **báo cáo, không tự sửa**. Mọi dòng sửa phải truy ngược
được về brief này.

**Không commit, không push.** Claude audit rồi mới commit.

---

## 5. ĐIỀU PHẢI GHI VÀO DOCSTRING MODULE MỚI

Bắt buộc, để người đọc code sau này không hiểu nhầm:

1. Chiến lược này là **phần tín hiệu** của hybrid; cơ chế BUY STOP + SL/TP cố
   định đã tạo ra các con số trong báo cáo hybrid **không có** ở đây (§0.1).
2. Vì vậy **mọi con số trong 4 báo cáo hybrid không áp dụng cho class này.**
   Con số của class này là con số đo ở bước 5.
3. Ba lỗ hổng ở §0.3 của nền bằng chứng hybrid (phí = 0 trên crypto, quét lưới
   trong mẫu, T+2,5 chạm sớm 54,5–88,3%).

---

## 6. BÁO CÁO NỘP LẠI

- Bảng số bước 5 đặt cạnh baseline octopus.
- Output thô của bước 6 và 7 (không tóm tắt, dán nguyên).
- Output đỏ thô của từng lần phá hoại ở §3, kèm xác nhận `grep` rỗng.
- Bất cứ chỗ nào brief này sai hoặc mâu thuẫn: **báo lại, đừng tự quyết**.
