# Brief đợt 194: xu hướng khung tuần (MA) + vào lệnh khung ngày (RSI) + thoát theo ATR (ĐĂNG KÝ TRƯỚC)

- **Ngày:** 25/10/2026.
- **Spec:** dòng H ngày 25/10/2026 (đợt 194) trong `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`.
- **Vai trò:**
  - Claude giao việc, xuất dữ liệu, audit, commit, push và **chạy kiểm chứng**.
  - Agent viết code, tự kiểm chứng và chạy khám phá trên tập khám phá.
- **Agent KHÔNG được:**
  - commit hay push;
  - gọi API thật nào;
  - đọc `.env`;
  - **truy vấn DB**, cả đọc lẫn ghi;
  - mở bất kỳ file dữ liệu nào ngoài `data/research194/explore/`;
  - sửa `scripts/research188_*.py`, `research191_*.py`, `research192_*.py`, `research193_*.py`, `trading/indicators.py` hay `trading/strategies/momentum_rsi.py`. Chỉ được **import**.
- **Niêm phong:**
  - Tập kiểm chứng gồm:
    - các mã không thuộc tập khám phá trong 2016–2022;
    - mọi mã từ 01/01/2023 trở đi.
  - Tập này **không tồn tại** trên máy agent. Agent không được tìm, suy ra hay tải về.
  - Giá 2023+ đã bị các đợt 175/177/191 mở, nhưng chưa ai chạy luật của đợt này trên đó. V2 mang cảnh báo đó.

## 0. Yêu cầu và cách hiểu (đọc trước; có gì sai thì dừng và báo)

- **Yêu cầu của chủ dự án:** "plan tiếp chiến lược khác giao agent, áp dụng kết hợp atr, rsi, ma có thay đổi tham số phù hợp và xét khung thời gian lớn để xác định xu hướng, khung thời gian nhỏ để vào lệnh".
- **Cách Claude hiểu và chốt:**
  - **MA:** đường trung bình **khung tuần** xác định xu hướng. Chỉ mua khi xu hướng tuần lên.
  - **RSI:** RSI(14) **khung ngày** cắt lên lại ngưỡng θ, tức mua nhịp hồi trong xu hướng.
  - **ATR:** ATR(14) khung ngày đặt **dừng lỗ kéo theo** (chandelier), để lệnh thắng chạy dài.
  - **"Thay đổi tham số phù hợp":** một lưới nhỏ **đăng ký trước** (§3.6). Không chọn tham số theo đỉnh một ô; ô được chọn phải nằm trên **cao nguyên** (§5, Bước 2).
- **Vì sao khung lớn là tuần, khung nhỏ là ngày, không phải 1 giờ/5 phút:** dữ liệu trong phiên VN chỉ có từ 03/04/2026, khoảng 7 tháng. Như vậy không đủ để đo, và cũng không có tập kiểm chứng. Nến ngày có từ 2016.
- **Trùng với các họ đã đóng. Claude ghi rõ để không ai nói đây là ý tưởng mới:**
  - đợt 173 (pullback trên MA50/MA200) và đợt 177 (RSI2 trên MA200) chết vì **thoát quá sớm**. Trung vị giữ 2–4 phiên, cú hồi nhỏ hơn phí khứ hồi khoảng 0,76%;
  - đợt 188 `STK_WK_TREND_PULLBACK` (xu hướng tuần + pullback ngày) trượt cao nguyên;
  - đợt 175 (Donchian) và đợt 188 thắng tuyệt đối trong thị trường tăng nhưng **thua mua đều cả universe**.
- **Khác các đợt trên ở ba điểm, và đó là thứ đợt này đo:**
  1. **Thoát bằng ATR kéo theo + mất xu hướng tuần**, không chốt lời cố định, không thoát theo MA5. Nếu lỗi của 173/177 là "chốt non" thì luật này phải cho lệnh dài hơn và lãi ròng mỗi lệnh lớn hơn phí.
  2. **Mô phỏng danh mục 10 slot có NAV đánh giá theo giá đóng cửa mỗi ngày**. Lỗi #2 của đợt 188 là chỉ ghi lãi khi đóng lệnh, làm MDD thấp giả.
  3. **Thống kê chính là vượt trội tháng so với EW thanh khoản** (giống đợt 193), không phải lãi mỗi lệnh. Tiền mặt khi không có xu hướng được tính đủ: tháng thị trường tăng mà danh mục cầm tiền thì X âm.
- **Ước lượng trước của Claude:** khả năng qua đủ cổng là **thấp**. Lý do là 26 phép đo âm, trong đó có ba họ gần giống. Đây là phép đo, không phải lời hứa. **0 ứng viên là kết quả hợp lệ.**
- **Một ý tưởng duy nhất, 18 cấu hình EA.** Agent **không thêm ý tưởng, không thêm bộ lọc**.
- **Không dùng:** học máy, tham số riêng cho từng mã, đòn bẩy, bán khống. Chỉ mua (long-only).
- **Thiên lệch sống sót:** dữ liệu gần như không có mã huỷ niêm yết. Mã huỷ thường sụt dài, tức là loại mã mà bộ lọc xu hướng tránh được. Như vậy phép so với EW **thiên vị nhẹ cho EW**, bất lợi cho chiến lược. Vẫn ghi cảnh báo trong mọi báo cáo.

## 1. Dữ liệu agent được dùng (Claude xuất vào `data/research194/explore/`)

| File | Nội dung |
|---|---|
| `stocks_daily.csv.gz` | `symbol,date,open,high,low,close,volume`. Giá đã điều chỉnh, 04/01/2016 → 30/12/2022. Gồm các mã khám phá, tức `sha256('dot194\|'+mã).digest()[0] < 128`. Đã loại `exclusions.txt` và các dòng có OHLC ≤ 0 |
| `sessions.csv` | `date`: mọi phiên toàn thị trường (ngày có ≥ 100 mã có nến), 04/01/2016 → 30/12/2022 |
| `exchanges.csv` | `symbol,exchange` |
| `manifest.json` | Cùng định dạng đợt 193 |

**Đọc dữ liệu:** dùng `load_stocks`, `load_exchanges` của `scripts/research191_data.py` và `load_sessions` của `scripts/research192_core.py`.

## 2. Phạm vi file

- **Được tạo mới:**
  - `scripts/research194_core.py`
  - `scripts/research194_explore.py`
  - `scripts/research194_validate.py`
  - `tests/test_research194_*.py`
  - `docs/research/dot194/`, chứa `trial_ledger.csv`, `exploration_report.md`, `candidates.json`
- **Được import, không sửa:**

| Module | Symbol | Dùng để |
|---|---|---|
| `scripts/research188_core.py` | `resample` (luật `"W"`), `deflated_sharpe` | nến tuần; Bước 4 |
| `scripts/research188_ledger.py` | `evaluate_and_log` | sổ thử |
| `scripts/research191_data.py` | `load_stocks`, `load_exchanges`, `StockDailyBar` | đọc dữ liệu |
| `scripts/research191_exits.py` | `is_liquid`, `is_floor_locked`, `assert_ledger_safety` | thanh khoản, khoá sàn, an toàn sổ |
| `scripts/research192_core.py` | `load_sessions` | lịch phiên |
| `scripts/research193_core.py` | `get_rebalance_dates`, `ew_benchmark`, `calculate_rotation_metrics` | mốc tháng, EW, thống kê X_m |
| `scripts/research193_explore.py` | `filter_rebalance_dates`, `get_parameter_neighbors` | cắt giai đoạn, láng giềng cao nguyên |
| `trading/indicators.py` | `AtrCalculator` | ATR(14) |
| `trading/strategies/momentum_rsi.py` | `_RsiState` | RSI(14) Wilder |
| `trading/stock_study.py` | `entry_status` | chặn mua khi mở cửa giá trần, khối lượng 0, không có nến |
| `trading/paper_broker.py` | `FEE_RATE`, `SELL_TAX_RATE`, `SLIPPAGE_BPS` | phí |

  - Claude đã chạy thử `resample(bars, "W")`, `AtrCalculator(14).update(bar)` và `_RsiState(14).update(close)` trên `StockDailyBar` của tập này, cả ba đều chạy.
  - `_RsiState` có dấu `_` nhưng là cài đặt RSI Wilder duy nhất trong repo. Import nó thay vì viết lại.
  - Nếu một hàm không dùng lại được nguyên trạng thì **dừng và báo**, không chép rồi sửa.
  - **Không dùng** `simulate_portfolio` của đợt 188 (không đánh giá NAV theo ngày) hay `simulate_rotation` của đợt 193 (xoay vòng tháng, không phải lệnh theo tín hiệu). Mô phỏng viết mới theo §3.4.
- **KHÔNG đụng:** mọi file khác, `pyproject.toml`, `uv.lock`, DB.
- **GitNexus:**
  - Trước khi viết code, chạy `context`/`impact` cho các symbol import ở trên.
  - Sau khi xong, chạy `detect-changes --scope all`.
  - Dùng `node .gitnexus/run.cjs` hoặc `gitnexus`, **không npx**.

## 3. Luật (chốt; agent code đúng như dưới, không đổi)

`S` là danh sách phiên trong `sessions.csv`. `t` là một phiên. Mọi chỉ báo tính trên **nến của chính mã đó**, chỉ dùng dữ liệu tới hết phiên `t`.

### 3.1 Khung tuần: xu hướng (`weekly_trend_series`)
- **Nến tuần:** `resample(bars_của_mã, "W")` của đợt 188 (gộp theo tuần ISO).
- **Tuần nhìn thấy được tại phiên `t`:** chỉ các tuần ISO **trước** tuần chứa `t`. Tuần đang chạy, kể cả khi `t` là thứ Sáu, **không** được dùng. Luật này bảo thủ một phiên vào thứ Sáu, nhưng không có ngoại lệ ngày lễ phải xử lý.
- Gọi `w` là tuần nhìn thấy gần nhất, `SMA_n(w)` là trung bình đơn của `n` giá đóng cửa tuần kết thúc ở `w`.
- **`TREND(t)` đúng khi** `C_tuần(w) > SMA_n(w)` **và** `SMA_n(w) > SMA_n(w−1)`.
- Cần ít nhất `n + 1` tuần nhìn thấy được. Thiếu thì `TREND(t)` là sai (không có tín hiệu).

### 3.2 Khung ngày: tín hiệu vào (`entry_signals`)
- `RSI(t)`: `_RsiState(14)` nạp lần lượt close của mã tới hết `t`.
- **Tín hiệu mua ở close `t`** khi thoả cả sáu điều kiện:
  1. `TREND(t)` đúng;
  2. `RSI(t−1) < θ` **và** `RSI(t) ≥ θ` (cắt lên lại ngưỡng);
  3. `is_liquid(bars, t, min_turnover=1e9)`, tức **GTGD20 ≥ 1 tỷ** (`MIN_TURNOVER_194 = 1e9`, cùng lý do đợt 193);
  4. mã có ít nhất 60 nến ngày tới `t`;
  5. mã không đang được giữ, kể cả khi đang chờ bán;
  6. `entry_status(bars, t, exchange) == "ok"`, **và** nến kế tiếp của mã rơi đúng vào phiên kế tiếp của `t` trong `S`. Mã bị ngừng giao dịch thì không mua.
- **Khớp mua:** open của phiên kế tiếp.

### 3.3 Thoát (`chandelier_stop` + trong mô phỏng)
- Lệnh vào ở nến chỉ số `e`, giá `E`. Ở mỗi close `t ≥ e`:
  - `H_t = max(E, max close từ nến e tới t)`, dùng **close**, không dùng high;
  - `ATR(t)`: `AtrCalculator(14)` nạp nến của mã tới hết `t`. Đây là trung bình đơn của True Range, đúng như engine đang dùng;
  - `Stop_t = H_t − k × ATR(t)`.
- **Tín hiệu bán ở close `t`** khi `close_t < Stop_t` (lý do `STOP`) **hoặc** `TREND(t)` sai (lý do `TREND`). Nếu cả hai cùng đúng thì ghi `STOP`.
- **Khớp bán:** open của nến kế tiếp của mã, với hai luật:
  - **T+2:** phiên bán phải cách phiên mua ít nhất 2 phiên trong `S`. Tín hiệu đến sớm hơn thì lệnh bán **đã chốt**, chờ tới open của phiên đầu tiên được phép, không xét lại điều kiện;
  - **khoá sàn:** nến bán mà `is_floor_locked(close nến trước, high, low, exchange)` đúng thì không bán được, thử lại ở open nến sau. Mã không có nến ở phiên đó thì cũng chờ nến sau.
- Không có giới hạn số phiên giữ. Không có chốt lời cố định.

### 3.4 Mô phỏng danh mục (`simulate_swing_portfolio`, viết mới)
- Vốn đầu 100 triệu đồng. **K = 10 slot** (cố định, không thuộc lưới). Số cổ phiếu là số thực, không làm tròn lô.
- **Mỗi phiên `t` của giai đoạn, theo thứ tự:**
  1. **Open `t`:** khớp các lệnh bán đang chờ trước, rồi các lệnh mua từ tín hiệu ở close phiên trước.
     - Bán: tiền mặt được cộng `số cổ × open × (1 − FEE_RATE − SELL_TAX_RATE − SLIPPAGE_BPS/10⁴)`.
     - Mua: số lệnh mua ≤ `K −` số mã đang giữ sau khi bán. Thứ tự ưu tiên là GTGD20 tại phiên tín hiệu, giảm dần, hoà thì A→Z.
     - Giá trị mỗi lệnh mua `v = min(NAV(close phiên trước) / K, tiền mặt / (1 + FEE_RATE + SLIPPAGE_BPS/10⁴))`. `v ≤ 0` thì bỏ. Tiền mặt bị trừ `v × (1 + FEE_RATE + SLIPPAGE_BPS/10⁴)`.
     - Tiền bán ở cùng open được dùng để mua ngay sau đó.
     - Tín hiệu không được mua vì hết slot hoặc hết tiền thì **bỏ**, không để dành sang phiên sau.
  2. **Close `t`:** NAV = tiền mặt + Σ số cổ × close. Mã không có nến ở `t` thì dùng close gần nhất trước đó. Ghi NAV ngày.
  3. **Sau close `t`:** xét thoát cho mã đang giữ (§3.3), rồi xét tín hiệu mua (§3.2) cho phiên sau.
- **Đầu giai đoạn:** phiên bắt đầu là `L(M₀)`. NAV ở close `L(M₀)` là 100 triệu, và tín hiệu ở close `L(M₀)` được dùng. Chỉ báo được tính trên toàn bộ lịch sử từ 04/01/2016.
- **Cuối giai đoạn:** phiên cuối là `L(M₁)`.
  - Không nhận tín hiệu mua ở close của phiên ngay trước phiên cuối và ở close phiên cuối.
  - Ở close phiên cuối, bán hết theo giá close, trừ phí bán. Mã khoá sàn hoặc không có nến vẫn được định giá theo close cuối và trừ phí bán, rồi đóng sổ. Ghi lý do `END`.
- **Đầu ra:**
  - NAV ngày; NAV ở close mỗi `L(m)`; lợi nhuận tháng `R_m = NAV(L(m)) / NAV(L(m−1)) − 1`;
  - danh sách lệnh: mã, ngày tín hiệu, ngày mua, giá mua, ngày bán, giá bán, lý do, số phiên giữ, lãi ròng theo `compute_stock_net_return` của đợt 188 (chỉ để báo cáo);
  - tổng phí; tỷ lệ vốn nằm trong cổ phiếu, trung bình theo ngày.
- **CAGR** tính từ NAV đầu và NAV cuối theo số ngày dương lịch / 365,25. **MDD** trên **NAV ngày**. **Calmar** = CAGR / MDD.

### 3.5 Baseline và thống kê
- **EW:** `ew_benchmark(rebalance_dates, bars, sessions, min_turnover=1e9)` của đợt 193, cùng các mốc `L(m)` của giai đoạn.
- **Vượt trội tháng:** `X_m = R_m − EW_m`.
- **Thống kê:** `calculate_rotation_metrics(R, EW, rebalance_dates, portfolio_metrics, seed=194)` của đợt 193, trong đó `portfolio_metrics` có `cagr`, `mdd`, `calmar` của §3.4. Hàm này cho `mean_X`, `sharpe_X` (theo tháng), `p` một phía, `skew`, `kurt` Pearson.
- **Sổ thử:**
  - Dùng `evaluate_and_log` với `ledger_path="docs/research/dot194/trial_ledger.csv"`.
  - Ghi `n` = số tháng, `mean_net` = `mean_X`, `sharpe` = `sharpe_X`, `p`, `cagr`, `mdd`, `calmar`.
- **An toàn sổ:** `run_exploration` gọi `assert_ledger_safety(ledger_path)` **ở dòng đầu tiên**. Không có nhánh "đọc lại sổ rồi chạy tiếp".

### 3.6 Lưới (đăng ký trước, 18 cấu hình)

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `n` | {20, 40} | SMA tuần, khoảng MA100 và MA200 ngày |
| `θ` | {35, 40, 45} | ngưỡng RSI(14) ngày cắt lên |
| `k` | {2, 3, 4} | hệ số ATR của dừng kéo theo |

`idea_id = "I1_WKMA_RSI_ATR"`. Thứ tự ghi sổ: `n`, rồi `θ`, rồi `k`, mỗi tham số tăng dần.

### 3.7 Giai đoạn
- **EA:** `L(12/2016)` → `L(12/2019)`, 36 tháng `X_m`, từ 01/2017 tới 12/2019.
- **EB:** `L(12/2019)` → `L(12/2022)` = 30/12/2022, 36 tháng. EB bắt đầu với danh mục trống. Dữ liệu trước 2020 chỉ dùng để làm nóng chỉ báo.

## 4. Việc 1: hạ tầng (TDD trên dữ liệu tổng hợp trong `tmp_path`)

**Tiêu chí xong:**
- `uv run pytest tests/test_research194_*.py -q` xanh.
- **Test tính tay `simulate_swing_portfolio`:** 2–3 mã, có đủ **bốn nhánh tính phí** là mua, bán `STOP`, bán `TREND` và bán `END`. Ghi NAV cuối và tổng phí vào chú thích của test, và assert cả hai.
  - Đây là bài học đợt 193: phép phá "bỏ phí phần bán bớt" đã sống vì không test nào đi qua nhánh đó.
- **Test `weekly_trend_series`:** chuỗi có xu hướng tuần lật ở giữa một tuần. Test ghi rõ phiên đầu tiên `TREND` đổi giá trị.
- Mỗi phép phá dưới đây phải làm đỏ một test **gọi đúng hàm sản phẩm ghi ở cột cuối**.
  - Test chỉ so hằng số hay hàm tự định nghĩa trong test thì **không tính**. Đợt 188 (b)(g) và đợt 191 (i)(j) đã trượt vì lỗi này.
  - Ghi tên test bị đỏ.

| # | Phép phá | Test phải gọi |
|---|---|---|
| a | Xu hướng tuần dùng tuần **đang chạy** (chứa `t`) | `weekly_trend_series` |
| b | Bỏ điều kiện `SMA_n(w) > SMA_n(w−1)` | `weekly_trend_series` |
| c | RSI không cần cắt lên (chỉ `RSI(t) ≥ θ`), hoặc dùng `RSI(t+1)` | `entry_signals` |
| d | Bỏ `is_liquid` | `entry_signals` |
| e | `H_t` dùng high thay vì close, hoặc bỏ `E` khỏi `max` | `chandelier_stop` hoặc `simulate_swing_portfolio` |
| f | Bán ở close `t` thay vì open phiên sau | `simulate_swing_portfolio` |
| g | Bán trước T+2 | `simulate_swing_portfolio` |
| h | Bán được khi khoá sàn | `simulate_swing_portfolio` |
| i | Mua được khi `entry_status != "ok"` (mở cửa giá trần) | `simulate_swing_portfolio` |
| j | Giữ quá K mã, hoặc mua lại mã đang giữ | `simulate_swing_portfolio` |
| k1–k4 | Bỏ phí ở từng nhánh: mua / `STOP` / `TREND` / `END` (bốn phép riêng) | `simulate_swing_portfolio`, so với số tính tay |
| l | MDD tính trên NAV tháng thay vì NAV ngày | `simulate_swing_portfolio`, chuỗi sụt giữa tháng rồi hồi |
| m | `run_exploration` xoá sổ cũ hoặc bỏ `assert_ledger_safety` | `run_exploration` với `ledger_path` trong `tmp_path` |
| n | Bước 4 dùng `n_trials` thiếu `+ 26`, hoặc gọi `deflated_sharpe` sai tham số | `compute_step4_dsr` của `research194_explore.py`, so với lời gọi `deflated_sharpe` viết thẳng trong test |

- **Không có cờ phá thử trong code sản phẩm.**
- Chạy `uv run pyright scripts/research194_*.py tests/test_research194_*.py`. Không có pyright thì dùng `uv run python -m py_compile`. Ghi nguyên văn kết quả.

## 5. Việc 2: khám phá (sau khi Việc 1 xanh)

- **Bước 1:** chạy đủ 18 cấu hình trên EA và ghi sổ. Chọn cấu hình có `sharpe_X` cao nhất.
- **Bước 2: cao nguyên.** Mọi láng giềng ±1 bước trên **từng** tham số (`get_parameter_neighbors` của đợt 193) phải có `mean_X > 0` và `sharpe_X ≥ 50%` của cấu hình được chọn. Không đạt thì loại, **không** đổi đỉnh.
- **Bước 3:** chạy đúng cấu hình đó **một lần** trên EB và ghi sổ với `period='EB'`. Đạt khi thoả cả ba:
  - `mean_X > 0` và p một phía < 0,05;
  - Calmar danh mục ≥ 0,86;
  - **số lệnh đã đóng trong EB ≥ 100**.
- **Bước 4: DSR** trên chuỗi `X_m` của EA.
  - Hàm riêng `compute_step4_dsr(sharpe_x, n_months, skew, kurt, ea_sharpes)` gọi `deflated_sharpe(sr, n_obs, skew, kurt, n_trials=len(ea_sharpes) + 26, sr_trials_var=var(ea_sharpes, ddof=1))`. Hằng số `PRIOR_NEGATIVE_FAMILIES = 26`.
  - Đạt khi DSR ≥ 0,95. **Chỉ in DSR đã tính thật.** Dừng trước Bước 4 thì ghi "không tính".
- **Ứng viên:** tối đa 1. **0 ứng viên là kết quả hợp lệ.** Không nới bước nào.
- **Mọi bảng EA và EB phải in:**
  - số tháng, `mean_X`, `sharpe_X`, p;
  - lợi nhuận tháng TB của chiến lược và của EW; CAGR của EW tính từ chuỗi EW_m;
  - CAGR, MDD, Calmar của danh mục;
  - số lệnh đóng, tỷ lệ thắng, lãi ròng TB mỗi lệnh, trung vị số phiên giữ, số lệnh theo lý do `STOP` / `TREND` / `END`;
  - tỷ lệ vốn trong cổ phiếu TB, phí theo năm tính bằng % NAV bình quân.
- **Bảng phụ cho cả 18 dòng EA**, chỉ để đọc, không dùng để chọn: `mean_X`, `sharpe_X`, trung vị số phiên giữ, lãi ròng TB mỗi lệnh. Đây là chỗ trả lời câu hỏi "thoát bằng ATR có cho lệnh dài hơn phí không".
- **Cấm:** chạy EB lần hai, sửa luật sau khi thấy EB, thêm bộ lọc, thêm ý tưởng.

**`research194_validate.py`** (agent viết, Claude chạy):
- **CLI:** `--data-dir`, `--candidates`, `--candidates-sha`, `--part V1|V2`, `--first-rebalance`, `--last-rebalance`, `--hurdle-cagr`.
  - `--hurdle-cagr` **bắt buộc khi `--part V2`, không có giá trị mặc định**. Đợt 192 và 193 để mặc định 0,10, và lần này không chấp nhận lại.
  - Sha lệch thì `return 2`. Thiếu file thì `return 3`.
- Gọi đúng luật và tham số ghi trong `candidates.json`. In ĐẠT hoặc TRƯỢT theo §6.
- **Test, chỉ dùng dữ liệu tổng hợp trong `tmp_path`:**
  - sha sai thì `return 2`;
  - V2 thiếu `--hurdle-cagr` thì lỗi;
  - chuỗi có một mã tăng đều theo xu hướng, có nhịp điều chỉnh làm RSI cắt lên, còn các mã khác đi ngang, thì ĐẠT;
  - chuỗi mà mọi mã giảm đều thì TRƯỢT.

**Tiêu chí xong Việc 2:**
- `docs/research/dot194/` có đủ 3 file.
- Sổ có đúng 18 dòng EA, cộng 1 dòng EB nếu đi tới Bước 3.
- `uv run ruff check scripts/research194_*.py tests/test_research194_*.py` sạch.
- `uv run pytest -m "not integration" -q` không đỏ thêm. Ghi số passed trước và sau.

## 6. Cổng kiểm chứng (chốt hôm nay; Claude chạy một lần sau audit)

Mỗi ứng viên phải ĐẠT **cả V1 lẫn V2**, với `α = 0,05`, vì có tối đa 1 ứng viên.

| Phần | Dữ liệu | Giai đoạn |
|---|---|---|
| **V1: mã chưa thấy** | các mã kiểm chứng, 2016–2022 | `L(12/2016)` → `L(12/2022)`, 72 tháng |
| **V2: giai đoạn sau** | toàn bộ mã, làm nóng chỉ báo bằng dữ liệu 2022 | `L(12/2022)` → `L(09/2026)`, 45 tháng |

- Mọi phần phải có `mean_X > 0` với p một phía < α, Calmar ≥ 0,86 và số lệnh đóng ≥ 100.
- **V2 thêm một điều kiện:** CAGR danh mục phải **lớn hơn** mốc ETF + tiền gửi tính trên cùng giai đoạn. Trước khi chạy V2, Claude tính lại mốc tới `L(09/2026)` theo memory `moc-chuan-etf-cong-tien-gui` rồi truyền vào `--hurdle-cagr`.
- **Qua cổng:** chỉ được paper forward ≥ 3 tháng (spec E). **Không có đường tới lệnh thật trong đợt này.**
- **Trượt:** đóng họ "xu hướng tuần + RSI + ATR", ghi phép đo âm.

## 7. Báo cáo agent phải nộp

1. GitNexus: `context`/`impact` trước khi sửa và `detect-changes` sau khi sửa, chép nguyên văn phần tóm tắt.
2. Test:
   - danh sách `def test_`, số passed trước và sau;
   - bảng phép phá (a)–(n), gồm tên test bị đỏ **và hàm sản phẩm mà test đó gọi**;
   - kết quả pyright hoặc `py_compile`.
3. Số dòng sổ theo giai đoạn.
4. Bảng §5 và bảng phụ 18 dòng, kết luận, sha256 của `candidates.json`.
5. **Chỉ chép số có trong file kết quả.** Con số không có trong `exploration_report.md` hay sổ thì không được đưa vào báo cáo.
6. Chỗ mơ hồ: lựa chọn nào ảnh hưởng tới kết quả mà brief chưa quy định thì **dừng và hỏi**.
7. Cam kết: không truy vấn DB, không gọi API, không đọc file ngoài `data/research194/explore/`, không chạy validator trên dữ liệu thật, không xoá sổ.

## 8. Claude làm

- **Trước khi giao:** đã xuất `data/research194/explore/` kèm manifest và kiểm bằng loader. 623 mã, 0 mã lọt từ tập kiểm chứng. Universe chỉ đếm số mã, không xem giá: 57–92 mã đạt GTGD20 ≥ 1 tỷ trong 2016–2019.
- **Sau khi nhận báo cáo:**
  - chạy lại test, pyright và **tự viết phép phá** (a)–(n), không chỉ đọc bảng của agent;
  - chạy lại explore vào thư mục tạm rồi so sổ;
  - **đếm độc lập** NAV và danh sách lệnh của cấu hình được chọn trên EA, bằng code riêng;
  - commit, tức niêm phong `candidates.json`.
- **Nếu có ứng viên:**
  - ghi `docs/holdout-unlock-log.md` **trước**;
  - xuất tập kiểm chứng;
  - chạy V1 một lần, V2 một lần;
  - lưu nguyên văn vào `logs/dot194-kiem-chung-<ngày>.log`.
- **Cuối cùng:** viết `docs/research/2026-10-dot-194-ket-qua-…md`, cập nhật memory, commit và push.
