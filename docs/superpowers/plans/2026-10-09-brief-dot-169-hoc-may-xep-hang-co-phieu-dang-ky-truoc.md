# Brief đợt 169 — Học máy xếp hạng cổ phiếu VN theo tháng (ĐĂNG KÝ TRƯỚC)

Ngày: 09/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.
Khung đánh giá: `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md` (vốn rủi ro 100 triệu, MDD ≤ 7%, MDD backtest ≤ 4,7%, hurdle tiền gửi 6%/năm).
**Giả thuyết 3/3 của tháng 10/2026** (spec mục F). Chủ dự án chọn ngày 09/10/2026: cổ phiếu VN, bài toán xếp hạng, mô hình Ridge + LightGBM.

---

## 0. Câu hỏi, kỳ vọng trước, và điều KHÔNG hỏi

**Câu hỏi:** một mô hình học từ đặc trưng giá/khối lượng có xếp hạng được lợi nhuận tháng tới của cổ phiếu VN đủ tốt để danh mục top 10% **thắng danh mục mua đều (EW) sau phí**, kiểm theo kiểu walk-forward (chỉ học từ quá khứ)? Nếu có, phần thắng đó **đến từ học máy** (LightGBM) hay mô hình tuyến tính (Ridge) cũng làm được?

**Kỳ vọng trước của Claude: nhiều khả năng âm.**
- Đợt 102 (cùng dữ liệu, cùng khung danh mục): momentum 12−1 tháng **thua EW có ý nghĩa**, −1,02%/tháng, KTC [−1,81; −0,26]. Tức có dấu hiệu **đảo chiều**, và đó là thông tin một mô hình có thể học. Nhưng chính vì Claude đã thấy kết quả này trên IS, việc chọn đặc trưng ở §1.3 không hoàn toàn mù. Ghi nhận ở đây để không ai coi kết quả dương là "tìm ra từ đầu".
- 14 phép đo trước đều âm. Mốc phải vượt rất cao (§1.8).

**Không hỏi:** có giao dịch thật được không. Kết quả dương chỉ mở đường tới bước mở niêm phong (§5).

## 1. Thiết kế đăng ký trước — KHÔNG đổi sau khi thấy dữ liệu

### 1.1 Dùng lại khuôn đợt 102
Đọc `scripts/screen_momentum_portfolio.py` (brief đợt 102) trước. **Import** các hàm của nó và của `trading/stock_study.py` khi dùng được, không chép lại. Các quy tắc giữ **đúng như đợt 102**:
- Nguồn `bars_daily` qua `Storage.read_daily_bars`, ngày theo giờ VN (`bar_date`), bỏ nến giá ≤ 0 (`clean_bars`).
- Universe: `load_universe(storage, "exclusions.txt")` (loại 246 mã hỏng điều chỉnh giá), rồi chỉ giữ mã cổ phiếu (`is_stock_symbol`).
- Ngày xếp hạng F = phiên cuối mỗi tháng dương lịch. Điều kiện được xếp hạng tại F: thanh khoản 20 phiên ≥ 1 tỷ (`liquidity_ok`), có đủ 252 phiên lịch sử. Dưới 100 mã đủ điều kiện thì bỏ tháng.
- Giữ tháng kế tiếp: vào ở OPEN phiên đầu, ra ở CLOSE phiên cuối. Mã mở cửa giá trần phiên vào thì loại, không thay mã khác.
- Chi phí theo turnover, `cost_rt = 2 × FEE_RATE + SELL_TAX_RATE + 2 × SLIPPAGE_BPS / 10.000`, **import** từ `trading/paper_broker.py` (FEE_RATE hiện 0,28%).

### 1.2 Niêm phong và chia giai đoạn
- **Niêm phong:** cổ phiếu từ **01/01/2023** (`SEALED_START`, đợt 120). Đọc tới 31/12/2022; nến ≥ 01/01/2023 thì ném lỗi (`validate_sealed_bars`). Họ "học máy xếp hạng cổ phiếu" chưa từng mở niêm phong.
- **Walk-forward trong IS:** tháng thử đầu tiên là 01/2018, tháng cuối là 12/2022, tức **60 tháng thử**.
- Mỗi tháng 1 (2018…2022) huấn luyện lại trên **mọi** mẫu (F, mã) có F từ 30/12/2016, với nhãn **đã biết hết trước** tháng thử đầu tiên của năm đó.
  - **Purge 1 tháng:** mẫu tại F có nhãn là lợi nhuận tháng F+1, nên mẫu F = tháng 12 năm trước **không** được vào tập huấn luyện của năm sau, vì nhãn của nó chính là tháng thử đầu tiên.
- Mô hình giữ cố định cả năm, không học thêm giữa năm.

### 1.3 Đặc trưng (11, cố định) — tính chỉ từ dữ liệu tới CLOSE phiên F
| Tên | Định nghĩa (i_F là chỉ số nến tại F) |
|---|---|
| `ret_1m` | close[i_F] / close[i_F−21] − 1 |
| `ret_3m` | close[i_F] / close[i_F−63] − 1 |
| `ret_6m` | close[i_F] / close[i_F−126] − 1 |
| `mom_12_1` | close[i_F−21] / close[i_F−252] − 1 (đúng định nghĩa đợt 102) |
| `vol_20` | độ lệch chuẩn log return ngày, 20 phiên kết thúc tại i_F |
| `vol_60` | như trên, 60 phiên |
| `dist_ma50` | close[i_F] / trung bình close 50 phiên − 1 |
| `dist_high_252` | close[i_F] / max close 252 phiên − 1 |
| `log_turnover_20` | log(trung bình close × volume 20 phiên) |
| `vol_ratio_5_60` | trung bình volume 5 phiên / trung bình volume 60 phiên |
| `max_ret_21` | log return ngày lớn nhất trong 21 phiên |

Mỗi tháng, mỗi đặc trưng đổi thành **hạng phần trăm trong mặt cắt** (0…1) giữa các mã đủ điều kiện tháng đó. Thiếu dữ liệu thì mã không đủ điều kiện, không nội suy.

### 1.4 Nhãn
Hạng phần trăm trong mặt cắt (0…1) của **lợi nhuận gộp** tháng giữ (OPEN phiên đầu → CLOSE phiên cuối), theo đúng định nghĩa giữ tháng của đợt 102. Mã bị loại vì trần ở phiên vào thì **không có nhãn**, không vào tập huấn luyện.

### 1.5 Mô hình (tham số chốt, KHÔNG dò)
- **Ridge** (`sklearn.linear_model.Ridge`): `alpha=1.0`, `fit_intercept=True`.
- **LightGBM** (`lightgbm.LGBMRegressor`): `n_estimators=200`, `learning_rate=0.05`, `num_leaves=15`, `min_child_samples=100`, `subsample=0.8`, `subsample_freq=1`, `colsample_bytree=0.8`, `reg_lambda=1.0`, `random_state=42`, `deterministic=True`, `force_row_wise=True`, `n_jobs=1`, `verbose=-1`.
- Không early stopping, không tập validation, không tìm siêu tham số. Agent thấy tham số nào sai cú pháp với phiên bản thư viện thì **dừng và báo**, không tự thay.

### 1.6 Danh mục
Với mỗi mô hình, mỗi tháng thử: **WIN** = 10% mã có dự báo cao nhất (làm tròn lên, tối thiểu 10 mã), trọng số đều. **EW** = mọi mã đủ điều kiện, như đợt 102. Ghi thêm **LOSE** = 10% thấp nhất, chỉ để mô tả.

### 1.7 Phép thử (chốt)
- **Chính:** `excess(M) = net_WIN_LGBM(M) − net_EW(M)` trên 60 tháng. Bootstrap theo **khối 3 tháng liền nhau**, 2.000 lần, `seed=42` (dùng lại hàm đợt 102).
  - **CÓ LỢI THẾ** khi cả ba: p < 0,05 một phía, trung bình `net_WIN_LGBM` > 0, và trung vị `excess` > 0.
- **Học máy có giá trị hay không:** cùng bootstrap cho `net_WIN_LGBM − net_WIN_Ridge`. Đọc kết quả:
  - LGBM CÓ LỢI THẾ **và** thắng Ridge với p < 0,05 → "học máy có giá trị".
  - LGBM CÓ LỢI THẾ nhưng không thắng Ridge → "lợi thế đến từ đặc trưng, không phải học máy".
  - Ridge CÓ LỢI THẾ còn LGBM không → ghi đúng như vậy; biến thể chính vẫn là LGBM, không đổi.
- **IC (mô tả):** mỗi tháng, Spearman giữa dự báo và lợi nhuận tháng giữ; báo trung bình, độ lệch chuẩn, số tháng IC > 0, cho cả hai mô hình.
- **Đối chứng âm (bắt buộc):** chạy lại toàn bộ đường ống LGBM với **nhãn xáo trộn trong từng tháng** (`seed=42`). `excess` trung bình phải gần 0; báo con số và p. Nếu đối chứng âm cũng ra CÓ LỢI THẾ thì đường ống có rò rỉ: **dừng, không in kết quả chính**, báo Claude.

### 1.8 Đối chiếu mốc chuẩn (mô tả, không dùng để chọn)
Trên cùng 2018–2022:
- WIN_LGBM, WIN_Ridge, EW, và `E1VFVN30` mua-giữ (khuôn đợt 102): CAGR ròng, MDD, năm tệ nhất.
- **Phương án thay thế phần ETF trong mốc chuẩn đợt 165:** 15% vốn vào WIN_LGBM + 85% tiền gửi 6%, cân bằng năm, so với 15% ETF + 85% tiền gửi trên cùng 2018–2022. Dùng lại hàm của `scripts/measure_etf_deposit_mix.py` cho phần tiền gửi và cân bằng.
- Cột ĐẠT/KHÔNG ĐẠT theo spec mục B: MDD ≤ 4,7%, MDD ≤ 7%, CAGR ≥ 6%.

### 1.9 Kỷ luật chạy
Chạy phép đo thật **một lần**. Lỗi code buộc chạy lại thì báo cả hai lần và lỗi gì. Cấm đổi đặc trưng, tham số, nhãn, ngưỡng thanh khoản, kích thước WIN, cách purge, hay thêm mô hình.

## 2. Phạm vi
- **Được thêm:** `scripts/screen_ml_cross_section.py`, `tests/test_screen_ml_cross_section.py`, báo cáo `docs/superpowers/research/2026-10-09-dot-169-hoc-may-xep-hang-co-phieu.md`.
- **Được sửa:** `pyproject.toml` + `uv.lock`, **chỉ** để thêm `scikit-learn` và `lightgbm` vào nhóm `dev` (không vào dependencies chính). Kiểm `Dockerfile` vẫn `uv sync --frozen --no-dev`, tức image chạy thật không có hai thư viện này. Báo phiên bản đã cài.
- **Được import, không sửa:** `scripts/screen_momentum_portfolio.py`, `scripts/measure_etf_deposit_mix.py`, `trading/stock_study.py`, `trading/paper_broker.py`, `trading/metrics.py`.
- **Không sửa:** mọi file khác. **Chỉ đọc DB.** Cấm chạy `scripts/sched.sh`. Thấy vấn đề ngoài phạm vi thì báo, không tự sửa.
- Quy ước `scripts/` (đợt 159): script mới phải được test nhắc tên, tức file test ở trên là đủ. Chạy `tests/test_scripts_convention.py` để chắc chắn.
- GitNexus: chạy `npx gitnexus analyze` trước. Chạy `context` cho các hàm dùng lại của đợt 102 trước khi viết; `detect_changes` sau khi xong.

## 3. Kiểm chứng — TDD trên dữ liệu dựng tay, không đọc DB
1. **Đặc trưng không nhìn tương lai:** sửa mọi nến sau F → 11 đặc trưng tại F không đổi.
2. **Purge:** với năm thử 2019, tập huấn luyện gồm đúng các F từ phiên cuối 12/2016 tới **phiên cuối 11/2018** (nhãn là tháng 12/2018, đã biết), và **không** có F của tháng 12/2018 (nhãn của nó là tháng 01/2019, tức tháng thử). Khẳng định bằng danh sách F trong tập huấn luyện.
3. **Không huấn luyện trên tương lai:** đổi nhãn của mọi tháng ≥ tháng thử → dự báo của tháng thử không đổi.
4. **Hạng mặt cắt:** đặc trưng và nhãn nằm trong [0, 1]; mã duy nhất bằng nhau thì hạng bằng nhau.
5. **Tín hiệu giả phải được tìm thấy (đối chứng dương):** dựng dữ liệu tổng hợp mà lợi nhuận tháng tới tỷ lệ với `−ret_1m` cộng nhiễu nhỏ → cả Ridge và LGBM cho WIN thắng EW rõ rệt.
6. **Nhãn xáo trộn không thắng (đối chứng âm):** cùng dữ liệu, xáo nhãn trong tháng → `excess` trung bình gần 0 (ngưỡng do agent đặt, nêu lý do).
7. **Chi phí:** danh mục giữ nguyên hai tháng liền thì turnover = 0, không mất phí; đổi toàn bộ thì mất đúng `cost_rt`.
8. **Niêm phong:** có nến ≥ 01/01/2023 thì hàm đọc ném lỗi.
9. **Tất định:** chạy LGBM hai lần cùng dữ liệu → dự báo giống hệt.

Kiểm thử phá hoại: sao lưu file ra ngoài repo; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ.
- Dùng close[i_F+1] trong `ret_1m` → test 1 đỏ.
- Bỏ purge → test 2 đỏ.
- Hạng tính trên toàn giai đoạn thay vì từng tháng → test 4 hoặc 3 đỏ.
- Bỏ phí → test 7 đỏ.

```
uv sync --extra dev
uv run pytest tests/test_screen_ml_cross_section.py -v
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts
```

## 4. Hoàn thành khi
- 9 test xanh, bốn bước phá hoại mỗi bước làm đỏ đúng test đã nêu.
- Bộ đầy đủ không có test mới đỏ. Mốc 09/10: `1932 passed` (bộ đầy đủ); dán số trước và sau.
- ruff sạch. `detect_changes` chỉ gồm các file ở §2.
- Phép đo IS thật đã chạy **một lần** (chỉ đọc DB). Báo cáo có:
  - số mã trong universe, số tháng hợp lệ, số mã đủ điều kiện mỗi tháng (min/trung vị/max);
  - **số mã có nến cuối trước 30/06/2022** (để biết dữ liệu có gồm mã đã hủy niêm yết không, tức mức thiên lệch sống sót);
  - kết quả đối chứng âm;
  - bảng §1.7 cho LGBM, Ridge, và LGBM − Ridge;
  - IC hai mô hình;
  - bảng §1.8;
  - bảng theo năm của WIN_LGBM, WIN_Ridge, EW;
  - đối chiếu kỳ vọng trước của Claude ở §0, ghi đúng/sai;
  - độ quan trọng đặc trưng của LGBM năm cuối (mô tả, không dùng để chọn lại đặc trưng).

## 5. Quy tắc đọc kết quả
- LGBM không CÓ LỢI THẾ → ghi **"Học máy xếp hạng cổ phiếu VN (11 đặc trưng giá/khối lượng): KHÔNG có lợi thế trên IS 2018–2022"**, phép đo âm thứ 15. Không mở niêm phong.
- LGBM CÓ LỢI THẾ → chưa phải kết luận. Claude mở niêm phong **một lần** (2023-01 → 09/2026) cho đúng cấu hình LGBM top 10%, ghi `docs/holdout-unlock-log.md`; cần p < 0,05 lặp lại. Qua thì so tiếp với mốc chuẩn đợt 165 trên cùng giai đoạn.
- Ghi kết quả vào sổ giả thuyết tháng 10, kể cả âm.

## 6. Báo cáo cho Claude
1. Output pytest/ruff, bảng bốn bước phá hoại, phiên bản `scikit-learn`/`lightgbm`.
2. `detect_changes`.
3. Lệnh chạy IS và **output đầy đủ, nguyên văn**.
4. Một câu xác nhận: "Tôi không đọc nến nào từ 01/01/2023 và không ghi vào `docs/holdout-unlock-log.md`."
5. Mọi chỗ brief mơ hồ mà agent phải tự diễn giải; không im lặng chọn.
