# Brief giao việc — gói K: cửa sổ thanh khoản tính theo NGÀY, không theo bar

Viết 06/09, sau quyết định của chủ dự án 05/09:

- **G — giữ `octopus_pullback` làm chiến lược engine.**
- **K — ngưỡng thanh khoản là giá trị giao dịch bình quân 20 NGÀY gần nhất ≥ 2 tỷ VND.**
- **F — dùng hợp đồng perpetual** cho crypto (đã thoả sẵn: `bars_crypto` đang nạp
  đúng perpetual, 20 mã, từ 2021-05-14 — không cần nạp lại gì cho F).

Quyết định K xác nhận đúng giả thuyết trong
`2026-09-05-danh-gia-go-live-va-plan-ton-dong.md` §1: ý định gốc của
`min_avg_value_20` luôn là **20 phiên/ngày**, không phải "20 bar bất kỳ". Đây
không phải chọn số mới — là **sửa một lỗi triển khai** đã có từ đầu, chỉ vô
hại khi engine chạy bar ngày và lộ ra khi engine chạy bar 5 phút.

---

## 1. Việc CHÍNH — cửa sổ thanh khoản phải gộp theo ngày giao dịch trước khi lấy bình quân

### 1.1 Hiện trạng (đọc trước khi sửa)

`trading/strategies/octopus_pullback.py:104-113` (`_track_windows`) đẩy
**mỗi bar** — bất kể khung thời gian — vào một deque `maxlen=liquidity_window+1`,
rồi `_liquidity_ok` (dòng 124-131) lấy bình quân trực tiếp trên deque đó qua
`liquidity_avg_before` (dòng 49-58).

Với bar ngày: 1 bar = 1 ngày, nên "20 bar cuối" tình cờ đúng "20 ngày cuối".
Với bar 5 phút: "20 bar cuối" là ~100 phút, sai với ý định ~78 lần.

`trading/backtest.py:56` (`ever_liquid`) là **bản chép công thức thứ hai**
dùng cho các script đo diện rộng (`measure_strategy.py`,
`measure_octopus_matched_basket.py`, `measure_5m_strategies.py`) — nó phải
sửa **cùng lúc, cùng cách**, nếu không các script đo sẽ đo một thứ khác với
cái chiến lược thật sự dùng (đúng bẫy `4ea4c8d` — một công thức phải ở đúng
một nơi; `liquidity_avg_before` đã là nỗ lực trước đó để gộp hai công thức về
một, đừng làm nó tách ra lại theo hướng khác).

### 1.2 Việc phải làm

Đổi đơn vị của cửa sổ từ "N bar" thành "N ngày giao dịch đã đóng". Cụ thể:

- Gộp giá trị giao dịch (`close * volume`) của mọi bar cùng một **ngày** (theo
  `bar.ts.date()`) thành một giá trị tổng của ngày đó.
- Giữ một cửa sổ trượt **N ngày đã đóng** (không tính ngày hôm nay, kể cả khi
  hôm nay đã đi qua nhiều bar) — giữ đúng ngữ nghĩa "TRƯỚC bar hiện tại" mà
  docstring cũ đã nêu.
- `_liquidity_ok` lấy bình quân trên N ngày đã đóng đó, so với `min_avg_value_20`.

### 1.3 Quyết định thiết kế đã có sẵn — đọc kỹ trước khi tự chọn khác

**Dùng `bar.ts.date()` trực tiếp, KHÔNG ép múi giờ.** Đừng chuyển `bar.ts`
sang `Asia/Ho_Chi_Minh` trước khi lấy `.date()`. Lý do:

- Bar cổ phiếu VN (`bars`, `bars_daily`) đã được lưu với `tzinfo` đúng theo
  quy ước sản phẩm (xem `db.py:819` — bài học "bẫy ép ngày theo UTC" đã ghi
  lại). `.date()` trực tiếp cho đúng ngày giao dịch VN.
- Bar crypto (`bars_crypto`) lưu UTC-aware, và BingX tự đóng nến ngày theo
  UTC. `.date()` trực tiếp cho đúng ngày giao dịch của sàn.

Ép cả hai về `Asia/Ho_Chi_Minh` sẽ tạo ra **lỗi đơn vị thứ sáu** của dự án này
— áp quy ước thị trường VN lên dữ liệu 24/7 UTC. Không làm việc đó.

### 1.4 Ràng buộc cứng — phạm vi phẫu thuật

- **Chỉ sửa cơ chế cửa sổ thanh khoản.** Không đụng `_reds`/`_reds_before`
  (cửa sổ nến đỏ pullback) — mục đó không nằm trong quyết định K, giữ nguyên
  theo bar như hiện tại.
- Sửa `liquidity_avg_before` (octopus_pullback.py) **và** `ever_liquid`
  (backtest.py) — hai hàm phải cùng đổi ngữ nghĩa, cùng cách, một nơi.
- Không đổi `min_avg_value_20 = 2_000_000_000.0` — giá trị đó đã đúng theo
  quyết định K, chỉ đơn vị thời gian của cửa sổ là sai.
- Không đụng `compute_crossover`, `on_bar`, `warmup_bars`, hay bất kỳ strategy
  nào khác ngoài `octopus_pullback.py` và `backtest.py::ever_liquid`.
- Chạy `gitnexus_impact` trên `OctopusPullbackStrategy._liquidity_ok` và
  `ever_liquid` trước khi sửa (chỉ số đang cũ — `npx gitnexus analyze
  --repo AI_auto_trading_system` trước).

### 1.5 Tiêu chí — cổng bắt buộc là tiêu chí 1

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | **CỔNG.** Tái hiện đúng bảng khung ngày cũ | Chạy lại `measure_octopus_matched_basket.py` (hoặc `measure_strategy.py --strategy octopus_pullback`) trên `bars_daily`: phải ra **đúng** −1.615.319.902 / 1.514 lệnh / 439 mã / 748 mã đủ TK — bit-for-bit như trước khi sửa. Vì 1 bar ngày = 1 ngày, sửa đúng thì con số này KHÔNG ĐỔI. Lệch dù chỉ 1 đồng ⇒ dừng, báo cáo, đừng đi tiếp |
| 2 | Cửa sổ 5 phút giờ đúng nghĩa | Test đơn vị: nạp N bar 5 phút cùng một ngày với tổng giá trị vượt 2 tỷ, cửa sổ phải coi đó là **một ngày** đủ thanh khoản, không phải N ngày |
| 3 | Chốt X hết đỏ (nếu thanh khoản thật đủ) | Chạy lại `scripts/check_silent_engine.py` trên `bars` thật. Báo cáo nguyên văn output — kể cả nếu vẫn còn mã câm (đó có thể là sự thật hợp lệ: HII/AAA có thể vẫn không đủ 2 tỷ/ngày thật) |
| 4 | Đo lại đúng trên bar 5 phút | Chạy lại kiểu `measure_5m_strategies.py` với cửa sổ đã sửa, báo cáo số lệnh/PnL mới cạnh số cũ (đã sai) để thấy chênh lệch |
| 5 | Sabotage | Tạm phá cửa sổ về lại "N bar" (bỏ bước gộp ngày) trên đúng test ở tiêu chí 2 ⇒ phải đỏ. Dán output đỏ, khôi phục, `grep -rn "SABOTAGE"` rỗng |
| 6 | Không hồi quy | `uv run pytest -m "not integration" -q` + `-m integration -q` |
| 7 | Lint | `uv run ruff check trading tests scripts` sạch |

**Tiêu chí 1 là cổng cứng nhất trong toàn bộ session này.** Nó là bằng chứng
duy nhất cho thấy việc sửa "đơn vị thời gian" không vô tình sửa luôn "công
thức". Không qua được tiêu chí 1 thì không báo cáo bất kỳ số nào khác.

### 1.6 Phạm vi file

- **Sửa:** `trading/strategies/octopus_pullback.py`, `trading/backtest.py`
  (chỉ hàm `ever_liquid`), `tests/` (test mới/sửa cho hai hàm trên).
- **Không đụng:** mọi strategy khác, `trading/engine/`, `trading/real_orders.py`,
  `config/config.yaml`, `scripts/measure_*.py` hiện có (chúng gọi
  `ever_liquid`/`liquidity_spec` — sẽ tự đúng theo sau khi hàm lõi sửa, không
  cần sửa các script đó).

---

## 2. Việc phụ — F đã thoả, chỉ cần ghi nhận

Không có package code cho F. `bars_crypto` đã là dữ liệu perpetual (kiểm
05/09: 20 mã kiểu `1000PEPE-USDT`, min ts 2021-05-14, khớp phát hiện "perpetual
sâu hơn spot ~5,3 năm"). Sau khi gói K xong, các phép đo crypto trước đó
(`measure_crypto_strategies.py`, `liquidity_sensitivity.py`) dùng lại đúng
`ever_liquid` đã sửa — không cần script mới. Nếu muốn đo lại crypto với ngưỡng
thanh khoản đúng ngữ nghĩa ngày, đó là việc nối tiếp SAU gói K, không phải
song song (phụ thuộc trực tiếp vào kết quả K).

## 3. Không giao agent — Claude làm sau khi audit gói K

- Cập nhật `CLAUDE.md`, `_default_strategy()` docstring, `GO_LIVE_AUDIT.md`,
  bảng tồn đọng — gỡ cảnh báo "engine đang CÂM" nếu tiêu chí 3 cho thấy đã hết
  câm, hoặc ghi rõ nếu vẫn câm vì lý do thật (thanh khoản thật sự không đủ).
- Đăng ký scheduled task `trading-engine-cam` (đã hoãn từ đợt X, không phụ
  thuộc gói K).
- Dựng lại image — gói K chạm `trading/`, nên đây là điểm dựng lại tự nhiên
  cho toàn bộ các thay đổi tồn từ đợt L đến nay.

## 4. An toàn — không đổi so với các đợt trước

`real_trading_enabled` giữ `false`. Không gọi API đặt lệnh. Không sửa
`config/config.yaml`. Agent không commit, không push — Claude audit rồi mới
commit.
