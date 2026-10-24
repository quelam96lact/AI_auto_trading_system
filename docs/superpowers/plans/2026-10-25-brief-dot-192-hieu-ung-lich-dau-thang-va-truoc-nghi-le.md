# Brief đợt 192: hiệu ứng lịch, gồm dịp đầu tháng và dịp trước kỳ nghỉ lễ (ĐĂNG KÝ TRƯỚC)

- Ngày: 25/10/2026. Spec: dòng H ngày 25/10/2026 trong `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`.
- **Vai trò:**
  - Claude giao việc, xuất dữ liệu, audit, commit, push và **chạy kiểm chứng**.
  - Agent viết code, tự kiểm chứng và chạy khám phá trên tập khám phá.
- **Agent KHÔNG được:**
  - commit hay push;
  - gọi API thật nào;
  - đọc `.env`;
  - **truy vấn DB** (cả đọc lẫn ghi);
  - mở bất kỳ file dữ liệu nào ngoài `data/research192/explore/`;
  - sửa `scripts/research188_*.py` hay `scripts/research191_*.py`. Chỉ được **import**.
- **Niêm phong:**
  - Tập kiểm chứng gồm hai phần:
    - các mã không thuộc tập khám phá, 2016–2022;
    - mọi mã từ 01/01/2023 trở đi.
  - Tập này **không tồn tại** trên máy agent. Agent không được tìm, suy ra hay tải về.
  - Giá 2023+ đã bị đợt 175/177/191 mở, nhưng chưa ai xét theo lịch. V2 mang cảnh báo đó.

## 0. Yêu cầu và cách hiểu (đọc trước; có gì sai thì dừng và báo)

- **Yêu cầu của chủ dự án:** "plan tiếp chiến lược khác giao agent".
- **Vì sao chọn họ này:**
  - 24 phép đo âm trước đều dùng tín hiệu giá, khối lượng, khối ngoại hoặc order flow.
  - Hiệu ứng lịch chưa từng được đo. Cơ chế của nó không phụ thuộc vào việc đoán giá:
    - **dòng tiền đầu tháng:** lương, quỹ và tiền gửi mới vào thị trường quanh ngày chuyển tháng;
    - **tâm lý trước kỳ nghỉ:** nhà đầu tư mua trước kỳ nghỉ, và rủi ro không giữ vị thế qua kỳ nghỉ được định giá lại sau đó.
- **Ý tưởng do Claude viết sẵn** (§3), agent **không thêm ý tưởng**. Hai ý tưởng × 9 cấu hình = **18 dòng EA**.
- **Rủi ro biết trước:** phí khứ hồi khoảng 0,76%, gồm phí 0,28% mỗi chiều, thuế bán 0,1% và trượt 5 bps mỗi chiều.
  - Hiệu ứng đầu tháng có 12 cửa sổ mỗi năm, tức khoảng 9%/năm chi phí trên phần vốn vào lệnh.
  - Mỗi cửa sổ cần lãi gộp trung bình lớn hơn khoảng 0,8% mới có cơ hội. Báo cáo phải in **lãi gộp trung bình mỗi lệnh** để thấy hiệu ứng có tồn tại trước phí hay không.
- **Không dùng:** học máy, tham số riêng cho từng mã, chọn mã theo kết quả. Chỉ mua (long-only).
- **Thiên lệch sống sót:** bắt buộc ghi trong mọi báo cáo, như đợt 191.

## 1. Dữ liệu agent được dùng (Claude xuất vào `data/research192/explore/`)

| File | Nội dung |
|---|---|
| `stocks_daily.csv.gz` | `symbol,date,open,high,low,close,volume`, giá đã điều chỉnh, từ 04/01/2016 (ngày đầu của `bars_daily`) tới 30/12/2022. Gồm các mã khám phá (`sha256('dot192\|'+mã).digest()[0] < 128`), đã loại `exclusions.txt` |
| `sessions.csv` | `date`, mọi phiên giao dịch của toàn thị trường (ngày có ≥ 100 mã có nến), 04/01/2016 → 30/12/2022. Chỉ có ngày, không có giá |
| `exchanges.csv` | `symbol,exchange` |
| `manifest.json` | Quy tắc chia mã, số dòng, min/max ngày, sha256 từng file. Cùng định dạng đợt 191 |

**Đọc dữ liệu:** dùng `load_stocks` và `load_exchanges` của `scripts/research191_data.py` (import, không sửa). `load_stocks` nhận `end` và `raise` khi thiếu manifest hoặc lệch sha. Riêng `sessions.csv` thì agent viết loader mới, cũng kiểm sha theo manifest.

## 2. Phạm vi file

- **Được tạo mới:**
  - `scripts/research192_core.py`
  - `scripts/research192_explore.py`
  - `scripts/research192_validate.py`
  - `tests/test_research192_*.py`
  - `docs/research/dot192/`, gồm `trial_ledger.csv`, `exploration_report.md`, `candidates.json`
- **Được import, không sửa:**
  - `scripts/research188_core.py`: `Trade`, `compute_stock_net_return`, `calculate_trade_metrics`, `simulate_portfolio`, `deflated_sharpe`.
  - `scripts/research188_ledger.py`: `evaluate_and_log`, với `ledger_path` mới.
  - `scripts/research191_data.py`: `load_stocks`, `load_exchanges`, `compute_file_sha256`.
  - `scripts/research191_exits.py`: `is_liquid`, `assert_ledger_safety`.
  - `trading/stock_study.py`: `bootstrap_by_month`, `limit_rate`.
  - Nếu một hàm không dùng lại được nguyên trạng thì **dừng và báo**, không chép rồi sửa.
- **KHÔNG đụng:** mọi file khác, `pyproject.toml`, `uv.lock`, DB.
- **GitNexus:**
  - Trước khi viết code: `context`/`impact` cho các symbol import ở trên.
  - Sau khi xong: `detect-changes --scope all`.
  - Dùng `node .gitnexus/run.cjs` hoặc `gitnexus`, **không npx**.

## 3. Luật (chốt; agent code đúng như dưới, không đổi)

### 3.1 Lịch
- `S` là danh sách phiên đọc từ `sessions.csv`. Mọi chỉ số phiên trong brief đều tính trên `S`, không tính trên nến của từng mã.
- **Phiên cuối tháng** `L(M)` là phiên cuối cùng trong S thuộc tháng M. **Phiên thứ j của tháng M+1** là phiên thứ j trong S thuộc tháng M+1.
- **Kỳ nghỉ:** giữa hai phiên liền nhau `h` và `a` trong S có ít nhất một ngày thứ Hai–thứ Sáu không phải phiên. Khi đó `h` là phiên trước kỳ nghỉ, `a` là phiên đầu tiên sau kỳ nghỉ. Cuối tuần thường không tính là kỳ nghỉ.

### 3.2 Hai ý tưởng (đăng ký trước)
- **I1 `TOM`, dịp đầu tháng:** mua ở close của phiên thứ `k` tính ngược từ cuối tháng (`k = 1` là `L(M)`), bán ở close của phiên thứ `m` của tháng sau.
  - Lưới: `k ∈ {1, 2, 3}` × `m ∈ {2, 3, 4}`.
- **I2 `PREHOL`, trước kỳ nghỉ:** mua ở close của phiên thứ `n` tính ngược từ `h` (`n = 1` là `h`), bán ở close của phiên thứ `q` tính từ `a` (`q = 1` là `a`).
  - Lưới: `n ∈ {2, 3, 4}` × `q ∈ {1, 2, 3}`.
  - Phải có `n ≥ 2` vì mua ở close `h` thì không bán kịp trước kỳ nghỉ.

### 3.3 Chọn mã và khớp lệnh (chung cho hai ý tưởng)
- Gọi `b` là phiên mua và `e` là phiên bán theo §3.2.
- **Ràng buộc T+2:** chỉ số của `e` trong S trừ chỉ số của `b` phải ≥ 2. Mọi cấu hình trong lưới đều thỏa. Viết `assert` trong code.
- **Universe tại `b`:** các mã có nến ở **phiên trước `b`** và GTGD trung bình 20 phiên tính **tới hết phiên trước `b`** ≥ 10 tỷ, theo `is_liquid`.
  - Lệnh mua ATC được đặt trước khi biết khối lượng phiên `b`, nên **không được** dùng dữ liệu của phiên `b` để chọn mã.
- **Chọn tối đa 10 mã** có GTGD20 lớn nhất, hoà thì xếp theo mã A→Z. `score` = GTGD20.
- **Mua** ở close phiên `b`. Bỏ mã nếu:
  - mã không có nến phiên `b`;
  - hoặc phiên `b` khoá trần: `high == low` và `close ≥ prev_close × (1 + limit_rate − 0,001)`.
- **Bán** ở close phiên `e`.
  - Nếu mã không có nến phiên `e`, hoặc phiên `e` khoá sàn (`high == low` và `close ≤ prev_close × (1 − limit_rate + 0,001)`), thì bán ở close của phiên kế tiếp có nến và không khoá sàn.
  - Hết dữ liệu thì đóng ở close cuối với lý do `END`.
- **Không có** cắt lỗ hay chốt lời. Đây là phép đo hiệu ứng lịch thuần.
- Lãi ròng tính bằng `compute_stock_net_return(entry, exit)`. Ghi thêm `gross_return`.
- Một mã không có hai lệnh chồng nhau trong **cùng một ý tưởng**. Cửa sổ sau mở khi lệnh trước của mã đó chưa đóng thì bỏ mã đó.

### 3.4 Baseline theo thời gian (viết mới trong `research192_core.py`)
- Câu hỏi của phép đo là: cửa sổ lịch có tốt hơn **một cửa sổ bất kỳ cùng độ dài** của cùng mã không. Baseline kiểu đợt 191, so cùng ngày giữa các mã, **không** trả lời câu này.
- `time_baseline_excess(trades, bars_by_symbol, sessions, period_start, period_end)`:
  - Với lệnh trên mã s, giữ `h` phiên S (từ `b` tới `e` thực tế), baseline là trung bình của `close[j+h]/close[j] − 1`.
  - `j` chạy qua mọi phiên S trong `[period_start, period_end]` mà s có nến ở cả `j` lẫn `j+h` và s đạt `is_liquid` ở phiên trước `j`.
  - `excess = net_return − baseline`. Phía lệnh là ròng, phía baseline là gộp, nên phép so bảo thủ.
  - Trả về `mean_excess` và `mean_excess_trim1pct`, tức trung bình sau khi bỏ 1% lệnh có excess cao nhất.
- Test bằng một bộ tổng hợp 2 mã, kết quả tính tay ghi trong chú thích.

### 3.5 Sổ thử
- Dùng `evaluate_and_log` với `ledger_path="docs/research/dot192/trial_ledger.csv"`.
- `run_exploration` gọi `assert_ledger_safety(LEDGER_PATH)` **ở dòng đầu tiên**. Sổ đã tồn tại thì dừng, kể cả khi sổ chỉ có dòng EA. Đây là bản sửa audit đợt 191; không được có nhánh "đọc lại sổ rồi chạy tiếp".

## 4. Việc 1: hạ tầng (TDD trên dữ liệu tổng hợp trong `tmp_path`)

**Tiêu chí xong:**
- `uv run pytest tests/test_research192_*.py -q` xanh.
- Mỗi phép phá dưới đây phải làm đỏ một test **gọi đúng hàm sản phẩm ghi trong ngoặc**.
  - Test chỉ so hàm hay hằng số tự định nghĩa trong test thì **không tính**. Đợt 188 (b)(g) và đợt 191 (i)(j) đều trượt vì lỗi này.
  - Ghi tên test bị đỏ.

| # | Phép phá | Test phải gọi |
|---|---|---|
| a | `L(M)` lấy ngày cuối tháng dương lịch thay cho phiên cuối trong S | hàm lịch TOM |
| b | Kỳ nghỉ tính cả cuối tuần thường, tức thứ Sáu → thứ Hai cũng thành kỳ nghỉ | hàm lịch PREHOL |
| c | Universe dùng GTGD20 tính tới hết phiên `b` thay cho phiên trước `b` | hàm sinh lệnh |
| d | Bỏ kiểm khoá trần ở phiên mua | hàm sinh lệnh |
| e | Bỏ dời bán khi phiên `e` khoá sàn | hàm sinh lệnh |
| f | Bỏ giới hạn 10 mã | hàm sinh lệnh |
| g | Baseline lấy `j` trên toàn bộ dữ liệu thay cho trong giai đoạn | `time_baseline_excess` |
| h | Baseline bỏ điều kiện thanh khoản | `time_baseline_excess` |
| i | `run_exploration` xoá sổ cũ trước khi chạy, hoặc bỏ `assert_ledger_safety` | `run_exploration` với `LEDGER_PATH` trỏ vào `tmp_path` |
| j | Cho bán khi `e − b = 1` (bỏ T+2) | hàm sinh lệnh, với một lịch tổng hợp mà cấu hình thử ép `e − b = 1` |

- **Không có cờ phá thử trong code sản phẩm.**

## 5. Việc 2: khám phá (sau khi Việc 1 xanh và Claude báo dữ liệu sẵn sàng)

- **Giai đoạn:**
  - EA: lệnh có `b` từ 04/01/2016 tới 31/12/2019.
  - EB: lệnh có `b` từ 01/01/2020 tới 30/12/2022.
  - Lệnh đóng sau mốc vẫn dùng dữ liệu ≤ 30/12/2022, còn mở thì `END`.
  - Không có nến trước 04/01/2016. Cửa sổ nào có `b` mà chưa đủ 20 phiên để tính GTGD20 thì tự rơi vì không mã nào đạt `is_liquid`. Đây là hệ quả của dữ liệu, không phải lỗi.
- **Bước 1:** chạy đủ 18 cấu hình trên EA và ghi sổ. Chọn cấu hình có Sharpe-mỗi-lệnh cao nhất **trong số cấu hình có n ≥ 100**. Ý tưởng không có cấu hình nào n ≥ 100 thì bị loại vì thiếu mẫu.
- **Bước 2: cao nguyên.** Mọi láng giềng ±1 bước trên **từng** tham số phải có lãi ròng TB > 0 và Sharpe ≥ 50% Sharpe của cấu hình chọn. Không đạt thì loại, **không** đổi đỉnh.
- **Bước 3:** chạy đúng cấu hình đó **một lần** trên EB, ghi sổ `period='EB'`. Đạt khi:
  - n ≥ 100;
  - lãi ròng TB > 0, p một phía < 0,05 (`bootstrap_by_month`, n = 2000, seed = 192);
  - Calmar ≥ 0,86 (`simulate_portfolio`, 100 triệu, 10 vị thế × 10%, tiền nhàn rỗi lãi 0%);
  - `mean_excess_trim1pct` > 0.
- **Bước 4: DSR** trên EA, `n_trials` = số dòng EA + **24**. Đạt khi DSR ≥ 0,95. **Chỉ in DSR đã tính thật**, ý tưởng dừng trước bước 4 ghi "không tính".
- **Ứng viên:** các ý tưởng qua đủ bốn bước, tối đa 2. **0 ứng viên là kết quả hợp lệ.** Không nới bước nào.
- **Mọi bảng EA/EB in:**
  - n, lãi **gộp** TB, lãi ròng TB, Sharpe, p, CAGR, MDD, Calmar, `mean_excess_trim1pct`;
  - số cửa sổ (sự kiện lịch) có ít nhất một lệnh;
  - số mã trung bình mỗi cửa sổ.
- **Cấm:** chạy EB lần hai, sửa luật sau khi thấy EB, thêm bộ lọc.

**`research192_validate.py`** (agent viết, Claude chạy):
- CLI: `--data-dir`, `--candidates`, `--candidates-sha`, `--part V1|V2`, `--start`, `--end`.
  - Sha lệch thì `return 2`. Thiếu file thì `return 3`.
- Gọi đúng luật và tham số trong `candidates.json`. In ĐẠT / TRƯỢT / THIẾU SỨC MẠNH theo §6.
- Test chỉ trên dữ liệu tổng hợp trong `tmp_path`:
  - chuỗi có hiệu ứng đầu tháng giả: luật mẫu phải ĐẠT;
  - chuỗi ngẫu nhiên: phải TRƯỢT;
  - sha sai: `return 2`.

**Tiêu chí xong Việc 2:**
- `docs/research/dot192/` có đủ 3 file. Sổ có đúng 18 dòng EA, cộng số ý tưởng tới bước 3.
- `uv run ruff check scripts/research192_*.py tests/test_research192_*.py` sạch.
- `uv run pytest -m "not integration" -q` không đỏ thêm; ghi số passed trước và sau.

## 6. Cổng kiểm chứng (chốt hôm nay; Claude chạy một lần sau audit)

k = số ứng viên, α = 0,05 / k. Mỗi ứng viên phải ĐẠT **cả V1 lẫn V2**.

| Phần | Dữ liệu |
|---|---|
| **V1: mã chưa thấy** | các mã kiểm chứng, `b` từ 04/01/2016 tới 30/12/2022 |
| **V2: giai đoạn sau** | toàn bộ mã, `b` từ 01/01/2023 tới 23/10/2026 |

- n ≥ 100. Dưới mức đó ghi **THIẾU SỨC MẠNH**.
- Lãi ròng TB > 0 với p một phía < α; Calmar ≥ 0,86; `mean_excess_trim1pct` > 0.
- **V2 thêm:** CAGR danh mục, với tiền nhàn rỗi lãi 0%, phải lớn hơn mốc ETF + tiền gửi cùng giai đoạn. Claude tính lại mốc tới 23/10/2026 **trước** khi chạy V2, theo memory `moc-chuan-etf-cong-tien-gui`.
- **Qua cổng:** paper forward ≥ 3 tháng hoặc ≥ 50 lệnh (spec E). **Không có đường tới lệnh thật trong đợt này.**
- **Trượt:** đóng họ hiệu ứng lịch, ghi phép đo âm.

## 7. Báo cáo agent phải nộp

1. GitNexus `context`/`impact` trước và `detect-changes` sau, nguyên văn phần tóm tắt.
2. Danh sách `def test_`, số passed trước và sau, bảng phép phá (a)–(j) kèm tên test bị đỏ **và hàm sản phẩm mà test đó gọi**.
3. Số dòng sổ theo ý tưởng và giai đoạn.
4. Bảng §5 của từng ý tưởng, ứng viên, sha256 của `candidates.json`.
5. **Chỉ chép số có trong file kết quả.** Con số không có trong `exploration_report.md` hay sổ thì không được đưa vào báo cáo (đợt 191 có một "DSR 0,999" không có nguồn).
6. Chỗ mơ hồ: lựa chọn nào ảnh hưởng tới kết quả mà brief chưa quy định thì **dừng và hỏi**.
7. Cam kết: không truy vấn DB, không gọi API, không đọc file ngoài `data/research192/explore/`, không chạy validator trên dữ liệu thật, không xoá sổ.

## 8. Claude làm

- **Trước:** xuất `data/research192/explore/` kèm manifest, kiểm bằng loader rồi báo agent.
- **Sau báo cáo:**
  - chạy lại test và các phép phá (a)–(j);
  - chạy lại explore vào thư mục tạm và so sổ;
  - **đếm độc lập** một ý tưởng trên EB;
  - commit, tức niêm phong `candidates.json`.
- **Nếu có ứng viên:**
  - ghi `docs/holdout-unlock-log.md` **trước**;
  - xuất tập kiểm chứng;
  - chạy V1 một lần, V2 một lần;
  - lưu nguyên văn vào `logs/dot192-kiem-chung-<ngày>.log`.
- Viết `docs/research/2026-10-dot-192-ket-qua-…md`, cập nhật memory, commit, push.
