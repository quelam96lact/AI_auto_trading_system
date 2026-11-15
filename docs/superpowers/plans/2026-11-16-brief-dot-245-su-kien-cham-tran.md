# Brief đợt 245: sự kiện chạm trần khoá (ĐĂNG KÝ TRƯỚC)

- **Ngày đăng ký:** 16/11/2026. **Phép đo IS chỉ chạy từ 01/12/2026** = giả thuyết #1 tháng 12. Trước 01/12 chỉ làm hạ tầng (§5 bước 1–2), **không ai tính lợi nhuận sau sự kiện**.
- **Spec:** dòng H ngày 16/11/2026 (đợt 245). Chủ dự án chọn "thử tiếp giá-khối lượng" (16/11) sau khi kiểm kê không có nguồn sự kiện doanh nghiệp từ 2017; Lead chọn họ.
- **Cơ chế:** biên độ giá VN (HOSE 7%, HNX 10%, UPCOM 15%) chặn giá ở trần → cầu dư không khớp hết trong phiên, có thể tràn sang các phiên sau (tiếp diễn). Họ này chưa có trong 32 phép đo âm.
- **Ước lượng trước của Lead:** thấp. Nhà đầu tư cá nhân VN biết rõ "đu trần"; giá mở cửa t+1 thường đã gap lên, có thể ăn hết phần tiếp diễn; chi phí khứ hồi ~0,76%. **0 ứng viên là kết quả hợp lệ.**
- **Cỡ mẫu đã đếm trước (Researcher 16/11, chỉ số đếm):** E3 IS 2017–2022 = 7.623 sự kiện / 1.257 ngày; niêm phong 2023–11/2026 = 4.130 / 865 ngày. Đủ cổng n ≥ 100 ở cả hai tập.

## 1. Dữ liệu

- `data/research244/is/` (2016-01-04 → 2022-12-30, mọi mã trong universe 227 không chia băm; sha256 trong `manifest.json`) cho IS.
- `data/research244/v/` (2022-10-03 → 2026-11-13) cho niêm phong; **Builder không được đọc**; chỉ mở ở bước 6.
- Cảnh báo thiên lệch sống sót (spec H 10/10) và chuỗi giá đã điều chỉnh không hoàn toàn (245 mã bị loại) ghi vào báo cáo.

## 2. Sự kiện (E3, chốt trước)

Tại phiên `t` của mã `m` (không phải chứng chỉ quỹ; mã có nến `t−1`):
- `r_t = close_t / close_{t−1} − 1`; `band` theo sàn trong `exchanges.csv`: HOSE 0,07; HNX 0,10; UPCOM 0,15.
- **Chạm trần:** `r_t ≥ band − 0,005` và `r_t ≤ band + 0,02` (trên mức này coi là ngày điều chỉnh/sai số → bỏ).
- **Đầu chuỗi:** phiên `t−1` của mã không chạm trần.
- **Khoá:** `close_t == high_t`.
- Bỏ phiên đầu tiên mã xuất hiện trong dữ liệu.
- **Thanh khoản:** GTGD trung bình 20 phiên tới `t−1` (`close × volume`) ≥ 1 tỷ.

## 3. Giao dịch (3 cấu hình)

- **Vào:** giá mở cửa phiên `t+1`. Không có nến `t+1` → bỏ, đếm.
- **Ra:** giá đóng cửa phiên `t+H`, `H ∈ {3, 5, 10}` (H = 3 là sớm nhất bán được theo T+2). Thiếu nến ở `t+H` → bán ở nến gần nhất trước đó trong khoảng (`t+1, t+H]`; nếu không có → bỏ, đếm.
- Một mã đang giữ không vào lệnh mới (sự kiện mới của cùng mã trong lúc giữ bị bỏ, đếm).
- **Chi phí:** `FEE_RATE`, `SELL_TAX_RATE`, `SLIPPAGE_BPS` import từ `trading.paper_broker` như `research193_core.simulate_rotation`. Không gõ lại hằng số.
- **Đối chứng:** EW cùng cửa sổ (mở cửa `t+1` → đóng cửa phiên bán) của universe: không phải chứng chỉ quỹ, có nến ở `t+1` và phiên bán, GTGD20 tới `t` ≥ 1 tỷ. `X_i = r_net,i − r_ew,i`.

## 4. Thống kê và cổng

- Mỗi cấu hình: `n`, `mean_X`, trung vị, tỷ lệ `X > 0`, `sharpe_X` theo lệnh, p một phía bằng **bootstrap cụm theo tuần lịch của `t+1`** (10.000 lần, seed 245), Holm trên 3 cấu hình. Báo theo năm, theo sàn (chỉ mô tả).
- **PBO:** `scripts/trial_ledger.pbo_for_exploration` trên ma trận hàng = tháng của `t+1`, cột = H3/H5/H10, giá trị = trung bình `X` của tháng; chỉ báo cáo.
- **Chọn:** cấu hình có `sharpe_X` lớn nhất. **Cao nguyên:** cấu hình láng giềng (theo thứ tự 3↔5↔10) phải cùng dấu `mean_X > 0`; trượt → dừng.
- **Đạt IS:** `n ≥ 100`, `mean_X > 0`, p Holm < 0,05, cao nguyên đạt, **DSR ≥ 0,95** với `n_trials = 3 + PRIOR_NEGATIVE_FAMILIES` (= 35, import từ `scripts/trial_ledger`). Không đạt → phép đo âm thứ 33, không mở niêm phong.
- **Niêm phong (một lần, ghi `docs/holdout-unlock-log.md` trước):** cấu hình đã chọn, `mean_X > 0` và p < 0,05 một phía. Đạt → ứng viên paper forward (spec mục E), kèm cảnh báo: thống kê theo lệnh chưa phải danh mục — MDD danh mục ≤ 4,7% phải đo riêng trước paper.

## 5. Các bước

1. **Builder:** `scripts/research245_core.py` (dò sự kiện §2, lệnh §3, EW, `X`), `scripts/research245_explore.py` (IS → `docs/research/dot245/`), `tests/test_research245_core.py` trên dữ liệu giả. Loader IS **từ chối** ngày > 2022-12-30 (test bắt buộc). Không chạy trên dữ liệu thật trước 01/12. Test bắt buộc: biên `band − 0,005` và `band + 0,02`; đầu chuỗi; khoá; thanh khoản dùng tới `t−1`; T+2 (`H=3`); mã đang giữ; thiếu nến ra; phí bán gồm thuế.
2. **Researcher oracle (trước 01/12, không giá sau sự kiện):** độc lập từ brief, đếm sự kiện E3 IS theo năm (đã có) và so với bộ dò của Builder chạy **chỉ phần dò sự kiện** trên IS (được phép, không tính lợi nhuận); lệch → dừng.
3. **Từ 01/12:** Researcher tính tay ≥ 5 lệnh (seed 245) trước khi ai xem tổng hợp; rồi Builder chạy IS.
4. Lead audit, quyết cổng, ghi spec H.

## 6. Phạm vi file và điều cấm

- **Tạo:** `scripts/research245_core.py`, `scripts/research245_explore.py`, `tests/test_research245_core.py`, `docs/research/dot245/`. Dùng lại bằng import (loader 191, phí như 193, `trial_ledger`, `overfit_core`).
- **Builder KHÔNG:** commit/push; DB; API; docker; `sched.sh`; `npx`; đọc `data/research244/v/`; thêm biến thể/bộ lọc/cấu hình; tính lợi nhuận trên dữ liệu thật trước 01/12.
