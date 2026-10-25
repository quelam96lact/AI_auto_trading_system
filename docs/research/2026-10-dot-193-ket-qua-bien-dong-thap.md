# Đợt 193: kết quả danh mục biến động thấp xoay vòng tháng

Brief: `docs/superpowers/plans/2026-10-25-brief-dot-193-danh-muc-bien-dong-thap.md`.
Kết quả thô: `docs/research/dot193/` (sổ thử, báo cáo, `candidates.json`).

## Kết luận

**0 ứng viên. Đây là phép đo âm thứ 26.** Họ biến động thấp đóng theo §6. Không mở V1/V2.

- Cả hai ý tưởng trượt ở Bước 2 (cao nguyên), nên không chạy EB. Sổ có 18 dòng EA, 0 dòng EB.
- Khác 25 lần trước, lần này **không phải phí giết chiến lược**. 14/18 cấu hình có `mean_X > 0` sau phí. Lý do trượt là kết quả không ổn định giữa các cấu hình láng giềng.

| Ý tưởng, cấu hình chọn (EA) | Tháng | R TB | EW TB | mean_X | Sharpe_X | p | CAGR | MDD | Calmar | Láng giềng trượt |
|---|---|---|---|---|---|---|---|---|---|---|
| I1 LOWVOL L=250, N=20 | 35 | 0,90% | 0,15% | 0,75% | 0,313 | 0,030 | 10,45% | 18,01% | 0,58 | L=120, N=20: Sharpe 0,124 < 0,157 |
| I2 LOWMAX W=120, N=20 | 35 | 0,52% | 0,15% | 0,37% | 0,180 | 0,122 | 5,39% | 21,41% | 0,25 | W=60, N=20: 0,035; W=120, N=15: 0,028 (< 0,090) |

**Chỗ không được đọc quá:**
- LOWVOL chỉ mạnh ở `L = 250`: N=15 có Sharpe 0,300 và p 0,036, N=20 có 0,313 và p 0,030. Ở `L = 60` và `L = 120`, Sharpe chỉ 0,10–0,18.
- Luật đăng ký trước là **không đổi đỉnh, không thu hẹp lưới**. "Thử lại riêng L = 250" sau khi đã thấy số chính là chọn sau khi xem. Nó cũng phải gánh 18 + 25 = 43 phép thử đã có trong DSR.
- Kể cả EA đạt, Calmar 0,58 vẫn dưới ngưỡng 0,86 của Bước 3. CAGR 10,45% của 2017–19 cũng chưa so với mốc ETF + tiền gửi.

## Audit của Claude (25/10)

- **Test, Pyright, Ruff:** 17/17 test đợt 193 xanh. Pyright trên 5 file báo `0 errors, 0 warnings`. Ruff sạch.
- **Phép phá:** Claude tự chạy 15 biến thể bằng script scratchpad `mut193.py`, gồm (a)–(e), (g), (h), ba biến thể (f), hai biến thể (i) và hai biến thể (j).
  - Ban đầu 14/15 đỏ.
  - **f1 sống:** bỏ phí ở phần bán bớt (mã vẫn trong danh sách nhưng vượt tỷ trọng) mà mọi test vẫn xanh, vì không test nào có lần bán bớt. Code sản phẩm đúng; chỉ thiếu test.
  - Claude thêm `test_mutation_f_trim_sell_pays_fee_in_cash` (tính tay, N = 2, A tăng 50% rồi bị bán bớt). Sau đó cả 15/15 đỏ.
  - (j) lần này gọi thật tới `deflated_sharpe` qua hàm riêng `compute_step4_dsr`, nên lỗi của đợt 192 không lặp lại.
- **Chạy lại:** `run_exploration` chạy vào thư mục tạm cho sổ giống 18/18 dòng (chỉ khác `utc_ts`). `candidates.json` và `exploration_report.md` giống từng byte.
- **Đếm độc lập:** Claude viết code riêng, đọc thẳng CSV, không import `research193_*` (chỉ lấy hằng số phí). Kết quả khớp sổ tới chữ số cuối trên ba cấu hình:
  - LOWVOL L=250, N=20: mean_X 0,007480, Sharpe 0,3133, CAGR 0,1045, MDD 0,1801;
  - LOWVOL L=120, N=20 (láng giềng làm trượt): 0,003104 / 0,1236 / 0,0482 / 0,2185;
  - LOWMAX W=120, N=20: 0,003721 / 0,1796 / 0,0539 / 0,2141.
- `candidates.json` = `[]`, sha256 `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`. Commit này niêm phong file đó.
- **Validator:** có đủ test sha sai, ĐẠT tổng hợp và TRƯỢT tổng hợp như §5 yêu cầu.

## Lệch brief đã ghi nhận (không ảnh hưởng kết quả)

- **`ew_benchmark`:** đòi ≥ 20 nến tới `r⁻`, trong khi "§3.2 với L = 20" là ≥ 21. Phép đếm độc lập dùng ≥ 21 và cho EW TB giống hệt (0,001520), nên trên dữ liệu này không có tác động.
- **"Phí / năm (% NAV)":** chia cho vốn đầu 100 triệu, không chia cho NAV bình quân. Chỉ là số báo cáo, không vào cổng nào.
- **Validator V2:** `--hurdle-cagr` vẫn mặc định 0,10, lỗi giống đợt 192. Không dùng tới; nếu dùng thì Claude luôn truyền mốc tính lại.
- **`R_m`:** dùng NAV **sau** giao dịch ở `L(m)`, nên phí xoay vòng tháng m tính vào tháng m. Brief không nói NAV trước hay sau giao dịch; cách này bảo thủ.
