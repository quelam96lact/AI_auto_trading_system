# Mục tiêu và ngưỡng đánh giá chiến lược (đăng ký trước)

**Hiệu lực từ:** 04/10/2026. **Người chốt:** chủ dự án. **Soạn:** Claude.
**Mục đích:** định nghĩa trước "chiến lược có lời" là gì, để không ai (kể cả planner) đổi tiêu chí sau
khi đã thấy dữ liệu. Mọi phép đo chiến lược về sau phải dẫn chiếu tài liệu này.

## 0. Đầu vào do chủ dự án chốt (04/10/2026)

| Mục | Giá trị |
|---|---|
| Vốn rủi ro dành cho hệ thống tự động | **100.000.000 đồng** |
| Drawdown tối đa chịu được | **7% vốn rủi ro = 7.000.000 đồng** |
| Lãi suất tiền gửi tham chiếu (hurdle 3) | **6%/năm** (chủ dự án chốt 08/10/2026, "lãi suất cơ bản"; thay mức 9% của 04/10 — xem mục H) |
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
- **Hệ quả của hurdle 6%/năm** (từ 08/10/2026; trước đó 9%): 6% trên 100 triệu là 6 triệu đồng mỗi
  năm, tương đương khoảng 60 điểm VN30F ròng mỗi năm với một hợp đồng. Với MDD tối đa 7%, chỉ để ngang
  tiền gửi cũng cần tỷ số lãi năm / MDD (Calmar) ≥ 6 / 7 ≈ 0,86; tiền gửi không có drawdown nên yêu cầu
  thực tế còn cao hơn. Với cổ phiếu và ETF, tiêu chí CAGR ≥ mua-và-giữ − 1 điểm (≈ 12,34%) đã cao hơn
  6%, nên hurdle 3 chỉ ràng buộc thật với chiến lược alpha.
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
| Mọi loại, khi đánh giá bằng backtest | **MDD backtest ≤ 4,7% vốn rủi ro** (= 7% / 1,5) | Biên an toàn vì drawdown tương lai thường xấu hơn backtest. Chủ dự án duyệt 04/10/2026. Mức 7% vẫn là ngưỡng dừng cứng khi chạy thật (mục D) |
| Beta thấp (cổ phiếu, ETF) | MDD ≤ ⅔ MDD mua-và-giữ **và** CAGR ≥ mua-và-giữ − 1 điểm % | Đúng tiêu chí đợt 161; bổ sung cho mức 7%. Mua-và-giữ ETF VN30: CAGR 13,34%, MDD 47,74% (2017 → 09/2026) |
| Alpha, trung tính (phái sinh, perpetual) | Lãi kỳ vọng mỗi vòng ≥ **1,5 lần** chi phí thật (phí, thuế, spread/trượt giá) | Đợt 98 dùng 1,0 lần; 1,5 chừa biên cho trượt giá thực thi |
| Mọi loại | Lãi ròng trên vốn rủi ro ≥ **6%/năm** (lãi suất tiền gửi, quy đổi theo thời gian chiếm vốn) | Chỉ đánh giá được khi quy năm trên cửa sổ ≥ 12 tháng hoặc bằng kiểm định thống kê; không kết luận trên cửa sổ vài tuần |

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

## H. Nhật ký thay đổi

| Ngày | Thay đổi | Lý do | Người duyệt |
|---|---|---|---|
| 04/10/2026 | Ban hành bản đầu; MDD tuyệt đối 7% là ràng buộc ưu tiên | Chủ dự án chốt vốn rủi ro 100 triệu và drawdown tối đa 7% | Chủ dự án |
| 04/10/2026 | Điền hurdle 3 = 9%/năm; xác nhận quy tắc dừng cứng (drawdown ≥ 7%) | Chủ dự án trả lời các mục chưa chốt cùng ngày | Chủ dự án |
| 04/10/2026 | Áp dụng biên an toàn: MDD backtest ≤ 4,7% (mục B). Mục "Việc chưa chốt" bỏ vì không còn việc nào | Chủ dự án duyệt đề xuất 4,7% | Chủ dự án |
| 08/10/2026 | Hurdle 3: 9%/năm → **6%/năm** (lãi suất tiền gửi tham chiếu). Đợt 165 thêm r = 6% vào IS và đổi hai cấu hình mở niêm phong thành w = 15%, r = 6% và r = 0% (brief 165 §7) | Chủ dự án chốt sau khi Claude nêu mức 9% chưa kiểm nguồn. **Ghi nhận:** đổi SAU khi đã thấy kết quả IS đợt 165 (r = 9%), TRƯỚC khi mở niêm phong | Chủ dự án |
| 09/10/2026 | Cho phép **giả thuyết thứ 4 của tháng 10** (vượt ngân sách mục F): tối ưu tham số `octopus_pullback` trên nến ngày, theo brief đợt 171 (lưới 12 bộ chốt trước, walk-forward 2016–2019 chọn / 2020–2022 kiểm). Kết quả **bắt buộc** mang cảnh báo đa so sánh. Octopus đã nhìn dữ liệu 2023+ (đợt 18, nhật ký niêm phong 06/09) nên không còn tập niêm phong sạch; qua kiểm 2020–2022 chỉ mở đường tới paper forward, không tới vốn thật | Chủ dự án chọn phương án (b) "sửa spec để chạy ngay" sau khi Claude khuyến nghị chờ tháng 11. Ghi TRƯỚC khi chạy | Chủ dự án |
| 10/10/2026 | **Không dùng mã đã hủy niêm yết** trong dữ liệu cổ phiếu. Đợt 172 hủy; đợt 171 bỏ cổng dữ liệu (brief 171 §7). Mọi phép đo cổ phiếu trên `bars_daily` phải ghi cảnh báo thiên lệch sống sót và chỉ so với mua đều/mua-và-giữ cùng universe, không so với ETF hay mốc chuẩn đợt 165 | Chủ dự án quyết định. Ghi TRƯỚC khi chạy đợt 171 | Chủ dự án |
| 10/10/2026 | Cho phép **giả thuyết thứ 5 của tháng 10** (vượt ngân sách mục F): pullback trong xu hướng, giữ 2–4 tuần, theo brief đợt 173 (quy tắc chốt trước). Kết quả mang cảnh báo đa so sánh (5 giả thuyết trong tháng) và thiên lệch sống sót | Chủ dự án chọn hướng "pullback trong xu hướng tuần" và "sửa spec, chạy ngay" sau khi Claude khuyến nghị chờ 01/11. Ghi TRƯỚC khi chạy | Chủ dự án |
| 10/10/2026 | Cho phép **giả thuyết thứ 6 của tháng 10** (vượt ngân sách mục F): phá đỉnh Donchian 55/20 trên cổ phiếu, cắt lỗ 10%, giữ ≤ 40 phiên, theo brief đợt 175 (quy tắc chốt trước). Kết quả mang cảnh báo đa so sánh (6 giả thuyết trong tháng) và thiên lệch sống sót | Chủ dự án yêu cầu "tìm chiến lược tối ưu khác… giao dịch trên tín hiệu kĩ thuật" và hai lần từ chối câu hỏi chọn họ tín hiệu/ngân sách; Claude chọn Donchian (họ kỹ thuật chưa đo trên cổ phiếu VN) và chạy ngay theo tiền lệ 09/10, 10/10. Ghi TRƯỚC khi chạy | Chủ dự án (Claude chọn chi tiết) |
| 10/10/2026 | Cho phép **giả thuyết thứ 7 của tháng 10** (vượt ngân sách mục F): quá bán RSI(2) trên MA200, thoát MA5 / 10 phiên, theo brief đợt 177 (quy tắc chốt trước, thêm điều kiện 5 "vượt trội theo lệnh > 0 sau khi bỏ 1% lệnh lãi nhất" vì bài học đợt 175). Kết quả mang cảnh báo đa so sánh (7 giả thuyết) và thiên lệch sống sót; tập 2023+ là lần mở thứ hai | Chủ dự án yêu cầu "tìm thêm chiến lược giao dịch mới" ngay sau khi Claude khuyến nghị dừng đo trong tháng 10; Claude chọn họ quá bán. Ghi TRƯỚC khi chạy | Chủ dự án (Claude chọn chi tiết) |

| 10/10/2026 | Cho phép **giả thuyết thứ 8 của tháng 10** (vượt ngân sách mục F): áp nguyên văn bốn luật đã có (octopus, pullback 173, Donchian 175, RSI2 177) vào riêng VCB 2017–2022, so với mua-và-giữ VCB; Bonferroni p < 0,0125; theo brief đợt 181. Kết quả mang cảnh báo chọn mã sau khi luật đã trượt trên toàn thị trường, mẫu nhỏ, đa so sánh (8 giả thuyết); không mở 2023+ và không dẫn tới vốn thật | Chủ dự án yêu cầu "kiểm tra chiến lược giao dịch trên mã VCB"; Claude chọn cách hiểu (dùng lại luật có sẵn, không đặt luật mới). Ghi TRƯỚC khi chạy | Chủ dự án (Claude chọn chi tiết) |
| 11/10/2026 | Cho phép **giả thuyết thứ 9 của tháng 10** (vượt ngân sách mục F): order flow VN30F theo footprint — phân kỳ CVD, hấp thụ, chuỗi mất cân bằng chéo × chân trời 15/30 phút (6 cặp), theo brief đợt 182. Cùng tập IS 25/09–30/11 và holdout từ 01/12 với đợt 162 (tổng 15 cặp trên cùng dữ liệu); Bonferroni 0,05/6; ngưỡng chi phí gồm thêm 0,2 điểm trượt giá. Đo từ 01/12; không có đường tới lệnh thật | Chủ dự án gửi danh sách phát YouTube về order flow (riêng tư, Claude chỉ đọc được tên video đầu) và yêu cầu triển khai; Claude chọn ba khái niệm order flow chuẩn không trùng OFI của 162. Ghi TRƯỚC khi dựng công cụ | Chủ dự án (Claude chọn chi tiết) |
| 11/10/2026 | **Sửa giả thuyết thứ 9 (brief đợt 182 v2) TRƯỚC khi có code và trước khi mở dữ liệu**: E2 đảo chiều theo video (nến giảm + delta dương lớn ⇒ mua); E3 đổi từ "≥3 mức imbalance liên tiếp" sang bộ đôi hấp thụ (nến t−1) → khởi xướng ngược chiều (nến t), imbalance chéo 3:1; E1 giữ nguyên. Vẫn 6 cặp, cùng cổng, cùng ngày đo | Chủ dự án gửi bản tóm tắt nội dung video (Fractal Flow); v1 làm E2 ngược chiều video và E3 không xét giá đóng cửa so với imbalance | Chủ dự án (Claude đối chiếu) |
| 11/10/2026 | Đăng ký trước **giả thuyết thứ 1 của tháng 11** (phần đo chỉ được chạy từ 01/11/2026): order flow BTCUSDT perp theo footprint 5 phút, đúng ba sự kiện của brief 182 v2 × chân trời 15/30 phút (6 cặp), theo brief đợt 183. Dữ liệu aggTrades Binance Vision 2023-01 → 2026-08 (niêm phong crypto giữ nguyên); CHÍNH 2023–2024, LẶP LẠI 2025 → 08/2026; Bonferroni 0,05/6; ngưỡng 1,5 × (phí BingX 0,10% + trượt 0,04%). Không có đường tới lệnh thật | Chủ dự án muốn áp order flow cho phái sinh, forex, crypto. Forex không có khối lượng chủ động thật (giao ngay phi tập trung; dữ liệu CME phải mua) nên không làm; phái sinh là đợt 182. Phần dựng dữ liệu làm ngay vì không phải phép thử | Chủ dự án (Claude chọn chi tiết) |
| 11/10/2026 | **Sửa giả thuyết thứ 1 của tháng 11 (brief đợt 183b) TRƯỚC khi đo**, chỉ cho E3 crypto: bước footprint 1 bp (thay 2 bps), lưu footprint đầy đủ, ngưỡng imbalance tương đối theo 5 ngày UTC trước (min_vol = p90, sàn mẫu số = p50 giá trị USDT mỗi mức). Lần sửa duy nhất: nếu ở CHÍNH tỷ lệ nến có imbalance cả hai phía > 50% thì E3 bị loại, Bonferroni giữ 0,05/6. E1/E2, cửa sổ, hurdle, ngày đo giữ nguyên | Claude audit 183 đếm đặc trưng (không tính mục tiêu): 92–96% nến có imbalance cả hai phía vì min_vol 50.000 USDT quá thấp và chỉ 5–6 mức mỗi nến ⇒ E3 suy biến | Claude (lỗi thiết kế của Claude) |
| 11/10/2026 | Cho phép **giả thuyết thứ 10 của tháng 10** (vượt ngân sách mục F): phép đo order flow BTCUSDT perp của brief 183/183b được chạy từ **12/10/2026** thay vì 01/11, theo brief đợt 184. Thiết kế đo giữ nguyên (6 cặp, CHÍNH 2023–24, LẶP LẠI 2025→08/2026, Bonferroni 0,05/6, ngưỡng 0,0021); suất giả thuyết thứ 1 tháng 11 được trả lại. VN30F (162/182) KHÔNG đổi: cổng 01/12 là điều kiện đủ 40 phiên dữ liệu, không phải ngân sách. Không có đường tới lệnh thật | Chủ dự án: "áp dụng order flow trong tháng 10". Dữ liệu crypto đã dựng và niêm phong tới 08/2026 nên đo sớm không đổi số, chỉ tiêu ngân sách. Ghi TRƯỚC khi chạy | Chủ dự án |
