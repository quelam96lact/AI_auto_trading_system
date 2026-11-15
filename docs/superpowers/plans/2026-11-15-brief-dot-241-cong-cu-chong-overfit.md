# Brief đợt 241: công cụ chống overfitting (PBO/CSCV, CPCV có purge, DSR, cao nguyên)

- **Ngày:** 15/11/2026.
- **Nguồn:** chủ dự án 15/11: "Suy nghĩ finetune tham số của chiến lược để phù hợp giao dịch chống overfitting" → Lead đề xuất xây công cụ trước, chủ dự án "ok do it".
- **Đây là hạ tầng, KHÔNG phải giả thuyết:** không đo chiến lược nào, không tốn ngân sách giả thuyết, không mở dữ liệu thị trường.
- **Vai trò:** Builder viết code + test. Researcher viết oracle độc lập **chỉ từ brief này** (không đọc code Builder trước khi oracle xong), giống đợt 233/239.
- **Builder KHÔNG được:** commit/push; truy vấn DB; gọi API; docker; `sched.sh`; `npx` (dùng `gitnexus` hoặc `node .gitnexus/run.cjs`); sửa bất kỳ file nào ngoài §2; "tiện thể" refactor các `research*_core.py` đang có bản sao `deflated_sharpe`. Thấy vấn đề ngoài phạm vi → báo lại.

## 1. Đặc tả hàm (module `scripts/overfit_core.py`, numpy + scipy như các `research*_core.py`)

Mọi lỗi đầu vào → `ValueError` (thông điệp nêu tham số sai). Không in, không đọc/ghi file.

### 1.1 `sharpe_cols(m: np.ndarray) -> np.ndarray`
Với ma trận `m` (T×N), trả mảng dài N: `mean(cột) / std(cột, ddof=1)`; cột có `std == 0` hoặc T < 2 → `0.0`. Không nhân căn thời gian (không annualize).

### 1.2 `pbo_cscv(perf: np.ndarray, n_splits: int = 16) -> PBOResult`
Bailey, Borwein, López de Prado, Zhu (2015).
- `perf`: T×N, hàng = kỳ (theo thời gian), cột = cấu hình; giá trị = lợi nhuận kỳ. Yêu cầu: 2 chiều, N ≥ 2, không NaN/inf, `n_splits` chẵn ≥ 2, `T // n_splits ≥ 2`.
- Bỏ `T mod n_splits` hàng **cuối**; chia phần còn lại thành `S = n_splits` khối liền kề bằng nhau, đánh số 0..S−1.
- Duyệt mọi tổ hợp `c` gồm S/2 khối theo thứ tự `itertools.combinations(range(S), S//2)`. IS = các hàng của các khối trong `c` (giữ thứ tự gốc); OOS = các khối còn lại.
- `is_m = sharpe_cols(IS)`, `oos_m = sharpe_cols(OOS)`. `n_star = argmax(is_m)` (hoà → chỉ số cột nhỏ nhất, tức `np.argmax`).
- `rank = scipy.stats.rankdata(oos_m, method="average")[n_star]` (1 = tệ nhất). `w = rank / (N + 1)`. `logit = ln(w / (1 − w))`.
- `pbo = (số tổ hợp có logit ≤ 0) / số tổ hợp`.
- `PBOResult` là dataclass frozen: `pbo: float`, `logits: tuple[float, ...]` (đúng thứ tự tổ hợp), `n_combos: int` (= C(S, S/2)), `n_rows_used: int`.

### 1.3 `purged_cpcv_splits(n_obs, n_groups, n_test_groups, horizon, embargo) -> list[tuple[np.ndarray, np.ndarray]]`
- Yêu cầu: số nguyên; `n_obs ≥ n_groups ≥ 2`; `1 ≤ n_test_groups < n_groups`; `horizon ≥ 0`; `embargo ≥ 0`.
- Nhóm = `np.array_split(np.arange(n_obs), n_groups)`. Duyệt tổ hợp nhóm test theo `itertools.combinations(range(n_groups), n_test_groups)`.
- `test` = hợp các nhóm test (tăng dần). Quan sát `i` có nhãn phủ đoạn `[i, i + horizon]`.
- Gộp các nhóm test **liền kề** thành khối `[a, b]`. Với mỗi khối, loại khỏi train mọi `i` không thuộc test thỏa (a) **purge:** `i <= b` và `i + horizon >= a`; hoặc (b) **embargo:** `b < i <= b + embargo`.
- `train` = phần còn lại (tăng dần, dtype int). Trả list `(train, test)`. Train rỗng vẫn trả (không lỗi).

### 1.4 `deflated_sharpe(sr, n_obs, skew, kurt, n_trials, sr_trials_var) -> float`
Cùng chữ ký và **cùng kết quả số** với `scripts/research188_core.py::deflated_sharpe` (Bailey & López de Prado 2014, SE Mertens, `kurt` kiểu Pearson, chuẩn = 3). Viết lại trong module này (không import từ research188), test so khớp với bản 188 trên lưới tham số (sai lệch ≤ 1e-12).

### 1.5 `neighbor_pass_fraction(scores: np.ndarray, threshold: float) -> np.ndarray`
- `scores`: mảng d chiều (d ≥ 1), mỗi ô = điểm của một cấu hình trên lưới tham số theo thứ tự lưới. NaN = trượt.
- Ô "đạt" nếu `score >= threshold` (không NaN). Kết quả cùng shape: với mỗi ô, tỉ lệ ô đạt trong láng giềng Chebyshev bán kính 1 **gồm chính nó**, cắt ở biên (ô góc 2D có 4 ô láng giềng gồm nó).

### 1.6 `pick_plateau(scores: np.ndarray, threshold: float) -> tuple[int, ...] | None`
- Ứng viên = ô tự nó đạt. Không có → `None`.
- Chọn ô có `neighbor_pass_fraction` lớn nhất; hoà → trung vị điểm các ô láng giềng không NaN (gồm chính nó) lớn nhất; hoà nữa → chỉ số nhỏ nhất theo thứ tự từ điển. Trả tuple chỉ số (int Python).

## 2. Phạm vi file

- **Tạo mới:** `scripts/overfit_core.py`, `tests/test_overfit_core.py`.
- **Không đụng** bất kỳ file nào khác (kể cả `pyproject.toml`, `research*_core.py`, `trading/`).

## 3. Tiêu chí hoàn thành (Builder tự kiểm, nộp output thô)

1. Test cho từng hàm §1, tối thiểu:
   - `pbo_cscv`: (a) T=8, N=2, S=4 tự dựng tay sao cho PBO = 0 và một ma trận khác cho PBO = 1; (b) `n_combos == 70` khi S=8; (c) bỏ hàng dư (T=10, S=4 → `n_rows_used == 8`); (d) mọi ValueError ở §1.2; (e) hoà IS chọn cột nhỏ nhất.
   - `purged_cpcv_splits`: một ca tính tay `n_obs=10, n_groups=5, n_test_groups=2, horizon=1, embargo=1` liệt kê đủ 10 cặp; ca `horizon=0, embargo=0` thì train ∪ test = toàn bộ và rời nhau; ValueError.
   - `deflated_sharpe`: khớp bản 188 trên ≥ 20 bộ tham số, kể cả `n_trials=1`, `n_obs<=1`, `var_sr<=0`.
   - `neighbor_pass_fraction` / `pick_plateau`: 1D và 2D, NaN, ô biên/góc, cả ba tầng hoà, trường hợp `None`.
2. `uv run pytest tests/test_overfit_core.py -v` xanh.
3. `uv run pytest -m "not integration" -q` xanh (không làm đỏ test cũ).
4. `uv run ruff check scripts/overfit_core.py tests/test_overfit_core.py` sạch.
5. `gitnexus detect_changes` chỉ thấy 2 file mới.
6. Báo cáo: danh sách `def test_*`, output thô của 2–4, và mọi chỗ brief mơ hồ Builder đã phải tự quyết.

## 4. Oracle Researcher

- Viết `check_241.py` trong scratchpad của Researcher **từ §1 brief này**, kịch bản tính tay/độc lập (tối thiểu: 3 ca PBO gồm một ca ma trận ngẫu nhiên seed cố định tính bằng vòng lặp thuần Python không dùng code Builder; 3 ca CPCV liệt kê tay; 2 ca DSR so với `research188_core`; 4 ca cao nguyên gồm hoà).
- Ghi lại mọi chỗ brief mơ hồ (đợt 233 oracle tìm ra 12 chỗ).
- Chỉ chạy oracle lên `scripts/overfit_core.py` khi Lead báo Builder xong. Báo PASS/FAIL từng kiểm.

## 5. Ngoài phạm vi (đợt sau, nếu chủ dự án muốn)

Sổ đếm tổng số lần thử toàn dự án; nối công cụ vào khuôn khám phá 237; chọn ngưỡng PBO cho cổng (gợi ý < 0,2, chưa chốt).
