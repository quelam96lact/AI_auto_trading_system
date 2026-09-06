"""Phí giao dịch crypto — BingX perpetual.

Nguồn (chủ dự án cung cấp 2026-09-06):
https://bingx.com/vi/learn/article/crypto-trading-bingx-fees

    Perpetual futures (VIP0):  maker 0,02%  |  taker 0,05%
    Spot (VIP0):               từ 0,1% cả hai chiều

Chủ dự án đã chốt dùng **perpetual** (quyết định F), nên chỉ hàng perpetual có
hiệu lực ở đây.

DÙNG TAKER CHO HỌ CHIẾN LƯỢC HIỆN CÓ. Lý do phải hiểu, đừng đổi: vào lệnh bằng
BUY/SELL STOP và thoát bằng SL đều là lệnh dừng — khi kích hoạt sẽ ăn vào sổ
lệnh, tức taker. Chỉ nhánh thoát bằng TP mới có thể là maker (0,02%) nếu đặt
dạng lệnh giới hạn chờ sẵn. `run_pattern_backtest` dùng MỘT `fee_rate` chung
cho cả hai chiều, nên lấy taker là hơi thận trọng ở nhánh TP — chấp nhận, và
ghi rõ trong báo cáo. Không tự chẻ thành hai mức.

HAI ĐIỀU TRANG NGUỒN KHÔNG NÓI — CẤM TỰ ĐIỀN:

1. Mức phí từng bậc VIP. Trang chỉ nói phí giảm dần VIP0→VIP5. VIP0 là giả định
   thận trọng nhất; nếu chủ dự án ở bậc cao hơn thì phí thật thấp hơn, lệch về
   phía an toàn.
2. Phí funding. Vị thế perpetual giữ qua chu kỳ funding phải trả (hoặc nhận)
   khoản này, và trên khung 1H nhiều lệnh sống qua vài chu kỳ. Đây là **hạn chế
   đã biết** của mọi phép đo crypto trong repo, phải nêu trong báo cáo. Khoản
   thiếu này thường bất lợi cho phía LONG trong thị trường tăng.

VÌ SAO CON SỐ NÀY QUAN TRỌNG: phí tính trên giá trị danh nghĩa, không phải ký
quỹ. Với vốn 100.000 USDT/mã không đòn bẩy thì một vòng mua-bán tốn ~100 USDT.
Các báo cáo hybrid từng có 13.612–27.571 lệnh ⇒ tổng phí ~1,36–2,76 triệu USDT,
cùng bậc độ lớn với chính con số "lợi nhuận" chúng báo khi chạy `fee_rate=0.0`.
Đó là lý do hằng số này tồn tại thay vì để mỗi script tự gõ lại.
"""

BINGX_PERP_MAKER = 0.0002
BINGX_PERP_TAKER = 0.0005
