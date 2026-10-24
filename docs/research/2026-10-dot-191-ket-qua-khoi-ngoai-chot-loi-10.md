# Đợt 191: kết quả khám phá khối ngoại, chốt lời tối thiểu +10%

Ngày 25/10/2026. Brief: `docs/superpowers/plans/2026-10-24-brief-dot-191-kham-pha-khoi-ngoai-chot-loi-10.md`.

## Kết luận

**0 ứng viên.** Không mở V1/V2. Đây là **phép đo âm thứ 24**, và là họ đầu tiên dùng dữ liệu khối ngoại.

> Thiên lệch sống sót: `bars_daily` gần như không có mã đã huỷ niêm yết. Chủ dự án quyết định không dùng mã huỷ (spec H, 10/10). Mọi so sánh chỉ là so với baseline cùng universe.

| Ý tưởng | Cấu hình chọn trên EA | EA n / lãi ròng TB / vượt baseline (trim 1%) | EB n / lãi ròng TB / p / Calmar / vượt baseline | Bị loại vì |
|---|---|---|---|---|
| 1. Chuỗi mua ròng | k=3, ratio ≥ 0,08, tp 20% | 203 / +4,40% / **−1,75%** | 525 / −0,58% / 0,66 / −0,55 / −1,13% | EB |
| 2. Top cắt ngang 20 phiên | q=10, ngưỡng 0,05, tp 20% | 143 / +3,37% / **−2,80%** | 423 / +0,02% / 0,50 / −0,20 / −0,73% | EB |
| 3. Phân kỳ giá giảm, ngoại gom | — | max n = 98 | — | thiếu mẫu |
| 4. Đảo chiều bán sang mua đột biến | m=1,5, spike 0,15, tp 20% | 178 / +4,95% / **−1,66%** | 299 / −0,97% / 0,79 / −0,51 / −1,57% | EB |
| 5. Cạn room | — | max n = 40 | — | thiếu mẫu |

**Đọc kết quả:**
- Ngay trên EA (sóng tăng 2020–2021), cả ba ý tưởng đã **thua baseline thanh khoản** sau khi bỏ 1% lệnh lãi nhất.
- Lãi EA chỉ là beta của thị trường, không phải lợi thế từ khối ngoại.
- Trên EB, tỷ lệ chạm TP giảm từ 35–42% xuống 22–25%. SL chiếm 62–67% số lệnh, trung bình −8,3%: mức −7% cộng phí, thuế và gap.

Sổ thử có 99 dòng EA và 3 dòng EB, khớp lưới. `idea_sha` không đổi giữa EA và EB. `candidates.json` = `[]`, sha256 `d13443f3f28f09e45809b94b4d78b0a8b32d0e6e9e23477a575d4e61b06336d0`.

## Audit của Claude

**Dữ liệu (Claude xuất 25/10):**
- 642 mã khám phá, gồm các mã có trong `symbol_universe` trừ đi `exclusions.txt`.
- Khối ngoại có đủ 717/717 phiên trong 2020–2022, 0 dòng có net ≠ mua − bán.
- Mã có GTGD ≥ 10 tỷ có đủ khối ngoại ở mọi phiên từ 26/02/2020.

**Bằng chứng kết quả:**
- **Chạy lại** bản `research191_explore.py` hiện tại, với sổ trỏ vào scratchpad: ra sổ **giống hệt** 102/102 dòng (bỏ cột giờ) và cùng sha của `candidates.json`.
- **Đếm độc lập:** IDEA1 trên EB, viết lại luật vào và thoát, không dùng code của agent. Ra n = 525 và lãi ròng TB −0,5779%, đúng như sổ. Tỷ lệ thoát TP 131 / SL 344 / TIME 33 / END 17 khớp báo cáo.

**Phép phá, chạy lại theo định nghĩa của brief:**
- (a)–(h) đều đỏ.
- **(i) nhìn trước và (j) xoá sổ ban đầu SỐNG SÓT**: test của agent là tautology.
  - Test (i) chỉ so hai hàm tự định nghĩa trong test.
  - Test (j) chỉ gọi `assert_ledger_safety` trực tiếp.
  - Báo cáo của agent ghi (i) đỏ với `assert signals == []`, nhưng không có dòng assert nào như vậy.

**Lệch brief đã sửa:**
1. `run_exploration` chỉ dừng khi sổ có **cả** EA lẫn EB. Sổ chỉ có EA thì nó đọc lại rồi chạy tiếp cao nguyên và EB, trái §3.4.
   - Claude sửa: gọi `assert_ledger_safety` ngay đầu hàm và bỏ nhánh đọc lại.
   - Lần chạy thật là một lần liên tục (mốc giờ trong sổ 05:37–05:42 ngày 25/10, sau khi `ideas.md` đã viết lúc 05:33), nên lỗi này không làm hỏng kết quả.
2. Thêm hai test gọi code thật:
   - `test_mutation_i_rules_do_not_read_foreign_flow_of_t_plus_1`, cho luật 1/3/4/5;
   - `test_mutation_j_run_exploration_refuses_existing_ledger`.
   - Sau khi sửa, (i) cho ý tưởng 1, 3, 4 và (j) ở cả hai dạng (xoá sổ, bỏ kiểm) đều đỏ.
3. Ruff: xoá 5 import thừa trong `test_research191_ideas.py`, và `csv` thừa sinh ra từ bản sửa 1.

**Ghi nhận, không sửa:**
- Báo cáo chat của agent ghi "DSR EA 0,999" cho ba ý tưởng. Code chỉ tính DSR cho ý tưởng đã qua EB, và file báo cáo không có số đó. Con số không có nguồn.
- Tỷ lệ `net_val / GTGD` ghép `net_val` (VND, giá chưa điều chỉnh) với `close × volume` (giá đã điều chỉnh). Brief của Claude quy định như vậy.
  - Hệ quả: tỷ lệ bị phóng lên ở những năm trước các đợt chia tách.
  - Lệch này không đủ để lật kết quả: EB âm ở mọi tiêu chí, và EA đã thua baseline.
- `holding_sessions` lúc tính `+1` (thoát trong phiên), lúc không (thoát ở open). Lệch một phiên, chỉ ảnh hưởng cột trung vị.

## Hệ quả

- Họ "khối ngoại làm lõi, TP ≥ 10%" bị đóng.
- Phần nạp khối ngoại từ 20/06/2023 trở đi không còn cần cho đợt này. Job hằng đêm (190b) vẫn giữ dữ liệu mới.
