# Mục tiêu và ngưỡng đánh giá chiến lược (đăng ký trước)

**Hiệu lực từ:** 04/10/2026. **Người chốt:** chủ dự án. **Soạn:** Claude.
**Mục đích:** định nghĩa trước "chiến lược có lời" là gì, để không ai (kể cả planner) đổi tiêu chí sau
khi đã thấy dữ liệu. Mọi phép đo chiến lược về sau phải dẫn chiếu tài liệu này.

## 0. Đầu vào do chủ dự án chốt (04/10/2026)

| Mục | Giá trị |
|---|---|
| Vốn rủi ro dành cho hệ thống tự động | **100.000.000 đồng** |
| Drawdown tối đa chịu được | **7% vốn rủi ro = 7.000.000 đồng** |
| Lãi suất tiền gửi tham chiếu (hurdle 3) | **9%/năm** (chủ dự án cung cấp 04/10/2026; chưa đối chiếu nguồn ngân hàng) |
| Quy tắc dừng cứng | Drawdown từ đỉnh vốn ≥ 7% (7 triệu đồng) thì tắt hệ thống: **chủ dự án xác nhận 04/10/2026** |
| Mức duyệt | Duyệt toàn bộ mục A–G bên dưới |

## 1. Hệ quả trực tiếp của mức 7% (đọc trước)

- 7 triệu đồng tương đương **70 điểm VN30F** (1 điểm = 100.000 đồng). Một hợp đồng ở chỉ số 1.900 có
  giá trị danh nghĩa khoảng 190 triệu, nên một cú đi ngược 70 điểm (khoảng 3,7%) là hết ngân sách
  drawdown. Chiến lược phái sinh phải có cắt lỗ theo điểm và kích thước hợp đồng sao cho chuỗi xấu
  nhất vẫn trong 70 điểm. Ngưỡng lỗ ngày 2% (20 điểm) và dừng sau 2 lệnh thua liên tiếp đã có sẵn trong
  `DerivativeRiskManager`.
- Mua-và-giữ ETF VN30 có MDD lịch sử 47,74% (đợt 161). Nếu coi MDD lịch sử là thước đo thô, vị thế ETF
  tương ứng 7 triệu drawdown chỉ khoảng **15% vốn rủi ro** (7 / 47,74), và đó là ước tính thô: drawdown
  tương lai thường xấu hơn mức xấu nhất đã thấy. Cổ phiếu và ETF không thể chiếm toàn bộ 100 triệu
  nếu muốn giữ trong 7%.
- **Hệ quả của hurdle 9%/năm:** 9% trên 100 triệu là 9 triệu đồng mỗi năm, tương đương khoảng 90
  điểm VN30F ròng mỗi năm với một hợp đồng. Với MDD tối đa 7%, chỉ để ngang tiền gửi cũng cần tỷ số
  lãi năm / MDD (Calmar) ≥ 9 / 7 ≈ 1,29; tiền gửi không có drawdown nên yêu cầu thực tế còn cao hơn.
  Với cổ phiếu và ETF, tiêu chí CAGR ≥ mua-và-giữ − 1 điểm (≈ 12,34%) đã cao hơn 9%, nên hurdle 3 chỉ
  ràng buộc thật với chiến lược alpha.
- Vì vậy tiêu chí "MDD ≤ ⅔ MDD mua-và-giữ" (mục B) cho phép khoảng 31,8%, **vượt xa 7%**. Từ nay mức
  tuyệt đối 7% là ràng buộc ưu tiên; tiêu chí ⅔ chỉ còn là điều kiện bổ sung, không còn là ràng buộc
  chính.

## A. Mục tiêu
Thành công là lãi ròng sau mọi chi phí và thuế, tính trên vốn rủi ro, và phải thắng hurdle ở cả ba giai
đoạn: mẫu thử (IS), tập niêm phong, và paper forward. **Mọi giai đoạn đều phải giữ MDD ≤ 7% vốn rủi ro.**

## B. Hurdle phải thắng

| Loại chiến lược | Tiêu chí | Ghi chú |
|---|---|---|
| Mọi loại | **MDD ≤ 7% vốn rủi ro** (tuyệt đối, ưu tiên cao nhất) | Chủ dự án chốt 04/10/2026 |
| Beta thấp (cổ phiếu, ETF) | MDD ≤ ⅔ MDD mua-và-giữ **và** CAGR ≥ mua-và-giữ − 1 điểm % | Đúng tiêu chí đợt 161; bổ sung cho mức 7%. Mua-và-giữ ETF VN30: CAGR 13,34%, MDD 47,74% (2017 → 09/2026) |
| Alpha, trung tính (phái sinh, perpetual) | Lãi kỳ vọng mỗi vòng ≥ **1,5 lần** chi phí thật (phí, thuế, spread/trượt giá) | Đợt 98 dùng 1,0 lần; 1,5 chừa biên cho trượt giá thực thi |
| Mọi loại | Lãi ròng trên vốn rủi ro ≥ **9%/năm** (lãi suất tiền gửi, quy đổi theo thời gian chiếm vốn) | Chỉ đánh giá được khi quy năm trên cửa sổ ≥ 12 tháng hoặc bằng kiểm định thống kê; không kết luận trên cửa sổ vài tuần |

## C. Ngưỡng thống kê và mẫu
- p < 0,05 một phía (hoán vị khối, Holm trong họ giả thuyết) ở IS, **rồi lặp lại p < 0,05** trên tập
  niêm phong (đúng một cặp, mở đúng một lần, ghi vào `docs/holdout-unlock-log.md`). Cần cả hai.
- Mẫu tối thiểu: ≥ 100 lệnh độc lập, hoặc ≥ 60 phiên với tín hiệu tần suất cao. Dưới mức đó ghi nhãn
  **THIẾU SỨC MẠNH**, không kết luận âm hay dương.

## D. Rủi ro
- Vốn rủi ro 100 triệu; **quy tắc dừng cứng: drawdown từ đỉnh vốn ≥ 7% (7 triệu đồng) thì tắt hệ thống,
  không tự bật lại, chủ dự án xem xét trước khi chạy tiếp.** (Chủ dự án xác nhận 04/10/2026. Muốn
  đổi ngưỡng thì sửa tại đây và ghi vào mục H.)
- Giữ nguyên ngưỡng có sẵn: lỗ ngày tối đa 2%, dừng sau 2 lệnh thua liên tiếp trong ngày (phái sinh).

## E. Thang chuyển giai đoạn
backtest đủ chi phí (khớp ở nến sau, có spread) → mở tập niêm phong một lần → paper forward ≥ 50 lệnh
hoặc ≥ 3 tháng → vốn thật nhỏ (≤ 10–20% vốn rủi ro) tối thiểu 3 tháng → tăng dần. Bất kỳ bước nào
trượt thì đóng hướng đó.

## F. Ngân sách thử
Tối đa **3 giả thuyết mới mỗi tháng**, mỗi giả thuyết ghi sổ kể cả kết quả âm. Mỗi lần thử thêm làm
ngưỡng "đáng tin" khó hơn.

## G. Bất biến
Không đổi ngưỡng sau khi thấy dữ liệu. Muốn đổi thì ghi ngày và lý do vào mục H **trước** khi chạy
phép đo mới.

## Việc chưa chốt (chưa có hiệu lực)
1. **Đề xuất, chưa được duyệt:** vì drawdown tương lai thường xấu hơn lịch sử, có thể đòi MDD của
   backtest ≤ khoảng 4,7% (= 7% / 1,5) để chừa biên an toàn. Chưa áp dụng cho tới khi chủ dự án duyệt.

## H. Nhật ký thay đổi

| Ngày | Thay đổi | Lý do | Người duyệt |
|---|---|---|---|
| 04/10/2026 | Ban hành bản đầu; MDD tuyệt đối 7% là ràng buộc ưu tiên | Chủ dự án chốt vốn rủi ro 100 triệu và drawdown tối đa 7% | Chủ dự án |
| 04/10/2026 | Điền hurdle 3 = 9%/năm; xác nhận quy tắc dừng cứng (drawdown ≥ 7%) | Chủ dự án trả lời các mục chưa chốt cùng ngày | Chủ dự án |
