# Biểu phí phái sinh có nguồn: Thuế TNCN và Phí bù trừ VSDC

Tài liệu đặc tả nguồn gốc pháp lý và công thức chi phí giao dịch Hợp đồng tương lai chỉ số VN30 (VN30F).  
Căn cứ: Brief đợt 95 (26/09/2026).  
Người nghiên cứu: Gemini Flash 3.8. Người audit: Claude.

---

## Bảng tổng hợp biểu phí và thuế áp dụng cho tài khoản VN30F (Gói có chuyên viên TVCK tại SSI)

| Thành phần | Mức thu / Công thức | Đơn vị thu | Cơ chế thu | Nguồn pháp lý & tài liệu | Trạng thái |
|---|---|---|---|---|---|
| **Phí dịch vụ SSI** | 3.000 đ / HĐ | SSI | Mỗi lượt (mở & đóng) | Biểu giá SSI hiệu lực 10/10/2025 | `RESOLVED` |
| **Phí giao dịch HNX** | 2.700 đ / HĐ / giao dịch | HNX (SSI thu hộ) | Mỗi lượt (mở & đóng) | Thông tư 83/2024/TT-BTC & Biểu giá SSI | `RESOLVED` |
| **Phí bù trừ VSDC** | 2.550 đ / HĐ | VSDC (SSI thu hộ) | Mỗi lượt (mở & đóng) | Thông tư 83/2024/TT-BTC & Quy chế VSDC | `RESOLVED` |
| **Thuế TNCN** | `(Giá khớp x 100.000 x Qty x 17% / 2) x 0,1%` | Ngân sách Nhà nước | Mỗi lượt chuyển nhượng (mở & đóng) | CV 11133/BTC-CST, TT 87/2026/TT-BTC | `RESOLVED` |
| **Phí quản lý ký quỹ** | 0,0024%/tháng (tối thiểu 100.000 đ, tối đa 1.600.000 đ) | VSDC (SSI thu hộ) | Theo tháng (không theo lệnh) | Biểu giá SSI & Thông tư 83/2024/TT-BTC | `RESOLVED` (Không mô hình vào broker) |

---

## Chi tiết nghiên cứu theo yêu cầu Brief 95

### 1a. Thuế TNCN trên giao dịch hợp đồng tương lai chỉ số

- **Trạng thái:** `RESOLVED`
- **Văn bản pháp lý gốc và hiện hành:**
  1. **Công văn số 11133/BTC-CST ngày 21/08/2017 của Bộ Tài chính** về chính sách thuế và giá dịch vụ đối với chứng khoán phái sinh (văn bản hướng dẫn chuyên biệt đầu tiên đặt ra công thức tính thuế cho HĐTL).
  2. **Luật Thuế thu nhập cá nhân** (Luật số 04/2007/QH12, sửa đổi bởi Luật số 26/2012/QH13 và Luật số 71/2014/QH13).
  3. **Thông tư số 92/2015/TT-BTC** (sửa đổi Điều 11 Thông tư số 111/2013/TT-BTC) và **Thông tư số 87/2026/TT-BTC** của Bộ Tài chính hướng dẫn về thuế TNCN đối với chuyển nhượng chứng khoán phái sinh.
- **URL tham chiếu:**
  - `https://thuvienphapluat.vn/cong-van/Thue-Phi-Le-Phi/Cong-van-11133-BTC-CST-2017-chinh-sach-thue-gia-dich-vu-chung-khoan-phai-sinh-360057.aspx`
  - `https://luatvietnam.vn/thue-phi-le-phi/cong-van-11133-btc-cst-bo-tai-chinh-116527-d6.html`
- **Trích nguyên văn công thức và quy định:**
  > *"Đối với cá nhân chuyển nhượng chứng khoán phái sinh (hợp đồng tương lai): Cá nhân cư trú, cá nhân không cư trú nộp thuế theo thuế suất 0,1% trên giá chuyển nhượng từng lần."*
  >
  > *"Giá chuyển nhượng từng lần = (Giá thanh toán của hợp đồng tương lai tại thời điểm xác định thu nhập tính thuế × Hệ số nhân hợp đồng × Số lượng hợp đồng × Tỷ lệ ký quỹ ban đầu) / 2"*
  >
  > *"Thời điểm xác định thu nhập tính thuế là thời điểm khớp lệnh mua, bán hợp đồng tương lai của nhà đầu tư trên hệ thống giao dịch của Sở Giao dịch chứng khoán hoặc thời điểm hợp đồng tương lai đáo hạn."*

- **Claude kiểm, 26/09:**
  - Thông tư 87/2026/TT-BTC là văn bản thật. Nó ban hành 30/06/2026, **hiệu lực 01/07/2026**, và **thay thế Thông tư 111/2013/TT-BTC** (có trong danh mục văn bản của chinhphu.vn).
  - Công thức `(giá thanh toán × hệ số nhân × số lượng × tỷ lệ ký quỹ ban đầu) / 2`, thuế suất 0,1% **mỗi lần chuyển nhượng**, khớp giữa nhiều nguồn độc lập (luatvietnam, Vietstock 07/2026, Tạp chí Kinh tế Tài chính).
  - Trang thuvienphapluat mà agent dẫn bị Cloudflare chặn, Claude **không đọc được**. Nguyên văn trích ở trên chưa được Claude đối chiếu từng chữ. Nội dung công thức thì đã được xác nhận qua các nguồn kể trên.
- **Trả lời cụ thể 4 câu hỏi:**
  1. **Thuế suất:** **0,1%** trên giá chuyển nhượng từng lần.
  2. **Cơ sở tính thuế & Công thức:**
     $$\text{Giá chuyển nhượng} = \frac{\text{Giá thanh toán} \times \text{Hệ số nhân (100.000)} \times \text{Số lượng} \times \text{Tỷ lệ ký quỹ ban đầu}}{2}$$
     $$\text{Thuế TNCN} = \text{Giá chuyển nhượng} \times 0,1\%$$
     - **CÓ** nhân tỷ lệ ký quỹ ban đầu (Initial Margin Rate).
     - **CÓ** chia 2 (do bản chất vị thế phái sinh hình thành từ hai phía mua và bán cùng ký quỹ).
  3. **Tần suất thu:** Thu **mỗi lần chuyển nhượng**, áp dụng cho **cả lệnh mở vị thế lẫn lệnh đóng vị thế** (mỗi lần khớp lệnh mua/bán trên hệ thống đều là một lần phát sinh giao dịch chuyển nhượng).
  4. **Tình trạng hiệu lực văn bản:** Công văn 11133/BTC-CST và các quy định pháp quy hóa tương ứng (Thông tư 87/2026/TT-BTC) đang có hiệu lực thi hành, không bị bãi bỏ.

---

### 1b. Phí bù trừ / quản lý vị thế 2.550 đ trả VSDC

- **Trạng thái:** `RESOLVED`
- **Văn bản pháp lý & Nguồn:**
  1. **Thông tư số 83/2024/TT-BTC ngày 26/11/2024 của Bộ Tài chính** (hiệu lực từ 10/01/2025, thay thế Thông tư số 101/2021/TT-BTC) hướng dẫn cơ chế, chính sách giá dịch vụ trong lĩnh vực chứng khoán do Nhà nước định giá tại SGDCK và VSDC.
  2. **Quy chế bù trừ và thanh toán giao dịch chứng khoán phái sinh của VSDC** (Quyết định số 26/QĐ-HĐTV).
  3. **Biểu giá dịch vụ chứng khoán SSI** (hiệu lực 10/10/2025): `https://www.ssi.com.vn/khach-hang-ca-nhan/bieu-phi/bieu-gia-dich-vu-giao-dich-chung-khoan`.
- **Trích nguyên văn (Claude đối chiếu HTML gốc của SSI, 26/09):** dòng 3 của bảng phí trả HNX/VSDC ghi
  > "Giá dịch vụ bù trừ chứng khoán phái sinh | 2,550 đồng/hợp đồng vị thế"

  *(Bản agent nộp đặt một câu diễn giải trong ngoặc kép như trích dẫn, kèm ý "từ khi hệ thống KRX vận hành" không có nguồn. Claude đã bỏ câu đó.)*
- **Căn cứ cho "thu theo mỗi hợp đồng khớp" (Claude kiểm):** FAQ phí của VNDIRECT ghi phí bù trừ 2.550 đ **theo mỗi hợp đồng khớp**, mở và đóng trong cùng ngày là 5.100 đ, và phí này **thay cho phí quản lý vị thế từ 05/05/2025**. Đây là nguồn của công ty chứng khoán, không phải văn bản gốc. Chưa đọc được nguyên văn phần biểu giá của Thông tư 83/2024/TT-BTC. Mô hình vẫn chấp nhận được vì cách tính theo mỗi lượt là **bảo thủ**: nếu sai thì chi phí bị tính dư 2.550 đ/vòng, không bị tính thiếu.

- **Trả lời cụ thể 3 câu hỏi:**
  1. **Cơ sở tính phí:** Tính trên **mỗi hợp đồng giao dịch khớp lệnh** (mở vị thế và đóng vị thế).
  2. **Một vòng mở và đóng trong cùng phiên:** **CÓ bị thu 2 lần**, bao gồm:
     - 2.550 đ khi khớp lệnh mở vị thế.
     - 2.550 đ khi khớp lệnh đóng vị thế.
     - Tổng cộng: **5.100 đ / hợp đồng / vòng giao dịch**.
  3. **Giữ qua đêm N ngày:** **Không thu thêm phí vị thế qua đêm theo ngày**. Kể từ khi vận hành theo Thông tư 83/2024/TT-BTC và cơ chế bù trừ mới, VSDC không thu phí lưu giữ vị thế theo từng đêm nữa mà đã chuyển sang thu trọn gói theo phí dịch vụ bù trừ khi khớp lệnh (2.550 đ/lượt). Khoản phí duy nhất giữ theo thời gian là Phí quản lý tài sản ký quỹ (0,0024%/tháng).

---

### 1c. Tỷ lệ ký quỹ ban đầu hiện hành của VN30F

- **Trạng thái:** `RESOLVED`
- **Cơ quan ban hành:** Tổng công ty Lưu ký và Bù trừ Chứng khoán Việt Nam (VSDC - trước đây là VSD).
- **Mức tỷ lệ ký quỹ ban đầu (Initial Margin - IM):** **17%** (0,17).
- **Nguồn gốc (Claude kiểm, 26/09):** `https://vsdc.vn/vi/ad/177750`. Bảng của VSDC ghi **17%** cho VN30F2501, 2502, 2503, 2506, cập nhật 18/12/2024.
- **Cách VSDC công bố:** VSDC công bố tỷ lệ **theo từng mã hợp đồng, định kỳ**. Đây không phải một quyết định áp dụng mãi. Có một thông báo hiệu lực **19/12/2025** (Vietstock đăng lại), nhưng số liệu nằm trong file Excel đính kèm mà Claude chưa đọc được. Vì vậy 17% là giá trị **đã kiểm tới 12/2024**, chưa kiểm cho các mã 2026.
- **Hệ quả nếu số này lệch:** thuế tỷ lệ thuận với tỷ lệ ký quỹ. Ví dụ, nếu tỷ lệ thật là 18% thì thuế mỗi lượt tăng khoảng 6%, tức khoảng 950 đ ở giá 1.900 điểm.
- *(Bản agent nộp dẫn "Quyết định 71/QĐ-VSD ngày 15/12/2022" qua một bài báo năm 2022, tức nguồn thứ cấp và đã cũ, trái quy tắc nguồn của brief. Claude đã thay bằng nguồn trên.)*

---

## Chi phí phát hiện thêm ngoài phạm vi (Ghi nhận để audit, không mô hình vào broker)

1. **Thuế GTGT (VAT) trên phí dịch vụ:** *(Claude đính chính.)* Bản agent nộp cho rằng phí môi giới 3.000 đ chịu VAT 10%. Nhận định này **sai và không có nguồn**. Theo Luật Thuế GTGT, môi giới chứng khoán thuộc nhóm dịch vụ kinh doanh chứng khoán **không chịu thuế GTGT**. Biểu phí SSI cũng chỉ ghi "đã bao gồm VAT" / "chưa bao gồm VAT" ở các dịch vụ ngân hàng và SMS, không ghi ở phí giao dịch. **Không có khoản VAT nào cần mô hình.**
2. **Phí quản lý tài sản ký quỹ tại VSDC:**
   - Mức: 0,0024%/tháng trên tổng giá trị số dư ký quỹ (tối thiểu 100.000 đ/tháng, tối đa 1.600.000 đ/tháng).
   - Đây là chi phí định kỳ hàng tháng của tài khoản ký quỹ phái sinh, không phụ thuộc vào số lượng lệnh giao dịch trong ngày nên không mô hình vào broker theo lượt lệnh.
