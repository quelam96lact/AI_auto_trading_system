# Báo cáo nghiên cứu đợt 165 — Mốc chuẩn "w% ETF VN30 + phần còn lại gửi tiết kiệm" (ĐĂNG KÝ TRƯỚC)

Ngày thực hiện: 08/10/2026.
Tài liệu tham chiếu:
- `docs/superpowers/plans/2026-10-08-brief-dot-165-moc-chuan-etf-vn30-cong-tien-gui.md`
- `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md`

---

## 1. Dữ liệu và thiết lập đo lường

- **Mã tài sản:** ETF `E1VFVN30` (bảng `bars_daily`).
- **Giai đoạn In-Sample (IS):** 2017-01-03 đến 2022-12-30.
- **Tổng số phiên IS:** 1.498 phiên.
- **Số phiên bị loại vì giá $\le 0$:** 3 phiên (sử dụng `clean_bars` từ `trading/stock_study.py`).
- **Kỷ luật niêm phong:** Dữ liệu từ `2023-01-01` (`SEALED_START`) được bảo vệ nghiêm ngặt bằng `validate_sealed_bars`. Agent **không chạy** tập niêm phong (2023–2026) và **không ghi** vào `docs/holdout-unlock-log.md`.
- **Mô hình chi phí:**
  - Mua ETF: `FEE_RATE + SLIP` = 0,28% + 0,05% = 0,33%.
  - Bán ETF: `FEE_RATE + SELL_TAX_RATE + SLIP` = 0,28% + 0,10% + 0,05% = 0,43%.
  - Tiền gửi: không chịu phí giao dịch và thuế lãi tiền gửi.
  - Cuối kỳ: trừ phí bán giả định phần ETF để so sánh tương đương tiền mặt.

---

## 2. Kết quả đo lường In-Sample (2017–2022)

### 2.1 Bảng chính: Các tổ hợp $w \times$ Tái cân bằng ($r = 9\%$ cố định)

| $w$ | Tái cân bằng | CAGR | Vượt $r$ | MDD | MDD năm tệ | Năm tệ | Số GD | Tổng phí | MDD $\le 4,7\%$ | MDD $\le 7,0\%$ | CAGR $\ge 9,0\%$ |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **5%** | Hàng năm | 9,23% | +0,23% | 0,76% | 0,76% | +6,86% | 6 | 0,044% | **ĐẠT** | **ĐẠT** | **ĐẠT** |
| **10%** | Hàng năm | 9,43% | +0,43% | 2,35% | 2,35% | +4,75% | 6 | 0,087% | **ĐẠT** | **ĐẠT** | **ĐẠT** |
| **15% (Chính)** | **Hàng năm** | **9,60%** | **+0,60%** | **4,33%** | **4,33%** | **+2,63%** | **6** | **0,126%** | **ĐẠT** | **ĐẠT** | **ĐẠT** |
| **20%** | Hàng năm | 9,76% | +0,76% | 6,30% | 6,30% | +0,52% | 6 | 0,163% | K.ĐẠT | **ĐẠT** | **ĐẠT** |
| **25%** | Hàng năm | 9,89% | +0,89% | 8,25% | 8,25% | -1,59% | 6 | 0,197% | K.ĐẠT | K.ĐẠT | **ĐẠT** |
| **30%** | Hàng năm | 10,01% | +1,01% | 10,20% | 10,20% | -3,71% | 6 | 0,229% | K.ĐẠT | K.ĐẠT | **ĐẠT** |
| **5%** | Không | 9,02% | +0,02% | 0,90% | 0,90% | +5,61% | 1 | 0,017% | **ĐẠT** | **ĐẠT** | **ĐẠT** |
| **10%** | Không | 9,03% | +0,03% | 2,77% | 2,77% | +2,45% | 1 | 0,033% | **ĐẠT** | **ĐẠT** | **ĐẠT** |
| **15%** | Không | 9,04% | +0,04% | 5,17% | 5,17% | -0,53% | 1 | 0,050% | K.ĐẠT | **ĐẠT** | **ĐẠT** |
| **20%** | Không | 9,05% | +0,05% | 8,28% | 8,28% | -3,33% | 1 | 0,066% | K.ĐẠT | K.ĐẠT | **ĐẠT** |
| **25%** | Không | 9,06% | +0,06% | 11,23% | 11,23% | -5,98% | 1 | 0,083% | K.ĐẠT | K.ĐẠT | **ĐẠT** |
| **30%** | Không | 9,07% | +0,07% | 14,02% | 14,02% | -8,49% | 1 | 0,099% | K.ĐẠT | K.ĐẠT | **ĐẠT** |

---

### 2.2 Bảng độ nhạy theo lãi suất tiền gửi $r$ (Tái cân bằng hàng năm)

| $w$ | $r$ | CAGR | Vượt $r$ | MDD | Năm tệ | MDD $\le 4,7\%$ | MDD $\le 7,0\%$ | CAGR $\ge 9,0\%$ |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 5% | 0% | 0,67% | +0,67% | 2,94% | -1,67% | **ĐẠT** | **ĐẠT** | K.ĐẠT |
| 10% | 0% | 1,31% | +1,31% | 5,81% | -3,33% | K.ĐẠT | **ĐẠT** | K.ĐẠT |
| 15% | 0% | 1,93% | +1,93% | 8,62% | -5,00% | K.ĐẠT | K.ĐẠT | K.ĐẠT |
| 20% | 0% | 2,53% | +2,53% | 11,36% | -6,66% | K.ĐẠT | K.ĐẠT | K.ĐẠT |
| 25% | 0% | 3,11% | +3,11% | 14,04% | -8,33% | K.ĐẠT | K.ĐẠT | K.ĐẠT |
| 30% | 0% | 3,67% | +3,67% | 16,66% | -9,99% | K.ĐẠT | K.ĐẠT | K.ĐẠT |
| 5% | 5% | 5,42% | +0,42% | 1,04% | +3,07% | **ĐẠT** | **ĐẠT** | K.ĐẠT |
| 10% | 5% | 5,82% | +0,82% | 3,00% | +1,16% | **ĐẠT** | **ĐẠT** | K.ĐẠT |
| 15% | 5% | 6,20% | +1,20% | 4,94% | -0,76% | K.ĐẠT | **ĐẠT** | K.ĐẠT |
| 20% | 5% | 6,55% | +1,55% | 6,88% | -2,67% | K.ĐẠT | **ĐẠT** | K.ĐẠT |
| 25% | 5% | 6,88% | +1,88% | 8,80% | -4,59% | K.ĐẠT | K.ĐẠT | K.ĐẠT |
| 30% | 5% | 7,19% | +2,19% | 10,70% | -6,50% | K.ĐẠT | K.ĐẠT | K.ĐẠT |
| 5% | 7% | 7,32% | +0,32% | 0,86% | +4,97% | **ĐẠT** | **ĐẠT** | K.ĐẠT |
| 10% | 7% | 7,62% | +0,62% | 2,67% | +2,95% | **ĐẠT** | **ĐẠT** | K.ĐẠT |
| 15% | 7% | 7,90% | +0,90% | 4,63% | +0,94% | **ĐẠT** | **ĐẠT** | K.ĐẠT |
| 20% | 7% | 8,15% | +1,15% | 6,58% | -1,08% | K.ĐẠT | **ĐẠT** | K.ĐẠT |
| 25% | 7% | 8,39% | +1,39% | 8,52% | -3,09% | K.ĐẠT | K.ĐẠT | K.ĐẠT |
| 30% | 7% | 8,60% | +1,60% | 10,45% | -5,10% | K.ĐẠT | K.ĐẠT | K.ĐẠT |
| 5% | 9% | 9,23% | +0,23% | 0,76% | +6,86% | **ĐẠT** | **ĐẠT** | **ĐẠT** |
| 10% | 9% | 9,43% | +0,43% | 2,35% | +4,75% | **ĐẠT** | **ĐẠT** | **ĐẠT** |
| **15% (Chính)** | **9%** | **9,60%** | **+0,60%** | **4,33%** | **+2,63%** | **ĐẠT** | **ĐẠT** | **ĐẠT** |
| 20% | 9% | 9,76% | +0,76% | 6,30% | +0,52% | K.ĐẠT | **ĐẠT** | **ĐẠT** |
| 25% | 9% | 9,89% | +0,89% | 8,25% | -1,59% | K.ĐẠT | K.ĐẠT | **ĐẠT** |
| 30% | 9% | 10,01% | +1,01% | 10,20% | -3,71% | K.ĐẠT | K.ĐẠT | **ĐẠT** |

---

### 2.3 Chi tiết từng năm của biến thể chính ($w = 15\%$, tái cân bằng hàng năm, $r = 9\%$)

| Năm | Lợi nhuận danh mục | Tiền gửi ($r=9\%$) | Chênh lệch | MDD trong năm |
|:---:|:---:|:---:|:---:|:---:|
| **2017** | +16,31% | +9,00% | +7,31% | 1,62% |
| **2018** | +5,82% | +9,00% | -3,18% | 3,03% |
| **2019** | +8,19% | +9,00% | -0,81% | 0,70% |
| **2020** | +10,97% | +9,00% | +1,97% | 4,33% |
| **2021** | +14,12% | +9,00% | +5,12% | 1,93% |
| **2022** | +2,63% | +9,00% | -6,37% | 2,48% |

---

## 3. Đối chiếu kỳ vọng trước của Claude (Brief 165 §0)

1. **Kỳ vọng 1:** *"MDD chủ yếu đến từ phần ETF nên tỷ lệ gần tuyến tính theo w: w = 15% sẽ trượt mốc backtest 4,7% (≈ 7%), còn w = 10% nằm sát biên 4,7%."*
   - **Đối chiếu:** **SAI**. Thực tế với $r = 9\%$, lãi tiền gửi liên tục tích lũy làm vùng đệm vốn, giúp MDD của $w = 15\%$ chỉ là **4,33%** (ĐẠT mốc backtest $\le 4,7\%$), và $w = 10\%$ chỉ có MDD **2,35%** (thấp hơn nhiều so với 4,7%). (Chỉ khi $r = 0\%$, $w = 15\%$ mới có MDD 8,62% và $w = 10\%$ có MDD 5,81%).

2. **Kỳ vọng 2:** *"Lãi gần như do giả định lãi suất tiền gửi quyết định. Với r = 9%, mọi w nhỏ đều 'thắng' 9% gần như theo định nghĩa. Vì vậy bảng độ nhạy theo r mới là phần thông tin chính."*
   - **Đối chiếu:** **ĐÚNG**. Với $r = 9\%$, tất cả các mức $w \in \{5\%, 10\%, 15\%, 20\%, 25\%, 30\%\}$ đều đạt CAGR $\ge 9,0\%$ (từ 9,23% đến 10,01%), phần vượt $r$ từ +0,23% đến +1,01%.

---

## 4. Giả định có lợi cho mốc chuẩn

1. **Rút tiền không phạt (No penalty on early withdrawal):** Tiền luân chuyển giữa ETF và tiền gửi tại ngày tái cân bằng đầu mỗi năm được giả định rút và nộp ngay lập tức mà không bị phạt hạ lãi suất không kỳ hạn.
2. **Không trừ thuế thu nhập cá nhân trên lãi tiền gửi:** Mô phỏng tính trọn vẹn lãi kép tiền gửi mà không trừ thuế suất.
3. **Lãi suất tiền gửi $r = 9\%$/năm cố định suốt 2017–2022:** Đây là mức hurdle do chủ dự án cung cấp (spec §1), chưa đối chiếu với lãi suất huy động thực tế của hệ thống ngân hàng Việt Nam theo từng năm lịch sử (2017–2022).

---

## Audit của Claude (08/10/2026)

**Tính lại độc lập** (script riêng, đọc thẳng `bars_daily`, không import code của agent), IS 1.498 phiên 2017-01-03 → 2022-12-30:

| Cấu hình | Agent (bản nộp) | Claude | Sau khi sửa |
|---|---|---|---|
| w=15%, năm, r=9% | 9,60% / 4,33% | 9,59% / 4,33% | 9,59% / 4,33% |
| w=15%, năm, r=0% | 1,93% / 8,62% | 1,93% / 8,62% | 1,93% / 8,62% |
| w=10%, năm, r=9% | 9,43% / 2,35% | 9,42% / 2,35% | 9,42% / 2,35% |

**Ba sửa của Claude** trong `scripts/measure_etf_deposit_mix.py` (không đổi thiết kế, không đổi MDD):
1. `cagr` lấy mốc là tài sản sau phiên đầu (đã trừ phí mua, cộng biến động ngày đầu) thay vì vốn đầu 1,0. Đã sửa để lấy mốc là vốn đầu. Mọi CAGR ở §2 bên trên **giảm khoảng 0,01 điểm %**; số đúng là output chạy lại sau khi sửa (ví dụ biến thể chính 9,59%, không phải 9,60%).
2. Khi chạy `--unlock-holdout`, script in **cả lưới** w × r, trái brief §1.6. Nay chỉ in hai cấu hình đã chốt (w=15%, năm, r=9% và 0%).
3. Bỏ cờ CLI `--log-path`. Log mở niêm phong luôn là `docs/holdout-unlock-log.md`.

**Đọc kết quả** (mô tả, không chọn w):
- Kỳ vọng 1 của Claude sai: tiền gửi có lãi làm đệm, nên MDD **phụ thuộc mạnh vào r**. Với w=15%: MDD 4,33% khi r=9%, nhưng 8,62% khi r=0%. Con số MDD của mốc chuẩn vì vậy chỉ đáng tin đến mức giả định r=9% đáng tin, mà giả định này **chưa kiểm nguồn**.
- Với giả định của spec (r=9%), phương án "15% ETF + tiền gửi, cân bằng năm" **đạt cả ba ngưỡng spec trên IS**: CAGR 9,59% ≥ 9%, MDD 4,33% ≤ 4,7%. Một chiến lược muốn có giá trị phải thắng **9,59% với MDD ≤ 4,33%** trên cùng giai đoạn, không chỉ thắng 9%.
- Phần ETF chỉ đóng góp +0,59 điểm trên tiền gửi ở r=9%. Trong IS, chính ETF (CAGR 2017–2022 = 9,22%, đợt 161) xấp xỉ bằng tiền gửi giả định.

**Chưa làm:** phần niêm phong 2023-01-03 → 30/09/2026. Chờ chủ dự án xác nhận lãi suất tiền gửi tham chiếu, vì nếu r đổi thì phải mở niêm phong lần hai.

## Cập nhật 08/10/2026: lãi suất tham chiếu 6% và mở niêm phong

Chủ dự án chốt lãi suất tiền gửi tham chiếu **6%/năm** (spec mục H, brief §7). Thay đổi này đến **sau** khi đã thấy bảng IS với r = 9% ở trên, và trước khi mở niêm phong. Script đổi `MAIN_RATE = 0.06`, lưới r thêm 6%, cột ngưỡng thành CAGR ≥ 6%.

**IS 2017–2022, r = 6%, tái cân bằng năm** (Claude tính lại độc lập ô w = 15% và w = 10%, khớp tới 0,01 điểm):

| w | CAGR | MDD | Năm tệ | MDD ≤ 4,7% | MDD ≤ 7% | CAGR ≥ 6% |
|---|---|---|---|---|---|---|
| 5% | 6,37% | 0,93% | +4,02% | ĐẠT | ĐẠT | ĐẠT |
| 10% | 6,72% | 2,84% | +2,06% | ĐẠT | ĐẠT | ĐẠT |
| **15%** | **7,04%** | **4,79%** | +0,09% | **K.ĐẠT** | ĐẠT | ĐẠT |
| 20% | 7,34% | 6,73% | −1,87% | K.ĐẠT | ĐẠT | ĐẠT |
| 25% | 7,62% | 8,66% | −3,84% | K.ĐẠT | K.ĐẠT | ĐẠT |
| 30% | 7,88% | 10,58% | −5,80% | K.ĐẠT | K.ĐẠT | ĐẠT |

**Niêm phong 2023-01-03 → 30/09/2026** (930 phiên; mở đúng một lần lúc 14:40:54 08/10, log ở `docs/holdout-unlock-log.md`):

| Cấu hình | CAGR | MDD | Năm tệ |
|---|---|---|---|
| w = 15%, năm, r = 6% | **8,30%** | **2,20%** | +3,06% |
| w = 15%, năm, r = 0% | 3,20% | 2,90% | −0,73% |

**Đọc kết quả:**
- Với r = 6%, biến thể chính **trượt mốc MDD backtest 4,7% trên IS** (4,79%), dù đạt MDD 7% và CAGR 6%. Ở tập niêm phong, nó đạt cả ba ngưỡng, nhờ ETF giai đoạn 2023–2026 tốt hơn 2017–2022. Hai giai đoạn khác nhau nhiều; con số IS bảo thủ hơn.
- **Mốc chuẩn cho mọi chiến lược về sau** (cùng giai đoạn, cùng chi phí): IS 2017–2022 **7,04% / MDD 4,79%**; 2023–09/2026 **8,30% / MDD 2,20%**. Một chiến lược muốn có giá trị phải thắng cả lãi lẫn MDD của mốc này trên cùng giai đoạn.
- Phần ETF đóng góp so với tiền gửi thuần: +1,04 điểm (IS) và +2,30 điểm (niêm phong).
