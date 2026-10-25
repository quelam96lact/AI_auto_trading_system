# Brief đợt 195: xu hướng khung ngày (MA) + vào lệnh khung 1 giờ (RSI) + thoát theo ATR ngày (ĐĂNG KÝ TRƯỚC)

- **Ngày:** 25/10/2026.
- **Spec:** dòng H ngày 25/10/2026 (đợt 195) trong `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`.
- **Vai trò:**
  - Claude giao việc, xuất dữ liệu, audit, commit, push và **chạy kiểm chứng**.
  - Agent viết code, tự kiểm chứng và chạy khám phá trên tập khám phá.
- **Agent KHÔNG được:**
  - commit hay push;
  - gọi API thật nào;
  - đọc `.env`;
  - **truy vấn DB**, cả đọc lẫn ghi;
  - mở bất kỳ file dữ liệu nào ngoài `data/research195/explore/`;
  - sửa bất kỳ file `scripts/research18x_*.py`, `research19[0-4]_*.py`, `trading/indicators.py`, `trading/strategies/momentum_rsi.py`, `trading/stock_study.py`. Chỉ được **import**.
- **Niêm phong:**
  - **V1:** các mã không thuộc tập khám phá, 03/04 → 07/08/2026. Dữ liệu nằm trong DB, không xuất cho agent.
  - **V2:** toàn bộ mã, 10/08 → 23/10/2026. Nến 5 phút của giai đoạn này **chưa có trong DB**, vì collector chỉ ghi 4 mã từ tháng 9. Như vậy chưa ai, kể cả Claude, nhìn thấy nó.
  - Agent không được tìm, suy ra hay tải về hai tập trên.

## 0. Yêu cầu và cách hiểu (đọc trước; có gì sai thì dừng và báo)

- **Yêu cầu của chủ dự án:** "plan tiếp sửa thông số chiến lược giao dịch khung ngày, vào lệnh khung 1h".
- **Cách Claude hiểu và chốt:** giữ khung luật của đợt 194 (MA xác định xu hướng, RSI cắt lên để vào lệnh, ATR kéo theo để thoát) nhưng hạ một khung và **chỉnh lại tham số** cho khung mới:
  - **xu hướng:** SMA trên nến **ngày**, n ∈ {50, 100}. Đợt 194 dùng SMA tuần 20/40, tương đương ngày 100/200;
  - **vào lệnh:** RSI(14) trên nến **1 giờ** cắt lên lại θ ∈ {30, 40}. Nến 1 giờ dao động mạnh hơn nến ngày nên ngưỡng hạ xuống;
  - **thoát:** dừng kéo theo bằng ATR(14) **ngày**, k ∈ {2, 3}, xét ở mỗi close 1 giờ, cộng thêm điều kiện mất xu hướng ngày.
  - Lưới chỉ có 8 cấu hình vì dữ liệu ngắn (xem dưới). Không có cấu hình nào được chọn theo đỉnh một ô.
- **Giới hạn dữ liệu. Đây là điểm quyết định của đợt này:**
  - SSI chỉ giữ nến 5 phút khoảng 4 tháng gần nhất.
  - Trong DB có khoảng 300 mã cho **03/04 → 07/08/2026, tức 87 phiên**. Sau đó collector chỉ ghi HPG, IJC, AAA, HII.
  - Như vậy giai đoạn khám phá chỉ là **một giai đoạn 4 tháng, một trạng thái thị trường**, và không đủ để thống kê theo tháng như đợt 193/194.
  - **Vì thế thống kê chính là theo lệnh**: vượt trội của từng lệnh so với EW cùng khoảng thời gian, với p bootstrap theo **khối tuần**. Không mô phỏng danh mục slot.
- **Trùng với họ vừa đóng.** Claude ghi rõ:
  - đợt 194 (tuần/ngày) cho 18/18 ô âm, và lãi ròng mỗi lệnh âm ở mọi ô. Thoát bằng ATR không cứu được, nên lỗi nằm ở tín hiệu vào;
  - điều đợt này đo là: **vào lệnh chính xác hơn bằng nến 1 giờ có làm lệnh thắng phí không.**
- **Ước lượng trước của Claude: thấp.** Cùng họ luật vừa âm ở khung lớn hơn; khung nhỏ hơn thì nhiễu hơn và vẫn chịu phí khứ hồi khoảng 0,76%. **0 ứng viên là kết quả hợp lệ.**
- **Một ý tưởng, 8 cấu hình.** Agent **không thêm ý tưởng, không thêm bộ lọc**.
- **Không dùng:** học máy, tham số riêng từng mã, đòn bẩy, bán khống. Chỉ mua.
- **Thiên lệch:**
  - danh sách khoảng 300 mã có nến 5 phút là universe collector chọn theo thanh khoản ở thời điểm gần đây, nên có thiên lệch nhìn trước nhẹ;
  - dữ liệu không có mã huỷ niêm yết.

  Phép so với EW trên **cùng** universe vẫn đứng. Ghi cảnh báo trong mọi báo cáo.

## 1. Dữ liệu agent được dùng (Claude đã xuất vào `data/research195/explore/`)

| File | Nội dung |
|---|---|
| `stocks_daily.csv.gz` | `symbol,date,open,high,low,close,volume`, nến **ngày** đã điều chỉnh, 02/01/2025 → 07/08/2026, 147 mã khám phá (`sha256('dot195\|'+mã).digest()[0] < 128`). Đã loại `exclusions.txt` |
| `bars_5m.csv.gz` | `symbol,ts,open,high,low,close,volume`, nến **5 phút**, 03/04 → 07/08/2026, cùng 147 mã. Chi tiết dưới bảng |
| `sessions.csv` | `date`: mọi phiên toàn thị trường, 02/01/2025 → 07/08/2026 |
| `exchanges.csv` | `symbol,exchange` |
| `manifest.json` | sha256 từng file, luật chia mã, luật điều chỉnh, số liệu xuất |

**Chi tiết `bars_5m.csv.gz`:**
- `ts` là **giờ bắt đầu nến**, giờ Việt Nam, dạng `YYYY-MM-DDTHH:MM`, không có múi giờ.
- Giá đã nhân hệ số `f(d) = close ngày(d) / close nến ATC 14:45(d)` để khớp với nến ngày đã điều chỉnh. Ngày không có nến ATC thì dùng `f` của ngày trước.
- Giá được kẹp vào [low, high] của nến ngày cùng ngày. 1,5% số trường giá bị kẹp, vì dữ liệu 5 phút thô có lẫn giá ngoài biên độ ngày.
- Đã bỏ các dòng có OHLC ≤ 0.

**Claude đã kiểm:**
- 0 mã lọt từ tập kiểm chứng.
- Sau điều chỉnh, 0 ngày có high/low 5 phút vượt nến ngày.
- 128–143 mã đạt GTGD20 ≥ 1 tỷ.
- Lưới giờ 5 phút: 09:00–11:25, 13:00–14:25, nến ATC 14:45, và một số ít nến 14:30–14:55.

**Đọc dữ liệu:**
- `load_stocks(dir, end="2026-08-07")` và `load_exchanges` của `scripts/research191_data.py`;
- `load_sessions(dir, end="2026-08-07")` của `scripts/research192_core.py`;
- agent viết `load_bars_5m(dir)` mới: kiểm sha256 với manifest giống `load_stocks`, lệch thì `ValueError`; trả `dict[mã, list[Bar5m]]` theo thứ tự thời gian.

## 2. Phạm vi file

- **Được tạo mới:**
  - `scripts/research195_core.py`
  - `scripts/research195_explore.py`
  - `scripts/research195_validate.py`
  - `tests/test_research195_*.py`
  - `docs/research/dot195/`, chứa `trial_ledger.csv`, `exploration_report.md`, `candidates.json`
- **Được import, không sửa:**

| Module | Symbol | Dùng để |
|---|---|---|
| `scripts/research188_core.py` | `compute_stock_net_return`, `deflated_sharpe` | lãi ròng mỗi lệnh; Bước 4 |
| `scripts/research188_ledger.py` | `evaluate_and_log` | sổ thử |
| `scripts/research191_data.py` | `load_stocks`, `load_exchanges`, `StockDailyBar` | dữ liệu ngày |
| `scripts/research191_exits.py` | `is_liquid`, `is_floor_locked`, `assert_ledger_safety` | thanh khoản, khoá sàn, an toàn sổ |
| `scripts/research192_core.py` | `load_sessions` | lịch phiên |
| `scripts/research193_explore.py` | `get_parameter_neighbors` | láng giềng cao nguyên |
| `trading/indicators.py` | `AtrCalculator` | ATR(14) ngày |
| `trading/strategies/momentum_rsi.py` | `_RsiState` | RSI(14) Wilder trên close 1 giờ |
| `trading/stock_study.py` | `is_ceiling_open`, `bootstrap_by_month` | chặn mua giá trần; bootstrap khối, xem ghi chú |
| `trading/paper_broker.py` | `FEE_RATE`, `SELL_TAX_RATE`, `SLIPPAGE_BPS` | phí |

  - `bootstrap_by_month` nhận `dict[tuple[int, int], list[float]]` và lấy mẫu lại theo khoá. Truyền khoá `(năm ISO, tuần ISO)` thì nó thành bootstrap **theo tuần**. Không viết hàm bootstrap mới.
  - Nếu một hàm không dùng lại được nguyên trạng thì **dừng và báo**, không chép rồi sửa.
- **KHÔNG đụng:** mọi file khác, `pyproject.toml`, `uv.lock`, DB.
- **GitNexus:**
  - Trước khi viết code, chạy `context`/`impact` cho các symbol import ở trên.
  - Sau khi xong, chạy `detect-changes --scope all`.
  - Dùng `node .gitnexus/run.cjs` hoặc `gitnexus`, **không npx**.

## 3. Luật (chốt; agent code đúng như dưới, không đổi)

`S` là danh sách phiên trong `sessions.csv`. "Phiên trước `t`" là phiên liền trước `t` trong `S`. Mọi chỉ báo tính trên nến của chính mã đó.

### 3.1 Nến 1 giờ (`resample_1h`)
- **Gộp nến 5 phút của mỗi mã, mỗi ngày, theo giờ của `ts`:**
  - `09` gồm 09:00–09:55;
  - `10` gồm 10:00–10:55;
  - `11` gồm 11:00–11:25;
  - `13` gồm 13:00–13:55;
  - `14` gồm 14:00–14:55, **kể cả nến ATC 14:45**.
- **Giá trị của nến 1 giờ:** open là open của nến 5 phút đầu; close là close của nến cuối; high là max, low là min; volume là tổng; `ts` là ngày cộng giờ bắt đầu nhóm.
- Nhóm không có nến 5 phút nào thì **không có** nến 1 giờ. Mỗi ngày có tối đa 5 nến 1 giờ.

### 3.2 Khung ngày: xu hướng, ATR, thanh khoản tại phiên `t`
Chỉ dùng nến ngày có ngày **< t**. Gọi `j` là chỉ số nến ngày cuối cùng trước `t`.
- `TREND_D(t)` đúng khi `close[j] > SMA_n(j)` **và** `SMA_n(j) > SMA_n(j−1)`. Cần ít nhất `n + 1` nến ngày trước `t`; thiếu thì sai.
- `ATR_D(t)`: `AtrCalculator(14)` nạp nến ngày tới hết `j`. Chưa đủ 14 nến thì là `None`.
- `LIQ(t)`: `is_liquid(nến_ngày, j, min_turnover=1e9)` (`MIN_TURNOVER_195 = 1e9`), **và** có ít nhất 60 nến ngày trước `t`.

### 3.3 Tín hiệu vào ở close nến 1 giờ `h` (phiên `t`) và khớp mua
- **RSI:** `RSI1h(h)` là `_RsiState(14)` nạp lần lượt close mọi nến 1 giờ của mã từ đầu dữ liệu tới hết `h`, liên tục qua các ngày.
- **Tín hiệu mua** khi thoả cả sáu điều kiện:
  1. `TREND_D(t)` đúng;
  2. `RSI1h(h−1) < θ` **và** `RSI1h(h) ≥ θ`, cả hai khác `None`, và `h` là nến 1 giờ thứ 30 trở đi của mã;
  3. `LIQ(t)` đúng;
  4. mã **không đang giữ**, kể cả khi đang chờ bán;
  5. mã có nến 1 giờ kế tiếp `h+1`. Nếu `h+1` thuộc phiên khác `t` thì đó phải là **phiên kế tiếp của `t` trong `S`**;
  6. tại nến khớp `h+1`: `is_ceiling_open(ref, open[h+1], exchange)` sai và `volume[h+1] > 0`. `ref` là close ngày của phiên trước phiên chứa `h+1`.
- **Khớp mua:** open của `h+1`, giá vào `E`.
- **Sau khi đóng lệnh:** mã được vào lại từ tín hiệu ở close của nến khớp bán trở đi.

### 3.4 Thoát
- **Dừng kéo theo**, xét ở close mỗi nến 1 giờ `u` của mã, từ nến khớp mua trở đi:
  - `H_u = max(E, max close 1 giờ từ nến khớp mua tới u)`, dùng **close**, không dùng high;
  - `Stop_u = H_u − k × ATR_D(phiên của u)`. `ATR_D` là `None` thì không có dừng;
  - **`STOP`** khi `close[u] < Stop_u`.
- **Mất xu hướng:** ở close của **nến 1 giờ cuối cùng của phiên `t`**, nếu `TREND_D(phiên kế tiếp của t)` sai thì có tín hiệu **`TREND`**. Giá trị này tính bằng nến ngày tới hết `t`, tức đã biết lúc ATC.
- Nếu cả hai cùng đúng ở một close thì ghi `STOP`.
- **Khớp bán:** open của nến 1 giờ kế tiếp của mã, với ba luật:
  - **T+2:** cổ phiếu mua ở phiên `e` chỉ bán được từ nến `13` của phiên `e+2` (chỉ số trong `S`) trở đi. Đây là giả định "hàng về chiều T+2" (§9). Tín hiệu đến sớm hơn thì lệnh bán **đã chốt**, chờ tới open của nến đầu tiên được phép, không xét lại điều kiện;
  - **khoá sàn:** nến khớp có `is_floor_locked(ref, high, low, exchange)` đúng thì không bán được, thử lại ở nến sau. `ref` là close ngày của phiên trước;
  - mã không có nến kế tiếp thì chờ nến sau.
- **Cuối dữ liệu:** ở close nến 1 giờ cuối cùng của phiên 07/08/2026, mọi lệnh còn mở đóng theo close 1 giờ cuối cùng của mã, lý do **`END`**.
- Không giới hạn số phiên giữ. Không chốt lời cố định.

### 3.5 Thống kê theo lệnh
- Mỗi mã giữ tối đa một lệnh. **Không có giới hạn slot, không có vốn chung.** Mỗi lệnh là một quan sát.
- **Lãi ròng lệnh `i`:** `r_i = compute_stock_net_return(E, giá bán)`.
- **EW cùng thời gian:**
  - Universe `U_i` là các mã khám phá có `LIQ(phiên mua)` đúng, kể cả chính mã đó.
  - Với mỗi `s ∈ U_i`, `P_s(τ)` là open nến 1 giờ của `s` có `ts == τ`. Nếu không có nến đó thì dùng close nến 1 giờ gần nhất **trước** `τ`. Nếu `s` không có nến nào trước giờ mua thì bỏ `s`.
  - Với lệnh `END`, giá cuối của `s` là close nến 1 giờ cuối cùng của `s` tới hết 07/08.
  - `EW_i = trung bình_s [P_s(giờ bán) / P_s(giờ mua) − 1]`. Đây là EW **gộp**, không phí, giống đợt 193/194.
- **Vượt trội:** `X_i = r_i − EW_i`.
- **Thống kê một cấu hình:**
  - `n` là số lệnh; `mean_X`; `sharpe_X = mean_X / sd_X` với `ddof = 1`;
  - **p một phía:** `bootstrap_by_month(by_week, n=10000, seed=195, ci_low_pct=2.5, ci_high_pct=97.5)["p"]`, trong đó `by_week[(năm ISO, tuần ISO) của phiên mua] = [X_i …]`;
  - `mean_r`, tỷ lệ thắng (`r_i > 0`), trung vị số nến 1 giờ giữ, trung vị số phiên giữ, số lệnh theo lý do `STOP` / `TREND` / `END`, `mean_EW`.
- **Chuỗi tuần cho Bước 4:** `X_w` là trung bình `X_i` của các lệnh mua trong tuần `w`. Tính `sharpe_w = mean / sd` với `ddof = 1`, số tuần, `skew` và `kurt` Pearson (`scipy.stats.skew` và `kurtosis(fisher=False)`, cả hai `bias=True`).
- **Sổ thử:**
  - Dùng `evaluate_and_log` với `ledger_path="docs/research/dot195/trial_ledger.csv"`, `market="stock"`, `period="EA"`.
  - `metrics = {"n": n, "mean_net": mean_X, "sharpe": sharpe_X, "p": p}`. Không truyền `cagr`, `mdd`, `calmar`; hàm tự ghi 0.
- **An toàn sổ:** `run_exploration` gọi `assert_ledger_safety(ledger_path)` **ở dòng đầu tiên**.

### 3.6 Lưới (đăng ký trước, 8 cấu hình)

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `n` | {50, 100} | SMA ngày của xu hướng |
| `θ` | {30, 40} | ngưỡng RSI(14) 1 giờ cắt lên |
| `k` | {2, 3} | hệ số ATR(14) ngày của dừng kéo theo |

`idea_id = "I1_DMA_RSI1H_ATR"`. Thứ tự ghi sổ: `n`, rồi `θ`, rồi `k`, mỗi tham số tăng dần.

## 4. Việc 1: hạ tầng (TDD trên dữ liệu tổng hợp trong `tmp_path`)

**Tiêu chí xong:**
- `uv run pytest tests/test_research195_*.py -q` xanh. **Ghi danh sách `def test_` và số lượng đúng.** Claude sẽ tự đếm.
- **Test tính tay `simulate_trades`** (hàm mô phỏng lệnh của §3.3–3.5): 2–3 mã. Phải đi qua đủ:
  - lệnh `STOP`, `TREND` và `END`;
  - một lệnh mà tín hiệu bán đến trước T+2 rồi khớp ở nến `13` của `e+2`;
  - một lần khoá sàn bị hoãn.

  Ghi `r_i`, `EW_i`, `X_i` từng lệnh vào chú thích của test, và assert cả ba.
- **Test `resample_1h`:** một ngày có nến 09:00–09:10, 11:25, 14:25, 14:45 và 14:55. Assert đủ 5 nhóm và OHLCV từng nhóm.
- **Test `TREND_D`:** ghi rõ phiên đầu tiên `TREND_D` đổi giá trị, và rằng close của chính phiên `t` không ảnh hưởng `TREND_D(t)`.
- **Mỗi phép phá dưới đây phải làm đỏ một test gọi đúng hàm sản phẩm.**
  - Test chỉ so hằng số, hoặc chỉ gọi helper bằng số cho sẵn trong khi luật nằm trong mô phỏng, thì **không tính**.
  - Đợt 194 có 6 biến thể sống vì bảng cũ thiếu nhánh. Bảng này phủ **mọi gạch đầu dòng của §3**.

| # | Phép phá | Test phải gọi |
|---|---|---|
| a1 | Nhóm `14` bỏ nến ATC 14:45, hoặc nến 14:30–14:55 thành nhóm riêng | `resample_1h` |
| a2 | Open/close nhóm lấy sai nến (không phải nến đầu/cuối) | `resample_1h` |
| b1 | `TREND_D(t)` dùng nến ngày của chính `t` | `simulate_trades` |
| b2 | Bỏ điều kiện `SMA_n(j) > SMA_n(j−1)` | `simulate_trades` hoặc hàm xu hướng |
| b3 | Bỏ yêu cầu `n + 1` nến | hàm xu hướng |
| c1 | RSI không cần cắt lên (chỉ `RSI(h) ≥ θ`) | `simulate_trades` |
| c2 | RSI reset mỗi ngày thay vì liên tục | `simulate_trades` |
| c3 | Bỏ yêu cầu nến thứ 30 | `simulate_trades` |
| d1 | Bỏ `is_liquid` | `simulate_trades` |
| d2 | Bỏ yêu cầu 60 nến ngày | `simulate_trades` |
| e1 | Mua lại mã đang giữ hoặc đang chờ bán | `simulate_trades` |
| e2 | Khớp mua ở close `h` thay vì open `h+1` | `simulate_trades` |
| e3 | Mua được khi mở cửa giá trần, hoặc khi volume nến khớp bằng 0 | `simulate_trades` |
| e4 | Mua qua một phiên bị ngừng (nến `h+1` không thuộc phiên kế tiếp) | `simulate_trades` |
| f1 | `H` dùng high thay close, hoặc bỏ `E` khỏi `max` | `simulate_trades` |
| f2 | `ATR_D` gồm nến ngày của phiên hiện tại | `simulate_trades` |
| f3 | Bỏ thoát `TREND` | `simulate_trades` |
| f4 | Ưu tiên `TREND` thay vì `STOP` khi cả hai đúng | `simulate_trades` |
| g1 | Bán ở close nến tín hiệu thay vì open nến sau | `simulate_trades` |
| g2 | T+2 cho bán từ open phiên `e+2` (bỏ luật nến `13`) | `simulate_trades` |
| g3 | T+2 tính theo ngày lịch thay vì chỉ số trong `S` | `simulate_trades` |
| h | Bán được khi khoá sàn | `simulate_trades` |
| i | Bỏ phí ở chiều mua, hoặc ở chiều bán (hai phép riêng) | `simulate_trades`, so `r_i` tính tay |
| j1 | `EW_i` dùng close ngày thay vì giá 1 giờ đúng giờ mua/bán | `simulate_trades` |
| j2 | `U_i` bỏ điều kiện `LIQ` | `simulate_trades` |
| k | Bootstrap theo từng lệnh thay vì theo tuần | hàm thống kê, so với `bootstrap_by_month` gọi thẳng trong test |
| m | `run_exploration` xoá sổ cũ hoặc bỏ `assert_ledger_safety` | `run_exploration` với `ledger_path` trong `tmp_path` |
| n | Bước 4 dùng `n_trials` thiếu `+ 27`, gọi `deflated_sharpe` sai tham số, hoặc dùng chuỗi lệnh thay vì chuỗi tuần | `compute_step4_dsr`, so với lời gọi `deflated_sharpe` viết thẳng trong test |

- **Không có cờ phá thử trong code sản phẩm.**
- Chạy `uv run pyright scripts/research195_*.py tests/test_research195_*.py` và ghi nguyên văn kết quả.

## 5. Việc 2: khám phá (sau khi Việc 1 xanh)

- **Bước 1:** chạy đủ 8 cấu hình trên toàn bộ 03/04 → 07/08/2026 và ghi sổ. Chọn cấu hình có `sharpe_X` cao nhất.
- **Bước 2: cao nguyên.** Mọi láng giềng ±1 bước (`get_parameter_neighbors`, ở đây 3 láng giềng) phải có `mean_X > 0` và `sharpe_X ≥ 50%` của cấu hình được chọn. Không đạt thì loại, **không** đổi đỉnh.
- **Bước 3:** cấu hình được chọn phải thoả **cả ba** điều kiện:
  - `mean_X > 0` và p một phía (bootstrap tuần) < 0,05;
  - `mean_r > 0`, tức lãi ròng tuyệt đối sau phí cũng dương;
  - **số lệnh ≥ 100**.
- **Bước 4: DSR** trên chuỗi tuần `X_w`.
  - Hàm riêng `compute_step4_dsr(sharpe_w, n_weeks, skew, kurt, week_sharpes)` gọi `deflated_sharpe(sr, n_obs, skew, kurt, n_trials=len(week_sharpes) + 27, sr_trials_var=var(week_sharpes, ddof=1))`. Hằng số `PRIOR_NEGATIVE_FAMILIES = 27`.
  - Đạt khi DSR ≥ 0,95. **Chỉ in DSR đã tính thật.** Dừng trước Bước 4 thì ghi "không tính".
- **Ứng viên:** tối đa 1. **0 ứng viên là kết quả hợp lệ.** Không nới bước nào.
- **Bảng của cấu hình chọn phải in:**
  - số lệnh, số tuần, `mean_X`, `sharpe_X`, p;
  - `mean_r`, `mean_EW`, tỷ lệ thắng;
  - trung vị số nến 1 giờ giữ và số phiên giữ;
  - `STOP` / `TREND` / `END`;
  - `sharpe_w`, DSR hoặc "không tính".
- **Bảng phụ cả 8 dòng**, chỉ để đọc: `mean_X`, `sharpe_X`, `mean_r`, số lệnh, trung vị phiên giữ.
- **Cấm:** chạy lại sau khi sửa luật, thêm bộ lọc, thêm ý tưởng, cắt bớt giai đoạn.

**`research195_validate.py`** (agent viết, Claude chạy):
- **CLI:** `--data-dir`, `--candidates`, `--candidates-sha`, `--part V1|V2`, `--first-session`, `--last-session`.
  - Sha lệch thì `return 2`. Thiếu file thì `return 3`.
  - **Không có cờ nào nới cổng.** Ngưỡng 100 lệnh, 0,05 và `mean_r > 0` là hằng số.
- Chạy đúng luật và tham số ghi trong `candidates.json`. In ĐẠT hoặc TRƯỢT theo §6.
- **Test, chỉ dùng dữ liệu tổng hợp trong `tmp_path`:**
  - sha sai thì `return 2`;
  - chuỗi mà một nhóm mã tăng đều trong ngày, có nhịp chỉnh 1 giờ làm RSI cắt lên, còn EW đi ngang, thì ĐẠT;
  - chuỗi mà mọi mã giảm đều thì TRƯỢT.
  - Được truyền ngưỡng số lệnh thấp hơn **qua tham số hàm** trong test, không qua CLI.

**Tiêu chí xong Việc 2:**
- `docs/research/dot195/` có đủ 3 file.
- Sổ có đúng 8 dòng EA.
- `uv run ruff check scripts/research195_*.py tests/test_research195_*.py` sạch.
- `uv run pytest -m "not integration" -q` không đỏ thêm. Ghi số passed trước và sau.

## 6. Cổng kiểm chứng (chốt hôm nay; Claude chạy một lần sau audit)

Ứng viên phải ĐẠT **cả V1 lẫn V2**, `α = 0,05`.

| Phần | Dữ liệu | Giai đoạn |
|---|---|---|
| **V1: mã chưa thấy** | các mã kiểm chứng; nến ngày từ 02/01/2025 để làm nóng | 03/04 → 07/08/2026 |
| **V2: giai đoạn sau** | toàn bộ mã; nến 1 giờ từ 03/04 để làm nóng RSI | lệnh mua từ 10/08 → 23/10/2026 |

- Mỗi phần phải có `mean_X > 0` với p < α, `mean_r > 0` và ≥ 100 lệnh.
- **V2 cần dữ liệu chưa có:** phải nạp lại nến 5 phút của khoảng 300 mã từ SSI cho 10/08 → 23/10. Việc này **ghi vào DB thật**, nên Claude xin chủ dự án duyệt trước khi chạy.
  - SSI chỉ giữ khoảng 4 tháng, nên dữ liệu từ 10/08 sẽ mất dần từ khoảng đầu tháng 12/2026.
  - Nếu có ứng viên, V2 phải chạy **trước 01/12/2026**.
- **Qua cổng:** chỉ được paper forward ≥ 3 tháng (spec E), và collector phải ghi nến 5 phút cho các mã liên quan. **Không có đường tới lệnh thật trong đợt này.**
- **Trượt:** đóng họ "MA + RSI + ATR" ở cả khung tuần/ngày lẫn ngày/1 giờ, ghi phép đo âm.

## 7. Báo cáo agent phải nộp

1. GitNexus: `context`/`impact` trước khi sửa và `detect-changes` sau khi sửa, chép nguyên văn phần tóm tắt.
2. Test:
   - danh sách `def test_` kèm **số lượng đếm được**, số passed trước và sau;
   - bảng phép phá: tên test bị đỏ **và hàm sản phẩm mà test đó gọi**;
   - kết quả pyright.
3. Số dòng sổ.
4. Bảng §5, bảng phụ 8 dòng, kết luận, sha256 của `candidates.json`.
5. **Chỉ chép số có trong file kết quả.**
6. Chỗ mơ hồ: lựa chọn nào ảnh hưởng tới kết quả mà brief chưa quy định thì **dừng và hỏi**.
7. Cam kết: không truy vấn DB, không gọi API, không đọc file ngoài `data/research195/explore/`, không chạy validator trên dữ liệu thật, không xoá sổ.

## 8. Claude làm

- **Trước khi giao (đã xong 25/10):** xuất `data/research195/explore/` kèm manifest và kiểm bằng loader.
  - 147 mã, 462.996 nến 5 phút, 0 mã lọt.
  - Kiểm khớp giá ngày–5 phút sau điều chỉnh và kẹp biên độ.
  - Universe: 128–143 mã đạt GTGD20 ≥ 1 tỷ.
- **Sau khi nhận báo cáo:**
  - tự đếm `def test_`;
  - chạy lại test và pyright, **tự viết phép phá** theo bảng §4 và các gạch đầu dòng §3;
  - chạy lại explore vào thư mục tạm rồi so sổ;
  - **đếm độc lập** danh sách lệnh, `r_i`, `EW_i` của cấu hình được chọn bằng code riêng;
  - commit, tức niêm phong `candidates.json`.
- **Nếu có ứng viên:**
  - ghi `docs/holdout-unlock-log.md` **trước**;
  - xuất V1 và chạy một lần;
  - xin duyệt nạp 5 phút 10/08 → 23/10, xuất V2 và chạy một lần;
  - lưu nguyên văn vào `logs/dot195-kiem-chung-<ngày>.log`.
- **Cuối cùng:** viết `docs/research/2026-10-dot-195-ket-qua-…md`, cập nhật memory, commit và push.

## 9. Giả định đã ghi (agent không đổi; thấy sai thì báo)

- **T+2:** cổ phiếu mua phiên `e` bán được từ phiên chiều `e+2`. Nếu thực tế bán được từ sáng `e+2` thì luật này bảo thủ hơn khoảng 2 giờ.
- **Khớp ở open nến 1 giờ:** open của nến 5 phút đầu nhóm. Nhóm `09` có thể bắt đầu bằng nến 09:00–09:10, là cửa sổ ATO, nếu dữ liệu có. Trượt giá 5 bps giữ như mọi đợt.
- **Nến 1 giờ có độ dài khác nhau:** nhóm `11` là 30 phút, nhóm `14` khoảng 30 phút cộng ATC. RSI coi mỗi nến là một bước, như mọi công cụ biểu đồ.
- **EW gộp so với chiến lược ròng:** thiên vị cho EW khoảng một lần phí mỗi lệnh. Đợt 193/194 cũng vậy.
