# Brief đợt 244: dòng tiền ETF khi tái cơ cấu rổ (ĐĂNG KÝ TRƯỚC)

- **Ngày đăng ký:** 15/11/2026. **Chạy phép đo IS từ 01/12/2026** — giả thuyết #1 tháng 12 (tháng 11 đã vượt ngân sách mục F). Trước 01/12 chỉ được làm hạ tầng (§4 bước 1–3), **không tính bất kỳ lợi nhuận nào**.
- **Spec:** dòng H ngày 15/11/2026 (đợt 244). Lead quyết định (chủ dự án giao tự quyết phần chiến lược 15/11).
- **Cơ chế:** ETF bám chỉ số (VNM ETF ~520tr USD, FUEVFVND ~10.180 tỷ, E1VFVN30 ~5.830 tỷ, FTSE VN ETF tới 2025Q2, FUESSVFL) **bắt buộc** mua mã được thêm vào rổ quanh ngày hiệu lực. Nhà đầu tư biết danh sách từ ngày công bố → giá mã được thêm có thể tăng vượt thị trường trong cửa sổ công bố → hiệu lực. Nguồn lợi thế là dòng tiền bắt buộc, không phải hình mẫu giá-khối lượng (32 họ giá-khối lượng đã âm).
- **Ước lượng trước của Lead:** khả năng qua đủ cổng là **thấp–trung bình**: hiệu ứng được biết rộng rãi (có thể đã bị khai thác hết), mẫu nhỏ, tập niêm phong ít sự kiện (xem §3). **0 ứng viên là kết quả hợp lệ.**

## 1. Dữ liệu sự kiện (đã chốt, không sửa sau khi đăng ký)

- File: `docs/research/dot244/events_filled.csv` (sha256 `0fd46a9f4d1edeae300afb05ae0f91080a15827c7eae7a7ec15d1bf08f3906ed`; kèm `periods.csv`, `sample_audit_result.csv`) (gom bởi Researcher 15/11, kiểm độc lập 33/33 dòng mẫu khớp nguồn; ngày hiệu lực thiếu được điền theo quy tắc chính thức của nhà cung cấp chỉ số **chỉ** khi quy tắc khớp ≥ 95% ngày đã biết: VNM 21/22, FTSE (kỳ có ETF) 16/16, VNFinLead 12/12). Mọi sửa đổi file sau đăng ký = vi phạm.
- **Lọc sự kiện dùng được:** `etf_tracked = true`, `action = add`, `effective_date_kind ≠ missing`, `announce_date < effective_date`. (VNDiamond 19 dòng thiếu ngày → loại; FTSE 2017Q1 có ngày bài báo sau hiệu lực → loại.)
- **Khử trùng:** một cặp (`symbol`, `effective_date`) chỉ tính một lệnh dù mã vào nhiều rổ cùng kỳ; giữ `announce_date` **sớm nhất** của cặp.
- **Chỉ chiều thêm (add), chỉ mua.** Chiều loại (remove) không đo: không bán khống được, còn "mua mã bị loại để đón hồi" là giả thuyết khác, không đăng ký ở đây.

## 2. Quy tắc giao dịch (2 cấu hình, chốt trước)

Ký hiệu: `s_a` = phiên giao dịch đầu tiên **sau** `announce_date` (ngày công bố/bài báo không tính, kể cả khi công bố trong giờ); `s_e` = phiên đầu tiên có ngày ≥ `effective_date`; `s_r` = phiên ngay trước `s_e` (phiên ETF tái cơ cấu).

- **A1:** mua giá đóng cửa `s_a`, bán giá đóng cửa `s_r`. Nếu `s_a ≥ s_r` → bỏ sự kiện (không đủ cửa sổ).
- **A2:** mua giá đóng cửa `s_a`, bán giá đóng cửa phiên thứ 5 sau `s_e` (`s_e` tính là phiên 0).
- Thiếu nến ở `s_a` hoặc phiên bán (mã chưa niêm yết/tạm ngừng) → bỏ sự kiện, **đếm và báo cáo** theo chỉ số.
- **Chi phí:** `FEE_RATE`, `SELL_TAX_RATE`, `SLIPPAGE_BPS` import từ `trading.paper_broker` (đúng cách `research193_core.simulate_rotation` dùng). Không gõ lại hằng số.
- **Đối chứng:** lợi nhuận EW cùng cửa sổ (đóng cửa `s_a` → đóng cửa phiên bán) của universe: mọi mã không phải chứng chỉ quỹ, có nến ở `s_a`, GTGD trung bình 20 phiên tới `s_a` ≥ 1 tỷ. `X_i = r_net,i − r_ew,i` (EW không trừ phí).

## 3. Mẫu và niêm phong

- **IS:** sự kiện có `effective_date` 2017-01-01 → 2022-12-31 (đếm trước, chưa khử trùng: 101 add).
- **Niêm phong V:** `effective_date` 2023-01-01 → 2026-11-30 (~50 add). Mở **đúng một lần**, chỉ cho cấu hình đã chọn ở IS, ghi `docs/holdout-unlock-log.md` trước khi mở.
- **Cảnh báo bắt buộc trong báo cáo:** V có < 100 lệnh → theo spec mục C, kết quả V mang nhãn **THIẾU SỨC MẠNH** nếu không đạt p < 0,05; khi đó không mở đường paper forward. Thiên lệch sống sót: `bars_daily` gần như không có mã đã hủy; ảnh hưởng chiều add nhỏ (mã vừa được thêm là mã lớn) nhưng phải đếm số sự kiện mất nến.

## 4. Các bước

1. **Xuất dữ liệu (Researcher, chỉ đọc DB):** `data/research244/is/` gồm `stocks_daily.csv.gz` (mọi mã trong `symbol_universe` trừ `exclusions.txt` như manifest 227, **không chia băm**, OHLC > 0, 2016-01-04 → 2022-12-30), `sessions.csv`, `exchanges.csv`, `manifest.json` (sha256, số dòng). `data/research244/v/` tương tự cho 2022-10-01 → 2026-11-30 nhưng **không ai đọc nội dung** trước bước 6; chỉ ghi manifest. Builder không được đọc `data/research244/v/`.
2. **Builder:** `scripts/research244_core.py` (lọc + khử trùng sự kiện §1, tìm `s_a/s_e/s_r`, lợi nhuận ròng, EW cửa sổ, `X_i`), `scripts/research244_explore.py` (chạy IS, ghi `docs/research/dot244/`), test `tests/test_research244_core.py` trên dữ liệu giả. Loader IS phải **từ chối** đọc bất kỳ ngày > 2022-12-30 (test bắt buộc). Không DB, không API, không commit.
3. **Researcher oracle:** tính tay độc lập ≥ 5 sự kiện IS chọn ngẫu nhiên (seed 244) từ brief, so với output Builder. **Chưa xem tổng hợp.**
4. **IS (từ 01/12):** với mỗi cấu hình: `n`, `mean_X`, trung vị, tỷ lệ `X > 0`, `sharpe_X` (theo lệnh), p một phía bằng bootstrap **cụm theo `effective_date`** (10.000 lần, seed 244), Holm trên 2 cấu hình. Báo theo năm và theo chỉ số (chỉ mô tả, không chọn lọc). PBO qua `scripts/trial_ledger.pbo_for_exploration` trên ma trận hàng = kỳ xét lại (trung bình `X` theo `effective_date`), cột = A1/A2, chỉ báo cáo.
5. **Chọn và cổng IS:** chọn cấu hình có `sharpe_X` cao hơn. Đạt IS khi: `n ≥ 100` (sau khử trùng/bỏ), `mean_X > 0`, p Holm < 0,05, và **DSR ≥ 0,95** với `n_trials = 2 + PRIOR_NEGATIVE_FAMILIES` (= 34, import từ `scripts/trial_ledger`). Không đạt → dừng, ghi phép đo âm thứ 33, **không mở V**.
6. **V (chỉ khi đạt IS, đúng một lần):** cấu hình đã chọn: `mean_X > 0` và p < 0,05 một phía (bootstrap cụm như trên). Đạt → ứng viên paper forward; trượt hoặc THIẾU SỨC MẠNH → không tiến.

## 5. Phạm vi file và điều cấm

- **Tạo:** `scripts/research244_core.py`, `scripts/research244_explore.py`, `tests/test_research244_core.py`, `docs/research/dot244/`. Dùng lại bằng import (loader 191/227, cách tính phí 193); được thêm tham số tuỳ chọn có mặc định giữ hành vi cũ, liệt kê diff.
- **Builder KHÔNG:** commit/push; DB; API; `sched.sh`; docker; `npx`; đọc `data/research244/v/`; thêm cấu hình/bộ lọc/chỉ số; chạy bước 4 trước 01/12.
- **Không ai** được tính lợi nhuận sự kiện, kể cả "thử một mã", trước 01/12.
