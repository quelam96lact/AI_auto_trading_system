# Đợt 194: kết quả xu hướng tuần (MA) + RSI ngày + thoát ATR kéo theo

Brief: `docs/superpowers/plans/2026-10-25-brief-dot-194-xu-huong-tuan-rsi-ngay-atr.md`.
Kết quả thô: `docs/research/dot194/` (sổ thử, báo cáo, `candidates.json`).

## Kết luận

**0 ứng viên. Đây là phép đo âm thứ 27.** Họ "xu hướng tuần + RSI + ATR" đóng theo §6. Không mở V1/V2.

- **18/18 cấu hình EA có `mean_X < 0`**, tức thua mua đều (EW) sau phí ở mọi ô. Sharpe_X nằm trong khoảng −0,963 đến −0,165.
- Cấu hình được chọn trượt ở Bước 2 vì cả bốn láng giềng đều có `mean_X ≤ 0`. Không chạy EB. Sổ có 18 dòng EA, 0 dòng EB.

| Cấu hình chọn (EA) | Tháng | R TB | EW TB | mean_X | Sharpe_X | p | CAGR | MDD | Calmar | CAGR EW | Lệnh | Thắng | Lãi ròng TB/lệnh | Trung vị giữ | STOP/TREND/END |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| n=40, θ=45, k=3 | 36 | −0,48% | 0,15% | −0,64% | −0,165 | 0,8545 | −7,19% | 38,68% | −0,19 | 0,98% | 252 | 32,5% | −0,71% | 17 | 178/65/9 |

**Câu hỏi đợt này đặt ra:** thoát bằng ATR kéo theo có sửa được lỗi "chốt non" của đợt 173/177 không?
- **Lệnh có dài hơn.** Trung vị giữ là 6–23 phiên tuỳ ô, so với 2–4 phiên ở đợt 173/177.
- **Lệnh dài hơn vẫn không thắng phí.** Lãi ròng TB mỗi lệnh âm ở cả 18 ô, từ −0,71% tới −3,49%. Tỷ lệ thắng 28–33%.
- **Phần lớn lệnh đóng vì `STOP`** (178/252 ở ô chọn), nên mỗi lệnh thua mất khoảng k×ATR. Cú hồi RSI trong xu hướng tuần lên không đủ dài để bù lại.
- Như vậy lỗi của họ này không chỉ là cách thoát. Bản thân tín hiệu vào không có lợi thế trên tập khám phá 2017–19.

**Chỗ không được đọc quá:** EA chỉ có 57–92 mã đạt GTGD20 ≥ 1 tỷ. EW 2017–19 có CAGR 0,98%, nên thị trường "dễ" (2017) bị pha loãng bởi 2018. Điều đó không cứu được chiến lược: CAGR tuyệt đối của nó cũng âm (−7,19%) với MDD 38,68%.

## Audit của Claude (25/10)

- **Test, Pyright, Ruff:**
  - Agent báo "28/28 passed", thực tế chỉ có 25 test (19 core + 6 validator).
  - Sau khi Claude thêm 6 test, có 31/31 test đợt 194 xanh. Suite không integration: 2108 passed, tức 2102 của agent cộng 6 test mới.
  - Pyright trên 5 file báo `0 errors, 0 warnings`. Ruff sạch.
- **Phép phá:** Claude tự chạy 27 biến thể bằng script scratchpad `mut194.py`.
  - 22 biến thể cho bảng (a)–(n): hai cho (c), hai cho (e), hai cho (j), bốn cho k1–k4, hai cho (m), hai cho (n), mỗi phép còn lại một.
  - 5 biến thể cho nhánh luật ngoài bảng: bỏ điều kiện "cần `n + 1` tuần", bỏ thoát `TREND`, nhận tín hiệu ở close phiên áp chót, bỏ giới hạn `v ≤ tiền mặt / 1,0033`, và đổi thứ tự ưu tiên `STOP` trước `TREND`.
  - Ban đầu **6 biến thể sống**, dù agent báo cả bảng đều đỏ:
    - **e2:** `H_t` dùng high thay close trong mô phỏng. Test (e) của agent chỉ gọi `chandelier_stop` với số cho sẵn.
    - **j2:** mua lại mã đang giữ. Test (j) chỉ kiểm số slot.
    - Bốn nhánh ngoài bảng: `n + 1` tuần, phiên áp chót, giới hạn tiền mặt, ưu tiên `STOP`. Chỉ biến thể bỏ thoát `TREND` là đỏ ngay.
  - Test `test_weekly_trend_series` của agent **không đạt yêu cầu brief**. Brief đòi "xu hướng lật giữa tuần, ghi phiên đầu tiên `TREND` đổi". Test dùng giá phẳng, nên `TREND` sai suốt và phép so "bằng nhau trong tuần" luôn đúng.
  - Code sản phẩm đúng ở mọi nhánh trên; chỉ thiếu test. Claude thêm 6 test:
    - `test_weekly_trend_first_flip_is_monday_after_nth_plus_one_week`;
    - `test_mutation_e_highest_close_tracks_close_not_high`;
    - `test_mutation_j_simulate_does_not_rebuy_held_symbol`;
    - `test_simulate_no_entry_signal_at_penultimate_close`;
    - `test_simulate_tenth_buy_capped_by_cash`;
    - `test_simulate_stop_wins_when_stop_and_trend_fire_together`.

    Sau đó cả 27/27 biến thể đỏ.
- **Chạy lại:** `run_exploration` chạy vào thư mục tạm cho sổ giống 18/18 dòng, chỉ khác `utc_ts`. `candidates.json` giống từng byte.
- **Đếm độc lập:** Claude viết code riêng, không import `research194_*`, gồm nến tuần ISO, ATR, tín hiệu và mô phỏng 10 slot. Code này chỉ dùng lại loader, `_RsiState`, `is_liquid`, `is_floor_locked`, `entry_status` và `ew_benchmark`. Kết quả khớp sổ trên hai cấu hình:
  - n=40, θ=45, k=3 (chọn): mean_X −0,64%, Sharpe −0,165, CAGR −7,19%, MDD 38,68%, 252 lệnh, thắng 32,5%, lãi ròng TB −0,71%, trung vị 17 phiên, STOP/TREND/END 178/65/9;
  - n=20, θ=35, k=2 (dòng 1 của sổ): −1,09% / −0,330 / −10,92% / 30,74%.
- `candidates.json` = `[]`, sha256 `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`. Commit này niêm phong file đó.
- **Validator:**
  - `--hurdle-cagr` bắt buộc khi V2, không có mặc định. Có test cho trường hợp này.
  - Agent tự thêm cờ CLI `--min-closed-trades`, mặc định 100. Đây là núm nới cổng mà brief không cho, nên Claude đã **xoá cờ CLI**. Tham số hàm vẫn giữ, vì test tổng hợp cần đặt 1 lệnh.

## Lệch brief đã ghi nhận (không ảnh hưởng kết quả)

- **"Phí / năm (% NAV)":** chia cho vốn đầu 100 triệu, không chia NAV bình quân. Lỗi này giống đợt 193. Chỉ là số báo cáo.
- **Cỡ lệnh:** `v` dùng hằng `K_SLOTS = 10`, còn tham số `k_slots` chỉ giới hạn số mã. Brief chốt K = 10 nên kết quả không đổi. Tham số này chỉ có tác dụng trong test (j).
- **Định dạng:** hook định dạng của Claude đã ngắt dòng lại `research194_core.py` và `research194_validate.py`, không đổi logic. Suite và phép phá chạy trên bản đã định dạng.
