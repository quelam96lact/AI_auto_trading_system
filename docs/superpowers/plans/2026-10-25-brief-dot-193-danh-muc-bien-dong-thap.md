# Brief đợt 193: danh mục biến động thấp, xoay vòng tháng (ĐĂNG KÝ TRƯỚC)

- **Ngày:** 25/10/2026.
- **Spec:** dòng H ngày 25/10/2026 (đợt 193) trong `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`.
- **Vai trò:**
  - Claude giao việc, xuất dữ liệu, audit, commit, push và **chạy kiểm chứng**.
  - Agent viết code, tự kiểm chứng và chạy khám phá trên tập khám phá.
- **Agent KHÔNG được:**
  - commit hay push;
  - gọi API thật nào;
  - đọc `.env`;
  - **truy vấn DB**, cả đọc lẫn ghi;
  - mở bất kỳ file dữ liệu nào ngoài `data/research193/explore/`;
  - sửa `scripts/research188_*.py`, `scripts/research191_*.py` hay `scripts/research192_*.py`. Chỉ được **import**.
- **Niêm phong:**
  - Tập kiểm chứng gồm:
    - các mã không thuộc tập khám phá trong 2016–2022;
    - mọi mã từ 01/01/2023 trở đi.
  - Tập này **không tồn tại** trên máy agent. Agent không được tìm, suy ra hay tải về.
  - Giá 2023+ đã bị các đợt 175/177/191 mở, nhưng chưa ai xếp hạng theo biến động. V2 mang cảnh báo đó.

## 0. Yêu cầu và cách hiểu (đọc trước; có gì sai thì dừng và báo)

- **Yêu cầu của chủ dự án:** "plan tiếp chiến lược khác giao agent".
- **Vì sao chọn họ này:**
  - 25 phép đo âm trước đều là lệnh **ngắn** (2–40 phiên) bắt một cú di chuyển giá. Đợt 173, 177 và 192 chết vì cú di chuyển nhỏ hơn phí khứ hồi khoảng 0,76%.
  - Họ này khác về bản chất. Danh mục **luôn đầy vốn**, mỗi tháng chỉ đổi phần mã rơi khỏi danh sách. Phí chỉ tính trên phần đổi, ước khoảng 20–30% danh mục mỗi tháng, tức khoảng 2%/năm thay vì 9%/năm như đợt 192.
- **Cơ chế:**
  - **Biến động thấp:** cổ phiếu ít biến động thường cho lãi điều chỉnh rủi ro cao hơn. Có hai lời giải thích:
    - nhà đầu tư bị giới hạn đòn bẩy nên mua quá giá cổ phiếu biến động cao;
    - nhà đầu tư cá nhân thích "xổ số".
  - **MAX:** mã từng có vài phiên tăng mạnh bị trả giá quá cao. Lý do là nhà đầu tư cá nhân chiếm áp đảo thanh khoản VN và thích các mã như vậy.
- **Ý tưởng do Claude viết sẵn** (§3). Agent **không thêm ý tưởng**. Hai ý tưởng × 9 cấu hình = **18 dòng EA**.
- **Không dùng:** học máy, tham số riêng cho từng mã, đòn bẩy, bán khống. Chỉ mua (long-only).
- **Thiên lệch sống sót:** dữ liệu gần như không có mã huỷ niêm yết.
  - Mã huỷ thường là mã biến động cao và lỗ nặng. Khi thiếu chúng, nhóm biến động cao trông **tốt hơn thật**, nên phép so đang **bất lợi** cho chiến lược.
  - Vẫn phải ghi cảnh báo trong mọi báo cáo.
- **Đây là phép đo theo tháng, không phải theo lệnh:**
  - Đơn vị thống kê là **lợi nhuận vượt trội tháng** của danh mục. EA có 35 tháng, EB có 36 tháng.
  - Không có ngưỡng n ≥ 100 lệnh. Sức mạnh thống kê thấp hơn các đợt trước. Đó là điều đã biết, không phải lý do để nới cổng.

## 1. Dữ liệu agent được dùng (Claude xuất vào `data/research193/explore/`)

| File | Nội dung |
|---|---|
| `stocks_daily.csv.gz` | `symbol,date,open,high,low,close,volume`. Giá đã điều chỉnh, 04/01/2016 → 30/12/2022. Gồm các mã khám phá, tức `sha256('dot193\|'+mã).digest()[0] < 128`. Đã loại `exclusions.txt` |
| `sessions.csv` | `date`: mọi phiên toàn thị trường (ngày có ≥ 100 mã có nến), 04/01/2016 → 30/12/2022 |
| `exchanges.csv` | `symbol,exchange` |
| `manifest.json` | Cùng định dạng đợt 192 |

**Đọc dữ liệu:** dùng `load_stocks` và `load_exchanges` của `scripts/research191_data.py`, cùng `load_sessions` của `scripts/research192_core.py`. Cả ba chỉ import, không sửa.

## 2. Phạm vi file

- **Được tạo mới:**
  - `scripts/research193_core.py`
  - `scripts/research193_explore.py`
  - `scripts/research193_validate.py`
  - `tests/test_research193_*.py`
  - `docs/research/dot193/`, chứa `trial_ledger.csv`, `exploration_report.md`, `candidates.json`
- **Được import, không sửa:**
  - `scripts/research188_core.py`: `deflated_sharpe`.
  - `scripts/research188_ledger.py`: `evaluate_and_log`.
  - `scripts/research191_data.py`: `load_stocks`, `load_exchanges`.
  - `scripts/research191_exits.py`: `is_liquid`, `is_floor_locked`, `assert_ledger_safety`.
  - `scripts/research192_core.py`: `load_sessions`.
  - `trading/stock_study.py`: `bootstrap_by_month`, `limit_rate`.
  - `trading/paper_broker.py`: `FEE_RATE`, `SELL_TAX_RATE`, `SLIPPAGE_BPS`.
  - Nếu một hàm không dùng lại được nguyên trạng thì **dừng và báo**, không chép rồi sửa.
  - **Không dùng** `simulate_portfolio` hay `Trade` của đợt 188. Chúng mô hình hoá lệnh rời 10 slot, không phải danh mục xoay vòng. Mô phỏng danh mục viết mới trong `research193_core.py`, theo §3.4.
- **KHÔNG đụng:** mọi file khác, `pyproject.toml`, `uv.lock`, DB.
- **GitNexus:**
  - Trước khi viết code, chạy `context`/`impact` cho các symbol import ở trên.
  - Sau khi xong, chạy `detect-changes --scope all`.
  - Dùng `node .gitnexus/run.cjs` hoặc `gitnexus`, **không npx**.

## 3. Luật (chốt; agent code đúng như dưới, không đổi)

### 3.1 Lịch xoay vòng
- `S` là danh sách phiên lấy từ `sessions.csv`. `L(M)` là phiên cuối cùng trong S thuộc tháng M.
- **Phiên xoay vòng** `r = L(M)`. Mua và bán đều khớp ở close của `r`, như lệnh ATC.
- **Dữ liệu dùng để xếp hạng** chỉ tính tới hết phiên **trước** `r` trong S, gọi là `r⁻`. Lệnh ATC được đặt trước khi biết giá đóng cửa của `r`.

### 3.2 Universe tại `r`
Một mã thuộc universe tại `r` khi thoả cả hai điều kiện:
- có nến ở `r⁻`, và đạt `is_liquid(bars, t, min_turnover=1e9)` ở `r⁻`, tức **GTGD20 ≥ 1 tỷ**. Hằng số này đặt trong code là `MIN_TURNOVER_193 = 1e9`;
- có **ít nhất `L + 1` nến** tính tới `r⁻`, với `L` là cửa sổ của cấu hình. Thiếu nến thì không xếp hạng được và bị loại.

**Vì sao ngưỡng là 1 tỷ, không phải 10 tỷ như đợt 191/192.** Claude đếm cỡ universe trên tập khám phá **trước khi giao việc**. Phép đếm chỉ đếm số mã, không xem giá hay lãi lỗ. Với `L = 250`:

| Phiên | ≥ 10 tỷ | ≥ 5 tỷ | ≥ 1 tỷ |
|---|---|---|---|
| `L(01/2017)` | 9 | 19 | 51 |
| `L(06/2018)` | 22 | 32 | 68 |
| `L(12/2019)` | 20 | 36 | 84 |
| `L(12/2022)` | 72 | 95 | 152 |

- **Ở ngưỡng 10 tỷ**, câu "giữ 20 mã biến động thấp nhất" gần như là mua cả rổ, nên phép đo vô nghĩa.
- **Ở ngưỡng 1 tỷ**, vị thế lớn nhất là 10 triệu (N = 10, vốn 100 triệu). Mức này chỉ bằng khoảng 1% GTGD của mã, nên trượt giá 5 bps vẫn hợp lý.
- **Lưới `N` là {10, 15, 20}**, không có 30. Như vậy ngay cả khi universe hẹp nhất (51 mã), danh mục chỉ chọn tối đa khoảng 40% số mã.

### 3.3 Hai ý tưởng (đăng ký trước)

Lợi nhuận ngày `ret_t = close_t / close_{t−1} − 1` tính trên **nến của chính mã đó**, liền nhau trong danh sách nến của mã.

**I1 `LOWVOL`:**
- Điểm = độ lệch chuẩn mẫu (ddof = 1) của `L` lợi nhuận ngày gần nhất, kết thúc ở `r⁻`.
- Giữ `N` mã có điểm **thấp nhất**. Hoà điểm thì xếp mã theo A→Z.
- Lưới: `L ∈ {60, 120, 250}` × `N ∈ {10, 15, 20}`.

**I2 `LOWMAX`:**
- Điểm = trung bình của **3 lợi nhuận ngày lớn nhất** trong `W` lợi nhuận ngày gần nhất, kết thúc ở `r⁻`.
- Giữ `N` mã có điểm **thấp nhất**. Hoà điểm thì xếp mã theo A→Z.
- Lưới: `W ∈ {20, 60, 120}` × `N ∈ {10, 15, 20}`. Với I2, `L` ở §3.2 chính là `W`.

**Áp dụng cho cả hai:** nếu universe có ít hơn `N` mã thì giữ hết số mã đang có. Phần tỷ trọng còn trống để tiền mặt, lãi 0%.

### 3.4 Mô phỏng danh mục (`simulate_rotation`, viết mới)

- **Vốn và tỷ trọng:**
  - Vốn đầu 100 triệu đồng.
  - Tỷ trọng mục tiêu mỗi mã là `1/N` của NAV tính tại close `r`, NAV này đánh giá **trước** giao dịch.
  - Không làm tròn lô 100 cổ: số cổ phiếu là số thực.
- **Mỗi phiên xoay vòng, xử lý bán trước rồi mới mua:**
  - **Bán:**
    - mã đang giữ mà không còn trong danh sách mới thì bán hết;
    - mã còn trong danh sách mà giá trị vượt mục tiêu thì bán phần vượt.
  - **Mua:**
    - mã mới vào danh sách thì mua tới mục tiêu;
    - mã còn trong danh sách mà giá trị thiếu so với mục tiêu thì mua phần thiếu.
    - Mua bị giới hạn bởi tiền mặt đang có. Không vay.
- **Khoá giá:**
  - Không **bán** được nếu `r` khoá sàn (`high == low` và `close ≤ prev_close × (1 − limit_rate + 0,001)`) hoặc mã không có nến ở `r`. Khi đó giữ nguyên vị thế tới phiên xoay vòng sau.
  - Không **mua** được nếu `r` khoá trần (`high == low` và `close ≥ prev_close × (1 + limit_rate − 0,001)`) hoặc mã không có nến ở `r`. Khi đó phần đó để tiền mặt tới phiên xoay vòng sau.
  - `prev_close` là close của nến liền trước **của chính mã đó**.
  - **Khoá sàn:** gọi `is_floor_locked(prev_close, high, low, exchange)` của `research191_exits.py`, không tự viết lại.
  - **Khoá trần:** chưa có hàm dùng chung. Viết **một** hàm `is_ceiling_locked` trong `research193_core.py` và dùng nó ở mọi chỗ.
- **Phí** tính trên **giá trị giao dịch**, theo hằng số của `paper_broker`:
  - mua: tiền mặt bị trừ `giá trị × (1 + FEE_RATE + SLIPPAGE_BPS/10⁴)`;
  - bán: tiền mặt được cộng `giá trị × (1 − FEE_RATE − SELL_TAX_RATE − SLIPPAGE_BPS/10⁴)`.
- **NAV mỗi phiên S** = tiền mặt + tổng `số cổ × close`. Mã không có nến ở một phiên thì dùng close gần nhất trước đó.
- **Kết thúc giai đoạn:**
  - Bán hết ở close phiên xoay vòng cuối, áp đúng luật khoá giá.
  - Mã không bán được thì định giá theo close cuối, **trừ phí bán**, rồi đóng sổ.
- **Đầu ra:**
  - NAV ngày;
  - lợi nhuận tháng `R_m = NAV(L(m)) / NAV(L(m−1)) − 1`;
  - turnover tháng = tổng giá trị mua và bán chia NAV;
  - tổng phí;
  - số mã giữ trung bình.
- **CAGR** tính từ NAV đầu và NAV cuối theo số ngày dương lịch / 365,25.
- **MDD** tính trên **NAV ngày**.
- **Calmar** = CAGR / MDD.

### 3.5 Baseline (`ew_benchmark`, viết mới)
- **EW tháng m:**
  - Mỗi tháng m lấy mọi mã thoả **§3.2 với `L = 20`** tại `L(m−1)`, tức chỉ xét thanh khoản.
  - Lợi nhuận EW tháng m = trung bình **gộp** của `close(L(m)) / close(L(m−1)) − 1` qua các mã có nến ở cả hai phiên.
  - Baseline không trừ phí, nên phép so bảo thủ với chiến lược.
- **Vượt trội tháng** `X_m = R_m − EW_m`. Đây là đại lượng thống kê chính.
- **Vì sao baseline là EW thanh khoản:** câu hỏi của đợt này là "xếp theo biến động có hơn mua đều mọi mã thanh khoản không", không phải "có hơn tiền gửi không". So với ETF + tiền gửi chỉ làm ở V2 (§6).

### 3.6 Giai đoạn
- **EA:**
  - Phiên xoay vòng đầu là `L(01/2017)`, áp dụng cho **mọi** cấu hình để cùng mốc. Lý do: `L = 250` cần khoảng một năm nến, và nến đầu tiên là 04/01/2016.
  - Phiên xoay vòng cuối là `L(12/2019)`, đồng thời là phiên bán hết.
  - Kết quả: 35 tháng `X_m`, từ 02/2017 tới 12/2019.
- **EB:**
  - Phiên xoay vòng đầu là `L(12/2019)`, cuối là `L(12/2022)` = 30/12/2022.
  - Kết quả: 36 tháng, từ 01/2020 tới 12/2022. Dữ liệu 2019 chỉ dùng làm lookback.

### 3.7 Thống kê
- Trên chuỗi `X_m` của một giai đoạn:
  - `mean_X` là trung bình;
  - `sharpe_X = mean_X / std(X, ddof=1)`, tính theo tháng, không nhân √12;
  - `skew` và `kurt` theo **Pearson**, phân phối chuẩn có `kurt = 3`. Công thức giống hệt `calculate_trade_metrics` của đợt 188.
- **p một phía:** `bootstrap_by_month({(y,m): [X_m]}, n=2000, seed=193, ci_low_pct=0.05, ci_high_pct=0.95)["p"]`.
- **Sổ thử:**
  - Dùng `evaluate_and_log` với `ledger_path="docs/research/dot193/trial_ledger.csv"`.
  - Các trường ghi sổ: `n` = số tháng, `mean_net` = `mean_X`, `sharpe` = `sharpe_X`, `p`, cùng `cagr`, `mdd`, `calmar` của danh mục.
- **An toàn sổ:** `run_exploration` gọi `assert_ledger_safety(LEDGER_PATH)` **ở dòng đầu tiên**. Không có nhánh "đọc lại sổ rồi chạy tiếp".

## 4. Việc 1: hạ tầng (TDD trên dữ liệu tổng hợp trong `tmp_path`)

**Tiêu chí xong:**
- `uv run pytest tests/test_research193_*.py -q` xanh.
- `simulate_rotation` có test **tính tay**: 3 mã, 3 phiên xoay vòng, có một lần đổi mã. NAV, phí và turnover ghi trong chú thích của test.
- `ew_benchmark` có test tính tay trên 3 mã, 2 tháng.
- Mỗi phép phá dưới đây phải làm đỏ một test **gọi đúng hàm sản phẩm ghi trong cột cuối**.
  - Test chỉ so hằng số hay hàm tự định nghĩa trong test thì **không tính**. Đợt 188 (b)(g) và đợt 191 (i)(j) đã trượt vì lỗi này.
  - Ghi tên test bị đỏ.

| # | Phép phá | Test phải gọi |
|---|---|---|
| a | Điểm xếp hạng tính tới hết `r` thay vì `r⁻` | hàm chọn mã |
| b | Giữ `N` mã điểm **cao** nhất thay vì thấp nhất | hàm chọn mã |
| c | Bỏ điều kiện `is_liquid` của universe | hàm chọn mã |
| d | Mua được khi `r` khoá trần | `simulate_rotation` |
| e | Bán được khi `r` khoá sàn | `simulate_rotation` |
| f | Phí tính trên NAV thay vì trên giá trị giao dịch, hoặc bỏ phí phần điều chỉnh tỷ trọng | `simulate_rotation`, so với số tính tay |
| g | MDD tính trên NAV tháng thay vì NAV ngày | `simulate_rotation`, với một chuỗi sụt giữa tháng rồi hồi |
| h | `LOWMAX` lấy 1 lợi nhuận lớn nhất thay vì trung bình 3 | hàm điểm `LOWMAX` |
| i | `run_exploration` xoá sổ cũ hoặc bỏ `assert_ledger_safety` | `run_exploration` với `ledger_path` trong `tmp_path` |
| j | Bước 4 dùng `n_trials` thiếu `+ 25`, hoặc gọi `deflated_sharpe` sai tham số | **hàm Bước 4 của `research193_explore.py`**, chạy thật tới lệnh gọi `deflated_sharpe` trên dữ liệu tổng hợp |

- **Bài học đợt 192 về (j):** đợt trước có lời gọi `deflated_sharpe` sai chữ ký nằm trong nhánh không test nào chạy tới. Lần này Bước 4 phải tách thành hàm riêng, có test gọi tới, và kết quả so với một lời gọi `deflated_sharpe` viết trực tiếp trong test.
- **Không có cờ phá thử trong code sản phẩm.**
- Chạy thêm `uv run pyright scripts/research193_*.py` nếu có pyright. Không có thì dùng `uv run python -m py_compile`. Ghi nguyên văn kết quả vào báo cáo.

## 5. Việc 2: khám phá (sau khi Việc 1 xanh và Claude báo dữ liệu sẵn sàng)

- **Bước 1:** chạy đủ 18 cấu hình trên EA và ghi sổ. Với mỗi ý tưởng, chọn cấu hình có `sharpe_X` cao nhất.
- **Bước 2: cao nguyên.** Mọi láng giềng ±1 bước trên **từng** tham số phải có `mean_X > 0` và `sharpe_X ≥ 50%` của cấu hình được chọn. Không đạt thì loại, **không** đổi đỉnh.
- **Bước 3:** chạy đúng cấu hình đó **một lần** trên EB và ghi sổ với `period='EB'`. Đạt khi thoả cả ba:
  - `mean_X > 0` và p một phía < 0,05;
  - Calmar danh mục ≥ 0,86;
  - **trung bình số mã giữ ≥ 0,8 × N**, để chắc universe đủ rộng.
- **Bước 4: DSR** trên chuỗi `X_m` của EA.
  - Gọi `deflated_sharpe(sr=sharpe_X, n_obs=số tháng, skew, kurt, n_trials=số dòng EA + 25, sr_trials_var=var(sharpe_X của 18 dòng EA, ddof=1))`.
  - Đạt khi DSR ≥ 0,95.
  - **Chỉ in DSR đã tính thật.** Ý tưởng dừng trước Bước 4 thì ghi "không tính".
- **Ứng viên:** các ý tưởng qua đủ bốn bước, tối đa 2. **0 ứng viên là kết quả hợp lệ.** Không nới bước nào.
- **Mọi bảng EA và EB phải in:**
  - số tháng, `mean_X`, `sharpe_X`, p;
  - lợi nhuận tháng TB của chiến lược và của EW;
  - CAGR và MDD của danh mục, Calmar;
  - CAGR của EW, tính từ chuỗi EW_m;
  - turnover tháng TB, phí theo năm tính bằng % NAV, số mã giữ TB.
- **Cấm:** chạy EB lần hai, sửa luật sau khi thấy EB, thêm bộ lọc.

**`research193_validate.py`** (agent viết, Claude chạy):
- **CLI:** `--data-dir`, `--candidates`, `--candidates-sha`, `--part V1|V2`, `--first-rebalance`, `--last-rebalance`, `--hurdle-cagr`.
  - Sha lệch thì `return 2`. Thiếu file thì `return 3`.
- Gọi đúng luật và tham số ghi trong `candidates.json`. In ĐẠT hoặc TRƯỢT theo §6.
- **Test, chỉ dùng dữ liệu tổng hợp trong `tmp_path`:**
  - sha sai thì `return 2`;
  - chuỗi mà mã biến động thấp có lãi đều còn mã biến động cao đi ngang thì ĐẠT;
  - chuỗi mà mã biến động thấp lỗ đều thì TRƯỢT.
  - Đợt 192 thiếu đúng hai test cuối. Lần này bắt buộc có.

**Tiêu chí xong Việc 2:**
- `docs/research/dot193/` có đủ 3 file.
- Sổ có đúng 18 dòng EA, cộng thêm một dòng cho mỗi ý tưởng đi tới Bước 3.
- `uv run ruff check scripts/research193_*.py tests/test_research193_*.py` sạch.
- `uv run pytest -m "not integration" -q` không đỏ thêm. Ghi số passed trước và sau.

## 6. Cổng kiểm chứng (chốt hôm nay; Claude chạy một lần sau audit)

`k` = số ứng viên, `α = 0,05 / k`. Mỗi ứng viên phải ĐẠT **cả V1 lẫn V2**.

| Phần | Dữ liệu | Xoay vòng |
|---|---|---|
| **V1: mã chưa thấy** | các mã kiểm chứng, 2016–2022 | `L(01/2017)` → `L(12/2022)`, 71 tháng |
| **V2: giai đoạn sau** | toàn bộ mã, lookback lấy từ 2022 | `L(12/2022)` → `L(09/2026)`, 45 tháng |

- Mọi phần phải có `mean_X > 0` với p một phía < α, Calmar ≥ 0,86 và trung bình số mã giữ ≥ 0,8 × N.
- **V2 thêm một điều kiện:** CAGR danh mục phải **lớn hơn** mốc ETF + tiền gửi tính trên cùng giai đoạn. Trước khi chạy V2, Claude tính lại mốc tới `L(09/2026)` theo memory `moc-chuan-etf-cong-tien-gui` rồi truyền vào `--hurdle-cagr`.
- **Qua cổng:** chỉ được paper forward ≥ 3 tháng (spec E). **Không có đường tới lệnh thật trong đợt này.**
- **Trượt:** đóng họ biến động thấp, ghi phép đo âm.

## 7. Báo cáo agent phải nộp

1. GitNexus: `context`/`impact` trước khi sửa và `detect-changes` sau khi sửa, chép nguyên văn phần tóm tắt.
2. Test:
   - danh sách `def test_`, số passed trước và sau;
   - bảng phép phá (a)–(j), gồm tên test bị đỏ **và hàm sản phẩm mà test đó gọi**;
   - kết quả pyright hoặc `py_compile`.
3. Số dòng sổ theo ý tưởng và giai đoạn.
4. Bảng §5 của từng ý tưởng, danh sách ứng viên, sha256 của `candidates.json`.
5. **Chỉ chép số có trong file kết quả.** Con số không có trong `exploration_report.md` hay sổ thì không được đưa vào báo cáo.
6. Chỗ mơ hồ: lựa chọn nào ảnh hưởng tới kết quả mà brief chưa quy định thì **dừng và hỏi**.
7. Cam kết: không truy vấn DB, không gọi API, không đọc file ngoài `data/research193/explore/`, không chạy validator trên dữ liệu thật, không xoá sổ.

## 8. Claude làm

- **Trước khi giao:** xuất `data/research193/explore/` kèm manifest, kiểm bằng loader, rồi báo agent.
- **Sau khi nhận báo cáo:**
  - chạy lại test và các phép phá (a)–(j), cùng pyright;
  - chạy lại explore vào thư mục tạm rồi so sổ;
  - **đếm độc lập** NAV của một cấu hình trên EA bằng code riêng;
  - commit, tức niêm phong `candidates.json`.
- **Nếu có ứng viên:**
  - ghi `docs/holdout-unlock-log.md` **trước**;
  - xuất tập kiểm chứng;
  - chạy V1 một lần, V2 một lần;
  - lưu nguyên văn vào `logs/dot193-kiem-chung-<ngày>.log`.
- **Cuối cùng:** viết `docs/research/2026-10-dot-193-ket-qua-…md`, cập nhật memory, commit và push.
