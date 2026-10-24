# Brief đợt 191: khám phá chiến lược cổ phiếu từ dữ liệu khối ngoại, chốt lời tối thiểu +10% (ĐĂNG KÝ TRƯỚC)

- Ngày: 24/10/2026. Spec: dòng H ngày 24/10/2026 trong `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`.
- **Vai trò:**
  - Claude giao việc, xuất dữ liệu, audit, commit, push và **chạy kiểm chứng**.
  - Agent khác khám phá, viết code và tự kiểm chứng.
- **Agent KHÔNG được:**
  - commit hay push;
  - gọi API thật nào;
  - đọc `.env`;
  - **truy vấn DB** (cả đọc lẫn ghi);
  - mở bất kỳ file dữ liệu nào ngoài `data/research191/explore/`;
  - sửa file `scripts/research188_*.py`. Chỉ được **import**.
- **Niêm phong:**
  - Tập kiểm chứng gồm hai phần:
    - các mã không thuộc tập khám phá;
    - mọi mã từ 01/01/2023 trở đi.
  - Tập này **không tồn tại** trên máy agent dưới dạng file.
  - Agent không được tìm, suy ra hay tải về tập này.
  - Với họ khối ngoại, 2023+ chưa từng được mở. Giá 2023+ đã bị đợt 175/177 mở, nên V2 mang cảnh báo đó.

## 0. Yêu cầu và cách hiểu (đọc trước; có gì sai thì dừng và báo)

- **Yêu cầu của chủ dự án:** "chiến lược giao dịch khác căn cứ trên dữ liệu lịch sử giao dịch, tín hiệu sao cho có lời ít nhất 10% vị thế".
- **Cách hiểu đã chốt:** mỗi lệnh có mục tiêu chốt lời **tối thiểu +10%**, với lưới {10%, 15%, 20%}. Tín hiệu vào lệnh phải nhắm tới những đợt tăng đủ lớn để chạm mức đó.
  - **Không ai bảo đảm được mọi lệnh lãi 10%.** Lệnh chạm cắt lỗ vẫn lỗ.
  - Thước đo thành công vẫn là kỳ vọng ròng dương có ý nghĩa thống kê, vượt baseline cùng universe, và đạt Calmar, như đợt 188.
  - Báo cáo phải in thêm **tỷ lệ lệnh chạm chốt lời**.
- **"Khác":** đã có 23 phép đo âm, tất cả chỉ dùng giá và khối lượng. Ý tưởng ở đây **phải lấy dữ liệu khối ngoại làm điều kiện chính**. Lọc giá được phép, nhưng không được là lõi của tín hiệu.
- **Không dùng:** học máy, tham số riêng cho từng mã, chọn mã sau khi đã thấy kết quả. Một luật áp cho mọi mã. Chỉ mua (long-only).
- **Thiên lệch sống sót** bắt buộc ghi trong mọi báo cáo: `bars_daily` gần như không có mã đã huỷ; chủ dự án quyết định không dùng mã huỷ, spec H ngày 10/10. Chỉ so với baseline cùng universe.

## 1. Dữ liệu agent được dùng

Claude xuất vào `data/research191/explore/`. Thư mục này đã bị `.gitignore` bỏ qua qua dòng `/data/`.

| File | Nội dung |
|---|---|
| `stocks_daily.csv.gz` | `symbol,date,open,high,low,close,volume` (giá đã điều chỉnh từ `bars_daily`). Từ 01/06/2019, để có đủ warm-up, tới 30/12/2022. Mã khám phá, đã loại `exclusions.txt` |
| `foreign_flow.csv.gz` | `symbol,date,buy_vol,sell_vol,buy_val,sell_val,net_vol,net_val,current_room`, 26/02/2020 → 30/12/2022, cùng tập mã |
| `exchanges.csv` | `symbol,exchange` |
| `manifest.json` | Quy tắc chia (`sha256('dot191\|'+mã).digest()[0] < 128` là khám phá), số dòng, min/max ngày, sha256 từng file |

**Sự thật đã kiểm (Claude, 24/10):**
- Ngày 22/10/2026, `foreign_flow_daily` khớp fixture SSI từng trường, và `close_price` khớp `bars_daily` ở 173/173 mã.
- Lưu ý ba điểm:
  - `net_*` là số SSI trả. `net = buy − sell` đúng trên mọi dòng đã kiểm.
  - `*_val` tính bằng **VND theo giá chưa điều chỉnh**, còn giá trong `stocks_daily` **đã điều chỉnh**. Tỷ lệ phải dùng `net_val / GTGD`, trong đó GTGD = `close × volume` của `stocks_daily`. Không được ghép giá điều chỉnh với giá chưa điều chỉnh trong cùng phép tính mức giá.
  - Số khối ngoại của ngày t chỉ biết **sau phiên t**. Tín hiệu tính ở close t, khớp ở open t+1.
- `current_room` là số cổ phiếu còn được phép mua, không phải tỷ lệ. Không có tổng room để chia.

## 2. Phạm vi file

- **Được tạo mới:**
  - `scripts/research191_data.py`
  - `scripts/research191_exits.py`
  - `scripts/research191_ideas.py`
  - `scripts/research191_explore.py`
  - `scripts/research191_validate.py`
  - `tests/test_research191_*.py`
  - `docs/research/dot191/`, gồm `ideas.md`, `trial_ledger.csv`, `exploration_report.md`, `candidates.json`
- **Được import, không sửa:**
  - `scripts/research188_core.py`: `compute_stock_net_return`, `deflated_sharpe`, `calculate_trade_metrics`, `simulate_portfolio`, `Trade`. **Không** dùng `calculate_stock_baseline_excess`, vì hàm đó tính trên mọi mã khám phá chứ không theo universe thanh khoản; xem §3.3.
  - `scripts/research188_ledger.py`: `evaluate_and_log` và `compute_idea_sha`, với `ledger_path` mới.
  - `trading/stock_study.py`: `entry_status`, `bootstrap_by_month`, `limit_rate`.
  - `trading/paper_broker.py`: `FEE_RATE`, `SELL_TAX_RATE`, `SLIPPAGE_BPS`.
  - Nếu một hàm của 188 không dùng lại được nguyên trạng thì **dừng và báo**, không chép rồi sửa.
- **KHÔNG đụng:** mọi file khác, `pyproject.toml`, `uv.lock`, DB.
- **GitNexus:**
  - Trước khi viết code: `context`/`impact` cho các symbol sẽ import ở trên.
  - Sau khi xong: `detect-changes --scope all`.
  - Dùng `node .gitnexus/run.cjs` hoặc `gitnexus`, **không npx**.

## 3. Việc 1: hạ tầng (TDD, làm trước khi khám phá; dùng dữ liệu tổng hợp nên không cần chờ file thật)

### 3.1 `research191_data.py`
- `load_stocks(data_dir, end)` và `load_foreign_flow(data_dir, end)`:
  - kiểm sha256 theo `manifest.json`, lệch thì `raise`;
  - gặp dòng có ngày > `end` (mặc định 2022-12-31) thì `raise`, không lọc lặng lẽ;
  - không import `trading.storage`.
- `join_daily(stocks, flows)` trả về, theo từng mã, chuỗi ngày có giá. Ngày có giá mà không có dòng khối ngoại thì các trường khối ngoại là `None`, **không điền 0**.

### 3.2 `research191_exits.py`: luật thoát chung (chốt, mọi ý tưởng dùng chung)
- **Vào lệnh:** tín hiệu ở close t, khớp ở open t+1. Bỏ lệnh nếu `entry_status` khác `'ok'`.
- **Mức thoát** tính từ giá vào lệnh E:
  - chốt lời `TP = E × (1 + tp)`, với `tp ∈ {0.10, 0.15, 0.20}` (tham số của ý tưởng);
  - cắt lỗ `SL = E × (1 − 0.07)`, cố định;
  - giữ tối đa **60 phiên**, cố định. Hết hạn thì thoát ở open phiên kế tiếp.
- **T+2:** không bán trước phiên thứ 3 kể từ phiên khớp. Phiên khớp là phiên 1, nên phiên thứ 3 là phiên đầu tiên được bán. Phiên 1–2 bị bỏ qua khi xét chạm mức.
- **Từ phiên thứ 3**, xét theo thứ tự trong mỗi phiên:
  1. Open ≤ SL: thoát ở open. Open ≥ TP: thoát ở open.
  2. Low ≤ SL **và** high ≥ TP trong cùng phiên: coi như chạm **SL trước** (bảo thủ).
  3. Low ≤ SL: thoát ở SL. High ≥ TP: thoát ở TP.
- **Phiên khoá sàn** (high == low == giá sàn theo `limit_rate`) thì không bán được. Lệnh chuyển sang open phiên kế tiếp và giữ nguyên quy tắc.
- Lãi ròng tính bằng `compute_stock_net_return`, tức phí, thuế và trượt như đợt 188.
- Mỗi lệnh ghi lý do thoát: `TP`, `SL`, `TIME`, hoặc `END` khi hết dữ liệu (đóng ở close cuối).

### 3.3 Universe thanh khoản (chốt)
- Mã chỉ được vào lệnh ở ngày t nếu GTGD trung bình 20 phiên tới t ≥ **10 tỷ VND**, tính bằng `close × volume`. Lý do ở memory `ro-dang-chay-tuong-quan-cao`.
- **Baseline** viết mới trong `research191_exits.py`: `liquid_baseline_excess(trades, bars_by_symbol)`.
  - Với mỗi lệnh, baseline = lãi gộp bình quân đều, từ open phiên vào tới giá thoát cùng phiên ra, của mọi mã khám phá **đạt lọc GTGD ở ngày tín hiệu** và có nến ở cả hai phiên.
  - Hàm trả `mean_excess` và `mean_excess_trim1pct`, tức trung bình sau khi bỏ 1% lệnh có vượt trội cao nhất. Ý nghĩa giống hàm của 188.
  - Test bằng một bộ 3 mã tổng hợp, kết quả tính tay ghi trong chú thích. Mã không đạt lọc thanh khoản phải **không** vào baseline.

### 3.4 Sổ thử
- Dùng `evaluate_and_log` với `ledger_path="docs/research/dot191/trial_ledger.csv"`. Trần 400 dòng EA, và luật đổi `idea_sha` cần `idea_id` mới, đều đã có trong 188.
- **Không bao giờ xoá hay ghi đè sổ.** Nếu file đã tồn tại khi bắt đầu một lần chạy mới thì `raise SystemExit`. Đây là bản sửa của Claude ở đợt 188, `research188_explore.py`.

### Tiêu chí xong Việc 1
- `uv run pytest tests/test_research191_*.py -q` xanh.
- Mỗi phép phá sau phải làm đỏ **một test gọi code sản phẩm**. Test chỉ so hằng số viết trong test thì không tính (bài học đợt 188, (b)(g) tautology). Ghi tên test bị đỏ.
  - (a) Khớp ở close t thay cho open t+1.
  - (b) Bỏ T+2: cho bán từ phiên 2.
  - (c) Phiên chạm cả TP lẫn SL thì lấy TP.
  - (d) Thoát ở TP khi open đã vượt TP (đúng ra phải thoát ở open).
  - (e) Bỏ xử lý phiên khoá sàn.
  - (f) Điền 0 cho ngày thiếu khối ngoại thay cho `None`.
  - (g) Loader lọc lặng lẽ dòng quá mốc thay cho `raise`.
  - (h) Bỏ lọc GTGD ≥ 10 tỷ, ở luật vào lệnh hoặc ở baseline.
  - (i) Tín hiệu đọc khối ngoại của ngày t+1, tức nhìn trước.
  - (j) Explore xoá sổ thử cũ trước khi chạy.
- Test của (i) phải dùng chuỗi tổng hợp trong đó khối ngoại t+1 "báo trước" giá t+2. Luật đúng không được hưởng lợi từ chuỗi đó, còn bản bị phá thì có.
- **Không có cờ phá thử trong code sản phẩm.**

## 4. Việc 2: khám phá (chỉ sau khi Việc 1 xanh **và** Claude đã báo dữ liệu sẵn sàng)

### 4.1 Viết ý tưởng TRƯỚC khi chạy
`docs/research/dot191/ideas.md` gồm **≤ 6 ý tưởng**. Mỗi ý tưởng ghi:
1. Cơ chế kinh tế hoặc hành vi trong một câu. Ví dụ: tổ chức nước ngoài gom dần nên áp lực mua kéo dài; hoặc ngoại bán tháo theo dòng quỹ ETF chứ không theo cơ bản nên giá hồi.
2. Luật vào lệnh bằng lời, đủ rõ để người khác code lại. Luật thoát luôn là §3.2.
3. Vì sao điều kiện khối ngoại là lõi, và khác gì các họ đã âm.
4. ≤ 3 tham số tự do, **tính cả `tp`**, mỗi tham số ≤ 5 giá trị, và **lưới viết trước**.
5. Điểm ưu tiên khi danh mục đầy chỗ.

Gợi ý hướng, không bắt buộc:
- chuỗi mua ròng N phiên liên tiếp, có tổng `net_val / GTGD` vượt ngưỡng;
- xếp hạng cắt ngang `Σ net_val 20 phiên / Σ GTGD 20 phiên`, mua nhóm đầu;
- phân kỳ: giá giảm trong khi khối ngoại mua ròng;
- khối ngoại đảo chiều từ bán ròng kéo dài sang mua ròng;
- `current_room` giảm nhanh về gần 0, tức ngoại tranh mua phần room còn lại.

### 4.2 Quy trình chọn (chốt, không đổi giữa chừng)
- **Giai đoạn:**
  - EA = tín hiệu từ 01/03/2020 tới 30/06/2021;
  - EB = tín hiệu từ 01/07/2021 tới 30/12/2022.
  - Lệnh mở ở cuối giai đoạn được giữ theo luật thoát, nhưng chỉ dùng dữ liệu ≤ 30/12/2022. Lệnh còn mở lúc đó đóng ở close cuối với lý do `END`.
  - Warm-up được dùng dữ liệu trước mốc.
- **Bước 1.** Chạy toàn bộ lưới trên EA và ghi sổ mọi cấu hình. Chọn cấu hình có Sharpe-mỗi-lệnh cao nhất **trong số cấu hình có n ≥ 100**. Ý tưởng không có cấu hình nào n ≥ 100 thì bị loại vì thiếu mẫu.
- **Bước 2: cao nguyên.** Mọi láng giềng ±1 bước lưới trên **từng** tham số phải có lãi ròng trung bình > 0 và Sharpe ≥ 50% Sharpe của cấu hình được chọn. Không đạt thì loại, **không** đổi sang đỉnh khác.
- **Bước 3.** Chạy đúng cấu hình đó **một lần** trên EB, ghi sổ `period='EB'`. Đạt khi:
  - n ≥ 100;
  - lãi ròng trung bình > 0, p một phía < 0,05 (`bootstrap_by_month`, n = 2000, seed = 191);
  - Calmar ≥ 0,86 trên danh mục mô phỏng: 100 triệu, tối đa 10 vị thế × 10%, giống đợt 188;
  - vượt baseline sau khi bỏ 1% lệnh lãi nhất > 0.
- **Bước 4: DSR** trên EA, `n_trials` = số dòng EA trong sổ + **23**. Đạt khi DSR ≥ 0,95.
- **Ứng viên:** các ý tưởng qua cả bốn bước. Nếu nhiều hơn 3 thì lấy 3 cái có p trên EB nhỏ nhất. **0 ứng viên là kết quả hợp lệ.** Không nới bước nào.
- **Cấm:**
  - chạy EB lần hai cho cùng ý tưởng;
  - sửa ý tưởng sau khi thấy EB mà giữ `idea_id` cũ;
  - thêm bộ lọc sau khi thấy EB.
- **Mọi bảng EA/EB in thêm:** tỷ lệ lệnh thoát theo TP/SL/TIME/END, lãi ròng trung bình của lệnh TP và của lệnh SL, và số phiên giữ trung vị.

### 4.3 `research191_validate.py` (agent viết, Claude chạy)
- CLI: `--data-dir`, `--candidates docs/research/dot191/candidates.json`, `--candidates-sha <sha256>`, `--part V1|V2`, `--end YYYY-MM-DD`.
  - Sha lệch thì `return 2`. Thiếu file thì `return 3`.
- Gọi đúng hàm luật và tham số trong `candidates.json`, không tối ưu gì.
- In ĐẠT / TRƯỢT / THIẾU SỨC MẠNH cho từng ứng viên theo §5.
- Test chỉ trên dữ liệu tổng hợp trong `tmp_path`:
  - một chuỗi có hiệu ứng khối ngoại giả: luật mẫu phải ĐẠT;
  - một chuỗi ngẫu nhiên: phải TRƯỢT;
  - sha sai: `return 2`.

### Tiêu chí xong Việc 2
- `docs/research/dot191/` có đủ 4 file. Số dòng sổ khớp tổng lưới (EA) cộng số ý tưởng tới bước 3 (EB).
- `exploration_report.md` có bảng EA / cao nguyên / EB / DSR cho **mọi** ý tưởng kèm lý do loại, và câu cảnh báo thiên lệch sống sót.
- `uv run ruff check scripts/research191_*.py tests/test_research191_*.py` sạch.
- `uv run pytest -m "not integration" -q` không đỏ thêm; ghi số passed trước và sau.

## 5. Cổng kiểm chứng (chốt hôm nay; Claude chạy một lần sau audit)

k = số ứng viên, α = 0,05 / k. Mỗi ứng viên phải ĐẠT **cả V1 lẫn V2**.

| Phần | Dữ liệu |
|---|---|
| **V1: mã chưa thấy, cùng giai đoạn** | các mã kiểm chứng, tín hiệu 01/03/2020 → 30/12/2022 |
| **V2: giai đoạn sau** | toàn bộ mã, tín hiệu 01/01/2023 → 23/10/2026 |

**Cổng (mỗi phần):**
- n ≥ 100. Dưới mức đó ghi **THIẾU SỨC MẠNH**, và ứng viên không được coi là có lợi thế.
- Lãi ròng trung bình mỗi lệnh > 0, p một phía < α.
- Calmar ≥ 0,86.
- Vượt baseline cùng universe sau khi bỏ 1% lệnh lãi nhất > 0.
- **V2 thêm:** CAGR danh mục phải lớn hơn mốc ETF + tiền gửi cùng giai đoạn. Memory `moc-chuan-etf-cong-tien-gui` ghi niêm phong 2023 → 09/2026 là 8,30%/năm; Claude tính lại đúng tới 23/10/2026 **trước** khi chạy V2 và ghi vào log.

**Hệ quả:**
- Qua V1 + V2: paper forward ≥ 3 tháng hoặc ≥ 50 lệnh (spec E). **Không có đường tới lệnh thật trong đợt này.**
- Trượt: đóng ý tưởng, ghi phép đo âm.

## 6. Báo cáo agent phải nộp

1. GitNexus `context`/`impact` trước và `detect-changes` sau, nguyên văn phần tóm tắt.
2. Danh sách `def test_`, số passed trước/sau, bảng phép phá (a)–(j) kèm **tên test bị đỏ**.
3. `ideas.md` đúng như đã viết trước khi chạy.
4. Số dòng sổ thử theo ý tưởng và giai đoạn.
5. Bảng EA / cao nguyên / EB / DSR của từng ý tưởng, kèm các cột §4.2; ứng viên và sha256 của `candidates.json`.
6. Chỗ mơ hồ. Lựa chọn nào ảnh hưởng tới kết quả mà brief chưa quy định thì **dừng và hỏi**.
7. Cam kết: không truy vấn DB, không gọi API, không đọc file ngoài `data/research191/explore/`, không chạy validator trên dữ liệu thật, không sửa `research188_*`, không xoá sổ thử.

## 7. Claude làm

**Trước khi agent khám phá:**
- Khi nạp khối ngoại xong, kiểm:
  - số phiên mỗi năm;
  - số mã mỗi phiên;
  - phiên có số mã thấp bất thường;
  - tổng `bad_row` và `net_mismatch`.
- Xuất `data/research191/explore/` kèm manifest, rồi báo agent sẵn sàng.

**Sau báo cáo:**
1. **Audit:**
   - đối chiếu code với brief;
   - chạy lại test và các phép phá (a)–(j);
   - viết **phép đếm độc lập** số lệnh và lãi ròng cho ít nhất một ứng viên (hoặc ý tưởng tốt nhất nếu 0 ứng viên) trên EB, rồi đối chiếu;
   - kiểm sổ khớp lưới và `idea_sha` không đổi giữa EA và EB;
   - grep truy cập DB và đường dẫn ngoài thư mục khám phá.
2. Commit kết quả và sha của `candidates.json`. Commit này là niêm phong ứng viên.
3. Nếu có ứng viên:
   - ghi `docs/holdout-unlock-log.md` **trước**;
   - xuất tập kiểm chứng;
   - chạy V1 một lần, V2 một lần;
   - lưu nguyên văn vào `logs/dot191-kiem-chung-<ngày>.log`.
4. Viết `docs/research/2026-10-dot-191-ket-qua-…md`, cập nhật memory, commit, push.
