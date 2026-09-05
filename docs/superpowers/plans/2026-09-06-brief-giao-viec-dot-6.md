# Brief giao việc — đợt 6

Viết 06/09, sau quyết định G/F/K (`2026-09-03-plan-xu-ly-ton-dong.md` §7).
Image hiện cũ hơn **16 giờ 57 phút** so với commit gần nhất chạm `trading/`
(vẫn đúng — chưa dựng lại kể từ gói L).

---

## 0. Hai gói giao được, không giẫm chân nhau

| Gói | File brief | Chạm gì | Phụ thuộc |
|---|---|---|---|
| **K** | `2026-09-06-brief-goi-K-thanh-khoan-theo-ngay.md` (đã viết, đã push) | `trading/` (chạm engine) | Không — làm ngay |
| **R2** | Đặc tả ở §1 dưới đây | `docs/superpowers/research/` (chỉ báo cáo) | Không — làm ngay |

Hai gói không dùng chung file — giao song song được. **K quan trọng hơn**: nó
sửa lý do engine đang câm. R2 chỉ gỡ nút C3, không khẩn.

---

## 1. GÓI R2 — làm lại lịch nghỉ lễ 2027, đúng cách lần này

### 1.1 Vì sao làm lại

Gói R (đợt 5) bị bác khi audit: phần 2026 đúng và đã tự chứng minh bằng cách
đối chiếu ngược `bars_daily` (13/13 ngày khớp). Nhưng phần **2027 không có
nguồn nào** — chỉ có suy luận trình bày như kết luận chính thức, đúng thứ brief
đã cấm. Xem phụ lục audit trong `2026-09-05-dot-4-q-r-report.md`.

R2 chỉ làm lại phần 2027. Không làm lại 2026 — đã xong, đừng đo lại.

### 1.2 Việc

Tra **nguồn chính thức** cho lịch nghỉ lễ Việt Nam 2027, đặc biệt Tết Đinh Mùi
(dự kiến rơi giữa tháng 2/2027 — cần biết sớm vì ảnh hưởng `holidays` trong
`config.yaml` sang năm sau).

### 1.3 Ràng buộc cứng — lặp lại nguyên văn vì lần trước không theo

- Mỗi ngày đề xuất phải kèm **URL nguồn cụ thể** (không phải tên miền trần)
  **và đoạn trích nguyên văn** nói ra đúng ngày đó. Không có cả hai ⇒ không
  đưa vào danh sách chính thức.
- Nguồn hợp lệ: văn bản nhà nước VN (nghị định/thông báo nghỉ lễ có số hiệu,
  tra được), hoặc thông báo lịch giao dịch HOSE/HNX/VSD **có link**. Không
  dùng báo/blog tổng hợp, không suy luận từ Điều 112 Bộ luật Lao động (điều đó
  chỉ quy định *loại* ngày lễ, không cho *ngày cụ thể của năm 2027*).
- **Không tìm được nguồn có thẩm quyền cho ngày nào thì để ngày đó riêng trong
  mục "chưa chắc — chưa có nguồn"**, không trộn vào danh sách chính dù chỉ là
  "phương án dự kiến". Đây là điểm chính xác gói R cũ đã sai.
- Không sửa `config/config.yaml`. Đây là gói tra cứu, không phải gói code —
  không đụng `trading/`, `scripts/`, `tests/`.

### 1.4 Tiêu chí

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Mỗi ngày có URL + trích dẫn | dán cả hai cho từng ngày trong danh sách chính |
| 2 | Ngày không có nguồn nằm riêng | mục "chưa chắc" tách bạch, không lẫn vào danh sách chính |
| 3 | Không dùng Điều 112 làm nguồn cho ngày cụ thể | chỉ dùng để phân loại ngày lễ theo luật vs nghỉ bù, không dùng để suy ra ngày |

### 1.5 Phạm vi

- **Sửa:** một file báo cáo mới trong `docs/superpowers/research/`
  (`2026-09-06-lich-nghi-le-2027.md` hoặc tên tương tự).
- **Không đụng:** mọi thứ khác.

---

## 2. Vẫn chờ chủ dự án — không đổi

**E** (vốn/tài khoản thật), **C1** (VPS Ubuntu), **C2** (Docker tự khởi động),
**D1** (diễn tập dead-man's switch, cần phiên thật — sớm nhất thứ Hai đã qua,
giờ là phiên kế tiếp), **J** (hướng sửa đường thoát lệnh thật — gói K không
đụng vào J).

## 3. Việc của Claude sau khi hai gói xong

- Audit gói K bằng cách chạy lại tiêu chí cổng (tái hiện bảng khung ngày).
- Audit gói R2: kiểm từng URL thật sự mở được và trích dẫn khớp.
- Dựng lại image — gộp gói K với mọi thay đổi tồn từ gói L đến nay, một lần.
- Đăng ký scheduled task `trading-engine-cam` (vẫn hoãn, không phụ thuộc K/R2).
