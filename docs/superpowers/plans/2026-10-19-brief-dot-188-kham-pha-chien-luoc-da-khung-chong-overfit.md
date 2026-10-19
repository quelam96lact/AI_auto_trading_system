# Brief đợt 188: khám phá chiến lược đa khung thời gian, có hàng rào chống overfit (ĐĂNG KÝ TRƯỚC)

- Ngày: 19/10/2026.
- **Vai trò:**
  - Claude: giao việc, audit, commit, push, và **chạy kiểm chứng**.
  - Agent khác: khám phá, viết code và tự kiểm chứng.
- **Agent KHÔNG được:**
  - commit hay push;
  - gọi API thật nào (SSI, DNSE, BingX, Binance);
  - đọc `.env`;
  - **truy vấn DB** (cả đọc lẫn ghi);
  - mở bất kỳ file dữ liệu nào ngoài `data/research188/explore/`.
- Nền: commit sau `634d97a`. Spec: dòng H ngày 19/10/2026 trong `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`.
- **Niêm phong:**
  - Tập kiểm chứng gồm hai phần:
    - các mã không có trong tập khám phá;
    - cổ phiếu từ 01/01/2023 trở đi, crypto từ 01/09/2026 trở đi.
  - Tập này **không tồn tại** trong máy của agent dưới dạng file.
  - Danh sách mã kiểm chứng chỉ Claude giữ.
  - Agent không được tìm, suy ra hay tải về tập này.

## 0. Bối cảnh: vì sao phải có hàng rào

Repo đã có **22 phép đo âm** liên tiếp: SMA, octopus, pullback 173, Donchian 175, RSI2 177, momentum, SEPA, VCP, SMC, vol targeting, ML xếp hạng 169, TSMOM forex, đặc trưng phi giá crypto, order flow 182/184/186/187. Xem memory `vn-regime-timing-overlay-loses-10-of-11-years`.

Đợt 175 là bài học trực tiếp: **qua IS nhưng trượt holdout**. Nếu agent được thử tự do hàng trăm biến thể rồi chọn cái đẹp nhất, gần như chắc chắn sẽ "tìm ra" một chiến lược lãi trên giấy. Lãi đó chỉ là may mắn khi chọn (overfitting).

Brief này cho agent **tự do sáng tạo**, nhưng ràng buộc bằng bốn hàng rào:

1. **Chia dữ liệu theo cả mã lẫn thời gian.** Agent chỉ thấy một nửa số mã và chỉ giai đoạn cũ.
2. **Sổ thử (trial ledger).** Mỗi cấu hình được chạy đều tự động ghi một dòng, không xoá được. Số dòng đi vào phép phạt đa so sánh (DSR).
3. **Ngân sách cứng:** ≤ 6 ý tưởng, ≤ 3 tham số tự do mỗi ý tưởng, ≤ 400 cấu hình tổng, ≤ 3 ứng viên.
4. **Kiểm chứng chạy đúng một lần, do Claude chạy,** với cổng chốt trong brief này (§6), trước khi có ứng viên.

## 1. Giả định và cách hiểu (đọc trước, có gì sai thì dừng và báo)

- **"Các khung, các sàn":** chỉ dùng hai thị trường có lịch sử đủ dài để làm đa khung:
  - **Cổ phiếu VN, nến ngày 2016–2022.** Ghép lên khung tuần và tháng. Mua dài hạn (long-only), vì cổ phiếu VN không bán khống được.
  - **Crypto perpetual BingX, nến 1h.** Ghép lên 4h và 1d. Được mua và bán khống (long/short).
- **Bị loại khỏi phạm vi:**
  - **Nến trong phiên VN (5m/15m/1h/4h, cổ phiếu và VN30F):** chỉ có từ 03/04/2026, khoảng 6,5 tháng, đã bị đợt 162/182/186/187 dùng. Không đủ cho cả khám phá lẫn kiểm chứng.
  - **Forex:** chỉ có 2–3 chuỗi nến ngày, và TSMOM forex đã âm (đợt 118).
- **"Hoàn toàn mới":** không lặp lại họ đã âm. Một họ cũ chỉ được dùng nếu yếu tố mới (đa khung) chính là giả thuyết. Ví dụ: "pullback ngày chỉ khi xu hướng **tuần** lên" được phép, nhưng phải ghi rõ khác đợt 173 ở đâu.
- **Không dùng:** học máy, tham số riêng cho từng mã, hay chọn mã sau khi đã thấy kết quả. Một luật áp cho mọi mã trong thị trường đó.
- Chi phí và khớp lệnh theo §4.3. Không có tranh cãi ở đây: dùng đúng hằng số đã ghi.

## 2. Dữ liệu agent được dùng

Claude đã xuất sẵn vào `data/research188/explore/`. Thư mục này bị `.gitignore` bỏ qua, không commit.

| File | Nội dung | Số dòng | sha256 |
|---|---|---|---|
| `stocks_daily.csv.gz` | `symbol,date,open,high,low,close,volume`; 593 mã có nến, 04/01/2016 → 30/12/2022, đã loại 246 mã trong `exclusions.txt` | 815.601 | `d896cd12…b3f9` |
| `crypto_1h.csv.gz` | `symbol,ts_utc,open,high,low,close,volume`; 15 coin, 27/04/2024 10:00 UTC → 31/08/2026 23:00 UTC | 308.370 | `1a1b0c9b…7d3a` |
| `exchanges.csv` | `symbol,exchange` (HOSE/HNX/UPCOM) cho mã cổ phiếu khám phá | | |
| `manifest.json` | Quy tắc chia, số dòng, min/max, sha256 đầy đủ | | |

- `ts` của nến 1h là **mốc bắt đầu** nến, theo UTC. Nến ngày cổ phiếu tính theo ngày VN.
- Cảnh báo bắt buộc trong mọi báo cáo cổ phiếu: thiên lệch sống sót (`bars_daily` gần như không có mã đã huỷ niêm yết; chủ dự án quyết định không dùng mã huỷ, spec H ngày 10/10). Vì vậy chỉ so với baseline cùng universe.

## 3. Phạm vi file

- **Được tạo mới:**
  - `scripts/research188_data.py`
  - `scripts/research188_core.py`
  - `scripts/research188_ledger.py`
  - `scripts/research188_ideas.py`
  - `scripts/research188_explore.py`
  - `scripts/research188_validate.py`
  - `tests/test_research188_*.py`
  - `docs/research/dot188/` gồm `ideas.md`, `trial_ledger.csv`, `exploration_report.md`, `candidates.json`
- **Được import (không sửa):** `trading/stock_study.py` (`entry_status`, `bootstrap_by_month`, `limit_rate`) và `trading/paper_broker.py` (`FEE_RATE`, `SELL_TAX_RATE`, `SLIPPAGE_BPS`).
- **KHÔNG đụng:**
  - mọi file khác trong `trading/`, `scripts/`, `tests/`;
  - `pyproject.toml`, `uv.lock` (không thêm thư viện; dùng thư viện chuẩn, numpy/pandas nếu đã có trong lock);
  - DB.
- **Working tree đang có thay đổi chưa commit, không phải của đợt này:** `scripts/bingx_klines.py`, `scripts/build_derivative_continuous_series.py`, `tests/test_build_derivative_continuous_series.py`, `trading/storage/db.py`, `trading/storage/schema.sql`, `scripts/resample_*.py`, `tests/test_resample_*.py`. **Không sửa, không stash, không checkout, không xoá chúng.** Nếu test của chúng đỏ thì báo lại, không sửa.
- **GitNexus:**
  - Trước khi viết code: chạy `context`/`impact` cho các symbol sẽ import (`entry_status`, `bootstrap_by_month`, `net_return`, `FEE_RATE`).
  - Sau khi xong: chạy `detect-changes --scope all`.
  - Dùng `node .gitnexus/run.cjs …` hoặc `gitnexus …`, **không dùng npx** (memory `gitnexus-lech-phien-ban`).

## 4. Việc 1: hạ tầng (TDD, làm trước khi khám phá)

### 4.1 `research188_data.py`: loader có chốt
- `load_stocks()` và `load_crypto()` chỉ đọc đúng các file ở §2.
  1. Kiểm sha256 so với `manifest.json`; lệch thì `raise`.
  2. Gặp dòng nào có ngày > mốc (cổ phiếu 2022-12-31, crypto 2026-08-31T23:00Z) thì `raise`, không lặng lẽ lọc.
- Hàm nhận đường dẫn thư mục làm tham số; mặc định là `data/research188/explore`. Validator (§5.3) gọi lại các hàm này với thư mục khác và mốc khác, nên mốc phải là **tham số**. Giá trị mặc định là mốc khám phá.
- Đọc từ DB hay gọi API là cấm. File này không được import `trading.storage`.

### 4.2 `research188_core.py`: đa khung không nhìn trước
Đây là lỗi số 1 của chiến lược đa khung: dùng nến khung lớn **chưa đóng**. Ví dụ nến tuần của tuần hiện tại, khi đang ở thứ Tư.

- **`resample(bars, rule)`:** gộp ngày → tuần (tuần kết thúc thứ Sáu theo lịch VN; tuần nghỉ lễ ngắn vẫn là một nến) và ngày → tháng. Với crypto: 1h → 4h (biên 00/04/08/12/16/20 UTC) và 1h → 1d (biên 00:00 UTC). Mỗi nến khung lớn mang `close_time`.
- **`align_higher(lower_bars, higher_bars)`:** với mỗi nến khung nhỏ t, trả về nến khung lớn **mới nhất có `close_time` ≤ thời điểm đóng của nến t**. Không có thì trả `None`.
- **Khớp lệnh:** tín hiệu tính ở close nến t, khớp ở **open nến t+1** của khung giao dịch.
  - Cổ phiếu: bỏ lệnh nếu `entry_status` khác `'ok'` (trần, khối lượng 0, hết nến).
  - Cổ phiếu: giữ **tối thiểu 3 phiên** (T+2). Thoát tại open phiên sau tín hiệu thoát, hoặc theo luật của ý tưởng.
- **Chỉ báo:** chỉ dùng dữ liệu tới nến t. Tự viết, hoặc dùng `rolling_*` có sẵn trong `stock_study` (cho phép import).

### 4.3 Chi phí (chốt, không đổi)
- **Cổ phiếu:** `net_return` của `stock_study`, tức `FEE_RATE` 0,28% mỗi chiều, thuế bán 0,1%, trượt 5 bps mỗi chiều.
- **Crypto:**
  - Phí taker 0,05% mỗi chiều (BingX VIP0) + trượt 0,02% mỗi chiều, tức **0,14% một vòng**.
  - Funding: trừ cố định **0,01% mỗi mốc 00/08/16 UTC** mà vị thế đi qua, tính cả lệnh mua lẫn lệnh bán khống. Đây là giả định bảo thủ vì repo chưa có dữ liệu funding.
- Hằng số crypto đặt trong `research188_core.py`, có chú thích nguồn (memory `bingx-fee-schedule`, `scripts/measure_forex_tsmom.py:47`).

### 4.4 Thước đo
Với mỗi cấu hình, đo:
- n lệnh;
- lãi ròng trung bình mỗi lệnh;
- Sharpe của chuỗi lãi ròng mỗi lệnh;
- p một phía của trung bình > 0 bằng `bootstrap_by_month` (n = 2000, seed = 188);
- **danh mục mô phỏng:**
  - Cổ phiếu: vốn 100 triệu, tối đa 10 vị thế, mỗi vị thế 10%. Khi đầy chỗ thì bỏ tín hiệu, thứ tự ưu tiên theo điểm tín hiệu do ý tưởng định nghĩa; hoà thì theo mã A→Z.
  - Crypto: tối đa 5 vị thế, mỗi vị thế 20%, đòn bẩy 1x.
  - Equity tính theo close ngày; báo CAGR, MDD và Calmar = CAGR / MDD.
- **Vượt baseline (chỉ cổ phiếu):** lãi ròng của lệnh trừ đi lãi gộp bình quân đều của mọi mã khám phá có nến trong cùng cửa sổ vào/ra. Báo trung bình, và trung bình sau khi bỏ 1% lệnh lãi nhất.

### 4.5 DSR (Deflated Sharpe Ratio)
- **`deflated_sharpe(sr, n_obs, skew, kurt, n_trials, sr_trials_var)`** theo Bailey & López de Prado (2014). Ngưỡng kỳ vọng tối đa dùng xấp xỉ Euler–Mascheroni (công thức 2 trong bài).
- Test với ít nhất hai bộ số tính tay, ghi bằng chú thích trong test:
  - n_trials = 1 thì DSR = PSR(0);
  - n_trials tăng thì DSR giảm đơn điệu.

### 4.6 `research188_ledger.py`: sổ thử
- **`evaluate_and_log(idea_id, params, market, period, metrics, ledger_path)`** ghi nối thêm (append) một dòng CSV. Các cột: `utc_ts, idea_id, idea_sha, market, period, params_json, n, mean_net, sharpe, p, cagr, mdd, calmar`.
  - `idea_sha` = sha256 của mã nguồn hàm luật của ý tưởng, lấy qua `inspect.getsource`.
- **`research188_explore.py` chỉ được đánh giá cấu hình qua hàm này.** Không có cờ nào bỏ qua việc ghi.
- **Ngân sách cứng:**
  - Số dòng có `period = 'EA'` vượt 400 thì `evaluate_and_log` `raise`.
  - Một `idea_id` đã chạy rồi mà đổi `idea_sha` (sửa luật hay lưới) thì phải đặt `idea_id` mới, và vẫn tính vào trần 6 ý tưởng. Hàm `raise` nếu thấy `idea_id` cũ đi kèm `idea_sha` mới.

### Tiêu chí xong Việc 1
`uv run pytest tests/test_research188_*.py -q` xanh. Đồng thời mỗi **phép phá** sau phải làm ít nhất một test đỏ (phá xong thì khôi phục, ghi lệnh và kết quả vào báo cáo):
- (a) `align_higher` dùng `close_time` ≥ thay cho ≤, hoặc lấy nến khung lớn đang hình thành;
- (b) khớp ở close t thay cho open t+1;
- (c) bỏ phí crypto, hoặc bỏ funding;
- (d) loader lọc lặng lẽ dòng quá mốc thay vì `raise`;
- (e) `evaluate_and_log` không ghi dòng;
- (f) bỏ chốt 400 hoặc bỏ chốt đổi `idea_sha`;
- (g) bỏ ràng buộc giữ ≥ 3 phiên với cổ phiếu;
- (h) DSR bỏ hiệu chỉnh n_trials.

**Không có cờ phá thử (mutation flag) trong code sản phẩm.**

## 5. Việc 2: khám phá (sau khi Việc 1 xanh)

### 5.1 Viết ý tưởng TRƯỚC khi chạy
`docs/research/dot188/ideas.md` gồm **≤ 6 ý tưởng**, trong đó ít nhất 4 dùng ≥ 2 khung thời gian. Mỗi ý tưởng ghi:
1. Cơ chế kinh tế hoặc hành vi giải thích **vì sao** nó có thể có lời sau phí: một câu, không phải "backtest thấy đẹp".
2. Luật vào/ra viết bằng lời, đủ rõ để người khác code lại được.
3. Khác gì với các họ đã âm (§0).
4. ≤ 3 tham số tự do, mỗi tham số ≤ 5 giá trị, và **lưới viết ra trước**.
5. Thị trường: cổ phiếu, crypto, hoặc cả hai. Nếu cả hai thì tính là hai ý tưởng trong sổ.

Gợi ý hướng (không bắt buộc):
- xu hướng khung lớn lọc điểm vào khung nhỏ;
- chế độ biến động khung lớn quyết định có giao dịch phá vỡ khung nhỏ hay không;
- đồng thuận nhiều khung;
- chênh lệch giữa khung (khung ngày quá bán trong khi khung tuần còn khoẻ).

### 5.2 Quy trình chọn (chốt, không đổi giữa chừng)
- **Chia tập khám phá:**

  | Thị trường | EA (chọn) | EB (kiểm trong tập khám phá) |
  |---|---|---|
  | Cổ phiếu | 2016–2019 | 2020–2022 |
  | Crypto | 27/04/2024 → 31/07/2025 | 01/08/2025 → 31/08/2026 |

  Chỉ báo được phép "khởi động" (warm-up) bằng dữ liệu trước mốc của giai đoạn, nhưng lệnh chỉ tính khi tín hiệu nằm trong giai đoạn.
- **Bước 1.** Chạy toàn bộ lưới của ý tưởng trên **EA**; mọi cấu hình đều ghi sổ. Chọn cấu hình có Sharpe-mỗi-lệnh cao nhất **trong số cấu hình có n ≥ 100**.
- **Bước 2: kiểm cao nguyên.** Mọi cấu hình láng giềng (±1 bước lưới trên **từng** tham số) phải có lãi ròng trung bình > 0 và Sharpe ≥ 50% Sharpe của cấu hình được chọn. Không đạt thì ý tưởng bị loại. **Không** được đổi sang đỉnh khác.
- **Bước 3.** Chạy đúng cấu hình đó **một lần** trên **EB** (ghi sổ với `period='EB'`). Đạt khi:
  - n ≥ 100;
  - lãi ròng trung bình > 0, p < 0,05;
  - Calmar ≥ 0,86 (= 6/7, spec §1);
  - cổ phiếu: vượt baseline sau khi bỏ 1% lệnh lãi nhất > 0;
  - crypto: lãi gộp trung bình mỗi lệnh ≥ 1,5 × chi phí vòng (spec B).
- **Bước 4: DSR.** Tính DSR của cấu hình được chọn trên **EA**, với `n_trials` = số dòng EA của **thị trường đó** trong sổ, cộng **22** (các phép đo âm trước). Đạt khi DSR ≥ 0,95.
- **Ứng viên** là các ý tưởng qua cả bốn bước. Nếu nhiều hơn 3 thì lấy 3 cái có p trên EB nhỏ nhất. **0 ứng viên là kết quả hợp lệ và phải báo đúng như vậy.** Không được nới bước nào để có ứng viên.
- **Cấm:**
  - chạy lại EB lần hai cho cùng ý tưởng;
  - nhìn EB rồi sửa ý tưởng mà giữ `idea_id` cũ;
  - thêm bộ lọc sau khi thấy kết quả EB. Nếu muốn thì đó là ý tưởng mới, tốn một suất.

### 5.3 `research188_validate.py` (agent viết, Claude chạy)
- CLI: `--data-dir`, `--candidates docs/research/dot188/candidates.json`, `--candidates-sha <sha256>`, `--part V1|V2`.
  - Sha lệch thì `return 2`, không chạy.
  - Thiếu file dữ liệu thì `return 3`.
- `candidates.json` cho mỗi ứng viên ghi: `idea_id`, `idea_sha`, `market`, `params`, và tên hàm luật trong `research188_ideas.py`. Validator gọi đúng hàm đó với đúng tham số, **không tối ưu gì cả**.
- Áp các cổng §6 và in bảng kết quả có kết luận ĐẠT/TRƯỢT/THIẾU SỨC MẠNH cho từng ứng viên.
- **Chỉ test trên dữ liệu tổng hợp** (`tmp_path`):
  - một chuỗi có xu hướng giả, mà luật mẫu phải bắt được;
  - một chuỗi ngẫu nhiên, mà validator phải báo TRƯỢT;
  - sha sai thì `return 2`.
- **Agent không chạy validator trên dữ liệu thật**; dữ liệu đó cũng không có trên máy agent.

### Tiêu chí xong Việc 2
- `docs/research/dot188/` có đủ 4 file.
- `trial_ledger.csv` có số dòng khớp với tổng lưới của các ý tưởng.
- `exploration_report.md` có bảng EA/EB/DSR cho **mọi** ý tưởng, kể cả bị loại, kèm lý do loại.
- `candidates.json` có 0–3 ứng viên.
- `uv run ruff check scripts/research188_*.py tests/test_research188_*.py` sạch.
- `uv run pytest -m "not integration" -q`: toàn suite không đỏ thêm so với trước khi bắt đầu. Ghi số passed trước/sau.

## 6. Cổng kiểm chứng (chốt hôm nay; Claude chạy một lần sau audit)

Với k = số ứng viên, α = 0,05 / k. Mỗi ứng viên phải ĐẠT **cả V1 lẫn V2**.

| Phần | Cổ phiếu | Crypto |
|---|---|---|
| **V1: mã chưa thấy, cùng giai đoạn** | 664 mã kiểm chứng, 2016–2022 | 10 coin kiểm chứng, 27/04/2024 → 31/08/2026 |
| **V2: giai đoạn sau** | toàn bộ 1.308 mã, 01/01/2023 → 30/09/2026 (⚠ đã mở hai lần bởi 175/177) | toàn bộ 25 coin, 01/09/2026 → ngày đo |

**Cổng (mỗi phần):**
- n ≥ 100. Dưới mức đó ghi **THIẾU SỨC MẠNH**.
- Lãi ròng trung bình mỗi lệnh > 0, p một phía < α (`bootstrap_by_month`, n = 2000, seed = 188).
- Calmar ≥ 0,86.
- Cổ phiếu: vượt baseline cùng universe sau khi bỏ 1% lệnh lãi nhất > 0.
- Crypto: lãi gộp mỗi lệnh ≥ 1,5 × chi phí vòng.

**V2 crypto chỉ có khoảng 7 tuần** nên nhiều khả năng THIẾU SỨC MẠNH. Quy tắc chốt trước: nếu V1 ĐẠT và V2 THIẾU SỨC MẠNH, ứng viên **chưa được coi là có lợi thế**. Nó chỉ được chạy paper forward cho tới khi đủ 100 lệnh, rồi áp lại đúng cổng V2.

**Hệ quả:**
- Qua V1 + V2: đi tiếp paper forward ≥ 3 tháng hoặc ≥ 50 lệnh (spec E).
- Trượt bất kỳ cổng nào: đóng ý tưởng đó, ghi là phép đo âm.
- **Không có đường tới lệnh thật trong đợt này.**

## 7. Báo cáo agent phải nộp

1. Kết quả GitNexus `context`/`impact` trước khi sửa, và `detect-changes` sau khi sửa (nguyên văn phần tóm tắt).
2. Danh sách test, số passed trước/sau, và bảng phép phá (a)–(h) kèm kết quả.
3. Nội dung `ideas.md`, đúng như đã viết trước khi chạy.
4. Số dòng sổ thử theo ý tưởng và theo giai đoạn.
5. Bảng EA/EB/cao nguyên/DSR của từng ý tưởng; ứng viên và sha256 của `candidates.json`.
6. Những chỗ mơ hồ đã gặp và cách xử lý. Nếu có lựa chọn ảnh hưởng tới kết quả mà brief chưa quy định, **dừng và hỏi**, không tự chọn.
7. Một câu cam kết: không truy vấn DB, không gọi API, không đọc file ngoài `data/research188/explore/`, không chạy validator trên dữ liệu thật.

## 8. Claude sẽ làm sau khi nhận báo cáo

1. **Audit:**
   - đối chiếu từng dòng code với brief;
   - tự chạy lại test và các phép phá (a)–(h);
   - tự viết **phép đếm độc lập** cho ít nhất một ứng viên trên EB, và đối chiếu khớp số;
   - kiểm `trial_ledger.csv` khớp lưới, và `idea_sha` không đổi giữa EA và EB;
   - grep xem có truy vấn DB hay đường dẫn ngoài thư mục khám phá không.
2. **Commit kết quả khám phá và sha của `candidates.json`.** Commit này là niêm phong ứng viên.
3. **Chạy kiểm chứng:**
   - Xuất tập kiểm chứng (mã kiểm chứng và giai đoạn V2) ra một thư mục riêng.
   - Chạy validator **một lần** cho V1 và một lần cho V2.
   - Lưu nguyên văn vào `logs/dot188-kiem-chung-<ngày>.log`.
   - Ghi `docs/holdout-unlock-log.md`.
4. Viết `docs/research/2026-10-dot-188-ket-qua-…md`, cập nhật memory, commit, push.
