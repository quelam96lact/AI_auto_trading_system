# Đợt 195: kết quả xu hướng ngày (MA) + vào lệnh 1 giờ (RSI) + thoát ATR ngày

Brief (đăng ký trước 25/10, spec H cùng ngày): `docs/superpowers/plans/2026-10-25-brief-dot-195-xu-huong-ngay-vao-lenh-1h.md`.
Kết quả thô: `docs/research/dot195/` (sổ thử 8 dòng EA, `exploration_report.md`, `candidates.json` sha256 `fc25c2ea5e68bdac506901971fa0338e01bc3eb373a118728daa04d0d3e10437`).
Chạy ngày 02/11/2026. Agent thực thi: Builder. Audit: Claude.

## Kết luận

**0 ứng viên. Đây là phép đo âm thứ 28.** Theo §6, họ "MA + RSI + ATR" đóng ở cả hai cặp khung: tuần/ngày (đợt 194) và ngày/1 giờ (đợt 195). V1 và V2 không được mở.

- **7/8 cấu hình có `mean_X < 0`.** Cấu hình duy nhất dương là n=100, θ=40, k=3, với `mean_X` +0,30%/lệnh. Mức này không có ý nghĩa thống kê (p 0,29).
- Lệnh thua ròng ở **mọi** ô: `mean_r` từ −1,68% đến −2,82%/lệnh. Tỷ lệ thắng của ô chọn là 26%.
- Ô chọn **trượt Bước 2 (cao nguyên)**: cả 3 láng giềng có `mean_X < 0`. Ô này cũng trượt Bước 3 (p ≥ 0,05, `mean_r` < 0). DSR không tính.

| Cấu hình chọn | Lệnh | Tuần | mean_X | Sharpe_X | p | mean_r | mean_EW | Thắng | Trung vị nến 1h / phiên giữ | STOP/TREND/END |
|---|---|---|---|---|---|---|---|---|---|---|
| n=100, θ=40, k=3 | 110 | 17 | +0,299% | 0,032 | 0,2935 | −1,686% | −1,985% | 26,4% | 45,5 / 10,5 | 38/58/14 |

Bảng phụ 8 ô (chỉ để đọc):

| n | θ | k | Lệnh | mean_X | Sharpe_X | p | mean_r | Trung vị phiên giữ |
|---|---|---|---|---|---|---|---|---|
| 50 | 30 | 2 | 46 | −0,533% | −0,077 | 0,717 | −2,50% | 4,5 |
| 50 | 30 | 3 | 42 | −0,754% | −0,133 | 0,819 | −2,82% | 5,0 |
| 50 | 40 | 2 | 137 | −0,366% | −0,052 | 0,741 | −2,12% | 6,0 |
| 50 | 40 | 3 | 113 | −0,278% | −0,038 | 0,673 | −2,37% | 7,0 |
| 100 | 30 | 2 | 54 | −0,577% | −0,080 | 0,744 | −2,12% | 9,0 |
| 100 | 30 | 3 | 47 | −0,731% | −0,110 | 0,838 | −2,66% | 10,0 |
| 100 | 40 | 2 | 141 | −0,163% | −0,021 | 0,664 | −1,68% | 9,0 |
| 100 | 40 | 3 | 110 | +0,299% | 0,032 | 0,294 | −1,69% | 10,5 |

**Chỗ không được đọc quá:**
- Toàn bộ dữ liệu là 87 phiên (03/04 → 07/08/2026) trong một trạng thái thị trường. Ở giai đoạn này EW cũng âm (−2%/lệnh).
- Việc `mean_X` dương nhẹ ở một ô chỉ có nghĩa là ô đó "thua ít hơn rổ", không phải có lãi. Ô đó cũng không đứng vững khi đổi bất kỳ tham số nào một bước.

## Audit của Claude (02/11)

- **Test:**
  - Claude tự đếm được 36 `def test_` (32 core + 4 validator), khớp báo cáo. 36/36 xanh, ruff sạch.
  - Suite không integration theo agent là 2283 passed.
- **Chạy lại khám phá** vào thư mục tạm: 8 dòng sổ (cột tham số → p) **khớp từng chữ số**. `candidates.json` cùng sha256.
- **Đếm độc lập bằng code riêng của Claude** (`recount.py` ở scratchpad, viết lại toàn bộ luật §3, chỉ dùng chung các hàm cơ sở `_RsiState`, `AtrCalculator`, `is_liquid`, `is_ceiling_open`, `is_floor_locked`, `compute_stock_net_return`, `bootstrap_by_month`):
  - Ô chọn khớp **chính xác**: 110 lệnh, 17 tuần, `mean_X` 0,002989, Sharpe_X 0,0324, p 0,2935, `mean_r` −0,016857, `mean_EW` −0,019846, thắng 26,36%, trung vị 45,5 nến, STOP/TREND/END 38/58/14.
  - 6/8 ô khớp chính xác.
  - Hai ô n=50, θ=30 lệch đúng **1 lệnh** (POM, mua 10/07/2026 nến 11 giờ). POM chỉ giao dịch thứ Sáu, nên không có close ngày ở phiên liền trước phiên mua. Agent coi thiếu giá tham chiếu là chặn mua. Claude dùng close gần nhất, vì đó cũng là giá tham chiếu thật. Brief không quy định trường hợp này.
  - Kết luận không đổi: lệch không nằm ở ô chọn, và hai ô đó vẫn âm (Claude: 47 lệnh, `mean_X` −0,543%, p 0,726).
  - Ghi chú phụ cho lần sau: code agent dùng xử lý "thiếu ref" không đối xứng. Phía mua bị chặn, còn phía bán bỏ qua phép kiểm khoá sàn.
- **Phép phá do Claude tự làm** (sửa code sản phẩm, chạy test, khôi phục): cả 3 lần đều có test đỏ.
  - T+2 từ nến 13 → 9;
  - điều kiện RSI cắt lên → luôn đúng;
  - `PRIOR_NEGATIVE_FAMILIES` 27 → 26.
- **Báo cáo agent:** bảng phép phá ghi tên hàm sản phẩm **không tồn tại** (`resample_5m_to_1h`, `compute_daily_trend`, …). Code thật là `resample_1h`, `daily_trend_series`, …, và test import đúng hàm thật. Lỗi nằm ở báo cáo, không ở code.
- Agent cam kết không truy vấn DB, không gọi API, không đọc ngoài `data/research195/explore/`. Claude grep code mới: chỉ đọc qua các loader của thư mục dữ liệu.
