# Brief đợt 237: danh mục "ít được chú ý" (abnormal turnover thấp), xoay vòng tháng (ĐĂNG KÝ TRƯỚC)

- **Ngày:** 15/11/2026.
- **Spec:** dòng H ngày 15/11/2026 (đợt 237) trong `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`. Suất giả thuyết thứ 1 của tháng 11 (được trả lại 11/10).
- **Khuôn:** đợt 193 (`docs/superpowers/plans/2026-10-25-brief-dot-193-danh-muc-bien-dong-thap.md`). Mọi luật không nêu lại ở đây thì **giữ đúng như brief 193** (§3.1 lịch xoay vòng, §3.4 mô phỏng, §3.5 baseline EW, §3.6 giai đoạn EA/EB, §3.7 thống kê). Đọc brief 193 trước.
- **Vai trò:**
  - **Builder** viết code + test, chạy khám phá **một lần**. KHÔNG commit, KHÔNG push.
  - **Researcher** (song song, không xem code của Builder) tính lại độc lập danh sách mã được chọn và EW.
  - **Lead** audit, đối chiếu, commit, push; chạy kiểm chứng V1/V2 nếu có ứng viên.
- **Builder KHÔNG được:** truy vấn DB (đọc lẫn ghi); gọi API thật; đọc file bí mật; mở file dữ liệu nào ngoài `data/research227/explore/`; chạy `scripts/sched.sh`; docker; `npx`; `taskkill` theo tên; sửa file đã có **trừ một chỗ ở §2**.
- **Niêm phong:** tập kiểm chứng gồm các mã ngoài tập khám phá (2016–2022) và mọi mã từ 01/01/2023. Tập này không có trong thư mục dữ liệu của Builder. Không tìm, không suy ra, không tải về.

## 0. Giả thuyết và cách hiểu (thấy sai thì dừng và báo)

- **Cơ chế:** ở thị trường do nhà đầu tư cá nhân chi phối, mã đang được chú ý (thanh khoản tăng bất thường so với chính nó) bị mua quá giá; mã bị bỏ quên (thanh khoản gần đây thấp so với mức một năm của chính nó) có lãi kỳ vọng cao hơn.
- **Một ý tưởng `I1_LOWATTN`, 9 cấu hình.** Builder không thêm ý tưởng, bộ lọc, đặc trưng hay cấu hình. Chỉ mua, không học máy, không đòn bẩy.
- **Gợi ý đã thấy, không phải bằng chứng:** đợt 77 và đợt 227 (B0 thua EW) đều tính trên dữ liệu đã mở. Kết quả đợt này mới là phép đo.
- **Gần họ đã đóng:** danh mục biến động thấp (đợt 193). Báo cáo phải ghi cảnh báo này và cảnh báo thiên lệch sống sót.
- **Ước lượng trước của Lead:** khả năng qua đủ cổng là thấp. **0 ứng viên là kết quả hợp lệ.** Không nới cổng nào.

## 1. Dữ liệu

`data/research227/explore/` (đã có, sha256 `stocks_daily.csv.gz` = `0d04ca36…`, 601 mã, 04/01/2016 → 30/12/2022). Đọc bằng `load_stocks`, `load_exchanges` (`scripts/research191_data.py`) và `load_sessions` (`scripts/research192_core.py`).

**Loại chứng chỉ quỹ trước mọi phép tính** (cả chọn mã lẫn EW): mã `== "E1VFVN30"` hoặc bắt đầu bằng `"FU"`. Tập khám phá có 10 mã như vậy; còn 591 mã.

**Đếm trước của Lead (chỉ đếm số mã, không xem lợi nhuận):** số mã thuộc universe §3.2 tại `r` = `L(01/2017)`, `L(06/2018)`, `L(12/2019)`, `L(06/2021)`, `L(12/2022)` là **56, 58, 85, 166, 136**. Số của Builder phải khớp; lệch thì dừng và báo trước khi tính lợi nhuận.

## 2. Phạm vi file

- **Tạo mới:** `scripts/research237_core.py`, `scripts/research237_explore.py`, `scripts/research237_validate.py`, `tests/test_research237_*.py`, `docs/research/dot237/` (`trial_ledger.csv`, `exploration_report.md`, `candidates.json`, `selections.json`).
- **Sửa đúng một chỗ:** `scripts/research193_core.py`, hàm `simulate_rotation`: thêm tham số cuối `select_fn: Callable[[date], list[str]] | None = None`. Khi `select_fn` khác `None`, danh sách mã tại phiên xoay vòng `r` là `select_fn(r)` thay cho lời gọi `score_and_rank_symbols(...)`; khi `None`, hành vi **không đổi**. Không sửa gì khác trong file. Toàn bộ `tests/test_research193_*.py` phải vẫn xanh. Trước khi sửa: `node .gitnexus/run.cjs impact "simulate_rotation" --direction upstream --repo .` (kèm grep), dán kết quả.
- **Import, không sửa:** `research193_core` (`get_rebalance_dates`, `simulate_rotation`, `ew_benchmark`, `calculate_rotation_metrics`, `is_ceiling_locked`), `research191_exits` (`is_liquid`, `assert_ledger_safety`), `research188_core.deflated_sharpe`, `research188_ledger.evaluate_and_log`, `research191_data`, `research192_core.load_sessions`.
- Không đụng file nào khác, `pyproject.toml`, `uv.lock`.

## 3. Luật (chốt)

### 3.2 Universe tại `r` (thay §3.2 của 193)
`r⁻` là phiên liền trước `r` trong `S`. Mã thuộc universe khi: không phải chứng chỉ quỹ (§1); có nến ở `r⁻`; `is_liquid(bars, t, min_turnover=1e9)` tại nến `r⁻`; và có **ít nhất 250 nến** tính tới hết `r⁻` (chỉ số nến `t ≥ 249`).

### 3.3 Điểm `AT_S`
- `v_i = close_i × volume_i` của nến `i` của chính mã.
- `AT_S = mean(v của S nến gần nhất, kết thúc ở r⁻) / mean(v của 250 nến gần nhất, kết thúc ở r⁻)`. Mẫu số ≤ 0 thì loại mã.
- Giữ `N` mã có `AT_S` **thấp nhất**; hoà điểm xếp mã A→Z. Universe ít hơn `N` mã thì giữ hết, phần trống để tiền mặt.
- Lưới: `S ∈ {20, 40, 60}` × `N ∈ {10, 15, 20}`. `LONG_WINDOW = 250` cố định.

### 3.4–3.7
Như brief 193: `simulate_rotation` (qua `select_fn`), `ew_benchmark(..., min_turnover=1e9)` trên cùng tập đã loại chứng chỉ quỹ, EA `L(01/2017) → L(12/2019)`, EB `L(12/2019) → L(12/2022)`, `calculate_rotation_metrics(seed=237)`, sổ thử `docs/research/dot237/trial_ledger.csv` với `idea_id="I1_LOWATTN"`.

## 4. Việc 1: hạ tầng (TDD, dữ liệu tổng hợp trong `tmp_path`)

Mỗi phép phá phải làm đỏ một test **gọi đúng hàm sản phẩm**; test chỉ so hằng số hay hàm tự viết trong test thì không tính. Sao lưu ra ngoài repo rồi sửa; cấm `git checkout/restore/stash`; không có cờ phá thử trong code sản phẩm.

| # | Phép phá | Hàm phải gọi |
|---|---|---|
| a | Điểm tính tới hết `r` thay vì `r⁻` | hàm chọn mã |
| b | Giữ `N` mã `AT` **cao** nhất | hàm chọn mã |
| c | Bỏ `is_liquid` | hàm chọn mã |
| d | Tử số hoặc mẫu số dùng sai cửa sổ (ví dụ mẫu số dùng `S`) | hàm chọn mã, so `AT` **tính tay** |
| e | `AT` tính bằng khối lượng, bỏ giá | hàm chọn mã (dữ liệu mà giá đổi làm đổi thứ hạng) |
| f | Không loại chứng chỉ quỹ | hàm lọc universe |
| g | Yêu cầu 250 nến bị bỏ hoặc lệch một nến | hàm chọn mã |
| h | `simulate_rotation` bỏ qua `select_fn` | `simulate_rotation` |
| i | Bước 1 chọn cấu hình theo `mean_X` thay vì `sharpe_X` | hàm chọn cấu hình |
| j | Bỏ kiểm cao nguyên, hoặc chỉ kiểm một chiều tham số | hàm kiểm cao nguyên |
| k | Cổng EB bỏ điều kiện MDD ≤ ⅔ ETF, hoặc bỏ CAGR ≥ ETF − 1 điểm, hoặc bỏ p < 0,05 | hàm cổng EB |
| l | DSR dùng `n_trials` thiếu `+ 29` hoặc gọi sai chữ ký | hàm Bước 4, so với một lời gọi `deflated_sharpe` viết trực tiếp trong test |
| m | `run_exploration` bỏ `assert_ledger_safety` hoặc xoá sổ cũ | `run_exploration` với sổ trong `tmp_path` |

`research237_validate.py` (Builder viết, Lead chạy): CLI và mã thoát như brief 193 §5 (`--data-dir`, `--candidates`, `--candidates-sha`, `--part V1|V2`, `--first-rebalance`, `--last-rebalance`, `--hurdle-cagr`, thêm `--etf-cagr`, `--etf-mdd`). Test trên dữ liệu tổng hợp: sha sai → 2; chuỗi mà mã ít chú ý lãi đều → ĐẠT; lỗ đều → TRƯỢT.

Chạy `uv run python -m py_compile` cho các file mới.

## 5. Việc 2: khám phá (một lần)

`run_exploration` gọi `assert_ledger_safety(ledger_path)` ở dòng đầu. Lỗi code buộc chạy lại thì báo cả hai lần và lỗi gì.

- **Bước 0:** in số mã universe tại 5 mốc ở §1, so với đếm trước. Lệch thì dừng.
- **Bước 1:** chạy 9 cấu hình trên EA, ghi sổ. Chọn cấu hình có `sharpe_X` cao nhất.
- **Bước 2 (cao nguyên):** mọi láng giềng ±1 bước trên **từng** tham số (`S`, `N`) phải có `mean_X > 0` và `sharpe_X ≥ 50%` của cấu hình được chọn. Không đạt thì dừng, **không** đổi đỉnh.
- **Bước 3:** chạy đúng cấu hình đó **một lần** trên EB, ghi sổ `period="EB"`. Đạt khi thoả cả bốn:
  1. `mean_X > 0` và p một phía < 0,05;
  2. MDD danh mục ≤ **28,19%** (= ⅔ × 42,29%, MDD mua-và-giữ `E1VFVN30` trên EB);
  3. CAGR danh mục ≥ **4,50%** (= 5,50% − 1 điểm);
  4. trung bình số mã giữ ≥ 0,8 × N.
  Hằng số đặt trong code: `ETF_EB_CAGR = 0.0550`, `ETF_EB_MDD = 0.4229`, `ETF_EA_CAGR = 0.1251`, `ETF_EA_MDD = 0.2788` (Lead tính từ `bars_daily` trước khi có kết quả chiến lược).
- **Bước 4 (DSR)** trên chuỗi `X_m` của EA: `deflated_sharpe(sr=sharpe_X, n_obs=số tháng, skew, kurt, n_trials=9 + 29, sr_trials_var=var(sharpe_X của 9 dòng EA, ddof=1))`. `PRIOR_NEGATIVE_FAMILIES = 29`. Đạt khi ≥ 0,95. Chỉ in DSR đã tính thật; dừng trước Bước 4 thì ghi "không tính".
- **Ứng viên:** tối đa 1, khi qua đủ bốn bước.
- **Cấm:** chạy EB lần hai, sửa luật sau khi thấy EB, thêm bộ lọc.

**`exploration_report.md`** in cho mọi dòng EA và EB: số tháng, `mean_X`, `sharpe_X`, p; lợi nhuận tháng TB của chiến lược và EW; CAGR, MDD, Calmar danh mục (ghi rõ **cổng cũ Calmar ≥ 0,86 đạt hay không**, chỉ để thông tin); CAGR của EW; turnover tháng TB; phí theo năm (% NAV); số mã giữ TB; so với mốc ETF cùng giai đoạn; kết quả từng bước; cảnh báo thiên lệch sống sót, đa so sánh và gần họ 193.

**`selections.json`** (để đối chiếu độc lập): với mỗi cấu hình EA (`"S20_N10"` …) và lần chạy EB (`"EB_S.._N.."`): `{"rebalance_dates": [...], "selected": {ngày: [mã theo thứ tự xếp hạng]}, "monthly_r": [...], "monthly_ew": [...]}`.

## 6. Cổng kiểm chứng (Lead chạy một lần, chỉ khi có ứng viên)

| Phần | Dữ liệu | Xoay vòng |
|---|---|---|
| V1 | mã ngoài tập khám phá, 2016–2022 | `L(01/2017) → L(12/2022)` |
| V2 | mọi mã, lookback từ 2022 | `L(12/2022) → L(10/2026)` |

Mỗi phần: `mean_X > 0` với p một phía < 0,05; MDD ≤ ⅔ MDD ETF và CAGR ≥ CAGR ETF − 1 điểm trên cùng giai đoạn (Lead tính mốc lúc chạy); số mã giữ TB ≥ 0,8 × N. V2 thêm: CAGR > mốc ETF + tiền gửi cùng giai đoạn. Qua cả hai mới mở paper forward trên engine nến ngày. Trượt thì đóng họ, ghi phép đo âm.

## 7. Tiêu chí hoàn thành (dán output thật)

1. Impact/grep cho `simulate_rotation`; chữ ký các hàm import đã đọc.
2. `uv run pytest tests/test_research237_*.py tests/test_research193_*.py -q`; bảng phép phá a–m với dòng `FAILED` nguyên văn.
3. `uv run ruff check scripts tests`; `uv run pytest -m "not integration" -q` (số pass).
4. Bước 0: số mã universe 5 mốc so với §1.
5. Lệnh chạy khám phá và output nguyên văn.
6. `node .gitnexus/run.cjs detect-changes --scope all --repo .`; `git status --short`; `git diff --stat`.
7. Một câu: "Tôi không truy vấn DB và không mở file dữ liệu nào ngoài `data/research227/explore/`."
8. Mọi chỗ brief mơ hồ mà Builder phải tự diễn giải.
