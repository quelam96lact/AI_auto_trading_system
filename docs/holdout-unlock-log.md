# NHẬT KÝ MỞ KHÓA TẬP DỮ LIỆU NGOÀI MẪU (HOLDOUT UNLOCK LOG)

| Thời gian | Chiến lược | Cấu hình tham số | Lý do mở khóa |
|---|---|---|---|
| 2026-09-06 02:29:56 | OctopusPullback | Sensitivity Analysis (holdout) | Kiem tra dot 9b Task 4 |
| 2026-10-04 | Volatility targeting phủ lên E1VFVN30 mua-và-giữ (đợt 161) | EWMA λ=0,94, mục tiêu = trung vị mở rộng, ngưỡng 0,20 — chốt trước khi chạy, không chỉnh sau | **Lỗi của brief (Claude), không phải agent:** brief chốt đo tới 30/09/2026 mà không nhắc niêm phong cổ phiếu từ 2023-01-01 (đợt 120). Kết luận KHÔNG ĐẠT giống hệt khi chỉ đo 2017–2022 (Claude tính lại). Hệ quả: dữ liệu E1VFVN30 từ 2023 KHÔNG còn là ngoài mẫu cho họ volatility targeting / chia vốn theo biến động. |
| 2026-10-08 14:40:54 | Mốc chuẩn ETF + tiền gửi (đợt 165) | w=15%, rebalance=annual, r=6% & r=0% | Đánh giá mốc chuẩn tham chiếu trên tập niêm phong sau khi audit IS (E1VFVN30) |
| 2026-10-10 | Phá đỉnh Donchian 55/20 cổ phiếu (đợt 175) | Đỉnh 55 phiên (không gồm t), kênh đáy 20, cắt lỗ 10%, giữ ≤ 40 phiên, thanh khoản ≥ 2 tỷ — chốt trước, không chỉnh. Tín hiệu 2023-01-01 → 2026-07-31, đọc nến từ 2022-01-01 để làm nóng | IS 2017–2022 ĐẠT cả bốn điều kiện (Claude kiểm độc lập khớp 3.173/3.173 lệnh). Mở MỘT lần theo brief 175 §5, lặp lại đủ bốn điều kiện. Ghi TRƯỚC khi chạy |
| 2026-10-10 | Ma trận tương quan rổ đang chạy HPG/IJC/AAA (đợt 180) — phép MÔ TẢ rủi ro, không phải chiến lược | Lợi suất log ngày, tương quan Pearson/Spearman, trị riêng, PR, lỗ rổ theo định cỡ ATR; cửa sổ B 2023-01-01 → 2026-10-01; chốt trong brief 180 §1 + §8 | Câu hỏi là rủi ro của rổ HÔM NAY nên cần dữ liệu gần; không chọn hay chỉnh luật giao dịch nào. Claude cho phép và ghi TRƯỚC khi agent chạy |
