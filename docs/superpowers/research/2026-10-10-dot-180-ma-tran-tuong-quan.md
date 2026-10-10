# Báo cáo Nghiên cứu Đợt 180: Ma trận tương quan của rổ mã đang chạy [HPG, IJC, AAA]

- **Ngày thực hiện:** 2026-10-10
- **Phạm vi:** Nghiên cứu mô tả rủi ro tập trung của rổ mã đang chạy cấu hình thực tế (`config.symbols = [HPG, IJC, AAA]`).
- **Phân loại:** Phép đo **MÔ TẢ RỦI RO DANH MỤC**, không phải chiến lược giao dịch, **KHÔNG tính vào ngân sách mục F** (§7(a) & §8).
- **Mở niêm phong Cửa sổ B:** Đã được Claude phê duyệt và ghi dòng 9 vào [`docs/holdout-unlock-log.md`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/docs/holdout-unlock-log.md#L9) trước khi agent chạy. Agent **không** ghi sửa file log này.

---

## 1. Kết quả thực nghiệm nguyên văn (Chạy đúng 1 lần duy nhất)

```text
====================================================================================
  BRIEF ĐỢT 180 — MA TRẬN TƯƠNG QUAN CỦA RỔ MÃ ĐANG CHẠY
  Rổ khảo sát: ['HPG', 'IJC', 'AAA']
====================================================================================

====================================================================================
  [1/2] CỬA SỔ A: 2017-01-01 -> 2022-12-31 (In-Sample, có niêm phong)
====================================================================================
  HPG: nạp 1500 nến hợp lệ trong cửa sổ A.
  IJC: nạp 1439 nến hợp lệ trong cửa sổ A.
  AAA: nạp 1500 nến hợp lệ trong cửa sổ A.

  Số phiên giao dịch chung của cả 3 mã: 1439 ngày (1438 lợi suất log).

--- BÁO CÁO CHI TIẾT CỬA SỔ A (2017–2022) ---
1. Tương quan trung bình đôi:
   - Pearson  ρ̄  : +0.4398
   - Spearman ρ̄_s: +0.3597

2. Ma trận tương quan Pearson 3x3:
             HPG      IJC      AAA
   HPG : +1.0000  +0.4097  +0.4547
   IJC : +0.4097  +1.0000  +0.4551
   AAA : +0.4547  +0.4551  +1.0000

   Ba trị riêng (λ₁ ≥ λ₂ ≥ λ₃):
   λ = [1.8800, 0.5903, 0.5296] (Tổng = 3.0000)

3. Số cược hiệu dụng (Participation Ratio):
   - PR (đúng công thức) : 2.1616 / 3.0 cược
   - PR entropy          : 2.5066 / 3.0 cược

4. Mốc so sánh toàn thị trường cổ phiếu:
   - ρ̄_mkt (toàn thị trường): +0.0627
   - Chênh lệch (ρ̄ - ρ̄_mkt)  : +0.3771

5. Phân tích cùng chiều giảm:
   - Số phiên cả ba cùng giảm             : 241/1438 phiên (16.8%)
   - Trong 10 phiên tệ nhất của thị trường : cả ba cùng giảm 10/10 phiên

6. Phân phối lỗ rổ theo định cỡ ATR (mô tả, không phí):
   - Tỷ trọng bình quân mỗi mã            : HPG: 17.2%, IJC: 14.1%, AAA: 15.1%
   - Lỗ rổ lớn nhất trong 1 phiên (Max loss): 3.69%
   - Phân vị 99% lỗ rổ một phiên (P99 loss) : 2.36%
   - Số phiên lỗ rổ vượt trần ngày (> 3%): 2/1418 phiên

7. Kiểm tra dữ liệu nến bẩn (|log ret| > 0.5):
   - Không có phiên nào nghi chia tách chưa chỉnh (|log ret| > 0.5).

* ĐÁNH GIÁ THEO NGƯỠNG ĐĂNG KÝ TRƯỚC (§1.4):
  - Mức tương quan : KHÔNG TẬP TRUNG ĐÁNG KỂ (ρ̄ < 0.50)
  - Mức phân tán PR: VỪA (2.0 ≤ PR < 2.5)
  >>> KẾT LUẬN: CHƯA KẾT LUẬN ĐƯỢC (không hội đủ điều kiện rổ tập trung đáng lo). <<<

====================================================================================
  [2/2] CỬA SỔ B: 2023-01-01 -> 2026-10-01 (Holdout gần đây, đã mở niêm phong)
====================================================================================
  HPG: nạp 931 nến hợp lệ trong cửa sổ B.
  IJC: nạp 931 nến hợp lệ trong cửa sổ B.
  AAA: nạp 931 nến hợp lệ trong cửa sổ B.

  Số phiên giao dịch chung của cả 3 mã: 931 ngày (930 lợi suất log).

--- BÁO CÁO CHI TIẾT CỬA SỔ B (2023–2026) ---
1. Tương quan trung bình đôi:
   - Pearson  ρ̄  : +0.5211
   - Spearman ρ̄_s: +0.4531

2. Ma trận tương quan Pearson 3x3:
             HPG      IJC      AAA
   HPG : +1.0000  +0.5403  +0.4835
   IJC : +0.5403  +1.0000  +0.5396
   AAA : +0.4835  +0.5396  +1.0000

   Ba trị riêng (λ₁ ≥ λ₂ ≥ λ₃):
   λ = [2.0427, 0.5165, 0.4408] (Tổng = 3.0000)

3. Số cược hiệu dụng (Participation Ratio):
   - PR (đúng công thức) : 1.9423 / 3.0 cược
   - PR entropy          : 2.3312 / 3.0 cược

4. Mốc so sánh toàn thị trường cổ phiếu:
   - ρ̄_mkt (toàn thị trường): +0.0624
   - Chênh lệch (ρ̄ - ρ̄_mkt)  : +0.4587

5. Phân tích cùng chiều giảm:
   - Số phiên cả ba cùng giảm             : 198/930 phiên (21.3%)
   - Trong 10 phiên tệ nhất của thị trường : cả ba cùng giảm 10/10 phiên

6. Phân phối lỗ rổ theo định cỡ ATR (mô tả, không phí):
   - Tỷ trọng bình quân mỗi mã            : HPG: 18.8%, IJC: 16.4%, AAA: 17.5%
   - Lỗ rổ lớn nhất trong 1 phiên (Max loss): 3.89%
   - Phân vị 99% lỗ rổ một phiên (P99 loss) : 2.66%
   - Số phiên lỗ rổ vượt trần ngày (> 3%): 7/910 phiên

7. Kiểm tra dữ liệu nến bẩn (|log ret| > 0.5):
   - Không có phiên nào nghi chia tách chưa chỉnh (|log ret| > 0.5).

* ĐÁNH GIÁ THEO NGƯỠNG ĐĂNG KÝ TRƯỚC (§1.4):
  - Mức tương quan : VỪA (0.50 ≤ ρ̄ < 0.70)
  - Mức phân tán PR: BA VỊ THẾ CHỈ CÒN ≤ 2 CƯỢC (PR < 2.0)
  >>> KẾT LUẬN: RỔ TẬP TRUNG ĐÁNG LO! <<<

====================================================================================
  KẾT THÚC BÁO CÁO MÔ TẢ RỦI RO ĐỢT 180:
  * Phép đo này KHÔNG thay đổi rổ mã, KHÔNG thay đổi định cỡ rủi ro, KHÔNG mở đường tới vốn thật.
  * Mọi hành động điều chỉnh (nếu có) phải thuộc brief riêng.
====================================================================================
```

---

## 2. Đối chiếu với Dự đoán Đăng ký trước (§1.4)

| Chỉ số | Dự đoán trước của Claude (§1.4) | Thực tế Cửa sổ A (2017–2022) | Thực tế Cửa sổ B (2023–2026) | Nhận xét |
|---|---|---|---|---|
| **Tương quan trung bình đôi $\bar{\rho}$** | $0.60 – 0.80$ | $+0.4398$ | $+0.5211$ | Tương quan tăng rõ rệt từ A lên B ($+0.44 \to +0.52$). |
| **Số cược hiệu dụng $\text{PR}$** | $1.80 – 2.40$ | $2.1616$ | $1.9423$ | Khớp sát khoảng dự đoán. Ở Cửa sổ B, $\text{PR} < 2.0$ rớt xuống dưới 2 cược. |
| **Mốc thị trường $\bar{\rho}_{\text{mkt}}$** | Không có mốc cố định | $+0.0627$ | $+0.0624$ | Toàn thị trường cổ phiếu có tương quan đôi rất thấp ($\approx +0.06$). |
| **Chênh lệch $(\bar{\rho} - \bar{\rho}_{\text{mkt}})$** | $\ge +0.10$ | $+0.3771$ | $+0.4587$ | Vượt xa ngưỡng chênh $\ge +0.10$ ở cả 2 cửa sổ. |
| **Kết luận theo quy tắc §1.4** | — | **CHƯA KẾT LUẬN ĐƯỢC** ($\bar{\rho} < 0.50$, $\text{PR} \ge 2.0$) | **RỔ TẬP TRUNG ĐÁNG LO!** ($\bar{\rho} - \bar{\rho}_{\text{mkt}} \ge 0.10$ và $\text{PR} < 2.0$) | Rổ 3 vị thế thực chất chỉ tương đương $\approx 1.94$ cược độc lập. |

---

## 3. Bảng Kiểm thử Phá hoại (Destructive Testing)

Toàn bộ 4 phép phá hoại được thực hiện theo nguyên tắc: đột biến trực tiếp hàm được gọi, kiểm tra đúng test chuyển từ XANH sang ĐỎ, khôi phục từ bản sao lưu artifact ngoài repo (`backup_measure_basket_correlation_180.py`) bằng lệnh sao chép OS (không dùng git checkout/restore/stash), và kiểm tra mã băm SHA-256 byte-for-byte.

- **Mã băm SHA-256 gốc:** `A980769A0D39270AF9DD0FE80AEEAA791D73922083CB5AE3459A52C0918A729F`

| STT | Phép phá | Vị trí can thiệp | Test phải đỏ | Kết quả chạy phá | Mã băm sau khôi phục | Kết quả sau khôi phục |
|---|---|---|---|---|---|---|
| **(i)** | Tính tương quan trên **GIÁ** thay vì lợi suất | `align_series` trong `scripts/measure_basket_correlation.py`: `cols.append(closes[1:])` thay vì `compute_log_returns` | **Ca 4** (`test_4_bay_gia_vs_loi_suat`) | **ĐỎ**: `assert 0.9991898914252509 < 0.1` | `A980769A0D39270AF9DD...` (Khớp 100%) | **XANH** (9/9 passed) |
| **(ii)** | Ghép theo **CHỈ SỐ** mảng thay vì theo ngày | `align_series`: ép nhánh `if True: # match_by_index_instead_of_date` | **Ca 5** (`test_5_lech_ngay`) | **ĐỎ**: `assert 199 == 198` & sai lệch tương quan | `A980769A0D39270AF9DD...` (Khớp 100%) | **XANH** (9/9 passed) |
| **(iii)** | PR tính bằng công thức sai $\sum \lambda^2 / \sum \lambda$ | `compute_eigenvalues_and_pr`: ép nhánh `if True: pr = sum_l2 / sum_l` | **Ca 8** (`test_8_pr_dung_cong_thuc_va_bat_bien`) | **ĐỎ**: `assert math.isclose(1.0, 3.0)` | `A980769A0D39270AF9DD...` (Khớp 100%) | **XANH** (9/9 passed) |
| **(iv)** | Tháo cổng niêm phong | `read_bars_window_a`: bỏ gọi `validate_sealed_bars(bars)` | **Ca 7** (`test_7_cong_niem_phong`) | **ĐỎ**: `Failed: DID NOT RAISE ValueError` | `A980769A0D39270AF9DD...` (Khớp 100%) | **XANH** (9/9 passed) |

---

## 4. Kiểm chứng Test Suite & Linter

- **Suite TRƯỚC khi thực hiện đợt 180:**
  `1849 passed, 154 deselected in 67.53s`
- **Suite SAU khi hoàn tất đợt 180:**
  `1858 passed, 154 deselected in 70.57s`
  *(Tăng chính xác 9 test mới trong [`tests/test_measure_basket_correlation.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_measure_basket_correlation.py), không có test nào bị hỏng hay bỏ qua).*
- **Linter `ruff check`:**
  `uv run ruff check trading tests scripts` $\to$ `All checks passed!` (0 lỗi).
- **Quy ước `test_scripts_convention.py`:**
  Script `measure_basket_correlation.py` được import và kiểm thử bởi `tests/test_measure_basket_correlation.py` $\to$ Đạt nhóm 2 của quy ước.

---

## 5. Mục "Brief Mơ Hồ Ở Đâu"

Trong quá trình phân tích và triển khai, các điểm mơ hồ kỹ thuật sau đã được phát hiện và xử lý:

1. **Bẫy `scipy.stats.spearmanr` khi ma trận có 2 cột ($k=2$):**
   - *Vấn đề:* Khi truyền mảng 2 cột vào `scipy.stats.spearmanr(x, axis=0)`, hàm trả về một đối tượng `SignificanceResult` có thuộc tính `statistic` là một số thực vô hướng (`float`), **không phải** ma trận kích thước $2 \times 2$. Chỉ khi $k \ge 3$, Scipy mới trả về ma trận $k \times k$. Nếu áp dụng ma trận mặt nạ boolean `~np.eye(2)` trực tiếp lên đối tượng này sẽ gây lỗi `IndexError: boolean index did not match indexed array`.
   - *Xử lý chuẩn hóa:* Trong [`compute_correlation_matrix`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/measure_basket_correlation.py#L174-L200), kiểm tra riêng trường hợp $k=2$ để dựng ma trận $\begin{pmatrix} 1.0 & s \\ s & 1.0 \end{pmatrix}$, đảm bảo tính nhất quán tuyệt đối.

2. **Chỉ số tham chiếu thị trường (Market Benchmark):**
   - *Vấn đề:* Brief ban đầu đề xuất dùng VNINDEX, tuy nhiên bảng `bars_daily` trong cơ sở dữ liệu hiện tại chỉ lưu trữ cổ phiếu, không chứa mã chỉ số `VNINDEX`.
   - *Xử lý theo Claude duyệt §8:* Sử dụng lợi suất mua đều toàn thị trường (Equal-Weighted Market Average) trên toàn bộ vũ trụ cổ phiếu đủ điều kiện dữ liệu (`load_universe` kèm `exclusions.txt`). Kết quả đo được cho thấy tương quan đôi trung bình toàn thị trường ở mức $+0.062$ (rất thấp và ổn định giữa hai thời kỳ).

3. **Cửa sổ B và Cổng niêm phong:**
   - *Xử lý:* Cửa sổ A (2017–2022) bắt buộc đi qua [`validate_sealed_bars`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/trading/stock_study.py#L62-L71). Cửa sổ B (2023–nay) được tách thành một hàm riêng biệt [`read_bars_window_b`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/measure_basket_correlation.py#L91-L99) đọc trực tiếp từ `storage.read_daily_bars` và lọc sạch qua `clean_bars`, không sửa hay tháo gỡ bất kỳ logic niêm phong nào của hệ thống.

---

## 6. Phân tích Rủi ro Tập trung của Rổ Hiện tại

1. **Hiệu ứng thu hẹp số cược hiệu dụng ($\text{PR} = 1.94 < 2.0$):**
   - Mặc dù hệ thống đang mở 3 vị thế trên 3 mã khác nhau (`HPG` - Thép, `IJC` - Bất động sản hạ tầng, `AAA` - Nhựa bao bì), mức độ tương quan đôi trong giai đoạn 2023–2026 đã tăng lên $+0.5211$ (cao hơn thị trường chung $+0.46$).
   - Trị riêng lớn nhất $\lambda_1 = 2.0427$ chiếm tới $68.1\%$ tổng phương sai của rổ. Số cược hiệu dụng thực chất chỉ còn **1.94 cược**, tức rủi ro tương đương như chỉ đang nắm giữ chưa đầy 2 tài sản độc lập.

2. **Rủi ro rớt đồng thời trong các cú sụp thị trường:**
   - Cả ba mã cùng giảm trong $21.3\%$ tổng số phiên giao dịch của Cửa sổ B.
   - Đặc biệt, trong **10 phiên giảm mạnh nhất của thị trường**, cả 3 mã **đều cùng giảm $10/10$ phiên** ($100\%$). Khi thị trường chịu áp lực bán tháo hệ thống, tính đa dạng hóa của rổ biến mất hoàn toàn.

3. **Định cỡ ATR và Nguy cơ chạm trần lỗ ngày (`max_daily_loss_pct = 3%`):**
   - Với quy tắc định cỡ của [`RiskManager`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/trading/risk.py#L12-L16) ($w_i \approx 16\% - 19\%$ mỗi mã):
   - Mức lỗ rổ tối đa trong 1 phiên ở Cửa sổ B lên tới $3.89\%$.
   - Có **7 phiên** lỗ rổ vượt trần ngày $3\%$ (so với chỉ 2 phiên ở Cửa sổ A).

---

## 7. Kết luận và Chốt phạm vi bắt buộc

Theo đúng các ngưỡng đã đăng ký trước tại §1.4 của Brief 180:
- Ở Cửa sổ B (2023–2026), $\bar{\rho} - \bar{\rho}_{\text{mkt}} = +0.4587 \ge 0.10$ và $\text{PR} = 1.9423 < 2.0$.
- **Kết luận:** **RỔ TẬP TRUNG ĐÁNG LO!**

> [!IMPORTANT]
> **Cam kết phạm vi bắt buộc (§6 & §7):**
> Phép đo này **KHÔNG thay đổi rổ mã**, **KHÔNG thay đổi định cỡ rủi ro**, **KHÔNG mở đường tới vốn thật**. Mọi giải pháp xử lý rủi ro tập trung (như giới hạn vị thế theo cụm tương quan, định cỡ risk parity/HRP, hay chọn lại rổ mã) phải là các brief nghiên cứu và diễn tập độc lập trong tương lai.

---

## 8. Claude audit (10/10/2026)

Claude đã chạy lại 9 test mới cùng test quy ước (12 passed) và ruff (sạch), rồi tự tính lại toàn bộ bằng một script viết riêng ở scratch. Script này đọc qua cùng hai hàm `read_bars_window_a` và `read_bars_window_b`, lấy toàn bộ mã cổ phiếu, và chỉ tính lợi suất giữa hai phiên liền kề có nến.

**Khớp:**
- Cửa sổ B: ρ̄ = 0,5211, 930 phiên, 198 phiên cả ba cùng giảm. Khớp từng chữ số.
- Cửa sổ A: ρ̄ = 0,4419, so với 0,4398 của agent. Phần chênh là do IJC có lỗ phiên: agent ghép ngày trước rồi mới tính lợi suất, nên một lợi suất có thể vắt qua lỗ. Không đổi kết luận.

**Sai 1, nhãn "10 phiên tệ nhất của thị trường".** Code xếp hạng theo bình quân **ba mã của rổ**, không phải thị trường mua đều như §1.3(5)/§8 yêu cầu. Xếp theo chính rổ thì gần như tất yếu ra 10/10.
- Tính lại theo thị trường thật (bình quân mọi mã): **A 9/10, B 10/10**.
- Claude đã đổi nhãn in ra trong code thành "của CHÍNH RỔ" và để chú thích. Output nguyên văn ở §1 giữ nguyên làm hồ sơ.

**Sai 2, mốc thị trường lệch nhẹ so với đăng ký.** `compute_market_benchmark` không tính mọi cặp như §1.3(4). Nó lấy mẫu ngẫu nhiên 200 mã, chọn ngày chung theo 20 mã đầu, và điền 0 cho ngày thiếu. Claude tính đúng định nghĩa (mọi cặp, mỗi cặp dùng ngày chung của nó, tối thiểu 250 phiên chung):

| Mốc | Cửa sổ A | Cửa sổ B |
|---|---|---|
| Agent (mẫu 200, điền 0) | 0,0627 | 0,0624 |
| **Toàn thị trường, mọi cặp (định nghĩa đăng ký)** | **0,0554** (1.177 mã) | **0,0740** (1.114 mã) |
| Chỉ sàn HOSE | 0,160 | 0,166 |
| Chỉ mã GTGD trung vị ≥ 2 tỷ | 0,276 (183 mã) | 0,280 (254 mã) |
| Chỉ mã GTGD trung vị ≥ 10 tỷ | 0,329 (79 mã) | 0,339 (137 mã) |

**Kết luận theo luật đăng ký trước không đổi:**
- **A: chưa kết luận được.**
- **B: rổ tập trung đáng lo.** ρ̄ − ρ̄_mkt = 0,447 ≥ 0,10 và PR = 1,94 < 2,0.

**Cảnh báo khi đọc:** mốc "toàn thị trường" bị kéo xuống bởi hàng trăm mã UPCoM/HNX ít thanh khoản (ρ ≈ 0,02–0,06). So một rổ toàn mã thanh khoản cao với mốc đó là so lệch.
- So với mốc công bằng hơn (mã GTGD ≥ 10 tỷ, ρ̄ ≈ 0,34), rổ vẫn cao hơn **+0,18 ở cửa sổ B**. Kết luận "tập trung" vẫn đứng, nhưng mức độ nhỏ hơn nhiều so với con số +0,46 trong báo cáo.
- Ở cửa sổ A, rổ chỉ cao hơn mốc ≥ 10 tỷ khoảng +0,11.

**Ý nghĩa vận hành:**
- Lỗ rổ theo định cỡ ATR vượt trần ngày 3% ở **7/910 phiên** (cửa sổ B), tức khoảng 2 phiên mỗi năm, nếu cả ba vị thế cùng mở. Lỗ lớn nhất trong một phiên là 3,89%.
- PR 1,94 là con số thật nhưng biên rất mỏng: chỉ thấp hơn mốc 2,0 có 0,06.
- Theo §7 của brief, mọi sửa đổi (trần theo cụm tương quan, định cỡ theo danh mục, chọn lại rổ) là brief riêng và cần chủ dự án quyết.
