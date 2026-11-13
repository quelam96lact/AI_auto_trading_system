# Brief đợt 227: sự kiện khối lượng đột biến + học máy lọc sự kiện (ĐĂNG KÝ TRƯỚC)

- **Ngày:** 13/11/2026.
- **Spec:** dòng H ngày 13/11/2026 (đợt 227) trong `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`. Giả thuyết thứ 3 của tháng 11.
- **Vai trò:**
  - Claude (Lead) giao việc, xuất dữ liệu, audit, commit, push và **chạy kiểm chứng**.
  - **Builder** viết code, tự kiểm chứng, và chạy khám phá **một lần** trên tập khám phá.
- **Builder KHÔNG được:**
  - commit hay push;
  - gọi API thật nào, đọc `.env`, đọc file token SDK;
  - **truy vấn DB**, cả đọc lẫn ghi;
  - mở bất kỳ file dữ liệu nào ngoài `data/research227/explore/`;
  - sửa bất kỳ file nào đã có. Chỉ được **tạo file mới** theo §2 và **import**;
  - chạy `scripts/sched.sh`, restart container, dùng `npx`.
- **Niêm phong:**
  - Tập kiểm chứng gồm các mã không thuộc tập khám phá (2016–2022) và mọi mã từ 01/01/2023.
  - Tập này **không tồn tại** trong thư mục dữ liệu của Builder. Không tìm, không suy ra, không tải về.
  - Giá 2023+ đã bị các đợt 175/177/191 mở. Chưa ai chạy luật của đợt này trên đó.

## 0. Yêu cầu và cách hiểu (đọc trước; thấy sai thì dừng và báo)

- **Yêu cầu của chủ dự án (13/11):** bỏ việc chỉ giao dịch 3 mã giá trị thấp; lọc các mã có tín hiệu, khối lượng giao dịch lớn, đột biến; áp dụng học máy/học sâu. Chủ dự án đã chọn: nến ngày, giữ vài ngày.
- **Cách Claude hiểu và chốt:**
  - "Khối lượng lớn": GTGD trung bình 20 phiên ≥ 5 tỷ đồng.
  - "Đột biến": khối lượng phiên `t` ≥ 2 lần trung bình 20 phiên trước, và phiên `t` tăng giá.
  - "Học máy": LightGBM hồi quy, chấm điểm từng sự kiện, chỉ mua sự kiện có dự báo vượt chi phí.
  - "Học sâu": **không đo ở đợt này**. Chỉ mở nếu LightGBM qua đủ cổng. Lý do: với khoảng 4.500 sự kiện, mạng học sâu dễ khớp nhiễu hơn cây quyết định; nếu mô hình đơn giản không thấy tín hiệu thì thêm mô hình phức tạp chỉ tăng số lần thử.
- **Trùng với các họ đã đóng:**
  - đợt 169 (LightGBM xếp hạng tháng, 11 đặc trưng giá/khối lượng): âm;
  - đợt 175 (Donchian), VCP, SEPA: có dùng khối lượng, âm hoặc trượt niêm phong;
  - đợt 173/177: chết vì lãi mỗi lệnh nhỏ hơn phí khứ hồi khoảng 0,76%.
- **Khác ở chỗ:** mẫu là **sự kiện** (ngày khối lượng đột biến), không phải mọi mã mỗi tháng; nhãn là lợi nhuận vượt thị trường sau 5 hoặc 10 phiên; có đối chứng B0 không dùng học máy để tách phần của sự kiện với phần của mô hình.
- **Ước lượng trước của Claude:** khả năng qua đủ cổng là **thấp** (28 phép đo âm). **0 ứng viên là kết quả hợp lệ.**
- **Một ý tưởng, 2 cấu hình (H=5, H=10).** Builder không thêm đặc trưng, mô hình, bộ lọc hay cấu hình.
- **Thiên lệch sống sót:** dữ liệu gần như không có mã huỷ niêm yết. Ghi cảnh báo trong báo cáo.

## 1. Dữ liệu (Claude đã xuất vào `data/research227/explore/`)

| File | Nội dung |
|---|---|
| `stocks_daily.csv.gz` | `symbol,date,open,high,low,close,volume`. Giá đã điều chỉnh, 04/01/2016 → 30/12/2022. 601 mã có `sha256('dot227\|'+mã).digest()[0] < 128`. Đã loại `exclusions.txt` và dòng có OHLC ≤ 0. sha256 `0d04ca36…` |
| `sessions.csv` | 1.752 phiên toàn thị trường |
| `exchanges.csv` | `symbol,exchange` |
| `manifest.json` | Cùng định dạng đợt 194 |

Đọc bằng `load_stocks`, `load_exchanges` (`scripts/research191_data.py`) và `load_sessions` (`scripts/research192_core.py`). Claude đã chạy thử cả ba trên thư mục này.

**Đếm trước của Claude (chỉ đếm sự kiện, không tính lợi nhuận):** theo định nghĩa §3.1 nhưng chưa xét điều kiện 5: 4.495 sự kiện; theo năm 2016→2022: 114, 385, 367, 429, 661, 1.445, 1.094. Số mã đạt GTGD20 ≥ 5 tỷ theo năm: 47, 72, 68, 73, 93, 185, 194. Số của Builder phải khớp (lệch thì dừng và báo).

## 2. Phạm vi file

- **Được tạo mới:**
  - `scripts/research227_core.py`, `scripts/research227_explore.py`, `scripts/research227_validate.py`
  - `tests/test_research227_*.py`
  - `docs/research/dot227/`: `trial_ledger.csv`, `exploration_report.md`, `candidates.json`
- **Được import, không sửa:**

| Module | Symbol |
|---|---|
| `scripts/research191_data.py` | `load_stocks`, `load_exchanges`, `StockDailyBar` |
| `scripts/research191_exits.py` | `is_floor_locked`, `assert_ledger_safety` |
| `scripts/research192_core.py` | `load_sessions` |
| `scripts/research193_core.py` | `get_rebalance_dates`, `ew_benchmark`, `calculate_rotation_metrics` |
| `scripts/research188_core.py` | `deflated_sharpe` |
| `scripts/research188_ledger.py` | `evaluate_and_log` |
| `trading/stock_study.py` | `entry_status` |
| `trading/paper_broker.py` | `FEE_RATE`, `SELL_TAX_RATE`, `SLIPPAGE_BPS` |

  - `lightgbm` và `scikit-learn` đã có trong nhóm `dev` của `pyproject.toml` (đợt 169). **Không sửa** `pyproject.toml`, `uv.lock`.
  - Hàm nào không dùng lại được nguyên trạng thì **dừng và báo**, không chép rồi sửa.
- **GitNexus:** trước khi viết code, chạy `node .gitnexus/run.cjs context <symbol> --repo .` cho các symbol import. `scripts/` không được index nên sẽ ra "not found"; khi đó đọc trực tiếp hàm và ghi lại chữ ký. Sau khi xong chạy `detect-changes --scope all`. **Không npx.**
- **Thư mục làm việc:** thư mục chính. Chỉ tạo file mới nên không ảnh hưởng job đang chạy.

## 3. Luật (chốt; code đúng như dưới, không đổi)

`S` là danh sách phiên. Mọi phép tính tại phiên `t` chỉ dùng nến của mã tới hết `t`, trừ hai đặc trưng thị trường ở §3.3.

### 3.1 Sự kiện (`find_events`)
Mã có sự kiện ở close `t` (chỉ số nến của mã) khi thoả cả năm:
1. `t ≥ 120` (đủ 120 nến trước `t`);
2. `GT20 = mean(close × volume)` của 20 nến `t−20 … t−1` ≥ `5e9` (`MIN_TURNOVER_227`);
3. `V20 = mean(volume)` của 20 nến `t−20 … t−1` > 0 và `volume[t] ≥ 2 × V20` (`VOL_MULT = 2.0`);
4. `close[t] > close[t−1]`;
5. `entry_status(bars, t, exchange) == "ok"` **và** nến `t+1` của mã rơi đúng vào phiên kế tiếp của phiên `t` trong `S`.

### 3.2 Lệnh của một sự kiện (`event_trade`)
- **Mua:** open nến `e = t+1`.
- **Bán:** open của nến đầu tiên của mã có ngày ≥ `S[i_e + H]`, với `i_e` là chỉ số phiên mua trong `S`. H ≥ 5 nên luôn thoả T+2.
- **Khoá sàn:** nến bán có `is_floor_locked(close nến trước, high, low, exchange)` đúng thì thử lại ở open nến sau.
- Hết dữ liệu trước khi bán được: lệnh không có nhãn (`None`), không vào tập huấn luyện. Trong mô phỏng thì đóng ở close nến cuối, lý do `END`.
- `gross = giá_bán / giá_mua − 1`.

### 3.3 Đặc trưng tại close `t` (15, cố định, giá trị thô, không xếp hạng)

| Tên | Định nghĩa |
|---|---|
| `vol_ratio` | `volume[t] / V20` |
| `log_gt20` | `ln(GT20)` |
| `ret_1` | `close[t]/close[t−1] − 1` |
| `ret_5`, `ret_20`, `ret_60` | `close[t]/close[t−k] − 1` |
| `dist_ma20`, `dist_ma50` | `close[t] / mean(close[t−k+1 … t]) − 1` |
| `dist_high_60` | `close[t] / max(close[t−59 … t]) − 1` |
| `vol_20` | độ lệch chuẩn (ddof=1) của log return ngày, 20 return kết thúc tại `t` |
| `range_t` | `(high[t] − low[t]) / close[t]` |
| `close_pos` | `(close[t] − low[t]) / (high[t] − low[t])`; bằng 0,5 nếu high = low |
| `gap_open` | `open[t]/close[t−1] − 1` |
| `events_20` | số phiên trong `t−20 … t−1` thoả điều kiện 2, 3, 4 của §3.1 cho chính mã đó |
| `mkt_ret_20` | trung bình đều của `close[d]/close[d−20 nến] − 1` trên mọi mã trong tập có GT20 ≥ 5 tỷ tại phiên `d = S`-ngày của `t` và có nến đúng ngày đó |
| `mkt_breadth` | tỷ lệ các mã như trên có `close > close nến trước` tại ngày đó |

Hai đặc trưng thị trường chỉ dùng nến có ngày ≤ ngày của `t`.

### 3.4 Nhãn
`y = gross − mkt`, với `mkt` = trung bình đều của `open[ngày bán]/open[ngày mua] − 1` trên mọi mã trong tập có GT20 ≥ 5 tỷ tại phiên trước ngày mua và có nến ở **cả hai** ngày. Ngày mua và ngày bán là của chính lệnh đó.

### 3.5 Mô hình và walk-forward (`train_and_score`)
- `lightgbm.LGBMRegressor`: `n_estimators=200`, `learning_rate=0.05`, `num_leaves=15`, `min_child_samples=50`, `subsample=0.8`, `subsample_freq=1`, `colsample_bytree=0.8`, `reg_lambda=1.0`, `random_state=42`, `deterministic=True`, `force_row_wise=True`, `n_jobs=1`, `verbose=-1`. Không early stopping, không dò tham số.
- **Năm thử Y ∈ {2019, 2020, 2021, 2022}.** Mô hình của năm Y huấn luyện trên mọi sự kiện có **ngày bán < phiên đầu tiên của năm Y** (purge) và có nhãn. Mỗi H có mô hình riêng. Mô hình giữ cố định cả năm.
- Điểm của sự kiện trong năm Y = dự báo của mô hình năm Y.
- **Ngưỡng mua:** điểm > `COST_RT = 2 × FEE_RATE + SELL_TAX_RATE + 2 × SLIPPAGE_BPS / 10_000` (import, không gõ số).

### 3.6 Mô phỏng danh mục (`simulate_event_portfolio`)
- Vốn đầu 100.000.000, `K = 10` slot. Bắt đầu ở phiên đầu tiên của 2019 với danh mục trống, kết thúc 30/12/2022.
- Mỗi phiên `d`, theo thứ tự: (1) bán các lệnh tới hạn ở open `d` theo §3.2; (2) mua các sự kiện có close ở phiên trước `d`.
- **Chọn sự kiện để mua:** bỏ mã đang giữ. Sắp theo thứ tự ưu tiên giảm dần, lấy cho tới khi hết slot trống. Mỗi lệnh mua bằng `min(tiền mặt, NAV close phiên trước / K)`.
  - **Biến thể ML:** chỉ sự kiện có điểm > `COST_RT`; ưu tiên theo điểm; hoà thì theo mã ABC.
  - **Biến thể B0 (đối chứng không học máy):** mọi sự kiện; ưu tiên theo `vol_ratio`; hoà thì theo mã ABC.
- **Phí:** mua trả `FEE_RATE` + trượt giá; bán trả `FEE_RATE` + `SELL_TAX_RATE` + trượt giá; trượt giá `SLIPPAGE_BPS` mỗi chiều, bất lợi cho mình. Khối lượng mua là số thực (không làm tròn lô), như đợt 194.
- **NAV** đánh giá theo close mỗi phiên; mã không có nến thì dùng close gần nhất. MDD tính trên NAV ngày.
- Cuối kỳ: lệnh còn mở đóng ở close phiên cuối, lý do `END`.
- **Thống kê tháng:** `R_m = NAV(L(m))/NAV(L(m−1)) − 1` cho 48 tháng 01/2019 → 12/2022 (`get_rebalance_dates`); `EW_m` từ `ew_benchmark(..., min_turnover=5e9)`; `X_m = R_m − EW_m`; thống kê bằng `calculate_rotation_metrics(seed=227)`.

### 3.7 Đối chứng nhãn xáo trộn
Chạy lại đúng biến thể ML với nhãn huấn luyện **xáo trộn trong từng năm lịch của ngày mua** (`numpy.random.default_rng(227)`). Nếu biến thể này qua cổng 1 của §5 thì đường ống có rò rỉ: **dừng, không in kết quả chính**, báo Lead.

## 4. Việc 1: hạ tầng (TDD trên dữ liệu tổng hợp trong `tmp_path`)

**Xong khi:** `uv run pytest tests/test_research227_*.py -q` xanh, và mỗi phép phá dưới đây làm đỏ một test **gọi đúng hàm sản phẩm ở cột cuối**. Test chỉ so hằng số hoặc hàm tự viết trong test thì không tính. Ghi tên test bị đỏ.

| # | Phép phá | Test phải gọi |
|---|---|---|
| a | `V20`/`GT20` tính gồm cả nến `t` | `find_events` |
| b | Bỏ điều kiện `close[t] > close[t−1]` | `find_events` |
| c | Bỏ điều kiện GT20 ≥ 5 tỷ | `find_events` |
| d | Mua được khi `entry_status != "ok"` | `find_events` |
| e | Một đặc trưng dùng nến `t+1` (thử với `ret_1` và `mkt_breadth`) | hàm tính đặc trưng: sửa mọi nến sau `t`, đặc trưng không đổi |
| f | Bỏ purge (sự kiện có ngày bán trong năm Y lọt vào tập huấn luyện năm Y) | `train_and_score`, khẳng định bằng danh sách sự kiện huấn luyện |
| g | Đổi nhãn của sự kiện năm ≥ Y làm đổi điểm năm Y | `train_and_score` |
| h | Bán ở phiên `i_e + H − 1` | `event_trade` |
| i | Bán được khi khoá sàn | `event_trade` |
| j | Ngưỡng mua là điểm > 0 thay vì > `COST_RT` | `simulate_event_portfolio` |
| k | Giữ quá 10 mã, hoặc mua lại mã đang giữ | `simulate_event_portfolio` |
| l1–l3 | Bỏ phí ở từng nhánh: mua / bán thường / bán `END` | `simulate_event_portfolio`, so với NAV cuối và tổng phí **tính tay** ghi trong test |
| m | MDD tính trên NAV tháng | `simulate_event_portfolio` |
| n | B0 ưu tiên theo điểm thay vì `vol_ratio` | `simulate_event_portfolio` |
| o | `run_exploration` bỏ `assert_ledger_safety` hoặc xoá sổ cũ | `run_exploration` với sổ trong `tmp_path` |

Thêm ba test không thuộc bảng phá:
- **Đối chứng dương:** dữ liệu tổng hợp mà lợi nhuận sau sự kiện tỷ lệ với `close_pos` cộng nhiễu nhỏ → biến thể ML có `mean_X` lớn hơn B0 rõ rệt.
- **Đối chứng âm:** cùng dữ liệu, nhãn xáo trộn → không hơn B0 (ngưỡng do Builder đặt, nêu lý do).
- **Tất định:** chạy hai lần cho điểm giống hệt.

Kiểm thử phá hoại: sao lưu file ra ngoài repo rồi sửa; cấm `git checkout/restore/stash`. Không có cờ phá thử trong code sản phẩm. Chạy `uv run python -m py_compile` cho các file mới.

## 5. Việc 2: khám phá (sau khi Việc 1 xanh và Lead chưa cần duyệt giữa chừng)

`run_exploration` gọi `assert_ledger_safety(ledger_path)` ở dòng đầu. Chạy **một lần**. Lỗi code buộc chạy lại thì báo cả hai lần và lỗi gì.

Thứ tự ghi sổ: `idea_id = "I1_VOLSPIKE_LGBM"`, H=5 rồi H=10; mỗi H ghi ba dòng `variant` = `ML`, `B0`, `SHUFFLE`.

**Cổng (một cấu hình H là ứng viên khi qua cả bảy):**
1. Biến thể ML: `mean_X > 0` và p một phía < **0,025** (Bonferroni 0,05/2).
2. Số lệnh đã đóng của ML ≥ 100.
3. Calmar danh mục ML ≥ 0,86.
4. Học máy có giá trị: chuỗi tháng `R_ML − R_B0` có trung bình > 0 và p một phía < 0,05 (cùng hàm bootstrap, `monthly_ew` thay bằng `R_B0`).
5. Lãi ròng mỗi lệnh trừ `mkt` của ML, sau khi bỏ 1% lệnh lãi nhất, có trung bình > 0.
6. Cấu hình H còn lại cũng có `mean_X > 0` ở biến thể ML (thay cho kiểm cao nguyên).
7. DSR ≥ 0,95: `deflated_sharpe(sharpe_X, 48, skew, kurt, n_trials=2 + 28, sr_trials_var=var([sharpe_X của hai H], ddof=1))`. Hằng số `PRIOR_NEGATIVE_FAMILIES = 28`. Chỉ in DSR đã tính thật.

Tối đa 1 ứng viên: nếu cả hai H qua thì chọn H có `sharpe_X` cao hơn. **Không nới cổng nào.**

**Báo cáo `exploration_report.md` phải in, cho từng H và từng biến thể:**
- số sự kiện theo năm, số sự kiện có nhãn, cỡ tập huấn luyện của từng năm thử;
- 48 tháng: `mean_X`, `sharpe_X`, p; `R` và `EW` trung bình tháng; CAGR, MDD, Calmar; CAGR của EW;
- số lệnh đóng, tỷ lệ thắng, lãi ròng TB mỗi lệnh, tỷ lệ vốn trong cổ phiếu TB, phí theo năm (% NAV bình quân);
- bảng theo năm 2019–2022 của `R`, `EW`, `X`;
- tương quan Spearman giữa điểm và nhãn thật trên từng năm thử (mô tả);
- độ quan trọng đặc trưng của mô hình năm 2022 (mô tả, không dùng để chọn lại);
- kết quả từng cổng, đạt hay không, kèm số;
- cảnh báo thiên lệch sống sót và đa so sánh;
- đối chiếu ước lượng trước của Claude ở §0.

`candidates.json`: danh sách ứng viên (có thể rỗng) kèm H và các số của bảy cổng.

`research227_validate.py`: hàm `run_validation(data_dir, model_train_dir, h, start, end)` chạy đúng đường ống ML và B0 trên một thư mục dữ liệu khác, với mô hình huấn luyện **chỉ** từ sự kiện của `model_train_dir`. Builder viết và test trên dữ liệu tổng hợp; **không chạy** trên dữ liệu thật. Lead chạy nếu có ứng viên.

## 6. Tiêu chí hoàn thành (bằng chứng gửi Lead)

1. Chữ ký các hàm import đã đọc.
2. Output `pytest tests/test_research227_*.py -q` và bảng phép phá a–o với tên test bị đỏ, chép nguyên văn dòng `FAILED`.
3. `uv run pytest -m "not integration" -q`: tổng pass/fail. `uv run ruff check scripts tests`.
4. Số sự kiện theo năm, so với số đếm trước ở §1.
5. Lệnh chạy khám phá và **output nguyên văn**.
6. `detect-changes --scope all`.
7. Một câu xác nhận: "Tôi không truy vấn DB và không mở file dữ liệu nào ngoài `data/research227/explore/`."
8. Mọi chỗ brief mơ hồ mà Builder phải tự diễn giải. Không im lặng chọn.
